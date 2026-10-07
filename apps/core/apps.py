from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        from django.urls import register_converter

        from .converters import UnicodeSlugConverter

        register_converter(UnicodeSlugConverter, "uslug")

        # Registers the production auth-infrastructure system checks.
        from shop_core import checks  # noqa: F401
