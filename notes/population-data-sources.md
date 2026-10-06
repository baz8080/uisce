# Population data sources

The open datasets behind the committed lookup `uisce-site` depends on: `data/sa_towns.csv`, each Small Area's centroid, Census population and the named area it belongs to, used to place a pin and to print an area's population. See [statuspage-methodology.md](statuspage-methodology.md) for what it feeds. Everything here is free, keyless, and unthrottled. `uisce-fetch-towns` (src/uisce/towns.py) automates the joins and needs re-running only if the CSO revises the geography.

Until 2026-10-06 the centroids and populations were a second file, `data/sa_pop.csv`, from a second command joining the SAPS populations to the same layer's centroids; the two were folded together when the population estimate was removed (statuspage-methodology.md, "The estimate is removed").

## SAPS 2022 — population per Small Area

- CSV (≈39 MB): https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_Small_Area_UR_171024.csv
- Landing page: https://www.cso.ie/en/census/census2022/census2022smallareapopulationstatistics/
- Column glossary: https://www.cso.ie/en/media/csoie/census/census2022/Glossary_Saps_2022_REVISED_21102024.xlsx

Join key is the `GUID` column; total population is **`T1_1AGETT`** (theme 1, all ages, both sexes). 18,920 rows. The file ships with a UTF-8 BOM — read it with `encoding="utf-8-sig"`.

## Small Area centroids — Tailte Éireann / CSO ArcGIS

- FeatureServer layer (generalised 20 m view): https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0 — note "Genralised" is a typo in the live service name. Rediscoverable via ArcGIS item `c1787e2003f543828995a2889efa1c7a` (`https://www.arcgis.com/sharing/rest/content/items/<id>?f=json` → `url`).
- No polygon download is needed: query with `returnCentroid=true&returnGeometry=false&outFields=SA_GUID_2022&outSR=4326` and paginate with `resultOffset` (maxRecordCount 2000; 18,919 features in 10 pages, seconds to fetch).
- Electoral Division boundaries exist under the same owner (IE-CSO_Maps) if a coarser geography is ever wanted, e.g. `CSO_ELECTORAL_DIVISIONS_National_Statistical_Boundaries_2022_Generalised_100m`.

## Verification

`SA_GUID_2022` matches the SAPS `GUID` for **all 18,919** Small Areas, and the joined populations sum to **5,149,139, the exact Census 2022 state total**. `uisce-fetch-towns` checks this invariant and warns if it drifts.

## The drill-down geography — all of it from Small Area attributes

`data/sa_towns.csv` maps every Small Area to the named area a notice pin there belongs to. It needs no boundary polygons at all, because the Small Area layer already carries the answers as attributes:

`https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0` - the same layer that gives the centroids, fetched in the same query - exposes **`SA_URBAN_AREA_NAME`** (the Census settlement the Small Area is in, blank if none), **`CSO_LEA`**, **`ED_ENGLISH`** and **`COUNTY_ENGLISH`** alongside `SA_GUID_2022`. Query with `returnGeometry=false` and paginate; 18,919 rows in ten pages, a couple of seconds.

Two supporting fetches:

- **Settlement codes.** The Urban Areas layer (`Urban_Areas_National_Statistical_Boundaries_2022_Generalised_20m/FeatureServer/5`), attributes only: `URBAN_AREA_CODE`, `URBAN_AREA_NAME`, `COUNTY` for 867 settlements in one page. The Small Area carries its settlement's *name*, not its code, so this supplies a stable key.
- **Published populations**, for verification only: SAPS 2022 Built-Up Areas, https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_BUA_270923.csv. Join key `GEOGID` = `URBAN_AREA_CODE`, population `T1_1AGETT`. **cp1252, not the utf-8-sig of the Small Area file** — the fadas in Irish-language placenames ("Dumha Thuama") are single-byte here and utf-8 decoding dies at byte 8073. It also carries an `Ireland` state-total row, so it has 868 rows against 867 settlements; iterate the boundary layer rather than the CSV and it never becomes a phantom settlement.

### Joining a Small Area to its settlement

On `(name, county)`, with the county mapped from the 34 local authorities to the 26 traditional counties the site uses (strip a trailing ` CITY`; name the Dublin four and the two Tipperaries — `county_name` in `towns.py`). The pair is needed because **19 names are shared by unrelated settlements**: there is a Milltown in Kerry, another in Kildare and a third in Galway, and joining on name alone would merge them.

A settlement may also genuinely straddle a county line, leaving its minority-county Small Areas with no matching pair — Limerick's agglomeration reaches into Clare, Waterford's into Kilkenny, Drogheda into Meath. Those fall through to the name, which is unambiguous for every straddler on file. Measured: **13,060 matched on the pair, 125 straddlers, none ambiguous, none unresolved.**

### Verification

Summing Small Area populations reproduces **all 867 published settlement populations exactly**, and the urban total is **3,630,501 — the published figure to the person**. `uisce-fetch-towns` asserts that equality per settlement rather than allowing a tolerance: the CSO does the assignment itself, so any drift means the two datasets have stopped describing the same geography.

This is why the attribute is used rather than geometry. An earlier implementation derived the same mapping by point-in-polygon over downloaded boundaries, and it was both heavier and wrong in ways that mattered: 37 MB of polygons and ~60 lines of ray casting, recovering only 97.5% of urban population, **dropping 54 settlements whose boundary happened to contain no Small Area centroid** (Knockbridge, Termonbarry, Kilmore Quay — their cases fell into the rural bucket and the village never appeared), and leaving **187 of 789 settlements more than 10% short**. Doneraile came out at 214 people against a published 857, and since the site divides by that population to get availability, a burst there read about four times worse than it was.

### Cities and countryside

`CSO_LEA` and `ED_ENGLISH` come from the same attribute query, so the other two tiers are free:

- A settlement over 50,000 is split into its Local Electoral Areas. The share of each LEA lying inside the city is measured by summing Small Areas, so no separate LEA population file is needed.
- A Small Area in no settlement is grouped with the rest of its Electoral Division's countryside, as "Around <ED>".

See the drill-down section of [statuspage-methodology.md](statuspage-methodology.md) for why those two layers and not one.

## How the lookups are used

A notice pin is placed in the area of its nearest Small Area centroid within 8 km, and is unplaced when that Small Area lies in another county than the notice names. Centroids are grid-hashed, so the lookup is pure-Python fast, with no GIS dependencies. Until 2026-10-06 a pin was instead assumed to affect every Small Area within 500 m, and placed in the area holding most of that population (statuspage-methodology.md, "The estimate is removed"). County populations are hardcoded Census 2022 figures in site.py, printed beside each county. See the drill-down section of [statuspage-methodology.md](statuspage-methodology.md).

## Future refinement: EPA public water supplies register

Boil-water notices name their supply scheme in the `location` field ("Ballymacarbry Upper Public Water Supply"), and the EPA's register of public water supplies records **population served per scheme** — a better affected-population estimate for quality notices than any radius. Not yet integrated.
