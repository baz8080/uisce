# Pipeline dependencies

## `uisce-build-inferred` requires the local DB to be at least as fresh as the inference run

`data/inferred_duration.jsonl` and `out/uisce.db` are two independently-evolving artifacts. The JSONL is produced by running `uisce-infer` against whatever `out/uisce.db` happened to be on disk at the time — often on a different machine, at a different point in the scrape history, than whatever `out/uisce.db` you currently have locally.

`inferred_cases.case_id` has a foreign key to `cases.id`, so `uisce-build-inferred` will fail if the JSONL references a `case_id` that isn't in your local `out/uisce.db` — e.g. if inference was run elsewhere against a later scrape than the DB you're building against. This showed up in practice: an inference run on a different machine referenced ~650 case_ids that a locally-downloaded release didn't have yet.

`uisce-build-inferred` (`src/uisce/build.py`) checks for this up front and fails with a clear message naming the missing case_id range, rather than a raw `sqlite3.IntegrityError`. The fix is always the same: get a DB that's at least as new as whatever the inference run used, e.g.:

```
gh release download --pattern uisce.db --dir out/ --clobber
```

(defaults to the latest release; pass a specific tag if you know which one you need). There's no automatic reconciliation here on purpose — the inference run itself doesn't record which DB snapshot it used (see the description-hash discussion elsewhere in this repo's history for why the hash alone is enough for correctness, just not for provenance), so "grab the latest release" is the practical default rather than something that could be automated reliably.
