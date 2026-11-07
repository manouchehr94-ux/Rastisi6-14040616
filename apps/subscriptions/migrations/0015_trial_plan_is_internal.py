from django.db import migrations

TRIAL_CODE = "trial"


def hide_trial_plan(apps, schema_editor):
    """The internal Trial plan must never be offered as a purchasable plan: switch off its public selectability.
    Non-destructive (no version, price, subscription or invoice is touched); a missing plan is a no-op."""
    Plan = apps.get_model("subscriptions", "Plan")
    Plan.objects.filter(code=TRIAL_CODE, is_publicly_selectable=True).update(is_publicly_selectable=False)


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0014_planversionprice_discount_percent"),
    ]

    operations = [
        migrations.RunPython(hide_trial_plan, migrations.RunPython.noop),
    ]
