"""Map every Census 2022 Small Area to the named area a notice pin there belongs to.

Writes data/sa_towns.csv (guid, town_code, town_name, town_county) — the lookup
uisce-site uses to break a county down into named areas. Three kinds of area, in
priority order:

- a **Census settlement** (CSO Urban Area), for the ~70% of the country living in one
- a **Local Electoral Area**, where the settlement is too big to read as one row:
  the Census counts a city and its suburbs as a single settlement, and Dublin's is
  1.26M people (see split_large_settlements)
- **"Around <Electoral Division>"**, for Small Areas in no settlement at all —
  most of the water network is between towns rather than in one

All of it comes from attributes the Small Area layer already carries
(`SA_URBAN_AREA_NAME`, `CSO_LEA`, `ED_ENGLISH`, `COUNTY_ENGLISH`), so no boundary
polygons are downloaded and no point-in-polygon test is needed. That is not just
cheaper than deriving it from geometry, it is *exact*: summing Small Areas
reproduces all 867 published settlement populations to the person, where a
centroid-in-polygon assignment recovered 97.5% of urban population, dropped 54
settlements whose boundary contained no centroid, and left 24% of settlements
more than a tenth short — which matters because the site divides by that
population to get availability.

The Census figures are still downloaded, purely to assert that invariant.

See notes/population-data-sources.md. The result is committed, so this only needs
re-running if the CSO revises the geography (next census).
"""

import csv
import io
from collections import Counter, defaultdict

from uisce.config import SA_POP_PATH, SA_TOWNS_PATH, make_session

BUA_CSV_URL = "https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_BUA_270923.csv"
SMALL_AREAS_URL = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0/query"
)
URBAN_AREAS_URL = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "Urban_Areas_National_Statistical_Boundaries_2022_Generalised_20m/FeatureServer/5/query"
)
SA_FIELDS = "SA_GUID_2022,SA_URBAN_AREA_NAME,CSO_LEA,ED_ENGLISH,COUNTY_ENGLISH"
PAGE_SIZE = 2000

# A settlement this large is an agglomeration rather than a town and reads
# uselessly as one row: "Dublin city and suburbs" is a single Census settlement of
# 1.26M holding 83% of the county's cases. Currently selects exactly the five
# "city and suburbs" areas — the next largest settlement is Drogheda at 44,135 —
# but it is expressed as a population rule rather than a name match so it cannot
# be broken by the CSO renaming them.
SPLIT_ABOVE_POP = 50_000

# An LEA is kept as its own row only if this much of it lies inside the settlement
# being split. Below that it is a sliver of an area that mostly lies elsewhere, and
# naming a row after it actively misleads: the Cork agglomeration clips 942 people
# of the 39,145-person Carrigaline LEA, which would otherwise appear as
# "Carrigaline" beside the real Carrigaline town row. Every name collision observed
# between a part and an existing settlement row was a sliver, which is not luck —
# an LEA shares a town's name precisely when it is named after a town that is not
# part of the agglomeration.
MIN_PART_SHARE = 0.30

# The Small Area layer reports the 34 local-authority areas; the site works in the
# 26 traditional counties, which is what cases.county and COUNTY_POP use. Stripping
# a trailing " CITY" covers Cork, Galway, Limerick and Waterford; the Dublin four
# and the two Tipperaries need naming.
COUNTY_ALIASES = {
    "DUBLIN CITY": "Dublin",
    "DUN LAOGHAIRE/RATHDOWN": "Dublin",
    "FINGAL": "Dublin",
    "SOUTH DUBLIN": "Dublin",
    "NORTH TIPPERARY": "Tipperary",
    "SOUTH TIPPERARY": "Tipperary",
}


def county_name(value):
    """'CORK CITY' -> 'Cork', 'FINGAL' -> 'Dublin', 'CARLOW' -> 'Carlow'."""
    return COUNTY_ALIASES.get(value) or value.removesuffix(" CITY").title()


def elsewhere_label(settlement_name):
    """'Dublin city and suburbs' -> 'Elsewhere in Dublin city'."""
    return f"Elsewhere in {settlement_name.replace(' and suburbs', '')}"


def around_label(ed_name):
    """The countryside of an Electoral Division, named for the place at its centre.

    Not bare "Celbridge": the Electoral Division of that name is the parish
    *around* the town, and the town has its own row on the same page. Almost every
    county has at least one such pair — Kildare alone would otherwise show
    Celbridge, Leixlip, Maynooth, Kill and Carragh twice — and unlike the LEA
    slivers these cannot be pooled away, because a rural Electoral Division is not
    a sliver of anything. It is a real place that happens to share a name.
    """
    return f"Around {ed_name}"


def fetch_bua_populations(session):
    """Settlement code -> Census 2022 population, from the SAPS Built-Up Areas CSV.

    cp1252, not the utf-8-sig of the Small Area file — the fadas in Irish-language
    placenames ("Dumha Thuama") are single-byte here and utf-8 decoding dies on
    them. The file also carries an "Ireland" state-total row.
    """
    response = session.get(BUA_CSV_URL, timeout=120)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.content.decode("cp1252")))
    return {row["GEOGID"]: int(row["T1_1AGETT"]) for row in reader}


def fetch_settlements(session):
    """Yield (code, name, county) for every Census 2022 settlement.

    Attributes only — the geometry this layer also holds is what the previous
    implementation needed and this one does not. All 867 fit in one page.
    """
    response = session.get(
        URBAN_AREAS_URL,
        params={
            "where": "1=1",
            "outFields": "URBAN_AREA_CODE,URBAN_AREA_NAME,COUNTY",
            "returnGeometry": "false",
            "f": "json",
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("exceededTransferLimit"):
        raise RuntimeError("settlement query was paginated; add resultOffset handling")
    for feature in data["features"]:
        attrs = feature["attributes"]
        yield attrs["URBAN_AREA_CODE"], attrs["URBAN_AREA_NAME"], attrs["COUNTY"]


def fetch_small_areas(session):
    """Yield one attribute dict per Census 2022 Small Area, paginated."""
    offset = 0
    while True:
        response = session.get(
            SMALL_AREAS_URL,
            params={
                "where": "1=1",
                "outFields": SA_FIELDS,
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        for feature in features:
            yield feature["attributes"]
        offset += len(features)
        if not features or (not data.get("exceededTransferLimit") and len(features) < PAGE_SIZE):
            return


def resolve_settlements(small_areas, settlements):
    """{guid: settlement code} for the Small Areas the CSO places in a settlement.

    The Small Area carries its settlement's *name*, not its code, and 19 names are
    shared by two or three unrelated settlements — there is a Milltown in Kerry,
    another in Kildare and a third in Galway. So the join is on (name, county),
    which keeps those apart.

    A settlement may also genuinely straddle a county boundary, in which case its
    minority-county Small Areas find no (name, county) pair: the Limerick
    agglomeration reaches into Clare, Waterford's into Kilkenny, Drogheda into
    Meath. Those fall through to the name, which is unambiguous for every
    straddler on file, and so stay with the settlement rather than splitting off a
    phantom one. Measured on the 2022 geography: 13,060 exact, 125 straddlers, no
    name both ambiguous and unmatched, nothing unresolved.
    """
    by_pair, by_name = {}, defaultdict(list)
    for code, name, county in settlements:
        by_pair[(name, county)] = code
        by_name[name].append(code)

    resolved = {}
    for area in small_areas:
        name = area["SA_URBAN_AREA_NAME"]
        if not name:
            continue
        county = county_name(area["COUNTY_ENGLISH"])
        code = by_pair.get((name, county))
        if code is None and len(by_name.get(name, ())) == 1:
            code = by_name[name][0]
        if code is not None:
            resolved[area["SA_GUID_2022"]] = code
    return resolved


def split_large_settlements(resolved, small_areas, sa_pop, names):
    """Re-home the Small Areas of any settlement too large to read as one row.

    The parts are Local Electoral Areas, read straight off `CSO_LEA`. An LEA is not
    contained by the settlement — it extends into the surrounding county — so a
    part earns its own row only when MIN_PART_SHARE of the LEA lies inside, and
    the remainder pools into one "Elsewhere in ..." row. The share is measured
    against the LEA's whole population, summed over every Small Area in it, so no
    separate population file is needed and the two figures cannot disagree.

    Returns (assignment, parts, report): `parts` names each part code it created,
    `report` is one row per settlement split.
    """
    settlement_pop = Counter()
    for guid, code in resolved.items():
        settlement_pop[code] += sa_pop.get(guid, 0)
    big = {code for code, pop in settlement_pop.items() if pop >= SPLIT_ABOVE_POP}
    if not big:
        return dict(resolved), {}, []

    lea_pop, lea_of = Counter(), {}
    for area in small_areas:
        guid = area["SA_GUID_2022"]
        lea = area["CSO_LEA"].title()
        lea_pop[lea] += sa_pop.get(guid, 0)
        lea_of[guid] = lea

    inside = Counter()
    for guid, code in resolved.items():
        if code in big:
            inside[(code, lea_of[guid])] += sa_pop.get(guid, 0)
    kept = {key for key, pop in inside.items() if pop >= lea_pop[key[1]] * MIN_PART_SHARE}

    out, folded, parts = {}, Counter(), {}
    for guid, code in resolved.items():
        if code not in big:
            out[guid] = code
            continue
        lea = lea_of[guid]
        if (code, lea) in kept:
            part = f"{code}-{lea}"
            parts[part] = lea
        else:
            part = f"{code}-rest"
            parts[part] = elsewhere_label(names[code])
            folded[code] += sa_pop.get(guid, 0)
        out[guid] = part

    report = [
        (
            code,
            sum(1 for key in kept if key[0] == code),
            sum(1 for key in inside if key[0] == code and key not in kept),
            folded[code],
            settlement_pop[code],
        )
        for code in sorted(big, key=lambda c: -settlement_pop[c])
    ]
    return out, parts, report


def area_rows(small_areas, assignment, names, counties):
    """[(guid, code, name, county)] for every Small Area, settled or not.

    A Small Area in no settlement is grouped with the rest of its Electoral
    Division's countryside. EDs are keyed by (county, name): 50 of 3,368 such pairs
    cover more than one ED record, some of them parts of a single ED split by a
    boundary, and merging them beats emitting two rows a reader cannot tell apart.
    """
    rows = []
    for area in small_areas:
        guid = area["SA_GUID_2022"]
        county = county_name(area["COUNTY_ENGLISH"])
        code = assignment.get(guid)
        if code is not None:
            rows.append((guid, code, names[code], counties.get(code, county)))
        else:
            ed = area["ED_ENGLISH"].title()
            rows.append((guid, f"ed:{county}:{ed}", around_label(ed), county))
    return rows


def check_populations(assignment, sa_pop, census_pop, codes):
    """Every settlement's Small Areas must sum to its published Census population.

    Exact equality, not a tolerance: the CSO assigns each Small Area to a
    settlement itself, so the only way this drifts is if the two datasets stop
    describing the same geography. Skipped for settlements that were split, whose
    Small Areas now carry a part code.
    """
    summed = Counter()
    for guid, code in assignment.items():
        summed[code] += sa_pop.get(guid, 0)
    wrong = [
        (code, summed.get(code, 0), census_pop[code])
        for code in codes
        if code in census_pop and code in summed and summed[code] != census_pop[code]
    ]
    return summed, wrong


def run():
    session = make_session()
    census_pop = fetch_bua_populations(session)
    settlements = list(fetch_settlements(session))
    names = {code: name for code, name, _ in settlements}
    counties = {code: county for code, _, county in settlements}
    print(f"Settlements: {len(settlements)} (SAPS rows {len(census_pop)})")

    small_areas = list(fetch_small_areas(session))
    print(f"Small Areas: {len(small_areas)}")
    with open(SA_POP_PATH, newline="") as f:
        sa_pop = {row["guid"]: int(row["pop"]) for row in csv.DictReader(f)}
    missing = [a for a in small_areas if a["SA_GUID_2022"] not in sa_pop]
    if missing:
        print(f"WARNING: {len(missing)} Small Areas are absent from {SA_POP_PATH}")

    resolved = resolve_settlements(small_areas, settlements)
    urban = sum(sa_pop.get(guid, 0) for guid in resolved)
    share = 100 * len(resolved) / len(small_areas)
    print(f"In a settlement: {len(resolved)} ({share:.1f}%), {urban:,} people")

    _, wrong = check_populations(resolved, sa_pop, census_pop, set(names))
    if wrong:
        print(f"WARNING: {len(wrong)} settlements do not match their Census population")
        for code, got, expected in wrong[:5]:
            print(f"  {names[code]}: summed {got:,}, Census {expected:,}")
    else:
        print(f"Verified: all {len(names)} settlements match their published population")

    assignment, parts, report = split_large_settlements(resolved, small_areas, sa_pop, names)
    for code, n_kept, n_folded, folded_pop, total in report:
        pct = 100 * folded_pop / total
        print(
            f"  split {names[code]} ({total:,}) into {n_kept} areas"
            f" + {n_folded} sliver{'' if n_folded == 1 else 's'}"
            f" pooled as '{elsewhere_label(names[code])}' ({folded_pop:,}, {pct:.1f}%)"
        )
    # a part inherits the settlement's county: two agglomerations cross a county
    # line, and a part filed under the neighbour would be refused by the
    # cross-county guard in site.py and vanish from both pages
    for part, name in parts.items():
        names[part] = name
        counties[part] = counties[part.split("-", 1)[0]]

    rows = area_rows(small_areas, assignment, names, counties)
    areas = {(code, name) for _, code, name, _ in rows}
    rural = sum(1 for _, code, _, _ in rows if code.startswith("ed:"))
    print(f"Named areas: {len(areas)} ({rural} Small Areas grouped by Electoral Division)")

    with open(SA_TOWNS_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["guid", "town_code", "town_name", "town_county"])
        writer.writerows(sorted(rows))
    print(f"Wrote {SA_TOWNS_PATH}")
