# Status site methodology

How `uisce-site` (src/uisce/site.py) turns `out/uisce.db` into the statuspage-style site in `out/site/`, and why each modelling decision was made. Companion notes: [data-quality.md](data-quality.md) for what the underlying fields can and cannot support, [water-sla-benchmarks.md](water-sla-benchmarks.md) for how the grades relate to real regulatory SLAs, and [population-data-sources.md](population-data-sources.md) for the Census join.

## Why not plain "uptime"?

The obvious statuspage metric — fraction of the month with no active outage anywhere in the county — collapses at county granularity: Cork came out at 2% "uptime" for May 2026 because somewhere in Cork almost always has an active case. A county is not a single supply component, and binary county-level uptime punishes size and reporting diligence, not service quality.

The replacement is **population-weighted availability**, a SAIDI-style measure: each notice pin is assumed to affect the Census 2022 Small Areas whose centroids lie within 500 m (nearest Small Area within 8 km as a rural fallback); an event's affected population is the union of its pins' Small Areas, capped at the county population. Then availability = 100% − person-outage-seconds ÷ (county population × observed seconds). Under this measure Cork's May 2026 is ~99.2%, and a burst main serving a 2,000-person town no longer reads as "Cork is down".

## Severity classes

Each case maps to one class from `work_category` plus the impact flags, tested in that order:

1. `boil_notice_lifted` → ignored as an event (it is the good-news end of an earlier notice; used only for pairing, below)
2. category boil_notice_issued / consumption_notice_issued / discolouration → **quality**. The feed's `do_not_drink` / `boil_water_notice` flags were read here until 2026-08-18 and are not: both are redundant with the category, and `do_not_drink` is wrong on 9 of 19 cases — see [data-quality.md](data-quality.md)
3. water_conservation / low_pressure categories, or `water_restrictions` / `reduced_pressure` flags → **degraded**
4. burst_main, reservoir_interruption, water_treatment_plant_interruption, pump_station_interruption, pump_failure, power_outage → **outage**, regardless of `work_type` (the title itself announces lost supply)
5. mains_repair / valve_repair / pump_repair / NULL category, when not marked Planned → **outage** (emergency repairs normally shut off supply)
6. everything else — investigations, leak detection, hydrant works, installations, and anything Planned → **works**

Only the **outage** class accrues availability downtime. This is deliberate: an F grade should mean people lost water, not that a county ran many investigations. Before this split, `investigation` alone contributed ~8% of accrued hours (4,090 h in May+June 2026 against 27,128 h from burst mains). No feed flag can do this job: `water_outage` is set on 97% of all cases, and the two health flags carry nothing the category does not (2026-08-18).

Interval inputs come from `inferred_cases.notice_to_end_seconds`, capped at 14 days. The genuinely long events (40–87-day conservation restrictions) are classed degraded and never accrue, so the cap is a backstop, not the outlier strategy — see the outliers section of [data-quality.md](data-quality.md).

## Events, intervals, and edge cases

- Cases are grouped into events by `reference_num` (a 13-pin multi-pin publication counts once); each event's pin intervals are unioned before any accounting.
- Open cases with no inferred end (e.g. an active boil notice — `boil_notice_issued` cases never have inferred durations) accrue from publication until "now", capped at 14 days. Exception: a case whose own text says it already ended — an extracted end that precedes publication (nulled in `build.py`) or a `lifted_immediate` — gets the token 1-second footprint instead, whatever the feed's `status` claims (`ended_by_publication` in `site.py`; see [data-quality.md](data-quality.md) for the 532-case family behind this).
- Closed cases with no usable end signal are charged the typical observed span for their `work_category` (`SpanTable`), anchored backwards from the reported end where there is one. Until 2026-08-15 they kept a token 1-second footprint instead — their start day coloured and they counted as events, but they added no downtime, which is a zero rather than a floor. See the 2026-08-15 section below.
- Nothing accrues beyond "now" (a scheduled end in the future is not downtime yet) or before **2026-04-20**, when data collection began; earlier days render as "no data" and each month's denominator is the observed window only. Collection start matters a lot: April 2026 originally graded far better than later months purely because its first three weeks were unobserved.
- Boil-water **and do-not-consume** notices are lifted by separate cases with fresh reference_nums, so issue → lift is paired by county + lift category + normalised scheme name from `location` ("Ardfinnan Regional Public Water Supply" → "ardfinnan"), with up to 2 days of publication-order slack. The two kinds never cross-pair: a boil notice is ended only by a `boil_notice_lifted`, a do-not-consume only by a `consumption_notice_lifted`. On the July 2026 snapshot only one notice pairs — every other lift on file refers to a notice issued before collection began — but coverage grows with history. A paired end is then capped at `CAP_DAYS` like every other end signal (`paired_end` in `site.py`) — see "A paired lift is capped like any other end" below. See "Do-not-consume notices got the pairing, not the exclusion" for why only half the boil-notice policy carried over.

## Do-not-consume notices got the pairing, not the exclusion (2026-08-18)

A methodology review found a fairness gap: `consumption_notice_issued` and `boil_notice_issued` are published identically — the issue never states its own end (all 7 on file are `not_found`), the lift arrives as a separate case, and the feed's `status` goes stale — yet only boil notices routed through `boil_notice_fate`. The review proposed giving both classes the whole policy. **Half of it was taken.**

**Taken: lift pairing.** A do-not-consume notice can now be closed by a `consumption_notice_lifted` for the same scheme. This is strictly more information than running to the 14-day cap, and it uses real evidence — a published lift. The pairing index is now keyed by `(county, lift category)` so the two kinds cannot cross-pair; `LIFT_OF` names the pairs, and `IGNORE_CATS` derives from it. Zero notices pair on the 2026-08-18 snapshot (both consumption lifts on file refer to notices issued before collection began), which is exactly where boil pairing started.

**Not taken: the staleness exclusion.** Boil notices unpaired and `Open` past `CAP_DAYS` are dropped rather than accrued. That rule rests on evidence: case 221165 sat `Open` while **its own description said** the notice "is now lifted with immediate effect" — the text contradicted the status, so the status was declared untrustworthy. **No do-not-consume notice on file does that.** Whiddy Island (`Open` since 2022-08-18) and Dursey Island (since 2024-08-07) both read as genuine, unlifted notices naming a specific water-quality failure — turbidity and colour on one, elevated manganese on the other — issued after HSE consultation, with explicit instructions that boiling will not make the water safe.

The argument for extending the exclusion was structural identity: the two classes are published alike, so they should be treated alike. That is sound as far as it goes, but it carries the *policy* across without the *evidence* that justified it. The asymmetry in what being wrong costs settles it: dropping a stale boil notice that was in fact lifted loses nothing, while dropping a do-not-consume notice that is still in force removes a live drinking-water warning from the site. The 14-day cap was also calibrated on boil notices, which end when remedial works finish; a manganese problem does not resolve on that schedule.

Practically the exclusion would have changed two cases today — Knockeragh (Cork, 32 days) and Drum (Monaghan, 25 days). Whiddy and Dursey are already invisible: their capped intervals predate the 2026-04-20 collection window.

**Reopen this if** a do-not-consume notice appears whose own text says it was lifted while `status` stays `Open`. That is the 221165 shape, and it is the evidence this decision is waiting on.

## A paired lift is capped like any other end (2026-08-18)

The pairing above originally returned `max(lift, start)` with no upper clamp, on the reasoning that a published lift is a real observed end and not a schedule. That is true and it is not the question. **The 14-day cap is a ceiling on what one notice may charge, not a statement about how long it ran** — an observed `completion_update` is capped, the open-and-accruing branch is capped, the imputed span is capped. A paired lift is not stronger evidence than a completion update, so it does not get an exemption the completion update does not have.

The bug this hides is an inversion. An unpaired notice stops at the cap, and an unpaired boil notice past it is dropped outright. So *finding the lift* — strictly more information, and information that the notice **ended** — made the notice accrue **more**. Evidence of an ending should never raise the charge.

The exposure was not hypothetical and not confined to the do-not-consume class. Open, unpaired, past the cap on the 2026-08-18 snapshot:

| Notice | Class | Open for |
|---|---|---|
| Whiddy Island (Cork) | do-not-consume | 1,460 days |
| Dursey Island (Cork) | do-not-consume | 740 days |
| Carrignagower (Waterford) | boil | 590 days |
| Poulnagunogue (Waterford) | boil | 405 days |
| Scrahan (Waterford) | boil | 250 days |
| Courtbrack (Cork) | boil | 202 days |

Any one of those lifts landing would have dragged its notice forward across **every month on the site at once**, painting the county as a continuous quality event carrying an active health marker. The boil rows are the point: this was never a do-not-consume-only hole, so the clamp lives in one function both classes call rather than being patched into the branch that happened to be under review.

**The cap bounds the arithmetic, not the marker.** Capping the paired interval initially capped `health_n` with it, because `region_month` read both off the same intervals: a notice in force 1 May – 5 July, *proven* by its own lift, showed the drinking-water marker on May and then nothing for June and July. That is the wrong trade — the health notice was unbundled from the grade in the first place because "its importance is not measured in person-hours", and a cap is a person-hours instrument. So the two are now separate: `paired_end` says when the notice stood until (uncapped — the lift is evidence), `charged_end` says how much of that it may charge, and `Case.in_force` carries the former into `Region.knock_iv` for the marker. The unpaired path is deliberately **not** given the same treatment: there the cap is a staleness hedge on a `status` field known to go stale, not an accrual ceiling, and lifting it would put a marker on every month for Whiddy Island's 1,460 open days on the strength of that field alone.

**And the marker knows "now" from "this month".** `health_n` counts notices active at any point in the month, which the front end was reading as a present-tense claim: a notice lifted on the 3rd went on saying "the water may not be safe to drink" on the 25th. `region_month` now also publishes `health_now`, the count standing at build time, and the copy makes the safety claim only where that is non-zero — elsewhere the mark is a record ("active in August 2026"). On the 2026-08-18 build the two differ already: Galway 2/2, Mayo 1/1 and Tipperary 1/1 are standing, Monaghan 1/0 is not. The test is inclusive of the interval end, because an ongoing notice accrues to exactly `now` and a half-open comparison calls every live one lifted.

**Cost today: nothing.** One notice pairs on this snapshot and it spans 0.00 days; the full built payload is byte-identical before and after, compared at a fixed `now`. This is a guard against a future lift, which is the only time it can ever fire.

**A lift only ends a notice that was still running.** The same review found the pairing sitting *ahead* of the `ended_by_publication` check it shares a branch with, so a notice whose own text reported an end before it was even published — a `lifted_immediate`, or an extracted end that `build.py` nulled for preceding publication — would take a later lift as its end and accrue the gap. That is precisely the fabrication `ended_by_publication` exists to refuse, so the flag is now read once and gates the pairing and the accrual alike. Also nothing today (all 35 boil and all 7 do-not-consume notices are `end_source = not_found`, so neither can trip it) and also byte-identical on the built payload; also a guard for later.

`boil_notice_fate` deliberately does **not** take this guard. It can only fire on a case carrying an extracted end, and that class structurally never has one — the end is a different case. Adding it would mean a fourth outcome and a rewritten fixture to defend against zero cases; the comment in the function says so, and says to add it if a prompt version ever starts extracting ends there.

Worth noting for anyone reading those tests: two of the do-not-consume fixtures described a state `build.py` cannot produce — `notice_to_end_seconds` NULL while `end_source` stayed `completion_update` with an `end_local_date` *after* publication, which would have yielded a span rather than a NULL. They now carry `not_found`, as all 7 real cases do, and the staleness test gained the assertion it was missing: that the notice is still accruing on day 9.

**Known limitation of strict kind-matching.** The feed sometimes files a do-not-consume lift under the wrong category: case 231989 is `boil_notice_lifted`, titled "Lifting of The Boil Water Notice - Cork", and its body says it lifts a *Do Not Consume Notice* on the Knockeragh supply. Strict matching will not pair that with its issue. It costs nothing today (that issue is closed and pre-collection), and loosening the rule would let any boil lift close a do-not-consume for the same scheme, which is the worse error.

## The county drill-down: county → towns (added 2026-07-25)

Clicking a county opens a per-county view (hash route `#county/<name>`, same single page) which carries the tabular detail that used to expand inline, plus a breakdown of the county into the named places its cases fall in. Selecting one of those areas opens its incident history (`#area/<county>/<code>`) — every notice ever published there, newest first. Both URL segments are percent-encoded, which is what keeps the 31 slash-bearing area codes from breaking the route.

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

That is a constant-factor saving, not a bound: each new month adds roughly **85 KB**, so the file passes 1 MB in about four months. The fix when it matters is to emit one `county/<name>.js` per county and load it with an injected `<script>` tag on navigation — off-disk use survives, the index drops to about 150 KB, and growth stops being the index's problem. Deliberately not done yet; revisit at 1 MB. Note that `h/<county>.js` is already taken by the incident histories below, so that split wants its own directory.

**Per-area incident histories are sharded, not shipped.** The history — every notice ever published in an area, event by event — is 7,525 records, **1.5 MB raw / 183 KB gzipped**, more than twice `data.js`. It is written to `h/<county>.js`, one file per county, and the page injects a `<script>` for one county when a reader opens an area in it. Median county 40 KB raw / ~5 KB gzipped; Dublin worst at 203 KB / 23 KB. Growth is ~444 KB raw per month across all 26, so Dublin passes 500 KB raw in about five months and is the first that would want splitting by year.

Per county rather than per area, on two counts. Area codes are not filenames: 31 contain a slash (`ed:Cavan:Dunmakeever/Benbrack/Derrynananta`), 2,808 contain a colon, 312 a space, 15 an apostrophe and 4 are non-ASCII — per-area files would need a slug scheme and a collision map, the same string-munging this page refuses when it declines to key the drill-down on `location`. And one county file serves every area a reader opens in a sitting, against 1,614 files churning through the Pages artifact twice a day.

**An event is listed under every area its pins were homed to**, not only the one it is named after. The two are different questions and the county breakdown already takes this position: it homes each *pin*, so a burst published as pins in Naas and in Sallins puts counts and person-hours on both rows. Naming the *event* once and listing it only there left **220 of the county tables' 1,830 areas with no history at all**, and their pages said no notice had ever been published directly under a row that had just counted one. 764 events are multi-area; listing each under all of them costs 6 KB gzipped across every shard and is what makes the two pages agree. The record carries `areas` when it appears in more than one, because a reader who meets the same burst twice would otherwise reasonably conclude the site is double-counting. The naming decision is untouched — `area_of` still gives an event exactly one label for the open list and the top ten.

What a record carries: reference, title, worst severity across the event's pins, earliest publication, pin count, covered hours, people affected, how the end was signalled, open/closed state, and the raw `location` string as a display line. Not the notice text — 5.5 MB raw, 402 KB gzipped, four times the whole history. Not `work_category` — the title already states it, and it would only buy a filter. Two records deliberately say less than they could: an event **closed without ever reporting an end** publishes no duration at all, because its token one-second footprint would print "0.0h" for 801 events, and a **recurring** event publishes covered hours with the window series' span beside it rather than the span alone.

**The area directory is a separate page.** `areas.html` lists all 1,836 areas that have had a notice, grouped by county, each linking to its history — ~292 KB raw / 32 KB gzipped. Standalone rather than a fourth view in the single page, so the first paint does not grow to carry a list most readers will never open; `index.html` gains only the two links pointing at it. It also means Ctrl+F searches the whole list, which is worth more than any filter box at this size, and per-area notice counts are free because nothing is shipped up front. Deliberately **not paginated**: 1,836 rows render instantly, and paging them would break the search that makes a list this long usable. Areas with no notice at all — roughly 1,900 of the country's named areas — are left out; a page of them would say nothing.

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

[water-sla-benchmarks.md](water-sla-benchmarks.md) explains why Ofwat/CRU numbers (~99.99%+ availability equivalents) cannot be borrowed: they count measured minutes without water at the tap for ≥3-hour interruptions, whereas this index counts whole published-notice durations across an assumed 500 m population, including "may be affected" notices. The intent is to keep these thresholds fixed so months stay comparable, and revisit after a full year of seasons.

## Radius sensitivity (checked 2026-07-16)

Rebuilding May and June 2026 at 300 m / 500 m / 1 km affect-radii: county **rankings** by availability are robust (Spearman rank correlation vs the 500 m baseline: 0.93/0.91 at 300 m, 0.90/0.86 at 1 km), but absolute **grades** are not — 48 of 52 county-months change letter somewhere across the range, because affected population scales roughly with radius², shifting everyone against the fixed thresholds together. Read the letters as calibrated to the 500 m assumption; read the ordering of counties as real. (A percentile-based grading would be radius-invariant, at the cost of losing fixed meaning across months.)

## The national top ten (added 2026-08-01)

`#top` ranks the ten largest **individual** disruptions nationally in a month, by person-hours. Nothing else on the site does: person-hours are computed per county and per area, so a reader who wants to know what actually happened in July gets 26 county rows rather than the burst that caused them. The distribution justifies the page — in July 2026 the ten largest events were **21.9%** of every person-hour lost nationally, and one Donegal reservoir interruption was 9% on its own.

Three decisions worth recording:

**Person-hours are clipped to the month**, using the same bounds `region_month` uses, rather than attributing a whole event to the month it started in. That keeps the ranking summable against the county figures already published — the "these ten are a fifth of July" headline is only true under clipping — at the cost that `person_h` is not exactly the two displayed figures multiplied (`hours` is rounded to 1dp for the payload; `person_h` comes from the unrounded span, because matching the county totals matters more).

**Complete months only.** The in-progress month reshuffles between builds as open events accrue toward the 14-day cap and then resolve, so a "largest disruptions of this month" list would contradict itself twice a day. The front end shares `curMonth` with the other views but falls back to the newest complete month, since `curMonth` defaults to the in-progress one.

**The end badge counts notices, not events.** `Region.observed_end` is OR'd across an event's pins, which is what the monthly median wants (does this event carry *an* end signal?) but is wrong for a per-event verdict: July's largest event, `DON00115765`, has 18 pins of which exactly **one** reported a completion and 17 only stated a schedule. Badging that "completion confirmed" would present a plan as a measurement, which is the failure this whole site is organised against. The payload therefore carries `pins` / `confirmed` / `scheduled` and the page says "partly confirmed — 1 of 18 notices reported complete".

### A scheduled repeating window is a restriction, not an outage (added 2026-08-02)

The severity classes are keyed to the notice's title, and **Uisce uses two titles for one situation**. The same Donegal supply zone — Lifford, Rossgier — under the same nightly 10pm–7am regime was published as:

| date | reference | title | class | accrued |
|---|---|---|---|---|
| 30 Apr | `DON00111054` | Water **Conservation** | degraded | nothing |
| 23 Jun | `DON00114559` | Reservoir **Interruption** | outage | everything |
| 9 Jul | `DON00115765` | Reservoir **Interruption** | outage | 949,824 person-hours |

Overlapping villages, identical window, near-identical wording, opposite treatment — and the July one was the largest single figure on the site. Whichever way that pair is resolved, it has to be resolved alike.

`classify` now takes `recurring` and downgrades an outage to `degraded` when the *event* announced a window repeating over a date range. It downgrades an outage and nothing else: a nightly leak-detection round is still maintenance. Recurrence is read at event level, not per notice, because the pin carrying the completion update reports no window and would otherwise sit as a lone outage inside a restriction event, whose interval the per-reference union then charges in full.

The reasoning: a scheduled, repeating, announced overnight window is demand management rather than a failure, and that is true whichever title carries it. The conservative side is also the one already published — restrictions have never counted here.

Measured on the 2026-08-02 corpus: **July national person-hours −3.8%** (25,395,359 → 24,440,623), Donegal −45% and out of the per-capita table's top five (rank 1 at 12,682 h/1k → rank 6 at 6,997). Only two July events move class. **No county's grade changes**, so the A–F thresholds did not need recalibrating.

Note what this does *not* touch. May's largest event, a 23.8h reservoir interruption across Drogheda, is one continuous interruption with no repeating window and stays an outage at 551,427 person-hours — which is the discrimination the rule exists to make.

⚠️ **This makes the recurring-window expansion numerically inert.** Person-seconds accrue for `outage` only, so an event that is now `degraded` contributes nothing however its intervals are shaped. The expansion still earns its place — the day bars and event counts read from those intervals, and the `end_recurrence` field it introduced is exactly what this rule keys on — but nothing multiplies by a window's length any more. If the policy ever flips to counting restrictions, the arithmetic is already there and correct.

### Recurring windows cover hours, not days (added 2026-08-01)

A notice reading *"daily from 10pm until 7am, from 9 July to 27 July"* is 18 nights of nine hours, not 16 days of continuous outage. Prompt v3 extracts the window itself (`recurrence`, `window_open`, `window_close`, `window_first_date`) and `resolve_case` expands it into one interval per night, so a `Case` now carries a *list* of intervals. Everything downstream already unioned and clipped lists, so only `Region.add` changed.

Three consequences worth stating:

**`median_completion_h` is covered hours.** For a single-block event that is also its elapsed span, so nothing moved for the other 99%. For a recurring event the two now differ sharply — a night's works inside a fortnight's presence — and the covered figure is the one published, because "how long did the works take" is the question the metric name asks. The site copy says so.

**Expansion is decided per notice; coverage is unioned per event.** One pin falling back to the continuous interval re-covers every gap the others carved out, so the fix can land on 17 of 18 pins and barely move the number. This is not hypothetical — it is what happened to `DON00115765` on the first v3 run, because the model reports no window on a notice whose text says the works are complete.

So a window is treated as a property of the **works**, not of the notice: `event_windows` lends the window any pin of a `reference_num` reported to the pins that reported none. The borrowed series is still clipped to the borrowing pin's own start and end, which is what makes this a reading rather than a guess — the completion pin takes the schedule and then stops at the moment it says the works stopped. Inherited windows face the same cross-check as claimed ones and are listed individually on every build, being the least-evidenced expansions here. Where pins disagree the commonest window wins, ties broken deterministically. Every build also prints any event whose pins still disagree, which is the line that catches a fix landing on 17 pins and being undone by the 18th.

**The guard refuses by default.** A refusal is a numeric no-op, so the checks are deliberately suspicious: the recurrence value must be exactly `daily`, all three window fields must parse, open must differ from close, the series must produce at least two windows, and for a *scheduled* end the window's closing time must match the reported end time — the prompt requires them to be the same, so a disagreement is the model contradicting itself. Completion updates have no such cross-check available (their `local_time` is the completion, not a window close), so they are honoured and listed individually in the build report.

The ranking is by raw person-hours, not per-capita, and it ranks events rather than counties deliberately. A county ranking adds nothing: by raw person-hours it is a population ranking, and per-capita it is arithmetically identical to the availability column already on the overview (Donegal's 22,156 person-hours per 1,000 residents in July *is* its 97.022%).

## An event with no usable end is charged a typical span, not a zero (settled 2026-08-15)

The events with no usable `notice_to_end_seconds` were being kept out of the published median **and** given a token 1-second footprint in the availability arithmetic. The first is right; the second was not, and this splits them.

**The population is not what its name suggests.** Of 4,473 outage-class events on the 2026-08-15 corpus, 204 took the token footprint. Only **4** of those are genuinely `not_found`. **200** are the negative-span family — the end is known, the *publication timestamp* is not, because the feed re-stamps `STARTDATE` in place (measured 2026-07-20, [data-quality.md](data-quality.md)). A further 29 are open with no signal at all and take the accrue-to-now branch instead. So this is overwhelmingly "closed, with a known end, and a broken start", not "never closed".

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
- Overlapping events in the same area double-count person-hours — **measured 2026-08-18 at 2.0% of national outage person-hours** (1.58M of 80.3M person-hours over Apr–Aug 2026, August partial and still accruing, ranging 0.5–2.5% by month), by re-unioning intervals per Small Area across events, which cannot double-count by construction. Re-measure any time with `uv run uisce-eval-overlap` (`src/uisce/eval_overlap.py`); it prints the published-vs-exact split per month and changes nothing. Left uncorrected deliberately: the double-count is pessimistic (overstates disruption), a correction would touch the availability arithmetic itself, and it is smaller than the modelling error already conceded by the 500 m radius assumption.

  **The first run of this said 3.6%, and it was wrong in two ways** (both found in review the same day, both now pinned by tests in `tests/test_eval_overlap.py`). It de-overlapped per *pin* while the published side accrues per *event*, so an event's own pins — staggered in time and place, as July's 18-pin, 385h event is — read as double-counting: a two-pin event with no overlap at all reported 50%. And it resolved cases without the `SpanTable`, so every case with no usable end signal took a 1-second token footprint instead of the imputed span the site charges it, dropping the published total to 77.2M against the site's own 79.8M. Correcting both moves the figure from 3.6% to 2.0% and the monthly range from 3.0–5.1% to 0.5–2.5%. The lesson for the next probe of this kind: reproducing a published number means reproducing the *whole* resolution path, and a diagnostic that cannot reproduce the total it is a fraction of is measuring something else.
- The 14-day cap applies to each *notice*, not each event, so an event published as several staggered notices can span longer than 14 days — July's largest ran 385h (16 days) across 18 pins published over three days. The page copy says so.
- The scheduled-end events that accrue disruption time are accruing an *announced* interval, not an observed one. They are kept out of the headline median but not out of the availability percentage, so availability carries an assumption the median does not. As of 2026-08-15 the same is true one tier further down, for the events charged an imputed span.
- `start_date` is the notice publication time, so durations are a floor on true outage length (overnight events are typically posted the next working morning — see [data-quality.md](data-quality.md)).
- "May be affected" notices count everyone in the radius; the index measures disruption exposure, not confirmed loss of supply.
- County populations are hardcoded Census 2022 figures in site.py.
- The current month grades harshly while in progress, for three separate reasons: open cases accrue to "now" against a part-elapsed denominator; some feed `status` values are known to be stale; and cases downloaded since the last `uisce-infer` run have no end signal at all, which sends them down the same accrue-to-now branch — 98% of the never-inferred backlog is `status = 'Open'`, so this is concentrated exactly where it does most damage. See [pipeline-dependencies.md](pipeline-dependencies.md).
- "Open cases" on the page is a right-now snapshot of `Case.is_open` (`status = 'Open'`, still served by the feed, and not past a completion the notice's own text reported - see "The notice's own completion closes it" below), attached to the county rather than the selected month, so it does not vary as you page through months (the copy says so). Of 508 open cases on the 2026-07-20 snapshot: 127 are future-dated advance notices of planned works, 20 carry a description that already says "works are now complete" (genuinely stale feed status; these no longer list), 72 more have a passed scheduled end (these still do), and 13 are long-lived boil / do-not-consume notices that are correctly still open.

## The notice's own completion closes it (settled 2026-09-05)

A reader flagged CAR00119809 (Carlow, Burst Water Main): its own 2:36pm update said "Works are now complete ... supply should start returning", and two days later the county page still listed it under "Open now". `Case.is_open` read `row["status"] == "Open"` and nothing else. The extracted completion (`OBSERVED_END_SOURCES`) is what the accrual already stops charging at, so the case's *hours* were closed off at 2:36pm while its badge said open: the arithmetic trusted the notice and the display trusted the feed, on the same case.

The first session to look at this prototyped the fix and set it aside for the owner, on the argument that hiding a genuinely open case on a bad extraction costs more than a stale badge. It did not measure either side of that trade. Measured the same day on the 2026-09-05 release:

| | n |
|---|---|
| cases the feed had `Open` (not vanished) | 562 |
| ... past a completion their own text reported | **216** (143 outage-class, 65 maintenance, 8 restriction) |
| ... past a *scheduled* end, no completion | 133 |
| ... with a scheduled end still ahead | 154 |
| ... with no end signal at all | 55 (41 of them boil / do-not-consume notices, which never carry one) |
| events those 216 cases make, once pins are grouped | 177 of the 437 the site listed as open |

The stale badge is not "a build cycle or two". Across the 3,783 closed cases carrying both a completion update and a `closed_at`, the feed closed the case a **median 72h after the stated completion** (p10 33h, p90 111h, 11 cases over a week). The 216 had been sitting past their completion a median 50h. So a reader checking whether their road is affected was, on this day, shown 177 disruptions as ongoing that had been over for two days, and had to read each notice's text to find out.

The false-negative side is small enough to measure at zero. A completion read wrongly would come from a template misread (the rules emit `completion_update` only under a parsed update header carrying the phrase; 0 wrong emissions on the labelled rounds, [rules-vs-llm-end-times.md](rules-vs-llm-end-times.md)) or from a follow-up problem after the completion. Of the 7,667 cases on file with a completion update, **exactly one** carries an update block newer than the completion, and it is the same 3:47pm update pasted twice (DLR00118752). Uisce publishes a follow-up problem as a new case with a new reference, which the feed then serves as Open with no completion, so it lists on its own.

**Decision.** A case is open only while nothing the notice itself has said has ended it: `is_open(row, now)` is `status = 'Open'`, not `vanished_at`, and not past an *observed* end (`OBSERVED_END_SOURCES`, plus `lifted_immediate`). The decision is made once, in `resolve_case`, and carried on `Case.is_open`, so the open list, `open_total`, the national open view, the county page's "Open now" section and its notice text, the history's "still open" / "at least Nh so far" and the Atom feed's "still open" all read the same answer and cannot drift apart again. On the 2026-09-05 release this takes the national open count from 437 to 260; every published figure - availability, person-hours, grades, medians, coverage, the top ten, the area breakdowns - is byte-identical under both readings with the clock pinned, which is the point: the arithmetic already believed the notice.

**What does not close a case here.** A passed scheduled end (133 on the day). A schedule is a plan the works may have overrun, the same line the published median draws ("The published time metric" above), and the feed saying Open past one is the only evidence either way. A completion reported for an instant still ahead of the build leaves the case open until then. And `closed_at` is untouched: it records the build that observed the feed close the case, so the "observed to close" list and the history's "closed <date>" keep meaning that, and a case closed by its own text reads as closed with no close date until the feed catches up.

**The general rule this settles**, because the deferral was the failure here rather than the five-line patch: when the site trusts a signal for the arithmetic, it trusts it for the display. A surface that reads the feed's `status` alone where the site's own extraction contradicts it is a bug, not a trade-off, and a trade-off left for the owner has to carry both sides' numbers. The measurements above took a few minutes against the release DB; the deferral left 177 finished disruptions listed as ongoing on the live site.

**Reopen this if** the follow-up-after-completion count stops being zero (re-run the segment check in this section's commit against the current release), or if a labelled sample shows scheduled ends are met reliably enough to close a case for display too.

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

**Resolution:** scheduled ends still **accrue** disruption time and person-hours — a published plan is the best interval available and dropping it would under-count exposure — but they are excluded from the published median and reported separately as "+N scheduled-only". `OBSERVED_END_SOURCES` in `config.py` is the single switch. At event level the split holds every month (observed 7.1/12.6/15.8/10.2h against scheduled 4.8/5.3/4.4/4.3h for Apr–Jul 2026).

See the eval in [end-time-eval.md](end-time-eval.md) for how the LLM-extracted end times behind this are validated.

## Possible next steps

Population served per named supply scheme from the EPA public water supplies register (boil notices name their scheme in `location`); per-county script files once `data.js` reaches 1 MB (see the payload note above); deriving `COUNTY_POP` from the Small Areas, since it is now the only hardcoded population left in the project and every other figure is exact-from-data — it shifts published county availability, so it wants its own change; folding `sa_pop.csv` and `sa_towns.csv` into one file and one command, both being derived from the same ArcGIS layer; an Electoral-Division split for the cities, trading a name-merging heuristic for vernacular area names and retiring the hyphenated LEA compounds (costed in the drill-down section above); a prompt tweak for the nightly-works pattern where the model currently extracts date-only ends (see [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) — qwen got `scheduled_end_with_time` right on those 8 cases); GitHub Pages publishing from the weekly Build DB workflow.
