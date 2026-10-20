"""G2.1 Defect C (re-based by ARCH-02) — EVERYTHING VISIBLY RENDERED IN PREVIEW MUST HAVE A TRUTHFUL EDIT PATH.

The demo's images are the store's SHARED default media (``section=NULL``): store-owned,
template-independent, rendered by every section that has no media of its own
(``render_service._scoped_*``). The R4 media manager must therefore never report "0 items"
for a section that visibly renders them, and the truthful edit path is explicit:

  VISIBLE IN PREVIEW  ->  LISTED AS "DEFAULT MEDIA" IN THE SECTION  ->  ADOPT (copy-on-write)
  ->  THE COPY OPENS FOR EDITING (200)

while the shared originals and every OTHER section's rendered content stay untouched.
"""

import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Product, ProductImage
from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from django.utils import timezone

from apps.storefront_builder.services import layout_service, render_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store, StoreMembership

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class G2_1MediaEditabilityRoundTripTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        # Golden setup: catalog/content + baseline apply + Golden customization + publish.
        call_command("apply_golden_reference_storefront", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)
        # The Builder edits a DRAFT (Preview renders the Draft). Opening the
        # Builder clones Published -> Draft, exactly like a merchant opening the
        # editor. All media CRUD + this round-trip must work on the Draft.
        self.draft = layout_service.get_or_create_draft(self.store)
        self.home = self.draft.get_page("home")
        # A staff user with an OWNER membership can reach the Builder media CRUD.
        # Created explicitly here (the seed no longer provisions any owner).
        self.user = User.objects.create_user(
            username="g21_media_staff", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.user)

    # --------------------------------------------------------------- helpers

    def _section(self, section_key, occurrence=0):
        secs = [s for s in self.home.sections.order_by("order") if s.section_key == section_key]
        return secs[occurrence]

    def _rendered_items(self, section, context_key, resolver):
        return list(resolver(self.store, section)[context_key] if False else resolver(self.store, section))

    # --------------------------------------------------------------- list not zero

    def _host(self):
        return {"HTTP_HOST": f"{self.store.admin_subdomain}.rastisi.localhost"}

    def test_hero_media_list_is_not_falsely_zero_when_shared_media_renders(self):
        from apps.storefront_builder.services import media_defaults_service

        hero = self._section("hero_banner")
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        self.assertGreater(len(rendered), 0)
        self.assertTrue(all(r.section_id is None for r in rendered))  # shared, store-owned
        state = media_defaults_service.default_media_state(hero, HeroSlide)
        self.assertTrue(state.in_effect)
        self.assertEqual([r.pk for r in state.items], [r.pk for r in rendered])
        url = reverse("dashboard:storefront-builder-section-media-list", args=[hero.pk, "hero-slides"])
        resp = self.client.get(url, **self._host())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تصاویر پیش‌فرض فروشگاه")  # the manager surfaces them (not "0 items")
        self.assertContains(resp, "قابل‌ویرایش کردن تصاویر پیش‌فرض")

    # --------------------------------------------------------------- adopt -> edit opens (no 404)

    def _adopt(self, section, kind):
        url = reverse("dashboard:storefront-builder-section-media-adopt-defaults", args=[section.pk, kind])
        # htmx request -> the endpoint returns the refreshed list body (200) instead of a redirect
        return self.client.post(url, HTTP_HX_REQUEST="true", **self._host())

    def test_adopting_the_shared_hero_slides_gives_each_a_working_edit_path(self):
        hero = self._section("hero_banner")
        shared_before = list(HeroSlide.objects.filter(store=self.store, section__isnull=True).values_list("pk", "is_active", "title"))
        rendered = list(render_service._scoped_hero_slides(self.store, hero))
        self.assertEqual(self._adopt(hero, "hero-slides").status_code, 200)
        own = list(HeroSlide.objects.filter(section=hero).order_by("display_order", "id"))
        self.assertEqual([o.title for o in own], [r.title for r in rendered])  # same content, same order
        url = reverse("dashboard:storefront-builder-section-media-edit", args=[hero.pk, "hero-slides", own[0].pk])
        self.assertEqual(self.client.get(url, **self._host()).status_code, 200,
                         "an adopted hero item must have a working edit path")
        # the shared originals are untouched
        self.assertEqual(
            shared_before,
            list(HeroSlide.objects.filter(store=self.store, section__isnull=True).values_list("pk", "is_active", "title")),
        )

    def test_a_shared_item_is_not_directly_editable_through_a_section(self):
        hero = self._section("hero_banner")
        shared = HeroSlide.objects.filter(store=self.store, section__isnull=True).first()
        url = reverse("dashboard:storefront-builder-section-media-edit", args=[hero.pk, "hero-slides", shared.pk])
        self.assertEqual(self.client.get(url, **self._host()).status_code, 404)

    def test_adopting_banners_in_one_section_never_changes_another_section_or_the_shared_media(self):
        banner_sections = [s for s in self.home.sections.order_by("order") if s.section_key == "multi_banner"]
        self.assertGreaterEqual(len(banner_sections), 2)
        sec_a, sec_b = banner_sections[0], banner_sections[1]
        before_b = [b.pk for b in render_service._scoped_banners(self.store, sec_b)]
        shared_before = list(PromotionalBanner.objects.filter(store=self.store, section__isnull=True).values_list("pk", "is_active"))
        self.assertEqual(self._adopt(sec_a, "banners").status_code, 200)
        own_a = list(PromotionalBanner.objects.filter(section=sec_a).order_by("display_order", "id"))
        self.assertGreater(len(own_a), 0)
        toggle = reverse("dashboard:storefront-builder-section-media-toggle", args=[sec_a.pk, "banners", own_a[0].pk])
        self.assertEqual(self.client.post(toggle, **self._host()).status_code, 200)
        self.assertEqual([b.pk for b in render_service._scoped_banners(self.store, sec_b)], before_b)
        self.assertEqual(
            shared_before,
            list(PromotionalBanner.objects.filter(store=self.store, section__isnull=True).values_list("pk", "is_active")),
        )

    def test_the_two_golden_banner_sections_render_distinct_slices_of_the_shared_media(self):
        banner_sections = [s for s in self.home.sections.order_by("order") if s.section_key == "multi_banner"]
        self.assertEqual(len(banner_sections), 2)
        from apps.storefront_builder.services import render_service as rs

        a = [b.pk for b in rs._multi_banner_context(self.store, banner_sections[0])["banners"]]
        b = [b.pk for b in rs._multi_banner_context(self.store, banner_sections[1])["banners"]]
        self.assertTrue(a and b)
        self.assertFalse(set(a) & set(b), "the two banner rows must not show the same shared banners")

    # --------------------------------------------------------------- product image round-trip

    def test_product_image_roundtrip_for_fsh_050(self):  # noqa: D401
        product = Product.objects.get(store=self.store, sku="FSH-050")
        rows = list(product.images.all())
        self.assertGreater(len(rows), 0)
        # exactly one cover; storefront card reads the same cover row
        covers = [i for i in rows if i.is_cover]
        self.assertEqual(len(covers), 1)
        self.assertEqual(product.cover_image.pk, covers[0].pk)
        # all images belong to this product/store
        for img in rows:
            self.assertEqual(img.product_id, product.id)
            self.assertEqual(img.product.store_id, self.store.pk)
        # editor image manager opens and shows the same rows
        url = reverse("dashboard:product-images", args=[product.pk])
        resp = self.client.get(url, HTTP_HOST=f"{self.store.admin_subdomain}.rastisi.localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context["product"].images.all()), rows)

    # --------------------------------------------------------------- category round-trip

    def test_seeded_product_category_is_a_valid_editor_leaf(self):
        from apps.dashboard.services.catalog_admin_service import leaf_categories

        product = Product.objects.get(store=self.store, sku="FSH-050")
        valid_ids = set(leaf_categories(self.store).values_list("id", flat=True))
        self.assertIn(product.category_id, valid_ids)
