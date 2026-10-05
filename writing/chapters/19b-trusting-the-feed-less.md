# 19b. Trusting the feed less
*~10 min read · PRs #83, #84, #88, #89, #90 · 5 September 2026*

*Where we are:* chapter 19a covered the seven features the 5 September survey found missing. Two
of the nine items on that list were not features. They were places where the site believed the
feed over its own evidence, and both had been quietly wrong for weeks.

## The question that opened this stretch

Chapter 1 records the decision the whole archive rests on: never delete a row, because the feed
has no memory. Chapter 7 records a measurement that seemed to bound the risk in that. Probing the
feed on 21 July found no case that had ever been removed from it, and the note written that day
says the feed never deletes.

That was true when it was measured. It stopped being true on 10 August, and nothing noticed for
nearly a month.

## What changed

### Ten notices that could never close (PR #83)

The work that found it started somewhere smaller. Ten cases were sitting in the "open now" counts
and colouring day bars, and would sit there forever, because the feed had stopped serving them.
Chapter 7's `closed_at` is stamped when a case the site has seen as Open comes back as Closed; a
case the feed no longer serves never comes back as anything, so the transition it waits for will
never arrive. Nine of the ten had been gone for more than a fortnight. All were low-pressure or
conservation notices.

The fix is a fourth column on the additive migration ladder from chapter 7: a date stamped on the
first build whose download does not contain a case, and cleared if the case returns. The site's
open test reads it beside the feed's status, so a vanished case is treated as closed with no end
signal and appears in neither the open list nor the closed-this-month list - the latter because
that list is keyed on an observed closure, and this is not one.

> **Concept: a stamp is only as safe as the download it is inferred from.** Absence is not
> evidence unless you can prove you looked. The downloader pages through the feed until it gets an
> empty page, which means a truncated response - a network fault, a partial outage at the far end -
> looks exactly like a feed that has dropped thousands of cases. Stamping on that would mark a
> large part of the archive as vanished on the strength of a broken connection, and the stamp
> changes what the site publishes. So the run now asks the feed for its own count first, and
> refuses any download more than 1% short of it, before anything touches the database. The guard
> runs ahead of the inference, because the cheapest place to stop a bad build is before it writes.

Validating the stamp against a copy of the release is where the ten became the real finding.

#### Worked example: 9,052 notices the feed forgot

Stamping the 4 September release marked **9,052 cases as no longer served, all of them published
before about 8 August**: 2,367 from May, 2,563 from June, 3,205 from July and 46 from August. They
went on 10 August, and it is not a rolling window either - closed cases that closed 31 days before
the horizon are still served, and only one case has gone since (PR #83, 5 Sep 2026).

So the July finding is superseded, and the sentence in chapter 1 about the feed having no memory
turns out to have been an understatement rather than a figure of speech. **The feed does not merely
fail to remember when something ended. It stops carrying the notice at all.** For those 9,052
notices - four months of Irish water disruptions - the release database this project publishes
twice a day is now the only record there is.

That is either the most gratifying sentence in this series or the most alarming one, depending on
where you stand. The upsert decision in chapter 1 was made in June for a mundane reason: rebuilding
the table each run threw away yesterday's rows and that seemed wasteful. It is the reason four
months of notices still exist in a readable form.

Nothing printed the purge, which is why it took a month to find. The build now reports the count it
stamped on every run, so the next one is in the log the day it happens.

A note published the same day extends the theme. Chapter 12 left boil-water notices with an open
question: only 1 of 17 events could be paired with the notice lifting it, and the expectation was
that coverage would improve as the archive grew. Re-measured on the 4 September release it is still
1, and the reason is not history. The 10 issue events and the 16 lift events published since
collection began name **disjoint schemes**: one town appears on both lists and for every other lift
the archive holds no case of any category naming that scheme in the preceding 90 days. The utility
publishes the issue for some schemes and the lift for others, almost never both, so nothing in this
pipeline can pair a lift with an issue that was never published. Waiting for more data will not fix
it, and the note now says so instead of hoping (PR #84).

### The badge that disagreed with the notice (PRs #88, #90)

The second wrong thing came from a reader, which is the first time in this series that has
happened.

They pointed at one notice in Carlow: its own most recent update said the works were complete, and
the county page still listed it under "Open now". Two days after the fact.

The cause is a sentence that should have been uncomfortable to write down. The site's open test
read the feed's status field and nothing else - while the availability arithmetic, since chapter 3,
has been reading the *extracted* end out of the notice's own text and stopping the charge there.
**The arithmetic trusted the notice and the badge trusted the feed**, on the same case, in the same
build, from the same row.

The first response was to document it. A prototype fix touched the open list, the national total,
the per-event history and the new Atom feed, plus about a dozen tests that used "status Open" on a
fixture which - it turned out - already carried a completion. That blast radius, and the asymmetric
cost of a false negative hiding a genuinely open case, looked like something for the owner to
decide rather than a five-line patch (PR #88).

Then it got measured, and the measurement dissolved the question.

#### Worked example: how often each side is wrong

Measured against the 5 September release:

- **216 of the 562 cases the feed calls Open** were already past a completion their own text
  reported - 177 of the 437 events the site was listing as open.
- Across 3,783 closed cases, **the feed marks a case closed a median of 72 hours after the stated
  completion**, with a 90th percentile of 111 hours. This is chapter 7's finding again, from the
  other end: the utility's closure lag is real, it is the reason the site invented `closed_at`, and
  it had been silently setting what the badge said.
- The other side of the trade is empty. **Of 7,667 completion updates on file, none has ever been
  followed by a newer update** - the one candidate turned out to be the same update pasted twice.
  So the false-negative risk that justified the caution, a notice saying it was finished and then
  resuming, has never once occurred in the archive.

One measurement later, the same day, the fix went in (PR #90, 5 Sep 2026).

> **Concept: a signal trusted for the arithmetic is trusted for the display.** If the site is
> confident enough in its extracted end time to stop charging a county's availability at that
> moment - the number in the grade, the number on the front page - then it is confident enough to
> stop saying the notice is open. Any surface that reads the raw feed status where the extraction
> contradicts it is not a trade-off to record; it is a bug. The corollary that went into the
> repository's conventions is about *how* to defer: leaving a trade-off for the owner means
> measuring both sides first and writing both numbers into the entry. Deferring without the numbers
> is not caution, it is just a delay that looks like caution.

The decision is now made once, in the function that resolves a case, and carried on the case
object, so the open list, the national total, the new national open view, the county page's open
section and its notice text, the history's "still open" and the Atom feed all read one answer.
Scheduled ends still do not close a case: a schedule is a plan, which is the same line chapter 6's
median draws.

The scale of the correction is worth stating precisely, because it is easy to misread. **No
published figure moved.** With the clock pinned, every availability number, every person-hour
total and every grade is byte-identical under both readings, because the arithmetic was already
doing the right thing. What moved is what the site *says* is happening now: the count of open
events nationally went from 437 to 260.

### One more thing the day broke (PR #89)

A footnote that is really a lesson about the deploy split from chapter 15. Adding the vanished
column to the schema broke the *site* build within the hour: the site downloads whichever release
database is current and reads it as it is, and the current release was still on the old schema,
because only the data build migrates it and it had not run since the merge.

Since chapter 15 the site can deploy on its own clock, which is the feature working exactly as
designed and, on this one day, the reason the failure existed at all. The site now carries the
downloaded copy to the current schema itself before reading it. The copy is local to the runner and
never republished; the data build runs the same migration on the real database later and it does
nothing. Every future column addition would have failed the same way on the first user-interface
push after it.

## Where it left the site

Measured against the database on 12 September, the archive holds 12,430 cases across 10,133
distinct references, and 9,281 of them are cases the feed no longer serves. The site does not
present a notice as open unless nothing the notice itself says has ended it.

Both of this chapter's findings are the same mistake with different faces. The feed is the source,
and treating a source as authoritative about its own contents is a habit rather than a decision: if
it stops listing something, the thing is gone; if it says Open, the notice is open. Both are
statements about the feed. Neither is a statement about a burst water main in Carlow. The archive
was built in chapter 1 on the assumption that the feed forgets, and the correction here is just
that assumption applied two more places, three months late.

There is a last irony in the reader's report. This site exists because I wanted to know whether
other places had it as bad as Leixlip, and for four months it answered that with a table nobody
had asked it about. The first stranger to send me a correction did not query the grades or the
person-hours or the Census weighting. They noticed that a notice on their county page said "open"
when the notice underneath said the works were done. The arithmetic is what took the work. The
badge is what got read.

## Notes

- PR #83 (5 Sep 2026): `cases.vanished_at`, schema v4, one entry in `CASE_COLUMNS` plus a migration
  step; stamped by the loader on the first download lacking a case, cleared on return; 9,052 cases
  unserved since 2026-08-10 (May 2,367, June 2,563, July 3,205, August 46), not a rolling window,
  one case since; ten Open cases stamped, nine gone over 14 days; `FEED_COUNT_TOLERANCE` refuses a
  download more than 1% short, checked before the database is touched; count printed each build.
  `notes/data-quality.md` "Cases that vanish from the feed"; supersedes the 2026-07-16 finding.
- PR #84 (5 Sep): 37 issued pins / 17 events, 1 paired (unchanged since July), 6 pins accruing, 29
  excluded, 52 lift pins / 27 events with 16 since collection began; issue and lift schemes
  disjoint but one; `IGNORE_BOIL_NOTICES` stays off. `notes/boil-notices.md` "Re-measured
  2026-09-05".
- PR #88 (5 Sep): the reader's case, the prototype's blast radius, the reopen criterion, documented
  and deferred. PR #90 (5 Sep): 216 of 562 Open cases past their own completion (177 of 437
  events); feed closes a median 72 h late, p90 111 h, over 3,783 closed cases; 0 of 7,667
  completions ever followed by a newer update; decided in `resolve_case`, carried on
  `Case.is_open`; scheduled ends still do not close; every published figure byte-identical, open
  events 437 to 260; the convention "a signal trusted for the arithmetic is trusted for the
  display" added to `CLAUDE.md`. `notes/statuspage-methodology.md` "The notice's own completion
  closes it".
- PR #89 (5 Sep): `read_cases` runs the schema check on the downloaded release before its SELECT;
  reproduced against a v3 copy of the 4 Sep release.
- Archive counts measured 12 Sep 2026 against `out/uisce.db` (feed read 9 Sep).
