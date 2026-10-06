"""index.html carries the data the first overview render reads; data.js the rest.

frontend-notes.md, "The first render's data is inline" (2026-10-02). The payload
is derived once in write_site and split there, so what these hold is the split:
the inline part can only be a subset of data.js, nothing in it can close the
script element, and the page loads data.js after drawing rather than before.
"""

import json
import re

from conftest import site_case as _case
from test_site import AFTER_MAY, SA_INDEX, TOWNS, _open

from uisce.site import SITE_HTML, build_site, first_render_payload, inline_json, write_site

APP = SITE_HTML.read_text()


def _site():
    rows = [_case(), _open(id=2, reference_num="CAR00000002")]
    site = build_site(rows, SA_INDEX, AFTER_MAY, TOWNS)
    for key in ("recurrence_report", "history", "notice_text", "feed"):
        site.pop(key)
    for county in site["counties"].values():
        county.pop("towns")
        county.pop("resolved")
    return site


def _inline(page):
    inline = re.search(r"<script>window\.UISCE_DATA = (.*?);</script>", page, re.S)
    return json.loads(inline.group(1))


def test_the_first_render_keeps_the_newest_month_and_the_month_lists():
    site = _site()
    first = first_render_payload(site)
    assert set(first) == {
        "generated", "generated_iso", "data_as_of_iso", "months", "last_30", "mains_km",
        "national", "counties",
    }
    assert first["months"] == site["months"] == ["2026-04", "2026-05", "2026-06"]
    assert set(first["national"]) == {"2026-06"}
    assert set(first["counties"]["Carlow"]) == {
        "pop", "mains_km", "last_30", "open_total", "months"}
    assert set(first["counties"]["Carlow"]["months"]) == {"2026-06"}


def test_it_is_a_subset_of_what_data_js_carries():
    site = _site()
    first = first_render_payload(site)
    carlow, full = first["counties"]["Carlow"], site["counties"]["Carlow"]
    assert carlow["months"]["2026-06"] == full["months"]["2026-06"]
    assert carlow["pop"] == full["pop"] and carlow["open_total"] == full["open_total"]
    assert first["national"]["2026-06"] == site["national"]["2026-06"]
    assert full["open"] and "open" not in carlow


def test_a_field_added_to_the_county_lands_in_the_first_render_not_out_of_it():
    site = _site()
    site["counties"]["Carlow"]["slug"] = "carlow"
    assert first_render_payload(site)["counties"]["Carlow"]["slug"] == "carlow"


def test_a_less_than_sign_never_reaches_the_script_element():
    text = inline_json({"t": "</script><!-- x", "n": 1})
    assert "<" not in text
    assert json.loads(text) == {"t": "</script><!-- x", "n": 1}


def test_the_built_page_inlines_the_first_render_and_data_js_stays_whole(tmp_path):
    site = _site()
    expected = json.loads(inline_json(first_render_payload(site)))
    sizes = write_site(site, tmp_path, TOWNS)
    page = (tmp_path / "index.html").read_text()
    assert _inline(page) == expected
    assert sizes["first_render"] > 0
    full = json.loads((tmp_path / "data.js").read_text().split("=", 1)[1].rstrip(";"))
    carlow = full["counties"]["Carlow"]
    assert carlow["open"] and set(carlow["months"]) == set(site["months"])


def test_the_page_no_longer_waits_on_data_js_to_draw():
    assert '<script src="data.js">' not in APP
    inline = APP.index("window.UISCE_DATA = <!--FIRST-RENDER-->")
    assert inline < APP.index("<!--UI-JS-->") < APP.index("const FIRST = window.UISCE_DATA;")


def test_data_js_is_loaded_after_the_first_render_and_a_view_that_needs_it_waits():
    assert APP.rstrip().endswith("route();\nloadAll();\n</script>\n</body>\n</html>")
    assert 'loadShard(DATA_STATE, "all", "data.js" + cacheBust(D),' in APP
    guard = "if (needsAll() && D === FIRST) return renderWaiting();"
    assert APP.index("function render() {") < APP.index(guard)
    needs = APP[APP.index("function needsAll()"):].split("}")[0]
    for view in ('"county"', '"open"', '(view === "overview" && curMonth !== LATEST)'):
        assert view in needs
    assert '"area"' not in needs


def test_a_data_js_landing_after_the_timeout_is_still_adopted():
    render = APP[APP.index("function render() {"):]
    assert render.index("adopt(window.UISCE_DATA)") < render.index("return renderWaiting();")
    assert 'if (DATA_STATE.all === "ok") D = ' not in APP


def test_an_older_data_js_never_moves_the_page_back():
    adopt = APP[APP.index("function adopt(full) {"):]
    assert adopt.index("full.generated_iso < FIRST.generated_iso") < adopt.index("D = full;")
