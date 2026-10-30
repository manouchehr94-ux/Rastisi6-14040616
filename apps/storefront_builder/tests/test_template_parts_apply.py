"""Header-only and Hero-only from a Ready Template (``header.apply_template`` / ``hero.apply_template``).

A merchant can take ONE part of a template without re-applying the whole thing: the header of template B, or the Hero Stage look of template C.
Each is a normal R4 mutation (one revision, one Undo/Redo step, Draft only, Store-scoped) built on the existing validated header path and
the stage recipe — no template key is ever named by the engine. Throw-away database only."""

import json
import re

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import MediaAsset
from apps.storefront_builder import hero_stage
from apps.storefront_builder.models import StorefrontLayout
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

from .test_hero_stage_templates import PUBLIC_A, _png
from .test_r4_mutation_api import R4MutationApiTestCase



def _version(key):
    from apps.storefront_builder import layout_preset_registry as lpr
    return lpr.get_layout_preset(key).version


def _strip_csrf(html):
    return re.sub(r'(csrfmiddlewaretoken" value=")[^"]+', r"\1", html)


@override_settings(ALLOWED_HOSTS=["*"])
class TemplatePartsApplyTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=PUBLIC_A)
        self.asset = MediaAsset.objects.create(store=self.store, image=_png("parts-a.png", (200, 80, 80)))
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="parts-other", admin_subdomain="parts-other", status=Store.Status.ACTIVE)

    # ------------------------------------------------------------------------------------------------------------ helpers
    def _draft(self):
        return svc.get_or_create_draft(self.store, user=self.staff)

    def _apply_whole(self, key):
        response = self.client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": key, "confirm_preset_apply": "1"})
        self.assertEqual(response.status_code, 302, key)

    def _mutate(self, mutation, *, expect=200):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "mutation": mutation}), content_type="application/json",
        )
        self.assertEqual(response.status_code, expect, response.content[:400])
        return response

    def _history(self, command):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._draft().edit_revision, "command": command}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])

    def _header(self, key):
        return self._apply_header(key)

    def _apply_header(self, key, *, expect=200):
        return self._mutate({"type": "header.apply_template", "template_key": key, "template_version": _version(key)}, expect=expect)

    def _apply_hero(self, key, *, expect=200):
        return self._mutate({"type": "hero.apply_template", "template_key": key, "template_version": _version(key)}, expect=expect)

    def _home(self):
        return [(s.section_key, s.pk) for s in self._draft().get_page("home").sections.order_by("order", "id")]

    def _stage(self):
        return self._draft().get_page("home").sections.get(section_key=hero_stage.SECTION_KEY)

    def _variant(self):
        return self._draft().effective_header_config()["header_variant"]

    def _publish(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps({"base_revision": self._draft().edit_revision}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        cache.clear()

    # ------------------------------------------------------------------------------------------------------------ header only
    def test_header_only_changes_the_header_and_nothing_else(self):
        self._apply_whole("dual_atelier")
        sections_before, stage_before = self._home(), dict(self._stage().settings)
        footer_before = self._draft().effective_footer_config()
        before_revision = self._draft().edit_revision
        self.assertEqual(self._variant(), "atelier_nav")

        self._apply_header("editorial_noir")

        self.assertEqual(self._variant(), "editorial_masthead")
        self.assertEqual(self._home(), sections_before, "no section added, removed or re-created")
        self.assertEqual(self._stage().settings, stage_before, "the hero is untouched")
        self.assertEqual(self._draft().effective_footer_config(), footer_before)
        self.assertEqual(self._draft().edit_revision, before_revision + 1, "exactly one revision")

    def test_header_only_keeps_the_merchants_announcement_bar(self):
        self._apply_whole("dual_atelier")
        self._mutate({"type": "header.update", "patch": {"announcement_enabled": True, "announcement_text": "ارسال رایگان امروز"}})
        self._apply_header("glass_commerce")
        config = self._draft().effective_header_config()
        self.assertEqual(config["announcement_text"], "ارسال رایگان امروز")
        self.assertTrue(config["announcement_enabled"], "a template's style never switches the merchant's message off")
        self.assertEqual(config["header_variant"], "centered_brand")

    def test_header_only_from_a_pre_existing_template_works_on_a_stage_template(self):
        self._apply_whole("asymmetric_canvas")
        self._apply_header("premium_leather")                              # a legacy Ready Template: only its header is taken
        self.assertEqual(self._variant(), "editorial_row")
        self.assertEqual(self._stage().settings["header_mode"], "overlay", "the stage keeps its own header mode")

    def test_header_only_is_one_undo_and_redo_step(self):
        self._apply_whole("dual_atelier")
        self._apply_header("editorial_noir")
        self._history("undo")
        self.assertEqual(self._variant(), "atelier_nav")
        self._history("redo")
        self.assertEqual(self._variant(), "editorial_masthead")

    # ------------------------------------------------------------------------------------------------------------ hero only
    def test_hero_only_takes_the_look_and_keeps_the_merchants_words_pictures_and_header(self):
        self._apply_whole("dual_atelier")
        stage = self._stage()
        stage.settings = {**stage.settings, "title": "تیتر خودِ فروشنده", "button_label": "برو به فروشگاه",
                          "bg_a_media_asset_id": self.asset.pk, "bg_a_focal_x": 30}
        stage.save(update_fields=["settings"])
        sections_before, variant_before = self._home(), self._variant()

        self._apply_hero("asymmetric_canvas")

        settings = self._stage().settings
        self.assertEqual((settings["header_mode"], settings["bg_layout"], settings["bg_split"]), ("overlay", "dual", "first_dominant"))
        self.assertEqual(settings["title"], "تیتر خودِ فروشنده")
        self.assertEqual(settings["button_label"], "برو به فروشگاه")
        self.assertEqual(settings["bg_a_media_asset_id"], self.asset.pk)
        self.assertEqual(settings["bg_a_focal_x"], 30)
        self.assertEqual(self._variant(), variant_before, "the Store's header is not part of the hero")
        self.assertEqual(self._home(), sections_before)

    def test_hero_only_is_one_undo_and_redo_step(self):
        self._apply_whole("dual_atelier")
        before = dict(self._stage().settings)
        self._apply_hero("editorial_noir")
        changed = dict(self._stage().settings)
        self.assertNotEqual(changed["bg_layout"], before["bg_layout"])
        self._history("undo")
        self.assertEqual(self._stage().settings, before)
        self._history("redo")
        self.assertEqual(self._stage().settings, changed)

    def test_hero_only_adds_a_stage_at_the_top_when_the_page_has_none(self):
        self._apply_whole("premium_leather")                               # a legacy template: slider hero, no stage
        before = self._home()
        self.assertFalse(any(key == hero_stage.SECTION_KEY for key, _pk in before))
        self._apply_hero("glass_commerce")
        after = self._home()
        self.assertEqual(after[0][0], hero_stage.SECTION_KEY, "the new stage is the first block of the page")
        self.assertEqual(after[1:], before, "every existing section is still there, in the same order")
        self.assertEqual(self._stage().settings["content_frame"], "none")

    def test_hero_only_from_a_template_without_a_stage_is_refused_and_changes_nothing(self):
        self._apply_whole("dual_atelier")
        revision, stage = self._draft().edit_revision, dict(self._stage().settings)
        response = self._apply_hero("premium_leather", expect=400)
        self.assertEqual(response.json().get("code") or response.json().get("error"), "template_has_no_hero_stage")
        self.assertEqual(self._draft().edit_revision, revision)
        self.assertEqual(self._stage().settings, stage)

    def test_a_locked_stage_is_not_overwritten(self):
        self._apply_whole("dual_atelier")
        stage = self._stage()
        stage.is_locked = True
        stage.save(update_fields=["is_locked"])
        before = dict(stage.settings)
        self._apply_hero("editorial_noir", expect=400)
        self.assertEqual(self._stage().settings, before)

    def test_unknown_template_and_version_mismatch_are_refused(self):
        self._apply_whole("dual_atelier")
        self._mutate({"type": "header.apply_template", "template_key": "nope", "template_version": "1"}, expect=400)
        self._mutate({"type": "hero.apply_template", "template_key": "editorial_noir", "template_version": "99"}, expect=400)

    # ------------------------------------------------------------------------------------------------------------ recombination
    def test_template_a_with_the_header_of_b_and_the_hero_of_c_renders_as_one_composition(self):
        self._apply_whole("dual_atelier")
        self._apply_header("glass_commerce")
        self._apply_hero("editorial_noir")
        self._publish()
        live = self.public.get(reverse("catalog:home")).content.decode()
        stage = re.search(r'<section class="hs-stage".*?</section>', live, re.S).group(0)
        self.assertEqual(live.count("<header"), 1, "one header, never two")
        self.assertIn("<header", stage, "merged mode: the chosen header lives inside the stage")
        self.assertIn('data-hs-layout="single"', stage)                    # the hero look of editorial_noir
        self.assertEqual(self._variant(), "centered_brand")                # the header of glass_commerce
        self.assertEqual(self._draft().template_provenance["template"]["key"], "dual_atelier", "the base template identity is unchanged")

    def test_the_independent_header_mode_still_gets_the_chosen_header_from_the_shell(self):
        self._apply_whole("dual_atelier")
        self._apply_header("editorial_noir")
        stage = self._stage()
        stage.settings = {**stage.settings, "header_mode": "independent"}
        stage.save(update_fields=["settings"])
        self._publish()
        live = self.public.get(reverse("catalog:home")).content.decode()
        self.assertEqual(live.count("<header"), 1)
        self.assertNotIn("<header", re.search(r'<section class="hs-stage".*?</section>', live, re.S).group(0))

    # ------------------------------------------------------------------------------------------------------------ tenant isolation
    def test_another_stores_draft_is_never_touched(self):
        other = svc.get_or_create_draft(self.other_store)
        other_header, other_sections = dict(other.effective_header_config()), other.get_page("home").sections.count()
        self._apply_whole("dual_atelier")
        self._apply_header("editorial_noir")
        self._apply_hero("glass_commerce")
        other.refresh_from_db()
        self.assertEqual(other.effective_header_config(), other_header)
        self.assertEqual(other.get_page("home").sections.count(), other_sections)
        self.assertEqual(StorefrontLayout.objects.filter(store=self.other_store).count(), 1)

    def test_the_published_page_does_not_change_until_publish(self):
        self._apply_whole("dual_atelier")
        self._publish()
        live_before = self.public.get(reverse("catalog:home")).content.decode()
        self._apply_header("editorial_noir")
        self._apply_hero("asymmetric_canvas")
        cache.clear()
        self.assertEqual(_strip_csrf(self.public.get(reverse("catalog:home")).content.decode()), _strip_csrf(live_before))


from django.test import SimpleTestCase


class HeroRecipeUnitTests(SimpleTestCase):
    def test_a_recipe_never_contains_content_keys(self):
        recipe = hero_stage.layout_recipe({"title": "x", "bg_a_media_asset_id": 5, "bg_layout": "dual", "bg_a_focal_x": 10})
        for key in hero_stage.CONTENT_KEYS:
            self.assertNotIn(key, recipe)
        self.assertEqual(recipe["bg_layout"], "dual")

    def test_applying_a_recipe_resets_unlisted_design_keys_and_keeps_content(self):
        current = {"title": "من", "bg_a_media_asset_id": 7, "scrim_strength": 80, "design": {"radius": 4}}
        merged = hero_stage.apply_layout_recipe(current, hero_stage.layout_recipe({"bg_layout": "dual"}))
        self.assertEqual((merged["title"], merged["bg_a_media_asset_id"], merged["design"]), ("من", 7, {"radius": 4}))
        self.assertEqual(merged["bg_layout"], "dual")
        self.assertEqual(merged["scrim_strength"], hero_stage.default_settings()["scrim_strength"], "no trace of the previous look lingers")

    def test_garbage_recipes_fall_back_to_the_defaults(self):
        for junk in (None, [], "x", {"bg_a_media_asset_id": "abc", "header_mode": 9}):
            recipe = hero_stage.layout_recipe(junk)
            self.assertEqual(recipe["header_mode"], hero_stage.default_settings()["header_mode"])

    def test_engine_never_names_a_template(self):
        import pathlib
        source = (pathlib.Path(hero_stage.__file__)).read_text(encoding="utf8")
        for key in ("dual_atelier", "editorial_noir", "glass_commerce", "asymmetric_canvas"):
            self.assertNotIn(key, source)
