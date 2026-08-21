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

**You only need to fill the cells the model got wrong** — leaving the rest blank is correct and expected. `uisce-eval-replay` falls back to the model's own value for any blank cell on an `incorrect` row, so a blank reads as "the model's value here was right". Two consequences follow, and round 1 tripped on both:

- **A wrong field must get its corrected value in its cell, not only in `human_notes`.** Otherwise the blank claims the model was right about the very field you are marking wrong, and no tool can tell that apart from a genuine endorsement. Round 1's case 233443 recorded "the model picked 20:00 rather than the update time 09:28" in prose with all three cells empty; the corrected 09:28 was invisible to scoring.
- **Marking a row `correct` endorses blank model cells too.** An empty `model_local_time` on a `correct` row asserts that the text states no time of day. Round 1's case 237632 was endorsed that way while its description read "Update 9:57am 6/07/2026". When a model cell is empty, check the text before accepting it.

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

### 2026-07-19 — gemma-4-12b-qat, prompt v2, N = 120 (0 unsure) — **first corpus-wide estimate**

| end_source | correct | incorrect | accuracy |
|---|---|---|---|
| completion_update | 80 | 0 | 100% |
| scheduled_end_with_time | 35 | 0 | 100% |
| not_found | 5 | 0 | 100% |
| **total** | **120** | **0** | **100%** |

Drawn with `uisce-eval-sample-fresh`: 120 unseen cases, uniform draw, inferred with pv2 in
about five minutes rather than a full corpus run. Because the draw is uniform this headline
**is** an unbiased corpus-wide estimate — the first this project has produced. It is *not*
comparable to round 1's 71.9%, which oversamples minority classes by design; the like-for-like
pv1-vs-pv2 comparison is the replay below (81 vs 99 on identical rows).

**Read 100% as "no errors detectable at this sample size", not as perfect.** With zero errors
in 120 draws the rule of three puts the 95% confidence lower bound at ~97.5% — the data cannot
distinguish a 99.9% prompt from a 97.6% one. Detecting a ~2% error rate would need several
hundred labelled rows. The measurement's resolution is exhausted, not its subject.

Two limits on scope:

- **Two classes drew zero rows** (`lifted_immediate`, `scheduled_end_date_only`), so nothing is
  measured about them. That is the corpus's real rarity rather than a sampling failure, and the
  overall estimate stands — but no per-class claim can be made for either. The empty
  `scheduled_end_date_only` is itself a pv2 signal: the recurring-window rule moved that traffic
  into `scheduled_end_with_time`.
- **The headline is dominated by `completion_update`** (80/120 = 67%), which is the corpus mix
  and therefore correct for a corpus estimate, but it means the number is mostly a statement
  about that one class.

Labelling was audited afterwards for the failure mode that damaged round 1: rows endorsed
`correct` while a model cell was blank, where the blank silently asserts the text states no
time. Five such rows exist and all five are the `not_found` cases, none of whose descriptions
contain a time-like string. Clean.

Labelled CSV: `data/eval/end_time_sample_2026-07-19_gemma-4-12b-qat_pv2.csv`.

### 2026-08-21 — gemma-4-12b-qat, prompt v3, N = 120 (0 unsure) — and the rules-v1 truth gate

| end_source | correct | incorrect | accuracy |
|---|---|---|---|
| completion_update | 74 | 0 | 100% |
| scheduled_end_with_time | 39 | 0 | 100% |
| not_found | 7 | 0 | 100% |
| **total** | **120** | **0** | **100%** |

Drawn with `uisce-eval-sample-fresh` (uniform, seed 42, unseen cases) as the out-of-sample
check on the rules-first hybrid ([rules-vs-llm-end-times.md](rules-vs-llm-end-times.md)).
pv3's second perfect uniform round, with the same reading as round 2's: no errors detectable
at this sample size, 95% lower bound ~97.5%.

The round's second purpose was the rules truth gate, and it passed: replaying `rules-v1`
against these labels scores **110/110 correct on answered rows (0 wrong emissions) at
110/120 (91.7%) coverage** — abstentions were the 7 `not_found` rows (never emitted, by
design) and 3 completion updates with unparseable headers. None of these 120 cases was used
to derive or tune any rule pattern.

Labelled CSV: `data/eval/end_time_sample_2026-08-21_gemma-4-12b-qat_pv3.csv`.

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

### 2026-08-01 — pv3 replay (the gate before the v3 corpus run)

pv3 adds four window fields and **leaves `local_date` and `local_time` meaning exactly what
they meant in pv2**, which is the whole reason replay can validate it with no new labelling:
the three fields the harness scores are unchanged, so any drop is the new fields disturbing
the old ones. Both rounds were replayed before committing five hours to a corpus run.

| round | draw | pv1 | pv2 | **pv3** |
|---|---|---|---|---|
| round 1 (N=114) | stratified | 81/114 = 71.1% | 99/114 = 86.8% | **99/114 = 86.8%** |
| round 1, excl. `lifted_immediate` | | 81/99 = 81.8% | 99/99 = 100% | **99/99 = 100%** |
| round 2 (N=120) | uniform, unseen | — | 120/120 = 100% | **120/120 = 100%** |

**pv3 is indistinguishable from pv2 on both rounds** — identical totals, identical per-class
splits, zero parse errors across 234 replayed rows. That is the result the gate wanted: seven
output fields do not degrade the four that already worked. It is *not* evidence that pv3 is
better, and the 86.8% is not comparable to round 1's 71.9% headline (different scoring; see
the pv2 replay section above). The 15 misses are the same `lifted_immediate` convention rows,
excluded from site metrics by the 2026-07-18 decision.

**Round 1 is also the only labelled data touching recurring windows** — 8 rows, against 1 in
round 2. pv1 got all 8 wrong (backlog item 2); pv2 fixed them; pv3 holds all 8, including the
two where pv1 had the *date* wrong (238075 said 17 July for a 27 July range; 238256 said 13
July for 17 July). Between them they cover the variants that matter: `until`/`between … and`
ranges, the feed's `unil` typo, a half-hour close (05:30), a non-crossing daytime window
(09:00–18:00), and windows the notice calls "daily" while they run 10pm–7am.

That last point is what the window fields rest on. The human-corrected `local_time` on all
eight rows *is* the window's closing time — 09:00, 08:00, 18:00, 07:00, 07:00, 07:00, 08:00,
05:30 — and pv3 reproduces each exactly. So the cross-check in `recurring_intervals`
(a scheduled end whose `window_close` disagrees with its own `local_time` is disbelieved) is
validated against eight labelled cases rather than against a reading of the prompt. The window
fields themselves are still unlabelled; this validates their premise, not their values.

**The prompt now has a size budget, and v3 spent most of it.** pv2's prompt was 6,255 chars;
v3 is 9,746 — about 875 extra input tokens on every one of ~7,700 calls, which is also most of
why per-call time went 2.4s to 5.41s and the corpus run took 11 hours rather than 5.

At LM Studio's default 4,096-token context that pushed the longest notices over the edge. The
corpus run failed 29 cases and the separation was almost perfectly by length: every failure
had a description of 4,216 chars or more, against a corpus median of 600, and only 4 of the
9,154 successes were that long. Worst case is ~2,440 prompt tokens + ~1,270 description = 3,720
in, leaving ~380 for an output whose first field is a reasoning string — hence two failure
kinds, 19 HTTP 400s (input alone overflows) and 10 unterminated-JSON parse errors (input fits,
output is cut). **Raised to 8,192 and the 29 re-ran clean**; the corpus is now uniformly pv3.

They changed nothing that matters — 26 came back `not_found` and 23 were boil notices, whose
end is a paired lift rather than their own text, so July's figures and the national top ten are
byte-identical either way. The lesson is for the next prompt change: check the longest
descriptions against the context before starting a corpus run, not after.

One case worth remembering: **238256, "daily from 10pm until 7am until 17 July", states no
first date**. `window_first_date` has nothing to extract, so the guard refuses and the case
keeps its continuous interval — the safe direction, and a reminder that expansion is
opportunistic rather than universal.

Replay CSVs: `..._pv1_replay_gemma-4-12b-qat_pv3.csv` and `..._pv2_replay_gemma-4-12b-qat_pv3.csv`
in `data/eval/`.

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

### pv3 adds the recurring window itself (2026-08-01)

v2 already recognised a repeating window and reported the last date at its closing time,
correctly. What it could not do is say *what the window was*, so `site.py` had no choice but
to charge the whole range as one continuous outage — 385h for eighteen 10pm–7am nights on
`DON00115765`, which made one event 9.9% of July's national person-hours. See the recurring
windows section of [data-quality.md](data-quality.md).

v3 adds four fields — `recurrence`, `window_open`, `window_close`, `window_first_date` — and
**deliberately leaves `local_date` and `local_time` meaning exactly what they meant in v2**.
That is what lets `uisce-eval-replay` validate v3 against the pv2 round with no new labelling:
the three fields it scores are unchanged, so a drop from 120/120 means the new fields have
disturbed the old ones. Run that before spending five hours on a corpus run.

The window fields are **outside the eval loop** — `FIELDNAMES` carries only the end-time
triple, so no round labels them. That is the honest reason the guard refuses by default:
believing a hallucinated recurrence silently halves a county's person-hours, and disbelieving
a real one costs nothing but the status quo.

Three checks stand in for a labelled round, and between them they cover more than the phrase
"unvalidated" suggests:

1. **The close-time cross-check** in `recurring_intervals` — a scheduled end whose window close
   disagrees with its own reported end time is disbelieved. Validated against 8 labelled
   round-1 rows where the human-corrected `local_time` *is* the window's closing time.
2. **`unquotable_windows` in `build.py`** — every window value should be quotable from the
   description the model read, so a reported "22:00" appearing nowhere in the text was
   invented. This needs no labelled data at all and runs on every build. On the v3 corpus:
   **89 of 97 fully quotable, 0 flagged**, and the 8 exceptions are one Tipperary event whose
   text gives no first date at all ("nightly from 8pm until 10am until 5 August"), where the
   model substitutes the publication date — counted separately as inert, because
   `daily_windows` clamps the series start to publication anyway and the value cannot move a
   figure.
3. **The per-build recurrence report** in `site.py` — expanded and refused counts, the
   before/after hour totals, and any event whose pins disagree.

What none of them measure is **recall**: a window the model missed entirely. That is now the
failure mode that costs money, since the guard already makes false positives cheap to refuse,
and it is what a labelled round should target. The pool is small and known — 56 notices whose
description matches the recurrence pattern but which the model called `none`, of which 39 are
`water_conservation` (degraded, a miss costs nothing) and roughly 9 are outage-class. 55 of the
56 are `completion_update`, the pattern cross-pin inheritance already rescues wherever a
sibling claimed a window. So the high-value round is those ~9 plus a sample of the 97 claimed,
not all 153.

### Validated 2026-07-19 — the prompt is settled, `PROMPT_VERSION` stays at 2

Step 1 is done: the replay above shows pv2 beating pv1 on every class that feeds a duration,
100% against 81.8%, with all three targeted backlog items closed. **The prompt was not edited
during validation**, so pv2 as committed is the validated version — and since the replay set
is the development set, the clean sweep raises the value of the unseen round rather than
settling the question.

### Round 2 is labelled and clean — corpus run done 2026-07-20

Round 2 came in at 120/120 (see Results). The gate we set before spending four hours of
inference was passed, and the corpus run followed: all 8,130 inferred cases now carry
`end_prompt_version = 2`. `PROMPT_VERSION` stays at 2: the prompt was never edited during
validation. Nothing in this workflow is pending.

### Superseded by pv3 — corpus run 2026-08-01

The two sections above describe the pv2 end state and are kept as the record of it. pv3 does
not revisit any of it: the end-time triple is unchanged and replayed identically on both
rounds (see the pv3 replay entry in Results). What pv3 adds is the recurring *window*, which
pv2 could recognise but had no field to report — see the recurring-windows section of
[data-quality.md](data-quality.md) for why that mattered enough to spend a second corpus run on.

Neither round labels the window fields, so no accuracy claim exists for them. Their guard is
the close-time cross-check and the per-build recurrence report. **The next labelling round
should stratify on `recurrence`**, which needs a `FIELDNAMES` extension and a quota key —
until then the four new fields are outside the eval loop by construction, not by oversight.

<details>
<summary>Original handoff for round 2 (completed 2026-07-19)</summary>

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

</details>
