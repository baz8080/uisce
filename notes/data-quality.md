# Data quality findings

Notes on data quality issues discovered while building the duration-inference pipeline, kept here so the reasoning isn't lost to chat history. Effects quoted in person-hours or availability were measured before 2026-10-06, when the site stopped publishing those figures ([archive/availability-method.md](archive/availability-method.md)); the findings stand.

## `cases.start_date` / `cases.end_date` are not trustworthy duration signals

**Simply put:** the feed's start and end dates are stamped by its software when a notice is posted or edited, not when water was lost or restored. The site reads its times from the notice text instead.

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
- Some cases produce a computed end that precedes `start_date`; these are nulled out rather than stored as negative durations. First noticed as "~19 cases" on the pv1 corpus - re-measured 2026-07-20 at **532**, and 2026-08-15 at **646** - and given its own section below, including direct evidence that `start_date` is re-stamped in place. The NULL is the honest *duration*.

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

**Simply put:** the feed sometimes rewrites a notice's start date after the event, so a few hundred notices look as if they ended before they began. Those get no length at all. Two obvious rescues, the earliest start ever seen and the works window the text names, were tried and both give a wrong number, so the gap stays.

`build.py` nulls a computed span when the extracted end precedes `start_date`. The edge-cases section above recorded this as "~19 cases" on the pv1 corpus; on the current corpus (8,074 inferred) it is **532 cases, 6.6%** — 314 `scheduled_end_with_time`, 218 `completion_update`. Spot-checks across the magnitude range confirm the extractions are right: the text really does state an end before the publication timestamp.

The distribution says what it is. Median −2.7h, 78% within −6h, and the descriptions are same-day: either the notice was published just after the works window it announces had closed ("works 9am until midday on 03 July", published 17:04 — case 237573), or the *first* publication already carried the completion update. For these, the true notice→end value is ≤ 0 — the event was over at publication — so NULL is the honest store and the family is the negative-side continuation of the "sub-minute durations" pattern in the outliers section.

The tail (18 cases more than a day negative) is a different animal: **`start_date` re-stamped by later administrative edits.** Case 232428: works stated for 08 May, `start_date` 08 *June* — exactly +1 month, the same round-offset clamping seen in `end_date`. Case 233527: completion update 11 May, `start_date` stamped 18 May, the *scheduled-end* day. And the JSONL provides direct proof of in-place editing: 10 cases where `start_date` changed between re-inferences of the same case, with the **date part moving while the machine time-of-day survives** (235225: `12:43:19` kept, date +40 days; 238140: `09:17:25` kept, date −30 days; 238310 changed to a round human `11:00:00`). Ten is a floor, not a rate — detection requires the description to have changed in the same window. This hardens the "date from a schedule, time machine-stamped" reading in the qualified note above.

**The contamination appears confined to the nulled family.** The positive side was checked for clusters within ±12h of 7/14/28/29/30/31 days: 19, 2, 0, 0, 1, 2 cases respectively out of 7,177 — noise, not a pattern. So re-stamping is not silently distorting the published medians; it surfaces as negative spans, which are already excluded.

**Two rescue routes measured and closed (2026-07-20).** Both intuitive salvage ideas were tried before accepting the exclusion:

1. *Use the earliest `start_date` the JSONL ever recorded.* Already implemented — `first_start_date_per_case` in `build.py` pins the start seen by the first inference run precisely to defeat later re-stamps. It cannot fire here: the JSONL only witnesses a re-stamp when the description also changed, and only **1 of the 532** has more than one distinct start on record. The re-stamps predate our first observation. (Taking the *minimum* recorded start instead of the first-observed would rescue that one case, but is a worse rule: backward re-stamps like 238140's −30 days would then inflate durations with a bogus early start.)
2. *Use the description's stated works window as the start.* Parses for 478 of 532 (90%), but what comes out answers a different question. For the 314 `scheduled_end_with_time` cases the extracted end *is* the window's "until Y", so stated-start→end = the announced window length — plan minus plan, median 4.0h in a tight band, zero observational content. For the 179 parseable `completion_update` cases it gives planned-start→observed-completion, median 4.7h against the corpus completion median of 18.3h — a hybrid basis over a systematically-short subpopulation (same-day jobs posted after the fact), which is exactly the kind of number that must not be pooled into the published median.

So the spans stay NULL.

**Re-measured 2026-08-15: the family is 646.** On the current corpus (10,273 inferred) the negative spans are **646 cases** - 387 `scheduled_end_with_time`, 259 `completion_update`. The distribution is unchanged from the 2026-07-20 reading (median −2.7h, 80% within −6h, none date-only), so this is the same phenomenon with four more weeks of feed behind it, not a new one. The spans stay NULL; nothing here reopens the two rescue routes above. From 2026-08-15 to 2026-10-06 the site charged these cases a typical span in its availability total ([archive/availability-method.md](archive/availability-method.md)); they are a one-second token on their publication again.

**A forward-looking guard, added 2026-08-15.** `cases.first_start_date` (schema v3) stamps the publication timestamp seen on the *first download* of a case and never advances it, using COALESCE rather than MIN — a backward re-stamp is as real as a forward one, and taking the minimum is the rule rejected above. `first_start_date_per_case` in `build.py` already pins the start seen at the first *inference*, and can only witness a re-stamp when the description changed in the same window; stamping at download time closes that gap. It recovers none of the 646, and nothing computes a duration from it yet — it is an instrument, and it needs history behind it before it can say whether download-time stamping catches re-stamps that inference-time stamping missed.

**Consequence, fixed 2026-07-20:** an *open* case with a nulled span used to fall into the site's accrue-to-now branch, 28 such cases on this snapshot, 12 of them outage-class, running toward the 14-day cap for events whose own text says they finished. `ended_by_publication()` in `site.py` now routes them to the token 1-second footprint instead: their day still colours and they count as events, but no span runs. Open cases with genuinely *no* signal (`not_found`, or not yet inferred) still run to now - that behaviour is unchanged, and the never-inferred backlog is printed by `uisce-build-inferred` (see [pipeline-dependencies.md](pipeline-dependencies.md)).

## Scheduled vs actual end: the second signal is real and cheap (probed 2026-07-20)

**Simply put:** most "works are now complete" updates still carry the originally planned end underneath, so the site could one day say how often Uisce Éireann beats its own estimate. It was probed, not built: a simple pattern match says about seven in ten run late, but nothing has checked that number by hand.

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

**Amended 2026-09-24: the span and its anchor came from different starts.** `build.py` measures `notice_to_end_seconds` from the start it pinned at first inference (`end_input_start_date`), but `site.py` added that span to the *current* `start_date`. When the feed re-stamped the start between the two, the charged interval matched neither reading and ran past the notice's own end. On the 2026-09-23 release that was **21 cases with a usable span**, so the "confined to the nulled family" reading above no longer holds for the site: 243451 (Clare) was charged 4 days past its own completion, and 235225 (Meath, start moved +40 days) was charged the whole 14-day cap after its scheduled end. The interval now starts at `end_input_start_date`, the start the span was measured from, and so does the event's publication date everywhere it is read (the month the completion median files it under, the history, the top ten, the open and closed lists): a code review of the first cut found that leaving `start_date` as the publication produced history records ending before they started and a July median counting a completion July's own event count did not. The span lengths are unchanged, so this moves hours onto the right days rather than adding or removing them. No grade changed.

### A start typed into the wrong millennium (2026-10-04)

**Simply put:** one notice was typed with the year 0206. It made an 1,820-year span, a page dated "Aug 0206", and a notice that fell in no month. Any start before the year 2000 is now ignored wherever a start is read; the other guards considered either missed it or caught real notices.

Case 241224 (`WEX00118070`, "Burst Water Main - Wexford") carries `start_date` and `first_start_date` of `0206-08-10T10:15:00+00:00`: a hand-typed start (round `10:15:00`, where the feed's own stamps carry seconds) with the year's digits transposed. Its sibling pins 241225 and 241230 start 2026-08-10 08:51 and 09:12, all three were first seen 2026-08-10 12:01 and all three carry a completion update at 11:45 that day. Nothing checked the year, so on the 2026-10-04 release:

- `build.py` measured `notice_to_end_seconds` at 57,433,710,600 (about 1,820 years).
- `site.py` capped that at 14 days from year 206, an interval wholly before `COLLECTION_START`. The event's history record read `"start": "0206-08-10", "hours": 337.9, "span_h": 15953808.5`, and the county page printed "Sun 10 Aug 0206 · 337.9h".
- The event's earliest publication fell in no month, so it was missing from August's completion median (Wexford counted 59, not 60), and the capped 14 days stood as a burst-main span.

**Measured before choosing a guard.** 14,467 cases, 14,460 with a start:

| check | cases |
|---|---|
| start year before 2000 | **1** (241224) |
| start year 2022 to 2025 | 14, all standing boil or do-not-consume notices and their lifts, the oldest 2022-08-18 |
| `first_seen` NULL (first downloaded before 2026-07-20) | 7,893 |
| start more than 30 / 14 / 7 / 1 days before `first_seen`, of the 6,572 with both | 4 / 5 / 6 / 136 |
| start after `first_seen`, same 6,572 | 2,056, by up to 35.7 days |

The four more than 30 days before are one event, `WME00115938` (38.1 days), whose 10 July start carries the feed's own machine stamp: the feed served it late. So a bound relative to `first_seen` either misfires on real starts (anything under 38 days) or catches the same single case as a year check, and it cannot see the 7,893 rows with no `first_seen` at all. It was rejected as the detector. Neither check can catch a typo that lands on a plausible year (2016, 2025): the floor is a backstop against dates the feed cannot mean, not a typo detector.

**The guard is one predicate, applied where a start is read.** `plausible_start` in `config.py` refuses a start before `EARLIEST_START_YEAR` (2000; nothing sits between 0206 and 2022, so any cut in that gap reads the corpus the same way). Three readers use it:

- `build.py`: no span is measured from such a start. `notice_to_end_seconds` is NULL, as for a negative span, and `uisce-build-inferred` prints a `::warning::` naming the cases.
- `site.py`: `publication(row)` dates the notice from `first_seen` instead, and a row with neither is not an event (0 cases). With the span NULL and the end known, the pin takes the route the negative-span family already takes: a one-second token (a typical span, at the time).
- `site.py` again: `measured_span` does not read a span whose pinned start fails the same check. A UI deploy builds from the current release without running `uisce-build-inferred`, so the release's `inferred_cases` still holds the 1,820-year span until the next data build; built from that table and from a rebuilt one, the site's payload is identical.
- `build.py` again: `reported_end_utc` reads an end in a year before the floor as no end (0 on file). The rules' abstention below sends a year-less date to the LLM, which is handed the same start; an end it resolved to year 206 was charged there and printed as the history's `from`. With no usable end the pin is a token at `first_seen`.
- `rules.py`: `_resolve_year` lends no year from such a start, so the rules abstain on a date written without one. 4,481 of the rules' 13,560 emissions take their year from the start; 241224's did not (its update header writes `10/08/2026`), but the next one could, and an end in year 206 beside a start in year 206 would be a plausible-looking span of a few hours filed under no month.

**What moved** (same DB, same clock, before and after). The event reads `"start": "2026-08-10", "hours": 1.9, "from": "2026-08-09"`, closed 10 August, 2 of 3 pins confirmed. Wexford August: 9 August now colours, completions 59 to 60 with the median unchanged at 3.7h. National August completions 879 to 880, median unchanged at 16.7h. No grade changed.

**Rejected:**

1. *Guard at ingest (`pipeline.py`).* The typo is already stored, `first_start_date` is COALESCEd and never rewritten, and the JSONL pins the start seen at first inference, so `build.py` and a UI deploy reading an older release would still need the read-side check. Rewriting the stored value is also not an additive migration, and the DB would stop recording what the feed said.
2. *`first_seen` as the start the span is measured from.* For 241224 it changes nothing (first seen 12:01 UTC, completed 10:45 UTC: negative, NULL). In general `first_seen` trails publication by up to a build interval, so a span from it is a hybrid basis that understates, and it would enter the published median as an observed completion. Same reason the stated works window was refused on 2026-07-20.
3. *Repairing the digits (0206 to 2026).* Gives 10:15 to 10:45 UTC, a 0.5h span, where the siblings say the notice was up by 08:51. A guess on one case, and no rule generalises it.
4. *The earliest sibling pin's start.* The right answer here (median 3.6h), but it is a new rule that would apply equally to the whole negative-span family and belongs with the roadmap entry, not in a guard for one case.
5. *Dropping the pin.* A single-pin event would vanish from the count, and the DB would stop recording what the feed said.
6. *An upper bound on the start.* 118 cases start after the last build, by at most 10.5 days, all within the advance-publication range already described above. Nothing to catch, and a threshold would have to be picked without a case to fit it to.

Not touched: the 7 cases with no `start_date` at all stay excluded by `load_cases`. Six are closed with no `first_seen`; the seventh, 243084, is an `Open` Cork burst main first seen 2026-08-31.

## Multi-pin events inflate per-case statistics

One real-world event is often published as several map pins sharing a `reference_num` (e.g. `LOU00112686`: 13 pins across Drogheda created within 22 minutes, identical title/description). 675 reference numbers cover 1,930 rows, so the 6,758 "cases" are ~5,485 distinct events. Any per-county counts or duration aggregates computed per-row weight events by pin count. Note the pins are *not* guaranteed byte-identical in description across a group (902 distinct descriptions across the 1,930 duplicate-ref rows), so deduplication by `reference_num` alone would discard real per-area updates — the inference-level dedupe keys on the description hash instead.

**Padded references (found 2026-09-24).** 57 references on the 2026-09-23 release carry a trailing space or `\xa0`, and 16 of them also appear without it, so 15 events were split in two: listed twice, and counted twice in the month's event counts. `case_ref` strips the reference before keying on it.

## `work_category` and `work_type` derivation from title categories

**Simply put:** every notice title is "Kind of work - County", so the kind of work comes from the title, not from reading the text. For bursts, failures and new connections the title also settles whether the work was planned, and overrides the feed's own planned/unplanned flag, which is missing on most notices.

Titles are rigidly structured as `"Category – County"` (dash inconsistently a hyphen or en-dash, spacing messy). A single mechanism, `CATEGORY_RULES` in `src/uisce/pipeline.py`, normalises the category part to a stable `work_category` slug and attaches a `work_type` policy (26 categories as of 2026-07; that list is the source of truth). `work_category` is a pure deterministic normalisation of an existing column, so it lives in `cases`, not `inferred_cases`; a title matching no rule gets a NULL `work_category`.

Each rule's `work_type` policy is one of:

- **Planned / Unplanned** — set on every matching case, *overriding whatever the feed says*, because the label is editorially unambiguous: a burst main / pump failure / interruption is never planned; installation, new-connection and rehabilitation works are always planned; and the stray contradicting rows are typically the completion update tacked onto the end of the job. On the 2026-07 snapshot this overrides ~1,700 rows and, combined with the feed's own labels, takes `work_type` coverage from ~31% to ~89%.
- **None (slug-only)** — the category is clear but planned-vs-unplanned genuinely isn't, so `work_type` is left exactly as the feed reported it (NULL included). Only `mains_repair` (~816 rows, roughly 105P/122U and the rest NULL) and `power_outage` (~192 rows, 22P/26U) use this: both legitimately occur as planned works *and* as emergencies, and the title carries no signal to tell them apart. Separating them would need the description text or reference-number grouping — i.e. inference into `inferred_cases`, not a title backfill.

The rules are static rather than recomputed each run, to avoid a feedback loop where overridden values feed the next run's purity statistics — revisit the `work_type` policies manually if the feed's labelling behaviour changes.

### A missing variant was silently inventing supply outages (found 2026-08-01)

A title no rule claims gets a NULL `work_category`, and NULL used to sit in `REPAIR_CATS` in `site.py` - so any spelling the table missed was classified as an **unplanned repair, i.e. a hard supply outage**, and counted as one. The failure was invisible because the affected cases still appeared on the site; they just appeared as the wrong thing.

66 cases across 46 distinct titles were unmatched on the 2026-07-31 snapshot. Almost every one was a near-miss on a slug that already existed: `Water Conservation/Restriction` against the rule's plural `.../Restrictions` (19 cases — the largest group, and *restrictions are degraded, they accrue nothing*), the US spelling `Discoloration`, the feed's own typo `Essential Maintrnance Works`, singular `Main Repair Works` / `Main Flushing`, a stray leading article in `A Water Treatment Plant Interruption`, and bare `Valve Failure` / `Valve Replacement` / `Meter Installation` / `Mains Rehabilitation`. Three genuinely new slugs were added — `reservoir_works` (cleaning and upgrades, which must *not* share `reservoir_interruption`'s place in `HARD_CATS`), `water_treatment_plant_upgrade`, and `consumption_notice_lifted`.

The last of those exposed a second, sharper bug: `Lifting of Do Not Consume Notice - Cork` was stored as `consumption_notice_issued` — a lift recorded as the notice being *issued*, the opposite claim, and one that knocks a grade. It was a stale value from an earlier rule set, surviving because `backfill_work_category` only ever sets a slug and never clears one. That is fine for additive rule changes and is why the table must only ever grow; a rename needs its own migration.

Two changes stop this recurring. NULL no longer groups with the repairs - an unparseable title now falls through to `maintenance` and accrues nothing, on the grounds that a title of literally `"unknown"` evidences nothing and a fail-loud default fabricates an outage. And `backfill_work_category` prints every unmatched title prefix with a count on each run, so a new spelling is visible in the build log within one cycle. That guard found `Lifting of Do Not Consume Notice` on its very first run.

Eleven cases remain unmatched and correctly so: eight titled `unknown`, one bare reference number, one `Gorteen, Mullingar`, one `Supply Re-direction`.

### The dash lost its trailing space (found 2026-09-03)

The report from the late-August builds (issue #67) listed 17 cases across 9 prefixes. Six were fixable, and four of those were not the table's fault: `Mains Repair Works -Meath`, `Mains Repair Works -Sligo` and `Burst Water Main -Kerry` put the space *before* the dash and none after, and the title splitter required the space after it, so the county was swallowed into the category key and the exact lookup missed a rule that was already there. Two burst mains and two repairs, invisible to the metrics.

The splitter now splits on a dash with whitespace on at least one side. A dash with no whitespace at all still does not split, which is the invariant that keeps `Mains Tie-In` and `Supply Re-direction` whole; every existing variant resolves to itself under the new pattern. The alternative, stripping a trailing county name against the 26-county list in `site.py`, was rejected as heavier and wrong in a different way: it would also strip the tail off a title that has no category at all, and `Gorteen, Mullingar` is correctly left whole today.

The other two were plain missing variants and were added: `Mains Flushing Works` to `mains_flushing` and `Fire Hydrant Replacement` to `hydrant_repair`. The four survivors are the same as on 2026-08-01, `unknown` (now nine), the bare reference number, `Gorteen, Mullingar` and `Supply Re-direction`, and the report keeps its role. Not re-run against the live archive from the fixing session (the proxy blocks ArcGIS): the next CI data build's `backfill()` re-derives `work_category` and its log should read 12 cases with no category rule.

## Recurring windows were charged as continuous outages (found 2026-08-01)

**Simply put:** some notices describe works that repeat each night for weeks. The site counts the hours inside the windows, and lends a window reported by one notice of an event to its siblings that reported none.

147 of 9,183 notices (1.6%) describe a window that *repeats* over a date range — "Works are now scheduled to take place daily from 10pm until 7am, from 9 July to 27 July". Until prompt v3 the pipeline had nowhere to put that, so it charged the whole range as one continuous block.

The extraction was never at fault. The v2 prompt already had a "Recurring windows" section instructing the model to report the last date at the window's closing time, and it did so correctly — `end_notes` on all 18 pins of `DON00115765` reads *"The text describes a recurring nightly…"*. The loss was in the **representation**: a single end instant cannot express a repeating schedule, and `notice_to_end_seconds` is by construction the span from publication to that instant.

The distortion is small in count and large in effect, because the affected notices are the *longest* ones (median charged span 167h, max 2,826h): one of them, `DON00115765`, 18 nights of 10pm to 7am, was the top row of the national ranking at 385h.

### What the v3 corpus run delivered (2026-08-02)

97 notices claimed a window, 3 more inherited one, and 99 expanded — cutting 20,448 charged hours to 8,418.

`DON00115765` went from 385.2h before v3 to 354.0h on the first run and **144.0h** after window sharing. The middle figure is why the sharing step exists, and it is the more instructive number.

**The first run barely moved anything, for two separate reasons.** Most recurring notices are restrictions - 81 of the 147 candidates are `water_conservation` - so most of the saved hours were in notices the letters never counted. And more seriously, **a completion-update pin blocked its own event**: the model reports `recurrence: "none"` on a notice whose text says the works are complete, which is defensible in isolation since there is no forward schedule left to state. But expansion is decided per notice while coverage is unioned per `reference_num`, so that one pin's continuous interval re-covered every gap its seventeen siblings had carved out, and `DON00115765` kept 354h of its 385.2h. Three events nationally were stuck this way, and the blocking pin was a `completion_update` in all three.

**The repair is that a window belongs to the works, not to the notice.** `event_windows` collects the window any pin of a `reference_num` reported and lends it to pins that reported none; the borrowed series is still clipped to the borrowing pin's own start and end, so the completion pin takes the schedule and then stops at the moment it says the works stopped. Inherited windows face the same cross-check as claimed ones, are refused on the same terms, and are listed case by case on every build - they are the least-evidenced expansions the site makes. Where pins disagree the commonest window wins, ties broken by sorting, so an event cannot resolve itself differently between builds. The first event to disagree arrived on 2026-09-13 and broke the build - see "A pin can report half a window" below.

That closed the county-ordering problem this started from: one notice's missing field had put Donegal at more than double its neighbours on the ranking of the day.

The per-build report names any event whose pins still disagree. It did not at first: the check only inspected pins that had *claimed* a window, so a pin claiming nothing — exactly the pin doing the damage, and tagged indistinguishably from a burst main — was invisible to it. Fixed, with a test for that pin.

### A pin can report half a window (found 2026-09-13)

The 2026-09-13 build failed in `event_windows` with a `TypeError` comparing `None` with `str`: the tie-break sorts the window tuples an event's pins reported, and `TIP00116073` is the first event whose pins report *different amounts* of a window.

The notice is a Tipperary conservation restriction, published as eight pins: "Restrictions are now scheduled to take place nightly from 8pm until 10am until 18 September". It names one date, and that date is the last one. Five pins therefore carry `(20:00, 10:00, NULL)` and three carry `(20:00, 10:00, 2026-08-14)` from an earlier revision of the same text, which is a set of two tuples that cannot be sorted.

Two things were already true and stay true, which is why this is a crash rather than a number moving:

- A window missing any of its three fields is refused wherever it is read (`recurring_intervals`), so all eight pins were charged continuously before and after. The prompt tells the model to use only dates that appear in the text, and no first date appears, so the `NULL` is the model being faithful.
- An absent first date is deliberately not flagged by `unquotable_windows` - see [end-time-eval.md](end-time-eval.md).

**The fix is that a window the guard could not honour does not stand in the vote**, so it cannot beat a usable window a sibling reported and leave the event with nothing to lend. The event key survives with a `None` value, because that key set is also the recurrence signal `recurring_events` seeds from: dropping the key would turn an event the notice plainly describes as nightly back into an outage, which is a severity change dressed up as a crash fix.

One reading decides both, `_read_window`, rather than the vote keeping its own list of what counts: the first version tested only that the three fields were present, which let a whole-day window (open equal to close, refused wherever it is read) stand for election. Two of those are live - `COR00115518` at 16:00-16:00 and `WAT00118181` at 12:00-12:00 - and both are single-pin events, so the vote has nothing to beat and this costs 0h today. It is the same latent failure as the crash, found by review rather than by a build dying.

**Related extraction error, measured and left alone.** On the three pins that do carry a first date, `2026-08-14` is the range's *last* date, taken from "until 14 August" - there is no first date to take. 3 of 96 recurring claims corpus-wide are like this, all three of them this event. It fails safe: a first date at or after the reported end produces an empty series, which the "single window in span" refusal catches, so the pin keeps its continuous interval. `unquotable_windows` cannot see it, because the date is quotable. A coherence check - a window cannot first open after the works end - would catch it and would have nothing else to do, since the refusal it duplicates already fires, so it is not built. Nothing counts these either: the build report folds them into "single window in span" alongside genuine single-window claims, which is where anyone measuring this again would have to start.

**A pin whose own window is unreadable does not borrow a sibling's, and that costs nothing here.** Inheritance is for pins that claimed nothing; a pin that claimed something unreadable keeps its refusal, so the five `NULL`-first-date pins stay continuous while three siblings hold a readable window. On this event it is worth 0h whichever way it goes: that window's first date, `2026-08-14`, is past the 14-day cap on all five, so the borrowed series would be empty. Nothing surfaces the shape, either - the per-build mixed-pin warning fires only when an event mixes expanded and unexpanded pins, and all eight of these refused.

## The notice title is not a reliable severity signal (found 2026-08-02)

**Simply put:** the warnings inside a notice ("may cause supply disruptions", "allow 3-4 hours") appear on every kind of notice, so they say nothing about how bad it is. The one phrase that does carry meaning is "may cause low pressure", and Uisce Éireann also uses two different titles for the same nightly restriction.

Prompted by a sniff test on the national top ten of the day: its largest event looked wrong. Investigating it turned up two things, and the language analysis is worth keeping because it rules out the obvious reading.

**The hedging in Uisce's notices carries no severity signal.** "May cause supply disruptions" appears on **100% of burst mains**, which are unambiguous total outages — it is boilerplate about *who* is affected within a named area, not *whether*. Likewise "allow 3-4 hours for your supply to fully return" (99–100% of every category) and "supply should have returned" (39–48% of every category, and used *more* by `low_pressure` notices than by burst mains). None of them distinguish anything.

Exactly one phrase does: **"may cause low pressure to …"** - 98% of `low_pressure` notices, 0% of burst mains. Two `reservoir_interruption` notices use it (`WAT00113034`, `LON00116458`), describing pressure and no loss of supply while their title says Interruption, and so were counted as hard outages. `backfill_reduced_pressure` now sets the feed's own flag from the notice's own text for these, the same principle as the `work_type` override above. The far commoner "low pressure **and** supply disruptions" (100 cases) is deliberately not matched - those announce both, and the supply loss is the part that accrues.

**The bigger finding is that the title decides severity and Uisce uses two titles for one situation** - the Donegal nightly regime published as Water Conservation in April and Reservoir Interruption in June and July, same villages, same window, opposite treatment. That is handled in [statuspage-methodology.md](statuspage-methodology.md); it removed the top row of the national ranking.

One signal noticed and *not* acted on: ~2% of interruption notices say supply will be "intermittent" — July's second-largest event says "may cause supply intermittent disruptions" and is charged 248.4h continuously. That is the same class of problem as the recurring windows but a much weaker and rarer signal, and no rule here reads it.

## The feed began (or was purged) around 2026-04-20 — earlier months are unobservable

Daily case counts jump from ~0 to 100+ per day on exactly 2026-04-20 (one stray case from 2026-04-07). Verified 2026-07-16 against the live feed: this is **not** a rolling retention window — the feed still contains all 876 cases with STARTDATE before 2026-05-01 and all 24 pre-April cases the DB knows, exactly matching the DB, so **nothing has been deleted since collection began**. (*Superseded 2026-09-05: the feed purged 9,052 cases on 2026-08-10; see the section on cases that vanish, below.*) The feed itself evidently started (or was emptied) around mid-April 2026; the handful of older cases are long-lived carryovers such as active boil notices from 2025. Consequences: weekly snapshots currently miss nothing; "April 2026" is still really ten observed days, so any per-month metric must clip its measurement window to [2026-04-20, now] or early months look artificially healthy — this artifact, not a real deterioration, fully explained an apparent month-on-month decline in the status site's grades before the clip was added. Every boil-notice *lift* currently on file refers to a notice issued before the feed window opened. The pipeline now stamps `first_seen`/`last_seen` on every case as a tripwire: if `last_seen` ever stops advancing for cases still marked open, the operator has started pruning and snapshot frequency needs rethinking.

## The feed carries no modification timestamp — `LASTUPDATE` and `CREATEDATE` are declared but always NULL (probed 2026-07-21)

The layer's field list looks like it solves case history: alongside the fields the pipeline maps, it declares `LASTUPDATE` (Date) and `CREATEDATE` (Date), and the service's `editFieldsInfo` names `EditDate` / `CreationDate` / `Creator` / `Editor`. None of it is usable.

Counted layer-wide against the live service: `LASTUPDATE IS NOT NULL` returns **0** of 8,155 records, and `CREATEDATE IS NOT NULL` returns **0** (for scale, `ENDDATE IS NOT NULL` returns 6,497, so the query itself is sound). The `editFieldsInfo` fields are named in the service metadata but are not exposed as queryable fields on this DeptView. `capabilities` is `Query` alone, `supportsChangeTracking` is absent, and there is no `archivingInfo` — so no change-tracking and no `historicMoment` temporal queries either.

Consequence: **the feed is a complete archive of cases but a pure snapshot of status.** It returns everything (8,155 live vs 8,131 in the DB), yet carries no time dimension whatsoever, so no amount of re-querying recovers when a case changed. `status` transitions are observable only by us, only at build time, which is why `cases.closed_at` is stamped in the upsert and why the published daily release DBs are the only route to history before that column existed (see [`uisce.replay_closed_at`](../src/uisce/replay_closed_at.py)). Do not re-derive this; the fields will keep looking promising.

## `closed_at` is a floor: short-lived cases are never observed open

**Simply put:** the site only learns a notice has closed by looking and finding it no longer open. A notice that opens and closes between two looks is never seen open, so counts of closures always run low. Building more often helped a little; the rest of the gap is Uisce Éireann marking notices closed about three days after the works finished, which no schedule can fix.

Measured 2026-07-21 by replaying the 10 published snapshots (2026-06-30 → 2026-07-20): of the 2,224 cases that first appeared after the earliest snapshot, **256 (12%) were never seen `Open` in any snapshot** — created and closed inside a single gap between builds. No transition exists for those, so they can neither be replayed nor caught live.

This is a property of the build cadence, not of the replay: any "closed in month M" figure is a **floor**, systematically missing the shortest-lived cases, in the same way notice-to-completion spans are floors. The 12% above was measured under the original Mon/Wed/Fri cron (≤3-day gaps plus missed runs); the cron went daily on 2026-07-21 to shrink it, which no amount of frequency can close entirely. **The figure is therefore not comparable across that date** — expect months from August 2026 to carry a smaller undercount than July, and re-measure before reading any month-on-month change in closure counts as real. Also note 76% of currently-closed cases (5,798) closed before the first published snapshot and are unrecoverable outright, so the series realistically begins with July 2026.

### Re-measured 2026-07-31: daily already paid this out, and the floor's true owner is the operator

The 12% figure above is stale, and the paragraph's implied remedy — shrink the gap further — is now closed off. On the 933 cases first seen across the ten daily builds since 2026-07-21, **18 (1.9%) were never observed open**, six of them `investigation` (maintenance severity, feeding no published number).

**The remaining floor is not ours to shrink.** Comparing the observed `Closed` transition against the LLM-inferred actual completion for those cases (n=484): median **+75.7h**, p25 +57.2h, p90 +85.2h, and **97% land more than 24h after the works finished**. Uisce Éireann stamps a case closed roughly three days late, so past a daily cadence the build gap is a small quantisation on top of a much larger administrative lag. This also reframes the 18: they are not fast events narrowly missed but notices posted at or after completion — the negative-span family in the section above — which no cadence can catch open.

**Consequence for the 2026-07-31 move to two builds/day** (added for publication latency, not for this): the second discontinuity in the closure series is roughly an order of magnitude smaller than the first. At most 11 of the 18 were even *published* before the new midday slot, which is a generous upper bound since it assumes each was still `Open` at that moment — so the undercount moves 1.9% → ~1.1% at best. Against a resolved panel carrying a median of 53 events per county-month, that is under half an event, and `resolvedSection` in `site.html` renders one month at a time with no delta or trend, so there is no rendered comparison for it to corrupt. Note it and move on; the 2026-07-21 step is the one that warrants care.

If a closure *series* is ever published (month-over-month counts, or a time-to-close metric keyed on `closed_at`), this stops being a prose caveat and needs the cadence recorded alongside the data so the series can be corrected rather than annotated.

### The replay has nothing left to recover (2026-09-24)

A dry run of `uisce-replay-closed-at` over all 75 release snapshots (2026-06-30 to 2026-09-23) against a copy of the 2026-09-23 release finds 6,961 transitions, and every one of those cases already carries a `closed_at` on the same date as the replayed tag: **0 rows to stamp, and 0 that would change** even if the replay were allowed to overwrite. None of the 5,872 closed cases with a NULL `closed_at` appears in the replay at all; they closed before the first snapshot or were never seen `Open`. Since the v2 schema landed, the live upsert has stamped every transition a snapshot can see, so the `replay_closed_at` dispatch input was dropped from Build DB (owner, 2026-09-24). The script stays for the one case it still serves, a DB restored from an older release, and is run by hand as its docstring shows.

### One release per build (2026-09-24)

Until this date each day had one release, and the second build of the day replaced its
`uisce.db` with `gh release upload --clobber`, which deletes the old asset before uploading
the new one: a failure in between left the day's release with no DB, and every later build
and Pages deploy, which all start from the latest release, failed until someone fixed it by
hand. A same-day swap (upload as `uisce.db.next`, then delete and rename) was built and
rejected on two rounds of review: each round found another state it could strand, all of
them coming from juggling two names inside one release. From this date every build publishes
its own release, tagged `YYYY-MM-DD-HHMM` (UTC); `gh release create` makes a draft, uploads,
then publishes, so the latest release always holds a complete `uisce.db`. About two releases
a day instead of one. `uisce-replay-closed-at` reads the date from the tag's first ten
characters, so the daily and per-build names replay alike.

### Twice-daily builds: why, and why not three (2026-07-31)

The second daily build slot exists for publication latency, not to sharpen `closed_at` (see above — past a daily cadence, Uisce Éireann's own administrative lag dominates, not the build gap). Notices publish between 07:00 and 16:00 UTC (staffed office hours), so a second build only helps if it lands inside that window: measured over 8,135 cases, a single evening build leaves a mean **7.7h** from publication to the site, a midday build halves that to **3.9h**, and an overnight build would only have bought **0.9h**. A third build takes 3.9h to 3.5h — not worth the run.

The schedule (`.github/workflows/build.yml`) is two crons 6h apart; scheduled runs land ~1h20 after the cron fires, so these hit ~12:45 and ~18:45 UTC — spacing far wider than the 1–3 minute run time needs, which is what makes overlapping runs (guarded against via `concurrency`, queued rather than cancelled since a cancelled run has already read the feed) a manual-dispatch edge case rather than a routine one.

**Amended 2026-09-27: the crons moved from 11:20 and 17:23 to 07:17 and 16:23 UTC.** The ~1h20 delay no longer
holds. Over the scheduled runs from 2026-08-28 to 2026-09-26, GitHub started the 11:20 cron a
median 3.8h late (2.5h to 5.7h) and the 17:23 cron a median 2.6h late (1.75h to 4.5h), so the
builds landed ~15:00 and ~20:00 UTC: 5h apart, then a 19h overnight gap, with the midday build
at the tail of the 07:00-16:00 publication window instead of its middle. At 07:17 the same delay
lands the first build ~11:00 (roughly 09:45 to 13:00). The evening cron moved an hour earlier
to land ~19:00: the middle half of its delays (about 2.3h to 3.1h) puts it between 18:40 and
19:30, though the range (1.75h to 4.5h) still reaches 18:10 to 20:55. Re-measure
the delays from the run list if the site's age at the midday build drifts again;
if either new slot turns out to be delayed differently from the old one, move it again rather than adding a
third build.

## The feed purged 9,052 cases on 2026-08-10, and cases that vanish while Open are stamped (2026-09-05)

**Simply put:** the feed sometimes drops notices without ever closing them. The site stamps when it last saw each one, and treats a notice that disappeared while open as closed with no end.

The "nothing has been deleted since collection began" finding of 2026-07-16 (above) no longer
holds. On the 2026-09-04 release, `last_seen` falls on exactly three days: 3,044 cases on
2026-09-04, one on 2026-08-24, and **9,052 on 2026-08-10**. Everything else the DB holds was
dropped by the feed in one build. By publication month the dropped cases are May 2,367, June
2,563, July 3,205, August 46 (none published after 2026-08-08); what survived is 2,401 August
cases, 71 July, and a couple of dozen long-lived older notices back to 2022. It is not a clean
date cut and not a rolling window either: closed cases closed 31 days before the horizon are
still served, and only one case has gone since. A second purge like the one around 2026-04-20,
then, and the release DB is the only record of those 9,052 notices. The 2026-07-16 probe was
right on the day it was run; the tripwire it left (`last_seen` stopping) is what caught this,
a month late, because nothing printed it.

The tripwire's real target had fired too: 10 of 549 `Open` cases had a `last_seen` behind the
data horizon, 9 of them by more than 14 days, all `low_pressure` (6) or `water_conservation`
(4). The feed had dropped them without ever closing them. `closed_at` stamps only a status
transition the feed sends, and these will never send one, so they sat in every "open now"
count and coloured every day bar as restrictions, and the set could only grow.

`cases.vanished_at` (schema v4) is stamped by `load_cases` on the first build whose download
lacks a case, and cleared by the upsert if it comes back. `site.py`'s `is_open` reads it
beside `status` and the extracted end, so a vanished case is closed with no end signal: it takes the one-second token any such case takes, and appears in
neither the open list nor the closed-in-month list, which is keyed on `closed_at` and would
be claiming an observation that was never made.

**The stamp is only safe behind a count check.** `download_cases` stops on an empty page or a
missing `exceededTransferLimit`, so a truncated response looked exactly like a purge and, with
this stamp, would have marked thousands of cases vanished in one build. `run` now reads the
feed's own count (`returnCountOnly=true`, the endpoint the README lists) before downloading
and refuses a download more than 1% short (`FEED_COUNT_TOLERANCE`). The 1% is for the feed
changing under the paging; a real purge like the one around 2026-04-20 would still be stamped,
which is right: that is what happened.

*2026-09-24:* the tolerance passes an empty feed, 0 downloaded of 0 reported, and that build
would stamp vanished every row not yet vanished, closed ones included (4,306 on the 2026-09-23
release, 498 of them open). `run` now also refuses an empty download
while the DB holds rows not yet vanished; the guard counts what the stamp touches, not the
open ones only. No real purge has emptied the feed; the 2026-08-10 one left 3,044 cases, so a
partial purge is still stamped as before. The same review moved `download_cases` from
`resultOffset` to `OBJECTID > <last seen>` paging: by offset, one case deleted during the
download pushed a live case out of the next page and stamped it vanished, and a server
`maxRecordCount` below the 1,000 asked for dropped the difference at every page, both inside
the 1%. Key paging is only sound on pages returned in `OBJECTID` order, so a page that is not
ascending fails the build rather than skip or repeat rows.

### A feature with no pin (2026-09-24)

ArcGIS omits `geometry` for a null shape, or writes an empty point as `"NaN"`, and one such
feature crashed every build: the coordinates are `NOT NULL` in `cases` and key the geocode
cache. Making them nullable was rejected, because that is not an additive migration.
`restore_pins` instead gives a case the pin the DB last stored for it, and sets aside a case
the DB has never seen pinned, with a `::warning::` on the Actions run naming its id: such a
case is missing from the site, health notices included, until the feed pins it. It is not in
the DB, so it cannot be stamped vanished. None of the 13,588 cases on the 2026-09-23 release
lacked a pin.

The first v4 build will stamp all 9,053 (verified on a copy of the release: the stamp is
idempotent across builds and clears when a case returns), and `create_db` prints the count
stamped on every build from now on, so the next purge is in the build log the day it happens.

Not done: treating `vanished_at` as `closed_at`. They are different observations (the notice
stopped being published, versus the notice's status changed) and only the second is what the
closed-in-month lists claim. Ten cases today; re-count with
`SELECT COUNT(*) FROM cases WHERE status = 'Open' AND vanished_at IS NOT NULL`.

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

The flag was doing damage in two directions at once. Because `classify` tests quality before the hard categories, a flagged burst main became a **quality** event, so five burst mains and mains repairs were not counted as outages. Meanwhile `knocks_grade` painted a drinking-water warning on eight county-months that no notice text supported.

**Resolution: both flags dropped from `classify` and `knocks_grade`, which now read `work_category` alone.** Measured effect on the published site: 8 county-months change, **0 change grade**, and 9 false health markers disappear. The correction runs in both directions - outages that should always have accrued now do, and warnings that were never justified are gone.

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
- **They are already excluded from everything that matters.** 423 of the 463 classify as `maintenance` severity (category `investigation`), which is never counted as an outage. Only 5 land in `outage`. So they do not inflate the published metrics - they show up as blue "works" cells on the day bars and in the total case count, and nothing else.

**Conclusion: leave them.** The remaining cost is cosmetic. Suppressing them would remove a genuine signal (Uisce Éireann did publish something about that area on that day) to fix a problem that measurably isn't distorting any published number. Revisit only if investigations start landing in `outage` in volume.

### Corrected 2026-07-20: a pairing pattern exists after all — by location, not reference — and it still isn't worth building

The "no reference number by construction" line above is true of the description *text* but not the record: the short-variant investigation pins carry an internal `HM`-format `reference_num` (`HM1015170526`) while the resolving sibling gets a fresh county-format ref (`LEI00112029`). So reference pairing is structurally impossible for this class — no prompt or join on `reference_num` can ever link them — but **coordinate pairing works**: at identical rounded coordinates within ±5 days, 2 investigations pair to a completion sibling; widened to 500 m, a *unique* completion sibling exists for 69 of 283 `not_found` investigations (24%), with only 18 ambiguous. Two verified pairs are unmistakably the same event (233454→233455, Carrick-On-Shannon burst; 234163→234166, Ballivor — same streets, completion update in the sibling).

The exclusion decision stands anyway, for the reason the re-measured section above establishes: investigations classify as `maintenance`, which is never counted as an outage, so a rescued duration feeds no published number. Recorded here so the pattern isn't re-derived - if investigation-duration stats are ever wanted, 500 m/±5 d unique-sibling coordinate pairing is the mechanism, not references.

## Closed cases with no end signal create false-green days

~300 `not_found` cases (plus closed unpaired boil notices) have no interval at all, so day-level views show green where a notice demonstrably existed. A same-day outage-then-all-clear is *not* affected - a case with any inferred duration still overlaps its start day - the hole is only the no-signal cases. The status site gives them a token 1-second footprint: the start day colours and the event counts, but no length is read.

## `county` and the pin's own coordinates disagree for ~1.5% of cases (found 2026-07-25)

Building the county drill-down surfaced a small class where `cases.county` and `full_lat`/`full_lon` point at different counties: the notice says Tipperary and the pin sits in Waterford. It only became visible once every Census Small Area belonged to a named area, at which point a pin that still failed to place could only be one whose nearest Small Area lies outside the county the notice claims (since 2026-10-06; before that, its whole 500 m footprint).

About 1.5% of case-months, concentrated in border counties — Tipperary has the most at 21 case-months, Kilkenny 24 across four months.

Which of the two fields is wrong is not established here, and it matters which way you lean: the county drives every county-level figure on the site, while the coordinates drive where it is listed. The site keeps the case on the county the feed names, so county totals stay consistent with `cases.county`, and gives it a `Pinned outside the county` row that reports case counts only.
