"""Coverage contracts from the Task 1 advertised vocabulary to A8 recipes."""

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.tests.test_a8_component_library import (
    A8_COMPONENT_KEYS as LITERAL_TASK_1_ADVERTISED_KEYS,
)

try:
    from apps.storefront_builder.storefront_appearance.inventory import (
        A8_ADVERTISED_COMPONENT_KEYS,
        A8_COMPONENT_COVERAGE_EXCEPTIONS,
        component_coverage,
    )
except ModuleNotFoundError:  # expected during the Task 4 RED run
    A8_ADVERTISED_COMPONENT_KEYS = None
    A8_COMPONENT_COVERAGE_EXCEPTIONS = None
    component_coverage = None


EXPECTED_ADVERTISED_COUNTS = {
    "header": 12,
    "mega_menu": 1,
    "hero": 13,
    "layout": 9,
    "product_view": 7,
    "card": 16,
    "badge": 2,
    "motion": 3,
    "footer": 8,
    "bottom_nav": 7,
    # P5-W2 — Ready Templates advertise only the Theme no-op.
    "theme": 1,
}


class A8ComponentCoverageTests(SimpleTestCase):
    def test_advertised_inventory_is_explicit_and_has_no_exceptions(self):
        self.assertIsNotNone(A8_ADVERTISED_COMPONENT_KEYS)
        self.assertEqual(A8_COMPONENT_COVERAGE_EXCEPTIONS, ())
        self.assertEqual(
            A8_ADVERTISED_COMPONENT_KEYS,
            LITERAL_TASK_1_ADVERTISED_KEYS,
        )
        actual_counts = {
            family: len(
                [key for key in A8_ADVERTISED_COMPONENT_KEYS if key.startswith(f"{family}.")]
            )
            for family in EXPECTED_ADVERTISED_COUNTS
        }
        self.assertEqual(actual_counts, EXPECTED_ADVERTISED_COUNTS)

    def test_every_advertised_component_is_used_by_at_least_one_recipe(self):
        self.assertIsNotNone(component_coverage)
        coverage = component_coverage(lpr.list_ready_templates())
        used = {
            component_key
            for family_counts in coverage.values()
            for component_key, count in family_counts.items()
            if count > 0
        }
        unused = set(A8_ADVERTISED_COMPONENT_KEYS) - used

        self.assertEqual(unused, set(A8_COMPONENT_COVERAGE_EXCEPTIONS))
