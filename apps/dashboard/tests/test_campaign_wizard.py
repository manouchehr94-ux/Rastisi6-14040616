"""رابطِ ساده‌ی ساختِ کمپین/مناسبت (طرحِ v2): رندر، ذخیره/ویرایش، انواعِ هدیه و مناسبت،
مخاطبِ خاص، پیش‌نویس، مجوزها، ایزولاسیونِ فروشگاه، و قانونِ قطعیِ «متنِ پیامک فقط از پلتفرم».

هیچ پیامک/ایمیلِ واقعی ارسال نمی‌شود: همه‌چیز در دیتابیسِ آزمایشیِ تست و با outbox است."""

import json
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Coupon
from apps.core.jalali_utils import format_jalali
from apps.core.utils import to_fa_digits
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.services import occasions, simple_setup
from apps.engagement.tests.base import EngagementBase, jdt
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.notifications.services import template_service
from apps.sms.events import PLATFORM_MANAGED_EVENTS
from apps.sms.models import SmsTemplate
from apps.stores.models import Store, StoreMembership

M = 1_000_000


class WizardBase(CouponViewsTestCase, EngagementBase):
    def setUp(self):
        CouponViewsTestCase.setUp(self)
        EngagementBase.setUp(self)

    def occasion_payload(self, **kw):
        data = {
            "name": "هدیه تولد", "trigger_type": "occasion", "occasion_kind": "birthday", "audience_kind": "all",
            "reward_type": "coupon", "coupon_type": "percent", "coupon_value": "۱۵", "code_valid_days": "7",
            "personalized": "on", "per_customer_limit": "1", "occasion_offset_days": "0", "channels_explicit": "1",
            "rules_json": "{}",
        }
        data.update(kw)
        return data

    def campaign_payload(self, **kw):
        data = {
            "name": "جشن پاییزی", "trigger_type": "manual", "audience_kind": "all", "reward_type": "coupon",
            "coupon_type": "percent", "coupon_value": "20", "code_valid_days": "14", "personalized": "on",
            "per_customer_limit": "1", "channels_explicit": "1", "rules_json": "{}",
        }
        data.update(kw)
        return data

    def post_new(self, payload):
        return self.client.post(reverse("dashboard:campaign-add"), payload)

    def last(self):
        return Campaign.objects.order_by("-pk").first()


class WizardRenderTests(WizardBase):
    def test_both_pages_render_the_approved_design_without_any_sms_text_field(self):
        for kind, marker in (("occasions", "یک مناسبت جدید بسازیم"), ("campaigns", "یک کمپین جذاب بسازیم")):
            r = self.client.get(reverse("dashboard:campaign-add") + f"?kind={kind}")
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'id="cw-root"')
            self.assertContains(r, marker)
            self.assertContains(r, "🔒 فقط‌خواندنی")
            html = r.content.decode()
            self.assertNotIn("custom_sms_body", html)
            self.assertNotIn("<textarea", html.split('id="cw-step3"')[1].split("تنظیمات پیشرفته فعالیت")[0])
            self.assertEqual(r.context["form"]["trigger_type"].value(), "occasion" if kind == "occasions" else "manual")

    def test_new_occasion_page_defaults_to_birthday_with_sms_off(self):
        r = self.client.get(reverse("dashboard:campaign-add") + "?kind=occasions")
        form = r.context["form"]
        self.assertEqual((form["occasion_kind"].value(), form["audience_kind"].value()), ("birthday", "all"))
        self.assertEqual(form["channels"].value(), [])  # پیش‌فرضِ طرح: هیچ کانالی روشن نیست
        self.assertContains(r, 'name="channels_explicit" value="1"')

    def test_edit_prefills_and_locks_mode(self):
        self.post_new(self.occasion_payload(code_prefix="tav", coupon_max_discount="3000000"))
        c = self.last()
        r = self.client.get(reverse("dashboard:campaign-edit", args=[c.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'value="هدیه تولد"')
        self.assertContains(r, 'value="TAV"')
        self.assertNotContains(r, "cw-mode-tabs")  # نوعِ پیشنهاد در ویرایش قفل است
        self.assertTrue(r.context["is_occasion"])

    def test_extra_audience_sources_are_store_scoped(self):
        from apps.catalog.models import Category

        other = Store.objects.create(name="دیگر", slug="wiz-other", status=Store.Status.ACTIVE)
        Category.objects.create(store=other, name="دسته‌ی-فروشگاه-دیگر", slug="oc1")
        mine = Category.objects.create(store=self.store, name="دسته‌ی-من", slug="mc1")
        r = self.client.get(reverse("dashboard:campaign-add") + "?kind=campaigns")
        self.assertContains(r, "دسته‌ی-من")
        self.assertNotContains(r, "دسته‌ی-فروشگاه-دیگر")
        self.assertIn(mine.pk, [o[0] for o in r.context["wizard_config"] and dict((k, v) for k, _l, v in r.context["extra_groups"])["category"]])


class CitySourceTests(WizardBase):
    def test_city_choices_come_from_store_customer_addresses_only(self):
        from apps.customers.models import Address

        item = self.product("کالا", M)
        mine = self.customer("من")
        self.order(mine, [(item, 1)], when=timezone.now(), city="اصفهان")  # آدرسِ سفارش/پروفایل
        Address.objects.filter(customer=mine).update(city="اصفهان")
        stranger = self.customer("غریبه")
        Address.objects.create(customer=stranger, receiver_name="غ", phone=stranger.phone, province="x", city="شهر-بیگانه", postal_code="1111111111", full_address="x")
        r = self.client.get(reverse("dashboard:campaign-add") + "?kind=campaigns")
        cities = [c[0] for k, _l, opts in r.context["extra_groups"] if k == "city" for c in opts]
        self.assertIn("اصفهان", cities)
        self.assertNotIn("شهر-بیگانه", cities)


class WizardSaveTests(WizardBase):
    # ---- مناسبت‌ها ------------------------------------------------------------
    def test_create_each_occasion_kind_as_draft_without_issuing_or_sending(self):
        cases = [
            ("birthday", {}, {}),
            ("registration_anniversary", {}, {}),
            ("first_purchase_anniversary", {}, {}),
            ("reactivation", {"occ_days": "۹۰"}, {"days": 90}),
            ("order_milestone", {"occ_n": "۳"}, {"n": 3}),
            ("spending_milestone", {"occ_amount": "۵٬۰۰۰٬۰۰۰"}, {"amount": 5_000_000}),
            ("holiday", {"occ_month": "9", "occ_day": "۳۰"}, {"month": 9, "day": 30}),
            ("custom_date", {"occ_date": "۱۴۰۵/۰۸/۱۵"}, None),
        ]
        for kind, extra, params in cases:
            r = self.post_new(self.occasion_payload(name=f"م-{kind}", occasion_kind=kind, **extra))
            self.assertEqual(r.status_code, 302, (kind, getattr(r, "context", None) and r.context["form"].errors))
            c = Campaign.objects.get(name=f"م-{kind}")
            self.assertEqual((c.status, c.trigger_type, c.occasion_kind), ("draft", "occasion", kind))
            if params is not None:
                self.assertEqual(c.occasion_params, params)
            self.assertEqual(cs.validate_campaign(c), [], kind)
        self.assertEqual(CampaignIssuance.objects.count(), 0)
        self.assertEqual(Coupon.objects.filter(customer__isnull=False).count(), 0)
        self.assertEqual(NotificationOutbox.objects.filter(event_key__startswith="occasion.").count(), 0)

    def test_occasion_requires_a_kind(self):
        r = self.post_new(self.occasion_payload(occasion_kind=""))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "مناسبت را انتخاب کنید")
        self.assertFalse(Campaign.objects.exists())

    def test_occasion_offsets_and_reward_types(self):
        for offset in ("-3", "0", "1"):
            self.post_new(self.occasion_payload(name=f"o{offset}", occasion_offset_days=offset))
            self.assertEqual(Campaign.objects.get(name=f"o{offset}").occasion_offset_days, int(offset))
        r = self.post_new(self.occasion_payload(name="free", coupon_type="free_ship", coupon_value=""))
        self.assertEqual(r.status_code, 302)
        c = Campaign.objects.get(name="free")
        self.assertEqual((c.reward_type, c.coupon_type), ("coupon", "free_ship"))
        self.assertEqual(cs.validate_campaign(c), [])

    # ---- کمپین‌ها: انواعِ هدیه و زمان‌بندی ------------------------------------
    def test_campaign_reward_types_map_to_engine_fields(self):
        for choice, payload, expected in (
            ("percent", {"coupon_type": "percent", "coupon_value": "۲۵", "coupon_max_discount": "۱٬۰۰۰٬۰۰۰"}, ("coupon", "percent", Decimal(25), Decimal(M))),
            ("fixed", {"coupon_type": "fixed", "coupon_value": "۱۰۰٬۰۰۰"}, ("coupon", "fixed", Decimal(100000), None)),
            ("free_ship", {"coupon_type": "free_ship", "coupon_value": ""}, ("coupon", "free_ship", Decimal(0), None)),
            ("none", {"reward_type": "none"}, ("none", "percent", Decimal(20), None)),
        ):
            r = self.post_new(self.campaign_payload(name=f"ک-{choice}", **payload))
            self.assertEqual(r.status_code, 302, (choice, getattr(r, "context", None) and r.context["form"].errors))
            c = Campaign.objects.get(name=f"ک-{choice}")
            self.assertEqual((c.reward_type, c.coupon_type, c.coupon_value, c.coupon_max_discount), expected, choice)
            self.assertEqual(c.status, "draft")
        self.assertEqual(Coupon.objects.filter(customer__isnull=False).count(), 0)

    def test_campaign_timing_options(self):
        self.post_new(self.campaign_payload(name="دستی", trigger_type="manual"))
        self.post_new(self.campaign_payload(name="رویداد", trigger_type="event"))
        self.post_new(self.campaign_payload(name="زمان‌بندی", trigger_type="scheduled", active_from="۱۴۰۵/۰۸/۱۵"))
        self.assertEqual(Campaign.objects.get(name="دستی").trigger_type, "manual")
        self.assertEqual(Campaign.objects.get(name="رویداد").trigger_type, "event")
        sched = Campaign.objects.get(name="زمان‌بندی")
        self.assertEqual(sched.trigger_type, "scheduled")
        self.assertIsNotNone(sched.active_from)

    def test_invalid_numbers_are_rejected_with_message_and_nothing_saved(self):
        r = self.post_new(self.campaign_payload(coupon_max_discount="abc"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "عدد صحیح وارد کنید")
        r = self.post_new(self.campaign_payload(trigger_type="scheduled", active_from="not-a-date"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Campaign.objects.exists())

    # ---- مخاطبان ----------------------------------------------------------------
    def test_audience_presets_become_real_rule_trees(self):
        expected = {
            "all": {},
            "new": {"type": "registered", "mode": "within_days", "days": 30},
            "loyal": {"type": "lifetime_orders", "op": "gte", "value": "3"},
            "dormant": {"type": "days_since_last_purchase", "op": "gte", "value": "90"},
        }
        for kind, tree in expected.items():
            self.post_new(self.campaign_payload(name=f"a-{kind}", audience_kind=kind))
            self.assertEqual(Campaign.objects.get(name=f"a-{kind}").rules, tree, kind)

    def test_audience_presets_actually_select_the_right_customers(self):
        item = self.product("کالا", 1 * M)
        loyal = self.customer("وفادار")
        for i in range(3):
            self.order(loyal, [(item, 1)], when=jdt(1404, 1, 10 + i))
        casual = self.customer("معمولی")
        self.order(casual, [(item, 1)], when=timezone.now())
        self.post_new(self.campaign_payload(name="وفادارها", audience_kind="loyal"))
        eligible = set(cs.compute_eligible(Campaign.objects.get(name="وفادارها")))
        self.assertEqual(eligible, {loyal.pk})

    def test_specific_audience_city_category_tag_segment(self):
        from apps.catalog.models import Category
        from apps.customers.models import CustomerSegment, CustomerTag

        cat = Category.objects.create(store=self.store, name="ویژه", slug="wiz-cat")
        tag = CustomerTag.objects.create(store=self.store, name="vip")
        seg = CustomerSegment.objects.create(store=self.store, name="گروه الف")
        for extra_kind, values, leaf in (
            ("city", ["شیراز", "تهران"], {"type": "customer_city", "values": ["شیراز", "تهران"]}),
            ("category", [str(cat.pk)], {"type": "line_match", "category_ids": [cat.pk], "min_quantity": 1}),
            ("tag", [str(tag.pk)], {"type": "customer_tag_ids", "ids": [tag.pk]}),
            ("segment", [str(seg.pk)], {"type": "segment_ids", "ids": [seg.pk]}),
        ):
            r = self.post_new(self.campaign_payload(name=f"x-{extra_kind}", audience_kind="loyal", audience_extra_kind=extra_kind, audience_extra_values=values))
            self.assertEqual(r.status_code, 302, (extra_kind, getattr(r, "context", None) and r.context["form"].errors))
            tree = Campaign.objects.get(name=f"x-{extra_kind}").rules
            self.assertEqual(tree["op"], "and")
            self.assertEqual(tree["children"][1], leaf)
            self.assertEqual(tree["children"][0]["type"], "lifetime_orders")
            # رفت‌وبرگشت: همان انتخاب‌ها در ویرایش بازسازی می‌شوند
            detected = simple_setup.detect_audience(tree, self.store)
            self.assertEqual((detected["kind"], detected["extra_kind"]), ("loyal", extra_kind))

    def test_specific_audience_requires_a_selection_and_is_store_scoped(self):
        from apps.catalog.models import Category

        r = self.post_new(self.campaign_payload(audience_extra_kind="city", audience_extra_values=[]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "حداقل یک مورد")
        other = Store.objects.create(name="دیگر", slug="wiz-other2", status=Store.Status.ACTIVE)
        foreign = Category.objects.create(store=other, name="بیگانه", slug="foreign-cat")
        r = self.post_new(self.campaign_payload(audience_extra_kind="category", audience_extra_values=[str(foreign.pk)]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Campaign.objects.exists())
        r = self.post_new(self.campaign_payload(audience_extra_kind="category", audience_extra_values=["not-a-number"]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Campaign.objects.exists())

    def test_custom_rules_from_the_advanced_builder_are_still_supported(self):
        tree = {"type": "group", "op": "or", "children": [{"type": "customer_city", "values": ["شیراز"]}, {"type": "customer_type", "value": "new"}]}
        r = self.post_new(self.campaign_payload(audience_kind="custom", rules_json=json.dumps(tree)))
        self.assertEqual(r.status_code, 302)
        saved = self.last().rules
        self.assertEqual(saved["op"], "or")  # گروه OR دست‌نخورده
        self.assertEqual(simple_setup.detect_audience(saved, self.store)["kind"], "custom")
        bad = {"type": "evil"}
        r = self.post_new(self.campaign_payload(name="bad", audience_kind="custom", rules_json=json.dumps(bad)))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Campaign.objects.filter(name="bad").exists())

    # ---- ویرایش: اطلاعاتِ قبلی از بین نمی‌رود ------------------------------------
    def test_edit_keeps_every_legacy_field_not_shown_in_the_simple_ui(self):
        tree = {"type": "group", "op": "and", "children": [
            {"type": "customer_city", "values": ["شیراز"]}, {"type": "lifetime_orders", "op": "gte", "value": "2"},
            {"type": "customer_type", "value": "returning"},
        ]}
        legacy = Campaign.objects.create(
            store=self.store, name="قدیمی", description="توضیح داخلی", trigger_type="manual", rules=tree,
            period_mode="jalali_months", period_jalali_year=1405, period_start_month=7, period_end_month=8,
            rule_scope="same_order", amount_basis="grand_total", valid_payment_statuses=["paid", "pending"],
            coupon_type="fixed", coupon_value=Decimal(50000), coupon_min_order=Decimal(200000),
            code_prefix="OLD", personalized=False, code_valid_days=30, total_redemption_limit=100,
            per_customer_limit=2, per_customer_period_days=30, max_issuances=500, validity_from_delivery=True,
            coupon_applies_to_gift_wrap=True, channels=["email"], channels_explicit=False,
            custom_email_subject="موضوع قبلی", custom_email_body="سلام {customer_name} کد {discount_code}",
            custom_sms_body="متنِ پیامکِ قدیمیِ فروشنده", reminder_days_before_expiry=3,
        )
        r = self.client.get(reverse("dashboard:campaign-edit", args=[legacy.pk]))
        self.assertEqual(r.status_code, 200)
        form = r.context["form"]
        self.assertEqual(form["audience_kind"].value(), "custom")  # قواعدِ قبلی به‌عنوانِ «سفارشی» حفظ می‌شود
        self.assertTrue(r.context["audience_is_custom"])
        # ذخیره‌ی دوباره با همان مقادیرِ نمایش‌داده‌شده
        payload = {
            "name": "قدیمی (ویرایش‌شده)", "description": "توضیح داخلی", "trigger_type": "manual", "audience_kind": "custom",
            "rules_json": form["rules_json"].value(), "period_mode": "jalali_months", "period_jalali_year": "1405",
            "period_start_month": "7", "period_end_month": "8", "rule_scope": "same_order", "amount_basis": "grand_total",
            "valid_payment_statuses": ["paid", "pending"], "reward_type": "coupon", "coupon_type": "fixed",
            "coupon_value": "50000", "coupon_min_order": "200000", "code_prefix": "OLD", "code_valid_days": "30",
            "total_redemption_limit": "100", "per_customer_limit": "2", "per_customer_period_days": "30",
            "max_issuances": "500", "validity_from_delivery": "on", "coupon_applies_to_gift_wrap": "on",
            "channels": ["email"], "channels_explicit": "1", "reminder_days_before_expiry": "3",
        }
        r = self.client.post(reverse("dashboard:campaign-edit", args=[legacy.pk]), payload)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "قدیمی (ویرایش‌شده)")
        from apps.engagement.services import rules as rules_engine

        self.assertEqual(legacy.rules, rules_engine.validate_tree(tree, self.store))  # دقیقاً همان قواعدِ قبلی
        self.assertEqual((legacy.rule_scope, legacy.amount_basis, legacy.period_start_month), ("same_order", "grand_total", 7))
        self.assertEqual(legacy.valid_payment_statuses, ["paid", "pending"])
        self.assertEqual((legacy.total_redemption_limit, legacy.per_customer_limit, legacy.per_customer_period_days, legacy.max_issuances), (100, 2, 30, 500))
        self.assertTrue(legacy.validity_from_delivery and legacy.coupon_applies_to_gift_wrap and not legacy.personalized)
        self.assertEqual(legacy.coupon_min_order, Decimal(200000))
        # متن‌های قدیمی از فرم پاک/بازنویسی نمی‌شوند (ایمیلِ قدیمی حفظ؛ پیامکِ قدیمی دیگر هرگز ارسال نمی‌شود)
        self.assertEqual(legacy.custom_email_body, "سلام {customer_name} کد {discount_code}")
        self.assertEqual(legacy.custom_sms_body, "متنِ پیامکِ قدیمیِ فروشنده")

    def test_legacy_campaign_without_explicit_channels_shows_both_channels_on(self):
        legacy = Campaign.objects.create(store=self.store, name="ق", channels=[], channels_explicit=False)
        r = self.client.get(reverse("dashboard:campaign-edit", args=[legacy.pk]))
        self.assertEqual(sorted(r.context["form"]["channels"].value()), ["email", "sms"])

    def test_active_campaign_cannot_be_edited(self):
        self.post_new(self.campaign_payload())
        c = self.last()
        self.client.post(reverse("dashboard:campaign-activate", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.status, "active")
        self.client.post(reverse("dashboard:campaign-edit", args=[c.pk]), self.campaign_payload(name="تغییر"))
        c.refresh_from_db()
        self.assertEqual(c.name, "جشن پاییزی")

    def test_incomplete_draft_is_saved_but_cannot_be_activated(self):
        self.post_new(self.campaign_payload(coupon_value="0", code_valid_days=""))
        c = self.last()
        self.assertEqual(c.status, "draft")
        self.client.post(reverse("dashboard:campaign-activate", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.status, "draft")

    # ---- مجوزها و ایزولاسیون ------------------------------------------------------
    def test_permissions_and_store_isolation(self):
        self.post_new(self.campaign_payload())
        self._login_as(StoreMembership.Role.ANALYST, "501")
        self.assertEqual(self.client.get(reverse("dashboard:campaign-add") + "?kind=occasions").status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-add"), self.campaign_payload(name="x")).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-sms-preview"), self.campaign_payload()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:campaign-add")).status_code, 302)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-sms-preview"), {}).status_code, 302)
        self.assertEqual(Campaign.objects.count(), 1)

    def test_other_store_campaign_edit_is_404(self):
        other = Store.objects.create(name="دیگر", slug="wiz-other3", status=Store.Status.ACTIVE)
        foreign = Campaign.objects.create(store=other, name="x")
        self.assertEqual(self.client.get(reverse("dashboard:campaign-edit", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:campaign-edit", args=[foreign.pk]), self.campaign_payload()).status_code, 404)

    # ---- کانال‌ها ------------------------------------------------------------------
    def test_channel_toggles_are_explicit_and_none_means_no_messages(self):
        c1 = self.post_new(self.campaign_payload(name="هیچ‌کدام"))
        self.assertEqual(c1.status_code, 302)
        none_c = Campaign.objects.get(name="هیچ‌کدام")
        self.assertEqual((none_c.channels, none_c.channels_explicit), ([], True))
        self.post_new(self.campaign_payload(name="فقط پیامک", channels=["sms"]))
        self.post_new(self.campaign_payload(name="فقط ایمیل", channels=["email"]))
        self.assertEqual(Campaign.objects.get(name="فقط پیامک").channels, ["sms"])
        self.assertEqual(cs.notification_channels(none_c), [])
        self.assertEqual(cs.notification_channels(Campaign.objects.get(name="فقط ایمیل")), ["email"])


class SmsTextOwnershipTests(WizardBase):
    """قانونِ قطعی: متنِ پیامکِ کمپین/مناسبت فقط از قالبِ پلتفرم می‌آید."""

    def run_campaign(self, **kw):
        defaults = dict(channels=["sms", "email"], channels_explicit=True)
        defaults.update(kw)
        campaign = cs.save_campaign(Campaign(store=self.store, name=kw.pop("name", "ک"), **{
            "trigger_type": "manual", "reward_type": "coupon", "coupon_type": "percent", "coupon_value": Decimal(20),
            "code_valid_days": 7, "code_prefix": "T", "per_customer_limit": 1, **defaults,
        }))
        cs.activate(campaign)
        return campaign

    def customer_ready(self):
        c = self.customer("مشتری آزمون", email="a@example.com")
        self.order(c, [(self.product("کالا", M), 1)], when=timezone.now())
        return c

    def test_posted_custom_sms_body_is_ignored_by_the_form(self):
        r = self.post_new(self.campaign_payload(custom_sms_body="متن جعلی فروشنده {customer_name}", channels=["sms"]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.last().custom_sms_body, "")
        r = self.client.post(reverse("dashboard:campaign-edit", args=[self.last().pk]), self.campaign_payload(custom_sms_body="باز هم جعلی", channels=["sms"]))
        self.assertEqual(self.last().custom_sms_body, "")

    def test_legacy_custom_sms_body_is_never_sent(self):
        self.customer_ready()
        campaign = self.run_campaign(custom_sms_body="متنِ قدیمیِ فروشنده {customer_name}")
        cs.execute_campaign(campaign)
        sms = NotificationOutbox.objects.get(event_key="campaign.offer_percent", channel="sms")
        self.assertNotIn("متنِ قدیمیِ فروشنده", sms.body)
        self.assertIn("«ک»", sms.body)

    def test_store_level_template_row_for_a_platform_managed_event_is_ignored(self):
        NotificationTemplate.objects.create(store=self.store, event_key="campaign.offer_percent", channel="sms", body="هک فروشنده {discount_code}")
        self.customer_ready()
        cs.execute_campaign(self.run_campaign())
        sms = NotificationOutbox.objects.get(event_key="campaign.offer_percent", channel="sms")
        self.assertNotIn("هک فروشنده", sms.body)

    def test_overrides_cannot_replace_sms_text_in_dispatch(self):
        from apps.notifications.services.dispatcher import dispatch_event

        c = self.customer_ready()
        rows = dispatch_event(
            "campaign.announce", store=self.store, customer=c, context={"campaign_name": "ک", "customer_name": c.full_name},
            channels=["sms"], overrides={"sms": {"body": "متن جعلی"}},
        )
        self.assertEqual(len(rows), 1)
        self.assertNotIn("متن جعلی", rows[0].body)

    def test_store_cannot_edit_save_reset_or_test_platform_managed_sms(self):
        original = SmsTemplate.ensure_defaults() or SmsTemplate.objects.get(event_key="camp_offer_percent").body
        url = reverse("dashboard:notification-template-edit", args=["campaign.offer_percent"])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "🔒")
        self.assertNotContains(page, '<textarea class="inp" name="sms_body"')
        # POST دست‌کاری‌شده
        self.client.post(url, {"sms_enabled": "on", "sms_body": "هک {discount_code}", "email_enabled": "on", "email_subject": "s", "email_body": "b {discount_code}"})
        self.client.post(url, {"action": "reset", "channel": "sms"})
        self.assertEqual(SmsTemplate.objects.get(event_key="camp_offer_percent").body, original)
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, event_key="campaign.offer_percent", channel="sms").exists())
        with self.assertRaises(template_service.PlatformManagedError):
            template_service.save_template(self.store, "campaign.offer_percent", "sms", enabled=True, subject="", body="x {discount_code}")
        with self.assertRaises(template_service.PlatformManagedError):
            template_service.reset_template(self.store, "campaign.offer_percent", "sms")
        # پیش‌نمایشِ ویرایشگر هرگز متنِ ارسالیِ کاربر را رندر نمی‌کند
        r = self.client.post(reverse("dashboard:notification-template-preview", args=["campaign.offer_percent"]), {"channel": "sms", "sms_body": "متن جعلی"})
        self.assertNotContains(r, "متن جعلی")
        # ایمیل همچنان قابلِ ویرایش است (فقط پیامک پلتفرم‌محور است)
        self.assertTrue(NotificationTemplate.objects.filter(store=self.store, event_key="campaign.offer_percent", channel="email").exists())

    def test_store_sms_template_screens_hide_and_reject_platform_managed_templates(self):
        SmsTemplate.ensure_defaults()
        row = SmsTemplate.objects.get(event_key="camp_offer_percent")
        original = row.body
        self.assertEqual(self.client.get(reverse("dashboard:sms-template-edit", args=[row.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:sms-template-edit", args=[row.pk]), {"body": "هک {customer_name}"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:sms-template-toggle", args=[row.pk])).status_code, 404)
        row.refresh_from_db()
        self.assertEqual((row.body, row.is_active), (original, True))
        from apps.dashboard.services import sms_admin_service

        keys = {r["template"].event_key for r in sms_admin_service.templates_with_variables()}
        self.assertFalse(keys & set(PLATFORM_MANAGED_EVENTS))
        self.assertIn("welcome", keys)  # قالب‌هایِ دیگرِ فروشگاه دست‌نخورده
        r = self.client.post(reverse("dashboard:sms-test-send"), {"event_key": "camp_offer_percent", "phone": "09120000000"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(NotificationOutbox.objects.count(), 0)

    def test_other_store_notification_templates_are_not_touched(self):
        """محدودیت فقط روی پیامکِ کمپین/مناسبت است؛ سایرِ قالب‌هایِ اعلانِ فروشگاه ویرایش‌پذیر می‌مانند."""
        url = reverse("dashboard:notification-template-edit", args=["coupon.expiring"])
        r = self.client.post(url, {"sms_enabled": "on", "sms_body": "x", "email_enabled": "on", "email_subject": "s", "email_body": "b"})
        # coupon.expiring اکنون پلتفرم‌محور است؛ ایمیلش ذخیره می‌شود، پیامکش نه
        self.assertEqual(r.status_code, 302)
        self.assertTrue(NotificationTemplate.objects.filter(store=self.store, event_key="coupon.expiring", channel="email").exists())
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, event_key="coupon.expiring", channel="sms").exists())
        r = self.client.post(reverse("dashboard:notification-template-edit", args=["coupon.issued"]), {
            "sms_enabled": "on", "sms_body": "کد شما {discount_code}", "email_enabled": "on", "email_subject": "s", "email_body": "b"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(NotificationTemplate.objects.get(store=self.store, event_key="coupon.issued", channel="sms").body, "کد شما {discount_code}")

    def test_platform_staff_can_manage_the_central_templates_and_it_changes_what_is_sent(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, override_settings

        host = "platformadmins.rastisi.localhost"
        staff = get_user_model().objects.create_user(username="pa-wiz@example.com", email="pa-wiz@example.com", password="a-very-strong-pass-1", is_staff=True, is_superuser=True)
        SmsTemplate.ensure_defaults()
        with override_settings(ALLOWED_HOSTS=[host, "testserver"]):
            pc = Client()
            pc.force_login(staff)
            listing = pc.get("/sms/templates/", HTTP_HOST=host)
            self.assertContains(listing, "کمپین تخفیف · تخفیف درصدی")
            new_body = "{customer_name} عزیز، پیشنهاد «{campaign_name}» از {shop_name}: {discount_amount} تخفیف، کد {discount_code} تا {discount_expires_at}"
            r = pc.post("/sms/templates/camp_offer_percent/", {"title": "تخفیف درصدی", "body": new_body, "is_active": "on", "melipayamak_variables_order": "otp_code"}, HTTP_HOST=host)
            self.assertEqual(r.status_code, 302)
            # متغیرِ ناشناخته/هدیه در قالبِ «بدون کد» رد می‌شود
            bad = pc.post("/sms/templates/camp_announce/", {"title": "اطلاع", "body": "کد {discount_code}", "is_active": "on"}, HTTP_HOST=host)
            self.assertEqual(bad.status_code, 200)
            self.assertNotIn("discount_code", SmsTemplate.objects.get(event_key="camp_announce").body)
        self.customer_ready()
        cs.execute_campaign(self.run_campaign())
        sms = NotificationOutbox.objects.get(event_key="campaign.offer_percent", channel="sms")
        self.assertIn("پیشنهاد «ک»", sms.body)
        # فروشنده (غیرِ پلتفرم) به صفحه‌ی ادمین پلتفرم دسترسی ندارد
        with override_settings(ALLOWED_HOSTS=[host, "testserver"]):
            seller = Client()
            seller.force_login(self.owner)
            self.assertNotEqual(seller.post("/sms/templates/camp_offer_percent/", {"title": "x", "body": "هک {shop_name}"}, HTTP_HOST=host).status_code, 200)
        self.assertNotIn("هک", SmsTemplate.objects.get(event_key="camp_offer_percent").body)


class MessageContentTests(WizardBase):
    """پیام‌هایِ درست برایِ هر ترکیبِ «هدیه × زمان»، و یکسانیِ پیش‌نمایش با متنِ قابلِ‌ارسال."""

    def make(self, **kw):
        base = dict(store=self.store, name="جشن", trigger_type="manual", reward_type="coupon", coupon_type="percent",
                    coupon_value=Decimal(15), code_valid_days=7, code_prefix="PRV", per_customer_limit=1, channels=["sms", "email"],
                    channels_explicit=True)
        base.update(kw)
        return cs.save_campaign(Campaign(**base))

    def preview(self, campaign):
        return cs.preview_message(campaign)

    def test_reward_none_never_promises_a_gift_or_code(self):
        for kw in (dict(reward_type="none"),
                   dict(reward_type="none", trigger_type="occasion", occasion_kind="birthday"),
                   dict(reward_type="none", trigger_type="occasion", occasion_kind="birthday", occasion_offset_days=-3),
                   dict(reward_type="none", trigger_type="occasion", occasion_kind="birthday", occasion_offset_days=2),
                   dict(reward_type="none", trigger_type="occasion", occasion_kind="holiday", occasion_params={"month": 1, "day": 1}),
                   dict(reward_type="none", trigger_type="occasion", occasion_kind="registration_anniversary", occasion_offset_days=1)):
            text = self.preview(self.make(**kw))["text"]
            for word in ("کد تخفیف", "کد هدیه", "تخفیف", "هدیه", "PRV", "اعتبار تا", "{"):
                self.assertNotIn(word, text, (kw, text))

    def test_free_ship_percent_fixed_have_independent_correct_messages(self):
        pct = self.preview(self.make(coupon_type="percent", coupon_value=Decimal(15), coupon_max_discount=Decimal(M)))
        fixed = self.preview(self.make(coupon_type="fixed", coupon_value=Decimal(100000)))
        free = self.preview(self.make(coupon_type="free_ship", coupon_value=Decimal(0)))
        self.assertEqual((pct["event_key"], fixed["event_key"], free["event_key"]), ("campaign.offer_percent", "campaign.offer_fixed", "campaign.offer_free_ship"))
        self.assertIn("۱۵٪", pct["text"])
        self.assertIn("۱٬۰۰۰٬۰۰۰", pct["text"])
        self.assertIn("۱۰۰٬۰۰۰ تومان", fixed["text"])
        self.assertIn("ارسال رایگان", free["text"])
        self.assertNotIn("٪", free["text"])
        self.assertNotIn("تومان", free["text"])
        for r in (pct, fixed, free):
            self.assertIn("PRV-", r["text"])

    def test_before_on_after_messages_match_timing_and_reward(self):
        before = self.preview(self.make(trigger_type="occasion", occasion_kind="birthday", occasion_offset_days=-3))
        on = self.preview(self.make(trigger_type="occasion", occasion_kind="birthday"))
        after = self.preview(self.make(trigger_type="occasion", occasion_kind="birthday", occasion_offset_days=1))
        self.assertEqual((before["event_key"], on["event_key"], after["event_key"]), ("occasion.birthday_before", "occasion.birthday", "occasion.birthday_after"))
        self.assertIn("نزدیک است", before["text"])
        self.assertIn("مبارک", on["text"])
        self.assertIn("امیدواریم", after["text"])
        for r in (before, on, after):  # هدیه‌ی واقعی در هر سه زمان صادر می‌شود ⇒ هر سه پیام کد دارند
            self.assertIn("PRV-", r["text"])
        g_before = self.preview(self.make(trigger_type="occasion", occasion_kind="holiday", occasion_params={"month": 9, "day": 30}, occasion_offset_days=-2, name="شب یلدا"))
        g_after = self.preview(self.make(trigger_type="occasion", occasion_kind="holiday", occasion_params={"month": 9, "day": 30}, occasion_offset_days=2, name="شب یلدا"))
        self.assertEqual((g_before["event_key"], g_after["event_key"]), ("occasion.generic_before", "occasion.generic_after"))
        self.assertIn("«شب یلدا»", g_before["text"])
        self.assertIn("«شب یلدا»", g_after["text"])

    def test_every_event_key_combination_resolves_to_a_platform_template(self):
        from apps.notifications import events as ev

        seen = set()
        for kind in Campaign.Occasion.values:
            for offset in (-3, 0, 2):
                for reward in ("coupon", "none"):
                    c = Campaign(store=self.store, name="n", trigger_type="occasion", occasion_kind=kind, occasion_offset_days=offset, reward_type=reward)
                    seen.add(occasions.notification_event_key(c))
        for coupon_type in ("percent", "fixed", "free_ship"):
            seen.add(occasions.notification_event_key(Campaign(store=self.store, name="n", reward_type="coupon", coupon_type=coupon_type)))
        seen.add(occasions.notification_event_key(Campaign(store=self.store, name="n", reward_type="none")))
        self.assertEqual(len(seen), 16)  # ۱۲ مناسبت + ۴ کمپین، همه مستقل
        for key in seen:
            self.assertTrue(ev.get_event(key).platform_sms_event, key)
            self.assertIn(ev.get_event(key).platform_sms_event, {e for e in PLATFORM_MANAGED_EVENTS}, key)

    def test_expiry_date_is_computed_from_the_real_code_validity(self):
        for days in (3, 30):
            text = self.preview(self.make(code_valid_days=days))["text"]
            expected = to_fa_digits(format_jalali(timezone.now() + timezone.timedelta(days=days)))
            self.assertIn(expected, text, (days, text))
            self.assertNotIn("۱۴۰۵/۰۹/۳۰", text.replace(expected, "")) if expected != "۱۴۰۵/۰۹/۳۰" else None
        # انقضای ثابت
        fixed_end = jdt(1450, 1, 15, 23, 59, 59)
        text = self.preview(self.make(code_valid_days=None, code_expires_at=fixed_end))["text"]
        self.assertIn(to_fa_digits(format_jalali(fixed_end)), text)

    def test_preview_equals_the_text_actually_queued_for_sending(self):
        customer = self.customer("مشتری واقعی", email="r@example.com")
        self.order(customer, [(self.product("ک", M), 1)], when=timezone.now())
        for kw in (dict(), dict(coupon_type="fixed", coupon_value=Decimal(50000)), dict(coupon_type="free_ship", coupon_value=Decimal(0)),
                   dict(reward_type="none"), dict(trigger_type="occasion", occasion_kind="reactivation", occasion_params={"days": 1}, name="دلتنگی")):
            NotificationOutbox.objects.all().delete()
            CampaignIssuance.objects.all().delete()
            campaign = self.make(**{"name": "پیشنهاد", **kw})
            preview = self.preview(campaign)["text"]
            cs.activate(campaign)
            if campaign.trigger_type == "occasion":
                cs.issue_reward(campaign, customer, "c1")
            else:
                cs.execute_campaign(campaign)
            sms = NotificationOutbox.objects.get(channel="sms", event_key=preview and cs.occasions.notification_event_key(campaign))
            issuance = CampaignIssuance.objects.get()
            expected = preview.replace(cs.SAMPLE_CUSTOMER_NAME, customer.full_name)
            if issuance.coupon:
                expected = expected.replace("PRV-AB12CD34", issuance.coupon.code)
            self.assertEqual(sms.body, expected, kw)
            Campaign.objects.all().delete()

    def test_preview_endpoint_is_read_only_and_matches_the_service(self):
        before = (Coupon.objects.count(), NotificationOutbox.objects.count(), Campaign.objects.count(), CampaignIssuance.objects.count())
        r = self.client.post(reverse("dashboard:campaign-sms-preview"), {
            "name": "پاییز", "trigger_type": "manual", "reward_type": "coupon", "coupon_type": "percent", "coupon_value": "۱۵",
            "code_valid_days": "7", "code_prefix": "autumn",
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("«پاییز»", data["text"])
        self.assertIn("AUTUMN-", data["text"])
        self.assertIn("۱۵٪", data["text"])
        self.assertEqual("".join(p["text"] for p in data["parts"]), data["text"])
        self.assertTrue(any(p.get("variable") == "discount_code" for p in data["parts"]))
        self.assertTrue(data["template_active"])
        self.assertEqual(before, (Coupon.objects.count(), NotificationOutbox.objects.count(), Campaign.objects.count(), CampaignIssuance.objects.count()))
        # ورودیِ نیمه‌کاره نباید بشکند
        r = self.client.post(reverse("dashboard:campaign-sms-preview"), {"trigger_type": "occasion", "coupon_value": "xyz", "code_valid_days": "q"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:campaign-sms-preview")).status_code, 405)

    def test_platform_can_switch_a_template_off(self):
        SmsTemplate.ensure_defaults()
        SmsTemplate.objects.filter(event_key="camp_announce").update(is_active=False)
        r = self.client.post(reverse("dashboard:campaign-sms-preview"), {"name": "ک", "trigger_type": "manual", "reward_type": "none"})
        self.assertFalse(r.json()["template_active"])
        customer = self.customer("م", email="e@example.com")
        self.order(customer, [(self.product("ک", M), 1)], when=timezone.now())
        campaign = self.make(reward_type="none")
        cs.activate(campaign)
        cs.execute_campaign(campaign)
        self.assertFalse(NotificationOutbox.objects.filter(channel="sms").exists())
        self.assertTrue(NotificationOutbox.objects.filter(channel="email", event_key="campaign.announce").exists())


class DeliveryRulesTests(WizardBase):
    """رضایت، جلوگیری از ارسالِ تکراری، و خاموش‌بودنِ ارسال با کلیدِ فروشنده."""

    def setUp(self):
        super().setUp()
        self.item = self.product("کالا", M)

    def activated(self, **kw):
        base = dict(store=self.store, name="ک", trigger_type="manual", reward_type="coupon", coupon_type="percent",
                    coupon_value=Decimal(10), code_valid_days=7, per_customer_limit=1)
        base.update(kw)
        c = cs.save_campaign(Campaign(**base))
        cs.activate(c)
        return c

    def test_seller_toggle_off_sends_nothing_but_reward_is_still_issued(self):
        c = self.customer("م", email="x@example.com")
        self.order(c, [(self.item, 1)], when=timezone.now())
        campaign = self.activated(channels=[], channels_explicit=True)
        run = cs.execute_campaign(campaign)
        self.assertEqual(run.issued, 1)
        self.assertEqual(Coupon.objects.filter(customer=c).count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key__startswith="campaign.").count(), 0)

    def test_only_selected_channels_are_queued(self):
        c = self.customer("م", email="x@example.com")
        self.order(c, [(self.item, 1)], when=timezone.now())
        cs.execute_campaign(self.activated(channels=["email"], channels_explicit=True))
        self.assertEqual({r.channel for r in NotificationOutbox.objects.filter(event_key="campaign.offer_percent")}, {"email"})

    def test_legacy_campaign_with_empty_channels_still_means_all(self):
        c = self.customer("م", email="x@example.com")
        self.order(c, [(self.item, 1)], when=timezone.now())
        cs.execute_campaign(self.activated(channels=[], channels_explicit=False))
        self.assertEqual({r.channel for r in NotificationOutbox.objects.filter(event_key="campaign.offer_percent")}, {"sms", "email"})

    def test_no_consent_is_skipped_and_no_duplicate_on_rerun(self):
        no_consent = self.customer("بی‌رضایت", email="n@example.com", sms=False, mail=False)
        self.order(no_consent, [(self.item, 1)], when=timezone.now())
        consenting = self.customer("راضی", email="y@example.com")
        self.order(consenting, [(self.item, 1)], when=timezone.now())
        campaign = self.activated(channels=["sms", "email"], channels_explicit=True)
        cs.execute_campaign(campaign)
        cs.execute_campaign(campaign)
        rows = NotificationOutbox.objects.filter(event_key="campaign.offer_percent")
        self.assertEqual(rows.count(), 4)  # ۲ مشتری × ۲ کانال، بدونِ تکرار با اجرای دوم
        for row in rows.filter(customer=no_consent):
            self.assertEqual((row.status, row.skip_reason), ("skipped", "no_promotional_consent"))
        self.assertEqual(CampaignIssuance.objects.count(), 2)

    def test_cross_store_customers_are_never_messaged(self):
        from apps.core.models import ShopSettings

        other = Store.objects.create(name="دیگر", slug="wiz-other4", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other)
        stranger = self.customer("غریبه", email="s@example.com")
        self.order(stranger, [(self.product("کالای-دیگر", M, store=other), 1)], when=timezone.now(), store=other)
        cs.execute_campaign(self.activated(channels=["sms", "email"], channels_explicit=True))
        self.assertFalse(NotificationOutbox.objects.filter(customer=stranger, event_key__startswith="campaign.").exists())
        self.assertFalse(CampaignIssuance.objects.filter(customer=stranger).exists())

    def test_expiry_reminder_sms_is_platform_managed_and_respects_toggle(self):
        c = self.customer("م", email="x@example.com")
        self.order(c, [(self.item, 1)], when=timezone.now())
        campaign = self.activated(channels=["sms"], channels_explicit=True, reminder_days_before_expiry=30)
        cs.execute_campaign(campaign)
        NotificationTemplate.objects.create(store=self.store, event_key="coupon.expiring", channel="sms", body="هک {discount_code}")
        self.assertEqual(cs.send_expiry_reminders(self.store), 1)
        sms = NotificationOutbox.objects.get(event_key="coupon.expiring", channel="sms")
        self.assertNotIn("هک", sms.body)
        self.assertIn("روز دیگر", sms.body)
        off = self.activated(name="خاموش", channels=[], channels_explicit=True, reminder_days_before_expiry=30)
        before = NotificationOutbox.objects.filter(event_key="coupon.expiring").count()
        cs.execute_campaign(off)
        cs.send_expiry_reminders(self.store)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="coupon.expiring").count(), before)


def browser_like_post_data(html: str) -> dict:
    """مقادیری که مرورگر هنگامِ «ذخیره» از فرمِ رندرشده می‌فرستد (بدونِ هیچ تغییرِ کاربر)."""
    from bs4 import BeautifulSoup

    form = BeautifulSoup(html, "html.parser").find("form", id="cw-form")
    data: dict = {}

    def add(name, value):
        data.setdefault(name, []).append(value)

    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or el.has_attr("disabled"):
            continue
        if el.name == "input":
            kind = el.get("type", "text")
            if kind in ("checkbox", "radio"):
                if el.has_attr("checked"):
                    add(name, el.get("value", "on"))
            elif kind != "submit":
                add(name, el.get("value", ""))
        elif el.name == "textarea":
            add(name, el.text.strip("\n"))
        else:
            chosen = el.find("option", selected=True) or el.find("option")
            if chosen is not None:
                add(name, chosen.get("value", chosen.text))
    return {k: (v if len(v) > 1 else v[0]) for k, v in data.items()}


class EditRoundTripTests(WizardBase):
    """باز کردنِ هر کمپینِ قدیمی و ذخیره‌ی بدونِ تغییر نباید هیچ فیلدی را عوض کند."""

    FIELDS = (
        "name", "description", "trigger_type", "rules", "rule_scope", "period_mode", "period_jalali_year", "period_start_month",
        "period_end_month", "period_start_date", "period_end_date", "valid_payment_statuses", "amount_basis", "reward_type",
        "coupon_type", "coupon_value", "coupon_max_discount", "coupon_min_order", "coupon_applies_to_gift_wrap", "code_prefix",
        "personalized", "code_starts_at", "code_expires_at", "code_valid_days", "total_redemption_limit", "per_customer_limit",
        "per_customer_period_days", "max_issuances", "validity_from_delivery", "channels", "reminder_days_before_expiry",
        "occasion_kind", "occasion_name", "occasion_offset_days", "occasion_params", "active_from", "active_until",
        "custom_email_subject", "custom_email_body", "custom_sms_body",
    )

    def snapshot(self, c):
        c.refresh_from_db()
        return {f: getattr(c, f) for f in self.FIELDS}

    def roundtrip(self, campaign):
        before = self.snapshot(campaign)
        url = reverse("dashboard:campaign-edit", args=[campaign.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        r = self.client.post(url, browser_like_post_data(r.content.decode()))
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        after = self.snapshot(campaign)
        diff = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        if diff.get("valid_payment_statuses", (None, None))[0] == [] and diff["valid_payment_statuses"][1] == ["paid"]:
            del diff["valid_payment_statuses"]  # [] و ["paid"] در موتور یکی‌اند (``or ["paid"]``)
        return diff

    def test_legacy_occasion_with_every_old_field(self):
        tree = {"type": "group", "op": "and", "negate": False, "children": [
            {"type": "customer_city", "values": ["شیراز"]}, {"type": "lifetime_orders", "op": "gte", "value": "2"}]}
        c = Campaign.objects.create(
            store=self.store, name="مناسبت قدیمی", description="d", trigger_type="occasion", occasion_kind="holiday",
            occasion_name="شب یلدا", occasion_params={"month": 9, "day": 30}, occasion_offset_days=-2, rules=tree,
            period_mode="jalali_months", period_jalali_year=1404, period_start_month=1, period_end_month=6,
            rule_scope="same_order", amount_basis="items_total", valid_payment_statuses=["paid", "refunded"],
            coupon_type="percent", coupon_value=Decimal(25), coupon_max_discount=Decimal(2_000_000), coupon_min_order=Decimal(100_000),
            code_prefix="YLDA", personalized=False, code_valid_days=10, total_redemption_limit=50, per_customer_limit=2,
            per_customer_period_days=60, max_issuances=300, validity_from_delivery=True, coupon_applies_to_gift_wrap=True,
            channels=["sms"], channels_explicit=True, reminder_days_before_expiry=2, active_until=jdt(1450, 1, 1, 23, 59, 59),
            custom_email_subject="موضوع", custom_email_body="سلام {customer_name} {discount_code}", custom_sms_body="قدیمی",
        )
        self.assertEqual(self.roundtrip(c), {})

    def test_legacy_manual_campaign_with_custom_rules_period_dates_and_fixed_expiry(self):
        tree = {"type": "group", "op": "or", "negate": False, "children": [
            {"type": "customer_city", "values": ["شیراز"]}, {"type": "customer_type", "value": "new"}]}
        c = Campaign.objects.create(
            store=self.store, name="قدیمی", trigger_type="scheduled", rules=tree, period_mode="dates",
            period_start_date=jdt(1404, 1, 1).date(), period_end_date=jdt(1404, 6, 31).date(), coupon_type="fixed",
            coupon_value=Decimal(70000), code_starts_at=jdt(1405, 1, 1, 0, 0, 0), code_expires_at=jdt(1405, 6, 31, 23, 59, 59),
            code_valid_days=None, active_from=jdt(1405, 1, 1, 0, 0, 0), channels=[], channels_explicit=False, per_customer_limit=1,
        )
        diff = self.roundtrip(c)
        # تنها تفاوتِ مجاز: کمپینِ قدیمی بدونِ انتخابِ صریحِ کانال، «همه‌ی کانال‌ها» را صریح نشان می‌دهد (همان معنی)
        self.assertEqual(set(diff), {"channels"})
        self.assertEqual(sorted(diff["channels"][1]), ["email", "sms"])

    def test_legacy_reward_none_and_free_ship_campaigns(self):
        for kw in (dict(reward_type="none", coupon_value=Decimal(0)), dict(coupon_type="free_ship", coupon_value=Decimal(0), code_valid_days=5)):
            c = Campaign.objects.create(store=self.store, name="ق", trigger_type="manual", channels=["email"], channels_explicit=True, **kw)
            self.assertEqual(self.roundtrip(c), {}, kw)


class OffsetlessOccasionTests(WizardBase):
    """«۳ روز قبل/۱ روز بعد» برای مناسبت‌هایی که روزِ تقویمی ندارند عملیاتی نیست؛ نباید قابل‌انتخاب یا اثرگذار باشد."""

    def test_milestone_and_reactivation_ignore_offset_in_form_and_message(self):
        for kind, extra in (("reactivation", {"occ_days": "30"}), ("order_milestone", {"occ_n": "3"}), ("spending_milestone", {"occ_amount": "1000000"})):
            r = self.post_new(self.occasion_payload(name=f"o-{kind}", occasion_kind=kind, occasion_offset_days="-3", **extra))
            self.assertEqual(r.status_code, 302, kind)
            c = Campaign.objects.get(name=f"o-{kind}")
            self.assertEqual(c.occasion_offset_days, 0, kind)
            self.assertEqual(occasions.notification_event_key(c), "occasion.generic", kind)
        legacy = Campaign.objects.create(store=self.store, name="ق", trigger_type="occasion", occasion_kind="reactivation", occasion_params={"days": 30}, occasion_offset_days=-3)
        self.assertEqual(occasions.notification_event_key(legacy), "occasion.generic")  # offset قدیمی بی‌اثر بود؛ پیام هم «قبل» نیست

    def test_calendar_occasions_still_use_offset(self):
        r = self.post_new(self.occasion_payload(name="h", occasion_kind="holiday", occ_month="9", occ_day="30", occasion_offset_days="-3"))
        self.assertEqual(Campaign.objects.get(name="h").occasion_offset_days, -3)


class TestSendCannotCarryCustomSmsText(WizardBase):
    def test_store_test_send_of_platform_managed_event_uses_platform_text_only(self):
        from django.core import mail

        url = reverse("dashboard:notification-template-test", args=["campaign.announce"])
        self.client.post(url, {"channel": "sms", "recipient": "09120001111", "sms_body": "متن جعلی فروشنده"})
        rows = NotificationOutbox.objects.filter(is_test=True, event_key="campaign.announce")
        self.assertEqual(rows.count(), 1)
        self.assertNotIn("متن جعلی", rows[0].body)
        self.assertIn("آغاز شد", rows[0].body)
        self.assertEqual(len(mail.outbox), 0)
