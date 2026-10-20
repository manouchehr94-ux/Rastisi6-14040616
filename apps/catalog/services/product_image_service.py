"""سرویس مدیریت گالری تصاویر کالا — آپلود، اعتبارسنجی، تغییر اندازه و بندانگشتی.

قواعد:
- فرمت‌های مجاز: jpg/jpeg/png/webp، حداکثر حجم ۵ مگابایت.
- تصویر اصلی اگر از حد مجاز بزرگ‌تر باشد خودکار کوچک می‌شود (بدون افت کیفیت
  برای تصاویر کوچک‌تر — Pillow.thumbnail فقط در صورت نیاز کوچک می‌کند).
- برای هر تصویر یک نسخه‌ی بندانگشتی هم ساخته می‌شود تا صفحات سریع‌تر باز شوند.
- اولین تصویر هر کالا خودکار کاور می‌شود؛ با حذف کاور، تصویر بعدی (طبق ترتیب)
  خودکار جایگزین می‌شود تا کالای دارای تصویر همیشه یک کاور مشخص داشته باشد.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.crypto import get_random_string
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.catalog.models import ProductImage

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
EXTENSION_BY_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

MAX_DIMENSION = 2000
THUMBNAIL_DIMENSION = 400


class ProductImageError(Exception):
    """خطای قابل‌نمایش هنگام اعتبارسنجی/پردازش تصویر کالا."""


class ProductImageReorderError(ProductImageError):
    """ورودیِ مرتب‌سازی نامعتبر است (شناسه‌ی تکراری) — هیچ ردیفی تغییر نکرد."""


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def validate_image_file(file) -> None:
    """پسوند، حجم و معتبربودن واقعی فایل (فرمتِ تشخیص‌داده‌شدهٔ Pillow + سقف پیکسل) را بررسی می‌کند؛ در خطا ProductImageError می‌دهد."""
    from django.core.exceptions import ValidationError

    from apps.core.image_validation import open_and_verify

    ext = _extension(getattr(file, "name", ""))
    if ext not in ALLOWED_EXTENSIONS:
        allowed = "، ".join(sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS))
        raise ProductImageError(f"فرمت تصویر مجاز نیست. فرمت‌های مجاز: {allowed}")

    if file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ProductImageError("حجم تصویر نباید بیشتر از ۵ مگابایت باشد.")

    try:
        open_and_verify(file, label="تصویر", formats=tuple(ALLOWED_PIL_FORMATS))
    except ValidationError as exc:
        raise ProductImageError(exc.messages[0]) from exc
    finally:
        file.seek(0)


def _shrink_to_fit(image: Image.Image, max_dimension: int) -> Image.Image:
    resized = image.copy()
    resized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return resized


def _encode(image: Image.Image, fmt: str) -> bytes:
    buffer = BytesIO()
    save_kwargs = {"quality": 85, "optimize": True} if fmt in ("JPEG", "WEBP") else {}
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def _load_normalized_image(file):
    file.seek(0)
    try:
        opened = Image.open(file)
        opened.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProductImageError("فایل انتخاب‌شده تصویر معتبری نیست یا ناقص است.") from exc

    fmt = (opened.format or "JPEG").upper()
    if fmt not in ALLOWED_PIL_FORMATS:
        fmt = "JPEG"

    pil_image = ImageOps.exif_transpose(opened) or opened
    if fmt == "JPEG" and pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")
    elif fmt in ("PNG", "WEBP") and pil_image.mode not in ("RGB", "RGBA"):
        pil_image = pil_image.convert("RGBA")

    return pil_image, fmt


ORIGINALS_DIR = "products/originals"


def original_storage_name(main_name: str) -> str:
    """مسیرِ نسخهٔ اصلیِ آپلودشده برای یک تصویرِ کالا — از نامِ فایلِ اصلی مشتق می‌شود (بدون ستونِ جدید/Migration)."""
    return f"{ORIGINALS_DIR}/{(main_name or '').rsplit('/', 1)[-1]}"


def _keep_original(file, final_name: str) -> None:
    """R4-14 — بایت‌های آپلودشدهٔ فروشنده بدونِ هیچ تغییری کنارِ نسخه‌های نمایشی (≤۲۰۰۰px و بندانگشتی) نگه داشته می‌شود؛
    پردازش غیرمخرب است و اگر روزی نسخهٔ نمایشی عوض شود، اصلِ فایل در دسترس است. خطای ذخیره‌سازیِ این نسخه مانعِ آپلود نمی‌شود."""
    from django.core.files.storage import default_storage

    try:
        file.seek(0)
        default_storage.save(original_storage_name(final_name), ContentFile(file.read()))
    except Exception:  # pragma: no cover - best effort, never blocks the upload
        pass
    finally:
        file.seek(0)


def _delete_original(main_name: str) -> None:
    from django.core.files.storage import default_storage

    try:
        if main_name:
            default_storage.delete(original_storage_name(main_name))
    except Exception:  # pragma: no cover
        pass


def add_product_image(product, file, *, alt: str = "") -> ProductImage:
    """تصویر را اعتبارسنجی، در صورت نیاز کوچک، و همراه بندانگشتی برای کالا ثبت می‌کند."""
    validate_image_file(file)
    pil_image, fmt = _load_normalized_image(file)

    main_image = _shrink_to_fit(pil_image, MAX_DIMENSION)
    thumb_image = _shrink_to_fit(pil_image, THUMBNAIL_DIMENSION)
    ext = EXTENSION_BY_FORMAT[fmt]
    base_name = f"{product.slug}-{get_random_string(10)}"

    next_order = product.images.count()
    instance = ProductImage(product=product, alt=(alt or "").strip(), order=next_order, is_cover=next_order == 0)
    _keep_original(file, f"{base_name}{ext}")
    instance.image.save(f"{base_name}{ext}", ContentFile(_encode(main_image, fmt)), save=False)
    instance.thumbnail.save(f"{base_name}-thumb{ext}", ContentFile(_encode(thumb_image, fmt)), save=False)
    instance.save()
    return instance


def delete_product_image(image: ProductImage) -> None:
    """تصویر و فایل‌های آن را حذف می‌کند؛ اگر کاور بود، تصویر بعدی خودکار کاور می‌شود."""
    product = image.product
    was_cover = image.is_cover

    if image.image:
        _delete_original(image.image.name)
        image.image.delete(save=False)
    if image.thumbnail:
        image.thumbnail.delete(save=False)
    image.delete()

    if was_cover:
        next_image = product.images.order_by("order", "id").first()
        if next_image is not None:
            next_image.is_cover = True
            next_image.save(update_fields=["is_cover"])


def set_cover_image(product, image_id) -> ProductImage:
    """دقیقاً یک تصویر کالا را کاور می‌کند؛ بقیه خودکار غیرکاور می‌شوند."""
    image = product.images.filter(pk=image_id).first()
    if image is None:
        raise ProductImageError("تصویر مورد نظر یافت نشد.")

    product.images.exclude(pk=image.pk).filter(is_cover=True).update(is_cover=False)
    if not image.is_cover:
        image.is_cover = True
        image.save(update_fields=["is_cover"])
    return image


def move_product_image(image: ProductImage, direction: str) -> None:
    """ترتیب نمایش تصویر را با همسایه‌ی بالا/پایین آن جابه‌جا می‌کند."""
    ordered = list(image.product.images.order_by("order", "id"))
    index = next((i for i, item in enumerate(ordered) if item.pk == image.pk), None)
    if index is None:
        return

    if direction == "up" and index > 0:
        neighbor = ordered[index - 1]
    elif direction == "down" and index < len(ordered) - 1:
        neighbor = ordered[index + 1]
    else:
        return

    image.order, neighbor.order = neighbor.order, image.order
    ProductImage.objects.bulk_update([image, neighbor], ["order"])


def update_image_alt(image: ProductImage, alt: str) -> ProductImage:
    image.alt = (alt or "").strip()
    image.save(update_fields=["alt"])
    return image


def update_image_caption(image: ProductImage, caption: str) -> ProductImage:
    image.caption = (caption or "").strip()
    image.save(update_fields=["caption"])
    return image


def set_image_360(image: ProductImage, is_360: bool) -> ProductImage:
    """پرچمِ «بخشی از مجموعه‌ی ۳۶۰ درجه» را روشن/خاموش می‌کند — نگاه کنید به
    ``ProductImage.is_360``: فقط زیرساختِ داده است، هنوز ویوئری برایش وجود ندارد."""
    image.is_360 = bool(is_360)
    image.save(update_fields=["is_360"])
    return image


@transaction.atomic
def reorder_product_images(product, ordered_ids: list[int]) -> None:
    """ترتیبِ نمایشِ تصاویر را طبقِ ``ordered_ids`` بازنویسی می‌کند — برایِ
    مرتب‌سازیِ کشاندنی (drag)؛ همان الگویِ ``brand_service.reorder_brands``.

    قرارداد (A4): شناسه‌ی تکراری کل عملیات را رد می‌کند (هیچ ردیفی تغییر
    نمی‌کند)؛ شناسه‌ی نامعتبر/متعلق‌به‌کالایِ‌دیگر بی‌صدا نادیده گرفته
    می‌شود (چون ``product.images`` از قبل به همین کالا محدود است)؛ کل
    عملیات داخل یک تراکنش است — یا ترتیبِ کامل ذخیره می‌شود یا هیچ‌کدام.
    """
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ProductImageReorderError("فهرست مرتب‌سازی شامل شناسه‌ی تکراری است.")

    valid_id_set = set(product.images.filter(pk__in=ordered_ids).values_list("pk", flat=True))
    ordered_valid_ids = [image_id for image_id in ordered_ids if image_id in valid_id_set]
    for order, image_id in enumerate(ordered_valid_ids):
        ProductImage.objects.filter(pk=image_id, product=product).update(order=order)


def set_image_variant(image: ProductImage, variant) -> ProductImage:
    """تصویر را به یک تنوع مشخص از همان کالا اختصاص می‌دهد (یا با ``variant=None`` عمومی می‌کند).

    اگر تنوع متعلق به کالای دیگری باشد، ``ProductImageError`` می‌دهد — این تنها
    راهی است که یک تصویر می‌تواند به تنوع متصل شود، پس این‌جا اعتبارسنجی
    تنانت/کالا برای همیشه اجرا می‌شود.
    """
    if variant is not None and variant.product_id != image.product_id:
        raise ProductImageError("این تنوع متعلق به کالای دیگری است.")
    image.variant = variant
    image.save(update_fields=["variant"])
    return image


def set_image_option_value(image: ProductImage, option_value) -> ProductImage:
    """تصویر را به یک مقدارِ ویژگیِ خاص (مثلاً «قرمز») اختصاص می‌دهد، مستقل از
    محورهای دیگر — با ``option_value=None`` این اختصاص برداشته می‌شود.

    برخلافِ ``set_image_variant`` که به یک *ترکیبِ کامل* تنوع وصل می‌شود،
    این تابع تصویر را به تنهاییِ یک مقدار وصل می‌کند تا هرجا آن مقدار
    انتخاب شود (صرف‌نظر از سایر محورها) همین تصویر نمایش داده شود."""
    if option_value is not None and option_value.option.product_id != image.product_id:
        raise ProductImageError("این مقدارِ ویژگی متعلق به کالای دیگری است.")
    image.option_value = option_value
    image.save(update_fields=["option_value"])
    return image
