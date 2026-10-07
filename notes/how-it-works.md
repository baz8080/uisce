# How it works

**Simply put:** a script downloads every notice Uisce Éireann has published into a database, twice a day, and keeps the ones the feed later drops. A second script reads each notice's text for when the works ended. A third turns the database into a static website: a letter per county per month for outage notices per 100 km of water main, the typical time to "works complete", day bars, and a page for every county and town.

A map of the moving parts, for picking the project back up after a while away. **Structure only**: every measurement and every *why* lives in the other notes, linked from here and indexed in [README.md](README.md). If a number appears in this file, it is wrong; go and read the note.

## The shape of it

Three artifacts, each rebuilt by a different command, none derived from the other two on demand:

```
ArcGIS feed ──uisce-pipeline──▶ out/uisce.db ──uisce-site──▶ out/site/
                                    │  ▲
                        uisce-infer │  │ uisce-build-inferred
                                    ▼  │
                    data/inferred_end_times.jsonl
```

- **`out/uisce.db`**: the archive. The feed serves only current notices and keeps no history, so the DB is the only record that a case ever existed. Never rebuild it casually: a rebuild costs every case the feed has dropped, plus the geocode cache.
- **`data/inferred_end_times.jsonl`**: committed, append-only, the cache for end-time extraction. It is the source of truth for what has been inferred; the `inferred_cases` table is a rebuilt projection of it. Querying the table to decide what needs inference is the classic mistake, see [pipeline-dependencies.md](pipeline-dependencies.md).
- **`out/site/`**: fully static, regenerated from scratch every time, safe to delete.

Two committed lookups sit outside the loop: `data/sa_towns.csv`, the Census geography, refreshed only when the CSO revises it; and `data/wsz_mains.csv` and `data/wsz.geojson`, the km of water main and the boundary of each supply zone, refreshed by hand from Uisce Éireann's layer.

## Flow 1 - getting cases in (`pipeline.py`, `uisce-pipeline`)

1. `download_cases` pulls every notice from the ArcGIS feature server, paged by `OBJECTID`. `run` first reads the feed's own count and refuses a short download, so it never reaches the DB; the guard is in `run`, not in `download_cases`.
2. `map_cases` flattens attributes, converts epoch-ms timestamps, and derives the computed columns: `classify_category` turns a title into a `work_category` slug via the `CategoryRule` table, which also overrides `work_type` where the title is unambiguous (a burst main is never planned).
3. `geocode_all` reverse-geocodes each *rounded* coordinate through LocationIQ, caching in `geocode_cache`. Rounding is what keeps this affordable; `--skip-geocode` writes placeholder rows for a network-free refresh.
4. `load_cases` upserts into `cases`, stamps `closed_at` the first time a build observes a case stop being `Open`, and stamps `vanished_at` on a case the feed has dropped.

`create_db` declares the schema once (`CASE_COLUMNS`) and stamps `SCHEMA_VERSION` into `PRAGMA user_version`; `check_schema_version` runs every build and carries older DBs forward through `MIGRATIONS`. Migration is deliberately narrow, additive nullable columns only, and a DB missing a v1 column is refused rather than repaired.

`uisce-backfill` re-derives the computed columns in place with no network, for when the category rules change.

## Flow 2 - end times (`rules.py`, `inference.py` → `build.py`)

`uisce-infer` reads each case description and extracts the end-time signal: CPU rules first (`rules.py`, the templated ~93%, see [rules-vs-llm-end-times.md](rules-vs-llm-end-times.md)), asking a local LLM only for the cases the rules abstain on. It decides its own work by comparing each case's description hash, prompt version and extractor against the JSONL, so it is idempotent and only reprocesses changed text; bumping `RULES_VERSION` re-runs just the rules-produced cases. CI runs it with `--rules-only` on every data build and commits the JSONL; the fallback needs a local model, so the residue is run by hand.

`uisce-build-inferred` rebuilds the `inferred_cases` table from the JSONL, computing `notice_to_end_seconds` per case from the start it pinned at first inference. It refuses to run if the JSONL references cases the local DB does not have, and prints the never-inferred backlog on every build.

The distinction that matters downstream: `end_source` separates an **observed** completion from a **scheduled** one. See [statuspage-methodology.md](statuspage-methodology.md).

## Flow 3 - the site (`site.py`, `uisce-site`)

The only genuinely intricate part. It runs in four stages:

**a. Each case becomes an interval.** `resolve_case` maps one row to a `Case`: a severity class from `classify`, a start and end (or one interval per night for a repeating window), whether it is open and when it closed. All the awkward rules live here: boil notices routed through `boil_notice_fate`, open cases running to now under a cap, no-signal cases getting a token one-second footprint. It is deliberately pure, because it is the same answer regardless of who is counting.

**b. Cases accumulate into regions.** A `Region` is interval accounting for one grouping: counts by severity, day coverage, end signals. A county and an area within it are the *same object*; every case is added twice, once to its county and once to the area its pin was placed in.

**c. Regions become months.** `region_month` produces counts, day bars and the notice-to-completion medians for one region in one month. Counties additionally get outage notices per 100 km of main and the letter cut on it, a rolling `last_30` for the month in progress, and the health-marker counts; areas get counts only, written sparsely because they dominate the payload.

**d. Output.** `write_site` writes the pages, `data.js` and two shards per county. The county *metrics* are serialised into `data.js` as `window.UISCE_DATA`, and `site.html` is copied beside it; `index.html` also inlines the newest month of every county, which is all the first overview reads, so the first paint does not wait on `data.js`; the per-area breakdown and the closed-in-month lists go to `t/<county>.js`, loaded when a county is opened. A `<script>` tag rather than `fetch`, so the site works opened straight off disk.

The per-area *incident histories*, every notice ever published, event by event, do not go in `data.js`: together they are many times its size. They are written to `h/<county>.js`, one shard per county, each assigning into `window.UISCE_HISTORY`, and the page injects a `<script>` tag for one county when a reader opens an area in it. Same reason as above: an injected script survives `file://`, where `fetch` cannot read a local path at all. `write_site` owns the split, so a field added to the history cannot leak into the payload by somebody forgetting to pop it.

The static pages are templates: `county.html` (`c/<county>.html`), `area.html` (`a/<county>/<area>.html`, for areas that name a place), `areas.html`, the directory of every area with a notice, `zone.html` (`z/<zone>.html`, one per Water Supply Zone) and `zones.html`, the directory of every zone. Each has a marker that `write_site` substitutes, so markup and CSS stay in an HTML file and only the rows come from Python.

`site.html` is the whole front end: hash routing between an overview, one county view, one area history, the open list and the ten longest, no build step, no dependencies.

## Flow 4 - the geography (`towns.py`, `wsz.py`)

Committed lookups, each written by a command that is run only when its source changes.

- `uisce-fetch-towns` → `data/sa_towns.csv`: each Census Small Area's centroid and population, and the named area it belongs to: a settlement, a Local Electoral Area of a city, or the countryside around an Electoral Division.
- `uisce-fetch-wsz` → `data/wsz_mains.csv`: one row per Water Supply Zone with its mains length; `wsz.county_mains_km` sums the zones to the 26 counties. It also writes `data/wsz.geojson`, the zones' boundaries, and `wsz.ZoneLookup` puts a pin in its zone by winding number.

At runtime `TownLookup.place` answers "which named area is this pin in?" by the nearest Small Area centroid within `PLACE_KM`, from a grid hash, and `TownLookup.pop` "how many people live in it?", which is printed and never computed from. It is pure Python with no GIS dependency, and the named areas come from attributes the CSO already publishes: [population-data-sources.md](population-data-sources.md) records why deriving them from Census boundary polygons instead was both heavier and less accurate. `ZoneLookup.zone` answers "which supply zone is this pin in?" by a bounding-box prefilter and a winding number on `data/wsz.geojson`, also pure Python; the build prints how many distinct pins land in a zone.

## Where to change things

| To change | Go to |
|---|---|
| What counts as an outage / a quality notice | `classify` and the `*_CATS` sets in `site.py` |
| How a title becomes a category | `CategoryRule` in `pipeline.py`, then run `uisce-backfill` |
| Grade thresholds | `COUNT_CUTS` in `site.py` |
| Mains length per county | `data/wsz_mains.csv` via `uisce-fetch-wsz`, summed by `wsz.county_mains_km` |
| Which supply zone a pin is in | `data/wsz.geojson` via `uisce-fetch-wsz`, read by `wsz.ZoneLookup` |
| How long an open case runs for | `CAP_DAYS`, and `resolve_case` |
| What counts as open, everywhere the site says so | `is_open` in `site.py`, carried on `Case.is_open` |
| Which end signals count as observed | `OBSERVED_END_SOURCES` in `config.py` |
| How far a pin may be from the Small Area it is placed by | `PLACE_KM` |
| When a settlement is split into electoral areas | `SPLIT_ABOVE_POP` / `MIN_PART_SHARE` in `towns.py` |
| Anything visual, or the page copy | `site.html` and `site.css` (single file, no build); the shared parts in `../statusui` |
| The LLM prompt or model | `inference.py`, then re-run inference and rebuild |
| The rules templates (bump `RULES_VERSION`) | `rules.py`, then `uisce-eval-rules-shadow` + `uisce-eval-replay --extractor rules` before re-running inference |

## Things that will bite

Each of these cost real time once. They are one line here and a section elsewhere.

- **`start_date` is a publication timestamp, not an onset**, and the feed re-stamps it in place. Every duration is a floor. [data-quality.md](data-quality.md)
- **A start before the year 2000 is a feed typo**, refused wherever a start is read. [data-quality.md](data-quality.md)
- **`closed_at` is observation time and `NULL` is ambiguous**: either still open, or closed before the column existed. Pair it with `status`. [data-quality.md](data-quality.md)
- **The `inferred_cases` table can lag the JSONL**, making inference look undone when it is not. Trust the count printed by `uisce-build-inferred`. [pipeline-dependencies.md](pipeline-dependencies.md)
- **The month in progress has no letter of its own**; the page shows the rolling 30-day letter, and never-inferred open cases colour its bars to "now". [statuspage-methodology.md](statuspage-methodology.md), [pipeline-dependencies.md](pipeline-dependencies.md)
- **The feed's `water_outage` flag is set on 97% of cases** and cannot be used as a filter. [data-quality.md](data-quality.md)
- **Boil notices never state their own end**; the lift arrives as a separate case. [boil-notices.md](boil-notices.md)
- **CSO population CSVs are cp1252, not UTF-8**, except the Small Area one, which is utf-8-sig. [population-data-sources.md](population-data-sources.md)

The other notes are indexed in [README.md](README.md).
