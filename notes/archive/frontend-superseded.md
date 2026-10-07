# Frontend notes, superseded entries

**Simply put:** three entries from frontend-notes.md that a later entry replaced. They are
kept as written, except that links to sibling notes now point one directory up. The live note is [../frontend-notes.md](../frontend-notes.md); each entry
below names the one that superseded it.

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

*Superseded by "The iPhone review pass 2026-08-19": the strip scrolls.*

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

*Superseded by "The page counts notices" (2026-10-06): the availability copy is gone with the figures it qualified.*

## The page said more than the method - 2026-10-04

water-sla-benchmarks.md has always called the availability figure an exposure index, two to
three orders of magnitude above a regulator's measured minutes by construction. The index
page did not: the national tile read "hours without water, added up across everyone
affected" and the banner "typical outage 6.1h". Annualised from May to September the
person-hours come to 48 hours per person per year, against about a quarter of an hour for
Ofwat's sector figure, so "without water" was a claim the method cannot make.

- The tile reads "hours of announced outage, added up across everyone in range", the pair of
  its neighbour "of people's time with no outage announced".
- The banner uses the county tile's name for the same figure: typical time to "works complete".
- "What this measures" says a notice counts for everyone within 500 m for as long as it
  stands, and that the figures cannot be compared with a regulator's.
- "What the letters mean" says the cuts are fitted to this site's own record and that the
  letters lean on the 500 m assumption (statuspage-methodology.md, "Density sensitivity").

"Availability" keeps its name: it is the grade's basis on every surface, and the caveat now
sits where the word is defined.
