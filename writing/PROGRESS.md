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
| 03 | Ask a local model what the notice actually says | #8–13 | todo | |
| 04 | Make it a real project | #14–15 | todo | |
| 05 | A website, and an honest number on the model | #16–17 | todo | |
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

## Open threads

- README says `SCHEMA_VERSION` "currently 2"; code says 3 — separate fix, not for the series.
- Oldest `start_date` in the DB is `0206-08-10` (mis-typed year in the feed) — a possible
  footnote in Ch 1 or Ch 6 about trusting feed dates.
- PR #23's Kildare table shows Naas at 25,824; the corrected settlement figure is 26,180. When
  quoting the table say "as published in PR #23" and note the correction once.

## Next session

**Ch 3** (+ Ch 4 if the window allows). Read: this file → `README.md` → `outline.md` Ch 3–4 →
`sources/ch03.md` (~1.7k words), `sources/ch04.md` → `notes/end-time-eval.md` intro and
"Decision: `lifted_immediate` is excluded" → `notes/model-and-runtime-benchmarks.md` (whole,
short). For the worked example reuse KLD00118059 from Ch 1: pull its `inferred_cases` row
(`end_source`, inferred end, `notice_to_end_seconds`) and, if cheap, the prompt text from
`src/uisce/inference.py`. Continuity: Ch 1 promised that "getting the end out of the prose is
chapter 3"; Ch 2 ended on the same line. Register figures. Update this file. Commit per chapter.

## Session log

- 2026-08-18 · Session 1 · drafted Ch 1 (1,934 w) and Ch 2 (1,034 w); measured 10,610 cases /
  10,550 distinct rounded coords; KLD00118059 pulled as the running example.
- 2026-08-18 · Session 0 · scaffold: README (style guide), outline, figures registry with anchors
  verified, source pack built (12 files, 34.7k words) via `tools/build_sources.sh`.
