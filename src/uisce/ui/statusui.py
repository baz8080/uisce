"""Build helpers shared by the status sites.

Vendored from baz8080/statusui — edit there, then run scripts/sync-ui.sh.
Standard library only, Python 3.9 syntax: the consumers keep both floors.

The one that matters is `assemble`: it inlines base.css and ui.js into a page
template at the <!--UI-CSS--> and <!--UI-JS--> markers. Inlined, not linked,
because every page is entered cold from a search result and a shared
stylesheet would cost each of those readers a second request.
"""

from __future__ import annotations

import html
import json
import math
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).parent
UI_CSS, UI_JS = "<!--UI-CSS-->", "<!--UI-JS-->"

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Said on a day cell built from part of a day. Plain words on purpose: it is
# read by someone wondering why their place looks quiet. Mirrored in ui.js.
PARTIAL_NOTE = " — only part of this day was recorded"


def base_css():
    return (HERE / "base.css").read_text(encoding="utf-8")


def ui_js():
    return (HERE / "ui.js").read_text(encoding="utf-8")


def assemble(template, markers=None):
    """Fill a page template: the shared CSS and JS, then each <!--NAME--> in `markers`."""
    page = template.replace(UI_CSS, base_css()).replace(UI_JS, ui_js())
    for name, text in (markers or {}).items():
        page = page.replace(f"<!--{name}-->", text)
    return page


def slug(name):
    """URL-safe, lowercase, fadas folded to ASCII rather than dropped."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "-" for c in folded.lower()).strip("-")


def month_label(ym):
    return f"{MONTH_NAMES[int(ym[5:7]) - 1]} {ym[:4]}"


def dumps(obj):
    # Default separators spend a byte on every comma and colon in the payload.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def when(ts, year=False):
    """'2026-08-16T20:21' -> '16 Aug, 20:21', or with the year before the comma."""
    if not ts:
        return ""
    mon = MONTH_NAMES[int(ts[5:7]) - 1][:3]
    return f"{int(ts[8:10])} {mon}{' ' + ts[:4] if year else ''}, {ts[11:16]}"


def half_up(x):
    # JS Math.round rounds a .5 up; Python's round() goes to even. The pages
    # format the same figure on both sides, so they have to agree.
    return math.floor(x + 0.5)


def tenth(x):
    # JS toFixed rounds a tie up, "%.1f" goes to even, and x * 10 can cross a tie
    # that neither side sees; Decimal(float) is the double both are looking at.
    return Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def days(n):
    if n < 2:
        return "1 day"
    if n < 60:
        return f"{n} days"
    return f"{n / 30.44:.1f} months"


def hours(h, days_fmt=None):
    """Mirrors ui.js fmtHours; `days_fmt` formats the whole-days branch."""
    if h < 1:
        return f"{half_up(h * 60)} min"
    if h < 48:
        return f"{tenth(h)} h" if h < 10 else f"{half_up(h)} h"
    n = half_up(h / 24)
    if days_fmt:
        return days_fmt(n)
    return "1 day" if n == 1 else f"{n} days"


def day_cells(cells, ym, partial, labels, qualify=lambda ch: True):
    """The day bar for a static page: one <i> per cell, class b<ch>, caption in data-cap.

    `labels` maps a cell character to its caption text; `qualify` says whether a
    part-day suffix applies to that cell (no data and not-yet days take none).
    """
    out = []
    for i, ch in enumerate(cells):
        day = f"{ym}-{i + 1:02d}"
        cap = f"{day}: {labels[ch]}"
        if qualify(ch) and day in partial:
            cap += PARTIAL_NOTE
        out.append(f'<i class="b{ch}" data-cap="{html.escape(cap)}"></i>')
    return "".join(out)


def sitemap(base_url, paths, lastmod):
    urls = "".join(
        f"<url><loc>{html.escape(f'{base_url}/{p}')}</loc><lastmod>{lastmod}</lastmod></url>"
        for p in paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )


def robots(base_url):
    return f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"


def size_report(site_dir, budget, pages_dir, pages_label, extra=()):
    """What a reader downloads before they touch anything, as (bytes, text).

    Printed on every build: the payload is the constraint these sites keep
    having to defend, and a regression belongs in the build log. `extra` is
    [(filename, note)] for on-demand files worth listing after the initial load.
    """
    site_dir = Path(site_dir)
    initial = {p: (site_dir / p).stat().st_size for p in ("index.html", "data.js")}
    shards = sorted((site_dir / "h").glob("*.js"), key=lambda p: -p.stat().st_size)
    pages = list((site_dir / pages_dir).glob("*.html"))
    lines = [
        f"  {'index.html':<16}{initial['index.html'] / 1024:8.1f} KB",
        f"  {'data.js':<16}{initial['data.js'] / 1024:8.1f} KB",
        f"  {'initial load':<16}{sum(initial.values()) / 1024:8.1f} KB"
        f"   (budget {budget / 1024:.1f} KB)",
    ]
    for name, note in extra:
        lines.append(f"  {name:<16}{(site_dir / name).stat().st_size / 1024:8.1f} KB   ({note})")
    lines.append(
        f"  {pages_label:<16}{sum(p.stat().st_size for p in pages) / 1024:8.1f} KB"
        f"   ({len(pages)} files)"
    )
    if shards:
        lines.append(
            f"  {'shards':<16}{sum(p.stat().st_size for p in shards) / 1024:8.1f} KB"
            f"   ({len(shards)} files, largest {shards[0].name} at"
            f" {shards[0].stat().st_size / 1024:.1f} KB)"
        )
    return sum(initial.values()), "\n".join(lines)
