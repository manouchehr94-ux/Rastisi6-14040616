"""Merchant-editable SEMANTIC colours for the Universal Storefront Engine.

A design colour stored in a section setting is never a free CSS string. It is one of

* ``""``                 — "automatic": the engine / theme default applies,
* ``"token:<name>"``     — a role of the Store's own appearance palette
                           (``primary``, ``accent``, ``surface``, ``tone-3`` …),
* ``"#RRGGBB"``          — an explicit custom colour.

Tokens resolve to the CSS custom properties the appearance system already
publishes on ``<html>`` (``--brand-*``, ``--theme-*``), so a palette change in
Global Design recolours every setting that points at a role, and the accessible
foreground derivation (``--brand-*-fg``) keeps applying. Custom hex values get
their foreground from the same WCAG helper the background block uses.
"""

from __future__ import annotations

import re

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

#: token -> (css variable of the colour, css variable of its accessible foreground)
SEMANTIC_COLOR_TOKENS: dict[str, tuple[str, str]] = {
    "primary": ("--brand-primary", "--brand-primary-fg"),
    "accent": ("--brand-accent", "--brand-accent-fg"),
    "secondary": ("--brand-secondary", "--brand-secondary-fg"),
    "surface": ("--brand-surface", "--brand-text"),
    "background": ("--brand-background", "--brand-text"),
    "text": ("--brand-text", "--brand-surface"),
    "muted": ("--brand-muted", "--brand-muted-fg"),
    "border": ("--brand-border", "--brand-text"),
    "tone-1": ("--brand-tone-1", "--brand-tone-1-fg"),
    "tone-2": ("--brand-tone-2", "--brand-tone-2-fg"),
    "tone-3": ("--brand-tone-3", "--brand-tone-3-fg"),
    "tone-4": ("--brand-tone-4", "--brand-tone-4-fg"),
    "tone-5": ("--brand-tone-5", "--brand-tone-5-fg"),
    "footer": ("--theme-footer-bg", "--theme-footer-text"),
    "header": ("--theme-header-bg", "--theme-header-text"),
    "price": ("--theme-price-text", "--brand-surface"),
}

SEMANTIC_COLOR_TOKEN_LABELS_FA: dict[str, str] = {
    "primary": "رنگ اصلی برند",
    "accent": "رنگ تأکید",
    "secondary": "رنگ ثانویه",
    "surface": "سطح (کارت/پنل)",
    "background": "پس‌زمینه صفحه",
    "text": "رنگ متن",
    "muted": "متن کم‌رنگ",
    "border": "حاشیه",
    "tone-1": "طیف پالت ۱",
    "tone-2": "طیف پالت ۲",
    "tone-3": "طیف پالت ۳",
    "tone-4": "طیف پالت ۴",
    "tone-5": "طیف پالت ۵",
    "footer": "پس‌زمینه فوتر",
    "header": "پس‌زمینه هدر",
    "price": "رنگ قیمت",
}


class SemanticColorError(ValueError):
    """The stored colour is neither empty, a known token, nor a #RRGGBB hex."""


def clean_semantic_color(raw: object) -> str:
    """Normalise a raw value to ``""`` / ``"token:<name>"`` / ``"#RRGGBB"`` (upper-case hex)."""
    if raw is None:
        return ""
    value = str(raw).strip()
    if not value:
        return ""
    if value.startswith("token:"):
        name = value[len("token:"):]
        if name in SEMANTIC_COLOR_TOKENS:
            return value
        raise SemanticColorError("نقش رنگیِ انتخاب‌شده نامعتبر است")
    if _HEX_RE.match(value):
        return value.upper()
    raise SemanticColorError("رنگ باید یک کد #RRGGBB معتبر یا یکی از رنگ‌های پالت باشد")


def semantic_color_css(value: object) -> str:
    """CSS value for a cleaned semantic colour (``var(--x)`` / hex) or ``""``."""
    value = _safe(value)
    if not value:
        return ""
    if value.startswith("token:"):
        return f"var({SEMANTIC_COLOR_TOKENS[value[6:]][0]})"
    return value


def semantic_foreground_css(value: object) -> str:
    """Accessible foreground for text drawn ON this colour, or ``""`` when automatic."""
    value = _safe(value)
    if not value:
        return ""
    if value.startswith("token:"):
        return f"var({SEMANTIC_COLOR_TOKENS[value[6:]][1]})"
    from apps.core.color_utils import best_foreground

    return best_foreground(value)


def semantic_color_choices() -> list[tuple[str, str]]:
    return [(f"token:{key}", SEMANTIC_COLOR_TOKEN_LABELS_FA[key]) for key in SEMANTIC_COLOR_TOKENS]


#: token -> where its CURRENT hex lives in the resolved appearance (R4-09: the picker shows a real swatch per role)
_BASE_COLOR_TOKENS = ("primary", "secondary", "accent", "background", "surface", "text", "muted", "border")
_THEME_ROLE_TOKENS = {"header": "header_bg", "footer": "footer_bg", "price": "price"}


def token_hex_map(appearance_config: dict | None) -> dict[str, str]:
    """``{"token:<role>": "#RRGGBB"}`` — what every palette role currently resolves to for this Draft.

    DISPLAY data for the colour picker's swatches only: the stored value of a role stays ``token:<role>`` (so a palette
    change still recolours it) and the renderer keeps resolving it through the ``--brand-*`` CSS variables. Uses the very
    same resolvers the storefront CSS is generated from (``appearance_registry``), never a second palette source."""
    from . import appearance_registry

    config = appearance_config or {}
    colors = appearance_registry.resolve_colors(config)
    roles = appearance_registry.resolve_theme_roles(config)
    tones = appearance_registry.resolve_section_tones(config)
    out: dict[str, str] = {}
    for name in _BASE_COLOR_TOKENS:
        if _HEX_RE.match(str(colors.get(name, ""))):
            out[f"token:{name}"] = str(colors[name]).upper()
    for token, role in _THEME_ROLE_TOKENS.items():
        if _HEX_RE.match(str(roles.get(role, ""))):
            out[f"token:{token}"] = str(roles[role]).upper()
    for index, tone in enumerate(tones, start=1):
        if _HEX_RE.match(str(tone)):
            out[f"token:tone-{index}"] = str(tone).upper()
    return out


def _safe(value: object) -> str:
    try:
        return clean_semantic_color(value)
    except SemanticColorError:
        return ""
