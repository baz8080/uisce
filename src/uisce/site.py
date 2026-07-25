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
import shutil
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from uisce.config import DB_PATH, SA_POP_PATH, SA_TOWNS_PATH, SITE_DIR

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
IGNORE_CATS = {"boil_notice_lifted"}  # the lift is good news, not an event

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
# accrue unless the feed says they were planned. NULL categories group here.
REPAIR_CATS = {"mains_repair", "valve_repair", "pump_repair", None}

# Only health-relevant quality notices knock a grade; discolouration shows
# but doesn't knock.
KNOCK_CATS = {"boil_notice_issued", "consumption_notice_issued"}

SCHEME_NOISE = {"public", "water", "supply", "scheme", "regional", "pws", "the"}


def classify(row):
    """Severity class for a case row, or None if it isn't an event."""
    cat = row["work_category"]
    if cat in IGNORE_CATS:
        return None
    if IGNORE_BOIL_NOTICES and cat == "boil_notice_issued":
        return None
    if row["do_not_drink"] or row["boil_water_notice"] or cat in QUALITY_CATS:
        return "quality"
    if cat in DEGRADED_CATS or row["water_restrictions"] or row["reduced_pressure"]:
        return "degraded"
    if cat in HARD_CATS:
        return "outage"
    if cat in REPAIR_CATS and row["work_type"] != "Planned":
        return "outage"
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


def grade(availability, knock_events):
    """A-F from population-weighted availability (see notes for calibration)."""
    if availability >= 99.9:
        g = "A"
    elif availability >= 99.75:
        g = "B"
    elif availability >= 99.45:
        g = "C"
    elif availability >= 99.0:
        g = "D"
    else:
        g = "F"
    if knock_events:
        g = "F" if g in ("D", "F") else chr(ord(g) + 1)
    return g


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

    def dominant(self, sas, county):
        """Area holding the largest share of a pin's affected population, or UNPLACED.

        Pins rarely straddle a boundary — the median dominant share is 1.00 on
        the July 2026 corpus — so one home per pin costs almost nothing and
        keeps per-area case counts summing to the county's.

        Only areas in the case's own county are considered. Border pins are real
        (a Kildare-labelled notice whose footprint reaches Blessington, Co.
        Wicklow), and re-homing one across a county line would contradict the
        page it appears on — so the pin goes to the best area that *is* in the
        county rather than being set aside. UNPLACED is left for the pin whose
        whole footprint lies in another county.
        """
        shares = defaultdict(int)
        for guid, pop in sas.items():
            code = self.town.get(guid)
            if code is not None and self.county[code] == county:
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


class Case(NamedTuple):
    """A case row with its severity class and disruption interval resolved.

    Splitting this out of the accumulation loop is what lets a county and a town
    share one set of arithmetic: the interval a case contributes is a property of
    the case alone, not of the geography it is being counted under.
    """

    row: object
    sev: str
    ref: str
    start: datetime
    end: datetime
    sas: dict
    has_end: bool
    observed_end: bool

    @property
    def county(self):
        return self.row["county"]

    @property
    def is_open(self):
        return self.row["status"] == "Open"


def resolve_case(r, sa_index, lifts, now):
    """A Case for one row, or None if it isn't an event at all.

    The interval rules and their rationale are in
    notes/statuspage-methodology.md; this is the code they describe.
    """
    sev = classify(r)
    if sev is None or r["county"] not in COUNTY_POP:
        return None
    start = parse_dt(r["start_date"])
    cap = timedelta(days=CAP_DAYS)

    notice_to_end = r["notice_to_end_seconds"]
    has_end = notice_to_end is not None
    # a paired boil-notice lift is an observed end too; set below
    observed_end = has_end and r["end_source"] in OBSERVED_END_SOURCES

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

    return Case(
        row=r,
        sev=sev,
        ref=r["reference_num"] or f"id:{r['id']}",
        start=start,
        end=end,
        sas=sa_index.affected(r["full_lat"], r["full_lon"]),
        has_end=has_end,
        observed_end=observed_end,
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
        self.has_end = defaultdict(lambda: defaultdict(bool))
        self.observed_end = defaultdict(lambda: defaultdict(bool))
        self.knock_refs = set()
        self.open_now = {}  # ref -> case (dedups multi-pin events)
        self.resolved = {}  # ref -> case, for cases observed to close

    def add(self, case, sas):
        sev, ref = case.sev, case.ref
        self.sev_iv[sev].append((case.start, case.end))
        self.iv[sev][ref].append((case.start, case.end))
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

    counts, person_s, knock_n = {}, 0.0, 0
    for sev in SEV_ORDER:
        n = 0
        for ref, iv in events[sev].items():
            secs = union_seconds(iv, eff_lo, eff_hi)
            if secs > 0:
                n += 1
                if sev == "outage":
                    person_s += secs * epop[sev].get(ref, 0)
                if sev == "quality" and ref in region.knock_refs:
                    knock_n += 1
        counts[sev] = n

    period_s = max((eff_hi - eff_lo).total_seconds(), 1.0)
    availability = 100.0 * (1 - person_s / (pop * period_s))
    return {
        "person_h": round(person_s / 3600),
        "period_h": round(period_s / 3600),
        "availability": round(max(availability, 0.0), 3),
        "events": counts,
        # both for the caller to pop: grading off the rounded, clamped figure
        # would flip a county sitting a thousandth under a threshold
        "knock_n": knock_n,
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


def build_site(rows, sa_index, now, towns=None):
    months = month_list(COLLECTION_START, now)

    lifts = defaultdict(list)
    for r in rows:
        if r["work_category"] == "boil_notice_lifted":
            lifts[r["county"]].append((norm_scheme(r["location"]), parse_dt(r["start_date"])))

    counties = defaultdict(Region)
    county_towns = defaultdict(lambda: defaultdict(Region))
    area_of = {}  # (county, ref) -> area code, so an open case can name its area

    for r in rows:
        case = resolve_case(r, sa_index, lifts, now)
        if case is None:
            continue
        counties[case.county].add(case, case.sas)
        if towns is not None:
            code = towns.dominant(case.sas, case.county)
            county_towns[case.county][code].add(case, towns.within(case.sas, code))
            # first pin wins, matching how the event's open entry is recorded
            area_of.setdefault((case.county, case.ref), code)

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
            county_grade = grade(stats.pop("avail_raw"), stats.pop("knock_n"))

            # Notice-to-end span of disruption events that started this month
            # and carry a real end signal (open/no-signal events excluded so
            # they can't drag the median). Split by end kind: an observed
            # completion says how long works took; a scheduled end only says
            # what was announced, so the two are never pooled.
            observed_h, scheduled_h = [], []
            for ref, iv in events["outage"].items():
                if not (region.has_end["outage"][ref] and lo <= iv[0][0] < hi):
                    continue
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

    return site


def load_cases(conn):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT c.id, c.county, c.work_category, c.work_type, c.status, c.title,
               c.reference_num, c.start_date, c.location, c.closed_at,
               c.full_lat, c.full_lon,
               c.boil_water_notice, c.do_not_drink, c.water_restrictions,
               c.reduced_pressure,
               i.notice_to_end_seconds, i.end_source, i.end_local_date
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

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "data.js").write_text("window.UISCE_DATA = " + json.dumps(site) + ";")
    shutil.copyfile(SITE_HTML, SITE_DIR / "index.html")
    n_months = len(site["months"])
    n_towns = sum(len(c["towns"]) for c in site["counties"].values())
    print(
        f"Wrote {SITE_DIR}/ ({len(site['counties'])} counties, "
        f"{n_towns} town breakdowns, {n_months} months)"
    )
