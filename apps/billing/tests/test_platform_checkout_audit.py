"""Phase-A audit reproductions (kept as regression tests). Each test asserts the behaviour a merchant/owner must get;
before the checkout unification they FAILED on the PR #43 baseline (see docs/platform-checkout/AUDIT_20261106.md)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.tests.platform_payment_support import (
    ready_platform_zarinpal,
)
from apps.billing.tests.test_platform_card_to_card import enable_platform_card, use_private_tmp
from apps.portal.models import PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import get_platform_configuration, update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service

User = get_user_model()
PORTAL = "rastisi.localhost"
PLATFORM = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[PORTAL, PLATFORM, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PortalPurchaseWithOnlyCardToCardTests(TestCase):
    """AUDIT-FINDING-1: with exactly one ready method the portal plans form posts no ``gateway``; the purchase then fell
    through to the *manual provider* attempt — a status page that can never be paid."""

    def setUp(self):
        use_private_tmp(self)
        self.addCleanup(cache.clear)
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(name="فروشگاه", slug="aud-store", admin_subdomain="aud-store")
        self.owner = User.objects.create_user(username="09120000001", password="pass-12345-x")
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        trial = Plan.objects.create(code="aud-trial", name="Trial", is_publicly_selectable=True)
        tv = PlanVersion.objects.create(plan=trial, version_number=1, status=PlanVersion.Status.PUBLISHED,
                                        billing_interval=PlanVersion.BillingInterval.NONE, display_price=0, trial_days=14)
        sub = subscription_service.create_subscription(self.store, tv, actor=self.owner)
        subscription_service.start_trial(sub, actor=self.owner)
        plan = Plan.objects.create(code="aud-pro", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
                                                  billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000)
        self.client.force_login(self.owner)

    def test_only_card_to_card_ready_never_creates_a_dead_manual_provider_attempt(self):
        enable_platform_card(self)
        self.client.post(f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=PORTAL)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(store=self.store, provider="manual").count(), 0)

    def test_no_method_ready_never_creates_a_dead_manual_provider_attempt(self):
        self.client.post(f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=PORTAL)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(store=self.store, provider="manual").count(), 0)


@override_settings(ALLOWED_HOSTS=[PORTAL, PLATFORM, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class LegacyZibalPageConflictTests(TestCase):
    """AUDIT-FINDING-2: the legacy page could only choose manual|zibal, so saving it silently reset the default chosen on
    /payments/gateways/ and disabled Zibal."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.staff = User.objects.create_user(username="aud-staff@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.client = Client(HTTP_HOST=PLATFORM)
        self.client.force_login(self.staff)

    def test_legacy_route_cannot_overwrite_the_canonical_default(self):
        ready_platform_zarinpal(self, default=True)
        self.assertEqual(get_platform_configuration().default_payment_provider, "zarinpal")
        self.client.post("/payments/zibal/", {"default_payment_provider": "manual", "zibal_merchant": ""})
        cache.clear()
        self.assertEqual(get_platform_configuration().default_payment_provider, "zarinpal")

    def test_legacy_route_does_not_keep_a_second_copy_of_the_credentials(self):
        self.client.post("/payments/gateways/", {"action": "save", "gateway_code": "zibal", "cred_merchant": "AUDIT-MERCHANT-1", "is_enabled": "on"})
        self.assertTrue(PlatformGatewayConfig.objects.filter(gateway_code="zibal").exists())
        legacy = get_platform_configuration()
        self.assertEqual(legacy.encrypted_zibal_credentials, "")
