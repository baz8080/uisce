"""Human evaluation of the LLM end-time extraction.

uisce-eval-sample draws a stratified random sample of inferred cases into a
new round file, data/eval/end_time_sample_<date>_<model>_pv<N>.csv, carrying
the model and prompt version that produced each sampled output. Cases drawn
in earlier rounds are excluded, so each round extends coverage. A human fills
in the human_* columns (see notes/end-time-eval.md for the labelling guide),
then uisce-eval-score reports accuracy overall and per end_source class,
defaulting to the newest round file. Labelled rounds are committed so the
published accuracy numbers are reproducible.
"""

import argparse
import csv
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from uisce.config import DB_PATH, make_session
from uisce.inference import (
    MODEL_NAME,
    PROMPT_VERSION,
    call_llm,
    hash_description,
    parse_response,
)

EVAL_DIR = Path("data/eval")
ROUND_GLOB = "end_time_sample*.csv"

# Oversample minority classes so per-class error rates mean something.
QUOTAS = {
    "completion_update": 40,
    "scheduled_end_with_time": 30,
    "scheduled_end_date_only": 15,
    "not_found": 20,
    "lifted_immediate": 15,
}

FIELDNAMES = [
    "case_id", "county", "title", "start_date", "model", "prompt_version",
    "model_end_source", "model_local_date", "model_local_time",
    "human_verdict", "human_end_source", "human_local_date", "human_local_time",
    "human_notes", "description",
]


def draw_sample(rows, quotas, seed, exclude_ids=frozenset()):
    """Stratified sample, one row per unique description hash per class."""
    rng = random.Random(seed)
    by_source = defaultdict(list)
    seen_hashes = set()
    for row in rows:
        if row["case_id"] in exclude_ids:
            continue
        if row["end_description_hash"] in seen_hashes:
            continue
        seen_hashes.add(row["end_description_hash"])
        by_source[row["end_source"]].append(row)

    sample = []
    for source, quota in quotas.items():
        pool = by_source.get(source, [])
        rng.shuffle(pool)
        sample.extend(pool[:quota])
    return sample


def draw_uniform(rows, size, seed, exclude_ids=frozenset(), hash_of=None):
    """Uniform sample, one row per unique description.

    Used by the sample-then-infer path, where end_source is not known before the
    model runs and so cannot be stratified on. A uniform draw reproduces the
    corpus's own class mix, which is what a corpus-wide accuracy estimate needs;
    the stratified draw above deliberately does not.
    """
    rng = random.Random(seed)
    seen_hashes = set()
    pool = []
    for row in rows:
        if row["id"] in exclude_ids:
            continue
        digest = hash_of(row["description"])
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        pool.append(row)
    rng.shuffle(pool)
    return pool[:size]


def round_filename(day, models, versions):
    """One CSV per labelling round, named for what produced the sampled outputs."""
    model = next(iter(models)) if len(models) == 1 else "mixed"
    version = next(iter(versions)) if len(versions) == 1 else "mixed"
    return f"end_time_sample_{day.isoformat()}_{model}_pv{version}.csv"


def unique_round_path(day, models, versions):
    """Round files are never overwritten; suffix _r2, _r3 ... if the name is taken."""
    base = round_filename(day, models, versions)
    out_path = EVAL_DIR / base
    n = 1
    while out_path.exists():
        n += 1
        out_path = EVAL_DIR / base.replace(".csv", f"_r{n}.csv")
    return out_path


def write_round(out_path, records):
    """Write a round file: the model's three fields, then blank human_* columns to fill."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "human_verdict": "",
                "human_end_source": "",
                "human_local_date": "",
                "human_local_time": "",
                "human_notes": "",
                **rec,
            })


def round_files():
    return sorted(EVAL_DIR.glob(ROUND_GLOB)) if EVAL_DIR.exists() else []


def previously_sampled_ids():
    """Case ids drawn in any earlier round — never re-ask the labeller about them."""
    ids = set()
    for path in round_files():
        with open(path, newline="") as f:
            ids.update(int(row["case_id"]) for row in csv.DictReader(f))
    return ids


def sample(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    args = parser.parse_args(argv)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT i.case_id, i.end_description_hash, i.end_source,
                   i.end_local_date, i.end_local_time,
                   i.end_model, i.end_prompt_version,
                   c.county, c.title, c.start_date, c.description
            FROM inferred_cases i JOIN cases c ON c.id = i.case_id
            ORDER BY i.case_id
            """
        ).fetchall()

    exclude = previously_sampled_ids()
    picked = draw_sample(rows, QUOTAS, args.seed, exclude)
    if not picked:
        sys.exit("Nothing left to sample — all eligible cases appear in earlier rounds.")

    models = {row["end_model"] for row in picked}
    versions = {row["end_prompt_version"] for row in picked}
    out_path = unique_round_path(date.today(), models, versions)

    write_round(out_path, [
        {
            "case_id": row["case_id"],
            "county": row["county"],
            "title": row["title"],
            "start_date": row["start_date"],
            "model": row["end_model"],
            "prompt_version": row["end_prompt_version"],
            "model_end_source": row["end_source"],
            "model_local_date": row["end_local_date"] or "",
            "model_local_time": row["end_local_time"] or "",
            "description": row["description"],
        }
        for row in picked
    ])

    counts = Counter(row["end_source"] for row in picked)
    print(f"Wrote {len(picked)} rows to {out_path} (seed {args.seed}, "
          f"{len(exclude)} previously sampled cases excluded)")
    for source, n in sorted(counts.items()):
        print(f"  {source}: {n}")
    print("Label per notes/end-time-eval.md, then run: uv run uisce-eval-score")


def sample_fresh(argv=None):
    """Draw N unseen cases and infer only those — a fresh round without a corpus run.

    uisce-eval-sample draws from inferred_cases, so measuring a new prompt on unseen
    cases would mean re-inferring all ~7,500 first. This path inverts that: sample
    from `cases`, run the current prompt over just the sampled rows, and write the
    round from those answers. N calls instead of the whole corpus.

    The cost is stratification. end_source is not known until the model has run, so
    minority classes cannot be oversampled and rare ones may land few rows or none.
    In exchange the draw is uniform, so the round reflects the corpus's real class
    mix and its headline number is an unbiased corpus-wide estimate — which the
    stratified rounds, by design, are not.
    """
    parser = argparse.ArgumentParser(description=sample_fresh.__doc__)
    parser.add_argument("-n", "--size", type=int, default=120,
                        help="Number of unseen cases to draw and infer (default 120)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    args = parser.parse_args(argv)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, county, title, start_date, description
            FROM cases WHERE description IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    exclude = previously_sampled_ids()
    picked = draw_uniform(rows, args.size, args.seed, exclude, hash_of=hash_description)
    if not picked:
        sys.exit("Nothing left to sample — all eligible cases appear in earlier rounds.")

    print(f"Inferring {len(picked)} unseen cases with prompt v{PROMPT_VERSION}, "
          f"model {MODEL_NAME} ({len(exclude)} previously sampled cases excluded)")

    session = make_session()
    records = []
    for i, row in enumerate(picked, 1):
        try:
            result = parse_response(call_llm(session, row["start_date"], row["description"]))
            source = result.get("end_source") or ""
            local_date = result.get("local_date") or ""
            local_time = result.get("local_time") or ""
        except Exception as exc:  # a failed call still gets a row, flagged for the labeller
            print(f"  case {row['id']} failed: {exc}")
            source, local_date, local_time = "", "", ""
        records.append({
            "case_id": row["id"],
            "county": row["county"],
            "title": row["title"],
            "start_date": row["start_date"],
            "model": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "model_end_source": source,
            "model_local_date": local_date,
            "model_local_time": local_time,
            "description": row["description"],
        })
        if i % 10 == 0:
            print(f"  {i}/{len(picked)} inferred")

    out_path = unique_round_path(date.today(), {MODEL_NAME}, {PROMPT_VERSION})
    write_round(out_path, records)

    counts = Counter(rec["model_end_source"] for rec in records)
    print(f"\nWrote {len(records)} rows to {out_path} (seed {args.seed}, uniform draw)")
    for source, n in sorted(counts.items()):
        print(f"  {source or '(failed)'}: {n}")
    print("Label per notes/end-time-eval.md, then run: uv run uisce-eval-score")


def score(argv=None):
    parser = argparse.ArgumentParser(description="Score a labelled end-time eval CSV")
    parser.add_argument("--csv", type=Path, default=None,
                        help="Round file to score (default: newest in data/eval)")
    args = parser.parse_args(argv)

    path = args.csv
    if path is None:
        rounds = round_files()
        if not rounds:
            sys.exit(f"No {ROUND_GLOB} files in {EVAL_DIR} — run uisce-eval-sample first.")
        path = max(rounds, key=lambda p: p.stat().st_mtime)

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    provenance = sorted({
        (row.get("model", "?"), row.get("prompt_version", "?")) for row in rows
    })
    prov = ", ".join(f"{m} pv{v}" for m, v in provenance)
    print(f"Scoring {path} ({prov})")

    labelled = [r for r in rows if r["human_verdict"].strip()]
    print(f"{len(labelled)}/{len(rows)} rows labelled")
    if not labelled:
        return

    per_class = defaultdict(Counter)
    for row in labelled:
        verdict = row["human_verdict"].strip().lower()
        per_class[row["model_end_source"]][verdict] += 1

    total = Counter()
    print(f"\n{'end_source':<26} {'correct':>8} {'incorrect':>10} {'unsure':>7} {'accuracy':>9}")
    for source in sorted(per_class):
        c = per_class[source]
        total.update(c)
        judged = c["correct"] + c["incorrect"]
        acc = f"{100 * c['correct'] / judged:.0f}%" if judged else "n/a"
        print(f"{source:<26} {c['correct']:>8} {c['incorrect']:>10} {c['unsure']:>7} {acc:>9}")
    judged = total["correct"] + total["incorrect"]
    acc = f"{100 * total['correct'] / judged:.1f}%" if judged else "n/a"
    print(f"{'TOTAL':<26} {total['correct']:>8} {total['incorrect']:>10} "
          f"{total['unsure']:>7} {acc:>9}")

    wrong = [r for r in labelled if r["human_verdict"].strip().lower() == "incorrect"]
    if wrong:
        print("\nIncorrect cases (model vs human):")
        for row in wrong:
            human = row["human_end_source"] or "?"
            print(f"  case {row['case_id']}: {row['model_end_source']} "
                  f"{row['model_local_date']} {row['model_local_time']} -> "
                  f"{human} {row['human_local_date']} {row['human_local_time']} "
                  f"| {row['human_notes'][:60]}")
