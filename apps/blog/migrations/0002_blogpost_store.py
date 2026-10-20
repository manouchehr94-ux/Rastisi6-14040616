# A backward-compatible Store owner for articles; legacy global articles retain NULL.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("stores", "0020_store_onboarding_required_at"),
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogpost",
            name="store",
            field=models.ForeignKey(
                to="stores.store", on_delete=django.db.models.deletion.CASCADE,
                related_name="journal_posts", null=True, blank=True,
                verbose_name="فروشگاه",
            ),
        ),
    ]
