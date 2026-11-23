"""The data build's two checks that nothing else watches, written as issues.

    uv run uisce-check        # writes out/checks/*.md, one per finding

A finding is a file whose first line is an issue title and whose body says what
tripped and what to look at. scripts/open-check-issues.sh, run by the data
build, opens one issue per file unless an issue with that title already exists,
open or closed, so each occurrence is raised once. A warning in the build log
was declined for these: a line in a log is missed (owner, 2026-11-23).

- Cases the feed stopped serving in this build, over the share the download
  guard tolerates: the 2026-08-10 purge dropped 9,052 and was found a month
  later (notes/data-quality.md).
- The newest finished month's national rate outside NATIONAL_BAND: a prompt to
  check how notices are being published, not to re-fit the cuts
  (notes/statuspage-methodology.md, "Every supply notice per 100 km of main").
"""

import shutil
import sqlite3
from pathlib import Path
from typing import NamedTuple

import statusui

from uisce.config import DB_PATH
from uisce.eval_grading import NATIONAL_BAND
from uisce.pipeline import FEED_COUNT_TOLERANCE
from uisce.site import build_site, local_date, parse_dt, read_cases

CHECKS_DIR = Path("out/checks")
NOTES = "https://github.com/baz8080/uisce/blob/main/notes"


class Finding(NamedTuple):
    title: str
    body: str


def vanished_finding(conn, tolerance=FEED_COUNT_TOLERANCE):
    """Cases stamped vanished by the build that last read the feed, when they
    are more than `tolerance` of what the feed had been serving."""
    (stamp,) = conn.execute("SELECT MAX(last_seen) FROM cases").fetchone()
    if stamp is None:
        return None
    gone = conn.execute(
        "SELECT substr(start_date, 1, 7), status, COUNT(*) FROM cases "
        "WHERE vanished_at = ? GROUP BY 1, 2 ORDER BY 1, 2", (stamp,)
    ).fetchall()
    n = sum(count for _, _, count in gone)
    (served,) = conn.execute("SELECT COUNT(*) FROM cases WHERE vanished_at IS NULL").fetchone()
    if n <= tolerance * (served + n):
        return None
    still_open = sum(count for _, status, count in gone if status == "Open")
    by_month = {}
    for month, _, count in gone:
        by_month[month] = by_month.get(month, 0) + count
    rows = "\n".join(f"| {month or 'no start'} | {count:,} |" for month, count in by_month.items())
    day = local_date(parse_dt(stamp))
    return Finding(
        f"Data check: {n:,} cases vanished from the feed on {day}",
        f"The build that read the feed at `{stamp}` found {n:,} of the {served + n:,} cases "
        f"the feed had been serving gone from it: {n / (served + n):.1%}, against the "
        f"{tolerance:.0%} the download guard tolerates. {still_open:,} of them were still "
        f"`Open`.\n\n"
        f"They are stamped `vanished_at` and the site treats them as closed with no end. "
        f"Nothing was deleted from the archive.\n\n"
        f"| published in | cases gone |\n|---|---|\n{rows}\n\n"
        f"**What to check**\n\n"
        f"- Whether the feed dropped a date range, as it did on 2026-08-10, or cases across "
        f"the board: the table above.\n"
        f"- Whether the month pages changed: a purge of open cases closes them on the site "
        f"with no completion.\n"
        f"- [data-quality.md]({NOTES}/data-quality.md), \"The feed purged 9,052 cases on "
        f"2026-08-10\", for what the last one did and how it was handled.\n\n"
        f"Close this when it has been read. It is raised once for this build and not again.",
    )


def band_finding(site, band=NATIONAL_BAND):
    """The newest month seen whole, when its national rate is outside `band`."""
    whole = [ym for ym in site["months"]
             if site["national"][ym]["supply_per_100km"] is not None]
    if not whole:
        return None
    ym = whole[-1]
    month = site["national"][ym]
    rate = month["supply_per_100km"]
    if band[0] <= rate <= band[1]:
        return None
    recent = "\n".join(
        f"| {m} | {site['national'][m]['supply_notices']:,} | "
        f"{site['national'][m]['planned']:,} | {site['national'][m]['supply_per_100km']:.2f} |"
        for m in whole[-6:]
    )
    # each county against its own earlier months, to show whether one region moved
    movers = []
    for county, cdata in site["counties"].items():
        earlier = [cdata["months"][m]["supply_per_100km"] for m in whole[-4:-1]]
        if earlier:
            usual = sum(earlier) / len(earlier)
            now = cdata["months"][ym]
            movers.append((now["supply_per_100km"] - usual, county, usual, now))
    movers.sort(key=lambda mover: -abs(mover[0]))
    counties = "\n".join(
        f"| {county} | {usual:.2f} | {now['supply_per_100km']:.2f} | "
        f"{now['supply_notices']:,} | {now['planned']:,} |"
        for _, county, usual, now in movers[:6]
    )
    label = statusui.month_label(ym)
    return Finding(
        f"Data check: national rate of {rate:.2f} in {ym} is outside "
        f"{band[0]:g} to {band[1]:g}",
        f"{label} closed at {rate:.2f} supply notices per 100 km of water main nationally "
        f"({month['supply_notices']:,} notices, {month['planned']:,} of them planned), "
        f"outside the {band[0]:g} to {band[1]:g} the months before it kept to.\n\n"
        f"This is a prompt to check how notices are being published, **not** to re-fit the "
        f"letter's cuts. The count moves with publishing practice: a region that starts "
        f"announcing a week of works as a notice a day, or stops publishing investigations, "
        f"shifts every letter with no change in service. A hard month is what the bands "
        f"above the record are for.\n\n"
        f"| month | supply notices | planned | per 100 km |\n|---|---|---|---|\n{recent}\n\n"
        f"The counties furthest from their own previous three months:\n\n"
        f"| county | usual rate | {ym} | supply notices | planned |\n|---|---|---|---|---|\n"
        f"{counties}\n\n"
        f"**What to check**\n\n"
        f"- Is the move in a few counties or all of them? One region changing how it "
        f"publishes shows as a few rows above; weather shows as most of them.\n"
        f"- Is it in the planned share? Compare the planned column with the months before.\n"
        f"- `uv run uisce-eval-grading` prints the repeated planned works and the "
        f"investigations beside an outage notice, the two places a publishing change shows.\n"
        f"- [statuspage-methodology.md]({NOTES}/statuspage-methodology.md), \"Every supply "
        f"notice per 100 km of main\", for the rule.\n\n"
        f"Close this when it has been read. It is raised once for {label} and not again.",
    )


def findings(db_path=DB_PATH):
    with sqlite3.connect(db_path) as conn:
        vanished = vanished_finding(conn)
    rows, horizon = read_cases(db_path)
    band = band_finding(build_site(rows, horizon, data_as_of=horizon))
    return [finding for finding in (vanished, band) if finding is not None]


def run():
    shutil.rmtree(CHECKS_DIR, ignore_errors=True)
    found = findings()
    if not found:
        print("No data check tripped")
        return
    CHECKS_DIR.mkdir(parents=True)
    for i, finding in enumerate(found, 1):
        (CHECKS_DIR / f"{i}.md").write_text(f"{finding.title}\n\n{finding.body}\n")
        print(finding.title)
