# Population data sources

The open datasets behind the two committed lookups `uisce-site` depends on: `data/sa_pop.csv` (Small Area populations, used to population-weight availability) and `data/sa_towns.csv` (which named settlement each Small Area belongs to, used for the county → town drill-down). See [statuspage-methodology.md](statuspage-methodology.md) for what they feed. Everything here is free, keyless, and unthrottled. `uisce-fetch-sa-pop` (src/uisce/sa_pop.py) and `uisce-fetch-towns` (src/uisce/towns.py) automate the joins; neither needs re-running unless the CSO revises the geography.

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

`SA_GUID_2022` matches the SAPS `GUID` for **all 18,919** Small Areas, and the joined populations sum to **5,149,139 — the exact Census 2022 state total**. `uisce-fetch-sa-pop` checks this invariant and warns if it drifts.

## Settlements — the named towns behind the drill-down

Two more datasets, joined on the settlement code, produce `data/sa_towns.csv`.

- **Boundaries.** CSO Urban Areas 2022, same ArcGIS org as the Small Area centroids: `https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/Urban_Areas_National_Statistical_Boundaries_2022_Generalised_20m/FeatureServer/5` — 867 features with `URBAN_AREA_CODE`, `URBAN_AREA_NAME`, `COUNTY` and polygons. All 867 fit in one page (maxRecordCount 2000), so there is no pagination; `uisce-fetch-towns` raises if `exceededTransferLimit` ever comes back true rather than silently taking a prefix. Polygons at 20 m generalisation are ~2.9 MB / 76,582 points, fetched and discarded — only the assignment is committed.
- **Populations.** SAPS 2022 **Built-Up Areas**: https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_BUA_270923.csv. Join key is `GEOGID` = `URBAN_AREA_CODE`; population is `T1_1AGETT`, as for Small Areas. **This file is cp1252, not the utf-8-sig of the Small Area file** — the fadas in Irish-language placenames ("Dumha Thuama") are single-byte and utf-8 decoding dies at byte 8073. It also carries an **`Ireland` state-total row**, so it has 868 rows against 867 settlements; iterate the boundary layer rather than the CSV and it never becomes a phantom settlement.

Assignment is centroid-in-polygon: a Small Area belongs to the settlement whose boundary contains its centroid. Pure Python, even-odd ray casting summed across all of a feature's rings so multipart settlements and holes need no winding-order interpretation, with polygons binned by 0.1° of latitude to keep it to a fraction of a second. No GIS dependency, matching the grid-hash approach in `site.py`.

### Verification

**12,837 of 18,919** Small Areas (67.9%) fall inside a settlement, carrying **3,539,104** people — 97.5% of the 3,630,501 the SAPS file publishes for those settlements, and consistent with Census 2022's ~70% urban share. Per town the recovery is near-exact: Naas 25,824 against a published 26,180, Newbridge 24,366 against 24,366, Celbridge 20,601 against 20,601, Leixlip 16,733 against 16,733.

The shortfall is concentrated in small villages, where a single Small Area centroid landing just outside the boundary is a large fraction of the total (Allenwood 1,233 against 1,685). `uisce-fetch-towns` therefore only warns for settlements over **5,000** people that recover less than **80%** of their published population — a real geography error would show up there, and no town currently trips it.

Populations are deliberately **not** written to `data/sa_towns.csv`. `site.py` sums the Small Areas assigned to a town instead, so town figures and the county availability denominator come from one source and cannot disagree; the published Census figures are fetched purely to check the join.

## How the lookups are used

A notice pin is assumed to affect the Small Areas whose centroids lie within 500 m (nearest Small Area within 8 km as a rural fallback). Centroids are grid-hashed in 0.01° bins, so the radius query is pure-Python fast — no GIS dependencies. County totals used for the availability denominator are hardcoded Census 2022 figures in site.py.

For the drill-down, those affected Small Areas are mapped through `sa_towns.csv` and the pin is placed in whichever settlement holds the largest share of the affected population. See the drill-down section of [statuspage-methodology.md](statuspage-methodology.md).

## Future refinement: EPA public water supplies register

Boil-water notices name their supply scheme in the `location` field ("Ballymacarbry Upper Public Water Supply"), and the EPA's register of public water supplies records **population served per scheme** — a better affected-population estimate for quality notices than any radius. Not yet integrated.
