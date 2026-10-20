"""Default Published provisioning + Published immutability (final foundation hardening).

* ``ensure_default_published_layout`` is the engine's one lazy provisioning boundary. It must be idempotent under REAL
  concurrency (threads with their own DB connections; PostgreSQL only — SQLite serialises writers itself and has no row
  locks), never produce duplicate versions / IntegrityError, never publish or touch a Draft, never replace an existing
  Published version.
* A public GET never writes: an existing Published version keeps its rows and its content fingerprint. Legacy
  normalisation happens at the explicit lifecycle boundary ``layout_service.normalize_published_composition``.
"""

import threading

from django.db import connection, connections
from django.test import RequestFactory, TestCase, TransactionTestCase

from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import storefront_context_service as ctx
from apps.stores.models import Store

PUBLISHED = StorefrontLayoutVersion.Status.PUBLISHED


def _new_store(slug):
    return Store.objects.create(
        name=f"فروشگاه {slug}", slug=slug, admin_subdomain=slug, status=Store.Status.ACTIVE,
    )


def _composition(version):
    return (
        StorefrontSection.objects.filter(page__version=version).count(),
        StorefrontContainer.objects.filter(page__version=version).count(),
        StorefrontCell.objects.filter(container__page__version=version).count(),
    )


class DefaultPublishedConcurrencyTests(TransactionTestCase):
    """Real concurrency: N simultaneous first public requests for a Store that has never published."""

    THREADS = 8

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("real row-lock concurrency needs PostgreSQL (DATABASE_URL)")
        self.store = _new_store("sfb-conc-default")

    def _race(self, store):
        barrier = threading.Barrier(self.THREADS)
        results, errors = [], []

        def worker():
            try:
                barrier.wait(timeout=20)
                layout = svc.ensure_default_published_layout(store)
                results.append(layout.published_version_id)
            except BaseException as exc:  # noqa: BLE001 - the test reports every failure mode
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(self.THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        return results, errors

    def test_simultaneous_first_requests_create_exactly_one_default_published_version(self):
        results, errors = self._race(self.store)
        self.assertEqual(errors, [], f"concurrent provisioning raised: {errors!r}")
        self.assertEqual(len(results), self.THREADS)
        self.assertEqual(len(set(results)), 1, "every request must see the same Published version")
        layout = StorefrontLayout.objects.get(store=self.store)
        versions = list(layout.versions.all())
        self.assertEqual(len(versions), 1, [(v.version_number, v.status) for v in versions])
        self.assertEqual(versions[0].status, PUBLISHED)
        self.assertEqual(layout.published_version_id, versions[0].pk)
        self.assertIsNone(layout.draft_version_id)
        self.assertEqual(versions[0].content_fingerprint, versions[0].compute_fingerprint())

    def test_concurrent_first_requests_never_publish_or_touch_an_existing_draft(self):
        draft = svc.get_or_create_draft(self.store)
        draft.label = "merchant draft"
        draft.save(update_fields=["label"])
        draft_sections = StorefrontSection.objects.filter(page__version=draft).count()
        results, errors = self._race(self.store)
        self.assertEqual(errors, [], f"concurrent provisioning raised: {errors!r}")
        layout = StorefrontLayout.objects.get(store=self.store)
        draft.refresh_from_db()
        self.assertEqual(draft.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertEqual(draft.label, "merchant draft")
        self.assertEqual(layout.draft_version_id, draft.pk)
        self.assertEqual(StorefrontSection.objects.filter(page__version=draft).count(), draft_sections)
        published = layout.versions.filter(status=PUBLISHED)
        self.assertEqual(published.count(), 1)
        self.assertNotEqual(published.get().pk, draft.pk)
        self.assertEqual(layout.versions.count(), 2)

    def test_repeat_calls_after_the_race_are_idempotent(self):
        self._race(self.store)
        layout = StorefrontLayout.objects.get(store=self.store)
        before = (layout.published_version_id, layout.versions.count(), layout.published_version.content_fingerprint)
        for _ in range(3):
            svc.ensure_default_published_layout(self.store)
        layout.refresh_from_db()
        self.assertEqual(
            (layout.published_version_id, layout.versions.count(), layout.published_version.content_fingerprint), before,
        )


class DefaultPublishedProvisioningTests(TestCase):
    def test_a_legitimate_published_version_is_never_archived_or_replaced_by_the_obsolete_flag(self):
        store = _new_store("sfb-flag-default")
        layout = svc.get_or_create_layout(store)
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        StorefrontLayout.objects.filter(pk=layout.pk).update(uses_visual_storefront_layout=False)
        before = _composition(published)
        fingerprint = published.content_fingerprint

        again = svc.ensure_default_published_layout(store)

        self.assertEqual(again.published_version_id, published.pk)
        published.refresh_from_db()
        self.assertEqual(published.status, PUBLISHED)
        self.assertEqual(again.versions.count(), 1)
        self.assertEqual(_composition(published), before)
        self.assertEqual(published.content_fingerprint, fingerprint)

    def test_first_provisioning_builds_one_valid_default_and_leaves_no_draft(self):
        store = _new_store("sfb-first-default")
        layout = svc.ensure_default_published_layout(store)
        version = layout.published_version
        self.assertEqual(version.status, PUBLISHED)
        self.assertEqual(layout.versions.count(), 1)
        self.assertIsNone(layout.draft_version_id)
        self.assertEqual(version.content_fingerprint, version.compute_fingerprint())
        self.assertFalse(
            StorefrontSection.objects.filter(page__version=version, is_active=True, placement_cell__isnull=True).exists()
        )


class PublishedImmutabilityTests(TestCase):
    def _published_with_unplaced_legacy_section(self, slug):
        store = _new_store(slug)
        svc.get_or_create_draft(store)
        published = svc.publish(store)
        home = published.get_page(StorefrontPage.PageType.HOME)
        # a pre-invariant legacy row: an active section that sits in no cell
        legacy = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=99, settings={"body_html": "<p>x</p>"},
        )
        return store, published, legacy

    def test_public_get_never_mutates_an_existing_published_version(self):
        store, published, legacy = self._published_with_unplaced_legacy_section("sfb-immut-get")
        fingerprint = published.content_fingerprint
        before = _composition(published)

        for _ in range(2):
            svc.ensure_default_published_layout(store)
            request = RequestFactory().get("/")
            request.store = store
            ctx.build_universal_storefront_context(request, store, "home")

        published.refresh_from_db()
        self.assertEqual(_composition(published), before, "a public GET must not create containers/cells")
        self.assertEqual(published.content_fingerprint, fingerprint)
        self.assertFalse(StorefrontCell.objects.filter(section=legacy).exists())

    def test_explicit_normalisation_places_legacy_sections_and_refreshes_the_fingerprint(self):
        store, published, legacy = self._published_with_unplaced_legacy_section("sfb-immut-norm")
        stale = published.content_fingerprint

        changed = svc.normalize_published_composition(store)

        self.assertTrue(changed)
        published.refresh_from_db()
        self.assertTrue(StorefrontCell.objects.filter(section=legacy).exists())
        self.assertEqual(published.status, PUBLISHED)
        self.assertNotEqual(published.content_fingerprint, stale)
        self.assertEqual(
            published.content_fingerprint, published.compute_fingerprint(),
            "the fingerprint always represents the actual published composition",
        )
        # idempotent: a second pass has nothing to do and writes nothing
        after = (published.content_fingerprint, _composition(published))
        self.assertFalse(svc.normalize_published_composition(store))
        published.refresh_from_db()
        self.assertEqual((published.content_fingerprint, _composition(published)), after)

    def test_normalisation_is_a_noop_for_a_store_without_a_published_version(self):
        store = _new_store("sfb-immut-none")
        self.assertFalse(svc.normalize_published_composition(store))
        self.assertFalse(StorefrontLayoutVersion.objects.filter(layout__store=store).exists())


class NormalizePublishedLayoutsCommandTests(TestCase):
    def test_dry_run_reports_without_writing_and_the_real_run_normalises(self):
        from io import StringIO

        from django.core.management import call_command

        helper = PublishedImmutabilityTests()
        store, published, legacy = helper._published_with_unplaced_legacy_section("sfb-cmd-norm")
        stale = published.content_fingerprint

        out = StringIO()
        call_command("normalize_published_layouts", "--store", store.slug, "--dry-run", stdout=out)
        self.assertIn("1 unplaced", out.getvalue())
        published.refresh_from_db()
        self.assertEqual(published.content_fingerprint, stale)
        self.assertFalse(StorefrontCell.objects.filter(section=legacy).exists())

        call_command("normalize_published_layouts", "--store", store.slug, stdout=StringIO())
        published.refresh_from_db()
        self.assertTrue(StorefrontCell.objects.filter(section=legacy).exists())
        self.assertEqual(published.content_fingerprint, published.compute_fingerprint())
