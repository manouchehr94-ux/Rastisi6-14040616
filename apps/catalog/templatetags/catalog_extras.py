from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def product_description_html(value):
    """توضیحاتِ کالا را برایِ نمایش آماده می‌کند — پاک‌سازیِ allowlist و امنِ
    رندرِ مستقیم؛ نگاه کنید به apps.catalog.services.html_sanitizer."""
    from apps.catalog.services.html_sanitizer import render_description_html

    return mark_safe(render_description_html(value))


@register.filter
def star_rating(value):
    """امتیاز عددی (۰ تا ۵) را به رشته‌ی ستاره تبدیل می‌کند، مثل ★★★★☆."""
    try:
        rounded = round(float(value))
    except (TypeError, ValueError):
        rounded = 0
    rounded = max(0, min(5, rounded))
    return "★" * rounded + "☆" * (5 - rounded)



@register.simple_tag
def product_metafield(product, namespace, key, default=""):
    """دسترسیِ امن به یک metafield از cache/prefetch (بدونِ N+1 query).

    Usage: {% product_metafield product "artisan" "maker" as maker %}
           {% product_metafield product "size_guide" "chart_html" as size_chart %}

    اگر prefetch_related('metafields') روی queryset فراخوانی شده باشد،
    هیچ query اضافه‌ای اجرا نمی‌شود."""
    metafields = getattr(product, "_prefetched_objects_cache", {}).get("metafields")
    if metafields is not None:
        for mf in metafields:
            if mf.namespace == namespace and mf.key == key:
                return mf.value_text or default
        return default
    product_id = getattr(product, "pk", None)
    if product_id is None:
        return default
    # Fallback: اگر prefetch نشده باشد (مثلاً صفحه‌ی تکی محصول)
    from apps.catalog.models import ProductMetafield as MF
    try:
        mf = MF.objects.get(product_id=product_id, namespace=namespace, key=key)
        return mf.value_text or default
    except MF.DoesNotExist:
        return default


@register.filter
def product_card_data(product):
    """Resolve the shared, centralized business facts (price/badge/
    availability/quick-add) for one product card — see
    ``apps.catalog.services.product_card_service``. Used by
    ``catalog/partials/product_card.html`` so every card-rendering surface
    reads identical business semantics regardless of visual card variant."""
    from apps.catalog.services.product_card_service import build_product_card_data

    return build_product_card_data(product)


@register.filter
def metafield_json(product_metafield_value):
    """تبدیلِ value_json یک metafield به dict/list قابل استفاده در template.
    اگر null باشد، dict خالی برمی‌گرداند."""
    import json
    if product_metafield_value is None:
        return {}
    if isinstance(product_metafield_value, str):
        try:
            return json.loads(product_metafield_value)
        except (json.JSONDecodeError, ValueError):
            return {}
    return product_metafield_value


#: Card styles that render the cart action as a regular block BELOW the card body (``.pcard-cta``) instead of the hover add-bar over the
#: picture. Presentation vocabulary only (see ``section_registry.CARD_STYLE_CHOICES``); the action itself is the canonical ``cart:add``.
_CARD_STYLES_WITH_FOOTER_CTA = frozenset({"lifestyle_cart"})


@register.filter
def card_cta_below(style):
    return str(style) in _CARD_STYLES_WITH_FOOTER_CTA
