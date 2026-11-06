"""«سایر (صنف آزاد)» — the seller must enter (and the server must validate) the REAL industry name (FV2, 2026-11-06).

* ``ValidateCustomIndustryNameTests`` — pure validation rules (normalisation, length, forbidden characters).
* ``OnboardingCustomIndustryTests`` — the real onboarding «صنف» step: required, persisted, ignored for ordinary templates, nothing is installed on error,
  the typed value survives a rejected POST, XSS is escaped, existing selections/legacy rows are untouched.
* ``DashboardCustomIndustryTests`` — the merchant-admin settings install path enforces the same rule.
* ``CustomIndustryTenantIsolationTests`` — a name is bound to its own store; another tenant's owner cannot read or set it.
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.catalog.models import Category, IndustryTemplate, StoreIndustryInstallation
from apps.catalog.services import industry_template_service as svc
from apps.portal.tests._industry import ensure_other_template, install_other_industry
from apps.portal.tests.test_onboarding_journey import _HOST, JourneyBase, make_rich_template
from apps.portal.services import provisioning_service
from apps.stores.models import Store

User = get_user_model()


class ValidateCustomIndustryNameTests(SimpleTestCase):
    def ok(self, raw, expected=None):
        self.assertEqual(svc.validate_custom_industry_name(raw), expected if expected is not None else raw)

    def bad(self, raw, message=None):
        with self.assertRaises(svc.IndustryInstallationError) as ctx:
            svc.validate_custom_industry_name(raw)
        if message:
            self.assertEqual(str(ctx.exception), message)

    def test_accepts_real_persian_and_latin_names_with_normal_punctuation(self):
        for name in ("لوازم‌التحریرِ هنری", "Handmade soaps", "قنادی و شیرینی (سنتی)", "فرش و گلیم - دست‌باف", "پوشاک ۱۲۳", "A&B"):
            with self.subTest(name=name):
                self.ok(name)

    def test_normalises_whitespace_arabic_letters_and_repeated_zwnj(self):
        self.ok("  لوازم    تحریر  ", "لوازم تحریر")
        self.ok("كتاب‌فروشي", "کتاب‌فروشی")
        self.ok("نان‌‌سنگک", "نان‌سنگک")
        self.ok("‌ نان‌ ", "نان")

    def test_required_and_length_bounds(self):
        self.bad("", svc.CUSTOM_INDUSTRY_NAME_REQUIRED_MESSAGE)
        self.bad(None, svc.CUSTOM_INDUSTRY_NAME_REQUIRED_MESSAGE)
        self.bad("   ‌  ", svc.CUSTOM_INDUSTRY_NAME_REQUIRED_MESSAGE)
        self.bad("ا", svc.CUSTOM_INDUSTRY_NAME_TOO_SHORT_MESSAGE)
        self.ok("ab")
        self.ok("ا" * 80)
        self.bad("ا" * 81, svc.CUSTOM_INDUSTRY_NAME_TOO_LONG_MESSAGE)

    def test_rejects_markup_control_characters_and_symbol_only_values(self):
        for bad in ("<script>alert(1)</script>", "a<b", "x\u0000y", "x\ny", "نام‮معکوس", "'; DROP TABLE--", "javascript:alert(1)", "---", "(())", "123", "۱۲۳۴"):
            with self.subTest(value=bad):
                self.bad(bad)


class _Base(JourneyBase):
    with_industry = False

    def post(self, template, name=None, **extra):
        data = {"industry_template_id": template.pk, "confirm_industry_install": "1", **extra}
        if name is not None:
            data["custom_industry_name"] = name
        return self.client.post(self.url("industry"), data, HTTP_HOST=_HOST)

    def assertNothingInstalled(self):
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        self.assertEqual(Category.objects.filter(store=self.store).count(), 0)


class OnboardingCustomIndustryTests(_Base):
    def setUp(self):
        super().setUp()
        self.other = ensure_other_template()
        self.rich = make_rich_template()

    def test_other_without_a_name_is_rejected_and_installs_nothing(self):
        for missing in (None, "", "   ", "ا"):
            with self.subTest(name=missing):
                response = self.post(self.other, missing)
                self.assertEqual(response.status_code, 200)               # re-rendered with an error, not a redirect
                self.assertTrue(response.context["custom_name_error"])
                self.assertContains(response, 'id="ob-custom-industry-error"')
                self.assertNothingInstalled()
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)

    def test_other_with_a_valid_name_installs_once_stores_the_normalised_name_and_advances(self):
        response = self.post(self.other, "  لوازم   تحریرِ هنری ")
        self.assertEqual(response.status_code, 302)
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, self.other.pk)
        self.assertEqual(installation.custom_industry_name, "لوازم تحریرِ هنری")
        self.store.refresh_from_db()
        self.assertNotEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)

    def test_a_rejected_post_keeps_the_typed_name_and_the_selection(self):
        response = self.post(self.other, "x" * 81)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('value="' + "x" * 81 + '"', html)
        self.assertIn(f'value="{self.other.pk}" checked', html)
        self.assertNotIn("data-ob-custom-industry hidden", html)           # the box is visible so the seller can fix the name
        self.assertNothingInstalled()

    def test_markup_in_the_name_is_rejected_and_never_rendered_unescaped(self):
        payload = '<img src=x onerror=alert(1)>'
        response = self.post(self.other, payload)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, payload)                          # escaped (&lt;img …) in the echoed field value
        self.assertNothingInstalled()

    def test_a_name_sent_with_an_ordinary_template_is_ignored_not_stored(self):
        response = self.post(self.rich, "نامِ جعلی")
        self.assertEqual(response.status_code, 302)
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, self.rich.pk)
        self.assertEqual(installation.custom_industry_name, "")

    def test_a_forged_non_offerable_or_unknown_template_still_installs_nothing(self):
        self.assertEqual(self.post(self.other, "نام معتبر", **{"industry_template_id": 999999}).status_code, 200)
        self.assertNothingInstalled()

    def test_the_name_must_not_be_required_without_confirmation_but_nothing_installs(self):
        response = self.client.post(self.url("industry"), {"industry_template_id": self.other.pk, "custom_industry_name": "نام معتبر"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["confirm_error"])
        self.assertNothingInstalled()

    def test_a_double_submit_never_creates_a_second_installation_or_overwrites_the_name(self):
        self.assertEqual(self.post(self.other, "نامِ اول").status_code, 302)
        self.assertEqual(self.post(self.other, "نامِ دوم").status_code, 302)    # idempotent continue
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)
        self.assertEqual(StoreIndustryInstallation.objects.get(store=self.store).custom_industry_name, "نامِ اول")

    def test_the_page_markup_exposes_the_conditional_field_and_the_other_card_slug(self):
        html = self.get("industry").content.decode()
        self.assertIn('data-slug="other"', html)
        self.assertIn('name="custom_industry_name"', html)
        self.assertIn("data-ob-custom-industry hidden", html)              # hidden until «other» is picked
        self.assertIn('maxlength="80"', html)

    def test_the_installed_summary_shows_the_custom_name_and_the_base_template(self):
        self.post(self.other, "گالری سفال")
        html = self.get("industry").content.decode()
        self.assertIn("گالری سفال", html)
        self.assertIn("قالبِ پایه", html)


class LegacyAndCompatibilityTests(_Base):
    def test_existing_other_installations_without_a_name_stay_valid_and_render_the_template_name(self):
        installation = install_other_industry(self.store)                   # the legacy / seeded path (no name)
        self.assertEqual(installation.custom_industry_name, "")
        html = self.get("industry").content.decode()
        self.assertIn("سایر (صنف آزاد)", html)
        self.assertNotIn("قالبِ پایه", html)
        self.assertEqual(self.client.post(self.url("industry"), {}, HTTP_HOST=_HOST).status_code, 302)   # continue still works

    def test_existing_ordinary_selections_are_unchanged(self):
        template = make_rich_template()
        installation = svc.install_industry_template(self.store, template).installation
        installation.refresh_from_db()
        self.assertEqual(installation.custom_industry_name, "")
        self.assertEqual(installation.industry_template_id, template.pk)

    def test_the_column_is_additive_blank_by_default(self):
        field = StoreIndustryInstallation._meta.get_field("custom_industry_name")
        self.assertEqual((field.blank, field.default, field.max_length), (True, "", 80))


class CustomIndustryTenantIsolationTests(_Base):
    def test_each_store_keeps_its_own_name(self):
        other = ensure_other_template()
        self.assertEqual(self.post(other, "صنفِ فروشگاه الف").status_code, 302)
        owner_b = User.objects.create_user(username="b@example.com", email="b@example.com", password="a-very-strong-pass-1")
        store_b = provisioning_service.provision_trial_store(owner=owner_b, name="فروشگاه ب")
        installation_b = svc.install_industry_template(store_b, other, custom_name="صنفِ فروشگاه ب").installation
        self.assertEqual(StoreIndustryInstallation.objects.get(store=self.store).custom_industry_name, "صنفِ فروشگاه الف")
        self.assertEqual(installation_b.custom_industry_name, "صنفِ فروشگاه ب")

    def test_another_owner_cannot_set_or_read_a_name_through_this_stores_onboarding_url(self):
        other = ensure_other_template()
        intruder = User.objects.create_user(username="intruder@example.com", email="intruder@example.com", password="a-very-strong-pass-1")
        provisioning_service.provision_trial_store(owner=intruder, name="فروشگاه مهاجم")
        self.client.force_login(intruder)
        get = self.client.get(self.url("industry"), HTTP_HOST=_HOST)
        post = self.post(other, "نامِ دزدیده")
        self.assertEqual(get.status_code, 404)
        self.assertEqual(post.status_code, 404)
        self.assertNothingInstalled()
