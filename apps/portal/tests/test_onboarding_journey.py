"""The store-creation → onboarding wizard → store-created journey as ONE coherent system.

Contracts pinned here: a single shell (no legacy dark-theme classes, no inline styles, one palette),
a real 5-step progress indicator, every field error rendered, real-data template previews,
one-time-install confirmation, forged non-offerable installs refused, honest publication state.
"""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

import apps.portal as portal_app_module
from apps.catalog.models import (
    Attribute,
    Category,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    StoreIndustryInstallation,
)
from apps.catalog.services.template_validation_service import validate_and_persist
from apps.core.models import ShopSettings
from apps.portal.services import provisioning_service
from apps.portal.tests._ready_template import select_template
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription

User = get_user_model()
_HOST = "rastisi.localhost"
_PORTAL = Path(portal_app_module.__file__).resolve().parent
_TEMPLATES = _PORTAL / "templates" / "portal"

_JOURNEY_TEMPLATES = sorted(
    list((_TEMPLATES / "onboarding").glob("*.html"))
    + [
        _TEMPLATES / "app" / name for name in (
            "onboarding_identity.html", "onboarding_industry.html", "onboarding_template.html", "onboarding_branding.html",
            "onboarding_review.html", "store_create.html", "store_created.html",
        )
    ]
)

Readiness = IndustryTemplate.Readiness
CONFIRM = {"confirm_industry_install": "1"}


def make_rich_template(slug="journey-rich", name="پوشاک نمونه", sector=IndustryTemplate.Sector.RETAIL):
    """A production-ready template with a real tree, structured attribute and a variant axis."""
    template = IndustryTemplate.objects.create(
        slug=slug, name=name, description="توضیحِ واقعیِ قالب", sector=sector, version=1, icon="👗",
        default_section_keys=["announcement_bar", "hero_banner", "category_grid", "not-a-real-section-key"],
    )
    root = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="لباس")
    leaves = [
        IndustryTemplateCategory.objects.create(
            industry_template=template, code=f"leaf-{i}", name=f"زیرگروه {i}", parent=root,
        )
        for i in range(4)
    ]
    size = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
        is_variant_axis=True,
    )
    for label in ("S", "M", "L"):
        IndustryTemplateAttributeValue.objects.create(template_attribute=size, label=label)
    attrs = [size] + [
        IndustryTemplateAttribute.objects.create(
            industry_template=template, code=code, label=label, data_type=Attribute.DataType.TEXT,
        )
        for code, label in (("material", "جنسِ پارچه"), ("brand", "برند"), ("season", "فصل"), ("origin", "کشور سازنده"))
    ]
    for leaf in leaves:
        for attribute in attrs[:3]:
            IndustryTemplateCategoryAttributeMapping.objects.create(
                template_category=leaf, template_attribute=attribute, group="مشخصات", is_filterable=True,
            )
    IndustryTemplateRecommendedOption.objects.create(template_category=leaves[0], template_attribute=size)
    validate_and_persist(template)
    template.refresh_from_db()
    assert template.readiness == Readiness.PRODUCTION_READY, template.readiness
    return template


def make_skeletal_template(slug="journey-skeletal", name="اسکلتیِ نیازمندِ بازبینی"):
    template = IndustryTemplate.objects.create(slug=slug, name=name, sector=IndustryTemplate.Sector.RETAIL, version=1)
    category = IndustryTemplateCategory.objects.create(industry_template=template, code="all", name="همه")
    attribute = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="brand", label="برند", data_type=Attribute.DataType.TEXT,
    )
    IndustryTemplateCategoryAttributeMapping.objects.create(template_category=category, template_attribute=attribute)
    validate_and_persist(template)
    template.refresh_from_db()
    assert template.readiness == Readiness.REVIEW_REQUIRED, template.readiness
    return template


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class JourneyBase(TestCase):
    with_subscription = True

    def setUp(self):
        self.owner = User.objects.create_user(
            username="journey@example.com", email="journey@example.com", password="a-very-strong-pass-1",
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاهِ سفر")
        self.client.force_login(self.owner)
        if self.with_subscription and not StoreSubscription.objects.filter(store=self.store).exists():
            plan = Plan.objects.create(code="journey-plan", name="Journey")
            version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
            StoreSubscription.objects.create(
                store=self.store, plan_version=version, status=StoreSubscription.Status.TRIALING,
                is_current=True, trial_end_at=timezone.now(),
            )

    def url(self, stage):
        return f"/app/stores/{self.store.public_id}/onboarding/{stage}/"

    def get(self, stage):
        response = self.client.get(self.url(stage), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        return response

    def set_stage(self, stage):
        Store.objects.filter(pk=self.store.pk).update(onboarding_stage=stage)
        self.store.refresh_from_db()


class SingleShellContractTests(JourneyBase):
    def test_no_journey_template_uses_inline_styles_or_legacy_dark_classes(self):
        self.assertGreaterEqual(len(_JOURNEY_TEMPLATES), 12)
        for path in _JOURNEY_TEMPLATES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(template=path.name):
                self.assertNotRegex(source, r'\sstyle\s*=', "inline styles are not allowed in the journey")
                self.assertNotIn("<style", source)
                for legacy in ("p-form-card", "p-wrap", "p-btn", "p-card", "--p-", "industry-card", "industry-grid"):
                    self.assertNotRegex(source, rf"(?<![\w-]){re.escape(legacy)}")

    def test_every_stage_uses_the_one_onboarding_shell(self):
        for stage in ("identity", "industry", "template", "branding", "review"):
            with self.subTest(stage=stage):
                html = self.get(stage).content.decode()
                self.assertIn("portal/css/public-site-v2.css", html)
                self.assertIn("portal/css/onboarding.css", html)
                self.assertIn('class="ob-header"', html)
                self.assertIn("فروشگاهِ سفر", html)  # current store name in the header
                # the header link is plain navigation and must never promise a save
                self.assertIn("بازگشت<span", html)
                self.assertIn("بازگشت به فروشگاه‌های من", html)
                self.assertNotIn("ذخیره و بازگشت", html)
                self.assertIn("پس از «ذخیره و ادامه» در هر مرحله، پیشرفت شما ثبت می‌شود", html)
                self.assertNotIn("پیشرفت شما در هر مرحله ذخیره می‌شود", html)
                self.assertNotIn("p-header", html)
                self.assertNotIn("p-form-card", html)

    def test_onboarding_stylesheet_has_no_colour_literals_outside_tokens(self):
        css = (_PORTAL / "static" / "portal" / "css" / "onboarding.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotRegex(css, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(css, r"\b(rgb|rgba|hsl|hsla)\(")


class ProgressIndicatorTests(JourneyBase):
    def _steps(self, html):
        return re.findall(r'<li class="ob-step([^"]*)">', html)

    def test_fresh_store_has_current_first_step_and_locked_rest(self):
        html = self.get("identity").content.decode()
        classes = self._steps(html)
        self.assertEqual(len(classes), 5)
        self.assertIn("is-current", classes[0])
        for later in classes[1:]:
            self.assertIn("is-locked", later)
        for label in ("معرفی", "صنف", "قالب فروشگاه", "برند", "بازبینی"):
            self.assertIn(label, html)
        self.assertNotIn("ظاهر", html.split('<ol class="ob-steps">')[1].split("</ol>")[0])  # branding renamed
        self.assertIn("مرحله 1 از 5", html.replace("۱", "1").replace("۵", "5"))
        self.assertEqual(html.count('aria-current="step"'), 1)

    def test_template_step_is_done_once_a_template_is_applied(self):
        select_template(self.client, self.url("template"))
        self.set_stage(Store.OnboardingStage.REVIEW)
        classes = self._steps(self.get("review").content.decode())
        self.assertIn("is-done", classes[2])

    def test_completed_steps_are_links_and_current_changes_per_stage(self):
        self.set_stage(Store.OnboardingStage.REVIEW)
        html = self.get("review").content.decode()
        classes = self._steps(html)
        self.assertEqual(len(classes), 5)
        self.assertIn("is-done", classes[0])
        self.assertIn("is-done", classes[1])
        # «قالب فروشگاه» is done only when a Ready Template is REALLY applied — not merely passed
        self.assertNotIn("is-done", classes[2])
        self.assertIn("is-done", classes[3])
        self.assertIn("is-current", classes[4])
        for stage in ("identity", "industry", "template", "branding"):
            self.assertIn(f'href="{self.url(stage)}"', html)
        # revisiting an earlier step never loses progress
        earlier = self.get("identity").content.decode()
        self.assertIn("is-current", self._steps(earlier)[0])
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.REVIEW)

    def test_optional_steps_are_marked_optional_and_have_a_skip_action(self):
        self.assertIn("اختیاری", self.get("industry").content.decode())
        template_html = self.get("template").content.decode()
        self.assertNotIn("فعلاً رد شو", template_html)  # the template step is required: no skip path
        html = self.get("branding").content.decode()
        self.assertIn("فعلاً رد شو", html)
        self.assertNotIn("فعلاً رد شو", self.get("identity").content.decode())
        self.assertNotIn("فعلاً رد شو", self.get("review").content.decode())


class IdentityStageTests(JourneyBase):
    def test_every_field_error_is_rendered_and_values_are_preserved(self):
        response = self.client.post(
            self.url("identity"),
            {
                "name": "", "tagline": "ش" * 250, "description": "d",
                "contact_phone": "9" * 40, "contact_email": "not-an-email", "contact_address": "آ" * 301,
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for field in ("name", "tagline", "contact_phone", "contact_email", "contact_address"):
            with self.subTest(field=field):
                self.assertTrue(response.context["form"][field].errors)
        self.assertGreaterEqual(html.count('class="ob-error"'), 5)
        self.assertIn('data-ob-error-summary', html)
        self.assertIn("not-an-email", html)  # typed value survives
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "فروشگاهِ سفر")  # nothing persisted on error

    def test_required_vs_optional_is_explicit_and_ltr_fields_are_isolated(self):
        html = self.get("identity").content.decode()
        self.assertEqual(html.count("ob-tag-required"), 1)
        self.assertGreaterEqual(html.count('class="ob-tag">اختیاری'), 5)
        self.assertIn('inputmode="tel"', html)
        self.assertIn('autocomplete="email"', html)

    def test_placeholders_are_never_saved(self):
        self.client.post(self.url("identity"), {"name": "فقط نام"}, HTTP_HOST=_HOST)
        settings_row = ShopSettings.load(store=self.store)
        self.assertEqual(settings_row.tagline, "")
        self.assertEqual(settings_row.contact_phone, "")
        self.assertEqual(settings_row.contact_email, "")


class IndustryStageTests(JourneyBase):
    def test_cards_come_from_real_template_data_and_are_simple(self):
        template = make_rich_template()
        make_skeletal_template()
        html = self.get("industry").content.decode()
        self.assertIn("پوشاک نمونه", html)
        self.assertNotIn("اسکلتیِ نیازمندِ بازبینی", html)  # review-required never offered
        # real count only: 1 root + 4 leaves = 5 categories — no attribute/feature count or list
        self.assertIn("5 دسته‌بندی", html)
        self.assertNotIn("5 ویژگی", html)
        card = html[html.index(f'data-id="{template.pk}"'):]
        card = card[:card.index("</label>")]
        for detail in ("جنسِ پارچه", "کشور سازنده", "زیرگروه 3", "نگاشتِ ویژگی", "محورهایِ تنوع", "نوار اعلان"):
            self.assertNotIn(detail, card)

    def test_install_cta_is_confirmation_grade_and_skip_is_explained(self):
        make_rich_template()
        html = self.get("industry").content.decode()
        self.assertIn("data-ob-confirm-check", html)
        self.assertIn('name="confirm_industry_install" value="1"', html)  # the exact server-checked value
        self.assertIn("صنف انتخاب‌شده:", html)
        self.assertIn("دسته‌بندی‌ها و ویژگی‌های پایه‌ی این صنف برای فروشگاه ساخته می‌شوند", html)
        self.assertIn("فقط یک‌بار", html)
        self.assertIn("این صنف را برای فروشگاهم نصب کن", html)
        self.assertIn("data-ob-install-submit", html)
        self.assertNotIn("data-ob-install-submit disabled", html)  # JS enables/disables; no-JS can still submit (server decides)
        self.assertIn("فعلاً رد شو", html)
        self.assertIn("بدونِ قالبِ صنف ادامه می‌دهید و دسته‌بندی‌ها و ویژگی‌ها را بعداً از پنلِ مدیریت می‌سازید", html)

    def test_direct_post_without_confirmation_installs_nothing(self):
        """The one-time-install acknowledgement is enforced SERVER-side: a bare
        {"industry_template_id": pk} POST (JS disabled / forged) must not install."""
        template = make_rich_template()
        response = self.client.post(self.url("industry"), {"industry_template_id": template.pk}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "برای نصبِ قالبِ صنف باید تأیید کنید")
        self.assertContains(response, "برای نصب باید کادرِ تأییدِ بالا را علامت بزنید")
        self.assertTrue(response.context["confirm_error"])
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        self.assertEqual(Category.objects.filter(store=self.store).count(), 0)
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)  # not advanced
        # the selection is kept so the owner only has to tick the box
        self.assertIn(f'value="{template.pk}" checked', response.content.decode())
        for falsy in ("", "0", "false"):
            with self.subTest(confirm=falsy):
                again = self.client.post(
                    self.url("industry"),
                    {"industry_template_id": template.pk, "confirm_industry_install": falsy}, HTTP_HOST=_HOST,
                )
                self.assertEqual(again.status_code, 200)
                self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_confirmation_checkbox_is_a_real_named_input(self):
        make_rich_template()
        html = self.get("industry").content.decode()
        self.assertRegex(html, r'<input type="checkbox" name="confirm_industry_install" value="1" data-ob-confirm-check')

    def test_selected_template_with_confirmation_installs_exactly_once(self):
        template = make_rich_template()
        response = self.client.post(
            self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self.url("template"))
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.categories_created, template.categories.count())
        self.assertEqual(Category.objects.filter(store=self.store).count(), 5)
        # replay / double-submit with the same payload: no second install, no error, no duplicate rows
        replay = self.client.post(
            self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(replay, self.url("template"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)
        self.assertEqual(Category.objects.filter(store=self.store).count(), 5)

    def test_skip_and_already_installed_continue_do_not_require_confirmation(self):
        skip = self.client.post(self.url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(skip, self.url("template"))
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_installed_continue_without_confirmation_is_fine(self):
        template = make_rich_template()
        self.client.post(self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST)
        cont = self.client.post(self.url("industry"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(cont, self.url("template"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_forged_post_cannot_install_a_review_required_template(self):
        held = make_skeletal_template()
        response = self.client.post(
            self.url("industry"), {"industry_template_id": held.pk, **CONFIRM}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "در دسترس نیست")
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        self.assertEqual(Category.objects.filter(store=self.store).count(), 0)
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.IDENTITY)  # not advanced

    def test_forged_post_cannot_install_inactive_deprecated_or_draft_templates(self):
        rich = make_rich_template("forge-inactive", "غیرفعال")
        IndustryTemplate.objects.filter(pk=rich.pk).update(is_active=False)
        deprecated = make_rich_template("forge-deprecated", "منسوخ")
        IndustryTemplate.objects.filter(pk=deprecated.pk).update(readiness=Readiness.DEPRECATED, is_active=False)
        draft = make_rich_template("forge-draft", "پیش‌نویس")
        IndustryTemplate.objects.filter(pk=draft.pk).update(readiness=Readiness.DRAFT)
        for pk in (rich.pk, deprecated.pk, draft.pk, 999999):
            with self.subTest(pk=pk):
                response = self.client.post(
                    self.url("industry"), {"industry_template_id": pk, **CONFIRM}, HTTP_HOST=_HOST,
                )
                self.assertEqual(response.status_code, 200)  # friendly error, not a 404 page
                self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_a_racing_second_install_moves_on_instead_of_showing_an_error(self):
        """Double-click/concurrent POST: the first install won; the loser must not see
        «already installed» as a failure. Simulated by installing between the page's
        installation check and its POST handling."""
        from unittest import mock

        from apps.catalog.services import industry_template_service

        template = make_rich_template()
        real_install = industry_template_service.install_industry_template

        def racing(store, tpl):
            real_install(store, tpl)  # the "other request" wins first
            return real_install(store, tpl)  # this request now fails: already installed

        with mock.patch("apps.catalog.services.industry_template_service.install_industry_template", racing):
            response = self.client.post(
                self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST,
            )
        self.assertRedirects(response, self.url("template"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_empty_selection_explains_instead_of_silently_reloading(self):
        make_rich_template()
        response = self.client.post(self.url("industry"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ابتدا یک صنف را انتخاب کنید")

    def test_already_installed_state_shows_summary_and_is_idempotent(self):
        template = make_rich_template()
        self.client.post(self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST)
        html = self.get("industry").content.decode()
        self.assertIn("ob-installed", html)
        self.assertIn("پوشاک نمونه", html)
        self.assertIn("5 دسته‌بندی و 5 ویژگی ساخته شد", html)
        self.assertNotIn("data-ob-industry", html)  # no selector, no second install
        again = self.client.post(self.url("industry"), {"industry_template_id": template.pk, **CONFIRM}, HTTP_HOST=_HOST)
        self.assertRedirects(again, self.url("template"))
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)
        self.assertEqual(Category.objects.filter(store=self.store).count(), 5)

    def test_no_template_state_is_not_a_dead_end(self):
        make_skeletal_template()  # only a review-required one exists → nothing offerable
        response = self.get("industry")
        self.assertContains(response, "در حال حاضر قالبِ صنفی برای ارائه موجود نیست.")
        self.assertContains(response, "ادامه بدونِ قالبِ صنف")
        skip = self.client.post(self.url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertRedirects(skip, self.url("template"))


class BrandingStageTests(JourneyBase):
    def test_guidance_matches_the_real_validation_and_no_fake_colour_controls(self):
        html = self.get("branding").content.decode()
        self.assertIn('accept="image/png,image/jpeg,image/webp,image/gif"', html)
        self.assertIn("SVG", html)
        self.assertIn("سازنده‌ی ویترین", html)
        self.assertIn("هنوز لوگویی نیست", html)
        for forbidden in ("primary_color", "accent_color", 'type="color"'):
            self.assertNotIn(forbidden, html)

    def test_non_image_upload_shows_the_real_backend_error(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("logo.png", b"definitely not an image", content_type="image/png")
        response = self.client.post(self.url("branding"), {"logo": bad}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"]["logo"].errors)
        self.assertContains(response, "data-ob-error-summary")
        self.assertFalse(ShopSettings.load(store=self.store).logo)

    def test_skip_and_blank_continue_both_advance_without_a_logo(self):
        blank = self.client.post(self.url("branding"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(blank, self.url("review"))
        self.assertFalse(ShopSettings.load(store=self.store).logo)


class ReviewAndPublishTests(JourneyBase):
    def test_review_summarises_what_the_owner_entered_with_edit_links(self):
        self.client.post(self.url("identity"), {
            "name": "فروشگاهِ نهایی", "tagline": "شعارِ نهایی", "contact_phone": "021-12345678",
            "contact_email": "shop@example.com",
        }, HTTP_HOST=_HOST)
        html = self.get("review").content.decode()
        for expected in ("فروشگاهِ نهایی", "شعارِ نهایی", "021-12345678", "shop@example.com", "ثبت نشده"):
            self.assertIn(expected, html)
        self.assertIn("ob-ltr", html)  # phone/email/hostname are isolated LTR runs
        self.assertIn(self.store.domains.filter(is_primary=True).first().hostname, html)
        for stage in ("identity", "industry", "template", "branding"):
            self.assertIn(f'href="{self.url(stage)}"', html)
        self.assertIn("نصب نشده", html)
        self.assertIn("انتشارِ فروشگاه", html)
        self.assertIn("با انتشار چه می‌شود؟", html)
        self.assertIn("هنوز منتشر نشده", html)

    def test_nothing_is_public_before_the_publish_post_and_the_post_is_idempotent(self):
        from apps.stores.services.publication_service import PublicationState, get_store_publication_state

        self.assertEqual(get_store_publication_state(self.store), PublicationState.TRIAL_PRIVATE)
        select_template(self.client, self.url("template"))
        self.get("review")  # viewing never publishes
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        first = self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(first, f"/app/stores/{self.store.public_id}/created/")
        self.store.refresh_from_db()
        stamp = self.store.onboarding_completed_at
        self.assertIsNotNone(stamp)
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.DONE)
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)  # refresh / double-click
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_completed_at, stamp)

    def test_review_after_publish_has_no_second_publish_button(self):
        select_template(self.client, self.url("template"))
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        html = self.get("review").content.decode()
        self.assertNotIn("ob-publish-form", html)
        self.assertIn("رفتن به صفحه‌ی فروشگاه", html)

    def test_publication_claim_follows_the_real_publication_state(self):
        Store.objects.filter(pk=self.store.pk).update(status=Store.Status.SUSPENDED)
        html = self.get("review").content.decode()
        self.assertIn("تا رفعِ این وضعیت ویترین برای عموم نمایش داده نمی‌شود", html)
        self.assertNotIn("برای بازدیدکنندگان قابلِ مشاهده می‌شود", html)


class StoreCreatedAndStoreCreateTests(JourneyBase):
    def created(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/created/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_unfinished_store_is_pointed_back_into_the_wizard(self):
        html = self.created()
        self.assertIn("ساخته شد", html)
        self.assertIn("ادامه‌ی راه‌اندازی", html)
        self.assertIn(f'href="/app/stores/{self.store.public_id}/onboarding/"', html)
        self.assertIn("فعلاً فقط برای شما قابلِ مشاهده است", html)
        self.assertNotIn("enter-admin", html)
        self.assertNotIn("/enter-admin/", html)

    def test_published_store_shows_real_hostname_and_admin_entry(self):
        select_template(self.client, self.url("template"))
        self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)
        html = self.created()
        self.assertIn("منتشر شد", html)
        self.assertIn(self.store.domains.filter(is_primary=True).first().hostname, html)
        self.assertIn("ورود به پنلِ مدیریت", html)
        self.assertNotIn("ادامه‌ی راه‌اندازی", html)

    def test_store_create_uses_the_same_shell_and_has_no_industry_installation_path(self):
        make_rich_template()
        html = self.client.get("/app/stores/new/", HTTP_HOST=_HOST).content.decode()
        self.assertIn("portal/css/onboarding.css", html)
        self.assertNotIn("پوشاک نمونه", html)  # no selector at creation
        self.assertNotIn("industry_template_id", html)
        self.assertNotIn("confirm_industry_install", html)
        self.assertIn("در این صفحه هیچ قالبی نصب نمی‌شود", html)

    def test_store_create_ignores_a_forged_template_even_with_confirmation(self):
        rich = make_rich_template()
        held = make_skeletal_template()
        for index, payload in enumerate((
            {"industry_template_id": rich.pk},
            {"industry_template_id": rich.pk, **CONFIRM},
            {"industry_template_id": held.pk, **CONFIRM},
        )):
            with self.subTest(payload=payload):
                token = self.client.get("/app/stores/new/", HTTP_HOST=_HOST).context["submission_token"]
                name = f"فروشگاهِ جعلی {index}"
                response = self.client.post(
                    "/app/stores/new/", {"name": name, "submission_token": token, **payload}, HTTP_HOST=_HOST,
                )
                self.assertEqual(response.status_code, 302)
                created = Store.objects.get(name=name)
                self.assertFalse(StoreIndustryInstallation.objects.filter(store=created).exists())
                self.assertEqual(Category.objects.filter(store=created).count(), 0)
