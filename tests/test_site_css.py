"""Guards against a regression of the `hidden`-vs-`display` bug fixed 2026-08-06
— see notes/frontend-notes.md. For each element either page hides, works out
which `display` actually wins once `hidden` is set, in every media context the
stylesheet defines. Only `display` matters here, so the parser is deliberately
small — it reads the two files it is pointed at, not CSS in general.
"""

import re

from uisce.site import AREAS_HTML, SITE_HTML


def _stylesheet(path):
    css = "\n".join(re.findall(r"<style>(.*?)</style>", path.read_text(), re.S))
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _block(css, open_brace):
    """The text inside the block starting at `open_brace`, and the index after it."""
    depth, i = 0, open_brace
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace + 1:i], i + 1
        i += 1
    raise AssertionError("unbalanced braces in stylesheet")


def _rules(css, media=None):
    """(selector, display, important, media) for every rule that sets `display`,
    in source order, descending through @media blocks."""
    out, i = [], 0
    while (brace := css.find("{", i)) != -1:
        prelude = css[i:brace].strip()
        body, i = _block(css, brace)
        if prelude.startswith("@"):
            out += _rules(body, media if media is not None else prelude)
            continue
        # the last one wins within a block, as it does in the cascade
        decls = re.findall(r"(?:^|;)\s*display\s*:\s*([^;]+)", body)
        if decls:
            value = decls[-1].strip()
            important = "!important" in value
            value = value.replace("!important", "").strip()
            out += [(sel.strip(), value, important, media) for sel in prelude.split(",")]
    return out


SIMPLE = r"\*|#[\w-]+|\.[\w-]+|\[[^\]]*\]|::?[\w-]+|[a-zA-Z][\w-]*"


def _matches(sel, el):
    """Does `sel` select `el`, an element carrying the `hidden` attribute?

    Only the subject — the last compound selector — is read. An ancestor part is
    assumed to match, which can only make the test stricter than the browser."""
    subject = re.split(r"[\s>+~]+", sel.strip())[-1]
    for simple in re.findall(SIMPLE, subject):
        if simple == "*":
            continue
        if simple.startswith("#"):
            if simple[1:] != el.get("id"):
                return False
        elif simple.startswith("."):
            if simple[1:] not in el.get("classes", ()):
                return False
        elif simple.startswith("["):
            # the only attribute either page selects on
            if simple.strip("[]").split("=")[0].strip() != "hidden":
                return False
        elif simple.startswith(":"):
            return False   # :hover, :focus-visible — not a resting state
        elif simple != el.get("tag"):
            return False
    return True


def _specificity(sel):
    return (len(re.findall(r"#[\w-]+", sel)),
            len(re.findall(r"\.[\w-]+|\[[^\]]*\]|:(?!:)[\w-]+", sel)),
            len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", sel)))


def _display(rules, el, media):
    """The `display` the cascade gives `el` in `media`, or None where no author
    rule applies and the UA stylesheet's `[hidden] { display: none }` stands."""
    best, winner = None, None
    for order, (sel, value, important, rule_media) in enumerate(rules):
        if rule_media not in (None, media) or not _matches(sel, el):
            continue
        key = (important, _specificity(sel), order)
        if best is None or key > best:
            best, winner = key, value
    return winner


def _contexts(rules):
    """The base cascade, plus each media block laid over it."""
    return [None] + sorted({m for *_, m in rules if m is not None})


def _assert_hidden_stays_hidden(path, elements):
    rules = _rules(_stylesheet(path))
    for el in elements:
        for media in _contexts(rules):
            display = _display(rules, el, media)
            assert display in (None, "none"), (
                f"{path.name}: {el} is display:{display} while [hidden] is set"
                f"{'' if media is None else ' under ' + media}"
                " — the UA rule for the hidden attribute needs an author rule to"
                " beat this one, or the element stays on screen"
            )


class TestHiddenViews:
    """Every view is switched by toggling `hidden`; nothing may out-specify it."""

    def _view_ids(self):
        # read off the router's own map, so a view added later is covered here
        block = re.search(r"VIEW_EL = \{(.*?)\}", SITE_HTML.read_text(), re.S)
        ids = re.findall(r':\s*"([\w-]+)"', block.group(1))
        assert len(ids) >= 4
        return ids

    def test_every_view_container_is_hidden_when_the_attribute_is_set(self):
        _assert_hidden_stays_hidden(
            SITE_HTML, [{"tag": "div", "id": vid} for vid in self._view_ids()])

    def test_the_overview_still_reorders_itself_on_a_phone(self):
        # the flex column carries the narrow-screen ordering; the fix must not
        # have been to delete it
        rules = _rules(_stylesheet(SITE_HTML))
        narrow = [m for m in _contexts(rules) if m and "640px" in m]
        assert narrow, "the narrow-screen media query went missing"
        assert _display(rules, {"tag": "div", "id": "overview"}, narrow[0]) == "none"
        visible = [v for sel, v, _, m in rules
                   if m == narrow[0] and sel.strip() == "#overview"]
        assert visible == ["flex"]

    def test_the_search_filter_can_still_hide_a_row(self):
        # areas.html hides list rows, sections and the jump nav the same way
        _assert_hidden_stays_hidden(AREAS_HTML, [
            {"tag": "li"}, {"tag": "li", "classes": {"unplaced"}},
            {"tag": "section"}, {"tag": "nav"},
        ])
