from django.apps import AppConfig


class ChatIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat_integration"
    verbose_name = "یکپارچه‌سازی گفتگو (RastiChat)"

    def ready(self):
        from . import conf

        conf.validate_settings()
