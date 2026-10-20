"""لایه‌ی سرویسِ کالکشنِ دستیِ مرچنت — همه‌ی نوشتن‌ها باید فقط از اینجا
عبور کنند (همان قرارداد ``brand_service``/``product_image_service``:
Store-scoped، تفکیکِ مستأجرِ صریح در هر کوئری، خطاهایِ تایپ‌شده‌ی
قابل‌نمایش، ``@transaction.atomic`` روی نوشتن‌هایِ چندردیفی)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from apps.catalog.models import MerchantCollection, MerchantCollectionItem, Product
from apps.catalog.services.product_publish_service import storefront_listing_products


class CollectionError(Exception):
    """خطای پایه‌ی قابل‌نمایش برای عملیاتِ کالکشن."""


class CollectionNotFoundError(CollectionError):
    """کالکشن یافت نشد یا متعلق به این فروشگاه نیست (fail-closed، هم برای
    شناسه‌ی ناموجود و هم برای شناسه‌ی متعلق به فروشگاهِ دیگر)."""


class ProductNotFoundError(CollectionError):
    """کالا یافت نشد یا متعلق به این فروشگاه نیست."""


class DuplicateProductError(CollectionError):
    """این کالا از قبل عضوِ همین کالکشن است."""


class CollectionReorderError(CollectionError):
    """ورودیِ مرتب‌سازی نامعتبر است (شناسه‌ی تکراری)."""


def _unique_slug(store, name: str, *, exclude_pk=None) -> str:
    base = slugify(name, allow_unicode=True).strip("-") or "collection"
    candidate = base
    counter = 2
    qs = MerchantCollection.objects.filter(store=store)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def get_scoped_collection(store, pk) -> MerchantCollection:
    """کالکشنِ ``pk`` را فقط اگر متعلق به همین Store باشد برمی‌گرداند —
    وگرنه ``CollectionNotFoundError`` (fail-closed، مستقل از این‌که pk
    اصلاً وجود ندارد یا متعلق به فروشگاهِ دیگری است)."""
    try:
        return MerchantCollection.objects.get(pk=pk, store=store)
    except MerchantCollection.DoesNotExist:
        raise CollectionNotFoundError(f"کالکشن {pk} متعلق به این فروشگاه نیست") from None


@transaction.atomic
def create_collection(
    store, *, name, description="", image=None, seo_title="", seo_description="", user=None,
    price_mode="standard",
) -> MerchantCollection:
    name = (name or "").strip()
    if not name:
        raise CollectionError("نام کالکشن نمی‌تواند خالی باشد.")
    actor = user if (user and user.is_authenticated) else None
    collection = MerchantCollection(
        store=store, name=name, slug=_unique_slug(store, name),
        description=description or "", seo_title=seo_title or "", seo_description=seo_description or "",
        created_by=actor, updated_by=actor, price_mode=price_mode,
    )
    if image is not None:
        collection.image = image
    try:
        collection.full_clean(exclude=["created_by", "updated_by"])
    except ValidationError as exc:
        raise CollectionError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    collection.save()
    return collection


@transaction.atomic
def update_collection(
    collection: MerchantCollection, *, name, description="", seo_title="", seo_description="",
    image=None, remove_image=False, user=None, price_mode=None,
) -> MerchantCollection:
    """اسلاگ عمداً هرگز با ویرایشِ نام دوباره ساخته نمی‌شود (همان قرارداد
    ``update_brand``) — تا لینکِ عمومیِ کالکشن پس از تغییرِ نام نشکند."""
    name = (name or "").strip()
    if not name:
        raise CollectionError("نام کالکشن نمی‌تواند خالی باشد.")
    collection.name = name
    collection.description = description or ""
    collection.seo_title = seo_title or ""
    collection.seo_description = seo_description or ""
    if image is not None:
        collection.image = image
    elif remove_image:
        collection.image = None
    if price_mode is not None:
        collection.price_mode = price_mode
    collection.updated_by = user if (user and user.is_authenticated) else None
    try:
        collection.full_clean(exclude=["created_by", "updated_by"])
    except ValidationError as exc:
        raise CollectionError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    collection.save()
    return collection


@transaction.atomic
def delete_collection(collection: MerchantCollection) -> None:
    """کالکشن و فقط ردیف‌هایِ ``MerchantCollectionItem`` آن حذف می‌شوند —
    ``Product`` هرگز لمس نمی‌شود (``MerchantCollectionItem.collection``
    است که ``on_delete=CASCADE`` دارد، نه رابطه‌ای که به Product برسد)."""
    collection.delete()


def activate_collection(collection: MerchantCollection) -> MerchantCollection:
    if not collection.is_active:
        collection.is_active = True
        collection.save(update_fields=["is_active", "updated_at"])
    return collection


def deactivate_collection(collection: MerchantCollection) -> MerchantCollection:
    if collection.is_active:
        collection.is_active = False
        collection.save(update_fields=["is_active", "updated_at"])
    return collection


@transaction.atomic
def add_product(collection: MerchantCollection, product: Product) -> MerchantCollectionItem:
    """افزودنِ صریحِ یک کالا — تکراری بودن یک خطایِ روشن است (نه نادیده‌
    گرفتنِ بی‌صدا)، چون این یک اقدامِ عمدیِ تکی است."""
    if product.store_id != collection.store_id:
        raise ProductNotFoundError("کالا متعلق به فروشگاه دیگری است.")
    if MerchantCollectionItem.objects.filter(collection=collection, product=product).exists():
        raise DuplicateProductError(f"«{product.name}» از قبل عضو این کالکشن است.")
    last = collection.items.order_by("-order").first()
    order = (last.order + 1) if last else 0
    return MerchantCollectionItem.objects.create(collection=collection, product=product, order=order)


@transaction.atomic
def add_products(collection: MerchantCollection, products) -> list[MerchantCollectionItem]:
    """افزودنِ دسته‌جمعیِ چند کالا (انتخابگرِ چندگانه) — بر خلافِ
    ``add_product``، کالایِ خارج از Store رد می‌شود (fail closed) اما
    کالایِ از‌قبل‌عضو بی‌صدا نادیده گرفته می‌شود (نه خطا)، چون این عملیات
    دسته‌جمعی است و کاربر معمولاً همان انتخابِ قبلی را دوباره تیک نمی‌زند
    بلکه چند مورد را با هم انتخاب می‌کند — یک خطا برای کلِ دسته به‌خاطرِ
    یک تکراریِ داخلش، UX نامعقولی است. کالکشن نتیجه هرگز نصفه‌کاره نیست:
    یا همه‌ی موارد معتبر اضافه می‌شوند یا (در خطای واقعی) هیچ‌کدام."""
    existing_ids = set(collection.items.values_list("product_id", flat=True))
    last = collection.items.order_by("-order").first()
    next_order = (last.order + 1) if last else 0
    created = []
    for product in products:
        if product.store_id != collection.store_id:
            continue
        if product.pk in existing_ids:
            continue
        created.append(MerchantCollectionItem(collection=collection, product=product, order=next_order))
        existing_ids.add(product.pk)
        next_order += 1
    if created:
        MerchantCollectionItem.objects.bulk_create(created)
    return created


@transaction.atomic
def remove_product(collection: MerchantCollection, item_id: int) -> None:
    try:
        item = MerchantCollectionItem.objects.get(pk=item_id, collection=collection)
    except MerchantCollectionItem.DoesNotExist:
        raise ProductNotFoundError(f"قلم {item_id} متعلق به این کالکشن نیست") from None
    item.delete()


@transaction.atomic
def reorder_items(collection: MerchantCollection, ordered_item_ids: list[int]) -> None:
    """قرارداد (مطابقِ ``storefront_section_reorder``/``reorder_brands``
    فاز A): شناسه‌ی تکراری کل عملیات را رد می‌کند؛ شناسه‌ی خارج از این
    کالکشن بی‌صدا حذف می‌شود؛ شناسه‌یِ معتبرِ غایب از فهرستِ پست‌شده دست‌
    نخورده می‌ماند (نه حذف، نه تغییرِ ترتیب)؛ کل عملیات یک تراکنشِ واحد
    است — یا ترتیبِ کامل ذخیره می‌شود یا هیچ‌کدام."""
    if len(set(ordered_item_ids)) != len(ordered_item_ids):
        raise CollectionReorderError("فهرست مرتب‌سازی شامل شناسه‌ی تکراری است.")

    valid_id_set = set(collection.items.values_list("pk", flat=True))
    ordered_valid_ids = [item_id for item_id in ordered_item_ids if item_id in valid_id_set]
    for order, item_id in enumerate(ordered_valid_ids):
        MerchantCollectionItem.objects.filter(pk=item_id, collection=collection).update(order=order)


def searchable_products(store, query: str = ""):
    """کالاهایِ این Store برایِ انتخابگرِ افزودنِ کالا به کالکشن — همه‌یِ
    وضعیت‌های انتشار (فعال/غیرفعال/پیش‌نویسِ تکمیل‌شده) نمایش داده
    می‌شوند چون این یک ابزارِ مدیریتی است، نه فهرستِ عمومی؛ وضعیتِ هرکالا
    باید در UI به‌وضوح نشان داده شود. پیش‌نویسِ داخلیِ ناتمام
    (``is_draft_placeholder``) هرگز نتیجه نیست."""
    qs = Product.objects.filter(store=store, is_draft_placeholder=False).select_related("brand").prefetch_related("images")
    query = (query or "").strip()
    if query:
        from apps.catalog.services.search_service import apply_text_search

        qs = apply_text_search(qs, query, fields=("name", "sku"))
    return qs.order_by("name")


def public_collection_queryset(store):
    """کالکشن‌هایِ فعالِ این Store — تنها منبعِ حقیقتِ نمایشِ عمومی، هم برایِ
    صفحه‌ی ایندکس و هم به‌عنوانِ پایه‌ی lookup صفحه‌ی جزئیات (کالکشنِ
    غیرفعال یا متعلق به فروشگاهِ دیگر هرگز اینجا نیست)."""
    return MerchantCollection.objects.filter(store=store, is_active=True).order_by("name")


def collection_visible_items(collection: MerchantCollection, store):
    """قلم‌هایِ این کالکشن که کالایشان از نظرِ storefront قابل‌مشاهده است
    (``storefront_listing_products`` — همان منطقِ فهرست/جست‌وجو، بدونِ
    تکرارِ قوانینِ نمایش)، به ترتیبِ دستیِ کالکشن."""
    visible_products = storefront_listing_products(store)
    return (
        collection.items.filter(product__in=visible_products)
        .select_related("product__brand", "product__category")
        .prefetch_related("product__images")
        .order_by("order", "id")
    )
