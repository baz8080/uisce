# Data quality findings

Notes on data quality issues discovered while building the duration-inference
pipeline, kept here so the reasoning isn't lost to chat history.

## `cases.start_date` / `cases.end_date` are not trustworthy duration signals

These are the raw `STARTDATE`/`ENDDATE` fields from the ArcGIS source feed.
Investigated whether `end_date - start_date` could be used as a cheap
alternative (or cross-check) to the LLM-derived duration in `inferred_cases`.
Verdict: no. Across the 4,295 cases in `out/uisce.db` (2026-06-30 snapshot)
with both fields populated:

- **Median difference: 3 seconds.** 69% of cases have the two timestamps
  within 5 minutes of each other — they look like both fields get stamped at
  the same administrative moment (case creation/last edit), not measured
  start/end of the actual works.
- **327 cases still marked `Open` already have an `end_date` populated.** If
  `end_date` reflected real completion, an open case shouldn't have one.
- **23 cases (0.5%) have `end_date` before `start_date`.** Invalid on its
  face.
- **999 more cases (23% of the total) sit within ±60 seconds of *exactly* 1
  day**, with smaller clusters at 2, 3, 4, and 7 days. This pattern (excluding
  the near-zero bucket above) looks like a default/SLA placeholder rather
  than a genuine measurement — it's too concentrated on round numbers to be
  coincidental.
- **Cross-check against `inferred_cases.end_duration_seconds`** (the
  LLM-derived duration from actually reading the notice text) for the 2,500
  cases with a high-confidence `completion_update` signal: only **6.6% agree
  within even a 1-hour tolerance**. The worst mismatches are off by hundreds
  of hours, and several land exactly on -30 days, -29 days, 24h, or 0h —
  the same clamping pattern as above, contradicting what the notice text
  actually says.

**Conclusion:** treat `cases.end_date` as low-trust for duration purposes by
default, not as "usually fine, occasionally wrong." The near-zero and
negative-diff cases (~70% of the total) are unambiguous red flags. The
remaining round-day-clamped cases (~23%) can't be reliably distinguished from
genuine same/next-day resolutions using this field alone — there's no clean
rule that separates "really resolved in 24 hours" from "administratively
defaulted to +1 day." This is why `inferred_cases` derives duration from the
notice text via the LLM rather than from these fields.

## Known model-output edge cases

While computing `end_duration_seconds` (see `build_inferred_cases.py`), a
few real edge cases showed up in the actual data:

- `lifted_immediate` (29 cases): the prompt spec implies `local_date` should
  be populated for every `end_source` except `not_found`, but 10 of 29
  `lifted_immediate` records have a null `local_date` anyway. Where it *is*
  populated, it always equals `start_date`'s calendar day. Duration for this
  `end_source` is stored as `NULL` regardless (an "immediately lifted" report
  tells you it had already resolved by report time, not how long it actually
  took — storing `0` would be a fabricated point estimate that could bias
  aggregates toward zero).
- `completion_update` can also have a missing `local_time` (100/3,527 cases)
  — not just `scheduled_end_date_only`. The "missing time → treat as
  end-of-day (23:59:59)" fallback is keyed off whether `local_time` is
  actually present, not off `end_source`.
- ~19 cases produce a computed end that precedes `start_date` (up to a full
  month earlier in one case). Given the `start_date`/`end_date` unreliability
  documented above, this is more likely to reflect a bad `start_date` than a
  bad LLM extraction, but the root cause hasn't been dug into further. These
  are nulled out rather than stored as negative durations.
