"""Promotional notifications vs rewards: a reward is issued and visible in the customer's account regardless of whether a promotional
notification may be (or can be) delivered. No consent is invented: a customer without recorded consent is never messaged, and skipped
rows are final (no retroactive send after a later opt-in)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.cart.models import Coupon
from apps.cart.services import coupon_service
from apps.customers.services import consent_service
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.tests.test_occasions import OccasionBase, jd
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import RetryNotAllowed, deliver_pending, retry_notification
from apps.sms.models import SmsOutboxItem


class PromotionalDeliveryIndependenceTests(OccasionBase):
    def birthday(self, **customer_kw):
        c = self.customer_with_order("متولد", email="b@example.com", birth_date=jd(1370, 5, 5), **customer_kw)
        campaign = self.occ(Campaign.Occasion.BIRTHDAY, name="تولد")
        run = self.go(campaign, jd(1405, 5, 5))
        return c, campaign, run

    def promo_mails(self, c):
        code = Coupon.objects.get(customer=c).code
        return [m for m in mail.outbox if code in m.body]  # setup orders also send transactional mail — only count the reward message

    def rows(self):
        return {r.channel: r for r in NotificationOutbox.objects.filter(event_key="occasion.birthday")}

    def test_customer_without_consent_still_gets_the_reward_and_sees_it_but_no_message(self):
        c, _, run = self.birthday(sms=False, mail=False)  # exactly the post-migration state of an existing customer
        self.assertEqual(run.issued, 1)
        coupon = Coupon.objects.get(customer=c)
        self.assertEqual(CampaignIssuance.objects.get().coupon_id, coupon.pk)
        self.assertEqual([x["coupon"].pk for x in coupon_service.customer_coupons(self.store, c)], [coupon.pk])
        rows = self.rows()
        self.assertEqual({(r.status, r.skip_reason) for r in rows.values()}, {("skipped", "no_promotional_consent")})
        deliver_pending()
        self.assertEqual((len(self.promo_mails(c)), SmsOutboxItem.objects.count()), (0, 0))

    def test_reward_is_visible_on_the_account_page_without_any_notification(self):
        c, _, _ = self.birthday(sms=False, mail=False)
        coupon = Coupon.objects.get(customer=c)
        client = Client()
        client.force_login(c.user)
        page = client.get(reverse("customers:account"))
        self.assertContains(page, coupon.code)

    def test_channels_are_independent_only_the_consented_channel_is_notified(self):
        c, _, _ = self.birthday(sms=False, mail=True)
        rows = self.rows()
        self.assertEqual((rows["sms"].status, rows["email"].status), ("skipped", "pending"))
        deliver_pending()
        self.assertEqual(len(self.promo_mails(c)), 1)

    def test_skipped_rows_are_final_a_later_opt_in_does_not_resend_but_never_blocks_the_reward(self):
        c, _, _ = self.birthday(sms=False, mail=False)
        consent_service.set_promotional_consent(c, source="account", sms=True, email=True)
        deliver_pending()
        self.assertEqual((len(self.promo_mails(c)), SmsOutboxItem.objects.count()), (0, 0))
        for row in self.rows().values():
            with self.assertRaises(RetryNotAllowed):
                retry_notification(row)
        self.assertEqual(Coupon.objects.filter(customer=c).count(), 1)

    def test_delivery_failure_never_rolls_back_or_hides_the_reward(self):
        c, _, run = self.birthday()
        with patch("apps.notifications.services.notification_service._send_email", side_effect=RuntimeError("smtp down")):
            deliver_pending()
        self.assertEqual(self.rows()["email"].status, "failed")
        self.assertEqual((run.issued, Coupon.objects.filter(customer=c).count(), CampaignIssuance.objects.count()), (1, 1, 1))
        self.assertEqual(len(coupon_service.customer_coupons(self.store, c)), 1)
