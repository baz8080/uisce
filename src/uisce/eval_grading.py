"""Re-measure the figures the county letter rests on, against out/uisce.db.

The letter counts supply notices per 100 km of main on fixed cuts, re-fitted
yearly (notes/statuspage-methodology.md, "Every supply notice per 100 km of
main"). This prints what that section records, so a re-fit or a look at an odd
month is one command and not a scratch script:

    uv run uisce-eval-grading                      # every month seen whole
    uv run uisce-eval-grading --to 2026-10         # the months the note measured
    uv run uisce-eval-grading --cuts 2,3,4,5,6     # the mix under candidate cuts

It builds the site with the clock at the data horizon and refuses to report if
its own count of supply notices differs from the payload's: a diagnostic that
cannot reproduce the published total is measuring something else. Nothing is
written and no published number changes.
"""

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from typing import NamedTuple

from uisce.site import (
    SA_TOWNS_PATH,
    SEV_ORDER,
    SUPPLY_CUTS,
    TownLookup,
    build_site,
    case_ref,
    collect_lifts,
    counted_county,
    event_windows,
    km_apart,
    local_date,
    read_cases,
    recurring_events,
    resolve_case,
)
from uisce.wsz import ZoneLookup, county_mains_km, read_zones

# a finished month outside this is a prompt to check how notices are published
NATIONAL_BAND = (3.0, 5.5)
PAIR_KM, PAIR_DAYS = 0.5, 5
REPEAT_KM, REPEAT_DAYS = 0.2, 14
GRID = 0.01  # degrees: a cell is wider than either radius


class Event(NamedTuple):
    county: str
    sev: str
    first_pub: object
    planned: bool
    investigation: bool
    pins: tuple


def supply_events(rows, now, zones=None, zone_rows=()):
    """{(county, ref): Event} of every event that is not a quality notice,
    grouped, dated and counted for a county as build_site does it."""
    zone_county = {row["code"]: row["county"] for row in zone_rows}
    lifts = collect_lifts(rows)
    shared = event_windows(rows)
    recurring = recurring_events(rows, shared)
    held = {}
    for r in rows:
        key = (r["county"], case_ref(r))
        case = resolve_case(r, lifts, now, shared.get(key), key in recurring)
        if case is None:
            continue
        e = held.setdefault(key, {"sev": case.sev, "first": case.start, "planned": True,
                                  "inv": False, "pins": [], "votes": []})
        e["sev"] = min(e["sev"], case.sev, key=SEV_ORDER.index)
        e["first"] = min(e["first"], case.start)
        e["planned"] &= r["work_type"] == "Planned"
        e["inv"] |= r["work_category"] == "investigation"
        e["pins"].append((r["full_lat"], r["full_lon"]))
        if zones is not None:
            zone = zones.zone(r["full_lat"], r["full_lon"])
            e["votes"].append((case.start, r["id"], zone_county.get(zone, key[0])))
    return {
        key: Event(counted_county(key[0], e["votes"]) if e["votes"] else key[0],
                   e["sev"], e["first"], e["planned"], e["inv"], tuple(e["pins"]))
        for key, e in held.items() if e["sev"] != "quality"
    }


def letter(rate, cuts=SUPPLY_CUTS):
    return "ABCDEF"[sum(rate >= cut for cut in cuts)]


def month_of(event):
    return local_date(event.first_pub)[:7]


def monthly_counts(events, months, skip=frozenset()):
    """{(county, ym): supply notices} over `months`, less the events in `skip`."""
    counts = Counter()
    for key, e in events.items():
        if key not in skip and month_of(e) in months:
            counts[e.county, month_of(e)] += 1
    return counts


def _cell(lat, lon):
    return round(lat / GRID), round(lon / GRID)


def near_another(events, candidates, others, km, days):
    """The keys in `candidates` with a pin within `km` of a pin of a different
    event in `others` first published within `days` of it."""
    grid = defaultdict(list)
    for key in others:
        for pin in events[key].pins:
            grid[_cell(*pin)].append((pin, key))
    window = timedelta(days=days)
    hits = set()
    for key in candidates:
        e = events[key]
        for pin in e.pins:
            i, j = _cell(*pin)
            close = (
                other for di in (-1, 0, 1) for dj in (-1, 0, 1)
                for spot, other in grid.get((i + di, j + dj), ())
                if other != key and km_apart(pin, spot) <= km
                and abs(events[other].first_pub - e.first_pub) <= window
            )
            if next(close, None) is not None:
                hits.add(key)
                break
    return hits


def outside_band(national, band=NATIONAL_BAND):
    """[(ym, rate)] of the months whose national rate is outside `band`."""
    return [(ym, rate) for ym, rate in sorted(national.items())
            if not band[0] <= rate <= band[1]]


def red_half(site, months, letters):
    """(A and B county-months red on half their days or more, A and B county-months)."""
    red = total = 0
    for (county, ym), grade in letters.items():
        if grade not in "AB" or ym not in months:
            continue
        days = [d[0] for d in site["counties"][county]["months"][ym]["days"] if d[0] != "nd"]
        total += 1
        red += 2 * days.count("outage") >= len(days)
    return red, total


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="lo", default="0000-00", help="first month, YYYY-MM")
    parser.add_argument("--to", dest="hi", default="9999-99", help="last month, YYYY-MM")
    parser.add_argument("--cuts", help="five candidate cuts, e.g. 2,3,4,5,6")
    args = parser.parse_args(argv)
    cuts = tuple(float(c) for c in args.cuts.split(",")) if args.cuts else SUPPLY_CUTS
    if len(cuts) != 5:
        parser.error("--cuts takes five numbers")

    rows, horizon = read_cases()
    zones, zone_rows = ZoneLookup.from_geojson(), read_zones()
    site = build_site(rows, horizon, TownLookup.from_csv(SA_TOWNS_PATH), horizon,
                      zones=zones, zone_rows=zone_rows)
    counties = site["counties"]
    months = [ym for ym in site["months"] if args.lo <= ym <= args.hi
              and site["national"][ym]["supply_per_100km"] is not None]
    if not months:
        raise SystemExit("no month in that range was seen whole")
    events = supply_events(rows, horizon, zones, zone_rows)
    counts = monthly_counts(events, months)
    published = {(c, ym): counties[c]["months"][ym]["supply_notices"]
                 for c in counties for ym in months}
    if any(counts[k] != n for k, n in published.items()):
        raise SystemExit("this count of supply notices differs from the payload's: "
                         "supply_events has drifted from build_site")

    km = county_mains_km(zone_rows)
    rates = {k: counties[k[0]]["months"][k[1]]["supply_per_100km"] for k in published}
    letters = {k: letter(rate, cuts) for k, rate in rates.items()}
    total = sum(published.values())
    planned = sum(counties[c]["months"][ym]["planned"] for c, ym in published)

    print(f"Release read to {local_date(horizon)}; months {months[0]} to {months[-1]}, "
          f"{len(published)} county-months; cuts {' / '.join(f'{c:g}' for c in cuts)}")
    n_outage = sum(1 for e in events.values() if e.sev == "outage" and month_of(e) in months)
    print(f"Supply notices {total:,}, of them planned {planned:,}, outage notices {n_outage:,}")
    ordered = sorted(rates.values())
    print("Per 100 km per month: " + ", ".join(
        f"{name} {ordered[int(p * (len(ordered) - 1))]:.2f}" for name, p in
        (("min", 0), ("p10", .1), ("p25", .25), ("median", .5), ("p75", .75), ("p90", .9),
         ("max", 1))))
    mix = Counter(letters.values())
    print("Letters: " + ", ".join(f"{g} {mix[g]}" for g in "ABCDEF"))
    empty = [g for g in "ABCDEF" if not any(
        letters[c, ym] == g for c in counties for ym in months[-12:])]
    print(f"Bands holding nothing over the last {len(months[-12:])} months: "
          f"{', '.join(empty) or 'none'}")

    national = {ym: site["national"][ym]["supply_per_100km"] for ym in months}
    print("Nationally: " + ", ".join(f"{ym} {rate:.2f}" for ym, rate in national.items()))
    out = outside_band(national)
    print(f"Months outside {NATIONAL_BAND[0]:g} to {NATIONAL_BAND[1]:g}: "
          + (", ".join(f"{ym} {rate:.2f}" for ym, rate in out) or "none")
          + ("  <- check how notices are being published before reading it as service"
             if out else ""))

    print(f"\n{'county':<11}{'rank':>5}  " + "  ".join(f"{ym:>8}" for ym in months))
    pooled = {c: sum(published[c, ym] for ym in months) / km[c] for c in counties}
    for rank, county in enumerate(sorted(counties, key=pooled.get), 1):
        cells = "  ".join(f"{rates[county, ym]:6.2f} {letters[county, ym]}" for ym in months)
        print(f"{county:<11}{rank:>5}  {cells}")

    in_window = {k for k, e in events.items() if month_of(e) in months}
    investigations = {k for k in in_window if events[k].investigation}
    # an investigation is an outage notice itself; the pair is with one that is not
    outages = {k for k, e in events.items() if e.sev == "outage" and not e.investigation}
    paired = near_another(events, investigations, outages, PAIR_KM, PAIR_DAYS)
    without = monthly_counts(events, months, skip=paired)
    moved = sum(
        letter(round(100.0 * without[k] / km[k[0]], 2), cuts) != letters[k] for k in published
    )
    print(f"\nInvestigations {len(investigations):,}; with another outage notice within "
          f"{PAIR_KM:g} km and {PAIR_DAYS} days {len(paired):,}; "
          f"letters that change if those are not counted: {moved} of {len(published)}")

    works = {k for k in in_window if events[k].planned and events[k].sev == "maintenance"}
    repeats = near_another(events, works, works, REPEAT_KM, REPEAT_DAYS)
    print(f"Planned works {len(works):,}; with another within {REPEAT_KM:g} km and "
          f"{REPEAT_DAYS} days {len(repeats):,} ({len(repeats) / max(len(works), 1):.0%})")

    red, ab = red_half(site, set(months), letters)
    print(f"A and B county-months red on half their days or more: {red} of {ab}")
