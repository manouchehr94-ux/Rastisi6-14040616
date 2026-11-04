"""Mandatory custom-domain email policy: provisioning, separate website/email verification, no shared fallback,
hold/recovery/expiry, SMS isolation. Fake provider only — no network, no real email."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer

User = get_user_model()
from apps.notifications.mail import dns as dns_mod
from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailSenderIdentity, NotificationOutbox
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.services.notification_service import (
    deliver_pending, release_held, retry_notification,
)
from apps.stores.models import Store, StoreDomain

S = NotificationOutbox.Status
ID = EmailSenderIdentity.Status


def make_store(slug):
    return Store.objects.create(name=f"فروشگاه {slug}", slug=slug, status=Store.Status.ACTIVE)


def add_domain(store, host, *, verified=False, primary=False):
    return StoreDomain.objects.create(
        store=store, hostname=host, is_primary=primary, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=(StoreDomain.VerificationStatus.VERIFIED if verified else StoreDomain.VerificationStatus.UNVERIFIED),
        verified_at=timezone.now() if verified else None,
    )


class SenderBase(TestCase):
    def setUp(self):
        FakeTransport.reset()
        dns_mod.FakeDnsProvisioner.reset()
        self.store = make_store("bike")
        user = User.objects.create_user(username="09125551111", password="x12345678")
        self.customer = Customer.objects.create(
            user=user, full_name="علی", phone="09125551111", email="ali@example.com",
            accepts_promotional_email=True, accepts_promotional_sms=True,
        )
        self.ctx = {"customer_name": "علی", "return_number": "R1", "order_number": "O1", "order_total": "1",
                    "order_status": "x", "order_url": "https://x.test/o", "reason": ""}

    def queue_email(self, store=None, key="k1", event="return.approved"):
        rows = dispatch_event(event, store=store or self.store, customer=self.customer, context=self.ctx,
                              channels=["email"], dedupe_key=key)
        self.assertEqual(len(rows), 1)
        return rows[0]


class ProvisioningTests(SenderBase):
    def test_no_custom_domain_is_inactive_with_full_diagnostics(self):
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.status, identity.reason_code), (ID.INACTIVE, "no_custom_domain"))
        d = svc.diagnostics(self.store)
        self.assertEqual(d.status, "inactive")
        self.assertTrue(d.reason_text and d.corrective_action)
        self.assertTrue(d.owner_action_required)
        self.assertFalse(d.platform_can_fix)
        self.assertEqual(d.responsible_party, "مالکِ دامنه")
        self.assertEqual(svc.active_sender_address(self.store), "")

    def test_email_verification_is_independent_of_website_verification(self):
        """Website TXT-ownership NOT verified, routing/TLS unchecked — email still provisions and can become ACTIVE."""
        dom = add_domain(self.store, "mybikestore.test", verified=False)
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.status, ID.PENDING)  # provider has not verified yet
        d = svc.diagnostics(self.store)
        self.assertEqual(d.website_domain, "mybikestore.test")
        self.assertEqual(d.website_status, dom.get_verification_status_display())
        FakeTransport.verify("mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.status, ID.ACTIVE)
        dom.refresh_from_db()
        self.assertNotEqual(dom.verification_status, StoreDomain.VerificationStatus.VERIFIED)  # still separate
        self.assertEqual(svc.active_sender_address(self.store), "info@mybikestore.test")

    def test_website_verified_does_not_make_email_active(self):
        add_domain(self.store, "mybikestore.test", verified=True, primary=True)
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual(identity.status, ID.PENDING)
        self.assertEqual(svc.active_sender_address(self.store), "")

    def test_pending_exposes_exact_provider_records_and_actions(self):
        add_domain(self.store, "mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        d = svc.diagnostics(self.store)
        self.assertEqual(d.status, "pending")
        self.assertEqual(len(d.dns_records), 3)
        for rec in d.dns_records:
            self.assertEqual(rec["type"], "CNAME")
            self.assertTrue(rec["name"].endswith("._domainkey.mybikestore.test"))
            self.assertTrue(rec["value"].endswith(".dkim.fake-mail.test"))
        self.assertIsNotNone(d.last_checked_at)
        self.assertTrue(d.owner_action_required)
        self.assertFalse(identity.dns_auto_requested)

    def test_activation_only_after_provider_confirms(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        for _ in range(3):
            self.assertEqual(svc.sync_sender_identity(self.store).status, ID.PENDING)
        FakeTransport.verify("mybikestore.test")
        self.assertEqual(svc.sync_sender_identity(self.store).status, ID.ACTIVE)

    def test_provider_failure_and_temporary_failure_reasons(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.fail_domain("mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.status, identity.reason_code), (ID.ERROR, "provider_failed"))
        FakeTransport.temp_fail_domain("mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.status, identity.reason_code), (ID.ERROR, "provider_temporary_failure"))
        d = svc.diagnostics(self.store)
        self.assertTrue(d.platform_can_fix and not d.owner_action_required)
        self.assertEqual(d.responsible_party, "راستی‌سی")

    def test_active_sender_survives_a_transient_provider_blip(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.temp_fail_domain("mybikestore.test")
        for _ in range(2):
            self.assertEqual(svc.sync_sender_identity(self.store).status, ID.ACTIVE)
        self.assertEqual(svc.sync_sender_identity(self.store).status, ID.ERROR)  # persistent -> blocked

    def test_provider_not_configured_blocks_email_only(self):
        add_domain(self.store, "mybikestore.test")
        with patch("apps.notifications.mail.provisioning_service.get_transport",
                   side_effect=svc.TransportNotConfigured("x")):
            identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.status, identity.reason_code), (ID.ERROR, "provider_not_configured"))

    def test_changing_the_sender_domain_never_carries_verification_over(self):
        d1 = add_domain(self.store, "old.test", primary=True)
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("old.test")
        self.assertEqual(svc.sync_sender_identity(self.store).status, ID.ACTIVE)
        d1.is_primary = False
        d1.retired_at = timezone.now()
        d1.save()
        add_domain(self.store, "new.test", primary=True)
        identity = svc.sync_sender_identity(self.store)
        self.assertEqual((identity.domain_name, identity.status), ("new.test", ID.PENDING))
        self.assertIsNone(identity.verified_at)
        self.assertEqual(svc.active_sender_address(self.store), "")

    def test_platform_disabled_blocks_even_a_verified_domain(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        EmailSenderIdentity.objects.filter(store=self.store).update(platform_disabled=True)
        self.assertEqual(svc.sync_sender_identity(self.store).reason_code, "platform_disabled")
        self.assertEqual(svc.active_sender_address(self.store), "")

    def test_tenant_isolation_of_senders(self):
        other = make_store("other")
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        self.assertEqual(svc.active_sender_address(self.store), "info@mybikestore.test")
        self.assertEqual(svc.active_sender_address(other), "")  # another Store cannot use it
        row = self.queue_email(store=other, key="iso")
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), (S.PENDING, "sender_not_active"))
        self.assertEqual(FakeTransport.sent, [])

    def test_revalidate_due_catches_a_domain_that_stopped_verifying(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        EmailSenderIdentity.objects.update(next_check_at=timezone.now() - timedelta(minutes=1))
        FakeTransport.fail_domain("mybikestore.test")
        result = svc.revalidate_due()
        self.assertEqual(result, {"checked": 1, "changed": 1})
        self.assertEqual(svc.active_sender_address(self.store), "")


class DnsProvisioningHonestyTests(SenderBase):
    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_authorized_zone_is_only_REQUESTED_never_claimed_successful(self):
        dns_mod.FakeDnsProvisioner.zones = {"mybikestore.test"}
        add_domain(self.store, "mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        self.assertTrue(identity.dns_auto_requested)
        self.assertEqual(len(dns_mod.FakeDnsProvisioner.applied), 1)
        self.assertEqual(identity.status, ID.PENDING)  # NOT active until the provider verifies
        self.assertEqual(svc.active_sender_address(self.store), "")
        FakeTransport.verify("mybikestore.test")
        self.assertEqual(svc.sync_sender_identity(self.store).status, ID.ACTIVE)

    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_unauthorized_zone_is_never_written(self):
        dns_mod.FakeDnsProvisioner.zones = set()
        add_domain(self.store, "mybikestore.test")
        identity = svc.sync_sender_identity(self.store)
        self.assertFalse(identity.dns_auto_requested)
        self.assertEqual(dns_mod.FakeDnsProvisioner.applied, [])

    def test_no_provisioner_configured_means_manual(self):
        add_domain(self.store, "mybikestore.test")
        self.assertFalse(svc.sync_sender_identity(self.store).dns_auto_requested)

    @override_settings(RASTISI_EMAIL_DNS_PROVISIONER="apps.notifications.mail.dns.FakeDnsProvisioner")
    def test_a_failing_provisioner_degrades_to_manual_without_raising(self):
        add_domain(self.store, "mybikestore.test")
        with patch.object(dns_mod.FakeDnsProvisioner, "controls_zone", side_effect=RuntimeError("api down")):
            identity = svc.sync_sender_identity(self.store)
        self.assertFalse(identity.dns_auto_requested)
        self.assertEqual(identity.status, ID.PENDING)

    def test_dns_publication_is_observation_only(self):
        records = [{"type": "CNAME", "name": "a._domainkey.x.test", "value": "a.dkim.fake-mail.test", "purpose": "dkim"}]
        self.assertEqual(dns_mod.annotate_published("x.test", records, enabled=False)[0]["published"], None)
        with patch.object(dns_mod, "_lookup", return_value=True):
            self.assertTrue(dns_mod.annotate_published("x.test", records, enabled=True)[0]["published"])


class NoSharedFallbackTests(SenderBase):
    def test_store_email_without_active_sender_is_held_not_sent_and_never_uses_shared_domain(self):
        row = self.queue_email()
        result = deliver_pending()
        row.refresh_from_db()
        self.assertEqual(result["held"], 1)
        self.assertEqual((row.status, row.attempts, row.last_error), (S.PENDING, 0, "sender_not_active"))
        self.assertEqual(FakeTransport.sent, [])
        self.assertEqual(mail.outbox, [])  # the shared DEFAULT_FROM_EMAIL path is never used for a Store

    def test_sender_is_the_stores_own_domain(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        row = self.queue_email()
        deliver_pending()
        row.refresh_from_db()
        msg = FakeTransport.sent[0]["message"]
        self.assertEqual(msg.from_address, "info@mybikestore.test")
        self.assertEqual((row.status, row.sender_address, row.provider), (S.SENT, "info@mybikestore.test", "fake"))
        self.assertTrue(row.provider_ref.startswith("fake-"))
        self.assertNotIn("rastisi", msg.from_address.lower())

    def test_provider_refusing_an_unverified_sender_is_permanent_and_not_retried(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        EmailSenderIdentity.objects.filter(store=self.store).update(status=ID.ACTIVE)  # stale local state
        row = self.queue_email()
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), (S.DEAD, 1))
        self.assertEqual(FakeTransport.sent, [])

    def test_sms_and_business_flow_are_unaffected_by_a_blocked_email_channel(self):
        sms = dispatch_event("return.approved", store=self.store, customer=self.customer, context=self.ctx,
                             channels=["sms"], dedupe_key="smsonly")
        email = self.queue_email(key="mailonly")
        from apps.sms.models import SmsLog

        ok = SmsLog(status=SmsLog.Status.SENT, provider="p", provider_ref_id="r")
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=ok):
            deliver_pending()
        for r in (*sms, email):
            r.refresh_from_db()
        self.assertEqual(sms[0].status, S.SENT)
        self.assertEqual(email.status, S.PENDING)


class HoldRecoveryExpiryTests(SenderBase):
    def add_owner(self):
        from apps.stores.models import StoreMembership

        owner = User.objects.create_user(username="owner1", password="x12345678", email="owner@example.com")
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def activate(self):
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        return svc.sync_sender_identity(self.store)

    def test_held_mail_is_sent_exactly_once_after_activation(self):
        row = self.queue_email()
        deliver_pending()
        add_domain(self.store, "mybikestore.test")
        svc.sync_sender_identity(self.store)
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)  # transition to ACTIVE releases held mail immediately
        deliver_pending()
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, len(FakeTransport.sent)), (S.SENT, 1))

    def test_transactional_mail_is_never_silently_discarded_on_expiry(self):
        row = self.queue_email()
        t0 = timezone.now()
        deliver_pending(now=t0)
        later = t0 + timedelta(hours=73)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=later - timedelta(minutes=1))
        result = deliver_pending(now=later)
        row.refresh_from_db()
        self.assertEqual(result["failed"], 1)
        self.assertEqual((row.status, row.last_error), (S.DEAD, "sender_not_active_expired"))  # visible, not SKIPPED
        # manual operational recovery works
        retry_notification(row)
        row.refresh_from_db()
        self.assertEqual(row.status, S.PENDING)

    def test_expired_important_mail_is_auto_revived_when_the_sender_recovers(self):
        row = self.queue_email()
        t0 = timezone.now()
        deliver_pending(now=t0)
        later = t0 + timedelta(hours=73)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=later - timedelta(minutes=1))
        deliver_pending(now=later)
        row.refresh_from_db()
        self.assertEqual(row.status, S.DEAD)
        self.activate()
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, len(FakeTransport.sent)), (S.SENT, 1))

    def test_promotional_mail_expires_as_skipped_and_is_not_revived(self):
        rows = dispatch_event("coupon.issued", store=self.store, customer=self.customer, channels=["email"],
                              dedupe_key="promo", context={
                                  "discount_code": "G", "discount_amount": "x", "discount_max": "",
                                  "discount_expires_at": "x", "campaign_name": "c", "occasion_name": "o",
                                  "customer_name": "علی"})
        row = rows[0]
        t0 = timezone.now()
        deliver_pending(now=t0)
        later = t0 + timedelta(hours=25)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=later - timedelta(minutes=1))
        deliver_pending(now=later)
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, "sender_not_active_expired"))
        self.assertEqual(release_held(self.store)["revived"], 0)

    def test_hold_does_not_burn_retry_attempts(self):
        row = self.queue_email()
        t = timezone.now()
        for i in range(8):
            deliver_pending(now=t + timedelta(minutes=16 * (i + 1)))
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), (S.PENDING, 0))

    def test_activation_and_problem_notices_come_from_the_platform_sender_not_the_store_domain(self):
        self.add_owner()
        self.activate()
        notices = NotificationOutbox.objects.filter(event_key="platform.email_sender_active")
        self.assertEqual(notices.count(), 1)
        self.assertEqual(notices[0].recipient_email, "owner@example.com")
        deliver_pending()  # platform sender path (Django mail backend), store domain not required
        self.assertTrue(all(m.from_email != "info@mybikestore.test" for m in mail.outbox))
