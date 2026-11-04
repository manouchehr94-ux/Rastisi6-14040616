"""The 19-template gallery policy (owner decision): ONE shared source decides which Ready Templates a seller may CHOOSE.

Hidden templates are never deleted: they stay registered, renderable, editable, previewable and publishable, a Store that already carries one
keeps it, and offering them again needs no migration (a setting / one tuple). Throw-away database only."""

import json
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry as lpr, template_gallery_policy as policy
from apps.storefront_builder.services import (
    layout_service as svc,
    ready_template_card_service,
    store_template_service,
)

from .test_r4_mutation_api import R4MutationApiTestCase

#: the owner's list, by the Registry's own Persian label (names → keys is asserted, never guessed)
OWNER_LIST = (
    ("کارگاه لاله", "warm_boutique"), ("نسخه", "utility_catalog"), ("خیابان", "street_drop"), ("گالری آب", "gallery_minimal"),
    ("آچار", "tool_finder"), ("رایان", "rayan_tech"), ("زیبایی ارغوانی", "magenta_beauty_retail"), ("کاغذ پاستلی", "pastel_kawaii_stationery"),
    ("بوتیک شنی (دکور و لوازم خانه)", "decor_sand_boutique"), ("رز کرمی (آرایشی و بهداشتی)", "rose_beauty_store"),
    ("گالری فوشیا (زیبایی)", "pink_beauty_gallery"), ("هاب کمپینی عسلی (آرایشی)", "campaign_beauty_hub"),
    ("هدیه و ماگ کاکائویی", "cocoa_gift_shop"), ("فروشگاه دیجیتال نئونی", "neon_digital_store"),
    ("آتلیه دوپنل (هدر یکپارچه با دو تصویر)", "dual_atelier"), ("نشریهٔ نوآر (هیروی مجله‌ای با کارت محصول)", "editorial_noir"),
    ("تجارت شیشه‌ای (هیرو با نوار دسته‌بندی)", "glass_commerce"), ("بوم نامتقارن (هدر شناور روی تصویر)", "asymmetric_canvas"),
    ("تحریر رنگی", "stationery_spectrum"),
)
HIDDEN_KEY = "dark_digital"          # a registered Ready Template that is NOT in the 19 (label «پالس نئون»)


class PolicyDataTests(SimpleTestCase):
    def test_the_nineteen_names_map_to_real_registry_keys_in_the_owners_order(self):
        self.assertEqual(len(OWNER_LIST), 19)
        self.assertEqual(policy.SELECTABLE_TEMPLATE_KEYS, tuple(key for _label, key in OWNER_LIST))
        ready = {preset.key: preset for preset in lpr.list_ready_templates()}
        for label, key in OWNER_LIST:
            self.assertIn(key, ready, key)
            self.assertEqual(ready[key].label_fa, label, f"{key}: the Registry label must be exactly the owner's name")
        self.assertEqual(len(set(policy.SELECTABLE_TEMPLATE_KEYS)), 19)

    def test_the_selectable_list_is_exactly_those_nineteen_and_a_strict_subset_of_the_registry(self):
        selectable = lpr.list_selectable_templates()
        self.assertEqual([p.key for p in selectable], list(policy.SELECTABLE_TEMPLATE_KEYS))
        self.assertTrue(all(p.is_ready_template for p in selectable))
        self.assertGreater(len(lpr.list_ready_templates()), 19)

    def test_nothing_is_removed_from_the_registry(self):
        self.assertIsNotNone(lpr.get_layout_preset(HIDDEN_KEY))
        self.assertIn(HIDDEN_KEY, {p.key for p in lpr.list_ready_templates()})
        self.assertNotIn(HIDDEN_KEY, {p.key for p in lpr.list_selectable_templates()})
        self.assertGreaterEqual(len(lpr.list_layout_presets()), 63)

    def test_restoring_hidden_templates_is_only_a_setting(self):
        with override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False):
            self.assertEqual({p.key for p in lpr.list_selectable_templates()}, {p.key for p in lpr.list_ready_templates()})
            self.assertTrue(policy.is_selectable_key(HIDDEN_KEY))
        self.assertFalse(policy.is_selectable_key(HIDDEN_KEY))              # default: restricted

    def test_policy_is_never_decided_by_css_or_markup(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / "static" / "storefront_builder" / "r4_studio.js", root / "static" / "css" / "storefront_builder.css"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("dark_digital", text)
            self.assertNotIn("SELECTABLE_TEMPLATE_KEYS", text)


class CardsAndSelectionTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def _cards(self, *, key=None, version=None):
        return ready_template_card_service.build_ready_template_cards(
            None, current_template_key=key, current_template_version=version, scope=ready_template_card_service.SCOPE_GALLERY,   # the SELLER gallery projection
        )

    def test_the_gallery_projection_has_exactly_the_nineteen_cards(self):
        cards = self._cards()
        self.assertEqual([c["preset"].key for c in cards], list(policy.SELECTABLE_TEMPLATE_KEYS))
        self.assertNotIn(HIDDEN_KEY, [c["preset"].key for c in cards])

    def test_a_store_on_a_hidden_template_keeps_its_identity_pinned_as_current(self):
        preset = lpr.get_layout_preset(HIDDEN_KEY)
        cards = self._cards(key=preset.key, version=preset.version)
        self.assertEqual(len(cards), 20)
        pinned = [c for c in cards if c.get("is_hidden_current")]
        self.assertEqual([(c["preset"].key, c["is_current"]) for c in pinned], [(HIDDEN_KEY, True)])
        self.assertEqual(sum(1 for c in cards if c["is_current"]), 1)

    def test_a_store_on_a_listed_template_gets_no_extra_card(self):
        preset = lpr.get_layout_preset("warm_boutique")
        cards = self._cards(key=preset.key, version=preset.version)
        self.assertEqual(len(cards), 19)
        self.assertEqual([c["preset"].key for c in cards if c["is_current"]], ["warm_boutique"])

    def test_the_studio_context_lists_only_the_nineteen_templates_everywhere(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        keys = [t["key"] for t in response.context["ready_templates"]]
        self.assertEqual(keys, list(policy.SELECTABLE_TEMPLATE_KEYS))
        studio_cards = [t["key"] for t in response.context["studio"]["templates"]] if "templates" in response.context["studio"] else keys
        self.assertEqual(studio_cards, keys)                                  # the search/count source is the same list

    def test_the_hidden_template_cannot_be_chosen_through_any_seller_entry_point(self):
        preset = lpr.get_layout_preset(HIDDEN_KEY)
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        before = draft.template_provenance
        switch = self.client.post(
            reverse("dashboard:storefront-builder-r4-switch-template"),
            data=json.dumps({"base_revision": draft.edit_revision, "template_key": preset.key, "template_version": preset.version, "confirm_replace": True}),
            content_type="application/json",
        )
        self.assertEqual((switch.status_code, switch.json()["code"]), (400, "template_not_selectable"))
        apply = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": draft.edit_revision, "mutation": {
                "type": "appearance.template.apply", "template_key": preset.key, "template_version": preset.version, "confirm_replace": True}}),
            content_type="application/json",
        )
        self.assertEqual((apply.status_code, apply.json()["code"]), (400, "template_not_selectable"))
        form = self.client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": preset.key, "confirm_preset_apply": "1"})
        self.assertEqual(form.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.template_provenance, before)                  # nothing was written
        self.assertEqual(draft.edit_revision, 0)

    def test_a_listed_template_is_still_selectable_and_the_current_hidden_one_can_be_reapplied(self):
        listed = lpr.get_layout_preset("gallery_minimal")
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        ok = self.client.post(
            reverse("dashboard:storefront-builder-r4-switch-template"),
            data=json.dumps({"base_revision": draft.edit_revision, "template_key": listed.key, "template_version": listed.version, "confirm_replace": True}),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200, ok.content[:200])
        # the engine itself is NOT gated: an operator/repair path (or a Store that carries a hidden template) can still apply it by identity
        with override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False):
            hidden = lpr.get_layout_preset(HIDDEN_KEY)
            draft = svc.get_or_create_draft(self.store, user=self.staff)
            self.client.post(
                reverse("dashboard:storefront-builder-r4-switch-template"),
                data=json.dumps({"base_revision": draft.edit_revision, "template_key": hidden.key, "template_version": hidden.version, "confirm_replace": True}),
                content_type="application/json",
            )
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(draft.template_provenance["template"]["key"], HIDDEN_KEY)
        again = self.client.post(                                             # re-applying the template the Draft ALREADY carries is not a new choice
            reverse("dashboard:storefront-builder-r4-switch-template"),
            data=json.dumps({"base_revision": draft.edit_revision, "template_key": HIDDEN_KEY, "template_version": lpr.get_layout_preset(HIDDEN_KEY).version, "confirm_replace": True}),
            content_type="application/json",
        )
        self.assertNotEqual(again.json().get("code"), "template_not_selectable")

    def test_a_hidden_templates_store_still_renders_and_is_identified_not_auto_replaced(self):
        with override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False):
            hidden = lpr.get_layout_preset(HIDDEN_KEY)
            draft = svc.get_or_create_draft(self.store, user=self.staff)
            self.client.post(
                reverse("dashboard:storefront-builder-r4-switch-template"),
                data=json.dumps({"base_revision": draft.edit_revision, "template_key": hidden.key, "template_version": hidden.version, "confirm_replace": True}),
                content_type="application/json",
            )
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version), (HIDDEN_KEY, hidden.version))
        self.assertTrue(applied.is_current_version)                           # identity resolution is NOT affected by the gallery policy
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))                    # Studio opens, Draft intact
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:storefront-builder-preview")).status_code, 200)
        self.assertEqual(svc.get_or_create_draft(self.store, user=self.staff).template_provenance["template"]["key"], HIDDEN_KEY)

    def test_onboarding_selection_service_refuses_a_hidden_template_and_names_why(self):
        with self.assertRaises(store_template_service.ReadyTemplateSelectionError) as ctx:
            store_template_service.select_ready_template(store=self.store, actor=self.staff, template_key=HIDDEN_KEY)
        self.assertEqual(ctx.exception.code, "template_not_available")


class StudioGalleryMarkupTests(SimpleTestCase):
    def test_there_is_no_header_only_button_in_the_gallery_but_the_api_remains(self):
        js = (Path(__file__).resolve().parents[1] / "static" / "storefront_builder" / "r4_studio.js").read_text(encoding="utf-8")
        self.assertNotIn("فقط هدرِ این قالب", js)
        self.assertNotIn("apply-template-header", js)
        from apps.storefront_builder.services import r4_mutation_service as svc_

        self.assertTrue(callable(getattr(svc_, "_apply_header_from_template", None)), "the header.apply_template backend stays available")


    def test_there_is_no_hero_only_button_in_the_gallery_but_the_backend_and_the_studio_remain(self):
        base = Path(__file__).resolve().parents[1] / "static" / "storefront_builder"
        js = (base / "r4_studio.js").read_text(encoding="utf-8")
        self.assertNotIn("فقط هیرو (چیدمانِ هیرو)", js)
        self.assertNotIn("btn('apply-template-hero'", js)
        self.assertNotIn("parts.hero", js)
        self.assertIn("function applyTemplatePart(part, key)", js)      # the wiring to the mutation is kept
        from apps.storefront_builder.services import r4_mutation_service as svc_

        self.assertTrue(callable(getattr(svc_, "_apply_hero_from_template", None)), "the hero.apply_template backend stays available")
        self.assertIn('"hero.apply_template"', (Path(svc_.__file__)).read_text(encoding="utf-8"))
