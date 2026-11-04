from django.urls import path

from . import webhook_views

app_name = "notifications"

urlpatterns = [
    path("email/ses-events/", webhook_views.ses_sns_webhook, name="ses-sns-webhook"),
]
