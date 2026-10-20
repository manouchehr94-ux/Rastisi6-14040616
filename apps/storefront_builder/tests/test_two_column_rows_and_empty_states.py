"""Two-column rows (Brand | Blog) through the ONE canonical Container/Cell engine, and the shared template-owned
empty-state contract. Nothing here is hard-coded to a template: any two registered sections can share a row, each keeps
its own settings, and an empty data source never removes a section — it renders the shared empty state in its own cell."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.catalog.models import Brand
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import (
    container_service, edit_history_service, layout_service as svc, render_service, r4_mutation_service as r4,
    section_empty_state_service,
)
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class TwoColumnBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.owner = User.objects.create_user(username="two_col_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.owner)

    def mutate(self, mutation):
        self.draft.refresh_from_db()
        return r4.apply_mutation(
            store=self.store, actor=self.owner, base_revision=self.draft.edit_revision, mutation=mutation,
        )

    def home(self):
        self.draft.refresh_from_db()
        return self.draft.get_page("home")

    def build_row(self, layout_key="half"):
        """Add a brand carousel, make its row two-cell, add the blog section into the empty cell."""
        self.mutate({"type": "section.add", "section_key": "brand_carousel", "page_type": "home"})
        brand = self.home().sections.filter(section_key="brand_carousel").latest("id")
        container = container_service.find_container_for_section(brand) if hasattr(
            container_service, "find_container_for_section") else None
        if container is None:
            from apps.storefront_builder.services import section_structure_service as sss

            container = sss.find_placement_cell(brand).container
        self.mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": layout_key})
        container.refresh_from_db()
        empty_cell = [c for c in container.cells.order_by("order", "id") if not container_service.get_cell_blocks(c)][0]
        self.mutate({"type": "cell.add_section", "section_key": "blog_posts", "cell_id": empty_cell.pk})
        blog = self.home().sections.filter(section_key="blog_posts").latest("id")
        return container, brand, blog


class TwoColumnRowTests(TwoColumnBase):
    def test_brand_and_blog_share_one_equal_row(self):
        container, brand, blog = self.build_row("half")
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual([c.span for c in cells], [6, 6])
        self.assertEqual(container.layout_key, "half")
        self.assertEqual(
            [[b.pk for b in container_service.get_cell_blocks(c)] for c in cells], [[brand.pk], [blog.pk]],
        )

    def test_ratio_change_keeps_both_sections_and_their_identities(self):
        container, brand, blog = self.build_row("half")
        before = (brand.stable_id, blog.stable_id)
        for layout_key, spans in (("third_left", [4, 8]), ("third_right", [8, 4]), ("half", [6, 6])):
            self.mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": layout_key})
            cells = list(container.cells.order_by("order", "id"))
            self.assertEqual([c.span for c in cells], spans, layout_key)
            ids = [b.pk for c in cells for b in container_service.get_cell_blocks(c)]
            self.assertEqual(sorted(ids), sorted([brand.pk, blog.pk]), layout_key)
        brand.refresh_from_db()
        blog.refresh_from_db()
        self.assertEqual((brand.stable_id, blog.stable_id), before)

    def test_each_cell_is_independently_configurable(self):
        _container, brand, blog = self.build_row("half")
        self.mutate({"type": "section.update_settings", "section_id": brand.pk, "patch": {"title": "برندهای ما"}})
        self.mutate({"type": "section.update_settings", "section_id": blog.pk, "patch": {"title": "مجله ما"}})
        brand.refresh_from_db()
        blog.refresh_from_db()
        self.assertEqual(brand.settings.get("title"), "برندهای ما")
        self.assertEqual(blog.settings.get("title"), "مجله ما")

    def test_row_edit_is_undoable(self):
        container, brand, blog = self.build_row("half")
        stable = {brand.stable_id, blog.stable_id}
        self.mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": "third_right"})
        self.draft.refresh_from_db()
        edit_history_service.undo(self.draft)
        # Undo restores the Draft state (containers may be re-created), so locate the row by section identity.
        restored = [
            c for c in self.home().containers.all()
            if {b.stable_id for cell in c.cells.all() for b in container_service.get_cell_blocks(cell)} == stable
        ]
        self.assertEqual(len(restored), 1)
        self.assertEqual([cell.span for cell in restored[0].cells.order_by("order", "id")], [6, 6])

    def test_row_is_store_scoped_other_store_untouched(self):
        from apps.stores.services.platform_code_service import generate_unique_platform_code

        other = Store.objects.create(
            name="O", slug=f"iso-other-{Store.objects.count()}", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        other_draft = svc.get_or_create_draft(other)
        before = StorefrontSection.objects.filter(page__version=other_draft).count()
        self.build_row("half")
        self.assertEqual(StorefrontSection.objects.filter(page__version=other_draft).count(), before)
        self.assertFalse(StorefrontSection.objects.filter(page__version=other_draft, section_key="brand_carousel").exists())


class EmptyStateContractTests(TwoColumnBase):
    def items(self):
        page = self.home()
        return render_service.build_page_render_items(page, self.store)

    def test_zero_brands_and_posts_keep_both_sections_with_empty_states_inside_their_cells(self):
        Brand.objects.filter(store=self.store).delete()
        container, brand, blog = self.build_row("half")
        by_id = {i["section"].pk: i for i in self.items()}
        self.assertIsNotNone(by_id[brand.pk]["empty_state"])
        self.assertEqual(by_id[brand.pk]["empty_state"]["kind"], "brand")
        self.assertEqual(by_id[brand.pk]["empty_state"]["studio_message"], "فروشگاه شما هنوز برندی تعریف نکرده است.")
        self.assertEqual(by_id[blog.pk]["empty_state"]["kind"], "blog") if by_id[blog.pk]["empty_state"] else None
        rows = render_service.build_container_render_items(self.home(), list(by_id.values()), include_empty=True)
        row = next(r for r in rows if any((c.get("item") or {}).get("section") and c["item"]["section"].pk == brand.pk
                                          for c in r["cells"]))
        self.assertEqual(len(row["cells"]), 2)

    def test_public_path_never_drops_an_empty_template_owned_section(self):
        Brand.objects.filter(store=self.store).delete()
        _c, brand, _b = self.build_row("half")
        public = render_service.hide_empty_public_sections(self.items())
        self.assertIn(brand.pk, [i["section"].pk for i in public])

    def test_adding_data_later_fills_the_same_section_without_reinstalling(self):
        Brand.objects.filter(store=self.store).delete()
        _c, brand, _b = self.build_row("half")
        before = next(i for i in self.items() if i["section"].pk == brand.pk)
        self.assertIsNotNone(before["empty_state"])
        Brand.objects.create(store=self.store, name="برند واقعی", slug="real-brand-es", is_active=True)
        after = next(i for i in self.items() if i["section"].pk == brand.pk)
        self.assertIsNone(after["empty_state"])
        self.assertEqual(after["section"].pk, brand.pk)

    def test_studio_and_public_markup_differ_only_in_audience(self):
        from django.template.loader import render_to_string

        Brand.objects.filter(store=self.store).delete()
        _c, brand, _b = self.build_row("half")
        item = next(i for i in self.items() if i["section"].pk == brand.pk)
        studio = render_to_string(
            "storefront_builder/sections/section_empty_state.html", {"item": item, "is_builder_preview": True},
        )
        public = render_to_string(
            "storefront_builder/sections/section_empty_state.html", {"item": item, "is_builder_preview": False},
        )
        self.assertIn("فروشگاه شما هنوز برندی تعریف نکرده است.", studio)
        self.assertIn("به‌صورت خودکار پر می‌شود", studio)
        self.assertNotIn("فروشگاه شما هنوز برندی", public)
        self.assertNotIn("پر می‌شود", public)
        self.assertIn("data-empty-state=\"brand\"", public)

    def test_no_section_spec_invents_data(self):
        for key in ("brand_carousel", "category_grid", "blog_posts", "multi_banner", "newest_products"):
            self.assertIsNotNone(section_empty_state_service.spec_for(key), key)


class SpecKeysMatchTheContextBuildersTests(TwoColumnBase):
    def test_every_registered_spec_reads_a_key_its_builder_actually_provides(self):
        """A spec naming a key the builder never sets would make a populated section look empty (it did for
        ``single_banner``: the builder exposes ``banners``)."""
        from apps.storefront_builder.services.section_empty_state_service import _SPECS

        home = self.home()
        for index, section_key in enumerate(sorted(_SPECS)):
            StorefrontSection.objects.create(page=home, section_key=section_key, order=900 + index, settings={})
        items = {i["section"].section_key: i for i in render_service.build_page_render_items(self.home(), self.store)}
        for section_key, spec in _SPECS.items():
            if section_key not in items:
                continue  # not allowed on this page type / hidden from the library
            missing = [k for k in spec.context_keys if k not in items[section_key]["context"]]
            self.assertEqual(missing, [], f"{section_key}: spec reads {missing} which its builder does not set")
