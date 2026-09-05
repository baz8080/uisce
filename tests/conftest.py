from uisce import pipeline


def _permissive(name, declared):
    """The real declaration includes `REAL NOT NULL` on the coordinates, which a
    throwaway record of Nones would trip. These fixtures exercise the upsert's
    stamping logic, not its geometry, so every column is relaxed to TEXT — but
    the column set and order still come from pipeline.CASE_COLUMNS, which is the
    whole point: adding a column to the schema must not mean remembering to add
    it here too."""
    return "INTEGER PRIMARY KEY" if name == "id" else "TEXT"


def make_cases_table(conn):
    """A `cases` table with the declared columns and no constraints to satisfy."""
    conn.execute(f"CREATE TABLE cases ({pipeline.cases_ddl(_permissive)})")
    return conn


def case_record(**overrides):
    """A mapped case as load_cases expects one: every fed column, all None."""
    return dict.fromkeys(pipeline.DB_CASE_COLUMNS) | overrides


def site_case(**overrides):
    """A row as `load_cases` hands one to `site.py`, with a plain closed burst
    main as the default.

    Lives here rather than in a test module because test_site.py and
    test_eval_overlap.py need the same shape and `tests/` shares code through
    this file — see the `from conftest import ...` in test_pipeline.py and
    test_replay_closed_at.py. A second copy is how the shape drifts from
    `pipeline.CASE_COLUMNS` one column at a time.
    """
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
        # read only by describes_recurrence; the default says nothing about a
        # repeating window, so a case is non-recurring unless a test says so
        "description": "Works may cause supply disruptions to Somewhere, Co. Carlow.",
        "closed_at": None,
        "vanished_at": None,
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
