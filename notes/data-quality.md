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

Practical consequence: `end_duration_seconds` in `inferred_cases` measures "notice published → works complete", which *understates* the real outage duration for events that happened overnight or at weekends and weren't posted until the next working morning.

### Sharpened 2026-07-19: the timestamp is machine-generated, and the error is not one-directional

Two refinements from a follow-up pass, prompted by case 234595 (`start_date` 15:37:59, description says "from 10am until 6pm on 3 June"):

- **The seconds field settles it.** 97.6% of the 7,887 populated `start_date` values carry non-zero seconds, and minute values are uniformly spread — only ~2% land on `:00`, which is chance (1/60). A human-stated schedule clusters hard on round hours and `:00` minutes. This is a machine timestamp, not a transcribed event time.
- **There *is* an in-feed alternative signal, contradicting the "no in-feed signal" line above.** 55% of case descriptions (4,352/7,892) state their own start, e.g. "Works are scheduled to take place from 10am until 6pm". Top categories: `essential_works` (892), `burst_main` (753), `mains_repair` (661).
- **The gap runs both ways.** A first crude probe (time-of-day only, ignoring dates) gave median −0.6h with publication preceding the stated start in 59% of cases. See the section below for the properly dated version, which supersedes it and corrects the interpretation offered here.

**Why this matters enough to act on eventually:** median inferred duration is 9.9h (p25 4.1h, p75 23.8h), so start-side noise of ±2–3h is roughly a quarter of the signal — the same order of distortion as the completion-precedence prompt bug fixed in pv2, hitting the same published median-time-to-fix.

**Parked as a possible pv3, with a caveat that makes it more than an extraction problem.** Neither field records the *observed* start: the description states the plan, `start_date` records publication. So a prompt can at best extract "scheduled start per the notice" — it cannot recover when the works truly began. That makes this a definitional question for the site (does a published duration mean *scheduled* or *observed*?) as much as a modelling one, and the current pipeline is incoherent on it: for the `completion_update` class it pairs a machine publication timestamp with a genuinely observed, human-reported end.

Design notes for whenever this is picked up: keep start extraction out of the end-time prompt — pv2 reached 99/99 on the round-1 dev set and a larger prompt puts that at risk, whereas a separate call keeps the two independently measurable. A start-only eval round is also cheaper on the labeller than widening the existing CSV.

### Resolved 2026-07-20: there is no better start basis in the data — do not build the toggle

The open design question was whether the site should let a reader switch duration between the `start_date` basis and a start inferred from the description. **Measured and answered: no.** The inferred start is not closer to the truth, and for the cases that matter most it is further away.

**The stated time is a works-start, not an outage onset.** Of the phrasings introducing a time in the corpus, 4,275 are "works are scheduled to take place from X" and 2,664 give only an end ("until X"). The text describes when crews are scheduled to work, not when supply was lost.

Publication time versus the stated works-start, parsing the accompanying date properly (positive = published *after* the stated start):

| work_type | n | median | p25 | p75 | published after |
|---|---|---|---|---|---|
| Unplanned | 1,512 | −0.8h | −3.2h | −0.3h | 21% |
| Planned | 2,094 | +0.1h | −2.8h | +4.3h | 51% |
| (null) | 535 | +0.9h | −1.3h | +4.3h | 55% |

Reading it:

- **For unplanned events the notice is published *before* works start** — 79% of the time, median 0.8h earlier. Case 232064 is typical: burst main published 08:55, works stated to start 10:30, complete 16:30. The real ordering is therefore `outage onset < publication < works start`. Substituting the stated start moves the clock *later*, shortening durations and moving **away** from the true onset. It would make the metric worse precisely where the office-hours artifact bites hardest.
- **For planned works it changes essentially nothing** (median +0.1h, a 51/49 split). There is no distortion to correct.

So neither population gains. **The toggle is dropped** — not on cherry-picking grounds, though that concern stands for any two-number public control, but because no second number worth showing exists.

**This corrects the earlier bullet above.** The crude time-of-day probe suggested planned works are published in advance and therefore overstate duration; with dates parsed, planned publication sits on top of the stated start and the advance-publication pattern belongs to *unplanned* works instead. The original "floor, not a point estimate" framing survives: publication-based duration remains a lower bound for unplanned events, because onset precedes publication by an amount the feed never records.

**Recommended next step is naming, not modelling.** The metric misleads only because it implicitly claims to be outage duration. Describing it as *time from public notice to restoration* makes it accurate as published, needs no second number, and turns the office-hours clustering into a documented property of a well-named metric rather than a defect in a badly-named one. Cheap, honest, and it forecloses the cherry-picking risk entirely. Not done here — it is a status-site change (`src/uisce/site.py` and its templates), separate from the inference work.

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

## "We are investigating" notices: reference pairing works, but rescues almost nothing

These are correctly modelled `not_found` — an investigation notice genuinely carries no end signal — so the question is whether a paired case found via the reference number supplies one, or whether they should simply be excluded.

**The pairing mechanism works.** Reference numbers (`[A-Z]{2,4}\d{6,}`) yield 6,109 distinct refs across 7,892 cases; 806 refs span more than one case, covering 2,326 cases. The worked example resolves exactly as hoped — `LIM00111812` appears in two cases: 233185, the "We are investigating … Patrick Street, O'Connell Street" notice, and 233184, its sibling carrying "Works are now complete at 10:39am 14/05/2026".

**But it almost never fires.** Of 296 `not_found` cases (pv1 data), 203 are "we are investigating". Of those:

| outcome | count |
|---|---|
| no reference number in the description at all | 145 |
| reference present, no sibling with a real end signal | 56 |
| **rescuable via a paired reference** | **2** |

The 145 unpairable ones are the short variant — "We are investigating reports of supply disruptions affecting X … More information to follow." — which carries no reference number by construction. The `LIM00111812` case is one of the two that do pair; a lucky pick rather than a representative one.

**Conclusion: exclude, don't pair.** A cross-case join is real work (schema, build step, ordering rules for pins that publish out of sequence — see the boil-notice section) to recover two cases. Worth revisiting only if the feed's publishing behaviour changes such that investigation notices routinely carry references *and* resolving siblings.

Note these already contribute NULL duration, so they do not distort duration aggregates today. The live question is narrower: whether they should still count as *events* in per-county and per-day case counts, where they currently do. That interacts with the false-green-days handling below.

## Closed cases with no end signal create false-green days

~300 `not_found` cases (plus closed unpaired boil notices) have no interval at all, so day-level views show green where a notice demonstrably existed. A same-day outage-then-all-clear is *not* affected — a case with any inferred duration still overlaps its start day — the hole is only the no-signal cases. The status site gives them a token 1-second footprint: the start day colours and the event counts, but no downtime accrues.
