"""بارگذاری ایده‌آل‌نما (idempotent) قالب‌های صنف — نگاه کنید به ADR-25 و ADR-26.

این دستور داده‌ی ``apps.catalog.industry_templates.registry.ALL_INDUSTRY_TEMPLATES``
(تجمیعِ صنف‌های بنیان‌گذار + صنف‌های فاز ۱F) را به رکوردهای
``IndustryTemplate`` (و مدل‌های فرزندش) تبدیل می‌کند. اجرای دوباره‌ی آن
هرگز رکورد تکراری نمی‌سازد: کلید طبیعی «قالب» جفتِ (slug, version) است و
کلید طبیعی هر زیررکورد، کدِ پایدارش در محدوده‌ی همان قالب است — همه از
طریق ``update_or_create`` نوشته می‌شوند.

پس از ساخت/به‌روزرسانیِ هر قالب، اعتبارسنجی (``template_validation_service``)
اجرا و کش می‌شود و آمادگیِ قالب طبق نتیجه تنظیم می‌شود — یک قالب با خطای
اعتبارسنجی هرگز ``production_ready`` نمی‌شود، پس برای مرچنت‌ها قابل‌نصب
نخواهد بود.

این دستور هرگز رکورد Store-محور نمی‌سازد و به هیچ Store متصل نیست؛ فقط
داده‌ی پلتفرم‌محور (IndustryTemplate*) را می‌سازد/به‌روزرسانی می‌کند.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.industry_templates.registry import ALL_INDUSTRY_TEMPLATES, DEPRECATED_LEGACY_SLUGS
from apps.catalog.models import (
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.services.template_validation_service import validate_and_persist

INDUSTRY_TEMPLATES = ALL_INDUSTRY_TEMPLATES

# چیدمان پیشنهادیِ صفحه اصلی به‌ازای هر رستهٔ صنف — کلیدها با
# ``apps.storefront_builder.section_registry.SECTION_REGISTRY`` باید معتبر
# باشند (در زمان مصرف اعتبارسنجی می‌شود، نه اینجا). هر قالبی که در تعریف
# خودش (registry.py) صراحتاً ``default_section_keys`` نداده باشد، بر اساس
# رستهٔ خودش از این نگاشت استفاده می‌کند.
SECTOR_DEFAULT_SECTIONS = {
    "retail": ["announcement_bar", "hero_banner", "category_grid", "newest_products", "best_sellers", "brand_carousel", "promo_cards", "trust_features"],
    "digital": ["announcement_bar", "hero_banner", "category_grid", "amazing_offers", "newest_products", "brand_carousel", "best_sellers", "trust_features"],
    "food": ["announcement_bar", "hero_banner", "category_grid", "newest_products", "discounted_products", "trust_features"],
    "home": ["announcement_bar", "image_slider", "category_grid", "best_sellers", "newest_products", "promo_cards", "trust_features"],
    "beauty": ["announcement_bar", "hero_banner", "category_grid", "best_sellers", "discounted_products", "brand_carousel", "trust_features"],
    "sport": ["announcement_bar", "image_slider", "category_grid", "newest_products", "best_sellers", "brand_carousel", "trust_features"],
    "culture": ["announcement_bar", "hero_banner", "category_grid", "newest_products", "rich_text", "trust_features"],
    "auto": ["announcement_bar", "single_banner", "category_grid", "newest_products", "best_sellers", "trust_features"],
    "industry": ["announcement_bar", "single_banner", "category_grid", "newest_products", "trust_features"],
    "services": ["announcement_bar", "hero_banner", "rich_text", "category_grid", "trust_features"],
    "other": ["announcement_bar", "hero_banner", "category_grid", "newest_products", "best_sellers", "trust_features"],
}


class Command(BaseCommand):
    help = "بارگذاری idempotent قالب‌های صنف (پلتفرم‌محور) از apps.catalog.industry_templates.registry"

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-missing", action="store_true",
            help="فقط قالب‌هایی را بساز که (slug, version)شان هنوز در پایگاه‌داده نیست؛ رکوردهای موجود را هرگز تغییر نمی‌دهد "
                 "(بدون این پرچم، update_or_create رکوردهای موجود را با داده‌ی رجیستری هم‌گرا می‌کند).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created_templates = 0
        updated_templates = 0

        entries = INDUSTRY_TEMPLATES
        if options.get("only_missing"):
            existing = set(IndustryTemplate.objects.values_list("slug", "version"))
            entries = [entry for entry in INDUSTRY_TEMPLATES if (entry["slug"], entry["version"]) not in existing]

        for entry in entries:
            sector = entry.get("sector", IndustryTemplate.Sector.OTHER)
            default_section_keys = entry.get("default_section_keys") or SECTOR_DEFAULT_SECTIONS.get(
                sector, SECTOR_DEFAULT_SECTIONS["other"],
            )
            template, created = IndustryTemplate.objects.update_or_create(
                slug=entry["slug"], version=entry["version"],
                defaults={
                    "name": entry["name"],
                    "description": entry.get("description", ""),
                    "icon": entry.get("icon", ""),
                    "sector": sector,
                    "display_order": entry.get("display_order", 0),
                    "is_active": entry.get("is_active", True),
                    "default_section_keys": list(default_section_keys),
                },
            )
            created_templates += int(created)
            updated_templates += int(not created)

            categories_by_code = self._seed_categories(template, entry["categories"])
            attributes_by_code = self._seed_attributes(template, entry["attributes"])
            self._seed_mappings(entry.get("mappings", []), categories_by_code, attributes_by_code)
            self._seed_recommended_options(
                entry.get("recommended_options", []), categories_by_code, attributes_by_code,
            )

            result = validate_and_persist(template)
            status = "✅" if result.is_valid else "❌"

            self.stdout.write(
                f"{'ساخته شد' if created else 'به‌روزرسانی شد'}: {template.name} "
                f"(نسخه {template.version}) — {len(categories_by_code)} دسته، {len(attributes_by_code)} ویژگی "
                f"— اعتبارسنجی: {status} ({template.readiness}, امتیاز {result.quality_score})"
            )

        # The legacy templates are part of the registry data but must never be offered. A full seed re-sweeps all of them; --only-missing
        # sweeps ONLY the legacy rows it created in this run, so a row that already existed is never touched.
        legacy_scope = (
            [entry["slug"] for entry in entries if entry["slug"] in DEPRECATED_LEGACY_SLUGS]
            if options.get("only_missing") else DEPRECATED_LEGACY_SLUGS
        )
        deprecated_count = IndustryTemplate.objects.filter(slug__in=legacy_scope).update(
            is_active=False, readiness=IndustryTemplate.Readiness.DEPRECATED,
        )
        if deprecated_count:
            self.stdout.write(
                f"🗄  {deprecated_count} قالبِ قدیمیِ منسوخ‌شده (بدونِ تناظرِ یک‌به‌یک با کاتالوگِ "
                f"تأییدشده) از فهرستِ نصبِ جدید حذف شد — رکوردشان حذف نمی‌شود."
            )

        invalid_count = sum(
            1 for t in IndustryTemplate.objects.all() if t.readiness == IndustryTemplate.Readiness.VALIDATION_FAILED
        )
        self.stdout.write(self.style.SUCCESS(
            f"پایان بارگذاری قالب‌های صنف — {created_templates} قالب جدید، {updated_templates} قالب به‌روزرسانی‌شده."
        ))
        if invalid_count:
            self.stdout.write(self.style.WARNING(
                f"⚠️  {invalid_count} قالب اعتبارسنجی را رد کرد و production_ready نشد — "
                f"جزئیات را با «python manage.py validate_industry_templates» ببینید."
            ))

    def _seed_categories(self, template, category_defs, parent=None, display_order_start=0):
        """ساخت درختِ دسته‌بندی قالب به‌صورت بازگشتی؛ کلید طبیعی هر گره ``code`` است."""
        by_code = {}
        for order, node in enumerate(category_defs, start=display_order_start):
            category, _ = IndustryTemplateCategory.objects.update_or_create(
                industry_template=template, code=node["code"],
                defaults={
                    "name": node["name"],
                    "icon": node.get("icon", ""),
                    "parent": parent,
                    "display_order": order,
                },
            )
            by_code[node["code"]] = category
            children = node.get("children", [])
            if children:
                by_code.update(self._seed_categories(template, children, parent=category))
        return by_code

    def _seed_attributes(self, template, attribute_defs):
        by_code = {}
        for order, attr in enumerate(attribute_defs):
            attribute, _ = IndustryTemplateAttribute.objects.update_or_create(
                industry_template=template, code=attr["code"],
                defaults={
                    "label": attr["label"],
                    "data_type": attr["data_type"],
                    "display_type": attr.get("display_type", ""),
                    "unit": attr.get("unit", ""),
                    "is_variant_axis": attr.get("is_variant_axis", False),
                    "display_order": order,
                },
            )
            by_code[attr["code"]] = attribute

            for value_order, raw_value in enumerate(attr.get("values", [])):
                if isinstance(raw_value, tuple):
                    label, color_hex = raw_value
                else:
                    label, color_hex = raw_value, ""
                IndustryTemplateAttributeValue.objects.update_or_create(
                    template_attribute=attribute, label=label,
                    defaults={"value": label, "color_hex": color_hex, "display_order": value_order},
                )
        return by_code

    def _seed_mappings(self, mapping_defs, categories_by_code, attributes_by_code):
        group_orders = {}
        for order, mapping in enumerate(mapping_defs):
            category = categories_by_code[mapping["category"]]
            attribute = attributes_by_code[mapping["attribute"]]
            group = mapping.get("group", "")
            cat_groups = group_orders.setdefault(category.code, {})
            if group not in cat_groups:
                cat_groups[group] = len(cat_groups)
            IndustryTemplateCategoryAttributeMapping.objects.update_or_create(
                template_category=category, template_attribute=attribute,
                defaults={
                    "group": group,
                    "group_order": cat_groups[group],
                    "display_order": order,
                    "is_required": mapping.get("required", False),
                    "is_filterable": mapping.get("filterable", False),
                    "is_comparable": mapping.get("comparable", False),
                    "is_searchable": mapping.get("searchable", False),
                    "help_text": mapping.get("help_text", ""),
                    "placeholder": mapping.get("placeholder", ""),
                },
            )

    def _seed_recommended_options(self, recommendation_defs, categories_by_code, attributes_by_code):
        for order, rec in enumerate(recommendation_defs):
            category = categories_by_code[rec["category"]]
            attribute = attributes_by_code[rec["attribute"]]
            IndustryTemplateRecommendedOption.objects.update_or_create(
                template_category=category, template_attribute=attribute,
                defaults={"display_order": order},
            )
