"""Acceptance Batch 3 (post-U11) — Ready Template Gallery real visual
previews.

Root gap (per the master contract): the Gallery card's only "preview" was
three flat color swatches (``storefront_template_gallery``'s
``_palette_swatch`` — still present, only for the small legacy strip) —
a meaningless placeholder that told a merchant nothing about a Template's
actual design language.

Architecture chosen: a **deterministic, registry-driven inline SVG**
schematic, computed fresh on every Gallery request from real
``LayoutPresetDefinition``/``appearance_registry``/``global_region_registry``
data — never a screenshot, never a second hand-maintained mini-renderer,
never a database row.

Why this over a captured screenshot:
- Runtime Gallery requests must never need Playwright/Selenium/a browser
  process, and must stay cheap (no live storefront render, no nested
  public-store request, no N+1 queries) — this function does zero I/O and
  zero DB queries; it only reads already-imported, in-memory Python
  registry objects.
- A generated screenshot file would need a key+version-keyed manifest, a
  regeneration command, and would silently go stale the moment a Preset's
  Python definition changes without someone re-running that command. This
  approach can never go stale — it *is* a direct function of the exact
  same registry data ``apply_preset`` reads, so it updates itself the
  moment a Preset's real definition changes.
- It is not "arbitrary decorative art": every visual fact drawn below
  traces to a real registered value — the resolved palette/theme-role
  colors (``appearance_registry.resolve_colors``/``resolve_theme_roles``,
  the exact same functions the real renderer's context processors call),
  the preset's real ``pages["home"]`` section composition and order, and
  ``appearance.density`` for row spacing. No product photography, no
  brand copy, no third-party imagery — pure abstract shapes and color.

This module never branches on a Preset/Template *key* (``dense_marketplace``,
``dark_digital``, ...) — only on already-registered, cross-Preset
*section types* (``section_registry``) and *global region variant keys*
(``global_region_registry`` — the same generic dispatch axis the real
renderer already uses via ``resolve_global_renderer_template``), so this
stays a generic function of the engine's real vocabulary, not a
per-Template special case.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import appearance_registry
from ..layout_preset_registry import LayoutPresetDefinition
from ..section_registry import CARD_AWARE_SECTION_KEYS

_VIEWBOX_W = 300
_VIEWBOX_H = 188
_HEADER_H = 24
_SECOND_ROW_H = 11  # a second header row (e.g. a category rail) when present
_FOOTER_H = 22
_ANNOUNCE_H = 7
_MAX_DISPLAYED_SECTIONS = 6

#: Acceptance Batch 3 — the ONE known, real exception to "header/nav chrome
#: color always follows the resolved palette role colors": the registered
#: ``dark_tech`` global header/footer variant renders its own always-dark
#: chrome via a dedicated CSS shell (``storefront_builder.css``'s
#: ``.gh-shell--dark``), independent of the active palette — confirmed in
#: the Acceptance Batch 1 ledger entry (Issue 2 audit). These are the exact
#: literal hex values that CSS rule already declares, not invented
#: schematic colors, so `dark_tech`'s preview matches what a merchant
#: really sees regardless of which (always-light, per the 8 official
#: Templates) palette a Ready Template pairs it with. Keyed by the
#: registered *variant key* (shared across any current/future Preset that
#: selects this header/footer variant), never by a Preset key.
_DARK_TECH_CHROME = {
    "bg": "#121218",  # --gh-bg
    "surface": "#1b1b24",  # --gh-surface
    "ink": "#f1f0f5",  # --gh-ink
    "border": "#2a2a37",  # --gh-border
}

#: Section types that render a grid of product cards — reuses the existing
#: cross-cutting allowlist (``section_registry.CARD_AWARE_SECTION_KEYS``)
#: rather than a second, possibly-diverging list.
_PRODUCT_GRID_KEYS = CARD_AWARE_SECTION_KEYS

#: Section-type → schematic archetype + relative height weight (taller
#: weight = visually dominant, matching how that section type actually
#: reads on a real page — a hero is a large block, a trust-badge row is
#: thin). Any section type not listed here (rare/text-heavy types not used
#: by any of the 8 official Ready Templates today) safely falls back to a
#: plain content block — never a crash, matching this engine's established
#: "unknown key degrades safely" convention (``render_service``).
_ARCHETYPE_WEIGHTS = {
    "hero_banner": ("hero", 2.4),
    "multi_banner": ("banner_pair", 1.5),
    "image_text": ("image_text", 1.5),
    "story_rail": ("chip_row", 0.85),
    "category_grid": ("chip_row", 0.85),
    "brand_carousel": ("pill_row", 0.7),
    "trust_features": ("icon_row", 0.7),
    "newsletter": ("bar_cta", 0.8),
    "promo_cards": ("card_row", 1.1),
    "testimonials": ("quote_row", 1.1),
}


def _chip(x, y, w, h, rx, fill, stroke=None):
    stroke_attr = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}"{stroke_attr} fill="{fill}"/>'


def _line(x, y, w, h, fill):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" fill="{fill}"/>'


def _header_markup(preset: LayoutPresetDefinition, colors: dict, roles: dict, radius: float) -> tuple[str, float, str]:
    header = preset.header or {}
    variant_key = header.get("header_variant")
    chrome = _DARK_TECH_CHROME if variant_key == "dark_tech" else None
    header_bg = chrome["surface"] if chrome else roles["header_bg"]
    header_ink = chrome["ink"] if chrome else roles["header_text"]
    page_bg = chrome["bg"] if chrome else colors["background"]

    parts = []
    y = 0.0
    if header.get("announcement_enabled"):
        parts.append(_chip(0, y, _VIEWBOX_W, _ANNOUNCE_H, 0, roles.get("nav_bg", header_bg)))
        y += _ANNOUNCE_H

    parts.append(_chip(0, y, _VIEWBOX_W, _HEADER_H, 0, header_bg))
    # logo mark
    parts.append(_chip(14, y + 7, 26, 10, min(radius, 4), colors["primary"]))
    # nav lines — count reflects real header toggles (show_search/account/wishlist/cart)
    nav_toggle_count = sum(1 for key in ("show_search", "show_account", "show_wishlist", "show_cart") if header.get(key, True))
    nav_x = _VIEWBOX_W - 16
    for _ in range(max(2, min(4, nav_toggle_count))):
        nav_x -= 22
        parts.append(_line(nav_x, y + 10, 16, 4, header_ink))
    y += _HEADER_H

    # marketplace_search_first is the one registered header variant whose
    # own real structure (label: "بازارگاهی (جستجو-محور)") adds a dense
    # secondary category rail under the main row — reflected here as a
    # second thin strip, not invented per-Template.
    if variant_key == "marketplace_search_first":
        parts.append(_chip(0, y, _VIEWBOX_W, _SECOND_ROW_H, 0, roles.get("nav_bg", header_bg)))
        for i in range(5):
            parts.append(_line(10 + i * 34, y + 4, 26, 3, header_ink))
        y += _SECOND_ROW_H

    return "".join(parts), y, page_bg


def _footer_markup(preset: LayoutPresetDefinition, colors: dict, roles: dict, top_y: float) -> str:
    footer = preset.footer or {}
    variant_key = footer.get("footer_variant")
    chrome = _DARK_TECH_CHROME if variant_key == "dark_tech" else None
    footer_bg = chrome["surface"] if chrome else roles["footer_bg"]
    footer_ink = chrome["ink"] if chrome else roles["footer_text"]

    parts = [_chip(0, top_y, _VIEWBOX_W, _FOOTER_H, 0, footer_bg)]
    column_count = sum(
        1 for key in ("show_about", "show_contact", "show_categories", "show_quick_links", "show_social")
        if footer.get(key, True)
    )
    columns = max(2, min(4, column_count)) if column_count else 3
    col_w = (_VIEWBOX_W - 28) / columns
    for i in range(columns):
        cx = 14 + i * col_w
        parts.append(_line(cx, top_y + 7, col_w * 0.6, 3, footer_ink))
        parts.append(_line(cx, top_y + 13, col_w * 0.4, 2.5, footer_ink))
    return "".join(parts)


def _section_row(archetype: str, x: float, y: float, w: float, h: float, colors: dict, radius: float) -> str:
    rx = min(radius / 1.6, h / 2, 8)
    surface, primary, accent, muted, border = colors["surface"], colors["primary"], colors["accent"], colors["muted"], colors["border"]

    if archetype == "hero":
        parts = [_chip(x, y, w, h, rx, primary)]
        parts.append(_chip(x + 16, y + h * 0.32, w * 0.45, h * 0.14, 2, "rgba(255,255,255,.85)"))
        parts.append(_chip(x + 16, y + h * 0.55, w * 0.28, h * 0.11, 2, "rgba(255,255,255,.6)"))
        return "".join(parts)

    if archetype == "banner_pair":
        gap = 6
        half = (w - gap) / 2
        return _chip(x, y, half, h, rx, accent) + _chip(x + half + gap, y, half, h, rx, primary)

    if archetype == "image_text":
        img_w = w * 0.42
        parts = [_chip(x, y, img_w, h, rx, muted)]
        tx = x + img_w + 12
        parts.append(_line(tx, y + h * 0.2, w - img_w - 24, h * 0.12, colors["text"]))
        parts.append(_line(tx, y + h * 0.45, (w - img_w - 24) * 0.7, h * 0.1, muted))
        parts.append(_chip(tx, y + h * 0.68, w * 0.18, h * 0.18, rx, accent))
        return "".join(parts)

    if archetype == "chip_row":
        count = 5
        gap = 6
        cw = (w - gap * (count - 1)) / count
        return "".join(_chip(x + i * (cw + gap), y, cw, h, rx, surface, stroke=border) for i in range(count))

    if archetype == "pill_row":
        count = 5
        gap = 8
        cw = (w - gap * (count - 1)) / count
        return "".join(_line(x + i * (cw + gap), y + h * 0.35, cw, h * 0.3, muted) for i in range(count))

    if archetype == "icon_row":
        count = 4
        gap = (w - count * h) / max(1, count - 1)
        parts = []
        for i in range(count):
            cx = x + i * (h + gap) + h / 2
            parts.append(f'<circle cx="{cx:.1f}" cy="{y + h * 0.35:.1f}" r="{h * 0.3:.1f}" fill="{accent}"/>')
            parts.append(_line(cx - h * 0.35, y + h * 0.75, h * 0.7, h * 0.12, muted))
        return "".join(parts)

    if archetype == "bar_cta":
        parts = [_chip(x, y, w * 0.62, h, rx, surface, stroke=border)]
        parts.append(_chip(x + w * 0.66, y, w * 0.32, h, rx, primary))
        return "".join(parts)

    if archetype == "quote_row":
        count = 2
        gap = 8
        cw = (w - gap) / count
        parts = []
        for i in range(count):
            cx = x + i * (cw + gap)
            parts.append(_chip(cx, y, cw, h, rx, surface, stroke=border))
            parts.append(_line(cx + 8, y + h * 0.3, cw - 16, h * 0.12, muted))
            parts.append(_line(cx + 8, y + h * 0.55, (cw - 16) * 0.6, h * 0.12, muted))
        return "".join(parts)

    if archetype == "card_row":
        count = 3
        gap = 8
        cw = (w - gap * (count - 1)) / count
        parts = []
        for i in range(count):
            cx = x + i * (cw + gap)
            parts.append(_chip(cx, y, cw, h, rx, surface, stroke=border))
            parts.append(_chip(cx + 4, y + 4, cw - 8, h * 0.55, min(rx, 3), muted))
        return "".join(parts)

    # "product_grid" and any unrecognized archetype — a generic content
    # block, never a crash for a future section type this preview hasn't
    # been taught yet.
    count = 4
    gap = 6
    cw = (w - gap * (count - 1)) / count
    parts = []
    for i in range(count):
        cx = x + i * (cw + gap)
        parts.append(_chip(cx, y, cw, h * 0.62, min(rx, 4), surface, stroke=border))
        parts.append(_line(cx + 3, y + h * 0.68, cw - 6, h * 0.1, colors["text"]))
        parts.append(_line(cx + 3, y + h * 0.84, cw * 0.5, h * 0.1, accent))
    return "".join(parts)


def _archetype_for(section_key: str) -> tuple[str, float]:
    if section_key in _PRODUCT_GRID_KEYS:
        return "product_grid", 1.3
    return _ARCHETYPE_WEIGHTS.get(section_key, ("content_block", 0.9))


def build_template_thumbnail_svg(preset: LayoutPresetDefinition) -> str:
    """A deterministic inline SVG schematic of ``preset``'s real home-page
    baseline — see the module docstring for the full rationale. Pure
    function of registry data: no database access, no template rendering,
    safe to call for every card on every Gallery request."""
    appearance_config = {**preset.appearance, "palette_slug": preset.default_palette_slug}
    colors = appearance_registry.resolve_colors(appearance_config)
    roles = appearance_registry.resolve_theme_roles(appearance_config)
    radius = float(preset.appearance.get("radius", 8) or 8)
    density = preset.appearance.get("density", "normal")
    gap = {"compact": 3.0, "relaxed": 7.0}.get(density, 5.0)

    header_markup, body_top, page_bg = _header_markup(preset, colors, roles, radius)
    body_bottom = _VIEWBOX_H - _FOOTER_H
    footer_markup = _footer_markup(preset, colors, roles, body_bottom)

    home_entries = preset.pages.get("home", ())[:_MAX_DISPLAYED_SECTIONS]
    weighted = [(*_archetype_for(entry.section_key), entry.section_key) for entry in home_entries]
    total_weight = sum(w for _, w, _ in weighted) or 1.0
    available_h = max(0.0, body_bottom - body_top - gap * (len(weighted) + 1))

    body_parts = []
    y = body_top + gap
    pad_x = 12.0
    row_w = _VIEWBOX_W - pad_x * 2
    for archetype, weight, _section_key in weighted:
        row_h = available_h * (weight / total_weight)
        if row_h > 2:
            body_parts.append(_section_row(archetype, pad_x, y, row_w, row_h, colors, radius))
        y += row_h + gap

    svg = (
        f'<svg viewBox="0 0 {_VIEWBOX_W} {_VIEWBOX_H}" xmlns="http://www.w3.org/2000/svg" '
        f'focusable="false" aria-hidden="true">'
        f'<rect x="0" y="0" width="{_VIEWBOX_W}" height="{_VIEWBOX_H}" fill="{page_bg}"/>'
        f"{header_markup}"
        f"{''.join(body_parts)}"
        f"{footer_markup}"
        f"</svg>"
    )
    return svg


#: A neutral, always-safe placeholder — used only if building the real
#: preview above ever raises (a future Preset shape this module hasn't
#: been taught yet). Keeps the Gallery page itself unbreakable.
_FALLBACK_SVG = (
    f'<svg viewBox="0 0 {_VIEWBOX_W} {_VIEWBOX_H}" xmlns="http://www.w3.org/2000/svg" '
    f'focusable="false" aria-hidden="true">'
    f'<rect width="{_VIEWBOX_W}" height="{_VIEWBOX_H}" fill="#F1EFF9"/>'
    f'<rect x="0" y="0" width="{_VIEWBOX_W}" height="24" fill="#E4E0F3"/>'
    f'<rect x="0" y="{_VIEWBOX_H - 22}" width="{_VIEWBOX_W}" height="22" fill="#E4E0F3"/>'
    f"</svg>"
)


def resolve_gallery_thumbnail(preset: LayoutPresetDefinition) -> str:
    """Safe entry point for the Gallery view — never lets a thumbnail
    rendering problem break the whole Gallery page (Batch 3's explicit
    "missing/broken thumbnail metadata degrades safely" requirement)."""
    try:
        return build_template_thumbnail_svg(preset)
    except Exception:
        return _FALLBACK_SVG


# ------------------------------------------------------------------
# Real Ready Template Gallery screenshots (Rasti Mode Demo mission).
#
# Everything above this point is untouched from Acceptance Batch 3 — the
# pure, zero-I/O SVG schematic remains the permanent safe fallback and its
# own tests keep passing unchanged. What follows is an ADDITIONAL,
# independent resolution layer: a real browser-captured screenshot of the
# actual Rasti Mode Demo public storefront, one canonical HOME shot per
# Ready Template, generated OFFLINE by
# ``apps.storefront_builder.management.commands.capture_ready_template_previews``
# (a dev/build-time tool that applies+publishes each preset onto the
# isolated demo store, launches Playwright, and saves a versioned WebP —
# see that command's docstring for the full architecture). A normal
# Gallery request never launches a browser, never calls Playwright/
# Selenium, and never mutates data — ``resolve_real_screenshot`` below
# only ever does a filesystem existence check plus reading one small JSON
# sidecar file.
#
# Anti-staleness (mission Step 24: "do NOT silently show an old version
# screenshot"): each captured screenshot is saved with a sidecar
# ``.meta.json`` recording a content hash of the exact registry data the
# SVG function above already reads (palette/appearance, header, footer,
# home section-key order). If the registered Preset changes without a
# matching re-capture, the stored hash no longer matches and this resolver
# safely refuses the stale file — falling back to the always-fresh SVG
# schematic rather than ever risking a misleading screenshot.

#: Relative to this app's ``static/`` directory (matches the existing
#: ``{% static 'css/storefront_builder.css' %}`` flat-namespace convention
#: already used by ``template_gallery.html``).
_PREVIEWS_STATIC_SUBDIR = "ready_template_previews"

APP_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def preview_content_hash(preset: LayoutPresetDefinition) -> str:
    """A short, deterministic fingerprint of exactly the registry data the
    real screenshot visually depends on — the same inputs
    ``build_template_thumbnail_svg`` reads, so this hash changes if and
    only if a real, screenshot-visible aspect of the Preset changed."""
    home_section_keys = [entry.section_key for entry in preset.pages.get("home", ())]
    payload = {
        "appearance": preset.appearance,
        "default_palette_slug": preset.default_palette_slug,
        "header": preset.header,
        "footer": preset.footer,
        "home_section_keys": home_section_keys,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: Post-demo hardening pass (Issue 3) — filesystem locations of the
#: deterministic Demo Store definition inputs a real screenshot's PIXELS
#: actually depend on, beyond the Template registry itself. Both are plain
#: repo files (never a database query), so reading/hashing them at Gallery
#: request time stays exactly as cheap/DB-free as the rest of this module.
#: A missing file hashes as ``b""`` — never raises — so an environment that
#: has never run the Rasti Mode Demo seed command simply never has a "real"
#: screenshot to begin with (``resolve_real_screenshot`` already handles a
#: missing screenshot/meta file safely).
_DEMO_MEDIA_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "stores" / "demo_assets" / "rasti_mode_demo"
    / "selected_product_media_manifest.json"
)
_DEMO_SEED_COMMAND_PATH = (
    Path(__file__).resolve().parents[2] / "stores" / "management" / "commands"
    / "seed_ready_template_fashion_demo.py"
)


def _canonicalize_text_bytes(data: bytes) -> bytes:
    """Normalize line endings so logically identical TEXT hashes the same on
    every platform: CRLF (Windows) and lone CR (classic Mac) both collapse to
    LF. LF-only content (how these inputs are committed on Linux) is returned
    unchanged, so fingerprints captured on Linux stay valid after a Windows
    checkout that materializes the same text with CRLF."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _file_hash(path: Path) -> str:
    """SHA256 of a deterministic TEXT input to ``preview_input_fingerprint``.

    Both callers pass text files (``selected_product_media_manifest.json`` and
    ``seed_ready_template_fashion_demo.py``), so the bytes are line-ending
    normalized before hashing — the fingerprint must identify logical content,
    not the checkout's platform-specific EOL style. A missing file hashes as
    empty (never raises)."""
    try:
        data = path.read_bytes()
    except OSError:
        data = b""
    return hashlib.sha256(_canonicalize_text_bytes(data)).hexdigest()


def preview_input_fingerprint(preset: LayoutPresetDefinition) -> str:
    """Post-demo hardening pass (Issue 3) — the CANONICAL preview identity:
    a real screenshot is only "fresh" if BOTH the Template registry data
    (``preview_content_hash``) AND the deterministic Demo Store definition
    it was captured against are unchanged.

    ``preview_content_hash`` alone missed a real staleness case: Template
    ``dense_marketplace`` stays at v1 (registry unchanged) while the Demo
    Store's real catalog/media/content changes (e.g. this mission's own
    Issue 2 multi-color rework) — the OLD screenshot still visually shows
    the stale product photos/colors, but the old hash still matched, so it
    kept resolving as "healthy". This fingerprint additionally covers:

    - ``selected_product_media_manifest.json`` — identity of every real
      product image (SKU, color, order, source/derived hashes) the Demo
      Store's PDP/listing/hero/category renders read.
    - ``seed_ready_template_fashion_demo.py``'s own source bytes — the
      single deterministic definition of the Demo Store's catalog/pricing/
      variants/collections/hero/banner/story-rail content (any real change
      to what gets seeded is, by construction, a change to this file).

    ``SHA256(template key/version + manifest hash + seed-definition hash)``
    — exactly the architecture the mission specifies. Still a pure
    filesystem read, no database access, safe on every normal Gallery GET."""
    payload = "|".join([
        preset.key,
        str(preset.version),
        preview_content_hash(preset),
        _file_hash(_DEMO_MEDIA_MANIFEST_PATH),
        _file_hash(_DEMO_SEED_COMMAND_PATH),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def screenshot_relpath(template_key: str, version: str) -> str:
    """The static-relative path a real capture is saved to / read from —
    the exact ``ready_template_previews/<key>/v<version>.webp`` shape the
    mission specifies.

    Part 2B follow-up (version-mismatch bug): ``version`` has no default.
    It must always be the Ready Template's OWN registry
    ``LayoutPresetDefinition.version`` (a string, e.g. ``"2"``) — never an
    independent screenshot-format constant. A prior version of this module
    defaulted this to a fixed, never-bumped ``SCREENSHOT_VERSION = 1``
    module constant, so every capture kept writing to ``v1.webp``/
    ``v1.meta.json`` no matter what the registry's own ``version`` field
    said (confirmed: ``fashion_promo_catalog`` reached registry version
    ``"2"`` while its committed preview stayed named/labeled version 1).
    The underlying pixels were never actually stale — ``preview_input_
    fingerprint`` below already hashes ``preset.version`` in, so a version
    bump did correctly force a re-capture — but the file name and the
    ``"version"`` field inside the sidecar disagreed with the registry,
    which is exactly what a merchant-side audit correctly flagged as
    inconsistent. Requiring the caller to pass the real version here
    (no silent fallback) makes that class of drift impossible to reproduce."""
    return f"{_PREVIEWS_STATIC_SUBDIR}/{template_key}/v{version}.webp"


def meta_relpath(template_key: str, version: str) -> str:
    return f"{_PREVIEWS_STATIC_SUBDIR}/{template_key}/v{version}.meta.json"


def resolve_real_screenshot(preset: LayoutPresetDefinition) -> str | None:
    """Returns the static-relative path to a real, still-fresh screenshot
    for ``preset``, or ``None`` if none exists / it is stale — in which
    case the caller must fall back to ``resolve_gallery_thumbnail``.

    Pure filesystem read (existence check + one small JSON file) — no
    browser, no network, no database write, safe to call on every normal
    Gallery request.

    Post-demo hardening pass (Issue 3): staleness is decided by
    ``preview_input_fingerprint`` — the canonical identity covering BOTH
    the Template registry AND the Demo Store's real catalog/media/content
    definition — not the narrower, Template-only ``content_hash``. A
    sidecar captured under a different Template (or before this mission,
    with no ``preview_input_fingerprint`` key at all) simply never matches
    another Template's/the current fingerprint, so it safely falls back
    rather than ever satisfying the wrong Template.

    Part 2B follow-up: the path itself is now keyed by ``preset.version``
    (see ``screenshot_relpath``'s docstring) — a v1 file on disk is simply
    never looked at once the registry moves a Template to v2; only a
    genuinely re-captured v2 file (at the v2 path, with a matching v2
    fingerprint) can ever resolve as current."""
    relpath = screenshot_relpath(preset.key, preset.version)
    image_path = APP_STATIC_DIR / relpath
    meta_path = APP_STATIC_DIR / meta_relpath(preset.key, preset.version)
    if not image_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None
    if meta.get("preview_input_fingerprint") != preview_input_fingerprint(preset):
        return None
    return relpath
