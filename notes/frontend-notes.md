# Frontend notes

Notes on `site.html` / `areas.html` / `county.html`, kept here so the reasoning isn't lost to chat history. See [how-it-works.md](how-it-works.md) for how the three pages fit together.

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

### Left open

The *fills* still fail the 3:1 non-text threshold against the light page — `--warning` 1.74:1, `--serious` 2.50:1 — which matters for the legend swatches, where the colour itself is the meaning rather than a backdrop for a letter. The review checked `--maint` against this threshold but not the others. Not addressed here: changing the fills reaches the bars and the county grid, which is a bigger visual decision than a text-contrast fix.

Also noted and not taken: the overview is entirely JS-rendered with no `<noscript>` fallback (the county pages are static, so the content exists — it is the pointer that is missing); the health mark explains itself only through `title=`, which never fires on touch; and the sort `<select>` has no programmatic label. The first needs a wording decision, the other two touch generated markup the tests pin.
