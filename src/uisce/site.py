"""Build the static status site (out/site/) from out/uisce.db.

Per county and calendar month the generator computes:

- a daily worst-condition status for the statuspage-style day bars
- events, deduplicated by reference_num with pin intervals unioned
- outage notices per 100 km of water main, and the A-F letter cut on that count
  (count_grade); an active boil-water / do-not-drink / do-not-consume notice is
  published beside the letter (health_n) rather than folded into it
- a median notice-to-completion time over events whose end was *observed*
  (an "works are now complete" update), excluding those whose only end signal
  was a schedule — see the notice_to_end_seconds docstring in build.py

Each county then breaks down into named Census areas, a pin placed in the area
of its nearest Small Area centroid, with the same per-class counts as the county
and no letter: a letter needs a length of main, which is published by supply
zone, not by town.

Methodology and data findings are documented in notes/statuspage-methodology.md.
"""

import csv
import html
import json
import math
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import statusui

from uisce.build import reported_end_utc
from uisce.config import (
    BASE_URL,
    DB_PATH,
    DUBLIN,
    OBSERVED_END_SOURCES,
    RECURRING,
    SA_TOWNS_PATH,
    SITE_DIR,
    describes_recurrence,
    plausible_start,
)
from uisce.pipeline import check_schema_version
from uisce.wsz import county_mains_km, read_zones

SITE_HTML = Path(__file__).parent / "site.html"
AREAS_HTML = Path(__file__).parent / "areas.html"
COUNTY_HTML = Path(__file__).parent / "county.html"
AREA_HTML = Path(__file__).parent / "area.html"
SITE_CSS = Path(__file__).parent / "site.css"
AREAS_MARKER = "<!--AREAS-->"
CANONICAL_MARKER = "<!--CANONICAL-->"


def page_html(template, markers):
    """A template with the shared statusui CSS/JS and site.css inlined, then its markers."""
    markers = dict(markers, **{"SITE-CSS": SITE_CSS.read_text()})
    return statusui.assemble(template.read_text(), markers)

# The feed was first snapshotted on 2026-04-20; earlier days are unobserved
# (the ArcGIS source only retains recent notices).
COLLECTION_START = datetime(2026, 4, 20, tzinfo=timezone.utc)

# Notice-to-end spans above this are capped; the genuinely long events
# (conservation restrictions) are classed degraded and never accrue anyway.
CAP_DAYS = 14

# A pin is placed in the area of the nearest Small Area centroid within this.
PLACE_KM = 8.0

# Key and label for the county drill-down bucket holding cases whose pin lies
# nearest a Small Area outside the county the notice names: a disagreement
# between the feed's `county` and its own coordinates, not a gap in the
# geography. See notes/data-quality.md ("county and the pin's own coordinates
# disagree") and notes/statuspage-methodology.md.
UNPLACED = "unplaced"
UNPLACED_LABEL = "Couldn't be placed in a town"

# Census 2022 county populations (approximate; city+county combined), printed
# beside each county and the list of counties a case must name.
COUNTY_POP = {
    "Carlow": 61968, "Cavan": 81704, "Clare": 127938, "Cork": 584156,
    "Donegal": 167084, "Dublin": 1458154, "Galway": 276451, "Kerry": 156458,
    "Kildare": 246977, "Kilkenny": 104160, "Laois": 91877, "Leitrim": 35199,
    "Limerick": 205444, "Longford": 46751, "Louth": 139703, "Mayo": 137970,
    "Meath": 220826, "Monaghan": 65288, "Offaly": 83150, "Roscommon": 70259,
    "Sligo": 70198, "Tipperary": 167895, "Waterford": 127363,
    "Westmeath": 96221, "Wexford": 163919, "Wicklow": 155851,
}

# Severity classes, worst first. Only "outage" is counted.
SEV_ORDER = ["outage", "quality", "degraded", "maintenance"]

QUALITY_CATS = {"boil_notice_issued", "consumption_notice_issued", "discolouration"}
DEGRADED_CATS = {"water_conservation", "low_pressure"}
# The lift category that ends each kind of standing notice. Both kinds are
# published the same way: the issue cannot state its own end, and the lift
# arrives as a separate case with a fresh reference_num. Pairing consults only
# the matching kind, so a boil notice can never be closed by a do-not-consume
# lift that happens to name the same scheme.
LIFT_OF = {
    "boil_notice_issued": "boil_notice_lifted",
    "consumption_notice_issued": "consumption_notice_lifted",
}

IGNORE_CATS = set(LIFT_OF.values())  # a lift is good news, not an event

# Boil notices are the weakest class in the dataset: only 1 of 17 events has a
# real end, and the issue and lift populations are disjoint schemes, so that will
# not grow (notes/boil-notices.md, 2026-09-05). Setting this to True drops the
# class from the metrics entirely — a defensible position, since what survives is
# a handful of events resting on a status flag known to go stale. Left False so
# genuinely-live notices still show; flip it if the class stays this thin.
IGNORE_BOIL_NOTICES = False

# Hard supply outages: the title itself announces lost supply.
HARD_CATS = {
    "burst_main", "reservoir_interruption", "water_treatment_plant_interruption",
    "pump_station_interruption", "pump_failure", "power_outage",
}
# Emergency repair works: supply is normally shut off while they run, so they
# accrue unless the feed says they were planned. NULL categories deliberately
# do NOT group here — see notes/data-quality.md ("A missing variant was
# silently inventing supply outages") for why; unmatched titles fall through
# to maintenance and are printed by every backfill (see backfill_work_category).
REPAIR_CATS = {"mains_repair", "valve_repair", "pump_repair"}

# Only health-relevant quality notices knock a grade; discolouration shows
# but doesn't knock.
KNOCK_CATS = {"boil_notice_issued", "consumption_notice_issued"}

SCHEME_NOISE = {"public", "water", "supply", "scheme", "regional", "pws", "the"}


def is_open(row, now):
    """Open as far as the row alone can say: the feed says so, still serves the
    case, and nothing the notice itself has said has ended it yet. A paired lift
    or the cap on a standing notice can close it further; `Case.is_open` carries
    that, and every surface reads it.

    The feed's `status` is the weakest of the three signals. A case that dropped
    out of the feed while Open never gets the transition closed_at records, so
    vanished_at is its only close. And the feed closes a case a median 72h after
    the notice's own update reports the works complete (p90 111h, measured
    2026-09-05 on 3,783 closed cases), so 216 of that day's 562 Open cases were
    past a completion their own text had announced. The extracted end is what
    the accrual already stops charging at; reading `status` alone here put the
    "Open now" badge and the arithmetic in contradiction on the same case.

    Only an *observed* end closes a case here, the same line the published
    median draws: a scheduled end is a plan the works may have overrun, and the
    feed saying Open past one is the only evidence either way. A completion
    reported for a future instant (an update written ahead of the works) leaves
    the case open until then. See notes/statuspage-methodology.md ("The
    notice's own completion closes it").
    """
    if row["status"] != "Open" or row["vanished_at"]:
        return False
    if row["end_source"] == "lifted_immediate":
        return False
    if row["end_source"] in OBSERVED_END_SOURCES:
        end = observed_end_utc(row)
        return end is None or end > now
    return True


def observed_end_utc(row):
    """When the notice's own text reported the works complete, or None."""
    if row["end_source"] not in OBSERVED_END_SOURCES:
        return None
    return reported_end_utc(row["end_local_date"], row["end_local_time"])


def closed_on(row, now, start, closed_by=None):
    """The day a closed case closed: its own completion, else the lift or cap
    that closed it (`closed_by`), else closed_at. A completion before `start`
    is not used: the history reads a close before the start as a withdrawal.
    See notes/statuspage-methodology.md, 2026-09-24."""
    end = observed_end_utc(row)
    if end is not None and start <= end <= now:
        return row["end_local_date"]
    if closed_by is not None:
        return closed_by.strftime("%Y-%m-%d")
    return row["closed_at"][:10] if row["closed_at"] else None


def classify(row, recurring=False):
    """Severity class for a case row, or None if it isn't an event.

    `recurring` says the *event* announced a window repeating over a date range —
    "nightly from 10pm until 7am, from 9 to 27 July". A scheduled, repeating,
    announced overnight window is demand management rather than a failure, and it
    is treated as a restriction whatever the title on it says.

    That rule exists because the title alone was deciding it, and Uisce uses two
    titles for one situation. The same Donegal supply zone — Lifford, Rossgier —
    was published as "Water Conservation" on 30 April, which accrued nothing, and
    as "Reservoir Interruption" on 23 June and 9 July, which accrued 949,824
    person-hours and became the largest single figure on the site. Same villages,
    same 10pm-7am window, near-identical wording. Whichever way that pair is
    resolved they have to be resolved alike; this takes the conservative side,
    consistent with restrictions never having counted here.

    It downgrades an outage and nothing else: a nightly leak-detection round is
    still maintenance, not a restriction.
    """
    cat = row["work_category"]
    if cat in IGNORE_CATS:
        return None
    if IGNORE_BOIL_NOTICES and cat == "boil_notice_issued":
        return None
    # Category only: the feed's do_not_drink / boil_water_notice flags were tested
    # here too, and measured 2026-08-18 to add nothing. boil_water_notice appears
    # on the two boil categories and nowhere else; do_not_drink adds only 9 cases
    # on unrelated categories (burst mains, mains repairs, a new connection) whose
    # descriptions say nothing about drinking water at all. Reading them promoted
    # ordinary outages to quality, where they accrued no downtime, and painted a
    # drinking-water marker no notice supported. See notes/data-quality.md.
    if cat in QUALITY_CATS:
        return "quality"
    if cat in DEGRADED_CATS or row["water_restrictions"] or row["reduced_pressure"]:
        return "degraded"
    if cat in HARD_CATS or (cat in REPAIR_CATS and row["work_type"] != "Planned"):
        return "degraded" if recurring else "outage"
    # planned works, and non-disruptive activity regardless of work_type
    return "maintenance"


def knocks_grade(row):
    """Whether a case raises the health marker. Category only — see classify for
    why the feed's two health flags are not read."""
    return row["work_category"] in KNOCK_CATS


def ended_by_publication(row):
    """True when the notice's own text says the event was already over when the
    notice went up: a lift with immediate effect, or an extracted end whose span
    build.py nulled because the end precedes publication (532 cases on the
    2026-07-20 snapshot — mostly notices published just after the works window
    they announce; see notes/data-quality.md). Whatever the feed's status claims,
    these must not accrue "ongoing" time: 12 outage-class open cases were doing
    exactly that, fabricating downtime toward the 14-day cap."""
    if row["end_source"] == "lifted_immediate":
        return True
    return row["end_source"] not in (None, "not_found") and row["end_local_date"] is not None


def norm_scheme(location):
    """'Ardfinnan Regional Public Water Supply' -> 'ardfinnan' etc."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in (location or "").lower())
    return " ".join(w for w in cleaned.split() if w not in SCHEME_NOISE)


def boil_notice_fate(row, lifts, now):
    """What a boil-notice case contributes to the metrics: the whole policy, in one place.

    Boil notices cannot end themselves. The notice text never states its own end
    (`end_source` is `not_found` for every one of them), because Uisce publishes the
    lift as a *separate* case. So the LLM extraction is structurally irrelevant here
    and no prompt version will change that — the only real end signal is a paired lift.

    Returns (outcome, fate), where `fate` is None or an (in_force, end) pair —
    the intervals the health marker stands over and the end the notice may charge
    to. They differ only for a lift paired past the cap; `()` means "same as the
    charged interval". One shape for every outcome, so a caller never has to ask
    which one it got.
      "paired"  — a matching lift was found; `in_force` carries the real end and
                  `end` is that end capped (see charged_end).
      "accrue"  — no lift, but the notice is younger than CAP_DAYS, so status='Open'
                  is still plausible; `end` runs to now.
      "exclude" — no lift and older than CAP_DAYS. The feed's status is known to go
                  stale (case 221165 has been 'Open' since 2025-11-13 and its own
                  description says it was lifted), so accruing these fabricates
                  downtime that never happened. `fate` is None; drop the case.

    See notes/boil-notices.md for the measurements behind this.
    """
    start = publication(row)
    # No ended_by_publication guard, unlike the do-not-consume pairing in
    # resolve_case, and the asymmetry is deliberate rather than missed: it can
    # only fire on a case carrying an extracted end, and this class never has
    # one — end_source was `not_found` for all 35 on file at 2026-08-18, and
    # structurally so, because the end is published as a different case rather
    # than in this notice's text. Adding the guard would mean a fourth outcome
    # to protect against zero cases. If a prompt version ever starts extracting
    # ends here, add it then.
    pairing = lift_pairing(row, lifts, start)
    if pairing is not None:
        return "paired", pairing
    if not is_open(row, now):
        return "closed_no_signal", None
    if now - start > timedelta(days=CAP_DAYS):
        return "exclude", None
    # clamped to start, as the paired branch above clamps an early lift. An
    # advance-dated notice — the feed publishes these, and the front end already
    # prints "from" rather than "since" for them — would otherwise accrue from a
    # future start back to now. The clipped county arithmetic never sees the
    # negative span, but the area history prints it as "-240h so far".
    return "accrue", ((), max(min(now, start + timedelta(days=CAP_DAYS)), start))


def lift_pairing(row, lifts, start):
    """(in-force intervals, charged end) for a notice a lift closes, else None.

    The only place the pairing key is built and the two clamps applied, because
    the two classes that pair are published alike and have already drifted apart
    once here: the cap reached one branch and not the other, and a lift beyond it
    charged its whole span. What still differs between them is what happens when
    nothing pairs, and that stays with each caller.
    """
    cat = row["work_category"]
    if cat not in LIFT_OF:
        return None
    lift = paired_lift(lifts, (row["county"], LIFT_OF[cat]), row["location"], start)
    if lift is None:
        return None
    end = paired_end(lift, start)
    return [(start, end)], charged_end(end, start)


def paired_end(lift, start):
    """When a paired lift says the notice actually stood until: never before the
    token second after `start` (a lift can be stamped before its issue), and not
    capped; `charged_end` caps what it charges. See statuspage-methodology.md."""
    return max(lift, start + timedelta(seconds=1))


def charged_end(end, start):
    """The furthest a notice may charge from `start`, whatever its end signal.

    CAP_DAYS is a ceiling on one notice's contribution, not a claim about how
    long it ran: an observed `completion_update` is capped, the open-and-accruing
    branch is capped. A paired lift is not stronger
    evidence than a completion update, so it gets no exemption either.

    Without this, pairing a notice *raised* what it accrued: an unpaired notice
    stops at the cap (a boil notice past it is dropped outright), so finding its
    lift — better evidence, and evidence that the thing ended — charged more
    rather than less. That inversion was the bug, not the length. The exposure is
    real and not only in the consumption class: on the 2026-08-18 snapshot Whiddy
    Island had been Open 1,460 days and Dursey Island 740, but so had the
    Carrignagower boil notice at 590 days and Poulnagunogue at 405.

    Capping costs nothing on the snapshot this was written against: one notice
    pairs, and it spans 0.00 days.
    """
    return min(end, start + timedelta(days=CAP_DAYS))


def collect_lifts(rows):
    """{(county, lift category): [(scheme, when)]} — the pairing index.

    Built in one place because three callers need it identically (build_site and
    both eval commands); three copies of this loop is how the key shape drifts.
    """
    lifts = defaultdict(list)
    for r in rows:
        when = publication(r)
        if r["work_category"] in IGNORE_CATS and when is not None:
            lifts[(r["county"], r["work_category"])].append((norm_scheme(r["location"]), when))
    return lifts


def paired_lift(lifts, key, location, start):
    """Earliest lift matching this notice's scheme, or None.

    Lift notices arrive as separate cases with fresh reference_nums, so the
    pairing key is (county, lift category) + normalised scheme name. The
    category half is what stops a boil notice pairing with a do-not-consume
    lift for the same scheme. Multi-pin publishing is not chronologically
    tidy, so a lift up to 2 days before the issue pin's start still counts.
    """
    scheme = norm_scheme(location)
    if not scheme:
        return None
    candidates = [
        dt for k, dt in lifts.get(key, []) if k == scheme and dt >= start - timedelta(days=2)
    ]
    return min(candidates) if candidates else None


def parse_dt(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def publication(row):
    """When the notice went up: start_date, or the first sighting where the feed
    typed a start that is not a date (case 241224, year 0206). None if neither."""
    if plausible_start(row["start_date"]):
        return parse_dt(row["start_date"])
    return parse_dt(row["first_seen"]) if row["first_seen"] else None


def measured_span(row):
    """notice_to_end_seconds, or None where it was measured from a start that is
    not a date: a release built before build.py refused those still carries it."""
    pinned = row["end_input_start_date"]
    if pinned and not plausible_start(pinned):
        return None
    return row["notice_to_end_seconds"]


def month_bounds(ym):
    year, month = (int(p) for p in ym.split("-"))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    return start, end


def month_list(start, end):
    """['2026-04', ...] covering every month from start to end inclusive."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = year + (month == 12), month % 12 + 1
    return months


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def overlaps(intervals, lo, hi):
    """Whether any of `intervals` covers part of [lo, hi)."""
    return any(max(start, lo) < min(end, hi) for start, end in intervals)


# Fitted on May-Sep 2026 and re-fitted yearly; see "Outage notices per 100 km of main".
COUNT_CUTS = (1.0, 2.0, 3.0, 4.0, 5.0)


def count_grade(per_100km):
    for letter, cut in zip("ABCDE", COUNT_CUTS):
        if per_100km < cut:
            return letter
    return "F"


class TownLookup:
    """Small Area -> named area, with each Small Area's centroid and population.

    Built by uisce-fetch-towns (see src/uisce/towns.py). A pin is placed in the
    area of its nearest Small Area centroid; an area's population is the sum of
    its Small Areas, so every settlement reproduces its published Census figure.
    """

    BIN = 0.05  # degrees: a few bins either way cover PLACE_KM

    def __init__(self, rows):
        self.name = {}  # code -> area name
        self.county = {}  # code -> county
        self.pop = defaultdict(int)  # code -> population
        self._bins = defaultdict(list)
        self._cache = {}
        for _guid, code, name, county, lat, lon, pop in rows:
            self.name.setdefault(code, name)
            self.county.setdefault(code, county)
            self.pop[code] += pop
            self._bins[self._bin(lat, lon)].append((lat, lon, code))

    @classmethod
    def from_csv(cls, path):
        with open(path, newline="") as f:
            return cls(
                (r["guid"], r["town_code"], r["town_name"], r["town_county"],
                 float(r["lat"]), float(r["lon"]), int(r["pop"]))
                for r in csv.DictReader(f)
            )

    def _bin(self, lat, lon):
        return math.floor(lat / self.BIN), math.floor(lon / self.BIN)

    def _nearest(self, lat, lon, km):
        """The code of the nearest centroid within `km`, or None."""
        kx = 111.0 * math.cos(math.radians(lat))
        (lo_i, lo_j), (hi_i, hi_j) = (
            self._bin(lat - km / 111.0, lon - km / kx),
            self._bin(lat + km / 111.0, lon + km / kx),
        )
        best = None
        for bi in range(lo_i, hi_i + 1):
            for bj in range(lo_j, hi_j + 1):
                for slat, slon, code in self._bins.get((bi, bj), ()):
                    dist = math.hypot((slat - lat) * 111.0, (slon - lon) * kx)
                    if dist <= km and (best is None or dist < best[0]):
                        best = (dist, code)
        return best and best[1]

    def place(self, lat, lon, county):
        """The area a pin is placed in: its nearest Small Area's, or UNPLACED when
        that lies in another county than the notice names, or none is in range.

        Not re-homed to the best area that *is* in the county: a pin nearest a
        Wicklow Small Area on a Kildare notice is where the feed's own two fields
        disagree, and naming a Kildare town for it would hide that.
        """
        key = (round(lat, 5), round(lon, 5))
        if key not in self._cache:
            # a near search first: a Dublin box of PLACE_KM holds thousands of centroids
            self._cache[key] = self._nearest(lat, lon, 1.0) or self._nearest(lat, lon, PLACE_KM)
        code = self._cache[key]
        return code if code is not None and self.county[code] == county else UNPLACED

    def label(self, code):
        return UNPLACED_LABEL if code == UNPLACED else self.name[code]


def event_area(pins):
    """The one area an event is named after, from `pins` [(publication, id, code)]:
    the area most of its pins were placed in, the earliest pin breaking a tie, and
    UNPLACED only when every pin is."""
    placed = [pin for pin in pins if pin[2] != UNPLACED]
    if not placed:
        return UNPLACED
    n = Counter(code for _, _, code in placed)
    return min(placed, key=lambda pin: (-n[pin[2]], pin[0], pin[1]))[2]


def span_stats(observed_h, scheduled_h, no_end_n=0):
    """Published notice-to-end figures. `median_completion_h` is the headline and
    covers observed completions only; the scheduled figures are reported
    alongside so the split is visible rather than silently pooled, and
    `no_end_n` counts the events that never reported an end at all.
    """
    return {
        "median_completion_h": round(statistics.median(observed_h), 1) if observed_h else None,
        "completed_n": len(observed_h),
        "median_scheduled_h": round(statistics.median(scheduled_h), 1) if scheduled_h else None,
        "scheduled_n": len(scheduled_h),
        "no_end_n": no_end_n,
    }


def daily_windows(first_date, open_t, close_t, lo, hi):
    """Every window of a daily local-time series, as UTC pairs clipped to [lo, hi).

    Windows are wall clock: 22:00-07:00 is nine hours of Irish night whatever the
    UTC offset is that week, so each date is combined with Europe/Dublin and
    converted individually rather than offsetting the series once. That also makes
    the clocks-change nights come out right on their own — eight hours in spring,
    ten in autumn.

    Whether the window crosses midnight comes from the times (close < open), never
    from the notice's own wording: the feed writes "daily from 10pm until 7am".

    `hi` carries the end of the series, so nothing here re-derives the last date.
    resolve_case passes the capped end it would otherwise have used, and that
    instant *is* the last window's close by construction — build.py derives
    notice_to_end_seconds from local_date + local_time in the same timezone. The
    14-day cap and a completion update both truncate the series through that one
    clip rather than through a second code path.

    Returns [] for a degenerate or incoherent series; the caller keeps its single
    interval, because an empty expansion never means "no disruption".
    """
    if close_t == open_t:
        return []
    # the window may already be open at `lo` (a notice published mid-series), so
    # start a day early and let the clip truncate it rather than dropping it
    day = max(first_date, (lo - timedelta(days=1)).astimezone(DUBLIN).date())
    overnight = timedelta(days=1 if close_t < open_t else 0)

    windows = []
    while True:
        opens = datetime.combine(day, open_t, DUBLIN).astimezone(timezone.utc)
        if opens >= hi:
            return windows
        closes = datetime.combine(day + overnight, close_t, DUBLIN).astimezone(timezone.utc)
        opens, closes = max(opens, lo), min(closes, hi)
        if closes > opens:
            windows.append((opens, closes))
        day += timedelta(days=1)


def _parse_time(value):
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def case_ref(row):
    """The key that groups a multi-pin publication into one event."""
    # the feed pads some references with a space or \xa0; unstripped, 15 events split in two
    return (row["reference_num"] or "").strip() or f"id:{row['id']}"


def notice_url(ref):
    """water.ie's page for a notice, or None: the HM-style codes, the `id:`
    fallbacks and a reference with a stray space are not pages there."""
    ref = (ref or "").strip()
    return f"https://wtr.ie/{ref}" if re.fullmatch(r"[A-Z]{3}\d{8}", ref) else None


def recurring_events(rows, windows):
    """Event keys whose notices describe a window repeating over a date range.

    Two signals, because neither alone is enough and they fail in opposite
    directions. The extraction misses a window whenever the notice also carries a
    completion update — it is told a completion takes priority over a scheduled
    end and applies that to the window fields too — which is 33 events, including
    every one of the eight a human review found charged as a continuous outage.
    The text misses the enumerated form, "from 10am until 6pm on 5 May, 6 May and
    7 May", which names its days instead of saying "daily", and which the model
    reads correctly.

    Detection is all the severity rule needs, and detection is the easy half: the
    window *values* are what needed a language model. So classification no longer
    waits on a corpus re-run to be right.

    Known residual: one notice reading "until 6pm on 9 May until 9pm 13 May" — two
    "until"s and no "from", garbled at source — is read as a repeating 18:00-21:00
    window by the model and is not recurring. Reviewed and recorded rather than
    parsed around; see data/eval/recurrence_review_2026-08-02.csv.
    """
    keys = set(windows)
    for row in rows:
        if describes_recurrence(row["description"]):
            keys.add((row["county"], case_ref(row)))
    return keys


def _read_window(window):
    """(open, close, first_date) as objects, or (None, why it cannot be honoured).

    One reading for both callers. A window `event_windows` elects has to be one
    `recurring_intervals` could honour, or the vote hands a sibling a window that
    is refused the moment it is read - and two separate lists of checks would
    drift apart the first time one of them grew a case.
    """
    open_t, close_t, first_date = (
        _parse_time(window[0]), _parse_time(window[1]), _parse_date(window[2])
    )
    if open_t is None or close_t is None or first_date is None:
        return None, "window fields missing or unparseable"
    if open_t == close_t:
        # a window covering the whole day is a continuous event; say so rather
        # than inventing touching intervals that merge would rejoin anyway
        return None, "window covers the whole day"
    return (open_t, close_t, first_date), None


def event_windows(rows):
    """{(county, ref): (open, close, first_date) or None} per event a pin claimed.

    A repeating window is a property of the *works*, not of the notice that
    happens to describe them. Uisce publishes one event as many pins over several
    days, and the pin carrying the completion update reports no window at all —
    reasonably, since a finished job has no forward schedule left to state. But
    coverage is unioned per reference_num, so that one pin's continuous interval
    re-covers every gap its siblings carved out: on the first v3 run
    DON00115765 had 17 of 18 pins expanded and still kept 354h of its 385h.

    So a pin with no window of its own borrows one its siblings reported. It is
    still clipped to that pin's own start and end, which is what makes this safe
    rather than a guess — the completion pin inherits the schedule and then stops
    at the moment it says the works stopped.

    Where pins disagree the commonest window wins, ties broken by sorting so a
    rebuild is reproducible. Only a window `_read_window` can honour stands for
    election: one that is refused wherever it is read must not win the vote and
    deny a sibling the window another pin did report. The value is then None, but
    the *key* is kept either way, because the key set is also the recurrence
    signal recurring_events seeds from and a window the extraction half-reported
    is still a window the notice described.
    """
    claims = defaultdict(list)
    for r in rows:
        if r["end_recurrence"] == RECURRING:
            claims[(r["county"], case_ref(r))].append(
                (r["end_window_open"], r["end_window_close"], r["end_window_first_date"])
            )
    windows = {}
    for key, claimed in claims.items():
        usable = [w for w in claimed if _read_window(w)[0] is not None]
        windows[key] = max(sorted(set(usable)), key=usable.count) if usable else None
    return windows


def recurring_intervals(row, start, end, shared=None):
    """(windows, tag) for a notice claiming a window that repeats over a date range.

    `windows` is None whenever the claim is not honoured, so a refusal is a pure
    numeric no-op — the caller keeps the single [start, end] interval it would
    have used anyway. That is what lets the checks below be as suspicious as they
    are: the cost of disbelieving the model is zero, and the cost of believing a
    hallucinated recurrence is an outage's hours quietly falling by half.

    The sharpest check is the cross-check on a scheduled end. The prompt requires
    the reported end to be the last date *at the window's closing time*, so a
    notice whose window_close disagrees with its own local_time has contradicted
    itself, and the field that survives is the one the eval round validates.
    A completion update has no such check available — its local_time is the
    completion, not a window close — so those are honoured but reported
    individually on every build.
    """
    claimed = row["end_recurrence"] == RECURRING
    if claimed:
        window = (row["end_window_open"], row["end_window_close"], row["end_window_first_date"])
    elif shared is not None:
        # borrowed from a sibling pin of the same event — see event_windows
        window = shared
    else:
        return None, "none"

    read, unreadable = _read_window(window)
    if unreadable:
        return None, f"refused: {unreadable}"
    open_t, close_t, first_date = read

    # An inherited window faces the same cross-check as a claimed one: if a
    # sibling's closing time disagrees with this pin's own scheduled end, the two
    # notices are describing different things and the borrowed window is refused.
    observed = row["end_source"] in OBSERVED_END_SOURCES
    if not observed and _parse_time(row["end_local_time"]) != close_t:
        return None, (
            f"refused: close time {window[1]} != reported end time {row['end_local_time']}"
        )

    windows = daily_windows(first_date, open_t, close_t, start, end)
    if len(windows) < 2:
        # nearly every notice contains something like "from 9am until 5pm", so a
        # one-window recurrence is the cheapest false positive to make and the
        # least valuable to honour — it is just an interval
        return None, "refused: single window in span"
    if not claimed:
        # every tag starts with "expanded" so the mixed-event check counts an
        # inherited pin as expanded, which it is
        return windows, "expanded_inherited"
    return windows, "expanded_observed" if observed else "expanded"


class Case(NamedTuple):
    """A case row with its severity class and disruption intervals resolved.

    Splitting this out of the accumulation loop is what lets a county and a town
    share one set of arithmetic: the intervals a case contributes are a property
    of the case alone, not of the geography it is being counted under.

    `intervals` is a list because a notice can describe a *recurring* window —
    "daily from 10pm until 7am, from 9 July to 27 July" is eighteen nights of nine
    hours, not sixteen days of continuous outage. Every other case carries exactly
    one interval and behaves as it always has. They are sorted and non-overlapping
    on arrival; nothing downstream re-sorts them.
    """

    row: object
    sev: str
    ref: str
    # publication: the start the span was measured from where build.py pinned
    # one, else start_date. The intervals open here.
    start: datetime
    intervals: list
    has_end: bool
    observed_end: bool
    rec: str = "none"  # recurrence outcome, for the build report
    # When the notice actually stood, as opposed to what it charges. They differ
    # only for a lift paired past CAP_DAYS: the charge is capped, but the lift is
    # evidence the notice was in force to the end of it, and the health marker
    # answers to the evidence rather than to the accrual ceiling. Empty means
    # "same as intervals", which is every other case.
    in_force: tuple = ()
    # Closed, or over by its own text, with no usable end: the interval is a
    # one-second token on its publication, counted in `no_end_n` and kept out of
    # every duration.
    no_end: bool = False
    # is_open(row, now), less what only resolve_case knows (a paired lift, the
    # cap on a standing notice); decided once here so the open list, the
    # history's "still open", the county page's notice text and the Atom feed
    # cannot disagree about a case. Read this, not is_open().
    is_open: bool = False
    # closed_on(...): the day every "closed" surface prints; None while open
    closed: str | None = None
    # open and not yet started at the build: every surface says "from", not "since"
    ahead: bool = False
    # its own span ran past CAP_DAYS and was cut there
    capped: bool = False
    # the end an open notice states and has not reported reached, in Irish wall
    # clock: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"; None for a repeating window
    back: str | None = None

    @property
    def county(self):
        return self.row["county"]

    @property
    def marker_intervals(self):
        """The intervals the health marker stands over — see `in_force`."""
        return self.in_force or self.intervals


def resolve_case(r, lifts, now, shared_window=None, recurring=None):
    """A Case for one row, or None if it isn't an event at all.

    `shared_window` is the recurring window this row's *event* reported, used
    when this particular notice reported none of its own — see event_windows.
    `recurring` is whether the event announces a repeating window by either
    signal (see recurring_events); it decides severity, while shared_window
    decides the intervals. Left None, it falls back to this row's own fields plus
    shared_window, which is enough for a single-notice caller but is *not* the
    event-level signal: an event whose every claimed window is unreadable has no
    window to share, so a pin of it that claimed nothing would classify on its
    own title. Pass `key in recurring_events(...)`, as every corpus caller does.

    The interval rules and their rationale are in
    notes/statuspage-methodology.md; this is the code they describe.
    """
    # Recurrence is a property of the event, not the notice: the pin carrying the
    # completion update reports no window, and classifying it on its own field
    # would leave one outage pin inside a restriction event, whose interval the
    # per-reference union would then charge in full.
    if recurring is None:
        recurring = (shared_window is not None or r["end_recurrence"] == RECURRING
                     or describes_recurrence(r["description"]))
    sev = classify(r, recurring)
    start = publication(r)
    if sev is None or start is None or r["county"] not in COUNTY_POP:
        return None
    cap = timedelta(days=CAP_DAYS)

    notice_to_end = measured_span(r)
    has_end = notice_to_end is not None
    # a paired boil-notice lift is an observed end too; set below
    observed_end = has_end and r["end_source"] in OBSERVED_END_SOURCES
    rec = "none"
    no_end = False
    in_force = ()  # empty: the charged intervals are the in-force ones
    back = None
    capped = False
    open_now = is_open(r, now)
    closed_by = None  # when a lift or the cap closed it, for closed_on
    # a standing notice no lift has closed closes at the cap, where its marker
    # stops, whichever branch below it takes (owner decision, 2026-09-24)
    if r["work_category"] in LIFT_OF and now - start > cap:
        if open_now:
            closed_by = start + cap
        open_now = False

    if r["work_category"] == "boil_notice_issued":
        # This class never ends itself; boil_notice_fate owns the whole decision.
        outcome, fate = boil_notice_fate(r, lifts, now)
        if outcome == "exclude":
            return None
        # a lift is a real, observed event, not a schedule
        has_end = outcome == "paired"
        observed_end = has_end
        open_now = open_now and not has_end
        if fate is None:
            # closed with no lift: token footprint, as for any no-signal case
            end = start + timedelta(seconds=1)
        else:
            in_force, end = fate
            if has_end:
                closed_by = in_force[-1][1]
    elif not has_end:
        # A do-not-consume notice cannot state its own end either — the lift is a
        # separate case, exactly as for a boil notice — so pairing one is strictly
        # more information than running to the cap.
        #
        # The staleness *exclusion* boil notices take is deliberately NOT applied
        # here. The case that justified it (221165) sat 'Open' while its own text
        # said the notice "is now lifted with immediate effect" — the text
        # contradicted the status. No do-not-consume notice on file does that:
        # Whiddy Island and Dursey Island both read as genuine, unlifted notices
        # naming a specific water-quality failure. Dropping them would remove a
        # live drinking-water warning on an assumption rather than on evidence.
        # See notes/statuspage-methodology.md.
        #
        # `already_over` gates the pairing and the accrual below it alike, which
        # is why it is read once here rather than inside the second branch only.
        # A notice whose own text reported an end before it was even published
        # did not then run on until some later lift, so pairing it to one would
        # fabricate precisely the downtime ended_by_publication exists to refuse.
        # The lift is still a real lift; it just ends a notice already over.
        already_over = ended_by_publication(r)
        pairing = None if already_over else lift_pairing(r, lifts, start)
        if pairing is not None:
            # a lift is a real, observed end, not a schedule
            in_force, end = pairing
            has_end = observed_end = True
            open_now = False
            closed_by = in_force[-1][1]
        elif open_now and start < now and not already_over:
            # ongoing with no inferred end: runs from start until now, capped
            end = min(now, start + cap)
        else:
            # Closed with no usable end signal, or already over per the notice's
            # own text: a token that keeps its publication day on the bars. The
            # typical span charged here until 2026-10-06 was a person-hours
            # instrument (notes/statuspage-methodology.md).
            no_end = True
            end = start + timedelta(seconds=1)
    else:
        # The span was measured from the start build.py pinned at first inference;
        # start_date may have been re-stamped since, and adding the span to the
        # new one charges hours past the notice's own end (21 cases, 2026-09-24).
        # The pinned start is the publication for everything that reads one.
        if r["end_input_start_date"]:
            start = parse_dt(r["end_input_start_date"])
        capped = timedelta(seconds=notice_to_end) > cap
        end = start + min(timedelta(seconds=notice_to_end), cap)
        # Recurrence lives strictly under has_end, which keeps it away from the
        # branches above: a boil notice's end is a paired lift and never its own
        # text, and the no-signal branches own the 532 cases whose span build.py
        # nulled because the notice was published after its own works window.
        windows, rec = recurring_intervals(r, start, end, shared_window)
        if windows:
            return Case(
                row=r, sev=sev, ref=case_ref(r), start=start, intervals=windows,
                has_end=has_end, observed_end=observed_end, rec=rec,
                is_open=open_now, closed=None if open_now else closed_on(r, now, start),
                ahead=open_now and windows[0][0] > now, capped=capped,
            )
        if open_now and not observed_end and r["end_local_date"]:
            back = r["end_local_date"] + (f"T{r['end_local_time']}" if r["end_local_time"] else "")

    return Case(
        row=r,
        sev=sev,
        ref=case_ref(r),
        start=start,
        intervals=[(start, end)],
        has_end=has_end,
        observed_end=observed_end,
        rec=rec,
        no_end=no_end,
        in_force=tuple(in_force),
        is_open=open_now,
        closed=None if open_now else closed_on(r, now, start, closed_by),
        ahead=open_now and start > now,
        back=back,
        capped=capped,
    )


class Region:
    """Interval accounting for one grouping of cases: a county, or an area in one,
    which holds the pins placed there."""

    def __init__(self):
        self.sev_iv = defaultdict(list)
        self.iv = defaultdict(lambda: defaultdict(list))
        # both are OR'd across an event's pins, which is what the monthly median
        # wants (does this event carry *an* end signal at all?) but not what a
        # per-event badge wants: DON00115765 has 18 pins of which 1 reported a
        # completion, and the OR would call the whole thing observed. The top ten
        # prints a pin count instead; see event_meta in build_site.
        self.has_end = defaultdict(lambda: defaultdict(bool))
        self.observed_end = defaultdict(lambda: defaultdict(bool))
        # OR'd the same way, and read only for the published `no_end_n`
        self.no_end = defaultdict(lambda: defaultdict(bool))
        # ref -> the intervals its knocking pins were *in force* over, which is
        # the charged interval for all but a lift paired past the cap. Kept apart
        # from `iv` so the marker is not silently bounded by the cap, which says
        # how far a notice may run, not how long a warning stood.
        self.knock_iv = defaultdict(list)
        self.open_now = {}  # ref -> case (dedups multi-pin events)
        self.unstated = set()  # refs with an open pin that states no end
        self.resolved = {}  # ref -> case, for cases observed to close

    def add(self, case):
        sev, ref = case.sev, case.ref
        self.sev_iv[sev].extend(case.intervals)
        self.iv[sev][ref].extend(case.intervals)
        self.has_end[sev][ref] |= case.has_end
        self.observed_end[sev][ref] |= case.observed_end
        self.no_end[sev][ref] |= case.no_end
        if knocks_grade(case.row):
            self.knock_iv[ref].extend(case.marker_intervals)
        r = case.row
        if case.is_open:
            entry = self.open_now.setdefault(
                ref,
                {
                    "ref": ref,
                    "sev": sev,
                    "title": r["title"],
                    "loc": r["location"] or "",
                    "since": case.start.strftime("%Y-%m-%d"),
                } | ({"ahead": 1} if case.ahead else {}),
            )
            if not case.ahead:
                entry.pop("ahead", None)
            # the latest end its open pins state, and none if any open pin states none
            if not case.back or ref in self.unstated:
                self.unstated.add(ref)
                entry.pop("back", None)
            elif back_key(case.back) > back_key(entry.get("back", "")):
                entry["back"] = case.back
        elif case.closed:
            held = self.resolved.get(ref)
            # the earliest close across the event's pins, as event_meta takes it
            if held is None or case.closed < held["closed"]:
                self.resolved[ref] = {
                    "sev": sev,
                    "title": r["title"],
                    "loc": r["location"] or "",
                    "since": case.start.strftime("%Y-%m-%d"),
                    "closed": case.closed,
                }

    def merged(self):
        return {sev: merge(self.sev_iv[sev]) for sev in SEV_ORDER}

    def events(self):
        return {
            sev: {ref: merge(iv) for ref, iv in self.iv[sev].items()} for sev in SEV_ORDER
        }

    def knock_events(self):
        return {ref: merge(iv) for ref, iv in self.knock_iv.items()}


def seen_span(lo, hi, seen):
    """The part of [lo, hi) the site has seen: not before collection began, and
    not after the feed was last read."""
    return max(lo, COLLECTION_START), min(hi, seen)


def seen_whole(lo, hi, seen):
    return seen_span(lo, hi, seen) == (lo, hi)


def count_notices(first_pubs, lo, hi, seen):
    eff_lo, eff_hi = seen_span(lo, hi, seen)
    return sum(1 for pub in first_pubs if eff_lo <= pub < eff_hi)


def count_figures(notices, km, *, whole, graded=True):
    """The count, its rate per 100 km of main and the letter on the published
    figure; a span the site saw only in part carries its count so far alone."""
    per_100km = round(100.0 * notices / km, 2) if whole else None
    figures = {"outage_notices": notices, "per_100km": per_100km}
    if graded:
        figures["count_grade"] = count_grade(per_100km) if whole else None
    return figures


def back_key(back):
    """A stated end as a sortable wall-clock string; a date alone means the end of that day."""
    return back if "T" in back or not back else back + "T24:00"


def region_month(region, ym, now):
    """Counts for one region in one month: events active in it by class, and the
    health notices in force. Shared by counties and areas; the day bars, the
    outage count and the completion median are county only - see build_site.
    """
    lo, hi = month_bounds(ym)
    # nothing is active beyond "now" (future scheduled works have not started)
    # nor before collection began
    eff_hi, eff_lo = min(hi, now), max(lo, COLLECTION_START)
    events = region.events()
    counts = {
        sev: sum(1 for iv in events[sev].values() if overlaps(iv, eff_lo, eff_hi))
        for sev in SEV_ORDER
    }

    # Health-relevant quality notices — boil water, do not drink, do not consume
    # — published beside the grade rather than inside it. Counted over the months
    # each notice was *in force*, not the months it charged: a lift paired past
    # CAP_DAYS caps what its notice charges, and reading the marker off that
    # interval dropped the warning from months the lift itself proves the notice
    # was standing. See Region.knock_iv.
    knock = region.knock_events()
    health_n = sum(1 for iv in knock.values() if overlaps(iv, eff_lo, eff_hi))
    # How many of those are standing *right now*. A right-now snapshot on a
    # per-month figure, like `open_now` on the county: the same value on every
    # month, and only the month the snapshot belongs to may read it. It exists
    # because health_n alone cannot separate "a notice is in force" from "a
    # notice was in force at some point this month" — and the front end was
    # saying "the water may not be safe to drink" for the second.
    # inclusive of `e`: an ongoing notice accrues to exactly `now` (see
    # resolve_case), so a half-open test reports the live ones as not standing
    health_now = sum(1 for iv in knock.values() if any(s <= now <= e for s, e in iv))
    return {"events": counts, "health_n": health_n, "health_now": health_now}


RESOLVED_SHOWN = 20


def resolved_by_month(region, shown=None):
    """{ym: {"n": count, "cases": [...]}} of events that closed that month.

    Keyed on `closed_on`, so coverage is partial by construction: a case with no
    reported completion needs `closed_at`, which is NULL for every case that
    closed before schema v2 and for one opened and closed inside one build gap.
    The site says so rather than presenting these as a complete record.

    `shown` caps the listed cases (newest first) while `n` stays the true count —
    the full lists are a third of the page payload and a reader wants the recent
    handful, not 200 titles.
    """
    by_month = defaultdict(list)
    for ref, event in region.resolved.items():
        # an event with a pin still open is open, whatever its siblings say; a
        # close before collection began (a standing notice capped years ago) is
        # in no month the site shows
        if ref not in region.open_now and event["closed"] >= f"{COLLECTION_START:%Y-%m-%d}":
            by_month[event["closed"][:7]].append(event)
    out = {}
    for ym, events in by_month.items():
        events.sort(key=lambda e: e["closed"], reverse=True)
        out[ym] = {"n": len(events), "cases": events[:shown] if shown else events}
    return out


TOP_EVENTS_SHOWN = 10


def top_events(longest, event_meta, towns, area_of, shown=TOP_EVENTS_SHOWN):
    """The longest supply disruptions nationally among one month's outage notices.

    `longest` is [(hours, county, ref)], the events the month's published median
    is taken over: outage notices first published in the month whose end was
    observed, at the covered hours that median reads. So the ten are the tail of
    the distribution the headline summarises, and no figure here is one the
    median does not already rest on. Why this ranking and not another is in
    notes/statuspage-methodology.md ("The national top ten").

    Keyed by (county, ref), not ref: 15 reference numbers span two counties and
    each half is its own notice in its own county's count.
    """
    ranked = sorted(
        longest, key=lambda e: (-e[0], event_meta[e[1:]]["first_pub"], e[1:])
    )[:shown]
    rows = []
    for hours, county, ref in ranked:
        meta = event_meta[(county, ref)]
        row = {
            "ref": ref,
            "county": county,
            "title": meta["title"],
            "hours": round(hours, 1),
            "start": meta["start"],
            "pins": meta["pins"],
            "confirmed": meta["confirmed"],
            "scheduled": meta["scheduled"],
        }
        # a pin's reported span ran past the cap; the page says "14 days+"
        if meta["capped"]:
            row["capped"] = 1
        if towns is not None and (county, ref) in area_of:
            # the same name the county's open list uses: one event, one area
            row["area"] = towns.label(area_of[(county, ref)])
        rows.append(row)
    return rows


def town_months(region, months, now):
    """Per-month counts for one area, only for the months it has activity in.

    Every field that is zero, absent or implied is left out, and the reader fills
    the gaps. These are the bulk of the page — a few thousand area-months against
    26 counties — and most of them are one disruption and three zeroes, so
    spelling out the zeroes cost a quarter of the whole payload.
    """
    resolved = resolved_by_month(region)
    out = {}
    for ym in months:
        counts = {sev: n for sev, n in region_month(region, ym, now)["events"].items() if n}
        if not counts:
            continue
        month = {"events": counts}
        if resolved.get(ym):
            month["resolved_n"] = resolved[ym]["n"]
        out[ym] = month
    return out


def county_town_data(regions, towns, county, months, now):
    """The drill-down for one county: every named area with a case that month.

    No letter grade: a letter needs a length of main, which Uisce Éireann
    publishes by supply zone, not by town.
    """
    if towns is None:
        return {}
    out = {}
    for code, region in regions.items():
        by_month = town_months(region, months, now)
        if not by_month:
            continue
        # no open-case list here: each one is already in the county's, tagged with
        # its area, and holding both copies cost 80 KB to say the same thing twice
        area = {"name": towns.label(code), "months": by_month}
        # Present exactly when the area has a page, so it is the flag as well as
        # the value. ui.js's slug() is deliberately not this one - it would send
        # 17 of these places to a URL that does not exist - so the app is told
        # rather than left to work it out.
        if area_has_page(code):
            area["slug"] = statusui.slug(area["name"])
        if code != UNPLACED:
            area["pop"] = towns.pop[code]
        else:
            area["unplaced"] = True
        out[code] = area
    return out


def event_record(ref, meta, intervals, now):
    """One published event as the per-area history renders it.

    Every field that is zero, absent or implied is left out, the same discipline
    town_months applies and for the same reason — this is the bulk of what the
    history ships, and most events are one disruption and six defaults.

    Three of the omissions are not thrift but honesty:

    `hours` is dropped entirely for an event that is closed and never reported an
    end. Those carry resolve_case's token one-second footprint, so publishing the
    number would print "0.0h" for 801 events as a measurement. The page says no
    end was ever reported instead.

    `hours` is what has elapsed by `now` on the pins that measured something,
    never a token nor time still ahead. An open event with nothing
    elapsed yet carries `ahead` instead, which the pages read as "not started".

    `span_h` appears only when a recurring window makes it differ from `hours`.
    Covered time is what the works took; elapsed time is what the notice spanned,
    and 18 nights of nine hours is not 16 days of outage. Publishing only the
    span would restate the bug notes/statuspage-methodology.md records.

    `from` and `end` are the first and last charged days, present when they
    differ from `start`, so a day in the county's bar finds every event that
    coloured it, hours or none.
    """
    iv = merge(intervals)
    record = {
        "ref": ref,
        "title": meta["title"],
        "sev": meta["sev"],
        # earliest publication across the event's pins, not the first pin's own
        # date: rows arrive in id order, not start_date order
        "start": meta["first_pub"].strftime("%Y-%m-%d"),
        "pins": meta["pins"],
    }
    counted = [(s, min(e, now)) for s, e in merge(meta["measured"]) if s < now]
    if meta["open"] and not any(s < now for s, _ in iv):
        record["ahead"] = 1
    if counted and (meta["open"] or meta["confirmed"] or meta["scheduled"]):
        hours = sum((e - s).total_seconds() for s, e in counted) / 3600
        record["hours"] = round(hours, 1)
        span = (counted[-1][1] - counted[0][0]).total_seconds() / 3600
        if span - hours > 0.1:
            record["span_h"] = round(span, 1)
    if iv:
        # a repeating window can first open after the notice went up
        first = iv[0][0].strftime("%Y-%m-%d")
        if first != record["start"]:
            record["from"] = first
        end = (iv[-1][1] - timedelta(seconds=1)).strftime("%Y-%m-%d")
        if end != record["start"]:
            record["end"] = end
    for field in ("confirmed", "scheduled"):
        if meta[field]:
            record[field] = meta[field]
    if meta["open"]:
        record["open"] = 1
    if meta["closed"] and not meta["open"]:
        record["closed"] = meta["closed"]
    if meta["loc"]:
        # the vernacular name the settlement it was homed to does not carry:
        # "Sefton Green" inside Dún Laoghaire. Too fragmented to group on (see
        # notes/statuspage-methodology.md), exactly right to print.
        record["loc"] = meta["loc"]
    if meta["health"]:
        record["health"] = 1
    return record


def area_history(event_meta, event_iv, event_codes, towns, now):
    """{county: {code: {"name": ..., "events": [...]}}}, newest event first.

    A regrouping of what build_site already holds rather than new geography.

    An event is listed under **every** area its pins were homed to, not only the
    one area_of names it after. The two answer different questions and the county
    breakdown already takes this position: it homes each pin individually, so a
    burst published as pins in Naas and in Sallins puts a count on both rows.
    Listing it only under the area it is named after left
    220 of the county tables' 1,830 areas with no history at all, and their pages
    said "no notice has ever been published here" directly underneath the row
    that had just counted one. 764 events are multi-area; the duplication costs
    6 KB gzipped across every shard and is what makes the two pages agree.

    So this is deliberately not a partition. `areas` on the record says how many
    histories an event appears in, because a reader who meets the same burst
    twice would otherwise reasonably conclude the site is double-counting.

    area_of is untouched and still names an event once, for the county's open
    list and the national top ten — what changed is where an event is *listed*,
    not what it is called.

    Keyed (county, ref) throughout, so the 16 reference numbers published in two
    counties appear in both, each its own notice in its own county's count.
    That is the same "two rows is the honest rendering" decision top_events
    documents, not a duplicate.

    `name` is carried per area even though the county payload already has one,
    because it does not always: an area whose every event is still in the future
    has no month rows, so county_town_data drops it and the page would have no
    name to print.
    """
    out = defaultdict(dict)
    for key, codes in event_codes.items():
        county, ref = key
        # built once and shared by reference across the areas it is listed in:
        # event_record merges intervals, and the record is
        # the same event whichever page it appears on
        record = event_record(ref, event_meta[key], event_iv[key], now)
        if len(codes) > 1:
            record["areas"] = len(codes)
        for code in codes:
            # name, pop and slug ride here because the area view has nothing
            # else to read them from: the county breakdown is its own shard
            area = out[county].setdefault(code, {
                "name": towns.label(code), "pop": towns.pop[code] or None, "events": [],
            })
            if area_has_page(code):
                area["slug"] = statusui.slug(area["name"])
            area["events"].append(record)
    for areas in out.values():
        for area in areas.values():
            # newest first, ref breaking ties so a rebuild is reproducible —
            # the rule event_windows uses for the same reason
            area["events"].sort(key=lambda e: (e["start"], e["ref"]), reverse=True)
    return dict(out)


def area_index(history, towns):
    """[(county, [(code, name, pop, n_notices), ...]), ...] for the directory page.

    Counties A-Z, areas A-Z within them. Reads the finished history, so the
    notice count is len(events) — true by construction rather than re-derived,
    and free, since the shards already exist by the time this runs.

    Deliberately not summed from the county payload's month rows: an event
    spanning a month boundary is counted in both months there, so adding them up
    would overstate every area that has ever had one.
    """
    out = []
    for county in sorted(history):
        areas = [
            (code, area["name"], towns.pop[code] if code != UNPLACED else None,
             len(area["events"]))
            for code, area in history[county].items()
        ]
        # by name, code breaking ties so a rebuild is reproducible
        out.append((county, sorted(areas, key=lambda a: (a[1], a[0]))))
    return out


def _area_items(county, areas, prefix=""):
    """The <li> rows for one county's areas, shared by the directory and c/*.html.

    `prefix` is prepended to the link target because the county pages sit one
    directory down; everything else about a row is identical on both pages, and
    the two drifting apart is exactly the bug a reader would report as "the
    directory says three notices and the county page says four".
    """
    items = []
    for code, name, pop, n in areas:
        # the page when the area has one, the hash route when it does not:
        # an ED is only ever reachable inside the app
        href = (
            f"{prefix}{area_path(county, name)}"
            if area_has_page(code)
            else f"{prefix}index.html#area/{quote(county, safe='')}/{quote(code, safe='')}"
        )
        # The units ride on every row rather than in a column heading: the
        # heading scrolls away after the first county, and two bare
        # right-aligned integers are read in the wrong order by most people
        # (the bigger one looks like the count). ~15 KB for a page that
        # explains itself wherever you land in it, and in search results.
        items.append(
            f'<li{" class=\"unplaced\"" if pop is None else ""}>'
            f'<a href="{href}">{html.escape(name)}</a>'
            f'<span class="fill"></span>'
            f'<span class="n">{n} notice{"" if n == 1 else "s"}</span>'
            f'<span class="p">{"" if pop is None else f"{pop:,} people"}</span></li>'
        )
    return "".join(items)


def _area_index_html(index):
    """The directory's body: a jump nav and one section per county."""
    nav = " · ".join(
        f'<a href="#c-{county_slug(c)}">{html.escape(c)}</a>' for c, _ in index
    )
    sections = []
    for county, areas in index:
        # The crawlable link into c/*.html. A sitemap alone is a weak discovery
        # signal — an internal link from an already-indexed page is the strong
        # one, and this page is where a county's name is already the heading.
        # data-county carries the bare name for the search: the heading itself
        # now also holds the count and the county-page link, and matching on all
        # of that would make "page" select every county in the country
        sections.append(
            f'<section id="c-{county_slug(county)}" data-county="{html.escape(county)}" '
            f'style="--n:{len(areas)};--r:{(len(areas) + 1) // 2}">'
            f'<h2>Co. {html.escape(county)} <span>· {len(areas)} areas · '
            f'<a href="c/{county_slug(county)}.html">county page</a></span></h2>'
            f'<ul class="areas">{_area_items(county, areas)}</ul></section>'
        )
    return f"<nav>{nav}</nav>\n{''.join(sections)}"


def area_has_page(code):
    """Whether an area names a place a reader could search for.

    Three kinds of code never do. An Electoral Division is the countryside
    around somewhere rather than a place - all 2,808 are named "Around ...", and
    1,193 of them have a notice; publishing that many near-identical pages is
    what a search engine demotes as scaled thin content, and nobody searches the
    name. A city's "-rest" code is the remainder of its Local Electoral Areas,
    named "Elsewhere in Cork city". UNPLACED is a pin that could not be homed at
    all. What is left is 697 CSO settlements and 42 city LEAs.

    Deliberately not gated on a notice count as well. A floor would make a URL
    appear the day an area's second notice arrives, and a permalink that comes
    and goes is worse than a short one - the 122 pages currently holding a
    single notice still answer "was the water off in Abbeydorney" for a real
    place with a real population.
    """
    return (
        code != UNPLACED
        and not code.startswith("ed:")
        and not code.endswith("-rest")
    )


def area_path(county, name):
    """`a/<county>/<area>.html` for an area with a page.

    Nested under the county because an area name is not unique nationally, and
    keyed on the name rather than the code because a code is not a filename - 31
    contain a slash and most contain colons, which is what kept the history
    shards per county. The county-and-name pair is unique over every area in the
    CSO file, asserted in the tests rather than assumed.

    `statusui.slug` rather than the `slug` in ui.js: the two are deliberately
    unpaired, and the JS one leaves a fada as a dash - it would send 17 of these
    places to a URL that does not exist. The app is given the slug in the
    payload for that reason.
    """
    return f"{AREA_DIR}/{county_slug(county)}/{statusui.slug(name)}.html"


def county_slug(county):
    """The history shard filename for a county.

    Every key of COUNTY_POP is one ASCII word, so lowercasing is total and
    injective — asserted in the tests rather than trusted, because a future
    county spelled with a space or a fada would silently collide or produce a
    filename the loader cannot request.
    """
    return county.lower()


# Kept in step with SEVLABEL in site.html by hand — the same duplication, and
# for the same reason, as the :root token block areas.html repeats.
SEV_LABEL = {
    "outage": "Supply disruption",
    "quality": "Water quality notice",
    "degraded": "Restrictions / low pressure",
    "maintenance": "Works (planned / non-disruptive)",
}

def county_events(areas_history):
    """Every event in one county, newest first, each appearing once.

    area_history lists an event under every area its pins were homed to and
    shares one record by reference between them, so the county's own list has to
    de-duplicate or it would print the 764 multi-area events twice over. Keyed on
    `ref`, which is unique within a county — the (county, ref) pairing that
    area_history documents is already resolved by the time we are inside one.
    """
    seen = {}
    for area in areas_history.values():
        for event in area["events"]:
            seen.setdefault(event["ref"], event)
    return sorted(seen.values(), key=lambda e: (e["start"], e["ref"]), reverse=True)


def _fmt_day(iso):
    """'Fri 1 Aug' for readers, with the year appended when it isn't this year's."""
    return statusui.fmt_date(iso, date.today())


def notice_paragraphs(description):
    """The feed's notice text as plain paragraphs, its markup gone.

    The feed writes notices as HTML with <br><br> between paragraphs and <b>
    around updates; none of that is trusted on a page, so tags are stripped and
    the breaks kept. The trailing "LA01"-style code is a feed artefact, not
    something the notice said.
    """
    text = re.sub(r"<br\s*/?>|</p>", "\n", description or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    paragraphs = [p for p in paragraphs if p]
    if paragraphs and re.fullmatch(r"[A-Z]{2}\d{2}", paragraphs[-1]):
        paragraphs.pop()
    return paragraphs


def _notice_text_html(description):
    paragraphs = notice_paragraphs(description)
    if not paragraphs:
        return ""
    return (
        "<details><summary>What the notice says</summary>"
        + "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
        + "</details>"
    )


def _county_open_html(cdata, today, text=None, built=""):
    """Notices open right now — the one thing on the page a reader may have come
    for today rather than for the record. `text` is ref -> the notice's own
    words, carried here and nowhere in the app payload: the open notices are
    the ones a reader needs the wording of, to know whether their road is in it.
    """
    if not cdata["open"]:
        return ""
    text = text or {}
    rows = "".join(
        f'<li><span class="sev sev-{html.escape(o["sev"])}">'
        f'{html.escape(SEV_LABEL[o["sev"]])}</span> '
        f'<strong>{html.escape(o["title"])}</strong>'
        + (f' - {html.escape(o["loc"])}' if o["loc"] else "")
        # "from" for one still ahead of the build, as the app's openGroups says it
        + f'<span class="when">{"from" if o.get("ahead") or o["since"] > today else "since"} '
        + _fmt_day(o["since"])
        + (
            f' · <a href="{url}">{url.rsplit("/", 1)[1]}</a>'
            if (url := notice_url(o["ref"]))
            else ""
        )
        + (f" · {_back_text(o['back'], built)}" if o.get("back") else "")
        + "</span>"
        + _notice_text_html(text.get(o["ref"]))
        + "</li>"
        for o in cdata["open"]
    )
    return (
        f'<section id="open"><h2>Open now <span>'
        f'· {cdata["open_total"]:,} notice{"" if cdata["open_total"] == 1 else "s"}'
        f'</span></h2><ul class="notices">{rows}</ul></section>'
    )


def _back_text(back, built):
    """"expected back by Wed 7 Oct, 18:00", the end an open notice states; one
    already past at `built` (Irish wall clock, as `back` is) was expected."""
    when = _fmt_day(back[:10]) + (f", {back[11:]}" if "T" in back else "")
    return f"{'was ' if back_key(back) < built else ''}expected back by {when}"


def _rate_text(per_100km):
    return "-" if per_100km is None else f"{per_100km:.2f}"


def _grade_cell(letter):
    """The month table's grade cell; a month the site did not see whole has none."""
    if letter is None:
        return '<td class="g g-none">-</td>'
    return f'<td class="g g-{letter}">{letter}</td>'


def _county_summary_html(county, cdata, n_areas, n_events, months):
    """The opening paragraph and the current-state line."""
    pop = cdata["pop"]
    latest = next(
        (ym for ym in reversed(months) if cdata["months"][ym]["days_elapsed"]), None
    )
    parts = [
        f"<p class=\"sub\">Every water supply notice Uisce Éireann has published for "
        f"Co. {html.escape(county)}: "
        f"{n_events:,} notice{'' if n_events == 1 else 's'} across "
        f"{n_areas:,} area{'' if n_areas == 1 else 's'}. "
        f"Population {pop:,}; {cdata['mains_km']:,} km of water main, "
        f"from Uisce Éireann's supply zones.</p>"
    ]
    if latest:
        m = cdata["months"][latest]
        last = cdata["last_30"]
        health = ""
        # health_now, not health_n: this line says "now", and a notice lifted
        # on the 3rd is not an active warning on the 25th
        if m["health_now"]:
            health = (
                f' <span class="health">{m["health_now"]} active health '
                f'notice{"" if m["health_now"] == 1 else "s"}</span>'
            )
        n = last["outage_notices"]
        # inside collection's first 30 days the window carries its count alone
        rated = (
            f'grade <strong>{last["count_grade"]}</strong>, {n} outage '
            f'notice{"" if n == 1 else "s"}, {_rate_text(last["per_100km"])} per 100 km of main'
            if last["count_grade"]
            else f'{n} outage notice{"" if n == 1 else "s"}, too soon for a rate'
        )
        parts.append(
            f'<p class="now">Over the last 30 days: {rated}. This month, '
            f'{m["clear_days"]} of {m["days_elapsed"]} elapsed days clear of '
            f'supply disruption.'
            f'{health}</p>'
        )
    return "".join(parts)


def _county_months_html(cdata, months):
    """One row per month: the same figures the app's county view charts."""
    rows = []
    for ym in reversed(months):
        m = cdata["months"][ym]
        if not m["days_elapsed"]:
            continue  # a month collection never reached says nothing
        ev = m["events"]
        rows.append(
            f'<tr><th scope="row">{ym}</th>'
            f'{_grade_cell(m["count_grade"])}'
            f'<td>{_rate_text(m["per_100km"])}</td>'
            f'<td>{m["outage_notices"]}</td><td>{ev["quality"]}</td>'
            f'<td>{ev["degraded"]}</td><td>{ev["maintenance"]}</td></tr>'
        )
    if not rows:
        return ""
    return (
        '<section id="months"><h2>Month by month</h2>'
        '<div class="scroll"><table><thead><tr>'
        '<th scope="col">Month</th><th scope="col">Grade</th>'
        '<th scope="col" title="Outage notices published per 100 km of the county\'s water main; '
        'only for a month the site saw whole">Per 100 km</th>'
        '<th scope="col" title="Supply disruptions first published this month">Outages</th>'
        '<th scope="col" title="Boil water, do not drink, discolouration">Quality</th>'
        '<th scope="col" title="Restrictions and low pressure">Restricted</th>'
        '<th scope="col" title="Planned or non-disruptive works">Works</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _area_months_html(area_months, months):
    """One row per month with a notice, from the same area-month rows the app's
    county breakdown charts. No grade: a letter needs the county's mains."""
    rows = []
    for ym in reversed(months):
        m = area_months.get(ym)
        if not m:
            continue
        ev = m["events"]
        rows.append(
            f'<tr><th scope="row">{ym}</th>'
            f'<td>{ev.get("outage", 0)}</td><td>{ev.get("quality", 0)}</td>'
            f'<td>{ev.get("degraded", 0)}</td><td>{ev.get("maintenance", 0)}</td></tr>'
        )
    if not rows:
        return ""
    return (
        '<section id="months"><h2>Month by month</h2>'
        '<div class="scroll"><table><thead><tr>'
        '<th scope="col">Month</th>'
        '<th scope="col" title="Supply disruptions">Outages</th>'
        '<th scope="col" title="Boil water, do not drink, discolouration">Quality</th>'
        '<th scope="col" title="Restrictions and low pressure">Restricted</th>'
        '<th scope="col" title="Planned or non-disruptive works">Works</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _events_html(events, heading="Notice history", multi_area=False):
    """A list of notices, newest first. Shared by the county and area pages.

    Uncapped on both. These pages exist to be the durable, indexable record, and
    a county's whole history costs a few hundred KB of text — cheaper than a
    document that presents itself as complete and is not.

    `multi_area` adds the note the app's area view carries for the same reason:
    one event published as pins in several areas is listed under each, so
    meeting the same burst twice reads as double-counting unless the page says
    so. The county list de-duplicates and must not carry it.
    """
    if not events:
        return ""
    rows = []
    for e in events:
        bits = []
        started = not e.get("ahead")
        if e.get("hours") is not None:
            # "so far" on an open event: the figure is time accrued to this
            # build, not what the works took, and a bare "0h · still open" on
            # something published this morning reads as a completed nothing
            bits.append(f'{e["hours"]:g}h so far' if e.get("open") else f'{e["hours"]:g}h')
        if e.get("open"):
            bits.append("still open" if started else "not started yet")
        elif e.get("closed"):
            bits.append(f'closed {_fmt_day(e["closed"])}')
        elif not e.get("confirmed") and not e.get("scheduled"):
            # the distinction event_record is careful about: no end was ever
            # reported, which is not the same as an end of zero hours
            bits.append("no end reported")
        meta = " · ".join(bits)
        rows.append(
            f'<li><span class="sev sev-{html.escape(e["sev"])}">'
            f'{html.escape(SEV_LABEL[e["sev"]])}</span> '
            f'<strong>{html.escape(e["title"])}</strong>'
            + (f' - {html.escape(e["loc"])}' if e.get("loc") else "")
            + f'<span class="when">{_fmt_day(e["start"])}'
            + (f' · {meta}' if meta else "")
            + "</span>"
            + (
                f'<span class="also">Also published in '
                f'{e["areas"] - 1} other area'
                f'{"" if e["areas"] == 2 else "s"}, and listed in each'
                "</span>"
                if multi_area and e.get("areas")
                else ""
            )
            + "</li>"
        )
    return (
        f'<section id="notices"><h2>{html.escape(heading)} '
        f'<span>· {len(events):,} notice{"" if len(events) == 1 else "s"}</span></h2>'
        f'<ul class="notices">{"".join(rows)}</ul></section>'
    )


def area_page_html(county, name, pop, events, area_months=None, months=()):
    """The whole body of a/<county>/<area>.html.

    Server-rendered in full and carrying no data.js, for the same reason the
    county pages are: the hash route it replaces is not a URL a reader can keep
    or a search engine can index.

    The list is the same one the app's area view shows, uncapped, so the page
    and the view are the same content - which is why the app links to it as a
    permanent link rather than by naming what is on it.
    """
    # the county route, the same one county_page_html links to: the area route
    # needs the code as a second segment, and a bare `#area/<county>` matches
    # neither of the app's two patterns
    app = f"../../index.html#county/{quote(county, safe='')}"
    return (
        f'<a class="back" href="../../{COUNTY_DIR}/{county_slug(county)}.html">'
        f'← Co. {html.escape(county)}</a>'
        f'<div class="chead"><h1>{html.escape(name)}</h1></div>'
        f'<div class="sub">'
        f'{f"{pop:,} people · Census 2022 · " if pop is not None else ""}'
        f'Co.&nbsp;{html.escape(county)}</div>'
        f'{_area_months_html(area_months or {}, months)}'
        f'{_events_html(events, "Every notice published here", multi_area=True)}'
        f'<section id="more"><h2>Elsewhere</h2><p class="links">'
        f'<a href="../../{COUNTY_DIR}/{county_slug(county)}.html">'
        f'Co. {html.escape(county)}\u2019s whole record</a> · '
        f'<a href="{app}">Co.&nbsp;{html.escape(county)}\u2019s interactive view</a>'
        f'</p></section>'
    )


def county_page_html(
    county, cdata, areas, events, months, all_counties, today, text=None, built=""
):
    """The whole body of c/<slug>.html.

    Server-rendered in full and carrying no data.js: the point of these pages is
    to be readable and indexable without executing anything, which the hash
    routes in site.html can never be. The interactive month chart stays one link
    away rather than being reproduced here.
    """
    nav = " · ".join(
        f'<a href="{county_slug(c)}.html">{html.escape(c)}</a>'
        if c != county
        else f"<strong>{html.escape(c)}</strong>"
        for c in all_counties
    )
    app = f"../index.html#county/{quote(county, safe='')}"
    return (
        f'<header><h1>Co. {html.escape(county)} water supply disruptions</h1>'
        f'{_county_summary_html(county, cdata, len(areas), len(events), months)}'
        f'<p class="app"><a href="{app}">Open the interactive view for '
        f'Co. {html.escape(county)}</a> - daily bars, month switching and the '
        f'area drill-down.</p></header>'
        f'<nav>{nav}</nav>'
        f'{_county_open_html(cdata, today, text, built)}'
        f'{_county_months_html(cdata, months)}'
        f'{_events_html(events)}'
        f'<section id="areas"><h2>Areas with a notice '
        f'<span>· {len(areas):,} area{"" if len(areas) == 1 else "s"}</span></h2>'
        f'<ul class="areas">{_area_items(county, areas, "../")}</ul></section>'
    )


def _window_label(case):
    """"22:00-07:00 from 2026-07-09" — the window a case actually expanded on.

    Read back off the intervals rather than the row, because an inherited window
    is not in the row's own columns. Safe for any series the guard let through:
    it requires two windows, so only the first interval's start and the last
    one's end can be clipped, leaving intervals[1][0] and intervals[0][1] as true
    window edges.
    """
    opens = case.intervals[1][0].astimezone(DUBLIN)
    closes = case.intervals[0][1].astimezone(DUBLIN)
    first = case.intervals[0][0].astimezone(DUBLIN).date()
    return f"{opens:%H:%M}-{closes:%H:%M} from {first}"


def recurrence_report(cases, pin_tags=None):
    """Lines describing what claimed a recurring window and what was believed.

    Printed on every build, matching backfill_work_category's unmatched-title
    report: a prompt that starts hallucinating recurrence would otherwise show up
    only as hours quietly falling, and the expanded count moving together
    with the hour delta is what makes that visible within one build.

    `pin_tags` maps (county, ref) to the outcome of *every* pin, including the
    ones that never claimed a window. It has to, because the event this report
    exists to catch is precisely one where a pin claimed nothing: DON00115765
    published 17 notices describing a nightly window and one completion update
    that described no window at all, and the completion pin's continuous interval
    re-covered every gap the other seventeen carved out. A check that looked only
    at pins with a claim could not see the pin doing the damage.

    Empty when nothing claimed recurrence, so the test suite stays silent.
    """
    if not cases:
        return []
    expanded = [c for c in cases if c.rec.startswith("expanded")]
    covered = sum((e - s).total_seconds() for c in expanded for s, e in c.intervals) / 3600
    # what the continuous rule would have charged: publication to the capped end,
    # which is the last window's close — the [(start, end)] the guard falls back to
    elapsed = sum((c.intervals[-1][1] - c.start).total_seconds() for c in expanded) / 3600

    inherited = sum(1 for c in cases if c.rec == "expanded_inherited")
    claimed = len(cases) - inherited
    lines = [
        f"{claimed} notice(s) claim a recurring window"
        + (f", {inherited} inherit one from a sibling pin:" if inherited else ":")
    ]
    if expanded:
        lines.append(
            f"  {len(expanded):>4} expanded  {covered:,.0f}h charged "
            f"where the continuous rule charged {elapsed:,.0f}h"
        )
    # The two tiers with no cross-check behind them, listed case by case because
    # they are the least-evidenced expansions on the site and few enough to read:
    # a completion update states no window close to check against, and an
    # inherited window was never stated by the notice it is applied to.
    for tag, why in (("expanded_observed", "from a completion update (no cross-check)"),
                     ("expanded_inherited", "using a window inherited from a sibling pin")):
        tier = [c for c in expanded if c.rec == tag]
        if not tier:
            continue
        lines.append(f"  {len(tier):>4} {why} — listed:")
        for c in tier:
            hours = sum((e - s).total_seconds() for s, e in c.intervals) / 3600
            lines.append(
                f"       {c.row['id']} {c.ref}  {_window_label(c)}, "
                f"{len(c.intervals)} windows, {hours:.0f}h"
            )
    refusals = Counter(c.rec for c in cases if c.rec.startswith("refused"))
    for reason, n in refusals.most_common():
        lines.append(f"  {n:>4}x {reason}")

    # An event's coverage is unioned across its pins, so one pin falling back to
    # the continuous interval re-covers every gap the others carved out — the fix
    # can land on 17 pins and be undone by the 18th. This is the only place that
    # shows up, and it must count pins that made no claim at all.
    mixed = sorted(
        (key, tags) for key, tags in (pin_tags or {}).items()
        if any(t.startswith("expanded") for t in tags)
        and not all(t.startswith("expanded") for t in tags)
    )
    if mixed:
        lines.append(
            f"  ⚠ {len(mixed)} event(s) mix expanded and unexpanded pins — "
            "the union keeps the continuous block:"
        )
        for (county, ref), tags in mixed:
            n = sum(1 for t in tags if t.startswith("expanded"))
            others = Counter(t for t in tags if not t.startswith("expanded"))
            why = ", ".join(f"{v}x {k}" for k, v in others.most_common())
            lines.append(f"       {county} {ref}  {n}/{len(tags)} pins expanded ({why})")
    return lines


def build_site(rows, now, towns=None, data_as_of=None, mains_km=None):
    # data_as_of is when the feed was last read; the site can be rebuilt without
    # a data build, so the freshness banner must not follow the build clock
    data_as_of = data_as_of or now
    mains_km = mains_km or county_mains_km(read_zones())
    months = month_list(COLLECTION_START, now)

    lifts = collect_lifts(rows)

    counties = defaultdict(Region)
    county_towns = defaultdict(lambda: defaultdict(Region))
    # (county, ref) -> (publication, id, area) per pin, so the event can be named
    # once, after the loop, from all of them
    event_pins = defaultdict(list)
    event_codes = defaultdict(set)
    # (county, ref) -> every disruption interval the event's pins contributed,
    # unmerged. area_history merges them; nothing else reads this.
    event_iv = defaultdict(list)
    # (county, ref) -> title, start, and how each of the event's pins signalled
    # its end. Kept out of Region, which is instantiated once per county *and*
    # once per county-area — a couple of thousand times — and none of the area
    # regions need any of this.
    #
    # Covers every severity, not just outages. An event is a reference_num, and
    # a per-area history that skipped the works and the quality notices would be
    # answering a narrower question than the one a reader asked. The consequence
    # is that the 36 events whose pins disagree on severity now report all their
    # pins to top_events rather than only the outage ones — see the build report.
    event_meta = {}
    recurrence = []  # every pin that claimed a window, for the report's detail lines
    notice_text = defaultdict(dict)  # county -> ref -> the wording, open events only
    # every pin's outcome, claimed or not — the mixed-event check needs the ones
    # that made no claim, since those are what re-cover an expanded event's gaps
    pin_tags = defaultdict(list)
    shared = event_windows(rows)
    recurring = recurring_events(rows, shared)

    for r in rows:
        key = (r["county"], case_ref(r))
        case = resolve_case(r, lifts, now, shared.get(key), key in recurring)
        if case is None:
            continue
        pin_tags[(case.county, case.ref)].append(case.rec)
        if case.rec != "none":
            recurrence.append(case)
        counties[case.county].add(case)
        meta = event_meta.setdefault(
            (case.county, case.ref),
            # first pin wins, matching how the event's open entry is recorded
            {"title": r["title"], "start": case.start.strftime("%Y-%m-%d"),
             "first_pub": case.start,
             "pins": 0, "confirmed": 0, "scheduled": 0, "sev": case.sev,
             "loc": r["location"] or "", "open": False, "closed": None, "health": False,
             "measured": [], "capped": False,
             "seen": r["first_seen"] or r["start_date"]},
        )
        meta["pins"] += 1
        # the build that first saw any pin; NULL on every case before the column
        meta["seen"] = min(meta["seen"], r["first_seen"] or r["start_date"])
        # the earliest publication across the event's pins, which is what
        # "started this month" means for the completion median. Not
        # setdefault: rows arrive in id order, not start_date order.
        meta["first_pub"] = min(meta["first_pub"], case.start)
        if case.observed_end:
            meta["confirmed"] += 1
        elif case.has_end:
            meta["scheduled"] += 1
        # the worst class any of the event's pins was put in. A burst published
        # alongside its own traffic-management notice is a burst.
        meta["sev"] = min(meta["sev"], case.sev, key=SEV_ORDER.index)
        meta["loc"] = meta["loc"] or (r["location"] or "")
        meta["health"] |= knocks_grade(r)
        if case.is_open:
            meta["open"] = True
            notice_text[case.county].setdefault(case.ref, r["description"])
        elif case.closed and (meta["closed"] is None or case.closed < meta["closed"]):
            # the earliest close across the pins, which is how Region.resolved
            # takes it, so the history and the closed list agree on the day
            meta["closed"] = case.closed
        event_iv[(case.county, case.ref)].extend(case.intervals)
        if not case.no_end:
            meta["measured"].extend(case.intervals)
        meta["capped"] |= case.capped and case.sev == "outage"
        if towns is not None:
            # the breakdown homes each pin individually; the event is named once
            code = towns.place(r["full_lat"], r["full_lon"], case.county)
            county_towns[case.county][code].add(case)
            event_pins[(case.county, case.ref)].append((case.start, r["id"], code))
            event_codes[(case.county, case.ref)].add(code)

    # One name per event, decided on all its pins rather than on whichever the
    # feed happened to publish first. A 6-pin burst spread across two settlements
    # was being labelled from one pin and ranked from another, so the same event
    # could read "Allenwood" in the open list and "Prosperous" in the top ten.
    area_of = {key: event_area(pins) for key, pins in event_pins.items()}

    site = {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        # the same instant in a form Date.parse handles across engines, so the
        # banner can say "4 hours ago" rather than make the reader do timezone
        # arithmetic. The human-readable one above stays, in the footer.
        "generated_iso": now.strftime("%Y-%m-%dT%H:%M:00Z"),
        "data_as_of_iso": data_as_of.strftime("%Y-%m-%dT%H:%M:00Z"),
        "months": months,
        "counties": {},
        "national": {},
    }
    # ym -> notice-to-end hours, split by whether the end was observed or merely
    # scheduled. Only the observed list feeds the published headline.
    national_observed = defaultdict(list)
    national_scheduled = defaultdict(list)
    national_no_end = Counter()
    # ym -> (hours, county, ref) of every event the observed median reads
    national_longest = defaultdict(list)

    # county -> first publication of each event whose worst pin is an outage
    outage_pubs = defaultdict(list)
    for (county, _ref), meta in event_meta.items():
        if meta["sev"] == "outage":
            outage_pubs[county].append(meta["first_pub"])
    national_km = sum(mains_km.values())
    site["mains_km"] = round(national_km)
    national_notices = Counter()
    # counted to the last feed read: a UI deploy on a stale release must not
    # read the days nobody fetched as quiet ones
    seen = min(now, data_as_of)
    # the month in progress is graded on this window, not on its own part-month
    rolling_lo = seen - timedelta(days=30)
    rolling_whole = seen_whole(rolling_lo, seen, seen)
    site["last_30"] = count_figures(
        sum(count_notices(pubs, rolling_lo, seen, seen) for pubs in outage_pubs.values()),
        national_km, graded=False, whole=rolling_whole,
    )

    for county in sorted(counties):
        region = counties[county]
        merged, events = region.merged(), region.events()
        cdata = {
            "pop": COUNTY_POP[county],
            "mains_km": round(mains_km[county]),
            "last_30": count_figures(
                count_notices(outage_pubs[county], rolling_lo, seen, seen), mains_km[county],
                whole=rolling_whole,
            ),
            "months": {},
            "open": sorted(
                (
                    {**case, "area": area_of[(county, ref)],
                     "name": towns.label(area_of[(county, ref)])}
                    if (county, ref) in area_of
                    else dict(case)
                    for ref, case in region.open_now.items()
                ),
                key=lambda o: o["since"],
                reverse=True,
            ),
            "open_total": len(region.open_now),
            "towns": county_town_data(county_towns[county], towns, county, months, now),
            "resolved": resolved_by_month(region, RESOLVED_SHOWN),
        }

        for ym in months:
            lo, hi = month_bounds(ym)
            ndays = (hi - lo).days

            days = []
            # Days the month has actually reached: neither before collection
            # began nor in the future. Counting "clear" over the whole month
            # counts days that have not happened yet as clear — on 6 August a
            # county with four bad days out of six read "27/31 clear days".
            days_elapsed = clear_days = 0
            for d in range(ndays):
                dlo, dhi = lo + timedelta(days=d), lo + timedelta(days=d + 1)
                # one element, not a bare string: a cached page from before
                # 2026-10-06 destructures [severity, share] and still reads it
                if dhi <= COLLECTION_START:
                    days.append(["nd"])
                    continue
                # the same predicate dayCells applies client-side, and both
                # sides read UTC dates, so they agree on the boundary
                elapsed = dlo.date() <= now.date()
                days_elapsed += elapsed
                worst = ""
                for sev in SEV_ORDER:
                    # Quality never colours a bar: drinking-water safety is the
                    # healthmark's job, supply is the bar's - and skipping
                    # it here lets a quality+restriction day fall through to the
                    # restriction, which no client-side remap could recover.
                    if sev == "quality":
                        continue
                    if overlaps(merged[sev], dlo, dhi):
                        worst = sev
                        break
                clear_days += elapsed and not worst
                days.append([worst])

            stats = region_month(region, ym, now)

            notices = count_notices(outage_pubs[county], lo, hi, seen)
            national_notices[ym] += notices

            # Notice-to-end span of disruption events that started this month.
            # Two tiers, never pooled into the headline: an observed completion
            # says how long works took; a scheduled end only says what was
            # announced. An event that never reported an end is counted, so the
            # exclusion is visible rather than a silence. Events still open with
            # no signal stay out of every figure here.
            observed_h, scheduled_h, no_end_n = [], [], 0
            for ref, iv in events["outage"].items():
                # an empty interval list would not raise here, it would quietly
                # contribute a 0.0 and drag the published median toward zero
                if not iv:
                    continue
                # publication, not iv[0][0]: the median is over events that
                # started this month, wherever their intervals fall
                if not lo <= event_meta[(county, ref)]["first_pub"] < hi:
                    continue
                if not region.has_end["outage"][ref]:
                    no_end_n += region.no_end["outage"][ref]
                    continue
                # covered hours, not elapsed span — for a recurring event these
                # differ, and what the works took is the honest reading
                hours = sum((e - s).total_seconds() for s, e in iv) / 3600
                if region.observed_end["outage"][ref]:
                    observed_h.append(hours)
                    national_longest[ym].append((hours, county, ref))
                else:
                    scheduled_h.append(hours)
            national_observed[ym].extend(observed_h)
            national_scheduled[ym].extend(scheduled_h)
            national_no_end[ym] += no_end_n

            cdata["months"][ym] = {
                "days": days,
                "clear_days": clear_days,
                "days_elapsed": days_elapsed,
                **stats,
                **span_stats(observed_h, scheduled_h, no_end_n),
                **count_figures(notices, mains_km[county], whole=seen_whole(lo, hi, seen)),
            }
        site["counties"][county] = cdata

    for ym in months:
        lo, hi = month_bounds(ym)
        site["national"][ym] = {
            **span_stats(national_observed[ym], national_scheduled[ym], national_no_end[ym]),
            **count_figures(
                national_notices[ym], national_km, graded=False, whole=seen_whole(lo, hi, seen)
            ),
        }

    # Complete months only. The in-progress month gains completions as notices
    # report them, so a "longest of this month" list would reshuffle twice a day.
    current = now.strftime("%Y-%m")
    site["top"] = {
        ym: top_events(national_longest[ym], event_meta, towns, area_of)
        for ym in months
        if ym < current
    }
    # Not part of the payload: write_site splits it into per-county shards the
    # page loads on demand. All of it together is twice the size of data.js.
    site["history"] = (
        area_history(event_meta, event_iv, event_codes, towns, now) if towns else {}
    )
    # popped by write_site into the county pages; never part of the payload
    site["notice_text"] = dict(notice_text)
    site["feed"] = feed_entries(event_meta, area_of, towns)
    site["recurrence_report"] = recurrence_report(recurrence, pin_tags)

    return site


FEED_SHOWN = 50


def feed_entries(event_meta, area_of, towns):
    """{county: [entry, ...]} of the newest FEED_SHOWN events by first sighting.

    Sighting, not publication: `start_date` is re-stamped in place upstream, and
    what a subscriber wants is the build that first saw the notice. Not part of
    the payload; write_site pops it into the Atom files.
    """
    by_county = defaultdict(list)
    for (county, ref), meta in event_meta.items():
        entry = {
            "ref": ref, "county": county, "title": meta["title"], "sev": meta["sev"],
            "seen": meta["seen"], "start": meta["start"], "loc": meta["loc"],
            "open": meta["open"], "closed": meta["closed"],
        }
        code = area_of.get((county, ref)) if towns is not None else None
        if code is not None:
            entry["area"] = towns.label(code)
            if area_has_page(code):
                entry["path"] = area_path(county, entry["area"])
        by_county[county].append(entry)
    return {
        county: sorted(entries, key=lambda e: (e["seen"], e["ref"]), reverse=True)[:FEED_SHOWN]
        for county, entries in by_county.items()
    }


# XML 1.0 forbids these in a document, escaped or not, so one anywhere makes a
# reader reject the whole feed. The feed has sent \x02 in a description.
_NOT_XML = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _xml_text(value):
    return xml_escape(_NOT_XML.sub("", value))


def _atom_entry(e):
    where = e.get("area") or e["loc"]
    state = "still open" if e["open"] else f"closed {e['closed']}" if e["closed"] else "closed"
    summary = " · ".join(
        filter(None, [SEV_LABEL[e["sev"]], f"Co. {e['county']}", where,
                      f"published {e['start']}", state])
    )
    link = e.get("path") or f"{COUNTY_DIR}/{county_slug(e['county'])}.html"
    return (
        # keyed by county as well as reference: 15 references span two counties.
        # Percent-encoded so it is an IRI; a clean reference keeps its old id
        f"<entry><id>{BASE_URL}/n/{county_slug(e['county'])}/"
        f"{quote(e['ref'], safe=':@')}</id>"
        f"<title>{_xml_text(e['title'] + (f': {where}' if where else ''))}</title>"
        f"<updated>{_xml_text(e['seen'])}</updated>"
        f'<link href="{xml_escape(f"{BASE_URL}/{link}", {chr(34): "&quot;"})}"/>'
        f"<summary>{_xml_text(summary)}</summary></entry>"
    )


def atom_feed(title, path, entries, updated):
    """An Atom document of `entries` (feed_entries' shape), newest first."""
    if entries:
        updated = entries[0]["seen"]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>{_xml_text(title)}</title>"
        f'<link href="{BASE_URL}/{path}" rel="self"/><link href="{BASE_URL}/"/>'
        f"<id>{BASE_URL}/{path}</id><updated>{_xml_text(updated)}</updated>"
        f"{''.join(_atom_entry(e) for e in entries)}</feed>"
    )


def data_horizon(conn):
    """The last instant the pipeline read the feed, or None on an empty DB."""
    (last_seen,) = conn.execute("SELECT MAX(last_seen) FROM cases").fetchone()
    return parse_dt(last_seen) if last_seen else None


def read_cases(db_path=DB_PATH):
    """The rows and horizon of the DB at `db_path`, carried to this code's schema
    first: a UI deploy builds from whichever release is current, and that
    release predates every column added since the last data build."""
    with sqlite3.connect(db_path) as conn:
        check_schema_version(conn, db_path)
        return load_cases(conn), data_horizon(conn)


def load_cases(conn):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT c.id, c.county, c.work_category, c.work_type, c.status, c.title,
               c.reference_num, c.start_date, c.location, c.closed_at, c.first_seen,
               c.vanished_at,
               -- read only by describes_recurrence, which is why the severity
               -- rule no longer depends on the model having extracted a window
               c.description,
               c.full_lat, c.full_lon,
               c.boil_water_notice, c.do_not_drink, c.water_restrictions,
               c.reduced_pressure,
               i.notice_to_end_seconds, i.end_input_start_date, i.end_source,
               i.end_local_date, i.end_local_time,
               i.end_recurrence, i.end_window_open, i.end_window_close, i.end_window_first_date
        FROM cases c
        LEFT JOIN inferred_cases i ON i.case_id = c.id
        WHERE c.county IS NOT NULL AND c.start_date IS NOT NULL
        """
    ).fetchall()


# index.html + data.js, what a reader downloads before touching anything. Only
# index.html gates the first paint: it inlines the first render's data and
# data.js loads after it. The split of 2026-09-05 left both under 300 KB; the
# warning is for the next growth.
INITIAL_BUDGET = 512 * 1024

HISTORY_DIR = "h"
COUNTY_SHARD_DIR = "t"
COUNTY_DIR = "c"
AREA_DIR = "a"
FEED_DIR = "feed"


def first_render_payload(site):
    """What the first overview render reads, for index.html to inline; data.js stays whole."""
    newest = set(site["months"][-1:])
    # named, not "all but": a key added to the payload must not ride into the HTML
    keys = ("generated", "generated_iso", "data_as_of_iso", "months", "last_30", "mains_km")
    first = {k: site[k] for k in keys if k in site}
    first["top_months"] = list(site["top"])
    first["national"] = {m: v for m, v in site["national"].items() if m in newest}
    first["counties"] = {
        name: {
            **{k: v for k, v in county.items() if k not in ("months", "open")},
            "months": {m: v for m, v in county["months"].items() if m in newest},
        }
        for name, county in site["counties"].items()
    }
    return first


def inline_json(payload):
    """JSON for a <script> element: a `<` never reaches the page, so no string in
    it can close the element or open a comment."""
    return json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")


def write_site(site, site_dir, towns=None):
    """data.js, index.html, areas.html, c/<county>.html, and two shards per county.

    The c/ pages, sitemap.xml and robots.txt are the site's indexable surface.
    Before them the whole site was two URLs: everything a reader might search
    for — a county, a town — lived behind a hash route, which is not a URL a
    crawler can index. The county pages carry the same figures server-rendered
    and link into the app rather than embedding it.

    Owning the split here is what keeps it from failing open: the history is
    popped before data.js is serialised, so a future field added to it cannot
    leak into the payload by omission. All the shards together are twice the
    size of data.js, which is the whole reason they are separate files.

    A shard is written for every county, empty ones included, so the loader
    never has to tell a 404 apart from a county with nothing to show.

    Per county rather than per area, on two counts. Area codes are not
    filenames — 31 of them contain a slash, most contain a colon, several are
    non-ASCII — so per-area files would need a slug scheme and a collision map,
    the same string-munging this project refused when it declined to key the
    drill-down on `location`. And a county shard is one request for every area
    a reader is likely to open in a sitting, at a median 5 KB gzipped.
    """
    history = site.pop("history", {})
    # the county view's own data, out of the payload the overview loads: the
    # area breakdown alone was 61% of data.js and the overview never read it
    county_data = {
        county: {"towns": cdata.pop("towns", {}), "resolved": cdata.pop("resolved", {})}
        for county, cdata in site["counties"].items()
    }
    notice_text = site.pop("notice_text", {})
    feed = site.pop("feed", {})
    data = "window.UISCE_DATA = " + json.dumps(site) + ";"
    first = inline_json(first_render_payload(site))
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "data.js").write_text(data)
    # the noscript fallback: the county pages carry the same figures statically
    county_links = " · ".join(
        f'<a href="{COUNTY_DIR}/{county_slug(c)}.html">{html.escape(c)}</a>'
        for c in sorted(site["counties"])
    )
    (site_dir / "index.html").write_text(
        page_html(
            SITE_HTML,
            {"CANONICAL": f"{BASE_URL}/", "COUNTY-LINKS": county_links, "FIRST-RENDER": first},
        )
    )
    sizes = {"feeds": 0}
    feed_dir = site_dir / FEED_DIR
    feed_dir.mkdir(exist_ok=True)
    # the national feed is the newest of every county's, so a county's own can
    # never carry a notice the national one skipped
    national = sorted(
        (e for entries in feed.values() for e in entries),
        key=lambda e: (e["seen"], e["ref"]), reverse=True,
    )[:FEED_SHOWN]
    feeds = [("feed.xml", "Irish water supply disruptions", national)] + [
        (f"{FEED_DIR}/{county_slug(c)}.xml", f"Co. {c} water supply disruptions", feed.get(c, []))
        for c in site["counties"]
    ]
    for path, title, entries in feeds:
        doc = atom_feed(title, path, entries, site["generated_iso"])
        (site_dir / path).write_text(doc)
        sizes["feeds"] += len(doc.encode())

    shard_bytes = county_shard_bytes = 0
    for name, sub, payload in (
        ("UISCE_HISTORY", HISTORY_DIR, history),
        ("UISCE_COUNTY", COUNTY_SHARD_DIR, county_data),
    ):
        shard_dir = site_dir / sub
        shard_dir.mkdir(exist_ok=True)
        for county in site["counties"]:
            # keyed by the county's real name, so the page never has to invert
            # the slug; the ||= guard makes a shard self-sufficient and
            # order-independent
            body = (
                f"window.{name} = window.{name} || {{}};\n"
                f"window.{name}[{json.dumps(county)}] = "
                f"{json.dumps(payload.get(county, {}))};"
            )
            (shard_dir / f"{county_slug(county)}.js").write_text(body)
            if sub == HISTORY_DIR:
                shard_bytes += len(body.encode())
            else:
                county_shard_bytes += len(body.encode())

    # The directory. Substituted rather than copied, unlike index.html: the rows
    # are the page, and generating them into a template keeps the markup and CSS
    # in an HTML file instead of in Python string literals.
    index_bytes = county_bytes = n_county_pages = search_bytes = 0
    n_area_pages = area_bytes = 0
    pages = ["", "areas.html"]
    if towns is not None:
        # The search index: every Census settlement, noticed or not, so a
        # reader finds their town even when it has never had a notice. Fetched
        # by bindSearch on the first keystroke, never in the initial payload.
        #
        # An entry is `[name, slug]` where the area has a page and a bare name
        # where it does not, which is what lets a hit be a link straight to it.
        # The gate is the payload's own slug rather than area_has_page: 904
        # names are eligible but only the ones with notices get a page built,
        # and the difference would be a search result that 404s.
        names = defaultdict(set)
        for code, name in towns.name.items():
            county = towns.county[code]
            if county not in site["counties"]:
                continue
            # the history, not the breakdown: an area whose every notice is still
            # ahead has no month row, but its page is built all the same
            area = history.get(county, {}).get(code) or {}
            names[county].add((name, area["slug"]) if "slug" in area else name)

        def entry(e):
            return e if isinstance(e, str) else list(e)

        def by_name(e):
            return e if isinstance(e, str) else e[0]

        # UISCE_PLACES, not UISCE_SEARCH: search.js is fetched lazily, so a tab
        # opened before a deploy pairs its own inlined ui.js with the current
        # file. The entries carry a slug now, and the old searchHits calls
        # toLowerCase on them - renaming with the shape means that reader gets
        # the box's own "unavailable, try reloading" rather than a dropdown
        # stuck on "Searching".
        search = "window.UISCE_PLACES = " + statusui.dumps(
            {c: [entry(e) for e in sorted(v, key=by_name)]
             for c, v in sorted(names.items())}
        ) + ";"
        (site_dir / "search.js").write_text(search)
        search_bytes = len(search.encode())
        index = area_index(history, towns)
        page = page_html(
            AREAS_HTML,
            {"AREAS": _area_index_html(index), "CANONICAL": f"{BASE_URL}/areas.html"},
        )
        (site_dir / "areas.html").write_text(page)
        index_bytes = len(page.encode())

        # The indexable surface, one page per county in the payload — the same
        # set the shards cover, so a county the app can route to is always a
        # county a search result can land on. A county with no notice at all is
        # absent from both, and has no page rather than an empty one; every one
        # of the 26 has had notices since collection began.
        county_dir = site_dir / COUNTY_DIR
        county_dir.mkdir(exist_ok=True)
        by_county = dict(index)
        all_counties = sorted(site["counties"])
        built = (datetime.fromisoformat(site["generated_iso"]).astimezone(DUBLIN)
                 .strftime("%Y-%m-%dT%H:%M"))
        for county in all_counties:
            slug = county_slug(county)
            areas = by_county.get(county, [])
            events = county_events(history.get(county, {}))
            body = county_page_html(
                county, site["counties"][county] | county_data[county], areas, events,
                site["months"], all_counties, site["generated_iso"][:10],
                notice_text.get(county), built,
            )
            page = page_html(
                COUNTY_HTML,
                {
                    "FEED": f"../{FEED_DIR}/{slug}.xml",
                    "TITLE": html.escape(
                        f"Co. {county} water supply disruptions - Uisce Éireann notices"
                    ),
                    # The counts and the listing now agree, but the order still
                    # matters: the record first, what the page holds after it, so
                    # a snippet truncated by width leaves a true sentence.
                    "DESC": html.escape(
                        f"Co. {county}: {len(events):,} Uisce Éireann "
                        f"notice{'' if len(events) == 1 else 's'} across {len(areas):,} "
                        f"area{'' if len(areas) == 1 else 's'} - water outages, boil "
                        f"notices, restrictions and works. Month-by-month totals and "
                        f"every notice published."
                    ),
                    "CANONICAL": f"{BASE_URL}/{COUNTY_DIR}/{slug}.html",
                    "BODY": body,
                },
            )
            (county_dir / f"{slug}.html").write_text(page)
            county_bytes += len(page.encode())
            pages.append(f"{COUNTY_DIR}/{slug}.html")
        n_county_pages = len(all_counties)

        # One page per area that names a place - see area_has_page. Written from
        # the history that is already in hand, so this costs a render and no new
        # arithmetic; the app's area view reads the same events out of the shard.
        for county, areas in index:
            for code, name, pop, _n in areas:
                if not area_has_page(code):
                    continue
                events = history.get(county, {}).get(code, {}).get("events", [])
                rel = area_path(county, name)
                path = site_dir / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                page = page_html(
                    AREA_HTML,
                    {
                        "FEED": f"../../{FEED_DIR}/{county_slug(county)}.xml",
                        "TITLE": html.escape(
                            f"{name}, Co. {county} - water outages and notices"
                        ),
                        "DESC": html.escape(
                            f"{name}, Co. {county}"
                            + (f" - {pop:,} people" if pop is not None else "")
                            + f". {len(events):,} Uisce Éireann "
                            f"notice{'' if len(events) == 1 else 's'} published here: "
                            f"water outages, boil notices, restrictions and works, "
                            f"every one of them, newest first."
                        ),
                        "CANONICAL": f"{BASE_URL}/{rel}",
                        "BODY": area_page_html(
                            county, name, pop, events,
                            county_data[county]["towns"].get(code, {}).get("months"),
                            site["months"],
                        ),
                    },
                )
                path.write_text(page)
                area_bytes += len(page.encode())
                pages.append(rel)
                n_area_pages += 1

    # a sitemap over the pages, not the payload: data.js and the shards are
    # fetched by the app, never landed on
    (site_dir / "sitemap.xml").write_text(statusui.sitemap(BASE_URL, pages, site["generated_iso"]))
    (site_dir / "robots.txt").write_text(statusui.robots(BASE_URL))
    return sizes | {
        "data.js": len(data.encode()),
        "first_render": len(first.encode()),
        "shards": shard_bytes + county_shard_bytes,
        "n_areas": sum(len(a) for a in history.values()),
        "areas.html": index_bytes,
        "n_county_pages": n_county_pages,
        "county_pages": county_bytes,
        "search.js": search_bytes,
        "n_area_pages": n_area_pages,
        "area_pages": area_bytes,
    }


def run():
    towns = TownLookup.from_csv(SA_TOWNS_PATH)
    rows, data_as_of = read_cases()
    site = build_site(rows, datetime.now(timezone.utc), towns, data_as_of)

    # a diagnostic for the build log, not for the page
    for line in site.pop("recurrence_report"):
        print(line)

    n_counties, n_months = len(site["counties"]), len(site["months"])
    n_towns = sum(len(c["towns"]) for c in site["counties"].values())
    s = write_site(site, SITE_DIR, towns)
    print(
        f"Wrote {SITE_DIR}/ ({n_counties} counties, "
        f"{n_towns} town breakdowns, {n_months} months)"
    )
    # the payload is the thing this site keeps having to defend; print it every
    # build so a regression is visible in the log rather than in the field
    initial, report = statusui.size_report(
        SITE_DIR, INITIAL_BUDGET, COUNTY_DIR, "county pages",
        extra=[("search.js", "loaded on demand"), ("areas.html", "the directory")],
    )
    print(report)
    print(f"  {'first render':<16}{s['first_render'] / 1024:8.1f} KB   (inline in index.html)")
    print(
        f"  {2 * n_counties} shards {s['shards']:,} bytes over {s['n_areas']} areas "
        f"(one county's breakdown and one county's history, each loaded on demand)"
    )
    if initial > INITIAL_BUDGET:
        # GitHub Actions surfaces this line on the run; a deploy must not fail
        # on growth alone
        print(f"::warning::initial load {initial:,} bytes is over the {INITIAL_BUDGET:,} budget")
    # the indexable surface, printed for the same reason: these pages exist to
    # be crawled, and one silently rendering empty is invisible from the field
    print(
        f"  {s['n_county_pages']} county pages {s['county_pages']:,} bytes  ·  "
        f"{s['n_area_pages']} area pages {s['area_pages']:,} bytes  ·  "
        f"sitemap {s['n_county_pages'] + s['n_area_pages'] + 2} URLs  ·  "
        f"{n_counties + 1} feeds {s['feeds']:,} bytes"
    )
