"""The national open-now list.

The overview tile counted the open notices and nothing listed them: a reader
found them one county at a time. Source-level, like test_permalink_affordance:
the view is template strings assembled at runtime, and what needs guarding is
that the route, the way in and the shared grouping are still there.
"""

import re
from pathlib import Path

SITE_HTML = (Path(__file__).resolve().parent.parent / "src" / "uisce" / "site.html").read_text()


def _fn(name):
    body = SITE_HTML[SITE_HTML.index(f"function {name}(") :]
    return body[: body.index("\n}\n")]


def test_the_route_and_the_container_exist():
    assert '<div id="openview" hidden></div>' in SITE_HTML
    assert 'open: "openview"' in re.search(r"VIEW_EL = \{(.*?)\}", SITE_HTML).group(1)
    assert 'location.hash === "#open" ? "open"' in SITE_HTML


def test_the_tile_is_the_way_in():
    tile = re.search(r'<a class="tile" href="#open"[^>]*>(.*?)</a>', _fn("renderOverview"))
    assert tile and "open right now" in tile.group(1)


def test_both_lists_group_the_same_way():
    # one grouping for the county card and the national list, or the two drift
    assert "openGroups(c)" in _fn("openSection")
    assert "openGroups(c)" in _fn("renderOpen")
    assert "OPEN_NOTE" in _fn("openSection") and "OPEN_NOTE" in _fn("renderOpen")


def test_a_county_heading_is_a_real_link_that_stays_in_the_app():
    view = _fn("renderOpen")
    assert 'href="c/${name.toLowerCase()}.html"' in view
    assert "if (newTab(event)) return true; goCounty(" in view
