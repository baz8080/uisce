# Data quality findings

Notes on data quality issues discovered while building the duration-inference pipeline, kept here so the reasoning isn't lost to chat history.

## `cases.start_date` / `cases.end_date` are not trustworthy duration signals

These are the raw `STARTDATE`/`ENDDATE` fields from the ArcGIS source feed. Investigated whether `end_date - start_date` could be used as a cheap alternative (or cross-check) to the LLM-derived duration in `inferred_cases`. Verdict: no. Across the 4,295 cases in `out/uisce.db` (2026-06-30 snapshot) with both fields populated:

- **Median difference: 3 seconds.** 69% of cases have the two timestamps within 5 minutes of each other — they look like both fields get stamped at the same administrative moment (case creation/last edit), not measured start/end of the actual works.
- **327 cases still marked `Open` already have an `end_date` populated.** If `end_date` reflected real completion, an open case shouldn't have one.
- **23 cases (0.5%) have `end_date` before `start_date`.** Invalid on its face.
- **999 more cases (23% of the total) sit within ±60 seconds of *exactly* 1 day**, with smaller clusters at 2, 3, 4, and 7 days. This pattern (excluding the near-zero bucket above) looks like a default/SLA placeholder rather than a genuine measurement — it's too concentrated on round numbers to be coincidental.
- **Cross-check against `inferred_cases.end_duration_seconds`** (the LLM-derived duration from actually reading the notice text) for the 2,500 cases with a high-confidence `completion_update` signal: only **6.6% agree within even a 1-hour tolerance**. The worst mismatches are off by hundreds of hours, and several land exactly on -30 days, -29 days, 24h, or 0h — the same clamping pattern as above, contradicting what the notice text actually says.

**Conclusion:** treat `cases.end_date` as low-trust for duration purposes by default, not as "usually fine, occasionally wrong." The near-zero and negative-diff cases (~70% of the total) are unambiguous red flags. The remaining round-day-clamped cases (~23%) can't be reliably distinguished from genuine same/next-day resolutions using this field alone — there's no clean rule that separates "really resolved in 24 hours" from "administratively defaulted to +1 day." This is why `inferred_cases` derives duration from the notice text via the LLM rather than from these fields.

## Known model-output edge cases

While computing `end_duration_seconds` (see `src/uisce/build.py`), a few real edge cases showed up in the actual data:

- `lifted_immediate` (29 cases): the prompt spec implies `local_date` should be populated for every `end_source` except `not_found`, but 10 of 29 `lifted_immediate` records have a null `local_date` anyway. Where it *is* populated, it always equals `start_date`'s calendar day. Duration for this `end_source` is stored as `NULL` regardless (an "immediately lifted" report tells you it had already resolved by report time, not how long it actually took — storing `0` would be a fabricated point estimate that could bias aggregates toward zero).
- `completion_update` can also have a missing `local_time` (100/3,527 cases) — not just `scheduled_end_date_only`. The "missing time → treat as end-of-day (23:59:59)" fallback is keyed off whether `local_time` is actually present, not off `end_source`.
- ~19 cases produce a computed end that precedes `start_date` (up to a full month earlier in one case). Given the `start_date`/`end_date` unreliability documented above, this is more likely to reflect a bad `start_date` than a bad LLM extraction, but the root cause hasn't been dug into further. These are nulled out rather than stored as negative durations.

## `start_date` looks like a publish timestamp, not an event start

Further evidence (2026-07 snapshot, 6,758 cases) that `start_date` records when staff *posted* the notice, not when the event started:

- **Hour-of-day clusters in office hours.** The top start hours are 09:00 (893), 08:00 (822), 10:00 (772), 11:00 (672), tailing off through the afternoon. Burst mains don't respect office hours; notice publishing does.
- **Day-of-week clusters mid-week.** Thursday has 1,466 starts vs Sunday's 252 (Mon 981, Tue 1,398, Wed 1,419, Fri 848, Sat 388). Again consistent with staffed publishing, not with when water infrastructure actually fails.
- This holds even for `work_type = 'Unplanned'` cases, which is the giveaway — planned works clustering in business hours would be expected; emergencies clustering there would not.

Practical consequence: `end_duration_seconds` in `inferred_cases` measures "notice published → works complete", which systematically *understates* the real outage duration for events that happened overnight or at weekends and weren't posted until the next working morning. There's no in-feed signal to correct for this; it's a floor, not a point estimate.

## Multi-pin events inflate per-case statistics

One real-world event is often published as several map pins sharing a `reference_num` (e.g. `LOU00112686`: 13 pins across Drogheda created within 22 minutes, identical title/description). 675 reference numbers cover 1,930 rows, so the 6,758 "cases" are ~5,485 distinct events. Any per-county counts or duration aggregates computed per-row weight events by pin count. Note the pins are *not* guaranteed byte-identical in description across a group (902 distinct descriptions across the 1,930 duplicate-ref rows), so deduplication by `reference_num` alone would discard real per-area updates — the inference-level dedupe keys on the description hash instead.

## `work_category` and `work_type` derivation from title categories

Titles are rigidly structured as `"Category – County"` (dash inconsistently a hyphen or en-dash, spacing messy). A single mechanism, `CATEGORY_RULES` in `src/uisce/pipeline.py`, normalises the category part to a stable `work_category` slug and attaches a `work_type` policy (26 categories as of 2026-07; that list is the source of truth). `work_category` is a pure deterministic normalisation of an existing column, so it lives in `cases`, not `inferred_cases`; a title matching no rule gets a NULL `work_category`.

Each rule's `work_type` policy is one of:

- **Planned / Unplanned** — set on every matching case, *overriding whatever the feed says*, because the label is editorially unambiguous: a burst main / pump failure / interruption is never planned; installation, new-connection and rehabilitation works are always planned; and the stray contradicting rows are typically the completion update tacked onto the end of the job. On the 2026-07 snapshot this overrides ~1,700 rows and, combined with the feed's own labels, takes `work_type` coverage from ~31% to ~89%.
- **None (slug-only)** — the category is clear but planned-vs-unplanned genuinely isn't, so `work_type` is left exactly as the feed reported it (NULL included). Only `mains_repair` (~816 rows, roughly 105P/122U and the rest NULL) and `power_outage` (~192 rows, 22P/26U) use this: both legitimately occur as planned works *and* as emergencies, and the title carries no signal to tell them apart. Separating them would need the description text or reference-number grouping — i.e. inference into `inferred_cases`, not a title backfill.

The rules are static rather than recomputed each run, to avoid a feedback loop where overridden values feed the next run's purity statistics — revisit the `work_type` policies manually if the feed's labelling behaviour changes.

## The feed began (or was purged) around 2026-04-20 — earlier months are unobservable

Daily case counts jump from ~0 to 100+ per day on exactly 2026-04-20 (one stray case from 2026-04-07). Verified 2026-07-16 against the live feed: this is **not** a rolling retention window — the feed still contains all 876 cases with STARTDATE before 2026-05-01 and all 24 pre-April cases the DB knows, exactly matching the DB, so **nothing has been deleted since collection began**. The feed itself evidently started (or was emptied) around mid-April 2026; the handful of older cases are long-lived carryovers such as active boil notices from 2025. Consequences: weekly snapshots currently miss nothing; "April 2026" is still really ten observed days, so any per-month metric must clip its measurement window to [2026-04-20, now] or early months look artificially healthy — this artifact, not a real deterioration, fully explained an apparent month-on-month decline in the status site's grades before the clip was added. Every boil-notice *lift* currently on file refers to a notice issued before the feed window opened. The pipeline now stamps `first_seen`/`last_seen` on every case as a tripwire: if `last_seen` ever stops advancing for cases still marked open, the operator has started pruning and snapshot frequency needs rethinking.

## `water_outage` flag is not a filter

The flag is set on 7,345 of 7,553 cases (97%) — including installations, investigations, and flushing works. Any "which cases actually cut supply" logic has to come from `work_category` + `work_type`, not this flag (the status site's severity classes in [statuspage-methodology.md](statuspage-methodology.md) do exactly that).

## Duration outliers are categorical, not statistical

Every inferred duration above 30 days belongs to `water_conservation` (real 40–87-day restriction events) or a reservoir interruption; sub-minute durations are notices published after the works were already complete. Trimming by percentile would delete real events while keeping misclassified ones — the right move is to classify by category and cap only as a backstop.

## Boil notices: no durations, and lifts arrive as new cases

All 23 `boil_notice_issued` cases have NULL `end_duration_seconds` (there is no end signal in an issue notice), so any duration-based view silently drops active boil notices unless open cases accrue start→now. The lift arrives later as a **separate case with a fresh `reference_num`** (e.g. Downings: issued without a reference, lifted as DON00112xxx), so issue→lift pairing must key on county + normalised scheme name from `location` (strip public/water/supply/scheme/regional/pws: "Ardfinnan Regional Public Water Supply" → "ardfinnan"). Multi-pin publication is not chronologically tidy — lifts can be stamped up to ~2 days before their issue pins. On the 2026-07 snapshot only one pair completes (every other lift refers to a pre-collection notice); the open notices for Achill (MAY00116204), Ballymacarbry (WAT00116255) and Ardfinnan (TIP00113432) are good future test cases for the pairing.

Related: the duplicate case_ids in `data/inferred_duration.jsonl` (422 cases with >1 record) are re-inferences after a description changed, not cross-case links. The 13 `not_found → lifted_immediate` transitions are the lift-notice cases themselves being correctly reclassified once re-read — `build.py` keeps latest-per-case and stores NULL duration for them; no cross-case pairing exists upstream yet.

## Closed cases with no end signal create false-green days

~300 `not_found` cases (plus closed unpaired boil notices) have no interval at all, so day-level views show green where a notice demonstrably existed. A same-day outage-then-all-clear is *not* affected — a case with any inferred duration still overlaps its start day — the hole is only the no-signal cases. The status site gives them a token 1-second footprint: the start day colours and the event counts, but no downtime accrues.
