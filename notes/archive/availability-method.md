# The availability method (retired 2026-10-06)

**Simply put:** until October 2026 the site guessed how many people each notice reached,
added up their hours without water, and graded each county on the share of people's time
with no outage. That guess was dropped on 2026-10-06; the letters now count outage notices
per 100 km of water main. These sections are kept as they were written, for the record.
Nothing in them describes a figure the site still publishes. The live method is
[../statuspage-methodology.md](../statuspage-methodology.md), and the decision to retire
this one is its section "The estimate is removed".

Sections below are moved unedited from statuspage-methodology.md, in their original order.

## Why not plain "uptime"?

The obvious statuspage metric — fraction of the month with no active outage anywhere in the county — collapses at county granularity: Cork came out at 2% "uptime" for May 2026 because somewhere in Cork almost always has an active case. A county is not a single supply component, and binary county-level uptime punishes size and reporting diligence, not service quality.

The replacement is **population-weighted availability**, a SAIDI-style measure: each notice pin is assumed to affect the Census 2022 Small Areas whose centroids lie within 500 m (nearest Small Area within 8 km as a rural fallback); an event's affected population is the union of its pins' Small Areas, capped at the county population. Then availability = 100% − person-outage-seconds ÷ (county population × observed seconds). Under this measure Cork's May 2026 is ~99.2%, and a burst main serving a 2,000-person town no longer reads as "Cork is down".

## Grades

A to F comes from availability: **A ≥ 99.9%, B ≥ 99.75%, C ≥ 99.45%, D ≥ 99.0%, E ≥ 98.7%, else F** - supply availability and nothing else.

### The scale grew an E (2026-08-29)

The scale ran A, B, C, D, F. Skipping E is an American-ism, and this is an Irish site, so the letter was added. It splits the old F band and moves nothing else: every cut from 99.9 down to 99.0 sits exactly where it did, so no county-month that was graded A to D changes letter. The alternative, re-spreading six bands across the distribution, was rejected without measuring: it would move published letters, and the calibration below was settled on 2026-08-02 after an explicit recalibration check that was declined.

**The cut is 98.7%, and it is fitted to the tail rather than derived from the band widths.** The obvious cut was 98.4%: the bands widen 0.15, 0.30, 0.45, so 0.60 continues the arithmetic, and 98.4 is the rounder number. Measured against the 2026-08-29 build it is wrong. Over 130 graded county-months the whole F population lies between 98.459% and 98.900%, so the record's worst month is 0.54 points below the D cut, and a cut at 98.4 puts all 11 rows in E and leaves F holding nobody.

| cut | E | F |
|---|---|---|
| 98.7 | 9 | 2 |
| 98.5 | 10 | 1 |
| 98.4 | 11 | 0 |
| 98.0 | 11 | 0 |

98.7 keeps both bands saying something, and the two it leaves in F (98.459 and 98.596) are the two worst county-months in the record. 98.5 was rejected as too fragile: it would hold one row, four hundredths below the cut. The empty-F option was rejected because these bands are calibrated to be honest relative to this dataset rather than imported from a regulator, and a bottom band nothing reaches teaches a reader the scale is mis-set.

The grade mix moves A 9, B 26, C 53, D 31, F 11 to A 9, B 26, C 53, D 31, E 9, F 2.

What this costs: the band is 0.30 wide where D is 0.45, so the widening progression breaks at the bottom, and the cut is fitted to a young 130-row archive. **Re-measure it as the archive grows**, against the `uisce.db` CI publishes as a release asset rather than a fresh `uisce-pipeline` run: the numbers above came off the 2026-08-29 release, and in a Claude Code web session the proxy blocks ArcGIS, so the release is the only way to get a current database. If months worse than 98.459% start arriving, the honest move is to widen F downward by raising the cut, not to leave 98.7 sitting where a fuller distribution no longer puts a break. In hours off supply over a 30-day month the cuts now read 0.72, 1.8, 3.96, 7.2 and 9.36.

One consequence on the page: the banner counts the counties graded F (`nF` in `site.html`), and that count now excludes the E counties it used to include. **Raised, measured and left as it is on 2026-08-30**, on the owner's call: F still means the worst band the site has, and a reader who wants the detail has the county rows immediately below. The cost is written down rather than guessed at, because it is larger than a glance at a build suggests. Counties under 99.0% against counties under the new 98.7%:

| month | banner before | banner now | moved F to E |
|---|---|---|---|
| 2026-04 | 3 | 0 | Kildare, Sligo, Waterford |
| 2026-05 | 0 | 0 | - |
| 2026-06 | 2 | 1 | Kildare |
| 2026-07 | 5 | 0 | Clare, Kerry, Limerick, Tipperary, Waterford |
| 2026-08 | 1 | 1 | - |

Two of the five months now head the page with "0 counties graded F" while still holding counties in the bottom two bands. The month the page opens on is unaffected, which is why this does not show up in a casual look at a build. If it is ever reopened, the one-line fix is to count `E` and `F` together and say "graded E or F".

### The health notice was unbundled from the grade (2026-08-02)

An active boil-water / do-not-drink / do-not-consume notice used to knock the letter one step (D and F staying F). It is now published as a marker *beside* the grade instead, driven by `health_n` in the month payload.

It was measured before it was removed. Across 78 settled county-months the knock set the published letter for 8, and it was drastically out of scale with everything else on the page:

| county | month | grade | notice reached | for | it would have cost | the band it crossed |
|---|---|---|---|---|---|---|
| Cork | Jul | D→F | 142 | 336h | 0.011pp | 0.45pp |
| Dublin | Jul | C→D | 5,374 | 24h | 0.012pp | 0.45pp |
| Donegal | Jul | D→F | 204 | 7h | 0.001pp | 0.45pp |
| Kildare | Jul | D→F | 359 | 2h | 0.000pp | 0.45pp |
| Monaghan | Jul | B→C | 190 | <1h | 0.000pp | 0.30pp |

"It would have cost" is what the notice would take off availability if it accrued like an outage. The median ratio to the band it crossed was **0.01** — the knock was about a hundred times the harm it represented on the site's own arithmetic, and it was uniform: 190 people for under an hour cost exactly what 5,374 people for a day cost.

That is not an argument that a boil notice is unimportant. It is an argument that its importance is not measured in person-hours, and so should not be expressed by moving a person-hours score. The two questions — how much water was there, and was it safe to drink — are independent, and one letter cannot answer both. By the time it was removed the knock was the *only* reason for Donegal's July F, which a reader comparing it with a genuine F could not see.

Unbundling also recovered information the knock was destroying. A knock cannot move an F, so a county already at F showed nothing: **Tipperary's July had three active health notices and displayed no sign of any of them.** The marker shows on 10 county-months where the knock affected 8.

Grade mix across the 78 settled county-months, before and after: A2 B16 C31 D19 F10 → **A2 B17 C34 D18 F7**.

Discolouration is a quality event but never raises the marker — it is not a health-relevant notice.

The thresholds are calibrated to the observed distribution of county-months (p10 ≈ 98.9%, median ≈ 99.6%, p90 ≈ 99.87% on the July 2026 snapshot) — they are honest relative to this dataset, not imported from a regulator.

**Checked against the recalibration question, 2026-08-02, and left alone.** Four definitional changes in two days — the classification leak, recurring windows, cross-pin window sharing, and treating a repeating window as a restriction — took July's national person-hours from 27,563,068 to 24,324,401, a fall of 11.8%. That looked like grounds to re-derive the cutoffs. It was not. Rebuilding the pre-change code against pre-change data and comparing 78 settled county-months (May–July):

| | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| before | 98.890 | 99.313 | 99.568 | 99.745 | 99.820 |
| after | 99.064 | 99.333 | 99.576 | 99.748 | 99.820 |

Every cut sits at the percentile it always did — A at 97%, B at 76%, C at 33→32%, D at 10→9% — and **exactly one county-month changed letter** (Waterford, May, D→C). The grade mix went A2 B16 C30 D20 F10 to A2 B16 C31 D19 F10.

The lesson is that the national total and the grading distribution are not the same measurement and do not move together. The total is population-weighted and dominated by a handful of large events, so stripping 2.6M person-hours out of Donegal moves one county-month a long way while leaving the median of 78 where it was. A change big enough to reshape the headline can be invisible to the cutoffs, and re-deriving them on that evidence would have been fitting to noise — and would have broken the comparability the fixed thresholds exist to provide.

What did move was how much work the quality knock was doing: 7 of 78 county-months published worse than their availability alone before the four changes, 8 after — and Donegal's July F had become the knock alone, its availability having risen from 97.015% to 99.153%. That is what prompted unbundling the knock from the grade entirely, above; the figures in this section predate that and describe the last state in which the knock existed.

[water-sla-benchmarks.md](../water-sla-benchmarks.md) explains why Ofwat/CRU numbers (~99.99%+ availability equivalents) cannot be borrowed: they count measured minutes without water at the tap for ≥3-hour interruptions, whereas this index counts whole published-notice durations across an assumed 500 m population, including "may be affected" notices. The intent is to keep these thresholds fixed so months stay comparable, and revisit after a full year of seasons.

## Radius sensitivity (checked 2026-07-16)

Rebuilding May and June 2026 at 300 m / 500 m / 1 km affect-radii: county **rankings** by availability are robust (Spearman rank correlation vs the 500 m baseline: 0.93/0.91 at 300 m, 0.90/0.86 at 1 km), but absolute **grades** are not — 48 of 52 county-months change letter somewhere across the range, because affected population scales roughly with radius², shifting everyone against the fixed thresholds together. Read the letters as calibrated to the 500 m assumption; read the ordering of counties as real. (A percentile-based grading would be radius-invariant, at the cost of losing fixed meaning across months.)

## Density sensitivity (checked 2026-10-04)

The radius check above scales every county together, so it cannot see what a fixed *area* does between counties: it catches people in proportion to density. On the 2026-10-04 release, May to September:

| county | outage notices per 10k people | median people charged per event | mean monthly availability |
|---|---|---|---|
| Dublin | 3.7 | 2,989 | 99.44% |
| Mayo | 22.3 | 306 | 99.64% |
| Donegal | 26.6 | 300 | 99.42% |
| Kerry | 41.4 | 267 | 99.27% |

Notices are counted once per `reference_num`, by start date: summing the payload's monthly counts instead double-counts the 100 of 5,968 that run across a month end. Of the outage notices, 3 carry the `HM` investigation reference that cannot pair with its resolving sibling (data-quality.md, "'We are investigating' notices"), so cross-reference duplication does not move the rate.

Dublin publishes a tenth of the notices per head and is charged ten times the people for each, so it grades below counties with six times its notice rate. Whether a Dublin street burst really reaches 3,000 people the feed cannot say: a pattern search finds 1 notice of 14,467 stating a customer count (238842, a boil notice lift).

`uisce-eval-footprint` (on branch `archive/eval-footprint`, not on `main`: the simplification plan removes what it measures) rebuilds the county figures under the opposite assumption, a fixed *headcount*: each pin affects its nearest Small Areas until they hold N residents. The variant is rescaled to the published national person-hours, so only the distribution between counties differs and the fixed cuts still apply. Over the six finished months (156 county-months):

| nearest N people | rank correlation with the published ordering | county-months changing letter |
|---|---|---|
| 300 | 0.61 | 94 |
| 1,000 | 0.60 | 91 |
| 3,000 | 0.60 | 92 |

N does not matter, which is the rescaling doing its job. The movers at N = 1,000, by pooled rank of 26: Dublin 18th to 1st, Kildare 22nd to 7th, Louth 15th to 6th, Cork 25th to 18th; Leitrim 5th to 19th, Roscommon 10th to 21st, Kilkenny 6th to 13th, Longford 17th to 24th, Mayo 9th to 16th. What holds under both: Tipperary is last, Kerry, Sligo, Donegal and Waterford sit in the bottom eight, and Carlow, Wicklow, Cavan and Galway in the top five.

Neither footprint is the truth. A city burst is isolated by valves to far fewer than everyone within 500 m, and a rural trunk main cuts off more than the 267 people near its pin, so the fixed area probably overstates dense counties; the fixed headcount is the far bracket, not a correction. The reading that survives is narrower than the one under "Radius sensitivity": the two ends of the table are real, and the middle of the ordering, with most of the letters, is the footprint assumption. Nothing published changed with this check except the page copy, which now says so; what to do about the letters is in [roadmap.md](../roadmap.md).

## Supply zones as a limit on the circle (measured 2026-10-05)

Uisce Éireann publishes its Water Supply Zones as polygons on the feed's own ArcGIS org (`services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/watersupplyzonesDWQ_DeptView/FeatureServer/0`, layer `IWGIS_WSZ_Boundary`): 688 zones, each with `CENSUSPOPULATION`, connection counts (`WPRN_*`) and distribution mains length in metres (`DISMAINSLENGTH`, 53,756 km in all); last edited 2026-09-29, 81 boundaries `UnderReview`, no licence stated on the item (the matching water.ie spreadsheet is CC BY 4.0). District Metered Area boundaries are not published. The feed carries no zone field, so a notice reaches its zone by point-in-polygon on its pin. Measured on the 2026-10-04 release, May to September, with shapely in a scratch probe (nothing committed):

- 95.4% of 14,356 distinct pin coordinates fall in a zone, 19 in two. 78.9% of the Small Area population has its centroid in a zone; the rest is on group or private schemes the feed does not cover, and the circle charges it today.
- **Clipping** the circle to Small Areas whose centroid lies in the pin's zone cuts national person-hours by 6.3% (Cavan 14%, Dublin 11%, Roscommon 0%). Rank correlation of county availability with the published ordering 0.99; 4 of 156 county-months change letter, all up one (Laois May C to B, Longford May D to C, Offaly June C to B, Cork August D to C). Dublin moves 18th to 15th.
- The clip cannot act on 2,227 coordinates (16%): the pin is in a zone but no Small Area it charges is. 1,945 of them charge only areas outside every zone, because 4,802 coordinates (33%) have no centroid within 500 m and fall back to the nearest Small Area up to 8 km away. A centroid is too coarse a test for a rural zone.
- **Capping** each notice at its zone's population instead changes almost nothing (-0.4% person-hours, 1 letter): circles are nearly always smaller than zones (median zone 861 people, mean 6,315; Fingal Zone 1 is 293,411).

So the zone is a correction to the circle, not an answer to the density question above: Dublin's zones run to six figures, and no limit drawn from them touches its 3,000 people per notice.

Normalised by mains length, outage notices per 100 km run from Carlow 4.4, Louth 4.7 and Leitrim 4.8 to Wexford 16.9, Waterford 20.7 and Kerry 23.8, with Dublin 8.7 (13th). That ordering correlates 0.60 with notices per 10,000 people, and agrees with the ends that held under both footprints. Zones are keyed to a local authority, not a county (Dublin's four and the two cities merged by hand); Louth's zones hold 110% of its census population, so some cross the county line.

## The national top ten (added 2026-08-01)

**Superseded 2026-10-06:** the page now ranks the ten *longest*, by time to "works complete"; see "The estimate is removed" above. What follows is the person-hours ranking it replaced.

`#top` ranks the ten largest **individual** disruptions nationally in a month, by person-hours. Nothing else on the site does: person-hours are computed per county and per area, so a reader who wants to know what actually happened in July gets 26 county rows rather than the burst that caused them. The distribution justifies the page — in July 2026 the ten largest events were **21.9%** of every person-hour lost nationally, and one Donegal reservoir interruption was 9% on its own.

Three decisions worth recording:

**Person-hours are clipped to the month**, using the same bounds `region_month` uses, rather than attributing a whole event to the month it started in. That keeps the ranking summable against the county figures already published — the "these ten are a fifth of July" headline is only true under clipping — at the cost that `person_h` is not exactly the two displayed figures multiplied (`hours` is rounded to 1dp for the payload; `person_h` comes from the unrounded span, because matching the county totals matters more).

**Complete months only.** The in-progress month reshuffles between builds as open events accrue toward the 14-day cap and then resolve, so a "largest disruptions of this month" list would contradict itself twice a day. The front end shares `curMonth` with the other views but falls back to the newest complete month, since `curMonth` defaults to the in-progress one.

**The end badge counts notices, not events.** `Region.observed_end` is OR'd across an event's pins, which is what the monthly median wants (does this event carry *an* end signal?) but is wrong for a per-event verdict: July's largest event, `DON00115765`, has 18 pins of which exactly **one** reported a completion and 17 only stated a schedule. Badging that "completion confirmed" would present a plan as a measurement, which is the failure this whole site is organised against. The payload therefore carries `pins` / `confirmed` / `scheduled` and the page says "partly confirmed — 1 of 18 notices reported complete".

## An event with no usable end is charged a typical span, not a zero (settled 2026-08-15)

**Superseded 2026-10-06:** with availability gone there is no total to charge, and these events are a token again, counted in `no_end_n`; see "The estimate is removed" above.

The events with no usable `notice_to_end_seconds` were being kept out of the published median **and** given a token 1-second footprint in the availability arithmetic. The first is right; the second was not, and this splits them.

**The population is not what its name suggests.** Of 4,473 outage-class events on the 2026-08-15 corpus, 204 took the token footprint. Only **4** of those are genuinely `not_found`. **200** are the negative-span family — the end is known, the *publication timestamp* is not, because the feed re-stamps `STARTDATE` in place (measured 2026-07-20, [data-quality.md](../data-quality.md)). A further 29 are open with no signal at all and take the accrue-to-now branch instead. So this is overwhelmingly "closed, with a known end, and a broken start", not "never closed".

**Why the median still excludes them.** Three reasons, in order of weight:

1. **The precedent.** 894 `scheduled_end_with_time` events are already excluded from the headline because a plan is not an observation (the 2026-07-20 section below). An imputed category median is *weaker* evidence than a published plan. Letting imputations in while keeping plans out would be incoherent.
2. **Complete-case analysis is valid here.** Only the outcome variable (duration) is incomplete, and two checks say missingness is not related to it: Kaplan-Meier treating the open-no-signal events as censored gives **13.9h against the naive 13.4h**; and for no-signal cases carrying a `closed_at`, start→`closed_at` runs a median 80.8h against a calibrated 70.1h overshoot measured on observed completions, implying **~10.7h** against 16.9h for observed. The missing events are *shorter*, not longer. This is the check that would have made exclusion dishonest had it failed.
3. **It barely moves.** Pooling all 204 in at category medians gives 12.9h against 13.4h — and downwards, because 102 of the 204 are `mains_repair`, whose median is 7.5h.

**Why availability must not.** Its denominator is fixed by population and calendar, so an event that supplies no duration supplies a **zero** — "exclude" and "impute 0" are the same operation, and there is no third option the way there is for a median. One second is not a conservative reading of a burst main; it is a claim that it disrupted nobody. The token was introduced to stop open negative-span cases accruing to the 14-day cap (`ended_by_publication`), and it fixed that, but it was never the right *value*.

**What is charged.** `SpanTable` in `site.py`: the median observed-completion span for that `work_category`, capped at `CAP_DAYS`, requiring n ≥ 15 before a category speaks for itself and falling back to the global observed median otherwise. Evidence is observed completions only — the same tier the headline rests on. The negative-span family is anchored **backwards** from the end it does know, so the hours land on the days the works ran rather than on the day the notice finally went up; `not_found` cases anchor forwards from publication. With no observed completion anywhere in the corpus there is no table and the token stands, because a guess with nothing behind it is worse than the zero it replaces.

**What it moved** (2026-08-15 corpus, measured by building both ways over the same rows):

| | Apr | May | Jun | Jul | Aug |
|---|---|---|---|---|---|
| `median_completion_h` | 7.1 → 7.1 | 12.6 → 12.6 | 15.8 → 15.8 | 12.5 → **12.7** | 15.2 → 15.2 |
| `imputed_n` | 23 | 39 | 53 | 58 | 43 |
| person-hours | +2.9% | +3.4% | +2.4% | +2.3% | +4.4% |
| national availability | −0.0118pp | −0.0154pp | −0.0130pp | −0.0144pp | −0.0200pp |

Four county-months move down one grade: Limerick 2026-04 B→C, Mayo 2026-05 C→D, Monaghan 2026-08 C→D, Offaly 2026-08 B→C. The worst-hit single county-month is Offaly 2026-08 at −0.179pp; the median affected county-month is −0.018pp.

**July's headline moved, and that is a real leak.** `has_end` and `imputed` are OR'd across an event's pins, and an event's span is the union of its pins' intervals. **5 events of 4,473** carry both an observed completion on one pin and an imputed span on another, so their unioned spans grew and the July median rose 0.2h. This is the same mechanism by which a scheduled-end pin already contributes its announced interval to an event counted as observed, so it is consistent with existing behaviour rather than new — but it does mean the headline is not perfectly insulated from the estimate. Separating the tiers would need a second per-tier interval accumulator in `Region` for a 0.2h effect in one month of five, which is not worth the machinery.

**Prior art.** Ofwat's supply interruptions commitment is the closest regulated analogue — property-minutes as a total, same shape as availability. Its default position is that "there are no exclusions"; where telemetry or logging is unavailable, start and stop times are taken from customer contact, flow/pressure indications or **"verified modelled data"**, so a missing timestamp is modelled rather than used to discard the event. It also requires companies to report "what proportion of its start/stop times has been informed by each data source", which is what `imputed_n` on the page is. See [PR24 common performance commitments](https://www.ofwat.gov.uk/wp-content/uploads/2023/05/Water-supply-interruptions.pdf) and the [2018 reporting guidance](https://www.ofwat.gov.uk/wp-content/uploads/2018/03/Reporting-guidance-supply-interruptions.pdf).

## Known limitations
- **We deviate from Ofwat's precautionary principle.** It resolves uncertain interruption data toward "the start and finish times and the properties affected that will give the **highest** supply interruption value". A category median is a central estimate, not the highest, so the imputed events are charged less than that principle would ask. Chosen because the site's own claim is a floor rather than a worst case, but it is a deviation and it favours the utility.
- *Retired 2026-10-06 with the person-hours it measured, and `eval_overlap.py` with it:* overlapping events in the same area double-count person-hours: **measured 2026-08-18 at 2.0% of national outage person-hours** (1.58M of 80.3M person-hours over Apr–Aug 2026, August partial and still accruing, ranging 0.5–2.5% by month), by re-unioning intervals per Small Area across events, which cannot double-count by construction. It was measured with `uv run uisce-eval-overlap` (`src/uisce/eval_overlap.py`), which printed the published-vs-exact split per month and changes nothing. Left uncorrected deliberately: the double-count is pessimistic (overstates disruption), a correction would touch the availability arithmetic itself, and it is smaller than the modelling error already conceded by the 500 m radius assumption.

  **The first run of this said 3.6%, and it was wrong in two ways** (both found in review the same day, both now pinned by tests in `tests/test_eval_overlap.py`). It de-overlapped per *pin* while the published side accrues per *event*, so an event's own pins — staggered in time and place, as July's 18-pin, 385h event is — read as double-counting: a two-pin event with no overlap at all reported 50%. And it resolved cases without the `SpanTable`, so every case with no usable end signal took a 1-second token footprint instead of the imputed span the site charges it, dropping the published total to 77.2M against the site's own 79.8M. Correcting both moves the figure from 3.6% to 2.0% and the monthly range from 3.0–5.1% to 0.5–2.5%. The lesson for the next probe of this kind: reproducing a published number means reproducing the *whole* resolution path, and a diagnostic that cannot reproduce the total it is a fraction of is measuring something else.
- The 14-day cap applies to each *notice*, not each event, so an event published as several staggered notices can span longer than 14 days — July's largest ran 385h (16 days) across 18 pins published over three days. The page copy says so.
- The scheduled-end events that accrue disruption time are accruing an *announced* interval, not an observed one. They are kept out of the headline median but not out of the availability percentage, so availability carries an assumption the median does not. As of 2026-08-15 the same is true one tier further down, for the events charged an imputed span.
- `start_date` is the notice publication time, so durations are a floor on true outage length (overnight events are typically posted the next working morning — see [data-quality.md](../data-quality.md)).
- "May be affected" notices count everyone in the radius; the index measures disruption exposure, not confirmed loss of supply.
- County populations are hardcoded Census 2022 figures in site.py.
- The current month grades harshly while in progress, for three separate reasons: open cases accrue to "now" against a part-elapsed denominator; some feed `status` values are known to be stale; and cases downloaded since the last `uisce-infer` run have no end signal at all, which sends them down the same accrue-to-now branch — 98% of the never-inferred backlog is `status = 'Open'`, so this is concentrated exactly where it does most damage. See [pipeline-dependencies.md](../pipeline-dependencies.md).
- "Open cases" on the page is a right-now snapshot of `Case.is_open` (`status = 'Open'`, still served by the feed, and not past a completion the notice's own text reported - see "The notice's own completion closes it" below), attached to the county rather than the selected month, so it does not vary as you page through months (the copy says so). Of 508 open cases on the 2026-07-20 snapshot: 127 are future-dated advance notices of planned works, 20 carry a description that already says "works are now complete" (genuinely stale feed status; these no longer list), 72 more have a passed scheduled end (these still do), and 13 are long-lived boil / do-not-consume notices that are correctly still open.
