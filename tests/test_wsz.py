import pytest

from uisce.site import COUNTY_POP
from uisce.wsz import COUNTIES, LA_COUNTY, county_mains_km, county_of, read_zones, zone_rows

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
