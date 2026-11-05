"""ممیزیِ ۷۶ ردیفیِ مرجع: ردیف‌هایِ تازه‌ی کاتالوگ + اصلاحِ ردیفِ «ریدایرکتِ ۳۰۱» (قاعده‌ی قابلِ‌تعریف وجود ندارد ⇒ عمومی نمی‌شود).

فقط ردیف‌هایِ ماتریسِ نمایشی را می‌سازد/پنهان می‌کند؛ هیچ Entitlement/اشتراکی تغییر نمی‌کند. Idempotent؛ reverse بی‌اثر."""

from django.db import migrations


def apply(apps, schema_editor):
    from apps.subscriptions.feature_catalog import CATALOG, PLANNED

    Definition = apps.get_model("subscriptions", "EntitlementDefinition")
    Feature = apps.get_model("subscriptions", "PricingFeature")
    for order, f in enumerate(CATALOG, start=1):
        definition = Definition.objects.filter(key=f.entitlement).first() if f.entitlement else None
        Feature.objects.get_or_create(
            key=f.key,
            defaults={
                "category": f.category, "title": f.title, "description": f.description, "unit_label": f.unit,
                "display_order": order * 10, "is_visible": f.availability != PLANNED,
                "entitlement": definition, "availability": f.availability, "note": f.note,
            },
        )
    # ردیفِ اشتباهاً «پیاده‌سازی‌شده» در نسخه‌ی اولِ کاتالوگ
    Feature.objects.filter(key="redirects").update(availability="planned", is_visible=False)
    # دامنه‌یِ اختصاصی اکنون با grandfathering اعمال می‌شود
    definition = Definition.objects.filter(key="domains.custom").first()
    if definition is not None:
        Feature.objects.filter(key="custom_domain").update(entitlement=definition)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0011_entitlement_enforced_from")]
    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
