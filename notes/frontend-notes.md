# Frontend notes

Notes on `site.html` / `areas.html` / `county.html`, kept here so the reasoning isn't lost to chat history. See [how-it-works.md](how-it-works.md) for how the three pages fit together.

## 2026-08-20: the vendored copy became a pinned uv git dependency

One day of the vendored mechanism was enough to show its cost: a shared fix meant a sync,
test, commit and PR in each of three repos, and the sites drifted anyway — esb and lifts were
synced to statusui `f248ac3` while this site's main sat at `c9f8beb`, five UI commits behind,
with nothing failing to say so (the byte-compare only fires against the checkout you happen
to have; the catch-up sync eventually arrived buried in the iPhone-review PR below).
`statusui` is now a real package: `pyproject.toml` declares it with a `[tool.uv.sources]` git
source and `uv.lock` pins the commit, so what the build used is recorded and CI-visible, not
stamped in a file by a script.

**To change the shared UI:** edit in `../statusui`, test there, push, then run
`../statusui/rollout.sh` — it bumps the pin in all three sites, runs each site's tests, and
opens the three PRs. To try an unpushed statusui change here first:
`uv run --with-editable ../statusui uisce-site`. The vendored tree (`src/uisce/ui/`),
`scripts/sync-ui.sh` and the byte-compare went; the guard that no page script redeclares a
shared JS global stayed, as `tests/test_ui_globals.py` reading the installed package.

The pages are unchanged: `statusui.assemble()` still inlines the shared CSS/JS at build, so a
search-result landing still costs one request. The pin lands at the statusui commit whose
content the last vendored sync already carried, so the switch itself changes nothing but the
shared files' header comments.

## Shared with esb and lifts since 2026-08-19: the design layer lives in `statusui`

*(Mechanism superseded 2026-08-20, above: the vendored copy is now a pinned git dependency.
The what-is-shared split and the renames below still hold.)*

The three status sites are deliberately look-alike, and every UI fix had been ported three
times by hand — and not always: the 2026-08-18 contrast pass below never reached esb. The
tokens, base rules, the row/bar/card components and the small browser helpers are now one set
of files in `../statusui` (GitHub `baz8080/statusui`), **vendored** under `src/uisce/ui/` and
inlined into each page at build by `statusui.assemble()` (`page_html` in `site.py`). The pages
stay single-file: a search-result landing still costs one request.

Vendoring, not a submodule or a package, was the choice: the sites stay clone-and-build, each
site's PR shows the real CSS diff, and esb/lifts keep their empty `dependencies`. Drift is
guarded by `tests/test_ui_vendored.py`, which compares the copy to `../statusui/ui` when that
checkout is present and skips otherwise — the same convention as `../esb-data`.

**To change the shared UI:** edit in `statusui`, commit, then `scripts/sync-ui.sh` here and in
each sibling; `uv run pytest`; commit. If a site needed more than the sync, that was a site
change and belongs in its own block. What is shared and what is deliberately per-site is listed
in statusui's README; the short rule is that a rule goes upstream when two sites want it and
none wants it different, and becomes a custom property the moment one does.

What this site gave up in the unification: month tabs abbreviate to "Aug 2026" like the
siblings (the strip was wrapping on a phone anyway — see the overflow table below), the county
view's grade chip is the shared 32px, and the footer disclosures take the shared arrow. The
name collisions were renamed here rather than upstream: `plural` → `pl` (ours returns the word,
the shared one the count and word), `monthLabel` → `monthLabelLong`, and `dayCells` takes a
`describe()` for our `[severity, share]` cells. `test_site_css.py` parses the assembled page now,
since the template alone no longer carries the rules it guards.

## Fixed 2026-08-06: `hidden` needs `!important`, or an author `display` wins

Both pages are hand-written HTML that switch views on and off with the `hidden` attribute. The UA stylesheet's rule for it is a plain `display: none`, which any author `display` on the same element outranks — the element then stays on screen while the page believes it is gone.

That was not hypothetical. `#overview { display: flex }`, added for the narrow-screen column reorder, did exactly that under 640px: the overview stayed rendered underneath every drill-down. On a phone, tapping a county appeared to do nothing — the router scrolled to the top of an overview that had never left — and a reload landed on an un-rendered overview (an empty `.banner` box) with the county view thousands of pixels below it.

**Fix:** `[hidden] { display: none !important; }` in `site.html`, so `hidden` wins regardless of whatever `display` a future layout rule sets. `tests/test_site_css.py` guards the invariant generally: for every element either page hides, it works out which `display` actually wins once `hidden` is set, in every `@media` context the stylesheet defines, so the same class of bug on a different element or a different breakpoint fails a test instead of shipping. The parser is deliberately small — it reads only the `display` property out of the two files it's pointed at, not CSS in general.

## Contrast pass 2026-08-18: the grade chips could not carry white text

From a cold external usability review. Every ratio below was recomputed independently against the WCAG 2.1 relative-luminance formula before anything changed; all of the review's figures reproduced exactly, including the `color-mix` for grade B, which lands on `#69930f`.

**The grade chips are the site's headline signal and three of five failed as text.** White on A `#0ca30c` was 3.35:1, on B `#6ba911` 2.87:1, on D `#ec835a` 2.64:1 — against the 4.5:1 that 14px text needs. B and D were the worst, and B against D is exactly the distinction the overview most needs to convey: a reader could see *that* a county had a grade and not reliably *which*.

`--good` darkens to `#087f08` (white on A: 5.19:1) and B and D join C in dark `#1a1a19` lettering (B 4.79:1, D 6.60:1). A and F keep white on ends dark enough to hold it. **The alternative — keeping white throughout and darkening all five fills — was rejected**: carrying `#ec835a` dark enough for white text turns the D chip a red close enough to F to blur the one boundary the scale exists to draw. The ink alternation (white·dark·dark·dark·white) reads as ordered because the hue progression green→olive→amber→salmon→red carries the ordering on its own.

The same pass fixed the text uses of the status hues, which are tuned for fills and are too light to be read on the page: `.badge.partial` was **1.79:1** — yellow on off-white, effectively invisible — and the boil-water `!` mark, the most safety-relevant element on the page, was 2.64:1. Text-safe shades (`--good-text`, `--warning-text`, `--serious-text`, `--critical-text`, and `--serious-deep` for fills that must carry white) are separate tokens rather than changes to the fill hues, so the fills keep their identity in the bars and swatches. Light-mode `--muted` was 3.41:1 and becomes `#6e6c66`; dark mode keeps `#898781`, which already passed at 5.41:1 on near-black.

### The month-tab overflow starts at six months, not now

The review reported the tab strip already overflowing a 390px phone at five tabs, with the sort control clipped and a page scrollbar. **That did not reproduce and was not true when written.** At five tabs the buttons shrink to fit (89px → 65px) and `document.scrollWidth` equals the viewport exactly. Measured at 390px, without `flex-wrap`:

| tabs | overflow |
|---|---|
| 5 (Apr–Aug 2026) | none |
| 6 | 42px |
| 7 | 122px |
| 8 | 214px |
| 12 | 536px |

Collection began 2026-04-20, so the sixth tab arrives **1 September 2026** and the overflow with it. `flex-wrap: wrap` on `.months` fixes it at every count. Shipped ahead of the fault rather than after it.

**Superseded 2026-08-19**: wrap was the stopgap, not the answer — see "The iPhone review
pass" below. The strip scrolls horizontally now.

### Left open

The *fills* still fail the 3:1 non-text threshold against the light page — `--warning` 1.74:1, `--serious` 2.50:1 — which matters for the legend swatches, where the colour itself is the meaning rather than a backdrop for a letter. The review checked `--maint` against this threshold but not the others. Not addressed here: changing the fills reaches the bars and the county grid, which is a bigger visual decision than a text-contrast fix. *Partially closed 2026-08-26*: the worst offenders — the 40%/70% opacity steps, at 1.80:1 and 2.93:1 light and 1.54:1/2.51:1 dark — left the bars with the solid severity ramp (see "The design alignment pass" below); `--warning` at 1.74:1 remains, on restriction days and their swatch.

Also noted and not taken: the overview is entirely JS-rendered with no `<noscript>` fallback (the county pages are static, so the content exists — it is the pointer that is missing); the health mark explains itself only through `title=`, which never fires on touch; and the sort `<select>` has no programmatic label (*closed 2026-08-26: the sort control was removed outright — see below*). The first needs a wording decision, the second touches generated markup the tests pin.

## The design alignment pass 2026-08-26

The owner reviewed uisce and esb side by side and picked a winner per element, so the two
sites read as one product before the same language reaches lifts. What uisce absorbed, with
the measurements:

**Quality notices left the day bars** (owner decision). A quality-only day now renders clear;
the `!` healthmark, the county tiles and the county pages carry drinking-water notices, and
the healthkey line says so ("Quality notices do not colour the day bars."). Removed
*server-side*, in the `worst` scan in `site.py`: `worst` short-circuits on the first severity
with coverage, so a quality+restriction day must fall through to the restriction — a
client-side remap of the packed `["quality", pct]` cell could never recover what was
underneath. Consequence, accepted: `clear_days` counts quality-only days as clear.

**The intensity ramp became solid severity tokens.** The old `opacity: .40/.70` steps are
colour-mixing with `--page`: measured, n1 was 1.80:1 (light) / 1.54:1 (dark) and n2 2.93:1 /
2.51:1 — the washed-out pink an owner review flagged against esb's solid bands. No tuned
opacity clears 3:1 for the lightest step without collapsing the ramp, so the steps now reuse
the severity tokens: n1 `--serious` (2.50:1 light / 7.37:1 dark), n2 `--critical` (4.56 /
4.05), n3 `--severe` (8.44 / 2.98). Zero new tokens, theme-correct automatically, darker =
worse literally true in light mode. n1-light and n3-dark still sit just under 3:1 — a partial
close of the "fills fail 3:1" item above, not a full one. Cross-site wrinkle, deliberate:
uisce's "minor" is orange where esb's is yellow — colour maps stay per site (statusui's rule).

**Captions became severity words.** "Fri 1 Aug: minor supply disruption" at the old
thresholds (minor < 0.5% of the county, moderate < 2%, major above), matching esb's pattern;
the percentage left the caption, the legend ramp carries "darker = worse".

**The sort control was removed; the shared search box replaced it.** 26 rows scroll;
alphabetical is the only order, and statusui's `bindSearch` (the behaviour esb's box already
had, moved upstream) searches every Census settlement — `search.js`, county → sorted names
over the full TownLookup so never-noticed towns are findable, built per build and fetched on
the first keystroke (~66 KB, never in the initial payload). Picking routes to the county view.

**Rows gained esb's affordances**: the `›` chevron (the per-site `--row-cols` override that
dropped its track is gone; both sites ride base), and the bare percentage became the two-line
`.cml` stat with an "availability" caption. The counts label is "outages" — "disruptions"
overflows the shared 92px stats column.

**The banner-duplicate tiles went** ("announced supply disruptions", "typical time…"), the
basis line became esb's shape ("Counties are graded on water supply availability. Nationally
this month: …"), the partial-month note was removed outright (the owner: don't explain that
future data doesn't exist), the county drill-down card adopted esb's order (legend on top,
tall bar, tiles instead of the `.drow` run), and the footer's `.method` hairlines went, with
every disclosure tightened for a lay reader — the numbers stay in these notes and the
methodology files.

## The iPhone review pass 2026-08-19

An owner review on a 390px iPhone. Everything below was verified against fixture-built
before/after screenshots (touch-emulated Chromium, 390×844 and 1280px, both colour schemes).

**The month strip scrolls instead of wrapping** (statusui). At five tabs the strip was already
two rows on a phone; wrapped, twelve tabs measured three to four rows sitting above the county
list. Now `.months` is a single `overflow-x: auto` row — hidden scrollbar, edge shadows that
appear only where more tabs lie (surface-coloured covers with `background-attachment: local`
hide the pinned shadows at rest), and a new `revealMonthTab()` scrolls the selected tab back
into view after each render, via `scrollLeft` because `scrollIntoView()` also scrolls the page.
At twelve simulated months: one row, 1,095px of tabs in a 356px strip, page `scrollWidth`
still exactly the viewport. Alternatives rejected: a "recent + older" split is two controls
where readers overwhelmingly want the current month anyway, and a `<select>` loses one-tap
adjacency between neighbouring months. The top-ten view's tabs sat bare in `.controls` with no
`.months` pill at all; they are wrapped now, so all three strips behave alike.

**Day captions no longer pop in on touch** (statusui). PR #44's `(hover: none)` +
`:empty` gate hid the list strip on phones — but iOS fires `pointerover` on the touch that
starts a scroll or a tap, the delegated listener filled the strip, and once non-empty the
`:empty` gate no longer matched: the caption appeared and grew the row 17px, exactly what the
gate existed to stop. `bindDayCaption` now ignores `pointerover` with `pointerType: "touch"`.
The click path is untouched, so the county cards' "Tap a day for detail." still works, and an
iPad trackpad (which reports `hover: none` but hovers as `pointerType: "mouse"`) still fills
the strip — the exception PR #44 was built around.

**The phone column owns its rhythm** (statusui). Under 640px `#overview` is a flex column, so
the desktop margins stopped collapsing and the section gaps landed wherever they fell:
measured 22/6/14/14/18/30/16px down the page, the 6 being uisce's `.healthkey` desktop margin
(`-4px`, tuned to sit under `.legend`) applying after the mobile reorder had moved it under
`.controls`. The column now zeroes its children's vertical margins and spaces them itself:
`gap: 12px`, plus `margin-top: 12px` where a section starts (`.controls`, `#list`, `.legend`,
`.natheading`). Measured after: 24/12/12/24/24/24/12/12. Desktop is untouched.

**Copy cut to what a phone can carry** (this repo): the subtitle is one sentence plus the
county prompt ("Uisce Éireann water outages, restrictions and works. Pick your county for
details." — "outages and events" was considered and rejected, "events" carries nothing);
"Partial month — in progress" reads "Month in progress."; and "What this measures" went behind a footer
disclosure like its two siblings — `id="method"` stays on the methodology block, which
`openMethod()` and two links target.

**Reverted 2026-08-20: the health key names all three kinds again.** Shortening it to
"boil-water or do-not-drink" was measured against the archive after the fact and is wrong:
of the 42 notices that raise the mark, 35 are `boil_notice_issued` and 7 are
`consumption_notice_issued` — every one of those 7 titled "Do Not Consume Notice" — and no
notice in the feed has ever said "drink". The short line named a kind the site has never
seen and dropped the only other kind it marks, on the mark's one always-visible explanation,
while `healthPill`, `healthTitle`, the methodology and the area badge all named three. It is
the same fault the pill comment at `healthKey`'s neighbour already records being fixed once.
Folding for a lay reader is fine where the fold is true; here the generic term was the one
that does not occur.

**Fixed 2026-08-20: `revealMonthTab()` did not survive a rotate** (statusui). It runs only
from `render()`, which nothing calls on resize, so a narrowing viewport left `scrollLeft`
measured against the old width: at 851px the strip fits with "Aug 2026" at x 352–439 and
`scrollLeft` 0; at 375px that is a 341px strip still at 0, with the selected tab entirely out
of view while the page below shows August. `bindMonthReveal()` (statusui `0567472`) binds one
resize listener that reveals the tab in every laid-out `.months`; hidden views measure zero
and are skipped, since they re-render before they are shown.

## The county-page link came up out of the footer — 2026-08-26

It was a `<p id="countyHistoryLink">` in the footer, shown only in the county view, reading "See every notice ever recorded for Kildare". Nothing gets clicked in a footer, and what is on the other side — the full notice history, the month table, the area list — is more interesting than that placement implied.

It now sits on its own line directly under the county heading, above the month tabs: the placement lifts has always used and esb adopted the same day. The rule that styles it, `.chead + .sub`, is promoted to statusui's `base.css`; lifts and esb had been carrying it byte for byte and this site is the third consumer. It sat in this site's inline block beside `.chead .pop` until the pin bump that followed, which removed all three local copies.

**The overview row's `href` changed too, and this was the bigger hole.** It pointed at `#county/<name>` — the hash. lifts and esb both point theirs at the static page with the click suppressed, so a crawler, a middle-click and a "copy link address" all reach the page while a normal click stays in the app. Here they reached a fragment, which meant `c/<county>.html` was discoverable only from the footer link and from `areas.html`. It now points at `c/<county>.html`.

**Wording: "Every month for Co. Carlow on one page" — the same sentence esb uses, and not the old footer copy.** It first shipped as "Every notice ever recorded in Co. Carlow", carried over from the footer without being checked against the page. That was wrong: `_county_events_html` caps at `COUNTY_EVENTS_SHOWN = 60` and prints its own "N older notices not shown here", so the label promised something the page then denied — the exact false-promise failure this whole decision exists to avoid.

What the page really carries that the view does not is *every month*: the county view is one month's bars, tiles and town table, and the month table on the page covers every month collection reached. That is true, and it is word for word the relation esb's county page stands in to esb's county view — so the two sites say the same thing. Two categories, not three:

- **esb and uisce** — the view is one month, the page is all of them: "Every month for County X on one page".
- **lifts** — the page carries the same months and cases the view already shows, so there is no content difference to name, only a durable address: "Permanent link to Athy station".

Same placement on all three; the words follow the content relationship, and two of the three share one.

"Permalink" was rejected as the label: it is blogging-era vocabulary a general audience mostly does not hold, and it would undersell a page that genuinely carries more than the view. The county is in the link text because a screen reader lists links stripped of their context.

### The area view has no equivalent, and that is the accepted gap

An area is reachable only as `#area/<county>/<code>`. There is no `a/<slug>.html`, so a reader who drills county → area watches the affordance disappear — one click deeper, into the ~1,836 areas that are the long tail and where a shareable URL is worth most.

Left open rather than papered over. Closing it means building area pages, and the measurement that would gate that is written down: of 3,717 areas, 909 are named CSO settlements and 2,808 are electoral divisions whose names all begin "Around " — pages for those would be thin content at scale. Slugging the `(county, name)` pair is collision-free across all 3,717 (name alone collides 185 times), so the scheme is not the obstacle; the decision about which areas deserve a page is.

Guarded by `tests/test_permalink_affordance.py`, including a test that asserts the area view offers nothing, so the gap stays deliberate.

### The county page's meta description had the same shape

"…in Co. Carlow - 1,234 notices across 56 areas, updated twice daily." The counts are the county's whole record; `_county_events_html` stops at `COUNTY_EVENTS_SHOWN = 60`. Less blatant than the link, because it never said the page listed them — but a reader arriving from that snippet expects to find them.

Now: "Co. Carlow: 1,234 Uisce Éireann notices across 56 areas - water outages, boil notices, restrictions and works. Month-by-month totals and the most recent notices." Same fix as esb's, and the same ordering rule behind it.

**Ordered so truncation cannot make it false.** A snippet is cut by pixel width and what survives is the front, so the clause naming what the page holds goes last: cut anywhere in it, what remains is a true statement about the county. 156 characters on the fixture county.

`{len(areas):,} areas` printed "1 areas"; fixed in passing.

Guarded in `tests/test_site.py::TestIndexablePages` — the ordering, the truncation property, the length ceiling and the plural.

## The area pages — 2026-08-26

The gap the previous entry recorded as accepted is closed. 739 areas now have a page at `a/<county>/<area>.html`, and the app's area view links to it. The site's indexable surface goes from 28 URLs to 767.

### Which areas, and the numbers that decided it

An area code is one of five things. Measured on the 2026-08-26 corpus, over the 1,960 areas that have ever had a notice:

| kind | with a notice | page? |
|---|---|---|
| CSO settlement | 697 | yes |
| City Local Electoral Area | 42 | yes |
| Electoral Division | 1,193 | **no** |
| City residual (`-rest`) | 5 | **no** |
| Unplaced | 23 | **no** |

The EDs are the whole reason there is a predicate. All 2,808 of them are named *Around …* — countryside around somewhere, not a place anyone types into a search box — and publishing 1,193 near-identical pages is what a search engine demotes as scaled thin content, with the risk landing on the county pages that already work. The `-rest` codes are a city's leftover LEAs, named *Elsewhere in Cork city*. Neither is a place, so neither gets an address.

**Deliberately not gated on a notice count as well.** A floor of two would drop 122 pages today, but it would also make a URL appear the day an area's second notice arrives and vanish if the data were ever rebuilt differently. A permalink that comes and goes is worse than a short one, and a page reading "one notice, this date, 4 hours, ~500 people" is a real answer for a real place. Notices per page today: median 5, mean 9.0, max 83 (Dún Laoghaire).

### The path is keyed on the name, and the app is told the slug

`a/<county-slug>/<area-slug>.html`. Not the code — a code is not a filename, which is what kept the history shards per county: 31 contain a slash and most contain colons. Not the name alone either, because 185 area names repeat across counties. County-and-name is unique over all 3,717 areas in the CSO file, asserted rather than assumed.

**The slug ships in the payload rather than being derived in the app, and this is not thrift being skipped.** statusui's two slug functions are deliberately unpaired — its own test says so — and `ui.js`'s leaves a fada as a dash: `Dún Laoghaire` → `d-n-laoghaire`, where Python gives `dun-laoghaire`. 17 area names carry a fada and 3 more carry punctuation the two treat differently, so deriving the href client-side would 404 on 20 places. `towns[code].slug` is present exactly when the area has a page, so it is the flag as well as the value. Cost: 16,092 bytes on `data.js`, 849,664 → 865,756 (+1.9%).

### The label names the address, not the content

"Permanent link to Abbeydorney" — lifts' wording, not the county view's. The rule set on 2026-08-26 is that a label must match the content relationship, and this page carries the same notices the area view does, uncapped. Naming it for its content would promise a reader what they are already looking at. That puts uisce on both sides of the split: its county link names the months, its area link names the address.

Uncapped, unlike the county page's 60: an area accrues about one notice a month where a county accrues hundreds. Worth re-deciding if the biggest page passes a few hundred rows.

### Two things a review caught

The "open the interactive map" link shipped as `#area/<county>` — one segment where the app's area route needs two — so it matched neither of the router's patterns and dropped the reader on the national overview. It is the county route now, the same one the county pages use. A test reads the two patterns out of `site.html` and runs them against the href, rather than pinning a remembered shape; the build check does the same across all 1,247 hash links the static pages emit.

An event's `people` is the whole event's footprint. On an area page that sits two lines under the area's own Census population, so a notice spanning five areas printed 3,775 people on a page headed 528 with nothing to explain it — the app's badge carries that caveat in its title and the page had dropped it. The multi-area note now carries it too, and only when there is a figure to qualify.

### What it costs

739 pages, 15,030,476 bytes raw and 4.58 MB gzipped — the largest is Dún Laoghaire at 35.5 KB raw / 7.8 KB gzipped, the smallest ~18.5 KB. **84% of a small page is the inlined CSS**, which is the tradeoff statusui's `assemble()` makes on purpose: every one of these pages is entered cold from a search result, so a shared stylesheet would cost that reader a second request. Inlining is most justified exactly here. Re-decide if the page count goes much past a thousand; a linked stylesheet would drop ~12 MB from the artifact and cost each cold reader a round trip.

The whole build was checked rather than sampled: 767 sitemap URLs against 767 files on disk, matching in both directions, every canonical self-referential, and all 8,376 relative links resolving.

## Search reaches the area, not just its county — 2026-08-27

The area pages shipped yesterday, and the one control a reader actually uses could not reach them. Typing "Abbeydorney" and clicking the hit landed you on Co. Kerry, to find Abbeydorney again yourself.

That was the index's shape rather than a routing choice. statusui's `searchHits` returned `[name, county]`, `bindSearch` rendered a button carrying `data-c` alone, and the matched name was discarded — so `pick: goCounty` was not a decision, it was the only thing the callback was given. Both destinations already existed and both needed a key `search.js` did not ship.

### The destination is the page, not this site's own area view

uisce has an `#area/<county>/<code>` view as well as the page, so routing search at the view — and building one for esb, which has none, so the two sites would match — was the obvious symmetric answer. It was rejected, because the view earns almost nothing over the page:

- They are the same content. `area_page_html`'s own docstring says so, and the page then adds an "Elsewhere" section the view lacks.
- `renderArea` has no month tabs. The view is not a more interactive surface, just the same list.
- The search box is not in the area view either — `#q` lives inside `#overview` — so staying in the app does not keep searching available.
- `go()`'s comment already settled the analytics case: pushState does not get a drill-down counted, and "the county pages are what actually solved it, being real documents at their own URLs".
- The page is indexable, shareable, middle-clickable and survives JS off. At ~18.5 KB self-contained it is one request; the in-app route may still have to fetch a county history shard, so from a cold search click the page can be the faster of the two.

**A search hit is an entry point, not a drill-down, and entry points should be real URLs.** That is the same argument that moved the overview's county rows off their hash on 2026-08-26 — recorded there as "the bigger hole" — applied to the one control that had not had it yet. Every hit is an `<a href>` now: an area goes to `a/<county>/<slug>.html`, a county to `c/<county>.html` with the click kept in the app. esb does the same thing with the same code, and needs no `#area` route to do it, so the two sites converge on the page rather than on a route neither of them needed.

### The `#area` view stays, and is not dead weight

The argument above says the page is the better destination, which invites the conclusion that the view should go. It should not, for two reasons that are the mirror image of it:

**It is the only surface the pageless areas have.** Of the 1,960 areas that have ever had a notice, 739 get a page; the 1,193 `Around …` Electoral Divisions, 5 city `-rest` buckets and 23 unplaced are denied one on purpose, to keep 1,193 near-identical pages out of the index as scaled thin content. Their notices still have to be readable, and `_area_items` already routes them there. Delete the view and **62% of noticed areas become unreachable**. Having no URL is exactly the property that makes it right for them.

**A drill-down is not an entry point.** The county view's towns table is an in-app table; a row click should behave like the rest of the app. That is a different job from a hit arriving cold, and the distinction is what justifies both existing.

The towns rows did carry the same hole the county rows had, though: their `href` was `#area/<county>/<code>` for *every* area, including the 739 with a page. `t.slug` was already in scope on the row. They now point at the page where there is one and the hash where there is not — the rule `_area_items` follows server-side, finally the same on both sides.

### The gate is the payload's slug, not `area_has_page`

`area_has_page` is a predicate on the *name*: 904 of the 3,717 areas pass it. Only the ones that have had a notice get a page built, so gating the index on the predicate would have put ~165 names on a URL that does not exist. `site["counties"][c]["towns"][code]["slug"]` is present exactly when a page was written, so it is the flag as well as the value, and the test asserts every slug the index emits has a file behind it.

The slug and not the whole href: measured on `sa_towns.csv`, `search.js` goes 66,477 → 79,784 bytes (+20.0%) carrying slugs, against 92,704 (+39.5%) carrying full paths. Both sites already share the `a/<county>/<area>.html` shape, so each assembles it in one line. Shipping the *code* instead would have been cheaper still (+9,766) — settlement codes are five digits where the long colon-and-slash ones all belong to EDs — but the code only addresses the in-app view, which is not where the hit goes.

`search.js` is fetched on the first keystroke and never in the initial payload, so none of this lands on a reader who does not search. It assigns `UISCE_PLACES` rather than `UISCE_SEARCH`, and the rename is load-bearing: fetching it lazily means a tab opened before a deploy pairs its own inlined `ui.js` with the current file, and the cache-bust is a query string the server ignores rather than a version it selects. The old `searchHits` calls `toLowerCase` on an entry, which throws on the pair, before the dropdown's markup is assigned — leaving it stuck on "Searching…" until a reload. Renaming with the shape means that reader gets "Search is unavailable - try reloading" instead, which is the box's own state and tells them what to do. esb took the same rename.

### Two edges, both left as they are

A county that is also a settlement name dedups to the county hit, so search cannot reach the *town* of Carlow's page. There are 14 of them — Carlow, Cavan, Donegal, Kildare, Kilkenny, Leitrim, Longford, Louth, Monaghan, Roscommon, Sligo, Tipperary, Wexford, Wicklow. It is the pre-existing `name|county` dedup and typing a county name almost always means the county, which is also the richer destination. A non-prefix query ("ligo") skips the county hit and does reach the area, so the annotation stopped blanking on `name === county`: it now blanks only for a hit with no target, or the two rows would be indistinguishable.

A modified click asks for a new tab, and `return false` on an in-app jump cancels it. That cost nothing while these hrefs were hashes; it costs a page now, so the two rows whose href is a real document — the overview's county row and the towns row — ask `newTab(event)` first. The hash links are left alone, having nothing on the other side worth a tab. statusui's `bindSearch` took the same fix the same day, where the guard has to be conditional on there being an href at all: lifts renders buttons, and swallowing the click there would just break it.

An `Around …` ED and a settlement that has never had a notice both stay county-bound, and the annotation beside the hit says "· county" so the mixed behaviour is visible rather than arbitrary. Routing the never-noticed ones at the in-app view would give a better answer than the county — "nothing was ever published in Abbeydorney" — but the view falls back to the bare area code for its heading when the payload has no entry, so it would need a name shipped as well. Worth doing only if readers turn out to search for quiet towns.
