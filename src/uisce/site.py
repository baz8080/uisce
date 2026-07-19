"""Build the static status site (out/site/) from out/uisce.db.

Per county and calendar month the generator computes:

- a daily worst-condition status for the statuspage-style day bars, with
  intensity = share of county population affected that day
- events, deduplicated by reference_num with pin intervals unioned
- population-weighted supply availability: 100% minus person-outage-seconds
  over county person-seconds, measured across the observed window only
- an A-F grade from availability, knocked one step by any active
  boil-water / do-not-drink / do-not-consume notice

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

from uisce.config import DB_PATH, SA_POP_PATH, SITE_DIR

SITE_HTML = Path(__file__).parent / "site.html"

# The feed was first snapshotted on 2026-04-20; earlier days are unobserved
# (the ArcGIS source only retains recent notices).
COLLECTION_START = datetime(2026, 4, 20, tzinfo=timezone.utc)

# Outage durations above this are capped; the genuinely long events
# (conservation restrictions) are classed degraded and never accrue anyway.
CAP_DAYS = 14

# A pin is assumed to affect the Small Areas whose centroids lie within
# AFFECT_RADIUS_KM; if none, the nearest Small Area within FALLBACK_KM.
AFFECT_RADIUS_KM = 0.5
FALLBACK_KM = 8.0

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
        for lat, lon, guid, pop in rows:
            self._bins[(int(lat / self.BIN), int(lon / self.BIN))].append((lat, lon, guid, pop))

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


def build_site(rows, sa_index, now):
    months = month_list(COLLECTION_START, now)
    cap = timedelta(days=CAP_DAYS)

    lifts = defaultdict(list)
    for r in rows:
        if r["work_category"] == "boil_notice_lifted":
            lifts[r["county"]].append((norm_scheme(r["location"]), parse_dt(r["start_date"])))

    county_sev_iv = defaultdict(lambda: defaultdict(list))
    event_iv = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    event_sas = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    event_has_end = defaultdict(lambda: defaultdict(lambda: defaultdict(bool)))
    knock_refs = defaultdict(set)
    open_now = defaultdict(dict)  # county -> ref -> case (dedups multi-pin events)

    for r in rows:
        sev = classify(r)
        if sev is None or r["county"] not in COUNTY_POP:
            continue
        county = r["county"]
        start = parse_dt(r["start_date"])
        ref = r["reference_num"] or f"id:{r['id']}"

        if r["status"] == "Open":
            open_now[county].setdefault(
                ref,
                {
                    "sev": sev,
                    "title": r["title"],
                    "loc": r["location"] or "",
                    "ref": ref,
                    "since": r["start_date"][:10],
                },
            )

        duration = r["end_duration_seconds"]
        has_real_end = duration is not None

        if r["work_category"] == "boil_notice_issued":
            # This class never ends itself; boil_notice_fate owns the whole decision.
            outcome, end = boil_notice_fate(r, lifts, now)
            if outcome == "exclude":
                open_now[county].pop(ref, None)
                continue
            has_real_end = outcome == "paired"
            if end is None:
                # closed with no lift: token footprint, as for any no-signal case
                end = start + timedelta(seconds=1)
        elif not has_real_end:
            if r["status"] == "Open" and start < now:
                # ongoing with no inferred end: runs from start until now, capped
                end = min(now, start + cap)
            else:
                # closed with no usable end signal: a token 1s footprint so
                # its start day still colours and it counts as an event,
                # while adding ~nothing to downtime
                end = start + timedelta(seconds=1)
        else:
            end = start + min(timedelta(seconds=duration), cap)

        county_sev_iv[county][sev].append((start, end))
        event_iv[county][sev][ref].append((start, end))
        event_sas[county][sev][ref].update(sa_index.affected(r["full_lat"], r["full_lon"]))
        event_has_end[county][sev][ref] |= has_real_end
        if knocks_grade(r):
            knock_refs[county].add(ref)

    site = {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "months": months,
        "counties": {},
        "national": {},
    }
    national_fixes = defaultdict(list)  # ym -> fix durations (hours)

    for county in sorted(county_sev_iv):
        merged = {sev: merge(county_sev_iv[county][sev]) for sev in SEV_ORDER}
        events = {
            sev: {ref: merge(iv) for ref, iv in event_iv[county][sev].items()}
            for sev in SEV_ORDER
        }
        cpop = COUNTY_POP[county]
        epop = {
            sev: {ref: min(sum(s.values()), cpop) for ref, s in event_sas[county][sev].items()}
            for sev in SEV_ORDER
        }
        cdata = {
            "pop": cpop,
            "months": {},
            "open": sorted(open_now[county].values(), key=lambda o: o["since"], reverse=True)[:8],
            "open_total": len(open_now[county]),
        }

        for ym in months:
            lo, hi = month_bounds(ym)
            ndays = (hi - lo).days
            # nothing accrues beyond "now" (future scheduled works are not
            # downtime yet) nor before collection began
            eff_hi, eff_lo = min(hi, now), max(lo, COLLECTION_START)

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

            counts, person_s, knock_n = {}, 0.0, 0
            for sev in SEV_ORDER:
                n = 0
                for ref, iv in events[sev].items():
                    secs = union_seconds(iv, eff_lo, eff_hi)
                    if secs > 0:
                        n += 1
                        if sev == "outage":
                            person_s += secs * epop[sev].get(ref, 0)
                        if sev == "quality" and ref in knock_refs[county]:
                            knock_n += 1
                counts[sev] = n

            # time-to-fix: full duration of disruption events that started this
            # month and have a real end signal (open/no-signal events excluded
            # so they can't drag the median)
            fixes = [
                sum((e - s).total_seconds() for s, e in iv) / 3600
                for ref, iv in events["outage"].items()
                if event_has_end[county]["outage"][ref] and lo <= iv[0][0] < hi
            ]
            national_fixes[ym].extend(fixes)

            period_s = (eff_hi - eff_lo).total_seconds()
            availability = 100.0 * (1 - person_s / (cpop * period_s))
            cdata["months"][ym] = {
                "days": days,
                "clear_days": sum(1 for d in days if d[0] == ""),
                "person_h": round(person_s / 3600),
                "period_h": round(period_s / 3600),
                "availability": round(max(availability, 0.0), 3),
                "grade": grade(availability, knock_n),
                "events": counts,
                "median_fix_h": round(statistics.median(fixes), 1) if fixes else None,
                "fixed_n": len(fixes),
            }
        site["counties"][county] = cdata

    for ym in months:
        fixes = national_fixes[ym]
        site["national"][ym] = {
            "median_fix_h": round(statistics.median(fixes), 1) if fixes else None,
            "fixed_n": len(fixes),
        }

    return site


def load_cases(conn):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT c.id, c.county, c.work_category, c.work_type, c.status, c.title,
               c.reference_num, c.start_date, c.location,
               c.full_lat, c.full_lon,
               c.boil_water_notice, c.do_not_drink, c.water_restrictions,
               c.reduced_pressure,
               i.end_duration_seconds
        FROM cases c
        LEFT JOIN inferred_cases i ON i.case_id = c.id
        WHERE c.county IS NOT NULL AND c.start_date IS NOT NULL
        """
    ).fetchall()


def run():
    sa_index = SmallAreaIndex.from_csv(SA_POP_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        rows = load_cases(conn)
    site = build_site(rows, sa_index, datetime.now(timezone.utc))

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "data.js").write_text("window.UISCE_DATA = " + json.dumps(site) + ";")
    shutil.copyfile(SITE_HTML, SITE_DIR / "index.html")
    n_months = len(site["months"])
    print(f"Wrote {SITE_DIR}/ ({len(site['counties'])} counties, {n_months} months)")
