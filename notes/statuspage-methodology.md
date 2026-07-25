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
- Open cases with no inferred end (e.g. an active boil notice — `boil_notice_issued` cases never have inferred durations) accrue from publication until "now", capped at 14 days. Exception: a case whose own text says it already ended — an extracted end that precedes publication (nulled in `build.py`) or a `lifted_immediate` — gets the token 1-second footprint instead, whatever the feed's `status` claims (`ended_by_publication` in `site.py`; see [data-quality.md](data-quality.md) for the 532-case family behind this).
- Closed cases with no usable end signal keep a token 1-second footprint: their start day still colours and they count as events, but they add no downtime. Without this, ~300 `not_found` cases silently produced false-green days.
- Nothing accrues beyond "now" (a scheduled end in the future is not downtime yet) or before **2026-04-20**, when data collection began; earlier days render as "no data" and each month's denominator is the observed window only. Collection start matters a lot: April 2026 originally graded far better than later months purely because its first three weeks were unobserved.
- Boil-water notices are lifted by separate cases with fresh reference_nums, so issue → lift is paired by county + normalised scheme name from `location` ("Ardfinnan Regional Public Water Supply" → "ardfinnan"), with up to 2 days of publication-order slack. On the July 2026 snapshot only one notice pairs — every other lift on file refers to a notice issued before collection began — but coverage grows with history.

## The county drill-down: county → towns (added 2026-07-25)

Clicking a county opens a per-county view (hash route `#county/<name>`, same single page) which carries the tabular detail that used to expand inline, plus a breakdown of the county into the named places its cases fall in.

**The geography is Census settlements, not the feed's own text.** `cases.location` looks tempting — for Kildare it reads `Leixlip`, `Prosperous`, `Celbridge`, `Newbridge`, `Naas` — but it has 3,866 distinct values nationally and fragments badly: `Newbridge` / `Newbridge,` / `Mount Carmel, Newbridge` are three keys for one town, estate and street names appear as if they were places (`Marlton Park`, `Ashgrove Crescent`, `Wolstan Haven Road`), and it carries no population, so nothing can be weighted by it. The geocode cache is worse: 94% of rows have only `city_district`, which is mostly Electoral Divisions (`Naas Urban ED`) and bridges (`Bond Bridge`).

Instead each pin is placed in the CSO Urban Area (settlement) holding the largest share of its 500 m affected population, via `data/sa_towns.csv` — see [population-data-sources.md](population-data-sources.md) for that join. Names come out canonical (`Kildare`, not `Kildare Town`; `Coill Dubh (Blackwood)`), the fragmented location strings consolidate onto one row, and every town arrives with a Census population.

Four decisions worth recording:

- **One home per pin, by dominant share.** A pin could be split across every settlement its footprint touches, but the median dominant share is **1.00** on the July 2026 corpus — pins essentially never straddle a boundary — so splitting would buy nothing and would stop per-town case counts summing to the county's.
- **Population attributed to a town is the footprint ∩ town, not the whole footprint.** A pin at the edge of a village would otherwise log person-hours for people who don't live in it, and could drive availability below zero. County figures still take the whole footprint, so town person-hours sum to ≤ the county's, never more.
- **Only areas in the case's own county are considered.** Border pins are real — a Kildare-labelled notice whose footprint reaches Blessington, Co. Wicklow — and re-homing one across a county line would contradict the page it appears on, so the pin takes the best area that *is* in its county rather than being set aside.
- **No letter grades at town level.** The A–F thresholds are calibrated to the distribution of county-months; against a 500-person denominator an ordinary burst main reads F. Availability *is* published, because that is the figure the drill-down exists to show — a 24-hour event that moves a county of 62,000 by 0.18 points moves the 1,000-person town it happened in by 11. The page says so in as many words.

**About 40% of cases fall outside any settlement** — not a defect of the geography, since most of the network (reservoirs, treatment plants, trunk mains) runs between towns rather than through one. Those are named by their Electoral Division; see the countryside section below.

**No day bars at area level.** Deliberate: the day arrays are the bulk of the payload, and 1,767 area breakdowns × months of 31 two-element arrays would multiply `data.js` several times over for a chart nobody would read at that granularity. Counts, person-hours and availability only.

**Payload, and when to change the shape.** `data.js` carries every county, area and month because the page is one file that must work opened straight off disk — `fetch()` fails on `file://`, a `<script>` tag does not. Area-months are ~76% of it, so they are written sparsely: zero severities, zero person-hours and zero resolved counts are all omitted and the reader defaults them, and availability is rounded to the two decimals the page actually renders. Open cases are stored once, on the county, tagged with their area, rather than a second time under each area. Together that took the file from 960 KB to **645 KB** (84 KB gzipped).

That is a constant-factor saving, not a bound: each new month adds roughly **85 KB**, so the file passes 1 MB in about four months. The fix when it matters is to emit one `county/<name>.js` per county and load it with an injected `<script>` tag on navigation — off-disk use survives, the index drops to about 150 KB, and growth stops being the index's problem. Deliberately not done yet; revisit at 1 MB.

### `closed_at` gives a past month something to say

The site's open-case figures are a right-now snapshot with no month dimension, so a historic month previously had nothing to report beyond its bars (see the known limitation below, and PR #21 which hid those figures on non-latest months for exactly that reason). `cases.closed_at` is the one field that does carry a month for a case that is no longer open, so the county view adds an **"observed to close in <month>"** section, and each town row a resolved count.

Its coverage is partial by construction and the copy says so: NULL for every case that closed before schema v2, and a case that opens and closes inside one build gap is never observed open, so never stamped. Read it as a floor. This is what lets a county with zero open cases still show something true — Carlow, at 0 open on the July 2026 snapshot, reports 8 cases observed closing that month across Rathvilly, Carlow town and the countryside around them.

### Cities: a settlement over 50,000 is split into Local Electoral Areas

CSO Urban Areas treats a city and its suburbs as **one settlement** — `Dublin city and suburbs` is a single area of 1,261,884 people holding **83% of Dublin's cases**, so the drill-down did nothing at all there. Measured across the five:

| agglomeration | population | cases | share of the county's |
|---|---|---|---|
| Dublin city and suburbs | 1,261,884 | 808 | **83%** |
| Cork city and suburbs | 222,288 | 257 | 25% |
| Galway city and suburbs | 85,876 | 124 | 32% |
| Limerick city and suburbs | 102,287 | 82 | 22% |
| Waterford city and suburbs | 60,079 | 40 | 14% |

Any settlement over **50,000** is therefore broken into the Local Electoral Areas its Small Areas fall in (`SPLIT_ABOVE_POP` in `towns.py`). That threshold currently selects exactly those five — the next largest settlement is Drogheda at 44,135 — but it is a population rule rather than a name match so the CSO renaming them cannot break it. Dublin goes from one row to **40 rows, the largest 8 disruptions**.

**LEA in the city, ED in the countryside — the rule, stated once.** The drill-down uses *the finest official geography whose names arrive usable*. That selects different layers in different places, which looks arbitrary until you look at the names:

| | EDs involved | letter-suffixed |
|---|---|---|
| Urban Small Areas | 1,492 | **242 (16%)** |
| Rural Small Areas | 2,552 | **0 (0%)** |

City EDs come as `Bishopstown A`…`E` and `Arran Quay A`…`E` — 211 of them in Dublin — so using them means inventing a name-merging heuristic, the same string munging this project refused when it declined to key the drill-down on `cases.location`. Rural EDs need nothing: `Ardmayle`, `Nodstown`, `Ballymackey` arrive clean and are the names locals use. So the city stops at the LEA and the countryside goes all the way to the ED. Row counts follow from that choice; they are not the reason for it.

An earlier draft of this note argued the reverse — that ~4 cases per ED row was too thin for a city — while the rural tier happily publishes rows at 2.9. That was two tiers justified on contradictory grounds, and the thinness half of it had already been withdrawn (the settlement layer publishes single-case rows for villages of 500). The suffixing above is the real distinction and the only one this note now rests on.

**The uniform alternative, consciously rejected.** Grouping the countryside by LEA as well would leave just two geographies and collapse 1,172 rural rows to roughly 200, with familiar names — `Around Cashel` rather than `Around Ardmayle`. It is rejected because a rural LEA is enormous: "Around Cashel" would cover some 300 km² and place a case 20 km away in the wrong parish, which is a worse falsehood than an unfamiliar but correct name. Uniformity is not worth that.

### The LEA names are administrative, not vernacular

This is the real cost of the choice and it should not be oversold. LEA names are electoral compounds stitched from the districts a boundary happens to cover. Of Dublin's 28 areas:

- **12 are hyphenated compounds** — `Kimmage-Rathmines`, `Cabra-Glasnevin`, `Rathfarnham-Templeogue`, `Ballymun-Finglas`, `Artane-Whitehall`, `Firhouse-Bohernabreena`, `Killiney-Shankill` … Nobody says these. They pair districts that residents would not group, and in some cases actively would not.
- **5 are compass-qualified**: `North Inner City`, `Tallaght Central`.
- **11 are plain place names**: `Clontarf`, `Blackrock`, `Stillorgan`, `Dundrum`, `Lucan`, `Clondalkin`, `Castleknock`, `Dún Laoghaire`.

Cork's are worse — `Cork City South East` and three siblings, pure quadrants.

The compound is ugly but **not wrong**: the polygon genuinely spans both places, so relabelling `Kimmage-Rathmines` as `Rathmines` would file a Kimmage burst under Rathmines. The fix is therefore a finer geography, not a better label — and the vernacular name is not actually lost from the page, because every case in the open and resolved lists carries the notice's own `location` beneath it (`Killinarden, Tallaght`, `Chapelizod`, `Bluebell`). The area row is the statistical unit; the notice location is the human one.

**What the ED route would cost, measured.** Stripping the trailing letter from Dublin's 211 EDs leaves **104 distinct names averaging ~12,100 people** — town-sized, and largely vernacular (Crumlin, Chapelizod, Ballymun, Drumcondra, Rathmines East/West, Cabra East/West). Against that: the merging heuristic above, some names that are obscure even locally (Decies, Drumfinn, Botanic), and newer suburbs carrying their own hyphenated compounds (`Clondalkin-Rowlagh`, `Clondalkin-Cappaghmore`), so EDs would not fully escape the compound problem either. Worth revisiting if the compound names prove to be what readers stumble on.

**Slivers are pooled, and that is what avoids name collisions.** LEAs are not contained by the settlement — they run out into the surrounding county — so a part is kept only when **30%** of its LEA lies inside (`MIN_PART_SHARE`). Containment is otherwise excellent: 26 of Dublin's 30 parts are ≥91% inside. The leftovers are small (Dublin 0.6% of the city, Cork 2.8%, Galway 2.2%, Limerick 4.3%, Waterford 9.6% — that last being Ferrybank, on the Kilkenny side) and pool into one `Elsewhere in Dublin city` row.

The threshold is load-bearing beyond tidiness. Four LEA labels collided with an existing settlement row on the same county page — `Swords` in Dublin, `Macroom` / `Carrigaline` / `Cobh` in Cork — and **all four were slivers**, which is structural rather than lucky: an LEA carries a town's name precisely when it is named after a town that is *not* part of the agglomeration, and such an LEA lies mostly outside it. Cork's clipping of the Carrigaline LEA is 942 of its 39,145 people, and unpooled it would have appeared as "Carrigaline" beside the real 18,239-person Carrigaline town row. With the threshold in place, **no county page has two rows with the same name**.

Parts keep the *settlement's* county, not the LEA's. Two agglomerations cross a county line — Limerick's reaches into Clare (Shannon LEA), Waterford's into Kilkenny — so a part filed under the neighbouring county would be refused by the cross-county guard above and vanish from both pages.

### The countryside: "Around <Electoral Division>"

Splitting the cities fixed Dublin and little else, because outside Dublin the biggest row was never the city — it was the single undifferentiated rural bucket, holding **44% of all cases** and ranking first in **22 of 26 counties** (Longford 80% rural, Tipperary 72%, Roscommon 71%, Kerry 63%).

Every Small Area outside a settlement is therefore grouped with the rest of its Electoral Division's countryside, giving 1,172 named rural areas nationally at ~2.9 cases each, with exact Census populations. Tipperary's bucket of 456 becomes `Around Ardmayle`, `Around Nodstown`, `Around Ballymackey` and 110 others.

**The label is "Around X", not "X".** A rural ED is usually the parish *around* the town it is named after, and that town has its own row on the same page — Kildare alone would otherwise show Celbridge, Leixlip, Maynooth, Kill and Carragh twice. Unlike the city slivers these cannot be pooled away, because a rural ED is not a sliver of anything; it is a real place that happens to share a name. Nearly every county has at least one such pair, so the prefix is doing real work rather than decorating.

Two smaller decisions: EDs are keyed by (county, name), which merges the 50 of 3,368 pairs covering more than one ED record — several of those are parts of one ED split by a boundary, and merging beats emitting two rows a reader cannot tell apart. And no threshold is applied: every area with a case that month gets a row, as for towns. The median county shows 33 rows in a month; Cork, the busiest, shows 104.

### Known limitation: pins outside the county they claim

With every Small Area now belonging to a named area, a pin only fails to place when its whole affected footprint lies in a different county from the one the notice names — the feed's `county` disagreeing with its own coordinates, for about 1.5% of case-months. Those collect in a `Pinned outside the county` row that reports its case counts and nothing else: there is no population to divide by, so publishing an availability there would invent a denominator. Tipperary has the most, at 21 case-months.

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

Population served per named supply scheme from the EPA public water supplies register (boil notices name their scheme in `location`); per-county script files once `data.js` reaches 1 MB (see the payload note above); deriving `COUNTY_POP` from the Small Areas, since it is now the only hardcoded population left in the project and every other figure is exact-from-data — it shifts published county availability, so it wants its own change; folding `sa_pop.csv` and `sa_towns.csv` into one file and one command, both being derived from the same ArcGIS layer; an Electoral-Division split for the cities, trading a name-merging heuristic for vernacular area names and retiring the hyphenated LEA compounds (costed in the drill-down section above); a prompt tweak for the nightly-works pattern where the model currently extracts date-only ends (see [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) — qwen got `scheduled_end_with_time` right on those 8 cases); GitHub Pages publishing from the weekly Build DB workflow.
