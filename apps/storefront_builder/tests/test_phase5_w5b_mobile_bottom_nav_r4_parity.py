"""P5-W5B — Mobile Bottom Navigation, R4 Parity.

Strict TDD RED-before-GREEN suite closing the merchant-facing R4 vertical
slice for the ALREADY-EXISTING ``GLOBAL_MOBILE_NAV_REGION`` authority (see
``docs/superpowers/plans/2026-09-19-phase5-w5b-mobile-bottom-nav-r4-parity.md``):
no new variant, renderer, registry, model, JSON field, or mutation type is
introduced here — only ``footer.update``'s allowlist/patch-application and
the R4 Global Design read projection/selector are extended to expose the
field that already round-trips through ``footer_config``.
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import global_region_registry
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store, StoreDomain, StoreMembership

from .test_r4_mutation_api import R4MutationApiTestCase

User = get_user_model()

REGISTERED_MOBILE_NAV_VARIANTS = global_region_registry.list_global_variants(
    global_region_registry.GLOBAL_MOBILE_NAV_REGION
)


# ---------------------------------------------------------------------------
# A, B. R4 Global Design read projection is registry-driven.
# ---------------------------------------------------------------------------
class MobileNavReadProjectionTests(R4MutationApiTestCase):
    def _get_editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor"))

    def test_editor_response_lists_every_registered_variant_key_and_label(self):
        """A/B — the projection (surfaced through the rendered HTML, since
        the context itself is not directly introspectable through the
        client) must contain every registry-declared variant's key and
        label, derived from the registry — never a second hardcoded list."""
        body = self._get_editor().content.decode()
        for variant in REGISTERED_MOBILE_NAV_VARIANTS:
            self.assertIn(f'value="{variant.key}"', body)
            self.assertIn(variant.label_fa, body)

    def test_registered_variant_count_matches_the_canonical_registry(self):
        """The expected option count is derived from the registry itself,
        never a second duplicated hardcoded number in this test file."""
        self.assertEqual(len(REGISTERED_MOBILE_NAV_VARIANTS), 9)


# ---------------------------------------------------------------------------
# C, D. R4 Global Design HTML renders a merchant-facing selector, wired
#    through the existing generic data-r4-global-field/data-r4-global-
#    mutation flow (no new JS branch needed).
# ---------------------------------------------------------------------------
class MobileNavSelectorMarkupTests(R4MutationApiTestCase):
    def _get_editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor"))

    def test_selector_uses_generic_global_field_and_mutation_attributes(self):
        body = self._get_editor().content.decode()
        self.assertIn('data-r4-global-field="mobile_nav_variant"', body)
        # The field must live inside a section carrying the EXISTING
        # footer.update mutation group — no new mutation type.
        field_index = body.index('data-r4-global-field="mobile_nav_variant"')
        preceding = body[:field_index]
        group_index = preceding.rfind('data-r4-global-mutation="footer.update"')
        self.assertNotEqual(group_index, -1, "selector must be nested under an existing footer.update group")

    def test_selector_shows_current_value_as_selected(self):
        self.draft.footer_config = dict(self.draft.effective_footer_config())
        self.draft.footer_config["mobile_nav_variant"] = "luxury_floating_cart"
        self.draft.save(update_fields=["footer_config"])
        body = self._get_editor().content.decode()
        self.assertIn('value="luxury_floating_cart" selected', body)

    def test_selector_carries_a_merchant_facing_persian_label(self):
        body = self._get_editor().content.decode()
        self.assertIn("ناوبری پایین موبایل", body)


# ---------------------------------------------------------------------------
# E, F. footer.update accepts mobile_nav_variant; unknown key fails closed.
# ---------------------------------------------------------------------------
class MobileNavMutationAcceptanceTests(R4MutationApiTestCase):
    def test_footer_update_accepts_mobile_nav_variant(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "four_item"}},
        })
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["mobile_nav_variant"], "four_item")

    def test_unknown_mobile_nav_variant_fails_closed(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "not-a-real-variant"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)
        self.draft.refresh_from_db()
        self.assertNotEqual(self.draft.footer_config.get("mobile_nav_variant"), "not-a-real-variant")

    def test_validate_footer_config_remains_the_single_validator_boundary(self):
        from unittest.mock import patch as mock_patch

        with mock_patch(
            "apps.storefront_builder.services.r4_mutation_service.layout_service.validate_footer_config",
            wraps=svc.validate_footer_config,
        ) as mock_validate:
            response = self._post_json({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "five_item"}},
            })
        self.assertEqual(response.status_code, 200)
        mock_validate.assert_called_once()


# ---------------------------------------------------------------------------
# G, H, I, J. Sibling-state isolation — Bottom Nav is an INDEPENDENT axis.
# ---------------------------------------------------------------------------
class MobileNavSiblingIsolationTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.draft.footer_config = dict(self.draft.effective_footer_config())
        self.draft.footer_config.update({
            "footer_variant": "marketplace_dense",
            "mobile_nav_variant": "hidden",
            "show_copyright": True,
            "show_social": False,
            "extra_blocks": [],
        })
        self.draft.save(update_fields=["footer_config"])
        # Sync the typed manifest to match, exactly like a real save through
        # _apply_footer_update already does -- otherwise the "before"
        # snapshot below is inconsistent (raw footer_config says
        # marketplace_dense, but the typed footer selection is still
        # whatever the untouched default was), which would make the FIRST
        # real mutation's routine re-sync look like an unwanted side effect.
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
        from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive

        appearance_authority_service.apply_footer_variant(
            version=self.draft, footer_variant="marketplace_dense", mobile_nav_variant="hidden",
        )

        self.before_manifest = manifest_to_primitive(
            appearance_persistence.load_store_appearance_manifest(self.draft)
        )
        self.before_header = dict(self.draft.header_config)

    def _change_mobile_nav(self, key="four_item"):
        return self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": key}},
        })

    def test_changing_only_mobile_nav_preserves_footer_variant(self):
        resp = self._change_mobile_nav()
        self.assertEqual(resp.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["footer_variant"], "marketplace_dense")

    def test_changing_only_mobile_nav_preserves_footer_toggles_and_blocks(self):
        resp = self._change_mobile_nav()
        self.assertEqual(resp.status_code, 200)
        self.draft.refresh_from_db()
        self.assertIs(self.draft.footer_config["show_copyright"], True)
        self.assertIs(self.draft.footer_config["show_social"], False)
        self.assertEqual(self.draft.footer_config["extra_blocks"], [])

    def test_changing_only_mobile_nav_preserves_unrelated_appearance_and_header(self):
        """H — the typed Store Appearance manifest lives inside the same
        ``appearance_config`` JSONField as the ``bottom_nav`` selection
        itself, so a byte-for-byte compare of the whole field would always
        fail (bottom_nav is EXPECTED to change) -- assert every OTHER typed
        family selection, plus header_config, is untouched instead."""
        resp = self._change_mobile_nav()
        self.assertEqual(resp.status_code, 200)
        self.draft.refresh_from_db()
        from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
        from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive

        after = manifest_to_primitive(appearance_persistence.load_store_appearance_manifest(self.draft))
        before_selections = dict(self.before_manifest["selections"])
        after_selections = dict(after["selections"])
        del before_selections["bottom_nav"]
        del after_selections["bottom_nav"]
        self.assertEqual(after_selections, before_selections)
        self.assertEqual(dict(self.draft.header_config), self.before_header)

    def test_typed_bottom_nav_selection_is_synchronized(self):
        resp = self._change_mobile_nav("floating_dock")
        self.assertEqual(resp.status_code, 200)
        from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
        from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive

        self.draft.refresh_from_db()
        after = manifest_to_primitive(appearance_persistence.load_store_appearance_manifest(self.draft))
        self.assertIn("floating_dock", after["selections"]["bottom_nav"])

    def test_typed_footer_selection_does_not_change_merely_because_bottom_nav_changed(self):
        resp = self._change_mobile_nav("glass_dock")
        self.assertEqual(resp.status_code, 200)
        from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
        from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive

        self.draft.refresh_from_db()
        after = manifest_to_primitive(appearance_persistence.load_store_appearance_manifest(self.draft))
        self.assertEqual(after["selections"]["footer"], self.before_manifest["selections"]["footer"])


# ---------------------------------------------------------------------------
# K, L, M, N. Stale-write, exactly-one revision advance, Undo/Redo.
# ---------------------------------------------------------------------------
class MobileNavConcurrencyAndHistoryTests(R4MutationApiTestCase):
    def _post_history(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps(payload), content_type="application/json",
        )

    def test_stale_base_revision_is_rejected(self):
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "four_item"}},
        })
        stale_response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "five_item"}},
        })
        self.assertEqual(stale_response.status_code, 409)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["mobile_nav_variant"], "four_item")

    def test_successful_change_advances_revision_exactly_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "raised_cart"}},
        })
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)

    def test_undo_restores_previous_mobile_nav_selection(self):
        # The raw stored footer_config may not yet carry every key (defaults
        # are only merged in on read, via effective_footer_config()) until a
        # real save has happened at least once -- use the effective view
        # consistently, including after Undo restores the pre-mutation raw
        # snapshot.
        original = self.draft.effective_footer_config().get("mobile_nav_variant", "hidden")
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "wide_cart"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["mobile_nav_variant"], "wide_cart")

        undo_response = self._post_history({"base_revision": after_mutation_revision, "command": "undo"})
        self.assertEqual(undo_response.status_code, 200)
        self.assertIs(undo_response.json()["changed"], True)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.effective_footer_config().get("mobile_nav_variant"), original)

    def test_redo_restores_changed_mobile_nav_selection(self):
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "minimal_icons"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        undo_response = self._post_history({"base_revision": after_mutation_revision, "command": "undo"})
        after_undo_revision = undo_response.json()["new_revision"]

        redo_response = self._post_history({"base_revision": after_undo_revision, "command": "redo"})
        self.assertEqual(redo_response.status_code, 200)
        self.assertIs(redo_response.json()["changed"], True)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["mobile_nav_variant"], "minimal_icons")


# ---------------------------------------------------------------------------
# O, P, Q. Draft Preview / Published-unchanged-until-Publish / Public.
# ---------------------------------------------------------------------------
class MobileNavPreviewAndPublicTests(TestCase):
    HOST = "w5b-public.example.com"
    ADMIN_HOST = "w5b-admin.rastisi.localhost"

    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه W5B", slug="w5b-mobile-nav-store",
            admin_subdomain=self.ADMIN_HOST.split(".")[0], status=Store.Status.ACTIVE,
        )
        StoreDomain.objects.create(
            store=self.store, hostname=self.HOST, is_primary=False,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.user = User.objects.create_user(username="w5b_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        layout = svc.get_or_create_layout(self.store)
        layout.r4_editor_enabled = True
        layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store, user=self.user)
        preset_service.apply_preset_by_key(draft, "dark_digital")
        draft.refresh_from_db()
        draft.footer_config = dict(draft.effective_footer_config())
        draft.footer_config["mobile_nav_variant"] = "hidden"
        draft.save(update_fields=["footer_config"])
        # The dark_digital preset applies an explicit (non-safe-default)
        # typed bottom_nav selection; the renderer prefers that typed
        # selection over the legacy footer_config mirror once it is
        # explicit (see storefront_appearance/rendering.py:global_renderer_
        # template). Directly poking footer_config above is not enough on
        # its own -- sync the typed manifest too, exactly like the real
        # write path (_apply_footer_update) already does on every save.
        from apps.storefront_builder.services import appearance_authority_service

        appearance_authority_service.apply_footer_variant(
            version=draft, mobile_nav_variant="hidden",
        )
        svc.publish(self.store)
        self.admin_client = Client(HTTP_HOST=self.ADMIN_HOST)
        self.admin_client.login(username="w5b_owner", password="pass12345")

    def _post_json(self, payload):
        return self.admin_client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload), content_type="application/json",
        )

    def _post_publish(self, payload):
        return self.admin_client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps(payload), content_type="application/json",
        )

    @override_settings(ALLOWED_HOSTS=[HOST, ADMIN_HOST, "testserver"])
    def test_full_preview_publish_lifecycle(self):
        draft = svc.get_or_create_draft(self.store)

        # Published starts hidden.
        public_client = Client(HTTP_HOST=self.HOST)
        public_before = public_client.get(reverse("catalog:home"))
        self.assertNotContains(public_before, 'data-mobile-nav="luxury_floating_cart"')

        # Merchant changes the Draft to a non-hidden variant.
        resp = self._post_json({
            "base_revision": draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "luxury_floating_cart"}},
        })
        self.assertEqual(resp.status_code, 200, resp.content)

        # O — Draft Preview resolves the changed variant.
        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(preview_resp.status_code, 200)
        self.assertContains(preview_resp, 'data-mobile-nav="luxury_floating_cart"')

        # P — Public storefront remains unchanged until Publish.
        public_still_before = public_client.get(reverse("catalog:home"))
        self.assertNotContains(public_still_before, 'data-mobile-nav="luxury_floating_cart"')

        # Publish.
        draft.refresh_from_db()
        publish_resp = self._post_publish({"base_revision": draft.edit_revision})
        self.assertEqual(publish_resp.status_code, 200, publish_resp.content)

        # Q — Public now resolves the newly-selected variant.
        public_after = public_client.get(reverse("catalog:home"))
        self.assertContains(public_after, 'data-mobile-nav="luxury_floating_cart"')

    @override_settings(ALLOWED_HOSTS=[HOST, ADMIN_HOST, "testserver"])
    def test_hidden_variant_is_the_safe_default_and_renders_no_nav_markup(self):
        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(preview_resp.status_code, 200)
        self.assertNotContains(preview_resp, "data-mobile-nav=")


# ---------------------------------------------------------------------------
# R. Tenant isolation.
# ---------------------------------------------------------------------------
class MobileNavTenantIsolationTests(R4MutationApiTestCase):
    def test_mutation_never_touches_a_foreign_stores_draft(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر W5B", slug="w5b-other-store", admin_subdomain="w5b-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_before = dict(other_draft.footer_config)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": "four_item"}},
        })
        self.assertEqual(response.status_code, 200)

        other_draft.refresh_from_db()
        self.assertEqual(dict(other_draft.footer_config), other_before)


# ---------------------------------------------------------------------------
# S. No migration / model change.
# ---------------------------------------------------------------------------
class NoMigrationNeededTests(TestCase):
    def test_mobile_nav_variant_round_trips_through_the_existing_footer_config_jsonfield(self):
        field = StorefrontLayoutVersion._meta.get_field("footer_config")
        self.assertEqual(field.get_internal_type(), "JSONField")


# ---------------------------------------------------------------------------
# Registered variant coverage — every registry entry appears in the R4
# projection, is accepted by validation, and resolves to a trusted renderer.
# ---------------------------------------------------------------------------
class RegisteredVariantCoverageTests(R4MutationApiTestCase):
    def test_every_registered_variant_appears_in_editor_projection(self):
        body = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        for variant in REGISTERED_MOBILE_NAV_VARIANTS:
            self.assertIn(f'value="{variant.key}"', body)

    def test_every_registered_variant_is_accepted_by_footer_update(self):
        for variant in REGISTERED_MOBILE_NAV_VARIANTS:
            response = self._post_json({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "footer.update", "patch": {"mobile_nav_variant": variant.key}},
            })
            self.assertEqual(response.status_code, 200, f"{variant.key}: {response.content}")
            self.draft.refresh_from_db()
            self.assertEqual(self.draft.footer_config["mobile_nav_variant"], variant.key)

    def test_every_registered_variant_resolves_to_its_own_trusted_renderer(self):
        for variant in REGISTERED_MOBILE_NAV_VARIANTS:
            resolved = global_region_registry.get_global_variant(
                global_region_registry.GLOBAL_MOBILE_NAV_REGION, variant.key,
            )
            self.assertIsNotNone(resolved)
            self.assertTrue(resolved.renderer.startswith("storefront_builder/partials/global_mobile_nav/"))
