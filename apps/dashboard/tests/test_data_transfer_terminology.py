"""Merchant-facing terminology: «ورود اطلاعات» / «خروج اطلاعات» only.

Internal identifiers (``ImportJob``, ``ExportJob``, ``import-*`` routes, docstrings) keep their
names. Everything a merchant can see or download — pages, flash messages, service error
messages, generated XLSX (cells, header comments, validation prompts, document properties),
error reports, templates, entitlement labels — must not contain the obsolete words
«واردات» / «صادرات» (which also covers «واردات داده(‌ها)» and «صادرات داده(‌ها)»).
"""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.catalog.models import StockMovement
from apps.core.models import ExportJob, ImportJob
from apps.core.services.export_service import ExportError, generate_export
from apps.dashboard import navigation
from apps.dashboard.services import import_service, import_xlsx
from apps.dashboard.tests.test_export_views import SHEET_TITLES, ExportTestCase
from apps.dashboard.tests.xlsx_helpers import open_workbook
from apps.stores.models import Store
from apps.subscriptions import entitlements

OBSOLETE = ("واردات", "صادرات")
NAMED_OBSOLETE = ("واردات داده", "واردات داده‌ها", "صادرات داده", "صادرات داده‌ها")
HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)
SERVICE = "apps.dashboard.services.import_service"


def workbook_texts(content: bytes) -> list[str]:
    """Every merchant-readable string inside a workbook."""
    wb = open_workbook(content)
    texts = [str(wb.properties.__dict__.get(name) or "") for name in
             ("title", "subject", "description", "creator", "keywords", "category", "lastModifiedBy")]
    for ws in wb.worksheets:
        texts.append(ws.title)
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    texts.append(str(cell.value))
                if cell.comment is not None:
                    texts.append(cell.comment.text)
        for validation in ws.data_validations.dataValidation:
            texts.extend(str(v or "") for v in (
                validation.prompt, validation.promptTitle, validation.error, validation.errorTitle,
            ))
    return texts


class TerminologyTestCase(ExportTestCase):
    def assertClean(self, text, where=""):
        text = text if isinstance(text, str) else " ".join(text)
        for word in OBSOLETE + NAMED_OBSOLETE:
            self.assertNotIn(word, text, f"obsolete term «{word}» found in {where}")

    def _csv_upload(self, rows):
        return SimpleUploadedFile("t.csv", (HEADER + rows).encode(), content_type="text/csv")

    def _job(self, rows, *, preview=True, mode=ImportJob.Mode.CREATE_ONLY):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS, uploaded_file=self._csv_upload(rows),
            mode=mode, requested_by=self.owner,
        )
        if preview:
            import_service.run_preview(job, actor=self.owner)
        return job


GOOD = ",TERM-1,کالا,,,active,brand-exp,leaf-exp,1000,1,,,,,\n"
BAD = ",,,,,,,,,,,,,,\n"


class GeneratedWorkbookTerminologyTests(TerminologyTestCase):
    def test_every_export_workbook_is_clean(self):
        empty = Store.objects.create(name="خالی", slug="term-empty")
        for store in (self.store, empty):
            for export_type in SHEET_TITLES:
                with self.subTest(store=store.slug, export_type=export_type):
                    result = generate_export(store, export_type, requested_by=self.owner)
                    self.assertClean(workbook_texts(result.content), f"{export_type} export")

    def test_export_guides_point_merchants_to_the_new_names(self):
        products = " ".join(workbook_texts(
            generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.owner).content,
        ))
        self.assertIn("«ورود اطلاعات»", products)
        self.assertIn("«خروج اطلاعات»", products)
        inventory = " ".join(workbook_texts(
            generate_export(self.store, ExportJob.ExportType.INVENTORY, requested_by=self.owner).content,
        ))
        self.assertIn("«ورود اطلاعات ← موجودی انبار»", inventory)

    def test_every_import_template_is_clean_and_uses_the_new_names(self):
        for import_type in ImportJob.ImportType.values:
            with self.subTest(import_type=import_type):
                response = self.client.get(reverse("dashboard:import-template", args=[import_type]))
                self.assertEqual(response.status_code, 200)
                texts = workbook_texts(response.content)
                self.assertClean(texts, f"{import_type} template")
                self.assertIn("«ورود اطلاعات»", " ".join(texts))

    def test_xlsx_error_report_is_clean(self):
        job = self._job(GOOD + BAD)
        self.assertTrue(job.error_report_file)
        response = self.client.get(reverse("dashboard:import-download-errors", args=[job.pk]))
        content = b"".join(response.streaming_content)
        texts = workbook_texts(content)
        self.assertClean(texts, "error report")
        self.assertIn("ورودِ اطلاعات", " ".join(texts))


class PageAndMessageTerminologyTests(TerminologyTestCase):
    def _flash(self, response):
        return " ".join(str(m) for m in response.context["messages"])

    def test_all_merchant_pages_in_every_state_are_clean(self):
        pages = {"export-list": self.client.get(reverse("dashboard:export-list"))}
        pages["import-list"] = self.client.get(reverse("dashboard:import-list"))
        pages["import-upload"] = self.client.get(reverse("dashboard:import-upload"))
        clean = self._job(GOOD)
        blocked = self._job(GOOD + BAD)
        uploaded = self._job(GOOD, preview=False)
        failed = self._job(GOOD)
        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=RuntimeError("x")):
            import_service.run_execution(failed, actor=self.owner)
        done = self._job(GOOD.replace("TERM-1", "TERM-2"))
        import_service.run_execution(done, actor=self.owner)
        for name, job in (("clean", clean), ("blocked", blocked), ("uploaded", uploaded),
                          ("rolled-back", failed), ("completed", done)):
            pages[f"detail-{name}"] = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        for name, response in pages.items():
            self.assertEqual(response.status_code, 200, name)
            self.assertClean(response.content.decode(), f"page {name}")

    def test_flash_messages_of_every_execute_outcome_are_clean(self):
        outcomes = {}
        blocked = self._job(GOOD + BAD)
        outcomes["blocked"] = self.client.post(reverse("dashboard:import-execute", args=[blocked.pk]), follow=True)
        uploaded = self._job(GOOD, preview=False)
        outcomes["uploaded"] = self.client.post(reverse("dashboard:import-execute", args=[uploaded.pk]), follow=True)
        failed = self._job(GOOD)
        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=RuntimeError("x")):
            outcomes["rolled-back"] = self.client.post(
                reverse("dashboard:import-execute", args=[failed.pk]), follow=True,
            )
        ok = self._job(GOOD.replace("TERM-1", "TERM-3"))
        outcomes["ok"] = self.client.post(reverse("dashboard:import-execute", args=[ok.pk]), follow=True)
        outcomes["replay"] = self.client.post(reverse("dashboard:import-execute", args=[ok.pk]), follow=True)
        cancelled = self._job(GOOD.replace("TERM-1", "TERM-4"))
        outcomes["cancel"] = self.client.post(reverse("dashboard:import-cancel", args=[cancelled.pk]), follow=True)
        outcomes["cancel-again"] = self.client.post(reverse("dashboard:import-cancel", args=[cancelled.pk]), follow=True)
        for name, response in outcomes.items():
            flash = self._flash(response)
            self.assertTrue(flash, name)
            self.assertClean(flash, f"flash message after {name}")
        self.assertIn("ورودِ اطلاعات با موفقیت انجام شد", self._flash(outcomes["ok"]))

    def test_service_error_messages_are_clean(self):
        job_args = dict(store=self.store, uploaded_file=self._csv_upload(GOOD), mode="create_only", requested_by=self.owner)
        messages = []

        def capture(func, *args, **kwargs):
            with self.assertRaises(Exception) as ctx:
                func(*args, **kwargs)
            messages.append(str(ctx.exception))

        capture(import_service.create_import_job, import_type="nonsense", **job_args)
        capture(import_service.build_template_xlsx, self.store, "nonsense")
        capture(import_service.build_template_csv, "nonsense")
        first = import_service.create_import_job(import_type="products", idempotency_key="k1", **job_args)
        job_args["uploaded_file"] = self._csv_upload(GOOD)
        capture(import_service.create_import_job, import_type="products", idempotency_key="k1", **job_args)
        capture(import_service.run_execution, first, actor=self.owner)  # uploaded: no preview yet
        import_service.run_preview(first, actor=self.owner)
        import_service.run_execution(first, actor=self.owner)
        capture(import_service.run_execution, first, actor=self.owner)  # replay
        capture(import_service.run_preview, first, actor=self.owner)
        capture(import_service.cancel_import_job, first, actor=self.owner)
        capture(generate_export, self.store, "nonsense", requested_by=self.owner)
        job = self._job(GOOD.replace("TERM-1", "TERM-9"))
        messages.append(" ".join(import_service.job_execution_blockers(
            self._job(GOOD + BAD),
        )))
        ImportJob.objects.filter(pk=job.pk).update(status=ImportJob.Status.CANCELLED)
        job.refresh_from_db()
        messages.append(" ".join(import_service.job_execution_blockers(job)))
        self.assertTrue(all(messages))
        self.assertClean(messages, "service error messages")
        self.assertTrue(issubclass(ExportError, Exception))

    def test_rollback_result_texts_are_clean(self):
        job = self._job(GOOD + GOOD.replace("TERM-1", "TERM-7"))
        real = import_service._apply_product_row
        calls = {"n": 0}

        def second_row_fails(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("x")
            return real(**kwargs)

        with mock.patch(f"{SERVICE}._apply_product_row", side_effect=second_row_fails):
            import_service.run_execution(job, actor=self.owner)
        job.refresh_from_db()
        texts = [job.error_summary] + [w for r in job.row_results.all() for w in r.warnings + r.errors]
        self.assertClean(texts, "rollback result texts")
        self.assertIn("ورودِ اطلاعات", " ".join(texts))

    def test_plan_limit_text_is_clean(self):
        job = self._job(GOOD + GOOD.replace("TERM-1", "TERM-2"))
        with mock.patch("apps.subscriptions.services.enforcement.product_creation_budget", return_value=1):
            with self.assertRaises(import_service.ImportExecutionBlocked) as ctx:
                import_service.run_execution(job, actor=self.owner)
        self.assertClean(str(ctx.exception), "plan limit message")

    def test_import_xlsx_help_text_is_clean(self):
        for import_type, columns in import_xlsx.IMPORT_SPECS.items():
            for column in columns:
                self.assertClean(
                    " ".join(str(getattr(column, a, "") or "") for a in ("label", "help", "accepted", "example", "blank")),
                    f"{import_type}.{column.key} help",
                )
        self.assertClean(list(import_xlsx.MODE_LABELS.values()) + list(import_xlsx.MODE_DESCRIPTIONS.values()), "mode texts")


class StaticLabelTerminologyTests(TerminologyTestCase):
    def test_navigation_tabs_use_the_new_names(self):
        labels = {tab.key: tab.label for section in navigation.SECTIONS for tab in section.tabs}
        self.assertEqual(labels["imports"], "ورود اطلاعات")
        self.assertEqual(labels["exports"], "خروج اطلاعات")
        self.assertClean([section.label for section in navigation.SECTIONS] + list(labels.values()), "navigation labels")

    def test_command_palette_path_labels(self):
        response = self.client.get(reverse("dashboard:import-list"))
        html = response.content.decode()
        self.assertIn("تنظیمات ← ورود اطلاعات", html)
        self.assertIn("تنظیمات ← خروج اطلاعات", html)
        self.assertClean(html, "palette markup of the import page")

    def test_entitlement_and_usage_labels(self):
        names = [name for _key, name, _type, _default in entitlements.ENTITLEMENT_DEFINITIONS]
        self.assertClean(names, "entitlement definitions")
        self.assertClean(list(entitlements.PERIOD_METRIC_KEYS.values()), "usage metric labels")
        by_key = {key: name for key, name, _t, _d in entitlements.ENTITLEMENT_DEFINITIONS}
        self.assertEqual(by_key["catalog.import"], "ورود اطلاعات (Import)")
        self.assertEqual(by_key["catalog.export"], "خروج اطلاعات (Export)")

    def test_synced_definitions_in_the_database_are_clean(self):
        from apps.subscriptions.models import EntitlementDefinition

        entitlements.sync_entitlement_definitions()
        self.assertClean(list(EntitlementDefinition.objects.values_list("name", flat=True)), "definition rows")

    def test_rename_migration_updates_existing_rows_and_is_reversible(self):
        import importlib

        from django.apps import apps as django_apps

        from apps.subscriptions.models import EntitlementDefinition

        migration = importlib.import_module("apps.subscriptions.migrations.0008_rename_import_export_entitlement_labels")
        entitlements.sync_entitlement_definitions()
        forward = migration.Migration.operations[0].code
        backward = migration.Migration.operations[0].reverse_code
        backward(django_apps, None)
        self.assertEqual(EntitlementDefinition.objects.get(key="catalog.import").name, "واردات (Import)")
        forward(django_apps, None)
        self.assertEqual(EntitlementDefinition.objects.get(key="catalog.import").name, "ورود اطلاعات (Import)")
        self.assertEqual(EntitlementDefinition.objects.get(key="catalog.exports_monthly").name, "دفعاتِ خروج اطلاعات در ماه")

    def test_stock_movement_reason_labels(self):
        self.assertClean([label for _value, label in StockMovement.Reason.choices], "stock movement reasons")
        self.assertIn("ورود اطلاعات", StockMovement.Reason.IMPORT_ADJUSTMENT.label)

    def test_export_and_import_choice_labels(self):
        self.assertClean([label for _v, label in ExportJob.ExportType.choices], "export type labels")
        self.assertClean([label for _v, label in ImportJob.ImportType.choices], "import type labels")
        self.assertClean([label for _v, label in ImportJob.Status.choices], "import status labels")
        self.assertClean([label for _v, label in ImportJob.Mode.choices], "import mode labels")

    def test_model_verbose_names_shown_in_admin_forms_are_clean(self):
        from apps.core.models import ImportRowResult

        texts = []
        for model in (ExportJob, ImportJob, ImportRowResult):
            texts += [str(model._meta.verbose_name), str(model._meta.verbose_name_plural)]
            texts += [str(f.verbose_name) for f in model._meta.get_fields() if hasattr(f, "verbose_name")]
        self.assertClean(texts, "model verbose names")
