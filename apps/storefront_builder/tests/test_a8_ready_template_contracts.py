"""A8 contract tests for immutable, versioned Ready Template DNA."""

from copy import deepcopy

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)


class ReadyTemplateContractTests(SimpleTestCase):
    """Exercise registry behavior without a database or renderer dependency."""

    def setUp(self):
        super().setUp()
        self._latest_before = dict(lpr.LAYOUT_PRESET_REGISTRY)
        self._versions_before = dict(lpr.LAYOUT_PRESET_VERSION_REGISTRY)

    def tearDown(self):
        lpr.LAYOUT_PRESET_REGISTRY.clear()
        lpr.LAYOUT_PRESET_REGISTRY.update(self._latest_before)
        lpr.LAYOUT_PRESET_VERSION_REGISTRY.clear()
        lpr.LAYOUT_PRESET_VERSION_REGISTRY.update(self._versions_before)
        super().tearDown()

    def _manifest(self):
        return {
            "schema_version": 1,
            "selections": dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
            "settings": {},
        }

    def _ready(self, *, key="__a8_contract__", version="1", manifest=None):
        if manifest is None:
            manifest = self._manifest()
        return lpr.LayoutPresetDefinition(
            key=key,
            label_fa="قرارداد",
            description_fa="قرارداد آماده",
            version=version,
            is_ready_template=True,
            store_appearance=manifest,
        )

    def test_exact_versions_are_immutable_and_latest_is_numeric_not_import_order(self):
        """Registering an older version later must not replace the numeric latest."""
        newest = self._ready(version="10")
        older = self._ready(version="2")

        lpr.register_layout_preset(newest)
        lpr.register_layout_preset(older)

        self.assertIs(lpr.get_layout_preset_version(newest.key, "2"), older)
        self.assertIs(lpr.get_layout_preset_version(newest.key, "10"), newest)
        self.assertIs(lpr.get_layout_preset(newest.key), newest)
        self.assertEqual(
            [preset.version for preset in lpr.list_ready_templates() if preset.key == newest.key],
            ["10"],
        )

    def test_duplicate_exact_version_is_rejected_without_mutating_registries(self):
        original = self._ready(version="1")
        duplicate = self._ready(version="1")
        lpr.register_layout_preset(original)
        latest_before = dict(lpr.LAYOUT_PRESET_REGISTRY)
        versions_before = dict(lpr.LAYOUT_PRESET_VERSION_REGISTRY)

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(duplicate)

        self.assertEqual(lpr.LAYOUT_PRESET_REGISTRY, latest_before)
        self.assertEqual(lpr.LAYOUT_PRESET_VERSION_REGISTRY, versions_before)

    def test_empty_and_non_numeric_versions_are_rejected(self):
        for version in ("", " ", "v2", "2.0", "01", "0"):
            with self.subTest(version=version):
                with self.assertRaises(lpr.InvalidLayoutPresetError):
                    lpr.register_layout_preset(self._ready(key=f"__a8_version_{version!r}__", version=version))

    def test_new_ready_template_requires_a_manifest(self):
        preset = self._ready(manifest=None)
        preset = lpr.LayoutPresetDefinition(
            key=preset.key,
            label_fa=preset.label_fa,
            description_fa=preset.description_fa,
            version=preset.version,
            is_ready_template=True,
        )

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(preset)

    def test_historical_ready_versions_have_complete_manifests_after_task_four(self):
        """The eight pre-A8 exact identities remain strict, complete recipes."""
        expected_identities = {
            ("dense_marketplace", "2"),
            ("premium_leather", "2"),
            ("warm_boutique", "2"),
            ("fashion_promo_catalog", "7"),
            ("playful_lifestyle", "1"),
            ("utility_catalog", "1"),
            ("editorial_jewelry", "2"),
            ("dark_digital", "2"),
        }
        self.assertFalse(hasattr(lpr, "_LEGACY_READY_TEMPLATE_IDENTITIES"))
        for identity in expected_identities:
            preset = lpr.get_layout_preset_version(*identity)
            self.assertIsNotNone(preset, identity)
            self.assertIsNotNone(preset.store_appearance, identity)
            self.assertEqual(preset.store_appearance["schema_version"], 1)

    def test_new_version_of_legacy_ready_key_requires_a_manifest(self):
        preset = lpr.LayoutPresetDefinition(
            key="dense_marketplace",
            label_fa="قرارداد",
            description_fa="نسخه جدید",
            version="3",
            is_ready_template=True,
        )

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(preset)

    def test_ready_template_rejects_missing_schema_version(self):
        manifest = self._manifest()
        manifest.pop("schema_version")
        latest_before = dict(lpr.LAYOUT_PRESET_REGISTRY)
        versions_before = dict(lpr.LAYOUT_PRESET_VERSION_REGISTRY)

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

        self.assertEqual(lpr.LAYOUT_PRESET_REGISTRY, latest_before)
        self.assertEqual(lpr.LAYOUT_PRESET_VERSION_REGISTRY, versions_before)

    def test_ready_template_rejects_incomplete_family_selections(self):
        manifest = self._manifest()
        manifest["selections"].pop("bottom_nav")

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

    def test_ready_template_rejects_unknown_component_keys(self):
        manifest = self._manifest()
        manifest["selections"]["header"] = "header.unknown.v1"

        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(self._ready(manifest=manifest))

    def test_ready_template_rejects_renderer_and_template_payloads(self):
        for payload in (
            {"renderer_path": "apps.evil.renderer"},
            {"template_path": "evil/template.html"},
            {"settings": {"hero": {"javascript": "alert(1)"}}},
        ):
            with self.subTest(payload=payload):
                manifest = deepcopy(self._manifest())
                manifest.update(payload)
                with self.assertRaises(lpr.InvalidLayoutPresetError):
                    lpr.register_layout_preset(self._ready(manifest=manifest))



class AllReadyTemplatesDeclareCompleteManifestTests(SimpleTestCase):
    """Phase 1 (Task 5, Step 12) — every latest Ready Template declares a
    COMPLETE, valid typed manifest covering the canonical family set. This is a
    declaration-completeness contract only (no DB, no renderer); it does not
    certify browser output.
    """

    def test_all_latest_ready_templates_declare_valid_complete_manifest(self):
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        required_families = set(COMPONENT_FAMILIES)
        ready_templates = lpr.list_ready_templates()
        self.assertTrue(ready_templates, "there must be at least one Ready Template")

        for preset in ready_templates:
            identity = f"{preset.key}/{preset.version}"
            with self.subTest(preset=identity):
                self.assertIsNotNone(preset.store_appearance, identity)
                # Validates as a complete StoreAppearanceManifest (require_complete
                # defaults to True) — raises InvalidStoreAppearanceContract otherwise.
                validated = validate_store_appearance_manifest(preset.store_appearance)
                self.assertEqual(
                    set(validated.manifest.selections),
                    required_families,
                    identity,
                )
