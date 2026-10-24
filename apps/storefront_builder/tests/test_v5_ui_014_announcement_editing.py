"""V5-UI-014 — the announcement strip is selected and edited like any other Section of the Design Studio (click → standard toolbar →
«ویرایش» → the standard workspace), with ONE difference: it is fixed above the header (no move, no duplicate, no Cell).

Storage / authority are unchanged and asserted here: the data stays the Draft header_config, every change is ``header.update`` (one Revision,
Undo-able), no second Section/model/migration, nothing of the Studio reaches the published or customer-preview documents."""

import re
from pathlib import Path

from django.test import Client
from django.urls import reverse

from apps.storefront_builder import global_region_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service, r4_mutation_service
from apps.stores.models import StoreMembership

from . import test_v5_linked_image_announcement as linked_tests
from .test_media_views import HOST

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"


class _UI014Base(linked_tests._LinkedBase):
    def _header(self, **patch):
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        return r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=draft.edit_revision,
            mutation={"type": "header.update", "patch": patch},
        )

    def _draft(self):
        return layout_service.get_or_create_draft(self.store, user=self.staff)

    def _on(self, **extra):
        self._header(announcement_enabled=True, announcement_text="اطلاعیهٔ تست", **extra)


class BuilderPreviewSelectionContractTests(_UI014Base):
    def test_every_header_variant_has_exactly_one_selectable_strip_and_no_old_edit_button(self):
        self._on(announcement_link_url="/products/")
        for variant in global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION):
            with self.subTest(variant=variant.key):
                self._header(header_variant=variant.key)
                html = self._preview()
                self.assertEqual(html.count('data-section-id="announcement"'), 1, variant.key)
                self.assertEqual(html.count("data-builder-announcement"), 1, variant.key)
                self.assertIn('data-section-key="header_announcement"', html)
                self.assertNotIn("sfb-announcement-edit-button", html)           # the small «⚙ ویرایش» button is gone: one standard toolbar only

    def test_the_strip_is_not_a_second_section_and_is_never_in_the_structure(self):
        self._on()
        before = StorefrontSection.objects.count()
        self._preview()
        self.assertEqual(StorefrontSection.objects.count(), before)
        self.assertFalse(StorefrontSection.objects.filter(section_key__in=("header_announcement", "announcement")).exists())

    def test_switched_off_with_stored_content_keeps_a_selectable_builder_stand_in_only(self):
        self._on(announcement_image_alt="x")
        self._header(announcement_enabled=False)
        html = self._preview()
        self.assertEqual(html.count("data-builder-announcement-off"), 1)
        self.assertEqual(html.count('data-section-id="announcement"'), 1)
        self.assertIn("غیرفعال است", html)
        self.assertEqual(self._draft().header_config["announcement_text"], "اطلاعیهٔ تست")          # off = hidden, the data is kept
        # nothing configured and off: no stand-in
        self._header(announcement_text="", announcement_links=[])
        self.assertNotIn("data-builder-announcement", self._preview())

    def test_published_and_customer_preview_carry_no_builder_marker(self):
        self._on(announcement_link_url="/products/")
        draft_view = self.client.get(reverse("dashboard:storefront-builder-draft-preview")).content.decode()
        self.assertIn("اطلاعیهٔ تست", draft_view)
        for forbidden in ('data-section-id="announcement"', "data-builder-announcement", "sfb-builder-announcement", "sfb-rsec-selected"):
            self.assertNotIn(forbidden, draft_view, forbidden)


class AnnouncementWorkspaceTests(_UI014Base):
    URL = "dashboard:storefront-builder-r4-announcement-inspector"

    def _html(self):
        response = self.client.get(reverse(self.URL))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_standard_workspace_has_the_three_tabs_and_every_announcement_setting(self):
        self._on()
        html = self._html()
        self.assertEqual(re.findall(r'data-r4-tab="(\w+)"', html), ["content", "design", "advanced"])
        for marker in ("announcement_text", "announcement_image_asset_id", "announcement_image_alt", "announcement_image_side", "announcement_link_url",
                       "announcement_link_new_tab", "announcement_align", "announcement_pages", "announcement_enabled", "announcement_show_phone"):
            self.assertIn(f'data-r4-global-field="{marker}"', html, marker)
        for key in ("announce_bg", "announce_fg", "announce_image_size", "announce_height", "announce_padding"):
            self.assertIn(f'data-r4-geometry-prop="{key}"', html, key)
        self.assertIn("data-r4-ann-repeater", html)                                            # the extra links
        self.assertIn('data-r4-global-responsive-key="announcement_enabled"', html)         # desktop / tablet / mobile visibility
        self.assertIn('class="r4-ws-footer"', html)                                             # the standard footer of every workspace

    def test_no_placement_control_exists_in_the_workspace(self):
        html = self._html()
        for forbidden in ("data-rs-section-actions", "data-rs-move-cell", "section-up", "section-down", "section-duplicate", "section-remove",
                          "data-r4-structure-move", "data-r4-section-id", "cell.add_section", "section-lock", "toggle_locked"):
            self.assertNotIn(forbidden, html, forbidden)
        self.assertIn("جابه‌جایی، تکثیر و انتقال به خانهٔ چیدمان برای آن وجود ندارد", html)

    def test_it_is_read_only_manager_only_and_store_scoped(self):
        self._on()
        revision, history = self._draft().edit_revision, self._draft().edit_history_entries.count()
        self._html()
        draft = self._draft()
        self.assertEqual((draft.edit_revision, draft.edit_history_entries.count()), (revision, history))
        anonymous = Client(HTTP_HOST=HOST).get(reverse(self.URL))
        self.assertNotEqual(anonymous.status_code, 200)
        from django.contrib.auth import get_user_model

        outsider = get_user_model().objects.create_user(username="ui014_outsider", password="pass12345", is_staff=True)
        client = Client(HTTP_HOST=HOST)
        client.login(username="ui014_outsider", password="pass12345")
        self.assertNotEqual(client.get(reverse(self.URL)).status_code, 200)
        self.assertFalse(StoreMembership.objects.filter(user=outsider, store=self.store).exists())
        self.assertEqual(self.client.post(reverse(self.URL)).status_code, 405)

    def test_the_old_global_panel_block_is_only_an_entry_to_the_same_editor(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        panel = html.split('id="r4GlobalDesign"', 1)[1]
        self.assertIn('data-r4-announce-entry', panel)
        for duplicate in ('data-r4-global-field="announcement_text"', 'data-r4-global-field="announcement_link_url"', "r4GlobalAnnouncementText"):
            self.assertNotIn(duplicate, panel, duplicate)                                        # one place to edit: no divergent second set of controls

    def test_the_workspace_state_is_the_header_config_and_nothing_else(self):
        self._on(announcement_align="end", geometry={"announce_bg": "#102030", "announce_height": 48, "announce_padding": 8})
        html = self._html()
        self.assertIn('value="اطلاعیهٔ تست"', html)
        self.assertRegex(html, r'<option value="end" selected>')
        self.assertRegex(html, r'data-r4-global-geometry-key="announce_height"[^>]*value="48"')
        self.assertIn('data-r4-geometry-prop="announce_bg"', html)


class HeightAndPaddingTests(_UI014Base):
    def test_height_and_padding_stay_inside_the_allowed_range_and_reach_the_strip(self):
        self._on()
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self._header(geometry={"announce_height": "tall"})                                   # not a number: refused
        for sent, stored in ((31, 32), (121, 120), (40, 40)):
            self._header(geometry={"announce_height": sent})
            self.assertEqual(self._draft().header_config["geometry"]["announce_height"], stored)  # out of range: clamped to the allowed 32–120 (V5 six-site kit raised the ceiling from 72 for tall campaign strips)
        for sent, stored in ((17, 16), (-1, 0), (8, 8)):
            self._header(geometry={"announce_padding": sent})
            self.assertEqual(self._draft().header_config["geometry"]["announce_padding"], stored)
        self._header(geometry={"announce_height": 56, "announce_padding": 10})
        html = self._preview()
        self.assertIn("--ann-h:56px", html)
        self.assertIn("--ann-py:10px", html)
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn("min-height: var(--ann-h, 32px); padding-block: var(--ann-py, 4px)", css)
        self.assertIn("min-height: max(var(--ann-h, 36px), 36px)", css)                        # a phone strip is never below 36px

    def test_nothing_changes_for_a_strip_that_never_used_the_new_settings(self):
        self._on()
        html = self._preview()
        self.assertNotIn("--ann-h", html)
        self.assertNotIn("--ann-py", html)


class StudioScriptContractTests(_UI014Base):
    RESIZE = (STATIC / "r4_resize.js").read_text(encoding="utf-8")
    ANN = (STATIC / "r4_announcement.js").read_text(encoding="utf-8")

    def test_the_standard_toolbar_hides_move_and_duplicate_for_the_strip(self):
        body = self.RESIZE[self.RESIZE.index("function renderToolbar"):]
        body = body[:body.index("var tw = toolbar.offsetWidth")]
        self.assertIn("var isAnn = id === ANN;", body)
        self.assertIn("['duplicate', 'up', 'down', 'remove'].forEach", body)
        self.assertIn(".hidden = isAnn", body)
        self.assertIn("ann-toggle", body)
        # the toolbar actions for the strip: edit / on-off / close only
        click = self.RESIZE[self.RESIZE.index("if (id === ANN) {"):]
        click = click[:click.index("return;")]
        for allowed in ("action === 'edit'", "action === 'ann-toggle'", "action === 'close'"):
            self.assertIn(allowed, click)
        for forbidden in ("duplicate", "'up'", "'down'", "remove"):
            self.assertNotIn(forbidden, click, forbidden)
        self.assertIn("id !== ANN && !S.rowState(id)", self.RESIZE)                           # the strip is not a structure row: never cleared as «deleted»

    def test_the_strip_has_no_resize_handles_and_no_auto_chip(self):
        self.assertIn("id !== ANN && resizeAllowed()", self.RESIZE)
        self.assertIn("isAnn ? { height: false, width: false } : manualState(sec)", self.RESIZE)

    def test_selection_uses_the_preview_documents_own_messages_and_writes_use_header_update_only(self):
        for needle in ("'sfb:selectSection'", "'sfb:openSectionSettings'", "type: 'header.update'", "R4.enqueueMutation"):
            self.assertIn(needle, self.ANN, needle)
        self.assertNotIn("section.update_settings", self.ANN)
        preview = (APP / "templates" / "storefront_builder" / "preview.html").read_text(encoding="utf-8")
        self.assertNotIn("header_announcement", preview)                                       # the protected preview document is not touched
