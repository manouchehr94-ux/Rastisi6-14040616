"""Allowlist HTML sanitizer for email bodies (stdlib only).

Anything not on the allowlist is removed: tags are dropped (their text is kept, except for dangerous containers
whose whole content is dropped), attributes are dropped except a tiny allowlist, ``style``/``on*``/``class``/``id``
never survive, and ``href`` must be http(s)/mailto/tel (or, at template *save* time only, a bare ``{variable}``
placeholder that is re-validated after substitution at render time). There is no template language: variables
are plain ``{name}`` substitutions handled by ``template_service``; no Python/Jinja is ever evaluated."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset({
    "p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a", "h1", "h2", "h3", "blockquote", "hr",
    "span", "div", "table", "thead", "tbody", "tr", "td", "th",
})
VOID_TAGS = frozenset({"br", "hr"})
#: containers whose *content* is also discarded (never leak script/style text into the message)
DROP_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math", "title", "head"})
ALLOWED_ATTRS = {
    "a": {"href"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "p": {"dir"}, "div": {"dir"}, "span": {"dir"}, "li": {"dir"}, "h1": {"dir"}, "h2": {"dir"}, "h3": {"dir"},
}
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:")
_PLACEHOLDER_HREF = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")
_DIR_VALUES = {"rtl", "ltr", "auto"}
_SPAN_RE = re.compile(r"^\d{1,2}$")


def _clean_href(value: str, *, allow_placeholders: bool) -> str | None:
    value = (value or "").strip()
    # strip control chars / whitespace that browsers ignore inside a scheme ("java\tscript:")
    probe = re.sub(r"[\x00-\x20]+", "", value).lower()
    if allow_placeholders and _PLACEHOLDER_HREF.match(value):
        return value
    if probe.startswith(_SAFE_SCHEMES):
        return value
    return None


class _Sanitizer(HTMLParser):
    def __init__(self, *, allow_placeholders: bool):
        super().__init__(convert_charrefs=True)
        self.allow_placeholders = allow_placeholders
        self.out: list[str] = []
        self.open: list[str] = []
        self.skip_depth = 0
        self.skip_tag = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        if tag in DROP_CONTENT_TAGS:
            self.skip_depth, self.skip_tag = 1, tag
            return
        if tag not in ALLOWED_TAGS:
            return
        rendered = []
        for name, value in attrs:
            name = (name or "").lower()
            if name not in ALLOWED_ATTRS.get(tag, ()):
                continue
            if name == "href":
                href = _clean_href(value, allow_placeholders=self.allow_placeholders)
                if href is None:
                    continue
                rendered.append(f' href="{escape(href, quote=True)}"')
            elif name == "dir":
                if (value or "").lower() in _DIR_VALUES:
                    rendered.append(f' dir="{value.lower()}"')
            elif name in ("colspan", "rowspan"):
                if _SPAN_RE.match(value or ""):
                    rendered.append(f' {name}="{value}"')
        if tag == "a":
            rendered.append(' rel="noopener noreferrer"')
        self.out.append(f"<{tag}{''.join(rendered)}>")
        if tag not in VOID_TAGS:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS and not self.skip_depth:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth -= 1
            return
        if tag in VOID_TAGS or tag not in self.open:
            return
        # close any unclosed inner tags first so the output is always well-nested
        while self.open:
            top = self.open.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if not self.skip_depth:
            self.out.append(escape(data, quote=False))

    def handle_comment(self, data):  # comments (incl. conditional comments) are dropped
        return

    def close_all(self):
        while self.open:
            self.out.append(f"</{self.open.pop()}>")


def sanitize_html(markup: str, *, allow_placeholders: bool = False) -> str:
    parser = _Sanitizer(allow_placeholders=allow_placeholders)
    parser.feed(markup or "")
    parser.close()
    parser.close_all()
    return "".join(parser.out).strip()
