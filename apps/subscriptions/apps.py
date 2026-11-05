from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    verbose_name = "اشتراک‌ها و پلن‌ها"

    def ready(self):
        from apps.subscriptions.services import feature_gate

        feature_gate._connect()
