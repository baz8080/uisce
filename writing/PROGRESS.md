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
| 05a | A website, and a number that is fair to Cork | #16 | drafted | 1,930 |
| 05b | An honest number on the model | #16–17 | drafted | 1,900 |
| 06 | Say what you actually measured | #18–20 | todo | |
| 07 | Record the moment a case closes | #21–22 | todo | |
| 08a | How a pin gets a population | #23 | todo | |
| 08b | Where you actually live | #23–25 | todo | |
| 09 | Not everything is an outage | #26–31 | todo | |
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

## Open threads

- README says `SCHEMA_VERSION` "currently 2"; code says 3 — separate fix, not for the series.
- Oldest `start_date` in the DB is `0206-08-10` (mis-typed year in the feed) — a possible
  footnote in Ch 1 or Ch 6 about trusting feed dates.
- PR #23's Kildare table shows Naas at 25,824; the corrected settlement figure is 26,180. When
  quoting the table say "as published in PR #23" and note the correction once.

## Next session

**Ch 6** (PRs #18–#20: rename to notice_to_end, observed 17.0 h vs scheduled 5.4 h vs pooled
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

- 2026-08-18 · Session 3 · drafted Ch 5a (1,930 w) and 5b (1,900 w) — Ch 5 split as the length
  rule intends; first SVG diagram.
- 2026-08-18 · Session 2 · drafted Ch 3 (2,231 w) and Ch 4 (1,296 w); pulled prompt v1/v2 diffs
  and KLD00118059's inferred row; category counts measured.
- 2026-08-18 · Session 1 · drafted Ch 1 (1,934 w) and Ch 2 (1,034 w); measured 10,610 cases /
  10,550 distinct rounded coords; KLD00118059 pulled as the running example.
- 2026-08-18 · Session 0 · scaffold: README (style guide), outline, figures registry with anchors
  verified, source pack built (12 files, 34.7k words) via `tools/build_sources.sh`.
