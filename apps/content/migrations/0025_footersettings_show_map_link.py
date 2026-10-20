from django.db import migrations, models


class Migration(migrations.Migration):
    """RS-03: opt-in map link. Default False — an existing (possibly demo) address never gets a map link until the merchant
    confirms it is a real, routable address."""

    dependencies = [
        ("content", "0024_alter_heroslide_desktop_image_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="footersettings",
            name="show_map_link",
            field=models.BooleanField(
                default=False,
                help_text="فقط وقتی نشانی را به‌عنوان نشانیِ واقعی و قابل‌مسیریابی تأیید می‌کنید روشن شود؛ پیش‌فرض خاموش است تا نشانیِ نمایشی/ناقص لینکِ نقشهٔ گمراه‌کننده نسازد.",
                verbose_name="نمایش لینک نقشه",
            ),
        ),
    ]
