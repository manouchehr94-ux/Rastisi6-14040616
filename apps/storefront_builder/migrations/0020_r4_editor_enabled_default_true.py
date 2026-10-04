from django.db import migrations, models


def flip_existing_layouts_to_r4_enabled(apps, schema_editor):
    """Pre-Task-10 remediation — R4 live cutover. No important production
    data exists to preserve (per the remediation's explicit instruction);
    every existing Store's layout is flipped to the new non-blocking
    default so R4 is the reachable merchant editor immediately after this
    migration runs, not only for Stores provisioned after it."""
    StorefrontLayout = apps.get_model("storefront_builder", "StorefrontLayout")
    StorefrontLayout.objects.filter(r4_editor_enabled=False).update(r4_editor_enabled=True)


def revert_existing_layouts_to_r4_disabled(apps, schema_editor):
    StorefrontLayout = apps.get_model("storefront_builder", "StorefrontLayout")
    StorefrontLayout.objects.filter(r4_editor_enabled=True).update(r4_editor_enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0019_page_appearance_overrides"),
    ]

    operations = [
        migrations.AlterField(
            model_name="storefrontlayout",
            name="r4_editor_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Non-blocking compatibility flag for the R4 storefront-builder "
                    "editor shell. Pre-Task-10 remediation: R4 is now the default "
                    "canonical merchant editor (dashboard nav routes here); this "
                    "flag exists only so an individual Store can be pinned back to "
                    "the legacy editor if a regression is found, never to gate "
                    "normal access."
                ),
            ),
        ),
        migrations.RunPython(
            flip_existing_layouts_to_r4_enabled,
            revert_existing_layouts_to_r4_disabled,
        ),
    ]
