# Status site methodology

How `uisce-site` (src/uisce/site.py) turns `out/uisce.db` into the statuspage-style site in `out/site/`, and why each modelling decision was made. Companion notes: [data-quality.md](data-quality.md) for what the underlying fields can and cannot support, [water-sla-benchmarks.md](water-sla-benchmarks.md) for how the grades relate to real regulatory SLAs, and [population-data-sources.md](population-data-sources.md) for the Census join.

## Why not plain "uptime"?

The obvious statuspage metric — fraction of the month with no active outage anywhere in the county — collapses at county granularity: Cork came out at 2% "uptime" for May 2026 because somewhere in Cork almost always has an active case. A county is not a single supply component, and binary county-level uptime punishes size and reporting diligence, not service quality.

The replacement is **population-weighted availability**, a SAIDI-style measure: each notice pin is assumed to affect the Census 2022 Small Areas whose centroids lie within 500 m (nearest Small Area within 8 km as a rural fallback); an event's affected population is the union of its pins' Small Areas, capped at the county population. Then availability = 100% − person-outage-seconds ÷ (county population × observed seconds). Under this measure Cork's May 2026 is ~99.2%, and a burst main serving a 2,000-person town no longer reads as "Cork is down".

## Severity classes

Each case maps to one class from `work_category` plus the impact flags, tested in that order:

1. `boil_notice_lifted` → ignored as an event (it is the good-news end of an earlier notice; used only for pairing, below)
2. `do_not_drink` / `boil_water_notice` flags, or category boil_notice_issued / consumption_notice_issued / discolouration → **quality**
3. water_conservation / low_pressure categories, or `water_restrictions` / `reduced_pressure` flags → **degraded**
4. burst_main, reservoir_interruption, water_treatment_plant_interruption, pump_station_interruption, pump_failure, power_outage → **outage**, regardless of `work_type` (the title itself announces lost supply)
5. mains_repair / valve_repair / pump_repair / NULL category, when not marked Planned → **outage** (emergency repairs normally shut off supply)
6. everything else — investigations, leak detection, hydrant works, installations, and anything Planned → **works**

Only the **outage** class accrues availability downtime. This is deliberate: an F grade should mean people lost water, not that a county ran many investigations. Before this split, `investigation` alone contributed ~8% of accrued hours (4,090 h in May+June 2026 against 27,128 h from burst mains). The `water_outage` feed flag cannot do this job — it is set on 97% of all cases.

Interval inputs come from `inferred_cases.notice_to_end_seconds`, capped at 14 days. The genuinely long events (40–87-day conservation restrictions) are classed degraded and never accrue, so the cap is a backstop, not the outlier strategy — see the outliers section of [data-quality.md](data-quality.md).

## Events, intervals, and edge cases

- Cases are grouped into events by `reference_num` (a 13-pin multi-pin publication counts once); each event's pin intervals are unioned before any accounting.
- Open cases with no inferred end (e.g. an active boil notice — `boil_notice_issued` cases never have inferred durations) accrue from publication until "now", capped at 14 days.
- Closed cases with no usable end signal keep a token 1-second footprint: their start day still colours and they count as events, but they add no downtime. Without this, ~300 `not_found` cases silently produced false-green days.
- Nothing accrues beyond "now" (a scheduled end in the future is not downtime yet) or before **2026-04-20**, when data collection began; earlier days render as "no data" and each month's denominator is the observed window only. Collection start matters a lot: April 2026 originally graded far better than later months purely because its first three weeks were unobserved.
- Boil-water notices are lifted by separate cases with fresh reference_nums, so issue → lift is paired by county + normalised scheme name from `location` ("Ardfinnan Regional Public Water Supply" → "ardfinnan"), with up to 2 days of publication-order slack. On the July 2026 snapshot only one notice pairs — every other lift on file refers to a notice issued before collection began — but coverage grows with history.

## Grades

A–F comes from availability: **A ≥ 99.9%, B ≥ 99.75%, C ≥ 99.45%, D ≥ 99.0%, else F**, and any active boil-water / do-not-drink / do-not-consume notice knocks the grade one step (D and F stay F). Discolouration is shown but never knocks.

The thresholds are calibrated to the observed distribution of county-months (p10 ≈ 98.9%, median ≈ 99.6%, p90 ≈ 99.87% on the July 2026 snapshot) — they are honest relative to this dataset, not imported from a regulator. [water-sla-benchmarks.md](water-sla-benchmarks.md) explains why Ofwat/CRU numbers (~99.99%+ availability equivalents) cannot be borrowed: they count measured minutes without water at the tap for ≥3-hour interruptions, whereas this index counts whole published-notice durations across an assumed 500 m population, including "may be affected" notices. The intent is to keep these thresholds fixed so months stay comparable, and revisit after a full year of seasons.

## Radius sensitivity (checked 2026-07-16)

Rebuilding May and June 2026 at 300 m / 500 m / 1 km affect-radii: county **rankings** by availability are robust (Spearman rank correlation vs the 500 m baseline: 0.93/0.91 at 300 m, 0.90/0.86 at 1 km), but absolute **grades** are not — 48 of 52 county-months change letter somewhere across the range, because affected population scales roughly with radius², shifting everyone against the fixed thresholds together. Read the letters as calibrated to the 500 m assumption; read the ordering of counties as real. (A percentile-based grading would be radius-invariant, at the cost of losing fixed meaning across months.)

## Known limitations
- Overlapping events in the same area double-count person-hours.
- The scheduled-end events that accrue disruption time are accruing an *announced* interval, not an observed one. They are kept out of the headline median but not out of the availability percentage, so availability carries an assumption the median does not.
- `start_date` is the notice publication time, so durations are a floor on true outage length (overnight events are typically posted the next working morning — see [data-quality.md](data-quality.md)).
- "May be affected" notices count everyone in the radius; the index measures disruption exposure, not confirmed loss of supply.
- County populations are hardcoded Census 2022 figures in site.py.
- The current month grades harshly while in progress, for three separate reasons: open cases accrue to "now" against a part-elapsed denominator; some feed `status` values are known to be stale; and cases downloaded since the last `uisce-infer` run have no end signal at all, which sends them down the same accrue-to-now branch — 98% of the never-inferred backlog is `status = 'Open'`, so this is concentrated exactly where it does most damage. See [pipeline-dependencies.md](pipeline-dependencies.md).
- "Open cases" on the page is a right-now snapshot of `status = 'Open'`, attached to the county rather than the selected month, so it does not vary as you page through months (the copy says so). Of 508 open cases on the 2026-07-20 snapshot: 127 are future-dated advance notices of planned works, 20 carry a description that already says "works are now complete" (genuinely stale feed status), 72 more have a passed scheduled end, and 13 are long-lived boil / do-not-consume notices that are correctly still open.

## The published time metric is notice → *observed* completion (settled 2026-07-20)

The metric is the span from **notice publication** (`cases.start_date`) to the end the notice reports. It is not outage duration, and the naming across code, schema and site copy now says so: the DB column is `notice_to_end_seconds`, the site fields are `median_completion_h` / `completed_n`, and the page reads "median notice → completion".

Two separate honesty problems were fixed together here.

**1. The start is a publication timestamp, not an onset.** Long documented in [data-quality.md](data-quality.md), and resolved there: no better start basis exists in the feed, so the fix is naming rather than modelling. Every figure on the page is a **floor** on true length.

**2. The end was pooling observations with plans.** `end_source` distinguishes an observed completion (`completion_update` — "works are now complete at 10:39am") from a stated schedule (`scheduled_end_*` — a plan that may not have been met). The site was pooling both under "median time to fix ... resolved", which claims observation for all of it. Measured on the 2026-07-20 corpus, restricted to the `outage` severity class that actually feeds the metric:

| end signal | n | median |
|---|---|---|
| `completion_update` (observed) | 3,166 | **17.0h** |
| `scheduled_end_with_time` (a plan) | 894 | **5.4h** |
| pooled — as previously published | 4,060 | 9.3h |

Scheduled ends were 22% of the metric and dragged the headline from 17.0h to 9.3h — a far larger distortion than the ±2–3h start-side noise that motivated the pv3 discussion. The gap is not purely bias (scheduled ends skew to short planned windows, observed completions to unplanned bursts) but that is exactly why pooling them is wrong: they are different populations answering different questions.

**Resolution:** scheduled ends still **accrue** disruption time and person-hours — a published plan is the best interval available and dropping it would under-count exposure — but they are excluded from the published median and reported separately as "+N scheduled-only". `OBSERVED_END_SOURCES` in `site.py` is the single switch. At event level the split holds every month (observed 7.1/12.6/15.8/10.2h against scheduled 4.8/5.3/4.4/4.3h for Apr–Jul 2026).

See the eval in [end-time-eval.md](end-time-eval.md) for how the LLM-extracted end times behind this are validated.

## Possible next steps

Population served per named supply scheme from the EPA public water supplies register (boil notices name their scheme in `location`); a locality-level component view (statuspage-style groups: county → towns); a prompt tweak for the nightly-works pattern where the model currently extracts date-only ends (see [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) — qwen got `scheduled_end_with_time` right on those 8 cases); GitHub Pages publishing from the weekly Build DB workflow.
