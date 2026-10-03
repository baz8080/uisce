# 18. The letter with nowhere to sit
*~11 min read · PRs #69-#75 · 29 August - 3 September 2026*

*Where we are:* chapter 17 gave 739 places their own address. This is the quieter week that
followed: one change to a published number, one rule written down where it could be seen, and
three separate cases of a check that could not have failed.

## The question that opened this stretch

The grades have run A, B, C, D, F since chapter 5a, and skipping E is an American habit on an
Irish site. That is a two-minute change if you pick a number for the new cut, and the whole of
this chapter's interesting half is what happened when I tried to pick it.

## What changed

### The obvious cut was wrong (PR #71, 30 August)

The bands widen as they descend: A stops at 99.9, B at 99.75, C at 99.45, D at 99.0. The steps
are 0.15, 0.30, 0.45, so 0.60 continues the arithmetic and puts E's floor at 98.4, which is also
the rounder number. I was ready to ship that until I measured it.

> **Concept: fit the cut to your own tail, not to the pattern above it.** Chapter 12 recorded that
> these thresholds were calibrated to this archive's own distribution rather than imported from a
> regulator, because a water utility's published availability targets are not comparable to what
> this site measures. The same reasoning applies to a new band at the bottom, and it is a stronger
> constraint than a pretty sequence: a cut is only meaningful if the bands either side of it hold
> something. A bottom band nothing ever reaches does not flatter the counties above it. It teaches
> the reader that the scale is mis-set, and quietly discredits the letters that do get used.

#### Worked example: four candidate cuts against 130 county-months

Measured against the database CI published on 29 August, across 130 graded county-months, the
whole F population sits between 98.459% and 98.900%. The record's worst month is 0.54 points below
the D cut and no month has ever been worse. So:

| cut | E | F |
|---|---|---|
| 98.7 | 9 | 2 |
| 98.5 | 10 | 1 |
| 98.4 | 11 | **0** |
| 98.0 | 11 | **0** |

The arithmetically obvious 98.4 empties F entirely, and so does anything below it. 98.5 leaves one
county-month in F, four hundredths below its own cut, which is fragile enough that one rebuild
could move it. 98.7 leaves both bands saying something, and the two it leaves in F are the two
worst county-months on record. The grade mix moves from A 9, B 26, C 53, D 31, F 11 to A 9, B 26,
C 53, D 31, E 9, F 2 (PR #71, 30 Aug 2026).

Every cut from 99.9 down to 99.0 is unmoved, so no county-month graded A to D changes letter. What
the change costs is written down rather than smoothed over: the new band is 0.30 wide where D is
0.45, so the widening progression breaks at the bottom, and the cut is fitted to a young 130-row
archive and will need re-measuring as it grows. The note now also says where to get the database
to re-measure against, because the obvious route does not work from a cloud session where the
ArcGIS feed is unreachable.

One consequence was raised, measured and deliberately left. The banner at the top of the page
counts counties graded F, and that count now excludes the E counties it used to include: two of
the five months now open with "0 counties graded F" while still holding counties in the bottom two
bands. F still means the worst band the site has, and the county rows are immediately below the
banner. Counting E and F together is a one-line change if it is ever reopened, and the per-month
figures are in the note so nobody has to re-derive them.

### A settled decision that got reopened without being read

The new letter needed a chip, and the chip work upstream did something chapter 12's contrast pass
had explicitly rejected. That pass put dark lettering on the B and D chips and turned down the
alternative of darkening the fills so they could carry white text, on the grounds that a D dark
enough would blur into F. The upstream change adopted exactly that alternative.

It was done before the note was read, which is precisely what the settled-decisions convention
exists to prevent, and there is no version of this chapter where that is not worth saying plainly.

The reconciliation is that the reopening turns out to be right, for a reason the original pass
could not have had.

> **Concept: two ways to measure contrast.** WCAG 2.1's contrast ratio is a formula over relative
> luminance, and it is what chapter 12's pass judged on. APCA is a newer model that accounts for
> which of the two colours is the text and which the background, because dark text on a mid-tone
> and light text on the same mid-tone do not read alike to a human eye even when the ratio is
> identical. On APCA, dark ink on the B chip measures Lc 38.6 against white's 69.2, which made B
> the least readable chip on the page under the arrangement the earlier pass had chosen. And the
> original objection does not hold at the value actually picked: D sits at delta-E 20.6 from F and
> 20.2 from E, and no two of the six chips are closer than 20.2.

So the note is amended with the evidence rather than rewritten, and the settled-decisions index
gains the pointer row that section never had, which is part of why it was easy to miss in the
first place. The grade test also grew boundary cases while this was open: it had only ever checked
values in the middle of each band, so an off-by-one on any cut would have passed, and the legend
prints those five numbers to the reader.

### A rule that could not be seen (PR #70, 29 August)

The house style forbids em dashes. That rule had never been in this repository, or in any of the
sibling repositories: it lived in a personal configuration file on my own machine.

Which meant it was invisible to more than half the sessions that worked here. A cloud session
starts from a fresh container that clones the repository and nothing else, so a rule written into
the project travels and a rule written into a personal file does not. The rule was consequently
broken, at length, by every session that ran that way, and the current count is 905 em dashes and
335 en dashes across 45 files: the widest spread of the three sibling sites.

It is stated, not enforced, and the difference is deliberate. A checker in the test suite would
fail on day one, and the only way to make it pass is a re-punctuation of settled notes that nobody
asked for. More importantly, five of those files are recorded evaluation samples, and
re-punctuating a character inside one changes what was sampled - so the rule says, in those words,
that those files are never touched. The rest get fixed on lines someone is already editing.

This series is written in the repository, so the rule binds it from here. Chapter 16 described the
site's own em dashes being replaced with hyphens and noted, in a sentence full of em dashes, that
they are a writer's habit rather than a reader's need. This chapter is the first one written under
the rule, which is as good a demonstration as any that a convention only binds where it can be
read.

### Three checks that could not have failed

The rest of the week is a set of small corrections that share a shape, which is why they are one
section.

> **Concept: a guard that reads a shorter list passes by seeing fewer names.** Since chapter 14 a
> test has forbidden this site's page scripts from redeclaring any name the shared layer provides,
> and it built that list of forbidden names by reading the shared script file. Upstream then split
> the day-caption listener into its own file so a static page could inline just that listener
> instead of the whole app, which took the file the test reads down to about half the bundle. When
> the dependency pin moved, the test would have gone on passing while silently no longer covering
> the name that had moved out. Nothing would have gone red, because the failure mode of a guard
> built from a list is that a shorter list is easier to satisfy. The fix is that the test asks the
> shared package for its names rather than parsing a file, and asserts that the name it knows about
> is in what it got back (PR #69, 29 Aug 2026).

That one took four attempts to get right, and the four attempts are a small essay on knowing when
to stop. The first read a declaration too loosely and would have failed the build over a shared
helper's name appearing inside an array. The second required an equals sign and started missing
declarations that have none. The third counted brackets to handle a multi-line object and counted
brackets inside strings too, so an ordinary table of user-facing captions containing one stray
bracket failed the build. Each attempt traded a narrow miss for a worse false alarm. The version
that shipped is honest about what it can do - one name per declaration, at column zero - and names
the gap it leaves in its own docstring, pointing at the line in this repository that exercises it,
rather than papering over it. Holding the shared bundle to a stricter standard is done upstream by
running it under an actual JavaScript engine, and nothing short of that belonged on this side.

#### Worked example: an error message that named the wrong culprit

On 3 September an inference run died on one case with `Unterminated string starting at: line 1
column 307`, and the summary underneath read "0 cases answered by rules-v1, 0 by gemma".

The case is a 4,448-character boil-water notice. With the model loaded at a 4,096-token context,
the prompt plus the notice came to 4,018 tokens, leaving 78 for the answer, and the model stopped
mid-string with its own reason recorded as "length". The JSON parser then reported an
unterminated string, which reads like the model gave a bad answer rather than like it was cut off
in the middle of a good one. That misdirection is what made it hard to place, especially since
every description over 3,000 characters, up to 5,093, had extracted cleanly under the same prompt
in early August, when the context had been larger (PR #74, 3 Sep 2026).

Two things were wrong and both are the same kind of wrong. The call ignored the model's own
statement that it had run out of room, so it now checks that and raises with the token counts and
the remedy, which means a short context names itself next time. And the run swallowed the failure
whole: no record written, that misleading summary, and an exit code of zero. **A run that
extracted nothing looked identical to a run with nothing to do**, which matters more since
chapter 15 put the rules half of this into every scheduled build, where a green tick over a
dropped case is exactly what nobody would look at. Failures are counted, printed and returned as a
non-zero exit now.

There is a discipline point in that PR worth keeping. The HTML scaffolding in these notices is a
large share of those 4,018 tokens and stripping it would have made the case fit. It was left
alone, because it changes what the model reads, and that is a methodology change to be measured
rather than something folded into a bug fix.

The third is the smallest. Some notice titles arrive as "Mains Repair Works -Meath", with the
space before the dash and none after, and the splitter that turns a title into a category required
the space to be after. Four of the six fixable uncategorised cases from the late-August builds
were that, not a missing rule in the table. The pattern accepts whitespace on either side now,
while still requiring at least one, so "Mains Tie-In" and "Supply Re-direction" stay whole (PR
#75, 3 Sep 2026).

## Where it left the site

The scale runs A to F inclusive, with E at 98.7% and F holding the two worst county-months the
archive has ever recorded. The chips are legible under a model that accounts for which colour is
the ink. The house punctuation rule is somewhere every session can read it. And three checks that
would have passed while not checking now fail when they should.

Two small statusui bumps close the week (PRs #72, #73): the shared freshness line dropped its
"cause" argument after the sibling sites showed a banner reading "collection has stopped" when
collection had not stopped, their site build having been waiting on a cron that fired hours late.
This site's own note was hedged and may well have been accurate, so it was removed as a side
effect of a shared change rather than because it was judged wrong, and the note says so. The
twenty-four-hour threshold and the reasoning behind it are untouched.

## Notes

- PR #71 (30 Aug 2026): 130 graded county-months on the 29 Aug release; F population 98.459% to
  98.900%; the four-cut table; mix A 9 / B 26 / C 53 / D 31 / F 11 to A 9 / B 26 / C 53 / D 31 /
  E 9 / F 2; band 0.30 wide against D's 0.45; banner F count excludes E, two of five months read
  "0 counties graded F", left on the owner's call; APCA Lc 38.6 vs 69.2 on B, delta-E 20.6 / 20.2,
  no two chips closer than 20.2; `TestGrade` boundary cases; 494 tests.
  `notes/statuspage-methodology.md` "The scale grew an E"; `notes/frontend-notes.md` "Contrast pass
  2026-08-18" and its 30 Aug amendment.
- PR #70 (29 Aug): the rule lived only in a user-level file a cloud session never sees; 905 em
  dashes and 335 en dashes across 45 files; stated not enforced; `data/eval/*.csv` never
  re-punctuated.
- PR #69 (29 Aug): the shared script split in two, so the guard's source list halved; asks the
  package for its names now; four attempts at reading a declaration, the gap named in the
  docstring; 492 tests.
- PR #74 (3 Sep): case 243245, 4,448 chars, 4,018 prompt tokens of 4,096, 78 left; 49 descriptions
  over 3,000 chars (max 5,093) had extracted cleanly on 2 Aug; `finish_reason` now checked;
  failures counted and returned as a non-zero exit; HTML deliberately not stripped; 498 tests.
- PR #75 (3 Sep): `\s+[-]\s*|\s*[-]\s+`; "Mains Repair Works -Meath"; `mains_flushing` and
  `hydrant_repair` variants added. PRs #72, #73 (2 Sep): statusui `be56e99`, `freshness()` loses
  its note argument; `STALE_AFTER_H = 24` unchanged.
