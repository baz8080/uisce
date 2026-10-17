# 17. A page for every place
*~11 min read · PRs #62-#66, #68 · 26-27 August 2026*

*Where we are:* chapter 11 gave the site 28 addresses a search engine could find, one per county
plus the directory. Chapter 16 made the words on them plainer. This chapter is about the other
1,960 places the site knows and could not point at.

## The question that opened this stretch

Chapter 11's argument was that a hash route is not a URL: everything after the `#` is never sent
to the server, so a site whose views live behind fragments is one document as far as a crawler is
concerned. The fix then was county pages. It left the long tail untouched.

Watch what a reader does. They open the county, they find their own town in the table, they click
it, and the site shows them Abbeydorney's history. Then they go to copy the address and there
isn't one worth keeping. The affordance they had at county level quietly disappears one click
further in, which is exactly one click past the point where a shareable link starts being worth
something: there are 26 counties and 1,960 areas that have had a notice.

Two days in late August closed that, and in the process forced three small decisions that were
more interesting than the feature.

## What changed

### First the link, then the href behind it (PR #62, 26 August)

The county page already existed and the way in was a paragraph in the footer, visible only in the
county view. Nothing gets clicked in a footer. It moved to its own line directly under the county
heading, which is where the two sibling sites put theirs.

The bigger hole was underneath. Each row in the overview list pointed at `#county/Carlow`, a
fragment, so a crawler following it reached nothing, a middle-click opened nothing and "copy link
address" copied a fragment. The sibling sites point theirs at the static page and suppress the
click, so the page is reachable by every route except a plain click, which stays in the app. This
site's rows do that now.

Then the label on the new link turned out to be a lie, and the shape of the lie is the useful
part.

#### Worked example: a link that promised what the page would not show

It shipped as "Every notice ever recorded in Co. Carlow", carried over from the footer copy it
replaced without being checked. But the page capped its list at 60 notices and printed its own "N
older notices not shown here" line, so any county past 60 had a link making a promise the page it
landed on then denied (PR #62, 26 Aug 2026). What the page genuinely holds that the view does not
is *every month*: the view is one month of bars and tables, the page has a row per month since
collection began. So the link says months. A test now pins the accuracy rather than the wording:
the label may claim the months, and may not claim every notice.

The same shape turned up in the page's search-result description a few lines later, and the fix
there is about word order. A snippet is cut to fit a pixel width, so what survives is the front of
it. The description now states the county's record first and names what the page holds last: cut
it anywhere and what remains is a true statement about Carlow rather than a claim about a listing.

### 739 pages, and the argument about which (PR #63, 26 August)

> **Concept: thin content at scale.** A search engine's problem is not that a page is short. It is
> a thousand near-identical short pages, which is a pattern it demotes, and the demotion lands on
> the whole site rather than on the offending pages. So "give every area a page" needed a
> predicate. Of the 1,960 areas that have had a notice, 697 are Census settlements and 42 are city
> Local Electoral Areas: those are addresses, and they got pages. 1,193 are Electoral Divisions,
> and every one of the 2,808 in the CSO file is named *Around* somewhere (chapter 8b) - countryside
> around a place rather than a place, and not a thing anyone types into a search box. Five are a
> city's leftover bucket, named *Elsewhere in Cork city*. Twenty-three are pins that could not be
> homed at all. None of those three is an address, so none gets a page.

That produced 739 pages at `a/<county>/<area>.html`, and took the site from 28 indexable URLs to
767. What it deliberately does *not* have is a floor on top. A minimum of two notices would have
dropped 122 pages, and it would mean a URL appears the day an area's second notice arrives. A
permalink that comes and goes is worse than a short one, and a page reading "one notice, this
date, four hours, about 500 people" is a real answer about a real place. The distribution is a
median of 5 notices per page, a mean of 9.0, and a maximum of 83 at Dún Laoghaire (PR #63).

#### Worked example: the fada that would have 404ed twenty places

The obvious way to link an area from the app is to derive its filename in the browser: take the
name, lowercase it, replace anything odd with a dash. The site has two such functions, one in
Python for writing the files and one in JavaScript for the app, and statusui's own test says they
are deliberately unpaired. The JavaScript one leaves a fada as a dash: `Dún Laoghaire` becomes
`d-n-laoghaire` where the file on disk is `dun-laoghaire`. Seventeen names carry a fada and three
more carry punctuation the two treat differently, so deriving the link in the browser would have
produced a dead link for twenty places (PR #63, 26 Aug 2026).

So the filename ships in the data instead. It is present exactly when a page was written, which
makes it the flag as well as the value: if there is a slug, there is a page. That turns out to
matter a day later.

The path is keyed on county-and-name rather than on the notice's own area code, because a code is
not a filename (31 contain a slash, most contain colons) and a name alone is not unique, repeating
185 times across counties. The pair is unique across all 3,717 areas, asserted in a test rather
than assumed.

The label on the app's link to the page says "Permanent link to Abbeydorney", naming the address
rather than the content, because unlike the county page this one holds nothing the view does not.
The site is now on both sides of its own rule, correctly: the county link names the months, the
area link names the address.

**What it costs.** 739 pages, about 15.1 MB raw and 4.58 MB gzipped, which nobody downloads: a
reader landing on one from a search result fetches exactly one file, measured at about 6.2 KB
gzipped. The cost every front-page visitor pays whether they ever open an area or not is the
filenames in the payload, 4,517 bytes gzipped, a 4.4% increase (PR #63). Eighty-four per cent of a
small area page is the CSS inlined into it, which is the trade chapter 14's build-time assembly
makes on purpose, and these cold-entry pages are what justifies it.

### The control nobody had rewired (PRs #65, #66, 27 August)

The pages shipped on the 26th. On the 27th, typing "Abbeydorney" into the search box and clicking
the hit still landed you on Co. Kerry, to find Abbeydorney again yourself.

That was not a routing choice. The shared search returned each hit as a name and a county and
discarded the matched name, so going to the county was the only thing the callback could do. The
index now carries each area's filename beside its name, and every hit is a real link: an area to
its page, a county to the county page with the click kept in the app.

> **Concept: the flag and the value are the same field.** 904 area names are *eligible* for a page
> under the predicate above; 739 pages exist. Gating the search index on eligibility would have put
> about 165 names on a URL that does not exist, which is a worse failure than the one being fixed,
> because a reader who searches and lands on a 404 concludes the site is broken. The index is gated
> on the filename being present in the data, since that is written only when a file was written,
> and a test asserts every name the index offers has a file behind it.

Three things fell out of review on that change, and each is the kind of bug that only exists once
the thing on the other side becomes real. A `return false` on the click handler had been harmless
while every link was a fragment and now cancelled the new tab a Cmd-click asked for. The label
beside a hit blanked whenever a settlement shared its county's name, which is 14 real towns, so
those rows rendered bare and read as county hits. And the search file is fetched lazily, so a tab
left open across a deploy pairs old code with a new file: the old reader threw on the new shape
and left the box stuck on "Searching...". Renaming the variable the file assigns means that reader
gets the box's own "Search is unavailable, try reloading" instead, which is an honest state that
says what to do.

A same-day fix to the directory belongs beside it: its filter matched each row's whole text, so
"notice" matched all 1,800 rows, as did "people" or any digit, and the count read out to a screen
reader was meaningless. It matches the name now.

### The cap comes off (PR #68, 27 August)

The link label was corrected in #62 because the page held 60 notices and claimed more. The
better fix was the other one. The static county page exists to be the durable record the hash
routes can never be, and presenting itself as a county's record while holding a sixtieth of it was
the one claim on the site that could be checked and found short. Both caps are gone.

The old comment's worry is real and was written down rather than deleted: the archive grows
without bound. But a count was always a proxy for bytes and a poor one, so if a bound is needed
again it should be a byte budget. Measured at 251 bytes per row, a thousand notices is 245 KB of
list (PR #68). The real measurement had to wait for a build with feed data, and it arrived nine
days later: the largest page is Dublin at 384 KB, comfortably under what the front page budgets
for itself, so no bound has been needed yet (PR #87, 5 Sep 2026).

The rest of that pass is consistency. Three surfaces named the directory three ways and one was
false: the static footers called it "every area in Ireland", but the directory is built from the
history, so an area that has never had a notice is not in it. Everything says "every area with a
notice" now, which is the directory's own heading. The app is "Co. X's interactive view"
everywhere rather than "the interactive map", because it is bars and a table and not a map.

### A test for whether a rule applies (PR #64, 26 August)

One more thing landed that day, tests only, and it is worth a paragraph because it names a blind
spot the shared design layer created.

The line under a drill-down heading - the "Permanent link to ..." line on every one of those 739
new pages - is styled by a rule that reaches this repository only through the pinned dependency.
When it moved upstream, the local copy had to be kept for one commit, because the lock file can
only follow the shared repository's main branch. Deleting both at once would have left that line
unstyled on the live site with every test still green, because nothing anywhere asserted that a
rule *applied*. The tests only asserted that files said what they said.

"Applies" turns out to decompose into three things checkable from a build without a browser: the
page renders an element the rule can match, the rule is in the stylesheet that page inlines, and
nothing in the cascade beats it. Each one is now a test, and each was verified by making the
failure it exists for: removing the rule upstream fails four of them, renaming the element fails
the adjacency one, and copying the rule back locally fails the one that says it should not be
there.

## Where it left the site

By the evening of 27 August the site had 767 indexable addresses against the 2 it had in early
August, a search box that reaches a town's own page, county pages that hold their county's whole
record, and one name for each thing on it. The words "every area in Ireland" and "the interactive
map" are gone because neither was true.

The thing I would not have predicted is how much of this stretch was spent on promises rather than
on pages. A link label that claimed more than the page held; a description that read as an
inventory when it was cut short; a footer naming a directory that did not contain what it said; a
search result that would have 404ed on 165 names. The pages themselves were a Saturday's work. The
statements about them took as long, because a wrong statement on a page a stranger has just
landed on costs more than a missing feature does.

## Notes

- PR #62 (26 Aug 2026): link under the county heading; overview row href to the static page with
  the click suppressed; "every notice" false against `COUNTY_EVENTS_SHOWN = 60`, changed to the
  months; description ordering; `tests/test_permalink_affordance.py` new; 450 tests.
- PR #63 (26 Aug): 1,960 areas with a notice = 697 settlements + 42 LEAs + 1,193 EDs + 5 `-rest` +
  23 unplaced; 739 pages; 28 to 767 indexable URLs; no notice-count floor (a floor of 2 drops 122);
  median 5 / mean 9.0 / max 83; slug divergence on 17 fadas + 3 others = 20 404s; path keyed on
  county-and-name (185 name repeats, unique over 3,717); 15.1 MB raw / 4.58 MB gzipped, ~6.2 KB
  gzipped per cold landing, payload +4,517 B gzipped (+4.4%); 767 sitemap URLs against 767 files;
  480 tests.
- PR #64 (26 Aug): the three components of "a rule applies", each verified by mutation; 485 tests.
  PR #65 (27 Aug): directory filter matched full row text; sticky-nav fallback moved to 900 px.
- PR #66 (27 Aug): search hits become real links; 904 eligible vs 739 built; index gated on the
  slug; modified-click, county-named-town label and lazy-fetch rename from review; 489 tests.
- PR #68 (27 Aug): caps removed; 251 bytes per row; "every area with a notice"; "Co. X's
  interactive view"; footers unified. Largest page measured at Dublin 384 KB (PR #87, 5 Sep).
- `notes/frontend-notes.md` "The area pages", "The county-page link came up out of the footer",
  "Search reaches the area, not just its county", "The copy and consistency pass", "One name per
  thing".
