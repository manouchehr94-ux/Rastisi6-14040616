"""Store-wide DEFAULT media (demo hero images) in the R4 media manager.

Root cause under test: the demo seeds (and the legacy dashboard screen) create
STORE-WIDE rows (``section IS NULL``). The renderer shows a section's own ACTIVE
items when it has any and otherwise FALLS BACK to those store-wide rows, but the
manager lists only the section's own items — so the demo images were invisible
and un-editable there, and the first managed slide silently hid them all.

The repair (``services/media_defaults_service.py``) makes the fallback visible
and adds an explicit, non-destructive "make editable" copy action. It changes
nothing about what the renderer picks.
"""
import re

from django.urls import reverse

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.stores.models import Store

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import media_defaults_service as mds
from apps.storefront_builder.services.render_service import (
    _scoped_banners, _scoped_hero_slides, _story_rail_context,
)

from .test_media_views import MediaViewsTestCase, _img

INLINE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_R4_INLINE": "1"}
DEMO = ["دمو ۱", "دمو ۲", "دمو ۳"]


class _DefaultsBase(MediaViewsTestCase):
    def make_defaults(self, titles=DEMO, store=None, **extra):
        """What the demo seeds create: STORE-WIDE rows with a legacy file only."""
        store = store or self.store
        rows = []
        for i, title in enumerate(titles):
            rows.append(HeroSlide.objects.create(
                store=store, section=None, title=title, subtitle=f"زیر {i}", display_order=i,
                desktop_image=_img(f"demo{i}.png"), is_active=True, show_button=True,
                button_label="خرید", destination_type="search", **extra,
            ))
        return rows

    def url(self, name, *args):
        return reverse(f"dashboard:storefront-builder-section-media-{name}", args=args)

    def list_html(self, section=None, kind="hero-slides", inline=True):
        section = section or self.hero_section
        url = self.url("list", section.pk, kind)
        return (self.client.get(url, **INLINE) if inline else self.client.get(url)).content.decode()

    def adopt(self, section=None, kind="hero-slides", inline=True):
        section = section or self.hero_section
        url = self.url("adopt-defaults", section.pk, kind)
        return self.client.post(url, **INLINE) if inline else self.client.post(url)

    def add_own(self, title, section=None):
        section = section or self.hero_section
        return self.client.post(
            self.url("add", section.pk, "hero-slides"),
            {"title": title, "desktop_image": _img(), "is_active": "on", "destination_type": "none"}, **INLINE,
        )

    def rendered(self, section=None):
        return [s.title for s in _scoped_hero_slides(self.store, section or self.hero_section)]

    def own(self, section=None):
        return list(HeroSlide.objects.filter(section=section or self.hero_section).order_by("display_order", "id"))


class DemoStoreOnlyDefaultsTests(_DefaultsBase):
    """1. A demo store with only default hero images."""

    def test_renderer_shows_the_store_wide_defaults(self):
        self.make_defaults()
        self.assertEqual(self.rendered(), DEMO)

    def test_manager_lists_the_defaults_read_only_with_an_explicit_action(self):
        self.make_defaults()
        html = self.list_html()
        self.assertIn("data-r4-media-defaults", html)
        for title in DEMO:
            self.assertIn(title, html)
        self.assertIn("تصاویر پیش‌فرض فروشگاه (3)", html)
        self.assertIn(self.url("adopt-defaults", self.hero_section.pk, "hero-slides"), html)
        self.assertIn("data-r4-media-adopt", html)
        self.assertIn("hx-confirm=", html)  # explicit: asks before copying anything
        self.assertNotIn("هنوز هیچ اسلایدی", html)  # no misleading empty state
        block = html.split("data-r4-media-defaults", 1)[1]
        self.assertNotIn("data-r4-media-open", block)  # the defaults are NOT directly editable rows
        self.assertNotIn("/edit/", html)

    def test_listing_does_not_change_anything(self):
        rows = self.make_defaults()
        self.list_html()
        self.assertEqual(HeroSlide.objects.filter(section__isnull=True).count(), 3)
        self.assertEqual(self.own(), [])
        self.assertEqual(MediaAsset.objects.count(), 0)
        for row in rows:
            row.refresh_from_db()
            self.assertIsNone(row.section_id)

    def test_only_active_store_wide_rows_are_shown(self):
        rows = self.make_defaults()
        HeroSlide.objects.filter(pk=rows[1].pk).update(is_active=False)
        html = self.list_html()
        self.assertIn("(2)", html)
        self.assertNotIn(rows[1].title, html)
        self.assertEqual(self.rendered(), ["دمو ۱", "دمو ۳"])  # exactly what the renderer shows

    def test_no_defaults_keeps_the_original_empty_state(self):
        html = self.list_html()
        self.assertNotIn("data-r4-media-defaults", html)
        self.assertIn("هنوز هیچ اسلایدی", html)

    def test_add_form_warns_that_the_defaults_will_be_hidden(self):
        self.make_defaults()
        html = self.client.get(self.url("add", self.hero_section.pk, "hero-slides"), **INLINE).content.decode()
        self.assertIn("data-r4-media-defaults-notice", html)
        self.assertIn("3 تصویر پیش‌فرض", html)
        self.assertIn("پیش‌فرض‌ها پنهان می‌شوند", html)
        legacy = self.client.get(self.url("add", self.hero_section.pk, "hero-slides")).content.decode()
        self.assertIn("data-r4-media-defaults-notice", legacy)

    def test_notice_is_absent_without_defaults_and_on_edit(self):
        add = self.url("add", self.hero_section.pk, "hero-slides")
        self.assertNotIn("data-r4-media-defaults-notice", self.client.get(add, **INLINE).content.decode())
        self.make_defaults()
        own = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="من", desktop_image=_img(), is_active=False)
        edit = self.url("edit", self.hero_section.pk, "hero-slides", own.pk)
        self.assertNotIn("data-r4-media-defaults-notice", self.client.get(edit, **INLINE).content.decode())

    def test_state_helper_matches_the_renderer_for_every_kind(self):
        """The helper must use exactly the renderer's fallback condition."""
        HeroSlide.objects.create(store=self.store, section=None, title="h", desktop_image=_img(), is_active=True)
        PromotionalBanner.objects.create(store=self.store, section=None, title="b", desktop_image=_img(), is_active=True)
        StoryRailItem.objects.create(store=self.store, section=None, title="s", image=_img(), is_active=True)
        cases = [
            (HeroSlide, self.hero_section, [x.pk for x in _scoped_hero_slides(self.store, self.hero_section)]),
            (PromotionalBanner, self.banner_section, [x.pk for x in _scoped_banners(self.store, self.banner_section)]),
            (StoryRailItem, self.story_section, [x.pk for x in _story_rail_context(self.store, self.story_section)["story_items"]]),
        ]
        for model, section, renderer_ids in cases:
            with self.subTest(model=model.__name__):
                state = mds.default_media_state(section, model)
                self.assertTrue(state.in_effect)
                self.assertEqual([x.pk for x in state.items], renderer_ids)

    def test_unsaved_or_missing_section_is_inert(self):
        self.assertFalse(mds.default_media_state(None, HeroSlide).in_effect)
        self.assertFalse(mds.default_media_state(StorefrontSection(section_key="hero_banner"), HeroSlide).in_effect)


class FirstManagedSlideTests(_DefaultsBase):
    """2 + 3. The first, and several, merchant-created slides (behaviour documented, not changed)."""

    def test_first_own_slide_replaces_the_defaults_in_the_renderer(self):
        defaults = self.make_defaults()
        self.assertEqual(self.add_own("من ۱").status_code, 200)
        self.assertEqual(self.rendered(), ["من ۱"])
        # ...but nothing was lost: the store-wide rows are untouched and recoverable.
        for row in defaults:
            row.refresh_from_db()
            self.assertTrue(row.is_active)
            self.assertIsNone(row.section_id)

    def test_list_stops_showing_the_defaults_block_once_there_are_own_slides(self):
        self.make_defaults()
        self.add_own("من ۱")
        html = self.list_html()
        self.assertNotIn("data-r4-media-defaults", html)
        self.assertIn("من ۱", html)

    def test_several_own_slides_render_in_order_and_defaults_stay_hidden(self):
        self.make_defaults()
        for title in ("من ۱", "من ۲", "من ۳"):
            self.add_own(title)
        self.assertEqual(self.rendered(), ["من ۱", "من ۲", "من ۳"])
        self.assertEqual([s.display_order for s in self.own()], [0, 1, 2])


class AdoptDefaultsTests(_DefaultsBase):
    """4. Editing / replacing an existing default image."""

    def setUp(self):
        super().setUp()
        self.defaults = self.make_defaults()

    def test_adopt_copies_defaults_as_normal_editable_slides_without_visible_change(self):
        before = self.rendered()
        resp = self.adopt()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["HX-Trigger"], "r4:media-changed")
        copies = self.own()
        self.assertEqual([c.title for c in copies], DEMO)
        self.assertEqual(self.rendered(), before)  # identical output before and after
        for copy, original in zip(copies, self.defaults):
            self.assertEqual(
                (copy.subtitle, copy.button_label, copy.show_button, copy.destination_type, copy.is_active),
                (original.subtitle, original.button_label, original.show_button, original.destination_type, True),
            )
        # the list now shows ordinary, editable rows and no defaults block
        html = resp.content.decode()
        self.assertNotIn("data-r4-media-defaults", html)
        self.assertEqual(len(re.findall(r'data-r4-media-open="[^"]*/edit/"', html)), 3)
        self.assertIn("/edit/", html)

    def test_adopt_reuses_the_stored_files_through_media_assets_and_copies_no_bytes(self):
        stored = [r.desktop_image.name for r in self.defaults]
        self.adopt()
        copies = self.own()
        self.assertEqual(MediaAsset.objects.count(), 3)
        for copy, name in zip(copies, stored):
            self.assertIsNotNone(copy.desktop_asset_id)
            self.assertEqual(copy.desktop_asset.image.name, name)  # the SAME file, not a copy
            self.assertEqual(copy.desktop_asset.store_id, self.store.pk)
            self.assertEqual(copy.desktop_image_url, self.defaults[copies.index(copy)].desktop_image_url)

    def test_adopt_never_modifies_the_originals(self):
        snapshot = [(r.pk, r.title, r.is_active, r.display_order, r.desktop_image.name, r.section_id,
                     r.desktop_asset_id) for r in self.defaults]
        self.adopt()
        for row, snap in zip(self.defaults, snapshot):
            row.refresh_from_db()
            self.assertEqual((row.pk, row.title, row.is_active, row.display_order, row.desktop_image.name,
                              row.section_id, row.desktop_asset_id), snap)
        self.assertEqual(HeroSlide.objects.filter(section__isnull=True).count(), 3)

    def test_adopt_is_idempotent_and_a_double_submit_is_harmless(self):
        self.adopt()
        again = self.adopt()
        self.assertEqual(again.status_code, 200)
        self.assertNotIn("HX-Trigger", again.headers)  # nothing changed -> no draft-changed signal
        self.assertEqual(len(self.own()), 3)
        self.assertEqual(MediaAsset.objects.count(), 3)

    def test_adopt_requires_post(self):
        resp = self.client.get(self.url("adopt-defaults", self.hero_section.pk, "hero-slides"))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(len(self.own()), 0)

    def test_adopt_skips_a_default_with_no_image(self):
        HeroSlide.objects.create(store=self.store, section=None, title="بدون تصویر", display_order=9, is_active=True)
        result = mds.adopt_store_defaults(
            self.hero_section, model=HeroSlide, related_name="hero_slides",
            asset_fields={"desktop_image": "desktop_asset", "mobile_image": "mobile_asset"},
        )
        self.assertEqual((result.created, result.skipped), (3, 1))
        self.assertNotIn("بدون تصویر", [c.title for c in self.own()])

    def test_replace_one_adopted_image_leaves_the_others_untouched(self):
        self.adopt()
        first, second, third = self.own()
        keep = (second.desktop_asset_id, third.desktop_asset_id)
        resp = self.client.post(
            self.url("edit", self.hero_section.pk, "hero-slides", second.pk),
            {"title": "دمو ۲ — جایگزین", "subtitle": "x", "desktop_image": _img("replacement.png"),
             "is_active": "on", "destination_type": "none"}, **INLINE,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        first.refresh_from_db(), second.refresh_from_db(), third.refresh_from_db()
        self.assertEqual(second.title, "دمو ۲ — جایگزین")
        self.assertIn("replacement", second.desktop_asset.image.name)
        self.assertNotEqual(second.desktop_asset_id, keep[0])
        self.assertEqual((first.title, third.title), ("دمو ۱", "دمو ۳"))
        self.assertEqual(third.desktop_asset_id, keep[1])
        self.assertEqual(self.rendered(), ["دمو ۱", "دمو ۲ — جایگزین", "دمو ۳"])  # no image lost
        # the shared store-wide originals are still exactly what they were
        self.assertEqual(sorted(HeroSlide.objects.filter(section__isnull=True).values_list("title", flat=True)), DEMO)

    def test_edit_without_a_new_file_keeps_the_adopted_image(self):
        """The adopted copy is asset-backed with no legacy file: editing only text must still save."""
        self.adopt()
        target = self.own()[0]
        asset_id = target.desktop_asset_id
        resp = self.client.post(
            self.url("edit", self.hero_section.pk, "hero-slides", target.pk),
            {"title": "عنوان تازه", "is_active": "on", "destination_type": "none"}, **INLINE,
        )
        self.assertEqual(resp.status_code, 200)
        target.refresh_from_db()
        self.assertEqual((target.title, target.desktop_asset_id), ("عنوان تازه", asset_id))

    def test_adoption_works_for_banners_and_story_items_too(self):
        PromotionalBanner.objects.create(store=self.store, section=None, title="بنر پیش‌فرض", desktop_image=_img(), is_active=True)
        StoryRailItem.objects.create(store=self.store, section=None, title="استوری پیش‌فرض", image=_img(), is_active=True)
        self.assertEqual(self.adopt(self.banner_section, "banners").status_code, 200)
        self.assertEqual(self.adopt(self.story_section, "story-items").status_code, 200)
        banner = PromotionalBanner.objects.get(section=self.banner_section)
        story = StoryRailItem.objects.get(section=self.story_section)
        self.assertEqual((banner.title, story.title), ("بنر پیش‌فرض", "استوری پیش‌فرض"))
        self.assertIsNotNone(banner.desktop_asset_id)
        self.assertIsNotNone(story.image_asset_id)
        self.assertEqual([b.title for b in _scoped_banners(self.store, self.banner_section)], ["بنر پیش‌فرض"])

    def test_legacy_full_page_adopt_redirects_back_to_the_list(self):
        resp = self.adopt(inline=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(self.own()), 3)
        self.assertNotIn("data-r4-media-defaults", self.list_html(inline=False))

    def test_legacy_full_page_list_also_shows_the_defaults_and_the_action(self):
        html = self.list_html(inline=False)
        self.assertIn("data-r4-media-defaults", html)
        self.assertIn("data-r4-media-adopt", html)


class ActivationAndOrderingTests(_DefaultsBase):
    """5 + 6. Activation, deactivation and ordering after adoption."""

    def setUp(self):
        super().setUp()
        self.make_defaults()
        self.adopt()
        self.copies = self.own()

    def toggle(self, item):
        return self.client.post(self.url("toggle", self.hero_section.pk, "hero-slides", item.pk), **INLINE)

    def move(self, item, direction):
        return self.client.post(
            self.url("move", self.hero_section.pk, "hero-slides", item.pk), {"direction": direction}, **INLINE,
        )

    def test_deactivating_one_adopted_slide_removes_only_that_slide(self):
        self.toggle(self.copies[1])
        self.assertEqual(self.rendered(), ["دمو ۱", "دمو ۳"])
        self.toggle(self.copies[1])
        self.assertEqual(self.rendered(), DEMO)

    def test_deactivating_every_own_slide_brings_the_defaults_back_and_the_list_says_so(self):
        for copy in self.copies:
            self.toggle(copy)
        self.assertEqual([s.pk for s in _scoped_hero_slides(self.store, self.hero_section)],
                         [r.pk for r in HeroSlide.objects.filter(section__isnull=True).order_by("display_order", "id")])
        html = self.list_html()
        self.assertIn("data-r4-media-defaults", html)
        self.assertIn("غیرفعال‌اند", html)  # the "all inactive" explanation
        self.assertEqual(len(re.findall(r'data-r4-media-open="[^"]*/edit/"', html)), 3)  # inactive own slides stay listed/editable

    def test_toggle_response_refreshes_the_defaults_block(self):
        self.toggle(self.copies[0]), self.toggle(self.copies[1])
        resp = self.toggle(self.copies[2])  # last active one -> defaults reappear immediately
        self.assertIn("data-r4-media-defaults", resp.content.decode())

    def test_reactivating_one_hides_the_defaults_again(self):
        for copy in self.copies:
            self.toggle(copy)
        self.toggle(self.copies[0])
        self.assertNotIn("data-r4-media-defaults", self.list_html())
        self.assertEqual(self.rendered(), ["دمو ۱"])

    def test_adopting_while_all_inactive_appends_after_the_existing_items(self):
        for copy in self.copies:
            self.toggle(copy)
        self.assertEqual(self.adopt().status_code, 200)
        orders = [s.display_order for s in self.own()]
        self.assertEqual(orders, [0, 1, 2, 3, 4, 5])  # continues after the existing items, no collisions
        self.assertEqual(self.rendered(), DEMO)  # the three new active copies are what is shown

    def test_reordering_adopted_slides_changes_the_rendered_order(self):
        self.move(self.copies[0], "down")
        self.assertEqual(self.rendered(), ["دمو ۲", "دمو ۱", "دمو ۳"])
        self.move(self.copies[0], "up")
        self.assertEqual(self.rendered(), DEMO)

    def test_a_slide_added_after_adoption_goes_last(self):
        self.add_own("جدید")
        self.assertEqual(self.rendered(), DEMO + ["جدید"])
        self.assertEqual([s.display_order for s in self.own()], [0, 1, 2, 3])


class DraftVersusPublishedTests(_DefaultsBase):
    """7. Draft preview versus the published storefront."""

    def test_adopting_in_the_draft_does_not_change_the_published_storefront_until_publish(self):
        self.make_defaults()
        published = svc.publish(self.store)
        pub_section = StorefrontSection.objects.get(page__version=published, stable_id=self.hero_section.stable_id)
        draft = svc.get_or_create_draft(self.store)
        draft_section = StorefrontSection.objects.get(page__version=draft, stable_id=self.hero_section.stable_id)
        self.assertNotEqual(draft_section.pk, pub_section.pk)

        self.assertEqual(self.client.post(self.url("adopt-defaults", draft_section.pk, "hero-slides"), **INLINE).status_code, 200)

        # draft preview: its own (adopted) copies; published storefront: still the store-wide defaults
        draft_rows = list(_scoped_hero_slides(self.store, draft_section))
        self.assertEqual([r.title for r in draft_rows], DEMO)
        self.assertTrue(all(r.section_id == draft_section.pk for r in draft_rows))
        pub_rows = list(_scoped_hero_slides(self.store, pub_section))
        self.assertEqual([r.title for r in pub_rows], DEMO)
        self.assertTrue(all(r.section_id is None for r in pub_rows))
        self.assertFalse(HeroSlide.objects.filter(section=pub_section).exists())

    def test_publishing_clones_the_adopted_slides_into_the_published_version(self):
        """Publish only clones asset-backed Placements — adoption must make them asset-backed."""
        self.make_defaults()
        self.adopt()
        published = svc.publish(self.store)
        pub_section = StorefrontSection.objects.get(page__version=published, stable_id=self.hero_section.stable_id)
        cloned = list(HeroSlide.objects.filter(section=pub_section).order_by("display_order", "id"))
        self.assertEqual([c.title for c in cloned], DEMO)
        self.assertTrue(all(c.desktop_asset_id for c in cloned))
        self.assertEqual([r.title for r in _scoped_hero_slides(self.store, pub_section)], DEMO)

    def test_edits_after_adoption_reach_the_published_storefront_only_on_publish(self):
        self.make_defaults()
        self.adopt()
        pub1 = svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        draft_section = StorefrontSection.objects.get(page__version=draft, stable_id=self.hero_section.stable_id)
        target = HeroSlide.objects.filter(section=draft_section).order_by("display_order").first()
        self.client.post(
            self.url("edit", draft_section.pk, "hero-slides", target.pk),
            {"title": "عنوان تغییرکرده", "is_active": "on", "destination_type": "none"}, **INLINE,
        )
        pub1_section = StorefrontSection.objects.get(page__version=pub1, stable_id=self.hero_section.stable_id)
        self.assertEqual(self.rendered(pub1_section)[0], "دمو ۱")  # published unchanged
        self.assertEqual([r.title for r in _scoped_hero_slides(self.store, draft_section)][0], "عنوان تغییرکرده")
        pub2 = svc.publish(self.store)
        pub2_section = StorefrontSection.objects.get(page__version=pub2, stable_id=self.hero_section.stable_id)
        self.assertEqual(self.rendered(pub2_section)[0], "عنوان تغییرکرده")


class ExistingManagedStoresTests(_DefaultsBase):
    """8. A store that already has its own managed slides keeps its behaviour."""

    def setUp(self):
        super().setUp()
        self.make_defaults()
        self.add_own("اختصاصی ۱")
        self.add_own("اختصاصی ۲")

    def test_renderer_and_list_are_unchanged(self):
        self.assertEqual(self.rendered(), ["اختصاصی ۱", "اختصاصی ۲"])
        html = self.list_html()
        self.assertNotIn("data-r4-media-defaults", html)
        self.assertNotIn("data-r4-media-adopt", html)
        self.assertEqual(len(re.findall(r'data-r4-media-open="[^"]*/edit/"', html)), 2)

    def test_adopt_is_a_no_op_for_them(self):
        resp = self.adopt()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Trigger", resp.headers)
        self.assertEqual([s.title for s in self.own()], ["اختصاصی ۱", "اختصاصی ۲"])
        self.assertEqual(self.rendered(), ["اختصاصی ۱", "اختصاصی ۲"])

    def test_add_form_has_no_defaults_notice(self):
        html = self.client.get(self.url("add", self.hero_section.pk, "hero-slides"), **INLINE).content.decode()
        self.assertNotIn("data-r4-media-defaults-notice", html)


class StoreIsolationTests(_DefaultsBase):
    """9. Store isolation."""

    def setUp(self):
        super().setUp()
        self.other = Store.objects.create(name="فروشگاه دیگر", slug="other-defaults")
        self.make_defaults(["دمو من"], store=self.store)
        self.other_defaults = self.make_defaults(["دموی دیگران"], store=self.other)

    def test_only_this_stores_defaults_are_shown_and_rendered(self):
        html = self.list_html()
        self.assertIn("دمو من", html)
        self.assertNotIn("دموی دیگران", html)
        self.assertEqual(self.rendered(), ["دمو من"])

    def test_adopt_copies_only_this_stores_rows(self):
        self.adopt()
        self.assertEqual([c.title for c in self.own()], ["دمو من"])
        self.assertTrue(all(c.store_id == self.store.pk for c in self.own()))
        self.assertTrue(all(a.store_id == self.store.pk for a in MediaAsset.objects.all()))
        other = self.other_defaults[0]
        other.refresh_from_db()
        self.assertEqual((other.store_id, other.section_id, other.is_active), (self.other.pk, None, True))
        self.assertEqual(HeroSlide.objects.filter(store=self.other).count(), 1)

    def test_a_section_of_another_store_cannot_be_adopted_from_this_store(self):
        foreign_draft = svc.get_or_create_draft(self.other)
        foreign = StorefrontSection.objects.create(version=foreign_draft, section_key="hero_banner", order=900)
        resp = self.client.post(self.url("adopt-defaults", foreign.pk, "hero-slides"), **INLINE)
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(HeroSlide.objects.filter(section=foreign).exists())
        self.assertEqual(HeroSlide.objects.filter(store=self.other, section__isnull=True).count(), 1)

    def test_state_is_scoped_to_the_sections_own_store(self):
        foreign_draft = svc.get_or_create_draft(self.other)
        foreign = StorefrontSection.objects.create(version=foreign_draft, section_key="hero_banner", order=901)
        state = mds.default_media_state(foreign, HeroSlide)
        self.assertEqual([r.title for r in state.items], ["دموی دیگران"])
