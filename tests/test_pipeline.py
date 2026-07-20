import json
import sqlite3

import pytest
import requests

from uisce import pipeline
from uisce.pipeline import (
    CATEGORY_RULES,
    _epoch_ms_to_iso,
    _is_usable_case,
    backfill,
    backfill_work_category,
    backfill_work_type,
    classify_category,
    download_cases,
    geocode_all,
    geocode_cache_row,
    map_cases,
    normalise_legacy_empty_strings,
    skip_geocoding,
    trim_titles,
)


def make_feature(attrs=None, x=0.0, y=0.0):
    base = {"OBJECTID": 1, "TITLE": "Burst Water Main – Cork", "COUNTY": "Cork"}
    base.update(attrs or {})
    return {"attributes": base, "geometry": {"x": x, "y": y}}


class TestMapCases:
    def test_maps_fields_and_converts_dates(self):
        feature = make_feature(
            {
                "OBJECTID": 42,
                "STARTDATE": 0,
                "ENDDATE": 86_400_000,
                "DESCRIPTION": "Some works",
                "UNMAPPED_FIELD": "dropped",
            }
        )
        mapped, skipped = map_cases([feature])

        assert skipped == []
        case = mapped[0]
        assert case["id"] == 42
        assert case["title"] == "Burst Water Main – Cork"
        assert case["start_date"] == "1970-01-01T00:00:00+00:00"
        assert case["end_date"] == "1970-01-02T00:00:00+00:00"
        assert "UNMAPPED_FIELD" not in case
        assert "unmapped_field" not in case

    def test_transforms_and_rounds_coordinates(self):
        # Web Mercator origin is exactly (0, 0) in WGS84
        mapped, _ = map_cases([make_feature(x=0.0, y=0.0)])
        case = mapped[0]
        assert case["full_lat"] == 0.0
        assert case["full_lon"] == 0.0

        # rounded coords are always the 4-decimal rounding of the full coords
        mapped, _ = map_cases([make_feature(x=-697000.0, y=7047000.0)])
        case = mapped[0]
        assert case["rounded_lat"] == round(case["full_lat"], 4)
        assert case["rounded_lon"] == round(case["full_lon"], 4)

    def test_skips_cases_without_title_or_description(self):
        unusable = make_feature({"OBJECTID": 7, "TITLE": None, "DESCRIPTION": ""})
        usable = make_feature({"OBJECTID": 8, "TITLE": None, "DESCRIPTION": "text"})

        mapped, skipped = map_cases([unusable, usable])

        assert skipped == [7]
        assert [c["id"] for c in mapped] == [8]

    def test_fixes_dnegal_typo_and_missing_title(self):
        feature = make_feature({"COUNTY": "Dnegal", "TITLE": "", "DESCRIPTION": "text"})
        mapped, _ = map_cases([feature])
        assert mapped[0]["county"] == "Donegal"
        assert mapped[0]["title"] == "unknown"

    def test_trims_title_whitespace(self):
        feature = make_feature({"TITLE": "  Burst Water Main – Cork  "})
        mapped, _ = map_cases([feature])
        assert mapped[0]["title"] == "Burst Water Main – Cork"

    def test_whitespace_only_title_becomes_unknown(self):
        feature = make_feature({"TITLE": "   ", "DESCRIPTION": "text"})
        mapped, _ = map_cases([feature])
        assert mapped[0]["title"] == "unknown"

    def test_normalises_empty_strings_to_none(self):
        feature = make_feature({"WORKTYPE": "", "STATUS": "", "DESCRIPTION": "text"})
        mapped, _ = map_cases([feature])
        assert mapped[0]["work_type"] is None
        assert mapped[0]["status"] is None


def test_epoch_ms_to_iso_none_passthrough():
    assert _epoch_ms_to_iso(None) is None


def test_is_usable_case():
    assert _is_usable_case({"TITLE": "t", "DESCRIPTION": None})
    assert _is_usable_case({"TITLE": None, "DESCRIPTION": "d"})
    assert not _is_usable_case({"TITLE": "", "DESCRIPTION": None})
    assert not _is_usable_case({})


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeSession:
    """Serves canned ArcGIS pages keyed by resultOffset."""

    def __init__(self, pages):
        self.pages = pages
        self.offsets_requested = []

    def get(self, url, params=None, timeout=None):
        offset = params["resultOffset"]
        self.offsets_requested.append(offset)
        return FakeResponse(self.pages[offset])


class TestDownloadCases:
    def test_paginates_until_transfer_limit_clear(self, monkeypatch):
        monkeypatch.setattr(pipeline, "ARCGIS_PAGE_SLEEP", 0)
        page_size = pipeline.ARCGIS_PAGE_SIZE
        session = FakeSession(
            {
                0: {"features": [{"id": 1}, {"id": 2}], "exceededTransferLimit": True},
                page_size: {"features": [{"id": 3}]},
            }
        )

        features = download_cases(session)

        assert session.offsets_requested == [0, page_size]
        assert features == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_stops_on_empty_page(self):
        session = FakeSession({0: {"features": []}})
        assert download_cases(session) == []

    def test_raises_on_arcgis_error_payload(self):
        # ArcGIS reports errors in a 200 response body, not an HTTP status
        session = FakeSession({0: {"error": {"code": 400, "message": "bad"}}})
        try:
            download_cases(session)
        except RuntimeError as e:
            assert "ArcGIS error" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


class GeocodeSession:
    """Fake LocationIQ session: serves a canned result, or an HTTP error."""

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        session = self

        class Response:
            status_code = 500 if session.fail else 200

            def raise_for_status(self):
                if session.fail:
                    raise requests.HTTPError("500 Server Error")

            def json(self):
                return {"display_name": "Somewhere", "address": {"county": "County Cork"}}

        return Response()


class TestSkipGeocoding:
    def test_placeholders_only_new_coords_and_satisfy_the_fk(self, tmp_path):
        db_path = tmp_path / "test.db"
        # a coord already geocoded for real must not be clobbered
        geocode_all(
            [{"rounded_lat": 51.9, "rounded_lon": -8.1}],
            "key",
            db_path=db_path,
            session=GeocodeSession(),
        )

        cases = [
            {"rounded_lat": 51.9, "rounded_lon": -8.1},  # already cached
            {"rounded_lat": 53.3, "rounded_lon": -6.2},  # new
        ]
        skip_geocoding(cases, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            rows = dict(
                conn.execute(
                    """SELECT rounded_lat, json_extract(raw_json, '$.geocode_failed')
                       FROM geocode_cache"""
                )
            )
        assert rows[51.9] is None  # real result untouched
        assert rows[53.3] == "geocode skipped"  # new coord gets a retryable placeholder


class TestGeocodeAll:
    def _cases(self):
        return [{"rounded_lat": 51.9, "rounded_lon": -8.1}]

    def test_single_failure_writes_placeholder_and_continues(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "LOCATIONIQ_GEOCODE_SLEEP", 0)
        db_path = tmp_path / "test.db"

        # one failing coord does not raise; it gets a placeholder row that
        # satisfies the cases FK
        geocode_all(self._cases(), "key", db_path=db_path, session=GeocodeSession(fail=True))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """SELECT county, json_extract(raw_json, '$.geocode_failed')
                   FROM geocode_cache"""
            ).fetchone()
        assert row[0] is None
        assert "500" in row[1]

    def test_placeholder_is_retried_and_replaced_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "LOCATIONIQ_GEOCODE_SLEEP", 0)
        db_path = tmp_path / "test.db"

        session = GeocodeSession(fail=True)
        geocode_all(self._cases(), "key", db_path=db_path, session=session)
        assert session.calls == 1

        # service recovers: the placeholder coord is retried, not skipped,
        # and the real result replaces the placeholder
        session.fail = False
        geocode_all(self._cases(), "key", db_path=db_path, session=session)
        assert session.calls == 2

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT county FROM geocode_cache").fetchall()
        assert rows == [("County Cork",)]

    def test_consecutive_failures_trip_the_circuit_breaker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "LOCATIONIQ_GEOCODE_SLEEP", 0)
        cases = [
            {"rounded_lat": 51.0 + i / 10, "rounded_lon": -8.1}
            for i in range(pipeline.GEOCODE_CIRCUIT_BREAKER)
        ]

        with pytest.raises(RuntimeError, match="looks down"):
            geocode_all(
                cases, "key", db_path=tmp_path / "test.db", session=GeocodeSession(fail=True)
            )

    def test_success_is_cached_and_not_refetched(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "LOCATIONIQ_GEOCODE_SLEEP", 0)
        db_path = tmp_path / "test.db"

        session = GeocodeSession()
        geocode_all(self._cases(), "key", db_path=db_path, session=session)
        assert session.calls == 1

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT rounded_lat, rounded_lon, county FROM geocode_cache"
            ).fetchone()
        assert row == (51.9, -8.1, "County Cork")

        # a second run resumes from the cache and makes no requests
        geocode_all(self._cases(), "key", db_path=db_path, session=session)
        assert session.calls == 1


class TestCategoryRulesTable:
    def test_no_variant_is_claimed_by_two_rules(self):
        # a variant listed under two rules would be silently masked by
        # _RULE_BY_VARIANT, so guard the whole table against it
        seen = {}
        for rule in CATEGORY_RULES:
            for variant in rule.variants:
                assert variant not in seen, (
                    f"{variant!r} is in both {seen.get(variant)} and {rule.slug}"
                )
                seen[variant] = rule.slug

    def test_slugs_are_unique(self):
        slugs = [rule.slug for rule in CATEGORY_RULES]
        assert len(slugs) == len(set(slugs))

    def test_variants_are_normalised(self):
        # variants are matched post-normalisation, so any un-normalised entry
        # (uppercase, padded, doubled spaces) is dead and can never match
        for rule in CATEGORY_RULES:
            for variant in rule.variants:
                assert variant == " ".join(variant.lower().split())

    def test_work_type_is_a_valid_policy(self):
        for rule in CATEGORY_RULES:
            assert rule.work_type in (None, "Planned", "Unplanned")

    def test_every_rule_is_reachable_via_classify(self):
        # a representative title per rule resolves back to that exact rule
        for rule in CATEGORY_RULES:
            title = f"{rule.variants[0].title()} – Cork"
            assert classify_category(title) is rule


class TestCategoryClassification:
    def test_classifies_known_categories_to_slugs(self):
        assert classify_category("Burst Water Main – Cork").slug == "burst_main"
        assert classify_category("Burst Water Mains - Kerry").slug == "burst_main"
        assert classify_category("Burst Main - Tipperary").slug == "burst_main"
        assert classify_category("Essential Works – Dublin").slug == "essential_works"
        assert classify_category("Essential Maintenance Works - Mayo").slug == "essential_works"
        assert classify_category("Leak Detection Works – Cork").slug == "leak_detection"
        assert classify_category("Leak Detection/Step Testing - Dublin").slug == "leak_detection"
        assert classify_category("Mains Flushing - Louth").slug == "mains_flushing"
        assert classify_category("Boil Water Notice – Mayo").slug == "boil_notice_issued"
        assert classify_category("Lifting of Boil Water Notice – Cork").slug == "boil_notice_lifted"
        assert classify_category("Lifting of The Boil Water Notice").slug == "boil_notice_lifted"
        assert classify_category("Valve Installation – Dublin").slug == "valve_installation"
        assert classify_category("Valve Installation Works - Cork").slug == "valve_installation"
        assert classify_category("Valve Repair Works– Roscommon").slug == "valve_repair"
        assert classify_category("Valve Repair – Dublin").slug == "valve_repair"
        assert classify_category("Valve Replacement Works – Kerry").slug == "valve_repair"
        assert classify_category("Step Testing Works – Cork").slug == "leak_detection"
        assert classify_category("Water Conservation Restrictions – X").slug == "water_conservation"
        assert classify_category("Hydrant Repair Works – Cork").slug == "hydrant_repair"
        assert classify_category("Hydrant Installation Works – Cork").slug == "hydrant_installation"
        assert classify_category("Meter Installation Works – Cork").slug == "meter_installation"
        assert classify_category("New Connection Works – Meath").slug == "new_connection"
        assert classify_category("Pump Station Interruption").slug == "pump_station_interruption"
        assert classify_category("Pump Failure – Cork").slug == "pump_failure"
        assert classify_category("Pump Repair Works – Cork").slug == "pump_repair"
        assert classify_category("Pump Installation Works – Cork").slug == "pump_installation"
        assert classify_category("Discolouration – Cork").slug == "discolouration"
        assert classify_category("Low Pressure – Cork").slug == "low_pressure"
        assert classify_category("Do Not Consume – Cork").slug == "consumption_notice_issued"
        assert classify_category("Do Not Consume Notice – Cork").slug == "consumption_notice_issued"
        assert classify_category("Investigation Works – Cork").slug == "investigation"
        assert classify_category("Under Investigation – Cork").slug == "investigation"
        assert classify_category("Mains Rehabilitation Works – Cork").slug == "mains_rehabilitation"
        assert classify_category("Mains Rehabilitation Works – Cork").work_type == "Planned"
        assert classify_category("Reservoir Interruption – Cork").slug == "reservoir_interruption"
        wtp = classify_category("Water Treatment Plant Interruption – Cork")
        assert wtp.slug == "water_treatment_plant_interruption"
        assert wtp.work_type == "Unplanned"

    def test_new_category_work_types(self):
        assert classify_category("Water Conservation – Mayo").work_type == "Unplanned"
        assert classify_category("Hydrant Repair Works – Cork").work_type == "Unplanned"
        assert classify_category("Pump Failure – Cork").work_type == "Unplanned"
        assert classify_category("Hydrant Installation Works – Cork").work_type == "Planned"
        assert classify_category("New Connection Works – Meath").work_type == "Planned"
        assert classify_category("Pump Installation Works – Cork").work_type == "Planned"

    def test_normalises_messy_dashes_and_spacing(self):
        assert classify_category("Burst Water Main- Cork").slug == "burst_main"  # no space
        assert classify_category("essential works –  dublin").slug == "essential_works"  # lower
        assert classify_category("  Mains Flushing – Kerry  ").slug == "mains_flushing"  # padded

    def test_returns_none_for_unknown_or_empty(self):
        assert classify_category("Meter Exchange Works – Cork") is None
        assert classify_category("Something Novel – Kerry") is None
        assert classify_category("unknown") is None
        assert classify_category(None) is None

    def test_slug_only_rules_carry_no_work_type(self):
        # category is clear but planned vs unplanned genuinely isn't
        for title in ("Mains Repair Works – Cork", "Power Outage – Dublin"):
            rule = classify_category(title)
            assert rule.work_type is None
        assert classify_category("Mains Repair Works – Cork").slug == "mains_repair"
        assert classify_category("Power Outage – Dublin").slug == "power_outage"

    def test_each_rule_forces_the_expected_work_type(self):
        assert classify_category("Burst Water Main – Cork").work_type == "Unplanned"
        assert classify_category("Essential Works – Dublin").work_type == "Planned"
        assert classify_category("Leak Detection Works – Cork").work_type == "Planned"
        assert classify_category("Mains Flushing - Louth").work_type == "Planned"
        assert classify_category("Boil Water Notice – Mayo").work_type == "Unplanned"
        assert classify_category("Lifting of Boil Water Notice – Cork").work_type == "Unplanned"
        assert classify_category("Valve Installation Works - Cork").work_type == "Planned"
        assert classify_category("Valve Repair Works– Roscommon").work_type == "Unplanned"


class TestWorkTypeBackfill:
    def test_backfill_overrides_rules_and_leaves_others_alone(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, title TEXT, work_type TEXT)")
        conn.executemany(
            "INSERT INTO cases VALUES (?, ?, ?)",
            [
                (1, "Burst Water Main – Cork", None),          # override fills the NULL
                (2, "Burst Water Main – Cork", "Planned"),     # override wins over the feed
                (3, "Essential Works – Dublin", "Unplanned"),  # override to Planned
                (4, "Mains Repair Works – Cork", None),        # slug-only rule: stays NULL
                (5, "Mains Repair Works – Cork", "Planned"),   # slug-only rule: feed kept
                (6, "Something Novel – Kerry", "Unplanned"),   # no rule: untouched
            ],
        )

        overridden = backfill_work_type(conn)

        assert overridden == 3
        rows = dict(conn.execute("SELECT id, work_type FROM cases"))
        assert rows == {
            1: "Unplanned",
            2: "Unplanned",
            3: "Planned",
            4: None,
            5: "Planned",
            6: "Unplanned",
        }

    def test_backfill_work_category_sets_slug_for_known_categories(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE cases (id INTEGER PRIMARY KEY, title TEXT, work_category TEXT)"
        )
        conn.executemany(
            "INSERT INTO cases VALUES (?, ?, ?)",
            [
                (1, "Burst Water Main – Cork", None),
                (2, "Leak Detection/Step Testing - Dublin", None),
                (3, "Mains Flushing - Louth", None),
                (4, "Something Novel – Kerry", None),
            ],
        )

        count = backfill_work_category(conn)

        assert count == 3
        rows = dict(conn.execute("SELECT id, work_category FROM cases"))
        assert rows == {1: "burst_main", 2: "leak_detection", 3: "mains_flushing", 4: None}


def _v1_cases_db(db_path):
    """A DB carrying the full declared v1 `cases` schema, as create_db writes it."""
    cols = ", ".join(
        f"{c} TEXT" if c != "id" else "id INTEGER PRIMARY KEY"
        for c in pipeline.DB_CASE_COLUMNS
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"CREATE TABLE cases ({cols}, work_category TEXT, first_seen TEXT, last_seen TEXT)"
        )
        conn.execute(f"PRAGMA user_version = {pipeline.SCHEMA_VERSION}")


def test_backfill_runs_standalone_on_existing_db(tmp_path):
    db_path = tmp_path / "test.db"
    _v1_cases_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO cases (id, work_type, status, title) VALUES (?, ?, ?, ?)",
            [
                (1, "Planned", "Open", "  Burst Water Main – Cork  "),  # override + trim
                (2, "", "Open", "Mains Flushing – Kerry"),  # override a blank
                (3, None, "Open", "Something Novel – Kerry"),  # left alone
            ],
        )

    backfill(db_path=db_path)  # no network, adds the column and derives

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, work_type, work_category FROM cases ORDER BY id"
        ).fetchall()
    assert rows == [
        (1, "Burst Water Main – Cork", "Unplanned", "burst_main"),
        (2, "Mains Flushing – Kerry", "Planned", "mains_flushing"),
        (3, "Something Novel – Kerry", None, None),
    ]


def test_create_db_builds_a_fresh_db_from_scratch(tmp_path):
    """The declared CREATE TABLE must actually execute. CI and most local runs
    start from a downloaded release DB, so IF NOT EXISTS normally no-ops and a
    defect in the declaration itself goes unnoticed — a duplicate column name
    once shipped that way, breaking only the from-scratch path in the README."""
    db_path = tmp_path / "fresh.db"
    case = {col: None for col in pipeline.DB_CASE_COLUMNS} | {
        "id": 1,
        "title": "Burst Water Main – Cork",
        "full_lat": 51.9,
        "full_lon": -8.5,
        "rounded_lat": 51.9,
        "rounded_lon": -8.5,
    }

    # mirrors run(skip_geocode=True): geocode rows first (the cases FK), then the DB
    skip_geocoding([case], db_path=db_path)
    pipeline.create_db([case], db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(cases)")]
        assert sorted(cols) == sorted(pipeline.REQUIRED_CASE_COLUMNS)
        assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
        assert conn.execute("PRAGMA user_version").fetchone()[0] == pipeline.SCHEMA_VERSION


class TestSchemaVersion:
    """The schema is declared once and never migrated; check_schema_version is
    the whole compatibility story, so its three outcomes are pinned here."""

    def test_stamped_current_version_passes(self, tmp_path):
        db_path = tmp_path / "v1.db"
        _v1_cases_db(db_path)
        with sqlite3.connect(db_path) as conn:
            pipeline.check_schema_version(conn, db_path)  # no raise

    def test_unstamped_but_structurally_current_db_is_stamped_in_place(self, tmp_path):
        # DBs built before versioning began read as v0 but already carry every
        # declared column; they are adopted rather than rejected.
        db_path = tmp_path / "v0.db"
        _v1_cases_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA user_version = 0")
        with sqlite3.connect(db_path) as conn:
            pipeline.check_schema_version(conn, db_path)
            assert conn.execute("PRAGMA user_version").fetchone()[0] == pipeline.SCHEMA_VERSION

    def test_genuinely_older_db_is_rejected_not_migrated(self, tmp_path):
        db_path = tmp_path / "old.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, title TEXT)")
        with sqlite3.connect(db_path) as conn:
            with pytest.raises(RuntimeError, match="does not migrate"):
                pipeline.check_schema_version(conn, db_path)

    def test_newer_db_is_rejected(self, tmp_path):
        db_path = tmp_path / "future.db"
        _v1_cases_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute(f"PRAGMA user_version = {pipeline.SCHEMA_VERSION + 1}")
        with sqlite3.connect(db_path) as conn:
            with pytest.raises(RuntimeError, match="Update the package"):
                pipeline.check_schema_version(conn, db_path)


def test_trim_titles():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany(
        "INSERT INTO cases VALUES (?, ?)",
        [(1, "  Burst Water Main – Cork  "), (2, "Clean Title"), (3, "unknown")],
    )

    trim_titles(conn)

    rows = conn.execute("SELECT id, title FROM cases ORDER BY id").fetchall()
    assert rows == [(1, "Burst Water Main – Cork"), (2, "Clean Title"), (3, "unknown")]


def test_normalise_legacy_empty_strings():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, work_type TEXT, status TEXT)")
    conn.executemany(
        "INSERT INTO cases VALUES (?, ?, ?)",
        [(1, "", ""), (2, "Planned", "Open"), (3, None, None)],
    )

    normalise_legacy_empty_strings(conn)

    rows = conn.execute("SELECT work_type, status FROM cases ORDER BY id").fetchall()
    assert rows == [(None, None), ("Planned", "Open"), (None, None)]


def test_geocode_cache_row_flattens_address():
    result = {
        "display_name": "Somewhere, Cork, Ireland",
        "address": {"road": "Main St", "town": "Midleton", "county": "County Cork"},
    }
    row = geocode_cache_row(51.9, -8.1, result)

    assert row[0:3] == (51.9, -8.1, "Somewhere, Cork, Ireland")
    assert row[3] == "Main St"  # road
    assert row[4] == "Midleton"  # town
    assert row[9] == "County Cork"  # county
    assert json.loads(row[-1]) == result  # raw_json round-trips


class TestLoadCasesSeenStamps:
    def _conn(self):
        conn = sqlite3.connect(":memory:")
        cols = ", ".join(f"{c} TEXT" if c != "id" else "id INTEGER PRIMARY KEY"
                         for c in pipeline.DB_CASE_COLUMNS)
        conn.execute(f"CREATE TABLE cases ({cols}, first_seen TEXT, last_seen TEXT)")
        return conn

    def _record(self, **overrides):
        record = dict.fromkeys(pipeline.DB_CASE_COLUMNS)
        record.update({"id": 1, "title": "Burst Water Main – Cork", "status": "Open"})
        record.update(overrides)
        return record

    def test_fresh_insert_stamps_first_and_last_seen(self):
        conn = self._conn()
        pipeline.load_cases(conn, [self._record()], now="2026-07-01T00:00:00+00:00")
        row = conn.execute("SELECT first_seen, last_seen FROM cases").fetchone()
        assert row == ("2026-07-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00")

    def test_reload_advances_last_seen_but_preserves_first_seen(self):
        conn = self._conn()
        pipeline.load_cases(conn, [self._record()], now="2026-07-01T00:00:00+00:00")
        pipeline.load_cases(conn, [self._record(status="Closed")],
                            now="2026-07-08T00:00:00+00:00")
        row = conn.execute("SELECT first_seen, last_seen, status FROM cases").fetchone()
        assert row == ("2026-07-01T00:00:00+00:00", "2026-07-08T00:00:00+00:00", "Closed")

    def test_case_absent_from_download_keeps_stale_last_seen(self):
        conn = self._conn()
        pipeline.load_cases(conn, [self._record(), self._record(id=2)],
                            now="2026-07-01T00:00:00+00:00")
        pipeline.load_cases(conn, [self._record()], now="2026-07-08T00:00:00+00:00")
        stale = conn.execute("SELECT last_seen FROM cases WHERE id = 2").fetchone()
        assert stale == ("2026-07-01T00:00:00+00:00",)
