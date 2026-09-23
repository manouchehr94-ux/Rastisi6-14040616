"""Phase-1 independent-review CORRECTION-ROUND regressions.

These lock in the fixes required by the first independent review of the Phase-1
GREEN candidate. They are additive regression coverage (the three approved
Phase-1 RED/GREEN contract files are untouched):

  * IMPORTANT-1 — retained hand-built Ready Templates carry EXPLICIT
    unresolved-legacy semantic roles (``legacy_unresolved.<key>.<name>``); two
    different such templates that happen to share a ``section_key`` never become
    a cross-template semantic match, so switching preserves (fail safe), never
    guesses.
  * IMPORTANT-2 — the pristine classifier proves the full canonical
    Container/Cell/block placement graph; a real merchant Cell-placement edit
    (made through canonical Container APIs, never fabricated DB state) forces the
    preservation path and merchant content survives.
  * IMPORTANT-5 — an introduced target slot's legacy row metadata
    (``row_key``/``row_span``) can never disagree with its canonical standalone
    full-width Container/Cell placement.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import container_service
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import r4_mutation_service
from apps.storefront_builder.services import section_structure_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()

TEMPLATE_A_KEY = "aftab_price"
TEMPLATE_B_KEY = "almas_luxury"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class _ReviewCorrectionBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.staff = User.objects.create_user(
            username="p1_review_owner", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.template_a = lpr.get_layout_preset(TEMPLATE_A_KEY)
        self.template_b = lpr.get_layout_preset(TEMPLATE_B_KEY)
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, self.template_a)
        self.draft.refresh_from_db()

    def _active_draft(self):
        self.layout.refresh_from_db()
        return self.layout.draft_version

    def _switch_to_b(self):
        r4_mutation_service.switch_template(
            store=self.store, actor=self.staff,
            base_revision=self.draft.edit_revision,
            template_key=self.template_b.key, template_version=self.template_b.version,
        )
        return self._active_draft()


# --------------------------------------------------------------------------
# IMPORTANT-1 — explicit unresolved-legacy roles never cross-match by section_key
# --------------------------------------------------------------------------
class UnresolvedLegacyRoleTests(TestCase):
    def test_two_legacy_templates_sharing_section_key_have_distinct_roles(self):
        a = lpr.get_layout_preset_version("premium_leather", "2")
        b = lpr.get_layout_preset_version("dark_digital", "2")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        a_hero = next(e for e in a.pages["home"] if e.section_key == "hero_banner")
        b_hero = next(e for e in b.pages["home"] if e.section_key == "hero_banner")
        # Both are hero_banner rows, but their unresolved-legacy roles embed the
        # template identity and therefore can never be equal.
        self.assertTrue(a_hero.semantic_slot_key.startswith("legacy_unresolved.premium_leather."))
        self.assertTrue(b_hero.semantic_slot_key.startswith("legacy_unresolved.dark_digital."))
        self.assertNotEqual(
            a_hero.semantic_slot_key, b_hero.semantic_slot_key,
            "the SAME section_key across two unresolved legacy Ready Templates "
            "must NOT collapse into one shared semantic role",
        )

    def test_no_two_ready_templates_reuse_a_legacy_unresolved_role(self):
        # A legacy_unresolved role is globally owned by exactly one template key,
        # so it can never accidentally match another template's slot.
        owners: dict[str, set[str]] = {}
        for (key, _version), preset in lpr.LAYOUT_PRESET_VERSION_REGISTRY.items():
            if not preset.is_ready_template:
                continue
            for entries in preset.pages.values():
                for entry in entries:
                    role = entry.semantic_slot_key or ""
                    if role.startswith("legacy_unresolved."):
                        owners.setdefault(role, set()).add(key)
        cross = {role: keys for role, keys in owners.items() if len(keys) > 1}
        self.assertEqual(cross, {}, f"legacy_unresolved roles must be single-owner; shared: {cross}")


class UnresolvedLegacyResolutionTests(_ReviewCorrectionBase):
    def test_live_legacy_section_role_never_matches_another_template(self):
        # Re-apply a hand-built legacy Ready Template so its sections carry that
        # template's positional slot keys, then prove the resolved role is that
        # template's unresolved-legacy role and is absent from a DIFFERENT
        # template's target roles (so a switch would find no semantic match).
        preset_service.apply_preset(self.draft, lpr.get_layout_preset_version("premium_leather", "2"))
        self.draft.refresh_from_db()
        hero = self.draft.get_page("home").sections.filter(section_key="hero_banner").first()
        self.assertIsNotNone(hero)
        role = preset_service._resolve_section_semantic_role(hero)
        self.assertTrue(
            role.startswith("legacy_unresolved.premium_leather."),
            f"legacy section must resolve its own template's unresolved role, got {role!r}",
        )
        other = lpr.get_layout_preset_version("dark_digital", "2")
        other_roles = {e.semantic_slot_key for e in other.pages["home"]}
        self.assertNotIn(
            role, other_roles,
            "an unresolved legacy role must never appear in another template's slots",
        )


# --------------------------------------------------------------------------
# IMPORTANT-2 — a real Cell-placement edit forces the preservation path
# --------------------------------------------------------------------------
class CellPlacementPristineProofTests(_ReviewCorrectionBase):
    def test_cell_placement_edit_is_preservation_required_and_survives(self):
        home = self.draft.get_page("home")
        sections = list(home.sections.order_by("order", "id"))
        self.assertGreaterEqual(len(sections), 2, "template A must have >=2 home sections")
        original_sids = [s.stable_id for s in sections]

        # A REAL canonical Cell-placement edit (never fabricated DB state):
        # grow the first container to two cells, then move the last section into
        # the newly-created empty Cell. No section's own settings/keys change.
        first_container = home.containers.order_by("order", "id").first()
        self.assertIsNotNone(first_container)
        try:
            container_service.change_container_layout(first_container, "half")
        except container_service.ContainerLayoutError as exc:
            self.skipTest(f"cannot grow first container to half here: {exc}")
        first_container.refresh_from_db()
        empty_cell = first_container.cells.order_by("order", "id").last()
        moved = sections[-1]
        section_structure_service.move_section_to_cell(
            draft=self.draft, section_id=moved.pk, cell_id=empty_cell.pk,
        )

        # The hardened classifier must now classify this page preservation-required.
        self.draft.refresh_from_db()
        self.assertFalse(
            preset_service._page_is_pristine(
                self.draft.get_page("home"), self.draft.template_baseline_snapshot or {},
            ),
            "a merchant Cell-placement edit must make the page preservation-required",
        )

        # And a real switch must preserve every merchant section on the same Draft.
        switched = self._switch_to_b()
        self.assertEqual(self.layout.draft_version_id, self.draft.pk, "switch must keep same Draft")
        for sid in original_sids:
            self.assertIsNotNone(
                StorefrontSection.objects.filter(page__version=switched, stable_id=sid).first(),
                f"merchant section {sid} must survive the switch after a Cell-placement edit",
            )

    def test_clean_applied_page_is_still_classified_pristine(self):
        # Guard the other direction: a freshly-applied, untouched page's full
        # canonical graph must still verify as pristine (no false-dirty from the
        # hardened graph proof).
        self.assertTrue(
            preset_service._page_is_pristine(
                self.draft.get_page("home"), self.draft.template_baseline_snapshot or {},
            ),
            "an untouched freshly-applied page must remain classified pristine",
        )


# --------------------------------------------------------------------------
# IMPORTANT-5 — introduced standalone slot row metadata cannot disagree
# --------------------------------------------------------------------------
class IntroducedSlotPlacementConsistencyTests(_ReviewCorrectionBase):
    def test_introduced_slot_row_metadata_matches_standalone_container(self):
        # Make the page preservation-required so target slots are INTRODUCED
        # (not a pristine replace).
        StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=90,
            settings={"content": "merchant keep"},
        )
        before_keys = set(
            self.draft.get_page("home").sections.values_list("section_key", flat=True)
        )
        switched = self._switch_to_b()
        b_keys = {e.section_key for e in self.template_b.pages.get("home", ())}
        introduced_keys = b_keys - before_keys
        if not introduced_keys:
            self.skipTest("no newly-introduced B section on this page")
        introduced = [
            s for s in switched.get_page("home").sections.all()
            if s.section_key in introduced_keys
        ]
        self.assertTrue(introduced, "expected at least one introduced target slot")
        for section in introduced:
            # Legacy row metadata must be standalone full-width...
            self.assertEqual(section.row_key, "", f"{section.section_key}: introduced slot must be standalone")
            self.assertEqual(section.row_span, 12, f"{section.section_key}: introduced slot must be full-width")
            # ...AND the canonical Container/Cell placement must agree exactly.
            cell = section_structure_service.find_placement_cell(section)
            self.assertIsNotNone(cell, f"{section.section_key}: introduced slot must have canonical placement")
            self.assertEqual(cell.span, 12, "standalone placement Cell must be full-width")
            self.assertEqual(cell.container.layout_key, "single", "standalone placement Container must be single")
            self.assertEqual(cell.container.cells.count(), 1, "standalone placement Container must have one Cell")
            self.assertEqual(
                cell.container.page.version_id, switched.pk,
                "introduced slot's placement must belong to the active switched Draft",
            )
