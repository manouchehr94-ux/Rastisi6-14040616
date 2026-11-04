"""Header and footer are changed on their OWN from the Studio (click them on the canvas → the Global Design panel's variant picker), never by
re-applying a whole template. Verified on the Hero-Stage templates where the header lives INSIDE the stage: one header only (no duplicate),
the hero / pictures / texts / menus / footer untouched, one Undo/Redo step, Draft-only until Publish, Store-scoped. Throw-away database only."""

import json
import re

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import MediaAsset
from apps.storefront_builder import global_region_registry as regions, hero_stage
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

from .test_hero_stage_templates import PUBLIC_A, _png
from .test_r4_mutation_api import R4MutationApiTestCase

STAGE_TEMPLATES = ("dual_atelier", "editorial_noir", "glass_commerce", "asymmetric_canvas")


def _other_variant(region, current):
    return next(v.key for v in regions.list_global_variants(region) if v.key != current)


@override_settings(ALLOWED_HOSTS=["*"])
class HeaderFooterIndependenceTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=PUBLIC_A)
        MediaAsset.objects.create(store=self.store, image=_png("hf-a.png", (90, 120, 200)))
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="hf-other", admin_subdomain="hf-other", status=Store.Status.ACTIVE)

    # helpers ------------------------------------------------------------------------------------------------------------------
    def _draft(self):
        return svc.get_or_create_draft(self.store, user=self.staff)

    def _apply_whole(self, key):
        response = self.client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": key, "confirm_preset_apply": "1"})
        self.assertEqual(response.status_code, 302, key)

    def _mutate(self, mutation, *, expect=200):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "mutation": mutation}), content_type="application/json",
        )
        self.assertEqual(response.status_code, expect, response.content[:300])
        return response

    def _history(self, command):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "command": command}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])

    def _publish(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps({"base_revision": self._draft().edit_revision}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        cache.clear()

    def _sections(self):
        return [(s.section_key, s.pk) for s in self._draft().get_page("home").sections.order_by("order", "id")]

    def _stage(self):
        return self._draft().get_page("home").sections.get(section_key=hero_stage.SECTION_KEY)

    def _header_variant(self):
        return self._draft().effective_header_config()["header_variant"]

    def _footer_variant(self):
        return self._draft().effective_footer_config()["footer_variant"]

    def _preview_headers(self):
        html = self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()
        return len(re.findall(r"<header\b", html)), html

    # header ------------------------------------------------------------------------------------------------------------------
    def test_changing_only_the_header_keeps_everything_else_on_every_unified_header_template(self):
        for key in STAGE_TEMPLATES:
            with self.subTest(template=key):
                self._apply_whole(key)
                sections, stage = self._sections(), dict(self._stage().settings)
                footer, provenance = self._draft().effective_footer_config(), self._draft().template_provenance
                before_headers, _ = self._preview_headers()
                self.assertGreaterEqual(before_headers, 1, "the preview really renders a header")
                current = self._header_variant()
                revision = self._draft().edit_revision

                target = _other_variant(regions.GLOBAL_HEADER_REGION, current)
                self._mutate({"type": "header.update", "patch": {"header_variant": target}})

                self.assertEqual(self._header_variant(), target)
                self.assertEqual(self._sections(), sections, "no section added, removed or re-created")
                self.assertEqual(self._stage().settings, stage, "hero, pictures, texts, header mode and slots are untouched")
                self.assertEqual(self._draft().effective_footer_config(), footer)
                self.assertEqual(self._draft().template_provenance, provenance, "the template identity is not replaced")
                self.assertEqual(self._draft().edit_revision, revision + 1, "exactly one revision")
                after_headers, _ = self._preview_headers()
                self.assertEqual(after_headers, before_headers, "never a second header")

                self._history("undo")
                self.assertEqual(self._header_variant(), current)
                self._history("redo")
                self.assertEqual(self._header_variant(), target)

    def test_the_header_change_is_draft_only_until_publish(self):
        self._apply_whole("dual_atelier")
        self._publish()
        published_before = StorefrontLayoutVersion.objects.get(layout__store=self.store, status="published")
        variant_before = published_before.effective_header_config()["header_variant"]
        target = _other_variant(regions.GLOBAL_HEADER_REGION, variant_before)

        self._mutate({"type": "header.update", "patch": {"header_variant": target}})
        published_now = StorefrontLayoutVersion.objects.get(layout__store=self.store, status="published")
        self.assertEqual(published_now.pk, published_before.pk)
        self.assertEqual(published_now.effective_header_config()["header_variant"], variant_before, "Publish has not been pressed")

        self._publish()
        published_after = StorefrontLayoutVersion.objects.get(layout__store=self.store, status="published")
        self.assertEqual(published_after.effective_header_config()["header_variant"], target)

    def test_menus_logo_and_contact_data_are_never_part_of_a_header_variant_change(self):
        self._apply_whole("glass_commerce")
        config_before = dict(self._draft().effective_header_config())
        self._mutate({"type": "header.update", "patch": {"header_variant": _other_variant(regions.GLOBAL_HEADER_REGION, config_before["header_variant"])}})
        config_after = self._draft().effective_header_config()
        changed = {key for key in config_after if config_after[key] != config_before.get(key)}
        self.assertEqual(changed, {"header_variant"}, "only the variant moved; toggles / announcement / blocks / geometry are untouched")

    def test_an_unknown_header_variant_is_refused_and_nothing_is_written(self):
        self._apply_whole("dual_atelier")
        revision, variant = self._draft().edit_revision, self._header_variant()
        response = self._mutate({"type": "header.update", "patch": {"header_variant": "no_such_variant"}}, expect=400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual((self._draft().edit_revision, self._header_variant()), (revision, variant))

    # footer ------------------------------------------------------------------------------------------------------------------
    def test_changing_only_the_footer_keeps_header_hero_and_sections(self):
        for key in STAGE_TEMPLATES:
            with self.subTest(template=key):
                self._apply_whole(key)
                sections, stage = self._sections(), dict(self._stage().settings)
                header = dict(self._draft().effective_header_config())
                current = self._footer_variant()
                target = _other_variant(regions.GLOBAL_FOOTER_REGION, current)
                revision = self._draft().edit_revision

                self._mutate({"type": "footer.update", "patch": {"footer_variant": target}})

                self.assertEqual(self._footer_variant(), target)
                self.assertEqual(self._sections(), sections)
                self.assertEqual(self._stage().settings, stage)
                self.assertEqual(self._draft().effective_header_config(), header)
                self.assertEqual(self._draft().edit_revision, revision + 1)
                self._history("undo")
                self.assertEqual(self._footer_variant(), current)
                self._history("redo")
                self.assertEqual(self._footer_variant(), target)

    def test_the_footer_variant_picker_lists_real_registered_variants_only(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        listed = [v["key"] if isinstance(v, dict) else v.key for v in response.context["global_design"]["footer_variants"]]
        self.assertEqual(listed, [v.key for v in regions.list_global_variants(regions.GLOBAL_FOOTER_REGION)])
        listed_header = [v["key"] if isinstance(v, dict) else v.key for v in response.context["global_design"]["header_variants"]]
        self.assertEqual(listed_header, [v.key for v in regions.list_global_variants(regions.GLOBAL_HEADER_REGION)])

    # tenancy -----------------------------------------------------------------------------------------------------------------
    def test_another_stores_draft_is_never_touched(self):
        svc.get_or_create_layout(self.other_store)
        other_draft = svc.get_or_create_draft(self.other_store, user=self.staff)
        snapshot = (other_draft.edit_revision, other_draft.effective_header_config(), other_draft.effective_footer_config())
        self._apply_whole("dual_atelier")
        self._mutate({"type": "header.update", "patch": {"header_variant": _other_variant(regions.GLOBAL_HEADER_REGION, self._header_variant())}})
        self._mutate({"type": "footer.update", "patch": {"footer_variant": _other_variant(regions.GLOBAL_FOOTER_REGION, self._footer_variant())}})
        other_draft.refresh_from_db()
        self.assertEqual((other_draft.edit_revision, other_draft.effective_header_config(), other_draft.effective_footer_config()), snapshot)

    def test_the_studio_wires_canvas_header_and_footer_clicks_to_the_global_design_pickers(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        preview = (root / "templates" / "storefront_builder" / "preview.html").read_text(encoding="utf-8")
        composer = (root / "static" / "storefront_builder" / "r4_composer.js").read_text(encoding="utf-8")
        studio = (root / "static" / "storefront_builder" / "r4_studio.js").read_text(encoding="utf-8")
        # a click on ANY element of the header drawn inside a Hero Stage (links included) opens the header picker instead of selecting the stage
        self.assertRegex(composer, r"t\.closest\('\.hs-header'\)\) \{\s*evt\.preventDefault\(\); evt\.stopPropagation\(\);\s*st\.sel = null; st\.menu = false;\s*S\.openGlobal\('header'\)")
        self.assertNotIn("!isInteractive(target, embeddedHeader)", preview)
        for message in ("sfb:openHeaderSettings", "sfb:openFooterSettings"):
            self.assertIn(message, preview)
            self.assertIn(message, composer)
        self.assertIn("rsGlobalHeader", studio)
        self.assertIn("rsGlobalFooter", studio)
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn('id="r4GlobalHeaderVariant"', html)
        self.assertIn('id="r4GlobalFooterVariant"', html)
