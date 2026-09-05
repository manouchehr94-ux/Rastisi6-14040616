import copy
import json

from django.core.cache import cache
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import (
    APPEARANCE_CONFIG_DEFAULTS,
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
)
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    STORE_APPEARANCE_CONFIG_KEY,
    load_store_appearance_manifest,
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
)
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


class R4StoreAppearanceMutationTestCase(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def _post_mutation(self, mutation, *, base_revision=None):
        if base_revision is None:
            self.draft.refresh_from_db()
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _manifest(self):
        self.draft.refresh_from_db()
        return manifest_to_primitive(load_store_appearance_manifest(self.draft))

    def _history_count(self):
        return StorefrontEditHistoryEntry.objects.filter(
            draft_version=self.draft,
        ).count()

    def _component_mutation(self, family, component_key, *, draft_id=None):
        return {
            "type": "appearance.component.update",
            "draft_id": self.draft.pk if draft_id is None else draft_id,
            "family": family,
            "component_key": component_key,
        }

    def _template_mutation(self, key, version, *, draft_id=None):
        return {
            "type": "appearance.template.apply",
            "draft_id": self.draft.pk if draft_id is None else draft_id,
            "template_key": key,
            "template_version": version,
        }


class IndependentComponentMutationTests(R4StoreAppearanceMutationTestCase):
    def test_component_update_changes_only_requested_family(self):
        before = self._manifest()
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation(
            self._component_mutation("header", "header.dark_tech.v1")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        after = self._manifest()
        self.assertEqual(after["selections"]["header"], "header.dark_tech.v1")
        for family, component_key in before["selections"].items():
            if family != "header":
                self.assertEqual(after["selections"][family], component_key)
        self.assertEqual(after["settings"], before["settings"])
        self.assertEqual(self._history_count(), before_history + 1)

    def test_invalid_component_key_writes_nothing(self):
        before = self._manifest()
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation(
            self._component_mutation("header", "header.does_not_exist.v1")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_appearance_component")
        self.assertEqual(self._manifest(), before)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)

    def test_unknown_family_writes_nothing(self):
        before = self._manifest()
        starting_revision = self.draft.edit_revision

        response = self._post_mutation(
            self._component_mutation("unknown_family", "header.dark_tech.v1")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_appearance_family")
        self.assertEqual(self._manifest(), before)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)

    def test_valid_noop_does_not_increment_revision_or_history(self):
        current = self._manifest()["selections"]["header"]
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation(
            self._component_mutation("header", current)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)


class ManifestApplyMutationTests(R4StoreAppearanceMutationTestCase):
    def test_identical_manifest_is_a_semantic_noop(self):
        candidate = self._manifest()
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation({
            "type": "appearance.manifest.apply",
            "draft_id": self.draft.pk,
            "manifest": candidate,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)

    def test_complete_manifest_applies_atomically_with_one_revision_and_history_entry(self):
        candidate = self._manifest()
        candidate["selections"]["header"] = "header.dark_tech.v1"
        candidate["selections"]["footer"] = "footer.premium_columns.v1"
        candidate["selections"]["motion"] = "motion.none.v1"
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation({
            "type": "appearance.manifest.apply",
            "draft_id": self.draft.pk,
            "manifest": candidate,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._manifest(), candidate)
        self.assertEqual(self._history_count(), before_history + 1)

    def test_invalid_manifest_is_fully_rolled_back(self):
        before = self._manifest()
        candidate = copy.deepcopy(before)
        candidate["selections"]["header"] = "header.not_registered.v1"
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation({
            "type": "appearance.manifest.apply",
            "draft_id": self.draft.pk,
            "manifest": candidate,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_store_appearance_manifest")
        self.assertEqual(self._manifest(), before)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)

    def test_unsupported_manifest_schema_version_is_rejected_without_write(self):
        before = self._manifest()
        candidate = copy.deepcopy(before)
        candidate["schema_version"] = 999
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation({
            "type": "appearance.manifest.apply",
            "draft_id": self.draft.pk,
            "manifest": candidate,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_store_appearance_manifest")
        self.assertEqual(self._manifest(), before)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)


class VersionedTemplateMutationTests(R4StoreAppearanceMutationTestCase):
    def test_versioned_ready_template_applies_as_one_semantic_mutation(self):
        preset = layout_preset_registry.get_layout_preset("dark_digital")
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation(
            self._template_mutation(preset.key, preset.version)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.template_provenance["template"],
            {"key": preset.key, "version": preset.version},
        )
        self.assertEqual(self._history_count(), before_history + 1)
        self.assertTrue(
            self.draft.home_page().sections.exclude(template_slot_key="").exists()
        )


    def test_template_baseline_snapshot_matches_final_typed_appearance(self):
        preset = layout_preset_registry.get_layout_preset("dark_digital")
        response = self._post_mutation(
            self._template_mutation(preset.key, preset.version)
        )
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.template_baseline_snapshot["appearance"],
            self.draft.appearance_config,
        )

    def test_template_version_mismatch_is_rejected_before_any_write(self):
        preset = layout_preset_registry.get_layout_preset("dark_digital")
        before_fingerprint = self.draft.compute_fingerprint()
        starting_revision = self.draft.edit_revision
        before_history = self._history_count()

        response = self._post_mutation(
            self._template_mutation(preset.key, "definitely-not-current")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "template_version_mismatch")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.compute_fingerprint(), before_fingerprint)
        self.assertEqual(self.draft.edit_revision, starting_revision)
        self.assertEqual(self._history_count(), before_history)

    def test_internal_non_ready_preset_is_not_exposed_as_appearance_template(self):
        preset = layout_preset_registry.get_layout_preset("dense_catalog")
        response = self._post_mutation(
            self._template_mutation(preset.key, preset.version)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "unknown_appearance_template")


class AppearanceMutationIsolationTests(R4StoreAppearanceMutationTestCase):
    def test_stale_revision_rejects_appearance_mutation_without_write(self):
        self.draft.edit_revision = 4
        self.draft.save(update_fields=["edit_revision"])
        before = self._manifest()
        before_history = self._history_count()

        response = self._post_mutation(
            self._component_mutation("header", "header.dark_tech.v1"),
            base_revision=3,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_revision")
        self.assertEqual(self._manifest(), before)
        self.assertEqual(self._history_count(), before_history)

    def test_foreign_draft_id_is_rejected_without_cross_store_access(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر A6",
            slug="r4-a6-other-store",
            admin_subdomain="r4-a6-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        own_before = self._manifest()
        other_before = manifest_to_primitive(
            load_store_appearance_manifest(other_draft)
        )
        own_revision = self.draft.edit_revision
        other_revision = other_draft.edit_revision

        response = self._post_mutation(
            self._component_mutation(
                "header", "header.dark_tech.v1", draft_id=other_draft.pk,
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "draft_not_found")
        self.assertEqual(self._manifest(), own_before)
        other_draft.refresh_from_db()
        self.assertEqual(
            manifest_to_primitive(load_store_appearance_manifest(other_draft)),
            other_before,
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, own_revision)
        self.assertEqual(other_draft.edit_revision, other_revision)

    def test_template_apply_does_not_mutate_published_composition_or_metadata(self):
        published = layout_service.publish(self.store, user=self.staff)
        published_fingerprint = published.compute_fingerprint()
        published_provenance = copy.deepcopy(published.template_provenance)
        published_snapshot = copy.deepcopy(published.template_baseline_snapshot)

        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        preset = layout_preset_registry.get_layout_preset("dark_digital")
        response = self._post_mutation(
            self._template_mutation(preset.key, preset.version)
        )

        self.assertEqual(response.status_code, 200)
        published.refresh_from_db()
        self.assertEqual(published.compute_fingerprint(), published_fingerprint)
        self.assertEqual(published.template_provenance, published_provenance)
        self.assertEqual(published.template_baseline_snapshot, published_snapshot)

    def test_published_version_remains_unchanged_until_publish(self):
        published = layout_service.publish(self.store, user=self.staff)
        published_manifest = manifest_to_primitive(
            load_store_appearance_manifest(published)
        )
        published_fingerprint = published.compute_fingerprint()

        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        response = self._post_mutation(
            self._component_mutation("header", "header.dark_tech.v1")
        )

        self.assertEqual(response.status_code, 200)
        published.refresh_from_db()
        self.assertEqual(
            manifest_to_primitive(load_store_appearance_manifest(published)),
            published_manifest,
        )
        self.assertEqual(published.compute_fingerprint(), published_fingerprint)


class LegacySelectorManifestSynchronizationTests(R4StoreAppearanceMutationTestCase):
    def test_template_switch_persists_owned_fields_when_manifest_sync_is_noop(self):
        # boutique keeps the default motion="subtle", so its typed motion
        # selection does not change. The legacy template-owned appearance fields
        # must still be persisted before Manifest synchronization short-circuits.
        response = self._post_mutation({
            "type": "appearance.update",
            "patch": {"template_slug": "boutique", "font": "Georgia"},
        })

        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("template_slug"), "boutique")
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(self._manifest()["selections"]["motion"], "motion.subtle.v1")

    def test_preexisting_a5_stale_legacy_sibling_is_preserved_by_component_update(self):
        # Simulate a Draft created on A5: the typed manifest was persisted, then
        # an older legacy mutation changed the live Header without updating it.
        stale_manifest = self._manifest()
        appearance = dict(self.draft.appearance_config or {})
        appearance[STORE_APPEARANCE_CONFIG_KEY] = stale_manifest
        self.draft.appearance_config = appearance
        self.draft.header_config = {
            **self.draft.effective_header_config(),
            "header_variant": "dark_tech",
        }
        self.draft.save(update_fields=["appearance_config", "header_config"])

        response = self._post_mutation(
            self._component_mutation("footer", "footer.premium_columns.v1")
        )

        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.effective_header_config()["header_variant"], "dark_tech")
        manifest = self._manifest()
        self.assertEqual(manifest["selections"]["header"], "header.dark_tech.v1")
        self.assertEqual(manifest["selections"]["footer"], "footer.premium_columns.v1")

    def test_legacy_header_update_keeps_manifest_in_sync_and_later_component_change_preserves_it(self):
        response = self._post_mutation({
            "type": "header.update",
            "patch": {"header_variant": "dark_tech"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._manifest()["selections"]["header"],
            "header.dark_tech.v1",
        )

        response = self._post_mutation(
            self._component_mutation("footer", "footer.premium_columns.v1")
        )
        self.assertEqual(response.status_code, 200)
        manifest = self._manifest()
        self.assertEqual(manifest["selections"]["header"], "header.dark_tech.v1")
        self.assertEqual(manifest["selections"]["footer"], "footer.premium_columns.v1")


    def test_legacy_footer_update_keeps_typed_manifest_in_sync(self):
        response = self._post_mutation({
            "type": "footer.update",
            "patch": {"footer_variant": "premium_columns"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._manifest()["selections"]["footer"],
            "footer.premium_columns.v1",
        )

    def test_legacy_motion_update_keeps_typed_manifest_in_sync(self):
        response = self._post_mutation({
            "type": "appearance.update",
            "patch": {"motion": "none"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._manifest()["selections"]["motion"], "motion.none.v1")


class TemplateUndoRedoIdentityTests(R4StoreAppearanceMutationTestCase):
    def test_undo_redo_restores_template_metadata_and_slot_identity(self):
        first = layout_preset_registry.get_layout_preset("dense_marketplace")
        second = layout_preset_registry.get_layout_preset("warm_boutique")

        first_response = self._post_mutation(
            self._template_mutation(first.key, first.version)
        )
        self.assertEqual(first_response.status_code, 200)
        self.draft.refresh_from_db()
        first_provenance = copy.deepcopy(self.draft.template_provenance)
        first_snapshot = copy.deepcopy(self.draft.template_baseline_snapshot)
        first_slots = list(
            self.draft.home_page().sections.order_by("order", "id").values_list(
                "template_slot_key", flat=True,
            )
        )

        second_response = self._post_mutation(
            self._template_mutation(second.key, second.version)
        )
        self.assertEqual(second_response.status_code, 200)
        self.draft.refresh_from_db()
        second_provenance = copy.deepcopy(self.draft.template_provenance)
        second_snapshot = copy.deepcopy(self.draft.template_baseline_snapshot)
        second_slots = list(
            self.draft.home_page().sections.order_by("order", "id").values_list(
                "template_slot_key", flat=True,
            )
        )

        undo = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "command": "undo",
            }),
            content_type="application/json",
        )
        self.assertEqual(undo.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.template_provenance, first_provenance)
        self.assertEqual(self.draft.template_baseline_snapshot, first_snapshot)
        self.assertEqual(
            list(self.draft.home_page().sections.order_by("order", "id").values_list(
                "template_slot_key", flat=True,
            )),
            first_slots,
        )

        redo = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({
                "base_revision": self.draft.edit_revision,
                "command": "redo",
            }),
            content_type="application/json",
        )
        self.assertEqual(redo.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.template_provenance, second_provenance)
        self.assertEqual(self.draft.template_baseline_snapshot, second_snapshot)
        self.assertEqual(
            list(self.draft.home_page().sections.order_by("order", "id").values_list(
                "template_slot_key", flat=True,
            )),
            second_slots,
        )


class CanonicalManifestPristineDraftTests(R4StoreAppearanceMutationTestCase):
    def _empty_global_only_draft(self, manifest):
        for page in self.draft.pages.all():
            page.containers.all().delete()
            page.sections.all().delete()
        self.draft.header_config = {}
        self.draft.footer_config = {}
        self.draft.template_provenance = {}
        self.draft.template_baseline_snapshot = {}
        self.draft.appearance_config = {
            **APPEARANCE_CONFIG_DEFAULTS,
            STORE_APPEARANCE_CONFIG_KEY: manifest,
        }
        self.draft.save(update_fields=[
            "header_config", "footer_config", "template_provenance",
            "template_baseline_snapshot", "appearance_config",
        ])

    def test_canonical_default_manifest_does_not_make_empty_draft_meaningful(self):
        default_manifest = manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        self._empty_global_only_draft(default_manifest)

        result = layout_service.checkpoint_draft_before_replacement(
            self.store, reason_label="A6 pristine test", user=self.staff,
        )

        self.assertEqual(result.pk, self.draft.pk)

    def test_non_default_manifest_is_meaningful_even_when_draft_has_no_sections(self):
        manifest = manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        manifest["selections"]["header"] = "header.dark_tech.v1"
        self._empty_global_only_draft(manifest)

        result = layout_service.checkpoint_draft_before_replacement(
            self.store, reason_label="A6 meaningful test", user=self.staff,
        )

        self.assertNotEqual(result.pk, self.draft.pk)



class R4AppearanceAuthorityPreservationTests(R4StoreAppearanceMutationTestCase):
    """Phase 1 (Task 4) — R4 appearance/global-region commands delegate their
    state transformation to the canonical authority service, so the reserved
    typed manifest and unrelated canonical keys survive an ordinary R4
    appearance patch. R4 keeps ownership of lock/revision/history.
    """

    def _seed_manifest(self, **selections):
        raw = copy.deepcopy(
            manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        )
        raw["selections"].update(selections)
        persist_store_appearance_manifest(self.draft, raw)
        self.draft.refresh_from_db()
        return raw

    def test_r4_appearance_patch_preserves_manifest_and_unrelated_keys(self):
        # Seed a non-default typed manifest and an opaque canonical key.
        self._seed_manifest(hero="hero.split.v1", card="card.luxury_dark.v1")
        self.draft.refresh_from_db()
        old_manifest = copy.deepcopy(
            self.draft.appearance_config[STORE_APPEARANCE_CONFIG_KEY]
        )
        config = dict(self.draft.appearance_config)
        config["__opaque_canonical_probe__"] = {"kept": True}
        self.draft.appearance_config = config
        self.draft.save(update_fields=["appearance_config"])
        starting_revision = self.draft.edit_revision

        # An ordinary R4 appearance patch that does not change motion/template
        # (so manifest sync is not triggered) — the typed manifest must survive.
        response = self._post_mutation({
            "type": "appearance.update",
            "patch": {"font": "Tahoma"},
        })

        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY),
            old_manifest,
            "R4 ordinary appearance patch must preserve the typed manifest",
        )
        self.assertEqual(
            self.draft.appearance_config.get("__opaque_canonical_probe__"),
            {"kept": True},
            "R4 ordinary appearance patch must preserve unrelated opaque keys",
        )
        # R4 still owns revision monotonicity.
        self.assertEqual(
            response.json()["new_revision"], starting_revision + 1
        )

    def test_r4_header_update_keeps_manifest_and_unrelated_families(self):
        self._seed_manifest(
            header="header.legacy_default.v1",
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
        )
        response = self._post_mutation({
            "type": "header.update",
            "patch": {"header_variant": "dark_tech"},
        })
        self.assertEqual(response.status_code, 200)
        after = self._manifest()["selections"]
        self.assertEqual(after["header"], "header.dark_tech.v1")
        # Unrelated families preserved.
        self.assertEqual(after["hero"], "hero.split.v1")
        self.assertEqual(after["card"], "card.luxury_dark.v1")

    def test_r4_footer_update_keeps_manifest_and_unrelated_families(self):
        self._seed_manifest(
            footer="footer.legacy_default.v1",
            hero="hero.split.v1",
        )
        response = self._post_mutation({
            "type": "footer.update",
            "patch": {"footer_variant": "premium_columns"},
        })
        self.assertEqual(response.status_code, 200)
        after = self._manifest()["selections"]
        self.assertEqual(after["footer"], "footer.premium_columns.v1")
        self.assertEqual(after["hero"], "hero.split.v1")
