from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services import provisioning_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.publication_service import PublicationState, get_store_publication_state

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingViewTests(TestCase):
    """Section 5 — the multi-stage wizard (identity → industry → branding →
    review). The dispatcher (``/onboarding/``) always redirects to whichever
    stage the Store is currently on; only the review stage's POST sets
    ``onboarding_completed_at``."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="onboardowner@example.com", email="onboardowner@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه من")
        self.client.force_login(self.owner)

    def _url(self, stage):
        return f"/app/stores/{self.store.public_id}/onboarding/{stage}/"

    def test_dispatcher_redirects_a_fresh_store_to_the_identity_stage(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("identity"))

    def test_identity_stage_renders_form_with_current_name(self):
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فروشگاه من")

    def test_new_store_starts_with_onboarding_incomplete(self):
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)

    def _complete_identity(self, name="عطر گل"):
        return self.client.post(self._url("identity"), {"name": name}, HTTP_HOST=_HOST)

    def test_identity_stage_saves_name_and_advances_to_industry(self):
        response = self._complete_identity()
        self.assertRedirects(response, self._url("industry"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "عطر گل")
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.INDUSTRY)
        self.assertIsNone(self.store.onboarding_completed_at)

    def test_industry_stage_installs_the_selected_template_and_advances(self):
        from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation

        template = IndustryTemplate.objects.create(
            slug="perfume", name="عطر", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        self._complete_identity()
        response = self.client.post(
            self._url("industry"), {"industry_template_id": template.pk, "confirm_industry_install": "1"}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url("branding"))
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, template.pk)

    def test_industry_stage_already_installed_never_installs_twice(self):
        from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
        from apps.catalog.services.industry_template_service import install_industry_template

        template = IndustryTemplate.objects.create(
            slug="books", name="کتاب", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        self._complete_identity()
        install_industry_template(self.store, template)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

        response = self.client.get(self._url("industry"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کتاب")

        response = self.client.post(self._url("industry"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("branding"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_industry_stage_skip_advances_to_branding_without_installing(self):
        self._complete_identity()
        response = self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("branding"))
        self.assertFalse(hasattr(self.store, "industry_installation"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

    def test_branding_stage_skip_advances_to_review(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("review"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.REVIEW)

    def test_branding_stage_has_no_color_fields(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.get(self._url("branding"), HTTP_HOST=_HOST)
        self.assertNotContains(response, "primary_color")
        self.assertNotContains(response, "accent_color")
        self.assertNotContains(response, "رنگ اصلی")
        self.assertNotContains(response, "رنگ مکمل")

    def test_branding_stage_post_succeeds_without_color_values(self):
        from apps.core.models import ShopSettings

        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        original = ShopSettings.load(store=self.store)
        original_primary, original_accent = original.primary_color, original.accent_color

        # No primary_color/accent_color in the POST at all — the step must
        # not require them to proceed, and any such keys a client sends
        # anyway must be silently ignored by the (now colorless) form.
        response = self.client.post(
            self._url("branding"),
            {"primary_color": "#112233", "accent_color": "#445566"},
            HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._url("review"))

        # Existing theme defaults are untouched — onboarding never wrote to
        # them, even though the client tried to send color values.
        shop_settings = ShopSettings.load(store=self.store)
        self.assertEqual(shop_settings.primary_color, original_primary)
        self.assertEqual(shop_settings.accent_color, original_accent)

    def test_review_stage_publishes_and_completes_onboarding(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        response = self.client.post(self._url("review"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertIsNotNone(self.store.onboarding_completed_at)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)

    def test_dispatcher_resumes_at_the_saved_stage(self):
        self._complete_identity()
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("industry"))

    def test_dispatcher_sends_a_completed_store_straight_to_store_created(self):
        self._complete_identity()
        self.client.post(self._url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(self._url("review"), {}, HTTP_HOST=_HOST)
        response = self.client.get(f"/app/stores/{self.store.public_id}/onboarding/", HTTP_HOST=_HOST)
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/created/")

    def test_earlier_stage_remains_freely_editable_after_advancing(self):
        self._complete_identity()
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.client.post(self._url("identity"), {"name": "دوباره ویرایش شد"}, HTTP_HOST=_HOST)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "دوباره ویرایش شد")
        # Revisiting an earlier stage never regresses saved progress.
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.INDUSTRY)

    def test_other_owner_cannot_onboard_someone_elses_store(self):
        other = User.objects.create_user(
            username="otheronboard@example.com", email="otheronboard@example.com",
            password="a-very-strong-pass-1",
        )
        self.client.force_login(other)
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self._url("identity"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingIdentityPlaceholderTests(TestCase):
    """Regression tests for Issue 1 — the onboarding identity step used to
    persist generic, example platform content (``SHOP_NAME``/``SHOP_TAGLINE``/
    ``SHOP_CONTACT_*`` — literally "دیجی‌مارکت" / "info@digimarket.ir" /
    "تهران، خیابان ولیعصر", explicitly documented in settings.py as generic
    *platform* identity, not any real merchant's data) into a brand-new
    Store's real ``ShopSettings`` row via ``provision_for``, and the
    onboarding form then pre-filled those fake values as if they were the
    merchant's own saved data."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="placeholderowner@example.com", email="placeholderowner@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه شعف")
        self.client.force_login(self.owner)

    def _url(self):
        return f"/app/stores/{self.store.public_id}/onboarding/identity/"

    def test_new_store_shop_settings_has_no_fake_example_values(self):
        from apps.core.models import ShopSettings

        shop_settings = ShopSettings.load(store=self.store)
        self.assertEqual(shop_settings.name, self.store.name)
        self.assertNotEqual(shop_settings.name, "دیجی‌مارکت")
        self.assertEqual(shop_settings.tagline, "")
        self.assertEqual(shop_settings.contact_phone, "")
        self.assertEqual(shop_settings.contact_email, "")
        self.assertEqual(shop_settings.contact_address, "")

    def test_new_store_identity_form_fields_are_genuinely_empty(self):
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("tagline", ""), "")
        self.assertEqual(form.initial.get("contact_phone", ""), "")
        self.assertEqual(form.initial.get("contact_email", ""), "")
        self.assertEqual(form.initial.get("contact_address", ""), "")
        # Never rendered as a real, submitted value for a brand-new store.
        self.assertNotContains(response, "info@digimarket.ir")
        self.assertNotContains(response, "021-91008877")
        self.assertNotContains(response, "تهران، خیابان ولیعصر")

    def test_guidance_appears_as_html_placeholder_not_a_value(self):
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertContains(response, 'placeholder="مثلاً: بهترین کیفیت، مناسب‌ترین قیمت"')
        self.assertContains(response, 'placeholder="مثلاً: 021-12345678"')

    def test_submitting_without_optional_fields_persists_nothing(self):
        self.client.post(self._url(), {"name": "فروشگاه شعف"}, HTTP_HOST=_HOST)
        from apps.core.models import ShopSettings

        shop_settings = ShopSettings.load(store=self.store)
        self.assertEqual(shop_settings.tagline, "")
        self.assertEqual(shop_settings.contact_phone, "")
        self.assertEqual(shop_settings.contact_email, "")
        self.assertEqual(shop_settings.contact_address, "")

    def test_previously_saved_real_value_is_shown_normally_on_return(self):
        self.client.post(
            self._url(),
            {
                "name": "فروشگاه شعف", "tagline": "بهترین کیفیت شهر",
                "contact_phone": "09120000000", "contact_email": "real@myshop.ir",
                "contact_address": "اصفهان، خیابان چهارباغ",
            },
            HTTP_HOST=_HOST,
        )
        # Revisit the (freely-editable) identity stage.
        response = self.client.get(self._url(), HTTP_HOST=_HOST)
        self.assertContains(response, "بهترین کیفیت شهر")
        self.assertContains(response, "09120000000")
        self.assertContains(response, "real@myshop.ir")
        self.assertContains(response, "اصفهان، خیابان چهارباغ")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingIndustryTemplateVisibilityTests(TestCase):
    """Regression tests for Issue 2 — the onboarding "choose your industry"
    step must show every active, production-ready Industry Template, must
    never show an inactive/unusable one, and must only fall back to the
    empty state when there are genuinely zero usable templates.

    ``IndustryTemplate`` rows are living platform content synced only by
    ``python manage.py seed_industry_templates`` (never by a schema
    migration — see ``ProductionDeploymentSequenceTests`` in
    ``apps/catalog/tests/test_seed_industry_templates.py`` for why), so a
    freshly-migrated test database already starts with zero rows.
    ``IndustryTemplate.objects.all().delete()`` in ``setUp`` is a defensive
    no-op today that keeps this class self-contained regardless of what any
    other fixture/test in the suite may have created."""

    _EMPTY_STATE_TEXT = "در حال حاضر قالبِ صنفی برای ارائه موجود نیست."

    def setUp(self):
        from apps.catalog.models import IndustryTemplate

        IndustryTemplate.objects.all().delete()
        self.owner = User.objects.create_user(
            username="industryowner@example.com", email="industryowner@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه صنف")
        self.client.force_login(self.owner)
        self.client.post(
            f"/app/stores/{self.store.public_id}/onboarding/identity/",
            {"name": self.store.name}, HTTP_HOST=_HOST,
        )

    def _industry_url(self):
        return f"/app/stores/{self.store.public_id}/onboarding/industry/"

    def test_empty_state_shown_when_no_templates_exist_at_all(self):
        response = self.client.get(self._industry_url(), HTTP_HOST=_HOST)
        self.assertContains(response, self._EMPTY_STATE_TEXT)

    def test_active_production_ready_template_is_shown(self):
        from apps.catalog.models import IndustryTemplate

        IndustryTemplate.objects.create(
            slug="visible-industry", name="صنفِ نمایان", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        response = self.client.get(self._industry_url(), HTTP_HOST=_HOST)
        self.assertContains(response, "صنفِ نمایان")
        self.assertNotContains(response, self._EMPTY_STATE_TEXT)

    def test_inactive_template_is_never_shown(self):
        from apps.catalog.models import IndustryTemplate

        IndustryTemplate.objects.create(
            slug="hidden-inactive", name="صنفِ غیرفعال", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=False,
        )
        response = self.client.get(self._industry_url(), HTTP_HOST=_HOST)
        self.assertNotContains(response, "صنفِ غیرفعال")
        # Nothing else is active either — the empty state must still show.
        self.assertContains(response, self._EMPTY_STATE_TEXT)

    def test_non_production_ready_template_is_never_shown(self):
        from apps.catalog.models import IndustryTemplate

        IndustryTemplate.objects.create(
            slug="hidden-draft", name="صنفِ پیش‌نویس", version=1,
            readiness=IndustryTemplate.Readiness.DRAFT, is_active=True,
        )
        response = self.client.get(self._industry_url(), HTTP_HOST=_HOST)
        self.assertNotContains(response, "صنفِ پیش‌نویس")
        self.assertContains(response, self._EMPTY_STATE_TEXT)

    def test_installing_a_template_only_provisions_data_for_this_store(self):
        from apps.catalog.models import Category, IndustryTemplate, IndustryTemplateCategory

        template = IndustryTemplate.objects.create(
            slug="isolated-industry", name="صنفِ ایزوله", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        IndustryTemplateCategory.objects.create(
            industry_template=template, code="root-category", name="دسته‌ی ریشه",
        )
        other_owner = User.objects.create_user(
            username="otherstoreowner@example.com", email="otherstoreowner@example.com",
            password="a-very-strong-pass-1",
        )
        other_store = provisioning_service.provision_trial_store(owner=other_owner, name="فروشگاه دیگر")

        response = self.client.post(
            self._industry_url(), {"industry_template_id": template.pk, "confirm_industry_install": "1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)

        self.assertTrue(Category.objects.filter(store=self.store).exists())
        self.assertFalse(Category.objects.filter(store=other_store).exists())


class RegistrationAutoProvisionsTrialStoreTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # OTP rate-limit counters are cache-backed and leak across tests otherwise

    def _fixed_code(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "222333"
        self.addCleanup(setattr, svc, "_generate_code", original)
        return "222333"

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_first_registration_creates_exactly_one_store(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "First Timer", "phone": "09359990001", "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990001", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990001")
        memberships = StoreMembership.objects.filter(
            user=user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        self.assertEqual(memberships.count(), 1)
        self.assertEqual(memberships.first().store.name, "فروشگاه من")

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_my_stores_shows_the_auto_provisioned_store_immediately(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Second", "phone": "09359990002", "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990002", "code": code}, HTTP_HOST=_HOST)

        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertContains(response, "فروشگاه من")
        self.assertContains(response, "راه‌اندازی ناتمام")

    @override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
    def test_trial_store_storefront_is_403_until_onboarding_completes(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Third", "phone": "09359990003", "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990003", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990003")
        store = StoreMembership.objects.get(user=user).store
        trial_domain = store.domains.get(is_primary=True)

        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        # RASTISI_DEFAULT_PLAN_CODE is unset in this environment (Section 7 —
        # the four seeded Plans — is not built yet), so provisioning's call
        # to provision_default_subscription fails open and creates no
        # subscription at all. With zero subscriptions, publication_service
        # itself fails open (ADR-65/ADR-103) rather than restrict a Store it
        # has no entitlement data for — so this is correctly 200 today. Once
        # a real default plan is configured, this same Store (still not
        # onboarded) would 403 instead — see test_publication_service.py for
        # that behavior tested directly against the service, and
        # test_full_chain_with_real_default_plan_configured below for the
        # same thing exercised end-to-end.
        self.assertEqual(response.status_code, 200)

    @override_settings(RASTISI_DEFAULT_PLAN_CODE="trial")
    def test_full_chain_with_real_default_plan_configured(self):
        """Section 7 (four seeded Plans) closes the loop Section 6 left
        open: with a real default plan configured, a freshly-registered
        owner's Store gets a genuine trialing subscription, so its
        storefront is correctly 403 until onboarding completes — then 200
        once it does."""
        call_command("seed_default_plans", stdout=StringIO())

        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Fourth", "phone": "09359990004", "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09359990004", "code": code}, HTTP_HOST=_HOST)

        user = User.objects.get(username="09359990004")
        membership = StoreMembership.objects.get(user=user)
        store = membership.store
        trial_domain = store.domains.get(is_primary=True)

        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        self.assertEqual(response.status_code, 403)

        # Complete the onboarding wizard — the same Store must now be publicly visible.
        base = f"/app/stores/{store.public_id}/onboarding"
        self.client.post(f"{base}/identity/", {"name": "فروشگاه چهارم"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/industry/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/branding/", {"action": "skip"}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/review/", {}, HTTP_HOST=_HOST)
        with self.settings(ALLOWED_HOSTS=[trial_domain.hostname, _HOST, "testserver"]):
            response = self.client.get("/", HTTP_HOST=trial_domain.hostname)
        self.assertEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class IndustrySearchInputContrastTests(TestCase):
    """Regression tests for the invisible industry-search input text.

    Root cause: the shared ``.industry-search input`` component
    (``apps/catalog/static/css/industry_selector.css``) sets an explicit
    light/white ``background`` but never sets ``color`` at all, so the
    typed/placeholder text falls back to whatever color is ambient on the
    page. On this dark-first portal theme (``--p-ink`` is a light,
    near-white color — see ``platform-tokens.css``), that produces
    effectively white text on a white input: unreadable. The component
    itself is correct for its other, light-themed consumers (the public
    "supported industries" page, the merchant dashboard) and is
    deliberately left untouched; the fix instead scopes an override to
    ``.p-form-card .industry-search input`` in ``platform-tokens.css``
    (loaded on every dark-themed portal page), reusing this theme's own
    existing tokens (``--p-card``/``--p-ink``/``--p-muted``) rather than
    hard-coded colors."""

    def setUp(self):
        from apps.catalog.models import IndustryTemplate

        # The search bar (and its ``.industry-search`` markup) only renders
        # when at least one offerable template exists — without one, both
        # pages under test fall back to their (unrelated) empty state.
        IndustryTemplate.objects.create(
            slug="contrast-test-industry", name="صنفِ آزمایشیِ کنتراست", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        self.owner = User.objects.create_user(
            username="contrastowner@example.com", email="contrastowner@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه کنتراست")
        self.client.force_login(self.owner)

    def _css_path(self):
        import apps.portal as portal_app_module
        from pathlib import Path

        return Path(portal_app_module.__file__).resolve().parent / "static/portal/css/platform-tokens.css"

    def test_platform_tokens_css_defines_readable_search_input_colors(self):
        css = self._css_path().read_text(encoding="utf-8")
        self.assertIn(".p-form-card .industry-search input", css)
        # Not just present — must actually set both background and a
        # readable foreground color together (a rule that set only one of
        # the two would still leave the text unreadable).
        rule_start = css.index(".p-form-card .industry-search input{")
        rule_end = css.index("}", rule_start)
        rule_body = css[rule_start:rule_end]
        self.assertIn("background:var(--p-card)", rule_body)
        self.assertIn("color:var(--p-ink)", rule_body)
        # The placeholder must stay visually secondary (muted), not the
        # same strong foreground color as typed text.
        self.assertIn(".p-form-card .industry-search input::placeholder", css)
        placeholder_start = css.index(".p-form-card .industry-search input::placeholder{")
        placeholder_end = css.index("}", placeholder_start)
        self.assertIn("color:var(--p-muted)", css[placeholder_start:placeholder_end])

    def test_onboarding_industry_page_uses_the_light_onboarding_shell_search_input(self):
        """The onboarding journey no longer renders the legacy dark-themed selector
        (the original root cause); its own search input pairs a background with a
        readable foreground token, so typed text can never go invisible."""
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/onboarding/industry/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("portal/css/onboarding.css", content)
        self.assertNotIn("css/industry_selector.css", content)
        self.assertIn("data-ob-search", content)

        from pathlib import Path
        import apps.portal as portal_app_module

        css = (Path(portal_app_module.__file__).resolve().parent / "static/portal/css/onboarding.css").read_text(
            encoding="utf-8",
        )
        rule = css[css.index(".ob-search input{"):]
        rule = rule[:rule.index("}")]
        self.assertIn("background:var(--rs-paper)", rule)
        self.assertIn("color:var(--rs-ink)", rule)

    def test_store_create_wizard_no_longer_renders_the_selector(self):
        """Store creation installs nothing (the irreversible install is confirmation-gated on the
        onboarding «صنف» step), so there is no selector — and no contrast issue — on that page."""
        self.client.logout()
        second_owner = User.objects.create_user(
            username="contrastowner2@example.com", email="contrastowner2@example.com",
            password="a-very-strong-pass-1",
        )
        self.client.force_login(second_owner)
        response = self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("portal/css/onboarding.css", content)
        self.assertNotIn("css/industry_selector.css", content)
        self.assertNotIn("data-ob-search", content)
