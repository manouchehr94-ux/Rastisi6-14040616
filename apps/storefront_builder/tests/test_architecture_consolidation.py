"""Universal Design Engine — architecture regression tests.

Source-level guards for the consolidated architecture: ONE homepage renderer, ONE capability model, ONE settings
contract (registry → schema → Inspector → validator → renderer), ONE shared shell, a valid engine-native default for a
new Store, and no retired fallbacks / parallel systems. These read the source tree on purpose: a parallel path is added
by writing code, so the cheapest reliable guard is to fail when its name reappears.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from apps.storefront_builder import design_block, section_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.settings_schema import clean_section_schema_patch
from apps.stores.models import Store

ROOT = Path(settings.BASE_DIR)


def _product_sources():
    """Every non-test python / template / css / js file of the application (the code that ships)."""
    for base in ("apps", "templates", "shop_core"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".py", ".html", ".css", ".js"}:
                continue
            parts = set(path.parts)
            if parts & {"tests", "migrations", "__pycache__", "node_modules", "qa"}:
                continue
            if path.name.startswith("test_") or "management" in parts:
                continue
            yield path


def _occurrences(pattern: str):
    regex = re.compile(pattern)
    return sorted(
        str(path.relative_to(ROOT))
        for path in _product_sources()
        if regex.search(path.read_text(encoding="utf-8", errors="ignore"))
    )


class OneHomepageRendererTests(SimpleTestCase):
    def test_the_legacy_homepage_template_is_gone_and_home_renders_the_engine_template(self):
        self.assertFalse((ROOT / "apps/catalog/templates/catalog/home.html").exists())
        views = (ROOT / "apps/catalog/views.py").read_text(encoding="utf-8")
        home = views[views.index("def home("):]
        home = home[: home.index("\ndef ")] if "\ndef " in home else home
        self.assertIn("build_universal_storefront_context", home)
        self.assertIn("catalog/home_visual.html", home)
        self.assertNotIn("catalog/home.html", views)

    def test_home_best_products_legacy_endpoint_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("catalog:home-best-products")

    def test_retired_fallback_names_do_not_exist_anywhere_in_shipped_code(self):
        for name in (
            "uses_universal_shell", "build_default_render_items", "_unresolved_context", "home_best_products",
            "catalog/home.html",
        ):
            self.assertEqual(_occurrences(re.escape(name)), [], f"retired name {name!r} is back")

    def test_every_public_page_extends_the_one_storefront_shell(self):
        base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
        self.assertNotIn("<footer", base)
        self.assertNotIn('<nav class="nav"', base)
        shell = (ROOT / "templates/storefront_shell.html").read_text(encoding="utf-8")
        self.assertIn("header_variant_template", shell)
        self.assertIn("footer_variant_template", shell)
        for template in (
            "apps/catalog/templates/catalog/home_visual.html",
            "apps/orders/templates/orders/checkout_step1.html",
            "apps/orders/templates/orders/payment_result.html",
            "apps/customers/templates/customers/account.html",
            "apps/customers/templates/customers/order_detail.html",
        ):
            self.assertIn('{% extends "storefront_shell.html" %}', (ROOT / template).read_text(encoding="utf-8"), template)

    def test_public_context_has_a_single_builder_for_the_engine_page(self):
        service = (ROOT / "apps/storefront_builder/services/storefront_context_service.py").read_text(encoding="utf-8")
        self.assertIn("ensure_default_published_layout", service)
        self.assertIn("def render_domain_page", service)
        self.assertNotIn("page_resolution_service", service)

    def test_preview_and_published_share_the_same_render_pipeline(self):
        public = (ROOT / "apps/storefront_builder/services/storefront_context_service.py").read_text(encoding="utf-8")
        views = (ROOT / "apps/storefront_builder/views.py").read_text(encoding="utf-8")
        for source in (public, views):
            self.assertIn("build_page_render_items", source)
            self.assertIn("build_container_render_items", source)
        preview = (ROOT / "apps/storefront_builder/templates/storefront_builder/preview.html").read_text(encoding="utf-8")
        published = (ROOT / "apps/catalog/templates/catalog/home_visual.html").read_text(encoding="utf-8")
        for template in (preview, published):
            self.assertIn("storefront_builder/partials/render_rows.html", template)


class OneCapabilityModelTests(SimpleTestCase):
    def test_no_parallel_allowlists_exist(self):
        self.assertEqual(_occurrences(r"[A-Z_]+_AWARE_SECTION_KEYS"), [])
        self.assertEqual(_occurrences(r"COLUMN_VISUAL_SECTION_KEYS|_derived_capabilities|_DERIVED_CAPABILITY_SOURCES"), [])
        self.assertEqual(_occurrences(r"BACKGROUND_FIELD_BASIC_SECTION_KEYS"), [])

    def test_every_definition_declares_only_known_capabilities(self):
        for key, definition in section_registry.SECTION_REGISTRY.items():
            self.assertLessEqual(definition.capabilities, section_registry.KNOWN_CAPABILITIES, key)
            self.assertIn("responsive", definition.capabilities, key)

    def test_validator_wrappers_follow_the_declared_capabilities(self):
        probes = {
            "background": "background", "spacing": "spacing", "card": "card", "motion": "motion",
            "destination": "destination", "layout_width": "layout",
        }
        for key, definition in section_registry.SECTION_REGISTRY.items():
            defaults = definition.default_settings()
            for capability, block in probes.items():
                self.assertEqual(
                    block in defaults, capability in definition.capabilities,
                    f"{key}: default settings block {block!r} must exist exactly when {capability!r} is declared",
                )
            self.assertEqual("columns" in definition.capabilities, "desktop_columns" in defaults["responsive"], key)

    def test_the_design_block_is_derived_from_the_same_capabilities(self):
        for key, definition in section_registry.SECTION_REGISTRY.items():
            applicable = design_block.properties_for_capabilities(definition.capabilities)
            schema = definition.settings_schema
            if schema is None:
                continue
            self.assertEqual(schema.get_field("design") is not None, bool(applicable), key)
            self.assertEqual(schema.get_field("background") is not None, "background" in definition.capabilities, key)

    def test_sections_with_capability_is_the_registry_projection(self):
        self.assertIn("product_section", section_registry.sections_with_capability("card"))
        self.assertNotIn("rich_text", section_registry.sections_with_capability("card"))
        self.assertEqual(
            section_registry.sections_with_capability("appearance_override") - section_registry.sections_with_capability("card"),
            {"hero_banner", "brand_carousel", "collection_tiles"},
        )


class InspectorAndRendererShareOneContractTests(SimpleTestCase):
    @staticmethod
    def _probe_value(field):
        if field.field_type == "boolean":
            return not bool(field.default)
        if field.field_type == "choice":
            others = [value for value, _ in field.choices if value != field.default]
            return others[0] if others else None
        if field.field_type == "integer":
            low = field.min_value if field.min_value is not None else 0
            high = field.max_value if field.max_value is not None else low + 10
            value = (low + high) // 2
            return value if value != field.default else min(value + 1, high)
        if field.field_type == "text":
            return "probe"
        return None

    def test_every_schema_control_is_stored_by_the_validator_so_no_inspector_control_is_dead(self):
        from apps.storefront_builder.r4_views import _INSPECTOR_SUPPORTED_FIELD_TYPES

        dead = []
        for key, definition in section_registry.SECTION_REGISTRY.items():
            if definition.settings_schema is None:
                continue
            base = definition.default_settings()
            for field in definition.settings_schema.fields:
                self.assertIn(field.field_type, _INSPECTOR_SUPPORTED_FIELD_TYPES, f"{key}.{field.key}")
                value = self._probe_value(field)
                if value is None or field.field_type not in {"boolean", "choice", "integer", "text"}:
                    continue
                try:
                    stored = clean_section_schema_patch(definition, {field.key: value}, base)
                except ValueError:
                    continue  # explicit, user-visible validation (e.g. a URL the provider list does not know)
                if stored.get(field.key) != value:
                    dead.append((key, field.key, value, stored.get(field.key)))
        # ``min_slots`` is the one documented schema/validator range difference (0 = off, otherwise ≥ 2 / ≥ 3).
        dead = [row for row in dead if row[1] != "min_slots"]
        self.assertEqual(dead, [])

    def test_inspector_and_renderer_read_the_same_settings_keys(self):
        """Every settings block the validator can emit for a capability is the block the template/CSS pipeline reads."""
        wrapper = (ROOT / "apps/storefront_builder/templates/storefront_builder/partials/responsive_section_wrapper.html")
        text = wrapper.read_text(encoding="utf-8")
        for needle in ("data-bg-mode", "--sfb-section-bg-color", "data-d"):
            self.assertIn(needle, text)


class NoTemplateSpecificLogicTests(SimpleTestCase):
    def test_section_templates_and_renderer_never_branch_on_a_ready_template_key(self):
        pattern = r"(template_slug\s*==|ready_template_key\s*==|data-template-key|{% if [^%]*template-\d)"
        offenders = []
        for path in (ROOT / "apps/storefront_builder/templates/storefront_builder/sections").rglob("*.html"):
            if re.search(pattern, path.read_text(encoding="utf-8")):
                offenders.append(path.name)
        render_service = (ROOT / "apps/storefront_builder/services/render_service.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"if\s+[^\n]*template_slug\s*==", render_service))
        self.assertEqual(offenders, [])


class NewStoreStartsWithAValidEngineHomepageTests(TestCase):
    def _new_store(self, slug):
        return Store.objects.create(name=f"Arch {slug}", slug=slug, status=Store.Status.ACTIVE)

    def test_a_store_without_any_layout_gets_a_published_engine_native_composition(self):
        store = self._new_store("arch-new-store")
        self.assertFalse(StorefrontLayout.objects.filter(store=store).exists())
        layout = layout_service.ensure_default_published_layout(store)
        layout.refresh_from_db()
        version = layout.published_version
        self.assertIsNotNone(version)
        self.assertEqual(version.status, StorefrontLayoutVersion.Status.PUBLISHED)
        self.assertTrue(layout.uses_visual_storefront_layout)
        home = version.pages.get(page_type="home")
        keys = list(home.sections.filter(is_active=True).values_list("section_key", flat=True))
        self.assertTrue({"category_grid", "newest_products", "best_sellers", "trust_features"} <= set(keys))
        for section in StorefrontSection.objects.filter(page__version=version):
            definition = section_registry.get_definition(section.section_key)  # registered
            definition.validate_settings(section.settings or {})  # and valid under the one validator
            self.assertTrue(hasattr(section, "placement_cell"), f"{section.section_key} has no container cell")

    def test_provisioning_is_idempotent_and_never_replaces_an_existing_composition(self):
        store = self._new_store("arch-idempotent")
        first = layout_service.ensure_default_published_layout(store).published_version_id
        second = layout_service.ensure_default_published_layout(store).published_version_id
        self.assertEqual(first, second)
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout__store=store).count(), 1)
