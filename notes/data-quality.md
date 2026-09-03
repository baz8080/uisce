# Data quality findings

Notes on data quality issues discovered while building the duration-inference pipeline, kept here so the reasoning isn't lost to chat history.

## `cases.start_date` / `cases.end_date` are not trustworthy duration signals

These are the raw `STARTDATE`/`ENDDATE` fields from the ArcGIS source feed. Investigated whether `end_date - start_date` could be used as a cheap alternative (or cross-check) to the LLM-derived duration in `inferred_cases`. Verdict: no. Across the 4,295 cases in `out/uisce.db` (2026-06-30 snapshot) with both fields populated:

- **Median difference: 3 seconds.** 69% of cases have the two timestamps within 5 minutes of each other — they look like both fields get stamped at the same administrative moment (case creation/last edit), not measured start/end of the actual works.
- **327 cases still marked `Open` already have an `end_date` populated.** If `end_date` reflected real completion, an open case shouldn't have one.
- **23 cases (0.5%) have `end_date` before `start_date`.** Invalid on its face.
- **999 more cases (23% of the total) sit within ±60 seconds of *exactly* 1 day**, with smaller clusters at 2, 3, 4, and 7 days. This pattern (excluding the near-zero bucket above) looks like a default/SLA placeholder rather than a genuine measurement — it's too concentrated on round numbers to be coincidental.
- **Cross-check against `inferred_cases.notice_to_end_seconds`** (the LLM-derived duration from actually reading the notice text) for the 2,500 cases with a high-confidence `completion_update` signal: only **6.6% agree within even a 1-hour tolerance**. The worst mismatches are off by hundreds of hours, and several land exactly on -30 days, -29 days, 24h, or 0h — the same clamping pattern as above, contradicting what the notice text actually says.

**Conclusion:** treat `cases.end_date` as low-trust for duration purposes by default, not as "usually fine, occasionally wrong." The near-zero and negative-diff cases (~70% of the total) are unambiguous red flags. The remaining round-day-clamped cases (~23%) can't be reliably distinguished from genuine same/next-day resolutions using this field alone — there's no clean rule that separates "really resolved in 24 hours" from "administratively defaulted to +1 day." This is why `inferred_cases` derives duration from the notice text via the LLM rather than from these fields.

## Known model-output edge cases

While computing `notice_to_end_seconds` (see `src/uisce/build.py`), a few real edge cases showed up in the actual data:

- `lifted_immediate` (29 cases): the prompt spec implies `local_date` should be populated for every `end_source` except `not_found`, but 10 of 29 `lifted_immediate` records have a null `local_date` anyway. Where it *is* populated, it always equals `start_date`'s calendar day. Duration for this `end_source` is stored as `NULL` regardless (an "immediately lifted" report tells you it had already resolved by report time, not how long it actually took — storing `0` would be a fabricated point estimate that could bias aggregates toward zero).
- `completion_update` can also have a missing `local_time` (100/3,527 cases) — not just `scheduled_end_date_only`. The "missing time → treat as end-of-day (23:59:59)" fallback is keyed off whether `local_time` is actually present, not off `end_source`.
- Some cases produce a computed end that precedes `start_date`; these are nulled out rather than stored as negative durations. First noticed as "~19 cases" on the pv1 corpus — re-measured 2026-07-20 at **532**, and 2026-08-15 at **646** — and given its own section below, including direct evidence that `start_date` is re-stamped in place. The NULL is still the honest *duration*; since 2026-08-15 these cases are nonetheless charged an estimated span in the availability totals, where the alternative to a number is a zero rather than an abstention.

## `start_date` looks like a publish timestamp, not an event start

Further evidence (2026-07 snapshot, 6,758 cases) that `start_date` records when staff *posted* the notice, not when the event started:

- **Hour-of-day clusters in office hours.** The top start hours are 09:00 (893), 08:00 (822), 10:00 (772), 11:00 (672), tailing off through the afternoon. Burst mains don't respect office hours; notice publishing does.
- **Day-of-week clusters mid-week.** Thursday has 1,466 starts vs Sunday's 252 (Mon 981, Tue 1,398, Wed 1,419, Fri 848, Sat 388). Again consistent with staffed publishing, not with when water infrastructure actually fails.
- This holds even for `work_type = 'Unplanned'` cases, which is the giveaway — planned works clustering in business hours would be expected; emergencies clustering there would not.

Practical consequence: `notice_to_end_seconds` in `inferred_cases` measures "notice published → works complete", which *understates* the real outage duration for events that happened overnight or at weekends and weren't posted until the next working morning.

### Sharpened 2026-07-19: the timestamp is machine-generated, and the error is not one-directional

Two refinements from a follow-up pass, prompted by case 234595 (`start_date` 15:37:59, description says "from 10am until 6pm on 3 June"):

- **The seconds field settles it.** 97.6% of the 7,887 populated `start_date` values carry non-zero seconds, and minute values are uniformly spread — only ~2% land on `:00`, which is chance (1/60). A human-stated schedule clusters hard on round hours and `:00` minutes. This is a machine timestamp, not a transcribed event time.
- **There *is* an in-feed alternative signal, contradicting the "no in-feed signal" line above.** 55% of case descriptions (4,352/7,892) state their own start, e.g. "Works are scheduled to take place from 10am until 6pm". Top categories: `essential_works` (892), `burst_main` (753), `mains_repair` (661).
- **The gap runs both ways.** A first crude probe (time-of-day only, ignoring dates) gave median −0.6h with publication preceding the stated start in 59% of cases. See the section below for the properly dated version, which supersedes it and corrects the interpretation offered here.

**Qualified 2026-07-20: the rule is not universal — some `start_date`s are in the future.** 127 currently-open cases carry a `start_date` up to 27 days *ahead* of the snapshot, which a pure publication timestamp cannot be. They are overwhelmingly planned works (88 Planned, 12 Unplanned) and 98% still carry the non-zero-seconds machine signature. The most likely reading is that these rows take their *date* from a scheduled start while the *time* component is still machine-stamped, rather than the whole field being one thing. This does not disturb the resolved toggle decision below, which rests on unplanned events, but "start_date is a publication timestamp" should be read as a statement about the bulk of the corpus, not every row — anything computing an age or an elapsed time from this field needs to handle negatives.

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

**Recommended next step is naming, not modelling.** The metric misleads only because it implicitly claims to be outage duration. Describing it as *time from public notice to restoration* makes it accurate as published, needs no second number, and turns the office-hours clustering into a documented property of a well-named metric rather than a defect in a badly-named one. Cheap, honest, and it forecloses the cherry-picking risk entirely.

**Done 2026-07-20.** The column is `notice_to_end_seconds`, the site publishes "median notice → completion", and the footer states the publication-time caveat directly. The rename turned up a second, larger problem in the same metric — observed completions were being pooled with scheduled ends — recorded in [statuspage-methodology.md](statuspage-methodology.md).

### Measured 2026-07-20: ends preceding publication are 532 cases, not ~19 — and `start_date` is re-stamped in place

`build.py` nulls a computed span when the extracted end precedes `start_date`. The edge-cases section above recorded this as "~19 cases" on the pv1 corpus; on the current corpus (8,074 inferred) it is **532 cases, 6.6%** — 314 `scheduled_end_with_time`, 218 `completion_update`. Spot-checks across the magnitude range confirm the extractions are right: the text really does state an end before the publication timestamp.

The distribution says what it is. Median −2.7h, 78% within −6h, and the descriptions are same-day: either the notice was published just after the works window it announces had closed ("works 9am until midday on 03 July", published 17:04 — case 237573), or the *first* publication already carried the completion update. For these, the true notice→end value is ≤ 0 — the event was over at publication — so NULL is the honest store and the family is the negative-side continuation of the "sub-minute durations" pattern in the outliers section.

The tail (18 cases more than a day negative) is a different animal: **`start_date` re-stamped by later administrative edits.** Case 232428: works stated for 08 May, `start_date` 08 *June* — exactly +1 month, the same round-offset clamping seen in `end_date`. Case 233527: completion update 11 May, `start_date` stamped 18 May, the *scheduled-end* day. And the JSONL provides direct proof of in-place editing: 10 cases where `start_date` changed between re-inferences of the same case, with the **date part moving while the machine time-of-day survives** (235225: `12:43:19` kept, date +40 days; 238140: `09:17:25` kept, date −30 days; 238310 changed to a round human `11:00:00`). Ten is a floor, not a rate — detection requires the description to have changed in the same window. This hardens the "date from a schedule, time machine-stamped" reading in the qualified note above.

**The contamination appears confined to the nulled family.** The positive side was checked for clusters within ±12h of 7/14/28/29/30/31 days: 19, 2, 0, 0, 1, 2 cases respectively out of 7,177 — noise, not a pattern. So re-stamping is not silently distorting the published medians; it surfaces as negative spans, which are already excluded.

**Two rescue routes measured and closed (2026-07-20).** Both intuitive salvage ideas were tried before accepting the exclusion:

1. *Use the earliest `start_date` the JSONL ever recorded.* Already implemented — `first_start_date_per_case` in `build.py` pins the start seen by the first inference run precisely to defeat later re-stamps. It cannot fire here: the JSONL only witnesses a re-stamp when the description also changed, and only **1 of the 532** has more than one distinct start on record. The re-stamps predate our first observation. (Taking the *minimum* recorded start instead of the first-observed would rescue that one case, but is a worse rule: backward re-stamps like 238140's −30 days would then inflate durations with a bogus early start.)
2. *Use the description's stated works window as the start.* Parses for 478 of 532 (90%), but what comes out answers a different question. For the 314 `scheduled_end_with_time` cases the extracted end *is* the window's "until Y", so stated-start→end = the announced window length — plan minus plan, median 4.0h in a tight band, zero observational content. For the 179 parseable `completion_update` cases it gives planned-start→observed-completion, median 4.7h against the corpus completion median of 18.3h — a hybrid basis over a systematically-short subpopulation (same-day jobs posted after the fact), which is exactly the kind of number that must not be pooled into the published median.

So the spans stay NULL. The residual usable content in these descriptions is the window as *availability exposure* (see the salvage rider under the overrun probe above), not as a duration.

**Re-measured 2026-08-15: the family is 646, and its availability treatment changed.** On the current corpus (10,273 inferred) the negative spans are **646 cases** — 387 `scheduled_end_with_time`, 259 `completion_update`. The distribution is unchanged from the 2026-07-20 reading (median −2.7h, 80% within −6h, none date-only), so this is the same phenomenon with four more weeks of feed behind it, not a new one.

**The spans still stay NULL.** Nothing here reopens the two rescue routes above; both remain closed for the reasons given. What changed is downstream, in `site.py` rather than `build.py`: these cases used to take a token 1-second footprint in the *availability* arithmetic, and they are now charged the typical observed span for their `work_category`, anchored backwards from the end they do know. The distinction is the one this section's own `lifted_immediate` note draws at the top of the file — storing `0` as a *duration* would be a fabricated point estimate that biases an aggregate toward zero, and that is still true, which is why the estimate is kept out of the published median. But availability is a **total** over a denominator fixed by population and calendar, and omitting an event from a total is not abstaining, it is asserting zero. There is no NULL available there. See the 2026-08-15 section of [statuspage-methodology.md](statuspage-methodology.md) for the censoring checks that justify the split.

**A forward-looking guard, added 2026-08-15.** `cases.first_start_date` (schema v3) stamps the publication timestamp seen on the *first download* of a case and never advances it, using COALESCE rather than MIN — a backward re-stamp is as real as a forward one, and taking the minimum is the rule rejected above. `first_start_date_per_case` in `build.py` already pins the start seen at the first *inference*, and can only witness a re-stamp when the description changed in the same window; stamping at download time closes that gap. It recovers none of the 646, and nothing computes a duration from it yet — it is an instrument, and it needs history behind it before it can say whether download-time stamping catches re-stamps that inference-time stamping missed.

**Consequence, fixed 2026-07-20:** an *open* case with a nulled span used to fall into the site's accrue-to-now branch — 28 such cases on this snapshot, 12 of them outage-class, fabricating population-weighted downtime toward the 14-day cap for events whose own text says they finished (in July: Kildare −101k person-hours, Donegal −66k once corrected). `ended_by_publication()` in `site.py` now routes them to the token 1-second footprint instead: their day still colours and they count as events, but nothing accrues. Open cases with genuinely *no* signal (`not_found`, or not yet inferred) still accrue — that behaviour is unchanged, and the never-inferred backlog is now printed by `uisce-build-inferred` (see [pipeline-dependencies.md](pipeline-dependencies.md)).

## Scheduled vs actual end: the second signal is real and cheap (probed 2026-07-20)

An earlier session concluded that extracting scheduled-vs-actual "probably would not materially change things". **That was answering the wrong question** and is superseded here.

The valuable signal is not which `end_source` a notice has. It is that a *single* `completion_update` description usually carries **two** timestamps: the completion update at the top, and the originally-announced window still sitting underneath. Case 236163 is typical:

> **Update 9am 19/06/2026** Works are now complete … *Works are now scheduled to take place until 3pm on 18 June.*

Completed 9am 19 June against a stated 3pm 18 June — an 18h overrun. **90.3% of `completion_update` descriptions retain their scheduled window** (4,359 of 4,829).

**Why this dimension is worth more than it first appears: it never touches `start_date`.** Both timestamps come from the notice text, so the overrun metric is entirely free of the publication-timestamp problem that limits every other time figure in this project. It is also a *self-referential* benchmark — did Uisce Éireann meet its own stated estimate? — which needs no assumption about onset, no population model, and no external SLA.

A crude regex probe (`until <time> on <date>`, no LLM spend at all) parsed 4,342 cases and gave:

| overrun (actual − scheduled) | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| hours | −1.9 | 0.0 | **+2.7** | +16.8 | +39.0 |

**69.5% finish late (>15 min over), 8.8% land within 15 minutes of their own estimate, 21.7% finish early.**

**Treat this as a probe, not a result.** Three known weaknesses: the regex takes the *first* `until X on DATE` match, so a stale window can win over a revised one — precisely the completion-precedence bug pv1 had; the year is assumed from the actual end's year (harmless now, wrong across a Dec/Jan boundary); and there is no ground truth, so the p90 of 39h may be partly stale-window artifact rather than real overrun.

**Recommended approach if picked up:** regex first with an LLM fallback for the ~10% that don't match, *not* a widened pv2 prompt. The design note below still applies — pv2 scored 99/99 and 120/120, and widening it risks that for a signal a regex mostly gets for free. Validate with a small labelled round before publishing any overrun figure.

**A cleaner input exists for a subset (found 2026-07-20): the JSONL's own history.** 498 cases in `data/inferred_end_times.jsonl` carry a `scheduled_*` record followed by a later `completion_update` record — the description was re-inferred after the completion update arrived. For these, the scheduled end is the *newest* window visible at its inference date — it can still lag a revision published between that run and the completion, but it cannot be the regex's first-match failure of picking the original window over a revised one already in the text; that neutralises the probe's worst weakness exactly where the two sources can be compared. Use the transition pairs to validate the regex (disagreement rate ≈ stale-window artifact rate), or prefer them outright where available. Coverage grows with every re-inference cycle.

## Multi-pin events inflate per-case statistics

One real-world event is often published as several map pins sharing a `reference_num` (e.g. `LOU00112686`: 13 pins across Drogheda created within 22 minutes, identical title/description). 675 reference numbers cover 1,930 rows, so the 6,758 "cases" are ~5,485 distinct events. Any per-county counts or duration aggregates computed per-row weight events by pin count. Note the pins are *not* guaranteed byte-identical in description across a group (902 distinct descriptions across the 1,930 duplicate-ref rows), so deduplication by `reference_num` alone would discard real per-area updates — the inference-level dedupe keys on the description hash instead.

## `work_category` and `work_type` derivation from title categories

Titles are rigidly structured as `"Category – County"` (dash inconsistently a hyphen or en-dash, spacing messy). A single mechanism, `CATEGORY_RULES` in `src/uisce/pipeline.py`, normalises the category part to a stable `work_category` slug and attaches a `work_type` policy (26 categories as of 2026-07; that list is the source of truth). `work_category` is a pure deterministic normalisation of an existing column, so it lives in `cases`, not `inferred_cases`; a title matching no rule gets a NULL `work_category`.

Each rule's `work_type` policy is one of:

- **Planned / Unplanned** — set on every matching case, *overriding whatever the feed says*, because the label is editorially unambiguous: a burst main / pump failure / interruption is never planned; installation, new-connection and rehabilitation works are always planned; and the stray contradicting rows are typically the completion update tacked onto the end of the job. On the 2026-07 snapshot this overrides ~1,700 rows and, combined with the feed's own labels, takes `work_type` coverage from ~31% to ~89%.
- **None (slug-only)** — the category is clear but planned-vs-unplanned genuinely isn't, so `work_type` is left exactly as the feed reported it (NULL included). Only `mains_repair` (~816 rows, roughly 105P/122U and the rest NULL) and `power_outage` (~192 rows, 22P/26U) use this: both legitimately occur as planned works *and* as emergencies, and the title carries no signal to tell them apart. Separating them would need the description text or reference-number grouping — i.e. inference into `inferred_cases`, not a title backfill.

The rules are static rather than recomputed each run, to avoid a feedback loop where overridden values feed the next run's purity statistics — revisit the `work_type` policies manually if the feed's labelling behaviour changes.

### A missing variant was silently inventing supply outages (found 2026-08-01)

A title no rule claims gets a NULL `work_category`, and NULL used to sit in `REPAIR_CATS` in `site.py` — so any spelling the table missed was classified as an **unplanned repair, i.e. a hard supply outage**, and accrued full person-hours. The failure was invisible because the affected cases still appeared on the site; they just appeared as the wrong thing.

66 cases across 46 distinct titles were unmatched on the 2026-07-31 snapshot. Almost every one was a near-miss on a slug that already existed: `Water Conservation/Restriction` against the rule's plural `.../Restrictions` (19 cases — the largest group, and *restrictions are degraded, they accrue nothing*), the US spelling `Discoloration`, the feed's own typo `Essential Maintrnance Works`, singular `Main Repair Works` / `Main Flushing`, a stray leading article in `A Water Treatment Plant Interruption`, and bare `Valve Failure` / `Valve Replacement` / `Meter Installation` / `Mains Rehabilitation`. Three genuinely new slugs were added — `reservoir_works` (cleaning and upgrades, which must *not* share `reservoir_interruption`'s place in `HARD_CATS`), `water_treatment_plant_upgrade`, and `consumption_notice_lifted`.

The last of those exposed a second, sharper bug: `Lifting of Do Not Consume Notice - Cork` was stored as `consumption_notice_issued` — a lift recorded as the notice being *issued*, the opposite claim, and one that knocks a grade. It was a stale value from an earlier rule set, surviving because `backfill_work_category` only ever sets a slug and never clears one. That is fine for additive rule changes and is why the table must only ever grow; a rename needs its own migration.

Two changes stop this recurring. NULL no longer groups with the repairs — an unparseable title now falls through to `maintenance` and accrues nothing, on the grounds that a title of literally `"unknown"` evidences nothing and a fail-loud default fabricates downtime. And `backfill_work_category` prints every unmatched title prefix with a count on each run, so a new spelling is visible in the build log within one cycle. That guard found `Lifting of Do Not Consume Notice` on its very first run.

Net effect on the July 2026 figures: national person-hours 27,505,846 → 26,898,291 (**−2.2%**), of which −1.9% is the slug fixes and −0.3% the NULL default. Eleven cases remain unmatched and correctly so: eight titled `unknown`, one bare reference number, one `Gorteen, Mullingar`, one `Supply Re-direction`.

### The dash lost its trailing space (found 2026-09-03)

The report from the late-August builds (issue #67) listed 17 cases across 9 prefixes. Six were fixable, and four of those were not the table's fault: `Mains Repair Works -Meath`, `Mains Repair Works -Sligo` and `Burst Water Main -Kerry` put the space *before* the dash and none after, and the title splitter required the space after it, so the county was swallowed into the category key and the exact lookup missed a rule that was already there. Two burst mains and two repairs, invisible to the metrics.

The splitter now splits on a dash with whitespace on at least one side. A dash with no whitespace at all still does not split, which is the invariant that keeps `Mains Tie-In` and `Supply Re-direction` whole; every existing variant resolves to itself under the new pattern. The alternative, stripping a trailing county name against the 26-county list in `site.py`, was rejected as heavier and wrong in a different way: it would also strip the tail off a title that has no category at all, and `Gorteen, Mullingar` is correctly left whole today.

The other two were plain missing variants and were added: `Mains Flushing Works` to `mains_flushing` and `Fire Hydrant Replacement` to `hydrant_repair`. The four survivors are the same as on 2026-08-01, `unknown` (now nine), the bare reference number, `Gorteen, Mullingar` and `Supply Re-direction`, and the report keeps its role. Not re-run against the live archive from the fixing session (the proxy blocks ArcGIS): the next CI data build's `backfill()` re-derives `work_category` and its log should read 12 cases with no category rule.

## Recurring windows were charged as continuous outages (found 2026-08-01)

147 of 9,183 notices (1.6%) describe a window that *repeats* over a date range — "Works are now scheduled to take place daily from 10pm until 7am, from 9 July to 27 July". Until prompt v3 the pipeline had nowhere to put that, so it charged the whole range as one continuous block.

The extraction was never at fault. The v2 prompt already had a "Recurring windows" section instructing the model to report the last date at the window's closing time, and it did so correctly — `end_notes` on all 18 pins of `DON00115765` reads *"The text describes a recurring nightly…"*. The loss was in the **representation**: a single end instant cannot express a repeating schedule, and `notice_to_end_seconds` is by construction the span from publication to that instant.

The distortion is small in count and large in effect, because the affected notices are the *longest* ones (median charged span 167h, max 2,826h) and person-hours are span × population. Measured on the 2026-07-31 snapshot: 6 outage-class events accounted for **9.9% of July's national person-hours**, and one of them — `DON00115765`, 18 nights of 10pm–7am — was 2.54M person-hours on its own: 9.9% nationally, 69% of Donegal, and the top row of the national ranking.

### What the v3 corpus run delivered (2026-08-02)

97 notices claimed a window, 3 more inherited one, and 99 expanded — cutting 20,448 charged hours to 8,418.

| | before v3 | first run | after window sharing |
|---|---|---|---|
| national July person-hours | 26,898,291 | 26,780,519 (−0.4%) | **25,395,359 (−5.6%)** |
| Donegal July | 3,700,792 / 97.023% | 3,504,101 / 97.181% | **2,118,941 / 98.295%** |
| `DON00115765` | 2,540,854 @ 385.2h | 2,334,984 @ 354.0h | **949,824 @ 144.0h** |
| Donegal per-capita | 22,156 h/1k | 20,972 h/1k | **12,682 h/1k** |

The middle column is why the sharing step exists, and it is the more instructive number.

**The first run barely moved anything, for two separate reasons.** Most recurring notices never accrued in the first place — 81 of the 147 candidates are `water_conservation`, which is degraded — so most of the saved hours were hours nobody was charged for. And more seriously, **a completion-update pin blocked its own event**: the model reports `recurrence: "none"` on a notice whose text says the works are complete, which is defensible in isolation since there is no forward schedule left to state. But expansion is decided per notice while coverage is unioned per `reference_num`, so that one pin's continuous interval re-covered every gap its seventeen siblings had carved out, and `DON00115765` kept 354h of its 385.2h. Three events nationally were stuck this way, and the blocking pin was a `completion_update` in all three.

**The repair is that a window belongs to the works, not to the notice.** `event_windows` collects the window any pin of a `reference_num` reported and lends it to pins that reported none; the borrowed series is still clipped to the borrowing pin's own start and end, so the completion pin takes the schedule and then stops at the moment it says the works stopped. Inherited windows face the same cross-check as claimed ones, are refused on the same terms, and are listed case by case on every build — they are the least-evidenced expansions the site makes. Where pins disagree the commonest window wins, ties broken by sorting; no event in the corpus currently disagrees, and the rule exists so that one cannot resolve itself differently between builds.

That closes the county-ordering problem this started from. Donegal was 22,156 person-hours per 1,000 residents against Clare's 9,588 — more than double, on the strength of one notice's missing field. It is now 12,682 against 9,588, the same order as its neighbours, which is what `notes/statuspage-methodology.md` promises readers county ordering means.

The per-build report names any event whose pins still disagree. It did not at first: the check only inspected pins that had *claimed* a window, so a pin claiming nothing — exactly the pin doing the damage, and tagged indistinguishably from a burst main — was invisible to it. Fixed, with a test for that pin.

## The notice title is not a reliable severity signal (found 2026-08-02)

Prompted by a sniff test on the national top ten: nearly a million person-hours for 6,596 people looked wrong. Investigating it turned up two things, and the language analysis is worth keeping because it rules out the obvious reading.

**The hedging in Uisce's notices carries no severity signal.** "May cause supply disruptions" appears on **100% of burst mains**, which are unambiguous total outages — it is boilerplate about *who* is affected within a named area, not *whether*. Likewise "allow 3-4 hours for your supply to fully return" (99–100% of every category) and "supply should have returned" (39–48% of every category, and used *more* by `low_pressure` notices than by burst mains). None of them distinguish anything.

Exactly one phrase does: **"may cause low pressure to …"** — 98% of `low_pressure` notices, 0% of burst mains. Two `reservoir_interruption` notices use it (`WAT00113034`, `LON00116458`), describing pressure and no loss of supply while their title says Interruption, and so were charged as hard outages. `backfill_reduced_pressure` now sets the feed's own flag from the notice's own text for these, the same principle as the `work_type` override above. The far commoner "low pressure **and** supply disruptions" (100 cases) is deliberately not matched — those announce both, and the supply loss is the part that accrues.

**The bigger finding is that the title decides severity and Uisce uses two titles for one situation** — the Donegal nightly regime published as Water Conservation in April and Reservoir Interruption in June and July, same villages, same window, opposite treatment. That is handled in [statuspage-methodology.md](statuspage-methodology.md); it moved July's national total by −3.8% and removed the top row of the national ranking.

One signal noticed and *not* acted on: ~2% of interruption notices say supply will be "intermittent" — July's second-largest event says "may cause supply intermittent disruptions" and is charged 248.4h continuously. That is the same class of problem as the recurring windows but a much weaker and rarer signal, and no rule here reads it.

## The feed began (or was purged) around 2026-04-20 — earlier months are unobservable

Daily case counts jump from ~0 to 100+ per day on exactly 2026-04-20 (one stray case from 2026-04-07). Verified 2026-07-16 against the live feed: this is **not** a rolling retention window — the feed still contains all 876 cases with STARTDATE before 2026-05-01 and all 24 pre-April cases the DB knows, exactly matching the DB, so **nothing has been deleted since collection began**. The feed itself evidently started (or was emptied) around mid-April 2026; the handful of older cases are long-lived carryovers such as active boil notices from 2025. Consequences: weekly snapshots currently miss nothing; "April 2026" is still really ten observed days, so any per-month metric must clip its measurement window to [2026-04-20, now] or early months look artificially healthy — this artifact, not a real deterioration, fully explained an apparent month-on-month decline in the status site's grades before the clip was added. Every boil-notice *lift* currently on file refers to a notice issued before the feed window opened. The pipeline now stamps `first_seen`/`last_seen` on every case as a tripwire: if `last_seen` ever stops advancing for cases still marked open, the operator has started pruning and snapshot frequency needs rethinking.

## The feed carries no modification timestamp — `LASTUPDATE` and `CREATEDATE` are declared but always NULL (probed 2026-07-21)

The layer's field list looks like it solves case history: alongside the fields the pipeline maps, it declares `LASTUPDATE` (Date) and `CREATEDATE` (Date), and the service's `editFieldsInfo` names `EditDate` / `CreationDate` / `Creator` / `Editor`. None of it is usable.

Counted layer-wide against the live service: `LASTUPDATE IS NOT NULL` returns **0** of 8,155 records, and `CREATEDATE IS NOT NULL` returns **0** (for scale, `ENDDATE IS NOT NULL` returns 6,497, so the query itself is sound). The `editFieldsInfo` fields are named in the service metadata but are not exposed as queryable fields on this DeptView. `capabilities` is `Query` alone, `supportsChangeTracking` is absent, and there is no `archivingInfo` — so no change-tracking and no `historicMoment` temporal queries either.

Consequence: **the feed is a complete archive of cases but a pure snapshot of status.** It returns everything (8,155 live vs 8,131 in the DB), yet carries no time dimension whatsoever, so no amount of re-querying recovers when a case changed. `status` transitions are observable only by us, only at build time, which is why `cases.closed_at` is stamped in the upsert and why the published daily release DBs are the only route to history before that column existed (see [`uisce.replay_closed_at`](../src/uisce/replay_closed_at.py)). Do not re-derive this; the fields will keep looking promising.

## `closed_at` is a floor: short-lived cases are never observed open

Measured 2026-07-21 by replaying the 10 published snapshots (2026-06-30 → 2026-07-20): of the 2,224 cases that first appeared after the earliest snapshot, **256 (12%) were never seen `Open` in any snapshot** — created and closed inside a single gap between builds. No transition exists for those, so they can neither be replayed nor caught live.

This is a property of the build cadence, not of the replay: any "closed in month M" figure is a **floor**, systematically missing the shortest-lived cases, in the same way notice-to-completion spans are floors. The 12% above was measured under the original Mon/Wed/Fri cron (≤3-day gaps plus missed runs); the cron went daily on 2026-07-21 to shrink it, which no amount of frequency can close entirely. **The figure is therefore not comparable across that date** — expect months from August 2026 to carry a smaller undercount than July, and re-measure before reading any month-on-month change in closure counts as real. Also note 76% of currently-closed cases (5,798) closed before the first published snapshot and are unrecoverable outright, so the series realistically begins with July 2026.

### Re-measured 2026-07-31: daily already paid this out, and the floor's true owner is the operator

The 12% figure above is stale, and the paragraph's implied remedy — shrink the gap further — is now closed off. On the 933 cases first seen across the ten daily builds since 2026-07-21, **18 (1.9%) were never observed open**, six of them `investigation` (maintenance severity, feeding no published number).

**The remaining floor is not ours to shrink.** Comparing the observed `Closed` transition against the LLM-inferred actual completion for those cases (n=484): median **+75.7h**, p25 +57.2h, p90 +85.2h, and **97% land more than 24h after the works finished**. Uisce Éireann stamps a case closed roughly three days late, so past a daily cadence the build gap is a small quantisation on top of a much larger administrative lag. This also reframes the 18: they are not fast events narrowly missed but notices posted at or after completion — the negative-span family in the section above — which no cadence can catch open.

**Consequence for the 2026-07-31 move to two builds/day** (added for publication latency, not for this): the second discontinuity in the closure series is roughly an order of magnitude smaller than the first. At most 11 of the 18 were even *published* before the new midday slot, which is a generous upper bound since it assumes each was still `Open` at that moment — so the undercount moves 1.9% → ~1.1% at best. Against a resolved panel carrying a median of 53 events per county-month, that is under half an event, and `resolvedSection` in `site.html` renders one month at a time with no delta or trend, so there is no rendered comparison for it to corrupt. Note it and move on; the 2026-07-21 step is the one that warrants care.

If a closure *series* is ever published (month-over-month counts, or a time-to-close metric keyed on `closed_at`), this stops being a prose caveat and needs the cadence recorded alongside the data so the series can be corrected rather than annotated.

### Twice-daily builds: why, and why not three (2026-07-31)

The second daily build slot exists for publication latency, not to sharpen `closed_at` (see above — past a daily cadence, Uisce Éireann's own administrative lag dominates, not the build gap). Notices publish between 07:00 and 16:00 UTC (staffed office hours), so a second build only helps if it lands inside that window: measured over 8,135 cases, a single evening build leaves a mean **7.7h** from publication to the site, a midday build halves that to **3.9h**, and an overnight build would only have bought **0.9h**. A third build takes 3.9h to 3.5h — not worth the run.

The schedule (`.github/workflows/build.yml`) is two crons 6h apart; scheduled runs land ~1h20 after the cron fires, so these hit ~12:45 and ~18:45 UTC — spacing far wider than the 1–3 minute run time needs, which is what makes overlapping runs (guarded against via `concurrency`, queued rather than cancelled since a cancelled run has already read the feed) a manual-dispatch edge case rather than a routine one.

## `water_outage` flag is not a filter

The flag is set on 7,345 of 7,553 cases (97%) — including installations, investigations, and flushing works. Any "which cases actually cut supply" logic has to come from `work_category` + `work_type`, not this flag (the status site's severity classes in [statuspage-methodology.md](statuspage-methodology.md) do exactly that).

## The two health flags are not signals either (measured 2026-08-18)

`water_outage` is not the only feed boolean that carries no information. Both health flags were being read by `classify` and `knocks_grade` ahead of the category, and both were measured against the notice text:

| Flag | Cases | Text supports it | Verdict |
|---|---|---|---|
| `boil_water_notice` | 81 | **81 (100%)** | Reliable, and entirely **redundant** — it appears on `boil_notice_issued` (35) and `boil_notice_lifted` (46) and on no other category, ever |
| `do_not_drink` | 19 | **10 (53%)** | Redundant where it is right, and **wrong** on the other 9 |

The 9 unsupported `do_not_drink` cases are spread across `burst_main` (2), `mains_repair` (2), `low_pressure`, `reservoir_interruption`, `mains_rehabilitation`, `new_connection` and `water_conservation`. Their descriptions are ordinary supply-disruption boilerplate — "repairs to a burst water main may cause supply disruptions… allow 3-4 hours for your supply to fully return" — with no mention of boiling, drinking or safety. Every one of the 10 legitimate flagged cases is already a `consumption_notice_*` or `boil_notice_*` category, so the flags never identified a case the category did not.

**Found by reading the site rather than the code:** Donegal carried a health marker on May. It was case 232423, titled *"Low Pressure - Donegal"*.

The flag was doing damage in two directions at once. Because `classify` tests quality before the hard categories, a flagged burst main became a **quality** event — and only outages accrue availability downtime, so five burst mains and mains repairs were charging **nothing**. Meanwhile `knocks_grade` painted a drinking-water warning on eight county-months that no notice text supported.

**Resolution: both flags dropped from `classify` and `knocks_grade`, which now read `work_category` alone.** Measured effect on the published site: 8 county-months change, **0 change grade**, national person-hours 79,745,765 → 79,819,755 (**+0.09%**), and 9 false health markers disappear. The correction runs in both directions — outages that should always have accrued now do, and warnings that were never justified are gone.

**The rejected alternative was to keep the flags but require the description to corroborate them** (a regex for "boil water notice", "do not consume", "do not drink"). It gives byte-identical results on every case on file — tested against both a loose and a tight pattern, which agree on all 100 flagged cases — so it buys nothing today, and it trades a category lookup for a prose match that can rot. Worth revisiting only if the feed ever puts a *supported* health flag on a non-health category, which has not happened once in 9,762 cases.

## Duration outliers are categorical, not statistical

Every inferred duration above 30 days belongs to `water_conservation` (real 40–87-day restriction events) or a reservoir interruption; sub-minute durations are notices published after the works were already complete. Trimming by percentile would delete real events while keeping misclassified ones — the right move is to classify by category and cap only as a backstop.

## Boil notices: no durations, and lifts arrive as new cases

All 23 `boil_notice_issued` cases have NULL `notice_to_end_seconds` (there is no end signal in an issue notice), so any duration-based view silently drops active boil notices unless open cases accrue start→now. The lift arrives later as a **separate case with a fresh `reference_num`** (e.g. Downings: issued without a reference, lifted as DON00112xxx), so issue→lift pairing must key on county + normalised scheme name from `location` (strip public/water/supply/scheme/regional/pws: "Ardfinnan Regional Public Water Supply" → "ardfinnan"). Multi-pin publication is not chronologically tidy — lifts can be stamped up to ~2 days before their issue pins. On the 2026-07 snapshot only one pair completes (every other lift refers to a pre-collection notice); the open notices for Achill (MAY00116204), Ballymacarbry (WAT00116255) and Ardfinnan (TIP00113432) are good future test cases for the pairing.

Related: duplicate case_ids in `data/inferred_end_times.jsonl` are per-case re-inferences — a changed description, or a prompt-version bump (after the pv2 corpus run, 7,634 of 8,130 cases carry more than one record; the pv1-era figure was 422) — not cross-case links. The 13 `not_found → lifted_immediate` transitions are the lift-notice cases themselves being correctly reclassified once re-read — `build.py` keeps latest-per-case and stores NULL duration for them; no cross-case pairing exists upstream yet.

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

### Re-measured 2026-07-20 under pv2: less of a problem than it looks

Two corrections to the picture above, on the current corpus (463 cases whose description contains "we are investigating"):

- **About half of them do resolve.** 238 carry a `completion_update` and a real interval; only 205 are `not_found`. The pv1-era framing ("203 of 296 `not_found` cases are investigations") counted only the stuck ones and made the class look wholly inert.
- **They are already excluded from everything that matters.** 423 of the 463 classify as `maintenance` severity (category `investigation`), which never accrues availability downtime and never appears in the supply-disruption event counts. Only 5 land in `outage`. So they do not inflate the published metrics — they show up as blue "works" cells on the day bars and in the total case count, and nothing else.

**Conclusion: leave them.** The remaining cost is cosmetic. Suppressing them would remove a genuine signal (Uisce Éireann did publish something about that area on that day) to fix a problem that measurably isn't distorting any published number. Revisit only if investigations start landing in `outage` in volume.

### Corrected 2026-07-20: a pairing pattern exists after all — by location, not reference — and it still isn't worth building

The "no reference number by construction" line above is true of the description *text* but not the record: the short-variant investigation pins carry an internal `HM`-format `reference_num` (`HM1015170526`) while the resolving sibling gets a fresh county-format ref (`LEI00112029`). So reference pairing is structurally impossible for this class — no prompt or join on `reference_num` can ever link them — but **coordinate pairing works**: at identical rounded coordinates within ±5 days, 2 investigations pair to a completion sibling; widened to 500 m, a *unique* completion sibling exists for 69 of 283 `not_found` investigations (24%), with only 18 ambiguous. Two verified pairs are unmistakably the same event (233454→233455, Carrick-On-Shannon burst; 234163→234166, Ballivor — same streets, completion update in the sibling).

The exclusion decision stands anyway, for the reason the re-measured section above establishes: investigations classify as `maintenance`, which never accrues and never appears in the disruption counts, so a rescued duration feeds no published number. Recorded here so the pattern isn't re-derived — if investigation-duration stats are ever wanted, 500 m/±5 d unique-sibling coordinate pairing is the mechanism, not references.

## Closed cases with no end signal create false-green days

~300 `not_found` cases (plus closed unpaired boil notices) have no interval at all, so day-level views show green where a notice demonstrably existed. A same-day outage-then-all-clear is *not* affected — a case with any inferred duration still overlaps its start day — the hole is only the no-signal cases. The status site gives them a token 1-second footprint: the start day colours and the event counts, but no downtime accrues.

## `county` and the pin's own coordinates disagree for ~1.5% of cases (found 2026-07-25)

Building the county drill-down surfaced a small class where `cases.county` and `full_lat`/`full_lon` point at different counties: the notice says Tipperary and the pin sits in Waterford. It only became visible once every Census Small Area belonged to a named area, at which point a pin that still failed to place could only be one whose entire 500 m footprint lay outside the county the notice claims.

About 1.5% of case-months, concentrated in border counties — Tipperary has the most at 21 case-months, Kilkenny 24 across four months.

Which of the two fields is wrong is not established here, and it matters which way you lean: the county drives every county-level figure on the site, while the coordinates drive the affected population. The site keeps the case on the county the feed names, so county totals stay consistent with `cases.county`, and gives it a `Pinned outside the county` row that reports case counts only — with no population to divide by, publishing an availability there would invent a denominator.
