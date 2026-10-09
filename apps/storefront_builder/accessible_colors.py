"""Accessible *usage* colours for the dynamic storefront palette.

A merchant's brand colours (``Palette`` / ``color_overrides`` / ``theme_overrides``)
are identity: they are stored and shown in the Builder exactly as chosen and are
never rewritten. But a brand colour that is a fine *fill* is often an unreadable
*text* colour (a gold accent price on white is 2.3:1) and the pairing a template
declares (``header_text`` on ``header_bg``) is only as good as the merchant's
choice. This module is the one place that turns raw palette colours into the
colours the storefront actually paints text with:

  * ``*_text``      – the brand hue, minimally nudged (towards black or white,
                      hue preserved) until it reaches 4.5:1 on EVERY surface it
                      can sit on (page background, card surface, themed card);
  * ``*_fg``        – black/white, whichever has the higher WCAG contrast on a
                      filled control (always >= 4.5:1 — worst case ~4.58:1);
  * ``primary_hover``/``primary_hover_fg`` – the hover/active background and the
                      foreground re-derived FOR THAT background, so a state change
                      can never leave an inherited foreground on a new background;
  * ``header_text`` / ``nav_text`` / ``footer_text`` – the region text colour
                      against its own region background.

A colour that already passes is returned unchanged, so well-designed Ready
Templates render byte-identically; only unsafe combinations move, and only as
far as needed. The same ``accessible_pairs`` list is what the contrast tests
iterate for all 50 Ready Templates, so "what the renderer promises" and "what
the tests check" cannot drift apart.
"""

from __future__ import annotations

from apps.core.color_utils import (
    best_foreground,
    contrast_ratio,
    ensure_contrast,
    mix_hex,
    state_pair,
)

#: Normal-text AA is 4.5:1; derive with a small margin so 8-bit rounding in any
#: browser colour pipeline can never land a hair under the bar.
TARGET = 4.55
MIN_TEXT = 4.5
#: Text on the header gets hover/tint states (a tint toward the ink colour is painted behind it), which shifts the
#: effective contrast down by roughly 10-15%; derive it with that headroom so the hover state stays >= 4.5:1 too.
HEADER_TARGET = 5.5
#: backgrounds of the always-dark header shell (``.gh-shell--dark`` in storefront_builder.css)
DARK_SHELL_SURFACES = ("#121218", "#1B1B24", "#21180A", "#090909", "#111111")  # + the fixed-dark luxury hero stage


def build_accessible_theme(colors: dict, roles: dict, tones: tuple | list | None = None) -> dict:
    """``colors``: resolved palette (primary/secondary/accent/background/surface/
    text/muted/border). ``roles``: resolved theme roles (header_bg/header_text/
    nav_bg/nav_text/card_bg/footer_bg/footer_text/price). Returns hex strings."""
    surfaces = [colors["background"], colors["surface"], roles["card_bg"]]

    def on_surfaces(color):
        return ensure_contrast(color, surfaces, TARGET)

    hover_bg, hover_fg = state_pair(colors["primary"], min_ratio=TARGET)
    out = {
        "text": on_surfaces(colors["text"]),
        "muted_text": on_surfaces(colors["muted"]),
        "primary_text": on_surfaces(colors["primary"]),
        "secondary_text": on_surfaces(colors["secondary"]),
        "accent_text": on_surfaces(colors["accent"]),
        "price_text": on_surfaces(roles["price"]),
        "primary_fg": best_foreground(colors["primary"]),
        "secondary_fg": best_foreground(colors["secondary"]),
        "accent_fg": best_foreground(colors["accent"]),
        "muted_fg": best_foreground(on_surfaces(colors["muted"])),
        # A primary->secondary gradient carries ONE label colour. Black/white can't serve two arbitrary stops
        # (e.g. near-black -> pale gold), so the label follows the primary stop and the END stop is the
        # secondary colour minimally nudged until that same label reads on it too.
        "gradient_fg": best_foreground(colors["primary"]),
        "gradient_end": ensure_contrast(colors["secondary"], [best_foreground(colors["primary"])], TARGET),
        # the dark header shell (`.gh-shell--dark`) has FIXED chrome colours, independent of the palette
        "primary_text_on_dark": ensure_contrast(colors["primary"], DARK_SHELL_SURFACES, HEADER_TARGET),
        "primary_hover": hover_bg,
        "primary_hover_fg": hover_fg,
        "header_text": ensure_contrast(roles["header_text"], [roles["header_bg"]], HEADER_TARGET),
        "header_muted_text": ensure_contrast(colors["muted"], [roles["header_bg"]], HEADER_TARGET),
        "nav_text": ensure_contrast(roles["nav_text"], [roles["nav_bg"]], HEADER_TARGET),
        "footer_text": ensure_contrast(roles["footer_text"], [roles["footer_bg"]], TARGET),
    }
    # palette-tone bands (``data-bg-mode="palette"``): text on tone N is black or white, whichever reads better
    out["tone_fgs"] = [best_foreground(t) for t in (tones or ())]
    # footer secondary text (links / small print) sits on the same background
    # secondary footer text keeps the hierarchy by being the footer text softened toward the footer background
    out["footer_muted_text"] = ensure_contrast(
        mix_hex(out["footer_text"], roles["footer_bg"], 0.8), [roles["footer_bg"]], TARGET)
    return out


def accessible_pairs(colors: dict, roles: dict, theme: dict | None = None, tones=None):
    """Every (name, foreground, background, minimum ratio) the storefront relies on.

    This is the contract: tests assert each pair, and the runtime audit checks the
    rendered result. Adding a new derived variable means adding its pair here.
    """
    theme = theme or build_accessible_theme(colors, roles, tones)
    pairs = []
    for surface_name, surface in (
        ("background", colors["background"]),
        ("surface", colors["surface"]),
        ("card", roles["card_bg"]),
    ):
        for key in ("text", "muted_text", "primary_text", "secondary_text", "accent_text", "price_text"):
            pairs.append((f"{key} on {surface_name}", theme[key], surface, MIN_TEXT))
    for key, bg_key in (("primary", "primary"), ("secondary", "secondary"), ("accent", "accent")):
        pairs.append((f"{key}_fg on {key}", theme[f"{key}_fg"], colors[bg_key], MIN_TEXT))
    for surface in DARK_SHELL_SURFACES:
        pairs.append((f"primary_text_on_dark on {surface}", theme["primary_text_on_dark"], surface, MIN_TEXT))
    pairs.append(("muted_fg on muted_text", theme["muted_fg"], theme["muted_text"], MIN_TEXT))
    pairs.append(("gradient_fg on primary", theme["gradient_fg"], colors["primary"], MIN_TEXT))
    pairs.append(("gradient_fg on gradient_end", theme["gradient_fg"], theme["gradient_end"], MIN_TEXT))
    pairs.append(("primary_hover_fg on primary_hover", theme["primary_hover_fg"], theme["primary_hover"], MIN_TEXT))
    pairs.append(("header_text on header_bg", theme["header_text"], roles["header_bg"], MIN_TEXT))
    pairs.append(("header_muted_text on header_bg", theme["header_muted_text"], roles["header_bg"], MIN_TEXT))
    pairs.append(("nav_text on nav_bg", theme["nav_text"], roles["nav_bg"], MIN_TEXT))
    pairs.append(("footer_text on footer_bg", theme["footer_text"], roles["footer_bg"], MIN_TEXT))
    for index, tone in enumerate(tones or ()):
        pairs.append((f"tone_{index + 1}_fg on tone_{index + 1}", theme["tone_fgs"][index], tone, MIN_TEXT))
    pairs.append(("footer_muted_text on footer_bg", theme["footer_muted_text"], roles["footer_bg"], MIN_TEXT))
    return pairs


def failing_pairs(colors: dict, roles: dict, theme: dict | None = None, tones=None):
    return [
        (name, fg, bg, contrast_ratio(fg, bg), need)
        for name, fg, bg, need in accessible_pairs(colors, roles, theme, tones)
        if contrast_ratio(fg, bg) + 1e-9 < need
    ]
