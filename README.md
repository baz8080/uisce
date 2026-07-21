# uisce

Download, transform, and geocode [Uisce Éireann](https://www.water.ie/) (Irish Water) supply and works notices, and infer each notice's end time from its text with a local LLM. The result is a single SQLite database, rebuilt by CI three times a week and published as a GitHub release, plus a statuspage-style static site with per-county supply availability and A–F grades.

**What the time figures mean.** This project does not measure outage duration and cannot: the feed never records when supply was actually lost. What it measures is the span from **when a notice was published** to **the end that notice reports** (`notice_to_end_seconds`), and the site publishes the subset where that end is an observed "works are now complete" update rather than a schedule. Every figure is a floor on true length. See [notes/data-quality.md](notes/data-quality.md) and [notes/statuspage-methodology.md](notes/statuspage-methodology.md).

## Just want the data?

Grab the latest `uisce.db` from [releases](https://github.com/baz8080/uisce/releases) — no setup needed:

```
gh release download --clobber --pattern "uisce.db" --dir out/
```

Tables:

* `cases` — one row per published notice pin (title, description, dates, status, impact flags, WGS84 coordinates). `work_category` is a slug normalised from the title (`burst_main`, `essential_works`, …); `work_type` (Planned/Unplanned) is taken from the feed but overridden for categories where the label is unambiguous (a burst main is never planned).
* `geocode_cache` — reverse-geocoded address per rounded coordinate
* `inferred_cases` — LLM-extracted end-time signal and computed `notice_to_end_seconds` per case

Before leaning on `start_date`/`end_date` or per-case counts, read [notes/data-quality.md](notes/data-quality.md) — several fields don't mean what they appear to mean.

The `cases` schema is declared once, in `create_db`, and stamped into `PRAGMA user_version` (`SCHEMA_VERSION`, currently 2). The published DB is downloaded and updated in place each build, so `check_schema_version` runs every time and carries older DBs forward via `MIGRATIONS`.

Migration is deliberately narrow: **additive nullable columns only**, which SQLite applies without rewriting a row. A DB missing any v1 column is refused with instructions to rebuild rather than migrated. That asymmetry is on purpose — the DB is an accumulating archive of a feed with no history, so a rebuild costs every case the feed no longer serves plus the geocode cache. Take a copy before rebuilding.

`cases.closed_at` (v2) records when a build **first observed** a case stop being `Open`. The feed publishes only current status, so this is the sole record of the transition. Two consequences for anyone querying it:

* It is observation time, not event time — resolution is the build cadence.
* `NULL` is ambiguous: either still open, or closed before the column existed (every case closed prior to v2). Pair it with `status` rather than reading `NULL` as open.
* It is a **floor**. Cases created and closed between two builds are never observed open, so no transition exists to record — 12% of newly-appearing cases, measured 2026-07-21. See [notes/data-quality.md](notes/data-quality.md).

History from before v2 can be partially recovered by replaying the published release DBs, each of which is a full snapshot. Run the **Build DB** workflow with `replay_closed_at` ticked — it does the whole thing in one build, after the pipeline has migrated the DB and stamped its own transitions.

The replay recovers the same measurement the live path makes (first build observing the case non-Open), never overwrites an existing stamp, and is idempotent, so it is safe to re-run — worth doing if the DB is ever restored from an older release. It reached 24% of closed cases on 2026-07-21; the rest closed before the earliest published snapshot.

Locally, against a directory of downloaded snapshots named `<release-tag>.db`:

```sh
uv run uisce-replay-closed-at --snapshots snaps          # dry run
uv run uisce-replay-closed-at --snapshots snaps --write
```

## Running it yourself

Requirements: [uv](https://docs.astral.sh/uv/) (any recent version; it manages Python itself) and, for the geocoding step, a free [LocationIQ](https://locationiq.com/) API key.

```
git clone https://github.com/baz8080/uisce
cd uisce
uv sync
echo 'LOCATIONIQ_API_KEY=your_key_here' > .env
uv run uisce-pipeline
```

`uisce-pipeline` downloads all cases from the ArcGIS feed, maps and geocodes them, and builds `out/uisce.db`. Geocoding results are cached in the DB, so the first run makes one LocationIQ request per unique coordinate (rate limited to 1/s — expect a couple of hours from scratch) and later runs only geocode new coordinates. Start from a released DB (see above) to skip most of that.

Two options for working without the paid geocoding step:

* `uisce-pipeline --skip-geocode` — refresh cases from the ArcGIS feed but skip LocationIQ; new coordinates get placeholder geocode rows (retried on the next real run). Handy for seeing the current source data quickly. Don't publish the result — those cases have no location yet.
* `uisce-backfill` — re-derive the computed columns (trimmed title, `work_category`, `work_type`) on the existing `out/uisce.db` with no network at all. Run it after editing the category rules to re-apply them to data you've already downloaded.

## Building the status site

```
uv run uisce-site
```

Reads `out/uisce.db` and writes a fully static site to `out/site/` (serve it with any file server, e.g. `python -m http.server -d out/site`). Per county and month it shows day-by-day status bars, population-weighted supply availability, and an A–F grade — only hard supply outages (bursts, plant/reservoir/pump interruptions, unplanned repairs) count against availability; restrictions, discolouration and non-disruptive works are shown but never accrue downtime.

The availability weighting uses Census 2022 Small Area populations (`data/sa_pop.csv`, committed; regenerate with `uv run uisce-fetch-sa-pop`). Before reading too much into the numbers, see the notes:

* [notes/statuspage-methodology.md](notes/statuspage-methodology.md) — every modelling decision and its rationale
* [notes/water-sla-benchmarks.md](notes/water-sla-benchmarks.md) — Ofwat/CRU service levels and why the grades can't borrow them
* [notes/population-data-sources.md](notes/population-data-sources.md) — the CSO/Tailte open-data join
* [notes/data-quality.md](notes/data-quality.md) — what the source fields actually mean

## Running inference locally

Duration inference reads each notice and extracts the end-time signal using a local model (currently `gemma-4-12b-qat`) behind an OpenAI-compatible API, e.g. [LM Studio](https://lmstudio.ai/).

1. Start the LLM server on :1234
2. `gh release download --clobber --pattern "uisce.db" --dir out/`
3. `uv run uisce-infer` — appends results to `data/inferred_end_times.jsonl` (committed to the repo; only new/changed descriptions are processed)
4. (Local test only - CI will do this on a schedule) `uv run uisce-build-inferred`

## Layout

```
src/uisce/
  pipeline.py    download, map, geocode, load cases   (uisce-pipeline)
  inference.py   LLM end-time extraction to JSONL      (uisce-infer)
  build.py       build inferred_cases from the JSONL   (uisce-build-inferred)
  site.py        generate the static status site       (uisce-site)
  sa_pop.py      fetch Census Small Area populations   (uisce-fetch-sa-pop)
  site.html      front end copied into out/site/
  config.py      shared paths, constants, HTTP session
tests/           pytest suite (no network access needed)
notes/           data-quality findings and pipeline caveats
```

The commands are console entry points declared in `pyproject.toml`; run them from the repo root, since data paths (`out/`, `data/`) are relative.

## Development

```
uv sync --group dev
uv run pytest
uv run ruff check
```

CI lints and tests on every push. The `Build DB` workflow runs the pipeline three times a week (Mon/Wed/Fri) and publishes the refreshed DB as a release.

## Interesting APIs

* features - https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/WaterAdvisoryCR021_DeptView/FeatureServer/0/?f=json
* count - https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/WaterAdvisoryCR021_DeptView/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json

## License

[Apache 2.0](LICENSE)
