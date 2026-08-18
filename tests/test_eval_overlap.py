from datetime import datetime, timezone

from conftest import site_case as _case

from uisce.eval_overlap import overlap_by_month, report
from uisce.site import SmallAreaIndex

UTC = timezone.utc
NOW = datetime(2026, 5, 10, tzinfo=UTC)

# two Small Areas, far enough apart that a pin on one never reaches the other
SA_INDEX = SmallAreaIndex(
    [(52.836, -6.926, "SA1", 1000), (53.500, -6.926, "SA2", 500)]
)


class TestOverlapByMonth:
    def test_a_single_event_shows_no_overlap(self):
        """With one event the per-event and per-SA sums are the same product,
        so any nonzero delta here would be a bug in the probe, not overlap."""
        by_month = overlap_by_month([_case()], SA_INDEX, NOW)
        published, exact = by_month["2026-05"]
        assert published == exact == 24 * 3600 * 1000

    def test_two_events_on_the_same_area_double_count(self):
        """Two concurrent events covering SA1 charge its 1,000 people twice in
        the published figure; the per-SA union charges them once."""
        rows = [
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="CAR2"),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published == 2 * 24 * 3600 * 1000
        assert exact == 24 * 3600 * 1000

    def test_disjoint_events_do_not_read_as_overlap(self):
        rows = [
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="CAR2", full_lat=53.500),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published == exact == 24 * 3600 * 1000 + 24 * 3600 * 500

    def test_only_the_outage_class_is_measured(self):
        """The published availability numerator is outage-only, so the probe
        must be too — a quality notice overlapping a burst is not overlap in
        any figure the site ships."""
        rows = [
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="CAR2", work_category="discolouration"),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published == exact == 24 * 3600 * 1000

    def test_one_events_staggered_pins_are_not_overlap(self):
        """The measurement this probe exists to make is *between* events. A
        multi-pin event whose pins land in different places at different times —
        July's largest ran 385h across 18 pins — is one accrual, and reading its
        own staggering as double-counting reported 50% overlap where there was
        none. Both sides charge the event's whole union to its whole footprint."""
        rows = [
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="CAR1", full_lat=53.500,
                  start_date="2026-05-05T00:00:00+00:00",
                  end_local_date="2026-05-06"),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published == exact == 48 * 3600 * 1500

    def test_a_case_with_no_end_signal_is_charged_its_imputed_span(self):
        """"published" has to be what the site publishes, which means the same
        SpanTable. Without it these take a 1-second token footprint instead of
        the category median, and about one disruption in twenty is one of them —
        so their overlap silently left the measurement."""
        rows = [
            # the only observed completion, so SpanTable's global median is 24h
            _case(id=1, reference_num="CAR1", full_lat=53.500),
            _case(id=2, reference_num="CAR2", notice_to_end_seconds=None,
                  end_source="not_found", end_local_date=None, end_local_time=None),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published == exact == 24 * 3600 * 500 + 24 * 3600 * 1000

    def test_partial_temporal_overlap_counts_only_the_shared_span(self):
        """12 hours shared between two 24-hour events: the delta is 12 hours of
        SA1's population, not a whole event."""
        rows = [
            _case(id=1, reference_num="CAR1"),
            _case(id=2, reference_num="CAR2",
                  start_date="2026-05-01T12:00:00+00:00"),
        ]
        published, exact = overlap_by_month(rows, SA_INDEX, NOW)["2026-05"]
        assert published - exact == 12 * 3600 * 1000


class TestReport:
    def test_report_totals_and_share(self):
        lines = report({"2026-05": (200.0 * 3600, 150.0 * 3600)})
        assert any("2026-05" in line and "25.0%" in line for line in lines)
        assert lines[-1].startswith("   total")
