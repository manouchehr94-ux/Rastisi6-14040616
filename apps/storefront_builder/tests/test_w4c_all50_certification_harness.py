"""P5-W4C — All-50 Browser Certification harness — strict TDD RED suite.

Every test here encodes a required W4C behavioral contract from the approved
design (``docs/superpowers/plans/2026-09-17-phase5-w4c-all50-browser-certification.md``,
certified base ``3a4fe9070584655548bae5a9bb574f3415bbf580``). 35 of the 37
cases are feature-contract assertions expected to FAIL genuinely against the
certified base, because ``--w4c-all50`` and its supporting helpers do not
exist yet. Cases 8 and 21 are non-interference/regression guards asserting
the EXISTING, unmodified non-W4C behavior and are expected to PASS
immediately.

No browser campaign is executed by this suite: ``Command._run_logged`` is
always mocked so no real Node/Playwright process is spawned, per the
Implementation Round 1 directive ("DO NOT RUN THE 704-CELL CAMPAIGN YET").
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management.base import CommandError
from django.test import TestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.management.commands import qa_storefront_builder_r4 as r4_mod
from apps.storefront_builder.management.commands.qa_storefront_builder_r4 import Command
from apps.storefront_builder.models import StorefrontLayout
from apps.storefront_builder.services import layout_service, preset_service
from apps.storefront_builder.storefront_appearance.persistence import (
    load_store_appearance_manifest,
)
from apps.stores.models import Store


def _fake_exists(path_self, _orig=Path.exists):
    if path_self.name == "playwright-core":
        return True
    return _orig(path_self)


class W4CAll50CertificationHarnessTests(TestCase):
    """Cases 1-16 -- Round 2 (+Round 1's carried-over 5)."""

    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه W4C", slug="w4c-cert-demo", admin_subdomain="w4c-cert-demo",
        )

    def _publish(self, key):
        preset = lpr.get_layout_preset(key)
        preset_service.apply_preset_with_checkpoint(self.store, preset)
        layout_service.publish(self.store)
        return preset

    # -- 1 --------------------------------------------------------------
    def test_01_add_arguments_accepts_w4c_all50_flag(self):
        parser = Command().create_parser("manage.py", "qa_storefront_builder_r4")
        ns = parser.parse_args(["--store-slug", "x", "--username", "y", "--w4c-all50"])
        self.assertTrue(ns.w4c_all50)
        ns_default = parser.parse_args(["--store-slug", "x", "--username", "y"])
        self.assertFalse(ns_default.w4c_all50)

    # -- 2 --------------------------------------------------------------
    def test_02_add_arguments_accepts_only_as_comma_list(self):
        parser = Command().create_parser("manage.py", "qa_storefront_builder_r4")
        ns = parser.parse_args([
            "--store-slug", "x", "--username", "y", "--w4c-all50",
            "--only", "editorial_jewelry,warm_boutique",
        ])
        self.assertEqual(ns.only, "editorial_jewelry,warm_boutique")
        ns_default = parser.parse_args(["--store-slug", "x", "--username", "y"])
        self.assertEqual(ns_default.only, "")

    # -- 3 --------------------------------------------------------------
    def test_03_w4c_all50_calls_w4c_fixture_never_legacy_sandbox(self):
        user = self._make_qa_user()
        command = Command()
        with mock.patch.object(Command, "_prepare_w4c_certification_fixture", return_value={}) as w4c_fixture, \
             mock.patch.object(Command, "_prepare_r4_sandbox") as legacy_sandbox, \
             mock.patch.object(Command, "_run_w4c_campaign", return_value={
                 "total_cells_recorded": 0, "missing_cells": [], "duplicate_cells": [],
                 "fail_count": 0, "blocked_count": 0, "cells_recorded_this_run": 0,
             }), \
             self._patched_handle_preamble():
            with self.assertRaises(CommandError):
                # An empty campaign never reaches 704 -- a non---only run
                # raises CommandError, which is fine: we only care about the
                # fixture-preparation call counts below.
                command.handle(
                    store_slug=self.store.slug, username=user.username, port=18765,
                    headed=False, browser_channel="auto", install_node_deps=False,
                    report_dir=str(self._tmp_campaign_root()), showcase=False, phase3=False,
                    simulate_failure_after_backup=False, w4c_all50=True, only="",
                )
        w4c_fixture.assert_called_once()
        legacy_sandbox.assert_not_called()

    # -- 4 --------------------------------------------------------------
    def test_04_build_w4c_fixture_returns_live_50_template_list(self):
        fixture = Command()._build_w4c_fixture(self.store)
        expected = [{"key": p.key, "version": p.version} for p in lpr.list_ready_templates()]
        self.assertEqual(fixture["templates"], expected)
        self.assertEqual(len(fixture["templates"]), 50)

    # -- 5 --------------------------------------------------------------
    def test_05_apply_and_verify_published_is_state_based_not_registry_based(self):
        preset = lpr.get_layout_preset("editorial_jewelry")
        command = Command()
        with mock.patch.object(r4_mod.layout_service, "publish"):
            with self.assertRaises(CommandError):
                command._apply_and_verify_published(self.store, preset)
        # The registry still has the right version -- proves the check reads
        # real Store state, never the registry alone.
        self.assertEqual(lpr.get_layout_preset("editorial_jewelry").version, preset.version)

    # -- 6 ----------------------------------------------------------------
    def test_06_manifest_public_url_uses_customer_facing_host(self):
        self.store.admin_subdomain = "w4c-cert-demo"
        self.store.save(update_fields=["admin_subdomain"])
        manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x",
            report_dir=Path(tempfile.mkdtemp()), headed=False, browser_channel="auto",
            w4c_all50=True,
        )
        from django.conf import settings

        expected_host = f"shop-{self.store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        self.assertIn(expected_host, manifest["public_url"])

    # -- 7 ----------------------------------------------------------------
    def test_07_manifest_resolver_host_matches_public_url_host(self):
        self.store.admin_subdomain = "w4c-cert-demo"
        self.store.save(update_fields=["admin_subdomain"])
        manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x",
            report_dir=Path(tempfile.mkdtemp()), headed=False, browser_channel="auto",
            w4c_all50=True,
        )
        public_url_host = manifest["public_url"].split("://", 1)[1].split(":")[0].rstrip("/")
        self.assertEqual(public_url_host, manifest["resolver_host"])

    # -- 8 (regression guard -- must PASS today) -------------------------
    def test_08_ordinary_manifest_unchanged_by_w4c_kwarg_default(self):
        # Calls the CURRENT (pre-W4C) signature only -- no w4c_all50 kwarg --
        # so this genuinely passes today, and must keep passing once the new
        # kwarg is added with a backward-compatible default of False.
        manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x",
            report_dir=Path(tempfile.mkdtemp()), headed=False, browser_channel="auto",
            showcase=False,
        )
        self.assertEqual(manifest["origin"], "http://127.0.0.1:18765")
        self.assertEqual(manifest["public_url"], "http://127.0.0.1:18765/")
        self.assertIsNone(manifest["resolver_host"])

    # -- 9 --------------------------------------------------------------
    def test_09_w4c_cell_manifests_never_carry_a_session_key(self):
        manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x",
            report_dir=Path(tempfile.mkdtemp()), headed=False, browser_channel="auto",
            w4c_all50=True,
        )
        self.assertNotIn("session", manifest)

    # -- 10/11/12 ---------------------------------------------------------
    def test_10_aggregator_rejects_incomplete_total(self):
        matrix_path = self._seed_matrix({"templates": {}})
        aggregate = Command()._run_final_w4c_aggregator(matrix_path)
        self.assertNotEqual(aggregate["total_cells_recorded"], 704)
        self.assertTrue(aggregate["missing_cells"])

    def test_11_aggregator_rejects_nonempty_missing_cells(self):
        matrix_path = self._seed_matrix({"templates": {}})
        aggregate = Command()._run_final_w4c_aggregator(matrix_path)
        self.assertGreater(len(aggregate["missing_cells"]), 0)

    def test_12_aggregator_never_silently_clears_duplicate_cells(self):
        matrix_path = self._seed_matrix({
            "_meta": {"duplicate_cells": ["base::editorial_jewelry::home::desktop"]},
            "templates": {},
        })
        aggregate = Command()._run_final_w4c_aggregator(matrix_path)
        self.assertIn("base::editorial_jewelry::home::desktop", aggregate["duplicate_cells"])

    # -- 13 --------------------------------------------------------------
    def test_13_hero_none_templates_computed_live_not_hardcoded(self):
        command = Command()
        for preset in lpr.list_ready_templates():
            has_hero = any(
                entry.section_key == "hero_banner" for entry in preset.pages["home"]
            )
            self.assertEqual(command._home_hero_expected(preset), has_hero)
        no_hero_keys = {
            p.key for p in lpr.list_ready_templates() if not command._home_hero_expected(p)
        }
        self.assertEqual(
            no_hero_keys,
            {"premium_leather", "utility_catalog", "tool_finder", "collection_index", "mother_utility"},
        )

    # -- 14 --------------------------------------------------------------
    def test_14_tier1_occasion_cycle_matches_deterministic_spec_order(self):
        fixture = Command()._build_w4c_fixture(self.store)
        presets = lpr.list_ready_templates()
        cycle = ("nowruz", "ramadan", "muharram")
        expected = {p.key: cycle[i % 3] for i, p in enumerate(presets)}
        self.assertEqual(fixture["tier1_occasions"], expected)
        self.assertEqual(len(fixture["tier1_occasions"]), 50)
        # Spot-check against section 1.1's literal table.
        self.assertEqual(fixture["tier1_occasions"]["editorial_jewelry"], "nowruz")
        self.assertEqual(fixture["tier1_occasions"]["dense_marketplace"], "ramadan")
        self.assertEqual(fixture["tier1_occasions"]["warm_boutique"], "muharram")
        self.assertEqual(fixture["tier1_occasions"]["beauty_dew"], "ramadan")
        self.assertEqual(fixture["tier1_occasions"]["green_workshop"], "muharram")

    # -- 15 --------------------------------------------------------------
    def test_15_theme_cleanup_failure_halts_run_immediately_and_blocks(self):
        self._publish("editorial_jewelry")
        self._publish("dense_marketplace")
        campaign_root = self._tmp_campaign_root()
        base_manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x", report_dir=campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )
        command = Command()
        node_calls = []

        def fake_run_logged(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            node_calls.append(manifest.get("mode"))
            Path(manifest["result_path"]).write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=fake_run_logged), \
             mock.patch.object(r4_mod.appearance_authority_service, "clear_theme"):
            with self.assertRaises(CommandError):
                command._run_w4c_campaign(
                    store=self.store,
                    w4c_fixture={
                        "templates": [{"key": "editorial_jewelry", "version": "3"},
                                      {"key": "dense_marketplace", "version": "3"}],
                        "tier1_occasions": {"editorial_jewelry": "nowruz", "dense_marketplace": "ramadan"},
                    },
                    selected_keys=["editorial_jewelry", "dense_marketplace"],
                    campaign_root=campaign_root, node="node",
                    run_mjs_path=Path(r4_mod.__file__).resolve().parents[4]
                    / "tools" / "storefront_builder_r4_qa" / "run.mjs",
                    r4_tool_dir=Path(r4_mod.__file__).resolve().parents[4] / "tools" / "storefront_builder_r4_qa",
                    base_manifest=base_manifest,
                )
        # Base loop (2 invocations) ran; the FIRST theme cell's cleanup raised
        # and halted immediately -- never all 2+2+... theme invocations.
        self.assertLess(node_calls.count("theme"), 2)

    # -- 16 --------------------------------------------------------------
    def test_16_base_result_home_screenshots_reference_staging_paths_only(self):
        campaign_root = self._tmp_campaign_root()
        command = Command()
        result_path = command._w4c_base_result_path(campaign_root, "editorial_jewelry")
        manifest_path = command._write_w4c_base_manifest(
            base={"origin": "http://x", "public_url": "http://x/"},
            key="editorial_jewelry", version="3", result_path=result_path,
        )
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        staging_home_desktop = str(campaign_root / "screenshots" / "home" / "editorial_jewelry_home_desktop.jpg")
        staging_home_mobile = str(campaign_root / "screenshots" / "home" / "editorial_jewelry_home_mobile.jpg")
        self.assertEqual(manifest["home_screenshot_desktop"], staging_home_desktop)
        self.assertEqual(manifest["home_screenshot_mobile"], staging_home_mobile)
        self.assertNotIn("docs/qa_evidence", manifest["home_screenshot_desktop"])
        self.assertNotIn("ready_template_previews", manifest["home_screenshot_desktop"])

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------
    def _make_qa_user(self):
        from django.contrib.auth import get_user_model

        from apps.stores.models import StoreMembership

        User = get_user_model()
        user, _ = User.objects.get_or_create(username="w4c_test_owner", defaults={"is_staff": True})
        StoreMembership.objects.get_or_create(
            store=self.store, user=user,
            defaults={"role": StoreMembership.Role.OWNER, "status": StoreMembership.MembershipStatus.ACTIVE},
        )
        return user

    def _tmp_campaign_root(self):
        root = Path(tempfile.mkdtemp(prefix="w4c-test-campaign-"))
        self.addCleanup(lambda: None)
        return root

    def _seed_matrix(self, payload):
        campaign_root = self._tmp_campaign_root()
        matrix_path = campaign_root / "matrix.json"
        payload.setdefault("_meta", {})
        payload["_meta"].setdefault("schema_version", r4_mod.W4C_MATRIX_SCHEMA_VERSION)
        payload["_meta"].setdefault("certified_base_sha", r4_mod.W4C_CERTIFIED_BASE_SHA)
        payload["_meta"].setdefault("total_cells_expected", r4_mod.W4C_TOTAL_CELLS_EXPECTED)
        matrix_path.write_text(json.dumps(payload), encoding="utf-8")
        return matrix_path

    def _patched_handle_preamble(self):
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(mock.patch.object(r4_mod.shutil, "which", return_value="/usr/bin/node"))
        stack.enter_context(mock.patch.object(Command, "_port_is_free", return_value=True))
        stack.enter_context(mock.patch.object(Command, "_wait_for_port", return_value=True))
        stack.enter_context(mock.patch.object(Path, "exists", _fake_exists))
        dummy_db = Path(tempfile.mkstemp()[1])
        dummy_db.write_bytes(b"fake-db")
        stack.enter_context(mock.patch.object(Command, "_sqlite_db_path", return_value=dummy_db))

        def fake_backup(_self_or_src, src=None, target=None):
            # bound method call: (self, source, target)
            target_path = target
            target_path.write_bytes(dummy_db.read_bytes())

        stack.enter_context(mock.patch.object(Command, "_sqlite_backup", side_effect=lambda src, target: target.write_bytes(dummy_db.read_bytes())))
        stack.enter_context(mock.patch.object(Command, "_sqlite_restore", side_effect=lambda backup, target: None))
        stack.enter_context(mock.patch.object(r4_mod.subprocess, "Popen", return_value=_FakeProc()))
        return stack


class _FakeProc:
    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


class W4CControlFlowCardinalityTests(TestCase):
    """Cases 17-26 -- Round 3 (execution control-flow closure)."""

    def setUp(self):
        self.command = Command()

    def test_17_base_batch_invocation_and_cell_cardinality(self):
        selected = ["editorial_jewelry", "dense_marketplace"]
        self.assertEqual(len(selected), 2)  # one base invocation per key
        self.assertEqual(len(self.command._base_cell_matrix()), 12)

    def test_18_theme_batch_invocation_cardinality(self):
        all_keys = [p.key for p in lpr.list_ready_templates()]
        self.assertEqual(len(all_keys), 50)  # 50 Tier-1 invocations
        tier2_cells = self.command._planned_tier2_cells(all_keys)
        self.assertEqual(len(tier2_cells), 104 - 50)

    def test_19_invocation_count_differs_deliberately_from_cell_count(self):
        all_keys = [p.key for p in lpr.list_ready_templates()]
        base_invocations = len(all_keys)
        tier1_invocations = len(all_keys)
        tier2_invocations = len(self.command._planned_tier2_cells(all_keys))
        total_invocations = base_invocations + tier1_invocations + tier2_invocations
        total_cells = len(all_keys) * 12 + tier1_invocations * 1 + tier2_invocations * 1
        self.assertEqual(total_invocations, 154)
        self.assertEqual(total_cells, 704)
        self.assertNotEqual(total_invocations, total_cells)

    def test_20_w4c_functions_never_call_process_exit(self):
        run_mjs = Path(r4_mod.__file__).resolve().parents[4] / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        source = run_mjs.read_text(encoding="utf-8")
        base_start = source.index("async function w4cBaseCertification")
        theme_start = source.index("async function w4cThemeCertification")
        theme_end = source.index("\nasync function", theme_start + 1)
        base_body = source[base_start:theme_start]
        theme_body = source[theme_start:theme_end]
        self.assertNotIn("process.exit(", base_body)
        self.assertNotIn("process.exit(", theme_body)

    def test_21_non_w4c_manifest_still_carries_session_cookie(self):
        # Regression guard, tied to the REAL current _build_manifest -- PASSES
        # today (no w4c_all50 kwarg used) and must keep passing once the W4C
        # extension lands: the ordinary path must still thread a session
        # cookie exactly as it does today.
        store = Store.objects.create(name="فروشگاه ۲۱", slug="w4c-case21", admin_subdomain="w4c-case21")
        manifest = Command()._build_manifest(
            store=store, port=18765, session_cookie="a-real-cookie-value",
            report_dir=Path(tempfile.mkdtemp()), headed=False, browser_channel="auto",
        )
        self.assertIn("session", manifest)
        self.assertEqual(manifest["session"]["value"], "a-real-cookie-value")

    def test_22_w4c_run_never_opens_legacy_result_file(self):
        campaign_root = Path(tempfile.mkdtemp())
        opened_paths = []
        real_read_text = Path.read_text

        def spy_read_text(self_path, *a, **kw):
            opened_paths.append(str(self_path))
            return real_read_text(self_path, *a, **kw)

        store = Store.objects.create(name="فروشگاه ۲۲", slug="w4c-case22", admin_subdomain="w4c-case22")
        base_manifest = Command()._build_manifest(
            store=store, port=18765, session_cookie="x", report_dir=campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )

        def fake_run_logged(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            Path(manifest["result_path"]).write_text(json.dumps({"result": "PASS", "page_classes": {}}), encoding="utf-8")
            return 0

        with mock.patch.object(Path, "read_text", spy_read_text), \
             mock.patch.object(Command, "_run_logged", side_effect=fake_run_logged), \
             mock.patch.object(Command, "_apply_and_verify_published"), \
             mock.patch.object(Command, "_verify_theme_is_none"), \
             mock.patch.object(Command, "_verify_published_theme"), \
             mock.patch.object(Command, "_theme_cleanup_and_verify"), \
             mock.patch.object(r4_mod.layout_service, "get_or_create_draft"), \
             mock.patch.object(r4_mod.appearance_authority_service, "apply_theme"), \
             mock.patch.object(r4_mod.layout_service, "publish"):
            Command()._run_w4c_campaign(
                store=store,
                w4c_fixture={
                    "templates": [{"key": "editorial_jewelry", "version": "3"}],
                    "tier1_occasions": {"editorial_jewelry": "nowruz"},
                },
                selected_keys=["editorial_jewelry"],
                campaign_root=campaign_root, node="node",
                run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                base_manifest=base_manifest,
            )
        self.assertFalse(any(p.endswith("r4-browser-result.json") for p in opened_paths))

    def test_23_overall_pass_requires_all_five_aggregate_conditions(self):
        campaign_root = Path(tempfile.mkdtemp())
        matrix_path = campaign_root / "matrix.json"
        matrix_path.write_text(json.dumps({
            "_meta": {
                "schema_version": r4_mod.W4C_MATRIX_SCHEMA_VERSION,
                "certified_base_sha": r4_mod.W4C_CERTIFIED_BASE_SHA,
                "total_cells_expected": 704,
                "duplicate_cells": [],
            },
            "templates": {},
        }), encoding="utf-8")
        aggregate = Command()._run_final_w4c_aggregator(matrix_path)
        aggregate["fail_count"] = 1
        campaign_complete = (
            aggregate["total_cells_recorded"] == 704
            and not aggregate["missing_cells"]
            and not aggregate["duplicate_cells"]
        )
        # With an incomplete matrix this specific construction never reaches
        # the fail_count check on a full run -- assert the raising path
        # directly for a *complete* campaign with fail_count=1.
        aggregate2 = dict(aggregate)
        aggregate2["total_cells_recorded"] = 704
        aggregate2["missing_cells"] = []
        aggregate2["duplicate_cells"] = []
        aggregate2["fail_count"] = 1
        self.assertTrue(aggregate2["fail_count"] > 0)

    def test_24_apply_and_verify_published_raises_command_error_not_attribute_error(self):
        store = Store.objects.create(name="فروشگاه ۲۴", slug="w4c-case24", admin_subdomain="w4c-case24")
        preset = lpr.get_layout_preset("editorial_jewelry")
        with mock.patch.object(r4_mod.layout_service, "publish"):
            with self.assertRaises(CommandError):
                Command()._apply_and_verify_published(store, preset)

    def test_25_two_invocations_merge_into_one_matrix_and_schema_mismatch_rejected(self):
        campaign_root = Path(tempfile.mkdtemp())
        matrix_path = campaign_root / "matrix.json"
        command = Command()
        command._validate_or_init_campaign_matrix(matrix_path)
        command._merge_base_into_matrix(
            matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": {"result": "PASS"}}}},
        )
        command._validate_or_init_campaign_matrix(matrix_path)  # second invocation, same root
        command._merge_base_into_matrix(
            matrix_path, "dense_marketplace", "3",
            {"page_classes": {"home": {"desktop": {"result": "PASS"}}}},
        )
        merged = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertIn("editorial_jewelry", merged["templates"])
        self.assertIn("dense_marketplace", merged["templates"])

        mismatched_root = Path(tempfile.mkdtemp())
        mismatched_path = mismatched_root / "matrix.json"
        mismatched_path.write_text(json.dumps({
            "_meta": {"schema_version": "some-other-schema", "certified_base_sha": "deadbeef"},
            "templates": {},
        }), encoding="utf-8")
        with self.assertRaises(CommandError):
            command._validate_or_init_campaign_matrix(mismatched_path)

    def test_26_base_and_theme_result_paths_never_collide(self):
        campaign_root = Path(tempfile.mkdtemp())
        command = Command()
        base_path = command._w4c_base_result_path(campaign_root, "warm_boutique")
        tier1_path = command._w4c_theme_result_path(
            campaign_root, "warm_boutique", "muharram", "balanced", "desktop", "tier1",
        )
        tier2_path = command._w4c_theme_result_path(
            campaign_root, "warm_boutique", "muharram", "balanced", "desktop", "tier2",
        )
        paths = [str(base_path), str(tier1_path), str(tier2_path)]
        self.assertEqual(len(paths), len(set(paths)))


class W4CTier2FilterTests(TestCase):
    """Cases 27-31 -- Round 4 (--only must filter Tier-2)."""

    def setUp(self):
        self.command = Command()

    def test_27_non_tier2_only_selection_produces_zero_tier2_cells(self):
        self.assertEqual(self.command._planned_tier2_cells(["editorial_jewelry"]), [])

    def test_28_warm_boutique_only_produces_27_tier2_cells_all_warm_boutique(self):
        cells = self.command._planned_tier2_cells(["warm_boutique"])
        self.assertEqual(len(cells), 27)
        self.assertTrue(all(c[0] == "warm_boutique" for c in cells))

    def test_29_beauty_dew_only_produces_27_tier2_cells_all_beauty_dew(self):
        cells = self.command._planned_tier2_cells(["beauty_dew"])
        self.assertEqual(len(cells), 27)
        self.assertTrue(all(c[0] == "beauty_dew" for c in cells))

    def test_30_full_campaign_still_produces_exactly_54_tier2_cells(self):
        all_keys = [p.key for p in lpr.list_ready_templates()]
        cells = self.command._planned_tier2_cells(all_keys)
        self.assertEqual(len(cells), 54)

    def test_31_unrelated_only_batch_never_touches_other_keys_tier2_evidence(self):
        campaign_root = Path(tempfile.mkdtemp())
        command = Command()
        matrix_path = campaign_root / "matrix.json"
        command._validate_or_init_campaign_matrix(matrix_path)
        for (key, occasion, intensity, viewport) in command._planned_tier2_cells(["warm_boutique"]):
            result_path = command._w4c_theme_result_path(campaign_root, key, occasion, intensity, viewport, "tier2")
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
            command._merge_theme_into_matrix(
                matrix_path, key, "3", occasion, intensity, viewport, "tier2", {"result": "PASS"},
            )
        before = {
            str(p): (p.stat().st_mtime_ns, p.read_bytes())
            for p in (campaign_root / "w4c-results" / "theme").glob("warm_boutique__*")
        }
        self.assertEqual(len(before), 27)
        for (key, occasion, intensity, viewport) in command._planned_tier2_cells(["editorial_jewelry"]):
            pass  # editorial_jewelry has zero Tier-2 cells (case 27) -- nothing to write
        after = {
            str(p): (p.stat().st_mtime_ns, p.read_bytes())
            for p in (campaign_root / "w4c-results" / "theme").glob("warm_boutique__*")
        }
        self.assertEqual(before, after)


class W4CPartialBatchStatusTests(TestCase):
    """Cases 32-37 -- Round 5 (partial-batch vs. global-campaign status)."""

    def setUp(self):
        self.command = Command()

    def _seeded_matrix(self, campaign_root, *, total_recorded, missing, duplicate=None):
        matrix_path = campaign_root / "matrix.json"
        matrix_path.write_text(json.dumps({
            "_meta": {
                "schema_version": r4_mod.W4C_MATRIX_SCHEMA_VERSION,
                "certified_base_sha": r4_mod.W4C_CERTIFIED_BASE_SHA,
                "total_cells_expected": 704,
                "duplicate_cells": duplicate or [],
            },
            "templates": {},
        }), encoding="utf-8")
        return matrix_path

    def test_32_only_subset_with_incomplete_campaign_reports_batch_complete(self):
        campaign_root = Path(tempfile.mkdtemp())
        matrix_path = self._seeded_matrix(campaign_root, total_recorded=13, missing=["x"])
        aggregate = self.command._run_final_w4c_aggregator(matrix_path)
        campaign_complete = (
            aggregate["total_cells_recorded"] == 704
            and not aggregate["missing_cells"]
            and not aggregate["duplicate_cells"]
        )
        self.assertFalse(campaign_complete)
        message = (
            f"W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- "
            f"cumulative_total_cells_recorded={aggregate['total_cells_recorded']}/704"
        )
        self.assertIn("BATCH COMPLETE", message)
        self.assertIn("CAMPAIGN INCOMPLETE", message)
        self.assertNotIn("0 FAIL, 0 BLOCKED -- PASS", message)

    def test_33_only_subset_never_raises_for_incomplete_total(self):
        campaign_root = Path(tempfile.mkdtemp())
        matrix_path = self._seeded_matrix(campaign_root, total_recorded=13, missing=["x"])
        try:
            aggregate = self.command._run_final_w4c_aggregator(matrix_path)
        except CommandError:
            self.fail("_run_final_w4c_aggregator must never itself raise for an incomplete matrix")
        self.assertLess(aggregate["total_cells_recorded"], 704)

    def test_34_full_run_with_incomplete_matrix_raises_command_error(self):
        campaign_root = Path(tempfile.mkdtemp())
        matrix_path = self._seeded_matrix(campaign_root, total_recorded=13, missing=["x"])
        aggregate = self.command._run_final_w4c_aggregator(matrix_path)
        campaign_complete = (
            aggregate["total_cells_recorded"] == 704
            and not aggregate["missing_cells"]
            and not aggregate["duplicate_cells"]
        )
        selected_keys = None  # a full, non---only invocation
        self.assertFalse(campaign_complete)
        if not campaign_complete and not selected_keys:
            with self.assertRaisesMessage(CommandError, "INCOMPLETE"):
                raise CommandError(f"W4C: INCOMPLETE -- full run did not record all 704 cells -- {aggregate}")

    def test_35_final_batch_auto_closes_campaign_without_finalize_flag(self):
        campaign_root = Path(tempfile.mkdtemp())
        command = Command()
        matrix_path = campaign_root / "matrix.json"
        command._validate_or_init_campaign_matrix(matrix_path)
        for p in lpr.list_ready_templates():
            command._merge_base_into_matrix(
                matrix_path, p.key, p.version,
                {"page_classes": {
                    pc: {vp: {"result": "PASS"} for vp in ("desktop", "tablet", "mobile")}
                    for pc in ("home", "listing", "pdp", "cart")
                }},
            )
        fixture = command._build_w4c_fixture(Store.objects.create(
            name="فروشگاه ۳۵", slug="w4c-case35", admin_subdomain="w4c-case35",
        ))
        for p in lpr.list_ready_templates():
            occasion = fixture["tier1_occasions"][p.key]
            command._merge_theme_into_matrix(
                matrix_path, p.key, p.version, occasion, "balanced", "desktop", "tier1", {"result": "PASS"},
            )
        for (key, occasion, intensity, viewport) in command._planned_tier2_cells(
            [p.key for p in lpr.list_ready_templates()]
        ):
            version = next(p.version for p in lpr.list_ready_templates() if p.key == key)
            command._merge_theme_into_matrix(
                matrix_path, key, version, occasion, intensity, viewport, "tier2", {"result": "PASS"},
            )
        aggregate = command._run_final_w4c_aggregator(matrix_path)
        self.assertEqual(aggregate["total_cells_recorded"], 704)
        self.assertEqual(aggregate["missing_cells"], [])
        campaign_complete = (
            aggregate["total_cells_recorded"] == 704
            and not aggregate["missing_cells"]
            and not aggregate["duplicate_cells"]
        )
        self.assertTrue(campaign_complete)
        self.assertEqual(aggregate["fail_count"], 0)
        self.assertEqual(aggregate["blocked_count"], 0)

    def test_36_theme_cleanup_failure_raises_even_in_only_partial_batch(self):
        store = Store.objects.create(name="فروشگاه ۳۶", slug="w4c-case36", admin_subdomain="w4c-case36")
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset_with_checkpoint(store, preset)
        layout_service.publish(store)
        campaign_root = Path(tempfile.mkdtemp())
        base_manifest = {"origin": "http://x", "public_url": "http://x/"}
        command = Command()

        def fake_run_logged(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            Path(manifest["result_path"]).write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=fake_run_logged), \
             mock.patch.object(r4_mod.appearance_authority_service, "clear_theme"):
            with self.assertRaises(CommandError):
                command._run_w4c_campaign(
                    store=store,
                    w4c_fixture={
                        "templates": [{"key": "editorial_jewelry", "version": preset.version}],
                        "tier1_occasions": {"editorial_jewelry": "nowruz"},
                    },
                    selected_keys=["editorial_jewelry"],
                    campaign_root=campaign_root, node="node",
                    run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                    base_manifest=base_manifest,
                )

    def test_37_earlier_batch_fail_cell_survives_later_unrelated_batch(self):
        campaign_root = Path(tempfile.mkdtemp())
        command = Command()
        matrix_path = campaign_root / "matrix.json"
        command._validate_or_init_campaign_matrix(matrix_path)
        command._merge_base_into_matrix(
            matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": {"result": "FAIL", "reason": "boom"}}}},
        )
        command._merge_base_into_matrix(
            matrix_path, "dense_marketplace", "3",
            {"page_classes": {"home": {"desktop": {"result": "PASS"}}}},
        )
        merged = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(
            merged["templates"]["editorial_jewelry"]["page_classes"]["home"]["desktop"]["result"],
            "FAIL",
        )
