"""U1A — Engine Metadata Contract Foundation, item J/§15.

R1 marked one thing UNVERIFIED: whether applying a ``LayoutPresetDefinition``
(``services/preset_service.apply_preset``) currently produces exactly one
logical Undo/Redo history event, or several/none.

This file originally characterized the answer (exactly one event) without
changing behaviour, per the U1A brief's own explicit escape hatch: "if the
answer had turned out to be 'not exactly one event', the correct move would
be to report that and defer any behavioural change to U7 (Reset design)".

Acceptance Batch 2 (post-U11) is that Reset-design batch, and it changes this
on purpose: ``views.storefront_apply_layout_preset`` now calls
``preset_service.apply_preset_with_checkpoint`` (Issue 1) instead of
``apply_preset`` directly. Whenever the current Draft has real existing
content, that function preserves it as a recoverable version-history
checkpoint by ARCHIVING the current Draft row and making a brand-new row the
active Draft — exactly the same Draft-identity boundary ``publish()`` already
treats specially (it deletes ``draft.edit_history_entries.all()`` for exactly
this reason: Undo/Redo entries are scoped to one Draft row's continuous
lifetime via ``StorefrontEditHistoryEntry.draft_version`` and a
``select_for_update().get(pk=draft.pk)`` lock inside
``edit_history_service.record_change`` — they cannot meaningfully follow
content across a row swap). So once a checkpoint fires, there is nothing
correct to attach a local Undo entry to: the old row's timeline ends there
(mirroring publish), and the new row starts with a clean, empty history
(mirroring restore_version/apply_industry_layout, which also always hand
back a brand-new Draft row with zero edit-history entries).

The pre-apply state is not lost — it is now durably recoverable via
``layout_service.restore_version`` on the archived checkpoint, a strictly
more robust mechanism than a local Undo stack entry (survives navigation/
reload, has its own dedicated UI at ``storefront-builder-history``).

Only the "content already existed" scenario changes. When the Draft was
already empty (nothing worth checkpointing), ``apply_preset_with_checkpoint``
mutates the SAME Draft row in place exactly like plain ``apply_preset``
always did — Undo/Redo for that case is completely unaffected, still
verified below.
"""

from apps.storefront_builder.models import StorefrontEditHistoryEntry, StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.tests.test_preset_service import PresetServiceTestCase


class PresetApplyEditHistoryCharacterizationTests(PresetServiceTestCase):
    def test_applying_a_preset_over_existing_content_creates_a_checkpoint_not_an_undo_entry(self):
        draft_before = svc.get_or_create_draft(self.store)
        self.assertTrue(draft_before.sections.exists(), "bootstrap content must exist for this scenario")
        before_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft_before).count()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        resp = self.admin_client.post(
            reverse_apply_preset_url(),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)

        # No Undo entry against the old (now archived) row — the checkpoint
        # is the recovery mechanism for this action, not the edit-history log.
        after_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft_before).count()
        self.assertEqual(after_count, before_count)

        draft_before.refresh_from_db()
        self.assertEqual(draft_before.status, StorefrontLayoutVersion.Status.ARCHIVED)
        layout.refresh_from_db()
        self.assertNotEqual(layout.draft_version_id, draft_before.pk)
        self.assertEqual(layout.versions.count(), versions_before + 1)

    def test_pre_apply_state_is_recoverable_via_history_restore_instead_of_undo(self):
        draft = svc.get_or_create_draft(self.store)
        home_before = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))

        resp = self.admin_client.post(
            reverse_apply_preset_url(),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)

        layout = svc.get_or_create_layout(self.store)
        new_draft = layout.draft_version
        home_after_apply = list(new_draft.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertNotEqual(home_before, home_after_apply)  # the preset really changed the page

        # The new Draft row starts with a completely clean Undo/Redo history.
        self.assertFalse(StorefrontEditHistoryEntry.objects.filter(draft_version=new_draft).exists())

        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")
        restored = svc.restore_version(self.store, checkpoint.pk, user=self.staff)
        home_after_restore = list(restored.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(
            home_after_restore, home_before,
            "the pre-apply state must remain fully recoverable, just via History → Restore instead of Undo",
        )

    def test_applying_a_preset_over_an_already_empty_draft_still_uses_plain_undo(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """No existing content → nothing to checkpoint → the SAME Draft row
        is mutated in place, exactly like before this Batch — Undo/Redo for
        this scenario is completely unaffected."""
        draft = svc.get_or_create_draft(self.store)
        for page_type in ("home", "product_detail", "listing", "collection", "search", "cart"):
            draft.get_page(page_type).sections.all().delete()
        before_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

        resp = self.admin_client.post(
            reverse_apply_preset_url(),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)

        after_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()
        self.assertEqual(after_count - before_count, 1)

        entry = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).latest("sequence")
        self.assertEqual(entry.action_label, "اعمال پیش‌تنظیم صفحه‌آرایی")

        undo_resp = self.admin_client.post(reverse_undo_url())
        self.assertEqual(undo_resp.status_code, 200)
        draft.refresh_from_db()
        self.assertFalse(draft.home_page().sections.exists())

    def test_a_rejected_preset_apply_creates_no_history_entry(self):
        """A no-op/failed submission must not pollute the history log — this
        mirrors record_change's own before==after no-op filtering."""
        draft = svc.get_or_create_draft(self.store)
        before_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

        # Missing confirm_preset_apply=1 while pages already have sections —
        # the view rejects this without calling apply_preset at all.
        resp = self.admin_client.post(reverse_apply_preset_url(), {"preset_key": "dense_catalog"})
        self.assertEqual(resp.status_code, 302)

        after_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()
        self.assertEqual(after_count, before_count)


def reverse_apply_preset_url():
    from django.urls import reverse
    return reverse("dashboard:storefront-builder-apply-preset")


def reverse_undo_url():
    from django.urls import reverse
    return reverse("dashboard:storefront-builder-undo")
