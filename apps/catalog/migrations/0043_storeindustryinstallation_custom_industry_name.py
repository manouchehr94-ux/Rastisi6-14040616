from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: a free-text industry name for the «other» template (blank for every existing row)."""

    dependencies = [
        ("catalog", "0042_price_inquiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="storeindustryinstallation",
            name="custom_industry_name",
            field=models.CharField(blank=True, default="", max_length=80, verbose_name="نامِ صنفِ آزاد"),
        ),
    ]
