"""Every drill-down offers the page it has a permanent URL for.

The hash routes are not URLs a reader can keep or a crawler can index, so the
static page is the only durable address a county has. The app is where a reader
already is when they want it, and it lived in the footer until 2026-08-26,
where nothing gets clicked.

Source-level rather than executed: these are template strings assembled at
runtime, and what needs guarding is that the link is still written at all.
"""

from pathlib import Path

SITE_HTML = (Path(__file__).resolve().parent.parent / "src" / "uisce" / "site.html").read_text()


def test_the_county_view_links_to_the_county_page():
    assert '<div class="sub"><a href="c/${county.toLowerCase()}.html">' in SITE_HTML


def test_the_link_sits_under_the_heading_and_not_in_the_footer():
    """Placement is the point: above the month tabs, directly under the county
    name, the same position lifts and esb use."""
    head = SITE_HTML.index('<span class="pop">${c.pop.toLocaleString()}')
    link = SITE_HTML.index('<div class="sub"><a href="c/${county.toLowerCase()}.html">')
    tabs = SITE_HTML.index('<div class="months">${monthTabs(D.months, curMonth, "setMonth")}')
    assert head < link < tabs
    assert "countyHistoryLink" not in SITE_HTML


def test_an_overview_row_points_a_crawler_at_the_page_not_the_hash():
    """The row's href is what a crawler follows and what "copy link address"
    yields; the click handler is what keeps a real click inside the app. uisce
    pointed its href at the hash, so the page was reachable only from the
    footer link and areas.html."""
    assert "const href = `c/${name.toLowerCase()}.html`;" in SITE_HTML
    assert '<a href="${href}" onclick="${jump}; return false;">' in SITE_HTML


def test_the_area_view_offers_nothing_because_there_is_nothing_to_offer():
    """Accepted gap, not an oversight: an area is reachable only as
    #area/<county>/<code> and has no page of its own. Recorded here so that
    building area pages is remembered as the thing that closes it."""
    area_view = SITE_HTML[SITE_HTML.index("function renderArea()"):]
    area_view = area_view[:area_view.index("// ---- routing ----")]
    assert 'href="c/' not in area_view
    assert 'href="a/' not in area_view
