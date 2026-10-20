"""RS-03 — the footer never fabricates credential squares: with a ``badge_slots`` block (Template 51) and no real badge the
region renders nothing; real badges/e-namad/payment logos render only when enabled AND their file exists."""

import io
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from PIL import Image

from apps.content.context_processors import footer_settings
from apps.content.models import FooterPaymentLogo, FooterSettings, FooterTrustBadge
from apps.stores.models import Store

PARTIAL = "storefront_builder/partials/global_footer/_shared/badge_slots_row.html"
_MEDIA = tempfile.mkdtemp(prefix="rs03-media-")


def _img(name):
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "green").save(buf, "PNG")
    return ContentFile(buf.getvalue(), name=name)


def render(**ctx):
    base = {"fc": {"show_trust_badges": True, "show_payment_logos": True, "extra_blocks": [{"type": "badge_slots", "count": 5}]},
            "rc": {}, "FOOTER_TRUST_BADGES": [], "FOOTER_PAYMENT_LOGOS": []}
    base.update(ctx)
    return render_to_string(PARTIAL, base)


class SlotsNeverFabricateTests(TestCase):
    def test_no_real_credentials_means_no_elements_at_all(self):
        html = render()
        self.assertNotIn("gf-trust-badge-item", html)
        self.assertNotIn("gf-credibility", html)
        self.assertEqual(html.strip(), "")

    def test_five_slot_block_with_the_toggle_off_still_renders_nothing(self):
        html = render(fc={"show_trust_badges": False, "show_payment_logos": False, "extra_blocks": [{"type": "badge_slots", "count": 5}]})
        self.assertEqual(html.strip(), "")


@override_settings(MEDIA_ROOT=_MEDIA)
class RealCredentialsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = True
        fs.show_payment_logos = True
        fs.save()

    def context(self):
        request = RequestFactory().get("/")
        request.store = self.store
        return footer_settings(request)

    def test_a_real_badge_renders_exactly_one_item_and_no_filler(self):
        FooterTrustBadge.objects.create(store=self.store, title="نماد واقعی", image=_img("real.png"), is_active=True)
        ctx = self.context()
        html = render(FOOTER_TRUST_BADGES=ctx["FOOTER_TRUST_BADGES"], FOOTER_PAYMENT_LOGOS=ctx["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(html.count("gf-trust-badge-item"), 1)
        self.assertNotIn("--empty", html)
        self.assertIn("نماد واقعی", html)

    def test_a_badge_whose_file_is_missing_is_skipped_not_drawn_as_a_blank_tile(self):
        badge = FooterTrustBadge.objects.create(store=self.store, title="گم‌شده", image=_img("gone.png"), is_active=True)
        badge.image.storage.delete(badge.image.name)
        FooterPaymentLogo.objects.create(store=self.store, title="پرداخت", image=_img("pay.png"), is_active=True)
        ctx = self.context()
        self.assertEqual(list(ctx["FOOTER_TRUST_BADGES"]), [])
        html = render(FOOTER_TRUST_BADGES=ctx["FOOTER_TRUST_BADGES"], FOOTER_PAYMENT_LOGOS=ctx["FOOTER_PAYMENT_LOGOS"])
        self.assertNotIn("gf-trust-badge-item", html)
        self.assertEqual(html.count("gf-payment-logos"), 1)

    def test_toggle_off_hides_real_badges_too(self):
        FooterTrustBadge.objects.create(store=self.store, title="x", image=_img("t.png"), is_active=True)
        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = False
        fs.save()
        self.assertEqual(list(self.context()["FOOTER_TRUST_BADGES"]), [])

    def test_another_stores_badge_never_appears(self):
        other = Store.objects.create(name="B", slug="rs03-other", status=Store.Status.ACTIVE)
        FooterTrustBadge.objects.create(store=other, title="دیگر", image=_img("o.png"), is_active=True)
        self.assertEqual(list(self.context()["FOOTER_TRUST_BADGES"]), [])


class MapLinkIsOptInTests(TestCase):
    """The footer shows the address text; a map link only when the merchant confirmed the address is real/routable."""

    PARTIAL = "storefront_builder/partials/global_footer/_shared/contact_info.html"

    def render(self, **fields):
        fs = FooterSettings(address="تهران - آدرس نمایشی Demo (بدون آدرس واقعی)", show_contact=True, **fields)
        return render_to_string(self.PARTIAL, {"FOOTER_SETTINGS": fs, "fc": {"show_contact": True}, "rc": {}})

    def test_default_has_no_map_link_but_keeps_the_address_text(self):
        html = self.render()
        self.assertIn("آدرس نمایشی Demo", html)
        self.assertNotIn("openstreetmap", html)
        self.assertNotIn("gf-map-link", html)

    def test_confirmed_address_gets_the_link(self):
        self.assertIn("openstreetmap.org/search?query=", self.render(show_map_link=True))

    def test_field_defaults_to_false_for_every_existing_and_new_row(self):
        self.assertFalse(FooterSettings._meta.get_field("show_map_link").default)
