"""نصب یک قالب صنف پلتفرم روی یک Store — deep copy، اتمیک، حداکثر یک نصب در طول عمر Store.

ADR-22 (استراتژی کپی) و ADR-25 (نسخه‌بندی و سیاست تغییر صنف) را در
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`` نگاه کنید.
"""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Category,
    CategoryAttributeSchema,
    CategoryRecommendedOption,
    IndustryTemplate,
    StoreIndustryInstallation,
)
from apps.core.utils import normalization_key


class IndustryInstallationError(Exception):
    """خطای قابل‌نمایش هنگام نصب قالب صنف."""


@dataclass
class InstallationResult:
    installation: StoreIndustryInstallation
    categories_created: list = field(default_factory=list)
    attributes_created: list = field(default_factory=list)


def can_install_industry_template(store) -> None:
    """اگر Store قبلاً یک قالب صنف نصب کرده باشد، خطای قابل‌نمایش می‌دهد (نگاه کنید به ADR-25)."""
    if StoreIndustryInstallation.objects.filter(store=store).exists():
        raise IndustryInstallationError(
            "این فروشگاه قبلاً یک قالب صنف نصب کرده است؛ در این نسخه هر فروشگاه فقط یک بار "
            "می‌تواند قالب صنف نصب کند."
        )


OTHER_INDUSTRY_SLUG = "other"
CUSTOM_INDUSTRY_NAME_MAX_LENGTH = 80
CUSTOM_INDUSTRY_NAME_MIN_LENGTH = 2
CUSTOM_INDUSTRY_NAME_REQUIRED_MESSAGE = "برای «سایر (صنف آزاد)» نامِ صنفِ خودتان را بنویسید؛ مثلاً «لوازم‌التحریرِ هنری»."
CUSTOM_INDUSTRY_NAME_TOO_SHORT_MESSAGE = "نامِ صنف باید دست‌کم ۲ نویسه باشد."
CUSTOM_INDUSTRY_NAME_TOO_LONG_MESSAGE = f"نامِ صنف حداکثر {CUSTOM_INDUSTRY_NAME_MAX_LENGTH} نویسه می‌تواند باشد."
CUSTOM_INDUSTRY_NAME_INVALID_MESSAGE = "نامِ صنف فقط می‌تواند شاملِ حروف، عدد و نشانه‌هایِ معمولیِ نگارشی باشد."


def is_other_industry(industry_template) -> bool:
    return getattr(industry_template, "slug", "") == OTHER_INDUSTRY_SLUG


def validate_custom_industry_name(raw) -> str:
    """نامِ آزادِ صنف را پاکسازی و اعتبارسنجی می‌کند و مقدارِ نرمال‌شده را برمی‌گرداند (وگرنه ``IndustryInstallationError``).

    * فاصله‌هایِ اضافه (از جمله نیم‌فاصله‌یِ تکراری/کنترل‌ها) فشرده می‌شود؛ ي/ك عربی به ی/ک فارسی تبدیل می‌شود؛
    * طول ۲..۸۰؛ نویسه‌هایِ کنترلی/نشانه‌گذاری (``<``، ``>`` و …) رد می‌شود (نام در قالب‌ها escape می‌شود، این دفاعِ دوم است)؛
    * فقط حرف/عدد (هر زبان) و فاصله و «‌ - _ . , ، & ( ) /» پذیرفته می‌شود.
    """
    import re
    import unicodedata

    text = unicodedata.normalize("NFKC", str(raw or "")).replace("ي", "ی").replace("ك", "ک")
    if any(unicodedata.category(ch) in {"Cc", "Cs", "Co"} for ch in text.replace("\u200c", "").replace("\t", " ")):
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_INVALID_MESSAGE)
    text = re.sub(r"\u200c+", "\u200c", re.sub(r"\s+", " ", text)).strip(" \u200c")
    if not text:
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_REQUIRED_MESSAGE)
    if len(text) < CUSTOM_INDUSTRY_NAME_MIN_LENGTH:
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_TOO_SHORT_MESSAGE)
    if len(text) > CUSTOM_INDUSTRY_NAME_MAX_LENGTH:
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_TOO_LONG_MESSAGE)
    allowed_punctuation = " \u200c()-.,،&/"
    # حروف/ارقامِ هر زبان + اعراب (Mn/Mc، مثل کسره‌ی «ِ» که در «لوازم‌التحریرِ» می‌آید)؛ `\w` اعراب را نمی‌پذیرد، پس دستی بررسی می‌شود
    if not all(ch.isalnum() or ch in allowed_punctuation or unicodedata.category(ch) in {"Mn", "Mc"} for ch in text):
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_INVALID_MESSAGE)
    if not any(ch.isalpha() for ch in text):
        raise IndustryInstallationError(CUSTOM_INDUSTRY_NAME_INVALID_MESSAGE)
    return text


@transaction.atomic
def install_industry_template(store, industry_template: IndustryTemplate, *, custom_name=None) -> InstallationResult:
    """قالب صنف را روی Store نصب می‌کند — کاملاً اتمیک؛ در خطا هیچ تغییری ثبت نمی‌شود.

    برایِ قالبِ «سایر (صنف آزاد)» نامِ واقعیِ صنف (``custom_name``) الزامی و اعتبارسنجی‌شده است؛ برایِ هر قالبِ دیگری
    نادیده/خالی ذخیره می‌شود (فروشنده‌ی صنفِ مشخص نمی‌تواند نامِ آزاد را جعل کند). ``custom_name=None`` برایِ فراخوانی‌هایِ
    قدیمی (seed/مهاجرت/تست) فقط در «other» خطا نمی‌دهد: آن‌جا خالی ذخیره می‌شود تا نصب‌هایِ برنامه‌ریزی‌شده نشکنند —
    ولی دو نقطه‌ی ورودیِ فروشنده (آنبوردینگ و تنظیماتِ داشبورد) همیشه ``custom_name`` را (حتی خالی) می‌فرستند."""
    can_install_industry_template(store)
    stored_custom_name = ""
    if is_other_industry(industry_template) and custom_name is not None:
        stored_custom_name = validate_custom_industry_name(custom_name)
    if not industry_template.is_offerable_for_new_installation:
        raise IndustryInstallationError(
            f"قالب صنف «{industry_template.name}» در وضعیت «{industry_template.readiness}» است و برای نصب در "
            "دسترس نیست (نگاه کنید به ADR-26)."
        )

    category_map: dict[int, Category] = {}
    categories_created: list[Category] = []

    template_categories = list(
        industry_template.categories.select_related("parent").order_by("display_order")
    )
    remaining = template_categories
    # پردازش لایه‌به‌لایه: والد همیشه قبل از فرزند ساخته می‌شود، صرف‌نظر از عمق سلسله‌مراتب.
    while remaining:
        progressed = []
        still_remaining = []
        for template_category in remaining:
            if template_category.parent_id and template_category.parent_id not in category_map:
                still_remaining.append(template_category)
                continue
            parent = category_map.get(template_category.parent_id) if template_category.parent_id else None
            category = Category(
                store=store, name=template_category.name, icon=template_category.icon,
                parent=parent, order=template_category.display_order,
                source_template_category=template_category,
                slug=_unique_category_slug(store, template_category.name),
            )
            try:
                category.full_clean(exclude=["slug"])
            except ValidationError as exc:
                raise IndustryInstallationError(
                    "؛ ".join(sum(exc.message_dict.values(), []))
                ) from exc
            category.save()
            category_map[template_category.pk] = category
            categories_created.append(category)
            progressed.append(template_category)
        if not progressed:
            raise IndustryInstallationError(
                "ساختار دسته‌بندی قالب صنف نامعتبر است (زنجیره‌ی والد ناقص یا حلقه‌ای)."
            )
        remaining = still_remaining

    attribute_map: dict[int, Attribute] = {}
    attributes_created: list[Attribute] = []
    attribute_value_map: dict[int, AttributeValue] = {}

    for template_attribute in industry_template.attributes.order_by("display_order"):
        attribute, created = Attribute.objects.get_or_create(
            store=store, code=template_attribute.code,
            defaults={
                "label": template_attribute.label, "data_type": template_attribute.data_type,
                "display_type": template_attribute.display_type, "unit": template_attribute.unit,
                "is_variant_axis": template_attribute.is_variant_axis,
                "display_order": template_attribute.display_order,
                "source_template_attribute": template_attribute,
            },
        )
        attribute_map[template_attribute.pk] = attribute
        if created:
            attributes_created.append(attribute)

        for template_value in template_attribute.values.order_by("display_order"):
            key = normalization_key(template_value.label)
            value, _created = AttributeValue.objects.get_or_create(
                attribute=attribute, normalized_label=key,
                defaults={
                    "label": template_value.label, "value": template_value.value or template_value.label,
                    "color_hex": template_value.color_hex, "display_order": template_value.display_order,
                    "source_template_value": template_value,
                },
            )
            attribute_value_map[template_value.pk] = value

    from apps.catalog.models import IndustryTemplateCategoryAttributeMapping, IndustryTemplateRecommendedOption

    for tcam in IndustryTemplateCategoryAttributeMapping.objects.filter(
        template_category__industry_template=industry_template
    ).select_related("template_category", "template_attribute"):
        category = category_map[tcam.template_category_id]
        attribute = attribute_map[tcam.template_attribute_id]
        # قالب برای سه پرچم فقط True/False دارد (نه سه‌حالته)، پس همیشه
        # صریح روی طرح Store نوشته می‌شود — نه ``or None`` که مقدار False
        # صریحِ قالب را با «ارث‌بری از Attribute» اشتباه می‌گرفت.
        CategoryAttributeSchema.objects.get_or_create(
            category=category, attribute=attribute,
            defaults={
                "group": tcam.group, "group_order": tcam.group_order, "display_order": tcam.display_order,
                "is_required": tcam.is_required, "is_filterable_override": tcam.is_filterable,
                "is_comparable_override": tcam.is_comparable,
                "is_searchable_override": tcam.is_searchable,
                "help_text": tcam.help_text, "placeholder": tcam.placeholder,
                "source_template_mapping": tcam,
            },
        )

    for tro in IndustryTemplateRecommendedOption.objects.filter(
        template_category__industry_template=industry_template
    ).select_related("template_category", "template_attribute"):
        category = category_map[tro.template_category_id]
        attribute = attribute_map[tro.template_attribute_id]
        CategoryRecommendedOption.objects.get_or_create(
            category=category, attribute=attribute, defaults={"display_order": tro.display_order},
        )

    installation = StoreIndustryInstallation.objects.create(
        store=store, industry_template=industry_template, installed_version=industry_template.version,
        status=StoreIndustryInstallation.Status.COMPLETED, custom_industry_name=stored_custom_name,
        categories_created=len(categories_created), attributes_created=len(attributes_created),
    )

    return InstallationResult(
        installation=installation, categories_created=categories_created, attributes_created=attributes_created,
    )


def _unique_category_slug(store, name: str) -> str:
    from django.utils.text import slugify

    base = slugify(name, allow_unicode=True).strip("-") or "category"
    candidate = base
    counter = 2
    while Category.objects.filter(store=store, slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate
