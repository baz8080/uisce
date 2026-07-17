from datetime import datetime, timezone

from uisce.site import (
    SmallAreaIndex,
    build_site,
    classify,
    grade,
    merge,
    month_bounds,
    month_list,
    norm_scheme,
    paired_lift,
    union_seconds,
)

UTC = timezone.utc


def _dt(iso):
    return datetime.fromisoformat(iso).astimezone(UTC)


def _case(**overrides):
    base = {
        "id": 1,
        "county": "Carlow",
        "work_category": "burst_main",
        "work_type": "Unplanned",
        "status": "Closed",
        "title": "Burst Water Main - Carlow",
        "reference_num": "CAR00000001",
        "start_date": "2026-05-01T00:00:00+00:00",
        "location": "Somewhere",
        "full_lat": 52.836,
        "full_lon": -6.926,
        "boil_water_notice": 0,
        "do_not_drink": 0,
        "water_restrictions": 0,
        "reduced_pressure": 0,
        "end_duration_seconds": 86400.0,
    }
    base.update(overrides)
    return base


# one Small Area of 1,000 people sitting right on the test pin
SA_INDEX = SmallAreaIndex([(52.836, -6.926, "SA1", 1000)])
NOW = datetime(2026, 5, 10, tzinfo=UTC)


class TestClassify:
    def test_hard_category_is_outage_even_if_marked_planned(self):
        assert classify(_case(work_category="burst_main", work_type="Planned")) == "outage"

    def test_unplanned_repair_is_outage_but_planned_is_not(self):
        assert classify(_case(work_category="mains_repair", work_type=None)) == "outage"
        assert classify(_case(work_category="mains_repair", work_type="Planned")) == "maintenance"

    def test_non_disruptive_activity_never_accrues_as_outage(self):
        assert classify(_case(work_category="investigation")) == "maintenance"
        assert classify(_case(work_category="leak_detection")) == "maintenance"

    def test_quality_beats_works_and_lift_notices_are_ignored(self):
        assert classify(_case(boil_water_notice=1)) == "quality"
        assert classify(_case(work_category="discolouration")) == "quality"
        assert classify(_case(work_category="boil_notice_lifted")) is None

    def test_restriction_flags_are_degraded(self):
        assert classify(_case(work_category=None, work_type=None, reduced_pressure=1)) == "degraded"


class TestGrade:
    def test_thresholds(self):
        assert grade(99.95, 0) == "A"
        assert grade(99.8, 0) == "B"
        assert grade(99.5, 0) == "C"
        assert grade(99.2, 0) == "D"
        assert grade(98.0, 0) == "F"

    def test_quality_notice_knocks_one_step_and_d_goes_to_f(self):
        assert grade(99.95, 1) == "B"
        assert grade(99.2, 1) == "F"


class TestIntervals:
    def test_merge_joins_overlaps_and_union_clips(self):
        iv = merge([(_dt("2026-05-01T00:00"), _dt("2026-05-01T12:00")),
                    (_dt("2026-05-01T06:00"), _dt("2026-05-02T00:00"))])
        assert len(iv) == 1
        secs = union_seconds(iv, _dt("2026-05-01T18:00"), _dt("2026-05-03T00:00"))
        assert secs == 6 * 3600


class TestMonths:
    def test_month_list_spans_year_boundary(self):
        months = month_list(datetime(2026, 11, 20, tzinfo=UTC), datetime(2027, 1, 5, tzinfo=UTC))
        assert months == ["2026-11", "2026-12", "2027-01"]

    def test_month_bounds_december(self):
        lo, hi = month_bounds("2026-12")
        assert (lo.month, hi.year, hi.month) == (12, 2027, 1)


class TestSchemePairing:
    def test_norm_scheme_strips_boilerplate(self):
        assert norm_scheme("Ardfinnan Regional Public Water Supply") == "ardfinnan"
        assert norm_scheme("Castlerea PWS") == "castlerea"
        assert norm_scheme(None) == ""

    def test_paired_lift_matches_scheme_within_tolerance(self):
        lifts = {"Tipperary": [("ardfinnan", _dt("2026-06-23T10:00"))]}
        start = _dt("2026-06-07T00:00")
        assert paired_lift(lifts, "Tipperary", "Ardfinnan PWS", start) is not None
        # a lift long before the issue is a different, older notice
        early = {"Tipperary": [("ardfinnan", _dt("2026-05-01T00:00"))]}
        assert paired_lift(early, "Tipperary", "Ardfinnan PWS", start) is None


class TestSmallAreaIndex:
    def test_pin_on_top_of_sa_finds_it(self):
        assert SA_INDEX.affected(52.836, -6.926) == {"SA1": 1000}

    def test_distant_pin_falls_back_to_nearest_within_8km(self):
        assert SA_INDEX.affected(52.86, -6.926) == {"SA1": 1000}

    def test_very_remote_pin_affects_nothing(self):
        assert SA_INDEX.affected(54.5, -8.5) == {}


class TestBuildSite:
    def test_outage_accrues_population_weighted_downtime(self):
        site = build_site([_case()], SA_INDEX, NOW)
        month = site["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 24 * 1000
        assert month["availability"] < 100.0
        assert month["median_fix_h"] == 24.0
        assert month["fixed_n"] == 1
        assert site["national"]["2026-05"]["median_fix_h"] == 24.0

    def test_multi_pin_event_counts_once(self):
        rows = [_case(id=1), _case(id=2, full_lat=52.837)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1

    def test_closed_case_without_end_signal_still_marks_its_day(self):
        rows = [_case(end_duration_seconds=None, status="Closed")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 0
        assert month["days"][0][0] == "outage"  # May 1st is not a false green
        assert month["median_fix_h"] is None  # unknown ends can't drag the median

    def test_open_boil_notice_closed_by_paired_lift_and_knocks_grade(self):
        issue = _case(
            work_category="boil_notice_issued",
            boil_water_notice=1,
            status="Open",
            end_duration_seconds=None,
            location="Ardfinnan Public Water Supply",
            reference_num="TIP1",
        )
        lift = _case(
            id=99,
            work_category="boil_notice_lifted",
            status="Closed",
            end_duration_seconds=None,
            location="Ardfinnan Regional Water Supply Scheme",
            reference_num="TIP2",
            start_date="2026-05-03T00:00:00+00:00",
        )
        month = build_site([issue, lift], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["quality"] == 1
        # interval closed at the lift, not running to "now"
        assert month["days"][1][0] == "quality"  # May 2: active
        assert month["days"][4][0] == ""  # May 5: lifted
        assert month["grade"] == "B"  # would be A on availability alone

    def test_days_before_collection_start_are_no_data(self):
        site = build_site([_case()], SA_INDEX, NOW)
        april = site["counties"]["Carlow"]["months"]["2026-04"]
        assert april["days"][0] == ["nd", 0]  # Apr 1
        assert april["days"][19][0] != "nd"  # Apr 20

    def test_future_scheduled_end_does_not_accrue_beyond_now(self):
        rows = [_case(start_date="2026-05-09T00:00:00+00:00",
                      end_duration_seconds=10 * 86400.0, status="Open")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 24 * 1000  # May 9 -> NOW (May 10) only
