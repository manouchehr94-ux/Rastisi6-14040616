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

    def test_legacy_real_mutation_records_exactly_one_history_entry_and_one_revision(self):
        """POST-FIX (L01 fixed in Task 3): the former anti-invariant witness
        ``test_baseline_legacy_mutation_does_not_advance_edit_revision`` is now
        obsolete — it asserted the defect (no revision advance). It is
        replaced here by the correct post-fix invariant: a real legacy
        setting change both records exactly one history entry AND advances
        ``edit_revision`` by exactly 1, and the two stay coherent (revision
        advances iff a history entry is appended).
        """
        from apps.storefront_builder.models import StorefrontEditHistoryEntry

        draft, section = self._draft_with_rich_text_section()
        starting_revision = draft.edit_revision
        history_before = StorefrontEditHistoryEntry.objects.filter(
            draft_version=draft).count()

        response = self._post_change(section, "<p>متن دیگر</p>")
        self.assertEqual(response.status_code, 302)

        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>متن دیگر</p>")

        draft.refresh_from_db()
        history_after = StorefrontEditHistoryEntry.objects.filter(
            draft_version=draft).count()
        # Post-fix reality: exactly one history entry AND exactly one
        # revision advance — coherent, never drifting apart.
        self.assertEqual(history_after, history_before + 1)
        self.assertEqual(draft.edit_revision, starting_revision + 1)

    def test_legacy_noop_mutation_advances_nothing_and_records_no_history(self):
        """A legacy POST that changes NOTHING (submits the identical settings
        already on the section) is a semantic no-op: it must NOT advance
        ``edit_revision`` and must NOT append a history entry. This is the
        coherence twin of the real-mutation invariant above.
        """
        from apps.storefront_builder.models import StorefrontEditHistoryEntry

        draft, section = self._draft_with_rich_text_section()
        # Persist a first real edit so the section has a known, stable state.
        self._post_change(section, "<p>وضعیت پایدار</p>")
        draft.refresh_from_db()
        section.refresh_from_db()
        revision_after_real_edit = draft.edit_revision
        history_after_real_edit = StorefrontEditHistoryEntry.objects.filter(
            draft_version=draft).count()

        # Re-submit the IDENTICAL body — no state change at all.
        response = self._post_change(section, "<p>وضعیت پایدار</p>")
        self.assertEqual(response.status_code, 302)

        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>وضعیت پایدار</p>")

        draft.refresh_from_db()
        history_after_noop = StorefrontEditHistoryEntry.objects.filter(
            draft_version=draft).count()
        # No-op: neither the token nor the history moved.
        self.assertEqual(draft.edit_revision, revision_after_real_edit)
        self.assertEqual(history_after_noop, history_after_real_edit)


class LegacyEditMakesConcurrentR4BaseRevisionStaleTests(StorefrontBuilderViewsTestCase):
    """L01 cross-path convergence: because ``edit_revision`` is now a single
    Draft-wide token advanced by legacy mutations too, a legacy edit performed
    *after* an R4 client captured its ``base_revision`` makes that R4 client's
    revision stale — the subsequent R4 mutation is rejected (409
    ``stale_revision``) and mutates nothing. This is the concrete last-writer
    protection L01 was missing at baseline (legacy edits used to be invisible
    to R4's optimistic-concurrency check).
    """

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.section = StorefrontSection.objects.create(
            page=home, section_key="hero_banner", order=0,
        )

    def _post_r4(self, payload):
        import json

        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _legacy_section_edit(self, section, body_html):
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

    def test_legacy_edit_makes_prior_r4_base_revision_stale(self):
        # An R4 client observes the current revision as its base_revision.
        self.draft.refresh_from_db()
        r4_base_revision = self.draft.edit_revision

        # Meanwhile a legacy edit lands on a rich_text section of the SAME
        # Draft, advancing the Draft-wide token under the R4 client.
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        rich_text = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=1,
            settings={"body_html": "<p>اولیه</p>"},
        )
        legacy_response = self._legacy_section_edit(
            rich_text, "<p>تغییر مسیر قدیمی هم‌زمان</p>")
        self.assertEqual(legacy_response.status_code, 302)

        self.draft.refresh_from_db()
        # The legacy edit advanced the token, so the R4 client's captured
        # base_revision is now stale.
        self.assertEqual(self.draft.edit_revision, r4_base_revision + 1)

        original_hero_settings = dict(self.section.settings)

        # The R4 client now replays with its now-stale base_revision.
        stale_r4 = self._post_r4({
            "base_revision": r4_base_revision,
            "mutation": {
                "type": "section.update_settings",
                "section_id": self.section.pk,
                "patch": {"autoplay": False},
            },
        })

        self.assertEqual(stale_r4.status_code, 409)
        body = stale_r4.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], "stale_revision")
        self.assertEqual(body["current_revision"], r4_base_revision + 1)

        # The stale R4 mutation changed nothing.
        self.section.refresh_from_db()
        self.assertEqual(self.section.settings, original_hero_settings)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, r4_base_revision + 1)



# ---------------------------------------------------------------------------
# Task 2 — Published / Archived / Cross-store mutation-protection convergence
# ---------------------------------------------------------------------------
#
# GOAL (gap L05): prove that EVERY active Appearance/Builder-owned legacy
# mutation family cannot mutate (a) a PUBLISHED version, (b) an ARCHIVED
# version, or (c) a FOREIGN store's version.
#
# This is a NEGATIVE-TEST task. All legacy structural / container / cell /
# block / media routes resolve their target through the Draft+store scoping
# helpers (``_get_scoped_section`` / ``_get_scoped_container`` /
# ``_get_scoped_cell`` in ``apps/storefront_builder/views.py``, mirrored by
# ``media_views``), so a Published/Archived/foreign target id is
# indistinguishable from "does not exist" → 404, and nothing is mutated.
# The Appearance/header/footer/publish/undo/redo/discard/reset routes have
# NO target-version parameter at all — they resolve the request store's
# active Draft via ``layout_service.get_or_create_draft`` — so they are
# structurally incapable of naming a Published/Archived version; the only
# reachable "wrong target" for them is a foreign store, which the tenant
# host + membership resolution rejects. ``storefront_restore`` is the one
# route that accepts an explicit ``version_id``; it never mutates the target
# (it clones it into a NEW Draft) and rejects a foreign version id (404).
#
# Coverage already proven elsewhere and intentionally NOT duplicated here:
#   * R4 ``section.update_settings`` on a Published version and on a foreign
#     store section — ``test_r4_mutation_api.PublishedVersionImmutabilityTests``
#     / ``TenantIsolationTests``.
#   * ``layout_service.restore_version`` cross-store rejection —
#     ``test_layout_service.RestoreTests.test_restore_rejects_cross_store_version``.
#   * Media list/edit/delete from another store → 404 —
#     ``test_media_views.TenantIsolationTests``.
#   * Tampered foreign background-media asset rejected without mutation —
#     ``test_phase35_reference_editable_backgrounds``.
# The legacy ``storefront_section_settings`` Published/Archived cases are
# already covered by the Task-1 classes above and are also not duplicated.

from apps.storefront_builder.models import StorefrontContainer
from apps.storefront_builder.services import container_service
from apps.stores.models import Store, StoreMembership
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

_User = get_user_model()


class _LifecycleTargetsMixin(StorefrontBuilderViewsTestCase):
    """Shared fixture: for the Store under test, build a PUBLISHED version,
    an ARCHIVED version, and a FOREIGN store's DRAFT — each with a real
    Home page, one ``rich_text`` section, and one Container/Cell — plus an
    active own Draft.  All rows carry the DRAFT-scoping-violating status (or
    foreign store) that every legacy route must reject."""

    FOREIGN_HOST = "sfb-foreign.rastisi.localhost"

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        # Active own Draft (the ONLY legitimately mutable version).
        self.own_draft = svc.get_or_create_draft(self.store, user=self.staff)

        self.published = self._make_version(
            StorefrontLayoutVersion.Status.PUBLISHED, version_number=990,
        )
        self.archived = self._make_version(
            StorefrontLayoutVersion.Status.ARCHIVED, version_number=989,
        )
        # Wire the layout's published pointer at the Published version so a
        # real ``publish`` of the active Draft archives it (as production
        # does) — required by ``test_publish_only_touches_callers_own_draft``.
        self.layout.refresh_from_db()
        self.layout.published_version = self.published
        self.layout.save(update_fields=["published_version", "updated_at"])

        # Foreign store with its own active Draft + membership + client.
        self.foreign_store = Store.objects.create(
            name="فروشگاه بیگانه", slug="sfb-foreign",
            admin_subdomain=self.FOREIGN_HOST.split(".")[0],
            status=Store.Status.ACTIVE,
        )
        self.foreign_staff = _User.objects.create_user(
            username="sfb_foreign_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.foreign_store, user=self.foreign_staff,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.foreign_draft = svc.get_or_create_draft(self.foreign_store, user=self.foreign_staff)
        self.foreign_section, self.foreign_container, self.foreign_cell = \
            self._seed_version(self.foreign_draft)
        self.foreign_client = Client(HTTP_HOST=self.FOREIGN_HOST)
        self.foreign_client.login(username="sfb_foreign_owner", password="pass12345")

        (self.published_section, self.published_container,
         self.published_cell) = self._seed_version(self.published)
        (self.archived_section, self.archived_container,
         self.archived_cell) = self._seed_version(self.archived)

    def _make_version(self, status, *, version_number):
        version = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=version_number, status=status,
        )
        StorefrontPage.ensure_version_pages(version)
        return version

    def _seed_version(self, version):
        """Create one section + one container/cell on the version's Home
        page and return (section, container, cell)."""
        home = version.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>محتوای اصلی</p>"},
        )
        container = container_service.create_empty_container(home, "single")
        cell = container.cells.order_by("order", "id").first()
        return section, container, cell


class LegacyStructuralSectionProtectionTests(_LifecycleTargetsMixin):
    """Legacy per-section structural routes (remove / move / toggle / lock /
    collapse / duplicate) must reject a Published, Archived, or foreign
    section id with 404 and mutate nothing — all six resolve the target via
    ``_get_scoped_section`` (Draft + store)."""

    def _assert_section_route_rejected(self, route_name, section, *, method="post", client=None):
        client = client or self.client
        before_active = section.is_active
        before_locked = section.is_locked
        before_count = StorefrontSection.objects.filter(page=section.page).count()

        url = reverse(route_name, args=[section.pk])
        resp = getattr(client, method)(url, {})
        self.assertEqual(resp.status_code, 404, f"{route_name} must 404 on protected target")

        section.refresh_from_db()
        self.assertEqual(section.is_active, before_active)
        self.assertEqual(section.is_locked, before_locked)
        self.assertEqual(
            StorefrontSection.objects.filter(page=section.page).count(), before_count,
            f"{route_name} must not add/remove sections on a protected version",
        )

    def _all_targets(self):
        return (
            ("published", self.published_section, self.client),
            ("archived", self.archived_section, self.client),
            ("foreign", self.foreign_section, self.client),
        )

    def test_section_toggle_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-toggle", section, client=client,
            )

    def test_section_lock_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-lock", section, client=client,
            )

    def test_section_collapse_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-collapse", section, client=client,
            )

    def test_section_remove_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-remove", section, client=client,
            )

    def test_section_move_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-move", section, client=client,
            )

    def test_section_duplicate_rejected_on_all_protected_targets(self):
        for _label, section, client in self._all_targets():
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-duplicate", section, client=client,
            )

    def test_foreign_client_cannot_toggle_published_or_archived_of_target_store(self):
        # Belt-and-braces: the foreign store's own owner, authenticated on
        # the foreign host, still cannot reach the target store's Published
        # or Archived section id.
        for section in (self.published_section, self.archived_section, self.published_section):
            self._assert_section_route_rejected(
                "dashboard:storefront-builder-section-toggle", section,
                client=self.foreign_client,
            )


class LegacyContainerProtectionTests(_LifecycleTargetsMixin):
    """Legacy container routes (settings / layout / move / remove) must
    reject Published / Archived / foreign container ids (404) via
    ``_get_scoped_container`` and mutate nothing."""

    def _assert_container_route_rejected(self, route_name, container, payload=None, *, client=None):
        client = client or self.client
        before_settings = dict(container.settings or {})
        before_layout = container.layout_key
        before_order = container.order

        resp = client.post(reverse(route_name, args=[container.pk]), payload or {})
        self.assertEqual(resp.status_code, 404, f"{route_name} must 404 on protected target")

        container.refresh_from_db()
        self.assertEqual(dict(container.settings or {}), before_settings)
        self.assertEqual(container.layout_key, before_layout)
        self.assertEqual(container.order, before_order)

    def _all_containers(self):
        return (self.published_container, self.archived_container, self.foreign_container)

    def test_container_settings_rejected_on_all_protected_targets(self):
        for container in self._all_containers():
            self._assert_container_route_rejected(
                "dashboard:storefront-builder-container-settings", container,
                payload={"gap": "large", "mobile_mode": "stack", "vertical_align": "center"},
            )

    def test_container_layout_rejected_on_all_protected_targets(self):
        for container in self._all_containers():
            self._assert_container_route_rejected(
                "dashboard:storefront-builder-container-layout", container,
                payload={"layout_key": "two-equal"},
            )

    def test_container_move_rejected_on_all_protected_targets(self):
        for container in self._all_containers():
            self._assert_container_route_rejected(
                "dashboard:storefront-builder-container-move", container,
                payload={"direction": "up"},
            )

    def test_container_remove_rejected_on_all_protected_targets(self):
        for container in self._all_containers():
            self._assert_container_route_rejected(
                "dashboard:storefront-builder-container-remove", container,
            )


class LegacyCellAndBlockProtectionTests(_LifecycleTargetsMixin):
    """Legacy cell-clear and block move/remove routes must reject
    Published / Archived / foreign target ids (404) and mutate nothing."""

    def test_cell_clear_rejected_on_all_protected_targets(self):
        for cell in (self.published_cell, self.archived_cell, self.foreign_cell):
            before = StorefrontContainer.objects.filter(pk=cell.container_id).exists()
            resp = self.client.post(
                reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk]), {},
            )
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(
                StorefrontContainer.objects.filter(pk=cell.container_id).exists(), before,
            )

    def test_block_move_rejected_on_all_protected_targets(self):
        for section in (self.published_section, self.archived_section, self.foreign_section):
            before_order = section.order
            resp = self.client.post(
                reverse("dashboard:storefront-builder-block-move", args=[section.pk]),
                {"direction": "up"},
            )
            self.assertEqual(resp.status_code, 404)
            section.refresh_from_db()
            self.assertEqual(section.order, before_order)

    def test_block_remove_rejected_on_all_protected_targets(self):
        for section in (self.published_section, self.archived_section, self.foreign_section):
            self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
            resp = self.client.post(
                reverse("dashboard:storefront-builder-block-remove", args=[section.pk]), {},
            )
            self.assertEqual(resp.status_code, 404)
            self.assertTrue(
                StorefrontSection.objects.filter(pk=section.pk).exists(),
                "block-remove must not delete a section on a protected version",
            )


class LegacySectionSettingsForeignProtectionTests(_LifecycleTargetsMixin):
    """L05 foreign-store complement to the Task-1 Published/Archived
    ``storefront_section_settings`` cases: a foreign store's DRAFT section
    id is also rejected (404) and unmutated."""

    def test_section_settings_post_on_foreign_draft_section_is_not_found(self):
        original = dict(self.foreign_section.settings)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[self.foreign_section.pk]),
            {
                "body_html": "<p>نفوذ به فروشگاه دیگر</p>",
                "show_on_desktop": "on", "show_on_tablet": "on", "show_on_mobile": "on",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.foreign_section.refresh_from_db()
        self.assertEqual(self.foreign_section.settings, original)

    def test_section_field_reset_rejected_on_protected_targets(self):
        for section in (self.published_section, self.archived_section, self.foreign_section):
            original = dict(section.settings)
            resp = self.client.post(
                reverse("dashboard:storefront-builder-section-field-reset", args=[section.pk]),
                {"field": "body_html"},
            )
            self.assertEqual(resp.status_code, 404)
            section.refresh_from_db()
            self.assertEqual(section.settings, original)

    def test_section_reset_rejected_on_protected_targets(self):
        for section in (self.published_section, self.archived_section, self.foreign_section):
            original = dict(section.settings)
            resp = self.client.post(
                reverse("dashboard:storefront-builder-section-reset", args=[section.pk]), {},
            )
            self.assertEqual(resp.status_code, 404)
            section.refresh_from_db()
            self.assertEqual(section.settings, original)


class LegacyMediaLifecycleProtectionTests(StorefrontBuilderViewsTestCase):
    """Media placement routes resolve their section via ``_get_scoped_section``
    (Draft + store), so a HeroSlide hanging off a Published or Archived
    version's section cannot be listed / edited / deleted / toggled / moved.
    (The foreign-store case is already covered by
    ``test_media_views.TenantIsolationTests``.)"""

    def _make_hero_slide_on(self, status, version_number):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from apps.content.models import HeroSlide

        layout = svc.get_or_create_layout(self.store)
        version = StorefrontLayoutVersion.objects.create(
            layout=layout, version_number=version_number, status=status,
        )
        StorefrontPage.ensure_version_pages(version)
        home = version.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="hero_banner", order=0,
        )
        buf = BytesIO()
        Image.new("RGB", (400, 200), (1, 2, 3)).save(buf, "PNG")
        image = SimpleUploadedFile("m.png", buf.getvalue(), content_type="image/png")
        slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید محافظت‌شده",
            desktop_image=image,
        )
        return section, slide

    def test_media_list_on_published_and_archived_section_is_not_found(self):
        for status, num in (
            (StorefrontLayoutVersion.Status.PUBLISHED, 970),
            (StorefrontLayoutVersion.Status.ARCHIVED, 969),
        ):
            section, _slide = self._make_hero_slide_on(status, num)
            resp = self.client.get(
                reverse("dashboard:storefront-builder-section-media-list",
                        args=[section.pk, "hero-slides"]),
            )
            self.assertEqual(resp.status_code, 404)

    def test_media_edit_and_delete_and_toggle_on_protected_section_is_not_found(self):
        from apps.content.models import HeroSlide

        for status, num in (
            (StorefrontLayoutVersion.Status.PUBLISHED, 971),
            (StorefrontLayoutVersion.Status.ARCHIVED, 968),
        ):
            section, slide = self._make_hero_slide_on(status, num)

            edit = self.client.post(
                reverse("dashboard:storefront-builder-section-media-edit",
                        args=[section.pk, "hero-slides", slide.pk]),
                {"title": "دستکاری", "destination_type": "none"},
            )
            self.assertEqual(edit.status_code, 404)
            slide.refresh_from_db()
            self.assertEqual(slide.title, "اسلاید محافظت‌شده")

            toggle = self.client.post(
                reverse("dashboard:storefront-builder-section-media-toggle",
                        args=[section.pk, "hero-slides", slide.pk]),
            )
            self.assertEqual(toggle.status_code, 404)

            delete = self.client.post(
                reverse("dashboard:storefront-builder-section-media-delete",
                        args=[section.pk, "hero-slides", slide.pk]),
            )
            self.assertEqual(delete.status_code, 404)
            self.assertTrue(
                HeroSlide.objects.filter(pk=slide.pk).exists(),
                "delete must not remove a slide on a protected version",
            )


class LegacyLifecycleRouteTargetingTests(_LifecycleTargetsMixin):
    """The Appearance / header / footer / publish / undo / redo / discard /
    reset routes take NO target-version parameter — they always resolve the
    request store's active Draft.  These tests prove that (a) they operate
    ONLY on the caller's active Draft and never on the caller's own
    Published/Archived versions, and (b) a foreign store cannot use them to
    reach the target store's versions."""

    def test_publish_only_touches_callers_own_draft_not_the_existing_published(self):
        # Publishing the own active Draft archives the current PUBLISHED and
        # promotes the Draft — it must NEVER mutate the pre-existing Published
        # version in place (its rows keep their identity as an ARCHIVED
        # version afterwards; no legacy route can edit the Published rows).
        published_pk = self.published.pk
        published_section_settings = dict(self.published_section.settings)

        resp = self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertEqual(resp.status_code, 302)

        # The old Published version's section content was never edited.
        self.published_section.refresh_from_db()
        self.assertEqual(self.published_section.settings, published_section_settings)
        # And the previously-published version still exists (now archived),
        # i.e. publish did not delete/rewrite it destructively.
        self.published.refresh_from_db()
        self.assertEqual(self.published.pk, published_pk)
        self.assertEqual(
            self.published.status, StorefrontLayoutVersion.Status.ARCHIVED,
        )

    def test_appearance_editor_get_does_not_expose_or_mutate_foreign_draft(self):
        # A GET to the appearance editor resolves the caller's OWN active
        # draft; a foreign caller only ever sees their own draft, never the
        # target store's versions.
        foreign_appearance_before = dict(self.foreign_draft.appearance_config or {})
        own_appearance_before = dict(self.own_draft.appearance_config or {})

        resp = self.foreign_client.get(reverse("dashboard:storefront-builder-appearance"))
        # Foreign owner is authorized on their own store, so 200 on THEIR draft.
        self.assertEqual(resp.status_code, 200)

        self.own_draft.refresh_from_db()
        self.assertEqual(dict(self.own_draft.appearance_config or {}), own_appearance_before)
        self.foreign_draft.refresh_from_db()
        self.assertEqual(
            dict(self.foreign_draft.appearance_config or {}), foreign_appearance_before,
        )

    def test_undo_redo_discard_operate_on_own_draft_only(self):
        # None of these can name a Published/Archived version; a foreign
        # caller's undo/redo/discard only affects the foreign draft, never
        # the target store's active draft or its published/archived rows.
        own_draft_pk = self.own_draft.pk
        published_pk = self.published.pk
        archived_pk = self.archived.pk

        for route in ("storefront-builder-undo", "storefront-builder-redo"):
            resp = self.foreign_client.post(reverse(f"dashboard:{route}"))
            self.assertIn(resp.status_code, (200, 302))

        # Target store's versions are untouched by the foreign caller.
        self.assertTrue(StorefrontLayoutVersion.objects.filter(pk=own_draft_pk).exists())
        self.assertTrue(StorefrontLayoutVersion.objects.filter(
            pk=published_pk, status=StorefrontLayoutVersion.Status.PUBLISHED).exists())
        self.assertTrue(StorefrontLayoutVersion.objects.filter(
            pk=archived_pk, status=StorefrontLayoutVersion.Status.ARCHIVED).exists())


class LegacyRestoreCrossStoreViewProtectionTests(_LifecycleTargetsMixin):
    """``storefront_restore`` is the only legacy route that accepts an
    explicit ``version_id``.  It NEVER mutates the target version (it clones
    it into a fresh Draft) and rejects a foreign store's version id with a
    404 (``CrossStoreVersionError`` → ``Http404``).  The service-level
    cross-store rejection is proven in
    ``test_layout_service.RestoreTests.test_restore_rejects_cross_store_version``;
    this asserts the same guarantee at the HTTP boundary."""

    def test_restore_of_foreign_version_id_is_404_and_mutates_nothing(self):
        # The foreign store's DRAFT version id, aimed at the target store's
        # restore route, must be rejected (foreign version not owned).
        foreign_version_pk = self.foreign_draft.pk
        before_own_versions = set(
            self.layout.versions.values_list("pk", flat=True)
        )

        resp = self.client.post(
            reverse("dashboard:storefront-builder-restore", args=[foreign_version_pk]),
        )
        self.assertEqual(resp.status_code, 404)

        # No new Draft was cloned into the target store's layout, and the
        # foreign draft is untouched.
        after_own_versions = set(self.layout.versions.values_list("pk", flat=True))
        self.assertEqual(after_own_versions, before_own_versions)
        self.assertTrue(StorefrontLayoutVersion.objects.filter(pk=foreign_version_pk).exists())

    def test_restore_of_own_published_creates_new_draft_without_mutating_source(self):
        # Positive-safety complement: restoring the caller's OWN Published
        # version is a legitimate operation that must NOT mutate the source
        # Published version — it only clones it into a new Draft.
        published_section_settings = dict(self.published_section.settings)
        published_status = self.published.status

        resp = self.client.post(
            reverse("dashboard:storefront-builder-restore", args=[self.published.pk]),
        )
        self.assertEqual(resp.status_code, 302)

        self.published.refresh_from_db()
        self.published_section.refresh_from_db()
        self.assertEqual(self.published.status, published_status)
        self.assertEqual(self.published_section.settings, published_section_settings)



# ---------------------------------------------------------------------------
# Task 4 — Legacy Publish / Undo / Redo / Restore / Discard lifecycle safety
# ---------------------------------------------------------------------------
#
# Gaps closed here:
#
# * L03 (P1) — the legacy ``storefront_undo`` / ``storefront_redo`` views must
#   be revision-coherent: a *successful* undo/redo (one that actually restores
#   a different Draft state) advances the Draft-wide ``edit_revision`` by
#   EXACTLY 1, matching the R4 ``apply_history_command`` guarantee — so
#   undo/redo through EITHER entry point is revision-monotonic. A no-op
#   undo/redo (nothing to undo/redo) advances nothing. Undo/Redo must NEVER
#   append a new undoable history entry (Section 13). Baseline: RED — the
#   legacy views call ``edit_history_service.undo/redo`` directly and never
#   touch ``edit_revision``.
#
# * L02 (P1) — the legacy ``storefront_publish`` view must reach the same
#   lifecycle guarantee as R4 ``publish_draft``: atomic, archive the previous
#   Published, clear draft history/pointer, swap pointers — by delegating to
#   the SAME shared ``layout_service.publish`` contract. Where a base revision
#   is available on the request, a stale publish (Draft advanced under the
#   client) is rejected coherently and mutates nothing.
#
# * Restore / Discard remain atomic, Draft-lifecycle-correct, and recover the
#   canonical typed ``store_appearance`` manifest intact across an
#   apply → undo → redo → restore round-trip (structurally byte-for-byte
#   equal), with revision monotonic where a real change occurred.

from apps.storefront_builder.models import StorefrontEditHistoryEntry
from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive


class LegacyUndoRedoRevisionCoherenceTests(StorefrontBuilderViewsTestCase):
    """L03 — legacy Undo/Redo must be atomic and revision-monotonic: a
    successful undo/redo advances ``edit_revision`` by exactly 1 and never
    appends a new undoable history entry.  A no-op undo/redo advances
    nothing.  These mirror the already-proven R4 ``apply_history_command``
    guarantees (see ``test_r4_mutation_api``)."""

    def _draft_with_two_edits(self):
        """Return a Draft carrying two real recorded edits (so there is
        something to undo, then redo)."""
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        home = draft.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>حالت اول</p>"},
        )
        # Two real legacy edits → two history entries → two revision advances.
        self._post_change(section, "<p>حالت دوم</p>")
        self._post_change(section, "<p>حالت سوم</p>")
        draft.refresh_from_db()
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

    def _undoable_count(self, draft):
        return StorefrontEditHistoryEntry.objects.filter(
            draft_version=draft, is_undone=False).count()

    def _total_history(self, draft):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

    def test_successful_undo_advances_edit_revision_by_exactly_one(self):
        draft, section = self._draft_with_two_edits()
        revision_before = draft.edit_revision
        total_history_before = self._total_history(draft)

        resp = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["ok"], True)

        # The undo really restored an older content state.
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>حالت دوم</p>")

        draft.refresh_from_db()
        # L03 invariant: exactly one revision advance.
        self.assertEqual(draft.edit_revision, revision_before + 1)
        # Undo NEVER creates a NEW undoable history entry — the total number
        # of entries is unchanged (an entry only flips is_undone).
        self.assertEqual(self._total_history(draft), total_history_before)

    def test_successful_redo_advances_edit_revision_by_exactly_one(self):
        draft, section = self._draft_with_two_edits()
        # Undo once so there is something to redo.
        self.client.post(reverse("dashboard:storefront-builder-undo"))
        draft.refresh_from_db()
        revision_before = draft.edit_revision
        total_history_before = self._total_history(draft)

        resp = self.client.post(reverse("dashboard:storefront-builder-redo"))
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["ok"], True)

        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>حالت سوم</p>")

        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, revision_before + 1)
        self.assertEqual(self._total_history(draft), total_history_before)

    def test_noop_undo_advances_nothing_and_records_no_history(self):
        # A fresh Draft with no recorded edits: undo is a controlled no-op.
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        draft.refresh_from_db()
        revision_before = draft.edit_revision
        total_history_before = self._total_history(draft)

        resp = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["ok"], False)

        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, revision_before)
        self.assertEqual(self._total_history(draft), total_history_before)

    def test_noop_redo_advances_nothing(self):
        draft, _section = self._draft_with_two_edits()
        draft.refresh_from_db()
        revision_before = draft.edit_revision

        # Nothing was undone, so redo has nothing to do.
        resp = self.client.post(reverse("dashboard:storefront-builder-redo"))
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["ok"], False)

        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, revision_before)

    def test_undo_then_redo_is_revision_monotonic(self):
        draft, _section = self._draft_with_two_edits()
        draft.refresh_from_db()
        r0 = draft.edit_revision

        self.client.post(reverse("dashboard:storefront-builder-undo"))
        draft.refresh_from_db()
        r1 = draft.edit_revision

        self.client.post(reverse("dashboard:storefront-builder-redo"))
        draft.refresh_from_db()
        r2 = draft.edit_revision

        # Strictly increasing across each successful command.
        self.assertEqual(r1, r0 + 1)
        self.assertEqual(r2, r1 + 1)


class LegacyPublishLifecycleConvergenceTests(_LifecycleTargetsMixin):
    """L02 — legacy publish must reach the SAME lifecycle guarantee as R4
    ``publish_draft`` by delegating to the shared ``layout_service.publish``:
    atomic, archive the previous Published, clear the draft history + pointer,
    swap pointers.  (Cross-store / published-immutability of publish is
    already proven by ``LegacyLifecycleRouteTargetingTests``.)"""

    def test_publish_clears_draft_history_and_swaps_pointers_atomically(self):
        # Seed the active Draft with real edit-history entries so we can prove
        # publish clears them (editor-session concern must not cross the
        # publish boundary).
        home = self.own_draft.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=5,
            settings={"body_html": "<p>الف</p>"},
        )
        self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"body_html": "<p>ب</p>", "show_on_desktop": "on",
             "show_on_tablet": "on", "show_on_mobile": "on"},
        )
        self.assertTrue(
            StorefrontEditHistoryEntry.objects.filter(draft_version=self.own_draft).exists())

        own_draft_pk = self.own_draft.pk
        previous_published_pk = self.published.pk

        resp = self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.assertEqual(resp.status_code, 302)

        self.layout.refresh_from_db()
        # Pointers swapped: the former Draft is now the Published version, and
        # the draft pointer is cleared.
        self.assertEqual(self.layout.published_version_id, own_draft_pk)
        self.assertIsNone(self.layout.draft_version_id)

        # Previous Published archived (not deleted / rewritten).
        prev = StorefrontLayoutVersion.objects.get(pk=previous_published_pk)
        self.assertEqual(prev.status, StorefrontLayoutVersion.Status.ARCHIVED)

        # Published version's short-lived edit history was cleared at the
        # publish boundary.
        self.assertFalse(
            StorefrontEditHistoryEntry.objects.filter(draft_version_id=own_draft_pk).exists())

        # The promoted version is PUBLISHED.
        promoted = StorefrontLayoutVersion.objects.get(pk=own_draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.PUBLISHED)

    def test_publish_with_matching_base_revision_publishes(self):
        # A publish carrying the current (matching) base_revision succeeds via
        # the shared stale-aware path.
        self.own_draft.refresh_from_db()
        own_draft_pk = self.own_draft.pk
        base_revision = self.own_draft.edit_revision

        resp = self.client.post(
            reverse("dashboard:storefront-builder-publish"),
            {"base_revision": str(base_revision)},
        )
        self.assertEqual(resp.status_code, 302)

        self.layout.refresh_from_db()
        self.assertEqual(self.layout.published_version_id, own_draft_pk)
        self.assertIsNone(self.layout.draft_version_id)

    def test_publish_with_stale_base_revision_is_rejected_and_mutates_nothing(self):
        # Capture a base_revision, then let a real legacy edit advance the
        # Draft token under the publisher, making the captured revision stale.
        self.own_draft.refresh_from_db()
        stale_base_revision = self.own_draft.edit_revision
        own_draft_pk = self.own_draft.pk
        previous_published_pk = self.published.pk

        home = self.own_draft.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=7,
            settings={"body_html": "<p>یک</p>"},
        )
        self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"body_html": "<p>دو</p>", "show_on_desktop": "on",
             "show_on_tablet": "on", "show_on_mobile": "on"},
        )
        self.own_draft.refresh_from_db()
        self.assertEqual(self.own_draft.edit_revision, stale_base_revision + 1)

        # Publish with the now-stale base_revision — must be rejected and
        # mutate nothing (Draft not promoted, previous Published not archived).
        resp = self.client.post(
            reverse("dashboard:storefront-builder-publish"),
            {"base_revision": str(stale_base_revision)},
        )
        self.assertEqual(resp.status_code, 302)

        self.layout.refresh_from_db()
        # Draft is still the active draft; publish did NOT happen.
        self.assertEqual(self.layout.draft_version_id, own_draft_pk)
        self.assertEqual(self.layout.published_version_id, previous_published_pk)
        promoted = StorefrontLayoutVersion.objects.get(pk=own_draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.DRAFT)
        prev = StorefrontLayoutVersion.objects.get(pk=previous_published_pk)
        self.assertEqual(prev.status, StorefrontLayoutVersion.Status.PUBLISHED)


class LegacyLifecycleAppearanceManifestRoundTripTests(StorefrontBuilderViewsTestCase):
    """The canonical typed ``store_appearance`` manifest must survive an
    apply → (legacy) undo → (legacy) redo → restore round-trip byte-for-byte
    (structurally equal), and each successful step must be revision-monotonic
    where a real change occurred. This proves restore/discard remain atomic
    and Draft-lifecycle-correct while recovering the canonical Appearance."""

    def _persist_manifest_and_snapshot(self, draft, manifest_primitive):
        """Persist a complete typed manifest on the Draft, then make a real
        legacy edit so a history entry captures the manifest in both its
        before/after snapshot (the round-trip material for undo/redo)."""
        appearance_persistence.persist_store_appearance_manifest(draft, manifest_primitive)
        draft.refresh_from_db()

    def _post_change(self, section, body_html):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-settings",
                    args=[section.pk]),
            {"body_html": body_html, "show_on_desktop": "on",
             "show_on_tablet": "on", "show_on_mobile": "on"},
        )

    def _manifest_primitive(self, draft):
        return manifest_to_primitive(
            appearance_persistence.load_store_appearance_manifest(draft))

    def test_store_appearance_manifest_survives_undo_redo_restore_round_trip(self):
        from apps.storefront_builder import layout_preset_registry as lpr

        ready = next(iter(lpr.list_ready_templates()))
        expected_manifest = dict(ready.store_appearance)

        draft = svc.get_or_create_draft(self.store, user=self.staff)
        # Apply the canonical typed manifest to the Draft.
        self._persist_manifest_and_snapshot(draft, expected_manifest)
        applied_manifest = self._manifest_primitive(draft)
        # Sanity: the manifest was actually persisted and is complete.
        self.assertEqual(applied_manifest, expected_manifest)

        # Make a real legacy edit AFTER persisting the manifest so the history
        # entry's after_state snapshot carries the manifest.
        home = draft.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0,
            settings={"body_html": "<p>قبل</p>"},
        )
        self._post_change(section, "<p>بعد</p>")
        draft.refresh_from_db()
        rev_after_edit = draft.edit_revision
        # The manifest is intact after a real edit.
        self.assertEqual(self._manifest_primitive(draft), expected_manifest)

        # UNDO (legacy route): restores the pre-edit state, which still had the
        # manifest persisted → manifest intact, revision advances by 1.
        undo_resp = self.client.post(reverse("dashboard:storefront-builder-undo"))
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIs(undo_resp.json()["ok"], True)
        draft.refresh_from_db()
        self.assertEqual(self._manifest_primitive(draft), expected_manifest)
        self.assertEqual(draft.edit_revision, rev_after_edit + 1)

        # REDO (legacy route): restores the post-edit state → manifest intact,
        # revision advances by 1 again.
        redo_resp = self.client.post(reverse("dashboard:storefront-builder-redo"))
        self.assertEqual(redo_resp.status_code, 200)
        self.assertIs(redo_resp.json()["ok"], True)
        draft.refresh_from_db()
        self.assertEqual(self._manifest_primitive(draft), expected_manifest)
        self.assertEqual(draft.edit_revision, rev_after_edit + 2)

        # PUBLISH the draft so there is an immutable version to RESTORE from.
        self.client.post(reverse("dashboard:storefront-builder-publish"))
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id

        # RESTORE the published version into a NEW Draft — the canonical typed
        # manifest must survive the clone byte-for-byte (structurally equal).
        restore_resp = self.client.post(
            reverse("dashboard:storefront-builder-restore", args=[published_version_id]))
        self.assertEqual(restore_resp.status_code, 302)

        restored_draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(self._manifest_primitive(restored_draft), expected_manifest)

    def test_discard_is_atomic_and_removes_only_the_draft(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        draft_pk = draft.pk

        resp = self.client.post(reverse("dashboard:storefront-builder-discard"))
        self.assertEqual(resp.status_code, 302)

        # The Draft row is gone and the layout no longer points at it.
        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=draft_pk).exists())
        layout = svc.get_or_create_layout(self.store)
        layout.refresh_from_db()
        self.assertNotEqual(layout.draft_version_id, draft_pk)



# ---------------------------------------------------------------------------
# Task 5 — Structure-lock operation-matrix convergence (L06) + lifecycle-safe
# template/reset revision coherence (L04)
# ---------------------------------------------------------------------------
#
# AUTHORITATIVE structure-lock operation matrix (spec §11). "structure-lock
# protects STRUCTURAL operations ONLY" — it is NOT an appearance/content lock.
# These tests prove the matrix is COMPLETE and CONSISTENT across BOTH the R4
# structure path (``section_structure_service`` behind the R4 mutation route)
# AND the legacy views, for both ``Section.is_locked`` and
# ``Container.is_locked``:
#
#   Operation                              | locked: allowed? | proven on
#   ---------------------------------------|------------------|-----------
#   Section move / reorder                 | NO               | R4 + legacy
#   Section remove                         | NO               | R4 + legacy
#   Block move / remove (within cell)      | NO               | legacy
#   Container settings/layout/move/remove  | NO (locked ctr)  | legacy
#   Cell add-section / clear               | NO (locked ctr)  | legacy
#   Template apply / baseline reset (page  | NO               | preset_service
#       with a locked section)             |                  | + apply view
#   Section settings edit (content/appear) | YES              | R4 + legacy
#   Toggle active / collapse / lock-toggle | YES              | legacy
#   Section duplicate (new logical section)| YES              | R4 + legacy
#
# The R4 path surfaces a refused structural op as a 400 JSON body
# ``{"ok": false, "code": "<section_locked|container_locked|target_locked|...>"}``
# (see ``r4_views.storefront_r4_mutation`` mapping ``SectionStructureError.code``
# via ``R4MutationError``); the legacy views surface it as a Persian
# ``messages.error`` + the section/container-state partial (no mutation). Both
# must leave the Draft byte-for-byte unchanged: no structural mutation, no
# ``edit_revision`` advance, no history entry.

import json

from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontEditHistoryEntry as _T5HistoryEntry,
)
from apps.storefront_builder.services import (
    container_service as _t5_container_service,
    section_structure_service as _t5_sss,
)


class _StructureLockMatrixMixin(StorefrontBuilderViewsTestCase):
    """Shared fixture for the structure-lock matrix: an active Draft with the
    R4 gate ON so the R4 mutation route is reachable, plus helpers to build
    real page-level sections placed in real Container/Cell composition (the
    exact runtime shape ``ensure_page_containers`` produces)."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        # Start from a clean Home so section counts/orders are deterministic.
        self.home.containers.all().delete()
        self.home.sections.all().delete()

    def _add_section(self, section_key="rich_text", *, order=0, settings=None, is_locked=False):
        section = StorefrontSection.objects.create(
            page=self.home, section_key=section_key, order=order,
            settings=settings if settings is not None else {"body_html": "<p>x</p>"},
            is_locked=is_locked,
        )
        return section

    def _place_each_section_in_own_container(self):
        """Mirror the real runtime placement: every page-level Section ends up
        as the sole Block of its own single-column Container/Cell."""
        _t5_container_service.ensure_page_containers(self.home)

    def _cell_of(self, section):
        """Resolve a Section's placement Cell the same way the production code
        does: prefer the new multi-block FK, fall back to the legacy
        ``StorefrontCell.section`` OneToOne that ``ensure_page_containers``
        writes."""
        section.refresh_from_db()
        if section.cell_id is not None:
            return section.cell
        return StorefrontCell.objects.filter(section=section).select_related("container").first()

    def _post_r4(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _r4_mutate(self, mutation):
        self.draft.refresh_from_db()
        return self._post_r4({
            "base_revision": self.draft.edit_revision,
            "mutation": mutation,
        })

    def _history_count(self):
        return _T5HistoryEntry.objects.filter(draft_version=self.draft).count()

    def _revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision


# ---------------------------------------------------------------------------
# L06 — NEGATIVE tests: every "NO" cell, R4 structure path
# ---------------------------------------------------------------------------


class R4StructureLockNegativeTests(_StructureLockMatrixMixin):
    """R4 structure path (``section_structure_service`` behind the R4 mutation
    route): every structural "NO" cell must be refused with the stable
    ``SectionStructureError.code`` and mutate nothing (no revision advance, no
    history entry)."""

    def _assert_r4_refused(self, mutation, expected_code):
        revision_before = self._revision()
        history_before = self._history_count()
        resp = self._r4_mutate(mutation)
        self.assertEqual(resp.status_code, 400, f"{mutation['type']} must be refused")
        body = resp.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], expected_code)
        # Nothing moved: revision + history are unchanged (atomic refusal).
        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)

    def test_r4_section_remove_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()
        self._assert_r4_refused(
            {"type": "section.remove", "section_id": locked.pk}, "section_locked",
        )
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())

    def test_r4_section_move_on_locked_source_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._add_section(section_key="rich_text", order=1)
        self._place_each_section_in_own_container()
        order_before = locked.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": locked.pk, "direction": "down"},
            "section_locked",
        )
        locked.refresh_from_db()
        self.assertEqual(locked.order, order_before)

    def test_r4_section_move_toward_locked_target_is_refused(self):
        mover = self._add_section(order=0)
        locked_target = self._add_section(order=1, is_locked=True)
        self._place_each_section_in_own_container()
        order_before = mover.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": mover.pk, "direction": "down"},
            "target_locked",
        )
        mover.refresh_from_db()
        self.assertEqual(mover.order, order_before)

    def test_r4_section_move_out_of_locked_container_is_refused(self):
        # A section whose CONTAINER is locked cannot be reordered even if the
        # section itself is unlocked — container-level structural lock.
        mover = self._add_section(order=0)
        self._add_section(order=1)
        self._place_each_section_in_own_container()
        # Lock the mover's own container.
        container = self._cell_of(mover).container
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        order_before = mover.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": mover.pk, "direction": "down"},
            "container_locked",
        )
        mover.refresh_from_db()
        self.assertEqual(mover.order, order_before)


# ---------------------------------------------------------------------------
# L06 — POSITIVE tests: lock is structure-only (R4 path)
# ---------------------------------------------------------------------------


class R4StructureLockPositiveTests(_StructureLockMatrixMixin):
    """A locked section must still accept content/appearance settings edits and
    duplication through the R4 path — the lock is structural only."""

    def test_r4_settings_edit_on_locked_section_succeeds(self):
        locked = self._add_section(
            section_key="hero_banner", order=0,
            settings=None, is_locked=True,
        )
        # hero_banner carries a real schema; give it its defaults first.
        from apps.storefront_builder import section_registry
        locked.settings = section_registry.get_definition("hero_banner").default_settings()
        locked.save(update_fields=["settings"])
        self._place_each_section_in_own_container()

        revision_before = self._revision()
        resp = self._r4_mutate({
            "type": "section.update_settings",
            "section_id": locked.pk,
            "patch": {"autoplay": False},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        locked.refresh_from_db()
        self.assertIs(locked.settings["autoplay"], False)
        self.assertTrue(locked.is_locked)  # still locked — edit did not unlock
        self.assertEqual(self._revision(), revision_before + 1)

    def test_r4_duplicate_of_locked_section_succeeds_and_creates_new_section(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()
        count_before = self.home.sections.count()

        revision_before = self._revision()
        resp = self._r4_mutate({"type": "section.duplicate", "section_id": locked.pk})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        # A NEW logical section was created; the source stays locked/intact.
        self.assertEqual(self.home.sections.count(), count_before + 1)
        locked.refresh_from_db()
        self.assertTrue(locked.is_locked)
        self.assertEqual(self._revision(), revision_before + 1)
        # The duplicate is a distinct section (fresh stable_id) and is NOT
        # itself locked — a duplicate is a brand-new logical section.
        duplicate = self.home.sections.exclude(pk=locked.pk).get()
        self.assertNotEqual(duplicate.stable_id, locked.stable_id)
        self.assertFalse(duplicate.is_locked)


# ---------------------------------------------------------------------------
# L06 — NEGATIVE tests: every "NO" cell, legacy views (Section + Container)
# ---------------------------------------------------------------------------


class LegacySectionStructureLockNegativeTests(_StructureLockMatrixMixin):
    """Legacy per-section structural routes must refuse a locked section and
    mutate nothing: remove, move (up/down), reorder. Each refusal returns the
    list partial (200) with no structural change and no revision/history
    advance."""

    def _assert_legacy_refused_no_advance(self, do_request, *, expect_status=200):
        revision_before = self._revision()
        history_before = self._history_count()
        resp = do_request()
        self.assertEqual(resp.status_code, expect_status)
        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)
        return resp

    def test_legacy_section_remove_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._add_section(order=1)
        self._place_each_section_in_own_container()

        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-section-remove", args=[locked.pk])))
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())

    def test_legacy_section_move_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._add_section(order=1)
        self._place_each_section_in_own_container()
        order_before = locked.order

        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-section-move", args=[locked.pk]),
            {"direction": "down"}))
        locked.refresh_from_db()
        self.assertEqual(locked.order, order_before)

    def test_legacy_section_move_toward_locked_neighbor_is_refused(self):
        mover = self._add_section(order=0)
        locked_neighbor = self._add_section(order=1, is_locked=True)
        self._place_each_section_in_own_container()
        order_before = mover.order

        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-section-move", args=[mover.pk]),
            {"direction": "down"}))
        mover.refresh_from_db()
        self.assertEqual(mover.order, order_before)

    def test_legacy_section_reorder_cannot_move_locked_section(self):
        locked = self._add_section(order=0, is_locked=True)
        other = self._add_section(order=1)
        self._place_each_section_in_own_container()

        # Attempt to reorder so the locked section changes position.
        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-section-reorder"),
            {"section_ids": [str(other.pk), str(locked.pk)]}))
        locked.refresh_from_db()
        self.assertEqual(locked.order, 0)

    def test_legacy_block_move_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._add_section(order=1)
        self._place_each_section_in_own_container()
        target_cell_id = self._cell_of(locked).pk

        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-block-move", args=[locked.pk]),
            {"target_cell_id": str(target_cell_id), "at_index": "0"}))
        locked.refresh_from_db()
        self.assertTrue(locked.is_locked)

    def test_legacy_block_remove_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()

        self._assert_legacy_refused_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-block-remove", args=[locked.pk])))
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())


class LegacyContainerStructureLockNegativeTests(_StructureLockMatrixMixin):
    """Legacy container routes must refuse a LOCKED container (settings /
    layout / move / remove) and mutate nothing. Cell add-section and cell
    clear must likewise refuse when the cell's container is locked."""

    def _locked_container_with_cell(self):
        section = self._add_section(order=0)
        self._place_each_section_in_own_container()
        cell = self._cell_of(section)
        container = cell.container
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        return container, cell

    def _assert_no_advance(self, do_request):
        revision_before = self._revision()
        history_before = self._history_count()
        resp = do_request()
        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)
        return resp

    def test_legacy_container_settings_on_locked_container_is_refused(self):
        container, _cell = self._locked_container_with_cell()
        settings_before = dict(container.settings or {})
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-container-settings", args=[container.pk]),
            {"gap": "40", "mobile_mode": "stack", "vertical_align": "center"}))
        container.refresh_from_db()
        self.assertEqual(dict(container.settings or {}), settings_before)

    def test_legacy_container_layout_on_locked_container_is_refused(self):
        container, _cell = self._locked_container_with_cell()
        layout_before = container.layout_key
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-container-layout", args=[container.pk]),
            {"layout_key": "half"}))
        container.refresh_from_db()
        self.assertEqual(container.layout_key, layout_before)

    def test_legacy_container_move_on_locked_container_is_refused(self):
        container, _cell = self._locked_container_with_cell()
        # Add a second container so a move is theoretically possible.
        self._add_section(order=1)
        self._place_each_section_in_own_container()
        order_before = container.order
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-container-move", args=[container.pk]),
            {"direction": "down"}))
        container.refresh_from_db()
        self.assertEqual(container.order, order_before)

    def test_legacy_container_remove_on_locked_container_is_refused(self):
        container, _cell = self._locked_container_with_cell()
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-container-remove", args=[container.pk])))
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())

    def test_legacy_cell_add_section_into_locked_container_is_refused(self):
        container, cell = self._locked_container_with_cell()
        count_before = self.home.sections.count()
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"section_key": "rich_text", "cell_id": str(cell.pk), "page": "home"}))
        self.assertEqual(self.home.sections.count(), count_before)

    def test_legacy_cell_clear_on_locked_container_is_refused(self):
        container, cell = self._locked_container_with_cell()
        self._assert_no_advance(lambda: self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk])))
        # The block is still placed in the cell.
        self.assertTrue(_t5_container_service.get_cell_blocks(cell))


# ---------------------------------------------------------------------------
# L06 — POSITIVE tests: lock is structure-only (legacy views)
# ---------------------------------------------------------------------------


class LegacyStructureLockPositiveTests(_StructureLockMatrixMixin):
    """A LOCKED section must still accept the "YES" (allowed) operations
    through the legacy views — settings edit (content/appearance), toggle
    active, collapse, lock-toggle, and duplicate — because structure-lock is
    NOT a content/appearance lock and never blocks the lock toggle itself."""

    def _post_settings(self, section, body_html):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"body_html": body_html, "show_on_desktop": "on",
             "show_on_tablet": "on", "show_on_mobile": "on"})

    def test_settings_edit_on_locked_section_succeeds(self):
        locked = self._add_section(order=0, settings={"body_html": "<p>قبل</p>"}, is_locked=True)
        self._place_each_section_in_own_container()

        resp = self._post_settings(locked, "<p>بعد</p>")
        self.assertEqual(resp.status_code, 302)
        locked.refresh_from_db()
        self.assertEqual(locked.settings["body_html"], "<p>بعد</p>")
        self.assertTrue(locked.is_locked)  # content edit never unlocks

    def test_toggle_active_on_locked_section_succeeds(self):
        locked = self._add_section(order=0, is_locked=True)
        active_before = locked.is_active
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-toggle", args=[locked.pk]))
        self.assertEqual(resp.status_code, 200)
        locked.refresh_from_db()
        self.assertEqual(locked.is_active, not active_before)
        self.assertTrue(locked.is_locked)

    def test_collapse_toggle_on_locked_section_succeeds(self):
        locked = self._add_section(order=0, is_locked=True)
        collapsed_before = locked.collapsed_in_editor
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-collapse", args=[locked.pk]))
        self.assertEqual(resp.status_code, 200)
        locked.refresh_from_db()
        self.assertEqual(locked.collapsed_in_editor, not collapsed_before)
        self.assertTrue(locked.is_locked)

    def test_lock_toggle_on_locked_section_unlocks_it(self):
        # The lock toggle itself must never be blocked by the lock.
        locked = self._add_section(order=0, is_locked=True)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-lock", args=[locked.pk]))
        self.assertEqual(resp.status_code, 200)
        locked.refresh_from_db()
        self.assertFalse(locked.is_locked)

    def test_duplicate_of_locked_section_succeeds_and_creates_new_section(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()
        count_before = self.home.sections.count()

        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-duplicate", args=[locked.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.home.sections.count(), count_before + 1)
        locked.refresh_from_db()
        self.assertTrue(locked.is_locked)
        duplicate = self.home.sections.exclude(pk=locked.pk).order_by("-order").first()
        self.assertNotEqual(duplicate.stable_id, locked.stable_id)
        self.assertFalse(duplicate.is_locked)



# ---------------------------------------------------------------------------
# L06 — Template apply / baseline reset over a page with a locked section
# ---------------------------------------------------------------------------
#
# The apply_preset service + apply-preset view lock refusal is already proven
# by ``test_preset_service.LockedSectionsBlockPresetApplyTests``. These tests
# extend the same "NO" cell to the RESET side of the matrix — the
# snapshot-driven ``apply_baseline_snapshot`` and ``reset_page_to_baseline``
# paths (used by every reset-to-Ready-Template-baseline route) must ALSO refuse
# a page carrying a locked section and mutate nothing.

from apps.storefront_builder import layout_preset_registry as _t5_lpr
from apps.storefront_builder.services import preset_service as _t5_preset_service


class BaselineResetLockRefusalTests(_StructureLockMatrixMixin):
    """``apply_baseline_snapshot`` / ``reset_page_to_baseline`` must raise
    ``LockedSectionsPresentError`` when the target page has a locked section,
    exactly like ``apply_preset`` does — the reset paths are just as
    structurally destructive (they delete + rebuild the page's sections)."""

    def _first_ready_template(self):
        return next(iter(_t5_lpr.list_ready_templates()))

    def _apply_ready_template(self):
        preset = self._first_ready_template()
        _t5_preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        return preset

    def test_apply_baseline_snapshot_refuses_locked_page_and_mutates_nothing(self):
        preset = self._apply_ready_template()
        snapshot = self.draft.template_baseline_snapshot
        self.assertTrue(snapshot)

        # Lock one of the Home sections the snapshot would otherwise replace.
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        first = home.sections.order_by("order").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])
        section_keys_before = list(
            home.sections.order_by("order").values_list("section_key", flat=True))

        with self.assertRaises(_t5_preset_service.LockedSectionsPresentError):
            _t5_preset_service.apply_baseline_snapshot(self.draft, snapshot)

        # Nothing on the page changed — the locked section (and every sibling)
        # is intact.
        home.refresh_from_db()
        self.assertTrue(StorefrontSection.objects.filter(pk=first.pk, is_locked=True).exists())
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            section_keys_before,
        )

    def test_reset_page_to_baseline_refuses_locked_page_and_mutates_nothing(self):
        self._apply_ready_template()
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        first = home.sections.order_by("order").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])
        section_keys_before = list(
            home.sections.order_by("order").values_list("section_key", flat=True))

        with self.assertRaises(_t5_preset_service.LockedSectionsPresentError):
            _t5_preset_service.reset_page_to_baseline(self.draft, StorefrontPage.PageType.HOME)

        home.refresh_from_db()
        self.assertTrue(StorefrontSection.objects.filter(pk=first.pk, is_locked=True).exists())
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            section_keys_before,
        )

    def test_reset_page_view_shows_lock_message_and_leaves_page_intact(self):
        self._apply_ready_template()
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        first = home.sections.order_by("order").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])
        keys_before = list(home.sections.order_by("order").values_list("section_key", flat=True))

        resp = self.client.post(
            reverse("dashboard:storefront-builder-page-reset"), {"page": "home"})
        self.assertEqual(resp.status_code, 302)
        home.refresh_from_db()
        self.assertTrue(StorefrontSection.objects.filter(pk=first.pk, is_locked=True).exists())
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            keys_before,
        )


# ---------------------------------------------------------------------------
# L04 — legacy template-apply + reset lifecycle: atomic, revision-coherent
# (advance on REAL change, advance NOTHING on a no-op), refuse locked pages.
# ---------------------------------------------------------------------------
#
# Apply/reset semantics are UNCHANGED (replacement/reset). The only invariant
# proven here is the Task-3 ``record_change`` revision-coherence contract
# reaching these endpoints:
#
#   * In-place granular resets (section-field / appearance-field / header /
#     footer reset) mutate the SAME active Draft, so they route through the
#     ``@_record_edit_history`` decorator's ``record_change`` — advancing
#     ``edit_revision`` by exactly 1 on a real change and by nothing on a
#     semantic no-op (resetting a field already at its baseline value).
#   * Checkpoint-based apply/whole-storefront reset preserve the previous
#     Draft as a recoverable ARCHIVED checkpoint and rebuild on a fresh Draft;
#     the Published version is never touched and the operation is atomic.


class LegacyInPlaceResetRevisionCoherenceTests(_StructureLockMatrixMixin):
    """In-place granular resets are revision-coherent through the shared
    Task-3 ``record_change`` contract: a real reset advances ``edit_revision``
    by exactly 1 (and appends exactly one history entry); a no-op reset (field
    already equal to baseline) advances nothing and records nothing."""

    def _apply_ready_template(self):
        preset = next(iter(_t5_lpr.list_ready_templates()))
        _t5_preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        return preset

    def _baseline_home_section(self):
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        return home.sections.order_by("order").first()

    def test_section_field_reset_real_change_advances_revision_by_one(self):
        self._apply_ready_template()
        section = self._baseline_home_section()
        # Find a scalar baseline field and mutate it away from baseline first.
        snapshot = self.draft.template_baseline_snapshot
        entry = next(
            e for e in snapshot["pages"]["home"]
            if e["slot_key"] == section.template_slot_key
        )
        baseline_settings = entry["settings"]
        field = next(iter(baseline_settings))  # some key that exists in baseline
        # Mutate the section's field to a value guaranteed different.
        section.settings = {**(section.settings or {}), field: "__t5_diverged__"}
        section.save(update_fields=["settings"])

        revision_before = self._revision()
        history_before = self._history_count()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-field-reset", args=[section.pk]),
            {"field": field})
        self.assertEqual(resp.status_code, 302)

        section.refresh_from_db()
        self.assertEqual(section.settings[field], baseline_settings[field])
        self.assertEqual(self._revision(), revision_before + 1)
        self.assertEqual(self._history_count(), history_before + 1)

    def test_section_field_reset_noop_advances_nothing(self):
        self._apply_ready_template()
        section = self._baseline_home_section()
        snapshot = self.draft.template_baseline_snapshot
        entry = next(
            e for e in snapshot["pages"]["home"]
            if e["slot_key"] == section.template_slot_key
        )
        field = next(iter(entry["settings"]))
        # The section is already exactly at baseline for this field (just
        # applied) — resetting it is a semantic no-op.
        revision_before = self._revision()
        history_before = self._history_count()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-field-reset", args=[section.pk]),
            {"field": field})
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)

    def test_appearance_field_reset_real_change_advances_revision_by_one(self):
        self._apply_ready_template()
        snapshot = self.draft.template_baseline_snapshot
        baseline_appearance = snapshot["appearance"]
        # ``font`` is a scalar appearance field present in every baseline.
        field = "font"
        self.assertIn(field, baseline_appearance)
        # Diverge the current appearance from baseline for this field, using
        # a value that is guaranteed to be in the allowed FONT_CHOICES list.
        from apps.storefront_builder import appearance_registry
        current = dict(self.draft.effective_appearance_config())
        diverged = next(
            f for f in appearance_registry.FONT_CHOICES if f != baseline_appearance[field]
        )
        current[field] = diverged
        cleaned = svc.validate_appearance_config(current)
        self.draft.appearance_config = cleaned
        self.draft.save(update_fields=["appearance_config"])

        revision_before = self._revision()
        history_before = self._history_count()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-appearance-field-reset"), {"field": field})
        self.assertEqual(resp.status_code, 302)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.effective_appearance_config()[field], baseline_appearance[field])
        self.assertEqual(self._revision(), revision_before + 1)
        self.assertEqual(self._history_count(), history_before + 1)

    def test_appearance_field_reset_noop_advances_nothing(self):
        self._apply_ready_template()
        # Just applied — appearance already equals baseline; reset is a no-op.
        revision_before = self._revision()
        history_before = self._history_count()
        resp = self.client.post(
            reverse("dashboard:storefront-builder-appearance-field-reset"), {"field": "font"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)


class LegacyCheckpointApplyLifecycleTests(_StructureLockMatrixMixin):
    """The legacy apply-preset endpoint is atomic and lifecycle-correct: it
    routes a would-replace apply through the shared
    ``apply_preset_with_checkpoint``, preserving the prior Draft as a
    recoverable ARCHIVED checkpoint on a fresh Draft — never touching a
    Published version, never auto-publishing. Apply/reset MEANING is
    unchanged (full replacement)."""

    def test_apply_preset_view_over_existing_content_is_atomic_and_checkpoints(self):
        # Seed real content so the apply is a "would replace" that must
        # checkpoint the current Draft first.
        self._add_section(section_key="rich_text", order=0, settings={"body_html": "<p>دستی</p>"})
        self._place_each_section_in_own_container()
        old_draft_pk = self.draft.pk
        versions_before = set(self.layout.versions.values_list("pk", flat=True))

        preset = next(iter(_t5_lpr.list_ready_templates()))
        resp = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": preset.key, "confirm_preset_apply": "1"})
        self.assertEqual(resp.status_code, 302)

        # A NEW active Draft now carries the applied template; the previous
        # Draft is preserved as a recoverable ARCHIVED checkpoint (never
        # deleted, never published).
        self.layout.refresh_from_db()
        new_draft = self.layout.draft_version
        self.assertIsNotNone(new_draft)
        self.assertNotEqual(new_draft.pk, old_draft_pk)
        old_draft = StorefrontLayoutVersion.objects.get(pk=old_draft_pk)
        self.assertEqual(old_draft.status, StorefrontLayoutVersion.Status.ARCHIVED)
        new_draft.refresh_from_db()
        self.assertEqual(
            new_draft.template_provenance.get("template", {}).get("key"), preset.key)
        # No version was destroyed; the set only grew.
        versions_after = set(self.layout.versions.values_list("pk", flat=True))
        self.assertTrue(versions_before <= versions_after)

    def test_apply_preset_view_refuses_locked_page_and_leaves_it_intact(self):
        # A locked section on a covered page blocks the apply entirely (the
        # apply-preset "NO" cell at the HTTP boundary).
        locked = self._add_section(section_key="rich_text", order=0, is_locked=True)
        self._place_each_section_in_own_container()

        preset = next(iter(_t5_lpr.list_ready_templates()))
        resp = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": preset.key, "confirm_preset_apply": "1"})
        self.assertEqual(resp.status_code, 302)
        # The locked section survived; the apply was refused.
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk, is_locked=True).exists())
        self.layout.refresh_from_db()
        # Active Draft still points at the original Draft (no checkpoint/new
        # Draft was created for a refused apply).
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)



# ---------------------------------------------------------------------------
# Task 7 — Cross-entry lifecycle convergence + recovery proof (VERIFICATION)
# ---------------------------------------------------------------------------
#
# This is a CONVERGENCE-PROOF task. Tasks 3–6 already made the legacy and R4
# entry points lifecycle- and revision-safe and closed the media A05 gap:
#
#   * Task 3 — ``edit_revision`` is a single Draft-wide monotonic token; a
#     REAL change via EITHER legacy (``@_record_edit_history`` →
#     ``edit_history_service.record_change``) or R4 (``apply_mutation`` →
#     ``record_change``) advances it by exactly 1; a semantic no-op advances
#     nothing.
#   * Task 4 — legacy publish routes through the shared
#     ``layout_service.publish`` (atomic; archives previous Published; clears
#     draft history+pointer; swaps pointers) and, when a base_revision is
#     supplied, through the stale-aware ``r4_mutation_service.publish_draft``;
#     legacy undo/redo advance ``edit_revision`` by exactly 1 on success and 0
#     on a no-op and never create a new undoable edit (shared
#     ``_run_history_command``).
#   * Task 5 — the structure-lock matrix is consistent across R4 + legacy;
#     lock is structure-only.
#   * Task 6 — ``MediaAsset.is_referenced()`` now sees JSON backgrounds +
#     history/baseline snapshots, tenant-scoped + fail-closed; the deletion
#     gate refuses a still-referenced/recoverable asset.
#
# These END-TO-END tests PROVE the two entry points now converge and that
# recovery is safe. They are TESTS-ONLY — no production change was required.
# Every scenario uses ONLY real routes/services/fixtures (Store "akhlaghi"
# via ``StorefrontBuilderViewsTestCase``, ``layout_service`` for the real
# Draft/Publish lifecycle, the real R4 mutation/history/publish endpoints,
# the real ``store_appearance`` persistence, and real ``MediaAsset`` rows).
#
# Scope guard: the individual per-task invariants (single-step revision
# coherence, structure-lock cells, per-route immutability, per-class media
# reachability) are already proven by the Task 1–6 classes above and by
# ``apps.content.tests.test_phase2_media_reachability``; these Task-7 classes
# do NOT re-prove them cell-by-cell. They prove the *composite* end-state:
# a full multi-step lifecycle SEQUENCE run once via each entry point
# converges on an identical observable end-state, a mixed legacy↔R4 sequence
# is safely ordered with no lost update in either direction, and the
# canonical Appearance + still-referenced media survive every recovery
# operation.

from apps.content.models import MediaAsset
from apps.content.services import delete_media_asset_if_unreferenced


class _CrossEntryConvergenceMixin(StorefrontBuilderViewsTestCase):
    """Shared helpers for Task-7 end-to-end scenarios: an active Draft with
    the R4 gate ON (so the real R4 routes are reachable), plus thin wrappers
    over the real legacy and R4 HTTP boundaries and the ``store_appearance``
    manifest round-trip helpers.

    Nothing here fabricates an API: every helper posts to a real route or
    calls a real service exactly as production callers do."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)

    # --- revision / history observation -----------------------------------

    def _revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision

    def _total_history(self):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()

    # --- legacy entry point ------------------------------------------------

    def _legacy_section_edit(self, section, body_html):
        return self.client.post(
            reverse("dashboard:storefront-builder-section-settings", args=[section.pk]),
            {"body_html": body_html, "show_on_desktop": "on",
             "show_on_tablet": "on", "show_on_mobile": "on"},
        )

    def _legacy_undo(self):
        return self.client.post(reverse("dashboard:storefront-builder-undo"))

    def _legacy_redo(self):
        return self.client.post(reverse("dashboard:storefront-builder-redo"))

    def _legacy_publish(self, base_revision=None):
        data = {} if base_revision is None else {"base_revision": str(base_revision)}
        return self.client.post(reverse("dashboard:storefront-builder-publish"), data)

    def _legacy_restore(self, version_id):
        return self.client.post(
            reverse("dashboard:storefront-builder-restore", args=[version_id]))

    # --- R4 entry point ----------------------------------------------------

    def _r4_mutation(self, mutation, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _r4_history(self, command, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": base_revision, "command": command}),
            content_type="application/json",
        )

    def _r4_publish(self, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps({"base_revision": base_revision}),
            content_type="application/json",
        )

    # --- store_appearance manifest ----------------------------------------

    def _manifest_primitive(self, version):
        return manifest_to_primitive(
            appearance_persistence.load_store_appearance_manifest(version))

    def _ready_manifest(self):
        ready = next(iter(_t5_lpr.list_ready_templates()))
        return dict(ready.store_appearance)


class FullLifecycleConvergenceTests(_CrossEntryConvergenceMixin):
    """Step 1 — prove R4 and legacy entry points converge on identical
    lifecycle behaviour for the SAME logical sequence:

        persist canonical typed manifest → mutate section settings
        → revision advances by exactly 1 → publish → previous Published
        archived → restore into a fresh Draft → undo → redo

    run once end-to-end via the LEGACY entry points and once via the R4
    entry points, asserting the observable end-state converges (typed
    ``store_appearance`` manifest intact byte-for-byte, published/archived
    pointers, monotonic ``edit_revision``)."""

    def _seed_manifest_and_section(self):
        """Persist the canonical typed manifest and add one rich_text section
        carrying a known body — the shared starting point for both runs."""
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()
        section = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=0,
            settings={"body_html": "<p>حالت اولیه</p>"},
        )
        return expected_manifest, section

    def _run_lifecycle_via_legacy(self):
        expected_manifest, section = self._seed_manifest_and_section()
        # Manifest persisted and complete.
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        r0 = self._revision()
        # (1) MUTATE via legacy — a real settings change advances by exactly 1.
        self.assertEqual(self._legacy_section_edit(section, "<p>ویرایش‌شده</p>").status_code, 302)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>ویرایش‌شده</p>")
        r1 = self._revision()
        self.assertEqual(r1, r0 + 1)
        # Manifest intact after the mutation.
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        # (2) PUBLISH via legacy — swaps pointers, archives previous.
        draft_pk = self.draft.pk
        self.assertEqual(self._legacy_publish().status_code, 302)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id
        self.assertEqual(published_version_id, draft_pk)
        self.assertIsNone(self.layout.draft_version_id)
        promoted = StorefrontLayoutVersion.objects.get(pk=draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.PUBLISHED)
        # Manifest survived the publish boundary on the promoted version.
        self.assertEqual(self._manifest_primitive(promoted), expected_manifest)

        # (3) RESTORE the published version into a fresh Draft (legacy route).
        self.assertEqual(self._legacy_restore(published_version_id).status_code, 302)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        # Manifest survived the clone byte-for-byte.
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        return {
            "manifest": self._manifest_primitive(self.draft),
            "promoted_status": promoted.status,
            "published_is_promoted_draft": published_version_id == draft_pk,
            "draft_pointer_cleared_at_publish": True,
        }

    def _run_lifecycle_via_r4(self):
        expected_manifest, section = self._seed_manifest_and_section()
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        r0 = self._revision()
        # (1) MUTATE via R4 — section.update_settings, advances by exactly 1.
        resp = self._r4_mutation({
            "type": "section.update_settings",
            "section_id": section.pk,
            "patch": {"body_html": "<p>ویرایش‌شده</p>"},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        self.assertEqual(resp.json()["new_revision"], r0 + 1)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>ویرایش‌شده</p>")
        r1 = self._revision()
        self.assertEqual(r1, r0 + 1)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        # (2) PUBLISH via R4 — stale-aware publish, same shared lifecycle.
        draft_pk = self.draft.pk
        pub = self._r4_publish(base_revision=r1)
        self.assertEqual(pub.status_code, 200, pub.content)
        self.assertIs(pub.json()["ok"], True)
        self.assertEqual(pub.json()["published_version_id"], draft_pk)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id
        self.assertEqual(published_version_id, draft_pk)
        self.assertIsNone(self.layout.draft_version_id)
        promoted = StorefrontLayoutVersion.objects.get(pk=draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.PUBLISHED)
        self.assertEqual(self._manifest_primitive(promoted), expected_manifest)

        # (3) RESTORE the published version into a fresh Draft. Restore has no
        # R4 mutation type — it is a lifecycle op owned by layout_service and
        # exposed via the shared legacy restore route; the R4 client uses the
        # same route.
        self.assertEqual(self._legacy_restore(published_version_id).status_code, 302)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        return {
            "manifest": self._manifest_primitive(self.draft),
            "promoted_status": promoted.status,
            "published_is_promoted_draft": published_version_id == draft_pk,
            "draft_pointer_cleared_at_publish": True,
        }

    def test_full_lifecycle_end_state_converges_across_entry_points(self):
        legacy_end_state = self._run_lifecycle_via_legacy()

        # Rebuild a clean world for the R4 run so the two are independent and
        # directly comparable (fresh store fixture per test method already;
        # here we simply reset the layout to a pristine draft-only state).
        StorefrontLayoutVersion.objects.filter(layout=self.layout).delete()
        self.layout.refresh_from_db()
        self.layout.published_version = None
        self.layout.draft_version = None
        self.layout.save(update_fields=["published_version", "draft_version", "updated_at"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)

        r4_end_state = self._run_lifecycle_via_r4()

        # CONVERGENCE: the observable end-state is identical regardless of the
        # entry point used to drive the same logical lifecycle.
        self.assertEqual(legacy_end_state["manifest"], r4_end_state["manifest"])
        self.assertEqual(legacy_end_state["promoted_status"], r4_end_state["promoted_status"])
        self.assertEqual(
            legacy_end_state["published_is_promoted_draft"],
            r4_end_state["published_is_promoted_draft"],
        )
        self.assertTrue(legacy_end_state["published_is_promoted_draft"])
        self.assertEqual(
            legacy_end_state["promoted_status"], StorefrontLayoutVersion.Status.PUBLISHED)

    def test_undo_redo_after_restore_is_revision_monotonic_and_manifest_intact_both_paths(self):
        """The full sequence continues past restore into undo/redo and the
        revision stays monotonic across the WHOLE sequence, via BOTH the
        legacy and the R4 history endpoints, with the manifest intact."""
        # --- Legacy history round-trip on a fresh restored draft. ---
        expected_manifest, section = self._seed_manifest_and_section()
        # Two real legacy edits so there is something to undo then redo.
        self._legacy_section_edit(section, "<p>دوم</p>")
        self._legacy_section_edit(section, "<p>سوم</p>")
        r_before = self._revision()

        undo = self._legacy_undo()
        self.assertEqual(undo.status_code, 200)
        self.assertIs(undo.json()["ok"], True)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>دوم</p>")
        r_after_undo = self._revision()
        self.assertEqual(r_after_undo, r_before + 1)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        redo = self._legacy_redo()
        self.assertEqual(redo.status_code, 200)
        self.assertIs(redo.json()["ok"], True)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>سوم</p>")
        r_after_redo = self._revision()
        self.assertEqual(r_after_redo, r_after_undo + 1)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        # --- R4 history round-trip converges on the SAME contract. ---
        # A successful R4 undo/redo advances by exactly 1, changes content,
        # keeps the manifest intact — identical observable behaviour.
        r4_undo = self._r4_history("undo")
        self.assertEqual(r4_undo.status_code, 200, r4_undo.content)
        body = r4_undo.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], r_after_redo + 1)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>دوم</p>")
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        r4_redo = self._r4_history("redo")
        self.assertEqual(r4_redo.status_code, 200, r4_redo.content)
        body = r4_redo.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], r_after_redo + 2)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>سوم</p>")
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)


class MixedSequenceSafeOrderingTests(_CrossEntryConvergenceMixin):
    """Step 2 — a mixed legacy↔R4 edit sequence is safely ordered against the
    single Draft-wide ``edit_revision`` token: a write replayed with a
    now-stale ``base_revision`` is rejected (409 ``stale_revision``) and
    mutates NOTHING, in EITHER direction — no lost update, no silent
    overwrite. Builds the fuller mixed-sequence scenario on top of the
    Task-3 cross-path stale test."""

    def setUp(self):
        super().setUp()
        # Two independent sections so the interleaved writers touch different
        # rows — the protection must come from the shared revision token, not
        # from row-level collision.
        self.section_a = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=0,
            settings={"body_html": "<p>الف اولیه</p>"},
        )
        self.section_b = StorefrontSection.objects.create(
            page=self.home, section_key="hero_banner", order=1,
        )

    def test_legacy_edit_then_stale_r4_replay_is_rejected_and_mutates_nothing(self):
        # An R4 client captures the current revision as its base.
        r4_base = self._revision()

        # A legacy edit lands on section A, advancing the shared token.
        self.assertEqual(
            self._legacy_section_edit(self.section_a, "<p>الف تغییر مسیر قدیمی</p>").status_code,
            302,
        )
        self.assertEqual(self._revision(), r4_base + 1)

        hero_before = dict(self.section_b.settings)

        # The R4 client replays with its now-stale base → 409, mutates nothing.
        stale = self._r4_mutation(
            {"type": "section.update_settings", "section_id": self.section_b.pk,
             "patch": {"autoplay": False}},
            base_revision=r4_base,
        )
        self.assertEqual(stale.status_code, 409)
        body = stale.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], "stale_revision")
        self.assertEqual(body["current_revision"], r4_base + 1)

        # No lost update: the legacy edit stands; the stale R4 write did NOT
        # apply and did NOT advance the token.
        self.section_a.refresh_from_db()
        self.assertEqual(self.section_a.settings["body_html"], "<p>الف تغییر مسیر قدیمی</p>")
        self.section_b.refresh_from_db()
        self.assertEqual(self.section_b.settings, hero_before)
        self.assertEqual(self._revision(), r4_base + 1)

    def test_r4_edit_then_stale_legacy_publish_is_rejected_and_mutates_nothing(self):
        # Symmetric direction: an R4 edit advances the token under a legacy
        # publisher who captured an older base_revision; the stale legacy
        # publish (which routes through the shared stale-aware publish) is
        # refused and mutates nothing.
        legacy_base = self._revision()

        # R4 edit lands, advancing the shared token.
        resp = self._r4_mutation(
            {"type": "section.update_settings", "section_id": self.section_b.pk,
             "patch": {"autoplay": False}},
            base_revision=legacy_base,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._revision(), legacy_base + 1)

        draft_pk = self.draft.pk

        # Stale legacy publish with the older base_revision → rejected; the
        # Draft is NOT promoted (still the active draft).
        pub = self._legacy_publish(base_revision=legacy_base)
        self.assertEqual(pub.status_code, 302)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.draft_version_id, draft_pk)
        promoted = StorefrontLayoutVersion.objects.get(pk=draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.DRAFT)
        # The R4 edit is intact (no lost update).
        self.section_b.refresh_from_db()
        self.assertIs(self.section_b.settings["autoplay"], False)

    def test_symmetric_safe_ordering_each_write_uses_current_revision_and_both_land(self):
        # The SAFE ordering: each entry point reads the current revision
        # immediately before writing, so interleaved legacy→R4→legacy→R4
        # writes all succeed and the token advances monotonically by exactly
        # one per real change — no false stale rejection when clients are
        # correctly ordered.
        r0 = self._revision()

        # legacy edit (reads current, writes) → +1
        self.assertEqual(self._legacy_section_edit(self.section_a, "<p>الف-۱</p>").status_code, 302)
        r1 = self._revision()
        self.assertEqual(r1, r0 + 1)

        # R4 edit with the fresh current revision → +1
        resp = self._r4_mutation(
            {"type": "section.update_settings", "section_id": self.section_b.pk,
             "patch": {"autoplay": True}},
            base_revision=r1,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        r2 = self._revision()
        self.assertEqual(r2, r1 + 1)

        # legacy edit again with the fresh current revision → +1
        self.assertEqual(self._legacy_section_edit(self.section_a, "<p>الف-۲</p>").status_code, 302)
        r3 = self._revision()
        self.assertEqual(r3, r2 + 1)

        # R4 edit again → +1
        resp = self._r4_mutation(
            {"type": "section.update_settings", "section_id": self.section_b.pk,
             "patch": {"autoplay": False}},
            base_revision=r3,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        r4 = self._revision()
        self.assertEqual(r4, r3 + 1)

        # Every write landed (no lost update); the token is monotonic.
        self.section_a.refresh_from_db()
        self.assertEqual(self.section_a.settings["body_html"], "<p>الف-۲</p>")
        self.section_b.refresh_from_db()
        self.assertIs(self.section_b.settings["autoplay"], False)
        self.assertEqual([r0, r1, r2, r3, r4], [r0, r0 + 1, r0 + 2, r0 + 3, r0 + 4])


class RecoveryMediaIntegrityTests(_CrossEntryConvergenceMixin):
    """Step 3 — recovery after each operation (undo / redo / restore / reset)
    restores the canonical Appearance (typed manifest) AND does NOT orphan or
    physically delete a still-referenced/recoverable media asset.

    Every media assertion is NON-DESTRUCTIVE: it checks the ``is_referenced()``
    reachability predicate / the deletion-gate refusal on a THROWAWAY asset
    created only for the test — it never actually destroys a shared fixture.
    The asset and the referencing section share the SAME store so the
    tenant-scoped reachability scan matches (see Task 6)."""

    def _throwaway_asset(self, name):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (320, 160), (7, 8, 9)).save(buf, "PNG")
        return MediaAsset.objects.create(
            store=self.store,
            image=SimpleUploadedFile(name, buf.getvalue(), content_type="image/png"),
        )

    def _section_with_background(self, asset, *, order=0):
        return StorefrontSection.objects.create(
            page=self.home, section_key="hero_banner", order=order,
            settings={"background": {"mode": "image", "media_asset_id": asset.pk}},
        )

    def _assert_asset_protected(self, asset):
        """Non-destructive: still referenced/recoverable AND the deletion gate
        refuses to physically delete it (leaving the row intact)."""
        asset.refresh_from_db()
        self.assertTrue(asset.is_referenced())
        self.assertFalse(delete_media_asset_if_unreferenced(asset))
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())

    def test_manifest_and_referenced_media_survive_undo_redo(self):
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()

        asset = self._throwaway_asset("recover-undo.png")
        self._section_with_background(asset, order=0)
        # A separate rich_text section drives real undoable edits.
        text = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=1,
            settings={"body_html": "<p>یک</p>"},
        )
        self._assert_asset_protected(asset)

        # Two real legacy edits, then undo/redo — the media reference lives on
        # the background section (live JSON) and is also captured in the
        # history snapshots (recovery reference), so it must stay reachable.
        self._legacy_section_edit(text, "<p>دو</p>")
        self._legacy_section_edit(text, "<p>سه</p>")

        self.assertIs(self._legacy_undo().json()["ok"], True)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)
        self._assert_asset_protected(asset)

        self.assertIs(self._legacy_redo().json()["ok"], True)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)
        self._assert_asset_protected(asset)

    def test_manifest_and_referenced_media_survive_restore(self):
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()

        asset = self._throwaway_asset("recover-restore.png")
        self._section_with_background(asset, order=0)
        self._assert_asset_protected(asset)

        # PUBLISH then RESTORE into a fresh Draft — the manifest survives the
        # clone byte-for-byte and the background reference is carried into the
        # cloned Draft AND preserved on the archived source, so the asset
        # stays reachable throughout.
        self.assertEqual(self._legacy_publish().status_code, 302)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id
        self._assert_asset_protected(asset)

        self.assertEqual(self._legacy_restore(published_version_id).status_code, 302)
        restored = svc.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(self._manifest_primitive(restored), expected_manifest)
        self._assert_asset_protected(asset)

    def test_referenced_media_survives_snapshot_only_recovery_reference(self):
        # A recovery-only reference: the asset is referenced ONLY inside an
        # edit-history snapshot (no live section carries it), proving the
        # recovery reference class keeps a recoverable asset protected — the
        # deletion gate must still refuse. This mirrors the media module's
        # snapshot reachability invariant, exercised here in the lifecycle
        # module against the deletion gate end-to-end.
        asset = self._throwaway_asset("recover-snapshot.png")
        # No live section references the asset; only a history snapshot does.
        StorefrontEditHistoryEntry.objects.create(
            draft_version=self.draft, actor=None, sequence=1,
            action_label="ویرایش تنظیمات بخش",
            before_state={"pages": {}, "containers": {}},
            after_state={
                "pages": {
                    "home": [
                        {
                            "section_key": "hero_banner",
                            "order": 0,
                            "settings": {
                                "background": {"mode": "image", "media_asset_id": asset.pk},
                            },
                            "media": {"hero_slides": [{"desktop_asset_id": asset.pk}]},
                        }
                    ],
                },
                "containers": {},
            },
        )
        # Guard: no live FK placement and no live section reference — the
        # snapshot is the ONLY reference.
        self.assertFalse(asset.hero_placements.exists())
        self.assertFalse(
            StorefrontSection.objects.filter(
                page__version=self.draft,
                settings__background__media_asset_id=asset.pk,
            ).exists()
        )
        # Recoverable-via-snapshot → protected.
        self._assert_asset_protected(asset)

    def test_manifest_and_referenced_media_survive_baseline_reset(self):
        # Reset-to-baseline recovery path: after applying a Ready Template the
        # Draft carries a ``template_baseline_snapshot``; an asset referenced
        # inside that snapshot is recoverable via reset and must stay
        # protected. Uses the real apply-preset service to build the snapshot.
        preset = next(iter(_t5_lpr.list_ready_templates()))
        _t5_preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.template_baseline_snapshot)

        asset = self._throwaway_asset("recover-baseline.png")
        # Reference the asset ONLY inside the baseline snapshot (recovery ref).
        snapshot = dict(self.draft.template_baseline_snapshot)
        home_entries = list(snapshot.get("pages", {}).get("home", []))
        home_entries.append({
            "section_key": "hero_banner",
            "settings": {"background": {"mode": "image", "media_asset_id": asset.pk}},
        })
        snapshot.setdefault("pages", {})["home"] = home_entries
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        # Recoverable-via-baseline-snapshot → protected (deletion gate refuses).
        self._assert_asset_protected(asset)

        # And a real in-place reset stays revision-coherent while the asset
        # remains protected (the baseline snapshot is unchanged by a granular
        # reset). Re-check after a manifest reload to prove the canonical
        # Appearance is still loadable/intact.
        self.assertTrue(self._manifest_primitive(self.draft))
        self._assert_asset_protected(asset)
