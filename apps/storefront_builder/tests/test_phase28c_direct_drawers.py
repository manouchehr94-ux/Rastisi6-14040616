from pathlib import Path

from django.test import SimpleTestCase



class Phase28CDirectDrawerStaticTests(SimpleTestCase):
    def test_v3_desktop_shell_has_no_offscreen_drawer_translation(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        start = css.index("Storefront Builder V3 — Free Layout visual contract")
        phase = css[start:]
        self.assertIn("grid-template-columns: 280px minmax(0, 1fr) 320px", phase)
        self.assertNotIn("translateX(104%)", phase)
        self.assertNotIn("translateX(-104%)", phase)
        self.assertNotIn("sfb-overlay-drawer-open", phase)
