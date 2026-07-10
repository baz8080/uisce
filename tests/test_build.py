import sqlite3

import pytest

from uisce.build import (
    check_cases_cover,
    compute_duration_seconds,
    first_start_date_per_case,
    latest_per_case,
)


class TestComputeDurationSeconds:
    def test_summer_time_end_is_converted_from_ist(self):
        # 12:00 Dublin local in June is 11:00 UTC (IST = UTC+1)
        duration = compute_duration_seconds(
            "2026-06-01T10:00:00+00:00", "completion_update", "2026-06-01", "12:00"
        )
        assert duration == 3600

    def test_winter_time_end_matches_utc(self):
        # 12:00 Dublin local in January is 12:00 UTC (GMT)
        duration = compute_duration_seconds(
            "2026-01-05T10:00:00+00:00", "completion_update", "2026-01-05", "12:00"
        )
        assert duration == 7200

    def test_missing_time_falls_back_to_end_of_day(self):
        duration = compute_duration_seconds(
            "2026-01-05T00:00:00+00:00", "scheduled_end_date_only", "2026-01-05", None
        )
        assert duration == 23 * 3600 + 59 * 60 + 59

    def test_nonexistent_spring_forward_time_does_not_crash(self):
        # 01:30 local on 2026-03-29 does not exist in Dublin (clocks jump
        # 01:00 -> 02:00); zoneinfo resolves it rather than raising
        duration = compute_duration_seconds(
            "2026-03-29T00:00:00+00:00", "completion_update", "2026-03-29", "01:30"
        )
        assert duration is not None and duration > 0

    def test_negative_duration_is_nulled(self):
        duration = compute_duration_seconds(
            "2026-06-02T10:00:00+00:00", "completion_update", "2026-06-01", "12:00"
        )
        assert duration is None

    @pytest.mark.parametrize("source", ["not_found", "lifted_immediate"])
    def test_no_duration_sources_return_none(self, source):
        assert (
            compute_duration_seconds("2026-06-01T10:00:00+00:00", source, "2026-06-01", "12:00")
            is None
        )

    def test_missing_date_or_start_returns_none(self):
        assert (
            compute_duration_seconds("2026-06-01T10:00:00+00:00", "completion_update", None, None)
            is None
        )
        assert compute_duration_seconds(None, "completion_update", "2026-06-01", "12:00") is None


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
