"""R4-09b — the colour picker must not depend on a stylesheet the browser may have cached before the patch.

Real-Windows QA (Firefox) showed BOTH the native colour control and an unstyled picker: the new script ran against an OLD
cached r4_studio.css (Django serves static files with ``Last-Modified`` only, so browsers apply heuristic freshness).
Fixed at the root, not around it:

* every Studio asset URL carries a content hash (``static_v``) — a changed file is a new URL, so script and stylesheet can
  never come from different releases;
* the picker has its OWN stylesheet (new URL) with selectors that also hold outside ``.rs-studio``;
* the script itself neutralises the native control (inline display:none!important, inert, not focusable, label-click and
  click guards) and gives the popover its layout-critical inline declarations, and loads its stylesheet itself if a sentinel
  rule is not applied — so a missing/stale stylesheet can no longer bring back the Windows dialog or an unpositioned popover.

The behaviour in real Firefox and Chromium (including a deliberately stale cached stylesheet) is in the QA evidence.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

import apps.storefront_builder as sfb_package
from apps.storefront_builder.templatetags import storefront_builder_extras as extras

from .test_r408_section_settings_contract import _Base

APP = Path(sfb_package.__file__).parent
STATIC = APP / "static" / "storefront_builder"
PICKER_JS = (STATIC / "r4_color_picker.js").read_text(encoding="utf-8")
PICKER_CSS = (STATIC / "r4_color_picker.css").read_text(encoding="utf-8")
STUDIO_CSS = (STATIC / "r4_studio.css").read_text(encoding="utf-8")
ASSETS = ("r4_editor.css", "r4_studio.css", "r4_color_picker.css", "r4_editor.js", "r4_color_picker.js", "r4_studio.js")


class StaticVersionTagTests(SimpleTestCase):
    def test_the_url_changes_exactly_when_the_file_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            asset = folder / "probe_asset.css"
            asset.write_text("a{color:red}", encoding="utf-8")
            with override_settings(
                STATICFILES_DIRS=[str(folder)],
                STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"],
            ):
                finders.get_finder.cache_clear()
                try:
                    first = extras.static_v("probe_asset.css")
                    again = extras.static_v("probe_asset.css")
                    self.assertRegex(first, r"\?v=[0-9a-f]{10}$")
                    self.assertEqual(first, again)
                    asset.write_text("a{color:blue}", encoding="utf-8")
                    later = os.stat(asset).st_mtime + 2
                    os.utime(asset, (later, later))
                    self.assertNotEqual(extras.static_v("probe_asset.css"), first)
                finally:
                    finders.get_finder.cache_clear()

    def test_a_file_the_finders_cannot_see_gets_the_plain_url_and_a_fingerprinted_url_is_untouched(self):
        self.assertNotIn("?", extras.static_v("storefront_builder/definitely_missing_file.css"))
        rendered = Template("{% load storefront_builder_extras %}{% static_v 'storefront_builder/r4_color_picker.css' %}").render(Context())
        self.assertRegex(rendered, r"r4_color_picker\.css\?v=[0-9a-f]{10}$")

    def test_the_hash_is_the_content_hash_of_the_served_file(self):
        url = extras.static_v("storefront_builder/r4_color_picker.css")
        expected = hashlib.sha1((STATIC / "r4_color_picker.css").read_bytes()).hexdigest()[:10]
        self.assertTrue(url.endswith("?v=" + expected), url)


class EditorPageAssetTests(_Base):
    def test_every_studio_asset_is_loaded_through_a_content_hashed_url(self):
        page = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        for name in ASSETS:
            self.assertRegex(page, rf"storefront_builder/{re.escape(name)}\?v=[0-9a-f]{{10}}", name)
            self.assertNotRegex(page, rf"storefront_builder/{re.escape(name)}[\"']", f"{name} must not be loaded un-versioned")
            expected = hashlib.sha1((STATIC / name).read_bytes()).hexdigest()[:10]
            self.assertIn(f"{name}?v={expected}", page, name)

    def test_the_picker_stylesheet_is_a_link_of_its_own_and_comes_after_the_studio_layer(self):
        page = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertLess(page.index("r4_studio.css?v="), page.index("r4_color_picker.css?v="))
        self.assertIn("data-r4-cp-css", page[page.index("r4_color_picker.css?v="):][:200])

    def test_the_inspector_that_hosts_the_colours_lives_inside_the_studio_root(self):
        page = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        root = page.index('class="r4-builder rs-studio"')
        self.assertLess(root, page.index('id="r4Inspector"'))
        self.assertLess(root, page.index('id="r4GlobalDesign"'))


class PickerStylesheetContractTests(SimpleTestCase):
    def test_the_picker_rules_left_the_studio_stylesheet(self):
        self.assertNotIn("r4-cp-", STUDIO_CSS)

    def test_every_rule_is_anchored_so_it_holds_inside_or_outside_the_studio_root(self):
        rules = re.findall(r"(?m)^([^\s@/}][^{]*)\{", PICKER_CSS)
        self.assertGreater(len(rules), 30)
        for selector in rules:
            for part in re.split(r",(?![^()]*\))", selector):
                part = part.strip()
                if part.startswith(".r4-cp-probe"):
                    continue
                self.assertTrue(part.startswith(":is(.rs-studio,html) "), part)

    def test_the_sentinel_and_the_hide_rules_exist(self):
        self.assertIn(".r4-cp-probe{--r4-cp-css:1", PICKER_CSS)
        self.assertRegex(PICKER_CSS, r"\.r4-cp-ready>select[^{]*\{display:none!important\}")

    def test_design_tokens_carry_fallbacks_for_a_host_without_the_studio_variables(self):
        self.assertEqual(re.findall(r"var\(--[a-z-]+\)", PICKER_CSS), [])


class PickerScriptRobustnessTests(SimpleTestCase):
    def test_the_native_control_is_neutralised_by_the_script_itself(self):
        block = PICKER_JS[PICKER_JS.index("function neutralise("):PICKER_JS.index("function stylesApplied()")]
        for needle in ("setProperty('display', 'none', 'important')", "tabIndex = -1", "aria-hidden", "inert"):
            self.assertIn(needle, block)
        # both kinds of control go through it
        enhance = PICKER_JS[PICKER_JS.index("function enhance("):PICKER_JS.index("function scan(")]
        self.assertEqual(enhance.count("neutralise("), 3)   # token select + custom input + a plain colour input

    def test_a_label_or_a_click_can_never_reach_the_native_dialog(self):
        guard = PICKER_JS[PICKER_JS.index("A <label for="):PICKER_JS.index("keep the triggers honest")]
        for needle in ("closest('[data-r4-cp-native]')", "evt.preventDefault()", "label.control", "openPicker(owner)", ", true);"):
            self.assertIn(needle, guard)
        trigger = PICKER_JS[PICKER_JS.index("button.addEventListener('click'"):][:400]
        self.assertIn("evt.preventDefault()", trigger)

    def test_the_popover_carries_its_layout_critical_declarations_inline(self):
        block = PICKER_JS[PICKER_JS.index("var pop = el('div', 'r4-cp');"):][:900]
        for needle in ("position:fixed", "z-index:2147483000", "width:304px", "max-width:calc(100vw - 16px)", "max-height:calc(100dvh - 16px)", "overflow:auto"):
            self.assertIn(needle, block)
        place = PICKER_JS[PICKER_JS.index("function place()"):][:1500]
        self.assertIn("pop.style.width = 'auto'", place)       # the phone sheet overrides the inline desktop width

    def test_it_loads_its_own_stylesheet_when_the_sentinel_is_not_applied(self):
        self.assertIn("--r4-cp-css", PICKER_JS)
        ensure = PICKER_JS[PICKER_JS.index("function ensureStyles()"):PICKER_JS.index("the trigger (what the merchant sees")]
        for needle in ("data-r4-cp-css-fallback", "'r4_color_picker.css'", "document.head.appendChild(link)", "SCRIPT_SRC"):
            self.assertIn(needle, ensure)
        self.assertIn("ensureStyles();", PICKER_JS[PICKER_JS.index("function start()"):][:200])
        self.assertIn("ensureStyles();", PICKER_JS[PICKER_JS.index("var pop = el('div', 'r4-cp');") - 80:][:120])
