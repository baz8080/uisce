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
| There is no better start basis in the feed than the publication timestamp. **Do not build the toggle.** | data-quality.md — "Resolved 2026-07-20" |
| The published median is notice → *observed* completion. Scheduled ends accrue disruption time but are excluded from the headline; pooling them dragged 17.0h to 9.3h. | statuspage-methodology.md — "The published time metric" (settled 2026-07-20) |
| Events with no usable end are charged a typical observed span in availability, but stay out of the median. A total has no exclude option; a median does. | statuspage-methodology.md — "An event with no usable end is charged a typical span" (2026-08-15) |
| A notice announcing a *repeating* window is a restriction whatever its title says — the same supply zone is published both ways. | statuspage-methodology.md — "A scheduled repeating window is a restriction" (2026-08-02) |
| Recurring windows are charged as hours inside the windows, not as continuous days. | statuspage-methodology.md — "Recurring windows cover hours, not days" (2026-08-01) |
| The grade chips: **C alone takes dark lettering**, the other five carry white. B and D were dark-inked on 2026-08-18 on WCAG 2 alone, reversed 2026-08-30 once APCA showed dark ink on B at Lc 38.6 against white's 69.2. B is `--fair`, D is `--serious-deep`; no two of the six chips are closer than delta-E 20.2. Colours live in `../statusui`, guarded there by `test_fills_carry_the_lettering_set_on_them`. | frontend-notes.md - "Contrast pass 2026-08-18" and its 2026-08-30 amendment |
| The scale runs A to F inclusive. E splits the old F band at **98.7%**, a cut fitted to the tail: the obvious 98.4 (continuing the 0.15/0.30/0.45 widths) leaves F empty, because the whole F population sits between 98.459 and 98.900. Every A-D cut is unmoved. Re-measure as the archive grows. | statuspage-methodology.md - "The scale grew an E" (2026-08-29) |
| An active boil-water / do-not-drink notice is a marker *beside* the grade, not a knock to it. | statuspage-methodology.md — "The health notice was unbundled from the grade" (2026-08-02) |
| `lifted_immediate` is excluded from site metrics; its duration is NULL, never 0. | end-time-eval.md — "Decision: `lifted_immediate` is excluded" (2026-07-18) |
| Boil-notice pairing is 1 of 17 events and **will not grow with history**: the feed publishes the issue for some schemes and the lift for others, almost never both. `IGNORE_BOIL_NOTICES` stays off for the live warnings' sake. | boil-notices.md - "Re-measured 2026-09-05" |
| Do-not-consume notices get lift pairing but **not** the boil-notice staleness exclusion. A paired lift is capped for what it charges, uncapped for the health marker. | statuspage-methodology.md — "Do-not-consume notices got the pairing, not the exclusion" (2026-08-18) |
| The notice title alone is not a reliable severity signal. | data-quality.md — "The notice title is not a reliable severity signal" (2026-08-02) |
| The `water_outage` feed flag cannot filter anything — it is set on 97% of cases. | data-quality.md — "`water_outage` flag is not a filter" |
| Neither feed health flag is a signal: both dropped from `classify`/`knocks_grade`, which read the category only. Text-gating them instead was measured and rejected. | data-quality.md — "The two health flags are not signals either" (2026-08-18) |
| Duration outliers are categorical, not statistical. The 14-day cap is a backstop, not the outlier strategy. | data-quality.md — "Duration outliers are categorical" |
| "We are investigating" reference pairing works but rescues almost nothing — not worth building. | data-quality.md — "'We are investigating' notices" (corrected 2026-07-20) |
| `closed_at` is a floor: short-lived cases are never observed open. Twice-daily builds are the settled cadence. | data-quality.md — "`closed_at` is a floor" (re-measured 2026-07-31) |
| A case the feed drops while `Open` is stamped `vanished_at` (schema v4) and is closed with no signal on the site, never `closed_at`. The stamp is safe only behind the feed-count guard (`FEED_COUNT_TOLERANCE`), which refuses a short download before anything touches the DB. | data-quality.md - "Cases that vanish from the feed" (2026-09-05) |
| **A case is open only while nothing its own text has ended.** `is_open(row, now)` reads `status`, `vanished_at` and a passed *observed* end, decided once in `resolve_case` and carried on `Case.is_open` for every surface that says open. The feed closes a case a median 72h after the notice reports completion; 216 of 562 `Open` cases were past one, 0 of 7,667 completions were ever followed up. Scheduled ends do not close a case for display. | statuspage-methodology.md - "The notice's own completion closes it" (2026-09-05) |
| gemma-4-12b-qat over qwen3.5-9b for end-time extraction; prompt version is at v3. | model-and-runtime-benchmarks.md, end-time-eval.md |
| Geography is CSO Census settlements, not the feed's `location` string (3,866 distinct values, fragments badly, carries no population). | statuspage-methodology.md — "The county drill-down" (2026-07-25) |
| Overlapping events double-count person-hours by **2.0%** nationally, left uncorrected. Re-measure with `uv run uisce-eval-overlap`. | statuspage-methodology.md — "Known limitations" (2026-08-18) |
| Quality notices do not colour the day bars — removed server-side so a quality+restriction day falls through to the restriction; the healthmark, county tiles and county pages carry them. The bars' intensity ramp is solid severity tokens, not opacity (measured contrast in the note). Sort control removed for the shared search box. | frontend-notes.md — "The design alignment pass" (2026-08-26) |
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
| CI runs `uisce-infer --rules-only` every data build and commits the JSONL to `main`; the LLM residue is run by hand. JSONL stays in this repo (`merge=union`) — a `uisce-data` repo and a release asset were both rejected. | rules-vs-llm-end-times.md — "CI runs the rules half" (2026-08-21) |
| The fourteen towns named for their county (Carlow, Sligo, Wexford ...) render one row under the county's, `Sligo` + `town`, reachable from the box. The index always carried them; the `name|county` dedup that hid them was fixed upstream in statusui and the pin moved in the same PR | frontend-notes.md - "Two edges, both left as they are", 2026-09-03 amendment |

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
- Comments earn their place or they go. Say **why**, not what — never a paraphrase of the line
  below, a heading for an obviously-named block, or an explanation of a standard flag. One line
  where one will do; a paragraph of reasoning belongs in the commit message or `notes/`.
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
