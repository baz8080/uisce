"""Every drill-down offers the page it has a permanent URL for.

The hash routes are not URLs a reader can keep or a crawler can index, so the
static page is the only durable address a county or an area has. The app is
where a reader already is when they want it, and the county's link lived in the
footer until 2026-08-26, where nothing gets clicked.

Source-level rather than executed: these are template strings assembled at
runtime, and what needs guarding is that the link is still written at all.
"""

from pathlib import Path

SITE_HTML = (Path(__file__).resolve().parent.parent / "src" / "uisce" / "site.html").read_text()


def _view(fn, until):
    """The body of one render function, so a claim about the county view cannot
    be satisfied by wording that only appears in the area view."""
    body = SITE_HTML[SITE_HTML.index(fn):]
    return body[: body.index(until)]


def _sub_line(view):
    """The `.sub` line under a drill-down heading — where the link lives."""
    return view.split('class="sub"')[1].split("</div>")[0]


def test_the_county_view_links_to_the_county_page():
    assert '<div class="sub"><a href="c/${county.toLowerCase()}.html">' in SITE_HTML


def test_the_county_label_claims_the_months_and_not_every_notice():
    """The county page caps its notice list at COUNTY_EVENTS_SHOWN and says so
    in its own "older notices not shown here" line, so a link promising every
    notice would be contradicted by the page it lands on. What that page really
    does carry that the view does not is every month — the same claim esb's
    makes, because the two stand in the same relation to their views."""
    label = _sub_line(_view("function renderCounty()", "function renderTop()"))
    assert "Every month for" in label
    assert "on one page" in label
    assert "Permanent link" not in label
    assert "Every notice ever recorded" not in SITE_HTML


def test_the_county_link_sits_under_the_heading_and_not_in_the_footer():
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


def test_the_area_view_links_to_the_area_page_when_there_is_one():
    """The gap this file used to record as accepted, now closed for the areas
    that name a place. An Electoral Division still has none, so the link is
    conditional on the slug — which the payload carries precisely because the
    app cannot derive it."""
    area_view = _view("function renderArea()", "// ---- routing ----")
    assert "t && t.slug ?" in area_view
    assert 'href="a/${areaCounty.toLowerCase()}/${t.slug}.html"' in area_view


def test_the_area_label_names_the_address_and_not_the_content():
    """The area page carries the same notices this view does, uncapped, so
    naming it for its content would promise a reader what they are already
    looking at — the same reason lifts says "permanent link" where esb and
    uisce name the months."""
    label = _sub_line(_view("function renderArea()", "// ---- routing ----"))
    assert "Permanent link to ${esc(name)}" in label
    assert "Every notice" not in label
