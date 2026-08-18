"""Measure how much overlapping events double-count person-hours (uisce-eval-overlap).

notes/statuspage-methodology.md lists "Overlapping events in the same area
double-count person-hours" as a known limitation — the only one carrying no
number. This puts a number on it, against whatever DB is in out/.

The published availability numerator charges each *event* independently: its
unioned intervals times its affected population. Two events covering the same
Small Area at the same time therefore charge that population twice. The exact
numerator unions intervals per *Small Area* across every event touching it,
which cannot double-count by construction. The delta is the overstatement.

Both sides charge an event's *whole* interval union against its *whole* SA
footprint, which is the pairing `region_month` publishes; only the de-overlapping
differs. That is what makes the delta mean one thing: an event's own pins are
staggered in time and place (July's largest ran 385h across 18 pins published
over three days), and splitting the exact side per pin would book that
staggering as overlap, which it is not. With the event-level pairing, a month
with no overlap agrees exactly however many pins its events carry.

The one wrinkle is the county cap: the published figure caps an event's
population at its county's, the per-SA sum has nothing to cap, so a single event
bigger than its county could read here as a small negative overlap. No event in
the corpus is; the report would show it as such.

A diagnostic, not a correction: it prints and changes nothing. If the
overstatement ever grows to matter, the fix belongs in region_month, priced
with this tool's output in hand.
"""

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from uisce.config import DB_PATH, SA_POP_PATH
from uisce.site import (
    COLLECTION_START,
    COUNTY_POP,
    SmallAreaIndex,
    SpanTable,
    case_ref,
    collect_lifts,
    event_windows,
    load_cases,
    merge,
    month_bounds,
    month_list,
    recurring_events,
    resolve_case,
    union_seconds,
)


def overlap_by_month(rows, sa_index, now):
    """{ym: (published_person_s, exact_person_s)} over the outage class nationally.

    Resolution mirrors build_site — same lifts, shared windows, recurrence
    signals and SpanTable — so "published" here is the same accrual the site
    ships, restricted to the only class that accrues. The SpanTable matters as
    much as the rest: without it every case with no usable end signal takes a
    1-second token footprint instead of the imputed span the site charges it
    (see resolve_case), and roughly one disruption in twenty is one of those.
    """
    lifts = collect_lifts(rows)
    shared = event_windows(rows)
    recurring = recurring_events(rows, shared)
    spans = SpanTable(rows)

    # (county, ref) -> intervals and footprint, as Region accumulates them
    ev_iv = defaultdict(list)
    ev_sas = defaultdict(dict)
    for r in rows:
        key = (r["county"], case_ref(r))
        case = resolve_case(
            r, sa_index, lifts, now, shared.get(key), key in recurring, spans
        )
        if case is None or case.sev != "outage":
            continue
        ev_iv[key].extend(case.intervals)
        ev_sas[key].update(case.sas)

    # Merged once, not once per month: the merge is a property of the event, and
    # only the clipping bounds below change from month to month.
    ev_merged = {key: merge(iv) for key, iv in ev_iv.items()}

    # (county, guid) -> the intervals of every event touching that Small Area.
    # The event's merged intervals against the event's whole footprint, matching
    # what region_month charges — see the module docstring on why a per-pin split
    # here would report an event's own staggered pins as overlap.
    sa_iv = defaultdict(list)
    for key, iv in ev_merged.items():
        for guid in ev_sas[key]:
            sa_iv[(key[0], guid)].extend(iv)
    sa_merged = {key: merge(iv) for key, iv in sa_iv.items()}

    out = {}
    for ym in month_list(COLLECTION_START, now):
        lo, hi = month_bounds(ym)
        eff_hi, eff_lo = min(hi, now), max(lo, COLLECTION_START)
        if eff_hi <= eff_lo:
            continue
        published = 0.0
        for key, iv in ev_merged.items():
            secs = union_seconds(iv, eff_lo, eff_hi)
            published += secs * min(sum(ev_sas[key].values()), COUNTY_POP[key[0]])
        exact = 0.0
        for (_, guid), iv in sa_merged.items():
            exact += union_seconds(iv, eff_lo, eff_hi) * sa_index.pop[guid]
        out[ym] = (published, exact)
    return out


def report(by_month):
    lines = [
        "Outage person-hours: as published (per event) vs de-overlapped (per Small Area)",
        f"{'month':>8}  {'published':>12}  {'exact':>12}  {'overlap':>10}  {'share':>6}",
    ]
    tot_pub = tot_exact = 0.0
    for ym, (published, exact) in sorted(by_month.items()):
        tot_pub += published
        tot_exact += exact
        delta = published - exact
        share = 100 * delta / published if published else 0.0
        lines.append(
            f"{ym:>8}  {published / 3600:>12,.0f}  {exact / 3600:>12,.0f}"
            f"  {delta / 3600:>10,.0f}  {share:>5.1f}%"
        )
    delta = tot_pub - tot_exact
    share = 100 * delta / tot_pub if tot_pub else 0.0
    lines.append(
        f"{'total':>8}  {tot_pub / 3600:>12,.0f}  {tot_exact / 3600:>12,.0f}"
        f"  {delta / 3600:>10,.0f}  {share:>5.1f}%"
    )
    return lines


def run():
    sa_index = SmallAreaIndex.from_csv(SA_POP_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        rows = load_cases(conn)
    for line in report(overlap_by_month(rows, sa_index, datetime.now(timezone.utc))):
        print(line)
