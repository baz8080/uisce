"""Build the static status site (out/site/) from out/uisce.db.

Per county and calendar month the generator computes:

- a daily worst-condition status for the statuspage-style day bars, with
  intensity = share of county population affected that day
- events, deduplicated by reference_num with pin intervals unioned
- population-weighted supply availability: 100% minus person-disruption-seconds
  over county person-seconds, measured across the observed window only
- a median notice-to-completion time over events whose end was *observed*
  (an "works are now complete" update), excluding those whose only end signal
  was a schedule — see the notice_to_end_seconds docstring in build.py
- an A-F grade from availability, knocked one step by any active
  boil-water / do-not-drink / do-not-consume notice

Each county then breaks down into the named Census settlements its cases fall
in, plus one bucket for everything outside a settlement. A town gets the same
counts, person-hours and availability as a county, computed with the same
arithmetic over a narrower population — but no letter grade, because the
thresholds are calibrated to county-months and a single burst in a village
would read F while being entirely ordinary.

Methodology, data findings, and the benchmark context behind the grade
thresholds are documented in notes/statuspage-methodology.md.
"""

import csv
import json
import math
import re
import shutil
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from uisce.config import DB_PATH, DUBLIN, RECURRING, SA_POP_PATH, SA_TOWNS_PATH, SITE_DIR

SITE_HTML = Path(__file__).parent / "site.html"

# The feed was first snapshotted on 2026-04-20; earlier days are unobserved
# (the ArcGIS source only retains recent notices).
COLLECTION_START = datetime(2026, 4, 20, tzinfo=timezone.utc)

# Notice-to-end spans above this are capped; the genuinely long events
# (conservation restrictions) are classed degraded and never accrue anyway.
CAP_DAYS = 14

# An end signal only supports a claim about how long works actually took when
# it is an observed completion. Scheduled ends still accrue disruption time
# (a stated plan is the best interval available) but are kept out of the
# published median, which would otherwise mix a plan with an observation.
OBSERVED_END_SOURCES = {"completion_update"}

# A pin is assumed to affect the Small Areas whose centroids lie within
# AFFECT_RADIUS_KM; if none, the nearest Small Area within FALLBACK_KM.
AFFECT_RADIUS_KM = 0.5
FALLBACK_KM = 8.0

# Key and label for the county drill-down bucket holding every case that does
# not fall in a named settlement — 40% of them, since most of Ireland's water
# infrastructure is not in a town.
# Every Small Area belongs to a named area — a settlement, a Local Electoral Area
# of a city, or the countryside of an Electoral Division — so a pin lands in one
# unless its whole affected footprint lies outside the county the notice names.
# That happens for ~1.5% of case-months and is a disagreement between the feed's
# `county` and its own coordinates, not a gap in the geography, so the bucket says
# so instead of pretending to be a place.
UNPLACED = "unplaced"
UNPLACED_LABEL = "Pinned outside the county"

# Census 2022 county populations (approximate; city+county combined).
COUNTY_POP = {
    "Carlow": 61968, "Cavan": 81704, "Clare": 127938, "Cork": 584156,
    "Donegal": 167084, "Dublin": 1458154, "Galway": 276451, "Kerry": 156458,
    "Kildare": 246977, "Kilkenny": 104160, "Laois": 91877, "Leitrim": 35199,
    "Limerick": 205444, "Longford": 46751, "Louth": 139703, "Mayo": 137970,
    "Meath": 220826, "Monaghan": 65288, "Offaly": 83150, "Roscommon": 70259,
    "Sligo": 70198, "Tipperary": 167895, "Waterford": 127363,
    "Westmeath": 96221, "Wexford": 163919, "Wicklow": 155851,
}

# Severity classes, worst first. Only "outage" accrues availability downtime.
SEV_ORDER = ["outage", "quality", "degraded", "maintenance"]

QUALITY_CATS = {"boil_notice_issued", "consumption_notice_issued", "discolouration"}
DEGRADED_CATS = {"water_conservation", "low_pressure"}
IGNORE_CATS = {"boil_notice_lifted", "consumption_notice_lifted"}  # a lift is good news

# Boil notices are the weakest class in the dataset: only 1 of 23 has a real end
# (see boil_notice_fate and notes/boil-notices.md). Setting this to True drops the
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
# accrue unless the feed says they were planned.
#
# NULL categories deliberately do NOT group here. A title classify_category
# cannot place — "unknown", a bare reference number — evidences nothing, and
# counting it as a national supply outage fabricates downtime in the way
# ended_by_publication and boil_notice_fate exist to prevent. It also made the
# rule table fail loudly in the wrong direction: an unrecognised spelling of
# "Water Conservation/Restriction" accrued as a hard outage until someone
# noticed. Unmatched titles now fall through to maintenance and are printed by
# every backfill instead (see backfill_work_category).
REPAIR_CATS = {"mains_repair", "valve_repair", "pump_repair"}

# Only health-relevant quality notices knock a grade; discolouration shows
# but doesn't knock.
KNOCK_CATS = {"boil_notice_issued", "consumption_notice_issued"}

SCHEME_NOISE = {"public", "water", "supply", "scheme", "regional", "pws", "the"}


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
    if row["do_not_drink"] or row["boil_water_notice"] or cat in QUALITY_CATS:
        return "quality"
    if cat in DEGRADED_CATS or row["water_restrictions"] or row["reduced_pressure"]:
        return "degraded"
    if cat in HARD_CATS or (cat in REPAIR_CATS and row["work_type"] != "Planned"):
        return "degraded" if recurring else "outage"
    # planned works, and non-disruptive activity regardless of work_type
    return "maintenance"


def knocks_grade(row):
    return bool(
        row["do_not_drink"] or row["boil_water_notice"] or row["work_category"] in KNOCK_CATS
    )


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

    Returns (outcome, end):
      "paired"  — a matching lift was found; `end` is the real end of the notice.
      "accrue"  — no lift, but the notice is younger than CAP_DAYS, so status='Open'
                  is still plausible; `end` runs to now.
      "exclude" — no lift and older than CAP_DAYS. The feed's status is known to go
                  stale (case 221165 has been 'Open' since 2025-11-13 and its own
                  description says it was lifted), so accruing these fabricates
                  downtime that never happened. `end` is None; drop the case.

    See notes/boil-notices.md for the measurements behind this.
    """
    start = parse_dt(row["start_date"])
    lift = paired_lift(lifts, row["county"], row["location"], start)
    if lift is not None:
        return "paired", max(lift, start)
    if row["status"] != "Open":
        return "closed_no_signal", None
    if now - start > timedelta(days=CAP_DAYS):
        return "exclude", None
    return "accrue", min(now, start + timedelta(days=CAP_DAYS))


def paired_lift(lifts, county, location, start):
    """Earliest boil-notice lift matching this notice's scheme, or None.

    Lift notices arrive as separate cases with fresh reference_nums, so the
    pairing key is county + normalised scheme name. Multi-pin publishing is
    not chronologically tidy, so a lift up to 2 days before the issue pin's
    start still counts.
    """
    key = norm_scheme(location)
    if not key:
        return None
    candidates = [
        dt for k, dt in lifts.get(county, []) if k == key and dt >= start - timedelta(days=2)
    ]
    return min(candidates) if candidates else None


def parse_dt(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


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


def union_seconds(intervals, lo, hi):
    """Seconds covered by already-merged intervals, clipped to [lo, hi)."""
    total = 0.0
    for start, end in intervals:
        start, end = max(start, lo), min(end, hi)
        if end > start:
            total += (end - start).total_seconds()
    return total


def grade(availability):
    """A-F from population-weighted availability (see notes for calibration).

    Availability and nothing else. An active boil-water or do-not-drink notice
    used to knock the letter one step, which conflated two things the page is
    better off saying separately: the letter now means supply availability, and a
    health notice is published beside it as its own marker (`health_n`).

    The knock was measured before it was removed. Across 78 settled county-months
    it set the published letter for 8, and it was wildly out of scale with
    everything else on the page — the median knocking notice would have cost
    0.003 points of availability had it accrued like an outage, against the 0.45
    points of the letter band it crossed, a factor of about a hundred. That is
    not an argument that a boil notice is unimportant; it is an argument that its
    importance is not measured in person-hours, and so should not be expressed by
    moving a person-hours score. Donegal's July F was by then the knock alone,
    which a reader comparing it to a genuine F could not see.
    """
    if availability >= 99.9:
        return "A"
    if availability >= 99.75:
        return "B"
    if availability >= 99.45:
        return "C"
    if availability >= 99.0:
        return "D"
    return "F"


class SmallAreaIndex:
    """Census Small Area centroids + populations, grid-hashed for radius lookups."""

    BIN = 0.01  # degrees, ~1.1 km of latitude

    def __init__(self, rows):
        self._bins = defaultdict(list)
        self._cache = {}
        self.pop = {}
        for lat, lon, guid, pop in rows:
            self._bins[(int(lat / self.BIN), int(lon / self.BIN))].append((lat, lon, guid, pop))
            self.pop[guid] = pop

    @classmethod
    def from_csv(cls, path):
        with open(path, newline="") as f:
            return cls(
                (float(r["lat"]), float(r["lon"]), r["guid"], int(r["pop"]))
                for r in csv.DictReader(f)
            )

    def _near(self, lat, lon, r_km):
        dlat = r_km / 111.0
        dlon = r_km / (111.0 * math.cos(math.radians(lat)))
        hits = []
        for bi in range(int((lat - dlat) / self.BIN) - 1, int((lat + dlat) / self.BIN) + 2):
            for bj in range(int((lon - dlon) / self.BIN) - 1, int((lon + dlon) / self.BIN) + 2):
                for slat, slon, guid, pop in self._bins.get((bi, bj), ()):
                    dist = math.hypot(
                        (slat - lat) * 111.0,
                        (slon - lon) * 111.0 * math.cos(math.radians(lat)),
                    )
                    if dist <= r_km:
                        hits.append((dist, guid, pop))
        return hits

    def affected(self, lat, lon):
        """{guid: pop} of Small Areas a pin at this coordinate is assumed to affect."""
        key = (round(lat, 4), round(lon, 4))
        if key not in self._cache:
            hits = self._near(lat, lon, AFFECT_RADIUS_KM)
            if not hits:
                fallback = self._near(lat, lon, FALLBACK_KM)
                hits = [min(fallback)] if fallback else []
            self._cache[key] = {guid: pop for _, guid, pop in hits}
        return self._cache[key]


class TownLookup:
    """Small Area -> Census settlement, with each settlement's population.

    Built by uisce-fetch-towns (see src/uisce/towns.py): every Small Area whose
    centroid falls inside a CSO Urban Area 2022 boundary is listed against that
    settlement. A town's population is the sum of its Small Areas, not the
    published Census settlement figure, so that town populations and the county
    availability denominator are derived from one source and cannot disagree.
    """

    def __init__(self, rows, sa_pop):
        self.town = {}  # SA guid -> settlement code
        self.name = {}  # code -> settlement name
        self.county = {}  # code -> county
        self.pop = defaultdict(int)  # code -> population
        for guid, code, name, county in rows:
            if guid not in sa_pop:
                continue
            self.town[guid] = code
            if code not in self.name:
                self.name[code] = name
                self.county[code] = county
            self.pop[code] += sa_pop[guid]

    @classmethod
    def from_csv(cls, path, sa_pop):
        with open(path, newline="") as f:
            return cls(
                (
                    (r["guid"], r["town_code"], r["town_name"], r["town_county"])
                    for r in csv.DictReader(f)
                ),
                sa_pop,
            )

    def label(self, code):
        return UNPLACED_LABEL if code == UNPLACED else self.name[code]

    def dominant(self, sas, county, allowed=None):
        """Area holding the largest share of an affected population, or UNPLACED.

        Pins rarely straddle a boundary — the median dominant share is 1.00 on
        the July 2026 corpus — so one home per pin costs almost nothing and
        keeps per-area case counts summing to the county's.

        Only areas in the case's own county are considered. Border pins are real
        (a Kildare-labelled notice whose footprint reaches Blessington, Co.
        Wicklow), and re-homing one across a county line would contradict the
        page it appears on — so the pin goes to the best area that *is* in the
        county rather than being set aside. UNPLACED is left for the pin whose
        whole footprint lies in another county.

        `allowed` restricts the answer to a set of codes. Naming a whole *event*
        needs it: shares are summed per area, so a secondary area common to
        several pins can out-total every pin's own winner and produce a code no
        pin ever registered in the county breakdown — which the page renders as
        a blank heading and silently drops from the area table's open counts.
        No event in the corpus does that today; passing the pins' own codes makes
        it unrepresentable rather than unlikely.
        """
        shares = defaultdict(int)
        for guid, pop in sas.items():
            code = self.town.get(guid)
            if code is None or self.county[code] != county:
                continue
            if allowed is not None and code not in allowed:
                continue
            shares[code] += pop
        if not shares:
            return UNPLACED
        return max(shares.items(), key=lambda kv: kv[1])[0]

    def within(self, sas, code):
        """The part of a pin's footprint that lies in one area.

        Attributing the whole footprint would let a village accrue person-hours
        for people who don't live in it, and could push availability below zero
        when a pin on its edge reaches most of the next one.
        """
        return {guid: pop for guid, pop in sas.items() if self.town.get(guid) == code}


def span_stats(observed_h, scheduled_h):
    """Published notice-to-end figures. `median_completion_h` is the headline and
    covers observed completions only; the scheduled figures are reported
    alongside so the split is visible rather than silently pooled."""
    return {
        "median_completion_h": round(statistics.median(observed_h), 1) if observed_h else None,
        "completed_n": len(observed_h),
        "median_scheduled_h": round(statistics.median(scheduled_h), 1) if scheduled_h else None,
        "scheduled_n": len(scheduled_h),
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
    return row["reference_num"] or f"id:{row['id']}"


# The wording the feed uses for a window repeating over a range of dates.
RECURRENCE_TEXT = re.compile(
    r"\b(daily|nightly|each night|every night|each day|overnight (?:from|between))\b", re.I
)


def describes_recurrence(description):
    """Whether a notice's own text announces a repeating window."""
    return bool(RECURRENCE_TEXT.search(re.sub(r"<[^>]+>", " ", description or "")))


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


def event_windows(rows):
    """{(county, ref): (open, close, first_date)} for events any pin gave a window.

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
    rebuild is reproducible. No event in the corpus currently disagrees; the rule
    exists so that one does not resolve itself differently build to build.
    """
    claims = defaultdict(list)
    for r in rows:
        if r["end_recurrence"] == RECURRING:
            claims[(r["county"], case_ref(r))].append(
                (r["end_window_open"], r["end_window_close"], r["end_window_first_date"])
            )
    return {
        key: max(sorted(set(windows)), key=windows.count)
        for key, windows in claims.items()
    }


def recurring_intervals(row, start, end, shared=None):
    """(windows, tag) for a notice claiming a window that repeats over a date range.

    `windows` is None whenever the claim is not honoured, so a refusal is a pure
    numeric no-op — the caller keeps the single [start, end] interval it would
    have used anyway. That is what lets the checks below be as suspicious as they
    are: the cost of disbelieving the model is zero, and the cost of believing a
    hallucinated recurrence is a county's person-hours quietly falling by half.

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

    open_t, close_t, first_date = (
        _parse_time(window[0]), _parse_time(window[1]), _parse_date(window[2])
    )
    if open_t is None or close_t is None or first_date is None:
        return None, "refused: window fields missing or unparseable"
    if open_t == close_t:
        # a window covering the whole day is a continuous event; say so rather
        # than inventing touching intervals that merge would rejoin anyway
        return None, "refused: window covers the whole day"

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
    start: datetime  # publication, which is also where the intervals are anchored
    intervals: list
    sas: dict
    has_end: bool
    observed_end: bool
    rec: str = "none"  # recurrence outcome, for the build report

    @property
    def county(self):
        return self.row["county"]

    @property
    def is_open(self):
        return self.row["status"] == "Open"


def resolve_case(r, sa_index, lifts, now, shared_window=None, recurring=None):
    """A Case for one row, or None if it isn't an event at all.

    `shared_window` is the recurring window this row's *event* reported, used
    when this particular notice reported none of its own — see event_windows.
    `recurring` is whether the event announces a repeating window by either
    signal (see recurring_events); it decides severity, while shared_window
    decides the intervals. Left None, it falls back to this row's own fields,
    which is enough for a single-notice caller.

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
    if sev is None or r["county"] not in COUNTY_POP:
        return None
    start = parse_dt(r["start_date"])
    cap = timedelta(days=CAP_DAYS)

    notice_to_end = r["notice_to_end_seconds"]
    has_end = notice_to_end is not None
    # a paired boil-notice lift is an observed end too; set below
    observed_end = has_end and r["end_source"] in OBSERVED_END_SOURCES
    rec = "none"

    if r["work_category"] == "boil_notice_issued":
        # This class never ends itself; boil_notice_fate owns the whole decision.
        outcome, end = boil_notice_fate(r, lifts, now)
        if outcome == "exclude":
            return None
        # a lift is a real, observed event, not a schedule
        has_end = outcome == "paired"
        observed_end = has_end
        if end is None:
            # closed with no lift: token footprint, as for any no-signal case
            end = start + timedelta(seconds=1)
    elif not has_end:
        if r["status"] == "Open" and start < now and not ended_by_publication(r):
            # ongoing with no inferred end: runs from start until now, capped
            end = min(now, start + cap)
        else:
            # closed with no usable end signal, or already over per the
            # notice's own text: a token 1s footprint so its start day
            # still colours and it counts as an event, while adding
            # ~nothing to downtime
            end = start + timedelta(seconds=1)
    else:
        end = start + min(timedelta(seconds=notice_to_end), cap)
        # Recurrence lives strictly under has_end, which keeps it away from the
        # branches above: a boil notice's end is a paired lift and never its own
        # text, and the no-signal branches own the 532 cases whose span build.py
        # nulled because the notice was published after its own works window.
        windows, rec = recurring_intervals(r, start, end, shared_window)
        if windows:
            return Case(
                row=r, sev=sev, ref=case_ref(r), start=start,
                intervals=windows, sas=sa_index.affected(r["full_lat"], r["full_lon"]),
                has_end=has_end, observed_end=observed_end, rec=rec,
            )

    return Case(
        row=r,
        sev=sev,
        ref=case_ref(r),
        start=start,
        intervals=[(start, end)],
        sas=sa_index.affected(r["full_lat"], r["full_lon"]),
        has_end=has_end,
        observed_end=observed_end,
        rec=rec,
    )


class Region:
    """Interval and population accounting for one grouping of cases.

    A county and a town within it are the same object with a different
    population attributed to each event: the county gets a pin's whole 500 m
    footprint, a town only the part of it inside the town (`TownLookup.within`).
    """

    def __init__(self):
        self.sev_iv = defaultdict(list)
        self.iv = defaultdict(lambda: defaultdict(list))
        self.sas = defaultdict(lambda: defaultdict(dict))
        # both are OR'd across an event's pins, which is what the monthly median
        # wants (does this event carry *an* end signal at all?) but not what a
        # per-event badge wants: DON00115765 has 18 pins of which 1 reported a
        # completion, and the OR would call the whole thing observed. The top-ten
        # page counts pins instead — see event_meta in build_site.
        self.has_end = defaultdict(lambda: defaultdict(bool))
        self.observed_end = defaultdict(lambda: defaultdict(bool))
        self.knock_refs = set()
        self.open_now = {}  # ref -> case (dedups multi-pin events)
        self.resolved = {}  # ref -> case, for cases observed to close

    def add(self, case, sas):
        sev, ref = case.sev, case.ref
        self.sev_iv[sev].extend(case.intervals)
        self.iv[sev][ref].extend(case.intervals)
        self.sas[sev][ref].update(sas)
        self.has_end[sev][ref] |= case.has_end
        self.observed_end[sev][ref] |= case.observed_end
        if knocks_grade(case.row):
            self.knock_refs.add(ref)
        r = case.row
        if case.is_open:
            self.open_now.setdefault(
                ref,
                {
                    "sev": sev,
                    "title": r["title"],
                    "loc": r["location"] or "",
                    "since": r["start_date"][:10],
                },
            )
        elif r["closed_at"]:
            # closed_at is the first build that saw the case stop being Open —
            # observation time, resolution the build cadence, and NULL for every
            # case that closed before the column existed (schema v2). It is the
            # only field with a month dimension for a case that is no longer
            # open, which is what lets a past month say anything at all.
            self.resolved.setdefault(
                ref,
                {
                    "sev": sev,
                    "title": r["title"],
                    "loc": r["location"] or "",
                    "since": r["start_date"][:10],
                    "closed": r["closed_at"][:10],
                },
            )

    def merged(self):
        return {sev: merge(self.sev_iv[sev]) for sev in SEV_ORDER}

    def events(self):
        return {
            sev: {ref: merge(iv) for ref, iv in self.iv[sev].items()} for sev in SEV_ORDER
        }

    def event_pop(self, cap_pop):
        return {
            sev: {ref: min(sum(s.values()), cap_pop) for ref, s in self.sas[sev].items()}
            for sev in SEV_ORDER
        }


def region_month(region, pop, ym, now):
    """Counts, person-hours and availability for one region in one month.

    Shared by counties and towns. Day bars and the completion median are county
    only — see build_site.
    """
    lo, hi = month_bounds(ym)
    # nothing accrues beyond "now" (future scheduled works are not downtime
    # yet) nor before collection began
    eff_hi, eff_lo = min(hi, now), max(lo, COLLECTION_START)
    events, epop = region.events(), region.event_pop(pop)

    counts, person_s, health_n = {}, 0.0, 0
    for sev in SEV_ORDER:
        n = 0
        for ref, iv in events[sev].items():
            secs = union_seconds(iv, eff_lo, eff_hi)
            if secs > 0:
                n += 1
                if sev == "outage":
                    person_s += secs * epop[sev].get(ref, 0)
                # health-relevant quality notices — boil water, do not drink, do
                # not consume. Published beside the grade rather than inside it.
                if sev == "quality" and ref in region.knock_refs:
                    health_n += 1
        counts[sev] = n

    period_s = max((eff_hi - eff_lo).total_seconds(), 1.0)
    availability = 100.0 * (1 - person_s / (pop * period_s))
    return {
        "person_h": round(person_s / 3600),
        "period_h": round(period_s / 3600),
        "availability": round(max(availability, 0.0), 3),
        "events": counts,
        # active health notices, published beside the grade rather than folded
        # into it — see grade()
        "health_n": health_n,
        # for the caller to pop: grading off the rounded, clamped figure would
        # flip a county sitting a thousandth under a threshold
        "avail_raw": availability,
    }


RESOLVED_SHOWN = 20


def resolved_by_month(region, shown=None):
    """{ym: {"n": count, "cases": [...]}} of events observed to close that month.

    Keyed on `closed_at`, so coverage is partial by construction: it is NULL for
    every case that closed before schema v2, and a case opened and closed inside
    one build gap is never seen open and so never stamped. The site says so
    rather than presenting these as a complete record.

    `shown` caps the listed cases (newest first) while `n` stays the true count —
    the full lists are a third of the page payload and a reader wants the recent
    handful, not 200 titles.
    """
    by_month = defaultdict(list)
    for event in region.resolved.values():
        by_month[event["closed"][:7]].append(event)
    out = {}
    for ym, events in by_month.items():
        events.sort(key=lambda e: e["closed"], reverse=True)
        out[ym] = {"n": len(events), "cases": events[:shown] if shown else events}
    return out


TOP_EVENTS_SHOWN = 10


def top_events(counties, event_meta, towns, area_of, ym, now, shown=TOP_EVENTS_SHOWN):
    """The largest individual supply disruptions nationally in one month.

    Nothing else on the site ranks a single event: person-hours are computed per
    county and per area, and a reader who wants to know what actually happened in
    July gets 26 county rows instead of the burst that caused them. In July 2026
    the ten largest events were 21% of every person-hour lost nationally, one of
    them 9% on its own, so the distribution is worth a page.

    Person-hours are clipped to the month with the same bounds region_month uses,
    not attributed whole to the month an event started, which keeps the ranking
    summable against the county figures already published — "these ten are a fifth
    of July" is only true under clipping. person_h comes from the unrounded span
    for that reason, so multiplying the two displayed figures reproduces it to
    within the rounding of `hours`, not exactly.

    Keyed by (county, ref), not ref: 15 reference numbers span two counties, and
    event_pop caps each half against its own county's population, so they are
    genuinely separate accruals and two rows is the honest rendering.
    """
    lo, hi = month_bounds(ym)
    eff_hi, eff_lo = min(hi, now), max(lo, COLLECTION_START)

    rows = []
    for county, region in counties.items():
        events, epop = region.events()["outage"], region.event_pop(COUNTY_POP[county])
        for ref, iv in events.items():
            secs = union_seconds(iv, eff_lo, eff_hi)
            people = epop["outage"].get(ref, 0)
            if secs <= 0 or people <= 0:
                continue
            meta = event_meta[(county, ref)]
            row = {
                "ref": ref,
                "county": county,
                "title": meta["title"],
                "person_h": round(secs * people / 3600),
                "hours": round(secs / 3600, 1),
                "people": people,
                "start": meta["start"],
                "pins": meta["pins"],
                "confirmed": meta["confirmed"],
                "scheduled": meta["scheduled"],
            }
            if towns is not None and (county, ref) in area_of:
                # the same name the county's open list uses — one event, one area,
                # decided once in build_site over the event's whole footprint
                row["area"] = towns.label(area_of[(county, ref)])
            rows.append(row)

    rows.sort(key=lambda r: r["person_h"], reverse=True)
    return rows[:shown]


def town_months(region, pop, months, now, placed=True):
    """Per-month figures for one area, only for the months it has activity in.

    Every field that is zero, absent or implied is left out, and the reader fills
    the gaps. These are the bulk of the page — a few thousand area-months against
    26 counties — and most of them are one disruption and three zeroes, so
    spelling out the zeroes cost a quarter of the whole payload.

    An unplaced pin has no population to divide by, its footprint being in
    another county, so it reports counts and nothing derived from a denominator.
    """
    resolved = resolved_by_month(region)
    out = {}
    for ym in months:
        stats = region_month(region, pop, ym, now)
        counts = {sev: n for sev, n in stats["events"].items() if n}
        if not counts:
            continue
        month = {"events": counts}
        if placed:
            # two decimals is what the page renders; the third was never read
            month["availability"] = round(stats["availability"], 2)
            if stats["person_h"]:
                month["person_h"] = stats["person_h"]
        if resolved.get(ym):
            month["resolved_n"] = resolved[ym]["n"]
        out[ym] = month
    return out


def county_town_data(regions, towns, county, months, now):
    """The drill-down for one county: every named area with a case that month.

    No letter grade. The A-F thresholds are calibrated to the distribution of
    county-months, and an area's population is small enough that one burst main
    covering the whole of it reads F — which would be true arithmetic and a
    false comparison. Availability is still published, against the area's own
    population, because that is the figure the drill-down exists to show.
    """
    if towns is None:
        return {}
    out = {}
    for code, region in regions.items():
        placed = code != UNPLACED
        by_month = town_months(region, towns.pop[code] or 1, months, now, placed)
        if not by_month:
            continue
        # no open-case list here: each one is already in the county's, tagged with
        # its area, and holding both copies cost 80 KB to say the same thing twice
        area = {"name": towns.label(code), "months": by_month}
        if placed:
            area["pop"] = towns.pop[code]
        else:
            area["unplaced"] = True
        out[code] = area
    return out


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
    only as person-hours quietly falling, and the expanded count moving together
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


def build_site(rows, sa_index, now, towns=None):
    months = month_list(COLLECTION_START, now)

    lifts = defaultdict(list)
    for r in rows:
        if r["work_category"] == "boil_notice_lifted":
            lifts[r["county"]].append((norm_scheme(r["location"]), parse_dt(r["start_date"])))

    counties = defaultdict(Region)
    county_towns = defaultdict(lambda: defaultdict(Region))
    # (county, ref) -> the event's whole footprint and the areas its pins were
    # homed to, so the event can be named once, after the loop, from all of it
    event_sas = defaultdict(dict)
    event_codes = defaultdict(set)
    # (county, ref) -> title, start, and how each of the event's pins signalled
    # its end. Kept out of Region, which is instantiated once per county *and*
    # once per county-area — a couple of thousand times — and none of the area
    # regions need any of this.
    event_meta = {}
    recurrence = []  # every pin that claimed a window, for the report's detail lines
    # every pin's outcome, claimed or not — the mixed-event check needs the ones
    # that made no claim, since those are what re-cover an expanded event's gaps
    pin_tags = defaultdict(list)
    shared = event_windows(rows)
    recurring = recurring_events(rows, shared)

    for r in rows:
        key = (r["county"], case_ref(r))
        case = resolve_case(r, sa_index, lifts, now, shared.get(key), key in recurring)
        if case is None:
            continue
        pin_tags[(case.county, case.ref)].append(case.rec)
        if case.rec != "none":
            recurrence.append(case)
        counties[case.county].add(case, case.sas)
        if case.sev == "outage":
            meta = event_meta.setdefault(
                (case.county, case.ref),
                # first pin wins, matching how the event's open entry is recorded
                {"title": r["title"], "start": r["start_date"][:10], "first_pub": case.start,
                 "pins": 0, "confirmed": 0, "scheduled": 0},
            )
            meta["pins"] += 1
            # the earliest publication across the event's pins, which is what
            # "started this month" means for the completion median. Not
            # setdefault: rows arrive in id order, not start_date order.
            meta["first_pub"] = min(meta["first_pub"], case.start)
            if case.observed_end:
                meta["confirmed"] += 1
            elif case.has_end:
                meta["scheduled"] += 1
        if towns is not None:
            # the breakdown still homes each pin individually, with `within`
            # clipping its footprint, so an area only accrues its own people
            code = towns.dominant(case.sas, case.county)
            county_towns[case.county][code].add(case, towns.within(case.sas, code))
            event_sas[(case.county, case.ref)].update(case.sas)
            event_codes[(case.county, case.ref)].add(code)

    # One name per event, decided on its whole footprint rather than on whichever
    # pin the feed happened to publish first. A 6-pin burst spread across two
    # settlements was being labelled from one pin and ranked from another, so the
    # same event could read "Allenwood" in the open list and "Prosperous" in the
    # national top ten. Restricted to codes the pins were homed to — see dominant.
    area_of = {
        key: towns.dominant(sas, key[0], event_codes[key])
        for key, sas in event_sas.items()
    }

    site = {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "months": months,
        "counties": {},
        "national": {},
    }
    # ym -> notice-to-end hours, split by whether the end was observed or merely
    # scheduled. Only the observed list feeds the published headline.
    national_observed = defaultdict(list)
    national_scheduled = defaultdict(list)

    for county in sorted(counties):
        region = counties[county]
        merged, events = region.merged(), region.events()
        cpop = COUNTY_POP[county]
        epop = region.event_pop(cpop)
        cdata = {
            "pop": cpop,
            "months": {},
            "open": sorted(
                (
                    {**case, "area": area_of[(county, ref)]}
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
            for d in range(ndays):
                dlo, dhi = lo + timedelta(days=d), lo + timedelta(days=d + 1)
                if dhi <= COLLECTION_START:
                    days.append(["nd", 0])
                    continue
                worst = ""
                for sev in SEV_ORDER:
                    if union_seconds(merged[sev], dlo, dhi) > 0:
                        worst = sev
                        break
                pct = 0.0
                if worst:
                    affected = sum(
                        epop[worst].get(ref, 0)
                        for ref, iv in events[worst].items()
                        if union_seconds(iv, dlo, dhi) > 0
                    )
                    pct = min(100.0, 100.0 * affected / cpop)
                days.append([worst, round(pct, 2)])

            stats = region_month(region, cpop, ym, now)
            county_grade = grade(stats.pop("avail_raw"))

            # Notice-to-end span of disruption events that started this month
            # and carry a real end signal (open/no-signal events excluded so
            # they can't drag the median). Split by end kind: an observed
            # completion says how long works took; a scheduled end only says
            # what was announced, so the two are never pooled.
            observed_h, scheduled_h = [], []
            for ref, iv in events["outage"].items():
                # an empty interval list would not raise here, it would quietly
                # contribute a 0.0 and drag the published median toward zero
                if not iv:
                    continue
                # publication, not iv[0][0]: a recurring event's first *window*
                # can open in the month after the notice went up, and the median
                # is over events that started this month
                if not (region.has_end["outage"][ref]
                        and lo <= event_meta[(county, ref)]["first_pub"] < hi):
                    continue
                # covered hours, not elapsed span — for a recurring event these
                # differ, and what the works took is the honest reading
                hours = sum((e - s).total_seconds() for s, e in iv) / 3600
                if region.observed_end["outage"][ref]:
                    observed_h.append(hours)
                else:
                    scheduled_h.append(hours)
            national_observed[ym].extend(observed_h)
            national_scheduled[ym].extend(scheduled_h)

            cdata["months"][ym] = {
                "days": days,
                "clear_days": sum(1 for d in days if d[0] == ""),
                "grade": county_grade,
                **stats,
                **span_stats(observed_h, scheduled_h),
            }
        site["counties"][county] = cdata

    for ym in months:
        site["national"][ym] = span_stats(national_observed[ym], national_scheduled[ym])

    # Complete months only. The in-progress month reshuffles between builds as
    # open events accrue toward the 14-day cap and then resolve, so a "largest
    # disruptions of this month" list would contradict itself twice a day.
    current = now.strftime("%Y-%m")
    site["top"] = {
        ym: top_events(counties, event_meta, towns, area_of, ym, now)
        for ym in months
        if ym < current
    }
    site["recurrence_report"] = recurrence_report(recurrence, pin_tags)

    return site


def load_cases(conn):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT c.id, c.county, c.work_category, c.work_type, c.status, c.title,
               c.reference_num, c.start_date, c.location, c.closed_at,
               -- read only by describes_recurrence, which is why the severity
               -- rule no longer depends on the model having extracted a window
               c.description,
               c.full_lat, c.full_lon,
               c.boil_water_notice, c.do_not_drink, c.water_restrictions,
               c.reduced_pressure,
               i.notice_to_end_seconds, i.end_source, i.end_local_date, i.end_local_time,
               i.end_recurrence, i.end_window_open, i.end_window_close, i.end_window_first_date
        FROM cases c
        LEFT JOIN inferred_cases i ON i.case_id = c.id
        WHERE c.county IS NOT NULL AND c.start_date IS NOT NULL
        """
    ).fetchall()


def run():
    sa_index = SmallAreaIndex.from_csv(SA_POP_PATH)
    towns = TownLookup.from_csv(SA_TOWNS_PATH, sa_index.pop)
    with sqlite3.connect(DB_PATH) as conn:
        rows = load_cases(conn)
    site = build_site(rows, sa_index, datetime.now(timezone.utc), towns)

    # a diagnostic for the build log, not for the page
    for line in site.pop("recurrence_report"):
        print(line)

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "data.js").write_text("window.UISCE_DATA = " + json.dumps(site) + ";")
    shutil.copyfile(SITE_HTML, SITE_DIR / "index.html")
    n_months = len(site["months"])
    n_towns = sum(len(c["towns"]) for c in site["counties"].values())
    print(
        f"Wrote {SITE_DIR}/ ({len(site['counties'])} counties, "
        f"{n_towns} town breakdowns, {n_months} months)"
    )
