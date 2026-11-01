"""Automatic IndexNow: off by default, guarded, deduplicated, retried only when transient, honest about what «sent» means, store-scoped. Fake transport only."""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.core import automation, indexnow, indexnow_sync
from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreDomain

HOST = "shop.brand-example.ir"


class Transport:
    def __init__(self, *statuses):
        self.statuses, self.payloads = list(statuses), []

    def __call__(self, payload):
        self.payloads.append(payload)
        return self.statuses.pop(0) if self.statuses else 200


def _store(slug, host=HOST, verified=True):
    store = Store.objects.create(name=slug, slug=slug, status=Store.Status.ACTIVE)
    if host:
        StoreDomain.objects.create(
            store=store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED if verified else StoreDomain.VerificationStatus.PENDING,
            verified_at=timezone.now() if verified else None,
            verification_requested_at=None if verified else timezone.now(), verification_token="" if verified else "tok-pending-123")
    return store


def _product(store, slug, **extra):
    vendor, _ = Vendor.objects.get_or_create(store=store, slug="v", defaults={"name": "V"})
    category, _ = Category.objects.get_or_create(store=store, slug="c", defaults={"name": "C"})
    return Product.objects.create(store=store, vendor=vendor, category=category, name=slug, slug=slug, price=100000, **extra)


@override_settings(RASTISI_INDEXNOW_ENABLED=True)
class IndexNowSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _store("inx-a")
        p = mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(indexnow_sync, "_retired_product_urls", return_value=[])
        self.retired = q.start()
        self.addCleanup(q.stop)

    def sync(self, **kw):
        kw.setdefault("transport", Transport(200))
        kw.setdefault("sleep", lambda s: None)
        return indexnow_sync.sync(self.store, **kw)

    def test_default_platform_setting_is_off_and_nothing_is_sent(self):
        with override_settings(RASTISI_INDEXNOW_ENABLED=False):
            transport = Transport(200)
            result = self.sync(transport=transport)
        self.assertEqual((result.status, result.reason), (automation.DISABLED, "platform_disabled"))
        self.assertEqual(transport.payloads, [])
        from pathlib import Path
        source = (Path(__file__).resolve().parents[3] / "shop_core" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('RASTISI_INDEXNOW_ENABLED = env_bool("RASTISI_INDEXNOW_ENABLED", default=False)', source)     # off unless the platform turns it on

    def test_first_run_sends_everything_once_and_a_second_run_sends_nothing(self):
        transport = Transport(200)
        first = self.sync(transport=transport)
        self.assertEqual(first.status, automation.DONE)
        payload = transport.payloads[0]
        self.assertEqual(payload["host"], HOST)
        self.assertTrue(all(u.startswith(f"https://{HOST}/") for u in payload["urlList"]))
        self.assertEqual(len(payload["urlList"]), len(set(payload["urlList"])))
        self.assertEqual(payload["key"], indexnow.key_for_store(self.store))
        again = Transport(200)
        second = self.sync(transport=again)
        self.assertEqual(again.payloads, [])
        self.assertEqual(second.metrics["urls"], 0)

    def test_a_changed_product_is_sent_alone_and_a_retired_one_is_sent_as_gone(self):
        self.sync(transport=Transport(200))
        product = _product(self.store, "new-shoe")
        Product.objects.filter(pk=product.pk).update(updated_at=timezone.now() + timedelta(seconds=5))
        transport = Transport(200)
        result = self.sync(transport=transport, now=timezone.now() + timedelta(seconds=10))
        sent = transport.payloads[0]["urlList"] if transport.payloads else []
        self.assertTrue(any(u.endswith("/new-shoe/") for u in sent), sent)
        self.assertNotIn(f"https://{HOST}/", sent)                     # the home page did not change: it is not resubmitted
        self.assertEqual(result.status, automation.DONE)
        self.retired.return_value = [f"https://{HOST}/products/old-hat/"]
        transport = Transport(200)
        self.sync(transport=transport, now=timezone.now() + timedelta(seconds=20))
        self.assertIn(f"https://{HOST}/products/old-hat/", transport.payloads[0]["urlList"])

    def test_a_domain_change_resubmits_everything(self):
        self.sync(transport=Transport(200))
        domain = StoreDomain.objects.get(store=self.store)
        domain.hostname = "shop.new-brand-example.ir"
        domain.save()
        transport = Transport(200)
        result = self.sync(transport=transport, now=timezone.now() + timedelta(seconds=30))
        self.assertTrue(result.metrics["full_resubmit"])
        self.assertEqual(transport.payloads[0]["host"], "shop.new-brand-example.ir")

    def test_no_verified_domain_localhost_and_unpublished_never_send(self):
        for store in (_store("inx-nodomain", host=""), _store("inx-pending", host="pending.brand-example.ir", verified=False),
                      _store("inx-local", host="shop.rastisi.localhost")):
            transport = Transport(200)
            result = indexnow_sync.sync(store, transport=transport, sleep=lambda s: None)
            self.assertNotEqual(result.status, automation.DONE, store.slug)
            self.assertEqual(transport.payloads, [])
        with mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=False):
            transport = Transport(200)
            self.assertEqual(self.sync(transport=transport).reason, "store_not_public")
            self.assertEqual(transport.payloads, [])

    def test_dry_run_reports_the_plan_and_sends_and_records_nothing(self):
        transport = Transport(200)
        result = self.sync(transport=transport, dry_run=True)
        self.assertEqual(result.status, automation.DRY_RUN)
        self.assertGreater(result.metrics["urls"], 0)
        self.assertEqual(transport.payloads, [])
        self.assertFalse(AuditLogEntry.objects.filter(action_code="automation.indexnow_sync").exists())

    def test_transient_answers_are_retried_permanent_ones_are_not_and_success_is_never_faked(self):
        flaky = Transport(503, 429, 200)
        self.assertEqual(self.sync(transport=flaky).status, automation.DONE)
        self.assertEqual(len(flaky.payloads), 3)
        cache.clear()
        AuditLogEntry.objects.all().delete()
        rejected = Transport(403)
        result = self.sync(transport=rejected)
        self.assertEqual((result.status, len(rejected.payloads)), (automation.FAILED, 1))
        self.assertFalse(automation.last_result(self.store, "indexnow_sync")["ok"])
        AuditLogEntry.objects.all().delete()
        down = Transport(500, 500, 500)
        self.assertEqual(self.sync(transport=down).reason, "transient_exhausted")

    def test_the_result_says_accepted_not_indexed_and_never_contains_the_key(self):
        self.sync(transport=Transport(202))
        info = automation.last_result(self.store, "indexnow_sync")
        self.assertIn("not guaranteed", info["metadata"]["metrics"]["note"])
        self.assertNotIn(indexnow.key_for_store(self.store), str(info))

    def test_another_stores_urls_and_key_never_mix(self):
        other = _store("inx-b", host="shop.other-brand-example.ir")
        transport = Transport(200)
        self.sync(transport=transport)
        indexnow_sync.sync(other, transport=Transport(200), sleep=lambda s: None)
        payload = transport.payloads[0]
        self.assertNotIn("other-brand", str(payload))
        self.assertNotEqual(indexnow.key_for_store(self.store), indexnow.key_for_store(other))
        self.assertIsNone(automation.last_result(_store("inx-c", host=""), "indexnow_sync"))

    def test_no_url_is_private_or_off_host(self):
        with mock.patch.object(indexnow_sync.seo, "_sitemap_entries", return_value=[
                {"loc": f"https://{HOST}/", "lastmod": None}, {"loc": f"https://{HOST}/cart/", "lastmod": None},
                {"loc": f"https://{HOST}/checkout/", "lastmod": None}, {"loc": "http://shop.brand-example.ir/insecure/", "lastmod": None},
                {"loc": "https://evil.example.com/x/", "lastmod": None}]):
            transport = Transport(200)
            self.sync(transport=transport)
        self.assertEqual(transport.payloads[0]["urlList"], [f"https://{HOST}/"])
