import json
import sqlite3

import pytest
from conftest import make_cases_table

from uisce import build, inference
from uisce.build import (
    check_cases_cover,
    compute_notice_to_end_seconds,
    count_never_inferred,
    date_forms,
    first_start_date_per_case,
    time_forms,
    unquotable_windows,
)
from uisce.inference import readable_latest


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


def test_readable_latest_keeps_newest_record():
    records = [
        _record(1, "2026-06-01T00:00:00+00:00"),
        _record(1, "2026-07-01T00:00:00+00:00"),
        _record(2, "2026-06-15T00:00:00+00:00"),
    ]
    latest, unreadable = readable_latest(records)
    assert {c: r["inferred_at"] for c, r in latest.items()} == {
        1: "2026-07-01T00:00:00+00:00", 2: "2026-06-15T00:00:00+00:00"}
    assert unreadable == []


def test_first_start_date_per_case_pins_earliest_run():
    # the later run saw an earlier start: a backward re-stamp, which must not win
    records = [
        _record(1, "2026-07-01T00:00:00+00:00", start_date="2026-05-01T00:00:00+00:00"),
        _record(1, "2026-06-01T00:00:00+00:00", start_date="2026-06-20T00:00:00+00:00"),
    ]
    assert first_start_date_per_case(records) == {1: "2026-06-20T00:00:00+00:00"}


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


START = "2026-09-22T13:18:00+00:00"
# case 244925 before and after its completion update: the rules abstain on
# neither now, so the stale tests use a description they cannot read
BOILERPLATE = (" We recommend that you allow 3-4 hours after the estimated restoration "
               "time for your supply to fully return. Please take note of the following "
               "reference number: GAL00121134. LA01")
SCHEDULED = ("Mains repair works may cause supply disruptions to Shanbally and surrounding "
             "areas in Co. Galway. Works are scheduled to take place from 2pm until "
             "6:15pm on 22 September." + BOILERPLATE)
COMPLETED = ("**11:31rn 23/09/2026 - Tá críoch leis an obair se o anois, agus beidh an "
             "soláthar uisce ar ais chomh luath agus is féidir.** Seans go mbeidh cur "
             "isteach ar an soláthar uisce i Shanbally. **Update 11:31am 23/09/2026** "
             "Works are now complete and supply should have returned to all affected "
             "areas. " + SCHEDULED)
INVESTIGATING = "We are investigating reports of supply disruptions to Shanbally."


class TestRun:
    def _wire(self, tmp_path, monkeypatch, description, records):
        db, jsonl = tmp_path / "uisce.db", tmp_path / "inferred.jsonl"
        conn = make_cases_table(sqlite3.connect(db))
        conn.execute("INSERT INTO cases (id, description, start_date, status) "
                     "VALUES (1, ?, ?, 'Open')", (description, START))
        conn.commit()
        conn.close()
        jsonl.write_text("".join(json.dumps(r) + "\n" for r in records))
        for module in (build, inference):
            monkeypatch.setattr(module, "DB_PATH", db)
            monkeypatch.setattr(module, "JSONL_PATH", jsonl)
        return db, jsonl

    def _record(self, description=SCHEDULED, inferred_at="2026-09-22T20:00:00+00:00",
                **result):
        return inference.build_record(
            1, description, START,
            {"end_source": "scheduled_end_with_time", "local_date": "2026-09-22",
             "local_time": "18:15"} | result,
            inferred_at=inferred_at)

    def _published(self, db):
        return sqlite3.connect(db).execute(
            "SELECT end_inferred_at, end_source, end_local_time FROM inferred_cases"
        ).fetchall()

    def test_a_value_build_cannot_read_is_left_out_with_a_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        db, _ = self._wire(tmp_path, monkeypatch, SCHEDULED,
                           [self._record(local_time="24:00")])
        build.run()
        assert self._published(db) == []
        out = capsys.readouterr().out
        assert "::warning::1 case(s) have a newest record" in out and out.count(": 1\n")

    def test_an_unreadable_record_superseded_by_a_readable_one_is_not_warned(
        self, tmp_path, monkeypatch, capsys
    ):
        self._wire(tmp_path, monkeypatch, SCHEDULED, [
            self._record(local_time="24:00") | {"model": inference.MODEL_NAME},
            self._record(inferred_at="2026-09-23T00:00:00+00:00")
            | {"model": inference.MODEL_NAME},
        ])
        build.run()
        assert "::warning::" not in capsys.readouterr().out

    def test_an_unreadable_window_falls_back_to_the_previous_record(
        self, tmp_path, monkeypatch
    ):
        db, _ = self._wire(tmp_path, monkeypatch, SCHEDULED, [
            self._record(),
            self._record(inferred_at="2026-09-23T00:00:00+00:00", recurrence="daily",
                         window_open="7:00", window_close="22:00",
                         window_first_date="2026-09-22"),
        ])
        build.run()
        assert self._published(db) == [
            ("2026-09-22T20:00:00+00:00", "scheduled_end_with_time", "18:15")]

    def test_a_failure_part_way_leaves_the_previous_table_standing(
        self, tmp_path, monkeypatch
    ):
        db, _ = self._wire(tmp_path, monkeypatch, SCHEDULED, [self._record()])
        build.run()

        def failing(conn):
            raise RuntimeError("after the inserts")

        monkeypatch.setattr(build, "unquotable_windows", failing)
        with pytest.raises(RuntimeError):
            build.run()
        assert len(self._published(db)) == 1

    def test_a_record_for_an_older_description_is_published_and_warned(
        self, tmp_path, monkeypatch, capsys
    ):
        db, _ = self._wire(tmp_path, monkeypatch, INVESTIGATING, [self._record()])
        build.run()
        assert self._published(db) == [
            ("2026-09-22T20:00:00+00:00", "scheduled_end_with_time", "18:15")]
        out = capsys.readouterr().out
        assert "::warning::1 case(s) publish a record uisce-infer would redo" in out
        assert out.rstrip().endswith(": 1")

    def test_a_record_from_a_retired_extractor_is_warned_too(
        self, tmp_path, monkeypatch, capsys
    ):
        self._wire(tmp_path, monkeypatch, SCHEDULED,
                   [self._record() | {"model": "rules-v1"}])
        build.run()
        assert "::warning::1 case(s)" in capsys.readouterr().out

    def test_a_current_record_raises_no_warning(self, tmp_path, monkeypatch, capsys):
        self._wire(tmp_path, monkeypatch, SCHEDULED,
                   [self._record() | {"model": inference.MODEL_NAME}])
        build.run()
        assert "::warning::" not in capsys.readouterr().out

    def test_a_bilingual_completion_reaches_the_table_from_a_rules_only_run(
        self, tmp_path, monkeypatch, capsys
    ):
        db, jsonl = self._wire(tmp_path, monkeypatch, COMPLETED,
                               [self._record() | {"model": "rules-v1"}])
        inference.run(["--rules-only"])
        build.run()
        assert self._published(db)[0][1:] == ("completion_update", "11:31")
        assert "::warning::" not in capsys.readouterr().out
