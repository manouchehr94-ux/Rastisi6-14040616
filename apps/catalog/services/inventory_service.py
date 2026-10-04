"""دفتر موجودی (Inventory Ledger) — کاهش/بازگشتِ اتمیکِ موجودی به‌همراه ثبتِ حسابرسی.

هیچ‌جای این ماژول موجودی را مستقیماً بدون ثبت یک ``StockMovement`` تغییر
نمی‌دهد (ADR-31 در ``SAAS_DOMAIN_DECISIONS.md``). این سرویس، لایه‌ی واحدِ
اعمالِ تغییرِ موجودی برای سفارش‌ها (ثبت/لغو) است — پیش از این PR،
``order_service.create_order_from_cart`` مستقیماً و بدون ثبت، ``Product.stock``
را کم می‌کرد و برای اقلامِ دارای تنوع، موجودیِ *اشتباه* (Product به‌جای
ProductVariant) را کم می‌کرد و لغو سفارش هرگز موجودی را بازنمی‌گرداند — این
دو باگ اینجا با معرفیِ دفتر موجودی اصلاح شده‌اند.

``Product.stock``/``ProductVariant.stock`` همچنان تکِ منبعِ حقیقتِ موجودیِ
قابل‌فروش‌اند (ADR-38، checkpoint 3). هر تابعی که این مقادیر را تغییر
می‌دهد، همان تغییر را — در همان تراکنش — روی موجودیِ انبارِ پیش‌فرض
(``WarehouseInventory``) هم اعمال می‌کند تا این دو هرگز از هم واگرا
نشوند؛ ``verify_inventory_consistency`` این هم‌ترازی را بررسی می‌کند.
"""

from django.db import transaction
from django.db.models import F, Sum

from apps.catalog.models import Product, ProductVariant, StockMovement, Warehouse, WarehouseInventory
from apps.core.services.audit_service import record_audit_event


class InsufficientStockError(Exception):
    """موجودیِ هدف (کالا یا تنوع) برای این تعداد کافی نیست."""


class ReturnItemAlreadyRestockedError(Exception):
    """این قلمِ مرجوعی/استرداد قبلاً یک‌بار به موجودی بازگشته — نگاه کنید به ADR-35."""


class InvalidRestockWarehouseError(Exception):
    """انبارِ انتخاب‌شده برای بازگشتِ موجودی نامعتبر است (فروشگاهِ دیگر یا آرشیوشده) — نگاه کنید به ADR-48."""


def _resolve_default_warehouse(store) -> Warehouse:
    from apps.catalog.services.warehouse_service import provision_default_warehouse

    return provision_default_warehouse(store)


def _resolve_restock_warehouse(store, *, explicit_warehouse=None, order_item=None) -> Warehouse:
    """انبارِ مقصدِ بازگشتِ موجودی را طبقِ اولویتِ ADR-48 حل می‌کند: انتخابِ
    صریحِ مدیر > انبارِ تأمین‌کننده‌ی اصلیِ همان قلمِ سفارش > انبارِ
    پیش‌فرضِ Store."""
    if explicit_warehouse is not None:
        if explicit_warehouse.store_id != store.pk:
            raise InvalidRestockWarehouseError("این انبار متعلق به فروشگاه دیگری است.")
        if not explicit_warehouse.is_active:
            raise InvalidRestockWarehouseError("این انبار آرشیو شده و نمی‌تواند مقصدِ بازگشتِ موجودی باشد.")
        return explicit_warehouse
    if order_item is not None and order_item.fulfillment_warehouse_id is not None:
        warehouse = order_item.fulfillment_warehouse
        if warehouse.is_active:
            return warehouse
    return _resolve_default_warehouse(store)


def _sync_warehouse_balance(*, store, product, variant, delta: int, warehouse: Warehouse | None = None) -> Warehouse:
    """موجودیِ یک انبار را با همان ``delta``ی اعمال‌شده روی
    Product.stock/ProductVariant.stock هماهنگ می‌کند. اگر ردیفِ موجودیِ
    انبار هنوز برای این کالا/تنوع وجود نداشته باشد (اولین‌بار)، با مقدارِ
    *فعلیِ* (پس از اعمالِ delta) Product.stock/ProductVariant.stock ساخته
    می‌شود — نه این‌که delta دوباره روی صفر اعمال شود.

    ``warehouse`` اختیاری است — اگر داده نشود، انبارِ پیش‌فرضِ Store حل
    می‌شود (رفتارِ همیشگی برای سفارش/لغو/اصلاحِ دستی). فقط بازگشتِ موجودیِ
    مرجوعی/استرداد (ADR-48) ممکن است انبارِ دیگری صریحاً بدهد."""
    if warehouse is None:
        warehouse = _resolve_default_warehouse(store)
    current_aggregate = (
        ProductVariant.objects.filter(pk=variant.pk).values_list("stock", flat=True).first()
        if variant is not None
        else Product.objects.filter(pk=product.pk).values_list("stock", flat=True).first()
    )
    balance, created = WarehouseInventory.objects.select_for_update().get_or_create(
        store=store, warehouse=warehouse, product=product, variant=variant,
        defaults={"on_hand": current_aggregate if current_aggregate is not None else 0},
    )
    if not created:
        WarehouseInventory.objects.filter(pk=balance.pk).update(on_hand=F("on_hand") + delta)
    return warehouse


def get_available_quantity(*, product, variant=None) -> int:
    """موجودیِ در دسترس = موجودیِ فعلی − مجموعِ رزروهای فعال. نگاه کنید به ADR-39."""
    from apps.catalog.models import InventoryReservation

    on_hand = variant.stock if variant is not None else product.stock
    reserved = InventoryReservation.objects.filter(
        product=product, variant=variant, status=InventoryReservation.Status.ACTIVE,
    ).aggregate(total=Sum("quantity"))["total"] or 0
    return on_hand - reserved


def decrement_stock_for_order_item(*, store, product, variant, quantity, order, actor=None):
    """موجودیِ صحیح (تنوع در صورت وجود، وگرنه خودِ کالا) را برای یک قلمِ سفارشِ
    تازه کاهش می‌دهد و یک ``StockMovement`` ثبت می‌کند.

    باید داخل همان تراکنشی فراخوانی شود که قفلِ ردیف (``select_for_update``)
    را از قبل گرفته — نگاه کنید به
    ``order_service._lock_and_revalidate_items`` — چون مقدارِ
    ``stock_before`` مستقیماً از رویِ نمونه‌ی پاس‌داده‌شده خوانده می‌شود، نه
    با یک کوئریِ تازه.
    """
    if variant is not None:
        stock_before = variant.stock
        updated = ProductVariant.objects.filter(pk=variant.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )
    else:
        stock_before = product.stock
        updated = Product.objects.filter(pk=product.pk, stock__gte=quantity).update(
            stock=F("stock") - quantity
        )

    if updated == 0:
        raise InsufficientStockError(f"موجودی «{product.name}» کافی نیست")

    warehouse = _sync_warehouse_balance(store=store, product=product, variant=variant, delta=-quantity)
    StockMovement.objects.create(
        store=store, product=product, variant=variant, warehouse=warehouse,
        reason=StockMovement.Reason.ORDER_PLACED, delta=-quantity,
        stock_before=stock_before, stock_after=stock_before - quantity,
        order=order, actor=actor,
    )


def restock_order(*, store, order, actor=None) -> None:
    """موجودیِ تمامِ اقلامِ این سفارش را بازمی‌گرداند (لغو سفارش) و برای هرکدام
    یک ``StockMovement`` با علتِ ``ORDER_CANCELED`` ثبت می‌کند.

    اقلامی که ``product``شان دیگر وجود ندارد (حذف‌شده، ``SET_NULL``) بی‌صدا
    رد می‌شوند — چیزی برای بازگرداندنِ موجودی به آن باقی نمانده.
    """
    for item in order.items.select_for_update(of=("self",)).select_related("product", "variant"):
        if item.product_id is None:
            continue

        if item.variant_id is not None:
            variant = ProductVariant.objects.select_for_update().filter(pk=item.variant_id).first()
            if variant is None:
                continue
            stock_before = variant.stock
            ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + item.quantity)
            product, target_variant = item.product, variant
        else:
            product = Product.objects.select_for_update().filter(pk=item.product_id).first()
            if product is None:
                continue
            stock_before = product.stock
            Product.objects.filter(pk=product.pk).update(stock=F("stock") + item.quantity)
            target_variant = None

        warehouse = _sync_warehouse_balance(store=store, product=product, variant=target_variant, delta=item.quantity)
        StockMovement.objects.create(
            store=store, product=product, variant=target_variant, warehouse=warehouse,
            reason=StockMovement.Reason.ORDER_CANCELED, delta=item.quantity,
            stock_before=stock_before, stock_after=stock_before + item.quantity,
            order=order, actor=actor,
        )


def restock_return_item(*, store, return_item, actor=None) -> "StockMovement | None":
    """موجودیِ یک قلمِ مرجوعیِ قابل‌بازگشت را افزایش می‌دهد و یک
    ``StockMovement`` با علتِ ``RETURN_RESTOCK`` ثبت می‌کند.

    محافظت در برابر بازگشتِ دوباره از دو راه: (۱) قیدِ دیتابیسِ
    ``uniq_stockmv_per_return_item`` که هرگز اجازه نمی‌دهد بیش از یک
    ``StockMovement`` به یک ``ReturnItem`` ارجاع دهد، و (۲) این تابع پیش از
    درج، وجودِ ردیفِ قبلی را صریحاً بررسی می‌کند تا خطای واضح
    ``ReturnItemAlreadyRestockedError`` بدهد به‌جای ``IntegrityError`` خام.
    فراخواننده (``return_service.complete_return``) باید ``return_item`` را
    از قبل قفل کرده باشد.
    """
    if StockMovement.objects.filter(return_item=return_item).exists():
        raise ReturnItemAlreadyRestockedError("موجودیِ این قلمِ مرجوعی قبلاً بازگشت داده شده است.")

    quantity = return_item.quantity_received or 0
    if quantity <= 0:
        return None

    order_item = return_item.order_item
    product = order_item.product
    variant = order_item.variant
    if product is None:
        return None  # کالای اصلی حذف شده — چیزی برای بازگرداندنِ موجودی به آن نمانده

    restock_warehouse = _resolve_restock_warehouse(
        store, explicit_warehouse=return_item.restock_warehouse, order_item=order_item,
    )

    if variant is not None:
        variant = ProductVariant.objects.select_for_update().filter(pk=variant.pk).first()
        if variant is None:
            return None
        stock_before = variant.stock
        ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + quantity)
    else:
        product = Product.objects.select_for_update().filter(pk=product.pk).first()
        if product is None:
            return None
        stock_before = product.stock
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + quantity)

    warehouse = _sync_warehouse_balance(
        store=store, product=product, variant=variant, delta=quantity, warehouse=restock_warehouse,
    )
    return StockMovement.objects.create(
        store=store, product=product, variant=variant, warehouse=warehouse,
        reason=StockMovement.Reason.RETURN_RESTOCK, delta=quantity,
        stock_before=stock_before, stock_after=stock_before + quantity,
        order=order_item.order, return_item=return_item, actor=actor,
    )


def restock_refund_item(*, store, refund_item, actor=None) -> "StockMovement | None":
    """موجودی را برای یک قلمِ استردادِ *بدونِ* درخواستِ مرجوعیِ رسمی بازمی‌گرداند
    (مثلاً استردادِ سریعِ حضوری) — فقط وقتی مدیر صراحتاً «بازگرداندنِ موجودی»
    را در لحظه‌ی ثبتِ استرداد انتخاب کرده باشد
    (``refund_service.execute_order_refund(..., restock=True)``)."""
    if StockMovement.objects.filter(refund_item=refund_item).exists():
        raise ReturnItemAlreadyRestockedError("موجودیِ این قلمِ استرداد قبلاً بازگشت داده شده است.")

    order_item = refund_item.order_item
    quantity = refund_item.quantity
    product = order_item.product
    variant = order_item.variant
    if product is None or quantity <= 0:
        return None

    restock_warehouse = _resolve_restock_warehouse(store, order_item=order_item)

    if variant is not None:
        variant = ProductVariant.objects.select_for_update().filter(pk=variant.pk).first()
        if variant is None:
            return None
        stock_before = variant.stock
        ProductVariant.objects.filter(pk=variant.pk).update(stock=F("stock") + quantity)
    else:
        product = Product.objects.select_for_update().filter(pk=product.pk).first()
        if product is None:
            return None
        stock_before = product.stock
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + quantity)

    warehouse = _sync_warehouse_balance(
        store=store, product=product, variant=variant, delta=quantity, warehouse=restock_warehouse,
    )
    return StockMovement.objects.create(
        store=store, product=product, variant=variant, warehouse=warehouse,
        reason=StockMovement.Reason.REFUND_RESTOCK, delta=quantity,
        stock_before=stock_before, stock_after=stock_before + quantity,
        order=order_item.order, refund_item=refund_item, actor=actor,
    )


def adjust_stock_manually(*, store, product, variant=None, new_stock: int, actor, note: str = ""):
    """موجودیِ کالا یا تنوع را به مقدارِ مطلقِ ``new_stock`` تنظیم می‌کند
    (مثلاً پس از شمارشِ انبار) و تفاوت را در دفترِ موجودی ثبت می‌کند."""
    if new_stock < 0:
        raise ValueError("موجودی نمی‌تواند منفی باشد.")

    target = variant if variant is not None else product
    stock_before = target.stock
    delta = new_stock - stock_before
    if delta == 0:
        return None

    target.stock = new_stock
    target.save(update_fields=["stock", "updated_at"])

    warehouse = _sync_warehouse_balance(store=store, product=product, variant=variant, delta=delta)
    movement = StockMovement.objects.create(
        store=store, product=product, variant=variant, warehouse=warehouse,
        reason=StockMovement.Reason.MANUAL_ADJUSTMENT, delta=delta,
        stock_before=stock_before, stock_after=new_stock,
        actor=actor, note=note,
    )
    record_audit_event(
        store=store, actor=actor, action_code="inventory.manual_adjustment",
        object_type="Product" if variant is None else "ProductVariant",
        object_id=target.pk, object_label=product.name,
        before={"stock": stock_before}, after={"stock": new_stock}, metadata={"note": note},
    )
    return movement


@transaction.atomic
def adjust_warehouse_stock(
    *, store, warehouse, product, variant=None, mode: str, quantity: int, reason: str, actor, note: str = "",
):
    """موجودیِ یک انبارِ *مشخص* را برایِ یک کالا/تنوع تغییر می‌دهد — همیشه یک
    ``StockMovement`` می‌سازد و Product.stock/ProductVariant.stock (تجمیع
    میانِ همه‌ی انبارها، ADR-38) را با همان دلتا هم‌زمان به‌روزرسانی می‌کند.

    برخلافِ ``adjust_stock_manually`` (که همیشه انبارِ پیش‌فرضِ Store را
    هدف می‌گیرد)، این تابع صراحتاً یک ``warehouse`` می‌پذیرد — برایِ
    Inventory Import (checkpoint 4B، ستونِ ``warehouse_code``) که باید
    بتواند انبارِ غیرپیش‌فرض را هم هدف بگیرد. نگاه کنید به ADR-60 برایِ
    سیاستِ ایمنیِ رزرو: تغییری که موجودیِ در دسترسِ کل (تجمیعی، نه
    per-warehouse — این کدبیس رزرو را در سطحِ Store/Product ردیابی می‌کند،
    نه per-warehouse) را منفی کند رد می‌شود.

    ``mode``: ``"adjustment"`` (``quantity`` دلتا، می‌تواند منفی باشد) یا
    ``"set_on_hand"`` (``quantity`` مقدارِ مطلقِ همین انبار؛ دلتا از رویِ
    تفاوت با on_hand فعلیِ همین انبار محاسبه می‌شود). دلتایِ صفر هیچ
    ``StockMovement``ای نمی‌سازد و ``None`` برمی‌گرداند (idempotent no-op)."""
    from apps.catalog.models import InventoryReservation

    if warehouse.store_id != store.pk:
        raise InvalidRestockWarehouseError("این انبار متعلق به فروشگاه دیگری است.")
    if product.store_id != store.pk or (variant is not None and variant.store_id != store.pk):
        raise InvalidRestockWarehouseError("این کالا/تنوع متعلق به فروشگاه دیگری است.")

    target_model = ProductVariant if variant is not None else Product
    target_pk = variant.pk if variant is not None else product.pk
    locked_target = target_model.objects.select_for_update().get(pk=target_pk)
    stock_before = locked_target.stock

    balance, _created = WarehouseInventory.objects.select_for_update().get_or_create(
        store=store, warehouse=warehouse, product=product, variant=variant,
        defaults={"on_hand": 0},
    )

    if mode == "set_on_hand":
        if quantity < 0:
            raise ValueError("موجودیِ مطلق نمی‌تواند منفی باشد.")
        delta = quantity - balance.on_hand
    elif mode == "adjustment":
        delta = quantity
    else:
        raise ValueError(f"حالتِ «{mode}» نامعتبر است.")

    if delta == 0:
        return None

    new_aggregate = stock_before + delta
    if new_aggregate < 0:
        raise InsufficientStockError("این تغییر موجودیِ کل را منفی می‌کند.")

    reserved = InventoryReservation.objects.filter(
        product=product, variant=variant, status=InventoryReservation.Status.ACTIVE,
    ).aggregate(total=Sum("quantity"))["total"] or 0
    if new_aggregate < reserved:
        raise InsufficientStockError(
            f"این تغییر موجودیِ در دسترس را منفی می‌کند (رزروِ فعالِ کنونی: {reserved})."
        )

    locked_target.stock = new_aggregate
    locked_target.save(update_fields=["stock", "updated_at"])
    WarehouseInventory.objects.filter(pk=balance.pk).update(on_hand=F("on_hand") + delta)

    movement = StockMovement.objects.create(
        store=store, product=product, variant=variant, warehouse=warehouse,
        reason=reason, delta=delta, stock_before=stock_before, stock_after=new_aggregate,
        actor=actor, note=note,
    )
    record_audit_event(
        store=store, actor=actor, action_code="inventory.warehouse_adjustment",
        object_type="Product" if variant is None else "ProductVariant",
        object_id=target_pk, object_label=product.name,
        before={"stock": stock_before}, after={"stock": new_aggregate},
        metadata={"warehouse": warehouse.code, "note": note, "reason": reason, "mode": mode},
    )
    return movement


def list_stock_movements(store, *, product=None, variant=None, warehouse=None):
    queryset = StockMovement.objects.filter(store=store).select_related(
        "product", "variant", "order", "actor", "warehouse",
    )
    if variant is not None:
        queryset = queryset.filter(variant=variant)
    elif product is not None:
        queryset = queryset.filter(product=product)
    if warehouse is not None:
        queryset = queryset.filter(warehouse=warehouse)
    return queryset
