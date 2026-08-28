"""No page script may redeclare a global from statusui's shared bundle.

The bundle is inlined ahead of each page's own script, so a redeclaration
silently shadows the shared helper on that page alone.

The shared names come from `statusui.js_globals()`, never from reading
`ui.js`: the bundle is two files since the caption listener moved to
`caption.js`, and a test that reads one of them passes by seeing fewer names -
a guard failing open, silently, exactly when it stops covering something.

The page's own side reads `let` and `const` as well as `function` and `var`:
this site's scripts use them and the shared ES5 bundle never will.
"""

import re
from pathlib import Path

import pytest
import statusui

PKG = Path(__file__).resolve().parent.parent / "src" / "uisce"

# A page takes the whole bundle or, if all it calls is the day-cell caption
# listener, that alone. From statusui, not spelled out here: a marker it
# renamed would leave this test looking for a string no page carries, and
# returning early because it found nothing to check.
MARKERS = (statusui.UI_JS, statusui.UI_JS_CAPTION)


def declares(script, name):
    """Does this script declare `name` at the top level?

    Asked per name rather than by listing what the script declares, because
    listing misses the second name in `let a = 1, b = 2;` - and a guard that
    misses a name fails open.

    Column zero only, which is what top level means in these files: `const when`
    inside a function body is scoped to that function and shadows nothing. This
    page has two of those, and allowing indentation failed on both.
    """
    n = re.escape(name)
    if re.search(rf"^(?:function|var|let|const)\s+{n}\b", script, re.M):
        return True
    # a later declarator in one statement: `let a = 1, name = 2;`
    return any(
        re.search(rf",\s*{n}\s*(?:=|[,;]|$)", statement)
        for statement in re.findall(r"^(?:var|let|const)\b[^;]*", script, re.M)
    )


# area.html included: it is a real template (site.py renders one per area) and
# the likeliest first taker of the caption marker, so leaving it off the list
# would ship its script unchecked.
@pytest.mark.parametrize("page", ["site.html", "county.html", "area.html", "areas.html"])
def test_site_script_redeclares_no_shared_global(page):
    shared = statusui.js_globals()
    assert "bindDayCaption" in shared, "the bundle's second file is missing"
    text = (PKG / page).read_text()
    marker = next((m for m in MARKERS if m in text), None)
    if marker is None:
        return  # no shared script on this page, nothing to collide with
    own = text.split(marker, 1)[1]
    clashes = sorted(name for name in shared if declares(own, name))
    assert not clashes, f"{page} redeclares {clashes}"
