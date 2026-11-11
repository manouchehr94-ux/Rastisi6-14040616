from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    verbose_name = "صورتحساب و پرداختِ اشتراک (SaaS Billing)"

    def ready(self):
        from . import checks  # noqa: F401 — registers the webhook-secret strength check (F-12)
