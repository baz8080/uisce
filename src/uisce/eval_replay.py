"""Replay an extraction backend over an already-labelled eval round.

Step 2 of the pv2 workflow in notes/end-time-eval.md: re-run an extractor
over every description in a labelled round file and score against the human
labels it already carries — no human time needed, so a prompt or rule edit
can be measured before any re-inference of the corpus. Ground truth per row
matches uisce-eval-score; see notes/end-time-eval.md for the definition.

    uv run uisce-eval-replay                 # newest round file, LLM backend
    uv run uisce-eval-replay --extractor rules
    uv run uisce-eval-replay --csv <path> --out <path>

--extractor rules replays uisce.rules.extract instead of the LLM. The rules
backend may abstain; an abstained row counts toward coverage, not accuracy,
because the caller falls back to the LLM for it (see rules.py).

Results are written to a replay CSV alongside the round file so the misses can
be read case by case, and a summary is printed in the same shape as
uisce-eval-score for direct comparison.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from uisce.config import make_session
from uisce.eval_end_time import EVAL_DIR, round_files
from uisce.inference import MODEL_NAME, PROMPT_VERSION, call_llm, parse_response
from uisce.rules import RULES_VERSION
from uisce.rules import extract as rules_extract

REPLAY_FIELDNAMES = [
    "case_id", "verdict",
    "truth_end_source", "truth_local_date", "truth_local_time",
    "replay_end_source", "replay_local_date", "replay_local_time",
    "replay_notes", "error",
]


def normalise_time(value):
    """Compare times at minute precision; the human labels sometimes carry seconds."""
    value = (value or "").strip()
    return value[:5] if len(value) >= 5 else value


def truth_for(row):
    """The human's answer: their corrections when incorrect, else the endorsed model fields.

    On an `incorrect` row the labeller fills only the fields that were wrong and leaves
    the rest blank — "the other model fields were correct", as round 1's notes put it.
    So each field falls back to the model's own value independently; reading a blank as
    an empty-string truth would score a corrected row as a miss no matter what the
    prompt answers.
    """
    if row["human_verdict"].strip().lower() == "incorrect":
        return (
            (row["human_end_source"].strip() or row["model_end_source"].strip()),
            (row["human_local_date"].strip() or (row["model_local_date"] or "").strip()),
            (normalise_time(row["human_local_time"]) or normalise_time(row["model_local_time"])),
        )
    return (
        row["model_end_source"].strip(),
        (row["model_local_date"] or "").strip(),
        normalise_time(row["model_local_time"]),
    )


def matches(truth, got):
    return truth == got


def replay_row(extractor, row):
    """One extractor answer as (source, date, time, notes), or None to abstain."""
    result = extractor(row["start_date"], row["description"])
    if result is None:
        return None
    return (
        (result.get("end_source") or "").strip(),
        (result.get("local_date") or "").strip(),
        normalise_time(result.get("local_time")),
        result.get("notes") or "",
    )


def summarise(records):
    """Per-truth-class and overall accuracy, mirroring uisce-eval-score's table.

    Accuracy is over answered rows only; abstentions are shown beside them
    because an abstained row costs coverage, not correctness — the caller
    falls back to the LLM for it. The LLM backend never abstains, so its
    table reads exactly as before the column existed.
    """
    per_class = defaultdict(Counter)
    for rec in records:
        outcome = ("abstain" if rec.get("abstained")
                   else "correct" if rec["match"] else "incorrect")
        per_class[rec["truth"][0]][outcome] += 1

    total = Counter()
    print(f"\n{'end_source (human truth)':<26} {'correct':>8} {'incorrect':>10} "
          f"{'abstain':>8} {'accuracy':>9}")
    for source in sorted(per_class):
        counts = per_class[source]
        total.update(counts)
        judged = counts["correct"] + counts["incorrect"]
        acc = f"{100 * counts['correct'] / judged:.0f}%" if judged else "n/a"
        print(f"{source:<26} {counts['correct']:>8} {counts['incorrect']:>10} "
              f"{counts['abstain']:>8} {acc:>9}")
    judged = total["correct"] + total["incorrect"]
    acc = f"{100 * total['correct'] / judged:.1f}%" if judged else "n/a"
    print(f"{'TOTAL':<26} {total['correct']:>8} {total['incorrect']:>10} "
          f"{total['abstain']:>8} {acc:>9}")
    if total["abstain"]:
        answered = judged
        print(f"Coverage: {answered}/{len(records)} answered "
              f"({100 * answered / len(records):.1f}%), accuracy on answered {acc}")


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None,
                        help="Labelled round file to replay (default: newest in data/eval)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Where to write the replay results CSV")
    parser.add_argument("--limit", type=int, default=None,
                        help="Replay only the first N labelled rows (smoke test)")
    parser.add_argument("--extractor", choices=("llm", "rules"), default="llm",
                        help="Extraction backend to replay (default: llm)")
    args = parser.parse_args(argv)

    path = args.csv
    if path is None:
        rounds = round_files()
        if not rounds:
            sys.exit(f"No round files in {EVAL_DIR} — run uisce-eval-sample first.")
        path = max(rounds, key=lambda p: p.stat().st_mtime)

    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["human_verdict"].strip()]
    rows = [r for r in rows if r["human_verdict"].strip().lower() != "unsure"]
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        sys.exit(f"No labelled rows in {path} — nothing to replay.")

    if args.extractor == "rules":
        backend_label = RULES_VERSION
        extractor = rules_extract
    else:
        backend_label = f"{MODEL_NAME}_pv{PROMPT_VERSION}"
        session = make_session()

        def extractor(start_date, description):
            return parse_response(call_llm(session, start_date, description))

    out_path = args.out or path.with_name(path.stem + f"_replay_{backend_label}.csv")
    print(f"Replaying {len(rows)} labelled rows from {path}")
    print(f"  extractor {backend_label} -> {out_path}")

    records = []
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPLAY_FIELDNAMES)
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            truth = truth_for(row)
            abstained = False
            try:
                answer = replay_row(extractor, row)
                if answer is None:
                    abstained = True
                    source = local_date = local_time = notes = ""
                else:
                    source, local_date, local_time, notes = answer
                error = ""
            except Exception as exc:  # a failed call is a miss, not a crash
                source = local_date = local_time = notes = ""
                error = str(exc)
            got = (source, local_date, local_time)
            match = not error and not abstained and matches(truth, got)
            records.append({"truth": truth, "match": match, "abstained": abstained})
            writer.writerow({
                "case_id": row["case_id"],
                "verdict": "abstain" if abstained else "match" if match else "miss",
                "truth_end_source": truth[0],
                "truth_local_date": truth[1],
                "truth_local_time": truth[2],
                "replay_end_source": source,
                "replay_local_date": local_date,
                "replay_local_time": local_time,
                "replay_notes": notes,
                "error": error,
            })
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(rows)} replayed")

    summarise(records)
    print(f"\nPer-row results: {out_path}")
    print("Compare against the pv1 headline in notes/end-time-eval.md.")
