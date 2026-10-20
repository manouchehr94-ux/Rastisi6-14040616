"""R4-14 — smart upload guide: what the server really enforces, the store's real frames, and the non-destructive product pipeline.

* ``apps.core.image_validation`` is the ONE server check (real Pillow format, byte limit, pixel ceiling) used by every picture upload that used
  to rely on a bare ``ImageField`` (category, brand logo, collection, gift wrap, swatch, onboarding logo) and by the product service;
* the guide (``image_specs`` → ``{% image_guide %}`` → ``image_guide.js``) only announces numbers this code enforces;
* ``upload_frames`` resolves the frames a picture is shown in from the store's own layout and is pinned to the storefront CSS;
* the product service keeps the seller's original bytes untouched next to the display versions."""

import hashlib
import os
import re
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import product_image_service as pis
from apps.core import image_specs
from apps.core.image_validation import MAX_PIXELS, validate_uploaded_image
from apps.dashboard import forms as dash_forms
from apps.stores.models import Store
from apps.storefront_builder import upload_frames

APPS = Path(__file__).resolve().parents[2]
JS = (APPS / "core" / "static" / "core" / "image_guide.js").read_text(encoding="utf-8")
CARD_CSS = (APPS / "catalog" / "static" / "css" / "product_card.css").read_text(encoding="utf-8")


def _bytes(fmt, size=(400, 300), color="#2a7"):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _upload(name, data, ctype="image/png"):
    return SimpleUploadedFile(name, data, content_type=ctype)


class ServerValidationTests(SimpleTestCase):
    def test_real_formats_are_accepted(self):
        for fmt, name in (("JPEG", "a.jpg"), ("PNG", "a.png"), ("WEBP", "a.webp")):
            self.assertTrue(validate_uploaded_image(_upload(name, _bytes(fmt)), max_bytes=5 * 1024 * 1024, label="تصویر"))

    def test_none_is_left_alone(self):
        self.assertIsNone(validate_uploaded_image(None, max_bytes=10))

    def test_format_comes_from_the_bytes_not_the_name_or_content_type(self):
        for fmt in ("GIF", "BMP"):
            with self.assertRaises(ValidationError) as ctx:
                validate_uploaded_image(_upload("photo.png", _bytes(fmt), "image/png"), max_bytes=5 * 1024 * 1024, label="تصویر")
            self.assertIn("فرمت‌های مجاز: JPG، PNG، WebP", ctx.exception.messages[0])

    def test_svg_html_and_text_are_rejected(self):
        for data in (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', b"<html><script>alert(1)</script></html>", b"hello"):
            with self.assertRaises(ValidationError):
                validate_uploaded_image(_upload("x.png", data), max_bytes=5 * 1024 * 1024)

    def test_truncated_file_is_rejected(self):
        data = _bytes("JPEG", (1200, 900))
        with self.assertRaises(ValidationError):
            validate_uploaded_image(_upload("t.jpg", data[: len(data) // 4], "image/jpeg"), max_bytes=5 * 1024 * 1024)

    def test_byte_limit_message_names_the_real_numbers(self):
        big = _upload("big.png", b"\x89PNG" + b"0" * (3 * 1024 * 1024))
        with self.assertRaises(ValidationError) as ctx:
            validate_uploaded_image(big, max_bytes=2 * 1024 * 1024, label="لوگو")
        self.assertIn("حداکثر مجاز 2 مگابایت", ctx.exception.messages[0])

    def test_pixel_ceiling_stops_a_small_file_that_expands_hugely(self):
        side = int((MAX_PIXELS) ** 0.5) + 200
        data = BytesIO()
        Image.new("L", (side, side), 200).save(data, format="PNG")
        self.assertLess(len(data.getvalue()), 5 * 1024 * 1024)  # tiny on disk, huge once decoded
        with self.assertRaises(ValidationError) as ctx:
            validate_uploaded_image(_upload("huge.png", data.getvalue()), max_bytes=5 * 1024 * 1024)
        self.assertIn("بیش از حد بزرگ", ctx.exception.messages[0])

    def test_validation_never_consumes_the_stream(self):
        up = _upload("a.png", _bytes("PNG"))
        validate_uploaded_image(up, max_bytes=5 * 1024 * 1024)
        self.assertEqual(up.read(4), b"\x89PNG")


class FormsUseTheSharedCheckTests(SimpleTestCase):
    """Category / brand / collection / swatch / gift-wrap used to accept ANY Pillow-readable file of ANY size (GIF, BMP, 100 MB)."""

    def _field_error(self, form_cls, field, upload, **data):
        form = form_cls(data={"name": "x", "label": "x", **data}, files={field: upload})
        form.is_valid()
        return form.errors.get(field)

    def test_each_path_rejects_a_gif_named_png(self):
        gif = _upload("a.png", _bytes("GIF"))
        for cls, field in ((dash_forms.BrandForm, "logo"), (dash_forms.CollectionForm, "image"), (dash_forms.MainCategoryForm, "image"),
                           (dash_forms.CategoryEditForm, "image"), (dash_forms.AttributeValueForm, "swatch_image")):
            gif.seek(0)
            self.assertTrue(self._field_error(cls, field, gif), f"{cls.__name__}.{field} accepted a GIF")

    def test_each_path_accepts_a_valid_picture(self):
        for cls, field in ((dash_forms.BrandForm, "logo"), (dash_forms.CollectionForm, "image"), (dash_forms.MainCategoryForm, "image"),
                           (dash_forms.CategoryEditForm, "image"), (dash_forms.AttributeValueForm, "swatch_image")):
            png = _upload("a.png", _bytes("PNG"))
            self.assertFalse(self._field_error(cls, field, png), f"{cls.__name__}.{field} rejected a valid PNG")

    def test_oversized_file_is_rejected_with_the_limit(self):
        buf = BytesIO()
        Image.frombytes("RGB", (1500, 1500), os.urandom(1500 * 1500 * 3)).save(buf, format="PNG")
        self.assertGreater(len(buf.getvalue()), 5 * 1024 * 1024)
        errors = self._field_error(dash_forms.MainCategoryForm, "image", _upload("big.png", buf.getvalue()))
        self.assertTrue(errors)
        self.assertIn("5 مگابایت", errors[0])

    def test_identity_favicon_checks_the_real_format_not_the_client_content_type(self):
        form = dash_forms.IdentityAssetsForm(files={"favicon": _upload("f.png", _bytes("GIF"), "image/png")})
        form.is_valid()
        self.assertTrue(form.errors.get("favicon"))

    def test_identity_logo_limit_message_is_exact_for_half_megabyte_values(self):
        self.assertEqual(dash_forms.MAX_FAVICON_SIZE, 512 * 1024)
        self.assertEqual(f"{dash_forms.MAX_FAVICON_SIZE / (1024 * 1024):g}", "0.5")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductPipelineIsNonDestructiveTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-r414")
        category = Category.objects.create(store=store, name="دسته", slug="cat-r414")
        self.product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالا", slug="p-r414", sku="SKU-R414", price=Decimal("1000"),
            icon="🧸", tint="#fde68a", status=Product.Status.ACTIVE,
        )

    def test_the_sellers_original_bytes_are_kept_unchanged(self):
        data = _bytes("JPEG", (2600, 1800))
        image = pis.add_product_image(self.product, _upload("big.jpg", data, "image/jpeg"))
        original = pis.original_storage_name(image.image.name)
        self.assertTrue(default_storage.exists(original))
        with default_storage.open(original, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), hashlib.sha256(data).hexdigest())
        with Image.open(image.image.path) as shown:
            self.assertLessEqual(max(shown.size), pis.MAX_DIMENSION)  # display version is shrunk; the original is not

    def test_deleting_the_image_removes_the_kept_original_too(self):
        image = pis.add_product_image(self.product, _upload("a.jpg", _bytes("JPEG"), "image/jpeg"))
        original = pis.original_storage_name(image.image.name)
        pis.delete_product_image(image)
        self.assertFalse(default_storage.exists(original))

    def test_a_pixel_bomb_is_a_clean_product_image_error_not_a_500(self):
        side = int(MAX_PIXELS ** 0.5) + 200
        buf = BytesIO()
        Image.new("L", (side, side), 9).save(buf, format="PNG")
        with self.assertRaises(pis.ProductImageError):
            pis.add_product_image(self.product, _upload("bomb.png", buf.getvalue()))
        self.assertEqual(self.product.images.count(), 0)

    def test_a_truncated_file_is_a_clean_error(self):
        data = _bytes("JPEG", (1200, 900))
        with self.assertRaises(pis.ProductImageError):
            pis.add_product_image(self.product, _upload("t.jpg", data[: len(data) // 5], "image/jpeg"))

    def test_a_gif_renamed_jpg_no_longer_slips_through_as_jpeg(self):
        with self.assertRaises(pis.ProductImageError):
            pis.add_product_image(self.product, _upload("a.jpg", _bytes("GIF"), "image/jpeg"))


class GuideOnlyAnnouncesEnforcedNumbersTests(SimpleTestCase):
    def test_every_spec_that_claims_a_server_limit_has_a_real_validator_behind_it(self):
        enforced_ratio_free = {k for k, s in image_specs.SPECS.items() if s.max_enforced}
        for key in ("category_image", "collection_image", "brand_logo", "gift_wrap_image", "swatch_image", "journal_cover", "hero_desktop",
                    "hero_mobile", "banner_desktop", "banner_mobile", "story_item", "product_image", "shop_logo", "favicon", "footer_badge"):
            self.assertIn(key, enforced_ratio_free, key)

    def test_product_and_logo_limits_equal_the_code_constants(self):
        self.assertEqual(image_specs.SPECS["product_image"].max_bytes, pis.MAX_UPLOAD_SIZE_BYTES)
        self.assertEqual(image_specs.SPECS["shop_logo"].max_bytes, dash_forms.MAX_LOGO_SIZE)
        self.assertEqual(image_specs.SPECS["favicon"].max_bytes, dash_forms.MAX_FAVICON_SIZE)
        self.assertEqual(image_specs.SPECS["category_image"].max_bytes, dash_forms.IMAGE_MAX_BYTES)

    def test_listed_formats_are_exactly_the_formats_the_server_accepts(self):
        for key, spec in image_specs.SPECS.items():
            self.assertTrue(set(spec.formats) <= {"JPG", "PNG", "WebP", "ICO"}, key)
            if key != "favicon":
                self.assertEqual(set(spec.formats), {"JPG", "PNG", "WebP"}, key)  # no spec promises GIF / SVG / AVIF / HEIC

    def test_story_has_a_spec_and_the_stale_category_sentence_is_gone(self):
        self.assertIn("story_item", image_specs.SPECS)
        self.assertNotIn("فرمِ آپلودِ تصویر وجود ندارد", image_specs.render_media_spec_markdown())

    def test_the_guide_script_detects_formats_from_bytes_and_defers_the_product_upload(self):
        for needle in ("function detectFormat", "ftypavif", "data-confirm-event", "new DataTransfer()", "پیش‌نمایش در فروشگاه شما"):
            self.assertIn(needle, JS)
        # the page never sends a file because it was merely chosen: confirm is an explicit button
        self.assertIn("'ذخیرهٔ '", JS)

    def test_product_upload_forms_wait_for_the_confirm_event(self):
        for rel in ("dashboard/templates/dashboard/partials/product_images_modal.html", "dashboard/templates/dashboard/partials/product_form.html"):
            html = (APPS / rel).read_text(encoding="utf-8")
            self.assertIn('hx-trigger="imgguide-confirm"', html, rel)
            self.assertNotIn('hx-trigger="change"', html.split("product-image-upload")[1][:600] if "product-image-upload" in html else html, rel)


class FrameResolverTests(SimpleTestCase):
    def _s(self, key, **settings):
        return SimpleNamespace(section_key=key, settings=settings, is_active=True)

    def test_card_ratio_table_is_pinned_to_the_product_card_css(self):
        css = re.sub(r"/\*.*?\*/", "", CARD_CSS, flags=re.S)
        for style, (w, h) in upload_frames._STYLE_FIXED.items():
            # the LAST declaration wins the cascade (e.g. compact: 1.14/1, then 1.05/1 on phones, then an unconditional 1/1.03)
            found = re.findall(r"\.pcard\.style-" + style + r" \.img\{[^}]*?aspect-ratio:\s*([\d.]+)\s*(?:/\s*([\d.]+))?", css)
            if style in ("pastel_flat", "chocolate_retail", "compact", "catalog_index"):
                self.assertTrue(found, style)
            if found:
                css_w, css_h = float(found[-1][0]), float(found[-1][1] or 1)
                self.assertAlmostEqual(css_w / css_h, w / h, places=1, msg=style)
        self.assertIn(".pcard.ratio-portrait .img{aspect-ratio:3/4}", css)
        self.assertIn(".pcard.ratio-landscape .img{aspect-ratio:4/3}", css)

    def test_default_card_follows_the_card_ratio_setting(self):
        for setting, expected in (("square", 1.0), ("portrait", 0.75), ("landscape", 1.3333)):
            frames = upload_frames.resolve_frames("product_image", sections=[self._s("newest_products", card={"image_ratio": setting})])
            card = next(f for f in frames if f["label"] == "کارت کالا")
            self.assertAlmostEqual(card["ratio"], expected, places=3)

    def test_design_studio_ratio_overrides_the_card_style(self):
        s = self._s("best_sellers", card={"card_style": "compact", "image_ratio": "square"}, design={"image_ratio": "portrait", "image_fit": "cover", "image_position": "top"})
        card = next(f for f in upload_frames.resolve_frames("product_image", sections=[s]) if f["label"] == "کارت کالا")
        self.assertEqual((card["ratio"], card["fit"], card["pos"]), (0.75, "cover", "top"))
        self.assertTrue(card["can_fit"] and card["can_pos"] and card["can_zoom"])

    def test_zoom_and_fit_of_the_amazing_offers_section_reach_the_guide(self):
        s = self._s("amazing_offers", design={"image_zoom": "125", "image_fit": "cover"})
        frame = next(f for f in upload_frames.resolve_frames("product_image", sections=[s]) if f["label"] == "پیشنهاد شگفت‌انگیز")
        self.assertEqual((frame["zoom"], frame["fit"], frame["ratio"]), (1.25, "cover", 1.3333))

    def test_identical_frames_are_listed_once_with_every_section_that_uses_them(self):
        frames = upload_frames.resolve_frames("product_image", sections=[
            self._s("newest_products", title="الف"), self._s("best_sellers", title="ب"), self._s("discounted_products", title="ج")])
        cards = [f for f in frames if f["label"] == "کارت کالا"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["used_by"], ["الف", "ب", "ج"])

    def test_a_store_without_sections_still_gets_the_product_page_frame(self):
        frames = upload_frames.resolve_frames("product_image", sections=[])
        self.assertEqual([f["label"] for f in frames], ["صفحهٔ کالا (گالری)"])

    def test_circle_and_square_category_modes(self):
        circle = upload_frames.resolve_frames("category_image", sections=[self._s("category_grid", display_mode="grey_circles")])[0]
        square = upload_frames.resolve_frames("category_image", sections=[self._s("category_grid", display_mode="pastel_tiles")])[0]
        self.assertEqual((circle["shape"], circle["ratio"]), ("circle", 1.0))
        self.assertEqual((square["shape"], square["ratio"]), ("rect", 1.0))

    def test_story_frame_is_a_circle(self):
        frame = upload_frames.resolve_frames("story_item", sections=[])[0]
        self.assertEqual(frame["shape"], "circle")

    def test_hero_phone_frame_is_marked_approximate(self):
        frame = upload_frames.resolve_frames("hero_mobile", sections=[])[0]
        self.assertTrue(frame["approx"])
        self.assertTrue(all(f["fit"] == "cover" for f in upload_frames.resolve_frames("hero_desktop", sections=[])))

    def test_resolver_is_read_only_and_never_provisions_a_layout(self):
        self.assertEqual(upload_frames.resolve_frames("product_image", store=None, sections=None), [])


class GuideTagTests(TestCase):
    def test_tag_renders_real_limits_frames_and_confirm_event(self):
        from django.template import Context, Template

        html = Template('{% load image_guide %}{% image_guide "product_image" "images" "imgguide-confirm" %}').render(
            Context({"guide_sections": [SimpleNamespace(section_key="newest_products", settings={"title": "تازه‌ها", "card": {"image_ratio": "portrait"}}, is_active=True)]}))
        self.assertIn('data-image-guide="product_image"', html)
        self.assertIn('data-confirm-event="imgguide-confirm"', html)
        self.assertIn("در قالب فعلی شما این تصویر در این قاب‌ها دیده می‌شود", html)
        self.assertIn("تازه‌ها", html)
        self.assertIn("حداکثر ۵ مگابایت (اعمال می‌شود)", html)
        self.assertIn("JPG، PNG، WebP", html)
        self.assertNotIn("GIF", html.replace("GIF8", ""))

    def test_tag_without_a_store_falls_back_to_the_static_ratio(self):
        from django.template import Context, Template

        html = Template('{% load image_guide %}{% image_guide "brand_logo" "logo" %}').render(Context({}))
        self.assertIn('data-image-guide="brand_logo"', html)
        self.assertNotIn("imgguide-frames-note", html)
        self.assertNotIn("data-confirm-event", html)


class StudioMediaDialogsAllCarryAGuideTests(SimpleTestCase):
    def test_every_media_kind_file_field_has_a_known_guide_slot(self):
        from apps.storefront_builder import media_views

        expected = {"hero-slides": ["hero_desktop", "hero_mobile"], "banners": ["banner_desktop", "banner_mobile"], "story-items": ["story_item"]}
        for kind, config in media_views._MEDIA_KINDS.items():
            slots = [f.get("guide_key") for f in config["file_fields"]]
            self.assertEqual(slots, expected[kind], kind)
            for slot in slots:
                self.assertIn(slot, image_specs.SPECS)

    def test_files_partial_renders_the_guide_per_field_and_the_view_passes_its_section(self):
        files = (APPS / "storefront_builder" / "templates" / "dashboard" / "storefront_builder" / "partials" / "media_form" / "_files.html").read_text(encoding="utf-8")
        self.assertIn("{% image_guide f.guide_key f.name %}", files)
        view = (APPS / "storefront_builder" / "media_views.py").read_text(encoding="utf-8")
        self.assertIn('"guide_sections": [section]', view)

    def test_no_surface_announces_gif_svg_avif_or_heic_as_supported(self):
        for spec in image_specs.SPECS.values():
            joined = " ".join((spec.usage, spec.safe_area, spec.crop, spec.extra) + tuple(spec.formats))
            for bad in ("GIF", "AVIF", "HEIC"):
                self.assertNotIn(bad, joined, spec.key)
            if "SVG" in joined:
                self.assertIn("پذیرفته نمی‌شود", joined, spec.key)  # only ever mentioned as NOT accepted


class GuideNeverShowsStaleStateTests(SimpleTestCase):
    """R4-14b — QA saw a red GIF error next to the previous picture's preview and a green «نسبت مناسب است». That green sentence only exists in
    the R4-13 script: the browser was still running a cached copy (the guide assets were linked without a version), and that old script painted
    a preview/green note for ANY readable file. Two guards keep it from coming back."""

    def test_guide_assets_are_linked_with_a_content_version_so_a_patch_replaces_cached_copies(self):
        base = (APPS / "dashboard" / "templates" / "dashboard" / "base_admin.html").read_text(encoding="utf-8")
        self.assertIn("{% static_v 'core/image_guide.js' %}", base)
        self.assertIn("{% static_v 'core/image_guide.css' %}", base)
        self.assertNotIn("{% static 'core/image_guide.js' %}", base)

    def test_versioned_url_changes_with_the_file(self):
        from apps.storefront_builder.templatetags.storefront_builder_extras import static_v

        self.assertRegex(static_v("core/image_guide.js"), r"image_guide\.js\?v=[0-9a-f]{10}$")

    def test_a_late_result_of_an_older_selection_is_discarded(self):
        self.assertIn("guide._seq = (guide._seq || 0) + 1", JS)
        self.assertIn("if (guide._seq !== seq)", JS)

    def test_an_invalid_file_is_dropped_from_a_plain_form_input_and_gets_no_preview(self):
        self.assertIn("input.value = '';", JS)
        self.assertIn("if (info.ok && !v.errors.length) renderPreview", JS)
        self.assertIn("تصویرِ فعلی تغییری نمی‌کند", JS)

    def test_the_old_always_green_sentence_is_gone(self):
        self.assertNotIn("نسبتِ تصویر برایِ این جایگاه مناسب است", JS)
