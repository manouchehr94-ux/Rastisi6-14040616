"""Fast-delivery fixes (2026-11-08): (1) the trial banner's «خرید اشتراک» must lead to the plan page, not back to the overview;
(2) the old «تیم و اشتراک» tab is two independent top-level tabs. URLs are unchanged."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.tests.platform_payment_support import patch_zibal, ready_platform_zibal
from apps.billing.tests.test_trial_purchase_flow import PW, formula_plan, make_owner
from apps.dashboard import navigation
from apps.stores.models import StoreMembership
from apps.subscriptions.services import entitlement_service as ent

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class BuyLinkTests(TestCase):
    def setUp(self):
        ready_platform_zibal(self)
        patch_zibal(self)
        # the QA plan: code «123», yearly 9,600,000 toman (800,000 × 12, no discount) — numeric codes must work end to end
        from apps.subscriptions.models import Plan
        from apps.subscriptions.services import plan_service as ps
        from apps.subscriptions.tests.test_pricing_dynamic import make_plan

        _p, draft = make_plan("123", base=800_000, order=1, publish=False)
        ps.set_formula_pricing(draft, monthly_price=800_000, discounts={"quarterly": 0, "semiannual": 0, "yearly": 0})
        ps.publish_plan_version(draft)
        self.plan = Plan.objects.get(code="123")
        self.version = self.plan.versions.get(status="published")
        self.owner, self.store = make_owner("buylink@example.com", "QA Trial 30")
        self.host = f"{self.store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        self.c = Client(HTTP_HOST=self.host)
        self.c.login(username=self.owner.username, password=PW)

    def test_the_banner_buy_link_goes_to_the_plan_page_on_every_page_including_the_overview(self):
        for name in ("dashboard:subscription-overview", "dashboard:subscription-history", "dashboard:usage-overview"):
            html = self.c.get(reverse(name)).content.decode()
            self.assertIn('data-testid="trial-banner-buy"', html, name)
            self.assertIn(f'href="{reverse("dashboard:subscription-plans")}" data-testid="trial-banner-buy"', html, name)

    def test_non_owner_banner_does_not_offer_a_buy_link(self):
        admin = User.objects.create_user(username="buylink-adm@example.com", password=PW, is_staff=True)
        StoreMembership.objects.create(store=self.store, user=admin, role=StoreMembership.Role.ADMINISTRATOR,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        c = Client(HTTP_HOST=self.host)
        c.login(username=admin.username, password=PW)
        html = c.get(reverse("dashboard:subscription-overview")).content.decode()
        self.assertNotIn('data-testid="trial-banner-buy"', html)
        self.assertEqual(c.get(reverse("dashboard:subscription-plans")).status_code, 403)

    def test_plan_123_with_all_four_periods_preview_invoice_and_no_activation_without_payment(self):
        page = self.c.get(reverse("dashboard:subscription-plans") + "?plan=123&period=yearly")
        html = page.content.decode()
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-plan="123"', html)
        self.assertRegex(html, r'value="yearly"\s+checked')                        # the choice from the public page is honoured
        expected = {"monthly": 800_000, "quarterly": 2_400_000, "semiannual": 4_800_000, "yearly": 9_600_000}
        for interval, amount in expected.items():
            self.assertEqual(int(self.version.price_for(interval)), amount)
            resp = self.c.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.version.pk, "billing_interval": interval})
            self.assertEqual(int(resp.context["preview"]["payable_amount"]), amount, interval)
        token = self.c.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.version.pk, "billing_interval": "yearly"}).context["preview"]["token"]
        resp = self.c.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.version.pk, "preview_token": token, "billing_interval": "yearly"})
        invoice = SubscriptionInvoice.objects.get(store=self.store, kind="plan_change")
        self.assertRedirects(resp, reverse("dashboard:platform-checkout", args=["subscription", invoice.pk]), fetch_redirect_response=False)
        self.assertEqual(int(invoice.grand_total), 9_600_000)
        self.assertEqual(self.c.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])).status_code, 200)
        sub = ent.get_current_subscription(self.store)                              # nothing paid ⇒ still the Trial
        self.assertEqual((sub.plan_version.plan.code, sub.status), ("trial", "trialing"))

    def test_the_selection_made_at_sign_up_survives_login_in_the_session(self):
        from apps.subscriptions.services.pricing_page_service import resolve_selection

        client = Client(HTTP_HOST="rastisi.localhost")
        client.get("/register/?plan=123&period=yearly")
        self.assertEqual(client.session.get("portal_selected_plan"), {"code": "123", "interval": "yearly"})
        client.login(username=self.owner.username, password=PW)                    # login cycles the session key but keeps its data
        self.assertEqual(client.session.get("portal_selected_plan"), {"code": "123", "interval": "yearly"})
        self.assertEqual(resolve_selection("123", "yearly")[1], "yearly")
        page = client.get(f"/app/stores/{self.store.public_id}/billing/")           # the portal billing page picks it up
        self.assertEqual((page.context["selected_plan_id"], page.context["selected_interval"]), (self.plan.pk, "yearly"))


class TabsTests(TestCase):
    def test_the_old_combined_tab_is_gone_and_two_independent_tabs_exist(self):
        keys = {t.key: t for sec in navigation.SECTIONS for t in sec.tabs} if hasattr(navigation, "SECTIONS") else {}
        self.assertNotIn("account", keys)
        self.assertEqual(keys["team"].label, "تیم و اعضا")
        self.assertEqual(keys["subscription"].label, "اشتراک و صورتحساب")
        self.assertEqual([c.label for c in keys["team"].children], ["اعضای تیم", "دعوت‌نامه‌ها", "نقش‌ها و دسترسی‌ها"])
        self.assertEqual([c.label for c in keys["subscription"].children],
                         ["اشتراک فعلی", "خرید، تغییر یا تمدید پلن", "صورتحساب‌ها و پرداخت‌ها", "مصرف و سقف‌ها", "تاریخچه اشتراک"])
        self.assertIn("settings-finance", keys)                                    # «مالی و پرداخت» (customer payments) is untouched
        self.assertEqual(keys["settings-finance"].label, "مالی و پرداخت")

    def test_every_existing_url_resolves_to_the_right_new_tab_and_subtab(self):
        cases = {
            "staff-list": ("team", "team-members"), "staff-add": ("team", "team-members"), "staff-change-role": ("team", "team-members"),
            "subscription-overview": ("subscription", "subscription-current"), "subscription-plans": ("subscription", "subscription-plans"),
            "subscription-plan-preview": ("subscription", "subscription-plans"), "subscription-history": ("subscription", "subscription-history"),
            "billing-overview": ("subscription", "billing"), "billing-invoice-detail": ("subscription", "billing"),
            "platform-checkout": ("subscription", "billing"), "usage-overview": ("subscription", "usage"),
        }
        for url_name, (tab, child) in cases.items():
            with self.subTest(url=url_name):
                section, got_tab = navigation.resolve_active(url_name, {}, "")
                self.assertEqual((section, got_tab), ("settings", tab))
                tab_obj = next(t for sec in navigation.SECTIONS for t in sec.tabs if t.key == tab)
                self.assertEqual(navigation.resolve_child(tab_obj, url_name, {}), child)
        team = next(t for sec in navigation.SECTIONS for t in sec.tabs if t.key == "team")
        self.assertEqual(navigation.resolve_child(team, "staff-list", {"status": "invited"}), "team-invitations")
        self.assertEqual(navigation.resolve_child(team, "staff-list", {"view": "roles"}), "team-roles")
