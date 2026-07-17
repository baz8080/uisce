# Population data sources

The open datasets behind `data/sa_pop.csv`, the Small Area population lookup that `uisce-site` uses to population-weight availability (see [statuspage-methodology.md](statuspage-methodology.md)). Everything here is free, keyless, and unthrottled. `uisce-fetch-sa-pop` (src/uisce/sa_pop.py) automates the whole join; it only needs re-running if the CSO revises the Small Area geography.

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

## How the lookup is used

A notice pin is assumed to affect the Small Areas whose centroids lie within 500 m (nearest Small Area within 8 km as a rural fallback). Centroids are grid-hashed in 0.01° bins, so the radius query is pure-Python fast — no GIS dependencies. County totals used for the availability denominator are hardcoded Census 2022 figures in site.py.

## Future refinement: EPA public water supplies register

Boil-water notices name their supply scheme in the `location` field ("Ballymacarbry Upper Public Water Supply"), and the EPA's register of public water supplies records **population served per scheme** — a better affected-population estimate for quality notices than any radius. Not yet integrated.
