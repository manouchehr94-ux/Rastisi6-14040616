"""Capability metadata wiring.

``SectionDefinition.capabilities`` (declared on each registry definition,
validated against ``section_registry.KNOWN_CAPABILITIES``) is the single source
editor/server-side gating code queries, through
``SectionDefinition.supports_capability(name, *, variant=None)``. There is no
parallel allowlist: ``section_registry._finalize_registry``'s wrappers
(``_with_card``, ``_with_background``, ...) read the very same declaration.

Nothing here changes ``validate_settings``/``default_settings``/rendered
HTML/merchant-visible editor controls.
"""


from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.storefront_builder.section_registry import (
    SECTION_REGISTRY,
    SectionDefinition,
    get_definition,
    list_definitions,
)
from apps.storefront_builder.variant_contract import VariantDefinition
from apps.stores.models import Store

User = get_user_model()
HOST = "sfb-u1b2-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SupportsCapabilityCorrectnessTests(TestCase):
    """Test A/B/C — ``supports_capability`` agrees with raw ``.capabilities``
    membership, for every section and every capability, including the
    "no capability at all" case."""

    _CAPABILITIES = (
        "card", "background", "spacing", "motion", "destination",
        "layout_width", "layout_height", "columns", "columns_visual",
    )

    def test_supports_capability_matches_raw_capabilities_membership(self):
        for definition in list_definitions():
            for name in self._CAPABILITIES:
                self.assertEqual(
                    definition.supports_capability(name),
                    name in definition.capabilities,
                    f"{definition.key}: supports_capability({name!r}) disagrees "
                    f"with raw .capabilities membership",
                )

    def test_supports_capability_false_for_unknown_capability_name(self):
        for definition in list_definitions():
            self.assertFalse(definition.supports_capability("no_such_capability_xyz"))

    def test_announcement_bar_has_no_layout_gating_capabilities(self):
        """``announcement_bar`` is a representative "no capability" section — only
        the unconditional ``responsive`` capability applies. (``blog_posts`` used to be the example; it now owns a
        background + spacing so a Ready Template can put the journal on a coloured band.)"""
        definition = get_definition("announcement_bar")
        for capability in self._CAPABILITIES:
            self.assertFalse(definition.supports_capability(capability), capability)
        self.assertTrue(definition.supports_capability("responsive"))


class SupportsCapabilityVariantCombinationTests(TestCase):
    """Test D — variant-level capability resolution via ``supports_capability``'s
    optional ``variant`` argument, matching ``variant_contract.resolve_capabilities``'s
    union semantics. Uses only a synthetic, unregistered definition/variant —
    no production ``SECTION_REGISTRY`` key is touched."""

    def test_variant_with_no_extra_capabilities_does_not_change_the_answer(self):
        definition = get_definition("category_grid")
        variant = definition.variants[0]
        self.assertEqual(variant.capabilities, frozenset())
        for capability in ("card", "background", "responsive"):
            self.assertEqual(
                definition.supports_capability(capability),
                definition.supports_capability(capability, variant=variant),
            )

    def test_synthetic_variant_with_its_own_capability_widens_the_answer(self):
        synthetic_variant = VariantDefinition(
            key="synthetic_variant_u1b2",
            label_fa="Variantِ آزمایشیِ U1B2",
            capabilities=frozenset({"synthetic_capability_u1b2"}),
        )
        synthetic_definition = SectionDefinition(
            key="synthetic_section_u1b2",
            label_fa="بخشِ آزمایشیِ U1B2",
            icon="star",
            template_name="storefront_builder/sections/rich_text.html",
            validate_settings=lambda raw: dict(raw),
            default_settings=lambda: {},
        )
        self.assertFalse(synthetic_definition.supports_capability("synthetic_capability_u1b2"))
        self.assertTrue(
            synthetic_definition.supports_capability(
                "synthetic_capability_u1b2", variant=synthetic_variant,
            )
        )


class NoProductionVariantDeclaresCapabilitiesTests(TestCase):
    """U1B2 architecture tripwire — intentionally NOT a regular behavioral
    test. ``SectionDefinition.supports_capability(..., variant=...)`` and
    ``VariantDefinition.capabilities`` already support resolving the
    *effective* (section + active variant) capability union (see
    ``SupportsCapabilityVariantCombinationTests`` above) — but current
    production editor gating (``views.py``) and server-side settings
    validation (``section_registry._finalize_registry``'s ``_with_motion``/
    ``_with_card``/etc. wrappers) both resolve gating from the base
    ``SectionDefinition`` only; neither resolves the section's active
    variant at all. This is safe *only* as long as every real,
    registered ``VariantDefinition`` in ``SECTION_REGISTRY`` declares an
    empty ``capabilities`` set. If a future change adds
    ``VariantDefinition(capabilities={...})`` to a production section
    without first making editor/server-side gating variant-aware, that
    variant's extra capability would be reachable through
    ``supports_capability(name, variant=...)`` but invisible to both the
    merchant editor and write-time validation — a silent UI/server
    mismatch. This test fails loudly the moment that happens, forcing a
    deliberate decision instead of an accidental one."""

    def test_no_production_variant_declares_additional_capabilities(self):
        offenders = [
            (definition.key, variant.key, variant.capabilities)
            for definition in SECTION_REGISTRY.values()
            for variant in definition.variants
            if variant.capabilities
        ]
        self.assertEqual(
            offenders, [],
            "Production variant capabilities cannot be introduced until merchant "
            "editor and server-side settings gating resolve the active variant. "
            f"Offending (section_key, variant_key, capabilities) entries: {offenders}",
        )


class SectionDefinitionIsAuthoritativeSourceTests(TestCase):
    """Test E — ``.capabilities`` (and therefore ``supports_capability``) is
    populated purely from ``_finalize_registry``'s union of the definition's
    own declared capabilities; no DB access,
    no per-request computation."""

    def test_capabilities_identical_across_repeated_lookups(self):
        first = get_definition("product_section").capabilities
        second = get_definition("product_section").capabilities
        self.assertEqual(first, second)
        self.assertIs(SECTION_REGISTRY["product_section"], SECTION_REGISTRY["product_section"])

    def test_supports_capability_performs_no_database_queries(self):
        definition = get_definition("hero_banner")
        with self.assertNumQueries(0):
            for capability in ("card", "background", "motion", "responsive", "nonexistent"):
                definition.supports_capability(capability)


class RegistryInvariantsUnchangedByU1B2Tests(TestCase):
    """Test K/L/M — the invariants U1B2 must not disturb: registry size,
    hero_banner/image_slider both present and unmerged, multi_banner's
    passthrough validator untouched, no new template/store/family
    conditional was introduced anywhere in ``section_registry.py``."""

    def test_section_registry_still_has_exactly_34_keys(self):
        self.assertEqual(len(SECTION_REGISTRY), 40)   # Hero Stage: + hero_stage

    def test_hero_banner_and_image_slider_both_still_present(self):
        self.assertIn("hero_banner", SECTION_REGISTRY)
        self.assertIn("image_slider", SECTION_REGISTRY)
        self.assertNotEqual(
            SECTION_REGISTRY["hero_banner"].template_name,
            SECTION_REGISTRY["image_slider"].template_name,
        )

    def test_multi_banner_layout_variant_now_coerces_malformed_value(self):
        # Task 6 (Group C) narrowed multi_banner's validate_settings to a
        # real closed-enum validator — a malformed/unrecognized value is
        # now coerced to "" (the historical "no override" state) instead
        # of passing through verbatim.
        definition = get_definition("multi_banner")
        cleaned = definition.validate_settings({"layout_variant": {"anything": "goes", "n": 1}})
        self.assertEqual(cleaned["layout_variant"], "")

    def test_persisted_settings_for_representative_sections_still_validate_identically(self):
        """A previously-saved settings dict for a card/motion/background/column
        section must still validate to the same cleaned shape after the
        views.py migration (which only changed *how* gating is decided, not
        the validators themselves)."""
        product_definition = get_definition("product_section")
        cleaned = product_definition.validate_settings({
            "data_source": "newest", "display_mode": "carousel",
            "card": {"show_price": True},
            "responsive": {"desktop_columns": 4},
        })
        self.assertEqual(cleaned["display_mode"], "carousel")
        self.assertTrue(cleaned["card"]["show_price"])
        self.assertEqual(cleaned["responsive"]["desktop_columns"], 4)
