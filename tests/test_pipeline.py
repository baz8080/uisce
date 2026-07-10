import json
import sqlite3

import pytest
import requests

from uisce import pipeline
from uisce.pipeline import (
    _epoch_ms_to_iso,
    _is_usable_case,
    backfill_work_type,
    download_cases,
    geocode_all,
    geocode_cache_row,
    infer_work_type,
    map_cases,
    normalise_legacy_empty_strings,
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


class TestWorkTypeBackfill:
    def test_infer_work_type_known_categories(self):
        assert infer_work_type("Burst Water Main – Cork") == "Unplanned"
        assert infer_work_type("Burst Water Main - Cork") == "Unplanned"  # hyphen variant
        assert infer_work_type("Mains Rehabilitation Works – Dublin") == "Planned"

    def test_infer_work_type_handles_messy_titles_from_real_data(self):
        assert infer_work_type("investigation Works - Tipperary") == "Unplanned"  # lowercase
        assert infer_work_type("Valve Repair Works– Roscommon") == "Unplanned"  # no space
        assert infer_work_type("Burst Water Main- Cork") == "Unplanned"  # no space, hyphen
        assert infer_work_type("Reservoir interruption  - Cork") == "Unplanned"  # double space
        assert infer_work_type("Burst Main - Tipperary") == "Unplanned"  # abbreviation
        assert infer_work_type("Valve Repair – Dublin") == "Unplanned"  # abbreviation

    def test_infer_work_type_leaves_ambiguous_and_unknown_alone(self):
        assert infer_work_type("Essential Works – Dublin") is None  # 64/36 split in feed
        assert infer_work_type("Mains Repair Works – Cork") is None
        assert infer_work_type("Something Novel – Kerry") is None
        assert infer_work_type("unknown") is None
        assert infer_work_type(None) is None

    def test_backfill_fills_missing_and_preserves_feed_values(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, title TEXT, work_type TEXT)")
        conn.executemany(
            "INSERT INTO cases VALUES (?, ?, ?)",
            [
                (1, "Burst Water Main – Cork", None),
                (2, "Burst Water Main – Cork", "Planned"),  # feed value wins, however odd
                (3, "Essential Works – Dublin", None),
                (4, "New Connection Works – Meath", ""),
            ],
        )

        filled = backfill_work_type(conn)

        assert filled == 2
        rows = dict(conn.execute("SELECT id, work_type FROM cases"))
        assert rows == {1: "Unplanned", 2: "Planned", 3: None, 4: "Planned"}


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
