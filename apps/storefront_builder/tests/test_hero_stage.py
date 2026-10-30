"""Hero Stage (``hero_stage`` section) — header + hero in one composition.

Throw-away test database only. Covers: the closed vocabulary / cleaner / resolver (pure), the header-embedding decision, the live
storefront and builder Preview output (one header, inside the stage), safe fallbacks (not first, hidden on a device, independent mode),
Store scoping (media, categories, product card), security (no raw markup/CSS from settings) and backward compatibility.
"""

import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.storefront_builder import hero_stage
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service as structure
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "hs-admin-test.rastisi.localhost"
PUBLIC_HOST = "hs-public-test.example.com"


class VocabularyTests(SimpleTestCase):
    def test_every_default_is_a_member_of_its_own_choice_set(self):
        for key, _label, choices, default, _group, _visible in hero_stage.CHOICES:
            self.assertIn(default, {value for value, _l in choices}, key)

    def test_cleaner_coerces_never_raises_and_keeps_foreign_keys(self):
        cleaned = hero_stage.clean_hero_stage_settings({
            "header_mode": "evil", "bg_layout": "dual", "scrim_strength": "999", "height_desktop": "-4",
            "title": "x" * 500, "design": {"radius": 4}, "responsive": {"hide_on_mobile": False},
            "slots": [{"key": "title"}, {"key": "title"}, {"key": "nope"}, "cta", 7],
        })
        self.assertEqual(cleaned["header_mode"], "merged")           # unknown choice -> default
        self.assertEqual(cleaned["bg_layout"], "dual")
        self.assertEqual(cleaned["scrim_strength"], 90)              # clamped
        self.assertEqual(cleaned["height_desktop"], 40)
        self.assertEqual(len(cleaned["title"]), hero_stage.TEXT_MAX["title"])
        self.assertEqual(cleaned["design"], {"radius": 4})            # untouched
        self.assertEqual(cleaned["responsive"], {"hide_on_mobile": False})
        self.assertEqual([slot["key"] for slot in cleaned["slots"]], ["title", "cta"])   # de-duplicated, unknown dropped
        self.assertEqual(cleaned["v"], hero_stage.SETTINGS_VERSION)

    def test_a_junk_media_id_is_refused_and_no_picture_clears_the_field(self):
        with self.assertRaises(ValueError):
            hero_stage.clean_hero_stage_settings({"bg_a_media_asset_id": "abc"})
        with self.assertRaises(ValueError):
            hero_stage.clean_hero_stage_settings({"bg_a_media_asset_id": -3})
        self.assertNotIn("bg_a_media_asset_id", hero_stage.clean_hero_stage_settings({"bg_a_media_asset_id": None}))
        self.assertEqual(hero_stage.clean_hero_stage_settings({"bg_a_media_asset_id": "7"})["bg_a_media_asset_id"], 7)

    def test_an_absent_key_stays_absent(self):
        self.assertEqual(set(hero_stage.clean_hero_stage_settings({"title": "a"})), {"title", "v"})

    def test_resolver_never_raises_on_garbage(self):
        for garbage in (None, [], "x", {"slots": "no", "header_mode": 5, "scrim_strength": [1], "fallback_color": "javascript:1"}):
            view = hero_stage.resolve_stage_view(garbage)
            self.assertEqual(view["header_mode"], "merged")
            self.assertEqual([s["key"] for s in view["slots"]], list(hero_stage.DEFAULT_SLOTS))

    def test_style_string_is_built_only_from_numbers_and_semantic_colours(self):
        view = hero_stage.resolve_stage_view({"fallback_color": "#112233", "title": "<script>alert(1)</script>"})
        self.assertRegex(view["style"], r"^(--hs-[a-z-]+:[0-9a-z%#(),. -]+;?)+$")
        self.assertNotIn("<", view["style"])
        self.assertIn("#112233", view["style"])

    def test_header_mode_of(self):
        self.assertEqual(hero_stage.header_mode_of({"header_mode": "overlay"}), "overlay")
        self.assertEqual(hero_stage.header_mode_of({"header_mode": "x"}), "merged")
        self.assertEqual(hero_stage.header_mode_of(None), "merged")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class StageRenderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.owner = User.objects.create_user(username="hs_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin = Client(HTTP_HOST=ADMIN_HOST)
        self.admin.login(username="hs_owner", password="pass12345")
        self.public = Client(HTTP_HOST=PUBLIC_HOST)
        self.draft = svc.get_or_create_draft(self.store, user=self.owner)
        self.page = self.draft.get_page("home")
        self.page.containers.all().delete()
        self.page.sections.all().delete()

    # ---- helpers ----------------------------------------------------------------------------------------------------------
    def _stage(self, **settings):
        section = structure.add_section(draft=self.draft, section_key="hero_stage", page_type="home")
        section.settings = hero_stage.clean_hero_stage_settings({**hero_stage.default_settings(), **settings})
        section.save(update_fields=["settings"])
        return section

    def _publish(self):
        svc.publish(self.store)
        cache.clear()

    def _live(self):
        return self.public.get(reverse("catalog:home")).content.decode()

    def _preview(self):
        return self.admin.get(reverse("dashboard:storefront-builder-preview")).content.decode()

    @staticmethod
    def _stage_html(body):
        match = re.search(r'<section class="hs-stage".*?</section>', body, re.S)
        return match.group(0) if match else ""

    # ---- the stage itself -------------------------------------------------------------------------------------------------
    def test_merged_stage_renders_the_single_real_header_inside_itself(self):
        self._stage(title="تیتر آزمایشی", button_label="بخرید")
        self._publish()
        body = self._live()
        stage = self._stage_html(body)
        self.assertTrue(stage, "the stage must render")
        self.assertIn('data-hs-header="merged"', stage)
        self.assertEqual(body.count("<header"), 1, "exactly one header on the page")
        self.assertIn("<header", stage)                       # ...and it lives inside the stage
        self.assertIn("تیتر آزمایشی", stage)
        self.assertIn("بخرید", stage)

    def test_preview_and_live_agree(self):
        self._stage(title="هم‌خوانی")
        self._publish()
        live, preview = self._live(), self._preview()
        for body in (live, preview):
            self.assertEqual(body.count("<header"), 1)
            self.assertIn("<header", self._stage_html(body))
            self.assertIn("هم‌خوانی", body)

    def test_independent_mode_keeps_the_shell_header(self):
        self._stage(header_mode="independent")
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("<header", self._stage_html(body))   # the header is the shell's, outside the stage

    def test_overlay_mode_marks_the_stage(self):
        self._stage(header_mode="overlay")
        self._publish()
        stage = self._stage_html(self._live())
        self.assertIn('data-hs-header="overlay"', stage)
        self.assertIn("<header", stage)

    def test_a_page_without_a_stage_is_unchanged(self):
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("hs-stage", body)

    def test_stage_not_first_falls_back_to_the_shell_header(self):
        first = structure.add_section(draft=self.draft, section_key="rich_text", page_type="home")
        self.assertIsNotNone(first)
        self._stage()
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("<header", self._stage_html(body))

    def test_a_stage_hidden_on_a_device_never_swallows_the_header(self):
        section = self._stage()
        section.settings = {**section.settings, "responsive": {"hide_on_mobile": True}}
        section.save(update_fields=["settings"])
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("<header", self._stage_html(body))

    def test_other_pages_keep_their_shell_header(self):
        self._stage()
        self._publish()
        response = self.public.get(reverse("catalog:product-list"))
        body = response.content.decode()
        self.assertEqual(body.count("<header"), 1)
        self.assertNotIn("hs-stage", body)

    def test_ordered_slots_follow_the_merchant_order_and_hidden_flags(self):
        self._stage(
            eyebrow="کوچک", title="بزرگ", subtitle="توضیح", button_label="برو",
            slots=[{"key": "cta"}, {"key": "title", "hide_mobile": True}, {"key": "eyebrow"}],
        )
        self._publish()
        stage = self._stage_html(self._live())
        self.assertLess(stage.index("hs-slot hs-cta-wrap"), stage.index("hs-slot hs-title"))
        self.assertLess(stage.index("hs-slot hs-title"), stage.index("hs-slot hs-eyebrow"))
        self.assertNotIn("hs-slot hs-subtitle", stage)        # not in the arranged list -> not rendered
        self.assertRegex(stage, r'<h1 class="hs-slot hs-title"[^>]*data-hs-hide-m')

    def test_markup_in_text_settings_is_escaped(self):
        self._stage(title="<img src=x onerror=alert(1)>", subtitle="<script>1</script>")
        self._publish()
        stage = self._stage_html(self._live())
        self.assertNotIn("<img src=x", stage)
        self.assertNotIn("<script>1", stage)
        self.assertIn("&lt;img src=x", stage)

    def test_categories_and_product_card_come_from_this_store(self):
        self._stage(slots=[{"key": "title"}, {"key": "categories"}, {"key": "product_card"}], category_limit=4)
        self._publish()
        stage = self._stage_html(self._live())
        self.assertIn("hs-cats", stage)
        self.assertIn("همه کالاها", stage)
        own = list(Category.objects.filter(store=self.store, is_active=True, parent__isnull=True).values_list("slug", flat=True)[:4])
        for slug in own:
            self.assertIn(f"category={slug}", stage)
        foreign = Category.objects.exclude(store=self.store).values_list("slug", flat=True)[:5]
        own_all = set(Category.objects.filter(store=self.store).values_list("slug", flat=True))
        for slug in foreign:
            if slug not in own_all:
                self.assertNotIn(f"category={slug}", stage)
        if Product.objects.filter(store=self.store).exists():
            self.assertIn("hs-card", stage)

    def test_cta_without_a_destination_points_to_the_real_catalog(self):
        self._stage(button_label="مشاهده")
        self._publish()
        stage = self._stage_html(self._live())
        self.assertIn(f'href="{reverse("catalog:product-list")}"', stage)

    def test_a_stage_in_a_page_without_content_still_renders_the_header(self):
        self._stage(title="", subtitle="", button_label="", eyebrow="")
        self._publish()
        body = self._live()
        self.assertEqual(body.count("<header"), 1)
        self.assertIn("<header", self._stage_html(body))
