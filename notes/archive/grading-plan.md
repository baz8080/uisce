# Grading plan (owner decision 2026-11-23)

**Closed 2026-11-23.** All four sessions are merged (#127, #128, #129 and the notes audit).
The outcomes live in [../statuspage-methodology.md](../statuspage-methodology.md) ("Every
supply notice per 100 km of main") and [../frontend-notes.md](../frontend-notes.md) ("The
area's day bar", "The page counts every supply notice"); the letter it retired is in
[outage-letter.md](outage-letter.md). Kept as it was written.

**Simply put:** the county letter stops counting only unplanned outages and counts every
notice that says supply may be disrupted, planned works included, per 100 km of main. Each
area gets a day bar and no letter. The county stays the unit that is lettered, because it is
the smallest one with a length of main behind it that a reader would recognise. Four PRs;
two questions for the owner, both answered 2026-11-23.

All figures are release 2026-11-22-2154, built with the clock at the data horizon, over the
six months the site saw whole (May to October 2026, 156 county-months). Nothing here is
built yet: statuspage-methodology.md describes the site as it is until each session lands.

## What the review found

**The letter and the bar disagree by construction.** The bar is red when an outage notice
stands anywhere in the county, the "plain uptime" reading rejected in July because Cork came
out at 2% (archive/availability-method.md). The letter is a rate. Today's letters run A 21,
B 71, C 40, D 18, E 3, F 3, and 50 of the 92 A and B months were red on half their days or
more. Dublin's four B months were red on 28 to 31 days each.

**The letter sees about half the notices that warn of a supply disruption.** May to October
holds 12,783 events that are not quality notices: 6,976 outages, 620 restrictions and 5,187
works. The text names a supply disruption in 6,967, 618 and 5,182 of them; every planned
category says "may cause supply disruptions". 847 of the works are "we are investigating
reports of supply disruptions". By `work_type`, 4,356 events are planned on every pin and
8,427 are not. Planned notices outnumber the rest in four counties: Dublin 1,048 to 815,
Galway 352 to 324, Meath 290 to 276, Kildare 181 to 154.

**Kildare is not a bad county on any figure the feed supports.** It is 3rd best on the
current count, 9th on outage hours per 100 km, 11th on red days, 8th on place-days, and 12th
once every supply notice is counted. Its outages sit in three towns: Newbridge, Leixlip and
Celbridge had 23, 23 and 22 outage days of 184, which is typical of towns their size (median
24 for 15,000 to 50,000 people). Its one poor figure is time to "works complete", 21.9h on
single-pin outages against Wexford's 3.6h. Only the retired availability method ranked it
low (22nd), through the 500 m circle that charged dense counties more. Local sentiment is not
measured by anything here, and nothing below is tuned to it.

## What is decided

- **The letter counts every supply notice** (owner, 2026-11-23, option 2). A planned repair
  counts against a county: "repairs are fair game", overdue maintenance being part of what
  the letter should show. CRU and Ofwat count planned and unplanned interruptions together
  (water-sla-benchmarks.md).
- **Areas get a day bar and no letter** (owner, 2026-11-23).

## The count

A supply notice is an event (one `reference_num` in one county) whose worst pin is an
outage, a restriction or works: everything but quality notices, which stay the health
marker's, and lifts. It is dated as today's count is, by its earliest pin's start, so a
planned notice counts in the month its works run: `start_date` on a planned case is the
works' start, a median 90h after the build that first saw it. The denominator, the gate on a
month seen whole and the last-30-days window are unchanged. The median time to "works
complete" and the ten longest stay on outage notices: a planned end is a plan.

The class rule, not a text match, decides: the text agrees on 12,767 of 12,783 and a regex
is one more thing to drift. Planned beside unplanned is `work_type`: an event is planned when
every pin is.

Distribution, notices per 100 km per month: min 0.68 (Carlow May), p10 2.00, p25 2.49,
median 3.20, p75 4.33, p90 5.65, max 11.46 (Kerry July). Nationally 3.59, 3.81, 4.78, 3.86,
4.02, 3.73.

| county | today's rank | new rank | May | Jun | Jul | Aug | Sep | Oct |
|---|---|---|---|---|---|---|---|---|
| Leitrim | 4 | 1 | 0.93 A | 2.80 B | 2.49 B | 1.71 A | 1.95 A | 2.49 B |
| Carlow | 1 | 2 | 0.68 A | 3.25 C | 1.37 A | 2.56 B | 3.59 C | 1.71 A |
| Longford | 13 | 3 | 1.98 A | 2.31 B | 4.21 D | 2.23 B | 2.31 B | 1.65 A |
| Westmeath | 7 | 4 | 2.28 B | 2.28 B | 3.35 C | 1.78 A | 2.92 B | 2.28 B |
| Offaly | 12 | 5 | 1.31 A | 2.18 B | 3.93 C | 3.06 C | 2.01 B | 2.80 B |
| Sligo | 9 | 6 | 3.60 C | 3.01 C | 2.07 B | 2.71 B | 1.95 A | 2.01 B |
| Monaghan | 8 | 7 | 1.54 A | 2.92 B | 2.31 B | 3.54 C | 2.31 B | 2.77 B |
| Cavan | 6 | 8 | 2.30 B | 1.99 A | 3.98 C | 2.45 B | 2.76 B | 2.14 B |
| Wicklow | 5 | 9 | 2.40 B | 2.50 B | 2.98 B | 2.11 B | 4.03 D | 1.92 A |
| Louth | 2 | 10 | 2.46 B | 2.28 B | 3.51 C | 2.52 B | 3.02 C | 2.15 B |
| Roscommon | 10 | 11 | 3.33 C | 2.00 B | 2.66 B | 2.90 B | 3.14 C | 2.52 B |
| Kildare | 3 | 12 | 2.76 B | 3.29 C | 2.76 B | 3.08 C | 3.61 C | 2.28 B |
| Clare | 15 | 13 | 2.76 B | 2.87 B | 3.20 C | 2.76 B | 3.20 C | 2.98 B |
| Laois | 20 | 14 | 1.87 A | 3.09 C | 3.75 C | 4.21 D | 3.28 C | 2.90 B |
| Donegal | 16 | 15 | 3.03 C | 3.96 C | 3.82 C | 2.53 B | 2.94 B | 3.64 C |
| Mayo | 18 | 16 | 4.17 D | 3.88 C | 3.31 C | 3.34 C | 3.27 C | 3.66 C |
| Kilkenny | 17 | 17 | 4.74 D | 3.65 C | 4.01 D | 3.01 C | 3.83 C | 3.19 C |
| Galway | 11 | 18 | 3.00 C | 4.15 D | 3.04 C | 4.22 D | 4.02 D | 4.39 D |
| Limerick | 21 | 19 | 3.17 C | 3.09 C | 4.83 D | 2.77 B | 4.67 D | 4.63 D |
| Tipperary | 22 | 20 | 2.90 B | 4.35 D | 5.71 D | 4.43 D | 4.49 D | 3.47 C |
| Cork | 23 | 21 | 4.76 D | 4.86 D | 5.81 D | 4.26 D | 5.11 D | 4.02 D |
| Dublin | 14 | 22 | 4.33 D | 4.26 D | 5.01 D | 5.74 D | 5.09 D | 5.77 D |
| Wexford | 24 | 23 | 4.93 D | 4.32 D | 7.92 E | 5.54 D | 5.37 D | 4.93 D |
| Waterford | 25 | 24 | 6.49 E | 4.03 D | 10.12 F | 7.77 E | 5.21 D | 4.72 D |
| Meath | 19 | 25 | 7.00 E | 7.77 E | 9.18 F | 5.11 D | 6.16 E | 4.41 D |
| Kerry | 26 | 26 | 5.80 D | 5.65 D | 11.46 F | 6.35 E | 6.10 E | 5.36 D |

Letters above are on the proposed cuts. Over the 30 days to 2026-11-22 Kildare reads 2.86, a
B, where today's page says 0.48, an A.

**Proposed cuts: A below 2, B below 3, C below 4, D below 6, E below 8, F at 8 or more.**
A 15, B 49, C 39, D 42, E 8, F 3; the three F are July in Kerry, Waterford and Meath.
Against today's letters 89 county-months keep theirs, 59 drop and 8 rise. The A and B months
red on half their days fall from 50 of 92 to 28 of 64. The same re-fit rule applies as
before: yearly, dated, and sooner if a band empties.

**Investigations are counted, all of them.** 201 of the 847 have an outage notice within
500 m and 5 days and are probably the same incident published twice. Counting only the
other 646 changes 7 of 156 letters and moves two counties one place, which does not earn a
coordinate heuristic in a published number. Dropping all 847 moves 8 counties, one by 5
places: they are reports of lost supply and they matter.

**Known limits, to say on the page.**

- How works are published moves the count. 1,140 of 4,211 planned events have another
  planned event within 200 m and 14 days (Galway 45%): a week of works published daily is
  several notices, and the same week announced as one repeating window is one.
- A three-hour planned window and a three-day burst each count one. The median beside the
  letter is the only length the site measures, and it covers outages alone.
- The 25 pins with an unmatched title are works by default and now count.
- Everything under "Known limits" in "Outage notices per 100 km of main" still holds.

## The area bar

A day is coloured in an area when a notice listed there covers it: from its first charged
day to its last, by the event's class, worst class winning, quality never colouring. That is
the `from` / `end` each history record already carries and the test the county's day list
already applies, so the bar costs the payload nothing, the app's area view draws it from the
shard it has loaded, and the area page draws it from the records it already prints. Every
coloured day is a notice in the list under it.

Against a bar built from the area's own pins, it is identical on 22,018 of 22,339 coloured
area-days (98.6%) and differs in 118 of 2,290 areas: 211 days where an event's pins elsewhere
ran longer, 108 where the event's class is worse than this area's pin, 2 missing.

The bar is sparse enough to read. Of 5,424 area-months on the 904 areas eligible for a page,
2,659 have no coloured day, 1,216 have one or two and 280 have eleven or more; on outages
alone 3,285 have none.

## The county bar stays

Three replacements were measured and none beat it. It keeps its meaning and gains a caption
that says what red is: an unplanned outage notice stood somewhere in the county that day.

## Sessions

**1. Area bars.** (Built 2026-11-23: frontend-notes.md, "The area's day bar".) PR "Give each area a day bar": one row per month, newest first, in the
app's area view and on `a/<county>/<area>.html`, built from the history records by one rule
on both sides; frontend-notes.md entry and CLAUDE.md row. No published number moves.
Depends on: nothing. Done when: the bar matches one built from the area's own pins on the
98.6% above, and the area page's bytes are recorded before and after.

**Checkpoint A (answered 2026-11-23):** the cuts. Owner: 2 / 3 / 4 / 6 / 8, which leaves
room above the record. Declined: 2 / 3 / 4 / 5 / 6 (even steps; A 15, B 49, C 39, D 28,
E 14, F 11; 70 months drop).

**Checkpoint B (answered 2026-11-23):** the name. The page says "outage notices" for what
the letter counts. Owner: "supply notices", split "unplanned" and "planned", with "outage
notices" kept for what the median and the ten longest read.

**2. The count.** (Built 2026-11-23, beside the outage count so the page is unchanged until session 3: statuspage-methodology.md, "Every supply notice per 100 km of main".) PR "Count every supply notice": the numerator, the planned split in the
payload, `COUNT_CUTS`, the last-30 window; statuspage-methodology.md section with this
note's tables, `TestNoticesPer100km` re-pinned to the new sums. Depends on: A, B. Done
when: Kerry July 11.46, Carlow May 0.68 and the national 3.59 for May reproduce.

**3. The page says the count.** (Built 2026-11-23: frontend-notes.md, "The page counts every supply notice".) PR "The page counts every supply notice", stacked on 2:
tiles, banner, county rows, county pages and their meta descriptions, the method block and
its dated "what changed" entry, the bar's caption, `TestThePagesSayTheCount`. Done when: no
page calls the letter's count "outage notices".

**4. Notes audit.** (Built 2026-11-23. The October frontend entry was amended rather than archived whole: most of it still binds.) The "Only outages are counted" text and the October cuts move to
`notes/archive/` unedited; CLAUDE.md's rows for the count and the page are rewritten; the
roadmap entry closes; this plan is archived.

Not in this plan: zone pages keep counting outage notices and carry no letter; esb and lifts
are untouched.

## Rejected, with the numbers

- **Re-cutting today's count.** 0.75 / 1.5 / 2.25 / 3 / 4 gives A 8, B 50, C 45, D 29, E 18,
  F 6 and leaves Kildare B B B B A A. 0.5 / 1 / 1.5 / 2.5 / 4 gives Kildare C C C C B B and
  2 A in 156, the shape declined at checkpoint B in October. It moves letters, not the order.
- **Another county figure.** Outage hours, red days and place-days per 100 km correlate
  0.84, 0.78 and 0.92 with the count by rank; none reorders the table enough to matter.
- **A letter on time to "works complete".** County medians on single-pin observed outages
  run from Wexford 3.6h to Monaghan 24.7h; 68% of Wexford's close inside 6h against 27% of
  Kildare's. The feed cannot say whether that is repair time or when a region posts its
  update.
- **A letter per supply zone.** 224 of 688 zones have 50 km of main or more, holding 88.5%
  of the main and 82.1% of zoned outage notices, so a floor answers October's objection.
  464 zones would carry no letter, the names are not what people call places, and Kildare's
  zones read 0.70 to 1.31 with one at 2.51.
- **A letter per area.** No length of main exists by area. Outage days track population
  (0.63 with its log; median 2 days under 500 people, 24 for 15,000 to 50,000), and a rate
  per head inverts it: Burnfoot 41.2 notices per 1,000 people, Rathfarnham-Templeogue 0.5.
- **No county letter.** Honest, and it loses the page's one-glance reading.
- **The county bar shaded by places hit.** Of 3,285 red county-days, 929 have one place and
  648 two: the objection that closed the notice ramp on 2026-10-06, unchanged.
- **The county bar graded by day on the letter's cuts.** It cannot contradict the letter,
  but 57% of 4,784 day cells sit within one band of their month's letter: Dublin reads A on
  43 days of 184 and F on 37, which is the weekend.
- **An area bar from the area's own pins.** Exact, 44 KB gzipped across the shards for six
  months, and it would colour days the list under it does not explain.
