# 16. Stop sounding like the author
*~9 min read · PRs #54–#61 · 25–26 August 2026*

*Where we are:* chapters 14 and 15 covered three days in which the site's look moved into a
layer shared with its two sibling sites and the end-time reading became rules-first. Four days
later came a two-day pass over the words and the look themselves — the last stretch this
account covers.

## The question that opened this stretch

Chapter 10 rewrote the site "for a reader, not an analyst", and I believed it had. Three weeks
on, reading the county page cold — as a neighbour would, not as its author — it still gave the
game away. The "Areas" section opened with a thousand-character paragraph about Census
placement rules. Dates read `2026-08-01`. The word "pin" — this series' own term of art —
appeared in copy, where it is jargon. The footer announced "Generated 2026-08-25 19:41 UTC from
uisce.db", which restates the banner's freshness stamp in a form no reader wanted. And the same
pin-placement rule was explained, in slightly different words, in four different places —
the surest sign that text was written where the author happened to be standing rather than
where the reader is.

Meanwhile the electricity site had pulled ahead on design, and the whole point of chapter 14's
shared layer was that the three sites should converge rather than drift. So this stretch has
two halves: make the water site sound like a person, and make it look like its family.

## What changed

### Words a neighbour would use (PRs #54–#57, 25 August)

The copy pass touched every page. The thousand-character Areas paragraph became one line —
"Select an area…" — with the Census detail behind a "How areas are drawn" disclosure; hard
facts were kept but demoted, not deleted. The word "pin" left reader-facing copy entirely (the
series keeps it; a page cannot stop to define its terms the way a chapter can). The
methodology-flavoured subtitles ("this list does not change with the month you are viewing")
were trimmed or removed, their one useful caveat each moved into the footer's methodology
disclosure. The rule stated four ways became one canonical statement plus links.

#### Worked example: a date a reader already knows

A bar caption had read `2026-08-01: supply disruption…` — ISO 8601, the format engineers
exchange because it sorts. It now reads "Sat 1 Aug: Supply disruption · about 0.1% of the
county", through one formatter used by every caption, incident list, area history, the top ten
and the static county pages, appending the year only when it is not the current one (PR #54,
25 Aug 2026). The day-of-week is the part a reader actually uses — "was that the Saturday we
had no water?" is how people remember outages. Both bar render paths already went through one
`describeCell` function, so the change was made once; chapter 14's consolidation paying out in
a small way.

Two smaller cuts in the same spirit: every reader-facing mention of the exact collection start
date went ("This site started collecting partway through April, so April is a part-month" keeps
the caveat without the date, PR #56); and the footer's generated line became "Source code · not
affiliated with Uisce Éireann" — the timestamp duplicated the banner, "from uisce.db" meant
nothing to anyone, and the repository URL had been plain text you could not tap (PR #57). The
pass also replaced em-dashes with hyphens or commas throughout the site's prose (PR #54). I
write in em-dashes — this series is full of them — but they are a writer's habit, not a
reader's need, and on a phone-width column they read as clutter. The bare "—"
as an empty table cell stayed; that one is a convention readers do know.

### The layer pays forward (PRs #58–#60, 25–26 August)

Chapter 14 stated the sharing rule — a thing goes upstream when at least two sites want it and
none wants it different — and this stretch was the first time the rule ran in the forward
direction, twice in two days.

> **Concept: promoted on the second user.** The date formatter above was written *here*, as
> this site's own helper, because no other site needed it yet. Then the electricity site wanted
> the same friendly dates — and the moment a second user exists, a copy is a liability, so the
> helper moved up into the shared layer and this site deleted its local one and called the
> shared name. What makes this discipline rather than good intentions is a test: the suite
> fails if a page script *redeclares* a name the shared layer provides. Once `fmtDay` exists
> upstream, a local `fmtDay` here is a redeclaration and the build says so. The guard turns
> "we should probably consolidate that" into a step that cannot be skipped — the same
> mechanism, pointed the opposite way from chapter 14's drift problem.

The second promotion was the freshness stamp itself — the "Updated N hours ago" arithmetic from
chapter 15's data clock. It was never water-specific; the electricity site was about to grow a
second copy. It moved upstream parameterised on exactly the two things that differ per site:
the overdue threshold (24 hours here, sized against this site's build schedule) and the sentence
the warning carries. The move was verified the honest way: the shared function was compared
against the local one it replaced for every age from minus two hours to forty days, minute by
minute — identical across all 57,721 of them (PR #59, 26 Aug 2026). And a tidiness PR the next
morning moved the version pin from a pre-merge branch commit onto the layer's main line —
byte-identical content, recorded properly (PR #60). The same PR wrote down, at last, a rule
that had been asked for by hand across four repositories: comments say *why*, never *what* —
which is the definition of a convention that should be written down rather than remembered.

### Look like the family (PR #61, 26 August)

The second day was this site's half of a design-alignment pass across all three sites, against
the shared layer's new pieces. Most of it is the county list and county page taking the
electricity site's shapes: rows with a chevron and a two-line availability figure, both county
lists alphabetical, the county page reordered — legend on top, tall bar, then large tiles — the
banner-duplicating national tiles gone, the footer's hairlines gone, the disclosures rewritten
once more for a lay reader. The sort control went entirely, replaced by the shared "Search a
town or county" box over a build-time index of every Census settlement — about 66 KB, fetched
on the first keystroke and never in the initial payload — so the quiet towns chapter 10's
directory made findable are now findable from the front page too.

Two changes in this pass are decisions rather than styling, and belong in the record.

> **Concept: the bars answer one question.** Chapter 10 moved the boil-water marker *beside*
> the grade, because how much water there was and whether it was safe to drink are independent
> questions. This pass finishes that thought at the level of the day bars: a water-quality
> notice no longer colours a day cell at all. The bars answer "was the supply disrupted?";
> the health marker, the county tiles and the county pages answer "was it safe?". The skip has
> to happen at build time, not in the browser: each day cell is published as a single worst
> severity, and "worst" stops at the first hit — so a day with both a quality notice and a
> restriction must fall through to the restriction *when the cell is computed*, or the
> information is already gone by the time any page script could remap it. One consequence is
> accepted and written down: a quality-only day now counts as a clear day in the counts.

That consequence promptly produced the pass's one review catch. The static county pages
summarised a month as "31 of 31 elapsed days with no notice" — which a standing boil notice
would contradict in the very next sentence: "31 of 31 elapsed days with no notice. 1 active
health notice." The line now says what the scan actually counts: days "clear of supply
disruption" (PR #61, 26 Aug 2026). A sentence that can disagree with its neighbour is wrong
even when the number in it is right.

#### Worked example: the ramp that washed out

The other decision was colour. Day cells had shown *how bad* a day was by opacity — the worse
the day, the more opaque the band. Measured, most real county-days sat at contrast ratios of
about 1.5–1.8 : 1 against the page background, with the two lightest ramp steps at 1.80 and
2.93 (light mode) — below the 3 : 1 that chapter 12's contrast pass had already established as
the floor for meaningful graphics, and washed out beside the electricity site's solid bands.
The ramp became three solid severity tokens, measuring 2.50 / 4.56 / 8.44 : 1 (PR #61;
`notes/frontend-notes.md`). The captions absorbed the meaning the opacity lost: a day now
reads "minor supply disruption" under 0.5% of the county affected, "moderate" under 2%,
"major" above — the same thresholds the opacity had encoded, now in words a caption can carry.

The tests are worth a sentence, because a change like this can silently delete coverage. A
handful of tests had *observed* real behaviour — the boil-notice pairing, the 14-day cap —
through the side-effect of quality days colouring the bars. They were repurposed to assert the
same facts through the health data itself, and a new guard pins the new fact: quality days do
not colour the bars. 443 tests, up from 440.

## Where it left the site

On 26 August the site reads and navigates like its siblings: alphabetical counties, a search
box, chevroned rows, solid severity bands, dates with weekdays, a one-line footer. The words
"pin", "generated" and "uisce.db" appear nowhere a reader looks. Two published numbers moved,
both deliberately and both recorded: clear-day counts now include quality-only days (the health
marker carries them instead), and day-bar colours encode severity class rather than share-of-
county. Nothing in the availability arithmetic — the person-hours, the medians, the grades —
changed at all.

There is a small irony in ending here. This series spent fifteen chapters building a fixed
vocabulary — pin, case, event, footprint — and the site spent this stretch deleting that
vocabulary from its own pages. Both are right. A chapter can afford to define its terms and
then lean on them; a page read once, by someone whose water is off, cannot. The site's job was
never to teach its reader the author's words. It was to answer the question the author started
with, in the reader's own: *was that the Saturday we had no water?*

## Notes

- PR #54 (25 Aug 2026): Areas paragraph → one line + "How areas are drawn" disclosure; "pin"
  removed from copy; `fmtDay`/`_fmt_day` ("Sat 1 Aug", year only when not current); em-dashes →
  hyphens/commas, "—" cell placeholder kept; placement rule stated once; 440 tests. PR #55:
  area-history note and county-footer definitions deleted. PR #56: collection-start date out of
  reader copy. PR #57: footer "Source code · not affiliated with Uisce Éireann".
- PR #58 (25 Aug): statusui `2076735` promotes `fmtDay`/`fmtDate` (esb the second user); local
  copies deleted; `_fmt_day` delegates to `statusui.fmt_date`. PR #59 (26 Aug): `freshness()`
  upstream, parameterised on `STALE_AFTER_H = 24` and the warning sentence; equivalence
  identical across 57,721 ages (−2 h to 40 d); `test_ui_globals` is the forcing guard. PR #60:
  pin onto statusui main (byte-identical); the comment rule ("say why, not what") written down.
- PR #61 (26 Aug): quality notices leave the day bars, skip server-side in the worst-severity
  scan (worst short-circuits); quality-only days count clear, noted; "elapsed days with no
  notice" → "clear of supply disruption"; opacity ramp 1.80/2.93 : 1 → solid tokens
  2.50/4.56/8.44 : 1, most real county-days had measured 1.5–1.8 : 1; captions
  minor < 0.5% / moderate < 2% / major; shared search over `search.js` (~66 KB, first
  keystroke); sort control removed; county card reorder; 443 tests. `notes/frontend-notes.md`
  carries the contrast table. There is no PR #53 (the number resolves to nothing on GitHub — skipped).
