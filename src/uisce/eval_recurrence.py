"""Review the recurrence calls that actually change a published figure.

The window fields sit outside the end-time eval harness (see
notes/end-time-eval.md), so this stands in for a sample instead: it enumerates
every call that flips an answer, rather than drawing one.

  downgraded — the recurrence rule turned an outage into a restriction, so a
               wrong "daily" here erases a real outage from the index entirely
  charged    — the notice's own text describes a repeating window but no window
               was extracted, so a nightly regime is being charged as one
               continuous outage (see notes/data-quality.md, "Recurring
               windows were charged as continuous outages")

Sorted by the person-hours at stake so a partial pass still covers most of the
exposure. Re-run after any prompt change or corpus run.
"""

import argparse
import csv
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from uisce.config import DB_PATH, RECURRING, SA_POP_PATH
from uisce.site import (
    COLLECTION_START,
    COUNTY_POP,
    SmallAreaIndex,
    case_ref,
    classify,
    collect_lifts,
    describes_recurrence,
    event_windows,
    load_cases,
    merge,
    month_bounds,
    month_list,
    recurring_events,
    resolve_case,
    union_seconds,
)

REVIEW_DIR = Path("data/eval")
REVIEW_GLOB = "recurrence_review*.csv"

FIELDNAMES = [
    "case_id", "reference_num", "county", "title", "pins", "effect", "person_h",
    "text_says_recurring", "model_says_recurring", "model_window",
    "human_verdict", "human_window", "human_notes", "description",
]


def plain(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())


def consequential(db_path=DB_PATH, now=None):
    """Every event whose recurrence call changes a published figure, worst first."""
    now = now or datetime.now(timezone.utc)
    sa_index = SmallAreaIndex.from_csv(SA_POP_PATH)
    with sqlite3.connect(db_path) as conn:
        rows = load_cases(conn)
        descriptions = dict(conn.execute("SELECT id, description FROM cases"))

    lifts = collect_lifts(rows)
    shared = event_windows(rows)
    recurring = recurring_events(rows, shared)

    events = defaultdict(lambda: {"iv": [], "sas": {}, "ids": [], "window": None})
    for r in rows:
        key = (r["county"], case_ref(r))
        case = resolve_case(r, sa_index, lifts, now, shared.get(key), key in recurring)
        if case is None:
            continue
        event = events[key]
        event["iv"].extend(case.intervals)
        event["sas"].update(case.sas)
        event["ids"].append(r["id"])
        event["sev"] = case.sev
        # what the class would be if recurrence were never consulted
        event["plain_sev"] = classify(r, recurring=False)
        event["title"] = r["title"]
        # across every pin, not just the last: a multi-pin event states the
        # window in the notice that announced it and not in the one that
        # reported completion, and either is enough to want a human to look
        text = plain(descriptions.get(r["id"]))
        event["says_recurring"] = event.get("says_recurring") or describes_recurrence(text)
        if len(text) > len(event.get("text") or ""):
            event["text"] = text
        if r["end_recurrence"] == RECURRING:
            event["window"] = (r["end_window_open"], r["end_window_close"],
                               r["end_window_first_date"])
        elif shared.get(key) and event["window"] is None:
            event["window"] = shared[key]

    months = month_list(COLLECTION_START, now)
    out = []
    for (county, ref), e in events.items():
        downgraded = e["plain_sev"] == "outage" and e["sev"] == "degraded"
        missed = e["sev"] == "outage" and e["says_recurring"]
        if not (downgraded or missed):
            continue
        merged = merge(e["iv"])
        person_h = sum(
            union_seconds(merged, lo, min(hi, now)) * min(sum(e["sas"].values()),
                                                          COUNTY_POP[county]) / 3600
            for lo, hi in (month_bounds(ym) for ym in months)
        )
        out.append({
            "case_id": min(e["ids"]),
            "reference_num": ref,
            "county": county,
            "title": e["title"],
            "pins": len(e["ids"]),
            "effect": "downgraded to restriction" if downgraded else "charged as outage",
            "person_h": round(person_h),
            "text_says_recurring": "yes" if e["says_recurring"] else "no",
            "model_says_recurring": "yes" if e["window"] else "no",
            "model_window": (f"{e['window'][0]}-{e['window'][1]} from {e['window'][2]}"
                             if e["window"] else ""),
            "human_verdict": "",
            "human_window": "",
            "human_notes": "",
            "description": e["text"],
        })
    out.sort(key=lambda r: -r["person_h"])
    return out


def unique_review_path(day, directory=REVIEW_DIR):
    """A path that does not exist yet, suffixing _r2, _r3 on repeat runs.

    A review file is hand-labelled, so overwriting one silently destroys work
    that cannot be regenerated. Re-running on the same day is the normal case —
    you fix a rule and want to see what moved — so it has to be safe.
    """
    path = directory / f"recurrence_review_{day}.csv"
    n = 1
    while path.exists():
        n += 1
        path = directory / f"recurrence_review_{day}_r{n}.csv"
    return path


def review(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    records = consequential()
    day = datetime.now(timezone.utc).date().isoformat()
    path = args.out or unique_review_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    at_stake = sum(r["person_h"] for r in records)
    disagree = [r for r in records if r["text_says_recurring"] != r["model_says_recurring"]]
    print(f"Wrote {path} — {len(records)} event(s), {at_stake:,} person-hours at stake")
    for effect in ("downgraded to restriction", "charged as outage"):
        sel = [r for r in records if r["effect"] == effect]
        if sel:
            print(f"  {len(sel):>3} {effect:<26} {sum(r['person_h'] for r in sel):>10,} person-h")
    print(f"  {len(disagree)} row(s) where the text and the model disagree — read those first")


def score(argv=None):
    """Report the verdicts on a reviewed file."""
    parser = argparse.ArgumentParser(description=score.__doc__)
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args(argv)
    path = args.csv or max(REVIEW_DIR.glob(REVIEW_GLOB), key=lambda p: p.stat().st_mtime)

    rows = list(csv.DictReader(open(path)))
    done = [r for r in rows if r["human_verdict"].strip()]
    print(f"{path}: {len(done)} of {len(rows)} row(s) reviewed")
    if not done:
        print("  Nothing labelled yet. Fill human_verdict with 'correct' or 'wrong'.")
        return

    for verdict in ("correct", "wrong"):
        sel = [r for r in done if r["human_verdict"].strip().lower() == verdict]
        if sel:
            ph = sum(int(r["person_h"]) for r in sel)
            print(f"  {verdict:<8} {len(sel):>3} event(s), {ph:>10,} person-hours")
    wrong = [r for r in done if r["human_verdict"].strip().lower() == "wrong"]
    if wrong:
        print("\n  Calls to fix:")
        for r in wrong:
            print(f"    {r['reference_num'] or r['case_id']} ({r['county']}) — {r['effect']}, "
                  f"{int(r['person_h']):,} person-h")
            if r["human_notes"]:
                print(f"      {r['human_notes']}")
    unreviewed = len(rows) - len(done)
    if unreviewed:
        remaining = sum(int(r["person_h"]) for r in rows if not r["human_verdict"].strip())
        print(f"\n  {unreviewed} row(s) left, {remaining:,} person-hours unreviewed")
