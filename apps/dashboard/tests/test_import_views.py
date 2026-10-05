"""View-level tests for the Merchant Admin Import UI (checkpoint 4B §19-21):
upload → preview → execute → results flow, error-report and source
downloads, permissions, tenant isolation, invalid-file handling, and the
XLSX template downloads, the redesigned upload page, XLSX upload/preview/execute,
XLSX source/error-report downloads, and legacy CSV compatibility."""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor, Warehouse
from apps.core.models import ImportJob
from apps.dashboard.services import import_service
from apps.dashboard.tests.xlsx_helpers import (
    XLSX_MIME,
    make_xlsx,
    open_workbook,
    read_job_file,
    sheet_values,
    xlsx_upload,
)
from apps.orders.models import TaxClass
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"import-view-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

PRODUCT_HEADER = (
    "product_id,sku,name,slug,barcode,status,brand_code,category_code,"
    "price,stock,weight_grams,requires_shipping,tax_class_code,seo_title,seo_description\n"
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _csv(text, name="products.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ImportViewTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "import-view-test"
        self.store.save(update_fields=["admin_subdomain"])
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-ivw")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-ivw", parent=None)
        self.leaf = Category.objects.create(store=self.store, name="زیردسته", slug="leaf-ivw", parent=self.category)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-ivw")

        self.owner = User.objects.create_user(username="ivw-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="ivw-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"ivw-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")

    def _valid_product_csv(self):
        return PRODUCT_HEADER + ",SKU-IVW-1,کالای وارداتی,,,active,brand-ivw,leaf-ivw,150000,8,,,,,\n"


class UploadPreviewFlowTests(ImportViewTestCase):
    def test_upload_creates_job_and_preview(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(job.valid_rows, 1)
        # Preview did not create the product.
        self.assertFalse(Product.objects.filter(store=self.store, sku="SKU-IVW-1").exists())
        self.assertIn(reverse("dashboard:import-detail", args=[job.pk]), response.url)

    def test_upload_without_file_errors(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.UPSERT,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ImportJob.objects.exists())

    def test_upload_unsupported_binary_rejected(self):
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.UPSERT,
            "file": SimpleUploadedFile("data.xlsx", b"binary", content_type="application/octet-stream"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ImportJob.objects.exists())

    def test_execute_runs_and_creates_product(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertTrue(Product.objects.filter(store=self.store, sku="SKU-IVW-1").exists())

    def test_detail_page_renders(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نتیجه‌ی ردیف‌ها")


class ErrorReportTests(ImportViewTestCase):
    def test_error_report_generated_and_downloadable(self):
        bad_csv = PRODUCT_HEADER + ",,,,,,,,,,,,,,\n"  # invalid: no name/category/price
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(bad_csv),
        })
        job = ImportJob.objects.get(store=self.store)
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        self.assertTrue(job.error_report_file)
        response = self.client.get(reverse("dashboard:import-download-errors", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        self.assertIn(f"products-errors-{job.pk}.xlsx", response["Content-Disposition"])
        body = b"".join(response.streaming_content)
        self.assertEqual(body[:2], b"PK")
        self.assertEqual(open_workbook(body).sheetnames, ["خطاها", "راهنما"])

    def test_source_downloadable(self):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        job = ImportJob.objects.get(store=self.store)
        response = self.client.get(reverse("dashboard:import-download-source", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        # a legacy CSV upload is downloaded as CSV (never forced to another format)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(f"products-source-{job.pk}.csv", response["Content-Disposition"])


INTERNAL_TERMS = (
    "category_code", "brand_code", "warehouse_code", "tax_class_code", "option_1_code", "set_on_hand",
    "product_sku", "variant_sku", "weight_grams", "requires_shipping", "compare_at_price",
)


class TemplateDownloadTests(ImportViewTestCase):
    def setUp(self):
        super().setUp()
        self.tax = TaxClass.objects.create(store=self.store, name="عمومیِ تست", code="gen-ivw")
        self.warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="ivw-tpl-other")
        Brand.objects.create(store=self.other_store, name="برندِ بیگانه", slug="foreign-brand-ivw")
        other_root = Category.objects.create(store=self.other_store, name="ریشه‌ی بیگانه", slug="f-root-ivw")
        Category.objects.create(store=self.other_store, name="برگِ بیگانه", slug="f-leaf-ivw", parent=other_root)

    def _template(self, import_type):
        response = self.client.get(reverse("dashboard:import-template", args=[import_type]))
        self.assertEqual(response.status_code, 200)
        return response, open_workbook(response.content)

    def _all_text(self, wb):
        return "\n".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None)

    def test_templates_are_real_xlsx_with_the_agreed_sheets(self):
        for import_type in ("products", "variants", "inventory"):
            with self.subTest(import_type=import_type):
                response, wb = self._template(import_type)
                self.assertEqual(response["Content-Type"], XLSX_MIME)
                self.assertIn(f"{import_type}-import-template.xlsx", response["Content-Disposition"])
                self.assertEqual(response.content[:2], b"PK")
                self.assertEqual(wb.sheetnames, ["داده‌ها", "راهنما", "فهرست‌ها"])
                self.assertTrue(wb["داده‌ها"].sheet_view.rightToLeft)
                self.assertEqual(wb["داده‌ها"].freeze_panes, "A2")
                # the editable sheet holds only the header row (the rest is pre-formatted but empty)
                values_below_header = [c.value for row in wb["داده‌ها"].iter_rows(min_row=2) for c in row if c.value is not None]
                self.assertEqual(values_below_header, [])

    def test_product_template_columns_and_required_markers(self):
        _response, wb = self._template("products")
        header = [c.value for c in wb["داده‌ها"][1]]
        self.assertEqual(header, [
            "شناسه کالا", "SKU", "نام کالا *", "وضعیت", "برند", "دسته‌بندی *", "قیمت (تومان) *", "موجودی",
            "بارکد", "وزن (گرم)", "نیاز به ارسال", "دسته مالیاتی", "عنوان سئو", "توضیحات سئو",
        ])
        required_fill = wb["داده‌ها"]["C1"].fill.start_color.rgb
        optional_fill = wb["داده‌ها"]["A1"].fill.start_color.rgb
        self.assertNotEqual(required_fill, optional_fill)
        self.assertIn("الزامی", wb["داده‌ها"]["C1"].comment.text)
        self.assertIn("اختیاری", wb["داده‌ها"]["A1"].comment.text)

    def test_no_internal_column_names_are_exposed_anywhere(self):
        for import_type in ("products", "variants", "inventory"):
            _response, wb = self._template(import_type)
            text = self._all_text(wb)
            for term in INTERNAL_TERMS:
                self.assertNotIn(term, text, f"{import_type}: {term}")
            lists_text = "\n".join(str(c.value) for row in wb["فهرست‌ها"].iter_rows() for c in row if c.value)
            self.assertNotRegex(lists_text, r"\bactive\b|\binactive\b")

    def test_guide_sheet_documents_every_column(self):
        for import_type in ("products", "variants", "inventory"):
            with self.subTest(import_type=import_type):
                _response, wb = self._template(import_type)
                guide = sheet_values(wb["راهنما"])
                table_start = next(i for i, row in enumerate(guide) if row and row[0] == "ستون")
                self.assertEqual(guide[table_start][:6], ["ستون", "الزامی؟", "توضیح", "مقدارهایِ مجاز", "مثال", "اگر خالی بماند"])
                documented = [row[0] for row in guide[table_start + 1:] if row and row[0]]
                data_header = [str(c.value).replace(" *", "") for c in wb["داده‌ها"][1]]
                self.assertEqual(documented, data_header)
                for row in guide[table_start + 1:]:
                    if row and row[0]:
                        self.assertIn(row[1], ("الزامی", "اختیاری", "الزامی برایِ مورد تازه"))
                        self.assertTrue(row[2] and row[3] and row[4] and row[5], row)

    def test_reference_lists_are_store_specific(self):
        _response, wb = self._template("products")
        text = self._all_text(wb)
        self.assertIn("برند", text)  # this store's brand
        self.assertIn("دسته > زیردسته", text)  # full category path
        self.assertIn("عمومیِ تست", text)
        self.assertIn("فعال", text)
        self.assertIn("پیش‌نویس", text)
        self.assertIn("بله", text)
        self.assertIn("— بدون دسته مالیاتی —", text)
        self.assertNotIn("برندِ بیگانه", text)
        self.assertNotIn("برگِ بیگانه", text)

    def test_inventory_template_lists_warehouses_and_operation_types(self):
        _response, wb = self._template("inventory")
        text = self._all_text(wb)
        self.assertIn(self.warehouse.name, text)
        self.assertIn("تنظیم موجودی نهایی", text)
        self.assertIn("افزایش/کاهش موجودی", text)
        self.assertIn("عددِ منفی از موجودی کم می‌کند", text)  # negative adjustments decrease
        header = [c.value for c in wb["داده‌ها"][1]]
        self.assertEqual(header[0], "انبار *")
        self.assertIn("نوع عملیات *", header)
        self.assertIn("مقدار *", header)

    def test_variant_template_columns(self):
        _response, wb = self._template("variants")
        header = [c.value for c in wb["داده‌ها"][1]]
        self.assertIn("SKU کالا *", header)
        self.assertIn("نام ویژگی ۱", header)
        self.assertIn("مقدار ویژگی ۱", header)
        self.assertIn("تغییر قیمت (تومان)", header)

    def test_dropdown_data_validations_point_at_the_lists_sheet(self):
        _response, wb = self._template("products")
        ws = wb["داده‌ها"]
        validations = ws.data_validations.dataValidation
        lists = [v for v in validations if v.type == "list"]
        self.assertGreaterEqual(len(lists), 5)  # status, brand, category, shipping, tax class
        for validation in lists:
            self.assertIn("'فهرست‌ها'!", validation.formula1)
            self.assertTrue(validation.showErrorMessage)
        covered = {str(rng).split(":")[0][0] for v in lists for rng in v.sqref.ranges}
        self.assertTrue({"D", "E", "F", "K", "L"} <= covered, covered)  # وضعیت، برند، دسته‌بندی، نیاز به ارسال، دسته مالیاتی
        numeric = [v for v in validations if v.type in ("whole", "decimal")]
        self.assertTrue(numeric)
        _r, inv = self._template("inventory")
        inv_lists = [v for v in inv["داده‌ها"].data_validations.dataValidation if v.type == "list"]
        self.assertEqual(len(inv_lists), 2)  # انبار، نوع عملیات

    def test_text_columns_are_formatted_as_text_so_leading_zeros_survive(self):
        _response, wb = self._template("products")
        ws = wb["داده‌ها"]
        self.assertEqual(ws["B2"].number_format, "@")  # SKU
        self.assertEqual(ws["I2"].number_format, "@")  # barcode

    def test_template_download_is_audited(self):
        from apps.core.models import AuditLogEntry

        self._template("products")
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="import.template_downloaded").exists())

    def test_legacy_csv_template_remains_available_via_query_flag(self):
        response = self.client.get(reverse("dashboard:import-template", args=["products"]) + "?format=csv")
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(b"category_code", response.content)

    def test_invalid_template_type_404(self):
        response = self.client.get(reverse("dashboard:import-template", args=["not-a-type"]))
        self.assertEqual(response.status_code, 404)

    def test_template_requires_import_export_permission(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "tpl-content")
        self.assertEqual(self.client.get(reverse("dashboard:import-template", args=["products"])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:import-template", args=["products"])).status_code, 302)


class UploadPageTests(ImportViewTestCase):
    def test_page_guides_the_merchant_without_internal_column_names(self):
        response = self.client.get(reverse("dashboard:import-upload"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for step in ("انتخابِ نوعِ داده", "دانلودِ قالبِ اکسل", "تکمیلِ فایل", "بارگذاریِ فایل",
                     "پیش‌نمایش و بررسیِ خطاها", "تأییدِ اجرایِ واقعی"):
            self.assertIn(step, html)
        for term in INTERNAL_TERMS + ("product_id", "requires_shipping"):
            self.assertNotIn(term, html)
        self.assertNotIn("فایلِ CSV", html)

    def test_mode_cards_use_merchant_language_and_default_to_upsert(self):
        html = self.client.get(reverse("dashboard:import-upload")).content.decode()
        for label in ("افزودن موارد جدید", "فقط بروزرسانی موارد موجود", "افزودن و بروزرسانی"):
            self.assertIn(label, html)
        for old in ("فقط ایجاد", "Upsert"):
            self.assertNotIn(old, html)
        import re

        checked = re.findall(r'name="mode" value="(\w+)"\s*([^>]*)>', html)
        self.assertEqual([v for v, rest in checked if "checked" in rest], ["upsert"])

    def test_page_offers_a_template_link_per_type_and_accepts_xlsx(self):
        response = self.client.get(reverse("dashboard:import-upload"))
        for import_type in ("products", "variants", "inventory"):
            self.assertContains(response, reverse("dashboard:import-template", args=[import_type]))
        self.assertContains(response, 'accept=".xlsx,.csv"')

    def test_type_query_parameter_preselects_the_type(self):
        html = self.client.get(reverse("dashboard:import-upload") + "?type=inventory").content.decode()
        import re

        self.assertRegex(html, r'value="inventory"[^>]*checked')
        self.assertTrue(re.search(r'data-columns-for="inventory"\s*>', html))


class XlsxUploadFlowTests(ImportViewTestCase):
    XLSX_HEADERS = ["SKU", "نام کالا *", "وضعیت", "برند", "دسته‌بندی *", "قیمت (تومان) *", "موجودی"]

    def _post(self, rows, *, mode="create_only", import_type="products", headers=None, name="products.xlsx", **kw):
        return self.client.post(reverse("dashboard:import-upload"), {
            "import_type": import_type, "mode": mode,
            "file": xlsx_upload(headers or self.XLSX_HEADERS, rows, name=name, **kw),
        })

    def _good(self, sku="XU-1"):
        return [sku, "کالای اکسلی", "فعال", "برند", "دسته > زیردسته", "۱۵۰٬۰۰۰", 8]

    def test_upload_preview_execute_xlsx(self):
        response = self._post([self._good()])
        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertFalse(Product.objects.filter(sku="XU-1").exists())

        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertContains(detail, "تأییدِ اجرایِ واقعی")
        self.assertContains(detail, "ساخته می‌شود")
        self.assertContains(detail, "ردیف در اکسل")
        self.assertEqual(detail.context["summary"], {"total": 1, "will_create": 1, "will_update": 0, "invalid": 0, "warnings": 0})

        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        product = Product.objects.get(store=self.store, sku="XU-1")
        self.assertEqual((product.brand, product.category, product.price, product.stock), (self.brand, self.leaf, 150000, 8))

    def test_preview_shows_create_update_invalid_and_warning_counts(self):
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="موجود", slug="existing-ivw", sku="XU-OLD",
            price=Decimal("1"), stock=0,
        )
        rows = [self._good("XU-NEW"), self._good("XU-OLD"), ["XU-BAD", "", "فعال", "برندِ ناموجود", "", "x", ""]]
        self._post(rows, mode="upsert", headers=self.XLSX_HEADERS + ["ستونِ اضافه"])
        job = ImportJob.objects.get(store=self.store)
        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        summary = detail.context["summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["will_create"], 1)
        self.assertEqual(summary["will_update"], 1)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["warnings"], 1)  # the ignored extra column
        self.assertContains(detail, "ردیفِ دارایِ خطا")

    def test_errors_show_excel_row_and_merchant_column_names(self):
        bad = ["XU-BAD", "", "فعال", "برندِ ناموجود", "مسیر > غلط", "abc", ""]
        self._post([self._good(), bad])
        job = ImportJob.objects.get(store=self.store)
        html = self.client.get(reverse("dashboard:import-detail", args=[job.pk])).content.decode()
        self.assertIn(">3<", html.replace("۳", "3"))  # Excel row 3
        for column in ("نام کالا", "برند", "دسته‌بندی", "قیمت"):
            self.assertIn(f'class="imp-col">{column}<', html)
        for term in INTERNAL_TERMS + ("«name»", "«price»", "Traceback", "Exception", "ValueError"):
            self.assertNotIn(term, html)
        only = self.client.get(reverse("dashboard:import-detail", args=[job.pk]) + "?only=problems")
        self.assertEqual([r.row_number for r in only.context["row_results"]], [3])

    def test_source_download_preserves_xlsx_bytes_name_and_type(self):
        content = make_xlsx(self.XLSX_HEADERS, [self._good()])
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": "create_only",
            "file": SimpleUploadedFile("my-products.xlsx", content, content_type=XLSX_MIME),
        })
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual(job.original_filename, "my-products.xlsx")
        self.assertTrue(job.source_file.name.endswith(".xlsx"))
        response = self.client.get(reverse("dashboard:import-download-source", args=[job.pk]))
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        self.assertIn(f"products-source-{job.pk}.xlsx", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), content)

    def test_error_report_is_available_after_preview_and_after_execution(self):
        self._post([self._good(), ["XU-BAD", "", "فعال", "", "", "1", ""]])
        job = ImportJob.objects.get(store=self.store)
        self.assertTrue(job.error_report_file.name.endswith(".xlsx"))
        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertContains(detail, "گزارشِ خطا (اکسل)")
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        report = self.client.get(reverse("dashboard:import-download-errors", args=[job.pk]))
        self.assertEqual(report["Content-Type"], XLSX_MIME)
        ws = open_workbook(b"".join(report.streaming_content))["خطاها"]
        self.assertEqual(ws["A2"].value, 3)
        self.assertEqual(ws["B2"].value, "نامعتبر")

    def test_formula_cells_in_upload_are_rejected_row_wise(self):
        self._post([self._good("OK-1"), self._good("EV-1")[:1] + ["=1+1"] + self._good()[2:]])
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual((job.valid_rows, job.invalid_rows), (1, 1))
        html = self.client.get(reverse("dashboard:import-detail", args=[job.pk])).content.decode()
        self.assertIn("فرمول", html)

    def test_unsupported_and_dangerous_spreadsheets_are_rejected(self):
        content = make_xlsx(self.XLSX_HEADERS, [self._good()])
        cases = {
            "macro.xlsm": SimpleUploadedFile("macro.xlsm", content, content_type="application/vnd.ms-excel.sheet.macroEnabled.12"),
            "old.xls": SimpleUploadedFile("old.xls", b"\xd0\xcf\x11\xe0" + b"0" * 64, content_type="application/vnd.ms-excel"),
            "binary.xlsb": SimpleUploadedFile("binary.xlsb", content),
            "fake.xlsx": SimpleUploadedFile("fake.xlsx", b"this is not a zip", content_type=XLSX_MIME),
            "empty.xlsx": SimpleUploadedFile("empty.xlsx", b"", content_type=XLSX_MIME),
            "evil.exe.xlsx": SimpleUploadedFile("evil.exe.xlsx", b"MZ" + b"0" * 100, content_type=XLSX_MIME),
            "wrong-type.xlsx": SimpleUploadedFile("wrong-type.xlsx", content, content_type="application/x-msdownload"),
        }
        for label, upload in cases.items():
            with self.subTest(label=label):
                response = self.client.post(
                    reverse("dashboard:import-upload"), {"import_type": "products", "mode": "upsert", "file": upload}, follow=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(ImportJob.objects.filter(store=self.store).exists(), label)

    def test_xlsx_with_embedded_macro_project_is_rejected(self):
        import io
        import zipfile

        original = zipfile.ZipFile(io.BytesIO(make_xlsx(self.XLSX_HEADERS, [self._good()])))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as out:
            for item in original.infolist():
                out.writestr(item, original.read(item.filename))
            out.writestr("xl/vbaProject.bin", b"\x00macro")
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": "upsert",
            "file": SimpleUploadedFile("p.xlsx", buffer.getvalue(), content_type=XLSX_MIME),
        }, follow=True)
        self.assertContains(response, "ماکرو")
        self.assertFalse(ImportJob.objects.exists())

    def test_unreadable_xlsx_marks_the_job_failed_instead_of_leaving_it_pending(self):
        response = self._post([["a", "b"]], headers=["ستونِ ناشناس ۱", "ستونِ ناشناس ۲"])
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:import-upload"), response.url)
        job = ImportJob.objects.get(store=self.store)
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertTrue(job.error_summary)

    def test_inventory_xlsx_flow_ignores_job_mode(self):
        warehouse = Warehouse.objects.filter(store=self.store, is_default=True).first()
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.leaf, name="کالای موجودی", slug="inv-ivw", sku="INV-IVW",
            price=Decimal("1000"), stock=0,
        )
        headers = ["انبار *", "SKU کالا", "نوع عملیات *", "مقدار *"]
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "inventory", "mode": "upsert",
            "file": xlsx_upload(headers, [[warehouse.name, "INV-IVW", "تنظیم موجودی نهایی", "۲۵"]], name="inv.xlsx"),
        })
        job = ImportJob.objects.get(store=self.store)
        detail = self.client.get(reverse("dashboard:import-detail", args=[job.pk]))
        self.assertNotContains(detail, "حالت:")
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        product.refresh_from_db()
        self.assertEqual(product.stock, 25)

    def test_import_list_shows_format_and_merchant_mode_names(self):
        self._post([self._good()], mode="update_only")
        html = self.client.get(reverse("dashboard:import-list")).content.decode()
        self.assertIn("فقط بروزرسانی موارد موجود", html)
        self.assertIn("(XLSX)", html)
        self.assertNotIn("Upsert", html)

    def test_other_stores_job_files_are_not_downloadable(self):
        other = Store.objects.create(name="دیگر", slug="ivw-xlsx-other")
        job = import_service.create_import_job(
            other, import_type="products", uploaded_file=xlsx_upload(self.XLSX_HEADERS, [self._good()]),
            mode="upsert", requested_by=None,
        )
        for name in ("import-download-source", "import-download-errors", "import-detail"):
            self.assertEqual(self.client.get(reverse(f"dashboard:{name}", args=[job.pk])).status_code, 404)


class PermissionTests(ImportViewTestCase):
    def test_analyst_can_view_but_not_upload(self):
        self._login_as(StoreMembership.Role.ANALYST, "analyst")
        self.assertEqual(self.client.get(reverse("dashboard:import-list")).status_code, 200)
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 403)

    def test_catalog_manager_can_upload(self):
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "catmgr")
        response = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ImportJob.objects.filter(store=self.store).exists())

    def test_content_editor_cannot_view(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "content")
        self.assertEqual(self.client.get(reverse("dashboard:import-list")).status_code, 403)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:import-list"))
        self.assertEqual(response.status_code, 302)

    def test_csrf_enforced_on_upload(self):
        csrf_client = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        csrf_client.login(username="ivw-owner", password="pass12345")
        response = csrf_client.post(reverse("dashboard:import-upload"), {
            "import_type": ImportJob.ImportType.PRODUCTS, "mode": ImportJob.Mode.CREATE_ONLY,
            "file": _csv(self._valid_product_csv()),
        })
        self.assertEqual(response.status_code, 403)


class TenantIsolationTests(ImportViewTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="ivw-other-store")
        self.other_job = ImportJob.objects.create(
            store=self.other_store, import_type=ImportJob.ImportType.PRODUCTS,
            status=ImportJob.Status.PREVIEW_READY,
        )

    def test_cannot_view_other_stores_job(self):
        response = self.client.get(reverse("dashboard:import-detail", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_execute_other_stores_job(self):
        response = self.client.post(reverse("dashboard:import-execute", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_download_other_stores_source(self):
        response = self.client.get(reverse("dashboard:import-download-source", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_download_other_stores_errors(self):
        response = self.client.get(reverse("dashboard:import-download-errors", args=[self.other_job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_import_list_only_shows_own_store(self):
        response = self.client.get(reverse("dashboard:import-list"))
        jobs = list(response.context["jobs"])
        self.assertTrue(all(j.store_id == self.store.pk for j in jobs))
