import sqlite3

import pytest

from uisce.build import (
    check_cases_cover,
    compute_notice_to_end_seconds,
    count_never_inferred,
    date_forms,
    first_start_date_per_case,
    latest_per_case,
    time_forms,
    unquotable_windows,
)


class TestComputeDurationSeconds:
    def test_summer_time_end_is_converted_from_ist(self):
        # 12:00 Dublin local in June is 11:00 UTC (IST = UTC+1)
        duration = compute_notice_to_end_seconds(
            "2026-06-01T10:00:00+00:00", "completion_update", "2026-06-01", "12:00"
        )
        assert duration == 3600

    def test_winter_time_end_matches_utc(self):
        # 12:00 Dublin local in January is 12:00 UTC (GMT)
        duration = compute_notice_to_end_seconds(
            "2026-01-05T10:00:00+00:00", "completion_update", "2026-01-05", "12:00"
        )
        assert duration == 7200

    def test_missing_time_falls_back_to_end_of_day(self):
        duration = compute_notice_to_end_seconds(
            "2026-01-05T00:00:00+00:00", "scheduled_end_date_only", "2026-01-05", None
        )
        assert duration == 23 * 3600 + 59 * 60 + 59

    def test_nonexistent_spring_forward_time_does_not_crash(self):
        # 01:30 local on 2026-03-29 does not exist in Dublin (clocks jump
        # 01:00 -> 02:00); zoneinfo resolves it rather than raising
        duration = compute_notice_to_end_seconds(
            "2026-03-29T00:00:00+00:00", "completion_update", "2026-03-29", "01:30"
        )
        assert duration is not None and duration > 0

    def test_negative_duration_is_nulled(self):
        duration = compute_notice_to_end_seconds(
            "2026-06-02T10:00:00+00:00", "completion_update", "2026-06-01", "12:00"
        )
        assert duration is None

    @pytest.mark.parametrize("source", ["not_found", "lifted_immediate"])
    def test_no_end_signal_sources_return_none(self, source):
        start = "2026-06-01T10:00:00+00:00"
        assert compute_notice_to_end_seconds(start, source, "2026-06-01", "12:00") is None

    def test_missing_date_or_start_returns_none(self):
        start = "2026-06-01T10:00:00+00:00"
        assert compute_notice_to_end_seconds(start, "completion_update", None, None) is None
        assert (
            compute_notice_to_end_seconds(None, "completion_update", "2026-06-01", "12:00") is None
        )


def _record(case_id, inferred_at, start_date="2026-06-01T00:00:00+00:00"):
    return {"case_id": case_id, "inferred_at": inferred_at, "start_date": start_date}


def test_latest_per_case_keeps_newest_record():
    records = [
        _record(1, "2026-06-01T00:00:00+00:00"),
        _record(1, "2026-07-01T00:00:00+00:00"),
        _record(2, "2026-06-15T00:00:00+00:00"),
    ]
    latest = {r["case_id"]: r["inferred_at"] for r in latest_per_case(records)}
    assert latest == {1: "2026-07-01T00:00:00+00:00", 2: "2026-06-15T00:00:00+00:00"}


def test_first_start_date_per_case_pins_earliest_run():
    records = [
        _record(1, "2026-07-01T00:00:00+00:00", start_date="2026-06-20T00:00:00+00:00"),
        _record(1, "2026-06-01T00:00:00+00:00", start_date="2026-05-01T00:00:00+00:00"),
    ]
    assert first_start_date_per_case(records) == {1: "2026-05-01T00:00:00+00:00"}


def test_count_never_inferred_reports_backlog_and_open_share():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, description TEXT, status TEXT)")
    conn.execute("CREATE TABLE inferred_cases (case_id INTEGER PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO cases VALUES (?, ?, ?)",
        [
            (1, "inferred already", "Open"),
            (2, "backlog, open", "Open"),
            (3, "backlog, closed", "Closed"),
            (4, None, "Open"),  # no description: never a candidate for inference
        ],
    )
    conn.execute("INSERT INTO inferred_cases VALUES (1)")

    assert count_never_inferred(conn) == (2, 1)


class TestCheckCasesCover:
    def _db_with_case_ids(self, ids):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO cases (id) VALUES (?)", [(i,) for i in ids])
        return conn

    def test_passes_when_all_ids_known(self):
        conn = self._db_with_case_ids([1, 2, 3])
        check_cases_cover(conn, {1, 3})

    def test_raises_naming_missing_range(self):
        conn = self._db_with_case_ids([1, 2])
        with pytest.raises(RuntimeError, match=r"2 case_id\(s\).*range 5-9"):
            check_cases_cover(conn, {1, 5, 9})


class TestWindowForms:
    """The spellings a notice might use. Generous by design: a form this misses
    reads as a value absent from the text, so a gap costs a false alarm rather
    than a missed one."""

    def test_a_whole_hour_covers_the_twelve_and_twenty_four_hour_spellings(self):
        forms = time_forms("22:00")
        assert {"22:00", "10pm", "10 pm", "10.00pm", "10:00pm"} <= forms

    def test_a_half_hour_keeps_its_minutes(self):
        forms = time_forms("05:30")
        assert {"05:30", "5:30", "5:30am", "5.30am"} <= forms
        assert "5am" not in forms

    def test_noon_and_midnight_do_not_become_zero(self):
        assert "12pm" in time_forms("12:00")
        assert "12am" in time_forms("00:00")

    def test_dates_cover_the_written_and_numeric_spellings(self):
        forms = date_forms("2026-07-09")
        assert {"9 July", "09 July", "9 Jul", "9th July", "9/07", "09/07"} <= forms


class TestUnquotableWindows:
    """The only standing check on the window fields: no eval round labels them,
    so a prompt that began inventing windows would otherwise show up only as
    person-hours quietly falling."""

    def _db(self, description, open_t="22:00", close_t="07:00",
            first_date="2026-07-09", start_date="2026-07-09T14:00:00+00:00"):
        conn = sqlite3.connect(":memory:")
        conn.execute("""CREATE TABLE cases (id INTEGER PRIMARY KEY,
            description TEXT, start_date TEXT)""")
        conn.execute("""CREATE TABLE inferred_cases (case_id INTEGER PRIMARY KEY,
            end_recurrence TEXT, end_window_open TEXT, end_window_close TEXT,
            end_window_first_date TEXT)""")
        conn.execute("INSERT INTO cases VALUES (1, ?, ?)", (description, start_date))
        conn.execute("INSERT INTO inferred_cases VALUES (1, 'daily', ?, ?, ?)",
                     (open_t, close_t, first_date))
        return conn

    QUOTABLE = (
        "Works are scheduled to take place daily from 10pm until 7am, from 9 July to 27 July."
    )

    def test_a_window_quoted_from_the_text_is_not_flagged(self):
        flagged, inert = unquotable_windows(self._db(self.QUOTABLE))
        assert (flagged, inert) == ([], 0)

    def test_html_markup_does_not_hide_a_quotable_value(self):
        conn = self._db(f"<p>Notice.<br><br>{self.QUOTABLE}</p>")
        assert unquotable_windows(conn) == ([], 0)

    def test_an_invented_opening_time_is_flagged(self):
        flagged, _ = unquotable_windows(self._db(self.QUOTABLE, open_t="03:00"))
        assert flagged == [(1, ["open 03:00"])]

    def test_an_invented_closing_time_is_flagged(self):
        flagged, _ = unquotable_windows(self._db(self.QUOTABLE, close_t="04:30"))
        assert flagged == [(1, ["close 04:30"])]

    def test_a_first_date_the_text_gives_none_for_is_inert_not_flagged(self):
        """The model fills that gap with the publication date, and daily_windows
        clamps the series to publication anyway, so no figure can move. Flagging
        it every build would train the reader to ignore the check."""
        text = "Restrictions are scheduled nightly from 10pm until 7am until 5 August."
        flagged, inert = unquotable_windows(
            self._db(text, first_date="2026-07-09", start_date="2026-07-09T14:00:00+00:00")
        )
        assert (flagged, inert) == ([], 1)

    def test_a_first_date_after_publication_that_is_absent_is_flagged(self):
        """Inert only covers a date at or before publication. A later one moves
        the series start, so it has to be quotable."""
        text = "Restrictions are scheduled nightly from 10pm until 7am until 5 August."
        flagged, inert = unquotable_windows(
            self._db(text, first_date="2026-07-20", start_date="2026-07-09T14:00:00+00:00")
        )
        assert flagged == [(1, ["first date 2026-07-20"])]
        assert inert == 0

    def test_a_case_claiming_no_recurrence_is_not_checked(self):
        conn = self._db(self.QUOTABLE, open_t="03:00")
        conn.execute("UPDATE inferred_cases SET end_recurrence = 'none'")
        assert unquotable_windows(conn) == ([], 0)
