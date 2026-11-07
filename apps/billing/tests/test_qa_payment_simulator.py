"""LOCAL-QA payment simulator for the platform subscription checkout (2026-11-08).

Proves: (1) it is inert unless every guard holds, (2) it makes NO network call, (3) the OFFICIAL path is kept — invoice → checkout → attempt → public
callback → server-side verify → confirmation → activation — for the four scenarios success / failure / cancel / repeated callback, with the QA plan
«123» at 9,600,000 toman yearly, (4) roles / other-store isolation / no activation without a verified payment still hold."""

from urllib.parse import urlsplit
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers import qa_simulator
from apps.billing.tests.test_trial_purchase_flow import PW, make_owner
from apps.subscriptions.models import Plan, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent, plan_service as ps
from apps.subscriptions.tests.test_pricing_dynamic import make_plan
from shop_core.env_config import resolve_qa_payment_simulator

User = get_user_model()


def sim_settings():
    return dict(DEBUG=True, RASTISI_PRODUCTION_MODE=False, RASTISI_QA_PAYMENT_SIMULATOR=True,
                RASTISI_QA_SIMULATOR_DB_CONFIRM=connection.settings_dict["NAME"], ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")


class GuardTests(TestCase):
    def test_inactive_by_default(self):
        self.assertFalse(qa_simulator.is_active())

    def test_every_guard_is_required(self):
        with self.settings(**sim_settings()):
            self.assertTrue(qa_simulator.is_active())
            for bad in ({"DEBUG": False}, {"RASTISI_PRODUCTION_MODE": True}, {"RASTISI_QA_PAYMENT_SIMULATOR": False},
                        {"RASTISI_QA_SIMULATOR_DB_CONFIRM": "some-other-database"}):
                with self.subTest(bad=bad), self.settings(**bad):
                    self.assertFalse(qa_simulator.is_active())

    def test_the_database_must_be_an_isolated_qa_one(self):
        with self.settings(**sim_settings()):
            with mock.patch.dict(connection.settings_dict, {"NAME": "rastisi_production"}):
                self.assertFalse(qa_simulator.is_active())
            with mock.patch.dict(connection.settings_dict, {"NAME": "rastisi_qa_trial_purchase_20261107"}), self.settings(RASTISI_QA_SIMULATOR_DB_CONFIRM=""):
                self.assertTrue(qa_simulator.is_active())               # the name itself says «qa»

    def test_startup_refuses_the_flag_when_debug_is_off(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_qa_payment_simulator(False, environ={"RASTISI_QA_PAYMENT_SIMULATOR": "1"})
        self.assertTrue(resolve_qa_payment_simulator(True, environ={"RASTISI_QA_PAYMENT_SIMULATOR": "1"}))
        self.assertFalse(resolve_qa_payment_simulator(False, environ={}))

    def test_views_and_command_are_inert_when_inactive(self):
        self.assertEqual(Client().get("/billing/qa-simulator/start/70001/").status_code, 404)
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("qa_enable_payment_simulator")
        with self.assertRaises(RuntimeError):
            qa_simulator.handle("request", {"amount": 1, "orderId": "x", "callbackUrl": "http://x/"})


class SimulatedCheckoutBase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.enterContext(self.settings(**sim_settings()))
        self.enterContext(mock.patch("apps.billing.providers.zibal.requests.post", side_effect=AssertionError("NETWORK CALL: the simulator must not use HTTP")))
        call_command("qa_enable_payment_simulator")
        _p, draft = make_plan("123", base=800_000, order=1, publish=False)
        ps.set_formula_pricing(draft, monthly_price=800_000, discounts={"quarterly": 0, "semiannual": 0, "yearly": 0})
        ps.publish_plan_version(draft)
        self.version = Plan.objects.get(code="123").versions.get(status="published")
        self.owner, self.store = make_owner("simpay@example.com", "QA Trial 30")
        self.host = f"{self.store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        self.c = Client(HTTP_HOST=self.host)
        self.c.login(username=self.owner.username, password=PW)

    def start_purchase(self, interval="yearly", client=None, version=None):
        c, version = client or self.c, version or self.version
        token = c.post(reverse("dashboard:subscription-plan-preview"), {"version_id": version.pk, "billing_interval": interval}).context["preview"]["token"]
        c.post(reverse("dashboard:subscription-plan-execute"), {"version_id": version.pk, "preview_token": token, "billing_interval": interval})
        return SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").latest("pk")

    def pay(self, invoice, client=None):
        """POST the unified checkout «pay»: returns (attempt, absolute simulator URL)."""
        response = (client or self.c).post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"})
        attempt = SubscriptionPaymentAttempt.objects.filter(invoice=invoice).latest("pk")
        return attempt, response

    def sim_path(self, response):
        """The redirect target of the checkout: the local bank page. It may sit behind a tiny bridge page — find the URL in the response."""
        location = response.headers.get("Location", "")
        if not location:
            body = response.content.decode()
            import re

            m = re.search(r"https?://[^\"' <]+/billing/qa-simulator/start/\d+/", body)
            location = m.group(0) if m else ""
        return location

    def decide(self, url, outcome):
        path = urlsplit(url).path
        page = Client(HTTP_HOST=urlsplit(url).netloc)
        return page, page.post(path, {"outcome": outcome})

    def callback(self, redirect_response):
        url = redirect_response.headers["Location"]
        parts = urlsplit(url)
        return Client(HTTP_HOST=parts.netloc).get(f"{parts.path}?{parts.query}")

    def current(self):
        return ent.get_current_subscription(self.store)


class OfficialFlowScenarioTests(SimulatedCheckoutBase):
    def test_the_invoice_is_9_600_000_toman_and_the_gateway_session_is_96_000_000_rial(self):
        invoice = self.start_purchase("yearly")
        self.assertEqual(int(invoice.grand_total), 9_600_000)
        attempt, response = self.pay(invoice)
        self.assertEqual(int(attempt.amount), 9_600_000)
        url = self.sim_path(response)
        self.assertIn("/billing/qa-simulator/start/", url)
        page = Client(HTTP_HOST=urlsplit(url).netloc).get(urlsplit(url).path)
        self.assertContains(page, "9,600,000")
        self.assertContains(page, "هیچ درخواستی به بانک ارسال نمی‌شود")
        self.assertEqual(cache.get(f"qa-sim:zibal:{attempt.provider_session_id}")["amount"], 96_000_000)

    def test_success_activates_through_the_official_verification_and_a_repeated_callback_changes_nothing(self):
        invoice = self.start_purchase("yearly")
        attempt, response = self.pay(invoice)
        self.assertEqual((self.current().plan_version.plan.code, self.current().status), ("trial", "trialing"))        # nothing before payment
        _page, ok = self.decide(self.sim_path(response), "success")
        self.callback(ok)
        for _ in range(3):
            self.callback(ok)                                                                         # replayed callbacks
        sub = self.current()
        self.assertEqual((sub.plan_version_id, sub.status, sub.billing_interval), (self.version.pk, StoreSubscription.Status.ACTIVE, "yearly"))
        invoice.refresh_from_db()
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, 9_600_000))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription=sub, event_type="activated").count(), 1)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_failed_and_cancelled_payments_never_activate_and_a_retry_still_works(self):
        invoice = self.start_purchase("yearly")
        for outcome in ("failed", "cancel"):
            with self.subTest(outcome=outcome):
                attempt, response = self.pay(invoice)
                _p, redirect = self.decide(self.sim_path(response), outcome)
                self.callback(redirect)
                self.callback(redirect)
                self.assertEqual((self.current().plan_version.plan.code, self.current().status), ("trial", "trialing"))
                invoice.refresh_from_db()
                self.assertNotEqual(invoice.status, SubscriptionInvoice.Status.PAID)
                self.assertEqual(int(invoice.amount_paid), 0)
        attempt, response = self.pay(invoice)                                                         # a new attempt on the SAME invoice
        _p, ok = self.decide(self.sim_path(response), "success")
        self.callback(ok)
        self.assertEqual(self.current().plan_version_id, self.version.pk)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_a_browser_success_return_without_a_paid_state_is_not_proof(self):
        invoice = self.start_purchase("yearly")
        attempt, _response = self.pay(invoice)
        Client().get(f"/billing/return/{attempt.public_token}/?success=1&status=2&trackId={attempt.provider_session_id}")   # forged return, bank never said «paid»
        self.assertEqual((self.current().plan_version.plan.code, self.current().status), ("trial", "trialing"))

    def test_all_four_periods_price_correctly(self):
        for interval, amount in {"monthly": 800_000, "quarterly": 2_400_000, "semiannual": 4_800_000, "yearly": 9_600_000}.items():
            self.assertEqual(int(self.version.price_for(interval)), amount)


class SecurityStillHoldsTests(SimulatedCheckoutBase):
    def test_another_stores_owner_cannot_pay_or_see_this_invoice(self):
        invoice = self.start_purchase("yearly")
        other_owner, other_store = make_owner("simother@example.com", "فروشگاه دیگر")
        other = Client(HTTP_HOST=f"{other_store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")
        other.login(username=other_owner.username, password=PW)
        self.assertEqual(other.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])).status_code, 404)
        self.assertEqual(other.post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"}).status_code, 404)
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).exists())

    def test_non_owner_roles_cannot_start_a_purchase(self):
        from django.utils import timezone

        from apps.stores.models import StoreMembership

        for role in (StoreMembership.Role.ADMINISTRATOR, StoreMembership.Role.ANALYST):
            u = User.objects.create_user(username=f"sim-{role}@example.com", password=PW, is_staff=True)
            StoreMembership.objects.create(store=self.store, user=u, role=role, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
            c = Client(HTTP_HOST=self.host)
            c.login(username=u.username, password=PW)
            self.assertEqual(c.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.version.pk, "preview_token": "x", "billing_interval": "yearly"}).status_code, 403)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())

    def test_the_simulator_page_is_inert_in_production_mode_even_with_a_known_track(self):
        invoice = self.start_purchase("yearly")
        attempt, response = self.pay(invoice)
        url = self.sim_path(response)
        with self.settings(RASTISI_PRODUCTION_MODE=True):
            self.assertEqual(Client(HTTP_HOST=urlsplit(url).netloc).get(urlsplit(url).path).status_code, 404)
            self.assertEqual(Client(HTTP_HOST=urlsplit(url).netloc).post(urlsplit(url).path, {"outcome": "success"}).status_code, 404)
        self.assertEqual((self.current().plan_version.plan.code, self.current().status), ("trial", "trialing"))
