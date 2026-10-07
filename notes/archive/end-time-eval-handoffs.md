# End-time eval, prompt handoffs (completed)

**Simply put:** the working notes for the pv2 prompt change of July 2026, kept as written
once the work was done, except that links to sibling notes now point one directory up. The results they led to are in
[../end-time-eval.md](../end-time-eval.md).

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
[data-quality.md](../data-quality.md) for why that mattered enough to spend a second corpus run on.

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
