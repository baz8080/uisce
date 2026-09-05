# Roadmap

Follow-ups with no other home: work agreed and not started, checks that gate it, decisions
waiting on the owner, and re-measurements with a trigger. Settled decisions live in
CLAUDE.md's table and rejected ideas in the note that rejected them; this file holds neither.
When an entry closes, delete it here and put the outcome where it belongs.

Started 2026-09-05, from the follow-ups the nine PRs of the missing-features survey (#76 to
#84) and the notes left behind.

## Queued

1. **The water.ie deep link, everywhere it belongs.** #80 links each open notice's reference
   on the county pages to `https://wtr.ie/<reference>`, gated by `notice_url` (three letters,
   eight digits, after stripping the trailing space a few references carry). Still to do, once
   #80 to #83 have merged: open entries carry `url` so `incident()` in `site.html` links the
   reference in the county view, the national `#open` view and the day list from #81; the Atom
   entries gain `<link rel="related">`. The notice history and the area pages wait on the check
   below.
2. **Retire the paragraph that asked for the split.** statuspage-methodology.md, "Payload, and
   when to change the shape", still says the per-county file is "deliberately not done yet".
   #82 did it; once it merges, point the paragraph at frontend-notes "The county's own data
   left data.js" instead of re-stating it.
3. **Put the next purge in the Actions summary, not only the log.** `create_db` prints how
   many cases were stamped `vanished_at`. A `::warning::` line when that count is large, say
   over the 1% the download guard already uses, would have shown the 2026-08-10 purge the day
   it happened instead of a month later. A candidate, not agreed.

## Waiting on a check by hand

- **Does an old reference still resolve on wtr.ie?** Try one from May. The feed purged
  everything published before 8 August, and whether water.ie kept the pages decides whether
  closed rows, the notice history and the area pages get the link. The proxy blocks both hosts
  from a session, so this needs a browser.

## Decisions waiting on the owner

- **`IGNORE_BOIL_NOTICES`.** Recommendation is to leave it off (boil-notices.md, re-measured
  2026-09-05): the two accruing notices and the one paired one are the live warnings the health
  marker exists for. The cost of leaving it off is 13 of 17 issue events excluded as stale
  when any of them may be a notice genuinely still standing; the feed cannot say which.
- **"0 counties graded F" over a month with counties in E.** Raised, measured and left on
  2026-08-30 (statuspage-methodology.md, "The scale grew an E"). The one-line fix is to count E
  and F together and say "graded E or F". Listed so it is findable, not to reopen it.

## Re-measure when

- **The E cut at 98.7%**, fitted to a 130-row archive: re-measure against the latest release
  DB as months worse than 98.459% arrive (statuspage-methodology.md).
- **Overlap double-counting**, 2.0% of national outage person-hours on 2026-08-18:
  `uv run uisce-eval-overlap` (statuspage-methodology.md, "Known limitations").
- **Boil-notice pairing**, only if the feed starts publishing the issue and the lift for the
  same schemes (boil-notices.md). Do-not-consume: no case in the release carries either
  `consumption_notice_*` category since the purge, so that pairing runs in tests alone; reopen
  the staleness question if a notice's own text says lifted while `status` stays Open.
- **The index budget.** `data.js` is 212 KB after #82 against the 512 KB `INITIAL_BUDGET`
  for index.html plus data.js, and the months block grows with months × counties. When the
  build's `::warning::` fires, measure what grew before choosing the next cut.
- **A closure series**, if one is ever published from `closed_at`: record the build cadence
  beside the data so the series can be corrected rather than annotated (data-quality.md,
  "`closed_at` is a floor").

## Noted and not taken

- The health mark explains itself only through `title=`, which never fires on touch; it is
  generated markup the tests pin (frontend-notes.md, the iPhone review).
- A settlement that has never had a notice routes to its county from search. Routing it to
  the in-app view would say "nothing was ever published here", but the view needs a name
  shipped for it. Worth doing only if readers turn out to search for quiet towns
  (frontend-notes.md, "Two edges, both left as they are").
- `ul.areas` resets its own padding here; its promotion to statusui is tracked in esb's
  `notes/area-pages.md`.
- The day list (#81) is county-view only, and a recurring event matches every day of its span
  because the shard carries hours and span, not the windows. Both accepted; shipping the
  windows reopens the second (frontend-notes.md, "A day in the county bar lists its notices").
- water-sla-benchmarks.md, "Related metrics worth adopting later": a CAIDI-style time to
  restore (the published median completion is already the analogue) and AWWA breaks per 100
  miles of main once enough located events accumulate.

## Considered in the 2026-09-05 survey and not planned

A sort or ranking control (removed 2026-08-26 for the shared search box); pages for the 1,193
"Around ..." Electoral Divisions; any change to how a published number is computed.
