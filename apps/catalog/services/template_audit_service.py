"""گزارشِ قطعیِ «کامل‌بودنِ» قالب‌هایِ صنف — برایِ اپراتور/توسعه‌دهنده، نه مرچنت.

هر ردیف از رویِ داده‌یِ *واقعیِ* دیتابیس و همان اعتبارسنجِ ``template_validation_service``
ساخته می‌شود (هیچ منطقِ امتیازدهیِ جدایی اینجا نیست). خروجی مستقل از زمان/ترتیبِ درج و
قطعی است تا بتوان آن را در مخزن ثبت و diff کرد.
"""

from apps.catalog.models import IndustryTemplate
from apps.catalog.services.template_validation_service import validate_industry_template

_SECTOR_ORDER = {value: index for index, (value, _label) in enumerate(IndustryTemplate.Sector.choices)}


def latest_templates():
    """آخرین نسخه‌یِ هر ``slug`` (مستقل از readiness/فعال‌بودن)."""
    latest = {}
    for template in IndustryTemplate.objects.all().order_by("slug", "-version"):
        latest.setdefault(template.slug, template)
    return sorted(latest.values(), key=lambda t: (_SECTOR_ORDER.get(t.sector, 99), t.slug))


def audit_template(template) -> dict:
    result = validate_industry_template(template)
    m = result.metrics
    return {
        "slug": template.slug,
        "version": template.version,
        "name": template.name,
        "sector": template.sector,
        "is_active": template.is_active,
        "stored_readiness": template.readiness,
        # deprecated/archived are operator decisions the validator never overrides
        "recommended_readiness": (
            template.readiness if template.readiness in (
                IndustryTemplate.Readiness.DEPRECATED, IndustryTemplate.Readiness.ARCHIVED,
            ) else result.recommended_readiness
        ),
        "quality_score": result.quality_score,
        "completeness_profile": result.completeness_profile,
        "category_count": m.get("category_count", 0),
        "root_category_count": m.get("root_category_count", 0),
        "max_category_depth": m.get("max_category_depth", 0),
        "attribute_count": m.get("attribute_count", 0),
        "structured_attribute_count": m.get("structured_attribute_count", 0),
        "mapping_count": m.get("mapping_count", 0),
        "required_mapping_count": m.get("required_mapping_count", 0),
        "filterable_mapping_count": m.get("filterable_mapping_count", 0),
        "variant_axis_count": m.get("variant_axis_attribute_count", 0),
        "recommendation_count": m.get("recommendation_count", 0),
        "default_section_count": len(template.default_section_keys or []),
        "errors": [i.code for i in result.errors],
        "warnings": [i.code for i in result.warnings],
        "review_gaps": [i.code for i in result.review_gaps],
        "offerable": template.is_offerable_for_new_installation,
        "needs_enrichment": bool(result.review_gaps) and template.readiness not in (
            IndustryTemplate.Readiness.DEPRECATED, IndustryTemplate.Readiness.ARCHIVED,
        ),
    }


def audit_latest_templates() -> list:
    return [audit_template(t) for t in latest_templates()]


def summarize(rows: list) -> dict:
    """Totals by *stored* readiness and by what the validator recommends (they differ until
    ``seed_industry_templates`` / ``audit_industry_templates --apply`` reconciles)."""
    from collections import Counter

    return {
        "total": len(rows),
        "stored_readiness": dict(sorted(Counter(r["stored_readiness"] for r in rows).items())),
        "recommended_readiness": dict(sorted(Counter(r["recommended_readiness"] for r in rows).items())),
        "offerable_now": sum(1 for r in rows if r["offerable"]),
        "needs_enrichment": sum(1 for r in rows if r["needs_enrichment"]),
        "by_profile": dict(sorted(Counter(r["completeness_profile"] for r in rows).items())),
    }
