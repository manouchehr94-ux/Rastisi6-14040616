"""RastiSi Design Studio — Ready Template "current" identity is version-exact.

``list_ready_templates()`` returns the latest merchant-facing version per key;
historical exact versions stay available through
``get_layout_preset_version(key, version)``. A Draft whose provenance is an
older exact version of the same key must therefore:

* never mark the newer catalog card as current (it stays applicable);
* still be presented as that exact historical template (never "no template").

Uses the real registry pair ``fashion_promo_catalog`` v7 (historical) / v8
(latest) — no fabricated registry.
"""

import json

from django.urls import reverse

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.services import layout_service, preset_service
from apps.storefront_builder.views import (
    build_ready_template_cards,
    resolve_applied_template_card,
)

from .test_views import StorefrontBuilderViewsTestCase

KEY = "fashion_promo_catalog"
HISTORICAL = "7"
LATEST = "8"


class _TemplateIdentityCase(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.latest = layout_preset_registry.get_layout_preset(KEY)
        self.historical = layout_preset_registry.get_layout_preset_version(KEY, HISTORICAL)

    def _apply(self, preset):
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()

    def _provenance(self):
        self.draft.refresh_from_db()
        template = self.draft.template_provenance["template"]
        return template["key"], template["version"]

    def _cards(self):
        key, version = self._provenance()
        return {
            card["preset"].key: card
            for card in build_ready_template_cards(
                self.draft, current_template_key=key, current_template_version=version,
            )
        }

    def _studio(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        return response, response.context["studio"]


class RegistryFixtureSanityTests(_TemplateIdentityCase):
    def test_real_historical_and_latest_versions_exist(self):
        self.assertIsNotNone(self.historical)
        self.assertEqual(self.latest.version, LATEST)
        self.assertNotEqual(self.historical.label_fa, "")
        catalog = {p.key: p.version for p in layout_preset_registry.list_ready_templates()}
        self.assertEqual(catalog[KEY], LATEST)


class ExactVersionCurrentTests(_TemplateIdentityCase):
    def test_same_key_same_version_is_current(self):
        self._apply(self.latest)
        self.assertEqual(self._provenance(), (KEY, LATEST))
        cards = self._cards()
        self.assertTrue(cards[KEY]["is_current"])
        self.assertEqual(sum(1 for card in cards.values() if card["is_current"]), 1)

    def test_same_key_different_version_is_not_current(self):
        self._apply(self.historical)
        self.assertEqual(self._provenance(), (KEY, HISTORICAL))
        cards = self._cards()
        self.assertFalse(cards[KEY]["is_current"])
        self.assertFalse(any(card["is_current"] for card in cards.values()))

    def test_key_without_exact_version_never_marks_latest_current(self):
        cards = build_ready_template_cards(
            self.draft, current_template_key=KEY, current_template_version=None,
        )
        self.assertFalse(any(card["is_current"] for card in cards))
        self.assertIsNone(
            resolve_applied_template_card(
                self.draft, cards, current_template_key=KEY, current_template_version=None,
            )
        )

    def test_unresolvable_exact_version_is_not_guessed(self):
        cards = build_ready_template_cards(
            self.draft, current_template_key=KEY, current_template_version="999",
        )
        self.assertIsNone(
            resolve_applied_template_card(
                self.draft, cards, current_template_key=KEY, current_template_version="999",
            )
        )


class StudioHistoricalTemplateTests(_TemplateIdentityCase):
    def setUp(self):
        super().setUp()
        self._apply(self.historical)

    def test_studio_reports_exact_historical_template_not_no_template(self):
        response, studio = self._studio()
        self.assertIsNotNone(studio["current_template"])
        self.assertEqual(studio["current_template"]["preset"].key, KEY)
        self.assertEqual(studio["current_template"]["preset"].version, HISTORICAL)
        self.assertTrue(studio["current_template_is_historical"])
        self.assertFalse(studio["current_template_unresolved"])
        html = response.content.decode()
        self.assertIn(self.historical.label_fa, html)
        self.assertNotIn("بدون قالب آماده", html)
        self.assertIn("data-rs-historical-template", html)
        self.assertEqual(
            studio["client"]["current_template_label"],
            f"{self.historical.label_fa} · نسخهٔ {HISTORICAL}",
        )

    def test_latest_card_is_not_current_and_is_offered_with_its_exact_version(self):
        _, studio = self._studio()
        by_key = {t["key"]: t for t in studio["client"]["templates"]}
        self.assertFalse(by_key[KEY]["is_current"])
        self.assertEqual(by_key[KEY]["version"], LATEST)
        self.assertFalse(any(t["is_current"] for t in studio["client"]["templates"]))

    def test_latest_version_is_applicable_through_existing_switch_contract(self):
        _, studio = self._studio()
        offered = next(t for t in studio["client"]["templates"] if t["key"] == KEY)
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-switch-template"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "template_key": offered["key"],
                "template_version": offered["version"],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["ok"], True)
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(draft.template_provenance["template"]["key"], KEY)
        self.assertEqual(draft.template_provenance["template"]["version"], LATEST)

    def test_viewing_the_studio_never_repairs_the_draft(self):
        before = (self.draft.edit_revision, dict(self.draft.template_provenance))
        self._studio()
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.edit_revision, dict(self.draft.template_provenance)), before)


class GalleryAndStudioShareSemanticsTests(_TemplateIdentityCase):
    def _gallery_current(self):
        response = self.client.get(reverse("dashboard:storefront-builder-templates"))
        self.assertEqual(response.status_code, 200)
        return {c["preset"].key: c["is_current"] for c in response.context["template_cards"]}

    def _studio_current(self):
        _, studio = self._studio()
        return {t["key"]: t["is_current"] for t in studio["client"]["templates"]}

    def test_both_surfaces_agree_on_a_historical_draft(self):
        self._apply(self.historical)
        gallery, studio = self._gallery_current(), self._studio_current()
        self.assertEqual(gallery, studio)
        self.assertFalse(gallery[KEY])

    def test_both_surfaces_agree_on_a_latest_draft(self):
        self._apply(self.latest)
        gallery, studio = self._gallery_current(), self._studio_current()
        self.assertEqual(gallery, studio)
        self.assertTrue(gallery[KEY])

    def test_historical_gallery_card_keeps_its_apply_action(self):
        self._apply(self.historical)
        response = self.client.get(reverse("dashboard:storefront-builder-templates"))
        html = response.content.decode()
        self.assertNotIn("قالبِ فعلی", html)
        self.assertIn(f'value="{KEY}"', html)
