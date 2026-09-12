# 5b. An honest number on the model
*~9 min read · PRs #16–#17 · 18–20 July 2026*

*Where we are:* a website (chapter 5a) whose every grade rests on end times that a local model
read out of prose (chapter 3). Nobody had checked how often it read them right. This chapter
does — twice — and along the way finds that the measuring instrument was itself broken.

## The question that opened this stretch

Every number on the page — durations, person-hours, grades — trusts the model's reading of the
notice, and the only in-feed cross-check (`end_date`) had already been shown to be worthless
(chapter 3). So the model was the least-validated link in the chain, and the site had just made
that chain public. The question was simple and overdue: **what fraction of the time is it
right?**

## What changed

### Round 1: 114 cases, labelled by hand

The method: draw a sample of cases, show a human the description and the model's three answers
(`end_source`, `local_date`, `local_time`), and have them mark each row `correct`, `incorrect`
or `unsure` — filling in what the text actually supports when the model was wrong. A scorer then
reports accuracy per class and overall. The sample is **stratified**: the rare classes are
deliberately over-drawn so their error rates can be measured at all, and the draw is seeded so
it can be reproduced.

> **Concept: a stratified sample, and why its headline misleads.** If 67% of all cases are
> completion updates and 0.6% are boil-notice lifts, a random sample of 114 would contain about
> one lift — useless for judging how the model handles lifts. Stratifying means drawing *more*
> of the rare classes than their share, so each class gets enough rows to say something. The
> price is that the overall percentage no longer describes the corpus: it over-weights exactly
> the classes that were over-drawn. Round 1's 71.9% is a number about *the sample's mix*, not
> about the notices as a whole. Read the per-class table, not the total.

The result (18 July, prompt v1, gemma-4-12b-qat):

| `end_source` | correct | incorrect | accuracy |
|---|---|---|---|
| completion_update | 37 | 3 | 92% |
| scheduled_end_with_time | 27 | 3 | 90% |
| not_found | 18 | 2 | 90% |
| scheduled_end_date_only | 0 | 9 | 0% |
| lifted_immediate | 0 | 15 | 0% |
| **total** | **82** | **32** | **71.9%** |

Two zeros, and neither meant what it looked like. All 15 `lifted_immediate` misses were a
disagreement about convention: the labeller expected a time to be filled in from `start_date`;
the prompt says the time is null unless the *text* gives one; the model followed the prompt.
That class stores no duration anyway. Setting it aside, accuracy on the classes that actually
feed durations was **82/99 = 82.8%**. And of the nine `scheduled_end_date_only` misses, eight
were one pattern — *"works nightly from 10pm until 7am, from 8 July until 17 August"* — where
the model reported a bare date instead of the final date with the window's closing time.

The most damaging real error was smaller in count: **seven cases** where the description
contained a newer *"works are now complete"* update and the model reported an older scheduled
end anyway (worst: a scheduled end eight days before the actual completion). Those go straight
into the site's time-to-fix. Two more dropped a time that was plainly in the text, both with a
single-digit day (`6/07/2026`) — a hypothesis about the date format throwing the parse.

So round 1 produced a backlog of three prompt fixes, in impact order: completion beats
scheduled; recurring windows → final date + window close time; check the `d/mm/yyyy` case.
It also settled a policy: `lifted_immediate` is **excluded** from site metrics rather than
modelled — 42 pins deduplicating to 15 lift events, 0.56% of cases, and the ambiguity in how
the feed stamps their start makes a same-day lift indistinguishable from an unrecorded one.

### Prompt v2, and a broken ruler

PR #17 (20 July) shipped prompt version 2, aimed at exactly the three failure modes, with a
worked example of each written into the prompt. Two things about *validating* it are the
useful part of the story.

First, a bug that would have made the whole exercise silent: the skip logic from chapter 3
re-read a case only if its description hash changed. A prompt bump changed no hashes, so
bumping the version **re-inferred nothing**. Fixed to compare (hash, prompt version) — against
the live database that flagged all 7,552 cases where before it flagged zero.

Second, to score pv2 without a second week of labelling, a **replay** harness re-runs the new
prompt over round 1's 114 rows and scores against the human labels already there. Doing that
exposed defects in the ruler itself. The replay's ground truth fell back to the model's own
answer for a blank `end_source` cell but *not* for a blank date or time — and round 1's labeller
had, correctly, filled only the cells the model got wrong. So partially-corrected rows carried
an empty-string "truth" no prompt could ever match, understating every version equally. And four
of the 114 rows had defective labels: a correction written only in the notes column, a date and
time swapped, a row endorsed `correct` whose blank time the text contradicted (*"Update 9:57am
6/07/2026"*), and one the labeller had revised on review. Together they cost about four points
on any prompt scored against the file. They were fixed in place, each marked `[amended
2026-07-19]` — a deliberate breach of the "round files are never overwritten" rule, because
the file is the instrument every future prompt is measured with.

> **Concept: replay versus hold-out.** A *replay* scores a new prompt on the same rows its fixes
> were reasoned from. It is a regression filter — it tells you the three known failures are
> gone — and says nothing about failures you haven't met yet, because you tuned the prompt to
> pass it. A *hold-out* scores on cases the prompt has never seen. Only a hold-out estimates
> accuracy on the corpus. Both numbers were published; only the second carries evidential
> weight, and the PR says so.

The replay, after the ruler was fixed: pv1 **81/114** → pv2 **99/114** overall, and **99/99**
on the classes that feed durations. All three backlog items closed.

### Round 2: 120 unseen cases, and why 100% is not 100%

A new sampler draws *N* unseen cases and runs the current prompt over just those, so a fresh
round costs ~120 model calls (about five minutes) instead of re-inferring the corpus (7,552
calls, 4.2 hours). The draw is uniform, not stratified — the trade is that rare classes can't be
over-drawn, but a uniform draw is what a corpus-wide estimate actually needs, and no stratified
round had ever produced one.

Round 2, prompt v2, 120 unseen cases: **120/120**.

### Worked example: what zero errors in 120 can and cannot say

If you see zero failures in *n* independent trials, a standard rule of thumb (the "rule of
three") puts the 95% upper bound on the true failure rate at about 3 ÷ *n*. With *n* = 120:

3 ÷ 120 = 0.025, so the true error rate could plausibly be as high as **2.5%**, i.e. the true
accuracy is at least about **97.5%** with 95% confidence.

That is the number to carry, not 100%. The sample cannot distinguish a prompt that is right
99.9% of the time from one that is right 97.6% of the time. Two classes drew zero rows and are
simply unmeasured. And 67% of the sample is `completion_update` — the corpus mix, so the
headline is mostly a claim about that class. The PR published the 120/120 with all of that
attached rather than as a clean win.

### The corpus, re-read

With pv2 validated, all 7,892 cases were re-inferred: zero failures, and about 1.5% changed
class, every change in the direction the eval predicted:

| `end_source` | pv1 | pv2 | Δ |
|---|---|---|---|
| completion_update | 4,616 | 4,715 | +99 |
| scheduled_end_with_time | 2,543 | 2,503 | −40 |
| scheduled_end_date_only | 55 | **0** | −55 |
| not_found | 296 | 291 | −5 |
| lifted_immediate | 42 | 43 | +1 |

`scheduled_end_date_only` had become unreachable — the prompt emitted it zero times — which
raised the obvious worry that pv2 was now *inventing* times. So every case with a time was
checked for whether its description contained a time at all. **No fabrications.** The 15
apparent exceptions were real: twelve say "midday", three are Irish-language notices ("10rn go
dtí 6in", 10 am to 6 pm) that the prompt's Irish rules converted correctly. The corpus genuinely
contains no end-date-without-time notices. The pv1 records were kept in the JSONL alongside the
pv2 ones — the file is the only complete record of what pv1 said, and the table above is
computable only because both exist.

### Two policies settled in passing

*Boil notices cannot end themselves.* The utility publishes the lift as a separate case, so
every boil-notice-issued case is `not_found` for end time, in every prompt version. The site had
been letting 22 such notices accrue as open on the strength of the feed's `status` alone —
eight were older than the 14-day cap, and one had sat "Open" since November 2025 while its own
text said the notice was lifted. That fabricated roughly 37 merged days of *quality* time
across five counties. Quality does not touch availability, but it coloured days and knocked
grades: removing it moved Cork's May from F to D and Donegal's April from C to B. The policy now
lives in one function with four outcomes — paired to a lift, accrue, exclude, closed with no
signal — and a real lift beats the staleness rule at any age.

*There is no better start than publication.* Labelling surfaced that 55% of descriptions state
their own start ("works are scheduled to take place from 10pm"), which raised the idea of a
toggle: duration from the stated start rather than the publication time. Measured, it fails.
For unplanned works (n = 1,512) the notice goes out a median 0.8 h *before* the stated works
start, so substituting it moves the clock later — away from the true onset, exactly where the
floor already bites hardest; for planned works (n = 2,094) it changes nothing (median +0.1 h).
No toggle. The recommended alternative was to name the metric for what it is — *time from public
notice to restoration* — and that is chapter 6.

## Where it left the site

A measured accuracy behind every duration on the page: at least ~97.5% on unseen cases, with the
caveats written where the number is. A prompt (v2) whose three known failure modes are closed
and whose skip logic actually re-reads on a version bump. A labelling instrument that has been
audited, and a cheap way to run the next round. And two settled policies that stop the site
fabricating time. Three days later, the site changed what it *called* the number — chapter 6.

## Notes

- PR #16 (18 Jul 2026): `uisce-eval-sample` (stratified, seeded), `uisce-eval-score`; round 1
  N=114, 71.9% raw, 82.8% on duration-feeding classes; error taxonomy; `lifted_immediate`
  excluded (42 pins → 15 events, 0.56%).
- PR #17 (20 Jul): prompt v2; skip logic keyed on (hash, prompt_version) — 7,552 flagged where
  pv1 flagged 0; `uisce-eval-replay`; four round-1 labels amended (~4 points);
  pv1 81/114 → pv2 99/114, 99/99 excl. `lifted_immediate`; `uisce-eval-sample-fresh` (~5 min vs
  4.2 h); round 2 120/120 uniform, 95% lower bound ≈ 97.5%; corpus 7,892, 0 failures, class
  table above; boil-notice policy (22 stale, ~37 merged days, Cork May F→D, Donegal Apr C→B);
  start-basis toggle rejected (Unplanned n=1,512 median −0.8 h; Planned n=2,094 +0.1 h).
- `notes/end-time-eval.md` "Workflow", "Labelling guide", results 2026-07-18/19, "Decision:
  `lifted_immediate` is excluded"; `notes/boil-notices.md`; `notes/data-quality.md` "Resolved
  2026-07-20" (no better start basis).
- Rule of three: 95% upper bound ≈ 3/n for zero events in n trials; 3/120 = 2.5%.
