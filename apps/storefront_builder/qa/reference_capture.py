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


def reference_images(site: str, exclude: str = "") -> dict[str, list[Path]]:
    """Classify the reference capture images of a site into product-like, wide (hero/banner) and square pictures.

    ``exclude`` is an optional regular expression over file names that must never be used as product/hero/square pictures
    (for instance the small line-art category icons of a site)."""
    base = REFERENCE_ROOT / site / "capture"
    skip_extra = re.compile(exclude) if exclude else None
    products, wide, squares = [], [], []
    for path in sorted(base.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or _THUMB.search(path.name) or _SKIP.search(path.name):
            continue
        if skip_extra is not None and skip_extra.search(path.name):
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


def reference_file(site: str, pattern: str) -> Path | None:
    """The largest picture of the site's reference folder whose file name matches ``pattern`` (a regular expression), else ``None``.
    QA-only: lets a content pack give a role (hero, banner, story picture) a picture of the same *kind* the reference shows."""
    folder = REFERENCE_ROOT / site / "capture"
    best, best_size = None, 0
    for path in folder.iterdir():
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not re.search(pattern, path.name, re.I):
            continue
        if re.search(r"-\d+x\d+\.", path.name):
            continue
        size = path.stat().st_size
        if size > best_size:
            best, best_size = path, size
    return best


def uploaded(path: Path | None, name: str, *, size=(800, 800), label: str = "", color=(220, 214, 205), max_side: int = 1600,
             keep_alpha: bool = False, alpha_side: int = 600):
    """A ``SimpleUploadedFile`` from a reference picture, or a neutral placeholder when ``path`` is ``None``.
    ``keep_alpha`` keeps a PNG's transparency (line-art icons)."""
    if path is not None and keep_alpha and path.suffix.lower() == ".png":
        image = Image.open(path).convert("RGBA")
        image.thumbnail((alpha_side, alpha_side))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return SimpleUploadedFile(name.rsplit(".", 1)[0] + ".png", buffer.getvalue(), content_type="image/png")
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


_NEUTRAL_SENTENCES = (
    "این متن نمونهٔ آزمایشی است و فقط برای سنجش طول، ریتم و ساختار صفحه به‌کار می‌رود.",
    "تیترها، بندها و فهرست‌ها همان قالب یک توضیح واقعی را دارند تا جای‌گیری بخش‌ها دقیق دیده شود.",
    "مشخصات واقعی هر کالا را مدیر فروشگاه در بخش توضیحات محصول وارد می‌کند.",
    "طول متن، تعداد بخش‌ها و فاصلهٔ آن‌ها از روی یک صفحهٔ محصول معمول در فروشگاه‌های مشابه تنظیم شده است.",
    "در این بخش می‌توان روش استفاده، نکات نگهداری و توضیح گارانتی را نوشت.",
)
_NEUTRAL_BULLETS = (
    "ویژگی نمونهٔ اول", "ویژگی نمونهٔ دوم", "ویژگی نمونهٔ سوم", "ویژگی نمونهٔ چهارم", "ویژگی نمونهٔ پنجم", "ویژگی نمونهٔ ششم",
)


def neutral_article(blocks: int, *, paragraphs: int = 2, bullets: int = 5) -> str:
    """Neutral, invented article HTML (``blocks`` sections of heading + paragraphs + bullet list). QA only."""
    parts = []
    for block in range(blocks):
        parts.append(f"<h2>عنوان بخش {block + 1}</h2>")
        for para in range(paragraphs):
            parts.append("<p>" + " ".join(_NEUTRAL_SENTENCES[(block + para + n) % len(_NEUTRAL_SENTENCES)] for n in range(3)) + "</p>")
        if bullets:
            parts.append("<ul>" + "".join(f"<li>{_NEUTRAL_BULLETS[n % len(_NEUTRAL_BULLETS)]}</li>" for n in range(bullets)) + "</ul>")
    return "".join(parts)


def pdp_product_index(pack: dict) -> int:
    """Index of the demo product the product-page capture uses (a discounted one where the reference shows a discount)."""
    if pack.get("pdp_discounted"):
        return next((i for i, row in enumerate(pack["products"]) if row.get("discount")), 0)
    return 0


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
    images = reference_images(site, pack.get("exclude_images", "")) if image_mode == "reference" \
        else {"products": [], "wide": [], "squares": []}

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
    if pack.get("gift_wrap_price"):                # the merchant switches the existing Gift Wrap service on in its own settings
        shop.gift_wrap_available = True
        shop.gift_wrap_price = pack["gift_wrap_price"]
        shop.gift_wrap_title = pack.get("gift_wrap_title", shop.gift_wrap_title)
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

    # the real operational settings the trust claims are checked against (QA Store only): an active gateway and active shipping methods
    from apps.orders.models import PaymentGateway, ShippingMethod

    PaymentGateway.objects.create(store=store, name="پرداخت آنلاین", slug="cap-online", is_active=True)
    ShippingMethod.objects.create(store=store, name="پست پیشتاز", slug="cap-post", method_type=ShippingMethod.MethodType.FLAT_RATE,
                                  cost=60000, is_active=True, free_over=5_000_000)
    ShippingMethod.objects.create(store=store, name="تحویل حضوری", slug="cap-pickup", method_type=ShippingMethod.MethodType.LOCAL_PICKUP,
                                  cost=0, is_active=True)

    vendor = Vendor.objects.create(store=store, name=pack["store_name"], slug="cap-vendor")
    categories = []
    for index, (name, kind) in enumerate(pack["categories"]):
        category = Category.objects.create(store=store, name=name, slug=f"cap-cat-{index}", order=index, is_active=True)
        path = (REFERENCE_ROOT / site / "capture" / kind[5:]) if kind.startswith("file:") and image_mode == "reference" else pick(kind, index)
        category.image = uploaded(path, f"cat-{index}.jpg", size=(640, 640), label=name, keep_alpha=kind.startswith("file:"))
        category.save(update_fields=["image"])
        categories.append(category)
    children: dict[int, list] = {}
    for parent_index, rows in pack.get("children", {}).items():
        for order, (name, kind) in enumerate(rows):
            child = Category.objects.create(store=store, parent=categories[parent_index], name=name,
                                            slug=f"cap-cat-{parent_index}-{order}", order=order, is_active=True)
            path = (REFERENCE_ROOT / site / "capture" / kind[5:]) if kind.startswith("file:") and image_mode == "reference" else pick(kind, order)
            child.image = uploaded(path, f"cat-{parent_index}-{order}.jpg", size=(640, 640), label=name, keep_alpha=kind.startswith("file:"))
            child.save(update_fields=["image"])
            children.setdefault(parent_index, []).append(child)
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
        kids = children.get(spec.get("category", index) % len(categories))
        if kids and spec.get("child") is not None:
            category = kids[spec["child"] % len(kids)]
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

    pdp_fixture = pack.get("pdp")
    if pdp_fixture:
        from apps.catalog.models import Review, Specification
        from apps.catalog.services.variant_service import create_variant
        from apps.customers.models import Customer

        target = products[pdp_product_index(pack)]
        if pdp_fixture.get("article_blocks"):
            target.description = neutral_article(pdp_fixture["article_blocks"], paragraphs=pdp_fixture.get("paragraphs", 2))
            target.save(update_fields=["description"])
        for order, (label, value) in enumerate(pdp_fixture.get("specs", ())):
            Specification.objects.create(product=target, label=label, value=value, order=order)
        for attribute, values in pdp_fixture.get("variants", ()):
            for value_index, value in enumerate(values):
                create_variant(target, attribute=attribute, value=value, stock=4 + value_index, is_active=True)
        for number in range(pdp_fixture.get("reviews", 0)):
            user = get_user_model().objects.create_user(username=f"09{abs(hash((site, number))) % 10**9:09d}", password="x12345678")
            customer = Customer.objects.create(user=user, full_name=f"مشتری نمونه {number + 1}", phone=f"0912{abs(hash((site, number))) % 10**7:07d}")
            Review.objects.create(product=target, customer=customer, rating=3 + number % 3,
                                  text="این نظر نمونهٔ آزمایشی است و فقط برای سنجش چیدمان بخش نظرات ثبت شده است.", is_approved=True)

    for order, spec in enumerate(pack.get("hero", ())):
        slide = HeroSlide(store=store, title=spec.get("title", ""), subtitle=spec.get("subtitle", ""), display_order=order,
                          is_active=True, show_button=bool(spec.get("button")), button_label=spec.get("button", ""),
                          destination_type="category", destination_category=categories[order % len(categories)])
        desktop_file = reference_file(site, spec["desktop_file"]) if spec.get("desktop_file") and image_mode == "reference" else None
        mobile_file = reference_file(site, spec["mobile_file"]) if spec.get("mobile_file") and image_mode == "reference" else None
        if desktop_file is not None:       # the pack names the kind of picture the reference hero shows (e.g. a transparent mascot)
            slide.desktop_image = uploaded(desktop_file, f"hero-{order}.jpg", max_side=2200, keep_alpha=True, alpha_side=1400)
        else:
            slide.desktop_image = uploaded(pick("wide", order), f"hero-{order}.jpg", size=(1800, 800), max_side=2200)
        if mobile_file is not None:
            slide.mobile_image = uploaded(mobile_file, f"hero-m-{order}.jpg", max_side=1400, keep_alpha=True, alpha_side=1000)
        else:
            slide.mobile_image = uploaded(pick("products", order), f"hero-m-{order}.jpg", size=(900, 1200))
        slide.save()
    for order, spec in enumerate(pack.get("banners", ())):
        banner = PromotionalBanner(store=store, title=spec.get("title", ""), description=spec.get("description", ""),
                                   display_order=order, is_active=True, show_button=bool(spec.get("button")),
                                   button_label=spec.get("button", ""),
                                   destination_type="category", destination_category=categories[order % len(categories)])
        banner_file = reference_file(site, spec["file"]) if spec.get("file") and image_mode == "reference" else None
        if banner_file is not None:
            banner.desktop_image = uploaded(banner_file, f"banner-{order}.jpg", max_side=1600, keep_alpha=bool(spec.get("alpha")), alpha_side=500)
        else:
            banner.desktop_image = uploaded(pick(spec.get("kind", "wide"), order), f"banner-{order}.jpg", size=(1200, 500))
        banner.save()
    for order, category in enumerate(categories):
        item = StoryRailItem(store=store, title=category.name[:40], display_order=order, is_active=True)
        item.image = uploaded(pick("squares", order), f"story-{order}.jpg", size=(400, 400))
        item.save()

    from apps.blog.models import BlogPost

    for order, spec in enumerate(pack.get("posts", ())):
        post = BlogPost(store=store, title=spec["title"], slug=f"cap-post-{site.lower()}-{order}", excerpt=spec.get("excerpt", ""),
                        body=spec.get("body", "<p>متن مطلب.</p>"), category_label=spec.get("label", ""),
                        published_at=timezone.now() - timezone.timedelta(days=order + 1))
        post.cover_image = uploaded(pick(spec.get("kind", "squares"), order), f"post-{order}.jpg", size=(900, 600))
        post.save()

    menu, _ = Menu.objects.get_or_create(store=store, location=Menu.Location.HEADER, defaults={"title": "منوی اصلی", "is_active": True})
    for order, label in enumerate(pack.get("menu", ())):
        MenuItem.objects.create(menu=menu, title=label, display_order=order, is_active=True, destination_type="search")

    for location, labels in (("footer_1", pack.get("footer_menu", ("درباره ما", "تماس با ما", "قوانین و مقررات"))),
                             ("footer_2", pack.get("footer_menu_2", ("پیگیری سفارش", "سوالات متداول", "راهنمای خرید")))):
        footer_menu, _ = Menu.objects.get_or_create(store=store, location=location, defaults={"title": {"footer_1": "لینک‌های مفید", "footer_2": "دسترسی سریع"}[location], "is_active": True})
        for order, label in enumerate(labels):
            MenuItem.objects.create(menu=footer_menu, title=label, display_order=order, is_active=True, destination_type="search")

    if preset_key:
        preset = lpr.get_layout_preset(preset_key)
        draft = layout_service.get_or_create_draft(store, user=owner)
        layout_service.get_or_create_layout(store)
        preset_service.apply_preset(draft, preset)
        header = dict(draft.header_config or {})
        header.update(pack.get("header", {}))
        draft.header_config = layout_service.validate_header_config(header)
        draft.save(update_fields=["header_config"])
        from apps.content.models import MediaAsset

        media_ids = []
        for number, pattern in enumerate(pack.get("media_assets", ())):          # the Store's own media library (QA copies)
            picture = reference_file(site, pattern) if image_mode == "reference" else None
            asset = MediaAsset(store=store)
            asset.image = uploaded(picture, f"media-{number}.jpg", max_side=1800, size=(1200, 800))
            asset.save()
            media_ids.append(asset.pk)

        def _resolve(value):
            if isinstance(value, str) and value.startswith("@media:"):
                return media_ids[int(value[7:])]
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            return value

        for fixture in pack.get("section_fixtures", ()):
            page = draft.get_page(fixture.get("page", "home"))
            matching = [sec for sec in page.sections.all() if sec.section_key == fixture["section_key"]]
            section = matching[fixture.get("nth", 0)]
            section.settings = {**(section.settings or {}), **_resolve(fixture["settings"])}
            section.save(update_fields=["settings"])
        for spec in pack.get("banner_sections", ()):               # a picture row that belongs to ONE section (linked_image)
            page = draft.get_page(spec.get("page", "home"))
            section = next(sec for sec in page.sections.all() if sec.section_key == spec["section_key"])
            banner = PromotionalBanner(store=store, section=section, title=spec.get("title", ""), display_order=0, is_active=True,
                                       destination_type="category", destination_category=categories[0])
            picture = reference_file(site, spec["file"]) if image_mode == "reference" else None
            banner.desktop_image = uploaded(picture, "section-banner.jpg", max_side=1800, size=(1600, 400))
            banner.save()
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

#: the two reference sets whose screenshots are not exactly 1847 / 487 px wide (measured from the saved pictures)
SITE_VIEWPORT_WIDTHS = {("zhimunplus", "desktop"): 1858, ("lilium-gallery", "mobile"): 503}

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


def capture_page(browser, base_url: str, host: str, path: str, viewport: str, out: Path, site: str = "") -> dict:
    """Full-page screenshot of ``path`` at the named viewport. Returns basic geometry for the report."""
    size = dict(VIEWPORTS[viewport])
    size["width"] = SITE_VIEWPORT_WIDTHS.get((site, viewport), size["width"])
    context = browser.new_context(viewport=size, locale="fa-IR",
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
