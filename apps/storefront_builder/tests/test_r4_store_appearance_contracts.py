from dataclasses import FrozenInstanceError

from django.test import SimpleTestCase

from apps.storefront_builder.storefront_appearance.contracts import (
    ComponentDefinition,
    ComponentFamilyDefinition,
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
    validate_component_catalog,
    validate_family_catalog,
    validate_manifest_families,
)
from apps.storefront_builder.storefront_appearance.families import (
    COMPONENT_FAMILIES,
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)


class StoreAppearanceFamilyContractTests(SimpleTestCase):
    def test_initial_family_catalog_is_complete_and_ordered(self):
        self.assertEqual(
            tuple(COMPONENT_FAMILIES),
            (
                "header",
                "mega_menu",
                "hero",
                "layout",
                "product_view",
                "card",
                "badge",
                "motion",
                "footer",
                "bottom_nav",
                # P5-W2 — reversible occasion Theme appearance-token family.
                "theme",
            ),
        )
        validate_family_catalog(COMPONENT_FAMILIES.values())

    def test_family_definition_is_immutable_and_normalizes_capabilities(self):
        definition = ComponentFamilyDefinition(
            key="future_family",
            label_fa="خانواده آینده",
            storage_adapter_key="future_adapter",
            safe_default_component_key="future_family.off.v1",
            renderer_role="global_region",
            optional=True,
            capabilities={"touch", "rtl"},
        )
        self.assertEqual(definition.capabilities, frozenset({"touch", "rtl"}))
        with self.assertRaises(FrozenInstanceError):
            definition.key = "changed"

    def test_duplicate_family_key_is_rejected(self):
        family = COMPONENT_FAMILIES["header"]
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "duplicate family key"):
            validate_family_catalog((family, family))

    def test_unsafe_or_missing_family_contract_is_rejected(self):
        invalid_values = ("", "Header", "header.path", "../header", "header/path")
        for key in invalid_values:
            with self.subTest(key=key):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    ComponentFamilyDefinition(
                        key=key,
                        label_fa="هدر",
                        storage_adapter_key="header_region",
                        safe_default_component_key="header.legacy_default.v1",
                        renderer_role="global_region",
                    )

    def test_optional_family_requires_explicit_off_capable_default(self):
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "optional family"):
            ComponentFamilyDefinition(
                key="announcement_bar",
                label_fa="نوار اعلان",
                storage_adapter_key="announcement_adapter",
                safe_default_component_key="announcement_bar.standard.v1",
                renderer_role="global_region",
                optional=True,
            )


class StoreAppearanceComponentContractTests(SimpleTestCase):
    def test_component_definition_is_semantic_versioned_and_deeply_immutable(self):
        metadata = {"recommended_with": ["layout.editorial.v1"]}
        component = ComponentDefinition(
            key="header.editorial_centered.v1",
            family_key="header",
            version=1,
            label_fa="هدر تحریریه مرکزی",
            registry_reference="global_header:editorial_centered",
            capabilities={"mega_menu", "rtl"},
            compatibility=metadata,
        )
        metadata["recommended_with"].append("layout.changed.v1")

        self.assertEqual(component.capabilities, frozenset({"mega_menu", "rtl"}))
        self.assertEqual(
            component.compatibility["recommended_with"],
            ("layout.editorial.v1",),
        )
        with self.assertRaises(TypeError):
            component.compatibility["recommended_with"] += ("layout.changed.v1",)

    def test_component_key_must_match_family_and_version(self):
        invalid = (
            {"key": "footer.editorial.v1", "family_key": "header", "version": 1},
            {"key": "header/editorial/v1", "family_key": "header", "version": 1},
            {"key": "header...v1", "family_key": "header", "version": 1},
            {"key": "header.editorial.v2", "family_key": "header", "version": 1},
            {"key": "header.editorial.v1", "family_key": "header", "version": 0},
            {"key": "header.editorial.v1", "family_key": "header", "version": True},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    ComponentDefinition(
                        label_fa="نمونه",
                        registry_reference="registry:sample",
                        **values,
                    )

    def test_renderer_paths_and_executable_registry_references_are_rejected(self):
        unsafe_references = (
            "../template.html",
            "/tmp/template.html",
            "C:\\template.html",
            "storefront_builder/header.html",
            "<script>alert(1)</script>",
        )
        for reference in unsafe_references:
            with self.subTest(reference=reference):
                with self.assertRaises(InvalidStoreAppearanceContract):
                    ComponentDefinition(
                        key="header.safe.v1",
                        family_key="header",
                        version=1,
                        label_fa="نمونه",
                        registry_reference=reference,
                    )

    def test_duplicate_component_key_is_rejected(self):
        component = ComponentDefinition(
            key="header.safe.v1",
            family_key="header",
            version=1,
            label_fa="نمونه",
            registry_reference="global_header:safe",
        )
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "duplicate component key"):
            validate_component_catalog((component, component), COMPONENT_FAMILIES)

    def test_material_replacement_requires_new_versioned_identity(self):
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "deprecated_by"):
            ComponentDefinition(
                key="header.old.v1",
                family_key="header",
                version=1,
                label_fa="قدیمی",
                registry_reference="global_header:old",
                status="deprecated",
            )


class StoreAppearanceManifestContractTests(SimpleTestCase):
    def test_default_manifest_has_one_safe_selection_per_family(self):
        validate_manifest_families(
            DEFAULT_STORE_APPEARANCE_MANIFEST,
            COMPONENT_FAMILIES,
        )
        self.assertEqual(
            set(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
            set(COMPONENT_FAMILIES),
        )
        for family_key, definition in COMPONENT_FAMILIES.items():
            self.assertEqual(
                DEFAULT_STORE_APPEARANCE_MANIFEST.selections[family_key],
                definition.safe_default_component_key,
            )

    def test_manifest_is_deeply_immutable(self):
        raw_settings = {"header": {"density": "compact"}}
        manifest = StoreAppearanceManifest(
            schema_version=1,
            selections=dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
            settings=raw_settings,
        )
        raw_settings["header"]["density"] = "changed"
        self.assertEqual(manifest.settings["header"]["density"], "compact")
        with self.assertRaises(TypeError):
            manifest.selections["header"] = "header.changed.v1"

    def test_unknown_or_missing_manifest_family_is_rejected(self):
        selections = dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections)
        selections["floating_cart"] = "floating_cart.off.v1"
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "unknown families"):
            validate_manifest_families(
                StoreAppearanceManifest(schema_version=1, selections=selections),
                COMPONENT_FAMILIES,
            )

        selections = dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections)
        selections.pop("hero")
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "missing families"):
            validate_manifest_families(
                StoreAppearanceManifest(schema_version=1, selections=selections),
                COMPONENT_FAMILIES,
            )

    def test_unknown_manifest_schema_version_is_rejected(self):
        with self.assertRaisesRegex(InvalidStoreAppearanceContract, "schema_version"):
            StoreAppearanceManifest(
                schema_version=2,
                selections=dict(DEFAULT_STORE_APPEARANCE_MANIFEST.selections),
            )
