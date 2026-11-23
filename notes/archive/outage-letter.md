# The outage letter (retired 2026-11-23)

**Simply put:** from 6 October to 23 November 2026 a county's letter counted outage notices
alone, per 100 km of water main, cut at 1 to 5. It now counts every notice that warns of a
supply disruption, planned works included, cut at 2 to 8. These sections are kept as they
were written, for the record. Nothing in them describes a letter the site still publishes.
The live method is [../statuspage-methodology.md](../statuspage-methodology.md), "Every
supply notice per 100 km of main", and the review that retired this one is
[grading-plan.md](grading-plan.md).

What still holds is restated in the live note: the outage count itself, which the median and
the ten longest are taken over, the gate on a month seen whole, the last-30-days window and
the known limits. Sections below are moved in their original order, unedited except that
links to sibling notes now point one directory up.

## From "Severity classes"

Only the **outage** class is counted in the letter and the median. This is deliberate: an F should mean supply was lost, not that a county ran many investigations. No feed flag can do this job: `water_outage` is set on 97% of all cases, and the two health flags carry nothing the category does not (2026-08-18).

## Grades

**Simply put:** a county's letter for a month is the number of outage notices published per 100 km of its water main: fewer than one is an A, five or more an F. The cuts are fixed whole numbers, so a B means the same thing every month.

The letter is cut on the count metric below ("Outage notices per 100 km of main"): **A below 1, B below 2, C below 3, D below 4, E below 5, F at 5 or more**, and nothing else. Until 2026-10-06 it was cut on population-weighted availability; that scale, its E band and the sensitivity checks that retired it are in [archive/availability-method.md](availability-method.md).

## Outage notices per 100 km of main (2026-10-06)

**Simply put:** each county-month carries how many outage notices were published per 100 km of the county's water main, and a letter cut on that count. The median time to "works complete" sits beside it, unchanged.

**The numerator.** An outage notice is an event (one `reference_num` in one county, pins grouped as `event_meta` groups them) whose worst pin classifies as `outage`: a hard-supply category or an unplanned repair, not a repeating window (a restriction whatever its title), not a quality, conservation or pressure notice, not a lift. It is placed in the county the feed put it in, and dated by its earliest pin's publication (`first_pub`, the pinned start for a re-stamped case), which is the same reading the completion median uses for "started this month". A month counts only the part of it the site has seen: nothing before `COLLECTION_START`, and a notice dated ahead of the build waits for its day. The denominator is `wsz.county_mains_km` ("Mains length per county" above). On release 2026-10-06-2104, May to September, that is 5,869 events, and it reproduces to the decimal the figures first measured in a scratch probe with shapely ([archive/availability-method.md](availability-method.md), "Supply zones as a limit on the circle"): Carlow 4.4, Louth 4.7, Leitrim 4.8, Dublin 8.7, Wexford 17.0, Waterford 20.8 (20.7 before the payload's two-decimal rounding), Kerry 23.8. Any-pin-outage and worst-pin-outage give the same set; all-pins-outage drops 26 events and moves Kerry to 23.7, so the worst-pin rule the top ten already uses is kept. `tests/test_site.py`, `TestNoticesPer100km`, builds that many notices on a fixture against the committed mains table and asserts the two headline sums.

**Simply put:** a month gets its letter only once it is over. Until then the page shows the letter for the last 30 days, which always rests on a full month of notices. Scaling a part month up was tried first: one notice on the 1st of the month gave Carlow an F.

**The month in progress is graded on the last 30 days** (owner, 2026-10-06). A month the site saw whole gets its rate and letter; any other (the month in progress, and April 2026, seen from the 20th) carries only `outage_notices`, its count so far, with `per_100km` and `count_grade` null. Each county carries `last_30` (count, rate, letter over the 30 days to the build) and the site carries the national `last_30` (count and rate), for every surface that says "now". The first version scaled the part-month count to the month's length; one notice in Carlow on the 1st read 5.1, an F. Measured on May to September, a part-month letter matches the month-end one in 53 of 130 county-months at day 3, 50 at day 5, 73 at day 7 and 71 at day 10, so a minimum-days gate like esb's stops the day-1 F but leaves a coin flip. An "above, about or below its usual pace" trend did no better (46 of 130 at day 5, 12 pointing the wrong way). The rolling window always rests on a full month of notices; its costs are that it lags (a burst stays in it for 30 days) and that it can change between builds with nothing new published, which the label carries. It is graded on the calendar-month cuts, so it reads about 1.5% more leniently than an average month (30 days against 30.4) and can sit a letter apart from the month just finished at a cut; not corrected, because a rate per 30 days is what a reader takes "a month" to mean. The window is gated as a month is, lettered only once it lies wholly from `COLLECTION_START` on. Both the window and the 'seen whole' test run to the last feed read (`data_as_of`), not the build clock: a UI deploy on a stale release would otherwise count the unread days as quiet ones. History stays on calendar months: they do not overlap, so they compare and sum, and the cuts were fitted on them.

**The distribution** over the 130 finished county-months, notices per 100 km per month:

| min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| 0.17 (Carlow May) | 0.92 | 1.24 | 1.76 | 2.50 | 3.38 | 7.20 (Kerry July) |

Nationally May 1.87, June 2.03, July 2.69, August 2.11, September 2.21.

| county | km | May | Jun | Jul | Aug | Sep | notices | per 100 km |
|---|---|---|---|---|---|---|---|---|
| Carlow | 585 | 0.17 A | 0.68 A | 0.51 A | 1.20 B | 1.88 B | 26 | 4.4 |
| Louth | 1,625 | 0.80 A | 0.80 A | 1.66 B | 0.86 A | 0.62 A | 77 | 4.7 |
| Leitrim | 1,285 | 0.23 A | 1.40 B | 1.17 B | 1.17 B | 0.78 A | 61 | 4.8 |
| Kildare | 1,886 | 1.38 B | 1.06 B | 1.06 B | 1.01 B | 0.74 A | 99 | 5.2 |
| Cavan | 653 | 1.07 B | 1.07 B | 1.38 B | 1.23 B | 0.92 A | 37 | 5.7 |
| Wicklow | 1,042 | 0.96 A | 1.06 B | 1.15 B | 0.86 A | 2.02 C | 63 | 6.0 |
| Westmeath | 1,402 | 1.28 B | 1.21 B | 1.50 B | 0.57 A | 1.50 B | 85 | 6.1 |
| Monaghan | 650 | 0.92 A | 1.39 B | 1.54 B | 2.31 C | 1.08 B | 47 | 7.2 |
| Galway | 2,963 | 1.05 B | 1.55 B | 1.28 B | 1.49 B | 1.92 B | 216 | 7.3 |
| Sligo | 1,695 | 1.89 B | 1.48 B | 1.48 B | 1.83 B | 0.89 A | 128 | 7.6 |
| Roscommon | 2,102 | 1.38 B | 1.38 B | 1.71 B | 1.52 B | 1.76 B | 163 | 7.8 |
| Offaly | 1,145 | 0.96 A | 1.75 B | 2.53 C | 1.92 B | 0.96 A | 93 | 8.1 |
| Dublin | 6,170 | 1.56 B | 1.43 B | 1.82 B | 1.82 B | 2.04 C | 534 | 8.7 |
| Longford | 1,213 | 1.57 B | 1.65 B | 2.97 C | 1.57 B | 1.40 B | 111 | 9.2 |
| Clare | 1,811 | 1.71 B | 1.60 B | 2.21 C | 1.77 B | 2.32 C | 174 | 9.6 |
| Donegal | 4,418 | 1.58 B | 2.56 C | 2.51 C | 1.49 B | 1.90 B | 444 | 10.0 |
| Kilkenny | 1,097 | 2.37 C | 2.28 C | 2.01 C | 2.37 C | 1.82 B | 119 | 10.8 |
| Mayo | 2,784 | 2.05 C | 2.12 C | 2.26 C | 2.34 C | 2.26 C | 307 | 11.0 |
| Limerick | 2,527 | 2.14 C | 1.98 B | 2.93 C | 1.70 B | 2.85 C | 293 | 11.6 |
| Meath | 1,428 | 2.31 C | 2.52 C | 3.01 D | 1.68 B | 2.38 C | 170 | 11.9 |
| Laois | 1,068 | 0.94 A | 2.06 C | 3.00 D | 3.65 D | 2.62 C | 131 | 12.3 |
| Tipperary | 3,519 | 2.13 C | 3.01 D | 3.61 D | 2.84 C | 3.35 D | 526 | 14.9 |
| Cork | 5,144 | 2.90 C | 3.05 D | 3.81 D | 2.66 C | 3.11 D | 799 | 15.5 |
| Wexford | 1,807 | 3.38 D | 2.27 C | 4.71 E | 3.43 D | 3.21 D | 307 | 17.0 |
| Waterford | 1,017 | 3.74 D | 2.75 C | 6.49 F | 5.31 F | 2.46 C | 211 | 20.8 |
| Kerry | 2,723 | 3.64 D | 3.67 D | 7.20 F | 4.77 E | 4.52 E | 648 | 23.8 |

**The cuts are whole numbers: A below 1, B below 2, C below 3, D below 4, E below 5, F at 5 or more** (`COUNT_CUTS`, `count_grade`). The scale reads in its own unit, "fewer than one outage notice per 100 km of main a month is an A", which the availability cuts never could. The letter is cut on the two-decimal figure the payload carries, so a rate that rounds onto a cut takes the letter the page shows: Laois July, 32 notices on 1,068 km, is 2.996, published as 3.00 and a D. Every band holds something on May to September, A 19, B 57, C 33, D 15, E 3, F 3; the three F are Kerry July 7.20, Waterford July 6.49 and Waterford August 5.31, the three E Kerry August and September and Wexford July. By month: May A 7 B 10 C 6 D 3, June A 2 B 14 C 7 D 3, July A 1 B 11 C 7 D 4 E 1 F 2, August A 3 B 14 C 5 D 2 E 1 F 1, September A 6 B 8 C 8 D 3 E 1. The median county-month (1.76) is a B where the availability scale put it at C: the count is not a re-labelling of the old letter, and the two agree on 28 of the 130 county-months, which is the point of the change rather than a defect of it. A fixed scale has to leave room above the record for a winter the archive has not seen; the two bands above the May-Sep p90 are that room.

**Rejected: cuts shaped to the archive's percentiles**, 0.5 / 1 / 2 / 3 / 5, which reproduce the availability scale's shape (A at the top 3%, the median at C): A 2, B 17, C 57, D 33, E 18, F 3. Two A in 130 is the empty-band problem the availability scale's E band was fitted to avoid (archive/availability-method.md, "The scale grew an E"), met from the other end, and shaping the cuts to the dataset is the ranking the owner declined at checkpoint B wearing fixed numbers. **Rejected: archive quantiles** (checkpoint B, owner answer 2026-10-06, fixed). Sextiles on May to September fall at 1.06 / 1.48 / 1.76 / 2.26 / 2.95, none of them a number a reader can hold; they fill every band by construction, 22 a letter; a fit on May to July alone (1.06 / 1.40 / 1.69 / 2.23 / 2.97) already moves 6 of those 78 letters against the May to September fit, so published letters would move every build; and they differ from the whole-number cuts on 86 of 130 county-months, which is the dataset-shape argument above in another form.

**Re-fit yearly**, first in October 2027 against the release DB, and sooner if a band holds nothing over a full year of months or the national rate leaves 1.5 to 3. The record to beat is the table above. Raising a cut moves published letters, so the re-fit is a dated section here, not a quiet constant change.

**Known limits.**

- The count ignores size: a village burst and a city trunk main each count one. The page says so (session 3); the median time to completion beside it is the only size the site can measure.
- Zones cross county lines, and a notice is placed by pin while its main is counted by zone authority. Measured on the 2026-10-06 release with the zone boundaries fetched into a scratch probe (nothing committed) for Louth, Meath and their neighbours, May to September cases: 69 of Meath's 592 pins (11.7%) fall in Louth's "South Louth & East Meath" zone (693 km) and 4 in Fingal Zone 1; 0 of Louth's 298 fall in a Meath zone; 14 Louth and 38 Meath pins are in no zone. So Meath's 1,428 km serves fewer of its notices than the count assumes and Louth's 1,625 km more: Meath reads high and Louth low, by at most that twelfth. Nothing else in the layer's attributes can say how much of a zone's main is over the line; session 6 brings the polygons in.
- A county of 585 km (Carlow) moves 0.17 per notice, so one notice is a sixth of a band; Dublin's 6,170 km moves 0.016. The coarseness is in the small counties, where it is also the honest resolution of the data.
- The feed's `county` is the notice's claim, not the pin's; "Known limitation: pins outside the county they claim" above applies here as to everything placed by county.

## From frontend-notes.md

The opening and the first two entries of "The page counts notices - 2026-10-06". The rest of
that entry still binds and stays in [../frontend-notes.md](../frontend-notes.md), which
restates these two in the names the payload now uses.

### The page counts notices - 2026-10-06 (opening)

**Simply put:** every page now shows the count of outage notices per 100 km of water main,
its letter and the typical time to "works complete", and nothing from the population
estimate. Session 3 of [simplification-plan.md](simplification-plan.md); the arithmetic is
statuspage-methodology.md, "Outage notices per 100 km of main".

- **Letters and rates.** A finished month shows its own `count_grade` and `per_100km`. The
  newest month, which has no rate until the site has seen it whole, shows the county's
  `last_30` and says "last 30 days" wherever it does. April 2026 has neither and gets the
  shared `g-none` chip with a hyphen; the banner drops its "graded F" clause and the basis
  line says why there are no letters, rather than "0 counties graded F" of a month nobody
  was graded on.
  Inside collection's first 30 days `last_30` carries its count alone (#115 gated the
  window as a month is gated); the app shows the hyphen chip and the county page says
  "too soon for a rate".
- **The outage count beside a rate is the one the rate divides**: `outage_notices` (events
  by first publication), not `events.outage` (events active in the month), and on the
  newest month the overview row's count is `last_30`'s, labelled "30 days". The county
  view's tiles keep the month's count beside the 30-day rate, each labelled. The bars, the
  area breakdown and the quality and works tiles keep the active-in-month counts.
