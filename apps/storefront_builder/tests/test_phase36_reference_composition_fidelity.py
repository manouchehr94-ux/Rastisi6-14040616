from pathlib import Path

from django.conf import settings as django_settings
from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import container_service, layout_service, preset_service

from ._r4_support import r4_mutate
from .test_views import StorefrontBuilderViewsTestCase


class Phase36ReferencePresetCompositionTests(TestCase):
    def test_reference_hero_declares_equal_height_container_as_data(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        offer, hero = preset.pages["home"][:2]
        self.assertEqual(offer.row_key, "golden-hero-row")
        self.assertEqual(hero.row_key, "golden-hero-row")
        self.assertEqual(
            offer.container_settings,
            {
                "gap": 8,
                "mobile_mode": "stack",
                "vertical_align": "start",
                "height_mode": "equal",
            },
        )
        self.assertIsNone(hero.container_settings)

    def test_reference_category_strip_does_not_add_unwanted_heading(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        category = preset.pages["home"][2]
        self.assertEqual(category.section_key, "category_grid")
        self.assertEqual(category.settings["title"], "")

    def test_reference_same_kind_split_rows_use_equal_height(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        first_by_row = {}
        for entry in preset.pages["home"]:
            if entry.row_key and entry.row_key not in first_by_row:
                first_by_row[entry.row_key] = entry
        for key in (
            "golden-banner-pair-a",
            "golden-banner-pair-b",
            "golden-compact-row-a",
            "golden-compact-row-b",
        ):
            self.assertEqual(first_by_row[key].container_settings["height_mode"], "equal")


class Phase36ContainerHeightModeTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()

    def test_natural_is_platform_default(self):
        self.assertEqual(
            container_service.effective_container_settings({})["height_mode"],
            "natural",
        )

    def test_container_settings_persist_equal_height(self):
        container = container_service.create_empty_container(self.page, "half")
        response = r4_mutate(self.client, self.draft, {
            "type": "container.update_settings", "container_id": container.pk,
            "patch": {"gap": 14, "mobile_mode": "stack", "vertical_align": "start", "height_mode": "equal"},
        })
        self.assertEqual(response.status_code, 200, response.content[:200])
        container.refresh_from_db()
        self.assertEqual(
            container_service.effective_container_settings(container.settings)["height_mode"],
            "equal",
        )

    def test_preview_emits_height_mode(self):
        container_service.create_empty_container(
            self.page, "half", settings={"height_mode": "equal"}
        )
        response = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-height-mode="equal"')


class Phase36PresetApplicationTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_reference_preset_persists_container_composition_settings(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        preset_service.apply_preset(self.draft, preset)

        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        containers = list(page.containers.order_by("order", "id"))
        self.assertEqual(len(containers), 17)

        hero = containers[0]
        hero_settings = container_service.effective_container_settings(hero.settings)
        self.assertEqual(hero.layout_key, "quarter_left")
        self.assertEqual([c.span for c in hero.cells.order_by("order", "id")], [3, 9])
        self.assertEqual(hero_settings["gap"], 8)
        self.assertEqual(hero_settings["height_mode"], "equal")

        compact_rows = [
            c for c in containers
            if c.layout_key == "half"
            and c.cells.filter(section__section_key="product_section").count() == 2
        ]
        self.assertEqual(len(compact_rows), 2)
        self.assertTrue(all(
            container_service.effective_container_settings(c.settings)["height_mode"] == "equal"
            for c in compact_rows
        ))


class Phase36GenericRendererContractTests(TestCase):
    def test_generic_css_and_html_hooks_never_branch_on_reference_preset(self):
        root = Path(django_settings.BASE_DIR)
        sfb_css = (root / "apps/storefront_builder/static/css/storefront_builder.css").read_text(encoding="utf-8")
        home_css = (root / "apps/catalog/static/css/home.css").read_text(encoding="utf-8")
        base_html = (root / "templates/base.html").read_text(encoding="utf-8")

        self.assertIn('.rcontainer[data-height-mode="equal"]', sfb_css)
        self.assertIn(
            '.rcontainer[data-height-mode="equal"]:has(.hero):has(.product-section--spotlight)',
            home_css,
        )
        self.assertIn("data-sfb-type-scale=", base_html)

        combined = sfb_css + home_css
        self.assertNotIn("v5_golden_homepage", combined)
        self.assertNotIn("golden-hero-row", combined)
