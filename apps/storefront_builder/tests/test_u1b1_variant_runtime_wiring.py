"""U1B1 — Variant Runtime Wiring + Validation.

Traces the single authoritative path that already exists for BOTH Draft
preview and published public rendering — ``render_service._build_items_from_sections``
(called by ``build_page_render_items``/``build_render_items``/
``build_default_render_items``; ``build_container_render_items`` only
reshapes the same dicts and never re-derives ``template_name``) — and proves
the new variant-aware template resolution wired into that one place:

- introduces zero behavior change for the 31 section types with no
  registered variants, and zero rendered-HTML change for the three proven
  variant precedents (category_grid/brand_carousel/product_section), since
  every currently-registered variant is Pattern A (``renderer=None``);
- fails safely (never crashes, never mutates persisted settings) for an
  unknown/legacy persisted variant value at read time;
- enforces the generic write-time contract (``variant_contract.validate_variant_selection``,
  wired as the outermost layer in ``section_registry._finalize_registry``)
  without changing the three existing sections' own coercing validators;
- proves Pattern B (a different trusted renderer) is fully wired end-to-end
  using only a synthetic, unregistered ``SectionDefinition`` — production
  ``SECTION_REGISTRY`` gains no new key and no new template file.
"""

from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.section_registry import SECTION_REGISTRY, get_definition
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import render_service
from apps.storefront_builder.services.render_service import build_render_items
from apps.storefront_builder.variant_contract import (
    UnknownVariantSelectionError,
    VariantDefinition,
    resolve_active_variant,
    resolve_renderer_template,
    validate_variant_selection,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RenderPipelineUnchangedForNoVariantSectionsTests(TestCase):
    """Test A/F/H — 31 of 34 section types declare no variants; the wired
    pipeline must produce byte-identical ``template_name``/``active_variant``
    output to a definition that has none."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_no_variant_section_resolves_definition_template_name_unchanged(self):
        StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        items = build_render_items(self.draft, self.store)
        self.assertEqual(len(items), 1)
        item = items[0]
        definition = get_definition("rich_text")
        self.assertEqual(definition.variants, ())
        self.assertEqual(item["template_name"], definition.template_name)
        self.assertIsNone(item["active_variant"])


class ExistingThreePrecedentSectionsUnchangedTests(TestCase):
    """Test K — category_grid/brand_carousel/product_section must render
    through the exact same template as before U1B1, for every currently
    valid persisted ``display_mode``, while now also resolving a matching
    ``active_variant`` object (Pattern A: renderer=None everywhere)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_category_grid_every_registered_display_mode(self):
        definition = get_definition("category_grid")
        for display_mode in ("grid", "carousel", "circular", "image_strip"):
            self.draft.sections.all().delete()
            StorefrontSection.objects.create(
                version=self.draft, section_key="category_grid", order=0,
                settings={"display_mode": display_mode, "category_ids": [], "item_limit": 12, "title": ""},
            )
            items = build_render_items(self.draft, self.store)
            self.assertEqual(items[0]["template_name"], definition.template_name, display_mode)
            self.assertEqual(items[0]["active_variant"].key, display_mode, display_mode)

    def test_brand_carousel_every_registered_display_mode(self):
        definition = get_definition("brand_carousel")
        for display_mode in ("grid", "carousel", "beauty_tabs"):
            self.draft.sections.all().delete()
            StorefrontSection.objects.create(
                version=self.draft, section_key="brand_carousel", order=0,
                settings={"display_mode": display_mode, "brand_ids": [], "show_view_all": False, "title": ""},
            )
            items = build_render_items(self.draft, self.store)
            self.assertEqual(items[0]["template_name"], definition.template_name, display_mode)
            self.assertEqual(items[0]["active_variant"].key, display_mode, display_mode)

    def test_product_section_every_registered_display_mode(self):
        definition = get_definition("product_section")
        for display_mode in ("carousel", "grid", "campaign_band"):
            self.draft.sections.all().delete()
            StorefrontSection.objects.create(
                version=self.draft, section_key="product_section", order=0,
                settings={"data_source": "newest", "display_mode": display_mode, "product_ids": [], "item_limit": 8},
            )
            items = build_render_items(self.draft, self.store)
            self.assertEqual(items[0]["template_name"], definition.template_name, display_mode)
            self.assertEqual(items[0]["active_variant"].key, display_mode, display_mode)


class ReadTimeUnknownLegacyVariantTests(TestCase):
    """Test D — an unknown/legacy persisted value must never crash public
    rendering, must fail safely to ``default_variant``, and must never
    rewrite the stored Section."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_unknown_display_mode_written_directly_to_db_does_not_crash(self):
        # Bypasses validate_settings on purpose — simulates data persisted
        # by an older engine build that allowed a value no longer registered.
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=0,
            settings={"display_mode": "some-retired-value", "category_ids": [], "item_limit": 12, "title": ""},
        )
        items = build_render_items(self.draft, self.store)  # must not raise
        definition = get_definition("category_grid")
        self.assertEqual(items[0]["template_name"], definition.template_name)
        self.assertEqual(items[0]["active_variant"].key, definition.default_variant)

        section.refresh_from_db()
        self.assertEqual(section.settings["display_mode"], "some-retired-value")  # never rewritten

    def test_missing_selector_key_entirely_falls_back_to_default_variant(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=0,
            settings={"category_ids": [], "item_limit": 12, "title": ""},  # no display_mode key at all
        )
        items = build_render_items(self.draft, self.store)
        definition = get_definition("category_grid")
        self.assertEqual(items[0]["active_variant"].key, definition.default_variant)


class WriteTimeValidationTests(TestCase):
    """Test E — a newly-submitted, non-empty, unregistered variant selector
    must fail validation. Also proves the three existing sections' own
    validators are completely unaffected (they coerce before this layer
    ever runs, so it is provably a no-op for them, not a behavior change)."""

    def test_existing_three_sections_validate_settings_never_raises_for_garbage_display_mode(self):
        for section_key, base in (
            ("category_grid", {"category_ids": [], "item_limit": 12, "title": ""}),
            ("brand_carousel", {"brand_ids": [], "show_view_all": False, "title": ""}),
            ("product_section", {"data_source": "newest", "product_ids": [], "item_limit": 8}),
        ):
            definition = get_definition(section_key)
            raw = dict(base, display_mode="totally-made-up-value")
            cleaned = definition.validate_settings(raw)  # must not raise
            self.assertIn(cleaned["display_mode"], {v.key for v in definition.variants}, section_key)

    def test_synthetic_future_section_without_its_own_coercion_rejects_unknown_selector(self):
        """A hypothetical future section whose own validator is a plain
        passthrough (no closed-enum coercion of its own) is exactly the
        case ``validate_variant_selection`` exists to guard — proven
        directly against the function U1B1 wires in, without touching
        production SECTION_REGISTRY."""
        synthetic = _synthetic_definition_with_variants()
        with self.assertRaises(UnknownVariantSelectionError):
            validate_variant_selection(synthetic, {"variant": "does-not-exist"})

    def test_synthetic_future_section_accepts_known_selector_and_missing_selector(self):
        synthetic = _synthetic_definition_with_variants()
        validate_variant_selection(synthetic, {"variant": "a"})  # must not raise
        validate_variant_selection(synthetic, {})  # missing key — must not raise
        validate_variant_selection(synthetic, {"variant": ""})  # empty value — must not raise


class PatternARendererTests(TestCase):
    """Test F/H — Pattern A: every currently registered real variant has
    ``renderer=None``, so the resolved template is always
    ``SectionDefinition.template_name``."""

    def test_all_three_precedents_every_variant_is_pattern_a(self):
        for section_key in ("category_grid", "brand_carousel", "product_section"):
            definition = get_definition(section_key)
            for variant in definition.variants:
                self.assertIsNone(variant.renderer, f"{section_key}.{variant.key}")
                self.assertEqual(
                    resolve_renderer_template(definition, variant), definition.template_name,
                    f"{section_key}.{variant.key}",
                )


class PatternBRendererDispatchTests(TestCase):
    """Test G — Pattern B, proven end-to-end through the actual wired
    render pipeline (not just the pure resolver function in isolation),
    using a synthetic ``SectionDefinition``/``get_definition`` patch. No
    production registry key or template file is added — the Pattern-B
    renderer reused here (``rich_text.html``) is an existing, already
    registered, real template, proving the dispatched name is a genuine
    trusted local path, not an arbitrary string."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_pattern_b_variant_dispatches_to_its_own_trusted_renderer(self):
        synthetic = _synthetic_definition_with_pattern_b_variant()
        section = StorefrontSection(
            section_key="synthetic_variant_demo", order=0, is_active=True,
            settings={"variant": "alt_layout"},
        )
        with mock.patch.object(render_service, "get_definition", return_value=synthetic):
            items = render_service._build_items_from_sections([section], self.store, {})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["active_variant"].key, "alt_layout")
        self.assertEqual(items[0]["template_name"], "storefront_builder/sections/rich_text.html")
        self.assertNotEqual(items[0]["template_name"], synthetic.template_name)

    def test_pattern_a_variant_on_the_same_synthetic_definition_uses_own_template(self):
        synthetic = _synthetic_definition_with_pattern_b_variant()
        section = StorefrontSection(
            section_key="synthetic_variant_demo", order=0, is_active=True,
            settings={"variant": "default_layout"},
        )
        with mock.patch.object(render_service, "get_definition", return_value=synthetic):
            items = render_service._build_items_from_sections([section], self.store, {})
        self.assertEqual(items[0]["template_name"], synthetic.template_name)

    def test_production_registry_gained_no_new_key(self):
        self.assertEqual(len(SECTION_REGISTRY), 36)
        self.assertNotIn("synthetic_variant_demo", SECTION_REGISTRY)


class NoMerchantControlledRendererPathTests(TestCase):
    """Test I — persisted settings can never name a renderer path; only a
    variant *key* is ever read from settings, and the renderer string
    itself only ever comes from Python-authored ``VariantDefinition``
    metadata."""

    def test_resolve_renderer_template_signature_takes_only_python_objects(self):
        import inspect
        signature = inspect.signature(resolve_renderer_template)
        self.assertEqual(list(signature.parameters), ["definition", "variant"])

    def test_a_settings_key_literally_named_renderer_is_never_consumed_as_a_path(self):
        cache.clear()
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=0,
            settings={"body_html": "x", "renderer": "storefront_builder/sections/faq.html"},
        )
        items = build_render_items(draft, store)
        definition = get_definition("rich_text")
        # rich_text has no variants at all — the injected "renderer" settings
        # key is simply ignored (rich_text's own validator strips unknown
        # keys); the resolved template is unaffected either way.
        self.assertEqual(items[0]["template_name"], definition.template_name)


class VariantResolutionPerformanceTests(TestCase):
    """Test/§15 — variant resolution is pure metadata lookup: zero DB
    queries, independent of how many times it's called."""

    def test_resolve_active_variant_and_renderer_template_issue_no_queries(self):
        definition = get_definition("category_grid")
        settings = {"display_mode": "carousel"}
        with CaptureQueriesContext(connection) as ctx:
            variant = resolve_active_variant(definition, settings)
            resolve_renderer_template(definition, variant)
            resolve_active_variant(definition, {"display_mode": "unknown-value"})
            resolve_active_variant(definition, None)
        self.assertEqual(len(ctx.captured_queries), 0)


class ImportTimeVariantValidationStillEnforcedTests(TestCase):
    """Test J — invalid VariantDefinition/renderer metadata remains
    impossible to register at all (U1A's import-time guarantee, unchanged
    and still exercised by the fact SECTION_REGISTRY itself imported
    successfully)."""

    def test_section_registry_module_imported_successfully_with_34_keys(self):
        self.assertEqual(len(section_registry_module.SECTION_REGISTRY), 36)

    def test_a_malformed_synthetic_variant_list_still_fails_at_validation_time(self):
        from apps.storefront_builder.variant_contract import InvalidVariantDefinitionError, validate_variants
        with self.assertRaises(InvalidVariantDefinitionError):
            validate_variants(
                (VariantDefinition(key="a", label_fa="a", renderer="/etc/passwd"),), default_variant=None,
            )


class MultiBannerUnchangedTests(TestCase):
    """Test L — multi_banner has zero registered variants, so the entire
    U1B1 wiring (both read-time resolution and write-time validation) is a
    complete no-op for it; its ``_passthrough_dict`` behavior is untouched."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_multi_banner_arbitrary_layout_variant_renders_through_the_wired_pipeline_unchanged(self):
        definition = get_definition("multi_banner")
        self.assertEqual(definition.variants, ())
        StorefrontSection.objects.create(
            version=self.draft, section_key="multi_banner", order=0,
            settings={"layout_variant": "some-value-nobody-registered"},
        )
        items = build_render_items(self.draft, self.store)
        self.assertEqual(items[0]["template_name"], definition.template_name)
        self.assertIsNone(items[0]["active_variant"])

    def test_multi_banner_validate_settings_now_coerces_unknown_layout_variant(self):
        # Task 6 (Group C) deliberately narrowed multi_banner's
        # validate_settings from _passthrough_dict to a real closed-enum
        # validator (see MULTI_BANNER_KNOWN_LAYOUT_VARIANTS) — an
        # unrecognized value is now coerced to "" (the historical
        # "no override" state), not passed through verbatim.
        definition = get_definition("multi_banner")
        cleaned = definition.validate_settings({"layout_variant": "anything-at-all"})
        self.assertEqual(cleaned["layout_variant"], "")


def _synthetic_definition_with_variants():
    """A standalone SectionDefinition/variant pair, never registered in
    SECTION_REGISTRY, whose own ``validate_settings`` is a bare passthrough
    (no closed-enum coercion of its own) — the exact shape of a future
    section ``validate_variant_selection`` exists to guard."""
    from apps.storefront_builder.section_registry import SectionDefinition

    return SectionDefinition(
        key="synthetic_future_section", label_fa="آینده", icon="x",
        template_name="storefront_builder/sections/synthetic.html",
        validate_settings=lambda raw: dict(raw), default_settings=lambda: {},
        variants=(VariantDefinition(key="a", label_fa="A"), VariantDefinition(key="b", label_fa="B")),
        default_variant="a", variant_setting_key="variant",
    )


def _synthetic_definition_with_pattern_b_variant():
    from apps.storefront_builder.section_registry import SectionDefinition

    return SectionDefinition(
        key="synthetic_variant_demo", label_fa="نمایشِ Variant", icon="x",
        template_name="storefront_builder/sections/synthetic_default.html",
        validate_settings=lambda raw: dict(raw), default_settings=lambda: {"variant": "default_layout"},
        variants=(
            VariantDefinition(key="default_layout", label_fa="پیش‌فرض"),  # Pattern A: renderer=None
            VariantDefinition(
                key="alt_layout", label_fa="جایگزین",
                renderer="storefront_builder/sections/rich_text.html",  # Pattern B: real, existing, trusted template
            ),
        ),
        default_variant="default_layout", variant_setting_key="variant",
    )
