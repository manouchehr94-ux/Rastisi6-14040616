"""Tiny CSS custom-property resolver for the contrast tests.

Only what the contrast contract needs: collect custom properties declared on a
selector, resolve ``var(--x[, fallback])`` chains, evaluate ``color-mix(in srgb …)``
and hand back a concrete hex colour. It never guesses: an unresolvable value raises,
so a token that stops being a plain colour fails loudly instead of being skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.core.color_utils import contrast_ratio, mix_hex, parse_css_color, to_hex

REPO = Path(__file__).resolve().parents[3]


def read_css(relative_path: str) -> str:
    text = (REPO / relative_path).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def iter_rules(css: str):
    """(selector, {property: value}) for every innermost ``selector{…}`` block."""
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = " ".join(match.group(1).split())
        decls = {}
        for part in match.group(2).split(";"):
            if ":" in part:
                name, value = part.split(":", 1)
                decls[name.strip()] = value.strip()
        yield selector, decls


def custom_properties(css: str, selector: str) -> dict:
    """Merge custom properties declared on every rule whose selector list contains ``selector``."""
    merged: dict = {}
    for sel, decls in iter_rules(css):
        if selector in [s.strip() for s in sel.split(",")]:
            merged.update({k: v for k, v in decls.items() if k.startswith("--")})
    return merged


def _split_args(text: str):
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return out


def resolve(value: str, props: dict, _depth: int = 0) -> str:
    """Resolve ``value`` to a hex colour using ``props`` as the custom-property scope."""
    if _depth > 12:
        raise ValueError(f"token cycle resolving {value!r}")
    value = value.strip().replace("!important", "").strip()
    var = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,(.*))?\)", value, flags=re.S)
    if var:
        name, fallback = var.group(1), var.group(2)
        if name in props:
            return resolve(props[name], props, _depth + 1)
        if fallback is not None:
            return resolve(fallback, props, _depth + 1)
        raise KeyError(f"{name} is not defined in this scope")
    mix = re.fullmatch(r"color-mix\(\s*in\s+srgb\s*,(.*)\)", value, flags=re.S)
    if mix:
        first, second = _split_args(mix.group(1))[:2]

        def part(text):
            m = re.fullmatch(r"(.*?)\s+(\d+(?:\.\d+)?)%", text.strip(), flags=re.S)
            return (m.group(1).strip(), float(m.group(2)) / 100.0) if m else (text.strip(), None)

        (c1, p1), (c2, p2) = part(first), part(second)
        if p1 is None and p2 is None:
            p1 = 0.5
        if p1 is None:
            p1 = 1.0 - p2
        return mix_hex(resolve(c1, props, _depth + 1), resolve(c2, props, _depth + 1), p1)
    return to_hex(parse_css_color(value))


def ratio(fg_value: str, bg_value: str, props: dict) -> float:
    return contrast_ratio(resolve(fg_value, props), resolve(bg_value, props))
