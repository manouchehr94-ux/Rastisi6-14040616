from django.urls import path

from apps.billing import views
from apps.billing.providers import qa_simulator

app_name = "billing"

urlpatterns = [
    # endpointِ عمومیِ Webhook (بدونِ CSRF، امضا-تأییدشده).
    path("webhook/<slug:provider_code>/", views.billing_webhook, name="webhook"),
    # بازگشتِ مرورگر از درگاهِ پلتفرم — توکنِ غیرقابلِ‌حدس + verify سرور-به-سرور (مدرک نیست).
    path("return/<str:token>/", views.payment_return, name="payment-return"),
    # LOCAL QA only: answers 404 unless the simulator guard holds (see providers/qa_simulator.py)
    path("qa-simulator/start/<int:track_id>/", qa_simulator.start_page, name="qa-simulator-start"),
]
