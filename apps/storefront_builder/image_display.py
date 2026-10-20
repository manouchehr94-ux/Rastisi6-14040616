"""R4-11 — the image display contract: ONE table says how every kind of storefront picture is shown.

The storefront CSS (``IMAGE DISPLAY CONTRACT`` block in ``static/css/storefront_builder.css``) implements this table through the
``data-img-role`` attribute every storefront ``<img>`` carries; the Design Studio image controls (``design_image_fit`` /
``design_image_position`` / ``design_image_ratio`` / ``design_image_zoom`` capabilities) override it per section through ``--img-fit`` / ``--img-pos`` /
``--img-ratio``. Uploaded files are never cropped, resized or re-encoded: the frame decides what is visible.

Adding a role means adding a row here AND its default rule in the CSS block; ``tests/test_r411_image_display_contract.py`` fails
if either side is missing.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTAIN = "contain"
COVER = "cover"


@dataclass(frozen=True)
class ImageRole:
    key: str
    fit: str  # default object-fit: contain = the whole picture, cover = the frame is filled
    description: str


IMAGE_ROLES: dict[str, ImageRole] = {r.key: r for r in (
    ImageRole("product", CONTAIN, "عکس محصول (کارت، محصول ویژه، گالری): کل محصول دیده می‌شود، هرگز کشیده نمی‌شود"),
    ImageRole("thumb", CONTAIN, "تصویر کوچک محصول (سبد، پرداخت، بندانگشتی گالری)"),
    ImageRole("logo", CONTAIN, "لوگو (برند، فروشگاه، اعتماد/پرداخت): در یک قاب استاندارد، بدون برش"),
    ImageRole("category", COVER, "تصویر دسته‌بندی در قاب استاندارد"),
    ImageRole("article", COVER, "تصویر شاخص مقاله در قاب استاندارد ۱۶:۱۰"),
    ImageRole("collection", COVER, "تصویر مجموعه در قاب استاندارد ۴:۳"),
    ImageRole("banner", COVER, "بنر: قاب نسبت‌دار با تصویر موبایل جدا در صورت وجود"),
    ImageRole("hero", COVER, "هیرو/اسلایدر: تمام‌عرض، نقطهٔ تمرکز قابل تنظیم"),
    ImageRole("story", COVER, "استوری: قاب دایره‌ای/عمودی ثابت"),
)}

# sections that own pictures and therefore offer the matching Design Studio controls (see section_registry capabilities)
IMAGE_CONTROLS_BY_SECTION: dict[str, frozenset[str]] = {
    "brand_carousel": frozenset({"fit", "position"}),
    "amazing_offers": frozenset({"fit", "position", "zoom"}),
    "collection_tiles": frozenset({"fit", "position", "ratio"}),
    "newest_products": frozenset({"fit", "position", "ratio", "zoom"}),
    "best_sellers": frozenset({"fit", "position", "ratio", "zoom"}),
    "discounted_products": frozenset({"fit", "position", "ratio", "zoom"}),
    "hero_banner": frozenset({"position"}),
    "image_slider": frozenset({"position"}),
    "multi_banner": frozenset({"position"}),
    "image_text": frozenset({"fit", "position"}),
}
