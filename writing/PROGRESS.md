# Progress ledger

Read this first each session. Keep it under ~1k tokens: status per chapter, a 3-line summary of
each drafted chapter (so the next session has continuity without re-reading it), open threads,
and the brief for the next session.

Statuses: `todo` → `drafted` → `reviewed` (continuity pass done by a later session) → `final`.

| Ch | Title | PRs | Status | Words |
|---|---|---|---|---|
| 00 | Intro | — | todo (final pass) | |
| 01 | A notice is a row | pre, #1–4 | drafted | 1,934 |
| 02 | Let a robot do it every week | #5–6 | drafted | 1,034 |
| 03 | Ask a local model what the notice actually says | #8–13 | drafted | 2,231 |
| 04 | Make it a real project | #14–15 | drafted | 1,296 |
| 05a | A website, and a number that is fair to Cork | #16 | drafted | 1,694 |
| 05b | An honest number on the model | #16–17 | drafted | 2,024 |
| 06 | Say what you actually measured | #18–20 | drafted | 2,090 |
| 07 | Record the moment a case closes | #21–22 | drafted | 2,074 |
| 08a | How a pin gets a population | #23 | drafted | 2,323 |
| 08b | Where you actually live | #23–25 | drafted | 2,491 |
| 09a | Eighteen nights in a trench coat | #26–27 | drafted | 2,000 |
| 09b | The title is not the severity | #28–31 | drafted | 1,950 |
| 10 | For a reader, not an analyst | #32–36 | todo | |
| 11 | Be findable | #37–39 | todo | |
| 12 | Put a number on what you don't know | #40–41 | todo | |
| 13 | Closing + glossary | — | todo (final pass) | |

## Chapter summaries (3 lines each, added when drafted)

- **01** Opens with the Leixlip question. Feed = ArcGIS feature service (Web Mercator → lat/lon,
  epoch-ms dates); pins reverse-geocoded via LocationIQ at 4-dp rounding with a cache; SQLite
  `cases` + `geocode_cache`; PR #4 upsert turns snapshot into archive because the feed has no
  memory (0/8,155 LASTUPDATE). Worked example KLD00118059 (Forest Park, Leixlip) foreshadows
  Ch 3 (end in prose), Ch 6 (end_date is a default), Ch 5/8 (no footprint). Concept boxes:
  ArcGIS feed; reverse geocoding + cache; notice/pin/case; the feed has no memory.
- **02** Weekly GHA (Mon 06:00 UTC) downloads last release DB → upsert → geocode new coords →
  publish dated Release; geocodes.jsonl folded into the DB. PR #6 backfills ~10 blank counties
  from the geocode cache, strips "County ". Concept box: CI as a scheduled clerk. Foreshadows
  Ch 7 (release snapshots are the only history; 1,816 closures recovered) and Ch 4 (one job per
  step). Ends: "when did the water come back" is in the prose, not a column.
- **03** Opens with end_date agreeing with the text 6.6% of the time. PR #8 gemma-4-12b-qat on
  LM Studio; PR #9 "do less in the model" — v1 asked for UTC+DST arithmetic (hallucinations,
  loops), v2 reads only: notes-first, end_source, local_date, local_time, temp 0. PR #10 hash
  gate + append-only JSONL as truth; PR #11 zoneinfo duration, NULL rules, ~19 negatives (→532,
  Ch 6); PR #12 pin start at first inference, JSONL/DB independent; PR #13 table on CI (6,561).
  15 Jul benchmark detour: decode-bound, qwen faster but wrong. Worked example KLD00118059
  → 52,987 s. Concept boxes: extraction is reading not writing; hash-based incremental work.
  Ends: accuracy unmeasured (Ch 5, 71.9%); column misnamed (Ch 6).
- **04** PR #14 package + 42 tests + hardening (retry, ordered paging, placeholder geocode rows,
  circuit breaker, dedupe −15% calls, timeout 120 s). PR #15 work_category (26 slugs) and
  work_type 31%→89% by title rules; today 90.4%, 16 uncategorised. Concept boxes: what a test
  suite buys; a title is a category, not a severity (→ Ch 9). Ends: next the Census, Ch 5.
- **05a** Cork May uptime 2% → person-hours and SAIDI-style availability (~99.2%); Small Areas
  within 500 m (details deferred to Ch 8a); four classes, outage-only accrues (investigation
  was ~8%); events by reference_num, intervals and footprints unioned; A–F thresholds stated,
  calibration deferred to Ch 12; Ofwat 99.999% not comparable; page claims "announced
  disruptions and time-to-fix". Worked example Drogheda 23.8 h × 23,169 = 551,427 ph → Louth
  May 99.469% (C) alone; vs Drogheda's own 44,135 → 98.3% (foreshadows Ch 8). SVG diagram
  person-hours-rectangle. Concept boxes: person-hours; population-weighted availability.
- **05b** Round 1 stratified 114: 71.9% raw / 82.8% duration-feeding; error taxonomy;
  lifted_immediate excluded. pv2: skip-logic bug (bump re-read nothing), replay harness, ruler
  defects (~4 pts, four labels amended), 81→99/114, 99/99. Round 2 uniform 120/120; rule of
  three → ≥97.5%. Corpus 7,892 re-read, date_only 55→0, no fabrications. Boil-notice staleness
  (Cork May F→D) and no-better-start (toggle rejected). Concept boxes: stratified sample;
  replay vs hold-out. Ends: the metric gets renamed → Ch 6.
- **06** PR #18 renames (notice_to_end_seconds etc.), floor not estimate; observed 17.0 h
  (3,166) vs scheduled 5.4 h (894) vs pooled 9.3 h — plans still accrue, excluded from median;
  overrun probe 69.5% late (parked); 183 un-inferred. PR #19: 532 negative spans (not 19),
  re-stamp evidence, 12 open outage cases fabricating ~101k Kildare / 66k Donegal ph →
  ended_by_publication; both rescue routes closed (minimum-start rejected — Ch 3's promise
  kept); create_db double column. PR #20 Pages deploy. Worked examples: case 237573 (−5 h 04 m)
  and a toy pooled-median list. SVG observed-vs-scheduled. Concept boxes: floor vs estimate;
  why pooling two populations lies. Ends: nobody can say which month a case closed → Ch 7.
- **07** "49 open now" on a historic month; closed_at stamped in the upsert — observation time,
  NULL ambiguous, a floor (12% under Mon/Wed/Fri); closed_at values pile up on build days
  (304/363/365/399). Schema v2 via the additive-only ladder (0.7 ms). Feed probe (0/8,155);
  replay of 10 release snapshots recovers 1,816 of 7,613 (24%) — Ch 2's accident pays. PR #22
  daily builds; re-measured 31 Jul: 1.9% never seen open, but utility closes cases a median
  75.7 h late — the floor's owner is the operator. Worked example KLD00118059's five days
  (72 h lag). SVG build-gap-timeline. Concept boxes: observation vs event time; additive-only
  migration ladder. Ends: closed_at's first use is Ch 8.
- **08a** cases.location unusable (3,866 values); Small Area concept box (18,919 → 5,149,139);
  the four Census files table with join keys and traps + mermaid; 500 m centroid rule (grid
  bins, fallback 8 km, cache) with concept box "centroid, not polygon"; SA→named area is the
  CSO's own attribute; the retracted point-in-polygon method (97.5%, 54 settlements missing,
  187/789 >10% short, Doneraile 214 vs 857 ~4×) with concept box on systematic under-count in
  a denominator; join wrinkles (19 shared names, 125 straddlers). Worked examples: KLD00118059's
  circle = 12 SAs / 3,255 people, all Leixlip, ≈47,900 ph; radius 300 m/1 km → 1,966/8,440
  (plants Ch 12); Leixlip 56 SAs = 16,733 exact. SVGs: pin-circle-centroids,
  doneraile-polygon-vs-attribute. Ends: tiers/homing/straddle → 8b, ending at the Kildare table.
- **08b** Three tiers concept box + one rule ("finest official geography whose names arrive
  usable"); Dublin 1,261,884 = 83% → 40 LEA rows, 30% sliver threshold and why it kills name
  collisions; 242/1,492 vs 0/2,552 suffixing; rural bucket 44% / 22 of 26 → 1,172 "Around <ED>";
  uniform alternative rejected (~300 km²); LEA names administrative (12/5/11), ED costed;
  homing by dominant share (median 1.00) + charge only inside (SVG straddle); own-county guard,
  "Pinned outside the county"; no town grades (0.18 vs 11); county page, closed_at first use
  (Carlow 8), payload 645 KB. Worked example: PR #23's Kildare table reconciled via the 588.5 h
  observed denominator; today's full-July: Leixlip 438,691 / 96.48% vs Naas & Maynooth 100%,
  county 99.20% D — THE ANSWER. Mermaid tier tree. #24/#25 as footnotes. Ends: → Ch 9 recurring
  windows.
- **09a** #26 midday build (7.7→3.9 h) as an aside. Concept box pin/case/event (LOU00112686;
  union intervals, union footprints, cap) + SVG pins-to-event. Top ten (21.9%); NULL-category
  leak (66, one #9; Cork DNC lift). Recurring windows: representation not reading; concept box
  hours-not-days; v3 replay identical; results table (−7.7%, Donegal 22,156→12,682/1k). Two
  failures: completion pin re-covered gaps → event_windows lends; the report that missed it.
  Worked example DON00115765 (162 announced, 144.0 run, 385.2 charged, 6,596 people) + SVG
  recurring-window. Ends: 949,824 still looked wrong → 9b.
- **09b** #28 name once (348 events; Exton/Wyeville/Zedbury table). #29 same zone two titles
  table; phrase counts rule out the text reading; concept box "a repeating window is a
  restriction whatever the title"; −3.8%, Donegal rank 1→6, no grade changes; reduced_pressure
  backfill; expansion now numerically inert. #30/#31 review 2/9, concept box "review the
  consequential calls"; text+model detection; grade thresholds checked (one letter). Worked
  example: Donegal event 2,540,854 → 949,824 → 0. Ends: correct but unreadable → Ch 10.

## Open threads

- README says `SCHEMA_VERSION` "currently 2"; code says 3 — separate fix, not for the series.
- Oldest `start_date` in the DB is `0206-08-10` (mis-typed year in the feed) — a possible
  footnote in Ch 1 or Ch 6 about trusting feed dates.
- PR #23's Kildare table shows Naas at 25,824; the corrected settlement figure is 26,180. When
  quoting the table say "as published in PR #23" and note the correction once.

## Next session

**Ch 10 + Ch 11** (light pair). Ch 10 "For a reader, not an analyst" (PRs #32–#36, 5–6 Aug):
per-area incident history + directory (1,836 areas; 220 of 1,830 with no history because
multi-area events named once; 764 multi-area; 6 KB gz; 801 false 0.0 h; h/<county>.js shards
1.5 MB/183 KB), legend icon (#33), plain-language rewrite (#34: Cavan 27/31 clear days on 6 Aug;
100.00% beside a disruption; 2,600-char paragraph → seven sections), Actions bump (#35), mobile
view switching (#36, 375 px). Also the health-marker unbundling (2 Aug, in #29's timeframe? —
check `sources/ch10.md` and notes "The health notice was unbundled from the grade" ~185: 0.45 pp
vs 0.003–0.012 pp ~100×; Tipperary three notices invisible; grade mix A2 B16 C31 D19 F10 → A2 B17
C34 D18 F7). Ch 11 "Be findable" (PRs #37–#39, 6–8 Aug): county landing pages 2→28 indexable
URLs, static text 73,087→383,714 chars, analytics pages 1→28, retraction of #25's pushState;
#38 link; #39 trim comments duplicating notes. Read: this file → `README.md` → `outline.md` Ch
10–11 → `sources/ch10.md` (~4.2k words), `sources/ch11.md` (~1.6k) → notes
`statuspage-methodology.md` "The health notice was unbundled from the grade" (~185–225) and the
history/directory paragraphs already read in Ch 8b (lines ~100–112, skip) → `notes/frontend-notes.md`
(short). Concept boxes: history lists name an event under every area it reached, accounting
charges it once; health marker beside the grade not inside it; why a JS-routed static site is
invisible to search. Worked example: Cavan clear-days arithmetic; the pushState retraction.
Register figures. Update this file. Commit.

_Superseded brief (done):_ **Ch 9 "Not everything is an outage"** (PRs #26–#31, 31 Jul – 2 Aug; heavy — likely split into
9a events/recurring windows and 9b naming/severity/review). Read: this file → `README.md` →
`outline.md` Ch 9 → `sources/ch09.md` (~8k words — the biggest; read in two passes, #26–#27
then #28–#31) → `notes/statuspage-methodology.md` "The national top ten" (~230), "A scheduled
repeating window is a restriction" (~242), "Recurring windows cover hours, not days" (~264) →
`notes/data-quality.md` "Multi-pin events" (~131), "The notice title is not a reliable severity
signal", "A missing variant was silently inventing supply outages (found 2026-08-01)" (~144),
"What the v3 corpus run delivered" (~164) → `src/uisce/site.py` `daily_windows` (~609),
`event_windows` (~708), `recurring_intervals` (~740), `Region.add` (~1019), `event_pop` (~1068).
Cover: #26 midday build (7.7 → 3.9 h) and 75.7 h feed lag; #27 top ten (21.9%), DON00115765
"daily 10pm–7am, 9–27 July" 385.2 h → 144.0 h, July −7.7%, NULL-category leak (66 cases, one
#9); #28 name an event once over its footprint (348 events, Exton/Wyeville/Zedbury table); #29
repeating window is a restriction whatever the title (Donegal Conservation vs Interruption,
949,824 ph, −3.8%); #30/#31 recurrence review 2 right / 9 wrong, text detection, pv3. Concept
boxes: pin vs case vs event (LOU00112686 13 pins; 675 refs / 1,930 rows); interval union +
population unioned once, capped; recurring windows as hours not days; the completion pin
borrows its siblings' window. Worked examples: DON00115765 arithmetic (18 pins, 9–11 Jul
publication; 18 nights × 9 h = 162 h — reconcile with the 144.0 h figure: PR #27 says 144.0;
check whether that is 16 nights or clipped to "now"/month; register); Exton table lifted from
#28. Diagrams: SVG 16 solid days vs 18 nightly stripes; SVG 13 dots → one event with unioned
footprint. Continuity: Ch 5a "eighteen nightly windows in a trench coat"; Ch 4 "title is a
category not a severity"; Ch 7 promised the 31 Jul twice-daily reason. Register figures.
Update this file. Commit.

_Superseded brief (done):_ **Ch 8b "Where you actually live"** (PR #23 second half + #24, #25 footnotes). Read: this file
→ `README.md` → `outline.md` Ch 8 concepts 4–6 → `sources/ch08.md` lines ~106–260 (commits
"Break each county down", "Split the city agglomerations", "Correct the claim that LEA names",
"Take the drill-down geography… name the countryside", "State the drill-down geography rule
once") and the #24/#25 stubs at the end → `notes/statuspage-methodology.md` "The county
drill-down" (~81–180: closed_at gives a past month something to say; Cities; LEA names;
countryside; pins outside the county) → `src/uisce/site.py` ~470–545 (`TownLookup.dominant`,
`.within`) → `src/uisce/towns.py` `split_large_settlements` (~172), `around_label` (~72).
Cover: three tiers (settlement / LEA >50,000 / "Around <ED>") and *why* — the finest official
geography whose names arrive usable (242/1,492 city EDs letter-suffixed vs 0/2,552 rural);
Dublin 1,261,884 = 83% of cases → 40 rows; MIN_PART_SHARE 0.30 and "Elsewhere in…"; rural
bucket ranked first in 22/26 → 1,172 areas; homing by dominant share (median 1.00); straddle
rule (filed under winner, charged only what's inside → area ph ≤ county); cross-county refusal
and "Pinned outside the county" (~1.5%); no town grades (0.18 pt vs 11); payload 645 KB;
closed_at's first use (Carlow 8 closures). END on the Kildare July table (Leixlip 405,666 ph
95.88% vs Naas 100%) — the answer to the original question; note Naas 25,824 → 26,180
correction once. Worked examples: Kildare table arithmetic (405,666 ÷ (16,733 × 744 h) =
3.26% → 96.74%? — check: PR says 95.88%; July observed window may be shorter than 744 h or the
2 events' footprints differ; derive or mark [verify]); a 60/40 straddle toy. Diagrams: mermaid
three-tier decision tree with Leixlip / Kimmage-Rathmines / Around Ardmayle as leaves; SVG
straddle. #24 (Cloudflare analytics) and #25 (pushState — retracted in Ch 11) as footnotes.
Register figures. Update this file. Commit.

_Superseded brief (done):_ **Ch 8a "How a pin gets a population"** (PR #23, first half — the chapter Barry most needs).
Read: this file → `README.md` → `outline.md` Ch 8 concepts 1–3 → `sources/ch08.md` (~4.5k
words; PR #23 body + commits, incl. the "Kildare 99.25% hid…" commit) →
`notes/population-data-sources.md` (whole, ~1.4k words) → `src/uisce/site.py` ~415–470
(`SmallAreaIndex`, `_near`, `affected`) → `src/uisce/towns.py` `resolve_settlements` (~145) and
the header comments 21–50. Cover: the four Census files and their join keys; Small Areas
(18,919 → 5,149,139 exactly); pin → SAs by centroid distance within 500 m, else nearest within
8 km, 0.01° grid hash; SA → named area is an attribute lookup; the retracted point-in-polygon
version (37 MB, 54 settlements missing, 187/789 >10% short, Doneraile 214 vs 857). Worked
examples: Leixlip 56 SAs → 16,733 exact; a real pin's 500 m circle listing its SAs (write a
~15-line script using `SmallAreaIndex` against KLD00118059's coordinates 53.3627, −6.506 —
one-off, register the result). Diagrams (SVG): circle over centroid dots; polygon-vs-attribute
on Doneraile. Leave tiers/homing/straddle/Kildare table for 8b. Register figures. Update this
file. Commit.

_Superseded brief (done):_ **Ch 7** (PRs #21–#22: `closed_at`, schema v2 and the additive-only migration ladder, replaying
release DBs to recover 1,816 of 7,613 closures, 12% of cases open+close inside one build gap →
daily builds). Read: this file → `README.md` → `outline.md` Ch 7 → `sources/ch07.md` (~2.2k
words) → `notes/data-quality.md` "`closed_at` is a floor" (line ~209) and its "Re-measured
2026-07-31" subsection (line ~215) → README migration paragraphs (~lines 25–40) →
`src/uisce/replay_closed_at.py` docstring only. Worked example: a case seen Open in the 14 Jul
snapshot and Closed in the 16 Jul one — closed_at = 16 Jul (a floor); and KLD00118059's
closed_at 2026-08-13 12:02 vs its text's 1 pm 10 Aug (three days of feed lag — ties to Ch 9's
75.7 h median). Diagram: timeline with build ticks and a short case that fits between two (SVG).
Continuity: Ch 2 promised the release snapshots would recover 1,816 closures; Ch 6 ended on
"which month did a case close". Register figures. Update this file. Commit.

_Superseded brief (done):_ **Ch 6** (PRs #18–#20: rename to notice_to_end, observed 17.0 h vs scheduled 5.4 h vs pooled
9.3 h, the 532-case negative-span family and ~101k fabricated Kildare person-hours, deploy to
Pages). Read: this file → `README.md` → `outline.md` Ch 6 → `sources/ch06.md` (~2k words) →
`notes/statuspage-methodology.md` "The published time metric is notice → observed completion"
(line ~324) → `notes/data-quality.md` "Measured 2026-07-20: ends preceding publication are 532
cases" (grep the heading; the rejected minimum-start rule is there — Ch 3 promised it).
Worked example: the median arithmetic with the three n's; maybe a real negative-span case.
Diagram: two histograms "measured" vs "promised" (SVG, simple). Continuity: Ch 5b ended
"three days later the site changed what it called the number"; Ch 1 said end_date "reads like
a system default". Register figures. Update this file. Commit.

_Superseded brief (done):_ **Ch 5** (heavy — first site, person-hours, availability, grades, the model eval). Read: this
file → `README.md` → `outline.md` Ch 5 → `sources/ch05.md` (~3.4k words) →
`notes/statuspage-methodology.md` "Why not plain uptime?" and "Severity classes" →
`notes/end-time-eval.md` "Workflow", "Labelling guide", and the 2026-07-18/19 results → `site.py`
`region_month` (~1075–1120) and `grade`. Worked example: one event's person-hours → a
county-month availability (Drogheda 23.8 h / 551,427 ph is in the notes; or derive one for
Kildare July from PR #23's table). Diagrams: rectangle (hours × people); a county-month bar with
the lost sliver. Keep grade *calibration* for Ch 12 — Ch 5 only states the thresholds. Continuity:
Ch 3 promised "71.9%" and Ch 4 ended "that is where the Census comes in". Register figures.
Update this file. Commit.

_Superseded brief (done):_ **Ch 3** (+ Ch 4 if the window allows). Read: this file → `README.md` → `outline.md` Ch 3–4 →
`sources/ch03.md` (~1.7k words), `sources/ch04.md` → `notes/end-time-eval.md` intro and
"Decision: `lifted_immediate` is excluded" → `notes/model-and-runtime-benchmarks.md` (whole,
short). For the worked example reuse KLD00118059 from Ch 1: pull its `inferred_cases` row
(`end_source`, inferred end, `notice_to_end_seconds`) and, if cheap, the prompt text from
`src/uisce/inference.py`. Continuity: Ch 1 promised that "getting the end out of the prose is
chapter 3"; Ch 2 ended on the same line. Register figures. Update this file. Commit per chapter.

## Session log

- 2026-08-18 · Session 8 · drafted Ch 9a (2,000 w) and 9b (1,950 w); SVGs recurring-window,
  pins-to-event; reconciled 144.0 h / 6,596 people.
- 2026-08-18 · Session 7 · drafted Ch 8b (2,491 w); SVG straddle; reconciled PR #23's Kildare
  table (588.5 h denominator) and pulled today's July figures from data.js.
- 2026-08-18 · Session 6 · drafted Ch 8a (2,323 w); two SVGs; measured KLD00118059's 500 m
  footprint (12 SAs / 3,255) and Doneraile's three SAs.
- 2026-08-18 · Session 5 · drafted Ch 7 (2,074 w); SVG build-gap-timeline; measured closed_at
  distribution and KLD00118059 lifecycle.
- 2026-08-18 · Session 4 · drafted Ch 6 (2,090 w); SVG observed-vs-scheduled.
- 2026-08-18 · Session 3 · drafted Ch 5a (1,694 w) and 5b (2,024 w) — Ch 5 split as the length
  rule intends; first SVG diagram.
- 2026-08-18 · Session 2 · drafted Ch 3 (2,231 w) and Ch 4 (1,296 w); pulled prompt v1/v2 diffs
  and KLD00118059's inferred row; category counts measured.
- 2026-08-18 · Session 1 · drafted Ch 1 (1,934 w) and Ch 2 (1,034 w); measured 10,610 cases /
  10,550 distinct rounded coords; KLD00118059 pulled as the running example.
- 2026-08-18 · Session 0 · scaffold: README (style guide), outline, figures registry with anchors
  verified, source pack built (12 files, 34.7k words) via `tools/build_sources.sh`.
