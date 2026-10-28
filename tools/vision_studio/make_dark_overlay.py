"""Generate ``vision-r4-dark.css``: a dark re-colouring of the R4 Studio's own components for RastiSi Vision Studio.

The R4 editor/studio stylesheets hard-code a LIGHT palette (white cards, dark ink). Vision Studio re-uses those very components (the
section Inspector, the Global Design panel, the structure rows, the dialogs) inside its dark shell, so this tool reads the R4 stylesheets
and emits, for every rule that paints a colour, a twin rule scoped under ``.vs`` whose colours are mapped to the Vision dark palette.
Layout declarations are never copied: only colour-bearing declarations, so the R4 geometry stays exactly the R4 one.

    python tools/vision_studio/make_dark_overlay.py

Re-run it whenever r4_editor.css / r4_studio.css / r4_color_picker.css change (the output is committed, like scope_reference_css.py's)."""

import colorsys
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "apps" / "storefront_builder" / "static" / "storefront_builder"
SOURCES = ["r4_editor.css", "r4_studio.css", "r4_color_picker.css"]
OUT = STATIC / "vision" / "vision-r4-dark.css"

HUE = 218 / 360          # the reference's navy
BG_PROPS = re.compile(r"^(background|background-color|background-image)$")
BORDER_PROPS = re.compile(r"^(border(-[a-z]+)*(-color)?|outline(-color)?|border-color)$")
TEXT_PROPS = re.compile(r"^(color|fill|stroke|caret-color|text-decoration-color|accent-color)$")
COLOR_RE = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b|rgba?\([^)]*\)|\bwhite\b|\bblack\b", re.I)


def parse_color(token):
    t = token.strip().lower()
    if t == "white":
        return 1.0, 1.0, 1.0, 1.0
    if t == "black":
        return 0.0, 0.0, 0.0, 1.0
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    m = re.match(r"rgba?\(([^)]*)\)", t)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        if len(parts) < 3 or any("var(" in p for p in parts):
            return None
        vals = []
        for p in parts[:3]:
            vals.append(float(p[:-1]) / 100 if p.endswith("%") else float(p) / 255)
        a = 1.0
        if len(parts) > 3:
            a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
        return vals[0], vals[1], vals[2], a
    return None


def fmt(r, g, b, a):
    r, g, b = (max(0, min(255, round(v * 255))) for v in (r, g, b))
    if a >= 0.999:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d,%d,%d,%.3g)" % (r, g, b, a)


def map_surface(rgba):
    r, g, b, a = rgba
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l < 0.55:
        return None                      # already dark / a real accent: keep
    if s < 0.3 or l > 0.9:               # neutral light surface -> navy surface (lighter source = darker result)
        nl = 0.10 + (1 - l) * 0.55
        nr, ng, nb = colorsys.hls_to_rgb(HUE, nl, 0.32)
    else:                                # pastel tint -> same hue, dark and muted
        nr, ng, nb = colorsys.hls_to_rgb(h, 0.18 + (1 - l) * 0.3, min(0.4, s * 0.5))
    return nr, ng, nb, a


def map_border(rgba):
    r, g, b, a = rgba
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l < 0.6 and s > 0.25:
        return None
    if l < 0.4:
        return None
    nl = 0.20 + (1 - l) * 0.35
    nr, ng, nb = colorsys.hls_to_rgb(HUE, nl, 0.25)
    return nr, ng, nb, a


def map_text(rgba):
    r, g, b, a = rgba
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l > 0.8:
        return None                      # already light (e.g. white on an accent button)
    if s < 0.25:                         # neutral ink -> light ink / muted
        nl = 0.97 - l * 0.45 if l < 0.5 else 0.78 - (l - 0.5) * 0.3
        nr, ng, nb = colorsys.hls_to_rgb(HUE, min(nl, 0.97), 0.22)
        return nr, ng, nb, a
    if l < 0.62:                         # saturated mid/dark text (links, danger): lift it for the dark surface
        nr, ng, nb = colorsys.hls_to_rgb(h, 0.76, min(1.0, s))
        return nr, ng, nb, a
    return None


def remap_value(prop, value, kind):
    if "var(" in value and not COLOR_RE.search(value):
        return value
    mapper = {"bg": map_surface, "border": map_border, "text": map_text}[kind]
    changed = [False]

    def repl(m):
        parsed = parse_color(m.group(0))
        if parsed is None:
            return m.group(0)
        out = mapper(parsed)
        if out is None:
            return m.group(0)
        changed[0] = True
        return fmt(*out)

    new = COLOR_RE.sub(repl, value)
    return new if changed[0] else value


def split_declarations(body):
    out, cur, depth, quote = [], "", 0, None
    for ch in body:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur += ch
        elif ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == ";" and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def transform_body(body):
    kept = []
    for decl in split_declarations(body):
        if ":" not in decl:
            continue
        prop, value = decl.split(":", 1)
        prop = prop.strip().lower()
        important = re.search(r"!\s*important\s*$", value, re.I)
        raw = re.sub(r"!\s*important\s*$", "", value, flags=re.I).strip()
        if BG_PROPS.match(prop):
            kind = "bg"
        elif BORDER_PROPS.match(prop):
            kind = "border"
        elif TEXT_PROPS.match(prop):
            kind = "text"
        else:
            continue
        if "url(" in raw and "gradient" not in raw:
            continue
        new = remap_value(prop, raw, kind)
        if new != raw:
            kept.append(f"{prop}:{new}{' !important' if important else ''}")
    return ";".join(kept)


def scope_selector(sel):
    sel = sel.strip()
    if not sel or sel.startswith(("@", "from", "to")) or re.match(r"^\d+%$", sel):
        return None
    if sel.startswith(".rs-studio"):
        return ".rs-studio.vs" + sel[len(".rs-studio"):]
    return ".vs " + sel


def parse_blocks(css, start=0, end=None):
    """Yield (prelude, body) top-level blocks of ``css[start:end]``; body of an at-rule is returned raw."""
    end = len(css) if end is None else end
    i = start
    while i < end:
        while i < end and css[i].isspace():
            i += 1
        if i >= end:
            break
        if css.startswith("/*", i):
            j = css.find("*/", i + 2)
            i = end if j < 0 else j + 2
            continue
        j = i
        depth = 0
        while j < end and css[j] != "{":
            if css[j] == ";" and depth == 0:     # a statement at-rule (@import ...)
                break
            j += 1
        if j >= end or css[j] == ";":
            i = j + 1
            continue
        prelude = css[i:j].strip()
        k, d = j + 1, 1
        while k < end and d:
            if css.startswith("/*", k):
                m = css.find("*/", k + 2)
                k = end if m < 0 else m + 2
                continue
            if css[k] == "{":
                d += 1
            elif css[k] == "}":
                d -= 1
            k += 1
        yield prelude, css[j + 1:k - 1]
        i = k


def emit(css, out):
    for prelude, body in parse_blocks(css):
        if prelude.startswith("@media") or prelude.startswith("@supports"):
            inner = []
            emit(body, inner)
            if inner:
                out.append(prelude + "{" + "\n".join(inner) + "}")
        elif prelude.startswith("@"):
            continue                              # keyframes / font-face / etc.
        else:
            tb = transform_body(body)
            if not tb:
                continue
            sels = [scope_selector(s) for s in re.split(r",(?![^(]*\))", prelude)]
            sels = [s for s in sels if s]
            if sels:
                out.append(",".join(sels) + "{" + tb + "}")


def main():
    parts = ["/* RastiSi Vision Studio — dark re-colouring of the R4 Studio components.\n   GENERATED by tools/vision_studio/make_dark_overlay.py from "
             + ", ".join(SOURCES) + ".\n   Colour-bearing declarations only (layout is never copied). Do not hand-edit; tune in vision.css. */"]
    for name in SOURCES:
        text = (STATIC / name).read_text(encoding="utf-8")
        out = []
        emit(text, out)
        parts.append(f"/* ---- {name} ---- */")
        parts.extend(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
