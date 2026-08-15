# uisce

A static status site for Uisce Éireann water disruption notices, built from an ArcGIS feed.
`notes/` carries ~33k tokens of measured findings and settled decisions across 10 files — too much
to read wholesale, which is why the important ones are indexed here.

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
| An active boil-water / do-not-drink notice is a marker *beside* the grade, not a knock to it. | statuspage-methodology.md — "The health notice was unbundled from the grade" (2026-08-02) |
| `lifted_immediate` is excluded from site metrics; its duration is NULL, never 0. | end-time-eval.md — "Decision: `lifted_immediate` is excluded" (2026-07-18) |
| The notice title alone is not a reliable severity signal. | data-quality.md — "The notice title is not a reliable severity signal" (2026-08-02) |
| The `water_outage` feed flag cannot filter anything — it is set on 97% of cases. | data-quality.md — "`water_outage` flag is not a filter" |
| Duration outliers are categorical, not statistical. The 14-day cap is a backstop, not the outlier strategy. | data-quality.md — "Duration outliers are categorical" |
| "We are investigating" reference pairing works but rescues almost nothing — not worth building. | data-quality.md — "'We are investigating' notices" (corrected 2026-07-20) |
| `closed_at` is a floor: short-lived cases are never observed open. Twice-daily builds are the settled cadence. | data-quality.md — "`closed_at` is a floor" (re-measured 2026-07-31) |
| gemma-4-12b-qat over qwen3.5-9b for end-time extraction; prompt version is at v3. | model-and-runtime-benchmarks.md, end-time-eval.md |
| Geography is CSO Census settlements, not the feed's `location` string (3,866 distinct values, fragments badly, carries no population). | statuspage-methodology.md — "The county drill-down" (2026-07-25) |

## Conventions

- Decisions go in `notes/`, dated, with the rejected alternatives and their numbers. Add a row here
  when one closes something off — this file carries pointers only, never the rationale, or it
  becomes the thing it exists to fix.
- `uv run pytest` before anything ships. The payload-shape tests in `tests/test_site.py` are guards:
  when one fails because a key was added, that is the guard working.
- The `cases` schema is declared once, as `CASE_COLUMNS` in `pipeline.py`. `create_db`,
  `DB_CASE_COLUMNS`, the `V1`/`REQUIRED` migration sets and the test fixtures all derive from it.
  Adding a column is one entry there plus a `MIGRATIONS` step and a `SCHEMA_VERSION` bump;
  `TestSchemaIsDeclaredOnce` fails if a second statement of the schema reappears.
- Migrations are additive nullable columns only; anything that rewrites data is a rebuild, and a
  rebuild costs the accumulated archive.

## Commands

```bash
uv run uisce-pipeline        # download the feed into out/uisce.db
uv run uisce-infer           # LLM end-time extraction (needs LM Studio)
uv run uisce-build-inferred  # rebuild inferred_cases from the JSONL
uv run uisce-site            # build out/site/
uv run pytest
```
