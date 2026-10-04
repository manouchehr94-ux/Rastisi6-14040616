"""پنل مدیریتِ کمپین‌ها/مناسبت‌ها و اعلان‌ها: دسترسی، ایزولاسیونِ Store، فرم، پیش‌نمایش،
فعال‌سازی/اجرا، قالب‌ها، ارسالِ آزمایشی، تاریخچه و تلاشِ دوباره."""

import json
from decimal import Decimal

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Coupon
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.tests.base import EngagementBase, jdt
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.stores.models import Store, StoreMembership

M = 1_000_000


class CampaignAdminTests(CouponViewsTestCase, EngagementBase):
    """EngagementBase.setUp سپس تنظیمِ ورودِ ادمین (CouponViewsTestCase.setUp)."""

    def setUp(self):
        CouponViewsTestCase.setUp(self)
        EngagementBase.setUp(self)
        self.nike_shoe = self.product("کفش نایک", 12 * M, category=self.cat_shoe, brand=self.nike)

    def form_data(self, **kw):
        tree = {"type": "group", "op": "and", "children": [
            {"type": "group", "op": "or", "children": [
                {"type": "line_match", "category_ids": [self.cat_bag.pk], "colors": ["زیتونی"]},
                {"type": "line_match", "category_ids": [self.cat_shoe.pk], "brand_ids": [self.nike.pk]},
            ]},
            {"type": "order_total", "op": "gt", "value": str(10 * M)},
            {"type": "shipping_city", "values": ["شیراز"]},
        ]}
        data = {
            "name": "مهر–آبان", "description": "", "trigger_type": "manual", "rules_json": json.dumps(tree),
            "rule_scope": "aggregate", "period_mode": "jalali_months", "period_jalali_year": "۱۴۰۵",
            "period_start_month": "7", "period_end_month": "8", "valid_payment_statuses": ["paid"],
            "amount_basis": "net_total", "reward_type": "coupon", "coupon_type": "percent", "coupon_value": "30",
            "coupon_max_discount": "4000000", "coupon_min_order": "0", "code_prefix": "mehr", "personalized": "on",
            "code_valid_days": "30", "total_redemption_limit": "1", "per_customer_limit": "1",
            "channels": ["sms", "email"], "occasion_offset_days": "0",
        }
        data.update(kw)
        return data

    def test_list_and_form_render_and_schema_is_store_scoped(self):
        other = Store.objects.create(name="دیگر", slug="adm-other", status=Store.Status.ACTIVE)
        from apps.catalog.models import Brand

        Brand.objects.create(store=other, name="OtherBrand", slug="ob")
        r = self.client.get(reverse("dashboard:campaign-list"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("dashboard:campaign-add"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="rule-builder"')
        self.assertContains(r, "Nike")
        self.assertNotContains(r, "OtherBrand")

    def test_create_edit_activate_preview_run_flow_for_mandatory_campaign(self):
        winner = self.customer("برنده")
        self.order(winner, [(self.nike_shoe, 1)], when=jdt(1405, 7, 9))
        loser = self.customer("بازنده")
        self.order(loser, [(self.nike_shoe, 1)], when=jdt(1405, 9, 9))  # خارج از بازه

        r = self.client.post(reverse("dashboard:campaign-add"), self.form_data())
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        campaign = Campaign.objects.get()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertEqual((campaign.period_jalali_year, campaign.period_start_month, campaign.period_end_month), (1405, 7, 8))
        self.assertEqual(campaign.code_prefix, "MEHR")
        self.assertEqual(campaign.rules["children"][0]["op"], "or")           # گروه OR حفظ شد

        # پیش‌نمایش (HTMX) — فقط شمارش، بدون صدور
        r = self.client.post(reverse("dashboard:campaign-preview", args=[campaign.pk]))
        self.assertContains(r, "برنده")
        self.assertNotContains(r, "بازنده")
        self.assertEqual(CampaignIssuance.objects.count(), 0)

        # اجرا پیش از فعال‌سازی ممکن نیست
        self.client.post(reverse("dashboard:campaign-run", args=[campaign.pk]))
        self.assertEqual(CampaignIssuance.objects.count(), 0)

        r = self.client.post(reverse("dashboard:campaign-activate", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.ACTIVE)

        # کمپینِ فعال ویرایش‌پذیر نیست
        r = self.client.post(reverse("dashboard:campaign-edit", args=[campaign.pk]), self.form_data(name="تغییر"))
        campaign.refresh_from_db()
        self.assertEqual(campaign.name, "مهر–آبان")

        self.client.post(reverse("dashboard:campaign-run", args=[campaign.pk]))
        issuance = CampaignIssuance.objects.get()
        self.assertEqual(issuance.customer, winner)
        self.assertEqual(issuance.coupon.customer, winner)

        for tab in ("overview", "issued", "redemptions"):
            r = self.client.get(reverse("dashboard:campaign-detail", args=[campaign.pk]) + f"?tab={tab}")
            self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("dashboard:campaign-detail", args=[campaign.pk]) + "?tab=issued")
        self.assertContains(r, issuance.coupon.code)

        r = self.client.post(reverse("dashboard:campaign-pause", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.PAUSED)

    def test_invalid_rules_and_config_are_rejected_with_message(self):
        bad_tree = json.dumps({"type": "group", "op": "or", "children": [{"type": "evil"}]})
        r = self.client.post(reverse("dashboard:campaign-add"), self.form_data(rules_json=bad_tree))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "مجاز نیست")
        self.assertEqual(Campaign.objects.count(), 0)
        r = self.client.post(reverse("dashboard:campaign-add"), self.form_data(period_start_date="abc", period_mode="dates"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_incomplete_campaign_cannot_be_activated(self):
        self.client.post(reverse("dashboard:campaign-add"), self.form_data(coupon_value="0", code_valid_days=""))
        campaign = Campaign.objects.get()
        self.client.post(reverse("dashboard:campaign-activate", args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_cross_store_references_in_rules_are_rejected(self):
        from apps.catalog.models import Brand

        other = Store.objects.create(name="دیگر", slug="adm-other2", status=Store.Status.ACTIVE)
        foreign = Brand.objects.create(store=other, name="Foreign", slug="fb")
        tree = json.dumps({"type": "line_match", "brand_ids": [foreign.pk]})
        r = self.client.post(reverse("dashboard:campaign-add"), self.form_data(rules_json=tree))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_other_store_campaign_is_404(self):
        other = Store.objects.create(name="دیگر", slug="adm-other3", status=Store.Status.ACTIVE)
        foreign = Campaign.objects.create(store=other, name="x")
        for name in ("campaign-detail", "campaign-edit", "campaign-activate", "campaign-run", "campaign-preview", "campaign-delete"):
            url = reverse(f"dashboard:{name}", args=[foreign.pk])
            r = self.client.post(url) if name not in ("campaign-detail", "campaign-edit") else self.client.get(url)
            self.assertEqual(r.status_code, 404, name)

    def test_occasion_campaign_creation_from_form(self):
        data = self.form_data(trigger_type="occasion", occasion_kind="birthday", occasion_name="تولد", occasion_offset_days="0",
                              rules_json="{}", period_mode="none", coupon_value="20", coupon_max_discount="", code_valid_days="7")
        r = self.client.post(reverse("dashboard:campaign-add"), data)
        self.assertEqual(r.status_code, 302)
        c = Campaign.objects.get()
        self.assertEqual((c.trigger_type, c.occasion_kind, c.coupon_value), ("occasion", "birthday", Decimal("20")))
        self.assertEqual(cs.validate_campaign(c), [])

    def test_delete_only_clean_drafts(self):
        self.client.post(reverse("dashboard:campaign-add"), self.form_data())
        c = Campaign.objects.get()
        self.client.post(reverse("dashboard:campaign-delete", args=[c.pk]))
        self.assertFalse(Campaign.objects.exists())

    def test_permissions_analyst_reads_but_cannot_manage(self):
        self.client.post(reverse("dashboard:campaign-add"), self.form_data())
        campaign = Campaign.objects.get()
        self._login_as(StoreMembership.Role.ANALYST, "301")
        self.assertEqual(self.client.get(reverse("dashboard:campaign-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:campaign-detail", args=[campaign.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:campaign-add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-activate", args=[campaign.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-run", args=[campaign.pk])).status_code, 403)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_anonymous_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:campaign-list")).status_code, 302)


class CouponAdminAdvancedTests(CouponViewsTestCase):
    def test_form_saves_advanced_fields_and_validates(self):
        from apps.catalog.models import Category

        cat = Category.objects.create(store=self.store, name="ک", slug="adv-c")
        r = self.client.post(reverse("dashboard:coupon-add"), {
            "code": "adv1", "type": "percent", "value": "30", "max_discount": "4000000", "per_customer_limit": "2",
            "category_ids": [str(cat.pk)], "applies_to_gift_wrap": "on", "is_active": "on",
        })
        self.assertEqual(r.status_code, 302)
        c = Coupon.objects.get(code="ADV1")
        self.assertEqual((c.max_discount, c.per_customer_limit, c.restrictions), (Decimal("4000000"), 2, {"category_ids": [cat.pk]}))
        self.assertTrue(c.applies_to_gift_wrap)
        r = self.client.post(reverse("dashboard:coupon-add"), {"code": "bad150", "type": "percent", "value": "150", "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Coupon.objects.filter(code="BAD150").exists())

    def test_personal_codes_hidden_from_default_list(self):
        from apps.customers.models import Customer
        from django.contrib.auth import get_user_model

        u = get_user_model().objects.create_user(username="pc1", password="x12345678")
        cust = Customer.objects.create(user=u, full_name="مشتری اختصاصی", phone="09127770001")
        Coupon.objects.create(store=self.store, code="PERS-1", type="percent", value=10, customer=cust)
        Coupon.objects.create(store=self.store, code="PUB-1", type="percent", value=10)
        r = self.client.get(reverse("dashboard:coupon-list"))
        self.assertContains(r, "PUB-1")
        self.assertNotContains(r, "PERS-1")
        r = self.client.get(reverse("dashboard:coupon-list") + "?scope=personal")
        self.assertContains(r, "PERS-1")
        self.assertContains(r, "مشتری اختصاصی")
        self.assertNotContains(r, "PUB-1")


class NotificationAdminTests(CouponViewsTestCase):
    def test_templates_list_and_edit_save_preview_reset(self):
        r = self.client.get(reverse("dashboard:notification-templates"))
        self.assertContains(r, "ثبت سفارش")
        url = reverse("dashboard:notification-template-edit", args=["coupon.issued"])
        self.assertContains(self.client.get(url), "{discount_code}")
        r = self.client.post(url, {
            "sms_enabled": "on", "sms_body": "کد شما {discount_code}", "email_enabled": "on",
            "email_subject": "هدیه {customer_name}", "email_body": "سلام {customer_name} کد {discount_code}",
        })
        self.assertEqual(r.status_code, 302)
        row = NotificationTemplate.objects.get(store=self.store, event_key="coupon.issued", channel="sms")
        self.assertEqual(row.body, "کد شما {discount_code}")
        # متغیرِ نامعتبر ⇒ ذخیره نمی‌شود و خطا نشان می‌دهد
        r = self.client.post(url, {"sms_enabled": "on", "sms_body": "{password}", "email_enabled": "on",
                                   "email_subject": "s", "email_body": "b"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "{password}")
        row.refresh_from_db()
        self.assertEqual(row.body, "کد شما {discount_code}")
        # پیش‌نمایش
        r = self.client.post(reverse("dashboard:notification-template-preview", args=["coupon.issued"]),
                             {"channel": "sms", "sms_body": "سلام {customer_name}"})
        self.assertContains(r, "سلام سارا احمدی")
        r = self.client.post(reverse("dashboard:notification-template-preview", args=["coupon.issued"]),
                             {"channel": "sms", "sms_body": "{evil}"})
        self.assertContains(r, "ناشناخته")
        # بازنشانی
        self.client.post(url, {"action": "reset", "channel": "sms"})
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, event_key="coupon.issued", channel="sms").exists())

    def test_unknown_event_404(self):
        self.assertEqual(self.client.get(reverse("dashboard:notification-template-edit", args=["no.such"])).status_code, 404)

    def test_test_send_email_delivers_and_marks_row(self):
        url = reverse("dashboard:notification-template-test", args=["order.created"])
        r = self.client.post(url, {"channel": "email", "recipient": "qa@example.com"})
        self.assertEqual(r.status_code, 302)
        row = NotificationOutbox.objects.get(is_test=True)
        self.assertEqual(row.status, NotificationOutbox.Status.SENT)
        self.assertEqual([m.to for m in mail.outbox], [["qa@example.com"]])
        self.assertIn("DM-12345", mail.outbox[0].body)

    def test_test_send_invalid_recipient_and_rate_limit(self):
        url = reverse("dashboard:notification-template-test", args=["coupon.issued"])
        self.client.post(url, {"channel": "email", "recipient": "not-an-email"})
        row = NotificationOutbox.objects.get()
        self.assertEqual((row.status, row.skip_reason), ("skipped", "invalid_recipient"))
        self.assertEqual(len(mail.outbox), 0)
        from django.core.cache import cache

        cache.clear()
        for _ in range(11):
            self.client.post(url, {"channel": "email", "recipient": "qa@example.com"})
        self.assertLessEqual(NotificationOutbox.objects.filter(is_test=True, status="sent").count(), 10)

    def test_history_filters_and_store_isolation_and_retry(self):
        other = Store.objects.create(name="دیگر", slug="adm-other4", status=Store.Status.ACTIVE)
        NotificationOutbox.objects.create(channel="sms", store=other, body="SECRET-OTHER", recipient_phone="09120000000", event_key="x")
        mine_failed = NotificationOutbox.objects.create(
            channel="sms", store=self.store, body="پیام من", recipient_phone="09121110000", event_key="order.created",
            status="dead", last_error="timeout", provider="kavenegar", attempts=5,
        )
        NotificationOutbox.objects.create(channel="email", store=self.store, body="ایمیل", recipient_email="a@b.com",
                                          event_key="coupon.issued", status="sent")
        url = reverse("dashboard:notification-history")
        r = self.client.get(url)
        self.assertContains(r, "پیام من")
        self.assertNotContains(r, "SECRET-OTHER")
        self.assertContains(self.client.get(url + "?status=dead"), "پیام من")
        self.assertNotContains(self.client.get(url + "?status=sent"), "پیام من")
        self.assertContains(self.client.get(url + "?channel=sms&provider=kave&error=time"), "پیام من")
        self.assertNotContains(self.client.get(url + "?event=coupon.issued"), "پیام من")
        self.assertContains(self.client.get(url + "?q=09121110000"), "پیام من")
        self.assertEqual(self.client.get(url + "?date_from=garbage&date_to=").status_code, 200)
        r = self.client.post(reverse("dashboard:notification-retry", args=[mine_failed.pk]))
        mine_failed.refresh_from_db()
        self.assertEqual(mine_failed.status, "pending")
        # اعلانِ Store دیگر قابلِ تلاش نیست
        foreign = NotificationOutbox.objects.filter(store=other).get()
        foreign.status = "failed"
        foreign.save()
        self.assertEqual(self.client.post(reverse("dashboard:notification-retry", args=[foreign.pk])).status_code, 404)

    def test_permissions(self):
        self._login_as(StoreMembership.Role.ANALYST, "401")
        for name, args in (("notification-templates", []), ("notification-history", []), ("notification-template-edit", ["order.created"])):
            self.assertEqual(self.client.get(reverse(f"dashboard:{name}", args=args)).status_code, 403, name)
        self.assertEqual(self.client.post(reverse("dashboard:notification-template-test", args=["order.created"]),
                                          {"channel": "email", "recipient": "a@b.com"}).status_code, 403)
