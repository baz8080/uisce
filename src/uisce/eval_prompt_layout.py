"""Time and score the system/user prompt split against the current single user message.

    uv run uisce-eval-prompt-layout --limit 3 --rounds 1   # smoke test
    uv run uisce-eval-prompt-layout                        # 2 rounds, every residue row

Runs the labelled rows the rules abstain on (what the LLM gets in production)
through both layouts. Each layout runs as one warm sequential block after a
discarded warm-up call, because the layouts have different prefixes and
interleaving them per row would time a cold prefill nobody pays. Round order
alternates so drift does not favour whichever layout goes first. Keep everything
else off the LM Studio server while it runs.
"""

import argparse
import csv
import random
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from uisce.config import make_session
from uisce.eval_end_time import round_files
from uisce.eval_replay import replay_row, truth_for
from uisce.inference import LLM_TIMEOUT, MODEL_URL, PROMPT, build_payload, parse_response
from uisce.rules import extract as rules_extract

LAYOUTS = ("user", "split")
OUT_DIR = Path("out")
FIELDNAMES = [
    "round", "layout", "case_id", "seconds", "prompt_tokens", "completion_tokens",
    "verdict", "answer", "error",
]


def split_payload(payload):
    """The same request with the instructions moved into a system message."""
    (message,) = payload["messages"]
    body = message["content"]
    if not body.startswith(PROMPT):
        raise ValueError("payload does not start with PROMPT, so it cannot be split")
    return payload | {"messages": [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": body[len(PROMPT):].lstrip("\n")},
    ]}


def payload_for(layout, start_date, description):
    payload = build_payload(start_date, description)
    return split_payload(payload) if layout == "split" else payload


def residue_rows():
    """Labelled rows the rules abstain on, one per distinct description."""
    seen, rows = set(), []
    for path in round_files():
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if "human_verdict" not in (reader.fieldnames or ()):
                continue
            for row in reader:
                verdict = row["human_verdict"].strip().lower()
                if not verdict or verdict == "unsure" or row["description"] in seen:
                    continue
                if rules_extract(row["start_date"], row["description"]) is None:
                    seen.add(row["description"])
                    rows.append(row)
    return rows


def timed_call(session, layout, row):
    payload = payload_for(layout, row["start_date"], row["description"])
    started = time.perf_counter()
    resp = session.post(MODEL_URL, json=payload, timeout=LLM_TIMEOUT)
    seconds = time.perf_counter() - started
    resp.raise_for_status()
    body = resp.json()
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ValueError("response truncated")
    usage = body.get("usage") or {}
    result = parse_response(choice["message"]["content"])
    answer = replay_row(lambda *_: result, row)[:3]
    return seconds, usage.get("prompt_tokens"), usage.get("completion_tokens"), answer


def run_block(session, layout, rows, rnd, writer):
    try:
        timed_call(session, layout, rows[0])
    except Exception as exc:  # the warm-up only primes the cache
        print(f"  warm-up failed ({exc}); continuing")
    records = []
    for row in rows:
        seconds = prompt_tokens = completion_tokens = answer = None
        error = ""
        try:
            seconds, prompt_tokens, completion_tokens, answer = timed_call(session, layout, row)
        except Exception as exc:  # a failed call is a miss, not a crash
            error = str(exc)
        record = {
            "round": rnd, "layout": layout, "case_id": row["case_id"], "seconds": seconds,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "answer": answer, "error": error,
            "verdict": "error" if error else "match" if answer == truth_for(row) else "miss",
        }
        records.append(record)
        writer.writerow(record)
    return records


def bootstrap_ci(deltas, resamples=2000, seed=0):
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choices(deltas, k=len(deltas))) for _ in range(resamples)
    )
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def summarise(records):
    def ok(layout, rnd=None):
        return [r for r in records if r["layout"] == layout and not r["error"]
                and (rnd is None or r["round"] == rnd)]

    print(f"\n{'layout':<8} {'round':>5} {'n':>4} {'median s':>9} {'mean s':>7} {'p90 s':>7} "
          f"{'prompt tok':>10} {'compl tok':>9} {'right':>6}")
    for layout in LAYOUTS:
        rounds = sorted({r["round"] for r in records if r["layout"] == layout})
        for rnd in [*rounds, None]:
            rows = ok(layout, rnd)
            if not rows:
                continue
            secs = sorted(r["seconds"] for r in rows)
            right = sum(r["verdict"] == "match" for r in rows)
            print(f"{layout:<8} {('all' if rnd is None else rnd):>5} {len(rows):>4} "
                  f"{statistics.median(secs):>9.2f} {statistics.fmean(secs):>7.2f} "
                  f"{secs[int(0.9 * (len(secs) - 1))]:>7.2f} "
                  f"{statistics.fmean(r['prompt_tokens'] for r in rows):>10.0f} "
                  f"{statistics.fmean(r['completion_tokens'] for r in rows):>9.1f} "
                  f"{right:>3}/{len(rows):<2}")

    by_key = {(r["layout"], r["round"], r["case_id"]): r for r in records if not r["error"]}
    pairs = [(by_key[("user", rnd, cid)], by_key[("split", rnd, cid)])
             for (layout, rnd, cid) in by_key
             if layout == "user" and ("split", rnd, cid) in by_key]
    if not pairs:
        print("\nNo case answered under both layouts; nothing to compare.")
        return
    # Rounds repeat the same cases, so the CI resamples cases, not (round, case) pairs.
    per_case = {}
    for u, s in pairs:
        per_case.setdefault(u["case_id"], []).append(s["seconds"] - u["seconds"])
    deltas = [statistics.fmean(d) for d in per_case.values()]
    lo, hi = bootstrap_ci(deltas)
    faster = sum(d < 0 for d in deltas)
    tok = statistics.fmean(s["completion_tokens"] - u["completion_tokens"] for u, s in pairs)
    print(f"\nPaired over {len(deltas)} cases ({len(pairs)} pairs), split minus user:")
    print(f"  seconds: mean {statistics.fmean(deltas):+.2f}  median "
          f"{statistics.median(deltas):+.2f}  95% CI of the mean [{lo:+.2f}, {hi:+.2f}]  "
          f"split faster in {faster}/{len(deltas)} cases")
    print(f"  completion tokens: mean {tok:+.1f}   prompt tokens: mean "
          f"{statistics.fmean(s['prompt_tokens'] - u['prompt_tokens'] for u, s in pairs):+.1f}")
    differ = sum(u["answer"] != s["answer"] for u, s in pairs)
    print(f"  answers that differ between layouts: {differ}/{len(pairs)}")
    print("  A CI straddling zero means no measured speed difference.")


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=2,
                        help="passes over the corpus per layout; order alternates (default 2)")
    parser.add_argument("--limit", type=int, default=None, help="use only the first N rows")
    parser.add_argument("--out", type=Path, default=None, help="per-call CSV to write")
    args = parser.parse_args(argv)

    rows = residue_rows()[: args.limit]
    if not rows:
        sys.exit("No labelled rows the rules abstain on; run uisce-eval-sample first.")
    out_path = args.out or OUT_DIR / f"prompt_layout_{date.today().isoformat()}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"{len(rows)} rows x {len(LAYOUTS)} layouts x {args.rounds} rounds -> {out_path}")

    session = make_session()
    records = []
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for rnd in range(args.rounds):
            for layout in (LAYOUTS if rnd % 2 == 0 else reversed(LAYOUTS)):
                print(f"round {rnd}: {layout}")
                records += run_block(session, layout, rows, rnd, writer)
                f.flush()
    summarise(records)
    print(f"\nPer-call results: {out_path}")
