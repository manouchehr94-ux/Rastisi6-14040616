"""سناریویِ اجباریِ کمپین: مهر تا آبانِ ۱۴۰۵ — کیفِ زیتونی «یا» کفشِ نایک،
جمعِ فاکتورها > ۱۰ میلیون تومان، حداقل یک سفارش با مقصدِ شیراز ⇒ کدِ شخصیِ
۳۰٪ با سقفِ ۴ میلیون تومان."""

import datetime as dt
from decimal import Decimal

from django.core import mail
from django.utils import timezone

from apps.cart.models import Coupon
from apps.engagement.models import Campaign, CampaignIssuance, CampaignRun
from apps.engagement.services import campaign_service as cs
from apps.engagement.tests.base import EngagementBase, jdt
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import deliver_pending
from apps.orders.models import Order

M = 1_000_000


def mandatory_rules(olive_bag_category, shoe_category, nike):
    """(کیفِ زیتونی OR کفشِ نایک) AND جمع > ۱۰M AND مقصد = شیراز."""
    return {
        "type": "group", "op": "and", "children": [
            {"type": "group", "op": "or", "children": [
                {"type": "line_match", "category_ids": [olive_bag_category.pk], "colors": ["زیتونی"]},
                {"type": "line_match", "category_ids": [shoe_category.pk], "brand_ids": [nike.pk]},
            ]},
            {"type": "order_total", "op": "gt", "value": 10 * M},
            {"type": "shipping_city", "values": ["شیراز", "Shiraz"]},
        ],
    }


class MandatoryBase(EngagementBase):
    def setUp(self):
        super().setUp()
        self.olive_bag = self.product("کیف زیتونی", 6 * M, category=self.cat_bag, color=("زیتونی", "#808000"))
        self.black_bag = self.product("کیف مشکی", 6 * M, category=self.cat_bag, color=("مشکی", "#000000"))
        self.nike_shoe = self.product("کفش نایک", 12 * M, category=self.cat_shoe, brand=self.nike)
        self.adidas_shoe = self.product("کفش آدیداس", 12 * M, category=self.cat_shoe, brand=self.adidas)
        self.shirt = self.product("پیراهن", 5 * M)
        self.big_shirt = self.product("کت", 15 * M)
        self.mehr = lambda d, **kw: jdt(1405, 7, d, **kw)
        self.aban = lambda d, **kw: jdt(1405, 8, d, **kw)

    def campaign(self, **kw):
        defaults = dict(
            store=self.store, name="کمپین مهر–آبان ۱۴۰۵", trigger_type=Campaign.Trigger.MANUAL,
            rules=mandatory_rules(self.cat_bag, self.cat_shoe, self.nike),
            period_mode=Campaign.PeriodMode.JALALI_MONTHS, period_jalali_year=1405, period_start_month=7, period_end_month=8,
            reward_type=Campaign.Reward.COUPON, coupon_type="percent", coupon_value=Decimal("30"),
            coupon_max_discount=Decimal(4 * M), code_prefix="MEHR", personalized=True,
            code_starts_at=timezone.now() - dt.timedelta(minutes=5), code_expires_at=timezone.now() + dt.timedelta(days=30),
            total_redemption_limit=1, per_customer_limit=1, channels=["sms", "email"],
        )
        defaults.update(kw)
        return cs.save_campaign(Campaign(**defaults))

    def eligible(self, campaign):
        return set(cs.compute_eligible(campaign))

    def activated(self, **kw):
        c = self.campaign(**kw)
        cs.activate(c)
        c.refresh_from_db()
        return c


class MandatoryCampaignTests(MandatoryBase):
    # ---------------------------------------------------------------- معیارهای مثبت
    def test_olive_bag_in_two_orders_aggregate_is_eligible(self):
        c = self.customer("الف")
        self.order(c, [(self.olive_bag, 1)], when=self.mehr(10), city="شیراز")        # 6M, Shiraz
        self.order(c, [(self.shirt, 1)], when=self.aban(20), city="تهران")            # 5M
        self.assertIn(c.pk, self.eligible(self.campaign()))

    def test_nike_shoe_branch_of_or_is_eligible(self):
        c = self.customer("ب")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(15), city="شیراز")
        self.assertIn(c.pk, self.eligible(self.campaign()))

    def test_or_is_not_treated_as_and(self):
        only_olive = self.customer("فقط زیتونی")
        self.order(only_olive, [(self.olive_bag, 1), (self.shirt, 1)], when=self.mehr(3))
        only_nike = self.customer("فقط نایک")
        self.order(only_nike, [(self.nike_shoe, 1)], when=self.mehr(4))
        both = self.customer("هر دو")
        self.order(both, [(self.olive_bag, 1), (self.nike_shoe, 1)], when=self.mehr(5))
        got = self.eligible(self.campaign())
        self.assertEqual(got, {only_olive.pk, only_nike.pk, both.pk})

    # ---------------------------------------------------------------- معیارهای منفی
    def test_amount_must_exceed_ten_million_strictly(self):
        under = self.customer("کمتر")
        self.order(under, [(self.olive_bag, 1), (self.shirt, 1)], when=self.mehr(3))  # 6M+5M = 11M → eligible
        exact = self.customer("دقیقاً ۱۰")
        p10 = self.product("کیف ۱۰", 10 * M, category=self.cat_bag, color=("زیتونی", "#808000"))
        self.order(exact, [(p10, 1)], when=self.mehr(3))
        nine = self.customer("نه")
        p9 = self.product("کیف ۹", 9 * M, category=self.cat_bag, color=("زیتونی", "#808000"))
        self.order(nine, [(p9, 1)], when=self.mehr(3))
        got = self.eligible(self.campaign())
        self.assertIn(under.pk, got)
        self.assertNotIn(exact.pk, got)  # == 10M is not "exceeds"
        self.assertNotIn(nine.pk, got)

    def test_no_matching_product_not_eligible(self):
        c1, c2, c3 = self.customer("۱"), self.customer("۲"), self.customer("۳")
        self.order(c1, [(self.big_shirt, 1)], when=self.mehr(3))             # 15M but wrong product
        self.order(c2, [(self.black_bag, 2)], when=self.mehr(3))             # 12M, bag but not olive
        self.order(c3, [(self.adidas_shoe, 1)], when=self.mehr(3))           # 12M shoe but not Nike
        self.assertFalse(self.eligible(self.campaign()))

    def test_destination_must_be_shiraz(self):
        c = self.customer("تهرانی")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3), city="تهران", province="تهران")
        self.assertFalse(self.eligible(self.campaign()))

    def test_period_boundaries_cover_entire_months_in_store_timezone(self):
        first_second = self.customer("اولین ثانیه")
        self.order(first_second, [(self.nike_shoe, 1)], when=jdt(1405, 7, 1, 0, 0, 0))
        last_second = self.customer("آخرین ثانیه")
        self.order(last_second, [(self.nike_shoe, 1)], when=jdt(1405, 8, 30, 23, 59, 59))
        before = self.customer("قبل")
        self.order(before, [(self.nike_shoe, 1)], when=jdt(1405, 6, 31, 23, 59, 59))     # آخرین ثانیه‌ی شهریور
        after = self.customer("بعد")
        self.order(after, [(self.nike_shoe, 1)], when=jdt(1405, 9, 1, 0, 0, 0))          # اول آذر
        self.assertEqual(self.eligible(self.campaign()), {first_second.pk, last_second.pk})

    def test_cancelled_pending_failed_refunded_orders_are_not_valid(self):
        rows = {}
        for key, (status, payment) in {
            "canceled": ("canceled", "paid"), "pending": ("pending", "pending"),
            "failed": ("pending", "failed"), "refunded": ("processing", "refunded"),
        }.items():
            rows[key] = self.customer(key)
            self.order(rows[key], [(self.nike_shoe, 1)], when=self.mehr(7), status=status, payment=payment)
        self.assertFalse(self.eligible(self.campaign()))

    def test_partial_refund_reduces_net_amount(self):
        from apps.orders.services.refund_service import execute_order_refund

        c = self.customer("استرداد جزئی")
        order = self.order(c, [(self.nike_shoe, 1), (self.shirt, 1)], when=self.mehr(7))  # 17M
        item = order.items.get(product=self.shirt)
        execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        order.refresh_from_db()
        # net = 17M − 5M = 12M (> 10M) → still eligible on net basis
        self.assertIn(c.pk, self.eligible(self.campaign()))
        big = self.campaign(name="net 13M", rules={
            "type": "group", "op": "and", "children": [
                {"type": "order_total", "op": "gt", "value": 13 * M},
                {"type": "shipping_city", "values": ["شیراز"]},
            ]})
        self.assertNotIn(c.pk, self.eligible(big))
        gross = self.campaign(name="gross 13M", amount_basis="grand_total", rules=big.rules)
        self.assertIn(c.pk, self.eligible(gross))

    def test_other_store_orders_never_count(self):
        from apps.stores.models import Store

        from apps.core.models import ShopSettings

        other = Store.objects.create(name="دیگر", slug="eng-other", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other)
        c = self.customer("چندفروشگاهی")
        cat = self.cat_other
        p = self.product("کفش نایک دیگر", 12 * M, store=other, brand=None)
        self.order(c, [(p, 1)], when=self.mehr(5), store=other)
        self.assertNotIn(c.pk, self.eligible(self.campaign()))
        other_campaign = self.campaign(store=other, rules={})
        self.assertIn(c.pk, set(cs.compute_eligible(other_campaign)))
        self.assertNotIn(c.pk, set(cs.compute_eligible(self.campaign(rules={}))))

    # ---------------------------------------------------------------- دامنه‌ی شرط‌ها
    def test_same_order_scope_requires_one_order_to_satisfy_everything(self):
        split = self.customer("تقسیم‌شده")
        self.order(split, [(self.olive_bag, 1)], when=self.mehr(3), city="شیراز")      # 6M, Shiraz, olive bag
        self.order(split, [(self.nike_shoe, 1)], when=self.mehr(4), city="تهران")      # 12M, Nike, Tehran
        single = self.customer("یک‌سفارشه")
        self.order(single, [(self.nike_shoe, 1)], when=self.mehr(5), city="شیراز")      # 12M all in one
        aggregate = self.eligible(self.campaign())
        same = self.eligible(self.campaign(rule_scope=Campaign.Scope.SAME_ORDER))
        self.assertEqual(aggregate, {split.pk, single.pk})   # 18M total, olive bag, Shiraz (different orders)
        self.assertEqual(same, {single.pk})

    def test_historical_snapshot_is_used_not_current_catalog(self):
        c = self.customer("تاریخی")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(9))
        # بعد از خرید، برند و دسته‌ی کالا عوض می‌شود
        self.nike_shoe.brand = self.adidas
        self.nike_shoe.category = self.cat_other
        self.nike_shoe.save()
        self.assertIn(c.pk, self.eligible(self.campaign()))

    def test_legacy_item_without_snapshot_falls_back_to_live_catalog(self):
        c = self.customer("قدیمی")
        order = self.order(c, [(self.nike_shoe, 1)], when=self.mehr(9))
        order.items.update(attributes_snapshot={})
        self.assertIn(c.pk, self.eligible(self.campaign()))

    def test_nested_groups_and_negation(self):
        c1 = self.customer("n1")
        self.order(c1, [(self.nike_shoe, 1)], when=self.mehr(2))
        c2 = self.customer("n2")
        self.order(c2, [(self.nike_shoe, 1), (self.black_bag, 1)], when=self.mehr(2))
        tree = {"type": "group", "op": "and", "children": [
            {"type": "line_match", "brand_ids": [self.nike.pk]},
            {"type": "group", "op": "and", "negate": True, "children": [  # NOT any black bag
                {"type": "line_match", "colors": ["مشکی"], "category_ids": [self.cat_bag.pk]}]},
        ]}
        got = self.eligible(self.campaign(rules=tree))
        self.assertEqual(got, {c1.pk})

    def test_invalid_rule_trees_rejected_and_cross_store_ids_blocked(self):
        from apps.engagement.services import rules

        bad_trees = [
            {"type": "evil"}, {"type": "group", "op": "xor", "children": [{"type": "had_discount"}]},
            {"type": "group", "op": "and", "children": []}, {"type": "line_match"},
            {"type": "order_total", "op": "gt", "value": "abc"}, {"type": "order_total", "op": "between", "value": 5, "value2": 1},
            {"type": "line_match", "product_ids": [987654]}, {"type": "shipping_city", "values": []},
        ]
        for tree in bad_trees:
            with self.assertRaises(rules.RuleError, msg=str(tree)):
                rules.validate_tree(tree, self.store)
        deep = {"type": "had_discount"}
        for _ in range(8):
            deep = {"type": "group", "op": "and", "children": [deep]}
        with self.assertRaises(rules.RuleError):
            rules.validate_tree(deep, self.store)

    # ---------------------------------------------------------------- صدور
    def test_validation_blocks_activation_of_incomplete_campaign(self):
        c = self.campaign(coupon_value=Decimal("0"), code_expires_at=None, code_valid_days=None)
        errors = cs.validate_campaign(c)
        self.assertTrue(any("درصد" in e for e in errors))
        self.assertTrue(any("انقضا" in e for e in errors))
        with self.assertRaises(cs.CampaignError):
            cs.activate(c)
        self.assertEqual(Campaign.objects.get(pk=c.pk).status, Campaign.Status.DRAFT)

    def test_execute_requires_active_status(self):
        c = self.campaign()
        run = cs.execute_campaign(c)
        self.assertIn("قابلِ اجرا نیست", run.error_text)
        self.assertEqual(CampaignIssuance.objects.count(), 0)

    def test_full_flow_issue_personal_coupon_notify_redeem_expire(self):
        winner = self.customer("برنده", email="w@example.com")
        self.order(winner, [(self.olive_bag, 1), (self.shirt, 1)], when=self.mehr(3))
        loser = self.customer("بازنده")
        self.order(loser, [(self.shirt, 1)], when=self.mehr(3))
        campaign = self.activated()

        # پیش‌نمایش پیش از اجرا: چیزی صادر نمی‌شود
        info = cs.preview(campaign)
        self.assertEqual(info["count"], 1)
        self.assertEqual(CampaignIssuance.objects.count(), 0)

        run = cs.execute_campaign(campaign)
        self.assertEqual((run.eligible, run.issued, run.errors), (1, 1, 0))
        issuance = CampaignIssuance.objects.get()
        coupon = issuance.coupon
        self.assertEqual(issuance.customer, winner)
        self.assertEqual(coupon.customer, winner)                       # شخصی
        self.assertEqual((coupon.type, coupon.value, coupon.max_discount), ("percent", Decimal("30"), Decimal(4 * M)))
        self.assertEqual((coupon.usage_limit, coupon.per_customer_limit), (1, 1))
        self.assertIsNotNone(coupon.starts_at)
        self.assertIsNotNone(coupon.expires_at)
        self.assertTrue(coupon.code.startswith("MEHR-"))
        self.assertEqual(coupon.store, self.store)

        # اعلان‌ها در صف، حاویِ همان کد، فقط برایِ برنده
        rows = NotificationOutbox.objects.filter(event_key="coupon.issued")
        self.assertEqual({r.channel for r in rows}, {"sms", "email"})
        self.assertTrue(all(r.customer == winner and coupon.code in r.body for r in rows))
        self.assertTrue(all(r.metadata["issuance_id"] == issuance.pk for r in rows))
        deliver_pending()
        coupon_mail = [m for m in mail.outbox if coupon.code in m.body]
        self.assertEqual(len(coupon_mail), 1)
        self.assertEqual(coupon_mail[0].to, ["w@example.com"])

        # اجرایِ دوباره: idempotent — نه صدورِ جدید، نه پیامِ جدید
        run2 = cs.execute_campaign(campaign)
        self.assertEqual((run2.issued, run2.skipped_existing), (0, 1))
        self.assertEqual(CampaignIssuance.objects.count(), 1)
        self.assertEqual(Coupon.objects.filter(store=self.store, code__startswith="MEHR-").count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="coupon.issued").count(), 2)

        # بازخرید: ۳۰٪ با سقفِ ۴ میلیون روی سبدِ ۲۰ میلیونی
        from apps.cart.services.pricing import cart_totals
        from apps.cart.models import Cart, CartItem

        big = self.product("کالای گران", 20 * M)
        cart = Cart.objects.create(customer=winner)
        CartItem.objects.create(cart=cart, product=big, quantity=1, unit_price=big.final_price)
        totals = cart_totals(cart, store=self.store, coupon=coupon, customer=winner)
        self.assertEqual(totals["coupon_discount"], Decimal(4 * M))                 # 30% = 6M → cap 4M
        # فقط مالک
        self.assertFalse(cart_totals(cart, store=self.store, coupon=coupon, customer=loser)["coupon_applied"])
        self.assertFalse(cart_totals(cart, store=self.store, coupon=coupon, customer=None)["coupon_applied"])

        order = self.order(winner, [(big, 1)], when=timezone.now(), coupon=coupon)
        self.assertEqual(order.coupon_discount, Decimal(4 * M))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        # سقفِ کلِ استفاده (۱) پر شد
        self.assertFalse(cart_totals(cart, store=self.store, coupon=coupon, customer=winner)["coupon_applied"])

        # انقضا
        Coupon.objects.filter(pk=coupon.pk).update(used_count=0, expires_at=timezone.now() - dt.timedelta(seconds=1))
        coupon.refresh_from_db()
        t = cart_totals(cart, store=self.store, coupon=coupon, customer=winner)
        self.assertFalse(t["coupon_applied"])
        self.assertEqual(t["coupon_error_code"], "expired")

    def test_no_notification_without_consent_but_code_still_saved(self):
        c = self.customer("بدون رضایت", email="x@example.com", sms=False, mail=False)
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated()
        cs.execute_campaign(campaign)
        issuance = CampaignIssuance.objects.get()
        self.assertEqual(issuance.coupon.customer, c)  # در حسابِ مشتری ذخیره شد
        rows = NotificationOutbox.objects.filter(event_key="coupon.issued")
        self.assertTrue(all(r.status == "skipped" and r.skip_reason == "no_promotional_consent" for r in rows))
        deliver_pending()
        self.assertFalse([m for m in mail.outbox if issuance.coupon.code in m.body])

    def test_capacity_limit_completes_campaign(self):
        for i in range(3):
            c = self.customer(f"ظرفیت{i}")
            self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3 + i))
        campaign = self.activated(max_issuances=2)
        run = cs.execute_campaign(campaign)
        self.assertEqual(run.issued, 2)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.COMPLETED)

    def test_campaign_expires_after_active_until(self):
        c = self.customer("منقضی")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated(active_until=timezone.now() + dt.timedelta(hours=1))
        run = cs.execute_campaign(campaign, now=timezone.now() + dt.timedelta(hours=2))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.EXPIRED)
        self.assertEqual(run.issued, 0)

    def test_paused_campaign_does_not_issue(self):
        c = self.customer("متوقف")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated()
        cs.pause(campaign)
        run = cs.execute_campaign(campaign)
        self.assertEqual(run.issued, 0)
        self.assertEqual(CampaignIssuance.objects.count(), 0)

    def test_active_campaign_cannot_be_edited(self):
        campaign = self.activated()
        campaign.name = "تغییر"
        with self.assertRaises(cs.CampaignError):
            cs.save_campaign(campaign)

    def test_shared_code_campaign_issues_one_shared_coupon(self):
        a, b = self.customer("الف"), self.customer("ب")
        for c in (a, b):
            self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated(personalized=False, total_redemption_limit=10)
        cs.execute_campaign(campaign)
        coupons = set(CampaignIssuance.objects.values_list("coupon_id", flat=True))
        self.assertEqual(len(coupons), 1)
        self.assertIsNone(Coupon.objects.get(pk=coupons.pop()).customer)

    def test_event_trigger_runs_for_single_customer(self):
        a, b = self.customer("الف"), self.customer("ب")
        for c in (a, b):
            self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated(trigger_type=Campaign.Trigger.EVENT)
        cs.run_event_campaigns(self.store, a)
        self.assertEqual(list(CampaignIssuance.objects.values_list("customer_id", flat=True)), [a.pk])

    def test_scheduled_job_is_idempotent(self):
        c = self.customer("زمان‌بندی")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        self.activated(trigger_type=Campaign.Trigger.SCHEDULED)
        first = cs.run_due_campaigns()
        second = cs.run_due_campaigns()
        self.assertEqual(first["issued"], 1)
        self.assertEqual(second["issued"], 0)
        self.assertEqual(CampaignIssuance.objects.count(), 1)

    def test_expiry_reminder_sent_once(self):
        c = self.customer("یادآوری", email="r@example.com")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated(reminder_days_before_expiry=3, code_expires_at=timezone.now() + dt.timedelta(days=2))
        cs.execute_campaign(campaign)
        self.assertGreater(cs.send_expiry_reminders(), 0)
        self.assertEqual(cs.send_expiry_reminders(), 0)  # dedupe
        self.assertTrue(NotificationOutbox.objects.filter(event_key="coupon.expiring").exists())


class DeliveryValidityTests(MandatoryBase):
    """اعتبارِ کد از لحظه‌ی تحویل (نه صدور)."""

    def test_validity_anchored_to_first_successful_delivery(self):
        c = self.customer("تحویل", email="d@example.com")
        self.order(c, [(self.nike_shoe, 1)], when=self.mehr(3))
        campaign = self.activated(code_expires_at=None, code_valid_days=10, validity_from_delivery=True)
        cs.execute_campaign(campaign)
        coupon = CampaignIssuance.objects.get().coupon
        provisional = coupon.expires_at
        self.assertGreater(provisional, timezone.now() + dt.timedelta(days=16))   # 10 + ۷ روز مهلت
        self.assertIsNone(coupon.delivery_anchored_at)
        deliver_pending()                                      # ایمیل ارسال می‌شود (پیامک: اعتبار ندارد)
        coupon.refresh_from_db()
        self.assertIsNotNone(coupon.delivery_anchored_at)
        self.assertAlmostEqual((coupon.expires_at - coupon.delivery_anchored_at).total_seconds(), 10 * 86400, delta=1)
        anchored = coupon.delivery_anchored_at
        NotificationOutbox.objects.filter(event_key="coupon.issued", channel="sms").update(status="pending", attempts=0)
        deliver_pending()
        coupon.refresh_from_db()
        self.assertEqual(coupon.delivery_anchored_at, anchored)  # فقط اولین تحویل

    def test_validation_requires_days(self):
        c = self.campaign(code_expires_at=None, code_valid_days=None, validity_from_delivery=True)
        self.assertTrue(any("تحویل" in e for e in cs.validate_campaign(c)))
