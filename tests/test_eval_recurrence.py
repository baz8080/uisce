import csv

from uisce.eval_recurrence import FIELDNAMES, RECURRENCE_TEXT, plain, score


class TestRecurrenceText:
    """Tuned for recall: this only flags a row for a human, never decides
    anything, so a false flag costs one row of reading and a miss costs a
    wrong figure staying on the site."""

    def test_matches_the_wordings_the_feed_uses(self):
        for text in ("works nightly from 10pm", "daily from 9pm until 9am",
                     "each night from 11pm", "overnight from 10pm until 7am"):
            assert RECURRENCE_TEXT.search(text), text

    def test_does_not_match_a_single_continuous_period(self):
        assert not RECURRENCE_TEXT.search("Works will take place from 9am on 3 June until 5pm.")

    def test_plain_strips_markup_and_collapses_whitespace(self):
        assert plain("<p>Works  are<br><br>complete</p>") == "Works are complete"
        assert plain(None) == ""


class TestScore:
    def _file(self, tmp_path, rows):
        path = tmp_path / "recurrence_review_2026-08-02.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in FIELDNAMES})
        return path

    def _row(self, **kw):
        base = {"case_id": 1, "reference_num": "CAR1", "county": "Carlow", "person_h": 1000,
                "effect": "downgraded to restriction", "human_verdict": ""}
        return base | kw

    def test_reports_nothing_labelled(self, tmp_path, capsys):
        path = self._file(tmp_path, [self._row()])
        score(["--csv", str(path)])
        assert "Nothing labelled yet" in capsys.readouterr().out

    def test_counts_verdicts_and_names_the_calls_to_fix(self, tmp_path, capsys):
        path = self._file(tmp_path, [
            self._row(case_id=1, reference_num="CAR1", human_verdict="correct", person_h=1000),
            self._row(case_id=2, reference_num="CAR2", human_verdict="wrong", person_h=500,
                      human_notes="one continuous period, not a repeat"),
        ])
        score(["--csv", str(path)])
        out = capsys.readouterr().out
        assert "2 of 2 row(s) reviewed" in out
        assert "CAR2" in out and "one continuous period" in out
        assert "CAR1" not in out.split("Calls to fix:")[1]

    def test_reports_what_is_still_unreviewed_and_what_it_is_worth(self, tmp_path, capsys):
        path = self._file(tmp_path, [
            self._row(case_id=1, human_verdict="correct", person_h=1000),
            self._row(case_id=2, person_h=750),
        ])
        score(["--csv", str(path)])
        out = capsys.readouterr().out
        assert "1 of 2 row(s) reviewed" in out
        assert "1 row(s) left, 750 person-hours unreviewed" in out
