from datetime import datetime, timezone

from uisce.site import (
    UNPLACED,
    SmallAreaIndex,
    TownLookup,
    boil_notice_fate,
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
        "closed_at": None,
        "full_lat": 52.836,
        "full_lon": -6.926,
        "boil_water_notice": 0,
        "do_not_drink": 0,
        "water_restrictions": 0,
        "reduced_pressure": 0,
        "notice_to_end_seconds": 86400.0,
        "end_source": "completion_update",
        "end_local_date": "2026-05-02",
    }
    base.update(overrides)
    return base


# one Small Area of 1,000 people sitting right on the test pin
SA_INDEX = SmallAreaIndex([(52.836, -6.926, "SA1", 1000)])
NOW = datetime(2026, 5, 10, tzinfo=UTC)

# that Small Area is inside a Co. Carlow settlement; the pin therefore lands
# in the town rather than the unplaced bucket
TOWNS = TownLookup([("SA1", "T1", "Testtown", "Carlow")], SA_INDEX.pop)


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


class TestBoilNoticeFate:
    """The whole boil-notice policy. See notes/boil-notices.md."""

    def _notice(self, **overrides):
        defaults = {
            "work_category": "boil_notice_issued",
            "boil_water_notice": 1,
            "notice_to_end_seconds": None,
            "status": "Open",
        }
        return _case(**(defaults | overrides))

    def test_paired_lift_gives_the_real_end(self):
        lifts = {"Carlow": [("somewhere", _dt("2026-05-04T09:00:00+00:00"))]}
        outcome, end = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-05-04T09:00:00+00:00")

    def test_recent_unpaired_notice_still_accrues(self):
        """9 days old at NOW: 'Open' is plausible, so it runs to now."""
        outcome, end = boil_notice_fate(self._notice(), {}, NOW)
        assert outcome == "accrue"
        assert end == NOW

    def test_stale_open_notice_is_excluded_not_accrued(self):
        """Older than CAP_DAYS with no lift: the feed's 'Open' is not credible.

        Case 221165 sat 'Open' from 2025-11-13 while its own description said it
        had been lifted; accruing these fabricated ~37 days of quality downtime.
        """
        old = self._notice(start_date="2026-01-01T00:00:00+00:00")
        assert boil_notice_fate(old, {}, NOW) == ("exclude", None)

    def test_stale_notice_with_a_lift_is_still_paired(self):
        """Exclusion must not beat a real end signal."""
        old = self._notice(start_date="2026-01-01T00:00:00+00:00")
        lifts = {"Carlow": [("somewhere", _dt("2026-01-05T00:00:00+00:00"))]}
        outcome, end = boil_notice_fate(old, lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-01-05T00:00:00+00:00")

    def test_closed_notice_without_a_lift_gets_no_end(self):
        closed = self._notice(status="Closed")
        assert boil_notice_fate(closed, {}, NOW) == ("closed_no_signal", None)

    def test_lift_before_the_pin_start_clamps_to_start(self):
        """Multi-pin lifts publish untidily; a negative duration must not result."""
        lifts = {"Carlow": [("somewhere", _dt("2026-04-30T00:00:00+00:00"))]}
        outcome, end = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-05-01T00:00:00+00:00")


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
        assert month["median_completion_h"] == 24.0
        assert month["completed_n"] == 1
        assert site["national"]["2026-05"]["median_completion_h"] == 24.0

    def test_scheduled_end_accrues_downtime_but_stays_out_of_the_headline(self):
        # a scheduled finish is a published plan, not evidence the works ended
        # then, so it must not be pooled into the completion median
        rows = [_case(end_source="scheduled_end_with_time")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 24 * 1000  # still accrues
        assert month["median_completion_h"] is None
        assert month["completed_n"] == 0
        assert month["median_scheduled_h"] == 24.0
        assert month["scheduled_n"] == 1

    def test_headline_median_ignores_scheduled_ends(self):
        # pooling would give median 13h; the observed-only headline is 2h
        rows = [
            _case(id=1, reference_num="CAR1", notice_to_end_seconds=2 * 3600),
            _case(id=2, reference_num="CAR2", full_lat=52.900,
                  end_source="scheduled_end_with_time", notice_to_end_seconds=24 * 3600),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["median_completion_h"] == 2.0
        assert month["completed_n"] == 1
        assert month["scheduled_n"] == 1

    def test_multi_pin_event_counts_once(self):
        rows = [_case(id=1), _case(id=2, full_lat=52.837)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1

    def test_closed_case_without_end_signal_still_marks_its_day(self):
        rows = [_case(notice_to_end_seconds=None, status="Closed",
                      end_source="not_found", end_local_date=None)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 0
        assert month["days"][0][0] == "outage"  # May 1st is not a false green
        assert month["median_completion_h"] is None  # unknown ends can't drag the median

    def test_open_case_whose_text_says_it_ended_does_not_accrue_to_now(self):
        # the negative-span family: build.py nulls the span when the reported
        # end precedes publication, but the works are over — a stale 'Open'
        # must not turn that into 9 days of fabricated downtime
        rows = [_case(status="Open", notice_to_end_seconds=None,
                      end_source="completion_update", end_local_date="2026-05-01")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 0
        assert month["days"][0][0] == "outage"  # its day still colours
        assert month["median_completion_h"] is None  # no usable span either way

    def test_open_case_with_no_signal_at_all_still_accrues(self):
        # end_source None = downloaded since the last uisce-infer run
        for source in ("not_found", None):
            rows = [_case(status="Open", notice_to_end_seconds=None,
                          end_source=source, end_local_date=None)]
            month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
            assert month["person_h"] == 9 * 24 * 1000  # May 1 -> NOW, uncapped

    def test_open_boil_notice_closed_by_paired_lift_and_knocks_grade(self):
        issue = _case(
            work_category="boil_notice_issued",
            boil_water_notice=1,
            status="Open",
            notice_to_end_seconds=None,
            location="Ardfinnan Public Water Supply",
            reference_num="TIP1",
        )
        lift = _case(
            id=99,
            work_category="boil_notice_lifted",
            status="Closed",
            notice_to_end_seconds=None,
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
                      notice_to_end_seconds=10 * 86400.0, status="Open")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 24 * 1000  # May 9 -> NOW (May 10) only

    def test_towns_are_absent_without_a_lookup(self):
        assert build_site([_case()], SA_INDEX, NOW)["counties"]["Carlow"]["towns"] == {}


class TestTownLookup:
    def test_pin_lands_in_the_settlement_holding_most_of_its_population(self):
        towns = TownLookup(
            [("SA1", "T1", "Small", "Carlow"), ("SA2", "T2", "Big", "Carlow")],
            {"SA1": 100, "SA2": 900},
        )
        assert towns.dominant({"SA1": 100, "SA2": 900}, "Carlow") == "T2"

    def test_a_pin_with_no_in_county_footprint_is_unplaced(self):
        towns = TownLookup([("SA1", "T1", "Small", "Carlow")], {"SA1": 100})
        assert towns.dominant({"SA9": 900}, "Carlow") == UNPLACED
        assert towns.dominant({}, "Carlow") == UNPLACED

    def test_the_best_area_in_the_case_s_own_county_wins_over_a_bigger_one_outside(self):
        """Border pins are real — a Kildare-labelled notice reaching Blessington,
        Co. Wicklow — but the case belongs to the page its county says it does, so
        it takes the best Kildare area rather than the larger Wicklow one."""
        towns = TownLookup(
            [("SA1", "T1", "Blessington", "Wicklow"), ("SA2", "T2", "Kilcullen", "Kildare")],
            {"SA1": 1000, "SA2": 100},
        )
        assert towns.dominant({"SA1": 1000, "SA2": 100}, "Kildare") == "T2"

    def test_within_keeps_only_the_part_of_a_footprint_inside_the_area(self):
        towns = TownLookup([("SA1", "T1", "Town", "Carlow")], {"SA1": 100})
        assert towns.within({"SA1": 100, "SA9": 900}, "T1") == {"SA1": 100}


class TestTownBreakdown:
    def _town(self, rows, code="T1", ym="2026-05", towns=TOWNS):
        county = build_site(rows, SA_INDEX, NOW, towns)["counties"]["Carlow"]
        return county["towns"][code]["months"][ym], county["towns"][code]

    def test_town_availability_is_measured_against_the_town_population(self):
        """The same 24h event that barely dents a county of 62,000 takes a ninth
        of the person-time of the 1,000-person town it actually happened in.
        That divergence is the point of the drill-down, not an error."""
        month, town = self._town([_case()])
        county = build_site([_case()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert town["pop"] == 1000
        assert month["person_h"] == county["months"]["2026-05"]["person_h"] == 24 * 1000
        assert month["availability"] == 88.89
        assert county["months"]["2026-05"]["availability"] == 99.821

    def test_towns_carry_no_letter_grade(self):
        month, _ = self._town([_case()])
        assert "grade" not in month

    def test_a_town_only_appears_in_months_it_had_a_case(self):
        _, town = self._town([_case()])
        assert list(town["months"]) == ["2026-05"]

    def test_person_hours_outside_the_town_are_not_attributed_to_it(self):
        """A pin whose footprint reaches beyond the settlement accrues the whole
        of it at county level and only the inside part at town level — otherwise
        a village could log person-hours for people who do not live in it."""
        sa_index = SmallAreaIndex([(52.836, -6.926, "SA1", 1000), (52.838, -6.926, "SA2", 400)])
        towns = TownLookup([("SA1", "T1", "Testtown", "Carlow")], sa_index.pop)
        county = build_site([_case()], sa_index, NOW, towns)["counties"]["Carlow"]
        assert county["months"]["2026-05"]["person_h"] == 24 * 1400
        assert county["towns"]["T1"]["months"]["2026-05"]["person_h"] == 24 * 1000

    def test_a_pin_whose_footprint_is_in_another_county_reports_no_denominator(self):
        """The feed's county and its own coordinates disagree for ~1.5% of
        case-months. There is no population to divide by, so the row carries its
        counts and nothing derived from one — rather than a flattering 100%."""
        towns = TownLookup([("SA1", "T1", "Over the border", "Wicklow")], {"SA1": 1000})
        county = build_site([_case()], SA_INDEX, NOW, towns)["counties"]["Carlow"]
        area = county["towns"][UNPLACED]
        assert area["name"] == "Pinned outside the county"
        assert area["unplaced"] is True and "pop" not in area
        month = area["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert "availability" not in month and "person_h" not in month

    def test_an_open_case_names_its_area_instead_of_being_listed_twice(self):
        """The county's list is the only copy; the front end groups it by area."""
        county = build_site([_case(status="Open")], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert [(o["title"], o["area"]) for o in county["open"]] == [
            ("Burst Water Main - Carlow", "T1")
        ]
        assert "open" not in county["towns"]["T1"]


class TestPayload:
    """The area breakdown is the bulk of the page, so anything zero, absent or
    implied is left out and the reader fills it in."""

    def test_zero_severities_are_dropped_from_an_area_month(self):
        month = build_site([_case()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert month["towns"]["T1"]["months"]["2026-05"]["events"] == {"outage": 1}
        # the county keeps every severity: its row always renders all four
        assert set(month["months"]["2026-05"]["events"]) == {
            "outage", "quality", "degraded", "maintenance"
        }

    def test_a_month_with_no_person_hours_omits_the_field(self):
        rows = [_case(notice_to_end_seconds=None, status="Closed",
                      end_source="not_found", end_local_date=None)]
        month = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        area_month = month["towns"]["T1"]["months"]["2026-05"]
        assert "person_h" not in area_month
        assert area_month["availability"] == 100.0

    def test_a_month_with_nothing_resolved_omits_the_count(self):
        month = build_site([_case()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert "resolved_n" not in month["towns"]["T1"]["months"]["2026-05"]


class TestResolved:
    """cases.closed_at is the only field with a month dimension for a case that
    is no longer open — see PR #21 and notes/data-quality.md."""

    def test_a_closed_case_is_listed_under_the_month_it_was_observed_to_close(self):
        rows = [_case(status="Closed", closed_at="2026-05-06T04:00:00+00:00")]
        county = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert county["resolved"]["2026-05"]["n"] == 1
        assert county["resolved"]["2026-05"]["cases"][0]["closed"] == "2026-05-06"
        assert county["towns"]["T1"]["months"]["2026-05"]["resolved_n"] == 1

    def test_a_case_that_closed_before_the_column_existed_is_not_counted(self):
        """NULL closed_at is ambiguous, so it is reported as nothing rather than
        guessed at."""
        rows = [_case(status="Closed", closed_at=None)]
        assert build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]["resolved"] == {}

    def test_an_open_case_is_never_listed_as_resolved(self):
        rows = [_case(status="Open", closed_at="2026-05-06T04:00:00+00:00")]
        county = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert county["resolved"] == {}
        assert county["open_total"] == 1

    def test_a_multi_pin_event_resolves_once(self):
        rows = [
            _case(id=1, status="Closed", closed_at="2026-05-06T04:00:00+00:00"),
            _case(id=2, status="Closed", closed_at="2026-05-06T04:00:00+00:00"),
        ]
        county = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert county["resolved"]["2026-05"]["n"] == 1

    def test_the_listed_cases_are_capped_but_the_count_is_not(self):
        rows = [
            _case(id=i, reference_num=f"CAR{i}", status="Closed",
                  closed_at=f"2026-05-{i + 1:02d}T04:00:00+00:00")
            for i in range(25)
        ]
        resolved = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]["resolved"]
        assert resolved["2026-05"]["n"] == 25
        assert len(resolved["2026-05"]["cases"]) == 20
        # newest first, so the cap drops the oldest
        assert resolved["2026-05"]["cases"][0]["closed"] == "2026-05-25"
