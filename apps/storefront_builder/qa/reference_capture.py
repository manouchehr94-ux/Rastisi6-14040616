"""Dev/QA harness: render a Ready Template on a throw-away Store and capture full-page browser screenshots.

Used to compare the real R4 output of a template with the reference screenshots in ``docs/design-references/v5-six-sites``.
It only ever runs inside a Django *test database* (see ``tests/test_v5_reference_capture.py``, opt-in) with an isolated
``MEDIA_ROOT``: it never touches a real Store, database or shared media.

Demo images may be drawn from the reference capture folder of the same site (``image_mode="reference"``) so that the
comparison is about layout/typography/colour rather than about photography. Those images exist only in the temporary
media folder of the run; they are never copied into the repository or into a template.
"""

from __future__ import annotations

import io
import os
import re
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image, ImageDraw

REFERENCE_ROOT = Path(__file__).resolve().parents[3] / "docs" / "design-references" / "v5-six-sites" / "references"

_WIDE = re.compile(r"slide|banner|hero|wide|cover|header", re.I)
_SKIP = re.compile(r"logo|icon|favicon|badge|enamad|namad|trust|avatar|sprite|placeholder|pattern|bg[-_]|wave|svg", re.I)
_THUMB = re.compile(r"-\d{2,4}x\d{2,4}\.")


def _read(path: Path, max_side: int = 1600, quality: int = 86) -> tuple[bytes, tuple[int, int]]:
    image = Image.open(path)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        backdrop = Image.new("RGBA", image.size, (255, 255, 255, 255))
        backdrop.alpha_composite(image)
        image = backdrop
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue(), image.size


def reference_images(site: str) -> dict[str, list[Path]]:
    """Classify the reference capture images of a site into product-like, wide (hero/banner) and square pictures."""
    base = REFERENCE_ROOT / site / "capture"
    products, wide, squares = [], [], []
    for path in sorted(base.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or _THUMB.search(path.name) or _SKIP.search(path.name):
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            continue
        if min(width, height) < 400:
            continue
        ratio = width / height
        if ratio >= 1.35 or _WIDE.search(path.name):
            wide.append(path)
        elif 0.9 <= ratio <= 1.12:
            squares.append(path)
        else:
            products.append(path)
    return {"products": products, "wide": wide, "squares": squares}


def uploaded(path: Path | None, name: str, *, size=(800, 800), label: str = "", color=(220, 214, 205), max_side: int = 1600):
    """A ``SimpleUploadedFile`` from a reference picture, or a neutral placeholder when ``path`` is ``None``."""
    if path is not None:
        data, _ = _read(path, max_side=max_side)
        return SimpleUploadedFile(name, data, content_type="image/jpeg")
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] * 0.18, size[1] * 0.18, size[0] * 0.82, size[1] * 0.82), outline=(255, 255, 255), width=6)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=84)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


# --------------------------------------------------------------------------------------------------------------------
# Content packs: store-owned demo data (names, prices, picture roles). Pure data, one per reference site.
# --------------------------------------------------------------------------------------------------------------------

PACKS: dict[str, dict] = {}


def register_pack(site: str, **pack) -> None:
    PACKS[site] = pack


def seed_store(site: str, *, image_mode: str = "reference", preset_key: str | None = None, host: str = "ref-capture.example.com"):
    """Create and return ``(store, owner, products)`` for ``site`` inside the current (test) database."""
    from django.contrib.auth import get_user_model

    from apps.catalog.models import Brand, Category, Product, Vendor
    from apps.catalog.services.product_image_service import add_product_image
    from apps.content.models import (
        FooterSettings, HeroSlide, Menu, MenuItem, PromotionalBanner, SocialLink, StoryRailItem,
    )
    from apps.core.models import ShopSettings
    from apps.storefront_builder.services import layout_service, preset_service
    from apps.storefront_builder import layout_preset_registry as lpr
    from apps.stores.models import Store, StoreDomain, StoreMembership
    from apps.stores.services.platform_code_service import generate_unique_platform_code

    pack = PACKS[site]
    images = reference_images(site) if image_mode == "reference" else {"products": [], "wide": [], "squares": []}

    def pick(kind: str, index: int):
        pool = images.get(kind) or images["products"] or images["squares"] or images["wide"]
        return pool[index % len(pool)] if pool else None

    store = Store.objects.create(
        name=pack["store_name"], slug=f"cap-{site.lower()}", status=Store.Status.ACTIVE,
        platform_code=generate_unique_platform_code(), admin_subdomain=f"cap-{site.lower()[:12]}",
    )
    shop = ShopSettings.provision_for(store)
    shop.name = pack["store_name"]
    shop.tagline = pack.get("tagline", "")
    shop.contact_phone = pack.get("phone", "")
    if pack.get("logo_file"):                      # local comparison only: a picture from the reference kit, never shipped
        shop.logo = uploaded(REFERENCE_ROOT / site / "capture" / pack["logo_file"], "logo.jpg", max_side=900)
    shop.save()
    footer = FooterSettings.provision_for(store)
    footer.is_enabled = True
    footer.show_contact = True
    footer.phone = pack.get("phone", "")
    footer.description = pack.get("footer_text", "")
    footer.copyright_text = pack.get("copyright", "")
    footer.show_social_links = True
    footer.save()
    for order, (platform, title) in enumerate((("INSTAGRAM", "اینستاگرام"), ("WHATSAPP", "واتساپ"))):
        platform_value = getattr(SocialLink.Platform, platform, None)
        if platform_value is not None:
            SocialLink.objects.create(store=store, platform=platform_value, title=title, url="https://example.com/",
                                      display_order=order, is_active=True, show_in_footer=True)

    owner = get_user_model().objects.create_user(username=f"09{abs(hash(site)) % 10**9:09d}", password="x12345678", is_staff=True)
    StoreMembership.objects.create(store=store, user=owner, role=StoreMembership.Role.OWNER,
                                   status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
    StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                               verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())

    vendor = Vendor.objects.create(store=store, name=pack["store_name"], slug="cap-vendor")
    categories = []
    for index, (name, kind) in enumerate(pack["categories"]):
        category = Category.objects.create(store=store, name=name, slug=f"cap-cat-{index}", order=index, is_active=True)
        path = pick(kind, index)
        category.image = uploaded(path, f"cat-{index}.jpg", size=(640, 640), label=name)
        category.save(update_fields=["image"])
        categories.append(category)
    brands = []
    for index, name in enumerate(pack.get("brands", ())):
        brand = Brand.objects.create(store=store, name=name, slug=f"cap-brand-{index}", sort_order=index, is_active=True,
                                     description=pack.get("brand_description", ""), country=pack.get("brand_country", ""))
        brand.logo = uploaded(None, f"brand-{index}.jpg", size=(300, 120), color=(235, 235, 235))
        brand.save(update_fields=["logo"])
        brands.append(brand)

    products = []
    for index, spec in enumerate(pack["products"]):
        category = categories[spec.get("category", index) % len(categories)]
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, brand=(brands[index % len(brands)] if brands else None),
            name=spec["name"], slug=f"cap-p-{index}", sku=f"CAP-{index:03d}", price=Decimal(spec["price"]),
            discount_percent=spec.get("discount", 0), stock=spec.get("stock", 12), status=Product.Status.ACTIVE,
            description=spec.get("description", pack.get("description", "<p>توضیحات کامل محصول.</p>")),
            rating=Decimal(str(spec.get("rating", "4.8"))), reviews_count=spec.get("reviews", 14),
            sold_count=50 + index * 7, views_count=300 + index * 31,
            tag=spec.get("tag", ""),
        )
        for shot in range(spec.get("shots", 2)):
            add_product_image(product, uploaded(pick("products", index + shot * 5), f"p{index}-{shot}.jpg",
                                                size=(900, 1200)), alt=spec["name"])
        products.append(product)

    for order, spec in enumerate(pack.get("hero", ())):
        slide = HeroSlide(store=store, title=spec.get("title", ""), subtitle=spec.get("subtitle", ""), display_order=order,
                          is_active=True, show_button=bool(spec.get("button")), button_label=spec.get("button", ""))
        slide.desktop_image = uploaded(pick("wide", order), f"hero-{order}.jpg", size=(1800, 800), max_side=2200)
        slide.mobile_image = uploaded(pick("products", order), f"hero-m-{order}.jpg", size=(900, 1200))
        slide.save()
    for order, spec in enumerate(pack.get("banners", ())):
        banner = PromotionalBanner(store=store, title=spec.get("title", ""), description=spec.get("description", ""),
                                   display_order=order, is_active=True, show_button=bool(spec.get("button")),
                                   button_label=spec.get("button", ""))
        banner.desktop_image = uploaded(pick(spec.get("kind", "wide"), order), f"banner-{order}.jpg", size=(1200, 500))
        banner.save()
    for order, category in enumerate(categories):
        item = StoryRailItem(store=store, title=category.name[:40], display_order=order, is_active=True)
        item.image = uploaded(pick("squares", order), f"story-{order}.jpg", size=(400, 400))
        item.save()

    menu, _ = Menu.objects.get_or_create(store=store, location=Menu.Location.HEADER, defaults={"title": "منوی اصلی", "is_active": True})
    for order, label in enumerate(pack.get("menu", ())):
        MenuItem.objects.create(menu=menu, title=label, display_order=order, is_active=True, destination_type="search")

    if preset_key:
        preset = lpr.get_layout_preset(preset_key)
        draft = layout_service.get_or_create_draft(store, user=owner)
        layout_service.get_or_create_layout(store)
        preset_service.apply_preset(draft, preset)
        header = dict(draft.header_config or {})
        header.update(pack.get("header", {}))
        draft.header_config = layout_service.validate_header_config(header)
        draft.save(update_fields=["header_config"])
        layout_service.publish(store)
    return store, owner, products


class patched_best_sellers:
    """Context manager: the real best-seller algorithm needs paid orders; the capture uses the seeded products in order."""

    def __init__(self, products):
        self.ids = [p.pk for p in products]

    def __enter__(self):
        from unittest import mock

        from apps.orders.services import best_seller_service

        self._patch = mock.patch.object(best_seller_service, "best_selling_product_ids", lambda store, limit, days=30: self.ids[:limit])
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


# --------------------------------------------------------------------------------------------------------------------
# Browser capture
# --------------------------------------------------------------------------------------------------------------------

VIEWPORTS = {
    "desktop": {"width": 1847, "height": 1000},
    "mobile": {"width": 487, "height": 900},
}

SETTLE_JS = """
async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  document.querySelectorAll('img[loading=lazy]').forEach((i) => { i.loading = 'eager'; });
  const h = document.documentElement.scrollHeight;
  for (let y = 0; y < h; y += 500) { window.scrollTo(0, y); await sleep(50); }
  window.scrollTo(0, 0);
  if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
  const pending = [...document.images].filter((i) => !i.complete).map((i) => new Promise((r) => { i.onload = i.onerror = r; }));
  await Promise.race([Promise.all(pending), sleep(5000)]);
  await sleep(300);
}
"""


def capture_page(browser, base_url: str, host: str, path: str, viewport: str, out: Path) -> dict:
    """Full-page screenshot of ``path`` at the named viewport. Returns basic geometry for the report."""
    context = browser.new_context(viewport=VIEWPORTS[viewport], locale="fa-IR",
                                  device_scale_factor=1, is_mobile=(viewport == "mobile"), has_touch=(viewport == "mobile"))
    page = context.new_page()
    page.set_default_timeout(60000)
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    if os.environ.get("SFB_CAPTURE_DEBUG"):
        page.on("request", lambda r: print("REQ", r.url[:110], flush=True))
        page.on("requestfailed", lambda r: print("FAIL", r.url[:110], flush=True))
    try:
        page.goto(f"{base_url}{path}", wait_until="load")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.evaluate(SETTLE_JS)
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), full_page=True)
        geometry = page.evaluate(
            "() => ({w: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,"
            " h: document.documentElement.scrollHeight})")
        geometry["errors"] = errors
        if os.environ.get("SFB_CAPTURE_EVAL"):
            geometry["eval"] = page.evaluate(os.environ["SFB_CAPTURE_EVAL"])
        return geometry
    finally:
        context.close()
