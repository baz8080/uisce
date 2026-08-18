# 13. Closing: what the site can say, and what it cannot
*~10 min read · with a glossary*

*Where we are:* the end of the account, on 18 August 2026, with the repository at pull request
#41. This chapter returns to the question, sets out plainly what the site can and cannot claim,
lists what was learned in the form the repository itself keeps it, and collects every concept
box into a glossary.

## The question, answered as far as it can be

*Are other areas having as many outages as I am?* For Leixlip, in July 2026: no, they were
having fewer. Two supply outages cost the town's 16,733 people 438,691 person-hours — about one
part in twenty-eight of everyone's month — while Naas (26,180 people) and Maynooth (17,259) lost
none, and Kildare as a whole read 99.20%, a D. That was invisible until the site could go below
the county; the county figure averaged it away.

But the honest answer is longer than that, because the site measures a specific thing in a
specific way, and every step of the way carries an assumption or a floor. Here they are,
collected, in the order the chapters met them.

## What the site can say

- **How many notices** were published, where, and of what kind — completely, since 20 April
  2026, because the archive keeps everything the feed forgets (chapter 1).
- **When the utility said the works were done**, read out of the notice text by a local model at
  an accuracy of at least ~97.5% on unseen cases (chapter 5b) — the only end signal that exists.
- **How many people were near each notice**, from the Census, exactly for every settlement and
  to the person for the state (chapters 8a–8b) — under a stated 500 m assumption.
- **A county-month's availability**, as person-hours lost to supply outages over person-hours
  possible, and its letter — comparable month to month because the thresholds are fixed
  (chapters 5a, 12).
- **The same figure for every town, city area and rural parish** that has had a notice, against
  its own population, deliberately harsher than the county's — without a letter (chapter 8b).
- **Which drinking-water notices were in force**, beside the grade rather than inside it
  (chapter 10).
- **What has ever happened in a place**, event by event, listed under every area an event
  reached and charged once (chapter 10).

## What it cannot say, and says so

- **How long the water was actually off.** Every span starts at *publication*, and the feed
  never records onset. Every duration is a floor (chapter 6), and there is no better start
  anywhere in the data (chapter 5b).
- **When a case really closed.** `closed_at` is when a build first *saw* it closed — a floor
  whose real owner is the utility's own bookkeeping, a median 75.7 hours behind the crew
  (chapter 7).
- **That a scheduled end was met.** Plans accrue exposure but are kept out of the median; a
  cheap probe says 69.5% of works finish late (chapter 6). Events with no usable end are charged
  a category median and counted on the page as estimates (chapter 12).
- **Exactly who was affected.** The 500 m circle is an assumption; county *rankings* barely move
  with it, but 48 of 52 county-months change letter across 300 m–1 km. The letters are about
  the assumption (chapter 12).
- **That two overlapping outages did not count the same people twice.** They do, by 2.0% of
  national outage person-hours, left uncorrected because it is pessimistic and smaller than the
  radius error (chapter 12).
- **Anything comparable to a regulator's figure.** Ofwat's 99.999% counts measured minutes at the
  tap for interruptions over three hours; this counts whole published notices for everyone in a
  circle. The two differ by construction (chapter 5a).
- **How bad the current month is.** In-progress months grade harshly — open cases accrue to
  "now" against a part-elapsed denominator, some feed statuses are stale, and freshly downloaded
  cases have not been read yet (chapters 6, 10).

## What was learned, in the form the repository keeps it

Chapter 12 mentioned that a settled-decisions index now lives at the root of the repository,
because the notes had grown past what any single session could reload. It is the project's own
list of "things that were measured, and closed". In plain language:

| The tempting idea | Why it was closed, and where |
|---|---|
| Rescue the broken start dates by taking the earliest one ever recorded | Backward re-stamps would inflate durations with a bogus early start; the first-seen value is kept, the minimum rejected (chapter 6). |
| Use the notice's own "works from 10pm" as the start | It moves the clock *later* for unplanned works and changes nothing for planned ones; publication is the only basis (chapter 5b). |
| Pool scheduled ends into the median | It dragged 17.0 h to 9.3 h; plans and observations are different populations (chapter 6). |
| Leave events with no usable end out of availability | A total has no NULL; leaving them out charges zero. They are charged a category median and counted as estimates (chapter 12). |
| Trust the notice title for severity | The same zone was published as *Conservation* and *Interruption* for the same nightly regime; a repeating window is a restriction whatever the title (chapter 9b). |
| Charge a recurring window as continuous days | Eighteen nights of nine hours is 162 hours, not 385 (chapter 9a). |
| Let a boil-water notice knock the grade | The knock was ~100× the harm on the site's own arithmetic and hid Tipperary's three notices; the marker sits beside the grade (chapter 10). |
| Use the feed's `water_outage` or health flags to filter | `water_outage` is set on 97% of cases; `do_not_drink` is wrong on 9 of 19; category only (chapters 5a, 12). |
| Derive settlements from boundary polygons | 54 villages vanished and Doneraile read 214 people against 857; the CSO's own attribute is exact (chapter 8a). |
| Name places from the feed's `location` string | 3,866 values, one town under three keys, no population; Census geography instead (chapter 8a). |
| Build faster to catch short-lived cases | Past daily, the floor belongs to the utility's 75.7-hour closure lag; twice-daily is for freshness only (chapters 7, 9a). |
| Grade towns A–F | Thresholds are calibrated to county-months; a village burst reads F. Availability, no letter (chapter 8b). |
| Recalibrate the grades after a big definitional change | An 11.8% fall in the national total moved exactly one county-month; the distribution and the total are different measurements (chapter 9b). |
| Correct the overlap double-count | 2.0%, pessimistic, smaller than the radius error, and it would reach into the arithmetic; measured and left (chapter 12). |
| Ask the model to do date arithmetic | Hallucinations and infinite loops; let the model read, keep the sums (chapter 3). |
| Use the faster, smaller model | 40% faster, 61% agreement, and wrong in disqualifying ways (chapter 3). |

Two conventions sit under all of it and are worth naming last. **Decisions go in the notes,
dated, with the rejected alternatives and their numbers** — so a future session, human or
otherwise, engages with the evidence rather than re-deriving it. And **the schema is declared
once, migrations only ever add nullable columns, and anything that rewrites data is a rebuild
that costs the archive** — because the archive is the one thing the feed cannot give back.

## Glossary

Each entry is the concept box it comes from, compressed to a line; the chapter is where the
full box and its worked example live.

- **ArcGIS feed** — a public map layer that returns its underlying records as structured JSON when queried; the source of every notice (1).
- **Reverse geocoding, and the cache** — turning coordinates into an address via a paid web call; answers are cached by rounded coordinate so a lookup is made once (1).
- **Notice, pin, case** — what the utility publishes; where it appears on the map; how the database stores one pin (1).
- **The feed has no memory** — it returns only current notices, with no timestamps of change; the archive is the only history (1).
- **CI as a scheduled clerk** — a machine that runs the same procedure on a timer and files the result publicly; it must fetch last time's result first (2).
- **LLM extraction is structured reading, not writing** — the model fills a fixed form from the text; ask it to do as little as possible (3).
- **Hash-based incremental work** — a fingerprint of the text decides whether a case must be re-read (3).
- **What a test suite buys** — a written contract that makes a change fail in seconds rather than weeks later on the page (4).
- **A title is a category, not a severity** — the title says what the crew is doing, not what a household experiences (4, 9b).
- **Person-hours** — people affected × hours affected; a rectangle whose area is the number (5a).
- **Population-weighted availability** — 100 × (1 − person-hours lost ÷ person-hours possible) for a county-month; fair to large counties (5a).
- **A stratified sample, and why its headline misleads** — rare classes are over-drawn so their error rates are measurable; the total then describes the sample, not the corpus (5b).
- **Replay versus hold-out** — scoring on the rows a fix was reasoned from is a regression filter; only unseen rows estimate accuracy (5b).
- **A floor is not an estimate** — the true value is at least this large; publication starts the clock after onset (6).
- **Why pooling two populations lies** — a median of a mixture lands wherever the sorted midpoint falls, answering neither question (6).
- **Observation time versus event time** — the archive records when it saw a change, and inherits the shape of the build schedule (7).
- **An additive-only migration ladder** — schema steps may only add nullable columns; anything else is a rebuild, and a rebuild costs the archive (7).
- **The Census 2022 Small Area** — the smallest published unit, 18,919 of them summing to 5,149,139; each carries a centroid and the CSO's own labels for county, ED, LEA and settlement (8a).
- **Centroid, not polygon** — a pin affects every Small Area whose centre lies within 500 m; an approximation that is symmetric, cheap and about the right thing (8a).
- **Wrong in ways that reached the page** — a systematic under-count in a denominator inflates the figure silently, where fewest people notice (8a).
- **The three tiers** — settlement; Local Electoral Area for a city over 50,000; "Around ⟨Electoral Division⟩" for the countryside — chosen by the finest official geography whose names arrive usable (8b).
- **Homing by dominant share, charging only what is inside** — a pin is filed under the area holding most of its footprint and that area is charged only the footprint inside it, so area figures sum to ≤ the county's (8b).
- **Pin, case, event** — all pins sharing a reference number are one event; intervals and footprints are unioned, population capped at the county (9a).
- **Recurring windows cover hours, not days** — "nightly 10pm–7am for three weeks" is a list of nightly intervals, not one block (9a).
- **A scheduled repeating window is a restriction, whatever the title** — a managed nightly regime is degraded service, not an outage, and accrues nothing (9b).
- **Review the consequential calls, not a sample** — when few decisions change a number and they can be listed, read them all (9b).
- **The health marker is beside the grade, not inside it** — how much water there was and whether it was safe to drink are independent questions (10).
- **Listed under every area, charged once** — an event appears in the history of every area it reached but its person-hours land once (10).
- **Why a JavaScript-routed static site is invisible** — the fragment after `#` is never sent; one document, whatever the view (11).
- **A median can abstain, a total cannot** — leaving an event out of a total enters zero; missing spans are charged a category median and counted as estimates (12).
- **Censoring, and the check that would have made exclusion dishonest** — Kaplan–Meier and a `closed_at` calibration both say the missing events are shorter, so excluding them from the median is safe (12).
- **Overlap double-counting** — two events over the same Small Area at the same time count its people twice; measured at 2.0% and left (12).
- **The grades are letters about an assumption** — read the A–F as calibrated to 500 m; read county ordering as real (12).

## Notes

- Kildare July 2026 figures: `out/site/data.js` built 18 Aug 2026 14:37Z (chapter 8b).
- The settled-decisions table paraphrases the repository's `CLAUDE.md` index; each row's evidence is in the `notes/` section that row names.
- Concept boxes: 32 across chapters 1–12; this glossary lists each once.
