"""View model of the generic ``decorative_strip`` section.

Pure functions: stored (sparse) settings + an already ownership-checked image URL in, the
inline custom properties / flags the template renders out. Colours are semantic (palette role |
custom hex | automatic) and resolve to the appearance CSS variables, so a palette change recolours
the strip and the accessible foreground derivation keeps applying."""

from __future__ import annotations

from .section_registry import _DECORATIVE_STRIP_DEFAULTS
from .semantic_colors import semantic_color_css, semantic_foreground_css

_FIT_CSS = {"cover": "cover", "contain": "contain", "stretch": "100% 100%", "auto": "auto"}
_ALIGN_CSS = {"start": "flex-start", "center": "center", "end": "flex-end"}


def effective_settings(settings: dict | None) -> dict:
    return {**_DECORATIVE_STRIP_DEFAULTS, **(settings or {})}


def build_view(settings: dict | None, image_url: str | None = None) -> dict:
    """``{"enabled", "style", "pattern", "bleed", "hide", "text"}`` for ``decorative_strip.html``."""
    cfg = effective_settings(settings)
    mode = cfg["background_mode"]
    bleed = bool(cfg["bleed"])
    css: list[str] = [
        f"--ds-h-d:{cfg['desktop_height']}px",
        f"--ds-h-t:{cfg['tablet_height']}px",
        f"--ds-h-m:{cfg['mobile_height']}px",
        f"--ds-r:{0 if bleed else cfg['radius']}px",
        f"--ds-ja:{_ALIGN_CSS[cfg['alignment']]}",
    ]
    background = semantic_color_css(cfg["background_color"]) if mode in ("solid", "palette", "pattern", "image") else ""
    if mode == "image" and not image_url:
        mode_fill = background or "var(--brand-surface)"
    else:
        mode_fill = background or ("var(--brand-tone-1)" if mode == "palette" else "var(--brand-surface)")
    css.append(f"--ds-bg:{mode_fill}")
    if mode == "image" and image_url:
        safe_url = image_url.replace("'", "%27").replace(")", "%29")
        css.append(f"--ds-img:url('{safe_url}')")
        css.append(f"--ds-fit:{_FIT_CSS[cfg['image_fit']]}")
        css.append(f"--ds-pos:{cfg['image_position_x']}% {cfg['image_position_y']}%")
        css.append(f"--ds-repeat:{cfg['image_repeat']}")
    elif mode == "pattern":
        css.append("--ds-repeat:repeat")
    # Foreground: explicit, else the accessible pair of the fill colour, else the page text colour.
    foreground = semantic_color_css(cfg["foreground_color"])
    if not foreground:
        foreground = semantic_foreground_css(cfg["background_color"]) if cfg["background_color"] else ""
    css.append(f"--ds-fg:{foreground or 'var(--brand-text)'}")
    opacity = int(cfg["overlay_opacity"])
    if opacity > 0:
        overlay = semantic_color_css(cfg["overlay_color"]) or "var(--brand-text)"
        css.append(f"--ds-ov:color-mix(in srgb, {overlay} {opacity}%, transparent)")
    if cfg["border_width"] and not bleed:
        css.append(f"--ds-bw:{cfg['border_width']}px")
        css.append(f"--ds-bc:{semantic_color_css(cfg['border_color']) or 'var(--brand-border)'}")
    if cfg["shadow_enabled"] and not bleed:
        base = semantic_color_css(cfg["shadow_color"])
        color = f"color-mix(in srgb, {base} 40%, transparent)" if base else "color-mix(in srgb, var(--brand-text) 18%, transparent)"
        blur = int(cfg["shadow_blur"])
        css.append(f"--ds-sh:0 {max(1, blur // 4)}px {blur}px {color}")
    hidden = [name for name, key in (("desktop", "visible_desktop"), ("tablet", "visible_tablet"),
                                     ("mobile", "visible_mobile")) if not cfg[key]]
    return {
        "enabled": bool(cfg["enabled"]),
        "style": ";".join(css),
        "pattern": cfg["pattern_slug"] if mode == "pattern" else "",
        "bleed": bleed,
        "hide": " ".join(hidden),
        "text": cfg["optional_text"],
    }
