import pytest

from uisce.eval_prompt_layout import payload_for, split_payload, summarise
from uisce.inference import PROMPT, build_payload

START = "2026-05-18T08:00:00+00:00"
NOTICE = "Works are now complete at 4:13pm on 28/04/2026"


class TestSplitPayload:
    def test_control_is_the_production_payload(self):
        assert payload_for("user", START, NOTICE) == build_payload(START, NOTICE)

    def test_split_moves_the_prompt_into_a_system_message(self):
        messages = payload_for("split", START, NOTICE)["messages"]
        assert messages == [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"start_date: {START}\ndescription: {NOTICE}"},
        ]

    def test_split_changes_nothing_but_the_messages(self):
        control = build_payload(START, NOTICE)
        split = payload_for("split", START, NOTICE)
        assert split | {"messages": None} == control | {"messages": None}

    def test_a_payload_that_is_not_the_prompt_cannot_be_split(self):
        payload = build_payload(START, NOTICE)
        payload["messages"][0]["content"] = "something else"
        with pytest.raises(ValueError, match="cannot be split"):
            split_payload(payload)


class TestSummarise:
    def record(self, layout, seconds, verdict="match", case_id="1", rnd=0):
        return {
            "round": rnd, "layout": layout, "case_id": case_id, "seconds": seconds,
            "prompt_tokens": 3000, "completion_tokens": 100, "verdict": verdict,
            "answer": ("a", "b", "c"), "error": "",
        }

    def test_pairs_the_same_case_across_layouts(self, capsys):
        summarise([self.record("user", 2.0), self.record("split", 1.5)])
        out = capsys.readouterr().out
        assert "Paired over 1 cases (1 pairs)" in out
        assert "mean -0.50" in out

    def test_a_case_repeated_across_rounds_counts_once(self, capsys):
        summarise([
            self.record("user", 2.0, rnd=0), self.record("split", 1.0, rnd=0),
            self.record("user", 2.0, rnd=1), self.record("split", 1.0, rnd=1),
        ])
        assert "Paired over 1 cases (2 pairs)" in capsys.readouterr().out

    def test_reports_when_no_case_was_answered_under_both(self, capsys):
        summarise([self.record("user", 2.0)])
        assert "nothing to compare" in capsys.readouterr().out
