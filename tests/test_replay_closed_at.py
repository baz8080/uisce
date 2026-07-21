import sqlite3

import pytest

from uisce import pipeline
from uisce.replay_closed_at import apply_stamps, replay, snapshot_files


def _snapshot(tmp_path, tag, rows):
    """A minimal stand-in for a published uisce.db: only id and status are read."""
    path = tmp_path / f"{tag}.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, status TEXT)")
        conn.executemany("INSERT INTO cases VALUES (?, ?)", rows)
    return tag, path


def _live_db(tmp_path, rows):
    path = tmp_path / "live.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE cases (id INTEGER PRIMARY KEY, status TEXT, closed_at TEXT)"
        )
        conn.executemany("INSERT INTO cases VALUES (?, ?, ?)", rows)
    return path


class TestReplay:
    def test_stamps_the_first_snapshot_observing_the_close(self, tmp_path):
        snaps = [
            _snapshot(tmp_path, "2026-06-30", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-06", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-08", [(1, "Closed")]),
            _snapshot(tmp_path, "2026-07-10", [(1, "Closed")]),
        ]
        # the later snapshots must not drag the stamp forward
        assert replay(snaps) == {1: "2026-07-08"}

    def test_case_never_seen_open_is_not_stamped(self, tmp_path):
        # Created and closed inside one gap: no transition was ever observed, so
        # there is nothing to recover. ~12% of new cases look like this.
        snaps = [
            _snapshot(tmp_path, "2026-06-30", []),
            _snapshot(tmp_path, "2026-07-06", [(1, "Closed")]),
        ]
        assert replay(snaps) == {}

    def test_case_closed_before_the_window_is_not_stamped(self, tmp_path):
        snaps = [
            _snapshot(tmp_path, "2026-06-30", [(1, "Closed")]),
            _snapshot(tmp_path, "2026-07-06", [(1, "Closed")]),
        ]
        assert replay(snaps) == {}

    def test_reopen_clears_then_recloses(self, tmp_path):
        snaps = [
            _snapshot(tmp_path, "2026-06-30", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-06", [(1, "Closed")]),
            _snapshot(tmp_path, "2026-07-08", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-10", [(1, "Closed")]),
        ]
        assert replay(snaps) == {1: "2026-07-10"}

    def test_reopen_left_open_clears_entirely(self, tmp_path):
        snaps = [
            _snapshot(tmp_path, "2026-06-30", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-06", [(1, "Closed")]),
            _snapshot(tmp_path, "2026-07-08", [(1, "Open")]),
        ]
        assert replay(snaps) == {}

    def test_null_status_counts_as_closed(self, tmp_path):
        # Matches the live upsert's IS NOT 'Open'; some rows carry NULL status.
        snaps = [
            _snapshot(tmp_path, "2026-06-30", [(1, "Open")]),
            _snapshot(tmp_path, "2026-07-06", [(1, None)]),
        ]
        assert replay(snaps) == {1: "2026-07-06"}

    def test_snapshots_are_walked_in_tag_order_not_glob_order(self, tmp_path):
        for tag, rows in [
            ("2026-07-10", [(1, "Closed")]),
            ("2026-06-30", [(1, "Open")]),
            ("2026-07-06", [(1, "Closed")]),
        ]:
            _snapshot(tmp_path, tag, rows)
        assert replay(snapshot_files(tmp_path)) == {1: "2026-07-06"}

    def test_empty_snapshot_dir_is_an_error(self, tmp_path):
        with pytest.raises(SystemExit):
            snapshot_files(tmp_path)


class TestApplyStamps:
    def test_write_false_reports_without_changing_anything(self, tmp_path):
        db = _live_db(tmp_path, [(1, "Closed", None)])
        updates, _ = apply_stamps({1: "2026-07-06"}, db, write=False)
        assert updates == [("2026-07-06", 1)]
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT closed_at FROM cases").fetchone() == (None,)

    def test_write_true_stamps_the_row(self, tmp_path):
        db = _live_db(tmp_path, [(1, "Closed", None)])
        apply_stamps({1: "2026-07-06"}, db, write=True)
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT closed_at FROM cases").fetchone() == ("2026-07-06",)

    def test_existing_stamp_is_never_overwritten(self, tmp_path):
        # A live-path stamp is at least as precise as a replayed one.
        db = _live_db(tmp_path, [(1, "Closed", "2026-07-08T00:00:00+00:00")])
        updates, _ = apply_stamps({1: "2026-07-06"}, db, write=True)
        assert updates == []
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT closed_at FROM cases").fetchone() == (
                "2026-07-08T00:00:00+00:00",
            )

    def test_currently_open_row_is_skipped(self, tmp_path):
        # Reopened since the last snapshot: stamping it would hide it from any
        # "open at end of month" query.
        db = _live_db(tmp_path, [(1, "Open", None)])
        updates, _ = apply_stamps({1: "2026-07-06"}, db, write=True)
        assert updates == []

    def test_case_absent_from_the_live_db_is_skipped(self, tmp_path):
        db = _live_db(tmp_path, [(1, "Closed", None)])
        updates, _ = apply_stamps({2: "2026-07-06"}, db, write=True)
        assert updates == []


def test_replayed_and_live_stamps_share_one_column(tmp_path):
    """The two paths must remain the same measurement: replay fills the gap the
    live upsert cannot reach, and the live upsert takes over from there."""
    db = tmp_path / "live.db"
    with sqlite3.connect(db) as conn:
        cols = ", ".join(
            f"{c} TEXT" if c != "id" else "id INTEGER PRIMARY KEY"
            for c in pipeline.DB_CASE_COLUMNS
        )
        conn.execute(
            f"CREATE TABLE cases ({cols}, first_seen TEXT, last_seen TEXT, closed_at TEXT)"
        )

    record = dict.fromkeys(pipeline.DB_CASE_COLUMNS)
    with sqlite3.connect(db) as conn:
        pipeline.load_cases(conn, [record | {"id": 1, "status": "Open"},
                                   record | {"id": 2, "status": "Closed"}],
                            now="2026-07-21T00:00:00+00:00")

    # case 2 closed before we watched; replay recovers it from the snapshots
    apply_stamps({2: "2026-07-06"}, db, write=True)
    # case 1 closes later, on the live path
    with sqlite3.connect(db) as conn:
        pipeline.load_cases(conn, [record | {"id": 1, "status": "Closed"}],
                            now="2026-07-22T00:00:00+00:00")
        stamps = dict(conn.execute("SELECT id, closed_at FROM cases ORDER BY id"))

    assert stamps == {1: "2026-07-22T00:00:00+00:00", 2: "2026-07-06"}
