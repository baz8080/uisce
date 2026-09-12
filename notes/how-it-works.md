# How it works

A map of the moving parts, for picking the project back up after a while away. **Structure only** — every measurement and every *why* lives in the other notes, linked from here. If a number appears in this file, it is wrong; go and read the note.

## The shape of it

Three artifacts, each rebuilt by a different command, none derived from the other two on demand:

```
ArcGIS feed ──uisce-pipeline──▶ out/uisce.db ──uisce-site──▶ out/site/
                                    │  ▲
                        uisce-infer │  │ uisce-build-inferred
                                    ▼  │
                    data/inferred_end_times.jsonl
```

- **`out/uisce.db`** — the archive. The feed serves only current notices and keeps no history, so the DB is the only record that a case ever existed. Never rebuild it casually: a rebuild costs every case the feed has dropped, plus the geocode cache.
- **`data/inferred_end_times.jsonl`** — committed, append-only, the cache for LLM end-time extraction. It is the source of truth for what has been inferred; the `inferred_cases` table is a rebuilt projection of it. Querying the table to decide what needs inference is the classic mistake — see [pipeline-dependencies.md](pipeline-dependencies.md).
- **`out/site/`** — fully static, regenerated from scratch every time, safe to delete.

Two committed lookups sit outside the loop, refreshed only when the CSO revises its geography: `data/sa_pop.csv` and `data/sa_towns.csv`.

## Flow 1 — getting cases in (`pipeline.py`, `uisce-pipeline`)

1. `download_cases` pulls every notice from the ArcGIS feature server.
2. `map_cases` flattens attributes, converts epoch-ms timestamps, and derives the computed columns: `classify_category` turns a title into a `work_category` slug via the `CategoryRule` table, which also overrides `work_type` where the title is unambiguous (a burst main is never planned).
3. `geocode_all` reverse-geocodes each *rounded* coordinate through LocationIQ, caching in `geocode_cache`. Rounding is what keeps this affordable; `--skip-geocode` writes placeholder rows for a network-free refresh.
4. `load_cases` upserts into `cases` and stamps `closed_at` the first time a build observes a case stop being `Open`.

`create_db` declares the schema once and stamps `SCHEMA_VERSION` into `PRAGMA user_version`; `check_schema_version` runs every build and carries older DBs forward through `MIGRATIONS`. Migration is deliberately narrow — additive nullable columns only — and a DB missing a v1 column is refused rather than repaired.

`uisce-backfill` re-derives the computed columns in place with no network, for when the category rules change.

## Flow 2 — end times (`inference.py` → `build.py`)

`uisce-infer` reads each case description and extracts the end-time signal — CPU rules first (`rules.py`, the templated ~93%, see [rules-vs-llm-end-times.md](rules-vs-llm-end-times.md)), asking a local LLM only for the cases the rules abstain on. It decides its own work by comparing each case's description hash, prompt version and extractor against the JSONL, so it is idempotent and only reprocesses changed text; bumping `RULES_VERSION` re-runs just the rules-produced cases. CI runs it with `--rules-only` on every data build and commits the JSONL; the fallback needs a local model, so the residue is run by hand.

`uisce-build-inferred` rebuilds the `inferred_cases` table from the JSONL, computing `notice_to_end_seconds` per case. It refuses to run if the JSONL references cases the local DB does not have, and prints the never-inferred backlog on every build.

The distinction that matters downstream: `end_source` separates an **observed** completion from a **scheduled** one. See [statuspage-methodology.md](statuspage-methodology.md).

## Flow 3 — the site (`site.py`, `uisce-site`)

The only genuinely intricate part. It runs in four stages:

**a. Each case becomes an interval.** `resolve_case` maps one row to a `Case`: a severity class from `classify`, and a start/end pair. All the awkward rules live here — boil notices routed through `boil_notice_fate`, open cases accruing to now under a cap, no-signal cases getting a token one-second footprint. It is deliberately pure, because it is the same answer regardless of who is counting.

**b. Cases accumulate into regions.** A `Region` is interval-and-population accounting for one grouping. A county and an area within it are the *same object* differing only in the population attributed to each event — the county gets a pin's whole 500 m footprint, an area only the part inside it. Every case is added twice, once to its county and once to its area.

**c. Regions become months.** `region_month` produces counts, person-hours and availability for one region in one month. Counties additionally get day bars, an A–F `grade`, and the notice-to-completion medians; areas get neither grades nor bars, and their month rows are written sparsely because they dominate the payload.

**d. Output.** `write_site` writes the pages, `data.js` and two shards per county. The county *metrics* are serialised into `data.js` as `window.UISCE_DATA`, and `site.html` is copied beside it; the per-area breakdown and the closed-in-month lists go to `t/<county>.js`, loaded when a county is opened. A `<script>` tag rather than `fetch`, so the site works opened straight off disk.

The per-area *incident histories* — every notice ever published, event by event — do not go in `data.js`: together they are twice its size. They are written to `h/<county>.js`, one shard per county, each assigning into `window.UISCE_HISTORY`, and the page injects a `<script>` tag for one county when a reader opens an area in it. Same reason as above: an injected script survives `file://`, where `fetch` cannot read a local path at all. `write_site` owns the split, so a field added to the history cannot leak into the payload by somebody forgetting to pop it.

The third file is `areas.html`, a directory of every area with a notice, linking into those histories. Unlike `index.html` it is a *template* — `src/uisce/areas.html` with an `<!--AREAS-->` marker that `write_site` substitutes — so its markup and CSS stay in an HTML file and only the rows come from Python.

`site.html` is the whole front end: hash routing between an overview, one county view, one area history and the top ten, no build step, no dependencies.

## Flow 4 — the geography (`sa_pop.py`, `towns.py`)

Both write committed CSVs and are run only when the Census geography changes.

- `uisce-fetch-sa-pop` → `data/sa_pop.csv`: Small Area centroid and population.
- `uisce-fetch-towns` → `data/sa_towns.csv`: the named area each Small Area belongs to — a settlement, a Local Electoral Area of a city, or the countryside around an Electoral Division.

At runtime `SmallAreaIndex` answers "which Small Areas does this pin affect?" by grid-hashed radius lookup, and `TownLookup` answers "which named area is that, and how many people live in it?". Both are pure-Python with no GIS dependency, and everything the geography needs comes from attributes the CSO already publishes — [population-data-sources.md](population-data-sources.md) records why deriving it from boundary polygons instead was both heavier and less accurate.

## Where to change things

| To change | Go to |
|---|---|
| What counts as an outage / a quality notice | `classify` and the `*_CATS` sets in `site.py` |
| How a title becomes a category | `CategoryRule` in `pipeline.py`, then run `uisce-backfill` |
| Grade thresholds | `grade` in `site.py` |
| How long an open case accrues for | `CAP_DAYS`, and `resolve_case` |
| What counts as open, everywhere the site says so | `is_open` in `site.py`, carried on `Case.is_open` |
| Which end signals count as observed | `OBSERVED_END_SOURCES` in `config.py` |
| The affected-population radius | `AFFECT_RADIUS_KM` / `FALLBACK_KM` |
| When a settlement is split into electoral areas | `SPLIT_ABOVE_POP` / `MIN_PART_SHARE` in `towns.py` |
| Anything visual, or the page copy | `site.html` (single file, no build) |
| The LLM prompt or model | `inference.py`, then re-run inference and rebuild |
| The rules templates (bump `RULES_VERSION`) | `rules.py`, then `uisce-eval-rules-shadow` + `uisce-eval-replay --extractor rules` before re-running inference |

## Things that will bite

Each of these cost real time once. They are one line here and a section elsewhere.

- **`start_date` is a publication timestamp, not an onset.** Every duration is a floor. [data-quality.md](data-quality.md)
- **`closed_at` is observation time and `NULL` is ambiguous** — either still open, or closed before the column existed. Pair it with `status`. [data-quality.md](data-quality.md)
- **The `inferred_cases` table can lag the JSONL**, making inference look undone when it is not. Trust the count printed by `uisce-build-inferred`. [pipeline-dependencies.md](pipeline-dependencies.md)
- **The current month always grades harshly**, for three unrelated reasons. [statuspage-methodology.md](statuspage-methodology.md)
- **The feed's `water_outage` flag is set on 97% of cases** and cannot be used as a filter. [data-quality.md](data-quality.md)
- **Boil notices never state their own end**; the lift arrives as a separate case. [boil-notices.md](boil-notices.md)
- **CSO population CSVs are cp1252, not UTF-8** — except the Small Area one, which is utf-8-sig. [population-data-sources.md](population-data-sources.md)

## The other notes

[statuspage-methodology.md](statuspage-methodology.md) — every modelling decision behind the site and why · [data-quality.md](data-quality.md) — what the source fields actually mean · [population-data-sources.md](population-data-sources.md) — the Census joins · [pipeline-dependencies.md](pipeline-dependencies.md) — how the three artifacts get out of step · [boil-notices.md](boil-notices.md) — the weakest class in the dataset · [end-time-eval.md](end-time-eval.md) and [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) — whether the LLM extraction can be trusted · [water-sla-benchmarks.md](water-sla-benchmarks.md) — why the grades cannot borrow regulatory numbers · [frontend-notes.md](frontend-notes.md) — the hand-written pages' CSS gotchas.
