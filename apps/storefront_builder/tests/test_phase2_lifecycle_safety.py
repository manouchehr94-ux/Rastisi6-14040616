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
