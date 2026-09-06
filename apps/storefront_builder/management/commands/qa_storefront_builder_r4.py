from __future__ import annotations

import hashlib
import json
import os
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
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontEditHistoryEntry
from apps.storefront_builder.services import container_service, layout_service
from apps.stores.models import Store, StoreMembership


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

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This disposable browser QA is only permitted with DEBUG=True.")

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
        try:
            fixture = self._prepare_r4_sandbox(store, user)

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
    def _prepare_r4_sandbox(self, store: Store, user) -> dict:
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

        return {
            "hero_section_id": hero.pk,
            "brand_carousel_section_id": brand_carousel.pk,
            "draft_revision": draft.edit_revision,
        }

    def _build_manifest(self, *, store, port, session_cookie, report_dir, headed, browser_channel, phase3=False):
        origin = f"http://127.0.0.1:{port}"
        same_site = str(settings.SESSION_COOKIE_SAMESITE or "Lax").capitalize()
        if same_site not in {"Lax", "Strict", "None"}:
            same_site = "Lax"
        return {
            "origin": origin,
            "builder_url": f"{origin}/admin-portal/storefront-builder/r4/",
            "public_url": f"{origin}/",
            "report_dir": str(report_dir),
            "headed": bool(headed),
            "browser_channel": browser_channel,
            "phase3": bool(phase3),
            "session": {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_cookie,
                "domain": "127.0.0.1",
                "path": settings.SESSION_COOKIE_PATH or "/",
                "httpOnly": bool(settings.SESSION_COOKIE_HTTPONLY),
                "secure": bool(settings.SESSION_COOKIE_SECURE),
                "sameSite": same_site,
            },
            "store": {"id": store.pk, "name": store.name, "slug": store.slug},
        }

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
