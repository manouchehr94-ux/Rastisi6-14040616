"""چارچوب کیفیتِ قالب صنف: اعتبارسنجی ساختاری/معنایی و اثرانگشت محتوا.

نگاه کنید به ADR-26 (چارچوب کیفیت) و ADR-27 (نسخه‌بندی/اثرانگشت) در
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md``.

این ماژول تنها منبعِ منطق «قالب خوب چیست» است — توسط دستور مدیریتی
``validate_industry_templates``، پنل ادمین، دستور seed، و تست‌ها به‌طور
یکسان فراخوانی می‌شود؛ هیچ منطق اعتبارسنجی نباید در View یا Command
تکرار شود.
"""

import hashlib
import json
from dataclasses import dataclass, field

from apps.catalog.models import Attribute, IndustryTemplate

VALIDATOR_VERSION = "2"  # 2: sector-aware merchant-completeness gate (REVIEW_REQUIRED)

# وزن هر بُعد در امتیاز کیفیت — نگاه کنید به ADR-26. جمع = 100.
QUALITY_SCORE_WEIGHTS = {
    "structure": 25,
    "attribute_completeness": 20,
    "schema_quality": 20,
    "variant_recommendations": 15,
    "merchant_usefulness": 10,
    "installability": 10,
}

#: نگاشت پیشوند کدِ یافته به بُعدِ امتیازدهی — برای کسر امتیاز هشدارها.
_CODE_DIMENSION = {
    "IDENTITY": "structure",
    "CATEGORY": "structure",
    "ATTRIBUTE": "attribute_completeness",
    "SCHEMA": "schema_quality",
    "RECOMMENDATION": "variant_recommendations",
    "USEFULNESS": "merchant_usefulness",
    "COMPLETENESS": "merchant_usefulness",
    "INSTALL": "installability",
}

_WARNING_PENALTY = 5
#: یک قالبِ دارایِ خلأِ تکمیل هرگز امتیازِ «خوب» نمی‌گیرد (سقفِ امتیاز) — تا عددِ بالا
#: پشتِ یک اسکلتِ ناقص پنهان نشود.
_COMPLETENESS_SCORE_CAP = 69

# ---------------------------------------------------------------------------
# معیارهای «کامل‌بودن برای مرچنت» — سخت‌گیریِ وابسته به رسته (sector-aware)
#
# تفاوتِ سه لایه (نگاه کنید به ADR-26 و addendum «Completeness gate»):
#   1. خطای ساختاری (error)      → VALIDATION_FAILED: قالب اصلاً نصب‌شدنی نیست.
#   2. خلأِ تکمیل (review gap)   → REVIEW_REQUIRED : ساختار معتبر است ولی برای یک
#                                   مرچنتِ واقعی ناقص/اسکلتی است؛ پیشنهادِ نصبِ جدید نمی‌شود.
#   3. هشدار (warning)           → هرگز آمادگی را تغییر نمی‌دهد (مگر strict).
# فقط قالبی که هیچ خطا و هیچ خلأِ تکمیلی ندارد PRODUCTION_READY می‌شود.
#
# پروفایل‌ها:
#   product   — رسته‌هایِ کالا (retail/digital/food/home/beauty/sport/culture/auto/industry)
#   service   — رسته‌یِ خدمات (کاتالوگِ «کالا» ندارد؛ ویژگی‌هایِ کالایی لازم نیست)
#   free_form — «سایر (صنف آزاد)»: عمداً عمومی و بدونِ ویژگی؛ استثنایِ صریح، نه امتیازدهی
#               به‌عنوانِ یک قالبِ خرده‌فروشیِ غنی.
# ---------------------------------------------------------------------------
PRODUCT_SECTORS = frozenset({
    IndustryTemplate.Sector.RETAIL, IndustryTemplate.Sector.DIGITAL, IndustryTemplate.Sector.FOOD,
    IndustryTemplate.Sector.HOME, IndustryTemplate.Sector.BEAUTY, IndustryTemplate.Sector.SPORT,
    IndustryTemplate.Sector.CULTURE, IndustryTemplate.Sector.AUTO, IndustryTemplate.Sector.INDUSTRY,
})
#: رسته‌هایی که محورِ تنوعِ پیشنهادی (سایز/رنگ…) برایشان طبیعی و لازم است.
VARIANT_REQUIRED_SECTORS = frozenset({IndustryTemplate.Sector.RETAIL})

PRODUCT_MIN_CATEGORIES = 4
PRODUCT_MIN_ATTRIBUTES = 5
PRODUCT_MIN_MAPPINGS = 8
PRODUCT_MIN_MAPPED_LEAF_SHARE = 0.5      # دست‌کم نیمی از دسته‌هایِ برگ ویژگی داشته باشند
PRODUCT_MIN_MAPPED_CATEGORIES = 2
PRODUCT_MIN_STRUCTURED_ATTRIBUTES = 1    # دست‌کم یک ویژگیِ انتخابیِ دارایِ ≥۲ مقدار (نه فقط متنِ آزاد)
SERVICE_MIN_CATEGORIES = 3               # دست‌کم سه نوعِ خدمت

PROFILE_PRODUCT = "product"
PROFILE_SERVICE = "service"
PROFILE_FREE_FORM = "free_form"
_MAX_REASONABLE_DEPTH = 4
_MAX_REASONABLE_REQUIRED_PER_CATEGORY = 6


@dataclass
class ValidationIssue:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    model_type: str
    identifier: str
    remediation: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code, "severity": self.severity, "message": self.message,
            "model_type": self.model_type, "identifier": self.identifier, "remediation": self.remediation,
        }


@dataclass
class TemplateValidationResult:
    template: IndustryTemplate
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    quality_score: int = 0
    duration_ms: int = 0
    #: خلأهایِ «کامل‌بودن برایِ مرچنت» (severity="review") — ساختار معتبر ولی محتوا ناقص.
    review_gaps: list = field(default_factory=list)
    completeness_profile: str = PROFILE_PRODUCT

    @property
    def is_valid(self) -> bool:
        """اعتبارِ *ساختاری* — خلأِ تکمیل آن را نامعتبر نمی‌کند (نصبِ موجود معتبر می‌ماند)."""
        return not self.errors

    @property
    def is_merchant_complete(self) -> bool:
        return not self.review_gaps

    @property
    def recommended_readiness(self) -> str:
        if self.errors:
            return IndustryTemplate.Readiness.VALIDATION_FAILED
        if self.review_gaps:
            return IndustryTemplate.Readiness.REVIEW_REQUIRED
        return IndustryTemplate.Readiness.PRODUCTION_READY

    def as_dict(self) -> dict:
        return {
            "template": {"slug": self.template.slug, "version": self.template.version, "name": self.template.name},
            "is_valid": self.is_valid,
            "recommended_readiness": self.recommended_readiness,
            "quality_score": self.quality_score,
            "metrics": self.metrics,
            "errors": [i.as_dict() for i in self.errors],
            "review_gaps": [i.as_dict() for i in self.review_gaps],
            "completeness_profile": self.completeness_profile,
            "warnings": [i.as_dict() for i in self.warnings],
            "infos": [i.as_dict() for i in self.infos],
            "duration_ms": self.duration_ms,
        }


def _issue_dimension(code: str) -> str:
    prefix = code.split("_", 1)[0]
    return _CODE_DIMENSION.get(prefix, "structure")


def _category_tree(template: IndustryTemplate):
    return list(template.categories.select_related("parent").order_by("display_order", "code"))


def _detect_cycle(categories) -> list:
    """کدهای دسته‌بندی‌های درگیر در یک زنجیره‌ی حلقه‌ای (اگر باشد) را برمی‌گرداند."""
    by_id = {c.pk: c for c in categories}
    for category in categories:
        seen = set()
        current = category
        while current.parent_id:
            if current.parent_id in seen or current.parent_id == category.pk:
                return [by_id[cid].code for cid in seen if cid in by_id] + [category.code]
            seen.add(current.pk)
            current = by_id.get(current.parent_id)
            if current is None:
                break
    return []


def _category_depth(category, by_id, _seen=None) -> int:
    _seen = _seen or set()
    if category.pk in _seen or not category.parent_id:
        return 1
    _seen.add(category.pk)
    parent = by_id.get(category.parent_id)
    if parent is None:
        return 1
    return 1 + _category_depth(parent, by_id, _seen)


def completeness_profile_for(sector: str) -> str:
    """پروفایلِ معیارِ کامل‌بودن به‌ازایِ رسته — نگاه کنید به بالایِ همین ماژول."""
    if sector == IndustryTemplate.Sector.SERVICES:
        return PROFILE_SERVICE
    if sector == IndustryTemplate.Sector.OTHER:
        return PROFILE_FREE_FORM
    return PROFILE_PRODUCT


def evaluate_completeness_gaps(template: IndustryTemplate, metrics: dict, *, profile: str) -> list:
    """خلأهایِ «کامل‌بودن برایِ مرچنت» را (فقط از رویِ metrics) برمی‌گرداند.

    تابعِ خالص و قطعی است؛ ``free_form`` («سایر») عمداً هیچ خلأیی ندارد — آن قالب
    باید عمومی باشد و با معیارِ یک قالبِ غنیِ خرده‌فروشی سنجیده نمی‌شود."""
    gaps: list[ValidationIssue] = []

    def gap(code, message, remediation):
        gaps.append(ValidationIssue(
            code=code, severity="review", message=message, model_type="IndustryTemplate",
            identifier=template.slug, remediation=remediation,
        ))

    if profile == PROFILE_FREE_FORM:
        return gaps

    if profile == PROFILE_SERVICE:
        if metrics["category_count"] < SERVICE_MIN_CATEGORIES:
            gap("COMPLETENESS_SERVICE_TOO_FEW_CATEGORIES",
                f"قالبِ خدماتی فقط {metrics['category_count']} دسته‌ی خدمت دارد (حداقل {SERVICE_MIN_CATEGORIES} نوعِ خدمت لازم است).",
                "انواعِ اصلیِ خدماتِ این صنف را به‌عنوانِ دسته‌بندی اضافه کنید.")
        return gaps

    if metrics["category_count"] < PRODUCT_MIN_CATEGORIES:
        gap("COMPLETENESS_TOO_FEW_CATEGORIES",
            f"فقط {metrics['category_count']} دسته‌بندی (حداقل {PRODUCT_MIN_CATEGORIES} لازم است) — اسکلتِ تک‌دسته‌ای برایِ فروشگاهِ واقعی کافی نیست.",
            "درختِ دسته‌بندیِ واقعیِ این صنف را بنویسید.")
    if metrics["attribute_count"] < PRODUCT_MIN_ATTRIBUTES:
        gap("COMPLETENESS_TOO_FEW_ATTRIBUTES",
            f"فقط {metrics['attribute_count']} ویژگی (حداقل {PRODUCT_MIN_ATTRIBUTES} لازم است).",
            "ویژگی‌هایِ توصیفیِ مهمِ این صنف را اضافه کنید.")
    if metrics["mapping_count"] < PRODUCT_MIN_MAPPINGS:
        gap("COMPLETENESS_TOO_FEW_MAPPINGS",
            f"فقط {metrics['mapping_count']} نگاشتِ ویژگی به دسته (حداقل {PRODUCT_MIN_MAPPINGS} لازم است).",
            "ویژگی‌ها را به دسته‌هایِ مرتبط نگاشت کنید.")
    leaf_count = metrics.get("leaf_category_count", 0)
    mapped_leaf = metrics.get("mapped_leaf_category_count", 0)  # شاملِ پوششِ ارثی
    if (
        metrics.get("mapped_category_count", 0) < PRODUCT_MIN_MAPPED_CATEGORIES
        or (leaf_count and mapped_leaf / leaf_count < PRODUCT_MIN_MAPPED_LEAF_SHARE)
    ):
        gap("COMPLETENESS_LOW_SCHEMA_COVERAGE",
            f"فقط {mapped_leaf} از {leaf_count} دسته‌ی برگ (با احتسابِ ارثِ والد) طرحِ ویژگی دارد (حداقل نیمی از دسته‌هایِ برگ و ۲ دسته‌یِ نگاشت‌شده لازم است).",
            "برایِ دسته‌هایِ اصلی طرحِ ویژگی تعریف کنید.")
    if metrics.get("structured_attribute_count", 0) < PRODUCT_MIN_STRUCTURED_ATTRIBUTES:
        gap("COMPLETENESS_NO_STRUCTURED_ATTRIBUTE",
            "هیچ ویژگیِ انتخابی (با حداقل ۲ مقدار) وجود ندارد؛ فقط فیلدهایِ متنِ آزاد است.",
            "برایِ ویژگی‌هایِ رایج (جنس، نوع، …) مقدارهایِ استاندارد تعریف کنید.")
    # عمداً: نبودِ نگاشتِ «قابل‌فیلتر» فقط هشدارِ USEFULNESS_NO_FILTERABLE است، نه خلأِ تکمیل —
    # قالبی که دسته/ویژگی/نگاشتِ غنی دارد نباید به‌خاطرِ یک پرچمِ ثانویه از پیشنهاد حذف شود.
    if template.sector in VARIANT_REQUIRED_SECTORS and metrics["recommendation_count"] < 1:
        gap("COMPLETENESS_NO_VARIANT_RECOMMENDATION",
            "این رسته معمولاً محورِ تنوع (مثل سایز/رنگ) دارد اما هیچ محورِ پیشنهادی تعریف نشده است.",
            "محورهایِ تنوعِ پیشنهادیِ هر دسته را تعریف کنید.")
    return gaps


def validate_industry_template(template: IndustryTemplate) -> TemplateValidationResult:
    """اعتبارسنجی کامل ساختاری/معنایی یک قالب صنف — نگاه کنید به ADR-26."""
    import time

    started = time.monotonic()
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    infos: list[ValidationIssue] = []

    def add(bucket, code, message, model_type, identifier, remediation=""):
        bucket.append(ValidationIssue(code=code, severity=bucket_name[id(bucket)], message=message,
                                       model_type=model_type, identifier=identifier, remediation=remediation))

    bucket_name = {id(errors): "error", id(warnings): "warning", id(infos): "info"}

    # --- 6.1 هویت ---
    if not template.name.strip():
        add(errors, "IDENTITY_NAME_EMPTY", "نام صنف نمی‌تواند خالی باشد.", "IndustryTemplate", template.slug)
    if not template.slug.strip():
        add(errors, "IDENTITY_SLUG_EMPTY", "اسلاگ صنف نمی‌تواند خالی باشد.", "IndustryTemplate", str(template.pk))
    if not template.description.strip():
        add(warnings, "IDENTITY_DESCRIPTION_EMPTY", "توضیحات صنف خالی است.", "IndustryTemplate", template.slug,
            "یک توضیح کوتاه و کاربردی برای مرچنت اضافه کنید.")
    if not template.locale.strip():
        add(warnings, "IDENTITY_LOCALE_EMPTY", "زبان قالب مشخص نشده است.", "IndustryTemplate", template.slug)

    # --- 6.2 دسته‌بندی ---
    categories = _category_tree(template)
    by_id = {c.pk: c for c in categories}
    root_categories = [c for c in categories if c.parent_id is None]
    metrics = {
        "category_count": len(categories), "root_category_count": len(root_categories),
        "max_category_depth": max((_category_depth(c, by_id) for c in categories), default=0),
    }

    if not categories:
        add(errors, "CATEGORY_NONE", "قالب هیچ دسته‌بندی‌ای ندارد.", "IndustryTemplate", template.slug,
            "حداقل یک دسته‌بندی ریشه اضافه کنید.")
    elif not root_categories:
        add(errors, "CATEGORY_NO_ROOT", "هیچ دسته‌بندی ریشه‌ای وجود ندارد.", "IndustryTemplate", template.slug)

    cycle_codes = _detect_cycle(categories)
    if cycle_codes:
        add(errors, "CATEGORY_CIRCULAR_HIERARCHY", f"سلسله‌مراتب دسته‌بندی حلقه‌ای است: {', '.join(cycle_codes)}",
            "IndustryTemplateCategory", ",".join(cycle_codes), "زنجیره‌ی والد را اصلاح کنید.")

    for category in categories:
        if category.parent_id and category.parent_id not in by_id:
            add(errors, "CATEGORY_ORPHAN", f"دسته‌بندی «{category.code}» به والدی خارج از این قالب اشاره می‌کند.",
                "IndustryTemplateCategory", category.code)
        depth = _category_depth(category, by_id)
        if depth > _MAX_REASONABLE_DEPTH:
            add(warnings, "CATEGORY_DEPTH_EXCESSIVE",
                f"عمق دسته‌بندی «{category.code}» ({depth}) از حد معقول ({_MAX_REASONABLE_DEPTH}) بیشتر است.",
                "IndustryTemplateCategory", category.code)

    siblings_by_parent: dict = {}
    for category in categories:
        siblings_by_parent.setdefault(category.parent_id, []).append(category)
    for parent_id, siblings in siblings_by_parent.items():
        seen_names: dict[str, str] = {}
        for sibling in siblings:
            key = sibling.name.strip().lower()
            if key in seen_names:
                add(warnings, "CATEGORY_DUPLICATE_SIBLING_NAME",
                    f"دو دسته‌بندی هم‌سطح با نام مشابه «{sibling.name}» ({seen_names[key]}، {sibling.code}).",
                    "IndustryTemplateCategory", sibling.code)
            seen_names[key] = sibling.code

    # --- 6.3 ویژگی ---
    attributes = list(template.attributes.prefetch_related("values").order_by("display_order", "code"))
    metrics["attribute_count"] = len(attributes)
    value_count = 0
    choice_attribute_count = 0
    variant_axis_attribute_count = 0

    if not attributes:
        add(warnings, "ATTRIBUTE_NONE", "قالب هیچ ویژگی‌ای ندارد.", "IndustryTemplate", template.slug)

    for attribute in attributes:
        if not attribute.label.strip() or len(attribute.label.strip()) < 2:
            add(errors, "ATTRIBUTE_LABEL_INVALID", f"عنوان ویژگی «{attribute.code}» نامعتبر/خیلی کوتاه است.",
                "IndustryTemplateAttribute", attribute.code)
        values = list(attribute.values.all())
        value_count += len(values)
        is_choice = attribute.data_type in Attribute.CHOICE_DATA_TYPES
        if is_choice:
            choice_attribute_count += 1
            if not values:
                add(errors, "ATTRIBUTE_CHOICE_NO_VALUES",
                    f"ویژگیِ انتخابی «{attribute.code}» هیچ مقداری ندارد.", "IndustryTemplateAttribute",
                    attribute.code, "حداقل یک مقدار برای این ویژگی اضافه کنید.")
            if attribute.data_type == Attribute.DataType.COLOR:
                for value in values:
                    if not value.color_hex:
                        add(warnings, "ATTRIBUTE_COLOR_VALUE_NO_HEX",
                            f"مقدار رنگ «{value.label}» در «{attribute.code}» کد Hex ندارد.",
                            "IndustryTemplateAttributeValue", f"{attribute.code}:{value.label}")
        if attribute.is_variant_axis:
            variant_axis_attribute_count += 1

    metrics["value_count"] = value_count
    metrics["choice_attribute_count"] = choice_attribute_count
    metrics["variant_axis_attribute_count"] = variant_axis_attribute_count

    # --- 6.4 طرح ویژگیِ دسته‌بندی ---
    from apps.catalog.models import IndustryTemplateCategoryAttributeMapping, IndustryTemplateRecommendedOption

    mappings = list(
        IndustryTemplateCategoryAttributeMapping.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute").prefetch_related("template_attribute__values")
    )
    metrics["mapping_count"] = len(mappings)
    metrics["required_mapping_count"] = sum(1 for m in mappings if m.is_required)
    metrics["filterable_mapping_count"] = sum(1 for m in mappings if m.is_filterable)

    required_by_category: dict = {}
    for mapping in mappings:
        if mapping.is_required:
            attr = mapping.template_attribute
            if attr.data_type in Attribute.CHOICE_DATA_TYPES and attr.values.count() == 0:
                add(errors, "SCHEMA_REQUIRED_UNOBTAINABLE",
                    f"ویژگیِ الزامیِ «{attr.code}» روی «{mapping.template_category.code}» هیچ مقدار قابل‌انتخابی ندارد.",
                    "IndustryTemplateCategoryAttributeMapping",
                    f"{mapping.template_category.code}:{attr.code}")
            required_by_category.setdefault(mapping.template_category.code, 0)
            required_by_category[mapping.template_category.code] += 1

    for category_code, count in required_by_category.items():
        if count > _MAX_REASONABLE_REQUIRED_PER_CATEGORY:
            add(warnings, "SCHEMA_TOO_MANY_REQUIRED",
                f"دسته‌بندی «{category_code}» {count} ویژگیِ الزامی دارد — احتمالاً بیش‌ازحد است.",
                "IndustryTemplateCategory", category_code)

    leaf_categories = [c for c in categories if c.pk not in {p for p in siblings_by_parent if p}]
    mapped_category_codes = {m.template_category.code for m in mappings}
    for leaf in leaf_categories:
        if leaf.code not in mapped_category_codes:
            add(warnings, "SCHEMA_LEAF_CATEGORY_EMPTY",
                f"دسته‌بندی برگ «{leaf.code}» هیچ نگاشت ویژگی‌ای ندارد.", "IndustryTemplateCategory", leaf.code,
                "برای این دسته‌بندی حداقل چند ویژگی توصیفی نگاشت کنید.")

    # --- 6.5 محورهای تنوع پیشنهادی ---
    recommendations = list(
        IndustryTemplateRecommendedOption.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute").prefetch_related("template_attribute__values")
    )
    metrics["recommendation_count"] = len(recommendations)
    for rec in recommendations:
        value_count_for_axis = rec.template_attribute.values.count()
        if value_count_for_axis < 2:
            add(warnings, "RECOMMENDATION_TOO_FEW_VALUES",
                f"محور پیشنهادی «{rec.template_attribute.code}» روی «{rec.template_category.code}» "
                f"کمتر از ۲ مقدار دارد — تنوع معناداری نمی‌سازد.",
                "IndustryTemplateRecommendedOption", f"{rec.template_category.code}:{rec.template_attribute.code}")

    # --- 6.6 کاربردی‌بودن برای مرچنت ---
    if metrics["category_count"] < 2:
        add(warnings, "USEFULNESS_TOO_FEW_CATEGORIES", "قالب کمتر از ۲ دسته‌بندی دارد.", "IndustryTemplate",
            template.slug)
    if metrics["attribute_count"] < 3:
        add(warnings, "USEFULNESS_TOO_FEW_ATTRIBUTES", "قالب کمتر از ۳ ویژگی دارد.", "IndustryTemplate",
            template.slug)
    if mappings and metrics["filterable_mapping_count"] == 0:
        add(warnings, "USEFULNESS_NO_FILTERABLE", "هیچ‌کدام از نگاشت‌های ویژگی «قابل فیلتر» نیستند.",
            "IndustryTemplate", template.slug)

    # --- 6.6b کامل‌بودن برای مرچنت (sector-aware) ---
    # طرحِ ویژگی به زیرشاخه‌ها ارث می‌رسد (category_schema_service) — پس یک دسته‌یِ برگ «پوشش‌داده‌شده»
    # است اگر خودش یا یکی از اجدادش نگاشت داشته باشد.
    def _covered(category) -> bool:
        seen = set()
        current = category
        while current is not None and current.pk not in seen:
            if current.code in mapped_category_codes:
                return True
            seen.add(current.pk)
            current = by_id.get(current.parent_id) if current.parent_id else None
        return False

    mapped_leaf_codes = {c.code for c in leaf_categories if _covered(c)}
    structured_attribute_count = sum(
        1 for a in attributes
        if a.data_type in Attribute.CHOICE_DATA_TYPES and len(list(a.values.all())) >= 2
    )
    metrics["leaf_category_count"] = len(leaf_categories)
    metrics["mapped_category_count"] = len(mapped_category_codes)
    metrics["mapped_leaf_category_count"] = len(mapped_leaf_codes)
    metrics["structured_attribute_count"] = structured_attribute_count
    profile = completeness_profile_for(template.sector)
    gaps = evaluate_completeness_gaps(template, metrics, profile=profile)

    # --- 6.7 قابلیت نصب ---
    installable = bool(categories) and bool(root_categories) and not cycle_codes
    if not installable:
        add(errors, "INSTALL_STRUCTURE_INVALID", "ساختار دسته‌بندی برای نصب نامعتبر است.", "IndustryTemplate",
            template.slug)
    metrics["installable"] = installable

    # --- امتیاز کیفیت ---
    dimension_scores = dict(QUALITY_SCORE_WEIGHTS)
    for issue in warnings:
        dim = _issue_dimension(issue.code)
        dimension_scores[dim] = max(0, dimension_scores.get(dim, 0) - _WARNING_PENALTY)
    quality_score = sum(dimension_scores.values())
    if gaps:
        dimension_scores["merchant_usefulness"] = 0
        quality_score = min(sum(dimension_scores.values()), _COMPLETENESS_SCORE_CAP)
    if errors:
        quality_score = min(quality_score, 40)  # خطای بحرانی هرگز پشت امتیاز بالا پنهان نمی‌شود

    duration_ms = int((time.monotonic() - started) * 1000)

    return TemplateValidationResult(
        template=template, errors=errors, warnings=warnings, infos=infos, metrics=metrics,
        quality_score=quality_score, duration_ms=duration_ms,
        review_gaps=gaps, completeness_profile=profile,
    )


def _canonical_template_payload(template: IndustryTemplate) -> dict:
    """ساختار قطعیِ محتوای قالب — مستقل از PK/زمان درج، برای اثرانگشت."""
    categories = template.categories.select_related("parent").order_by("code")
    attributes = template.attributes.prefetch_related("values").order_by("code")

    from apps.catalog.models import IndustryTemplateCategoryAttributeMapping, IndustryTemplateRecommendedOption

    mappings = (
        IndustryTemplateCategoryAttributeMapping.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute")
        .order_by("template_category__code", "template_attribute__code")
    )
    recommendations = (
        IndustryTemplateRecommendedOption.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute")
        .order_by("template_category__code", "template_attribute__code")
    )

    return {
        "slug": template.slug,
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "locale": template.locale,
        "categories": [
            {
                "code": c.code, "name": c.name, "icon": c.icon,
                "parent_code": c.parent.code if c.parent_id else None, "display_order": c.display_order,
            }
            for c in categories
        ],
        "attributes": [
            {
                "code": a.code, "label": a.label, "data_type": a.data_type, "display_type": a.display_type,
                "unit": a.unit, "is_variant_axis": a.is_variant_axis, "display_order": a.display_order,
                "values": sorted(
                    [
                        {"label": v.label, "value": v.value, "color_hex": v.color_hex,
                         "display_order": v.display_order}
                        for v in a.values.all()
                    ],
                    key=lambda v: v["label"],
                ),
            }
            for a in attributes
        ],
        "mappings": [
            {
                "category_code": m.template_category.code, "attribute_code": m.template_attribute.code,
                "group": m.group, "group_order": m.group_order, "display_order": m.display_order,
                "is_required": m.is_required, "is_filterable": m.is_filterable, "is_comparable": m.is_comparable,
                "is_searchable": m.is_searchable, "help_text": m.help_text, "placeholder": m.placeholder,
            }
            for m in mappings
        ],
        "recommendations": [
            {
                "category_code": r.template_category.code, "attribute_code": r.template_attribute.code,
                "display_order": r.display_order,
            }
            for r in recommendations
        ],
    }


def compute_template_fingerprint(template: IndustryTemplate) -> str:
    """اثرانگشت SHA-256 قطعی محتوای قالب — مستقل از PK/ترتیب درج/زمان — نگاه کنید به ADR-27."""
    payload = _canonical_template_payload(template)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_READINESS_AUTO_MANAGED = {
    IndustryTemplate.Readiness.DRAFT,
    IndustryTemplate.Readiness.VALIDATION_FAILED,
    IndustryTemplate.Readiness.REVIEW_REQUIRED,
    IndustryTemplate.Readiness.PRODUCTION_READY,
}


def validate_and_persist(template: IndustryTemplate, *, strict: bool = False) -> TemplateValidationResult:
    """اعتبارسنجی را اجرا، اثرانگشت را ذخیره، نتیجه را کش، و آمادگی را به‌روزرسانی می‌کند.

    فقط حالت‌های خودکار‌مدیریت‌شونده‌ی آمادگی (draft/validation_failed/
    review_required/production_ready) را دست‌کاری می‌کند — یک قالبِ
    ``deprecated``/``archived`` هرگز با این تابع به‌طور خودکار به
    ``production_ready`` برنمی‌گردد (باید عملیات صریح اپراتور باشد)."""
    from apps.catalog.models import IndustryTemplateValidationResult

    result = validate_industry_template(template)
    fingerprint = compute_template_fingerprint(template)

    IndustryTemplate.objects.filter(pk=template.pk).update(content_fingerprint=fingerprint)
    template.content_fingerprint = fingerprint

    IndustryTemplateValidationResult.objects.update_or_create(
        industry_template=template,
        defaults={
            "fingerprint": fingerprint, "validator_version": VALIDATOR_VERSION,
            "status": IndustryTemplateValidationResult.Status.VALID if result.is_valid
            else IndustryTemplateValidationResult.Status.INVALID,
            "quality_score": result.quality_score,
            "errors": [i.as_dict() for i in result.errors],
            "warnings": [i.as_dict() for i in result.warnings],
            "infos": [i.as_dict() for i in result.infos],
            # بدونِ تغییرِ اسکیما: خلأهایِ تکمیل کنارِ metrics نگه‌داری می‌شوند.
            "metrics": {
                **result.metrics,
                "completeness": {
                    "profile": result.completeness_profile,
                    "merchant_complete": result.is_merchant_complete,
                    "gaps": [i.as_dict() for i in result.review_gaps],
                },
            },
            "duration_ms": result.duration_ms,
        },
    )

    if template.readiness in _READINESS_AUTO_MANAGED:
        if result.errors:
            new_readiness = IndustryTemplate.Readiness.VALIDATION_FAILED
        elif result.review_gaps or (strict and result.warnings):
            # ساختارِ معتبر ولی برایِ مرچنتِ واقعی ناقص (یا --strict و هشدار): پیشنهادِ نصبِ جدید نمی‌شود.
            # نصب‌هایِ موجود دست‌نخورده می‌مانند (deep copy مستقل از readiness).
            new_readiness = IndustryTemplate.Readiness.REVIEW_REQUIRED
        else:
            new_readiness = IndustryTemplate.Readiness.PRODUCTION_READY
        if new_readiness != template.readiness:
            IndustryTemplate.objects.filter(pk=template.pk).update(readiness=new_readiness)
            template.readiness = new_readiness

    return result


def latest_production_version(slug: str) -> IndustryTemplate | None:
    """جدیدترین نسخه‌ی «آماده‌ی تولید» و فعالِ یک خانواده‌ی صنف را برمی‌گرداند — نگاه کنید به ADR-27."""
    return (
        IndustryTemplate.objects.filter(
            slug=slug, is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        .order_by("-version")
        .first()
    )
