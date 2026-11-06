"""Zero-price SMS packages are a ONE-TIME grant per store and package (final validation, item 1).

The exploit this closes: a store member could POST the purchase endpoint for an active zero-price package again after each completion and mint unlimited SMS credits
(every cycle created a fresh pending purchase and `settle_free_purchase` credited it). Policy: a store may redeem a given zero-price package once; a refund does not reopen it;
paid packages are unaffected; existing completed purchases and their ledger rows are never altered (only NEW repeats are refused). A repeatable cadence (e.g. monthly) needs an
owner decision and stays disabled until then. Platform finance can still grant credits manually through the existing audited ``complete_purchase`` path."""

import threading
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse

from apps.billing.services import sms_purchase_payment_service
from apps.billing.services.payment_flow_service import PaymentFlowError
from apps.billing.tests.test_platform_checkout import CheckoutBase, OTHER_HOST, OWNER_HOST, User
from apps.core.models import AuditLogEntry
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership

BUY = "dashboard:settings-sms-package-purchase"


class FreePackagePolicyTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.free = SmsPackage.objects.create(name="هدیه ۵۰", credit_amount=50, price=0)

    def credits(self, store=None):
        return SmsBalance.objects.get(store=store or self.store).credits

    def redeem(self, client=None, package=None):
        """The real merchant journey: POST the purchase endpoint, follow to checkout, settle without a gateway."""
        client = client or self.owner_client
        response = client.post(reverse(BUY), {"package_id": (package or self.free).pk})
        match = SmsPackagePurchase.objects.filter(package=package or self.free).order_by("-pk").first()
        if match is not None and match.status == SmsPackagePurchase.Status.PENDING and response.status_code == 302 and "checkout" in response["Location"]:
            client.post(reverse("dashboard:platform-checkout-pay", args=["sms", match.pk]), {"method": "free"})
        return response

    def test_first_redemption_grants_once_and_is_recorded(self):
        before = self.credits()
        self.redeem()
        self.assertEqual(self.credits(), before + 50)
        purchase = SmsPackagePurchase.objects.get(store=self.store, package=self.free)
        self.assertEqual(purchase.status, SmsPackagePurchase.Status.COMPLETED)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase, delta=50).count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.sms_free_purchase_settled", store=self.store).count(), 1)

    def test_the_exploit_repeating_the_purchase_endpoint_no_longer_mints_credits(self):
        before = self.credits()
        for _ in range(6):
            self.redeem()
        self.assertEqual(self.credits(), before + 50)                                         # was: before + 300
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free).count(), 1)
        self.assertEqual(SmsCreditLedger.objects.filter(store=self.store, purchase__package=self.free).count(), 1)
        blocked = AuditLogEntry.objects.filter(action_code="billing.sms_free_purchase_blocked", store=self.store)
        self.assertEqual(blocked.count(), 5)                                                   # redemption history: every refused repeat is on record
        self.assertIn("free_package_already_redeemed", blocked.first().after_summary)
        self.assertEqual(blocked.first().object_id, str(self.free.pk))

    def test_a_repeat_attempt_shows_a_clear_persian_message_and_creates_nothing(self):
        self.redeem()
        from django.contrib.messages import get_messages

        response = self.owner_client.post(reverse(BUY), {"package_id": self.free.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(balance_service.FREE_PACKAGE_ALREADY_REDEEMED_MESSAGE, [str(m) for m in get_messages(response.wsgi_request)])
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free).count(), 1)

    def test_two_requests_before_settling_share_one_pending_purchase(self):
        self.owner_client.post(reverse(BUY), {"package_id": self.free.pk})
        self.owner_client.post(reverse(BUY), {"package_id": self.free.pk})
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free).count(), 1)

    def test_a_stale_second_pending_row_cannot_be_settled_and_the_page_says_why(self):
        self.redeem()
        stale = SmsPackagePurchase.objects.create(store=self.store, package=self.free, credit_amount=50, price=0)   # e.g. created by an old bug / direct insert
        before = self.credits()
        with self.assertRaises(PaymentFlowError):
            sms_purchase_payment_service.settle_free_purchase(stale)
        page = self.owner_client.get(reverse("dashboard:platform-checkout", args=["sms", stale.pk]))
        self.assertNotContains(page, 'data-testid="settle-free"')
        self.assertContains(page, "قبلاً فعال شده است")
        self.owner_client.post(reverse("dashboard:platform-checkout-pay", args=["sms", stale.pk]), {"method": "free"})
        self.assertEqual(self.credits(), before)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=stale.pk).status, SmsPackagePurchase.Status.PENDING)

    def test_a_refunded_free_grant_does_not_reopen_redemption(self):
        self.redeem()
        purchase = SmsPackagePurchase.objects.get(store=self.store, package=self.free)
        SmsPackagePurchase.objects.filter(pk=purchase.pk).update(status=SmsPackagePurchase.Status.REFUNDED)
        before = self.credits()
        self.redeem()
        self.assertEqual(self.credits(), before)
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free).count(), 1)

    def test_canceling_an_unsettled_pending_does_not_consume_the_grant(self):
        self.owner_client.post(reverse(BUY), {"package_id": self.free.pk})
        balance_service.cancel_purchase(purchase=SmsPackagePurchase.objects.get(store=self.store, package=self.free))
        self.redeem()
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free, status="completed").count(), 1)

    def test_legacy_repeat_redemptions_already_on_record_are_left_exactly_as_they_are(self):
        for _ in range(2):                                                                      # history created before the policy existed
            p = SmsPackagePurchase.objects.create(store=self.store, package=self.free, credit_amount=50, price=0)
            balance_service.complete_purchase(purchase=p, note="legacy")
        credits, ledger = self.credits(), SmsCreditLedger.objects.filter(store=self.store).count()
        self.redeem()
        self.assertEqual((self.credits(), SmsCreditLedger.objects.filter(store=self.store).count()), (credits, ledger))
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free, status="completed").count(), 2)

    def test_each_store_and_each_free_package_gets_its_own_single_grant(self):
        second = SmsPackage.objects.create(name="هدیه دوم", credit_amount=20, price=0)
        before_a, before_b = self.credits(), self.credits(self.other)
        self.redeem()
        self.redeem(package=second)
        self.redeem(client=self.other_client)
        self.assertEqual((self.credits(), self.credits(self.other)), (before_a + 70, before_b + 50))

    def test_priced_packages_are_not_affected_by_the_policy(self):
        # repeat purchase of a PAID package is still allowed (it needs a real, server-verified payment each time)
        first = SmsPackagePurchase.objects.get(pk=self.purchase.pk)
        balance_service.complete_purchase(purchase=first)
        second = balance_service.request_purchase(store=self.store, package=self.package)          # (the view itself also needs a ready gateway for priced packages)
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.package).count(), 2)
        self.assertFalse(balance_service.free_package_already_redeemed(store=self.store, package=self.package))

    def test_a_member_without_sms_permission_and_anonymous_cannot_redeem(self):
        analyst = User.objects.create_user(username="pcout-analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=__import__("django.utils.timezone", fromlist=["now"]).now())
        from django.test import Client

        client = Client(HTTP_HOST=OWNER_HOST)
        client.login(username="pcout-analyst", password="pass12345")
        before = self.credits()
        response = client.post(reverse(BUY), {"package_id": self.free.pk})
        self.assertNotEqual(response.status_code, 200)
        anonymous = Client(HTTP_HOST=OWNER_HOST).post(reverse(BUY), {"package_id": self.free.pk})
        self.assertIn(anonymous.status_code, (301, 302, 403, 404))
        self.assertEqual(SmsPackagePurchase.objects.filter(store=self.store, package=self.free).count(), 0)
        self.assertEqual(self.credits(), before)

    def test_another_stores_owner_cannot_settle_my_pending_free_purchase(self):
        mine = balance_service.request_purchase(store=self.store, package=self.free)
        before_other = self.credits(self.other)
        self.other_client.post(reverse("dashboard:platform-checkout-pay", args=["sms", mine.pk]), {"method": "free"})
        self.assertEqual(SmsPackagePurchase.objects.get(pk=mine.pk).status, SmsPackagePurchase.Status.PENDING)
        self.assertEqual((self.credits(self.other), self.credits(self.store)), (before_other, 100))

    def test_platform_finance_can_still_grant_credits_manually_through_the_audited_path(self):
        p = SmsPackagePurchase.objects.create(store=self.store, package=self.package, credit_amount=500, price=0)
        before = self.credits()
        balance_service.complete_purchase(purchase=p, actor=self.finance, note="manual grant")
        self.assertEqual(self.credits(), before + 500)
        self.assertEqual(SmsCreditLedger.objects.get(purchase=p).actor_id, self.finance.pk)


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrent transactions")
class FreePackageConcurrencyTests(TransactionTestCase):
    databases = {"default"}

    def setUp(self):
        self.free = SmsPackage.objects.create(name="هدیه هم‌زمان", credit_amount=50, price=0)
        self.stores = []
        for tag in ("a", "b"):
            store = Store.objects.create(name=f"s{tag}", slug=f"fp-{tag}", admin_subdomain=f"fp-{tag}", status=Store.Status.ACTIVE)
            SmsBalance.objects.update_or_create(store=store, defaults={"credits": 10})
            self.stores.append(store)

    def _race(self, jobs):
        barrier, results = threading.Barrier(len(jobs)), []

        def worker(job):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                try:
                    results.append(("ok", job()))
                except (balance_service.FreePackageAlreadyRedeemed, PaymentFlowError) as exc:
                    results.append(("refused", type(exc).__name__))
            except Exception as exc:  # noqa: BLE001
                results.append(("error", repr(exc)))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(j,)) for j in jobs]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        return results

    def redeem(self, store):
        purchase = balance_service.request_purchase(store=store, package=self.free)
        sms_purchase_payment_service.settle_free_purchase(purchase)
        return purchase.pk

    def test_eight_simultaneous_redemptions_by_one_store_grant_exactly_once(self):
        a = self.stores[0]
        results = self._race([lambda: self.redeem(a)] * 8)
        self.assertFalse([r for r in results if r[0] == "error"], results)
        self.assertEqual(SmsBalance.objects.get(store=a).credits, 10 + 50)
        self.assertEqual(SmsPackagePurchase.objects.filter(store=a, package=self.free, status="completed").count(), 1)
        self.assertEqual(SmsCreditLedger.objects.filter(store=a, kind="purchase").count(), 1)
        self.assertEqual(SmsPackagePurchase.objects.filter(store=a, package=self.free).count(), 1)     # even the pending rows were not duplicated

    def test_simultaneous_redemptions_by_two_stores_each_grant_exactly_once(self):
        a, b = self.stores
        results = self._race([lambda: self.redeem(a), lambda: self.redeem(b)] * 4)
        self.assertFalse([r for r in results if r[0] == "error"], results)
        self.assertEqual((SmsBalance.objects.get(store=a).credits, SmsBalance.objects.get(store=b).credits), (60, 60))
