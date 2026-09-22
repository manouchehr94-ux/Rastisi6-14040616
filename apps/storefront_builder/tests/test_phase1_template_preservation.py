"""Phase-1 RED tests — PRESERVATION-FIRST READY TEMPLATE SWITCHING.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

These RED tests encode the binding preservation contract that production
code does NOT yet implement. A NORMAL Ready Template change must be
preservation-first on the SAME Draft:

  * Pristine page  -> target B canonical composition MAY replace it.
  * Merchant-modified / uncertain page -> PRESERVE (no delete, no whole-page
    rebuild, no removing a section merely because B lacks that role).
  * Shared semantic role aligns ONLY via explicit semantic identity, never
    by index / section_key / settings similarity.
  * Missing target slot introduced with valid standalone placement, existing
    merchant Containers/Cells untouched.
  * Locked section/container preserved, never moved/deleted/rebuilt.
  * End state: provenance = B AND honest B baseline snapshot; unmatched
    preserved A/manual content is NOT written as B-owned baseline.

The preservation-first entry point does not exist yet. We resolve it
dynamically via ``_preservation_switch`` so this module still imports and
collects; when the operation is absent the dependent test fails at test
level with a descriptive message (never ImportError at collection).

Fixtures follow the repository's real conventions exactly:
``Store.objects.get(slug="akhlaghi")`` (seeded by migration
``apps/stores/migrations/0002_create_akhlaghi_store.py``),
``layout_service.get_or_create_draft``, ``preset_service.apply_preset``,
``StorefrontSection(version=draft, ...)`` shim, and the ``_img`` helper
pattern used across the suite.
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
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _two_ready_templates():
    """Return (template_a, template_b) — two distinct Ready Templates whose
    home compositions differ, or skip if fewer than two exist."""
    ready = lpr.list_ready_templates()
    if len(ready) < 2:
        return None, None
    # Prefer a pair with different home length to exercise slot add/remove.
    ready_sorted = sorted(ready, key=lambda p: p.key)
    a = ready_sorted[0]
    b = next((p for p in ready_sorted if p.key != a.key), None)
    return a, b


_MISSING = object()


def _preservation_switch(store, preset, *, user=None, base_revision=_MISSING):
    """Invoke the canonical preservation-first switch, whatever its final name.

    Tries, in order, the names the Phase-1 design may land on. Returns a
    sentinel string tag when none exists yet so the calling test fails at
    test level with a clear "not implemented" message instead of raising.
    """
    candidates = (
        "switch_ready_template_preserving",
        "switch_template_preserving_merge",
        "apply_ready_template_preserving",
        "preservation_first_switch",
    )
    for name in candidates:
        fn = getattr(preset_service, name, None)
        if callable(fn):
            return fn(store, preset, user=user)
    return _MISSING


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
        self.template_a, self.template_b = _two_ready_templates()
        if self.template_a is None:
            self.skipTest("fewer than two Ready Templates registered")

    def _apply_a(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(draft, self.template_a)
        draft.refresh_from_db()
        return draft

    def _home(self, draft):
        return draft.get_page("home")

    def _require_impl(self, result):
        if result is _MISSING:
            self.fail(
                "RED: preservation-first Ready Template switch not implemented "
                "(no preset_service.switch_ready_template_preserving / "
                "switch_template_preserving_merge / apply_ready_template_preserving)."
            )
        return result


# --------------------------------------------------------------------------
# PRISTINE PAGE (16, 17, 18)
# --------------------------------------------------------------------------
class PristinePageReplacementTests(Phase1PreservationBase):
    def test_fully_pristine_page_may_be_replaced_with_target_composition(self):
        draft = self._apply_a()  # freshly applied => pristine
        self._preservation_switch_or_require(draft)
        draft.refresh_from_db()
        home_keys = list(
            self._home(draft).sections.order_by("order").values_list("section_key", flat=True)
        )
        expected = [e.section_key for e in self.template_b.pages.get("home", ())]
        self.assertEqual(
            home_keys,
            expected,
            "RED: a fully pristine page must receive Template B's canonical "
            "composition after a preservation-first switch.",
        )

    def test_pristine_replacement_keeps_the_same_draft_pk(self):
        draft = self._apply_a()
        original_pk = draft.pk
        self._preservation_switch_or_require(draft)
        layout = svc.get_or_create_layout(self.store)
        layout.refresh_from_db()
        self.assertEqual(
            layout.draft_version_id,
            original_pk,
            "RED: a normal switch must stay on the SAME Draft (no new active "
            "Draft, no checkpoint_draft_before_replacement as the mechanism).",
        )

    def _preservation_switch_or_require(self, draft):
        result = _preservation_switch(self.store, self.template_b, user=self.staff)
        return self._require_impl(result)


# --------------------------------------------------------------------------
# DIRTY-PAGE PRESERVATION (19-31)
# --------------------------------------------------------------------------
class MerchantContentPreservationTests(Phase1PreservationBase):
    def test_merchant_created_section_survives_switch(self):
        draft = self._apply_a()
        merchant = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=99,
            settings={"content": "merchant note"},
        )
        # merchant-created => empty template_slot_key => always merchant-owned
        self.assertEqual(merchant.template_slot_key, "")
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontSection.objects.filter(pk=merchant.pk).exists(),
            "RED: a merchant-created section (empty template_slot_key) must "
            "never be deleted by a template switch.",
        )

    def test_merchant_edited_settings_survive(self):
        draft = self._apply_a()
        section = self._home(draft).sections.order_by("order").first()
        self.assertIsNotNone(section, "template A must produce at least one home section")
        section.settings = {**(section.settings or {}), "__merchant_edit__": "keep me"}
        section.save(update_fields=["settings"])
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        if StorefrontSection.objects.filter(pk=section.pk).exists():
            section.refresh_from_db()
            self.assertEqual(
                section.settings.get("__merchant_edit__"),
                "keep me",
                "RED: merchant-edited settings must be preserved.",
            )
        else:
            self.fail("RED: a merchant-edited section must be preserved, not deleted.")

    def test_merchant_text_link_content_survives(self):
        draft = self._apply_a()
        section = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=50,
            settings={"content": "<a href='https://merchant.example'>promo</a>"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        section.refresh_from_db()
        self.assertIn("merchant.example", section.settings.get("content", ""))

    def test_product_category_collection_selections_survive(self):
        draft = self._apply_a()
        section = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=51,
            settings={"data_source": "manual", "selected_products": [1, 2, 3]},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        section.refresh_from_db()
        self.assertEqual(section.settings.get("selected_products"), [1, 2, 3])

    def test_section_scoped_media_survives(self):
        draft = self._apply_a()
        hero = StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=0,
        )
        slide = HeroSlide.objects.create(
            store=self.store, section=hero, title="Merchant hero",
            desktop_image=_img(), is_active=True,
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            HeroSlide.objects.filter(pk=slide.pk).exists(),
            "RED: section-scoped merchant media must survive a switch.",
        )

    def test_merchant_reorder_survives(self):
        draft = self._apply_a()
        home = self._home(draft)
        sections = list(home.sections.order_by("order"))
        if len(sections) < 2:
            self.skipTest("template A home has fewer than 2 sections to reorder")
        first, second = sections[0], sections[1]
        first.order, second.order = second.order, first.order
        first.save(update_fields=["order"])
        second.save(update_fields=["order"])
        touched_pk = first.pk
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontSection.objects.filter(pk=touched_pk).exists(),
            "RED: a merchant reorder makes the page preservation-required; the "
            "reordered sections must not be wiped by the switch.",
        )

    def test_is_active_change_survives(self):
        draft = self._apply_a()
        section = self._home(draft).sections.order_by("order").first()
        section.is_active = False
        section.save(update_fields=["is_active"])
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        section.refresh_from_db()
        self.assertFalse(section.is_active, "RED: merchant is_active change must survive.")

    def test_locked_section_survives_without_move_or_delete(self):
        draft = self._apply_a()
        section = self._home(draft).sections.order_by("order").first()
        section.is_locked = True
        original_order = section.order
        section.save(update_fields=["is_locked"])
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontSection.objects.filter(pk=section.pk).exists(),
            "RED: a locked section must never be deleted by a switch.",
        )
        section.refresh_from_db()
        self.assertEqual(
            section.order, original_order,
            "RED: a locked section must never be moved by a switch.",
        )

    def test_changed_row_layout_marks_page_preservation_required(self):
        draft = self._apply_a()
        home = self._home(draft)
        sections = list(home.sections.order_by("order"))
        if len(sections) < 2:
            self.skipTest("need >=2 sections to form a merchant row")
        # Merchant joins two sections into a composite row.
        sections[0].row_key = "merchant_row"
        sections[0].row_span = 6
        sections[1].row_key = "merchant_row"
        sections[1].row_span = 6
        sections[0].save(update_fields=["row_key", "row_span"])
        sections[1].save(update_fields=["row_key", "row_span"])
        pks = {sections[0].pk, sections[1].pk}
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        survived = set(
            StorefrontSection.objects.filter(pk__in=pks).values_list("pk", flat=True)
        )
        self.assertEqual(
            survived, pks,
            "RED: a merchant row_key/row_span change must make the page "
            "preservation-required; those sections must not be wiped.",
        )


class ContainerCellPreservationTests(Phase1PreservationBase):
    def _first_container(self, draft):
        return (
            StorefrontContainer.objects.filter(page__version=draft, page__page_type="home")
            .order_by("order", "id")
            .first()
        )

    def test_container_setting_modification_survives(self):
        draft = self._apply_a()
        container = self._first_container(draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.settings = {**(container.settings or {}), "gap": "wide"}
        container.save(update_fields=["settings"])
        cid = container.pk
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontContainer.objects.filter(pk=cid).exists(),
            "RED: merchant Container setting change must survive; no whole-page "
            "container rebuild allowed on a merchant-modified page.",
        )
        container.refresh_from_db()
        self.assertEqual(container.settings.get("gap"), "wide")

    def test_container_layout_modification_survives(self):
        draft = self._apply_a()
        container = self._first_container(draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.layout_key = "half"
        container.save(update_fields=["layout_key"])
        cid = container.pk
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontContainer.objects.filter(pk=cid).exists())
        container.refresh_from_db()
        self.assertEqual(
            container.layout_key, "half",
            "RED: merchant Container layout change must survive a switch.",
        )

    def test_locked_container_graph_survives(self):
        draft = self._apply_a()
        container = self._first_container(draft)
        if container is None:
            self.skipTest("template A produced no home container")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        cid = container.pk
        original_cell_ids = set(container.cells.values_list("pk", flat=True))
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontContainer.objects.filter(pk=cid).exists(),
            "RED: a locked Container must never be rebuilt/removed.",
        )
        container.refresh_from_db()
        self.assertEqual(
            set(container.cells.values_list("pk", flat=True)),
            original_cell_ids,
            "RED: a locked Container's Cell graph must remain intact.",
        )

    def test_multiblock_cell_membership_and_order_survives(self):
        draft = self._apply_a()
        container = self._first_container(draft)
        if container is None or not container.cells.exists():
            self.skipTest("template A produced no home container/cell")
        cell = container.cells.order_by("order", "id").first()
        # Attach two ordered blocks to one cell (Phase-2B multi-block).
        block1 = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=60,
            settings={"content": "block-1"}, cell=cell, cell_order=0,
        )
        block2 = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=61,
            settings={"content": "block-2"}, cell=cell, cell_order=1,
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        for block, expected_order in ((block1, 0), (block2, 1)):
            self.assertTrue(
                StorefrontSection.objects.filter(pk=block.pk).exists(),
                "RED: multi-block Cell members must survive the switch.",
            )
            block.refresh_from_db()
            self.assertEqual(
                (block.cell_id, block.cell_order),
                (cell.pk, expected_order),
                "RED: multi-block Cell membership and order must be preserved.",
            )


# --------------------------------------------------------------------------
# SEMANTIC MAPPING (32-37)
# --------------------------------------------------------------------------
class SemanticMappingTests(Phase1PreservationBase):
    def _find_shared_role_section(self, draft):
        """Return a home section whose semantic role also exists in B, or None."""
        b_roles = set()
        for e in self.template_b.pages.get("home", ()):
            role = getattr(e, "semantic_slot_key", None)
            if role:
                b_roles.add(role)
        for s in self._home(draft).sections.all():
            # A section's semantic role is resolved from its origin slot; for a
            # freshly A-applied section it derives from A's recipe.
            origin_role = _resolve_section_role(s)
            if origin_role and origin_role in b_roles:
                return s, origin_role
        return None, None

    def test_shared_semantic_role_maps_only_by_explicit_key(self):
        draft = self._apply_a()
        section, role = self._find_shared_role_section(draft)
        if section is None:
            self.skipTest("A and B share no home semantic role to exercise mapping")
        section.settings = {**(section.settings or {}), "__merchant__": "v"}
        section.save(update_fields=["settings"])
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontSection.objects.filter(pk=section.pk).exists(),
            "RED: a merchant-edited section on a shared semantic role must be "
            "aligned (preserved), not deleted+recreated.",
        )
        section.refresh_from_db()
        self.assertEqual(
            section.settings.get("__merchant__"), "v",
            "RED: mapping a shared role must preserve merchant data (no overwrite).",
        )

    def test_mapped_section_may_receive_target_slot_ownership_metadata(self):
        draft = self._apply_a()
        section, role = self._find_shared_role_section(draft)
        if section is None:
            self.skipTest("A and B share no home semantic role to exercise retag")
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        if not StorefrontSection.objects.filter(pk=section.pk).exists():
            self.fail("RED: mapped section must be preserved, not deleted.")
        section.refresh_from_db()
        self.assertIn(
            self.template_b.key,
            section.template_slot_key,
            "RED: after a proven semantic match, the section's template_slot_key "
            "should be retagged to B's target positional slot (metadata "
            "convergence, not content overwrite).",
        )

    def test_unmatched_old_section_is_not_retagged_to_b(self):
        draft = self._apply_a()
        # A merchant/manual section with empty slot must never become B-owned.
        manual = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=70, settings={"content": "x"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        if StorefrontSection.objects.filter(pk=manual.pk).exists():
            manual.refresh_from_db()
            self.assertNotIn(
                self.template_b.key,
                manual.template_slot_key or "",
                "RED: an unmatched manual/legacy section must NOT be retagged to B.",
            )
        else:
            self.fail("RED: unmatched manual section must be preserved.")

    def test_positional_reorder_across_templates_cannot_misattach(self):
        # Edit a specific A section's content, then switch. Its merchant data
        # must not land on a different B slot by index coincidence.
        draft = self._apply_a()
        home_sections = list(self._home(draft).sections.order_by("order"))
        if not home_sections:
            self.skipTest("template A produced no home sections")
        marked = home_sections[-1]  # last index most prone to positional drift
        marked.settings = {**(marked.settings or {}), "__probe__": "unique-token"}
        marked.save(update_fields=["settings"])
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        # The probe token must still be attached to a section carrying the SAME
        # section_key it was on (never moved onto an unrelated section type).
        holders = StorefrontSection.objects.filter(
            page__version=draft, settings__contains={"__probe__": "unique-token"}
        )
        for holder in holders:
            self.assertEqual(
                holder.section_key, marked.section_key,
                "RED: merchant content must never be positionally re-attached to "
                "a different section type across a template switch.",
            )

    def test_same_section_key_different_role_cannot_misattach(self):
        draft = self._apply_a()
        # product_section may exist as products.primary and products.sale.
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=80,
            settings={"data_source": "newest", "__probe__": "primary"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        holders = StorefrontSection.objects.filter(
            page__version=draft, settings__contains={"__probe__": "primary"}
        )
        # It must remain merchant-owned/preserved, not silently mapped onto B's
        # products.sale slot just because section_key matches.
        self.assertTrue(
            holders.exists(),
            "RED: a same-section_key/different-role section must be preserved, "
            "never cross-mapped by section_key alone.",
        )


def _resolve_section_role(section):
    """Best-effort role resolver used only by the mapping tests.

    Mirrors the ratified resolution: parse the positional template_slot_key
    (``key:vN:page:index``) and read the semantic role from that EXACT
    registered historical recipe entry. Returns None when unresolved (the
    fail-safe/preserve case) — never a heuristic guess.
    """
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


# --------------------------------------------------------------------------
# TARGET SLOT INTRODUCTION (38-42)
# --------------------------------------------------------------------------
class TargetSlotIntroductionTests(Phase1PreservationBase):
    def test_missing_target_slot_is_introduced_safely(self):
        draft = self._apply_a()
        # Make the page dirty so we're on the preservation path.
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=90, settings={"content": "keep"},
        )
        before = set(
            self._home(draft).sections.values_list("section_key", flat=True)
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        after = list(
            self._home(draft).sections.values_list("section_key", flat=True)
        )
        b_keys = {e.section_key for e in self.template_b.pages.get("home", ())}
        introduced = (set(after) - before) & b_keys
        self.assertTrue(
            introduced or b_keys.issubset(set(after)),
            "RED: target B semantic slots absent from the page must be introduced.",
        )

    def test_introduced_slot_receives_valid_standalone_placement(self):
        draft = self._apply_a()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=91, settings={"content": "keep"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        # No introduced section may be left orphaned (row_span default full,
        # and it must be reachable as a normal page section).
        orphans = [
            s for s in self._home(draft).sections.all()
            if s.row_key == "" and s.row_span not in range(1, 13)
        ]
        self.assertEqual(
            orphans, [],
            "RED: an introduced target slot must receive valid standalone "
            "placement (full-width standalone or a valid container/cell).",
        )

    def test_existing_merchant_containers_remain_unchanged(self):
        draft = self._apply_a()
        container = (
            StorefrontContainer.objects.filter(page__version=draft, page__page_type="home")
            .order_by("order").first()
        )
        if container is None:
            self.skipTest("template A produced no home container")
        container.settings = {**(container.settings or {}), "content_width": "narrow"}
        container.save(update_fields=["settings"])
        cid, before_settings = container.pk, dict(container.settings)
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontContainer.objects.filter(pk=cid).exists())
        container.refresh_from_db()
        self.assertEqual(
            container.settings, before_settings,
            "RED: introducing a target slot must not mutate existing merchant "
            "Containers.",
        )

    def test_max_instances_conflict_fails_safe_without_deleting_merchant_content(self):
        draft = self._apply_a()
        merchant = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=92, settings={"content": "keep"},
        )
        # Even if introducing a B slot would exceed a section's max_instances,
        # the switch must never delete merchant content to make room.
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(
            StorefrontSection.objects.filter(pk=merchant.pk).exists(),
            "RED: a max_instances conflict must fail safe (preserve), never "
            "delete merchant content to make room for a target slot.",
        )

    def test_lock_conflict_fails_safe_without_deleting_or_moving_merchant_content(self):
        draft = self._apply_a()
        locked = self._home(draft).sections.order_by("order").first()
        locked.is_locked = True
        locked.save(update_fields=["is_locked"])
        locked_order = locked.order
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())
        locked.refresh_from_db()
        self.assertEqual(
            locked.order, locked_order,
            "RED: a lock conflict during target-slot insertion must fail safe — "
            "never delete or move the locked merchant section.",
        )
