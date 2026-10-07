# Status site methodology

**Simply put:** the site counts notices, not people. A county's letter for a month is how many outage notices were published per 100 km of its water main. The time beside it runs from a notice going up to its own "works complete" update. A notice is listed under the town nearest its map pin. Everything else in this note is why those three choices were made, and what lost to them.

How `uisce-site` (src/uisce/site.py) turns `out/uisce.db` into the statuspage-style site in `out/site/`, and why each modelling decision was made. Companion notes: [data-quality.md](data-quality.md) for what the underlying fields can and cannot support, [water-sla-benchmarks.md](water-sla-benchmarks.md) for how the figures relate to regulators' measures, and [population-data-sources.md](population-data-sources.md) for the Census geography. The population-weighted availability method the site used until 2026-10-06 is in [archive/availability-method.md](archive/availability-method.md).

## Severity classes

**Simply put:** each notice is sorted into one of four kinds: outage, restriction ("degraded"), quality, or works. The title decides, except that the feed's own restriction and low-pressure flags can make a notice a restriction. Only outages are counted; the rest are shown.

Each case maps to one class from `work_category` plus the impact flags, tested in that order:

1. `boil_notice_lifted` → ignored as an event (it is the good-news end of an earlier notice; used only for pairing, below)
2. category boil_notice_issued / consumption_notice_issued / discolouration → **quality**. The feed's `do_not_drink` / `boil_water_notice` flags were read here until 2026-08-18 and are not: both are redundant with the category, and `do_not_drink` is wrong on 9 of 19 cases — see [data-quality.md](data-quality.md)
3. water_conservation / low_pressure categories, or `water_restrictions` / `reduced_pressure` flags → **degraded**
4. burst_main, reservoir_interruption, water_treatment_plant_interruption, pump_station_interruption, pump_failure, power_outage → **outage**, regardless of `work_type` (the title itself announces lost supply)
5. mains_repair / valve_repair / pump_repair / NULL category, when not marked Planned → **outage** (emergency repairs normally shut off supply)
6. everything else — investigations, leak detection, hydrant works, installations, and anything Planned → **works**

Only the **outage** class is counted in the letter and the median. This is deliberate: an F should mean supply was lost, not that a county ran many investigations. No feed flag can do this job: `water_outage` is set on 97% of all cases, and the two health flags carry nothing the category does not (2026-08-18).

Interval inputs come from `inferred_cases.notice_to_end_seconds`, capped at 14 days. The genuinely long events (40–87-day conservation restrictions) are classed degraded and never count, so the cap is a backstop, not the outlier strategy - see the outliers section of [data-quality.md](data-quality.md).

## Events, intervals, and edge cases

**Simply put:** notices published under one reference are one event. Each notice gets a start (when it was published) and an end (what its own text reports, or its paired lift, or 14 days at most); those spans colour the day bars and feed the median.

- Cases are grouped into events by `reference_num` (a 13-pin multi-pin publication counts once); each event's pin intervals are unioned before any accounting.
- Open cases with no inferred end (e.g. an active boil notice: `boil_notice_issued` cases never have inferred durations) accrue from publication until "now", capped at 14 days. Exception: a case whose own text says it already ended (an extracted end that precedes publication, nulled in `build.py`, or a `lifted_immediate`) does not accrue to now, whatever the feed's `status` claims (`ended_by_publication` in `site.py`; see [data-quality.md](data-quality.md) for the 532-case family behind this). It keeps the one-second token of the next bullet. `lifted_immediate` lift *records* are excluded by their category (`IGNORE_CATS`); a notice whose own description was overwritten with lift wording, the 221165 shape, keeps its event.
- Closed cases with no usable end signal keep a one-second token on their publication: the start day colours and the event counts, but no length is read from it. Between 2026-08-15 and 2026-10-06 they were charged a typical span for their kind of works instead ([archive/availability-method.md](archive/availability-method.md)); with no total left to charge, the token is back.
- Nothing counts beyond "now" (a scheduled end in the future has not happened yet) or before **2026-04-20**, when data collection began; earlier days render as "no data", and a month is lettered only once the site has seen it whole, so April 2026 carries a count and no letter.
- Boil-water **and do-not-consume** notices are lifted by separate cases with fresh reference_nums, so issue → lift is paired by county + lift category + normalised scheme name from `location` ("Ardfinnan Regional Public Water Supply" → "ardfinnan"), with up to 2 days of publication-order slack. The two kinds never cross-pair: a boil notice is ended only by a `boil_notice_lifted`, a do-not-consume only by a `consumption_notice_lifted`. On the July 2026 snapshot only one notice pairs — every other lift on file refers to a notice issued before collection began — but coverage grows with history. A paired end is then capped at `CAP_DAYS` like every other end signal (`paired_end` in `site.py`) — see "A paired lift is capped like any other end" below. See "Do-not-consume notices got the pairing, not the exclusion" for why only half the boil-notice policy carried over.

## Do-not-consume notices got the pairing, not the exclusion (2026-08-18)

**Simply put:** a do-not-consume notice can be closed by its lift notice, like a boil notice. Unlike a boil notice it is not dropped when it stands unlifted past 14 days: it closes, but it still counts and raises the drinking-water mark for its first 14 days.

A methodology review found a fairness gap: `consumption_notice_issued` and `boil_notice_issued` are published identically — the issue never states its own end (all 7 on file are `not_found`), the lift arrives as a separate case, and the feed's `status` goes stale — yet only boil notices routed through `boil_notice_fate`. The review proposed giving both classes the whole policy. **Half of it was taken.**

**Taken: lift pairing.** A do-not-consume notice can now be closed by a `consumption_notice_lifted` for the same scheme. This is strictly more information than running to the 14-day cap, and it uses real evidence — a published lift. The pairing index is now keyed by `(county, lift category)` so the two kinds cannot cross-pair; `LIFT_OF` names the pairs, and `IGNORE_CATS` derives from it. Zero notices pair on the 2026-08-18 snapshot (both consumption lifts on file refer to notices issued before collection began), which is exactly where boil pairing started.

**Not taken: the staleness exclusion.** Boil notices unpaired and `Open` past `CAP_DAYS` are dropped rather than accrued. That rule rests on evidence: case 221165 sat `Open` while **its own description said** the notice "is now lifted with immediate effect" — the text contradicted the status, so the status was declared untrustworthy. **No do-not-consume notice on file does that.** Whiddy Island (`Open` since 2022-08-18) and Dursey Island (since 2024-08-07) both read as genuine, unlifted notices naming a specific water-quality failure — turbidity and colour on one, elevated manganese on the other — issued after HSE consultation, with explicit instructions that boiling will not make the water safe.

The argument for extending the exclusion was structural identity: the two classes are published alike, so they should be treated alike. That is sound as far as it goes, but it carries the *policy* across without the *evidence* that justified it. The asymmetry in what being wrong costs settles it: dropping a stale boil notice that was in fact lifted loses nothing, while dropping a do-not-consume notice that is still in force removes a live drinking-water warning from the site. The 14-day cap was also calibrated on boil notices, which end when remedial works finish; a manganese problem does not resolve on that schedule.

Practically the exclusion would have changed two cases today — Knockeragh (Cork, 32 days) and Drum (Monaghan, 25 days). Whiddy and Dursey are already invisible: their capped intervals predate the 2026-04-20 collection window.

**Reopen this if** a do-not-consume notice appears whose own text says it was lifted while `status` stays `Open`. That is the 221165 shape, and it is the evidence this decision is waiting on.

**Amended 2026-09-24 (owner decision): an unlifted notice closes at the cap.** The review behind the retroactive code audit found the two halves of this policy disagreeing on one screen. The health marker stands over the capped interval, so a do-not-consume notice stopped raising it on day 14, while `Case.is_open` still read `status` and kept it under "Open now" indefinitely: on the 2026-09-23 release Whiddy Island, Dursey Island and Knockeragh (Cork) and Laragh (Wicklow, 2 pins) were all listed open with `health_now` 0, so the page listed a warning it never made. The owner's intent is that a notice not closed explicitly closes itself after 14 days, marker and open status together. `resolve_case` now closes an unpaired standing notice once `now` is past `start + CAP_DAYS`. It is still not *excluded*: it counts as an event and raises the marker for its first 14 days, which is the half of the decision above that stands. A paired lift now closes the notice for display too; before, only the arithmetic read it, and Downings (Donegal, 232476) sat in "Open now" for 144 days after its lift. That lift is stamped a day before the issue, and `paired_end` clamping it to `start` gave a zero-length interval that dropped the notice from May's quality count and `health_n`; it now keeps the token second an unpaired closed notice keeps. On the release: 5 notices leave the open lists, Donegal May gains its quality event and its `health_n`, and no other figure moves.

Three edges a code review of this change raised, measured and left (2026-09-24). *A lift before its issue.* `paired_lift` keeps its 2 days of slack, so a notice reissued the day after the previous one on the same scheme was lifted would pair to the earlier lift and close on arrival. On the release the only paired notice is Downings, and its lift is the one stamped before its issue; under either reading it is not open today (paired, it is lifted; unpaired, it is a boil notice past the cap and excluded), so the slack stays. Re-measure when a second notice pairs. *The history after the cap.* A standing notice closed at the cap has no end signal, so its history record drops its hours and reads "no end reported", which is true: nothing ever reported one. *A re-stamped start.* The cap is measured from `start_date`, so a feed re-stamp reopens a closed standing notice for another 14 days; its marker restarts with it, so the two still agree.

## A paired lift is capped like any other end (2026-08-18)

**Simply put:** finding the notice that lifts a boil-water notice must never make it count for longer. The lift says when the notice really ended, so the drinking-water mark runs to the lift; what the notice counts for is still capped at 14 days like every other notice.

The pairing above originally returned `max(lift, start)` with no upper clamp, on the reasoning that a published lift is a real observed end and not a schedule. That is true and it is not the question. **The 14-day cap is a ceiling on what one notice may charge, not a statement about how long it ran** - an observed `completion_update` is capped and the open-and-accruing branch is capped. A paired lift is not stronger evidence than a completion update, so it does not get an exemption the completion update does not have.

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

**The cap bounds the arithmetic, not the marker.** Capping the paired interval initially capped `health_n` with it, because `region_month` read both off the same intervals: a notice in force 1 May – 5 July, *proven* by its own lift, showed the drinking-water marker on May and then nothing for June and July. That is the wrong trade - the health notice was unbundled from the grade in the first place because its importance is not measured in hours, and a cap is an instrument for hours. So the two are now separate: `paired_end` says when the notice stood until (uncapped - the lift is evidence), `charged_end` says how much of that it may charge, and `Case.in_force` carries the former into `Region.knock_iv` for the marker. The unpaired path is deliberately **not** given the same treatment: there the cap is a staleness hedge on a `status` field known to go stale, not an accrual ceiling, and lifting it would put a marker on every month for Whiddy Island's 1,460 open days on the strength of that field alone.

**And the marker knows "now" from "this month".** `health_n` counts notices active at any point in the month, which the front end was reading as a present-tense claim: a notice lifted on the 3rd went on saying "the water may not be safe to drink" on the 25th. `region_month` now also publishes `health_now`, the count standing at build time, and the copy makes the safety claim only where that is non-zero — elsewhere the mark is a record ("active in August 2026"). On the 2026-08-18 build the two differ already: Galway 2/2, Mayo 1/1 and Tipperary 1/1 are standing, Monaghan 1/0 is not. The test is inclusive of the interval end, because an ongoing notice accrues to exactly `now` and a half-open comparison calls every live one lifted.

**Cost today: nothing.** One notice pairs on this snapshot and it spans 0.00 days; the full built payload is byte-identical before and after, compared at a fixed `now`. This is a guard against a future lift, which is the only time it can ever fire.

**A lift only ends a notice that was still running.** The same review found the pairing sitting *ahead* of the `ended_by_publication` check it shares a branch with, so a notice whose own text reported an end before it was even published — a `lifted_immediate`, or an extracted end that `build.py` nulled for preceding publication — would take a later lift as its end and accrue the gap. That is precisely the fabrication `ended_by_publication` exists to refuse, so the flag is now read once and gates the pairing and the accrual alike. Also nothing today (all 35 boil and all 7 do-not-consume notices are `end_source = not_found`, so neither can trip it) and also byte-identical on the built payload; also a guard for later.

`boil_notice_fate` deliberately does **not** take this guard. It can only fire on a case carrying an extracted end, and that class structurally never has one — the end is a different case. Adding it would mean a fourth outcome and a rewritten fixture to defend against zero cases; the comment in the function says so, and says to add it if a prompt version ever starts extracting ends there.

Worth noting for anyone reading those tests: two of the do-not-consume fixtures described a state `build.py` cannot produce — `notice_to_end_seconds` NULL while `end_source` stayed `completion_update` with an `end_local_date` *after* publication, which would have yielded a span rather than a NULL. They now carry `not_found`, as all 7 real cases do, and the staleness test gained the assertion it was missing: that the notice is still accruing on day 9.

**Known limitation of strict kind-matching.** The feed sometimes files a do-not-consume lift under the wrong category: case 231989 is `boil_notice_lifted`, titled "Lifting of The Boil Water Notice - Cork", and its body says it lifts a *Do Not Consume Notice* on the Knockeragh supply. Strict matching will not pair that with its issue. It costs nothing today (that issue is closed and pre-collection), and loosening the rule would let any boil lift close a do-not-consume for the same scheme, which is the worse error.

## The county drill-down: county → towns (added 2026-07-25)

**Simply put:** clicking a county lists the towns and countryside its notices fall in, named from the Census: a town, a city electoral area, or "Around" a rural electoral division. The notice's own location text is too messy to group by.

Clicking a county opens a per-county view (hash route `#county/<name>`, same single page) which carries the tabular detail that used to expand inline, plus a breakdown of the county into the named places its cases fall in. Selecting one of those areas opens its incident history (`#area/<county>/<code>`) — every notice ever published there, newest first. Both URL segments are percent-encoded, which is what keeps the 31 slash-bearing area codes from breaking the route.

**The geography is Census settlements, not the feed's own text.** `cases.location` looks tempting — for Kildare it reads `Leixlip`, `Prosperous`, `Celbridge`, `Newbridge`, `Naas` — but it has 3,866 distinct values nationally and fragments badly: `Newbridge` / `Newbridge,` / `Mount Carmel, Newbridge` are three keys for one town, estate and street names appear as if they were places (`Marlton Park`, `Ashgrove Crescent`, `Wolstan Haven Road`), and it carries no population, so nothing can be weighted by it. The geocode cache is worse: 94% of rows have only `city_district`, which is mostly Electoral Divisions (`Naas Urban ED`) and bridges (`Bond Bridge`).

Instead each pin is placed in the named area of the nearest Census Small Area centroid within 8 km (`PLACE_KM`), via `data/sa_towns.csv` - see [population-data-sources.md](population-data-sources.md) for that join, and "The estimate is removed" below for the rule's measured alternatives. Names come out canonical (`Kildare`, not `Kildare Town`; `Coill Dubh (Blackwood)`), the fragmented location strings consolidate onto one row, and every town arrives with a Census population.

Three decisions worth recording:

- **One home per pin.** A pin takes one area, so per-area notice counts sum to the county's.
- **Only areas in the case's own county are considered.** Border pins are real - a Kildare-labelled notice whose nearest Small Area is in Blessington, Co. Wicklow - and re-homing one across a county line would contradict the page it appears on, so the pin is set aside as unplaced rather than moved (the known limitation below).
- **No letter grades at area level.** A letter needs a length of main, which Uisce Éireann publishes by supply zone, not by town; the area rows carry counts.

**About 40% of cases fall outside any settlement** — not a defect of the geography, since most of the network (reservoirs, treatment plants, trunk mains) runs between towns rather than through one. Those are named by their Electoral Division; see the countryside section below.

**No day bars at area level.** Deliberate: the day arrays are the bulk of the payload, and 1,767 area breakdowns × months of 31 cells would multiply the county shards several times over for a chart nobody would read at that granularity. Counts only.

**Payload.** The county's own data (`towns`, `resolved`) ships per county in `t/<county>.js`; `data.js` keeps every month, the open lists and the top tens, and the first overview's month is inlined in `index.html`; see [frontend-notes.md](frontend-notes.md), "The county's own data left data.js".

**Per-area incident histories are sharded, not shipped.** The history — every notice ever published in an area, event by event — is 7,525 records, **1.5 MB raw / 183 KB gzipped**, more than twice `data.js`. It is written to `h/<county>.js`, one file per county, and the page injects a `<script>` for one county when a reader opens an area in it. Median county 40 KB raw / ~5 KB gzipped; Dublin worst at 203 KB / 23 KB. Growth is ~444 KB raw per month across all 26, so Dublin passes 500 KB raw in about five months and is the first that would want splitting by year.

Per county rather than per area, on two counts. Area codes are not filenames: 31 contain a slash (`ed:Cavan:Dunmakeever/Benbrack/Derrynananta`), 2,808 contain a colon, 312 a space, 15 an apostrophe and 4 are non-ASCII — per-area files would need a slug scheme and a collision map, the same string-munging this page refuses when it declines to key the drill-down on `location`. And one county file serves every area a reader opens in a sitting, against 1,614 files churning through the Pages artifact twice a day.

**An event is listed under every area its pins were homed to**, not only the one it is named after. The two are different questions and the county breakdown already takes this position: it homes each *pin*, so a burst published as pins in Naas and in Sallins puts counts on both rows. Naming the *event* once and listing it only there left **220 of the county tables' 1,830 areas with no history at all**, and their pages said no notice had ever been published directly under a row that had just counted one. 764 events are multi-area; listing each under all of them costs 6 KB gzipped across every shard and is what makes the two pages agree. The record carries `areas` when it appears in more than one, because a reader who meets the same burst twice would otherwise reasonably conclude the site is double-counting. The naming decision is untouched - `area_of` still gives an event exactly one label for the open list and the top ten.

What a record carries: reference, title, worst severity across the event's pins, earliest publication, pin count, covered hours, how the end was signalled, open/closed state, and the raw `location` string as a display line. Not the notice text - 5.5 MB raw, 402 KB gzipped, four times the whole history. Not `work_category` - the title already states it, and it would only buy a filter. Two records deliberately say less than they could: an event **closed without ever reporting an end** publishes no duration at all, because its token one-second footprint would print "0.0h" for 801 events, and a **recurring** event publishes covered hours with the window series' span beside it rather than the span alone.

**The area directory is a separate page.** `areas.html` lists all 1,836 areas that have had a notice, grouped by county, each linking to its history — ~292 KB raw / 32 KB gzipped. Standalone rather than a fourth view in the single page, so the first paint does not grow to carry a list most readers will never open; `index.html` gains only the two links pointing at it. It also means Ctrl+F searches the whole list, which is worth more than any filter box at this size, and per-area notice counts are free because nothing is shipped up front. Deliberately **not paginated**: 1,836 rows render instantly, and paging them would break the search that makes a list this long usable. Areas with no notice at all — roughly 1,900 of the country's named areas — are left out; a page of them would say nothing.

### `closed_at` gives a past month something to say

The site's open-case figures are a right-now snapshot with no month dimension, so a historic month previously had nothing to report beyond its bars (see the known limitation below, and PR #21 which hid those figures on non-latest months for exactly that reason). `cases.closed_at` is the one field that does carry a month for a case that is no longer open, so the county view adds an **"observed to close in <month>"** section, and each town row a resolved count.

Its coverage is partial by construction and the copy says so: NULL for every case that closed before schema v2, and a case that opens and closes inside one build gap is never observed open, so never stamped. Read it as a floor. This is what lets a county with zero open cases still show something true — Carlow, at 0 open on the July 2026 snapshot, reports 8 cases observed closing that month across Rathvilly, Carlow town and the countryside around them.

### Cities: a settlement over 50,000 is split into Local Electoral Areas

**Simply put:** the Census treats a whole city and its suburbs as one place, which would make Dublin a single row holding most of its notices. So the five cities are split into their electoral areas, and the countryside outside any town is grouped by its electoral division as "Around X". The city uses the coarser electoral area because the finer division names there are "Bishopstown A" to "E"; the countryside uses the finer one because its names arrive clean.

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

With every Small Area belonging to a named area, a pin only fails to place when the Small Area nearest it lies in a different county from the one the notice names - the feed's `county` disagreeing with its own coordinates, for 267 of 14,557 pins on the 2026-10-06 release. Those collect in a `Pinned outside the county` row that reports its case counts and nothing else: it is not a place.

## Grades

**Simply put:** a county's letter for a month is the number of outage notices published per 100 km of its water main: fewer than one is an A, five or more an F. The cuts are fixed whole numbers, so a B means the same thing every month.

The letter is cut on the count metric below ("Outage notices per 100 km of main"): **A below 1, B below 2, C below 3, D below 4, E below 5, F at 5 or more**, and nothing else. Until 2026-10-06 it was cut on population-weighted availability; that scale, its E band and the sensitivity checks that retired it are in [archive/availability-method.md](archive/availability-method.md).

### The health notice is a marker beside the grade, not inside it (2026-08-02)

An active boil-water or do-not-consume notice used to knock the letter one step. It is published as a marker beside the grade instead, driven by `health_n` (notices active at any point in the month) and `health_now` (standing at build time) in the month payload; the copy makes the safety claim only where `health_now` is non-zero. The two questions, how much water was there and was it safe to drink, are independent, and one letter cannot answer both. A knock also hid information: a county already in the bottom band showed nothing, so Tipperary's July 2026 had three active health notices and no sign of any of them. The measurement that closed it, made on the availability scale, is in the archive. Discolouration is a quality event but never raises the marker: it is not a health notice.

## Mains length per county (2026-10-06)

`uisce-fetch-wsz` writes `data/wsz_mains.csv`, one row per supply zone (688: code, name, local authority, county, `DISMAINSLENGTH` in metres), from Uisce Éireann's Water Supply Zones layer on the feed's own ArcGIS org (`services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/watersupplyzonesDWQ_DeptView/FeatureServer/0`, layer `IWGIS_WSZ_Boundary`; `WSZ_URL` in `wsz.py`) with `returnGeometry=false`. The layer also carries each zone's census population and connection counts, and 81 boundaries were `UnderReview` on 2026-10-05; the probe that first measured it is in [archive/availability-method.md](archive/availability-method.md), "Supply zones as a limit on the circle". Source and attribution: Uisce Éireann's Water Supply Zones layer; terms have been requested and no licence is stated on the item, so the site should credit Uisce Éireann wherever the figure is shown. A county total is `wsz.county_mains_km`, an aggregate of the zone rows rather than a second file.

The layer's 31 local authorities merge to the site's 26 counties: Dublin City, Fingal, South Dublin and Dun Laoghaire-Rathdown to Dublin; Cork City to Cork; Galway City to Galway. Waterford and Limerick arrive already as city and county. An authority outside the map raises rather than drops its mains.

Totals sum to 53,756 km, the layer's own figure. Largest: Dublin 6,170, Cork 5,144, Donegal 4,418, Tipperary 3,519, Galway 2,963; smallest: Carlow 585, Monaghan 650, Cavan 653, Waterford 1,017, Wicklow 1,042.

Zones keyed to one authority can serve another county. With attributes alone, the one measurable signal is zone `CENSUSPOPULATION` against the county's census population: only Louth exceeds 100% (153,114 against 139,703, 109.6%, so about 13,400 people served from Louth zones live elsewhere, in practice Meath around Drogheda). Every other county is at or below 97%, the shortfall being group and private schemes. How much Louth's 1,625 km, or any other zone's, belongs over the line is not known without the boundary polygons; the figure is read as the authority's mains, not the county's, and a notice pinned in Meath counts against Meath but its zone's mains count for Louth, so Louth's rate per 100 km is the one most likely to read low and Meath's high.

## Zone lookup (2026-10-07)

**Simply put:** every pin is matched to the Water Supply Zone whose boundary it falls inside, at build, from boundaries committed in the repo. About 95 pins in 100 land in one; the rest are on group or private schemes the layer does not draw.

`uisce-fetch-wsz` also writes `data/wsz.geojson`: each zone's boundary as the layer serves it, every vertex, coordinates to 5 decimal places (about 1 m), keyed by code alone, one zone a line so a re-fetch diffs by zone. The fetch prints how many zones were added, removed and reshaped, and writes the mains table and the boundaries together or not at all: the boundaries must list exactly the mains table's zones. `wsz.ZoneLookup` answers a pin with a bounding-box prefilter and a ray cast, pure Python, no shapely; 14,665 distinct pins take about 3 s. The assignment is made at build and stored nowhere: the boundaries are re-fetched by hand, and a zone column in the DB would go stale behind them. `uisce-site` prints the coverage line every build.

**Coverage**, distinct pin coordinates: 95.47% of 14,467 on release 2026-10-04-1942, which reproduces the probe's 95.4% under "Supply zones as a limit on the circle" ([archive/availability-method.md](archive/availability-method.md)), and 95.52% of 14,665 on 2026-10-06-2104.

**A zone is tested part by part.** Some zones are drawn with parts that overlap each other. An even-odd ray cast over all of a zone's rings reads the overlap as a hole; it was the first version here, and it put 95.04% of pins in a zone on 2026-10-04-1942 instead of 95.47%. A pin is in a zone when it is inside one part's outer ring and none of that part's holes.

**A pin in two zones** goes to the smaller by area. The layer overlaps 8 pairs of zones under pins on 2026-10-06-2104, 24 pins in all: Kilsellagh inside Foxes Den (8), DCC Zone 3 and Zone 4 Leixlip (8), Glanmire inside Glashaboy, Innishannon inside Cork Harbour and City, and four with one pin each. The smaller is usually a town zone drawn inside its rural scheme.

**Rejected: simplified boundaries.** The plan's 3 MB budget for the file was never measured against accuracy, and nothing the browser loads reads the file. Fitting it needs the layer to smooth the boundaries by 35-55 m (`maxAllowableOffset=0.0005` degrees, 2.7 MB), which moved 128 of 14,665 pins against the full boundaries. Full-precision coordinates (21.5 MB, 8.3 MB compressed) were rejected for the 5 dp file (11.6 MB, 2.9 MB compressed in git): 3 of 14,665 pins differ.

## Outage notices per 100 km of main (2026-10-06)

**Simply put:** each county-month carries how many outage notices were published per 100 km of the county's water main, and a letter cut on that count. The median time to "works complete" sits beside it, unchanged.

**The numerator.** An outage notice is an event (one `reference_num` in one county, pins grouped as `event_meta` groups them) whose worst pin classifies as `outage`: a hard-supply category or an unplanned repair, not a repeating window (a restriction whatever its title), not a quality, conservation or pressure notice, not a lift. It is placed in the county the feed put it in, and dated by its earliest pin's publication (`first_pub`, the pinned start for a re-stamped case), which is the same reading the completion median uses for "started this month". A month counts only the part of it the site has seen: nothing before `COLLECTION_START`, and a notice dated ahead of the build waits for its day. The denominator is `wsz.county_mains_km` ("Mains length per county" above). On release 2026-10-06-2104, May to September, that is 5,869 events, and it reproduces to the decimal the figures first measured in a scratch probe with shapely ([archive/availability-method.md](archive/availability-method.md), "Supply zones as a limit on the circle"): Carlow 4.4, Louth 4.7, Leitrim 4.8, Dublin 8.7, Wexford 17.0, Waterford 20.8 (20.7 before the payload's two-decimal rounding), Kerry 23.8. Any-pin-outage and worst-pin-outage give the same set; all-pins-outage drops 26 events and moves Kerry to 23.7, so the worst-pin rule the top ten already uses is kept. `tests/test_site.py`, `TestNoticesPer100km`, builds that many notices on a fixture against the committed mains table and asserts the two headline sums.

**Simply put:** a month gets its letter only once it is over. Until then the page shows the letter for the last 30 days, which always rests on a full month of notices. Scaling a part month up was tried first: one notice on the 1st of the month gave Carlow an F.

**The month in progress is graded on the last 30 days** (owner, 2026-10-06). A month the site saw whole gets its rate and letter; any other (the month in progress, and April 2026, seen from the 20th) carries only `outage_notices`, its count so far, with `per_100km` and `count_grade` null. Each county carries `last_30` (count, rate, letter over the 30 days to the build) and the site carries the national `last_30` (count and rate), for every surface that says "now". The first version scaled the part-month count to the month's length; one notice in Carlow on the 1st read 5.1, an F. Measured on May to September, a part-month letter matches the month-end one in 53 of 130 county-months at day 3, 50 at day 5, 73 at day 7 and 71 at day 10, so a minimum-days gate like esb's stops the day-1 F but leaves a coin flip. An "above, about or below its usual pace" trend did no better (46 of 130 at day 5, 12 pointing the wrong way). The rolling window always rests on a full month of notices; its costs are that it lags (a burst stays in it for 30 days) and that it can change between builds with nothing new published, which the label carries. It is graded on the calendar-month cuts, so it reads about 1.5% more leniently than an average month (30 days against 30.4) and can sit a letter apart from the month just finished at a cut; not corrected, because a rate per 30 days is what a reader takes "a month" to mean. The window is gated as a month is, lettered only once it lies wholly from `COLLECTION_START` on. Both the window and the 'seen whole' test run to the last feed read (`data_as_of`), not the build clock: a UI deploy on a stale release would otherwise count the unread days as quiet ones. History stays on calendar months: they do not overlap, so they compare and sum, and the cuts were fitted on them.

**The distribution** over the 130 finished county-months, notices per 100 km per month:

| min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| 0.17 (Carlow May) | 0.92 | 1.24 | 1.76 | 2.50 | 3.38 | 7.20 (Kerry July) |

Nationally May 1.87, June 2.03, July 2.69, August 2.11, September 2.21.

| county | km | May | Jun | Jul | Aug | Sep | notices | per 100 km |
|---|---|---|---|---|---|---|---|---|
| Carlow | 585 | 0.17 A | 0.68 A | 0.51 A | 1.20 B | 1.88 B | 26 | 4.4 |
| Louth | 1,625 | 0.80 A | 0.80 A | 1.66 B | 0.86 A | 0.62 A | 77 | 4.7 |
| Leitrim | 1,285 | 0.23 A | 1.40 B | 1.17 B | 1.17 B | 0.78 A | 61 | 4.8 |
| Kildare | 1,886 | 1.38 B | 1.06 B | 1.06 B | 1.01 B | 0.74 A | 99 | 5.2 |
| Cavan | 653 | 1.07 B | 1.07 B | 1.38 B | 1.23 B | 0.92 A | 37 | 5.7 |
| Wicklow | 1,042 | 0.96 A | 1.06 B | 1.15 B | 0.86 A | 2.02 C | 63 | 6.0 |
| Westmeath | 1,402 | 1.28 B | 1.21 B | 1.50 B | 0.57 A | 1.50 B | 85 | 6.1 |
| Monaghan | 650 | 0.92 A | 1.39 B | 1.54 B | 2.31 C | 1.08 B | 47 | 7.2 |
| Galway | 2,963 | 1.05 B | 1.55 B | 1.28 B | 1.49 B | 1.92 B | 216 | 7.3 |
| Sligo | 1,695 | 1.89 B | 1.48 B | 1.48 B | 1.83 B | 0.89 A | 128 | 7.6 |
| Roscommon | 2,102 | 1.38 B | 1.38 B | 1.71 B | 1.52 B | 1.76 B | 163 | 7.8 |
| Offaly | 1,145 | 0.96 A | 1.75 B | 2.53 C | 1.92 B | 0.96 A | 93 | 8.1 |
| Dublin | 6,170 | 1.56 B | 1.43 B | 1.82 B | 1.82 B | 2.04 C | 534 | 8.7 |
| Longford | 1,213 | 1.57 B | 1.65 B | 2.97 C | 1.57 B | 1.40 B | 111 | 9.2 |
| Clare | 1,811 | 1.71 B | 1.60 B | 2.21 C | 1.77 B | 2.32 C | 174 | 9.6 |
| Donegal | 4,418 | 1.58 B | 2.56 C | 2.51 C | 1.49 B | 1.90 B | 444 | 10.0 |
| Kilkenny | 1,097 | 2.37 C | 2.28 C | 2.01 C | 2.37 C | 1.82 B | 119 | 10.8 |
| Mayo | 2,784 | 2.05 C | 2.12 C | 2.26 C | 2.34 C | 2.26 C | 307 | 11.0 |
| Limerick | 2,527 | 2.14 C | 1.98 B | 2.93 C | 1.70 B | 2.85 C | 293 | 11.6 |
| Meath | 1,428 | 2.31 C | 2.52 C | 3.01 D | 1.68 B | 2.38 C | 170 | 11.9 |
| Laois | 1,068 | 0.94 A | 2.06 C | 3.00 D | 3.65 D | 2.62 C | 131 | 12.3 |
| Tipperary | 3,519 | 2.13 C | 3.01 D | 3.61 D | 2.84 C | 3.35 D | 526 | 14.9 |
| Cork | 5,144 | 2.90 C | 3.05 D | 3.81 D | 2.66 C | 3.11 D | 799 | 15.5 |
| Wexford | 1,807 | 3.38 D | 2.27 C | 4.71 E | 3.43 D | 3.21 D | 307 | 17.0 |
| Waterford | 1,017 | 3.74 D | 2.75 C | 6.49 F | 5.31 F | 2.46 C | 211 | 20.8 |
| Kerry | 2,723 | 3.64 D | 3.67 D | 7.20 F | 4.77 E | 4.52 E | 648 | 23.8 |

**The cuts are whole numbers: A below 1, B below 2, C below 3, D below 4, E below 5, F at 5 or more** (`COUNT_CUTS`, `count_grade`). The scale reads in its own unit, "fewer than one outage notice per 100 km of main a month is an A", which the availability cuts never could. The letter is cut on the two-decimal figure the payload carries, so a rate that rounds onto a cut takes the letter the page shows: Laois July, 32 notices on 1,068 km, is 2.996, published as 3.00 and a D. Every band holds something on May to September, A 19, B 57, C 33, D 15, E 3, F 3; the three F are Kerry July 7.20, Waterford July 6.49 and Waterford August 5.31, the three E Kerry August and September and Wexford July. By month: May A 7 B 10 C 6 D 3, June A 2 B 14 C 7 D 3, July A 1 B 11 C 7 D 4 E 1 F 2, August A 3 B 14 C 5 D 2 E 1 F 1, September A 6 B 8 C 8 D 3 E 1. The median county-month (1.76) is a B where the availability scale put it at C: the count is not a re-labelling of the old letter, and the two agree on 28 of the 130 county-months, which is the point of the change rather than a defect of it. A fixed scale has to leave room above the record for a winter the archive has not seen; the two bands above the May-Sep p90 are that room.

**Rejected: cuts shaped to the archive's percentiles**, 0.5 / 1 / 2 / 3 / 5, which reproduce the availability scale's shape (A at the top 3%, the median at C): A 2, B 17, C 57, D 33, E 18, F 3. Two A in 130 is the empty-band problem the availability scale's E band was fitted to avoid (archive/availability-method.md, "The scale grew an E"), met from the other end, and shaping the cuts to the dataset is the ranking the owner declined at checkpoint B wearing fixed numbers. **Rejected: archive quantiles** (checkpoint B, owner answer 2026-10-06, fixed). Sextiles on May to September fall at 1.06 / 1.48 / 1.76 / 2.26 / 2.95, none of them a number a reader can hold; they fill every band by construction, 22 a letter; a fit on May to July alone (1.06 / 1.40 / 1.69 / 2.23 / 2.97) already moves 6 of those 78 letters against the May to September fit, so published letters would move every build; and they differ from the whole-number cuts on 86 of 130 county-months, which is the dataset-shape argument above in another form.

**Re-fit yearly**, first in October 2027 against the release DB, and sooner if a band holds nothing over a full year of months or the national rate leaves 1.5 to 3. The record to beat is the table above. Raising a cut moves published letters, so the re-fit is a dated section here, not a quiet constant change.

**Known limits.**

- The count ignores size: a village burst and a city trunk main each count one. The page says so (session 3); the median time to completion beside it is the only size the site can measure.
- Zones cross county lines, and a notice is placed by pin while its main is counted by zone authority. Measured on the 2026-10-06 release with the zone boundaries fetched into a scratch probe (nothing committed) for Louth, Meath and their neighbours, May to September cases: 69 of Meath's 592 pins (11.7%) fall in Louth's "South Louth & East Meath" zone (693 km) and 4 in Fingal Zone 1; 0 of Louth's 298 fall in a Meath zone; 14 Louth and 38 Meath pins are in no zone. So Meath's 1,428 km serves fewer of its notices than the count assumes and Louth's 1,625 km more: Meath reads high and Louth low, by at most that twelfth. Nothing else in the layer's attributes can say how much of a zone's main is over the line; session 6 brings the polygons in.
- A county of 585 km (Carlow) moves 0.17 per notice, so one notice is a sixth of a band; Dublin's 6,170 km moves 0.016. The coarseness is in the small counties, where it is also the honest resolution of the data.
- The feed's `county` is the notice's claim, not the pin's; "Known limitation: pins outside the county they claim" above applies here as to everything placed by county.

## The estimate is removed (2026-10-06)

**Simply put:** the code no longer works out how many people a notice reached. A pin is placed in the area of its nearest Census Small Area, a notice that never reported an end counts as a notice and has no length, and the ten largest disruptions are now the ten longest. Session 4 of [simplification-plan.md](simplification-plan.md); the page stopped showing the estimate in session 3 (frontend-notes.md, "The page counts notices").

**What went.** `SmallAreaIndex` and the 500 m circle, `SpanTable` and every imputed span, `union_seconds`, the availability `grade()`, `Region.event_pop`, `TownLookup.dominant` / `within`, and from the payload `person_h`, `period_h`, `availability`, `grade`, `median_pooled_h`, the per-day population share and the history's `people`. `sa_pop.py` and `data/sa_pop.csv` are folded into `towns.py` and `data/sa_towns.csv`, which now carries each Small Area's centroid and Census population (the area populations are Census counts and stay on the page). `eval_overlap.py` went with the person-hours it measured. `imputed_n` is `no_end_n`: the same events, counted the same way, with no span charged.

All figures below are release 2026-10-06-2104, built both ways over the same rows with the clock pinned at the data horizon.

**Placing a pin.** A pin takes the area of the nearest Small Area centroid within `PLACE_KM` (8 km, the old fallback radius), and is `UNPLACED` when that Small Area lies in another county than the notice names. An event is named for the area most of its pins were placed in, the earliest pin breaking a tie.

| Rule | Pins moved (of 14,557) | Area pages | Unplaced pins |
|---|---|---|---|
| 500 m circle, largest population share (before) | - | 780 | 263 |
| **Nearest Small Area centroid** (taken) | **177** | **785: 0 lost, 5 gained** | 267 |
| Nearest Small Area centroid in the notice's county | 366 | 786: 0 lost, 6 gained | 70 |
| Nearest area centroid (mean of its Small Areas) | 2,975 | 798: 5 lost, 23 gained | 75 |

The plan named "nearest settlement centroid"; read literally, that is the last row, and it is rejected: an "Around ..." Electoral Division or a city LEA is large, so its centre says little about where its pins are, and it would drop five permalinks. The in-county variant is rejected because it re-homes a pin the feed places over a county line into a town on the near side, which hides the disagreement the unplaced bucket exists to show. The five pages gained are Kells (Kilkenny), Beaulieu (Louth), Turlough (Mayo), Ballintober (Roscommon) and Ballyhack (Wexford); 174 of 12,016 events are listed under a different set of areas. Naming by most pins changes 660 event names; naming by the earliest pin alone would change 671 and is the rule that once called one burst "Allenwood" in the open list and "Prosperous" in the top ten.

**A notice with no end.** A closed notice with no usable end, or one whose own text ended it before it was published, is a one-second token on its publication, as it was before 2026-08-15. `no_end_n` equals the old `imputed_n` in every month (23, 39, 53, 58, 55, 85, 26 for April to October). The national median moves only where the 2026-08-15 section (now in [archive/availability-method.md](archive/availability-method.md)) said it had leaked through an event mixing an observed pin with an imputed one: July 12.7h to 12.5h (back to its value before imputation), October so far 8.0h to 7.7h; September's scheduled-only median 4.0h to 3.9h; three county-month medians in all. 80 of 5,070 county-day cells change, 61 of them to clear (50 planned-works days and 11 outage days that only an imputed span had coloured), and events active in a month move in 41 county-months of outages, by one or two either way, as imputed spans that crossed a month boundary or were anchored back from a known end stop doing so.

**The day bars keep one shade, and each cell is `[severity]`.** Session 3 already put every outage day on one colour. A ramp on outage notices standing per 100 km that day was considered and not taken: it needs thresholds fitted to a daily figure the site publishes nowhere else, and half of the 3,001 county-days with an outage on this release have one or two notices standing (931 and 617), where one notice more or less is the whole difference between two shades. The cell stays a one-element list rather than a bare string because a cached page from before this change destructures `[severity, share]`, and would read a string's first letter.

**The ten longest.** `#top` ranks the month's outage notices by the time from notice to "works complete": exactly the events the month's published median is taken over (outage class, first published in the month, an observed completion on some pin), at the covered hours that median reads, ties to the earlier publication. So the list is the tail of the distribution the headline summarises and prints no figure the median does not already rest on. An event with an outage pin cut at the 14-day cap, whatever that pin's end signal (a completion, a schedule, or still open), is flagged `capped` and its hours carry a "+" ("336h+"): the cap is a ceiling on what one notice counts, the notices that reach it ran longer, and an event's other pins can add hours of their own past it, so the figure is a floor and not a round "14 days" (WEX00118582, an August burst, reported complete after 889h). On this release one ranked event is flagged in each of April, June and August and none otherwise, the same whether the flag reads any cut pin or observed pins only, and the tenth place runs 67h to 92h. Rejected:

- *Person-hours*: the estimate.
- *Hours in the month for every outage notice, open ones included*: an open notice has no end yet, so the list would reshuffle between builds and rank notices on the cap rather than on anything they said.
- *Scheduled ends as well*: a plan is not evidence the works ended then, the same line the median draws.
- *The uncapped reported span*: it would rank on a figure the median does not use, and a lone over-long notice would sit first with nothing to compare it to; the "+" carries the same fact.
- *Pin count*: it measures how Uisce Éireann published a notice, not how long supply was off (DON00115765 is 18 pins of one nightly regime).

Complete months only, as before: the month under way gains completions as notices report them.

**Known limitation, left as it is.** An event counts as observed when any of its pins reported a completion, the OR the median reads, so a partly confirmed event ranks on all its outage pins' hours, scheduled or still open ones included. The row's badge says "partly confirmed - 1 of N notices reported complete" when that is so. On this release every ranked row is fully confirmed; ranking only fully confirmed events would make the list disagree with the median it is the tail of, and is the change to make if a partly confirmed row ever ranks.

## Repeating windows

**Simply put:** a notice that says works run nightly, say 10pm to 7am for three weeks, is counted as a restriction, not an outage, and its hours are the hours inside the windows, not the whole three weeks.

### A scheduled repeating window is a restriction, not an outage (added 2026-08-02)

The severity classes are keyed to the notice's title, and **Uisce uses two titles for one situation**. The same Donegal supply zone — Lifford, Rossgier — under the same nightly 10pm–7am regime was published as:

| date | reference | title | class | accrued |
|---|---|---|---|---|
| 30 Apr | `DON00111054` | Water **Conservation** | degraded | nothing |
| 23 Jun | `DON00114559` | Reservoir **Interruption** | outage | everything |
| 9 Jul | `DON00115765` | Reservoir **Interruption** | outage | everything |

Overlapping villages, identical window, near-identical wording, opposite treatment — and the July one was the largest single figure on the site. Whichever way that pair is resolved, it has to be resolved alike.

`classify` now takes `recurring` and downgrades an outage to `degraded` when the *event* announced a window repeating over a date range. It downgrades an outage and nothing else: a nightly leak-detection round is still maintenance. Recurrence is read at event level, not per notice, because the pin carrying the completion update reports no window and would otherwise sit as a lone outage inside a restriction event, whose interval the per-reference union then charges in full.

The reasoning: a scheduled, repeating, announced overnight window is demand management rather than a failure, and that is true whichever title carries it. The conservative side is also the one already published — restrictions have never counted here.

Measured on the 2026-08-02 corpus: only two July events move class, and no county's letter changed.

Note what this does *not* touch. May's largest event, a 23.8h reservoir interruption across Drogheda, is one continuous interruption with no repeating window and stays an outage - which is the discrimination the rule exists to make.

The expansion still earns its place for a restriction: the day bars, the event counts and the covered hours in the history read from those intervals, and the `end_recurrence` field it introduced is what this rule keys on.

### Recurring windows cover hours, not days (added 2026-08-01)

A notice reading *"daily from 10pm until 7am, from 9 July to 27 July"* is 18 nights of nine hours, not 16 days of continuous outage. Prompt v3 extracts the window itself (`recurrence`, `window_open`, `window_close`, `window_first_date`) and `resolve_case` expands it into one interval per night, so a `Case` now carries a *list* of intervals. Everything downstream already unioned and clipped lists, so only `Region.add` changed.

Three consequences worth stating:

**`median_completion_h` is covered hours.** For a single-block event that is also its elapsed span, so nothing moved for the other 99%. For a recurring event the two now differ sharply — a night's works inside a fortnight's presence — and the covered figure is the one published, because "how long did the works take" is the question the metric name asks. The site copy says so.

**Expansion is decided per notice; coverage is unioned per event.** One pin falling back to the continuous interval re-covers every gap the others carved out, so the fix can land on 17 of 18 pins and barely move the number. This is not hypothetical — it is what happened to `DON00115765` on the first v3 run, because the model reports no window on a notice whose text says the works are complete.

So a window is treated as a property of the **works**, not of the notice: `event_windows` lends the window any pin of a `reference_num` reported to the pins that reported none. The borrowed series is still clipped to the borrowing pin's own start and end, which is what makes this a reading rather than a guess - the completion pin takes the schedule and then stops at the moment it says the works stopped. Inherited windows face the same cross-check as claimed ones and are listed individually on every build, being the least-evidenced expansions here. Where pins disagree the commonest window wins, ties broken deterministically, and only a window the guard could honour stands for election (see [data-quality.md](data-quality.md), "A pin can report half a window"): one refused wherever it is read must not deny a sibling the window another pin did report, so the vote and the refusal both read it through `_read_window`. Every build also prints any event whose pins still disagree, which is the line that catches a fix landing on 17 pins and being undone by the 18th.

**The guard refuses by default.** A refusal is a numeric no-op, so the checks are deliberately suspicious: the recurrence value must be exactly `daily`, all three window fields must parse, open must differ from close, the series must produce at least two windows, and for a *scheduled* end the window's closing time must match the reported end time — the prompt requires them to be the same, so a disagreement is the model contradicting itself. Completion updates have no such cross-check available (their `local_time` is the completion, not a window close), so they are honoured and listed individually in the build report.



## Known limitations

- The count ignores size: a village burst and a city trunk main each count one. The median time to "works complete" beside it is the only size the site measures.
- The 14-day cap applies to each *notice*, not each event, so an event published as several staggered notices can run longer than 14 days; the ten longest flags such an event with a "+".
- `start_date` is the notice publication time, so every duration is a floor on true outage length (overnight events are typically posted the next working morning; see [data-quality.md](data-quality.md)).
- A notice counts for the county the feed names, not the one its pin sits in ("pins outside the county they claim" above).
- The county populations printed beside each county are hardcoded Census 2022 figures in site.py; no figure is computed from them.
- The month in progress has no letter of its own; the page shows the rolling 30-day letter instead. Cases downloaded since the last `uisce-infer` run have no end signal yet, so they colour the day bars to "now" and are missing from the median until inferred (see [pipeline-dependencies.md](pipeline-dependencies.md)).
- "Open cases" on the page is a right-now snapshot of `Case.is_open` (below), attached to the county rather than the selected month, so it does not vary as you page through months (the copy says so).

## The notice's own completion closes it (settled 2026-09-05)

**Simply put:** a notice whose own text says the works are complete is shown as closed, even while the feed still marks it open. The feed takes about three days to catch up, and the site already stopped counting the notice's hours at the completion.

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

**Decision.** A case is open only while nothing the notice itself has said has ended it: `is_open(row, now)` is `status = 'Open'`, not `vanished_at`, and not past an *observed* end (`OBSERVED_END_SOURCES`, plus `lifted_immediate`). The decision is made once, in `resolve_case`, and carried on `Case.is_open`, so the open list, `open_total`, the national open view, the county page's "Open now" section and its notice text, the history's "still open" / "at least Nh so far" and the Atom feed's "still open" all read the same answer and cannot drift apart again. On the 2026-09-05 release this takes the national open count from 437 to 260; every published figure is byte-identical under both readings with the clock pinned, which is the point: the arithmetic already believed the notice.

**What does not close a case here.** A passed scheduled end (133 on the day). A schedule is a plan the works may have overrun, the same line the published median draws ("The published time metric" above), and the feed saying Open past one is the only evidence either way. A completion reported for an instant still ahead of the build leaves the case open until then. And `closed_at` is untouched: it records the build that observed the feed close the case, so the "observed to close" list and the history's "closed <date>" keep meaning that, and a case closed by its own text reads as closed with no close date until the feed catches up.

**The general rule this settles**, because the deferral was the failure here rather than the five-line patch: when the site trusts a signal for the arithmetic, it trusts it for the display. A surface that reads the feed's `status` alone where the site's own extraction contradicts it is a bug, not a trade-off, and a trade-off left for the owner has to carry both sides' numbers. The measurements above took a few minutes against the release DB; the deferral left 177 finished disruptions listed as ongoing on the live site.

**Amended 2026-09-24 (owner decision): the close date follows the same reading.** The paragraph above kept `closed_at` as the close date so the "closed in <month>" lists and the history's "closed <date>" kept meaning "the build that saw the feed close it". The retroactive review measured what that cost: cases closed by their own text but still `Open` in the feed were in neither the open list nor any closed list, completions the feed closed three days later were filed under the following month, and every case that closed before schema v2 (July) had no close date at all, so April to June had no closed lists. `closed_on(row, now, start, closed_by)` in `site.py` now dates a close from, in order: the notice's own reported completion; the paired lift or the 14-day cap that `resolve_case` closed it with; `closed_at`. A completion before the case's publication (`start`, the pinned start for a re-stamped case, compared as instants) is not used, because the history reads a close before the start as a withdrawal. It is computed in `resolve_case` next to the open status and carried on `Case.closed`, so the closed lists, the history and the Atom feed read one answer; an event closes on its earliest pin, and an event with any pin still open is listed open and not closed. On the 2026-09-23 release with the clock pinned, against the build before it: the county closed lists go from 5,774 events to 8,785 (April 0 to 332, May 0 to 1,105, June 0 to 1,260, July 2,290 to 2,507, August 2,183 to 2,094, September 1,301 to 1,487); history events closed with no date fall from 5,072 to 2,055, and events listed both open and closed from 3 to 0. No letter, median or open-list figure moves. What still closes with no date: 2,378 vanished cases (by design, see data-quality.md), 43 closed with no signal and no `closed_at`, and 10 whose completion precedes their re-stamped start with no `closed_at`, the negative-span family of roadmap item 3.

**Reopen this if** the follow-up-after-completion count stops being zero (re-run the segment check in this section's commit against the current release), or if a labelled sample shows scheduled ends are met reliably enough to close a case for display too.

## The published time metric is notice → *observed* completion (settled 2026-07-20)

**Simply put:** the time figure runs from when a notice was published to when its own update said the works were complete. A notice that only gives a planned end is left out of that median, because a plan is not a result.

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

**Resolution:** a scheduled end still gives the notice an interval, so its days colour and its hours show, because a published plan is the best interval available - but it is excluded from the published median and reported separately as "+N scheduled-only". `OBSERVED_END_SOURCES` in `config.py` is the single switch. At event level the split holds every month (observed 7.1/12.6/15.8/10.2h against scheduled 4.8/5.3/4.4/4.3h for Apr–Jul 2026).

See the eval in [end-time-eval.md](end-time-eval.md) for how the LLM-extracted end times behind this are validated.

## Possible next steps

Deriving `COUNTY_POP` from the Small Areas, the one hardcoded population left (it is only printed beside each county, so the change moves no figure); an Electoral-Division split for the cities, trading a name-merging heuristic for vernacular area names and retiring the hyphenated LEA compounds (costed in the drill-down section above); the prompt change for "until midnight on D" ([roadmap.md](roadmap.md)).
