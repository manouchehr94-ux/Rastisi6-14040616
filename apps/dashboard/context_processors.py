"""Permission-aware navigation flags for merchant-admin templates.

Reads ``request.store_membership`` — set once per request by
``apps.dashboard.decorators.staff_required`` — so this never issues its own
database query. Requests that never went through ``staff_required`` (every
non-dashboard page) get an empty dict back, which is intentional: templates
outside ``apps.dashboard`` never reference these variable names, and Django
silently renders an undefined template variable as empty/falsy, so there is
nothing to guard here.
"""

from django.conf import settings

from apps.stores.authorization import (
    ATTRIBUTE_MANAGE,
    AUDIT_LOG_VIEW,
    BRAND_MANAGE,
    CATEGORY_MANAGE,
    COLLECTION_MANAGE,
    CONTENT_MANAGE,
    COUPON_VIEW,
    CUSTOMER_EXPORT,
    CUSTOMER_SEGMENT_VIEW,
    CUSTOMER_VIEW,
    DISCOUNT_MANAGE,
    IMPORT_EXPORT_MANAGE,
    ORDER_REVIEW_CARD_TRANSFER,
    IMPORT_EXPORT_VIEW,
    INVENTORY_MANAGE,
    MEDIA_MANAGE,
    ORDER_VIEW,
    PRODUCT_VIEW,
    REFUND_VIEW,
    REPORTS_VIEW,
    RESERVATION_VIEW,
    RETURN_VIEW,
    SETTINGS_MANAGE,
    SHIPPING_SETTINGS_MANAGE,
    SHIPPING_SETTINGS_VIEW,
    BILLING_VIEW,
    STAFF_MANAGE,
    STOREFRONT_LAYOUT_MANAGE,
    SUBSCRIPTION_CHANGE,
    SUBSCRIPTION_VIEW,
    TAX_SETTINGS_VIEW,
    TRANSFER_VIEW,
    USAGE_VIEW,
    WAREHOUSE_VIEW,
    membership_has_permission,
)


def merchant_permissions(request):
    membership = getattr(request, "store_membership", None)
    if membership is None:
        return {}
    return {
        "can_view_products": membership_has_permission(membership, PRODUCT_VIEW),
        "can_manage_categories": membership_has_permission(membership, CATEGORY_MANAGE),
        "can_manage_brands": membership_has_permission(membership, BRAND_MANAGE),
        "can_manage_attributes": membership_has_permission(membership, ATTRIBUTE_MANAGE),
        "can_view_orders": membership_has_permission(membership, ORDER_VIEW),
        "can_view_customers": membership_has_permission(membership, CUSTOMER_VIEW),
        "can_view_reports": membership_has_permission(membership, REPORTS_VIEW),
        "can_manage_settings": membership_has_permission(membership, SETTINGS_MANAGE),
        "can_manage_content": membership_has_permission(membership, CONTENT_MANAGE),
        "can_manage_storefront_layout": membership_has_permission(membership, STOREFRONT_LAYOUT_MANAGE),
        "can_manage_collections": membership_has_permission(membership, COLLECTION_MANAGE),
        "can_manage_media": membership_has_permission(membership, MEDIA_MANAGE),
        "can_manage_staff": membership_has_permission(membership, STAFF_MANAGE),
        "can_manage_inventory": membership_has_permission(membership, INVENTORY_MANAGE),
        "can_view_coupons": (
            membership_has_permission(membership, COUPON_VIEW)
            or membership_has_permission(membership, DISCOUNT_MANAGE)
        ),
        "can_view_returns": membership_has_permission(membership, RETURN_VIEW),
        "can_view_refunds": membership_has_permission(membership, REFUND_VIEW),
        "can_view_audit_log": membership_has_permission(membership, AUDIT_LOG_VIEW),
        "can_view_warehouses": membership_has_permission(membership, WAREHOUSE_VIEW),
        "can_view_transfers": membership_has_permission(membership, TRANSFER_VIEW),
        "can_view_reservations": membership_has_permission(membership, RESERVATION_VIEW),
        "can_view_shipping_settings": membership_has_permission(membership, SHIPPING_SETTINGS_VIEW),
        "can_manage_shipping_settings": membership_has_permission(membership, SHIPPING_SETTINGS_MANAGE),
        "can_view_tax_settings": membership_has_permission(membership, TAX_SETTINGS_VIEW),
        "can_view_exports": (
            membership_has_permission(membership, IMPORT_EXPORT_VIEW)
            or membership_has_permission(membership, CUSTOMER_EXPORT)
        ),
        "can_view_imports": membership_has_permission(membership, IMPORT_EXPORT_VIEW),
        "can_manage_imports": membership_has_permission(membership, IMPORT_EXPORT_MANAGE),
        "can_review_card_transfer": membership_has_permission(membership, ORDER_REVIEW_CARD_TRANSFER),
        "can_view_segments": membership_has_permission(membership, CUSTOMER_SEGMENT_VIEW),
        "can_view_subscription": membership_has_permission(membership, SUBSCRIPTION_VIEW),
        "can_change_subscription": membership_has_permission(membership, SUBSCRIPTION_CHANGE),
        "can_view_usage": membership_has_permission(membership, USAGE_VIEW),
        "can_view_billing": membership_has_permission(membership, BILLING_VIEW),
    }


def platform_link(request):
    """Absolute URL back to the owner portal's My Stores (Section H "Back
    to Rastisi" link). Always returned, unconditionally on ``request.
    store_membership`` — this link makes sense on the login page too, not
    only for an already-authenticated staff member. Must be absolute (not
    ``{% url %}``): the owner-portal urlconf is never the active one for a
    Merchant Admin request (ADR-97)."""
    return {
        "RASTISI_PORTAL_URL": f"{request.scheme}://{settings.RASTISI_PLATFORM_PRIMARY_HOST}/app/",
    }


def nav_badges(request):
    """شمارنده‌های نشان(badge) نوار کناری — یک‌بار برای هر درخواست، تا در
    همه‌ی صفحات پنل مدیریت درست باشند، نه فقط در خودِ صفحه‌ی داشبورد.

    پیش از این، این دو مقدار فقط داخل ``dashboard_service.build_dashboard_context``
    محاسبه می‌شدند (که فقط ویوی خودِ ``dashboard_home`` صدا می‌زند)، پس در هر
    صفحه‌ی دیگر (کالاها، سفارشات، ...) نامعین بودند و تمپلیت با
    ``|default:0`` بی‌صدا صفر نشان می‌داد — نه اینکه واقعاً صفر باشند."""
    store = getattr(request, "store", None)
    if store is None:
        return {}
    from apps.catalog.models import Product
    from apps.orders.models import Order

    return {
        "nav_product_count": Product.objects.filter(store=store, is_draft_placeholder=False).count(),
        "nav_pending_order_count": Order.objects.filter(
            store=store, status=Order.Status.PENDING
        ).count(),
    }


def storefront_link(request):
    """URL for the "Back to Store" button (``base_admin.html``'s header icon).

    Only meaningful once ``request.store`` is resolved (``staff_required``
    has run). Never built from ``store.admin_subdomain`` — see
    ``apps.stores.resolution.resolve_storefront_url_for_store``, which this
    delegates to for the actual custom-domain > permanent-handle >
    trial-domain priority and dev-mode ``:8000`` handling.
    ``STOREFRONT_URL`` is ``None`` whenever the Store has no eligible
    domain yet (e.g. still provisioning) — the template disables the button
    and shows "Store is not published yet." in that case."""
    store = getattr(request, "store", None)
    if store is None:
        return {}
    from apps.stores.resolution import resolve_storefront_url_for_store

    return {"STOREFRONT_URL": resolve_storefront_url_for_store(store, request)}


def support_mode_banner(request):
    """بنرِ سراسریِ «حالتِ پشتیبانی فعال است» — وقتی این نشستِ مدیریتِ فروشگاه
    از طریقِ یک بلیتِ ورودِ پشتیبانیِ Platform Admin ایجاد شده باشد (نگاه
    کنید به ``apps.dashboard.views.consume_admin_handoff`` که این پرچم را
    در سشن می‌گذارد). بخشِ ۷: نشانه‌ی واضح در پنلِ مرچنت + دکمه‌ی خروج."""
    support = request.session.get("platform_support_mode")
    if not support:
        return {}
    return {
        "support_mode_active": True,
        "support_mode_store_name": support.get("store_name", ""),
        "support_mode_admin_email": support.get("admin_email", ""),
    }


def subscription_banner(request):
    """پرچمِ وضعیتِ محدودشده‌ی اشتراک برایِ بنرِ سراسری در پنل مدیریت.

    فقط برایِ درخواست‌هایی که از ``staff_required`` عبور کرده‌اند (``request.store``
    ست شده) و فقط وقتی وضعیت واقعاً چیزی برایِ هشدار دارد (grace/restricted/
    expired) داده برمی‌گرداند — وضعیتِ سالم/بدونِ اشتراک هیچ بنری نمی‌سازد."""
    store = getattr(request, "store", None)
    if store is None:
        return {}
    from apps.subscriptions.services.entitlement_service import AccessState, get_subscription_access_state

    access = get_subscription_access_state(store)
    if access.state in (AccessState.FULL, AccessState.NONE) or not access.warning:
        return {}
    return {
        "subscription_banner_warning": access.warning,
        "subscription_banner_blocks_growth": not access.allows_growth,
    }
