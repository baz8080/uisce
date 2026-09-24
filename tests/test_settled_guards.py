"""Guards for rows of CLAUDE.md's "Settled" table that no other test would
notice breaking. Each names the row it holds; the evidence is in notes/."""

import json
import re
import sqlite3

import pytest
import statusui
from conftest import case_record, make_cases_table
from conftest import site_case as _case
from test_site import NOW, SA_INDEX, TOWNS

from uisce import build, pipeline, site
from uisce.site import build_site, classify, grade, knocks_grade, write_site


class TestFirstInferenceStartIsPinned:
    """`start_date` is re-stamped in place by the feed; taking the minimum
    recorded start is explicitly rejected (data-quality.md, 2026-07-20)."""

    FIRST = "2026-06-01T09:00:00+00:00"
    BACKWARD_RESTAMP = "2026-05-01T09:00:00+00:00"

    def _inference(self, inferred_at, start_date):
        return {
            "case_id": 1, "description_hash": "h", "start_date": start_date,
            "model": "rules", "prompt_version": 3, "notes": None,
            "end_source": "completion_update", "local_date": "2026-06-02",
            "local_time": "10:00", "inferred_at": inferred_at,
        }

    def test_a_backward_restamp_in_a_later_run_does_not_move_the_start(self):
        records = [
            self._inference("2026-06-01T12:00:00+00:00", self.FIRST),
            self._inference("2026-06-05T12:00:00+00:00", self.BACKWARD_RESTAMP),
        ]
        assert build.first_start_date_per_case(records) == {1: self.FIRST}

    def test_build_stores_and_measures_from_the_first_inference_start(
        self, tmp_path, monkeypatch
    ):
        jsonl = tmp_path / "inferred.jsonl"
        jsonl.write_text("".join(json.dumps(r) + "\n" for r in [
            self._inference("2026-06-05T12:00:00+00:00", self.BACKWARD_RESTAMP),
            self._inference("2026-06-01T12:00:00+00:00", self.FIRST),
        ]))
        db = tmp_path / "uisce.db"
        with sqlite3.connect(db) as conn:
            make_cases_table(conn)
            conn.execute(
                "INSERT INTO cases (id, description, status, start_date) VALUES (1, 'x', "
                "'Closed', ?)", (self.BACKWARD_RESTAMP,),
            )
        monkeypatch.setattr(build, "JSONL_PATH", jsonl)
        monkeypatch.setattr(build, "DB_PATH", db)

        build.run()

        with sqlite3.connect(db) as conn:
            start, seconds = conn.execute(
                "SELECT end_input_start_date, notice_to_end_seconds FROM inferred_cases"
            ).fetchone()
        assert start == self.FIRST
        # 10:00 IST on 2 June is 09:00 UTC, a day after the pinned start
        assert seconds == 24 * 3600


class TestShortDownloadNeverReachesTheDb:
    """The vanished_at stamp is safe only behind FEED_COUNT_TOLERANCE
    (data-quality.md, "Cases that vanish from the feed", 2026-09-05)."""

    def _run(self, tmp_path, monkeypatch, downloaded):
        created = []
        monkeypatch.setattr(pipeline, "make_session", lambda: None)
        monkeypatch.setattr(pipeline, "feed_count", lambda session: 1000)
        monkeypatch.setattr(pipeline, "download_cases", lambda session: [{}] * downloaded)
        monkeypatch.setattr(pipeline, "CASES_RAW_PATH", tmp_path / "raw.json")
        monkeypatch.setattr(pipeline, "CASES_MAPPED_PATH", tmp_path / "mapped.json")
        monkeypatch.setattr(pipeline, "map_cases", lambda features: ([], []))
        monkeypatch.setattr(pipeline, "skip_geocoding", lambda cases: None)
        monkeypatch.setattr(pipeline, "backfill_county", lambda cases: None)
        monkeypatch.setattr(pipeline, "create_db", lambda cases: created.append(cases))
        monkeypatch.setattr(pipeline, "backfill", lambda: None)
        return created

    def test_a_short_download_raises_before_create_db(self, tmp_path, monkeypatch):
        created = self._run(tmp_path, monkeypatch, downloaded=989)
        with pytest.raises(RuntimeError, match="truncated download"):
            pipeline.run(skip_geocode=True)
        assert created == []
        assert not (tmp_path / "raw.json").exists()

    def test_a_download_within_tolerance_reaches_create_db(self, tmp_path, monkeypatch):
        created = self._run(tmp_path, monkeypatch, downloaded=990)
        pipeline.run(skip_geocode=True)
        assert created == [[]]


def test_a_vanished_open_case_gets_vanished_at_and_never_closed_at():
    conn = make_cases_table(sqlite3.connect(":memory:"))
    record = case_record(id=1, title="Burst Water Main - Cork", status="Open")
    pipeline.load_cases(conn, [record], now="2026-07-01T00:00:00+00:00")
    pipeline.load_cases(conn, [], now="2026-07-08T00:00:00+00:00")
    pipeline.load_cases(conn, [], now="2026-07-09T00:00:00+00:00")
    row = conn.execute("SELECT vanished_at, closed_at, status FROM cases").fetchone()
    assert row == ("2026-07-08T00:00:00+00:00", None, "Open")


def test_the_printed_grade_legend_matches_grade():
    legend = re.search(r'<ul class="grades">(.*?)</ul>', site.SITE_HTML.read_text(), re.S)
    items = re.findall(
        r'<span class="gradechip g-([A-F])">\1</span>\s*(below|)\s*([\d.]+)% ?(or better|)',
        legend.group(1),
    )
    assert [letter for letter, *_ in items] == list("ABCDEF")

    floors = {}
    for letter, below, cut, better in items[:-1]:
        assert (below, better) == ("", "or better")
        floors[letter] = float(cut)
        assert grade(floors[letter]) == letter
        assert grade(floors[letter] - 0.001) != letter

    letter, below, cut, better = items[-1]
    assert (letter, below, better) == ("F", "below", "")
    assert float(cut) == floors["E"]
    assert grade(float(cut) - 0.001) == "F"


class TestInitialBudgetWarnsNeverFails:
    """INITIAL_BUDGET is warned, never failed (frontend-notes.md, "The county's
    own data left data.js", 2026-09-05)."""

    def test_the_budget_is_512_kb(self):
        assert site.INITIAL_BUDGET == 512 * 1024

    def _run(self, tmp_path, monkeypatch, initial):
        monkeypatch.setattr(site.SmallAreaIndex, "from_csv", lambda *a: SA_INDEX)
        monkeypatch.setattr(site.TownLookup, "from_csv", lambda *a: TOWNS)
        monkeypatch.setattr(site, "read_cases", lambda: ([_case()], NOW))
        monkeypatch.setattr(site, "SITE_DIR", tmp_path)
        monkeypatch.setattr(statusui, "size_report", lambda *a, **k: (initial, "report"))
        site.run()

    def test_an_over_budget_initial_load_is_warned_and_the_build_completes(
        self, tmp_path, monkeypatch, capsys
    ):
        self._run(tmp_path, monkeypatch, site.INITIAL_BUDGET + 1)
        out = capsys.readouterr().out
        assert f"::warning::initial load {site.INITIAL_BUDGET + 1:,} bytes" in out
        assert (tmp_path / "index.html").exists()

    def test_an_initial_load_at_the_budget_is_not_warned(self, tmp_path, monkeypatch, capsys):
        self._run(tmp_path, monkeypatch, site.INITIAL_BUDGET)
        assert "::warning::" not in capsys.readouterr().out


class TestOneNamePerThing:
    """frontend-notes.md, "One name per thing" (2026-08-27)."""

    FOOTER = ">Source code</a> · not affiliated with Uisce Éireann."

    @pytest.fixture
    def pages(self, tmp_path):
        built = build_site([_case()], SA_INDEX, NOW, TOWNS)
        built.pop("recurrence_report")
        write_site(built, tmp_path, TOWNS)
        return {str(p.relative_to(tmp_path)): p.read_text() for p in tmp_path.rglob("*.html")}

    def test_every_kind_of_page_is_checked(self, pages):
        assert {"index.html", "areas.html", "c/carlow.html", "a/carlow/testtown.html"} <= set(
            pages
        )

    def test_every_footer_carries_the_credit(self, pages):
        assert [p for p, text in pages.items() if self.FOOTER not in text] == []

    def test_no_page_puts_the_directory_in_ireland(self, pages):
        assert [p for p, text in pages.items() if "in Ireland" in text] == []

    def test_every_link_to_the_directory_names_it_the_same_way(self, pages):
        for path, text in pages.items():
            for label in re.findall(r'<a href="[./]*areas\.html"[^>]*>(.*?)</a>', text, re.S):
                assert label.lower().endswith("every area with a notice"), (path, label)

    def test_no_link_calls_the_app_a_map(self, pages):
        for path, text in pages.items():
            for label in re.findall(r"<a\b[^>]*>(.*?)</a>", text, re.S):
                assert not re.search(r"\bmaps?\b", label, re.I), (path, label)

    def test_the_static_pages_call_the_app_the_interactive_view(self, pages):
        assert "Co.&nbsp;Carlow’s interactive view</a>" in pages["a/carlow/testtown.html"]
        assert "interactive view for Co. Carlow</a>" in pages["c/carlow.html"]


CATEGORIES = sorted(
    site.HARD_CATS | site.REPAIR_CATS | site.QUALITY_CATS | site.DEGRADED_CATS
    | site.KNOCK_CATS | site.IGNORE_CATS | {"essential_works", "leak_detection"}
) + [None]


@pytest.mark.parametrize("work_type", ["Planned", "Unplanned", None])
@pytest.mark.parametrize("category", CATEGORIES)
def test_the_water_outage_flag_changes_nothing(category, work_type):
    off, on = (_case(work_category=category, work_type=work_type, water_outage=flag)
               for flag in (0, 1))
    assert classify(off) == classify(on)
    assert classify(off, recurring=True) == classify(on, recurring=True)
    assert knocks_grade(off) == knocks_grade(on)
