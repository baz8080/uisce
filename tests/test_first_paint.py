"""The index paints nothing below its header until its first render has run.

frontend-notes.md, "The first paint waits for the data" (2026-10-02). The
guard is source-level, like the permalink tests: the head script and the CSS
rule are statusui's and tested there; what this repo can lose is the marker,
the attributes and the release.
"""

import re

from uisce.site import AREA_HTML, AREAS_HTML, COUNTY_HTML, SITE_HTML, page_html

APP = SITE_HTML.read_text()
HEAD = APP[: APP.index("</head>")]


def _fn(name):
    body = APP[APP.index(f"function {name}("):]
    return body[: body.index("\n}\n")]


def test_the_head_carries_the_wait_marker_ahead_of_the_styles():
    assert HEAD.count("<!--UI-WAIT-->") == 1
    assert HEAD.index("<!--UI-WAIT-->") < HEAD.index("<style>")


def test_the_built_index_holds_the_skeleton_back_from_the_first_paint():
    built = page_html(SITE_HTML, {})
    assert "<!--UI-WAIT-->" not in built
    assert 'classList.add("wait")' in built
    assert "html.wait" in built


def test_what_the_first_render_fills_or_pushes_is_marked():
    assert '<div id="overview" data-wait>' in APP
    assert "<footer data-wait>" in APP


def test_render_releases_the_page_before_it_measures_the_month_strip():
    body = _fn("render")
    assert "pending(shardPending());" in body
    assert body.index("pending(shardPending());") < body.index("revealMonthTab(")


def test_only_the_view_whose_own_shard_is_loading_holds_the_footer():
    body = _fn("shardPending")
    assert 'HISTORY_STATE[areaCounty] === "loading"' in body
    assert 'COUNTY_STATE[county] === "loading"' in body


def test_a_page_with_no_script_to_release_it_never_waits():
    for page in (AREAS_HTML, COUNTY_HTML, AREA_HTML):
        text = page.read_text()
        assert "UI-WAIT" not in text
        assert not re.search(r"\bdata-wait\b", text)
