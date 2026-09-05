import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone

import pytest
from conftest import site_case as _case
from test_pipeline import _cases_db

from uisce.config import BASE_URL
from uisce.pipeline import SCHEMA_VERSION
from uisce.site import (
    CAP_DAYS,
    COUNTY_POP,
    MIN_CATEGORY_N,
    UNPLACED,
    UNPLACED_LABEL,
    SmallAreaIndex,
    SpanTable,
    TownLookup,
    _area_index_html,
    _area_items,
    area_index,
    boil_notice_fate,
    build_site,
    classify,
    county_events,
    county_slug,
    daily_windows,
    data_horizon,
    describes_recurrence,
    event_windows,
    grade,
    load_cases,
    merge,
    month_bounds,
    month_list,
    norm_scheme,
    notice_paragraphs,
    paired_lift,
    read_cases,
    recurrence_report,
    recurring_events,
    resolve_case,
    union_seconds,
    write_site,
)

UTC = timezone.utc


def _dt(iso):
    return datetime.fromisoformat(iso).astimezone(UTC)


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
        assert classify(_case(work_category="boil_notice_issued")) == "quality"
        assert classify(_case(work_category="discolouration")) == "quality"
        assert classify(_case(work_category="boil_notice_lifted")) is None

    def test_the_feed_health_flags_do_not_override_the_category(self):
        """Measured 2026-08-18: both flags are redundant with the category, and
        do_not_drink is additionally wrong on 9 cases whose descriptions never
        mention drinking water. Reading them turned ordinary burst mains into
        quality events, where they accrued no downtime at all."""
        assert classify(_case(work_category="burst_main", do_not_drink=1)) == "outage"
        assert classify(_case(work_category="burst_main", boil_water_notice=1)) == "outage"
        assert classify(_case(work_category="mains_repair", work_type=None,
                              do_not_drink=1)) == "outage"
        # the categories still carry it, which is the whole point
        assert classify(_case(work_category="consumption_notice_issued",
                              do_not_drink=0)) == "quality"

    def test_restriction_flags_are_degraded(self):
        assert classify(_case(work_category=None, work_type=None, reduced_pressure=1)) == "degraded"

    def test_a_lifted_do_not_consume_notice_is_not_an_event(self):
        # the lift is good news, like boil_notice_lifted. One of these was stored
        # as an *issued* do-not-consume notice, inverting its meaning and knocking
        # a grade off Cork.
        assert classify(_case(work_category="consumption_notice_lifted")) is None

    def test_a_scheduled_repeating_window_is_a_restriction_whatever_the_title(self):
        """The title alone was deciding this, and Uisce uses two for one
        situation: the same Donegal villages under the same nightly 10pm-7am
        regime were published as "Water Conservation" in April, accruing nothing,
        and as "Reservoir Interruption" in June and July, accruing 949,824
        person-hours and topping the national ranking."""
        assert classify(_case(work_category="reservoir_interruption")) == "outage"
        assert classify(_case(work_category="reservoir_interruption"), recurring=True) == "degraded"
        assert classify(_case(work_category="burst_main"), recurring=True) == "degraded"
        assert classify(_case(work_category="mains_repair", work_type=None),
                        recurring=True) == "degraded"

    def test_a_repeating_window_never_promotes_something_that_was_not_an_outage(self):
        """A nightly leak-detection round is still works, not a restriction."""
        assert classify(_case(work_category="leak_detection"), recurring=True) == "maintenance"
        assert classify(_case(work_category="essential_works"), recurring=True) == "maintenance"
        assert classify(_case(work_category="boil_notice_issued"), recurring=True) == "quality"

    def test_the_notice_text_can_correct_the_feed_to_low_pressure(self):
        """Two Reservoir Interruption notices describe only low pressure. The
        pipeline sets reduced_pressure from the text, and classify already reads
        that flag ahead of the hard categories, so no severity rule is needed."""
        assert classify(_case(work_category="reservoir_interruption",
                              reduced_pressure=1)) == "degraded"

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
        lifts = {("Carlow", "boil_notice_lifted"):
                 [("somewhere", _dt("2026-05-04T09:00:00+00:00"))]}
        outcome, (_, end) = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-05-04T09:00:00+00:00")

    def test_recent_unpaired_notice_still_accrues(self):
        """9 days old at NOW: 'Open' is plausible, so it runs to now."""
        outcome, (_, end) = boil_notice_fate(self._notice(), {}, NOW)
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
        lifts = {("Carlow", "boil_notice_lifted"):
                 [("somewhere", _dt("2026-01-05T00:00:00+00:00"))]}
        outcome, (_, end) = boil_notice_fate(old, lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-01-05T00:00:00+00:00")

    def test_closed_notice_without_a_lift_gets_no_end(self):
        closed = self._notice(status="Closed")
        assert boil_notice_fate(closed, {}, NOW) == ("closed_no_signal", None)

    def test_lift_before_the_pin_start_clamps_to_start(self):
        """Multi-pin lifts publish untidily; a negative duration must not result."""
        lifts = {("Carlow", "boil_notice_lifted"):
                 [("somewhere", _dt("2026-04-30T00:00:00+00:00"))]}
        outcome, (_, end) = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "paired"
        assert end == _dt("2026-05-01T00:00:00+00:00")

    def test_a_late_lift_reports_the_real_end_uncapped(self):
        """`boil_notice_fate` answers when the notice ended, which is a different
        question from what it may charge. The cap is the caller's (`charged_end`),
        so this reports the lift itself — which is what lets the health marker
        stand on the evidence while the arithmetic stays bounded."""
        lifts = {("Carlow", "boil_notice_lifted"):
                 [("somewhere", _dt("2026-05-21T00:00:00+00:00"))]}
        outcome, (in_force, end) = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "paired"
        # the marker stands to the lift itself, 20 days out...
        assert in_force == [(_dt("2026-05-01T00:00:00+00:00"),
                             _dt("2026-05-21T00:00:00+00:00"))]
        # ...while the charge stops at the cap
        assert end == _dt("2026-05-01T00:00:00+00:00") + timedelta(days=CAP_DAYS)

    def test_a_lift_of_the_other_kind_never_pairs(self):
        """A do-not-consume lift for the same scheme is a different notice's end;
        pairing across kinds would close a boil notice a lift never mentioned."""
        lifts = {("Carlow", "consumption_notice_lifted"):
                 [("somewhere", _dt("2026-05-04T09:00:00+00:00"))]}
        outcome, _ = boil_notice_fate(self._notice(), lifts, NOW)
        assert outcome == "accrue"

    def test_an_advance_dated_notice_never_accrues_backwards(self):
        """The other end of the same clamp. The feed publishes notices dated ahead
        of publication and leaves them 'Open'; min(now, start + cap) alone puts the
        end before the start, which the clipped county arithmetic never sees but
        the area history prints as "-240h so far"."""
        future = self._notice(start_date="2026-05-20T00:00:00+00:00")
        outcome, (_, end) = boil_notice_fate(future, {}, NOW)
        assert outcome == "accrue"
        assert end == _dt("2026-05-20T00:00:00+00:00")


class TestGrade:
    def test_thresholds(self):
        assert grade(99.95) == "A"
        assert grade(99.8) == "B"
        assert grade(99.5) == "C"
        assert grade(99.2) == "D"
        assert grade(98.8) == "E"
        assert grade(98.0) == "F"

    def test_the_bands_meet_where_they_say_they_do(self):
        """Mid-band values alone would pass an off-by-one on any cut, and the
        legend prints these five numbers to the reader."""
        for cut, above, below in ((99.9, "A", "B"), (99.75, "B", "C"), (99.45, "C", "D"),
                                  (99.0, "D", "E"), (98.7, "E", "F")):
            assert grade(cut) == above
            assert grade(cut - 0.001) == below

    def test_the_grade_depends_on_availability_alone(self):
        """A health notice used to knock the letter one step. It was measured
        before it was removed: across 78 settled county-months it set the
        published letter for 8, and the median knocking notice would have cost
        0.003 points of availability had it accrued, against the 0.45 of the band
        it crossed — about a hundred times out of scale with everything else on
        the page. It is published beside the grade now; see TestHealthNotices."""
        assert grade(99.95) == grade(99.91) == "A"


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
        key = ("Tipperary", "boil_notice_lifted")
        lifts = {key: [("ardfinnan", _dt("2026-06-23T10:00"))]}
        start = _dt("2026-06-07T00:00")
        assert paired_lift(lifts, key, "Ardfinnan PWS", start) is not None
        # a lift long before the issue is a different, older notice
        early = {key: [("ardfinnan", _dt("2026-05-01T00:00"))]}
        assert paired_lift(early, key, "Ardfinnan PWS", start) is None
        # a do-not-consume lift naming the same scheme is a different notice's end
        other = {("Tipperary", "consumption_notice_lifted"):
                 [("ardfinnan", _dt("2026-06-23T10:00"))]}
        assert paired_lift(other, key, "Ardfinnan PWS", start) is None


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

    def test_closed_case_without_end_signal_is_charged_a_typical_span(self):
        """It used to take a token 1-second footprint and accrue nothing.

        Availability divides by a denominator fixed by population and calendar,
        so an event contributing no duration contributes a zero — and zero is
        the one value a real outage certainly did not last. It is charged the
        typical observed span instead, while staying out of the median.
        """
        rows = [
            _case(id=1, reference_num="CAR1"),  # observed, 24h: the evidence
            _case(id=2, reference_num="CAR2", full_lat=52.900, status="Closed",
                  notice_to_end_seconds=None, end_source="not_found", end_local_date=None),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 2
        assert month["person_h"] == 2 * 24 * 1000  # both accrue, not just the observed one
        assert month["days"][0][0] == "outage"  # May 1st is not a false green
        assert month["median_completion_h"] == 24.0  # the estimate does not enter it
        assert month["completed_n"] == 1
        assert month["imputed_n"] == 1

    def test_imputation_needs_evidence_to_draw_on(self):
        """With no observed completion anywhere in the corpus there is no typical
        span to charge, and the token footprint stands. A guess with nothing
        behind it is worse than the zero it replaces."""
        rows = [_case(notice_to_end_seconds=None, status="Closed",
                      end_source="not_found", end_local_date=None)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1
        assert month["person_h"] == 0
        assert month["days"][0][0] == "outage"
        assert month["median_completion_h"] is None
        # nothing was estimated, so there is no estimate to disclose — the event
        # still counts and still colours its day, as it always did
        assert month["imputed_n"] == 0

    def test_negative_span_case_is_charged_backwards_from_its_reported_end(self):
        """The negative-span family knows when it ended and only lost its start
        (start_date is re-stamped in place upstream). Charging forwards from
        publication would put the hours on the day the notice went up, days
        after the works finished."""
        rows = [
            _case(id=1, reference_num="CAR1"),  # observed, 24h: the evidence
            _case(id=2, reference_num="CAR2", full_lat=52.900, status="Open",
                  start_date="2026-05-10T00:00:00+00:00", notice_to_end_seconds=None,
                  end_source="completion_update", end_local_date="2026-05-05",
                  end_local_time="00:00"),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["imputed_n"] == 1
        # 24h charged backwards from 5 May 00:00 lands on 4 May, not on the 10th
        assert month["days"][3][0] == "outage"
        assert month["days"][9][0] == ""

    def test_open_case_whose_text_says_it_ended_does_not_accrue_to_now(self):
        # the negative-span family: build.py nulls the span when the reported
        # end precedes publication, but the works are over — a stale 'Open'
        # must not turn that into 9 days of fabricated downtime. It is now
        # charged a typical span rather than a token second, but the point of
        # this test is the ceiling: nowhere near the 14-day cap.
        rows = [
            _case(id=1, reference_num="CAR1"),  # observed, 24h: the evidence
            _case(id=2, reference_num="CAR2", full_lat=52.900, status="Open",
                  start_date="2026-05-10T00:00:00+00:00", notice_to_end_seconds=None,
                  end_source="completion_update", end_local_date="2026-05-08",
                  end_local_time="12:00"),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 2
        assert month["person_h"] == 2 * 24 * 1000  # a typical span each, not 9 days
        assert month["median_completion_h"] == 24.0  # no usable span of its own
        assert month["imputed_n"] == 1

    def test_open_case_with_no_signal_at_all_still_accrues(self):
        # end_source None = downloaded since the last uisce-infer run
        for source in ("not_found", None):
            rows = [_case(status="Open", notice_to_end_seconds=None,
                          end_source=source, end_local_date=None)]
            month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
            assert month["person_h"] == 9 * 24 * 1000  # May 1 -> NOW, uncapped

    def test_pooled_median_is_the_sensitivity_figure(self):
        """What the headline would be if the estimated events were let into it.

        Published beside the headline so the exclusion is arithmetic a reader
        can check rather than a silence. The headline itself must not move.
        """
        rows = [
            _case(id=1, reference_num="CAR1", notice_to_end_seconds=20 * 3600),
            _case(id=2, reference_num="CAR2", full_lat=52.900,
                  notice_to_end_seconds=20 * 3600),
            _case(id=3, reference_num="CAR3", full_lat=52.910, status="Closed",
                  notice_to_end_seconds=None, end_source="not_found", end_local_date=None),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["median_completion_h"] == 20.0
        assert month["completed_n"] == 2
        assert month["imputed_n"] == 1
        # the estimate is the observed median by construction, so pooling holds it
        assert month["median_pooled_h"] == 20.0

    def test_open_boil_notice_is_closed_by_its_paired_lift(self):
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
        # interval closed at the lift, not running to "now": an unpaired open
        # notice would still be in force on the 10th and read health_now == 1
        assert month["health_now"] == 0
        # quality never colours a bar — the healthmark carries it
        assert month["days"][1][0] == ""
        # the notice is reported beside the grade, not inside it
        assert month["grade"] == "A"
        assert month["health_n"] == 1

    def test_open_consumption_notice_is_closed_by_its_paired_lift(self):
        """Do-not-consume notices are published exactly like boil notices: the
        issue never states its own end and the lift is a separate case with a
        fresh reference_num. Before this they could never be paired at all and
        ran to the 14-day cap regardless of a lift sitting right there."""
        issue = _case(
            work_category="consumption_notice_issued",
            do_not_drink=1,
            status="Open",
            notice_to_end_seconds=None,
            # as all 7 on file are: the end is a different case, so there is
            # nothing in this notice's own text for the extraction to find
            end_source="not_found",
            end_local_date=None,
            location="Coolineagh Public Water Supply",
            reference_num="COR1",
        )
        lift = _case(
            id=99,
            work_category="consumption_notice_lifted",
            status="Closed",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            location="Coolineagh PWS",
            reference_num="COR2",
            start_date="2026-05-03T00:00:00+00:00",
        )
        month = build_site([issue, lift], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["quality"] == 1
        # closed at the lift: an unpaired open notice would still be in force
        assert month["health_now"] == 0
        assert month["health_n"] == 1

    def test_a_long_running_consumption_notice_is_capped_at_its_lift(self):
        """The class where this bites hardest: Whiddy Island has been Open since
        2022 and Dursey since 2024, and their capped intervals predate collection
        precisely because the cap holds. An uncapped paired lift would drag one
        of them forward over every month on the site at once."""
        issue = _case(
            work_category="consumption_notice_issued",
            status="Open",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            start_date="2026-04-21T00:00:00+00:00",
            location="Whiddy Island",
            reference_num="COR1",
        )
        lift = _case(
            id=99,
            work_category="consumption_notice_lifted",
            status="Closed",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            location="Whiddy Island",
            reference_num="COR2",
            start_date="2026-05-09T00:00:00+00:00",
        )
        months = build_site([issue, lift], SA_INDEX, NOW)["counties"]["Carlow"]["months"]
        # the cap itself (21 April + 14 days, not the 9 May lift) is asserted at
        # the boil_notice_fate level; here the event stays confined to the
        # months the charge touches, and colours no bar in either
        assert [months[ym]["events"]["quality"] for ym in ("2026-04", "2026-05")] == [1, 1]
        assert not any(d[0] == "quality" for m in months.values() for d in m["days"])

    def test_the_cap_bounds_the_arithmetic_but_not_the_health_marker(self):
        """The other half of the cap. Capping what a notice charges must not
        quietly withdraw the drinking-water warning from months its own lift
        proves it was standing — the grade was unbundled from the health notice
        exactly because a person-hours instrument is the wrong one for it. Here
        the lift lands two months out: the charge stops at 14 days, the marker
        does not."""
        issue = _case(
            work_category="consumption_notice_issued",
            status="Open",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            start_date="2026-05-01T00:00:00+00:00",
            location="Whiddy Island",
            reference_num="COR1",
        )
        lift = _case(
            id=99,
            work_category="consumption_notice_lifted",
            status="Closed",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            location="Whiddy Island",
            reference_num="COR2",
            start_date="2026-07-05T00:00:00+00:00",
        )
        july = datetime(2026, 7, 15, tzinfo=UTC)
        months = build_site([issue, lift], SA_INDEX, july)["counties"]["Carlow"]["months"]
        # in force 1 May - 5 July per the lift, so every one of those months
        # carries the marker
        assert [months[ym]["health_n"] for ym in ("2026-05", "2026-06", "2026-07")] == [1, 1, 1]
        # but the charge still stops at the cap: 14 days in May, nothing after
        assert months["2026-06"]["events"] == {
            "outage": 0, "quality": 0, "degraded": 0, "maintenance": 0
        }

    def test_a_notice_already_over_at_publication_does_not_take_a_later_lift(self):
        """A lift is only an end for a notice that was still running. This one's
        own text reported an end before it was published (`lifted_immediate`), so
        pairing it to a lift eight days later would invent the eight days — the
        fabrication ended_by_publication exists to refuse. It keeps the token
        footprint instead, and the lift still ends whatever it really ended."""
        issue = _case(
            work_category="consumption_notice_issued",
            status="Open",
            notice_to_end_seconds=None,
            end_source="lifted_immediate",
            location="Somewhere",
            reference_num="COR1",
        )
        lift = _case(
            id=99,
            work_category="consumption_notice_lifted",
            status="Closed",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            location="Somewhere",
            reference_num="COR2",
            start_date="2026-05-09T00:00:00+00:00",
        )
        lifts = {("Carlow", "consumption_notice_lifted"):
                 [(norm_scheme(lift["location"]), _dt(lift["start_date"]))]}
        case = resolve_case(issue, SA_INDEX, lifts, NOW)
        # the token footprint survives the available lift: pairing was refused
        assert case.intervals[0][1] - case.intervals[0][0] == timedelta(seconds=1)

    def test_health_now_separates_a_standing_notice_from_a_lifted_one(self):
        """health_n counts notices active at any point in the month, which the
        front end was reading as "right now" — a notice lifted on the 3rd went on
        saying the water may not be safe on the 25th. health_now is the live
        count. It is inclusive of the interval end because an ongoing notice
        accrues to exactly `now`, and a half-open test calls those lifted."""
        base = dict(work_category="consumption_notice_issued", status="Open",
                    notice_to_end_seconds=None, end_source="not_found",
                    end_local_date=None, reference_num="COR1")
        standing = _case(**base, start_date="2026-05-05T00:00:00+00:00")
        month = build_site([standing], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert (month["health_n"], month["health_now"]) == (1, 1)

        # same notice, lifted on the 3rd: still a fact about May, not about now
        lifted = _case(**base, start_date="2026-05-01T00:00:00+00:00")
        lift = _case(id=99, work_category="consumption_notice_lifted", status="Closed",
                     notice_to_end_seconds=None, end_source="not_found",
                     end_local_date=None, reference_num="COR2",
                     start_date="2026-05-03T00:00:00+00:00")
        month = build_site([lifted, lift], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert (month["health_n"], month["health_now"]) == (1, 0)

    def test_an_unpaired_consumption_notice_is_not_excluded_as_stale(self):
        """The deliberate half-measure. Boil notices older than CAP_DAYS with no
        lift are dropped, because case 221165 sat 'Open' while its own text said
        it had been lifted — status contradicted by evidence. No do-not-consume
        notice on file does that: Whiddy Island (Open since 2022) names a real,
        unlifted water-quality failure. So these keep accruing to the cap and
        keep their marker, rather than vanishing on an assumption."""
        stale = _case(
            work_category="consumption_notice_issued",
            do_not_drink=1,
            status="Open",
            notice_to_end_seconds=None,
            end_source="not_found",
            end_local_date=None,
            start_date="2026-05-01T00:00:00+00:00",
            reference_num="COR1",
        )
        month = build_site([stale], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["quality"] == 1
        assert month["health_n"] == 1
        # still accruing, which is the half of the boil policy that was not
        # taken: excluded-as-stale would read health_now == 0
        assert month["health_now"] == 1

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


class TestSpanTable:
    """What a case with no usable end signal gets charged, and on what evidence."""

    def test_only_observed_completions_are_evidence(self):
        """A scheduled end is a published plan. It accrues its own announced
        interval, but it cannot say what a *different* notice's works took —
        that is the same line the headline median already draws."""
        rows = [_case(end_source="scheduled_end_with_time", notice_to_end_seconds=99 * 3600)]
        assert SpanTable(rows).overall is None

    def test_a_category_with_enough_cases_uses_its_own_median(self):
        rows = [_case(id=i, work_category="mains_repair", notice_to_end_seconds=6 * 3600)
                for i in range(MIN_CATEGORY_N)]
        rows += [_case(id=100 + i, notice_to_end_seconds=30 * 3600) for i in range(4)]
        table = SpanTable(rows)
        assert table.for_category("mains_repair") == 6 * 3600
        # burst_main is under the threshold, so it falls back to the global median
        assert table.for_category("burst_main") == table.overall

    def test_a_thin_category_falls_back_rather_than_setting_its_own_number(self):
        rows = [_case(id=i, work_category="mains_repair", notice_to_end_seconds=6 * 3600)
                for i in range(MIN_CATEGORY_N - 1)]
        rows += [_case(id=100 + i, notice_to_end_seconds=30 * 3600) for i in range(20)]
        assert SpanTable(rows).for_category("mains_repair") == 30 * 3600

    def test_the_cap_applies_to_the_evidence_too(self):
        """A 40-day observed span is already capped everywhere it accrues; it
        must not enter the table uncapped and charge a longer estimate than the
        case it was measured from could ever have contributed."""
        rows = [_case(notice_to_end_seconds=40 * 24 * 3600)]
        assert SpanTable(rows).overall == CAP_DAYS * 86400

    def test_without_a_table_resolve_case_keeps_the_token_footprint(self):
        """The single-row callers throughout this suite ask about severity and
        recurrence, not accrual, and must not be made to stand up a corpus."""
        row = _case(status="Closed", notice_to_end_seconds=None,
                    end_source="not_found", end_local_date=None)
        case = resolve_case(row, SA_INDEX, {}, NOW)
        assert case.imputed is False
        assert case.intervals[0][1] - case.intervals[0][0] == timedelta(seconds=1)


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
        assert area["name"] == UNPLACED_LABEL
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
        assert "availability" not in area_month  # a clear month's 100.0 is implied

    def test_a_month_that_lost_time_carries_its_availability(self):
        month = build_site([_case()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert month["towns"]["T1"]["months"]["2026-05"]["availability"] < 100

    def test_an_open_entry_names_its_area(self):
        county = build_site([_case(status="Open")], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert set(county["open"][0]) == {"sev", "title", "loc", "since", "area", "name", "ref"}
        assert (county["open"][0]["area"], county["open"][0]["name"]) == ("T1", "Testtown")

    def test_a_month_with_nothing_resolved_omits_the_count(self):
        month = build_site([_case()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert "resolved_n" not in month["towns"]["T1"]["months"]["2026-05"]


class TestVanished:
    """An Open case the feed no longer serves is not open: nothing will ever
    close it otherwise, and the open list would carry it for good."""

    def _row(self, **overrides):
        base = dict(status="Open", notice_to_end_seconds=None, end_source="not_found",
                    end_local_date=None, vanished_at="2026-05-05T12:00:00+00:00")
        return _case(**(base | overrides))

    def test_it_is_neither_open_nor_resolved(self):
        county = build_site([self._row()], SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]
        assert county["open"] == [] and county["open_total"] == 0
        assert county["resolved"] == {}

    def test_it_stops_accruing_to_now(self):
        # no end signal and no lift: the closed-no-signal branch, not the accrual
        live = resolve_case(self._row(vanished_at=None), SA_INDEX, {}, NOW)
        gone = resolve_case(self._row(), SA_INDEX, {}, NOW)
        assert live.intervals[0][1] == NOW
        assert gone.intervals[0][1] == live.start + timedelta(seconds=1)
        assert not gone.is_open

    def test_a_vanished_boil_notice_is_closed_with_no_signal(self):
        row = self._row(work_category="boil_notice_issued", title="Boil Water Notice - Carlow")
        assert boil_notice_fate(row, {}, NOW)[0] == "closed_no_signal"


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


class TestClearDays:
    """"N/M clear days" is the one figure on the site that could overstate.

    Counting every day of the month whose severity is empty counts days that
    have not happened yet as clear — on 6 August a county with four bad days out
    of six read "27/31 clear days", which is both wrong and flattering.
    """

    def _month(self, now, ym="2026-05"):
        return build_site([_case()], SA_INDEX, now, TOWNS)["counties"]["Carlow"]["months"][ym]

    def test_the_in_progress_month_counts_only_days_that_have_happened(self):
        m = self._month(NOW)          # 10 May 2026
        assert m["days_elapsed"] == 10
        assert len(m["days"]) == 31   # the bar still draws the whole month
        # the one case runs on 1 May, so nine of the ten elapsed days are clear
        assert m["clear_days"] == 9

    def test_a_finished_month_counts_every_day(self):
        m = self._month(AFTER_MAY)
        assert m["days_elapsed"] == 31
        assert m["clear_days"] == 30

    def test_days_before_collection_began_are_not_counted_as_clear(self):
        # April 2026 is a part-month: collection started on the 20th, so the
        # first 19 days are "nd" and belong to neither figure
        m = self._month(AFTER_MAY, "2026-04")
        assert m["days_elapsed"] == 11
        assert m["clear_days"] == 11

    def test_clear_days_never_exceeds_days_elapsed(self):
        for now in (NOW, AFTER_MAY):
            for ym, month in build_site(
                [_case()], SA_INDEX, now, TOWNS
            )["counties"]["Carlow"]["months"].items():
                assert month["clear_days"] <= month["days_elapsed"], ym


class TestQualityDaysDoNotColourTheBars:
    """Quality notices left the day bars in the 2026-08-26 design alignment:
    the healthmark and the county pages carry drinking-water notices, and the
    bar shows availability alone."""

    def test_a_quality_only_day_renders_clear(self):
        m = build_site(
            [_case(work_category="boil_notice_issued")], SA_INDEX, NOW, TOWNS
        )["counties"]["Carlow"]["months"]["2026-05"]
        assert m["days"][0] == ["", 0.0]
        assert m["clear_days"] == 10          # the notice day included
        assert m["events"]["quality"] == 1    # still counted, just not painted

    def test_a_quality_and_restriction_day_shows_the_restriction(self):
        # worst-severity short-circuits, so this only works with quality skipped
        # server-side; a client-side remap of ["quality", pct] could not recover
        # the restriction underneath
        rows = [
            _case(id=1, work_category="boil_notice_issued"),
            _case(id=2, reference_num="CAR00000002", work_category=None,
                  work_type=None, reduced_pressure=1),
        ]
        m = build_site(rows, SA_INDEX, NOW, TOWNS)["counties"]["Carlow"]["months"]["2026-05"]
        assert m["days"][0][0] == "degraded"


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
    """What a recurring window contributes.

    Since a scheduled repeating window is classed as a restriction (see
    `classify`), none of these accrue person-hours — the assertions are on the
    intervals themselves and on what the county still shows, which is what the
    expansion is now for.
    """

    def _hours(self, row):
        case = resolve_case(row, SA_INDEX, {}, NOW, None)
        return sum((e - s).total_seconds() for s, e in case.intervals) / 3600

    def test_a_nightly_series_covers_its_windows_not_the_elapsed_span(self):
        assert self._hours(_recurring()) == 63.0  # 7 nights x 9h, not the 165h span

    def test_a_recurring_event_accrues_no_person_hours(self):
        """A scheduled repeating window is demand management, whatever the title
        says — the rule that stopped one Donegal nightly regime being the largest
        figure on the site while the same villages' April notice counted zero."""
        month = build_site([_recurring()], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 0
        assert month["events"]["outage"] == 0
        assert month["events"]["degraded"] == 1

    def test_every_night_of_a_series_still_colours_its_day_bar(self):
        """Reclassifying must change the price, not the visibility — a reader
        looking at the county still sees something on every day it ran."""
        days = build_site([_recurring()], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert [d[0] for d in days["days"][:8]] == ["degraded"] * 8

    def test_pins_with_different_series_ends_union_to_the_longest(self):
        rows = [
            _recurring(id=1),
            _recurring(id=2, end_local_date="2026-05-06", notice_to_end_seconds=117 * 3600.0),
        ]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["degraded"] == 1

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

    def test_a_recurring_event_stays_out_of_the_completion_median(self):
        """The median is over supply disruptions, and a restriction is not one.
        Excluding them also keeps the headline comparing like with like: "how long
        did the works take" means something different for a nightly regime."""
        month = build_site(
            [_recurring(end_source="completion_update", end_local_time="12:02")],
            SA_INDEX, NOW,
        )["counties"]["Carlow"]["months"]["2026-05"]
        assert month["median_completion_h"] is None
        assert month["completed_n"] == 0

    def test_an_event_is_credited_to_the_month_it_was_published(self):
        """The median loop keys on publication, not on the first interval's start.
        Those coincide for every event that currently reaches it — only a
        recurring series can open in a later month, and those are restrictions
        now — so this is a guard rather than a live correction."""
        rows = [_case(start_date="2026-05-31T09:00:00+00:00",
                      end_local_date="2026-06-02", notice_to_end_seconds=48 * 3600.0)]
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

    def test_the_whole_event_is_one_restriction_once_the_last_pin_inherits(self):
        """Inheritance is what keeps the event coherent: without it the completion
        pin stays an outage inside a restriction event, and the per-reference
        union charges its continuous interval in full."""
        rows = [_recurring(id=1), self._completion_pin()]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["person_h"] == 0
        assert month["events"] == {"outage": 0, "quality": 0, "degraded": 1, "maintenance": 0}

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


class TestEventNaming:
    """One event, one area name, decided over its whole footprint.

    The open list and the national top ten used to name an event by different
    rules — first pin published versus largest share of the footprint — so a
    six-pin burst could read "Allenwood" in one place and "Prosperous" in the
    other, of the same event on the same page.
    """

    # two pins 7 km apart. Each has a home area of its own, and both reach into a
    # third that is bigger in total than either — the shape that decides whether
    # naming is done per pin or over the event.
    SA = SmallAreaIndex([
        (52.836, -6.926, "SA1", 100),   # pin A's home
        (52.8362, -6.926, "SA2", 60),   # shared
        (52.900, -6.926, "SA3", 90),    # pin B's home
        (52.9002, -6.926, "SA4", 60),   # shared, same area as SA2
    ])
    TOWNS = TownLookup([
        ("SA1", "X", "Exton", "Carlow"),
        ("SA2", "Y", "Wyeville", "Carlow"),
        ("SA3", "Z", "Zedbury", "Carlow"),
        ("SA4", "Y", "Wyeville", "Carlow"),
    ], SA.pop)

    def _pins(self, **overrides):
        # id 1 is published first and homes to Zedbury (90); id 2 homes to Exton
        # (100). So first-pin-wins and largest-share disagree, which is the point.
        return [_case(id=1, full_lat=52.900, **overrides),
                _case(id=2, full_lat=52.836, **overrides)]

    def test_an_event_is_named_over_its_whole_footprint_not_its_first_pin(self):
        site = build_site(self._pins(), self.SA, datetime(2026, 6, 15, tzinfo=UTC), self.TOWNS)
        # the first pin published would have said Zedbury; Exton holds more of
        # the event's footprint, and that is what a reader is shown
        assert [r["area"] for r in site["top"]["2026-05"]] == ["Exton"]

    def test_the_open_list_and_the_top_ten_agree_on_the_area(self):
        """The whole point of the change: both read the same decision."""
        now = datetime(2026, 6, 15, tzinfo=UTC)
        rows = self._pins(status="Open", notice_to_end_seconds=None,
                          end_source="not_found", end_local_date=None)
        site = build_site(rows, self.SA, now, self.TOWNS)
        county = site["counties"]["Carlow"]
        open_area = {c["area"] for c in county["open"]}
        top_area = {r["area"] for r in site["top"]["2026-05"]}
        assert len(open_area) == 1
        assert {self.TOWNS.label(code) for code in open_area} == top_area

    def test_the_name_is_restricted_to_areas_the_pins_were_homed_to(self):
        """Shares are summed per area, so Wyeville — reached by both pins but the
        home of neither — out-totals Exton and Zedbury across the union. Naming
        the event Wyeville would produce a code absent from the county breakdown,
        which the page renders as a blank heading and drops from the area table's
        open counts."""
        assert self.TOWNS.dominant(
            {"SA1": 100, "SA2": 60, "SA3": 90, "SA4": 60}, "Carlow"
        ) == "Y"
        assert self.TOWNS.dominant(
            {"SA1": 100, "SA2": 60, "SA3": 90, "SA4": 60}, "Carlow", {"X", "Z"}
        ) == "X"

    def test_an_event_is_never_named_after_an_area_no_pin_was_homed_to(self):
        """The invariant the restriction buys, stated exactly.

        It is *not* "every open case resolves in the county breakdown" — four
        real cases already fail that for an unrelated reason, being advance
        notices dated far enough ahead that their footprint lands in no listed
        month, so their area gets no breakdown entry. What this guarantees is
        narrower: naming cannot invent an area that no pin of the event chose.
        """
        now = datetime(2026, 6, 15, tzinfo=UTC)
        rows = self._pins(status="Open", notice_to_end_seconds=None,
                          end_source="not_found", end_local_date=None)
        county = build_site(rows, self.SA, now, self.TOWNS)["counties"]["Carlow"]
        homes = {self.TOWNS.dominant(self.SA.affected(r["full_lat"], r["full_lon"]), "Carlow")
                 for r in rows}
        for case in county["open"]:
            assert case["area"] in homes
            assert case["area"] in county["towns"]


class TestDescribesRecurrence:
    """Detection, which is the easy half — the window *values* are what needed a
    language model. Keying severity off this is why classification no longer
    waits on a corpus re-run to be right."""

    def test_matches_the_wordings_the_feed_uses(self):
        for text in ("works nightly from 10pm", "daily from 9pm until 9am",
                     "each night from 11pm", "overnight from 10pm until 7am"):
            assert describes_recurrence(text), text

    def test_does_not_match_a_single_continuous_period(self):
        assert not describes_recurrence("Works will take place from 9am on 3 June until 5pm.")

    def test_sees_through_markup(self):
        assert describes_recurrence("<p>Works take place<br>nightly from 10pm</p>")

    def test_an_absent_description_is_not_recurring(self):
        assert not describes_recurrence(None)

    def test_the_two_signals_are_combined_not_substituted(self):
        """They fail in opposite directions: the extraction misses a window when
        the notice also carries a completion update, and the text misses the
        enumerated form that names its days instead of saying "daily"."""
        text_only = _case(id=1, reference_num="CAR1",
                          description="Works take place nightly from 10pm until 7am.")
        model_only = _case(id=2, reference_num="CAR2", end_recurrence="daily",
                           description="from 10am until 6pm on 5 and 6 May",
                           end_window_open="10:00", end_window_close="18:00",
                           end_window_first_date="2026-05-05")
        rows = [text_only, model_only]
        keys = recurring_events(rows, event_windows(rows))
        assert ("Carlow", "CAR1") in keys
        assert ("Carlow", "CAR2") in keys

    def test_a_recurring_text_downgrades_even_with_no_extracted_window(self):
        """The eight events a human review found charged as continuous outages:
        every one is a completion notice whose window the model suppressed."""
        row = _case(description="Works are scheduled nightly from 11pm until 7am, 5 to 15 June.")
        assert resolve_case(row, SA_INDEX, {}, NOW).sev == "degraded"


class TestHealthNotices:
    """Boil-water, do-not-drink and do-not-consume notices are published beside
    the grade rather than folded into it. Whether the water is safe to drink is a
    different question from how much of it there was, and one letter cannot
    answer both — a notice reaching 200 people used to make a county read
    identically to one that lost supply county-wide."""

    def _notice(self, **overrides):
        return _case(work_category="boil_notice_issued", boil_water_notice=1, status="Open",
                     notice_to_end_seconds=None, end_source="not_found", end_local_date=None,
                     **overrides)

    def test_a_health_notice_is_counted_without_touching_the_grade(self):
        site = build_site([self._notice()], SA_INDEX, NOW)
        month = site["counties"]["Carlow"]["months"]["2026-05"]
        assert month["health_n"] == 1
        assert month["grade"] == "A"  # no outage, so availability is untouched
        assert month["events"]["quality"] == 1

    def test_a_county_with_no_health_notice_reports_zero(self):
        month = build_site([_case()], SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["health_n"] == 0

    def test_discolouration_is_a_quality_event_but_not_a_health_notice(self):
        """It shows as a quality event and always did; it never knocked, and it
        does not raise the marker either."""
        rows = [_case(work_category="discolouration", boil_water_notice=0)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["quality"] == 1
        assert month["health_n"] == 0

    def test_a_feed_flag_alone_no_longer_raises_the_marker(self):
        """The inverse of what this pinned before. A burst main carrying the
        feed's do_not_drink flag but no drinking-water language in its text is a
        burst main: it accrues as an outage and raises no marker. Nine such cases
        were painting a warning across eight county-months (2026-08-18)."""
        rows = [_case(work_category="burst_main", do_not_drink=1)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["health_n"] == 0
        assert month["events"]["outage"] == 1

    def test_a_consumption_notice_still_raises_the_marker(self):
        """Dropping the flags must not cost a real notice its marker: every
        legitimate flagged case on file is already one of these categories."""
        rows = [_case(work_category="consumption_notice_issued", do_not_drink=0)]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["health_n"] == 1

    def test_an_outage_still_grades_on_availability_with_a_notice_present(self):
        """The two are independent: the letter moves on person-hours, the marker
        on whether a health notice is active."""
        rows = [_case(id=1, reference_num="CAR1", notice_to_end_seconds=300 * 3600.0,
                      end_local_date="2026-05-13"),
                self._notice(id=2, reference_num="CAR2")]
        month = build_site(rows, SA_INDEX, NOW)["counties"]["Carlow"]["months"]["2026-05"]
        assert month["grade"] == "F"       # driven by the outage alone
        assert month["health_n"] == 1


def _history(rows, now=NOW, towns=TOWNS, sa=SA_INDEX, county="Carlow", code="T1"):
    """The events one area's history renders, for the common single-area case."""
    site = build_site(rows, sa, now, towns)
    return site["history"][county][code]["events"]


class TestAreaHistory:
    """Every notice ever published in one area.

    Not in data.js: all of it together is twice the payload, so it is written to
    per-county shards the page loads on demand. What is tested here is the
    regrouping and, mostly, the two places where saying nothing is the only
    honest answer.
    """

    def test_one_event_becomes_one_record(self):
        events = _history([_case()])
        assert len(events) == 1
        assert events[0] == {
            "ref": "CAR00000001", "title": "Burst Water Main - Carlow", "sev": "outage",
            "start": "2026-05-01", "pins": 1, "hours": 24.0, "people": 1000,
            "confirmed": 1, "loc": "Somewhere",
        }

    def test_the_last_charged_day_is_carried_when_it_differs_from_the_first(self):
        """The county bar finds a day's events by [start, end]; a one-day event
        omits the end, the sparse rule the rest of the record follows."""
        assert "end" not in _history([_case()])[0]  # 1 May 00:00 to 2 May 00:00
        three_days = _history([_case(notice_to_end_seconds=3 * 86400.0)])[0]
        assert three_days["end"] == "2026-05-03"  # ends 4 May 00:00, so the 3rd
        recurring = _history([_recurring()], now=AFTER_MAY)[0]
        assert recurring["end"] == "2026-05-08"
        open_case = _history([_case(status="Open", notice_to_end_seconds=None,
                                    end_source="not_found", end_local_date=None)])[0]
        assert open_case["end"] == "2026-05-09"  # accrues to NOW, midnight on the 10th

    def test_a_multi_pin_event_is_one_record_counting_its_pins(self):
        """The same rule the top ten uses: "was this confirmed complete?" is a
        count across the event's notices, never a boolean."""
        rows = [_case(id=1)] + [
            _case(id=i, end_source="scheduled_end_with_time") for i in (2, 3, 4)
        ]
        events = _history(rows)
        assert len(events) == 1
        assert (events[0]["pins"], events[0]["confirmed"], events[0]["scheduled"]) == (4, 1, 3)

    def test_a_closed_event_that_never_reported_an_end_has_no_duration(self):
        """It carries resolve_case's token one-second footprint, so publishing a
        duration would print 0.0h — a measurement that was never made. 801 events
        in the live corpus are this shape."""
        rows = [_case(status="Closed", notice_to_end_seconds=None,
                      end_source="not_found", end_local_date=None)]
        event = _history(rows)[0]
        assert "hours" not in event
        assert "span_h" not in event
        assert "confirmed" not in event and "scheduled" not in event
        assert "open" not in event

    def test_an_open_event_with_no_signal_reports_the_time_so_far(self):
        """Unlike the closed case above, this one is still running and is being
        charged for it — so the hours are real, and the page says "at least"."""
        rows = [_case(status="Open", notice_to_end_seconds=None,
                      end_source="not_found", end_local_date=None)]
        event = _history(rows)[0]
        assert event["open"] == 1
        assert event["hours"] == 9 * 24.0  # May 1 -> NOW, under the 14-day cap
        assert "closed" not in event

    def test_a_recurring_window_reports_covered_hours_and_its_span(self):
        """63h of works across seven nights. Publishing only the span would
        restate the bug the recurrence work exists to fix.

        The span is the window series' own — first opening to last close, 1 May
        22:00 local to 8 May 07:00 — not the 165h notice-to-end, which starts at
        publication 13 hours before the first window opened. "The repeating
        window spanned this long" is a claim about the windows.
        """
        event = _history([_recurring()], now=AFTER_MAY)[0]
        assert event["hours"] == 63.0
        assert event["span_h"] == 153.0

    def test_a_single_interval_event_omits_the_span(self):
        assert "span_h" not in _history([_case()])[0]

    def test_the_worst_severity_across_an_events_pins_wins(self):
        """An event is a reference_num, not a severity slice: a burst published
        alongside its own investigation notice is a burst."""
        rows = [_case(id=1), _case(id=2, work_category="investigation")]
        event = _history(rows)[0]
        assert event["sev"] == "outage"
        assert event["pins"] == 2

    def test_a_works_event_is_kept_not_only_disruptions(self):
        """The county metrics rank supply disruptions; a history that showed only
        those would answer a narrower question than the one the reader asked."""
        event = _history([_case(work_category="investigation")])[0]
        assert event["sev"] == "maintenance"

    def test_a_boil_notice_closed_by_its_paired_lift_reads_confirmed(self):
        issue = _case(
            work_category="boil_notice_issued", boil_water_notice=1, status="Open",
            notice_to_end_seconds=None, location="Ardfinnan Public Water Supply",
            reference_num="TIP1",
        )
        lift = _case(
            id=99, work_category="boil_notice_lifted", status="Closed",
            notice_to_end_seconds=None, location="Ardfinnan Regional Water Supply Scheme",
            reference_num="TIP2", start_date="2026-05-03T00:00:00+00:00",
        )
        # the lift is good news and is never an event of its own (IGNORE_CATS)
        events = _history([issue, lift])
        assert [e["ref"] for e in events] == ["TIP1"]
        assert events[0]["confirmed"] == 1
        assert events[0]["health"] == 1
        assert events[0]["hours"] == 48.0  # 1 May -> the lift on the 3rd

    def test_a_closed_event_carries_the_date_it_was_seen_to_close(self):
        rows = [_case(status="Closed", closed_at="2026-05-06T04:00:00+00:00")]
        assert _history(rows)[0]["closed"] == "2026-05-06"

    def test_the_newest_event_is_first(self):
        rows = [_case(id=1, reference_num="CAR1"),
                _case(id=2, reference_num="CAR2", start_date="2026-05-04T00:00:00+00:00")]
        assert [e["ref"] for e in _history(rows)] == ["CAR2", "CAR1"]

    def test_the_start_is_the_earliest_publication_across_the_pins(self):
        """Rows arrive in id order, not start_date order."""
        rows = [_case(id=1, start_date="2026-05-04T00:00:00+00:00"),
                _case(id=2, start_date="2026-05-01T00:00:00+00:00")]
        assert _history(rows)[0]["start"] == "2026-05-01"

    def test_people_is_the_whole_footprint_capped_at_the_county(self):
        """The same number the national top ten prints for the same event — two
        pages disagreeing about how many people a burst reached would be worse
        than either answer."""
        sa = SmallAreaIndex([(52.836, -6.926, "SA1", COUNTY_POP["Carlow"] * 2)])
        towns = TownLookup([("SA1", "T1", "Testtown", "Carlow")], sa.pop)
        assert _history([_case()], sa=sa, towns=towns)[0]["people"] == COUNTY_POP["Carlow"]

    def test_a_pin_outside_its_county_lands_in_the_unplaced_bucket(self):
        towns = TownLookup([("SA1", "T1", "Blessington", "Wicklow")], SA_INDEX.pop)
        site = build_site([_case()], SA_INDEX, NOW, towns)
        area = site["history"]["Carlow"][UNPLACED]
        assert area["name"] == UNPLACED_LABEL
        assert len(area["events"]) == 1

    def test_one_reference_published_in_two_counties_appears_in_both(self):
        """16 reference numbers do this. Each half has its own footprint and its
        own county cap, so two records is the honest rendering, not a duplicate."""
        sa = SmallAreaIndex([(52.836, -6.926, "SA1", 1000), (53.15, -6.8, "SA2", 500)])
        towns = TownLookup(
            [("SA1", "T1", "Testtown", "Carlow"), ("SA2", "T2", "Kilcullen", "Kildare")], sa.pop
        )
        rows = [_case(id=1), _case(id=2, county="Kildare", full_lat=53.15, full_lon=-6.8)]
        site = build_site(rows, sa, NOW, towns)
        assert site["history"]["Carlow"]["T1"]["events"][0]["ref"] == "CAR00000001"
        assert site["history"]["Kildare"]["T2"]["events"][0]["ref"] == "CAR00000001"

    def test_there_is_no_history_without_a_town_lookup(self):
        assert build_site([_case()], SA_INDEX, NOW)["history"] == {}


def _bare_site(county="Kildare"):
    """The least a payload can be and still be one write_site can render.

    Fuller than it used to need to be: write_site now also renders a county page,
    which reads the month list and the generation stamp for the sitemap. Still
    hand-built rather than grown from a corpus, because the cases that drive it
    are the empty ones a real build never produces.
    """
    return {
        "generated_iso": "2026-08-06T00:00:00Z",
        "months": [],
        "counties": {
            county: {
                "pop": COUNTY_POP[county],
                "months": {},
                "open": [],
                "open_total": 0,
                "towns": {},
                "resolved": {},
            }
        },
        "history": {},
    }


class TestHistoryShards:
    """The history is 26 files the page loads one at a time, and write_site owns
    the split — so a field added to the history cannot leak into data.js by
    somebody forgetting to pop it."""

    def _write(self, tmp_path, rows=None):
        site = build_site(rows or [_case()], SA_INDEX, NOW, TOWNS)
        site.pop("recurrence_report")
        return site, write_site(site, tmp_path, TOWNS)

    def test_a_county_slug_is_a_usable_and_unique_filename(self):
        """Every county is one ASCII word today. A future one spelled with a
        space or a fada would silently collide or produce a name the loader
        cannot request, so the assumption is checked rather than trusted."""
        slugs = [county_slug(c) for c in COUNTY_POP]
        assert all(s.isascii() and s.isalpha() and s.islower() for s in slugs)
        assert len(set(slugs)) == len(COUNTY_POP)

    def test_the_files_written_are_data_index_and_one_shard_per_county(self, tmp_path):
        site, sizes = self._write(tmp_path)
        data_bytes, shard_bytes, n_areas = sizes["data.js"], sizes["shards"], sizes["n_areas"]
        assert (tmp_path / "data.js").exists() and (tmp_path / "index.html").exists()
        shards = sorted(p.name for p in (tmp_path / "h").iterdir())
        assert shards == sorted(f"{county_slug(c)}.js" for c in site["counties"])
        assert (data_bytes, n_areas) == (len((tmp_path / "data.js").read_bytes()), 1)
        assert shard_bytes > 0

    def test_a_shard_round_trips_through_json(self, tmp_path):
        self._write(tmp_path)
        body = (tmp_path / "h" / "carlow.js").read_text()
        assert body.startswith("window.UISCE_HISTORY = window.UISCE_HISTORY || {};")
        payload = body.split(" = ", 2)[2].rstrip(";")
        assert json.loads(payload)["T1"]["name"] == "Testtown"

    def test_a_county_with_no_history_still_gets_a_well_formed_shard(self, tmp_path):
        """So the loader never has to tell a 404 apart from a county with nothing
        to show. Every county in a real build has both, so this drives write_site
        directly rather than waiting for a corpus that cannot arise."""
        write_site(_bare_site(), tmp_path, TOWNS)
        body = (tmp_path / "h" / "kildare.js").read_text()
        assert json.loads(body.split(" = ", 2)[2].rstrip(";")) == {}

    def test_the_history_never_reaches_data_js(self, tmp_path):
        """The hard constraint of the whole feature, made mechanical."""
        site, _ = self._write(tmp_path)
        data = (tmp_path / "data.js").read_text()
        assert "history" not in site
        assert "UISCE_HISTORY" not in data
        assert "CAR00000001" not in data

    def test_the_county_breakdown_never_reaches_data_js_either(self, tmp_path):
        """The 2026-09-05 split: towns and resolved are the county view's alone
        and were 78% of the payload the overview loaded."""
        site, _ = self._write(tmp_path)
        data = (tmp_path / "data.js").read_text()
        assert set(site["counties"]["Carlow"]) == {"pop", "months", "open", "open_total"}
        assert "Testtown" not in data and "towns" not in data and "resolved" not in data
        shard = (tmp_path / "t" / "carlow.js").read_text()
        assert shard.startswith("window.UISCE_COUNTY = window.UISCE_COUNTY || {};")
        county = json.loads(shard.split("=", 2)[2].rstrip(";"))
        assert set(county) == {"towns", "resolved"}
        assert county["towns"]["T1"]["name"] == "Testtown"

    def test_every_county_gets_a_breakdown_shard_including_the_empty_ones(self, tmp_path):
        write_site(_bare_site(), tmp_path, TOWNS)
        shard = (tmp_path / "t" / "kildare.js").read_text()
        assert json.loads(shard.split("=", 2)[2].rstrip(";")) == {"towns": {}, "resolved": {}}

    def test_the_history_entry_carries_what_the_area_view_needs(self, tmp_path):
        site, _ = self._write(tmp_path)
        shard = (tmp_path / "h" / "carlow.js").read_text()
        area = json.loads(shard.split("=", 2)[2].rstrip(";"))["T1"]
        assert (area["name"], area["pop"], area["slug"]) == ("Testtown", 1000, "testtown")

    def test_search_js_maps_each_county_to_its_sorted_names(self, tmp_path):
        """The search index bindSearch fetches on the first keystroke: county ->
        sorted settlement names, counties restricted to the payload's so a pick
        always routes. An area with a page carries its slug, so the hit can be a
        link straight to it."""
        site, _ = self._write(tmp_path)
        body = (tmp_path / "search.js").read_text()
        assert body.startswith("window.UISCE_PLACES = ")
        index = json.loads(body.split(" = ", 1)[1].rstrip(";"))
        assert index == {"Carlow": [["Testtown", "testtown"]]}
        assert set(index) <= set(site["counties"])

    def test_an_area_with_no_page_stays_a_bare_name(self, tmp_path):
        """The slug is the flag as well as the value. An Electoral Division never
        gets a page, and neither does a settlement that has never had a notice —
        both would 404, so both stay county-bound."""
        # SA2 and SA3 sit well away from the test pin, so the case still lands
        # in Testtown and the other two areas stay noticeless
        sa = SmallAreaIndex([
            (52.836, -6.926, "SA1", 1000),
            (53.500, -7.500, "SA2", 500),
            (54.500, -8.500, "SA3", 500),
        ])
        towns = TownLookup(
            [
                ("SA1", "T1", "Testtown", "Carlow"),
                ("SA2", "ed:Carlow:Around Testtown", "Around Testtown", "Carlow"),
                ("SA3", "T2", "Quietville", "Carlow"),
            ],
            sa.pop,
        )
        site = build_site([_case()], sa, NOW, towns)
        site.pop("recurrence_report")
        write_site(site, tmp_path, towns)
        body = (tmp_path / "search.js").read_text()
        index = json.loads(body.split(" = ", 1)[1].rstrip(";"))
        assert index == {
            "Carlow": ["Around Testtown", "Quietville", ["Testtown", "testtown"]]
        }
        # every slug emitted has a page on disk behind it
        for entry in index["Carlow"]:
            if not isinstance(entry, str):
                assert (tmp_path / "a" / "carlow" / f"{entry[1]}.html").exists()

    def test_a_town_named_for_its_county_is_indexed_with_its_slug(self, tmp_path):
        """Fourteen settlements share their county's name and each has a page
        of its own. The index carries the town like any other paged area; it is
        statusui's searchHits that keeps its row beside the county's, so a
        `name != county` filter here would hide the page from the box again."""
        sa = SmallAreaIndex([(52.836, -6.926, "SA1", 1000)])
        towns = TownLookup([("SA1", "T1", "Carlow", "Carlow")], sa.pop)
        site = build_site([_case()], sa, NOW, towns)
        site.pop("recurrence_report")
        write_site(site, tmp_path, towns)
        body = (tmp_path / "search.js").read_text()
        index = json.loads(body.split(" = ", 1)[1].rstrip(";"))
        assert index == {"Carlow": [["Carlow", "carlow"]]}
        assert (tmp_path / "a" / "carlow" / "carlow.html").exists()


class TestNoticeText:
    """The notice's own wording, on the county page's open rows and nowhere in
    the app payload: it is what tells a reader whether their road is in it."""

    FEED = (
        "<b>**Update 3:08pm 2/9/2026**<br><br>\n\nWorks are now complete.</b><br><br>"
        "Repairs may cause supply disruptions to Rosegreen &amp; Coolmoyne. <br><br>\n"
        "Please note the reference: TIP00119710. <br><br>LA01"
    )

    def test_paragraphs_come_out_plain_and_in_order(self):
        assert notice_paragraphs(self.FEED) == [
            "**Update 3:08pm 2/9/2026**",
            "Works are now complete.",
            "Repairs may cause supply disruptions to Rosegreen & Coolmoyne.",
            "Please note the reference: TIP00119710.",
        ]

    def test_nothing_and_markup_only_give_no_paragraphs(self):
        assert notice_paragraphs(None) == []
        assert notice_paragraphs("<br><br>LA01") == []

    def test_the_county_page_carries_it_only_for_open_notices(self, tmp_path):
        rows = [
            _case(id=1, reference_num="CAR00000001", status="Open",
                  description="Open <script>x</script> text.<br><br>Second."),
            _case(id=2, reference_num="CAR00000002", status="Closed",
                  description="Closed text nobody needs."),
        ]
        site = build_site(rows, SA_INDEX, NOW, TOWNS)
        site.pop("recurrence_report")
        write_site(site, tmp_path, TOWNS)
        assert "notice_text" not in site
        page = (tmp_path / "c" / "carlow.html").read_text()
        block = re.search(r'<section id="open">.*?</section>', page, re.S).group(0)
        assert "<summary>What the notice says</summary><p>Open x text.</p><p>Second.</p>" in block
        assert "<script" not in block
        assert "Closed text nobody needs" not in page
        data = (tmp_path / "data.js").read_text()
        assert "Second." not in data and "nobody needs" not in data

    def test_an_open_row_links_its_reference_on_water_ie(self, tmp_path):
        rows = [
            _case(id=1, reference_num="CAR00000001 ", status="Open", title="Trailing space"),
            _case(id=2, reference_num="HM1816040926", status="Open", title="Hand entered"),
            _case(id=3, reference_num=None, status="Open", title="No reference"),
            _case(id=4, reference_num="CAR00000004", status="Closed", title="Closed"),
        ]
        site = build_site(rows, SA_INDEX, NOW, TOWNS)
        site.pop("recurrence_report")
        write_site(site, tmp_path, TOWNS)
        page = (tmp_path / "c" / "carlow.html").read_text()
        block = re.search(r'<section id="open">.*?</section>', page, re.S).group(0)
        by_title = {
            re.search(r"<strong>(.*?)</strong>", r).group(1): r
            for r in re.findall(r"<li>.*?</li>", block, re.S)
        }
        link = '· <a href="https://wtr.ie/CAR00000001">CAR00000001</a>'
        assert link in by_title["Trailing space"]
        assert "wtr.ie" not in by_title["Hand entered"]
        assert "wtr.ie" not in by_title["No reference"]
        assert page.count("wtr.ie") == 1
class TestFeeds:
    """One Atom file nationally and one per county, written from a block that
    write_site pops the way it pops the history: a subscriber gets the newest
    sightings, the app payload gets none of them."""

    def _write(self, tmp_path, rows=None):
        site = build_site(rows or [_case()], SA_INDEX, NOW, TOWNS)
        site.pop("recurrence_report")
        write_site(site, tmp_path, TOWNS)
        return site

    def _entries(self, path):
        ns = {"a": "http://www.w3.org/2005/Atom"}
        return ET.parse(path).getroot().findall("a:entry", ns), ns

    def test_a_feed_is_written_nationally_and_per_county(self, tmp_path):
        site = self._write(tmp_path)
        assert "feed" not in site
        data = (tmp_path / "data.js").read_text().split("=", 1)[1].rstrip(";")
        assert "feed" not in json.loads(data)
        assert (tmp_path / "feed.xml").exists()
        assert (tmp_path / "feed" / "carlow.xml").exists()

    def test_an_entry_links_to_the_area_page_and_says_what_and_where(self, tmp_path):
        self._write(tmp_path)
        entries, ns = self._entries(tmp_path / "feed" / "carlow.xml")
        assert len(entries) == 1
        e = entries[0]
        assert e.find("a:title", ns).text == "Burst Water Main - Carlow: Testtown"
        assert e.find("a:link", ns).get("href") == f"{BASE_URL}/a/carlow/testtown.html"
        assert e.find("a:id", ns).text == f"{BASE_URL}/n/carlow/CAR00000001"
        summary = e.find("a:summary", ns).text
        assert "Supply disruption · Co. Carlow · Testtown · published 2026-05-01" in summary

    def test_the_sighting_orders_the_feed_and_publication_stands_in_for_it(self, tmp_path):
        rows = [
            _case(id=1, reference_num="CAR00000001", first_seen="2026-07-02T12:00:00+00:00"),
            _case(id=2, reference_num="CAR00000002", first_seen="2026-07-03T12:00:00+00:00",
                  start_date="2026-04-25T00:00:00+00:00"),
            _case(id=3, reference_num="CAR00000003", first_seen=None,
                  start_date="2026-05-20T00:00:00+00:00"),
        ]
        self._write(tmp_path, rows)
        entries, ns = self._entries(tmp_path / "feed.xml")
        assert [e.find("a:updated", ns).text for e in entries] == [
            "2026-07-03T12:00:00+00:00", "2026-07-02T12:00:00+00:00", "2026-05-20T00:00:00+00:00",
        ]

    def test_an_area_without_a_page_falls_back_to_the_county_page(self, tmp_path):
        self._write(tmp_path, [_case(full_lat=53.15, full_lon=-6.8)])
        entries, ns = self._entries(tmp_path / "feed.xml")
        assert entries[0].find("a:link", ns).get("href") == f"{BASE_URL}/c/carlow.html"

    def test_markup_in_a_title_cannot_break_the_document(self, tmp_path):
        self._write(tmp_path, [_case(title="Burst <b>Main</b> & more - Carlow")])
        entries, ns = self._entries(tmp_path / "feed.xml")
        assert entries[0].find("a:title", ns).text.startswith("Burst <b>Main</b> & more")

    def test_the_pages_point_at_their_feed(self, tmp_path):
        self._write(tmp_path)
        county = (tmp_path / "c" / "carlow.html").read_text()
        assert 'type="application/atom+xml"' in county and 'href="../feed/carlow.xml"' in county
        area = (tmp_path / "a" / "carlow" / "testtown.html").read_text()
        assert 'href="../../feed/carlow.xml"' in area
        assert 'href="feed.xml"' in (tmp_path / "index.html").read_text()


class TestIndexablePages:
    """The site's crawlable surface.

    Before the c/ pages it was two URLs: everything else lived behind a hash
    route, which a search engine does not index. These assert the pages exist,
    carry their county's own content, and are reachable — a page that renders
    empty or duplicates its neighbour is worse than not publishing it, because
    26 near-identical pages is what a search engine demotes as doorway pages.
    """

    def _write(self, tmp_path, rows=None):
        site = build_site(rows or [_case()], SA_INDEX, NOW, TOWNS)
        site.pop("recurrence_report")
        counties = sorted(site["counties"])
        return counties, write_site(site, tmp_path, TOWNS)

    def test_every_county_gets_a_page_including_the_empty_ones(self, tmp_path):
        counties, sizes = self._write(tmp_path)
        n_pages, county_bytes = sizes["n_county_pages"], sizes["county_pages"]
        written = sorted(p.name for p in (tmp_path / "c").iterdir())
        assert written == sorted(f"{county_slug(c)}.html" for c in counties)
        assert (n_pages, len(written)) == (len(counties), len(counties))
        assert county_bytes > 0

    def test_the_overview_points_a_reader_without_javascript_at_the_county_pages(self, tmp_path):
        counties, _ = self._write(tmp_path)
        page = (tmp_path / "index.html").read_text()
        fallback = re.search(r"<noscript>(.*?)</noscript>", page, re.S).group(1)
        for c in counties:
            assert f'<a href="c/{county_slug(c)}.html">{c}</a>' in fallback
        assert 'href="areas.html"' in fallback
        assert "<!--COUNTY-LINKS-->" not in page

    def test_a_county_page_carries_its_own_areas_and_not_another_county_s(self, tmp_path):
        """The doorway-page failure, made mechanical. The Kildare pin sits on
        the same Small Area as the Carlow one, so only `dominant`'s own-county
        rule keeps Testtown off the Kildare page — which is the case worth
        pinning, since a bug there would put one area on two counties' pages."""
        self._write(
            tmp_path,
            [_case(), _case(id=2, county="Kildare", reference_num="KIL00000001",
                            title="Burst Water Main - Kildare")],
        )
        carlow = (tmp_path / "c" / "carlow.html").read_text()
        kildare = (tmp_path / "c" / "kildare.html").read_text()
        assert "Testtown" in carlow
        assert "Testtown" not in kildare
        assert "<h1>Co. Carlow" in carlow and "<h1>Co. Kildare" in kildare
        assert "Burst Water Main - Kildare" in kildare
        assert "Burst Water Main - Kildare" not in carlow

    def test_a_county_page_needs_no_javascript_to_say_anything(self, tmp_path):
        """The whole point of the page. It must not pull the 680 KB payload, and
        it must carry real text rather than a shell for a script to fill."""
        self._write(tmp_path)
        page = (tmp_path / "c" / "carlow.html").read_text()
        assert "data.js" not in page and "UISCE_DATA" not in page
        body = re.sub(r"<(script|style).*?</\1>", "", page, flags=re.S)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        assert len(text) > 600, text

    def test_every_page_a_reader_can_land_on_reports_to_analytics(self, tmp_path):
        """A published page that reports nothing cannot tell you whether
        publishing it worked. The hash routes never could report: pushState of a
        fragment leaves the path at /uisce/, so there was no new page for the
        beacon to count — see the note on go() in site.html. Every real URL the
        site serves carries it, which is now the whole indexable surface."""
        counties, _ = self._write(tmp_path)
        beacon = "static.cloudflareinsights.com/beacon.min.js"
        pages = ["index.html", "areas.html"] + [
            f"c/{county_slug(c)}.html" for c in counties
        ]
        assert [p for p in pages if beacon not in (tmp_path / p).read_text()] == []

    def test_a_month_that_lost_person_time_never_prints_a_clean_hundred(self, tmp_path):
        """The app's availText clamps this and the static page has to match: a
        county that lost person-time must not round up to "100.000%", which reads
        as a claim the page is not making. A one-hour, 1,000-person burst against
        Dublin's population rounds there at three decimals."""
        self._write(tmp_path, [_case(
            county="Dublin", reference_num="DUB00000001",
            notice_to_end_seconds=3600.0, end_local_time="01:00",
        )])
        page = (tmp_path / "c" / "dublin.html").read_text()
        assert "99.999% supply availability" in page
        assert "100.000% supply availability" not in page

    def test_an_empty_county_page_still_renders_and_says_so(self, tmp_path):
        """A county with no notice is a page a search result can still land on,
        so it has to be a document rather than a stack trace."""
        write_site(_bare_site(), tmp_path, TOWNS)
        page = (tmp_path / "c" / "kildare.html").read_text()
        assert "Co. Kildare" in page
        assert "0 Uisce Éireann notices across 0 areas" in page

    def test_the_area_rows_differ_only_by_the_link_prefix(self, tmp_path):
        """The directory and the county page render the same area from the same
        builder, so the two can't drift into disagreeing about a notice count.

        Matched on the whole href rather than on `index.html`, because a row now
        points at a page or at the hash route depending on the area."""
        site = build_site([_case()], SA_INDEX, NOW, TOWNS)
        county, areas = area_index(site["history"], TOWNS)[0]
        assert _area_items(county, areas, "../") == _area_items(county, areas).replace(
            'href="', 'href="../'
        )

    def test_the_directory_links_to_every_county_page(self, tmp_path):
        """A sitemap is a weak discovery signal; an internal link is the strong
        one, and this is the page that already names every county."""
        counties, _ = self._write(tmp_path)
        areas_page = (tmp_path / "areas.html").read_text()
        for county in counties:
            assert f'href="c/{county_slug(county)}.html"' in areas_page

    def test_the_county_name_the_search_matches_on_stays_bare(self, tmp_path):
        """The directory's search treats a county-name hit as selecting the whole
        section, and it reads this attribute. It used to read the <h2>, which now
        also carries the area count and the county-page link — so a search for
        "page" would have selected all 26 counties."""
        counties, _ = self._write(tmp_path)
        areas_page = (tmp_path / "areas.html").read_text()
        for county in counties:
            assert f'data-county="{county}"' in areas_page
        assert "sec.dataset.county" in areas_page

    def test_the_description_states_the_county_s_record_not_the_page_s_listing(
        self, tmp_path
    ):
        """A snippet is read alone, in a search result, with the page not yet
        open - so it has to survive being read as a promise. It is cut by width,
        and what survives is the front: the clause naming what the page holds may
        be lost, and the sentence before it must not become false when it is."""
        self._write(tmp_path)
        page = (tmp_path / "c" / "carlow.html").read_text()
        desc = re.search(r'name="description" content="([^"]*)"', page).group(1)
        assert desc.startswith("Co. Carlow: ")
        assert "Month-by-month totals and every notice published" in desc
        head = desc.split(". ")[0]
        assert "most recent" not in head
        assert len(desc) <= 160, len(desc)

    def test_the_description_counts_one_area_as_one_area(self, tmp_path):
        """The fixture puts every notice in a single town."""
        self._write(tmp_path)
        desc = (tmp_path / "c" / "carlow.html").read_text()
        assert "across 1 area -" in desc
        assert "across 1 areas" not in desc

    def test_the_sitemap_lists_every_page_and_nothing_else(self, tmp_path):
        counties, _ = self._write(tmp_path)
        root = ET.fromstring((tmp_path / "sitemap.xml").read_text())
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = [el.text for el in root.iter(f"{ns}loc")]
        assert locs == [f"{BASE_URL}/", f"{BASE_URL}/areas.html"] + [
            f"{BASE_URL}/c/{county_slug(c)}.html" for c in counties
        ] + [f"{BASE_URL}/a/carlow/testtown.html"]
        # the payload is fetched by the app, never landed on
        assert not any("data.js" in loc or "/h/" in loc for loc in locs)

    def test_robots_points_at_the_sitemap(self, tmp_path):
        self._write(tmp_path)
        assert f"Sitemap: {BASE_URL}/sitemap.xml" in (tmp_path / "robots.txt").read_text()

    def test_every_page_has_exactly_one_self_referential_canonical(self, tmp_path):
        """A canonical pointing at the wrong page is worse than none: it tells a
        search engine to drop the page it is on."""
        counties, _ = self._write(tmp_path)
        expected = {"index.html": f"{BASE_URL}/", "areas.html": f"{BASE_URL}/areas.html"}
        for county in counties:
            slug = county_slug(county)
            expected[f"c/{slug}.html"] = f"{BASE_URL}/c/{slug}.html"
        for rel, want in expected.items():
            found = re.findall(
                r'<link rel="canonical" href="([^"]*)">', (tmp_path / rel).read_text()
            )
            assert found == [want], rel

    def test_no_marker_survives_into_a_published_page(self, tmp_path):
        """A template marker left in the output is invisible in a browser and
        fatal in a search result — an unsubstituted <!--TITLE--> is the tab."""
        counties, _ = self._write(tmp_path)
        pages = ["index.html", "areas.html"] + [
            f"c/{county_slug(c)}.html" for c in counties
        ]
        for rel in pages:
            text = (tmp_path / rel).read_text()
            assert not re.search(r"<!--(TITLE|DESC|CANONICAL|BODY|AREAS)-->", text), rel


class TestCountyEvents:
    """The county page's own notice list."""

    def test_a_multi_area_event_is_listed_once(self, tmp_path):
        """area_history lists an event under every area its pins were homed to
        and shares one record between them; the county's list is the one place
        that has to collapse them, or 764 events would print twice."""
        record = {"ref": "CAR00000001", "start": "2026-05-01", "title": "t", "sev": "outage"}
        history = {"A": {"name": "A", "events": [record]}, "B": {"name": "B", "events": [record]}}
        assert county_events(history) == [record]

    def test_events_come_back_newest_first(self):
        old = {"ref": "R1", "start": "2026-05-01", "title": "old", "sev": "outage"}
        new = {"ref": "R2", "start": "2026-06-01", "title": "new", "sev": "outage"}
        history = {"A": {"name": "A", "events": [old, new]}}
        assert [e["ref"] for e in county_events(history)] == ["R2", "R1"]


class TestPayloadShape:
    """A key-set snapshot of everything data.js ships.

    A byte-size assertion cannot run in CI — the DB is gitignored — but "no field
    was added to the payload" is what actually needs guarding, and this fails
    loudly on the next well-meaning addition rather than quietly costing 80 KB.
    """

    def _site(self):
        site = build_site([_case()], SA_INDEX, AFTER_MAY, TOWNS)
        site.pop("recurrence_report")
        site.pop("history")
        site.pop("notice_text")
        site.pop("feed")
        return site

    def test_the_freshness_stamp_follows_the_data_not_the_build_clock(self):
        site = build_site(
            [_case()], SA_INDEX, AFTER_MAY, TOWNS,
            data_as_of=datetime(2026, 6, 14, 18, 30, tzinfo=UTC),
        )
        assert site["data_as_of_iso"] == "2026-06-14T18:30:00Z"
        assert site["generated_iso"] == "2026-06-15T00:00:00Z"

    def test_the_freshness_stamp_defaults_to_the_build_clock(self):
        site = self._site()
        assert site["data_as_of_iso"] == site["generated_iso"]

    def test_data_horizon_is_the_latest_sighting(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, last_seen TEXT)")
        assert data_horizon(conn) is None
        conn.executemany(
            "INSERT INTO cases VALUES (?, ?)",
            [(1, "2026-08-20T21:10:00+00:00"), (2, "2026-08-10T18:09:25+00:00")],
        )
        assert data_horizon(conn) == datetime(2026, 8, 20, 21, 10, tzinfo=UTC)

    def test_the_top_level_keys_are_unchanged(self):
        assert set(self._site()) == {
            "generated", "generated_iso", "data_as_of_iso", "months", "counties",
            "national", "top",
        }

    def test_the_county_keys_are_unchanged(self):
        county = self._site()["counties"]["Carlow"]
        assert set(county) == {"pop", "open_total", "months", "open", "towns", "resolved"}
        # "slug" is present exactly when the area has a page: the app cannot
        # derive it, because ui.js's slug() leaves a fada as a dash
        assert set(county["towns"]["T1"]) == {"name", "pop", "months", "slug"}
        assert set(county["towns"]["T1"]["months"]["2026-05"]) == {
            "events", "availability", "person_h"
        }

    def test_the_county_month_keys_are_unchanged(self):
        month = self._site()["counties"]["Carlow"]["months"]["2026-05"]
        assert set(month) == {
            "days", "clear_days", "days_elapsed", "grade", "events", "person_h",
            "period_h", "availability",
            "health_n", "median_completion_h", "completed_n", "median_scheduled_h",
            "scheduled_n", "median_pooled_h", "imputed_n", "health_now",
        }

    def test_the_top_row_keys_are_unchanged(self):
        """Guards the widening of event_meta to every severity from drifting
        into the published ranking."""
        assert set(self._site()["top"]["2026-05"][0]) == {
            "ref", "county", "title", "person_h", "hours", "people", "start", "pins",
            "confirmed", "scheduled", "area",
        }


# two Small Areas 1.5 km apart in different settlements, so a two-pin event
# published across both is homed to one area per pin — the shape 764 real events
# have, and the one the county breakdown and the history used to disagree about
SPLIT_SA = SmallAreaIndex(
    [(52.836, -6.926, "SA1", 1000), (52.850, -6.926, "SA2", 400)]
)
SPLIT_TOWNS = TownLookup(
    [("SA1", "T1", "Bigtown", "Carlow"), ("SA2", "T2", "Smallville", "Carlow")],
    SPLIT_SA.pop,
)


def _split_event():
    """One reference_num published as a pin in each settlement."""
    return [_case(id=1, full_lat=52.836), _case(id=2, full_lat=52.850)]


class TestMultiAreaEvents:
    """An event is listed under every area its pins were homed to.

    The county breakdown homes each *pin*, so a burst published across two
    settlements puts counts and person-hours on both rows. Listing it only under
    the area holding most of its people left 220 of the 1,830 areas in the county
    tables with no history at all — and their pages said no notice had ever been
    published there, directly under the row that had just counted one.
    """

    def _site(self):
        return build_site(_split_event(), SPLIT_SA, NOW, SPLIT_TOWNS)

    def test_every_area_in_the_county_tables_has_a_history(self):
        """The invariant the pin/event mismatch broke, and the reason the area
        directory can link every row it lists."""
        site = self._site()
        listed = set(site["counties"]["Carlow"]["towns"])
        assert listed and listed <= set(site["history"]["Carlow"])

    def test_the_event_appears_in_both_areas(self):
        history = self._site()["history"]["Carlow"]
        assert [e["ref"] for e in history["T1"]["events"]] == ["CAR00000001"]
        assert [e["ref"] for e in history["T2"]["events"]] == ["CAR00000001"]

    def test_both_listings_report_the_whole_events_footprint(self):
        """The record describes an event, not an area's accrual — so it is the
        same number the national top ten prints for the same event, on both."""
        history = self._site()["history"]["Carlow"]
        big, small = history["T1"]["events"][0], history["T2"]["events"][0]
        assert big["people"] == small["people"] == 1400
        assert big["hours"] == small["hours"]

    def test_a_shared_event_says_how_many_areas_it_is_in(self):
        """Or meeting the same burst on two pages reads as double-counting."""
        assert self._site()["history"]["Carlow"]["T1"]["events"][0]["areas"] == 2

    def test_a_single_area_event_does_not_carry_the_field(self):
        assert "areas" not in _history([_case()])[0]

    def test_the_record_is_built_once_and_shared(self):
        """event_record merges intervals and sums a footprint; doing it again per
        listing would be 1,270 wasted passes and could let the two drift."""
        history = self._site()["history"]["Carlow"]
        assert history["T1"]["events"][0] is history["T2"]["events"][0]

    def test_the_county_still_counts_the_event_once(self):
        """The duplication is in the histories only — it must not reach the
        county's own arithmetic, which dedupes by reference_num."""
        month = self._site()["counties"]["Carlow"]["months"]["2026-05"]
        assert month["events"]["outage"] == 1


class TestAreaIndex:
    """The directory page's rows: every area with a notice, county by county."""

    def _index(self):
        site = build_site(_split_event(), SPLIT_SA, NOW, SPLIT_TOWNS)
        return area_index(site["history"], SPLIT_TOWNS)

    def test_counties_and_areas_come_out_sorted(self):
        [(county, areas)] = self._index()
        assert county == "Carlow"
        assert [name for _, name, _, _ in areas] == ["Bigtown", "Smallville"]

    def test_each_area_carries_its_population_and_notice_count(self):
        [(_, areas)] = self._index()
        assert areas[0] == ("T1", "Bigtown", 1000, 1)
        assert areas[1] == ("T2", "Smallville", 400, 1)

    def test_the_count_is_the_length_of_the_history_not_a_month_sum(self):
        """An event spanning a month boundary is deliberately counted in both
        months, so summing the county payload's month rows would overstate."""
        rows = [_case(start_date="2026-05-31T12:00:00+00:00",
                      notice_to_end_seconds=48 * 3600, end_local_date="2026-06-02")]
        site = build_site(rows, SA_INDEX, datetime(2026, 7, 5, tzinfo=UTC), TOWNS)
        months = site["counties"]["Carlow"]["towns"]["T1"]["months"]
        assert sum(m["events"]["outage"] for m in months.values()) == 2   # the trap
        [(_, areas)] = area_index(site["history"], TOWNS)
        assert areas[0][3] == 1                                          # the truth

    def test_an_unplaced_bucket_is_labelled_and_has_no_population(self):
        towns = TownLookup([("SA1", "T1", "Blessington", "Wicklow")], SA_INDEX.pop)
        site = build_site([_case()], SA_INDEX, NOW, towns)
        [(_, areas)] = area_index(site["history"], towns)
        assert areas == [(UNPLACED, UNPLACED_LABEL, None, 1)]


class TestAreaIndexHtml:
    """Links out of the directory have to survive area codes that are not
    URL-safe: 31 contain a slash, 2,808 a colon, 15 an apostrophe, 4 are
    non-ASCII. A slash left unescaped breaks the route's county capture."""

    def _links(self, code, name="X"):
        index = [("Cork", [(code, name, 100, 1)])]
        return _area_index_html(index)

    def test_a_slash_in_a_code_is_escaped(self):
        html = self._links("ed:Cork:Whiddy/Bantry Rural")
        assert "index.html#area/Cork/ed%3ACork%3AWhiddy%2FBantry%20Rural" in html
        assert "Whiddy/Bantry" not in html   # no raw slash reaches the href

    def test_an_apostrophe_and_a_fada_are_escaped(self):
        """Only areas without a page still go through the hash route, so the
        encoding that matters is an ED's."""
        assert "O%27Briensbridge" in self._links("ed:Clare:O'Briensbridge")
        assert "ed%3AGalway%3AAn%20Sp%C3%ADd%C3%A9al" in self._links("ed:Galway:An Spídéal")

    def test_an_area_with_a_page_is_linked_to_it_and_not_to_the_hash(self):
        """The county-and-name slug, not the code: a code is not a filename."""
        html = self._links("02341-Dún Laoghaire", name="Dún Laoghaire")
        assert 'href="a/cork/dun-laoghaire.html"' in html
        assert "index.html#area" not in html

    def test_an_area_name_is_html_escaped(self):
        assert "&amp;" in self._links("T1", name="Ballymore & Kill")

    def test_there_is_one_section_and_one_nav_link_per_county(self):
        html = _area_index_html([("Cork", [("T1", "A", 1, 1)]),
                                 ("Louth", [("T2", "B", 1, 1)])])
        assert html.count("<section") == 2
        assert 'href="#c-cork"' in html and 'id="c-louth"' in html


class TestReleaseDb:
    """The site builds from whichever release is current, and a release can
    predate a column: the data build migrates the DB and republishes it, but a
    UI push in between reads the old one. read_cases carries the local copy
    forward before the SELECT names the new column."""

    def _v3_db(self, path):
        _cases_db(path, version=3)
        with sqlite3.connect(path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(cases)")}
            assert "vanished_at" not in cols
            row = {k: v for k, v in _case().items() if k in cols}
            conn.execute(
                f"INSERT INTO cases ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                list(row.values()),
            )
            conn.execute(
                "CREATE TABLE inferred_cases (case_id, notice_to_end_seconds, end_source, "
                "end_local_date, end_local_time, end_recurrence, end_window_open, "
                "end_window_close, end_window_first_date)"
            )

    def test_a_release_from_before_the_last_column_still_builds(self, tmp_path):
        path = tmp_path / "uisce.db"
        self._v3_db(path)
        with sqlite3.connect(path) as conn:
            with pytest.raises(sqlite3.OperationalError, match="vanished_at"):
                load_cases(conn)
        rows, horizon = read_cases(path)
        assert [r["reference_num"] for r in rows] == ["CAR00000001"]
        assert rows[0]["vanished_at"] is None
        with sqlite3.connect(path) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
