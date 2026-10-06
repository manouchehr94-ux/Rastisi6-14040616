"""Checkpoint 5A commit 6 (ADR-68/69, §16): Import/Export entitlement gating
and period-usage integration.

Covers: import/export feature gate (boolean entitlement), monthly import-row
limit (whole-file rejection, no silent truncation), row consumption on execute
only (not preview) and once per job, import product create-budget so imports
cannot bypass the product limit while updates still succeed, export monthly
job limit + consumption on success only, and cleanup not consuming.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ExportJob, ImportJob, ImportRowResult
from apps.core.services import export_service
from apps.dashboard.services import import_service
from apps.stores.models import Store
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc
from apps.subscriptions.services import usage_service as usage
from apps.subscriptions.services.entitlement_service import (
    FeatureNotAvailable,
    UsageLimitExceeded,
)

User = get_user_model()

PRODUCT_HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)


def _csv_upload(text, name="products.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def _store_on_plan(slug, *, entitlements):
    """Create a store with an active subscription whose published plan version
    carries the given ``entitlements`` = {key: {"is_enabled":.., "integer_limit":..}}."""
    ent.clear_entitlement_cache()
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"plan-{slug}", name=slug)
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
    )
    for key, spec in entitlements.items():
        definition = EntitlementDefinition.objects.get(key=key)
        PlanEntitlement.objects.create(
            plan_version=version, entitlement=definition,
            is_enabled=spec.get("is_enabled", True),
            integer_limit=spec.get("integer_limit", 0),
        )
    sub = svc.create_subscription(store, version)
    svc.activate_subscription(sub)
    ent.clear_entitlement_cache()
    return store


class ImportFeatureGateTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="imp-gate", is_staff=True)
        self.store = _store_on_plan("imp-off", entitlements={
            ekeys.CATALOG_IMPORT: {"is_enabled": False},
        })

    def test_upload_blocked_when_import_disabled(self):
        with self.assertRaises(FeatureNotAvailable):
            import_service.create_import_job(
                self.store, import_type=ImportJob.ImportType.PRODUCTS,
                uploaded_file=_csv_upload(PRODUCT_HEADER + ",SKU-1,کالا,,,,,,,,,,,,\n"),
                mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
            )
        self.assertFalse(ImportJob.objects.filter(store=self.store).exists())


class ImportRowLimitTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="imp-rows", is_staff=True)
        self.store = _store_on_plan("imp-rows", entitlements={
            ekeys.CATALOG_IMPORT: {"is_enabled": True},
            ekeys.CATALOG_IMPORT_ROWS_MONTHLY: {"is_enabled": True, "integer_limit": 2},
        })
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-ir")
        self.category = Category.objects.create(store=self.store, name="c", slug="c-ir")
        self.leaf = Category.objects.create(store=self.store, name="leaf", slug="leaf-ir", parent=self.category)

    def _rows_csv(self, n):
        body = "".join(
            f",SKU-IR-{i},کالا {i},,,active,,leaf-ir,1000,0,,,,,\n" for i in range(n)
        )
        return PRODUCT_HEADER + body

    def test_preview_does_not_consume_rows(self):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(self._rows_csv(2)),
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 0)

    def test_execute_consumes_rows_once(self):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(self._rows_csv(2)),
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        import_service.run_execution(job, actor=self.actor)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 2)
        # Re-executing a finalized job is refused → no double-consume.
        with self.assertRaises(import_service.ImportServiceError):
            import_service.run_execution(job, actor=self.actor)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 2)

    def test_over_row_limit_rejects_whole_file(self):
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(self._rows_csv(3)),  # 3 > limit 2
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        with self.assertRaises(UsageLimitExceeded):
            import_service.run_execution(job, actor=self.actor)
        # No silent truncation: nothing imported, no rows consumed.
        self.assertFalse(Product.objects.filter(store=self.store).exists())
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 0)


class ImportProductBudgetTests(TestCase):
    """Imports must not bypass the product creation limit (§16), but update rows
    must still succeed at the limit."""

    def setUp(self):
        self.actor = User.objects.create_user(username="imp-budget", is_staff=True)
        self.store = _store_on_plan("imp-budget", entitlements={
            ekeys.CATALOG_IMPORT: {"is_enabled": True},
            ekeys.CATALOG_PRODUCTS: {"is_enabled": True, "integer_limit": 2},
        })
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-ib")
        self.parent = Category.objects.create(store=self.store, name="c", slug="c-ib", parent=None)
        self.category = Category.objects.create(store=self.store, name="leaf", slug="leaf-ib", parent=self.parent)

    def test_file_exceeding_product_limit_is_rejected_whole(self):
        # Limit 2, importing 3 new products: nothing is created (no partial import),
        # and the merchant gets a clear plan-limit message with a fresh preview.
        body = "".join(f",SKU-IB-{i},کالا {i},,,active,,leaf-ib,1000,0,,,,,\n" for i in range(3))
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(PRODUCT_HEADER + body),
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        with self.assertRaises(import_service.ImportExecutionBlocked) as ctx:
            import_service.run_execution(job, actor=self.actor)
        self.assertIn("پلن", str(ctx.exception))
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 0)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_IMPORT_ROWS_MONTHLY), 0)
        self.assertTrue(import_service.job_execution_blockers(job))

    def test_file_within_product_limit_is_applied(self):
        body = "".join(f",SKU-IB-{i},کالا {i},,,active,,leaf-ib,1000,0,,,,,\n" for i in range(2))
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(PRODUCT_HEADER + body),
            mode=ImportJob.Mode.UPSERT, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 2)

    def test_update_rows_succeed_at_limit(self):
        # Fill the limit with 2 products, then import an UPSERT that updates one
        # existing product — updates are not creation, so they pass at the limit.
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="p1",
            slug="p1-ib", sku="SKU-EXIST-1", price=Decimal("1"), stock=0,
        )
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="p2",
            slug="p2-ib", sku="SKU-EXIST-2", price=Decimal("1"), stock=0,
        )
        self.assertEqual(usage.get_count_usage(self.store, ekeys.CATALOG_PRODUCTS), 2)
        ent.clear_entitlement_cache()
        body = ",SKU-EXIST-1,نامِ به‌روزشده,,,active,,,2000,0,,,,,\n"
        job = import_service.create_import_job(
            self.store, import_type=ImportJob.ImportType.PRODUCTS,
            uploaded_file=_csv_upload(PRODUCT_HEADER + body),
            mode=ImportJob.Mode.UPDATE_ONLY, requested_by=self.actor,
        )
        import_service.run_preview(job, actor=self.actor)
        import_service.run_execution(job, actor=self.actor)
        job.refresh_from_db()
        self.assertEqual(job.updated_rows, 1)
        self.assertEqual(job.failed_rows, 0)
        self.assertEqual(Product.objects.get(sku="SKU-EXIST-1").name, "نامِ به‌روزشده")


class ExportGateTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="exp-gate", is_staff=True)

    def test_export_feature_disabled_blocks(self):
        store = _store_on_plan("exp-off", entitlements={
            ekeys.CATALOG_EXPORT: {"is_enabled": False},
        })
        with self.assertRaises(FeatureNotAvailable):
            export_service.generate_export(store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        self.assertFalse(ExportJob.objects.filter(store=store).exists())

    def test_export_consumes_on_success_and_blocks_at_limit(self):
        store = _store_on_plan("exp-lim", entitlements={
            ekeys.CATALOG_EXPORT: {"is_enabled": True},
            ekeys.CATALOG_EXPORTS_MONTHLY: {"is_enabled": True, "integer_limit": 1},
        })
        export_service.generate_export(store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        self.assertEqual(usage.get_period_usage(store, ekeys.CATALOG_EXPORTS_MONTHLY), 1)
        with self.assertRaises(UsageLimitExceeded):
            export_service.generate_export(store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        # The blocked attempt did not create a job or consume more quota.
        self.assertEqual(ExportJob.objects.filter(store=store).count(), 1)
        self.assertEqual(usage.get_period_usage(store, ekeys.CATALOG_EXPORTS_MONTHLY), 1)


class DirectExportAllowanceTests(TestCase):
    """«خروج اطلاعات» is direct-download: the allowance is spent only after the workbook
    exists, a failed build costs nothing, and no file or expiry is ever retained."""

    def setUp(self):
        self.actor = User.objects.create_user(username="exp-direct", is_staff=True)
        self.store = _store_on_plan("exp-direct", entitlements={
            ekeys.CATALOG_EXPORT: {"is_enabled": True},
            ekeys.CATALOG_EXPORTS_MONTHLY: {"is_enabled": True, "integer_limit": 2},
        })

    def test_failed_generation_does_not_consume_the_allowance(self):
        from unittest import mock

        with mock.patch.object(export_service, "build_export_workbook", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                export_service.generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_EXPORTS_MONTHLY), 0)
        job = ExportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ExportJob.Status.FAILED)
        self.assertFalse(job.file)

    def test_success_consumes_exactly_one_and_retains_only_metadata(self):
        result = export_service.generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_EXPORTS_MONTHLY), 1)
        self.assertEqual(result.content[:2], b"PK")
        job = result.job
        job.refresh_from_db()
        self.assertEqual((job.status, job.row_count), (ExportJob.Status.COMPLETED, result.row_count))
        self.assertFalse(job.file)
        self.assertIsNone(job.expires_at)

    def test_limit_blocks_before_building_anything(self):
        for _ in range(2):
            export_service.generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        with self.assertRaises(UsageLimitExceeded):
            export_service.generate_export(self.store, ExportJob.ExportType.PRODUCTS, requested_by=self.actor)
        self.assertEqual(ExportJob.objects.filter(store=self.store).count(), 2)
        self.assertEqual(usage.get_period_usage(self.store, ekeys.CATALOG_EXPORTS_MONTHLY), 2)
