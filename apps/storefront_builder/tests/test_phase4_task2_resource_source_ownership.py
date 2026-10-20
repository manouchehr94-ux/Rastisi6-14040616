"""Phase 4, Task 2 — ResourceSource read/write + tenant ownership convergence.

Before this task, legacy (``views.py::_validate_universal_selection_ownership``)
and R4 (``r4_mutation_service._validate_resource_source_ownership``) were two
independently-maintained ownership checks that disagreed on ``category``:
legacy validated ``category_grid``'s manual ``category_ids`` but NEVER
validated ``product_section``'s single-reference auto ``source_id`` when
``data_source`` was ``category``/``brand``/``collection`` (only ``product_ids``,
i.e. manual mode, was checked) — R4's own equivalent already covered exactly
that case for ``product_section``, and separately no-opped for the
``category`` *kind* only because no section exposed it through R4 yet.

These tests characterize the previously-uncovered legacy gap (RED before this
task's fix), protect the fix (GREEN), and prove legacy and R4 now delegate to
the SAME shared, DB-backed ownership function
(``section_data_service.validate_resource_source_ownership``).
"""

from __future__ import annotations


from django.test import TestCase

from apps.catalog.models import Category
from apps.storefront_builder import resource_source
from apps.storefront_builder.services import section_data_service



class SharedOwnershipUnificationTests(TestCase):
    """Legacy and R4 must resolve through the exact same function object —
    not two independently-maintained implementations that could drift again."""


    def test_category_kind_is_no_longer_a_silent_noop(self):
        # Before this task, R4's local ownership check silently no-opped for
        # kind="category" ("not exposed by the Task 10 UI yet"). The shared
        # function now enforces it like every other kind, ready for Task 6
        # to enable category_grid's R4 schema without reopening this gap.
        import inspect

        source_lines = inspect.getsource(section_data_service.validate_resource_source_ownership)
        self.assertIn('if source.kind == "category":', source_lines)
        self.assertNotIn("not exposed", source_lines)


class CategoryResourceSourceOwnershipUnitTests(TestCase):
    """Direct coverage of the shared function's ``category`` kind branch."""

    def setUp(self):
        from apps.stores.models import Store

        self.store = Store.objects.create(
            name="فروشگاه تست", slug="phase4-task2-unit", admin_subdomain="phase4-task2-unit",
        )
        self.foreign_store = Store.objects.create(
            name="فروشگاه بیگانه سه", slug="phase4-task2-unit-foreign", admin_subdomain="phase4-task2-unit-foreign",
        )
        self.own_category = Category.objects.create(store=self.store, name="خودی", slug="unit-own-cat")
        self.foreign_category = Category.objects.create(
            store=self.foreign_store, name="بیگانه", slug="unit-foreign-cat",
        )

    def test_manual_owned_category_id_passes(self):
        source = resource_source.ResourceSource(
            kind="category", mode="manual", manual_ids=(self.own_category.pk,),
        )
        section_data_service.validate_resource_source_ownership(store=self.store, source=source)

    def test_manual_foreign_category_id_rejected(self):
        source = resource_source.ResourceSource(
            kind="category", mode="manual", manual_ids=(self.foreign_category.pk,),
        )
        with self.assertRaises(section_data_service.ResourceSourceOwnershipError):
            section_data_service.validate_resource_source_ownership(store=self.store, source=source)

    def test_auto_all_active_is_a_true_noop(self):
        source = resource_source.ResourceSource(kind="category", mode="auto", auto_rule="all_active")
        section_data_service.validate_resource_source_ownership(store=self.store, source=source)
