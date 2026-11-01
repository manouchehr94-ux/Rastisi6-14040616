"""Header placement + Header Recipes: a professional header (model + where it is drawn) is selectable independently of the template.

* the four Hero-Stage templates' headers are read off the registry as recipes (no template name in any renderer);
* ``header.set_placement`` only changes the first Hero Stage's ``header_mode`` — model, hero pictures/texts, footer, other sections are untouched,
  exactly one header is drawn, one Undo/Redo step;
* on a template without a Hero Stage the placement is refused honestly (no half-rendered / duplicate header) and a recipe applies its MODEL only;
* a stage hidden on a device never embeds the header (the cart must stay reachable); another Store is never touched. Throw-away database only."""

import json
import re

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.storefront_builder import header_placement, hero_stage
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase

STAGE = {"dual_atelier": ("atelier_nav", "merged"), "editorial_noir": ("editorial_masthead", "merged"),
         "glass_commerce": ("centered_brand", "merged"), "asymmetric_canvas": ("floating_compact", "overlay")}
NO_STAGE = "street_drop"


@override_settings(ALLOWED_HOSTS=["*"])
class HeaderPlacementTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def _draft(self):
        return svc.get_or_create_draft(self.store, user=self.staff)

    def _apply_whole(self, key):
        response = self.client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": key, "confirm_preset_apply": "1"})
        self.assertEqual(response.status_code, 302, key)

    def _post(self, mutation):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "mutation": mutation}), content_type="application/json",
        )

    def _mutate(self, mutation, *, expect=200):
        response = self._post(mutation)
        self.assertEqual(response.status_code, expect, response.content[:300])
        return response

    def _history(self, command):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "command": command}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])

    def _stage(self):
        return self._draft().get_page("home").sections.get(section_key=hero_stage.SECTION_KEY)

    def _sections(self):
        return [(s.section_key, s.pk) for s in self._draft().get_page("home").sections.order_by("order", "id")]

    def _headers_in_preview(self):
        html = self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()
        return len(re.findall(r"<header\b", html)), html

    @staticmethod
    def _stage_header(html):
        """Is the header drawn INSIDE the stage? (the element, not the stylesheet that mentions the class)"""
        return bool(re.search(r'class="[^"]*\bhs-header\b', html))

    # recipes -----------------------------------------------------------------------------------------------------------------
    def test_the_four_stage_templates_are_the_recipes_read_from_the_registry(self):
        recipes = {r["key"]: (r["variant"], r["placement"]) for r in header_placement.list_recipes()}
        self.assertEqual(recipes, STAGE)
        for recipe in header_placement.list_recipes():
            self.assertTrue(recipe["label"])
            self.assertNotIn("(", recipe["label"])

    def test_every_recipe_variant_is_a_registered_header_model(self):
        from apps.storefront_builder import global_region_registry as regions

        keys = {v.key for v in regions.list_global_variants(regions.GLOBAL_HEADER_REGION)}
        for recipe in header_placement.list_recipes():
            self.assertIn(recipe["variant"], keys)

    # placement -------------------------------------------------------------------------------------------------------------
    def test_placement_moves_only_the_header_and_is_one_undoable_step(self):
        for key, (variant, mode) in STAGE.items():
            with self.subTest(template=key):
                self._apply_whole(key)
                self.assertEqual(header_placement.describe(self._draft())["mode"], mode)
                sections, stage = self._sections(), dict(self._stage().settings)
                footer, variant_before = self._draft().effective_footer_config(), self._draft().effective_header_config()["header_variant"]
                revision = self._draft().edit_revision
                self._mutate({"type": "header.set_placement", "placement": "independent"})
                self.assertEqual(self._draft().edit_revision, revision + 1)                      # ONE history step
                self.assertEqual(header_placement.describe(self._draft())["mode"], "independent")
                count, html = self._headers_in_preview()
                self.assertEqual(count, 1, "exactly one header is drawn")
                self.assertFalse(self._stage_header(html))
                now = dict(self._stage().settings)
                self.assertEqual({k: v for k, v in now.items() if k != "header_mode"}, {k: v for k, v in stage.items() if k != "header_mode"})
                self.assertEqual(self._sections(), sections)
                self.assertEqual(self._draft().effective_footer_config(), footer)
                self.assertEqual(self._draft().effective_header_config()["header_variant"], variant_before)
                self._mutate({"type": "header.set_placement", "placement": "overlay" if mode == "merged" else "merged"})
                count, html = self._headers_in_preview()
                self.assertEqual(count, 1)
                self.assertTrue(self._stage_header(html))
                self._history("undo")
                self._history("undo")
                self.assertEqual(self._stage().settings.get("header_mode"), stage.get("header_mode"))
                self.assertEqual(header_placement.describe(self._draft())["mode"], mode)

    def test_without_a_hero_stage_the_placement_is_refused_and_nothing_changes(self):
        self._apply_whole(NO_STAGE)
        state = header_placement.describe(self._draft())
        self.assertFalse(state["available"])
        self.assertEqual(state["reason"], "no_stage")
        before, sections = self._draft().edit_revision, self._sections()
        for mode in ("merged", "overlay"):
            response = self._mutate({"type": "header.set_placement", "placement": mode}, expect=400)
            self.assertEqual(response.json()["code"], "header_placement_needs_stage")
        self._mutate({"type": "header.set_placement", "placement": "independent"})                # already independent: accepted, a no-op
        self.assertEqual(self._sections(), sections)
        self.assertEqual(self._headers_in_preview()[0], 1)
        self.assertEqual(self._mutate({"type": "header.set_placement", "placement": "sideways"}, expect=400).json()["code"], "invalid_placement")
        self.assertGreaterEqual(self._draft().edit_revision, before)

    def test_a_stage_hidden_on_some_device_never_embeds_the_header(self):
        self._apply_whole("dual_atelier")
        self._mutate({"type": "header.set_placement", "placement": "independent"})
        stage = self._stage()
        stage.settings = {**stage.settings, "responsive": {"hide_on_mobile": True}}
        stage.save(update_fields=["settings"])
        state = header_placement.describe(self._draft())
        self.assertFalse(state["available"])
        self.assertEqual(state["reason"], "stage_hidden")
        self.assertEqual(self._mutate({"type": "header.set_placement", "placement": "merged"}, expect=400).json()["code"], "header_placement_stage_hidden")
        self.assertEqual(self._headers_in_preview()[0], 1)

    # recipes applied -------------------------------------------------------------------------------------------------------
    def test_a_recipe_on_a_template_without_a_stage_applies_the_model_only(self):
        self._apply_whole(NO_STAGE)
        sections, footer = self._sections(), self._draft().effective_footer_config()
        hero_like = [s for s in self._sections() if s[0] == hero_stage.SECTION_KEY]
        self.assertEqual(hero_like, [])
        for key, (variant, _mode) in STAGE.items():
            with self.subTest(recipe=key):
                self._mutate({"type": "header.apply_recipe", "recipe_key": key})
                self.assertEqual(self._draft().effective_header_config()["header_variant"], variant)
                self.assertEqual(self._sections(), sections, "no hero is added, replaced or removed")
                self.assertEqual(self._draft().effective_footer_config(), footer)
                count, html = self._headers_in_preview()
                self.assertEqual(count, 1)
                self.assertFalse(self._stage_header(html))

    def test_a_recipe_on_a_stage_template_applies_model_and_placement(self):
        self._apply_whole("dual_atelier")
        self._mutate({"type": "header.apply_recipe", "recipe_key": "asymmetric_canvas"})
        self.assertEqual(self._draft().effective_header_config()["header_variant"], "floating_compact")
        self.assertEqual(self._stage().settings.get("header_mode"), "overlay")
        self.assertEqual(header_placement.describe(self._draft())["mode"], "overlay")
        self.assertEqual(self._headers_in_preview()[0], 1)
        self._mutate({"type": "header.apply_recipe", "recipe_key": "dual_atelier"})
        self.assertEqual(self._stage().settings.get("header_mode"), "merged")
        self.assertEqual(self._draft().effective_header_config()["header_variant"], "atelier_nav")

    def test_unknown_recipe_is_refused(self):
        self._apply_whole("dual_atelier")
        self.assertEqual(self._mutate({"type": "header.apply_recipe", "recipe_key": "nope"}, expect=400).json()["code"], "unknown_header_recipe")
        self.assertEqual(self._mutate({"type": "header.apply_recipe", "recipe_key": NO_STAGE}, expect=400).json()["code"], "unknown_header_recipe")

    # isolation ---------------------------------------------------------------------------------------------------------------
    def test_another_stores_draft_is_never_touched(self):
        self._apply_whole("dual_atelier")
        other = Store.objects.create(name="فروشگاه دیگر", slug="hp-other", admin_subdomain="hp-other", status=Store.Status.ACTIVE)
        other_draft = svc.get_or_create_draft(other)
        before = (other_draft.header_config, other_draft.edit_revision, list(other_draft.get_page("home").sections.values_list("pk", "settings")))
        self._mutate({"type": "header.apply_recipe", "recipe_key": "editorial_noir"})
        self._mutate({"type": "header.set_placement", "placement": "independent"})
        other_draft.refresh_from_db()
        after = (other_draft.header_config, other_draft.edit_revision, list(other_draft.get_page("home").sections.values_list("pk", "settings")))
        self.assertEqual(before, after)
        # the mutation carries no section/draft id the caller could aim at another Store
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout__store=other).count(), 1)
