from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"

    def ready(self):
        from . import checks, signals  # noqa: F401 — registers the price-inquiry sync receivers and the industry-registry system check
