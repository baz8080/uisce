# 4. Make it a real project
*~6 min read · PRs #14–#15 · 10–11 July 2026*

*Where we are:* three scripts in the root of a folder — one fetches, one runs the model, one
builds a table — held together by the order I ran them in. They worked. This chapter is the
short, unglamorous stretch where they became software: a package, a test suite, and a first
attempt at reading the *kind* of work from a notice's title.

## The question that opened this stretch

By 9 July the pipeline had enough moving parts to break in ways I could not see: the feed paged
its results in an unstable order, a geocoding hiccup could crash a whole build, the model call
sometimes hung. And I was about to build a website on top of it. Before adding a consumer, the
producer needed to be something I could change without fear — which, in practice, means tests.

## What changed

### PR #14, 10 July: a package, tests, and hardening

The three root scripts moved into a proper Python package, `src/uisce/`, and became three named
commands — `uisce-pipeline`, `uisce-infer`, `uisce-build-inferred` — that the weekly build and
the README both call. Alongside them, a **42-test suite** that runs with no network: field
mapping and normalisation, ArcGIS paging, geocode caching and failure handling, the Dublin
daylight-saving arithmetic from chapter 3, hash-based skipping, and the `work_type` backfill
below. The CI stopped merely checking that the code compiles and started checking that it does
what the tests say.

> **Concept: what a test suite buys.** A test is a small, permanent statement of what a piece of
> code must do, run automatically on every change: *given a start of 21:16 UTC and a local end of
> 13:00 IST the next day, the duration is 52,987 seconds.* Individually they are trivial. Together
> they are a written contract, and they change what a change *costs*: with them, a refactor that
> breaks a rule fails within seconds on the machine; without them it fails weeks later, on the
> website, in a number a reader trusted. The later chapters make many changes to how numbers are
> computed. The reason those were survivable is that from here on the tests said, immediately,
> what each change did — and the "guard" tests, which fail on purpose when an output's shape
> changes, are how a payload key cannot be added by accident.

The hardening was the sort of thing you only add after being bitten. Web requests retry with
backoff on transient failures. The feed is paged with an explicit sort (`orderByFields=OBJECTID`)
so a case cannot fall between two pages. A geocode failure writes a **placeholder row** to be
retried next run rather than crashing the load; ten consecutive failures trip a circuit breaker
and fail the build cleanly, on the reasoning that the service is down, not the coordinate wrong.
An empty string from the feed becomes NULL. And on the model side, identical descriptions —
which, since one notice can be several pins (chapter 1), are common — are read **once per run**,
about 15% fewer calls; and the timeout went from 15 s to 120 s so a slow answer is waited for
rather than counted as a failure.

### PR #15, 11 July: what kind of work is this?

Every title has the same shape: *Category – County*. `Burst Water Main - Kildare`. `Essential
Works - Cork`. `Investigation Works - Kildare`. Messy in the details — a hyphen here, an en-dash
there, `Main` and `Mains`, stray spaces — but a small, closed vocabulary. PR #15 turned it into a
column, `work_category`, by normalising the category part into a stable slug: `burst_main`,
`essential_works`, `investigation`, twenty-six slugs in all as of July.

The same rule table does one more thing. The feed carries a `work_type` field — *Planned* or
*Unplanned* — but fills it in on only about **31%** of cases. For many categories the title
answers the question by itself: a burst main is never planned; a new connection or a valve
installation always is. Where a category's feed labels were at least 95% one-sided over at least
20 labelled cases, the rule *sets* `work_type` — overriding the feed, since the stray
contradictions were typically the completion update at the end of a planned job, mislabelled.
Where the title genuinely spans both — `mains_repair`, `power_outage` — the rule attaches a slug
and leaves `work_type` exactly as the feed said. Coverage went from 31% to **89%**, and only 29
cases had a title so one-off that no rule matched.

### Worked example: three titles

| Title as published | `work_category` | `work_type` | Why |
|---|---|---|---|
| `Burst Water Main - Kildare` / `Burst Water Mains - Kerry` | `burst_main` | Unplanned (set by rule) | a burst is never scheduled; hyphen and plural variants normalise to one slug |
| `Investigation Works - Kildare` (KLD00118059, chapters 1 and 3) | `investigation` | Unplanned (set by rule) | "we are investigating reports of…" is by nature reactive |
| `Mains Repair - Cork` | `mains_repair` | left as the feed says | repairs are scheduled about as often as not; the title cannot decide |

On today's database (18 Aug 2026) the largest categories are `burst_main` (3,332 cases, all
Unplanned), `essential_works` (1,376, Planned), `mains_repair` (1,272 across both and blank),
`investigation` (671) and `reservoir_interruption` (620); `work_type` is now filled on 90.4% of
cases and only 16 have no category at all.

> **Concept: a title is a category, not a severity.** It is tempting to read the slug as "how
> bad": *burst main* sounds like no water, *essential works* like a bit of pressure. Resist it.
> The category says what the crew is doing, not what the household experiences — the same supply
> zone can be published as a "Water Conservation" notice one week and a "Supply Interruption" the
> next for the same nightly shut-off. That is a chapter 9 story with a large number attached; for
> now the point is that `work_category` is a clean, useful *label*, and nothing more is claimed
> for it.

Two conveniences came in the same PR and were used constantly afterwards: `uisce-pipeline
--skip-geocode`, to refresh cases without spending a geocoding call, and `uisce-backfill`, to
re-derive the computed columns on an existing database with no network — so a change to the rule
table can be tried against real data in seconds. And because the published database is
downloaded and updated *in place* each build (chapter 2), the new column had to be added with an
`ALTER TABLE` that is safe to run twice. That is the seed of the migration discipline chapter 7
makes explicit.

## Where it left the site

Not yet a site, but a codebase: a package with named commands, 56 tests by the end of PR #15, a
pipeline that survives a flaky network, and — for the first time — a column that says what each
notice is *about*, filled on nine cases in ten. A week later (chapter 5) the first web page was
built on it, and the first thing that page needed was a way to say how many *people* a notice
affected. That is where the Census comes in.

## Notes

- PR #14 (10 Jul 2026): `src/uisce/` package and entry points; 42 tests; retry adapter;
  `orderByFields=OBJECTID`; placeholder geocode rows and a 10-failure circuit breaker; `''` → NULL;
  description dedupe ≈ 15% fewer model calls; timeout 15 s → 120 s; `work_type` 31% → 68%.
- PR #15 (11 Jul): `work_category` via `CATEGORY_RULES` (26 slugs); `work_type` set where a
  category's feed labels are ≥ 95% one-sided over ≥ 20 cases; 31% → 89%, 29 uncategorised;
  `--skip-geocode`, `uisce-backfill`; 56 tests.
- Today's counts (measured 18 Aug 2026 against `out/uisce.db`): `burst_main` 3,332,
  `essential_works` 1,376, `mains_repair` 1,272 (828 blank + 269 Unplanned + 175 Planned),
  `investigation` 671, `reservoir_interruption` 620; `work_type` filled 90.4%; 16 cases with no
  category.
- "The notice title is not a reliable severity signal": `notes/data-quality.md` (2 Aug 2026),
  taken up in chapter 9.
