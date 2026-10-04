from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.tests.base import EngagementBase, jdt


class RunEngagementJobsCommandTests(EngagementBase):
    def test_command_issues_once_and_delivers_notifications(self):
        item = self.product("کالا", 1_000_000)
        c = self.customer("م", email="cmd@example.com")
        self.order(c, [(item, 1)], when=jdt(1405, 7, 3))
        campaign = cs.save_campaign(Campaign(
            store=self.store, name="زمان‌بندی", trigger_type=Campaign.Trigger.SCHEDULED,
            rules={"type": "order_total", "op": "gte", "value": "1"}, coupon_type="percent", coupon_value=10,
            code_valid_days=5, code_prefix="CMD",
        ))
        cs.activate(campaign)
        out = StringIO()
        call_command("run_engagement_jobs", stdout=out)
        call_command("run_engagement_jobs", stdout=out)
        self.assertEqual(CampaignIssuance.objects.count(), 1)
        code = CampaignIssuance.objects.get().coupon.code
        self.assertEqual(len([m for m in mail.outbox if code in m.body]), 1)
        call_command("run_engagement_jobs", "--no-deliver", stdout=out)
        self.assertIn("کمپین‌هایِ اجراشده", out.getvalue())
