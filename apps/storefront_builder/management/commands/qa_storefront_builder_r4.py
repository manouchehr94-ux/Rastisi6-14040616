from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry
from apps.storefront_builder.section_registry import BRAND_CAROUSEL_DISPLAY_MODES
from apps.storefront_builder.models import StorefrontEditHistoryEntry, StorefrontLayout
from apps.storefront_builder.services import appearance_authority_service, container_service, layout_service, preset_service
from apps.storefront_builder.storefront_appearance.persistence import load_store_appearance_manifest
from apps.stores.models import Store, StoreMembership

# -- P5-W4C (Implementation Round 1) -- bounded --w4c-all50 extension of
# this SAME command. See docs/superpowers/plans/2026-09-17-phase5-w4c-all50-
# browser-certification.md sections 1/3/9/13/15 for the approved contract
# these constants encode. -------------------------------------------------
W4C_MATRIX_SCHEMA_VERSION = "w4c-matrix-v1"
W4C_CERTIFIED_BASE_SHA = "3a4fe9070584655548bae5a9bb574f3415bbf580"
W4C_TOTAL_CELLS_EXPECTED = 704
W4C_PAGE_CLASSES = ("home", "listing", "pdp", "cart")
W4C_VIEWPORTS = ("desktop", "tablet", "mobile")
W4C_TIER1_OCCASION_CYCLE = ("nowruz", "ramadan", "muharram")
W4C_TIER2_KEYS = ("warm_boutique", "beauty_dew")
W4C_TIER2_OCCASIONS = ("nowruz", "ramadan", "muharram")
W4C_TIER2_INTENSITIES = ("subtle", "balanced", "strong")
W4C_HERO_SECTION_KEY = "hero_banner"

# -- Code Review Repair Round 1 -- CRITICAL 1 (never accept a stale result
# file) / IMPORTANT 4 (matrix schema validator). -------------------------
W4C_VALID_CELL_RESULTS = frozenset({"PASS", "FAIL", "BLOCKED"})
W4C_REQUIRED_BASE_CELL_FIELDS = (
    "http_status", "rtl", "overflow", "header_count", "footer_count",
    "bottom_nav_present", "bottom_nav_display", "rsec_count", "expected_rsec_count",
    "product_cards_present", "dead_href_count", "console_errors", "page_errors",
    "failed_requests", "accessibility_checks", "result", "screenshot",
)
W4C_REQUIRED_THEME_RESULT_FIELDS = (
    "http_status", "rtl", "overflow", "console_errors", "page_errors",
    "failed_requests", "result",
)


def _png_swatch(color):
    try:
        from PIL import Image  # noqa: WPS433 (local import; project dep)
    except Exception:  # pragma: no cover — PIL is a project dependency
        return None
    from io import BytesIO
    buf = BytesIO()
    Image.new("RGB", (320, 180), color).save(buf, format="PNG")
    return buf.getvalue()


def _save_with_media_asset(obj, file_field: str, asset_field: str, filename: str, payload: bytes) -> None:
    """Pre-Task-10 corrective closure (Item 3) — module-level so both
    ``_prepare_phase3_task6_family_gate`` and
    ``_prepare_phase3_final_remediation_family_gate`` share ONE
    implementation, never two copies of this same fixture-media fix.

    Saving only the legacy file field (``obj.<file_field>.save(...)``) and
    leaving ``<asset_field>`` (the MediaAsset FK) unset means
    ``layout_service._clone_section_scoped_media`` (the Publish→new-Draft
    clone step scenario 12/either family-certification gate triggers)
    silently drops the row — exactly why ``multi_banner``'s own
    certification broke once its gate started running after that clone
    (reproduced live). This mirrors ``media_views.py``'s OWN real
    production upload flow exactly (``_sync_media_assets_from_file_fields``):
    save the real file first, THEN create a ``MediaAsset`` pointing at that
    SAME saved path (no byte copy — ``image=obj.<file_field>.name``), THEN
    set the FK — never a second media-storage mechanism."""
    from django.core.files.base import ContentFile

    from apps.content.models import MediaAsset

    file_obj = getattr(obj, file_field)
    file_obj.save(filename, ContentFile(payload), save=False)
    obj.save()
    asset = MediaAsset.objects.create(store=obj.store, image=file_obj.name)
    setattr(obj, f"{asset_field}_id", asset.pk)
    obj.save(update_fields=[asset_field])


class Command(BaseCommand):
    """R4 Task-12 browser-QA orchestrator.

    This is the reproducible, committed entrypoint for the R4 Phase-1
    vertical-slice Playwright smoke (tools/storefront_builder_r4_qa/run.mjs).
    It exists as a *separate* command from
    apps.storefront_builder.management.commands.qa_storefront_builder rather
    than a flag/branch on that command because that command is hardcoded, end
    to end, to R3: it targets tools/storefront_builder_qa/run.mjs, its
    _build_manifest() emits an R3-shaped manifest (page_types/
    library_by_page/all_definitions/expected_registry_count) that R4's
    run.mjs does not read, and its _prepare_builder_sandbox() clears every
    Draft Section down to a single announcement_bar sentinel — it never
    places the hero_banner/brand_carousel sections or the catalog Products/
    Brands the R4 scenario matrix requires. Reusing it as-is would produce a
    Draft/manifest the R4 runner cannot use; changing it would edit R3's own
    QA command. This command instead mirrors its proven safety lifecycle
    (session-cookie auth, SQLite backup/restore, runserver start/stop, both
    always in ``finally``) for the R4 surface specifically, without touching
    the R3 command or any R4 view/service/model/template/JS/CSS.
    """

    help = (
        "Run the R4 Phase-1 vertical-slice browser QA "
        "(tools/storefront_builder_r4_qa/run.mjs) against a disposable local "
        "SQLite Store, with byte-for-byte DB backup/restore around the run."
    )

    #: Phase 5 Task 6 (--showcase) — suffix for the merchant ADMIN host the
    #: browser uses to reach the R4 editor. The admin portal resolves the Store
    #: from its ``admin_subdomain`` (``<admin_subdomain>.rastisi.localhost``),
    #: which works in a multi-Store sandbox (unlike the 127.0.0.1 single-Store
    #: compatibility fallback the default run relies on). The full host is
    #: computed per-Store in _build_manifest; mapped to 127.0.0.1 by the
    #: runner's chromium --host-resolver-rules. ``.rastisi.localhost`` is in
    #: DEBUG ALLOWED_HOSTS. No StoreDomain seeding needed.
    SHOWCASE_QA_HOST_SUFFIX = ".rastisi.localhost"

    def add_arguments(self, parser):
        parser.add_argument("--store-slug", required=True)
        parser.add_argument("--username", required=True, help="Existing is_staff user with an active membership on the Store.")
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument("--headed", action="store_true", help="Show the QA browser while it runs.")
        parser.add_argument(
            "--browser-channel",
            default="auto",
            choices=("auto", "chrome", "msedge"),
            help="Use installed Chrome/Edge/Chromium. No Playwright browser download is required.",
        )
        parser.add_argument(
            "--install-node-deps",
            action="store_true",
            help="Run npm install in tools/storefront_builder_qa (the shared playwright-core dependency both R3 and R4 runners reuse) before the browser QA.",
        )
        parser.add_argument("--report-dir", default="")
        parser.add_argument(
            "--showcase",
            action="store_true",
            help=(
                "Phase 5 Task 6 — opt-in Storefront Showcase creation-facade "
                "browser scenario (desktop 1440 + mobile 390, RTL). Also seeds "
                "one active MerchantCollection into the sandbox so the "
                "Collections choice is legal. Off by default — existing "
                "scenarios/behavior are unchanged. NOTE: currently REQUIRES "
                "--phase3 as well (the runner eagerly bootstraps Phase-3 "
                "fixtures at import); the command fails fast otherwise. Typical "
                "Task-6-only run: R4_QA_ONLY_SCENARIO=task6-showcase "
                "manage.py qa_storefront_builder_r4 --phase3 --showcase ..."
            ),
        )
        parser.add_argument(
            "--phase3",
            action="store_true",
            help=(
                "Opt-in Phase 3 responsive capture: the runner iterates the "
                "three Phase 3 viewports and captures to the report dir. "
                "Off by default — existing scenarios/behavior are unchanged."
            ),
        )
        parser.add_argument(
            "--simulate-failure-after-backup",
            action="store_true",
            help=(
                "QA-safety self-test only: raise immediately after the pre-run "
                "SQLite backup (before the runserver is even started) to prove "
                "the restore step runs from `finally` on failure, not only on "
                "success. Never pass this for a real QA run."
            ),
        )
        parser.add_argument(
            "--w4c-all50",
            action="store_true",
            help=(
                "P5-W4C -- opt-in all-50-Ready-Template browser certification "
                "campaign (704 cells). Bypasses the legacy R4 sandbox in favor "
                "of a real published-Template fixture. Off by default -- "
                "existing R4 QA scenarios/behavior are completely unchanged."
            ),
        )
        parser.add_argument(
            "--only",
            default="",
            help=(
                "P5-W4C only -- a comma-separated subset of Ready Template keys "
                "to certify in this invocation (base + Theme cells alike). Has "
                "no effect unless --w4c-all50 is also passed."
            ),
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This disposable browser QA is only permitted with DEBUG=True.")

        # Phase 5 Task 6 — the current run.mjs eagerly builds phase3-only edit
        # matrices at module import (FINAL_REMEDIATION_SCALAR_EDITS reads
        # manifest.phase3_fixture.final_remediation_families), so the runner
        # cannot even load without --phase3. Rather than a broad phase3
        # refactor in Task 6, fail fast with a truthful message: the Showcase
        # scenario must be run as `--phase3 --showcase`.
        if options["showcase"] and not options["phase3"]:
            raise CommandError(
                "--showcase currently requires --phase3 as well: the R4 QA runner "
                "(tools/storefront_builder_r4_qa/run.mjs) eagerly requires the "
                "Phase-3 fixture bootstrap at import time. Re-run as: "
                "manage.py qa_storefront_builder_r4 --phase3 --showcase ... "
                "(optionally with R4_QA_ONLY_SCENARIO=task6-showcase to run only "
                "the Task-6 scenario)."
            )

        if options["w4c_all50"] and options["showcase"]:
            raise CommandError("--w4c-all50 and --showcase are mutually exclusive.")
        if options["w4c_all50"] and not options["report_dir"]:
            raise CommandError(
                "--w4c-all50 requires --report-dir (the shared CAMPAIGN_REPORT_ROOT "
                "every invocation of one campaign must pass) -- it never falls back "
                "to a fresh, unshared timestamp directory."
            )

        base_dir = Path(settings.BASE_DIR).resolve()
        shared_tool_dir = base_dir / "tools" / "storefront_builder_qa"
        r4_tool_dir = base_dir / "tools" / "storefront_builder_r4_qa"
        node_script = r4_tool_dir / "run.mjs"
        if not node_script.exists():
            raise CommandError(f"R4 QA runner not found: {node_script}")

        store = self._get_store(options["store_slug"])
        user = self._get_user(options["username"], store)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_dir = (
            Path(options["report_dir"]).expanduser().resolve()
            if options["report_dir"]
            else base_dir.parent / "RastiSi4_r4_qa_reports" / stamp
        )
        report_dir.mkdir(parents=True, exist_ok=True)

        node = shutil.which("node")
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if node is None:
            raise CommandError("Node.js not found; the R4 browser QA cannot run without it.")
        if options["install_node_deps"]:
            if npm is None:
                raise CommandError("npm not found.")
            self.stdout.write(self.style.WARNING("Installing the shared browser QA dependency (playwright-core)..."))
            install_code = self._run_logged(
                [npm, "install", "--no-audit", "--no-fund"],
                cwd=shared_tool_dir,
                log_path=report_dir / "npm-install.log",
            )
            if install_code:
                raise CommandError(f"npm install failed; log: {report_dir / 'npm-install.log'}")
        if not (shared_tool_dir / "node_modules" / "playwright-core").exists():
            raise CommandError(
                "playwright-core is not installed. Run once:\n"
                f"  cd {shared_tool_dir}\n"
                "  npm install\n"
                "then re-run this R4 QA command. (R4's runner deliberately reuses "
                "this dependency instead of a second package.json.)"
            )

        if not self._port_is_free(options["port"]):
            raise CommandError(f"Port {options['port']} is already in use; pass a different --port.")

        db_path = self._sqlite_db_path()
        backup_dir = base_dir.parent / "RastiSi4_r4_qa_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_backup = backup_dir / f"storefront-builder-r4-qa-{stamp}.sqlite3"
        self._sqlite_backup(db_path, db_backup)
        with open(db_backup, "rb") as fh:
            pre_run_sha256 = hashlib.sha256(fh.read()).hexdigest()
        (report_dir / "RECOVERY.txt").write_text(
            "If QA was interrupted and the automatic restore did not run, close "
            "every runserver process first, then:\n"
            f'Copy-Item "{db_backup}" "{db_path}" -Force\n'
            f"pre_run_sha256: {pre_run_sha256}\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.WARNING(f"Safety DB backup: {db_backup} (sha256={pre_run_sha256})"))

        server_proc = None
        server_log_handle = None
        runtime_manifest_path = None
        browser_exit = 1
        w4c_aggregate = None
        try:
            if options["w4c_all50"]:
                fixture = self._prepare_w4c_certification_fixture(store)
                w4c_fixture = self._build_w4c_fixture(store)
                base_manifest = self._build_manifest(
                    store=store,
                    port=options["port"],
                    session_cookie=None,
                    report_dir=report_dir,
                    headed=options["headed"],
                    browser_channel=options["browser_channel"],
                    w4c_all50=True,
                )
                base_manifest["pdp_product_slug"] = w4c_fixture["pdp_product_slug"]
                (report_dir / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

                self.stdout.write(self.style.MIGRATE_HEADING("W4C all-50 browser certification"))
                server_log_handle = (report_dir / "runserver.log").open("w", encoding="utf-8", errors="replace")
                server_proc = subprocess.Popen(
                    [sys.executable, "manage.py", "runserver", f"127.0.0.1:{options['port']}", "--noreload"],
                    cwd=base_dir,
                    stdout=server_log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                if not self._wait_for_port(options["port"], server_proc, timeout=20):
                    raise CommandError(f"W4C runserver did not come up; log: {report_dir / 'runserver.log'}")

                selected_keys = (
                    [k.strip() for k in options["only"].split(",") if k.strip()]
                    if options["only"] else None
                )
                w4c_aggregate = self._run_w4c_campaign(
                    store=store,
                    w4c_fixture=w4c_fixture,
                    selected_keys=selected_keys,
                    campaign_root=report_dir,
                    node=node,
                    run_mjs_path=node_script,
                    r4_tool_dir=r4_tool_dir,
                    base_manifest=base_manifest,
                )
                browser_exit = 0
            else:
                fixture = self._prepare_r4_sandbox(
                    store, user, phase3=options["phase3"], showcase=options["showcase"],
                )

                if options["phase3"]:
                    tenant_negatives = self._phase3_tenant_negatives(store)
                    (report_dir / "tenant_negatives.json").write_text(
                        json.dumps(tenant_negatives, ensure_ascii=False, indent=2), encoding="utf-8",
                    )
                    self.stdout.write(self.style.WARNING(f"Tenant/unauthorized negatives: {tenant_negatives}"))

                if options["simulate_failure_after_backup"]:
                    raise CommandError(
                        "Simulated failure after backup AND after sandbox prep "
                        "(--simulate-failure-after-backup). This is expected: it exists to "
                        "prove the `finally` restore below actually undoes real DB changes "
                        "(the sandbox prep above just cleared/rewrote Draft sections) on a "
                        "failure path, not only after a clean exit."
                    )

                session_cookie = self._make_session_cookie(user)
                manifest = self._build_manifest(
                    store=store,
                    port=options["port"],
                    session_cookie=session_cookie,
                    report_dir=report_dir,
                    headed=options["headed"],
                    browser_channel=options["browser_channel"],
                    phase3=options["phase3"],
                    phase3_fixture=fixture.get("phase3") if options["phase3"] else None,
                    showcase=options["showcase"],
                )
                fd, runtime_manifest_path = tempfile.mkstemp(prefix="rastisi-r4-qa-", suffix=".json")
                os.close(fd)
                Path(runtime_manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                (report_dir / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

                self.stdout.write(self.style.MIGRATE_HEADING("R4 Phase-1 vertical-slice browser QA"))
                server_log_handle = (report_dir / "runserver.log").open("w", encoding="utf-8", errors="replace")
                server_proc = subprocess.Popen(
                    [sys.executable, "manage.py", "runserver", f"127.0.0.1:{options['port']}", "--noreload"],
                    cwd=base_dir,
                    stdout=server_log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                if not self._wait_for_port(options["port"], server_proc, timeout=20):
                    raise CommandError(f"R4 QA runserver did not come up; log: {report_dir / 'runserver.log'}")

                browser_exit = self._run_logged(
                    [node, str(node_script), runtime_manifest_path],
                    cwd=r4_tool_dir,
                    log_path=report_dir / "browser.log",
                )
        finally:
            if server_proc is not None:
                self._stop_process(server_proc)
            if server_log_handle is not None:
                server_log_handle.close()
            if runtime_manifest_path:
                Path(runtime_manifest_path).unlink(missing_ok=True)
            # Exact local-state restoration on BOTH success and failure —
            # this `finally` runs even if the block above raised (including
            # --simulate-failure-after-backup, and including a non-zero
            # runserver/Playwright exit).
            self._sqlite_restore(db_backup, db_path)
            with open(db_path, "rb") as fh:
                post_restore_sha256 = hashlib.sha256(fh.read()).hexdigest()
            restored_ok = post_restore_sha256 == pre_run_sha256
            (report_dir / "db-restore-proof.json").write_text(
                json.dumps(
                    {
                        "db_backup": str(db_backup),
                        "pre_run_sha256": pre_run_sha256,
                        "post_restore_sha256": post_restore_sha256,
                        "match": restored_ok,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            style = self.style.SUCCESS if restored_ok else self.style.ERROR
            self.stdout.write(style(f"Local database restored — pre={pre_run_sha256} post={post_restore_sha256} match={restored_ok}"))
            if not restored_ok:
                raise CommandError("DB restore verification FAILED — pre-run and post-restore SHA-256 do not match.")

        if options["w4c_all50"]:
            aggregate = w4c_aggregate
            campaign_complete = (
                aggregate["total_cells_recorded"] == W4C_TOTAL_CELLS_EXPECTED
                and not aggregate["missing_cells"]
                and not aggregate["duplicate_cells"]
            )
            if not campaign_complete:
                if not options["only"]:
                    raise CommandError(f"W4C: INCOMPLETE -- full run did not record all 704 cells -- {aggregate}")
                self.stdout.write(self.style.SUCCESS(
                    "W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- "
                    f"selected_keys={options['only']}, "
                    f"cells_recorded_this_run={aggregate['cells_recorded_this_run']}, "
                    f"cumulative_total_cells_recorded={aggregate['total_cells_recorded']}/{W4C_TOTAL_CELLS_EXPECTED}, "
                    f"cumulative_missing={len(aggregate['missing_cells'])}, "
                    f"cumulative_fail_count={aggregate['fail_count']}, "
                    f"cumulative_blocked_count={aggregate['blocked_count']}"
                ))
                return
            if aggregate["fail_count"] > 0 or aggregate["blocked_count"] > 0:
                raise CommandError(
                    f"W4C: certification did not pass -- {aggregate['fail_count']} FAIL, "
                    f"{aggregate['blocked_count']} BLOCKED"
                )
            self.stdout.write(self.style.SUCCESS(
                f"W4C: {W4C_TOTAL_CELLS_EXPECTED}/{W4C_TOTAL_CELLS_EXPECTED} cells recorded, 0 FAIL, 0 BLOCKED -- PASS"
            ))
            return

        browser_result_path = report_dir / "r4-browser-result.json"
        browser_payload = None
        if browser_result_path.exists():
            try:
                browser_payload = json.loads(browser_result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                browser_payload = None
        fail_count = int((browser_payload or {}).get("summary", {}).get("failed", 0))
        if browser_exit or fail_count:
            raise CommandError(f"R4 browser QA found problems — exit={browser_exit} failed={fail_count}. Report: {report_dir}")
        self.stdout.write(self.style.SUCCESS(f"R4 browser QA PASS. Report: {report_dir}"))

    # -- Store/user resolution (no second auth system — an existing is_staff
    #    user with an active membership must already exist; no password is
    #    ever set or read here) -------------------------------------------
    def _get_store(self, slug: str) -> Store:
        try:
            return Store.objects.get(slug=slug)
        except Store.DoesNotExist as exc:
            raise CommandError(f"Store with slug={slug!r} not found.") from exc

    def _get_user(self, username: str, store: Store):
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User {username!r} not found.") from exc
        if not user.is_staff:
            raise CommandError("The QA user must be is_staff=True.")
        membership = StoreMembership.objects.filter(
            store=store,
            user=user,
            status=StoreMembership.MembershipStatus.ACTIVE,
        ).first()
        if membership is None:
            raise CommandError("The QA user has no active membership on this Store.")
        return user

    def _make_session_cookie(self, user) -> str:
        client = Client()
        client.force_login(user)
        cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        if cookie is None:
            raise CommandError("Could not build the QA session cookie.")
        return cookie.value

    # -- Task 7 tenant/unauthorized negatives (Django test Client, not the
    #    browser — a real unauthenticated request through the actual view/
    #    permission stack, never a skipped fixture). ------------------------
    def _phase3_tenant_negatives(self, store: Store) -> dict:
        anon = Client(SERVER_NAME="127.0.0.1")
        anon_resp = anon.get("/admin-portal/storefront-builder/preview/?page=home", follow=False)
        anon_ok = anon_resp.status_code in (302, 403)
        return {
            "anonymous_preview_get": {
                "url": "/admin-portal/storefront-builder/preview/?page=home",
                "status_code": anon_resp.status_code,
                "rejected": anon_ok,
                "note": (
                    "Unauthenticated GET against the real Preview view/permission "
                    "stack via Django's test Client (not the browser, not a skipped "
                    "fixture) — expected 302 (redirect to login) or 403, never 200."
                ),
            },
        }

    # -- SQLite safety lifecycle (same technique as qa_storefront_builder.py) --
    def _sqlite_db_path(self) -> Path:
        connection = connections["default"]
        if connection.vendor != "sqlite":
            raise CommandError("This disposable browser QA only runs against local SQLite, so restore can be exact and atomic.")
        name = str(connection.settings_dict["NAME"])
        if name == ":memory:":
            raise CommandError("An in-memory SQLite database is not supported for this QA.")
        return Path(name).resolve()

    def _sqlite_backup(self, source: Path, target: Path) -> None:
        connections.close_all()
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)

    def _sqlite_restore(self, backup: Path, target: Path) -> None:
        connections.close_all()
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        shutil.copy2(backup, target)

    # -- R4-specific deterministic fixture -----------------------------------
    def _prepare_r4_sandbox(self, store: Store, user, *, phase3: bool = False, showcase: bool = False) -> dict:
        layout = layout_service.get_or_create_layout(store)
        layout.r4_editor_enabled = True
        # Deterministic baseline: Publish must be a real, observable state
        # transition during the run, so it must start unpublished, with no
        # leftover Draft/Published state from an earlier QA session.
        if layout.published_version_id:
            old_published = layout.published_version
            layout.published_version = None
            old_published.delete()
        if layout.draft_version_id:
            old_draft = layout.draft_version
            layout.draft_version = None
            layout.save(update_fields=["r4_editor_enabled", "published_version", "draft_version", "updated_at"])
            old_draft.delete()
        else:
            layout.save(update_fields=["r4_editor_enabled", "published_version", "draft_version", "updated_at"])

        draft = layout_service.get_or_create_draft(store, user=user)
        StorefrontEditHistoryEntry.objects.filter(draft_version=draft).delete()

        home_page = draft.get_page("home")
        home_page.sections.all().delete()
        home_page.containers.all().delete()

        def place(section_key: str):
            definition = section_registry.get_definition(section_key)
            order = home_page.sections.count()
            from apps.storefront_builder.models import StorefrontSection

            section = StorefrontSection.objects.create(
                page=home_page, section_key=section_key, order=order, settings=definition.default_settings(),
            )
            container = container_service.create_empty_container(home_page, "single")
            cell = container.cells.order_by("order", "id").first()
            container_service.place_section(cell, section)
            return section

        hero = place("hero_banner")
        brand_carousel = place("brand_carousel")

        # Enough real, selectable catalog data for two independent manual-
        # Picker proofs (>=2 Products, >=2 Brands), searchable by the same
        # sentinel keyword the browser runner uses.
        vendor, _ = Vendor.objects.get_or_create(store=store, slug="t12-vendor", defaults=dict(name="فروشنده T12"))
        category, _ = Category.objects.get_or_create(store=store, slug="t12-category", defaults=dict(name="دسته T12"))
        for i in range(1, 6):
            Product.objects.get_or_create(
                store=store, slug=f"t12-product-{i}",
                defaults=dict(
                    vendor=vendor, category=category, name=f"کالای تی۱۲ شماره {i}",
                    sku=f"SKU-T12-{i}", price=Decimal("120000"), status=Product.Status.ACTIVE,
                ),
            )
        for i in range(1, 6):
            Brand.objects.get_or_create(store=store, slug=f"t12-brand-{i}", defaults=dict(name=f"برند تی۱۲ شماره {i}"))

        # Phase 5 Task 6 (opt-in --showcase) — the default sandbox has Products/
        # Categories/Brands but no MerchantCollection, so the Collections
        # Showcase choice would (correctly) be filtered out as unavailable.
        # Seed exactly one active collection so all four choices are legal.
        # Guarded: a non-showcase run's fixture/Draft is byte-for-byte unchanged.
        if showcase:
            from apps.catalog.models import MerchantCollection, MerchantCollectionItem
            collection, _ = MerchantCollection.objects.get_or_create(
                store=store, slug="t6-showcase-collection",
                defaults=dict(name="کالکشن ویترین T6", is_active=True),
            )
            for product in Product.objects.filter(store=store, slug__in=["t12-product-1", "t12-product-2"]):
                MerchantCollectionItem.objects.get_or_create(collection=collection, product=product)
            # The browser reaches the R4 editor via the Store's admin-subdomain
            # host (see SHOWCASE_QA_HOST_SUFFIX / _build_manifest); ensure the
            # Store actually has an admin_subdomain so that host resolves. No
            # StoreDomain seeding needed (admin portal resolves by subdomain).
            if not store.admin_subdomain:
                store.admin_subdomain = store.slug
                store.save(update_fields=["admin_subdomain"])

        fixture = {
            "hero_section_id": hero.pk,
            "brand_carousel_section_id": brand_carousel.pk,
            "draft_revision": draft.edit_revision,
        }

        # Task 3 "Brand gate" — heavier, phase3-only additions. Guarded so the
        # default (R3) run's Draft and fixture are byte-for-byte unchanged: on
        # a non-phase3 run this branch never executes.
        if phase3:
            fixture["phase3"] = self._prepare_phase3_brand_gate(store, user, draft)

        return fixture

    # -- Phase 3 (Task 3 "Brand gate") fixture --------------------------------
    def _prepare_phase3_brand_gate(self, store: Store, user, draft) -> dict:
        """Place a Draft ``brand_carousel`` on the five envelope pages the
        Brand browser-certification exercises (E1 home, E2 product_detail,
        E3 listing, E4 collection detail, E5 cart), give brands real logos
        (plus one deliberate no-logo brand for the name-fallback path), and
        stand up one active MerchantCollection host so ``/collections/…/``
        resolves. Returns the discovered ids the runner threads through the
        manifest. NEVER runs on the default R3 path."""
        from io import BytesIO

        from django.core.files.base import ContentFile

        from apps.catalog.models import MerchantCollection, MerchantCollectionItem, Product
        from apps.storefront_builder.models import StorefrontPage, StorefrontSection

        # A specific, ordered set of five brands the certification selects
        # (manual mode preserves this exact order). Four get a real PIL logo;
        # the fifth is left logo-less on purpose so the public name-fallback
        # (`span.brand-tile-name`) has a real subject to assert on.
        brand_slugs = [f"t12-brand-{i}" for i in range(1, 6)]
        brands = {b.slug: b for b in Brand.objects.filter(store=store, slug__in=brand_slugs)}
        selected = [brands[s] for s in brand_slugs if s in brands]
        ordered_slugs = [b.slug for b in selected]
        no_logo_brand = selected[-1]

        def _png_logo(color):
            try:
                from PIL import Image  # noqa: WPS433 (local import; test-only dep)
            except Exception:  # pragma: no cover — PIL is a project dependency
                return None
            buf = BytesIO()
            Image.new("RGB", (96, 48), color).save(buf, format="PNG")
            return buf.getvalue()

        logo_palette = ["#c0392b", "#2980b9", "#27ae60", "#8e44ad"]
        for idx, brand in enumerate(selected[:-1]):
            if brand.logo:  # already has one from an earlier run — leave it
                continue
            payload = _png_logo(logo_palette[idx % len(logo_palette)])
            if payload is not None:
                brand.logo.save(f"{brand.slug}.png", ContentFile(payload), save=True)
        # Guarantee the fallback brand truly has no logo (idempotent reruns).
        if no_logo_brand.logo:
            no_logo_brand.logo.delete(save=True)

        brand_ids = [b.pk for b in selected]

        # One active collection host so /collections/p3-collection-1/ resolves,
        # with a couple of members (the storefront-visible catalog products the
        # base fixture already created).
        member_products = list(
            Product.objects.filter(store=store, slug__in=["t12-product-1", "t12-product-2"]).order_by("slug")
        )
        collection, _ = MerchantCollection.objects.get_or_create(
            store=store, slug="p3-collection-1",
            defaults=dict(name="کالکشن پی۳ شماره ۱", is_active=True),
        )
        if not collection.is_active:
            collection.is_active = True
            collection.save(update_fields=["is_active"])
        for order, product in enumerate(member_products):
            MerchantCollectionItem.objects.get_or_create(
                collection=collection, product=product, defaults=dict(order=order),
            )

        product_slug = "t12-product-1"
        # The base fixture creates products with the default stock=0, which
        # would make the real add-to-cart raise UnavailableStockError. Give
        # the cart-flow product real stock so the E5 cart HTMX (add/update/
        # remove) exercises the genuine happy path.
        Product.objects.filter(store=store, slug=product_slug).update(stock=25)

        # A resolvable View-all destination (V02) for the grid/carousel
        # variants — points at the collection host above, so
        # resolve_destination_setting yields /collections/p3-collection-1/.
        destination = {
            "destination_type": "collection",
            "destination_id": collection.pk,
            "destination_external_url": "",
            "open_in_new_tab": False,
        }

        def _brand_settings(display_mode: str, page_type: str) -> dict:
            # grid/carousel carry a resolvable View-all destination (V02);
            # beauty_tabs stores show_view_all=True too (to prove the template
            # SUPPRESSES the anchor for beauty_tabs regardless of the flag),
            # but the template renders no `a.more` for it.
            return {
                "title": f"برندهای {page_type} {display_mode}",
                "display_mode": display_mode,
                "show_view_all": True,
                "brand_ids": list(brand_ids),
                "destination": dict(destination),
            }

        def place_variant(page, display_mode: str, page_type: str) -> int:
            order = page.sections.count()
            section = StorefrontSection.objects.create(
                page=page,
                section_key="brand_carousel",
                order=order,
                settings=_brand_settings(display_mode, page_type),
            )
            container = container_service.create_empty_container(page, "single")
            cell = container.cells.order_by("order", "id").first()
            container_service.place_section(cell, section)
            return section.pk

        variants = list(BRAND_CAROUSEL_DISPLAY_MODES)  # ("grid","carousel","beauty_tabs")

        def place_all_variants(page_type: str) -> dict:
            """Place one brand_carousel per variant on the page so a single
            published GET renders all three variants side by side (no
            re-publish loop needed to certify each variant)."""
            page = draft.get_page(page_type)
            ids = {}
            for display_mode in variants:
                ids[display_mode] = place_variant(page, display_mode, page_type)
            return ids

        # E1 home already carries the BASE fixture's own brand_carousel, which
        # scenarios 06/07 deliberately mutate (manual Picker reorder to a
        # 2-brand selection). We do NOT reuse it — instead we add three FRESH
        # phase3 brand_carousels (one per variant) on home too, each with the
        # full ordered five-brand selection, so the Brand-gate assertions are
        # never disturbed by (and never disturb) scenarios 06/07. The phase3
        # sections are told apart from the base one at assertion time by their
        # full five-brand tile count.
        envelopes = {
            "home": place_all_variants(StorefrontPage.PageType.HOME),
            "product_detail": place_all_variants(StorefrontPage.PageType.PRODUCT_DETAIL),
            "listing": place_all_variants(StorefrontPage.PageType.LISTING),
            "collection": place_all_variants(StorefrontPage.PageType.COLLECTION),
            "cart": place_all_variants(StorefrontPage.PageType.CART),
        }

        gate = {
            # brand_carousel section ids (in the DRAFT) per envelope page type,
            # keyed by variant display_mode: {envelope: {variant: section_pk}}
            "brand_section_ids": envelopes,
            # public route inputs the runner needs to reach each envelope
            "product_slug": product_slug,
            "collection_slug": collection.slug,
            # the ordered, selected brand ids + slugs + the deliberate no-logo
            # brand, so the runner can assert count/EXACT order and name-fallback
            "brand_ids": list(brand_ids),
            "brand_slugs": list(ordered_slugs),
            "no_logo_brand_id": no_logo_brand.pk,
            "no_logo_brand_name": no_logo_brand.name,
            # the resolved View-all target (V02) grid/carousel must render
            "view_all_url_path": f"/collections/{collection.slug}/",
            # the three variant values the certification cycles per envelope
            "variants": list(BRAND_CAROUSEL_DISPLAY_MODES),
        }
        # ---- Broken-image disposable fixture (Task 7). ----
        # A Brand whose ``logo`` FieldFile points at a file that was never
        # written to storage, isolated on the SEARCH page type — NOT one of
        # Brand's five certified envelopes (home/product_detail/listing/
        # collection/cart) above — so it can never interfere with the
        # existing certified public matrix. Distinct from the no-logo brand's
        # ``.brand-tile-name`` fallback (a supported path); this is the
        # UNSUPPORTED broken-URL path the inventory records has no explicit
        # fallback. Recorded separately, not asserted to succeed.
        broken_brand, _ = Brand.objects.get_or_create(
            store=store, slug="t12-brand-broken", defaults=dict(name="برند تصویر خراب"),
        )
        Brand.objects.filter(pk=broken_brand.pk).update(logo="brand_logos/qa-broken-nonexistent.png")
        search_page = draft.get_page(StorefrontPage.PageType.SEARCH)
        broken_section = StorefrontSection.objects.create(
            page=search_page,
            section_key="brand_carousel",
            order=search_page.sections.count(),
            settings={
                "title": "تصویر خراب QA",
                "display_mode": "grid",
                "show_view_all": False,
                "brand_ids": [broken_brand.pk],
                "destination": {
                    "destination_type": "none", "destination_id": None,
                    "destination_external_url": "", "open_in_new_tab": False,
                },
            },
        )
        broken_container = container_service.create_empty_container(search_page, "single")
        broken_cell = broken_container.cells.order_by("order", "id").first()
        container_service.place_section(broken_cell, broken_section)
        gate["broken_image_brand_id"] = broken_brand.pk

        # Task 5 "Collection gate" — additive, phase3-only. Placed alongside
        # the Brand gate on the SAME Draft (both publish together in one GET),
        # under a dedicated ``collection`` key so the Brand matrix inputs above
        # are untouched. The runner reads ``phase3_fixture.collection`` only for
        # the Collection matrix; the default R3 run never reaches this method.
        gate["collection"] = self._prepare_phase3_collection_gate(store, user, draft)
        # Phase 4 Task 6 — a SMALL representative set of Task-6 MIGRATE
        # families that scenarios 01-13/the Brand+Collection matrix never
        # exercise. Placed alongside everything above (additive, phase3-only;
        # the default R3 run never reaches this method either).
        gate["task6_families"] = self._prepare_phase3_task6_family_gate(draft)
        # Pre-Task-10 final remediation (Gap 2) — the remaining 15 MIGRATE
        # families family_certification_matrix.md tracked as NOT YET
        # CERTIFIED. Placed alongside everything above (additive, phase3-only;
        # the default R3 run never reaches this method either).
        gate["final_remediation_families"] = self._prepare_phase3_final_remediation_family_gate(draft)
        return gate

    def _prepare_phase3_final_remediation_family_gate(self, draft) -> dict:
        """Pre-Task-10 final remediation (Gap 2, corrected this session —
        see the "CORRECTIVE ITEM 1" continuation prompt) — one representative
        section per each of the 15 remaining MIGRATE families.

        The independent-review corrective pass explicitly rejected
        persistence-only proof as an acceptable certification for families
        whose real merchant-facing contract is RENDERING real content —
        classifying several of this session's ORIGINAL certifications as too
        weak (hero_banner/image_slider's visual proof deferred,
        amazing_offers/discounted_products never exercised with real
        discounted-catalog data, blog_posts never exercised with real Post
        rows, video_section deliberately avoiding a real embed). This method
        now places REAL fixture data for every one of those:

        - hero_banner (the EXISTING bootstrap section, not a new one — see
          below) and image_slider each get a real ``HeroSlide`` bound via
          the CANONICAL MediaAsset path (``_save_with_media_asset`` —
          reused here for the SAME reason ``_prepare_phase3_task6_family_
          gate``'s multi_banner fixture needed it: a legacy-file-field-only
          row does not survive this gate's Publish→new-Draft clone).
        - amazing_offers/discounted_products share ONE real discounted
          Product (``discount_percent__gt=0`` — ``render_service.py``'s own
          query for both).
        - blog_posts gets one real ``apps.blog.models.BlogPost`` row (a
          genuinely global, non-Store-scoped model — see
          ``_blog_posts_context``'s own docstring).
        - quick_links gets a real Menu + one real MenuItem (a Category
          destination, reusing the SAME demo Category
          ``_prepare_phase3_brand_gate`` already creates) — this is now the
          family's OWN edited field via the new ``menu_picker`` Inspector
          field type (see ``section_registry.QUICK_LINKS_SCHEMA``), not a
          QA-only fixture concern.
        - newest_products/best_sellers/promo_cards reuse catalog/category
          demo data that already exists by this point in fixture setup (no
          new fixture needed — their own real render proof is now a DOM
          assertion instead of persistence-only).

        Deliberately EXCLUDES ``hero_banner`` and ``product_section`` from
        the generic ``place()`` loop: both already have exactly one instance
        on this same Home page from ``bootstrap_service`` (scenarios 02/03/15
        and 04-07/12/13 respectively each discover it via
        ``openSectionViaPreview(sectionKey)``'s own ``.first()`` semantics).
        Placing a SECOND section under either key would silently make those
        earlier scenarios' discovery ambiguous — reproduced live while
        originally building this gate: scenario 12 failed reading a stale/
        wrong ``product_section`` title once a second one existed. hero_banner
        now gets its real HeroSlide bound to that SAME existing section
        instead of a second one."""
        from django.utils import timezone

        from apps.content.models import HeroSlide
        from apps.storefront_builder.models import StorefrontSection

        home_page = draft.get_page("home")
        store = draft.layout.store

        def place(section_key: str, settings_overrides: dict | None = None) -> int:
            definition = section_registry.get_definition(section_key)
            settings = definition.default_settings()
            if settings_overrides:
                settings.update(settings_overrides)
            order = home_page.sections.count()
            section = StorefrontSection.objects.create(
                page=home_page, section_key=section_key, order=order, settings=settings,
            )
            container = container_service.create_empty_container(home_page, "single")
            cell = container.cells.order_by("order", "id").first()
            container_service.place_section(cell, section)
            return section.pk

        section_ids = {}
        for section_key in (
            "newest_products", "best_sellers", "discounted_products", "promo_cards",
            "amazing_offers", "blog_posts", "image_slider",
            "video_section", "quick_links",
            "trust_features", "faq", "testimonials",
        ):
            section_ids[f"{section_key}_section_id"] = place(section_key)
        # rich_text.html renders NOTHING at all ({% if body %}) with its
        # default empty body_html — like image_text's own title override
        # above (Task 6), an empty section is just the generic placeholder
        # wrapper preview.html always emits, whose floating Container
        # toolbar overlay covers its entire (near-zero-height) click target
        # — reproduced live while building this gate:
        # openSectionViaPreview('rich_text') timed out retrying a click that
        # was always intercepted. A real starting body_html gives it actual
        # height to click, exactly the same fix Task 6 already applied to
        # image_text/story_rail/single_banner for the identical reason.
        section_ids["rich_text_section_id"] = place(
            "rich_text",
            {
                "body_html": (
                    "<p>متن اولیه QA تسک نهایی برای بخش متن — این پاراگراف عمداً بلند "
                    "است تا بخش ارتفاع واقعی داشته باشد و کلیک روی آن با نوار ابزار "
                    "شناور Container برخورد نکند.</p>"
                    "<p>پاراگراف دوم برای اطمینان از ارتفاع کافی.</p>"
                ),
            },
        )

        # --- CORRECTIVE ITEM 1 — real fixture data closing the persistence-
        # only weaknesses the independent review found -----------------------

        # hero_banner (existing bootstrap section) + image_slider (just
        # placed above) each get their own real HeroSlide, canonical
        # MediaAsset path.
        hero_banner_section = home_page.sections.filter(
            section_key="hero_banner",
        ).order_by("order", "id").first()
        if hero_banner_section is not None:
            slide = HeroSlide(
                store=store, section=hero_banner_section,
                title="اسلاید هیرو QA تسک نهایی", is_active=True,
            )
            _save_with_media_asset(slide, "desktop_image", "desktop_asset", "final-hero.png", _png_swatch("#7c3aed"))
        image_slider_section = StorefrontSection.objects.get(pk=section_ids["image_slider_section_id"])
        slide = HeroSlide(
            store=store, section=image_slider_section,
            title="اسلاید تصویر QA تسک نهایی", is_active=True,
        )
        _save_with_media_asset(slide, "desktop_image", "desktop_asset", "final-slider.png", _png_swatch("#0ea5e9"))

        # amazing_offers/discounted_products: ONE real discounted Product —
        # render_service.py's own query for BOTH families is
        # ``discount_percent__gt=0``.
        vendor, _ = Vendor.objects.get_or_create(store=store, slug="qa-final-vendor", defaults=dict(name="فروشنده QA"))
        category, _ = Category.objects.get_or_create(
            store=store, slug="t12-category", defaults=dict(name="دسته T12", is_active=True),
        )
        discounted_product, _ = Product.objects.get_or_create(
            store=store, slug="qa-final-discounted-product",
            defaults=dict(
                name="کالای تخفیف‌دار QA تسک نهایی", vendor=vendor, category=category,
                sku="SKU-QA-FINAL-DISCOUNTED", price=Decimal("500000"), discount_percent=25,
                status=Product.Status.ACTIVE,
            ),
        )

        # best_sellers: reproduced live — render_service._best_sellers_context
        # is deliberately NEVER computed from Product.sold_count (see
        # best_seller_service's own module docstring: that field has no
        # writer anywhere in the codebase); it ranks LIVE from real OrderItem
        # rows in the last 30 days. Reusing "existing catalog demo data"
        # (this gate's original assumption for newest_products/best_sellers/
        # promo_cards) is correct for newest_products (ordered by
        # -created_at) but was genuinely insufficient for best_sellers —
        # confirmed by a real browser run timing out on `.pcard`, not merely
        # theorized. A minimal real Order + OrderItem against the discounted
        # Product above is the actual, not-avoided real data path.
        from apps.customers.models import Customer
        from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod

        order_user, _ = get_user_model().objects.get_or_create(
            username="qa-final-best-seller-customer", defaults=dict(is_active=True),
        )
        customer, _ = Customer.objects.get_or_create(
            user=order_user, defaults=dict(full_name="مشتری QA تسک نهایی", phone="09120000000"),
        )
        shipping_method, _ = ShippingMethod.objects.get_or_create(
            store=store, slug="qa-final-shipping", defaults=dict(name="ارسال QA"),
        )
        payment_gateway, _ = PaymentGateway.objects.get_or_create(
            store=store, slug="qa-final-gateway", defaults=dict(name="درگاه QA"),
        )
        order, _ = Order.objects.get_or_create(
            code="QA-FINAL-BESTSELLER-1",
            defaults=dict(
                store=store, customer=customer, vendor=vendor, address={"receiver_name": "مشتری QA", "city": "تهران"},
                shipping_method=shipping_method, payment_gateway=payment_gateway,
                items_total=Decimal("500000"), grand_total=Decimal("500000"),
            ),
        )
        OrderItem.objects.get_or_create(
            order=order, product=discounted_product,
            defaults=dict(
                product_name=discounted_product.name, quantity=1,
                unit_price=Decimal("500000"), line_total=Decimal("500000"),
            ),
        )

        # blog_posts: one real, global BlogPost row.
        from apps.blog.models import BlogPost

        BlogPost.objects.get_or_create(
            slug="qa-final-remediation-post",
            defaults=dict(
                title="مطلب وبلاگ QA تسک نهایی", body="متنِ آزمایشیِ QA.",
                published_at=timezone.now(),
            ),
        )

        # quick_links: a real Menu + one real MenuItem (Category destination,
        # reusing the same demo Category above) — the family's OWN new
        # menu_picker field edits THIS Menu's id.
        from apps.content.models import Menu, MenuItem

        menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.HEADER,
            defaults=dict(title="منوی QA تسک نهایی", is_active=True),
        )
        MenuItem.objects.get_or_create(
            menu=menu, title="دسته T12 QA",
            defaults=dict(destination_type="category", destination_category=category, is_active=True),
        )
        section_ids["quick_links_menu_id"] = menu.pk

        return section_ids

    def _prepare_phase3_task6_family_gate(self, draft) -> dict:
        """Phase 4 Task 6 — representative browser certification for the
        Task-6 MIGRATE families the existing scenarios never touch.

        Deliberately NOT one registration per family (~20 of them): every
        schema-driven family shares the exact same R4 mechanism scenario 02
        already proves generically (Inspector field -> section.update_settings
        mutation -> Draft autosave -> persists across reload -> visible in
        Preview) — what is genuinely family-specific is only (a) whether
        *this* family's own field is really wired into the Inspector at all,
        and (b) its own distinct field TYPE. So this places exactly one
        representative per remaining field TYPE (integer: ``category_grid``;
        choice, two different enums: ``multi_banner``/``image_text``; text:
        ``newsletter``) plus the two non-schema dispositions with no
        equivalent proof anywhere (``story_rail`` — media CRUD; and
        ``single_banner`` — FIXED/STATIC, no Inspector schema field at all,
        certified by rendering its own real media-backed markup rather than
        a control edit). Every family sharing an already-registered field
        TYPE and mechanism (``newest_products``/``best_sellers``/
        ``discounted_products``/``promo_cards``/``amazing_offers`` share
        ``category_grid``'s integer item_limit; ``blog_posts``/
        ``quick_links``/``video_section`` share ``newsletter``'s text title;
        ``rich_text`` shares ``image_text``'s partial-schema-plus-unmanaged-
        key shape) is certified via that shared mechanism, not re-registered
        here.

        ``rich_text`` itself (field type ``rich_text``, a CKEditor5-managed
        control — see ``r4/partials/settings_field.html``) is a GENUINELY
        DIFFERENT Inspector mechanism from a plain text input or a
        ``<select>``, not a sharing case (Task 6 final-review fix, M1 — an
        earlier version of this docstring incorrectly grouped it with
        ``image_text`` on the basis of a shared VALIDATOR shape, which is
        not the same thing as a shared Inspector CONTROL type): it remains a
        recorded, deliberate browser-coverage gap, not a certified-by-sharing
        field type — see ``phase4/task6_family_convergence.md`` for the
        reasoning recorded per family. Returns the discovered ids the runner
        threads through the manifest. NEVER runs on the default R3 path.

        Task 6 (final-review fix, I2) — the independent reviewer proved
        ``story_rail``/``single_banner``/``multi_banner`` were placed with
        NO backing media row: every one of their templates renders nothing
        at all without one (``{% if story_items %}`` /
        ``{% for banner in banners %}``), so the harness's own
        ``waitFor({state: 'visible'})`` was passing only because the empty-
        placeholder wrapper `preview.html`/`responsive_section_wrapper.html`
        always emit is what it found — never the family's own real markup.
        A real ``StoryRailItem``/``PromotionalBanner`` row bound to each
        section (the same in-memory PNG technique the Collection gate below
        already uses) is created here so the DOM assertions in ``run.mjs``
        check the family's actual rendering."""
        from apps.content.models import PromotionalBanner, StoryRailItem
        from apps.storefront_builder.models import StorefrontSection

        home_page = draft.get_page("home")
        store = draft.layout.store

        def place(section_key: str, settings_overrides: dict | None = None) -> int:
            definition = section_registry.get_definition(section_key)
            settings = definition.default_settings()
            if settings_overrides:
                settings.update(settings_overrides)
            order = home_page.sections.count()
            section = StorefrontSection.objects.create(
                page=home_page, section_key=section_key, order=order, settings=settings,
            )
            container = container_service.create_empty_container(home_page, "single")
            cell = container.cells.order_by("order", "id").first()
            container_service.place_section(cell, section)
            return section.pk

        # No "source" override: the schema's own default (auto/all_active) is
        # guaranteed valid, and ResourceSource itself is already certified
        # thoroughly at the Django-test level plus via the shared Resource
        # Picker in scenarios 05-07 — this registration only needs to prove
        # category_grid's OWN item_limit field is R4-reachable.
        category_grid_section_id = place("category_grid")
        multi_banner_section_id = place("multi_banner")
        # image_text renders NOTHING at all ({% if title or body or image_url %})
        # with every one of those three empty, as default_settings() leaves
        # them — a real title is the cheapest way to give the
        # image_position CSS check something to actually assert against.
        image_text_section_id = place("image_text", {"title": "متن تسک ۶"})
        newsletter_section_id = place("newsletter")
        story_rail_section_id = place("story_rail")
        single_banner_section_id = place("single_banner")

        story_rail_section = StorefrontSection.objects.get(pk=story_rail_section_id)
        story_payload = _png_swatch("#c026d3")
        if story_payload is not None:
            item = StoryRailItem(
                store=store, section=story_rail_section, title="استوری تسک ۶", is_active=True,
            )
            _save_with_media_asset(item, "image", "image_asset", "task6-story.png", story_payload)

        single_banner_section = StorefrontSection.objects.get(pk=single_banner_section_id)
        single_banner_payload = _png_swatch("#0f766e")
        if single_banner_payload is not None:
            banner = PromotionalBanner(
                store=store, section=single_banner_section, title="بنر تک تسک ۶", is_active=True,
            )
            _save_with_media_asset(banner, "desktop_image", "desktop_asset", "task6-single-banner.png", single_banner_payload)

        multi_banner_section = StorefrontSection.objects.get(pk=multi_banner_section_id)
        for index, color in enumerate(("#ea580c", "#2563eb")):
            multi_banner_payload = _png_swatch(color)
            if multi_banner_payload is None:
                break
            banner = PromotionalBanner(
                store=store, section=multi_banner_section, title=f"بنر چندتایی تسک ۶ #{index + 1}",
                is_active=True, display_order=index,
            )
            _save_with_media_asset(
                banner, "desktop_image", "desktop_asset", f"task6-multi-banner-{index}.png", multi_banner_payload,
            )

        return {
            "category_grid_section_id": category_grid_section_id,
            "multi_banner_section_id": multi_banner_section_id,
            "image_text_section_id": image_text_section_id,
            "newsletter_section_id": newsletter_section_id,
            "story_rail_section_id": story_rail_section_id,
            "single_banner_section_id": single_banner_section_id,
        }

    def _prepare_phase3_collection_gate(self, store: Store, user, draft) -> dict:
        """Task 5 — a deterministic Collection matrix on the SAME Draft the
        Brand gate uses. Stands up:

          * ``p3-collection-1`` (reused from the Brand gate) AND a second
            ``p3-collection-2`` created deterministically LATER (a strictly
            greater ``created_at``) so auto (newest-first) ordering is
            provable and stable across reruns,
          * one collection with >12 storefront-visible members (a real
            ``?page=2``), created from dedicated collection products,
          * one member whose product is INACTIVE (so ``item_count`` = TOTAL
            membership is strictly greater than the visible-product count),
          * one collection WITH a real cover image + one WITHOUT (folder-glyph
            fallback),
          * one ``collection_tiles`` per tile_style variant (grid + carousel)
            on each of the six envelope pages.

        Returns the ids/slugs the runner threads through the manifest. NEVER
        runs on the default R3 path."""
        from io import BytesIO

        from django.core.files.base import ContentFile
        from django.utils import timezone

        from apps.catalog.models import (
            Category, MerchantCollection, MerchantCollectionItem, Product, Vendor,
        )
        from apps.storefront_builder.models import StorefrontPage, StorefrontSection

        def _png_cover(color):
            try:
                from PIL import Image  # noqa: WPS433 (local import; project dep)
            except Exception:  # pragma: no cover — PIL is a project dependency
                return None
            buf = BytesIO()
            Image.new("RGB", (320, 180), color).save(buf, format="PNG")
            return buf.getvalue()

        vendor, _ = Vendor.objects.get_or_create(
            store=store, slug="p3-coll-vendor", defaults=dict(name="فروشنده کالکشن پی۳"),
        )
        category, _ = Category.objects.get_or_create(
            store=store, slug="p3-coll-category", defaults=dict(name="دسته کالکشن پی۳", is_active=True),
        )

        # ---- Collection #1: reuse the Brand-gate host (p3-collection-1). ----
        # It has a couple of real members already; give it a real cover image
        # so the "image decoded" tile path has a subject.
        c1 = MerchantCollection.objects.get(store=store, slug="p3-collection-1")
        if not c1.image:
            payload = _png_cover("#6d28d9")
            if payload is not None:
                c1.image.save(f"{c1.slug}.png", ContentFile(payload), save=True)

        # ---- Collection #2: created LATER => deterministically newest. ----
        # A no-image collection (folder-glyph fallback subject).
        c2, created2 = MerchantCollection.objects.get_or_create(
            store=store, slug="p3-collection-2",
            defaults=dict(name="کالکشن پی۳ شماره ۲", is_active=True),
        )
        if c2.image:
            c2.image.delete(save=False)
        c2.is_active = True
        c2.save(update_fields=["is_active", "image"])
        # Force a strictly-greater created_at so newest-first ordering is
        # deterministic regardless of DB timestamp resolution / rerun timing.
        # ``created_at`` is auto_now_add, so a plain .save() ignores it — a
        # bulk ``update()`` bypasses that and writes the exact value.
        MerchantCollection.objects.filter(pk=c2.pk).update(
            created_at=c1.created_at + timezone.timedelta(days=1),
        )
        c2.refresh_from_db(fields=["created_at"])
        # A couple of members for c2 (reuse the base t12 products).
        for order, slug in enumerate(["t12-product-3", "t12-product-4"]):
            product = Product.objects.filter(store=store, slug=slug).first()
            if product is not None:
                MerchantCollectionItem.objects.get_or_create(
                    collection=c2, product=product, defaults=dict(order=order),
                )

        # ---- Collection #3: >12 visible members + one INACTIVE member. ----
        c_page2, _ = MerchantCollection.objects.get_or_create(
            store=store, slug="p3-collection-page2",
            defaults=dict(name="کالکشن پی۳ صفحه‌بندی", is_active=True),
        )
        c_page2.is_active = True
        c_page2.save(update_fields=["is_active"])
        # NOT newest: strictly-older created_at (bulk update bypasses auto_now_add).
        MerchantCollection.objects.filter(pk=c_page2.pk).update(
            created_at=c1.created_at - timezone.timedelta(days=1),
        )
        # 13 ACTIVE (visible) members => 2 pages at PRODUCTS_PER_PAGE=12.
        for i in range(13):
            product, _ = Product.objects.get_or_create(
                store=store, slug=f"p3-coll-page2-p{i:02d}",
                defaults=dict(
                    vendor=vendor, category=category, name=f"کالای صفحه‌بندی پی۳ {i:02d}",
                    sku=f"SKU-P3PAGE2-{i:02d}", price=Decimal("90000"), stock=10,
                    status=Product.Status.ACTIVE,
                ),
            )
            MerchantCollectionItem.objects.get_or_create(
                collection=c_page2, product=product, defaults=dict(order=i),
            )
        # One INACTIVE member: counts toward item_count (TOTAL membership) but
        # NOT toward the visible-product page listing.
        inactive_product, _ = Product.objects.get_or_create(
            store=store, slug="p3-coll-page2-inactive",
            defaults=dict(
                vendor=vendor, category=category, name="کالای غیرفعال پی۳",
                sku="SKU-P3PAGE2-INACTIVE", price=Decimal("90000"), stock=10,
                status=Product.Status.INACTIVE,
            ),
        )
        MerchantCollectionItem.objects.get_or_create(
            collection=c_page2, product=inactive_product, defaults=dict(order=99),
        )

        # ---- Broken-image disposable fixture (Task 7). ----
        # An ACTIVE collection (manual/auto selection both filter on
        # is_active, so an inactive fixture would simply be omitted and never
        # exercise the degraded-image path) whose ``image`` FieldFile points
        # at a file that was never written to storage. Because auto mode
        # selects "all active", this collection is picked up by every
        # existing auto collection_tiles section above — the runner records
        # its degraded state separately (per spec: "record browser network
        # failure; do not equate no-image with broken-image") and excludes it
        # from the existing per-tile decode/glyph assertions and from the
        # zero-error pools, rather than asserting it must decode. Its
        # ``created_at`` is strictly earlier than every other fixture
        # collection so it can never become the deterministic "newest" tile.
        c_broken, _ = MerchantCollection.objects.get_or_create(
            store=store, slug="p3-collection-broken",
            defaults=dict(name="کالکشن تصویر خراب", is_active=True),
        )
        c_broken.is_active = True
        c_broken.save(update_fields=["is_active"])
        MerchantCollection.objects.filter(pk=c_broken.pk).update(
            image="collection_images/qa-broken-nonexistent.png",
            created_at=c1.created_at - timezone.timedelta(days=2),
        )

        tile_variants = ["grid", "carousel"]

        def _tiles_settings(tile_style: str, page_type: str) -> dict:
            return {
                "title": f"کالکشن‌های {page_type} {tile_style}",
                "tile_style": tile_style,
                # empty selection => auto (all active, newest-first): proves
                # deterministic newest ordering (c2 first) on every envelope.
                "collection_ids": [],
            }

        def place_tiles_variant(page, tile_style: str, page_type: str) -> int:
            order = page.sections.count()
            section = StorefrontSection.objects.create(
                page=page,
                section_key="collection_tiles",
                order=order,
                settings=_tiles_settings(tile_style, page_type),
            )
            container = container_service.create_empty_container(page, "single")
            cell = container.cells.order_by("order", "id").first()
            container_service.place_section(cell, section)
            return section.pk

        def place_all_tile_variants(page_type: str) -> dict:
            page = draft.get_page(page_type)
            return {ts: place_tiles_variant(page, ts, page_type) for ts in tile_variants}

        envelopes = {
            "home": place_all_tile_variants(StorefrontPage.PageType.HOME),
            "product_detail": place_all_tile_variants(StorefrontPage.PageType.PRODUCT_DETAIL),
            "listing": place_all_tile_variants(StorefrontPage.PageType.LISTING),
            "search": place_all_tile_variants(StorefrontPage.PageType.SEARCH),
            "collection": place_all_tile_variants(StorefrontPage.PageType.COLLECTION),
            "cart": place_all_tile_variants(StorefrontPage.PageType.CART),
        }

        # Active-collection auto order is newest-first; c2 (created LATER) is
        # the deterministic newest.
        newest_slug = c2.slug

        return {
            # collection_tiles section ids (DRAFT) per envelope, keyed by
            # tile_style: {envelope: {variant: section_pk}}
            "tiles_section_ids": envelopes,
            # collection slugs the runner asserts against
            "collection_slugs": [c2.slug, c1.slug, c_page2.slug],
            "newest_collection_slug": newest_slug,
            # the >12-member collection for a real ?page=2 fetch
            "page2_collection_slug": c_page2.slug,
            # names for tile-text assertions
            "collection_names": {
                c1.slug: c1.name, c2.slug: c2.name, c_page2.slug: c_page2.name,
            },
            # which collection has a cover image vs the folder-glyph fallback
            "image_collection_slug": c1.slug,
            "no_image_collection_slug": c2.slug,
            # Task 7 disposable broken-image fixture (recorded separately;
            # excluded from decode/glyph assertions and zero-error pools).
            "broken_collection_slug": c_broken.slug,
            # item_count(TOTAL) vs visible-count evidence for the page2 host:
            # 14 members total (13 active + 1 inactive), 13 visible.
            "page2_total_members": 14,
            "page2_visible_members": 13,
            # a product slug on the six envelopes (product_detail route input);
            # reuse the Brand gate's stocked cart-flow product.
            "product_slug": "t12-product-1",
            # tile_style variants the matrix cycles per envelope
            "tile_variants": list(tile_variants),
        }

    def _build_manifest(self, *, store, port, session_cookie, report_dir, headed, browser_channel, phase3=False, phase3_fixture=None, showcase=False, w4c_all50=False):
        # Phase 5 Task 6 (--showcase) — reach the editor via the Store's
        # ADMIN-SUBDOMAIN host (``<admin_subdomain>.rastisi.localhost``, mapped
        # to 127.0.0.1 by the runner's chromium --host-resolver-rules), so a
        # multi-Store sandbox resolves the target Store instead of failing the
        # 127.0.0.1 single-Store compatibility fallback. The admin portal
        # resolves the Store by its admin_subdomain — no StoreDomain seeding is
        # involved. The default (non-showcase, non-W4C) run keeps the
        # 127.0.0.1 origin and cookie domain byte-for-byte unchanged.
        #
        # P5-W4C (design doc section 3.5) — a third, mutually-exclusive
        # branch: the REAL customer-facing Store host, so run.mjs's public
        # certification cells resolve the actual public storefront (never
        # raw 127.0.0.1, never the admin-subdomain host showcase mode uses).
        if showcase:
            host = f"{store.admin_subdomain}{self.SHOWCASE_QA_HOST_SUFFIX}"
        elif w4c_all50:
            host = f"shop-{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        else:
            host = "127.0.0.1"
        origin = f"http://{host}:{port}"
        cookie_domain = host
        same_site = str(settings.SESSION_COOKIE_SAMESITE or "Lax").capitalize()
        if same_site not in {"Lax", "Strict", "None"}:
            same_site = "Lax"
        manifest = {
            "origin": origin,
            # The host the runner must map to 127.0.0.1 (None for a normal run).
            "resolver_host": host if (showcase or w4c_all50) else None,
            "builder_url": f"{origin}/admin-portal/storefront-builder/r4/",
            "public_url": f"{origin}/",
            "report_dir": str(report_dir),
            "headed": bool(headed),
            "browser_channel": browser_channel,
            "phase3": bool(phase3),
            # Phase 5 Task 6 — opt-in Showcase creation-facade scenario. None/
            # False-shaped by default, so the default run.mjs run is unchanged.
            "showcase": bool(showcase),
            # Phase 3 (Task 3 "Brand gate") — the runner reads fixture ids
            # (per-page brand section ids, product slug, collection slug,
            # brand id lists) from the MANIFEST, not fixture.json. Only
            # populated on a --phase3 run; None (absent-shaped) otherwise, so
            # the default R3 manifest is byte-identical to before.
            "phase3_fixture": phase3_fixture,
            "store": {"id": store.pk, "name": store.name, "slug": store.slug},
        }
        if not w4c_all50:
            # P5-W4C (section 5/9) — no W4C manifest of any kind (base or
            # Theme cell) ever carries a "session" key. Every W4C Store-state
            # transition is a Python ORM/service call (section 3.1); the
            # browser only ever observes ANONYMOUS public traffic.
            manifest["session"] = {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_cookie,
                "domain": cookie_domain,
                "path": settings.SESSION_COOKIE_PATH or "/",
                "httpOnly": bool(settings.SESSION_COOKIE_HTTPONLY),
                "secure": bool(settings.SESSION_COOKIE_SECURE),
                "sameSite": same_site,
            }
        return manifest

    @staticmethod
    def _port_is_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) != 0

    @staticmethod
    def _wait_for_port(port: int, proc, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                return False
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            time.sleep(0.2)
        return False

    @staticmethod
    def _stop_process(proc) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

    def _run_logged(self, command, *, cwd: Path, log_path: Path) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.stdout.write(line.rstrip("\n"))
                log.write(line)
                log.flush()
            return process.wait()

    # =====================================================================
    # P5-W4C (Implementation Round 1) — bounded --w4c-all50 extension.
    # Design doc: docs/superpowers/plans/2026-09-17-phase5-w4c-all50-
    # browser-certification.md. Never invoked unless --w4c-all50 is passed;
    # the entire non-W4C path above is untouched by any method below.
    # =====================================================================

    def _prepare_w4c_certification_fixture(self, store: Store) -> dict:
        """Section 3.3 — bypasses ``_prepare_r4_sandbox`` entirely. Never
        wipes ``published_version``/``draft_version`` and never deletes
        Home ``Section``/``Container`` rows — W4C needs a real, Ready-
        Template-published starting state per Template, not a from-scratch
        publish transition to observe."""
        call_command("seed_ready_template_fashion_demo")
        return {"store_slug": store.slug, "seed_command": "seed_ready_template_fashion_demo"}

    def _build_w4c_fixture(self, store: Store) -> dict:
        """Section 2/3.2 — read live from the registry, never a hardcoded
        literal. ``tier1_occasions`` cycles nowruz/ramadan/muharram over the
        SAME live, deterministic ``a8_ready_templates._SPECS`` source order
        (section 1.1) -- NOT ``list_ready_templates()``'s dict-iteration
        order, which does not match ``_SPECS``'s definition order once the
        W4B historical-spec registrations are mixed in."""
        from apps.storefront_builder import a8_ready_templates

        presets = lpr.list_ready_templates()
        templates = [{"key": p.key, "version": p.version} for p in presets]
        tier1_occasions = {
            spec.key: W4C_TIER1_OCCASION_CYCLE[i % len(W4C_TIER1_OCCASION_CYCLE)]
            for i, spec in enumerate(a8_ready_templates._SPECS)
        }
        # The PDP/Cart cells exercise real quantity-adjustment and add-to-cart
        # flows against whichever variant the storefront pre-selects as the
        # DEFAULT (storefront_variant_service: is_default=True, else the
        # first by display_order/id -- never necessarily the one with stock).
        # Rather than duplicate that selection logic here, require every
        # active, non-obsolete variant to be in stock, so any variant the
        # storefront could pick as default is purchasable.
        pdp_product = (
            Product.objects.filter(
                store=store, product_type=Product.ProductType.VARIABLE,
                variants__is_active=True, variants__is_obsolete=False, variants__stock__gt=0,
            )
            .exclude(variants__is_active=True, variants__is_obsolete=False, variants__stock=0)
            .distinct().order_by("id").first()
        )
        return {
            "templates": templates,
            "tier1_occasions": tier1_occasions,
            "tier2_keys": list(W4C_TIER2_KEYS),
            "pdp_product_id": pdp_product.pk if pdp_product else None,
            "pdp_product_slug": pdp_product.slug if pdp_product else None,
        }

    def _home_hero_expected(self, preset) -> bool:
        """Section 6 — data-driven, never a hardcoded key list: derived from
        the live compiled Home composition, not the raw recipe token."""
        return any(entry.section_key == W4C_HERO_SECTION_KEY for entry in preset.pages.get("home", ()))

    def _home_hero_index(self, preset):
        """IMPORTANT 1 (repaired) -- the Hero section's 0-based position
        within the live compiled Home composition. The public page has no
        ``data-section-key`` (that attribute is preview-only, see
        ``responsive_section_wrapper.html``), and not every Hero variant
        template shares one common CSS class (``hero_banner_luxury.html``/
        ``hero_banner_atelier.html`` do not carry a bare ``.hero`` class the
        way ``hero_banner.html``/``_split``/``_beauty``/``_chocolate`` do) --
        so a real, universal Hero proof must be positional, computed from
        the SAME live registry data every other W4C check already uses,
        never a broad text-content selector."""
        for index, entry in enumerate(preset.pages.get("home", ())):
            if entry.section_key == W4C_HERO_SECTION_KEY:
                return index
        return None

    def _home_product_cards_expected(self, preset) -> bool:
        """IMPORTANT 1 (repaired) -- data-driven, mirrors ``_home_hero_expected``.
        Every product-bearing composition token
        (``product_grid``/``sale_products``/``product_rail``/``product_list``/
        ``bento_products``/``featured_products``) compiles to the SAME
        ``product_section`` section key (``a8_ready_templates._product_entry``)."""
        return any(entry.section_key == "product_section" for entry in preset.pages.get("home", ()))

    def _home_bottom_nav_expected(self, preset) -> bool:
        return bool(preset.footer and preset.footer.get("mobile_nav_variant"))

    def _apply_and_verify_published(self, store: Store, preset) -> None:
        """Section 3.4 — exact apply/publish/verify sequence. Checks
        ``published_version is None``/status FIRST, raising a controlled
        ``CommandError``, before ever dereferencing ``template_provenance``
        (the exact ordering bug the design review flagged)."""
        preset_service.apply_preset_with_checkpoint(store, preset)
        layout_service.publish(store)
        layout = StorefrontLayout.objects.get(store=store)
        pv = layout.published_version
        if pv is None or pv.status != pv.Status.PUBLISHED:
            raise CommandError(f"W4C: {preset.key} v{preset.version} has no valid published version")
        template = (pv.template_provenance or {}).get("template") or {}
        if template.get("key") != preset.key or template.get("version") != preset.version:
            raise CommandError(f"W4C: {preset.key} v{preset.version} did not verify as published (found {template})")

    def _verify_theme_is_none(self, store: Store) -> None:
        layout = StorefrontLayout.objects.get(store=store)
        pv = layout.published_version
        if pv is None or pv.status != pv.Status.PUBLISHED:
            raise CommandError("W4C: no valid published version -- cannot verify Theme state")
        manifest = load_store_appearance_manifest(pv)
        if manifest.selections.get("theme") != "theme.none.v1":
            raise CommandError(f"W4C: expected theme.none.v1, found {manifest.selections.get('theme')}")

    def _verify_published_theme(self, store: Store, occasion_component_key: str, intensity: str) -> None:
        layout = StorefrontLayout.objects.get(store=store)
        pv = layout.published_version
        if pv is None or pv.status != pv.Status.PUBLISHED:
            raise CommandError("W4C: no valid published version -- cannot verify Theme state")
        manifest = load_store_appearance_manifest(pv)
        if (
            manifest.selections.get("theme") != occasion_component_key
            or manifest.settings.get("theme", {}).get("intensity") != intensity
        ):
            raise CommandError(f"W4C: Theme did not verify as published ({occasion_component_key}/{intensity})")

    def _theme_cleanup_and_verify(self, store: Store) -> None:
        """Section 3.6 — Python-owned, failure-safe. Called from a Python
        ``try/finally`` around every Theme cell. If THIS raises, the entire
        run halts immediately (section 3.2's Important-2C exception) and is
        reported BLOCKED."""
        draft = layout_service.get_or_create_draft(store)
        appearance_authority_service.clear_theme(version=draft)
        layout_service.publish(store)
        self._verify_theme_is_none(store)

    # -- cardinality helpers (section 1/3.2) ---------------------------------
    def _base_cell_matrix(self):
        return tuple((page_class, viewport) for page_class in W4C_PAGE_CLASSES for viewport in W4C_VIEWPORTS)

    def _planned_tier2_cells(self, selected_keys):
        """Section 3.2 (repaired, Round 4 Important 1) — a ``--only`` batch
        NEVER runs a Tier-2 cell for a key it did not select, including
        warm_boutique/beauty_dew when neither is in ``selected_keys``."""
        cells = []
        for key in selected_keys:
            if key not in W4C_TIER2_KEYS:
                continue
            for occasion in W4C_TIER2_OCCASIONS:
                for intensity in W4C_TIER2_INTENSITIES:
                    for viewport in W4C_VIEWPORTS:
                        cells.append((key, occasion, intensity, viewport))
        return cells

    # -- unique per-cell result/log paths (section 3.9) ----------------------
    def _w4c_base_result_path(self, campaign_root, key: str) -> Path:
        return Path(campaign_root) / "w4c-results" / "base" / f"{key}.json"

    def _w4c_base_log_path(self, campaign_root, key: str) -> Path:
        return Path(campaign_root) / "logs" / "base" / f"{key}.log"

    def _w4c_theme_result_path(self, campaign_root, key: str, occasion: str, intensity: str, viewport: str, tier: str) -> Path:
        # A ``tier`` segment disambiguates warm_boutique/beauty_dew's Tier-1
        # cell from a Tier-2 cell that happens to land on the exact same
        # occasion/intensity/viewport triple -- both are separate
        # invocations (section 3.2) and must never collide on disk.
        return Path(campaign_root) / "w4c-results" / "theme" / f"{key}__{tier}__{occasion}__{intensity}__{viewport}.json"

    def _w4c_theme_log_path(self, campaign_root, key: str, occasion: str, intensity: str, viewport: str, tier: str) -> Path:
        return Path(campaign_root) / "logs" / "theme" / f"{key}__{tier}__{occasion}__{intensity}__{viewport}.log"

    def _w4c_home_screenshot_paths(self, campaign_root, key: str) -> tuple[str, str]:
        base = Path(campaign_root) / "screenshots" / "home"
        return (str(base / f"{key}_home_desktop.jpg"), str(base / f"{key}_home_mobile.jpg"))

    # -- manifest writers (section 3.2/3.7) -----------------------------------
    def _write_w4c_base_manifest(self, *, base: dict, key: str, version: str, result_path: Path,
                                  hero_expected: bool = False, hero_index=None, run_token: str, cells=None,
                                  expected_rsec_count=None, product_cards_expected: bool = False,
                                  bottom_nav_expected: bool = False) -> str:
        home_desktop, home_mobile = self._w4c_home_screenshot_paths(result_path.parents[2], key)
        manifest = dict(base)
        manifest.update({
            "w4c": True,
            "mode": "base",
            "run_token": run_token,
            "active_key": {
                "key": key, "version": version, "hero_expected": bool(hero_expected),
                "hero_index": hero_index, "expected_rsec_count": expected_rsec_count,
                "product_cards_expected": bool(product_cards_expected),
                "bottom_nav_expected": bool(bottom_nav_expected),
            },
            "result_path": str(result_path),
            "cells": [{"page_class": pc, "viewport": vp} for pc, vp in (cells if cells is not None else self._base_cell_matrix())],
            "home_screenshot_desktop": home_desktop,
            "home_screenshot_mobile": home_mobile,
        })
        result_path.parent.mkdir(parents=True, exist_ok=True)
        Path(home_desktop).parent.mkdir(parents=True, exist_ok=True)
        fd, manifest_path = tempfile.mkstemp(prefix="rastisi-w4c-base-", suffix=".json")
        os.close(fd)
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path

    def _write_w4c_theme_manifest(self, *, base: dict, key: str, version: str, occasion: str, intensity: str,
                                   viewport: str, tier: str, result_path: Path, run_token: str,
                                   expected_theme: dict | None = None) -> str:
        manifest = dict(base)
        manifest.update({
            "w4c": True,
            "mode": "theme",
            "run_token": run_token,
            "active_key": {
                "key": key, "version": version, "occasion": occasion,
                "intensity": intensity, "viewport": viewport, "tier": tier,
            },
            "expected_theme": expected_theme,
            "result_path": str(result_path),
        })
        result_path.parent.mkdir(parents=True, exist_ok=True)
        fd, manifest_path = tempfile.mkstemp(prefix="rastisi-w4c-theme-", suffix=".json")
        os.close(fd)
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path

    # -- freshness/identity/schema validation (Code Review Repair Round 1,
    # CRITICAL 1) -------------------------------------------------------------
    @staticmethod
    def _new_run_token() -> str:
        return secrets.token_hex(16)

    # -- campaign/harness git provenance (Code Review Repair Round 2,
    # IMPORTANT 6) -- pure primitives; the actual dirty/mismatch REJECTION
    # behavior lives in _validate_or_init_campaign_matrix, under TDD below.
    @staticmethod
    def _current_git_head() -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(Path(settings.BASE_DIR).resolve()),
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _tracked_worktree_is_dirty() -> bool:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(Path(settings.BASE_DIR).resolve()),
            capture_output=True, text=True, check=True,
        )
        return bool(result.stdout.strip())

    def _validate_base_cell_schema(self, cell, *, context: str) -> None:
        if not isinstance(cell, dict):
            raise CommandError(f"W4C: malformed base cell at {context}: {cell!r}")
        missing = [field for field in W4C_REQUIRED_BASE_CELL_FIELDS if field not in cell]
        if missing:
            raise CommandError(f"W4C: base cell at {context} is missing required fields {missing}: {cell!r}")
        if cell["result"] not in W4C_VALID_CELL_RESULTS:
            raise CommandError(f"W4C: base cell at {context} has an invalid result {cell['result']!r}")
        if cell["result"] != "PASS" and not cell.get("reason"):
            raise CommandError(f"W4C: base cell at {context} is not PASS but has no reason: {cell!r}")

    def _validate_base_result_freshness(self, result, *, run_token: str, key: str, version: str) -> bool:
        """CRITICAL 1 -- proves ``result`` was written by THIS invocation, for
        THIS Template, never a stale/foreign file left over from a prior run.
        Returns whether any cell is non-PASS (for exit-code consistency)."""
        if not isinstance(result, dict):
            raise CommandError(f"W4C: malformed base result for {key} (not a JSON object)")
        if result.get("run_token") != run_token:
            raise CommandError(f"W4C: stale/foreign base result for {key} -- run_token mismatch")
        if result.get("key") != key or result.get("version") != version:
            raise CommandError(
                f"W4C: base result identity mismatch for {key} v{version}: "
                f"found key={result.get('key')!r} version={result.get('version')!r}"
            )
        page_classes = result.get("page_classes")
        if not isinstance(page_classes, dict) or not page_classes:
            raise CommandError(f"W4C: base result for {key} has no page_classes")
        any_non_pass = False
        for page_class, by_viewport in page_classes.items():
            if not isinstance(by_viewport, dict) or not by_viewport:
                raise CommandError(f"W4C: base result for {key}/{page_class} is malformed")
            for viewport, cell in by_viewport.items():
                self._validate_base_cell_schema(cell, context=f"{key}/{page_class}/{viewport}")
                if cell["result"] != "PASS":
                    any_non_pass = True
        return any_non_pass

    def _validate_theme_result_freshness(self, result, *, run_token: str, key: str, occasion: str,
                                          intensity: str, viewport: str, tier: str) -> bool:
        if not isinstance(result, dict):
            raise CommandError(f"W4C: malformed theme result for {key} (not a JSON object)")
        if result.get("run_token") != run_token:
            raise CommandError(f"W4C: stale/foreign theme result for {key} -- run_token mismatch")
        identity = (result.get("key"), result.get("occasion"), result.get("intensity"),
                    result.get("viewport"), result.get("tier"))
        if identity != (key, occasion, intensity, viewport, tier):
            raise CommandError(
                f"W4C: theme result identity mismatch for {key}/{tier}/{occasion}/{intensity}/{viewport}: "
                f"found {identity}"
            )
        missing = [field for field in W4C_REQUIRED_THEME_RESULT_FIELDS if field not in result]
        if missing:
            raise CommandError(f"W4C: theme result for {key}/{tier} is missing required fields {missing}: {result!r}")
        if result["result"] not in W4C_VALID_CELL_RESULTS:
            raise CommandError(f"W4C: theme result for {key}/{tier} has an invalid result {result['result']!r}")
        return result["result"] != "PASS"

    def _w4c_expected_theme_dom(self, occasion: str) -> dict:
        """Section 3.1/W2 -- the real, live, source-backed public DOM proof
        of a rendered occasion Theme (``templates/base.html``'s
        ``data-occasion-*``/``--occasion-accent`` attributes). Reads the
        SAME canonical ``theme_catalog`` the appearance-authority service
        itself uses -- never a second, hand-maintained copy of these
        per-occasion values in the Node runner."""
        from apps.storefront_builder import theme_catalog

        entry = next(o for o in theme_catalog.list_theme_occasions() if o.occasion_key == occasion)
        return {"tone": entry.tone, "accent": entry.accent, "motif": entry.motif}

    # -- campaign matrix (section 3.9/3.10/13/15) -----------------------------
    def _validate_or_init_campaign_matrix(self, matrix_path: Path) -> None:
        matrix_path = Path(matrix_path)
        if not matrix_path.exists():
            matrix_path.parent.mkdir(parents=True, exist_ok=True)
            matrix_path.write_text(json.dumps({
                "_meta": {
                    "schema_version": W4C_MATRIX_SCHEMA_VERSION,
                    "certified_base_sha": W4C_CERTIFIED_BASE_SHA,
                    "total_cells_expected": W4C_TOTAL_CELLS_EXPECTED,
                    "duplicate_cells": [],
                    "recovered_state_events": [],
                },
                "templates": {},
            }, indent=2), encoding="utf-8")
            return
        existing = json.loads(matrix_path.read_text(encoding="utf-8"))
        meta = existing.get("_meta", {})
        if meta.get("schema_version") != W4C_MATRIX_SCHEMA_VERSION or meta.get("certified_base_sha") != W4C_CERTIFIED_BASE_SHA:
            raise CommandError(
                f"W4C: {matrix_path} belongs to a different campaign/schema "
                f"({meta.get('schema_version')!r}/{meta.get('certified_base_sha')!r}) -- "
                "use a different --report-dir to start a new campaign; never silently merge across roots"
            )

    def _load_matrix(self, matrix_path: Path) -> dict:
        return json.loads(Path(matrix_path).read_text(encoding="utf-8"))

    def _save_matrix(self, matrix_path: Path, matrix: dict) -> None:
        matrix_path = Path(matrix_path)
        fd, tmp_path = tempfile.mkstemp(prefix="rastisi-w4c-matrix-", dir=str(matrix_path.parent))
        os.close(fd)
        Path(tmp_path).write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, matrix_path)

    def _merge_base_into_matrix(self, matrix_path: Path, key: str, version: str, base_result: dict) -> int:
        """IMPORTANT 3 (repaired) -- insert-only. A cell that already carries
        ANY terminal result (PASS, FAIL, or BLOCKED alike -- never just
        "already PASS") is never overwritten by ordinary resume; the
        conflicting attempt is recorded in ``_meta.duplicate_cells`` and
        skipped. A genuine recheck is a separate, explicitly-invoked mode
        that does not exist in W4C today."""
        matrix = self._load_matrix(matrix_path)
        entry = matrix["templates"].setdefault(key, {"key": key, "version": version, "page_classes": {}, "theme": {"tier1_cell": None, "tier2_cells": {}}})
        entry["version"] = version
        recorded = 0
        for page_class, by_viewport in (base_result.get("page_classes") or {}).items():
            entry["page_classes"].setdefault(page_class, {})
            for viewport, cell in by_viewport.items():
                existing_cell = entry["page_classes"][page_class].get(viewport)
                if existing_cell is not None and existing_cell.get("result") in W4C_VALID_CELL_RESULTS:
                    matrix["_meta"].setdefault("duplicate_cells", []).append(f"base::{key}::{page_class}::{viewport}")
                    continue
                entry["page_classes"][page_class][viewport] = cell
                recorded += 1
        self._save_matrix(matrix_path, matrix)
        return recorded

    def _merge_theme_into_matrix(self, matrix_path: Path, key: str, version: str, occasion: str, intensity: str,
                                  viewport: str, tier: str, theme_result: dict) -> int:
        matrix = self._load_matrix(matrix_path)
        entry = matrix["templates"].setdefault(key, {"key": key, "version": version, "page_classes": {}, "theme": {"tier1_cell": None, "tier2_cells": {}}})
        entry["version"] = version
        entry.setdefault("theme", {"tier1_cell": None, "tier2_cells": {}})
        cell_payload = {"occasion": occasion, "intensity": intensity, "viewport": viewport, **theme_result}
        if tier == "tier1":
            existing = entry["theme"].get("tier1_cell")
            if existing is not None and existing.get("result") in W4C_VALID_CELL_RESULTS:
                matrix["_meta"].setdefault("duplicate_cells", []).append(f"theme::tier1::{key}")
                self._save_matrix(matrix_path, matrix)
                return 0
            entry["theme"]["tier1_cell"] = cell_payload
        else:
            slot = f"{occasion}__{intensity}__{viewport}"
            existing = entry["theme"].setdefault("tier2_cells", {}).get(slot)
            if existing is not None and existing.get("result") in W4C_VALID_CELL_RESULTS:
                matrix["_meta"].setdefault("duplicate_cells", []).append(f"theme::tier2::{key}::{slot}")
                self._save_matrix(matrix_path, matrix)
                return 0
            entry["theme"]["tier2_cells"][slot] = cell_payload
        self._save_matrix(matrix_path, matrix)
        return 1

    # -- resume: execute only missing cells (Code Review Repair Round 1,
    # IMPORTANT 3) -------------------------------------------------------------
    def _missing_base_cells(self, matrix: dict, key: str) -> list:
        entry = matrix.get("templates", {}).get(key, {})
        page_classes = entry.get("page_classes", {})
        missing = []
        for page_class, viewport in self._base_cell_matrix():
            cell = page_classes.get(page_class, {}).get(viewport)
            if cell is None or cell.get("result") not in W4C_VALID_CELL_RESULTS:
                missing.append((page_class, viewport))
        return missing

    def _cell_already_recorded_theme(self, matrix: dict, key: str, occasion: str, intensity: str,
                                      viewport: str, tier: str) -> bool:
        entry = matrix.get("templates", {}).get(key, {})
        theme = entry.get("theme", {})
        if tier == "tier1":
            cell = theme.get("tier1_cell")
        else:
            cell = (theme.get("tier2_cells") or {}).get(f"{occasion}__{intensity}__{viewport}")
        return bool(cell and cell.get("result") in W4C_VALID_CELL_RESULTS)

    def _record_recovered_state_event(self, matrix_path: Path, message: str) -> None:
        from datetime import datetime as _dt

        matrix = self._load_matrix(matrix_path)
        matrix["_meta"].setdefault("recovered_state_events", []).append(
            {"at": _dt.now().isoformat(), "event": message}
        )
        self._save_matrix(matrix_path, matrix)

    def _ensure_published_with_recovery(self, store: Store, preset, matrix_path: Path) -> None:
        layout = layout_service.get_or_create_layout(store)
        pv = layout.published_version
        template = (pv.template_provenance or {}).get("template") if pv else None
        already_correct = bool(
            pv is not None and pv.status == pv.Status.PUBLISHED
            and template and template.get("key") == preset.key and template.get("version") == preset.version
        )
        self._apply_and_verify_published(store, preset)
        if not already_correct:
            self._record_recovered_state_event(
                matrix_path, f"published Template drift repaired for {preset.key} v{preset.version}",
            )

    def _theme_currently_none(self, store: Store) -> bool:
        layout = layout_service.get_or_create_layout(store)
        pv = layout.published_version
        manifest = load_store_appearance_manifest(pv) if (pv and pv.status == pv.Status.PUBLISHED) else None
        return bool(manifest and manifest.selections.get("theme") == "theme.none.v1")

    def _ensure_theme_none_with_recovery(self, store: Store, matrix_path: Path, *, known_drifted: bool) -> None:
        """``known_drifted`` must be captured by the CALLER before any other
        Store-state operation for this cell runs (in particular, before
        ``_ensure_published_with_recovery``'s own Template reapplication,
        which -- as a side effect of restoring the preset's own baseline
        appearance manifest -- can silently reset a drifted Theme back to
        ``theme.none.v1`` on its own). Capturing drift state up front means
        this is logged correctly regardless of which step ultimately fixes
        it, and this function always performs a real, explicit cleanup for
        a known-drifted cell rather than relying on that side effect."""
        if not known_drifted:
            self._verify_theme_is_none(store)
            return
        self._theme_cleanup_and_verify(store)
        self._record_recovered_state_event(matrix_path, "published Theme drift repaired to theme.none.v1")

    def _all_expected_w4c_cell_ids(self) -> set:
        presets = lpr.list_ready_templates()
        keys = [p.key for p in presets]
        tier1_occasions = {
            p.key: W4C_TIER1_OCCASION_CYCLE[i % len(W4C_TIER1_OCCASION_CYCLE)]
            for i, p in enumerate(presets)
        }
        ids = set()
        for key in keys:
            for page_class, viewport in self._base_cell_matrix():
                ids.add(f"base::{key}::{page_class}::{viewport}")
            ids.add(f"theme::tier1::{key}")
        for key, occasion, intensity, viewport in self._planned_tier2_cells(list(W4C_TIER2_KEYS)):
            ids.add(f"theme::tier2::{key}::{occasion}__{intensity}__{viewport}")
        return ids

    def _run_final_w4c_aggregator(self, matrix_path: Path) -> dict:
        """Section 15/3.10 — the SAME aggregator, run on every invocation
        (full or ``--only``-partial). Recomputes real coverage from the
        matrix's own content -- never trusts a possibly-stale claimed
        count."""
        matrix = self._load_matrix(matrix_path)
        expected = self._all_expected_w4c_cell_ids()
        recorded_ids = set()
        fail_count = 0
        blocked_count = 0
        for key, entry in matrix.get("templates", {}).items():
            for page_class, by_viewport in (entry.get("page_classes") or {}).items():
                for viewport, cell in by_viewport.items():
                    recorded_ids.add(f"base::{key}::{page_class}::{viewport}")
                    if cell.get("result") == "FAIL":
                        fail_count += 1
                    elif cell.get("result") == "BLOCKED":
                        blocked_count += 1
            theme = entry.get("theme") or {}
            tier1_cell = theme.get("tier1_cell")
            if tier1_cell:
                recorded_ids.add(f"theme::tier1::{key}")
                if tier1_cell.get("result") == "FAIL":
                    fail_count += 1
                elif tier1_cell.get("result") == "BLOCKED":
                    blocked_count += 1
            for slot, cell in (theme.get("tier2_cells") or {}).items():
                recorded_ids.add(f"theme::tier2::{key}::{slot}")
                if cell.get("result") == "FAIL":
                    fail_count += 1
                elif cell.get("result") == "BLOCKED":
                    blocked_count += 1
        missing = sorted(expected - recorded_ids)
        duplicate_cells = list((matrix.get("_meta") or {}).get("duplicate_cells", []))
        return {
            "total_cells_recorded": len(recorded_ids & expected),
            "missing_cells": missing,
            "duplicate_cells": duplicate_cells,
            "fail_count": fail_count,
            "blocked_count": blocked_count,
        }

    # -- one Theme cell (section 3.2/3.6) -------------------------------------
    def _run_one_theme_cell(self, *, store, key, version, occasion, intensity, viewport, tier,
                             campaign_root, matrix_path, node, run_mjs_path, r4_tool_dir, base_manifest) -> int:
        # IMPORTANT 3 (repaired) -- resume executes only missing cells: an
        # already-terminal cell is skipped entirely, before touching Store
        # state at all.
        matrix = self._load_matrix(matrix_path)
        if self._cell_already_recorded_theme(matrix, key, occasion, intensity, viewport, tier):
            return 0

        result_path = self._w4c_theme_result_path(campaign_root, key, occasion, intensity, viewport, tier)
        log_path = self._w4c_theme_log_path(campaign_root, key, occasion, intensity, viewport, tier)
        theme_result = None
        try:
            preset = lpr.get_layout_preset(key)
            # Captured BEFORE the Template-recovery step below, whose own
            # preset-baseline reapplication can otherwise silently reset a
            # drifted Theme back to none as a side effect and hide genuine
            # drift from the Theme-recovery log.
            theme_was_drifted = not self._theme_currently_none(store)
            self._ensure_published_with_recovery(store, preset, matrix_path)
            self._ensure_theme_none_with_recovery(store, matrix_path, known_drifted=theme_was_drifted)
            draft = layout_service.get_or_create_draft(store)
            occasion_component_key = f"theme.{occasion}.v1"
            appearance_authority_service.apply_theme(version=draft, component_key=occasion_component_key, intensity=intensity)
            layout_service.publish(store)
            self._verify_published_theme(store, occasion_component_key, intensity)
            # CRITICAL 1 -- never accept a stale result file: unlink any
            # previous file for this exact cell before invoking Node, and
            # bind this invocation to a fresh, unique run_token.
            result_path.unlink(missing_ok=True)
            run_token = self._new_run_token()
            manifest_path = self._write_w4c_theme_manifest(
                base=base_manifest, key=key, version=version, occasion=occasion, intensity=intensity,
                viewport=viewport, tier=tier, result_path=result_path, run_token=run_token,
                expected_theme=self._w4c_expected_theme_dom(occasion),
            )
            try:
                node_exit = self._run_logged([node, str(run_mjs_path), manifest_path], cwd=r4_tool_dir, log_path=log_path)
                if not result_path.exists():
                    raise CommandError(
                        f"W4C: BLOCKED -- no result produced for theme cell {key}/{tier}/{occasion}/"
                        f"{intensity}/{viewport} (node_exit={node_exit})"
                    )
                try:
                    theme_result = json.loads(result_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise CommandError(
                        f"W4C: BLOCKED -- malformed theme result JSON for {key}/{tier}: {exc}"
                    ) from exc
                any_non_pass = self._validate_theme_result_freshness(
                    theme_result, run_token=run_token, key=key, occasion=occasion,
                    intensity=intensity, viewport=viewport, tier=tier,
                )
                if node_exit != 0 and not any_non_pass:
                    raise CommandError(
                        f"W4C: BLOCKED -- theme cell {key}/{tier} Node exited {node_exit} but the "
                        "result reports no FAIL/BLOCKED (inconsistent)"
                    )
            finally:
                Path(manifest_path).unlink(missing_ok=True)
        finally:
            # Always runs, whether the try block above passed, FAILed, or
            # raised. If cleanup itself raises, the run halts immediately
            # (section 3.2's Important-2C exception) -- BLOCKED, and the
            # cell above is NEVER merged (IMPORTANT 2: cleanup_verified must
            # never be a lie).
            self._theme_cleanup_and_verify(store)
        # Reached ONLY when nothing above raised, including cleanup.
        theme_result["cleanup_verified"] = True
        return self._merge_theme_into_matrix(
            matrix_path, key, version, occasion, intensity, viewport, tier, theme_result,
        )

    # -- the full campaign orchestration (section 3.2) ------------------------
    def _run_w4c_campaign(self, *, store, w4c_fixture, selected_keys, campaign_root, node,
                           run_mjs_path, r4_tool_dir, base_manifest) -> dict:
        campaign_root = Path(campaign_root)
        matrix_path = campaign_root / "matrix.json"
        self._validate_or_init_campaign_matrix(matrix_path)

        all_templates = w4c_fixture["templates"]
        by_key = {t["key"]: t["version"] for t in all_templates}
        keys = list(selected_keys) if selected_keys else [t["key"] for t in all_templates]
        cells_recorded_this_run = 0

        # ---------- BASE: one invocation per key, only missing cells -------
        for key in keys:
            version = by_key[key]
            matrix = self._load_matrix(matrix_path)
            missing = self._missing_base_cells(matrix, key)
            if not missing:
                continue  # IMPORTANT 3 -- fully recorded already; skip Node entirely
            preset = lpr.get_layout_preset(key)
            self._ensure_published_with_recovery(store, preset, matrix_path)
            result_path = self._w4c_base_result_path(campaign_root, key)
            log_path = self._w4c_base_log_path(campaign_root, key)
            result_path.unlink(missing_ok=True)  # CRITICAL 1 -- never read a stale file
            run_token = self._new_run_token()
            manifest_path = self._write_w4c_base_manifest(
                base=base_manifest, key=key, version=version, result_path=result_path,
                hero_expected=self._home_hero_expected(preset), hero_index=self._home_hero_index(preset),
                run_token=run_token, cells=missing,
                expected_rsec_count=len(preset.pages.get("home", ())),
                product_cards_expected=self._home_product_cards_expected(preset),
                bottom_nav_expected=self._home_bottom_nav_expected(preset),
            )
            try:
                node_exit = self._run_logged([node, str(run_mjs_path), manifest_path], cwd=r4_tool_dir, log_path=log_path)
                if not result_path.exists():
                    raise CommandError(f"W4C: BLOCKED -- no result produced for base {key} (node_exit={node_exit})")
                try:
                    base_result = json.loads(result_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise CommandError(f"W4C: BLOCKED -- malformed base result JSON for {key}: {exc}") from exc
                any_non_pass = self._validate_base_result_freshness(base_result, run_token=run_token, key=key, version=version)
                if node_exit != 0 and not any_non_pass:
                    raise CommandError(
                        f"W4C: BLOCKED -- base {key} Node exited {node_exit} but the result reports "
                        "no FAIL/BLOCKED cell (inconsistent)"
                    )
            finally:
                Path(manifest_path).unlink(missing_ok=True)
            cells_recorded_this_run += self._merge_base_into_matrix(matrix_path, key, version, base_result)

        # ---------- THEME TIER 1: one invocation per key, 1 cell each -------
        for key in keys:
            version = by_key[key]
            occasion = w4c_fixture["tier1_occasions"][key]
            cells_recorded_this_run += self._run_one_theme_cell(
                store=store, key=key, version=version, occasion=occasion, intensity="balanced",
                viewport="desktop", tier="tier1", campaign_root=campaign_root, matrix_path=matrix_path,
                node=node, run_mjs_path=run_mjs_path, r4_tool_dir=r4_tool_dir, base_manifest=base_manifest,
            )

        # ---------- THEME TIER 2: filtered by selected_keys (Round 4) -------
        for key, occasion, intensity, viewport in self._planned_tier2_cells(keys):
            version = by_key[key]
            cells_recorded_this_run += self._run_one_theme_cell(
                store=store, key=key, version=version, occasion=occasion, intensity=intensity,
                viewport=viewport, tier="tier2", campaign_root=campaign_root, matrix_path=matrix_path,
                node=node, run_mjs_path=run_mjs_path, r4_tool_dir=r4_tool_dir, base_manifest=base_manifest,
            )

        aggregate = self._run_final_w4c_aggregator(matrix_path)
        aggregate["cells_recorded_this_run"] = cells_recorded_this_run
        return aggregate
