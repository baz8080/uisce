import csv

from uisce.eval_recurrence import FIELDNAMES, plain, score, unique_review_path


class TestPlain:
    def test_strips_markup_and_collapses_whitespace(self):
        assert plain("<p>Works  are<br><br>complete</p>") == "Works are complete"
        assert plain(None) == ""


class TestScore:
    def _file(self, tmp_path, rows, fieldnames=FIELDNAMES):
        path = tmp_path / "recurrence_review_2026-08-02.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fieldnames})
        return path

    def _row(self, **kw):
        base = {"case_id": 1, "reference_num": "CAR1", "county": "Carlow", "hours": 1000,
                "effect": "downgraded to restriction", "human_verdict": ""}
        return base | kw

    def test_reports_nothing_labelled(self, tmp_path, capsys):
        path = self._file(tmp_path, [self._row()])
        score(["--csv", str(path)])
        assert "Nothing labelled yet" in capsys.readouterr().out

    def test_counts_verdicts_and_names_the_calls_to_fix(self, tmp_path, capsys):
        path = self._file(tmp_path, [
            self._row(case_id=1, reference_num="CAR1", human_verdict="correct", hours=1000),
            self._row(case_id=2, reference_num="CAR2", human_verdict="wrong", hours=500,
                      human_notes="one continuous period, not a repeat"),
        ])
        score(["--csv", str(path)])
        out = capsys.readouterr().out
        assert "2 of 2 row(s) reviewed" in out
        assert "CAR2" in out and "one continuous period" in out
        assert "CAR1" not in out.split("Calls to fix:")[1]

    def test_reports_what_is_still_unreviewed_and_what_it_is_worth(self, tmp_path, capsys):
        path = self._file(tmp_path, [
            self._row(case_id=1, human_verdict="correct", hours=1000),
            self._row(case_id=2, hours=750),
        ])
        score(["--csv", str(path)])
        out = capsys.readouterr().out
        assert "1 of 2 row(s) reviewed" in out
        assert "1 row(s) left, 750 hours unreviewed" in out

    def test_a_review_written_before_2026_10_06_is_read_in_person_hours(self, tmp_path, capsys):
        old = [k if k != "hours" else "person_h" for k in FIELDNAMES]
        path = self._file(tmp_path, [
            {"case_id": 1, "human_verdict": "correct", "person_h": 1000},
            {"case_id": 2, "person_h": 750},
        ], old)
        score(["--csv", str(path)])
        assert "1 row(s) left, 750 person-hours unreviewed" in capsys.readouterr().out


class TestUniqueReviewPath:
    """A review file is hand-labelled, so overwriting one destroys work that
    cannot be regenerated — and re-running on the same day, after fixing a rule
    to see what moved, is the normal case rather than the exception."""

    def test_first_run_uses_the_plain_name(self, tmp_path):
        got = unique_review_path("2026-08-02", tmp_path).name
        assert got == "recurrence_review_2026-08-02.csv"

    def test_a_second_run_the_same_day_does_not_overwrite(self, tmp_path):
        (tmp_path / "recurrence_review_2026-08-02.csv").write_text("labelled")
        got = unique_review_path("2026-08-02", tmp_path).name
        assert got == "recurrence_review_2026-08-02_r2.csv"

    def test_it_keeps_counting(self, tmp_path):
        for name in ("recurrence_review_2026-08-02.csv", "recurrence_review_2026-08-02_r2.csv"):
            (tmp_path / name).write_text("labelled")
        got = unique_review_path("2026-08-02", tmp_path).name
        assert got == "recurrence_review_2026-08-02_r3.csv"
