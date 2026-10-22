"""V5-UI-006/007 — one term («افزودن بخش») and clear, non-overlapping add controls on the canvas.

Presentation only: markup under ``is_preview`` + builder-only CSS + dialog wording. The engine contracts (container.add / cell.add_section /
revision / history) are covered by test_v5_container_add; here we pin that nothing of this chrome can reach the public storefront."""

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import container_service, layout_service

from .test_r4_mutation_api import R4MutationApiTestCase

APP = Path(__file__).resolve().parents[1]
CONTAINERS = (APP / "templates/storefront_builder/partials/render_containers.html").read_text(encoding="utf-8")
BUILDER_CSS = (APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")
STUDIO_JS = (APP / "static/storefront_builder/r4_studio.js").read_text(encoding="utf-8")


def _strip(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class TerminologyTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.draft.get_page("home")
        container_service.ensure_page_containers(self.page)
        container = container_service.create_empty_container(self.page, "thirds")
        first = container.cells.order_by("order", "id").first()
        from apps.storefront_builder.services import section_structure_service as sss
        sss.add_section_to_cell(draft=self.draft, section_key="faq", cell_id=first.pk)

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()

    def test_preview_uses_one_term_for_both_controls(self):
        html = self._preview()
        self.assertIn("افزودن بخش به این خانه", html)                      # empty Cell
        self.assertIn("افزودن بخش دیگر", html)                              # Cell that already has a Block
        self.assertNotIn("افزودن کامپوننت", html)
        self.assertNotIn("افزودن محتوا", html)

    def test_each_empty_cell_names_itself_and_its_real_width_share(self):
        html = self._preview()
        tags = re.findall(r'<small>(خانه [^<]+)</small>', html)
        self.assertEqual(tags, ["خانه ۲ · ۴ از ۱۲ ستون", "خانه ۳ · ۴ از ۱۲ ستون"])      # Cell 1 holds the FAQ; 2 and 3 are empty (RTL: 1 = right)
        self.assertEqual(len(re.findall(r'data-empty-cell="\d+"', html)), 2)

    def test_the_level_tag_is_display_only_and_the_controls_still_target_their_own_cell(self):
        html = self._preview()
        self.assertRegex(html, r'<span class="sfb-container-tag" aria-hidden="true">چیدمان ۳ خانه‌ای</span>')
        for cell_id in re.findall(r'data-empty-cell="(\d+)"', html):
            self.assertRegex(html, r'class="rcontainer-cell sfb-empty-cell"[^>]*data-cell-id="%s"' % cell_id)

    def test_nothing_of_the_builder_chrome_reaches_the_published_storefront(self):
        from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context

        layout_service.publish(self.store, user=self.staff)

        class Request:
            pass

        context = build_universal_storefront_context(Request(), self.store, StorefrontPage.PageType.HOME)
        html = render_to_string("storefront_builder/partials/render_containers.html", {"render_containers": context["render_containers"], "is_preview": False})
        self.assertIn("rcontainer-cell", html)
        for marker in ("sfb-empty-cell", "sfb-cell-add-more", "sfb-container-tag", "sfb-rcontainer-toolbar", "data-empty-cell", "data-cell-add", "data-cell-id", "افزودن بخش", "افزودن کامپوننت", "چیدمان ۳ خانه‌ای"):
            self.assertNotIn(marker, html, marker)


class TemplateAndCssContractTests(R4MutationApiTestCase):
    def test_the_css_block_is_builder_only(self):
        block = _strip(BUILDER_CSS[BUILDER_CSS.index("/* V5-UI-006/007 — add-section controls"):])
        for rule in re.findall(r"([^{}]+)\{", block):
            for selector in (s.strip() for s in rule.split(",")):
                if not selector or selector.startswith("@"):
                    continue
                self.assertRegex(selector, r"sfb-|\.rcontainer-cell", selector)
        # the control that sits over content stays an absolute overlay; the empty-Cell control fills ONLY its own empty Cell
        more = re.search(r"\n\.sfb-cell-add-more \{([^}]*)\}", block).group(1)
        self.assertNotIn("position: static", more)
        self.assertIn("bottom: -7px;", more)
        empty = re.search(r"\n\.sfb-empty-cell-add \{([^}]*)\}", block).group(1)
        self.assertIn("position: absolute;", empty)
        self.assertIn("inset: 0;", empty)

    def test_no_new_js_write_path_and_the_dialog_uses_the_same_term(self):
        self.assertIn("title = 'افزودن بخش به این خانه';", STUDIO_JS)
        self.assertNotIn("افزودن کامپوننت", STUDIO_JS)
        self.assertNotIn("افزودن محتوا به این خانه", STUDIO_JS)
        self.assertEqual(len(re.findall(r"^\s+R4\.addSection\(", STUDIO_JS, flags=re.M)), 1)               # the ONE cell.add_section caller is unchanged
