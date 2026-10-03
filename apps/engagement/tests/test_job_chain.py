"""End-to-end chain of the existing cron commands (no scheduler involved — each command is invoked exactly as cron would):
run_engagement_jobs (campaign + birthday issuance → outbox) → process_notification_outbox (email + SMS routing) →
idempotent re-runs, safe restart after a crash, failure isolation, health check. Provider HTTP is mocked; email uses locmem."""

from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.cart.models import Coupon
from apps.core.models import ShopSettings
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.tests.base import EngagementBase, jdt
from apps.engagement.tests.test_occasions import jd
from apps.notifications.models import NotificationOutbox
from apps.notifications.tests.test_verify_delivery_channels import set_platform
from apps.sms.models import SmsBalance, SmsOutboxItem, SmsTemplate

OK = {"return": {"status": 200}, "entries": [{"messageid": 77}]}


def http(payload=OK):
    response = MagicMock()
    response.json.return_value = payload
    return patch("requests.post", return_value=response)


def health():
    out = StringIO()
    code = 0
    try:
        call_command("check_background_jobs", stdout=out)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue()


class JobChainTests(EngagementBase):
    def setUp(self):
        super().setUp()
        SmsTemplate.ensure_defaults()
        shop = ShopSettings.load(store=self.store)
        shop.sms_enabled = True
        shop.sms_backend = ShopSettings.SmsBackend.CONSOLE  # = Platform method
        shop.save()
        set_platform("kavenegar", kavenegar_api_key="k-chain", kavenegar_sender="1000")
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        item = self.product("کالا", 1_000_000)
        self.buyer = self.customer("خریدار", email="buyer@example.com")
        self.order(self.buyer, [(item, 1)], when=jdt(1405, 5, 1))
        self.bday = self.customer("متولد", email="bday@example.com", birth_date=jd(1370, 5, 5))
        self.order(self.bday, [(item, 1)], when=jdt(1405, 5, 1))
        scheduled = cs.save_campaign(Campaign(
            store=self.store, name="زمان‌بندی", trigger_type=Campaign.Trigger.SCHEDULED, rules={"type": "order_total", "op": "gte", "value": "1"},
            coupon_type="percent", coupon_value=10, code_valid_days=5, code_prefix="SCH", channels=["sms", "email"],
        ))
        cs.activate(scheduled)
        birthday = cs.save_campaign(Campaign(
            store=self.store, name="تولد", trigger_type=Campaign.Trigger.OCCASION, occasion_kind=Campaign.Occasion.BIRTHDAY,
            occasion_name="تولد", reward_type=Campaign.Reward.COUPON, coupon_type="percent", coupon_value=20, code_valid_days=7,
            code_prefix="BDY", per_customer_limit=1, total_redemption_limit=1, channels=["sms", "email"],
        ))
        cs.activate(birthday)
        now_patch = patch("apps.engagement.services.campaign_service.store_now", return_value=jdt(1405, 5, 5, 12))
        now_patch.start()
        self.addCleanup(now_patch.stop)
        mail.outbox.clear()

    def cmd(self, command, *args):
        out = StringIO()
        call_command(command, *args, stdout=out)
        return out.getvalue()

    def promo_mails(self):
        codes = list(Coupon.objects.filter(code__regex=r"^(SCH|BDY)-").values_list("code", flat=True))
        return [m for m in mail.outbox if any(c in m.body for c in codes)]

    def test_full_chain_issues_notifies_once_and_is_idempotent_on_restart(self):
        self.cmd("run_engagement_jobs", "--no-deliver")
        issued = CampaignIssuance.objects.count()
        self.assertEqual(issued, 3)  # scheduled → buyer + birthday customer; birthday → birthday customer
        self.assertEqual(self.promo_mails(), [])  # --no-deliver: queued only
        self.assertGreater(NotificationOutbox.objects.filter(status="pending").count(), 0)
        with http() as post:
            self.cmd("process_notification_outbox")
            first_http, first_mail = post.call_count, len(self.promo_mails())
            # restart / overlapping cron: nothing is sent twice
            self.cmd("process_notification_outbox")
            self.cmd("run_engagement_jobs")
        self.assertEqual((post.call_count, len(self.promo_mails())), (first_http, first_mail))
        self.assertEqual(first_mail, 3)  # one e-mail per issuance
        self.assertEqual(first_http, 3)  # one SMS per issuance through the platform provider
        self.assertEqual(CampaignIssuance.objects.count(), issued)
        self.assertEqual(SmsOutboxItem.objects.count(), 0)

    def test_crash_mid_delivery_is_recovered_by_the_next_run_without_duplicates(self):
        self.cmd("run_engagement_jobs", "--no-deliver")
        row = NotificationOutbox.objects.filter(channel="email", status="pending").first()
        NotificationOutbox.objects.filter(pk=row.pk).update(status="sending", claimed_at=timezone.now() - timedelta(hours=1))
        with http():
            self.cmd("process_notification_outbox")
            self.cmd("process_notification_outbox")
        row.refresh_from_db()
        self.assertEqual(row.status, "sent")
        self.assertEqual(len([m for m in mail.outbox if row.recipient_email in m.to and row.subject == m.subject]), 1)

    def test_provider_outage_is_isolated_visible_in_health_and_recovers(self):
        self.cmd("run_engagement_jobs", "--no-deliver")
        failing = {"return": {"status": 418, "message": "down"}}
        with http(failing):
            with self.assertRaises(CommandError):  # whole batch of SMS failed ⇒ non-zero exit for monitoring
                # e-mails still go out in the same batch, so make the batch all-failing by blocking e-mail too
                with patch("apps.notifications.services.notification_service._send_email", side_effect=RuntimeError("smtp down")):
                    self.cmd("process_notification_outbox")
        self.assertGreater(NotificationOutbox.objects.filter(status="failed").count(), 0)
        NotificationOutbox.objects.filter(status="failed").update(created_at=timezone.now() - timedelta(hours=3))
        code, out = health()
        self.assertEqual(code, 2)
        self.assertIn("CRITICAL", out)
        NotificationOutbox.objects.filter(status="failed").update(next_attempt_at=timezone.now() - timedelta(minutes=1))
        with http():
            self.cmd("process_notification_outbox")
        self.assertEqual(NotificationOutbox.objects.filter(status__in=["failed", "pending", "sending"]).count(), 0)
        self.assertEqual(health()[0], 0)

    def test_housekeeping_commands_are_safe_noops_with_default_configuration(self):
        for command in ("expire_unpaid_orders", "expire_inventory_reservations", "refresh_customer_segments"):
            self.cmd(command)
        out = self.cmd("expire_unpaid_orders", "--dry-run")
        self.assertIn("candidates=0", out)
        self.assertEqual(ShopSettings.load(store=self.store).unpaid_online_order_ttl_minutes, 0)
