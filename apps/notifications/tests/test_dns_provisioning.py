"""Automatic DKIM provisioning: only where authorized, only the exact SES records, never touching other data, never
claiming success before the email provider verifies, and an exact Persian reason when automation is impossible."""

import base64

import dns.message
import dns.name
import dns.rcode
import dns.rdatatype
import dns.rrset
from django.test import TestCase, override_settings

from apps.notifications.mail import dns as D
from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.base import DnsRecord
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailSenderIdentity
from apps.stores.models import Store, StoreDomain

SECRET = base64.b64encode(b"super-secret-tsig-key-material").decode()
ZONE = "zone.test"


def recs(domain="shop.zone.test", n=3):
    return [DnsRecord("CNAME", f"tok{i}._domainkey.{domain}", f"tok{i}.dkim.amazonses.com", "dkim") for i in range(n)]


class FakeNameserver:
    """In-memory authoritative server: answers queries from ``data`` and applies updates into it (or refuses)."""

    def __init__(self):
        self.data: dict[tuple[str, str], list[str]] = {}
        self.updates = []
        self.update_rcode = dns.rcode.NOERROR
        self.query_rcode = dns.rcode.NOERROR
        self.down = False

    def install(self, provisioner):
        provisioner._query = self.query
        provisioner._send_update = self.send_update

    def query(self, name, rdtype):
        if self.down:
            raise ConnectionRefusedError("server down")
        msg = dns.message.make_query(name, rdtype)
        response = dns.message.make_response(msg)
        response.set_rcode(self.query_rcode)
        for value in self.data.get((name.lower().rstrip("."), rdtype), []):
            response.answer.append(dns.rrset.from_text(name + ".", 300, "IN", rdtype, value))
        return response

    def send_update(self, update):
        if self.down:
            raise ConnectionRefusedError("server down")
        self.updates.append(update)
        response = dns.message.make_response(update)
        response.set_rcode(self.update_rcode)
        if self.update_rcode == dns.rcode.NOERROR:
            for rrset in update.update:
                owner = str(rrset.name).rstrip(".")
                full = f"{owner}.{str(update.origin).rstrip('.')}".lower()
                self.data.setdefault((full, "CNAME"), []).append(str(rrset[0].target).rstrip("."))
        return response


CONF = dict(
    RASTISI_EMAIL_DNS_RFC2136_SERVER="203.0.113.53", RASTISI_EMAIL_DNS_RFC2136_KEY_NAME="rastisi-key.",
    RASTISI_EMAIL_DNS_RFC2136_KEY_SECRET=SECRET, RASTISI_EMAIL_DNS_ZONES=(ZONE,),
)


@override_settings(**CONF)
class Rfc2136ProvisionerTests(TestCase):
    def setUp(self):
        self.ns = FakeNameserver()
        self.p = D.Rfc2136DnsProvisioner()
        self.ns.install(self.p)

    def test_creates_exactly_the_three_dkim_cnames_and_reports_requested_not_success(self):
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.REQUESTED, "requested"))
        self.assertEqual(len(self.ns.updates), 3)
        self.assertEqual(sorted(k[0] for k in self.ns.data), [f"tok{i}._domainkey.shop.zone.test" for i in range(3)])
        self.assertTrue(all(k[1] == "CNAME" for k in self.ns.data))

    def test_updates_are_tsig_signed_and_scoped_to_the_configured_zone(self):
        self.p.apply("shop.zone.test", recs(n=1))
        update = self.ns.updates[0]
        self.assertEqual(str(update.origin).rstrip("."), ZONE)
        self.assertIsNotNone(update.keyring)
        self.assertEqual(str(update.keyname).rstrip("."), "rastisi-key")

    def test_idempotent_second_run_writes_nothing(self):
        self.p.apply("shop.zone.test", recs())
        self.ns.updates.clear()
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.REQUESTED, "already_present"))
        self.assertEqual(self.ns.updates, [])

    def test_a_different_existing_cname_is_a_conflict_and_is_never_overwritten(self):
        self.ns.data[("tok0._domainkey.shop.zone.test", "CNAME")] = ["someone-else.example.net"]
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.FAILED, "record_conflict"))
        self.assertEqual(self.ns.updates, [])  # nothing at all was written (checked BEFORE any write)
        self.assertEqual(self.ns.data[("tok0._domainkey.shop.zone.test", "CNAME")], ["someone-else.example.net"])

    def test_any_other_record_type_at_the_name_is_a_conflict(self):
        self.ns.data[("tok1._domainkey.shop.zone.test", "TXT")] = ['"v=something"']
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.FAILED, "record_conflict"))
        self.assertEqual(self.ns.updates, [])

    def test_domain_outside_the_authorized_zones_is_never_touched(self):
        self.assertFalse(self.p.controls_zone("shop.other.test"))
        self.assertFalse(self.p.controls_zone("zone.test.evil.com"))
        self.assertFalse(self.p.controls_zone("notzone.test"))
        out = self.p.apply("shop.other.test", recs("shop.other.test"))
        self.assertEqual((out.state, out.code), (D.NOT_ATTEMPTED, "zone_not_authorized"))
        self.assertEqual(self.ns.updates, [])

    def test_zone_apex_and_subdomains_are_in_scope(self):
        self.assertTrue(self.p.controls_zone("zone.test"))
        self.assertTrue(self.p.controls_zone("a.b.zone.test"))

    def test_only_ses_dkim_cnames_may_ever_be_written(self):
        bad_sets = [
            [DnsRecord("TXT", "tok0._domainkey.shop.zone.test", "v=spf1 -all", "spf")],
            [DnsRecord("CNAME", "www.shop.zone.test", "tok.dkim.amazonses.com", "dkim")],                 # not _domainkey
            [DnsRecord("CNAME", "shop.zone.test", "tok.dkim.amazonses.com", "dkim")],                      # apex
            [DnsRecord("CNAME", "tok0._domainkey.shop.zone.test", "evil.example.com", "dkim")],            # foreign target
            [DnsRecord("CNAME", "x.y._domainkey.shop.zone.test", "t.dkim.amazonses.com", "dkim")],         # extra label
            [DnsRecord("CNAME", "tok0._domainkey.other.zone.test", "t.dkim.amazonses.com", "dkim")],       # another domain
            [DnsRecord("MX", "tok0._domainkey.shop.zone.test", "10 mail.x", "mx")],
        ]
        for records in bad_sets:
            out = self.p.apply("shop.zone.test", records)
            self.assertEqual(out.code, "record_not_allowed", records[0].as_dict())
        self.assertEqual(self.ns.updates, [])

    def test_a_mixed_batch_with_one_forbidden_record_writes_nothing(self):
        batch = recs(n=2) + [DnsRecord("TXT", "tok9._domainkey.shop.zone.test", "x", "spf")]
        self.assertEqual(self.p.apply("shop.zone.test", batch).code, "record_not_allowed")
        self.assertEqual(self.ns.updates, [])

    def test_server_refusal_is_reported_as_failure_not_success(self):
        self.ns.update_rcode = dns.rcode.REFUSED
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.FAILED, "dns_server_error"))

    def test_partial_application_is_reported_as_partial(self):
        original = self.ns.send_update
        calls = {"n": 0}

        def flaky(update):
            calls["n"] += 1
            if calls["n"] == 2:
                self.ns.update_rcode = dns.rcode.SERVFAIL
            return original(update)

        self.p._send_update = flaky
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.FAILED, "partial"))

    def test_unreachable_server_never_raises_and_never_claims_success(self):
        self.ns.down = True
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual((out.state, out.code), (D.FAILED, "dns_server_error"))

    def test_error_detail_never_contains_the_key_secret(self):
        self.ns.down = True
        out = self.p.apply("shop.zone.test", recs())
        self.assertNotIn(SECRET, out.detail)
        self.assertNotIn("super-secret", out.detail)

    def test_bad_key_material_fails_closed(self):
        with override_settings(RASTISI_EMAIL_DNS_RFC2136_KEY_SECRET="***not-base64***"):
            p = D.Rfc2136DnsProvisioner()
            self.ns.install(p)
            self.assertEqual(p.apply("shop.zone.test", recs()).state, D.FAILED)
        self.assertEqual(self.ns.updates, [])

    def test_unexpected_query_rcode_aborts_before_any_write(self):
        self.ns.query_rcode = dns.rcode.SERVFAIL
        out = self.p.apply("shop.zone.test", recs())
        self.assertEqual(out.state, D.FAILED)
        self.assertEqual(self.ns.updates, [])


class ConfigurationTests(TestCase):
    def test_nothing_is_configured_by_default(self):
        self.assertIsNone(D.get_provisioner())
        self.assertEqual(D.try_apply("shop.test", recs("shop.test")).code, "no_integration")

    @override_settings(RASTISI_EMAIL_DNS_RFC2136_SERVER="203.0.113.53", RASTISI_EMAIL_DNS_ZONES=(ZONE,))
    def test_incomplete_rfc2136_configuration_is_treated_as_not_configured(self):
        self.assertIsNone(D.get_provisioner())  # no key -> no provisioner

    @override_settings(RASTISI_EMAIL_DNS_RFC2136_SERVER="203.0.113.53", RASTISI_EMAIL_DNS_RFC2136_KEY_NAME="k.",
                       RASTISI_EMAIL_DNS_RFC2136_KEY_SECRET=SECRET)
    def test_no_zone_allowlist_means_no_provisioner(self):
        self.assertIsNone(D.get_provisioner())

    @override_settings(**CONF)
    def test_complete_configuration_but_foreign_domain_is_zone_not_authorized(self):
        self.assertEqual(D.try_apply("merchant.example", recs("merchant.example")).code, "zone_not_authorized")

    def test_every_outcome_code_has_persian_text_and_an_instruction(self):
        for code in ("requested", "already_present", "no_integration", "zone_not_authorized", "record_conflict",
                     "record_not_allowed", "dns_server_error", "partial", "unexpected_error"):
            reason, action = D.describe(code)
            self.assertTrue(reason and action, code)
            self.assertTrue(any("\u0600" <= ch <= "\u06ff" for ch in reason), code)
        self.assertEqual(D.describe("made-up"), D.describe("unexpected_error"))

    def test_relative_name(self):
        self.assertEqual(D.relative_name("shop.test", "tok._domainkey.shop.test"), "tok._domainkey")
        self.assertEqual(D.relative_name("shop.test", "other.com"), "other.com")


class SyncIntegrationTests(TestCase):
    def setUp(self):
        FakeTransport.reset()
        D.FakeDnsProvisioner.reset()
        self.store = Store.objects.create(name="ف", slug="dns-int", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(store=self.store, hostname="shop.test", domain_type="custom_domain")

    def test_default_install_records_the_exact_blocking_reason_and_shows_persian_instructions(self):
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.dns_automation_state, identity.dns_automation_code), ("not_attempted", "no_integration"))
        self.assertFalse(identity.dns_auto_requested)
        d = svc.diagnostics(self.store)
        self.assertIn("راستی‌سی هیچ دسترسیِ مجازی برای نوشتن در DNS", d.dns_automation_reason_fa)
        self.assertTrue(d.dns_automation_action_fa)
        self.assertEqual(len(d.manual_steps_fa), 5)
        self.assertEqual(identity.status, "pending")

    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_authorized_zone_is_recorded_as_requested_and_stays_pending_until_the_provider_verifies(self):
        D.FakeDnsProvisioner.zones = {"shop.test"}
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.dns_automation_state, identity.dns_automation_code), ("requested", "requested"))
        self.assertEqual(identity.status, "pending")
        self.assertEqual(svc.active_sender_address(self.store), "")
        self.assertEqual(len(D.FakeDnsProvisioner.applied), 1)
        svc.sync_sender_identity(self.store)                      # recheck does not write again
        self.assertEqual(len(D.FakeDnsProvisioner.applied), 1)
        FakeTransport.verify("shop.test")
        self.assertEqual(svc.sync_sender_identity(self.store).status, "active")

    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_conflict_is_retried_on_each_recheck_and_clears_when_the_blocking_record_is_gone(self):
        D.FakeDnsProvisioner.zones = {"shop.test"}
        D.FakeDnsProvisioner.result = D.Outcome(D.FAILED, "record_conflict")
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.dns_automation_state, identity.dns_automation_code), ("failed", "record_conflict"))
        d = svc.diagnostics(self.store)
        self.assertIn("رکوردهای موجودِ شما را تغییر یا حذف نمی‌کند", d.dns_automation_reason_fa)
        D.FakeDnsProvisioner.result = None
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.dns_automation_state, "requested")

    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_zone_not_authorized_reason_when_an_integration_exists_but_not_for_this_domain(self):
        D.FakeDnsProvisioner.zones = {"another.test"}
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.dns_automation_code, "zone_not_authorized")

    def test_changing_the_sender_domain_resets_the_automation_record(self):
        svc.sync_sender_identity(self.store)
        StoreDomain.objects.filter(store=self.store).update(retired_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
                                                            is_primary=False)
        StoreDomain.objects.create(store=self.store, hostname="new.test", domain_type="custom_domain")
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.domain_name, "new.test")
        self.assertEqual(identity.dns_automation_code, "no_integration")  # re-evaluated for the new domain

    def test_active_sender_shows_no_dns_instructions(self):
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("shop.test")
        svc.sync_sender_identity(self.store)
        d = svc.diagnostics(self.store)
        self.assertEqual((d.dns_automation_reason_fa, d.manual_steps_fa), ("", ()))

    def test_provisioner_crash_degrades_to_manual_with_an_exact_reason(self):
        from unittest.mock import patch

        with override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner"), \
                patch.object(D.FakeDnsProvisioner, "controls_zone", side_effect=RuntimeError("api down")):
            identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.dns_automation_state, identity.dns_automation_code), ("failed", "unexpected_error"))
        self.assertEqual(identity.status, "pending")
