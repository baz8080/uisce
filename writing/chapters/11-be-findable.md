# 11. Be findable
*~5 min read · PRs #37–#39 · 6–8 August 2026*

*Where we are:* the page reads well on a phone (chapter 10). Nobody can find it. This short
chapter is about why a site that is entirely public was invisible to search engines, what
fixed it, and a retraction.

## The question that opened this stretch

The question I actually asked was whether buying a custom domain would help people find the
site. The answer was no, not much — `github.io` is on the Public Suffix List, so the site is
already treated as its own property with no shared-authority penalty. But asking it made the
real problem obvious: the site was **two indexable URLs**. `index.html` and `areas.html`.
Everything a reader might search for — a county, a town — lived behind a hash route
(`#county/Cork`), and the text itself existed only inside a JavaScript data file. Someone
searching for "water outage Cork" had nothing to land on.

> **Concept: why a JavaScript-routed static site is invisible.** A search engine indexes
> *documents at URLs*. The part of a web address after `#` — the *fragment* — is never sent to
> the server and is not, to a crawler, a different page: `/uisce/#county/Cork` and
> `/uisce/#county/Kerry` are the same document, whose visible text is whatever the page shows
> before any script runs. A "single-page app" like this one draws all its content with script,
> from a data file, after load. To a crawler it is one page with a banner on it. The content is
> not hidden or private; it is simply not *addressable*, and what cannot be addressed cannot be
> indexed, linked to, or previewed.

## What changed

### PR #37: a real page for every county

Twenty-six server-rendered county pages at `c/<county>.html` — plain HTML written at build time,
carrying the same figures the app draws: summary and current grade, open notices, the month
table, the notice history, and every area with its notice count. No data file and no history
shard on these pages; the interactive view is one link away rather than reproduced. Plus the
discovery files the site had never had — `sitemap.xml`, `robots.txt`, a self-referential
canonical on every page — and a single `BASE_URL` constant, because a `github.io` site cannot
redirect if it ever moves.

| | before | after |
|---|---|---|
| Indexable URLs | 2 | **28** |
| Static text across the site | 73,087 chars | **383,714** |
| Pages reporting to analytics | 1 | **28** |

Two bugs fixed on the way, both of the "specificity" kind that only surface when a page is
looked at rather than tested: the directory's search matched county *headings*, and the heading
now carried the county-page link, so searching "page" would have selected all 26 counties; and
grade **C** rendered white-on-amber because one CSS selector outranked another.

### The retraction

Chapter 8b footnoted PR #25 (27 July): it added `history.pushState` to the in-page navigation
so that the analytics beacon would count a county drill-down as a page view. **It does not do
that, and no variation on that call would.** What it pushes is a fragment, so the path stays
`/uisce/` for the whole session, and a beacon that counts views by path has no new page to
report. The measurement had been silently wrong for ten days — one page view per session,
whatever the reader did.

The `pushState` stayed, because it was doing a second, real job the original description had
not claimed: with the `popstate` listener it is what makes the browser's back and forward
buttons work across drill-downs. The comment in the code now says what it achieves rather than
what was hoped. What actually fixed the analytics was PR #37 — real documents at their own URLs
— and the beacon also went onto `areas.html`, which had never had it despite being the largest
single page on the site.

### Worked example: what a search engine saw

Before: request `/uisce/`, receive ~73,000 characters of HTML, of which the readable text is a
banner and a methodology paragraph. Request `/uisce/#county/Cork`: the fragment is not sent;
receive the same 73,000 characters. Conclusion: one page about water, no page about Cork.

After: request `/uisce/c/cork.html`, receive a document whose title, heading, tables and history
say *Cork* — the grade, the open notices, the areas — and whose canonical URL is itself; the
sitemap lists 28 such URLs. Conclusion: a page about Cork water disruptions exists, and can be
returned for "water outage Cork". The interactive page is unchanged; it just stopped being the
only door.

### PRs #38–#39: two small tidy-ups

The historic county page already linked back to the interactive view; nothing pointed the other
way. PR #38 added the reverse link in the footer, shown only while viewing a county, and fixed
the footer's disclosure arrows, which had rendered flush against the page edge. PR #39 removed
comments in the code that duplicated what `notes/` already said — 233 lines gone — on the
principle chapter 8b's orientation note established: the code names the thing, the note owns
the number and the reason, and a figure that lives in two places drifts.

## Where it left the site

Twenty-eight addressable pages, a sitemap, a robots file, honest analytics, and a retracted
claim. From here the site could be found by someone in Cork wondering about Cork. The next, and
so far last, stretch of work returned to the numbers — to the one class of event that the site
had been quietly counting as zero.

## Notes

- PR #37 (6 Aug 2026): 26 `c/<county>.html`; `sitemap.xml`, `robots.txt`, canonicals,
  `BASE_URL`; 2 → 28 URLs, 73,087 → 383,714 chars, 1 → 28 pages reporting; directory search
  "page" bug; grade C contrast bug; 339 tests (+14); county pages make one request (the beacon).
- PR #38 (8 Aug): reverse link + disclosure arrows. PR #39 (8 Aug): +113/−233, comments that
  duplicated `notes/*.md`.
- PR #25 (27 Jul): `history.pushState` for analytics — retracted in #37; retained for
  back/forward.
- Public Suffix List: `github.io` treated as its own property; a custom domain would not have
  changed the indexable surface.
