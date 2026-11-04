import json

from django import template
from django.utils.html import format_html, format_html_join

from apps.core.image_specs import SPECS
from apps.core.utils import to_fa_digits

register = template.Library()

#: Pillow format names the SERVER really accepts per guide format label (see apps.core.image_validation / forms)
_PIL_BY_LABEL = {"JPG": "JPEG", "PNG": "PNG", "WebP": "WEBP", "ICO": "ICO"}
#: only the product path also checks the filename extension (product_image_service.ALLOWED_EXTENSIONS)
_EXT_CHECKED = {"product_image": [".jpg", ".jpeg", ".png", ".webp"]}


def _dim(w, h) -> str:
    """«W×H پیکسل», or only the width when the height is free (a picture that keeps its own ratio)."""
    return f"{to_fa_digits(w)}×{to_fa_digits(h)} پیکسل" if h else f"عرض {to_fa_digits(w)} پیکسل"


def _fmt_ratio(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return to_fa_digits(text).replace(".", "٫")


def _frames_for(spec_key: str, context) -> list:
    """Frames the picture is really shown in for THIS store (Draft layout); ``[]`` when there is no store/layout."""
    request = context.get("request") if hasattr(context, "get") else None
    store = getattr(request, "store", None)
    explicit = context.get("guide_sections") if hasattr(context, "get") else None
    if store is None and explicit is None:
        return []
    try:
        from apps.storefront_builder.upload_frames import resolve_frames, slot_has_frames

        if not slot_has_frames(spec_key):
            return []  # logo / favicon / badges: static frames — no layout query
        if explicit is None and request is not None:
            if not hasattr(request, "_r414_guide_sections"):
                from apps.storefront_builder.upload_frames import _store_sections

                request._r414_guide_sections = _store_sections(store)  # one layout read per request, however many guides the page shows
            explicit = request._r414_guide_sections
        target = explicit[0] if (context.get("guide_sections") and len(context.get("guide_sections")) == 1) else None
        return resolve_frames(spec_key, store=store, sections=explicit, target=target)
    except Exception:  # the guide is advisory: never break the form because the layout could not be read
        return []


@register.simple_tag(takes_context=True)
def image_guide(context, key, input_name="", confirm=""):
    """راهنمای فارسیِ تصویر کنارِ فرمِ آپلود — کاربرد، نسبت و ابعاد، فرمت، حجم، ناحیهٔ امن، قاب‌های واقعیِ قالبِ فروشگاه و پیش‌نمایشِ برش.

    همهٔ حدها از ثابت‌هایی می‌آیند که سرور واقعاً اعمال می‌کند (``apps.core.image_specs``)؛ قاب‌ها از چیدمانِ همین فروشگاه
    (``apps.storefront_builder.upload_frames``) و فقط خواندنی‌اند."""
    spec = SPECS.get(key)
    if spec is None:
        return ""
    frames = _frames_for(key, context)
    w, h = spec.recommended
    mw, mh = spec.minimum
    size_note = f"حداکثر {to_fa_digits(format(spec.max_mb, 'g'))} مگابایت" + (" (اعمال می‌شود)" if spec.max_enforced else " (توصیه)")
    primary = next((f for f in frames if not f["approx"]), frames[0] if frames else None)
    placed = next((f for f in frames if f.get("placement")), None)
    if primary is not None:
        ratio_text = f"{_fmt_ratio(primary['ratio'])} به ۱ (عرض به ارتفاع)"
        if len({f["ratio"] for f in frames}) > 1:
            ratio_text += " — قاب‌های این فروشگاه متفاوت‌اند؛ سوژه را وسط بگذارید و حاشیهٔ امن بدهید"
    else:
        ratio_text = to_fa_digits(spec.ratio)
    common_rows = [
        ("فرمت", "، ".join(spec.formats) + (" — شفافیت توصیه می‌شود" if spec.transparent else "")),
        ("حجم", size_note),
        ("ناحیهٔ امن", spec.safe_area),
    ]
    if placed is not None:
        # the REAL frame of this picture in its Cell (apps.storefront_builder.upload_placement): measured numbers replace the generic spec ones
        w, h = placed["rec"]
        mw, mh = placed["min"]
        ratio_text = ("ارتفاع آزاد — هر نسبتی بدون برش نمایش داده می‌شود" if placed.get("free")
                      else f"{_fmt_ratio(placed['ratio'])} به ۱ (عرض به ارتفاع)" + (" — تقریبی" if placed["approx"] else ""))
        where = placed["slot_name"] + (f" — چیدمان «{placed['layout_label']}»" if placed.get("layout_label") else "")
        rows = [
            ("جایگاه واقعی", where),
            (f"اندازهٔ نمایش (صفحهٔ {to_fa_digits(placed['ref_viewport'])}px)", placed["size_text"]),
            ("نسبتِ پیشنهادی", ratio_text),
            ("وضوحِ پیشنهادیِ فایل", f"{_dim(w, h)} (دو برابرِ اندازهٔ نمایش، برای صفحه‌های رتینا؛ بزرگ‌تر لازم نیست)"),
            ("حداقل وضوحِ قابل‌قبول", f"{_dim(mw, mh)} (اندازهٔ نمایش در تراکم عادی)"),
            ("وضعیت برش", placed["crop_note"]),
        ] + common_rows + [("متنِ جایگزین (alt)", spec.alt_hint)]
    else:
        rows = [
            ("کاربرد", spec.usage),
            ("نسبتِ پیشنهادی", ratio_text),
            ("ابعادِ پیشنهادی", f"{to_fa_digits(w)}×{to_fa_digits(h)} پیکسل"),
            ("حداقل وضوح", f"{to_fa_digits(mw)}×{to_fa_digits(mh)} پیکسل"),
        ] + common_rows + [("برش", spec.crop), ("متنِ جایگزین (alt)", spec.alt_hint)]
    if spec.extra:
        rows.append(("نکته", spec.extra))
    rw, rh = (int(x) for x in spec.ratio.split(":"))
    shown_ratio = primary["ratio"] if primary else rw / rh
    data = {
        "key": spec.key, "ratio": [rw, rh], "min": [mw, mh], "rec": [w, h], "maxBytes": spec.max_bytes,
        "maxEnforced": spec.max_enforced, "formats": list(spec.formats), "label": spec.label,
        "pil": [_PIL_BY_LABEL[f] for f in spec.formats if f in _PIL_BY_LABEL], "exts": _EXT_CHECKED.get(spec.key),
        "maxPixels": spec.max_pixels, "frames": frames, "contain": spec.key in ("brand_logo", "shop_logo", "footer_badge", "favicon"),
    }
    if placed is not None:
        data["rec"], data["min"] = [w, h], [mw, mh]
    title = f"تصویر {placed['label']}" if placed is not None else spec.label    # the placement names the picture; the generic slot name is not its identity
    body = format_html_join("", "<dt>{}</dt><dd>{}</dd>", rows)
    frame_list = ""
    if frames:
        frame_list = format_html(
            '<div class="imgguide-frames-note"><strong>در قالب فعلی شما این تصویر در این قاب‌ها دیده می‌شود:</strong><ul>{}</ul></div>',
            format_html_join("", "<li>{}</li>", [
                ((f"{f['label']} — {f['size_text']}" if f.get("placement") else f"{f['label']} — {_fmt_ratio(f['ratio'])}:۱"
                  + (" (تقریبی)" if f["approx"] else ""))
                 + (" — " + "، ".join(f["used_by"]) if f["used_by"] else ""),)
                for f in frames
            ]),
        )
    return format_html(
        '<section class="imgguide" data-image-guide="{}" data-input-name="{}" data-spec="{}"{} aria-label="راهنمای تصویر: {}">'
        '<h4 class="imgguide-title">راهنمای تصویر: {}</h4>'
        '<div class="imgguide-spec"><button type="button" class="imgguide-toggle" aria-expanded="true">مشخصات و توصیه‌های این جایگاه</button>'
        '<div class="imgguide-spec-body"><div class="imgguide-body"><div class="imgguide-wire" style="aspect-ratio:{}" aria-hidden="true">'
        '<span class="imgguide-safe"></span><span class="imgguide-ratio">{}</span></div>'
        '<dl>{}</dl></div>{}</div></div>'
        '<div class="imgguide-live" role="status" aria-live="polite"></div></section>',
        spec.key, input_name, json.dumps(data, ensure_ascii=False), format_html(' data-confirm-event="{}"', confirm) if confirm else "",
        title, title, f"{shown_ratio:.4f}",
        "آزاد" if (placed is not None and placed.get("free")) else _fmt_ratio(shown_ratio) + ":۱", body, frame_list,
    )
