"""Structural diversity contracts for the 50 A8 recipes."""

import dataclasses

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.tests._catalog_count import READY_TEMPLATE_COUNT

try:
    from apps.storefront_builder.storefront_appearance.inventory import recipe_signature
except ModuleNotFoundError:  # expected during the Task 4 RED run
    recipe_signature = None


class A8TemplateDiversityTests(SimpleTestCase):
    def test_all_fifty_structural_signatures_are_pairwise_unique(self):
        self.assertIsNotNone(recipe_signature)
        signatures = [recipe_signature(preset) for preset in lpr.list_ready_templates()]

        self.assertEqual(len(signatures), READY_TEMPLATE_COUNT)
        self.assertEqual(len(set(signatures)), READY_TEMPLATE_COUNT)

    def test_signature_ignores_palette_and_font_only_changes(self):
        self.assertIsNotNone(recipe_signature)
        preset = lpr.list_ready_templates()[0]
        changed_appearance = dict(preset.appearance)
        changed_appearance["font"] = "Georgia"
        palette_font_clone = dataclasses.replace(
            preset,
            default_palette_slug="theme-midnight-electric",
            appearance=changed_appearance,
        )

        self.assertEqual(recipe_signature(preset), recipe_signature(palette_font_clone))

    def test_signature_observes_home_sequence_and_bounded_presentation(self):
        self.assertIsNotNone(recipe_signature)
        preset = lpr.list_ready_templates()[0]
        reversed_home = dataclasses.replace(
            preset,
            pages={**preset.pages, "home": tuple(reversed(preset.pages["home"]))},
        )

        self.assertNotEqual(recipe_signature(preset), recipe_signature(reversed_home))
