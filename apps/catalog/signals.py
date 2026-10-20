"""همگام‌سازیِ مقدارِ مؤثرِ «استعلام قیمت» (``Product.is_price_inquiry``).

تنها نویسنده‌ی آن فیلد ``pricing_mode_service`` است؛ این سیگنال‌ها فقط آن را
هنگامِ تغییرِ *مرتبط* صدا می‌زنند. بازمحاسبه‌ی کل فروشگاه فقط وقتی اجرا می‌شود که
واقعاً چیزی که روی استعلام اثر دارد عوض شده باشد (حالتِ قیمتِ دسته/کالکشن، والدِ دسته،
فعال‌بودنِ کالکشن، عضویتِ کالکشن) — نه با هر ذخیره‌ی بی‌ربط (تغییرِ نام، ترتیب،
جابه‌جاییِ دسته‌ها). همه‌ی نوشتن‌ها با ``update()`` انجام می‌شود، پس بازگشتیِ سیگنال
وجود ندارد.
"""

from django.db.models.signals import post_delete, post_save, pre_save
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
