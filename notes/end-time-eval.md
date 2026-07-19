# End-time extraction evaluation

The LLM end-time extraction (`uisce-infer`) is the least-validated link in the chain: everything downstream — durations, disruption metrics, grades — trusts it, and the one in-feed cross-check (`end_date`) turned out to be untrustworthy (see [data-quality.md](notes/data-quality.md)). This eval puts a measured accuracy number on it.

## Workflow

Each labelling session is a **round**: one CSV under `data/eval/`, named `end_time_sample_<date>_<model>_pv<N>.csv` for the model and prompt version that produced the sampled outputs (both are read per-case from `inferred_cases.end_model` / `end_prompt_version`, and repeated in each row's `model` / `prompt_version` columns). Round files are never appended to or overwritten — old rounds stay committed as the evidence behind their Results entries.

1. `uv run uisce-eval-sample` — writes a new round file: a stratified random sample (minority `end_source` classes oversampled so per-class error rates are meaningful; seeded, default 42). Cases drawn in any earlier round are excluded automatically, so each round extends coverage rather than re-asking.
2. A human labels the CSV (spreadsheet app recommended; the fill-in columns sit between the model's answer and the description text).
3. `uv run uisce-eval-score` — prints per-class and overall accuracy plus a list of the misses. Defaults to the newest round file; pass `--csv` to score an older one.
4. Commit the labelled round file and record the headline numbers under Results below.

**Prompt discipline:** any edit to the prompt in `src/uisce/inference.py` must bump `PROMPT_VERSION` there. That number flows through the JSONL into `inferred_cases` and onto every eval round, which is what makes rounds comparable — "pv1 scored 72%, pv2 scored X%" — without digging through git history. After a prompt change, re-run inference and rebuild before sampling a new round, or the sample will still contain pv-old outputs.

## Labelling guide

Read `description` (and `start_date` for context) and judge the model's three fields: `model_end_source`, `model_local_date`, `model_local_time`.

- **`human_verdict`** — the only required column. One of:
  - `correct` — all three fields are right (a null time is *right* when the text truly gives no time of day).
  - `incorrect` — any field is wrong.
  - `unsure` — the notice is genuinely ambiguous even to a human; excluded from the accuracy denominator.
- When `incorrect`, fill `human_end_source` / `human_local_date` / `human_local_time` with what the text actually supports, and say what went wrong in `human_notes`.

**`lifted_immediate` convention (settled 2026-07-18, after round 1 spent 15 rows on it):** `local_time` is **null** unless the text itself states a time of day for the lift. Do not expect the model to copy a time from `start_date` — `start_date` is UTC ISO, so filling it means a timezone conversion, which is Python's job, not the model's. A lift row with the right class and a null time is `correct`. The class is excluded from site metrics anyway ([boil-notices.md](boil-notices.md)), so these rows should cost the labeller almost nothing from round 2 onwards.

Interpretation rules, matching the prompt spec in `src/uisce/inference.py`:

- The **newest** update block wins: a completion update beats an earlier scheduled end.
- `completion_update` = works are reported done at a stated time; `scheduled_end_with_time` = a future end with a time of day; `scheduled_end_date_only` = a date but no time; `lifted_immediate` = an earlier order/restriction lifted with immediate effect and no separate end time; `not_found` = no usable end signal.
- Dates are day/month/year; times are Ireland local, reported as published without timezone conversion.

## Results

### 2026-07-18 — gemma-4-12b-qat, prompt v1, N = 114 (0 unsure)

| end_source | correct | incorrect | accuracy |
|---|---|---|---|
| completion_update | 37 | 3 | 92% |
| scheduled_end_with_time | 27 | 3 | 90% |
| not_found | 18 | 2 | 90% |
| scheduled_end_date_only | 0 | 9 | 0% |
| lifted_immediate | 0 | 15 | 0% |
| **total** | **82** | **32** | **71.9%** |

The raw 71.9% is misleading in both directions, so read it alongside the error taxonomy:

- **All 15 `lifted_immediate` rows failed on a labelling-convention point, not an extraction error.** In every case the model correctly identified the class; the disagreement is that the labeller expected `local_time` to be filled from `start_date` when the text gives no time, whereas the prompt spec says `local_time` is null when no time appears in the text — the model followed the spec as written. Downstream this class is stored with a NULL duration regardless (see [data-quality.md](data-quality.md)), so these rows carry zero weight in any site metric. Setting them aside, accuracy on the classes that actually feed durations is **82/99 = 82.8%**. One genuine improvement was spotted here (case 233792): the lift description states the original notice's issue date, so a true boil-notice duration could be derived instead of NULL — relevant to the issue→lift pairing work. (Investigated and rejected on volume grounds — see the exclusion decision below.)
- **Completion-update precedence failures (7 cases: 233443, 231591, 238390, 238481, 236122, 238536, 238574) are the most damaging real error.** The description contains a newer "works are now complete" block, but the model reported the older scheduled end (or `not_found`). The prompt already states that the newest update wins and shows a worked example; the model doesn't reliably follow it. Worst case (231591) reports a scheduled end 8 days before the actual completion. These directly distort the site's median time-to-fix, and the two `not_found` cases drop real durations entirely.
- **Recurring-window scheduled ends (8 of the 9 `scheduled_end_date_only` misses) are the known nightly/daily-works pattern** — "works nightly from 10pm until 7am, from 8 July until 17 August". The model should report the final date with the window's end time (`scheduled_end_with_time`); instead it reports date-only (correct date in 6 of 8, a wrong date in 2, one of them not in the text at all). This confirms with production data what [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) found on the benchmark set (qwen got these right; gemma didn't). Impact is modest per case — date-only ends fall back to 23:59:59, overstating by hours — except for the two wrong-date cases (days off).
- **Missing time on `completion_update` (2 cases: 234755, 237498):** date and source right, time null despite being present. Labeller's hypothesis: single-digit-day `d/mm/yyyy` dates in the text throw the extraction.

Production weighting: `completion_update` (92% here) is by far the largest class in the real corpus (~3,500 of ~6,800 inferred cases), so corpus-wide accuracy is meaningfully better than the sample's unweighted 82.8% — the sample deliberately oversamples the minority classes to make their error rates measurable.

**Prompt-fix backlog from this round** (in impact order): (1) strengthen completion-over-scheduled precedence, (2) recurring-window pattern → final date + window end time, (3) probe the `d/mm/yyyy` time-drop hypothesis, (4) clarify the `lifted_immediate` `local_time` convention in the spec and this guide so the next labelling round measures extraction, not convention.

Labelled CSV: `data/eval/end_time_sample_2026-07-18_gemma-4-12b-qat_pv1.csv`.

## Decision: `lifted_immediate` is excluded from site metrics (2026-07-18)

Round 1 spent 15 of its 32 misses on this class, so it was measured properly before pv2. The conclusion is to **exclude it, not model it**: 42 pins out of 7,553 cases (0.56%), deduping to 15 distinct lift events, of which the clever description-derived approach would rescue exactly one. The blocking reason is ambiguity rather than volume — the feed uses `start_date` inconsistently on lift records, so a same-day row can't be told apart from one whose lift time is simply unrecorded.

Full reasoning, measurements and the three publishing patterns are in [boil-notices.md](boil-notices.md), along with the related finding that boil notices as a whole are structurally unable to end themselves, which puts them outside this eval's scope entirely.

### 2026-07-19 — pv2 replay against round 1 (regression check, not a labelled round)

Replay re-runs a prompt over round 1's descriptions and scores against round 1's human
labels. It is a **regression filter, not an accuracy estimate**: the class mix is round 1's
deliberately-stratified one, and by the second iteration you are tuning against rows you have
already seen. Recorded separately from labelled rounds for that reason.

Both versions scored by the same field comparison, so the numbers are comparable to each
other — but *not* to the 71.9% in the round-1 table above, which counts `human_verdict`
rather than comparing fields:

| prompt | overall | excl. `lifted_immediate` |
|---|---|---|
| pv1 | 81/114 = 71.1% | 81/99 = 81.8% |
| **pv2** | **99/114 = 86.8%** | **99/99 = 100%** |

pv2 closes all three targeted backlog items: `completion_update` is 46/46 (all 7
completion-precedence misses fixed), both `d/mm/yyyy` time-drop cases fixed, and
`scheduled_end_with_time` is 35/35 with every recurring-window case fixed.

The 15 `lifted_immediate` rows still "fail" on the labelling-convention point; per the
decision above that class is excluded from site metrics, so it is not a prompt problem.

**Read the 100% as a warning, not a result.** These 114 rows are the development set the pv2
prompt was reasoned from — a perfect score on them is the expected outcome of a successful
fix, and it is also exactly what overfitting looks like. It says the three targeted failure
modes are gone; it says nothing about failure modes round 1 never contained. The unseen round
below is what carries evidential weight, and a drop there is information rather than
regression.

Round 1's last disputed row, case 232613 ("daily from 9pm unil 9am, from 5 May until 31
July"), was resolved in pv2's favour: the labeller confirmed on review that 09:00 — the
window's closing time on the last date of the range — is correct, and that the 21:00
originally entered was the window's *start*. Amended in the round file. Worth noting the
prompt's rule is still under-specified for windows crossing midnight (arguably the last
window closes 1 August 09:00, a date absent from the text), but no round-1 case turns on it.

#### Two fixes this round depended on

- **`truth_for()` in `eval_replay.py` was scoring corrected rows as unmatchable.** It fell
  back to the model's value for `end_source` when the labeller left the column blank, but not
  for date or time. Round 1's labeller corrected only the wrong field and left the others
  blank ("the other model fields were correct"), so those rows got an empty-string truth that
  no prompt could ever match — the harness understated every prompt equally. Each field now
  falls back independently. `tests/test_eval_replay.py` had encoded the old behaviour as
  expected; corrected.
- **Three round-1 ground-truth defects were amended** (see the `[amended 2026-07-19: ...]`
  markers in `human_notes`). The labeller's judgement is unchanged in all three; only the
  transcription was fixed. 233443: the correction (09:28) was written in `human_notes` but
  never into the columns. 238481: `human_local_date` and `human_local_time` held each other's
  values. 237632: endorsed `correct` with a blank `model_local_time`, though the description
  reads "Update 9:57am 6/07/2026" — reclassified `incorrect` with the time the text supports.
  232613: the labeller revised their own correction from 21:00 to 09:00 on review. This is a
  deliberate exception to the never-overwrite rule, taken because the file is the measuring
  instrument for every future prompt and the defects cost ~4 points on any version.

## Sampling a fresh round without re-inferring the corpus

`uisce-eval-sample` draws from `inferred_cases`, so a round showing a new prompt's behaviour
used to require a full corpus re-inference first (~7,550 calls, ~4.2 hours at the measured
~2.4s/call). **`uisce-eval-sample-fresh`** inverts that: it draws N unseen case ids from
`cases`, runs the current prompt over just those, and writes the round from those answers.
A 120-row round takes about 5 minutes.

The cost is stratification. `end_source` is unknown until the model has run, so minority
classes cannot be oversampled — the draw is uniform and rare classes may land few rows or
none. That trade is worth taking now for two reasons: a uniform draw is what a corpus-wide
accuracy estimate actually requires (no stratified round has ever produced one), and the two
classes that most justified oversampling no longer need it — `lifted_immediate` is excluded
from site metrics, and `scheduled_end_date_only` has largely collapsed into
`scheduled_end_with_time` under pv2.

Use it as a gate: validate on N calls before committing to the full corpus run. It does not
replace `uisce-eval-sample`, which is still the right tool when per-class error rates for a
specific minority class are the question.

## Next steps: the pv2 prompt update (handoff notes, 2026-07-18)

### Done offline (2026-07-18) — written but **not yet validated against the model**

- **`PROMPT` rewritten and `PROMPT_VERSION` bumped to 2** in `src/uisce/inference.py`, targeting backlog items 1–3: an explicit "scan the whole description for a completion phrase before anything else" step that names stale original text as the trap, a recurring-window rule (last date of the range at the window's closing time → `scheduled_end_with_time`) including the "unil" typo and "between X and Y" phrasing, and a note that a single-digit day is still a valid date carrying a time. Three worked examples were added, one per failure mode, modelled on real round-1 misses. Backlog item 4 is settled in the labelling guide above rather than in the prompt.
- **The skip-logic trap is fixed** (old item 4). `get_last_hash_by_case_id` now returns `(description_hash, prompt_version)` per case and `get_cases_needing_inference` compares both, so a version bump re-infers the corpus; `uisce-infer` also gained `--force` and `--limit`. Verified against the live DB: pv2 flags all 7,552 cases where pv1 flagged 0. Records written before this change carry no `prompt_version` and read as `None`, so they re-infer too.
- **`uisce-eval-replay` added** (`src/uisce/eval_replay.py`) for step 2 below. Ground truth per row is the human correction on `incorrect` rows and the endorsed model fields on `correct` rows; `unsure` rows are dropped; times compare at minute precision because some human labels carry seconds. Scoring logic is unit-tested without the model.

### Validated 2026-07-19 — the prompt is settled, `PROMPT_VERSION` stays at 2

Step 1 is done: the replay above shows pv2 beating pv1 on every class that feeds a duration,
100% against 81.8%, with all three targeted backlog items closed. **The prompt was not edited
during validation**, so pv2 as committed is the validated version — and since the replay set
is the development set, the clean sweep raises the value of the unseen round rather than
settling the question.

### Still needs a human: label round 2

`data/eval/end_time_sample_2026-07-19_gemma-4-12b-qat_pv2.csv` — 120 unseen cases, drawn
uniformly and inferred with pv2 via `uisce-eval-sample-fresh` (about 5 minutes; no corpus
run). These are the first pv2 numbers on cases nobody has looked at, so this is the round
that actually measures the prompt rather than confirming it.

Class mix as pv2 labelled it — the corpus's real distribution, not an oversampled one:
`completion_update` 80, `scheduled_end_with_time` 35, `not_found` 5, and **zero**
`scheduled_end_date_only` or `lifted_immediate`. The empty `scheduled_end_date_only` is
itself a pv2 signal: the recurring-window rule moved that traffic into
`scheduled_end_with_time`.

1. Label it per the guide above, then `uv run uisce-eval-score`.
2. Record the result under Results as the pv2 entry. Because the draw is uniform, this
   headline **is** a corpus-wide estimate — unlike round 1's 71.9%, which is not. Say so in
   the entry; the two numbers are not directly comparable.
3. Only then **ship the corpus**: `uisce-infer` (7,552 calls, ~4.2 hours at ~2.4s/call on
   this machine; `--force` and `--limit` exist), then `uisce-build-inferred`.

If the labelled round contradicts the replay — plausible, since replay had seen these
failure modes and this round has not — iterate the prompt *before* the corpus run, and only
then bump `PROMPT_VERSION` to 3.
