"""V5-FUNC-002 — a legitimate structural refusal (400, nothing written) must tell the merchant WHY.

Reproduced on real Django + the real Studio: moving a section past a locked neighbour or into a multi-section row is
refused by the server (``target_locked`` / ``row_layout_invalid`` …) with an empty ``message``; r4_editor.js only treats a
400 as a *known refusal* (precise Persian reason, saved state kept) when ``message`` is non-empty, so the merchant saw the
generic «ذخیره ناموفق». The server-side protective validation is unchanged; these tests pin that every refusal still
writes nothing and now carries a Persian reason."""

import re
import unittest

from .test_r4_vertical_slice import R4VerticalSliceTestCase
from ._v5_shell_support import EDITOR_JS

PERSIAN = re.compile(r"[؀-ۿ]")


class StructuralRefusalMessageTests(R4VerticalSliceTestCase):
    def _assert_refusal(self, mutation, code):
        starting_revision = self.draft.edit_revision
        response = self._post_json({"base_revision": starting_revision, "mutation": mutation})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertTrue(body["message"], f"{code} must carry a Persian reason")
        self.assertRegex(body["message"], PERSIAN)
        self.assertEqual(self._refresh_revision(), starting_revision)          # nothing written, revision untouched

    def test_move_past_locked_neighbour_explains_itself(self):
        section, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", is_locked=True)
        self._assert_refusal({"type": "section.move", "section_id": section.pk, "direction": "down"}, "target_locked")

    def test_move_of_locked_section_explains_itself(self):
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        self._place_new_section("faq")
        self._assert_refusal({"type": "section.move", "section_id": section.pk, "direction": "down"}, "section_locked")

    def test_move_that_would_split_a_multi_section_row_explains_itself(self):
        section, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        self._assert_refusal({"type": "section.move", "section_id": section.pk, "direction": "down"}, "row_layout_invalid")

    def test_move_at_the_page_boundary_explains_itself(self):
        section, _, _ = self._place_new_section("rich_text")
        self._assert_refusal({"type": "section.move", "section_id": section.pk, "direction": "up"}, "move_boundary")

    def test_move_into_locked_container_explains_itself(self):
        section, _, _ = self._place_new_section("rich_text")
        _, container_target, _ = self._place_new_section("faq")
        container_target.is_locked = True
        container_target.save(update_fields=["is_locked"])
        self._assert_refusal({"type": "section.move", "section_id": section.pk, "direction": "down"}, "target_container_locked")

    def test_stale_section_id_explains_itself(self):
        self._place_new_section("rich_text")
        self._assert_refusal({"type": "section.move", "section_id": 987654321, "direction": "up"}, "section_not_found")

    def test_a_valid_move_is_still_accepted_and_advances_the_revision_once(self):
        section, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)

    def test_a_stale_revision_is_still_a_conflict_not_a_refusal(self):
        section, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq")
        base = self._refresh_revision()
        mutation = {"type": "section.move", "section_id": section.pk, "direction": "down"}
        self.assertEqual(self._post_json({"base_revision": base, "mutation": mutation}).status_code, 200)
        response = self._post_json({"base_revision": base, "mutation": mutation})      # the same base replayed
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_revision")


class ClientRefusalContractTests(unittest.TestCase):
    """r4_editor.js (unchanged) treats a 400 WITH a message as a known refusal: saved state kept, reason shown; a 400
    without one is the generic failure. This pins that contract so the message text above is what the merchant sees."""

    def test_known_refusal_path_requires_a_message_and_keeps_the_saved_state(self):
        self.assertIn("if (result.status === 400 && result.body && result.body.code && result.body.message) {", EDITOR_JS)
        start = EDITOR_JS.index("function reportKnownRefusal(body, options) {")
        handler = EDITOR_JS[start:start + 500]
        self.assertIn("setSaveState('saved');", handler)
        self.assertIn("R4.notify(text)", handler)
