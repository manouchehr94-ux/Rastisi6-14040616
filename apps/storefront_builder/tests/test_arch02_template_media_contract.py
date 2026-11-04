"""ARCH-02 — one R4 engine: template Apply / candidate Preview / shared store media.

Owner contract (mission ARCH-02):

* Apply replaces the Draft's template-owned design (sections, header, footer,
  appearance) and nothing else; Published is untouched until an explicit Publish.
* The store's shared default media (``section IS NULL`` Hero/Banner/Story rows and
  their ``MediaAsset`` files) is store-owned and template-independent: it survives
  every template switch, and every template renders it.
* A candidate Preview never persists anything and shows exactly the media a real
  Apply would show (no cross-section borrowing, no Draft+Published duplicates).
* Repeating an Apply never accumulates sections or media.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service, render_service
from apps.storefront_builder.services import r4_mutation_service as r4
from apps.stores.models import Store, StoreMembership
from apps.storefront_builder.tests._catalog_count import READY_TEMPLATE_COUNT

User = get_user_model()


def _pool_state(store):
    return (
        list(HeroSlide.objects.filter(store=store, section__isnull=True).order_by("id").values_list("id", "title", "display_order", "desktop_asset_id")),
        list(PromotionalBanner.objects.filter(store=store, section__isnull=True).order_by("id").values_list("id", "title", "display_order", "desktop_asset_id")),
        list(StoryRailItem.objects.filter(store=store, section__isnull=True).order_by("id").values_list("id", "title", "display_order", "image_asset_id")),
        MediaAsset.objects.filter(store=store).count(),
    )


def _media_ids(items):
    """(section_key, hero ids, banner ids, story ids) for every media-bearing item."""
    out = []
    for item in items:
        ctx = item.get("context") or {}
        row = (
            item["section"].section_key,
            tuple(s.pk for s in ctx.get("hero_slides", ())) if "hero_slides" in ctx else None,
            tuple(b.pk for b in ctx.get("banners", ())) if "banners" in ctx else None,
            tuple(i.pk for i in ctx.get("story_items", ())) if "story_items" in ctx else None,
        )
        if any(v is not None for v in row[1:]):
            out.append(row)
    return out


class MediaContractBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.staff = User.objects.create_user("arch02_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        # Shared default media: 4 heroes, 6 banners, 3 stories — all store-wide.
        for i in range(4):
            a = MediaAsset.objects.create(store=self.store, image=f"pool/hero{i}.png")
            HeroSlide.objects.create(
                store=self.store, section=None, title=f"pool-hero-{i}", desktop_asset=a,
                is_active=True, display_order=i,
            )
        for i in range(6):
            a = MediaAsset.objects.create(store=self.store, image=f"pool/banner{i}.png")
            PromotionalBanner.objects.create(
                store=self.store, section=None, title=f"pool-banner-{i}", desktop_asset=a,
                is_active=True, display_order=i,
            )
        for i in range(3):
            a = MediaAsset.objects.create(store=self.store, image=f"pool/story{i}.png")
            StoryRailItem.objects.create(
                store=self.store, section=None, title=f"pool-story-{i}", image_asset=a,
                is_active=True, display_order=i,
            )
        self.layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("aftab_price"))
        self.published = svc.publish(self.store, user=self.staff)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)

    def active_draft(self):
        self.layout.refresh_from_db()
        return StorefrontLayoutVersion.objects.get(pk=self.layout.draft_version_id)

    def switch(self, preset):
        return r4.switch_template(
            store=self.store, actor=self.staff, base_revision=self.active_draft().edit_revision,
            template_key=preset.key, template_version=preset.version, confirm_replace=True,
        )

    def draft_items(self):
        return render_service.build_render_items(self.active_draft(), self.store)


class CandidateFallbackTests(MediaContractBase):
    def _scoped_copies_in(self, version_section, n=2):
        for i in range(n):
            a = MediaAsset.objects.create(store=self.store, image=f"scoped/{version_section.pk}_{i}.png")
            HeroSlide.objects.create(
                store=self.store, section=version_section, title=f"own-{i}", desktop_asset=a,
                is_active=True, display_order=i,
            )

    def test_candidate_section_renders_the_shared_pool_exactly_once(self):
        # The same Placement exists in BOTH the Published and the Draft version (what
        # a Draft clone produces). The former "borrow from any same-key section" tier
        # returned both copies -> every slide twice in a candidate preview.
        pub_hero = self.published.get_page("home").sections.filter(section_key="hero_banner").first()
        draft_hero = self.active_draft().get_page("home").sections.filter(section_key="hero_banner").first()
        self.assertIsNotNone(pub_hero)
        self.assertIsNotNone(draft_hero)
        self._scoped_copies_in(pub_hero)
        self._scoped_copies_in(draft_hero)

        candidate_section = StorefrontSection(section_key="hero_banner", settings={})  # unsaved: pk is None
        slides = list(render_service._scoped_hero_slides(self.store, candidate_section))
        self.assertEqual([s.title for s in slides], [f"pool-hero-{i}" for i in range(4)])

    def test_saved_section_with_own_media_never_mixes_in_the_pool(self):
        draft_hero = self.active_draft().get_page("home").sections.filter(section_key="hero_banner").first()
        self._scoped_copies_in(draft_hero, n=2)
        self.assertEqual(
            [s.title for s in render_service._scoped_hero_slides(self.store, draft_hero)], ["own-0", "own-1"],
        )

    def test_saved_section_without_own_media_falls_back_to_the_pool(self):
        draft_hero = self.active_draft().get_page("home").sections.filter(section_key="hero_banner").first()
        self.assertEqual(
            [s.title for s in render_service._scoped_hero_slides(self.store, draft_hero)],
            [f"pool-hero-{i}" for i in range(4)],
        )

    def test_banner_and_story_candidate_sections_use_the_pool_only(self):
        self.assertEqual(
            len(list(render_service._scoped_banners(self.store, StorefrontSection(section_key="multi_banner", settings={})))), 6,
        )
        ctx = render_service._story_rail_context(self.store, StorefrontSection(section_key="story_rail", settings={}))
        self.assertEqual(len(list(ctx["story_items"])), 3)


class AllReadyTemplatesTests(MediaContractBase):
    def test_gallery_has_53_ready_templates(self):
        self.assertEqual(len(lpr.list_ready_templates()), READY_TEMPLATE_COUNT)

    def test_every_template_previews_without_writes_applies_exactly_and_keeps_shared_media(self):
        templates = lpr.list_ready_templates()
        pool_before = _pool_state(self.store)
        published_before = (self.published.pk, self.published.content_fingerprint,
                            self.published.get_page("home").sections.count())
        failures = []
        templates_with_shared_media = 0
        for preset in templates:
            draft = self.active_draft()
            counts_before = (
                StorefrontSection.objects.count(), HeroSlide.objects.count(),
                PromotionalBanner.objects.count(), StoryRailItem.objects.count(),
                MediaAsset.objects.count(), StorefrontLayoutVersion.objects.count(), draft.edit_revision,
            )
            # --- candidate preview: pure read, renders through the shared pipeline
            candidate = preset_service.resolve_preset_candidate(draft, preset)
            candidate_items = render_service.build_candidate_render_items(
                candidate.pages["home"].sections, self.store, {},
            )
            counts_after_preview = (
                StorefrontSection.objects.count(), HeroSlide.objects.count(),
                PromotionalBanner.objects.count(), StoryRailItem.objects.count(),
                MediaAsset.objects.count(), StorefrontLayoutVersion.objects.count(), self.active_draft().edit_revision,
            )
            if counts_before != counts_after_preview:
                failures.append((preset.key, "preview mutated", counts_before, counts_after_preview))

            # --- real Apply
            self.switch(preset)
            draft = self.active_draft()
            home = list(draft.get_page("home").sections.order_by("order", "id"))
            # exact composition: slot keys == recipe, appearance/header/footer replaced
            recipe_keys = [e.section_key for e in preset.pages["home"]]
            applied_keys = [s.section_key for s in home]
            if not set(applied_keys) <= set(recipe_keys) | {"announcement_bar"} and sorted(applied_keys) != sorted(recipe_keys):
                failures.append((preset.key, "composition", recipe_keys, applied_keys))
            if candidate.header_config is not None and draft.header_config != candidate.header_config:
                failures.append((preset.key, "header_config differs from candidate"))
            if candidate.footer_config is not None and draft.footer_config != candidate.footer_config:
                failures.append((preset.key, "footer_config differs from candidate"))
            # The typed store-appearance manifest is the template's OWN (never the previous
            # template's); the remaining appearance keys equal the candidate's.
            manifest = (draft.appearance_config or {}).get("store_appearance") or {}
            if preset.store_appearance and (
                manifest.get("selections") != preset.store_appearance.get("selections")
                or manifest.get("settings", {}) != preset.store_appearance.get("settings", {})
            ):
                failures.append((preset.key, "store_appearance manifest is not the template's own"))
            rest_draft = {k: v for k, v in (draft.appearance_config or {}).items() if k != "store_appearance"}
            rest_candidate = {k: v for k, v in (candidate.appearance_config or {}).items() if k != "store_appearance"}
            if rest_candidate and rest_draft != rest_candidate:
                failures.append((preset.key, "appearance_config (non-manifest) differs from candidate",
                                 sorted(set(rest_draft) ^ set(rest_candidate))))

            # --- preview == applied for shared media (no ghost / duplicate rows)
            applied_media = _media_ids(render_service.build_render_items(draft, self.store))
            candidate_media = _media_ids(candidate_items)
            if candidate_media:
                templates_with_shared_media += 1
            if sorted(map(str, applied_media)) != sorted(map(str, candidate_media)):
                failures.append((preset.key, "preview media != applied media", candidate_media, applied_media))

            # --- shared media + Published untouched
            if _pool_state(self.store) != pool_before:
                failures.append((preset.key, "shared pool changed"))
            self.published.refresh_from_db()
            published_now = (self.published.pk, self.published.content_fingerprint,
                             self.published.get_page("home").sections.count())
            if published_now != published_before or self.published.status != StorefrontLayoutVersion.Status.PUBLISHED:
                failures.append((preset.key, "published changed"))

            # --- idempotent: the very same Apply again adds nothing
            n_sections = StorefrontSection.objects.count()
            n_media = (HeroSlide.objects.count(), PromotionalBanner.objects.count(),
                       StoryRailItem.objects.count(), MediaAsset.objects.count())
            self.switch(preset)
            if (StorefrontSection.objects.count(), HeroSlide.objects.count(), PromotionalBanner.objects.count(),
                    StoryRailItem.objects.count(), MediaAsset.objects.count()) != (n_sections, *n_media):
                failures.append((preset.key, "re-apply accumulated rows"))
        self.maxDiff = None
        self.assertEqual(failures, [])
        # not vacuous: media-bearing templates really rendered the shared pool
        self.assertGreater(templates_with_shared_media, 30)

    def test_returning_to_a_previous_template_applies_its_own_definition(self):
        a = lpr.get_layout_preset("aftab_price")
        b = lpr.get_layout_preset("almas_luxury")
        self.switch(b)
        home_b = [s.section_key for s in self.active_draft().get_page("home").sections.order_by("order", "id")]
        # customise the Draft, move away, come back: the template's OWN recipe returns.
        draft = self.active_draft()
        draft.get_page("home").sections.filter(section_key="rich_text").delete()
        self.switch(a)
        self.switch(b)
        home_b_again = [s.section_key for s in self.active_draft().get_page("home").sections.order_by("order", "id")]
        self.assertEqual(home_b, home_b_again)
