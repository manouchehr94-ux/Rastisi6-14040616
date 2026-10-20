"""چرخه‌ی عمرِ پیش‌نویسِ داخلیِ «افزودنِ کالا» (Product Entry full-page rebuild).

ریشه‌ی مشکلی که این ماژول حل می‌کند: پیش از این، صفحه‌ی «افزودنِ کالا» تا
وقتی نام/کدِ کالا و دسته‌بندی پر نمی‌شد هیچ ردیفِ واقعیِ ``Product`` نداشت،
پس ویژگی‌ها/تنوع‌ها/تصاویر (که همه به یک ``product_id`` واقعی نیاز دارند)
نمی‌توانستند پیش از آن تکمیل ذخیره شوند — دقیقاً همان چیزی که تبِ «قیمت و
تنوع» را با پیامِ «ابتدا اطلاعاتِ پایه را تکمیل کنید» قفل می‌کرد.

راه‌حل: به‌محضِ باز شدنِ صفحه‌ی «افزودنِ کالا»، یک ``Product`` واقعی با
``is_draft_placeholder=True`` ساخته یا (اگر از قبل یکی نیمه‌کاره مانده) از سر
گرفته می‌شود. این پرچم کاملاً مستقل از ``Product.status`` (پیش‌نویس/فعال/
غیرفعال، که وضعیتِ انتشارِ *واقعیِ* کالا را کنترل می‌کند) است — فقط یعنی
«این ردیف هنوز یک تلاشِ کامل‌نشده برای ساختِ کالاست»، و به همین دلیل هرگز:

- در فهرست/آمارِ کالاهای پنل (``filtered_products``/``_product_list_context``)
- در شمارشگرِ سقفِ اشتراک (``usage_service._count_products``)
- در هیچ کوئریِ فروشگاه/عمومی

ظاهر نمی‌شود. ذخیره‌ی نهاییِ معتبر (``_save_product`` در ``apps.dashboard.views``،
وقتی فرم با نام/کد/دسته‌بندی/قیمتِ واقعی معتبر است) همیشه این پرچم را
``False`` می‌کند — از آن لحظه یک کالای عادی و کامل است.

تک‌رکورد بودنِ پیش‌نویس در هر Store: چون ``(store, sku)`` و ``(store, slug)``
یکتا هستند و پیش‌نویسِ تازه هر دو را خالی می‌گذارد، هر Store در هر لحظه
حداکثر یک پیش‌نویسِ دست‌نخورده می‌تواند داشته باشد؛ ``get_or_create_product_draft``
دقیقاً همین محدودیت را از عمد به‌جای «یک پیش‌نویسِ اخیرِ قابلِ‌ازسرگیری در هر
جریانِ ساخت» انتخاب می‌کند (رجوع کنید به گزارشِ ریشه‌ای، بخشِ معماریِ پیش‌نویس)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import Product


@dataclass
class DraftCleanupResult:
    deleted_count: int
    deleted_ids: list[int]


def get_or_create_product_draft(store, user) -> Product:
    """پیش‌نویسِ نیمه‌کاره‌ی همین Store را از سر می‌گیرد، یا اگر نبود یکی می‌سازد.

    گیتِ سقفِ اشتراک (``enforce_can_create_product``) فقط هنگامِ *ساختِ* یک
    پیش‌نویسِ تازه اجرا می‌شود — نه هنگامِ ازسرگیریِ یکی که از قبل وجود دارد؛
    این دقیقاً همان نقطه‌ای است که پیش‌تر (پیش از معماریِ پیش‌نویس) این گیت در
    ``_save_product`` روی مسیرِ «کالایِ کاملاً تازه» اجرا می‌شد."""
    existing = (
        Product.objects.filter(store=store, is_draft_placeholder=True)
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return existing

    from apps.dashboard.services.catalog_admin_service import default_vendor
    from apps.subscriptions.services.enforcement import enforce_can_create_product

    enforce_can_create_product(store)
    vendor = default_vendor(store)
    return Product.objects.create(
        store=store,
        vendor=vendor,
        category=None,
        price=Decimal("0"),
        is_draft_placeholder=True,
        draft_created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def discard_product_draft(product: Product) -> None:
    """پیش‌نویس (و تصاویر/فایل‌هایِ آن) را کاملاً حذف می‌کند — برایِ اکشنِ صریحِ
    «انصراف» کاربر؛ فراخوان باید پیش از این، ``is_draft_placeholder`` و مالکیتِ
    Store را بررسی کرده باشد (نگاه کنید به ``product_discard_draft`` در
    ``apps.dashboard.views``)."""
    _delete_product_and_files(product)


def cleanup_stale_product_drafts(*, older_than_hours: int = 48, now=None) -> DraftCleanupResult:
    """پیش‌نویس‌های رهاشده‌ی قدیمی‌تر از ``older_than_hours`` را حذف می‌کند.

    Idempotent و batch-safe: بر رویِ ``updated_at`` (نه ``created_at``) فیلتر
    می‌کند، پس هر فعالیتِ merchant (حتی فقط بازکردنِ دوباره‌ی صفحه که رکورد را
    resume/touch می‌کند) تایمر را ریست می‌کند و پیش‌نویسِ در حالِ کار هرگز حذف
    نمی‌شود — نگاه کنید به دستورِ مدیریتیِ
    ``cleanup_stale_product_drafts``."""
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(hours=older_than_hours)
    stale = list(
        Product.objects.filter(is_draft_placeholder=True, updated_at__lt=cutoff)
    )
    deleted_ids = [p.pk for p in stale]
    for product in stale:
        _delete_product_and_files(product)
    return DraftCleanupResult(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


def touch_product_draft(product: Product) -> None:
    """``updated_at`` را به‌روز می‌کند تا پاک‌سازیِ خودکار پیش‌نویسِ در حالِ کار
    را حذف نکند — روی هر GET موفقِ صفحه‌ی ویرایش برایِ یک پیش‌نویس صدا زده
    می‌شود (نگاه کنید به ``product_form`` در ``apps.dashboard.views``)."""
    Product.objects.filter(pk=product.pk).update(updated_at=timezone.now())


def _delete_product_and_files(product: Product) -> None:
    for image in product.images.all():
        if image.image:
            from apps.catalog.services.product_image_service import _delete_original

            _delete_original(image.image.name)
            image.image.delete(save=False)
        if image.thumbnail:
            image.thumbnail.delete(save=False)
    product.delete()
