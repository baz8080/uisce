# 19a. Nine things it could not do
*~10 min read · PRs #76-#82, #85, #87 · 5 September 2026*

*Where we are:* by early September the site had its geography, its arithmetic, its grades and 767
addresses. What it had never had was a list of what it was still missing. This chapter is the
reader-facing half of the day that list was written and worked through; chapter 19b is the half
where the site found out it had been wrong about two things.

## The question that opened this stretch

Every chapter so far has started from a problem that arrived: a number that was wrong, a page that
misread on a phone, a reader's question. That is a good way to build something and a bad way to
notice an absence. A missing feature does not complain.

So the exercise on 5 September was the other kind: survey the repository against what a site like
this ought to be able to do, write the gaps down as nine independent pieces of work, and merge
them in one day. Two of the nine are in chapter 19b because they turned out not to be features at
all. The seven here are.

## What changed

### The page with JavaScript off (PR #76)

The front page is drawn entirely by script, so with JavaScript disabled it was a heading and a
search box. This had been recorded as open in the notes for weeks, needing only a decision about
what to say, and the answer was under everyone's nose since chapter 11: the county pages carry the
same figures statically. There is now a block naming all 26 of them and the directory, generated
at build time from the payload so the list cannot drift from the pages actually written, and
invisible when scripting is on.

### Every open notice, in one place (PR #77)

The tile at the top said "426 notices open right now" and nothing listed them. A reader who wanted
to see them went county by county, twenty-six times.

Every open case was already in the payload, so this is a render with no new bytes: the tile is a
link now, and behind it is one card per county with open notices, most first, each grouped by area
exactly the way the county view already grouped them. That grouping moved into a single function
both lists call, so the two cannot drift apart. Checked against the 4 September release it drew 26
cards, 295 area groups and 426 rows.

### Something that says what is new (PR #78)

The site rebuilds twice a day and nothing on it said what had changed since the last time you
looked. A reader who cares about one county had no way to be told when a notice appeared there.

> **Concept: a feed is the site's own change log.** An Atom feed is a small XML file listing the
> most recent items with their dates, which a reader's own software polls. It costs the site
> nothing at page load - it is a separate static file, no JavaScript, no bytes on the app - and it
> is the one mechanism that lets a reader follow a place without visiting it. The ordering question
> is the interesting part: a notice's publication date is when Uisce Éireann published it, which
> for a backfilled case can be months before this site ever saw it. Ordering a *change* log by
> publication would put a newly discovered old notice where nobody would look. So entries are
> ordered by the build that first saw them, falling back to publication for the cases that predate
> the column recording it.

There is a feed for the country and one for each county, each carrying the newest 50 events. An
entry links to the area page where one exists and the county page otherwise, which is the rule
chapter 17's search hits already follow. Its identifier is keyed by county as well as by reference
number, because 15 references span two counties. Every county and area page advertises its
county's feed in its head, and the overview and county footers link to it in prose. On the 4
September release that is 27 feeds totalling 499 KB.

### The month table an area page never had (PR #79)

An area page, as chapter 17 shipped it, was a notice list. The per-area month figures the app's
county breakdown charts were already in the payload, so the page now carries them as a table:
availability against the area's own population, the four counts, person-hours, one row per month
that had a notice. No grade, for the reason chapter 8b gave: the A to F cuts are calibrated to
county-months, and a village's bad week reads as an F.

### What the notice actually said (PR #80)

Here is an omission that had been there since chapter 1, hiding behind the fact that the site's
whole purpose was to turn notices into numbers. **The site had never shown a reader the words of a
notice.** And the words are what tell you whether your road is in it: "Rosegreen, Coolmoyne,
Derryluskin, Knockbrit, Ardsallagh and surrounding areas".

The full text of the archive is about 7 MB, which is not going on any page. But the open notices
are the ones a reader needs the wording of, and those total about 500 KB spread across 26 static
county pages. Each open row now has a collapsed "What the notice says" under it, with the feed's
HTML reduced to plain paragraphs: the double line breaks become paragraph breaks, every other tag
is stripped, entities are unescaped, and the trailing internal code is dropped. The output is
escaped, so no feed markup reaches the page. Like the history and the feeds, the text is removed
from the payload at build time, and a test asserts it never reaches the app.

Each open row also links its reference number to the notice's own page on the utility's site. Only
a well-formed reference gets the link - three letters and eight digits, after stripping the
trailing space three open cases carry - because the hand-entered codes and the fallback for a
missing reference are not pages there, and a dead link under a live notice is worse than none. On
the 4 September release, 423 links across 26 pages.

### The notices behind a day (PR #81)

Chapter 16 gave each day cell a caption reading "moderate supply disruption". It still did not say
*which* notices. The county's history shard already carried every event with the first day it was
charged; it now carries the last one too, omitted when it is the same day, following the sparse
convention the rest of the record uses.

Tapping a cell in the county view loads that county's shard on first use and lists every event
spanning that day, deduplicated across the areas it was homed to, worst first, each row naming its
area. Cork on 14 August lists 25 notices. Two limits are accepted and recorded: the overview's
bars still only caption, because loading a shard per hovered row is the wrong trade, and a
recurring event matches every day of its span rather than only the nights it ran, because the
shard carries covered hours and a span rather than the windows themselves (chapter 9a).

### What every reader downloads (PR #82)

The largest change of the day is invisible.

> **Concept: the initial payload is what everyone pays for.** The site ships one data file that the
> front page loads before it can draw anything. Every reader downloads all of it, including the
> parts that only exist to serve a view they may never open. By 4 September that file was 955,516
> bytes and the overview - the only thing a first-time visitor sees - read a third of it. The
> methodology note had named 1 MB as the point to split it per county, six months earlier; it was
> at 955 KB and growing linearly in months times areas, so the point had arrived.

#### Worked example: where 955 KB was going

| block | bytes | share | read by |
|---|---|---|---|
| towns | 583,560 | 61% | county view, area view |
| resolved | 164,809 | 17% | county view |
| months | 133,842 | 14% | overview |
| open | 58,212 | 6% | overview count, county view |

The first two rows, 78% of the file, are read only when a reader opens a county. They now go to a
per-county file loaded on entry, the same shape and loader the history shards have used since
chapter 10. The result: **212,116 bytes against 955,516, or 28,640 gzipped against 123,950** (PR
#82, 5 Sep 2026). The largest county's shard is Cork at 69,925 bytes.

Getting there needed two small pieces of denormalisation, and they are the part worth noticing. The
open list and the area view had both been reading the breakdown for one field each: an area's name
in one case, its population and filename in the other. Those fields now ride on the records that
needed them, so the two views stopped depending on a block they otherwise had no use for. And a
clear area-month stopped spelling out its "availability: 100.0", the way every other implied figure
is already omitted, which is 1,218 of 4,833 rows.

The build now prints a size report against a 512 KB budget for the front page plus its data, and
emits a warning on the deploy when it is over. Warned, never failed: a budget that fails the build
is a budget someone raises to make the build pass.

### Two smaller things

The fourteen settlements that share their county's name - Carlow, Sligo, Kildare and the rest -
had been in the search index with their filenames all along, and thirteen have pages, but the
shared search deduplicated hits on name-and-county and the county row won. So the town was
reachable from the directory and nowhere else. The deduplication is keyed on the destination now,
and with two rows surviving this site's label has to tell them apart: the county row is unchanged
and still first, and the town's row says "town" in the slot where every other area hit shows its
county. The dropdown reads "Sligo" and "Sligo town", which is how the two are told apart in speech
(PR #85).

And the nine pull requests left follow-ups in their own descriptions, while the notes had
accumulated re-measurements with triggers, "reopen if" clauses and "noted and not taken" items
across six files. Nothing gathered them, so they were one closed browser tab away from being lost.
They are now in one file, in five groups: queued work, checks needed by hand, decisions waiting on
me, things to re-measure when a condition is met, and things noted and deliberately not taken (PR
#87). Each entry points at the note carrying the reasoning rather than repeating it, which is the
same rule the settled-decisions index follows.

## Where it left the site

By the end of the day a reader without JavaScript has somewhere to go, a reader who wants every
open notice has one page, a reader who follows one county has a feed, a reader on an area page has
its month-by-month record, a reader wondering whether their road is affected can read the notice,
and a reader who taps a bad day can see what made it bad. The front page costs a quarter of what
it did.

Seven features in a day sounds like a lot until you notice what they have in common: not one of
them needed new data. The Atom feeds, the open list, the area month tables, the notice wording and
the day drill-down are all renders of things the archive had been carrying for weeks or months.
What had been missing was not information. It was the decision to show it.

## Notes

- PR #76 (5 Sep 2026): `<noscript>` block naming 26 county pages and the directory, generated from
  the payload. PR #77: tile becomes a route; grouping shared with the county view; 26 cards, 295
  groups, 426 rows on the 4 Sep release.
- PR #78: `feed.xml` plus 26 county feeds, newest 50 events by `first_seen` with publication as the
  fallback; entry links follow the area-page rule; ids keyed by county (15 references span two);
  `<link rel="alternate">` on every county and area page; 27 feeds, 499 KB; `write_site` returns a
  dict of sizes.
- PR #79: month table on 747 area pages from `towns[code].months`, no grade. PR #80: about 7 MB of
  full text archive-wide against ~500 KB for open notices; `notice_paragraphs`; text popped from
  the payload; 423 reference links on the 4 Sep release; closed notices deferred pending a check
  that old references still resolve.
- PR #81: `event_record` gains `end`; shards 2,406,853 to 2,513,470 bytes; Cork on 14 Aug lists 25;
  two accepted limits recorded.
- PR #82: block table; `data.js` 955,516 to 212,116 bytes (123,950 to 28,640 gzipped); Cork shard
  69,925; `name`, `pop` and `slug` denormalised; 1,218 of 4,833 rows lose an implied 100.0;
  `INITIAL_BUDGET` 512 KB, warned never failed; folding the breakdown into the history shard was
  rejected. `notes/frontend-notes.md` "The county's own data left data.js".
- PR #85: 14 county-named settlements, 13 with pages; dedup keyed on the target upstream; "Sligo
  town". PR #87: `notes/roadmap.md`, five groups; closes the uncapped-page measurement at Dublin
  384,115 bytes, Cork 335,599, Kerry 245,632.
