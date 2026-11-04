"""همگام‌سازیِ مقدارِ مؤثرِ «استعلام قیمت» (``Product.is_price_inquiry``).

تنها نویسنده‌ی آن فیلد ``pricing_mode_service`` است؛ این سیگنال‌ها فقط آن را
هنگامِ تغییرِ *مرتبط* صدا می‌زنند. بازمحاسبه‌ی کل فروشگاه فقط وقتی اجرا می‌شود که
واقعاً چیزی که روی استعلام اثر دارد عوض شده باشد (حالتِ قیمتِ دسته/کالکشن، والدِ دسته،
فعال‌بودنِ کالکشن، عضویتِ کالکشن) — نه با هر ذخیره‌ی بی‌ربط (تغییرِ نام، ترتیب،
جابه‌جاییِ دسته‌ها). همه‌ی نوشتن‌ها با ``update()`` انجام می‌شود، پس بازگشتیِ سیگنال
وجود ندارد.
"""

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Category, MerchantCollection, MerchantCollectionItem, PriceMode, Product
from .services import pricing_mode_service

_PRODUCT_FIELDS = {"category", "category_id", "price_mode_override"}


@receiver(post_save, sender=Product)
def sync_product_inquiry(sender, instance, created, update_fields, **kwargs):
    if update_fields is not None and not (_PRODUCT_FIELDS & set(update_fields)):
        return
    pricing_mode_service.recompute_product(instance)


def _remember_inquiry_relevant_state(model, fields):
    def handler(sender, instance, **kwargs):
        if not instance.pk:
            instance._inquiry_state_changed = True
            return
        old = model.objects.filter(pk=instance.pk).values(*fields).first()
        new = {f: getattr(instance, f if f != "parent" else "parent_id") for f in fields}
        instance._inquiry_state_changed = old is None or any(old[f] != new[f] for f in fields)
    return handler


pre_save.connect(
    _remember_inquiry_relevant_state(Category, ("price_mode", "parent_id")), sender=Category,
    weak=False, dispatch_uid="inquiry_category_pre_save",
)
pre_save.connect(
    _remember_inquiry_relevant_state(MerchantCollection, ("price_mode", "is_active")), sender=MerchantCollection,
    weak=False, dispatch_uid="inquiry_collection_pre_save",
)


@receiver(post_save, sender=Category)
def sync_category_inquiry(sender, instance, created, update_fields, **kwargs):
    if created and instance.price_mode == PriceMode.STANDARD:
        return
    if not getattr(instance, "_inquiry_state_changed", True):
        return
    pricing_mode_service.recompute_store(instance.store)


@receiver(post_save, sender=MerchantCollection)
def sync_collection_inquiry(sender, instance, created, update_fields, **kwargs):
    if created and instance.price_mode == PriceMode.STANDARD:
        return
    if not getattr(instance, "_inquiry_state_changed", True):
        return
    pricing_mode_service.recompute_store(instance.store)


@receiver(post_save, sender=MerchantCollectionItem)
@receiver(post_delete, sender=MerchantCollectionItem)
def sync_collection_item_inquiry(sender, instance, **kwargs):
    from django.core.exceptions import ObjectDoesNotExist

    try:
        collection = instance.collection
        store = collection.store
    except ObjectDoesNotExist:
        return  # the collection itself is being deleted (cascade) — nothing left to sync through it
    if collection.price_mode == PriceMode.INQUIRY:
        pricing_mode_service.recompute_store(store)
    elif kwargs.get("signal") is post_delete:
        # A removed member may have been inquiry only through this collection (rare: the collection was since
        # switched back to standard) — a targeted check instead of a store-wide pass.
        try:
            pricing_mode_service.recompute_product(instance.product)
        except ObjectDoesNotExist:
            return  # the product itself is being deleted (cascade)


# ---- a HARD-deleted product must still be announced as «gone» (IndexNow) ----------------------------------------------------------------------------------------
#: the audit action ``apps.core.indexnow_sync`` reads to find URLs that were public and no longer have a row (no new table: the existing audit ledger carries it)
PRODUCT_HARD_DELETED = "product.hard_deleted"


@receiver(pre_delete, sender=Product)
def remember_if_the_product_was_publicly_listed(sender, instance, **kwargs):
    """Decided BEFORE the row disappears: only a product that was really listed on the storefront had a public URL worth retiring (a draft never did)."""
    from .services.product_publish_service import storefront_listing_products

    try:
        instance._rs_was_public = storefront_listing_products(instance.store).filter(pk=instance.pk).exists()
    except Exception:                                                               # noqa: BLE001 — never block a delete on bookkeeping
        instance._rs_was_public = False


@receiver(post_delete, sender=Product)
def record_the_retired_public_url(sender, instance, **kwargs):
    """Write one audit row (store, slug) once the delete has COMMITTED — and only if the store itself still exists (a whole-store removal cascades everything)."""
    if not getattr(instance, "_rs_was_public", False) or not instance.slug:
        return
    store_id, slug, pk = instance.store_id, instance.slug, instance.pk

    def _record():
        from apps.core.services.audit_service import record_audit_event
        from apps.stores.models import Store

        store = Store.objects.filter(pk=store_id).first()
        if store is not None:
            record_audit_event(store=store, action_code=PRODUCT_HARD_DELETED, object_type="Product", object_id=pk, object_label=slug[:200], metadata={"slug": slug})

    transaction.on_commit(_record)
