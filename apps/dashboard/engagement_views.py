"""صفحه‌های مدیریتیِ سامانه‌های کادوپیچی، کمپین/مناسبت و اعلان‌ها.

جدا از ``views.py`` (که بسیار بزرگ است) نگه داشته شده؛ همه‌ی ویوها از همان
دکوراتورهایِ ``staff_required``/``permission_required`` و همان Storeِ
resolve‌شده‌ی ``request.store`` استفاده می‌کنند — هیچ کوئری‌ای بدونِ فیلترِ
Store نیست.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.core.models import ShopSettings
from apps.core.services.audit_service import record_audit_event
from apps.stores.authorization import PRODUCT_EDIT, PRODUCT_VIEW

from .decorators import permission_required, staff_required


@staff_required
@permission_required(PRODUCT_VIEW)
def gift_wrap_products(request):
    """فهرستِ کالاها با کنترلِ کادوپیچیِ هر کالا (فعال/غیرفعال + قیمتِ اختصاصی)."""
    store = request.store
    shop = ShopSettings.load(store=store)
    q = request.GET.get("q", "").strip()
    flt = request.GET.get("filter", "")
    products = Product.objects.filter(store=store, is_draft_placeholder=False).order_by("name")
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if flt == "disabled":
        products = products.filter(gift_wrap_enabled=False)
    elif flt == "custom_price":
        products = products.filter(gift_wrap_price__isnull=False)
    page = Paginator(products, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/gift_wrap_products.html", {
        "page": page, "q": q, "filter": flt, "shop": shop, "active_page": "settings",
        "can_edit": request.store_membership is not None and _can(request, PRODUCT_EDIT),
    })


def _can(request, permission) -> bool:
    from apps.stores.authorization import membership_has_permission

    return membership_has_permission(request.store_membership, permission)


@require_POST
@staff_required
@permission_required(PRODUCT_EDIT)
def gift_wrap_product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, store=request.store)
    enabled = request.POST.get("gift_wrap_enabled") == "on"
    raw_price = request.POST.get("gift_wrap_price", "").strip()
    price = None
    if raw_price:
        try:
            price = Decimal(raw_price)
        except InvalidOperation:
            messages.error(request, "قیمت کادوپیچی نامعتبر است.")
            return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")
        if price < 0 or price != price.to_integral_value():
            messages.error(request, "قیمت کادوپیچی باید عددی صحیح و غیرمنفی باشد.")
            return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")
    before = {"enabled": product.gift_wrap_enabled, "price": str(product.gift_wrap_price)}
    product.gift_wrap_enabled = enabled
    product.gift_wrap_price = price
    product.save(update_fields=["gift_wrap_enabled", "gift_wrap_price", "updated_at"])
    record_audit_event(
        store=request.store, actor=request.user, action_code="product.gift_wrap_updated",
        object_type="Product", object_id=product.pk, object_label=product.name,
        before=before, after={"enabled": enabled, "price": str(price)},
    )
    messages.success(request, f"تنظیمات کادوپیچیِ «{product.name}» ذخیره شد")
    return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")
