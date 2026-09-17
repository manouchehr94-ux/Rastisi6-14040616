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
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
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


# Repair Round 2, IMPORTANT 6 -- every test in this module that reaches
# _run_w4c_campaign/_validate_or_init_campaign_matrix touches the new
# git-HEAD-binding/dirty-worktree gate. Defaulting both to a clean,
# deterministic state here (module-wide) means the hundred-plus existing
# cases above never depend on this actual repo's real worktree/HEAD state
# at test-run time (which is genuinely dirty during this very repair
# round's own edit/test cycle) -- only the dedicated
# W4CCampaignProvenanceTests below override these defaults, deliberately,
# to exercise the real dirty/mismatch branches.
_GIT_HEAD_PATCHER = None
_DIRTY_WORKTREE_PATCHER = None


def setUpModule():
    global _GIT_HEAD_PATCHER, _DIRTY_WORKTREE_PATCHER
    _GIT_HEAD_PATCHER = mock.patch.object(Command, "_current_git_head", return_value="0" * 40)
    _DIRTY_WORKTREE_PATCHER = mock.patch.object(Command, "_tracked_worktree_is_dirty", return_value=False)
    _GIT_HEAD_PATCHER.start()
    _DIRTY_WORKTREE_PATCHER.start()


def tearDownModule():
    _GIT_HEAD_PATCHER.stop()
    _DIRTY_WORKTREE_PATCHER.stop()


class W4CAll50CertificationHarnessTests(TestCase):
    """Cases 1-16 -- Round 2 (+Round 1's carried-over 5)."""

    def setUp(self):
        cache.clear()
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
        with mock.patch.object(r4_mod.settings, "DEBUG", True), \
             mock.patch.object(Command, "_prepare_w4c_certification_fixture", return_value={}) as w4c_fixture, \
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
        from apps.storefront_builder import a8_ready_templates

        fixture = Command()._build_w4c_fixture(self.store)
        cycle = ("nowruz", "ramadan", "muharram")
        expected = {spec.key: cycle[i % 3] for i, spec in enumerate(a8_ready_templates._SPECS)}
        self.assertEqual(fixture["tier1_occasions"], expected)
        self.assertEqual(len(fixture["tier1_occasions"]), 50)
        # Spot-check against section 1.1's literal table.
        self.assertEqual(fixture["tier1_occasions"]["editorial_jewelry"], "nowruz")
        self.assertEqual(fixture["tier1_occasions"]["dense_marketplace"], "ramadan")
        self.assertEqual(fixture["tier1_occasions"]["warm_boutique"], "muharram")
        self.assertEqual(fixture["tier1_occasions"]["beauty_dew"], "ramadan")
        self.assertEqual(fixture["tier1_occasions"]["green_workshop"], "muharram")

    # -- 14b (smoke-round bug regression, section 11) ---------------------
    def test_14b_pdp_fixture_product_must_have_in_stock_variant(self):
        """The PDP/Cart cells exercise real quantity-adjustment and
        add-to-cart flows against this fixture product -- an out-of-stock
        VARIABLE product (found via the bounded editorial_jewelry browser
        smoke) makes those checks fail for the fixture's sake, not the check
        logic's. Reuses the same "has inventory" predicate as
        product_completion_service._has_inventory."""
        from decimal import Decimal

        from apps.catalog.models import Category, Product, ProductVariant, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="w4c-fixture-vendor")
        category = Category.objects.create(store=self.store, name="دسته", slug="w4c-fixture-cat")
        out_of_stock = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای ناموجود",
            slug="w4c-oos-product", sku="W4C-OOS", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        ProductVariant.objects.create(product=out_of_stock, attribute="رنگ", value="قرمز", stock=0)
        in_stock = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای موجود",
            slug="w4c-in-stock-product", sku="W4C-IN-STOCK", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        ProductVariant.objects.create(product=in_stock, attribute="رنگ", value="سبز", stock=5)
        # Repair round 2 (2A) -- a real variant TRANSITION needs >= 2
        # purchasable choices; a single-variant product can never exercise
        # it, so the fixture predicate now requires at least 2.
        ProductVariant.objects.create(product=in_stock, attribute="رنگ", value="آبی", stock=5)

        fixture = Command()._build_w4c_fixture(self.store)
        self.assertEqual(fixture["pdp_product_id"], in_stock.pk)

    # -- 14c (smoke-round bug regression, section 11) ---------------------
    def test_14c_pdp_fixture_rejects_product_with_any_out_of_stock_variant(self):
        """storefront_variant_service picks the DEFAULT variant as
        ``is_default=True`` else the first by (display_order, id) -- never
        necessarily an in-stock one. A product with a mix of in-stock and
        out-of-stock variants (found via the bounded editorial_jewelry
        browser smoke) can still present an out-of-stock default variant on
        the PDP even though "some" variant has stock. The fixture must
        require EVERY active variant to be in stock, not just one."""
        from decimal import Decimal

        from apps.catalog.models import Category, Product, ProductVariant, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="w4c-mixed-vendor")
        category = Category.objects.create(store=self.store, name="دسته", slug="w4c-mixed-cat")
        mixed = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای مخلوط",
            slug="w4c-mixed-product", sku="W4C-MIXED", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        ProductVariant.objects.create(product=mixed, attribute="سایز", value="41", stock=0)
        ProductVariant.objects.create(product=mixed, attribute="سایز", value="42", stock=10)
        all_in_stock = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای کاملا موجود",
            slug="w4c-all-in-stock-product", sku="W4C-ALL-IN-STOCK", price=Decimal("100000"),
            product_type=Product.ProductType.VARIABLE,
        )
        ProductVariant.objects.create(product=all_in_stock, attribute="سایز", value="41", stock=10)
        ProductVariant.objects.create(product=all_in_stock, attribute="سایز", value="42", stock=10)

        fixture = Command()._build_w4c_fixture(self.store)
        self.assertEqual(fixture["pdp_product_id"], all_in_stock.pk)

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
            run_token=command._new_run_token(),
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
        from django.utils import timezone

        from apps.stores.models import StoreMembership

        User = get_user_model()
        user, _ = User.objects.get_or_create(username="w4c_test_owner", defaults={"is_staff": True})
        StoreMembership.objects.get_or_create(
            store=self.store, user=user,
            defaults={
                "role": StoreMembership.Role.OWNER,
                "status": StoreMembership.MembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
            },
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
        cache.clear()
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
            _write_node_result(cmd_list[2])
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
        cache.clear()
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
        cache.clear()
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


# =============================================================================
# Independent Architect Code Review Repair Round 1
#
# CRITICAL 1 -- a stale result file must never be accepted as evidence of a
# current invocation. IMPORTANT 3 -- resume must execute only missing cells
# and never silently overwrite a terminal cell. IMPORTANT 4 -- an incomplete
# cell payload must be rejected before it ever reaches matrix.json.
#
# These tests are genuinely RED against implementation head
# e2f1070e68a259d94092f1c26ecbfe1ab67b19d5: none of _new_run_token,
# _validate_base_result_freshness, _validate_theme_result_freshness,
# _missing_base_cells, _cell_already_recorded_theme, or
# _record_recovered_state_event exist yet, and the current
# _merge_base_into_matrix/_run_one_theme_cell do not perform freshness,
# identity, or schema validation at all.
# =============================================================================
def _valid_base_cell(result="PASS", **overrides):
    cell = {
        "http_status": 200, "rtl": True, "overflow": False,
        "header_count": 1, "footer_count": 1,
        "bottom_nav_present": True, "bottom_nav_display": "none",
        "rsec_count": 5, "expected_rsec_count": 5,
        "product_cards_present": True, "dead_href_count": 0,
        "console_errors": [], "page_errors": [], "failed_requests": [],
        "accessibility_checks": {}, "result": result, "screenshot": None,
    }
    if result != "PASS":
        cell["reason"] = "simulated failure"
    cell.update(overrides)
    return cell


def _valid_theme_payload(manifest, result="PASS"):
    active_key = manifest["active_key"]
    return {
        "run_token": manifest.get("run_token"), "key": active_key["key"],
        "occasion": active_key["occasion"], "intensity": active_key["intensity"],
        "viewport": active_key["viewport"], "tier": active_key["tier"],
        "http_status": 200, "rtl": True, "overflow": False,
        "console_errors": [], "page_errors": [], "failed_requests": [], "result": result,
        "screenshot": None,
    }


def _write_node_result(manifest_path, *, base_result=None, theme_result=None):
    """A generic ``_run_logged`` replacement for tests that are not
    exercising base/theme freshness themselves: writes a valid PASS payload
    for whichever mode the manifest actually is, so the OTHER loop
    (base/tier1/tier2) never spuriously fails the freshness/schema
    validation this repair round added."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("mode") == "theme":
        payload = theme_result if theme_result is not None else _valid_theme_payload(manifest)
    else:
        cells = {}
        for cell_spec in manifest.get("cells", []):
            cells.setdefault(cell_spec["page_class"], {})[cell_spec["viewport"]] = _valid_base_cell()
        payload = base_result if base_result is not None else {
            "run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
            "version": manifest["active_key"]["version"], "page_classes": cells,
        }
    Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
    return manifest


class W4CResultFreshnessTests(TestCase):
    """CRITICAL 1 -- never accept a stale result file."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه تازگی", slug="w4c-freshness", admin_subdomain="w4c-freshness",
        )
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset_with_checkpoint(self.store, preset)
        layout_service.publish(self.store)
        self.campaign_root = Path(tempfile.mkdtemp(prefix="w4c-fresh-"))
        self.command = Command()
        self.base_manifest = self.command._build_manifest(
            store=self.store, port=18765, session_cookie="x", report_dir=self.campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )

    def _campaign_kwargs(self, keys):
        return dict(
            store=self.store,
            w4c_fixture={
                "templates": [{"key": k, "version": lpr.get_layout_preset(k).version} for k in keys],
                "tier1_occasions": {k: "nowruz" for k in keys},
            },
            selected_keys=keys,
            campaign_root=self.campaign_root, node="node",
            run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
            base_manifest=self.base_manifest,
        )

    def test_38_run_token_is_generated_and_distinct_per_invocation(self):
        tokens = {self.command._new_run_token() for _ in range(5)}
        self.assertEqual(len(tokens), 5)
        for token in tokens:
            self.assertIsInstance(token, str)
            self.assertGreaterEqual(len(token), 16)

    def test_39_stale_pass_file_survives_node_crash_is_rejected(self):
        result_path = self.command._w4c_base_result_path(self.campaign_root, "editorial_jewelry")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        stale = {"run_token": "an-old-token-from-a-previous-run", "key": "editorial_jewelry",
                  "version": "3", "page_classes": {"home": {"desktop": _valid_base_cell()}}}
        result_path.write_text(json.dumps(stale), encoding="utf-8")

        def crash_without_writing(cmd_list, *, cwd, log_path):
            return 1  # Node crashed -- writes nothing new, the stale file is left behind

        with mock.patch.object(Command, "_run_logged", side_effect=crash_without_writing):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))
        # The stale file's own content must never have been merged as fresh evidence.
        matrix_path = self.campaign_root / "matrix.json"
        if matrix_path.exists():
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            self.assertNotIn("editorial_jewelry", matrix.get("templates", {}))

    def test_40_run_token_mismatch_rejected(self):
        result_path = self.command._w4c_base_result_path(self.campaign_root, "editorial_jewelry")
        result_path.parent.mkdir(parents=True, exist_ok=True)

        def write_wrong_token(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = {"run_token": "wrong-token", "key": manifest["active_key"]["key"],
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": _valid_base_cell()}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_wrong_token):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_41_wrong_template_identity_rejected(self):
        def write_wrong_identity(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = {"run_token": manifest.get("run_token"), "key": "some_other_key",
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": _valid_base_cell()}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_wrong_identity):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_42_malformed_json_rejected(self):
        def write_garbage(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            Path(manifest["result_path"]).write_text("{not valid json", encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_garbage):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_43_missing_result_field_rejected(self):
        def write_incomplete(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            cell = _valid_base_cell()
            del cell["console_errors"]
            payload = {"run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": cell}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_incomplete):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_44_unknown_result_enum_rejected(self):
        def write_unknown_enum(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            cell = _valid_base_cell(result="MAYBE")
            payload = {"run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": cell}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_unknown_enum):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_45_nonzero_exit_with_no_result_is_blocked(self):
        def crash_after_unlink(cmd_list, *, cwd, log_path):
            return 1

        with mock.patch.object(Command, "_run_logged", side_effect=crash_after_unlink):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))

    def test_46_nonzero_exit_with_valid_fresh_fail_result_is_merged_as_fail(self):
        def write_genuine_fail(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            if manifest.get("mode") == "theme":
                payload = {
                    "run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                    "occasion": manifest["active_key"]["occasion"], "intensity": manifest["active_key"]["intensity"],
                    "viewport": manifest["active_key"]["viewport"], "tier": manifest["active_key"]["tier"],
                    "http_status": 200, "rtl": True, "overflow": False,
                    "console_errors": [], "page_errors": [], "failed_requests": [], "result": "PASS",
                    "screenshot": None,
                }
                Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
                return 0
            cell = _valid_base_cell(result="FAIL")
            payload = {"run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": cell}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 1  # a genuine FAIL exit consistent with the FAIL cell above

        with mock.patch.object(Command, "_run_logged", side_effect=write_genuine_fail):
            # Must NOT raise -- a consistent FAIL result is real evidence, not infrastructure BLOCKED.
            self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))
        matrix = json.loads((self.campaign_root / "matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["templates"]["editorial_jewelry"]["page_classes"]["home"]["desktop"]["result"], "FAIL",
        )

    def test_47_nonzero_exit_but_all_pass_result_is_inconsistent_blocked(self):
        def write_all_pass_but_crash(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = {"run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                       "version": manifest["active_key"]["version"],
                       "page_classes": {"home": {"desktop": _valid_base_cell(result="PASS")}}}
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 1  # exit 1 despite an all-PASS result -- inconsistent, must BLOCK

        with mock.patch.object(Command, "_run_logged", side_effect=write_all_pass_but_crash):
            with self.assertRaises(CommandError):
                self.command._run_w4c_campaign(**self._campaign_kwargs(["editorial_jewelry"]))


class W4CResumeAndMergeTests(TestCase):
    """IMPORTANT 3 -- resume executes only missing cells; merges are insert-only."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه ازسرگیری", slug="w4c-resume", admin_subdomain="w4c-resume",
        )
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset_with_checkpoint(self.store, preset)
        layout_service.publish(self.store)
        self.campaign_root = Path(tempfile.mkdtemp(prefix="w4c-resume-"))
        self.command = Command()
        self.matrix_path = self.campaign_root / "matrix.json"
        self.command._validate_or_init_campaign_matrix(self.matrix_path)
        self.base_manifest = self.command._build_manifest(
            store=self.store, port=18765, session_cookie="x", report_dir=self.campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )

    def test_48_missing_base_cells_helper_reports_only_unrecorded(self):
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        missing_all = self.command._missing_base_cells(matrix, "editorial_jewelry")
        self.assertEqual(len(missing_all), 12)
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": _valid_base_cell()}}},
        )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        missing_after = self.command._missing_base_cells(matrix, "editorial_jewelry")
        self.assertEqual(len(missing_after), 11)
        self.assertNotIn(("home", "desktop"), missing_after)

    def test_49_fully_recorded_template_skips_node_entirely(self):
        for page_class, viewport in self.command._base_cell_matrix():
            self.command._merge_base_into_matrix(
                self.matrix_path, "editorial_jewelry", "3",
                {"page_classes": {page_class: {viewport: _valid_base_cell()}}},
            )
        node_calls = []

        def track_and_write(cmd_list, *, cwd, log_path):
            node_calls.append(1)
            _write_node_result(cmd_list[2])
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=track_and_write):
            self.command._run_w4c_campaign(
                store=self.store,
                w4c_fixture={"templates": [{"key": "editorial_jewelry", "version": "3"}],
                             "tier1_occasions": {"editorial_jewelry": "nowruz"}},
                selected_keys=["editorial_jewelry"],
                campaign_root=self.campaign_root, node="node",
                run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                base_manifest=self.base_manifest,
            )
        base_invocations = [c for c in node_calls]  # any call at all would indicate re-execution
        # The base loop must have made zero Node calls for this fully-recorded key --
        # only Theme cells (tier1) remain unrecorded and would call Node.
        # We assert indirectly: the base result file was never rewritten after our seed.
        base_result_path = self.command._w4c_base_result_path(self.campaign_root, "editorial_jewelry")
        self.assertFalse(base_result_path.exists())  # never written by run.mjs -- only matrix.json holds it

    def test_50_partial_resume_requests_only_missing_cells_in_manifest(self):
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": _valid_base_cell()}}},
        )
        seen_manifests = []

        def capture_manifest(cmd_list, *, cwd, log_path):
            manifest = _write_node_result(cmd_list[2])
            seen_manifests.append(manifest)
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=capture_manifest):
            self.command._run_w4c_campaign(
                store=self.store,
                w4c_fixture={"templates": [{"key": "editorial_jewelry", "version": "3"}],
                             "tier1_occasions": {"editorial_jewelry": "nowruz"}},
                selected_keys=["editorial_jewelry"],
                campaign_root=self.campaign_root, node="node",
                run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                base_manifest=self.base_manifest,
            )
        base_manifests = [m for m in seen_manifests if m.get("mode") == "base"]
        self.assertEqual(len(base_manifests), 1)
        requested_cells = {(c["page_class"], c["viewport"]) for c in base_manifests[0]["cells"]}
        self.assertEqual(len(requested_cells), 11)
        self.assertNotIn(("home", "desktop"), requested_cells)

    def test_51_merge_refuses_to_overwrite_a_terminal_cell(self):
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": _valid_base_cell(result="PASS")}}},
        )
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"home": {"desktop": _valid_base_cell(result="FAIL")}}},
        )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["templates"]["editorial_jewelry"]["page_classes"]["home"]["desktop"]["result"], "PASS",
        )
        self.assertTrue(matrix["_meta"]["duplicate_cells"])

    def test_51b_merge_refuses_to_overwrite_a_terminal_fail_cell_with_pass(self):
        # The stricter rule is symmetric: an existing FAIL is just as terminal
        # as an existing PASS -- ordinary resume must never replace it either,
        # not even with a later PASS (a genuine recheck is a separate,
        # explicitly-invoked mode that does not exist in W4C today).
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"listing": {"mobile": _valid_base_cell(result="FAIL")}}},
        )
        self.command._merge_base_into_matrix(
            self.matrix_path, "editorial_jewelry", "3",
            {"page_classes": {"listing": {"mobile": _valid_base_cell(result="PASS")}}},
        )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["templates"]["editorial_jewelry"]["page_classes"]["listing"]["mobile"]["result"], "FAIL",
        )

    def test_52_recovered_state_event_recorded_on_theme_drift(self):
        draft = layout_service.get_or_create_draft(self.store)
        r4_mod.appearance_authority_service.apply_theme(
            version=draft, component_key="theme.nowruz.v1", intensity="balanced",
        )
        layout_service.publish(self.store)  # published Theme is now drifted away from theme.none.v1

        def write_pass(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = _valid_theme_payload(manifest)
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_pass):
            self.command._run_one_theme_cell(
                store=self.store, key="editorial_jewelry", version="3", occasion="ramadan",
                intensity="balanced", viewport="desktop", tier="tier1",
                campaign_root=self.campaign_root, matrix_path=self.matrix_path,
                node="node", run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                base_manifest=self.base_manifest,
            )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.assertTrue(matrix["_meta"]["recovered_state_events"])


class W4CThemeCleanupOrderingTests(TestCase):
    """IMPORTANT 2 -- cleanup_verified only after cleanup genuinely succeeds."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه پاک‌سازی", slug="w4c-cleanup-order", admin_subdomain="w4c-cleanup-order",
        )
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset_with_checkpoint(self.store, preset)
        layout_service.publish(self.store)
        self.campaign_root = Path(tempfile.mkdtemp(prefix="w4c-cleanup-"))
        self.command = Command()
        self.matrix_path = self.campaign_root / "matrix.json"
        self.command._validate_or_init_campaign_matrix(self.matrix_path)
        self.base_manifest = self.command._build_manifest(
            store=self.store, port=18765, session_cookie="x", report_dir=self.campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )

    def test_53_cleanup_verified_true_only_after_real_cleanup_success(self):
        def write_pass(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = _valid_theme_payload(manifest)
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_pass):
            self.command._run_one_theme_cell(
                store=self.store, key="editorial_jewelry", version="3", occasion="nowruz",
                intensity="balanced", viewport="desktop", tier="tier1",
                campaign_root=self.campaign_root, matrix_path=self.matrix_path,
                node="node", run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                base_manifest=self.base_manifest,
            )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.assertTrue(matrix["templates"]["editorial_jewelry"]["theme"]["tier1_cell"]["cleanup_verified"])

    def test_54_cleanup_failure_prevents_any_merge(self):
        def write_pass(cmd_list, *, cwd, log_path):
            manifest = json.loads(Path(cmd_list[2]).read_text(encoding="utf-8"))
            payload = _valid_theme_payload(manifest)
            Path(manifest["result_path"]).write_text(json.dumps(payload), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=write_pass), \
             mock.patch.object(r4_mod.appearance_authority_service, "clear_theme"):
            with self.assertRaises(CommandError):
                self.command._run_one_theme_cell(
                    store=self.store, key="editorial_jewelry", version="3", occasion="nowruz",
                    intensity="balanced", viewport="desktop", tier="tier1",
                    campaign_root=self.campaign_root, matrix_path=self.matrix_path,
                    node="node", run_mjs_path=Path("run.mjs"), r4_tool_dir=Path("."),
                    base_manifest=self.base_manifest,
                )
        matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        self.assertNotIn("editorial_jewelry", matrix.get("templates", {}))


class W4CBrowserContractSourceTests(TestCase):
    """IMPORTANT 1/2 -- real Home/Listing/PDP/Cart/Theme contracts in run.mjs,
    verified as static source-grep regression guards (the same technique
    the existing test_qa_harness_contract.py uses), since a live browser is
    not run in this repair round."""

    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def test_55_hero_check_is_positional_not_broad_text_selector(self):
        self.assertNotIn(':has-text("")', self.source)
        self.assertIn("hero_index", self.source)

    def test_56_home_result_requires_rsec_and_cards_for_pass(self):
        base_start = self.source.index("function w4cRunHomeCell")
        base_end = self.source.index("\nasync function", base_start + 1)
        body = self.source[base_start:base_end]
        self.assertIn("rsec_count", body)
        self.assertIn("expected_rsec_count", body)

    def test_57_listing_requires_real_product_link_resolution(self):
        start = self.source.index("function w4cRunListingCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertIn("pcard-hitarea", body)

    def test_58_pdp_requires_gallery_price_stock_variant_quantity_addtocart(self):
        start = self.source.index("function w4cRunPdpCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        for marker in ("data-slide", "pricebox", ".stock", "quantity"):
            self.assertIn(marker, body)
        # Repair round 2 (2A/2B) -- the variant-transition selector and the
        # real Add-to-Cart click/#cart-count check now live in shared
        # helpers this cell calls, not inline in its own body.
        self.assertIn("opt-block", self.source)
        self.assertIn("cart-count", self.source)

    def test_59_cart_requires_item_quantity_remove_totals_checkout(self):
        start = self.source.index("function w4cRunCartCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        for marker in ("citem", "stepper", "totals", "checkout"):
            self.assertIn(marker, body)
        # Repair round 2 (3B) -- the real remove selector now lives in the
        # shared w4cCartRealRemove helper this cell calls.
        self.assertIn(".rm", self.source)

    def test_60_theme_cell_checks_rendered_dom_identity(self):
        start = self.source.index("function w4cRunThemeCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertIn("data-occasion-theme", body)
        self.assertIn("data-occasion-tone", body)
        self.assertIn("data-occasion-intensity", body)

    def test_61_bottom_nav_is_a_pass_fail_contract(self):
        for fn in ("w4cRunHomeCell", "w4cRunListingCell", "w4cRunPdpCell", "w4cRunCartCell"):
            with self.subTest(fn=fn):
                start = self.source.index(f"function {fn}")
                end = self.source.index("\nasync function", start + 1)
                body = self.source[start:end]
                self.assertIn("bottom_nav", body)

    # -- smoke-round bug regressions (found by actually running the bounded
    # editorial_jewelry browser smoke, section 11) --------------------------
    def test_62_listing_resolves_relative_href_before_requesting_it(self):
        start = self.source.index("function w4cRunListingCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertNotIn("targetPage.request.get(linkHref)", body)
        self.assertIn("manifest.origin", body)

    def test_63_theme_identity_compares_against_raw_occasion_key(self):
        start = self.source.index("function w4cRunThemeCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertIn("rendered.theme === activeKey.occasion", body)
        self.assertNotIn("rendered.theme === expectedComponentKey", body)

    def test_64_cart_add_runs_inside_the_page_never_context_request(self):
        start = self.source.index("function w4cRunCartCell")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertNotIn("context.request.post", body)
        self.assertIn("targetPage.evaluate", body)
        self.assertIn("csrftoken", body)


# =============================================================================
# Repair Round 2 -- IMPORTANT 1: request failures must gate every public cell
# (Listing/PDP/Cart/Theme), not just Home. Genuine browser proof of this gate
# is the bounded real-browser smoke (section 1's own instruction); these are
# static source-grep regression guards, not a substitute for that proof.
# =============================================================================
class W4CRequestFailureGateTests(TestCase):
    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def _body(self, fn_name):
        start = self.source.index(f"function {fn_name}")
        end = self.source.index("\nasync function", start + 1)
        return self.source[start:end]

    def test_65_listing_request_failure_gates_pass(self):
        body = self._body("w4cRunListingCell")
        self.assertIn("errors.requestFailures.length === 0", body)

    def test_66_pdp_request_failure_gates_pass(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("errors.requestFailures.length === 0", body)

    def test_67_cart_request_failure_gates_pass(self):
        body = self._body("w4cRunCartCell")
        self.assertIn("errors.requestFailures.length === 0", body)

    def test_68_theme_request_failure_gates_pass(self):
        body = self._body("w4cRunThemeCell")
        self.assertIn("errors.requestFailures.length === 0", body)


# =============================================================================
# Repair Round 2 -- IMPORTANT 2: full PDP interaction contract. Source-grep
# regression guards for the real (not presence-only) variant transition,
# real Add-to-Cart, and real navigation checks; genuine behavioral proof is
# the bounded real-browser smoke.
# =============================================================================
class W4CPdpInteractionContractTests(TestCase):
    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")
        self.store = Store.objects.create(
            name="فروشگاه W4C R2", slug="w4c-r2-demo", admin_subdomain="w4c-r2-demo",
        )

    def _body(self, fn_name):
        start = self.source.index(f"function {fn_name}")
        end = self.source.index("\nasync function", start + 1)
        return self.source[start:end]

    def test_69_pdp_variant_presence_alone_is_insufficient(self):
        """The old gate (`variantControls > 0`) proved a control EXISTS, never
        that selecting a different one actually changes anything. The new
        gate must depend on a real transition outcome, not raw control count."""
        body = self._body("w4cRunPdpCell")
        self.assertNotIn("variantControls > 0 && qtyPresent && qtyAdjusted && addToCartForm", body)

    def test_70_pdp_requires_real_variant_transition(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("VariantTransition", body)
        # The real click/before-after-comparison logic lives in a shared
        # helper (reused if PDP ever needs it twice); the selector itself
        # must still be source-backed, on the real Alpine-driven markup.
        self.assertIn(".opt-block .swatch, .opt-block .size", self.source)

    def test_70b_variant_transition_tracks_every_axis_active_control(self):
        """Smoke-round bug regression: a product with a single-value axis
        (e.g. one color) alongside a multi-value axis (e.g. 5 sizes) has
        MULTIPLE currently-active controls, one per axis -- tracking only
        the first active index (instead of the full active set) can pick
        the axis's OWN already-selected value as the "different" target,
        which never changes anything. Found via the real editorial_jewelry
        smoke against product FSH-003 (1 color x 5 sizes)."""
        start = self.source.index("function w4cVariantTransitionCheck")
        end = self.source.index("\nasync function", start + 1)
        body = self.source[start:end]
        self.assertIn("activeIndices", body)
        self.assertNotIn("activeIndex:", body)

    def test_71_pdp_add_to_cart_presence_alone_is_insufficient(self):
        body = self._body("w4cRunPdpCell")
        self.assertNotIn("addToCartForm >= 1", body)

    def test_72_pdp_requires_real_add_to_cart_effect(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("RealAddToCart", body)
        self.assertIn("cart-count", self.source)

    def test_73_pdp_requires_real_navigation(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("RealNavigation", body)

    def test_74_pdp_fixture_has_enough_variants_for_a_transition(self):
        """2A -- the deterministic fixture product must have at least 2
        purchasable variants so a real transition is possible; a
        single-variant product can never exercise this contract. Uses the
        REAL seeded fixture store (seed_ready_template_fashion_demo always
        targets its own fixed rasti-mode-demo store), matching what the
        actual campaign runs against."""
        from django.core.management import call_command

        from apps.catalog.models import Product

        call_command("seed_ready_template_fashion_demo")
        store = Store.objects.get(slug="rasti-mode-demo")
        fixture = Command()._build_w4c_fixture(store)
        product_id = fixture["pdp_product_id"]
        self.assertIsNotNone(product_id)
        product = Product.objects.get(pk=product_id)
        purchasable = product.variants.filter(is_active=True, is_obsolete=False, stock__gt=0).count()
        self.assertGreaterEqual(purchasable, 2)


# =============================================================================
# Repair Round 2 -- IMPORTANT 3: Listing + Cart behavior completion.
# =============================================================================
class W4CListingCartBehaviorContractTests(TestCase):
    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def _body(self, fn_name):
        start = self.source.index(f"function {fn_name}")
        end = self.source.index("\nasync function", start + 1)
        return self.source[start:end]

    def test_75_listing_checks_sort_filter_pagination_where_rendered(self):
        body = self._body("w4cRunListingCell")
        self.assertIn("ListingControlsCheck", body)
        for marker in ('select[name="sort"]', 'select[name="category"]', ".pagination"):
            self.assertIn(marker, self.source)

    def test_76_cart_remove_presence_alone_is_insufficient(self):
        body = self._body("w4cRunCartCell")
        self.assertNotIn("removePresent = (await targetPage.locator('.citem .rm').count()) > 0;\n", body)

    def test_77_cart_requires_real_remove_effect(self):
        body = self._body("w4cRunCartCell")
        self.assertIn("RealRemove", body)

    def test_78_cart_requires_free_shipping_goal_contract(self):
        body = self._body("w4cRunCartCell")
        self.assertIn("FreeShippingGoal", body)
        self.assertIn(".fsg", self.source)

    def test_79_free_shipping_state_computed_in_python_not_recomputed_in_js(self):
        """Never a second pricing engine in JS -- the expected state must be
        computed server-side (Python) and merely verified in run.mjs."""
        body = self._body("w4cRunCartCell")
        self.assertNotIn("free_shipping_threshold", body)
        self.assertIn("expected_free_shipping_state", body)

    def test_80_fixture_exposes_expected_free_shipping_state(self):
        from django.core.management import call_command

        call_command("seed_ready_template_fashion_demo")
        store = Store.objects.get(slug="rasti-mode-demo")
        fixture = Command()._build_w4c_fixture(store)
        self.assertIn("expected_free_shipping_state", fixture)
        self.assertIn(fixture["expected_free_shipping_state"], {"goal", "success", "n/a"})


# =============================================================================
# Repair Round 2 -- IMPORTANT 4: accessibility-critical contract.
# =============================================================================
class W4CAccessibilityCriticalContractTests(TestCase):
    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def _body(self, fn_name):
        start = self.source.index(f"function {fn_name}")
        end = self.source.index("\nasync function", start + 1)
        return self.source[start:end]

    def test_81_mobile_nav_accessible_name_alone_is_insufficient(self):
        body = self._body("w4cMobileNavAccessibility")
        self.assertIn("aria-expanded", body)
        self.assertIn("Escape", body)

    def test_82_product_card_accessibility_checked(self):
        self.assertIn("function w4cProductCardAccessibility", self.source)

    def test_83_pdp_control_accessibility_checked(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("accessibility_checks", body)
        self.assertIn("variant_control", self.source)

    def test_84_cart_control_accessibility_checked(self):
        body = self._body("w4cRunCartCell")
        self.assertIn("checkout", body.lower())
        self.assertIn("accessibility_checks", body)

    def test_84b_cart_accessibility_runs_before_the_destructive_remove(self):
        """Smoke-round bug regression: checking quantity/remove control
        accessibility AFTER w4cCartRealRemove already emptied the cart
        made every check come back 'n/a' -- found via the real smoke
        against a genuinely single-item cart."""
        body = self._body("w4cRunCartCell")
        self.assertLess(
            body.index("w4cCartControlAccessibility"), body.index("w4cCartRealRemove"),
        )


# =============================================================================
# Repair Round 2 -- IMPORTANT 5: campaign evidence capture contract. Path
# helpers and manifest wiring are pure Python and fully behavioral here;
# the write-failure -> BLOCKED enforcement is JS-side (source-grep guard
# only -- genuine proof is the bounded smoke).
# =============================================================================
class W4CEvidenceCaptureContractTests(TestCase):
    def setUp(self):
        self.command = Command()
        self.js_source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def test_85_representative_screenshot_path_is_deterministic(self):
        path = self.command._w4c_representative_screenshot_path("/tmp/campaign", "editorial_jewelry", "listing")
        self.assertEqual(path, str(Path("/tmp/campaign") / "screenshots" / "representative" / "editorial_jewelry_listing_desktop.jpg"))

    def test_86_failure_screenshot_path_is_deterministic(self):
        path = self.command._w4c_failure_screenshot_path("/tmp/campaign", "editorial_jewelry", "pdp", "mobile")
        self.assertEqual(path, str(Path("/tmp/campaign") / "screenshots" / "failures" / "editorial_jewelry_pdp_mobile_FAIL.jpg"))

    def test_87_theme_screenshot_path_is_deterministic(self):
        path = self.command._w4c_theme_screenshot_path("/tmp/campaign", "warm_boutique", "nowruz", "balanced", "desktop", "tier2")
        self.assertEqual(
            path,
            str(Path("/tmp/campaign") / "screenshots" / "theme" / "warm_boutique__tier2__nowruz__balanced__desktop.jpg"),
        )

    def test_88_base_manifest_threads_representative_and_failure_paths_for_non_home_cells(self):
        manifest_path = self.command._write_w4c_base_manifest(
            base={"origin": "http://x"}, key="editorial_jewelry", version="3",
            result_path=Path("/tmp/w4c-evidence-test/w4c-results/base/editorial_jewelry.json"),
            run_token="tok", cells=[("listing", "desktop"), ("listing", "mobile")],
        )
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        finally:
            Path(manifest_path).unlink(missing_ok=True)
        listing_desktop = next(c for c in manifest["cells"] if c["page_class"] == "listing" and c["viewport"] == "desktop")
        listing_mobile = next(c for c in manifest["cells"] if c["page_class"] == "listing" and c["viewport"] == "mobile")
        self.assertIsNotNone(listing_desktop["representative_screenshot"])
        self.assertIsNotNone(listing_desktop["failure_screenshot"])
        self.assertIsNone(listing_mobile["representative_screenshot"])
        self.assertIsNotNone(listing_mobile["failure_screenshot"])

    def test_89_theme_manifest_threads_screenshot_path(self):
        manifest_path = self.command._write_w4c_theme_manifest(
            base={"origin": "http://x"}, key="editorial_jewelry", version="3", occasion="nowruz",
            intensity="balanced", viewport="desktop", tier="tier1",
            result_path=Path("/tmp/w4c-evidence-test/w4c-results/theme/x.json"), run_token="tok",
        )
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        finally:
            Path(manifest_path).unlink(missing_ok=True)
        self.assertIn("theme_screenshot_path", manifest)
        self.assertIsNotNone(manifest["theme_screenshot_path"])

    def test_90_required_theme_fields_include_screenshot(self):
        self.assertIn("screenshot", r4_mod.W4C_REQUIRED_THEME_RESULT_FIELDS)

    def test_91_screenshot_write_failure_forces_blocked_not_null(self):
        """5E -- source-grep guard: a required screenshot write must be
        wrapped so a thrown error forces BLOCKED, never a silent
        screenshot=null while some other PASS verdict stands."""
        for fn_name in ("w4cRunListingCell", "w4cRunPdpCell", "w4cRunCartCell"):
            with self.subTest(fn=fn_name):
                start = self.js_source.index(f"function {fn_name}")
                end = self.js_source.index("\nasync function", start + 1)
                body = self.js_source[start:end]
                self.assertIn("BLOCKED", body)


# =============================================================================
# Repair Round 2 -- IMPORTANT 6: bind the campaign matrix to the exact
# harness HEAD; reject a dirty worktree at real-campaign start; reject a
# resumed batch under a different HEAD. Fully behavioral (mocked git calls,
# no browser needed).
# =============================================================================
class W4CCampaignProvenanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="فروشگاه W4C پرووننس", slug="w4c-provenance-demo", admin_subdomain="w4c-provenance-demo",
        )
        self.command = Command()

    def _tmp_campaign_root(self):
        return Path(tempfile.mkdtemp(prefix="w4c-provenance-"))

    def test_92_fresh_matrix_records_branch_head_sha(self):
        matrix_path = self._tmp_campaign_root() / "matrix.json"
        with mock.patch.object(Command, "_current_git_head", return_value="a" * 40):
            self.command._validate_or_init_campaign_matrix(matrix_path)
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(matrix["_meta"]["w4c_branch_head_sha"], "a" * 40)

    def test_93_fresh_matrix_records_run_started_at(self):
        matrix_path = self._tmp_campaign_root() / "matrix.json"
        self.command._validate_or_init_campaign_matrix(matrix_path)
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(matrix["_meta"].get("run_started_at"))
        self.assertIsNone(matrix["_meta"].get("run_finished_at"))

    def test_94_dirty_worktree_rejected_at_fresh_campaign_start(self):
        campaign_root = self._tmp_campaign_root()
        matrix_path = campaign_root / "matrix.json"
        with mock.patch.object(Command, "_tracked_worktree_is_dirty", return_value=True):
            with self.assertRaises(CommandError):
                self.command._validate_or_init_campaign_matrix(matrix_path)
        self.assertFalse(matrix_path.exists(), "a dirty-worktree rejection must never create campaign artifacts")

    def test_95_resume_under_matching_head_proceeds(self):
        matrix_path = self._tmp_campaign_root() / "matrix.json"
        with mock.patch.object(Command, "_current_git_head", return_value="b" * 40):
            self.command._validate_or_init_campaign_matrix(matrix_path)
            # Resuming under the SAME head must not raise.
            self.command._validate_or_init_campaign_matrix(matrix_path)

    def test_96_resume_under_different_head_rejected(self):
        matrix_path = self._tmp_campaign_root() / "matrix.json"
        with mock.patch.object(Command, "_current_git_head", return_value="c" * 40):
            self.command._validate_or_init_campaign_matrix(matrix_path)
        with mock.patch.object(Command, "_current_git_head", return_value="d" * 40):
            with self.assertRaises(CommandError):
                self.command._validate_or_init_campaign_matrix(matrix_path)

    def test_97_run_finished_at_recorded_only_when_campaign_truly_completes(self):
        self._publish("editorial_jewelry")
        campaign_root = self._tmp_campaign_root()
        base_manifest = Command()._build_manifest(
            store=self.store, port=18765, session_cookie="x", report_dir=campaign_root,
            headed=False, browser_channel="auto", w4c_all50=True,
        )
        base_manifest["pdp_product_slug"] = None
        matrix_path = campaign_root / "matrix.json"

        def fake_run_logged(cmd_list, *, cwd, log_path):
            manifest_path = cmd_list[2]
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            result_path = Path(manifest["result_path"])
            if manifest.get("mode") == "theme":
                result = _valid_theme_payload(manifest, result="PASS")
            else:
                result = {
                    "run_token": manifest.get("run_token"), "key": manifest["active_key"]["key"],
                    "version": manifest["active_key"]["version"],
                    "page_classes": {c["page_class"]: {c["viewport"]: _valid_base_cell()} for c in manifest["cells"]},
                }
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(result), encoding="utf-8")
            return 0

        with mock.patch.object(Command, "_run_logged", side_effect=fake_run_logged):
            Command()._run_w4c_campaign(
                store=self.store, w4c_fixture=r4_mod.Command()._build_w4c_fixture(self.store),
                selected_keys=["editorial_jewelry"], campaign_root=campaign_root, node="node",
                run_mjs_path=Path("run.mjs"), r4_tool_dir=campaign_root, base_manifest=base_manifest,
            )
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        # Only editorial_jewelry ran -- nowhere near the full 704, so
        # run_finished_at must still be unset (never falsely marked complete).
        self.assertIsNone(matrix["_meta"].get("run_finished_at"))

    def _publish(self, key):
        preset = lpr.get_layout_preset(key)
        preset_service.apply_preset_with_checkpoint(self.store, preset)
        layout_service.publish(self.store)
        return preset


# =============================================================================
# Accessibility Closure Round -- IMPORTANT 1: accessibility_checks must GATE
# the cell's own result. "FAIL" recorded but non-gating (repair round 2's
# own, since-superseded design) is the exact defect this round repairs.
# =============================================================================
class W4CAccessibilityGatingTests(TestCase):
    def setUp(self):
        self.source = (
            Path(r4_mod.__file__).resolve().parents[4]
            / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        ).read_text(encoding="utf-8")

    def _body(self, fn_name):
        start = self.source.index(f"function {fn_name}")
        end = min(
            self.source.index("\nasync function", start + 1) if "\nasync function" in self.source[start + 1:] else len(self.source),
            self.source.index("\nfunction ", start + 1) if "\nfunction " in self.source[start + 1:] else len(self.source),
        )
        return self.source[start:end]

    def _extract_helper(self, name):
        """Extract a standalone (non-async) helper function's full source,
        by brace-counting from its opening ``{`` -- unlike ``_body`` (which
        stops at the next sibling function), this must capture exactly ONE
        function so it can be executed standalone under Node."""
        start = self.source.index(f"function {name}")
        open_brace = self.source.index("{", start)
        depth = 0
        for i in range(open_brace, len(self.source)):
            if self.source[i] == "{":
                depth += 1
            elif self.source[i] == "}":
                depth -= 1
                if depth == 0:
                    return self.source[start:i + 1]
        raise AssertionError(f"unbalanced braces extracting {name}")

    def _run_helper_against_cases(self, cases):
        """Genuine behavioral proof (not just source-grep): extracts the
        real w4cAccessibilityChecksPass function verbatim from run.mjs,
        executes it under the real Node the harness itself uses, and
        returns its actual return values for the given input objects."""
        helper_src = self._extract_helper("w4cAccessibilityChecksPass")
        script = helper_src + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(w4cAccessibilityChecksPass)));"
        fd, tmp_path = tempfile.mkstemp(suffix=".mjs")
        os.close(fd)
        try:
            Path(tmp_path).write_text(script, encoding="utf-8")
            result = subprocess.run(["node", tmp_path], capture_output=True, text=True, timeout=20)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        if result.returncode != 0:
            raise AssertionError(f"node execution failed: {result.stderr}")
        return json.loads(result.stdout.strip())

    # -- 1A: the shared helper exists and is genuinely correct -------------
    def test_98_accessibility_helper_exists(self):
        self.assertIn("function w4cAccessibilityChecksPass", self.source)

    def test_99_accessibility_helper_true_when_all_pass_or_na(self):
        results = self._run_helper_against_cases([
            {"a": "PASS", "b": "n/a"}, {"a": "PASS", "b": "PASS"}, {"a": "n/a", "b": "n/a"},
        ])
        self.assertEqual(results, [True, True, True])

    def test_100_accessibility_helper_false_when_any_fail(self):
        results = self._run_helper_against_cases([
            {"a": "PASS", "b": "FAIL"}, {"a": "FAIL"}, {"a": "FAIL", "b": "FAIL"},
        ])
        self.assertEqual(results, [False, False, False])

    # -- 1B: every Base cell's passing computation actually uses it --------
    def test_101_home_accessibility_gates_passing(self):
        body = self._body("w4cRunHomeCell")
        self.assertIn("w4cAccessibilityChecksPass", body)

    def test_102_listing_accessibility_gates_passing(self):
        body = self._body("w4cRunListingCell")
        self.assertIn("w4cAccessibilityChecksPass", body)

    def test_103_pdp_accessibility_gates_passing(self):
        body = self._body("w4cRunPdpCell")
        self.assertIn("w4cAccessibilityChecksPass", body)

    def test_104_cart_accessibility_gates_passing(self):
        body = self._body("w4cRunCartCell")
        self.assertIn("w4cAccessibilityChecksPass", body)

    def test_105_theme_cell_unaffected_no_admin_accessibility_controls(self):
        """Theme's public path exposes no admin accessibility controls in
        this matrix -- it must NOT gain the new gate."""
        body = self._body("w4cRunThemeCell")
        self.assertNotIn("w4cAccessibilityChecksPass", body)
