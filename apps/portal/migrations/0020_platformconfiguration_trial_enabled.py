from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: a switch for granting the initial Trial (default ON, so behaviour for existing configs is unchanged)."""

    dependencies = [
        ("portal", "0019_zibal_legacy_to_gateway_config"),
    ]

    operations = [
        migrations.AlterField(
            model_name="platformconfiguration",
            name="default_trial_days",
            field=models.PositiveIntegerField(
                default=30, verbose_name="روزهای پیش‌فرض دوره‌ی آزمایشی",
                help_text="فقط روی فروشگاه‌هایِ تازه اثر می‌گذارد؛ دوره‌یِ آزمایشیِ فروشگاه‌هایِ دارایِ Trial تغییر نمی‌کند.",
            ),
        ),
        migrations.AddField(
            model_name="platformconfiguration",
            name="trial_enabled",
            field=models.BooleanField(
                default=True, verbose_name="اعطایِ دوره‌ی آزمایشیِ اولیه به فروشگاه‌هایِ تازه",
                help_text="اگر خاموش باشد فروشگاهِ تازه Trial نمی‌گیرد و باید پلنِ پولی بخرد.",
            ),
        ),
    ]
