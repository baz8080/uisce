"""No page script may redeclare a global from statusui's ui.js.

The shared file is inlined ahead of each page's own script, so a redeclaration
silently shadows the shared helper on that page alone.
"""

import re
from pathlib import Path

import pytest
import statusui

PKG = Path(__file__).resolve().parent.parent / "src" / "uisce"

DECL = r"^(?:function|var|let|const)\s+(\w+)"


@pytest.mark.parametrize("page", ["site.html", "county.html", "areas.html"])
def test_site_script_redeclares_no_shared_global(page):
    shared_js = (Path(statusui.__file__).parent / "ui.js").read_text()
    shared = set(re.findall(DECL, shared_js, re.M))
    text = (PKG / page).read_text()
    if "<!--UI-JS-->" not in text:
        return  # no shared script on this page, nothing to collide with
    own = text.split("<!--UI-JS-->", 1)[1]
    mine = set(re.findall(DECL, own, re.M))
    assert not (mine & shared), f"{page} redeclares {sorted(mine & shared)}"
