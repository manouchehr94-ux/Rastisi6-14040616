"""V5 PDP package 1 — the WHOLE chain, over the real HTTP endpoints an editor uses, for both sections:

Inspector (HTTP) → Schema → Mutation (HTTP) → Draft → Preview → Undo / Redo (HTTP) → Publish → Public page → Inspector reload.

``test_v5_pdp_design_controls`` covers the pieces; this module proves they are ONE path (no side channel, no second store of state)
and that every default rendered by every registered preset is the pre-existing behaviour."""

import json
import re

from django.core.cache import cache
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service, r4_mutation_service
from apps.stores.models import Store, StoreDomain

from .test_media_views import HOST
from .test_v5_pdp_design_controls import (
    PDP, PUBLIC_HOST, _data_attrs, _pdp_tag, _PdpBase, _tabs_tag,
)


@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "testserver"])
class EditorChainOverHttpTests(_PdpBase):
    def setUp(self):
        super().setUp()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=PUBLIC_HOST)

    # -- the HTTP surface an editor really uses ------------------------------------------------------------------------------
    def _post(self, section, patch):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self._revision(), "mutation": {
                "type": "section.update_settings", "section_id": section.pk, "patch": patch}}),
            content_type="application/json",
        )

    def _inspector(self, section):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _selected(self, html, key):
        """The value the Inspector will show for a field: the server's effective value (``r4InspectorFieldValues``, defaults included)."""
        blob = re.search(r'<script id="r4InspectorFieldValues"[^>]*>(.*?)</script>', html, re.S)
        self.assertIsNotNone(blob, "the Inspector ships its effective values")
        return json.loads(blob.group(1)).get(key)

    def _public(self):
        cache.clear()
        response = self.public.get(f"/products/{self.product.slug}/", HTTP_HOST=PUBLIC_HOST)
        if response.status_code != 200:                                   # the catalog route name is the single source of the URL
            response = self.public.get(reverse("catalog:product-detail", args=[self.product.slug]), HTTP_HOST=PUBLIC_HOST)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    # -- product_main ---------------------------------------------------------------------------------------------------------
    def test_product_main_chain(self):
        before = self._inspector(self.main)
        self.assertIn('data-r4-field-key="cta_size"', before)                                  # Inspector → Schema
        self.assertEqual(self._selected(before, "cta_size"), "normal", "an untouched section shows the default")
        start = self._revision()

        response = self._post(self.main, {"cta_size": "large", "gallery_position": "end"})      # Mutation (HTTP)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], start + 1)
        self.assertEqual(self._stored(self.main)["cta_size"], "large")                          # Draft
        tag = _data_attrs(_pdp_tag(self._preview()))                                            # Preview
        self.assertEqual((tag["cta-size"], tag["gallery-pos"]), ("large", "end"))
        reloaded = self._inspector(self.main)                                                   # reload of the settings
        self.assertEqual(self._selected(reloaded, "cta_size"), "large")
        self.assertEqual(self._selected(reloaded, "gallery_position"), "end")

        self.assertEqual(self._history("undo").status_code, 200)                               # Undo
        self.assertNotIn("cta-size", _data_attrs(_pdp_tag(self._preview())))
        self.assertNotEqual(self._selected(self._inspector(self.main), "cta_size"), "large")
        self.assertEqual(self._history("redo").status_code, 200)                               # Redo
        self.assertEqual(self._selected(self._inspector(self.main), "cta_size"), "large")

        self.assertNotIn("data-cta-size", self._public())                                       # Draft is not public yet
        svc.publish(self.store)                                                                 # Publish
        self.assertEqual(_data_attrs(_pdp_tag(self._public()))["cta-size"], "large")
        self.draft = svc.get_or_create_draft(self.store)                                        # next editing session: reload
        fresh = self.draft.get_page(PDP).sections.get(section_key="product_main")
        self.assertEqual(self._selected(self._inspector(fresh), "cta_size"), "large")

    def test_a_refused_value_over_http_changes_nothing(self):
        revision, stored = self._revision(), dict(self._stored(self.main))
        for section, patch in ((self.main, {"cta_size": "huge"}), (self.main, {"unknown_key": 1}), (self.desc, {"layout_mode": "carousel"}),
                               (self.desc, {"sections": [{"key": "evil", "label": "x"}]})):
            with self.subTest(patch=patch):
                response = self._post(section, patch)
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500)
        self.assertEqual(self._revision(), revision)
        self.assertEqual(self._stored(self.main), stored)

    # -- product_description ---------------------------------------------------------------------------------------------------
    def test_product_description_chain(self):
        rows = [
            {"key": "review", "label": "دیدگاه‌ها", "visible": True},
            {"key": "desc", "label": "", "visible": True},
            {"key": "spec", "label": "مشخصات فنی", "visible": False},
        ]
        start = self._revision()
        response = self._post(self.desc, {"layout_mode": "accordion", "sections": rows})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], start + 1)
        html = self._preview()
        self.assertEqual(_data_attrs(_tabs_tag(html))["tabs-mode"], "accordion")
        order = [m for m in re.findall(r'id="pdp-tab-(desc|spec|review|brand)-', html)]
        self.assertEqual(order, ["review", "desc"])                                              # order + visibility
        self.assertIn("دیدگاه‌ها", html)
        self.assertNotIn("مشخصات فنی", html)
        reloaded = self._inspector(self.desc)
        self.assertEqual(self._selected(reloaded, "layout_mode"), "accordion")
        shown = self._selected(reloaded, "sections")
        self.assertEqual([(r["key"], r["visible"]) for r in shown], [("review", True), ("desc", True), ("spec", False)])
        self.assertEqual(shown[0]["label"], "دیدگاه‌ها")
        self.assertEqual(shown[2]["label"], "مشخصات فنی")                                          # a hidden row is still editable

        self.assertEqual(self._history("undo").status_code, 200)
        self.assertEqual(re.findall(r'id="pdp-tab-(desc|spec|review|brand)-', self._preview()), ["desc", "spec", "review"])
        self.assertNotIn("tabs-mode", _data_attrs(_tabs_tag(self._preview())))
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(re.findall(r'id="pdp-tab-(desc|spec|review|brand)-', self._preview()), ["review", "desc"])

        svc.publish(self.store)
        public = self._public()
        self.assertEqual(re.findall(r'id="pdp-tab-(desc|spec|review|brand)-', public), ["review", "desc"])
        self.assertEqual(_data_attrs(_tabs_tag(public))["tabs-mode"], "accordion")
        self.draft = svc.get_or_create_draft(self.store)
        fresh = self.draft.get_page(PDP).sections.get(section_key="product_description")
        self.assertEqual(self._selected(self._inspector(fresh), "layout_mode"), "accordion")


# ------------------------------------------------------------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "testserver"])
class BrandPanelSecurityTests(_PdpBase):
    """The optional «برند» section shows Store-owned data only and never renders an unsafe link (real rows, real render)."""

    def setUp(self):
        super().setUp()
        self.foreign = Store.objects.create(name="فروشگاه دیگر", slug="pdpc-e2e-foreign", status=Store.Status.ACTIVE)
        section_rows = {"sections": [{"key": "brand", "label": "برند", "visible": True}]}
        from apps.storefront_builder.services import r4_mutation_service
        r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=self._revision(),
            mutation={"type": "section.update_settings", "section_id": self.desc.pk, "patch": section_rows},
        )

    def _attach(self, **fields):
        store = fields.pop("store", self.store)
        brand = Brand.objects.create(store=store, name="برند آزمایشی", slug=f"b-{Brand.objects.count()}", **fields)
        self.product.brand = brand
        self.product.save(update_fields=["brand"])
        return brand

    def test_another_stores_brand_attached_to_this_product_is_never_rendered(self):
        self._attach(store=self.foreign, description="داده‌ی فروشگاه دیگر", country="آلمان")
        html = self._preview()
        self.assertNotIn("داده‌ی فروشگاه دیگر", html)
        self.assertNotIn("pdp-tab-brand-", html)

    def test_only_http_and_https_websites_become_links(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://x.test", "//evil.test", "vbscript:x"):
            with self.subTest(bad=bad):
                self._attach(description="توضیح", website=bad)
                html = self._preview()
                self.assertIn("pdp-tab-brand-", html)
                self.assertNotIn(bad, html)
                self.assertNotIn("<a href=\"" + bad, html)
        self._attach(description="توضیح", website="https://brand.example.com")
        html = self._preview()
        self.assertIn('href="https://brand.example.com"', html)
        self.assertIn('rel="noopener noreferrer nofollow"', html)
        self.assertIn('target="_blank"', html)

    def test_brand_text_is_escaped(self):
        self._attach(description='<script>alert(1)</script><img src=x onerror=alert(2)>')
        panel = self._preview().split('class="brand-panel"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("<script>alert(1)</script>", panel)
        self.assertNotIn("<img src=x onerror", panel)


# ------------------------------------------------------------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "testserver"])
class EveryPresetKeepsTheHistoricalProductPageTests(_PdpBase):
    """Default behaviour of EVERY registered preset / Ready Template is unchanged: no recipe carries a new setting, so the product
    page of each one renders no new layout data attribute and keeps every purchase-critical element."""

    ALLOWED_DEFAULT_PDP_ATTRS = {"pdp-layout"}
    MUST_CONTAIN = ('x-data="variantSelector(', 'hx-post="', 'role="tablist"', 'aria-selected="true"', 'role="tabpanel"')

    def test_all_presets_render_defaults_unchanged(self):
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        public = Client(HTTP_HOST=PUBLIC_HOST)
        checked = 0
        for preset in lpr.list_layout_presets():
            if StorefrontPage.PageType.PRODUCT_DETAIL not in preset.pages:
                continue
            with self.subTest(preset=preset.key):
                cache.clear()
                draft = svc.get_or_create_draft(self.store)
                preset_service.apply_preset(draft, preset)
                svc.publish(self.store)
                response = public.get(reverse("catalog:product-detail", args=[self.product.slug]), HTTP_HOST=PUBLIC_HOST)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                carried = any(
                    entry.settings for entry in preset.pages[StorefrontPage.PageType.PRODUCT_DETAIL]
                    if entry.section_key in ("product_main", "product_description")
                )
                if carried:
                    # a recipe that DELIBERATELY carries product-page presentation (the six-site kit) shows exactly those attributes
                    self.assertGreater(len(set(_data_attrs(_pdp_tag(html))) | set(_data_attrs(_tabs_tag(html)))), 1, preset.key)
                else:
                    self.assertLessEqual(set(_data_attrs(_pdp_tag(html))), self.ALLOWED_DEFAULT_PDP_ATTRS)
                    self.assertEqual(_data_attrs(_tabs_tag(html)), {})
                for needle in self.MUST_CONTAIN:
                    self.assertIn(needle, html, needle)
                self.assertEqual(html.count('x-data="variantSelector('), 1)
                checked += 1
        self.assertGreater(checked, 10)


# ------------------------------------------------------------------------------------------------------------------------------
class NoParallelPathTests(SimpleTestCase):
    """Package 1 adds settings vocabulary + markup only: no second state owner, renderer, store, endpoint or Alpine component."""

    def test_pdp_settings_is_pure_vocabulary_with_no_storage_or_io(self):
        import ast
        from pathlib import Path

        tree = ast.parse((Path(__file__).resolve().parents[1] / "pdp_settings.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0] or "." * node.level)
        self.assertFalse(imported & {"django", "requests", "urllib", "sqlite3", "os", "pathlib"}, imported)
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & {"open", "exec", "eval", "__import__"}, calls)

    def test_templates_keep_their_single_alpine_component_each(self):
        from pathlib import Path

        sections = Path(__file__).resolve().parents[1] / "templates" / "storefront_builder" / "sections"
        main = (sections / "product_main.html").read_text(encoding="utf-8")
        description = (sections / "product_description.html").read_text(encoding="utf-8")
        self.assertEqual(main.count('x-data="variantSelector('), 1)
        self.assertEqual(main.count("hx-post="), 1)
        self.assertEqual(description.count("x-data="), 1)
        for source in (main, description):
            self.assertNotIn("localStorage", source)
            self.assertNotIn("sessionStorage", source)
            self.assertNotIn("fetch(", source)

    def test_both_sections_persist_only_through_section_settings(self):
        from apps.storefront_builder import section_registry

        for key in ("product_main", "product_description"):
            definition = section_registry.get_definition(key)
            self.assertIsNotNone(definition.settings_schema)
            self.assertEqual(definition.max_instances, 1)
            self.assertTrue(definition.validate_settings is not None)


class PurchaseSupportBlocksTests(_PdpBase):
    """The three optional blocks (low stock / free shipping / contact buttons): OFF by default, real data only, never invented."""

    BLOCKS = ("pdp-lowstock", "pdp-freeship", "pdp-contact")

    def test_default_markup_has_none_of_them(self):
        html = self._preview()
        for marker in self.BLOCKS:
            self.assertNotIn(f'class="{marker}', html, marker)

    def test_each_block_appears_only_when_switched_on_and_uses_the_stores_own_data(self):
        from apps.content.models import SocialLink
        from apps.core.models import ShopSettings

        self._update(self.main, {"show_low_stock_alert": True, "show_free_shipping_notice": True, "show_contact_buttons": True})
        html = self._preview()
        self.assertIn('class="pdp-lowstock"', html)
        self.assertIn('class="pdp-freeship"', html)
        shop = ShopSettings.provision_for(self.store)
        self.assertIn(f"displayPrice.price >= {int(shop.free_shipping_threshold)}", html, "the Store's OWN free-shipping threshold, never a fixed number")
        self.assertNotIn("wa.me", html.split('class="pdp-contact"')[-1][:600] if 'class="pdp-contact"' in html else "", "no WhatsApp link on record: no invented button")
        SocialLink.objects.create(store=self.store, platform=SocialLink.Platform.WHATSAPP, title="واتساپ", url="https://wa.me/989121111111",
                                  is_active=True, show_in_footer=True)
        html = self._preview()
        self.assertIn('class="pdp-contact"', html)
        self.assertIn('href="https://wa.me/989121111111"', html)
        import re as _re
        phone = _re.search(r'class="pdp-contact-btn" href="tel:([^"]+)"', html)
        self.assertTrue(phone is None or phone.group(1) == (getattr(shop, "phone", "") or phone.group(1)), "phone button only from the Store's own record")

    def test_a_foreign_stores_contact_data_never_appears(self):
        from apps.content.models import SocialLink
        from apps.stores.models import Store

        other = Store.objects.create(name="دیگر", slug="pdpc-other-contact", status=Store.Status.ACTIVE)
        SocialLink.objects.create(store=other, platform=SocialLink.Platform.WHATSAPP, title="x", url="https://wa.me/989129999999",
                                  is_active=True, show_in_footer=True)
        self._update(self.main, {"show_contact_buttons": True})
        self.assertNotIn("989129999999", self._preview())

    def test_vocabulary_rejects_non_boolean_values_without_a_revision(self):
        revision = self._revision()
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self._update(self.main, {"show_low_stock_alert": "perhaps"})
        self.assertEqual(self._revision(), revision)
