from datetime import date

from uisce.eval_end_time import draw_sample, draw_uniform, round_filename


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


def make_case(case_id, description=None):
    return {"id": case_id, "description": description or f"desc-{case_id}"}


class TestDrawUniform:
    def test_dedups_by_description(self):
        rows = [make_case(1, "same"), make_case(2, "same"), make_case(3)]
        picked = draw_uniform(rows, 10, seed=1, hash_of=hash)
        assert sorted(r["id"] for r in picked) in ([1, 3], [2, 3])

    def test_excludes_previously_sampled_case_ids(self):
        rows = [make_case(i) for i in range(1, 6)]
        picked = draw_uniform(rows, 10, seed=1, exclude_ids={2, 4}, hash_of=hash)
        assert sorted(r["id"] for r in picked) == [1, 3, 5]

    def test_size_caps_the_draw(self):
        rows = [make_case(i) for i in range(20)]
        assert len(draw_uniform(rows, 5, seed=1, hash_of=hash)) == 5

    def test_draw_is_seeded_and_reproducible(self):
        rows = [make_case(i) for i in range(20)]
        a = [r["id"] for r in draw_uniform(rows, 5, seed=7, hash_of=hash)]
        b = [r["id"] for r in draw_uniform(rows, 5, seed=7, hash_of=hash)]
        assert a == b

    def test_smaller_pool_than_requested_returns_what_there_is(self):
        rows = [make_case(i) for i in range(3)]
        assert len(draw_uniform(rows, 50, seed=1, hash_of=hash)) == 3


class TestRoundFilename:
    def test_single_model_and_version(self):
        name = round_filename(date(2026, 7, 18), {"gemma-4-12b-qat"}, {1})
        assert name == "end_time_sample_2026-07-18_gemma-4-12b-qat_pv1.csv"

    def test_mixed_provenance_is_flagged(self):
        name = round_filename(date(2026, 7, 18), {"gemma", "qwen"}, {1, 2})
        assert name == "end_time_sample_2026-07-18_mixed_pvmixed.csv"
