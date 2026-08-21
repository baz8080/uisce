"""Shadow-eval the rules extractor against the LLM's whole recorded corpus.

The labelled rounds are 234 rows; this is the other half of the evidence.
Every case in data/inferred_end_times.jsonl already carries the LLM's answer,
so running uisce.rules over the same descriptions measures coverage (how much
of the corpus the rules answer at all) and agreement (how often the two
extractors say the same thing) across ~11k cases — no GPU and no new
labelling. Agreement is not truth: every disagreement is written to a CSV for
human adjudication, which is where truth gets decided. See
notes/rules-vs-llm-end-times.md for the acceptance criteria this feeds.

    uv run uisce-eval-rules-shadow

Cases whose description hash no longer matches the record's are skipped and
counted: the DB refreshes twice daily, so it can be newer than the last
inference run, and comparing extractors over different texts measures nothing.
"""

import csv
import json
import sqlite3
import time
from datetime import date

from uisce.build import latest_per_case
from uisce.config import DB_PATH, JSONL_PATH
from uisce.eval_end_time import EVAL_DIR
from uisce.eval_replay import normalise_time
from uisce.inference import hash_description
from uisce.rules import RULES_VERSION, extract

SHADOW_FIELDNAMES = [
    "case_id", "kind",
    "llm_end_source", "llm_local_date", "llm_local_time", "llm_recurrence",
    "rules_end_source", "rules_local_date", "rules_local_time", "rules_notes",
    "description",
]


def fields_of(record):
    return (
        (record.get("end_source") or "").strip(),
        (record.get("local_date") or "").strip(),
        normalise_time(record.get("local_time")),
    )


def compare(llm_record, rules_result):
    """One of "abstain", "agree", "disagree", "recurrence" for a joined case.

    A rules answer on a case the LLM read as a recurring window is its own
    bucket: the three compared fields can even agree there, but the rules
    version of the case would drop the window the site expands, so it counts
    against the rules, not as agreement.
    """
    if rules_result is None:
        return "abstain"
    if (llm_record.get("recurrence") or "none") != "none":
        return "recurrence"
    return "agree" if fields_of(llm_record) == fields_of(rules_result) else "disagree"


def run(argv=None):
    records = latest_per_case(
        json.loads(line)
        for line in open(JSONL_PATH)
        if line.strip()
    )
    by_case = {record["case_id"]: record for record in records}

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, start_date, description FROM cases WHERE description IS NOT NULL"
    ).fetchall()
    conn.close()

    started = time.monotonic()
    stale = never_inferred = 0
    outcomes = {"abstain": [], "agree": [], "disagree": [], "recurrence": []}
    for case_id, start_date, description in rows:
        record = by_case.get(case_id)
        if record is None:
            never_inferred += 1
            continue
        if record["description_hash"] != hash_description(description):
            stale += 1
            continue
        result = extract(start_date, description)
        outcomes[compare(record, result)].append((case_id, record, result, description))
    elapsed = time.monotonic() - started

    compared = sum(len(v) for v in outcomes.values())
    answered = compared - len(outcomes["abstain"])
    print(f"{RULES_VERSION} over {compared} cases in {elapsed:.1f}s "
          f"({stale} stale-hash skipped, {never_inferred} never inferred)")
    print(f"Coverage: {answered}/{compared} answered ({100 * answered / compared:.1f}%)")
    agree = len(outcomes["agree"])
    print(f"Agreement on answered: {agree}/{answered} ({100 * agree / answered:.2f}%) — "
          f"{len(outcomes['disagree'])} disagree, "
          f"{len(outcomes['recurrence'])} on LLM-recurring cases")

    per_class = {}
    for kind, cases in outcomes.items():
        for _, record, _, _ in cases:
            source = record.get("end_source") or "?"
            per_class.setdefault(source, {"agree": 0, "disagree": 0,
                                          "recurrence": 0, "abstain": 0})[kind] += 1
    print(f"\n{'LLM end_source':<26} {'agree':>7} {'disagree':>9} "
          f"{'recurring':>10} {'abstain':>8} {'coverage':>9}")
    for source in sorted(per_class):
        c = per_class[source]
        n = sum(c.values())
        answered_class = n - c["abstain"]
        print(f"{source:<26} {c['agree']:>7} {c['disagree']:>9} "
              f"{c['recurrence']:>10} {c['abstain']:>8} "
              f"{100 * answered_class / n:>8.1f}%")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"rules_shadow_{date.today().isoformat()}.csv"
    disputed = outcomes["disagree"] + outcomes["recurrence"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHADOW_FIELDNAMES)
        writer.writeheader()
        for kind in ("disagree", "recurrence"):
            for case_id, record, result, description in outcomes[kind]:
                writer.writerow({
                    "case_id": case_id,
                    "kind": kind,
                    "llm_end_source": record.get("end_source") or "",
                    "llm_local_date": record.get("local_date") or "",
                    "llm_local_time": record.get("local_time") or "",
                    "llm_recurrence": record.get("recurrence") or "none",
                    "rules_end_source": result.get("end_source") or "",
                    "rules_local_date": result.get("local_date") or "",
                    "rules_local_time": result.get("local_time") or "",
                    "rules_notes": result.get("notes") or "",
                    "description": description,
                })
    print(f"\n{len(disputed)} disputed cases written to {out_path}")
