"""Real Ready Template Gallery screenshots — «Rasti Mode Demo — COMPLETE
REAL CATALOG + MEDIA + CONTENT + THE ORIGINAL 8 READY TEMPLATE PREVIEWS»
mission (Steps 20-30).

This file tests the NEW real-screenshot resolution layer added to
``template_preview_service.py`` (``resolve_real_screenshot``,
``preview_content_hash``) and its Gallery-view integration — it does NOT
modify or duplicate ``test_acceptance_batch3.py``, whose 15 tests (the
pure-SVG schematic contract and the full no-mutation contract) must keep
passing byte-for-byte unchanged; see that file's own docstring.

The actual capture tool
(``apps.storefront_builder.management.commands.capture_ready_template_previews``)
is a dev/build-time-only script that requires a real running server and a
real browser — it is exercised manually (see the execution ledger for the
real capture run's evidence), not by this automated suite. What IS tested
here automatically:
  - the resolver's pure-filesystem contract (fresh vs. stale vs. missing)
  - that a normal Gallery request never imports/touches Playwright
  - that the currently-committed real screenshots (if present) satisfy
    the mission's structural requirements (one per official Template,
    correctly keyed, sourced from the Rasti Mode Demo capture workflow)
"""

import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import template_preview_service as tps
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-real-previews.rastisi.localhost"
READY_TEMPLATE_KEYS = (
    "dense_marketplace", "premium_leather", "warm_boutique", "fashion_promo_catalog",
    "playful_lifestyle", "utility_catalog", "editorial_jewelry", "dark_digital",
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RealScreenshotResolverTests(TestCase):
    """Pure filesystem-contract tests — no HTTP, no browser."""

    def test_original_eight_remain_a_subset_of_the_official_catalog(self):
        official_keys = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(len(official_keys), 50)
        self.assertTrue(set(READY_TEMPLATE_KEYS).issubset(official_keys))

    def test_missing_screenshot_falls_back_to_none(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(Path, "is_file", return_value=False):
            self.assertIsNone(tps.resolve_real_screenshot(preset))

    def test_stale_content_hash_is_rejected_not_silently_served(self):
        """Mission Step 24: 'do NOT silently show an old version
        screenshot' — a mismatched stored hash must safely refuse the
        file, never serve it as if it were current."""
        preset = lpr.get_layout_preset("dense_marketplace")
        real_relpath = tps.screenshot_relpath(preset.key, preset.version)
        real_image_path = tps.APP_STATIC_DIR / real_relpath

        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch("apps.storefront_builder.services.template_preview_service.json.loads",
                        return_value={"preview_input_fingerprint": "definitely-not-the-real-hash"}), \
             mock.patch.object(Path, "read_text", return_value="{}"):
            result = tps.resolve_real_screenshot(preset)
        self.assertIsNone(result)

    def test_matching_content_hash_resolves_the_expected_relpath(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        expected_relpath = tps.screenshot_relpath(preset.key, preset.version)
        real_fingerprint = tps.preview_input_fingerprint(preset)

        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": real_fingerprint})):
            result = tps.resolve_real_screenshot(preset)
        self.assertEqual(result, expected_relpath)

    def test_content_hash_changes_when_a_screenshot_visible_field_changes(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        original_hash = tps.preview_content_hash(preset)

        import copy
        mutated = copy.deepcopy(preset)
        mutated.appearance["density"] = "definitely-a-different-value"
        self.assertNotEqual(tps.preview_content_hash(mutated), original_hash)

    def test_content_hash_is_stable_across_repeated_calls(self):
        preset = lpr.get_layout_preset("warm_boutique")
        self.assertEqual(tps.preview_content_hash(preset), tps.preview_content_hash(preset))

    def test_screenshot_relpath_shape_matches_the_mission_spec(self):
        self.assertEqual(tps.screenshot_relpath("dense_marketplace", 1), "ready_template_previews/dense_marketplace/v1.webp")

    def test_f_resolve_real_screenshot_never_imports_playwright(self):
        """Structural proof of the no-browser-launch contract (Step 23) —
        the module may *mention* Playwright in prose (it documents the
        offline capture tool that produces the files it reads), but must
        contain no actual import statement for it, so a normal Gallery
        request cannot possibly trigger a browser launch."""
        import apps.storefront_builder.services.template_preview_service as module

        source = Path(module.__file__).read_text()
        for line in source.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith("import playwright"), line)
            self.assertFalse(stripped.startswith("from playwright"), line)
            self.assertFalse(stripped.startswith("import selenium"), line)
            self.assertFalse(stripped.startswith("from selenium"), line)


class PreviewInputFingerprintTests(TestCase):
    """Post-demo hardening pass, Issue 3 — stale-content tests A-F.

    ``preview_content_hash`` alone (Batch 3/the mission's original real-
    screenshot work) only covered the Template registry — it missed the
    real case of "Template unchanged, but the Demo Store's real catalog/
    media/content changed" (e.g. this mission's own Issue 2 multi-color
    rework). ``preview_input_fingerprint`` closes that gap; these tests
    mock the two underlying file hashes directly (never touching the real,
    possibly-committed screenshot/meta files on disk) to prove each
    required staleness case without any real capture/browser involved."""

    @staticmethod
    def _fake_file_hash(manifest_hash: str, seed_hash: str):
        def fake(path):
            if path == tps._DEMO_MEDIA_MANIFEST_PATH:
                return manifest_hash
            if path == tps._DEMO_SEED_COMMAND_PATH:
                return seed_hash
            raise AssertionError(f"unexpected path hashed: {path}")
        return fake

    def test_c_unchanged_inputs_resolve_normally(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s1")):
            fingerprint = tps.preview_input_fingerprint(preset)
            with mock.patch.object(Path, "is_file", return_value=True), \
                 mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": fingerprint})):
                self.assertEqual(tps.resolve_real_screenshot(preset), tps.screenshot_relpath(preset.key, preset.version))

    def test_a_same_template_version_but_changed_media_manifest_is_stale(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s1")):
            captured_fingerprint = tps.preview_input_fingerprint(preset)

        # Demo media manifest changed (e.g. Issue 2's multi-color rework) —
        # the Template registry (key/version) is completely untouched.
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m2-CHANGED", "s1")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": captured_fingerprint})):
            self.assertIsNone(tps.resolve_real_screenshot(preset))

    def test_b_same_template_version_but_changed_demo_catalog_content_is_stale(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s1")):
            captured_fingerprint = tps.preview_input_fingerprint(preset)

        # The seed command's own deterministic catalog/content definition
        # changed (new products, prices, hero/banner copy, ...) — again,
        # the Template registry itself is untouched.
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s2-CHANGED")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": captured_fingerprint})):
            self.assertIsNone(tps.resolve_real_screenshot(preset))

    def test_d_another_templates_screenshot_cannot_satisfy_the_current_template(self):
        preset_a = lpr.get_layout_preset("dense_marketplace")
        preset_b = lpr.get_layout_preset("warm_boutique")
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s1")):
            fingerprint_a = tps.preview_input_fingerprint(preset_a)

            with mock.patch.object(Path, "is_file", return_value=True), \
                 mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": fingerprint_a})):
                self.assertIsNone(tps.resolve_real_screenshot(preset_b))

    def test_e_stale_screenshot_falls_back_safely_to_the_svg_schematic(self):
        """See ``GalleryRealScreenshotIntegrationTests.test_every_card_renders_either_a_real_screenshot_or_the_svg_fallback``
        for the full HTTP-level proof; this unit-level check proves the
        resolver's own contract: stale (None) never raises, and the
        fallback SVG schematic is always independently available."""
        preset = lpr.get_layout_preset("dense_marketplace")
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m1", "s1")):
            captured_fingerprint = tps.preview_input_fingerprint(preset)
        with mock.patch.object(tps, "_file_hash", side_effect=self._fake_file_hash("m-STALE", "s1")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": captured_fingerprint})):
            self.assertIsNone(tps.resolve_real_screenshot(preset))
        fallback = tps.resolve_gallery_thumbnail(preset)
        self.assertTrue(fallback.startswith("<svg"))
        self.assertTrue(fallback.endswith("</svg>"))


class CommittedScreenshotIntegrityTests(TestCase):
    """If real screenshots have been captured and committed (the normal
    healthy state after running the capture command), verify they satisfy
    the mission's structural requirements. Skips gracefully if none are
    present yet (e.g. a fresh checkout before the first capture run)."""

    def _committed_keys(self):
        base = tps.APP_STATIC_DIR / "ready_template_previews"
        if not base.is_dir():
            return []
        return [p.name for p in base.iterdir() if p.is_dir()]

    def test_every_committed_screenshot_belongs_to_an_official_template(self):
        official_keys = {preset.key for preset in lpr.list_ready_templates()}
        for key in self._committed_keys():
            self.assertIn(key, official_keys, key)

    def test_every_committed_screenshot_has_a_meta_sidecar_from_rasti_mode_demo(self):
        keys = self._committed_keys()
        if not keys:
            self.skipTest("no real screenshots committed yet")
        checked_any = False
        for key in keys:
            preset = lpr.get_layout_preset(key)
            meta_path = tps.APP_STATIC_DIR / tps.meta_relpath(key, preset.version)
            if not meta_path.is_file():
                continue
            checked_any = True
            meta = json.loads(meta_path.read_text())
            self.assertEqual(meta["template_key"], key)
            self.assertEqual(meta["capture_source"], "rasti-mode-demo")
            self.assertEqual(meta["viewport"], {"width": 1440, "height": 1100})
        if not checked_any:
            self.skipTest("no current-version real screenshots committed yet")

    def test_every_official_template_resolves_its_committed_screenshot_as_fresh(self):
        if any(
            not (tps.APP_STATIC_DIR / tps.meta_relpath(key, lpr.get_layout_preset(key).version)).is_file()
            for key in READY_TEMPLATE_KEYS
        ):
            self.skipTest("not all current versions of the original 8 are captured yet")
        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            self.assertIsNotNone(tps.resolve_real_screenshot(preset), key)


class VersionedPreviewIdentityTests(TestCase):
    """Part 2B follow-up — merchant-side Windows QA found the committed
    ``fashion_promo_catalog`` preview stayed named/labeled version 1 while
    the registry had moved that Preset to ``version="2"`` (Part 2B's own
    Home-rebuild version bump). Root cause: ``screenshot_relpath``/
    ``meta_relpath`` used to default to a fixed, independent
    ``SCREENSHOT_VERSION`` module constant instead of the Preset's own
    ``version`` field. These tests prove the fix: the artifact identity
    (file path AND the ``"version"`` field inside its sidecar) now always
    tracks ``preset.version`` exactly, a stale lower-version file can never
    satisfy a bumped Preset, and the other 7 Ready Templates (whose
    ``version`` never moved) are provably unaffected."""

    def test_1_registry_version_2_resolves_the_v2_preview_path(self):
        # Part 2C precision pass bumped fashion_promo_catalog to version
        # "3" (a further real content change); the assertions below track
        # whatever the registry's CURRENT version actually is rather than
        # a second hardcoded literal, so this test keeps proving the same
        # invariant across future version bumps without needing its own
        # edit each time.
        preset = lpr.get_layout_preset("fashion_promo_catalog")
        expected = tps.screenshot_relpath(preset.key, preset.version)
        self.assertEqual(expected, f"ready_template_previews/fashion_promo_catalog/v{preset.version}.webp")

        real_fingerprint = tps.preview_input_fingerprint(preset)
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": real_fingerprint})):
            self.assertEqual(tps.resolve_real_screenshot(preset), expected)

    def test_2_metadata_version_equals_registry_version_for_every_committed_template(self):
        base = tps.APP_STATIC_DIR / "ready_template_previews"
        if not base.is_dir():
            self.skipTest("no real screenshots committed yet")
        checked_any = False
        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            meta_path = tps.APP_STATIC_DIR / tps.meta_relpath(key, preset.version)
            if not meta_path.is_file():
                continue
            checked_any = True
            meta = json.loads(meta_path.read_text())
            self.assertEqual(meta["version"], preset.version, key)
            self.assertEqual(meta["template_key"], key)
        if not checked_any:
            self.skipTest("no real screenshots committed yet")

    def test_3_a_v1_file_on_disk_is_stale_and_ignored_once_the_registry_is_v2(self):
        """Even if an old v1.webp/v1.meta.json physically exists (kept for
        historical retention — never deleted by this fix), a Preset now at
        a higher version must never resolve it: the resolver only ever
        looks at the CURRENT version's path, because that path is built
        from ``preset.version`` (now "3" after the Part 2C precision pass,
        but this test only needs "not the current version" to hold)."""
        preset = lpr.get_layout_preset("fashion_promo_catalog")
        self.assertNotEqual(preset.version, "1")

        def only_v1_exists(path_self):
            return "v1." in path_self.name

        with mock.patch.object(Path, "is_file", only_v1_exists):
            self.assertIsNone(tps.resolve_real_screenshot(preset))

    def test_4_missing_v2_falls_back_safely_to_the_svg_schematic(self):
        preset = lpr.get_layout_preset("fashion_promo_catalog")
        with mock.patch.object(Path, "is_file", return_value=False):
            self.assertIsNone(tps.resolve_real_screenshot(preset))
        fallback = tps.resolve_gallery_thumbnail(preset)
        self.assertTrue(fallback.startswith("<svg"))
        self.assertTrue(fallback.endswith("</svg>"))

    def test_5_current_v2_resolves_normally_when_actually_captured(self):
        preset = lpr.get_layout_preset("fashion_promo_catalog")
        expected = tps.screenshot_relpath(preset.key, preset.version)
        real_fingerprint = tps.preview_input_fingerprint(preset)
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=json.dumps({"preview_input_fingerprint": real_fingerprint})):
            self.assertEqual(tps.resolve_real_screenshot(preset), expected)

    def test_6_capture_command_source_derives_version_from_the_preset_not_a_constant(self):
        import apps.storefront_builder.management.commands.capture_ready_template_previews as cmd

        source = Path(cmd.__file__).read_text()
        self.assertIn("preset.version", source)
        self.assertNotIn("SCREENSHOT_VERSION", source)

    def test_9_only_reference_overhauled_templates_move_beyond_v1(self):
        # Every reference-driven family that has completed its Home rebuild
        # owns a bumped preview identity.  The remaining untouched Ready
        # Templates stay on their historical v1 artifact identity until
        # their own reference-driven pass begins.
        expected_versions = {
            "fashion_promo_catalog": "8",
            "warm_boutique": "3",
            "premium_leather": "3",
            "dense_marketplace": "3",
            "editorial_jewelry": "3",
            "dark_digital": "3",
            "playful_lifestyle": "2",
            "utility_catalog": "2",
        }
        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            expected_version = expected_versions.get(key, "1")
            self.assertEqual(preset.version, expected_version, key)
            self.assertEqual(
                tps.screenshot_relpath(preset.key, preset.version),
                f"ready_template_previews/{key}/v{expected_version}.webp",
                key,
            )

    def test_10_warm_boutique_historical_preview_cannot_satisfy_v3(self):
        preset = lpr.get_layout_preset("warm_boutique")
        self.assertEqual(preset.version, "3")

        def only_v2_exists(path_self):
            return "v2." in path_self.name

        with mock.patch.object(Path, "is_file", only_v2_exists):
            self.assertIsNone(tps.resolve_real_screenshot(preset))


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
class GalleryRealScreenshotIntegrationTests(TestCase):
    """HTTP-level integration — extends Batch 3's no-mutation contract to
    cover the new screenshot branch without touching that file."""

    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="real_preview_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="real_preview_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_gallery_page_never_imports_or_calls_playwright(self):
        """The whole request path (view + both preview-resolution
        branches) must be structurally incapable of launching a browser."""
        with mock.patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_every_card_renders_either_a_real_screenshot_or_the_svg_fallback(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for card in response.context["template_cards"]:
            self.assertIn(card["thumbnail_kind"], ("screenshot", "svg"))
            if card["thumbnail_kind"] == "screenshot":
                self.assertTrue(card["thumbnail_url"])
                self.assertIn("ready_template_previews", card["thumbnail_url"])
            else:
                self.assertTrue(card["thumbnail_svg"].startswith("<svg"))

    def test_gallery_get_still_creates_no_version_history_with_real_screenshots_present(self):
        """Re-proves Batch 3's Test G under the new code path."""
        from apps.storefront_builder.services import layout_service as svc

        svc.get_or_create_draft(self.store)
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        for _ in range(3):
            self.client.get(self.url)

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)

    def test_gallery_get_never_calls_apply_preset_with_screenshots_present(self):
        from apps.storefront_builder.services import layout_service as svc
        from apps.storefront_builder.services import preset_service

        svc.get_or_create_draft(self.store)
        with mock.patch.object(preset_service, "apply_preset") as mocked_apply, \
             mock.patch.object(preset_service, "apply_preset_with_checkpoint") as mocked_checkpoint:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        mocked_apply.assert_not_called()
        mocked_checkpoint.assert_not_called()

    def test_screenshot_click_opens_the_non_mutating_in_page_live_preview(self):
        """Mission Step 30: 'preview may open larger non-mutating view' —
        was originally a plain <a href> to the static image itself; P5-W5C
        (Ready Template Preview UX) supersedes that with the SAME
        non-mutating guarantee but a materially better merchant outcome —
        the screenshot now opens the real in-page live preview (large,
        Desktop/Tablet/Mobile, Demo/Merchant data) instead of the raw
        static image, per that phase's explicit product requirement
        ("clicking the screenshot ... should open the IN-PAGE preview
        experience"). The href still targets a plain, real, non-mutating
        GET URL (now the canonical live-preview route, still no view
        logic beyond what that already-non-mutating view does) — so this
        is a structural upgrade of Step 30's contract, not a relaxation of
        it: a no-JS browser still gets a working direct link, and a
        JS-enabled one gets the strictly richer in-page dialog
        (template_gallery_preview.js)."""
        response = self.client.get(self.url)
        content = response.content.decode()
        for card in response.context["template_cards"]:
            if card["thumbnail_kind"] == "screenshot":
                preview_url = reverse(
                    "dashboard:storefront-builder-template-live-preview",
                    kwargs={"key": card["preset"].key},
                )
                self.assertIn(f'data-tpl-preview-trigger', content)
                self.assertIn(f'data-tpl-preview-url-demo="{preview_url}"', content)
                self.assertIn(f'data-tpl-preview-url-merchant="{preview_url}?data=merchant"', content)


class CaptureCommandSafetyTests(TestCase):
    """The capture tool itself is dev/build-only and cannot be exercised
    end-to-end here (needs a real server + real browser), but its safety
    contract (fixed store slug, no CLI redirection) is structurally
    verifiable from its source, exactly like the seed command's own
    reset-safety tests."""

    def test_capture_command_hardcodes_the_demo_store_slug(self):
        import apps.storefront_builder.management.commands.capture_ready_template_previews as cmd

        self.assertEqual(cmd.STORE_SLUG, "rasti-mode-demo")

    def test_capture_command_exposes_no_store_targeting_argument(self):
        from apps.storefront_builder.management.commands.capture_ready_template_previews import Command

        parser = Command().create_parser("manage.py", "capture_ready_template_previews")
        dest_names = {action.dest for action in parser._actions}
        self.assertNotIn("store", dest_names)
        self.assertNotIn("store_slug", dest_names)
        self.assertNotIn("slug", dest_names)

    def test_capture_command_errors_clearly_when_demo_store_missing(self):
        from io import StringIO

        from django.core.management import CommandError, call_command

        Store.objects.filter(slug="rasti-mode-demo").delete()
        with self.assertRaises(CommandError):
            call_command("capture_ready_template_previews", stdout=StringIO())
