import json
import sqlite3

import pytest

from uisce import inference
from uisce.inference import (
    MODEL_NAME,
    PROMPT_VERSION,
    build_record,
    get_cases_needing_inference,
    get_last_hash_by_case_id,
    hash_description,
    parse_response,
)
from uisce.rules import RULES_VERSION


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
                "model": MODEL_NAME,
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
            1: ("new", PROMPT_VERSION, MODEL_NAME),
            2: ("only", PROMPT_VERSION, MODEL_NAME),
        }

    def test_blank_lines_are_skipped(self, tmp_path):
        jsonl = tmp_path / "inferred.jsonl"
        record = {
            "case_id": 1,
            "inferred_at": "2026-06-01T00:00:00+00:00",
            "description_hash": "h",
            "prompt_version": PROMPT_VERSION,
            "model": MODEL_NAME,
        }
        jsonl.write_text("\n" + json.dumps(record) + "\n\n")
        assert get_last_hash_by_case_id(jsonl) == {1: ("h", PROMPT_VERSION, MODEL_NAME)}

    def test_records_predating_prompt_version_read_as_none(self, tmp_path):
        jsonl = tmp_path / "inferred.jsonl"
        write_jsonl(
            jsonl,
            [{"case_id": 1, "inferred_at": "2026-06-01T00:00:00+00:00", "description_hash": "h"}],
        )
        assert get_last_hash_by_case_id(jsonl) == {1: ("h", None, None)}


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
            1: (hash_description("unchanged text"), PROMPT_VERSION, MODEL_NAME),
            2: (hash_description("previous version of text"), PROMPT_VERSION, MODEL_NAME),
        }

        cases = get_cases_needing_inference(db, last_state)

        assert [c["id"] for c in cases] == [2, 3]

    def test_prompt_version_bump_reinfers_unchanged_descriptions(self, tmp_path):
        """A prompt edit must re-infer the corpus; keying on the hash alone re-inferred nothing."""
        db = self._make_db(tmp_path, [(1, "2026-06-01", "unchanged text")])
        stale = {1: (hash_description("unchanged text"), PROMPT_VERSION - 1, MODEL_NAME)}

        assert [c["id"] for c in get_cases_needing_inference(db, stale)] == [1]

    def test_rules_version_bump_reselects_only_rules_cases(self, tmp_path):
        """Bumping RULES_VERSION re-runs the rules-produced cases and leaves the
        LLM's alone — the model in the record is part of the staleness key."""
        db = self._make_db(
            tmp_path,
            [(1, "2026-06-01", "rules text"), (2, "2026-06-01", "llm text")],
        )
        state = {
            1: (hash_description("rules text"), PROMPT_VERSION, "rules-v0"),
            2: (hash_description("llm text"), PROMPT_VERSION, MODEL_NAME),
        }

        assert [c["id"] for c in get_cases_needing_inference(db, state)] == [1]

    def test_current_rules_records_are_current(self, tmp_path):
        db = self._make_db(tmp_path, [(1, "2026-06-01", "rules text")])
        state = {1: (hash_description("rules text"), PROMPT_VERSION, RULES_VERSION)}

        assert get_cases_needing_inference(db, state) == []

    def test_force_reinfers_everything(self, tmp_path):
        db = self._make_db(tmp_path, [(1, "2026-06-01", "unchanged text")])
        current = {1: (hash_description("unchanged text"), PROMPT_VERSION, MODEL_NAME)}

        assert get_cases_needing_inference(db, current) == []
        assert [c["id"] for c in get_cases_needing_inference(db, current, force=True)] == [1]


def test_build_record_shape():
    result = {
        "notes": "found it",
        "end_source": "completion_update",
        "local_date": "2026-04-28",
        "local_time": "16:13",
        "recurrence": "none",
        "window_open": None,
        "window_close": None,
        "window_first_date": None,
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
        "recurrence": "none",
        "window_open": None,
        "window_close": None,
        "window_first_date": None,
        "inferred_at": "2026-05-01T00:00:00+00:00",
    }


def test_build_record_stamps_the_extractor_that_answered():
    record = build_record(7, "desc", "2026-04-28T00:00:00+00:00",
                          {"end_source": "completion_update"}, model=RULES_VERSION)

    assert record["model"] == RULES_VERSION
    # prompt_version is stamped regardless: it names the semantics the rules
    # mirror, and it keeps the PROMPT_VERSION-bump re-run covering everything.
    assert record["prompt_version"] == PROMPT_VERSION


def test_a_model_reply_missing_the_window_fields_still_builds_a_record():
    """The v3 fields are read with .get(), so a reply that omits them — an older
    model, a truncated response — yields NULLs rather than crashing the run. NULL
    recurrence reads as "not recurring" and the case behaves as it always did."""
    record = build_record(7, "desc", "2026-04-28T00:00:00+00:00", {"end_source": "not_found"})

    assert record["recurrence"] is None
    assert record["window_open"] is None


class TestHybridRun:
    """run() is rules first, LLM fallback (notes/rules-vs-llm-end-times.md)."""

    TEMPLATED = ("**Update 10:15am 18/05/2026** Works are now complete and supply "
                 "should have returned to all the affected areas.")
    UNTEMPLATED = "We are investigating reports of supply disruptions."

    def _wire(self, tmp_path, monkeypatch, rows):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE cases (id INTEGER PRIMARY KEY, start_date TEXT, description TEXT)"
        )
        conn.executemany("INSERT INTO cases VALUES (?, ?, ?)", rows)
        conn.commit()
        conn.close()
        jsonl = tmp_path / "inferred.jsonl"
        monkeypatch.setattr(inference, "DB_PATH", db)
        monkeypatch.setattr(inference, "JSONL_PATH", jsonl)
        return jsonl

    def test_rules_covered_run_never_touches_the_llm(self, tmp_path, monkeypatch):
        jsonl = self._wire(
            tmp_path, monkeypatch, [(1, "2026-05-18T08:00:00+00:00", self.TEMPLATED)]
        )

        def no_session():
            raise AssertionError("a fully rules-covered run must not open a session")

        monkeypatch.setattr(inference, "make_session", no_session)
        inference.run([])

        [record] = [json.loads(line) for line in jsonl.read_text().splitlines()]
        assert record["model"] == RULES_VERSION
        assert record["prompt_version"] == PROMPT_VERSION
        assert record["end_source"] == "completion_update"
        assert (record["local_date"], record["local_time"]) == ("2026-05-18", "10:15")

    def test_rules_only_skips_abstentions_without_touching_the_llm(
        self, tmp_path, monkeypatch, capsys
    ):
        jsonl = self._wire(
            tmp_path, monkeypatch,
            [(1, "2026-05-18T08:00:00+00:00", self.TEMPLATED),
             (2, "2026-05-18T08:00:00+00:00", self.UNTEMPLATED)],
        )

        def no_session():
            raise AssertionError("--rules-only must never open a session")

        monkeypatch.setattr(inference, "make_session", no_session)
        inference.run(["--rules-only"])

        [record] = [json.loads(line) for line in jsonl.read_text().splitlines()]
        assert (record["case_id"], record["model"]) == (1, RULES_VERSION)
        assert "1 left for the LLM" in capsys.readouterr().out

    def test_abstention_falls_back_to_the_llm(self, tmp_path, monkeypatch):
        jsonl = self._wire(
            tmp_path, monkeypatch, [(1, "2026-05-18T08:00:00+00:00", self.UNTEMPLATED)]
        )
        monkeypatch.setattr(inference, "make_session", lambda: object())
        monkeypatch.setattr(
            inference, "call_llm",
            lambda session, start_date, description: '{"end_source": "not_found"}',
        )
        inference.run([])

        [record] = [json.loads(line) for line in jsonl.read_text().splitlines()]
        assert record["model"] == MODEL_NAME
        assert record["end_source"] == "not_found"

    def test_a_failed_case_is_counted_and_the_run_exits_non_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        jsonl = self._wire(
            tmp_path, monkeypatch, [(1, "2026-05-18T08:00:00+00:00", self.UNTEMPLATED)]
        )
        monkeypatch.setattr(inference, "make_session", lambda: object())

        def failing_llm(session, start_date, description):
            raise ValueError("response truncated")

        monkeypatch.setattr(inference, "call_llm", failing_llm)

        assert inference.run([]) == 1
        assert "1 failed" in capsys.readouterr().out
        assert jsonl.read_text() == ""

    def test_a_clean_run_exits_zero(self, tmp_path, monkeypatch):
        self._wire(tmp_path, monkeypatch, [(1, "2026-05-18T08:00:00+00:00", self.TEMPLATED)])
        assert inference.run([]) == 0

    def test_multi_pin_dedupe_still_extracts_once(self, tmp_path, monkeypatch):
        jsonl = self._wire(
            tmp_path, monkeypatch,
            [(1, "2026-05-18T08:00:00+00:00", self.UNTEMPLATED),
             (2, "2026-05-18T08:00:00+00:00", self.UNTEMPLATED)],
        )
        calls = []
        monkeypatch.setattr(inference, "make_session", lambda: object())

        def counting_llm(session, start_date, description):
            calls.append(description)
            return '{"end_source": "not_found"}'

        monkeypatch.setattr(inference, "call_llm", counting_llm)
        inference.run([])

        records = [json.loads(line) for line in jsonl.read_text().splitlines()]
        assert [r["case_id"] for r in records] == [1, 2]
        assert len(calls) == 1


class TestCallLlm:
    class FakeSession:
        def __init__(self, body):
            self.body = body

        def post(self, url, json, timeout):
            body = self.body

            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return body

            return Response()

    def _body(self, finish_reason, content):
        return {
            "choices": [{"finish_reason": finish_reason,
                         "message": {"content": content}}],
            "usage": {"prompt_tokens": 4018, "completion_tokens": 78},
        }

    def test_returns_the_content_when_the_model_stopped_on_its_own(self):
        session = self.FakeSession(self._body("stop", '{"end_source": "not_found"}'))
        assert inference.call_llm(session, "2026-05-18T08:00:00+00:00", "notice") == (
            '{"end_source": "not_found"}'
        )

    def test_truncation_is_named_rather_than_left_to_json(self):
        session = self.FakeSession(self._body("length", '{"notes":"half a sen'))
        with pytest.raises(ValueError, match="truncated"):
            inference.call_llm(session, "2026-05-18T08:00:00+00:00", "notice")


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
