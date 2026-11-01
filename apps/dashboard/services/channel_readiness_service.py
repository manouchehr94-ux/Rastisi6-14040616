"""«Are my products ready for a price-comparison / shopping channel?» — answered from the store's own public product data, with NO outside contact and NO feed.

RastiSi has no contract, API or feed format with Torob (or any comparison engine) and invents none. What it CAN do for the seller today, independent of any contract, is check the
facts every such channel needs from a listing — a title, a real price, availability, a picture and a public page — using the SAME sources the storefront and its structured data use
(``storefront_listing_products`` for «what is publicly listed», ``seo_tags._offers`` / ``resolve_effective_price`` for price and availability). Missing facts are named per product
so the seller fixes them once, in RastiSi, and every channel that is later enabled benefits.

**Definition (QA: «58 بررسی‌شده / 50 آماده / 8 بدون تصویر / 10 ناموجود»).** A product is *ready* when it has a title, a real price and a cover image — the three BLOCKING checks.
``out_of_stock`` is informational (a channel shows the product as unavailable; it is not a data error), so an out-of-stock product CAN be ready. The problem counts therefore OVERLAP:
one product may be both «no image» and «out of stock», and out-of-stock products are mostly counted inside «ready». ``ready_in_stock`` / ``ready_out_of_stock`` split the ready group so the
numbers add up. ``no_price`` and ``out_of_stock`` never overlap (a product without a price has no availability to report). Scope: ``storefront_listing_products(store)`` only — this store's
published, non-deleted, listed products — so another store's products, deleted rows and unlisted drafts are never counted."""

from __future__ import annotations

from apps.catalog.models import Product
from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.core.templatetags import seo_tags

CHECKS = (
    ("no_title", "عنوان خالی", True),
    ("no_price", "قیمت ندارد (استعلام قیمت یا قیمت صفر)", True),
    ("no_image", "تصویر ندارد", True),
    ("out_of_stock", "ناموجود (به‌صورت «ناموجود» نمایش داده می‌شود)", False),
)
LABELS = {key: label for key, label, _ in CHECKS}
BLOCKING = {key for key, _, blocking in CHECKS if blocking}
SAMPLE = 5
LIMIT = 2000


def _problems(product) -> list[str]:
    found = []
    if not (product.name or "").strip():
        found.append("no_title")
    offers = seo_tags._offers(product, "https://example.invalid/")        # price + availability from the cart/checkout pricing authority
    price = None if offers is None else (offers.get("price") or offers.get("lowPrice"))
    if offers is None or not price or float(price) <= 0:
        found.append("no_price")
    elif offers["availability"].endswith("OutOfStock"):
        found.append("out_of_stock")
    if product.cover_image is None:
        found.append("no_image")
    return found


def readiness(store) -> dict:
    """Counts + a few named examples. Pure reading of THIS store's listed products (capped, so a huge catalogue cannot slow the page)."""
    products = list(storefront_listing_products(store).prefetch_related("images", "variants").order_by("-updated_at")[:LIMIT])
    counts = {key: 0 for key in LABELS}
    samples: dict[str, list[str]] = {key: [] for key in LABELS}
    ready = ready_out_of_stock = 0
    for product in products:
        problems = _problems(product)
        for key in problems:
            counts[key] += 1
            if len(samples[key]) < SAMPLE:
                samples[key].append(product.name or product.slug)
        if not (set(problems) & BLOCKING):
            ready += 1
            if "out_of_stock" in problems:
                ready_out_of_stock += 1
    rows = [{"key": key, "label": label, "count": counts[key], "blocking": blocking, "samples": samples[key]} for key, label, blocking in CHECKS if counts[key]]
    total = len(products)
    return {"total": total, "ready": ready, "not_ready": total - ready, "rows": rows, "capped": total >= LIMIT,
            "ready_in_stock": ready - ready_out_of_stock, "ready_out_of_stock": ready_out_of_stock, "out_of_stock": counts["out_of_stock"],
            "overlap_note": ("«آماده» یعنی عنوان، قیمت و تصویر دارد. «ناموجود» فقط اطلاع‌رسانی است و جزو کم‌وکاستی نیست؛ پس یک کالای ناموجود می‌تواند «آماده» باشد و "
                             "یک کالا می‌تواند هم «بدون تصویر» و هم «ناموجود» باشد. به همین دلیل جمع ردیف‌ها با «کالای بررسی‌شده» برابر نیست."),
            "summary": ("هنوز کالای منتشرشده‌ای برای بررسی نیست." if not total else
                        f"{ready} از {total} کالا همهٔ اطلاعات لازم (عنوان، قیمت، تصویر) را دارد." if ready == total else
                        f"{ready} از {total} کالا آماده است؛ {total - ready} کالا اطلاعات ناقص دارد.")}


# ---- Google Merchant Center ------------------------------------------------------------------------------------------------------
#: Google Merchant Center is not available to businesses established in Iran (Google's own country availability). RastiSi is a Persian / Toman / Iranian-market platform and stores no
#: business country per store, so every store is treated as an Iranian-market store: the honest answer is «not supported», and no connection, form or workaround is offered.
MERCHANT_CENTER = {
    "state": "unsupported",
    "title": "Google Merchant Center",
    "text": "Google Merchant Center برای کسب‌وکارهای مستقر در ایران در دسترس نیست؛ بنابراین راستی‌سی اتصال یا ارسال فید به آن ارائه نمی‌دهد و راه دورزدن این محدودیت را پیشنهاد نمی‌کند.",
}


def merchant_center_status(store) -> dict:
    return dict(MERCHANT_CENTER)
