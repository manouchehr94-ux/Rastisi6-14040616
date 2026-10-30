"""The Studio page and its Preview iframe are requested at the same moment. Two lifecycle paths used to race when they did:

* ``ensure_page_containers`` — a freshly applied template has Sections but no Cells yet; two requests each tried to place the same Section
  (a ``storefrontcell_section_id`` unique-constraint 500 on PostgreSQL);
* ``get_or_create_draft`` — right after a publish there is no Draft; two requests each tried to create it, and one could read a half-built one.

Real concurrency needs real row locks, so — like the project's other concurrency tests — this runs on PostgreSQL only (skipped on SQLite,
where writers are serialised by the file lock anyway)."""

import threading
import unittest

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.core.models import ShopSettings
from apps.storefront_builder.models import StorefrontCell, StorefrontContainer
from apps.storefront_builder.services import container_service, layout_service as svc
from apps.stores.models import Store
from apps.stores.services.platform_code_service import generate_unique_platform_code


def _run_together(target, count=2):
    barrier = threading.Barrier(count)
    results, errors = [], []

    def worker():
        try:
            barrier.wait(timeout=10)
            results.append(target())
        except Exception as exc:                                           # noqa: BLE001 - the test reports whatever happened
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results, errors


@unittest.skipUnless(connection.vendor == "postgresql", "row-lock concurrency needs PostgreSQL")
class StudioOpenConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه همزمانی", slug="hs-concurrency", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain="hs-concurrency",
        )
        ShopSettings.provision_for(self.store)

    def test_two_simultaneous_openings_place_every_section_exactly_once(self):
        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page("home")
        sections = page.sections.count()
        self.assertGreater(sections, 1)
        StorefrontContainer.all_objects.filter(page=page).delete()         # a template just applied: Sections, no Cells yet
        results, errors = _run_together(lambda: container_service.ensure_page_containers(page))
        self.assertEqual(errors, [], "no request may fail")
        self.assertEqual(page.containers.count(), sections)
        placed = list(StorefrontCell.objects.filter(container__page=page).values_list("section_id", flat=True))
        self.assertEqual(len(placed), len(set(placed)), "a Section sits in exactly one Cell")
        self.assertEqual(set(placed), set(page.sections.values_list("pk", flat=True)))

    def test_two_simultaneous_openings_after_a_publish_create_one_complete_draft(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        results, errors = _run_together(lambda: svc.get_or_create_draft(self.store).pk)
        self.assertEqual(errors, [], "no request may fail")
        self.assertEqual(len(set(results)), 1, "both requests got the same Draft")
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.pages.count(), 6)
        self.assertEqual(draft.layout.versions.filter(status="draft").count(), 1)
