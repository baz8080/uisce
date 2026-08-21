# Rules vs LLM for end-time extraction

**2026-08-21.** Question: how much of `uisce-infer`'s LLM work is actually language
understanding, and how much is template filling a regex could do on a CPU? Answer:
**~93% is template filling.** A rules extractor (`src/uisce/rules.py`, `rules-v1`)
covers 92.7% of the corpus with 99.99% agreement against the LLM on the cases it
answers, in 0.6 seconds where a corpus inference run takes ~11 GPU-hours. The
hypothesis is accepted; the architecture is **rules first, LLM fallback for
abstentions** — the same shape data-quality.md already recommended for the overrun
metric ("regex first with an LLM fallback"), now measured for the end-time signal
itself.

This closes the gap model-and-runtime-benchmarks.md left open: that note tested
every way to make the *LLM* faster (concurrency, qwen3.5-9b, speculative decoding,
MoE-on-MLX) and closed them all, but never asked whether most calls needed a model
at all.

## Acceptance criteria, fixed before any measurement

The LLM's demonstrated floor is 219/219 on site-relevant labelled rows (rounds 1+2,
see end-time-eval.md), a 95% lower bound of ~98.3%, so rules must not become the
accuracy bottleneck. Accept iff:

| # | Criterion | Threshold | Measured | |
|---|---|---|---|---|
| 1 | Corpus coverage | ≥ 60% | **92.7%** (10,068/10,860) | pass |
| 2 | Agreement with LLM on answered | ≥ 98%, overall and per emitted class | **99.99%** (10,067/10,068); completion 6,670/6,671, scheduled 3,397/3,397 | pass |
| 3 | After adjudicating every disagreement | rules-wrong ≤ 0.3% of answered AND ≤ LLM-wrong | rules-wrong **0**, LLM-wrong **1** | pass |
| 4 | Labelled rounds | 0 wrong emissions | **0** (round 2: 110/110 answered, 91.7% coverage; round 1: 73/73, 64.0% on the stratified draw) | pass |

Comparison everywhere is `(end_source, local_date, local_time)` at minute
precision. A rules answer on a case the LLM read as `recurrence: daily` counts as
a disagreement even when those three fields match, because the rules record would
drop the window the site expands.

## What rules-v1 is

`extract(start_date, description)` returns the same seven-field dict as prompt v3,
or `None` to abstain. It emits **only** `completion_update` (the
`**Update H:MMam D/M/Y**` header of the block containing an English completion
phrase) and `scheduled_end_with_time` (`until <time> on <date>` and
`estimated completion/restoration time of <time> on <date>` in the newest block).
Everything else abstains by construction:

- `not_found` is never emitted — a template not matching is evidence about the
  rules, not the notice.
- `scheduled_end_date_only` is never emitted — a date without its time becomes
  23:59:59 in `build.py:reported_end_utc`, an up-to-24h silent shift.
- Recurring windows abstain (RECURRENCE_TEXT — now in config.py — plus an
  enumerated-day-list pattern): the window *values* are what needed a language
  model (site.py:recurring_events).
- Lift wording, Irish-only completions, unparseable headers, invalid dates, two
  distinct ends in one block, and any `until` the pattern couldn't read in full
  all abstain.

Measured with `uv run uisce-eval-rules-shadow` (compares rules to the LLM's
latest-per-case JSONL answer for every hash-stable case; disagreements go to
`data/eval/rules_shadow_<date>.csv`) and
`uv run uisce-eval-replay --extractor rules` (scores against the human labels).

## The four corpus disagreements, adjudicated

The first shadow run (pre-freeze) disagreed on 4 of 10,075 answered cases. All
four were read in full:

- **237463 — the LLM is wrong, rules right.** Header `**Update 2:42pm
  02/07/2026**`; the LLM answered 14:22 — a digit transposition of exactly the
  kind it was benchmarked as never making. It stands as the one residual
  disagreement, left in place per the no-backfill rule below.
- **232976 — garbled at source** (`until 6pm on 9 May until 9pm 13 May`), already
  recorded in recurrence_review_2026-08-02.csv; the model reads it as a repeating
  window. Rules took the first `until`. Now abstains.
- **236066 — `17 June, 18 June and19 June`**: the missing space after "and"
  defeated the day-list guard, so rules read a single day where the model
  correctly saw three. Now abstains.
- **240600 — `until 5pm on 05 August until 07 August`**: a date range the model
  reads as recurring; rules took the first end. Now abstains.

Both fixes are strictly narrowing (more abstention, no new emissions), the only
kind of tuning allowed against observed disagreements without a fresh labelled
round. One iteration total; frozen as rules-v1. After the freeze the shadow eval
reads 10,068 answered / 1 disagreement (the LLM's transposition) / 0 on
LLM-recurring cases, and both labelled rounds still show 0 wrong emissions.

## What the LLM keeps (the abstention taxonomy, 792 cases)

| n | LLM class | why rules abstain |
|---|---|---|
| 381 | not_found | no template at all ("we are investigating", boil notices) |
| 117 | completion_update | completion phrase with an unparseable or absent header |
| 108 | scheduled_end_with_time | recurrence wording — model territory |
| 91 | lifted_immediate + not_found | lift wording |
| 27 | scheduled_end_with_time | enumerated day lists |
| 15 | mixed | Irish-only completion (`críoch leis an obair`) |
| 12 | scheduled_end_with_time | an `until` the pattern couldn't read (garbled/range/"further notice") |
| 41 | scheduled_end_with_time | two candidate ends, unusual time forms, other |

Nothing in the residue is a class the rules should have answered: it is exactly
the language-understanding tail the model earns its keep on.

## Rejected alternatives

- **Rules handle recurring windows too.** Rejected without measurement:
  site.py:recurring_events already settled that detection is the easy half and
  the window values needed a model, and 2 of the 4 corpus disagreements were
  range forms the rules mis-read as single ends. Detection patterns here exist
  only to abstain.
- **Rules emit `not_found` for the "we are investigating" template.** Rejected:
  turns absence of a match into a claim, and buys nothing — those cases are
  cheap for the LLM and mostly boil notices that are structurally `not_found`
  anyway.
- **Full replacement, no LLM fallback.** Rejected: 7.3% of the corpus (792
  cases) is real language work — recurring windows, lifts, Irish, garbled text —
  and it is precisely the part with the site's hardest failure modes.
- **Widening the prompt instead of adding rules.** Already rejected for the
  sibling overrun problem (data-quality.md, "regex first with an LLM fallback,
  *not* a widened pv2 prompt"); pv2→pv3 also showed prompt widening costs ~2x
  runtime (end-time-eval.md).
- **Tuning rules against the labelled rounds.** Not done, deliberately: the 234
  labelled rows are the *judge*, so patterns were derived from corpus frequency
  surveys and the shadow eval, and round replays only gated (0 wrong emissions
  before and after the one tuning pass). Residual overfitting risk is real but
  bounded; the clean out-of-sample check is below.

## Consequences for `uisce-infer` (the hybrid)

- Rules records stamp `model: "rules-v1"` and the `prompt_version` whose
  semantics they mirror — the JSONL schema already carries both fields, so no
  migration. Any pattern or precedence change bumps `RULES_VERSION`, the same
  discipline PROMPT_VERSION carries.
- Staleness keys on the model too: bumping RULES_VERSION re-runs only
  rules-produced cases; bumping PROMPT_VERSION re-runs everything, as before.
- **No backfill.** Historical LLM records stand even where the shadow eval shows
  rules would disagree (that is 1 case, and it is the LLM's error): unchanged
  descriptions are never re-extracted, by the same hash-skip rule as always.
  Rules answer new and changed cases only.
- A corpus re-run after a future RULES_VERSION bump costs seconds, not 11 hours,
  which removes the main cost end-time-eval.md attributes to prompt bumps — for
  the 93%, at least.

## Validation still owed (user-side, needs the GPU)

The shadow eval measures agreement on cases the LLM has already seen and the
labelled rounds predate rules-v1, so the clean check is one fresh round:
`uv run uisce-eval-sample-fresh` (~5 min of GPU for 120 unseen cases), label it,
then `uv run uisce-eval-replay --extractor rules --csv <new round>`. Expected:
0 wrong emissions at ~90% coverage. Worth doing before trusting the hybrid's
first big incremental run, not worth blocking the merge on.
