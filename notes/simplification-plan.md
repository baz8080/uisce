# Simplification plan (owner decision 2026-10-06)

**Simply put:** the site stops estimating how many people lost water and counts what it can
see: outage notices per 100 km of water main, per county, per month, a letter cut on that
count, and the median time to "works complete" beside it. Then a reader can look up their
own Water Supply Zone. Then every note is audited against the new method; the rest is
archived. Eleven PRs, the site shippable after each; three questions for the owner, asked
before the session that needs them.

Every kick-off prompt is "Implement session N of notes/simplification-plan.md", so only the
checkpoints are spelt out below. Model and effort are the cheapest that is safe.

## Phase 0: land what exists

**0. Interim honest state.** Goal: the live site says what its figures measure while the
method changes, and the evidence for this plan is on `main`. PR "Say what the figures
measure": the site.html copy fixes, frontend-notes.md "The page said more than the method",
its CLAUDE.md row, the "Density sensitivity" and "Supply zones" sections of
statuspage-methodology.md, the roadmap entry and this plan. **No new code**:
`eval_footprint.py`, its tests and its pyproject entry are dropped, because session 4 removes
what they measure; the script is kept on branch `archive/eval-footprint`. Sonnet,
low. Depends on: nothing. Done when: ruff and pytest pass, Pages shows the new copy.

## Phase 1: count, don't estimate

**Checkpoint A (answered 2026-10-06):** the CC BY 4.0 water.ie spreadsheet has zone names,
codes, local authority and population, but **no mains length**; that is only on the ArcGIS
layer, whose licence is unstated. Owner: proceed on the layer with attribution to Uisce
Éireann, and ask them for terms.

**1. Mains per county.** Goal: a committed table of km of main per county. PR "Mains length
per county": `data/wsz_mains.csv`, a `uisce-fetch-wsz` script (attributes only), the
LA-to-county merge for Dublin, Cork and Galway, a note on zones crossing county lines.
Sonnet, medium: a specified fetch and aggregate. Depends on: A. Done when: counties sum to
53,756 km within 1% and a test pins the merge.

**Checkpoint B (answered 2026-10-06):** letters cut on fixed thresholds of notices per 100 km
per month (readable, re-fitted yearly) or on archive quantiles (always fills A to F, moves
every build)? Owner: fixed.

**2. The count metric.** Goal: `site.py` computes notices per 100 km per county-month and the
letter on it; the median is unchanged. PR "Count notices per 100 km of main": new payload
keys beside the old, the cut and its rejected alternative recorded in
statuspage-methodology.md with the May-Sep distribution. Fable, high: the cut must survive the
archive growing. Depends on: 1, B. Done when: Kerry 23.8 and Carlow 4.4 reproduce for
May-Sep 2026 and the payload-shape tests are updated deliberately.

**3. The page says the count.** Goal: the front end shows the new figures and none of the old.
PR "The page counts notices": a "Simply put" block ahead of every method section, tiles,
banner and county rows on the count, "expected back by" on open notices with a stated end,
availability and 500 m prose gone. Opus, high: large templates and strict copy rules. Depends
on: 2. Done when: no page contains "availability" or "500" and an open notice with a
scheduled end shows "expected back by".

**4. Remove the estimate.** Goal: the code no longer carries what the page no longer says. PR
"Remove the population estimate": `SmallAreaIndex`, `sa_pop.py`, `data/sa_pop.csv`,
`eval_overlap.py`, imputed spans, `union_seconds`, their scripts and
tests. Area pages today map a pin to an area through Small Areas inside the circle; re-base on
nearest settlement centroid (`sa_towns.csv`) and write down how many of the 739 areas change.
Opus, high: a 2,790-line file, 790 tests, one mapping that must not move silently. Depends
on: 3. Done when: pytest passes and the set of area pages differs only by a measured, recorded
amount.

## Phase 2: notes audit

**5. Audit every .md.** Goal: the notes describe the site as it now is. PR "Notes audit":
every file in notes/, README.md and CLAUDE.md read; sections defending availability, the
circle, imputation or population weighting move unedited to `notes/archive/`; a short
`notes/README.md` indexes the rest; CLAUDE.md's Settled table keeps only rows that still bind;
how-it-works.md gets a "Simply put". Fable, medium: judging what binds is the job, the edits
are mechanical. Depends on: 4. Done when: no live note describes a figure the site does not
publish and every Settled row points at a live section.

## Phase 3: your supply zone

**6. Zone lookup.** Goal: each pin knows its zone. PR "Water Supply Zones": the fetch gains
geometry, simplified and committed as `data/wsz.geojson` (under 3 MB, re-fetched by hand,
diffed on re-fetch); a pure-Python ray-cast with a bbox prefilter, no shapely (14k pins by 688
polygons is seconds); zone assigned at build, no schema change. Opus, medium. Depends on: A,
4. Done when: 95.4% of distinct pins land in a zone and a known pin tests to a known zone.

**Checkpoint C:** while the archive is under twelve months, does a zone page say "in the
past year" or "since D Month 2026"? Recommended: "since".

**7. Zone pages.** Goal: `z/<slug>.html` for 688 zones. PR "Zone pages": outages in the
window from C, median fix time, repeat spots (pins recurring within 200 m, named by nearest
area), the health marker, and for pins in no zone the message that about one in five homes is
on a group or private scheme, linking the nearest area page. Opus, high: new template and
payload. Depends on: 6, C. Done when: 688 pages build and the out-of-zone text shows on the
index.

**8. Find your zone by place.** Goal: the search box reaches a zone. PR "Search reaches the
zone": scheme names join the index, an area hit lists the zones its pins fall in. No map.
Sonnet, medium. Depends on: 7. Done when: "Abbeydorney" offers its zone.

**9. Map tap (optional).** Goal: tap a map to find a zone. Upstream PR in `../statusui` adding
a Leaflet map with OSM tiles, then a pin bump here. Opus, medium. Depends on: 8 and an owner
yes: it is the first third-party script and tile host the sites load. Done when: a tap on
Tralee opens its zone page.

## Phase 4: close

**10. Audit, second pass.** Goal: notes cover the zones and nothing stale. PR "Notes audit,
zones": zone decisions dated with alternatives, their Settled rows, roadmap pruned, this plan
moved to `notes/archive/`. Sonnet, medium. Depends on: 9, or the owner declining it. Done
when: roadmap has no entry this plan closed.

## Risks and open questions

- The licence gates sessions 1 and 6: mains length and zone shapes are only on the ArcGIS
  layer. The spreadsheet's CC BY covers zone populations, which alone would bring back per-head.
- Zones cross county lines (Louth holds 110% of its population), so notices placed by pin are
  divided by mains placed by zone; measure the mismatch in session 2 and say it.
- Re-basing areas in session 4 can drop a permalink; the diff is recorded before merge.
- 81 zone boundaries are under review; a re-fetch can move pins silently.
- The count ignores size: a village notice and a city notice each count one. Say so.
