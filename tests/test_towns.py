from uisce.towns import TownIndex, assign_small_areas, check_populations, contains

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
