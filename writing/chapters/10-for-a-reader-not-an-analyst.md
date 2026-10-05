# 10. For a reader, not an analyst
*~9 min read · PR #31 (last commit), PRs #32–#36 · 2–6 August 2026*

*Where we are:* the numbers are, for the first time, mostly right (chapters 9a–9b). The page
carrying them was written the way the methodology notes are written — every figure qualified in
the breath it was given, the database's nouns on the screen, half the explanation hidden in
tooltips that do not exist on a phone. This chapter is the stretch where the site remembered
who it was for: a person who wants to know whether their town's water has been alright.

## The question that opened this stretch

Three questions, really, in the order they arrived. What does a boil-water notice have to do
with an availability grade? What has *ever* happened where I live, not just this month? And —
from reading the page on a phone as a stranger would — what does any of this mean?

## What changed

### A health notice beside the grade, not inside it (PR #31, 2 Aug)

Since chapter 5a, an active boil-water, do-not-drink or do-not-consume notice had *knocked* a
county's letter down one step (D and F staying F). It was measured before it was removed, and
the measurement is the argument. Across the 78 settled county-months the knock set the published
letter for eight, and it was wildly out of scale with everything else on the page:

| county | month | grade | notice reached | for | it would have cost | the band it crossed |
|---|---|---|---|---|---|---|
| Cork | Jul | D→F | 142 people | 336 h | 0.011 pp | 0.45 pp |
| Dublin | Jul | C→D | 5,374 | 24 h | 0.012 pp | 0.45 pp |
| Donegal | Jul | D→F | 204 | 7 h | 0.001 pp | 0.45 pp |
| Kildare | Jul | D→F | 359 | 2 h | 0.000 pp | 0.45 pp |
| Monaghan | Jul | B→C | 190 | <1 h | 0.000 pp | 0.30 pp |

"It would have cost" is what the notice would take off availability if it accrued like an
outage. The median ratio was **0.01** — the knock was about a hundred times the harm it
represented on the site's own arithmetic — and it was *uniform*: 190 people for under an hour
cost exactly what 5,374 people for a day cost. Worse, it destroyed information: a knock cannot
move an F, so a county already at F showed nothing — **Tipperary's July had three active health
notices and displayed no sign of any of them.** And by the time it was removed, the knock was the
*only* reason for Donegal's July F.

> **Concept: the health marker is beside the grade, not inside it.** *How much water was there*
> and *was it safe to drink* are independent questions, and one letter cannot answer both. The
> A–F now means supply availability and nothing else; an active health notice is a separate
> marker next to it, counted over the months a notice was in force. That is not a claim that a
> boil notice is unimportant — it is the claim that its importance is not measured in
> person-hours, and so should not be expressed by moving a person-hours score. Grade mix across
> the 78 county-months: A2 B16 C31 D19 F10 → A2 B17 C34 D18 F7. The marker now shows on ten
> county-months where the knock had touched eight.

### What has ever happened where I live (PR #32, 5 Aug)

Every county broke down into named areas with per-month counts (chapter 8b), but none of those
was a page. PR #32 made each one a list of the individual notices behind the numbers — every
event ever published there, newest first — and added a directory of all **1,836** areas that had
ever had one (roughly 1,900 named areas with no notice at all are left out; a page of them would
say nothing). Not paginated: 1,836 rows render instantly, and paging would break the Ctrl+F that
makes a list this long usable.

The design constraint was the payload. All 7,525 events serialised is 1.8 MB, more than twice the
main data file. So the history is not in the page: it is written as one file per county, and the
page injects a script for a county only when a reader opens an area in it — an injected
`<script>`, not `fetch`, because the site has to keep working opened straight off a disk. Median
county 5 KB compressed; Dublin worst at 23 KB.

Two records deliberately say less than they could. An event that closed without ever reporting
an end publishes **no duration at all** — those carry chapter 6's token one-second footprint, so a
number would print `0.0h` for **801 events**, a measurement nobody made. And a recurring event
publishes the hours *inside* its windows with the series' span beside it — *63 h of works across
seven nights inside a 153 h series* — never the span alone, which would restate the bug chapter
9a exists to fix.

Building it uncovered a real inconsistency, and its resolution is worth a box because it looks
like double-counting and is not.

> **Concept: an event is *listed* under every area it reached, and *charged* once.** The county
> breakdown homes each *pin* (chapter 8b), so a burst published as pins in Naas and in Sallins
> puts counts and person-hours on both rows. The history had named each *event* once, over its
> whole footprint, and listed it only there — so **220 of the 1,830 areas** in the county tables
> had no history at all, their pages saying no notice had ever been published directly under a
> row that had just counted one. The fix lists an event under every area its pins were homed to.
> 764 events are multi-area; the duplicated records compress to almost nothing — the honest
> version costs **6 KB** gzipped across the whole site — and each record carries its `areas` so
> a reader who meets the same burst twice is told why. What is *charged* is untouched: an event
> still has one name (for the open list and the top ten) and its person-hours land once on the
> county. Listing and accounting are different questions.

A payload-diff against a fixed clock confirmed the whole effect on published figures was three
fields on one June row. Fifteen events (0.2%) turned out to have closed *before* their announced
start — a notice for works on 8 August that stopped being listed on 31 July; "closed" implies
works that finished, so those now render as *withdrawn*.

### Three figures that were wrong, and a page rewritten (PR #34, 6 Aug)

The rewrite began as copy and found bugs. **`clear_days` counted days that hadn't happened.**
Future days carry an empty severity, and the count treated empty as clear.

**Worked example: Cavan, 6 August 2026.** August had six days so far, four of them with a
notice. The page said **27 of 31 clear days** — the 25 days that had not yet occurred, plus the
two genuinely clear ones. It was the only figure on the site that overstated rather than
understated. The fix emits `days_elapsed` beside `clear_days`, using the same is-this-day-in-the-
past test the day bar already applied, and the page reads **3 of 6 clear days so far** — with a
test that `clear_days` can never exceed `days_elapsed`.

The other two: no pluralisation on the county view ("1 supply disruptions"); and **`100.00%`
printed beside a real disruption** — two decimals guarantee it whenever a small event hits a
large county, and Cavan showed 100.00% next to *1 supply disruption (114 person-hours)*. The
*display* now clamps to 99.99% whenever person-time was actually lost; a genuine zero still shows
100.00%.

Then the copy. The 2,600-character methodology paragraph — nine topics, 12.5 px, muted grey —
became seven named sections behind a disclosure, with the A–F thresholds drawn as a key rather
than buried mid-sentence. The database's nouns left the page: *case*, *pin*, *event*, *the feed*
became *notice* and *incident*; *floor* became *minimum*; *person-time* became *people's time*;
*Pinned outside the county* became *Couldn't be placed in a town*. Content that existed only on
hover — the health mark, the day bar, the availability meter, five column headers — got visible
form: a pill (*"3 drinking-water notices in effect"*), a tap-to-read caption, sub-labels on the
two most-misread headers (*people × hours*; *vs this area's own population*). Counties moved above
the national tiles, so on a phone the first county row went from ~1,600 px down to the first
screen. County rows became real links, reachable by keyboard. The directory got a search box,
because 1,836 areas behind a county jump-nav were not findable by anyone unsure which county
their townland is in — exactly the reader the rural *Around …* rows exist for.

One small design argument is worth keeping. The banner said *data to 2026-08-05 22:07 UTC*,
which asked every visitor to do timezone arithmetic to answer "is this current?" — and a dead
build looked identical to a fresh one. It became relative (*updated 3 hours ago*), holding one
unit to 24 h and then saying, in red, that the build may have failed. The problem was never that
17 is a large number; it is that a large number from a healthy schedule is indistinguishable
from a build that died, and a friendlier word does not separate those. An explicit overdue signal
does — and its absence then does the reassuring at no cost. (A first pass tried calendar words —
"earlier today" — and simulation against the real cron showed that branch was unreachable: by
the time the 11:20 build is twelve hours old the 17:23 one has replaced it. One monotonic ladder,
like every relative-time library.)

Nothing was softened. Every caveat is still on the page — layered behind a disclosure rather
than deleted — and the load-bearing word *announced* stayed.

### The regression, and three chores (PRs #33, #35, #36)

The rewrite added `#overview { display: flex }` under 640 px to reorder the front page on phones.
Views are switched by toggling the `hidden` attribute, which browsers implement as a plain
`display: none` — and *any* author `display` outranks it. So on a phone the overview never went
away: tapping a county rendered the county page *below* a still-visible overview and scrolled to
the top of the wrong one. Measured at 375 px: `overviewHidden: true, overviewDisplay: "flex",
countyViewTop: 3988`. One rule fixed it, guarding the attribute rather than the id:
`[hidden] { display: none !important; }` (PR #36). The chores: the health mark's `!` centred in
the legend (#33), and the GitHub Actions versions bumped (#35).

## Where it left the site

A page a stranger could read on a phone: plain nouns, visible explanations, a health marker that
means one thing and a grade that means another, a history for every place that has ever had a
notice, a directory you can search, and a banner that says when to worry. Three figures fixed
that had been quietly wrong. What it still could not do was be *found*: everything a reader might
search for lived behind a `#` in the address bar. Chapter 11.

## Notes

- PR #31 last commit (2 Aug 2026), "Publish a health notice beside the grade instead of inside
  it"; `notes/statuspage-methodology.md` "The health notice was unbundled from the grade" (table
  above; 8 of 78; ratio 0.01; Tipperary; A2 B16 C31 D19 F10 → A2 B17 C34 D18 F7; marker on 10).
- PR #32 (5 Aug): 1,836 areas; ~1,900 without notices omitted; 7,525 events / 1.8 MB; shards
  `h/<county>.js` 1,846,326 raw / 200,924 gz, median 5 KB gz, Dublin 23 KB; `data.js` unchanged
  691,493 / 90,162; 801 events would print 0.0 h; 64 open no-signal events capped; 220 of 1,830
  → 1,830 of 1,830; 764 multi-area; 183 → 189 KB gz; 15 withdrawn (0.2%); 128 of 7,525 UNPLACED;
  318 tests.
- PR #34 (6 Aug): Cavan 27/31 → 3/6; 100.00% clamp to 99.99%; 2,600-char paragraph → seven
  sections; vocabulary table; ~1,600 px → first screen; freshness ladder; 322 tests. PR #36 (6
  Aug): `[hidden]` vs `display:flex`, measured at 375 px. PRs #33, #35: chores.
- `notes/frontend-notes.md` (short) for the front-end conventions.
