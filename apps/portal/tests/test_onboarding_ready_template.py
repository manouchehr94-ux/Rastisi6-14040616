"""Owner onboarding — the «قالب فروشگاه» (Ready Template) step and the publish boundary.

The catalog is the Storefront Builder's ONE Ready Template registry
(``layout_preset_registry.list_ready_templates()``), cards come from the shared
``ready_template_card_service``, and application/publication are done by existing Storefront Builder
services — this file pins that contract from the owner's side.
"""

import inspect
import re
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.utils import timezone

import apps.portal as portal_app_module
from apps.core.services.rate_limit import RateLimitExceeded
from apps.portal.models import OwnerProfile
from apps.portal.services import onboarding_publish_service, provisioning_service
from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import (
    layout_service,
    ready_template_card_service,
    store_template_service,
    template_preview_service,
)
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription

User = get_user_model()
_HOST = "rastisi.localhost"
_PASS = "a-very-strong-pass-1"

READY = layout_preset_registry.list_ready_templates()
KEY_A, KEY_B = READY[0].key, READY[1].key
NON_READY_KEY = next(k for k, v in layout_preset_registry.LAYOUT_PRESET_REGISTRY.items() if not v.is_ready_template)


def _versions_by_key():
    versions = {}
    for (key, version) in layout_preset_registry.LAYOUT_PRESET_VERSION_REGISTRY:
        versions.setdefault(key, []).append(version)
    return versions


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class Base(TestCase):
    def setUp(self):
        cache.clear()  # per-Store rate-limit counters are keyed by pk, which a rolled-back DB can reuse
        self.owner = User.objects.create_user(username="tpl-owner@example.com", email="tpl-owner@example.com", password=_PASS)
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاهِ قالب")
        plan = Plan.objects.create(code="tpl-plan", name="Tpl")
        version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        StoreSubscription.objects.create(
            store=self.store, plan_version=version, status=StoreSubscription.Status.TRIALING,
            is_current=True, trial_end_at=timezone.now(),
        )
        self.client.force_login(self.owner)

    def url(self, stage, store=None):
        return f"/app/stores/{(store or self.store).public_id}/onboarding/{stage}/"

    def get(self, stage):
        response = self.client.get(self.url(stage), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        return response

    def post_template(self, data, *, client=None, store=None):
        return (client or self.client).post(self.url("template", store), data, HTTP_HOST=_HOST)

    def select(self, key=KEY_A):
        return self.post_template({"template_key": key})

    def draft(self):
        layout = StorefrontLayout.objects.get(store=self.store)
        return layout.draft_version

    def counts(self):
        return (
            StorefrontLayout.objects.count(), StorefrontLayoutVersion.objects.count(),
            StorefrontSection.objects.count(),
        )


# ── Catalog / gallery ────────────────────────────────────────────────────────


class CatalogTests(Base):
    def test_gallery_exposes_exactly_the_canonical_current_ready_templates(self):
        response = self.get("template")
        cards = response.context["template_cards"]
        self.assertEqual(len(READY), 50)  # the pinned catalog contract
        self.assertEqual([c["preset"].key for c in cards], [p.key for p in layout_preset_registry.list_ready_templates()])
        html = response.content.decode()
        self.assertEqual(len(re.findall(r"<article class=\"ob-tpl-card", html)), 50)

    def test_no_historical_versions_and_no_non_ready_presets(self):
        cards = self.get("template").context["template_cards"]
        keys = [c["preset"].key for c in cards]
        self.assertEqual(len(keys), len(set(keys)))  # one card per key
        for card in cards:
            preset = card["preset"]
            self.assertTrue(preset.is_ready_template)
            self.assertIs(preset, layout_preset_registry.get_layout_preset(preset.key))  # the CURRENT version object
        non_ready = {k for k, v in layout_preset_registry.LAYOUT_PRESET_REGISTRY.items() if not v.is_ready_template}
        self.assertTrue(non_ready)  # the registry really has structural presets...
        self.assertFalse(non_ready & set(keys))  # ...and none leak into onboarding
        self.assertTrue(any(len(v) > 1 for v in _versions_by_key().values()))  # historical versions exist...
        for key, versions in _versions_by_key().items():
            if len(versions) > 1 and key in keys:
                html = self.get("template").content.decode()
                current = layout_preset_registry.get_layout_preset(key).version
                for old in versions:
                    if old != current:
                        old_shot = template_preview_service.screenshot_relpath(key, old)
                        self.assertNotIn(static(old_shot), html)  # ...and their screenshots never appear

    def test_card_screenshots_use_the_existing_preview_authority(self):
        response = self.get("template")
        html = response.content.decode()
        for card in response.context["template_cards"]:
            preset = card["preset"]
            relpath = template_preview_service.resolve_real_screenshot(preset)
            self.assertIsNotNone(relpath, preset.key)
            self.assertEqual(card["thumbnail_kind"], "screenshot")
            self.assertEqual(card["thumbnail_url"], static(relpath))
            self.assertIn(f'src="{static(relpath)}"', html)

    def test_cards_are_the_shared_projection_used_by_the_merchant_gallery(self):
        cards = self.get("template").context["template_cards"]
        shared = ready_template_card_service.build_ready_template_cards(
            None, current_template_key=None, current_template_version=None,
        )
        self.assertEqual([c["thumbnail_url"] for c in cards], [c["thumbnail_url"] for c in shared])
        from apps.storefront_builder import views as builder_views

        self.assertIs(builder_views.build_ready_template_cards, ready_template_card_service.build_ready_template_cards)

    def test_portal_has_no_second_catalog_or_application_logic(self):
        portal = Path(portal_app_module.__file__).resolve().parent
        source = "\n".join(
            (portal / rel).read_text(encoding="utf-8")
            for rel in ("views.py", "services/onboarding_publish_service.py")
        )
        for forbidden in ("A8_READY_TEMPLATES", "StorefrontSection(", "StorefrontSection.objects", "template_provenance =",
                          "template_baseline_snapshot", "apply_preset(", "switch_ready_template_preserving"):
            self.assertNotIn(forbidden, source)
        self.assertIn("list_ready_templates", inspect.getsource(ready_template_card_service))


# ── UI ──────────────────────────────────────────────────────────────────────


class GalleryUiTests(Base):
    def test_every_card_has_a_persian_name_a_lazy_preview_and_a_large_view_link(self):
        response = self.get("template")
        html = response.content.decode()
        for card in response.context["template_cards"]:
            preset = card["preset"]
            self.assertIn(f'data-name="{preset.label_fa}"', html)
            self.assertIn(f'alt="پیش‌نمایشِ قالبِ {preset.label_fa}"', html)
        self.assertEqual(html.count('loading="lazy"'), 50)
        self.assertEqual(html.count("data-ob-zoom"), 50)
        self.assertIn("مشاهده بزرگ‌تر", html)
        self.assertIn("<dialog", html)
        # no 50 live preview iframes
        self.assertNotIn("<iframe", html)

    def test_markup_and_stylesheet_are_responsive_without_inline_layout(self):
        html = self.get("template").content.decode()
        self.assertNotRegex(html.split("</header>", 1)[1], r'\sstyle\s*=')
        css = (Path(portal_app_module.__file__).resolve().parent / "static/portal/css/onboarding.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.ob-tpl-grid\{display:grid;grid-template-columns:repeat\(3,minmax\(0,1fr\)\)")
        self.assertRegex(css, r"max-width:640px\)\{\.ob-tpl-grid\{grid-template-columns:1fr\}")  # one card per row on mobile
        self.assertNotRegex(css, r"\.ob-tpl-card\{[^}]*\bwidth:\s*\d+px")  # nothing fixed-width

    def test_selected_state_is_rendered_for_the_applied_template(self):
        self.select(KEY_A)
        response = self.get("template")
        html = response.content.decode()
        self.assertEqual(response.context["selected_key"], KEY_A)
        self.assertRegex(html, rf'<article class="ob-tpl-card is-selected"[^>]*data-key="{KEY_A}"')
        self.assertRegex(html, rf'value="{KEY_A}" checked')
        self.assertEqual(html.count("ob-tpl-card is-selected"), 1)

    def test_search_is_client_side_and_a_get_never_mutates(self):
        before = self.counts()
        stage = self.store.onboarding_stage
        for query in ("", "?q=zzz", "?template_key=" + KEY_A, "?search=بازار"):
            response = self.client.get(self.url("template") + query, HTTP_HOST=_HOST)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context["template_cards"]), 50)  # the server never filters/selects
        self.assertIn("data-ob-tpl-search", response.content.decode())
        self.assertEqual(self.counts(), before)  # not even a Draft is created by GET
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, stage)
        self.assertIsNone(store_template_service.get_applied_template(self.store))

    def test_there_is_no_skip_path_and_no_guessed_industry_recommendation(self):
        html = self.get("template").content.decode()
        self.assertNotIn("فعلاً رد شو", html)
        self.assertNotIn('name="action"', html)
        self.assertNotIn("پیشنهادی برای صنف", html)
        post = self.client.post(self.url("template"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertEqual(post.status_code, 200)  # no key => error, no advance
        self.store.refresh_from_db()
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)


# ── Selection ───────────────────────────────────────────────────────────────


class SelectionTests(Base):
    def assertNothingApplied(self, before):
        self.assertEqual(self.counts(), before)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        self.store.refresh_from_db()
        self.assertNotIn(self.store.onboarding_stage, (Store.OnboardingStage.BRANDING, Store.OnboardingStage.REVIEW))

    def test_unknown_missing_and_non_ready_keys_are_rejected_without_mutation(self):
        before = self.counts()
        for payload in ({"template_key": "no-such-template"}, {}, {"template_key": ""}, {"template_key": NON_READY_KEY},
                        {"template_key": "../../etc"}, {"template_key": KEY_A + "x"}):
            with self.subTest(payload=payload):
                response = self.post_template(payload)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "قالبِ انتخاب‌شده معتبر نیست")
                self.assertNothingApplied(before)

    def test_a_historical_version_cannot_be_forced_through_post(self):
        key, versions = next((k, v) for k, v in _versions_by_key().items() if len(v) > 1 and k in {p.key for p in READY})
        current = layout_preset_registry.get_layout_preset(key).version
        old = next(v for v in versions if v != current)
        self.post_template({"template_key": key, "template_version": old, "version": old})
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version), (key, current))
        self.assertTrue(applied.is_current_version)

    def test_posted_version_label_palette_and_settings_are_ignored(self):
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        self.post_template({
            "template_key": KEY_A, "template_version": "999", "label_fa": "جعلی", "palette": "forged",
            "default_palette_slug": "forged", "appearance": '{"font": "evil"}', "store_appearance": "{}",
            "screenshot": "/static/evil.png", "manifest": "{}", "store": "999", "store_id": "999",
        })
        draft = self.draft()
        self.assertEqual(draft.template_provenance["template"], {"key": KEY_A, "version": preset.version})
        self.assertEqual(draft.template_baseline_snapshot["default_palette_slug"], preset.default_palette_slug)
        self.assertNotIn("evil", str(draft.appearance_config))
        self.assertNotIn("forged", str(draft.appearance_config))

    def test_cross_store_request_cannot_mutate_another_store(self):
        intruder = User.objects.create_user(username="tpl-intruder@example.com", email="tpl-intruder@example.com", password=_PASS)
        provisioning_service.provision_trial_store(owner=intruder, name="دیگری")
        self.client.force_login(intruder)
        before = self.counts()
        response = self.post_template({"template_key": KEY_A})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.counts(), before)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        # and a posted store id never redirects the write to another tenant
        self.client.force_login(self.owner)
        self.post_template({"template_key": KEY_A, "store": "x", "store_public_id": str(intruder.pk)})
        self.assertIsNotNone(store_template_service.get_applied_template(self.store))

    def test_a_member_without_settings_manage_cannot_apply_or_advance(self):
        analyst = User.objects.create_user(username="tpl-analyst@example.com", email="tpl-analyst@example.com", password=_PASS)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(analyst)
        before = self.counts()
        response = self.post_template({"template_key": KEY_A})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), before)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)

    def test_first_selection_applies_the_exact_template_through_the_initial_authority(self):
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        with mock.patch("apps.storefront_builder.services.preset_service.apply_preset",
                        wraps=__import__("apps.storefront_builder.services.preset_service", fromlist=["x"]).apply_preset) as initial, \
             mock.patch("apps.storefront_builder.services.r4_mutation_service.switch_template_current") as switch:
            response = self.select(KEY_A)
        self.assertRedirects(response, self.url("branding"))
        self.assertEqual(initial.call_count, 1)
        switch.assert_not_called()
        draft = self.draft()
        self.assertEqual(draft.status, StorefrontLayoutVersion.Status.DRAFT)
        # the EXACT template composition: no hybrid with the legacy bootstrap content
        for page_type, entries in preset.pages.items():
            keys = list(draft.get_page(page_type).sections.order_by("order", "id").values_list("section_key", flat=True))
            self.assertEqual(keys, [e.section_key for e in entries], page_type)

    def test_provenance_and_baseline_snapshot_match_the_selected_template(self):
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        self.select(KEY_A)
        draft = self.draft()
        self.assertEqual(draft.template_provenance["template"], {"key": preset.key, "version": preset.version})
        snapshot = draft.template_baseline_snapshot
        self.assertEqual((snapshot["template_key"], snapshot["template_version"]), (preset.key, preset.version))
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version, applied.location), (preset.key, preset.version, "draft"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_reposting_the_same_template_is_idempotent_with_no_history_churn(self):
        self.select(KEY_A)
        draft = self.draft()
        revision, fingerprint = draft.edit_revision, list(draft.sections.values_list("pk", flat=True))
        counts = self.counts()
        again = self.select(KEY_A)
        self.assertRedirects(again, self.url("branding"))
        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, revision)
        self.assertEqual(list(draft.sections.values_list("pk", flat=True)), fingerprint)  # same rows, not rebuilt
        self.assertEqual(self.counts(), counts)
        self.assertEqual(draft.edit_history_entries.count(), 0)

    def test_choosing_another_template_uses_the_preservation_first_switch(self):
        self.select(KEY_A)
        with mock.patch(
            "apps.storefront_builder.services.r4_mutation_service.switch_template_current",
            wraps=__import__("apps.storefront_builder.services.r4_mutation_service", fromlist=["x"]).switch_template_current,
        ) as switch, mock.patch("apps.storefront_builder.services.preset_service.apply_preset") as initial:
            response = self.select(KEY_B)
        self.assertRedirects(response, self.url("branding"))
        self.assertEqual(switch.call_count, 1)
        initial.assert_not_called()
        preset_b = layout_preset_registry.get_layout_preset(KEY_B)
        draft = self.draft()
        self.assertEqual(draft.template_provenance["template"], {"key": KEY_B, "version": preset_b.version})
        self.assertEqual(draft.template_baseline_snapshot["template_key"], KEY_B)
        self.assertEqual(draft.edit_history_entries.count(), 1)  # exactly one canonical history entry

    def test_selection_is_transactional_a_failure_leaves_nothing_applied(self):
        before = self.counts()
        with mock.patch("apps.storefront_builder.services.preset_service.apply_preset", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.select(KEY_A)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        self.assertEqual(self.counts(), before)

    def test_rate_limit_is_a_controlled_error(self):
        with mock.patch.object(store_template_service, "select_ready_template", side_effect=RateLimitExceeded("x")):
            response = self.select(KEY_A)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بیش از حدِ مجاز")


# ── Wizard order / compatibility ───────────────────────────────────────────────


class WizardTests(Base):
    def test_order_progress_and_resume(self):
        from apps.portal import views

        self.assertEqual(
            views._ONBOARDING_STAGE_ORDER,
            [Store.OnboardingStage.IDENTITY, Store.OnboardingStage.INDUSTRY, Store.OnboardingStage.TEMPLATE,
             Store.OnboardingStage.BRANDING, Store.OnboardingStage.REVIEW],
        )
        r = self.client.post(self.url("identity"), {"name": "نام"}, HTTP_HOST=_HOST)
        self.assertRedirects(r, self.url("industry"))
        r = self.client.post(self.url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(r, self.url("template"))
        html = self.get("template").content.decode()
        self.assertIn("مرحله 3 از 5", html.replace("۳", "3").replace("۵", "5"))
        self.assertEqual(len(re.findall(r'<li class="ob-step', html)), 5)
        self.assertIn("قالب فروشگاه", html)
        # resume: the dispatcher returns the owner to the Template step
        self.assertRedirects(
            self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST), self.url("template"),
        )
        self.select(KEY_A)
        self.assertRedirects(
            self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST), self.url("branding"),
        )
        r = self.client.post(self.url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(r, self.url("review"))

    def test_previous_links_chain_through_the_template_step(self):
        self.assertIn(f'href="{self.url("industry")}"', self.get("template").content.decode())
        self.assertIn(f'href="{self.url("template")}"', self.get("branding").content.decode())

    def test_an_old_unpublished_store_at_branding_or_review_without_a_template_is_routed_through_the_step(self):
        for stage in (Store.OnboardingStage.BRANDING, Store.OnboardingStage.REVIEW):
            Store.objects.filter(pk=self.store.pk).update(onboarding_stage=stage)
            response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
            self.assertRedirects(response, self.url("template"))
            self.store.refresh_from_db()
            self.assertEqual(self.store.onboarding_stage, stage)  # progress is never reset

    def test_an_old_store_that_already_has_a_template_resumes_where_it_was(self):
        self.select(KEY_A)
        Store.objects.filter(pk=self.store.pk).update(onboarding_stage=Store.OnboardingStage.REVIEW)
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self.url("review"))

    def test_completed_stores_are_never_forced_back_through_the_step(self):
        self.select(KEY_A)
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        created = f"/app/stores/{self.store.public_id}/created/"
        self.assertRedirects(self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST), created)
        self.assertRedirects(self.client.get(self.url("template"), HTTP_HOST=_HOST), created)
        before = self.counts()
        self.assertRedirects(self.select(KEY_B), created)  # and a POST cannot swap the published design either
        self.assertEqual(self.counts(), before)

    def test_a_completed_legacy_store_without_a_template_is_left_alone(self):
        Store.objects.filter(pk=self.store.pk).update(
            onboarding_stage=Store.OnboardingStage.DONE, onboarding_completed_at=timezone.now(),
        )
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/created/")
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout__store=self.store).count(), 0)  # nothing auto-applied


# ── Review ───────────────────────────────────────────────────────────────────


class ReviewTests(Base):
    def test_review_shows_the_chosen_visual_template_separately_from_the_industry_template(self):
        self.select(KEY_A)
        html = self.get("review").content.decode()
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        self.assertIn("صنف فروشگاه", html)
        self.assertIn("قالب ظاهریِ فروشگاه", html)
        block = html[html.index("data-review-template"):]
        block = block[:block.index("</dl>")]
        self.assertIn(preset.label_fa, block)
        self.assertIn(static(template_preview_service.resolve_real_screenshot(preset)), block)
        self.assertIn(f"نسخه‌ی {preset.version}", block)
        self.assertNotIn("نصب نشده", block)  # the industry placeholder is not in the visual-template block
        self.assertIn(f'href="{self.url("template")}"', block)
        self.assertIn("ویرایش قالب", block)

    def test_review_without_a_template_says_so_and_blocks_publish(self):
        response = self.get("review")
        html = response.content.decode()
        self.assertIn("قالب فروشگاه انتخاب نشده", html)
        self.assertRegex(html, r'<button type="submit" form="ob-publish-form"[^>]*disabled')
        self.assertIn("انتخاب قالب", html)

    def test_final_publish_refuses_when_no_ready_template_exists(self):
        response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self.url("template"))
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)
        self.assertFalse(StorefrontLayoutVersion.objects.filter(status=StorefrontLayoutVersion.Status.PUBLISHED).exists())
        # even with onboarding_stage forged to REVIEW the real layout state is what counts
        Store.objects.filter(pk=self.store.pk).update(onboarding_stage=Store.OnboardingStage.REVIEW)
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)


# ── Publication ─────────────────────────────────────────────────────────────


class PublicationTests(Base):
    def published(self):
        return StorefrontLayoutVersion.objects.filter(
            layout__store=self.store, status=StorefrontLayoutVersion.Status.PUBLISHED,
        )

    def test_the_chosen_template_stays_a_draft_until_final_publish(self):
        self.select(KEY_A)
        self.get("review")
        self.assertFalse(self.published().exists())
        self.assertEqual(self.draft().status, StorefrontLayoutVersion.Status.DRAFT)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)

    def test_final_publish_publishes_the_storefront_draft_with_the_chosen_provenance(self):
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        self.select(KEY_A)
        draft_pk = self.draft().pk
        response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/created/")
        version = self.published().get()
        self.assertEqual(version.pk, draft_pk)  # the Draft itself was published (no clone)
        self.assertEqual(version.template_provenance["template"], {"key": KEY_A, "version": preset.version})
        layout = StorefrontLayout.objects.get(store=self.store)
        self.assertEqual(layout.published_version_id, draft_pk)
        self.assertIsNone(layout.draft_version_id)
        self.assertTrue(layout.uses_visual_storefront_layout)
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.onboarding_completed_at)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.location), (KEY_A, "published"))

    def test_the_public_storefront_serves_the_published_chosen_template(self):
        self.select(KEY_A)
        domain = self.store.domains.filter(is_primary=True).first().hostname
        with self.settings(ALLOWED_HOSTS=[domain, _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST=domain).status_code, 403)  # private before publish
            self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
            response = self.client.get("/", HTTP_HOST=domain)
        self.assertEqual(response.status_code, 200)
        version = self.published().get()
        home_keys = list(version.get_page("home").sections.order_by("order", "id").values_list("section_key", flat=True))
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        self.assertEqual(home_keys, [e.section_key for e in preset.pages["home"]])

    def test_publication_failure_leaves_onboarding_incomplete_and_private(self):
        self.select(KEY_A)
        with mock.patch.object(layout_service, "publish", side_effect=RateLimitExceeded("x")):
            response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self.url("review"))
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)
        self.assertFalse(self.published().exists())
        self.assertEqual(self.draft().status, StorefrontLayoutVersion.Status.DRAFT)
        follow = self.client.get(self.url("review"), HTTP_HOST=_HOST)
        self.assertNotContains(follow, "فروشگاه شما منتشر شد")

    def test_a_database_failure_after_publishing_rolls_the_storefront_publish_back(self):
        from django.db import DatabaseError

        self.select(KEY_A)
        real_save = Store.save

        def failing_save(instance, *args, **kwargs):
            if kwargs.get("update_fields") and "onboarding_completed_at" in kwargs["update_fields"]:
                raise DatabaseError("boom")
            return real_save(instance, *args, **kwargs)

        with mock.patch.object(Store, "save", failing_save):
            response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self.url("review"))
        self.assertFalse(self.published().exists())  # the publish was inside the same transaction
        self.assertEqual(self.draft().status, StorefrontLayoutVersion.Status.DRAFT)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)

    def test_double_submit_does_not_republish_or_rewrite_the_first_timestamp(self):
        self.select(KEY_A)
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.store.refresh_from_db()
        stamp = self.store.onboarding_completed_at
        published_pk = self.published().get().pk
        versions = StorefrontLayoutVersion.objects.filter(layout__store=self.store).count()
        with mock.patch.object(layout_service, "publish") as publish:
            second = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        publish.assert_not_called()
        self.assertRedirects(second, f"/app/stores/{self.store.public_id}/created/")
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_completed_at, stamp)
        self.assertEqual(self.published().get().pk, published_pk)
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout__store=self.store).count(), versions)

    def test_a_member_without_settings_manage_cannot_publish(self):
        self.select(KEY_A)
        analyst = User.objects.create_user(username="tpl-an2@example.com", email="tpl-an2@example.com", password=_PASS)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(analyst)
        self.assertEqual(self.client.post(self.url("review"), {}, HTTP_HOST=_HOST).status_code, 403)
        self.assertFalse(self.published().exists())

    def test_a_legacy_store_whose_published_version_already_has_a_template_completes_without_republishing(self):
        self.select(KEY_A)
        layout_service.publish(self.store, user=self.owner)  # the merchant published from the Builder earlier
        published_pk = self.published().get().pk
        with mock.patch.object(layout_service, "publish") as publish:
            outcome = onboarding_publish_service.complete_onboarding(store=self.store, actor=self.owner)
        publish.assert_not_called()
        self.assertFalse(outcome.published_storefront)
        self.assertEqual(self.published().get().pk, published_pk)
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.onboarding_completed_at)


# ── Regression / independence ─────────────────────────────────────────────────


class RegressionTests(Base):
    def test_industry_template_stays_independent_of_the_ready_template(self):
        from apps.catalog.models import StoreIndustryInstallation

        self.select(KEY_A)
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_the_demo_store_is_untouched(self):
        demo = Store.objects.filter(slug="rasti-mode-demo").first()
        before = StorefrontLayoutVersion.objects.filter(layout__store=demo).count() if demo else 0
        self.select(KEY_A)
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        after = StorefrontLayoutVersion.objects.filter(layout__store=demo).count() if demo else 0
        self.assertEqual(before, after)

    def test_one_store_s_selection_does_not_touch_another_store(self):
        other_owner = User.objects.create_user(username="tpl-other@example.com", email="tpl-other@example.com", password=_PASS)
        other = provisioning_service.provision_trial_store(owner=other_owner, name="دیگر")
        self.select(KEY_A)
        self.assertIsNone(store_template_service.get_applied_template(other))
        self.assertFalse(StorefrontLayout.objects.filter(store=other).exists() and StorefrontLayout.objects.get(store=other).draft_version_id)


# ── Pre-publish privacy: a modern Store is never public before the final Publish ──────────────────


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PrePublishPrivacyTests(TestCase):
    """The exact misconfigured case: real portal provisioning with NO default subscription plan
    (``AccessState.NONE``). The Store must still be private until ``onboarding_completed_at`` is set."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="priv-owner@example.com", email="priv-owner@example.com", password=_PASS)
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاهِ خصوصی")
        self.domain = self.store.domains.filter(is_primary=True).first().hostname
        self.client.force_login(self.owner)

    def anonymous_home(self):
        from django.test import Client

        with self.settings(ALLOWED_HOSTS=[self.domain, _HOST, "testserver"]):
            return Client().get("/", HTTP_HOST=self.domain)

    def test_the_setup_really_has_no_subscription_and_a_routable_trial_domain(self):
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())
        self.assertIsNotNone(self.store.onboarding_required_at)
        self.assertIsNone(self.store.onboarding_completed_at)
        from apps.subscriptions.services.entitlement_service import AccessState, get_subscription_access_state

        self.assertEqual(get_subscription_access_state(self.store).state, AccessState.NONE)

    def test_without_a_subscription_the_anonymous_storefront_is_private_until_the_final_publish(self):
        from apps.stores.services.publication_service import PublicationState, get_store_publication_state

        self.assertEqual(get_store_publication_state(self.store), PublicationState.TRIAL_PRIVATE)
        self.assertEqual(self.anonymous_home().status_code, 403)

        # Choosing the template alone (a Draft) must not publish anything either.
        self.client.post(f"/app/stores/{self.store.public_id}/onboarding/template/", {"template_key": KEY_A}, HTTP_HOST=_HOST)
        self.assertEqual(self.anonymous_home().status_code, 403)

        response = self.client.post(f"/app/stores/{self.store.public_id}/onboarding/review/", {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/created/")
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.onboarding_completed_at)
        self.assertFalse(StoreSubscription.objects.filter(store=self.store).exists())  # still no subscription

        public = self.anonymous_home()
        self.assertEqual(public.status_code, 200)  # the normal post-onboarding policy applies
        preset = layout_preset_registry.get_layout_preset(KEY_A)
        published = StorefrontLayoutVersion.objects.get(
            layout__store=self.store, status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        self.assertEqual(published.template_provenance["template"], {"key": KEY_A, "version": preset.version})

    def test_the_gate_holds_for_a_no_default_plan_configuration(self):
        from apps.stores.services.publication_service import PublicationState, get_store_publication_state, is_publicly_visible
        from apps.subscriptions.services.subscription_service import resolve_default_plan_version

        self.assertIsNone(resolve_default_plan_version())  # the misconfiguration under test
        self.assertEqual(get_store_publication_state(self.store), PublicationState.TRIAL_PRIVATE)
        self.assertFalse(is_publicly_visible(self.store))

    def test_a_failed_publish_keeps_the_no_subscription_store_private(self):
        self.client.post(f"/app/stores/{self.store.public_id}/onboarding/template/", {"template_key": KEY_A}, HTTP_HOST=_HOST)
        with mock.patch.object(layout_service, "publish", side_effect=RateLimitExceeded("x")):
            self.client.post(f"/app/stores/{self.store.public_id}/onboarding/review/", {}, HTTP_HOST=_HOST)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertEqual(self.anonymous_home().status_code, 403)

    def test_a_legacy_store_without_the_signal_is_still_public(self):
        from apps.stores.models import Store as StoreModel
        from apps.stores.services.platform_code_service import generate_unique_platform_code

        legacy = StoreModel.objects.create(
            name="قدیمی", slug="legacy-no-signal", status=StoreModel.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        self.assertIsNone(legacy.onboarding_required_at)
        self.assertIsNone(legacy.onboarding_completed_at)
        from apps.stores.services.publication_service import is_publicly_visible

        self.assertTrue(is_publicly_visible(legacy))

    def test_both_modern_creation_paths_set_the_signal_and_the_store_create_view_too(self):
        other = User.objects.create_user(username="priv-o2@example.com", email="priv-o2@example.com", password=_PASS)
        store, created = provisioning_service.provision_initial_trial_store(owner=other, name="دوم")
        self.assertTrue(created)
        self.assertIsNotNone(store.onboarding_required_at)


# ── Historical applied template: never silently upgraded ──────────────────────────────────────────


class HistoricalTemplateTests(Base):
    def setUp(self):
        super().setUp()
        self.key, self.latest, self.old = self._historical_pair()
        self.old_preset = layout_preset_registry.get_layout_preset_version(self.key, self.old)
        self.latest_preset = layout_preset_registry.get_layout_preset(self.key)
        draft = layout_service.get_or_create_draft(self.store, user=self.owner)
        from apps.storefront_builder.services import preset_service

        preset_service.apply_preset(draft, self.old_preset)

    @staticmethod
    def _historical_pair():
        for key, versions in _versions_by_key().items():
            current = next((p for p in READY if p.key == key), None)
            if current is not None and len(versions) > 1:
                return key, current.version, next(v for v in versions if v != current.version)
        raise AssertionError("no historical Ready Template fixture")

    def snapshot(self):
        draft = self.draft()
        return (
            self.counts(), draft.pk, draft.edit_revision, draft.template_provenance,
            draft.template_baseline_snapshot, draft.edit_history_entries.count(),
            list(draft.sections.values_list("pk", flat=True)),
        )

    def test_the_fixture_is_really_a_historical_version_of_the_current_card_key(self):
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version), (self.key, self.old))
        self.assertFalse(applied.is_current_version)
        self.assertNotEqual(self.old, self.latest)

    def test_the_latest_same_key_card_is_neither_selected_nor_marked_current(self):
        response = self.get("template")
        html = response.content.decode()
        self.assertEqual(response.context["selected_key"], "")
        self.assertEqual(html.count("ob-tpl-card is-selected"), 0)
        self.assertNotRegex(html, r'name="template_key" value="[^"]+" checked')
        self.assertFalse(any(card["is_current"] for card in response.context["template_cards"]))
        self.assertNotIn("قالبِ فعلی</span>", html)

    def test_the_actual_historical_template_and_version_are_shown_in_an_informational_panel(self):
        html = self.get("template").content.decode()
        self.assertIn("data-ob-tpl-current", html)
        self.assertIn(f"قالب فعلی شما: «{self.old_preset.label_fa}»، نسخه {self.old}", html)
        self.assertIn("ادامه با همین قالب", html)
        self.assertIn('name="action" value="keep_current"', html)

    def test_get_of_the_step_mutates_nothing(self):
        before = self.snapshot()
        self.get("template")
        self.assertEqual(self.snapshot(), before)

    def test_keep_current_advances_with_zero_storefront_mutation(self):
        before = self.snapshot()
        with mock.patch.object(store_template_service, "select_ready_template") as select, \
                mock.patch("apps.storefront_builder.services.preset_service.apply_preset") as apply, \
                mock.patch("apps.storefront_builder.services.r4_mutation_service.switch_template_current") as switch:
            response = self.post_template({"action": "keep_current"})
        self.assertRedirects(response, self.url("branding"))
        select.assert_not_called()
        apply.assert_not_called()
        switch.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version), (self.key, self.old))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_keep_current_ignores_any_forged_template_fields(self):
        before = self.snapshot()
        response = self.post_template({
            "action": "keep_current", "template_key": KEY_B, "template_version": "999", "version": self.latest,
        })
        self.assertRedirects(response, self.url("branding"))
        self.assertEqual(self.snapshot(), before)

    def test_keep_current_then_publish_keeps_the_historical_version(self):
        self.post_template({"action": "keep_current"})
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version, applied.location), (self.key, self.old, "published"))

    def test_a_member_without_settings_manage_cannot_keep_current(self):
        analyst = User.objects.create_user(username="tpl-an3@example.com", email="tpl-an3@example.com", password=_PASS)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(analyst)
        before = self.snapshot()
        self.assertEqual(self.post_template({"action": "keep_current"}).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        self.store.refresh_from_db()
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_explicitly_choosing_the_latest_card_performs_the_upgrade(self):
        before_revision = self.draft().edit_revision
        response = self.select(self.key)
        self.assertRedirects(response, self.url("branding"))
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual((applied.key, applied.version), (self.key, self.latest))
        self.assertTrue(applied.is_current_version)
        self.assertGreater(self.draft().edit_revision, before_revision)

    def test_after_an_explicit_upgrade_the_exact_card_is_selected_and_the_panel_is_gone(self):
        self.select(self.key)
        response = self.get("template")
        html = response.content.decode()
        self.assertEqual(response.context["selected_key"], self.key)
        self.assertNotIn("data-ob-tpl-current", html)
        self.assertRegex(html, rf'value="{self.key}" checked')


class KeepCurrentAuthorityTests(Base):
    """``keep_current`` is only valid when the Store REALLY has a valid applied Ready Template."""

    def test_a_forged_keep_current_without_an_applied_template_cannot_advance_or_mutate(self):
        before = self.counts()
        stage = self.store.onboarding_stage
        response = self.post_template({"action": "keep_current"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هنوز قالبِ آماده‌ای ندارد")
        self.assertEqual(self.counts(), before)  # not even a Draft/Layout/history row
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, stage)

    def test_a_draft_without_template_provenance_does_not_satisfy_keep_current(self):
        layout_service.get_or_create_draft(self.store, user=self.owner)  # untouched legacy bootstrap Draft
        before = self.counts()
        response = self.post_template({"action": "keep_current"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counts(), before)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
        self.store.refresh_from_db()
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_a_current_version_store_can_also_keep_current_with_no_mutation(self):
        self.select(KEY_A)
        draft = self.draft()
        revision, history = draft.edit_revision, draft.edit_history_entries.count()
        before = self.counts()
        response = self.post_template({"action": "keep_current"})
        self.assertRedirects(response, self.url("branding"))
        draft.refresh_from_db()
        self.assertEqual((draft.edit_revision, draft.edit_history_entries.count(), self.counts()), (revision, history, before))

    def test_keep_current_cannot_touch_another_stores_template(self):
        intruder = User.objects.create_user(username="tpl-kc@example.com", email="tpl-kc@example.com", password=_PASS)
        provisioning_service.provision_trial_store(owner=intruder, name="دیگری")
        self.select(KEY_A)
        self.client.force_login(intruder)
        before = self.counts()
        response = self.post_template({"action": "keep_current"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.counts(), before)


# ── Publish error boundary ─────────────────────────────────────────────────────────────────────────


class PublishErrorBoundaryTests(Base):
    def published(self):
        return StorefrontLayoutVersion.objects.filter(
            layout__store=self.store, status=StorefrontLayoutVersion.Status.PUBLISHED,
        )

    def assertStillPrivateAndUnpublished(self):
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)
        self.assertFalse(self.published().exists())
        self.assertEqual(self.draft().status, StorefrontLayoutVersion.Status.DRAFT)

    def test_expected_domain_publication_failures_become_controlled_persian_errors(self):
        self.select(KEY_A)
        for exc, code in (
            (layout_service.NoDraftToPublishError("x"), "no_draft"),
            (RateLimitExceeded("x"), "rate_limited"),
        ):
            with self.subTest(code=code), mock.patch.object(layout_service, "publish", side_effect=exc):
                response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 302)  # a redirect with a message — never a 500
                with self.assertRaises(onboarding_publish_service.OnboardingPublishError) as ctx:
                    onboarding_publish_service.complete_onboarding(store=self.store, actor=self.owner)
                self.assertEqual(ctx.exception.code, code)
                self.assertStillPrivateAndUnpublished()

    def test_a_database_error_during_publish_is_controlled_and_rolls_back(self):
        from django.db import IntegrityError

        self.select(KEY_A)
        with mock.patch.object(layout_service, "publish", side_effect=IntegrityError("dup")):
            response = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self.url("review"))
        self.assertStillPrivateAndUnpublished()

    def test_a_programmer_error_is_not_swallowed_and_still_rolls_back(self):
        self.select(KEY_A)
        with mock.patch.object(layout_service, "publish", side_effect=RuntimeError("bug")):
            with self.assertRaises(RuntimeError):
                onboarding_publish_service.complete_onboarding(store=self.store, actor=self.owner)
        self.assertStillPrivateAndUnpublished()

    def test_base_exceptions_are_never_caught(self):
        self.select(KEY_A)
        for exc in (KeyboardInterrupt, SystemExit):
            with self.subTest(exc=exc.__name__), mock.patch.object(layout_service, "publish", side_effect=exc()):
                with self.assertRaises(exc):
                    onboarding_publish_service.complete_onboarding(store=self.store, actor=self.owner)
                self.assertStillPrivateAndUnpublished()

    def test_the_service_does_not_catch_base_exception_or_bare_except(self):
        source = inspect.getsource(onboarding_publish_service)
        self.assertNotRegex(source, r"except\s*:")
        self.assertNotRegex(source, r"except\s+BaseException")
        self.assertNotRegex(source, r"except\s+Exception\b")
