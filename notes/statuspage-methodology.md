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

Duration inputs come from `inferred_cases.end_duration_seconds`, capped at 14 days. The genuinely long events (40–87-day conservation restrictions) are classed degraded and never accrue, so the cap is a backstop, not the outlier strategy — see the outliers section of [data-quality.md](data-quality.md).

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
- `start_date` is the notice publication time, so durations are a floor on true outage length (overnight events are typically posted the next working morning — see [data-quality.md](data-quality.md)).
- "May be affected" notices count everyone in the radius; the index measures disruption exposure, not confirmed loss of supply.
- County populations are hardcoded Census 2022 figures in site.py.
- The current month grades harshly while in progress: open cases accrue to "now" against a part-elapsed denominator, and some feed `status` values are known to be stale.

## What the site copy says, deliberately

The page presents itself as a tracker of **announced disruptions and time-to-fix**, not of "availability": the headline percentage is labelled "person-time free of announced disruption", and each month shows a median time-to-fix over resolved events (events with a real end signal only, so open cases and unknown ends can't drag the median). This is the claim the data can actually support — see the eval in [end-time-eval.md](end-time-eval.md) for how the LLM-extracted end times behind it are validated.

## Possible next steps

Population served per named supply scheme from the EPA public water supplies register (boil notices name their scheme in `location`); a locality-level component view (statuspage-style groups: county → towns); a prompt tweak for the nightly-works pattern where the model currently extracts date-only ends (see [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) — qwen got `scheduled_end_with_time` right on those 8 cases); GitHub Pages publishing from the weekly Build DB workflow.
