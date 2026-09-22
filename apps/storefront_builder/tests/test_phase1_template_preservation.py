"""Phase-1 RED tests — PRESERVATION-FIRST READY TEMPLATE SWITCHING.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

Corrective pass (Architect review of b1107507). These tests now:

  * Blocker 1: use the EXISTING canonical switch entry point
    ``r4_mutation_service.switch_template(...)`` via a single local helper —
    no guessed future ``preset_service`` function names.
  * Blocker 2/9: resolve every post-switch assertion against the ACTIVE /
    returned Draft, and resolve logical merchant sections/containers/cells by
    STABLE IDENTITY (stable_id), never the old DB pk (which can survive inside
    the archived Draft and produce false green).
  * Blocker 5/14: use backend-neutral Python inspection of ``settings``
    (SQLite has no JSONField ``__contains``), never ``settings__contains``.
  * Blocker 6: prove real Container/Cell placement of introduced slots via
    ``section_structure_service.find_placement_cell``.
  * Blocker 7: build a REAL ``max_instances=1`` conflict using a merchant-owned
    ``newsletter`` (B introduces newsletter; A does not).
  * Blocker 8: use the deterministic pair A=``aftab_price`` / B=``almas_luxury``.
  * Blocker 10: exercise the canonical merchant settings keys
    ``product_ids`` / ``category_ids`` / ``collection_ids``.
  * Blocker 13: prove a same-section_key/different-role merchant section is
    preserved AND not retagged to any B slot.

The current implementation's ``r4_mutation_service.switch_template`` archives
the old Draft and clones a NEW active Draft (content-preserving DNA-only). So
the SAME-DRAFT contract test is expected RED today, while composition/merge
assertions expose the real Phase-1 gaps.
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.content.models import HeroSlide
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontContainer,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import r4_mutation_service
from apps.storefront_builder.services import section_structure_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()

# Deterministic canonical pair (Blocker 8).
TEMPLATE_A_KEY = "aftab_price"       # home: hero, chip_categories, product_grid, sale_products
TEMPLATE_B_KEY = "almas_luxury"      # home: hero, circular_categories, product_grid,
#                                              community_gallery, newsletter (newsletter B-only)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _settings_holder(sections, key, value):
    """Backend-neutral (SQLite-safe) resolver — return sections whose
    ``settings[key] == value`` via Python inspection (Blocker 5/14)."""
    return [s for s in sections if (s.settings or {}).get(key) == value]


class Phase1PreservationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.staff = User.objects.create_user(
            username="p1_owner", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store,
            user=self.staff,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        self.template_a = lpr.get_layout_preset(TEMPLATE_A_KEY)
        self.template_b = lpr.get_layout_preset(TEMPLATE_B_KEY)
        # Blocker 8: verify both exist and are Ready Templates.
        self.assertIsNotNone(self.template_a, f"{TEMPLATE_A_KEY} must exist")
        self.assertIsNotNone(self.template_b, f"{TEMPLATE_B_KEY} must exist")
        self.assertTrue(self.template_a.is_ready_template, f"{TEMPLATE_A_KEY} must be Ready")
        self.assertTrue(self.template_b.is_ready_template, f"{TEMPLATE_B_KEY} must be Ready")
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, self.template_a)
        self.draft.refresh_from_db()
        self.original_draft_pk = self.draft.pk

    # -- canonical switch helper (Blocker 1) --
    def _switch_to_b(self):
        """Invoke the EXISTING canonical switch and return the ACTIVE Draft."""
        r4_mutation_service.switch_template(
            store=self.store,
            actor=self.staff,
            base_revision=self.draft.edit_revision,
            template_key=self.template_b.key,
            template_version=self.template_b.version,
        )
        return self._active_draft()

    def _active_draft(self):
        """Blocker 2/general rule: always resolve the active Draft fresh."""
        self.layout.refresh_from_db()
        return self.layout.draft_version

    def _home(self, draft):
        return draft.get_page("home")

    def _resolve_by_stable_id(self, draft, stable_id):
        """Resolve a logical section on the ACTIVE Draft by stable identity."""
        return StorefrontSection.objects.filter(
            page__version=draft, stable_id=stable_id
        ).first()


# --------------------------------------------------------------------------
# PRISTINE PAGE (16, 17)
# --------------------------------------------------------------------------
class PristinePageReplacementTests(Phase1PreservationBase):
    def test_fully_pristine_page_may_be_replaced_with_target_composition(self):
        switched = self._switch_to_b()
        home_keys = list(
            self._home(switched).sections.order_by("order").values_list("section_key", flat=True)
        )
        expected = [e.section_key for e in self.template_b.pages.get("home", ())]
        self.assertEqual(
            home_keys,
            expected,
            "RED: a fully pristine page must receive Template B's canonical "
            "composition after a preservation-first switch (active Draft).",
        )

    def test_switch_keeps_the_same_active_draft_pk(self):
        # Binding SAME-DRAFT contract — expected RED against the current
        # clone/checkpoint switch implementation.
        self._switch_to_b()
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id,
            self.original_draft_pk,
            "RED: a normal switch must stay on the SAME active Draft "
            "(current clone/checkpoint switch violates this).",
        )


# --------------------------------------------------------------------------
# DIRTY-PAGE PRESERVATION (19-31) — all assertions on ACTIVE Draft by stable_id
# --------------------------------------------------------------------------
class MerchantContentPreservationTests(Phase1PreservationBase):
    def test_merchant_created_section_survives_switch(self):
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=99,
            settings={"content": "merchant note"},
        )
        self.assertEqual(merchant.template_slot_key, "")
        sid = merchant.stable_id
        switched = self._switch_to_b()
        self.assertIsNotNone(
            self._resolve_by_stable_id(switched, sid),
            "RED: a merchant-created section (empty template_slot_key) must "
            "survive on the ACTIVE Draft after a switch.",
        )

    def test_merchant_edited_settings_survive(self):
        section = self._home(self.draft).sections.order_by("order").first()
        self.assertIsNotNone(section, "template A must produce at least one home section")
        section.settings = {**(section.settings or {}), "__merchant_edit__": "keep me"}
        section.save(update_fields=["settings"])
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: merchant-edited section must be preserved.")
        self.assertEqual(
            (preserved.settings or {}).get("__merchant_edit__"), "keep me",
            "RED: merchant-edited settings must be preserved on the active Draft.",
        )

    def test_merchant_text_link_content_survives(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=50,
            settings={"content": "<a href='https://merchant.example'>promo</a>"},
        )
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: merchant text/link section must survive.")
        self.assertIn("merchant.example", (preserved.settings or {}).get("content", ""))

    def test_product_category_collection_selections_survive(self):
        # Blocker 10: canonical settings keys product_ids/category_ids/collection_ids.
        prod = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=51,
            settings={"data_source": "manual", "product_ids": [11, 22, 33]},
        )
        cat = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=52,
            settings={"category_ids": [4, 5]},
        )
        coll = StorefrontSection.objects.create(
            version=self.draft, section_key="collection_tiles", order=53,
            settings={"collection_ids": [7]},
        )
        ids = {"product": prod.stable_id, "category": cat.stable_id, "collection": coll.stable_id}
        switched = self._switch_to_b()
        rp = self._resolve_by_stable_id(switched, ids["product"])
        rc = self._resolve_by_stable_id(switched, ids["category"])
        rl = self._resolve_by_stable_id(switched, ids["collection"])
        self.assertIsNotNone(rp, "RED: merchant product_section must survive.")
        self.assertIsNotNone(rc, "RED: merchant category_grid must survive.")
        self.assertIsNotNone(rl, "RED: merchant collection_tiles must survive.")
        self.assertEqual((rp.settings or {}).get("product_ids"), [11, 22, 33])
        self.assertEqual((rc.settings or {}).get("category_ids"), [4, 5])
        self.assertEqual((rl.settings or {}).get("collection_ids"), [7])

    def test_section_scoped_media_survives(self):
        # Blocker 9: verify merchant media on the ACTIVE section (by stable_id),
        # not merely that some HeroSlide pk exists in history.
        hero = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0,
        )
        HeroSlide.objects.create(
            store=self.store, section=hero, title="Merchant hero",
            desktop_image=_img(), is_active=True,
        )
        sid = hero.stable_id
        switched = self._switch_to_b()
        active_hero = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(active_hero, "RED: merchant hero section must survive.")
        active_slides = HeroSlide.objects.filter(section=active_hero)
        self.assertTrue(
            active_slides.exists(),
            "RED: section-scoped merchant media must be attached to the ACTIVE "
            "section after switch (not only present on an archived Draft).",
        )
        self.assertTrue(
            active_slides.filter(title="Merchant hero").exists(),
            "RED: the merchant slide's content must be preserved on the active section.",
        )

    def test_merchant_reorder_survives(self):
        home = self._home(self.draft)
        sections = list(home.sections.order_by("order"))
        if len(sections) < 2:
            self.skipTest("template A home has fewer than 2 sections to reorder")
        first, second = sections[0], sections[1]
        first.order, second.order = second.order, first.order
        first.save(update_fields=["order"])
        second.save(update_fields=["order"])
        sid = first.stable_id
        switched = self._switch_to_b()
        self.assertIsNotNone(
            self._resolve_by_stable_id(switched, sid),
            "RED: a merchant reorder makes the page preservation-required; the "
            "reordered section must survive on the active Draft.",
        )

    def test_is_active_change_survives(self):
        section = self._home(self.draft).sections.order_by("order").first()
        section.is_active = False
        section.save(update_fields=["is_active"])
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: is_active-toggled section must survive.")
        self.assertFalse(preserved.is_active, "RED: merchant is_active change must survive.")

    def test_locked_section_survives_without_move_or_delete(self):
        section = self._home(self.draft).sections.order_by("order").first()
        section.is_locked = True
        original_order = section.order
        section.save(update_fields=["is_locked"])
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: a locked section must never be deleted.")
        self.assertEqual(
            preserved.order, original_order,
            "RED: a locked section must never be moved by a switch.",
        )

    def test_changed_row_layout_marks_page_preservation_required(self):
        home = self._home(self.draft)
        sections = list(home.sections.order_by("order"))
        if len(sections) < 2:
            self.skipTest("need >=2 sections to form a merchant row")
        sections[0].row_key = "merchant_row"
        sections[0].row_span = 6
        sections[1].row_key = "merchant_row"
        sections[1].row_span = 6
        sections[0].save(update_fields=["row_key", "row_span"])
        sections[1].save(update_fields=["row_key", "row_span"])
        sids = {sections[0].stable_id, sections[1].stable_id}
        switched = self._switch_to_b()
        survived = {
            s.stable_id
            for s in switched.get_page("home").sections.all()
            if s.stable_id in sids
        }
        self.assertEqual(
            survived, sids,
            "RED: a merchant row_key/row_span change must make the page "
            "preservation-required; those sections must survive on the active Draft.",
        )


class ContainerCellPreservationTests(Phase1PreservationBase):
    def _first_container(self, draft):
        return (
            StorefrontContainer.objects.filter(page__version=draft, page__page_type="home")
            .order_by("order", "id")
            .first()
        )

    def _container_by_stable_id(self, draft, stable_id):
        return StorefrontContainer.objects.filter(
            page__version=draft, stable_id=stable_id
        ).first()

    def test_container_setting_modification_survives(self):
        container = self._first_container(self.draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.settings = {**(container.settings or {}), "gap": "wide"}
        container.save(update_fields=["settings"])
        sid = container.stable_id
        switched = self._switch_to_b()
        active = self._container_by_stable_id(switched, sid)
        self.assertIsNotNone(
            active,
            "RED: merchant Container must survive by stable identity on the "
            "active Draft (no whole-page rebuild).",
        )
        self.assertEqual((active.settings or {}).get("gap"), "wide")

    def test_container_layout_modification_survives(self):
        container = self._first_container(self.draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.layout_key = "half"
        container.save(update_fields=["layout_key"])
        sid = container.stable_id
        switched = self._switch_to_b()
        active = self._container_by_stable_id(switched, sid)
        self.assertIsNotNone(active, "RED: merchant Container layout change must survive.")
        self.assertEqual(active.layout_key, "half")

    def test_locked_container_graph_survives(self):
        container = self._first_container(self.draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        sid = container.stable_id
        original_cell_stable_ids = set(container.cells.values_list("stable_id", flat=True))
        switched = self._switch_to_b()
        active = self._container_by_stable_id(switched, sid)
        self.assertIsNotNone(active, "RED: a locked Container must survive the switch.")
        self.assertEqual(
            set(active.cells.values_list("stable_id", flat=True)),
            original_cell_stable_ids,
            "RED: a locked Container's Cell graph (by stable identity) must remain intact.",
        )

    def test_multiblock_cell_membership_and_order_survives(self):
        container = self._first_container(self.draft)
        if container is None or not container.cells.exists():
            self.skipTest("template A produced no home container/cell")
        cell = container.cells.order_by("order", "id").first()
        block1 = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=60,
            settings={"content": "block-1"}, cell=cell, cell_order=0,
        )
        block2 = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=61,
            settings={"content": "block-2"}, cell=cell, cell_order=1,
        )
        cell_sid = cell.stable_id
        block_sids = [(block1.stable_id, 0), (block2.stable_id, 1)]
        switched = self._switch_to_b()
        for block_sid, expected_order in block_sids:
            active_block = self._resolve_by_stable_id(switched, block_sid)
            self.assertIsNotNone(
                active_block,
                "RED: multi-block Cell members must survive on the active Draft.",
            )
            active_cell = active_block.cell
            self.assertIsNotNone(active_cell, "RED: block must remain in a Cell.")
            self.assertEqual(
                (active_cell.stable_id, active_block.cell_order),
                (cell_sid, expected_order),
                "RED: multi-block Cell membership (by stable_id) and order preserved.",
            )


# --------------------------------------------------------------------------
# SEMANTIC MAPPING (32-37)
# --------------------------------------------------------------------------
def _resolve_section_role(section):
    """Ratified resolution: parse the positional origin key
    (``key:vN:page:index``) and read the semantic role from that EXACT
    registered historical recipe entry. Returns None when unresolved
    (fail-safe/preserve) — never a heuristic guess (Blocker 6/general rule)."""
    slot = getattr(section, "template_slot_key", "") or ""
    if not slot:
        return None
    try:
        template_key, vpart, page_type, index_str = slot.split(":")
        version = vpart[1:] if vpart.startswith("v") else vpart
        index = int(index_str)
    except (ValueError, AttributeError):
        return None
    preset = lpr.get_layout_preset_version(template_key, version)
    if preset is None:
        return None
    entries = preset.pages.get(page_type, ())
    if index >= len(entries):
        return None
    return getattr(entries[index], "semantic_slot_key", None)


class SemanticMappingTests(Phase1PreservationBase):
    def _b_home_roles(self):
        roles = set()
        for e in self.template_b.pages.get("home", ()):
            role = getattr(e, "semantic_slot_key", None)
            if role:
                roles.add(role)
        return roles

    def _find_shared_role_section(self, draft):
        b_roles = self._b_home_roles()
        for s in self._home(draft).sections.all():
            origin_role = _resolve_section_role(s)
            if origin_role and origin_role in b_roles:
                return s, origin_role
        return None, None

    def test_shared_semantic_role_maps_only_by_explicit_key(self):
        section, role = self._find_shared_role_section(self.draft)
        if section is None:
            self.skipTest("A and B share no resolvable home semantic role")
        section.settings = {**(section.settings or {}), "__merchant__": "v"}
        section.save(update_fields=["settings"])
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(
            preserved,
            "RED: a merchant-edited section on a shared semantic role must be "
            "aligned (preserved), not deleted+recreated.",
        )
        self.assertEqual(
            (preserved.settings or {}).get("__merchant__"), "v",
            "RED: mapping a shared role must preserve merchant data (no overwrite).",
        )

    def test_mapped_section_may_receive_target_slot_ownership_metadata(self):
        section, role = self._find_shared_role_section(self.draft)
        if section is None:
            self.skipTest("A and B share no resolvable home semantic role")
        sid = section.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: mapped section must be preserved.")
        self.assertIn(
            self.template_b.key,
            preserved.template_slot_key or "",
            "RED: after a proven semantic match, the section's template_slot_key "
            "should be retagged to B's target positional slot (metadata "
            "convergence, not content overwrite).",
        )

    def test_unmatched_old_section_is_not_retagged_to_b(self):
        manual = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=70, settings={"content": "x"},
        )
        sid = manual.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: unmatched manual section must be preserved.")
        self.assertNotIn(
            self.template_b.key,
            preserved.template_slot_key or "",
            "RED: an unmatched manual/legacy section must NOT be retagged to B.",
        )

    def test_positional_reorder_across_templates_cannot_misattach(self):
        # Blocker 14: backend-neutral, active-Draft scoped.
        home_sections = list(self._home(self.draft).sections.order_by("order"))
        if not home_sections:
            self.skipTest("template A produced no home sections")
        marked = home_sections[-1]
        marked.settings = {**(marked.settings or {}), "__probe__": "unique-token"}
        marked.save(update_fields=["settings"])
        marked_key = marked.section_key
        marked_sid = marked.stable_id
        switched = self._switch_to_b()
        # Resolve by stable_id first; if the logical section survived, its
        # section_key must be unchanged (never moved onto a different type).
        preserved = self._resolve_by_stable_id(switched, marked_sid)
        if preserved is not None:
            self.assertEqual(
                preserved.section_key, marked_key,
                "RED: merchant content must never be positionally re-attached to "
                "a different section type across a template switch.",
            )
        # And any holder of the probe (backend-neutral) must share the same type.
        holders = _settings_holder(
            list(switched.get_page("home").sections.all()), "__probe__", "unique-token"
        )
        for holder in holders:
            self.assertEqual(
                holder.section_key, marked_key,
                "RED: the probe token must stay with its original section type.",
            )

    def test_same_section_key_different_role_not_retagged_or_misattached(self):
        # Blocker 13: a merchant product_section (products.primary-like) must be
        # preserved AND must NOT be retagged to B's products.sale/primary merely
        # because section_key matches.
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=80,
            settings={"data_source": "newest", "__probe__": "primary"},
        )
        self.assertEqual(merchant.template_slot_key, "")
        sid = merchant.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(
            preserved,
            "RED: a same-section_key/different-role merchant section must be "
            "preserved on the active Draft.",
        )
        self.assertEqual(
            (preserved.settings or {}).get("__probe__"), "primary",
            "RED: merchant probe data must survive.",
        )
        # It had no explicit semantic identity -> must NOT be retagged to B.
        self.assertEqual(
            preserved.template_slot_key or "", "",
            "RED: a merchant section with no explicit semantic identity must NOT "
            "be retagged to any B slot by section_key alone.",
        )


# --------------------------------------------------------------------------
# TARGET SLOT INTRODUCTION (38-42)
# --------------------------------------------------------------------------
class TargetSlotIntroductionTests(Phase1PreservationBase):
    def test_missing_target_slot_is_introduced_safely(self):
        # Make the page dirty so we're on the preservation path.
        StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=90, settings={"content": "keep"},
        )
        switched = self._switch_to_b()
        after = list(self._home(switched).sections.values_list("section_key", flat=True))
        b_keys = {e.section_key for e in self.template_b.pages.get("home", ())}
        self.assertTrue(
            b_keys.issubset(set(after)),
            "RED: target B semantic slots absent from the page must be "
            f"introduced. active home keys={after}, expected superset of {sorted(b_keys)}",
        )

    def test_introduced_slot_receives_valid_standalone_placement(self):
        # Blocker 6: prove real Container/Cell placement, not row_span alone.
        StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=91, settings={"content": "keep"},
        )
        before_keys = set(self._home(self.draft).sections.values_list("section_key", flat=True))
        switched = self._switch_to_b()
        b_keys = {e.section_key for e in self.template_b.pages.get("home", ())}
        introduced_keys = b_keys - before_keys
        if not introduced_keys:
            self.skipTest("no newly-introduced B section on this page")
        introduced_sections = [
            s for s in self._home(switched).sections.all()
            if s.section_key in introduced_keys
        ]
        self.assertTrue(introduced_sections, "expected at least one introduced section")
        for section in introduced_sections:
            cell = section_structure_service.find_placement_cell(section)
            self.assertIsNotNone(
                cell,
                f"RED: introduced target slot {section.section_key!r} must receive a "
                "valid canonical Container/Cell placement (no orphan).",
            )
            self.assertEqual(
                cell.container.page.version_id, switched.pk,
                "RED: the introduced section's placement Cell must belong to the "
                "ACTIVE switched Draft/page.",
            )

    def test_existing_merchant_containers_remain_unchanged(self):
        container = (
            StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home")
            .order_by("order").first()
        )
        if container is None:
            self.skipTest("template A produced no home container")
        container.settings = {**(container.settings or {}), "content_width": "narrow"}
        container.save(update_fields=["settings"])
        sid, before_settings = container.stable_id, dict(container.settings)
        switched = self._switch_to_b()
        active = StorefrontContainer.objects.filter(
            page__version=switched, stable_id=sid
        ).first()
        self.assertIsNotNone(active, "RED: merchant Container must survive by stable id.")
        self.assertEqual(
            active.settings, before_settings,
            "RED: introducing a target slot must not mutate existing merchant Containers.",
        )

    def test_max_instances_conflict_fails_safe_without_deleting_merchant_content(self):
        # Blocker 7: REAL max_instances=1 conflict. B (almas_luxury) introduces
        # a newsletter slot; A (aftab_price) has none. Create a MERCHANT-OWNED
        # newsletter (empty template_slot_key) on A's dirty page first.
        merchant_newsletter = StorefrontSection.objects.create(
            version=self.draft, section_key="newsletter", order=92, settings={},
        )
        self.assertEqual(merchant_newsletter.template_slot_key, "")
        sid = merchant_newsletter.stable_id
        switched = self._switch_to_b()
        # 1) merchant newsletter survives in the ACTIVE Draft.
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(
            preserved,
            "RED: the merchant-owned newsletter must survive the switch "
            "(fail-safe/preserve), never deleted to 'make room'.",
        )
        # 2) not heuristically retagged as B just because section_key matches.
        self.assertEqual(
            preserved.template_slot_key or "", "",
            "RED: merchant newsletter must NOT be retagged as B's newsletter slot "
            "by section_key alone.",
        )
        # 3) no second (invalid) newsletter instance created — max_instances=1.
        newsletter_count = switched.get_page("home").sections.filter(
            section_key="newsletter"
        ).count()
        self.assertEqual(
            newsletter_count, 1,
            "RED: switching must not create a second newsletter instance "
            f"(max_instances=1). found {newsletter_count}.",
        )

    def test_lock_conflict_fails_safe_without_deleting_or_moving_merchant_content(self):
        locked = self._home(self.draft).sections.order_by("order").first()
        locked.is_locked = True
        locked.save(update_fields=["is_locked"])
        locked_order = locked.order
        sid = locked.stable_id
        switched = self._switch_to_b()
        preserved = self._resolve_by_stable_id(switched, sid)
        self.assertIsNotNone(preserved, "RED: locked section must survive a lock conflict.")
        self.assertEqual(
            preserved.order, locked_order,
            "RED: a lock conflict during target-slot insertion must fail safe — "
            "never move the locked merchant section.",
        )
