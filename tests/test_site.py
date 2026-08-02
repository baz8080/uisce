from datetime import date, datetime, time, timezone

from uisce.site import (
    UNPLACED,
    SmallAreaIndex,
    TownLookup,
    boil_notice_fate,
    build_site,
    classify,
    daily_windows,
    event_windows,
    grade,
    merge,
    month_bounds,
    month_list,
    norm_scheme,
    paired_lift,
    recurrence_report,
    resolve_case,
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
        "end_local_time": "00:00",
        # prompt v3; NULL on every v2 record, which reads as "not recurring"
        "end_recurrence": None,
        "end_window_open": None,
        "end_window_close": None,
        "end_window_first_date": None,
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

    def test_a_lifted_do_not_consume_notice_is_not_an_event(self):
        # the lift is good news, like boil_notice_lifted. One of these was stored
        # as an *issued* do-not-consume notice, inverting its meaning and knocking
        # a grade off Cork.
        assert classify(_case(work_category="consumption_notice_lifted")) is None

    def test_an_unclassifiable_title_does_not_accrue_as_an_outage(self):
        # NULL work_category used to group with the unplanned repairs and accrue
        # full supply downtime, so every spelling the rule table missed — a bare
        # reference number, a title of literally "unknown" — invented a national
        # outage. Nothing is evidenced by an unparseable title, so nothing accrues.
        assert classify(_case(work_category=None, work_type=None)) == "maintenance"
        assert classify(_case(work_category=None, work_type="Unplanned")) == "maintenance"


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


# May is in progress under NOW, and the top ten is a finished-month list, so
# these need a clock that has left May behind
AFTER_MAY = datetime(2026, 6, 15, tzinfo=UTC)


class TestTopEvents:
    """The largest individual disruptions nationally. Nothing else on the site
    ranks a single event — person-hours exist per county and per area only."""

    def test_events_rank_by_person_hours_across_counties(self):
        rows = [
            # Carlow: 1,000 people for 24h; Kildare: 1,000 people for 48h
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="KIL1", county="Kildare",
                  notice_to_end_seconds=48 * 3600, end_local_date="2026-05-03"),
        ]
        top = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]["2026-05"]
        assert [r["county"] for r in top] == ["Kildare", "Carlow"]
        assert [r["person_h"] for r in top] == [48 * 1000, 24 * 1000]
        assert [r["hours"] for r in top] == [48.0, 24.0]
        assert top[0]["people"] == 1000

    def test_the_in_progress_month_is_excluded(self):
        # the whole scope decision: an open event accruing toward the 14-day cap
        # would reshuffle the list between builds
        rows = [_case()]
        assert "2026-05" not in build_site(rows, SA_INDEX, NOW, TOWNS)["top"]
        assert "2026-05" in build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]

    def test_the_list_is_capped_at_ten(self):
        rows = [
            _case(id=i, reference_num=f"CAR{i}", notice_to_end_seconds=(i + 1) * 3600,
                  end_local_date="2026-05-03")
            for i in range(15)
        ]
        top = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]["2026-05"]
        assert len(top) == 10
        # largest first, so the cap drops the shortest five
        assert top[0]["hours"] == 15.0
        assert top[-1]["hours"] == 6.0

    def test_only_supply_disruptions_are_ranked(self):
        # pins the classification fix to the page: a restriction notice ran at #9
        # nationally in July 2026 purely because its title spelling was missing
        # from the rule table
        rows = [
            _case(id=1, reference_num="CAR1", work_category="water_conservation",
                  notice_to_end_seconds=200 * 3600, end_local_date="2026-05-09"),
            _case(id=2, reference_num="CAR2", work_category="investigation",
                  notice_to_end_seconds=200 * 3600, end_local_date="2026-05-09"),
            _case(id=3, reference_num="CAR3"),
        ]
        top = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]["2026-05"]
        assert [r["ref"] for r in top] == ["CAR3"]

    def test_a_multi_pin_event_is_one_row(self):
        rows = [_case(id=1), _case(id=2, full_lat=52.837)]
        top = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]["2026-05"]
        assert len(top) == 1
        assert top[0]["pins"] == 2

    def test_the_badge_counts_pins_not_events(self):
        """Region.observed_end is OR'd across an event's pins, so it would call
        this an observed completion; 3 of its 4 notices only stated a plan."""
        rows = [_case(id=1)] + [
            _case(id=i, end_source="scheduled_end_with_time") for i in (2, 3, 4)
        ]
        row = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)["top"]["2026-05"][0]
        assert (row["pins"], row["confirmed"], row["scheduled"]) == (4, 1, 3)

    def test_an_event_spanning_two_months_is_split_at_the_boundary(self):
        # 48h from 31 May 12:00: 12h in May, 36h in June
        rows = [_case(start_date="2026-05-31T12:00:00+00:00",
                      notice_to_end_seconds=48 * 3600, end_local_date="2026-06-02")]
        site = build_site(rows, SA_INDEX, datetime(2026, 7, 5, tzinfo=UTC), TOWNS)
        assert site["top"]["2026-05"][0]["person_h"] == 12 * 1000
        assert site["top"]["2026-06"][0]["person_h"] == 36 * 1000
        # and each half matches what the county reports for that month
        months = site["counties"]["Carlow"]["months"]
        assert site["top"]["2026-05"][0]["person_h"] == months["2026-05"]["person_h"]
        assert site["top"]["2026-06"][0]["person_h"] == months["2026-06"]["person_h"]

    def test_a_row_names_the_area_holding_most_of_the_footprint(self):
        # two Small Areas in different settlements; the larger one names the row,
        # even though the first pin sits in the smaller
        sa = SmallAreaIndex([(52.836, -6.926, "SA1", 100), (52.837, -6.926, "SA2", 900)])
        towns = TownLookup(
            [("SA1", "T1", "Smallville", "Carlow"), ("SA2", "T2", "Bigtown", "Carlow")],
            sa.pop,
        )
        rows = [_case(id=1, full_lat=52.836), _case(id=2, full_lat=52.837)]
        top = build_site(rows, sa, AFTER_MAY, towns)["top"]["2026-05"]
        assert top[0]["area"] == "Bigtown"

    def test_the_ranking_works_without_a_town_lookup(self):
        # every TestBuildSite case calls build_site this way
        top = build_site([_case()], SA_INDEX, AFTER_MAY)["top"]["2026-05"]
        assert len(top) == 1
        assert "area" not in top[0]


class TestDailyWindows:
    """The pure clock function behind a recurring window.

    A notice reading "daily from 10pm until 7am, from 9 July to 27 July" is
    eighteen nights of nine hours. Charged as one continuous block it was 385.2
    hours, which made a single Donegal event 9.9% of July 2026's national
    person-hours and the top row of the national ranking.
    """

    def _hours(self, windows):
        return sum((e - s).total_seconds() for s, e in windows) / 3600

    def test_a_nightly_window_expands_to_one_interval_per_night(self):
        windows = daily_windows(
            date(2026, 7, 9), time(22, 0), time(7, 0),
            _dt("2026-07-09T00:00:00+00:00"), _dt("2026-07-27T06:00:00+00:00"),
        )
        assert len(windows) == 18
        assert self._hours(windows) == 162.0

    def test_the_midnight_crossing_comes_from_the_times_not_the_wording(self):
        """The feed calls a 10pm-7am window "daily". A rule that trusted that word
        would produce a negative-length window; the times say it themselves."""
        windows = daily_windows(
            date(2026, 5, 1), time(22, 0), time(7, 0),
            _dt("2026-05-01T00:00:00+00:00"), _dt("2026-05-04T06:00:00+00:00"),
        )
        assert self._hours(windows) == 27.0  # 3 nights x 9h, not 3 x 15h
        assert all(e > s for s, e in windows)

    def test_a_same_day_window_closes_on_its_own_date(self):
        """The overnight offset must not leak into a window that doesn't cross."""
        windows = daily_windows(
            date(2026, 5, 4), time(8, 0), time(17, 0),
            _dt("2026-05-04T00:00:00+00:00"), _dt("2026-05-08T16:00:00+00:00"),
        )
        assert len(windows) == 5
        assert self._hours(windows) == 45.0
        assert windows[-1][1] == _dt("2026-05-08T16:00:00+00:00")

    def test_a_window_covering_the_whole_day_expands_to_nothing(self):
        """24h a day *is* continuous. Expanding would produce touching intervals
        that merge rejoins anyway, so the caller keeps its single interval."""
        assert daily_windows(
            date(2026, 5, 1), time(9, 0), time(9, 0),
            _dt("2026-05-01T00:00:00+00:00"), _dt("2026-05-05T08:00:00+00:00"),
        ) == []

    def test_the_night_the_clocks_go_forward_is_an_hour_shorter(self):
        """These are wall-clock times: 10pm Irish is a different UTC instant either
        side of a transition, so the series is converted per date, not offset once."""
        windows = daily_windows(
            date(2027, 3, 27), time(22, 0), time(7, 0),
            _dt("2027-03-27T00:00:00+00:00"), _dt("2027-03-28T06:00:00+00:00"),
        )
        assert self._hours(windows) == 8.0

    def test_the_night_the_clocks_go_back_is_an_hour_longer(self):
        windows = daily_windows(
            date(2026, 10, 24), time(22, 0), time(7, 0),
            _dt("2026-10-24T00:00:00+00:00"), _dt("2026-10-25T07:00:00+00:00"),
        )
        assert self._hours(windows) == 10.0

    def test_a_window_already_open_at_publication_is_clipped_not_dropped(self):
        """A notice published mid-series must keep the remainder of the window it
        was published inside — hence seeding the loop a day early."""
        windows = daily_windows(
            date(2026, 5, 1), time(22, 0), time(7, 0),
            _dt("2026-05-02T02:00:00+00:00"), _dt("2026-05-04T06:00:00+00:00"),
        )
        assert windows[0] == (_dt("2026-05-02T02:00:00+00:00"), _dt("2026-05-02T06:00:00+00:00"))

    def test_a_series_starting_after_the_span_ends_expands_to_nothing(self):
        assert daily_windows(
            date(2026, 9, 1), time(22, 0), time(7, 0),
            _dt("2026-05-01T00:00:00+00:00"), _dt("2026-05-04T06:00:00+00:00"),
        ) == []


def _recurring(**overrides):
    """The DON00115765 shape: nightly 22:00-07:00 published as one notice.

    Published 1 May 09:00Z, running until 8 May 07:00 local (06:00Z) — a 165h
    span that covers 63h across 7 nights.
    """
    base = {
        "start_date": "2026-05-01T09:00:00+00:00",
        "end_source": "scheduled_end_with_time",
        "end_local_date": "2026-05-08",
        "end_local_time": "07:00",
        "end_recurrence": "daily",
        "end_window_open": "22:00",
        "end_window_close": "07:00",
        "end_window_first_date": "2026-05-01",
        "notice_to_end_seconds": 165 * 3600.0,
    }
    return _case(**(base | overrides))


class TestRecurrenceGuard:
    """What resolve_case believes. A refusal is a numeric no-op — it keeps the
    single interval it would have used anyway — which is what lets these checks
    be as suspicious as they are."""

    def _resolve(self, row):
        return resolve_case(row, SA_INDEX, {}, NOW)

    def test_a_notice_claiming_no_recurrence_keeps_its_single_interval(self):
        """The no-op proof for the 9,000-odd rows that are not recurring."""
        case = self._resolve(_case())
        assert case.rec == "none"
        assert len(case.intervals) == 1

    def test_a_recurring_notice_expands(self):
        case = self._resolve(_recurring())
        assert case.rec == "expanded"
        assert len(case.intervals) == 7

    def test_a_close_time_contradicting_the_reported_end_is_refused(self):
        """The prompt requires the reported end to be the last date *at the
        window's closing time*, so a disagreement is the model contradicting
        itself — and the field that survives is the one the eval round validates."""
        case = self._resolve(_recurring(end_local_time="12:02"))
        assert case.rec.startswith("refused")
        assert len(case.intervals) == 1

    def test_a_completion_update_expands_without_the_cross_check(self):
        """Its local_time is the completion, not a window close, so the
        cross-check is unavailable. Refusing them would drop the recurring inputs
        to the completion median — and, because coverage is unioned per event, one
        refused pin re-covers every gap the others carved out."""
        case = self._resolve(_recurring(end_source="completion_update", end_local_time="12:02"))
        assert case.rec == "expanded_observed"
        assert len(case.intervals) > 1

    def test_a_single_window_claim_falls_back_to_one_interval(self):
        """Nearly every notice contains something like "from 9am until 5pm", so a
        one-window recurrence is the cheapest false positive to make."""
        case = self._resolve(_recurring(
            end_local_date="2026-05-02", notice_to_end_seconds=21 * 3600.0,
            end_window_first_date="2026-05-01",
        ))
        assert case.rec == "refused: single window in span"
        assert len(case.intervals) == 1

    def test_an_unrecognised_recurrence_value_is_refused(self):
        """Fails closed, so a future prompt can widen the vocabulary without
        silently changing the arithmetic first."""
        case = self._resolve(_recurring(end_recurrence="weekdays"))
        assert case.rec == "none"
        assert len(case.intervals) == 1

    def test_unparseable_window_fields_are_refused(self):
        case = self._resolve(_recurring(end_window_open="10pm"))
        assert case.rec.startswith("refused")
        assert len(case.intervals) == 1

    def test_a_boil_notice_never_expands_even_when_a_window_is_claimed(self):
        """boil_notice_fate owns that class outright: its end is a paired lift,
        never its own text."""
        case = self._resolve(_recurring(
            work_category="boil_notice_issued", boil_water_notice=1, status="Open",
        ))
        assert case.rec == "none"
        assert len(case.intervals) == 1

    def test_recurrence_is_ignored_when_the_span_was_nulled(self):
        """The 532 cases whose notice was published after its own works window
        keep their token footprint; a new field must not reopen them."""
        case = self._resolve(_recurring(notice_to_end_seconds=None, status="Closed"))
        assert case.rec == "none"
        assert case.intervals == [(_dt("2026-05-01T09:00:00+00:00"),
                                   _dt("2026-05-01T09:00:01+00:00"))]


class TestRecurringIntervals:
    """End to end: what a recurring window costs, and what it still shows."""

    def test_a_nightly_series_charges_covered_hours_not_the_elapsed_span(self):
        month = build_site([_recurring()], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 63 * 1000  # 7 nights x 9h, not the 165h span

    def test_every_night_of_a_series_still_colours_its_day_bar(self):
        """The fix must reduce the price, not the visibility — a reader looking at
        the county should still see the disruption on every day it ran."""
        days = build_site([_recurring()], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert [d[0] for d in days["days"][:8]] == ["outage"] * 8

    def test_pins_with_different_series_ends_union_to_the_longest(self):
        rows = [
            _recurring(id=1),
            _recurring(id=2, end_local_date="2026-05-06", notice_to_end_seconds=117 * 3600.0),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 63 * 1000

    def test_one_unexpanded_pin_restores_the_continuous_block(self):
        """Coverage is unioned per event but expansion is decided per pin, so a
        single refusal re-covers every gap the others carved out. This is the
        failure mode that would make the fix look like it worked while doing
        nothing, and it is why the build report calls out mixed events."""
        rows = [_recurring(id=1), _recurring(id=2, end_local_time="12:02")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] > 150 * 1000

    def test_a_long_series_still_accrues_at_most_fourteen_days_of_presence(self):
        """CAP_DAYS is the backstop against a schedule running for months; it must
        survive interval-by-interval, not just on the collapsed span."""
        rows = [_recurring(
            start_date="2026-05-01T00:00:00+00:00", end_local_date="2026-06-30",
            end_window_open="12:00", end_window_close="18:00", end_local_time="18:00",
            notice_to_end_seconds=1458 * 3600.0,
        )]
        case = resolve_case(rows[0], SA_INDEX, {}, NOW)
        assert len(case.intervals) == 14
        assert case.intervals[-1][1] <= _dt("2026-05-15T00:00:00+00:00")

    def test_the_completion_median_reports_covered_hours(self):
        month = build_site(
            [_recurring(end_source="completion_update", end_local_time="12:02")],
            SA_INDEX, NOW,
        )["counties"]["Carlow"]["months"]["2026-05"]
        assert month["median_completion_h"] == 63.0

    def test_a_recurring_event_is_credited_to_the_month_it_was_published(self):
        """iv[0][0] is the first *window*, which can open in the month after the
        notice went up — the median is over events that started this month."""
        rows = [_recurring(
            start_date="2026-05-31T09:00:00+00:00", end_source="completion_update",
            end_window_first_date="2026-06-01", end_local_date="2026-06-05",
            end_local_time="07:00", notice_to_end_seconds=118 * 3600.0,
        )]
        site = build_site(rows, SA_INDEX, datetime(2026, 7, 1, tzinfo=UTC))
        months = site["counties"]["Carlow"]["months"]
        assert months["2026-05"]["completed_n"] == 1
        assert months["2026-06"]["completed_n"] == 0


class TestRecurrenceReport:
    """Printed on every build, matching backfill_work_category's unmatched-title
    report: a prompt that starts hallucinating recurrence would otherwise show up
    only as person-hours quietly falling."""

    def _report(self, rows):
        cases = [resolve_case(r, SA_INDEX, {}, NOW) for r in rows]
        pin_tags = {}
        for c in cases:
            pin_tags.setdefault((c.county, c.ref), []).append(c.rec)
        return recurrence_report([c for c in cases if c.rec != "none"], pin_tags)

    def _cases(self, rows):
        return [c for c in (resolve_case(r, SA_INDEX, {}, NOW) for r in rows) if c.rec != "none"]

    def test_nothing_claiming_recurrence_prints_nothing(self):
        assert recurrence_report(self._cases([_case()])) == []

    def test_an_expanded_series_reports_covered_against_continuous_hours(self):
        report = "\n".join(recurrence_report(self._cases([_recurring()])))
        assert "1 expanded" in report
        assert "63h charged where the continuous rule charged 165h" in report

    def test_a_refusal_is_reported_with_its_reason(self):
        report = "\n".join(recurrence_report(self._cases([_recurring(end_local_time="12:02")])))
        assert "refused: close time 07:00 != reported end time 12:02" in report

    def test_an_event_mixing_expanded_and_refused_pins_is_flagged(self):
        rows = [_recurring(id=1), _recurring(id=2, end_local_time="12:02")]
        report = "\n".join(self._report(rows))
        assert "mix expanded and unexpanded pins" in report
        assert "Carlow CAR00000001  1/2 pins expanded" in report

    def test_a_pin_that_claimed_no_window_at_all_still_flags_the_event(self):
        """The failure this report exists to catch, and the one it originally
        missed. DON00115765 published 17 notices describing a nightly window and
        one completion update describing none; the completion pin's continuous
        interval re-covered every gap the other seventeen carved out, and a check
        that looked only at pins *with* a claim could not see it. Its rec tag is
        "none", exactly like a burst main's, so it has to be counted per event."""
        rows = [_recurring(id=1), _case(id=2, end_source="completion_update")]
        report = "\n".join(self._report(rows))
        assert "mix expanded and unexpanded pins" in report
        assert "1/2 pins expanded (1x none)" in report

    def test_an_event_whose_pins_all_expand_is_not_flagged(self):
        report = "\n".join(self._report([_recurring(id=1), _recurring(id=2)]))
        assert "mix expanded" not in report


class TestSharedWindows:
    """A repeating window belongs to the works, not to the notice describing them.

    Uisce publishes one event as many pins over several days, and the pin
    carrying the completion update reports no window — reasonably, since a
    finished job has no forward schedule. But coverage is unioned per
    reference_num, so that pin's continuous interval re-covers every gap its
    siblings carved out: DON00115765 had 17 of 18 pins expanded on the first v3
    run and still kept 354h of its 385h.
    """

    def _completion_pin(self, **overrides):
        """A pin of the same event reporting a completion and no window.

        Published 1 May 00:00Z, complete 8 May 03:00 local = 02:00Z — deliberately
        *inside* the 22:00-07:00 night window, so the inherited series has to be
        truncated mid-window at the completion rather than run to 07:00.
        """
        return _case(id=2, end_source="completion_update", end_local_date="2026-05-08",
                     end_local_time="03:00", notice_to_end_seconds=170 * 3600.0, **overrides)

    def test_a_pin_with_no_window_inherits_one_from_its_sibling(self):
        rows = [_recurring(id=1), self._completion_pin()]
        shared = event_windows(rows)
        case = resolve_case(rows[1], SA_INDEX, {}, NOW, shared[("Carlow", "CAR00000001")])
        assert case.rec == "expanded_inherited"
        assert len(case.intervals) > 1

    def test_the_inherited_window_still_stops_at_the_pin_s_own_end(self):
        """This is what makes borrowing safe rather than a guess: the completion
        pin takes the schedule and then stops when it says the works stopped."""
        rows = [_recurring(id=1), self._completion_pin()]
        shared = event_windows(rows)
        case = resolve_case(rows[1], SA_INDEX, {}, NOW, shared[("Carlow", "CAR00000001")])
        # the final night is cut at the completion instant, not run to its 07:00 close
        assert case.intervals[-1] == (_dt("2026-05-07T21:00:00+00:00"),
                                      _dt("2026-05-08T02:00:00+00:00"))

    def test_the_whole_event_expands_once_the_last_pin_inherits(self):
        rows = [_recurring(id=1), self._completion_pin()]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 63 * 1000  # not the ~170h continuous block

    def test_an_event_no_pin_gave_a_window_is_untouched(self):
        """Inheritance must not invent a window for an ordinary event."""
        rows = [_case(id=1), _case(id=2)]
        assert event_windows(rows) == {}
        case = resolve_case(rows[0], SA_INDEX, {}, NOW, None)
        assert case.rec == "none"
        assert len(case.intervals) == 1

    def test_a_window_is_not_shared_across_different_events(self):
        rows = [_recurring(id=1), _case(id=2, reference_num="CAR00000002")]
        shared = event_windows(rows)
        assert ("Carlow", "CAR00000002") not in shared

    def test_an_inherited_window_faces_the_same_cross_check(self):
        """If a sibling's closing time disagrees with this pin's own scheduled
        end, the two notices describe different things and the loan is refused."""
        rows = [_recurring(id=1), _case(id=2, end_source="scheduled_end_with_time",
                                        end_local_time="15:00", end_local_date="2026-05-08",
                                        notice_to_end_seconds=170 * 3600.0)]
        shared = event_windows(rows)
        case = resolve_case(rows[1], SA_INDEX, {}, NOW, shared[("Carlow", "CAR00000001")])
        assert case.rec.startswith("refused")
        assert len(case.intervals) == 1

    def test_a_pin_with_no_end_signal_never_inherits(self):
        """Recurrence lives under has_end. An open case accruing to now must keep
        that behaviour whatever its siblings reported."""
        rows = [_recurring(id=1), _case(id=2, status="Open", notice_to_end_seconds=None,
                                        end_source="not_found", end_local_date=None)]
        shared = event_windows(rows)
        case = resolve_case(rows[1], SA_INDEX, {}, NOW, shared[("Carlow", "CAR00000001")])
        assert case.rec == "none"
        assert len(case.intervals) == 1

    def test_the_commonest_window_wins_when_pins_disagree(self):
        """No event in the corpus disagrees today; the rule exists so that one
        does not resolve itself differently from build to build."""
        rows = [
            _recurring(id=1), _recurring(id=2),
            _recurring(id=3, end_window_open="20:00", end_window_close="06:00",
                       end_local_time="06:00"),
        ]
        assert event_windows(rows)[("Carlow", "CAR00000001")] == ("22:00", "07:00", "2026-05-01")

    def test_an_inherited_pin_counts_as_expanded_in_the_report(self):
        """Its tag has to start with "expanded" or the mixed-event check would
        flag the very event inheritance just repaired."""
        rows = [_recurring(id=1), self._completion_pin()]
        shared = event_windows(rows)
        cases = [resolve_case(r, SA_INDEX, {}, NOW, shared.get(("Carlow", "CAR00000001")))
                 for r in rows]
        tags = {("Carlow", "CAR00000001"): [c.rec for c in cases]}
        report = "\n".join(recurrence_report([c for c in cases if c.rec != "none"], tags))
        assert "mix expanded" not in report
        assert "inherit one from a sibling pin" in report
        assert "22:00-07:00 from 2026-05-01" in report
