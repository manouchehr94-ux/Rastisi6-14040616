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

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category
from apps.storefront_builder import resource_source
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service, section_data_service

from .test_views import StorefrontBuilderViewsTestCase


class LegacyProductSectionSingleReferenceOwnershipTests(StorefrontBuilderViewsTestCase):
    """The real, previously-uncovered gap: a merchant-controlled ``source_id``
    for ``product_section``'s ``category``/``brand``/``collection`` auto
    modes was never ownership-checked at write time — only manual
    ``product_ids`` was. The render path (``section_data_service._resolve_category``
    etc.) already re-scopes by Store independently, so this was never an
    exploitable data-exposure bug, but the write side should reject it, not
    silently persist a foreign reference."""

    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.foreign_store = type(self.store).objects.create(
            name="فروشگاه بیگانه",
            slug="phase4-task2-foreign",
            admin_subdomain="phase4-task2-foreign",
        )
        self.foreign_category = Category.objects.create(
            store=self.foreign_store, name="بیگانه", slug="foreign-cat",
        )

    def _product_section(self):
        section = StorefrontSection.objects.create(
            page=self.page, section_key="product_section", order=0,
            settings={
                "data_source": "newest", "source_id": None, "product_ids": [],
                "item_limit": 6, "display_mode": "carousel", "show_view_all": True,
                "title": "", "subtitle": "", "carousel_autoplay": False,
                "carousel_interval_ms": 3500, "carousel_show_arrows": True,
                "header_position": "above",
            },
        )
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)
        return section

    def _post(self, section, *, data_source, source_id):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "data_source": data_source,
                "source_id": str(source_id),
                "item_limit": "6",
                "display_mode": "carousel",
                "show_view_all": "on",
                "title": "عنوان",
                "subtitle": "",
                "carousel_interval_ms": "3500",
                "carousel_show_arrows": "on",
                "header_position": "above",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )

    def test_foreign_category_source_id_is_rejected(self):
        section = self._product_section()
        response = self._post(section, data_source="category", source_id=self.foreign_category.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "متعلق به این فروشگاه نیست")
        section.refresh_from_db()
        self.assertEqual(section.settings["data_source"], "newest")

    def test_own_category_source_id_is_accepted(self):
        own_category = Category.objects.create(store=self.store, name="خودی", slug="own-cat")
        section = self._product_section()
        response = self._post(section, data_source="category", source_id=own_category.pk)
        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["data_source"], "category")
        self.assertEqual(section.settings["source_id"], own_category.pk)

    def test_nonexistent_category_source_id_is_rejected(self):
        section = self._product_section()
        response = self._post(section, data_source="category", source_id=999999)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "متعلق به این فروشگاه نیست")


class LegacyCategoryGridOwnershipRegressionTests(StorefrontBuilderViewsTestCase):
    """``category_grid``'s manual ``category_ids`` ownership check already
    worked before this task (via the old per-model dict lookup) — protected
    here as a regression guard now that it routes through the shared
    ResourceSource-based check instead."""

    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.foreign_store = type(self.store).objects.create(
            name="فروشگاه بیگانه دو",
            slug="phase4-task2-foreign2",
            admin_subdomain="phase4-task2-foreign2",
        )
        self.foreign_category = Category.objects.create(
            store=self.foreign_store, name="بیگانه۲", slug="foreign-cat-2",
        )

    def _category_grid_section(self):
        section = StorefrontSection.objects.create(
            page=self.page, section_key="category_grid", order=0,
            settings={"title": "", "display_mode": "grid", "category_ids": [], "item_limit": 12},
        )
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)
        return section

    def test_foreign_category_ids_still_rejected(self):
        section = self._category_grid_section()
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "title": "دسته‌ها",
                "display_mode": "grid",
                "category_ids": [str(self.foreign_category.pk)],
                "item_limit": "12",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "متعلق به این فروشگاه نیست")
        section.refresh_from_db()
        self.assertEqual(section.settings["category_ids"], [])

    def test_own_category_ids_still_accepted(self):
        own = Category.objects.create(store=self.store, name="خودیِ گرید", slug="own-grid-cat")
        section = self._category_grid_section()
        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {
                "title": "دسته‌ها",
                "display_mode": "grid",
                "category_ids": [str(own.pk)],
                "item_limit": "12",
            },
        )
        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["category_ids"], [own.pk])


class SharedOwnershipUnificationTests(TestCase):
    """Legacy and R4 must resolve through the exact same function object —
    not two independently-maintained implementations that could drift again."""

    def test_legacy_and_r4_call_the_same_shared_function(self):
        from apps.storefront_builder import views
        from apps.storefront_builder.services import r4_mutation_service

        dummy_store = object()
        with mock.patch.object(
            section_data_service, "validate_resource_source_ownership",
        ) as shared, mock.patch.object(views, "_resolve_store", return_value=dummy_store):
            # Both call sites reference the module-level function looked up
            # at call time via ``section_data_service.validate_resource_source_ownership``
            # (not a rebound local import), so patching the shared module
            # attribute affects both — proving there is no second,
            # independently-invocable copy of the ownership logic anywhere.
            # Exercise BOTH call sites under the same patch, not just R4's —
            # a prior version of this test only checked R4 and left an
            # unused ``views`` import, which would have let a reintroduced
            # local legacy copy (with identical output) slip past silently.
            source = resource_source.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
            r4_mutation_service._validate_resource_source_ownership(store=dummy_store, source=source)

            views._validate_universal_selection_ownership(
                request=object(), section_key="brand_carousel", cleaned={"brand_ids": []},
            )

            self.assertEqual(shared.call_count, 2)
            for call in shared.call_args_list:
                self.assertEqual(call.kwargs["store"], dummy_store)

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
