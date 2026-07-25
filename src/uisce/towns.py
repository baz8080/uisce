"""One-time fetch of the Census 2022 settlement layer, mapped to Small Areas.

Assigns every Census 2022 Small Area centroid to the CSO Urban Area
(settlement) whose boundary contains it, and writes data/sa_towns.csv
(guid, town_code, town_name, town_county) — the lookup that lets uisce-site
drill a county down into named towns.

Two open datasets, joined on the settlement code:

- CSO Urban Areas 2022 boundaries (Tailte/CSO ArcGIS): name, county, polygon
- SAPS 2022 Built-Up Areas CSV: population per settlement

Populations are deliberately *not* written out. uisce-site derives a town's
population by summing the Small Areas assigned to it, so town figures and the
county denominator come from the same source and cannot disagree. The SAPS file
is fetched only to verify the geography: a town whose Small-Area sum drifts far
from its published Census population means the assignment is wrong, and that is
worth failing loudly on rather than discovering in the site.

See notes/population-data-sources.md. The result is committed, so this only
needs re-running if the CSO revises the settlement geography (next census).
"""

import csv
import io
from collections import defaultdict

from uisce.config import SA_POP_PATH, SA_TOWNS_PATH, make_session

BUA_CSV_URL = "https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_BUA_270923.csv"
URBAN_AREAS_URL = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "Urban_Areas_National_Statistical_Boundaries_2022_Generalised_20m/FeatureServer/5/query"
)

# Latitude bands used to narrow the candidate settlements for a given centroid.
# 867 polygons against 18,919 points is 16M naive bbox tests; binning by
# latitude cuts it to a few hundred thousand.
LAT_BIN = 0.1

# A town whose Small-Area sum falls below this share of its published Census
# population has been mis-assigned. Small villages legitimately land low — a
# single Small Area centroid sitting just outside a hamlet's boundary can drop
# it by a third — so the check is applied only to towns of REPORT_MIN_POP.
MIN_POP_RATIO = 0.8
REPORT_MIN_POP = 5000


def fetch_bua_populations(session):
    """Settlement code -> Census 2022 population, from the SAPS Built-Up Areas CSV.

    cp1252, not the utf-8-sig of the Small Area file — the fadas in Irish-language
    placenames ("Dumha Thuama") are single-byte here and utf-8 decoding dies on them.
    """
    response = session.get(BUA_CSV_URL, timeout=120)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.content.decode("cp1252")))
    return {row["GEOGID"]: int(row["T1_1AGETT"]) for row in reader}


def fetch_urban_areas(session):
    """Yield (code, name, county, rings) for every Census 2022 settlement.

    All 867 fit inside one page (maxRecordCount 2000), so there is no pagination
    to get wrong. The rings come back as WGS84 polygons — around 2.9 MB, used
    here and discarded; only the resulting assignment is committed.
    """
    response = session.get(
        URBAN_AREAS_URL,
        params={
            "where": "1=1",
            "outFields": "URBAN_AREA_CODE,URBAN_AREA_NAME,COUNTY",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("exceededTransferLimit"):
        raise RuntimeError("urban area query was paginated; add resultOffset handling")
    for feature in data["features"]:
        attrs = feature["attributes"]
        yield (
            attrs["URBAN_AREA_CODE"],
            attrs["URBAN_AREA_NAME"],
            attrs["COUNTY"],
            feature["geometry"]["rings"],
        )


def crossings(x, y, ring):
    """Ray-cast crossings of the +x ray from (x, y) over one ring."""
    count = 0
    prev_x, prev_y = ring[-1]
    for cur_x, cur_y in ring:
        if (cur_y > y) != (prev_y > y):
            if x < (prev_x - cur_x) * (y - cur_y) / (prev_y - cur_y) + cur_x:
                count += 1
        prev_x, prev_y = cur_x, cur_y
    return count


def contains(x, y, rings):
    """Even-odd containment across all of a feature's rings.

    Summing crossings over every ring and taking the parity handles both parts
    of a multipart settlement and holes punched in one, with no need to know
    which rings ArcGIS meant as which — a point inside a hole crosses the outer
    and inner rings once each and comes out even, i.e. outside.
    """
    return sum(crossings(x, y, ring) for ring in rings) % 2 == 1


class TownIndex:
    """Settlement polygons, binned by latitude for containment lookups."""

    def __init__(self, areas):
        self._bins = defaultdict(list)
        for code, name, county, rings in areas:
            lats = [point[1] for ring in rings for point in ring]
            lons = [point[0] for ring in rings for point in ring]
            box = (min(lons), max(lons), min(lats), max(lats))
            entry = (code, name, county, box, rings)
            for b in range(int(min(lats) / LAT_BIN), int(max(lats) / LAT_BIN) + 1):
                self._bins[b].append(entry)

    def town_of(self, lat, lon):
        """(code, name, county) of the settlement containing this point, or None."""
        for code, name, county, (x0, x1, y0, y1), rings in self._bins.get(int(lat / LAT_BIN), ()):
            if x0 <= lon <= x1 and y0 <= lat <= y1 and contains(lon, lat, rings):
                return code, name, county
        return None


def assign_small_areas(sa_rows, index):
    """[(guid, code, name, county)] for the Small Areas that fall inside a settlement."""
    assigned = []
    for row in sa_rows:
        hit = index.town_of(float(row["lat"]), float(row["lon"]))
        if hit:
            assigned.append((row["guid"], *hit))
    return assigned


def check_populations(assigned, sa_pop, census_pop, names):
    """Warn for any sizeable town whose Small-Area sum misses its Census population.

    The assignment is centroid-in-polygon, so a town's sum is the population of
    the Small Areas whose *centres* it contains — close to but never identical
    with the published settlement figure. A large shortfall means the geography
    is wrong, not that the rounding differs.
    """
    summed = defaultdict(int)
    for guid, code, _, _ in assigned:
        summed[code] += sa_pop[guid]
    # iterate the boundary layer, not the CSV: the SAPS file carries a state
    # total row ("Ireland") alongside the 867 settlements
    suspect = [
        (name, summed[code], census_pop[code])
        for code, name in names.items()
        if census_pop.get(code, 0) >= REPORT_MIN_POP
        and summed[code] < census_pop[code] * MIN_POP_RATIO
    ]
    for name, got, expected in sorted(suspect, key=lambda s: s[1] / s[2]):
        print(f"  WARNING {name}: Small Areas sum to {got:,}, Census says {expected:,}")
    return summed, suspect


def run():
    session = make_session()
    census_pop = fetch_bua_populations(session)
    print(f"SAPS Built-Up Areas: {len(census_pop)}")

    areas = list(fetch_urban_areas(session))
    names = {code: name for code, name, _, _ in areas}
    print(f"Settlement boundaries: {len(areas)}")
    missing = [code for code, *_ in areas if code not in census_pop]
    if missing:
        print(f"WARNING: {len(missing)} settlements have no SAPS population row")

    with open(SA_POP_PATH, newline="") as f:
        sa_rows = list(csv.DictReader(f))
    sa_pop = {row["guid"]: int(row["pop"]) for row in sa_rows}

    assigned = assign_small_areas(sa_rows, TownIndex(areas))
    share = 100 * len(assigned) / len(sa_rows)
    print(f"Small Areas inside a settlement: {len(assigned)} of {len(sa_rows)} ({share:.1f}%)")

    summed, suspect = check_populations(assigned, sa_pop, census_pop, names)
    urban = sum(summed.values())
    published = sum(census_pop.get(code, 0) for code, *_ in areas)
    print(f"Urban population covered: {urban:,} of {published:,} published")
    if suspect:
        print(f"WARNING: {len(suspect)} towns over {REPORT_MIN_POP:,} are short on population")

    with open(SA_TOWNS_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["guid", "town_code", "town_name", "town_county"])
        writer.writerows(sorted(assigned))
    print(f"Wrote {SA_TOWNS_PATH}")
