"""Measure how far the county ordering depends on the fixed-radius footprint (uisce-eval-footprint).

The published footprint is a fixed area: every Small Area centred within 500 m
of a pin. A fixed area catches people in proportion to density, so one notice is
charged ten times the people in Dublin that it is in Kerry. The radius check in
notes/statuspage-methodology.md cannot see that, because changing the radius
scales every county together.

This rebuilds the site's county figures under the opposite assumption, a fixed
headcount: each pin affects its nearest Small Areas until they hold PEOPLE
residents, however far apart they are. Neither is the truth, which the feed does
not carry; the two bracket it. Each variant is rescaled to the published national
person-hours, so only the distribution between counties differs and the fixed
grade cuts still mean something.

A diagnostic: it prints and changes nothing.
"""

import csv
import sqlite3
from datetime import datetime, timezone

from uisce.config import DB_PATH, SA_POP_PATH
from uisce.site import FALLBACK_KM, SmallAreaIndex, build_site, grade, load_cases

PEOPLE = (300, 1000, 3000)


class NearestPeopleIndex(SmallAreaIndex):
    """A footprint of the nearest Small Areas holding at least `people` residents."""

    def __init__(self, rows, people):
        super().__init__(rows)
        self.people = people

    def affected(self, lat, lon):
        key = (round(lat, 4), round(lon, 4))
        if key not in self._cache:
            r_km, hits = 0.5, []
            while True:
                hits = sorted(self._near(lat, lon, r_km))
                if sum(pop for _, _, pop in hits) >= self.people or r_km >= FALLBACK_KM:
                    break
                r_km *= 2
            out, total = {}, 0
            for _, guid, pop in hits:
                out[guid] = pop
                total += pop
                if total >= self.people:
                    break
            self._cache[key] = out
        return self._cache[key]


def county_months(rows, sa_index, now):
    """{county: {ym: (person_h, pop * period_h)}} over finished months."""
    site = build_site(rows, sa_index, now)
    done = site["months"][:-1]
    return {
        county: {
            ym: (c["months"][ym]["person_h"], c["pop"] * c["months"][ym]["period_h"])
            for ym in done
        }
        for county, c in site["counties"].items()
    }


def _availability(person_h, pop_h, scale=1.0):
    return 100 * (1 - scale * person_h / pop_h)


def _ranks(values):
    order = sorted(values, key=values.get, reverse=True)
    return {county: i + 1 for i, county in enumerate(order)}


def spearman(a, b):
    ra, rb = _ranks(a), _ranks(b)
    n = len(ra)
    return 1 - 6 * sum((ra[c] - rb[c]) ** 2 for c in ra) / (n * (n * n - 1))


def compare(base, variant):
    """Pooled availability per county under both footprints, and the letters that move.

    Returns (pooled, moved, graded): pooled is {county: (base %, variant %)} over
    every finished month, moved the county-months whose letter differs.
    """
    months = sorted(next(iter(base.values())))
    pooled_base, pooled_var = {}, {}
    tot_base = sum(base[c][ym][0] for c in base for ym in months)
    tot_var = sum(variant[c][ym][0] for c in base for ym in months)
    scale = tot_base / tot_var if tot_var else 1.0
    for c in base:
        pop_h = sum(base[c][ym][1] for ym in months)
        pooled_base[c] = _availability(sum(base[c][ym][0] for ym in months), pop_h)
        pooled_var[c] = _availability(sum(variant[c][ym][0] for ym in months), pop_h, scale)

    moved = []
    for ym in months:
        month_base = sum(base[c][ym][0] for c in base)
        month_var = sum(variant[c][ym][0] for c in base)
        k = month_base / month_var if month_var else 1.0
        for c in base:
            was = grade(_availability(*base[c][ym]))
            now = grade(_availability(*variant[c][ym], k))
            if was != now:
                moved.append((ym, c, was, now))
    pooled = {c: (pooled_base[c], pooled_var[c]) for c in base}
    return pooled, moved, len(months) * len(base)


def report(base, variants):
    lines = []
    for people, variant in variants.items():
        pooled, moved, graded = compare(base, variant)
        rb = _ranks({c: v[0] for c, v in pooled.items()})
        rv = _ranks({c: v[1] for c, v in pooled.items()})
        rho = spearman({c: v[0] for c, v in pooled.items()}, {c: v[1] for c, v in pooled.items()})
        lines += [
            f"Nearest {people:,} people per pin, against the published 500 m circle",
            f"  rank correlation of county availability: {rho:.2f}",
            f"  county-months changing letter: {len(moved)} of {graded}",
            f"  {'county':<10} {'500 m':>8} {'rank':>4}   {'fixed':>8} {'rank':>4}  {'moved':>5}",
        ]
        for c in sorted(pooled, key=lambda c: rb[c] - rv[c]):
            lines.append(
                f"  {c:<10} {pooled[c][0]:>7.2f}% {rb[c]:>4}   {pooled[c][1]:>7.2f}% {rv[c]:>4}"
                f"  {rb[c] - rv[c]:>+5}"
            )
        lines.append("")
    return lines


def run():
    with open(SA_POP_PATH, newline="") as f:
        sa_rows = [
            (float(r["lat"]), float(r["lon"]), r["guid"], int(r["pop"]))
            for r in csv.DictReader(f)
        ]
    with sqlite3.connect(DB_PATH) as conn:
        rows = load_cases(conn)
    now = datetime.now(timezone.utc)
    base = county_months(rows, SmallAreaIndex(sa_rows), now)
    variants = {
        people: county_months(rows, NearestPeopleIndex(sa_rows, people), now)
        for people in PEOPLE
    }
    for line in report(base, variants):
        print(line)
