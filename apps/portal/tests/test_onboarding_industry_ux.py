"""Onboarding «صنف» step — a clean single-flow card grid (no split master/detail, no feature dump).

The detailed ``template_summary_service`` stays available for other surfaces; onboarding renders only: icon, Persian
name, sector, a short authoritative description and a category count — plus ONE compact confirmation area next to the
action bar. The server-side one-time-install confirmation (exact ``"1"``) is unchanged.
"""

import re
from pathlib import Path

from django.template import TemplateDoesNotExist
from django.template.loader import get_template

import apps.portal as portal_app_module
from apps.catalog.models import Category, IndustryTemplate, StoreIndustryInstallation
from apps.portal.tests.test_onboarding_journey import (
    _HOST,
    JourneyBase,
    make_rich_template,
    make_skeletal_template,
)
from apps.stores.models import Store

_STATIC = Path(portal_app_module.__file__).resolve().parent / "static/portal"
CSS = (_STATIC / "css/onboarding.css").read_text(encoding="utf-8")
JS = (_STATIC / "js/onboarding.js").read_text(encoding="utf-8")


class IndustryPageIsSingleFlowTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.template = make_rich_template()
        make_rich_template(slug="journey-food", name="رستوران نمونه", sector=IndustryTemplate.Sector.FOOD)
        self.html = self.get("industry").content.decode()

    def test_there_is_no_split_layout_no_sticky_preview_and_no_detail_panels(self):
        for removed in (
            "ob-industry-layout", "ob-preview", "data-ob-preview", "data-ob-panel", "data-ob-preview-empty",
            "ob-creates", "ob-tags", "_template_preview",
        ):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, self.html)
        self.assertNotIn("<aside", self.html.split('id="ob-industry-title"')[1])

    def test_the_detail_partial_and_its_css_and_js_are_gone(self):
        with self.assertRaises(TemplateDoesNotExist):
            get_template("portal/onboarding/_template_preview.html")
        for rule in (".ob-industry-layout", ".ob-preview", ".ob-creates", ".ob-tags"):
            self.assertNotIn(rule, CSS)
        self.assertNotIn("data-ob-panel", JS)
        self.assertNotIn("data-ob-preview", JS)

    def test_cards_do_not_dump_categories_attributes_or_features(self):
        card = self.html[self.html.index(f'data-id="{self.template.pk}"'):]
        card = card[:card.index("</label>")]
        self.assertIn("پوشاک نمونه", card)
        self.assertIn("5 دسته‌بندی", card)
        self.assertIn("توضیحِ واقعیِ قالب", card)  # the short authoritative description
        for noise in ("ویژگی", "زیرگروه", "جنسِ پارچه", "نگاشت", "محور", "<ul", "<li"):
            self.assertNotIn(noise, card)

    def test_search_and_sector_filters_remain_and_every_offerable_industry_is_discoverable(self):
        make_skeletal_template()  # review_required: never offered
        html = self.get("industry").content.decode()
        self.assertIn("data-ob-search", html)
        self.assertIn("data-ob-sector=", html)
        offered = IndustryTemplate.objects.filter(
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        self.assertGreaterEqual(offered.count(), 2)
        for template in offered:
            with self.subTest(template=template.slug):
                self.assertIn(f'data-id="{template.pk}"', html)
                self.assertIn(f'data-name="{template.name}"', html)
        self.assertNotIn("اسکلتیِ نیازمندِ بازبینی", html)

    def test_one_compact_confirmation_area_sits_next_to_the_action_bar(self):
        html = self.html
        confirm = html.index("data-ob-confirm>")
        actions = html.index('class="ob-actions"')
        cards = html.index('class="ob-industry-list"')
        self.assertLess(cards, confirm)
        self.assertLess(confirm, actions)  # right above the CTA, not in a far-away side panel
        self.assertEqual(html.count("data-ob-confirm>"), 1)
        foot = html.index('class="ob-sticky-foot"')
        self.assertLess(foot, confirm)  # confirmation + CTA share one footer container
        area = html[confirm:actions]
        self.assertIn("صنف انتخاب‌شده:", area)
        self.assertIn("data-ob-selected-name", area)
        self.assertIn("دسته‌بندی‌ها و ویژگی‌های پایه‌ی این صنف برای فروشگاه ساخته می‌شوند", area)
        self.assertIn("این صنف را برای فروشگاهم نصب کن", area)
        self.assertIn('name="confirm_industry_install" value="1"', area)
        self.assertIn('form="ob-industry-form"', area)  # still submitted with the industry form (exact "1" checked server-side)

    def test_the_selected_card_state_is_strong_and_visible(self):
        self.assertIn(".ob-industry-card.is-selected{", CSS)
        self.assertRegex(CSS, r"\.ob-industry-card\.is-selected\{[^}]*box-shadow:0 0 0 3px var\(--rs-brand\)")
        self.assertIn(".ob-industry-card.is-selected .ob-ic-check{display:grid}", CSS)  # a visible check mark
        self.assertIn("ob-ic-check", self.html)
        # the JS reflects the selected name near the CTA and in the CTA label itself
        self.assertIn("confirmName.textContent", JS)
        self.assertIn("'نصبِ صنفِ «'", JS)

    def test_a_rejected_submit_keeps_the_selection_checked(self):
        response = self.client.post(
            self.url("industry"), {"industry_template_id": self.template.pk}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertRegex(html, rf'name="industry_template_id" value="{self.template.pk}" checked')
        self.assertIn("برای نصب باید کادرِ تأییدِ بالا را علامت بزنید", html)


class IndustryResponsiveCssTests(JourneyBase):
    def test_desktop_is_a_4_column_grid_then_3_then_2_then_1_without_a_scroll_box(self):
        self.assertRegex(CSS, r"\.ob-industry-list\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)")
        self.assertRegex(CSS, r"@media\(max-width:1100px\)\{\.ob-industry-list\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}\}")
        self.assertRegex(CSS, r"@media\(max-width:820px\)\{\.ob-industry-list\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}\}")
        self.assertRegex(CSS, r"@media\(max-width:560px\)\{\s*\.ob-industry-list\{grid-template-columns:1fr\}")  # 390px: one column
        rule = re.search(r"\.ob-industry-list\{[^}]*\}", CSS).group(0)
        for forbidden in ("max-height", "overflow:auto", "overflow-y"):
            self.assertNotIn(forbidden, rule)  # no nested scrolling list

    def test_the_confirmation_footer_is_sticky_only_on_wide_screens(self):
        self.assertRegex(CSS, r"@media\(min-width:961px\)\{\.ob-sticky-foot\{position:sticky;bottom:0")
        self.assertNotRegex(re.search(r"\.ob-sticky-foot \.ob-actions\{[^}]*\}", CSS).group(0), "position:")

    def test_cards_cannot_force_horizontal_overflow(self):
        self.assertIn("minmax(0,1fr)", CSS)  # grid tracks may shrink below their content
        self.assertRegex(CSS, r"\.ob-ic-desc\{[^}]*overflow:hidden")


class IndustryServerSideInvariantsTests(JourneyBase):
    def setUp(self):
        super().setUp()
        self.template = make_rich_template()

    def assertNothingInstalled(self):
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        self.assertEqual(Category.objects.filter(store=self.store).count(), 0)

    def test_only_the_exact_confirmation_value_installs(self):
        for bad in (None, "", "0", "on", "true", "True", "yes", "11", " 1x"):
            with self.subTest(confirm=bad):
                data = {"industry_template_id": self.template.pk}
                if bad is not None:
                    data["confirm_industry_install"] = bad
                response = self.client.post(self.url("industry"), data, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["confirm_error"])
                self.assertNothingInstalled()

    def test_exact_confirmation_installs_once_and_the_page_then_shows_the_installed_summary(self):
        response = self.client.post(
            self.url("industry"), {"industry_template_id": self.template.pk, "confirm_industry_install": "1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        count = Category.objects.filter(store=self.store).count()
        html = self.get("industry").content.decode()
        self.assertIn("ob-installed", html)
        self.assertNotIn("ob-industry-list", html)  # installed: summary + continue only, no re-selection
        again = self.client.post(
            self.url("industry"), {"industry_template_id": self.template.pk, "confirm_industry_install": "1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(again.status_code, 302)  # idempotent continue, never a second install
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)
        self.assertEqual(Category.objects.filter(store=self.store).count(), count)

    def test_skip_still_works_and_installs_nothing(self):
        response = self.client.post(self.url("industry"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/onboarding/template/", response["Location"])
        self.assertNothingInstalled()
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.TEMPLATE)

    def test_a_forged_unknown_or_non_offerable_id_cannot_install(self):
        skeletal = make_skeletal_template()
        for forged in (999999, skeletal.pk, "abc"):
            with self.subTest(forged=forged):
                response = self.client.post(
                    self.url("industry"), {"industry_template_id": forged, "confirm_industry_install": "1"},
                    HTTP_HOST=_HOST,
                )
                self.assertEqual(response.status_code, 200)
                self.assertNothingInstalled()
