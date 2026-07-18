"""One-time fetch of Census 2022 Small Area centroids + populations.

Joins the CSO SAPS small-area CSV (total population, column T1_1AGETT) with
Small Area centroids from the Tailte/CSO ArcGIS FeatureServer, and writes
data/sa_pop.csv (guid, lon, lat, pop) — the lookup uisce-site depends on.
Both sources are open data; see notes/population-data-sources.md.

The result is committed, so this only needs re-running if the CSO revises
the Small Area geography (next census).
"""

import csv
import io

from uisce.config import SA_POP_PATH, make_session

SAPS_CSV_URL = (
    "https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_Small_Area_UR_171024.csv"
)
# "Genralised" is a typo in the real service name
CENTROIDS_URL = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0/query"
)
PAGE_SIZE = 2000
CENSUS_2022_STATE_POP = 5_149_139


def fetch_saps_populations(session):
    """SA GUID -> total population from the SAPS small-area CSV."""
    response = session.get(SAPS_CSV_URL, timeout=120)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    return {row["GUID"]: int(row["T1_1AGETT"]) for row in reader}


def fetch_centroids(session):
    """Yield (guid, lon, lat) for every Small Area, paginated."""
    offset = 0
    while True:
        response = session.get(
            CENTROIDS_URL,
            params={
                "where": "1=1",
                "outFields": "SA_GUID_2022",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        for feature in features:
            centroid = feature.get("centroid")
            if centroid:
                yield (
                    feature["attributes"]["SA_GUID_2022"],
                    round(centroid["x"], 6),
                    round(centroid["y"], 6),
                )
        offset += len(features)
        if not features or (not data.get("exceededTransferLimit") and len(features) < PAGE_SIZE):
            return


def run():
    session = make_session()
    populations = fetch_saps_populations(session)
    print(f"SAPS rows: {len(populations)}")

    rows = [
        (guid, lon, lat, populations[guid])
        for guid, lon, lat in fetch_centroids(session)
        if guid in populations
    ]
    total = sum(r[3] for r in rows)
    print(f"Centroids joined: {len(rows)}, total population {total:,}")
    if total != CENSUS_2022_STATE_POP:
        print(f"WARNING: expected Census 2022 state total {CENSUS_2022_STATE_POP:,}")

    with open(SA_POP_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["guid", "lon", "lat", "pop"])
        writer.writerows(rows)
    print(f"Wrote {SA_POP_PATH}")
