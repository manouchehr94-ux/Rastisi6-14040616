"""Presentation helpers of the custom-domain guide: Host/Name hints, TXT/A/CNAME rows (targets only from settings), six steps."""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services import domain_guide_service as g


class HostHintTests(SimpleTestCase):
    def test_root_vs_subdomain_hosts(self):
        self.assertEqual((g.is_root_domain("example.com"), g.record_host("example.com"), g.txt_host_relative("example.com")), (True, "@", "_rastisi-verify"))
        self.assertEqual((g.is_root_domain("shop.example.com"), g.record_host("shop.example.com"), g.txt_host_relative("shop.example.com")),
                         (False, "shop", "_rastisi-verify.shop"))
        self.assertEqual(g.record_host("a.b.example.com"), "a.b")

    def test_two_level_suffixes_are_treated_as_one_registrable_domain(self):
        self.assertTrue(g.is_root_domain("example.co.ir"))
        self.assertEqual(g.record_host("shop.example.co.ir"), "shop")
        self.assertEqual(g.record_host("example.ac.ir"), "@")

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=("203.0.113.10",), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="edge.rastisi.test")
    def test_routing_rows_come_only_from_settings_and_the_right_type_is_recommended(self):
        root = g.routing_records("example.com")
        self.assertTrue(root["configured"])
        self.assertEqual([(r["type"], r["host"], r["value"], r["recommended"]) for r in root["rows"]],
                         [("A", "@", "203.0.113.10", True), ("CNAME", "@", "edge.rastisi.test", False)])
        sub = g.routing_records("shop.example.com")
        self.assertEqual([(r["type"], r["host"], r["recommended"]) for r in sub["rows"]], [("A", "shop", False), ("CNAME", "shop", True)])

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="")
    def test_nothing_is_invented_when_targets_are_not_configured(self):
        rec = g.routing_records("shop.example.com")
        self.assertFalse(rec["configured"])
        self.assertEqual(rec["rows"], [])


class StepsTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Guide", slug="guide-store", status=Store.Status.ACTIVE)

    def domain(self, **kw):
        defaults = dict(store=self.store, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                        verification_status=StoreDomain.VerificationStatus.UNVERIFIED)
        defaults.update(kw)
        if defaults["verification_status"] == "verified":
            defaults.setdefault("verified_at", timezone.now())
        return StoreDomain.objects.create(**defaults)

    def states(self, d, configured=True):
        return [s["state"] for s in g.steps(d, targets_configured=configured)]

    def test_unverified_domain_waits_at_the_txt_step(self):
        self.assertEqual(self.states(self.domain()), ["done", "done", "current", "todo", "todo", "todo"])

    def test_failed_txt_has_an_actionable_hint(self):
        d = self.domain(verification_status="failed", verification_token="tok")
        hint = g.steps(d, targets_configured=True)[2]["hint"]
        self.assertIn("TXT", hint)
        self.assertIn("Host", hint)

    def test_verified_domain_moves_to_routing_and_blocks_when_targets_missing(self):
        d = self.domain(verification_status="verified")
        self.assertEqual(self.states(d), ["done", "done", "done", "current", "todo", "todo"])
        blocked = g.steps(d, targets_configured=False)
        self.assertEqual(blocked[3]["state"], "blocked")
        self.assertIn("مدیر زیرساخت", blocked[3]["hint"])
        self.assertEqual(g.overall_state(blocked), "blocked")

    def test_routing_hint_mentions_proxy_and_stale_records(self):
        d = self.domain(verification_status="verified", routing_status="not_connected")
        self.assertIn("پروکسی", g.steps(d, targets_configured=True)[3]["hint"])

    def test_tls_pending_then_ready_and_fresh_enables_activation_step(self):
        now = timezone.now()
        d = self.domain(verification_status="verified", routing_status="connected", routing_checked_at=now, tls_status="not_ready", tls_checked_at=now)
        self.assertEqual(self.states(d)[4], "current")
        d.tls_status = "ready"; d.save()
        self.assertEqual(self.states(d), ["done", "done", "done", "done", "done", "current"])

    def test_stale_readiness_does_not_offer_activation(self):
        old = timezone.now() - timedelta(hours=3)
        d = self.domain(verification_status="verified", routing_status="connected", routing_checked_at=old, tls_status="ready", tls_checked_at=old)
        steps = g.steps(d, targets_configured=True)
        self.assertEqual(steps[5]["state"], "todo")
        self.assertIn("قدیمی", steps[5]["hint"])
        self.assertFalse(g.readiness_is_fresh(d))

    def test_active_domain_is_all_done(self):
        now = timezone.now()
        d = self.domain(verification_status="verified", routing_status="connected", routing_checked_at=now, tls_status="ready", tls_checked_at=now, is_primary=True)
        self.assertEqual(set(self.states(d)), {"done"})
        self.assertEqual(g.overall_state(g.steps(d, targets_configured=True)), "active")
