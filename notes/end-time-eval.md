# End-time extraction evaluation

The LLM end-time extraction (`uisce-infer`) is the least-validated link in the chain: everything downstream — durations, disruption metrics, grades — trusts it, and the one in-feed cross-check (`end_date`) turned out to be untrustworthy (see [data-quality.md](notes/data-quality.md)). This eval puts a measured accuracy number on it.

## Workflow

1. `uv run uisce-eval-sample` — writes a stratified random sample (~120 unique descriptions; minority `end_source` classes oversampled so per-class error rates are meaningful; seeded, default 42) to `data/eval/end_time_sample.csv`.
2. A human labels the CSV (spreadsheet app recommended; the fill-in columns sit between the model's answer and the description text).
3. `uv run uisce-eval-score` — prints per-class and overall accuracy plus a list of the misses.
4. Commit the labelled CSV and record the headline numbers (with date, model, and prompt version) at the bottom of this file.

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

_None recorded yet. Format: date, model, prompt version, N judged, overall accuracy, per-class accuracy, link to the labelled CSV commit._
