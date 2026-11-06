"""Simple plan pricing end to end: owner enters ONE monthly price + discount % for 3/6/12 months; the server computes, snapshots
and (on publish) freezes the amounts; the public page, merchant selection, invoice, unified checkout, gateway amount, activation,
renewal and plan changes all show/charge exactly the same numbers. Legacy absolute prices are preserved. Synthetic data only."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import confirmation_service, plan_change_billing_service as pcb, renewal_service
from apps.billing.tests.platform_payment_support import patch_zibal, portal_buy_and_pay, ready_platform_zibal
from apps.portal.models import PlatformAuditLogEntry
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, PlanVersionPrice
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import period_pricing as pp
from apps.subscriptions.services import plan_service as ps
from apps.subscriptions.services import subscription_service as sub_svc
from apps.subscriptions.tests.test_pricing_dynamic import make_plan

User = get_user_model()
PUBLIC = "rastisi.localhost"
ADMIN = "platformadmins.rastisi.localhost"
D = Decimal


def fa(n):
    return f"{int(n):,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, ".rastisi.localhost", "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PricingBase(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.staff = User.objects.create_user(username="px-staff@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.admin = self.client_class(HTTP_HOST=ADMIN)
        self.admin.force_login(self.staff)

    def form(self, **extra):
        data = {
            "name": "پلن تست", "code": "px-plan", "public_title": "پلن تست", "display_order": "1", "marketing_submitted": "1",
            "public_selectable_submitted": "1", "is_publicly_selectable": "on", "trial_once_submitted": "1", "trial_days": "0",
            "pricing_formula_submitted": "1", "plan_kind": "paid", "monthly_price": "100000",
            "offer_quarterly": "on", "offer_semiannual": "on", "offer_yearly": "on",
            "discount_quarterly": "5", "discount_semiannual": "10", "discount_yearly": "15",
        }
        data.update(extra)
        return {k: v for k, v in data.items() if v is not None}

    def create_plan(self, **extra):
        response = self.admin.post("/plans/add/", self.form(**extra))
        return response, Plan.objects.filter(code=extra.get("code", "px-plan")).first()

    def prices(self, version):
        return {i: (o["price"], o["discount_percent"]) for i, o in version.price_options().items()}

    def publish(self, plan, version):
        return self.admin.post(f"/plans/{plan.pk}/versions/{version.pk}/publish/")


class OwnerFormTests(PricingBase):
    def test_the_form_has_one_monthly_price_and_three_discount_fields_and_no_spinners_or_manual_period_prices(self):
        html = self.admin.get("/plans/add/").content.decode()
        block = html.split("data-pricing")[1].split("حق‌دسترسی‌ها و سقف‌ها")[0]
        self.assertIn('name="monthly_price"', block)
        for interval in ("quarterly", "semiannual", "yearly"):
            self.assertIn(f'name="discount_{interval}"', block)
            self.assertIn(f'name="offer_{interval}"', block)
            self.assertNotIn(f'name="price_{interval}"', block)                      # no independent period price
            self.assertNotIn(f'name="compare_{interval}"', block)
        self.assertNotIn('type="number"', block)                                    # no native numeric spinner in the pricing section
        self.assertIn("platform-admin-pricing.js", html)
        self.assertIn("&quot;months&quot;", html)                                   # the preview reads the server's period table (escaped JSON attribute)

    def test_creating_a_plan_with_the_brief_example_stores_exact_server_computed_amounts(self):
        _r, plan = self.create_plan(monthly_price="1000", discount_quarterly="5", discount_semiannual="10", discount_yearly="15")
        v = plan.versions.get()
        self.assertEqual((v.status, v.billing_interval, v.display_price), ("draft", "monthly", D(1000)))
        self.assertEqual(self.prices(v), {
            "monthly": (D(1000), None), "quarterly": (D(2850), D("5.00")), "semiannual": (D(5400), D("10.00")), "yearly": (D(10200), D("15.00")),
        })
        rows = {r.billing_interval: r for r in v.prices.all()}
        self.assertEqual((rows["yearly"].compare_at_price, rows["yearly"].price), (D(12000), D(10200)))     # struck-through = exact undiscounted total

    def test_discounts_default_to_zero_when_left_blank(self):
        _r, plan = self.create_plan(discount_quarterly="", discount_semiannual="", discount_yearly="")
        v = plan.versions.get()
        self.assertEqual(self.prices(v), {"monthly": (D(100000), None), "quarterly": (D(300000), D("0.00")),
                                          "semiannual": (D(600000), D("0.00")), "yearly": (D(1200000), D("0.00"))})
        self.assertIsNone(v.prices.get(billing_interval="yearly").compare_at_price)

    def test_persian_digits_and_separators_are_accepted(self):
        _r, plan = self.create_plan(monthly_price="۱۰۰٬۰۰۰", discount_quarterly="۵", discount_yearly="۱۵٫۵")
        v = plan.versions.get()
        self.assertEqual(v.price_for("quarterly"), D(285000))
        self.assertEqual(v.price_for("yearly"), D(1014000))                          # 1,200,000 × .845

    def test_invalid_discounts_and_prices_are_rejected_server_side_and_nothing_is_saved(self):
        seeded = PlanVersion.objects.count()
        for bad in ({"discount_quarterly": "-1"}, {"discount_semiannual": "100"}, {"discount_yearly": "250"},
                    {"discount_yearly": "5.555"}, {"discount_quarterly": "abc"}, {"discount_yearly": "NaN"},
                    {"monthly_price": "0"}, {"monthly_price": "-5"}, {"monthly_price": "100.5"}, {"monthly_price": ""}, {"monthly_price": "abc"}):
            with self.subTest(bad=bad):
                response, plan = self.create_plan(**bad)
                self.assertEqual(response.status_code, 200)                         # the form is shown again, with the errors
                self.assertIsNone(plan)
                self.assertEqual(PlanVersion.objects.count(), seeded)

    def test_an_edit_with_invalid_input_keeps_the_previous_draft_untouched(self):
        _r, plan = self.create_plan()
        before = self.prices(plan.versions.get())
        response = self.admin.post(f"/plans/{plan.pk}/edit/", self.form(code="px-plan", discount_yearly="100"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.prices(plan.versions.get()), before)
        self.assertContains(response, "کمتر از ۱۰۰")

    def test_amounts_submitted_by_the_browser_are_ignored(self):
        _r, plan = self.create_plan(price_yearly="1", compare_yearly="1", price_quarterly="1", display_price="1")
        v = plan.versions.get()
        self.assertEqual((v.price_for("yearly"), v.price_for("quarterly"), v.display_price), (D(1020000), D(285000), D(100000)))

    def test_changing_the_monthly_price_recomputes_every_period_on_the_draft_in_place(self):
        _r, plan = self.create_plan()
        draft = plan.versions.get()
        self.admin.post(f"/plans/{plan.pk}/edit/", self.form(code="px-plan", monthly_price="200000"))
        self.assertEqual(plan.versions.count(), 1)                                   # in place, no extra draft
        draft.refresh_from_db()
        self.assertEqual((draft.price_for("monthly"), draft.price_for("quarterly"), draft.price_for("yearly")), (D(200000), D(570000), D(2040000)))
        self.assertEqual(draft.prices.get(billing_interval="yearly").discount_percent, D("15.00"))

    def test_service_level_monthly_change_keeps_formula_rows_consistent(self):
        _r, plan = self.create_plan()
        draft = plan.versions.get()
        draft = ps.update_draft_version(draft, display_price=300000)
        self.assertEqual(draft.price_for("semiannual"), D(1620000))                  # 1,800,000 × .90
        self.assertEqual(ps.validate_for_publication(draft), [])

    def test_an_unoffered_period_has_no_row_and_is_not_sellable(self):
        _r, plan = self.create_plan(offer_semiannual=None)
        v = plan.versions.get()
        self.assertFalse(v.offers_interval("semiannual"))
        self.assertTrue(v.offers_interval("yearly"))
        with self.assertRaises(KeyError):
            v.price_for("semiannual")

    def test_free_plan_kind_has_no_period_prices_and_a_100_percent_discount_is_never_the_way_to_make_a_plan_free(self):
        _r, plan = self.create_plan(code="px-free", plan_kind="free", monthly_price="", trial_days="14")
        v = plan.versions.get()
        self.assertEqual((v.billing_interval, v.display_price, v.trial_days, v.prices.count()), ("none", D(0), 14, 0))
        self.assertEqual(v.price_options(), {})
        response, paid = self.create_plan(code="px-nofree", discount_yearly="100")
        self.assertIsNone(paid)

    def test_pricing_changes_are_audited_with_before_and_after_and_no_browser_amounts(self):
        _r, plan = self.create_plan()
        self.admin.post(f"/plans/{plan.pk}/edit/", self.form(code="px-plan", discount_yearly="20"))
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.plan_pricing_saved").order_by("-pk").first()
        self.assertIsNotNone(entry)
        self.assertIn("yearly", entry.before_summary + entry.after_summary)

    def test_a_server_side_edit_of_a_published_version_is_refused(self):
        _r, plan = self.create_plan()
        v = plan.versions.get()
        self.publish(plan, v)
        v.refresh_from_db()
        self.assertEqual(v.status, "published")
        with self.assertRaises(ps.PlanServiceError):
            ps.set_formula_pricing(v, monthly_price=1, discounts={})
        with self.assertRaises(ps.PlanServiceError):
            ps.update_draft_version(v, display_price=1)


class PublishAndVersioningTests(PricingBase):
    def test_publishing_freezes_the_amounts_and_editing_creates_a_new_draft_without_touching_the_published_version(self):
        _r, plan = self.create_plan()
        v1 = plan.versions.get()
        self.publish(plan, v1)
        v1.refresh_from_db()
        frozen = self.prices(v1)
        self.admin.post(f"/plans/{plan.pk}/edit/", self.form(code="px-plan", monthly_price="150000", discount_yearly="25"))
        self.assertEqual(plan.versions.count(), 2)
        v1.refresh_from_db()
        self.assertEqual((v1.status, self.prices(v1)), ("published", frozen))        # historical contract unchanged
        v2 = plan.versions.get(version_number=2)
        self.assertEqual((v2.status, v2.price_for("yearly")), ("draft", D(1350000)))  # 1,800,000 × .75
        self.publish(plan, v2)
        v2.refresh_from_db()
        self.assertEqual(v2.status, "published")

    def test_an_inconsistent_stored_formula_row_blocks_publication_and_is_never_charged(self):
        _r, plan = self.create_plan()
        v = plan.versions.get()
        PlanVersionPrice.objects.filter(plan_version=v, billing_interval="yearly").update(price=D(1))        # tampered row
        v = PlanVersion.objects.get(pk=v.pk)
        self.assertTrue(ps.validate_for_publication(v))
        self.publish(plan, v)
        v.refresh_from_db()
        self.assertEqual(v.status, "draft")
        with self.assertRaises(pp.PricingError):
            v.price_for("yearly")


class LegacyPreservationTests(PricingBase):
    """Existing plans keep their commercial value: published versions never change, absolute prices convert only by explicit choice."""

    def setUp(self):
        super().setUp()
        # legacy: monthly 290,000; quarterly absolute 780,000 (not an exact %); yearly absolute 2,900,000 (not exact); semiannual exact 10 %
        self.plan, self.v1 = make_plan("legacy-px", base=290000, extra={"quarterly": (780000, 870000, ""), "semiannual": 1566000, "yearly": (2900000, 3480000, "۲ ماه رایگان")})
        self.before = self.prices(self.v1)

    def edit_url(self):
        return f"/plans/{self.plan.pk}/edit/"

    def test_the_edit_form_shows_the_owner_review_and_prefills_only_exact_conversions(self):
        html = self.admin.get(self.edit_url()).content.decode()
        self.assertIn('data-testid="legacy-pricing-review"', html)
        for interval in ("quarterly", "semiannual", "yearly"):
            self.assertIn(f'data-testid="legacy-{interval}"', html)
        self.assertIn('name="ack_quarterly"', html)                                  # not exactly representable ⇒ explicit acknowledgement
        self.assertIn('name="ack_yearly"', html)
        self.assertNotIn('name="ack_semiannual"', html)                              # 1,566,000 = exactly 10 % off 1,740,000
        self.assertRegex(html, r'name="discount_semiannual"[^>]*value="10"')

    def test_keeping_the_legacy_prices_preserves_the_exact_absolute_amounts_on_the_new_draft(self):
        post = self.form(code="legacy-px", monthly_price="290000", keep_legacy_quarterly="on", keep_legacy_semiannual="on", keep_legacy_yearly="on")
        self.admin.post(self.edit_url(), post)
        v2 = self.plan.versions.get(version_number=2)
        self.assertEqual({k: v for k, v in self.prices(v2).items()}, {
            "monthly": (D(290000), None), "quarterly": (D(780000), None), "semiannual": (D(1566000), None), "yearly": (D(2900000), None)})
        self.assertEqual(v2.prices.get(billing_interval="yearly").label, "۲ ماه رایگان")      # custom label preserved
        self.v1.refresh_from_db()
        self.assertEqual((self.v1.status, self.prices(self.v1)), ("published", self.before))

    def test_converting_a_non_exact_price_without_acknowledgement_is_refused_and_changes_nothing(self):
        post = self.form(code="legacy-px", monthly_price="290000", keep_legacy_quarterly=None, keep_legacy_semiannual="on",
                         keep_legacy_yearly="on", discount_quarterly="10")
        response = self.admin.post(self.edit_url(), post)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.plan.versions.count(), 1)                              # no draft was even created
        self.assertContains(response, "ارزشِ تجاری را عوض می‌کند")

    def test_an_acknowledged_conversion_changes_only_that_period(self):
        post = self.form(code="legacy-px", monthly_price="290000", keep_legacy_quarterly=None, ack_quarterly="on", discount_quarterly="10",
                         keep_legacy_semiannual="on", keep_legacy_yearly="on")
        self.admin.post(self.edit_url(), post)
        v2 = self.plan.versions.get(version_number=2)
        self.assertEqual((v2.price_for("quarterly"), v2.prices.get(billing_interval="quarterly").discount_percent), (D(783000), D("10.00")))
        self.assertEqual((v2.price_for("semiannual"), v2.price_for("yearly")), (D(1566000), D(2900000)))
        self.assertEqual(self.prices(PlanVersion.objects.get(pk=self.v1.pk)), self.before)

    def test_an_exact_conversion_keeps_the_commercial_value_identical(self):
        post = self.form(code="legacy-px", monthly_price="290000", keep_legacy_quarterly="on", keep_legacy_yearly="on",
                         keep_legacy_semiannual=None, discount_semiannual="10")
        self.admin.post(self.edit_url(), post)
        v2 = self.plan.versions.get(version_number=2)
        self.assertEqual(v2.price_for("semiannual"), D(1566000))
        self.assertEqual(v2.prices.get(billing_interval="semiannual").discount_percent, D("10.00"))

    def test_a_legacy_structure_without_a_monthly_base_asks_for_one_and_keeps_old_prices_until_decided(self):
        plan = Plan.objects.create(code="yearly-only", name="Y")
        v = ps.create_plan_version(plan, display_price=2400000, billing_interval="yearly")
        ps.publish_plan_version(v)
        html = self.admin.get(f"/plans/{plan.pk}/edit/").content.decode()
        self.assertIn('data-testid="legacy-pricing-review"', html)
        self.assertEqual(pp.owner_review(PlanVersion.objects.get(pk=v.pk))["monthly"], None)

    def test_historical_invoices_and_subscriber_contracts_are_not_recalculated_by_a_new_version(self):
        store = Store.objects.create(name="قدیمی", slug="px-old", admin_subdomain="px-old", status=Store.Status.ACTIVE)
        sub = sub_svc.activate_subscription(sub_svc.create_subscription(store, self.v1), period_end=timezone.now() + timedelta(days=2))
        invoices = renewal_service.generate_renewals(store=store, lead_days=5)
        invoice = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        amount_before = invoice.grand_total
        self.assertEqual(invoices["created"], 1)
        self.admin.post(self.edit_url(), self.form(code="legacy-px", monthly_price="999999", keep_legacy_quarterly="on", keep_legacy_semiannual="on", keep_legacy_yearly="on"))
        v2 = self.plan.versions.get(version_number=2)
        ps.publish_plan_version(v2)
        invoice.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual((invoice.grand_total, sub.plan_version_id), (amount_before, self.v1.pk))     # grandfathered: still v1's price
        self.assertEqual(amount_before, self.v1.price_for(sub.effective_billing_interval))


class MerchantAndInvoiceConsistencyTests(PricingBase):
    """What the public page and merchant selection show == the invoice == the unified checkout == the gateway amount."""

    def setUp(self):
        super().setUp()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        _r, self.plan = self.create_plan(code="px-pay", name="Px Pay", public_title="Px Pay", monthly_price="100000")
        self.version = self.plan.versions.get()
        self.publish(self.plan, self.version)
        self.version.refresh_from_db()
        trial_plan, trial_version = make_plan("px-trial", base=0, interval="none", trial=14)
        self.store = Store.objects.create(name="فروشگاه قیمت", slug="px-store", admin_subdomain="px-store", status=Store.Status.ACTIVE)
        self.owner = User.objects.create_user(username="09120007001", password="pass-12345-x")
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        sub_svc.start_trial(sub_svc.create_subscription(self.store, trial_version, actor=self.owner), actor=self.owner)
        self.fake = patch_zibal(self)
        ready_platform_zibal(self)
        self.client.force_login(self.owner)

    def quote_table(self):
        return {i: pp.final_amount(self.version, i) for i in ("monthly", "quarterly", "semiannual", "yearly")}

    def test_the_stored_table_equals_the_brief_formula_for_monthly_100000(self):
        self.assertEqual(self.quote_table(), {"monthly": D(100000), "quarterly": D(285000), "semiannual": D(540000), "yearly": D(1020000)})

    def test_the_public_pricing_page_shows_the_exact_final_totals_and_discounts(self):
        html = self.client.get("/plans/", HTTP_HOST=PUBLIC).content.decode()
        for amount in (100000, 285000, 540000, 1020000):
            self.assertIn(fa(amount), html, amount)
        for percent in ("۵٪ تخفیف", "۱۰٪ تخفیف", "۱۵٪ تخفیف"):
            self.assertIn(percent, html, percent)

    def test_the_public_page_renders_formula_and_legacy_plans_side_by_side_with_numeric_percentages(self):
        # Regression: a formula row's percent must be numeric so it can be compared with a legacy row's int percent.
        make_plan("px-legacy", base=290000, interval="monthly", extra={"quarterly": 780000, "yearly": 2900000})
        response = self.client.get("/plans/", HTTP_HOST=PUBLIC)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for amount in (285000, 540000, 1020000, 290000, 780000, 2900000):
            self.assertIn(fa(amount), html, amount)
        from apps.subscriptions.services.pricing_page_service import _period_options

        for p in _period_options(self.version):
            self.assertNotIsInstance(p["discount_percent"], str)
            self.assertNotIsInstance(p["savings_percent"], str)

    def test_the_merchant_portal_plan_list_and_the_dashboard_selector_show_the_same_numbers(self):
        html = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=PUBLIC).content.decode()
        for amount in (100000, 285000, 540000, 1020000):
            self.assertIn(fa(amount), html, amount)
        from apps.subscriptions.services.pricing_page_service import _period_options

        shown = {p["interval"]: p["price"] for p in _period_options(self.version)}
        self.assertEqual(shown, self.quote_table())                                  # the interval switcher reads the same quotes

    def test_each_interval_invoice_equals_the_quote_carries_its_derivation_and_checkout_and_gateway_agree(self):
        for interval, rial in (("quarterly", 2850000), ("semiannual", 5400000), ("yearly", 10200000), ("monthly", 1000000)):
            with self.subTest(interval=interval):
                SubscriptionInvoice.objects.filter(store=self.store, status__in=["open", "payment_pending"]).update(status="void")
                self.fake.calls.clear()
                response = portal_buy_and_pay(self, self.client, self.store, self.owner, self.version, method="zibal", billing_interval=interval)
                self.assertEqual(response.status_code, 302)
                invoice = SubscriptionInvoice.objects.filter(store=self.store).order_by("-pk").first()
                expected = self.quote_table()[interval]
                self.assertEqual((invoice.grand_total, invoice.amount_due), (expected, expected))
                line = invoice.lines.get()
                self.assertEqual(line.unit_amount, expected)
                self.assertEqual(line.metadata["pricing"]["final"], str(expected))
                self.assertEqual(line.metadata["pricing"]["mode"], "base" if interval == "monthly" else "formula")
                self.assertEqual(self.fake.calls_to("request")[0]["amount"], int(expected) * 10)      # TOMAN → RIAL at the gateway boundary only
                page = self.client.get(f"/admin-portal/billing/checkout/subscription/{invoice.pk}/", HTTP_HOST="px-store.rastisi.localhost")
                self.assertContains(page, fa(expected))

    def test_verified_payment_activates_with_the_purchased_interval_and_renewal_uses_the_same_snapshot(self):
        portal_buy_and_pay(self, self.client, self.store, self.owner, self.version, method="zibal", billing_interval="yearly")
        invoice = SubscriptionInvoice.objects.filter(store=self.store).order_by("-pk").first()
        confirmation_service.mark_invoice_paid_manually(invoice)
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.plan_version_id, sub.status, sub.billing_interval), (self.version.pk, "active", "yearly"))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice.pk).amount_paid, D(1020000))
        type(sub).objects.filter(pk=sub.pk).update(current_period_end=timezone.now() + timedelta(days=2))
        renewal_service.generate_renewals(store=self.store, lead_days=5)
        renewal = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        self.assertEqual(renewal.grand_total, D(1020000))
        self.assertEqual(renewal.lines.get().metadata["pricing"]["interval"], "yearly")

    def test_a_later_version_with_new_prices_never_changes_the_subscribers_renewal(self):
        portal_buy_and_pay(self, self.client, self.store, self.owner, self.version, method="zibal", billing_interval="quarterly")
        confirmation_service.mark_invoice_paid_manually(SubscriptionInvoice.objects.filter(store=self.store).order_by("-pk").first())
        self.admin.post(f"/plans/{self.plan.pk}/edit/", self.form(code="px-pay", monthly_price="500000", discount_quarterly="50"))
        self.publish(self.plan, self.plan.versions.get(version_number=2))
        sub = ent.get_current_subscription(self.store)
        type(sub).objects.filter(pk=sub.pk).update(current_period_end=timezone.now() + timedelta(days=2))
        renewal_service.generate_renewals(store=self.store, lead_days=5)
        renewal = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        self.assertEqual((sub.plan_version_id, renewal.grand_total), (self.version.pk, D(285000)))        # v1's grandfathered price

    def test_an_upgrade_preview_and_invoice_use_the_same_period_price_and_preserve_the_interval(self):
        make_plan("px-low", base=50000, order=0)
        low = PlanVersion.objects.get(plan__code="px-low")
        current = ent.get_current_subscription(self.store)
        sub_svc.change_plan_version(current, low)
        sub_svc.activate_subscription(ent.get_current_subscription(self.store), period_end=timezone.now() + timedelta(days=20))
        current = ent.get_current_subscription(self.store)
        preview = pcb.preview(current, self.version, billing_interval="semiannual")
        self.assertEqual((preview["payable_amount"], preview["billing_interval"]), (D(540000), "semiannual"))
        kind, invoice = pcb.start_plan_change(current, self.version, preview_token=preview["token"], billing_interval="semiannual")
        self.assertEqual((kind, invoice.grand_total), ("invoice", D(540000)))
        self.assertEqual(invoice.lines.get().plan_version_snapshot["billing_interval"], "semiannual")


class FreeAndTrialEligibilityTests(PricingBase):
    def test_free_and_trial_plans_stay_free_and_a_paid_plan_never_is(self):
        _r, free = self.create_plan(code="px-free2", plan_kind="free", monthly_price="")
        _r, paid = self.create_plan(code="px-paid2", monthly_price="100000")
        fv, pv = free.versions.get(), paid.versions.get()
        self.assertEqual((fv.price_options(), fv.display_price), ({}, D(0)))
        self.assertTrue(all(pv.price_for(i) > 0 for i in ("monthly", "quarterly", "semiannual", "yearly")))
        self.assertEqual(sorted(pv.price_options()), ["monthly", "quarterly", "semiannual", "yearly"])

    def test_no_discount_value_can_produce_a_zero_period_price(self):
        for value in ("99.99", "99.9", "99"):
            _r, plan = self.create_plan(code=f"px-tiny-{value}", monthly_price="1", discount_quarterly=value, discount_semiannual="0", discount_yearly="0")
            if plan is not None:
                self.assertGreater(plan.versions.get().price_for("quarterly"), 0)

    def test_a_free_plan_version_still_prices_and_snapshots_at_zero_for_its_none_interval(self):
        # Regression: `price_for("none")` / the invoice plan snapshot must keep working for free plans (it used to return display_price).
        _r, free = self.create_plan(code="px-free3", plan_kind="free", monthly_price="")
        version = free.versions.get()
        self.assertEqual(version.billing_interval, "none")
        self.assertEqual(version.price_for(), D(0))
        self.assertEqual(version.price_for("none"), D(0))
        self.assertEqual(pp.invoice_metadata(version, "none")["pricing"]["mode"], "free")
        from apps.billing.services.invoice_service import plan_version_snapshot

        self.assertEqual(plan_version_snapshot(version, "none")["display_price"], "0")
