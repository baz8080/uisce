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
    listing misses the second name in `let a = 1, esc = 2;` - and a guard that
    misses a name fails open.

    Column zero only, which is what top level means here: site.html's
    `const when` and `const num` sit inside function bodies, scoped to them,
    shadowing nothing. The `=` in the second branch is what makes a name a
    declaration rather than a mention: a shared helper passed by reference
    reads as `, esc]`.
    """
    n = re.escape(name)
    return bool(
        re.search(rf"^(?:async\s+)?(?:function|var|let|const|class)\s+{n}\b", script, re.M)
        or re.search(rf"^(?:var|let|const)\b[^\n]*,\s*{n}\s*=", script, re.M)
    )


def unreadable_declarations(script):
    """Top-level declarations this guard cannot read, so it can say so.

    It reads a line at a time, which covers every form these pages use - a
    multi-line object literal still declares its one name on the first line.
    What it cannot follow is a declarator list continued onto the next line,
    or a destructuring pattern. Neither appears in any of the three sites
    today; the point is that the day one does, this stops rather than quietly
    missing whatever the second name was.
    """
    for line in re.findall(r"^(?:var|let|const)\b[^\n]*", script, re.M):
        # A trailing comma inside an open bracket is a literal continuing, not
        # a second name: `const SEVLABEL = { outage: "...",` is one declaration.
        open_brackets = sum(line.count(c) for c in "{[(") - sum(line.count(c) for c in "}])")
        if (line.rstrip().endswith(",") and open_brackets <= 0) or re.match(
            r"^(?:var|let|const)\s*[\[{]", line
        ):
            yield line.strip()


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
    assert list(unreadable_declarations(own)) == [], f"{page}: see the docstring"
    clashes = sorted(name for name in shared if declares(own, name))
    assert not clashes, f"{page} redeclares {clashes}"
