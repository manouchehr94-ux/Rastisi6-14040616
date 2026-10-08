"""Section 19 — end-to-end journeys through the real HTTP interface,
chaining together everything built this session (Sections 3-16) into one
realistic lifecycle, plus a cross-cutting adversarial sweep. Individual
adversarial cases (wrong OTP, tampered tokens, cross-store leakage, open
redirects, replay-safety) are already covered exhaustively in each
section's own test file; this module's job is to prove the sections
actually compose into one coherent journey, not to re-litigate each
building block in isolation."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.providers.manual import SIGNATURE_HEADER, TIMESTAMP_HEADER
from apps.notifications.models import NotificationOutbox
from apps.portal.models import OwnerOtpChallenge
from apps.stores.models import Store, StoreDomain, StoreMembership, StoreOwnershipTransfer
from apps.subscriptions.models import PlanVersion, StoreSubscription

User = get_user_model()
_HOST = "rastisi.localhost"
_BILLING_WEBHOOK_SECRET = "e2e-journey-billing-webhook-secret"


def _confirm_billing_attempt_via_signed_webhook(attempt, *, event_id):
    """The only registered payment provider (apps.billing's "manual") never
    auto-succeeds — real confirmation always comes from a signed provider
    webhook or an explicit Platform Admin action, never from the browser
    simply returning to the portal. This simulates the former, exactly the
    way a real gateway's callback would."""
    body = json.dumps({
        "event_id": event_id, "event_type": "payment.succeeded",
        "session_id": f"manual-sess-{attempt.public_token}", "provider_payment_id": f"pay-{event_id}",
        "amount": str(attempt.amount), "currency": attempt.currency,
    }).encode()
    ts = str(int(time.time()))
    sig = hmac.new(_BILLING_WEBHOOK_SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return Client().post(
        reverse("billing:webhook", args=["manual"]), data=body, content_type="application/json",
        **{"HTTP_" + SIGNATURE_HEADER.upper().replace("-", "_"): sig,
           "HTTP_" + TIMESTAMP_HEADER.upper().replace("-", "_"): ts},
    )


def _advance_past_step_up_rate_window(phone):
    """This journey performs several step-up OTP requests for the same
    phone back-to-back, which is unrealistic for a real owner and would
    otherwise trip the genuine per-phone rate limiter (3 per 600s,
    ``owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW``) — a real security
    control we must not weaken. Backdating the phone's own STEP_UP OTP
    history simulates the real minutes that would elapse between actions."""
    OwnerOtpChallenge.objects.filter(phone=phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP).update(
        created_at=timezone.now() - timedelta(seconds=700),
    )


class _FakeTXTRecord:
    def __init__(self, *chunks):
        self.strings = [chunk.encode() for chunk in chunks]


def _dns_target():
    return "apps.stores.services.domain_verification_service.dns.resolver.resolve"


@override_settings(
    ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_DEFAULT_PLAN_CODE="trial",
    RASTISI_BILLING_WEBHOOK_SECRET=_BILLING_WEBHOOK_SECRET, RASTISI_BILLING_PROVIDER="manual",
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class JourneyATestCase(TestCase):
    """Journey A: register → auto-provision → onboard → purchase →
    permanent handle → custom domain → ownership transfer → deletion."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        call_command("seed_default_plans", stdout=StringIO())
        self._codes = iter([
            "111111",  # registration OTP
            "222222",  # step-up: subscription purchase
            "333333",  # step-up: permanent handle claim
            "444444",  # step-up: custom domain activation
            "555555",  # step-up: ownership transfer initiate
            "666666",  # target's own OTP to accept the transfer
            "777777",  # step-up: store deletion request (by the NEW owner)
        ])
        import apps.portal.services.owner_otp_service as svc

        self._original_generate_code = svc._generate_code
        svc._generate_code = lambda: next(self._codes)
        self.addCleanup(setattr, svc, "_generate_code", self._original_generate_code)

    def test_full_lifecycle(self):
        # --- Register: phone + OTP, auto-provisions exactly one trial Store ---
        self.client.post("/register/", {"full_name": "مالکِ اول", "phone": "09121400001", "accept_terms": "1"}, HTTP_HOST=_HOST)
        response = self.client.post("/verify/", {"phone": "09121400001", "code": "111111"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/onboarding/", response["Location"])

        owner = User.objects.get(username="09121400001")
        membership = StoreMembership.objects.get(user=owner, role=StoreMembership.Role.OWNER)
        store = membership.store
        trial_domain = store.domains.get(is_primary=True)

        # --- Storefront is private until onboarding completes ---
        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST=trial_domain.hostname).status_code, 403)

        # --- Complete the onboarding wizard (identity, skip industry/branding, publish) ---
        base = f"/app/stores/{store.public_id}/onboarding"
        self.client.post(f"{base}/identity/", {"name": "فروشگاهِ سفر کامل"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/industry/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/branding/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/review/", {}, HTTP_HOST=_HOST)

        store.refresh_from_db()
        self.assertIsNotNone(store.onboarding_completed_at)
        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST=trial_domain.hostname).status_code, 200)

        # --- Purchase a paid plan (step-up gated; apps.billing is the one
        # billing system — confirmation only ever comes from a signed
        # webhook, never the browser's own return) ---
        version = PlanVersion.objects.get(plan__code="basic", status=PlanVersion.Status.PUBLISHED)
        checkout_response = self.client.post(
            f"/app/stores/{store.public_id}/billing/checkout/{version.pk}/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(checkout_response, f"/app/stores/{store.public_id}/billing/step-up/")
        step_up_response = self.client.post(
            f"/app/stores/{store.public_id}/billing/step-up/", {"code": "222222"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(step_up_response.status_code, 302)
        attempt_token = step_up_response["Location"].rstrip("/").rsplit("/", 1)[-1]
        attempt = SubscriptionPaymentAttempt.objects.get(public_token=attempt_token)
        webhook_response = _confirm_billing_attempt_via_signed_webhook(attempt, event_id="e2e-basic-purchase")
        self.assertEqual(webhook_response.status_code, 200)

        subscription = StoreSubscription.objects.get(store=store, is_current=True)
        self.assertEqual(subscription.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(subscription.plan_version.plan.code, "basic")

        # --- Claim the permanent handle (step-up gated); trial hostname retires ---
        _advance_past_step_up_rate_window("09121400001")
        handle_checkout = self.client.post(
            f"/app/stores/{store.public_id}/handle/", {"label": "safarekamel"}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(handle_checkout, f"/app/stores/{store.public_id}/handle/step-up/")
        self.client.post(
            f"/app/stores/{store.public_id}/handle/step-up/", {"code": "333333"}, HTTP_HOST=_HOST,
        )
        handle_domain = StoreDomain.objects.get(store=store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN)
        self.assertEqual(handle_domain.hostname, "safarekamel.rastisi.ir")
        self.assertTrue(handle_domain.is_primary)
        trial_domain.refresh_from_db()
        self.assertFalse(trial_domain.is_primary)
        self.assertIsNotNone(trial_domain.retired_at)
        # A security notification was queued for the handle claim (Section 16).
        self.assertTrue(NotificationOutbox.objects.filter(recipient_user=owner, is_security=True).exists())

        # --- Add, verify (mocked DNS), and activate a custom domain ---
        self.client.post(
            f"/app/stores/{store.public_id}/domains/", {"action": "add", "hostname": "shop.example.com"},
            HTTP_HOST=_HOST,
        )
        custom_domain = StoreDomain.objects.get(store=store, hostname="shop.example.com")
        self.client.post(
            f"/app/stores/{store.public_id}/domains/{custom_domain.pk}/begin-verify/", HTTP_HOST=_HOST,
        )
        custom_domain.refresh_from_db()
        with patch(_dns_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={custom_domain.verification_token}")]
            self.client.post(f"/app/stores/{store.public_id}/domains/{custom_domain.pk}/check/", HTTP_HOST=_HOST)
        custom_domain.refresh_from_db()
        self.assertEqual(custom_domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)

        # Site Delivery 2B: delivery readiness is separate from TXT ownership.
        custom_domain.routing_status = StoreDomain.RoutingStatus.CONNECTED
        custom_domain.routing_checked_at = timezone.now()
        custom_domain.tls_status = StoreDomain.TlsStatus.READY
        custom_domain.tls_checked_at = timezone.now()
        custom_domain.save(update_fields=[
            "routing_status", "routing_checked_at",
            "tls_status", "tls_checked_at", "updated_at",
        ])

        _advance_past_step_up_rate_window("09121400001")
        activate_response = self.client.post(
            f"/app/stores/{store.public_id}/domains/{custom_domain.pk}/activate/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(activate_response, f"/app/stores/{store.public_id}/domains/activate/step-up/")
        self.client.post(
            f"/app/stores/{store.public_id}/domains/activate/step-up/", {"code": "444444"}, HTTP_HOST=_HOST,
        )
        custom_domain.refresh_from_db()
        self.assertTrue(custom_domain.is_primary)
        handle_domain.refresh_from_db()
        self.assertFalse(handle_domain.is_primary)
        # Permanent Rastisi handle remains a live alias after custom-domain activation.
        # It is no longer primary, but it must not be retired so public requests can
        # 301 to the active custom domain while /admin-portal/ stays on Rastisi.
        self.assertIsNone(handle_domain.retired_at)

        with self.settings(ALLOWED_HOSTS=["shop.example.com", _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST="shop.example.com").status_code, 200)

        # --- Transfer ownership to a new phone (two-party OTP) ---
        _advance_past_step_up_rate_window("09121400001")
        transfer_checkout = self.client.post(
            f"/app/stores/{store.public_id}/transfer/", {"target_phone": "09121400002"}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(transfer_checkout, f"/app/stores/{store.public_id}/transfer/step-up/")
        self.client.post(
            f"/app/stores/{store.public_id}/transfer/step-up/", {"code": "555555"}, HTTP_HOST=_HOST,
        )
        transfer = StoreOwnershipTransfer.objects.get(store=store)
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.PENDING)

        target_client = self.client_class()
        target_client.post(f"/transfer/accept/{transfer.token}/", {"action": "request_code"}, HTTP_HOST=_HOST)
        accept_response = target_client.post(
            f"/transfer/accept/{transfer.token}/", {"action": "verify_code", "code": "666666"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(accept_response.status_code, 302)

        new_owner = User.objects.get(username="09121400002")
        new_owner_membership = StoreMembership.objects.get(store=store, user=new_owner)
        self.assertEqual(new_owner_membership.role, StoreMembership.Role.OWNER)
        old_owner_membership = StoreMembership.objects.get(store=store, user=owner)
        self.assertEqual(old_owner_membership.role, StoreMembership.Role.ADMINISTRATOR)
        self.assertIn("_auth_user_id", target_client.session)
        self.assertEqual(int(target_client.session["_auth_user_id"]), new_owner.pk)

        # --- The NEW owner requests deletion, then cancels it ---
        _advance_past_step_up_rate_window("09121400002")
        delete_checkout = target_client.post(
            f"/app/stores/{store.public_id}/delete/", {"typed_confirmation": store.slug}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(delete_checkout, f"/app/stores/{store.public_id}/delete/step-up/")
        target_client.post(
            f"/app/stores/{store.public_id}/delete/step-up/", {"code": "777777"}, HTTP_HOST=_HOST,
        )
        store.refresh_from_db()
        self.assertEqual(store.status, Store.Status.CLOSED)
        self.assertIsNotNone(store.deletion_requested_at)

        # A CLOSED store's domain never resolves at all (fail-closed at the
        # host-resolution layer itself, before publication-state is even
        # consulted) — 404, not 403, so a deleted Store's existence is
        # never leaked either.
        with self.settings(ALLOWED_HOSTS=["shop.example.com", _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST="shop.example.com").status_code, 404)

        target_client.post(f"/app/stores/{store.public_id}/delete/cancel/", HTTP_HOST=_HOST)
        store.refresh_from_db()
        self.assertEqual(store.status, Store.Status.ACTIVE)
        self.assertIsNone(store.deletion_requested_at)
        with self.settings(ALLOWED_HOSTS=["shop.example.com", _HOST, "testserver"]):
            self.assertEqual(self.client.get("/", HTTP_HOST="shop.example.com").status_code, 200)

        # Original owner (now demoted, not deleted/removed) never lost their account.
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        self.assertTrue(StoreMembership.objects.filter(store=store, user=owner, status="active").exists())


@override_settings(
    ALLOWED_HOSTS=[_HOST, "testserver"],
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class AdversarialSweepTests(TestCase):
    """A stranger — authenticated, but with no membership at all on this
    Store — must be refused (never 200, never leak existence via a
    different status per endpoint) on every sensitive owner-facing
    surface in one pass."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاهِ هدف", slug="adversarial-target-store", admin_subdomain="adversarial-target-store",
            status=Store.Status.ACTIVE,
        )
        self.owner = User.objects.create_user(username="09121400010", password="a-very-strong-pass-1")
        from django.utils import timezone

        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.stranger = User.objects.create_user(username="09121400099", password="a-very-strong-pass-1")
        self.client.force_login(self.stranger)

    def test_stranger_is_refused_on_every_sensitive_surface(self):
        store_id = self.store.public_id
        endpoints = [
            ("get", f"/app/stores/{store_id}/onboarding/"),
            ("get", f"/app/stores/{store_id}/billing/"),
            ("get", f"/app/stores/{store_id}/handle/"),
            ("get", f"/app/stores/{store_id}/domains/"),
            ("get", f"/app/stores/{store_id}/delete/"),
            ("get", f"/app/stores/{store_id}/transfer/"),
            ("post", f"/app/stores/{store_id}/enter-admin/"),
        ]
        for method, path in endpoints:
            caller = getattr(self.client, method)
            response = caller(path, HTTP_HOST=_HOST)
            self.assertEqual(response.status_code, 404, f"{method.upper()} {path} should 404 for a stranger")

    def test_anonymous_user_never_reaches_any_sensitive_surface_either(self):
        self.client.logout()
        store_id = self.store.public_id
        for path in [
            f"/app/stores/{store_id}/billing/", f"/app/stores/{store_id}/handle/",
            f"/app/stores/{store_id}/delete/", f"/app/stores/{store_id}/transfer/",
        ]:
            response = self.client.get(path, HTTP_HOST=_HOST)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response["Location"])

    def test_unauthenticated_merchant_admin_request_redirects_centrally_not_locally(self):
        admin_host = f"{self.store.admin_subdomain}.rastisi.ir"
        with self.settings(ALLOWED_HOSTS=[admin_host, _HOST, "testserver"]):
            self.client.logout()
            response = self.client.get("/admin-portal/", HTTP_HOST=admin_host)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response["Location"])
        self.assertIn("admin_return=", response["Location"])
