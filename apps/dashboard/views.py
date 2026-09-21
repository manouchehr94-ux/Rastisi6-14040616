import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, ProtectedError, Q, Sum, prefetch_related_objects
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Brand,
    Category,
    CategoryAttributeSchema,
    CategoryRecommendedOption,
    IndustryTemplate,
    MerchantCollection,
    MerchantCollectionItem,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductOption,
    ProductVideo,
    ProductOptionValue,
    ProductTag,
    ProductVariant,
    StockMovement,
    StoreIndustryInstallation,
    StoreTemplateUpdate,
)
from apps.catalog.services.attribute_service import (
    AttributeError_,
    AttributeInUseError,
    activate_attribute,
    add_product_attribute_multiselect_value,
    archive_attribute,
    archive_attribute_value,
    can_delete_attribute,
    can_delete_attribute_value,
    create_attribute,
    create_attribute_value,
    delete_attribute,
    delete_attribute_value,
    remove_product_attribute_value,
    reorder_attribute_values,
    set_product_attribute_value,
    update_attribute,
    update_attribute_value,
)
from apps.catalog.services.brand_service import (
    BrandError,
    BrandInUseError,
    BrandReorderError,
    activate_brand,
    archive_brand,
    create_brand,
    delete_brand,
    reorder_brands,
    update_brand,
)
from apps.catalog.services import collection_service
from apps.catalog.services.collection_service import (
    CollectionError,
    CollectionNotFoundError,
    CollectionReorderError,
    DuplicateProductError,
    ProductNotFoundError as CollectionProductNotFoundError,
)
from apps.catalog.services.category_schema_service import (
    CategorySchemaError,
    add_category_attribute,
    cleanup_orphaned_attribute_values,
    orphaned_product_attribute_values,
    remove_category_attribute,
    reorder_category_attributes,
    resolve_category_schema,
    update_category_attribute,
)
from apps.catalog.services import industry_catalog_service
from apps.catalog.services.industry_template_service import (
    IndustryInstallationError,
    install_industry_template,
)
from apps.catalog.models import InventoryReservation, Warehouse, WarehouseInventory, WarehouseTransfer
from apps.catalog.services.inventory_service import list_stock_movements
from apps.catalog.services.reservation_service import ReservationError, list_reservations, release_inventory_reservation
from apps.catalog.services.transfer_service import (
    TransferError,
    cancel_transfer,
    create_transfer,
    list_transfers,
    receive_transfer,
    request_transfer,
    ship_transfer,
)
from apps.catalog.services.warehouse_service import (
    WarehouseError,
    archive_warehouse,
    create_warehouse,
    list_warehouses,
    set_default_warehouse,
    update_warehouse,
)
from apps.core.services.audit_service import list_audit_events, record_audit_event
from apps.core.services.export_service import ExportError, run_export
from apps.subscriptions.services.entitlement_service import EntitlementError
from apps.subscriptions.services import enforcement as subscription_enforcement
from apps.dashboard.services import import_service
from apps.dashboard.services.import_service import ImportServiceError
from apps.cart.models import Coupon
from apps.cart.services.coupon_service import (
    CouponError,
    create_coupon,
    delete_coupon,
    list_coupons,
    toggle_coupon_active,
    update_coupon,
)
from apps.catalog.services.pricing_service import resolve_effective_price
from apps.catalog.services.product_completion_service import build_completion_checklist, completion_percent
from apps.catalog.services.product_publish_service import validate_product_for_publish
from apps.catalog.services.product_draft_service import (
    discard_product_draft,
    get_or_create_product_draft,
    touch_product_draft,
)
from apps.catalog.services.product_sku_service import generate_product_sku
from apps.catalog.services.tag_service import (
    collection_tags,
    ensure_default_collections,
    get_or_create_collection_tag,
    get_or_create_tags,
    suggest_tags,
)
from apps.catalog.services.product_specification_service import build_product_specification
from apps.catalog.services.template_preview_service import build_template_preview, plan_industry_template_installation
from apps.catalog.services.template_update_service import (
    TemplateUpdateError,
    apply_template_update,
    plan_template_update,
)
from apps.catalog.services.template_validation_service import latest_production_version
from apps.catalog.services.product_image_service import (
    ProductImageError,
    ProductImageReorderError,
    add_product_image,
    delete_product_image,
    move_product_image,
    reorder_product_images,
    set_cover_image,
    set_image_360,
    set_image_option_value,
    set_image_variant,
    update_image_alt,
    update_image_caption,
)
from apps.catalog.services.product_video_service import (
    ProductVideoError,
    add_product_video,
    delete_product_video,
)
from apps.catalog.services.variant_engine_service import (
    VariantEngineError,
    add_manual_variant,
    add_option_value,
    add_product_option,
    activate_product_option,
    deactivate_product_option,
    generate_variants,
    preview_combination_count,
    remove_option_value,
    reorder_product_options,
    set_default_variant,
)
from apps.catalog.services.variant_service import (
    ProductTypeError,
    VariantError,
    bulk_create_variants,
    deactivate_variant,
    delete_variant,
    duplicate_variant,
    parse_bulk_values,
    reorder_variants,
    set_product_type,
    update_variant,
)
from apps.core.color_utils import safe_hex
from apps.core.utils import normalize_digits
from apps.core.models import ExportJob, ImportJob, ImportRowResult, ShopSettings
from apps.core.theme_presets import THEME_PRESETS, matching_preset_key
from apps.customers.models import (
    Customer,
    CustomerNote,
    CustomerProfile,
    CustomerSegment,
    CustomerSegmentRule,
    CustomerTag,
)
from apps.orders.models import (
    Order,
    OrderItem,
    Refund,
    ReturnRequest,
    ShippingMethod,
    ShippingRateRule,
    ShippingZone,
    TaxClass,
    TaxRate,
    Transaction,
)
from apps.orders.services.order_service import change_order_status
from apps.orders.services.shipping_service import ensure_default_shipping_methods
from apps.orders.services.refund_service import (
    RefundError,
    execute_order_refund,
    paid_amount,
    plan_order_refund,
    refundable_amount,
    refunded_total,
)
from apps.orders.services.return_service import (
    ReturnError,
    approve_return_request,
    complete_return,
    create_return_request,
    inspect_return_items,
    mark_return_received,
    reject_return_request,
    review_return_request,
)
from apps.sms.events import EVENT_VARIABLES, SmsEvent
from apps.sms.models import SmsBillingPolicy, SmsPackage, SmsPackagePurchase, SmsTemplate
from apps.sms.services import balance_service
from apps.sms.services.sms_service import (
    RetryNotEligibleError,
    SmsTemplateError,
    regenerate_smsrasti_device_token,
    retry_failed_log,
    retry_smsrasti_outbox_item,
    send_test_sms,
)
from apps.stores.integrations.registry import get_provider as get_integration_provider
from apps.stores.models import StoreMembership
from apps.stores.services import integration_service
from apps.stores.services.membership_service import (
    ASSIGNABLE_ROLES,
    MembershipError,
    add_staff_member,
    change_role,
    list_memberships,
    reactivate_membership,
    revoke_membership,
    transfer_ownership,
)

from .decorators import admin_host_required, permission_required, staff_required
from apps.stores.authorization import (
    ATTRIBUTE_MANAGE,
    BILLING_ACCOUNT_MANAGE,
    BILLING_PAYMENT_MANAGE,
    BILLING_VIEW,
    BRAND_MANAGE,
    CATEGORY_MANAGE,
    COLLECTION_MANAGE,
    CONTENT_MANAGE,
    CUSTOMER_EXPORT,
    CUSTOMER_NOTE_MANAGE,
    CUSTOMER_SEGMENT_MANAGE,
    CUSTOMER_SEGMENT_VIEW,
    CUSTOMER_TAG_MANAGE,
    CUSTOMER_VIEW,
    AUDIT_LOG_VIEW,
    COUPON_VIEW,
    DASHBOARD_VIEW,
    DISCOUNT_MANAGE,
    IMPORT_EXPORT_MANAGE,
    IMPORT_EXPORT_VIEW,
    INVENTORY_MANAGE,
    MEDIA_MANAGE,
    ORDER_STATUS_CHANGE,
    ORDER_VIEW,
    PAYMENT_SETTINGS_MANAGE,
    PRODUCT_CREATE,
    PRODUCT_DELETE,
    PRODUCT_EDIT,
    PRODUCT_VIEW,
    REFUND_MANAGE,
    REFUND_VIEW,
    REPORTS_VIEW,
    RESERVATION_VIEW,
    RETURN_MANAGE,
    RETURN_VIEW,
    SETTINGS_MANAGE,
    SHIPPING_SETTINGS_MANAGE,
    SHIPPING_SETTINGS_VIEW,
    SMS_SETTINGS_MANAGE,
    STAFF_MANAGE,
    SUBSCRIPTION_CANCEL,
    SUBSCRIPTION_CHANGE,
    SUBSCRIPTION_VIEW,
    TAX_SETTINGS_MANAGE,
    TAX_SETTINGS_VIEW,
    TRANSFER_MANAGE,
    TRANSFER_VIEW,
    USAGE_VIEW,
    VARIANT_MANAGE,
    WAREHOUSE_MANAGE,
    WAREHOUSE_VIEW,
    membership_has_permission,
)
from .forms import (
    AttributeForm,
    AttributeValueForm,
    BrandForm,
    CategoryAttributeAddForm,
    CategoryEditForm,
    CollectionForm,
    FinanceSettingsForm,
    GiftWrapSettingsForm,
    MainCategoryForm,
    ProductForm,
    ProductImageAltForm,
    ProductImageUploadForm,
    ProductOptionForm,
    ProductOptionValueAddForm,
    ProductQuickAttributeForm,
    ProductQuickCategoryForm,
    ShopInfoForm,
    SmsConnectionForm,
    SmsPackagePurchaseForm,
    SmsTemplateForm,
    SmsTestForm,
    SubCategoryForm,
    SubSubCategoryForm,
    VariantBulkAddForm,
    VariantEditForm,
    VisualIdentityForm,
)
from .services import (
    checklist_service,
    customer_crm_service,
    customers_admin_service,
    dashboard_service,
    report_service,
    segment_service,
    settings_admin_service,
    sms_admin_service,
)
from .services.catalog_admin_service import (
    BULK_STATUS_ACTIONS,
    DEFAULT_PRODUCT_SORT,
    LOW_STOCK_THRESHOLD,
    PRODUCT_SORT_OPTIONS,
    PRODUCT_STATUS_FILTERS,
    BulkActionError,
    CategoryDeleteError,
    bulk_assign_category,
    bulk_assign_tax_class,
    bulk_clear_tax_class,
    bulk_delete_products,
    bulk_set_product_status,
    can_delete_category,
    category_chain,
    category_tree_context,
    reorder_categories,
    default_vendor,
    filtered_products,
    generate_unique_slug,
    leaf_categories,
    PRODUCT_HEALTH_FILTERS,
)
from .services.charts import build_line_chart_svg
from .services.orders_admin_service import (
    INVOICE_STATUS_FILTERS,
    ORDER_STATUS_FILTERS,
    TRANSACTION_STATUS_FILTERS,
    filtered_invoices,
    filtered_orders,
    filtered_transactions,
    invoice_totals,
    next_status_options,
    order_is_final,
    order_status_counts,
    order_status_steps,
)

VALID_RANGES = {"week", "month", "year"}


@admin_host_required
def admin_login(request):
    """صفحه‌ی ورود اختصاصی پنل مدیریت — مستقل از فروشگاه، اما هنوز هم فقط
    روی میزبان مدیریت مجاز قابل‌دسترسی (نگاه کنید به ``admin_host_required``)."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(request.GET.get("next", "/admin-portal/"))

    error = ""
    username = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            auth_login(request, user)
            next_url = request.POST.get("next", request.GET.get("next", "/admin-portal/"))
            # Prevent open redirect — ensure next is a relative admin path
            if not next_url.startswith("/admin-portal/"):
                next_url = "/admin-portal/"
            return redirect(next_url)
        elif user is not None and not user.is_staff:
            error = "شما به پنل مدیریت دسترسی ندارید"
        else:
            error = "نام کاربری یا رمز عبور اشتباه است"

    from apps.stores.resolution import resolve_store_for_admin_request, resolve_storefront_url_for_store

    store = resolve_store_for_admin_request(request)
    storefront_url = resolve_storefront_url_for_store(store, request) if store else None

    next_url = request.GET.get("next", "/admin-portal/")
    return render(request, "dashboard/login.html", {
        "error": error,
        "username": username,
        "next": next_url,
        "STOREFRONT_URL": storefront_url,
    })


@admin_host_required
def consume_admin_handoff(request, token):
    """Receiving end of the owner-portal handoff (Section H, ADR-98).

    Resolves the Store from THIS admin host itself (never trusts a Store
    id from the URL/portal) so a ticket can only ever be consumed on the
    exact admin host it was issued for. A missing/expired/already-consumed/
    wrong-store ticket 404s — same fail-closed, non-existence-revealing
    policy as every other admin-portal auth path in this module.
    """
    from apps.portal.services import handoff_service
    from apps.stores.resolution import resolve_store_for_admin_request

    store = resolve_store_for_admin_request(request)
    if store is None:
        raise Http404

    result = handoff_service.consume_ticket(token, store=store)
    if result is None:
        raise Http404

    user, destination_path, issued_by_platform_admin = result
    auth_login(request, user)
    if issued_by_platform_admin is not None:
        from apps.core.services.audit_service import record_audit_event

        request.session["platform_support_mode"] = {
            "store_name": store.name,
            "admin_email": issued_by_platform_admin.get_username(),
        }
        record_audit_event(
            store=store, actor=issued_by_platform_admin, action_code="platform_admin.support_login_entered",
            object_type="Store", object_id=store.pk, object_label=store.name,
            metadata={"logged_in_as": user.get_username()},
        )
    if not destination_path.startswith("/admin-portal/"):
        destination_path = "/admin-portal/"
    return redirect(destination_path)


@admin_host_required
@require_POST
def exit_support_mode(request):
    """دکمه‌ی خروجِ روشنِ حالتِ پشتیبانی (بخشِ ۷) — فقط پرچمِ سشن را پاک و
    از پنل خارج می‌کند (بدونِ حذفِ خودِ نشستِ کاربرِ مالک؛ ورودِ پشتیبانی
    session-takeover دائمی نیست، پس خروج هم باید ساده و بدونِ اثرِ جانبی
    رویِ حساب باشد)."""
    from apps.stores.resolution import resolve_store_for_admin_request

    store = resolve_store_for_admin_request(request)
    support = request.session.pop("platform_support_mode", None)
    if support and store is not None:
        from apps.core.services.audit_service import record_audit_event

        record_audit_event(
            store=store, actor=request.user if request.user.is_authenticated else None,
            action_code="platform_admin.support_login_exited",
            object_type="Store", object_id=store.pk, object_label=store.name,
        )
    auth_logout(request)
    return redirect("dashboard:login")


@staff_required
@permission_required(DASHBOARD_VIEW)
def dashboard_home(request):
    store = _resolve_dashboard_store(request)
    context = dashboard_service.build_dashboard_context(store)
    context["active_page"] = "dashboard"
    context["setup_checklist"] = checklist_service.build_setup_checklist(store, request)
    context["industry_summary"] = checklist_service.build_industry_summary(store)
    return render(request, "dashboard/dashboard.html", context)


@staff_required
@permission_required(DASHBOARD_VIEW)
def sales_chart_partial(request):
    store = _resolve_dashboard_store(request)
    range_key = request.GET.get("range", "month")
    if range_key not in VALID_RANGES:
        range_key = "month"
    data, labels = dashboard_service.sales_chart_data(store, range_key)
    svg = build_line_chart_svg(data, labels)
    return render(request, "dashboard/partials/sales_chart.html", {"svg": svg})


# ---------------------------------------------------------------- محصولات

PRODUCTS_PER_PAGE = 20


def _product_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    brand_id = request.GET.get("brand", "")
    status = request.GET.get("status", "")
    health = request.GET.get("health", "")
    if health not in PRODUCT_HEALTH_FILTERS:
        health = ""
    product_type = request.GET.get("product_type", "")
    if product_type not in Product.ProductType.values:
        product_type = ""
    sort = request.GET.get("sort", DEFAULT_PRODUCT_SORT)
    if sort not in PRODUCT_SORT_OPTIONS:
        sort = DEFAULT_PRODUCT_SORT

    qs = filtered_products(
        store, q=q, category_id=category_id, status=status, brand_id=brand_id, sort=sort, health=health,
        product_type=product_type,
    )
    paginator = Paginator(qs, PRODUCTS_PER_PAGE)
    page_number = request.GET.get("page", "1")
    page_obj = paginator.get_page(page_number)

    all_store_products = Product.objects.filter(store=store, is_draft_placeholder=False)
    stats = {
        "total": all_store_products.count(),
        "active": all_store_products.filter(status=Product.Status.ACTIVE).count(),
        "draft": all_store_products.filter(status=Product.Status.DRAFT).count(),
        "low_stock": all_store_products.filter(
            status=Product.Status.ACTIVE, stock__lte=LOW_STOCK_THRESHOLD,
        ).count(),
        "active_variants": ProductVariant.objects.filter(product__store=store, is_active=True).exclude(
            combination_key="",
        ).count(),
    }

    return {
        "products": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q,
        "selected_category": category_id,
        "selected_brand": brand_id,
        "selected_status": status,
        "selected_health": health,
        "selected_product_type": product_type,
        "selected_sort": sort,
        "has_active_filters": bool(q or category_id or brand_id or status or health or product_type),
        "category_options": leaf_categories(store),
        "brand_options": Brand.objects.filter(store=store).order_by("name"),
        "status_options": PRODUCT_STATUS_FILTERS,
        "product_type_options": Product.ProductType.choices,
        "sort_options": [(key, label) for key, (_fields, label) in PRODUCT_SORT_OPTIONS.items()],
        "tax_class_options": TaxClass.objects.filter(store=store, is_active=True).order_by("name"),
        "product_stats": stats,
    }


@staff_required
@permission_required(PRODUCT_VIEW)
def product_list(request):
    context = _product_list_context(request)
    context["active_page"] = "products"
    return render(request, "dashboard/products.html", context)


@staff_required
@permission_required(PRODUCT_VIEW)
def product_table(request):
    return render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))


def _selected_product_ids(request):
    ids = request.POST.getlist("product_ids")
    valid = []
    for raw in ids:
        try:
            valid.append(int(raw))
        except (TypeError, ValueError):
            continue
    return valid


@require_POST
@staff_required
def product_bulk_action(request):
    """اکشن فله‌ای روی کالاهای انتخاب‌شده — فقط کالاهای همین Store، هرگز بر
    اساس اعتماد به شناسه‌های ارسالی بدون فیلتر Store (نگاه کنید به
    ``catalog_admin_service.bulk_*``). مجوز لازم بسته به نوع اکشن فرق دارد:
    تغییر وضعیت/دسته‌بندی نیازمند PRODUCT_EDIT، حذف نیازمند PRODUCT_DELETE."""
    store = _resolve_dashboard_store(request)
    action = request.POST.get("bulk_action", "")
    product_ids = _selected_product_ids(request)

    required_permission = PRODUCT_DELETE if action == "delete" else PRODUCT_EDIT
    if not membership_has_permission(request.store_membership, required_permission):
        return render(request, "dashboard/403.html", status=403)

    if not product_ids:
        messages.warning(request, "هیچ کالایی انتخاب نشده است")
    else:
        try:
            if action in BULK_STATUS_ACTIONS:
                count = bulk_set_product_status(store, product_ids, action)
                messages.success(request, f"وضعیت {count} کالا به‌روزرسانی شد")
            elif action == "delete":
                count = bulk_delete_products(store, product_ids)
                messages.success(request, f"{count} کالا حذف شد")
            elif action == "assign-category":
                category_id = request.POST.get("bulk_category", "")
                count = bulk_assign_category(store, product_ids, category_id)
                messages.success(request, f"دسته‌بندی {count} کالا به‌روزرسانی شد")
            elif action == "assign-tax-class":
                tax_class_id = request.POST.get("bulk_tax_class", "")
                count = bulk_assign_tax_class(store, product_ids, tax_class_id, actor=request.user)
                messages.success(request, f"دسته‌ی مالیاتیِ {count} کالا به‌روزرسانی شد")
            elif action == "clear-tax-class":
                count = bulk_clear_tax_class(store, product_ids, actor=request.user)
                messages.success(request, f"دسته‌ی مالیاتیِ {count} کالا به پیش‌فرض بازگشت")
            else:
                messages.error(request, "اکشن فله‌ای نامعتبر است")
        except BulkActionError as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))


class ProductPublishError(Exception):
    """کالا برای انتشار (وضعیت فعال) آماده نیست — نگاه کنید به product_publish_service."""


def _product_attribute_field_context(category, product=None):
    """فهرست فیلدهای پویا (طبق طرح ویژگیِ دسته‌بندی) برای رندر در فرم کالا — مقدار فعلی هم پرشده."""
    if category is None:
        return []
    schema_entries = resolve_category_schema(category)
    existing_by_attribute: dict[int, list] = {}
    if product is not None and product.pk:
        for assignment in ProductAttributeValue.objects.filter(product=product).select_related("value"):
            existing_by_attribute.setdefault(assignment.attribute_id, []).append(assignment)

    fields = []
    for entry in schema_entries:
        attribute = entry.attribute
        assignments = existing_by_attribute.get(attribute.pk, [])
        field = {
            "entry": entry, "attribute": attribute,
            "field_name": f"attr_{attribute.pk}",
            "text_value": "", "number_value": None, "boolean_value": None,
            "selected_value_id": None, "selected_value_ids": set(),
        }
        if attribute.data_type in (Attribute.DataType.TEXT, Attribute.DataType.DATE) and assignments:
            field["text_value"] = assignments[0].text_value
        elif attribute.data_type == Attribute.DataType.NUMBER and assignments:
            field["number_value"] = assignments[0].number_value
        elif attribute.data_type == Attribute.DataType.BOOLEAN and assignments:
            field["boolean_value"] = assignments[0].boolean_value
        elif attribute.data_type in (Attribute.DataType.SELECT, Attribute.DataType.COLOR) and assignments:
            field["selected_value_id"] = assignments[0].value_id
        elif attribute.data_type == Attribute.DataType.MULTISELECT:
            field["selected_value_ids"] = {a.value_id for a in assignments}
        fields.append(field)
    return fields


def _save_product_metafields(request, product):
    """ذخیره‌ی متادیتاهایِ فرم‌محور (سایزگاید/سازنده/منطقه) از POST data."""
    from apps.catalog.services.metafield_service import save_product_metafields_from_form

    save_product_metafields_from_form(
        product,
        size_guide_content=request.POST.get("metafield_size_guide", "").strip(),
        maker=request.POST.get("metafield_maker", "").strip(),
        region=request.POST.get("metafield_region", "").strip(),
    )


def _save_product_attribute_values(request, product):
    """مقادیر فیلدهای پویا (``attr_<id>``) را طبق طرح ویژگیِ دسته‌بندیِ فعلی کالا ذخیره می‌کند."""
    for entry in resolve_category_schema(product.category):
        attribute = entry.attribute
        field_name = f"attr_{attribute.pk}"

        if attribute.data_type == Attribute.DataType.MULTISELECT:
            remove_product_attribute_value(product, attribute)
            for raw_id in request.POST.getlist(field_name):
                value = AttributeValue.objects.filter(pk=raw_id, attribute=attribute).first()
                if value is not None:
                    add_product_attribute_multiselect_value(product, attribute, value)
            continue

        raw = request.POST.get(field_name, "").strip()
        if attribute.data_type in (Attribute.DataType.SELECT, Attribute.DataType.COLOR):
            if not raw:
                remove_product_attribute_value(product, attribute)
                continue
            value = AttributeValue.objects.filter(pk=raw, attribute=attribute).first()
            if value is not None:
                set_product_attribute_value(product, attribute, value=value)
        elif attribute.data_type == Attribute.DataType.NUMBER:
            if not raw:
                remove_product_attribute_value(product, attribute)
                continue
            try:
                number = Decimal(normalize_digits(raw))
            except InvalidOperation:
                continue
            set_product_attribute_value(product, attribute, number_value=number)
        elif attribute.data_type == Attribute.DataType.BOOLEAN:
            if raw not in ("true", "false"):
                remove_product_attribute_value(product, attribute)
                continue
            set_product_attribute_value(product, attribute, boolean_value=(raw == "true"))
        else:  # TEXT / DATE
            if not raw:
                remove_product_attribute_value(product, attribute)
                continue
            set_product_attribute_value(product, attribute, text_value=raw)


class ProductMediaStageError(Exception):
    """خطای قابل‌نمایش هنگامِ پردازشِ تصاویر/ویدیوی هم‌زمان با ساختِ کالای جدید."""


def _save_staged_product_media(request, product) -> None:
    """تصاویر و ویدیوی ارسال‌شده هم‌زمان با فرمِ *ساختِ* کالای جدید را ثبت می‌کند.

    فقط برایِ مسیرِ ساختِ کالا فراخوانی می‌شود — کالای موجود از مسیرِ
    آپلودِ فوریِ همین تب (htmx مستقیم روی endpointِ تصویر/ویدیو) استفاده
    می‌کند. این تابع همیشه داخلِ تراکنشِ اتمیکِ ``product_form`` اجرا
    می‌شود؛ اگر تصویر یا ویدیو نامعتبر باشد، کلِ ساختِ کالا (شاملِ خودِ
    ردیفِ Product) برگردانده می‌شود — طبقِ الزامِ «ذخیره‌ی اتمیکِ رسانه
    همراه با کالای جدید»."""
    files = request.FILES.getlist("images")
    if files:
        image_form = ProductImageUploadForm(request.POST, request.FILES)
        if not image_form.is_valid():
            raise ProductMediaStageError("فایلِ تصویرِ انتخاب‌شده معتبر نیست.")
        created_images = []
        for file in image_form.cleaned_data.get("images") or []:
            try:
                created_images.append(add_product_image(product, file))
            except ProductImageError as exc:
                raise ProductMediaStageError(f"{file.name}: {exc}") from exc
        cover_raw = request.POST.get("cover_index", "").strip()
        if cover_raw.isdigit():
            index = int(cover_raw)
            if 0 <= index < len(created_images):
                set_cover_image(product, created_images[index].pk)

    video_url = request.POST.get("video_url", "").strip()
    if video_url:
        video_title = request.POST.get("video_title", "").strip()
        try:
            add_product_video(product, url=video_url, title=video_title)
        except ProductVideoError as exc:
            raise ProductMediaStageError(str(exc)) from exc


def _save_product(form, product, *, store):
    data = form.cleaned_data
    if product is None:
        # گیتِ اشتراک/سقفِ کالا (checkpoint 5A، ADR-69) — فقط مسیرِ ساختِ
        # یک‌مرحله‌ایِ قدیمی (بدونِ پیش‌نویس)؛ مسیرِ اصلیِ تازه (پیش‌نویسِ
        # تمام‌صفحه) همین گیت را زودتر، هنگامِ خودِ ساختِ پیش‌نویس، اجرا
        # می‌کند — نگاه کنید به ``apps.catalog.services.product_draft_service.get_or_create_product_draft``.
        from apps.subscriptions.services.enforcement import enforce_can_create_product

        enforce_can_create_product(store)
        vendor = default_vendor(store)
        product = Product(store=store, vendor=vendor)
    if not product.slug:
        # هم برایِ کالایِ کاملاً تازه (بالا) و هم برایِ نهایی‌کردنِ یک
        # پیش‌نویس (که با slug="" ساخته شده — نگاه کنید به ``product_draft_service``)؛
        # اگر merchant خودش در تبِ سئو آدرسی وارد کرده باشد، پایین‌تر
        # (``data.get("slug")``) رویِ همین مقدار می‌نویسد.
        product.slug = generate_unique_slug(Product, data["name"], store=store, instance=product)
    # این‌جا رسیدن یعنی فرم با نام/کد/دسته‌بندی/قیمتِ واقعی معتبر بوده —
    # پیش‌نویسِ داخلیِ در حالِ ساخت (اگر بود) از همین لحظه یک کالای کامل است.
    product.is_draft_placeholder = False
    product.name = data["name"]
    product.sku = data["sku"]
    product.category = data["category"]
    product.unit = data.get("unit") or Product.Unit.PIECE
    product.model_code = data.get("model_code") or ""
    product.country_of_origin = data.get("country_of_origin") or ""
    product.brand = data.get("brand")
    product.price = data["price"]
    product.discount_percent = data["discount_percent"]
    product.stock = data["stock"]
    product.status = data["status"]
    product.icon = data["icon"] or "🛍️"
    product.description = data["description"]
    product.barcode = data.get("barcode") or ""
    product.weight_grams = data.get("weight_grams")
    product.requires_shipping = data.get("requires_shipping", True)
    product.tax_class = data.get("tax_class")
    product.seo_title = data.get("seo_title") or ""
    product.seo_description = data.get("seo_description") or ""
    product.visibility = data.get("visibility") or Product.Visibility.PUBLIC
    product.publish_at = data.get("publish_at")
    if data.get("slug"):
        product.slug = data["slug"]
    product.full_clean(exclude=["slug"] if not data.get("slug") else [])
    product.save()
    # «گروهِ دوم» با همان رابطه‌ی M2M برچسب‌هایِ عادی ذخیره می‌شود (فقط با
    # purpose=COLLECTION متمایز است) — پس هر دو باید در یک .set() یک‌جا
    # نوشته شوند، وگرنه فراخوانیِ دومِ .set() اولی را پاک می‌کرد.
    ordinary_tags = get_or_create_tags(store, data.get("tags") or [])
    second_group = data.get("second_group")
    product.tags.set([*ordinary_tags, *([second_group] if second_group else [])])
    return product


#: کلیدهایِ معتبرِ تبِ فرمِ کالا — همان پنج تبِ ``product_form.html``؛ برایِ
#: اعتبارسنجیِ ``current_tab``ِ ارسال‌شده (رجوع کنید به هندلرِ موفقیتِ
#: ``product_form``: بعد از ذخیره‌ی موفق، merchant باید رویِ همان تبی بماند
#: که رویش بود، نه همیشه تبِ اول).
_PRODUCT_WIZARD_TAB_KEYS = {"basic", "category", "price", "media", "seo"}

#: نامِ فیلد → کلیدِ تبِ فرمِ کالا (product_form.html) — برایِ اینکه وقتی
#: اعتبارسنجیِ سمتِ سرور خطا می‌دهد، کاربر مستقیماً به همان تبی برود که خطا
#: در آن است، نه همیشه تبِ اول (فرم هر بار از نو با ``x-data`` مقداردهی
#: می‌شود، پس این تب باید سمتِ سرور محاسبه و به قالب داده شود).
_PRODUCT_WIZARD_FIELD_STEPS = {
    # تبِ ۱ — اطلاعات پایه: نام، کد کالا، برند، واحدِ شمارش، مدل/کدِ فنی،
    # برچسب‌ها، توضیحات، وضعیت — دقیقاً همان چیدمانِ پروتوتایپِ نهاییِ
    # تأییدشده (unit/model_code اینجا هستند، نه در تبِ دسته‌بندی).
    "name": "basic", "sku": "basic", "icon": "basic", "description": "basic",
    "brand": "basic", "status": "basic", "tags": "basic",
    "unit": "basic", "model_code": "basic",
    # تبِ «تصاویر و فیلم» فیلدهایِ ProductForm ندارد (images/video_url/video_title
    # مستقیماً از request.POST/FILES خوانده می‌شوند)؛ خطاهایش با error_step="media"
    # مستقیم در ``product_form`` مدیریت می‌شود، نه از این نگاشت.
    # تبِ ۲ — دسته‌بندی: دسته‌بندی، گروهِ دوم، کشورِ سازنده
    "category": "category", "second_group": "category", "country_of_origin": "category",
    # تبِ ۳ — قیمت و تنوع: نوعِ کالا، قیمت، تخفیف، مالیات، لجستیک، موجودی
    "price": "price", "discount_percent": "price", "tax_class": "price",
    "barcode": "price", "weight_grams": "price", "requires_shipping": "price",
    "product_type": "price", "stock": "price",
    # تبِ ۵ — سئو و انتشار
    "seo_title": "seo", "seo_description": "seo", "slug": "seo",
}


def _product_form_initial(product) -> dict:
    """مقادیرِ اولیه‌ی فرمِ کالا برایِ یک کالایِ *موجود* — ``ProductForm`` یک
    ``forms.Form`` سادّه است، نه ``ModelForm``، پس با دادنِ ``instance=``
    مقادیرِ فیلدها خودکار پر نمی‌شوند؛ این دیکشنری تنها منبعِ آن پرکردن
    است. یک تابعِ مشترک، چون هم مسیرِ GETِ ویرایش و هم مسیرِ «ذخیره و
    ادامه با تنظیمِ ویژگی‌ها» (keep_open) باید دقیقاً همین مقادیر را
    بسازند — یک نسخه‌ی جدا برایِ keep_open، همین باگِ دقیقاً همین‌جا
    (ریست‌شدنِ خاموشِ نوعِ کالا/نمایش/... به‌خاطرِ initialِ ناقص) را دوباره
    ممکن می‌کرد."""
    return {
        "name": product.name, "sku": product.sku, "category": product.category_id,
        "unit": product.unit, "model_code": product.model_code,
        "country_of_origin": product.country_of_origin,
        "second_group": (
            product.tags.filter(purpose=ProductTag.Purpose.COLLECTION).values_list("pk", flat=True).first()
        ),
        "brand": product.brand_id,
        "price": product.price, "discount_percent": product.discount_percent,
        "stock": product.stock, "status": product.status, "icon": product.icon,
        "description": product.description, "product_type": product.product_type,
        "barcode": product.barcode, "weight_grams": product.weight_grams,
        "requires_shipping": product.requires_shipping, "tax_class": product.tax_class_id,
        "seo_title": product.seo_title, "seo_description": product.seo_description,
        "visibility": product.visibility,
        "publish_at": product.publish_at.strftime("%Y-%m-%dT%H:%M") if product.publish_at else "",
    }


def _product_form_extra_context(store, product, *, form=None, request=None, category=None) -> dict:
    """کانتکستِ مشترکِ فرمِ کالا (چک‌لیستِ انتشار، درصدِ تکمیل، برچسب‌های
    فعلی/پیشنهادی، جدولِ ویژگی/تنوع برایِ تبِ «قیمت و تنوع») — در مسیرِ
    موفق و هر مسیرِ خطا یکسان لازم است.

    ``form``: اگر داده شود و برچسب‌هایی در ``cleaned_data`` داشته باشد (یعنی
    این یک بازارسالِ دارایِ خطا است، نه GETِ اول)، همان برچسب‌هایِ *ارسال‌شده*
    نمایش داده می‌شوند، نه برچسب‌هایِ ذخیره‌شده‌ی قبلیِ محصول — وگرنه با هر
    خطایِ اعتبارسنجی (مثلاً SKU تکراری)، برچسب‌هایِ تازه‌واردشده‌ی کاربر
    بی‌سروصدا از دست می‌رفتند."""
    submitted_tags = getattr(form, "cleaned_data", {}).get("tags") if form is not None else None
    if submitted_tags is not None:
        existing_tags_list = submitted_tags
    else:
        existing_tags_list = (
            list(product.tags.filter(purpose=ProductTag.Purpose.GENERAL).values_list("name", flat=True))
            if product else []
        )
    ensure_default_collections(store)
    resolved_category = category if category is not None else (product.category if product else None)
    tree_rows = category_tree_context(store)["rows"]
    categories_by_group = {
        str(row["category"].pk): [
            {"id": child["category"].pk, "name": child["category"].name} for child in row["children"]
        ]
        for row in tree_rows
    }
    # برایِ دکمه‌ی «+ افزودنِ زیرگروه»: اگر کالا از قبل به یک زیرگروهِ نهایی
    # وصل است، گروهِ اصلیِ آن (بالاترین جدِ درخت) را پیدا می‌کند تا مودالِ
    # ساختِ دسته‌بندی بتواند مستقیماً در مرحله‌ی ۲ با همان گروه از پیش‌پرشده
    # باز شود، بدونِ اینکه مدیرِ فروشگاه دوباره گروه را انتخاب کند.
    selected_category_group_id = None
    if resolved_category is not None and resolved_category.parent_id is not None:
        ancestor = resolved_category
        while ancestor.parent_id is not None:
            ancestor = ancestor.parent
        selected_category_group_id = ancestor.pk
    elif request is not None and request.method == "POST":
        # اگر merchant «گروهِ اصلی» را انتخاب کرده اما هنوز «زیرگروه» را
        # انتخاب نکرده (یا هر خطایِ دیگری در فرم باعثِ نامعتبر شدن شده)،
        # ``resolved_category`` چیزی نمی‌دهد که بشود گروه را از رویِ آن
        # حدس زد. بدونِ این fallback، سلکتِ «گروهِ اصلی» با هر بار خطا خالی
        # می‌شد و merchant باید دوباره گروه (و بعد زیرگروه) را انتخاب می‌کرد —
        # این حلقه اغلب باعث می‌شد ذخیره هیچ‌وقت موفق نشود.
        submitted_group_id = request.POST.get("category_group", "").strip()
        if submitted_group_id and submitted_group_id in {str(row["category"].pk) for row in tree_rows}:
            selected_category_group_id = int(submitted_group_id)

    # برایِ دو ‌سلکتِ سادّه‌ی «گروهِ اصلی»/«زیرگروه» (پروتوتایپِ نهاییِ
    # تأییدشده): برخلافِ ``categories_by_group`` (که فقط فرزندانِ مستقیم را
    # می‌دهد و توسطِ مودالِ سه‌مرحله‌ایِ ساختِ دسته‌بندی استفاده می‌شود)، این‌جا
    # برایِ هر گروهِ اصلی، همه‌ی برگ‌هایِ واقعیِ زیرِ آن — با هر عمقی (چه
    # ساختارِ دوسطحیِ قدیمی، چه گروه←دسته←زیرگروهِ سه‌سطحی) — لازم است، چون
    # فیلدِ نمایشیِ «زیرگروه» مستقیماً به همان برگ (نه یک گره‌ی میانی) وصل
    # می‌شود؛ نگاه کنید به ``leaf_categories``.
    group_leaf_options: dict[str, list[dict]] = {str(row["category"].pk): [] for row in tree_rows}
    for leaf in leaf_categories(store):
        root = leaf.parent if leaf.parent.parent_id is None else leaf.parent.parent
        group_leaf_options.setdefault(str(root.pk), []).append({"id": leaf.pk, "name": leaf.name})

    context = {
        "checklist": build_completion_checklist(product) if product else [],
        "completion_pct": completion_percent(product) if product else 0,
        "existing_tags_list": existing_tags_list,
        "tag_suggestions": suggest_tags(store),
        "category_tree_rows": tree_rows,
        "selected_category_path": category_chain(resolved_category) if resolved_category else "",
        "categories_by_group_json": categories_by_group,
        "selected_category_group_id": selected_category_group_id,
        "group_leaf_options_json": group_leaf_options,
        "collection_tags": collection_tags(store),
    }
    # همیشه (نه فقط وقتی ``product_type`` از قبل ``variable`` است) — تبِ «قیمت
    # و تنوع» پنلِ ویژگی/تنوع را همیشه رندر می‌کند (نگاه کنید به
    # ``product_form.html``) تا merchant بتواند در همان لحظه که سوییچِ
    # کالای‌ساده/کالای‌دارایِ‌تنوع را می‌زند، بدونِ نیازِ ذخیره‌ی پنهانِ
    # قبلی، ویژگی و تنوع اضافه کند. ``_product_options_context`` برایِ کالایِ
    # ساده/بدونِ محور هم امن است (فهرست‌هایِ خالی برمی‌گرداند).
    if product is not None:
        context.update(_product_options_context(request, product))
        # ``product_form.html`` تبِ «تصاویر و فیلم» را با
        # ``{% include "dashboard/partials/product_videos_list.html" %}``
        # می‌سازد که یک متغیرِ ``videos`` می‌خواهد؛ بدونِ این خط، آن متغیر در
        # GET/رفرشِ صفحه هرگز تعریف نمی‌شد (Django آن را بی‌صدا خالی می‌گرفت)
        # پس ویدیوهایی که با موفقیت در دیتابیس ذخیره شده بودند، بعد از هر
        # Refresh انگار اصلاً وجود نداشتند — صرف‌نظر از درستیِ خودِ ذخیره‌سازی.
        context["videos"] = product.videos.all()
        # متادیتاهایِ فرم‌محور (سایزگاید/سازنده/منطقه) — برایِ pre-fill
        from apps.catalog.services.metafield_service import get_product_metafield_values
        context["metafield_values"] = get_product_metafield_values(product)
    return context


def _product_wizard_error_step(form) -> str:
    for field_name in form.errors:
        if field_name.startswith("attr_"):
            return "price"
        step = _PRODUCT_WIZARD_FIELD_STEPS.get(field_name)
        if step:
            return step
    return "basic"


@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_form(request, pk=None):
    """صفحه‌ی تمام‌صفحه‌ی «افزودن/ویرایشِ کالا» — پیاده‌سازیِ مشترکِ Create/Edit
    (بدون سیستمِ موازی). وقتی ``pk`` داده شود، ``product`` می‌تواند یک کالای
    واقعیِ قبلاً ذخیره‌شده باشد یا یک پیش‌نویسِ داخلیِ در حالِ ساخت
    (``is_draft_placeholder=True`` — نگاه کنید به ``apps.catalog.services.product_draft_service``
    و مسیرِ ``product_create_entry`` که آن را می‌سازد/از سر می‌گیرد و به این‌جا
    هدایت می‌کند)؛ هر دو از همین یک ویو رد می‌شوند، پس تبِ «قیمت و تنوع» از
    همان اولین بارگذاری یک ``product_id`` واقعی برایِ اتصالِ ویژگی/تنوع دارد."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    is_new = product is None
    finalizing_draft = product is not None and product.is_draft_placeholder
    category_groups = Category.objects.filter(store=store, parent__isnull=True).order_by("order", "name")

    old_category_id = product.category_id if product else None

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, store=store)
        if form.is_valid():
            requested_type = form.cleaned_data.get("product_type") or None
            try:
                with transaction.atomic():
                    product = _save_product(form, product, store=store)
                    if requested_type and requested_type != product.product_type:
                        set_product_type(product, requested_type)
                    _save_product_attribute_values(request, product)
                    _save_product_metafields(request, product)
                    if is_new:
                        _save_staged_product_media(request, product)
                    if product.status == Product.Status.ACTIVE:
                        publish_errors = validate_product_for_publish(product)
                        if publish_errors:
                            raise ProductPublishError(publish_errors)
            except (ProductTypeError, EntitlementError) as exc:
                form.add_error(None, str(exc))
                category = form.cleaned_data.get("category")
                attribute_fields = _product_attribute_field_context(category, product)
                return render(request, "dashboard/product_form_page.html", {
                    "form": form, "product": product, "attribute_fields": attribute_fields, "category": category,
                    "category_groups": category_groups, "error_step": _product_wizard_error_step(form),
                    **_product_form_extra_context(store, product, form=form, request=request, category=category),
                })
            except ProductMediaStageError as exc:
                form.add_error(None, str(exc))
                category = form.cleaned_data.get("category")
                attribute_fields = _product_attribute_field_context(category, None)
                return render(request, "dashboard/product_form_page.html", {
                    "form": form, "product": None, "attribute_fields": attribute_fields, "category": category,
                    "category_groups": category_groups, "error_step": "media",
                    **_product_form_extra_context(store, None, form=form, request=request, category=category),
                })
            except ProductPublishError as exc:
                for message in exc.args[0]:
                    form.add_error(None, message)
                category = form.cleaned_data.get("category")
                attribute_fields = _product_attribute_field_context(category, product)
                return render(request, "dashboard/product_form_page.html", {
                    "form": form, "product": product, "attribute_fields": attribute_fields, "category": category,
                    "category_groups": category_groups, "error_step": _product_wizard_error_step(form),
                    **_product_form_extra_context(store, product, form=form, request=request, category=category),
                })
            except ValidationError as exc:
                # نامِ حلقه عمداً ``messages`` نیست: ``django.contrib.messages``
                # در همین فایل ایمپورت شده و اگر این نام دوباره اینجا استفاده
                # شود، پایتون آن را در کلِ تابع محلی می‌کند (حتی در شاخه‌های
                # دیگر) و ``messages.success(...)``ی پایین‌ترِ همین تابع را با
                # ``UnboundLocalError`` می‌شکند.
                for field, field_messages in exc.message_dict.items():
                    for message in field_messages:
                        form.add_error(field if field in form.fields else None, message)
                category = form.cleaned_data.get("category")
                attribute_fields = _product_attribute_field_context(category, product)
                return render(request, "dashboard/product_form_page.html", {
                    "form": form, "product": product, "attribute_fields": attribute_fields, "category": category,
                    "category_groups": category_groups, "error_step": _product_wizard_error_step(form),
                    **_product_form_extra_context(store, product, form=form, request=request, category=category),
                })

            action = "ویرایش" if not (is_new or finalizing_draft) else "افزوده"
            toast_message = f"کالا با موفقیت {action} شد"
            if old_category_id and old_category_id != product.category_id:
                orphan_count = orphaned_product_attribute_values(product).count()
                if orphan_count:
                    toast_message = (
                        f"کالا {action} شد — {orphan_count} مقدار ویژگی با دسته‌بندی جدید مطابقت ندارد "
                        "و برای بازبینی/پاک‌سازی در فرم ویرایش نگه داشته شده است."
                    )
            messages.success(request, toast_message)
            # صفحه‌ی تمام‌صفحه (بدونِ مودال) دوباره همین‌جا رندر می‌شود — نه
            # ریدایرکت — چون فرم دیگر یک سوآپِ htmx داخلِ یک مودال نیست؛ کالا
            # (یا پیش‌نویسِ به‌تازگی نهایی‌شده) هنوز دقیقاً همان صفحه‌ی
            # ویرایشِ تمام‌صفحه‌ای است که merchant رویش بود.
            category = product.category
            attribute_fields = _product_attribute_field_context(category, product)
            orphaned_count = orphaned_product_attribute_values(product).count()
            reopened_form = ProductForm(instance=product, initial=_product_form_initial(product), store=store)
            submitted_tab = request.POST.get("current_tab") or "basic"
            if submitted_tab not in _PRODUCT_WIZARD_TAB_KEYS:
                submitted_tab = "basic"
            return render(request, "dashboard/product_form_page.html", {
                "form": reopened_form, "product": product, "attribute_fields": attribute_fields,
                "orphaned_count": orphaned_count, "category": category, "category_groups": category_groups,
                "error_step": submitted_tab,
                **_product_form_extra_context(store, product, form=reopened_form, request=request, category=category),
            })
    else:
        if product is not None and product.is_draft_placeholder:
            # هر GETِ موفق یعنی merchant هنوز رویِ این پیش‌نویس کار می‌کند —
            # تایمرِ پاک‌سازیِ خودکار (``cleanup_stale_product_drafts``) را ریست
            # می‌کند تا کارِ در حالِ انجام هرگز حذف نشود.
            touch_product_draft(product)
        initial = _product_form_initial(product) if product else {"product_type": Product.ProductType.SIMPLE}
        form = ProductForm(instance=product, initial=initial, store=store)

    # این نقطه فقط با یک POSTِ نامعتبر (``form.is_valid()`` نادرست) یا یک GET
    # به این‌جا می‌رسد. برایِ POSTِ نامعتبر، ``product.category`` (دسته‌بندیِ
    # قبلاً *ذخیره‌شده*) کافی نیست — یک کالای تازه هنوز هیچ دسته‌بندیِ
    # ذخیره‌شده‌ای ندارد، پس سلکتِ «گروهِ اصلی» با هر بار خطا دوباره خالی
    # می‌شد و merchant مجبور بود گروه را از نو انتخاب کند (درحالی‌که زیرگروه
    # هم‌چنان خالی می‌ماند و ذخیره هرگز موفق نمی‌شد). دسته‌بندیِ *ارسال‌شده*
    # (حتی اگر خودش نامعتبر/ناقص باشد) باید اولویت داشته باشد تا انتخابِ
    # گروهِ merchant حفظ شود.
    category = product.category if product else None
    if request.method == "POST":
        submitted_category_id = request.POST.get("category")
        category = (
            Category.objects.filter(store=store, pk=submitted_category_id).first()
            if submitted_category_id else None
        ) or category
    attribute_fields = _product_attribute_field_context(category, product)
    orphaned_count = orphaned_product_attribute_values(product).count() if product else 0
    return render(request, "dashboard/product_form_page.html", {
        "form": form, "product": product, "attribute_fields": attribute_fields, "orphaned_count": orphaned_count,
        "category": category, "category_groups": category_groups, "error_step": _product_wizard_error_step(form),
        **_product_form_extra_context(store, product, form=form, request=request, category=category),
    })


@staff_required
@permission_required(PRODUCT_CREATE)
def product_create_entry(request):
    """نقطه‌ی ورودِ URLِ ``/admin-portal/products/new/`` — GET یک پیش‌نویسِ
    قابلِ‌ازسرگیری می‌سازد/از سر می‌گیرد و به صفحه‌ی تمام‌صفحه‌ی
    ``product_form`` (همان پیاده‌سازیِ Edit) هدایت می‌کند، تا آدرسِ مرورگر
    واقعاً عوض شود، رفرش/دکمه‌ی برگشت کار کند، و تبِ «قیمت و تنوع» از همان
    اولین لحظه (پیش از تکمیلِ نام/دسته‌بندی) یک کالای واقعی برایِ اتصالِ
    ویژگی/تنوع داشته باشد — نگاه کنید به گزارشِ ریشه‌ای
    ``docs/reports/PRODUCT_ENTRY_FULL_PAGE_ROOT_CAUSE.md``.

    POST مستقیم به همین آدرس (سازگاریِ عقب‌رو با فراخوان‌هایِ برنامه‌ای/تستیِ
    قدیمی که کالا را یک‌مرحله‌ای با کلِ payload می‌سازند) دقیقاً همان
    ``product_form(request, pk=None)``ِ قبلی را اجرا می‌کند — بدونِ هیچ
    سیستمِ موازی."""
    if request.method == "POST":
        return product_form(request, pk=None)
    store = _resolve_dashboard_store(request)
    try:
        draft = get_or_create_product_draft(store, request.user)
    except EntitlementError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:product-list")
    return redirect("dashboard:product-edit", pk=draft.pk)


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_discard_draft(request, pk):
    """اکشنِ صریحِ «انصراف» رویِ یک پیش‌نویسِ در حالِ ساخت — کالای واقعیِ
    قبلاً ذخیره‌شده را هرگز حذف نمی‌کند (فقط ``is_draft_placeholder=True``
    قابلِ حذف با این مسیر است)، پس تأییدِ کاربر در سمتِ کلاینت کافی است،
    بدونِ خطرِ از دست رفتنِ کارِ واقعیِ merchant."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store, is_draft_placeholder=True)
    discard_product_draft(product)
    messages.success(request, "پیش‌نویس لغو شد.")
    return redirect("dashboard:product-list")


@staff_required
@permission_required(PRODUCT_VIEW)
def product_preview(request, pk):
    """پیش‌نمایشِ کالا — فقط برایِ مدیرِ فروشگاه، حتی وقتی کالا هنوز منتشر
    (فعال) نیست؛ همان قالبِ صفحه‌ی محصولِ فروشگاه را با همان کانتکست رندر
    می‌کند (نگاه کنید به apps.catalog.views.build_product_detail_context)."""
    from apps.catalog.views import build_product_detail_context
    from apps.storefront_builder.models import StorefrontPage
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )

    store = _resolve_dashboard_store(request)
    product = get_object_or_404(
        Product.objects.select_related("brand", "category", "category__parent", "vendor"),
        pk=pk, store=store,
    )
    context = build_product_detail_context(request, product)
    context["is_merchant_preview"] = True
    # Phase 5: همان پوسته/چیدمانِ منتشرشده‌یِ همینِ Store — بدونِ این،
    # render_items خالی می‌ماند و پیش‌نمایشِ کالایِ منتشرنشده هیچ بدنه‌ای
    # نشان نمی‌دهد (نگاه کنید به apps.catalog.views.product_detail که
    # همین الگو را برایِ محصولاتِ منتشرشده استفاده می‌کند).
    context.update(build_universal_storefront_context(
        request, store, StorefrontPage.PageType.PRODUCT_DETAIL, page_context=context,
    ))
    return render(request, "catalog/product_detail.html", context)


@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_attribute_fields(request, pk=None):
    """بارگذاری/تازه‌سازی فیلدهای پویای ویژگی — هنگام تغییر دسته‌بندی در فرم کالا (بدون ارسال کل فرم)."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    category_id = request.GET.get("category", "").strip()
    category = Category.objects.filter(pk=category_id, store=store).first() if category_id else None
    attribute_fields = _product_attribute_field_context(category, product)
    return render(request, "dashboard/partials/product_attribute_fields.html", {
        "attribute_fields": attribute_fields, "product": product, "category": category,
    })


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_sku_generate(request):
    """دکمه‌ی «تولید» کنارِ فیلدِ کدِ کالا — فقط یک پیشنهادِ متنیِ ساده
    برمی‌گرداند (نه رندرِ کلِ فرم)؛ فیلد همچنان توسطِ مدیرِ فروشگاه
    قابلِ‌ویرایش می‌ماند و یکتاییِ نهایی هنگامِ ذخیره از نو بررسی می‌شود."""
    store = _resolve_dashboard_store(request)
    return HttpResponse(generate_product_sku(store), content_type="text/plain")


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_quick_add_brand(request):
    """«+ افزودن برند» داخل فرمِ کالا — بدون ترکِ فرم و بدون از دست رفتنِ
    داده‌های واردشده؛ فقط ‌select برند دوباره رندر و مقدارِ تازه انتخاب می‌شود."""
    store = _resolve_dashboard_store(request)
    # ورودیِ نامِ برند در این پنلِ کوچک عمداً ``quick_brand_name`` است، نه
    # ``name`` — چون این پنل داخلِ همان فرمِ کالا رندر می‌شود و htmx مقادیرِ
    # تمامِ فرمِ دربرگیرنده را هم می‌فرستد؛ اگر این فیلد هم ``name`` بود، با
    # فیلدِ «نام کالا»یِ خودِ فرم تداخل می‌کرد.
    form = BrandForm(data={"name": request.POST.get("quick_brand_name", "")})
    selected_id = None
    if form.is_valid():
        try:
            brand = create_brand(store, name=form.cleaned_data["name"])
        except BrandError:
            pass
        else:
            selected_id = brand.pk
    return render(request, "dashboard/partials/product_brand_select.html", {
        "brand_queryset": Brand.objects.filter(store=store).order_by("name"),
        "selected_brand_id": selected_id,
        "quick_errors": form.errors if not form.is_valid() else None,
    })


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_quick_add_collection(request):
    """«+ افزودن گروه دوم» داخل فرمِ کالا — همان الگویِ «+ افزودن برند»، فقط
    یک ProductTagِ جدید با purpose=COLLECTION می‌سازد (یا اگر از قبل با همان
    نام موجود بود، آن را با purpose=COLLECTION فعال می‌کند)."""
    store = _resolve_dashboard_store(request)
    name = (request.POST.get("quick_collection_name") or "").strip()
    selected_id = None
    error = None
    if not name:
        error = "نامِ گروهِ دوم را وارد کنید."
    else:
        tag = get_or_create_collection_tag(store, name)
        selected_id = tag.pk
    return render(request, "dashboard/partials/product_second_group_select.html", {
        "collection_tags": collection_tags(store),
        "selected_second_group_id": selected_id,
        "quick_error": error,
    })


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_quick_add_category(request, pk=None):
    """«+ ساختِ دسته‌بندی جدید» داخل فرمِ کالا — همیشه سه‌سطحی (گروه اصلی ←
    دسته ← زیرگروه نهایی)؛ هر سطح یا گره‌ی موجود را استفاده می‌کند یا
    تازه می‌سازد. کالا فقط به زیرگروهِ نهایی (برگ) وصل می‌شود (نگاه کنید
    به ``leaf_categories``)."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    form = ProductQuickCategoryForm(request.POST, store=store)
    selected_id = None
    selected_category = None
    if form.is_valid():
        with transaction.atomic():
            group = form.cleaned_data["group"]
            if group is None:
                group_name = form.cleaned_data["new_group_name"].strip()
                group = Category.objects.create(
                    store=store, name=group_name, icon="📁",
                    slug=generate_unique_slug(Category, group_name, store=store),
                )
            category = form.cleaned_data["category"]
            if category is None:
                category_name = form.cleaned_data["new_category_name"].strip()
                category = Category.objects.create(
                    store=store, name=category_name, parent=group,
                    slug=generate_unique_slug(Category, category_name, store=store),
                )
            sub_name = form.cleaned_data["sub_name"]
            selected_category = Category.objects.create(
                store=store, name=sub_name, parent=category,
                slug=generate_unique_slug(Category, sub_name, store=store),
            )
            selected_id = selected_category.pk

    select_html = render_to_string("dashboard/partials/product_category_select.html", {
        "product": product, "selected_category_id": selected_id,
        "quick_errors": form.errors if not form.is_valid() else None,
        "quick_form_data": request.POST if not form.is_valid() else None,
        **_product_form_extra_context(store, product, category=selected_category),
    }, request=request)
    attribute_fields = _product_attribute_field_context(selected_category, product)
    fields_html = render_to_string("dashboard/partials/product_attribute_fields.html", {
        "attribute_fields": attribute_fields, "product": product, "category": selected_category, "oob": True,
    }, request=request)
    banner_html = render_to_string("dashboard/partials/product_no_category_banner.html", {
        "has_leaf_categories": leaf_categories(store), "oob": True,
    }, request=request)
    return HttpResponse(select_html + fields_html + banner_html)


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_quick_add_attribute(request, pk=None):
    """«+ ساختِ ویژگی جدید» داخل فرمِ کالا — ویژگیِ متنیِ تازه بلافاصله به
    طرحِ ویژگیِ دسته‌بندیِ انتخاب‌شده اضافه و در همین فرم قابل‌پرکردن می‌شود.
    تنظیماتِ پیشرفته‌تر (نوعِ داده و...) همچنان فقط در صفحه‌ی ویژگی‌ها است."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    category_id = request.POST.get("category", "").strip()
    category = Category.objects.filter(pk=category_id, store=store).first() if category_id else None
    form = ProductQuickAttributeForm(request.POST)
    quick_error = None
    if category is None:
        quick_error = "اول یک دسته‌بندی برای کالا انتخاب کنید."
    elif form.is_valid():
        try:
            label = form.cleaned_data["label"]
            # از ساختِ دو ویژگیِ هم‌نامِ جداگانه (با کدهایی مثل «رنگ»/«رنگ-2»)
            # پرهیز می‌کند — اگر ویژگی‌ای با همین عنوان از قبل روی همین Store
            # هست، همان استفاده و فقط به این دسته‌بندی وصل می‌شود.
            attribute = Attribute.objects.filter(store=store, label=label).first()
            if attribute is None:
                attribute = create_attribute(store, label=label)
            add_category_attribute(category, attribute)
        except (AttributeError_, CategorySchemaError) as exc:
            quick_error = str(exc)
    attribute_fields = _product_attribute_field_context(category, product)
    return render(request, "dashboard/partials/product_attribute_fields.html", {
        "attribute_fields": attribute_fields, "product": product, "category": category,
        "orphaned_count": orphaned_product_attribute_values(product).count() if product else 0,
        "quick_attr_errors": form.errors if not form.is_valid() else None, "quick_attr_error": quick_error,
    })


@require_POST
@staff_required
@permission_required(PRODUCT_EDIT)
def product_attribute_cleanup_orphans(request, pk):
    """مقادیر ویژگیِ منسوخ (خارج از طرح دسته‌بندیِ فعلی) را با تأیید صریح مدیر حذف می‌کند."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    deleted_count = cleanup_orphaned_attribute_values(product)
    attribute_fields = _product_attribute_field_context(product.category, product)
    response = render(request, "dashboard/partials/product_attribute_fields.html", {
        "attribute_fields": attribute_fields, "orphaned_count": 0, "product": product, "category": product.category,
    })
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"{deleted_count} مقدار منسوخ پاک‌سازی شد", "type": "info"},
    })
    return response


@require_POST
@staff_required
@permission_required(PRODUCT_DELETE)
def product_delete(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    name = product.name
    product.delete()
    response = render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"کالای «{name}» حذف شد", "type": "info"}})
    return response


# ------------------------------------------------------- تصاویر کالا


def _image_driving_option_values(product):
    """مقادیرِ محورهایی که ویژگیِ مرتبط‌شان «تصویرمحور» علامت خورده — این‌ها
    در فرمِ مدیریتِ تصاویر به‌عنوانِ گزینه‌ی «اختصاصِ تصویر به مقدار» نمایش
    داده می‌شوند (مستقل از انتخابِ سایرِ محورها)."""
    return ProductOptionValue.objects.filter(
        option__product=product, option__attribute__is_image_driving=True,
    ).select_related("option")


@staff_required
@permission_required(MEDIA_MANAGE)
def product_images(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    return render(request, "dashboard/partials/product_images_modal.html", {
        "product": product, "upload_form": ProductImageUploadForm(),
        "variants": product.variants.all(), "videos": product.videos.all(),
        "image_driving_values": _image_driving_option_values(product),
    })


def _image_list_response(request, product, *, refresh_table=False):
    list_html = render_to_string(
        "dashboard/partials/product_images_list.html",
        {
            "product": product, "variants": product.variants.all(),
            "image_driving_values": _image_driving_option_values(product),
        },
        request=request,
    )
    if not refresh_table:
        return HttpResponse(list_html)
    table_html = render_to_string(
        "dashboard/partials/products_table_inner.html", _product_list_context(request), request=request,
    )
    oob_html = render_to_string(
        "dashboard/partials/oob_wrap.html", {"target_id": "productsTableWrap", "inner_html": table_html},
    )
    return HttpResponse(list_html + oob_html)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_upload(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    form = ProductImageUploadForm(request.POST, request.FILES)
    errors = []
    added = 0

    if form.is_valid():
        files = form.cleaned_data.get("images") or []
        if not files:
            errors.append("لطفاً حداقل یک تصویر انتخاب کنید.")
        for file in files:
            try:
                add_product_image(product, file)
                added += 1
            except ProductImageError as exc:
                errors.append(f"{file.name}: {exc}")
    else:
        errors.append("فایل انتخاب‌شده معتبر نیست.")

    if not errors:
        toast = {"message": "تصویر با موفقیت اضافه شد", "type": "ok"}
    elif added:
        toast = {"message": f"{added} تصویر اضافه شد؛ {errors[0]}", "type": "info"}
    else:
        toast = {"message": errors[0], "type": "error"}

    response = _image_list_response(request, product, refresh_table=True)
    response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_delete(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    delete_product_image(image)
    response = _image_list_response(request, product, refresh_table=True)
    response["HX-Trigger"] = json.dumps({"toast": {"message": "تصویر حذف شد", "type": "info"}})
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_set_cover(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    try:
        set_cover_image(product, image_id)
    except ProductImageError:
        pass
    return _image_list_response(request, product, refresh_table=True)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_move(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    direction = request.POST.get("direction", "")
    if direction in ("up", "down"):
        move_product_image(image, direction)
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_reorder(request, pk):
    """مرتب‌سازیِ کشاندنی (drag) — نگاه کنید به
    ``product_image_service.reorder_product_images``."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    ordered_ids = [int(i) for i in request.POST.getlist("image_ids") if i.strip().isdigit()]
    error = None
    try:
        reorder_product_images(product, ordered_ids)
    except ProductImageReorderError as exc:
        error = str(exc)
    response = _image_list_response(request, product, refresh_table=False)
    if error:
        response["HX-Trigger"] = json.dumps({"toast": {"message": error, "type": "error"}})
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_alt_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    form = ProductImageAltForm(request.POST)
    if form.is_valid():
        update_image_alt(image, form.cleaned_data["alt"])
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_caption_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    update_image_caption(image, request.POST.get("caption", ""))
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_360_toggle(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    set_image_360(image, not image.is_360)
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_variant_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    variant_id = request.POST.get("variant", "").strip()
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product) if variant_id else None
    try:
        set_image_variant(image, variant)
    except ProductImageError:
        pass
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_option_value_update(request, pk, image_id):
    """اختصاصِ تصویر به یک مقدارِ ویژگیِ خاص (مثلاً «قرمز») — نگاه کنید به
    ``set_image_option_value``: مستقل از سایر محورهاست، برخلافِ اختصاص به
    یک ترکیبِ کاملِ تنوع."""
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    option_value_id = request.POST.get("option_value", "").strip()
    option_value = (
        get_object_or_404(ProductOptionValue, pk=option_value_id, option__product=product)
        if option_value_id else None
    )
    try:
        set_image_option_value(image, option_value)
    except ProductImageError:
        pass
    return _image_list_response(request, product, refresh_table=False)


def _video_list_response(request, product, *, toast=None, trigger_extra=None):
    response = render(request, "dashboard/partials/product_videos_list.html", {
        "product": product, "videos": product.videos.all(),
    })
    trigger = dict(trigger_extra or {})
    if toast:
        trigger["toast"] = toast
    if trigger:
        response["HX-Trigger"] = json.dumps(trigger)
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_video_add(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    # ``video_url``/``video_title`` تنها نامِ معتبرِ این دو فیلد در کلِ
    # مسیر است — همان نامی که ``_stage_product_media`` (ساختِ یک‌مرحله‌ایِ
    # کالای جدید) هم می‌خواند؛ هیچ نامِ موازیِ دیگری (مثلِ ``__edit_video_url``
    # یا ``url``) نگه‌داشته نمی‌شود.
    url = request.POST.get("video_url", "").strip()
    title = request.POST.get("video_title", "").strip()
    try:
        add_product_video(product, url=url, title=title)
    except ProductVideoError as exc:
        return _video_list_response(
            request, product, toast={"message": str(exc), "type": "err"},
            trigger_extra={"video-error": {"message": str(exc)}},
        )
    return _video_list_response(
        request, product, toast={"message": "ویدیو اضافه شد", "type": "ok"},
        trigger_extra={"video-added": True},
    )


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_video_delete(request, pk, video_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    video = get_object_or_404(ProductVideo, pk=video_id, product=product)
    delete_product_video(video)
    return _video_list_response(request, product, toast={"message": "ویدیو حذف شد", "type": "info"})


# --------------------------------------------------------- تنوع کالا

VARIANTS_PER_PAGE = 25


def _variant_status_filter(request):
    status = request.GET.get("status", "").strip()
    return status if status in ("active", "inactive") else ""


def _variant_search_query(request):
    return request.GET.get("q", "").strip()


def _variant_page_context(request, product, *, bulk_form=None):
    """کانتکست کامل صفحه‌ی مدیریت تنوع: جست‌وجو، فیلتر وضعیت و صفحه‌بندی — همه محدود به همین کالا.

    شمارش‌های خلاصه (کل/فعال/غیرفعال/موجودی) همیشه روی کل تنوع‌های کالا محاسبه می‌شوند،
    نه فقط نتایج جست‌وجو/صفحه‌ی جاری، تا کارت‌های خلاصه گمراه‌کننده نشوند.
    ترتیب جابه‌جایی (بالا/پایین) همیشه روی ترتیب کامل کالا عمل می‌کند، نه ترتیب محلیِ
    نتیجه‌ی فیلترشده یا صفحه‌ی جاری — برای همین وقتی جست‌وجو یا فیلتر فعال است،
    دکمه‌های جابه‌جایی در قالب مخفی می‌شوند (ordering_locked) تا معنای «بالا/پایین»
    هرگز به‌صورت خاموش به ترتیب محلی صفحه تبدیل نشود.
    """
    q = _variant_search_query(request)
    status = _variant_status_filter(request)
    is_filtered = bool(q or status)

    base_qs = product.variants.all()
    variant_count = base_qs.count()
    active_variant_count = base_qs.filter(is_active=True).count()
    inactive_variant_count = variant_count - active_variant_count
    active_variant_stock = base_qs.filter(is_active=True).aggregate(total=Sum("stock"))["total"] or 0

    filtered_qs = base_qs.annotate(
        has_order_history=Exists(OrderItem.objects.filter(variant=OuterRef("pk")))
    )
    if q:
        filtered_qs = filtered_qs.filter(Q(attribute__icontains=q) | Q(value__icontains=q) | Q(sku__icontains=q))
    if status:
        filtered_qs = filtered_qs.filter(is_active=(status == "active"))
    filtered_qs = filtered_qs.order_by("display_order", "attribute", "value").prefetch_related(
        "images", "option_values"
    )

    paginator = Paginator(filtered_qs, VARIANTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    variants = list(page_obj.object_list)
    prefetch_related_objects([product], "images")
    for variant in variants:
        variant.effective_price = resolve_effective_price(product, variant)
        variant.product = product

    global_ids = list(base_qs.order_by("display_order", "attribute", "value").values_list("pk", flat=True))

    querystring_params = request.GET.copy()
    querystring_params.pop("page", None)

    return {
        "product": product,
        "variants": variants,
        "page_obj": page_obj,
        "variant_count": variant_count,
        "active_variant_count": active_variant_count,
        "inactive_variant_count": inactive_variant_count,
        "active_variant_stock": active_variant_stock,
        "bulk_form": bulk_form or VariantBulkAddForm(),
        "active_page": "products",
        "search_query": q,
        "status_filter": status,
        "is_filtered": is_filtered,
        "ordering_locked": is_filtered,
        "global_first_id": global_ids[0] if global_ids else None,
        "global_last_id": global_ids[-1] if global_ids else None,
        "querystring": querystring_params.urlencode(),
        "full_querystring": request.GET.urlencode(),
    }


def _variant_list_redirect(request, product):
    """بازگشت به صفحه‌ی تنوع‌ها با حفظ جست‌وجو/فیلتر/صفحه‌ی جاری (از querystring همان درخواست)."""
    url = reverse("dashboard:product-variants", args=[product.pk])
    query = request.GET.urlencode()
    return redirect(f"{url}?{query}" if query else url)


def _get_scoped_product(request, pk):
    """کالای همین Store را برمی‌گرداند — نه کالای ساده/متعلق به Store دیگر."""
    return get_object_or_404(Product, pk=pk, store=_resolve_dashboard_store(request))


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants(request, pk):
    product = _get_scoped_product(request, pk)
    return render(request, "dashboard/product_variants.html", _variant_page_context(request, product))


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_bulk_add(request, pk):
    product = _get_scoped_product(request, pk)
    if not product.is_variable:
        messages.error(request, "برای افزودن تنوع، ابتدا کالا را از ویرایش کالا به «دارای تنوع» تبدیل کنید.")
        return redirect("dashboard:product-variants", pk=product.pk)

    form = VariantBulkAddForm(request.POST)
    if form.is_valid():
        try:
            created, skipped = bulk_create_variants(
                product,
                attribute=form.cleaned_data["attribute"],
                raw_values=form.cleaned_data["raw_values"],
                default_stock=form.cleaned_data["default_stock"],
                default_extra_price=form.cleaned_data["default_extra_price"],
                is_active=form.cleaned_data["is_active"],
            )
        except VariantError as exc:
            form.add_error(None, str(exc))
        else:
            if created:
                message = f"{len(created)} مقدار تنوع اضافه شد"
                if skipped:
                    message += f" — {skipped[0]}"
                messages.success(request, message)
                return redirect("dashboard:product-variants", pk=product.pk)
            form.add_error(None, skipped[0] if skipped else "هیچ مقداری اضافه نشد")

    return render(
        request, "dashboard/product_variants.html", _variant_page_context(request, product, bulk_form=form)
    )


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_edit(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    if request.method == "POST":
        form = VariantEditForm(request.POST)
        if form.is_valid():
            try:
                update_variant(
                    variant,
                    attribute=form.cleaned_data["attribute"],
                    value=form.cleaned_data["value"],
                    sku=form.cleaned_data["sku"],
                    extra_price=form.cleaned_data["extra_price"],
                    stock=form.cleaned_data["stock"],
                    is_active=form.cleaned_data["is_active"],
                )
            except VariantError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, f"مقدار تنوع «{variant.value}» با موفقیت ویرایش شد")
                back_url = reverse("dashboard:product-variants", args=[product.pk])
                back_query = request.POST.get("back_query", "")
                return redirect(f"{back_url}?{back_query}" if back_query else back_url)
    else:
        form = VariantEditForm(initial={
            "attribute": variant.attribute, "value": variant.value, "sku": variant.sku,
            "extra_price": variant.extra_price, "stock": variant.stock, "is_active": variant.is_active,
        })

    back_url = reverse("dashboard:product-variants", args=[product.pk])
    back_query = request.GET.urlencode() or request.POST.get("back_query", "")
    return render(request, "dashboard/product_variant_edit.html", {
        "product": product, "variant": variant, "form": form, "active_page": "products",
        "back_url": f"{back_url}?{back_query}" if back_query else back_url,
        "back_query": back_query,
    })


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_toggle(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    try:
        if variant.is_active:
            deactivate_variant(variant)
            messages.info(request, f"مقدار تنوع «{variant.value}» غیرفعال شد")
        else:
            update_variant(variant, is_active=True)
            messages.success(request, f"مقدار تنوع «{variant.value}» فعال شد")
    except VariantError as exc:
        messages.error(request, str(exc))

    return _variant_list_redirect(request, product)


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_delete(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    if request.method != "POST":
        if variant.order_items.exists():
            messages.error(
                request,
                f"مقدار تنوع «{variant.value}» در سفارش‌های ثبت‌شده استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید.",
            )
            return _variant_list_redirect(request, product)
        cancel_url = reverse("dashboard:product-variants", args=[product.pk])
        if request.GET.urlencode():
            cancel_url = f"{cancel_url}?{request.GET.urlencode()}"
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "مقدار تنوع",
            "object_name": f"{variant.attribute}: {variant.value}",
            "cancel_url": cancel_url,
            "active_page": "products",
        })

    try:
        delete_variant(variant)
        messages.success(request, f"مقدار تنوع «{variant.value}» حذف شد")
    except VariantError as exc:
        messages.error(request, str(exc))

    return _variant_list_redirect(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_duplicate(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    try:
        duplicate_variant(variant)
        messages.success(request, f"یک کپی از «{variant.value}» ساخته شد — آن را غیرفعال نگه داشتیم تا پیش از انتشار ویرایشش کنید.")
    except VariantError as exc:
        messages.error(request, str(exc))
    return _variant_list_redirect(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_move(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    direction = request.POST.get("direction", "")

    ordered_ids = list(
        product.variants.order_by("display_order", "attribute", "value").values_list("pk", flat=True)
    )
    if direction in ("up", "down") and variant.pk in ordered_ids:
        index = ordered_ids.index(variant.pk)
        neighbor_index = index - 1 if direction == "up" else index + 1
        if 0 <= neighbor_index < len(ordered_ids):
            ordered_ids[index], ordered_ids[neighbor_index] = ordered_ids[neighbor_index], ordered_ids[index]
            reorder_variants(product, ordered_ids)

    return _variant_list_redirect(request, product)


# --------------------------------------------------------- ویژگی‌ها (Attribute)


ATTRIBUTE_TYPE_FILTERS = [("", "همه‌ی انواع"), *Attribute.DataType.choices]
ATTRIBUTE_STATUS_FILTERS = [("", "همه"), ("active", "فعال"), ("archived", "غیرفعال")]


#: query-param value -> order_by fields, whitelisted like PRODUCT_SORT_OPTIONS
#: (never pass request.GET["sort"] straight into order_by()).
ATTRIBUTE_SORT_OPTIONS = {
    "": (["display_order", "label"], "ترتیبِ سفارشی"),
    "label": (["label"], "نام (الف تا ی)"),
    "-label": (["-label"], "نام (ی تا الف)"),
    "-created_at": (["-created_at"], "جدیدترین"),
    "created_at": (["created_at"], "قدیمی‌ترین"),
}


def _attributes_context(request, *, form=None, value_form=None):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    data_type = request.GET.get("data_type", "")
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "")

    qs = Attribute.objects.filter(store=store).select_related("category")
    if q:
        qs = qs.filter(Q(label__icontains=q) | Q(code__icontains=q))
    if data_type in dict(Attribute.DataType.choices):
        qs = qs.filter(data_type=data_type)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "archived":
        qs = qs.filter(is_active=False)

    order_fields, _label = ATTRIBUTE_SORT_OPTIONS.get(sort, ATTRIBUTE_SORT_OPTIONS[""])
    return {
        "attributes": qs.order_by(*order_fields),
        "q": q,
        "selected_data_type": data_type,
        "selected_status": status,
        "selected_sort": sort,
        "sort_options": ATTRIBUTE_SORT_OPTIONS,
        "type_options": ATTRIBUTE_TYPE_FILTERS,
        "status_options": ATTRIBUTE_STATUS_FILTERS,
        "form": form or AttributeForm(store=store),
        "value_form": value_form or AttributeValueForm(),
        "active_page": "attributes",
    }


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_list(request):
    return render(request, "dashboard/attributes.html", _attributes_context(request))


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_table(request):
    return render(request, "dashboard/partials/attributes_table.html", _attributes_context(request))


def _attributes_table_response(request, *, toast=None):
    response = render(request, "dashboard/partials/attributes_table.html", _attributes_context(request))
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


def _attribute_form_kwargs(form):
    return {
        "label": form.cleaned_data["label"], "code": form.cleaned_data["code"],
        "description": form.cleaned_data["description"],
        "data_type": form.cleaned_data["data_type"], "display_type": form.cleaned_data["display_type"],
        "unit": form.cleaned_data["unit"], "category": form.cleaned_data["category"],
        "is_required": form.cleaned_data["is_required"], "is_filterable": form.cleaned_data["is_filterable"],
        "is_searchable": form.cleaned_data["is_searchable"], "is_comparable": form.cleaned_data["is_comparable"],
        "is_variant_axis": form.cleaned_data["is_variant_axis"],
        "is_image_driving": form.cleaned_data["is_image_driving"],
    }


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_add(request):
    store = _resolve_dashboard_store(request)

    if request.method == "POST":
        form = AttributeForm(request.POST, store=store)
        if form.is_valid():
            try:
                create_attribute(store, **_attribute_form_kwargs(form))
            except AttributeError_ as exc:
                form.add_error(None, str(exc))
            else:
                response = _attributes_table_response(request, toast={"message": "ویژگی اضافه شد", "type": "ok"})
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "ویژگی اضافه شد", "type": "ok"}, "modal-close": {},
                })
                return response
    else:
        form = AttributeForm(store=store)

    return render(request, "dashboard/partials/attribute_form_modal.html", {"form": form, "attribute": None})


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_edit(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)

    if request.method == "POST":
        form = AttributeForm(request.POST, store=store)
        if form.is_valid():
            kwargs = _attribute_form_kwargs(form)
            kwargs["code"] = kwargs["code"] or attribute.code
            try:
                update_attribute(attribute, **kwargs)
            except AttributeError_ as exc:
                form.add_error(None, str(exc))
            else:
                response = _attributes_table_response(request, toast={"message": "ویژگی ویرایش شد", "type": "ok"})
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "ویژگی ویرایش شد", "type": "ok"}, "modal-close": {},
                })
                return response
    else:
        form = AttributeForm(store=store, initial={
            "label": attribute.label, "code": attribute.code, "description": attribute.description,
            "data_type": attribute.data_type, "display_type": attribute.display_type, "unit": attribute.unit,
            "category": attribute.category_id, "is_required": attribute.is_required,
            "is_filterable": attribute.is_filterable, "is_searchable": attribute.is_searchable,
            "is_comparable": attribute.is_comparable, "is_variant_axis": attribute.is_variant_axis,
            "is_image_driving": attribute.is_image_driving,
        })

    return render(request, "dashboard/partials/attribute_form_modal.html", {"form": form, "attribute": attribute})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_archive(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    archive_attribute(attribute)
    return _attributes_table_response(request, toast={"message": f"«{attribute.label}» غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_activate(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    activate_attribute(attribute)
    return _attributes_table_response(request, toast={"message": f"«{attribute.label}» فعال شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_delete(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    try:
        delete_attribute(attribute)
    except AttributeInUseError as exc:
        return _attributes_table_response(request, toast={"message": str(exc), "type": "err"})
    return _attributes_table_response(request, toast={"message": "ویژگی حذف شد", "type": "info"})


def _brands_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = Brand.objects.filter(store=store).annotate(product_count=Count("products"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    return {
        "brands": qs.order_by("sort_order", "name"),
        "q": q,
        "selected_status": status,
        "active_page": "brands",
    }


def _brands_table_response(request, *, toast=None):
    response = render(request, "dashboard/partials/brands_table.html", _brands_context(request))
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@staff_required
@permission_required(BRAND_MANAGE)
def brand_list(request):
    return render(request, "dashboard/brands.html", _brands_context(request))


@staff_required
@permission_required(BRAND_MANAGE)
def brand_table(request):
    return render(request, "dashboard/partials/brands_table.html", _brands_context(request))


@staff_required
@permission_required(BRAND_MANAGE)
def brand_add(request):
    store = _resolve_dashboard_store(request)

    if request.method == "POST":
        form = BrandForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                create_brand(
                    store, name=form.cleaned_data["name"], name_en=form.cleaned_data["name_en"],
                    description=form.cleaned_data["description"], website=form.cleaned_data["website"],
                    country=form.cleaned_data["country"], logo=form.cleaned_data.get("logo"),
                )
            except BrandError as exc:
                form.add_error(None, str(exc))
            else:
                return _brand_modal_success_response(request, message="برند اضافه شد")
    else:
        form = BrandForm()

    return render(request, "dashboard/partials/brand_form_modal.html", {"form": form, "brand": None})


def _brand_modal_success_response(request, *, message):
    """پاسخِ موفقیتِ فرمِ برند (داخلِ مودال) — فرم با ``hx-target="#admin-modal-content"``
    ارسال می‌شود، پس پاسخ باید جدولِ واقعیِ زیرِ مودال (``#brandsTableWrap``)
    را به‌صورتِ out-of-band به‌روزرسانی کند؛ وگرنه محتوایِ تازه فقط داخلِ
    مودالِ درحالِ بسته‌شدن رندر و هرگز دیده نمی‌شود (همان الگویِ
    ``product_form`` برایِ ``productsTableWrap``)."""
    table_html = render_to_string("dashboard/partials/brands_table.html", _brands_context(request), request=request)
    response = render(request, "dashboard/partials/oob_wrap.html", {
        "target_id": "brandsTableWrap", "inner_html": table_html,
    })
    response["HX-Trigger"] = json.dumps({"toast": {"message": message, "type": "ok"}, "modal-close": {}})
    return response


@staff_required
@permission_required(BRAND_MANAGE)
def brand_edit(request, pk):
    store = _resolve_dashboard_store(request)
    brand = get_object_or_404(Brand, pk=pk, store=store)

    if request.method == "POST":
        form = BrandForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                update_brand(
                    brand, name=form.cleaned_data["name"], name_en=form.cleaned_data["name_en"],
                    description=form.cleaned_data["description"], website=form.cleaned_data["website"],
                    country=form.cleaned_data["country"],
                    **({"logo": form.cleaned_data["logo"]} if form.cleaned_data.get("logo") else {}),
                )
            except BrandError as exc:
                form.add_error(None, str(exc))
            else:
                return _brand_modal_success_response(request, message="برند ویرایش شد")
    else:
        form = BrandForm(initial={
            "name": brand.name, "name_en": brand.name_en, "description": brand.description,
            "website": brand.website, "country": brand.country,
        })

    return render(request, "dashboard/partials/brand_form_modal.html", {"form": form, "brand": brand})


@require_POST
@staff_required
@permission_required(BRAND_MANAGE)
def brand_archive(request, pk):
    store = _resolve_dashboard_store(request)
    brand = get_object_or_404(Brand, pk=pk, store=store)
    archive_brand(brand)
    return _brands_table_response(request, toast={"message": f"«{brand.name}» غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(BRAND_MANAGE)
def brand_activate(request, pk):
    store = _resolve_dashboard_store(request)
    brand = get_object_or_404(Brand, pk=pk, store=store)
    activate_brand(brand)
    return _brands_table_response(request, toast={"message": f"«{brand.name}» فعال شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(BRAND_MANAGE)
def brand_delete(request, pk):
    store = _resolve_dashboard_store(request)
    brand = get_object_or_404(Brand, pk=pk, store=store)
    try:
        delete_brand(brand)
    except BrandInUseError as exc:
        return _brands_table_response(request, toast={"message": str(exc), "type": "err"})
    return _brands_table_response(request, toast={"message": "برند حذف شد", "type": "info"})


@require_POST
@staff_required
@permission_required(BRAND_MANAGE)
def brand_bulk_action(request):
    """عملیاتِ گروهی روی برندهای انتخاب‌شده — نگاه کنید به ``brand_bulk_ids``
    در قالب که با نامِ ``brand_ids`` تیک می‌خورند."""
    store = _resolve_dashboard_store(request)
    action = request.POST.get("action", "")
    ids = [int(pk) for pk in request.POST.getlist("brand_ids") if pk.strip().isdigit()]
    brands = list(Brand.objects.filter(store=store, pk__in=ids))

    if not brands:
        return _brands_table_response(request, toast={"message": "هیچ برندی انتخاب نشده است.", "type": "err"})

    if action == "activate":
        for brand in brands:
            activate_brand(brand)
        return _brands_table_response(request, toast={"message": f"{len(brands)} برند فعال شد", "type": "ok"})

    if action == "deactivate":
        for brand in brands:
            archive_brand(brand)
        return _brands_table_response(request, toast={"message": f"{len(brands)} برند غیرفعال شد", "type": "info"})

    if action == "delete":
        deleted, skipped = 0, 0
        for brand in brands:
            try:
                delete_brand(brand)
                deleted += 1
            except BrandInUseError:
                skipped += 1
        message = f"{deleted} برند حذف شد"
        if skipped:
            message += f"؛ {skipped} برند دارایِ کالا حذف نشد"
        return _brands_table_response(request, toast={"message": message, "type": "info" if skipped else "ok"})

    return _brands_table_response(request, toast={"message": "عملیاتِ ناشناخته.", "type": "err"})


@require_POST
@staff_required
@permission_required(BRAND_MANAGE)
def brand_reorder(request):
    """مرتب‌سازیِ کشاندنی (drag) — بدنه‌یِ درخواست فهرستِ ``brand_ids`` را به
    ترتیبِ تازه می‌فرستد؛ نگاه کنید به ``brand_service.reorder_brands``."""
    store = _resolve_dashboard_store(request)
    ordered_ids = [int(pk) for pk in request.POST.getlist("brand_ids") if pk.strip().isdigit()]
    try:
        reorder_brands(store, ordered_ids)
    except BrandReorderError as exc:
        return _brands_table_response(request, toast={"message": str(exc), "type": "err"})
    return _brands_table_response(request)


# ---------------------------------------------------------------------------
# کالکشن‌های دستیِ مرچنت (Merchant Manual Collections — فاز B)
# ---------------------------------------------------------------------------

def _collections_context(request, *, q=""):
    store = _resolve_dashboard_store(request)
    qs = MerchantCollection.objects.filter(store=store).annotate(product_count=Count("items"))
    q = (q or "").strip()
    if q:
        qs = qs.filter(name__icontains=q)
    return {"collections": qs.order_by("name"), "q": q, "public_collection_url_name": "catalog:collection-detail"}


def _collections_table_response(request, *, toast=None):
    response = render(request, "dashboard/partials/collections_table.html", _collections_context(request, q=request.GET.get("q", "")))
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_list(request):
    return render(request, "dashboard/collections.html", {
        "active_page": "collections", **_collections_context(request, q=request.GET.get("q", "")),
    })


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_table(request):
    return render(request, "dashboard/partials/collections_table.html", _collections_context(request, q=request.GET.get("q", "")))


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_add(request):
    store = _resolve_dashboard_store(request)

    if request.method == "POST":
        form = CollectionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                collection = collection_service.create_collection(
                    store, name=form.cleaned_data["name"], description=form.cleaned_data["description"],
                    image=form.cleaned_data.get("image"), seo_title=form.cleaned_data["seo_title"],
                    seo_description=form.cleaned_data["seo_description"], user=request.user,
                )
            except CollectionError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, f"کالکشن «{collection.name}» ساخته شد — حالا کالاها را اضافه کنید")
                return redirect("dashboard:collection-products", pk=collection.pk)
    else:
        form = CollectionForm()

    return render(request, "dashboard/collection_form.html", {
        "active_page": "collections", "form": form, "collection": None,
    })


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_edit(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        collection = collection_service.get_scoped_collection(store, pk)
    except CollectionNotFoundError:
        raise Http404

    if request.method == "POST":
        form = CollectionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                collection_service.update_collection(
                    collection, name=form.cleaned_data["name"], description=form.cleaned_data["description"],
                    seo_title=form.cleaned_data["seo_title"], seo_description=form.cleaned_data["seo_description"],
                    image=form.cleaned_data.get("image"),
                    remove_image=(request.POST.get("remove_image") == "1"), user=request.user,
                )
            except CollectionError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "کالکشن ویرایش شد")
                return redirect("dashboard:collection-list")
    else:
        form = CollectionForm(initial={
            "name": collection.name, "description": collection.description,
            "seo_title": collection.seo_title, "seo_description": collection.seo_description,
        })

    return render(request, "dashboard/collection_form.html", {
        "active_page": "collections", "form": form, "collection": collection,
    })


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_delete(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        collection = collection_service.get_scoped_collection(store, pk)
    except CollectionNotFoundError:
        raise Http404
    name = collection.name
    collection_service.delete_collection(collection)
    return _collections_table_response(request, toast={"message": f"کالکشن «{name}» حذف شد", "type": "info"})


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        collection = collection_service.get_scoped_collection(store, pk)
    except CollectionNotFoundError:
        raise Http404
    if collection.is_active:
        collection_service.deactivate_collection(collection)
        toast = {"message": f"«{collection.name}» غیرفعال شد", "type": "info"}
    else:
        collection_service.activate_collection(collection)
        toast = {"message": f"«{collection.name}» فعال شد", "type": "ok"}
    return _collections_table_response(request, toast=toast)


def _get_scoped_collection_or_404(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        return collection_service.get_scoped_collection(store, pk)
    except CollectionNotFoundError:
        raise Http404


def _collection_items_response(request, collection, *, toast=None):
    response = render(request, "dashboard/partials/collection_items_list.html", {
        "collection": collection,
        "items": collection.items.select_related("product").prefetch_related("product__images").order_by("order", "id"),
    })
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_products(request, pk):
    collection = _get_scoped_collection_or_404(request, pk)
    return render(request, "dashboard/collection_products.html", {
        "active_page": "collections", "collection": collection,
        "items": collection.items.select_related("product").prefetch_related("product__images").order_by("order", "id"),
    })


@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_products_search(request, pk):
    collection = _get_scoped_collection_or_404(request, pk)
    store = _resolve_dashboard_store(request)
    query = request.GET.get("q", "")
    existing_ids = set(collection.items.values_list("product_id", flat=True))
    results = collection_service.searchable_products(store, query=query)[:30]
    return render(request, "dashboard/partials/collection_product_search_results.html", {
        "collection": collection, "results": results, "existing_ids": existing_ids, "query": query,
    })


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_products_add(request, pk):
    collection = _get_scoped_collection_or_404(request, pk)
    store = _resolve_dashboard_store(request)
    product_ids = [int(pk_) for pk_ in request.POST.getlist("product_ids") if pk_.strip().isdigit()]
    # ``pk__in`` ترتیبِ فهرستِ ورودی را حفظ نمی‌کند (ترتیبِ نتیجه دستِ خودِ
    # دیتابیس است) — برای این‌که ترتیبِ انتخابِ مرچنت در چک‌باکس‌ها همان
    # ترتیبِ اولیه‌ی کالکشن بماند (قابلِ ویرایش دستی پس از افزودن، نه تصادفی)،
    # فهرست را دوباره طبقِ همان ترتیبِ پست‌شده می‌سازیم.
    products_by_id = {p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids)}
    products = [products_by_id[pid] for pid in product_ids if pid in products_by_id]
    created = collection_service.add_products(collection, products)
    if created:
        toast = {"message": f"{len(created)} کالا اضافه شد", "type": "ok"}
    else:
        toast = {"message": "کالایی برای افزودن انتخاب نشده یا همه از قبل عضو بودند", "type": "info"}
    return _collection_items_response(request, collection, toast=toast)


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_product_remove(request, pk, item_id):
    collection = _get_scoped_collection_or_404(request, pk)
    try:
        collection_service.remove_product(collection, item_id)
    except CollectionProductNotFoundError:
        raise Http404
    return _collection_items_response(request, collection, toast={"message": "کالا از کالکشن حذف شد", "type": "info"})


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_products_reorder(request, pk):
    collection = _get_scoped_collection_or_404(request, pk)
    item_ids = [int(pk_) for pk_ in request.POST.getlist("item_ids") if pk_.strip().isdigit()]
    try:
        collection_service.reorder_items(collection, item_ids)
    except CollectionReorderError as exc:
        return _collection_items_response(request, collection, toast={"message": str(exc), "type": "err"})
    return _collection_items_response(request, collection)


@require_POST
@staff_required
@permission_required(COLLECTION_MANAGE)
def collection_product_move(request, pk, item_id):
    collection = _get_scoped_collection_or_404(request, pk)
    direction = request.POST.get("direction")
    siblings = list(collection.items.order_by("order", "id"))
    index = next((i for i, item in enumerate(siblings) if item.pk == item_id), None)
    if index is not None:
        swap_index = index - 1 if direction == "up" else index + 1
        if 0 <= swap_index < len(siblings):
            ordered_ids = [item.pk for item in siblings]
            ordered_ids[index], ordered_ids[swap_index] = ordered_ids[swap_index], ordered_ids[index]
            collection_service.reorder_items(collection, ordered_ids)
    return _collection_items_response(request, collection)


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_values(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    return render(request, "dashboard/partials/attribute_values_modal.html", {
        "attribute": attribute, "value_form": AttributeValueForm(),
    })


def _attribute_values_response(request, attribute, *, toast=None):
    response = render(request, "dashboard/partials/attribute_values_list.html", {
        "attribute": attribute, "value_form": AttributeValueForm(),
    })
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_add(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    form = AttributeValueForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            create_attribute_value(
                attribute, label=form.cleaned_data["label"], value=form.cleaned_data["value"],
                color_hex=form.cleaned_data["color_hex"], swatch_image=form.cleaned_data.get("swatch_image"),
            )
        except AttributeError_ as exc:
            return render(request, "dashboard/partials/attribute_values_list.html", {
                "attribute": attribute, "value_form": form, "form_error": str(exc),
            })
        return _attribute_values_response(request, attribute, toast={"message": "مقدار اضافه شد", "type": "ok"})
    return render(request, "dashboard/partials/attribute_values_list.html", {
        "attribute": attribute, "value_form": form,
    })


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_reorder(request, pk):
    """مرتب‌سازیِ کشاندنی (drag) بینِ مقادیرِ یک ویژگی — نگاه کنید به
    ``attribute_service.reorder_attribute_values``."""
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    ordered_ids = [int(v) for v in request.POST.getlist("value_ids") if v.strip().isdigit()]
    reorder_attribute_values(attribute, ordered_ids)
    return render(request, "dashboard/partials/attribute_values_list.html", {
        "attribute": attribute, "value_form": AttributeValueForm(),
    })


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_archive(request, pk, value_id):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    value = get_object_or_404(AttributeValue, pk=value_id, attribute=attribute)
    archive_attribute_value(value)
    return _attribute_values_response(request, attribute, toast={"message": "مقدار غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_delete(request, pk, value_id):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    value = get_object_or_404(AttributeValue, pk=value_id, attribute=attribute)
    try:
        delete_attribute_value(value)
    except AttributeInUseError as exc:
        return _attribute_values_response(request, attribute, toast={"message": str(exc), "type": "err"})
    return _attribute_values_response(request, attribute, toast={"message": "مقدار حذف شد", "type": "info"})


# ------------------------------------------- محور/مقدار تنوع چندمحوره (Variant Engine)


def _product_options_context(request, product):
    axes = list(
        product.options.all().order_by("position").prefetch_related("values")
    )
    variants = list(
        product.variants.exclude(combination_key="").order_by("display_order")
        .prefetch_related("option_values__option", "option_values__option_value", "images")
    )
    prefetch_related_objects([product], "images")
    applied_attribute_ids = {axis.attribute_id for axis in axes if axis.attribute_id}
    recommended_options = []
    if product.category_id:
        recommended_options = list(
            CategoryRecommendedOption.objects.filter(category=product.category)
            .exclude(attribute_id__in=applied_attribute_ids)
            .select_related("attribute")
            .order_by("display_order")
        )
    # کتابخانه‌ی ویژگی‌هایِ فروشگاه (بخشِ ۲۸) — ویژگی‌هایِ محورِ تنوعِ قابلِ
    # بازاستفاده‌ای که قبلاً برایِ کالاهایِ دیگرِ همین فروشگاه ساخته شده‌اند و
    # هنوز به این کالا اضافه نشده‌اند. انتخابِ یکی، همان ویژگی + همه‌ی
    # مقادیرِ فعالش را یک‌کلیکی اضافه می‌کند (دقیقاً همان الگویِ محورهایِ
    # پیشنهادیِ دسته‌بندی) — مقادیرِ اضافه نیز از همان کارتِ ویژگی قابلِ حذف‌اند.
    library_attributes = list(
        Attribute.objects.filter(store=product.store, is_active=True, is_variant_axis=True)
        .exclude(pk__in=applied_attribute_ids)
        .prefetch_related("values")
        .order_by("label")
    )
    active_variants = [v for v in variants if not v.is_obsolete]
    active_prices = [v.price for v in active_variants if v.price]
    return {
        "product": product,
        "axes": axes,
        "variants": variants,
        "obsolete_variants": [v for v in variants if v.is_obsolete],
        "active_variants": active_variants,
        "variant_count": len(active_variants),
        "variant_total_stock": sum(v.stock for v in active_variants),
        "variant_price_min": min(active_prices) if active_prices else None,
        "variant_price_max": max(active_prices) if active_prices else None,
        "combination_preview": preview_combination_count(product),
        "has_legacy_variants": product.variants.filter(combination_key="").exists(),
        "recommended_options": recommended_options,
        "library_attributes": library_attributes,
        "option_form": ProductOptionForm(),
        "option_value_form": ProductOptionValueAddForm(),
        "tax_class_options": TaxClass.objects.filter(store=product.store, is_active=True).order_by("name"),
        "active_page": "products",
    }


def _product_options_response(request, product, *, toast=None, value_error=None):
    context = _product_options_context(request, product)
    if value_error:
        context["value_error"] = value_error
    response = render(request, "dashboard/partials/product_options_body.html", context)
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_set_type(request, pk):
    """AJAXِ سبکِ سوییچِ «کالای ساده / کالای دارای تنوع» — مستقل از خودِ
    ``ProductForm`` (که فقط با ذخیره‌ی کاملِ فرم اجرا می‌شود). بدونِ این
    اندپوینت، merchant می‌توانست تبِ «قیمت و تنوع» را رویِ «دارای تنوع»
    بگذارد و بلافاصله ویژگی/تنوع اضافه کند، اما تا اولین ذخیره‌ی کاملِ فرم
    ``product.product_type`` همچنان «ساده» می‌ماند و
    ``generate_variants``/``product-variants-generate`` با خطایِ «این کالا
    از نوع دارای تنوع نیست» رد می‌شد — دقیقاً سناریویِ بخشِ ۷ (گزارشِ
    ریشه‌ای). قواعدِ ایمنِ ``set_product_type`` (بلوکه‌کردنِ دارای‌تنوع→ساده
    وقتی تنوعی وجود دارد) بدونِ تغییر اعمال می‌شوند."""
    product = _get_scoped_product(request, pk)
    requested_type = request.POST.get("product_type", "")
    try:
        set_product_type(product, requested_type)
    except ProductTypeError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(request, product)


@staff_required
@permission_required(VARIANT_MANAGE)
def product_options(request, pk):
    product = _get_scoped_product(request, pk)
    return render(request, "dashboard/product_options.html", _product_options_context(request, product))


def _get_or_create_library_attribute(store, label, value_labels, color_pairs=None):
    """ویژگی را در کتابخانه‌ی فروشگاه پیدا یا می‌سازد (بخشِ ۲۸) — تطبیقِ نامِ
    غیرِحساس‌به‌حروف در همین Store؛ مقادیرِ داده‌شده که هنوز در کتابخانه نبودند
    اضافه می‌شوند (مقادیرِ موجود دست‌نخورده می‌مانند). هرگز چیزی از کتابخانه
    حذف نمی‌کند — حذفِ یک مقدار از یک کالا فقط همان کالا را تحتِ‌تأثیر
    قرار می‌دهد.

    ``color_pairs``: فهرستِ ``{"label": ..., "color_hex": ...}`` — نوعِ
    ویژگی (``data_type``) هرگز از کاربر پرسیده نمی‌شود، بلکه خودکار از
    رویِ وجودِ حداقل یک مقدارِ رنگ به COLOR تنظیم می‌شود (تشخیصِ خودکار،
    بدونِ فیلدِ «نوعِ ورودی» در UI)."""
    color_pairs = color_pairs or []
    attribute = Attribute.objects.filter(store=store, label__iexact=label).first()
    if attribute is None:
        attribute = create_attribute(
            store, label=label, is_variant_axis=True,
            data_type=Attribute.DataType.COLOR if color_pairs else Attribute.DataType.TEXT,
        )
    else:
        updates = {}
        if not attribute.is_variant_axis:
            updates["is_variant_axis"] = True
        if color_pairs and attribute.data_type != Attribute.DataType.COLOR:
            updates["data_type"] = Attribute.DataType.COLOR
        if updates:
            update_attribute(attribute, **updates)
    existing_labels = {v.label for v in attribute.values.all()}
    for value_label in value_labels:
        if value_label not in existing_labels:
            create_attribute_value(attribute, label=value_label)
            existing_labels.add(value_label)
    for pair in color_pairs:
        if pair["label"] not in existing_labels:
            create_attribute_value(attribute, label=pair["label"], color_hex=pair["color_hex"])
            existing_labels.add(pair["label"])
    return attribute


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_add(request, pk):
    product = _get_scoped_product(request, pk)
    form = ProductOptionForm(request.POST)
    if form.is_valid():
        raw_values = form.cleaned_data["raw_values"]
        values = parse_bulk_values(raw_values) if raw_values else []
        color_pairs = form.cleaned_data["color_values_json"]
        combined_values = values + [pair["label"] for pair in color_pairs]
        color_hex_by_label = {pair["label"]: pair["color_hex"] for pair in color_pairs}
        input_type = ProductOption.InputType.COLOR if color_pairs else ProductOption.InputType.TEXT
        try:
            attribute = _get_or_create_library_attribute(
                product.store, form.cleaned_data["label"], values, color_pairs=color_pairs,
            )
            add_product_option(
                product, label=attribute.label, attribute=attribute,
                values=combined_values, input_type=input_type, color_hex_by_label=color_hex_by_label,
            )
        except (VariantEngineError, AttributeError_) as exc:
            return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
        return _product_options_response(request, product, toast={"message": "محور تنوع اضافه شد", "type": "ok"})
    return _product_options_response(request, product, toast={"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_add_from_library(request, pk, attribute_id):
    """افزودنِ یک ویژگیِ قبلاً استفاده‌شده‌ی فروشگاه به این کالا — بخشِ ۲۸
    (کتابخانه‌ی ویژگیِ فروشگاه). دقیقاً همان الگویِ ``product_apply_
    recommended_option``: ویژگی + همه‌ی مقادیرِ فعالش یک‌کلیکی اضافه می‌شود؛
    مقادیرِ ناخواسته بعداً از همان کارتِ ویژگی حذف می‌شوند — هیچ ردیفِ
    Attribute/AttributeValueِ کتابخانه پاک نمی‌شود، فقط برایِ این کالا
    استفاده می‌شود."""
    product = _get_scoped_product(request, pk)
    attribute = get_object_or_404(Attribute, pk=attribute_id, store=product.store, is_active=True, is_variant_axis=True)
    values = [v.label for v in attribute.values.filter(is_active=True)]
    try:
        add_product_option(product, label=attribute.label, attribute=attribute, values=values)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(request, product, toast={"message": f"ویژگی «{attribute.label}» از کتابخانه اضافه شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_apply_recommended_option(request, pk, recommendation_id):
    """محور تنوع پیشنهادیِ دسته‌بندی را — فقط با تأیید صریح مدیر — به کالا اضافه می‌کند."""
    product = _get_scoped_product(request, pk)
    recommendation = get_object_or_404(
        CategoryRecommendedOption, pk=recommendation_id, category=product.category,
    )
    values = [v.label for v in recommendation.attribute.values.filter(is_active=True)]
    try:
        add_product_option(product, label=recommendation.attribute.label, attribute=recommendation.attribute, values=values)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(request, product, toast={
        "message": f"محور پیشنهادی «{recommendation.attribute.label}» اضافه شد", "type": "ok",
    })


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_deactivate(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    deactivate_product_option(option)
    return _product_options_response(request, product, toast={
        "message": f"محور «{option.label}» غیرفعال شد — برای اعمال، دوباره تولید کنید.", "type": "info",
    })


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_activate(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    activate_product_option(option)
    return _product_options_response(request, product, toast={"message": f"محور «{option.label}» فعال شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_options_reorder(request, pk):
    product = _get_scoped_product(request, pk)
    ordered_ids = [int(v) for v in request.POST.getlist("option_ids") if v.isdigit()]
    reorder_product_options(product, ordered_ids)
    return _product_options_response(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_move(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    direction = request.POST.get("direction", "")

    ordered_ids = list(product.options.order_by("position").values_list("pk", flat=True))
    if direction in ("up", "down") and option.pk in ordered_ids:
        index = ordered_ids.index(option.pk)
        neighbor_index = index - 1 if direction == "up" else index + 1
        if 0 <= neighbor_index < len(ordered_ids):
            ordered_ids[index], ordered_ids[neighbor_index] = ordered_ids[neighbor_index], ordered_ids[index]
            reorder_product_options(product, ordered_ids)

    return _product_options_response(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_value_add(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    # فیلدِ فرم عمداً ``v_<option_id>`` نام‌گذاری شده (نه ``label`` ساده): چون
    # این دکمه هنوز داخلِ ``<form id="productSaveForm">`` است، htmx مقادیرِ
    # همه‌ی ورودی‌هایِ آن فرم (و همه‌ی کارت‌هایِ ویژگیِ دیگر) را هم به‌صورتِ
    # خودکار می‌فرستد؛ اگر این ورودی نامِ مشترکِ ``label`` داشت، مقدارِ خالیِ
    # یک کارتِ دیگر می‌توانست جای مقدارِ واقعی را بگیرد (چون Django برایِ
    # کلیدهایِ تکراری آخرین مقدار را برمی‌دارد). نامِ یکتا + ``hx-params``
    # در قالب، این اثرِ جانبی را کاملاً حذف می‌کند.
    data = request.POST.copy()
    data["label"] = request.POST.get(f"v_{option_id}", "")
    form = ProductOptionValueAddForm(data)
    if form.is_valid():
        label = form.cleaned_data["label"]
        try:
            attribute_value = None
            if option.attribute_id is not None:
                # مقدارِ تازه هم باید کتابخانه‌ی فروشگاه را به‌روز کند (بخشِ
                # ۲۸: «افزودنِ مقدارِ تازه، کتابخانه را به‌روز می‌کند»).
                attribute_value = option.attribute.values.filter(label=label).first()
                if attribute_value is None:
                    attribute_value = create_attribute_value(option.attribute, label=label)
            add_option_value(option, label, color_hex=form.cleaned_data["color_hex"], attribute_value=attribute_value)
        except (VariantEngineError, AttributeError_) as exc:
            return _product_options_response(request, product, value_error={"axis_id": option.pk, "message": str(exc)})
        return _product_options_response(request, product, toast={"message": "مقدار اضافه شد", "type": "ok"})
    message = "؛ ".join(form.errors.get("label", [])) or "لطفاً خطاهای فرم را برطرف کنید"
    return _product_options_response(request, product, value_error={"axis_id": option.pk, "message": message})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_value_remove(request, pk, value_id):
    product = _get_scoped_product(request, pk)
    value = get_object_or_404(ProductOptionValue, pk=value_id, option__product=product)
    label = value.label
    remove_option_value(value)
    return _product_options_response(request, product, toast={"message": f"مقدار «{label}» حذف/غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_generate(request, pk):
    product = _get_scoped_product(request, pk)
    try:
        result = generate_variants(product)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})

    parts = []
    if result.created:
        parts.append(f"{len(result.created)} تنوع جدید ساخته شد")
    if result.obsoleted:
        parts.append(f"{len(result.obsoleted)} ترکیب منسوخ شد")
    if not parts:
        parts.append("همه‌ی ترکیب‌ها از قبل موجود بودند")
    message = "، ".join(parts) + f" — {len(result.preserved) + len(result.created)} تنوع فعال"
    return _product_options_response(request, product, toast={"message": message, "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_manual_add(request, pk):
    """«+ اضافه کردنِ تنوعِ محصول» — یک ردیفِ جدولِ تنوع را دستی (با انتخابِ
    یک مقدار برایِ هر محورِ فعال) اضافه می‌کند؛ نگاه کنید به
    ``variant_engine_service.add_manual_variant``. برایِ ساختِ همه‌ی
    ترکیب‌های ممکن یک‌جا، دکمه‌ی «تولید/تطبیقِ تنوع‌ها» همچنان در دسترس است."""
    product = _get_scoped_product(request, pk)
    axes = list(product.options.filter(is_active=True))
    option_value_ids = {}
    for axis in axes:
        raw = request.POST.get(f"option_{axis.pk}", "").strip()
        if raw.isdigit():
            option_value_ids[axis.pk] = int(raw)
    try:
        variant = add_manual_variant(product, option_value_ids)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(
        request, product, toast={"message": f"تنوعِ «{variant.value}» اضافه شد", "type": "ok"},
    )


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_set_default(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    try:
        set_default_variant(product, variant)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(request, product, toast={"message": "تنوع پیش‌فرض تغییر کرد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_set_price(request, pk, variant_id):
    """مودالِ «تنظیمِ قیمت» یک ردیفِ تنوع — قیمت و تخفیف٪ می‌گیرد و قیمتِ
    نهایی را محاسبه می‌کند؛ دقیقاً همان قراردادِ Product.price/discount_percent
    را رویِ فیلدهایِ موجودِ ProductVariant پیاده می‌کند (بدونِ فیلدِ جدید):
    با تخفیف، ``price`` = قیمتِ نهایی و ``compare_at_price`` = قیمتِ خط‌خورده؛
    بدونِ تخفیف، ``price`` = همان مقدار و ``compare_at_price`` پاک می‌شود."""
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    raw_price = normalize_digits(request.POST.get("variant_price", "")).strip()
    raw_discount = normalize_digits(request.POST.get("variant_discount_percent", "")).strip() or "0"
    try:
        price = Decimal(raw_price)
        discount = Decimal(raw_discount)
        if price <= 0:
            raise ValueError
        if discount < 0 or discount > 100:
            raise ValueError
    except (InvalidOperation, ValueError):
        return _product_options_response(
            request, product, toast={"message": "قیمت یا درصدِ تخفیف نامعتبر است.", "type": "err"},
        )

    if discount > 0:
        final_price = (price * (Decimal(100) - discount) / Decimal(100)).quantize(Decimal("1"))
        variant.price = final_price
        variant.compare_at_price = price
    else:
        variant.price = price.quantize(Decimal("1"))
        variant.compare_at_price = None
    variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    variant.save(update_fields=["price", "compare_at_price", "updated_at"])
    return _product_options_response(request, product, toast={"message": "قیمتِ تنوع ذخیره شد", "type": "ok"})


def _parse_sales_limit_bound(raw: str):
    raw = normalize_digits(raw).strip()
    if not raw:
        return None, None
    try:
        value = int(raw)
    except ValueError:
        return None, "مقدارِ محدودیتِ فروش باید یک عددِ صحیح باشد."
    if value < 0:
        return None, "مقدارِ محدودیتِ فروش نمی‌تواند منفی باشد."
    return value, None


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_set_sales_limit(request, pk, variant_id):
    """مودالِ «تنظیمِ محدودیتِ فروش» یک تنوع (بخشِ ۱۴) — حداقل/حداکثرِ تعدادِ
    قابلِ‌خرید در هر سفارش؛ هر دو خالی یعنی نامحدود."""
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    min_value, min_error = _parse_sales_limit_bound(request.POST.get("sales_limit_min", ""))
    max_value, max_error = _parse_sales_limit_bound(request.POST.get("sales_limit_max", ""))
    if min_error or max_error:
        return _product_options_response(request, product, toast={"message": min_error or max_error, "type": "err"})
    if min_value is not None and max_value is not None and min_value > max_value:
        return _product_options_response(
            request, product, toast={"message": "حداقلِ محدودیتِ فروش نمی‌تواند بیشتر از حداکثر باشد.", "type": "err"},
        )

    variant.sales_limit_min = min_value
    variant.sales_limit = max_value
    variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    variant.save(update_fields=["sales_limit_min", "sales_limit", "updated_at"])
    return _product_options_response(request, product, toast={"message": "محدودیتِ فروش ذخیره شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_sales_limit(request, pk):
    """اعمالِ گروهیِ محدودیتِ فروش رویِ تنوع‌هایِ انتخاب‌شده."""
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("variant_ids") if v.isdigit()]
    if not variant_ids:
        return _product_options_response(request, product, toast={"message": "هیچ تنوعی انتخاب نشده است.", "type": "err"})

    min_value, min_error = _parse_sales_limit_bound(request.POST.get("sales_limit_min", ""))
    max_value, max_error = _parse_sales_limit_bound(request.POST.get("sales_limit_max", ""))
    if min_error or max_error:
        return _product_options_response(request, product, toast={"message": min_error or max_error, "type": "err"})
    if min_value is not None and max_value is not None and min_value > max_value:
        return _product_options_response(
            request, product, toast={"message": "حداقلِ محدودیتِ فروش نمی‌تواند بیشتر از حداکثر باشد.", "type": "err"},
        )

    variants = product.variants.filter(pk__in=variant_ids)
    updated = variants.update(sales_limit_min=min_value, sales_limit=max_value)
    return _product_options_response(
        request, product, toast={"message": f"محدودیتِ فروش برایِ {updated} تنوع اعمال شد", "type": "ok"},
    )


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_stock(request, pk):
    """اعمالِ گروهیِ موجودی رویِ تنوع‌هایِ انتخاب‌شده — بدونِ نیاز به کلیکِ
    جداگانه‌ی «ذخیره‌ی تغییرات»؛ درست مثلِ الگویِ ``product_variants_bulk_sales_limit``،
    بلافاصله در دیتابیس اعمال می‌شود."""
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("variant_ids") if v.isdigit()]
    if not variant_ids:
        return _product_options_response(request, product, toast={"message": "هیچ تنوعی انتخاب نشده است.", "type": "err"})

    raw_stock = normalize_digits(request.POST.get("stock", "")).strip()
    if not raw_stock:
        return _product_options_response(request, product, toast={"message": "موجودیِ جدید را وارد کنید.", "type": "err"})
    try:
        stock = int(raw_stock)
    except ValueError:
        return _product_options_response(request, product, toast={"message": "موجودی باید یک عدد صحیح باشد.", "type": "err"})
    if stock < 0:
        return _product_options_response(request, product, toast={"message": "موجودی نمی‌تواند منفی باشد.", "type": "err"})

    variants = product.variants.filter(pk__in=variant_ids)
    updated = variants.update(stock=stock)
    return _product_options_response(
        request, product, toast={"message": f"موجودیِ {updated} تنوع به‌روزرسانی شد", "type": "ok"},
    )


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_update(request, pk):
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("variant_ids") if v.isdigit()]
    variants = {v.pk: v for v in product.variants.filter(pk__in=variant_ids)}

    updated = []
    errors = []
    for variant_id in variant_ids:
        variant = variants.get(variant_id)
        if variant is None:
            continue
        prefix = f"variant_{variant_id}_"
        try:
            sku = request.POST.get(f"{prefix}sku", "").strip()
            if sku and sku != variant.sku:
                if ProductVariant.objects.filter(store=product.store, sku=sku).exclude(pk=variant.pk).exists():
                    raise VariantError(f"کد کالای «{sku}» قبلاً برای یک تنوع دیگر استفاده شده است.")
                variant.sku = sku
            variant.barcode = request.POST.get(f"{prefix}barcode", "").strip()
            variant.stock = int(normalize_digits(request.POST.get(f"{prefix}stock", "0")) or 0)
            variant.extra_price = Decimal(normalize_digits(request.POST.get(f"{prefix}extra_price", "0")) or 0)
            # قیمت/قیمتِ مقایسه‌ای دیگر اینجا دست نمی‌خورَند — این‌ها منحصراً از
            # طریقِ مودالِ «تنظیمِ قیمت» (نگاه کنید به ``product_variant_set_price``)
            # مدیریت می‌شوند تا با یک بارگذاریِ گروهیِ ناقص پاک نشوند.
            cost_raw = normalize_digits(request.POST.get(f"{prefix}cost", "")).strip()
            variant.cost = Decimal(cost_raw) if cost_raw else None
            weight_raw = normalize_digits(request.POST.get(f"{prefix}weight_grams", "")).strip()
            variant.weight_grams = int(weight_raw) if weight_raw else None
            # محدودیتِ فروش (حداقل/حداکثر) دیگر اینجا دست نمی‌خورَد — منحصراً از
            # طریقِ مودالِ «تنظیمِ محدودیتِ فروش» (نگاه کنید به
            # ``product_variant_set_sales_limit``) مدیریت می‌شود، دقیقاً همان
            # دلیلِ استثنایِ قیمت بالاتر.
            tax_class_raw = request.POST.get(f"{prefix}tax_class", "").strip()
            if tax_class_raw:
                tax_class = TaxClass.objects.filter(pk=tax_class_raw, store=product.store).first()
                if tax_class is None:
                    raise VariantError("دسته‌ی مالیاتیِ انتخاب‌شده معتبر نیست.")
                variant.tax_class = tax_class
            else:
                variant.tax_class = None
            # وضعیتِ فعال/غیرفعال دیگر اینجا دست نمی‌خورَد — منحصراً از طریقِ
            # دکمه‌هایِ «فعال‌سازیِ انتخاب‌شده‌ها»/«غیرفعال‌سازیِ انتخاب‌شده‌ها»
            # (نگاه کنید به ``product_variants_bulk_activate``) با تأییدِ صریحِ
            # کاربر مدیریت می‌شود تا با یک بارگذاریِ گروهیِ ناقص خاموش نشود.
            if variant.stock < 0:
                raise VariantError("موجودی نمی‌تواند منفی باشد.")
            variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
        except (VariantError, ValidationError, InvalidOperation, ValueError) as exc:
            message = "؛ ".join(sum(exc.message_dict.values(), [])) if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"{variant.value}: {message}")
            continue
        updated.append(variant)

    if errors:
        return _product_options_response(request, product, toast={"message": errors[0], "type": "err"})

    with transaction.atomic():
        for variant in updated:
            variant.save()

    return _product_options_response(
        request, product, toast={"message": f"{len(updated)} تنوع به‌روزرسانی شد", "type": "ok"},
    )


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_delete(request, pk):
    """حذفِ فله‌ای از جدولِ تنوع‌های موتورِ چندمحوره — دقیقاً همان قاعده‌ی
    ``variant_service.delete_variant`` (تنوعِ استفاده‌شده در سفارش حذف
    نمی‌شود، فقط رد می‌شود) برای هر ردیفِ انتخاب‌شده اجرا می‌شود."""
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("delete_variant_ids") if v.isdigit()]
    if not variant_ids:
        return _product_options_response(request, product, toast={"message": "هیچ تنوعی انتخاب نشده است.", "type": "err"})
    variants = product.variants.filter(pk__in=variant_ids)

    deleted_count = 0
    skipped_count = 0
    with transaction.atomic():
        for variant in list(variants):
            try:
                delete_variant(variant)
                deleted_count += 1
            except VariantError:
                skipped_count += 1

    if skipped_count:
        message = f"{deleted_count} تنوع حذف شد — {skipped_count} تنوع چون در سفارشی استفاده شده، حذف نشد."
        toast_type = "info" if deleted_count else "err"
    else:
        message = f"{deleted_count} تنوع حذف شد"
        toast_type = "ok" if deleted_count else "err"
    return _product_options_response(request, product, toast={"message": message, "type": toast_type})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_activate(request, pk):
    """فعال/غیرفعال‌سازیِ گروهیِ ردیف‌هایِ انتخاب‌شده‌ی جدولِ تنوع — Part 6 مشخصات."""
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("variant_ids") if v.isdigit()]
    if not variant_ids:
        return _product_options_response(request, product, toast={"message": "هیچ تنوعی انتخاب نشده است.", "type": "err"})
    is_active = request.POST.get("activate") == "1"
    with transaction.atomic():
        updated = product.variants.filter(pk__in=variant_ids).update(is_active=is_active)
    label = "فعال" if is_active else "غیرفعال"
    return _product_options_response(
        request, product, toast={"message": f"{updated} تنوع {label} شد", "type": "ok"},
    )


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_matrix_duplicate(request, pk, variant_id):
    """تکرارِ یک ردیفِ جدولِ تنوعِ چندمحوره — بدونِ ترکِ صفحه (برخلافِ
    ``product_variant_duplicate`` که برایِ صفحه‌ی قدیمیِ تک‌محوره است)."""
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    try:
        duplicate_variant(variant)
    except VariantError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(
        request, product, toast={"message": f"یک کپیِ غیرفعال از «{variant.value}» ساخته شد", "type": "ok"},
    )


# --------------------------------------------------------- دسته‌بندی‌ها


def _categories_context(request, *, main_form=None, sub_form=None, subsub_form=None):
    store = _resolve_dashboard_store(request)
    context = category_tree_context(store)
    context["main_form"] = main_form or MainCategoryForm()
    context["sub_form"] = sub_form or SubCategoryForm(store=store)
    context["subsub_form"] = subsub_form or SubSubCategoryForm(store=store)
    return context


@staff_required
@permission_required(CATEGORY_MANAGE)
def category_list(request):
    context = _categories_context(request)
    context["active_page"] = "categories"
    return render(request, "dashboard/categories.html", context)


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_add_main(request):
    store = _resolve_dashboard_store(request)
    form = MainCategoryForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            store=store, name=name, icon=form.cleaned_data["icon"] or "📁",
            slug=generate_unique_slug(Category, name, store=store),
        )
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": f"گروه «{name}» اضافه شد", "type": "ok"}})
        return response
    response = render(
        request, "dashboard/partials/categories_body.html", _categories_context(request, main_form=form)
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_add_sub(request):
    store = _resolve_dashboard_store(request)
    form = SubCategoryForm(request.POST, store=store)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            store=store, name=name, icon=form.cleaned_data["icon"], parent=form.cleaned_data["parent"],
            slug=generate_unique_slug(Category, name, store=store),
        )
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": f"زیرگروه «{name}» اضافه شد", "type": "ok"}})
        return response
    response = render(
        request, "dashboard/partials/categories_body.html", _categories_context(request, sub_form=form)
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_add_subsub(request):
    """سومین سطح (زیردسته) — والدش باید خودش یک «دسته» (سطحِ دوم) باشد؛
    نگاه کنید به ``SubSubCategoryForm``."""
    store = _resolve_dashboard_store(request)
    form = SubSubCategoryForm(request.POST, store=store)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            store=store, name=name, icon=form.cleaned_data["icon"], parent=form.cleaned_data["parent"],
            slug=generate_unique_slug(Category, name, store=store),
        )
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": f"زیردسته‌ی «{name}» اضافه شد", "type": "ok"}})
        return response
    response = render(
        request, "dashboard/partials/categories_body.html", _categories_context(request, subsub_form=form)
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_reorder(request):
    """مرتب‌سازیِ کشاندنی (drag) بینِ خواهر-و-برادرهای یک والدِ مشترک — نگاه
    کنید به ``catalog_admin_service.reorder_categories``."""
    store = _resolve_dashboard_store(request)
    ordered_ids = [int(pk) for pk in request.POST.getlist("category_ids") if pk.strip().isdigit()]
    reorder_categories(store, ordered_ids)
    response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
    return response


@staff_required
@permission_required(CATEGORY_MANAGE)
def category_edit(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)

    if request.method == "POST":
        form = CategoryEditForm(request.POST)
        if form.is_valid():
            category.name = form.cleaned_data["name"]
            category.icon = form.cleaned_data["icon"]
            category.save(update_fields=["name", "icon", "updated_at"])
            context = _categories_context(request)
            context["oob"] = True
            response = render(request, "dashboard/partials/categories_body.html", context)
            response["HX-Trigger"] = json.dumps({
                "toast": {"message": "دسته‌بندی ویرایش شد", "type": "ok"}, "modal-close": {},
            })
            return response
    else:
        form = CategoryEditForm(initial={"name": category.name, "icon": category.icon})

    return render(request, "dashboard/partials/category_edit_form.html", {"form": form, "category": category})


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_delete(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    try:
        can_delete_category(category)
    except CategoryDeleteError as exc:
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": str(exc), "type": "err"}})
        return response

    name = category.name
    try:
        category.delete()
    except ProtectedError:
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({
            "toast": {"message": f"دسته‌ی «{name}» دارای کالا است و قابل حذف نیست.", "type": "err"},
        })
        return response
    response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"«{name}» حذف شد", "type": "info"}})
    return response


# ------------------------------------------------- طرح ویژگیِ دسته‌بندی (Category Attribute Schema)


def _category_schema_context(request, category, *, form=None):
    store = _resolve_dashboard_store(request)
    return {
        "category": category,
        "resolved_schema": resolve_category_schema(category),
        "direct_entries": category.attribute_schema_entries.select_related("attribute").order_by(
            "group_order", "display_order",
        ),
        "form": form or CategoryAttributeAddForm(store=store),
    }


@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    return render(
        request, "dashboard/partials/category_schema_modal.html", _category_schema_context(request, category),
    )


def _category_schema_response(request, category, *, toast=None):
    response = render(
        request, "dashboard/partials/category_schema_list.html", _category_schema_context(request, category),
    )
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_add(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    form = CategoryAttributeAddForm(request.POST, store=store)
    if form.is_valid():
        try:
            add_category_attribute(
                category, form.cleaned_data["attribute"], group=form.cleaned_data["group"],
                is_required=form.cleaned_data["is_required"],
                is_inherited_by_children=form.cleaned_data["is_inherited_by_children"],
                help_text=form.cleaned_data["help_text"], placeholder=form.cleaned_data["placeholder"],
            )
        except CategorySchemaError as exc:
            return _category_schema_response(request, category, toast={"message": str(exc), "type": "err"})
        return _category_schema_response(request, category, toast={"message": "ویژگی اضافه شد", "type": "ok"})
    return render(request, "dashboard/partials/category_schema_list.html", {
        **_category_schema_context(request, category, form=form),
    })


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_toggle_required(request, pk, entry_id):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    entry = get_object_or_404(CategoryAttributeSchema, pk=entry_id, category=category)
    update_category_attribute(entry, is_required=not entry.is_required)
    return _category_schema_response(request, category)


_OVERRIDE_FIELDS = {"filterable": "is_filterable_override", "comparable": "is_comparable_override",
                    "searchable": "is_searchable_override"}


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_toggle_override(request, pk, entry_id):
    """چرخش سه‌حالته‌ی بازنویسی (ارث‌بری از Attribute → فعال → غیرفعال → ارث‌بری) — نگاه کنید به بخش ۳۱ پرامپت فاز ۱F."""
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    entry = get_object_or_404(CategoryAttributeSchema, pk=entry_id, category=category)
    field = request.POST.get("field", "")
    model_field = _OVERRIDE_FIELDS.get(field)
    if model_field is None:
        return _category_schema_response(request, category, toast={"message": "فیلد نامعتبر است.", "type": "err"})

    current = getattr(entry, model_field)
    next_value = {None: True, True: False, False: None}[current]
    update_category_attribute(entry, **{model_field: next_value})
    return _category_schema_response(request, category)


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_toggle_visibility(request, pk, entry_id):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    entry = get_object_or_404(CategoryAttributeSchema, pk=entry_id, category=category)
    update_category_attribute(entry, is_visible_on_storefront=not entry.is_visible_on_storefront)
    return _category_schema_response(request, category)


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_remove(request, pk, entry_id):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    entry = get_object_or_404(CategoryAttributeSchema, pk=entry_id, category=category)
    label = entry.attribute.label
    remove_category_attribute(entry)
    return _category_schema_response(request, category, toast={"message": f"«{label}» حذف شد", "type": "info"})


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_schema_move(request, pk, entry_id):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    entry = get_object_or_404(CategoryAttributeSchema, pk=entry_id, category=category)
    direction = request.POST.get("direction", "")

    ordered_ids = list(
        category.attribute_schema_entries.order_by("group_order", "display_order").values_list("pk", flat=True)
    )
    if direction in ("up", "down") and entry.pk in ordered_ids:
        index = ordered_ids.index(entry.pk)
        neighbor_index = index - 1 if direction == "up" else index + 1
        if 0 <= neighbor_index < len(ordered_ids):
            ordered_ids[index], ordered_ids[neighbor_index] = ordered_ids[neighbor_index], ordered_ids[index]
            reorder_category_attributes(category, ordered_ids)

    return _category_schema_response(request, category)


# --------------------------------------------------------------- سفارش‌ها


def _order_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    return {
        "orders": filtered_orders(store=store, q=q, status=status),
        "q": q,
        "selected_status": status,
        "status_filters": ORDER_STATUS_FILTERS,
        "status_counts": order_status_counts(store=store),
    }


@staff_required
@permission_required(ORDER_VIEW)
def order_list(request):
    context = _order_list_context(request)
    context["active_page"] = "orders"
    return render(request, "dashboard/orders.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def order_table(request):
    return render(request, "dashboard/partials/orders_table_inner.html", _order_list_context(request))


@staff_required
@permission_required(ORDER_VIEW)
def order_detail(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(
        Order.objects.select_related("customer", "vendor", "shipping_method"), code=code, store=store
    )

    if request.method == "POST":
        if not membership_has_permission(request.store_membership, ORDER_STATUS_CHANGE):
            return render(request, "dashboard/403.html", status=403)
        to_status = request.POST.get("status", "")
        tracking_code = request.POST.get("tracking_code", "").strip()
        try:
            change_order_status(
                order, to_status, by=request.user, tracking_code=tracking_code, store=store,
            )
            messages.success(request, f"وضعیت سفارش {order.code} به‌روزرسانی شد")
            return redirect("dashboard:order-detail", code=order.code)
        except ValueError as exc:
            context = _order_detail_context(order)
            context["active_page"] = "orders"
            context["error"] = str(exc)
            return render(request, "dashboard/order_detail.html", context)

    context = _order_detail_context(order)
    context["active_page"] = "orders"
    context["can_manage_refunds"] = membership_has_permission(request.store_membership, REFUND_MANAGE)
    context["can_manage_returns"] = membership_has_permission(request.store_membership, RETURN_MANAGE)
    return render(request, "dashboard/order_detail.html", context)


def _order_detail_context(order):
    return {
        "order": order,
        "items": order.items.select_related("product", "variant"),
        "status_history": order.status_history.select_related("changed_by"),
        "next_status_options": next_status_options(order),
        "is_final": order_is_final(order),
        "status_steps": order_status_steps(order),
        "paid_amount": paid_amount(order),
        "refunded_amount": refunded_total(order),
        "refundable_amount": refundable_amount(order),
        "refunds": order.refunds.select_related("actor").order_by("-created_at"),
        "return_requests": order.return_requests.order_by("-created_at"),
    }


# ---------------------------------------------------------------- فاکتورها


def _invoice_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    orders_qs = filtered_invoices(store=store, q=q, status=status)
    count, total = invoice_totals(orders_qs)
    return {
        "orders": orders_qs,
        "q": q,
        "selected_status": status,
        "status_filters": INVOICE_STATUS_FILTERS,
        "invoice_count": count,
        "invoice_total": total,
    }


@staff_required
@permission_required(ORDER_VIEW)
def invoice_list(request):
    context = _invoice_list_context(request)
    context["active_page"] = "invoices"
    return render(request, "dashboard/invoices.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def invoice_table(request):
    return render(request, "dashboard/partials/invoices_table_inner.html", _invoice_list_context(request))


@staff_required
@permission_required(ORDER_VIEW)
def invoice_detail(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(Order.objects.select_related("customer"), code=code, store=store)
    context = {
        "order": order,
        "items": order.items.select_related("product"),
        "active_page": "invoices",
    }
    return render(request, "dashboard/invoice_detail.html", context)


# ---------------------------------------------------------------- پرداخت‌ها


def _payment_list_context(request):
    store = _resolve_dashboard_store(request)
    status = request.GET.get("status", "")
    return {
        "transactions": filtered_transactions(store=store, status=status),
        "selected_status": status,
        "status_filters": TRANSACTION_STATUS_FILTERS,
    }


@staff_required
@permission_required(ORDER_VIEW)
def payment_list(request):
    context = _payment_list_context(request)
    context["active_page"] = "payments"
    return render(request, "dashboard/payments.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def payment_table(request):
    return render(request, "dashboard/partials/payments_table_inner.html", _payment_list_context(request))


# ---------------------------------------------------------------- مشتریان


def _customer_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    return {
        "customers": customers_admin_service.annotated_customers(store=store, q=q), "q": q,
        "bulk_tag_options": CustomerTag.objects.filter(store=store, is_active=True).order_by("name"),
        "bulk_status_options": CustomerProfile.InternalStatus.choices,
        "can_manage_tags": membership_has_permission(request.store_membership, CUSTOMER_TAG_MANAGE),
        "can_manage_notes": membership_has_permission(request.store_membership, CUSTOMER_NOTE_MANAGE),
        "can_export_customers": membership_has_permission(request.store_membership, CUSTOMER_EXPORT),
    }


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_list(request):
    context = _customer_list_context(request)
    context["active_page"] = "customers"
    return render(request, "dashboard/customers.html", context)


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_table(request):
    return render(request, "dashboard/partials/customers_table_inner.html", _customer_list_context(request))


def _selected_customer_ids(request):
    ids = []
    for raw in request.POST.getlist("customer_ids"):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


@require_POST
@staff_required
def customer_bulk_action(request):
    """اکشنِ فله‌ای روی مشتری‌های انتخاب‌شده — شناسه‌های مشتریِ فروشگاهِ دیگر
    (یا مشتریِ بدونِ هیچ Orderی در این Store) در همه‌ی توابعِ
    ``customer_crm_service`` بی‌صدا نادیده گرفته می‌شوند، دقیقاً همان قاعده‌ی
    ``product_bulk_action``."""
    store = _resolve_dashboard_store(request)
    action = request.POST.get("bulk_action", "")
    customer_ids = _selected_customer_ids(request)

    required_permission = CUSTOMER_TAG_MANAGE if action in ("add-tag", "remove-tag") else CUSTOMER_NOTE_MANAGE
    if action == "export-selected":
        required_permission = CUSTOMER_EXPORT
    if not membership_has_permission(request.store_membership, required_permission):
        return render(request, "dashboard/403.html", status=403)

    if not customer_ids:
        messages.warning(request, "هیچ مشتری‌ای انتخاب نشده است")
        return redirect("dashboard:customer-list")

    try:
        if action == "add-tag":
            tag_id = request.POST.get("bulk_tag", "")
            count = customer_crm_service.bulk_add_tag(store, customer_ids, tag_id, actor=request.user)
            messages.success(request, f"برچسب برای {count} مشتری اضافه شد")
        elif action == "remove-tag":
            tag_id = request.POST.get("bulk_tag", "")
            count = customer_crm_service.bulk_remove_tag(store, customer_ids, tag_id, actor=request.user)
            messages.success(request, f"برچسب از {count} مشتری حذف شد")
        elif action == "set-status":
            status = request.POST.get("bulk_status", "")
            count = customer_crm_service.set_internal_status(store, customer_ids, status, actor=request.user)
            messages.success(request, f"وضعیتِ داخلیِ {count} مشتری به‌روزرسانی شد")
        elif action == "export-selected":
            run_export(
                store, ExportJob.ExportType.CUSTOMERS, requested_by=request.user,
                filters={"customer_ids": customer_ids},
            )
            messages.success(request, "صادراتِ مشتریانِ انتخاب‌شده ساخته شد")
            return redirect("dashboard:export-list")
        else:
            messages.error(request, "اکشن فله‌ای نامعتبر است")
    except customer_crm_service.CustomerCrmError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:customer-list")


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_detail(request, pk):
    """مشتری فقط اگر حداقل یک Order در همین Store داشته باشد قابل‌دسترسی
    است — Customer فیلد store ندارد (تصمیم عمدی، نگاه کنید به
    customers_admin_service)، پس مرز دسترسی از طریق رابطه‌ی Order اعمال
    می‌شود، نه یک فیلد مستقیم روی Customer."""
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    orders = customers_admin_service.customer_orders(customer, store=store)
    profile = customer_crm_service.get_or_create_profile(store, customer)
    context = {
        "customer": customer,
        "orders": orders,
        "paid_total": customers_admin_service.customer_paid_total(orders),
        "active_page": "customers",
        "profile": profile,
        "notes": profile.notes.select_related("author").all(),
        "all_tags": CustomerTag.objects.filter(store=store, is_active=True).order_by("name"),
        "assigned_tag_ids": set(profile.tags.values_list("pk", flat=True)),
        "internal_status_choices": CustomerProfile.InternalStatus.choices,
        "can_manage_notes": membership_has_permission(request.store_membership, CUSTOMER_NOTE_MANAGE),
        "can_manage_tags": membership_has_permission(request.store_membership, CUSTOMER_TAG_MANAGE),
    }
    return render(request, "dashboard/customer_detail.html", context)


@require_POST
@staff_required
@permission_required(CUSTOMER_NOTE_MANAGE)
def customer_refresh_stats(request, pk):
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    profile = customer_crm_service.get_or_create_profile(store, customer)
    customer_crm_service.refresh_customer_profile_stats(profile)
    messages.success(request, "آمارِ مشتری به‌روزرسانی شد")
    return redirect("dashboard:customer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_NOTE_MANAGE)
def customer_status_update(request, pk):
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    try:
        customer_crm_service.set_internal_status(store, [customer.pk], request.POST.get("internal_status", ""), actor=request.user)
        messages.success(request, "وضعیتِ داخلیِ مشتری به‌روزرسانی شد")
    except customer_crm_service.CustomerCrmError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:customer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_NOTE_MANAGE)
def customer_note_add(request, pk):
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    profile = customer_crm_service.get_or_create_profile(store, customer)
    body = request.POST.get("body", "").strip()
    if body:
        customer_crm_service.add_note(
            profile, author=request.user, body=body, is_pinned=bool(request.POST.get("is_pinned")),
        )
        messages.success(request, "یادداشت ثبت شد")
    return redirect("dashboard:customer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_NOTE_MANAGE)
def customer_note_delete(request, pk, note_id):
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    note = get_object_or_404(CustomerNote, pk=note_id, profile__store=store, profile__customer=customer)
    customer_crm_service.delete_note(note, actor=request.user)
    messages.success(request, "یادداشت حذف شد")
    return redirect("dashboard:customer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_TAG_MANAGE)
def customer_tag_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    tag_id = request.POST.get("tag_id", "")
    action = request.POST.get("action", "")
    try:
        if action == "add":
            customer_crm_service.bulk_add_tag(store, [customer.pk], tag_id, actor=request.user)
        elif action == "remove":
            customer_crm_service.bulk_remove_tag(store, [customer.pk], tag_id, actor=request.user)
    except customer_crm_service.CustomerCrmError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:customer-detail", pk=pk)


# ---------------------------------------------------------------- برچسب‌های مشتری (CustomerTag)

@staff_required
@permission_required(CUSTOMER_TAG_MANAGE)
def customer_tag_list(request):
    store = _resolve_dashboard_store(request)
    tags = CustomerTag.objects.filter(store=store).order_by("name")
    return render(request, "dashboard/customer_tag_list.html", {"tags": tags, "active_page": "customers"})


@require_POST
@staff_required
@permission_required(CUSTOMER_TAG_MANAGE)
def customer_tag_add(request):
    store = _resolve_dashboard_store(request)
    name = request.POST.get("name", "").strip()
    code = slugify(request.POST.get("code", "") or name, allow_unicode=True)
    if name and code:
        try:
            customer_crm_service.create_tag(
                store, name=name, code=code, description=request.POST.get("description", "").strip(),
                color=request.POST.get("color", "").strip(), actor=request.user,
            )
            messages.success(request, "برچسب اضافه شد")
        except customer_crm_service.CustomerCrmError as exc:
            messages.error(request, str(exc))
    return redirect("dashboard:customer-tag-list")


@require_POST
@staff_required
@permission_required(CUSTOMER_TAG_MANAGE)
def customer_tag_archive(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        customer_crm_service.archive_tag(store, pk, actor=request.user)
        messages.success(request, "برچسب غیرفعال شد")
    except customer_crm_service.CustomerCrmError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:customer-tag-list")


# ---------------------------------------------------------------- سگمنت‌های مشتری (Customer Segments)

@staff_required
@permission_required(CUSTOMER_SEGMENT_VIEW, CUSTOMER_SEGMENT_MANAGE)
def segment_list(request):
    store = _resolve_dashboard_store(request)
    segments = (
        CustomerSegment.objects.filter(store=store)
        .annotate(member_count=Count("memberships", distinct=True))
        .order_by("-created_at")
    )
    return render(request, "dashboard/segment_list.html", {
        "segments": segments, "active_page": "segments",
        "can_manage_segments": membership_has_permission(request.store_membership, CUSTOMER_SEGMENT_MANAGE),
    })


def _parse_segment_rules(request):
    fields = request.POST.getlist("rule_field")
    operators = request.POST.getlist("rule_operator")
    values = request.POST.getlist("rule_value")
    values2 = request.POST.getlist("rule_value2")
    rows = []
    for i in range(len(fields)):
        field = fields[i].strip()
        operator = operators[i].strip() if i < len(operators) else ""
        value = values[i].strip() if i < len(values) else ""
        value2 = values2[i].strip() if i < len(values2) else ""
        if field and operator:
            rows.append({"field": field, "operator": operator, "value": value, "value2": value2, "position": i})
    return rows


@staff_required
@permission_required(CUSTOMER_SEGMENT_MANAGE)
def segment_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store) if pk else None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        segment_type = request.POST.get("segment_type", CustomerSegment.SegmentType.STATIC)
        match_mode = request.POST.get("match_mode", CustomerSegment.MatchMode.ALL)
        create_blocked = None
        if segment is None:
            # گیتِ اشتراک/قابلیت/سقفِ سگمنت (checkpoint 5A، §29) — فقط مسیرِ ساخت.
            try:
                subscription_enforcement.enforce_can_create_segment(store)
            except EntitlementError as exc:
                create_blocked = str(exc)
        if not name:
            messages.error(request, "نام سگمنت الزامی است")
        elif create_blocked:
            messages.error(request, create_blocked)
        else:
            if segment is None:
                segment = CustomerSegment.objects.create(
                    store=store, name=name, description=description,
                    segment_type=segment_type, match_mode=match_mode,
                )
            else:
                segment.name = name
                segment.description = description
                segment.segment_type = segment_type
                segment.match_mode = match_mode
                segment.save(update_fields=["name", "description", "segment_type", "match_mode"])

            if segment.segment_type == CustomerSegment.SegmentType.DYNAMIC:
                rows = _parse_segment_rules(request)
                try:
                    for row in rows:
                        segment_service.validate_rule(row["field"], row["operator"])
                except segment_service.SegmentError as exc:
                    messages.error(request, str(exc))
                    return render(request, "dashboard/segment_form.html", {
                        "segment": segment, "active_page": "segments",
                        "field_choices": segment_service.field_choices(),
                        "operator_labels": segment_service.OPERATOR_LABELS,
                        "allowed_fields": segment_service.ALLOWED_FIELDS,
                    })
                segment.rules.all().delete()
                CustomerSegmentRule.objects.bulk_create([
                    CustomerSegmentRule(segment=segment, **row) for row in rows
                ])
            record_audit_event(
                store=store, actor=request.user,
                action_code="customer_segment.created" if pk is None else "customer_segment.updated",
                object_type="CustomerSegment", object_id=str(segment.pk), object_label=segment.name,
            )
            messages.success(request, "سگمنت ذخیره شد")
            return redirect("dashboard:segment-detail", pk=segment.pk)

    return render(request, "dashboard/segment_form.html", {
        "segment": segment, "active_page": "segments",
        "field_choices": segment_service.field_choices(),
        "operator_labels": segment_service.OPERATOR_LABELS,
        "allowed_fields": segment_service.ALLOWED_FIELDS,
    })


@staff_required
@permission_required(CUSTOMER_SEGMENT_VIEW, CUSTOMER_SEGMENT_MANAGE)
def segment_detail(request, pk):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store)
    try:
        preview_customers = list(segment_service.preview_segment(segment)[:200])
        preview_error = ""
    except segment_service.SegmentError as exc:
        preview_customers = []
        preview_error = str(exc)
    return render(request, "dashboard/segment_detail.html", {
        "segment": segment, "active_page": "segments",
        "preview_customers": preview_customers, "preview_error": preview_error,
        "can_manage_segments": membership_has_permission(request.store_membership, CUSTOMER_SEGMENT_MANAGE),
    })


@require_POST
@staff_required
@permission_required(CUSTOMER_SEGMENT_MANAGE)
def segment_refresh(request, pk):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store)
    try:
        count = segment_service.refresh_segment_membership(segment, actor=request.user)
        messages.success(request, f"سگمنت تازه‌سازی شد — {count} مشتری")
    except segment_service.SegmentError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:segment-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_SEGMENT_MANAGE)
def segment_toggle_active(request, pk):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store)
    segment.is_active = not segment.is_active
    segment.save(update_fields=["is_active"])
    messages.success(request, "وضعیتِ سگمنت به‌روزرسانی شد")
    return redirect("dashboard:segment-list")


@require_POST
@staff_required
@permission_required(CUSTOMER_SEGMENT_MANAGE)
def segment_member_add(request, pk):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store)
    phone = request.POST.get("phone", "").strip()
    customer = Customer.objects.filter(phone=phone, orders__store=store).distinct().first()
    try:
        if customer is None:
            messages.error(request, "مشتری‌ای با این موبایل در این فروشگاه یافت نشد")
        else:
            added = segment_service.add_static_member(segment, customer.pk, actor=request.user)
            messages.success(request, "مشتری اضافه شد" if added else "این مشتری از قبل عضو بود")
    except segment_service.SegmentError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:segment-detail", pk=pk)


@require_POST
@staff_required
@permission_required(CUSTOMER_SEGMENT_MANAGE)
def segment_member_remove(request, pk, customer_id):
    store = _resolve_dashboard_store(request)
    segment = get_object_or_404(CustomerSegment, pk=pk, store=store)
    try:
        segment_service.remove_static_member(segment, customer_id, actor=request.user)
        messages.success(request, "مشتری از سگمنت حذف شد")
    except segment_service.SegmentError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:segment-detail", pk=pk)


# -------------------------------------------------------- گزارش‌های حرفه‌ای


@staff_required
@permission_required(REPORTS_VIEW)
def report_list(request):
    store = _resolve_dashboard_store(request)
    context = report_service.build_report_context(store, request.GET.get("range", "30"))
    context["active_page"] = "reports"
    return render(request, "dashboard/reports.html", context)


@staff_required
@permission_required(REPORTS_VIEW)
def report_partial(request):
    store = _resolve_dashboard_store(request)
    context = report_service.build_report_context(store, request.GET.get("range", "30"))
    return render(request, "dashboard/partials/reports_body.html", context)


# ------------------------------------------------------------------ تنظیمات


THEME_TOKEN_DEFAULTS = {
    "primary_color": "#6D28D9", "accent_color": "#FF4D77", "secondary_color": "#7C3AED",
    "background_color": "#F7F5FC", "surface_color": "#FFFFFF", "text_color": "#241C3A",
    "muted_text_color": "#8B86A3",
}


def _settings_context(
    request, *, shop_form=None, finance_form=None, gift_wrap_form=None, sms_form=None, visual_form=None,
):
    store = _resolve_dashboard_store(request)
    shop = ShopSettings.load(store=store)
    theme_values = {
        field: safe_hex(getattr(shop, field), default) for field, default in THEME_TOKEN_DEFAULTS.items()
    }
    return {
        "shop": shop,
        "shop_form": shop_form or ShopInfoForm(initial={
            "name": shop.name, "tagline": shop.tagline, "contact_phone": shop.contact_phone,
            "contact_email": shop.contact_email, "contact_address": shop.contact_address,
            "description": shop.description,
        }),
        "finance_form": finance_form or FinanceSettingsForm(initial={
            "tax_percent": shop.tax_percent, "free_shipping_threshold": shop.free_shipping_threshold,
        }),
        "gift_wrap_form": gift_wrap_form or GiftWrapSettingsForm(initial={
            "gift_wrap_available": shop.gift_wrap_available, "gift_wrap_price": shop.gift_wrap_price,
        }),
        "sms_form": sms_form or SmsConnectionForm(initial={
            "sms_enabled": shop.sms_enabled, "sms_backend": shop.sms_backend,
        }),
        "smsrasti_device_token": shop.smsrasti_device_token,
        "sms_balance": balance_service.get_or_create_balance(store=store),
        "sms_billing_policy": SmsBillingPolicy.load(),
        "sms_packages": balance_service.list_active_packages(),
        "sms_package_purchase_form": SmsPackagePurchaseForm(),
        "sms_pending_purchases": store.sms_package_purchases.filter(
            status=SmsPackagePurchase.Status.PENDING
        ).select_related("package"),
        "visual_form": visual_form or VisualIdentityForm(current_shop=shop, initial=theme_values),
        "theme_presets": THEME_PRESETS,
        "selected_preset_key": matching_preset_key(
            primary=theme_values["primary_color"], secondary=theme_values["secondary_color"],
            accent=theme_values["accent_color"], background=theme_values["background_color"],
        ),
        "sms_template_rows": sms_admin_service.templates_with_variables(),
        "sms_test_form": SmsTestForm(),
        "gateways": settings_admin_service.active_gateways_context(store=store),
        "shipping_methods": settings_admin_service.shipping_methods_context(store=store),
        "gateway_configs": settings_admin_service.gateway_configs_context(store=store),
        "industry_templates": _latest_active_industry_templates(),
        "industry_sector_tabs": industry_catalog_service.SECTOR_TABS,
        "industry_installation": _industry_installation_context(store),
        "integration_rows": integration_service.connections_context(store=store),
        "active_page": "settings",
    }


def _latest_active_industry_templates():
    """جدیدترین نسخه‌ی «آماده‌ی تولید» هر صنف — نازک‌پوششی روی تکِ منبعِ
    حقیقتِ کاتالوگِ صنف (``industry_catalog_service``، بخشِ ۲)."""
    return industry_catalog_service.offerable_industry_templates()


def _industry_installation_context(store):
    installation = (
        StoreIndustryInstallation.objects.filter(store=store).select_related("industry_template").first()
    )
    if installation is None:
        return None
    newer = latest_production_version(installation.industry_template.slug)
    update_available = bool(newer and newer.version > installation.installed_version)
    return {
        "installation": installation,
        "update_available": update_available,
        "latest_version": newer,
    }


SETTINGS_SECTIONS = [
    ("general", "اطلاعات فروشگاه", "🏪", "نام، شعار و اطلاعات تماس فروشگاه"),
    ("finance", "مالی و مالیات", "💰", "نرخ مالیات و آستانه‌ی ارسال رایگان"),
    ("delivery-payment", "ارسال و درگاه", "🚚", "روش‌های ارسال و درگاه‌های پرداخت"),
    ("payment-config", "پیکربندی درگاه", "🔐", "تنظیمات اعتبارنامه و فعال‌سازی درگاه‌های پرداخت"),
    ("sms", "پیامک", "📲", "اتصال و قالب‌های پیامک"),
    ("appearance", "تم رنگی", "🎨", "پیش‌فرض‌ها و رنگ‌بندی سفارشی فروشگاه"),
    ("industry", "صنف فروشگاه", "🏭", "نصب الگوی کاتالوگ آماده بر اساس صنف فعالیت"),
    ("integrations", "یکپارچه‌سازی‌ها", "🔗", "اینماد، ترب، گوگل آنالیتیکس و سایرِ اتصال‌های بیرونی"),
]

VALID_SECTION_KEYS = {s[0] for s in SETTINGS_SECTIONS}


@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_home(request):
    section = request.GET.get("section", "general")
    if section not in VALID_SECTION_KEYS:
        section = "general"
    context = _settings_context(request)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = section
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_industry_install(request, template_id):
    store = _resolve_dashboard_store(request)
    template = get_object_or_404(IndustryTemplate, pk=template_id)
    try:
        install_industry_template(store, template)
    except IndustryInstallationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"الگوی صنف «{template.name}» با موفقیت نصب شد")
    return redirect(f"{reverse('dashboard:settings')}?section=industry")


@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_industry_preview(request, template_id):
    """پیش‌نمایش کامل قالب صنف پیش از نصب — نگاه کنید به بخش ۱۳/۱۴ پرامپت فاز ۱F."""
    store = _resolve_dashboard_store(request)
    template = get_object_or_404(IndustryTemplate, pk=template_id)
    preview = build_template_preview(template)
    plan = plan_industry_template_installation(store, template)
    return render(request, "dashboard/industry_template_preview.html", {
        "template": template, "preview": preview, "plan": plan, "active_page": "settings",
    })


def _current_installation_and_target(store):
    installation = StoreIndustryInstallation.objects.filter(store=store).select_related("industry_template").first()
    if installation is None:
        return None, None
    target = latest_production_version(installation.industry_template.slug)
    if target is None or target.pk == installation.industry_template_id:
        return installation, None
    return installation, target


@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_industry_update_plan(request):
    """برنامه‌ی به‌روزرسانیِ نصبِ فعلی به جدیدترین نسخه‌ی «آماده‌ی تولید» — نگاه کنید به ADR-29."""
    store = _resolve_dashboard_store(request)
    installation, target = _current_installation_and_target(store)
    if installation is None:
        messages.error(request, "این فروشگاه هنوز هیچ الگوی صنفی نصب نکرده است.")
        return redirect(f"{reverse('dashboard:settings')}?section=industry")
    if target is None:
        messages.info(request, "نسخه‌ی جدیدتری برای به‌روزرسانی موجود نیست.")
        return redirect(f"{reverse('dashboard:settings')}?section=industry")

    plan = plan_template_update(installation, target)
    return render(request, "dashboard/industry_template_update.html", {
        "installation": installation, "target": target, "plan": plan, "active_page": "settings",
    })


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_industry_update_apply(request):
    store = _resolve_dashboard_store(request)
    installation, target = _current_installation_and_target(store)
    if installation is None or target is None:
        messages.error(request, "به‌روزرسانیِ در دسترسی برای اعمال وجود ندارد.")
        return redirect(f"{reverse('dashboard:settings')}?section=industry")

    plan = plan_template_update(installation, target)
    safe_ids = {c.change_id for c in plan.safe_additive}
    selected = [cid for cid in request.POST.getlist("change_id") if cid in safe_ids]

    try:
        apply_template_update(installation, target, selected, actor=request.user)
    except TemplateUpdateError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"به‌روزرسانی به نسخه‌ی {target.version} با موفقیت اعمال شد.")
    return redirect(f"{reverse('dashboard:settings')}?section=industry")


@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_industry_update_history(request):
    store = _resolve_dashboard_store(request)
    updates = (
        StoreTemplateUpdate.objects.filter(store=store)
        .select_related("from_template", "target_template", "actor")
        .order_by("-started_at")
    )
    return render(request, "dashboard/industry_template_update_history.html", {
        "updates": updates, "active_page": "settings",
    })


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_shop_info(request):
    form = ShopInfoForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        for field in ["name", "tagline", "contact_phone", "contact_email", "contact_address", "description"]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "اطلاعات فروشگاه ذخیره شد")
        return redirect("/admin-portal/settings/?section=general")
    context = _settings_context(request, shop_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "general"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_finance(request):
    form = FinanceSettingsForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        shop.tax_percent = form.cleaned_data["tax_percent"]
        shop.free_shipping_threshold = form.cleaned_data["free_shipping_threshold"]
        shop.save()
        messages.success(request, "تنظیمات مالی ذخیره شد")
        return redirect("/admin-portal/settings/?section=finance")
    context = _settings_context(request, finance_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "finance"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_gift_wrap(request):
    """کادوپیچی (toranj_gifting: optional_addon_checkbox_updates_total) —
    فعال‌سازی/قیمت‌گذاری در دسترسِ مدیرِ فروشگاه، مستقل از خانواده‌ی بصری."""
    form = GiftWrapSettingsForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        shop.gift_wrap_available = form.cleaned_data["gift_wrap_available"]
        shop.gift_wrap_price = form.cleaned_data["gift_wrap_price"]
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price", "updated_at"])
        messages.success(request, "تنظیمات کادوپیچی ذخیره شد")
        return redirect("/admin-portal/settings/?section=finance")
    context = _settings_context(request, gift_wrap_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "finance"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_toggle(request, pk):
    gateway = settings_admin_service.toggle_gateway(pk, store=_resolve_dashboard_store(request))
    state = "فعال" if gateway.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"درگاه «{gateway.name}» {state} شد", "type": "info"}})
    return response


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_shipping_toggle(request, pk):
    method = settings_admin_service.toggle_shipping_method(pk, store=_resolve_dashboard_store(request))
    state = "فعال" if method.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"روش ارسال «{method.name}» {state} شد", "type": "info"},
    })
    return response


# --------------------------------------------------------------- هویت بصری


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_appearance(request):
    """ذخیره تنظیمات هویت بصری: لوگو، فاوآیکون، توکن‌های رنگی تم؛ یا بازگردانی به پیش‌فرض."""
    from django.db import transaction as db_transaction

    if request.POST.get("action") == "reset":
        shop = ShopSettings.load(store=request.store)
        for field, default in THEME_TOKEN_DEFAULTS.items():
            setattr(shop, field, default)
        shop.save()
        messages.success(request, "رنگ‌بندی به پیش‌فرض بازگردانی شد")
        return redirect("/admin-portal/settings/?section=appearance")

    shop_for_validation = ShopSettings.load(store=request.store)
    form = VisualIdentityForm(request.POST, request.FILES, current_shop=shop_for_validation)
    if form.is_valid():
        shop = shop_for_validation
        old_logo_name = shop.logo.name if shop.logo else None
        old_favicon_name = shop.favicon.name if shop.favicon else None

        # رنگ‌ها — primary/accent همیشه اجباری‌اند؛ توکن‌های جدید فقط اگر ارسال شده باشند بازنویسی می‌شوند
        shop.primary_color = form.cleaned_data["primary_color"]
        shop.accent_color = form.cleaned_data["accent_color"]
        for field in ("secondary_color", "background_color", "surface_color", "text_color", "muted_text_color"):
            if form.cleaned_data.get(field):
                setattr(shop, field, form.cleaned_data[field])

        # لوگو — replacement wins over removal
        if form.cleaned_data.get("logo"):
            shop.logo = form.cleaned_data["logo"]
        elif form.cleaned_data.get("remove_logo") and shop.logo:
            shop.logo = ""

        # فاوآیکون — replacement wins over removal
        if form.cleaned_data.get("favicon"):
            shop.favicon = form.cleaned_data["favicon"]
        elif form.cleaned_data.get("remove_favicon") and shop.favicon:
            shop.favicon = ""

        shop.save()

        # پاکسازی فایل‌های قبلی فقط پس از ذخیره‌ی موفق (Storage-safe)
        if old_logo_name and old_logo_name != (shop.logo.name if shop.logo else ""):
            storage = shop.logo.storage
            db_transaction.on_commit(lambda n=old_logo_name, s=storage: (
                s.delete(n) if s.exists(n) else None
            ))
        if old_favicon_name and old_favicon_name != (shop.favicon.name if shop.favicon else ""):
            storage = shop.favicon.storage
            db_transaction.on_commit(lambda n=old_favicon_name, s=storage: (
                s.delete(n) if s.exists(n) else None
            ))

        messages.success(request, "هویت بصری فروشگاه ذخیره شد")
        return redirect("/admin-portal/settings/?section=appearance")

    context = _settings_context(request, visual_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "appearance"
    return render(request, "dashboard/settings.html", context)


# --------------------------------------------------------------- پیامک


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def settings_sms_connection(request):
    form = SmsConnectionForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        for field in ["sms_enabled", "sms_backend"]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "تنظیمات پیامک ذخیره شد")
        return redirect("/admin-portal/settings/?section=sms")
    context = _settings_context(request, sms_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "sms"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def settings_sms_package_purchase(request):
    """درخواستِ خریدِ یک بستهِ اعتبارِ پیامک را با وضعیتِ «در انتظار» ثبت
    می‌کند — اعتبار فقط پس از تکمیلِ آن از Platform Admin افزوده می‌شود
    (نگاه کنید به ``apps.sms.services.balance_service``)."""
    form = SmsPackagePurchaseForm(request.POST)
    if form.is_valid():
        package = get_object_or_404(SmsPackage, pk=form.cleaned_data["package_id"], is_active=True)
        balance_service.request_purchase(store=_resolve_dashboard_store(request), package=package)
        messages.success(request, "درخواستِ خرید ثبت شد؛ پس از تأیید، اعتبار به حساب شما افزوده می‌شود")
    else:
        messages.error(request, "بسته‌ی انتخاب‌شده نامعتبر است")
    return redirect("/admin-portal/settings/?section=sms")


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def settings_smsrasti_regenerate_token(request):
    """توکنِ قبلی (اگر باشد) بلافاصله باطل می‌شود؛ دستگاهِ اندرویدِ قدیمی
    باید با توکنِ جدید دوباره پیکربندی شود."""
    regenerate_smsrasti_device_token(store=_resolve_dashboard_store(request))
    messages.success(request, "توکنِ دستگاهِ اسمس‌راستی بازتولید شد؛ دستگاهِ اندروید را با مقدارِ جدید پیکربندی کنید")
    return redirect("/admin-portal/settings/?section=sms")


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_template_form(request, pk):
    template = get_object_or_404(SmsTemplate.objects.exclude(event_key__in=[SmsEvent.PLATFORM_OWNER_OTP, SmsEvent.PLATFORM_TEST, SmsEvent.NOTIFICATION]), pk=pk)

    if request.method == "POST":
        form = SmsTemplateForm(request.POST, event_key=template.event_key)
        if form.is_valid():
            template.body = form.cleaned_data["body"]
            template.save(update_fields=["body", "updated_at"])
            table_html = render_to_string(
                "dashboard/partials/sms_templates_table.html",
                {"sms_template_rows": sms_admin_service.templates_with_variables()},
                request=request,
            )
            response = render(request, "dashboard/partials/oob_wrap.html", {
                "target_id": "smsTemplatesWrap", "inner_html": table_html,
            })
            response["HX-Trigger"] = json.dumps({
                "toast": {"message": "قالب پیامک ذخیره شد", "type": "ok"},
                "modal-close": {},
            })
            return response
    else:
        form = SmsTemplateForm(event_key=template.event_key, initial={"body": template.body})

    variables = EVENT_VARIABLES.get(template.event_key, {})
    return render(
        request, "dashboard/partials/sms_template_form.html",
        {"form": form, "template": template, "variables": variables},
    )


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_template_toggle(request, pk):
    template = get_object_or_404(SmsTemplate.objects.exclude(event_key__in=[SmsEvent.PLATFORM_OWNER_OTP, SmsEvent.PLATFORM_TEST, SmsEvent.NOTIFICATION]), pk=pk)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if template.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"پیامک «{template.title}» {state} شد", "type": "info"},
    })
    return response


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_test_send(request):
    form = SmsTestForm(request.POST)
    event_key = request.POST.get("event_key", "")
    if form.is_valid():
        try:
            log = send_test_sms(
                event_key=event_key, phone=form.cleaned_data["phone"],
                store=_resolve_dashboard_store(request),
            )
        except SmsTemplateError as exc:
            messages.error(request, str(exc))
        else:
            if log.status == log.Status.SENT:
                messages.success(request, f"پیامک آزمایشی ارسال شد (وضعیت: {log.get_status_display()})")
            else:
                messages.error(request, f"ارسال ناموفق بود: {log.error_message or 'خطای نامشخص'}")
    else:
        messages.error(request, "شماره موبایل معتبر نیست")
    return redirect("/admin-portal/settings/?section=sms")


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_log_list(request):
    store = _resolve_dashboard_store(request)
    context = {
        "logs": sms_admin_service.filtered_logs(status=request.GET.get("status", ""), store=store),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
        "active_page": "settings",
    }
    return render(request, "dashboard/sms_logs.html", context)


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_log_table(request):
    store = _resolve_dashboard_store(request)
    context = {
        "logs": sms_admin_service.filtered_logs(status=request.GET.get("status", ""), store=store),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
    }
    return render(request, "dashboard/partials/sms_logs_table_inner.html", context)


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_log_retry(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        log = retry_failed_log(log_id=pk, store=store)
    except RetryNotEligibleError as exc:
        messages.error(request, str(exc))
    else:
        if log.status == log.Status.SENT:
            messages.success(request, "پیامک با موفقیت دوباره ارسال شد")
        else:
            messages.error(request, f"ارسالِ دوباره هم ناموفق بود: {log.error_message}")
    return redirect(request.META.get("HTTP_REFERER") or "/admin-portal/settings/sms/logs/")


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_outbox_list(request):
    store = _resolve_dashboard_store(request)
    context = {
        "items": sms_admin_service.filtered_outbox_items(status=request.GET.get("status", ""), store=store),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
        "active_page": "settings",
    }
    return render(request, "dashboard/sms_outbox.html", context)


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_outbox_retry(request, pk):
    store = _resolve_dashboard_store(request)
    try:
        retry_smsrasti_outbox_item(item_id=pk, store=store)
    except RetryNotEligibleError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "آیتم دوباره در صفِ ارسال قرار گرفت")
    return redirect("dashboard:sms-outbox-list")


# --------------------------------------------------------------- یکپارچه‌سازی‌ها


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_integration_connect(request, provider_code):
    store = _resolve_dashboard_store(request)
    provider = get_integration_provider(provider_code)
    if provider is None:
        return HttpResponse(status=404)

    values = {f.key: request.POST.get(f.key, "").strip() for f in provider.fields}
    try:
        integration_service.connect(store=store, provider_code=provider_code, values=values, actor=request.user)
    except integration_service.IntegrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{provider.display_name} با موفقیت متصل شد")
    return redirect("/admin-portal/settings/?section=integrations")


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_integration_disconnect(request, provider_code):
    store = _resolve_dashboard_store(request)
    provider = get_integration_provider(provider_code)
    if provider is None:
        return HttpResponse(status=404)

    integration_service.disconnect(store=store, provider_code=provider_code, actor=request.user)
    messages.success(request, f"اتصالِ {provider.display_name} قطع شد")
    return redirect("/admin-portal/settings/?section=integrations")


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_integration_test(request, provider_code):
    store = _resolve_dashboard_store(request)
    provider = get_integration_provider(provider_code)
    if provider is None:
        return HttpResponse(status=404)

    connection = integration_service.test_connection(store=store, provider_code=provider_code, actor=request.user)
    if connection.last_test_result == "success":
        messages.success(request, f"{provider.display_name}: {connection.last_test_message}")
    else:
        messages.error(request, f"{provider.display_name}: {connection.last_test_message}")
    return redirect("/admin-portal/settings/?section=integrations")


# ---------------------------------------------------------------- صفحات محتوایی

from apps.content.models import ContentPage


@staff_required
@permission_required(CONTENT_MANAGE)
def page_list(request):
    store = _resolve_dashboard_store(request)
    pages = ContentPage.objects.filter(store=store).order_by("-created_at")
    context = {"pages": pages, "active_page": "pages"}
    return render(request, "dashboard/pages.html", context)


@staff_required
@permission_required(CONTENT_MANAGE)
def page_form(request, pk=None):
    from django.utils.text import slugify as django_slugify

    store = _resolve_dashboard_store(request)
    page = get_object_or_404(ContentPage, pk=pk, store=store) if pk else None

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        slug = request.POST.get("slug", "").strip()
        body = request.POST.get("body", "")
        summary = request.POST.get("summary", "").strip()
        seo_title = request.POST.get("seo_title", "").strip()
        seo_description = request.POST.get("seo_description", "").strip()
        show_in_footer = request.POST.get("show_in_footer") == "on"
        footer_column = request.POST.get("footer_column", "")
        display_order = int(request.POST.get("display_order", "0") or "0")

        if not title:
            messages.error(request, "عنوان صفحه الزامی است")
            return redirect(request.path)

        if not slug:
            slug = django_slugify(title, allow_unicode=True) or "page"

        if page is None:
            page = ContentPage(store=store)

        page.title = title
        page.slug = slug
        page.body = body
        page.summary = summary
        page.seo_title = seo_title
        page.seo_description = seo_description
        page.show_in_footer = show_in_footer
        page.footer_column = footer_column
        page.display_order = display_order

        try:
            page.full_clean()
            page.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"صفحه‌ی «{page.title}» با موفقیت {action} شد")
            return redirect("dashboard:page-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                msg = " ".join(v[0] if isinstance(v, list) else v for v in exc.message_dict.values())
            else:
                msg = str(exc)
            messages.error(request, msg)
            return redirect(request.path)

    context = {"page": page, "active_page": "pages", "footer_columns": ContentPage.FooterColumn.choices}
    return render(request, "dashboard/page_form.html", context)


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def page_delete(request, pk):
    store = _resolve_dashboard_store(request)
    page = get_object_or_404(ContentPage, pk=pk, store=store)
    title = page.title
    page.delete()
    messages.success(request, f"صفحه‌ی «{title}» حذف شد")
    return redirect("dashboard:page-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def page_publish(request, pk):
    from django.utils import timezone

    store = _resolve_dashboard_store(request)
    page = get_object_or_404(ContentPage, pk=pk, store=store)
    if page.status == ContentPage.Status.PUBLISHED:
        page.status = ContentPage.Status.DRAFT
        page.published_at = None
        page.published_by = None
        messages.info(request, f"صفحه‌ی «{page.title}» به پیش‌نویس برگشت")
    else:
        page.status = ContentPage.Status.PUBLISHED
        page.published_at = timezone.now()
        page.published_by = request.user
        messages.success(request, f"صفحه‌ی «{page.title}» منتشر شد")
    page.save()
    return redirect("dashboard:page-list")



# ---------------------------------------------------------------- صفحه اصلی (اسلاید و بنر)

from apps.content.models import HeroSlide, PromotionalBanner


def _uses_visual_storefront_layout(store) -> bool:
    """آیا سازنده بصری برای این فروشگاه منتشر شده — دقیقاً همان شرطی که
    ``apps.catalog.views.home`` برایِ انتخابِ بینِ مسیرِ Builder و مسیرِ
    قدیمیِ سخت‌کدشده چک می‌کند. اگر True باشد، صفحاتِ قدیمیِ اسلایدر/بنر
    (``hero_list``/``banner_list``) دیگر هیچ اثری روی صفحه‌ی عمومیِ این
    فروشگاه ندارند — چون بخشِ ``hero_banner``ی سازنده جای‌گزینِ آن‌هاست."""
    from apps.storefront_builder.models import StorefrontLayout

    return StorefrontLayout.objects.filter(
        store=store, uses_visual_storefront_layout=True, published_version__isnull=False,
    ).exists()


@staff_required
@permission_required(CONTENT_MANAGE)
def hero_list(request):
    store = _resolve_dashboard_store(request)
    slides = HeroSlide.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/hero_list.html", {
        "slides": slides, "active_page": "homepage",
        "storefront_builder_active": _uses_visual_storefront_layout(store),
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def hero_form(request, pk=None):
    from django.db import transaction

    from apps.catalog.models import Brand, Category
    store = _resolve_dashboard_store(request)
    slide = get_object_or_404(HeroSlide, pk=pk, store=store) if pk else None

    if request.method == "POST":
        obj = slide or HeroSlide(store=store)

        # Capture old file names before modification
        old_desktop_name = obj.desktop_image.name if obj.pk and obj.desktop_image else None
        old_mobile_name = obj.mobile_image.name if obj.pk and obj.mobile_image else None

        obj.title = request.POST.get("title", "").strip()
        obj.subtitle = request.POST.get("subtitle", "").strip()
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active") == "on"
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        # FK destinations
        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        # Images
        if "desktop_image" in request.FILES:
            obj.desktop_image = request.FILES["desktop_image"]
        if "mobile_image" in request.FILES:
            obj.mobile_image = request.FILES["mobile_image"]
        if request.POST.get("remove_mobile") == "on" and "mobile_image" not in request.FILES:
            obj.mobile_image = ""

        try:
            obj.full_clean()
            obj.save()

            # Schedule old file cleanup after successful commit
            storage = HeroSlide.desktop_image.field.storage
            new_desktop_name = obj.desktop_image.name if obj.desktop_image else None
            new_mobile_name = obj.mobile_image.name if obj.mobile_image else None

            files_to_delete = []
            if old_desktop_name and old_desktop_name != new_desktop_name:
                files_to_delete.append(old_desktop_name)
            if old_mobile_name and old_mobile_name != new_mobile_name:
                files_to_delete.append(old_mobile_name)

            if files_to_delete:
                transaction.on_commit(lambda: [
                    storage.delete(f) for f in files_to_delete if storage.exists(f)
                ])

            messages.success(request, f"اسلاید «{obj.title or obj.pk}» ذخیره شد")
            return redirect("dashboard:hero-list")
        except (ValidationError, IntegrityError) as exc:
            msg = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, msg)

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    return render(request, "dashboard/hero_form.html", {
        "slide": slide, "active_page": "homepage", "categories": categories,
    })


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def hero_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    slide = get_object_or_404(HeroSlide, pk=pk, store=store)
    desktop_name = slide.desktop_image.name if slide.desktop_image else None
    mobile_name = slide.mobile_image.name if slide.mobile_image else None
    storage = slide.desktop_image.storage

    slide.delete()

    # Delete owned files only after successful DB commit
    def _cleanup():
        if desktop_name and storage.exists(desktop_name):
            storage.delete(desktop_name)
        if mobile_name and storage.exists(mobile_name):
            storage.delete(mobile_name)

    transaction.on_commit(_cleanup)
    messages.success(request, "اسلاید حذف شد")
    return redirect("dashboard:hero-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def hero_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    slide = get_object_or_404(HeroSlide, pk=pk, store=store)
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if slide.is_active else "غیرفعال"
    messages.info(request, f"اسلاید {state} شد")
    return redirect("dashboard:hero-list")


@staff_required
@permission_required(CONTENT_MANAGE)
def banner_list(request):
    store = _resolve_dashboard_store(request)
    banners = PromotionalBanner.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/banner_list.html", {
        "banners": banners, "active_page": "homepage",
        "storefront_builder_active": _uses_visual_storefront_layout(store),
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def banner_form(request, pk=None):
    from django.db import transaction

    from apps.catalog.models import Brand, Category
    store = _resolve_dashboard_store(request)
    banner = get_object_or_404(PromotionalBanner, pk=pk, store=store) if pk else None

    if request.method == "POST":
        obj = banner or PromotionalBanner(store=store)

        # Capture old file names before modification
        old_desktop_name = obj.desktop_image.name if obj.pk and obj.desktop_image else None
        old_mobile_name = obj.mobile_image.name if obj.pk and obj.mobile_image else None

        obj.title = request.POST.get("title", "").strip()
        obj.description = request.POST.get("description", "").strip()
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active") == "on"
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        if "desktop_image" in request.FILES:
            obj.desktop_image = request.FILES["desktop_image"]
        if "mobile_image" in request.FILES:
            obj.mobile_image = request.FILES["mobile_image"]
        if request.POST.get("remove_mobile") == "on" and "mobile_image" not in request.FILES:
            obj.mobile_image = ""

        try:
            obj.full_clean()
            obj.save()

            # Schedule old file cleanup after successful commit
            storage = PromotionalBanner.desktop_image.field.storage
            new_desktop_name = obj.desktop_image.name if obj.desktop_image else None
            new_mobile_name = obj.mobile_image.name if obj.mobile_image else None

            files_to_delete = []
            if old_desktop_name and old_desktop_name != new_desktop_name:
                files_to_delete.append(old_desktop_name)
            if old_mobile_name and old_mobile_name != new_mobile_name:
                files_to_delete.append(old_mobile_name)

            if files_to_delete:
                transaction.on_commit(lambda: [
                    storage.delete(f) for f in files_to_delete if storage.exists(f)
                ])

            messages.success(request, f"بنر «{obj.title or obj.pk}» ذخیره شد")
            return redirect("dashboard:banner-list")
        except (ValidationError, IntegrityError) as exc:
            msg = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, msg)

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    return render(request, "dashboard/banner_form.html", {
        "banner": banner, "active_page": "homepage", "categories": categories,
    })


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def banner_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    banner = get_object_or_404(PromotionalBanner, pk=pk, store=store)
    desktop_name = banner.desktop_image.name if banner.desktop_image else None
    mobile_name = banner.mobile_image.name if banner.mobile_image else None
    storage = banner.desktop_image.storage

    banner.delete()

    # Delete owned files only after successful DB commit
    def _cleanup():
        if desktop_name and storage.exists(desktop_name):
            storage.delete(desktop_name)
        if mobile_name and storage.exists(mobile_name):
            storage.delete(mobile_name)

    transaction.on_commit(_cleanup)
    messages.success(request, "بنر حذف شد")
    return redirect("dashboard:banner-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def banner_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    banner = get_object_or_404(PromotionalBanner, pk=pk, store=store)
    banner.is_active = not banner.is_active
    banner.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if banner.is_active else "غیرفعال"
    messages.info(request, f"بنر {state} شد")
    return redirect("dashboard:banner-list")




# ---------------------------------------------------------------- شبکه‌های اجتماعی

from apps.content.models import SocialLink


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_list(request):
    store = _resolve_dashboard_store(request)
    links = SocialLink.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/social_links.html", {
        "links": links, "active_page": "social_links",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    link = get_object_or_404(SocialLink, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = link or SocialLink(store=store)
        obj.platform = request.POST.get("platform", "custom")
        obj.title = request.POST.get("title", "").strip()
        obj.url = request.POST.get("url", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"
        obj.show_in_header = request.POST.get("show_in_header") == "on"
        obj.show_in_footer = request.POST.get("show_in_footer") == "on"

        try:
            obj.full_clean()
            obj.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"لینک «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:social-link-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    platforms = SocialLink.Platform.choices
    return render(request, "dashboard/social_link_form.html", {
        "link": link, "active_page": "social_links", "platforms": platforms,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_delete(request, pk):
    store = _resolve_dashboard_store(request)
    link = get_object_or_404(SocialLink, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "لینک شبکه اجتماعی",
            "object_name": link.title,
            "cancel_url": reverse("dashboard:social-link-list"),
            "active_page": "social_links",
        })
    title = link.title
    link.delete()
    messages.success(request, f"لینک «{title}» حذف شد")
    return redirect("dashboard:social-link-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    link = get_object_or_404(SocialLink, pk=pk, store=store)
    link.is_active = not link.is_active
    link.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if link.is_active else "غیرفعال"
    messages.info(request, f"لینک «{link.title}» {state} شد")
    return redirect("dashboard:social-link-list")




# ---------------------------------------------------------------- مدیریت منوها

from apps.content.models import Menu, MenuItem


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_list(request):
    store = _resolve_dashboard_store(request)
    menus = Menu.objects.filter(store=store).annotate(item_count=Count("items")).order_by("location")
    return render(request, "dashboard/menu_list.html", {
        "menus": menus, "active_page": "menus",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    menu = get_object_or_404(Menu, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = menu or Menu(store=store)
        obj.title = request.POST.get("title", "").strip()
        obj.location = request.POST.get("location", "")
        obj.is_active = request.POST.get("is_active") == "on"

        try:
            obj.full_clean()
            obj.save()
            if pk:
                messages.success(request, f"منوی «{obj.title}» با موفقیت ویرایش شد")
                return redirect("dashboard:menu-list")
            else:
                messages.success(request, f"منوی «{obj.title}» ایجاد شد. اکنون آیتم‌ها را اضافه کنید.")
                return redirect("dashboard:menu-item-list", menu_id=obj.pk)
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                # UniqueConstraint(store, location) violations are non-field
                # errors (multi-field constraint) — Django keys them under
                # "__all__", but the location <select> is the field the
                # merchant needs to see flagged as invalid.
                if "__all__" in field_errors and "location" not in field_errors:
                    field_errors["location"] = field_errors["__all__"]
                msg = " ".join(field_errors.values())
            elif "UNIQUE constraint" in str(exc) or "unique" in str(exc).lower():
                msg = "این مکان قبلاً دارای منو است. هر مکان فقط یک منو می‌تواند داشته باشد."
                field_errors = {"location": msg}
            else:
                msg = str(exc)
            messages.error(request, msg)

    locations = Menu.Location.choices
    return render(request, "dashboard/menu_form.html", {
        "menu": menu, "active_page": "menus", "locations": locations,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_delete(request, pk):
    store = _resolve_dashboard_store(request)
    menu = get_object_or_404(Menu, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "منو",
            "object_name": menu.title,
            "cancel_url": reverse("dashboard:menu-list"),
            "consequence": "تمام آیتم‌های این منو نیز حذف خواهند شد.",
            "active_page": "menus",
        })
    if menu.items.exists():
        messages.error(request, f"منوی «{menu.title}» دارای آیتم است و قابل حذف نیست. ابتدا آیتم‌ها را حذف کنید.")
        return redirect("dashboard:menu-list")
    title = menu.title
    try:
        menu.delete()
    except ProtectedError:
        messages.error(request, f"منوی «{menu.title}» دارای آیتم است و قابل حذف نیست.")
        return redirect("dashboard:menu-list")
    messages.success(request, f"منوی «{title}» حذف شد")
    return redirect("dashboard:menu-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def menu_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    menu = get_object_or_404(Menu, pk=pk, store=store)
    menu.is_active = not menu.is_active
    menu.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if menu.is_active else "غیرفعال"
    messages.info(request, f"منوی «{menu.title}» {state} شد")
    return redirect("dashboard:menu-list")


# --- آیتم‌های منو ---


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_list(request, menu_id):
    store = _resolve_dashboard_store(request)
    menu = get_object_or_404(Menu, pk=menu_id, store=store)
    items = menu.items.select_related("parent").order_by("parent__display_order", "parent__id", "display_order", "id")
    # Organize: top-level first, then children grouped under parents
    top_items = [i for i in items if i.parent_id is None]
    children_map = {}
    for i in items:
        if i.parent_id:
            children_map.setdefault(i.parent_id, []).append(i)

    organized = []
    for item in top_items:
        organized.append(("top", item))
        for child in children_map.get(item.pk, []):
            organized.append(("child", child))

    return render(request, "dashboard/menu_item_list.html", {
        "menu": menu, "organized_items": organized, "active_page": "menus",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_form(request, menu_id=None, pk=None):
    from apps.catalog.models import Category

    store = _resolve_dashboard_store(request)
    if pk:
        item = get_object_or_404(MenuItem, pk=pk, menu__store=store)
        menu = item.menu
    else:
        menu = get_object_or_404(Menu, pk=menu_id, store=store)
        item = None

    field_errors = {}

    if request.method == "POST":
        obj = item or MenuItem(menu=menu)
        obj.title = request.POST.get("title", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        # Parent
        parent_id = request.POST.get("parent") or None
        obj.parent_id = int(parent_id) if parent_id else None

        # Destination fields
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        try:
            obj.full_clean()
            obj.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"آیتم «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:menu-item-list", menu_id=menu.pk)
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    # Parent options: only top-level items of this menu (not the item itself)
    parent_options = menu.items.filter(parent__isnull=True)
    if pk:
        parent_options = parent_options.exclude(pk=pk)

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    return render(request, "dashboard/menu_item_form.html", {
        "item": item, "menu": menu, "active_page": "menus",
        "parent_options": parent_options, "categories": categories,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_delete(request, pk):
    store = _resolve_dashboard_store(request)
    item = get_object_or_404(MenuItem, pk=pk, menu__store=store)
    menu_id = item.menu_id
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "آیتم منو",
            "object_name": item.title,
            "cancel_url": reverse("dashboard:menu-item-list", args=[menu_id]),
            "active_page": "menus",
        })
    try:
        item.delete()
        messages.success(request, f"آیتم «{item.title}» حذف شد")
    except ProtectedError:
        messages.error(request, f"آیتم «{item.title}» دارای زیرآیتم است. ابتدا زیرآیتم‌ها را حذف کنید.")
    return redirect("dashboard:menu-item-list", menu_id=menu_id)


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    item = get_object_or_404(MenuItem, pk=pk, menu__store=store)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if item.is_active else "غیرفعال"
    messages.info(request, f"آیتم «{item.title}» {state} شد")
    return redirect("dashboard:menu-item-list", menu_id=item.menu_id)




# ---------------------------------------------------------------- تنظیمات فوتر

from apps.content.models import FooterSettings, FooterTrustBadge, FooterPaymentLogo


def _resolve_dashboard_store(request):
    """Store مورد نیاز برای عملیات نوشتنِ داشبورد (تنظیمات/نمادها/لوگوهای
    فوتر/سفارش/پیامک آزمایشی) — نازک‌پوششی روی
    ``apps.stores.resolution.resolve_store_for_service``، همان قانون
    fail-closed مشترک در کل کدبیس."""
    from apps.stores.resolution import resolve_store_for_service

    return resolve_store_for_service(request)


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_settings_page(request):
    fs = FooterSettings.load(store=request.store)
    field_errors = {}

    if request.method == "POST":
        fs.is_enabled = request.POST.get("is_enabled") == "on"
        fs.show_branding = request.POST.get("show_branding") == "on"
        fs.show_logo = request.POST.get("show_logo") == "on"
        fs.description = request.POST.get("description", "").strip()
        fs.show_contact = request.POST.get("show_contact") == "on"
        fs.address = request.POST.get("address", "").strip()
        fs.phone = request.POST.get("phone", "").strip()
        fs.secondary_phone = request.POST.get("secondary_phone", "").strip()
        fs.email = request.POST.get("email", "").strip()
        fs.working_hours = request.POST.get("working_hours", "").strip()
        fs.show_navigation = request.POST.get("show_navigation") == "on"
        fs.show_social_links = request.POST.get("show_social_links") == "on"
        fs.show_newsletter = request.POST.get("show_newsletter") == "on"
        fs.newsletter_title = request.POST.get("newsletter_title", "").strip()
        fs.newsletter_description = request.POST.get("newsletter_description", "").strip()
        fs.show_trust_badges = request.POST.get("show_trust_badges") == "on"
        fs.show_payment_logos = request.POST.get("show_payment_logos") == "on"
        fs.copyright_text = request.POST.get("copyright_text", "").strip()

        try:
            fs.full_clean()
            fs.save()
            messages.success(request, "تنظیمات فوتر ذخیره شد")
            return redirect("dashboard:footer-settings")
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)
            open_sections = {"general"}
            if hasattr(exc, "message_dict"):
                field_section_map = {
                    "address": "contact", "phone": "contact", "secondary_phone": "contact",
                    "email": "contact", "working_hours": "contact",
                    "newsletter_title": "newsletter", "newsletter_description": "newsletter",
                    "copyright_text": "copyright",
                }
                for field in exc.message_dict:
                    if field in field_section_map:
                        open_sections.add(field_section_map[field])
            return render(request, "dashboard/footer_settings.html", {
                "fs": fs, "active_page": "footer", "open_sections": open_sections,
                "field_errors": field_errors,
            })

    return render(request, "dashboard/footer_settings.html", {
        "fs": fs, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_list(request):
    store = _resolve_dashboard_store(request)
    badges = FooterTrustBadge.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_trust_badges.html", {
        "badges": badges, "active_page": "footer",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_form(request, pk=None):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = badge or FooterTrustBadge(store=store)
        old_image_name = obj.image.name if obj.pk and obj.image else None

        obj.title = request.POST.get("title", "").strip()
        obj.destination_url = request.POST.get("destination_url", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"

        if "image" in request.FILES:
            obj.image = request.FILES["image"]

        try:
            obj.full_clean()
            obj.save()

            # Cleanup old image
            if old_image_name and old_image_name != (obj.image.name if obj.image else ""):
                storage = obj.image.storage
                transaction.on_commit(lambda n=old_image_name, s=storage: (
                    s.delete(n) if s.exists(n) else None
                ))

            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"نماد اعتماد «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:footer-trust-badge-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    return render(request, "dashboard/footer_trust_badge_form.html", {
        "badge": badge, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "نماد اعتماد",
            "object_name": badge.title,
            "cancel_url": reverse("dashboard:footer-trust-badge-list"),
            "active_page": "footer",
        })
    image_name = badge.image.name if badge.image else None
    storage = badge.image.storage if badge.image else None
    title = badge.title
    badge.delete()

    if image_name and storage:
        transaction.on_commit(lambda: (
            storage.delete(image_name) if storage.exists(image_name) else None
        ))

    messages.success(request, f"نماد اعتماد «{title}» حذف شد")
    return redirect("dashboard:footer-trust-badge-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store)
    badge.is_active = not badge.is_active
    badge.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if badge.is_active else "غیرفعال"
    messages.info(request, f"نماد اعتماد «{badge.title}» {state} شد")
    return redirect("dashboard:footer-trust-badge-list")


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_list(request):
    store = _resolve_dashboard_store(request)
    logos = FooterPaymentLogo.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_payment_logos.html", {
        "logos": logos, "active_page": "footer",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_form(request, pk=None):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = logo or FooterPaymentLogo(store=store)
        old_image_name = obj.image.name if obj.pk and obj.image else None

        obj.title = request.POST.get("title", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"

        if "image" in request.FILES:
            obj.image = request.FILES["image"]

        try:
            obj.full_clean()
            obj.save()

            # Cleanup old image
            if old_image_name and old_image_name != (obj.image.name if obj.image else ""):
                storage = obj.image.storage
                transaction.on_commit(lambda n=old_image_name, s=storage: (
                    s.delete(n) if s.exists(n) else None
                ))

            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"لوگوی پرداخت «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:footer-payment-logo-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    return render(request, "dashboard/footer_payment_logo_form.html", {
        "logo": logo, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "لوگوی پرداخت",
            "object_name": logo.title,
            "cancel_url": reverse("dashboard:footer-payment-logo-list"),
            "active_page": "footer",
        })
    image_name = logo.image.name if logo.image else None
    storage = logo.image.storage if logo.image else None
    title = logo.title
    logo.delete()

    if image_name and storage:
        transaction.on_commit(lambda: (
            storage.delete(image_name) if storage.exists(image_name) else None
        ))

    messages.success(request, f"لوگوی پرداخت «{title}» حذف شد")
    return redirect("dashboard:footer-payment-logo-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store)
    logo.is_active = not logo.is_active
    logo.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if logo.is_active else "غیرفعال"
    messages.info(request, f"لوگوی پرداخت «{logo.title}» {state} شد")
    return redirect("dashboard:footer-payment-logo-list")



# ===========================================================================
# Payment Gateway Configuration (PR1)
# ===========================================================================


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_config_save(request, gateway_code):
    """ذخیره‌ی پیکربندی یک درگاه پرداخت (Zibal/COD) برای فروشگاه فعلی."""
    from apps.orders.encryption import CredentialEncryptionError, mask_credential
    from apps.orders.gateways import get_adapter, GATEWAY_CHOICES
    from apps.orders.models import PaymentGatewayConfig

    store = _resolve_dashboard_store(request)

    # Validate gateway code
    valid_codes = [code for code, _ in GATEWAY_CHOICES]
    if gateway_code not in valid_codes:
        return HttpResponse(status=404)

    # Get or create config for this store+gateway
    config, _created = PaymentGatewayConfig.objects.get_or_create(
        store=store,
        gateway_code=gateway_code,
        defaults={"display_order": len(valid_codes)},
    )

    adapter = get_adapter(gateway_code)

    # Process form data
    is_active = request.POST.get("is_active") == "on"
    is_sandbox = request.POST.get("is_sandbox") == "on"
    display_title = request.POST.get("display_title", "").strip()
    display_order = request.POST.get("display_order", "0")
    try:
        display_order = int(display_order)
    except (TypeError, ValueError):
        display_order = 0

    # Process credentials (only for gateways that need them)
    credentials = config.get_credentials()  # Start with existing
    credential_errors = []

    for field_name in adapter.required_credentials:
        new_value = request.POST.get(f"credential_{field_name}", "").strip()
        if new_value:
            # New value provided — update
            credentials[field_name] = new_value
        # If empty and existing value exists, keep existing (don't clear on blank)

    # Validate credentials before activation
    if is_active and adapter.required_credentials:
        validation_errors = adapter.validate_credentials(credentials)
        if validation_errors:
            credential_errors = validation_errors
            is_active = False  # Cannot activate with invalid credentials

    # Update config
    config.display_title = display_title
    config.display_order = display_order
    config.is_sandbox = is_sandbox

    if credentials and adapter.required_credentials:
        try:
            config.set_credentials(credentials)
        except CredentialEncryptionError as exc:
            credential_errors.append("خطا در رمزنگاری اعتبارنامه. لطفاً دوباره تلاش کنید.")
            is_active = False

    config.is_active = is_active
    config.save()

    # Build response
    if credential_errors:
        toast_msg = " | ".join(credential_errors)
        toast_type = "err"
    else:
        state = "فعال" if config.is_active else "ذخیره"
        toast_msg = f"پیکربندی {adapter.display_name} با موفقیت {state} شد"
        toast_type = "ok"

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": toast_msg, "type": toast_type},
        "settings-reload": {},
    })
    return response


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_config_toggle(request, gateway_code):
    """فعال/غیرفعال کردن سریع یک درگاه پیکربندی‌شده."""
    from apps.orders.gateways import get_adapter, GATEWAY_CHOICES
    from apps.orders.models import PaymentGatewayConfig

    store = _resolve_dashboard_store(request)

    valid_codes = [code for code, _ in GATEWAY_CHOICES]
    if gateway_code not in valid_codes:
        return HttpResponse(status=404)

    config = PaymentGatewayConfig.objects.filter(
        store=store, gateway_code=gateway_code
    ).first()

    if config is None:
        return HttpResponse(status=404)

    adapter = get_adapter(gateway_code)

    if config.is_active:
        # Deactivate — always allowed
        config.is_active = False
        config.save(update_fields=["is_active", "updated_at"])
        toast_msg = f"{adapter.display_name} غیرفعال شد"
    else:
        # Activate — only if configured
        if adapter.required_credentials:
            errors = adapter.validate_credentials(config.get_credentials())
            if errors:
                response = HttpResponse(status=204)
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "پیکربندی ناقص — ابتدا اعتبارنامه را وارد کنید", "type": "err"},
                })
                return response
        config.is_active = True
        config.save(update_fields=["is_active", "updated_at"])
        toast_msg = f"{adapter.display_name} فعال شد"

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": toast_msg, "type": "info"},
        "settings-reload": {},
    })
    return response


# ---------------------------------------------------------------- اعضای تیم (Staff / Membership)

def _dashboard_membership_or_404(store, pk):
    return get_object_or_404(StoreMembership, pk=pk, store=store)


@staff_required
@permission_required(STAFF_MANAGE)
def staff_list(request):
    memberships = list_memberships(request.store)
    return render(request, "dashboard/staff_list.html", {
        "memberships": memberships,
        "active_page": "staff",
        "assignable_roles": ASSIGNABLE_ROLES,
        "role_choices": StoreMembership.Role.choices,
    })


@staff_required
@permission_required(STAFF_MANAGE)
def staff_add(request):
    if request.method == "POST":
        phone = request.POST.get("phone", "")
        role = request.POST.get("role", "")
        try:
            add_staff_member(request.store, phone=phone, role=role, invited_by=request.user)
            messages.success(request, f"عضو تیم با موفقیت اضافه شد ({phone})")
        except MembershipError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:staff-list")

    return render(request, "dashboard/staff_form.html", {
        "active_page": "staff",
        "assignable_roles": ASSIGNABLE_ROLES,
    })


@require_POST
@staff_required
@permission_required(STAFF_MANAGE)
def staff_change_role(request, pk):
    membership = _dashboard_membership_or_404(request.store, pk)
    new_role = request.POST.get("role", "")
    try:
        change_role(membership, new_role=new_role, actor=request.user)
        messages.success(request, f"نقشِ «{membership.user.username}» به‌روزرسانی شد")
    except MembershipError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:staff-list")


@staff_required
@permission_required(STAFF_MANAGE)
def staff_revoke(request, pk):
    membership = _dashboard_membership_or_404(request.store, pk)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "عضویتِ",
            "object_name": membership.user.username,
            "consequence": "این کاربر دیگر به پنل مدیریتِ این فروشگاه دسترسی نخواهد داشت.",
            "action_label": "لغو عضویت",
            "cancel_url": reverse("dashboard:staff-list"),
            "active_page": "staff",
        })
    try:
        revoke_membership(membership, actor=request.user)
        messages.success(request, f"عضویتِ «{membership.user.username}» لغو شد")
    except MembershipError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:staff-list")


@require_POST
@staff_required
@permission_required(STAFF_MANAGE)
def staff_reactivate(request, pk):
    membership = _dashboard_membership_or_404(request.store, pk)
    try:
        reactivate_membership(membership, actor=request.user)
        messages.success(request, f"عضویتِ «{membership.user.username}» دوباره فعال شد")
    except MembershipError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:staff-list")


@staff_required
@permission_required(STAFF_MANAGE)
def staff_transfer_ownership(request, pk):
    new_owner = _dashboard_membership_or_404(request.store, pk)
    current_owner = request.store_membership

    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "انتقال مالکیتِ فروشگاه به",
            "object_name": new_owner.user.username,
            "consequence": "پس از این کار، شما دیگر مالکِ این فروشگاه نخواهید بود (نقشِ شما «مدیر» می‌شود) و امکانِ لغوِ خودکارِ این عملیات وجود ندارد.",
            "action_label": "انتقال مالکیت",
            "cancel_url": reverse("dashboard:staff-list"),
            "active_page": "staff",
        })
    try:
        transfer_ownership(request.store, current_owner=current_owner, new_owner=new_owner, actor=request.user)
        messages.success(request, f"مالکیتِ فروشگاه به «{new_owner.user.username}» منتقل شد")
    except MembershipError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:staff-list")


# ---------------------------------------------------------------- دفتر موجودی (Inventory Ledger)

INVENTORY_MOVEMENTS_PER_PAGE = 30


def _inventory_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    reason = request.GET.get("reason", "").strip()

    queryset = list_stock_movements(store)
    if q:
        queryset = queryset.filter(
            Q(product__name__icontains=q) | Q(product__sku__icontains=q)
            | Q(variant__attribute__icontains=q) | Q(variant__value__icontains=q)
        )
    if reason in StockMovement.Reason.values:
        queryset = queryset.filter(reason=reason)

    paginator = Paginator(queryset, INVENTORY_MOVEMENTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    return {
        "movements": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q,
        "selected_reason": reason,
        "reason_options": StockMovement.Reason.choices,
    }


@staff_required
@permission_required(INVENTORY_MANAGE)
def inventory_list(request):
    context = _inventory_list_context(request)
    context["active_page"] = "inventory"
    return render(request, "dashboard/inventory_list.html", context)


@staff_required
@permission_required(INVENTORY_MANAGE)
def inventory_table(request):
    return render(request, "dashboard/partials/inventory_table_inner.html", _inventory_list_context(request))


# ---------------------------------------------------------------- کدهای تخفیف (Coupons)

COUPON_FORM_FIELDS = ("code", "type", "value", "label", "min_order", "usage_limit", "expires_at", "is_active")


@staff_required
@permission_required(COUPON_VIEW, DISCOUNT_MANAGE)
def coupon_list(request):
    coupons = list_coupons(request.store)
    return render(request, "dashboard/coupon_list.html", {
        "coupons": coupons, "active_page": "coupons",
        "can_manage_coupons": membership_has_permission(request.store_membership, DISCOUNT_MANAGE),
    })


def _parse_coupon_form(request):
    data = request.POST
    fields = {
        "code": data.get("code", "").strip(),
        "type": data.get("type", Coupon.Type.PERCENT),
        "label": data.get("label", "").strip(),
        "is_active": data.get("is_active") == "on",
    }
    for key in ("value", "min_order"):
        try:
            fields[key] = Decimal(data.get(key, "0") or "0")
        except InvalidOperation:
            fields[key] = Decimal("0")
    usage_limit = data.get("usage_limit", "").strip()
    fields["usage_limit"] = int(usage_limit) if usage_limit.isdigit() else None
    expires_at_raw = data.get("expires_at", "").strip()
    fields["expires_at"] = expires_at_raw or None
    return fields


@staff_required
@permission_required(DISCOUNT_MANAGE)
def coupon_form(request, pk=None):
    coupon = get_object_or_404(Coupon, pk=pk, store=request.store) if pk else None
    field_errors = {}

    if request.method == "POST":
        fields = _parse_coupon_form(request)
        try:
            if coupon:
                update_coupon(coupon, actor=request.user, **fields)
            else:
                coupon = create_coupon(request.store, actor=request.user, **fields)
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"کد تخفیف «{coupon.code}» با موفقیت {action} شد")
            return redirect("dashboard:coupon-list")
        except CouponError as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/coupon_form.html", {
        "coupon": coupon, "active_page": "coupons", "type_choices": Coupon.Type.choices,
        "field_errors": field_errors,
    })


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def coupon_toggle(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk, store=request.store)
    toggle_coupon_active(coupon, actor=request.user)
    state = "فعال" if coupon.is_active else "غیرفعال"
    messages.info(request, f"کد تخفیف «{coupon.code}» {state} شد")
    return redirect("dashboard:coupon-list")


@staff_required
@permission_required(DISCOUNT_MANAGE)
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk, store=request.store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "کد تخفیف",
            "object_name": coupon.code,
            "cancel_url": reverse("dashboard:coupon-list"),
            "active_page": "coupons",
        })
    code = coupon.code
    delete_coupon(coupon, actor=request.user)
    messages.success(request, f"کد تخفیف «{code}» حذف شد")
    return redirect("dashboard:coupon-list")


# ---------------------------------------------------------------- گزارش رخدادها (Audit Log)

AUDIT_LOG_PER_PAGE = 40


def _audit_log_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    action_code = request.GET.get("action", "").strip()

    queryset = list_audit_events(store, q=q, action_code=action_code)
    paginator = Paginator(queryset, AUDIT_LOG_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    action_options = list(
        list_audit_events(store).order_by("action_code").values_list("action_code", flat=True).distinct()
    )

    return {
        "events": page_obj, "page_obj": page_obj, "paginator": paginator,
        "q": q, "selected_action": action_code, "action_options": action_options,
    }


@staff_required
@permission_required(AUDIT_LOG_VIEW)
def audit_log_list(request):
    context = _audit_log_list_context(request)
    context["active_page"] = "audit-log"
    return render(request, "dashboard/audit_log_list.html", context)


@staff_required
@permission_required(AUDIT_LOG_VIEW)
def audit_log_table(request):
    return render(request, "dashboard/partials/audit_log_table_inner.html", _audit_log_list_context(request))


# ---------------------------------------------------------------- صادرات (Export)

EXPORT_PERMISSION_BY_TYPE = {
    ExportJob.ExportType.PRODUCTS: IMPORT_EXPORT_VIEW,
    ExportJob.ExportType.VARIANTS: IMPORT_EXPORT_VIEW,
    ExportJob.ExportType.INVENTORY: IMPORT_EXPORT_VIEW,
    ExportJob.ExportType.CUSTOMERS: CUSTOMER_EXPORT,
    ExportJob.ExportType.ORDERS: IMPORT_EXPORT_VIEW,
}


@staff_required
@permission_required(IMPORT_EXPORT_VIEW, CUSTOMER_EXPORT)
def export_list(request):
    store = _resolve_dashboard_store(request)
    jobs = ExportJob.objects.filter(store=store).select_related("requested_by").order_by("-created_at")[:100]
    return render(request, "dashboard/export_list.html", {
        "jobs": jobs, "active_page": "exports",
        "export_types": [
            (value, label) for value, label in ExportJob.ExportType.choices
            if membership_has_permission(request.store_membership, EXPORT_PERMISSION_BY_TYPE[value])
        ],
    })


@require_POST
@staff_required
@permission_required(IMPORT_EXPORT_MANAGE, CUSTOMER_EXPORT)
def export_create(request):
    store = _resolve_dashboard_store(request)
    export_type = request.POST.get("export_type", "")
    required_permission = EXPORT_PERMISSION_BY_TYPE.get(export_type)
    if required_permission is None:
        messages.error(request, "نوعِ صادراتِ نامعتبر است.")
        return redirect("dashboard:export-list")
    # CUSTOMER_EXPORT is deliberately its own gate (PII), separate from the
    # general IMPORT_EXPORT_MANAGE that covers Product/Variant/Inventory/Order.
    if not membership_has_permission(request.store_membership, required_permission):
        return render(request, "dashboard/403.html", status=403)

    try:
        run_export(store, export_type, requested_by=request.user)
        messages.success(request, "صادرات با موفقیت انجام شد")
    except ExportError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:export-list")


@staff_required
@permission_required(IMPORT_EXPORT_VIEW, CUSTOMER_EXPORT)
def export_download(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ExportJob, pk=pk, store=store)
    required_permission = EXPORT_PERMISSION_BY_TYPE.get(job.export_type, IMPORT_EXPORT_VIEW)
    if not membership_has_permission(request.store_membership, required_permission):
        return render(request, "dashboard/403.html", status=403)
    if job.status != ExportJob.Status.COMPLETED or not job.file:
        raise Http404
    record_audit_event(
        store=store, actor=request.user, action_code="export.downloaded",
        object_type="ExportJob", object_id=str(job.pk),
        object_label=f"دانلودِ صادراتِ {job.get_export_type_display()}",
    )
    response = FileResponse(
        job.file.open("rb"), as_attachment=True,
        filename=f"{job.export_type}-{job.pk}.csv", content_type="text/csv",
    )
    return response


# ---------------------------------------------------------------- واردات (Import)

IMPORT_ROW_RESULTS_PER_PAGE = 50


@staff_required
@permission_required(IMPORT_EXPORT_VIEW)
def import_list(request):
    store = _resolve_dashboard_store(request)
    jobs = ImportJob.objects.filter(store=store).select_related("requested_by").order_by("-created_at")[:100]
    return render(request, "dashboard/import_list.html", {
        "jobs": jobs, "active_page": "imports",
        "import_types": ImportJob.ImportType.choices,
        "can_manage_imports": membership_has_permission(request.store_membership, IMPORT_EXPORT_MANAGE),
    })


@staff_required
@permission_required(IMPORT_EXPORT_MANAGE)
def import_upload(request):
    store = _resolve_dashboard_store(request)
    if request.method == "POST":
        import_type = request.POST.get("import_type", "")
        mode = request.POST.get("mode", ImportJob.Mode.UPSERT)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, "فایلی انتخاب نشده است.")
            return redirect("dashboard:import-upload")
        try:
            job = import_service.create_import_job(
                store, import_type=import_type, uploaded_file=uploaded, mode=mode,
                requested_by=request.user,
            )
            import_service.run_preview(job, actor=request.user)
        except ImportServiceError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:import-upload")
        return redirect("dashboard:import-detail", pk=job.pk)

    import_type_specs = [
        {"value": value, "label": label, "columns": ", ".join(import_service.IMPORT_COLUMNS[value])}
        for value, label in ImportJob.ImportType.choices
    ]
    return render(request, "dashboard/import_upload.html", {
        "active_page": "imports",
        "import_types": ImportJob.ImportType.choices,
        "modes": ImportJob.Mode.choices,
        "import_type_specs": import_type_specs,
    })


def _import_detail_context(request, job):
    row_results = job.row_results.all().order_by("row_number")
    paginator = Paginator(row_results, IMPORT_ROW_RESULTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", "1"))
    return {
        "job": job, "active_page": "imports",
        "row_results": page_obj, "page_obj": page_obj, "paginator": paginator,
        "can_manage_imports": membership_has_permission(request.store_membership, IMPORT_EXPORT_MANAGE),
    }


@staff_required
@permission_required(IMPORT_EXPORT_VIEW)
def import_detail(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ImportJob, pk=pk, store=store)
    return render(request, "dashboard/import_detail.html", _import_detail_context(request, job))


@require_POST
@staff_required
@permission_required(IMPORT_EXPORT_MANAGE)
def import_execute(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ImportJob, pk=pk, store=store)
    try:
        import_service.run_execution(job, actor=request.user)
        messages.success(
            request,
            f"واردات انجام شد — {job.created_rows} ایجاد، {job.updated_rows} به‌روزرسانی، "
            f"{job.skipped_rows} ردشده، {job.failed_rows} ناموفق",
        )
    except ImportServiceError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:import-detail", pk=job.pk)


@require_POST
@staff_required
@permission_required(IMPORT_EXPORT_MANAGE)
def import_cancel(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ImportJob, pk=pk, store=store)
    try:
        import_service.cancel_import_job(job, actor=request.user)
        messages.info(request, "واردات لغو شد")
    except ImportServiceError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:import-detail", pk=job.pk)


@staff_required
@permission_required(IMPORT_EXPORT_VIEW)
def import_download_source(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ImportJob, pk=pk, store=store)
    if not job.source_file:
        raise Http404
    record_audit_event(
        store=store, actor=request.user, action_code="import.source_downloaded",
        object_type="ImportJob", object_id=str(job.pk), object_label=job.original_filename,
    )
    return FileResponse(
        job.source_file.open("rb"), as_attachment=True,
        filename=f"{job.import_type}-source-{job.pk}.csv", content_type="text/csv",
    )


@staff_required
@permission_required(IMPORT_EXPORT_VIEW)
def import_download_errors(request, pk):
    store = _resolve_dashboard_store(request)
    job = get_object_or_404(ImportJob, pk=pk, store=store)
    if not job.error_report_file:
        raise Http404
    record_audit_event(
        store=store, actor=request.user, action_code="import.error_report_downloaded",
        object_type="ImportJob", object_id=str(job.pk), object_label=job.original_filename,
    )
    return FileResponse(
        job.error_report_file.open("rb"), as_attachment=True,
        filename=f"{job.import_type}-errors-{job.pk}.csv", content_type="text/csv",
    )


@staff_required
@permission_required(IMPORT_EXPORT_VIEW)
def import_template(request, import_type):
    _resolve_dashboard_store(request)
    try:
        content = import_service.build_template_csv(import_type)
    except ImportServiceError:
        raise Http404
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{import_type}-template.csv"'
    return response


# ---------------------------------------------------------------- استرداد (Refund)

@staff_required
@permission_required(REFUND_VIEW, REFUND_MANAGE)
def order_refund_form(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(Order.objects.select_related("customer"), code=code, store=store)
    items = list(order.items.select_related("product", "variant"))

    if request.method == "POST":
        if not membership_has_permission(request.store_membership, REFUND_MANAGE):
            return render(request, "dashboard/403.html", status=403)

        line_requests = []
        for item in items:
            raw_qty = request.POST.get(f"quantity_{item.pk}", "0").strip()
            quantity = int(raw_qty) if raw_qty.isdigit() else 0
            if quantity > 0:
                line_requests.append({"order_item_id": item.pk, "quantity": quantity})

        shipping_raw = request.POST.get("shipping_amount", "0").strip()
        try:
            shipping_amount = Decimal(shipping_raw or "0")
        except InvalidOperation:
            shipping_amount = Decimal("0")

        reason = request.POST.get("reason", Refund.Reason.CUSTOMER_REQUEST)
        merchant_note = request.POST.get("merchant_note", "").strip()
        restock = request.POST.get("restock") == "on"

        if not line_requests and shipping_amount <= 0:
            messages.error(request, "حداقل یک قلم یا مبلغِ ارسال باید برای استرداد انتخاب شود")
        else:
            try:
                refund = execute_order_refund(
                    order, store=store, actor=request.user, line_requests=line_requests,
                    shipping_amount=shipping_amount, reason=reason, merchant_note=merchant_note,
                    restock=restock,
                )
                messages.success(request, f"استرداد به مبلغِ {refund.approved_amount} تومان ثبت شد")
                return redirect("dashboard:order-detail", code=order.code)
            except RefundError as exc:
                messages.error(request, str(exc))

    return render(request, "dashboard/order_refund_form.html", {
        "order": order, "items": items, "active_page": "orders",
        "refundable_amount": refundable_amount(order),
        "max_shipping": max(Decimal("0"), order.shipping_cost - sum(
            (r.shipping_refund_amount for r in order.refunds.exclude(
                status__in=(Refund.Status.FAILED, Refund.Status.CANCELLED)
            )), Decimal("0")
        )),
        "reason_choices": Refund.Reason.choices,
    })


# ---------------------------------------------------------------- مرجوعی‌ها (Returns)

RETURN_PER_PAGE = 20


def _return_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    queryset = ReturnRequest.objects.filter(store=store).select_related("order", "customer").order_by("-created_at")
    if status:
        queryset = queryset.filter(status=status)
    if q:
        queryset = queryset.filter(
            Q(return_number__icontains=q) | Q(order__code__icontains=q) | Q(customer__full_name__icontains=q)
        )

    paginator = Paginator(queryset, RETURN_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    return {
        "returns": page_obj, "page_obj": page_obj, "paginator": paginator,
        "q": q, "selected_status": status, "status_choices": ReturnRequest.Status.choices,
    }


@staff_required
@permission_required(RETURN_VIEW, RETURN_MANAGE)
def return_list(request):
    context = _return_list_context(request)
    context["active_page"] = "returns"
    return render(request, "dashboard/return_list.html", context)


@staff_required
@permission_required(RETURN_MANAGE)
def return_create(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(Order.objects.select_related("customer"), code=code, store=store)
    items = list(order.items.select_related("product", "variant"))

    if request.method == "POST":
        line_requests = []
        for item in items:
            raw_qty = request.POST.get(f"quantity_{item.pk}", "0").strip()
            quantity = int(raw_qty) if raw_qty.isdigit() else 0
            if quantity > 0:
                line_requests.append({"order_item_id": item.pk, "quantity": quantity})

        reason = request.POST.get("reason", ReturnRequest.Reason.CUSTOMER_REQUEST)
        explanation = request.POST.get("customer_explanation", "").strip()

        try:
            return_request = create_return_request(
                order, store=store, customer=order.customer, reason=reason,
                line_requests=line_requests, customer_explanation=explanation, actor=request.user,
            )
            messages.success(request, f"درخواستِ مرجوعیِ «{return_request.return_number}» ثبت شد")
            return redirect("dashboard:return-detail", pk=return_request.pk)
        except ReturnError as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/return_form.html", {
        "order": order, "items": items, "active_page": "orders",
        "reason_choices": ReturnRequest.Reason.choices,
    })


@staff_required
@permission_required(RETURN_VIEW, RETURN_MANAGE)
def return_detail(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(
        ReturnRequest.objects.select_related("order", "customer", "refund"), pk=pk, store=store,
    )
    return render(request, "dashboard/return_detail.html", {
        "return_request": return_request,
        "items": return_request.items.select_related("order_item"),
        "warehouses": Warehouse.objects.filter(store=store, is_active=True),
        "active_page": "returns",
        "can_manage_returns": membership_has_permission(request.store_membership, RETURN_MANAGE),
    })


@require_POST
@staff_required
@permission_required(RETURN_MANAGE)
def return_review(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    try:
        review_return_request(return_request, store=store, actor=request.user)
        messages.success(request, "درخواست به حالتِ «در حال بررسی» منتقل شد")
    except ReturnError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


@require_POST
@staff_required
@permission_required(RETURN_MANAGE)
def return_approve(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    approved_quantities = {}
    for item in return_request.items.all():
        raw = request.POST.get(f"approved_{item.pk}", "").strip()
        if raw.isdigit():
            approved_quantities[item.pk] = int(raw)
    try:
        approve_return_request(
            return_request, store=store, actor=request.user, approved_quantities=approved_quantities,
            note=request.POST.get("note", "").strip(),
        )
        messages.success(request, "مرجوعی تأیید شد")
    except ReturnError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


@staff_required
@permission_required(RETURN_MANAGE)
def return_reject(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "درخواستِ مرجوعیِ", "object_name": return_request.return_number,
            "action_label": "رد مرجوعی", "cancel_url": reverse("dashboard:return-detail", args=[pk]),
            "active_page": "returns",
        })
    try:
        reject_return_request(
            return_request, store=store, actor=request.user,
            rejection_reason=request.POST.get("rejection_reason", "").strip(),
        )
        messages.success(request, "مرجوعی رد شد")
    except ReturnError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


@require_POST
@staff_required
@permission_required(RETURN_MANAGE)
def return_receive(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    received_quantities = {}
    for item in return_request.items.all():
        raw = request.POST.get(f"received_{item.pk}", "").strip()
        if raw.isdigit():
            received_quantities[item.pk] = int(raw)
    try:
        mark_return_received(return_request, store=store, actor=request.user, received_quantities=received_quantities)
        messages.success(request, "دریافتِ کالا ثبت شد")
    except ReturnError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


@require_POST
@staff_required
@permission_required(RETURN_MANAGE)
def return_inspect(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    inspections = []
    for item in return_request.items.all():
        prefix = f"item_{item.pk}_"
        if request.POST.get(f"{prefix}present") != "on":
            continue
        restock_warehouse_raw = request.POST.get(f"{prefix}restock_warehouse", "").strip()
        inspections.append({
            "item_id": item.pk,
            "condition": request.POST.get(f"{prefix}condition", ""),
            "is_restockable": request.POST.get(f"{prefix}restockable") == "on",
            "merchant_resolution": request.POST.get(f"{prefix}resolution", ""),
            "rejection_reason": request.POST.get(f"{prefix}rejection_reason", ""),
            "restock_warehouse_id": restock_warehouse_raw or None,
        })
    try:
        inspect_return_items(
            return_request, store=store, actor=request.user, inspections=inspections,
            inspection_result=request.POST.get("inspection_result", "").strip(),
        )
        messages.success(request, "نتیجه‌ی بازرسی ثبت شد")
    except ReturnError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


@require_POST
@staff_required
@permission_required(RETURN_MANAGE)
def return_complete(request, pk):
    store = _resolve_dashboard_store(request)
    return_request = get_object_or_404(ReturnRequest, pk=pk, store=store)
    try:
        complete_return(return_request, store=store, actor=request.user)
        messages.success(request, "مرجوعی تکمیل شد")
    except (ReturnError, RefundError) as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:return-detail", pk=pk)


# ---------------------------------------------------------------- انبارها (Warehouses)

WAREHOUSE_FORM_FIELDS = (
    "name", "code", "address", "province", "city", "postal_code",
    "contact_name", "contact_phone", "is_active", "is_pickup_location", "fulfillment_priority",
)


@staff_required
@permission_required(WAREHOUSE_VIEW, WAREHOUSE_MANAGE)
def warehouse_list(request):
    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/warehouse_list.html", {
        "warehouses": list_warehouses(store), "active_page": "warehouses",
        "can_manage_warehouses": membership_has_permission(request.store_membership, WAREHOUSE_MANAGE),
    })


def _parse_warehouse_form(request):
    data = request.POST
    fields = {
        "name": data.get("name", "").strip(),
        "code": data.get("code", "").strip(),
        "address": data.get("address", "").strip(),
        "province": data.get("province", "").strip(),
        "city": data.get("city", "").strip(),
        "postal_code": data.get("postal_code", "").strip(),
        "contact_name": data.get("contact_name", "").strip(),
        "contact_phone": data.get("contact_phone", "").strip(),
        "is_active": data.get("is_active") == "on",
        "is_pickup_location": data.get("is_pickup_location") == "on",
    }
    priority = data.get("fulfillment_priority", "").strip()
    fields["fulfillment_priority"] = int(priority) if priority.isdigit() else 0
    if data.get("is_default") == "on":
        fields["is_default"] = True
    return fields


@staff_required
@permission_required(WAREHOUSE_MANAGE)
def warehouse_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, store=store) if pk else None

    if request.method == "POST":
        fields = _parse_warehouse_form(request)
        try:
            if warehouse:
                update_warehouse(warehouse, actor=request.user, **fields)
            else:
                warehouse = create_warehouse(store, actor=request.user, **fields)
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"انبارِ «{warehouse.name}» با موفقیت {action} شد")
            return redirect("dashboard:warehouse-list")
        except WarehouseError as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/warehouse_form.html", {
        "warehouse": warehouse, "active_page": "warehouses",
    })


@require_POST
@staff_required
@permission_required(WAREHOUSE_MANAGE)
def warehouse_set_default(request, pk):
    store = _resolve_dashboard_store(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, store=store)
    try:
        set_default_warehouse(warehouse, actor=request.user)
        messages.success(request, f"انبارِ «{warehouse.name}» پیش‌فرض شد")
    except WarehouseError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:warehouse-list")


@require_POST
@staff_required
@permission_required(WAREHOUSE_MANAGE)
def warehouse_archive(request, pk):
    store = _resolve_dashboard_store(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, store=store)
    try:
        archive_warehouse(warehouse, actor=request.user)
        messages.info(request, f"انبارِ «{warehouse.name}» آرشیو شد")
    except WarehouseError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:warehouse-list")


@staff_required
@permission_required(WAREHOUSE_VIEW, WAREHOUSE_MANAGE)
def warehouse_detail(request, pk):
    store = _resolve_dashboard_store(request)
    warehouse = get_object_or_404(Warehouse, pk=pk, store=store)
    balances = (
        WarehouseInventory.objects.filter(store=store, warehouse=warehouse)
        .select_related("product", "variant").order_by("product__name")
    )
    return render(request, "dashboard/warehouse_detail.html", {
        "warehouse": warehouse, "balances": balances, "active_page": "warehouses",
    })


# ---------------------------------------------------------------- رزروهای موجودی (Reservations)

@staff_required
@permission_required(RESERVATION_VIEW)
def reservation_list(request):
    store = _resolve_dashboard_store(request)
    status = request.GET.get("status", "").strip()
    queryset = list_reservations(store, status=status)
    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get("page", "1"))
    return render(request, "dashboard/reservation_list.html", {
        "reservations": page_obj, "page_obj": page_obj, "paginator": paginator,
        "selected_status": status, "status_choices": InventoryReservation.Status.choices,
        "active_page": "reservations",
        "can_manage_reservations": membership_has_permission(request.store_membership, WAREHOUSE_MANAGE),
    })


@require_POST
@staff_required
@permission_required(WAREHOUSE_MANAGE)
def reservation_release(request, pk):
    store = _resolve_dashboard_store(request)
    reservation = get_object_or_404(InventoryReservation, pk=pk, store=store)
    try:
        release_inventory_reservation(reservation, actor=request.user)
        messages.success(request, "رزرو آزاد شد")
    except ReservationError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:reservation-list")


# ---------------------------------------------------------------- انتقالِ انبار (Warehouse Transfers)

@staff_required
@permission_required(TRANSFER_VIEW, TRANSFER_MANAGE)
def transfer_list(request):
    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/transfer_list.html", {
        "transfers": list_transfers(store), "active_page": "transfers",
        "can_manage_transfers": membership_has_permission(request.store_membership, TRANSFER_MANAGE),
    })


@staff_required
@permission_required(TRANSFER_VIEW, TRANSFER_MANAGE)
def transfer_detail(request, pk):
    store = _resolve_dashboard_store(request)
    transfer_obj = get_object_or_404(
        WarehouseTransfer.objects.select_related("source_warehouse", "destination_warehouse"), pk=pk, store=store,
    )
    return render(request, "dashboard/transfer_detail.html", {
        "transfer": transfer_obj,
        "items": transfer_obj.items.select_related("product", "variant"),
        "active_page": "transfers",
        "can_manage_transfers": membership_has_permission(request.store_membership, TRANSFER_MANAGE),
    })


@staff_required
@permission_required(TRANSFER_MANAGE)
def transfer_form(request):
    store = _resolve_dashboard_store(request)
    warehouses = list_warehouses(store)
    products = Product.objects.filter(store=store, status=Product.Status.ACTIVE).order_by("name")[:500]

    if request.method == "POST":
        source_id = request.POST.get("source_warehouse")
        destination_id = request.POST.get("destination_warehouse")
        note = request.POST.get("note", "").strip()

        source_warehouse = warehouses.filter(pk=source_id).first()
        destination_warehouse = warehouses.filter(pk=destination_id).first()

        items = []
        for product in products:
            raw_qty = request.POST.get(f"quantity_{product.pk}", "0").strip()
            quantity = int(raw_qty) if raw_qty.isdigit() else 0
            if quantity > 0:
                items.append({"product": product, "quantity": quantity})

        if source_warehouse is None or destination_warehouse is None:
            messages.error(request, "انبارِ مبدأ/مقصد نامعتبر است")
        else:
            try:
                transfer_obj = create_transfer(
                    store, source_warehouse=source_warehouse, destination_warehouse=destination_warehouse,
                    items=items, note=note, actor=request.user,
                )
                messages.success(request, f"انتقالِ «{transfer_obj.transfer_number}» ایجاد شد")
                return redirect("dashboard:transfer-detail", pk=transfer_obj.pk)
            except TransferError as exc:
                messages.error(request, str(exc))

    return render(request, "dashboard/transfer_form.html", {
        "warehouses": warehouses, "products": products, "active_page": "transfers",
    })


@require_POST
@staff_required
@permission_required(TRANSFER_MANAGE)
def transfer_request(request, pk):
    store = _resolve_dashboard_store(request)
    transfer_obj = get_object_or_404(WarehouseTransfer, pk=pk, store=store)
    try:
        request_transfer(transfer_obj, actor=request.user)
        messages.success(request, "انتقال درخواست شد")
    except TransferError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:transfer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(TRANSFER_MANAGE)
def transfer_ship(request, pk):
    store = _resolve_dashboard_store(request)
    transfer_obj = get_object_or_404(WarehouseTransfer, pk=pk, store=store)
    try:
        ship_transfer(transfer_obj, actor=request.user)
        messages.success(request, "انتقال ارسال شد")
    except TransferError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:transfer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(TRANSFER_MANAGE)
def transfer_receive(request, pk):
    store = _resolve_dashboard_store(request)
    transfer_obj = get_object_or_404(WarehouseTransfer, pk=pk, store=store)
    try:
        receive_transfer(transfer_obj, actor=request.user)
        messages.success(request, "انتقال دریافت شد")
    except TransferError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:transfer-detail", pk=pk)


@require_POST
@staff_required
@permission_required(TRANSFER_MANAGE)
def transfer_cancel(request, pk):
    store = _resolve_dashboard_store(request)
    transfer_obj = get_object_or_404(WarehouseTransfer, pk=pk, store=store)
    try:
        cancel_transfer(transfer_obj, actor=request.user)
        messages.info(request, "انتقال لغو شد")
    except TransferError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:transfer-detail", pk=pk)


# ---------------------------------------------------------------- مناطقِ ارسال (Shipping Zones)

def _parse_str_list(raw: str) -> list:
    return [line.strip() for line in raw.replace(",", "\n").split("\n") if line.strip()]


@staff_required
@permission_required(SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE)
def shipping_zone_list(request):
    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/shipping_zone_list.html", {
        "zones": ShippingZone.objects.filter(store=store), "active_page": "shipping",
        "can_manage_shipping": membership_has_permission(request.store_membership, SHIPPING_SETTINGS_MANAGE),
    })


def _parse_shipping_zone_form(request):
    data = request.POST
    return {
        "name": data.get("name", "").strip(),
        "code": data.get("code", "").strip(),
        "is_active": data.get("is_active") == "on",
        "priority": int(data.get("priority", "0") or "0"),
        "provinces": _parse_str_list(data.get("provinces", "")),
        "cities": _parse_str_list(data.get("cities", "")),
        "postal_codes": _parse_str_list(data.get("postal_codes", "")),
        "excluded_provinces": _parse_str_list(data.get("excluded_provinces", "")),
        "excluded_cities": _parse_str_list(data.get("excluded_cities", "")),
        "is_fallback": data.get("is_fallback") == "on",
    }


@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_zone_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    zone = get_object_or_404(ShippingZone, pk=pk, store=store) if pk else None

    if request.method == "POST":
        fields = _parse_shipping_zone_form(request)
        try:
            if fields["is_fallback"]:
                ShippingZone.objects.filter(store=store, is_fallback=True).exclude(pk=zone.pk if zone else None).update(is_fallback=False)
            if zone:
                for key, value in fields.items():
                    setattr(zone, key, value)
            else:
                zone = ShippingZone(store=store, **fields)
            zone.full_clean()
            zone.save()
            record_audit_event(
                store=store, actor=request.user,
                action_code="shipping_zone.updated" if pk else "shipping_zone.created",
                object_type="ShippingZone", object_id=zone.pk, object_label=zone.name,
            )
            messages.success(request, f"منطقه‌ی «{zone.name}» ذخیره شد")
            return redirect("dashboard:shipping-zone-list")
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/shipping_zone_form.html", {"zone": zone, "active_page": "shipping"})


@require_POST
@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_zone_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    zone = get_object_or_404(ShippingZone, pk=pk, store=store)
    zone.is_active = not zone.is_active
    zone.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"منطقه‌ی «{zone.name}» {'فعال' if zone.is_active else 'غیرفعال'} شد")
    return redirect("dashboard:shipping-zone-list")


# ---------------------------------------------------------------- روش‌های ارسال (Shipping Methods)

@staff_required
@permission_required(SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE)
def shipping_method_list(request):
    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/shipping_method_list.html", {
        "methods": ShippingMethod.objects.filter(store=store).select_related("zone", "pickup_warehouse"),
        "active_page": "shipping",
        "can_manage_shipping": membership_has_permission(request.store_membership, SHIPPING_SETTINGS_MANAGE),
    })


def _parse_shipping_method_form(request, store):
    data = request.POST
    zone_id = data.get("zone", "").strip()
    pickup_warehouse_id = data.get("pickup_warehouse", "").strip()
    fields = {
        "name": data.get("name", "").strip(),
        "slug": data.get("slug", "").strip(),
        "description": data.get("description", "").strip(),
        "method_type": data.get("method_type", ShippingMethod.MethodType.FLAT_RATE),
        "icon": data.get("icon", "").strip(),
        "is_active": data.get("is_active") == "on",
        "is_pickup": data.get("is_pickup") == "on",
        "cod_eligible": data.get("cod_eligible") == "on",
        "zone": _lookup_store_scoped(ShippingZone, zone_id, store),
        "pickup_warehouse": _lookup_store_scoped(Warehouse, pickup_warehouse_id, store),
    }
    for key in ("cost", "free_over"):
        try:
            fields[key] = Decimal(data.get(key, "0") or "0")
        except InvalidOperation:
            fields[key] = Decimal("0")
    fields["display_order"] = int(data.get("display_order", "0") or "0")
    min_days = data.get("min_delivery_days", "").strip()
    max_days = data.get("max_delivery_days", "").strip()
    fields["min_delivery_days"] = int(min_days) if min_days.isdigit() else None
    fields["max_delivery_days"] = int(max_days) if max_days.isdigit() else None
    return fields


def _lookup_store_scoped(model, raw_id, store):
    if not raw_id:
        return None
    return model.objects.filter(pk=raw_id, store=store).first()


@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_method_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=pk, store=store) if pk else None

    if request.method == "POST":
        fields = _parse_shipping_method_form(request, store)
        try:
            if method:
                for key, value in fields.items():
                    setattr(method, key, value)
            else:
                method = ShippingMethod(store=store, **fields)
            method.full_clean()
            method.save()
            record_audit_event(
                store=store, actor=request.user,
                action_code="shipping_method.updated" if pk else "shipping_method.created",
                object_type="ShippingMethod", object_id=method.pk, object_label=method.name,
            )
            messages.success(request, f"روشِ ارسالِ «{method.name}» ذخیره شد")
            return redirect("dashboard:shipping-method-list")
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/shipping_method_form.html", {
        "method": method, "active_page": "shipping",
        "zones": ShippingZone.objects.filter(store=store, is_active=True),
        "warehouses": Warehouse.objects.filter(store=store, is_pickup_location=True),
        "method_type_choices": ShippingMethod.MethodType.choices,
    })


@require_POST
@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_method_archive(request, pk):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=pk, store=store)
    method.is_active = not method.is_active
    method.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"روشِ ارسالِ «{method.name}» {'فعال' if method.is_active else 'غیرفعال'} شد")
    return redirect("dashboard:shipping-method-list")


# ---------------------------------------------------------------- راه‌اندازیِ سادهٔ ارسال (Onboarding)

@staff_required
@permission_required(SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE)
def shipping_setup(request):
    """صفحه‌ی سادهٔ راه‌اندازیِ ارسال — دقیقاً همان مدلِ ``ShippingMethod``ی
    که صفحه‌ی پیشرفته (``shipping-method-list``، مناطق، قواعدِ نرخ) هم
    استفاده می‌کند، فقط با مجموعه‌ی محدودی از فیلدها: نام، فعال/غیرفعال،
    پرداخت‌درمحل، هزینه (فقط وقتی پرداخت‌درمحل نیست)، آستانه‌ی ارسالِ رایگانِ
    اختیاری. صفحه‌ی پیشرفته برای مرچنت‌هایی که به منطقه‌بندی/جدولِ نرخ نیاز
    دارند دست‌نخورده و همچنان در دسترس می‌ماند."""
    store = _resolve_dashboard_store(request)
    ensure_default_shipping_methods(store)
    return render(request, "dashboard/shipping_setup.html", {
        "methods": ShippingMethod.objects.filter(store=store).order_by("display_order", "name"),
        "active_page": "shipping",
        "can_manage_shipping": membership_has_permission(request.store_membership, SHIPPING_SETTINGS_MANAGE),
    })


@require_POST
@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_method_simple_update(request, pk):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=pk, store=store)

    method.is_active = request.POST.get("is_active") == "on"
    method.cod_eligible = request.POST.get("cod_eligible") == "on" and not method.is_pickup

    if method.is_pickup:
        method.cost = Decimal("0")
    elif method.cod_eligible:
        method.cost = Decimal("0")
    else:
        raw_cost = request.POST.get("cost", "").strip()
        try:
            cost = Decimal(raw_cost) if raw_cost else Decimal("0")
        except InvalidOperation:
            messages.error(request, "مبلغِ هزینه‌ی ارسال نامعتبر است")
            return redirect("dashboard:shipping-setup")
        if cost < 0:
            messages.error(request, "هزینه‌ی ارسال نمی‌تواند منفی باشد")
            return redirect("dashboard:shipping-setup")
        method.cost = cost

    raw_free_over = request.POST.get("free_over", "").strip()
    if raw_free_over:
        try:
            free_over = Decimal(raw_free_over)
        except InvalidOperation:
            messages.error(request, "مبلغِ آستانه‌ی ارسالِ رایگان نامعتبر است")
            return redirect("dashboard:shipping-setup")
        if free_over < 0:
            messages.error(request, "آستانه‌ی ارسالِ رایگان نمی‌تواند منفی باشد")
            return redirect("dashboard:shipping-setup")
        method.free_over = free_over
    else:
        method.free_over = None

    try:
        method.full_clean()
        method.save()
    except (ValidationError, IntegrityError) as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:shipping-setup")

    record_audit_event(
        store=store, actor=request.user, action_code="shipping_method.updated",
        object_type="ShippingMethod", object_id=method.pk, object_label=method.name,
    )
    messages.success(request, f"روشِ ارسالِ «{method.name}» ذخیره شد")
    return redirect("dashboard:shipping-setup")


@staff_required
@permission_required(SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE)
def shipping_rate_rule_list(request, method_id):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=method_id, store=store)
    return render(request, "dashboard/shipping_rate_rule_list.html", {
        "method": method, "rules": method.rate_rules.all(), "active_page": "shipping",
        "can_manage_shipping": membership_has_permission(request.store_membership, SHIPPING_SETTINGS_MANAGE),
    })


def _parse_rate_rule_form(request):
    data = request.POST
    fields = {
        "name": data.get("name", "").strip(),
        "priority": int(data.get("priority", "0") or "0"),
        "is_active": data.get("is_active") == "on",
    }
    for key in ("min_subtotal", "max_subtotal", "rate_amount", "free_over"):
        raw = data.get(key, "").strip()
        if key == "rate_amount":
            fields[key] = Decimal(raw) if raw else Decimal("0")
        else:
            fields[key] = Decimal(raw) if raw else None
    for key in ("min_weight_grams", "max_weight_grams"):
        raw = data.get(key, "").strip()
        fields[key] = int(raw) if raw.isdigit() else None
    return fields


@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_rate_rule_form(request, method_id, pk=None):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=method_id, store=store)
    rule = get_object_or_404(ShippingRateRule, pk=pk, method=method) if pk else None

    if request.method == "POST":
        fields = _parse_rate_rule_form(request)
        try:
            if rule:
                for key, value in fields.items():
                    setattr(rule, key, value)
            else:
                rule = ShippingRateRule(method=method, **fields)
            rule.full_clean()
            rule.save()
            messages.success(request, f"قاعده‌ی «{rule.name}» ذخیره شد")
            return redirect("dashboard:shipping-rate-rule-list", method_id=method.pk)
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/shipping_rate_rule_form.html", {
        "method": method, "rule": rule, "active_page": "shipping",
    })


@require_POST
@staff_required
@permission_required(SHIPPING_SETTINGS_MANAGE)
def shipping_rate_rule_archive(request, method_id, pk):
    store = _resolve_dashboard_store(request)
    method = get_object_or_404(ShippingMethod, pk=method_id, store=store)
    rule = get_object_or_404(ShippingRateRule, pk=pk, method=method)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"قاعده‌ی «{rule.name}» {'فعال' if rule.is_active else 'غیرفعال'} شد")
    return redirect("dashboard:shipping-rate-rule-list", method_id=method.pk)


# ---------------------------------------------------------------- تنظیماتِ مالیات (Tax Settings)

@staff_required
@permission_required(TAX_SETTINGS_VIEW, TAX_SETTINGS_MANAGE)
def tax_settings(request):
    store = _resolve_dashboard_store(request)
    settings_row = ShopSettings.load(store=store)

    if request.method == "POST" and not membership_has_permission(request.store_membership, TAX_SETTINGS_MANAGE):
        return render(request, "dashboard/403.html", status=403)

    if request.method == "POST":
        from django.utils import timezone

        settings_row.tax_enabled = request.POST.get("tax_enabled") == "on"
        settings_row.prices_include_tax = request.POST.get("prices_include_tax") == "on"
        settings_row.shipping_taxable = request.POST.get("shipping_taxable") == "on"
        settings_row.tax_rounding_policy = request.POST.get(
            "tax_rounding_policy", ShopSettings.TaxRoundingPolicy.ON_TOTAL,
        )
        default_class_id = request.POST.get("default_tax_class", "").strip()
        settings_row.default_tax_class = (
            TaxClass.objects.filter(pk=default_class_id, store=store).first() if default_class_id else None
        )
        # مدیر با ذخیره‌ی این فرم (هر کدام از دو گزینه‌ی «مالیات ندارم»/«مالیات
        # دارم») صراحتاً تصمیمِ مالیاتی‌اش را اعلام کرده — این تنها سیگنالِ
        # تکمیلِ مرحله‌ی چک‌لیست است، نه ``tax_enabled`` به‌تنهایی (که
        # پیش‌فرضش True است و بدونِ این فیلد نمی‌تواند «هنوز انتخاب نشده» را
        # از «صراحتاً روشن نگه‌داشته شده» تشخیص دهد).
        settings_row.tax_setup_confirmed_at = timezone.now()
        settings_row.save(update_fields=[
            "tax_enabled", "prices_include_tax", "shipping_taxable", "tax_rounding_policy", "default_tax_class",
            "tax_setup_confirmed_at",
        ])
        record_audit_event(
            store=store, actor=request.user, action_code="tax_settings.updated",
            object_type="ShopSettings", object_id=settings_row.pk, object_label="تنظیماتِ مالیات",
        )
        messages.success(request, "تنظیماتِ مالیات ذخیره شد")
        return redirect("dashboard:tax-settings")

    return render(request, "dashboard/tax_settings.html", {
        "settings": settings_row, "active_page": "tax",
        "tax_classes": TaxClass.objects.filter(store=store, is_active=True),
        "rounding_choices": ShopSettings.TaxRoundingPolicy.choices,
    })


# ---------------------------------------------------------------- دسته‌های مالیاتی (Tax Classes)

@staff_required
@permission_required(TAX_SETTINGS_VIEW, TAX_SETTINGS_MANAGE)
def tax_class_list(request):
    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/tax_class_list.html", {
        "tax_classes": TaxClass.objects.filter(store=store), "active_page": "tax",
        "can_manage_tax": membership_has_permission(request.store_membership, TAX_SETTINGS_MANAGE),
    })


@staff_required
@permission_required(TAX_SETTINGS_MANAGE)
def tax_class_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    tax_class = get_object_or_404(TaxClass, pk=pk, store=store) if pk else None

    if request.method == "POST":
        data = request.POST
        fields = {
            "name": data.get("name", "").strip(),
            "code": data.get("code", "").strip(),
            "description": data.get("description", "").strip(),
            "is_active": data.get("is_active") == "on",
            "is_default": data.get("is_default") == "on",
        }
        try:
            if fields["is_default"]:
                TaxClass.objects.filter(store=store, is_default=True).exclude(
                    pk=tax_class.pk if tax_class else None
                ).update(is_default=False)
            if tax_class:
                for key, value in fields.items():
                    setattr(tax_class, key, value)
            else:
                tax_class = TaxClass(store=store, **fields)
            tax_class.full_clean()
            tax_class.save()
            record_audit_event(
                store=store, actor=request.user,
                action_code="tax_class.updated" if pk else "tax_class.created",
                object_type="TaxClass", object_id=tax_class.pk, object_label=tax_class.name,
            )
            messages.success(request, f"دسته‌ی مالیاتیِ «{tax_class.name}» ذخیره شد")
            return redirect("dashboard:tax-class-list")
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/tax_class_form.html", {"tax_class": tax_class, "active_page": "tax"})


@require_POST
@staff_required
@permission_required(TAX_SETTINGS_MANAGE)
def tax_class_archive(request, pk):
    store = _resolve_dashboard_store(request)
    tax_class = get_object_or_404(TaxClass, pk=pk, store=store)
    tax_class.is_active = not tax_class.is_active
    tax_class.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"دسته‌ی مالیاتیِ «{tax_class.name}» {'فعال' if tax_class.is_active else 'غیرفعال'} شد")
    return redirect("dashboard:tax-class-list")


@staff_required
@permission_required(TAX_SETTINGS_VIEW, TAX_SETTINGS_MANAGE)
def tax_rate_list(request, tax_class_id):
    store = _resolve_dashboard_store(request)
    tax_class = get_object_or_404(TaxClass, pk=tax_class_id, store=store)
    return render(request, "dashboard/tax_rate_list.html", {
        "tax_class": tax_class, "rates": tax_class.rates.all(), "active_page": "tax",
        "can_manage_tax": membership_has_permission(request.store_membership, TAX_SETTINGS_MANAGE),
    })


@staff_required
@permission_required(TAX_SETTINGS_MANAGE)
def tax_rate_form(request, tax_class_id, pk=None):
    store = _resolve_dashboard_store(request)
    tax_class = get_object_or_404(TaxClass, pk=tax_class_id, store=store)
    rate = get_object_or_404(TaxRate, pk=pk, tax_class=tax_class) if pk else None

    if request.method == "POST":
        data = request.POST
        applies_raw = data.get("applies_to_shipping", "")
        fields = {
            "province": data.get("province", "").strip(),
            "priority": int(data.get("priority", "0") or "0"),
            "is_active": data.get("is_active") == "on",
            "applies_to_shipping": {"true": True, "false": False}.get(applies_raw),
        }
        try:
            fields["rate_percent"] = Decimal(data.get("rate_percent", "0") or "0")
        except InvalidOperation:
            fields["rate_percent"] = Decimal("0")
        try:
            if rate:
                for key, value in fields.items():
                    setattr(rate, key, value)
            else:
                rate = TaxRate(store=store, tax_class=tax_class, **fields)
            rate.full_clean()
            rate.save()
            record_audit_event(
                store=store, actor=request.user,
                action_code="tax_rate.updated" if pk else "tax_rate.created",
                object_type="TaxRate", object_id=rate.pk, object_label=f"{tax_class.name} — {rate.rate_percent}٪",
            )
            messages.success(request, "نرخِ مالیات ذخیره شد")
            return redirect("dashboard:tax-rate-list", tax_class_id=tax_class.pk)
        except (ValidationError, IntegrityError) as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/tax_rate_form.html", {
        "tax_class": tax_class, "rate": rate, "active_page": "tax",
    })


@require_POST
@staff_required
@permission_required(TAX_SETTINGS_MANAGE)
def tax_rate_archive(request, tax_class_id, pk):
    store = _resolve_dashboard_store(request)
    tax_class = get_object_or_404(TaxClass, pk=tax_class_id, store=store)
    rate = get_object_or_404(TaxRate, pk=pk, tax_class=tax_class)
    rate.is_active = not rate.is_active
    rate.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"نرخِ مالیات {'فعال' if rate.is_active else 'غیرفعال'} شد")
    return redirect("dashboard:tax-rate-list", tax_class_id=tax_class.pk)


# ================================================================ اشتراک و صورتحساب
#
# نمایشِ اشتراک/مصرف/پلن‌ها و تغییرِ پلن برایِ مرچنت (Checkpoint 5A، §33-§37).
# مدیریتِ پلتفرمیِ خودِ پلن‌ها (ساخت/انتشار نسخه) هرگز اینجا نیست — فقط در
# Django Admin پشتِ superuser. مرچنت فقط پلن‌هایِ «قابلِ انتخابِ عمومی» را
# می‌بیند و فقط نسخه‌ی جاریِ منتشرشده‌ی هرکدام را می‌تواند انتخاب کند.


def _publicly_selectable_versions(store):
    """جدیدترین نسخه‌ی منتشرشده‌ی هر پلنِ «قابلِ انتخابِ عمومی» — همان چیزی که
    مرچنت مجاز است به آن سوییچ کند."""
    from apps.subscriptions.models import Plan, PlanVersion

    plans = Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order", "code")
    result = []
    for plan in plans:
        version = (
            PlanVersion.objects.filter(plan=plan, status=PlanVersion.Status.PUBLISHED)
            .order_by("-version_number").first()
        )
        if version is not None:
            result.append((plan, version))
    return result


@staff_required
@permission_required(SUBSCRIPTION_VIEW)
def subscription_overview(request):
    from apps.subscriptions.services import entitlement_service as ent

    store = _resolve_dashboard_store(request)
    summary = ent.get_subscription_summary(store)
    return render(request, "dashboard/subscription_overview.html", {
        "summary": summary,
        "active_page": "subscription",
        "can_change_subscription": membership_has_permission(request.store_membership, SUBSCRIPTION_CHANGE),
    })


@staff_required
@permission_required(USAGE_VIEW)
def usage_overview(request):
    from apps.subscriptions.services import usage_service as usage

    store = _resolve_dashboard_store(request)
    return render(request, "dashboard/usage_overview.html", {
        "usage_rows": usage.get_usage_summary(store),
        "active_page": "usage",
    })


@staff_required
@permission_required(SUBSCRIPTION_CHANGE)
def subscription_plans(request):
    from apps.subscriptions.services import entitlement_service as ent

    store = _resolve_dashboard_store(request)
    current_version = ent.get_effective_plan_version(store)
    current_plan_id = current_version.plan_id if current_version else None
    plans = [
        {"plan": plan, "version": version, "is_current": plan.pk == current_plan_id}
        for plan, version in _publicly_selectable_versions(store)
    ]
    return render(request, "dashboard/subscription_plans.html", {
        "plans": plans,
        "active_page": "subscription",
        "has_subscription": current_version is not None,
    })


def _resolve_selectable_version_or_404(store, version_id):
    """نسخه‌ی هدف را فقط از میانِ نسخه‌هایِ قابلِ انتخابِ عمومی می‌پذیرد — تا
    مرچنت نتواند با POSTِ دستی یک نسخه‌ی خصوصی/بایگانی را انتخاب کند."""
    for _plan, version in _publicly_selectable_versions(store):
        if str(version.pk) == str(version_id):
            return version
    raise Http404


@require_POST
@staff_required
@permission_required(SUBSCRIPTION_CHANGE)
def subscription_plan_preview(request):
    """SUB-001: از پیش‌نمایشِ کانونیِ صورتحساب‌محورِ
    ``plan_change_billing_service.preview`` عبور می‌کند (نه صرفاً 5Aِ
    entitlement-only) تا قالب بتواند صادقانه نشان دهد که آیا این تغییر
    ارتقاست (نیازمندِ پرداخت) یا تنزل/هم‌قیمت (زمان‌بندی‌شده، بدونِ پرداخت)."""
    from apps.billing.services import plan_change_billing_service as pcb
    from apps.subscriptions.services import entitlement_service as ent
    from apps.subscriptions.services import plan_change_service as pcs

    store = _resolve_dashboard_store(request)
    target_version = _resolve_selectable_version_or_404(store, request.POST.get("version_id", ""))
    current_subscription = ent.get_current_subscription(store)
    if current_subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
        return redirect("dashboard:subscription-plans")
    try:
        preview = pcb.preview(current_subscription, target_version)
    except pcs.PlanChangeError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:subscription-plans")
    return render(request, "dashboard/subscription_plan_preview.html", {
        "preview": preview,
        "active_page": "subscription",
    })


@require_POST
@staff_required
@permission_required(SUBSCRIPTION_CHANGE)
def subscription_plan_execute(request):
    """SUB-001: مرچنت هرگز نمی‌تواند مستقیماً ``subscription_service.
    change_plan_version`` را صدا بزند — این ویو حالا از همان مسیرِ
    صورتحساب‌محورِ کانونیک عبور می‌کند که خریدِ اشتراکِ پرتال هم از آن
    استفاده می‌کند (``plan_change_billing_service.start_plan_change``):

    * **ارتقا** یک فاکتورِ ``PLAN_CHANGE`` می‌سازد و مرچنت را به همان صفحه‌ی
      فاکتورِ Billing UIِ موجود (``dashboard:billing-invoice-detail``)
      می‌فرستد؛ نسخه‌ی پلن فقط پس از تأییدِ *واقعیِ* پرداخت
      (``confirmation_service``) تغییر می‌کند — نه با این درخواست.
    * **تنزل/قیمتِ برابر** بدونِ نیازِ پرداخت زمان‌بندی می‌شود
      (``ScheduledPlanChange``) و در دوره‌ی بعد اعمال می‌شود.

    محافظتِ پیش‌نمایشِ کهنه و انتخابِ فقط از میانِ نسخه‌هایِ قابلِ‌انتخابِ عمومی
    (``_resolve_selectable_version_or_404``) بدونِ تغییر باقی می‌ماند."""
    from apps.billing.services import plan_change_billing_service as pcb
    from apps.subscriptions.services import entitlement_service as ent
    from apps.subscriptions.services import plan_change_service as pcs

    store = _resolve_dashboard_store(request)
    target_version = _resolve_selectable_version_or_404(store, request.POST.get("version_id", ""))
    token = request.POST.get("preview_token", "")

    current_subscription = ent.get_current_subscription(store)
    if current_subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
        return redirect("dashboard:subscription-plans")

    try:
        kind, result = pcb.start_plan_change(
            current_subscription, target_version, preview_token=token, actor=request.user,
        )
    except pcs.StalePreviewError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:subscription-plans")
    except (pcs.PlanChangeError, pcb.PlanChangeBillingError) as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:subscription-plans")

    if kind == "scheduled":
        messages.success(request, "تغییرِ پلن برایِ دوره‌ی بعد زمان‌بندی شد؛ اشتراکِ فعلی تا آن زمان بدونِ تغییر باقی می‌ماند.")
        return redirect("dashboard:subscription-overview")

    # ارتقا: سندِ مالی (فاکتورِ تغییرِ پلن) ساخته/بازیابی شد؛ مرچنت را به همان
    # صفحه‌ی فاکتورِ Billing UIِ موجود می‌فرستیم تا از طریقِ ``dashboard:
    # billing-pay`` پرداخت کند — هیچ رابطِ پرداختِ دومی ساخته نمی‌شود.
    messages.success(request, "فاکتورِ تغییرِ پلن ایجاد شد؛ پلن پس از تکمیلِ پرداخت فعال می‌شود.")
    return redirect("dashboard:billing-invoice-detail", pk=result.pk)


@staff_required
@permission_required(SUBSCRIPTION_VIEW)
def subscription_history(request):
    from apps.subscriptions.models import SubscriptionEvent

    store = _resolve_dashboard_store(request)
    events = (
        SubscriptionEvent.objects.filter(store=store)
        .select_related("from_plan_version__plan", "to_plan_version__plan", "actor")
        .order_by("-created_at")[:200]
    )
    return render(request, "dashboard/subscription_history.html", {
        "events": events,
        "active_page": "subscription",
    })


# ==================================================================== صورتحساب (5B)
#
# Merchant Billing UI (§23): نمای کلی، حسابِ صورتحساب، فاکتورها، جزئیاتِ فاکتور،
# شروعِ پرداخت (hosted)، نتیجه‌ی پرداخت (بازگشتِ مرورگر فقط اطلاعاتی)، و لغو.
# بازگشتِ مرورگر هرگز مدرکِ پرداخت نیست — تأیید فقط از Webhook/اقدامِ مدیر.


def _billing_invoice_or_404(store, pk):
    from apps.billing.models import SubscriptionInvoice

    return get_object_or_404(SubscriptionInvoice, pk=pk, store=store)


@staff_required
@permission_required(BILLING_VIEW)
def billing_overview(request):
    from apps.billing.models import SubscriptionInvoice
    from apps.billing.services.account_service import get_billing_account
    from apps.subscriptions.services import entitlement_service as ent

    store = _resolve_dashboard_store(request)
    summary = ent.get_subscription_summary(store)
    next_open = (
        SubscriptionInvoice.objects.filter(
            store=store, status__in=[
                SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAYMENT_PENDING,
                SubscriptionInvoice.Status.PAST_DUE,
            ],
        ).order_by("due_at").first()
    )
    return render(request, "dashboard/billing_overview.html", {
        "summary": summary, "next_open_invoice": next_open,
        "billing_account": get_billing_account(store), "active_page": "billing",
        "can_manage_account": membership_has_permission(request.store_membership, BILLING_ACCOUNT_MANAGE),
        "can_pay": membership_has_permission(request.store_membership, BILLING_PAYMENT_MANAGE),
        "can_cancel": membership_has_permission(request.store_membership, SUBSCRIPTION_CANCEL),
    })


@staff_required
@permission_required(BILLING_ACCOUNT_MANAGE)
def billing_account_edit(request):
    from apps.billing.services import account_service

    store = _resolve_dashboard_store(request)
    if request.method == "POST":
        try:
            account_service.update_billing_account(
                store, actor=request.user,
                legal_name=request.POST.get("legal_name", "").strip(),
                billing_email=request.POST.get("billing_email", "").strip(),
                billing_phone=request.POST.get("billing_phone", "").strip(),
                country=request.POST.get("country", "").strip(),
                region=request.POST.get("region", "").strip(),
                city=request.POST.get("city", "").strip(),
                postal_code=request.POST.get("postal_code", "").strip(),
                address_line=request.POST.get("address_line", "").strip(),
                tax_identifier=request.POST.get("tax_identifier", "").strip(),
            )
            messages.success(request, "حسابِ صورتحساب ذخیره شد.")
            return redirect("dashboard:billing-overview")
        except account_service.BillingAccountError as exc:
            messages.error(request, str(exc))
    account = account_service.get_or_create_billing_account(store)
    return render(request, "dashboard/billing_account.html", {
        "account": account, "active_page": "billing",
    })


@staff_required
@permission_required(BILLING_VIEW)
def billing_invoices(request):
    from apps.billing.models import SubscriptionInvoice

    store = _resolve_dashboard_store(request)
    invoices = SubscriptionInvoice.objects.filter(store=store).order_by("-created_at")[:200]
    return render(request, "dashboard/billing_invoices.html", {
        "invoices": invoices, "active_page": "billing",
    })


@staff_required
@permission_required(BILLING_VIEW)
def billing_invoice_detail(request, pk):
    store = _resolve_dashboard_store(request)
    invoice = _billing_invoice_or_404(store, pk)
    return render(request, "dashboard/billing_invoice_detail.html", {
        "invoice": invoice,
        "lines": invoice.lines.all(),
        "attempts": invoice.payment_attempts.all(),
        "refunds": invoice.refunds.all(),
        "credit_notes": invoice.credit_notes.all(),
        "active_page": "billing",
        "can_pay": membership_has_permission(request.store_membership, BILLING_PAYMENT_MANAGE),
    })


@require_POST
@staff_required
@permission_required(BILLING_PAYMENT_MANAGE)
def billing_pay(request, pk):
    from apps.billing.services import payment_flow_service

    store = _resolve_dashboard_store(request)
    invoice = _billing_invoice_or_404(store, pk)
    return_url = request.build_absolute_uri(reverse("dashboard:billing-payment-result"))
    try:
        attempt, session = payment_flow_service.start_payment(
            invoice, return_url=return_url, actor=request.user,
        )
    except payment_flow_service.PaymentFlowError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:billing-invoice-detail", pk=invoice.pk)
    request.session["billing_last_attempt"] = attempt.public_token
    return redirect(session.redirect_url)


@staff_required
@permission_required(BILLING_PAYMENT_MANAGE)
def billing_payment_result(request):
    from apps.billing.models import SubscriptionPaymentAttempt
    from apps.billing.providers.base import BillingProviderError
    from apps.billing.services.confirmation_service import ConfirmationError
    from apps.billing.services.payment_flow_service import confirm_from_provider_verification

    store = _resolve_dashboard_store(request)
    token = request.session.get("billing_last_attempt", "")
    # بازگشتِ مرورگر فقط اطلاعاتی است — وضعیت از رکوردِ سمتِ سرور خوانده می‌شود،
    # نه از پارامترهایِ query. برایِ Providerهایی که Webhookِ فشاری ندارند
    # (زیبال)، همین بازگشت لحظه‌ای است که سرور verify واقعی را انجام می‌دهد —
    # امّا خودِ query params هرگز به‌عنوانِ مدرکِ پرداخت اعتماد نمی‌شوند.
    attempt = SubscriptionPaymentAttempt.objects.filter(
        store=store, public_token=token,
    ).select_related("invoice").first()
    verify_error = ""
    if attempt is not None:
        try:
            attempt = confirm_from_provider_verification(attempt, actor=request.user)
        except (BillingProviderError, ConfirmationError) as exc:
            verify_error = str(exc)
    return render(request, "dashboard/billing_payment_result.html", {
        "attempt": attempt, "verify_error": verify_error, "active_page": "billing",
    })


@staff_required
@permission_required(SUBSCRIPTION_CANCEL)
def billing_cancel(request):
    from apps.billing.services import cancellation_service
    from apps.subscriptions.services import entitlement_service as ent

    store = _resolve_dashboard_store(request)
    subscription = ent.get_current_subscription(store)
    if request.method == "POST":
        if subscription is None:
            messages.error(request, "اشتراکِ جاری یافت نشد.")
            return redirect("dashboard:billing-overview")
        immediate = request.POST.get("mode") == "immediate"
        try:
            cancellation_service.cancel_subscription_billing(
                subscription, immediate=immediate, actor=request.user,
            )
            messages.success(request, "درخواستِ لغوِ اشتراک ثبت شد.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect("dashboard:billing-overview")
    return render(request, "dashboard/billing_cancel.html", {
        "subscription": subscription, "active_page": "billing",
    })


@staff_required
@permission_required(BILLING_VIEW)
def billing_invoice_print(request, pk):
    from django.conf import settings

    store = _resolve_dashboard_store(request)
    invoice = _billing_invoice_or_404(store, pk)
    return render(request, "dashboard/billing_invoice_print.html", {
        "invoice": invoice, "lines": invoice.lines.all(),
        "seller_name": getattr(settings, "SHOP_NAME", "پلتفرم"),
    })
