# Frontend notes

Notes on `site.html` / `areas.html` / `county.html`, kept here so the reasoning isn't lost to chat history. See [how-it-works.md](how-it-works.md) for how the three pages fit together.

## Shared with esb and lifts since 2026-08-19: the design layer lives in `statusui`

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

The *fills* still fail the 3:1 non-text threshold against the light page — `--warning` 1.74:1, `--serious` 2.50:1 — which matters for the legend swatches, where the colour itself is the meaning rather than a backdrop for a letter. The review checked `--maint` against this threshold but not the others. Not addressed here: changing the fills reaches the bars and the county grid, which is a bigger visual decision than a text-contrast fix.

Also noted and not taken: the overview is entirely JS-rendered with no `<noscript>` fallback (the county pages are static, so the content exists — it is the pointer that is missing); the health mark explains itself only through `title=`, which never fires on touch; and the sort `<select>` has no programmatic label. The first needs a wording decision, the other two touch generated markup the tests pin.

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
"Partial month — in progress" reads "Month in progress."; the health key names two notice
kinds, not three ("do-not-consume" folds into "do-not-drink" for a lay reader — but not
"water quality issue", which would collide with the legend's "Water quality notice" category,
and the mark exists to say something stronger); and "What this measures" went behind a footer
disclosure like its two siblings — `id="method"` stays on the methodology block, which
`openMethod()` and two links target.
