"""No page script may redeclare a global from statusui's shared bundle.

The bundle is inlined ahead of each page's own script, so a redeclaration
silently shadows the shared helper on that page alone.

The shared names come from `statusui.js_globals()`, never from reading
`ui.js`: the bundle is two files since the caption listener moved to
`caption.js`, and a test that reads one of them passes by seeing fewer names -
a guard failing open, silently, exactly when it stops covering something. The
page's own side keeps DECL, which reads `let` and `const` too: this site's
scripts use them and the shared ES5 bundle never will.
"""

import re
from pathlib import Path

import pytest
import statusui

PKG = Path(__file__).resolve().parent.parent / "src" / "uisce"

DECL = r"^(?:function|var|let|const)\s+(\w+)"

# A page takes the whole bundle or, if all it calls is the day-cell caption
# listener, that alone.
MARKERS = ("<!--UI-JS-->", "<!--UI-JS-CAPTION-->")


@pytest.mark.parametrize("page", ["site.html", "county.html", "areas.html"])
def test_site_script_redeclares_no_shared_global(page):
    shared = statusui.js_globals()
    assert "bindDayCaption" in shared, "the bundle's second file is missing"
    text = (PKG / page).read_text()
    marker = next((m for m in MARKERS if m in text), None)
    if marker is None:
        return  # no shared script on this page, nothing to collide with
    own = text.split(marker, 1)[1]
    mine = set(re.findall(DECL, own, re.M))
    assert not (mine & shared), f"{page} redeclares {sorted(mine & shared)}"
