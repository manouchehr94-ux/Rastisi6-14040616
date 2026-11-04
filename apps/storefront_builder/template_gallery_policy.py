"""Which Ready Templates a seller may CHOOSE today — the ONE source of truth (owner decision, 1405/08/09).

Only the templates below are offered for a NEW selection (onboarding gallery, Studio gallery, merchant gallery, search, counts and the
server-side switch/apply checks all read this tuple through ``layout_preset_registry.list_selectable_templates``). Everything else stays
registered, renderable, editable, previewable and publishable — nothing is deleted or migrated, and a Store that already carries a hidden
template keeps it (its identity is never replaced automatically; the gallery pins it as «قالب فعلی» but offers no way to switch TO a hidden one).

Restoring hidden templates later needs no data and no migration: add keys to the tuple below, or set ``RASTISI_TEMPLATE_GALLERY_RESTRICTED=0`` in
the environment to offer EVERY registered Ready Template again (the default is restricted).

The order is the owner's list (names → real Registry keys; the Persian label in the comment is the Registry's own ``label_fa``)."""

SELECTABLE_TEMPLATE_KEYS = (
    "warm_boutique",            # کارگاه لاله
    "utility_catalog",          # نسخه
    "street_drop",              # خیابان
    "gallery_minimal",          # گالری آب
    "tool_finder",              # آچار
    "rayan_tech",               # رایان
    "magenta_beauty_retail",    # زیبایی ارغوانی
    "pastel_kawaii_stationery",  # کاغذ پاستلی
    "decor_sand_boutique",      # بوتیک شنی (دکور و لوازم خانه)
    "rose_beauty_store",        # رز کرمی (آرایشی و بهداشتی)
    "pink_beauty_gallery",      # گالری فوشیا (زیبایی)
    "campaign_beauty_hub",      # هاب کمپینی عسلی (آرایشی)
    "cocoa_gift_shop",          # هدیه و ماگ کاکائویی
    "neon_digital_store",       # فروشگاه دیجیتال نئونی
    "dual_atelier",             # آتلیه دوپنل (هدر یکپارچه با دو تصویر)
    "editorial_noir",           # نشریهٔ نوآر (هیروی مجله‌ای با کارت محصول)
    "glass_commerce",           # تجارت شیشه‌ای (هیرو با نوار دسته‌بندی)
    "asymmetric_canvas",        # بوم نامتقارن (هدر شناور روی تصویر)
    "stationery_spectrum",      # تحریر رنگی
)

_SELECTABLE_SET = frozenset(SELECTABLE_TEMPLATE_KEYS)


def is_restricted() -> bool:
    """True (the default) while only ``SELECTABLE_TEMPLATE_KEYS`` are offered; False = every registered Ready Template is offered again."""
    from django.conf import settings

    return bool(getattr(settings, "RASTISI_TEMPLATE_GALLERY_RESTRICTED", True))


def is_selectable_key(template_key) -> bool:
    if not isinstance(template_key, str) or not template_key:
        return False
    return template_key in _SELECTABLE_SET if is_restricted() else True
