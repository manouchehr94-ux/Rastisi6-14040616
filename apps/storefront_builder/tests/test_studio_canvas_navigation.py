"""The Studio's Preview document must keep its capture-phase navigation shield (links, forms, middle-click) and treat the Store header embedded
inside a Hero Stage like the shell header. Server-rendered checks only; the real-browser vectors live in ``test_hero_stage_browser``."""

from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase


class StudioCanvasNavigationShieldTests(StorefrontBuilderViewsTestCase):
    def _preview(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_shield_also_covers_text_node_targets_area_and_svg_links(self):
        html = self._preview()
        self.assertIn("evt.target.nodeType === 3 ? evt.target.parentElement : evt.target", html)      # Firefox: a click can target a text node
        self.assertIn("target.closest('a, area[href]')", html)
        for event in ("click", "auxclick"):
            self.assertIn(f"document.addEventListener('{event}', blockEmbeddedNavigation, true)", html)
        self.assertIn("document.addEventListener('submit', function (evt)", html)

    def test_the_header_embedded_in_a_stage_opens_the_header_settings(self):
        html = self._preview()
        self.assertIn("target.closest('.hs-header')", html)
        self.assertIn("sfb:openHeaderSettings", html)

    def test_the_shield_is_inert_outside_the_studio_frame(self):
        html = self._preview()
        self.assertIn("if (!inParentFrame) return;", html)             # the same document opened on its own keeps working links
