"""سناریوهایِ یکپارچه‌ی A–E: کمپین، تولد، خریدِ هدیه، هدیه + تخفیف، پرداختِ ناموفق/لغو/مرجوعی."""

import datetime as dt
from decimal import Decimal

from django.core import mail
from django.utils import timezone

from apps.cart.models import Cart, CartItem, Coupon
from apps.cart.services.cart_service import add_item_to_cart
from apps.cart.services.pricing import cart_totals
from apps.core.models import ShopSettings
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.tests.base import EngagementBase, jdt
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.notifications.services.notification_service import deliver_pending
from apps.orders.models import CouponRedemption, Order, ReturnItem
from apps.orders.services import return_service
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.orders.services.payment_service import simulate_payment
from apps.orders.services.refund_service import refundable_amount

M = 1_000_000


class GiftScenarioBase(EngagementBase):
    def setUp(self):
        super().setUp()
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("50000")
        shop.tax_percent = Decimal("9")
        shop.save()
        self.shipping.cost = Decimal("60000")
        self.shipping.save()
        self.shirt = self.product("پیراهن", 1 * M)
        self.vase = self.product("گلدان", 500_000)

    def buy(self, customer, lines, *, wrap=(), message="", coupon=None, gateway=None):
        from apps.customers.models import Address

        address = Address.objects.create(
            customer=customer, receiver_name="گ", phone=customer.phone, province="فارس", city="شیراز",
            postal_code="1111111111", full_address="x",
        )
        cart = Cart.objects.create(customer=customer)
        for product, qty in lines:
            add_item_to_cart(cart, product, None, qty, gift_wrap_requested=product in wrap, gift_message=message)
        return create_order_from_cart(
            cart, customer=customer, vendor=self.vendor, address=address, shipping_method=self.shipping,
            payment_gateway=gateway or self.gateway, coupon=coupon, store=self.store,
        )


class ScenarioCGiftPurchase(GiftScenarioBase):
    def test_gift_purchase_end_to_end_with_notifications(self):
        customer = self.customer("هدیه‌گیر", email="g@example.com")
        NotificationTemplate.objects.create(
            store=self.store, event_key="staff.order_created", channel="email", is_enabled=True,
            subject="سفارش {order_number}", body="{order_number} {customer_name} {order_total} {gift_wrap_note} {store_name}",
            extra_recipients="packing@example.com",
        )
        order = self.buy(customer, [(self.vase, 2), (self.shirt, 1)], wrap=(self.vase,), message="تبریک!")
        self.assertEqual(order.gift_wrap_total, Decimal("100000"))  # 2 × 50,000 (per unit)
        vase_item = order.items.get(product=self.vase)
        self.assertTrue(vase_item.gift_wrap_selected)
        self.assertEqual(vase_item.gift_message, "تبریک!")
        self.assertFalse(order.items.get(product=self.shirt).gift_wrap_selected)
        # فقط کالا (نه کادوپیچی/ارسال) مشمولِ مالیات است
        self.assertEqual(order.tax, Decimal("180000"))  # 9% of 2,000,000
        self.assertEqual(order.grand_total, Decimal("2000000") + 180000 + 60000 + 100000)

        rows = NotificationOutbox.objects.filter(order=order)
        self.assertTrue(rows.filter(event_key="order.created", channel="email", recipient_email="g@example.com").exists())
        staff = rows.get(event_key="staff.order_created")
        self.assertIn("کادوپیچی", staff.body)
        deliver_pending()
        self.assertTrue(any("packing@example.com" in m.to for m in mail.outbox))


class ScenarioDGiftWrapWithDiscount(GiftScenarioBase):
    def _check_consistency(self, order):
        item_discount = order.coupon_discount - order.gift_wrap_discount
        expected = (order.items_total - item_discount + order.tax + order.shipping_cost
                    + order.gift_wrap_total - order.gift_wrap_discount)
        self.assertEqual(order.grand_total, expected)
        self.assertGreaterEqual(order.grand_total, 0)

    def test_coupon_not_applied_to_gift_wrap_by_default(self):
        c = self.customer("د۱")
        coupon = Coupon.objects.create(store=self.store, code="D10", type="percent", value=10, max_discount=Decimal(100000))
        order = self.buy(c, [(self.shirt, 1)], wrap=(self.shirt,), coupon=coupon)
        self.assertEqual(order.items_total, Decimal("1000000"))
        self.assertEqual(order.coupon_discount, Decimal("100000"))
        self.assertEqual(order.gift_wrap_total, Decimal("50000"))
        self.assertEqual(order.gift_wrap_discount, Decimal("0"))
        self.assertEqual(order.tax, Decimal("81000"))            # 9% of (1,000,000 − 100,000)
        self.assertEqual(order.grand_total, Decimal("1000000") - 100000 + 81000 + 60000 + 50000)
        self._check_consistency(order)

    def test_coupon_applied_to_gift_wrap_when_configured_with_cap(self):
        c = self.customer("د۲")
        coupon = Coupon.objects.create(store=self.store, code="D20", type="percent", value=20, max_discount=Decimal(150000),
                                       applies_to_gift_wrap=True)
        order = self.buy(c, [(self.shirt, 1)], wrap=(self.shirt,), coupon=coupon)
        # 20% of (1,000,000 + 50,000) = 210,000 → capped at 150,000, split proportionally
        self.assertEqual(order.coupon_discount, Decimal("150000"))
        self.assertEqual(order.gift_wrap_discount, Decimal("7143"))   # 150000 × 50000/1050000 rounded
        self.assertEqual(order.coupon_discount - order.gift_wrap_discount, Decimal("142857"))   # سهمِ کالا
        self._check_consistency(order)

    def test_discount_never_exceeds_payable_and_total_never_negative(self):
        c = self.customer("د۳")
        coupon = Coupon.objects.create(store=self.store, code="D30", type="fixed", value=Decimal(99 * M), applies_to_gift_wrap=True)
        order = self.buy(c, [(self.vase, 1)], wrap=(self.vase,), coupon=coupon)
        self.assertEqual(order.coupon_discount, Decimal("550000"))     # item + wrap only; shipping not discounted
        self.assertGreaterEqual(order.grand_total, order.shipping_cost)
        self._check_consistency(order)

    def test_free_shipping_coupon_with_paid_wrap(self):
        c = self.customer("د۴")
        coupon = Coupon.objects.create(store=self.store, code="FREESHIP", type="free_ship", value=0)
        order = self.buy(c, [(self.shirt, 1)], wrap=(self.shirt,), coupon=coupon)
        self.assertEqual(order.shipping_cost, Decimal("0"))
        self.assertEqual(order.gift_wrap_total, Decimal("50000"))
        self.assertEqual(order.grand_total, Decimal("1000000") + order.tax + 50000)


class ScenarioEFailureCancelReturn(GiftScenarioBase):
    def setUp(self):
        super().setUp()
        self.customer_ = self.customer("ای", email="e@example.com")
        self.coupon = Coupon.objects.create(store=self.store, code="E10", type="percent", value=10, usage_limit=1,
                                            applies_to_gift_wrap=True)

    def test_failed_payment_releases_discount_keeps_state_consistent_and_notifies(self):
        order = self.buy(self.customer_, [(self.shirt, 1)], wrap=(self.shirt,), coupon=self.coupon)
        simulate_payment(order, False, store=self.store)
        order.refresh_from_db()
        self.coupon.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.coupon.used_count, 0)                 # ظرفیتِ کد برگشت
        self.assertEqual(order.gift_wrap_total, Decimal("50000"))   # اسنپ‌شاتِ سفارش دست‌نخورده
        self.assertTrue(NotificationOutbox.objects.filter(order=order, event_key="payment.failed", channel="email").exists())
        # مشتری می‌تواند دوباره با همان کد سفارش دهد
        order2 = self.buy(self.customer_, [(self.shirt, 1)], coupon=self.coupon)
        self.assertGreater(order2.coupon_discount, 0)

    def test_cancel_after_payment_releases_code_and_full_refund_covers_wrap_and_shipping(self):
        order = self.buy(self.customer_, [(self.shirt, 1)], wrap=(self.shirt,), coupon=self.coupon)
        simulate_payment(order, True, store=self.store)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        self.coupon.refresh_from_db()
        redemption = CouponRedemption.objects.get(order=order)
        self.assertEqual(redemption.status, CouponRedemption.Status.RELEASED)
        self.assertEqual(self.coupon.used_count, 0)
        # مبلغِ قابل‌استرداد = کلِ مبلغِ پرداخت‌شده (کالا + کادوپیچی + ارسال + مالیات − تخفیف)
        self.assertEqual(refundable_amount(order), order.grand_total)
        self.assertTrue(NotificationOutbox.objects.filter(order=order, event_key="order.canceled").exists())

    def test_partial_return_refunds_net_of_discount_and_wrap_and_notifies(self):
        from apps.orders.services.refund_service import execute_order_refund

        order = self.buy(self.customer_, [(self.shirt, 2)], wrap=(self.shirt,), coupon=self.coupon)
        simulate_payment(order, True, store=self.store)
        item = order.items.get()
        req = return_service.create_return_request(
            order, store=self.store, customer=self.customer_, reason="customer_request",
            line_requests=[{"order_item_id": item.pk, "quantity": 1}],
        )
        self.assertTrue(NotificationOutbox.objects.filter(event_key="return.requested", order=order).exists())
        return_service.review_return_request(req, store=self.store)
        return_service.approve_return_request(req, store=self.store)
        self.assertTrue(NotificationOutbox.objects.filter(event_key="return.approved", order=order).exists())
        return_service.mark_return_received(req, store=self.store)
        return_service.inspect_return_items(req, store=self.store, inspections=[{
            "item_id": req.items.get().pk, "condition": "new", "is_restockable": True, "merchant_resolution": ReturnItem.Resolution.REFUND}])
        req = return_service.complete_return(req, store=self.store)
        refund = req.refund
        # ۱ از ۲ عدد: نیمِ (قیمت − تخفیف) + نیمِ کادوپیچیِ خالص + نیمِ مالیات
        order.refresh_from_db()
        line = refund.items.get()
        self.assertEqual(line.amount, (order.items_total - (order.coupon_discount - order.gift_wrap_discount)) / 2)
        self.assertEqual(line.gift_wrap_amount, (order.gift_wrap_total - order.gift_wrap_discount) / 2)
        self.assertTrue(NotificationOutbox.objects.filter(event_key="refund.completed", order=order).exists())
        # بقیه (۱ عدد) هنوز قابل‌استرداد است و جمعِ دو استرداد از پرداختی بیشتر نمی‌شود
        remaining = refundable_amount(order)
        self.assertGreater(remaining, 0)
        execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}],
                             shipping_amount=order.shipping_cost)
        order.refresh_from_db()
        self.assertEqual(refundable_amount(order), Decimal("0"))

    def test_rejected_return_notifies_and_changes_nothing_financial(self):
        order = self.buy(self.customer_, [(self.shirt, 1)])
        simulate_payment(order, True, store=self.store)
        req = return_service.create_return_request(
            order, store=self.store, customer=self.customer_, reason="customer_request",
            line_requests=[{"order_item_id": order.items.get().pk, "quantity": 1}],
        )
        return_service.reject_return_request(req, store=self.store, rejection_reason="خارج از مهلت")
        row = NotificationOutbox.objects.get(event_key="return.rejected", channel="email")
        self.assertIn("خارج از مهلت", row.body)
        self.assertEqual(refundable_amount(order), order.grand_total)

    def test_order_status_notifications_are_not_duplicated(self):
        order = self.buy(self.customer_, [(self.shirt, 1)])
        simulate_payment(order, True, store=self.store)
        change_order_status(order, Order.Status.SHIPPED, store=self.store, tracking_code="TRK-1")
        change_order_status(order, Order.Status.DELIVERED, store=self.store)
        keys = list(NotificationOutbox.objects.filter(order=order, channel="email").values_list("event_key", flat=True))
        for event in ("order.created", "payment.succeeded", "order.processing", "order.shipped", "order.delivered"):
            self.assertEqual(keys.count(event), 1, event)
        shipped = NotificationOutbox.objects.get(order=order, event_key="order.shipped")
        self.assertIn("TRK-1", shipped.body)

    def test_event_campaign_runs_after_successful_payment_commit(self):
        customer = self.customer("رویداد", email="ev@example.com")
        campaign = cs.save_campaign(Campaign(
            store=self.store, name="پس از خرید", trigger_type=Campaign.Trigger.EVENT,
            rules={"type": "lifetime_orders", "op": "gte", "value": "1"}, coupon_type="percent", coupon_value=Decimal("5"),
            code_valid_days=10, code_prefix="THX",
        ))
        cs.activate(campaign)
        order = self.buy(customer, [(self.shirt, 1)])
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, True, store=self.store)
        issuance = CampaignIssuance.objects.get()
        self.assertEqual(issuance.customer, customer)
        self.assertTrue(issuance.coupon.code.startswith("THX-"))
        with self.captureOnCommitCallbacks(execute=True):
            other = self.buy(customer, [(self.shirt, 1)])
            simulate_payment(other, True, store=self.store)
        self.assertEqual(CampaignIssuance.objects.count(), 1)       # یک‌بار برایِ هر مشتری (cycle=once)


class ScenarioAPerformanceTracking(GiftScenarioBase):
    def test_redemption_and_performance_are_tracked(self):
        winner = self.customer("برنده")
        self.order(winner, [(self.shirt, 1)], when=jdt(1405, 7, 5))
        campaign = cs.save_campaign(Campaign(
            store=self.store, name="ردیابی", rules={"type": "order_total", "op": "gte", "value": "1"},
            period_mode="jalali_months", period_jalali_year=1405, period_start_month=7, period_end_month=7,
            coupon_type="percent", coupon_value=Decimal("10"), code_valid_days=30, code_prefix="TRK",
            total_redemption_limit=1, per_customer_limit=1,
        ))
        cs.activate(campaign)
        cs.execute_campaign(campaign)
        coupon = CampaignIssuance.objects.get().coupon
        perf = cs.performance(campaign)
        self.assertEqual((perf["issued"], perf["redeemed"], perf["redemption_rate"]), (1, 0, 0))
        order = self.buy(winner, [(self.vase, 1)], coupon=coupon)
        simulate_payment(order, True, store=self.store)
        perf = cs.performance(campaign)
        self.assertEqual((perf["redeemed"], perf["redeemed_customers"], perf["redemption_rate"]), (1, 1, 100.0))
        self.assertEqual(perf["discount_total"], Decimal("50000"))
        self.assertEqual(perf["revenue"], order.grand_total)
        self.assertGreaterEqual(perf["notifications_sent"] + perf["notifications"].get("pending", 0), 1)
        # لغوِ سفارش ⇒ استفاده آزاد می‌شود و در گزارش «آزادشده» حساب می‌شود
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        perf = cs.performance(campaign)
        self.assertEqual((perf["redeemed"], perf["released"]), (0, 1))
