"""Merchant-facing wording: «واردات/صادرات» → «ورود اطلاعات/خروج اطلاعات».

Only the display ``name`` of four existing ``EntitlementDefinition`` rows changes (keys and
behaviour are untouched). Rows that do not exist (fresh databases are synced from
``entitlements.ENTITLEMENT_DEFINITIONS``) are simply skipped."""

from django.db import migrations

NEW_NAMES = {
    "catalog.import": "ورود اطلاعات (Import)",
    "catalog.export": "خروج اطلاعات (Export)",
    "catalog.import_rows_monthly": "ردیف‌هایِ ورود اطلاعات در ماه",
    "catalog.exports_monthly": "دفعاتِ خروج اطلاعات در ماه",
}
OLD_NAMES = {
    "catalog.import": "واردات (Import)",
    "catalog.export": "صادرات (Export)",
    "catalog.import_rows_monthly": "ردیف‌هایِ واردات در ماه",
    "catalog.exports_monthly": "تعدادِ صادرات در ماه",
}


def _rename(names):
    def forward(apps, schema_editor):
        definition = apps.get_model("subscriptions", "EntitlementDefinition")
        for key, name in names.items():
            definition.objects.filter(key=key).update(name=name)
    return forward


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0007_alter_subscriptionevent_event_type")]
    operations = [migrations.RunPython(_rename(NEW_NAMES), _rename(OLD_NAMES))]
