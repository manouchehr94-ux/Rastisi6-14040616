"""P5-W5A — Canonical Editor Safety / Architecture Closure.

Strict TDD RED-before-GREEN suite for the binding single-active-write-
surface policy (see docs/superpowers/plans/
2026-09-19-phase5-w5a-canonical-editor-safety.md): for any Store with
``r4_editor_enabled=True``, no R3-editor-specific unprotected write
endpoint may mutate that Store's Draft (Class A); shared canonical
capabilities must remain reachable regardless (Class B); Restore Version
and Apply Industry Layout (Class C) must converge onto a new canonical
R4-safe, stale-write-protected replacement boundary rather than remain
unconditional legacy exceptions, while the legacy path keeps serving
Stores explicitly pinned to ``r4_editor_enabled=False`` (rollback).
"""
import json

from django.core.cache import cache
from django.urls import NoReverseMatch, reverse

from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.storefront_builder.models import StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


def _enable_r4(store):
    layout = svc.get_or_create_layout(store)
    layout.r4_editor_enabled = True
    layout.save(update_fields=["r4_editor_enabled"])
    return layout


def _disable_r4(store):
    layout = svc.get_or_create_layout(store)
    layout.r4_editor_enabled = False
    layout.save(update_fields=["r4_editor_enabled"])
    return layout


def _seed_template_baseline(store):
    """Header/Footer granular reset (``storefront_header_reset`` /
    ``storefront_footer_reset``) requires the Draft to already carry a
    ``template_baseline_snapshot`` — a fresh Draft with none raises
    ``NoTemplateBaselineError`` regardless of the Class-A guard. This is
    pre-existing, correct behavior unrelated to W5A; tests exercising
    these two routes must seed a real baseline first, exactly like a
    merchant who already applied a Ready Template would have."""
    from apps.storefront_builder.services import preset_service

    draft = svc.get_or_create_draft(store)
    preset_service.apply_preset_by_key(draft, "dark_digital")
    return draft


class R4EnabledCase(StorefrontBuilderViewsTestCase):
    """Base fixture flips the Store to the R4-active default, since
    ``StorefrontBuilderViewsTestCase`` itself pins every Store to
    ``r4_editor_enabled=False`` (most of that file's tests were written
    against the still-required full legacy body)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        _enable_r4(self.store)


# ---------------------------------------------------------------------------
# A. Class A redundant R3 mutation routes fail closed when R4 is active.
# ---------------------------------------------------------------------------
class ClassARedundantRoutesFailClosedTests(R4EnabledCase):
    """Representative coverage across every real Class-A category named in
    the approved master plan: section mutations, container/row mutations,
    appearance/header/footer form writes, reset operations, and the
    legacy Undo/Redo/Publish entry points."""

    def test_section_add_fails_closed(self):
        """A fresh Draft already has a default template's sections seeded
        (not zero) — the assertion is that the guarded POST adds none,
        not that the Draft starts empty."""
        draft = svc.get_or_create_draft(self.store)
        before_count = draft.sections.count()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-add"),
            {"page_type": "home", "section_key": "hero_banner"},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(draft.sections.count(), before_count)

    def test_section_toggle_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-section-toggle", args=[1]))
        self.assertEqual(resp.status_code, 404)

    def test_container_add_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-container-add"), {"page_type": "home"})
        self.assertEqual(resp.status_code, 404)

    def test_appearance_editor_fails_closed_on_get(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(resp.status_code, 404)

    def test_appearance_editor_fails_closed_on_post(self):
        draft = svc.get_or_create_draft(self.store)
        before = draft.appearance_config
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {"palette_slug": "midnight"})
        self.assertEqual(resp.status_code, 404)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config, before)

    def test_header_editor_fails_closed(self):
        draft = svc.get_or_create_draft(self.store)
        before = dict(draft.header_config)
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {"show_search": "on"})
        self.assertEqual(resp.status_code, 404)
        draft.refresh_from_db()
        self.assertEqual(draft.header_config, before)

    def test_footer_editor_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {"show_social": "on"})
        self.assertEqual(resp.status_code, 404)

    def test_header_reset_fails_closed(self):
        _seed_template_baseline(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-header-reset"))
        self.assertEqual(resp.status_code, 404)

    def test_footer_reset_fails_closed(self):
        _seed_template_baseline(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-footer-reset"))
        self.assertEqual(resp.status_code, 404)

    def test_reset_to_baseline_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-reset-to-baseline"))
        self.assertEqual(resp.status_code, 404)

    def test_legacy_undo_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(resp.status_code, 404)

    def test_legacy_redo_fails_closed(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-redo"))
        self.assertEqual(resp.status_code, 404)

    def test_legacy_publish_fails_closed(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertEqual(resp.status_code, 404)
        layout = svc.get_or_create_layout(self.store)
        self.assertFalse(layout.uses_visual_storefront_layout)

    def test_section_collapse_toggle_fails_closed(self):
        """P5-W5A Independent-Review repair: the Architect proved this is
        NOT a cosmetic-only write — ``collapsed_in_editor`` is in
        ``edit_history_service._SECTION_FIELDS`` and the view is decorated
        with ``@_record_edit_history``, so it participates in Draft
        snapshots/history exactly like ``storefront_section_toggle``. The
        prior "justified unguarded exclusion" classification was wrong;
        this is Class A like every other section mutation route."""
        from apps.storefront_builder.models import StorefrontSection

        draft = svc.get_or_create_draft(self.store)
        page = draft.pages.filter(page_type="home").first()
        section_obj = StorefrontSection.objects.filter(page=page).first()
        if section_obj is None:
            self.skipTest("no default home section fixture available")
        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section_obj.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_section_collapse_toggle_blocked_request_mutates_nothing(self):
        """B — the blocked collapse-toggle POST changes neither the
        section's persisted collapse state, the Draft's edit_revision, nor
        its edit-history entry count."""
        from apps.storefront_builder.models import StorefrontEditHistoryEntry, StorefrontSection

        draft = svc.get_or_create_draft(self.store)
        page = draft.pages.filter(page_type="home").first()
        section_obj = StorefrontSection.objects.filter(page=page).first()
        if section_obj is None:
            self.skipTest("no default home section fixture available")
        before_collapsed = section_obj.collapsed_in_editor
        before_revision = draft.edit_revision
        before_history_count = StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section_obj.pk]))
        self.assertEqual(resp.status_code, 404)

        section_obj.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(section_obj.collapsed_in_editor, before_collapsed)
        self.assertEqual(draft.edit_revision, before_revision)
        self.assertEqual(
            StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count(),
            before_history_count,
        )


# ---------------------------------------------------------------------------
# B. Rollback: the exact same Class-A capability keeps working when the
#    Store is explicitly pinned to r4_editor_enabled=False.
# ---------------------------------------------------------------------------
class ClassARollbackStillWorksTests(StorefrontBuilderViewsTestCase):
    """Base fixture already pins r4_editor_enabled=False."""

    def test_header_reset_still_works_when_pinned_back(self):
        _seed_template_baseline(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-header-reset"))
        self.assertNotEqual(resp.status_code, 404)

    def test_legacy_publish_still_works_when_pinned_back(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertNotEqual(resp.status_code, 404)
        layout = svc.get_or_create_layout(self.store)
        self.assertTrue(layout.uses_visual_storefront_layout)

    def test_appearance_editor_still_works_when_pinned_back(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(resp.status_code, 200)

    def test_section_collapse_toggle_still_works_when_pinned_back(self):
        """C — P5-W5A Independent-Review repair: an R3-pinned Store keeps
        the legacy collapse toggle fully functional (the guard only fails
        closed under r4_editor_enabled=True)."""
        from apps.storefront_builder.models import StorefrontSection

        draft = svc.get_or_create_draft(self.store)
        page = draft.pages.filter(page_type="home").first()
        section_obj = StorefrontSection.objects.filter(page=page).first()
        if section_obj is None:
            self.skipTest("no default home section fixture available")
        before_collapsed = section_obj.collapsed_in_editor

        resp = self.client.post(reverse("dashboard:storefront-builder-section-collapse", args=[section_obj.pk]))
        self.assertNotEqual(resp.status_code, 404)

        section_obj.refresh_from_db()
        self.assertNotEqual(section_obj.collapsed_in_editor, before_collapsed)


# ---------------------------------------------------------------------------
# C. Class B shared canonical routes remain reachable under R4 — must NOT
#    be caught by the Class-A guard merely because they live in views.py.
# ---------------------------------------------------------------------------
class ClassBSharedCapabilitiesRemainReachableTests(R4EnabledCase):
    def test_ready_template_gallery_remains_reachable(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-templates"))
        self.assertEqual(resp.status_code, 200)

    def test_ready_template_apply_remains_reachable(self):
        from apps.storefront_builder import layout_preset_registry

        preset = next(iter(layout_preset_registry.list_ready_templates()))
        resp = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": preset.key, "confirm_preset_apply": "1"},
        )
        self.assertNotEqual(resp.status_code, 404)

    def test_draft_preview_remains_reachable(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# D. History browser: read-only, reachable under R4, never mutates.
# ---------------------------------------------------------------------------
class HistoryBrowserReadOnlyUnderR4Tests(R4EnabledCase):
    def test_history_browser_readable_under_r4(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("dashboard:storefront-builder-history"))
        self.assertEqual(resp.status_code, 200)

    def test_history_browser_get_never_mutates_draft(self):
        draft = svc.get_or_create_draft(self.store)
        before_revision = draft.edit_revision
        self.client.get(reverse("dashboard:storefront-builder-history"))
        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, before_revision)


# ---------------------------------------------------------------------------
# E / J. Legacy Restore / Industry-Apply POST cannot mutate an R4-active
#         Store through the unprotected legacy path.
# ---------------------------------------------------------------------------
class LegacyClassCRoutesFailClosedUnderR4Tests(R4EnabledCase):
    def test_legacy_restore_fails_closed(self):
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        layout_before = svc.get_or_create_layout(self.store)
        published_before = layout_before.published_version_id

        resp = self.client.post(reverse("dashboard:storefront-builder-restore", args=[v1.pk]))

        self.assertEqual(resp.status_code, 404)
        layout_after = svc.get_or_create_layout(self.store)
        self.assertEqual(layout_after.published_version_id, published_before)
        self.assertIsNone(layout_after.draft_version_id)

    def test_legacy_industry_apply_fails_closed(self):
        template = IndustryTemplate.objects.create(
            slug="w5a-legacy-guard", name="صنف تست W5A", default_section_keys=["hero_banner"],
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=template.version,
        )
        resp = self.client.post(reverse("dashboard:storefront-builder-apply-industry-layout"))
        self.assertEqual(resp.status_code, 404)
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)


# ---------------------------------------------------------------------------
# O. R3-pinned Store preserves the legacy Restore/Industry flows required
#    by the rollback editor (unchanged, pre-existing behavior).
# ---------------------------------------------------------------------------
class R3PinnedClassCRollbackPreservedTests(StorefrontBuilderViewsTestCase):
    def test_legacy_restore_still_works_when_pinned_back(self):
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        resp = self.client.post(reverse("dashboard:storefront-builder-restore", args=[v1.pk]))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNotNone(layout.draft_version_id)

    def test_legacy_industry_apply_still_works_when_pinned_back(self):
        template = IndustryTemplate.objects.create(
            slug="w5a-legacy-rollback", name="صنف تست بازگشت", default_section_keys=["hero_banner"],
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=template.version,
        )
        resp = self.client.post(reverse("dashboard:storefront-builder-apply-industry-layout"))
        self.assertRedirects(resp, reverse("dashboard:storefront-builder-editor"))
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)


# ---------------------------------------------------------------------------
# F, G, H, I, P, Q. R4-safe Restore.
# ---------------------------------------------------------------------------
class R4SafeRestoreTests(R4EnabledCase):
    def _restore_url(self, pk):
        return reverse("dashboard:storefront-builder-r4-restore", args=[pk])

    def _post_restore(self, pk, base_draft_id, base_revision):
        return self.client.post(
            self._restore_url(pk),
            data=json.dumps({"base_draft_id": base_draft_id, "base_revision": base_revision}),
            content_type="application/json",
        )

    def test_r4_safe_restore_succeeds_with_matching_precondition_no_active_draft(self):
        """H — no-active-Draft contract: nothing open yet, client correctly
        expects null/null, restore proceeds."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)

        resp = self._post_restore(v1.pk, None, None)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        layout.refresh_from_db()
        self.assertIsNotNone(layout.draft_version_id)

    def test_r4_safe_restore_succeeds_with_matching_active_draft_revision(self):
        """F — an active Draft exists and the client's expectation (SAME
        identity, SAME revision) matches."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)

        resp = self._post_restore(v1.pk, draft.pk, draft.edit_revision)

        self.assertEqual(resp.status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertNotEqual(layout.draft_version_id, draft.pk)

    def test_r4_safe_restore_rejects_stale_active_draft_precondition(self):
        """G — same Draft identity, wrong (stale) revision: 409, and the
        newer Draft is untouched."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        stale = draft.edit_revision
        draft.edit_revision += 1
        draft.save(update_fields=["edit_revision"])

        resp = self._post_restore(v1.pk, draft.pk, stale)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "stale_revision")
        self.assertEqual(resp.json()["current_draft_id"], draft.pk)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft.pk)
        self.assertTrue(
            StorefrontLayoutVersion.objects.filter(pk=draft.pk, status=StorefrontLayoutVersion.Status.DRAFT).exists()
        )

    def test_r4_safe_restore_rejects_stale_no_draft_precondition(self):
        """H (conflict branch) — client expected no Draft (null/null), but
        one now exists (created concurrently); must reject, never silently
        overwrite it."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        svc.get_or_create_draft(self.store)

        resp = self._post_restore(v1.pk, None, None)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "stale_revision")

    def test_r4_safe_restore_rejects_wrong_draft_id_with_coincidentally_equal_revision(self):
        """Independent-Review repair — ABA hazard: Draft A is replaced by
        an unrelated Draft B whose ``edit_revision`` also happens to be 0
        (every new Draft row starts at 0). A stale client that still
        believes Draft A (id + revision 0) is active must be rejected even
        though the REVISION alone would coincidentally match Draft B's —
        the precondition binds to IDENTITY first, not revision alone."""
        draft_a = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_a.edit_revision, 0)
        draft_a_id = draft_a.pk
        svc.publish(self.store)
        v1 = StorefrontLayoutVersion.objects.get(pk=draft_a_id)

        # Draft A is replaced by an unrelated Draft B (also starts at
        # revision 0) — e.g. another restore/industry-apply/reset landed
        # first.
        draft_b = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_b.edit_revision, 0)
        self.assertNotEqual(draft_b.pk, draft_a_id)

        # The stale client still believes Draft A (id draft_a_id) is
        # active at revision 0 — REVISION matches Draft B's too, but
        # IDENTITY does not.
        resp = self._post_restore(v1.pk, draft_a_id, 0)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "stale_revision")
        self.assertEqual(resp.json()["current_draft_id"], draft_b.pk)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft_b.pk)
        self.assertTrue(
            StorefrontLayoutVersion.objects.filter(
                pk=draft_b.pk, status=StorefrontLayoutVersion.Status.DRAFT,
            ).exists(),
            "Draft B must not be deleted/replaced by the stale request against Draft A",
        )

    def test_r4_safe_restore_rejects_negative_and_non_integer_precondition_values(self):
        """Reject controlled 400, never a 500/silent coercion, for a
        negative or non-integer id/revision."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)

        for bad_draft_id, bad_revision in [(-1, 0), (1, -1), ("x", 0), (1, "x")]:
            resp = self._post_restore(v1.pk, bad_draft_id, bad_revision)
            self.assertEqual(resp.status_code, 400, (bad_draft_id, bad_revision))
            self.assertEqual(resp.json()["code"], "invalid_precondition")

    def test_r4_safe_restore_rejects_inconsistent_null_pairing(self):
        """Reject controlled 400 when only one of base_draft_id/
        base_revision is null — never treat that as a valid Case A or
        Case B precondition."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)

        resp = self._post_restore(v1.pk, None, 0)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_precondition")

        draft = svc.get_or_create_draft(self.store)
        resp = self._post_restore(v1.pk, draft.pk, None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_precondition")

    def test_r4_safe_restore_cross_store_fails_closed(self):
        """I — a version belonging to a different Store can never be
        restored onto this one."""
        other_store = Store.objects.create(
            name="فروشگاه دیگر W5A", slug="w5a-restore-other", admin_subdomain="w5a-restore-other",
        )
        svc.get_or_create_draft(other_store)
        other_version = svc.publish(other_store)

        resp = self._post_restore(other_version.pk, None, None)

        self.assertIn(resp.status_code, (400, 404))
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)

    def test_r4_safe_restore_delegates_to_existing_canonical_service(self):
        """P — no duplicated business logic: the resulting Draft has the
        exact provenance/labeling ``layout_service.restore_version``
        already produces, not a second hand-rolled implementation."""
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        resp = self._post_restore(v1.pk, None, None)
        self.assertEqual(resp.status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.RESTORED)

    def test_r4_safe_restore_requires_r4_editor_enabled(self):
        _disable_r4(self.store)
        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        resp = self._post_restore(v1.pk, None, None)
        self.assertEqual(resp.status_code, 404)

    def test_r4_safe_restore_rate_limit_exhaustion_returns_controlled_response(self):
        """The EXISTING, unmodified ``storefront_layout.restore`` rate
        limit (enforced inside ``layout_service.restore_version()``, before
        any Draft row is touched) must be translated to a controlled 429,
        never an unhandled 500 — and must not be loosened or duplicated."""
        from apps.storefront_builder.services import layout_service

        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        original = layout_service._RESTORE_RATE_LIMIT
        layout_service._RESTORE_RATE_LIMIT = dict(max_attempts=0, window_seconds=3600)
        try:
            resp = self._post_restore(v1.pk, None, None)
        finally:
            layout_service._RESTORE_RATE_LIMIT = original

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["code"], "rate_limited")
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id, "rate-limit rejection must not create/replace a Draft")


# ---------------------------------------------------------------------------
# K, L, M, N. R4-safe Industry Layout Apply.
# ---------------------------------------------------------------------------
class R4SafeIndustryApplyTests(R4EnabledCase):
    def _install_template(self, slug="w5a-r4-industry"):
        template = IndustryTemplate.objects.create(
            slug=slug, name="صنف تست R4", default_section_keys=["hero_banner"],
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=template.version,
        )
        return template

    def _apply_url(self):
        return reverse("dashboard:storefront-builder-r4-apply-industry-layout")

    def _post_apply(self, base_draft_id, base_revision, force=False):
        return self.client.post(
            self._apply_url(),
            data=json.dumps({"base_draft_id": base_draft_id, "base_revision": base_revision, "force": force}),
            content_type="application/json",
        )

    def test_r4_safe_industry_apply_succeeds_with_no_active_draft(self):
        """M — no-active-Draft contract."""
        self._install_template()
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)

        resp = self._post_apply(None, None)

        self.assertEqual(resp.status_code, 200)
        layout.refresh_from_db()
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)

    def test_r4_safe_industry_apply_succeeds_with_matching_active_draft(self):
        """K"""
        self._install_template()
        draft = svc.get_or_create_draft(self.store)

        resp = self._post_apply(draft.pk, draft.edit_revision)

        self.assertEqual(resp.status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertNotEqual(layout.draft_version_id, draft.pk)

    def test_r4_safe_industry_apply_rejects_stale_precondition(self):
        """L — same Draft identity, wrong (stale) revision: 409, and the
        newer Draft is untouched."""
        self._install_template()
        draft = svc.get_or_create_draft(self.store)
        stale = draft.edit_revision
        draft.edit_revision += 1
        draft.save(update_fields=["edit_revision"])

        resp = self._post_apply(draft.pk, stale)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "stale_revision")
        self.assertEqual(resp.json()["current_draft_id"], draft.pk)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft.pk)

    def test_r4_safe_industry_apply_rejects_stale_no_draft_precondition(self):
        self._install_template()
        svc.get_or_create_draft(self.store)

        resp = self._post_apply(None, None)

        self.assertEqual(resp.status_code, 409)

    def test_r4_safe_industry_apply_rejects_aba_stale_draft_identity_even_with_matching_revision(self):
        """Independent-Review repair — ABA hazard, Industry-Apply variant:
        Draft A (revision 0) is replaced by unrelated Draft B (also
        revision 0). A stale client still expecting Draft A must be
        rejected even though the revision alone coincidentally matches;
        Draft B remains active and is not deleted/replaced."""
        self._install_template()
        draft_a = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_a.edit_revision, 0)
        draft_a_id = draft_a.pk

        # Draft A is replaced by an unrelated Draft B: publish clears the
        # active-Draft pointer, and the next get_or_create_draft creates a
        # brand-new Draft row, which also starts at revision 0.
        svc.publish(self.store)
        draft_b = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_b.edit_revision, 0)
        self.assertNotEqual(draft_b.pk, draft_a_id)

        # The stale client still believes Draft A (id draft_a_id) is
        # active at revision 0 — REVISION matches Draft B's too, but
        # IDENTITY does not.
        resp = self._post_apply(draft_a_id, 0)

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "stale_revision")
        self.assertEqual(resp.json()["current_draft_id"], draft_b.pk)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft_b.pk)
        self.assertTrue(
            StorefrontLayoutVersion.objects.filter(
                pk=draft_b.pk, status=StorefrontLayoutVersion.Status.DRAFT,
            ).exists(),
            "Draft B must not be deleted/replaced by the stale request against Draft A",
        )
        self.assertNotEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)

    def test_r4_safe_industry_apply_rejects_negative_and_non_integer_precondition_values(self):
        self._install_template()
        for bad_draft_id, bad_revision in [(-1, 0), (1, -1), ("x", 0), (1, "x")]:
            resp = self._post_apply(bad_draft_id, bad_revision)
            self.assertEqual(resp.status_code, 400, (bad_draft_id, bad_revision))
            self.assertEqual(resp.json()["code"], "invalid_precondition")

    def test_r4_safe_industry_apply_rejects_inconsistent_null_pairing(self):
        self._install_template()
        resp = self._post_apply(None, 0)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_precondition")

        draft = svc.get_or_create_draft(self.store)
        resp = self._post_apply(draft.pk, None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_precondition")

    def test_r4_safe_industry_apply_requires_confirm_when_already_published(self):
        self._install_template()
        svc.get_or_create_draft(self.store)
        published = svc.publish(self.store)

        resp = self._post_apply(None, None, force=False)

        self.assertEqual(resp.status_code, 400)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertIsNone(layout.draft_version_id)

    def test_r4_safe_industry_apply_force_true_overrides_published_guard(self):
        self._install_template()
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        resp = self._post_apply(None, None, force=True)

        self.assertEqual(resp.status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)

    def test_r4_safe_industry_apply_rejects_truthy_string_force(self):
        """Code-review finding: ``bool("false")`` is True in Python — a
        non-boolean ``force`` value must be rejected outright, never
        silently coerced, or the 'never silently overwrite' confirm gate
        could be defeated by a client sending the literal string
        "false"."""
        self._install_template()
        svc.get_or_create_draft(self.store)
        published = svc.publish(self.store)

        resp = self.client.post(
            self._apply_url(),
            data=json.dumps({"base_draft_id": None, "base_revision": None, "force": "false"}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_force")
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertIsNone(layout.draft_version_id)

    def test_r4_safe_industry_apply_cross_store_fails_closed(self):
        """N — tenant isolation: a Store with no installation of its own
        can never reach another Store's industry template through this
        endpoint (the installation lookup is always scoped to the
        resolved Store)."""
        other_store = Store.objects.create(
            name="فروشگاه دیگر صنف", slug="w5a-industry-other", admin_subdomain="w5a-industry-other",
        )
        template = IndustryTemplate.objects.create(
            slug="w5a-industry-cross", name="صنف متعلق به دیگری", default_section_keys=["hero_banner"],
        )
        StoreIndustryInstallation.objects.create(
            store=other_store, industry_template=template, installed_version=template.version,
        )

        resp = self._post_apply(None, None)

        self.assertEqual(resp.status_code, 404)
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id)

    def test_r4_safe_industry_apply_delegates_to_existing_canonical_service(self):
        """P"""
        self._install_template()
        resp = self._post_apply(None, None)
        self.assertEqual(resp.status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)

    def test_r4_safe_industry_apply_requires_r4_editor_enabled(self):
        _disable_r4(self.store)
        self._install_template()
        resp = self._post_apply(None, None)
        self.assertEqual(resp.status_code, 404)

    def test_r4_safe_industry_apply_rate_limit_exhaustion_returns_controlled_response(self):
        """The EXISTING, unmodified ``storefront_layout.new_draft`` rate
        limit (enforced inside ``layout_service.apply_industry_layout()``,
        before any Draft row is touched) must be translated to a
        controlled 429, never an unhandled 500 — and must not be loosened
        or duplicated."""
        from apps.storefront_builder.services import layout_service

        self._install_template()
        original = layout_service._NEW_DRAFT_RATE_LIMIT
        layout_service._NEW_DRAFT_RATE_LIMIT = dict(max_attempts=0, window_seconds=3600)
        try:
            resp = self._post_apply(None, None)
        finally:
            layout_service._NEW_DRAFT_RATE_LIMIT = original

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["code"], "rate_limited")
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNone(layout.draft_version_id, "rate-limit rejection must not create/replace a Draft")


# ---------------------------------------------------------------------------
# Q. Concurrency: check-and-replace happen inside one lock-protected
#    transaction — proven at the unit level against the service function.
# ---------------------------------------------------------------------------
class ClassCConcurrencyBoundaryTests(R4EnabledCase):
    def test_stale_restore_raises_before_any_draft_row_is_touched(self):
        from apps.storefront_builder.services import r4_mutation_service

        svc.get_or_create_draft(self.store)
        v1 = svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        stale = draft.edit_revision
        draft.edit_revision += 1
        draft.save(update_fields=["edit_revision"])

        with self.assertRaises(r4_mutation_service.R4StaleRevision):
            r4_mutation_service.restore_version_safe(
                store=self.store, actor=self.staff,
                base_draft_id=draft.pk, base_revision=stale, version_id=v1.pk,
            )
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft.pk)

    def test_stale_industry_apply_raises_before_any_draft_row_is_touched(self):
        from apps.storefront_builder.services import r4_mutation_service

        template = IndustryTemplate.objects.create(
            slug="w5a-concurrency-industry", name="صنف تست همزمانی", default_section_keys=["hero_banner"],
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=template.version,
        )
        draft = svc.get_or_create_draft(self.store)
        stale = draft.edit_revision
        draft.edit_revision += 1
        draft.save(update_fields=["edit_revision"])

        with self.assertRaises(r4_mutation_service.R4StaleRevision):
            r4_mutation_service.apply_industry_layout_safe(
                store=self.store, actor=self.staff, base_draft_id=draft.pk, base_revision=stale,
            )
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, draft.pk)
        self.assertNotEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE)


# ---------------------------------------------------------------------------
# R. Ready Template / Style Pack terminology is unambiguous in the R4 UI.
# ---------------------------------------------------------------------------
class StylePackTerminologyTests(R4EnabledCase):
    def test_r4_editor_labels_the_ten_item_registry_as_style_pack(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "بستهٔ سبک")

    def test_ready_template_gallery_still_says_ready_template(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-templates"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "قالب آماده")


# ---------------------------------------------------------------------------
# S. layout / mega_menu reserved disposition remains intact — no new
#    renderer, no new selector, no new registry variant, and Design Lab's
#    randomizable-family set is unaffected.
# ---------------------------------------------------------------------------
class ReservedFamilyDispositionTests(R4EnabledCase):
    def test_layout_family_still_has_no_render_consumer(self):
        from apps.storefront_builder.storefront_appearance import rendering

        self.assertFalse(hasattr(rendering, "layout_settings_for"))

    def test_mega_menu_family_still_has_exactly_one_component(self):
        from apps.storefront_builder.storefront_appearance.inventory import (
            A8_ADVERTISED_COMPONENTS_BY_FAMILY,
        )

        self.assertEqual(A8_ADVERTISED_COMPONENTS_BY_FAMILY["mega_menu"], ("mega_menu.none.v1",))

    def test_design_lab_randomizable_families_excludes_layout_and_mega_menu(self):
        from apps.storefront_builder.services.design_lab_service import (
            DESIGN_LAB_RANDOMIZABLE_FAMILIES,
        )

        self.assertNotIn("layout", DESIGN_LAB_RANDOMIZABLE_FAMILIES)
        self.assertNotIn("mega_menu", DESIGN_LAB_RANDOMIZABLE_FAMILIES)
