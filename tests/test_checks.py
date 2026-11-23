import os
import sqlite3
import subprocess
from pathlib import Path

from uisce.checks import band_finding, vanished_finding

SCRIPT = Path(__file__).parent.parent / "scripts" / "open-check-issues.sh"
THIS_BUILD = "2026-12-01T16:30:00+00:00"
EARLIER = "2026-11-30T16:30:00+00:00"


def _db(served, gone, gone_earlier=0):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cases (id INTEGER PRIMARY KEY, start_date TEXT, status TEXT, "
                 "last_seen TEXT, vanished_at TEXT)")
    rows = [("2026-11-20T09:00:00+00:00", "Closed", THIS_BUILD, None)] * served
    rows += [("2026-07-03T09:00:00+00:00", "Open", EARLIER, THIS_BUILD)] * gone
    rows += [("2026-07-03T09:00:00+00:00", "Open", EARLIER, EARLIER)] * gone_earlier
    conn.executemany(
        "INSERT INTO cases (start_date, status, last_seen, vanished_at) VALUES (?, ?, ?, ?)", rows
    )
    return conn


class TestVanished:
    def test_a_few_cases_leaving_the_feed_is_not_a_finding(self):
        assert vanished_finding(_db(served=990, gone=10)) is None

    def test_more_than_the_guard_tolerates_is(self):
        finding = vanished_finding(_db(served=989, gone=11))
        assert finding.title == "Data check: 11 cases vanished from the feed on 2026-12-01"
        assert "11 of the 1,000 cases" in finding.body and "1.1%" in finding.body
        assert "11 of them were still `Open`" in finding.body
        assert "| 2026-07 | 11 |" in finding.body

    def test_a_purge_an_earlier_build_stamped_is_not_raised_again(self):
        assert vanished_finding(_db(served=500, gone=0, gone_earlier=400)) is None

    def test_an_empty_database_says_nothing(self):
        assert vanished_finding(_db(served=0, gone=0)) is None


def _site(rates):
    """A payload of one county whose months carry `rates`; None is a month not seen whole."""
    months = [f"2026-{m:02d}" for m in range(5, 5 + len(rates))]
    figures = {
        ym: {"supply_notices": 100, "planned": 40, "supply_per_100km": rate}
        for ym, rate in zip(months, rates)
    }
    return {"months": months, "national": figures, "counties": {"Carlow": {"months": figures}}}


class TestBand:
    def test_a_month_inside_the_band_is_not_a_finding(self):
        assert band_finding(_site([3.59, 3.0, 5.5])) is None

    def test_the_newest_finished_month_outside_it_is(self):
        finding = band_finding(_site([3.59, 3.81, 5.71, None]))
        assert finding.title == "Data check: national rate of 5.71 in 2026-07 is outside 3 to 5.5"
        assert "July 2026 closed at 5.71" in finding.body
        assert "**not** to re-fit" in finding.body
        assert "| Carlow | 3.70 | 5.71 |" in finding.body

    def test_an_older_month_outside_it_is_not_raised_late(self):
        assert band_finding(_site([2.5, 3.81])) is None

    def test_no_finished_month_says_nothing(self):
        assert band_finding(_site([None])) is None


def _gh_stub(tmp_path, existing):
    """A `gh` that logs its arguments and lists `existing` as the titles already raised."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/bin/sh\n"
        'echo "$@" >> "$GH_LOG"\n'
        'if [ "$1 $2" = "issue list" ]; then cat "$GH_EXISTING"; fi\n'
        'if [ "$1 $2" = "issue create" ]; then cat > /dev/null; fi\n'
    )
    stub.chmod(0o755)
    (tmp_path / "existing").write_text("".join(f"{title}\n" for title in existing))
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_LOG": str(tmp_path / "log"),
        "GH_EXISTING": str(tmp_path / "existing"),
        "GITHUB_REPOSITORY_OWNER": "someone",
    }


class TestOpeningIssues:
    def _run(self, tmp_path, findings, existing=()):
        checks = tmp_path / "checks"
        checks.mkdir()
        for i, title in enumerate(findings, 1):
            (checks / f"{i}.md").write_text(f"{title}\n\nWhat tripped.\n")
        env = _gh_stub(tmp_path, existing)
        out = subprocess.run([SCRIPT, checks], env=env, capture_output=True, text=True, check=True)
        log = tmp_path / "log"
        return out.stdout, log.read_text().splitlines() if log.exists() else []

    def test_a_finding_becomes_an_issue_assigned_to_the_owner(self, tmp_path):
        _, calls = self._run(tmp_path, ["Data check: a new one"])
        [create] = [call for call in calls if call.startswith("issue create")]
        assert "--title Data check: a new one" in create
        assert "--label data-check" in create and "--assignee someone" in create

    def test_a_finding_already_raised_is_not_raised_again_even_if_closed(self, tmp_path):
        out, calls = self._run(
            tmp_path, ["Data check: seen", "Data check: a new one"], existing=["Data check: seen"]
        )
        assert "already raised: Data check: seen" in out
        assert [call for call in calls if call.startswith("issue list")] == [
            "issue list --state all --label data-check --limit 1000 --json title --jq .[].title"
        ]
        assert len([call for call in calls if call.startswith("issue create")]) == 1

    def test_no_finding_calls_nothing(self, tmp_path):
        out, calls = self._run(tmp_path, [])
        assert "no data check tripped" in out and calls == []
