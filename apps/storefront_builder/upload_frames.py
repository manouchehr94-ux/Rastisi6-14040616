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


# --------------------------------------------------------------------------------------------- real placement (V5)
_POS_FA = {"center": "وسط", "top": "بالا", "bottom": "پایین", "left": "چپ", "right": "راست"}


def _px(value) -> str:
    from apps.core.utils import to_fa_digits

    return to_fa_digits(int(value + 0.5))


def _placement_frame(section, *, mobile: bool):
    """The frame a linked image's picture gets in ITS Cell — width/height from the real Draft layout (``upload_placement``), phone separately."""
    from . import upload_placement as up

    placement = up.resolve_placement(section)
    if placement is None:
        return None
    side = placement["phone"] if mobile else placement["desktop"]
    width, height, kind = side["section_w"], side["h"], side["kind"]
    free = height is None or height < 24
    device = "موبایل" if mobile else "دسکتاپ"
    ref = f"صفحهٔ {_px(side['viewport'])} پیکسلی"
    ratio = (width, height) if not free else (4, 3)
    files = up.recommended_file(width, None if free else width / height)
    approx = not free and not side["exact"]
    fit = placement["fit"]
    if free:
        size_text = f"عرض حدود {_px(width)} پیکسل؛ ارتفاع را خودِ تصویر تعیین می‌کند"
        crop_note = "بریده نمی‌شود: ارتفاعِ این بخش از نسبتِ طبیعیِ تصویر می‌آید و هر نسبتی کامل دیده می‌شود."
        if side["kind"] == "shared":
            crop_note = "بریده نمی‌شود: چند بخش زیر هم در یک خانه‌اند و ارتفاعِ هر کدام از نسبتِ طبیعیِ تصویرِ خودش می‌آید."
        elif side["kind"] == "equal":
            crop_note += " (چیدمان «ارتفاع برابر» است؛ اگر خانهٔ کناری بلندتر باشد، قاب کشیده و حاشیه خالی می‌ماند.)"
    else:
        size_text = f"حدود {_px(width)}×{_px(height)} پیکسل" + (" (تقریبی)" if approx else "")
        where = {"manual": "ارتفاع را دستی تنظیم کرده‌اید", "siblings": "ارتفاع از تصویر واقعیِ خانه‌های کناری محاسبه شد",
                 "assumed": "ارتفاع به محتوای خانه‌های کناری و نسبت‌هایی که کشیده‌اید بستگی دارد؛ فرض: دو خانهٔ کوچکِ مربع"}.get(kind, "")
        pos = _POS_FA.get(placement["pos"], "وسط")
        if fit == "cover":
            crop_note = (f"«پر کردن قاب»: اگر نسبتِ فایل با {_ratio_text(width / height)} فرق کند لبه‌ها بریده می‌شود (کانون: {pos}). {where}.").strip()
        else:
            crop_note = (f"«نمایش کامل»: بریده نمی‌شود؛ اگر نسبتِ فایل با {_ratio_text(width / height)} فرق کند حاشیهٔ خالی می‌ماند. {where}.").strip()
    if side.get("manual_ignored"):
        crop_note += " (ارتفاع دستیِ این بخش در چیدمان «بزرگ + دو کوچک» اثری ندارد؛ ارتفاع را ردیف‌های چیدمان تعیین می‌کنند.)"
    note = f"{size_text} · {ref}"
    frame = _frame(f"{placement['name']} — {device}", ratio, fit=fit, pos=placement["pos"], approx=approx,
                   section=_section_label(section), can=(placement["fit_capable"], placement["pos_capable"], False), note=note)
    frame.update({
        "free": free, "w_px": int(width + 0.5), "h_px": None if free else int(height + 0.5), "rec": list(files["rec"]), "min": list(files["min"]),
        "placement": True, "size_text": size_text, "crop_note": crop_note, "layout_label": placement["layout_label"], "kind": kind,
        "slot_name": placement["name"], "ref_viewport": side["viewport"],
    })
    frame.pop("section", None)
    frame["used_by"] = []
    return frame


def _augment_with_placement(frames, slot, target):
    """Hero / banner frames keep their resolver's ratio; the target Section's real width in its Cell is added so the guide can state the displayed
    size and a retina-sharp file size. A frame whose ratio is only approximate stays flagged approximate."""
    from . import upload_placement as up

    placement = up.resolve_placement(target)
    if placement is None:
        return frames
    mobile = slot.endswith("_mobile")
    side = placement["phone"] if mobile else placement["desktop"]
    width = side["section_w"]
    for fr in frames:
        files = up.recommended_file(width, fr["ratio"] or None)
        height = width / fr["ratio"] if fr["ratio"] else None
        fr.update({
            "placement": True, "slot_name": placement["name"], "layout_label": placement["layout_label"], "w_px": int(width + 0.5),
            "h_px": int(height + 0.5) if height else None, "rec": list(files["rec"]), "min": list(files["min"]), "free": False,
            "ref_viewport": side["viewport"], "kind": "ratio",
            "size_text": f"حدود {_px(width)}×{_px(height)} پیکسل" + (" (تقریبی)" if fr["approx"] else "") if height else f"عرض حدود {_px(width)} پیکسل",
            "crop_note": fr.get("note") or "",
        })
    return frames


def _ratio_text(value: float) -> str:
    from apps.core.utils import to_fa_digits

    return to_fa_digits(f"{value:.2f}".rstrip("0").rstrip(".")).replace(".", "٫") + ":۱"


_RESOLVERS = {
    "product_image": _product_frames, "category_image": _category_frames, "brand_logo": _brand_frames, "collection_image": _collection_frames,
    "journal_cover": _journal_frames, "hero_desktop": _hero_frames, "banner_desktop": _banner_frames, "story_item": _story_frames,
}


def slot_has_frames(slot: str) -> bool:
    return slot in _RESOLVERS or slot in ("hero_mobile", "banner_mobile")


def resolve_frames(slot: str, store=None, sections=None, target=None) -> list[dict]:
    """The frames a picture uploaded to ``slot`` is shown in for this store (empty list: the guide falls back to its static ratio).

    ``target`` — the Section the picture is being added to (media form). A linked image is shown in the real frame of ITS Cell; every other
    slot keeps its resolver (the placement only adds the real width of the target Section where the frame depends on it)."""
    if store is None and sections is None:
        return []
    if not slot_has_frames(slot):
        return []
    if target is not None and getattr(target, "section_key", "") == "linked_image" and slot in ("banner_desktop", "banner_mobile"):
        frame = _placement_frame(target, mobile=(slot == "banner_mobile"))
        if frame is not None:
            return [frame]
    sections = _store_sections(store) if sections is None else sections
    if slot in ("hero_mobile", "banner_mobile"):
        frames = _hero_frames(sections, mobile=True) if slot == "hero_mobile" else _banner_frames(sections, mobile=True)
    else:
        resolver = _RESOLVERS.get(slot)
        frames = resolver(sections) if resolver else []
    if slot == "product_image":
        frames.append(_frame("صفحهٔ کالا (گالری)", (1, 1), fit="contain", approx=False, note="در طرحِ «مد» ۳:۴ است"))
    merged = _merge(frames)
    if target is not None and slot in ("hero_desktop", "hero_mobile", "banner_desktop", "banner_mobile") \
            and getattr(target, "section_key", "") in ("hero_banner", "image_slider", "single_banner", "multi_banner"):
        merged = _augment_with_placement(merged, slot, target)
    return merged
