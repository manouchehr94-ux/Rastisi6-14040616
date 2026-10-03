"""H8: اجرایِ همزمانِ یک کمپین (دو job/دو مدیر) — فقط PostgreSQL. هر مشتری دقیقاً یک پاداش و یک اعلان به‌ازای کانال می‌گیرد."""

import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.cart.models import Coupon
from apps.customers.models import Customer
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.notifications.models import NotificationOutbox
from apps.stores.models import Store

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "نیازمندِ PostgreSQL")
class ParallelCampaignRunTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.store = Store.objects.create(name="رقابتِ کمپین", slug="camp-race", status=Store.Status.ACTIVE)
        self.customers = []
        for i in range(12):
            user = User.objects.create_user(username=f"0914000{i:04d}", password="x12345678")
            c = Customer.objects.create(
                user=user, full_name=f"c{i}", phone=f"0914000{i:04d}", email=f"c{i}@example.com",
                accepts_promotional_sms=True, accepts_promotional_email=True,
            )
            self.customers.append(c)
        self.campaign = cs.save_campaign(Campaign(
            store=self.store, name="همزمان", trigger_type=Campaign.Trigger.MANUAL, rules={}, reward_type=Campaign.Reward.COUPON,
            coupon_type="percent", coupon_value=Decimal("10"), code_prefix="RACE", personalized=True, channels=["email"],
            total_redemption_limit=1, per_customer_limit=1,
        ))
        self.campaign.status = Campaign.Status.ACTIVE
        self.campaign.save()
        from apps.customers.models import CustomerProfile

        for c in self.customers:  # مشتریِ Store بودن (ایزولاسیون): پروفایلِ همین فروشگاه
            CustomerProfile.objects.create(store=self.store, customer=c)

    def run_parallel(self, n):
        barrier = threading.Barrier(n)
        runs, errors = [], []

        def worker():
            try:
                barrier.wait()
                runs.append(cs.execute_campaign(Campaign.objects.get(pk=self.campaign.pk)))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker) for _ in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return runs, errors

    def test_two_parallel_executions_never_duplicate_rewards_or_notifications(self):
        runs, errors = self.run_parallel(2)
        self.assertEqual(errors, [])
        total = len(self.customers)
        self.assertEqual(CampaignIssuance.objects.filter(campaign=self.campaign).count(), total)
        self.assertEqual(sum(r.issued for r in runs), total)
        self.assertEqual(sum(r.issued + r.skipped_existing for r in runs), total * 2)
        self.assertEqual(sum(r.errors for r in runs), 0)
        coupons = Coupon.objects.filter(store=self.store, customer__in=self.customers)
        self.assertEqual(coupons.count(), total)
        self.assertEqual(len({c.customer_id for c in coupons}), total)
        mails = NotificationOutbox.objects.filter(store=self.store, channel="email", metadata__campaign_id=self.campaign.pk)
        self.assertEqual(mails.count(), total)
        self.assertEqual(len({m.recipient_email for m in mails}), total)

    def test_rerun_after_completion_is_a_no_op(self):
        self.run_parallel(1)
        before = (CampaignIssuance.objects.count(), Coupon.objects.count(), NotificationOutbox.objects.count())
        runs, errors = self.run_parallel(3)
        self.assertEqual(errors, [])
        self.assertEqual(sum(r.issued for r in runs), 0)
        self.assertEqual((CampaignIssuance.objects.count(), Coupon.objects.count(), NotificationOutbox.objects.count()), before)
