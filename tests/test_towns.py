from uisce.towns import (
    area_rows,
    around_label,
    check_populations,
    county_name,
    elsewhere_label,
    resolve_settlements,
    split_large_settlements,
)


def _sa(guid, urban=None, lea="SOMEWHERE", ed="SOMEPARISH", county="CORK"):
    return {
        "SA_GUID_2022": guid,
        "SA_URBAN_AREA_NAME": urban,
        "CSO_LEA": lea,
        "ED_ENGLISH": ed,
        "COUNTY_ENGLISH": county,
    }


class TestCountyName:
    def test_city_authorities_fold_into_their_county(self):
        assert county_name("CORK CITY") == "Cork"
        assert county_name("WATERFORD CITY") == "Waterford"

    def test_the_dublin_four_and_two_tipperaries_are_named(self):
        for value in ("DUBLIN CITY", "FINGAL", "SOUTH DUBLIN", "DUN LAOGHAIRE/RATHDOWN"):
            assert county_name(value) == "Dublin"
        assert county_name("NORTH TIPPERARY") == county_name("SOUTH TIPPERARY") == "Tipperary"

    def test_an_ordinary_county_is_just_title_cased(self):
        assert county_name("CARLOW") == "Carlow"

    def test_every_mapped_name_is_a_county_the_site_knows(self):
        from uisce.site import COUNTY_POP

        authorities = [
            "CARLOW", "CAVAN", "CLARE", "CORK", "CORK CITY", "DONEGAL", "DUBLIN CITY",
            "DUN LAOGHAIRE/RATHDOWN", "FINGAL", "GALWAY", "GALWAY CITY", "KERRY", "KILDARE",
            "KILKENNY", "LAOIS", "LEITRIM", "LIMERICK", "LIMERICK CITY", "LONGFORD", "LOUTH",
            "MAYO", "MEATH", "MONAGHAN", "NORTH TIPPERARY", "OFFALY", "ROSCOMMON", "SLIGO",
            "SOUTH DUBLIN", "SOUTH TIPPERARY", "WATERFORD", "WATERFORD CITY", "WESTMEATH",
            "WEXFORD", "WICKLOW",
        ]
        assert {county_name(a) for a in authorities} == set(COUNTY_POP)


class TestResolveSettlements:
    # there is a Milltown in Kerry, another in Kildare and a third in Galway
    SETTLEMENTS = [
        ("19851", "Milltown", "Kerry"),
        ("06463", "Milltown", "Kildare"),
        ("20497", "Limerick city and suburbs", "Limerick"),
    ]

    def test_same_name_in_two_counties_stays_two_settlements(self):
        resolved = resolve_settlements(
            [
                _sa("a", urban="Milltown", county="KERRY"),
                _sa("b", urban="Milltown", county="KILDARE"),
            ],
            self.SETTLEMENTS,
        )
        assert resolved == {"a": "19851", "b": "06463"}

    def test_a_settlement_straddling_a_county_line_keeps_its_far_side(self):
        """The Limerick agglomeration reaches into Clare, so those Small Areas find
        no (name, county) pair and must fall through to the name rather than
        splitting off a phantom settlement."""
        resolved = resolve_settlements(
            [_sa("a", urban="Limerick city and suburbs", county="CLARE")], self.SETTLEMENTS
        )
        assert resolved == {"a": "20497"}

    def test_a_small_area_in_no_settlement_is_left_out(self):
        assert resolve_settlements([_sa("a")], self.SETTLEMENTS) == {}

    def test_an_unknown_settlement_name_is_left_out(self):
        assert resolve_settlements([_sa("a", urban="Nowhere")], self.SETTLEMENTS) == {}


class TestSplitLargeSettlements:
    """A city and its suburbs are one Census settlement, so the biggest are broken
    into Local Electoral Areas. See notes/statuspage-methodology.md."""

    NAMES = {"CITY": "Bigton city and suburbs", "T2": "Smallville"}

    def _areas(self, clip_pop=100, outside_pop=39_000):
        """A city sitting wholly in one LEA and clipping the edge of another.

        `outside_pop` is the part of the clipped LEA that lies beyond the city, so
        it decides whether the clip is a sliver (the default) or most of that LEA.
        """
        return (
            [
                _sa("core", urban="Bigton city and suburbs", lea="INNER BIGTON"),
                _sa("clip", urban="Bigton city and suburbs", lea="FARAWAY"),
                _sa("town", urban="Smallville", lea="SMALLVILLE"),
                _sa("rural", lea="FARAWAY"),
            ],
            {"core": 60_000, "clip": clip_pop, "town": 900, "rural": outside_pop},
        )

    def _split(self, **kwargs):
        small_areas, sa_pop = self._areas(**kwargs)
        resolved = {"core": "CITY", "clip": "CITY", "town": "T2"}
        return split_large_settlements(resolved, small_areas, sa_pop, self.NAMES)

    def test_a_large_settlement_becomes_its_electoral_areas(self):
        assignment, parts, report = self._split()
        assert assignment["core"] == "CITY-Inner Bigton"
        assert parts["CITY-Inner Bigton"] == "Inner Bigton"
        assert report == [("CITY", 1, 1, 100, 60_100)]

    def test_an_electoral_area_mostly_outside_the_city_is_pooled(self):
        """Naming a row after an LEA the city merely clips misleads: Cork holds 942
        of the 39,145-person Carrigaline LEA, and there is a real Carrigaline town
        row on the same page."""
        assignment, parts, _ = self._split()
        assert assignment["clip"] == "CITY-rest"
        assert parts["CITY-rest"] == "Elsewhere in Bigton city"

    def test_an_electoral_area_mostly_inside_the_city_keeps_its_name(self):
        # the same clip, but now most of that LEA's population is inside the city
        assignment, _, _ = self._split(outside_pop=100)
        assert assignment["clip"] == "CITY-Faraway"

    def test_settlements_under_the_threshold_are_untouched(self):
        small_areas, sa_pop = self._areas()
        sa_pop["core"] = 100
        assignment, parts, report = split_large_settlements(
            {"core": "CITY", "clip": "CITY", "town": "T2"}, small_areas, sa_pop, self.NAMES
        )
        assert (parts, report) == ({}, [])
        assert assignment == {"core": "CITY", "clip": "CITY", "town": "T2"}

    def test_other_settlements_are_left_alone_by_the_split(self):
        assignment, _, _ = self._split()
        assert assignment["town"] == "T2"


class TestAreaRows:
    def test_a_settled_small_area_takes_the_settlements_name_and_county(self):
        rows = area_rows(
            [_sa("a", urban="Naas", county="KILDARE")],
            {"a": "06442"},
            {"06442": "Naas"},
            {"06442": "Kildare"},
        )
        assert rows == [("a", "06442", "Naas", "Kildare")]

    def test_an_unsettled_small_area_is_grouped_around_its_electoral_division(self):
        """Not bare "Celbridge": that Electoral Division is the parish around the
        town, and the town has its own row on the same page."""
        rows = area_rows([_sa("a", ed="CELBRIDGE", county="KILDARE")], {}, {}, {})
        assert rows == [("a", "ed:Kildare:Celbridge", "Around Celbridge", "Kildare")]

    def test_a_straddling_settlement_keeps_one_county_across_both_sides(self):
        rows = area_rows(
            [
                _sa("a", urban="Limerick city and suburbs", county="LIMERICK"),
                _sa("b", urban="Limerick city and suburbs", county="CLARE"),
            ],
            {"a": "20497", "b": "20497"},
            {"20497": "Limerick city and suburbs"},
            {"20497": "Limerick"},
        )
        assert {r[3] for r in rows} == {"Limerick"}


class TestCheckPopulations:
    def test_an_exact_match_passes(self):
        _, wrong = check_populations({"a": "T1"}, {"a": 20000}, {"T1": 20000}, {"T1"})
        assert wrong == []

    def test_any_discrepancy_at_all_is_reported(self):
        """Exact equality, not a tolerance: the CSO assigns Small Areas to
        settlements itself, so drift means the datasets have diverged."""
        _, wrong = check_populations({"a": "T1"}, {"a": 19999}, {"T1": 20000}, {"T1"})
        assert wrong == [("T1", 19999, 20000)]

    def test_the_saps_state_total_row_is_not_mistaken_for_a_settlement(self):
        _, wrong = check_populations(
            {"a": "T1"}, {"a": 20000}, {"T1": 20000, "Ireland": 5_149_139}, {"T1"}
        )
        assert wrong == []

    def test_a_split_settlement_is_not_checked_against_its_old_code(self):
        """Its Small Areas carry part codes now, so there is nothing to compare."""
        _, wrong = check_populations({"a": "CITY-Inner"}, {"a": 60000}, {"CITY": 60000}, {"CITY"})
        assert wrong == []


class TestLabels:
    def test_elsewhere_drops_the_suburbs_suffix(self):
        assert elsewhere_label("Dublin city and suburbs") == "Elsewhere in Dublin city"

    def test_around_names_the_countryside_for_its_town(self):
        assert around_label("Celbridge") == "Around Celbridge"
