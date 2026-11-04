"""Periodic domain re-checks: read-only, rate-bounded, off by default, store-scoped, and they can never activate a domain. Fake lookups only."""

from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core import automation
from apps.stores.models import Store, StoreDomain
from apps.stores.services import domain_autocheck_service as svc


def dom(store, host, *, status="verified", requested_ago=None, routing_ago=None, primary=False, ready=False, token="tok"):
    now = timezone.now()
    verified = status == "verified"
    return StoreDomain.objects.create(
        store=store, hostname=host, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, is_primary=primary,
        verification_status=StoreDomain.VerificationStatus.VERIFIED if verified else StoreDomain.VerificationStatus.PENDING,
        verified_at=now if verified else None, verification_token="" if verified else token,
        verification_requested_at=None if verified else now - (requested_ago or timedelta(minutes=5)),
        routing_status=StoreDomain.RoutingStatus.CONNECTED if ready else StoreDomain.RoutingStatus.UNCHECKED,
        tls_status=StoreDomain.TlsStatus.READY if ready else StoreDomain.TlsStatus.UNCHECKED,
        routing_checked_at=None if routing_ago is None else now - routing_ago)


@override_settings(RASTISI_DOMAIN_AUTOCHECK_ENABLED=True)
class DomainAutocheckTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(name="A", slug="dac-a", status=Store.Status.ACTIVE)
        self.other = Store.objects.create(name="B", slug="dac-b", status=Store.Status.ACTIVE)
        self.verify, self.ready = mock.Mock(return_value=False), mock.Mock()

    def run_pass(self, **kw):
        return svc.recheck_store(self.store, verify=self.verify, readiness=self.ready, sleep=lambda s: None, **kw)

    def test_off_by_default_nothing_is_checked(self):
        dom(self.store, "pending.brand-example.ir", status="pending")
        with override_settings(RASTISI_DOMAIN_AUTOCHECK_ENABLED=False):
            result = self.run_pass()
        self.assertEqual(result.status, automation.DISABLED)
        self.verify.assert_not_called()
        source = (Path(__file__).resolve().parents[3] / "shop_core" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('RASTISI_DOMAIN_AUTOCHECK_ENABLED = env_bool("RASTISI_DOMAIN_AUTOCHECK_ENABLED", default=False)', source)

    def test_a_pending_domain_is_verified_through_the_existing_check_and_a_found_record_is_reported(self):
        pending = dom(self.store, "pending.brand-example.ir", status="pending")
        self.verify.return_value = True
        result = self.run_pass()
        self.assertEqual((result.status, result.metrics["verified"]), (automation.DONE, 1))
        self.verify.assert_called_once()
        self.assertEqual(self.verify.call_args.args[0].pk, pending.pk)
        self.ready.assert_not_called()
        self.assertTrue(automation.last_result(self.store, svc.OPERATION)["ok"])          # recorded: something really changed

    def test_nothing_changed_means_nothing_recorded(self):
        dom(self.store, "pending.brand-example.ir", status="pending")
        self.run_pass()
        self.assertIsNone(automation.last_result(self.store, svc.OPERATION))

    def test_an_abandoned_request_is_not_chased_forever(self):
        dom(self.store, "old.brand-example.ir", status="pending", requested_ago=svc.PENDING_WINDOW + timedelta(days=1))
        self.run_pass()
        self.verify.assert_not_called()

    def test_verified_domains_get_a_readiness_look_only_when_stale_or_not_ready(self):
        dom(self.store, "fresh-ready.brand-example.ir", ready=True, routing_ago=timedelta(minutes=30))
        stale = dom(self.store, "stale.brand-example.ir", ready=True, routing_ago=svc.READINESS_STALE + timedelta(minutes=1))
        never = dom(self.store, "never.brand-example.ir")
        recently_not_ready = dom(self.store, "waiting.brand-example.ir", routing_ago=timedelta(minutes=2))
        result = self.run_pass()
        checked = {c.args[0].pk for c in self.ready.call_args_list}
        self.assertEqual(checked, {stale.pk, never.pk})                     # not the fresh one, not the one looked at 2 minutes ago
        self.assertEqual(result.metrics["readiness_checked"], 2)
        self.assertNotIn(recently_not_ready.pk, checked)

    def test_the_active_primary_domain_is_only_looked_at_daily(self):
        primary = dom(self.store, "live.brand-example.ir", primary=True, ready=True, routing_ago=timedelta(hours=7))
        self.run_pass()
        self.ready.assert_not_called()
        StoreDomain.objects.filter(pk=primary.pk).update(routing_checked_at=timezone.now() - svc.ACTIVE_STALE - timedelta(minutes=1))
        self.run_pass()
        self.ready.assert_called_once()

    def test_dry_run_lists_what_is_due_and_calls_nothing(self):
        dom(self.store, "pending.brand-example.ir", status="pending")
        dom(self.store, "never.brand-example.ir")
        result = self.run_pass(dry_run=True)
        self.assertEqual((result.status, result.metrics["due"]), (automation.DRY_RUN, 2))
        self.assertCountEqual(result.metrics["hosts"], ["pending.brand-example.ir", "never.brand-example.ir"])
        self.verify.assert_not_called()
        self.ready.assert_not_called()

    def test_another_stores_domains_and_non_custom_domains_are_never_touched(self):
        dom(self.other, "theirs.brand-example.ir", status="pending")
        StoreDomain.objects.create(store=self.store, hostname="sub.rastisi.localhost", domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(), verification_token="")
        self.run_pass()
        self.verify.assert_not_called()
        self.ready.assert_not_called()

    def test_a_state_change_under_it_is_skipped_not_fatal(self):
        dom(self.store, "pending.brand-example.ir", status="pending")
        self.verify.side_effect = svc.dvs.DomainVerificationError("changed")
        result = self.run_pass()
        self.assertEqual((result.status, result.metrics["skipped"]), (automation.DONE, 1))

    def test_it_can_never_activate_a_domain_or_touch_dns_or_certificates(self):
        import ast

        tree = ast.parse(Path(svc.__file__).read_text(encoding="utf-8"))
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        for forbidden in ("activate_custom_domain", "requests", "urllib", "socket", "create_dns_record"):
            self.assertNotIn(forbidden, used | imported)
        self.assertEqual({n for n in used if n.startswith(("check_", "refresh_"))}, {"check_dns_verification", "refresh_custom_domain_readiness"})
