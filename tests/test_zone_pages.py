"""The zone pages: z/<slug>.html for every Water Supply Zone, and the zones.html
directory with the notices pinned outside every zone."""

import html
import json
import re

import pytest
from conftest import site_case as _case
from test_site import NOW, TOWNS

from uisce.config import BASE_URL
from uisce.site import (
    SPOT_KM,
    _mains_text,
    _zone_summary_html,
    build_site,
    km_apart,
    repeat_spots,
    write_site,
    zone_path,
)
from uisce.wsz import ZoneLookup, read_zones


def _square(code, lat, lon, half=0.005):
    ring = [[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
            [lon - half, lat + half], [lon - half, lat - half]]
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


# one zone around the default pin (52.836, -6.926), one beside it, one with no pins
ZONES = ZoneLookup([_square("SZT1", 52.836, -6.926), _square("SZT2", 52.836, -6.910)])
ZONE_ROWS = [
    {"code": "SZT1", "name": "Testzone", "local_authority": "Carlow", "county": "Carlow",
     "mains_m": "12000"},
    {"code": "SZT2", "name": "Nextzone", "local_authority": "Carlow", "county": "Carlow",
     "mains_m": "4300"},
    {"code": "SZT3", "name": "Quiet Zone ", "local_authority": "Carlow", "county": "Carlow",
     "mains_m": "0"},
]
NEXT = {"full_lat": 52.836, "full_lon": -6.910}
OUTSIDE = {"full_lat": 52.836, "full_lon": -6.880}


def _build(rows=None):
    site = build_site(rows or [_case()], NOW, TOWNS, zones=ZONES, zone_rows=ZONE_ROWS)
    site.pop("recurrence_report")
    return site


def _write_zoned(tmp_path, rows=None):
    return write_site(_build(rows), tmp_path, TOWNS)


def _text(page):
    body = re.sub(r"<(script|style).*?</\1>", "", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))


class TestThePath:
    def test_every_zone_in_the_mains_table_slugs_to_its_own_page(self):
        paths = [zone_path(r["name"]) for r in read_zones()]
        assert len(set(paths)) == len(paths) == 688
        assert all(re.fullmatch(r"z/[a-z0-9][a-z0-9-]*\.html", p) for p in paths)

    def test_a_trailing_space_in_the_layer_does_not_reach_the_path(self):
        assert zone_path("Pollan Dam ") == "z/pollan-dam.html"


class TestRepeatSpots:
    def test_two_notices_within_200_m_are_a_spot(self):
        a, b = (52.0, -7.0), (52.0015, -7.0)
        assert km_apart(a, b) < SPOT_KM
        [(_centre, _coords, keys)] = repeat_spots([(a, "R1"), (b, "R2")])
        assert keys == {"R1", "R2"}

    def test_one_notice_pinned_twice_is_not(self):
        assert repeat_spots([((52.0, -7.0), "R1"), ((52.0005, -7.0), "R1")]) == []

    def test_notices_further_apart_are_not(self):
        assert repeat_spots([((52.0, -7.0), "R1"), ((52.0025, -7.0), "R2")]) == []

    def test_a_street_of_notices_150_m_apart_is_not_chained_into_one_spot(self):
        street = [((52.0 + i * 0.00135, -7.0), f"R{i}") for i in range(4)]
        spots = repeat_spots(street)
        assert [len(keys) for _, _, keys in spots] == [3]


class TestTheFigures:
    def test_every_zone_in_the_table_is_built_notices_or_none(self):
        zones = _build()["zones"]
        assert set(zones) == {"SZT1", "SZT2", "SZT3"}
        assert zones["SZT3"]["name"] == "Quiet Zone"
        assert zones["SZT3"]["outage_n"] == 0 and zones["SZT3"]["events"] == []

    def test_the_zone_counts_outages_and_takes_the_median_of_observed_completions(self):
        rows = [
            _case(),
            _case(id=2, reference_num="CAR2", notice_to_end_seconds=3 * 3600.0),
            _case(id=3, reference_num="CAR3", end_source="scheduled_end_with_time"),
            _case(id=4, reference_num="CAR4", work_category="planned_works",
                  work_type="Planned"),
        ]
        zone = _build(rows)["zones"]["SZT1"]
        assert zone["outage_n"] == 3
        assert (zone["median_h"], zone["completed_n"]) == (13.5, 2)
        assert len(zone["events"]) == 4

    def test_a_notice_published_before_collection_began_is_not_counted(self):
        zone = _build([_case(start_date="2026-03-01T00:00:00+00:00")])["zones"]["SZT1"]
        assert zone["outage_n"] == 0 and zone["completed_n"] == 0

    def test_a_notice_pinned_in_two_zones_is_listed_in_each_and_says_so(self):
        rows = [_case(), _case(id=2, **NEXT)]
        zones = _build(rows)["zones"]
        for code in ("SZT1", "SZT2"):
            [event] = zones[code]["events"]
            assert event["zones"] == 2
        assert zones["SZT1"]["outage_n"] == zones["SZT2"]["outage_n"] == 1

    def test_a_pin_outside_every_zone_is_listed_under_its_area(self):
        site = _build([_case(), _case(id=2, reference_num="CAR2", **OUTSIDE)])
        assert site["unzoned"] == {"Carlow": {"T1": 1}}
        assert len(site["zones"]["SZT1"]["events"]) == 1

    def test_an_active_boil_notice_raises_the_marker(self):
        row = _case(work_category="boil_notice_issued", status="Open", end_source=None,
                    notice_to_end_seconds=None, end_local_date=None, end_local_time=None)
        zone = _build([row])["zones"]["SZT1"]
        assert zone["health_now"] == 1
        assert '<span class="health">1 active health notice</span>' in _zone_summary_html(zone)

    def test_repeat_spots_are_outage_pins_named_for_the_nearest_area(self):
        rows = [_case(), _case(id=2, reference_num="CAR2", full_lat=52.837),
                _case(id=3, reference_num="CAR3", full_lat=52.8365,
                      work_category="planned_works", work_type="Planned")]
        [spot] = _build(rows)["zones"]["SZT1"]["spots"]
        assert (spot["name"], spot["n"], spot["loc"]) == ("Testtown", 2, "Somewhere")

    def test_nothing_is_built_without_the_zones(self):
        site = build_site([_case()], NOW, TOWNS)
        assert "zones" not in site and "unzoned" not in site

    def test_zones_without_towns_are_refused(self):
        with pytest.raises(ValueError, match="need towns"):
            build_site([_case()], NOW, zones=ZONES, zone_rows=ZONE_ROWS)


class TestThePages:
    def test_a_page_per_zone_at_its_path(self, tmp_path):
        sizes = _write_zoned(tmp_path)
        assert sizes["n_zone_pages"] == 3
        page = (tmp_path / "z/testzone.html").read_text()
        assert f'<link rel="canonical" href="{BASE_URL}/z/testzone.html">' in page
        assert (tmp_path / "z/quiet-zone.html").exists()

    def test_the_page_says_the_record_since_collection_began(self, tmp_path):
        _write_zoned(tmp_path)
        text = _text((tmp_path / "z/testzone.html").read_text())
        assert "Water Supply Zone SZT1 · Co. Carlow · 12 km of water main" in text
        assert "4.3 km of water main" in _text((tmp_path / "z/nextzone.html").read_text())
        assert "Since 20 April 2026: 1 outage notice ; typical time to" in text
        assert "Every notice published here · 1 notice" in text
        quiet = _text((tmp_path / "z/quiet-zone.html").read_text())
        assert "No outage notice since 20 April 2026." in quiet
        assert "km of water main" not in quiet

    def test_it_needs_no_javascript_and_links_back_to_its_county(self, tmp_path):
        _write_zoned(tmp_path)
        page = (tmp_path / "z/testzone.html").read_text()
        assert "data.js" not in page and "UISCE_DATA" not in page
        assert 'href="../c/carlow.html"' in page and 'href="../zones.html#c-carlow"' in page

    def test_a_main_under_a_kilometre_is_given_in_metres(self):
        assert _mains_text(0.022) == "22&nbsp;m" and _mains_text(0.564) == "564&nbsp;m"

    def test_two_zones_that_would_share_a_page_are_refused(self, tmp_path):
        site = build_site([_case()], NOW, TOWNS, zones=ZONES,
                          zone_rows=ZONE_ROWS + [dict(ZONE_ROWS[0], code="SZT4")])
        site.pop("recurrence_report")
        with pytest.raises(ValueError, match="share a page"):
            write_site(site, tmp_path, TOWNS)

    def test_no_outside_section_when_every_pin_is_in_a_zone(self, tmp_path):
        _write_zoned(tmp_path)
        assert 'id="outside"' not in (tmp_path / "zones.html").read_text()

    def test_a_repeat_spot_links_the_area_page(self, tmp_path):
        _write_zoned(tmp_path, [_case(), _case(id=2, reference_num="CAR2", full_lat=52.837)])
        spots = re.search(
            r'<section id="spots">.*?</section>', (tmp_path / "z/testzone.html").read_text(),
            re.S,
        ).group(0)
        assert '<a href="../a/carlow/testtown.html">Testtown</a>' in spots

    def test_the_directory_lists_every_zone_and_says_what_lies_outside(self, tmp_path):
        _write_zoned(tmp_path, [_case(), _case(id=2, reference_num="CAR2", **OUTSIDE)])
        page = (tmp_path / "zones.html").read_text()
        for path in ("z/testzone.html", "z/nextzone.html", "z/quiet-zone.html"):
            assert f'href="{path}"' in page
        outside = re.search(r'<section id="outside">.*?</section>', page, re.S).group(0)
        assert "About one person in five is on a group or private scheme" in outside
        assert '<a href="a/carlow/testtown.html">Testtown</a>' in outside

    def test_the_index_says_what_lies_outside_and_links_the_directory(self, tmp_path):
        _write_zoned(tmp_path)
        page = (tmp_path / "index.html").read_text()
        assert '<a href="zones.html" style="color:inherit">Every supply zone</a>' in page
        assert "About one person in five is on a group or private scheme" in page

    def test_the_sitemap_carries_the_zone_pages(self, tmp_path):
        sizes = _write_zoned(tmp_path)
        sitemap = (tmp_path / "sitemap.xml").read_text()
        assert f"{BASE_URL}/z/testzone.html" in sitemap and f"{BASE_URL}/zones.html" in sitemap
        assert sitemap.count("<loc>") == sizes["sitemap_urls"]

    def test_the_zones_never_reach_the_payload(self, tmp_path):
        _write_zoned(tmp_path)
        data = (tmp_path / "data.js").read_text()
        payload = json.loads(data.removeprefix("window.UISCE_DATA = ").removesuffix(";"))
        assert "zones" not in payload and "unzoned" not in payload
        assert "Testzone" not in data



class TestSearchReachesTheZone:
    def _index(self, tmp_path, rows=None):
        _write_zoned(tmp_path, rows)
        body = (tmp_path / "search.js").read_text()
        return json.loads(body.split(" = ", 1)[1].rstrip(";"))["Carlow"]

    def test_every_zone_name_is_in_the_index_under_its_county(self, tmp_path):
        entries = self._index(tmp_path)
        assert ["Testzone", "z/testzone.html"] in entries
        assert ["Quiet Zone", "z/quiet-zone.html"] in entries

    def test_an_area_entry_lists_the_zones_its_pins_fall_in(self, tmp_path):
        rows = [_case(), _case(id=2, ref="R2", **NEXT)]
        entries = self._index(tmp_path, rows)
        assert ["Testtown", "testtown", ["Nextzone", "Testzone"]] in entries

    def test_an_area_pinned_in_no_zone_keeps_the_two_part_entry(self, tmp_path):
        entries = self._index(tmp_path, [_case(**OUTSIDE)])
        assert ["Testtown", "testtown"] in entries

    def test_the_area_page_links_its_zone(self, tmp_path):
        _write_zoned(tmp_path)
        page = (tmp_path / "a" / "carlow" / "testtown.html").read_text()
        assert '<a href="../../z/testzone.html">Testzone</a>' in page

    def test_the_area_page_says_nothing_of_zones_when_none_hold_its_pins(self, tmp_path):
        _write_zoned(tmp_path, [_case(**OUTSIDE)])
        page = (tmp_path / "a" / "carlow" / "testtown.html").read_text()
        assert "supply zone" not in _text(page)
