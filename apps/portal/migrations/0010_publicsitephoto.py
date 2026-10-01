from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("portal", "0009_platformconfiguration_enamad_auth_code_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicSitePhoto",
            fields=[
                ("slot", models.CharField(
                    choices=[
                        ("stilllife", "تصویر اصلی محصولات دکور و Hero"),
                        ("ceramics", "نمای فروشگاه و محصولات سرامیکی"),
                        ("ivory", "محصول سرامیکی روشن"),
                        ("olive", "محصول سرامیکی زیتونی"),
                        ("clay", "محصول سفالی"),
                        ("fashion", "گالری پوشاک"),
                        ("beauty", "گالری محصولات زیبایی"),
                        ("skincare", "محصولات مراقبت پوست"),
                        ("bag", "عکس کیف و اکسسوری"),
                    ],
                    max_length=24, primary_key=True, serialize=False, verbose_name="جایگاه تصویر",
                )),
                ("image", models.ImageField(upload_to="portal/public-photos/", verbose_name="تصویر")),
                ("alt_text", models.CharField(
                    blank=True, default="", max_length=180, verbose_name="متن جایگزین تصویر",
                    help_text="برای دسترس‌پذیری و موتورهای جست‌وجو، تصویر را کوتاه و دقیق توصیف کنید.",
                )),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="public_site_photo_updates", to=settings.AUTH_USER_MODEL, verbose_name="ویرایشگر",
                )),
            ],
            options={"verbose_name": "تصویر سایت عمومی", "verbose_name_plural": "تصاویر سایت عمومی"},
        ),
    ]
