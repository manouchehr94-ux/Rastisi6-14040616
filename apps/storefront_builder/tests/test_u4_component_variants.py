"""U4 — Hero/Category/Content/Promotion Component System.

Behavioral tests for the three structural-variant extensions this phase
adds to the existing U1 ``variant_contract``/``SECTION_REGISTRY`` mechanism
(no new/competing registry, exactly the ``category_grid``/``brand_carousel``/
``product_section`` precedent):

- ``hero_banner``: new Pattern B variant (``split``, a genuinely different
  renderer partial) alongside the untouched, still-default ``overlay``.
- ``collection_tiles``: new Pattern A variant (``carousel``, same template,
  CSS branches on the new ``tile_style`` key), alongside the untouched,
  still-default ``grid``.
- ``image_text``: formalizes the already-existing, already-coerced
  ``image_position`` closed enum into the same registered-variant
  mechanism — no template/behavior change.

Also guards the explicit, documented R1 decision that ``multi_banner`` must
NOT be narrowed into a closed-set variant registry (its historical
``layout_variant`` write path cannot be proven closed from source alone).
"""

from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide
from apps.storefront_builder.section_registry import (
    SECTION_REGISTRY,
    get_definition,
)
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_render_items
from apps.storefront_builder.variant_contract import resolve_active_variant, resolve_renderer_template
from apps.stores.models import Store, StoreDomain

HOST = "sfb-u4.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


def _img(name="u4-hero.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (30, 60, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class MultiBannerNotNarrowedTests(TestCase):
    """R1 §9 explicitly forbids narrowing ``multi_banner`` into a closed
    enum without proof from live data — this is a tripwire against a future
    change accidentally doing that anyway while "helping" U4."""

    def test_multi_banner_has_no_registered_variants(self):
        definition = get_definition("multi_banner")
        self.assertEqual(definition.variants, ())

    def test_multi_banner_validate_settings_still_passthrough(self):
        definition = get_definition("multi_banner")
        cleaned = definition.validate_settings({"layout_variant": "anything-at-all"})
        self.assertEqual(cleaned["layout_variant"], "anything-at-all")


class ImageTextVariantFormalizationTests(TestCase):
    def test_registered_variants_match_existing_enum(self):
        definition = get_definition("image_text")
        keys = [v.key for v in definition.variants]
        self.assertEqual(sorted(keys), ["left", "right"])
        self.assertEqual(definition.default_variant, "right")
        self.assertEqual(definition.variant_setting_key, "image_position")

    def test_both_variants_have_no_renderer_override(self):
        """Pattern A — same template either way, so ``resolve_renderer_template``
        must return ``image_text.html`` regardless of which side is chosen."""
        definition = get_definition("image_text")
        for value in ("left", "right", "garbage", None):
            active = resolve_active_variant(definition, {"image_position": value})
            self.assertEqual(
                resolve_renderer_template(definition, active),
                "storefront_builder/sections/image_text.html",
            )

    def test_invalid_stored_value_still_coerces_via_own_validator(self):
        definition = get_definition("image_text")
        cleaned = definition.validate_settings({"image_position": "center"})
        self.assertEqual(cleaned["image_position"], "right")


class CollectionTilesVariantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_registered_variants(self):
        definition = get_definition("collection_tiles")
        keys = [v.key for v in definition.variants]
        self.assertEqual(sorted(keys), ["carousel", "grid"])
        self.assertEqual(definition.default_variant, "grid")
        self.assertEqual(definition.variant_setting_key, "tile_style")

    def test_invalid_tile_style_coerces_to_grid(self):
        definition = get_definition("collection_tiles")
        cleaned = definition.validate_settings({"tile_style": "not-a-real-style"})
        self.assertEqual(cleaned["tile_style"], "grid")

    def test_missing_tile_style_on_legacy_settings_defaults_to_grid(self):
        """A section saved before U4 has no ``tile_style`` key at all —
        must resolve exactly like an explicit ``grid``, never raise."""
        definition = get_definition("collection_tiles")
        cleaned = definition.validate_settings({"title": "کالکشن‌ها"})
        self.assertEqual(cleaned["tile_style"], "grid")

    def test_grid_renders_unchanged_container_class(self):
        from apps.catalog.models import MerchantCollection

        MerchantCollection.objects.create(store=self.store, name="کالکشن گرید", slug="u4-ct-grid", is_active=True)
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        StorefrontSection.objects.create(version=draft, section_key="collection_tiles", order=900)
        svc.publish(self.store)
        _verified_domain(self.store, HOST)
        with self.settings(ALLOWED_HOSTS=[HOST, "testserver"]):
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, '<div class="grid g4">')
        self.assertNotContains(resp, "tiles-carousel")

    def test_carousel_renders_new_container_classes(self):
        from apps.catalog.models import MerchantCollection

        MerchantCollection.objects.create(store=self.store, name="کالکشن کاروسل", slug="u4-ct-carousel", is_active=True)
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"tile_style": "carousel"},
        )
        svc.publish(self.store)
        _verified_domain(self.store, HOST)
        with self.settings(ALLOWED_HOSTS=[HOST, "testserver"]):
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "tiles-carousel collection-tiles-carousel")
        self.assertContains(resp, "کالکشن کاروسل")

    def test_title_and_source_edit_preserves_carousel_variant(self):
        """Task 5 — editing a collection_tiles section's title AND its source
        selection (``collection_ids``) must NOT change its structural variant:
        a ``carousel`` section keeps its ``tiles-carousel`` container after a
        real settings edit (variant/local intent preserved, only the local
        content changes)."""
        from apps.catalog.models import MerchantCollection

        c1 = MerchantCollection.objects.create(store=self.store, name="کالکشن اول", slug="u4-ct-src1", is_active=True)
        c2 = MerchantCollection.objects.create(store=self.store, name="کالکشن دوم", slug="u4-ct-src2", is_active=True)
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        section = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"tile_style": "carousel", "title": "قبل", "collection_ids": [c1.pk]},
        )
        # A real settings edit: new title + new source selection, variant kept.
        definition = get_definition("collection_tiles")
        section.settings = definition.validate_settings(
            {"tile_style": "carousel", "title": "بعد", "collection_ids": [c2.pk]},
        )
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        _verified_domain(self.store, HOST)
        with self.settings(ALLOWED_HOSTS=[HOST, "testserver"]):
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        # Variant preserved (still carousel), local intent updated.
        self.assertContains(resp, "tiles-carousel collection-tiles-carousel")
        self.assertContains(resp, "بعد")
        self.assertContains(resp, "کالکشن دوم")
        self.assertNotContains(resp, "کالکشن اول")

    def test_publish_restore_retains_selection_and_stable_id_not_pk(self):
        """Task 5 — after publish, the section is CLONED into a new version:
        its PK changes but its ``stable_id`` (the logical identity) is
        preserved, and the merchant's source selection / variant survive the
        clone. Mirrors ``layout_service``'s documented clone contract."""
        from apps.catalog.models import MerchantCollection

        c1 = MerchantCollection.objects.create(store=self.store, name="کالکشن الف", slug="u4-ct-sid1", is_active=True)
        c2 = MerchantCollection.objects.create(store=self.store, name="کالکشن ب", slug="u4-ct-sid2", is_active=True)
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        draft_section = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"tile_style": "carousel", "collection_ids": [c2.pk, c1.pk]},
        )
        published_stable_id = draft_section.stable_id

        svc.publish(self.store)

        from apps.storefront_builder.services import page_resolution_service

        published = page_resolution_service.get_published_layout(self.store).published_version
        pub_page = published.pages.get(page_type="home")
        published_section = pub_page.sections.get(section_key="collection_tiles")
        published_pk = published_section.pk
        # stable_id is stable through publish.
        self.assertEqual(published_section.stable_id, published_stable_id)
        # The merchant's manual source selection + order + variant survive publish.
        self.assertEqual(published_section.settings["collection_ids"], [c2.pk, c1.pk])
        self.assertEqual(published_section.settings["tile_style"], "carousel")

        # Restore/Draft-bootstrap CLONES published -> a fresh draft version:
        # the cloned section is a NEW row (different PK) but the SAME logical
        # section (stable_id preserved), and the selection/variant survive the
        # clone — stable_id, NOT PK, is the cross-version identity.
        new_draft = svc.get_or_create_draft(self.store)
        cloned_section = new_draft.sections.get(section_key="collection_tiles")
        self.assertEqual(cloned_section.stable_id, published_stable_id)
        self.assertNotEqual(cloned_section.pk, published_pk)
        self.assertEqual(cloned_section.settings["collection_ids"], [c2.pk, c1.pk])
        self.assertEqual(cloned_section.settings["tile_style"], "carousel")

    def test_draft_only_edit_leaves_published_public_unchanged(self):
        """Task 5 — an edit made to the DRAFT (never published) must not leak
        into the public storefront: the public route keeps serving the last
        PUBLISHED collection_tiles content, not the unpublished draft edit."""
        from apps.catalog.models import MerchantCollection

        MerchantCollection.objects.create(store=self.store, name="کالکشن منتشرشده", slug="u4-ct-pub", is_active=True)
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"tile_style": "grid", "title": "عنوان منتشرشده", "collection_ids": []},
        )
        svc.publish(self.store)
        _verified_domain(self.store, HOST)

        # Now make a DRAFT-only edit that is never published.
        draft2 = svc.get_or_create_draft(self.store)
        draft_section = draft2.sections.get(section_key="collection_tiles")
        draft_section.settings = {**draft_section.settings, "title": "عنوان پیش‌نویسِ منتشرنشده"}
        draft_section.save(update_fields=["settings"])

        with self.settings(ALLOWED_HOSTS=[HOST, "testserver"]):
            resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        # Public still serves the published title, NOT the unpublished draft edit.
        self.assertContains(resp, "عنوان منتشرشده")
        self.assertNotContains(resp, "عنوان پیش‌نویسِ منتشرنشده")


class HeroBannerVariantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self._override = self.settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_registered_variants(self):
        definition = get_definition("hero_banner")
        keys = [v.key for v in definition.variants]
        self.assertEqual(sorted(keys), ["atelier_triptych", "beauty_editorial", "chocolate_carousel", "luxury_showcase", "overlay", "split"])
        self.assertEqual(definition.default_variant, "overlay")
        self.assertEqual(definition.variant_setting_key, "hero_style")

    def test_image_slider_unaffected_no_variants_registered(self):
        """U4 deliberately scopes the new variant to ``hero_banner`` only —
        ``image_slider`` shares the same settings validator but must not
        gain a variant concept it wasn't asked for."""
        definition = get_definition("image_slider")
        self.assertEqual(definition.variants, ())

    def test_default_overlay_resolves_to_original_template_unchanged(self):
        definition = get_definition("hero_banner")
        active = resolve_active_variant(definition, {})
        self.assertEqual(
            resolve_renderer_template(definition, active),
            "storefront_builder/sections/hero_banner.html",
        )

    def test_split_resolves_to_new_renderer(self):
        definition = get_definition("hero_banner")
        active = resolve_active_variant(definition, {"hero_style": "split"})
        self.assertEqual(
            resolve_renderer_template(definition, active),
            "storefront_builder/sections/hero_banner_split.html",
        )

    def test_beauty_editorial_resolves_to_shared_slider_wrapper(self):
        definition = get_definition("hero_banner")
        active = resolve_active_variant(definition, {"hero_style": "beauty_editorial"})
        self.assertEqual(
            resolve_renderer_template(definition, active),
            "storefront_builder/sections/hero_banner_beauty.html",
        )

    def test_atelier_triptych_resolves_to_its_registered_renderer(self):
        definition = get_definition("hero_banner")
        active = resolve_active_variant(definition, {"hero_style": "atelier_triptych"})
        self.assertEqual(
            resolve_renderer_template(definition, active),
            "storefront_builder/sections/hero_banner_atelier.html",
        )

    def test_invalid_hero_style_coerces_to_overlay(self):
        definition = get_definition("hero_banner")
        cleaned = definition.validate_settings({"hero_style": "not-a-real-style"})
        self.assertEqual(cleaned["hero_style"], "overlay")

    def _publish_hero(self, *, settings, slide_kwargs):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999, settings=settings,
        )
        HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, **slide_kwargs)
        svc.publish(self.store)

    def test_default_overlay_end_to_end_markup_unchanged(self):
        self._publish_hero(settings={}, slide_kwargs={"title": "اسلایدِ اصلی یو۴"})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "اسلایدِ اصلی یو۴")
        self.assertContains(resp, "hero-slide single")
        self.assertNotContains(resp, "hero-split-inner")

    def test_split_variant_end_to_end_markup(self):
        self._publish_hero(
            settings={"hero_style": "split"},
            slide_kwargs={"title": "هدرِ دوستونه", "subtitle": "زیرنویسِ واقعی"},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "hero-split-inner")
        self.assertContains(resp, "هدرِ دوستونه")
        self.assertContains(resp, "زیرنویسِ واقعی")
        # Pattern B — the default overlay's carousel chrome must not leak in.
        self.assertNotContains(resp, "hero-tabs")

    def test_overlay_honors_explicitly_disabled_arrows_and_dots(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999,
            settings={"show_arrows": False, "show_dots": False},
        )
        HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, title="اول", display_order=0)
        HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, title="دوم", display_order=1)
        svc.publish(self.store)

        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "hero-arrow-prev")
        self.assertNotContains(resp, "hero-arrow-next")
        self.assertNotContains(resp, "hero-tabs")

    def test_split_variant_shows_only_first_slide_no_fabrication(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999, settings={"hero_style": "split"},
        )
        HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, title="اسلایدِ اول", display_order=0)
        HeroSlide.objects.create(store=self.store, section=section, desktop_image=_img(), is_active=True, title="اسلایدِ دوم", display_order=1)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "اسلایدِ اول")
        self.assertNotContains(resp, "اسلایدِ دوم")


class AllRegisteredVariantsResolveSafelyTests(TestCase):
    """Generic safety net across every ``SECTION_REGISTRY`` entry with
    ``variants`` (not just the three U4 touches) — an unknown/garbage stored
    value must always fail safely to the default, never raise."""

    def test_no_definition_with_variants_raises_on_garbage_input(self):
        for key, definition in SECTION_REGISTRY.items():
            if not definition.variants:
                continue
            for garbage in (None, "", "totally-unregistered-key", 12345):
                active = resolve_active_variant(definition, {definition.variant_setting_key: garbage})
                self.assertIsNotNone(active, key)
                self.assertEqual(active.key, definition.default_variant, key)
