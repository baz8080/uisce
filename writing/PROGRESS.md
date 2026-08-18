# Progress ledger

Read this first each session. Keep it under ~1k tokens: status per chapter, a 3-line summary of
each drafted chapter (so the next session has continuity without re-reading it), open threads,
and the brief for the next session.

Statuses: `todo` → `drafted` → `reviewed` (continuity pass done by a later session) → `final`.

| Ch | Title | PRs | Status | Words |
|---|---|---|---|---|
| 00 | Intro | — | todo (final pass) | |
| 01 | A notice is a row | pre, #1–4 | todo | |
| 02 | Let a robot do it every week | #5–6 | todo | |
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

_(none yet)_

## Open threads

- README says `SCHEMA_VERSION` "currently 2"; code says 3 — separate fix, not for the series.
- Oldest `start_date` in the DB is `0206-08-10` (mis-typed year in the feed) — a possible
  footnote in Ch 1 or Ch 6 about trusting feed dates.
- PR #23's Kildare table shows Naas at 25,824; the corrected settlement figure is 26,180. When
  quoting the table say "as published in PR #23" and note the correction once.

## Next session

**Ch 1 + Ch 2** (light pair). Read: this file → `README.md` → `outline.md` Ch 1–2 →
`sources/ch01.md`, `sources/ch02.md` → `notes/how-it-works.md` "The shape of it" →
`notes/data-quality.md` "The feed carries no modification timestamp". Pull one real Kildare case
row for the worked example (`sqlite3 -readonly out/uisce.db`). Draft `chapters/01-…md` and
`chapters/02-…md`; open Ch 1 with the Leixlip motivation. Register any new figures. Update this
file.

## Session log

- 2026-08-18 · Session 0 · scaffold: README (style guide), outline, figures registry with anchors
  verified, source pack built (12 files, 34.7k words) via `tools/build_sources.sh`.
