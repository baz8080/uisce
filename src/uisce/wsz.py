"""Distribution mains length per Water Supply Zone, from Uisce Éireann's own ArcGIS layer.

Writes data/wsz_mains.csv (code, name, local_authority, county, mains_m). Attributes
only, no boundaries. Source: Uisce Éireann; terms requested, no licence on the item.
"""

import csv
from collections import defaultdict

from uisce.config import WSZ_MAINS_PATH, make_session

WSZ_URL = (
    "https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/"
    "watersupplyzonesDWQ_DeptView/FeatureServer/0/query"
)
WSZ_FIELDS = "SCHEME_COD,SCHEME_NAM,LOCALAUTHORITY,DISMAINSLENGTH"
PAGE_SIZE = 1000
COLUMNS = ["code", "name", "local_authority", "county", "mains_m"]

COUNTIES = {
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway", "Kerry",
    "Kildare", "Kilkenny", "Laois", "Leitrim", "Limerick", "Longford", "Louth",
    "Mayo", "Meath", "Monaghan", "Offaly", "Roscommon", "Sligo", "Tipperary",
    "Waterford", "Westmeath", "Wexford", "Wicklow",
}

# The layer's 31 local authorities against the site's 26 counties; any other
# authority is already named for its county.
LA_COUNTY = {
    "Dublin City": "Dublin",
    "Fingal": "Dublin",
    "South Dublin": "Dublin",
    "Dun Laoghaire-Rathdown": "Dublin",
    "Cork City": "Cork",
    "Galway City": "Galway",
}


def county_of(local_authority):
    """Fail loudly on a local authority the merge has not seen, rather than drop its mains."""
    if local_authority in LA_COUNTY:
        return LA_COUNTY[local_authority]
    if local_authority in COUNTIES:
        return local_authority
    raise ValueError(f"unmapped local authority: {local_authority!r}")



def query(session, params):
    response = session.get(WSZ_URL, params={"where": "1=1", "f": "json", **params}, timeout=120)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"supply zone query failed: {data['error']}")
    return data


def zone_count(session):
    return query(session, {"returnCountOnly": "true"})["count"]


def fetch_zones(session):
    offset = 0
    while True:
        data = query(
            session,
            {
                "outFields": WSZ_FIELDS,
                "returnGeometry": "false",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
            },
        )
        features = data.get("features", [])
        for feature in features:
            yield feature["attributes"]
        offset += len(features)
        if not features or (not data.get("exceededTransferLimit") and len(features) < PAGE_SIZE):
            return


def zone_rows(zones):
    """Per-zone rows, sorted by code; a missing length is refused, not read as zero."""
    rows = []
    for zone in zones:
        if zone["DISMAINSLENGTH"] is None:
            raise ValueError(f"zone {zone['SCHEME_COD']} has no mains length")
        rows.append(
            {
                "code": zone["SCHEME_COD"],
                "name": zone["SCHEME_NAM"],
                "local_authority": zone["LOCALAUTHORITY"],
                "county": county_of(zone["LOCALAUTHORITY"]),
                "mains_m": round(zone["DISMAINSLENGTH"]),
            }
        )
    return sorted(rows, key=lambda r: r["code"])


def read_zones(path=WSZ_MAINS_PATH):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def county_mains_km(rows):
    metres = defaultdict(int)
    for row in rows:
        metres[row["county"]] += int(row["mains_m"])
    return {county: metres[county] / 1000 for county in sorted(metres)}


def write_zones(session, path=WSZ_MAINS_PATH):
    expected = zone_count(session)
    rows = zone_rows(fetch_zones(session))
    if len({r["code"] for r in rows}) != len(rows):
        raise RuntimeError("duplicate zone codes in the layer")
    if len(rows) != expected:
        raise RuntimeError(f"fetched {len(rows)} zones, the layer reports {expected}; not writing")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def run():
    rows = write_zones(make_session())
    totals = county_mains_km(rows)
    print(f"Zones: {len(rows)}, {sum(totals.values()):,.0f} km of main in {len(totals)} counties")
    for county, km in totals.items():
        print(f"  {county}: {km:,.0f} km")
