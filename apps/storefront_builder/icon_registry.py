"""Engine icon registry — the ONE place a built-in decorative icon is defined.

A section never embeds a fixed SVG: it stores an icon KEY (``settings.campaign_icon_key`` for the campaign panel today) and
the renderer resolves it here. The registry is generic and reusable by any section that wants a merchant-selectable icon;
it knows nothing about Ready Templates. Icons are drawn on a 64x64 grid with ``currentColor`` strokes, so their colour
always comes from the section's semantic colour settings (never from the SVG)."""

from __future__ import annotations

from django.utils.safestring import SafeString, mark_safe

#: key -> (merchant-facing Persian label, inner SVG markup). Inner markup is static, reviewed code (never merchant data).
_ICONS: dict[str, tuple[str, str]] = {
    "gift": ("هدیه", '<path d="M10 27h44v29H10z"/><path d="M7 18h50v11H7z"/><path d="M32 18v38"/>'
                     '<path d="M32 18c-6 0-14-2-14-8 0-4 3-6 7-6 6 0 7 8 7 14z"/><path d="M32 18c6 0 14-2 14-8 0-4-3-6-7-6-6 0-7 8-7 14z"/>'),
    "star": ("ستاره", '<path d="M32 7l7.6 15.4 17 2.5-12.3 12 2.9 17L32 45.9 16.8 54l2.9-17-12.3-12 17-2.5z"/>'),
    "sparkles": ("درخشش", '<path d="M26 9l4.8 13.6L44.4 27.4 30.8 32 26 45.6 21.2 32 7.6 27.4l13.6-4.8z"/>'
                          '<path d="M49 8v13M42.5 14.5h13"/><path d="M48 40v14M41 47h14"/>'),
    "shopping_bag": ("کیف خرید", '<path d="M12 22h40l-3 33H15z"/><path d="M22 22v-4a10 10 0 0120 0v4"/>'),
    "heart": ("قلب", '<path d="M32 55S7 40 7 23.5a12.5 12.5 0 0125-4 12.5 12.5 0 0125 4C57 40 32 55 32 55z"/>'),
    "tag": ("برچسب", '<path d="M7 7h23l27 27-23 23L7 30z"/><circle cx="19.5" cy="19.5" r="3.5"/>'),
    "percent": ("درصد تخفیف", '<circle cx="19" cy="19" r="8"/><circle cx="45" cy="45" r="8"/><path d="M49 13L15 51"/>'),
    "truck": ("ارسال", '<path d="M5 16h35v28H5z"/><path d="M40 26h12l8 10v8H40z"/><circle cx="18" cy="48" r="5"/><circle cx="48" cy="48" r="5"/>'),
    "fire": ("داغ", '<path d="M32 5c2 11 15 15 15 29a15 15 0 01-30 0c0-6 3-10 7-13 0 5 3 8 5 8 0-8-2-15 3-24z"/>'),
    "crown": ("تاج", '<path d="M7 46l4-27 15 14 6-19 6 19 15-14 4 27z"/><path d="M7 55h50"/>'),
}

ICON_KEYS: tuple[str, ...] = tuple(_ICONS)
DEFAULT_ICON_KEY = "gift"


def icon_choices() -> tuple[tuple[str, str], ...]:
    """``(key, label_fa)`` pairs in registry order — the Inspector's icon selector."""
    return tuple((key, label) for key, (label, _markup) in _ICONS.items())


def is_valid_icon_key(key: object) -> bool:
    return isinstance(key, str) and key in _ICONS


def icon_svg(key: object) -> SafeString:
    """The ``<svg>`` markup of a registered icon, or ``""`` for an unknown key (fail closed, never raises)."""
    if not is_valid_icon_key(key):
        return mark_safe("")
    markup = _ICONS[key][1]
    return mark_safe(
        '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{markup}</svg>'
    )
