"""The shared UI under src/uisce/ui is a vendored copy of ../statusui/ui.

Edits belong upstream, then `scripts/sync-ui.sh`. Compared file by file when
the sibling checkout is present; skipped otherwise.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "uisce"
VENDORED = PKG / "ui"
UPSTREAM = ROOT.parent / "statusui" / "ui"

DECL = r"^(?:function|var|let|const)\s+(\w+)"


def test_matches_upstream():
    if not UPSTREAM.is_dir():
        pytest.skip(f"no sibling checkout at {UPSTREAM}")
    for src in sorted(UPSTREAM.iterdir()):
        if src.name.startswith((".", "__pycache__")):
            continue
        copy = VENDORED / src.name
        assert copy.exists(), f"{src.name} not vendored; run scripts/sync-ui.sh"
        assert copy.read_bytes() == src.read_bytes(), (
            f"{src.name} differs from ../statusui; run scripts/sync-ui.sh"
        )


@pytest.mark.parametrize("page", ["site.html", "county.html", "areas.html"])
def test_site_script_redeclares_no_shared_global(page):
    shared = set(re.findall(DECL, (VENDORED / "ui.js").read_text(), re.M))
    text = (PKG / page).read_text()
    if "<!--UI-JS-->" not in text:
        return  # no shared script on this page, nothing to collide with
    own = text.split("<!--UI-JS-->", 1)[1]
    mine = set(re.findall(DECL, own, re.M))
    assert not (mine & shared), f"{page} redeclares {sorted(mine & shared)}"
