# Pipeline dependencies

## `uisce-build-inferred` requires the local DB to be at least as fresh as the inference run

`data/inferred_end_times.jsonl` and `out/uisce.db` are two independently-evolving artifacts. The JSONL is produced by running `uisce-infer` against whatever `out/uisce.db` happened to be on disk at the time — often on a different machine, at a different point in the scrape history, than whatever `out/uisce.db` you currently have locally.

`inferred_cases.case_id` has a foreign key to `cases.id`, so `uisce-build-inferred` will fail if the JSONL references a `case_id` that isn't in your local `out/uisce.db` — e.g. if inference was run elsewhere against a later scrape than the DB you're building against. This showed up in practice: an inference run on a different machine referenced ~650 case_ids that a locally-downloaded release didn't have yet.

`uisce-build-inferred` (`src/uisce/build.py`) checks for this up front and fails with a clear message naming the missing case_id range, rather than a raw `sqlite3.IntegrityError`. The fix is always the same: get a DB that's at least as new as whatever the inference run used, e.g.:

```
gh release download --pattern uisce.db --dir out/ --clobber
```

(defaults to the latest release; pass a specific tag if you know which one you need). There's no automatic reconciliation here on purpose — the inference run itself doesn't record which DB snapshot it used (see the description-hash discussion elsewhere in this repo's history for why the hash alone is enough for correctness, just not for provenance), so "grab the latest release" is the practical default rather than something that could be automated reliably.

## The mirror image: CI outruns inference, and the un-inferred backlog is almost all *open* cases

The section above covers the DB being older than the inference run, which fails loudly. The reverse — the DB being *newer* — fails silently, and it distorts the status site.

CI (`.github/workflows/build.yml`) runs `uisce-pipeline` then `uisce-build-inferred` on a schedule. It does **not** run `uisce-infer`: that needs a local LLM, so it only happens when the operator runs it by hand. Every CI build therefore lands cases that have no row in `inferred_cases` at all, and the backlog grows until someone runs inference.

Measured on the 2026-07-20 snapshot:

- **183 of 8,075 cases have never been inferred** (2.3%).
- **179 of those 183 (98%) have `status = 'Open'`.**

The skew is structural, not coincidental: un-inferred cases are by definition the most recently downloaded, and recent cases are the ones still open. So the backlog is not a random 2% — it is concentrated almost entirely in the population the site treats as ongoing.

**Why that matters for the site.** In `site.py`, a case that is `Open`, has no usable end signal, and classifies as `outage` accrues disruption time from publication until *now*, capped at 14 days. A never-inferred case has no end signal by construction, so it takes that branch. On this snapshot **126 cases are accruing to "now" with `end_source` NULL for 121 of them** — they are accruing because inference has not run, not because anything is known to be ongoing.

This inflates the newest month specifically, which is the month a reader looks at first. [statuspage-methodology.md](statuspage-methodology.md) already notes that "the current month grades harshly while in progress" and attributes it to open cases accruing against a part-elapsed denominator and to stale feed `status`; this is a distinct third cause, and unlike the other two it is an artifact of pipeline scheduling rather than a modelling choice.

**Not fixed here, because the fix is a real decision.** The options are not equivalent:

- *Run inference before building the site* — correct but manual, and it re-couples the site build to a local LLM.
- *Don't accrue for never-inferred cases* — treats "we haven't looked yet" as "no disruption", which under-counts in the opposite direction and silently hides a growing backlog.
- *Surface the backlog* — show un-inferred open cases as a data-freshness caveat rather than silently folding them into downtime.

The third is the honest default and the cheapest, but it changes what the page claims, so it wants a deliberate choice rather than a drive-by patch. Whatever is chosen, the count of never-inferred cases is worth printing at build time — it is currently invisible.
