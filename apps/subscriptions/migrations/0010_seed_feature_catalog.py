"""داده‌یِ اولیه: ردیف‌هایِ ماتریسِ تعرفه از کاتالوگِ کانونی. هیچ Entitlement/اشتراکِ موجودی تغییر نمی‌کند. Idempotent؛ reverse بی‌اثر."""

from django.db import migrations


def seed(apps, schema_editor):
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


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0009_pricing_options_and_catalog")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
