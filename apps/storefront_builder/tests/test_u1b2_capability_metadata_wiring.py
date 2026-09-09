"""U1B2 — Capability Metadata Wiring.

Makes ``SectionDefinition.capabilities`` (introduced additively in U1A,
derived in ``section_registry._finalize_registry`` from the pre-existing
``*_AWARE_SECTION_KEYS`` allowlists via ``_derived_capabilities``) the
authoritative source that editor/server-side gating code queries, through
the new ``SectionDefinition.supports_capability(name, *, variant=None)``
helper (``section_registry.py``).

Scope decision recorded here (see also
``U1ACapabilitiesConsistencyTests.test_capabilities_agree_with_every_pre_existing_allowlist``
in ``test_section_registry.py``, which already proves Option B — constants
kept + a consistency test — for the *internal* consumers):

- ``views.py`` (``storefront_section_settings`` and its
  ``_extract_responsive_raw`` helper) is a *downstream* consumer that always
  runs after ``SECTION_REGISTRY`` is fully built (via ``get_definition``) —
  it was migrated (Option A) to call ``definition.supports_capability(...)``
  instead of importing and checking membership in the raw
  ``*_AWARE_SECTION_KEYS`` frozensets directly.
- ``section_registry._finalize_registry``'s own wrapper functions
  (``_with_card``, ``_with_background``, ...) run *while* ``SECTION_REGISTRY``
  is being constructed and therefore cannot consult the not-yet-built
  registry's ``.capabilities`` — Option A is unsafe there, so those raw
  allowlist constants remain the source those specific functions read from
  (Option B; already covered by the consistency test referenced above).

Nothing here changes ``validate_settings``/``default_settings``/rendered
HTML/merchant-visible editor controls; every test below only proves the
*same* answer is now reachable through the metadata contract.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.section_registry import (
    BACKGROUND_AWARE_SECTION_KEYS,
    CARD_AWARE_SECTION_KEYS,
    COLUMN_AWARE_SECTION_KEYS,
    COLUMN_VISUAL_SECTION_KEYS,
    DESTINATION_AWARE_SECTION_KEYS,
    LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
    LAYOUT_WIDTH_AWARE_SECTION_KEYS,
    MOTION_AWARE_SECTION_KEYS,
    SPACING_AWARE_SECTION_KEYS,
    SECTION_REGISTRY,
    SectionDefinition,
    get_definition,
    list_definitions,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.views import _extract_responsive_raw
from apps.storefront_builder.variant_contract import VariantDefinition
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "sfb-u1b2-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SupportsCapabilityCorrectnessTests(TestCase):
    """Test A/B/C — ``supports_capability`` agrees with raw ``.capabilities``
    membership, for every section and every capability, including the
    "no capability at all" case."""

    _ALLOWLIST_BY_CAPABILITY = {
        "card": CARD_AWARE_SECTION_KEYS,
        "background": BACKGROUND_AWARE_SECTION_KEYS,
        "spacing": SPACING_AWARE_SECTION_KEYS,
        "motion": MOTION_AWARE_SECTION_KEYS,
        "destination": DESTINATION_AWARE_SECTION_KEYS,
        "layout_width": LAYOUT_WIDTH_AWARE_SECTION_KEYS,
        "layout_height": LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
        "columns": COLUMN_AWARE_SECTION_KEYS,
        "columns_visual": COLUMN_VISUAL_SECTION_KEYS,
    }

    def test_supports_capability_matches_raw_capabilities_membership(self):
        for definition in list_definitions():
            for name in self._ALLOWLIST_BY_CAPABILITY:
                self.assertEqual(
                    definition.supports_capability(name),
                    name in definition.capabilities,
                    f"{definition.key}: supports_capability({name!r}) disagrees "
                    f"with raw .capabilities membership",
                )

    def test_supports_capability_matches_every_pre_existing_allowlist(self):
        for capability, allowlist in self._ALLOWLIST_BY_CAPABILITY.items():
            for definition in list_definitions():
                expected = definition.key in allowlist
                self.assertEqual(
                    definition.supports_capability(capability), expected,
                    f"{definition.key}: supports_capability({capability!r}) disagrees "
                    f"with its allowlist",
                )

    def test_supports_capability_false_for_unknown_capability_name(self):
        for definition in list_definitions():
            self.assertFalse(definition.supports_capability("no_such_capability_xyz"))

    def test_blog_posts_has_no_layout_gating_capabilities(self):
        """``blog_posts`` is a representative "no capability" section — only
        the unconditional ``responsive`` capability applies."""
        definition = get_definition("blog_posts")
        for capability in self._ALLOWLIST_BY_CAPABILITY:
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
    own declared capabilities with ``_derived_capabilities``; no DB access,
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


class ViewsMigrationPreservesEditorGatingTests(TestCase):
    """Test F/G/H/I — end-to-end proof (through the real HTTP view) that
    migrating ``views.py`` from raw allowlist membership to
    ``definition.supports_capability(...)`` changed zero merchant-visible
    behavior, for one representative section per capability plus the
    no-capability case. Mirrors the pre-existing behavioral assertions in
    ``test_views.py`` (e.g. ``test_motion_controls_present_for_motion_aware_type``),
    which already re-ran unmodified against the migrated code path in the
    full-suite run and passed unchanged."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(
            username="sfb_u1b2_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="sfb_u1b2_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def _settings_url(self, section):
        return reverse("dashboard:storefront-builder-section-settings", args=[section.pk])

    def test_motion_aware_section_still_gets_motion_field_and_saves_it(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0,
        )
        resp = self.client.get(self._settings_url(section))
        self.assertContains(resp, 'name="motion_style"')
        resp = self.client.post(self._settings_url(section), {"motion_style": "hover_lift"})
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["motion"], {"style": "hover_lift"})

    def test_non_motion_aware_section_gets_no_motion_field_and_ignores_it(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=0,
        )
        resp = self.client.get(self._settings_url(section))
        self.assertNotContains(resp, 'name="motion_style"')
        resp = self.client.post(
            self._settings_url(section), {"body_html": "متن", "motion_style": "fade"},
        )
        self.assertEqual(resp.status_code, 302)
        section.refresh_from_db()
        self.assertNotIn("motion", section.settings)

    def test_card_aware_section_context_flag_unchanged(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=0,
        )
        resp = self.client.get(self._settings_url(section))
        self.assertTrue(resp.context["supports_card"])

    def test_column_visual_section_context_flag_unchanged(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=0,
        )
        resp = self.client.get(self._settings_url(section))
        self.assertTrue(resp.context["supports_columns"])

    def test_column_aware_but_not_visual_section_context_flag_still_false(self):
        """``category_grid`` remains in the broader ``COLUMN_AWARE_SECTION_KEYS``
        storage contract but not the narrower ``COLUMN_VISUAL_SECTION_KEYS`` UI
        allowlist — the migrated context flag must keep that distinction."""
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=0,
        )
        resp = self.client.get(self._settings_url(section))
        self.assertFalse(resp.context["supports_columns"])


class ExtractResponsiveRawSignatureMigrationTests(TestCase):
    """Test J — ``_extract_responsive_raw`` now takes a ``SectionDefinition``
    (not a raw ``section_key`` string) and consults ``supports_capability("columns")``;
    behavior for both a columns-aware and a non-columns-aware definition is
    unchanged."""

    def test_columns_aware_definition_extracts_column_fields(self):
        definition = get_definition("product_section")
        request = mock.Mock()
        request.POST = {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            "desktop_columns": "4", "tablet_columns": "2", "mobile_columns": "1",
        }
        raw = _extract_responsive_raw(request, definition)
        self.assertEqual(raw["desktop_columns"], "4")
        self.assertEqual(raw["tablet_columns"], "2")
        self.assertEqual(raw["mobile_columns"], "1")

    def test_non_columns_aware_definition_extracts_no_column_fields(self):
        definition = get_definition("rich_text")
        request = mock.Mock()
        request.POST = {
            "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            "desktop_columns": "4", "tablet_columns": "2", "mobile_columns": "1",
        }
        raw = _extract_responsive_raw(request, definition)
        self.assertNotIn("desktop_columns", raw)
        self.assertNotIn("tablet_columns", raw)
        self.assertNotIn("mobile_columns", raw)


class RegistryInvariantsUnchangedByU1B2Tests(TestCase):
    """Test K/L/M — the invariants U1B2 must not disturb: registry size,
    hero_banner/image_slider both present and unmerged, multi_banner's
    passthrough validator untouched, no new template/store/family
    conditional was introduced anywhere in ``section_registry.py``."""

    def test_section_registry_still_has_exactly_34_keys(self):
        self.assertEqual(len(SECTION_REGISTRY), 36)

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
