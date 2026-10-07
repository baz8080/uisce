"""Water Supply Zones, from Uisce Éireann's own ArcGIS layer.

Writes data/wsz_mains.csv (code, name, local_authority, county, mains_m) and the
simplified boundaries as data/wsz.geojson. Source: Uisce Éireann; terms requested,
no licence on the item.
"""

import csv
import json
from collections import defaultdict

from uisce.config import WSZ_MAINS_PATH, WSZ_SHAPES_PATH, make_session

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


def fetch_features(session, params):
    offset = 0
    while True:
        data = query(
            session,
            {
                **params,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
            },
        )
        features = data.get("features", [])
        yield from features
        offset += len(features)
        # GeoJSON responses carry the flag under properties
        more = data.get("exceededTransferLimit") or (data.get("properties") or {}).get(
            "exceededTransferLimit"
        )
        if not features or (not more and len(features) < PAGE_SIZE):
            return


def fetch_zones(session):
    params = {"outFields": WSZ_FIELDS, "returnGeometry": "false"}
    for feature in fetch_features(session, params):
        yield feature["attributes"]


def fetch_shapes(session):
    # every vertex, to about 1 m: smoothing the boundaries moves pins between zones
    params = {"outFields": "SCHEME_COD", "f": "geojson", "geometryPrecision": 5}
    return fetch_features(session, params)


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


def write_zones(session, path=WSZ_MAINS_PATH, shapes_path=WSZ_SHAPES_PATH):
    """Write the mains table and the boundaries together, or neither.

    Returns the rows and the boundary diff (added, removed, reshaped codes).
    """
    expected = zone_count(session)
    rows = zone_rows(fetch_zones(session))
    if len({r["code"] for r in rows}) != len(rows):
        raise RuntimeError("duplicate zone codes in the layer")
    if len(rows) != expected:
        raise RuntimeError(f"fetched {len(rows)} zones, the layer reports {expected}; not writing")
    features = shape_features(fetch_shapes(session))
    if [f["properties"]["code"] for f in features] != [r["code"] for r in rows]:
        raise RuntimeError("the boundaries are not the zones the mains table lists; not writing")
    try:
        old = read_shapes(shapes_path)
    except (OSError, ValueError, KeyError):
        old = []  # a missing or broken file must not block the fetch that replaces it
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    # one zone a line, so a re-fetch diffs by zone
    lines = ",\n".join(json.dumps(f, separators=(",", ":")) for f in features)
    shapes_path.write_text(f'{{"type":"FeatureCollection","features":[\n{lines}\n]}}\n')
    return rows, shape_diff(old, features)


def shape_features(features):
    """Features keyed by code alone, sorted by it; a zone with no boundary is refused."""
    out = []
    for feature in features:
        code = feature["properties"]["SCHEME_COD"]
        if not feature.get("geometry"):
            raise ValueError(f"zone {code} has no boundary")
        geometry = feature["geometry"]
        out.append({"type": "Feature", "properties": {"code": code}, "geometry": geometry})
    return sorted(out, key=lambda f: f["properties"]["code"])


def read_shapes(path=WSZ_SHAPES_PATH):
    with open(path) as f:
        return json.load(f)["features"]


def shape_diff(old, new):
    """(added, removed, reshaped) zone codes between two feature lists."""
    before = {f["properties"]["code"]: f["geometry"] for f in old}
    after = {f["properties"]["code"]: f["geometry"] for f in new}
    return (
        sorted(after.keys() - before.keys()),
        sorted(before.keys() - after.keys()),
        sorted(c for c in after.keys() & before.keys() if after[c] != before[c]),
    )


def edges(ring):
    # wraps to the first vertex, so an unclosed ring keeps its last edge
    return zip(ring, ring[1:] + ring[:1])


def _ring_area(ring):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in edges(ring))) / 2


def _in_ring(x, y, ring):
    inside = False
    for (x0, y0), (x1, y1) in edges(ring):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


class ZoneLookup:
    """Point-in-polygon on the committed boundaries: a bbox prefilter, then a ray cast."""

    def __init__(self, features):
        zones = []
        for f in features:
            geometry = f["geometry"]
            polygons = geometry["coordinates"]
            if geometry["type"] == "Polygon":
                polygons = [polygons]
            parts = []
            for outer, *holes in polygons:
                xs, ys = [x for x, _ in outer], [y for _, y in outer]
                parts.append(((min(xs), min(ys), max(xs), max(ys)), outer, holes))
            area = sum(_ring_area(p[0]) - sum(map(_ring_area, p[1:])) for p in polygons)
            zones.append((area, f["properties"]["code"], parts))
        # smallest first, so a pin in two zones goes to the town inside its rural scheme
        zones.sort(key=lambda z: (z[0], z[1]))
        self._zones = [z[1:] for z in zones]
        self._cache = {}

    @classmethod
    def from_geojson(cls, path=WSZ_SHAPES_PATH):
        return cls(read_shapes(path))

    @staticmethod
    def _inside(x, y, parts):
        # part by part, not even-odd over every ring: the layer draws some zones
        # with overlapping parts, and even-odd reads the overlap as a hole
        return any(
            x0 <= x <= x1 and y0 <= y <= y1 and _in_ring(x, y, outer)
            and not any(_in_ring(x, y, hole) for hole in holes)
            for (x0, y0, x1, y1), outer, holes in parts
        )

    def zone(self, lat, lon):
        """The zone code a pin falls in, or None for a scheme the layer does not cover."""
        key = (lat, lon)
        if key not in self._cache:
            self._cache[key] = next(
                (code for code, parts in self._zones if self._inside(lon, lat, parts)),
                None,
            )
        return self._cache[key]


def run():
    rows, (added, removed, reshaped) = write_zones(make_session())
    totals = county_mains_km(rows)
    print(f"Zones: {len(rows)}, {sum(totals.values()):,.0f} km of main in {len(totals)} counties")
    for county, km in totals.items():
        print(f"  {county}: {km:,.0f} km")
    print(f"Boundaries: {len(added)} added, {len(removed)} removed, {len(reshaped)} reshaped")
    for label, codes in (("removed", removed), ("reshaped", reshaped)):
        if codes:
            more = f" and {len(codes) - 20} more" if len(codes) > 20 else ""
            print(f"  {label}: {', '.join(codes[:20])}{more}")
