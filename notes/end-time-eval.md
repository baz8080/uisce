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

- **All 15 `lifted_immediate` rows failed on a labelling-convention point, not an extraction error.** In every case the model correctly identified the class; the disagreement is that the labeller expected `local_time` to be filled from `start_date` when the text gives no time, whereas the prompt spec says `local_time` is null when no time appears in the text — the model followed the spec as written. Downstream this class is stored with a NULL duration regardless (see [data-quality.md](data-quality.md)), so these rows carry zero weight in any site metric. Setting them aside, accuracy on the classes that actually feed durations is **82/99 = 82.8%**. One genuine improvement was spotted here (case 233792): the lift description states the original notice's issue date, so a true boil-notice duration could be derived instead of NULL — relevant to the issue→lift pairing work.
- **Completion-update precedence failures (7 cases: 233443, 231591, 238390, 238481, 236122, 238536, 238574) are the most damaging real error.** The description contains a newer "works are now complete" block, but the model reported the older scheduled end (or `not_found`). The prompt already states that the newest update wins and shows a worked example; the model doesn't reliably follow it. Worst case (231591) reports a scheduled end 8 days before the actual completion. These directly distort the site's median time-to-fix, and the two `not_found` cases drop real durations entirely.
- **Recurring-window scheduled ends (8 of the 9 `scheduled_end_date_only` misses) are the known nightly/daily-works pattern** — "works nightly from 10pm until 7am, from 8 July until 17 August". The model should report the final date with the window's end time (`scheduled_end_with_time`); instead it reports date-only (correct date in 6 of 8, a wrong date in 2, one of them not in the text at all). This confirms with production data what [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) found on the benchmark set (qwen got these right; gemma didn't). Impact is modest per case — date-only ends fall back to 23:59:59, overstating by hours — except for the two wrong-date cases (days off).
- **Missing time on `completion_update` (2 cases: 234755, 237498):** date and source right, time null despite being present. Labeller's hypothesis: single-digit-day `d/mm/yyyy` dates in the text throw the extraction.

Production weighting: `completion_update` (92% here) is by far the largest class in the real corpus (~3,500 of ~6,800 inferred cases), so corpus-wide accuracy is meaningfully better than the sample's unweighted 82.8% — the sample deliberately oversamples the minority classes to make their error rates measurable.

**Prompt-fix backlog from this round** (in impact order): (1) strengthen completion-over-scheduled precedence, (2) recurring-window pattern → final date + window end time, (3) probe the `d/mm/yyyy` time-drop hypothesis, (4) clarify the `lifted_immediate` `local_time` convention in the spec and this guide so the next labelling round measures extraction, not convention.

Labelled CSV: `data/eval/end_time_sample_2026-07-18_gemma-4-12b-qat_pv1.csv`.

## Next steps: the pv2 prompt update (handoff notes, 2026-07-18)

The plan for the next working session, in order:

1. **Iterate the prompt against the known misses first.** The 32 incorrect round-1 rows (with the human's notes and corrected answers) are the development set — run candidate prompts against those descriptions via the local model (LM Studio, `http://localhost:1234`, `gemma-4-12b-qat` — see `MODEL_URL`/`MODEL_NAME` in `src/uisce/inference.py`) before touching the corpus. Target the backlog above; [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) shows qwen handled the recurring-window cases, so its outputs hint at what a sufficient behaviour looks like.
2. **Cheap regression check before any relabelling:** re-run the new prompt over all 114 round-1 descriptions and score against the *existing* human labels (`human_end_source`/`human_local_date`/`human_local_time`, treating `correct` rows as endorsing the model's original three fields). No human time needed; this gives a pv1-labels-vs-pv2-outputs accuracy directly comparable to 71.9%.
3. **Ship it:** edit `PROMPT` in `src/uisce/inference.py`, bump `PROMPT_VERSION` to 2, and update the eval spec/guide for the `lifted_immediate` convention (backlog item 4).
4. **Beware: `uisce-infer` skips unchanged descriptions.** `get_cases_needing_inference` keys on the last JSONL description hash per case, so a prompt bump alone re-infers *nothing*. Re-inference for pv2 needs the skip logic to also consider the record's `prompt_version` (or a `--force` flag) — small code change, doesn't exist yet.
5. **Re-infer, `uisce-build-inferred`, then `uisce-eval-sample`** for a fresh pv2 round (prior-round case ids are excluded automatically; the minority-class pools were nearly exhausted under pv1 but re-inference reclassifies cases and refills them). Label, `uisce-eval-score`, record a pv2 entry under Results next to pv1's 71.9%.
6. **Opportunity spotted in round 1 (case 233792):** boil-notice *lift* descriptions can state the original notice's issue date — extracting it would give real durations for a class that currently stores NULL, and complements the issue→lift pairing in the status site.
