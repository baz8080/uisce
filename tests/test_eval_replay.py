from uisce.eval_replay import matches, normalise_time, truth_for


def row(**overrides):
    base = {
        "model_end_source": "completion_update",
        "model_local_date": "2026-05-18",
        "model_local_time": "20:00",
        "human_verdict": "correct",
        "human_end_source": "",
        "human_local_date": "",
        "human_local_time": "",
    }
    return base | overrides


class TestTruthFor:
    def test_correct_row_endorses_the_models_own_answer(self):
        assert truth_for(row()) == ("completion_update", "2026-05-18", "20:00")

    def test_incorrect_row_uses_the_human_correction(self):
        got = truth_for(row(
            human_verdict="incorrect",
            human_end_source="scheduled_end_with_time",
            human_local_date="2026-08-17",
            human_local_time="08:00",
        ))
        assert got == ("scheduled_end_with_time", "2026-08-17", "08:00")

    def test_incorrect_row_keeps_model_class_when_human_left_it_blank(self):
        """Round 1's labeller left human_end_source empty when only the time was wrong."""
        got = truth_for(row(human_verdict="incorrect", human_local_time="09:28"))
        assert got == ("completion_update", "", "09:28")

    def test_verdict_matching_ignores_case_and_padding(self):
        got = truth_for(row(human_verdict="  Incorrect  ", human_local_date="2026-01-01"))
        assert got[1] == "2026-01-01"


class TestNormaliseTime:
    def test_seconds_are_dropped_so_labels_compare_at_minute_precision(self):
        assert normalise_time("17:02:52") == "17:02"

    def test_plain_times_and_blanks_pass_through(self):
        assert normalise_time("08:00") == "08:00"
        assert normalise_time("") == ""
        assert normalise_time(None) == ""


def test_matches_is_an_all_three_fields_comparison():
    truth = ("completion_update", "2026-05-18", "09:28")
    assert matches(truth, ("completion_update", "2026-05-18", "09:28"))
    assert not matches(truth, ("completion_update", "2026-05-18", "20:00"))
    assert not matches(truth, ("scheduled_end_with_time", "2026-05-18", "09:28"))
