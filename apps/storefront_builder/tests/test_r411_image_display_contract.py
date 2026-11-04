"""R4-11 — every storefront picture goes through ONE display contract (role -> fit/position/frame), checked structurally.

No literal ``object-fit`` may bypass the contract, no storefront ``<img>`` may lack a role, and the table in
``image_display`` must match the CSS and the section capabilities."""

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder import design_block, image_display, section_registry
from apps.storefront_builder.tests._catalog_count import READY_TEMPLATE_COUNT

APPS = Path(__file__).resolve().parents[2]
BUILDER_CSS = (APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
LAYOUT_CSS = (APPS / "core" / "static" / "css" / "layout.css").read_text(encoding="utf-8")  # loaded by every storefront page
STOREFRONT_CSS = [
    APPS / "storefront_builder" / "static" / "css" / "storefront_builder.css",
    APPS / "catalog" / "static" / "css" / "product_card.css",
    APPS / "catalog" / "static" / "css" / "product_detail.css",
    APPS / "catalog" / "static" / "css" / "home.css",
    APPS / "cart" / "static" / "css" / "cart.css",
    APPS / "cart" / "static" / "css" / "cart_preview.css",
    APPS / "core" / "static" / "css" / "tokens.css",
    APPS / "core" / "static" / "css" / "layout.css",
]
STOREFRONT_TEMPLATE_DIRS = [
    APPS / "storefront_builder" / "templates" / "storefront_builder" / "sections",
    APPS / "storefront_builder" / "templates" / "storefront_builder" / "partials",
    APPS / "catalog" / "templates" / "catalog",
    APPS / "cart" / "templates" / "cart",
    APPS / "orders" / "templates" / "orders",
    APPS / "blog" / "templates" / "blog",
]
IMG_TAG = re.compile(r"<img\b[^>]*>", re.S)
ROLE_ATTR = re.compile(r'data-img-role="([a-z-]+)"')


def _templates():
    for base in STOREFRONT_TEMPLATE_DIRS:
        yield from base.rglob("*.html")


class EveryImageDeclaresARoleTests(SimpleTestCase):
    def test_every_storefront_img_has_a_known_role(self):
        missing, unknown, seen = [], [], set()
        for path in _templates():
            for tag in IMG_TAG.findall(path.read_text(encoding="utf-8")):
                role = ROLE_ATTR.search(tag)
                if not role:
                    missing.append(f"{path.relative_to(APPS)}: {tag[:90]}")
                elif role.group(1) not in image_display.IMAGE_ROLES:
                    unknown.append(f"{path.relative_to(APPS)}: {role.group(1)}")
                else:
                    seen.add(role.group(1))
        self.assertEqual(missing, [], "storefront <img> without data-img-role")
        self.assertEqual(unknown, [])
        self.assertEqual(seen, set(image_display.IMAGE_ROLES), "a role in the table is used by no template (or vice versa)")

    def test_no_template_sets_object_fit_inline(self):
        offenders = [str(p.relative_to(APPS)) for p in _templates() if re.search(r"style=\"[^\"]*object-fit", p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [], "an inline object-fit bypasses the image contract")


class CssImplementsTheTableTests(SimpleTestCase):
    def test_no_literal_object_fit_outside_the_contract(self):
        offenders = []
        for path in STOREFRONT_CSS:
            css = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
            for match in re.finditer(r"object-fit\s*:\s*([^;}]+)", css):
                value = match.group(1).strip()
                if not value.startswith("var(--img-fit") and value not in {"inherit", "unset", "initial"}:
                    offenders.append(f"{path.name}: object-fit:{value}")
        self.assertEqual(offenders, [], "object-fit must read var(--img-fit, <role default>)")

    def test_each_role_default_matches_the_table(self):
        for key, role in image_display.IMAGE_ROLES.items():
            rule = next((m for m in re.finditer(r"([^{}]*img\[data-img-role=\"%s\"\][^{}]*)\{([^{}]*)\}" % key, LAYOUT_CSS)
                         if "object-fit:var(--img-fit," in m.group(2) and m.group(1).strip().startswith("img[")), None)
            self.assertIsNotNone(rule, f"no default rule for role {key}")
            self.assertIn(f"object-fit:var(--img-fit,{role.fit})", rule.group(2), key)

    def test_section_design_flags_feed_the_contract_variables(self):
        for flag, var in (("ratio", "--img-ratio"), ("fit", "--img-fit"), ("pos", "--img-pos")):
            self.assertIn(f'.rsec[data-d~="{flag}"]{{{var}:var(--d-{flag})}}', BUILDER_CSS)

    def test_product_frames_fill_absolutely_so_a_natural_ratio_can_not_leak(self):
        card = (APPS / "catalog" / "static" / "css" / "product_card.css").read_text(encoding="utf-8")
        self.assertRegex(card, r'\.pcard \.img>img\[data-img-role="product"\]\{position:absolute;inset:0;width:100%;height:100%')
        detail = (APPS / "catalog" / "static" / "css" / "product_detail.css").read_text(encoding="utf-8")
        self.assertRegex(detail, r"\.gallery \.main>img\[data-img-role\]\{position:absolute;inset:0;width:100%;height:100%")


class DesignStudioControlsTests(SimpleTestCase):
    CAPS = {"fit": "design_image_fit", "position": "design_image_position", "ratio": "design_image_ratio", "zoom": "design_image_zoom"}

    def test_sections_offer_exactly_the_registered_image_controls(self):
        for key, controls in image_display.IMAGE_CONTROLS_BY_SECTION.items():
            definition = section_registry.get_definition(key)
            have = {name for name, cap in self.CAPS.items() if definition.supports_capability(cap)}
            self.assertEqual(have, set(controls), key)

    def test_controls_use_plain_persian_choices_with_a_smart_default(self):
        self.assertEqual(design_block._FIT_CHOICES[0][0], "")
        self.assertEqual({v for v, _ in design_block._FIT_CHOICES}, {"", "contain", "cover"})
        labels = dict(design_block._FIT_CHOICES)
        self.assertEqual(labels["contain"], "نمایش کامل تصویر")
        self.assertEqual(labels["cover"], "پر کردن قاب")
        self.assertEqual({v for v, _ in design_block._POSITION_CHOICES}, {"", "center", "top", "bottom", "left", "right"})


from django.template.loader import render_to_string  # noqa: E402

from apps.storefront_builder import layout_preset_registry as lpr  # noqa: E402
from apps.storefront_builder.services import render_service  # noqa: E402

from .test_arch02_template_media_contract import MediaContractBase  # noqa: E402


class EveryReadyTemplateRendersOnlyContractImagesTests(MediaContractBase):
    """Structural check across ALL ready templates (not a visual one): whatever template is applied, every picture its home
    sections render carries a known role and no inline fit, so the one contract governs it."""

    def test_home_of_every_ready_template_renders_roles_only(self):
        problems, imgs, templates = [], 0, lpr.list_ready_templates()
        for preset in templates:
            self.switch(preset)
            for item in render_service.build_render_items(self.active_draft(), self.store):
                html = render_to_string(item["template_name"], item["context"])
                for tag in IMG_TAG.findall(html):
                    imgs += 1
                    role = ROLE_ATTR.search(tag)
                    if not role or role.group(1) not in image_display.IMAGE_ROLES:
                        problems.append((preset.key, item["section"].section_key, tag[:100]))
                    if re.search(r"object-fit", tag):
                        problems.append((preset.key, item["section"].section_key, "inline object-fit"))
        self.assertEqual(len(templates), READY_TEMPLATE_COUNT)
        self.assertGreater(imgs, 100, "the check must really have rendered pictures")
        self.assertEqual(problems, [])
