import json
import sqlite3

import pytest

from uisce.inference import (
    MODEL_NAME,
    PROMPT_VERSION,
    build_record,
    get_cases_needing_inference,
    get_last_hash_by_case_id,
    hash_description,
    parse_response,
)


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


class TestGetLastHashByCaseId:
    def test_missing_file_means_nothing_inferred(self, tmp_path):
        assert get_last_hash_by_case_id(tmp_path / "nope.jsonl") == {}

    def test_latest_record_wins_per_case(self, tmp_path):
        jsonl = tmp_path / "inferred.jsonl"
        def record(case_id, inferred_at, description_hash):
            return {
                "case_id": case_id,
                "inferred_at": inferred_at,
                "description_hash": description_hash,
                "prompt_version": PROMPT_VERSION,
            }

        write_jsonl(
            jsonl,
            [
                record(1, "2026-06-01T00:00:00+00:00", "old"),
                record(1, "2026-07-01T00:00:00+00:00", "new"),
                record(2, "2026-06-01T00:00:00+00:00", "only"),
            ],
        )
        assert get_last_hash_by_case_id(jsonl) == {
            1: ("new", PROMPT_VERSION),
            2: ("only", PROMPT_VERSION),
        }

    def test_blank_lines_are_skipped(self, tmp_path):
        jsonl = tmp_path / "inferred.jsonl"
        record = {
            "case_id": 1,
            "inferred_at": "2026-06-01T00:00:00+00:00",
            "description_hash": "h",
            "prompt_version": PROMPT_VERSION,
        }
        jsonl.write_text("\n" + json.dumps(record) + "\n\n")
        assert get_last_hash_by_case_id(jsonl) == {1: ("h", PROMPT_VERSION)}

    def test_records_predating_prompt_version_read_as_none(self, tmp_path):
        jsonl = tmp_path / "inferred.jsonl"
        write_jsonl(
            jsonl,
            [{"case_id": 1, "inferred_at": "2026-06-01T00:00:00+00:00", "description_hash": "h"}],
        )
        assert get_last_hash_by_case_id(jsonl) == {1: ("h", None)}


class TestGetCasesNeedingInference:
    def _make_db(self, tmp_path, rows):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE cases (id INTEGER PRIMARY KEY, start_date TEXT, description TEXT)"
        )
        conn.executemany("INSERT INTO cases VALUES (?, ?, ?)", rows)
        conn.commit()
        conn.close()
        return db

    def test_selects_new_and_changed_skips_unchanged_and_null(self, tmp_path):
        db = self._make_db(
            tmp_path,
            [
                (1, "2026-06-01", "unchanged text"),
                (2, "2026-06-01", "changed text"),
                (3, "2026-06-01", "never inferred"),
                (4, "2026-06-01", None),
            ],
        )
        last_state = {
            1: (hash_description("unchanged text"), PROMPT_VERSION),
            2: (hash_description("previous version of text"), PROMPT_VERSION),
        }

        cases = get_cases_needing_inference(db, last_state)

        assert [c["id"] for c in cases] == [2, 3]

    def test_prompt_version_bump_reinfers_unchanged_descriptions(self, tmp_path):
        """A prompt edit must re-infer the corpus; keying on the hash alone re-inferred nothing."""
        db = self._make_db(tmp_path, [(1, "2026-06-01", "unchanged text")])
        stale = {1: (hash_description("unchanged text"), PROMPT_VERSION - 1)}

        assert [c["id"] for c in get_cases_needing_inference(db, stale)] == [1]

    def test_force_reinfers_everything(self, tmp_path):
        db = self._make_db(tmp_path, [(1, "2026-06-01", "unchanged text")])
        current = {1: (hash_description("unchanged text"), PROMPT_VERSION)}

        assert get_cases_needing_inference(db, current) == []
        assert [c["id"] for c in get_cases_needing_inference(db, current, force=True)] == [1]


def test_build_record_shape():
    result = {
        "notes": "found it",
        "end_source": "completion_update",
        "local_date": "2026-04-28",
        "local_time": "16:13",
    }
    record = build_record(
        7, "desc text", "2026-04-28T00:00:00+00:00", result, inferred_at="2026-05-01T00:00:00+00:00"
    )

    assert record == {
        "case_id": 7,
        "description_hash": hash_description("desc text"),
        "start_date": "2026-04-28T00:00:00+00:00",
        "model": MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
        "notes": "found it",
        "end_source": "completion_update",
        "local_date": "2026-04-28",
        "local_time": "16:13",
        "inferred_at": "2026-05-01T00:00:00+00:00",
    }


class TestParseResponse:
    def test_parses_object(self):
        assert parse_response('{"end_source": "not_found"}') == {"end_source": "not_found"}

    @pytest.mark.parametrize("bad", ["null", "[1, 2]", '"just a string"'])
    def test_rejects_non_object_json(self, bad):
        with pytest.raises(ValueError):
            parse_response(bad)

    def test_rejects_markdown_fences(self):
        with pytest.raises(json.JSONDecodeError):
            parse_response('```json\n{"end_source": "not_found"}\n```')
