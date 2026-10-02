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

**Amended 2026-10-02:** the shared rule, in statusui's `base.css` since 2026-08-20, became `[hidden]:not([hidden="until-found"])` so that find-in-page can still reveal an until-found element ([baz8080/statusui#19](https://github.com/baz8080/statusui/pull/19), for rail-delays' paged list). The parser read that `:not(` as a pseudo-class that never matches and failed three of these guards on a page the browser renders correctly, so it now takes exactly that exclusion as matching: these pages only ever set plain `hidden`. Any other pseudo-class still reads as no match.

## Contrast pass 2026-08-18: the grade chips could not carry white text

From a cold external usability review. Every ratio below was recomputed independently against the WCAG 2.1 relative-luminance formula before anything changed; all of the review's figures reproduced exactly, including the `color-mix` for grade B, which lands on `#69930f`.

**The grade chips are the site's headline signal and three of five failed as text.** White on A `#0ca30c` was 3.35:1, on B `#6ba911` 2.87:1, on D `#ec835a` 2.64:1 — against the 4.5:1 that 14px text needs. B and D were the worst, and B against D is exactly the distinction the overview most needs to convey: a reader could see *that* a county had a grade and not reliably *which*.

`--good` darkens to `#087f08` (white on A: 5.19:1) and B and D join C in dark `#1a1a19` lettering (B 4.79:1, D 6.60:1). A and F keep white on ends dark enough to hold it. **The alternative — keeping white throughout and darkening all five fills — was rejected**: carrying `#ec835a` dark enough for white text turns the D chip a red close enough to F to blur the one boundary the scale exists to draw. The ink alternation (white·dark·dark·dark·white) reads as ordered because the hue progression green→olive→amber→salmon→red carries the ordering on its own.

The same pass fixed the text uses of the status hues, which are tuned for fills and are too light to be read on the page: `.badge.partial` was **1.79:1** — yellow on off-white, effectively invisible — and the boil-water `!` mark, the most safety-relevant element on the page, was 2.64:1. Text-safe shades (`--good-text`, `--warning-text`, `--serious-text`, `--critical-text`, and `--serious-deep` for fills that must carry white) are separate tokens rather than changes to the fill hues, so the fills keep their identity in the bars and swatches. Light-mode `--muted` was 3.41:1 and becomes `#6e6c66`; dark mode keeps `#898781`, which already passed at 5.41:1 on near-black.

### Amended 2026-08-30: B and D carry white after all

The lettering decided above was reversed when the scale grew an E and every chip was
re-examined. **This reopened a settled decision, and the reopening was accidental**: the B and D
change was made before this section was read, which is the thing the conventions exist to stop.
The evidence that closes it is below, recorded late rather than not at all.

The 2026-08-18 pass judged the chips on WCAG 2.1 alone, which is the formula this repo has always
tested against and which is unreliable on saturated mid-tones. Checked against APCA, the WCAG 3
candidate that models the effect properly, the two metrics disagree sharply on B:

| B `#69930f` | WCAG 2 | APCA |
|---|---|---|
| dark `#1a1a19` | 4.79:1 | **Lc 38.6** |
| white | 3.63:1 | **Lc 69.2** |

Lc 38.6 made B the least readable chip on the page by a wide margin, the next worst being D at
51.3. The dark ink was chosen on a number that did not describe what a reader sees, and it was a
reader noticing B looked wrong that prompted the recheck.

**The alternative this section rejected was adopted.** The stated reason for rejecting it - that
a D dark enough for white text "turns the D chip a red close enough to F to blur the one boundary
the scale exists to draw" - was asserted rather than measured, and does not hold at the value
chosen. D is now `--serious-deep` `#b34a20`, already in the token set for exactly this purpose,
and sits at delta-E **20.6** from F and **20.2** from E. Across all fifteen pairs of the six
chips, no two are closer than 20.2. B is now its own token, `--fair` `#5a7a10`, rather than a
`color-mix` of two bar hues that moved whenever a bar was retuned.

The ink alternation is gone: **C is the only chip taking dark ink**, because the amber is the one
fill light enough to need it. White on the other five is 4.97 to 8.89 on WCAG and Lc 77.5 to 93.5
on APCA. The hue progression green, olive, amber, burnt orange, red, dark red still carries the
ordering, which is what the original note said was doing the work.

Guards, in `../statusui/tests/test_ui.py`: `test_fills_carry_the_lettering_set_on_them` names
every fill-and-lettering pair the chips actually use, in both schemes, so none of this can drift
silently again. The 2026-08-18 pass had no such test, which is the other reason it went stale
unnoticed.

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

*Amended 2026-09-24:* the breakdown's row is not the whole payload. An area whose every notice is still ahead of the build has no month row, so it had a page and no slug in the index: 1 of 763 on the 2026-09-23 release, Laragh in Wicklow. The index now reads the slug off the history entry too, which carries it on the same rule; 763 of 763 pages are reachable from the box.

The slug and not the whole href: measured on `sa_towns.csv`, `search.js` goes 66,477 → 79,784 bytes (+20.0%) carrying slugs, against 92,704 (+39.5%) carrying full paths. Both sites already share the `a/<county>/<area>.html` shape, so each assembles it in one line. Shipping the *code* instead would have been cheaper still (+9,766) — settlement codes are five digits where the long colon-and-slash ones all belong to EDs — but the code only addresses the in-app view, which is not where the hit goes.

`search.js` is fetched on the first keystroke and never in the initial payload, so none of this lands on a reader who does not search. It assigns `UISCE_PLACES` rather than `UISCE_SEARCH`, and the rename is load-bearing: fetching it lazily means a tab opened before a deploy pairs its own inlined `ui.js` with the current file, and the cache-bust is a query string the server ignores rather than a version it selects. The old `searchHits` calls `toLowerCase` on an entry, which throws on the pair, before the dropdown's markup is assigned — leaving it stuck on "Searching…" until a reload. Renaming with the shape means that reader gets "Search is unavailable - try reloading" instead, which is the box's own state and tells them what to do. esb took the same rename.

### Two edges, both left as they are

A county that is also a settlement name dedups to the county hit, so search cannot reach the *town* of Carlow's page. There are 14 of them — Carlow, Cavan, Donegal, Kildare, Kilkenny, Leitrim, Longford, Louth, Monaghan, Roscommon, Sligo, Tipperary, Wexford, Wicklow. It is the pre-existing `name|county` dedup and typing a county name almost always means the county, which is also the richer destination. A non-prefix query ("ligo") skips the county hit and does reach the area, so the annotation stopped blanking on `name === county`: it now blanks only for a hit with no target, or the two rows would be indistinguishable.

*Amended 2026-09-03.* Closed the other way, with esb (baz8080/esb#28), where the same fourteen towns were kept out of the index by a builder-side guard. statusui's dedup now keys on `name|county|target` (`eecdf2d`): a bare name that is also a county still collapses, which is what lifts relies on, and a targeted entry keeps its row under the county's, which still ranks first. The two rows read `Sligo` and `Sligo town`: the `note` callback returns "town" for a targeted hit named for its county, in the slot where every other area hit shows its county, because that is how the places are told apart in speech. Nothing changed in `site.py`; the index already carried the entry, and a test now holds it there so a `name != county` filter cannot creep in. statusui merged first and the pin bump (`49802b2`) rode in the same PR, so the row went live with it.

A modified click asks for a new tab, and `return false` on an in-app jump cancels it. That cost nothing while these hrefs were hashes; it costs a page now, so the two rows whose href is a real document — the overview's county row and the towns row — ask `newTab(event)` first. The hash links are left alone, having nothing on the other side worth a tab. statusui's `bindSearch` took the same fix the same day, where the guard has to be conditional on there being an href at all: lifts renders buttons, and swallowing the click there would just break it.

An `Around …` ED and a settlement that has never had a notice both stay county-bound, and the annotation beside the hit says "· county" so the mixed behaviour is visible rather than arbitrary. Routing the never-noticed ones at the in-app view would give a better answer than the county — "nothing was ever published in Abbeydorney" — but the view falls back to the bare area code for its heading when the payload has no entry, so it would need a name shipped as well. Worth doing only if readers turn out to search for quiet towns.

## The copy and consistency pass — 2026-08-27

A read-through of the live pages, page by page, against what each one actually says. Four
kinds of finding, plus one substantive change.

### The county page is the county's whole record now — the cap came off

`COUNTY_EVENTS_SHOWN = 60` and `COUNTY_OPEN_SHOWN = 20` are gone, and so is the
`"N older notices not shown here"` line under the list. The page exists to be the durable,
indexable document the hash routes can never be; presenting itself as a county's record while
holding a sixtieth of it was the one claim on the site that could be checked and found short.

Measured cost, at 251 bytes per rendered row (`_events_html`, synthetic Cork-shaped rows):
500 notices is 123 KB of list, 1,000 is 245 KB, 2,000 is 490 KB. The corpus holds 11,405 cases
nationally, so no county is near the top of that range today. esb, whose corpus *is* local and
whose cap came off the same day, went from a 100.7 KB largest county page to 127.4 KB.

**This does reopen a real concern**: the archive grows without bound and nothing now bounds
the page. The bound to reintroduce, if one is needed, is a byte budget rather than a count —
a count was always a proxy for the bytes and a bad one, since a row's size varies with the
title and location strings. Nothing was measured against the live uisce feed here: the ArcGIS
host is unreachable through this session's proxy, so the figures above are from synthetic rows
of realistic width. **Check the largest `c/*.html` on the next CI data build.**

*Measured 2026-09-05*, on the 2026-09-04 release with #80's notice text folded under the open
rows: Dublin 384,115 bytes, Cork 335,599, Kerry 245,632. Under the 512 KB the index budgets for
itself, so no byte budget yet; the entry to watch is Dublin's.

The two places that documented the cap as their reason moved with it. The county view's
sub-link still says "Every month for Co. X on one page" and still deliberately avoids "every
notice ever recorded" — but the reason is now that the *view* is one month at a time, not that
the page is short. The meta description reads "Month-by-month totals and every notice
published"; the record-then-listing ordering stays, because a snippet cut by width still has
to leave a true sentence behind.

`_events_html` lost its `shown` parameter entirely and `_county_events_html` with it — both
call sites are uncapped, so the parameter had no caller left.

### One name per thing

Three surfaces named the same destination three ways, and one of the three was false.

| Thing | Was | Now |
|---|---|---|
| the area directory | "every area with a notice" (index), "every area on the site" (county card), "every area on this site" (area page), **"every area in Ireland"** (static footers) | "every area with a notice" everywhere — the directory's own `<h1>`. The static-footer wording was simply wrong: `area_index` reads the built history, so an area with no notice is not in it |
| the app | "the interactive map of Co. X" (area page), "the interactive view" (county page) | "Co. X's interactive view". It is bars and a table; it was never a map |
| a notice count | `· 24` (static), `24 notices` (app cards), `· 24 notices` (app month headings) | `· 24 notices` everywhere, noun included |
| the footer credit | "Source and methodology" (uisce's three static pages) | "Source code · not affiliated with Uisce Éireann." — already the shape on uisce's index, both lifts pages and all three esb footers, so uisce's static pages were the outlier rather than the pattern |

The area page's "Elsewhere" block dropped to two links. The directory link it gave up now sits
in the footer, where the county page already had one and where every other static page carries
it; keeping both was one line saying the same thing twice. "Co. Carlow's whole record" survives
the edit because the cap coming off makes it literally true.

### The 40px that nothing asked for

`base.css` resets `margin` and not `padding`, so every `<ul>` a site emits keeps the user
agent's `padding-inline-start: 40px`. `list-style: none` takes the marker away and leaves the
gutter it sat in, which is why `ul.notices` and `ul.areas` were indented for no visible reason.
Both take their own padding back now; `.tl` and `.method .grades` already did, which is what
made the omission easy to miss. Guarded in `test_site_css.py` against the built county page,
so it is the assembled cascade being asserted and not the source text.

Kept local rather than promoted to statusui: the shared rule there wants a custom property or
a component, not a blanket `ul` reset, and lifts renders no such list. `ul.areas` is already
down for promotion as a separate follow-up (esb's `notes/area-pages.md`).

### The footer's own chrome

`.method` was doing two jobs. It styles the footer's three disclosures *and* the county card's
"How areas are drawn" — but only the footer ones sit inside `footer details` / `footer summary`
in base.css, so its `margin-top: 12px` and `summary { padding: 8px 0 }` were stacking on top of
chrome that already existed. Both are scoped to `.card > .method` now, which is the one context
that has no chrome of its own. `.method h4`, `.method > p:last-child` and `.method .grades` stay
unscoped; the footer's methodology block is the only thing that uses them.

`#topLink .toplink` lost its 14px bottom margin. It is the last thing in the overview, so the
footer's own 28px was the whole gap and the two were adding to 42px.

### Copy

- "Durations count from when a notice was published, not when the service was lost" replaces a
  sentence that explained the same thing through an example of a burst.
- "the headline" was doing work it cannot do in two places. The figure it named is a duration,
  so it says duration.
- "How many people a notice affects" was one sentence carrying pin geometry, a weighted average
  and a cap. It is three now, and the average is described rather than named.
- Two trailing clauses went: ", over the incidents that reported one" (the sentence before it
  already says so) and ": the same supply zone is published both ways" (the rationale, which
  belongs in statuspage-methodology.md and is there).
- The healthkey lost "Quality notices do not colour the day bars." The decision stands — see
  the design alignment pass above — but the key is for reading the page, not for explaining
  why the page is the way it is.

### The county card's hours tile carried someone else's numbers

`20.7h · 6 confirmed, 2 scheduled only, 1 never reported an end` put a duration and a
breakdown of *cases* in one tile. The split decomposes the outage count, so it moved onto the
tile that carries that count; the hours tile shows the hours. `completed_n` drops out of the
view but stays in the payload — it is what `median_completion_h` is computed over, and
`TestPayloadShape` snapshots the key set on purpose.

## A day in the county bar lists its notices - 2026-09-05

The caption on a day cell said "moderate supply disruption" and not which. The county's
history shard already carried every event with its first charged day, so `event_record` now
adds `end`, the last charged day (omitted when it is the start day, the sparse rule the rest
of the record follows), and the county view derives the day's list from the shard once a
reader taps a cell. Nothing is added to `data.js`; the shards grew from 2,406,853 to
2,513,470 bytes, loaded on demand as before.

Two limits, both accepted. The list is county-view only: the overview's bars are 26 rows
of the same cells and a tap there still just captions, because loading a shard per row a
reader hovers is the wrong trade. And a recurring event matches every day of its span, not
only the nights it ran, because the shard carries covered hours and span, not the windows;
the row says the hours were spread across the span. A cell carries no date, so the day is
its position among its siblings, which holds because `dayCells` emits one cell per calendar
day of the month.

## The county's own data left data.js - 2026-09-05

Measured on the 2026-09-04 release, `data.js` was 955,516 bytes and the overview read a third
of it. By block: `towns` 583,560 (61%), `resolved` 164,809 (17%), `months` 133,842 (14%),
`open` 58,212 (6%), `top` 11,548. The first two are read by the county view alone. The
methodology note had named 1 MB as the point to split per county, and six months in it was
at 955 KB, growing linearly in months × areas (4,833 town-month rows).

`write_site` now pops `towns` and `resolved` out of every county before serialising and
writes them to `t/<county>.js`, the same shape and loader as the history shards. The county
view loads its shard on entry and renders the head, tabs, bars and tiles from `data.js` at
once; the areas card and the closed-in-month card carry a loading note until the shard lands,
then re-render, the pattern the area view already used. After: `data.js` 212,116 bytes,
28,640 gzipped, against 955,516 and 123,950 before. The largest county shard is Cork at
69,925 bytes.

Three readers outside the county view needed a different source. The county's open list
grouped by area name through `towns`, so each open entry now carries its area's `name`
beside the code (about 10 KB across the payload; the code stays because the breakdown's
"Open now" column keys on it). The area view read name, population and slug from `towns`,
so the history entry carries `pop` and `slug` beside the `name` it already had, and the view
loads nothing but the history. The search index and the area pages are written by
`write_site`, which holds the popped block. `build_site`'s output is unchanged: the split is
the writer's, so `TestPayloadShape` still guards the full shape and a new guard asserts what
reaches `data.js`.

Two smaller things went with it. A clear area-month omitted its zero events and its zero
person-hours but spelled out `"availability": 100.0`; it is implied now, like the others
(1,218 of 4,833 rows). And `run()` prints `statusui.size_report` against `INITIAL_BUDGET`,
512 KB for index.html plus data.js, with a `::warning::` line on the Pages run when it is
over. A warning, not a failure: a deploy must not fail on growth alone, and the site would be
serving stale data until someone noticed.

Rejected: folding the breakdown into the history shard. It would have made one file and one
request per county, but the county view would wait for 2.4 MB of history it does not read,
and the area view would carry a breakdown it does not read either.

## The day list and "so far" read the charged span - 2026-09-24

Measured on the 2026-09-23 release with the clock pinned to 2026-09-24 06:00 UTC, and again
by running the app's own `dayEventsHtml` over every coloured cell up to today in Chromium.

**The day list.** `event_record` set `end` only inside the branch that publishes `hours`, so
an event charged an imputed span (closed, no usable end) carried its publication day and
nothing else, and the negative-span family, charged backwards from its reported end, was
filed under a publication day after every day it coloured. Of 3,420 coloured county-bar
days, 46 listed "0 notices" when tapped (Cavan 17 Aug: CAV00120687, published 16 Sep) and
9 more listed nothing of the bar's colour. The record now carries `end` for any event with
an interval and `from`, the first charged day, when it is not the publication day; the day
list matches on `[from || start, end || start]`. After: **0** and **0**, both counted in
Python and in the browser. `from` is on 619 events (617 of them earlier than publication),
`end` on 490 more; the history shards grew 2,862,985 to 2,887,669 bytes and `data.js` is
untouched. A row whose publication is on or after the tapped day reads "published <date>"
rather than "from <date>", which read backwards on those 617.

**"Nh so far".** An open event's `hours` summed its charged intervals, which run to a
scheduled or imputed end, so "so far" printed time that had not happened: Louth
LOU00120479 read 240.8h when 183.3h had passed since it went up, and 38 of 271 open events
had not started at all (Cork COR00120817, "Mon 5 Oct · 7.2h so far · 236 people · still
open" on 24 September). Another 37 start later on the build day and read the same way.
`hours` on an open event is now clipped to the build (LOU00120479: 183.3h), and dropped for
all 75 that have not started; an open record with no `hours` is how the pages know, so
there is no new key. The county and area pages print "not started yet" in place of the
hours and "still open"; the app prints "from <date> · not started yet" in place of "open
since" and the hours, drops the "still running" badge on the 6 of them with no end signal,
and the day list reuses the same wording. `end` is not clipped: the bar still shows the days ahead.

The county page's open list said "since" a date to come on the same 38; it now says "from",
the word the app's `openGroups` already used.

**Amended after code review, same day.** Three things changed from the text above.
- **`ahead` is a key after all.** Reading "not started" from a missing `hours` broke once
  hours stopped including estimates, so an open record that has not started carries
  `ahead: 1`, and so does an open entry in `data.js` (sparse). The county page and
  `openGroups` read it as well as the date. The 37 starting later on the build day used to
  read "since <today>" beside a history saying "not started yet"; they now read "from".
- **Hours are measured hours.** `hours` sums only pins that did not take a `SpanTable`
  estimate, and is clipped to the build for every event, open or closed. An open notice
  already over by its own text (charged an estimate) printed that estimate as "at least Nh
  so far", and a closed event with a scheduled end still ahead printed the unelapsed time.
- **Standing notices.** After #97 the Open column and `OPEN_NOTE` also leave out a
  boil-water or do-not-drink notice closed by its lift or after 14 days with no lift, and
  say so; such a notice closed with no lift reads "no lift published", not "withdrawn".

Re-measured on the same release: 0 days listing 0 notices, 0 "so far" on a future start,
0 "since" on a future date including the build day, Atom well-formed, 763 of 763 area
pages reachable from search (the slug is now read from the history alone).


## The first paint waits for the data - 2026-10-02

Cloudflare RUM put the index at CLS 0.453 on `html>body>div.wrap` (13% of loads poor), with
LCP p50 2.2s and p75 2.5s. The scripts sit at the end of `<body>`, so Chrome paints the
header, an empty skeleton (`#banner`, `#months`, `#legend`, `#list`) and the footer while
`data.js` downloads (216 KB raw, 28.4 KB gz); the first `route()` then fills everything above
the footer and it jumps.

Lab, Chromium 141, slow 4G, 4x CPU, median of 3 (the runs agreed to four places). Load CLS:
**0.4826** at 360px, **0.3236** at 412px, **0.182** at 1366px (0.184 with classic scrollbars).
Opening an area from its county at 3g, when `h/<county>.js` lands more than 500ms after the
click, the footer moved **0.3004 / 0.1945 / 0.1317** (360 / 412 / 1366); a deep link to
`#area/Cork/...` or `#county/Cork` had **0.30 / 0.13** at load (360 / 1366).

**Decision.** statusui's `<!--UI-WAIT-->` in `<head>` puts a `wait` class on `<html>`, and
base.css keeps `[data-wait]` out of the paint until `pending(false)`. `#overview` and
`<footer>` carry `data-wait`: the first render fills the one and pushes the other.
- `render()` ends with `pending(shardPending())`, so the page is released by every render and
  held only while the area view's history shard, or the county view's own shard, is `loading`.
  The shard callback's `render()` releases it on success and on failure, and navigating away
  does too, because the next render recomputes it. No second release path to forget.
- It runs **before** `revealMonthTab()`. The first attempt put it last, and a month strip inside
  a held-back `#overview` measures zero wide: the strip stayed at April with the current month
  off the right edge. Caught by comparing the strip's `scrollLeft` (261 before and after the fix).
- Only the footer is held for the county view. Its shard arriving moved the footer by 0.0009 to
  0.0099 on tall windows (shard delayed 1.5s, 2560x1440: Donegal 0.0099, Louth 0.0045, Mayo
  0.0043, Kildare 0.0015, Leitrim 0.0009; Carlow 0.001 at 1920x1080) and not at all on a phone,
  where the footer is 1,300 px or more down. Now 0.
- Every view's `innerHTML` is replaced, and a replaced node has no previous rect, so the
  footer is the only layout-shift source the browser reports in either view. The area card still
  drops 34px when the shard lands and the "Permanent link" line appears; it is not CLS and is
  left alone.

**After.** Load CLS **0** at 360, 412 and 1366 (also with classic scrollbars, where
statusui's `scrollbar-gutter: stable` takes the rest). The area click at 3g, both deep links
and the county click: **0** at 360, 412 and 1366. `index.html` is 31,041 to 19,997 bytes gz,
nearly all of it statusui's comment stripping; `data.js` is unchanged.

**LCP.** At 412 the lab LCP is unchanged (716 to 736 ms, the `#healthKey` line). At 360 and
1366 it moves from 244 to 728 ms and 268 to 752 ms, because the baseline's LCP element there
was the first footer paragraph, painted into an empty page at ~240 ms. That figure flattered
the page: the footer is no longer painted before the content is. The real LCP is the first
render, which waits on `data.js`; shortening it is a separate change.

**Every failure path reveals the page**, each checked in a browser: no JavaScript (the class is
never added and the `<noscript>` text shows), `file://` (index and `#county/Cork`), `data.js`
404 or blocked (the `load` event), `data.js` stalling past 8s (released at 8s with the page
still loading), a first render that throws (`load`), and an area or county shard that 404s or
stalls past the loader's 10s timer (the callback's render, from a click as well as a deep link).

**Rejected, 412px slow 4G, median of 3.**
- `<script src="data.js">` moved into `<head>`: FCP 248 to 620 ms because nothing paints until
  it lands, and CLS still 0.3236 in one run of three.
- Preloading `data.js`: CLS unchanged at 0.3236 (LCP 696 ms).
- Reserving the skeleton's height (`min-height` on `#banner`, `.controls`, `#legend`,
  `#healthKey`, `#basis` and `#list` at five breakpoints): CLS 0.0007 at 412 and 0.0013 at
  360, not 0, and 17 hard-coded heights that go stale when the copy wraps differently.

**Not fixed.** Tapping a day in the county bar loads the history shard for its list, and the
list pushing the tiles down moved them 0.1492 at 412 (0.0328 at 1366) on 3g: those are
existing nodes, so it counts. It is in roadmap.md.


## Long static lists skip what is off screen - 2026-10-02

The county pages list every notice (c/dublin.html: 1,733 rows, 436 KB) and areas.html lists
2,123 areas in 26 sections. Chrome laid all of it out and painted what it could before the
reader had moved: total long-task time on a cold load, 4x CPU, median of 7 (desktop / mobile
412): c/dublin.html **485 / 518 ms**, c/cork.html 445 / 387, areas.html 834 / 738, an area page
(103 rows) 63 / 67.

**Decision.** `ul.notices > li { content-visibility: auto }` in `site.css`, and
`section[data-county]` in areas.html's own block, each with `contain-intrinsic-size: auto <n>`
so a row keeps its real height once it has been drawn. After, same method: c/dublin.html
**55 / 51 ms**, c/cork.html 157 / 85, areas.html 86 / 68, an area page 56 / 0. LCP and load CLS
are unchanged (0); areas.html grows 1.4 KB raw (380,811 to 382,168 bytes) for the section styles.

- **The row estimate is the content box.** `base.css` sets `box-sizing: border-box` and
  `contain-intrinsic-size` still sizes the content box, so the row's padding and rule come on
  top: an estimate of 60px (80px up to 640px wide) made c/dublin.html 135,366 px tall against a
  real 101,422 at 1366 (+33%) and 171,209 against 139,665 at 412 (+23%). The estimates are now
  17px under a row's real height: **40px**, 60px up to 640px wide and 78px up to 400px wide
  (medians 56.7, 76.3 and 94.4 px at 1366, 412 and 360). The page heights are 101,334 (-0.1%),
  136,981 (-1.9%) and 168,149 (+4.5%).
- **The directory section is sized from its rows**, 38px for the heading and rule plus 26.6px a
  row, from `--n` (areas) and `--r` (two-column rows, `ceil(n/2)`, because a calc() cannot round
  up in every browser) on the section, 30px a row up to 400px wide where long names wrap. The
  page is 30,547 against a real 30,554 at 1366, 58,892 against 59,585 at 412 and 66,065 against
  66,674 at 360. The search rewrites both properties to the rows still shown.
- **A focus ring is clipped** by the paint containment `content-visibility` implies: with no
  `overflow-clip-margin` the left edge of the ring on a "What the notice says" summary is cut
  flat at the row's edge, with `6px` it is identical to the page without the rule (screenshots
  at 3x). Checked in Chromium 141 only.

**Checked, 360 / 412 / 1366 wide, 4x CPU.** Scrolling the whole page down and up: layout shift
**0** on all four pages. Anchor jumps on a cold load (`areas.html#c-wicklow`, `#c-cork`,
`c/dublin.html#open`, `#notices`, `#months`, `#areas`, an area page's `#notices`): shift 0 and
the target in the same place after 300 ms and after 1.8 s; the jump nav on areas.html lands at
its scroll margin (12px, 104px at desktop). Once every row has been drawn the layout equals the
layout with the rule forced off: 0 of 3,259 elements differ by more than 0.2px at each width.
Find-in-page (`window.find`) reaches the last of 1,733 rows and brings it into view. Printing
c/cork.html gives the same 76 pages and 27,959 words as before, and the last row is in the PDF.
Text is rasterised on a slightly different pixel grid inside a contained row (1px, not a layout
change), so screenshots are not byte-identical.

**Rejected, desktop, anchor jump to `areas.html#c-wicklow` unless stated.**
- A flat `contain-intrinsic-size: auto 1500px` on every section: shift **0.0652**, the footer
  moving when the real section replaced the estimate.
- `--n` alone: **0.0009**, half a row of error on a section with an odd row count. `--r` took
  it to 0.
- `content-visibility` on `ul.areas li`: **0.162** at `#c-wicklow` (the target landed 39px from
  the top instead of 104) and 0.038 at `#c-cork`. The list is `columns: 2`, so a row is not
  independently sized, and `ul.areas li` is left alone.


### Amended after review, 2026-10-02

A section drawn once keeps its last height while skipped: Chromium gives every `content-visibility: auto` element `contain-intrinsic-size: auto` whether the rule says so or not, so the search's rewrite of `--n`/`--r` reached only sections never painted. After scrolling the whole directory, a search for "bally" left a 14,987 px page over 4,210 px of rows at 1366 px (34,589 against 6,157 at 412). A search now adds `.searching` to the body, which draws every section (`content-visibility: visible`): the filtered list is short, and the page is exactly as tall as its rows. Clearing the search leaves each section its filtered height until it comes near the screen, so the scrollbar runs short for a while (17,864 against 30,554 px); anchor jumps after clearing still measured 0 CLS at both widths. The sections also took the 6 px `overflow-clip-margin` the notice rows already had, for the focus rings on edge links.

## The first render's data is inline - 2026-10-02

With the footer held back (the entry above) the first paint still waited on `data.js`: 216 KB
raw, 28.4 KB gz, a blocking `<script>` at the end of the body. The first overview reads one
month of every county, so most of it is not needed to draw. Lab, 4x CPU, median of 3, on the
gated page: LCP **692 ms at 412px and 1,216 ms at 3g** (slow 4G otherwise: 692 at 360px, 728 at
1366px).

**Decision.** `write_site` derives the first render's data from the same dict as `data.js`
(`first_render_payload`) and inlines it in `index.html`: the month list, the newest month of
every county (grade, day bars, counts), its `pop` and `open_total`, the newest month nationally
and `top_months`, the list of months that have a ten largest. **18.4 KB raw, 1.8 KB gz**, 44%
of it the day arrays; `index.html` goes from 20.0 to 22.5 KB gz. `data.js` is **unchanged**, a
complete payload (211.6 KB raw, 28.4 KB gz), and is loaded by `loadShard` after the first
render; when it lands the app rebinds `D` to it (`window.UISCE_DATA`), so there is no merge.
`INITIAL_BUDGET` still means index.html plus data.js (299.9 KB of 512), and the settled rows
about `towns`, `resolved` and the budget stand: this adds an inline subset and removes nothing.

- **What waits.** The month switcher, the county, top-ten and open views read older months, the
  open lists and the top tens, so `render()` shows a "Loading..." note in a `#waitview`, with
  the footer held, until `data.js` is there, then renders. The area view needs only its own
  shard and no longer waits for anything (a deep link to `#area/...` or `#county/...` had to
  fetch `data.js` before it could start its shard; now the shard starts at once). A failure
  shows "This view's figures did not load" with a way back, a month tab that cannot load is put
  back, and the next navigation retries, as it does for a shard.
- **A field added to a county goes inline by default.** The county's `months` and `open` are the
  two things taken out; a new key rides in the first render until someone decides otherwise,
  because the other failure, a first render missing a field, is silent in `site.html`.
  `tests/test_first_render_data.py` holds the key sets, so adding one is a decision.
- A `<` in the inline JSON is written `\u003c`, so no string can close the script element.

**After.** LCP at slow 4G **416 ms at 360px, 452 at 412px, 452 at 1366px** (from 692, 692 and
728), and at 3g **732 ms at 412px and 728 at 360px** (from 1,216 and 1,216). Load CLS 0 at
360, 412 and 1366; the area click, both deep links and the county click are still 0. Clicks
made before `data.js` arrived (a county, a month tab, the open tile and the top-ten link, 3g,
412 / 1366 / 1920 px): CLS 0, a waiting note, and then the same DOM as the previous template.

**Checked.** The new page against the previous template, over the same data, 1366 and 412px:
the same body markup, scroll position and class after each of 17 steps (month tabs, county,
month inside the county, a day, sort, an area, back twice, top ten and its month, open, home,
search and pick) and 7 deep links (counties, an area by number and by ED code, `#top`, `#open`,
an unknown county): 0 of 48 differ. Failure paths, each in a browser: no JavaScript, `file://`
(a county click and `#top`), `data.js` 404 or blocked (overview draws; a county shows the note
and the way back; a month tab is put back), `data.js` stalling past the loader's 10s, a failure
followed by a retry that works, and a corrupted inline payload (the `load` event reveals the
page, as it does for any first render that throws).

**Rejected.**
- *A `data.js` of the rest alone* (older months, open lists, top tens: 175 KB raw, 25.6 KB gz
  against 28.4): 2.8 KB gz less per visit, and a merge step, five tests rewritten, and a page
  cached across a deploy (`max-age=600`) breaking for up to ten minutes, because its `data.js`
  would no longer be the payload it expects. With the file whole an old page and a new
  `data.js` still agree. The saving is after the first render and does not move LCP.
- *`<link rel="preload" href="data.js">`* beside the inline data: LCP 436 at slow 4G and 748 at
  3g (412px) against 452 and 732 without it. The first render no longer needs the file.
- *Rendering the first overview into the HTML at build time.* The audit's prototype (a captured
  DOM plus a preload) reached LCP 248 at slow 4G and 424 at 3g (412px), and CLS 0. It needs a
  second implementation of `renderOverview` in Python that must stay byte-identical to the
  JavaScript one, which is the cost this change does not take.
- *A silent hold in `render()`* (leave the old view up until `data.js` arrives): no feedback on
  a slow link and no failure path; the page would look dead after a blocked request.

**Not done.** `data.js` is still requested by a visit that never leaves the overview. It
arrives after the first render, so it costs no LCP, only 28.4 KB gz of transfer.

### Amended after review, 2026-10-02

- A `data.js` that lands after loadShard's 10 s timeout is the data all the same: `loadAll`'s callback and `render()` now adopt `window.UISCE_DATA` whenever it is no longer the inline object, instead of only on an `"ok"` state. Before, a slow first load left every county, top and open view on "did not load" for the rest of the session with the payload already in memory. Measured with data.js held 12 s: the failure note at 10 s, the county view on the next navigation.
- Only the overview waits on data.js for an older month. The area view reads its shard alone, and was being held behind "Loading..." (or the failure note) whenever an older month had been picked.
- A cached `index.html` can meet a newer `data.js`, because `?v=` busts the browser cache, not Pages'. `adopt()` re-reads the latest month and the top-ten months from the newer build when `generated` differs, and moves a reader who was on the latest month onto the new one; before, the open-now badges would sit on the wrong month after a rollover.
- The waiting note carries a way back: to the latest month from the overview, to all counties (on the latest month, so the link lands on something drawn) from a drill-down.
- An older `data.js` than the page, which an edge cache can serve after a deploy, is not adopted: `generated_iso` is compared and an older payload counts as a failed load, rather than moving the page back a month.
- Not fixed here: nothing redraws the moment a late `data.js` lands, because loadShard ignores an onload after its timeout, so the reader sees the failure note until the next navigation. The county and history shards share the defect and never recover, since their state stays `"error"`. The fix belongs in statusui's loadShard.
- Clearing a search leaves each section its filtered height until it is near the screen. Keeping `.searching` one more frame would record the full heights, at the price of laying out the whole directory on the keystroke that clears it, which is the 700 ms long task the skipping exists to avoid; left as it is. One measurement in four of a programmatic jump to `#c-wicklow` straight after clearing a search shifted 1.09 at 1366 px (0 in the rest, and 0 at 412 px), as sections settled from their filtered heights around the target; a reader's own click on the nav is input and is not counted, and a cold load never searched has no filtered heights to settle.
- `first_render_payload` names its top-level keys instead of copying all but three, so a key added to the payload later cannot ride into the HTML unnoticed; and the build log prints the inline payload's size.
