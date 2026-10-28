"""RastiSi Vision Studio is a second presentation of the ONE R4 Studio session.

These tests prove the technical join, not the pixels: the route and its relative-endpoint aliases reach the very same R4 views
(so permission, tenant and Draft logic are the R4 ones), the page keeps the DOM contract r4_editor.js / r4_composer.js / r4_resize.js
rely on, the sidebar has its own «استودیو» entry that never shares an active state with the older tabs, and the old R4 route is untouched.
The real-browser proof (clicks, refresh, Undo/Redo, network log) lives in the opt-in Chromium run documented in the Vision report."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from apps.dashboard import navigation
from apps.dashboard import urls as dashboard_urls
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE, ROLE_PERMISSIONS
from apps.stores.models import Store, StoreMembership

from ._r4_support import r4_mutate
from .test_views import HOST, StorefrontBuilderViewsTestCase

User = get_user_model()

APP = Path(__file__).resolve().parents[1]
R4_JS = (APP / "static" / "storefront_builder" / "r4_editor.js").read_text(encoding="utf-8")

#: ids / hooks r4_editor.js, r4_composer.js, r4_resize.js, r4_announcement.js and r4_studio.js look up when they start
REQUIRED_IDS = (
    "r4Inspector", "r4PreviewFrame", "r4SaveState", "r4Structure", "r4GlobalDesign", "r4UndoButton", "r4RedoButton",
    "r4PublishButton", "r4PageSwitcherSelect", "r4SidebarToggle", "rsStudioData", "rsStudioIcons",
)
REQUIRED_SELECTORS = (
    ".rs-studio[data-r4-shell]", "[data-r4-device-switcher]", ".r4-preview-canvas", ".canvas", ".rs-app", "[data-rs-context-panel]",
    "[data-rs-workspace]", "[data-rs-workspace-dialog]", "[data-rs-modal-root]", "[data-rs-toast]", "[data-rs-structure-scroll]",
    "[data-rs-status-pill]", "[data-rs-save-feedback]", '[data-control="zoom"]', '[data-control="page"]',
    '[data-rastisi-action="publish"]', '[data-rastisi-action="open-add-section"]', "template[data-rs-add-section-template]",
)


def _relative_endpoints_of_r4_editor_js():
    """The relative paths r4_editor.js resolves against ``window.location.href`` (read from the source, not hard-coded)."""
    paths = set(re.findall(r"new URL\('([a-z][a-z\-/]*/)', window\.location\.href\)", R4_JS))
    paths |= set(re.findall(r"sendReplaceDraftAction\('([a-z][a-z\-/]*/)'", R4_JS))
    paths.add("sections/{pk}/inspector/")   # built as 'sections/' + sectionId + '/inspector/'
    assert "sections/' + sectionId + '/inspector/" in R4_JS
    return sorted(paths)


class VisionStudioTests(StorefrontBuilderViewsTestCase):
    def _vision(self, **params):
        return self.client.get(reverse("dashboard:vision-studio"), params)

    # ---- the page ---------------------------------------------------------------------------------------------------------------
    def test_the_route_renders_the_vision_template_with_the_r4_context(self):
        response = self._vision()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/vision/studio.html")
        self.assertTemplateNotUsed(response, "dashboard/storefront_builder/r4/editor.html")
        r4 = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        for key in ("draft", "r4_edit_revision", "page_type", "structure_items", "global_design", "studio"):
            self.assertIn(key, response.context)
        self.assertEqual(response.context["draft"].pk, r4.context["draft"].pk)
        self.assertEqual(response.context["r4_edit_revision"], r4.context["r4_edit_revision"])

    def test_the_old_r4_route_is_unchanged(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/storefront_builder/r4/editor.html")
        self.assertTemplateNotUsed(response, "dashboard/vision/studio.html")
        self.assertEqual(reverse("dashboard:storefront-builder-r4-editor"), "/admin-portal/storefront-builder/r4/")
        self.assertEqual(reverse("dashboard:vision-studio"), "/admin-portal/vision-studio/")

    def test_page_param_is_validated_like_r4_and_all_six_pages_open(self):
        for params in ({}, {"page": "not-a-page"}):
            self.assertEqual(self._vision(**params).context["page_type"], "home")
        for value, _label in StorefrontPage.PageType.choices:
            self.assertEqual(self._vision(page=value).context["page_type"], value)

    def test_the_dom_contract_the_r4_scripts_depend_on_is_present(self):
        soup = BeautifulSoup(self._vision().content.decode(), "html.parser")
        for dom_id in REQUIRED_IDS:
            self.assertIsNotNone(soup.find(id=dom_id), dom_id)
        for selector in REQUIRED_SELECTORS:
            self.assertIsNotNone(soup.select_one(selector), selector)
        shell = soup.select_one(".rs-studio[data-r4-shell]")
        for attr in ("data-edit-revision", "data-r4-draft-id", "data-r4-page-type", "data-rs-mode", "data-rs-device", "data-rs-draft-changed"):
            self.assertTrue(shell.has_attr(attr), attr)
        self.assertIn("vs", shell["class"])
        # the engine and its UI controller load unchanged, in the order r4_resize / r4_composer need (R4.studio exists before them)
        scripts = [s["src"].split("?")[0].rsplit("/", 1)[-1] for s in soup.find_all("script", src=True)]
        order = [s for s in scripts if s.startswith(("r4_", "vision"))]
        self.assertEqual(order, ["r4_editor.js", "r4_color_picker.js", "r4_studio.js", "r4_resize.js", "r4_composer.js", "r4_announcement.js", "vision.js"])
        data = json.loads(soup.find(id="rsStudioData").string)
        for key in ("layout_tree_url", "announcement_inspector_url", "draft_preview_url", "live_preview_url", "page_type"):
            self.assertIn(key, data)

    def test_the_structure_panel_and_global_design_are_the_real_r4_projections(self):
        soup = BeautifulSoup(self._vision().content.decode(), "html.parser")
        structure = soup.find(id="r4Structure")
        self.assertIsNotNone(structure.select_one("[data-rs-structure-scroll]"))
        self.assertIsNotNone(structure.select_one("template[data-rs-add-row-template]"))
        design = soup.find(id="r4GlobalDesign")
        self.assertIsNotNone(design.select_one('[data-r4-global-field="palette_slug"]'))
        self.assertIsNotNone(design.select_one("#rsGlobalHeader"))
        self.assertIsNotNone(design.select_one("#rsGlobalFooter"))

    def test_the_design_tab_lists_the_categories_and_the_modal_reuses_the_one_global_design_panel(self):
        html = self._vision().content.decode()
        soup = BeautifulSoup(html, "html.parser")
        categories = [button["data-vs-open-cat"] for button in soup.select('[data-vs-pane="design"] button[data-vs-open-cat]')]
        self.assertEqual(
            categories[:8], ["colors", "typography", "buttons", "shape", "images", "header", "footer", "bottom_nav"]
        )
        titles = [card.select_one("strong").get_text(strip=True) for card in soup.select('[data-vs-pane="design"] .vs-dcard')]
        self.assertEqual(titles[:3], ["برند و رنگ‌ها", "نوع نوشته و فونت‌ها", "دکمه‌ها"])
        # one real Global Design panel (no second form, no duplicated ids) inside the large dialog
        self.assertEqual(len(soup.select("#r4GlobalDesign")), 1)
        self.assertIsNotNone(soup.select_one('.vs-design-modal #r4GlobalDesign'))
        ids = [node["id"] for node in soup.find_all(id=True)]
        self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [], "no duplicated DOM ids")
        # the palette cards are drawn from the registry's own colours, handed over as data
        palettes = json.loads(soup.find(id="vsPalettes").string)
        self.assertGreaterEqual(len(palettes), 24)
        self.assertTrue(all(len(item["swatches"]) == 6 and all(item["swatches"]) for item in palettes))

    def test_unsupported_reference_settings_are_labelled_as_in_development_not_offered_as_controls(self):
        html = self._vision().content.decode()
        self.assertGreaterEqual(html.count("در دست توسعه"), 3)
        soup = BeautifulSoup(html, "html.parser")
        for pane in ("seo",):
            self.assertEqual(soup.select(f'[data-vs-pane="{pane}"] input, [data-vs-pane="{pane}"] textarea, [data-vs-pane="{pane}"] select'), [])
        self.assertNotIn("localStorage", (APP / "static" / "storefront_builder" / "vision" / "vision.js").read_text(encoding="utf-8"))

    # ---- the relative endpoints -------------------------------------------------------------------------------------------------
    def test_every_relative_endpoint_of_r4_editor_js_resolves_to_the_same_view_under_vision(self):
        vision = reverse("dashboard:vision-studio")
        r4 = reverse("dashboard:storefront-builder-r4-editor")
        endpoints = _relative_endpoints_of_r4_editor_js()
        self.assertGreaterEqual(len(endpoints), 9, endpoints)
        for rel in endpoints:
            rel = rel.replace("{pk}", "7")
            v = resolve(urljoin(vision, rel))
            r = resolve(urljoin(r4, rel))
            self.assertIs(v.func, r.func, rel)
            self.assertEqual(v.kwargs, r.kwargs, rel)

    def test_the_alias_table_covers_exactly_what_the_js_needs(self):
        needed = {p.replace("{pk}", "<int:pk>") for p in _relative_endpoints_of_r4_editor_js()}
        declared = {rel for rel, _view, _name in dashboard_urls.VISION_STUDIO_R4_ALIASES}
        self.assertEqual(needed, declared)
        for rel, view, name in dashboard_urls.VISION_STUDIO_R4_ALIASES:
            self.assertEqual(name[:len("vision-studio")], "vision-studio")
            self.assertFalse(name.startswith("storefront-builder-"))

    def test_server_provided_endpoints_stay_the_canonical_absolute_r4_urls(self):
        data = json.loads(BeautifulSoup(self._vision().content.decode(), "html.parser").find(id="rsStudioData").string)
        self.assertTrue(data["layout_tree_url"].startswith("/admin-portal/storefront-builder/r4/"))
        self.assertTrue(data["announcement_inspector_url"].startswith("/admin-portal/storefront-builder/r4/"))

    # ---- one Draft, one revision, one history --------------------------------------------------------------------------------
    def test_a_mutation_sent_to_the_vision_alias_writes_the_one_r4_draft(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        section = draft.get_page("home").sections.first()
        self.assertIsNotNone(section)
        before = draft.edit_revision
        response = self.client.post(
            reverse("dashboard:vision-studio-mutate"),
            data=json.dumps({"base_revision": before, "mutation": {"type": "section.toggle_active", "section_id": section.pk}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["new_revision"], before + 1)
        draft.refresh_from_db()
        self.assertEqual(draft.edit_revision, before + 1)
        # the R4 page and the Vision page show the very same revision and Draft
        for name in ("dashboard:storefront-builder-r4-editor", "dashboard:vision-studio"):
            soup = BeautifulSoup(self.client.get(reverse(name)).content.decode(), "html.parser")
            shell = soup.select_one("[data-r4-shell]")
            self.assertEqual(int(shell["data-edit-revision"]), before + 1, name)
            self.assertEqual(int(shell["data-r4-draft-id"]), draft.pk, name)
        # history and undo through the Vision alias use the same history
        undo = self.client.post(reverse("dashboard:vision-studio-history"), data=json.dumps({"command": "undo", "base_revision": before + 1}),
                                content_type="application/json")
        self.assertIn(undo.status_code, (200, 400), undo.content)   # R4's own contract answers; what matters is it reached R4's view
        self.assertNotEqual(undo.status_code, 404)

    def test_stale_revision_conflicts_through_vision_exactly_as_through_r4(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        section = draft.get_page("home").sections.first()
        body = json.dumps({"base_revision": draft.edit_revision + 5, "mutation": {"type": "section.toggle_active", "section_id": section.pk}})
        via_vision = self.client.post(reverse("dashboard:vision-studio-mutate"), data=body, content_type="application/json")
        via_r4 = self.client.post(reverse("dashboard:storefront-builder-r4-mutation"), data=body, content_type="application/json")
        self.assertEqual(via_vision.status_code, via_r4.status_code)
        self.assertEqual(via_vision.json().get("code"), via_r4.json().get("code"))

    def test_inspector_and_picker_aliases_serve_the_real_r4_responses(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        section = draft.get_page("home").sections.first()
        via_vision = self.client.get(reverse("dashboard:vision-studio-section-inspector", args=[section.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        via_r4 = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(via_vision.status_code, via_r4.status_code)
        self.assertEqual(via_vision.content, via_r4.content)
        picker = self.client.get(reverse("dashboard:vision-studio-resource-picker"), {"kind": "product"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(picker.status_code, self.client.get(
            reverse("dashboard:storefront-builder-r4-resource-picker"), {"kind": "product"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code)

    # ---- permission ---------------------------------------------------------------------------------------------------------------
    def test_permission_matches_r4_for_anonymous_and_for_a_role_without_storefront_layout(self):
        self.assertNotIn(STOREFRONT_LAYOUT_MANAGE, ROLE_PERMISSIONS[StoreMembership.Role.ANALYST])
        analyst = User.objects.create_user(username="vs_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        analyst_client = Client(HTTP_HOST=HOST)
        analyst_client.login(username="vs_analyst", password="pass12345")
        anon = Client(HTTP_HOST=HOST)
        pairs = [("dashboard:vision-studio", "dashboard:storefront-builder-r4-editor", None)]
        for rel, _view, name in dashboard_urls.VISION_STUDIO_R4_ALIASES:
            args = [1] if "<int:pk>" in rel else []
            r4_name = "dashboard:storefront-builder-r4-" + {
                "vision-studio-mutate": "mutation", "vision-studio-section-inspector": "section-inspector",
                "vision-studio-resource-picker": "resource-picker", "vision-studio-history": "history",
                "vision-studio-publish": "publish", "vision-studio-discard": "discard", "vision-studio-reset-page": "reset-page",
                "vision-studio-reset-storefront": "reset-storefront", "vision-studio-switch-template": "switch-template",
            }[name]
            pairs.append(("dashboard:" + name, r4_name, args))
        for vision_name, r4_name, args in pairs:
            for who, client in (("anonymous", anon), ("analyst", analyst_client)):
                for method in ("get", "post"):
                    a = getattr(client, method)(reverse(vision_name, args=args or None), **({"data": "{}", "content_type": "application/json"} if method == "post" else {}))
                    b = getattr(client, method)(reverse(r4_name, args=args or None), **({"data": "{}", "content_type": "application/json"} if method == "post" else {}))
                    self.assertEqual(a.status_code, b.status_code, f"{who} {method} {vision_name}")
                    self.assertNotEqual(a.status_code, 200 if method == "post" else -1)
        self.assertNotEqual(analyst_client.get(reverse("dashboard:vision-studio")).status_code, 200)
        self.assertNotEqual(anon.get(reverse("dashboard:vision-studio")).status_code, 200)

    # ---- tenant and draft isolation -----------------------------------------------------------------------------------------------
    def test_another_stores_owner_can_neither_open_nor_write_this_stores_vision_studio(self):
        from apps.core.models import ShopSettings

        other = Store.objects.create(name="فروشگاه ویژن ب", slug="vision-b", status=Store.Status.ACTIVE, admin_subdomain="vision-b")
        ShopSettings.provision_for(other)
        owner_b = User.objects.create_user(username="vs_owner_b", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other, user=owner_b, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        draft_a = svc.get_or_create_draft(self.store, user=self.staff)
        draft_b = svc.get_or_create_draft(other, user=owner_b)
        section_a = draft_a.get_page("home").sections.first()
        rev_a, rev_b = draft_a.edit_revision, draft_b.edit_revision

        # B's owner on A's host: never gets A's studio, never writes A's draft
        intruder = Client(HTTP_HOST=HOST)
        intruder.login(username="vs_owner_b", password="pass12345")
        self.assertNotEqual(intruder.get(reverse("dashboard:vision-studio")).status_code, 200)
        write = intruder.post(
            reverse("dashboard:vision-studio-mutate"),
            data=json.dumps({"base_revision": rev_a, "mutation": {"type": "section.toggle_active", "section_id": section_a.pk}}),
            content_type="application/json",
        )
        self.assertNotEqual(write.status_code, 200)
        draft_a.refresh_from_db()
        self.assertEqual(draft_a.edit_revision, rev_a)

        # B on B's own host sees B's draft, and an A section id means nothing there
        own = Client(HTTP_HOST="vision-b.rastisi.localhost")
        own.login(username="vs_owner_b", password="pass12345")
        page = own.get(reverse("dashboard:vision-studio"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["draft"].pk, draft_b.pk)
        cross = own.post(
            reverse("dashboard:vision-studio-mutate"),
            data=json.dumps({"base_revision": rev_b, "mutation": {"type": "section.toggle_active", "section_id": section_a.pk}}),
            content_type="application/json",
        )
        self.assertNotEqual(cross.status_code, 200)
        draft_b.refresh_from_db(); draft_a.refresh_from_db()
        self.assertEqual((draft_a.edit_revision, draft_b.edit_revision), (rev_a, rev_b))
        # and the published storefront is never touched by anything Vision does
        self.assertFalse(StorefrontLayoutVersion.objects.filter(layout__store=other, status=StorefrontLayoutVersion.Status.PUBLISHED).exists())


class VisionSidebarEntryTests(StorefrontBuilderViewsTestCase):
    def test_the_sidebar_has_its_own_one_click_studio_entry_for_a_permitted_user(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        soup = BeautifulSoup(response.content.decode(), "html.parser")
        link = soup.select_one('.sidebar nav.nav a.nav-item[data-section="studio"]')
        self.assertIsNotNone(link)
        self.assertEqual(link["href"], reverse("dashboard:vision-studio"))
        self.assertEqual(link.select_one(".nav-item-label").get_text(strip=True), "استودیو")

    def test_a_role_without_storefront_layout_does_not_see_it(self):
        analyst = User.objects.create_user(username="vs_nav_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="vs_nav_analyst", password="pass12345")
        soup = BeautifulSoup(client.get(reverse("dashboard:dashboard")).content.decode(), "html.parser")
        self.assertIsNone(soup.select_one('.sidebar nav.nav a.nav-item[data-section="studio"]'))

    def test_vision_and_the_older_tabs_never_share_an_active_state(self):
        self.assertEqual(navigation.resolve_active("vision-studio", {}, ""), ("studio", "vision-studio"))
        for name in ("vision-studio-mutate", "vision-studio-history", "vision-studio-section-inspector"):
            self.assertEqual(navigation.resolve_active(name, {}, "")[0], "studio", name)
        self.assertEqual(navigation.resolve_active("storefront-builder-r4-editor", {}, ""), ("store", "builder"))
        self.assertEqual(navigation.resolve_active("storefront-builder-r4-editor", {"panel": "appearance"}, ""), ("store", "appearance"))

    def test_the_older_store_tabs_are_still_there(self):
        store_tabs = [t.label for s in navigation.SECTIONS if s.key == "store" for t in s.tabs]
        self.assertIn("ظاهر و طراحی", store_tabs)
        self.assertIn("ساختار صفحه‌ها", store_tabs)
        soup = BeautifulSoup(self.client.get(reverse("dashboard:vision-studio")).content.decode(), "html.parser")
        active = soup.select('.sidebar nav.nav a.nav-item.active')
        self.assertEqual([a["data-section"] for a in active], ["studio"])
