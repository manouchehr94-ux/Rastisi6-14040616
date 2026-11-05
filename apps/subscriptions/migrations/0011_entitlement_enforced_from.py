"""Grandfathering برایِ Entitlementهایِ تازه‌اعمال‌شده: ``EntitlementDefinition.enforced_from``.

``domains.custom`` از این انتشار اعمال می‌شود؛ نسخه‌هایِ منتشرشده **پیش از** زمانِ این مهاجرت (از جمله Trial/Basicِ seed شده که
صریحاً False دارند) دسترسیِ قبلی را حفظ می‌کنند. هیچ ``PlanEntitlement``/اشتراکی تغییر نمی‌کند. Idempotent؛ reverse بی‌اثر."""

from django.db import migrations, models
from django.utils import timezone


def set_effective(apps, schema_editor):
    Definition = apps.get_model("subscriptions", "EntitlementDefinition")
    definition, _ = Definition.objects.get_or_create(
        key="domains.custom",
        defaults={"name": "دامنه‌ی اختصاصی", "entitlement_type": "boolean", "default_enabled": True, "is_active": True},
    )
    update = {"default_enabled": True}
    if definition.enforced_from is None:
        update["enforced_from"] = timezone.now()
    Definition.objects.filter(pk=definition.pk).update(**update)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0010_seed_feature_catalog")]
    operations = [
        migrations.AddField(
            model_name="entitlementdefinition", name="enforced_from",
            field=models.DateTimeField(blank=True, null=True, verbose_name="اعمال از (برایِ نسخه‌هایِ منتشرشده پس از)"),
        ),
        migrations.RunPython(set_effective, migrations.RunPython.noop),
    ]
