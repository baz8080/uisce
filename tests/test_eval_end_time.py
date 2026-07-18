from datetime import date

from uisce.eval_end_time import draw_sample, round_filename


def make_row(case_id, source, desc_hash=None):
    return {
        "case_id": case_id,
        "end_source": source,
        "end_description_hash": desc_hash or f"hash-{case_id}",
    }


class TestDrawSample:
    def test_dedups_by_description_hash(self):
        rows = [
            make_row(1, "not_found", "same"),
            make_row(2, "not_found", "same"),
            make_row(3, "not_found"),
        ]
        picked = draw_sample(rows, {"not_found": 10}, seed=1)
        assert [r["case_id"] for r in picked] in ([1, 3], [3, 1])

    def test_excludes_previously_sampled_case_ids(self):
        rows = [make_row(i, "not_found") for i in range(1, 6)]
        picked = draw_sample(rows, {"not_found": 10}, seed=1, exclude_ids={2, 4})
        assert sorted(r["case_id"] for r in picked) == [1, 3, 5]

    def test_excluded_case_does_not_shadow_shared_hash(self):
        rows = [
            make_row(1, "not_found", "same"),
            make_row(2, "not_found", "same"),
        ]
        picked = draw_sample(rows, {"not_found": 10}, seed=1, exclude_ids={1})
        assert [r["case_id"] for r in picked] == [2]

    def test_quota_limits_class_size(self):
        rows = [make_row(i, "not_found") for i in range(10)]
        picked = draw_sample(rows, {"not_found": 3}, seed=1)
        assert len(picked) == 3


class TestRoundFilename:
    def test_single_model_and_version(self):
        name = round_filename(date(2026, 7, 18), {"gemma-4-12b-qat"}, {1})
        assert name == "end_time_sample_2026-07-18_gemma-4-12b-qat_pv1.csv"

    def test_mixed_provenance_is_flagged(self):
        name = round_filename(date(2026, 7, 18), {"gemma", "qwen"}, {1, 2})
        assert name == "end_time_sample_2026-07-18_mixed_pvmixed.csv"
