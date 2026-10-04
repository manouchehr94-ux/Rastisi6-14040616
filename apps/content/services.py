"""سرویس حل مقصد — تبدیل مقصد ذخیره‌شده به URL قابل رندر.

این ماژول تنها نقطه‌ی مسئول تبدیل مقصد ذخیره‌شده به URL نهایی است.
هرگز '#' برنمی‌گرداند. اگر مقصدی معتبر نباشد، None برمی‌گرداند.
"""

from django.urls import reverse

from .models import DestinationType


def resolve_destination_url(instance) -> str | None:
    """URL مقصد را بر اساس نوع و مقادیر FK حل می‌کند.

    بازمی‌گرداند:
    - URL معتبر (رشته) اگر مقصد قابل حل باشد
    - None اگر مقصدی وجود نداشته باشد یا شیء مقصد حذف شده باشد

    هرگز بازنمی‌گرداند:
    - '#'
    - مسیر ساختگی
    - URL خطرناک
    """
    dtype = instance.destination_type

    if dtype == DestinationType.NONE:
        return None

    if dtype == DestinationType.CATEGORY:
        category = instance.destination_category
        if category is None:
            return None
        return reverse("catalog:product-list") + f"?category={category.slug}"

    if dtype == DestinationType.PRODUCT:
        product = instance.destination_product
        if product is None:
            return None
        return reverse("catalog:product-detail", args=[product.slug])

    if dtype == DestinationType.BRAND:
        brand = instance.destination_brand
        if brand is None:
            return None
        return reverse("catalog:product-list") + f"?brand={brand.slug}"

    if dtype == DestinationType.COLLECTION:
        collection = instance.destination_collection
        if collection is None:
            return None
        return reverse("catalog:collection-detail", args=[collection.slug])

    if dtype == DestinationType.SEARCH:
        return reverse("catalog:product-list")

    if dtype == DestinationType.CART:
        return reverse("cart:detail")

    if dtype == DestinationType.EXTERNAL:
        url = (instance.destination_external_url or "").strip()
        return url if url else None

    return None


def resolve_destination_context(instance) -> dict:
    """اطلاعات کامل مقصد برای رندر در تمپلیت.

    بازمی‌گرداند دیکشنری شامل:
    - url: آدرس مقصد یا None
    - open_new_tab: بولین
    - rel: مقدار rel برای لینک‌های خارجی (noopener noreferrer)
    """
    url = resolve_destination_url(instance)
    is_external = instance.destination_type == DestinationType.EXTERNAL

    return {
        "url": url,
        "open_new_tab": instance.open_in_new_tab,
        "rel": "noopener noreferrer" if (is_external and instance.open_in_new_tab) else "",
    }


def resolve_destination_setting(store, destination: dict | None) -> dict:
    """معادل ``resolve_destination_context`` برای مقصدهای ذخیره‌شده در JSON
    (نه یک شیء مدل ``DestinationMixin``) — یعنی بلوک ``destination`` داخل
    ``StorefrontSection.settings`` (سازنده بصری).

    برخلاف ``section_registry.validate_destination_settings`` (که فقط شکل/
    enum را چک می‌کند و هرگز دیتابیس را لمس نمی‌کند)، این تابع همان لایه‌ای
    است که مالکیت Store را چک می‌کند — دقیقاً همان تفکیک مسئولیتی که
    ``section_data_service.resolve_products`` برای منابع داده محصول دارد.
    ارجاع حذف‌شده/غیرفعال/متعلق به فروشگاه دیگر بی‌صدا به «بدون مقصد»
    (``url=None``) تبدیل می‌شود — هرگز کرش نمی‌کند."""
    destination = destination or {}
    dtype = destination.get("destination_type", DestinationType.NONE)
    open_in_new_tab = bool(destination.get("open_in_new_tab", False))
    url = None

    if dtype == DestinationType.CATEGORY:
        from apps.catalog.models import Category

        url = _category_url(store, destination.get("destination_id"), Category)
    elif dtype == DestinationType.PRODUCT:
        from apps.catalog.models import Product

        url = _product_url(store, destination.get("destination_id"), Product)
    elif dtype == DestinationType.BRAND:
        from apps.catalog.models import Brand

        url = _brand_url(store, destination.get("destination_id"), Brand)
    elif dtype == DestinationType.COLLECTION:
        from apps.catalog.models import MerchantCollection

        url = _collection_url(store, destination.get("destination_id"), MerchantCollection)
    elif dtype == DestinationType.SEARCH:
        url = reverse("catalog:product-list")
    elif dtype == DestinationType.CART:
        url = reverse("cart:detail")
    elif dtype == DestinationType.EXTERNAL:
        raw_url = (destination.get("destination_external_url") or "").strip()
        url = raw_url or None

    is_external = dtype == DestinationType.EXTERNAL
    return {
        "url": url,
        "open_new_tab": open_in_new_tab,
        "rel": "noopener noreferrer" if (is_external and open_in_new_tab) else "",
    }


def resolve_background_media_url(store, background: dict | None) -> str | None:
    """URL نهاییِ قابل‌رندرِ پس‌زمینه‌یِ یک section را حل می‌کند — Phase 1
    correction (tenant safety): ``section_registry.validate_background_settings``
    فقط ``media_asset_id`` را به‌شکلِ یک عددِ صحیحِ ساده اعتبارسنجی می‌کند
    (بدونِ دسترسی به دیتابیس)؛ این تابع همان لایه‌ای است که مالکیتِ Store
    را واقعاً چک می‌کند — دقیقاً همان تفکیکِ مسئولیتی که
    ``resolve_destination_setting`` بالا برایِ بلوکِ ``destination`` دارد.

    ``mode`` غیرِ ``"image"`` یا ``media_asset_id`` غایب/متعلق به فروشگاهِ
    دیگر/حذف‌شده همیشه ``None`` برمی‌گرداند — هرگز کرش نمی‌کند، هرگز رسانه‌ی
    فروشگاهِ دیگری را برنمی‌گرداند."""
    background = background or {}
    if background.get("mode") != "image":
        return None
    media_asset_id = background.get("media_asset_id")
    if not media_asset_id:
        return None

    from .models import MediaAsset

    try:
        asset = MediaAsset.objects.get(pk=media_asset_id, store=store)
    except MediaAsset.DoesNotExist:
        return None
    return asset.image.url


def _category_url(store, pk, Category):
    if not pk:
        return None
    try:
        category = Category.objects.get(pk=pk, store=store, is_active=True)
    except Category.DoesNotExist:
        return None
    return reverse("catalog:product-list") + f"?category={category.slug}"


def _product_url(store, pk, Product):
    if not pk:
        return None
    try:
        product = Product.objects.get(pk=pk, store=store)
    except Product.DoesNotExist:
        return None
    return reverse("catalog:product-detail", args=[product.slug])


def _brand_url(store, pk, Brand):
    if not pk:
        return None
    try:
        brand = Brand.objects.get(pk=pk, store=store, is_active=True)
    except Brand.DoesNotExist:
        return None
    return reverse("catalog:product-list") + f"?brand={brand.slug}"


def _collection_url(store, pk, MerchantCollection):
    if not pk:
        return None
    try:
        collection = MerchantCollection.objects.get(pk=pk, store=store, is_active=True)
    except MerchantCollection.DoesNotExist:
        return None
    return reverse("catalog:collection-detail", args=[collection.slug])


# ---------------------------------------------------------------- Media Asset cleanup (Phase 0.5)
#
# Explicit service function, deliberately NOT a Django signal (post_delete/
# pre_delete) — per the Phase 0.5 brief: "avoid fragile Django signals that
# delete files blindly on row deletion; prefer an explicit asset cleanup
# service." A signal fired on every Placement delete would have no easy way
# to express "only delete the physical file if truly nothing else still
# needs it" without duplicating this exact same reference check anyway —
# an explicit, callable function keeps that decision visible at every call
# site instead of hidden in signal-dispatch order.


# ---------------------------------------------------------------- MED-001 — RETENTION-FIRST policy (binding architect decision)
#
# BINDING POLICY (MED-001, architect decision — supersedes the earlier
# "delete-if-unreferenced" contract that shipped in the first MED-001
# repair): for the reusable-Storefront-media family (HeroSlide,
# PromotionalBanner, StoryRailItem, MediaAsset, section-background
# MediaAsset references, history/baseline-recoverable media), ONLINE /
# REQUEST-TIME code must NEVER automatically destroy either:
#
#   1. the physical storage bytes, OR
#   2. an unreferenced ``MediaAsset`` metadata row
#
# merely because current reachability happens to be zero at the instant of
# the check. This is deliberately conservative: a small storage/metadata
# leak (an orphaned file, an orphaned ``MediaAsset`` row) is an ACCEPTABLE
# cost for this P0; destroying bytes or rows that are, or could become
# again, legitimately referenced (via a concurrent write, an Undo/Redo, a
# restored version, a revived background/history/baseline snapshot) is
# NOT acceptable — that would be actual, irreversible data loss.
#
# WHY: the concurrency investigation for this P0 proved that a
# check-then-storage.delete design (even one that re-checks safety inside
# the ``transaction.on_commit`` callback, immediately before the physical
# delete) still has a real, provable attach-vs-delete TOCTOU race — a
# concurrent transaction can commit a brand-new reference (a new
# ``MediaAsset`` alias row, a revived Placement via Undo/Redo, a clone via
# Draft/Restore, a background-JSON write) to the exact same physical path
# in the narrow window between the safety re-check and the actual
# ``storage.delete()`` call, because ``storage.delete()`` is not a
# database operation and cannot be made atomic with any DB-side lock/check
# without either (a) making the physical delete happen while a DB lock is
# still held — which would require deleting bytes BEFORE the deciding
# transaction commits, directly violating the separately-required
# "physical delete only after successful commit" rule — or (b) a
# fully-serialized, schema-backed lock-identity/GC architecture that is
# explicitly out of scope for this P0 (deferred to a later, separately
# designed task; see the module-level note at the bottom of this section).
#
# THE FIX FOR THIS P0: remove the destructive side entirely from online
# mutation paths. If nothing here ever deletes bytes or rows, there is no
# window in which a concurrent writer can lose a race against a delete —
# there is no delete to race against. This is a genuine, provable
# elimination of the race for this P0, not a narrowing of it.
#
# ``delete_media_asset_if_unreferenced`` and ``cleanup_reusable_media_file``
# remain the ONE canonical retention/cleanup authority for this media
# family — every call site that used to reach for a raw ``storage.delete``
# still funnels through these two functions, unchanged in shape/signature,
# so there is exactly one place this policy is enforced. Their *contract*
# changes (no more destructive action for this reusable-media family);
# their *names* are kept as-is (renaming across the whole codebase is out
# of scope for this narrow P0) but are now retention-first by design.
#
# FUTURE WORK (explicitly NOT designed or implemented here): durable,
# serialized reusable-media garbage collection (e.g. a deferred/tombstoned
# sweep, a persistent path-identity lock row, or a PostgreSQL advisory-
# lock-backed reclaim job) is deferred to a separate, later-architected
# task. Nothing below should be read as a design for that future task.


def _reusable_media_placement_models():
    """MED-001 — هر مدل/فیلدِ ImageFieldِ قدیمیِ (legacy) رسانه‌ی
    قابل‌استفاده‌ی‌مجددِ Storefront که می‌تواند مستقیماً به یک مسیرِ فیزیکیِ
    فایل اشاره کند (نه از طریقِ ``MediaAsset``). این فهرست دقیقاً همانِ
    خانواده‌ی «رسانه‌ی قابل‌استفاده‌ی‌مجددِ Storefront»یِ MED-001 است —
    ``ProductImage``یِ کاتالوگ عمداً اینجا نیست (چرخه‌ی‌حیاتِ کاملاً جداست).
    باقی مانده صرفاً برایِ مستندسازیِ خانواده‌یِ MED-001 — دیگر توسطِ
    مسیرِ retention-first زیر خوانده نمی‌شود (نگاه کنید به یادداشتِ
    Retention-First بالا)."""
    from .models import HeroSlide, PromotionalBanner, StoryRailItem

    return (
        (HeroSlide, ("desktop_image", "mobile_image")),
        (PromotionalBanner, ("desktop_image", "mobile_image")),
        (StoryRailItem, ("image",)),
    )


def cleanup_reusable_media_file(file_name, storage, *, exclude_asset_pk=None) -> None:
    """MED-001 (Retention-First، تصمیمِ معمار — جانشینِ صریحِ نسخه‌ی قبلی):
    این تابع دیگر **هیچ حذفِ فیزیکی‌ای برایِ خانواده‌یِ رسانه‌یِ
    قابل‌استفاده‌ی‌مجددِ Storefront انجام نمی‌دهد**. عمداً یک no-op کانونیِ
    نگه‌داری (retention boundary) است — نه حذف شده، نه ساده‌سازی‌شده به
    هیچ‌کاری، بلکه صریحاً نگه داشته شده تا هر فراخوانِ قبلی/آینده‌ای که
    قبلاً به اینجا مسیریابی می‌شد همچنان از طریقِ همینِ یک مرجعِ کانونیک
    عبور کند — بدونِ اینکه لازم باشد فراخوان‌کننده‌ها را حذف/جایگزین کرد.

    چرا: بررسیِ هم‌زمانیِ MED-001 ثابت کرد که یک الگویِ check-then-delete —
    حتی اگر بازبینیِ ایمنی داخلِ callbackِ ``transaction.on_commit`` اجرا
    شود — بازهم یک پنجره‌یِ واقعیِ TOCTOU بینِ «تصمیمِ ایمن‌بودن» و خودِ
    ``storage.delete()`` باقی می‌گذارد، چون ``storage.delete()`` یک عملیاتِ
    دیتابیسی نیست و نمی‌تواند با هیچ قفلِ سمتِ دیتابیس اتمیک شود بدونِ
    اینکه یا حذفِ فیزیکی را پیش از commit ببرد (که قانونِ «حذفِ فیزیکی
    فقط پس از commitِ موفق» را نقض می‌کند) یا یک معماریِ کاملاً جدیدِ
    schema-backed بسازد (که خارج از حیطه‌یِ همینِ P0 است).

    راه‌حلِ این P0: حذفِ کاملِ سمتِ مخربِ مسیرهایِ آنلاین. اگر هیچ‌جا هیچ‌وقت
    بایتی حذف نشود، هیچ پنجره‌ای برایِ رقابتِ نویسنده‌یِ هم‌زمان با یک حذف
    وجود ندارد — چون اصلاً حذفی نیست که با آن رقابت شود.

    ``transaction.on_commit`` عمداً همچنان فراخوانی می‌شود (نه حذف شده) —
    اگر در آینده این نقطه‌ی نگه‌داری جایگزینِ یک معماریِ GCِ سریالایز/
    durable شود، ساختارِ callbackِ post-commit همینجا از قبل آماده است؛
    فعلاً آن callback عمداً کاری نمی‌کند."""
    if not file_name or storage is None:
        return

    from django.db import transaction

    def _cleanup():
        # MED-001 Retention-First: عمداً بدونِ storage.delete — نگاه کنید
        # به یادداشتِ کانونیِ Retention-First در بالایِ همین بخش از فایل.
        return None

    transaction.on_commit(_cleanup)


def delete_media_asset_if_unreferenced(asset) -> bool:
    """MED-001 (Retention-First، تصمیمِ معمار — جانشینِ صریحِ نسخه‌ی قبلی):
    نامِ این تابع تاریخی و اکنون تاحدی گمراه‌کننده است («delete»)، اما
    عمداً در این P0 بازنامگذاری نشده (بازنامگذاریِ سراسریِ آن در کلِ کدبیس
    خارج از حیطه‌یِ این ترمیمِ محدود است). قراردادِ *رفتاریِ* آن اکنون
    کاملاً نگه‌دارنده (retention-first) است:

    * ``asset is None`` → no-op امن، ``False``.
    * ``asset`` هنوز ارجاع‌شده (``asset.is_referenced()`` True) → نگه‌داشته
      می‌شود، ``False``.
    * ``asset`` اکنون بدون‌ارجاعِ قابلِ‌استفاده‌ی‌مجدد است → **بازهم نگه‌
      داشته می‌شود** (نه ردیفِ ``MediaAsset``اش حذف می‌شود، نه فایلِ
      فیزیکیِ زیرِ آن)، ``False``.

    این تابع دیگر **هرگز** ``asset.delete()`` صدا نمی‌زند و **هرگز** بایتِ
    فیزیکی را حذف نمی‌کند — برایِ هر دو حالت.

    چرا نگه‌داشتنِ خودِ ردیفِ متادیتا هم لازم است (نه صرفاً بایت‌ها): پس‌
    زمینه‌ی JSON، Undo/Redo، تاریخچه، baselineِ قالب، یا یک نوشتنِ هم‌زمانِ
    دیگر می‌توانند به‌طورِ کاملاً مجاز idِ همینِ ``MediaAsset`` را نگه دارند
    یا دوباره زنده کنند (نگاه کنید به بررسیِ هم‌زمانیِ MED-001، بخشِ
    «نقشه‌یِ authorityهایِ ایجادِ ارجاع» — Undo/Redo مستقیماً یک Placementِ
    تازه با همانِ FKِ قدیمی می‌سازد). حذفِ خودِ ردیفِ متادیتا، حتی اگر بایتِ
    فیزیکی زنده بماند، یک ریسکِ مسابقه‌یِ *ارجاعِ شکسته*‌یِ جداگانه می‌سازد
    (یک FK به یک ردیفِ حذف‌شده). پس صفرِ فعلیِ reachability هرگز اختیارِ
    کافی برایِ حذفِ ردیفِ ``MediaAsset`` در کدِ آنلاین/runtime نیست — هم
    ردیف و هم فایل، هر دو، نگه داشته می‌شوند.

    P0ِ همگام‌سازی: تضمینِ TOCTOU با حذفِ کاملِ سمتِ مخربِ این مسیرهایِ
    آنلاین به‌دست می‌آید، نه با ادعایِ یک قفلِ check-and-delete اتمیک —
    نگاه کنید به یادداشتِ کانونیِ Retention-First در بالایِ همین بخش."""
    if asset is None:
        return False
    # MED-001 Retention-First: صرفِ خوانشِ is_referenced() اینجا دیگر برایِ
    # هیچ اقدامِ مخربی استفاده نمی‌شود — فقط برایِ گزارش‌دهیِ صادقانه‌یِ
    # بازگشتی (``False`` در هر دو حالت، اما مستندسازی/لاگ‌گذاریِ آینده
    # می‌تواند این تفکیک را حفظ کند بدونِ اینکه رفتار عوض شود).
    asset.is_referenced()
    return False


class NewsletterSubscribeError(ValueError):
    """ایمیلِ خامِ ارسال‌شده به بلوکِ «خبرنامه» نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به بازدیدکننده."""


def subscribe_to_newsletter(store, raw_email: str):
    """ایمیل را (پس از اعتبارسنجیِ شکل) به‌ازای همین ``store`` ثبت می‌کند.

    دقیقاً همان الگویِ idempotent محلِ دیگرِ کدبیس (مثلِ
    ``StorefrontLayout.provision_for``) — عضویتِ دوباره‌یِ همان ایمیل هرگز
    خطا نیست، فقط همان ردیفِ موجود را برمی‌گرداند (``created=False``)."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.core.validators import EmailValidator

    from .models import NewsletterSubscriber

    email = (raw_email or "").strip().lower()
    if not email:
        raise NewsletterSubscribeError("ایمیل را وارد کنید")
    try:
        EmailValidator()(email)
    except DjangoValidationError as exc:
        raise NewsletterSubscribeError("ایمیلِ واردشده معتبر نیست") from exc

    return NewsletterSubscriber.objects.get_or_create(store=store, email=email)
