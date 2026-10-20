from .models import ContentPage, Menu, MenuItem
from .services import resolve_destination_url


def footer_pages(request):
    """صفحات محتوایی منتشرشده‌ی فروشگاه جاری که باید در فوتر نمایش داده شوند."""
    store = getattr(request, "store", None)
    if store is None:
        return {"footer_pages_quick_access": [], "footer_pages_customer_service": []}
    pages = ContentPage.objects.filter(
        store=store, status=ContentPage.Status.PUBLISHED, show_in_footer=True
    ).only("title", "slug", "footer_column").order_by("display_order", "title")

    quick_access = [p for p in pages if p.footer_column == ContentPage.FooterColumn.QUICK_ACCESS]
    customer_service = [p for p in pages if p.footer_column == ContentPage.FooterColumn.CUSTOMER_SERVICE]

    return {
        "footer_pages_quick_access": quick_access,
        "footer_pages_customer_service": customer_service,
    }


def _build_menu_tree(menu):
    """ساخت درخت آیتم‌های فعال منو با URL حل‌شده — بدون N+1.

    آیتم‌ها از queryset prefetch شده خوانده می‌شوند (فقط فعال‌ها).
    """
    if menu is None:
        return None

    # Use the prefetched items (already filtered to is_active=True)
    items = list(menu.items.all())

    # Build tree: top-level + children
    top_items = []
    children_map = {}
    for item in items:
        if item.parent_id is None:
            top_items.append(item)
        else:
            children_map.setdefault(item.parent_id, []).append(item)

    tree = []
    for item in top_items:
        url = resolve_destination_url(item)
        children = []
        for child in children_map.get(item.pk, []):
            child_url = resolve_destination_url(child)
            if child_url:
                children.append({
                    "title": child.title,
                    "url": child_url,
                    "open_in_new_tab": child.open_in_new_tab,
                })
        # Include item if it has a URL or has renderable children
        if url or children:
            tree.append({
                "title": item.title,
                "url": url,  # May be None for non-clickable parent headings
                "open_in_new_tab": item.open_in_new_tab,
                "children": children,
            })

    return {"title": menu.title, "items": tree} if tree else None


def navigation_menus(request):
    """منوهای ناوبری فعال فروشگاه — هدر، فوتر، موبایل.

    استراتژی Query:
    - ۱ query برای منوهای فعال
    - ۱ query برای آیتم‌های فعال با JOIN مقصدها (select_related)
    جمعاً: ۲ query مستقل از تعداد منوها و آیتم‌ها.
    """
    from django.db.models import Prefetch

    store = getattr(request, "store", None)
    if store is None:
        return {
            "NAV_HEADER": None, "NAV_FOOTER_1": None, "NAV_FOOTER_2": None,
            "NAV_FOOTER_3": None, "NAV_MOBILE": None,
        }

    items_qs = MenuItem.objects.filter(is_active=True).select_related(
        "parent", "destination_category", "destination_product", "destination_brand",
    ).order_by("display_order", "id")

    active_menus = {
        m.location: m
        for m in Menu.objects.filter(is_active=True, store=store).prefetch_related(
            Prefetch("items", queryset=items_qs),
        )
    }

    return {
        "NAV_HEADER": _build_menu_tree(active_menus.get("header")),
        "NAV_FOOTER_1": _build_menu_tree(active_menus.get("footer_1")),
        "NAV_FOOTER_2": _build_menu_tree(active_menus.get("footer_2")),
        "NAV_FOOTER_3": _build_menu_tree(active_menus.get("footer_3")),
        "NAV_MOBILE": _build_menu_tree(active_menus.get("mobile")),
    }




def _with_available_files(queryset):
    """RS-03: a badge/logo whose stored image file is not actually available is skipped (never drawn as a blank tile).
    Lazy (evaluated only if a footer renders them) and iterable/truthy like the queryset it wraps."""
    from django.utils.functional import SimpleLazyObject

    def available():
        rows = []
        for row in queryset:
            field = row.image
            try:
                if field and field.name and field.storage.exists(field.name):
                    rows.append(row)
            except (OSError, ValueError, NotImplementedError):
                continue
        return rows

    return SimpleLazyObject(available)


def footer_settings(request):
    """تنظیمات فوتر Store جاری + نمادها و لوگوهای پرداخت همان Store.

    Store از ``request.store`` خوانده می‌شود؛ همان قرارداد
    ``apps.core.context_processors.shop_settings`` — نگاه کنید به آن برای
    شرح کامل حالت سازگاری موقت.
    """
    from apps.stores.resolution import StoreResolutionError

    from .models import FooterSettings, FooterSettingsNotProvisionedError, FooterTrustBadge, FooterPaymentLogo

    try:
        settings_obj = FooterSettings.load(store=getattr(request, "store", None))
    except (StoreResolutionError, FooterSettingsNotProvisionedError):
        return {}
    context = {"FOOTER_SETTINGS": settings_obj}

    # store_id (not settings_obj.store) — the FK id is already in hand from
    # the settings_obj row itself; going through .store would trigger an
    # extra, unnecessary query to fetch the related Store instance just to
    # read its pk back out.
    if settings_obj.show_trust_badges:
        context["FOOTER_TRUST_BADGES"] = _with_available_files(
            FooterTrustBadge.objects.filter(store_id=settings_obj.store_id, is_active=True)
        )
    else:
        context["FOOTER_TRUST_BADGES"] = FooterTrustBadge.objects.none()

    if settings_obj.show_payment_logos:
        context["FOOTER_PAYMENT_LOGOS"] = _with_available_files(
            FooterPaymentLogo.objects.filter(store_id=settings_obj.store_id, is_active=True)
        )
    else:
        context["FOOTER_PAYMENT_LOGOS"] = FooterPaymentLogo.objects.none()

    return context
