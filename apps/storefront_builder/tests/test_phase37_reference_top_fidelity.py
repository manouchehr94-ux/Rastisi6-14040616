from pathlib import Path

from django.conf import settings as django_settings

from apps.storefront_builder import layout_preset_registry, section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase37HeroMerchantControlTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.page.containers.all().delete()

    def test_slider_default_preserves_historical_side(self):
        self.assertEqual(section_registry.default_slider_settings()["text_position"], "end")


class Phase37ReferenceTopPresetTests(StorefrontBuilderViewsTestCase):
    def test_reference_preset_uses_right_copy_and_seven_categories(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        hero = preset.pages["home"][1]
        category = preset.pages["home"][2]
        self.assertEqual(hero.settings["text_position"], "start")
        self.assertEqual(category.settings["display_mode"], "image_strip")
        self.assertEqual(category.settings["item_limit"], 7)


class Phase37GenericCssContractTests(StorefrontBuilderViewsTestCase):
    def test_top_fidelity_css_is_generic(self):
        root = Path(django_settings.BASE_DIR)
        # the engine stylesheet pair (shared rules live once, in storefront_builder.css)
        css = (root / "apps/catalog/static/css/home.css").read_text(encoding="utf-8") + (
            root / "apps/storefront_builder/static/css/storefront_builder.css"
        ).read_text(encoding="utf-8")
        self.assertIn('.hero-inner[data-text-position="start"]', css)
        self.assertIn(".product-section--spotlight", css)
        self.assertIn("repeat(auto-fit,minmax(112px,1fr))", css)
        self.assertNotIn("v5_golden_homepage", css)
        self.assertNotIn("golden-hero-row", css)
