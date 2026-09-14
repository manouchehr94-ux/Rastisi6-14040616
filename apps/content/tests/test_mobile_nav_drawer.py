"""Phase 5 Task 5 (MDR) — accessible mobile navigation drawer + the shared
storefront overlay-mechanics primitive.

Source-contract tests (same style as
apps/storefront_builder/tests/test_u2a_global_header_system.py): the drawer
lives in the canonical public base layout and consumes the canonical
Menu/NAV_MOBILE authority (NO second menu source), and the reusable overlay
primitive owns ONLY generic mechanics (open/close/escape/backdrop/focus-trap/
focus-return/scroll-lock) with no domain data.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_BASE_HTML = Path(settings.BASE_DIR, "templates", "base.html")
_OVERLAY_JS = Path(settings.BASE_DIR, "apps", "core", "static", "js", "storefront_overlay.js")
_LAYOUT_CSS = Path(settings.BASE_DIR, "apps", "core", "static", "css", "layout.css")


class SharedOverlayPrimitiveTests(SimpleTestCase):
    def test_overlay_primitive_file_exists_and_registers_alpine_data(self):
        self.assertTrue(_OVERLAY_JS.exists(), "shared overlay primitive JS is missing")
        src = _OVERLAY_JS.read_text(encoding="utf-8")
        self.assertIn("alpine:init", src)
        self.assertIn("Alpine.data('sfbOverlay'", src)

    def test_overlay_primitive_owns_only_generic_mechanics(self):
        src = _OVERLAY_JS.read_text(encoding="utf-8")
        # Generic overlay mechanics present.
        self.assertIn("open", src)
        self.assertIn("close", src)
        self.assertIn("Escape", src)  # escape handling
        self.assertIn("focus", src.lower())  # focus containment/return
        self.assertIn("overflow", src.lower())  # body scroll lock
        # NO domain data leaked into the generic primitive.
        for banned in ("cart", "product", "price", "menu", "nav_", "quantity"):
            self.assertNotIn(banned, src.lower(), f"overlay primitive must not own {banned}")

    def test_base_html_loads_the_overlay_primitive_before_alpine(self):
        src = _BASE_HTML.read_text(encoding="utf-8")
        self.assertIn("storefront_overlay.js", src)
        overlay_pos = src.index("storefront_overlay.js")
        alpine_pos = src.index("alpine.min.js")
        self.assertLess(overlay_pos, alpine_pos, "overlay JS must load before Alpine so alpine:init sees it")


class MobileNavDrawerTests(SimpleTestCase):
    def setUp(self):
        self.src = _BASE_HTML.read_text(encoding="utf-8")

    def test_burger_exposes_accessible_expanded_state_and_controls_drawer(self):
        self.assertIn("aria-expanded", self.src)
        self.assertIn("aria-controls=\"mobile-nav-drawer\"", self.src)

    def test_drawer_element_exists_with_dialog_semantics(self):
        self.assertIn('id="mobile-nav-drawer"', self.src)
        self.assertIn('role="dialog"', self.src)
        self.assertIn('aria-modal="true"', self.src)
        # Reuses the shared overlay primitive (not a bespoke open/close copy).
        self.assertIn("sfbOverlay", self.src)

    def test_drawer_has_explicit_close_control_and_backdrop(self):
        drawer_start = self.src.index('id="mobile-nav-drawer"')
        drawer_chunk = self.src[drawer_start - 400:drawer_start + 2000]
        self.assertIn("backdrop", drawer_chunk.lower())
        # An explicit close button with an accessible label.
        self.assertIn("بستن", drawer_chunk)

    def test_drawer_consumes_canonical_nav_mobile_with_header_fallback(self):
        drawer_start = self.src.index('id="mobile-nav-drawer"')
        drawer_chunk = self.src[drawer_start:drawer_start + 2500]
        # Canonical menu authority — NAV_MOBILE (falling back to NAV_HEADER).
        self.assertIn("NAV_MOBILE", drawer_chunk)
        self.assertIn("NAV_HEADER", drawer_chunk)
        # It must NOT query a second menu source or hard-code menu items.
        self.assertNotIn("Menu.objects", drawer_chunk)

    def test_desktop_nav_still_present_unchanged(self):
        # The existing desktop <nav class="nav"> is preserved (not removed).
        self.assertIn('<nav class="nav"', self.src)

    def test_drawer_css_is_offcanvas_and_rtl_safe(self):
        css = _LAYOUT_CSS.read_text(encoding="utf-8")
        self.assertIn("mobile-nav-drawer", css)
        # RTL-safe: uses logical inset properties, not hard-coded left/right geometry.
        self.assertTrue(
            "inset-inline" in css or "inset-block" in css,
            "drawer should use logical CSS properties for RTL safety",
        )
