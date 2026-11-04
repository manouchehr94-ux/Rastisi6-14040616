"""Admin Experience Upgrade — Part 6: card-to-card payment on the real payment infrastructure.

Covered: admin configuration, checkout selection, the customer's transfer form (last 4 digits + tracking number only), the order staying
UNPAID until an authorised admin approves, approval through the existing successful-payment lifecycle exactly once, reject + resubmit,
permissions, tenant isolation, CSRF, audit, and that Zibal / COD are unchanged."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import AuditLogEntry, ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.gateways import get_adapter
from apps.orders.models import (
    CardTransferSubmission, Order, PaymentAttempt, PaymentGateway, PaymentGatewayConfig, ShippingMethod, Transaction,
)
from apps.orders.services import card_transfer_service as svc
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.authorization import ROLE_PERMISSIONS
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "c2c-admin.rastisi.localhost"
SHOP_HOST = "c2c-shop.rastisi.localhost"
VALID_CARD = "6037997000000019"   # Luhn-valid test number


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class CardTransferBase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-c2c")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-c2c")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="prod-c2c", sku="C2C-1",
            price=Decimal("500000"), stock=20,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-c2c", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="کارت‌به‌کارت", slug="card_to_card", is_active=True)
        self.config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="card_to_card", is_active=True)
        self.config.set_credentials({"destination_card": VALID_CARD, "holder_name": "علی رضایی", "bank_name": "ملی"})
        self.config.save()
        self.user = User.objects.create_user(username="c2c-customer", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری", phone="09121110001")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121110001", province="تهران", city="تهران",
            postal_code="1111111111", full_address="خیابان آزادی",
        )
        ShopSettings.objects.filter(store=self.store).update(tax_enabled=False)

    def make_order(self, customer=None, gateway=None):
        customer = customer or self.customer
        cart = Cart.objects.create(customer=customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        return create_order_from_cart(
            cart, customer=customer, vendor=self.vendor, address=self.address, shipping_method=self.shipping,
            payment_gateway=gateway or self.gateway, store=self.store,
        )

    def submit(self, order, last4="1234", tracking="TRK12345"):
        return svc.submit(order.pk, store=self.store, customer=self.customer, source_last4=last4, tracking_number=tracking)


class AdapterAndConfigTests(CardTransferBase):
    def test_adapter_is_offline_manual_and_never_proves_payment(self):
        adapter = get_adapter("card_to_card")
        self.assertFalse(adapter.is_online)
        self.assertTrue(adapter.requires_manual_confirmation)
        result = adapter.verify_payment(track_id="x", expected_amount=Decimal("1"), currency="TOMAN", credentials={}, callback_data={"status": "1"})
        self.assertFalse(result.success)
        self.assertFalse(get_adapter("cod").requires_manual_confirmation if hasattr(get_adapter("cod"), "requires_manual_confirmation") else False)

    def test_credential_validation(self):
        adapter = get_adapter("card_to_card")
        self.assertEqual(adapter.validate_credentials({"destination_card": VALID_CARD, "holder_name": "x"}), [])
        self.assertTrue(adapter.validate_credentials({"destination_card": "1234567812345678", "holder_name": "x"}))     # fails Luhn
        self.assertTrue(adapter.validate_credentials({"destination_card": VALID_CARD, "holder_name": ""}))
        self.assertTrue(adapter.validate_credentials({"destination_card": VALID_CARD, "holder_name": "x", "sheba": "IR12"}))
        self.assertEqual(adapter.validate_credentials({"destination_card": "6037 9970-0000 0019", "holder_name": "x"}), [])

    def test_destination_is_stored_encrypted(self):
        self.assertNotIn(VALID_CARD, self.config.encrypted_credentials)
        self.assertEqual(svc.destination_for(self.config).card_grouped, "6037 9970 0000 0019")


class SubmitAndApproveTests(CardTransferBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="c2c-admin", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.admin, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())

    def test_order_is_not_paid_before_approval_and_state_is_under_review(self):
        order = self.make_order()
        self.assertEqual(svc.review_state(order), "awaiting_transfer")
        submission = self.submit(order)
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.status), (Order.PaymentStatus.PENDING, Order.Status.PENDING))
        self.assertEqual(svc.review_state(order), "under_review")
        self.assertEqual(svc.REVIEW_LABELS["under_review"], "در انتظار بررسی پرداخت")
        self.assertEqual(order.transactions.count(), 0)                                  # no payment record before approval
        self.assertEqual(submission.attempt.status, PaymentAttempt.Status.PENDING)       # never SUCCEEDED before approval
        self.assertEqual((submission.source_last4, submission.tracking_number, submission.destination_last4), ("1234", "TRK12345", "0019"))

    def test_only_four_digits_are_accepted_never_a_card_number_or_cvv(self):
        order = self.make_order()
        for bad in ("6037997000000019", "123", "12345", "abcd", "12 34 5"):
            with self.assertRaises(svc.CardTransferError, msg=bad):
                self.submit(order, last4=bad)
        for bad in ("6037997000000019", "ab", "<script>"):
            with self.assertRaises(svc.CardTransferError, msg=bad):
                self.submit(order, tracking=bad)
        self.assertEqual(CardTransferSubmission.objects.count(), 0)
        ok = self.submit(order, last4="۴۵۶۷", tracking="trk-۹۹۹")                        # Persian digits are normalised
        self.assertEqual((ok.source_last4, ok.tracking_number), ("4567", "trk-999"))

    def test_approval_marks_paid_once_through_the_lifecycle_and_advances_the_order(self):
        order = self.make_order()
        submission = self.submit(order)
        done = svc.approve(submission.pk, store=self.store, actor=self.admin)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PROCESSING)                          # same successful-payment path as Zibal
        tx = order.transactions.get()
        self.assertEqual((tx.method, tx.status, tx.ref_id, tx.confirmed_by_id, tx.amount), (Transaction.Method.CARD_TRANSFER, Transaction.Status.OK, "TRK12345", self.admin.pk, order.grand_total))
        self.assertEqual((done.status, done.transaction_id, done.reviewed_by_id), ("approved", tx.pk, self.admin.pk))
        self.assertEqual(PaymentAttempt.objects.get(pk=done.attempt_id).status, PaymentAttempt.Status.SUCCEEDED)
        with self.assertRaises(svc.AlreadyDecided):                                      # a second click / replay
            svc.approve(submission.pk, store=self.store, actor=self.admin)
        self.assertEqual(order.transactions.count(), 1)
        self.assertEqual(svc.review_state(order), "approved")
        self.assertEqual(AuditLogEntry.objects.filter(action_code="card_transfer.approved", store=self.store).count(), 1)

    def test_stale_second_actor_cannot_double_approve(self):
        order = self.make_order()
        submission = self.submit(order)
        stale_copy = CardTransferSubmission.objects.get(pk=submission.pk)               # a second admin loaded it before the first approved
        svc.approve(submission.pk, store=self.store, actor=self.admin)
        with self.assertRaises(svc.AlreadyDecided):
            svc.approve(stale_copy.pk, store=self.store, actor=self.admin)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 1)

    def test_reject_keeps_the_order_unpaid_and_allows_resubmission_up_to_the_cap(self):
        order = self.make_order()
        first = self.submit(order)
        with self.assertRaises(svc.CardTransferError):
            svc.reject(first.pk, store=self.store, actor=self.admin, reason=" ")           # a reason is required
        svc.reject(first.pk, store=self.store, actor=self.admin, reason="مبلغ واریزی با سفارش نمی‌خواند")
        order.refresh_from_db()
        self.assertEqual((order.payment_status, svc.review_state(order)), (Order.PaymentStatus.PENDING, "rejected"))
        self.assertEqual(order.transactions.count(), 0)
        with self.assertRaises(svc.AlreadyDecided):
            svc.reject(first.pk, store=self.store, actor=self.admin, reason="دوباره")
        second = self.submit(order, tracking="TRK-SECOND")
        self.assertEqual(svc.review_state(order), "under_review")
        with self.assertRaises(svc.CardTransferError):                                   # one open submission at a time
            self.submit(order, tracking="TRK-THIRD")
        svc.reject(second.pk, store=self.store, actor=self.admin, reason="رسید نامعتبر")
        self.submit(order, tracking="TRK-THIRD")
        with self.assertRaises(svc.CardTransferError):
            svc.reject(CardTransferSubmission.objects.get(tracking_number="TRK-THIRD").pk, store=self.store, actor=self.admin, reason="ok!!")
            self.submit(order, tracking="TRK-FOURTH")                                    # cap of 3 submissions per order

    def test_canceled_orders_cannot_be_submitted_or_approved(self):
        order = self.make_order()
        submission = self.submit(order)
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELED)
        with self.assertRaises(svc.CardTransferError):
            svc.approve(submission.pk, store=self.store, actor=self.admin)
        order2 = self.make_order()
        Order.objects.filter(pk=order2.pk).update(status=Order.Status.CANCELED)
        with self.assertRaises(svc.CardTransferError):
            self.submit(order2)

    def test_duplicate_tracking_needs_an_explicit_override(self):
        a, b = self.make_order(), self.make_order()
        svc.approve(self.submit(a, tracking="SAME-TRK").pk, store=self.store, actor=self.admin)
        second = self.submit(b, tracking="same-trk")
        with self.assertRaises(svc.DuplicateTracking):
            svc.approve(second.pk, store=self.store, actor=self.admin)
        b.refresh_from_db()
        self.assertEqual(b.payment_status, Order.PaymentStatus.PENDING)
        svc.approve(second.pk, store=self.store, actor=self.admin, allow_duplicate_tracking=True)
        b.refresh_from_db()
        self.assertEqual(b.payment_status, Order.PaymentStatus.PAID)

    def test_amount_changed_after_submission_blocks_approval(self):
        order = self.make_order()
        submission = self.submit(order)
        Order.objects.filter(pk=order.pk).update(grand_total=order.grand_total + 1000)
        with self.assertRaises(svc.CardTransferError):
            svc.approve(submission.pk, store=self.store, actor=self.admin)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PENDING)

    def test_other_customers_and_other_stores_are_refused(self):
        order = self.make_order()
        other_user = User.objects.create_user(username="c2c-other", password="pass12345")
        other = Customer.objects.create(user=other_user, full_name="دیگری", phone="09121110002")
        with self.assertRaises(svc.CardTransferError):
            svc.submit(order.pk, store=self.store, customer=other, source_last4="1234", tracking_number="TRK-OTHER")
        foreign = Store.objects.create(name="دیگر", slug="c2c-foreign", status=Store.Status.ACTIVE)
        with self.assertRaises(Order.DoesNotExist):
            svc.submit(order.pk, store=foreign, customer=self.customer, source_last4="1234", tracking_number="TRK-OTHER")
        submission = self.submit(order)
        with self.assertRaises(CardTransferSubmission.DoesNotExist):
            svc.approve(submission.pk, store=foreign, actor=self.admin)

    def test_inactive_or_incomplete_configuration_blocks_the_flow(self):
        order = self.make_order()
        PaymentGatewayConfig.objects.filter(pk=self.config.pk).update(is_active=False)
        with self.assertRaises(svc.CardTransferError):
            self.submit(order)

    def test_no_full_card_number_ever_reaches_the_database_or_audit_log(self):
        order = self.make_order()
        with self.assertRaises(svc.CardTransferError):
            self.submit(order, last4="6037997000000019")
        self.submit(order)
        blob = " ".join(str(v) for v in CardTransferSubmission.objects.values()) + " ".join(str(a.after_summary) + str(a.metadata) for a in AuditLogEntry.objects.all())
        self.assertNotIn("6037997000000019", blob.replace(" ", ""))
        self.assertNotIn("cvv", blob.lower())


class ExistingMethodsUnchangedTests(CardTransferBase):
    def test_cod_and_gateway_attempt_behaviour_is_unchanged(self):
        from apps.orders.services.gateway_payment_service import initiate_payment

        cod_config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="cod", is_active=True)
        cod_gateway = PaymentGateway.objects.create(store=self.store, name="در محل", slug="cod", is_active=True)
        order = self.make_order(gateway=cod_gateway)
        attempt = initiate_payment(order=order, gateway_config=cod_config, callback_url="", store=self.store)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)                 # COD keeps its recorded-selection semantics
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_card_transfer_attempt_stays_pending_through_initiate_payment(self):
        from apps.orders.services.gateway_payment_service import initiate_payment

        order = self.make_order()
        attempt = initiate_payment(order=order, gateway_config=self.config, callback_url="", store=self.store)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        again = initiate_payment(order=order, gateway_config=self.config, callback_url="", store=self.store)
        self.assertEqual(again.pk, attempt.pk)                                            # no pile of duplicate attempts

    def test_card_transfer_orders_are_never_expired_by_the_online_gateway_path(self):
        from datetime import timedelta
        from apps.orders.services import order_expiry_service

        ShopSettings.objects.filter(store=self.store).update(unpaid_online_order_ttl_minutes=30)
        order = self.make_order()
        self.submit(order)
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=5))
        order_expiry_service.expire_unpaid_orders(store=self.store)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.PENDING)


# ───────────────────────────── views: customer page, admin queue, configuration ─────────────────────────────

@override_settings(ALLOWED_HOSTS=[HOST, SHOP_HOST, "testserver", "127.0.0.1", "localhost"])
class CardTransferViewsTests(CardTransferBase):
    def setUp(self):
        super().setUp()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="c2c-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.admin_client = Client(HTTP_HOST=HOST)
        self.admin_client.force_login(self.owner)

    def staff_client(self, role, name):
        user = User.objects.create_user(username=f"c2c-{name}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=role, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        client = Client(HTTP_HOST=HOST)
        client.force_login(user)
        return client

    # --- admin queue
    def test_queue_lists_and_the_approve_button_marks_the_order_paid_once(self):
        order = self.make_order()
        submission = self.submit(order)
        page = self.admin_client.get(reverse("dashboard:card-transfer-list"))
        self.assertContains(page, order.code)
        self.assertContains(page, "TRK12345")
        self.assertContains(page, "1234")
        self.assertContains(page, "تأیید پرداخت")
        url = reverse("dashboard:card-transfer-decide", args=[submission.pk, "approve"])
        self.admin_client.post(url)
        self.admin_client.post(url)                                                          # double click
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.transactions.count(), 1)
        approved = self.admin_client.get(reverse("dashboard:card-transfer-list") + "?status=approved")
        self.assertContains(approved, "c2c-owner")

    def test_reject_requires_a_reason_and_leaves_the_order_unpaid(self):
        order = self.make_order()
        submission = self.submit(order)
        url = reverse("dashboard:card-transfer-decide", args=[submission.pk, "reject"])
        self.admin_client.post(url, {"reason": ""})
        self.assertEqual(CardTransferSubmission.objects.get(pk=submission.pk).status, "submitted")
        self.admin_client.post(url, {"reason": "واریز دیده نشد"})
        submission.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual((submission.status, submission.review_note, order.payment_status), ("rejected", "واریز دیده نشد", Order.PaymentStatus.PENDING))

    def test_only_the_review_permission_can_decide_and_the_get_is_not_a_decision(self):
        order = self.make_order()
        submission = self.submit(order)
        url = reverse("dashboard:card-transfer-decide", args=[submission.pk, "approve"])
        for role, name in ((StoreMembership.Role.ANALYST, "an"), (StoreMembership.Role.CATALOG_MANAGER, "cm"), (StoreMembership.Role.CONTENT_EDITOR, "ce")):
            client = self.staff_client(role, name)
            self.assertEqual(client.post(url).status_code, 403, role)
            self.assertEqual(client.get(reverse("dashboard:card-transfer-list")).status_code, 403, role)
        self.assertEqual(self.admin_client.get(url).status_code, 405)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PENDING)
        om = self.staff_client(StoreMembership.Role.ORDER_MANAGER, "om")                     # order manager is allowed by design
        self.assertEqual(om.get(reverse("dashboard:card-transfer-list")).status_code, 200)

    def test_csrf_protected(self):
        order = self.make_order()
        submission = self.submit(order)
        strict = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(reverse("dashboard:card-transfer-decide", args=[submission.pk, "approve"])).status_code, 403)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PENDING)

    def test_admin_of_another_store_cannot_see_or_decide(self):
        order = self.make_order()
        submission = self.submit(order)
        other = Store.objects.create(name="دیگر", slug="c2c-other-admin", status=Store.Status.ACTIVE, admin_subdomain="c2c-other")
        stranger = User.objects.create_user(username="c2c-stranger", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=other, user=stranger, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        foreign = Client(HTTP_HOST="c2c-other.rastisi.localhost")
        foreign.force_login(stranger)
        with self.settings(ALLOWED_HOSTS=["c2c-other.rastisi.localhost", "testserver"]):
            self.assertEqual(foreign.post(reverse("dashboard:card-transfer-decide", args=[submission.pk, "approve"])).status_code, 404)
            self.assertNotContains(foreign.get(reverse("dashboard:card-transfer-list")), order.code)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PENDING)

    # --- customer page
    def _customer(self):
        client = Client(HTTP_HOST=SHOP_HOST)
        client.force_login(self.user)
        return client

    def test_customer_page_shows_amount_and_destination_and_accepts_only_last4(self):
        order = self.make_order()
        with mock.patch("apps.orders.views.resolve_store_for_service", return_value=self.store), mock.patch(
            "apps.storefront_builder.services.storefront_context_service.build_universal_storefront_context", return_value={},
        ):
            client = self._customer()
            url = reverse("orders:card-transfer", args=[order.code])
            page = client.get(url)
            self.assertContains(page, "6037 9970 0000 0019")
            self.assertContains(page, "علی رضایی")
            self.assertContains(page, "CVV2")
            bad = client.post(url, {"source_last4": VALID_CARD, "tracking_number": "TRK1234"})
            self.assertContains(bad, "فقط ۴ رقمِ آخر")
            self.assertEqual(CardTransferSubmission.objects.count(), 0)
            ok = client.post(url, {"source_last4": "4321", "tracking_number": "TRK-777"}, follow=True)
            self.assertContains(ok, "در انتظار بررسی پرداخت")
            order.refresh_from_db()
            self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_a_customer_cannot_open_or_post_to_someone_elses_order(self):
        order = self.make_order()
        other_user = User.objects.create_user(username="c2c-intruder", password="pass12345")
        Customer.objects.create(user=other_user, full_name="مزاحم", phone="09121110009")
        with mock.patch("apps.orders.views.resolve_store_for_service", return_value=self.store):
            client = Client(HTTP_HOST=SHOP_HOST)
            client.force_login(other_user)
            url = reverse("orders:card-transfer", args=[order.code])
            self.assertEqual(client.get(url).status_code, 404)
            self.assertEqual(client.post(url, {"source_last4": "1111", "tracking_number": "TRK-X1"}).status_code, 404)
            anonymous = Client(HTTP_HOST=SHOP_HOST)
            self.assertEqual(anonymous.get(url).status_code, 404)
        self.assertEqual(CardTransferSubmission.objects.count(), 0)

    # --- configuration
    def test_admin_saves_the_destination_card_which_activates_the_method_and_the_checkout_row(self):
        PaymentGatewayConfig.objects.filter(store=self.store, gateway_code="card_to_card").delete()
        PaymentGateway.objects.filter(store=self.store, slug="card_to_card").delete()
        url = reverse("dashboard:settings-gateway-config-save", args=["card_to_card"])
        bad = self.admin_client.post(url, {"is_active": "on", "credential_destination_card": "1234567812345678", "credential_holder_name": "x"})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card").is_active)     # invalid card -> not activated
        self.admin_client.post(url, {
            "is_active": "on", "credential_destination_card": "6037 9970 0000 0019", "credential_holder_name": "علی رضایی",
            "credential_bank_name": "ملی", "display_title": "کارت‌به‌کارت",
        })
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card")
        self.assertTrue(config.is_active)
        self.assertEqual(config.get_credentials()["destination_card"], VALID_CARD)
        row = PaymentGateway.objects.get(store=self.store, slug="card_to_card")
        self.assertTrue(row.is_active)                                                       # what the checkout lists
        self.admin_client.post(reverse("dashboard:settings-gateway-config-toggle", args=["card_to_card"]))
        self.assertFalse(PaymentGateway.objects.get(pk=row.pk).is_active)
        self.assertFalse(PaymentGatewayConfig.objects.get(pk=config.pk).is_active)

    def test_configuration_needs_the_payment_settings_permission(self):
        client = self.staff_client(StoreMembership.Role.ORDER_MANAGER, "om2")
        url = reverse("dashboard:settings-gateway-config-save", args=["card_to_card"])
        self.assertEqual(client.post(url, {"is_active": "on"}).status_code, 403)

    def test_checkout_hides_card_to_card_while_its_configuration_is_inactive(self):
        from apps.orders.services import checkout_service

        self.assertIn(self.gateway, checkout_service.active_payment_gateways(store=self.store))
        PaymentGatewayConfig.objects.filter(pk=self.config.pk).update(is_active=False)
        self.assertNotIn(self.gateway, checkout_service.active_payment_gateways(store=self.store))


class DerivedStatusDisplayTests(CardTransferBase):
    def test_label_follows_the_submissions_and_never_the_payment_status(self):
        order = self.make_order()
        self.assertEqual(order.payment_review_label, "در انتظار واریز و ثبت اطلاعات")
        self.submit(order)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_review_label, "در انتظار بررسی پرداخت")
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, "pending")
        other = self.make_order(gateway=PaymentGateway.objects.create(store=self.store, name="دیگر", slug="other-gw", is_active=True))
        self.assertEqual(other.payment_review_label, "")                                   # other methods are untouched
