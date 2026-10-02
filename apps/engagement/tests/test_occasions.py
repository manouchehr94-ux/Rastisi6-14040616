"""مناسبت‌ها: تولد (پیش از/روز/پس از)، سیاستِ ۳۰ اسفند، چرخه‌ی سالانه، سالگردها،
نقاطِ عطف، بازگشتِ مشتری، تعطیلات و مناسبتِ اختصاصی."""

import datetime as dt
from decimal import Decimal

from django.utils import timezone

from apps.cart.models import Coupon
from apps.core.jalali_utils import jalali_to_gregorian
from apps.customers.models import Customer
from apps.engagement.models import Campaign, CampaignIssuance
from apps.engagement.services import campaign_service as cs
from apps.engagement.services import occasions
from apps.engagement.tests.base import EngagementBase, jdt
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import deliver_pending

M = 1_000_000


def jd(y, m, d):
    return jalali_to_gregorian(y, m, d)


class OccasionBase(EngagementBase):
    def setUp(self):
        super().setUp()
        self.item = self.product("کالا", 1 * M)

    def customer_with_order(self, name="م", **kw):
        c = self.customer(name, **kw)
        self.order(c, [(self.item, 1)], when=jdt(1404, 1, 10))
        return c

    def occ(self, kind, *, offset=0, reward=Campaign.Reward.COUPON, params=None, name="مناسبت", **kw):
        defaults = dict(
            store=self.store, name=name, trigger_type=Campaign.Trigger.OCCASION, occasion_kind=kind,
            occasion_offset_days=offset, occasion_params=params or {}, occasion_name=name, reward_type=reward,
            coupon_type="percent", coupon_value=Decimal("20"), code_valid_days=7, code_prefix="BDAY",
            per_customer_limit=1, total_redemption_limit=1,
        )
        defaults.update(kw)
        c = cs.save_campaign(Campaign(**defaults))
        cs.activate(c)
        c.refresh_from_db()
        return c

    def go(self, campaign, day):
        return cs.run_occasion_campaign(campaign, day)


class BirthdayTests(OccasionBase):
    def test_birthday_20_percent_valid_7_days_saved_for_customer(self):
        c = self.customer_with_order("متولد", email="b@example.com", birth_date=jd(1370, 5, 5))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY, name="تولد")
        run = self.go(campaign, jd(1405, 5, 5))
        self.assertEqual(run.issued, 1)
        coupon = Coupon.objects.get(customer=c)
        self.assertEqual((coupon.type, coupon.value), ("percent", Decimal("20")))
        delta = coupon.expires_at - timezone.now()
        self.assertTrue(dt.timedelta(days=6, hours=23) < delta <= dt.timedelta(days=7))
        self.assertEqual(coupon.per_customer_limit, 1)
        rows = NotificationOutbox.objects.filter(event_key="occasion.birthday")
        self.assertEqual({r.channel for r in rows}, {"sms", "email"})
        self.assertTrue(all(coupon.code in r.body and "متولد" in r.body for r in rows))

    def test_other_days_do_not_issue(self):
        self.customer_with_order("م", birth_date=jd(1370, 5, 5))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        for day in (jd(1405, 5, 4), jd(1405, 5, 6), jd(1405, 6, 5)):
            self.assertEqual(self.go(campaign, day).issued, 0)
        self.assertFalse(CampaignIssuance.objects.exists())

    def test_repeated_run_same_day_never_duplicates_reward_or_messages(self):
        self.customer_with_order("م", email="x@example.com", birth_date=jd(1370, 5, 5))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        self.go(campaign, jd(1405, 5, 5))
        before_n = NotificationOutbox.objects.filter(event_key="occasion.birthday").count()
        for _ in range(3):
            run = self.go(campaign, jd(1405, 5, 5))
            self.assertEqual((run.issued, run.skipped_existing), (0, 1))
        self.assertEqual(Coupon.objects.filter(code__startswith="BDAY-").count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="occasion.birthday").count(), before_n)

    def test_annual_cycle_new_reward_each_jalali_year(self):
        c = self.customer_with_order("م", birth_date=jd(1370, 5, 5))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        self.assertEqual(self.go(campaign, jd(1405, 5, 5)).issued, 1)
        self.assertEqual(self.go(campaign, jd(1406, 5, 5)).issued, 1)
        self.assertEqual(self.go(campaign, jd(1406, 5, 5)).issued, 0)
        self.assertEqual(sorted(CampaignIssuance.objects.values_list("cycle_key", flat=True)), ["1405", "1406"])
        self.assertEqual(Coupon.objects.filter(customer=c).count(), 2)

    def test_changing_birth_date_cannot_farm_second_reward_in_same_year(self):
        c = self.customer_with_order("م", birth_date=jd(1370, 5, 5))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        self.go(campaign, jd(1405, 5, 5))
        c.birth_date = jd(1370, 8, 8)
        c.save()
        # cycle_key = سالِ جلالیِ وقوعِ مناسبت ⇒ در همان سال دوباره پاداش داده نمی‌شود
        self.assertEqual(self.go(campaign, jd(1405, 8, 8)).issued, 0)
        self.assertEqual(Coupon.objects.filter(customer=c).count(), 1)

    def test_before_and_after_birthday_messages(self):
        self.customer_with_order("م", email="x@example.com", birth_date=jd(1370, 5, 5))
        before = self.occ(Campaign.Occasion.BIRTHDAY, offset=-3, reward=Campaign.Reward.NONE, name="پیش از تولد",
                          custom_sms_body="{customer_name} عزیز، ۳ روز تا تولدت مانده!")
        after = self.occ(Campaign.Occasion.BIRTHDAY, offset=2, reward=Campaign.Reward.NONE, name="پس از تولد")
        self.assertEqual(self.go(before, jd(1405, 5, 2)).issued, 1)
        self.assertEqual(self.go(before, jd(1405, 5, 3)).issued, 0)
        self.assertEqual(self.go(after, jd(1405, 5, 7)).issued, 1)
        sms = NotificationOutbox.objects.get(event_key="occasion.birthday_before", channel="sms")
        self.assertEqual(sms.body, "م عزیز، ۳ روز تا تولدت مانده!")
        self.assertTrue(NotificationOutbox.objects.filter(event_key="occasion.birthday_after").exists())
        self.assertFalse(Coupon.objects.filter(code__startswith="BDAY-").exists())

    def test_year_boundary_before_birthday_uses_occasion_year_as_cycle(self):
        # تولد ۲ فروردین؛ «۳ روز پیش» = ۲۸ اسفند (سالِ قبل) ⇒ چرخه = سالِ تولد (۱۴۰۵)
        self.customer_with_order("م", birth_date=jd(1370, 1, 2))
        before = self.occ(Campaign.Occasion.BIRTHDAY, offset=-3, reward=Campaign.Reward.NONE)
        self.assertEqual(self.go(before, jd(1404, 12, 28)).issued, 1)
        self.assertEqual(CampaignIssuance.objects.get().cycle_key, "1405")

    def test_esfand_30_policy_non_leap_and_leap_years(self):
        leap_born = self.customer_with_order("اسفند۳۰", birth_date=jd(1403, 12, 30))
        regular = self.customer_with_order("اسفند۲۹", birth_date=jd(1402, 12, 29))
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        # ۱۴۰۴ کبیسه نیست: هر دو در ۲۹ اسفند جشن می‌گیرند
        run = self.go(campaign, jd(1404, 12, 29))
        self.assertEqual(run.issued, 2)
        self.assertEqual(set(CampaignIssuance.objects.values_list("customer_id", flat=True)), {leap_born.pk, regular.pk})
        # ۱۴۰۸ کبیسه: ۲۹ اسفند فقط برای متولدِ ۲۹، و ۳۰ اسفند برای متولدِ ۳۰
        CampaignIssuance.objects.all().delete()
        self.assertEqual(self.go(campaign, jd(1408, 12, 29)).issued, 1)
        self.assertEqual(CampaignIssuance.objects.get().customer, regular)
        self.assertEqual(self.go(campaign, jd(1408, 12, 30)).issued, 1)
        self.assertEqual(CampaignIssuance.objects.filter(customer=leap_born, cycle_key="1408").count(), 1)

    def test_no_birthday_no_issue_and_other_store_customers_excluded(self):
        from apps.core.models import ShopSettings
        from apps.stores.models import Store

        nobody = self.customer_with_order("بی‌تولد")
        other = Store.objects.create(name="دیگر", slug="occ-other", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other)
        stranger = self.customer("غریبه", birth_date=jd(1370, 5, 5))
        p = self.product("x", 1 * M, store=other)
        self.order(stranger, [(p, 1)], when=jdt(1404, 1, 1), store=other)
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        self.assertEqual(self.go(campaign, jd(1405, 5, 5)).issued, 0)
        self.assertNotIn(nobody.pk, occasions.resolve_candidates(campaign, jd(1405, 5, 5)))
        self.assertNotIn(stranger.pk, occasions.resolve_candidates(campaign, jd(1405, 5, 5)))

    def test_promotional_consent_respected_but_reward_still_saved(self):
        c = self.customer_with_order("بدون رضایت", email="n@example.com", birth_date=jd(1370, 5, 5), sms=False, mail=False)
        campaign = self.occ(Campaign.Occasion.BIRTHDAY)
        self.go(campaign, jd(1405, 5, 5))
        self.assertTrue(Coupon.objects.filter(customer=c).exists())
        rows = NotificationOutbox.objects.filter(event_key="occasion.birthday")
        self.assertTrue(rows and all(r.status == "skipped" for r in rows))

    def test_rule_tree_further_restricts_occasion(self):
        vip = self.customer_with_order("وی‌آی‌پی", birth_date=jd(1370, 5, 5))
        normal = self.customer_with_order("عادی", birth_date=jd(1371, 5, 5))
        tree = {"type": "customer_ids", "ids": [vip.pk]}
        campaign = self.occ(Campaign.Occasion.BIRTHDAY, rules=tree)
        self.go(campaign, jd(1405, 5, 5))
        self.assertEqual(list(CampaignIssuance.objects.values_list("customer_id", flat=True)), [vip.pk])

    def test_scheduler_runs_occasion_campaigns_for_store_today(self):
        from unittest.mock import patch

        self.customer_with_order("م", birth_date=jd(1370, 5, 5))
        self.occ(Campaign.Occasion.BIRTHDAY)
        fake_now = dt.datetime.combine(jd(1405, 5, 5), dt.time(9, 0), tzinfo=cs.store_timezone())
        with patch.object(cs, "store_now", return_value=fake_now):
            first = cs.run_due_campaigns()
            second = cs.run_due_campaigns()
        self.assertEqual((first["issued"], second["issued"]), (1, 0))


class ProfileBirthDateTests(OccasionBase):
    def test_parse_inputs(self):
        from apps.customers.services.profile_service import BirthDateError, parse_birth_date

        self.assertEqual(parse_birth_date("۱۳۷۰/۰۵/۲۳"), dt.date(1991, 8, 14))
        self.assertEqual(parse_birth_date("1370-5-23"), dt.date(1991, 8, 14))
        self.assertEqual(parse_birth_date("1991-08-14"), dt.date(1991, 8, 14))
        self.assertIsNone(parse_birth_date("  "))
        for bad in ["1370/13/01", "1404/12/30", "abc", "1370/05", "3000-01-01", "1200/01/01", "1900-01-01"]:
            with self.assertRaises(BirthDateError, msg=bad):
                parse_birth_date(bad)

    def test_update_blank_never_clears_and_changes_are_detected(self):
        from apps.customers.services.profile_service import update_birth_date

        c = self.customer("م")
        self.assertTrue(update_birth_date(c, "1370/05/23"))
        self.assertEqual(c.birth_date, dt.date(1991, 8, 14))
        self.assertEqual(c.birth_month_day, 523)
        self.assertFalse(update_birth_date(c, ""))
        self.assertFalse(update_birth_date(c, "1370/05/23"))
        c.refresh_from_db()
        self.assertEqual(c.birth_date, dt.date(1991, 8, 14))
        self.assertTrue(update_birth_date(c, "1371/01/01"))
        c.refresh_from_db()
        self.assertEqual((c.birth_date, c.birth_month_day), (dt.date(1992, 3, 21), 101))

    def test_save_with_update_fields_keeps_month_day_in_sync(self):
        c = self.customer("م")
        c.birth_date = jd(1371, 12, 29)
        c.save(update_fields=["birth_date"])
        c.refresh_from_db()
        self.assertEqual(c.birth_month_day, 1229)

    def test_promotion_preferences(self):
        from apps.customers.services.profile_service import update_communication_preferences

        c = self.customer("م")
        self.assertTrue(update_communication_preferences(c, sms=False))
        self.assertFalse(update_communication_preferences(c, sms=False))
        c.refresh_from_db()
        self.assertFalse(c.accepts_promotional_sms)
        self.assertTrue(c.accepts_promotional_email)


class OtherOccasionTests(OccasionBase):
    def test_registration_anniversary(self):
        c = self.customer_with_order("سالگرد")
        Customer.objects.filter(pk=c.pk).update(created_at=jdt(1403, 6, 10))
        campaign = self.occ(Campaign.Occasion.REGISTRATION_ANNIVERSARY, name="سالگرد ثبت‌نام")
        self.assertEqual(self.go(campaign, jd(1403, 6, 10)).issued, 0)    # همان روزِ ثبت‌نام، سالگرد نیست
        self.assertEqual(self.go(campaign, jd(1404, 6, 10)).issued, 1)
        self.assertEqual(self.go(campaign, jd(1404, 6, 10)).issued, 0)
        self.assertEqual(self.go(campaign, jd(1405, 6, 10)).issued, 1)

    def test_first_purchase_anniversary(self):
        c = self.customer("اولین خرید")
        self.order(c, [(self.item, 1)], when=jdt(1403, 3, 15))
        self.order(c, [(self.item, 1)], when=jdt(1404, 1, 1))
        campaign = self.occ(Campaign.Occasion.FIRST_PURCHASE_ANNIVERSARY)
        self.assertEqual(self.go(campaign, jd(1404, 3, 15)).issued, 1)
        self.assertEqual(self.go(campaign, jd(1404, 1, 1)).issued, 0)

    def test_order_count_and_spending_milestones_issue_once(self):
        c = self.customer("نقطه عطف")
        for i in range(3):
            self.order(c, [(self.item, 1)], when=jdt(1404, 2, 1 + i))
        orders = self.occ(Campaign.Occasion.ORDER_MILESTONE, params={"n": 3}, name="سه سفارش")
        spend = self.occ(Campaign.Occasion.SPENDING_MILESTONE, params={"amount": 3 * M}, name="سه میلیون")
        too_high = self.occ(Campaign.Occasion.ORDER_MILESTONE, params={"n": 4}, name="چهار سفارش")
        today = jd(1404, 5, 1)
        self.assertEqual((self.go(orders, today).issued, self.go(spend, today).issued, self.go(too_high, today).issued), (1, 1, 0))
        self.assertEqual((self.go(orders, today).issued, self.go(spend, today).issued), (0, 0))

    def test_reactivation(self):
        c = self.customer("غیرفعال")
        self.order(c, [(self.item, 1)], when=jdt(1404, 1, 1))
        campaign = self.occ(Campaign.Occasion.REACTIVATION, params={"days": 90})
        self.assertEqual(self.go(campaign, jd(1404, 2, 1)).issued, 0)
        self.assertEqual(self.go(campaign, jd(1404, 6, 1)).issued, 1)
        self.assertEqual(self.go(campaign, jd(1404, 7, 1)).issued, 0)   # همان دوره‌ی عدمِ خرید
        self.order(c, [(self.item, 1)], when=jdt(1404, 7, 2))             # بازگشت
        self.assertEqual(self.go(campaign, jd(1405, 1, 2)).issued, 1)    # دوره‌ی جدیدِ عدمِ خرید

    def test_holiday_and_custom_date(self):
        c = self.customer_with_order("تعطیلات")
        yalda = self.occ(Campaign.Occasion.HOLIDAY, params={"month": 9, "day": 30}, name="شب یلدا")
        self.assertEqual(self.go(yalda, jd(1405, 9, 30)).issued, 1)
        self.assertEqual(self.go(yalda, jd(1405, 9, 29)).issued, 0)
        self.assertEqual(self.go(yalda, jd(1406, 9, 30)).issued, 1)
        custom = self.occ(Campaign.Occasion.CUSTOM_DATE, params={"date": "2026-12-25"}, name="جشنواره")
        self.assertEqual(self.go(custom, dt.date(2026, 12, 25)).issued, 1)
        self.assertEqual(self.go(custom, dt.date(2026, 12, 25)).issued, 0)
        self.assertEqual(self.go(custom, dt.date(2026, 12, 26)).issued, 0)
        self.assertTrue(NotificationOutbox.objects.filter(event_key="occasion.generic").exists())

    def test_invalid_occasion_params_block_activation(self):
        for kind, params in [
            (Campaign.Occasion.ORDER_MILESTONE, {}), (Campaign.Occasion.SPENDING_MILESTONE, {"amount": -5}),
            (Campaign.Occasion.REACTIVATION, {"days": 0}), (Campaign.Occasion.HOLIDAY, {"month": 13, "day": 1}),
            (Campaign.Occasion.HOLIDAY, {"month": 7, "day": 31}), (Campaign.Occasion.CUSTOM_DATE, {"date": "nope"}),
        ]:
            c = Campaign(store=self.store, name="x", trigger_type=Campaign.Trigger.OCCASION, occasion_kind=kind,
                         occasion_params=params, coupon_value=Decimal("10"), code_valid_days=3)
            self.assertTrue(cs.validate_campaign(c), (kind, params))
        c = Campaign(store=self.store, name="x", trigger_type=Campaign.Trigger.OCCASION, occasion_kind="",
                     coupon_value=Decimal("10"), code_valid_days=3)
        self.assertTrue(any("مناسبت" in e for e in cs.validate_campaign(c)))
