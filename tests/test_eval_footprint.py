from datetime import datetime, timezone

from conftest import site_case as _case

from uisce.eval_footprint import NearestPeopleIndex, compare, county_months, report, spearman
from uisce.site import SmallAreaIndex

UTC = timezone.utc
NOW = datetime(2026, 6, 10, tzinfo=UTC)

# SA1 under the default pin, SA2 1.1 km north of it, SA3 out of reach
SA_ROWS = [
    (52.836, -6.926, "SA1", 200),
    (52.846, -6.926, "SA2", 300),
    (53.500, -6.926, "SA3", 500),
]


class TestNearestPeopleIndex:
    def test_reaches_past_the_radius_until_the_headcount_is_met(self):
        index = NearestPeopleIndex(SA_ROWS, 400)
        assert index.affected(52.836, -6.926) == {"SA1": 200, "SA2": 300}

    def test_stops_at_the_nearest_area_that_fills_it(self):
        index = NearestPeopleIndex(SA_ROWS, 150)
        assert index.affected(52.836, -6.926) == {"SA1": 200}

    def test_gives_up_at_the_fallback_distance(self):
        index = NearestPeopleIndex(SA_ROWS, 10_000)
        assert index.affected(52.836, -6.926) == {"SA1": 200, "SA2": 300}


class TestCountyMonths:
    def test_covers_finished_months_only(self):
        months = county_months([_case()], SmallAreaIndex(SA_ROWS), NOW)["Carlow"]
        assert sorted(months) == ["2026-04", "2026-05"]
        assert months["2026-05"][0] == 24 * 200


class TestCompare:
    BASE = {
        "Carlow": {"2026-05": (100.0, 100_000.0)},
        "Kerry": {"2026-05": (900.0, 100_000.0)},
    }

    def test_the_same_footprint_moves_nothing(self):
        pooled, moved, graded = compare(self.BASE, self.BASE)
        assert moved == [] and graded == 2
        assert pooled["Kerry"][0] == pooled["Kerry"][1]

    def test_a_uniformly_larger_footprint_is_rescaled_away(self):
        doubled = {
            c: {ym: (2 * ph, pop_h) for ym, (ph, pop_h) in months.items()}
            for c, months in self.BASE.items()
        }
        pooled, moved, _ = compare(self.BASE, doubled)
        assert moved == []
        assert pooled["Carlow"][1] == pooled["Carlow"][0]

    def test_a_redistribution_moves_letters(self):
        swapped = {"Carlow": self.BASE["Kerry"], "Kerry": self.BASE["Carlow"]}
        _, moved, _ = compare(self.BASE, swapped)
        assert {(c, was, now) for _, c, was, now in moved} == {
            ("Carlow", "A", "D"),
            ("Kerry", "D", "A"),
        }


def test_spearman_of_a_reversed_order_is_minus_one():
    a = {"x": 1.0, "y": 2.0, "z": 3.0}
    assert spearman(a, {"x": 3.0, "y": 2.0, "z": 1.0}) == -1.0


def test_report_names_the_variant_and_every_county():
    lines = report(TestCompare.BASE, {1000: TestCompare.BASE})
    assert lines[0].startswith("Nearest 1,000 people")
    assert sum(line.strip().startswith(("Carlow", "Kerry")) for line in lines) == 2
