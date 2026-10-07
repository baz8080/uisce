import pytest

from uisce.config import WSZ_SHAPES_PATH
from uisce.site import COUNTY_POP, zone_report
from uisce.wsz import (
    COUNTIES,
    LA_COUNTY,
    ZoneLookup,
    county_mains_km,
    county_of,
    fetch_shapes,
    read_shapes,
    read_zones,
    shape_features,
    write_zones,
    zone_rows,
)

NATIONAL_KM = 53_756


@pytest.mark.parametrize(
    ("authority", "county"),
    [
        ("Dublin City", "Dublin"),
        ("Fingal", "Dublin"),
        ("South Dublin", "Dublin"),
        ("Dun Laoghaire-Rathdown", "Dublin"),
        ("Cork City", "Cork"),
        ("Cork", "Cork"),
        ("Galway City", "Galway"),
        ("Galway", "Galway"),
        ("Tipperary", "Tipperary"),
    ],
)
def test_authority_merges_to_county(authority, county):
    assert county_of(authority) == county


def test_unmapped_authority_fails_loudly():
    with pytest.raises(ValueError, match="Fingall"):
        county_of("Fingall")


def test_zone_without_length_is_refused():
    zone = {"SCHEME_COD": "Z1", "SCHEME_NAM": "n", "LOCALAUTHORITY": "Cork", "DISMAINSLENGTH": None}
    with pytest.raises(ValueError, match="Z1"):
        zone_rows([zone])


def test_county_names_match_the_site():
    assert COUNTIES == set(COUNTY_POP)
    assert set(LA_COUNTY.values()) <= COUNTIES


def test_committed_zones_all_map_and_keep_their_county():
    rows = read_zones()
    assert all(county_of(r["local_authority"]) == r["county"] for r in rows)
    assert {r["county"] for r in rows} == COUNTIES


def test_committed_counties_sum_to_the_national_figure():
    total = sum(county_mains_km(read_zones()).values())
    assert total == pytest.approx(NATIONAL_KM, rel=0.01)


def zone(code, authority="Cork", metres=1000.0):
    return {"attributes": {
        "SCHEME_COD": code, "SCHEME_NAM": code, "LOCALAUTHORITY": authority,
        "DISMAINSLENGTH": metres,
    }}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def layer_shape(code, geometry=True):
    polygon = {"type": "Polygon", "coordinates": [square(0, 0, 1, 1)]}
    return {"type": "Feature", "properties": {"SCHEME_COD": code},
            "geometry": polygon if geometry else None}


class FakeSession:
    """The layer: attribute features as JSON, boundaries (one per zone unless given) as GeoJSON."""

    def __init__(self, count, features=(), error=None, shapes=None):
        self.count, self.features, self.error = count, list(features), error
        self.shapes = shapes if shapes is not None else [
            layer_shape(f["attributes"]["SCHEME_COD"]) for f in self.features
        ]

    def get(self, url, params, timeout):
        if self.error:
            return FakeResponse({"error": self.error})
        if params.get("returnCountOnly"):
            return FakeResponse({"count": self.count})
        if params.get("f") == "geojson":
            return FakeResponse({"type": "FeatureCollection", "features": self.shapes})
        return FakeResponse({"features": self.features})


@pytest.fixture
def committed(tmp_path):
    for name in ("wsz_mains.csv", "wsz.geojson"):
        (tmp_path / name).write_text("committed\n")
    return tmp_path / "wsz_mains.csv", tmp_path / "wsz.geojson"


def untouched(paths):
    return all(path.read_text() == "committed\n" for path in paths)


def test_layer_error_leaves_the_table_alone(committed):
    session = FakeSession(2, error={"code": 400, "message": "Invalid field"})
    with pytest.raises(RuntimeError, match="Invalid field"):
        write_zones(session, *committed)
    assert untouched(committed)


def test_short_fetch_leaves_the_table_alone(committed):
    session = FakeSession(3, [zone("Z1"), zone("Z2")])
    with pytest.raises(RuntimeError, match="fetched 2 zones, the layer reports 3"):
        write_zones(session, *committed)
    assert untouched(committed)


def test_complete_fetch_writes_the_table(tmp_path):
    session = FakeSession(2, [zone("Z2", "Fingal", 2500.4), zone("Z1")])
    write_zones(session, tmp_path / "wsz_mains.csv", tmp_path / "wsz.geojson")
    rows = read_zones(tmp_path / "wsz_mains.csv")
    assert [(r["code"], r["county"], r["mains_m"]) for r in rows] == [
        ("Z1", "Cork", "1000"),
        ("Z2", "Dublin", "2500"),
    ]


def test_committed_boundaries_are_the_committed_zones():
    assert WSZ_SHAPES_PATH.stat().st_size < 3_000_000
    assert [f["properties"]["code"] for f in read_shapes()] == [r["code"] for r in read_zones()]


@pytest.fixture(scope="module")
def zones():
    return ZoneLookup.from_geojson()


@pytest.mark.parametrize(
    ("lat", "lon", "code"),
    [
        (52.8362, -6.9264, "SZPUB0001"),  # Carlow Town
        (51.8985, -8.4756, "SZPUB0045"),  # Cork City Water Supply
        (53.0, -11.0, None),  # the Atlantic
    ],
)
def test_known_pin_lands_in_its_zone(zones, lat, lon, code):
    assert zones.zone(lat, lon) == code


def shape(code, geometry_type, coordinates):
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": geometry_type, "coordinates": coordinates}}


def test_a_hole_is_outside_and_a_second_part_inside():
    lookup = ZoneLookup([shape("Z", "MultiPolygon", [
        [square(0, 0, 10, 10), square(4, 4, 6, 6)],
        [square(20, 0, 22, 2)],
    ])])
    assert lookup.zone(1, 1) == "Z"
    assert lookup.zone(5, 5) is None
    assert lookup.zone(1, 21) == "Z"
    assert lookup.zone(15, 15) is None


def test_a_pin_in_two_zones_goes_to_the_smaller():
    lookup = ZoneLookup([
        shape("RURAL", "Polygon", [square(0, 0, 10, 10)]),
        shape("TOWN", "Polygon", [square(4, 4, 6, 6)]),
    ])
    assert lookup.zone(5, 5) == "TOWN"
    assert lookup.zone(1, 1) == "RURAL"


def test_an_unclosed_ring_keeps_its_last_edge():
    lookup = ZoneLookup([shape("Z", "Polygon", [square(0, 0, 10, 10)[:-1]])])
    assert lookup.zone(5, 5) == "Z"
    assert lookup.zone(5, 11) is None


def test_zone_without_boundary_is_refused():
    with pytest.raises(ValueError, match="Z1"):
        shape_features([layer_shape("Z1", geometry=False)])


def test_boundaries_missing_a_zone_write_neither_file(committed):
    session = FakeSession(2, [zone("Z1"), zone("Z2")], shapes=[layer_shape("Z1")])
    with pytest.raises(RuntimeError, match="not the zones the mains table lists"):
        write_zones(session, *committed)
    assert untouched(committed)


def test_a_broken_boundary_file_is_replaced(committed):
    _, diff = write_zones(FakeSession(1, [zone("Z1")]), *committed)
    assert diff == (["Z1"], [], [])
    assert [f["properties"]["code"] for f in read_shapes(committed[1])] == ["Z1"]


def test_refetch_reports_what_moved(tmp_path):
    paths = tmp_path / "wsz_mains.csv", tmp_path / "wsz.geojson"
    _, diff = write_zones(FakeSession(2, [zone("Z2"), zone("Z1")]), *paths)
    assert diff == (["Z1", "Z2"], [], [])
    moved = layer_shape("Z2")
    moved["geometry"]["coordinates"] = [square(0, 0, 2, 2)]
    session = FakeSession(2, [zone("Z3"), zone("Z2")], shapes=[layer_shape("Z3"), moved])
    _, diff = write_zones(session, *paths)
    assert diff == (["Z3"], ["Z1"], ["Z2"])
    assert [f["properties"]["code"] for f in read_shapes(paths[1])] == ["Z2", "Z3"]
    assert len(paths[1].read_text().splitlines()) == 4


def test_zone_report_counts_distinct_pins():
    lookup = ZoneLookup([shape("Z", "Polygon", [square(0, 0, 10, 10)])])
    rows = [{"full_lat": lat, "full_lon": lat} for lat in (1, 1, 50)]
    assert zone_report(rows, lookup) == "Supply zones: 1 of 2 distinct pins in a zone (50.0%)"


class PagedSession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, params, timeout):
        return FakeResponse(self.pages[params["resultOffset"]])


def test_geojson_pages_on_while_the_layer_says_there_is_more():
    session = PagedSession({
        0: {"features": [layer_shape("Z1")], "properties": {"exceededTransferLimit": True}},
        1: {"features": [layer_shape("Z2")]},
    })
    assert [f["properties"]["SCHEME_COD"] for f in fetch_shapes(session)] == ["Z1", "Z2"]
