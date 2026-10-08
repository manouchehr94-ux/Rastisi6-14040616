"""خلاصه‌ی *واقعیِ* قالب‌های صنف برای نمایشِ مرچنت (کارت/پیش‌نمایشِ آنبوردینگ و ساخت فروشگاه).

همه‌ی اعداد و نام‌ها از رویِ ردیف‌هایِ واقعیِ ``IndustryTemplate*`` ساخته می‌شود؛ هیچ متنِ
بازاریابیِ ثابت یا عددِ ساختگی اینجا نیست. کوئری‌ها دسته‌ای‌اند (به‌ازای کلِ فهرست، نه هر قالب)
و خروجی فقط داده‌ی ساده است تا قالبِ HTML منطقی نداشته باشد.

آنچه نصب *می‌سازد* دقیقاً همان است که ``industry_template_service.install_industry_template``
می‌سازد: دسته‌بندی‌ها، ویژگی‌ها (و مقدارهایشان)، طرحِ ویژگیِ هر دسته و محورهای تنوعِ پیشنهادی.
چیدمانِ پیشنهادیِ صفحه‌ی اصلی (``default_section_keys``) در نصب اعمال **نمی‌شود**؛ بعداً از
سازنده‌ی ویترین به‌صورت پیش‌نویس قابلِ اعمال است — این تفاوت عمداً در خلاصه آمده است.
"""

from collections import defaultdict

from apps.catalog.models import (
    IndustryTemplateAttribute,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)

#: سقفِ نمایشِ نام‌ها در پیش‌نمایش (بقیه فقط به‌صورت «و N مورد دیگر» شمرده می‌شود).
MAX_ROOT_CATEGORIES = 8
MAX_ATTRIBUTE_LABELS = 10
MAX_SECTION_LABELS = 10


def _section_labels(keys) -> list[str]:
    """برچسبِ فارسیِ کلیدهایِ بخشِ پیشنهادی؛ کلیدِ ناشناخته بی‌صدا کنار گذاشته می‌شود."""
    from apps.storefront_builder import section_registry

    labels = []
    for key in keys or []:
        if section_registry.is_valid_section_key(key):
            labels.append(section_registry.get_definition(key).label_fa)
    return labels


def build_template_summaries(templates) -> dict:
    """``{template.pk: summary}`` برایِ فهرستِ داده‌شده — با تعدادِ ثابتی کوئری."""
    templates = list(templates)
    ids = [t.pk for t in templates]
    if not ids:
        return {}

    categories = defaultdict(list)
    for row in IndustryTemplateCategory.objects.filter(industry_template_id__in=ids).order_by(
        "display_order", "pk",
    ).values("industry_template_id", "pk", "parent_id", "name"):
        categories[row["industry_template_id"]].append(row)

    attributes = defaultdict(list)
    for row in IndustryTemplateAttribute.objects.filter(industry_template_id__in=ids).order_by(
        "display_order", "pk",
    ).values("industry_template_id", "label", "is_variant_axis"):
        attributes[row["industry_template_id"]].append(row)

    mapping_counts = defaultdict(int)
    for tid in IndustryTemplateCategoryAttributeMapping.objects.filter(
        template_category__industry_template_id__in=ids,
    ).values_list("template_category__industry_template_id", flat=True):
        mapping_counts[tid] += 1

    recommendation_counts = defaultdict(int)
    for tid in IndustryTemplateRecommendedOption.objects.filter(
        template_category__industry_template_id__in=ids,
    ).values_list("template_category__industry_template_id", flat=True):
        recommendation_counts[tid] += 1

    summaries = {}
    for template in templates:
        rows = categories.get(template.pk, [])
        children_of = defaultdict(int)
        for row in rows:
            if row["parent_id"]:
                children_of[row["parent_id"]] += 1
        roots = [row for row in rows if not row["parent_id"]]
        # «گروه‌هایِ اصلی» برایِ پیش‌نمایش: اگر قالب فقط یک/دو ریشه دارد (مثلاً «پوشاک مردانه»)،
        # نامِ آن ریشه چیزی نمی‌گوید؛ زیرگروه‌هایِ سطحِ دوم مفیدترند.
        root_ids = {row["pk"] for row in roots}
        second_level = [row for row in rows if row["parent_id"] in root_ids]
        highlights = roots if (len(roots) >= 3 or not second_level) else second_level
        attribute_rows = attributes.get(template.pk, [])
        section_labels = _section_labels(template.default_section_keys)
        summaries[template.pk] = {
            "id": template.pk,
            "slug": template.slug,
            "name": template.name,
            "icon": template.icon,
            "sector": template.sector,
            "sector_label": template.get_sector_display(),
            "description": template.description,
            "category_count": len(rows),
            "root_category_count": len(roots),
            "root_categories": [
                {"name": row["name"], "children": children_of.get(row["pk"], 0)}
                for row in highlights[:MAX_ROOT_CATEGORIES]
            ],
            "root_categories_more": max(0, len(highlights) - MAX_ROOT_CATEGORIES),
            "highlight_count": len(highlights),
            "attribute_count": len(attribute_rows),
            "attribute_labels": [row["label"] for row in attribute_rows[:MAX_ATTRIBUTE_LABELS]],
            "attribute_labels_more": max(0, len(attribute_rows) - MAX_ATTRIBUTE_LABELS),
            "variant_axis_labels": [row["label"] for row in attribute_rows if row["is_variant_axis"]],
            "schema_mapping_count": mapping_counts.get(template.pk, 0),
            "recommended_option_count": recommendation_counts.get(template.pk, 0),
            "section_labels": section_labels[:MAX_SECTION_LABELS],
            "section_count": len(section_labels),
            "is_service": template.sector == template.Sector.SERVICES,
        }
    return summaries


def summarize_template(template) -> dict:
    return build_template_summaries([template]).get(template.pk, {})


def attach_summaries(templates) -> list[dict]:
    """فهرستِ خلاصه‌ها به همان ترتیبِ ورودی (برایِ قالبِ HTML)."""
    templates = list(templates)
    summaries = build_template_summaries(templates)
    return [summaries[t.pk] for t in templates]
