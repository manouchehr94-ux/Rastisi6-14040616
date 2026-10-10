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


def _safe(value: object) -> str:
    try:
        return clean_semantic_color(value)
    except SemanticColorError:
        return ""
