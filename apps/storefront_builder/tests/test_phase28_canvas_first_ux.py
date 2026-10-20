from pathlib import Path



from .test_views import StorefrontBuilderViewsTestCase


class Phase28CanvasFirstUXTemplateTests(StorefrontBuilderViewsTestCase):
    """The older Phase 2.8 overlay-drawer contract is intentionally superseded
    by the approved V3 Free Layout prototype: both side panes are persistent on
    desktop and independently collapsible, while compact layouts keep the
    existing three-way mobile navigation.
    """


    def test_desktop_panels_follow_v3_persistent_three_column_contract(self):
        css = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "css"
            / "storefront_builder.css"
        ).read_text(encoding="utf-8")
        start = css.index("Storefront Builder V3 — Free Layout visual contract")
        v3 = css[start:]
        self.assertIn("display: grid;", v3)
        self.assertIn("grid-template-columns: 280px minmax(0, 1fr) 320px", v3)
        self.assertIn(".sfb-v3-sidebar-right", v3)
        self.assertIn(".sfb-v3-inspector", v3)
        self.assertIn(".sfb-v3-sidebar-collapsed", v3)
        self.assertIn(".sfb-v3-inspector-collapsed", v3)
        self.assertNotIn("sfb-overlay-drawer-open", v3)
