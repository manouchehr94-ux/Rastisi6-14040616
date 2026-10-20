"""FOLLOWUP-13 — the per-slot image guide: specs are internally consistent, tied to the real validators, and shown in the real upload forms."""

import io
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.blog.models import BlogPost
from apps.content.models import HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES, validate_image_content
from apps.core import image_specs
from apps.stores.models import Store, StoreMembership

REPO = Path(__file__).resolve().parents[3]
User = get_user_model()
HOST = "imgspec.rastisi.localhost"


class SpecConsistencyTests(SimpleTestCase):
    def test_recommended_size_matches_the_declared_ratio_and_minimum_is_not_bigger(self):
        for spec in image_specs.SPECS.values():
            rw, rh = (int(x) for x in spec.ratio.split(":"))
            self.assertAlmostEqual(spec.recommended[0] / spec.recommended[1], rw / rh, delta=0.03 * rw / rh, msg=spec.key)
            self.assertLessEqual(spec.minimum[0], spec.recommended[0], spec.key)
            self.assertLessEqual(spec.minimum[1], spec.recommended[1], spec.key)
            self.assertTrue(spec.usage and spec.safe_area and spec.crop and spec.alt_hint and spec.renderer, spec.key)

    def test_enforced_limits_are_the_real_validator_constants(self):
        from apps.catalog.services import product_image_service as pis
        from apps.dashboard import forms as dforms

        self.assertEqual(image_specs.get_spec("product_image").max_bytes, pis.MAX_UPLOAD_SIZE_BYTES)
        self.assertEqual(image_specs.get_spec("journal_cover").max_bytes, HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES)
        self.assertEqual(image_specs.get_spec("hero_desktop").max_bytes, HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES)
        self.assertEqual(image_specs.get_spec("shop_logo").max_bytes, dforms.MAX_LOGO_SIZE)
        self.assertEqual(image_specs.get_spec("favicon").max_bytes, dforms.MAX_FAVICON_SIZE)

    def test_documented_ratios_match_the_css_they_cite(self):
        css = (REPO / "apps/storefront_builder/static/css/storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn(".journal-cover{aspect-ratio:4/3", css)
        self.assertIn("aspect-ratio:1053/420", css)
        self.assertIn("brand-tile img{max-height:48px", css)
        pc = (REPO / "apps/catalog/static/css/product_card.css").read_text(encoding="utf-8")
        self.assertIn(".pcard .img{position:relative;aspect-ratio:1/1", pc)

    def test_markdown_matrix_lists_every_slot(self):
        md = image_specs.render_media_spec_markdown()
        for spec in image_specs.SPECS.values():
            self.assertIn(spec.label, md)


class UnsafeUploadsAreRejectedTests(SimpleTestCase):
    def _file(self, name, payload, ctype="image/png"):
        return SimpleUploadedFile(name, payload, content_type=ctype)

    def test_svg_html_and_corrupt_files_pass_no_matter_the_extension(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        for name, payload in (("a.png", svg), ("b.jpg", b"<html><script>x</script></html>"), ("c.webp", b"\x89PNG not really"), ("d.png", b"")):
            with self.assertRaises(ValidationError, msg=name):
                validate_image_content(self._file(name, payload))

    def test_a_real_png_passes(self):
        buf = io.BytesIO()
        Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(buf, "PNG")
        validate_image_content(self._file("ok.png", buf.getvalue()))


class GuideTagTests(SimpleTestCase):
    def render(self, key, name=""):
        return Template("{% load image_guide %}{% image_guide key name %}").render(Context({"key": key, "name": name}))

    def test_guide_shows_the_persian_matrix_and_machine_readable_spec(self):
        html = self.render("journal_cover", "cover_image")
        for text in ("راهنمای تصویر", "نسبتِ پیشنهادی", "۴:۳", "۱۶۰۰×۱۲۰۰", "حداقل وضوح", "فرمت", "ناحیهٔ امن", "برش", "متنِ جایگزین", "۵ مگابایت"):
            self.assertIn(text, html)
        self.assertIn('data-input-name="cover_image"', html)
        self.assertIn("&quot;maxBytes&quot;", html)

    def test_recommended_only_limits_are_labelled_as_such(self):
        # R4-14: every shipped spec is now enforced by the server (apps.core.image_validation); the label logic stays for any future
        # recommended-only spec, so it is exercised with a synthetic one
        import dataclasses
        from unittest import mock

        from apps.core.image_specs import SPECS

        self.assertNotIn("(توصیه)", self.render("collection_image"))
        self.assertIn("(اعمال می‌شود)", self.render("collection_image"))
        with mock.patch.dict(SPECS, {"collection_image": dataclasses.replace(SPECS["collection_image"], max_enforced=False)}):
            self.assertIn("(توصیه)", self.render("collection_image"))
        self.assertNotIn("(توصیه)", self.render("shop_logo"))

    def test_unknown_key_renders_nothing(self):
        self.assertEqual(self.render("nope").strip(), "")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class GuidesAreShownInTheRealFormsTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09127910001", password="pass12345")
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127910001", password="pass12345")

    def test_pages_with_an_upload_show_their_slot_guide(self):
        post = BlogPost.objects.create(store=self.store, title="t", slug="t-img", body="b", published_at=timezone.now())
        expectations = {
            reverse("dashboard:journal-edit", args=[post.pk]): ("data-image-guide=\"journal_cover\"",),
            reverse("dashboard:collection-add"): ("data-image-guide=\"collection_image\"",),
            reverse("dashboard:hero-add"): ("data-image-guide=\"hero_desktop\"", "data-image-guide=\"hero_mobile\""),
            reverse("dashboard:banner-add"): ("data-image-guide=\"banner_desktop\"", "data-image-guide=\"banner_mobile\""),
        }
        for url, needles in expectations.items():
            html = self.client.get(url).content.decode()
            for needle in needles:
                self.assertIn(needle, html, f"{url} {needle}")

    def test_remaining_upload_templates_declare_their_guides(self):
        base = REPO / "apps/dashboard/templates/dashboard"
        needles = {
            "partials/brand_form_modal.html": 'image_guide "brand_logo"',
            "partials/settings_general.html": 'image_guide "shop_logo"',
            "partials/product_images_modal.html": 'image_guide "product_image"',
            "footer_trust_badge_form.html": 'image_guide "footer_badge"',
            "footer_payment_logo_form.html": 'image_guide "footer_badge"',
            "partials/attribute_values_list.html": 'image_guide "swatch_image"',
        }
        for rel, needle in needles.items():
            self.assertIn(needle, (base / rel).read_text(encoding="utf-8"), rel)

    def test_the_brand_form_no_longer_advertises_svg(self):
        text = (REPO / "apps/dashboard/templates/dashboard/partials/brand_form_modal.html").read_text(encoding="utf-8")
        self.assertNotIn(".svg", text)
