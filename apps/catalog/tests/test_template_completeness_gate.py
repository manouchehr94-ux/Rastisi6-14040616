"""دروازه‌ی «کامل‌بودن برایِ مرچنت» — اعتبارِ ساختاری به‌تنهایی PRODUCTION_READY نیست."""

import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    Category,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
    StoreIndustryInstallation,
)
from apps.catalog.services import industry_catalog_service, template_audit_service
from apps.catalog.services.industry_template_service import (
    IndustryInstallationError,
    install_industry_template,
)
from apps.catalog.services.template_validation_service import (
    validate_and_persist,
    validate_industry_template,
)
from apps.stores.models import Store

Sector = IndustryTemplate.Sector
Readiness = IndustryTemplate.Readiness


def skeletal_template(slug="skeletal", sector=Sector.RETAIL):
    """الگوی اسکلتیِ رایجِ کاتالوگ: یک دسته‌بندی + چند فیلدِ متنیِ عمومی + ۳ نگاشت."""
    template = IndustryTemplate.objects.create(
        slug=slug, name="اسکلتی", description="توضیح", sector=sector, version=1,
    )
    category = IndustryTemplateCategory.objects.create(industry_template=template, code="all", name="همه محصولات")
    for code, label in (("brand", "برند"), ("model", "مدل"), ("origin", "کشور سازنده")):
        attribute = IndustryTemplateAttribute.objects.create(
            industry_template=template, code=code, label=label, data_type=Attribute.DataType.TEXT,
        )
        IndustryTemplateCategoryAttributeMapping.objects.create(
            template_category=category, template_attribute=attribute, group="عمومی", is_filterable=True,
        )
    return template


def rich_template(slug="rich-retail", sector=Sector.RETAIL, with_variant_axis=True):
    template = IndustryTemplate.objects.create(
        slug=slug, name="غنی", description="توضیح", sector=sector, version=1,
    )
    root = IndustryTemplateCategory.objects.create(industry_template=template, code="root", name="پوشاک")
    leaves = [
        IndustryTemplateCategory.objects.create(
            industry_template=template, code=f"leaf-{i}", name=f"زیردسته {i}", parent=root,
        )
        for i in range(4)
    ]
    size = IndustryTemplateAttribute.objects.create(
        industry_template=template, code="size", label="سایز", data_type=Attribute.DataType.SELECT,
        is_variant_axis=with_variant_axis,
    )
    for label in ("S", "M", "L"):
        IndustryTemplateAttributeValue.objects.create(template_attribute=size, label=label)
    attributes = [size]
    for code, label in (("material", "جنس"), ("brand", "برند"), ("season", "فصل"), ("origin", "کشور سازنده")):
        attributes.append(IndustryTemplateAttribute.objects.create(
            industry_template=template, code=code, label=label, data_type=Attribute.DataType.TEXT,
        ))
    for category in leaves:
        for attribute in attributes[:3]:
            IndustryTemplateCategoryAttributeMapping.objects.create(
                template_category=category, template_attribute=attribute, group="مشخصات", is_filterable=True,
            )
    if with_variant_axis:
        IndustryTemplateRecommendedOption.objects.create(template_category=leaves[0], template_attribute=size)
    return template


def service_template(slug="svc", categories=4):
    template = IndustryTemplate.objects.create(
        slug=slug, name="خدمات", description="توضیح", sector=Sector.SERVICES, version=1,
    )
    for i in range(categories):
        IndustryTemplateCategory.objects.create(industry_template=template, code=f"s{i}", name=f"خدمت {i}")
    return template


def gap_codes(template):
    return [gap.code for gap in validate_industry_template(template).review_gaps]


class CompletenessGateTests(TestCase):
    def test_skeletal_product_template_is_structurally_valid_but_not_production_ready(self):
        template = skeletal_template()
        result = validate_industry_template(template)
        self.assertTrue(result.is_valid)
        self.assertFalse(result.is_merchant_complete)
        self.assertEqual(result.recommended_readiness, Readiness.REVIEW_REQUIRED)
        self.assertIn("COMPLETENESS_TOO_FEW_CATEGORIES", gap_codes(template))
        self.assertLessEqual(result.quality_score, 69)
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, Readiness.REVIEW_REQUIRED)
        self.assertFalse(template.is_offerable_for_new_installation)

    def test_rich_retail_template_is_production_ready(self):
        template = rich_template()
        result = validate_industry_template(template)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.review_gaps, [])
        self.assertEqual(result.recommended_readiness, Readiness.PRODUCTION_READY)
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, Readiness.PRODUCTION_READY)
        self.assertTrue(template.is_offerable_for_new_installation)

    def test_retail_without_variant_recommendation_is_held_back(self):
        template = rich_template(slug="no-variants", with_variant_axis=False)
        self.assertIn("COMPLETENESS_NO_VARIANT_RECOMMENDATION", gap_codes(template))
        self.assertEqual(validate_industry_template(template).recommended_readiness, Readiness.REVIEW_REQUIRED)

    def test_variant_recommendation_only_required_for_retail_sector(self):
        template = rich_template(slug="food-rich", sector=Sector.FOOD, with_variant_axis=False)
        self.assertNotIn("COMPLETENESS_NO_VARIANT_RECOMMENDATION", gap_codes(template))
        self.assertEqual(validate_industry_template(template).recommended_readiness, Readiness.PRODUCTION_READY)

    def test_text_only_attributes_do_not_qualify_as_structured(self):
        template = rich_template(slug="text-only")
        IndustryTemplateAttributeValue.objects.filter(template_attribute__industry_template=template).delete()
        self.assertIn("COMPLETENESS_NO_STRUCTURED_ATTRIBUTE", gap_codes(template))

    def test_service_template_uses_service_criteria(self):
        ok = service_template("svc-ok", categories=4)
        result = validate_industry_template(ok)
        self.assertEqual(result.completeness_profile, "service")
        self.assertEqual(result.recommended_readiness, Readiness.PRODUCTION_READY)
        # خدمات به ویژگی/نگاشت/محورِ تنوع نیاز ندارد
        self.assertEqual(ok.attributes.count(), 0)
        thin = service_template("svc-thin", categories=1)
        self.assertEqual(gap_codes(thin), ["COMPLETENESS_SERVICE_TOO_FEW_CATEGORIES"])
        self.assertEqual(validate_industry_template(thin).recommended_readiness, Readiness.REVIEW_REQUIRED)

    def test_other_sector_is_deliberately_generic_and_production_ready(self):
        template = IndustryTemplate.objects.create(
            slug="other-x", name="سایر", description="عمومی", sector=Sector.OTHER, version=1,
        )
        IndustryTemplateCategory.objects.create(industry_template=template, code="general", name="عمومی")
        result = validate_industry_template(template)
        self.assertEqual(result.completeness_profile, "free_form")
        self.assertEqual(result.review_gaps, [])
        self.assertEqual(result.recommended_readiness, Readiness.PRODUCTION_READY)

    def test_structural_errors_outrank_quality_gaps(self):
        template = IndustryTemplate.objects.create(slug="empty-x", name="خالی", sector=Sector.RETAIL, version=1)
        result = validate_industry_template(template)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.recommended_readiness, Readiness.VALIDATION_FAILED)

    def test_persisted_result_records_completeness_gaps(self):
        template = skeletal_template("persist-gaps")
        validate_and_persist(template)
        stored = template.validation_result
        completeness = stored.metrics["completeness"]
        self.assertEqual(completeness["profile"], "product")
        self.assertFalse(completeness["merchant_complete"])
        self.assertIn("COMPLETENESS_TOO_FEW_CATEGORIES", [g["code"] for g in completeness["gaps"]])

    def test_deprecated_readiness_is_never_overridden(self):
        template = skeletal_template("old-one")
        IndustryTemplate.objects.filter(pk=template.pk).update(readiness=Readiness.DEPRECATED, is_active=False)
        template.refresh_from_db()
        validate_and_persist(template)
        template.refresh_from_db()
        self.assertEqual(template.readiness, Readiness.DEPRECATED)


class OfferingAndInstallationTests(TestCase):
    def setUp(self):
        self.ready = rich_template("offer-ready")
        self.held = skeletal_template("offer-held")
        validate_and_persist(self.ready)
        validate_and_persist(self.held)
        self.ready.refresh_from_db()
        self.held.refresh_from_db()

    def test_review_required_templates_are_not_offerable(self):
        slugs = [t.slug for t in industry_catalog_service.offerable_industry_templates()]
        self.assertIn("offer-ready", slugs)
        self.assertNotIn("offer-held", slugs)

    def test_installing_a_review_required_template_is_refused(self):
        store = Store.objects.create(name="فروشگاه", slug="gate-store", status=Store.Status.ACTIVE)
        with self.assertRaises(IndustryInstallationError):
            install_industry_template(store, self.held)
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=store).exists())
        self.assertEqual(Category.objects.filter(store=store).count(), 0)

    def test_existing_installation_survives_a_readiness_downgrade(self):
        store = Store.objects.create(name="فروشگاه", slug="gate-keep", status=Store.Status.ACTIVE)
        install_industry_template(store, self.ready)
        before = sorted(Category.objects.filter(store=store).values_list("name", flat=True))
        self.assertTrue(before)
        # صنف بعداً به REVIEW_REQUIRED برمی‌گردد (مثلاً معیارِ سخت‌گیرانه‌تر شده)
        IndustryTemplate.objects.filter(pk=self.ready.pk).update(readiness=Readiness.REVIEW_REQUIRED)
        validate_and_persist(IndustryTemplate.objects.get(pk=self.ready.pk), strict=True)
        installation = StoreIndustryInstallation.objects.get(store=store)
        self.assertEqual(installation.status, StoreIndustryInstallation.Status.COMPLETED)
        self.assertEqual(sorted(Category.objects.filter(store=store).values_list("name", flat=True)), before)


class AuditServiceAndCommandTests(TestCase):
    def setUp(self):
        rich_template("aud-rich")
        skeletal_template("aud-skel")
        service_template("aud-svc", categories=1)

    def test_audit_rows_have_all_required_fields_and_recommendations(self):
        rows = {row["slug"]: row for row in template_audit_service.audit_latest_templates()}
        self.assertEqual(set(rows), {"aud-rich", "aud-skel", "aud-svc"})
        for field in (
            "slug", "name", "sector", "stored_readiness", "recommended_readiness", "quality_score",
            "category_count", "root_category_count", "max_category_depth", "attribute_count", "mapping_count",
            "required_mapping_count", "filterable_mapping_count", "variant_axis_count", "recommendation_count",
            "default_section_count", "warnings", "errors", "review_gaps", "offerable", "needs_enrichment",
        ):
            self.assertIn(field, rows["aud-rich"], field)
        self.assertEqual(rows["aud-rich"]["recommended_readiness"], Readiness.PRODUCTION_READY)
        self.assertEqual(rows["aud-skel"]["recommended_readiness"], Readiness.REVIEW_REQUIRED)
        self.assertEqual(rows["aud-svc"]["recommended_readiness"], Readiness.REVIEW_REQUIRED)

    def test_audit_output_is_deterministic(self):
        def run(fmt):
            out = StringIO()
            call_command("audit_industry_templates", format=fmt, stdout=out)
            return out.getvalue()

        self.assertEqual(run("json"), run("json"))
        self.assertEqual(run("markdown"), run("markdown"))
        payload = json.loads(run("json"))
        self.assertEqual(payload["summary"]["total"], 3)

    def test_audit_without_apply_changes_nothing(self):
        call_command("audit_industry_templates", format="json", stdout=StringIO())
        self.assertFalse(IndustryTemplate.objects.filter(readiness=Readiness.REVIEW_REQUIRED).exists())

    def test_apply_converges_readiness_and_is_idempotent(self):
        IndustryTemplate.objects.update(readiness=Readiness.PRODUCTION_READY)
        call_command("audit_industry_templates", apply=True, format="json", stdout=StringIO())
        state = dict(IndustryTemplate.objects.values_list("slug", "readiness"))
        self.assertEqual(state["aud-rich"], Readiness.PRODUCTION_READY)
        self.assertEqual(state["aud-skel"], Readiness.REVIEW_REQUIRED)
        self.assertEqual(state["aud-svc"], Readiness.REVIEW_REQUIRED)
        call_command("audit_industry_templates", apply=True, format="json", stdout=StringIO())
        self.assertEqual(dict(IndustryTemplate.objects.values_list("slug", "readiness")), state)

    def test_apply_never_touches_existing_store_installations(self):
        ready = IndustryTemplate.objects.get(slug="aud-skel")
        IndustryTemplate.objects.filter(pk=ready.pk).update(readiness=Readiness.PRODUCTION_READY)
        ready.refresh_from_db()
        store = Store.objects.create(name="ف", slug="apply-keep", status=Store.Status.ACTIVE)
        install_industry_template(store, ready)
        categories = Category.objects.filter(store=store).count()
        call_command("audit_industry_templates", apply=True, format="json", stdout=StringIO())
        ready.refresh_from_db()
        self.assertEqual(ready.readiness, Readiness.REVIEW_REQUIRED)
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=store).exists())
        self.assertEqual(Category.objects.filter(store=store).count(), categories)
