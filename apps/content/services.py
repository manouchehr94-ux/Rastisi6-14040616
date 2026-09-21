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


def _reusable_media_placement_models():
    """MED-001 — هر مدل/فیلدِ ImageFieldِ قدیمیِ (legacy) رسانه‌ی
    قابل‌استفاده‌ی‌مجددِ Storefront که می‌تواند مستقیماً به یک مسیرِ فیزیکیِ
    فایل اشاره کند (نه از طریقِ ``MediaAsset``). این فهرست دقیقاً همانِ
    خانواده‌ی «رسانه‌ی قابل‌استفاده‌ی‌مجددِ Storefront»یِ MED-001 است —
    ``ProductImage``یِ کاتالوگ عمداً اینجا نیست (چرخه‌ی‌حیاتِ کاملاً جداست،
    نگاه کنید به مستندسازیِ ``is_physical_media_path_safe_to_delete``)."""
    from .models import HeroSlide, PromotionalBanner, StoryRailItem

    return (
        (HeroSlide, ("desktop_image", "mobile_image")),
        (PromotionalBanner, ("desktop_image", "mobile_image")),
        (StoryRailItem, ("image",)),
    )


def _legacy_field_still_claims_path(file_name: str) -> bool:
    """MED-001 — آیا هنوز حداقل یک ردیفِ ImageFieldِ *قدیمی*ِ رسانه‌ی
    قابل‌استفاده‌ی‌مجددِ Storefront (``HeroSlide.desktop_image``/
    ``mobile_image``، ``PromotionalBanner.desktop_image``/``mobile_image``،
    ``StoryRailItem.image``) — در هر Storeیی — دقیقاً به همینِ مسیرِ
    فیزیکی اشاره می‌دهد؟

    عمداً به هیچ Storeیی محدود نشده — این صرفاً یک پرسشِ «آیا این مسیرِ
    فیزیکی هنوز ادعا شده» است، نه یک پرسشِ داده‌یِ مستأجر؛ فقط یک مقدارِ
    بولی برمی‌گرداند (هرگز خودِ ردیف/Storeِ آن)، پس هیچ داده‌ی فروشگاهِ
    دیگری فاش نمی‌شود — فقط از فاش‌شدنِ *بایتِ فیزیکیِ* به‌اشتراک‌گذاشته‌شده
    جلوگیری می‌کند (نگاه کنید به RED 8 در گزارشِ MED-001)."""
    if not file_name:
        return False
    for model, field_names in _reusable_media_placement_models():
        for field_name in field_names:
            if model.objects.filter(**{field_name: file_name}).exists():
                return True
    return False


def _other_media_asset_alias_is_referenced(file_name: str, *, exclude_pk=None) -> bool:
    """MED-001 — آیا هنوز یک ردیفِ *دیگرِ* ``MediaAsset`` (در هر Storeیی)
    وجود دارد که ``image.name``اش دقیقاً همینِ مسیرِ فیزیکی است و آن ردیف
    خودش ``is_referenced()`` است (بررسیِ tenant-scopedِ همانِ ردیف، نسبت به
    Storeِ خودش)؟

    عمداً بینِ Storeها فیلتر نمی‌شود — یک نامِ فایلِ فیزیکیِ یکسان می‌تواند
    توسطِ دو ``MediaAsset`` در دو Storeِ متفاوت alias شود (وقتی
    ``_sync_asset_references`` یک ``MediaAsset`` تازه می‌سازد که مستقیماً
    به یک نامِ فایلِ *از قبل موجود* اشاره می‌کند، بدونِ آپلودِ دوباره —
    نگاه کنید به ``apps.storefront_builder.media_views._sync_asset_
    references``). این یک محافظتِ صرفاً فیزیکی/محافظه‌کارانه است، نه افشایِ
    داده‌ی مستأجر: تنها یک مقدارِ بولی برمی‌گردد، هرگز خودِ ردیف یا Storeِ
    آن (خودِ ``is_referenced()`` هم‌چنان کاملاً tenant-scoped می‌ماند —
    نگاه کنید به ``apps.content.media_reachability``)."""
    if not file_name:
        return False
    from .models import MediaAsset

    qs = MediaAsset.objects.filter(image=file_name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    for other in qs.iterator():
        if other.is_referenced():
            return True
    return False


def is_physical_media_path_safe_to_delete(file_name: str, *, exclude_asset_pk=None) -> bool:
    """MED-001 — تنها مرجعِ کانونیِ تصمیمِ «آیا این مسیرِ فیزیکیِ رسانه‌ی
    قابل‌استفاده‌ی‌مجددِ Storefront اکنون واقعاً می‌تواند حذف شود؟».

    این پرسش دربابِ *بایتِ فیزیکی* است، نه یک ردیفِ ``MediaAsset``ِ خاص —
    یک نامِ فایلِ فیزیکیِ واحد می‌تواند توسطِ چند ``MediaAsset`` (حتی در
    Storeهایِ متفاوت، از طریقِ alias بدونِ آپلودِ دوباره) و/یا چند
    ImageFieldِ قدیمی (پیش از Phase 0.5) هم‌زمان اشاره‌پذیر باشد. هرگز فرض
    نکنید یک ``MediaAsset``ِ بدون‌ارجاع یعنی خودِ بایت‌ها هم بدون‌ارجاعند.

    محافظه‌کارانه/fail-closed — دقیقاً همانِ قراردادِ
    ``media_reachability.is_reachable_via_json_or_snapshots``: هر خطایِ
    غیرِمنتظره «ناامن» تفسیر می‌شود (``False``) — یک خطا/ابهام هرگز نباید
    چراغِ سبزِ حذفِ فیزیکی باشد.

    هر فراخوانی که قصدِ حذفِ فیزیکیِ یک فایلِ رسانه‌ی قابل‌استفاده‌ی‌مجددِ
    Storefront را دارد — چه اکنون یک ردیفِ ``MediaAsset`` داشته باشد، چه
    فقط یک ImageFieldِ قدیمی، چه هر دو — باید دقیقاً پیش از
    ``storage.delete()`` همین تابع را صدا بزند (و ترجیحاً از *داخلِ* همانِ
    callbackِ ``transaction.on_commit``ی که خودِ حذف را انجام می‌دهد، تا
    بررسی رویِ تازه‌ترین وضعیتِ commit-شده اجرا شود، نه وضعیتِ پیش‌ازcommit —
    نگاه کنید به ``cleanup_reusable_media_file`` پایین‌تر و بخشِ Concurrency
    در گزارشِ MED-001 برایِ محدودیتِ باقی‌مانده‌ی این رویکرد).

    ``ProductImage``یِ کاتالوگ عمداً اینجا بررسی نمی‌شود — چرخه‌ی‌حیاتِ
    کاملاً جداییِ خودش را دارد (``apps.catalog.services.product_image_
    service``) و هرگز به این مرجع مسیریابی نمی‌شود (MED-001، مرزِ صریح)."""
    if not file_name:
        return False
    try:
        if _other_media_asset_alias_is_referenced(file_name, exclude_pk=exclude_asset_pk):
            return False
        if _legacy_field_still_claims_path(file_name):
            return False
        return True
    except Exception:
        return False


def cleanup_reusable_media_file(file_name, storage, *, exclude_asset_pk=None) -> None:
    """MED-001 — تنها نقطه‌یِ زمان‌بندیِ حذفِ فیزیکیِ فایل‌هایِ رسانه‌ی
    قابل‌استفاده‌ی‌مجددِ Storefront. حذفِ واقعی فقط **پس از commitِ موفقِ
    تراکنش** انجام می‌شود (``transaction.on_commit``) و بلافاصله پیش از
    خودِ ``storage.delete()``، ایمنیِ مسیرِ فیزیکی دوباره از طریقِ
    ``is_physical_media_path_safe_to_delete`` — رویِ وضعیتِ تازه‌ترینِ
    commit-شده — بازبینی می‌شود (نه فقط یک‌بار پیش از commit).

    این تابع خودش را «مالکِ» ردیفِ ``MediaAsset`` نمی‌داند — فقط نامِ فایل
    و storage را می‌گیرد، پس هم توسطِ حذفِ یک asset (``delete_media_asset_
    if_unreferenced``) و هم توسطِ fallbackِ قدیمیِ بدون‌asset (در
    ``apps.storefront_builder.media_views``/``apps.dashboard.views``)
    یکسان قابلِ‌استفاده است — بدونِ تکرارِ منطقِ حذف در چند جا.

    اگر ``file_name`` یا ``storage`` خالی باشد، بی‌صدا کاری نمی‌کند."""
    if not file_name or storage is None:
        return

    from django.db import transaction

    def _cleanup():
        if not storage.exists(file_name):
            return
        if not is_physical_media_path_safe_to_delete(file_name, exclude_asset_pk=exclude_asset_pk):
            return
        storage.delete(file_name)

    transaction.on_commit(_cleanup)


def delete_media_asset_if_unreferenced(asset) -> bool:
    """اگر ``asset`` دیگر توسط هیچ Placementی (در هیچ نسخه‌ای — Published،
    Draft یا بایگانی‌شده)، هیچ پس‌زمینه‌ی JSONای، و هیچ عکسِ بازیابی/
    baselineای ارجاع نمی‌شود، خودِ ردیفِ ``MediaAsset`` را بلادرنگ حذف
    می‌کند و ``True`` برمی‌گرداند.

    اگر هنوز حداقل یکی از آن‌ها به آن ارجاع می‌دهد، **هیچ کاری نمی‌کند** و
    ``False`` برمی‌گرداند — قانونِ حیاتیِ Phase 0.5: هرگز فایلِ فیزیکیِ
    زیرِ یک asset را حذف نکن اگر Placementِ دیگری (مثلاً نسخه‌ی Published)
    هنوز به همان ردیف اشاره می‌کند.

    MED-001: حذفِ خودِ ردیفِ متادیتا (این ردیفِ ``MediaAsset``ِ مشخص) از
    حذفِ *بایتِ فیزیکی* جدا شده است — حتی اگر همینِ ردیف بدون‌ارجاع باشد
    (و بنابراین خودش حذف شود)، بایتِ فیزیکیِ زیرِ آن فقط از طریقِ
    ``cleanup_reusable_media_file`` (یعنی مرجعِ کانونیِ
    ``is_physical_media_path_safe_to_delete``) حذف می‌شود — که خودش
    دوباره چک می‌کند آیا یک alias دیگر (یک ``MediaAsset``ِ دیگر با همانِ
    نامِ فایل، یا یک ImageFieldِ قدیمی) هنوز به همانِ مسیرِ فیزیکی نیاز
    دارد.

    ``asset`` می‌تواند ``None`` باشد (مثلاً وقتی Placementِ حذف‌شده هنوز از
    قبل از Phase 0.5 است و هیچ FKِ assetای نداشت) — در این حالت بی‌صدا
    ``False`` برمی‌گرداند؛ فراخوان مسئولِ رفتارِ fallback (پاک‌سازیِ فایلِ
    قدیمی از طریقِ همانِ ``cleanup_reusable_media_file``، نه دیگر یک
    ``storage.delete`` مستقیم) است، نه این تابع."""
    if asset is None:
        return False
    if asset.is_referenced():
        return False

    file_name = asset.image.name if asset.image else None
    storage = asset.image.storage if asset.image else None
    asset_pk = asset.pk
    asset.delete()

    cleanup_reusable_media_file(file_name, storage, exclude_asset_pk=asset_pk)
    return True


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
