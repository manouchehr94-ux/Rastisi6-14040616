"""``template_summary_service`` — the merchant-facing preview is built from real rows only."""

from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.services import template_summary_service as svc


def _template(slug, sector=IndustryTemplate.Sector.RETAIL, **kwargs):
    return IndustryTemplate.objects.create(slug=slug, name=f"قالب {slug}", sector=sector, version=1, **kwargs)


class SummaryTests(TestCase):
    def test_counts_names_and_creations_come_from_the_rows(self):
        t = _template("s-rich", default_section_keys=["announcement_bar", "category_grid", "bogus-key"])
        root_a = IndustryTemplateCategory.objects.create(industry_template=t, code="a", name="الف")
        root_b = IndustryTemplateCategory.objects.create(industry_template=t, code="b", name="ب")
        root_c = IndustryTemplateCategory.objects.create(industry_template=t, code="c", name="ج")
        IndustryTemplateCategory.objects.create(industry_template=t, code="a1", name="الف‌یک", parent=root_a)
        axis = IndustryTemplateAttribute.objects.create(
            industry_template=t, code="size", label="سایز", data_type=Attribute.DataType.SELECT, is_variant_axis=True,
        )
        plain = IndustryTemplateAttribute.objects.create(
            industry_template=t, code="brand", label="برند", data_type=Attribute.DataType.TEXT,
        )
        IndustryTemplateCategoryAttributeMapping.objects.create(template_category=root_a, template_attribute=axis)
        IndustryTemplateCategoryAttributeMapping.objects.create(template_category=root_b, template_attribute=plain)
        IndustryTemplateRecommendedOption.objects.create(template_category=root_a, template_attribute=axis)
        data = svc.summarize_template(t)
        self.assertEqual(data["category_count"], 4)
        self.assertEqual(data["root_category_count"], 3)
        self.assertEqual([c["name"] for c in data["root_categories"]], ["الف", "ب", "ج"])
        self.assertEqual(data["root_categories"][0]["children"], 1)
        self.assertEqual(data["attribute_count"], 2)
        self.assertEqual(data["variant_axis_labels"], ["سایز"])
        self.assertEqual(data["schema_mapping_count"], 2)
        self.assertEqual(data["recommended_option_count"], 1)
        self.assertEqual(data["section_labels"], ["نوار اعلان", "گرید دسته‌بندی"])
        self.assertEqual(data["section_count"], 2)  # the unknown key is dropped, never counted
        self.assertEqual(root_c.name, "ج")

    def test_single_root_templates_surface_second_level_groups(self):
        t = _template("s-single")
        root = IndustryTemplateCategory.objects.create(industry_template=t, code="root", name="ریشه")
        for i in range(3):
            IndustryTemplateCategory.objects.create(industry_template=t, code=f"k{i}", name=f"گروه {i}", parent=root)
        names = [c["name"] for c in svc.summarize_template(t)["root_categories"]]
        self.assertEqual(names, ["گروه 0", "گروه 1", "گروه 2"])

    def test_long_lists_are_capped_with_an_honest_remainder(self):
        t = _template("s-long")
        for i in range(svc.MAX_ROOT_CATEGORIES + 3):
            IndustryTemplateCategory.objects.create(industry_template=t, code=f"c{i}", name=f"دسته {i}")
        for i in range(svc.MAX_ATTRIBUTE_LABELS + 2):
            IndustryTemplateAttribute.objects.create(
                industry_template=t, code=f"a{i}", label=f"ویژگی {i}", data_type=Attribute.DataType.TEXT,
            )
        data = svc.summarize_template(t)
        self.assertEqual(len(data["root_categories"]), svc.MAX_ROOT_CATEGORIES)
        self.assertEqual(data["root_categories_more"], 3)
        self.assertEqual(len(data["attribute_labels"]), svc.MAX_ATTRIBUTE_LABELS)
        self.assertEqual(data["attribute_labels_more"], 2)

    def test_service_and_empty_templates_do_not_crash(self):
        service = _template("s-service", sector=IndustryTemplate.Sector.SERVICES)
        empty = _template("s-empty")
        self.assertTrue(svc.summarize_template(service)["is_service"])
        data = svc.summarize_template(empty)
        self.assertEqual((data["category_count"], data["attribute_count"], data["section_count"]), (0, 0, 0))

    def test_query_count_is_constant_in_the_number_of_templates(self):
        templates = [_template(f"q{i}") for i in range(12)]
        with self.assertNumQueries(4):
            svc.attach_summaries(templates)
        with self.assertNumQueries(0):
            svc.attach_summaries([])
