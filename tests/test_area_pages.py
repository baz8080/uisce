"""The area pages: what gets one, what it says, and what still does not.

An area was reachable only as `#area/<county>/<code>` until 2026-08-26 — not a
URL a reader can keep or a search engine can index, and the long tail of this
site is areas rather than counties. These pages are that surface.

The interesting half is the exclusions. 1,193 of the areas with a notice are
Electoral Divisions named "Around ...", which nobody searches for and which
would be 1,193 near-identical pages; publishing them is the failure this whole
change has to avoid, so the predicate is guarded rather than trusted.
"""

import csv
import re
from pathlib import Path

import pytest
import statusui
from conftest import site_case as _case
from test_site import NOW, SA_INDEX, TOWNS

from uisce.config import BASE_URL
from uisce.site import (
    SA_TOWNS_PATH,
    UNPLACED,
    _events_html,
    area_has_page,
    area_path,
    build_site,
    write_site,
)


def _write(tmp_path, rows=None):
    site = build_site(rows or [_case()], SA_INDEX, NOW, TOWNS)
    site.pop("recurrence_report")
    return write_site(site, tmp_path, TOWNS)


class TestWhichAreasGetOne:
    @pytest.mark.parametrize(
        "code",
        ["19848", "01626", "02341-Dún Laoghaire", "02341-Clondalkin"],
        ids=["settlement", "settlement-leading-zero", "city-lea-fada", "city-lea"],
    )
    def test_a_named_place_gets_a_page(self, code):
        assert area_has_page(code)

    @pytest.mark.parametrize(
        "code",
        ["ed:Carlow:Agha", "ed:Cavan:Dunmakeever/Benbrack/Derrynananta",
         "02341-rest", "17364-rest", UNPLACED],
        ids=["ed", "ed-with-slashes", "city-residual", "city-residual-cork", "unplaced"],
    )
    def test_a_bucket_that_is_not_a_place_does_not(self, code):
        assert not area_has_page(code)

    def test_the_split_over_the_real_csv_is_where_we_left_it(self):
        """The numbers the decision to exclude the EDs was made on. If the CSO
        file changes shape these move, and the choice deserves re-making rather
        than inheriting."""
        codes = {}
        with open(SA_TOWNS_PATH, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                codes.setdefault(r["town_code"], (r["town_name"], r["town_county"]))
        assert len(codes) == 3717
        assert sum(1 for c in codes if area_has_page(c)) == 904
        assert sum(1 for c in codes if c.startswith("ed:")) == 2808
        # every ED is "Around somewhere", which is why none of them is a page
        assert all(n.startswith("Around ") for c, (n, _) in codes.items()
                   if c.startswith("ed:"))

    def test_the_path_is_unique_over_every_area_in_the_file(self):
        """A code is not a filename, so the path is keyed on county and name.
        Name alone is not enough — 185 repeat across counties."""
        codes = {}
        with open(SA_TOWNS_PATH, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                codes.setdefault(r["town_code"], (r["town_name"], r["town_county"]))
        paths = [area_path(county, name) for code, (name, county) in codes.items()
                 if area_has_page(code)]
        assert len(set(paths)) == len(paths) == 904
        assert all(p.startswith("a/") and p.endswith(".html") for p in paths)

    def test_the_slug_is_the_python_one_because_the_js_one_would_404(self):
        """statusui's two slugs are deliberately unpaired: ui.js leaves a fada
        as a dash. 17 of these places carry one, so the app is handed the slug
        rather than left to build it."""
        assert area_path("Dublin", "Dún Laoghaire") == "a/dublin/dun-laoghaire.html"
        assert re.sub(r"[^a-z0-9]+", "-", "Dún Laoghaire".lower()) == "d-n-laoghaire"


class TestThePage:
    def test_it_is_written_for_the_area_and_reachable_at_its_path(self, tmp_path):
        _write(tmp_path)
        page = tmp_path / area_path("Carlow", "Testtown")
        assert page.exists()
        assert f'<link rel="canonical" href="{BASE_URL}/a/carlow/testtown.html">' in (
            page.read_text()
        )

    def test_it_needs_no_javascript_to_say_anything(self, tmp_path):
        """The whole point of the page, and the same bar the county pages meet:
        it must not pull the payload, and must carry text rather than a shell."""
        _write(tmp_path)
        page = (tmp_path / area_path("Carlow", "Testtown")).read_text()
        assert "data.js" not in page and "UISCE_DATA" not in page
        body = re.sub(r"<(script|style).*?</\1>", "", page, flags=re.S)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        assert len(text) > 400, text

    def test_it_carries_the_notice_and_the_population(self, tmp_path):
        _write(tmp_path)
        page = (tmp_path / area_path("Carlow", "Testtown")).read_text()
        assert "Testtown" in page
        assert "Burst Water Main - Carlow" in page
        assert "1,000 people" in page

    @pytest.mark.parametrize("n,expected", [(2, "1 other area,"), (4, "3 other areas,")])
    def test_it_says_when_a_notice_is_listed_in_more_than_one_area(self, n, expected):
        """One event published as pins in several areas appears in each of their
        histories. Meeting the same burst twice reads as double-counting unless
        the row says so — the app's area view carries the same note.

        The fixture corpus has one area, so the rule is exercised on the
        renderer rather than end to end."""
        event = {"ref": "R", "title": "Burst", "sev": "outage",
                 "start": "2026-05-01", "areas": n}
        assert expected in _events_html([event], multi_area=True)

    @pytest.mark.parametrize(
        "event,expected",
        [
            ({"areas": 4, "people": 3775}, True),
            ({"areas": 4}, False),
        ],
        ids=["with-a-people-figure", "without-one"],
    )
    def test_a_multi_area_row_says_whose_people_those_are(self, event, expected):
        """`people` is the whole event's footprint. An area page states the
        area's own population two lines above it, so a notice spanning five
        areas can print seven times that number — the app's badge carries this
        caveat and the page has to as well. Said only when there is a figure to
        qualify."""
        row = _events_html(
            [{"ref": "R", "title": "Burst", "sev": "outage",
              "start": "2026-05-01", **event}],
            multi_area=True,
        )
        assert ("not this area\u2019s share" in row) is expected

    def test_the_county_list_never_carries_that_note(self):
        """It de-duplicates, so every event on it is there once and saying
        "also published in 3 other areas" would be answering a question the
        page has not raised."""
        event = {"ref": "R", "title": "Burst", "sev": "outage",
                 "start": "2026-05-01", "areas": 4}
        assert "other area" not in _events_html([event])

    def test_the_description_is_true_of_an_uncapped_list(self, tmp_path):
        """It claims every notice, which only holds while the list is uncapped —
        the county page's claim had to be walked back for exactly this reason."""
        _write(tmp_path)
        page = (tmp_path / area_path("Carlow", "Testtown")).read_text()
        desc = re.search(r'name="description" content="([^"]*)"', page).group(1)
        assert "every one of them" in desc
        assert "not shown here" not in page

    def test_the_app_link_is_a_route_the_router_actually_has(self, tmp_path):
        """Run the app's own patterns against the href the page emits, rather
        than trusting a remembered shape. It shipped as `#area/<county>` — one
        segment where the area route needs two — which matches neither pattern
        and drops the reader on the national overview.
        """
        _write(tmp_path)
        page = (tmp_path / area_path("Carlow", "Testtown")).read_text()
        frag = re.search(r'href="\.\./\.\./index\.html(#[^"]*)"', page).group(1)

        site_html = (
            Path(__file__).resolve().parent.parent / "src" / "uisce" / "site.html"
        ).read_text()
        routes = [
            re.compile(pat.replace("\\/", "/"))
            for pat in re.findall(r"location\.hash\.match\(/(.+?)/\)", site_html)
        ]
        assert len(routes) == 2, "the router's patterns moved; this test reads them"
        assert any(r.match(frag) for r in routes), frag
        # the shape that regressed, held against the same patterns
        assert not any(r.match("#area/Carlow") for r in routes)

    def test_it_links_back_to_the_county_and_the_directory(self, tmp_path):
        """A sitemap is a weak discovery signal; these are the strong ones, and
        they are also how a reader gets out of a page they landed on cold."""
        _write(tmp_path)
        page = (tmp_path / area_path("Carlow", "Testtown")).read_text()
        assert 'href="../../c/carlow.html"' in page
        assert 'href="../../areas.html"' in page


class TestTheRestOfTheSite:
    def test_an_area_with_a_page_is_linked_from_the_directory(self, tmp_path):
        """The crawlable path in. areas.html already names every area."""
        _write(tmp_path)
        assert 'href="a/carlow/testtown.html"' in (tmp_path / "areas.html").read_text()

    def test_the_county_page_links_one_directory_up(self, tmp_path):
        _write(tmp_path)
        assert 'href="../a/carlow/testtown.html"' in (
            tmp_path / "c" / "carlow.html"
        ).read_text()

    def test_the_payload_carries_the_slug_exactly_when_there_is_a_page(self, tmp_path):
        site = build_site([_case()], SA_INDEX, NOW, TOWNS)
        towns = site["counties"]["Carlow"]["towns"]
        assert towns["T1"]["slug"] == "testtown"
        assert all(("slug" in t) == area_has_page(code) for code, t in towns.items())

    def test_the_sitemap_carries_the_area_pages(self, tmp_path):
        _write(tmp_path)
        sitemap = (tmp_path / "sitemap.xml").read_text()
        assert f"{BASE_URL}/a/carlow/testtown.html" in sitemap

    def test_slug_matches_statusui_so_the_path_and_the_payload_agree(self):
        """The page is written at one and the app links to the other; a drift
        between them is a 404 nobody would notice until a reader hit it."""
        assert area_path("Dublin", "Dún Laoghaire").endswith(
            f"{statusui.slug('Dún Laoghaire')}.html"
        )
