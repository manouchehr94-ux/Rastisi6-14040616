"""R4-14 — the REAL frames an uploaded picture will be shown in, resolved from the store's own layout.

The upload guide used to print one fixed ratio per slot. A store's pictures are shown in frames that depend on the template (card style),
on each section's Design Studio settings (frame ratio / fit / focal side / zoom) and on the section kind. This module reads the store's
Draft layout (Published when there is no Draft; read-only — it never creates a Draft) and returns, for an upload *slot*, the list of
frames the picture will appear in, so the guide can recommend a ratio that matches the template and preview the exact crop.

Ratios come from the storefront CSS (``apps/catalog/static/css/product_card.css``, ``storefront_builder.css``, ``core/tokens.css``); the table
below is pinned to those files by ``tests/test_r414_upload_guide.py`` so the two cannot drift. Where a frame depends on the viewport or on text
height (hero on phones, wide single banner) the frame is flagged ``approx``.

Nothing here touches a file or a setting."""

from __future__ import annotations

from . import design_block, section_registry

SQUARE, PORTRAIT, LANDSCAPE = "square", "portrait", "landscape"

#: frame-ratio presets of the Design Studio «نسبت قاب تصویر» (design_block._RATIO_CSS) as width/height
_DESIGN_RATIO = {"square": (1, 1), "portrait": (3, 4), "landscape": (4, 3)}

#: product-card picture frame, width/height, from product_card.css. A style listed in ``_STYLE_FIXED`` ignores the card's own
#: «نسبت» setting (its rule is declared after the .ratio-* rules); the two styles in ``_STYLE_BY_RATIO`` honour it.
_DEFAULT_RATIO = {SQUARE: (1, 1), PORTRAIT: (3, 4), LANDSCAPE: (4, 3)}
_STYLE_FIXED = {
    "compact": (1, 1.03), "editorial_minimal": (4, 5), "shelf_editorial": (3, 4), "beauty_glass": (1, 1), "paper_frame": (4, 5),
    "portrait_round": (1, 1), "catalog_index": (4, 3), "chocolate_retail": (1, 1), "pastel_flat": (1, 1),
}
_STYLE_BY_RATIO = {
    "beauty_retail": {SQUARE: (1.12, 1), PORTRAIT: (4, 5), LANDSCAPE: (1.12, 1)},
    "center_stepper": {SQUARE: (1, 1), PORTRAIT: (1, 1.2), LANDSCAPE: (4, 3)},
}
_STYLE_CIRCLE = {"portrait_round"}

PRODUCT_SECTIONS = ("product_section", "newest_products", "best_sellers", "discounted_products")

#: category_grid display modes → (ratio, shape, approx) of the picture frame (storefront_builder.css)
_CATEGORY_CIRCLE = {"fashion_flat", "chocolate_story", "luxury_shortcuts", "grey_circles", "circular", "icon_tiles"}
_CATEGORY_SQUARE = {"fashion_mosaic", "beauty_icons", "pastel_tiles"}
_CATEGORY_RECT = {"chocolate_badges": (124, 98), "image_strip": (3, 2), "atelier_mosaic": (4, 5), "gradient_tiles": (1, 1)}

#: hero / banner frames: (label, ratio, approx)
HERO_DESKTOP = (1053, 420)
HERO_TABLET = (16, 7)
HERO_PHONE = (13, 10)
HERO_POSTER = (1.89, 1)


def _num(value) -> float:
    return round(float(value), 4)


def _frame(label, ratio, *, shape="rect", fit="contain", pos="center", zoom=1.0, approx=False, section=None, can=(False, False, False), note=""):
    w, h = ratio
    return {
        "label": label, "ratio": _num(w / h), "w": w, "h": h, "shape": shape, "fit": fit, "pos": pos, "zoom": zoom, "approx": approx,
        "section": section or "", "can_fit": can[0], "can_pos": can[1], "can_zoom": can[2], "note": note,
    }


def card_ratio(card_style, card_ratio_setting) -> tuple:
    """The product-card picture frame (w, h) for a card style + the card's own «نسبت» setting (CSS-pinned)."""
    style = card_style or "standard"
    setting = card_ratio_setting if card_ratio_setting in _DEFAULT_RATIO else SQUARE
    if style in _STYLE_FIXED:
        return _STYLE_FIXED[style]
    if style in _STYLE_BY_RATIO:
        return _STYLE_BY_RATIO[style][setting]
    return _DEFAULT_RATIO[setting]


_POS = {"": "center", None: "center"}


def _design_of(section) -> dict:
    raw = (section.settings or {}).get("design") if isinstance(section.settings, dict) else None
    return raw if isinstance(raw, dict) else {}


def _caps(section_key) -> tuple[bool, bool, bool]:
    applicable = design_block.applicable_properties(section_key)
    return ("image_fit" in applicable, "image_position" in applicable, "image_zoom" in applicable)


def _design_fit(design, default):
    return design.get("image_fit") if design.get("image_fit") in ("contain", "cover") else default


def _design_pos(design):
    return design.get("image_position") if design.get("image_position") in ("top", "bottom", "left", "right", "center") else "center"


def _design_zoom(design):
    value = design.get("image_zoom")
    return {"110": 1.1, "125": 1.25, "150": 1.5, "175": 1.75}.get(str(value), 1.0)


def _section_label(section) -> str:
    title = ""
    if isinstance(section.settings, dict):
        title = str(section.settings.get("title") or "").strip()
    if not title:
        try:
            title = section_registry.get_definition(section.section_key).label_fa
        except Exception:  # pragma: no cover
            title = section.section_key
    return title


def _store_sections(store):
    """Active sections of the store's Draft (Published when there is no Draft). Read-only; never provisions a layout."""
    if store is None:
        return []
    from .models import StorefrontLayout, StorefrontSection

    layout = StorefrontLayout.objects.filter(store=store).select_related("draft_version", "published_version").first()
    version = (layout.draft_version or layout.published_version) if layout else None
    if version is None:
        return []
    return list(StorefrontSection.objects.filter(page__version=version, is_active=True).order_by("page_id", "order", "id"))


def _merge(frames: list[dict]) -> list[dict]:
    """Frames that look identical (ratio, shape, fit, focal, zoom) are shown once, with every section that uses them."""
    merged: dict[tuple, dict] = {}
    for fr in frames:
        key = (fr["ratio"], fr["shape"], fr["fit"], fr["pos"], fr["zoom"], fr["approx"], fr["label"] if not fr["section"] else "")
        if key in merged:
            names = merged[key].setdefault("sections", [])
            if fr["section"] and fr["section"] not in names:
                names.append(fr["section"])
        else:
            fr = dict(fr)
            fr["sections"] = [fr["section"]] if fr["section"] else []
            merged[key] = fr
    out = []
    for fr in merged.values():
        names = fr.pop("sections")
        fr.pop("section", None)
        fr["used_by"] = names[:4] + ([f"و {len(names) - 4} بخش دیگر"] if len(names) > 4 else [])
        out.append(fr)
    return out


# --------------------------------------------------------------------------------------------- per-slot resolvers
def _product_frames(sections):
    frames = []
    for s in sections:
        if s.section_key not in PRODUCT_SECTIONS:
            continue
        settings = s.settings if isinstance(s.settings, dict) else {}
        card = settings.get("card") if isinstance(settings.get("card"), dict) else {}
        design = _design_of(s)
        if design.get("image_ratio") in _DESIGN_RATIO:
            ratio, note = _DESIGN_RATIO[design["image_ratio"]], "نسبت قاب را در Design Studio تعیین کرده‌اید"
        else:
            ratio, note = card_ratio(card.get("card_style"), card.get("image_ratio")), "نسبت قاب از سبکِ کارت و تنظیمِ کارتِ این بخش می‌آید"
        shape = "circle" if (card.get("card_style") in _STYLE_CIRCLE and design.get("image_ratio") not in _DESIGN_RATIO) else "rect"
        frames.append(_frame("کارت کالا", ratio, shape=shape, fit=_design_fit(design, "contain"), pos=_design_pos(design), zoom=_design_zoom(design),
                             section=_section_label(s), can=_caps(s.section_key), note=note))
    for s in sections:
        if s.section_key == "amazing_offers":
            design = _design_of(s)
            frames.append(_frame("پیشنهاد شگفت‌انگیز", (4, 3), fit=_design_fit(design, "contain"), pos=_design_pos(design), zoom=_design_zoom(design),
                                 section=_section_label(s), can=_caps(s.section_key), approx=True,
                                 note="قاب ۴:۳ است؛ روی موبایل بالای متن و روی دسکتاپ کنار آن قرار می‌گیرد"))
    return frames


def _category_frames(sections):
    frames = []
    for s in sections:
        if s.section_key != "category_grid":
            continue
        settings = s.settings if isinstance(s.settings, dict) else {}
        mode = str(settings.get("display_mode") or "grid")
        design = _design_of(s)
        if design.get("image_ratio") in _DESIGN_RATIO:
            ratio, shape, approx = _DESIGN_RATIO[design["image_ratio"]], "rect", False
        elif mode in _CATEGORY_CIRCLE:
            ratio, shape, approx = (1, 1), "circle", False
        elif mode in _CATEGORY_SQUARE:
            ratio, shape, approx = (1, 1), "rect", False
        elif mode in _CATEGORY_RECT:
            ratio, shape, approx = _CATEGORY_RECT[mode], "rect", True
        else:
            ratio, shape, approx = (3, 2), "rect", True
        default_fit = "contain" if mode in ("circular", "grey_circles", "icon_tiles", "grid", "carousel", "image_strip", "gradient_tiles") else "cover"
        frames.append(_frame("کاشی دسته‌بندی", ratio, shape=shape, fit=_design_fit(design, default_fit), pos=_design_pos(design), zoom=_design_zoom(design),
                             section=_section_label(s), can=_caps(s.section_key), approx=approx,
                             note="دایره‌ای: گوشه‌ها بریده می‌شود؛ سوژه را در مرکز نگه دارید" if shape == "circle" else ""))
    return frames


def _brand_frames(sections):
    out = []
    for s in sections:
        if s.section_key == "brand_carousel":
            design = _design_of(s)
            out.append(_frame("لوگوی برند", (5, 2), fit=_design_fit(design, "contain"), pos=_design_pos(design), section=_section_label(s),
                              can=_caps(s.section_key), note="جعبهٔ ۱۴۰×۵۶ پیکسل؛ لوگو بریده نمی‌شود"))
    return out


def _collection_frames(sections):
    out = []
    for s in sections:
        if s.section_key == "collection_tiles":
            design = _design_of(s)
            ratio = _DESIGN_RATIO.get(design.get("image_ratio"), (4, 3))
            out.append(_frame("کارت کالکشن", ratio, fit=_design_fit(design, "cover"), pos=_design_pos(design), section=_section_label(s),
                              can=_caps(s.section_key), note="نسبت پیش‌فرض ۴:۳"))
    return out


def _journal_frames(sections):
    out = [_frame("فهرست مجله", (4, 3), fit="cover", note="کارتِ مقاله در صفحهٔ مجله")]
    for s in sections:
        if s.section_key == "blog_posts":
            design = _design_of(s)
            ratio = _DESIGN_RATIO.get(design.get("image_ratio"), (16, 10))
            out.append(_frame("بخش مطالب وبلاگ", ratio, fit=_design_fit(design, "cover"), pos=_design_pos(design), section=_section_label(s),
                              can=_caps(s.section_key)))
    return out


def _hero_frames(sections, *, mobile=False):
    out = []
    keys = ("hero_banner", "image_slider")
    present = [s for s in sections if s.section_key in keys]
    if mobile:
        out.append(_frame("اسلاید روی موبایل", HERO_PHONE, fit="cover", approx=True,
                          note="ارتفاعِ قاب به متنِ روی اسلاید بستگی دارد (حداقل ۳۰۰ پیکسل)"))
    else:
        out.append(_frame("اسلاید روی دسکتاپ", HERO_DESKTOP, fit="cover"))
        out.append(_frame("اسلاید روی تبلت", HERO_TABLET, fit="cover"))
    for s in present[:1]:
        design = _design_of(s)
        for fr in out:
            fr["fit"] = "cover"
            fr["pos"] = _design_pos(design)
            fr["can_pos"] = "image_position" in design_block.applicable_properties(s.section_key)
            fr["section"] = _section_label(s)
    return out


def _banner_frames(sections, *, mobile=False):
    out = []
    keys = ("single_banner", "multi_banner")
    present = [s for s in sections if s.section_key in keys]
    ratio = (1, 1) if mobile else (4, 3)
    out.append(_frame("بنر روی موبایل" if mobile else "بنر روی دسکتاپ", ratio, fit="cover", approx=True,
                      note="ارتفاعِ بنر به چیدمان بستگی دارد (۱۱۸ تا ۲۶۰ پیکسل)؛ برای بنر پهنِ تکی تصویرِ افقی‌تر بدهید"))
    for s in present[:1]:
        design = _design_of(s)
        out[0]["pos"] = _design_pos(design)
        out[0]["can_pos"] = "image_position" in design_block.applicable_properties(s.section_key)
        out[0]["section"] = _section_label(s)
    return out


def _story_frames(sections):
    out = [_frame("آیتم استوری", (1, 1), shape="circle", fit="cover", note="دایرهٔ ۶۸ پیکسلی؛ چهره/سوژه را در مرکز بگذارید")]
    for s in sections:
        if s.section_key == "story_rail":
            out[0]["section"] = _section_label(s)
            break
    return out


_RESOLVERS = {
    "product_image": _product_frames, "category_image": _category_frames, "brand_logo": _brand_frames, "collection_image": _collection_frames,
    "journal_cover": _journal_frames, "hero_desktop": _hero_frames, "banner_desktop": _banner_frames, "story_item": _story_frames,
}


def slot_has_frames(slot: str) -> bool:
    return slot in _RESOLVERS or slot in ("hero_mobile", "banner_mobile")


def resolve_frames(slot: str, store=None, sections=None) -> list[dict]:
    """The frames a picture uploaded to ``slot`` is shown in for this store (empty list: the guide falls back to its static ratio)."""
    if store is None and sections is None:
        return []
    if not slot_has_frames(slot):
        return []
    sections = _store_sections(store) if sections is None else sections
    if slot in ("hero_mobile", "banner_mobile"):
        frames = _hero_frames(sections, mobile=True) if slot == "hero_mobile" else _banner_frames(sections, mobile=True)
    else:
        resolver = _RESOLVERS.get(slot)
        frames = resolver(sections) if resolver else []
    if slot == "product_image":
        frames.append(_frame("صفحهٔ کالا (گالری)", (1, 1), fit="contain", approx=False, note="در طرحِ «مد» ۳:۴ است"))
    merged = _merge(frames)
    return merged
