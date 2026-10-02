"""Long static lists skip layout and paint while off screen.

frontend-notes.md, "Long static lists skip what is off screen" (2026-10-02).
Source-level, like the first-paint tests: what this repo can lose is the rule,
its estimate, and the one list it must never reach.
"""

import re

from uisce.site import AREAS_HTML, SITE_CSS, _area_index_html

CSS = SITE_CSS.read_text()
AREAS = AREAS_HTML.read_text()


def _rule(css, selector):
    """Every declaration block whose selector is exactly `selector`, joined."""
    return " ".join(re.findall(rf"(?:^|[}}\s]){re.escape(selector)}\s*{{([^}}]*)}}", css))


def test_a_notice_row_is_skipped_while_off_screen_and_remembers_its_real_height():
    rule = _rule(CSS, "ul.notices > li")
    assert "content-visibility: auto" in rule
    assert re.search(r"contain-intrinsic-size: auto \d+px", rule)


def test_the_paint_containment_leaves_room_for_a_focus_ring():
    assert "overflow-clip-margin" in _rule(CSS, "ul.notices > li")


def test_the_two_column_area_list_is_never_skipped():
    assert "content-visibility" not in re.sub(r"section\[data-county\][^}]*}", "", AREAS)
    assert not re.search(r"ul\.areas[^{]*{[^}]*content-visibility", CSS + AREAS)


def test_a_directory_section_is_sized_from_its_row_count():
    assert "section[data-county] { content-visibility: auto;" in AREAS
    assert "var(--r)" in AREAS and "var(--n)" in AREAS


def test_the_section_carries_its_rows_and_its_two_column_rows():
    areas = [(f"T{i}", f"A{i}", 1, 1) for i in range(7)]
    html = _area_index_html([("Cork", areas)])
    assert 'style="--n:7;--r:4"' in html


def test_a_search_draws_every_section_because_a_drawn_one_keeps_its_height():
    assert ".searching section[data-county] { content-visibility: visible; }" in AREAS
    assert 'document.body.classList.toggle("searching", !!s);' in AREAS
