# Outline — 12 chapters, chronological (+ 14–16 added as PRs landed)

Each entry: PRs · thesis (what the site now thinks) · concepts to box · worked example · diagram ·
reading list beyond `sources/chNN.md`. Read notes *by section heading only* (grep the heading,
then `Read` with offset/limit); `statuspage-methodology.md` and `data-quality.md` are ~13k tokens
each and must never be read whole. Figures listed here are already registered in `figures.md`
with sources; quote from there.

Session pairing: 1+2 · 3(+4) · 5 · 6 · 7 · 8 (splits into 8a/8b) · 9 · 10+11 · 12 · final pass.

---

## Ch 1 — A notice is a row · pre-PR commits, #1–#4 · 24–30 Jun 2026

**Thesis.** Fetch the ArcGIS feed, map fields, geocode, write SQLite; then upsert instead of
recreate — the decision that turned a snapshot into an archive. Open with the Leixlip motivation.

**Concepts.** *What an ArcGIS feed is* (a live map layer queried as JSON) · *the feed has no
memory* (0 of 8,155 rows carry LASTUPDATE/CREATEDATE) · *reverse geocoding, and why a cache
exists* · *upsert*.

**Worked example.** One real notice from feed JSON to a `cases` row (pick any current Kildare
case: `sqlite3 -readonly out/uisce.db "select * from cases where county='Kildare' limit 1"`).

**Diagram.** Feed (snapshot) → DB (archive), one-way arrow; mermaid.

**Reading.** `notes/how-it-works.md` "The shape of it"; `notes/data-quality.md` "The feed
carries no modification timestamp".

## Ch 2 — Let a robot do it every week · #5, #6 · 30 Jun (light; pair with Ch 1)

**Thesis.** The DB is a published artefact: weekly GitHub Actions build, dated Release. ~10 of
5,000+ cases had empty county → backfilled from the geocode cache; "County X" → "X".

**Concept.** *CI as a scheduled clerk* (a machine that runs the same errand on a timer and files
the result somewhere public).  No diagram.

## Ch 3 — Ask a local model what the notice actually says · #8–#13 · 2–9 Jul

**Thesis.** The end time is buried in prose. Extract it with a local LLM; track description
hashes so only changed text is re-read; pin the start date because the feed re-stamps it.

**Concepts.** *LLM extraction as structured reading, not generation* · *"do less in the model"*
(#9: hallucinations and infinite loops when asked to compute) · *hash-based incremental work* ·
*DST-correct durations via zoneinfo* (#11) · *JSONL vs DB as separately evolving artefacts* (#12).

**Worked example.** One notice → prompt → `{end_source, end_time}` → `notice_to_end_seconds`.

**Diagram.** Notice text → model → JSON → duration; mermaid.

**Reading.** `notes/end-time-eval.md` intro + "Decision: `lifted_immediate` is excluded";
`notes/model-and-runtime-benchmarks.md` (short, whole). Memory: gemma over qwen; decode is the
bottleneck; requests serialised.

## Ch 4 — Make it a real project · #14, #15 · 10–11 Jul (short; may pair with Ch 3)

**Thesis.** Package, tests, retry/circuit-breaker, category from title. 42 tests; dedupe
identical descriptions ≈ 15% fewer LLM calls; timeout 15 s → 120 s; `work_type` coverage
31% → 68% → 89% via 26 title categories, 29 unplaced.

**Concept.** *A title is a category but not a severity* (foreshadow Ch 9).

## Ch 5 — A website, and an honest number on the model · #16, #17 · 18–20 Jul (heavy)

**Thesis.** Data is for readers; the model needs a measured accuracy. First site, per-county
month view, A–F grades, population-weighted availability from Census Small Areas within 500 m of
a pin.

**Concepts (box each).** *person-hours = people × hours* · *SAIDI-style availability vs plain
uptime* (Cork May 2026: 2% binary vs ~99.2% weighted) · *stratified sample; replay vs holdout;
why 120/120 is not 100%* (95% lower bound ≈ 97.5%) · *A–F grade* (thresholds only; calibration
story belongs to Ch 12).

**Worked example.** One event's person-hours → the availability fraction for a county-month
(Drogheda reservoir interruption: 23.8 h, 551,427 person-hours).

**Diagrams.** Rectangle (hours × people); a county-month bar with the lost sliver shaded.

**Reading.** `notes/statuspage-methodology.md` "Why not plain uptime?", "Severity classes";
`notes/end-time-eval.md` eval design; `src/uisce/site.py` `region_month` (~1075–1120), `grade`.

## Ch 6 — Say what you actually measured · #18, #19, #20 · 20 Jul

**Thesis.** Name the metric after the thing it is: `notice_to_end_seconds`. Observed completions
17.0 h (n=3,166) vs scheduled ends 5.4 h (n=894); pooled 9.3 h. The 532-case negative-span family
fabricated ~101k person-hours in Kildare in July alone (~66k Donegal). Schedule overrun probe:
69.5% finish late, median +2.7 h. Deploy to Pages.

**Concepts.** *A floor is not an estimate* · *why pooling two populations lies*.

**Worked example.** The median arithmetic with the three n's.

**Diagram.** Two histograms, "measured" vs "promised".

**Reading.** `notes/statuspage-methodology.md` "The published time metric";
`notes/data-quality.md` "Measured 2026-07-20: ends preceding publication are 532 cases".

## Ch 7 — Record the moment a case closes · #21, #22 · 21 Jul

**Thesis.** The feed has no history, so we become the history: `closed_at`, schema v2 (0.7 ms
migration on a 20 MB DB), replay of release DBs recovering 1,816 of 7,613 closures; 12% of cases
open and close inside one build gap → daily builds (~7 GB/yr of release assets).

**Concepts.** *Schema migration as an additive-only ladder* · *observation time vs event time* ·
*`closed_at` is a floor*.

**Diagram.** Timeline with build ticks and a case that fits between two.

**Reading.** `notes/data-quality.md` "`closed_at` is a floor"; README migration paragraph.

## Ch 8 — Where you actually live · #23 (+ #24, #25 as footnotes) · 25–27 Jul (heaviest)

Plan as **two posts**: **8a "How a pin gets a population"** (concepts 1–3) and **8b "Where you
actually live"** (concepts 4–6 and the Kildare table).

**Thesis.** A county is not a place. Kildare, July 2026: Leixlip (16,733) 2 disruptions,
405,666 person-hours, 95.88% vs Naas 0 disruptions, 100.00% — the answer to the original
question. Commit "Kildare 99.25% hid the fact that Leixlip lost a ninth of its person-time and
Naas lost none" is the thesis statement.

**Concepts, in pipeline order.**
1. *Census 2022 Small Area* (18,919 SAs summing to 5,149,139 — the exact state total) and *the
   four Census files and their join keys* (SAPS CSV `T1_1AGETT` on `GUID`; SA ArcGIS layer with
   `SA_URBAN_AREA_NAME`, `CSO_LEA`, `ED_ENGLISH`; Urban Areas layer, 867 settlements; BUA CSV
   for verification only, cp1252).
2. *Pin → Small Areas by centroid distance, not polygon*: every SA centroid within 500 m; else
   the nearest within 8 km; 0.01° grid hash so no GIS library. (`site.py:SmallAreaIndex.affected`)
3. *SA → named area is an attribute lookup, not geometry* — and the retracted point-in-polygon
   version: 37 MB of polygons, 54 settlements with no row, 187 of 789 >10% short, Doneraile 214
   vs 857 (a burst read ~4× worse). Now all 867 settlement populations reproduce exactly.
4. *Three tiers*: settlement / LEA when a settlement > 50,000 (Dublin city and suburbs =
   1,261,884, 83% of Dublin's cases → 40 rows) / "Around \<ED\>" for the ~40% of cases outside
   any settlement (was one bucket ranking first in 22 of 26 counties → 1,172 named areas). City
   EDs letter-suffixed (242 of 1,492), rural not (0 of 2,552) — why the tiers use different layers.
5. *Homing a pin by dominant share* (median share 1.00) and *the straddle rule*: filed under the
   winner, charged only the population inside it (`TownLookup.dominant`, `.within`) so area
   person-hours ≤ county's.
6. *No letter grades below county* (24 h event: county of 62,000 moves 0.18 pt; town of 1,000
   moves 11).

**Worked examples.** (a) Leixlip: 56 SAs → 16,733, exact (verified 18 Aug 2026). (b) A pin's
500 m circle: list its SAs and populations → affected population (derive one from
`SmallAreaIndex` against a Leixlip pin; small script, once). (c) A straddling circle 60/40.

**Diagrams.** Circle over a grid of centroid dots (SVG); polygon-vs-attribute on Doneraile (SVG);
three-tier decision tree with Leixlip / a Dublin LEA / "Around Ardmayle" (494 people, 1 SA) as
leaves (mermaid); a straddle (SVG).

**Reading.** `notes/population-data-sources.md` (whole, ~1.4k words);
`notes/statuspage-methodology.md` "The county drill-down", "Cities", "The countryside";
`src/uisce/towns.py` `resolve_settlements`, `split_large_settlements`, `around_label`;
`src/uisce/site.py` ~436–540 (`SmallAreaIndex`, `TownLookup`).

## Ch 9 — Not everything is an outage · #26–#31 · 31 Jul – 2 Aug (heavy; may split)

**Thesis.** A repeating schedule is not a continuous outage; an event is one thing across all
its pins; the title alone is not severity.

**Figures.** 12:45 build cuts publication latency 7.7 h → 3.9 h mean; feed marks Closed a median
75.7 h after works finish (97% > 24 h). Ten largest events = 21.9% of July person-hours, one 9%
alone. "Daily 10pm–7am, 9–27 July" charged 385.2 h continuous → 144.0 h; July national
27,505,846 → 25,395,359 (−7.7%); Donegal per-capita 22,156 → 12,682 h/1k. NULL-category leak: 66
cases as hard outages, one ranked #9. Naming disagreed on 348 events (4.7%; 37.6% of multi-pin).
Same Donegal zone titled "Conservation" (accrued nothing) vs "Interruption" (949,824
person-hours). Recurrence review: 2 right, 9 wrong; text detection added (#31).

**Concepts.** *pin vs case vs event* (LOU00112686: 13 pins within 22 minutes; 675 refs cover
1,930 rows) · *interval union across pins; population unioned once, capped at county* ·
*recurring windows as hours not days* · *the completion pin borrows its siblings' window* ·
*a repeating window is a restriction whatever the title*.

**Worked examples.** DON00115765 arithmetic (18 pins, 9–11 Jul); Exton/Wyeville/Zedbury naming
table (lift from #28).

**Diagrams.** 13 dots → one event; 16 solid days vs 18 nightly stripes; Venn of SAs shaded once,
split across two area rows.

**Reading.** `notes/statuspage-methodology.md` "Recurring windows cover hours, not days", "A
scheduled repeating window is a restriction"; `notes/data-quality.md` "Multi-pin events…", "The
notice title is not a reliable severity signal"; `src/uisce/site.py` `daily_windows`,
`event_windows`, `recurring_intervals`, `Region.add`, `event_pop`.

## Ch 10 — For a reader, not an analyst · #32–#36 · 5–6 Aug

**Thesis.** A person wants to know if their town's water has been alright. 1,836-area directory;
220 of 1,830 areas had no history because multi-area events (764) were named once — fixed for
6 KB gzipped; 801 events would have printed a false 0.0 h; Cavan "27/31 clear days" on 6 Aug
when only 6 days had happened; the 2,600-character methodology paragraph → seven sections; the
health marker unbundled from the grade (0.45 pp knock vs 0.003–0.012 pp real harm, ~100×;
Tipperary's three notices invisible); mobile regression at 375 px.

**Concept.** *History lists name an event under every area it reached; accounting charges it
once* — a deliberate asymmetry.  *Health marker beside the grade, not inside it.*

**Reading.** `notes/statuspage-methodology.md` "The health notice was unbundled from the grade";
`notes/frontend-notes.md` (short); `notes/boil-notices.md` skim.

## Ch 11 — Be findable · #37, #38, #39 · 6–8 Aug (light; pair with Ch 10)

**Thesis.** A hash route is not a URL. Indexable pages 2 → 28; static text 73,087 → 383,714
chars; pages reporting analytics 1 → 28; the retraction that #25's `pushState` never could have
worked; comments that duplicated `notes/` trimmed (#39).

**Concept.** *Why a static site with a JS router is invisible to a search engine.*  No diagram.

## Ch 12 — Put a number on what you don't know · #40, #41 · 15–18 Aug

**Thesis.** Omitting an event asserts it lasted no time at all. 204 of 4,473 outage events on a
1-second footprint (200 = the negative-span family, 4 genuinely `not_found`); imputed by category
median (`mains_repair` 7.5 h vs `pump_repair` 43.7 h; `MIN_CATEGORY_N` 15); Kaplan–Meier 13.9 h
vs naive 13.4 h; +2.3–4.4% person-hours/month, four county-months drop a grade; overlap
double-count first 3.6% (per pin — wrong) then 2.0% (per event), left uncorrected; `do_not_drink`
flag wrong on 9 of 19; grade chips failing WCAG (3.35:1 … 1.79:1); radius sensitivity (rank corr
0.93/0.91 at 300 m, 0.90/0.86 at 1 km, yet 48 of 52 county-months change letter); grade
calibration to 78 county-months (cuts at the 97th/76th/33rd/10th percentiles; four definitional
changes cut national person-hours 11.8% and moved exactly one county-month).

**Concepts.** *Imputation vs exclusion* · *censoring* · *overlap double-counting* · *calibrating
thresholds to your own distribution vs importing a regulator's* · *grades are letters about an
assumption (radius)*.

**Diagrams.** Two events over one SA with the overlap hatched; distribution of 78 county-months
with five threshold lines; three concentric circles (300 m / 500 m / 1 km).

**Reading.** `notes/statuspage-methodology.md` "An event with no usable end is charged a typical
span", "Known limitations", "Radius sensitivity", grade calibration; `src/uisce/site.py`
`SpanTable`, `grade`; `src/uisce/eval_overlap.py` `overlap_by_month`.

## Intro and closing (final-pass session)

`00-intro.md`: the question, what this is, how it was built (AI-assisted, named once), how to
read it. `13-closing.md`: what the site says about Leixlip vs the rest of Kildare today; what it
cannot say (start_date is publication, closed_at is a floor, 2.0% overlap, the radius
assumption); the settled-decisions table as a "what we learned" appendix; glossary from the
concept boxes.

## Ch 14 — One design, three sites · #42, #44–#49 · 19–21 Aug (added 21 Aug 2026)

**Thesis.** Three look-alike sites were carrying three copies of one design layer, fixed by hand
and not always. Hover caption instead of tooltips (#44); the layer moves to `statusui`, first
vendored (#45) then, after one day showed the copies five commits apart, a uv git dependency
pinned in `uv.lock` (#48); the 390 px iPhone review (#47: scrolling month strip 1,095 px in
356 px, touch `pointerover`, rhythm 22/6/14/14/18/30/16 → 24/12/12/24/24/24/12/12, health key
shortened then reverted on 42 = 35 + 7 and the word "drink" never occurring); first rollout drops
the status dot (#49). #42 closes the README schema thread.

**Concepts.** *A page assembled at build, not fetched at load* · *vendor or pin* · *hover is not
touch*.  **Worked examples.** Month strip arithmetic and the 851→375 px rotate; the health-key
count.  **Diagram.** Mermaid: statusui → pins → single-file pages.

**Reading.** `sources/ch14.md`; `notes/frontend-notes.md` "2026-08-20: the vendored copy became a
pinned uv git dependency", "Shared with esb and lifts since 2026-08-19", "The iPhone review pass
2026-08-19"; `../statusui/README.md`.

## Ch 15 — Rules first, model second · #46, #50–#52 · 20–21 Aug (added 21 Aug 2026)

**Thesis.** ~93% of the end-time work is template filling. `rules.py` (rules-v1) emits only
`completion_update` / `scheduled_end_with_time`, abstains on everything else; acceptance criteria
fixed before measurement (≥60% coverage / ≥98% agreement / rules-wrong ≤0.3% and ≤ LLM-wrong /
0 wrong emissions); shadow eval 92.7% / 99.99% (10,068 of 10,860), four disagreements adjudicated
(237463 is the LLM's transposition), narrowing only, frozen; fresh 120-case round 120/120 LLM,
110/110 rules at 91.7%; hybrid stamps `model`, staleness keys on it, no backfill; 0.6 s vs ~11
GPU-hours. #51 site deploys on push, banner on the data clock. #52 CI runs `--rules-only`,
commits the JSONL, `merge=union`; uisce-data repo and release asset rejected. #46 footnote.

**Concepts.** *Fix the bar before you measure* · *a rule may abstain but may never guess* ·
*shadow evaluation, then the truth gate* · *the data clock and the build clock* · *two writers,
one append-only file*.  **Worked examples.** KLD00118059 through `rules.extract`; the acceptance
table; the four disagreements.  **Diagrams.** Mermaid: rules→LLM; the CI pair.

**Reading.** `sources/ch15.md`; `notes/rules-vs-llm-end-times.md` whole; `src/uisce/rules.py`
docstring.

## Ch 16 — Stop sounding like the author · #54–#61 · 25–26 Aug (added 26 Aug 2026)

**Thesis.** Ch 10 round two: cold-read as a neighbour, the county page still sounded like its
author. #54–#57 plain-reader copy (Areas paragraph → one line + disclosure; "pin" out of copy;
"Sat 1 Aug" dates via fmtDay/_fmt_day; em-dashes → hyphens; placement rule once; collection date
dropped; footer "Source code · not affiliated"). #58–#60 the sharing rule runs forward: fmtDay/
fmtDate then freshness() promoted on esb becoming the second user (freshness equivalence over
57,721 ages; test_ui_globals forces the move); comment rule written down. #61 esb design
alignment: quality leaves the day bars (server-side, worst short-circuits; quality-only days
count clear, noted; "clear of supply disruption" fix), opacity ramp 1.80/2.93 → solid tokens
2.50/4.56/8.44, severity-word captions (<0.5%/<2%), shared search over search.js (~66 KB),
alphabetical + chevron + card reorder; tests repurposed, 443.

**Concepts.** *Promoted on the second user* · *the bars answer one question*.
**Worked examples.** The date format; the contrast ramp; the self-contradicting clear-days
sentence.  **Diagram.** None — nothing spatial.

**Reading.** `sources/ch16.md`; `notes/frontend-notes.md` design-alignment section.
