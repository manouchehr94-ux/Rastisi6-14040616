"""Platform Admin «دوره‌ی آزمایشی» page + the public pricing split between new sellers and existing merchants (2026-11-07)."""

from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.tests.platform_payment_support import patch_zibal, ready_platform_zibal
from apps.billing.tests.test_trial_purchase_flow import PW, formula_plan, make_owner
from apps.portal.models import PlatformAuditLogEntry
from apps.portal.services import provisioning_service
from apps.portal.services.platform_config_service import get_platform_configuration
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import entitlement_service as ent, trial_service
from apps.subscriptions.tests.test_trial_engine import new_store

User = get_user_model()
ADMIN = "platformadmins.rastisi.localhost"
PUBLIC = "rastisi.localhost"
URL = "/trial/"


@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class TrialAdminBase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.staff = User.objects.create_user(username="ta-staff@example.com", password=PW, is_staff=True, is_superuser=True)
        self.plain_staff = User.objects.create_user(username="ta-plain@example.com", password=PW, is_staff=True)
        self.client_a = Client(HTTP_HOST=ADMIN)
        self.client_a.force_login(self.staff)

    def post(self, **data):
        return self.client_a.post(URL, data, follow=False)

    def limits(self, **override):
        """A complete valid limits form built from the page's own rows (so unknown keys stay valid)."""
        page = self.client_a.get(URL)
        data = {"action": "limits", "grace_period_days": "0"}
        for row in page.context["limit_rows"]:
            key = row["key"]
            if row["enabled"]:
                data[f"ent_{key}_enabled"] = "on"
            if row["numeric"]:
                if row["unlimited"]:
                    data[f"ent_{key}_unlimited"] = "on"
                else:
                    data[f"ent_{key}_limit"] = str(row["limit"] if row["limit"] is not None else 0)
        data.update(override)
        return data


class AccessTests(TrialAdminBase):
    def test_only_a_platform_superuser_can_open_or_change_it(self):
        anon = Client(HTTP_HOST=ADMIN)
        self.assertNotEqual(anon.get(URL).status_code, 200)
        plain = Client(HTTP_HOST=ADMIN)
        plain.force_login(self.plain_staff)
        self.assertNotEqual(plain.get(URL).status_code, 200)
        before = get_platform_configuration().default_trial_days
        self.assertNotEqual(plain.post(URL, {"action": "policy", "default_trial_days": "99", "trial_enabled": "on"}).status_code, 200)
        cache.clear()
        self.assertEqual(get_platform_configuration().default_trial_days, before)

    def test_merchants_cannot_reach_the_platform_trial_page(self):
        owner, store = make_owner("ta-merchant@example.com", "تاجر")
        merchant = Client(HTTP_HOST=f"{store.admin_subdomain}.rastisi.localhost")
        merchant.login(username=owner.username, password=PW)
        self.assertEqual(merchant.get(URL).status_code, 404)

    def test_page_renders_creates_the_internal_plan_and_is_in_the_navigation(self):
        Plan.objects.filter(code="trial").delete() if not StoreSubscription.objects.exists() else None
        response = self.client_a.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="trial-policy-form"')
        self.assertContains(response, 'data-testid="trial-limits-form"')
        self.assertContains(response, 'data-testid="trial-history"')
        self.assertContains(response, 'href="/trial/"')                                              # nav item (platform host has its own urlconf)
        self.assertFalse(Plan.objects.get(code="trial").is_publicly_selectable)


class PolicyTests(TrialAdminBase):
    def test_changing_the_default_days_is_validated_audited_and_only_affects_new_stores(self):
        old_store, _ = new_store("قبلی")
        old_end = ent.get_current_subscription(old_store).trial_end_at
        response = self.post(action="policy", default_trial_days="14", trial_enabled="on")
        self.assertEqual(response.status_code, 302)
        cache.clear()
        self.assertEqual(get_platform_configuration().default_trial_days, 14)
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_configuration.updated").latest("pk")
        self.assertEqual(entry.actor_id, self.staff.pk)
        self.assertIn("14", entry.after_summary)
        self.assertIn("30", entry.before_summary)
        self.assertEqual(ent.get_current_subscription(old_store).trial_end_at, old_end)
        fresh, _ = new_store("بعدی")
        sub = ent.get_current_subscription(fresh)
        self.assertEqual((sub.trial_end_at - sub.trial_start_at).days, 14)

    def test_invalid_days_are_rejected_and_nothing_changes(self):
        for bad in ("0", "366", "-5", "abc", "", "1.5"):
            with self.subTest(days=bad):
                response = self.client_a.post(URL, {"action": "policy", "default_trial_days": bad, "trial_enabled": "on"}, follow=True)
                self.assertContains(response, "مدتِ دوره‌ی آزمایشی")
                cache.clear()
                self.assertEqual(get_platform_configuration().default_trial_days, 30)

    def test_disabling_the_trial_applies_to_new_stores_and_keeps_running_trials(self):
        old_store, _ = new_store("جاری")
        self.post(action="policy", default_trial_days="30")                       # checkbox absent ⇒ disabled
        cache.clear()
        self.assertFalse(get_platform_configuration().trial_enabled)
        self.assertEqual(ent.get_current_subscription(old_store).status, StoreSubscription.Status.TRIALING)
        fresh, _ = new_store("بدون")
        self.assertEqual(ent.get_current_subscription(fresh).status, StoreSubscription.Status.SUSPENDED)
        self.assertIsNone(ent.get_current_subscription(fresh).trial_start_at)

    def test_the_configuration_form_also_validates_the_days(self):
        from apps.portal.forms import PlatformConfigurationForm

        config = get_platform_configuration()
        data = {name: getattr(config, name) for name in PlatformConfigurationForm.Meta.fields if name not in ("logo",)}
        data["default_trial_days"] = 0
        form = PlatformConfigurationForm(data, instance=config)
        self.assertFalse(form.is_valid())
        self.assertIn("default_trial_days", form.errors)


class LimitsTests(TrialAdminBase):
    def test_publishing_new_limits_makes_an_immutable_version_old_trials_keep_theirs(self):
        old_store, _ = new_store("قدیمی")
        old_version_id = ent.get_current_subscription(old_store).plan_version_id
        response = self.post(**self.limits(**{"ent_catalog.products_limit": "5", "grace_period_days": "3"}))
        self.assertEqual(response.status_code, 302)
        versions = list(Plan.objects.get(code="trial").versions.order_by("version_number"))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].status, "published")                                   # the old one is never edited
        self.assertEqual(versions[-1].grace_period_days, 3)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_admin.trial_limits_updated").exists())
        fresh, _ = new_store("جدید")
        self.assertEqual(ent.get_entitlement_limit(fresh, "catalog.products"), 5)
        self.assertEqual(ent.get_entitlement_limit(old_store, "catalog.products"), 20)         # grandfathered
        self.assertEqual(ent.get_current_subscription(old_store).plan_version_id, old_version_id)

    def test_features_can_be_switched_and_are_really_enforced(self):
        from apps.subscriptions.services import enforcement

        self.post(**self.limits(**{"ent_catalog.import_enabled": "on", "ent_catalog.import_rows_monthly_limit": "50"}))
        fresh, _ = new_store("واردات")
        self.assertEqual(ent.get_entitlement_limit(fresh, "catalog.import_rows_monthly"), 50)
        enforcement.enforce_feature(fresh, "catalog.import")                                    # no exception: enabled now

    def test_apply_to_active_trials_needs_a_reason_and_then_moves_them(self):
        old_store, _ = new_store("جاری")
        refused = self.client_a.post(URL, self.limits(**{"ent_catalog.products_limit": "7", "apply_to_active": "on"}), follow=True)
        self.assertContains(refused, "دلیل")
        self.assertEqual(Plan.objects.get(code="trial").versions.count(), 1)                    # nothing was published
        self.post(**self.limits(**{"ent_catalog.products_limit": "7", "apply_to_active": "on", "reason": "اصلاح سقف"}))
        self.assertEqual(ent.get_entitlement_limit(old_store, "catalog.products"), 7)

    def test_invalid_numbers_are_rejected_and_save_nothing(self):
        for bad in ("-1", "abc", ""):
            with self.subTest(limit=bad):
                response = self.client_a.post(URL, self.limits(**{"ent_catalog.products_limit": bad}), follow=True)
                self.assertContains(response, "سقفِ")
        self.assertEqual(Plan.objects.get(code="trial").versions.count(), 1)
        self.assertEqual(self.client_a.post(URL, self.limits(grace_period_days="99"), follow=True).status_code, 200)
        self.assertEqual(Plan.objects.get(code="trial").versions.count(), 1)

    def test_an_unchanged_save_creates_no_new_version(self):
        self.post(**self.limits())
        self.assertEqual(Plan.objects.get(code="trial").versions.count(), 1)


class HistoryTests(TrialAdminBase):
    def test_history_lists_running_ended_and_converted_trials_with_a_summary(self):
        running, _ = new_store("در جریان")
        ended, _ = new_store("پایان‌یافته")
        sub = ent.get_current_subscription(ended)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        from apps.subscriptions.services import subscription_service as ss

        ss.evaluate_subscription_states()
        _p, paid = formula_plan("hist-paid", 100000, order=3)
        converted, _ = new_store("تبدیل‌شده")
        csub = ent.get_current_subscription(converted)
        ss.change_plan_version(csub, paid)
        ss.activate_subscription(csub, period_end=timezone.now() + timedelta(days=30))
        response = self.client_a.get(URL)
        html = response.content.decode()
        for name in ("در جریان", "پایان‌یافته", "تبدیل‌شده"):
            self.assertIn(name, html)
        self.assertEqual(response.context["stats"], {"total": 3, "running": 1, "converted": 1, "ended": 1})
        self.assertIn("تبدیل‌شده به اشتراکِ پولی", html)


@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PublicPricingSplitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        trial_service.ensure_trial_plan()
        self.pro_plan, self.pro = formula_plan("pub-pro", 1_000_000, order=2)
        self.anon = Client(HTTP_HOST=PUBLIC)

    def test_the_trial_plan_is_not_on_the_public_page_and_the_platform_trial_is_advertised(self):
        html = self.anon.get("/plans/").content.decode()
        self.assertIn('data-plan="pub-pro"', html)
        self.assertNotIn('data-plan="trial"', html)
        self.assertIn("۳۰ روز دوره‌ی آزمایشیِ رایگان", html)

    def test_a_changed_default_is_what_the_public_page_says(self):
        from apps.subscriptions.tests.test_trial_engine import configure

        configure(days=45)
        cache.clear()
        self.assertIn("۴۵ روز", self.anon.get("/plans/").content.decode())
        configure(enabled=False)
        cache.clear()
        self.assertNotIn("روز دوره‌ی آزمایشیِ رایگان", self.anon.get("/plans/").content.decode())

    def test_a_visitor_can_register_with_the_plan_and_an_existing_merchant_can_log_in_and_buy_keeping_plan_and_period(self):
        html = self.anon.get("/plans/").content.decode()
        self.assertIn('data-cta="register"', html)
        self.assertIn("/register/?plan=pub-pro", html)
        self.assertIn('data-cta="login"', html)
        self.assertIn("%2Fplans%2F%3Fplan%3Dpub-pro%26period%3D", html)                      # login → back to /plans/ with plan AND period encoded in next

    def test_the_period_script_keeps_the_chosen_period_on_every_cta(self):
        js = (Path(__file__).resolve().parents[1] / "static/portal/js/pricing.js").read_text(encoding="utf-8")
        self.assertIn("a[data-base]", js)
        self.assertIn("data-sep", js)

    def test_a_logged_in_owner_goes_to_buy_never_to_register(self):
        owner, store = make_owner("pub-owner@example.com", "فروشگاه عمومی")
        client = Client(HTTP_HOST=PUBLIC)
        client.login(username=owner.username, password=PW)
        response = client.get("/plans/")
        html = response.content.decode()
        card = html[html.index('data-plan="pub-pro"'):]
        card = card[:card.index("</article>")]
        self.assertIn('data-cta="upgrade"', card)
        self.assertNotIn('data-cta="register"', card)
        self.assertNotIn("/register/", card)
        self.assertIn(f"/app/stores/{store.public_id}/billing/?plan=pub-pro&amp;period=", card)

    def test_the_billing_page_preselects_the_plan_and_period_from_the_public_page(self):
        owner, store = make_owner("pre-owner@example.com", "پیش‌انتخاب")
        client = Client(HTTP_HOST=PUBLIC)
        client.login(username=owner.username, password=PW)
        response = client.get(f"/app/stores/{store.public_id}/billing/?plan=pub-pro&period=yearly")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_plan_id"], self.pro_plan.pk)
        self.assertEqual(response.context["selected_interval"], "yearly")
        self.assertNotIn("trial", [o["version"].plan.code for o in response.context["plan_offers"]])

    def test_the_portal_checkout_refuses_the_trial_plan_and_older_versions(self):
        owner, store = make_owner("co-owner@example.com", "خرید پرتال")
        client = Client(HTTP_HOST=PUBLIC)
        client.login(username=owner.username, password=PW)
        trial_version = trial_service.trial_plan_version()
        self.assertEqual(client.post(f"/app/stores/{store.public_id}/billing/checkout/{trial_version.pk}/", {"billing_interval": "monthly"}).status_code, 404)
        old = self.pro
        PlanVersion.objects.create(plan=self.pro_plan, version_number=2, status="published", billing_interval="monthly", display_price=1_100_000)
        self.assertEqual(client.post(f"/app/stores/{store.public_id}/billing/checkout/{old.pk}/", {"billing_interval": "monthly"}).status_code, 404)

    def test_registration_remembers_only_a_real_offer_and_never_the_trial_plan(self):
        for query, expected in (("plan=pub-pro&period=yearly", {"code": "pub-pro", "interval": "yearly"}), ("plan=trial", None), ("plan=pub-pro&period=bogus", None)):
            with self.subTest(query=query):
                client = Client(HTTP_HOST=PUBLIC)
                client.get(f"/register/?{query}")
                self.assertEqual(client.session.get("portal_selected_plan"), expected)

    def test_an_authenticated_owner_opening_register_is_sent_to_the_app_not_a_second_signup(self):
        owner, _store = make_owner("reg-owner@example.com", "ثبت")
        client = Client(HTTP_HOST=PUBLIC)
        client.login(username=owner.username, password=PW)
        response = client.get("/register/?plan=pub-pro&period=yearly")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/register", response["Location"])
