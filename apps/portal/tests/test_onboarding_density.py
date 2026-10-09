"""Onboarding vertical density — lightweight structural regression guards.

The real acceptance is browser QA at 1366×768 / 1440×900 / 390px (see the task report); these tests only stop the
specific causes of the old wasted space from coming back: tall header, 36px page top padding, a title + long lead +
tall two-line stepper before the first control, and any fixed-height / viewport-height layout that could clip content
or validation errors.
"""

import re
from pathlib import Path

import apps.portal as portal_app_module
from apps.portal.tests.test_onboarding_journey import JourneyBase

_BASE = Path(portal_app_module.__file__).resolve().parent
CSS = (_BASE / "static/portal/css/onboarding.css").read_text(encoding="utf-8")
WIZARD = (_BASE / "templates/portal/onboarding/_wizard_head.html").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\{([^}]*)\}", CSS)
    assert match, selector
    return match.group(1)


def px(declarations: str, prop: str) -> int:
    return int(re.search(prop + r":(\d+)px", declarations).group(1))


class DesktopSpacingTests(JourneyBase):
    def test_the_header_is_compact(self):
        self.assertLessEqual(px(rule(".ob-header-inner"), "height"), 56)

    def test_the_old_excessive_page_padding_does_not_return(self):
        page = rule(".ob-page")
        self.assertNotIn("36px 0 72px", page)
        self.assertRegex(page, r"padding:(\d+)px 0 (\d+)px")
        top = int(re.search(r"padding:(\d+)px 0", page).group(1))
        self.assertLessEqual(top, 16)

    def test_title_and_stepper_share_one_row_and_there_is_no_long_lead_before_the_first_control(self):
        self.assertIn("display:flex", rule(".ob-wizard"))
        self.assertNotIn("ob-lead", WIZARD)
        self.assertEqual(WIZARD.count("<h1"), 1)
        self.assertIn('class="ob-wizard"', WIZARD)

    def test_the_desktop_stepper_is_a_single_compact_row(self):
        steps = rule(".ob-steps")
        self.assertIn("display:flex", steps)
        self.assertNotIn("flex-direction:column", rule(".ob-step-link"))  # label beside the dot, not under it
        self.assertLessEqual(px(rule(".ob-step-dot"), "width"), 30)
        self.assertLessEqual(px(rule(".ob-step-dot"), "height"), 30)
        self.assertNotIn(".ob-step::before", CSS)  # the old absolutely-positioned tall connector is gone

    def test_card_and_form_rhythm_is_tight_but_not_cramped(self):
        self.assertLessEqual(px(rule(".ob-card"), "padding"), 24)
        self.assertLessEqual(px(rule(".ob-card-head"), "margin-bottom"), 16)
        self.assertLessEqual(px(rule(".ob-actions"), "margin-top"), 20)
        self.assertGreaterEqual(px(rule(".ob-btn"), "min-height"), 44)  # still a comfortable tap target
        self.assertGreaterEqual(px(re.search(r"\.ob-field input\[type=text\][^{]*\{([^}]*)\}", CSS).group(1), "min-height"), 44)
        self.assertGreaterEqual(int(re.search(r"font-size:(\d+(?:\.\d+)?)px", rule(".ob-card-head p")).group(1)), 14)  # readable body text


class ResponsiveTests(JourneyBase):
    def test_narrow_screens_stack_the_title_above_the_stepper(self):
        self.assertRegex(CSS, r"@media\(max-width:960px\)\{\s*\.ob-wizard\{flex-direction:column")

    def test_mobile_shows_a_current_step_summary_and_keeps_every_label_for_assistive_tech(self):
        block = CSS[CSS.index("@media(max-width:720px){\n  .ob-header-inner"):]
        block = block[:block.index("\n}\n") + 3]
        self.assertIn(".ob-progress-summary{display:block}", block)
        hidden = re.search(r"\.ob-step:not\(\.is-current\) \.ob-step-text\{([^}]*)\}", block).group(1)
        self.assertIn("clip:rect(0 0 0 0)", hidden)  # visually hidden …
        self.assertNotIn("display:none", hidden)  # … but still in the accessibility tree
        self.assertGreaterEqual(int(re.search(r"\.ob-step-link\{min-height:(\d+)px", block).group(1)), 44)

    def test_every_step_page_has_one_h1_a_labelled_progress_nav_and_one_current_step(self):
        for stage in ("identity", "industry", "template", "branding", "review"):
            with self.subTest(stage=stage):
                self.set_stage(stage)
                html = self.get(stage).content.decode()
                self.assertEqual(html.count("<h1"), 1)
                self.assertIn('aria-label="مراحل راه‌اندازی"', html)
                self.assertEqual(html.count('aria-current="step"'), 1)
                self.assertIn('class="ob-progress-summary"', html)


class NoClippingTests(JourneyBase):
    def test_no_viewport_height_layouts_outside_the_lightbox(self):
        outside = re.sub(r"\.ob-lightbox[^{]*\{[^}]*\}", "", CSS)
        self.assertNotRegex(outside, r"\d+vh")
        self.assertNotIn("100dvh", outside)

    def test_content_containers_have_no_fixed_height_or_hidden_overflow(self):
        for selector in (".ob-page", ".ob-card", ".ob-card-head", ".ob-wizard", ".ob-progress", ".ob-actions", ".ob-field"):
            declarations = rule(selector)
            with self.subTest(selector=selector):
                self.assertNotRegex(declarations, r"(?<![-\w])height:\s*\d")
                self.assertNotRegex(declarations, r"(?<![-\w])max-height:")
                self.assertNotIn("overflow:hidden", declarations)

    def test_no_transform_or_negative_margin_hacks(self):
        self.assertNotIn("translateY", CSS)
        negatives = re.findall(r"margin(?:-[a-z]+)?:\s*-\s*\d+px", CSS)
        # only the visually-hidden helper (margin:-1px) and the sticky bar's 1px bleed are allowed
        self.assertTrue(all(n.replace(" ", "") in {"margin:-1px", "margin-inline:-1px"} for n in negatives), negatives)

    def test_only_the_template_gallery_has_a_sticky_action_bar(self):
        self.assertNotIn("position:sticky", rule(".ob-actions"))
        self.assertIn(".ob-page--gallery .ob-actions{position:sticky;bottom:0", CSS)
