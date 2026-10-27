"""Shared static readers for the V5-02A shell tests (no Django, no database, no browser)."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"
EDITOR_HTML = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "editor.html").read_text(encoding="utf-8")
STUDIO_CSS = (STATIC / "r4_studio.css").read_text(encoding="utf-8")
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")

V5_MARKER = "V5-02A — Studio shell layer"


def v5_layer() -> str:
    """The appended V5 shell layer: from the opening of its banner comment to the end of the stylesheet."""
    return STUDIO_CSS[STUDIO_CSS.rindex("/* ====", 0, STUDIO_CSS.index(V5_MARKER)):]


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def parse_rules(css: str):
    """Return [(media_query_or_None, selector_list, declarations)] for the V5 layer (one level of @media nesting)."""
    css = strip_comments(css)
    rules, media, depth, buf, head = [], None, 0, "", ""
    for ch in css:
        if ch == "{":
            text = buf.strip()
            if text.startswith("@media"):
                media = text
            else:
                head = text
            buf, depth = "", depth + 1
        elif ch == "}":
            if buf.strip():
                rules.append((media, head, buf.strip()))
            buf, depth = "", depth - 1
            if depth == 0:
                media = None
        else:
            buf += ch
    return rules


def declarations(rules, selector: str, media=None) -> str:
    """Concatenated declarations of every rule whose selector list contains `selector` (exact) within the given media query."""
    out = []
    for rule_media, selectors, decls in rules:
        if rule_media == media and selector in [s.strip() for s in selectors.split(",")]:
            out.append(decls)
    return ";".join(out)


def rail_and_float_markup() -> str:
    start = EDITOR_HTML.index('<aside class="rs-rail"')
    rail = EDITOR_HTML[start:EDITOR_HTML.index("</aside>", start)]
    fstart = EDITOR_HTML.index('<div class="rs-float-bar"')
    float_bar = EDITOR_HTML[fstart:EDITOR_HTML.index("</div>", fstart)]
    return rail + float_bar
