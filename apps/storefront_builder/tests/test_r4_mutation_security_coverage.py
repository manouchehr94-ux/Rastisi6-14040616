"""R4 mutation security coverage — EVERY operation of ``r4_mutation_service._dispatch_mutation``.

The dispatcher is the one allowlist of write operations. This module derives the set of operation types from the
dispatcher's own source and requires a protection test row for each (adding an operation without a row fails
``test_the_protection_table_covers_exactly_the_dispatcher``). For every operation it proves, against the real HTTP
route:

  * stale revision          → 409, nothing changes (no revision advance, no history entry)
  * no active Draft         → rejected, a Draft is never created implicitly, Published untouched
  * accepted on own Draft   → the Published version (configs, composition, fingerprint) is untouched
  * another Store's client  → can never change THIS Store's Draft or Published version
  * anonymous / non-member  → can never change anything

and, for the operations that carry an explicit target (section / container / cell ids, or a pinned ``draft_id``), that a
Published, Archived, foreign or non-existent target is rejected with nothing changed.
"""

import inspect
import json
import re

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import (
    container_service, layout_service as svc, preset_service, r4_mutation_service,
)
from apps.storefront_builder.storefront_appearance.persistence import load_store_appearance_manifest
from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive
from apps.stores.models import Store, StoreMembership

from .test_r4_mutation_api import R4MutationApiTestCase

_User = get_user_model()

#: operations that carry an explicit section / container / cell target (rejected for any non-Draft or foreign id)
ID_TARGETED = frozenset({
    "section.update_settings", "section.remove", "section.duplicate", "section.move", "section.toggle_active",
    "section.toggle_locked", "section.reset_to_baseline", "section.reset_setting_to_baseline",
    "container.change_layout", "container.update_settings", "cell.add_section", "section.move_to_cell",
})
#: operations pinned to one Draft by an explicit ``draft_id`` (rejected for a Published / Archived / foreign / unknown id)
DRAFT_PINNED = frozenset({
    "appearance.component.update", "appearance.manifest.apply", "appearance.template.apply", "theme.apply",
    "theme.clear", "design_lab.apply_candidate",
})


def _dispatched_types():
    source = inspect.getsource(r4_mutation_service._dispatch_mutation)
    return set(re.findall(r'mutation_type == "([a-z_.]+)"', source))


class R4MutationSecurityCoverageTests(R4MutationApiTestCase):
    FOREIGN_HOST = "sfb-seccov-foreign.rastisi.localhost"

    def setUp(self):
        super().setUp()
        # a Ready Template baseline (so the "reset to baseline" operations are real), then a published release + an
        # archived one, so the Draft has real lifecycle neighbours
        self.template = next(iter(lpr.list_ready_templates()))
        preset_service.apply_preset(self.draft, self.template)
        self.published = svc.publish(self.store, user=self.staff)
        self.archived = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=990, status=StorefrontLayoutVersion.Status.ARCHIVED,
        )
        StorefrontPage.ensure_version_pages(self.archived)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.layout.refresh_from_db()
        self.victim, self.victim_container, self.victim_cell = self._rows(self.draft)
        # a section that came from the Ready Template (it has a baseline to reset to)
        self.reset_target = StorefrontSection.objects.filter(page__version=self.draft, section_key="product_section").first()
        assert self.reset_target is not None

        self.foreign_store = Store.objects.create(
            name="فروشگاه بیگانه پوشش", slug="sfb-seccov-foreign",
            admin_subdomain=self.FOREIGN_HOST.split(".")[0], status=Store.Status.ACTIVE,
        )
        self.foreign_user = _User.objects.create_user(username="sfb_seccov_foreign", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.foreign_store, user=self.foreign_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.foreign_draft = svc.get_or_create_draft(self.foreign_store, user=self.foreign_user)
        self.foreign_client = Client(HTTP_HOST=self.FOREIGN_HOST)
        self.foreign_client.login(username="sfb_seccov_foreign", password="pass12345")

    # ------------------------------------------------------------------------------------------------------ helpers
    def _rows(self, version):
        home = version.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=50, settings={"body_html": "<p>اصلی</p>"},
        )
        container = container_service.create_empty_container(home, "half")
        occupied, empty = list(container.cells.order_by("order", "id")[:2])
        container_service.place_section(occupied, section)  # a placed section: the Draft stays composition-stable
        return section, container, empty

    def _post(self, client, mutation, base_revision):
        return client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _state(self, version):
        version.refresh_from_db()
        return {
            "revision": version.edit_revision,
            "header": version.header_config, "footer": version.footer_config, "appearance": version.appearance_config,
            "sections": sorted(
                (s.pk, s.section_key, json.dumps(s.settings, sort_keys=True), s.is_active, s.is_locked, s.order)
                for s in StorefrontSection.objects.filter(page__version=version)
            ),
            "containers": sorted(
                (c.pk, c.layout_key, json.dumps(c.settings, sort_keys=True))
                for c in StorefrontContainer.objects.filter(page__version=version)
            ),
            "cells": sorted(
                (c.pk, c.section_id) for c in StorefrontCell.objects.filter(container__page__version=version)
            ),
            "history": StorefrontEditHistoryEntry.objects.filter(draft_version=version).count(),
        }

    def _published_state(self):
        state = self._state(self.published)
        state["fingerprint"] = (self.published.content_fingerprint, self.published.compute_fingerprint())
        self.assertEqual(state["fingerprint"][0], state["fingerprint"][1], "fingerprint must equal the composition")
        return state

    # --------------------------------------------------- one valid command shape per operation (own Draft)
    def _lab_candidate(self):
        self.draft.refresh_from_db()
        mix = self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps({"action": "random_mix", "locked_families": []}), content_type="application/json",
        )
        token = mix.json()["token"]
        apply = self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps({"action": "apply_payload", "candidate_token": token}), content_type="application/json",
        )
        return apply.json()["mutation"]

    def _manifest_with_motion_none(self):
        manifest = manifest_to_primitive(load_store_appearance_manifest(self.draft))
        manifest["selections"]["motion"] = "motion.none.v1"
        return manifest

    def _payloads(self):
        d, s, c, cell = self.draft, self.victim, self.victim_container, self.victim_cell
        template = self.template
        return {
            "section.update_settings": lambda: {"type": "section.update_settings", "section_id": s.pk,
                                                "patch": {"body_html": "<p>تازه</p>"}},
            "section.add": lambda: {"type": "section.add", "section_key": "faq", "page_type": "home"},
            "section.remove": lambda: {"type": "section.remove", "section_id": s.pk},
            "section.duplicate": lambda: {"type": "section.duplicate", "section_id": s.pk},
            "section.move": lambda: {"type": "section.move", "section_id": s.pk, "direction": "up"},
            "section.toggle_active": lambda: {"type": "section.toggle_active", "section_id": s.pk},
            "section.toggle_locked": lambda: {"type": "section.toggle_locked", "section_id": s.pk},
            "container.change_layout": lambda: {"type": "container.change_layout", "container_id": c.pk,
                                                "layout_key": "single"},
            # V5-LAYOUT-ATOMIC: one new Container (existing preset) with a pre-filled and an empty Cell; no foreign id involved
            "container.add": lambda: {"type": "container.add", "page_type": "home", "layout_key": "half", "cells": [["faq"], []]},
            "container.remove": lambda: {"type": "container.remove", "container_id": c.pk},
            "cell.add_section": lambda: {"type": "cell.add_section", "section_key": "faq", "cell_id": cell.pk},
            "section.move_to_cell": lambda: {"type": "section.move_to_cell", "section_id": s.pk, "cell_id": cell.pk},
            "container.update_settings": lambda: {"type": "container.update_settings", "container_id": c.pk,
                                                  "patch": {"gap": 20}},
            "section.reset_to_baseline": lambda: {"type": "section.reset_to_baseline",
                                                  "section_id": self.reset_target.pk},
            "section.reset_setting_to_baseline": lambda: {"type": "section.reset_setting_to_baseline",
                                                          "section_id": self.reset_target.pk, "key": "title"},
            "appearance.reset_setting_to_baseline": lambda: {"type": "appearance.reset_setting_to_baseline",
                                                             "key": "density"},
            "header.reset_to_baseline": lambda: {"type": "header.reset_to_baseline"},
            "footer.reset_to_baseline": lambda: {"type": "footer.reset_to_baseline"},
            "appearance.update": lambda: {"type": "appearance.update", "patch": {"motion": "none"}},
            "header.update": lambda: {"type": "header.update", "patch": {"header_variant": "dark_tech"}},
            "footer.update": lambda: {"type": "footer.update", "patch": {"footer_variant": "premium_columns"}},
            "appearance.component.update": lambda: {"type": "appearance.component.update", "draft_id": d.pk,
                                                    "family": "header", "component_key": "header.dark_tech.v1"},
            "appearance.manifest.apply": lambda: {"type": "appearance.manifest.apply", "draft_id": d.pk,
                                                  "manifest": self._manifest_with_motion_none()},
            "appearance.template.apply": lambda: {"type": "appearance.template.apply", "draft_id": d.pk,
                                                  "template_key": template.key, "template_version": template.version,
                                                  # exact replacement is destructive: the server requires the explicit
                                                  # confirmation, and the fixture Draft carries a locked section
                                                  "confirm_replace": True, "allow_locked": True},
            "theme.apply": lambda: {"type": "theme.apply", "draft_id": d.pk, "component_key": "theme.yalda.v1",
                                    "intensity": "balanced"},
            "theme.clear": lambda: {"type": "theme.clear", "draft_id": d.pk},
            "design_lab.apply_candidate": self._lab_candidate,
        }

    # ------------------------------------------------------------------------------------------------- completeness
    def test_the_protection_table_covers_exactly_the_dispatcher(self):
        self.assertEqual(set(self._payloads()), _dispatched_types())
        self.assertEqual(len(_dispatched_types()), 27)
        self.assertTrue(ID_TARGETED <= set(self._payloads()))
        self.assertTrue(DRAFT_PINNED <= set(self._payloads()))

    def test_every_operation_has_a_working_command_shape_on_the_callers_own_draft(self):
        """Control: the matrix is not vacuous — each shape is accepted (200) by the Draft it will later be refused for."""
        for name, factory in self._payloads().items():
            with self.subTest(mutation=name):
                self.victim, self.victim_container, self.victim_cell = self._rows(self.draft)
                mutation = self._payloads()[name]()
                self.draft.refresh_from_db()
                response = self._post(self.client, mutation, self.draft.edit_revision)
                self.assertEqual(response.status_code, 200, f"{name}: {response.content[:300]!r}")

    # ---------------------------------------------------------------------------------------------- lifecycle matrix
    def test_stale_revision_is_rejected_for_every_operation_and_nothing_changes(self):
        before, published = self._state(self.draft), self._published_state()
        for name in self._payloads():
            with self.subTest(mutation=name):
                mutation = self._payloads()[name]()
                self.draft.refresh_from_db()
                response = self._post(self.client, mutation, self.draft.edit_revision + 7)
                self.assertEqual(response.status_code, 409, f"{name}: {response.content[:200]!r}")
                self.assertEqual(response.json().get("code"), "stale_revision")
                self.assertEqual(self._state(self.draft), before)
                self.assertEqual(self._published_state(), published)

    def test_without_an_active_draft_every_operation_is_rejected_and_no_draft_is_created(self):
        payloads = {name: factory() for name, factory in self._payloads().items()}
        revision = self.draft.edit_revision
        svc.discard_draft(self.store)
        published = self._published_state()
        versions = StorefrontLayoutVersion.objects.filter(layout=self.layout).count()
        for name, mutation in payloads.items():
            with self.subTest(mutation=name):
                response = self._post(self.client, mutation, revision)
                self.assertIn(response.status_code, (400, 404, 409), f"{name}: {response.content[:200]!r}")
                self.assertIs(response.json().get("ok"), False)
                self.layout.refresh_from_db()
                self.assertIsNone(self.layout.draft_version_id, "a mutation must never create a Draft implicitly")
                self.assertEqual(StorefrontLayoutVersion.objects.filter(layout=self.layout).count(), versions)
                self.assertEqual(self._published_state(), published)

    def test_an_accepted_operation_changes_only_the_draft_never_the_published_version(self):
        published = self._published_state()
        archived = self._state(self.archived)
        for name in self._payloads():
            with self.subTest(mutation=name):
                self.victim, self.victim_container, self.victim_cell = self._rows(self.draft)
                mutation = self._payloads()[name]()
                self.draft.refresh_from_db()
                response = self._post(self.client, mutation, self.draft.edit_revision)
                self.assertEqual(response.status_code, 200, f"{name}: {response.content[:200]!r}")
                self.assertEqual(self._published_state(), published, f"{name} leaked into the Published version")
                self.assertEqual(self._state(self.archived), archived, f"{name} leaked into the Archived version")

    def test_another_stores_client_can_never_change_this_stores_draft_or_published_version(self):
        draft_before, published = self._state(self.draft), self._published_state()
        for name in self._payloads():
            with self.subTest(mutation=name):
                mutation = self._payloads()[name]()
                self.foreign_draft.refresh_from_db()
                response = self._post(self.foreign_client, mutation, self.foreign_draft.edit_revision)
                if name in ID_TARGETED | DRAFT_PINNED:
                    self.assertIs(response.json().get("ok"), False, f"{name}: {response.content[:200]!r}")
                    self.assertIn(response.status_code, (400, 404))
                self.assertEqual(self._state(self.draft), draft_before)
                self.assertEqual(self._published_state(), published)

    def test_anonymous_and_non_member_requests_change_nothing(self):
        draft_before, published = self._state(self.draft), self._published_state()
        anonymous = Client(HTTP_HOST=self.client.defaults.get("HTTP_HOST", ""))
        outsider = Client(HTTP_HOST=self.client.defaults.get("HTTP_HOST", ""))
        outsider.login(username="sfb_seccov_foreign", password="pass12345")  # a real user, but not a member of THIS store
        for label, client in (("anonymous", anonymous), ("non-member", outsider)):
            for name in self._payloads():
                with self.subTest(client=label, mutation=name):
                    mutation = self._payloads()[name]()
                    self.draft.refresh_from_db()
                    response = self._post(client, mutation, self.draft.edit_revision)
                    self.assertNotEqual(response.status_code, 200, f"{label}/{name}")
                    self.assertEqual(self._state(self.draft), draft_before)
                    self.assertEqual(self._published_state(), published)

    # ------------------------------------------------------------------------------------------ explicit-target matrix
    def test_draft_pinned_operations_reject_a_published_archived_foreign_or_unknown_draft_id(self):
        foreign_id = self.foreign_draft.pk
        for label, bad_id in (("published", self.published.pk), ("archived", self.archived.pk),
                              ("foreign_draft", foreign_id), ("unknown", 9_999_999)):
            for name in sorted(DRAFT_PINNED):
                with self.subTest(target=label, mutation=name):
                    mutation = dict(self._payloads()[name]())
                    mutation["draft_id"] = bad_id
                    if name == "design_lab.apply_candidate":
                        self.assertIn("candidate_token", mutation)
                    before, published = self._state(self.draft), self._published_state()
                    response = self._post(self.client, mutation, self.draft.edit_revision)
                    self.assertEqual(response.status_code, 400, f"{name}: {response.content[:200]!r}")
                    self.assertIs(response.json().get("ok"), False)
                    self.assertEqual(response.json().get("code"), "draft_not_found", "must be refused for its SCOPE")
                    self.assertEqual(self._state(self.draft), before)
                    self.assertEqual(self._published_state(), published)

    def test_every_id_targeted_operation_is_rejected_for_published_archived_and_foreign_rows(self):
        targets = {
            "published": self._rows(self.published),
            "archived": self._rows(self.archived),
            "foreign_draft": self._rows(self.foreign_draft),
        }
        self.published.refresh_from_db()
        # the rows above are added on purpose AFTER publication to attack immutability; re-baseline the fingerprint check
        for label, (section, container, cell) in targets.items():
            for name in sorted(ID_TARGETED):
                with self.subTest(target=label, mutation=name):
                    self.victim, self.victim_container, self.victim_cell = section, container, cell
                    self.reset_target = section
                    mutation = self._payloads()[name]()
                    before = self._state(self.draft)
                    snapshot = self._state(section.page.version)
                    self.draft.refresh_from_db()
                    response = self._post(self.client, mutation, self.draft.edit_revision)
                    self.assertIn(response.status_code, (400, 404), f"{name}: {response.content[:200]!r}")
                    self.assertIs(response.json().get("ok"), False)
                    self.assertIn(
                        response.json().get("code"), {"section_not_found", "container_not_found", "cell_not_found"},
                        f"{name} on {label} must be refused for its SCOPE, not for an unrelated validation error",
                    )
                    self.assertEqual(self._state(self.draft), before)
                    self.assertEqual(self._state(section.page.version), snapshot, f"{label} target was mutated")
