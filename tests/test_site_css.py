"""What the cascade actually does on a built page.

Two things live here. The `hidden`-vs-`display` guard, against a regression of
the bug fixed 2026-08-06 — see notes/frontend-notes.md — which works out which
`display` wins once `hidden` is set, in every media context the stylesheet
defines. And the shared drill-down sub line, which is the first rule this repo
asserts *applies* rather than merely exists.

The parser is deliberately small: it reads the files it is pointed at, not CSS
in general, and resolves one property at a time.
"""

import re

import pytest
import statusui

from uisce.site import (
    AREA_HTML,
    AREAS_HTML,
    SITE_CSS,
    SITE_HTML,
    area_page_html,
    page_html,
)


def _stylesheet(path):
    # the page as built, with the shared base.css and site.css inlined: the
    # template alone carries only that page's own rules
    css = "\n".join(re.findall(r"<style>(.*?)</style>", page_html(path, {}), re.S))
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


def _rules(css, prop="display", media=None):
    """(selector, value, important, media) for every rule that sets `prop`, in
    source order, descending through @media blocks."""
    out, i = [], 0
    while (brace := css.find("{", i)) != -1:
        prelude = css[i:brace].strip()
        body, i = _block(css, brace)
        if prelude.startswith("@"):
            out += _rules(body, prop, media if media is not None else prelude)
            continue
        # the last one wins within a block, as it does in the cascade
        decls = re.findall(rf"(?:^|;)\s*{re.escape(prop)}\s*:\s*([^;]+)", body)
        if decls:
            value = decls[-1].strip()
            important = "!important" in value
            value = value.replace("!important", "").strip()
            out += [(sel.strip(), value, important, media) for sel in prelude.split(",")]
    return out


SIMPLE = r"\*|#[\w-]+|\.[\w-]+|\[[^\]]*\]|::?[\w-]+|[a-zA-Z][\w-]*"


def _matches(sel, el):
    """Does `sel` select `el`?

    Only the subject — the last compound selector — is read; an ancestor or
    sibling part is assumed to match. That can only make a test stricter than
    the browser, so where adjacency is the point (`.chead + .sub`) the markup is
    checked separately rather than inferred from a match here."""
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


def _winning(rules, el, media):
    """The value the cascade gives `el` in `media`, or None where no author rule
    applies — for `display`, that is where the UA stylesheet's
    `[hidden] { display: none }` stands."""
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
            display = _winning(rules, el, media)
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
        assert _winning(rules, {"tag": "div", "id": "overview"}, narrow[0]) == "none"
        visible = [v for sel, v, _, m in rules
                   if m == narrow[0] and sel.strip() == "#overview"]
        assert visible == ["flex"]

    def test_the_search_filter_can_still_hide_a_row(self):
        # areas.html hides list rows, sections and the jump nav the same way
        _assert_hidden_stays_hidden(AREAS_HTML, [
            {"tag": "li"}, {"tag": "li", "classes": {"unplaced"}},
            {"tag": "section"}, {"tag": "nav"},
        ])


class TestTheSharedSubLineRule:
    """`.chead + .sub` styles the line under a drill-down heading — on this site
    the "Permanent link to …" line on every area page — and it reaches here only
    through the statusui pin in `uv.lock`.

    When it moved upstream on 2026-08-26 the local copy had to be kept back for
    one commit, because `uv.lock` can only track statusui's `main`: dropping
    both at once would have left that line unstyled on the deployed site with
    every test still green. Nothing asserted a rule *applied*, only that files
    said what they said.

    These assert the three things that make one apply, as far as a build can
    reach without a browser — the page renders an element for the rule to match,
    the rule is in the stylesheet that page inlines, and the cascade leaves its
    values standing against everything else selecting `.sub`.
    """

    ELEMENT = {"tag": "div", "classes": {"sub"}}

    def _rules_for(self, prop):
        return _rules(_stylesheet(AREA_HTML), prop)

    def test_the_page_renders_an_element_the_rule_can_match(self):
        """A rule with nothing to match is a rule that does not apply. The
        lookahead keeps the closing tag the `.chead`'s own, so a nested div
        could not fake the adjacency."""
        body = area_page_html("Kerry", "Abbeydorney", 528, [])
        assert re.search(
            r'<div class="chead">(?:(?!</?div).)*</div>\s*<div class="sub"',
            body,
            re.S,
        ), body[:300]

    @pytest.mark.parametrize(
        "prop,expected", [("color", "var(--muted)"), ("font-size", "12.5px")]
    )
    def test_the_shared_values_win_in_every_media_context(self, prop, expected):
        """base.css also carries `header .sub`, which sets both of these. It
        loses on specificity — one class and one type against two classes — and
        this is what says so rather than assuming it."""
        rules = self._rules_for(prop)
        assert rules, f"nothing sets {prop} on a .sub; the shared rule never arrived"
        for media in _contexts(rules):
            assert _winning(rules, self.ELEMENT, media) == expected, (
                f"{prop} on the area page's sub line resolves to "
                f"{_winning(rules, self.ELEMENT, media)!r}, not {expected!r}"
                f"{'' if media is None else ' under ' + media}"
            )

    def test_a_page_can_still_take_one_of_the_properties_back(self):
        """area.html sets `margin-bottom: 20px` on the same selector. Equal
        specificity, later in source, so it wins — which is the override
        mechanism working, and the reason this test names the two properties
        above rather than asserting the whole shared block survives."""
        rules = self._rules_for("margin-bottom")
        assert _winning(rules, self.ELEMENT, None) == "20px"
        shared = [v for sel, v, _, _ in rules if sel == ".chead + .sub"]
        assert shared == ["16px", "20px"], shared

    def test_the_rule_is_upstream_and_has_not_been_copied_back(self):
        """Three byte-identical copies across three repos is what moving it to
        statusui existed to end."""
        assert ".chead + .sub" in statusui.base_css()
        assert ".chead + .sub" not in SITE_CSS.read_text()
