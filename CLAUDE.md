# uisce

A static status site for Uisce Éireann water disruption notices, built from an ArcGIS feed.
`notes/` carries ~33k tokens of measured findings and settled decisions across 11 files — too much
to read wholesale, which is why the important ones are indexed here.

## The UI is shared — change it upstream

The tokens, base CSS, row/bar/card components and the JS helpers that uisce, esb and lifts
all use come from [`../statusui`](https://github.com/baz8080/statusui), a **uv git dependency
pinned in `uv.lock`** and inlined into every page at build by `statusui.assemble()`. Edit it
there, push, then `../statusui/rollout.sh` bumps the pin in all three sites and opens the
PRs; to try an unpushed change here, `uv run --with-editable ../statusui uisce-site`. This
site's own rules are `src/uisce/site.css` and the inline blocks in the three templates; the
shared/per-site rule is in statusui's CLAUDE.md.

## Before you change how any published number is computed

Read the relevant section of [notes/data-quality.md](notes/data-quality.md) and
[notes/statuspage-methodology.md](notes/statuspage-methodology.md) **first**. Most of the obvious
improvements to this codebase have already been measured and rejected, with the numbers written
down. Re-deriving one costs a session; shipping one costs the site's credibility.

## Settled — don't re-litigate without reading the linked section

Each of these was measured and closed on the date given. They can be reopened, but only by engaging
with the evidence that closed them.

| Decision | Where |
|---|---|
| `start_date` is re-stamped in place by the feed. Two rescue routes measured and closed; **taking the minimum recorded start is explicitly rejected** (backward re-stamps would inflate durations). Negative spans stay NULL. | data-quality.md — "Measured 2026-07-20: ends preceding publication are 532 cases" |
| A `start_date` before 2000 is a feed typo, refused by `plausible_start` wherever a start is read: no span is measured from it, the site dates the notice from `first_seen`, the rules lend no year from it. A bound relative to `first_seen` and a guard at ingest were measured and rejected. | data-quality.md - "A start typed into the wrong millennium" (2026-10-04) |
| There is no better start basis in the feed than the publication timestamp. **Do not build the toggle.** | data-quality.md — "Resolved 2026-07-20" |
| The published median is notice → *observed* completion. Scheduled ends accrue disruption time but are excluded from the headline; pooling them dragged 17.0h to 9.3h. | statuspage-methodology.md — "The published time metric" (settled 2026-07-20) |
| The population estimate is gone from the code: no 500 m circle, imputed span, person-hours or availability. A pin is placed in the area of its **nearest Small Area centroid** within `PLACE_KM`, unplaced when that lies in another county; an event is named for the area most of its pins are in. The nearest *area* centroid (5 pages lost) and the nearest in-county Small Area (re-homes border pins) were measured and rejected. A notice with no usable end is a one-second token, counted in `no_end_n` and in no duration. | statuspage-methodology.md - "The estimate is removed" (2026-10-06) |
| A notice announcing a *repeating* window is a restriction whatever its title says — the same supply zone is published both ways. | statuspage-methodology.md — "A scheduled repeating window is a restriction" (2026-08-02) |
| Recurring windows are charged as hours inside the windows, not as continuous days. | statuspage-methodology.md — "Recurring windows cover hours, not days" (2026-08-01) |
| Only a window `_read_window` can honour stands in `event_windows`' vote - one refused wherever it is read must not beat a sibling's usable one, and the vote and the refusal read it through the same function so they cannot drift. The event **key** survives with a `None` value: it is also the recurrence signal, and dropping it would downgrade a nightly restriction to an outage. | data-quality.md - "A pin can report half a window" (2026-09-13) |
| The grade chips: **C alone takes dark lettering**, the other five carry white. B and D were dark-inked on 2026-08-18 on WCAG 2 alone, reversed 2026-08-30 once APCA showed dark ink on B at Lc 38.6 against white's 69.2. B is `--fair`, D is `--serious-deep`; no two of the six chips are closer than delta-E 20.2. Colours live in `../statusui`, guarded there by `test_fills_carry_the_lettering_set_on_them`. | frontend-notes.md - "Contrast pass 2026-08-18" and its 2026-08-30 amendment |
| An active boil-water / do-not-drink notice is a marker *beside* the grade, not a knock to it. | statuspage-methodology.md — "The health notice was unbundled from the grade" (2026-08-02) |
| `lifted_immediate` lift records are excluded from site metrics (by category); its duration is NULL, never 0. A notice whose own text was overwritten with lift wording keeps its event. | end-time-eval.md - "Decision: `lifted_immediate` is excluded" (2026-07-18) |
| Boil-notice pairing is 1 of 17 events and **will not grow with history**: the feed publishes the issue for some schemes and the lift for others, almost never both. `IGNORE_BOIL_NOTICES` stays off for the live warnings' sake. | boil-notices.md - "Re-measured 2026-09-05" |
| Do-not-consume notices get lift pairing but **not** the boil-notice staleness exclusion. A paired lift is capped for what it charges, uncapped for the health marker, and closes the notice for display. Unlifted, the notice closes at 14 days, marker and open status together (owner, 2026-09-24). | statuspage-methodology.md - "Do-not-consume notices got the pairing, not the exclusion" (2026-08-18, amended 2026-09-24) |
| The notice title alone is not a reliable severity signal. | data-quality.md — "The notice title is not a reliable severity signal" (2026-08-02) |
| The `water_outage` feed flag cannot filter anything — it is set on 97% of cases. | data-quality.md — "`water_outage` flag is not a filter" |
| Neither feed health flag is a signal: both dropped from `classify`/`knocks_grade`, which read the category only. Text-gating them instead was measured and rejected. | data-quality.md — "The two health flags are not signals either" (2026-08-18) |
| Duration outliers are categorical, not statistical. The 14-day cap is a backstop, not the outlier strategy. | data-quality.md — "Duration outliers are categorical" |
| "We are investigating" reference pairing works but rescues almost nothing — not worth building. | data-quality.md — "'We are investigating' notices" (corrected 2026-07-20) |
| `closed_at` is a floor: short-lived cases are never observed open. Twice-daily builds are the settled cadence. | data-quality.md — "`closed_at` is a floor" (re-measured 2026-07-31) |
| The `replay_closed_at` dispatch input is gone: a dry run over all 75 releases found 0 values to stamp or change. The script stays for a DB restored from an older release, run by hand. | data-quality.md - "The replay has nothing left to recover" (2026-09-24) |
| Every data build publishes its **own release**, tagged `YYYY-MM-DD-HHMM` (UTC); `scripts/publish-db.sh` and `scripts/fetch-db.sh` are the only publish and download. Replacing the asset in a per-day release was rejected: `--clobber` deletes first, and a rename swap stranded releases in three ways. | data-quality.md - "One release per build" (2026-09-24) |
| A case the feed drops while `Open` is stamped `vanished_at` (schema v4) and is closed with no signal on the site, never `closed_at`; the stamp touches closed rows too. It is safe only behind the feed-count guard (`FEED_COUNT_TOLERANCE`), which refuses a short download before anything touches the DB, and behind the empty-download refusal. Paging is by `OBJECTID`, refused unless each page is strictly ascending. | data-quality.md - "Cases that vanish from the feed" (2026-09-05, amended 2026-09-24) |
| A feature with no pin (no `geometry`, or `"NaN"`) keeps the pin the DB last stored, or is set aside with a `::warning::` until the feed pins it. Nullable coordinates were rejected: not an additive migration. | data-quality.md - "A feature with no pin" (2026-09-24) |
| **A case is open only while nothing its own text has ended.** `is_open(row, now)` reads `status`, `vanished_at` and a passed *observed* end, decided once in `resolve_case` and carried on `Case.is_open` for every surface that says open. The close date follows the same reading: the notice's own completion, else `closed_at` (`closed_on`, 2026-09-24). The feed closes a case a median 72h after the notice reports completion; 216 of 562 `Open` cases were past one, 0 of 7,667 completions were ever followed up. Scheduled ends do not close a case for display. | statuspage-methodology.md - "The notice's own completion closes it" (2026-09-05) |
| gemma-4-12b-qat over qwen3.5-9b for end-time extraction; prompt version is at v3. | model-and-runtime-benchmarks.md, end-time-eval.md |
| Geography is CSO Census settlements, not the feed's `location` string (3,866 distinct values, fragments badly, carries no population). | statuspage-methodology.md — "The county drill-down" (2026-07-25) |
| Quality notices do not colour the day bars: removed server-side so a quality+restriction day falls through to the restriction; the healthmark, county tiles and county pages carry them. The bars use solid severity tokens, not opacity (measured contrast in the note); since 2026-10-06 an outage day takes one shade and a cell is `[severity]`, the population share gone; a ramp on a count was rejected. Sort control removed for the shared search box. | frontend-notes.md - "The design alignment pass" (2026-08-26) |
| 739 areas that name a place get a page at `a/<county>/<area>.html`; the 1,193 "Around …" Electoral Divisions, the 5 city `-rest` buckets and the unplaced ones do not, and there is deliberately **no notice-count floor** — a permalink that comes and goes is worse than a short one. The slug ships in the payload because `ui.js`'s `slug()` is not `statusui.slug()` and would 404 on 20 place names. | frontend-notes.md — "The area pages" (2026-08-26) |
| The county-page link sits under the county heading, not in the footer, and the overview row's `href` points at `c/<county>.html` rather than the hash. Wording is the same sentence esb uses, because the two pages stand in the same relation to their views; it is deliberately not "every notice ever recorded" — not because the page is short (the cap came off 2026-08-27) but because the *view* is one month at a time. lifts' names the address instead, because its page is the same content as its view. The area view's link names the address ("Permanent link to Abbeydorney") because its page is the same content as the view. | frontend-notes.md — "The county-page link came up out of the footer" (2026-08-26) |
| A search hit is an entry point, so it is a real link: an area hit goes to `a/<county>/<area>.html`, a county hit carries `c/<county>.html` in its `href` but keeps the click in the app. The `#area` view stays — it is the only surface the 1,221 pageless areas have — and the towns rows got the same href treatment. The index gate is the payload's `slug`, not `area_has_page` (904 eligible, 739 built) | frontend-notes.md — "Search reaches the area, not just its county" (2026-08-27) |
| The county page's meta description states the county's record, then names what the page holds, in that order — a snippet truncated mid-sentence must not read as an inventory | frontend-notes.md — "The county page's meta description had the same shape" (2026-08-26) |
| The county page lists **every** notice; `COUNTY_EVENTS_SHOWN`/`COUNTY_OPEN_SHOWN` are gone. A count was always a proxy for bytes and a bad one — if a bound is needed again, make it a byte budget. Measured 2026-09-05 on the 2026-09-04 release: Dublin 384 KB, Cork 336 KB, with the open notices' text; no byte budget yet. | frontend-notes.md — "The copy and consistency pass" (2026-08-27) |
| One name per thing: the directory is "every area with a notice" (never "in Ireland" — that was false), the app is "Co. X's interactive view" (never a map), a count reads `· N notices`, and every footer says "Source code · not affiliated with Uisce Éireann." | frontend-notes.md — "One name per thing" (2026-08-27) |
| `base.css` resets margin, not padding, so a bare `<ul>` keeps the UA's 40px indent — `ul.notices`/`ul.areas` reset their own. Kept per-site, not promoted. | frontend-notes.md — "The 40px that nothing asked for" (2026-08-27) |
| The design layer (tokens, base CSS, row/bar/card, JS helpers) is shared with esb and lifts via `../statusui`, a **uv git dependency pinned in `uv.lock`** — edit upstream, then `../statusui/rollout.sh` bumps all three sites. Vendored copies were tried first and drifted within a day. `site.css` and the inline blocks are this site's own. | frontend-notes.md — "the vendored copy became a pinned uv git dependency" (2026-08-20); statusui's README for what is shared |
| End-time extraction is **rules first, LLM fallback**: `rules.py` answers the templated ~93% (99.99% corpus agreement, 0 wrong emissions on the labelled rounds, 0.6s vs ~11 GPU-hours) and abstains to the LLM for recurring windows, lifts, Irish and everything ambiguous. Rules may only emit `completion_update`/`scheduled_end_with_time`; re-measure with `uv run uisce-eval-rules-shadow`. | rules-vs-llm-end-times.md (2026-08-21) |
| `towns` and `resolved` are the county view's data and ship per county in `t/<county>.js`; `data.js` carries months, open and top only (212 KB against 955 KB). `INITIAL_BUDGET` is 512 KB for index.html plus data.js, **warned, never failed**. Folding the breakdown into the history shard was rejected. | frontend-notes.md - "The county's own data left data.js" (2026-09-05) |
| rules-v2: "until midnight on D" after a start earlier on D ends at D+1 00:00, after a start the day before at D 00:00 only for a literal "12am on D", and otherwise the rules abstain. An `until` in a sentence about an alternative supply makes the rules abstain. An English completion below an Irish one of the same day is read; Irish alone still abstains. The LLM prompt still reads midnight as the start of D (issue #102). | rules-vs-llm-end-times.md - "rules-v2" (2026-09-24) |
| CI runs `uisce-infer --rules-only` every data build and commits the JSONL to `main`; the LLM residue is run by hand. JSONL stays in this repo (`merge=union`) — a `uisce-data` repo and a release asset were both rejected. | rules-vs-llm-end-times.md — "CI runs the rules half" (2026-08-21) |
| The fourteen towns named for their county (Carlow, Sligo, Wexford ...) render one row under the county's, `Sligo` + `town`, reachable from the box. The index always carried them; the `name|county` dedup that hid them was fixed upstream in statusui and the pin moved in the same PR | frontend-notes.md - "Two edges, both left as they are", 2026-09-03 amendment |
| The index paints only its header until its first render has run: `<!--UI-WAIT-->` in the head, `data-wait` on `#overview` and the footer, released by `render()` and held while the open area or county view's own shard loads. `data.js` stays a trailing script; moving it, preloading it and reserving heights were measured and rejected | frontend-notes.md - "The first paint waits for the data" (2026-10-02) |
| `ul.notices > li` and `section[data-county]` skip layout and paint while off screen (`content-visibility: auto`), sized by content-box estimates and a per-section row count; `ul.areas li` is **not** given it (a multi-column list, 0.162 on an anchor jump), and the focus-ring clip margin stays, so all of it sits inside `@supports` for that margin (not Safari) | frontend-notes.md - "Long static lists skip what is off screen" (2026-10-02) |
| `index.html` inlines the first overview's data (`first_render_payload`: the newest month of every county, 18.4 KB raw / 1.8 KB gz) and `data.js`, still the complete payload, loads after the first render; the county and open views, and the overview on an older month, wait for it behind a `#waitview` note; a late or newer `data.js` is adopted, an older one is not. A rest-only `data.js` and a preload of it were measured and rejected | frontend-notes.md - "The first render's data is inline" (2026-10-02) |
| Each county-month carries **outage notices per 100 km of main** and its letter: events whose worst pin is an outage, by the feed's county and earliest publication, over `wsz.county_mains_km`. Cuts are **fixed whole numbers, A below 1 to F at 5**, re-fitted yearly; archive quantiles were rejected. Only a month seen whole is lettered; "now" is the rolling `last_30` letter, not a part-month pace. | statuspage-methodology.md - "Outage notices per 100 km of main" (2026-10-06) |
| The page shows outage notices per 100 km of main, its letter and the median, and nothing from the population estimate: no availability, person-hours, people affected or radius, guarded by `TestThePagesSayTheCount`. The newest month reads `last_30`. `#top` is the ten **longest**: the events the month's observed median is taken over, at its hours, a span at the cap reading "14 days+"; person-hours, open notices, scheduled ends, uncapped spans and pin count were rejected (statuspage-methodology.md - "The estimate is removed"). An open notice prints the end it states as "expected back by". | frontend-notes.md - "The page counts notices" (2026-10-06) |

## Conventions

- **A signal trusted for the arithmetic is trusted for the display.** The site's own extracted
  end outranks the feed's `status` wherever the accrual already reads it; a badge, list, count or
  feed entry that reads `status` alone where the extraction contradicts it is a bug to fix, not a
  trade-off to record. Deferring one to the owner means measuring both sides first - how many
  cases the display gets wrong today, and how often the signal would get it wrong - and writing
  the numbers into the entry. The `is_open` row above is what an unmeasured deferral cost.
- Decisions go in `notes/`, dated, with the rejected alternatives and their numbers. Add a row here
  when one closes something off — this file carries pointers only, never the rationale, or it
  becomes the thing it exists to fix.
- Follow-ups go in [notes/roadmap.md](notes/roadmap.md): work agreed and not started, checks
  that gate it, decisions waiting on the owner, re-measurements with a trigger. Delete the entry
  when it closes and put the outcome where it belongs.
- **Comment sparingly.** Say **why**, not what - never a paraphrase of the line below, a heading
  for an obviously-named block, or an explanation of a standard flag, and never restate a settled
  decision at each site that follows it: state it once, in `notes/` or the PR, and let the code
  stand. A comment earns its place only when it records something the reader cannot see: the
  feed's behaviour, a measurement, or a trap that would otherwise be refactored away - a
  re-stamped `start_date` or a `status` the extraction outranks is what that looks like in code.
  One line where one will do; a paragraph of reasoning belongs in the commit message or `notes/`.
  No docstring on a test whose name already says what it asserts.
- `uv run ruff check` and `uv run pytest` before anything ships, in that order — it is the order
  CI runs them in, and ruff failing first means the suite never runs there at all. The payload-shape tests in `tests/test_site.py` are guards:
  when one fails because a key was added, that is the guard working.
- The `cases` schema is declared once, as `CASE_COLUMNS` in `pipeline.py`. `create_db`,
  `DB_CASE_COLUMNS`, the `V1`/`REQUIRED` migration sets and the test fixtures all derive from it.
  Adding a column is one entry there plus a `MIGRATIONS` step and a `SCHEMA_VERSION` bump;
  `TestSchemaIsDeclaredOnce` fails if a second statement of the schema reappears.
- Migrations are additive nullable columns only; anything that rewrites data is a rebuild, and a
  rebuild costs the accumulated archive.

## Punctuation

**No em dashes.** Not in the site's prose, the code comments, `notes/`, commit messages, PR
bodies, issue bodies or the replies in a session. The house dash is a spaced hyphen - like this
one. Where a sentence reads better without one, write it out: "which is", "because", a colon, or
two sentences. En dashes go the same way outside a numeric range.

This binds new prose, and only prose. It is not a licence for a bulk rewrite: as of 2026-08-29
this repo carries 905 em dashes and 335 en dashes across 45 files. Many of them are in
`data/eval/*.csv`, which is recorded data and is **never** re-punctuated: fixing a character in a
sample changes what was sampled. Fix the rest on lines you are already editing.

## Commands

```bash
uv run uisce-pipeline        # download the feed into out/uisce.db
uv run uisce-infer           # end-time extraction: rules first, LLM fallback; CI runs
                             # --rules-only every build, the residue needs LM Studio
uv run uisce-build-inferred  # rebuild inferred_cases from the JSONL
uv run uisce-site            # build out/site/
uv run pytest
```
