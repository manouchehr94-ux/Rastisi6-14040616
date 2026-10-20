"""R4-14 — ONE server-side check for an uploaded picture, shared by every upload path that used to rely on a bare ``ImageField``.

The upload guide (``apps/core/image_specs.py`` + ``image_guide.js``) only announces numbers and formats this code really enforces:

* the real format is read by Pillow from the file's bytes (never from the extension or the client's Content-Type);
* the byte limit is the one the guide prints;
* a pixel ceiling stops a small, highly compressed file from expanding into hundreds of megapixels in memory.

Nothing here modifies the file: it is opened, verified and rewound."""

from __future__ import annotations

from django.core.exceptions import ValidationError

MB = 1024 * 1024
ALLOWED_PIL_FORMATS = ("JPEG", "PNG", "WEBP")
FORMAT_LABELS = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WebP", "ICO": "ICO"}
#: Pillow itself warns at ~89 MP and refuses at ~179 MP; 50 MP (e.g. 7000×7000) is far above any storefront need.
MAX_PIXELS = 50_000_000
MAX_PIXELS_LABEL = "۵۰ مگاپیکسل"
#: below this many pixels the whole picture is decoded during validation (catches truncated files)
FULL_DECODE_PIXELS = 25_000_000


def formats_text(formats) -> str:
    return "، ".join(FORMAT_LABELS.get(f, f) for f in formats)


def open_and_verify(file, *, label: str = "تصویر", formats=ALLOWED_PIL_FORMATS) -> str:
    """Return Pillow's detected format; raise a Persian ``ValidationError`` for an unreadable / unsupported / oversized-pixel file.

    The stream is rewound so the caller can still save the untouched upload."""
    from PIL import Image

    try:
        file.seek(0)
    except Exception:  # pragma: no cover - non-seekable wrapper
        pass
    try:
        with Image.open(file) as img:
            detected = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except Image.DecompressionBombError as exc:
        raise ValidationError(f"ابعاد {label} بیش از حد بزرگ است؛ تصویری با حداکثر {MAX_PIXELS_LABEL} بارگذاری کنید.") from exc
    except Exception as exc:
        raise ValidationError(f"فایل {label} یک تصویر معتبر نیست یا ناقص است.") from exc
    finally:
        try:
            file.seek(0)
        except Exception:  # pragma: no cover
            pass
    if detected not in formats:
        raise ValidationError(
            f"فرمت {label} «{FORMAT_LABELS.get(detected, detected or 'نامشخص')}» پشتیبانی نمی‌شود. فرمت‌های مجاز: {formats_text(formats)}."
        )
    if width * height > MAX_PIXELS:
        raise ValidationError(
            f"ابعاد {label} ({width}×{height}) بیش از حد بزرگ است؛ حداکثر {MAX_PIXELS_LABEL}. تصویر را کوچک‌تر ذخیره کنید."
        )
    if width * height <= FULL_DECODE_PIXELS:
        # verify() only walks the container: a JPEG/PNG cut off mid-stream still "verifies". A full decode (bounded to ordinary sizes, so a
        # 50 MP file never costs ~150 MB of RAM here) catches truncated uploads before they are stored.
        try:
            file.seek(0)
            with Image.open(file) as img:
                img.load()
        except Exception as exc:
            raise ValidationError(f"فایل {label} ناقص یا خراب است؛ دوباره ذخیره یا خروجی بگیرید.") from exc
        finally:
            try:
                file.seek(0)
            except Exception:  # pragma: no cover
                pass
    return detected


def validate_uploaded_image(file, *, max_bytes: int, label: str = "تصویر", formats=ALLOWED_PIL_FORMATS):
    """Size + real format + pixel ceiling. ``file`` may be ``None``/empty (nothing uploaded → unchanged)."""
    if not file:
        return file
    size = getattr(file, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError(
            f"حجم {label} {size / MB:.1f} مگابایت است؛ حداکثر مجاز {max_bytes / MB:g} مگابایت."
        )
    open_and_verify(file, label=label, formats=formats)
    return file
