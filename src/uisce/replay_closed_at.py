"""Backfill cases.closed_at by replaying published DB snapshots.

A one-off historical repair, not a pipeline step. The feed publishes only a
case's *current* status, so the Open -> Closed transition is observable exactly
once, in the upsert (see load_cases). Every case that closed before closed_at
existed therefore carries NULL forever — except that each build publishes a
full uisce.db as a dated GitHub release, so those releases are a snapshot
series the transitions can be recovered from after the fact.

The recovered value means exactly what the forward path's does: the first
snapshot in which we observed the case no longer Open. Both are observation
time, not event time, so replayed and live rows are the same measurement and
can share a column. Resolution is the gap between builds (cron is Mon/Wed/Fri,
so <= 3 days, plus any missed runs).

Two limits are inherent and do not shrink with effort:

  * Cases that closed before the earliest snapshot are unrecoverable. At the
    time of writing that is 76% of closed cases — the releases start
    2026-06-30, collection began 2026-04-20.
  * Cases created *and* closed inside a single gap are never observed Open, so
    no transition exists to find (~12% of newly-appearing cases). This one
    applies to the live path too: "closed in month M" is a floor, not a count.

    uv run uisce-replay-closed-at --snapshots <dir>          # dry run
    uv run uisce-replay-closed-at --snapshots <dir> --write

Download the snapshots first; they are ~10-20MB each:

    for T in $(gh release list --limit 100 | cut -f1); do
        gh release download "$T" --pattern uisce.db -O "snaps/$T.db"
    done
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from uisce.config import DB_PATH

# Snapshot files are named for their release tag (YYYY-MM-DD.db), which is also
# the value written to closed_at, so replayed rows carry the date of the build
# that observed the closure.
SNAPSHOT_GLOB = "*.db"


def snapshot_files(directory):
    """Snapshot paths in tag order. Names are ISO dates, so lexical sort is
    chronological; anything else is a caller error rather than something to
    guess at."""
    paths = sorted(Path(directory).glob(SNAPSHOT_GLOB))
    if not paths:
        raise SystemExit(f"No {SNAPSHOT_GLOB} snapshots in {directory}")
    return [(p.stem, p) for p in paths]


def statuses(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return dict(conn.execute("SELECT id, status FROM cases"))


def replay(snapshots):
    """Walk the snapshots forward and record, per case, the tag of the first one
    in which a previously-Open case was no longer Open.

    A case must be *seen* Open first: a case that is already closed the first
    time it appears tells us nothing about when it closed. Reopening clears the
    stamp, matching the live upsert — otherwise a stale value would hide a
    currently-open case from any "open at end of month" query."""
    closed_at = {}
    seen_open = set()
    for tag, path in snapshots:
        for case_id, status in statuses(path).items():
            if status == "Open":
                seen_open.add(case_id)
                closed_at.pop(case_id, None)
            elif case_id in seen_open and case_id not in closed_at:
                closed_at[case_id] = tag
    return closed_at


def apply_stamps(closed_at, db_path, write):
    """Fill only rows that are still NULL and are not currently Open.

    Never overwrite: a live-path stamp is at least as precise as a replayed one,
    since the replay's resolution is the snapshot gap. Skipping currently-Open
    rows keeps the replay from resurrecting a closure the case has since been
    reopened past."""
    with sqlite3.connect(db_path) as conn:
        current = dict(conn.execute("SELECT id, status FROM cases"))
        existing = {
            case_id
            for (case_id,) in conn.execute(
                "SELECT id FROM cases WHERE closed_at IS NOT NULL"
            )
        }
        updates = [
            (tag, case_id)
            for case_id, tag in closed_at.items()
            if case_id in current
            and case_id not in existing
            and current[case_id] != "Open"
        ]
        if write:
            conn.executemany(
                "UPDATE cases SET closed_at = ? WHERE id = ?", updates
            )
    return updates, current


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshots", required=True,
        help="Directory of published uisce.db snapshots, named <release-tag>.db",
    )
    parser.add_argument("--db", default=DB_PATH, type=Path, help="DB to stamp")
    parser.add_argument(
        "--write", action="store_true",
        help="Apply the stamps. Without it, report what would change and exit.",
    )
    args = parser.parse_args(argv)

    snapshots = snapshot_files(args.snapshots)
    print(f"{len(snapshots)} snapshots: {snapshots[0][0]} -> {snapshots[-1][0]}")

    closed_at = replay(snapshots)
    updates, current = apply_stamps(closed_at, args.db, args.write)

    closed_total = sum(1 for s in current.values() if s != "Open")
    pct = 100 * len(updates) / closed_total if closed_total else 0
    print(f"transitions recovered  : {len(closed_at)}")
    print(f"rows to stamp          : {len(updates)} of {closed_total} closed ({pct:.0f}%)")
    print(f"unrecoverable          : {closed_total - len(updates)}")
    if not args.write:
        print("\nDry run — re-run with --write to apply.", file=sys.stderr)
