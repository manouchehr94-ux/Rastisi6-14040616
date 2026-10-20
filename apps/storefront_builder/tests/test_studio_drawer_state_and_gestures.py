"""Static contract for the drawer state machine and the Preview's direct-edit gestures (real-browser proof lives in
``test_studio_direct_edit_browser.py``, opt-in).

Blank-drawer bug (owner-reported, intermittent): R4.openSection() hides Global Design (``#r4GlobalDesign``) *before* its Inspector
fetch returns, but the Studio stayed in ``mode='global'`` with the drawer open — a visible drawer whose only view had no content (and
for good if the fetch failed). Root cause = two state owners (Studio ``ui.mode``/``ui.panelVisible`` vs R4's own hidden flag) with
no invariant between them. Fix = ONE presentation authority (``resolveDrawerView``) + the ``r4:global-closed`` event + a defensive
"unavailable view closes the drawer" rule + a structure refresh that can never swap in an empty shell."""

import re
from pathlib import Path

from django.urls import reverse

from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
PREVIEW = (APP / "templates" / "storefront_builder" / "preview.html").read_text(encoding="utf-8")
PREVIEW_CSS = (APP / "static" / "css" / "storefront_builder_preview_v22.css").read_text(encoding="utf-8")


class DrawerStateMachineContractTests(_BandBase):
    def test_one_presentation_authority_derives_every_drawer_signal(self):
        render = STUDIO_JS[STUDIO_JS.index("function renderChrome()"):STUDIO_JS.index("renderDrawerFocus();")]
        self.assertEqual(render.count("var drawerView = resolveDrawerView();"), 1)
        for derived in ("contextPanel.classList.toggle('panel-visible', drawerView !== null)",
                        "root.dataset.rsDrawer = drawerView || 'closed'",
                        "view.hidden = view.getAttribute('data-rs-view') !== drawerView"):
            self.assertIn(derived, render)
        # the old split-brain forms are gone
        self.assertNotIn("ui.panelVisible && showPanel ? ui.mode", STUDIO_JS)
        self.assertNotIn("!(name === 'structure' && ui.mode === 'inspector')", STUDIO_JS)

    def test_unavailable_view_closes_the_drawer_instead_of_rendering_a_blank_shell(self):
        resolve = STUDIO_JS[STUDIO_JS.index("function resolveDrawerView()"):STUDIO_JS.index("function renderChrome()")]
        self.assertIn("ui.mode === 'inspector'", resolve)               # the workspace and the drawer are exclusive
        self.assertIn("ui.panelVisible = false", resolve)                # request dropped when the view has no content
        has_content = STUDIO_JS[STUDIO_JS.index("function drawerViewHasContent"):STUDIO_JS.index("function resolveDrawerView()")]
        for needle in ("[data-rs-structure-scroll] .tree-row", "R4.isGlobalDesignOpen()", "ui.previewTemplate"):
            self.assertIn(needle, has_content)

    def test_studio_follows_r4_when_r4_closes_global_design(self):
        handler = STUDIO_JS[STUDIO_JS.index("root.addEventListener('r4:global-closed'"):]
        handler = handler[:handler.index("});")]
        self.assertIn("ui.mode = 'structure'", handler)
        self.assertIn("ui.panelVisible = false", handler)

    def test_structure_refresh_can_never_swap_in_an_empty_shell(self):
        self.assertIn("freshStructure.querySelector('[data-rs-structure-scroll]')", EDITOR_JS)
        self.assertIn("R4.refreshStructure = function", EDITOR_JS)

    def test_legacy_structure_open_state_is_gone(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertNotIn("data-r4-structure-open", html)
        self.assertNotIn("r4StructureOpen", EDITOR_JS)
        self.assertNotIn("r4StructureToggle", EDITOR_JS)
        self.assertNotIn("data-r4-structure-open", STUDIO_JS)


class DirectEditGestureContractTests(_BandBase):
    def test_preview_layer_owns_the_gestures_and_reuses_the_canonical_messages(self):
        self.assertIn("var LONG_PRESS_MS = 550;", PREVIEW)
        self.assertIn("var LONG_PRESS_SLOP = 10;", PREVIEW)
        self.assertIn("'sfb:openSectionSettings'", PREVIEW)
        self.assertIn("'sfb:selectSection'", PREVIEW)
        # origin-restricted: never "*"
        self.assertNotRegex(PREVIEW, r"postMessage\([^;]*,\s*['\"]\*['\"]\s*\)")
        # identity from [data-section-id], never from CSS class names
        self.assertIn("closest('[data-section-id]')", PREVIEW)
        # mouse: single click selects, dblclick opens; touch/pen: tap selects, press-and-hold opens
        self.assertIn("if (lastPointerType !== 'mouse') return;", PREVIEW)
        self.assertIn("evt.pointerType === 'mouse'", PREVIEW)
        # cancellations
        for needle in ("pointermove", "'pointerup'", "'pointercancel'", "window.addEventListener('scroll', cancelPress, true)", "contextmenu"):
            self.assertIn(needle, PREVIEW)

    def test_entity_elements_are_ordinary_section_surface_inside_the_r4_studio(self):
        # the R4 Studio edits slides / categories / products through the section's settings (sfb:openEntityEditor is only
        # implemented by the legacy editor): inside #r4PreviewFrame an entity element must not be a dead zone for the gestures
        self.assertIn("window.frameElement.id === 'r4PreviewFrame'", PREVIEW)
        self.assertIn("function ownedByEntityEditor", PREVIEW)
        self.assertIn("!isStudioHost && !!(target && target.closest", PREVIEW)
        self.assertIn("builderMode !== 'edit' || isStudioHost) return false;", PREVIEW)

    def test_protected_interactive_controls(self):
        tags = re.search(r"var INTERACTIVE_TAGS = \{([^}]*)\}", PREVIEW).group(1)
        for tag in ("A", "BUTTON", "INPUT", "SELECT", "TEXTAREA", "LABEL", "SUMMARY", "VIDEO", "AUDIO", "IFRAME"):
            self.assertIn(f"{tag}: 1", tags)
        self.assertIn("isContentEditable", PREVIEW)
        self.assertIn("INTERACTIVE_ROLES", PREVIEW)
        self.assertIn("name.indexOf('@click') === 0", PREVIEW)      # Alpine-bound quantity controls / carousel arrows / card actions
        click = PREVIEW[PREVIEW.index("function interceptBuilderEditClick"):]
        click = click[:click.index("document.addEventListener('click', interceptBuilderEditClick, true);")]
        self.assertIn("if (isInteractive(target, section)) return;", click)
        # a single click only SELECTS (it used to open settings)
        self.assertIn("selectSectionElement(section);", click)
        self.assertNotIn("sfb:openSectionSettings", click)

    def test_studio_routes_select_and_open_through_the_canonical_pipeline(self):
        handler = EDITOR_JS[EDITOR_JS.index("if (type === 'sfb:selectSection')"):EDITOR_JS.index("if (type === 'sfb:sectionCommand')")]
        select, opened = handler.split("if (type === 'sfb:openSectionSettings')")
        self.assertNotIn("R4.openSection", select)                     # selection never opens settings
        self.assertIn("R4.openSection(sectionId)", opened)             # the SAME entry point the drawer's gear uses
        self.assertIn("r4:direct-edit", opened)
        self.assertIn("if (R4.previewSelect", STUDIO_JS + "if (R4.previewSelect")
        self.assertEqual(EDITOR_JS.count("R4.openSection = function"), 1)    # one authority, no second modal/selection path
        self.assertIn("r4:direct-edit", STUDIO_JS)                      # the Studio closes the drawer first

    def test_feedback_and_hint_wording(self):
        for needle in (".sfb-rsec-hold", ".sfb-rsec-ack", "-webkit-touch-callout: none"):
            self.assertIn(needle, PREVIEW_CSS)
        self.assertIn("یک‌بار کلیک برای انتخاب؛ دوبار کلیک برای تنظیمات", STUDIO_JS)
        self.assertIn("لمس برای انتخاب؛ نگه‌داشتن برای تنظیمات", STUDIO_JS)
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn("یک‌بار کلیک برای انتخاب؛ دوبار کلیک برای تنظیمات", html)
        self.assertNotIn("برای ویرایش، روی بخش موردنظر کلیک کنید", html + STUDIO_JS)
