"""Platform card-to-card: a first-class MANUAL payment method (not a fake online gateway). A submitted receipt is a CLAIM, never proof;
only an authorised finance admin, using an independent bank-statement reference and the exact amount, can approve — and approval goes
through the existing confirm_payment / SMS credit ledger so fulfilment happens exactly once. Synthetic data only; no real bank details."""

import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import (
    PlatformManualPaymentClaim as Claim,
    PlatformManualPaymentClaimEvent as ClaimEvent,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.services import manual_card_service as mcs
from apps.billing.services import refund_service
from apps.billing.services import sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.core.models import AuditLogEntry
from apps.orders.models import PaymentGatewayConfig
from apps.portal.models import PlatformAuditLogEntry, PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
S = Claim.Status
DEST_CARD = "6037997000000019"           # synthetic, Luhn-valid — not a real account
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64
_HOST = "platformadmins.rastisi.localhost"


def use_private_tmp(case):
    """Receipts go to a throw-away private directory (never the real private_media)."""
    tmp = tempfile.mkdtemp(prefix="rs_receipts_")
    storage = Claim._meta.get_field("receipt").storage
    old = getattr(storage, "_location", None)
    storage._location = tmp
    for attr in ("base_location", "location"):
        storage.__dict__.pop(attr, None)

    def restore():
        storage._location = old
        for attr in ("base_location", "location"):
            storage.__dict__.pop(attr, None)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    case.addCleanup(restore)
    return tmp


def enable_platform_card(case, *, types=("subscription", "sms_package"), card=DEST_CARD, enabled=True):
    case.addCleanup(cache.clear)
    cache.clear()
    pgs.save_gateway(
        pgs.PLATFORM_CARD, credentials={"destination_card": card, "holder_name": "شرکت نمونه راستیسی", "bank_name": "بانک نمونه",
                                         "sheba": "IR062960000000100324200001"},
        sandbox=False, enabled=enabled, purchase_types=list(types),
    )
    cache.clear()


def upload(data=PNG, name="receipt.png", content_type="image/png"):
    return SimpleUploadedFile(name, data, content_type=content_type)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class CardToCardBase(TestCase):
    PRICE = "300000"

    def setUp(self):
        use_private_tmp(self)
        self.store = Store.objects.create(name="فروشگاه کارت", slug="c2c-store", admin_subdomain="c2c-store")
        self.owner = User.objects.create_user(username="c2c-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.finance = User.objects.create_user(username="finance@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.finance2 = User.objects.create_user(username="finance2@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.sub, self.invoice = open_invoice_for(self.store, code="c2c", price=self.PRICE)
        enable_platform_card(self)

    def claim(self, ref="TRK-4455-6677", invoice=None, **extra):
        defaults = dict(user=self.owner, store=self.store, reference=ref, transferred_at=timezone.now() - timedelta(hours=1))
        defaults.update(extra)
        if "sms_purchase" not in extra:
            defaults.setdefault("invoice", invoice or self.invoice)
        return mcs.submit_claim(**defaults)

    def approve(self, claim, *, reviewer=None, ref="BANK-STMT-0001", amount=None, note=""):
        return mcs.approve_claim(
            claim, reviewer=reviewer or self.finance, bank_confirmation_reference=ref,
            confirmed_amount=amount if amount is not None else claim.expected_amount, note=note,
        )

    def sub_status(self):
        return StoreSubscription.objects.get(pk=self.sub.pk).status


class ConfigurationTests(CardToCardBase):
    def test_the_method_is_ready_only_with_valid_destination_details_and_chosen_purchase_types(self):
        state = pgs.gateway_state(pgs.PLATFORM_CARD)
        self.assertEqual((state.status, state.kind, state.ready), (pgs.READY, "manual", True))
        self.assertEqual(set(state.allowed_types), {"subscription", "sms_package"})
        PlatformGatewayConfig.objects.filter(gateway_code=pgs.PLATFORM_CARD).update(purchase_types=[])
        cache.clear()
        self.assertEqual(pgs.gateway_state(pgs.PLATFORM_CARD).status, pgs.MISSING_CONFIG)       # no purchase type chosen
        self.assertIsNone(pgs.manual_option("subscription"))

    def test_an_invalid_card_number_is_refused_with_the_same_card_rules_as_the_store_flow(self):
        PlatformGatewayConfig.objects.all().delete()
        for bad in ("6037997000000018", "1234", "6037 9970 0000"):
            with self.assertRaises(pgs.PlatformGatewayError, msg=bad):
                pgs.save_gateway(pgs.PLATFORM_CARD, credentials={"destination_card": bad, "holder_name": "x"}, sandbox=False,
                                 enabled=True, purchase_types=["subscription"])
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.save_gateway(pgs.PLATFORM_CARD, credentials={"destination_card": DEST_CARD, "holder_name": ""}, sandbox=False, enabled=True,
                             purchase_types=["subscription"])

    def test_persian_digits_and_spaces_are_normalised_to_the_canonical_card(self):
        PlatformGatewayConfig.objects.all().delete()
        pgs.save_gateway(pgs.PLATFORM_CARD, credentials={"destination_card": "۶۰۳۷ ۹۹۷۰ ۰۰۰۰ ۰۰۱۹", "holder_name": "نمونه"}, sandbox=False,
                         enabled=True, purchase_types=["subscription"])
        self.assertEqual(pgs.credentials_and_mode(pgs.PLATFORM_CARD)[0]["destination_card"], DEST_CARD)
        self.assertEqual(pgs.manual_card_instructions()["card_display"], "6037 9970 0000 0019")

    def test_platform_card_details_are_never_mixed_with_the_stores_own_card_transfer_settings(self):
        store_cfg = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="card_to_card", is_active=True)
        store_cfg.set_credentials({"destination_card": "6104337812345678", "holder_name": "صاحب فروشگاه"})
        store_cfg.save()
        snapshot = PaymentGatewayConfig.objects.get(pk=store_cfg.pk).encrypted_credentials
        self.assertEqual(pgs.manual_card_instructions()["card_number"], DEST_CARD)
        pgs.save_gateway(pgs.PLATFORM_CARD, credentials={"holder_name": "نام جدید"}, sandbox=False, enabled=True, purchase_types=["subscription"])
        self.assertEqual(PaymentGatewayConfig.objects.get(pk=store_cfg.pk).encrypted_credentials, snapshot)
        self.assertEqual(PlatformGatewayConfig.objects.get(gateway_code=pgs.PLATFORM_CARD).gateway_code, "platform_card")
        self.assertNotIn("card_to_card", {r.gateway_code for r in PlatformGatewayConfig.objects.all()})

    def test_the_manual_method_is_never_an_online_default_and_never_an_online_option(self):
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.set_default(pgs.PLATFORM_CARD)
        self.assertNotIn(pgs.PLATFORM_CARD, pgs.ready_codes("subscription"))
        option = pgs.manual_option("subscription")
        self.assertTrue(option["manual"])
        self.assertNotIn("card", " ".join(str(v) for k, v in option.items() if k != "label").lower().replace("platform_card", ""))   # no card details leak
        self.assertEqual({o["code"] for o in pgs.checkout_options("subscription")}, {pgs.PLATFORM_CARD})

    def test_disabled_or_unselected_purchase_types_hide_the_option(self):
        enable_platform_card(self, types=("subscription",))
        self.assertIsNotNone(pgs.manual_option("subscription"))
        self.assertIsNone(pgs.manual_option("sms_package"))
        enable_platform_card(self, enabled=False)
        self.assertIsNone(pgs.manual_option("subscription"))


class SubmissionTests(CardToCardBase):
    def test_a_submitted_claim_is_pending_review_and_has_no_financial_effect(self):
        claim = self.claim()
        self.assertEqual(claim.status, S.PENDING_REVIEW)
        self.assertEqual((claim.expected_amount, claim.currency, claim.submitted_by_id), (Decimal(self.PRICE), "IRT", self.owner.pk))
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, invoice.amount_paid), (SubscriptionInvoice.Status.PAYMENT_PENDING, 0))
        self.assertNotEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        attempt = claim.subscription_attempt
        self.assertEqual((attempt.provider, attempt.status), ("platform_card", SubscriptionPaymentAttempt.Status.PENDING))
        self.assertEqual(list(claim.events.values_list("action", flat=True)), ["submitted"])
        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.manual_claim_submitted").exists())
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="billing.manual_claim_submitted").exists())

    def test_the_amount_always_comes_from_the_server_never_from_the_caller(self):
        import inspect
        self.assertNotIn("amount", inspect.signature(mcs.submit_claim).parameters)
        self.assertEqual(self.claim().expected_amount, SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_due)

    def test_receipt_is_stored_privately_with_a_content_sniffed_type_and_a_hash(self):
        import hashlib
        import os
        from django.conf import settings

        claim = self.claim(receipt=upload())
        claim.refresh_from_db()
        self.assertEqual((claim.receipt_content_type, claim.receipt_sha256), ("image/png", hashlib.sha256(PNG).hexdigest()))
        path = claim.receipt.path
        self.assertTrue(os.path.exists(path))
        self.assertFalse(path.startswith(str(settings.MEDIA_ROOT)), "receipts must never live under public media")
        self.assertTrue(path.startswith(str(Claim._meta.get_field("receipt").storage.location)))

    def test_receipt_types_are_sniffed_from_content_not_the_name_or_declared_type(self):
        for data, kind in ((JPEG, "image/jpeg"), (PDF, "application/pdf"), (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 20, "image/webp")):
            made = self.claim(ref=f"REF-{kind[-3:]}-000111", receipt=upload(data, "x.txt", "text/plain"))
            self.assertEqual(made.receipt_content_type, kind)
            mcs.cancel_claim(made, user=self.owner)
        for bad in (b"<html><script>alert(1)</script>", b"GIF89a" + b"0" * 30, b"MZ" + b"0" * 30, b""):
            with self.assertRaises(mcs.ClaimError, msg=bad[:6]):
                self.claim(ref="REF-BAD-FILE-9", receipt=upload(bad, "evil.png", "image/png"))

    def test_oversized_receipts_are_refused(self):
        with self.assertRaises(mcs.ClaimError):
            self.claim(receipt=upload(PNG + b"0" * mcs.MAX_RECEIPT_BYTES))

    def test_validation_of_reference_time_and_card_digits(self):
        for ref in ("123", "  ", "ab--"):
            with self.assertRaises(mcs.ClaimError, msg=ref):
                self.claim(ref=ref)
        with self.assertRaises(mcs.ClaimError):
            self.claim(transferred_at=timezone.now() + timedelta(hours=2))
        with self.assertRaises(mcs.ClaimError):
            self.claim(payer_card_last4="12")
        claim = self.claim(ref="OLD-TRANSFER-1", transferred_at=timezone.now() - timedelta(days=30), payer_card_last4="۱۲۳۴")
        self.assertIn("old_transfer", claim.flags)
        self.assertEqual(claim.payer_card_last4, "1234")

    def test_reference_normalisation_makes_persian_arabic_spaced_variants_collide(self):
        self.assertEqual(mcs.normalize_reference("۱۲۳-۴۵ ۶۷۸ABC"), "12345678abc")
        self.assertEqual(mcs.normalize_reference("١٢٣٤٥٦٧٨ abc"), "12345678abc")

    def test_a_store_cannot_claim_for_another_stores_invoice_or_purchase(self):
        other = Store.objects.create(name="دیگر", slug="c2c-other", admin_subdomain="c2c-other")
        with self.assertRaises(mcs.ClaimError):
            self.claim(store=other)
        package = SmsPackage.objects.create(name="بسته", credit_amount=10, price=5000)
        foreign = balance_service.request_purchase(store=other, package=package)
        with self.assertRaises(mcs.ClaimError):
            mcs.submit_claim(user=self.owner, store=self.store, reference="REF-FOREIGN-1", transferred_at=timezone.now(), sms_purchase=foreign)

    def test_only_payable_targets_and_enabled_types_can_be_claimed(self):
        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.PAID)
        with self.assertRaises(mcs.ClaimError):
            self.claim()
        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.OPEN)
        enable_platform_card(self, types=("sms_package",))
        with self.assertRaises(mcs.ClaimError):
            self.claim()                                              # subscription not allowed for this method
        enable_platform_card(self, enabled=False)
        with self.assertRaises(mcs.ClaimError):
            self.claim()

    def test_only_one_pending_claim_per_invoice_and_a_flag_after_repeated_rejections(self):
        first = self.claim()
        with self.assertRaises(mcs.ClaimError):
            self.claim(ref="ANOTHER-REF-123")                        # stacking claims on one invoice is refused
        for n in range(3):
            mcs.reject_claim(first, reviewer=self.finance, reason="رسید خوانا نیست")
            first = self.claim(ref=f"REPEAT-REF-{n}-99")
        self.assertIn("repeated_rejected_claims", first.flags)


class DuplicateAndReplayTests(CardToCardBase):
    def test_a_duplicate_reference_is_refused_and_recorded_for_review(self):
        self.claim(ref="DUP-REF-001122")
        _sub2, invoice2 = open_invoice_for(Store.objects.create(name="دو", slug="c2c-two", admin_subdomain="c2c-two"), code="c2c2", price="100000")
        other_store = invoice2.store
        enable_platform_card(self)
        with self.assertRaises(mcs.DuplicateReferenceError):
            mcs.submit_claim(user=self.owner, store=other_store, reference="dup-ref 001122", transferred_at=timezone.now(), invoice=invoice2)
        self.assertEqual(Claim.objects.count(), 1)
        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.manual_claim_duplicate_reference", store=other_store).exists())
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="billing.manual_claim_duplicate_reference").exists())

    def test_a_rejected_reference_can_be_corrected_and_resubmitted_but_an_approved_one_never(self):
        claim = self.claim(ref="CORRECT-ME-5566")
        mcs.reject_claim(claim, reviewer=self.finance, reason="مبلغ نادرست — اصلاح کنید")
        again = self.claim(ref="CORRECT-ME-5566")                    # corrected claim after rejection
        self.approve(again)
        _s, invoice3 = open_invoice_for(Store.objects.create(name="سه", slug="c2c-three", admin_subdomain="c2c-three"), code="c2c3", price="90000")
        with self.assertRaises(mcs.DuplicateReferenceError):
            mcs.submit_claim(user=self.owner, store=invoice3.store, reference="CORRECT-ME-5566", transferred_at=timezone.now(), invoice=invoice3)

    def test_the_same_receipt_file_is_flagged_when_reused_on_another_active_claim(self):
        self.claim(ref="FILE-REUSE-0001", receipt=upload())
        other_store = Store.objects.create(name="چهار", slug="c2c-four", admin_subdomain="c2c-four")
        _s, invoice4 = open_invoice_for(other_store, code="c2c4", price="50000")
        second = mcs.submit_claim(user=self.owner, store=other_store, reference="FILE-REUSE-0002", transferred_at=timezone.now(),
                                  invoice=invoice4, receipt=upload())
        self.assertIn("duplicate_receipt_file", second.flags)

    def test_the_database_itself_enforces_the_uniqueness_rules(self):
        claim = self.claim(ref="DB-RULES-998877")
        base = dict(store=self.store, expected_amount=Decimal("1"), currency="IRT", transferred_at=timezone.now(), expires_at=timezone.now() + timedelta(days=1))
        _s, other_invoice = open_invoice_for(Store.objects.create(name="پنج", slug="c2c-five", admin_subdomain="c2c-five"), code="c2c5", price="10000")
        with self.assertRaises(IntegrityError), transaction.atomic():                     # active reference unique
            Claim.objects.create(invoice=other_invoice, reference_raw="x", reference_key=claim.reference_key, **base)
        with self.assertRaises(IntegrityError), transaction.atomic():                     # exactly one target
            Claim.objects.create(reference_raw="y", reference_key="uniquekey1", **base)
        with self.assertRaises(IntegrityError), transaction.atomic():                     # exactly one target (both)
            package = SmsPackage.objects.create(name="ب", credit_amount=1, price=1)
            purchase = balance_service.request_purchase(store=self.store, package=package)
            Claim.objects.create(invoice=other_invoice, sms_purchase=purchase, reference_raw="z", reference_key="uniquekey2", **base)
        with self.assertRaises(IntegrityError), transaction.atomic():                     # amount must be positive
            Claim.objects.create(invoice=other_invoice, reference_raw="w", reference_key="uniquekey3", **{**base, "expected_amount": Decimal("0")})
        with self.assertRaises(IntegrityError), transaction.atomic():                     # one pending claim per invoice
            Claim.objects.create(invoice=self.invoice, reference_raw="v", reference_key="uniquekey4", **base)

    def test_the_event_history_is_append_only(self):
        claim = self.claim()
        event = claim.events.first()
        event.detail = {"tampered": True}
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()


class ApprovalTests(CardToCardBase):
    def test_a_receipt_alone_never_activates_anything_and_only_finance_approval_does_exactly_once(self):
        claim = self.claim(receipt=upload())
        self.assertNotEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        approved = self.approve(claim, note="دیده شد در صورتحساب")
        self.assertEqual(approved.status, S.APPROVED)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, invoice.amount_paid), (SubscriptionInvoice.Status.PAID, Decimal(self.PRICE)))
        self.assertEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        attempt = SubscriptionPaymentAttempt.objects.get(pk=claim.subscription_attempt_id)
        self.assertEqual((attempt.status, attempt.provider_payment_id), (SubscriptionPaymentAttempt.Status.SUCCEEDED, f"card-{claim.reference_key}"))
        self.assertEqual((approved.reviewed_by_id, approved.bank_confirmation_reference, approved.confirmed_amount),
                         (self.finance.pk, "BANK-STMT-0001", Decimal(self.PRICE)))
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)
        for _ in range(3):                                           # repeated approval = idempotent, no second effect
            self.approve(claim)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, Decimal(self.PRICE))
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)
        self.assertEqual(list(claim.events.values_list("action", flat=True)), ["submitted", "approved"])

    def test_only_an_authorised_finance_administrator_can_approve_or_reject(self):
        claim = self.claim()
        staff = User.objects.create_user(username="staff-only", password="x", is_staff=True)
        plain = User.objects.create_user(username="plain-user", password="x")
        inactive = User.objects.create_user(username="inactive-su", password="x", is_staff=True, is_superuser=True, is_active=False)
        for who in (staff, plain, inactive, self.owner, None):
            with self.assertRaises(mcs.ClaimError, msg=str(who)):
                self.approve(claim, reviewer=who) if who is not None else mcs.approve_claim(claim, reviewer=None, bank_confirmation_reference="BANK-X-123", confirmed_amount=claim.expected_amount)
            with self.assertRaises(mcs.ClaimError, msg=str(who)):
                mcs.reject_claim(claim, reviewer=who, reason="تست مجوز") if who is not None else mcs.reject_claim(claim, reviewer=None, reason="تست مجوز")
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)
        self.assertNotEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)

    def test_self_approval_and_store_member_conflicts_of_interest_are_blocked(self):
        self.owner.is_superuser = True                                # a platform admin who is also this store's owner
        self.owner.save()
        claim = self.claim()
        with self.assertRaises(mcs.ClaimError) as ctx:
            self.approve(claim, reviewer=self.owner)
        self.assertIn("خودتان", str(ctx.exception))
        with self.assertRaises(mcs.ClaimError):
            mcs.reject_claim(claim, reviewer=self.owner, reason="ردِ ادعای خودم")
        member_admin = User.objects.create_user(username="member-admin", password="x", is_staff=True, is_superuser=True)
        StoreMembership.objects.filter(store=self.store).update(user=member_admin)       # the store's active member is now a platform admin
        with self.assertRaises(mcs.ClaimError) as ctx:
            self.approve(claim, reviewer=member_admin)
        self.assertIn("عضوِ فعالِ همین فروشگاه", str(ctx.exception))
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)

    def test_approval_requires_an_independent_bank_reference_and_the_exact_amount(self):
        claim = self.claim()
        for bad_ref in ("", "  ", "abc"):
            with self.assertRaises(mcs.ClaimError, msg=bad_ref):
                self.approve(claim, ref=bad_ref)
        for amount in (str(int(self.PRICE) - 1), str(int(self.PRICE) + 1), "0", "abc", "-5", ""):          # under / over / junk
            with self.assertRaises(mcs.ClaimError, msg=amount):
                self.approve(claim, amount=amount)
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, 0)

    def test_one_bank_statement_line_cannot_approve_two_payments(self):
        self.approve(self.claim(), ref="SAME-BANK-LINE-1")
        other_store = Store.objects.create(name="شش", slug="c2c-six", admin_subdomain="c2c-six")
        _s, invoice6 = open_invoice_for(other_store, code="c2c6", price=self.PRICE)
        claim6 = mcs.submit_claim(user=self.owner, store=other_store, reference="OTHER-TRANSFER-77", transferred_at=timezone.now(), invoice=invoice6)
        with self.assertRaises(mcs.ClaimError):
            self.approve(claim6, ref="SAME-BANK-LINE-1")
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice6.pk).amount_paid, 0)

    def test_an_expired_claim_cannot_be_approved_and_expiry_frees_the_reference_without_effect(self):
        claim = self.claim(ref="EXPIRING-REF-12")
        Claim.objects.filter(pk=claim.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaises(mcs.ClaimError):
            self.approve(claim)
        self.assertEqual(mcs.expire_stale_claims(), 1)
        expired = Claim.objects.get(pk=claim.pk)
        self.assertEqual(expired.status, S.EXPIRED)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=claim.subscription_attempt_id).status, SubscriptionPaymentAttempt.Status.EXPIRED)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, 0)
        self.assertEqual(mcs.expire_stale_claims(), 0)
        self.claim(ref="EXPIRING-REF-12")                            # the reference is free again

    def test_rejection_needs_a_reason_keeps_the_invoice_payable_and_blocks_later_approval(self):
        claim = self.claim()
        with self.assertRaises(mcs.ClaimError):
            mcs.reject_claim(claim, reviewer=self.finance, reason="  ")
        rejected = mcs.reject_claim(claim, reviewer=self.finance, reason="مبلغ در صورتحساب نیست")
        self.assertEqual(rejected.status, S.REJECTED)
        self.assertTrue(SubscriptionInvoice.objects.get(pk=self.invoice.pk).is_payable)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=claim.subscription_attempt_id).status, SubscriptionPaymentAttempt.Status.FAILED)
        with self.assertRaises(mcs.ClaimError):
            self.approve(rejected)
        self.assertNotEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)

    def test_the_owner_can_cancel_only_their_own_pending_claim(self):
        claim = self.claim()
        stranger = User.objects.create_user(username="stranger", password="x", is_staff=True)
        with self.assertRaises(mcs.ClaimError):
            mcs.cancel_claim(claim, user=stranger)
        cancelled = mcs.cancel_claim(claim, user=self.owner)
        self.assertEqual(cancelled.status, S.CANCELLED)
        with self.assertRaises(mcs.ClaimError):
            mcs.cancel_claim(claim, user=self.owner)
        with self.assertRaises(mcs.ClaimError):
            self.approve(claim)

    def test_money_confirmed_but_invoice_already_paid_elsewhere_becomes_needs_action_without_a_second_effect(self):
        claim = self.claim()
        from apps.billing.services.confirmation_service import mark_invoice_paid_manually
        SubscriptionPaymentAttempt.objects.filter(pk=claim.subscription_attempt_id).update(status=SubscriptionPaymentAttempt.Status.PENDING)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        mark_invoice_paid_manually(invoice, actor=self.finance, note="paid by wire")
        before = SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid
        result = self.approve(claim)
        self.assertEqual(result.status, S.NEEDS_ACTION)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, before)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=claim.subscription_attempt_id).failure_code, "duplicate_payment")


class SmsCardToCardTests(CardToCardBase):
    CREDITS, PRICE_SMS = 400, 120_000

    def setUp(self):
        super().setUp()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 25})
        self.package = SmsPackage.objects.create(name="بسته ۴۰۰", credit_amount=self.CREDITS, price=self.PRICE_SMS)
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)

    def sms_claim(self, ref="SMS-TRK-998877"):
        return mcs.submit_claim(user=self.owner, store=self.store, reference=ref, transferred_at=timezone.now(), sms_purchase=self.purchase)

    def credits(self):
        return SmsBalance.objects.get(store=self.store).credits

    def test_submission_adds_no_credit_and_approval_adds_it_exactly_once_with_a_ledger_trail(self):
        claim = self.sms_claim()
        self.assertEqual((claim.expected_amount, claim.purchase_type), (Decimal(self.PRICE_SMS), "sms_package"))
        self.assertEqual(self.credits(), 25)
        self.assertEqual(SmsCreditLedger.objects.count(), 0)
        for _ in range(3):
            self.approve(claim)
        self.assertEqual(self.credits(), 25 + self.CREDITS)
        entry = SmsCreditLedger.objects.get()
        self.assertEqual((entry.delta, entry.balance_before, entry.balance_after, entry.payment_attempt_id, entry.actor_id),
                         (self.CREDITS, 25, 25 + self.CREDITS, claim.sms_attempt_id, self.finance.pk))
        self.assertEqual(SmsPackagePurchase.objects.get(pk=self.purchase.pk).status, SmsPackagePurchase.Status.COMPLETED)
        self.assertEqual(SmsPackagePaymentAttempt.objects.get(pk=claim.sms_attempt_id).status, SmsPackagePaymentAttempt.Status.SUCCEEDED)

    def test_wrong_amounts_never_credit_and_rejection_leaves_the_purchase_payable(self):
        claim = self.sms_claim()
        for amount in (self.PRICE_SMS - 1, self.PRICE_SMS + 1):
            with self.assertRaises(mcs.ClaimError):
                self.approve(claim, amount=amount)
        mcs.reject_claim(claim, reviewer=self.finance, reason="رسید جعلی به نظر می‌رسد")
        self.assertEqual(self.credits(), 25)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=self.purchase.pk).status, SmsPackagePurchase.Status.PENDING)
        self.sms_claim(ref="SMS-TRK-CORRECTED-1")                      # a corrected claim is possible

    def test_approval_after_a_manual_completion_never_double_credits(self):
        claim = self.sms_claim()
        balance_service.complete_purchase(purchase=self.purchase, actor=self.finance)
        self.assertEqual(self.credits(), 25 + self.CREDITS)
        result = self.approve(claim)
        self.assertEqual(result.status, S.NEEDS_ACTION)
        self.assertEqual(self.credits(), 25 + self.CREDITS)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)
        self.assertEqual(SmsPackagePaymentAttempt.objects.get(pk=claim.sms_attempt_id).failure_code, "purchase_completed")

    def test_authorised_refund_reverses_the_credits_once_and_the_money_refund_stays_a_manual_step(self):
        claim = self.sms_claim()
        self.approve(claim)
        refunded, result = sms_svc.refund_purchase(self.purchase, actor=self.finance, reason="درخواست مالک")
        self.assertEqual(refunded.status, SmsPackagePurchase.Status.REFUNDED)
        self.assertEqual(self.credits(), 25)
        self.assertFalse(result.succeeded)
        self.assertIn("platform_card-manual-refund", result.provider_refund_id)
        self.assertEqual(list(SmsCreditLedger.objects.order_by("id").values_list("kind", "delta")), [("purchase", self.CREDITS), ("purchase_reversal", -self.CREDITS)])
        with self.assertRaises(sms_svc.SmsRefundError):
            sms_svc.refund_purchase(SmsPackagePurchase.objects.get(pk=self.purchase.pk), actor=self.finance, reason="تکرار")


class SubscriptionRefundTests(CardToCardBase):
    def test_refund_lifecycle_uses_the_existing_ledger_and_stays_manual_until_completed(self):
        claim = self.claim()
        self.approve(claim)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        refund = refund_service.request_refund(invoice, amount=invoice.amount_paid, reason="درخواست مالک", requested_by=self.finance, idempotency_key="c2c-rf-1")
        self.assertEqual(refund.status, "pending")                                          # honest: money goes back by manual transfer
        self.assertEqual(refund.provider, "platform_card")
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
        done = refund_service.complete_refund_manually(refund, actor=self.finance)
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(refund_service.request_refund(invoice, amount=invoice.amount_paid, reason="درخواست مالک", requested_by=self.finance, idempotency_key="c2c-rf-1").pk, refund.pk)
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal("1"), reason="بیش از حد", requested_by=self.finance)


class ReconcileDoesNotTouchManualAttemptsTests(CardToCardBase):
    def test_the_automatic_reconcile_job_never_verifies_or_changes_manual_card_attempts(self):
        from io import StringIO
        from django.core.management import call_command

        claim = self.claim()
        SubscriptionPaymentAttempt.objects.filter(pk=claim.subscription_attempt_id).update(created_at=timezone.now() - timedelta(hours=2))
        out = StringIO()
        call_command("reconcile_platform_payments", stdout=out)
        self.assertIn("checked=0", out.getvalue())
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)


class ExpiryCommandTests(CardToCardBase):
    def test_the_expiry_command_expires_only_overdue_claims_and_dry_run_changes_nothing(self):
        from io import StringIO
        from django.core.management import call_command

        claim = self.claim(ref="CMD-EXPIRE-0001")
        out = StringIO()
        call_command("expire_platform_card_claims", stdout=out)
        self.assertIn("expired=0", out.getvalue())
        Claim.objects.filter(pk=claim.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("expire_platform_card_claims", "--dry-run", stdout=out)
        self.assertIn("due=1", out.getvalue())
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)
        out = StringIO()
        call_command("expire_platform_card_claims", stdout=out)
        self.assertIn("expired=1", out.getvalue())
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.EXPIRED)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, 0)
        self.assertTrue(SubscriptionInvoice.objects.get(pk=self.invoice.pk).is_payable)

