"""Admin Experience Upgrade — Part 5: advanced Excel import with an approval queue for new reference values.

One engine (``import_xlsx`` / ``import_service``) - these tests drive it through the real views:

* a name that is not in the store (brand / main category / subcategory / attribute / attribute value) becomes a PROPOSAL, never a record;
* the file cannot run until every proposal is decided; approving creates exactly the real record (reusing an equivalent one);
* rejecting creates nothing and leaves the dependent rows as correctable errors;
* re-importing the same file never duplicates;
* names that differ only by ZWNJ / spaces / Arabic letter shapes / case / slug are the SAME entity;
* approval needs the permission of that entity, belongs to the job's store only, is audited and idempotent."""

from decimal import Decimal
from unittest import mock

from django.urls import reverse

from apps.catalog.models import (
    Attribute, AttributeValue, Brand, Category, Product, ProductAttributeValue, Specification,
)
from apps.core.models import AuditLogEntry, ImportJob, ImportProposal
from apps.dashboard.services import import_proposals
from apps.dashboard.tests.test_import_views import ImportViewTestCase
from apps.dashboard.tests.xlsx_helpers import xlsx_upload
from apps.stores.authorization import IMPORT_EXPORT_MANAGE, IMPORT_EXPORT_VIEW, ROLE_PERMISSIONS
from apps.stores.models import Store, StoreMembership

HEADERS = ["نام کالا", "دسته‌بندی", "زیردسته‌بندی", "قیمت (تومان)", "SKU", "برند", "موجودی", "مشخصات فنی", "ویژگی‌ها"]


def row(name, sku, *, category="دسته", sub="زیردسته", price="100000", brand="", stock="5", specs="", attrs=""):
    return [name, category, sub, price, sku, brand, stock, specs, attrs]


class EntityKeyTests(ImportViewTestCase):
    def test_persian_spacing_letter_shape_case_and_invisible_marks_are_one_entity(self):
        same = ["می‌شود", "می شود", "میشود", "ميشود", "می‌شود", "‏می‌شود‎", "می  شود "]
        self.assertEqual({import_proposals.entity_key(v) for v in same}, {import_proposals.entity_key("میشود")})
        self.assertEqual(import_proposals.entity_key("Nike"), import_proposals.entity_key(" NIKE "))
        self.assertEqual(import_proposals.entity_key("کتاب‌ها"), import_proposals.entity_key("كتابها"))
        self.assertEqual(import_proposals.entity_key("ﻛﻮﺷﻲ"), import_proposals.entity_key("کوشی"))   # presentation forms
        self.assertEqual(import_proposals.entity_key("برند۱"), import_proposals.entity_key("برند1"))     # Persian digits
        self.assertNotEqual(import_proposals.entity_key("آب"), import_proposals.entity_key("اب"))       # different letters stay different


class ProposalFlowBase(ImportViewTestCase):
    def upload(self, rows, *, mode="upsert", headers=HEADERS, name="products.xlsx"):
        self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": mode, "file": xlsx_upload(headers, rows, name=name),
        })
        return ImportJob.objects.filter(store=self.store).latest("pk")

    def detail(self, job, **extra):
        return self.client.get(reverse("dashboard:import-detail", args=[job.pk]), extra)

    def decide(self, job, proposal, action, **data):
        return self.client.post(reverse("dashboard:import-proposal-decide", args=[job.pk, proposal.pk, action]), data)

    def approve_all(self, job):
        return self.client.post(reverse("dashboard:import-proposals-approve-all", args=[job.pk]))

    def execute(self, job):
        self.client.post(reverse("dashboard:import-execute", args=[job.pk]))
        job.refresh_from_db()
        return job

    def brands(self):
        return Brand.objects.filter(store=self.store)


class FiveNewBrandsScenario(ProposalFlowBase):
    NAMES = ["آلفا", "بتا", "گاما", "دلتا", "امگا"]

    def _file(self):
        return [row(f"کالا {i}", f"NB-{i}", brand=name) for i, name in enumerate(self.NAMES, start=1)]

    def test_five_new_brands_wait_for_approval_then_create_exactly_five_and_a_reimport_adds_none(self):
        before = self.brands().count()
        job = self.upload(self._file())
        self.assertEqual(job.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(self.brands().count(), before)                                    # the preview created nothing
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="NB-").count(), 0)
        queue = list(ImportProposal.objects.filter(job=job))
        self.assertEqual(sorted(p.name for p in queue), sorted(self.NAMES))
        self.assertTrue(all(p.status == "pending" and p.kind == "brand" and p.requested_by_id == self.owner.pk for p in queue))
        self.assertTrue(all(p.source_filename == "products.xlsx" and len(p.source_rows) == 1 for p in queue))

        page = self.detail(job)
        summary = page.context["summary"]
        self.assertEqual((summary["awaiting"], summary["invalid"], summary["will_create"]), (5, 0, 0))
        self.assertContains(page, "مواردِ جدیدِ پیشنهادی")
        self.assertContains(page, "منتظرِ تأییدِ مورد جدید")

        blocked = self.execute(job)                                                        # a direct POST cannot run an unresolved file
        self.assertEqual(blocked.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual((self.brands().count(), Product.objects.filter(sku__startswith="NB-").count()), (before, 0))

        self.approve_all(job)
        self.assertEqual(self.brands().count(), before + 5)                                # exactly the five
        self.assertEqual(sorted(self.brands().exclude(pk=self.brand.pk).values_list("name", flat=True)), sorted(self.NAMES))
        job.refresh_from_db()
        summary = self.detail(job).context["summary"]
        self.assertEqual((summary["awaiting"], summary["invalid"], summary["will_create"], summary["blockers"]), (0, 0, 5, []))

        done = self.execute(job)
        self.assertEqual(done.status, ImportJob.Status.COMPLETED)
        products = Product.objects.filter(store=self.store, sku__startswith="NB-")
        self.assertEqual(products.count(), 5)
        self.assertEqual({p.brand.name for p in products}, set(self.NAMES))
        self.assertContains(self.detail(done), reverse("dashboard:product-list"))        # the final report links to the product list

        again = self.upload(self._file())                                                  # re-import of the very same file
        self.assertEqual(ImportProposal.objects.filter(job=again).count(), 0)
        self.assertEqual(self.detail(again).context["summary"]["awaiting"], 0)
        self.execute(again)
        self.assertEqual(self.brands().count(), before + 5)                                # still exactly five
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="NB-").count(), 5)

    def test_rejected_names_are_never_created_or_linked(self):
        before = self.brands().count()
        rows = self._file()
        job = self.upload(rows)
        for proposal in ImportProposal.objects.filter(job=job):
            self.decide(job, proposal, "reject", note="نام نامناسب")
        self.assertEqual(self.brands().count(), before)
        job.refresh_from_db()
        page = self.detail(job)
        summary = page.context["summary"]
        self.assertEqual((summary["awaiting"], summary["invalid"]), (0, 5))               # now correctable errors, not «waiting»
        self.assertContains(page, "رد شد؛ نام را اصلاح کنید")
        self.assertTrue(all(p.status == "rejected" and p.decided_by_id == self.owner.pk and p.decision_note for p in ImportProposal.objects.filter(job=job)))
        blocked = self.execute(job)
        self.assertEqual(blocked.status, ImportJob.Status.PREVIEW_READY)
        self.assertEqual(Product.objects.filter(store=self.store, sku__startswith="NB-").count(), 0)
        # correcting the file (no brand) and uploading again works - the rejected names stay out of the store
        fixed = self.upload([row(f"کالا {i}", f"NB-{i}") for i in range(1, 6)])
        self.assertEqual(self.execute(fixed).status, ImportJob.Status.COMPLETED)
        self.assertEqual(self.brands().count(), before)
        self.assertEqual(Product.objects.filter(store=self.store, brand__isnull=False, sku__startswith="NB-").count(), 0)

    def test_the_same_new_name_in_many_rows_and_shapes_is_one_proposal(self):
        rows = [row("الف", "SH-1", brand="نوین تک"), row("ب", "SH-2", brand="نوین‌تک"), row("پ", "SH-3", brand="نوینتک"), row("ت", "SH-4", brand="NOVIN")]
        job = self.upload(rows)
        queue = ImportProposal.objects.filter(job=job)
        self.assertEqual(queue.count(), 2)
        spaced = queue.get(name_key=import_proposals.entity_key("نوین تک"))
        self.assertEqual(spaced.source_rows, [2, 3, 4])
        self.approve_all(job)
        self.assertEqual(self.brands().count(), 1 + 2)
        self.assertEqual(self.execute(job).status, ImportJob.Status.COMPLETED)
        self.assertEqual(Product.objects.get(sku="SH-1").brand_id, Product.objects.get(sku="SH-3").brand_id)

    def test_names_equal_to_an_existing_brand_are_reused_not_proposed(self):
        Brand.objects.create(store=self.store, name="نوین‌تک", slug="novin-tek", name_en="Novin Tech")
        rows = [row("الف", "EQ-1", brand="نوین تک"), row("ب", "EQ-2", brand="نوینتک"), row("پ", "EQ-3", brand="NOVIN TECH"), row("ت", "EQ-4", brand="novin-tek"), row("ث", "EQ-5", brand="ﻧﻮﻳﻦ‌ﺗﮏ")]
        job = self.upload(rows)
        self.assertEqual(ImportProposal.objects.filter(job=job).count(), 0)
        self.assertEqual(self.execute(job).status, ImportJob.Status.COMPLETED)
        self.assertEqual(self.brands().filter(name__icontains="نوین").count(), 1)
        self.assertEqual({p.brand.slug for p in Product.objects.filter(sku__startswith="EQ-")}, {"novin-tek"})


class CategoryAndAttributeProposalTests(ProposalFlowBase):
    def test_new_main_category_and_subcategory_become_two_proposals_and_land_in_the_tree(self):
        before = Category.objects.filter(store=self.store).count()
        job = self.upload([row("تیشرت", "CT-1", category="پوشاک تازه", sub="مردانه تازه"), row("پیراهن", "CT-2", category="پوشاک تازه", sub="مردانه تازه")])
        kinds = sorted(ImportProposal.objects.filter(job=job).values_list("kind", flat=True))
        self.assertEqual(kinds, ["category", "subcategory"])
        sub = ImportProposal.objects.get(job=job, kind="subcategory")
        self.assertEqual((sub.parent_name, sub.source_rows), ("پوشاک تازه", [2, 3]))
        self.assertEqual(Category.objects.filter(store=self.store).count(), before)
        self.approve_all(job)
        self.assertEqual(Category.objects.filter(store=self.store).count(), before + 2)
        leaf = Category.objects.get(store=self.store, name="مردانه تازه")
        self.assertEqual(leaf.parent.name, "پوشاک تازه")
        self.assertEqual(self.execute(job).status, ImportJob.Status.COMPLETED)
        self.assertEqual({p.category_id for p in Product.objects.filter(sku__startswith="CT-")}, {leaf.pk})

    def test_full_path_in_one_column_and_an_existing_main_category_only_propose_the_missing_part(self):
        job = self.upload([row("الف", "CP-1", category="دسته > زیردسته جدید", sub=""), row("ب", "CP-2", category="  دسته  ", sub="زیردسته‌یِ دیگر")])
        queue = {(p.kind, p.name, p.parent_name) for p in ImportProposal.objects.filter(job=job)}
        self.assertEqual(queue, {("subcategory", "زیردسته جدید", "دسته"), ("subcategory", "زیردسته‌یِ دیگر", "دسته")})
        # approving a subcategory whose main category is itself new approves the parent first, once
        job2 = self.upload([row("پ", "CP-3", category="ریشه نو", sub="فرزند نو")])
        child = ImportProposal.objects.get(job=job2, kind="subcategory")
        self.decide(job2, child, "approve")
        self.assertEqual(Category.objects.filter(store=self.store, name="ریشه نو").count(), 1)
        self.assertEqual(Category.objects.get(store=self.store, name="فرزند نو").parent.name, "ریشه نو")
        self.assertEqual(ImportProposal.objects.get(job=job2, kind="category").status, "approved")

    def test_a_bare_main_category_or_a_three_level_new_path_is_a_correctable_error(self):
        job = self.upload([row("الف", "CE-1", category="دسته", sub=""), row("ب", "CE-2", category="الف > ب > ج", sub="")])
        self.assertEqual(ImportProposal.objects.filter(job=job).count(), 0)
        page = self.detail(job)
        self.assertEqual(page.context["summary"]["invalid"], 2)
        self.assertContains(page, "یک دسته‌یِ اصلی است؛ کالا باید در یک زیردسته باشد")
        self.assertContains(page, "فقط تا دو سطح")

    def test_attributes_values_and_specifications(self):
        color = Attribute.objects.create(store=self.store, code="color", label="رنگ", data_type=Attribute.DataType.SELECT, display_type="dropdown")
        red = AttributeValue.objects.create(attribute=color, label="قرمز", value="قرمز", normalized_label="قرمز")
        job = self.upload([
            row("الف", "AT-1", specs="جنس: پنبه؛ وزن: ۲۵۰ گرم", attrs="رنگ: قرمز؛ مدل: کلاسیک"),
            row("ب", "AT-2", attrs="رنگ: سبز"),
        ])
        queue = {(p.kind, p.name, p.parent_name) for p in ImportProposal.objects.filter(job=job)}
        self.assertEqual(queue, {("attribute", "مدل", ""), ("attribute_value", "سبز", "رنگ")})
        self.approve_all(job)
        self.assertEqual(Attribute.objects.get(store=self.store, label="مدل").data_type, Attribute.DataType.TEXT)
        self.assertTrue(AttributeValue.objects.filter(attribute=color, label="سبز").exists())
        self.assertEqual(self.execute(job).status, ImportJob.Status.COMPLETED)
        first, second = Product.objects.get(sku="AT-1"), Product.objects.get(sku="AT-2")
        self.assertEqual(ProductAttributeValue.objects.get(product=first, attribute=color).value_id, red.pk)
        self.assertEqual(ProductAttributeValue.objects.get(product=first, attribute__label="مدل").text_value, "کلاسیک")
        self.assertEqual(ProductAttributeValue.objects.get(product=second, attribute=color).value.label, "سبز")
        self.assertEqual({(s.label, s.value) for s in Specification.objects.filter(product=first)}, {("جنس", "پنبه"), ("وزن", "250 گرم")})
        # a later import updates a spec of the same title instead of adding a second one, and removes nothing
        again = self.upload([row("الف", "AT-1", price="", category="", sub="", specs="جنس: نخ")])
        self.assertEqual(self.execute(again).status, ImportJob.Status.COMPLETED)
        self.assertEqual({(s.label, s.value) for s in Specification.objects.filter(product=first)}, {("جنس", "نخ"), ("وزن", "250 گرم")})

    def test_malformed_cells_are_row_errors_and_formula_cells_are_rejected(self):
        job = self.upload([row("الف", "ME-1", specs="بدون دو نقطه"), row("ب", "ME-2", attrs="رنگ")])
        self.assertEqual(self.detail(job).context["summary"]["invalid"], 2)
        formula = self.client.post(reverse("dashboard:import-upload"), {
            "import_type": "products", "mode": "upsert",
            "file": xlsx_upload(HEADERS, [row("ج", "ME-3", brand="=1+1")], cell_types={(2, 6): "f"}),
        })
        fjob = ImportJob.objects.filter(store=self.store).latest("pk")
        self.assertEqual(ImportProposal.objects.filter(job=fjob).count(), 0)           # a formula never becomes a proposed name
        self.assertEqual(self.detail(fjob).context["summary"]["invalid"], 1)


class PermissionIsolationAndAuditTests(ProposalFlowBase):
    def test_each_kind_needs_its_own_permission_and_a_viewer_cannot_decide(self):
        job = self.upload([row("الف", "PM-1", brand="برند تازه")])
        proposal = ImportProposal.objects.get(job=job)
        # an order manager that was also given import rights still lacks brand.manage
        grant = ROLE_PERMISSIONS[StoreMembership.Role.ORDER_MANAGER] | {IMPORT_EXPORT_VIEW, IMPORT_EXPORT_MANAGE}
        with mock.patch.dict(ROLE_PERMISSIONS, {StoreMembership.Role.ORDER_MANAGER: grant}):
            self._login_as(StoreMembership.Role.ORDER_MANAGER, "om")
            self.assertEqual(self.decide(job, proposal, "approve").status_code, 403)
            self.assertEqual(self.approve_all(job).status_code, 302)
            page = self.detail(job)
            self.assertContains(page, "مجوزِ تأیید ندارید")
        proposal.refresh_from_db()
        self.assertEqual((proposal.status, self.brands().count()), ("pending", 1))
        self._login_as(StoreMembership.Role.ANALYST, "an")                              # view-only role
        self.assertEqual(self.decide(job, proposal, "approve").status_code, 403)
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "ce")
        self.assertEqual(self.decide(job, proposal, "approve").status_code, 403)
        self._login_as(StoreMembership.Role.CATALOG_MANAGER, "cm")                       # owns catalog + import
        self.assertEqual(self.decide(job, proposal, "approve").status_code, 302)
        proposal.refresh_from_db()
        self.assertEqual((proposal.status, proposal.decided_by.username), ("approved", "ivw-cm"))

    def test_another_store_can_neither_see_nor_decide_and_nothing_leaks(self):
        job = self.upload([row("الف", "IS-1", brand="برند خصوصی")])
        proposal = ImportProposal.objects.get(job=job)
        other = Store.objects.create(name="دیگر", slug="proposal-other-store", status=Store.Status.ACTIVE, admin_subdomain="import-other")
        stranger = self.make_user_for(other)
        from django.test import Client

        foreign = Client(HTTP_HOST="import-other.rastisi.localhost")
        foreign.force_login(stranger)
        with self.settings(ALLOWED_HOSTS=["import-other.rastisi.localhost", "testserver"]):
            self.assertEqual(foreign.post(reverse("dashboard:import-proposal-decide", args=[job.pk, proposal.pk, "approve"])).status_code, 404)
            self.assertEqual(foreign.post(reverse("dashboard:import-proposals-approve-all", args=[job.pk])).status_code, 404)
            self.assertEqual(foreign.get(reverse("dashboard:import-detail", args=[job.pk])).status_code, 404)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")
        self.assertFalse(Brand.objects.filter(store=other).exists())
        self.client.post(reverse("dashboard:import-proposal-decide", args=[job.pk, proposal.pk, "approve"]))
        self.assertFalse(Brand.objects.filter(store=other).exists())                      # approved in the job's store only
        self.assertTrue(Brand.objects.filter(store=self.store, name="برند خصوصی").exists())

    def make_user_for(self, store):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        user = get_user_model().objects.create_user(username=f"stranger-{store.pk}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=store, user=user, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        return user

    def test_decisions_are_audited_and_idempotent(self):
        job = self.upload([row("الف", "AU-1", brand="برند ممیزی")])
        proposal = ImportProposal.objects.get(job=job)
        self.decide(job, proposal, "approve")
        self.decide(job, proposal, "approve")                                             # double click / replay
        self.assertEqual(Brand.objects.filter(store=self.store, name="برند ممیزی").count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(store=self.store, action_code="import.proposal_approved").count(), 1)
        self.assertEqual(self.decide(job, proposal, "reject").status_code, 302)           # a decided proposal cannot flip
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "approved")
        job2 = self.upload([row("ب", "AU-2", brand="برند ردشده")])
        self.decide(job2, ImportProposal.objects.get(job=job2), "reject", note="x")
        entry = AuditLogEntry.objects.get(store=self.store, action_code="import.proposal_rejected")
        self.assertEqual(entry.actor_id, self.owner.pk)

    def test_concurrent_approval_of_the_same_name_from_two_files_creates_one_record(self):
        first = self.upload([row("الف", "CC-1", brand="هم‌نام")])
        second = self.upload([row("ب", "CC-2", brand="هم نام")])
        self.decide(first, ImportProposal.objects.get(job=first), "approve")
        self.decide(second, ImportProposal.objects.get(job=second), "approve")
        self.assertEqual(Brand.objects.filter(store=self.store, name__in=["هم‌نام", "هم نام"]).count(), 1)

    def test_the_store_list_and_upload_flow_entry_points(self):
        listing = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(listing, "ورود گروهی کالاها")
        self.assertContains(listing, reverse("dashboard:import-upload") + "?type=products")
        upload = self.client.get(reverse("dashboard:import-upload") + "?type=products")
        self.assertContains(upload, reverse("dashboard:import-template", args=["products"]))
        self._login_as(StoreMembership.Role.ANALYST, "an2")
        self.assertNotContains(self.client.get(reverse("dashboard:product-list")), "ورود گروهی کالاها")

    def test_a_store_specific_template_lists_its_own_references_only(self):
        from apps.dashboard.services import import_xlsx
        from apps.dashboard.tests.xlsx_helpers import open_workbook

        other = Store.objects.create(name="دیگر", slug="template-other-store", status=Store.Status.ACTIVE)
        Brand.objects.create(store=other, name="برندِ فروشگاهِ دیگر", slug="other-only")
        wb = open_workbook(import_xlsx.build_template_xlsx("products", self.store))
        listed = {c.value for row_ in wb["فهرست‌ها"].iter_rows() for c in row_ if c.value}
        self.assertIn("برند", listed)
        self.assertNotIn("برندِ فروشگاهِ دیگر", listed)
        self.assertEqual(wb.sheetnames, ["داده‌ها", "راهنما", "فهرست‌ها", "نمونه"])
        guide = " ".join(str(c.value) for r in wb["راهنما"].iter_rows() for c in r if c.value)
        for phrase in ("کالایِ تازه", "بروزرسانیِ کالایِ موجود", "پیشنهاد", "مشخصاتِ فنی و ویژگی‌ها"):
            self.assertIn(phrase, guide)
