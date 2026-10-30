"""Hero Stage templates — acceptance chain on a throw-away database.

For each of the four official templates: registry → official apply (Draft only) → the real R4 mutation API (six+ controls) → saved →
Preview → Undo / Redo → Publish → the live storefront (and "refresh" = a brand-new request). Plus: cross-preset recombination without any
template-id condition, two Stores with their own data, tenant isolation of media, malformed payloads / permissions, existing templates
untouched, responsive hide flags, gallery live preview. Real-browser (Chromium) coverage of the same chain lives in
``test_hero_stage_browser.py`` (opt-in)."""

import json
import re
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import MediaAsset
from apps.storefront_builder import hero_stage
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion
from apps.storefront_builder.services import appearance_authority_service as authority
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import template_preview_service
from apps.storefront_builder.storefront_appearance.inventory import recipe_signature
from apps.stores.models import Store, StoreDomain, StoreMembership

from .test_r4_mutation_api import R4MutationApiTestCase

User = get_user_model()
APP = Path(__file__).resolve().parents[1]
PUBLIC_A = "hs-a-public.example.com"
PUBLIC_B = "hs-b-public.example.com"
TEMPLATES = ("dual_atelier", "editorial_noir", "glass_commerce", "asymmetric_canvas")


def _png(name="stage.png", colour=(40, 90, 160)):
    buf = BytesIO()
    Image.new("RGB", (600, 360), colour).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _stage_html(body):
    match = re.search(r'<section class="hs-stage".*?</section>', body, re.S)
    return match.group(0) if match else ""


@override_settings(ALLOWED_HOSTS=["*"])
class StageTemplateAcceptanceTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # Store A (the fixture store) gets a public host, its own catalogue and pictures
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public_a = Client(HTTP_HOST=PUBLIC_A)
        vendor_a = Vendor.objects.create(store=self.store, name="فروشنده الف", slug="hs-vendor-a")
        self.cat_a = Category.objects.create(store=self.store, name="دستهٔ الفِ آزمون", slug="hs-cat-a", is_active=True)
        self.product_a = Product.objects.create(
            store=self.store, vendor=vendor_a, category=self.cat_a, name="کالای الفِ آزمون", slug="hs-prod-a", sku="HSA-1",
            price=111000, stock=5, status=Product.Status.ACTIVE,
        )
        self.asset_a1 = MediaAsset.objects.create(store=self.store, image=_png("a1.png", (200, 80, 80)))
        self.asset_a2 = MediaAsset.objects.create(store=self.store, image=_png("a2.png", (80, 200, 80)))
        # Store B — completely different data and pictures
        self.store_b = Store.objects.create(
            name="فروشگاه ب", slug="hs-store-b", admin_subdomain="hs-store-b", status=Store.Status.ACTIVE,
        )
        StoreDomain.objects.create(
            store=self.store_b, hostname=PUBLIC_B, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public_b = Client(HTTP_HOST=PUBLIC_B)
        vendor_b = Vendor.objects.create(store=self.store_b, name="فروشنده ب", slug="hs-vendor-b")
        self.cat_b = Category.objects.create(store=self.store_b, name="دستهٔ بِ آزمون", slug="hs-cat-b", is_active=True)
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=vendor_b, category=self.cat_b, name="کالای بِ آزمون", slug="hs-prod-b", sku="HSB-1",
            price=222000, stock=5, status=Product.Status.ACTIVE,
        )
        self.asset_b = MediaAsset.objects.create(store=self.store_b, image=_png("b1.png", (80, 80, 200)))

    # ------------------------------------------------------------------------------------------------------------ helpers
    def _draft(self):
        return svc.get_or_create_draft(self.store, user=self.staff)

    def _apply(self, key):
        response = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": key, "confirm_preset_apply": "1"},
        )
        self.assertEqual(response.status_code, 302, key)
        draft = self._draft()
        self.assertEqual(draft.template_provenance["template"]["key"], key)
        return draft

    def _stage(self):
        draft = self._draft()
        stage = draft.get_page("home").sections.filter(section_key="hero_stage").first()
        self.assertIsNotNone(stage, "the template must put a hero_stage on its home page")
        return stage

    def _mutate(self, patch, *, expect=200):
        draft = self._draft()
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": draft.edit_revision,
                "mutation": {"type": "section.update_settings", "section_id": self._stage().pk, "patch": patch},
            }), content_type="application/json",
        )
        self.assertEqual(response.status_code, expect, response.content[:300])
        return response

    def _history(self, command):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "command": command}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["changed"])

    def _publish(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps({"base_revision": self._draft().edit_revision}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        cache.clear()

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()

    def _live(self, client=None):
        return (client or self.public_a).get(reverse("catalog:home")).content.decode()

    # ------------------------------------------------------------------------------------------------------------ registry
    def test_the_four_templates_are_official_distinct_and_have_cards(self):
        ready = {preset.key: preset for preset in lpr.list_ready_templates()}
        signatures, thumbnails = set(), set()
        for key in TEMPLATES:
            with self.subTest(template=key):
                preset = ready[key]
                self.assertTrue(preset.label_fa.strip() and preset.description_fa.strip())
                self.assertEqual(preset.pages["home"][0].section_key, "hero_stage")
                signatures.add(recipe_signature(preset))
                svg = template_preview_service.build_template_thumbnail_svg(preset)
                self.assertTrue(svg.startswith("<svg"))
                thumbnails.add(svg)
        self.assertEqual(len(signatures), 4)
        self.assertEqual(len(thumbnails), 4, "four visibly different gallery thumbnails")
        headers = {ready[key].header["header_variant"] for key in TEMPLATES}
        self.assertEqual(len(headers), 4, "four different registered header variants")

    def test_no_engine_file_knows_a_template_key(self):
        sources = [
            APP / "hero_stage.py", APP / "templates/storefront_builder/sections/hero_stage.html",
            APP / "templates/storefront_builder/partials/hero_stage_header.html", APP / "services/render_service.py",
            APP / "services/storefront_context_service.py", APP / "services/template_preview_service.py",
        ]
        css = (APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")
        stage_css = css[css.index("hero stage (``hero_stage`` section)"):css.index("FOLLOWUP-08 — ONE mobile contract")]
        for key in TEMPLATES:
            for path in sources:
                self.assertNotIn(key, path.read_text(encoding="utf-8"), f"{path.name} names the template {key}")
            self.assertNotIn(key, stage_css)

    # ------------------------------------------------------------------------------------------------------------ selection
    def test_selecting_a_template_changes_only_the_draft_of_that_store(self):
        self._draft()
        svc.publish(self.store, user=self.staff)
        svc.get_or_create_draft(self.store_b, user=self.staff)
        published_b = svc.publish(self.store_b, user=self.staff)
        layout_a = StorefrontLayout.objects.get(store=self.store)
        published = layout_a.published_version
        fingerprint = published.compute_fingerprint()
        fingerprint_b = published_b.compute_fingerprint()
        for key in TEMPLATES:
            self._apply(key)
            layout_a.refresh_from_db()
            published.refresh_from_db()
            self.assertEqual(layout_a.published_version_id, published.pk)
            self.assertEqual(published.compute_fingerprint(), fingerprint, f"{key} must not touch the published version")
            self.assertEqual(StorefrontLayout.objects.get(store=self.store_b).published_version.compute_fingerprint(), fingerprint_b)
            self.assertNotIn("hs-stage", self._live(), "the live page changes only after Publish")

    def test_the_applied_page_uses_the_container_layout_and_the_stage_is_first(self):
        for key in TEMPLATES:
            with self.subTest(template=key):
                self._apply(key)
                page = self._draft().get_page("home")
                self.assertTrue(page.containers.exists(), "ready templates compose through Containers/Cells")
                self._publish()
                body = self._live()
                self.assertEqual(body.count("<header"), 1)
                self.assertIn("<header", _stage_html(body), "the real header is drawn inside the stage")

    # ------------------------------------------------------------------------------------------------------------ the chain
    def test_the_full_chain_for_every_template(self):
        for key in TEMPLATES:
            with self.subTest(template=key):
                self._apply(key)
                before = dict(self._stage().settings)
                new_mode = "overlay" if before.get("header_mode") != "overlay" else "merged"
                new_layout = "dual" if before.get("bg_layout") != "dual" else "single"
                reversed_slots = list(reversed(hero_stage.effective_slots(before.get("slots"))))
                changes = {
                    "header_mode": new_mode,                      # 1 header / hero mode
                    "bg_layout": new_layout,                      # 2 background panels
                    "scrim_strength": 71,                         # 3 overlay
                    "content_valign": "top" if before.get("content_valign") != "top" else "bottom",   # 4 position
                    "title_size": "sm" if before.get("title_size") != "sm" else "xl",                  # 5 typography
                    "button_label": "برچسب تازهٔ دکمه",           # 6 CTA
                    "slots": reversed_slots,                      # 7 slot order
                    "bg_a_media_asset_id": self.asset_a1.pk,      # 8 the Store's own picture
                }
                for field, value in changes.items():
                    self._mutate({field: value})
                saved = self._stage().settings                    # saved in the Draft (reload from the database)
                for field in ("header_mode", "bg_layout", "scrim_strength", "content_valign", "title_size", "button_label"):
                    self.assertEqual(saved[field], changes[field], f"{key}.{field}")
                self.assertEqual([slot["key"] for slot in saved["slots"]], [slot["key"] for slot in reversed_slots])

                preview = _stage_html(self._preview())            # the real Preview shows it
                self.assertIn(f'data-hs-header="{new_mode}"', preview)
                self.assertIn(f'data-hs-layout="{new_layout}"', preview)
                self.assertIn("--hs-scrim:0.71", preview)
                self.assertIn("برچسب تازهٔ دکمه", preview)
                self.assertIn(self.asset_a1.image.url, preview)

                for _ in changes:                                  # Undo walks back through every change…
                    self._history("undo")
                restored = self._stage().settings
                self.assertEqual(restored.get("header_mode"), before.get("header_mode"))
                self.assertEqual(restored.get("button_label"), before.get("button_label"))
                self.assertNotIn("bg_a_media_asset_id", {k for k, v in restored.items() if v})
                self.assertEqual(self._draft().pages.count(), 6, "Undo must never lose a page of the Draft")
                for _ in changes:                                  # …and Redo replays them
                    self._history("redo")
                self.assertEqual(self._draft().pages.count(), 6, "Redo must never lose a page of the Draft")
                self.assertEqual(self._stage().settings["button_label"], "برچسب تازهٔ دکمه")

                self._publish()                                    # Publish -> the live Storefront of THIS store
                for _ in range(2):                                 # (second loop = "refresh": a brand-new request)
                    live = _stage_html(self._live())
                    self.assertIn(f'data-hs-header="{new_mode}"', live, key)
                    self.assertIn(f'data-hs-layout="{new_layout}"', live, key)
                    self.assertIn("--hs-scrim:0.71", live, key)
                    self.assertIn("برچسب تازهٔ دکمه", live, key)
                    self.assertIn(self.asset_a1.image.url, live, key)
                    self.assertEqual(self._live().count("<header"), 1 if new_mode != "independent" else 1)
                live_stage = _stage_html(self._live())
                classes = {"eyebrow": "hs-eyebrow", "title": "hs-title", "subtitle": "hs-subtitle", "cta": "hs-cta-wrap",
                           "categories": "hs-cats", "product_card": "hs-card"}
                expected = [classes[s["key"]] for s in reversed_slots if f'hs-slot {classes[s["key"]]}' in live_stage]
                order = [m.group(1) for m in re.finditer(r'class="hs-slot (hs-[a-z-]+)', live_stage)]
                self.assertEqual(order, expected, f"{key}: the rendered slot order is the merchant's order")

    # ------------------------------------------------------------------------------------------------------------ cross preset
    def test_a_header_from_one_template_works_with_the_stage_of_another(self):
        self._apply("asymmetric_canvas")                           # overlay stage, 70/30 dual panels, floating_compact header
        authority.apply_header_variant(version=self._draft(), header_variant="editorial_masthead")   # header of editorial_noir
        self._mutate({"bg_a_media_asset_id": self.asset_a1.pk, "bg_b_media_asset_id": self.asset_a2.pk})
        self._publish()
        live = self._live()
        stage = _stage_html(live)
        self.assertEqual(live.count("<header"), 1)
        self.assertIn('data-hs-header="overlay"', stage)
        self.assertIn('data-hs-split="first_dominant"', stage)
        self.assertIn("gh-shell", stage)                           # the masthead header is rendered inside the stage
        self.assertIn(self.asset_a2.image.url, stage)
        self.assertIn(self.asset_a1.image.url, stage)

    def test_stage_settings_of_one_template_can_be_copied_onto_another(self):
        self._apply("editorial_noir")
        donor = {k: v for k, v in self._stage().settings.items() if k in {"header_mode", "card_position", "slots", "title_size", "bg_layout"}}
        self._apply("glass_commerce")
        for field, value in donor.items():
            self._mutate({field: value})
        self._publish()
        stage = _stage_html(self._live())
        self.assertIn('data-hs-card="side"', stage)
        self.assertIn("hs-card", stage)                            # the floating product card of the other template
        self.assertIn(self.product_a.name, stage)

    # ------------------------------------------------------------------------------------------------------------ tenants
    def test_two_stores_render_only_their_own_data(self):
        self._apply("glass_commerce")
        self._mutate({"bg_a_media_asset_id": self.asset_a1.pk})
        self._publish()
        # Store B: apply a different template through the same service layer
        draft_b = svc.get_or_create_draft(self.store_b, user=self.staff)
        from apps.storefront_builder.services import preset_service

        preset_service.apply_preset(draft_b, lpr.get_layout_preset("editorial_noir"))
        stage_b = draft_b.get_page("home").sections.get(section_key="hero_stage")
        stage_b.settings = {**stage_b.settings, "bg_a_media_asset_id": self.asset_b.pk}
        stage_b.save(update_fields=["settings"])
        svc.publish(self.store_b, user=self.staff)
        cache.clear()
        live_a, live_b = self._live(self.public_a), self._live(self.public_b)
        stage_a, stage_b_html = _stage_html(live_a), _stage_html(live_b)
        self.assertIn(self.cat_a.name, stage_a)
        self.assertNotIn(self.cat_b.name, live_a)
        self.assertIn(self.asset_a1.image.url, stage_a)
        self.assertNotIn(self.asset_b.image.url, live_a)
        self.assertIn(self.product_b.name, stage_b_html)             # editorial_noir -> the floating product card
        self.assertNotIn(self.product_a.name, live_b)
        self.assertIn(self.asset_b.image.url, stage_b_html)
        self.assertNotIn(self.asset_a1.image.url, live_b)
        self.assertNotIn('data-hs-header="independent"', stage_a)

    def test_a_foreign_media_asset_is_refused_and_never_rendered(self):
        self._apply("dual_atelier")
        before = dict(self._stage().settings)
        self._mutate({"bg_a_media_asset_id": self.asset_b.pk}, expect=400)
        self.assertEqual(self._stage().settings, before)
        stage = self._stage()
        stage.settings = {**stage.settings, "bg_a_media_asset_id": self.asset_b.pk}   # even if it got stored some other way
        stage.save(update_fields=["settings"])
        self._publish()
        live = self._live()
        self.assertNotIn(self.asset_b.image.url, live)
        self.assertEqual(live.count("<header"), 1)

    # ------------------------------------------------------------------------------------------------------------ validation / security
    def test_malformed_and_oversized_payloads_are_rejected_without_any_change(self):
        self._apply("dual_atelier")
        before, revision = dict(self._stage().settings), self._draft().edit_revision
        bad = (
            {"header_mode": "evil"}, {"scrim_strength": 500}, {"height_desktop": 5}, {"title": "x" * 500},
            {"slots": [{"key": "title"}] * 9}, {"slots": [{"key": "nope"}]}, {"slots": "nope"}, {"bg_layout": ["dual"]},
            {"fallback_color": "javascript:alert(1)"}, {"bg_a_media_asset_id": "abc"},
        )
        for patch in bad:
            with self.subTest(patch=patch):
                response = self._mutate(patch, expect=400)
                self.assertTrue(response.json().get("message") or response.json().get("code"))
        self.assertEqual(self._stage().settings, before)
        self.assertEqual(self._draft().edit_revision, revision, "a refused patch never creates a revision or a history step")

    def test_script_and_css_in_text_settings_never_reach_the_page_unescaped(self):
        self._apply("editorial_noir")
        self._mutate({"title": "<script>alert(1)</script>", "eyebrow": "a\" onmouseover=\"x", "subtitle": "</style><b>x</b>"})
        self._publish()
        stage = _stage_html(self._live())
        self.assertNotIn("<script>alert(1)", stage)
        self.assertNotIn('onmouseover="x', stage)
        self.assertNotIn("<b>x</b>", stage)
        self.assertRegex(re.search(r'<section class="hs-stage"[^>]*style="([^"]*)"', stage).group(1), r"^(--hs-[a-z-]+:[^;<>\"']+;?)+$")

    def test_a_user_without_the_storefront_permission_cannot_change_the_stage(self):
        self._apply("dual_atelier")
        analyst = User.objects.create_user(username="hs_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        host = self.client.defaults["HTTP_HOST"]
        client = Client(HTTP_HOST=host)
        client.login(username="hs_analyst", password="pass12345")
        before = dict(self._stage().settings)
        response = client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self._draft().edit_revision,
                             "mutation": {"type": "section.update_settings", "section_id": self._stage().pk, "patch": {"title": "هک"}}}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(self._stage().settings, before)
        anonymous = Client(HTTP_HOST=host).post(reverse("dashboard:storefront-builder-r4-mutation"), data="{}", content_type="application/json")
        self.assertIn(anonymous.status_code, (302, 401, 403))

    def test_a_stale_revision_is_a_conflict_not_an_overwrite(self):
        self._apply("dual_atelier")
        revision = self._draft().edit_revision
        self._mutate({"title": "اول"})
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": revision, "mutation": {"type": "section.update_settings", "section_id": self._stage().pk,
                                                                     "patch": {"title": "دوم"}}}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._stage().settings["title"], "اول")

    # ------------------------------------------------------------------------------------------------------------ compatibility
    def test_existing_templates_render_exactly_as_before(self):
        for key in ("decor_sand_boutique", "coastal_product", "premium_leather"):
            with self.subTest(template=key):
                self._apply(key)
                self._publish()
                body = self._live()
                self.assertNotIn("hs-stage", body)
                self.assertNotIn("hs-header", body)
                self.assertEqual(body.count("<header"), 1)

    def test_legacy_header_config_without_a_stage_is_untouched_by_an_independent_stage(self):
        self._apply("dual_atelier")
        self._mutate({"header_mode": "independent"})
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("<header", _stage_html(body))

    def test_responsive_hide_flags_are_real_css_rules_not_just_attributes(self):
        self._apply("editorial_noir")
        self._mutate({"slots": [{"key": "title"}, {"key": "subtitle", "hide_mobile": True, "hide_tablet": True}, {"key": "cta"}]})
        self._publish()
        stage = _stage_html(self._live())
        self.assertRegex(stage, r'hs-subtitle"[^>]*data-hs-hide-t[^>]*data-hs-hide-m|hs-subtitle"[^>]*data-hs-hide-m')
        css = (APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\(max-width:680px\)\{[^@]*\.hs-stage \[data-hs-hide-m\]\{display:none!important\}")
        self.assertRegex(css, r"@media\(min-width:681px\) and \(max-width:1000px\)\{[^@]*\.hs-stage \[data-hs-hide-t\]\{display:none!important\}")

    # ------------------------------------------------------------------------------------------------------------ editor / gallery
    def test_the_studio_inspector_exposes_the_controls_of_the_stage(self):
        self._apply("glass_commerce")
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self._stage().pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for key in ("header_mode", "bg_layout", "scrim_strength", "content_valign", "title_size", "button_label", "slots", "text_tone"):
            self.assertIn(f'data-r4-field-key="{key}"', body, key)

    def test_gallery_live_preview_draws_the_header_once_inside_the_stage(self):
        for key in TEMPLATES:
            with self.subTest(template=key):
                self._draft()                                          # merchant-data mode needs an existing Draft (never creates one)
                response = self.client.get(reverse("dashboard:storefront-builder-template-live-preview", args=[key]) + "?data=merchant")
                self.assertEqual(response.status_code, 200, key)
                body = response.content.decode()
                stage = _stage_html(body)
                self.assertTrue(stage, key)
                self.assertEqual(body.count("<header"), 1, key)
                self.assertIn("<header", stage, key)

    def test_the_draft_preview_customer_view_embeds_the_header_too(self):
        self._apply("glass_commerce")
        body = self.client.get(reverse("dashboard:storefront-builder-draft-preview")).content.decode()
        self.assertEqual(body.count("<header"), 1)
        self.assertIn("<header", _stage_html(body))
