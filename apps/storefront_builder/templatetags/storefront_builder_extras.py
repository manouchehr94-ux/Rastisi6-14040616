from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def section_label(section_key):
    """برچسب فارسیِ یک section_key از Section Registry — «؟» برای کلید
    ناشناخته (هرگز crash نمی‌کند)."""
    from ..section_registry import UnknownSectionTypeError, get_definition

    try:
        return get_definition(section_key).label_fa
    except UnknownSectionTypeError:
        return f"نوع ناشناخته ({section_key})"


@register.filter
def sanitize_rich_text(value):
    """پاک‌سازی allowlist محتوای بخش rich_text — همان ساینیتایزر توضیحات
    کالا (``apps.catalog.services.html_sanitizer``)، امن برای رندر مستقیم."""
    from apps.catalog.services.html_sanitizer import sanitize_product_description

    return mark_safe(sanitize_product_description(value or ""))


@register.filter
def dictget(d, key):
    """دسترسیِ پویا به یک کلیدِ dict که نامش در یک متغیرِ تمپلیت است —
    برایِ حلقه‌هایِ رنگِ ظاهر (``appearance_panel.html``) که کلید از یک
    متغیرِ حلقه (``color_field_labels``) می‌آید، نه یک رشته‌ی ثابت."""
    if not isinstance(d, dict):
        return ""
    return d.get(key, "")


@register.simple_tag
def has_real_footer_contact_data(footer_settings, shop_contact_phone, shop_contact_email):
    """آیا دادهٔ تماسِ واقعی برایِ فوتر وجود دارد؟ — دقیقاً همان شرطِ
    استفاده‌شده در ``global_footer/_shared/contact_info.html``/
    ``contact_column.html``، این‌جا به‌صورتِ یک بولِینِ آماده در دسترس
    است تا شرطِ «آیا گریدِ بیرونیِ فوتر چیزی برایِ رندر دارد؟» بتواند
    بدونِ تکرارِ آن عبارتِ طولانی از این مقدار استفاده کند — پوستهٔ گرید
    هرگز برایِ یک ستونِ تماسِ خالی باز نمی‌ماند."""
    fs = footer_settings
    if fs and (fs.phone or fs.secondary_phone or fs.email or fs.working_hours or fs.address):
        return True
    return bool(shop_contact_phone or shop_contact_email)


@register.filter
def has_renderable_footer_extra_block(extra_blocks, social_links_footer):
    """آیا فهرستِ ``extra_blocks`` فوترِ Global دستِ‌کم یک ستونِ واقعاً
    رندرشدنی دارد؟ — دقیقاً همان سه شرطِ per-block در
    ``global_footer/_shared/extra_blocks.html`` (custom_text با متنِ
    واقعی / link با آدرسِ واقعیِ ثبت‌شده / social با دادهٔ واقعیِ
    SOCIAL_LINKS_FOOTER)؛ چون write-time یک بلوکِ custom_text/link با
    متن/آدرسِ خالی هم می‌تواند ذخیره شود (بدونِ رد شدن)، صرفِ غیرخالی‌بودنِ
    فهرست تضمینی برایِ رندرِ واقعی نیست — این تابع همان بررسیِ دقیق را
    انجام می‌دهد تا پوستهٔ گریدِ بیرونیِ فوتر برایِ یک بلوکِ نامعتبر/خالی
    باز نماند. هرگز crash نمی‌کند (هم‌آهنگ با قراردادِ این ماژول)."""
    if not extra_blocks:
        return False
    for block in extra_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "custom_text" and block.get("text"):
            return True
        if block_type == "link" and block.get("url"):
            return True
        if block_type == "social" and social_links_footer:
            return True
    return False


@register.filter
def getattribute(obj, attr_name):
    """دسترسیِ پویا به یک attribute که نامش در یک متغیرِ تمپلیت است — برای
    فرمِ عمومیِ رسانه (``section_media_form.html``) که فیلدِ متنیِ دوم
    (``subtitle`` برایِ اسلاید، ``description`` برایِ بنر) بسته به ``kind``
    فرق می‌کند؛ Django به‌طورِ پیش‌فرض فقط دسترسیِ attribute با نامِ ثابت
    (نه متغیر) را در تمپلیت پشتیبانی می‌کند."""
    return getattr(obj, attr_name, "")


# نگاشتِ اسلاگِ آیکونِ Section Registry (``SectionDefinition.icon``) به
# مسیرِ SVG — همان سبکِ آیکون‌هایِ دستی‌نوشته‌ی ناوبریِ پنل مدیریت
# (``base_admin.html``: stroke=currentColor، viewBox 24x24)، تا فهرستِ
# «افزودن بخش جدید» به‌جایِ نمایشِ نامِ فنیِ آیکون (مثلاً «sparkles» به
# صورتِ متن) آیکونِ واقعی نشان دهد — طبقِ الزامِ صریحِ «بدون اصطلاحِ فنیِ
# registry» در بازبینیِ UX سازنده. فقط شاملِ آیکون‌هایِ واقعاً استفاده‌شده
# در section_registry.py است، نه یک کتابخانه‌ی عمومی.
_ICON_PATHS = {
    "megaphone": '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "image": '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "images": '<path d="M18 22H4a2 2 0 0 1-2-2V6"/><path d="m22 13-1.3-1.3a2.4 2.4 0 0 0-3.4 0L11 18"/><circle cx="12" cy="8" r="2"/><rect width="16" height="16" x="6" y="2" rx="2"/>',
    "layout-grid": '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    "grid": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "sparkles": '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.29 1.29L3 12l5.8 1.9a2 2 0 0 1 1.29 1.29L12 21l1.9-5.8a2 2 0 0 1 1.29-1.29L21 12l-5.8-1.9a2 2 0 0 1-1.29-1.29z"/>',
    "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "percent": '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "award": '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    "layout": '<rect width="18" height="18" x="3" y="3" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>',
    "text": '<path d="M17 6.1H3"/><path d="M21 12.1H3"/><path d="M15.1 18H3"/>',
    "image-plus": '<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"/><line x1="16" y1="5" x2="22" y2="5"/><line x1="19" y1="2" x2="19" y2="8"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "shopping-bag": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18M16 10a4 4 0 0 1-8 0"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "layers": '<path d="m12.83 2.18-8.6 3.9a1 1 0 0 0 0 1.83l8.6 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83l-8.58-3.91a2 2 0 0 0-1.66 0Z"/><path d="m22 12.18-9.17 4.16a2 2 0 0 1-1.66 0L2 12.18"/><path d="m22 17.18-9.17 4.16a2 2 0 0 1-1.66 0L2 17.18"/>',
    "compass": '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
    "help-circle": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "message-circle": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "play-circle": '<circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>',
}

_ICON_FALLBACK = '<circle cx="12" cy="12" r="9"/>'


@register.filter
def icon_svg(icon_slug):
    """SVG آیکونِ متناظرِ یک اسلاگِ ``SectionDefinition.icon`` (مثلاً
    ``"sparkles"``) — برایِ اسلاگِ ناشناخته یک دایره‌ی ساده برمی‌گرداند،
    هرگز crash نمی‌کند (هم‌آهنگ با قراردادِ ``section_label``)."""
    path = _ICON_PATHS.get(icon_slug, _ICON_FALLBACK)
    svg = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )
    return mark_safe(svg)


@register.simple_tag
def rs_icon(name):
    """R4 Design Studio stroke icon (see ``studio_icons``)."""
    from ..studio_icons import icon_svg

    return mark_safe(icon_svg(str(name)))


@register.simple_tag
def rs_family_icon(family_key):
    """R4 Design Studio icon for a Design Lab family key."""
    from ..studio_icons import DESIGN_LAB_FAMILY_ICONS, icon_svg

    return mark_safe(icon_svg(DESIGN_LAB_FAMILY_ICONS.get(str(family_key), "grid")))


@register.simple_tag
def rs_section_icon(section_key):
    """Design Studio outline icon for a canonical section key (presentation only)."""
    from apps.storefront_builder.studio_icons import icon_svg

    key = str(section_key or "")
    if "hero" in key or "banner" in key or "image" in key or "video" in key:
        name = "image"
    elif "product" in key or "catalog" in key:
        name = "grid"
    elif "brand" in key or "promo" in key or "offer" in key:
        name = "tag"
    elif "collection" in key:
        name = "card"
    elif "search" in key:
        name = "search"
    elif "cart" in key:
        name = "bag"
    else:
        name = "layers"
    return mark_safe(icon_svg(name))


@register.simple_tag
def rs_featured(items, attr, current, count):
    """Split a real choice list for the Design Studio: the current choice
    first plus the next ones up to ``count`` stay visible, the rest go into a
    "more" disclosure. Pure presentation; never filters anything out."""
    items = list(items or [])

    def _value(item):
        return item.get(attr) if isinstance(item, dict) else getattr(item, attr, None)

    current_items = [item for item in items if _value(item) == current]
    others = [item for item in items if _value(item) != current]
    ordered = current_items + others
    return {"featured": ordered[: int(count)], "more": ordered[int(count):]}


_STUDIO_FONT_LABELS_FA = {
    "Vazirmatn": "وزیرمتن · خوانا و امروزی",
    "Tahoma": "تاهوما · ساده و آشنا",
    "Arial": "آریال · بی‌پیرایه",
    "Georgia": "جورجیا · سریف و روایی",
}


@register.filter
def rs_font_label(value):
    """Merchant-facing Persian label for a canonical font choice (display only;
    the stored value stays the canonical font name)."""
    return _STUDIO_FONT_LABELS_FA.get(str(value), value)


#: Design Studio vocabulary for the seven Design Lab families (the approved
#: reference's terminology). Presentation only; family keys are unchanged.
STUDIO_FAMILY_LABELS_FA = {
    "header": "سربرگ",
    "hero": "بنر اصلی",
    "product_view": "چیدمان محصولات",
    "card": "کارت محصول",
    "footer": "پایین صفحه",
    "badge": "نشان محصول",
    "bottom_nav": "نوار موبایل",
}


@register.filter
def rs_family_label(family_key, fallback=""):
    return STUDIO_FAMILY_LABELS_FA.get(str(family_key), fallback or family_key)
