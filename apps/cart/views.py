import json

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.catalog.models import ProductVariant
from apps.catalog.services.pricing_service import resolve_regular_price
from apps.catalog.services.product_publish_service import storefront_visible_products

from apps.stores.resolution import resolve_store_for_service

from .models import CartItem
from .services.cart_service import UnavailableStockError, add_item_to_cart, get_cart
from .services.pricing import cart_totals


def _cart_context(request, cart):
    if cart is None:
        totals = {
            "items_total": 0, "product_discount": 0, "coupon_discount": 0,
            "shipping_cost": 0, "free_shipping": False, "tax": 0, "grand_total": 0,
        }
        item_count = 0
        items = []
    else:
        store = resolve_store_for_service(request)
        totals = cart_totals(cart, store=store)
        items = list(cart.items.select_related("product", "variant").all())
        for item in items:
            # برای نمایشِ «قیمتِ پیش از تخفیف» در قالب — item.unit_price خودش
            # همان قیمتِ نهایی (اسنپ‌شات) است، نه product.final_price ساده.
            item.regular_price = resolve_regular_price(item.product, item.variant)
        item_count = sum(item.quantity for item in items)
    return {"cart": cart, "cart_items": items, "totals": totals, "item_count": item_count}


def _render_cart_container(request, cart):
    """Phase 5: پاسخِ مشترکِ هر دو htmx endpointِ سبد (به‌روزرسانی/حذفِ
    قلم) — دقیقاً همان section‌ها (با همان ترتیب/تنظیماتِ ریسپانسیوِ
    پیکربندی‌شده) دوباره رندر می‌شوند، نه partialِ سخت‌کدشده‌ی قدیمی — تا
    شخصی‌سازیِ مرچنت هرگز بعد از یک اکشنِ htmx «ریست» نشود. منطقِ تجاریِ
    خودِ سبد (بالا) کاملاً دست‌نخورده و جدا می‌ماند؛ این فقط تصمیمِ
    presentation است. Storeهایی که هنوز هیچ Storefront V2ای منتشر
    نکرده‌اند هم همین مسیر را می‌گیرند — ``build_default_render_items``
    همان دو section پیش‌فرض را بدونِ ردیفِ واقعی در دیتابیس می‌سازد،
    دقیقاً همان الگویِ ``storefront_context_service.build_universal_storefront_context``."""
    from apps.storefront_builder.models import StorefrontPage
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.stores.resolution import resolve_store_for_storefront

    context = _cart_context(request, cart)
    store = resolve_store_for_storefront(request)
    # V05/A04: عبور از همان کانتکستِ سراسری که صفحه‌ی کاملِ ``cart_detail``
    # می‌سازد — نه رندرِ دستیِ فقط render_items/rows که layoutِ container و
    # نسخه‌ی ظاهر را نادیده می‌گرفت. build_universal_storefront_context علاوه
    # بر render_items/rows، کلیدهایِ ``render_containers``/``use_container_layout``
    # را می‌سازد و ``request.storefront_appearance_version`` را ست می‌کند، پس
    # فرگمنتِ htmx دقیقاً همان چیدمان/ظاهرِ صفحه‌ی کامل را دارد. ``page_context``
    # همان دیکشنریِ ``_cart_context`` است تا section‌های سبد به همان
    # cart/totals/item_count برسند؛ چون سپس با ``.update`` روی همان context
    # نوشته می‌شود (universal بُرنده است، دقیقاً الگویِ ``cart_detail``)،
    # کلیدهایِ سبد حفظ می‌شوند. تمپلیت همان ``cart_sections_body.html`` است،
    # پس includeِ POST-gatedِ شمارنده‌هایِ OOB (cart-count/...) هم دست‌نخورده
    # باقی می‌ماند.
    context.update(
        build_universal_storefront_context(
            request, store, StorefrontPage.PageType.CART, page_context=context,
        )
    )
    return render(request, "cart/partials/cart_sections_body.html", context)


def cart_detail(request):
    cart = get_cart(request, create=True)
    context = _cart_context(request, cart)

    # Phase 1B: پوسته‌ی سراسری — منطقِ سبد (بالا، بدونِ تغییر) کاملاً از
    # این جدا است؛ ``resolve_store_for_storefront`` (نه
    # ``resolve_store_for_service``ی که ``cart_totals`` داخلی استفاده
    # می‌کند) عمداً اینجا صدا زده می‌شود چون این تنها فراخوانِ صریحِ
    # تفکیکِ Store در این ویو است — دقیقاً همان resolverای که پنج ویوِ
    # دیگرِ Storefront استفاده می‌کنند (fail-closed: میزبانِ ناشناخته →
    # ۴۰۴، Storeِ غیرِ عمومی → ۴۰۳).
    from apps.stores.resolution import resolve_store_for_storefront
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    store = resolve_store_for_storefront(request)
    context.update(build_universal_storefront_context(request, store, StorefrontPage.PageType.CART, page_context=context))
    return render(request, "cart/cart_detail.html", context)


def _cart_add_error_response(request, message):
    """پاسخِ خطا برایِ افزودنِ ناموفق به سبد — طبقِ همان قراردادِ خطایِ
    موجودِ پروژه (200 + ``HX-Trigger`` توستِ ``err``، نه یک بدنه‌یِ خطایِ
    جدا؛ نگاه کنید به ``apps.orders.views._dynamic_response``). هرگز چیزی
    به سبد اضافه نمی‌شود — شمارنده‌یِ هدر هم بدونِ تغییر دوباره رندر می‌شود."""
    response = render(request, "cart/partials/header_counts_oob.html", _header_counts_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": message, "type": "err"}})
    return response


@require_POST
def cart_add(request, slug):
    store = resolve_store_for_service(request)
    # storefront_visible_products(store) به‌تنهایی محدودِ همینِ Store است —
    # هرگز کالای Storeِ دیگری بازگردانده نمی‌شود (404 در غیرِ این صورت).
    product = get_object_or_404(storefront_visible_products(store), slug=slug)

    variant = None
    variant_id = request.POST.get("variant_id", "").strip()
    if variant_id:
        # Server-side validation (ADR-85): the variant must belong to THIS
        # product (rejecting cross-store / cross-product ids) and be active —
        # an inactive variant can never be purchased. Price is resolved from the
        # server (pricing_service.resolve_effective_price, inside add_item_to_cart),
        # never from POST.
        variant = get_object_or_404(ProductVariant, pk=variant_id, product=product, is_active=True)

    # تعدادِ نامعتبر (غیرِعددی، صفر یا منفی) به‌جایِ کِلَمپ‌شدنِ بی‌صدا به ۱،
    # صریحاً رد می‌شود — پیش از این، هر مقدارِ نامعتبر بی‌صدا ۱ تفسیر می‌شد که
    # امکانِ تشخیصِ درخواست‌هایِ دستکاری‌شده را از بین می‌برد. کالا هرگز با
    # تعدادِ نامعتبر به سبد اضافه نمی‌شود.
    quantity_raw = request.POST.get("quantity", "1")
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return _cart_add_error_response(request, "تعداد درخواستی نامعتبر است.")
    if quantity <= 0:
        return _cart_add_error_response(request, "تعداد درخواستی باید بزرگ‌تر از صفر باشد.")

    cart = get_cart(request, create=True)

    # چک‌باکسِ کادوپیچی (toranj_gifting و هر خانواده‌ی دیگری که آن را نمایش
    # دهد) — مقدارِ خام از فرم صرفاً یک *درخواست* است؛ در دسترس‌بودن/قیمتِ
    # واقعی همیشه در add_item_to_cart از ShopSettings حل می‌شود، نه از اینجا.
    gift_wrap_requested = request.POST.get("gift_wrap") in ("1", "true", "on", "yes")

    try:
        add_item_to_cart(cart, product, variant, quantity, gift_wrap_requested=gift_wrap_requested)
    except UnavailableStockError as exc:
        # موجودیِ ناکافی/کالایِ ناموجود — چیزی به سبد اضافه نمی‌شود (نه حتی
        # با کِلَمپ‌کردنِ تعداد)؛ کاربر با پیامِ صریح آگاه می‌شود.
        return _cart_add_error_response(request, exc.message)

    response = render(request, "cart/partials/header_counts_oob.html", _header_counts_context(request))
    response["HX-Trigger"] = json.dumps(
        {"toast": {"message": f"«{product.name}» به سبد خرید اضافه شد", "type": "ok"}}
    )
    return response


@require_POST
def cart_item_update(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    # موجودیِ فعلی (نه در لحظه‌ی افزودنِ اولیه) دوباره خوانده می‌شود — کالا
    # ممکن است از آن زمان تا الان کاملاً بدونِ موجودی شده باشد. پیش از این
    # اصلاح، وقتی available_stock == 0 بود، شرط ``if available_stock > 0``
    # کاذب می‌شد و quantity هرگز کِلَمپ نمی‌شد — یعنی کاربر می‌توانست تعدادِ
    # دلخواهی را برایِ یک قلمِ کاملاً ناموجود ثبت کند. حالا کالای بدون‌موجودی
    # از سبد حذف می‌شود (نه این‌که با تعدادِ نامعتبر باقی بماند).
    if item.variant_id:
        item.variant.refresh_from_db()
        available_stock = item.variant.stock
    else:
        item.product.refresh_from_db()
        available_stock = item.product.stock

    if available_stock <= 0:
        item.delete()
        response = _render_cart_container(request, cart)
        response["HX-Trigger"] = json.dumps(
            {"toast": {"message": "این کالا دیگر موجود نیست و از سبد حذف شد", "type": "err"}}
        )
        return response

    quantity = min(quantity, available_stock)

    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])

    return _render_cart_container(request, cart)


@require_POST
def cart_item_remove(request, item_id):
    cart = get_cart(request, create=True)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return _render_cart_container(request, cart)


def _header_counts_context(request):
    from apps.cart.context_processors import cart_badge

    return cart_badge(request)



def cart_preview_partial(request):
    """پارشیالِ پیش‌نمایشِ سبد — برایِ بارگذاریِ htmx داخلِ پنلِ hover/کلیکیِ
    هدر. حالتِ پیش‌نمایش از query param ``mode`` خوانده می‌شود (پیش‌فرض:
    ``count_link``)."""
    from .services.cart_preview import (
        CART_PREVIEW_MODE_COUNT_LINK,
        CART_PREVIEW_MODE_MINI_CART,
        CART_PREVIEW_MODES,
        get_cart_preview_data,
    )

    mode = request.GET.get("mode", CART_PREVIEW_MODE_COUNT_LINK)
    if mode not in CART_PREVIEW_MODES:
        mode = CART_PREVIEW_MODE_COUNT_LINK
    data = get_cart_preview_data(request, mode=mode)
    return render(request, "cart/partials/cart_preview.html", data)
