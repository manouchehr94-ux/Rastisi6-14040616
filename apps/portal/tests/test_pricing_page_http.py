"""Public /plans/ page, Platform Admin pricing management and the plan → registration/purchase handoff over real HTTP.
Synthetic plan values; mocked/absent gateways (invoices only — no payment is ever taken)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import confirmation_service
from apps.core.models import AuditLogEntry
from apps.portal.models import PlatformAuditLogEntry
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import OptionalService, Plan, PlanFaq, PlanVersion, PricingFeature, StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc
from apps.subscriptions.tests.test_pricing_dynamic import make_plan, store_on

User = get_user_model()
PUBLIC = "rastisi.localhost"
ADMIN = "platformadmins.rastisi.localhost"
STORE_HOST = "pricehttp.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, STORE_HOST, "testserver"])
class PublicPricingPageTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        make_plan("base", base=290000, order=1, trial=14, extra={"quarterly": (780000, 870000, ""), "yearly": (2900000, 3480000, "۲ ماه رایگان")},
                  limits={"catalog.products": 200, "staff.members": 2}, flags={"catalog.import": False}, tagline="شروعِ سبک")
        make_plan("advanced", base=690000, order=2, trial=0, recommended=True, extra={"yearly": 6900000},
                  limits={"catalog.products": None, "staff.members": 8}, flags={"catalog.import": True}, badge_text="محبوب‌ترین")
        make_plan("ultra", base=1490000, order=3, extra={"yearly": 14900000}, limits={"catalog.products": None}, flags={"catalog.import": True})

    def get(self, path="/plans/"):
        return self.client.get(path, HTTP_HOST=PUBLIC)

    def test_three_cards_with_real_prices_periods_trials_and_the_recommended_highlight(self):
        html = self.get().content.decode()
        self.assertEqual(html.count('class="pz-tag'), 3)
        self.assertEqual(html.count('class="pz-tag pop"'), 1)
        for needle in ("۲۹۰٬۰۰۰", "۶۹۰٬۰۰۰", "۱٬۴۹۰٬۰۰۰", "۳۰ روز دوره‌ی آزمایشیِ رایگان", "محبوب‌ترین", "۲ ماه رایگان"):
            self.assertIn(needle, html, needle)
        # the initial Trial is ONE platform policy shown on every card (never a per-plan claim)
        self.assertEqual(html.count("روز دوره‌ی آزمایشیِ رایگان"), 3)
        self.assertNotIn("دوره‌ی آزمایشی برایِ این پلن تعریف نشده است", html)
        self.assertEqual(html.count("data-period="), 3)                          # monthly / quarterly / yearly toggle
        self.assertIn("پرداختِ اشتراک تک‌مرحله‌ای و بدونِ برداشتِ خودکار", html)

    def test_matrix_groups_the_seven_categories_and_uses_exact_quotas_not_checkmarks(self):
        html = self.get().content.decode()
        for label in ("عملیاتِ فروشگاه", "زیرساختِ فنی", "سئو و محتوا", "پرداخت", "طراحی و شخصی‌سازیِ ویترین", "بازاریابی و رشدِ فروش"):
            self.assertIn(f"<summary>{label}</summary>", html, label)
        self.assertNotIn("خدماتِ حرفه‌ایِ اختیاری", html)                        # no services configured ⇒ no empty section
        self.assertIn("۲۰۰ کالا", html)
        self.assertIn("نامحدود", html)
        self.assertIn("۲ عضو", html)
        row = html.split('data-feature="import"')[1].split('data-feature="')[0]
        self.assertEqual(row.count("pz-yes"), 2)                                 # advanced + ultra only
        self.assertEqual(row.count("pz-none"), 1)
        domain_row = html.split('data-feature="custom_domain"')[1].split('data-feature="')[0]
        self.assertEqual(domain_row.count("pz-yes"), 3)                          # no explicit value ⇒ fail-open ⇒ available

    def test_unimplemented_capabilities_are_never_advertised(self):
        html = self.get().content.decode()
        self.assertNotIn('data-feature="api"', html)
        self.assertNotIn("Webhook برای توسعه‌دهندگان", html)

    def test_optional_services_and_faq_appear_only_when_the_owner_configures_them(self):
        html = self.get().content.decode()
        self.assertNotIn("pz-faqtag", html)
        PlanFaq.objects.create(question="پرسشِ آزمایشیِ سراسری؟", answer="پاسخ سراسری")
        PlanFaq.objects.create(question="پرسشِ پلنِ پایه؟", answer="پاسخ پایه", plan=Plan.objects.get(code="base"))
        service = OptionalService.objects.create(code="onboarding", title="راه‌اندازیِ همراه با کارشناس", price=1500000, is_active=True)
        service.plan_modes.create(plan=Plan.objects.get(code="advanced"), mode="included")
        html = self.get().content.decode()
        self.assertIn("پرسشِ آزمایشیِ سراسری؟", html)
        self.assertIn("پرسشِ پلنِ پایه؟", html)
        self.assertIn("درباره‌ی پلنِ Base", html)
        self.assertIn("راه‌اندازیِ همراه با کارشناس", html)
        self.assertIn('data-service="onboarding"', html)

    def test_publication_and_visibility_rules_apply_to_the_public_page(self):
        make_plan("draftonly", publish=False, order=9)
        make_plan("secret", selectable=False, order=10)
        make_plan("gone", active=False, order=11)
        html = self.get().content.decode()
        for code in ("draftonly", "secret", "gone"):
            self.assertNotIn(f'data-plan="{code}"', html)
        self.assertEqual(html.count('class="pz-tag'), 3)

    def test_price_edit_on_a_new_version_changes_the_page_but_not_the_old_one(self):
        from apps.subscriptions.services import plan_service as ps

        plan = Plan.objects.get(code="base")
        v2 = ps.create_plan_version(plan, display_price=350000, billing_interval="monthly", trial_days=7)
        ps.publish_plan_version(v2)
        html = self.get().content.decode()
        self.assertIn("۳۵۰٬۰۰۰", html)
        self.assertIn("۳۰ روز دوره‌ی آزمایشیِ رایگان", html)               # the Trial is a platform policy, not part of the plan version
        self.assertNotIn("۷ روز دوره", html)
        self.assertEqual(PlanVersion.objects.get(plan=plan, version_number=1).display_price, 290000)

    def test_empty_state_when_nothing_is_published(self):
        PlanVersion.objects.update(status="retired")
        html = self.get().content.decode()
        self.assertIn("هنوز پلن عمومی", html)
        self.assertNotIn("pz-matrix", html)

    def test_cta_carries_the_plan_and_period_for_visitors_and_goes_to_billing_for_owners(self):
        html = self.get().content.decode()
        self.assertIn("/register/?plan=base&amp;period=monthly", html)
        self.assertIn('data-base="/register/?plan=advanced"', html)
        owner = User.objects.create_user(username="09121230055", password="x")
        store = Store.objects.create(name="o", slug="cta-store", admin_subdomain="cta-store", status=Store.Status.ACTIVE)
        StoreMembership.objects.create(store=store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.force_login(owner)
        html = self.get().content.decode()
        self.assertIn(f"/app/stores/{store.public_id}/billing/", html)
        self.assertNotIn("/register/?plan=", html)

    def test_page_has_rtl_lang_accessible_labels_and_no_hardcoded_blanket_trial_claim(self):
        html = self.get().content.decode()
        self.assertIn('lang="fa" dir="rtl"', html)
        self.assertIn('role="radiogroup"', html)
        self.assertIn("pricing.js", html)
        self.assertNotIn("همه پلن‌ها با", html.split('class="pz-controls"')[0])   # the lead copy no longer promises one trial to all


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, STORE_HOST, "testserver"])
class RegistrationSelectionTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        make_plan("pick", base=100000, trial=14, extra={"yearly": 1000000})
        make_plan("nopick", base=100000, trial=0)

    def test_valid_selection_is_remembered_server_side_and_garbage_is_ignored(self):
        self.client.get("/register/?plan=pick&period=yearly", HTTP_HOST=PUBLIC)
        self.assertEqual(self.client.session["portal_selected_plan"], {"code": "pick", "interval": "yearly"})
        self.client.get("/register/?plan=pick&period=semiannual", HTTP_HOST=PUBLIC)       # not offered ⇒ cleared
        self.assertNotIn("portal_selected_plan", self.client.session)
        self.client.get("/register/?plan=%27%3Bdrop&period=monthly", HTTP_HOST=PUBLIC)
        self.assertNotIn("portal_selected_plan", self.client.session)

    def test_a_selected_plan_never_replaces_the_initial_trial_it_is_only_remembered_for_the_purchase(self):
        from apps.portal.services import provisioning_service

        owner = User.objects.create_user(username="09121230066", password="x")
        version = PlanVersion.objects.get(plan__code="pick")
        store, created = provisioning_service.provision_initial_trial_store(owner=owner, name="فروشگاه انتخاب", plan_version=version)
        self.assertTrue(created)
        sub = ent.get_current_subscription(store)
        self.assertEqual((sub.plan_version.plan.code, sub.status), ("trial", "trialing"))        # the independent initial Trial …
        self.assertNotEqual(sub.plan_version_id, version.pk)                                      # … not the chosen plan (no second/free paid plan)
        self.assertAlmostEqual((sub.trial_end_at - sub.trial_start_at).days, 30, delta=1)


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, STORE_HOST, "testserver"], RASTISI_BILLING_PROVIDER="manual", RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class OwnerPurchaseWithPeriodTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.trial_plan, self.trial_v = make_plan("trialx", base=0, interval="none", trial=14)
        self.plan, self.version = make_plan("buyable", base=100000, extra={"quarterly": 270000, "yearly": 1000000})
        self.store, self.sub = store_on(self.trial_v, "buy-store", status="trialing")
        self.owner = User.objects.create_user(username="09121230077", password="x")
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        from apps.billing.tests.platform_payment_support import ready_platform_zibal

        ready_platform_zibal(self)                      # a purchase is refused unless a platform payment method is ready
        self.client.force_login(self.owner)

    def checkout(self, interval=None, version=None):
        data = {"billing_interval": interval} if interval is not None else {}
        return self.client.post(f"/app/stores/{self.store.public_id}/billing/checkout/{(version or self.version).pk}/", data, HTTP_HOST=PUBLIC)

    def test_billing_plans_page_lists_one_buy_button_per_offered_period(self):
        html = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=PUBLIC).content.decode()
        for interval in ("monthly", "quarterly", "yearly"):
            self.assertIn(f'name="billing_interval" value="{interval}"', html)
        self.assertNotIn('value="semiannual"', html)

    def test_checkout_creates_an_invoice_for_the_chosen_period_and_activates_nothing_by_itself(self):
        self.checkout("yearly")
        invoice = SubscriptionInvoice.objects.get(subscription=self.sub, kind="plan_change")
        self.assertEqual(invoice.grand_total, 1000000)
        self.assertEqual(invoice.lines.get().plan_version_snapshot["billing_interval"], "yearly")
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.status, sub.plan_version_id), ("trialing", self.trial_v.pk))     # a browser POST is never proof of payment
        confirmation_service.mark_invoice_paid_manually(invoice)
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.status, sub.plan_version_id, sub.billing_interval), ("active", self.version.pk, "yearly"))

    def test_forged_or_unoffered_period_is_rejected_without_any_invoice(self):
        for bad in ("semiannual", "weekly", "<script>"):
            response = self.checkout(bad)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_draft_or_retired_versions_cannot_be_purchased(self):
        draft_plan, draft = make_plan("draftbuy", publish=False)
        self.assertEqual(self.checkout("monthly", draft).status_code, 404)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_another_owner_cannot_purchase_for_this_store(self):
        stranger = User.objects.create_user(username="09121230088", password="x")
        self.client.force_login(stranger)
        response = self.checkout("yearly")
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, STORE_HOST, "testserver"])
class PlatformAdminPricingManagementTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.admin = User.objects.create_user(username="pa-pricing@example.com", password="x", is_staff=True, is_superuser=True)
        self.staff = User.objects.create_user(username="pa-staff-pricing@example.com", password="x", is_staff=True)
        self.owner = User.objects.create_user(username="09121230099", password="x")
        self.client.force_login(self.admin)

    def post(self, path, data):
        return self.client.post(path, data, HTTP_HOST=ADMIN)

    def plan_post(self, **extra):
        data = {
            "name": "Alpha", "code": "alpha", "public_title": "آلفا", "description": "d", "display_order": "1",
            "marketing_submitted": "1", "tagline": "شعار", "badge_text": "برگزیده", "cta_label": "شروع کنید",
            "billing_interval": "monthly", "price_monthly": "100000", "price_quarterly": "270000", "compare_quarterly": "300000",
            "price_yearly": "1000000", "label_yearly": "۲ ماه رایگان", "trial_days": "10", "trial_once_submitted": "1",
            "trial_once_per_store": "on", "is_recommended": "on", "public_selectable_submitted": "1", "is_publicly_selectable": "on",
            "entitlement_catalog.products": "25", "entitlement_catalog.import": "on", "entitlement_staff.members_unlimited": "on",
            "entitlement_catalog.attributes": "on",          # not enforced → must be ignored
        }
        data.update(extra)
        return self.post("/plans/add/", data)

    def test_owner_configures_periods_discounts_trial_marketing_and_quotas_in_one_form(self):
        self.assertEqual(self.plan_post().status_code, 302)
        plan = Plan.objects.get(code="alpha")
        self.assertEqual((plan.tagline, plan.badge_text, plan.cta_label, plan.is_recommended), ("شعار", "برگزیده", "شروع کنید", True))
        version = plan.versions.get()
        self.assertEqual((version.status, version.display_price, version.trial_days, version.trial_once_per_store), ("draft", 100000, 10, True))
        options = version.price_options()
        self.assertEqual(set(options), {"monthly", "quarterly", "yearly"})
        self.assertEqual(options["quarterly"]["compare_at"], 300000)
        self.assertEqual(options["yearly"]["label"], "۲ ماه رایگان")
        pe = {e.entitlement.key: e for e in version.plan_entitlements.select_related("entitlement")}
        self.assertEqual(pe["catalog.products"].integer_limit, 25)
        self.assertTrue(pe["catalog.import"].is_enabled)
        self.assertTrue(pe["staff.members"].is_unlimited)
        self.assertNotIn("catalog.attributes", pe)                          # unenforced entitlements cannot be "sold"
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_admin.plan_created").exists())

    def test_editing_a_published_plan_creates_a_new_draft_and_never_touches_the_published_version(self):
        self.plan_post()
        plan = Plan.objects.get(code="alpha")
        v1 = plan.versions.get()
        self.post(f"/plans/{plan.pk}/versions/{v1.pk}/publish/", {})
        v1.refresh_from_db()
        self.assertEqual(v1.status, "published")
        before = v1.price_options()
        self.assertEqual(self.plan_post().status_code, 200)               # a duplicate code is refused, not a 500
        self.client.post(f"/plans/{plan.pk}/edit/", {"name": "Alpha", "code": "alpha", "price_monthly": "150000", "billing_interval": "monthly",
                                                      "price_yearly": "1400000", "trial_days": "0", "public_selectable_submitted": "1",
                                                      "is_publicly_selectable": "on"}, HTTP_HOST=ADMIN)
        versions = list(plan.versions.order_by("version_number"))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].price_options(), before)
        self.assertEqual(versions[0].status, "published")
        self.assertEqual((versions[1].status, versions[1].display_price), ("draft", 150000))

    def test_publication_is_refused_for_an_incoherent_version(self):
        from apps.subscriptions.models import PlanVersionPrice
        from apps.subscriptions.services import plan_service as ps

        plan = Plan.objects.create(code="broken", name="B")
        v = ps.create_plan_version(plan, display_price=100, billing_interval="monthly")
        PlanVersionPrice.objects.create(plan_version=v, billing_interval="yearly", price=1000, compare_at_price=500)   # bypassing the service
        self.assertIn("قبل از تخفیف", " ".join(ps.validate_for_publication(v)))
        with self.assertRaises(ps.PlanServiceError):
            ps.publish_plan_version(v)

    def test_pricing_content_page_edits_text_faq_services_and_is_audited(self):
        page = self.client.get("/plans/content/", HTTP_HOST=ADMIN)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "گزارشِ شکاف")
        feature = PricingFeature.objects.get(key="coupons")
        self.post("/plans/content/", {"action": "feature", "id": feature.pk, "title": "تخفیفِ ویژه", "description": "توضیح تازه", "display_order": "7", "is_visible": "on"})
        feature.refresh_from_db()
        self.assertEqual((feature.title, feature.description, feature.display_order), ("تخفیفِ ویژه", "توضیح تازه", 7))
        planned = PricingFeature.objects.get(key="api")
        self.post("/plans/content/", {"action": "feature", "id": planned.pk, "title": planned.title, "is_visible": "on"})
        planned.refresh_from_db()
        self.assertFalse(planned.is_visible)                                 # cannot be forced public from the UI
        self.post("/plans/content/", {"action": "faq_save", "question": "پرسش؟", "answer": "پاسخ", "is_published": "on"})
        self.assertEqual(PlanFaq.objects.get().question, "پرسش؟")
        self.post("/plans/content/", {"action": "service_save", "code": "svc", "title": "خدمت", "price": "5000", "is_active": "on"})
        self.assertEqual(OptionalService.objects.get().price, 5000)
        self.assertEqual(self.post("/plans/content/", {"action": "bogus"}).status_code, 302)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code__startswith="platform_admin.pricing_content_").count() >= 4)

    def test_only_platform_superusers_can_reach_pricing_management(self):
        paths = [("get", "/plans/"), ("get", "/plans/add/"), ("get", "/plans/content/"), ("post", "/plans/content/")]
        for who in ("anonymous", "owner", "staff"):
            self.client.logout()
            if who == "owner":
                self.client.force_login(self.owner)
            elif who == "staff":
                self.client.force_login(self.staff)
            for method, path in paths:
                response = getattr(self.client, method)(path, {"action": "faq_save", "question": "x", "answer": "y"}, HTTP_HOST=ADMIN) if method == "post" else self.client.get(path, HTTP_HOST=ADMIN)
                self.assertIn(response.status_code, (302, 403, 404), (who, path))
        self.assertEqual(PlanFaq.objects.count(), 0)
        self.assertFalse(Plan.objects.filter(code="alpha").exists())

    def test_the_form_marks_unenforced_entitlements_as_not_applied(self):
        from apps.subscriptions.entitlements import sync_entitlement_definitions

        sync_entitlement_definitions()
        html = self.client.get("/plans/add/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn("هنوز اعمال‌نشده در کد", html)          # unenforced keys are listed (collapsed), not offered as controls
        self.assertIn('name="entitlement_catalog.products"', html)
        self.assertNotIn('name="entitlement_integrations.api"', html)
        self.assertIn("integrations.api", html)


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, STORE_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class DashboardPlanChangeWithPeriodTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.p1, self.v1 = make_plan("dlow", base=100000, order=1, limits={"catalog.products": 5})
        self.p2, self.v2 = make_plan("dhigh", base=300000, order=2, extra={"yearly": 3000000}, limits={"catalog.products": 50})
        self.store = Store.objects.create(name="d", slug="pricehttp", admin_subdomain="pricehttp", status=Store.Status.ACTIVE)
        self.sub = sub_svc.activate_subscription(sub_svc.create_subscription(self.store, self.v1), period_end=timezone.now() + timedelta(days=20))
        from apps.billing.tests.platform_payment_support import ready_platform_zibal

        ready_platform_zibal(self)                      # an upgrade is refused (no dead invoice) unless a platform method is ready
        self.owner = User.objects.create_user(username="dash-owner", password="x", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.force_login(self.owner)

    def test_preview_and_execute_carry_the_period_and_the_invoice_uses_it(self):
        preview = self.client.post("/admin-portal/subscription/plans/preview/", {"version_id": self.v2.pk, "billing_interval": "yearly"}, HTTP_HOST=STORE_HOST)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'name="billing_interval" value="yearly"')
        self.assertEqual(preview.context["preview"]["payable_amount"], 3000000)
        token = preview.context["preview"]["token"]
        response = self.client.post("/admin-portal/subscription/plans/change/", {"version_id": self.v2.pk, "preview_token": token, "billing_interval": "yearly"}, HTTP_HOST=STORE_HOST)
        self.assertEqual(response.status_code, 302)
        invoice = SubscriptionInvoice.objects.get(store=self.store, kind="plan_change")
        self.assertEqual(invoice.grand_total, 3000000)
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.v1.pk)       # unpaid ⇒ unchanged

    def test_unoffered_period_is_refused_at_preview(self):
        response = self.client.post("/admin-portal/subscription/plans/preview/", {"version_id": self.v2.pk, "billing_interval": "quarterly"}, HTTP_HOST=STORE_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_plans_page_offers_a_period_selector_only_when_several_periods_exist(self):
        html = self.client.get("/admin-portal/subscription/plans/", HTTP_HOST=STORE_HOST).content.decode()
        self.assertEqual(html.count('type="radio" name="billing_interval"'), 2)     # the multi-period plan offers its two periods as radios …
        self.assertEqual(html.count('type="hidden" name="billing_interval"'), 0)    # … the single-period plan is the CURRENT one (no form at all)
