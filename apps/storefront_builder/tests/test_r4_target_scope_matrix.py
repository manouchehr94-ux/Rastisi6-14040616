"""R4 mutation target-scope matrix — the canonical engine's tenant / lifecycle protection.

The retired R3 editor had one test class per legacy route proving it rejected a Published, an Archived or a foreign
Store's section / container / cell (and mutated nothing). The R4 mutation route is now the ONLY write surface, so the same
guarantees are pinned here once, as a matrix over every R4 mutation type:

  target version (Published / Archived / another Store's Draft)  ×  mutation type  →  rejected, nothing changes, the
  caller's own Draft revision does not advance and no history entry is written.
"""

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import container_service, layout_service as svc
from apps.stores.models import Store, StoreMembership

from .test_r4_mutation_api import R4MutationApiTestCase

_User = get_user_model()


class R4TargetScopeMatrixTests(R4MutationApiTestCase):
    FOREIGN_HOST = "sfb-matrix-foreign.rastisi.localhost"

    def setUp(self):
        super().setUp()
        self.published = self._version(StorefrontLayoutVersion.Status.PUBLISHED, 970)
        self.archived = self._version(StorefrontLayoutVersion.Status.ARCHIVED, 969)
        self.layout.refresh_from_db()
        self.layout.published_version = self.published
        self.layout.save(update_fields=["published_version", "updated_at"])

        foreign_store = Store.objects.create(
            name="فروشگاه بیگانه ماتریس", slug="sfb-matrix-foreign",
            admin_subdomain=self.FOREIGN_HOST.split(".")[0], status=Store.Status.ACTIVE,
        )
        foreign_user = _User.objects.create_user(username="sfb_matrix_foreign", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=foreign_store, user=foreign_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        foreign_draft = svc.get_or_create_draft(foreign_store, user=foreign_user)

        self.targets = {
            "published": self._seed(self.published),
            "archived": self._seed(self.archived),
            "foreign_draft": self._seed(foreign_draft),
        }
        # an own, mutable section/container/cell so that "moves" have a legitimate counterpart
        self.own_section, self.own_container, self.own_cell = self._seed(self.draft)

    def _version(self, status, number):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=number, status=status)
        StorefrontPage.ensure_version_pages(version)
        return version

    def _seed(self, version):
        home = version.get_page(StorefrontPage.PageType.HOME)
        section = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0, settings={"body_html": "<p>اصلی</p>"},
        )
        container = container_service.create_empty_container(home, "half")
        cell = container.cells.order_by("order", "id").first()
        return section, container, cell

    def _mutations(self, section, container, cell):
        return {
            "section.update_settings": {"type": "section.update_settings", "section_id": section.pk,
                                        "patch": {"body_html": "<p>هک</p>"}},
            "section.remove": {"type": "section.remove", "section_id": section.pk},
            "section.duplicate": {"type": "section.duplicate", "section_id": section.pk},
            "section.move": {"type": "section.move", "section_id": section.pk, "direction": "down"},
            "section.toggle_active": {"type": "section.toggle_active", "section_id": section.pk},
            "section.toggle_locked": {"type": "section.toggle_locked", "section_id": section.pk},
            "section.reset_to_baseline": {"type": "section.reset_to_baseline", "section_id": section.pk},
            "container.change_layout": {"type": "container.change_layout", "container_id": container.pk,
                                        "layout_key": "single"},
            "container.update_settings": {"type": "container.update_settings", "container_id": container.pk,
                                         "patch": {"min_height": 400}},
            "cell.add_section": {"type": "cell.add_section", "section_key": "faq", "cell_id": cell.pk},
            "section.move_to_cell": {"type": "section.move_to_cell", "section_id": self.own_section.pk,
                                     "cell_id": cell.pk},
        }

    def _snapshot(self, section, container, cell):
        section.refresh_from_db()
        container.refresh_from_db()
        cell.refresh_from_db()
        return (
            section.settings, section.is_active, section.is_locked, section.order, section.page_id,
            container.layout_key, container.settings, container.cells.count(),
            cell.section_id, StorefrontSection.objects.filter(page=section.page).count(),
        )

    def test_every_mutation_type_is_rejected_on_every_foreign_or_non_draft_target(self):
        own_snapshot = self._snapshot(self.own_section, self.own_container, self.own_cell)
        revision = self.draft.edit_revision
        history = StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()
        for label, (section, container, cell) in self.targets.items():
            before = self._snapshot(section, container, cell)
            for name, mutation in self._mutations(section, container, cell).items():
                with self.subTest(target=label, mutation=name):
                    response = self._post_json({"base_revision": revision, "mutation": mutation})
                    self.assertIn(response.status_code, (400, 404), response.content[:200])
                    self.assertIs(response.json().get("ok"), False)
                    self.draft.refresh_from_db()
                    self.assertEqual(self.draft.edit_revision, revision)
                    self.assertEqual(
                        StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count(), history,
                    )
            self.assertEqual(self._snapshot(section, container, cell), before, f"{label} target was mutated")
        self.assertEqual(self._snapshot(self.own_section, self.own_container, self.own_cell), own_snapshot)

    def test_the_same_mutations_do_work_on_the_callers_own_draft(self):
        """Control: the matrix is not vacuous — the draft's own rows accept the very same command shapes."""
        revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": revision,
            "mutation": {"type": "section.update_settings", "section_id": self.own_section.pk,
                         "patch": {"body_html": "<p>تازه</p>"}},
        })
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.own_section.refresh_from_db()
        self.assertIn("تازه", self.own_section.settings["body_html"])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, revision + 1)

    def test_inspector_and_media_routes_do_not_expose_non_draft_sections(self):
        from django.urls import reverse

        for label, (section, _container, _cell) in self.targets.items():
            with self.subTest(target=label):
                self.assertEqual(
                    self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk])).status_code,
                    404,
                )
                self.assertEqual(
                    self.client.get(
                        reverse("dashboard:storefront-builder-section-media-list", args=[section.pk, "hero_slide"]),
                    ).status_code,
                    404,
                )
        # a client for the foreign host cannot see the caller's own draft section either
        foreign_client = Client(HTTP_HOST=self.FOREIGN_HOST)
        foreign_client.login(username="sfb_matrix_foreign", password="pass12345")
        self.assertEqual(
            foreign_client.get(
                reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.own_section.pk]),
            ).status_code,
            404,
        )
