"""Phase 2 (Lifecycle & Safety) — Task 1 RED/GREEN characterization.

These tests encode the DESIRED Phase-2 lifecycle invariants and prove, at
the current baseline, which gaps are still RED (defect present) and which
already-safe behaviours are GREEN. They use ONLY real routes/services and
real fixtures (Store "akhlaghi" via ``StorefrontBuilderViewsTestCase``,
``layout_service`` for the real Draft/Publish lifecycle) — no fabricated
APIs, no production code changes.

Gap mapping (see
``docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md``):

* L05 (P2) — no editing path may mutate a Published/Archived version.
  Expected at baseline: GREEN (already safe by Draft-scoping in
  ``_get_scoped_section``, ``apps/storefront_builder/views.py:772-781``).
* L01 (P1) — a real legacy Draft mutation MUST advance the Draft's
  ``edit_revision`` (Draft-wide monotonic optimistic-concurrency token).
  Expected at baseline: RED — legacy view mutations record edit history but
  never advance ``edit_revision`` (see ``_record_edit_history``,
  ``apps/storefront_builder/views.py:68-104``; the increment lives only in
  the R4 path, ``r4_mutation_service._lock_active_draft``).
"""

from django.urls import reverse

from apps.storefront_builder.models import (
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase


class LegacyPublishedVersionImmutabilityTests(StorefrontBuilderViewsTestCase):
    """L05 — a legacy ``storefront_section_settings`` POST scoped at a
    section that lives on a PUBLISHED version must be rejected (404,
    because ``_get_scoped_section`` only ever matches ``status=DRAFT``)
    and must mutate nothing.

    Baseline expectation: GREEN — already correct by Draft-scoping. This
    is the legacy-path analogue of the existing R4 test
    ``test_r4_mutation_api.PublishedVersionImmutabilityTests
    .test_section_on_published_version_is_not_mutable_via_r4``.
    """

    def _make_published_section(self):
        layout = svc.get_or_create_layout(self.store)
        published = StorefrontLayoutVersion.objects.create(
            layout=layout,
            version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        home = published.get_page(StorefrontPage.PageType.HOME)
        return StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>منتشرشده اصلی</p>"},
        )

    def test_legacy_section_settings_post_on_published_section_is_not_found(self):
        published_section = self._make_published_section()
        original_settings = dict(published_section.settings)

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[published_section.pk]),
            {
                "body_html": "<p>تلاش برای تغییر نسخه‌ی منتشرشده</p>",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )

        # Draft-scoped lookup never matches a Published section → 404.
        self.assertEqual(response.status_code, 404)
        # And nothing was mutated on the Published version.
        published_section.refresh_from_db()
        self.assertEqual(published_section.settings, original_settings)

    def test_legacy_section_settings_get_on_published_section_is_not_found(self):
        published_section = self._make_published_section()
        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[published_section.pk]),
        )
        self.assertEqual(response.status_code, 404)


class LegacyArchivedVersionImmutabilityTests(StorefrontBuilderViewsTestCase):
    """L05 — same guarantee for an ARCHIVED version's section. Also a
    Draft-scoping consequence, so also expected GREEN at baseline."""

    def test_legacy_section_settings_post_on_archived_section_is_not_found(self):
        layout = svc.get_or_create_layout(self.store)
        archived = StorefrontLayoutVersion.objects.create(
            layout=layout,
            version_number=998,
            status=StorefrontLayoutVersion.Status.ARCHIVED,
        )
        StorefrontPage.ensure_version_pages(archived)
        home = archived.get_page(StorefrontPage.PageType.HOME)
        archived_section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>بایگانی اصلی</p>"},
        )
        original_settings = dict(archived_section.settings)

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[archived_section.pk]),
            {
                "body_html": "<p>تلاش برای تغییر نسخه‌ی بایگانی</p>",
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )

        self.assertEqual(response.status_code, 404)
        archived_section.refresh_from_db()
        self.assertEqual(archived_section.settings, original_settings)


class LegacyMutationAdvancesEditRevisionTests(StorefrontBuilderViewsTestCase):
    """L01 — DESIRED invariant: every real state-changing legacy mutation
    advances the active Draft's ``edit_revision`` by exactly 1 so a
    concurrent client's stale ``base_revision`` can be detected.

    Baseline expectation: RED — the legacy ``storefront_section_settings``
    view records edit history but never touches ``edit_revision``; only the
    R4 mutation path advances it. The baseline (unchanged ``edit_revision``)
    is recorded explicitly in ``test_baseline_legacy_mutation_does_not_advance_edit_revision``.
    """

    def _draft_with_rich_text_section(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        home = draft.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>متن اولیه</p>"},
        )
        return draft, section

    def _post_change(self, section, body_html):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[section.pk]),
            {
                "body_html": body_html,
                "show_on_desktop": "on",
                "show_on_tablet": "on",
                "show_on_mobile": "on",
            },
        )

    def test_legacy_real_mutation_advances_edit_revision_by_one(self):
        """DESIRED (currently RED): a real legacy setting change advances
        ``edit_revision`` by exactly 1."""
        draft, section = self._draft_with_rich_text_section()
        starting_revision = draft.edit_revision

        response = self._post_change(section, "<p>متن تغییریافته توسط مسیر قدیمی</p>")
        self.assertEqual(response.status_code, 302)

        # Confirm the mutation really happened (so this is a real edit,
        # not a no-op) before asserting the revision invariant.
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"],
                         "<p>متن تغییریافته توسط مسیر قدیمی</p>")

        draft.refresh_from_db()
        # DESIRED invariant — FAILS at baseline (L01 RED): legacy mutation
        # advances the Draft-wide revision token.
        self.assertEqual(draft.edit_revision, starting_revision + 1)

    def test_baseline_legacy_mutation_does_not_advance_edit_revision(self):
        """OBSERVED BASELINE (GREEN today, documents the L01 defect): a real
        legacy setting change records edit history but leaves ``edit_revision``
        completely unchanged. This test is intentionally an *anti-invariant*
        witness and is expected to flip / be removed once L01 is fixed in
        Task 3."""
        draft, section = self._draft_with_rich_text_section()
        starting_revision = draft.edit_revision

        response = self._post_change(section, "<p>متن دیگر</p>")
        self.assertEqual(response.status_code, 302)

        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>متن دیگر</p>")

        draft.refresh_from_db()
        # Baseline reality: no revision advance on legacy mutation.
        self.assertEqual(draft.edit_revision, starting_revision)
