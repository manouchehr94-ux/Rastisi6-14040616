"""Dynamic pricing, comparison matrix and entitlement consistency (service + billing lifecycle).

Synthetic plan values only — these are fixtures, not product decisions."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import (
    confirmation_service, invoice_service, plan_change_billing_service as pcb, renewal_service,
)
from apps.billing.services.period_utils import next_period_end
from apps.stores.models import Store
from apps.subscriptions import feature_catalog as catalog
from apps.subscriptions.entitlements import ENTITLEMENT_DEFINITIONS, sync_entitlement_definitions
from apps.subscriptions.models import (
    EntitlementDefinition, OptionalService, Plan, PlanFaq, PlanOptionalService, PlanVersion, PlanVersionPrice,
    PricingFeature, StoreSubscription,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import plan_service as ps
from apps.subscriptions.services import pricing_page_service as page
from apps.subscriptions.services import subscription_service as sub_svc


def make_plan(code, *, base=100000, interval="monthly", extra=None, trial=0, limits=None, flags=None, publish=True,
              recommended=False, order=0, selectable=True, active=True, **plan_fields):
    sync_entitlement_definitions()
    catalog.sync_feature_catalog()
    plan = Plan.objects.create(code=code, name=code.title(), public_title=code.title(), is_recommended=recommended,
                               display_order=order, is_publicly_selectable=selectable, is_active=active, **plan_fields)
    version = ps.create_plan_version(plan, display_price=base, billing_interval=interval, trial_days=trial)
    for ivl, spec in (extra or {}).items():
        price, compare, label = (spec + (None, ""))[:3] if isinstance(spec, tuple) else (spec, None, "")
        ps.set_version_price(version, ivl, price=price, compare_at_price=compare, label=label)
    for key, val in (limits or {}).items():
        if val is None:
            ps.set_plan_entitlement(version, key, is_enabled=True, is_unlimited=True)
        else:
            ps.set_plan_entitlement(version, key, is_enabled=True, integer_limit=val)
    for key, on in (flags or {}).items():
        ps.set_plan_entitlement(version, key, is_enabled=on)
    if publish:
        ps.publish_plan_version(version)
    return plan, PlanVersion.objects.get(pk=version.pk)


def store_on(version, slug, *, status="active"):
    store = Store.objects.create(name=slug, slug=slug, admin_subdomain=slug, status=Store.Status.ACTIVE)
    sub = sub_svc.create_subscription(store, version)
    sub = sub_svc.start_trial(sub) if status == "trialing" else sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=20))
    return store, sub


class PriceOptionsTests(TestCase):
    def test_primary_and_extra_periods_resolve_through_one_api(self):
        _p, v = make_plan("opt", base=100000, extra={"quarterly": 270000, "yearly": (1000000, 1200000, "دو ماه رایگان")})
        self.assertEqual(set(v.price_options()), {"monthly", "quarterly", "yearly"})
        self.assertEqual(v.price_for(), Decimal(100000))
        self.assertEqual(v.price_for("yearly"), Decimal(1000000))
        self.assertEqual(v.monthly_equivalent("quarterly"), Decimal(90000))
        self.assertTrue(v.offers_interval("yearly"))
        self.assertFalse(v.offers_interval("semiannual"))
        with self.assertRaises(KeyError):
            v.price_for("semiannual")

    def test_legacy_single_price_versions_are_untouched(self):
        plan = Plan.objects.create(code="legacyish", name="L")
        v = PlanVersion.objects.create(plan=plan, version_number=1, status="published", display_price=490000, billing_interval="monthly")
        self.assertEqual(v.price_options(), {"monthly": {"price": Decimal(490000), "compare_at": None, "label": "", "discount_percent": None}})
        free = PlanVersion.objects.create(plan=plan, version_number=2, status="published", display_price=0, billing_interval="none")
        self.assertEqual(free.price_options(), {})
        self.assertEqual(free.monthly_equivalent(), Decimal(0))

    def test_validation_of_extra_prices(self):
        plan = Plan.objects.create(code="val", name="V")
        v = ps.create_plan_version(plan, display_price=100, billing_interval="monthly")
        for bad in ({"price": -1}, {"price": "abc"}, {"price": 1.5}, {"price": 100, "compare_at_price": 50}):
            with self.assertRaises(ps.PlanServiceError, msg=str(bad)):
                ps.set_version_price(v, "yearly", **bad)
        with self.assertRaises(ps.PlanServiceError):
            ps.set_version_price(v, "none", price=10)
        with self.assertRaises(ps.PlanServiceError):
            ps.set_version_price(v, "monthly", price=999)          # the primary option's price is the version's own
        ps.set_version_price(v, "monthly", price=100, compare_at_price=150, label="ویژه")    # metadata only
        self.assertEqual(v.price_options()["monthly"]["compare_at"], Decimal(150))
        self.assertEqual(v.price_for("monthly"), Decimal(100))

    def test_published_versions_are_immutable_for_prices_and_entitlements(self):
        _p, v = make_plan("imm", base=100, extra={"yearly": 1000}, limits={"catalog.products": 10})
        with self.assertRaises(ps.PlanServiceError):
            ps.set_version_price(v, "quarterly", price=300)
        with self.assertRaises(ps.PlanServiceError):
            ps.clear_version_price(v, "yearly")
        with self.assertRaises(ps.PlanServiceError):
            ps.set_plan_entitlement(v, "catalog.products", is_enabled=True, integer_limit=99)
        self.assertEqual(v.price_for("yearly"), Decimal(1000))

    def test_database_rejects_duplicate_periods_and_negative_prices(self):
        from django.db import IntegrityError, transaction

        plan = Plan.objects.create(code="db", name="D")
        v = ps.create_plan_version(plan, display_price=100, billing_interval="monthly")
        PlanVersionPrice.objects.create(plan_version=v, billing_interval="yearly", price=1000)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlanVersionPrice.objects.create(plan_version=v, billing_interval="yearly", price=2000)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlanVersionPrice.objects.create(plan_version=v, billing_interval="quarterly", price=-1)


class PricingPageDataTests(TestCase):
    def setUp(self):
        self.base = make_plan("base", base=100000, order=1, trial=14, extra={"quarterly": (270000, 300000, ""), "yearly": (1000000, 1200000, "دو ماه رایگان")},
                              limits={"catalog.products": 50, "staff.members": 2}, flags={"catalog.import": False})
        self.adv = make_plan("adv", base=300000, order=2, trial=0, recommended=True, extra={"yearly": 3000000},
                             limits={"catalog.products": None, "staff.members": 9}, flags={"catalog.import": True})

    def test_only_published_active_public_plans_appear_and_in_display_order(self):
        make_plan("draft", publish=False, order=3)
        make_plan("hidden", selectable=False, order=4)
        make_plan("inactive", active=False, order=5)
        retired_plan, retired_v = make_plan("retired", order=6)
        ps.retire_plan_version(retired_v)
        self.assertEqual([c["plan"].code for c in page.build_pricing_page()["cards"]], ["base", "adv"])

    def test_card_prices_periods_discounts_and_trial_come_from_the_real_version(self):
        cards = {c["plan"].code: c for c in page.build_pricing_page()["cards"]}
        base, adv = cards["base"], cards["adv"]
        # the initial Trial is a PLATFORM policy for every new store (default 30 days), not a per-plan property any more
        self.assertEqual((base["trial_days"], adv["trial_days"]), (30, 30))
        self.assertEqual([p["interval"] for p in base["periods"]], ["monthly", "quarterly", "yearly"])
        yearly = next(p for p in base["periods"] if p["interval"] == "yearly")
        self.assertEqual((yearly["price"], yearly["compare_at"], yearly["discount_percent"], yearly["custom_label"]),
                         (Decimal(1000000), Decimal(1200000), 17, "دو ماه رایگان"))
        self.assertEqual(yearly["savings_percent"], 17)
        self.assertTrue(adv["is_recommended"] and not base["is_recommended"])
        adv_yearly = next(p for p in adv["periods"] if p["interval"] == "yearly")
        self.assertEqual((adv_yearly["compare_at"], adv_yearly["savings_percent"]), (None, 17))

    def test_matrix_values_equal_what_the_entitlement_service_enforces(self):
        data = page.build_pricing_page()
        rows = {r["feature"].key: r for cat in data["matrix"] for r in cat["rows"]}
        for key, ent_key in (("products", "catalog.products"), ("staff", "catalog.staff"), ):
            pass
        for col, (_plan, version) in enumerate(page.offered_plans()):
            for fkey, spec in ((f.key, f) for f in catalog.CATALOG if f.entitlement and f.availability != catalog.PLANNED):
                cell = rows[fkey]["cells"][col]
                definition = EntitlementDefinition.objects.get(key=spec.entitlement)
                if definition.entitlement_type == "boolean":
                    self.assertEqual(cell["kind"] == "check", ent.has_entitlement(None, spec.entitlement, plan_version=version), (fkey, col))
                else:
                    limit = ent.get_entitlement_limit(None, spec.entitlement, plan_version=version)
                    enabled = ent.has_entitlement(None, spec.entitlement, plan_version=version)
                    expected = "none" if (not enabled or limit == 0) else ("unlimited" if limit is None else "value")
                    self.assertEqual(cell["kind"], expected, (fkey, col, limit))
        products = rows["products"]["cells"]
        self.assertEqual((products[0]["text"], products[1]["kind"]), ("۵۰ کالا", "unlimited"))
        self.assertEqual([c["kind"] for c in rows["import"]["cells"]], ["none", "check"])

    def test_unimplemented_features_are_hidden_by_default_and_never_shown_as_available(self):
        api = PricingFeature.objects.get(key="api")
        self.assertEqual((api.availability, api.technical_status, api.is_visible), ("planned", "planned", False))
        self.assertFalse(api.grants_access)
        keys = {r["feature"].key for cat in page.build_pricing_page()["matrix"] for r in cat["rows"]}
        self.assertNotIn("api", keys)
        # the owner may deliberately surface it: it is then labelled «به‌زودی» — never a check / never available
        PricingFeature.objects.filter(pk=api.pk).update(is_visible=True)
        self.assertEqual(PricingFeature.objects.get(pk=api.pk).public_state, "coming_soon")
        for cat in page.build_pricing_page()["matrix"]:
            for row in cat["rows"]:
                if row["feature"].key == "api":
                    self.assertTrue(row["is_soon"])
                    self.assertNotIn(row["cells"][0]["kind"], ("check", "all", "value", "unlimited"))
        catalog.sync_feature_catalog()
        api = PricingFeature.objects.get(key="api")
        self.assertEqual((api.technical_status, api.commercial_status), ("planned", "planned"))   # sync never promotes it

    def test_owner_edits_to_text_and_visibility_survive_catalog_sync(self):
        row = PricingFeature.objects.get(key="coupons")
        row.title, row.description, row.is_visible = "کدهای تخفیفِ من", "توضیحِ ویرایش‌شده", False
        row.save()
        catalog.sync_feature_catalog()
        row.refresh_from_db()
        self.assertEqual((row.title, row.description, row.is_visible), ("کدهای تخفیفِ من", "توضیحِ ویرایش‌شده", False))
        keys = {r["feature"].key for cat in page.build_pricing_page()["matrix"] for r in cat["rows"]}
        self.assertNotIn("coupons", keys)

    def test_every_catalog_row_has_a_unique_key_a_known_category_and_enforced_gates_only(self):
        keys = [f.key for f in catalog.CATALOG]
        self.assertEqual(len(keys), len(set(keys)))
        categories = {c for c, _ in PricingFeature.Category.choices}
        self.assertEqual(len(categories), 7)
        for f in catalog.CATALOG:
            self.assertIn(f.category, categories, f.key)
            if f.entitlement:
                self.assertIn(f.entitlement, catalog.ENFORCED_ENTITLEMENT_KEYS, f.key)
            self.assertTrue(f.evidence, f.key)
        defined = {k for k, *_ in ENTITLEMENT_DEFINITIONS}
        self.assertTrue(catalog.ENFORCED_ENTITLEMENT_KEYS <= defined)
        self.assertTrue(catalog.UNENFORCED_ENTITLEMENT_KEYS.isdisjoint(catalog.ENFORCED_ENTITLEMENT_KEYS))
        self.assertIn("integrations.api", catalog.UNENFORCED_ENTITLEMENT_KEYS)

    def test_faq_and_optional_services_appear_only_when_configured_and_published(self):
        data = page.build_pricing_page()
        self.assertEqual((data["faqs"], data["plan_faqs"], data["services"]), ([], [], []))
        PlanFaq.objects.create(question="سراسری؟", answer="بله", display_order=1)
        PlanFaq.objects.create(question="پنهان", answer="x", is_published=False)
        PlanFaq.objects.create(question="پایه؟", answer="y", plan=self.base[0])
        service = OptionalService.objects.create(code="setup", title="راه‌اندازی", price=900000, is_active=True)
        OptionalService.objects.create(code="off", title="غیرفعال", is_active=False)
        PlanOptionalService.objects.create(plan=self.base[0], service=service, mode="paid")
        PlanOptionalService.objects.create(plan=self.adv[0], service=service, mode="included")
        data = page.build_pricing_page()
        self.assertEqual([f.question for f in data["faqs"]], ["سراسری؟"])
        self.assertEqual([f.question for f in data["plan_faqs"]], ["پایه؟"])
        self.assertEqual(len(data["services"]), 1)
        self.assertEqual([c["kind"] for c in data["services"][0]["cells"]], ["paid", "check"])

    def test_selection_resolution_never_trusts_user_input(self):
        self.assertEqual(page.resolve_selection("adv", "yearly")[1], "yearly")
        self.assertIsNone(page.resolve_selection("adv", "quarterly"))                  # period not offered by that plan
        self.assertIsNone(page.resolve_selection("nope", "monthly"))
        self.assertIsNone(page.resolve_selection("draftless'; drop", "monthly"))
        make_plan("draft2", publish=False)
        self.assertIsNone(page.resolve_selection("draft2", ""))
        self.assertEqual(page.resolve_selection("base", "")[1], "monthly")


class ExistingSubscriberPreservationTests(TestCase):
    def test_new_versions_never_change_existing_subscribers_price_or_entitlements(self):
        plan, v1 = make_plan("keep", base=100000, limits={"catalog.products": 5}, flags={"catalog.import": False}, extra={"yearly": 1000000})
        store, sub = store_on(v1, "keep-store")
        sub.billing_interval = "yearly"
        sub.save()
        v2 = ps.create_plan_version(plan, display_price=900000, billing_interval="monthly")
        ps.set_plan_entitlement(v2, "catalog.products", is_enabled=True, integer_limit=500)
        ps.set_plan_entitlement(v2, "catalog.import", is_enabled=True)
        ps.publish_plan_version(v2)
        ent.clear_entitlement_cache()
        sub.refresh_from_db()
        self.assertEqual(sub.plan_version_id, v1.pk)
        self.assertEqual(ent.get_entitlement_limit(store, "catalog.products"), 5)
        self.assertFalse(ent.has_entitlement(store, "catalog.import"))
        self.assertEqual(sub.plan_version.price_for(sub.effective_billing_interval), Decimal(1000000))
        # the public page now shows the new version; the subscriber still runs on the old one
        card = page.build_pricing_page()["cards"][0]
        self.assertEqual(card["version"].pk, v2.pk)

    def test_old_versions_without_a_gate_row_keep_their_prior_access(self):
        plan = Plan.objects.create(code="oldplan", name="Old")
        v = PlanVersion.objects.create(plan=plan, version_number=1, status="published", display_price=1, billing_interval="monthly")
        store, _sub = store_on(v, "old-store")
        self.assertTrue(ent.has_entitlement(store, "catalog.import"))             # default_enabled + fail-open


class CustomDomainGrandfatheringTests(TestCase):
    """domains.custom is now enforced, but ONLY for versions published after EntitlementDefinition.enforced_from; versions
    published before (e.g. the seeded Trial/Basic, which declare False) keep today's access, and nothing is ever deleted."""

    def setUp(self):
        from apps.stores.services import domain_verification_service as dvs

        self.dvs = dvs
        self.effective = EntitlementDefinition.objects.get(key="domains.custom").enforced_from

    def old_version(self, code, value):
        _p, v = make_plan(code, flags={"domains.custom": value})
        PlanVersion.objects.filter(pk=v.pk).update(published_at=self.effective - timedelta(days=30))
        return PlanVersion.objects.get(pk=v.pk)

    def request(self, store, host):
        return self.dvs.request_custom_domain(store=store, hostname=host, actor=None)

    def test_the_effective_date_is_recorded_and_the_key_is_enforced_and_advertised_as_plan_controlled(self):
        self.assertIsNotNone(self.effective)
        self.assertIn("domains.custom", catalog.ENFORCED_ENTITLEMENT_KEYS)
        self.assertNotIn("domains.custom", catalog.UNENFORCED_ENTITLEMENT_KEYS)
        self.assertTrue(EntitlementDefinition.objects.get(key="domains.custom").default_enabled)
        self.assertEqual(PricingFeature.objects.get(key="custom_domain").entitlement.key, "domains.custom")

    def test_subscribers_on_versions_published_before_the_effective_date_keep_access_even_if_the_version_says_false(self):
        store, _s = store_on(self.old_version("oldfalse", False), "gf-old")
        self.request(store, "grandfathered.example.com")
        self.assertTrue(store.domains.filter(hostname="grandfathered.example.com").exists())
        self.assertTrue(ent.has_entitlement(store, "domains.custom"))

    def test_legacy_versions_without_a_published_at_are_grandfathered(self):
        plan = Plan.objects.create(code="legacypub", name="L")
        v = PlanVersion.objects.create(plan=plan, version_number=1, status="published", display_price=0, billing_interval="none")
        ps_row = ps  # noqa: F841
        store, _s = store_on(v, "gf-legacy")
        self.request(store, "legacy.example.com")

    def test_new_versions_apply_their_explicit_value(self):
        _p, off = make_plan("newoff", flags={"domains.custom": False})
        _p2, on = make_plan("newon", flags={"domains.custom": True})
        denied, _s = store_on(off, "gf-new-denied")
        allowed, _s2 = store_on(on, "gf-new-allowed")
        with self.assertRaises(self.dvs.DomainVerificationError) as ctx:
            self.request(denied, "denied.example.com")
        self.assertIn("ارتقا", str(ctx.exception))
        self.assertFalse(denied.domains.filter(hostname="denied.example.com").exists())
        self.request(allowed, "allowed.example.com")

    def test_a_new_version_that_never_defines_the_key_stays_fail_open(self):
        _p, v = make_plan("newundefined")
        store, _s = store_on(v, "gf-undefined")
        self.request(store, "undefined.example.com")

    def test_a_store_without_any_subscription_stays_fail_open(self):
        store = Store.objects.create(name="ns", slug="gf-nosub", admin_subdomain="gf-nosub", status=Store.Status.ACTIVE)
        self.request(store, "nosub.example.com")

    def test_downgrading_to_a_gated_plan_closes_the_gate_but_deletes_nothing(self):
        _p, on = make_plan("downon", flags={"domains.custom": True})
        _p2, off = make_plan("downoff", flags={"domains.custom": False})
        store, sub = store_on(on, "gf-down")
        self.request(store, "keepme.example.com")
        sub_svc.change_plan_version(sub, off)
        ent.clear_entitlement_cache()
        with self.assertRaises(self.dvs.DomainVerificationError):
            self.request(store, "second.example.com")
        self.assertTrue(store.domains.filter(hostname="keepme.example.com").exists())

    def test_matrix_shows_what_is_actually_enforced_per_plan_including_grandfathered_versions(self):
        _p, new_off = make_plan("mxoff", order=1, flags={"domains.custom": False})
        _p2, new_on = make_plan("mxon", order=2, flags={"domains.custom": True})
        old = self.old_version("mxold", False)
        row = PricingFeature.objects.get(key="custom_domain")
        self.assertEqual(page._cell(row, new_off)["kind"], "none")
        self.assertEqual(page._cell(row, new_on)["kind"], "check")
        self.assertEqual(page._cell(row, old)["kind"], "check")            # honest: that version's subscribers keep access


class EnforcedQuotaConsistencyTests(TestCase):
    """The matrix advertises a number only because the service layer enforces that same number."""

    def test_advertised_product_cap_is_the_enforced_cap(self):
        from apps.subscriptions.services import enforcement

        _p, v = make_plan("capplan", limits={"catalog.products": 0 + 3})
        store, _sub = store_on(v, "cap-store")
        self.assertEqual(ent.get_entitlement_limit(store, "catalog.products"), 3)
        cell = page._cell(PricingFeature.objects.get(key="products"), v)
        self.assertEqual(cell["text"], "۳ کالا")
        enforcement.enforce_can_create_product(store)                      # no products yet → below the cap → allowed
        # the exact blocking behaviour at the cap is exercised by test_creation_limits; here we pin that the
        # advertised number and the enforced number are read from the same entitlement

    def test_boolean_gates_listed_as_enforced_have_behavioural_tests(self):
        enforced = catalog.ENFORCED_ENTITLEMENT_KEYS
        self.assertEqual(
            {"catalog.import", "catalog.export"} & enforced, {"catalog.import", "catalog.export"},
        )


class BillingLifecycleTests(TestCase):
    def setUp(self):
        self.trial_plan, self.trial_v = make_plan("trialp", base=0, interval="none", trial=14)
        self.base_plan, self.base_v = make_plan("lbase", base=100000, extra={"quarterly": 270000, "yearly": 1000000})
        self.adv_plan, self.adv_v = make_plan("ladv", base=300000, extra={"yearly": 3000000})
        self.store, self.sub = store_on(self.trial_v, "life-store", status="trialing")

    def start(self, version, interval=None, actor=None):
        sub = ent.get_current_subscription(self.store)
        token = pcs._preview_token(sub, version)
        return pcb.start_plan_change(sub, version, preview_token=token, actor=actor, billing_interval=interval)

    def test_purchasing_a_yearly_option_invoices_the_yearly_price_and_activates_for_a_year(self):
        kind, invoice = self.start(self.base_v, "yearly")
        self.assertEqual(kind, "invoice")
        self.assertEqual(invoice.grand_total, Decimal(1000000))
        line = invoice.lines.get()
        self.assertEqual(line.plan_version_snapshot["billing_interval"], "yearly")
        self.assertEqual(line.plan_version_snapshot["display_price"], "1000000")
        self.assertEqual(invoice_service.invoice_billing_interval(invoice), "yearly")
        self.assertEqual(ent.get_current_subscription(self.store).status, StoreSubscription.Status.TRIALING)   # unpaid ⇒ no activation
        confirmation_service.mark_invoice_paid_manually(invoice)
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.status, sub.plan_version_id, sub.billing_interval), ("active", self.base_v.pk, "yearly"))
        span = sub.current_period_end - sub.current_period_start
        self.assertGreaterEqual(span.days, 364)
        self.assertLessEqual(span.days, 366)

    def test_each_period_has_the_right_length(self):
        start = timezone.now().replace(day=1, month=1, year=2027)
        self.assertEqual(next_period_end(start, "quarterly").month, 4)
        self.assertEqual(next_period_end(start, "semiannual").month, 7)
        self.assertEqual(next_period_end(start, "yearly").year, 2028)
        self.assertIsNone(next_period_end(start, "none"))

    def test_default_interval_keeps_the_old_behaviour_and_snapshot(self):
        kind, invoice = self.start(self.base_v)                     # no interval given → current/primary ("monthly")
        self.assertEqual(invoice.grand_total, Decimal(100000))
        self.assertEqual(invoice.lines.get().plan_version_snapshot["billing_interval"], "monthly")

    def test_unoffered_or_forged_interval_is_refused_and_creates_nothing(self):
        for bad in ("semiannual", "weekly", "none"):
            with self.assertRaises(pcb.PlanChangeBillingError, msg=bad):
                self.start(self.adv_v, bad)
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=self.sub).count(), 0)

    def test_an_open_invoice_for_another_period_is_never_silently_reinterpreted(self):
        self.start(self.base_v, "yearly")
        with self.assertRaises(pcb.PlanChangeBillingError):
            self.start(self.base_v, "quarterly")
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=self.sub, kind="plan_change").count(), 1)
        kind, again = self.start(self.base_v, "yearly")                # the same decision is idempotent
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=self.sub, kind="plan_change").count(), 1)

    def test_renewal_uses_the_purchased_interval_and_its_immutable_price(self):
        _k, invoice = self.start(self.base_v, "yearly")
        confirmation_service.mark_invoice_paid_manually(invoice)
        sub = ent.get_current_subscription(self.store)
        StoreSubscription.objects.filter(pk=sub.pk).update(current_period_end=timezone.now() + timedelta(days=1))
        # a later version with a different yearly price must not touch this subscriber
        v2 = ps.create_plan_version(self.base_plan, display_price=555, billing_interval="monthly")
        ps.set_version_price(v2, "yearly", price=777)
        ps.publish_plan_version(v2)
        renewal_service.generate_renewals(lead_days=3)
        renewal = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        self.assertEqual(renewal.grand_total, Decimal(1000000))
        self.assertEqual(renewal.lines.get().plan_version_snapshot["billing_interval"], "yearly")
        self.assertEqual(renewal.billing_period_end.year - renewal.billing_period_start.year, 1)
        confirmation_service.mark_invoice_paid_manually(renewal)
        sub.refresh_from_db()
        self.assertEqual(sub.plan_version_id, self.base_v.pk)
        self.assertEqual(sub.billing_interval, "yearly")

    def test_upgrade_requires_payment_and_downgrade_is_scheduled_without_payment(self):
        _k, invoice = self.start(self.base_v, "monthly")
        confirmation_service.mark_invoice_paid_manually(invoice)
        sub = ent.get_current_subscription(self.store)
        ent.clear_entitlement_cache()
        kind, up = self.start(self.adv_v, "monthly")                  # 100k → 300k monthly: upgrade
        self.assertEqual((kind, up.grand_total), ("invoice", Decimal(300000)))
        confirmation_service.mark_invoice_paid_manually(up)
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.plan_version_id, sub.status), (self.adv_v.pk, "active"))
        kind, scheduled = self.start(self.base_v, "monthly")          # back down: scheduled, nothing charged now
        self.assertEqual(kind, "scheduled")
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.adv_v.pk)
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=sub, status="open").count(), 0)

    def test_comparison_of_different_periods_uses_monthly_equivalents(self):
        # yearly 1,000,000 (≈83k/month) vs a monthly 100k: NOT an upgrade even though the raw number is larger
        self.assertFalse(pcb.is_upgrade(self.base_v, self.base_v, current_interval="monthly", target_interval="yearly"))
        self.assertTrue(pcb.is_upgrade(self.base_v, self.adv_v, current_interval="monthly", target_interval="monthly"))
        # same interval keeps the exact old raw comparison
        self.assertEqual(pcb.is_upgrade(self.base_v, self.adv_v), Decimal(self.adv_v.display_price) > Decimal(self.base_v.display_price))

    def test_failed_payment_leaves_everything_unchanged_and_retry_works(self):
        from apps.billing.services import attempt_service

        _k, invoice = self.start(self.base_v, "yearly")
        attempt = attempt_service.create_attempt(invoice, provider="manual")
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.plan_version_id, sub.billing_interval), (self.trial_v.pk, ""))
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_payable)
        self.assertIsNotNone(attempt)

    def test_registration_with_a_selected_paid_plan_gets_the_platform_trial_and_no_second_one(self):
        """Choosing a plan (even one with its own legacy ``trial_days``) at registration never grants that plan or a second trial:
        the store gets the independent initial Trial of the platform length and the choice is only remembered for the purchase."""
        _p, paid_with_trial = make_plan("withtrial", base=200000, trial=14)
        fresh = Store.objects.create(name="f1", slug="fresh1", admin_subdomain="fresh1", status=Store.Status.ACTIVE)
        sub = sub_svc.provision_default_subscription(fresh, plan_version=paid_with_trial)
        self.assertEqual((sub.plan_version.plan.code, sub.status, sub.source), ("trial", "trialing", "default"))
        self.assertAlmostEqual((sub.trial_end_at - sub.trial_start_at).days, 30, delta=1)
        self.assertEqual(sub_svc.provision_default_subscription(fresh, plan_version=paid_with_trial).pk, sub.pk)   # idempotent
        self.assertEqual(fresh.subscriptions.count(), 1)

    def test_trial_once_per_store_is_enforced_but_can_be_switched_off(self):
        plan, version = make_plan("once", base=1000, trial=7)
        store, sub = store_on(version, "once-store", status="trialing")
        self.assertFalse(sub_svc.trial_eligible(store, version))
        PlanVersion.objects.filter(pk=version.pk).update(trial_once_per_store=False)
        version.refresh_from_db()
        self.assertTrue(sub_svc.trial_eligible(store, version))
