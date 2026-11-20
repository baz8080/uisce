# 2. Let a robot do it every week
*~5 min read · PRs #5–#6 · 30 June 2026*

*Where we are:* chapter 1 left a script on my laptop that fetches every water notice, gives each
pin an address, and keeps them all in a single-file database. It ran when I remembered to run it.
This chapter makes it run itself, and makes the result public.

## The question that opened this stretch

An archive that only grows when I remember to press a button is not an archive; it is a diary
with gaps. The feed forgets (chapter 1), so every week I failed to run the script was a week of
notices I might never see. The fix is old and boring and exactly right: put the script on a
timer, somewhere that is not my laptop, and have it file the result somewhere I can't lose it.

## What changed

### PR #5: a weekly build, published

Both halves of that arrived in one PR on 30 June. A **GitHub Actions** workflow now runs every
Monday at 6 am UTC. It does four things in order:

1. **Download the previous database** from the most recent GitHub Release. This step is the
   whole point. Chapter 1's upsert only preserves history if the run starts from the *old*
   database, not from nothing; on a fresh machine every week, "the old database" has to be
   fetched from wherever the last run left it.
2. **Fetch the feed** and upsert every case into it (chapter 1's pipeline, unchanged).
3. **Reverse-geocode only the new coordinates.** Here the cache from chapter 1 earns its keep:
   the geocode table travels inside the database, so a coordinate looked up in week 1 is never
   looked up again in week 40. PR #5 also removed the separate `geocodes.jsonl` file that had
   been holding this state; the cache table in the DB is now the only copy.
4. **Publish the updated database** as a dated Release — `2026-06-30`, `2026-07-07`, and so on
   — that anyone can download.

A second commit handled the case where the tag already exists (a manual run on the same day),
by attaching the file to the existing release instead of failing.

> **Concept: CI as a scheduled clerk.** "CI" (continuous integration) is the name for machines a
> code-hosting service will lend you to run a script whenever something happens — a commit, a
> button press, or a clock. Think of it as a clerk who turns up on schedule, follows the same
> written procedure every time, and files the output in a public cabinet with the date on the
> folder. The clerk has no memory of last week either — each run starts on a blank machine —
> which is why step 1 above, *fetch last week's folder before starting*, is not optional. It is
> the only thing that connects one run to the next.

Two consequences I did not fully appreciate at the time.

The first is that the database became a **published artefact**. From this PR on, anyone —
including me on a different machine — can get the whole archive with one download, no setup, no
API key. The README's "Just want the data?" section dates from here.

The second is that a *dated series of database snapshots* now exists on GitHub. Each Monday's
release is a photograph of every case's status as of that morning. That is not something I set
out to build. But it is history — the one thing the feed refuses to provide — and three weeks
later (chapter 7) it turns out to be the only way to recover when 1,816 cases actually closed.

### PR #6: fill in the county the feed left blank

The same day, a small data fix. About 10 of the 5,000-odd cases arrived from the feed with no
county at all. The pipeline already had a better source sitting in the geocode cache: every
pin's reverse-geocoded address includes a county. So after geocoding, a new step looks up just
the coordinates whose case has no county and fills it from the cache.

The wrinkle is spelling. LocationIQ says `County Kildare`; the feed says `Kildare`. Ten rows
saying `County Kildare` in a column where 5,000 say `Kildare` would be ten rows that never match a
filter, so the backfill strips the prefix. It is exactly the kind of one-line normalisation that
looks trivial and, left undone, silently loses ten cases from every count for the life of the
project.

Where the step sits was argued about in the PR and is worth a sentence: it runs *between*
geocoding and loading, as its own step, rather than being folded into the field-mapping (the
geocode answers don't exist yet at that point) or hidden inside the database load (which should
not be enriching data). Ordering the pipeline so each step has one job is a habit that pays off
in chapter 4, when the whole thing is restructured.

## Where it left the site

Still no site. But the archive now grew by itself, once a week, on a machine that wasn't mine,
and every version of it was kept. From here the question changed from "do I have the data?" to
"what does the data actually say?" — and the first honest answer to that, in chapter 3, is that
the most important field, *when did the water come back*, is not in any column. It is in the
prose.

## Notes

- PR #5 "Add weekly CI build with dated GitHub Releases" (30 Jun 2026): Monday 06:00 UTC cron;
  downloads the latest release DB before running; geocode state consolidated into
  `geocode_cache`; `geocodes.jsonl` removed; existing-tag fallback for same-day manual runs.
- PR #6 "Backfill missing county from geocode cache" (30 Jun 2026): ~10 of 5,000+ cases; "County
  X" → "X"; runs as its own step between `geocode_all` and `create_db`.
- The cadence changed later — Mon/Wed/Fri, then daily (PR #22, 21 Jul), then twice daily (PR #26,
  31 Jul) — for reasons that belong to chapters 7 and 9.
- Figures: PR #6 for the ~10 count; PR #21 (21 Jul) for the 1,816 recovered closures.
