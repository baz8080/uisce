from uisce.towns import (
    TownIndex,
    assign_small_areas,
    check_populations,
    contains,
    elsewhere_label,
    split_large_settlements,
)

# a 1x1 degree square with a 0.2 degree square hole punched out of the middle
SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
HOLE = [(0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4), (0.4, 0.4)]


class TestContains:
    def test_inside_and_outside_a_simple_ring(self):
        assert contains(0.5, 0.5, [SQUARE])
        assert not contains(1.5, 0.5, [SQUARE])
        assert not contains(0.5, 1.5, [SQUARE])

    def test_a_hole_reads_as_outside(self):
        """Even-odd across every ring, so ArcGIS ring winding never has to be
        interpreted: a point in the hole crosses both rings and comes out even."""
        assert not contains(0.5, 0.5, [SQUARE, HOLE])
        assert contains(0.2, 0.2, [SQUARE, HOLE])

    def test_multipart_settlement_counts_both_parts(self):
        far = [(5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0), (5.0, 5.0)]
        assert contains(5.5, 5.5, [SQUARE, far])
        assert contains(0.5, 0.5, [SQUARE, far])


TRIANGLE = [(2.0, 0.0), (3.0, 0.0), (3.0, 1.0), (2.0, 0.0)]


class TestTownIndex:
    def _index(self):
        return TownIndex(
            [
                ("06442", "Naas", "Kildare", [SQUARE]),
                ("06454", "Newbridge", "Kildare", [TRIANGLE]),
            ]
        )

    def test_point_lands_in_the_containing_settlement(self):
        assert self._index().town_of(0.5, 0.5) == ("06442", "Naas", "Kildare")

    def test_point_in_the_bounding_box_but_outside_the_shape_is_unassigned(self):
        # top-left of Newbridge's bbox, outside its triangle
        assert self._index().town_of(0.9, 2.1) is None

    def test_point_in_no_settlement_is_unassigned(self):
        assert self._index().town_of(0.5, 1.5) is None

    def test_a_settlement_spanning_two_latitude_bins_is_found_in_both(self):
        """The bins are 0.1 degrees and the test square is a whole degree tall,
        so an index that filed each shape once would miss most of it."""
        index = self._index()
        assert index.town_of(0.05, 0.5) is not None
        assert index.town_of(0.95, 0.5) is not None


class TestAssignSmallAreas:
    def test_only_small_areas_inside_a_settlement_are_returned(self):
        index = TownIndex([("06442", "Naas", "Kildare", [SQUARE])])
        rows = [
            {"guid": "in", "lat": "0.5", "lon": "0.5"},
            {"guid": "out", "lat": "9.0", "lon": "9.0"},
        ]
        assert assign_small_areas(rows, index) == [("in", "06442", "Naas", "Kildare")]


class TestCheckPopulations:
    def test_a_sizeable_town_missing_most_of_its_population_is_flagged(self):
        assigned = [("sa1", "T1", "Bigtown", "Cork")]
        summed, suspect = check_populations(
            assigned, {"sa1": 1000}, {"T1": 20000}, {"T1": "Bigtown"}
        )
        assert summed["T1"] == 1000
        assert suspect == [("Bigtown", 1000, 20000)]

    def test_a_close_match_and_a_small_village_are_both_left_alone(self):
        assigned = [("sa1", "T1", "Bigtown", "Cork"), ("sa2", "T2", "Hamlet", "Cork")]
        sa_pop = {"sa1": 19000, "sa2": 60}
        # T1 is within tolerance; T2 is far short but too small to judge
        _, suspect = check_populations(
            assigned, sa_pop, {"T1": 20000, "T2": 400}, {"T1": "Bigtown", "T2": "Hamlet"}
        )
        assert suspect == []

    def test_the_saps_state_total_row_is_not_mistaken_for_a_settlement(self):
        """The BUA CSV carries an "Ireland" row alongside the 867 settlements;
        iterating the boundary layer rather than the CSV is what skips it."""
        _, suspect = check_populations(
            [("sa1", "T1", "Bigtown", "Cork")],
            {"sa1": 19000},
            {"T1": 20000, "Ireland": 5_149_139},
            {"T1": "Bigtown"},
        )
        assert suspect == []


class TestSplitLargeSettlements:
    """A city and its suburbs are one Census settlement, so the five biggest are
    broken into Local Electoral Areas. See the drill-down section of
    notes/statuspage-methodology.md."""

    # two LEAs side by side; the city sits wholly in the left one and clips the right
    LEFT = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    RIGHT = [(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0), (1.0, 0.0)]

    def _split(self, city_pop=60_000, clip_pop=100, right_lea_pop=40_000):
        """One 'city' settlement whose Small Areas fall in two LEAs."""
        sa_rows = [
            {"guid": "core", "lat": "0.5", "lon": "0.5"},
            {"guid": "clip", "lat": "0.5", "lon": "1.5"},
            {"guid": "town", "lat": "0.5", "lon": "0.5"},
        ]
        assigned = [
            ("core", "CITY", "Bigton city and suburbs", "Cork"),
            ("clip", "CITY", "Bigton city and suburbs", "Cork"),
            ("town", "T2", "Smallville", "Cork"),
        ]
        sa_pop = {"core": city_pop, "clip": clip_pop, "town": 900}
        index = TownIndex(
            [("L1", "Inner Bigton", "Cork", [self.LEFT]), ("L2", "Faraway", "Cork", [self.RIGHT])]
        )
        return split_large_settlements(
            assigned, sa_rows, sa_pop, index, {"L1": city_pop, "L2": right_lea_pop}
        )

    def test_a_large_settlement_becomes_its_electoral_areas(self):
        assigned, report = self._split()
        by_guid = {guid: (code, name) for guid, code, name, _ in assigned}
        assert by_guid["core"] == ("CITY-L1", "Inner Bigton")
        assert report == [("CITY", 1, 1, 100, 60_100)]

    def test_an_electoral_area_mostly_outside_the_city_is_pooled(self):
        """Naming a row after an LEA the city merely clips misleads: Cork holds 942
        of the 39,145-person Carrigaline LEA, and there is a real Carrigaline town
        row on the same page."""
        assigned, _ = self._split()
        by_guid = {guid: (code, name) for guid, code, name, _ in assigned}
        assert by_guid["clip"] == ("CITY-rest", "Elsewhere in Bigton city")

    def test_an_electoral_area_mostly_inside_the_city_keeps_its_name(self):
        # same clip, but now the right-hand LEA is small enough to be 50% inside
        assigned, _ = self._split(clip_pop=100, right_lea_pop=200)
        by_guid = {guid: name for guid, _, name, _ in assigned}
        assert by_guid["clip"] == "Faraway"

    def test_settlements_under_the_threshold_are_untouched(self):
        assigned, report = self._split(city_pop=100)
        assert report == []
        assert [(guid, code) for guid, code, _, _ in assigned] == [
            ("core", "CITY"), ("clip", "CITY"), ("town", "T2")
        ]

    def test_other_settlements_are_left_alone_by_the_split(self):
        assigned, _ = self._split()
        assert ("town", "T2", "Smallville", "Cork") in assigned

    def test_parts_keep_the_settlements_county_not_the_areas(self):
        """Limerick's agglomeration reaches into Clare and Waterford's into
        Kilkenny. A part filed under the neighbour would be refused by the
        cross-county guard in site.py and vanish from both pages."""
        sa_rows = [{"guid": "core", "lat": "0.5", "lon": "0.5"}]
        assigned = [("core", "CITY", "Bigton city and suburbs", "Limerick")]
        index = TownIndex([("L1", "Shannon", "Clare", [self.LEFT])])
        out, _ = split_large_settlements(
            assigned, sa_rows, {"core": 60_000}, index, {"L1": 60_000}
        )
        assert out == [("core", "CITY-L1", "Shannon", "Limerick")]

    def test_a_small_area_no_electoral_area_claims_is_pooled(self):
        sa_rows = [{"guid": "core", "lat": "9.0", "lon": "9.0"}]
        assigned = [("core", "CITY", "Bigton city and suburbs", "Cork")]
        index = TownIndex([("L1", "Inner Bigton", "Cork", [self.LEFT])])
        out, _ = split_large_settlements(
            assigned, sa_rows, {"core": 60_000}, index, {"L1": 60_000}
        )
        assert out == [("core", "CITY-rest", "Elsewhere in Bigton city", "Cork")]


class TestElsewhereLabel:
    def test_the_suburbs_suffix_is_dropped(self):
        assert elsewhere_label("Dublin city and suburbs") == "Elsewhere in Dublin city"
        assert elsewhere_label("Somewhere") == "Elsewhere in Somewhere"
