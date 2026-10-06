import pytest

from uisce.site import COUNTY_POP
from uisce.wsz import (
    COUNTIES,
    LA_COUNTY,
    county_mains_km,
    county_of,
    read_zones,
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


class FakeSession:
    def __init__(self, count, features=(), error=None):
        self.count, self.features, self.error = count, list(features), error

    def get(self, url, params, timeout):
        if self.error:
            return FakeResponse({"error": self.error})
        if params.get("returnCountOnly"):
            return FakeResponse({"count": self.count})
        return FakeResponse({"features": self.features})


@pytest.fixture
def committed(tmp_path):
    path = tmp_path / "wsz_mains.csv"
    path.write_text("committed\n")
    return path


def test_layer_error_leaves_the_table_alone(committed):
    session = FakeSession(2, error={"code": 400, "message": "Invalid field"})
    with pytest.raises(RuntimeError, match="Invalid field"):
        write_zones(session, committed)
    assert committed.read_text() == "committed\n"


def test_short_fetch_leaves_the_table_alone(committed):
    session = FakeSession(3, [zone("Z1"), zone("Z2")])
    with pytest.raises(RuntimeError, match="fetched 2 zones, the layer reports 3"):
        write_zones(session, committed)
    assert committed.read_text() == "committed\n"


def test_complete_fetch_writes_the_table(committed):
    write_zones(FakeSession(2, [zone("Z2", "Fingal", 2500.4), zone("Z1")]), committed)
    rows = read_zones(committed)
    assert [(r["code"], r["county"], r["mains_m"]) for r in rows] == [
        ("Z1", "Cork", "1000"),
        ("Z2", "Dublin", "2500"),
    ]
