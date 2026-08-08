# Frontend notes

Notes on `site.html` / `areas.html` / `county.html`, kept here so the reasoning isn't lost to chat history. See [how-it-works.md](how-it-works.md) for how the three pages fit together.

## Fixed 2026-08-06: `hidden` needs `!important`, or an author `display` wins

Both pages are hand-written HTML that switch views on and off with the `hidden` attribute. The UA stylesheet's rule for it is a plain `display: none`, which any author `display` on the same element outranks — the element then stays on screen while the page believes it is gone.

That was not hypothetical. `#overview { display: flex }`, added for the narrow-screen column reorder, did exactly that under 640px: the overview stayed rendered underneath every drill-down. On a phone, tapping a county appeared to do nothing — the router scrolled to the top of an overview that had never left — and a reload landed on an un-rendered overview (an empty `.banner` box) with the county view thousands of pixels below it.

**Fix:** `[hidden] { display: none !important; }` in `site.html`, so `hidden` wins regardless of whatever `display` a future layout rule sets. `tests/test_site_css.py` guards the invariant generally: for every element either page hides, it works out which `display` actually wins once `hidden` is set, in every `@media` context the stylesheet defines, so the same class of bug on a different element or a different breakpoint fails a test instead of shipping. The parser is deliberately small — it reads only the `display` property out of the two files it's pointed at, not CSS in general.
