"""Viewهایِ عمومیِ صورتحساب: endpointِ Webhook (ADR-76) و بازگشتِ درگاه (``payment_return``).

این دو تنها مسیرهایِ صورتحساب‌اند که CSRF ندارند (Webhook/POSTِ بازگشتِ Provider نمی‌تواند توکنِ CSRF
بفرستد)؛ در عوض Webhook با امضا و بازگشت با **توکنِ غیرقابلِ‌حدسِ تلاش + verify سرور-به-سرور** محافظت
می‌شوند. هیچ مسیرِ دیگری از این معافیت استفاده نمی‌کند. Viewهایِ Merchant Billing در
``apps.dashboard`` هستند (commit 10)."""

import logging

from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.billing.providers.base import BillingProviderError, WebhookVerificationError
from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service, sms_purchase_payment_service, webhook_service
from apps.billing.services.confirmation_service import ConfirmationError
from apps.sms.models import SmsPackagePaymentAttempt

logger = logging.getLogger("billing")


@csrf_exempt
@require_POST
def billing_webhook(request, provider_code):
    """Webhookِ خام را می‌پذیرد، امضا را تأیید و رخداد را در صندوقِ ورودی ذخیره
    می‌کند. هرگز از پارامترهایِ query یا احرازِ نشست استفاده نمی‌کند."""
    content_type = (request.content_type or "").lower()
    if "json" not in content_type:
        return HttpResponseBadRequest("Content-Type نامعتبر است.")

    body = request.body  # bytes خام برایِ بررسیِ امضا
    try:
        event = webhook_service.ingest_webhook(
            provider_code=provider_code, headers=dict(request.headers), body=body,
        )
    except webhook_service.WebhookTooLarge:
        return HttpResponse("payload بیش از حد بزرگ است.", status=413)
    except WebhookVerificationError:
        # امضا/زمانِ نامعتبر — هیچ تغییری در دامنه؛ ۴۰۰ بدونِ افشایِ جزئیات.
        return HttpResponseBadRequest("تأییدِ Webhook ناموفق بود.")
    except BillingProviderError:
        return HttpResponseBadRequest("رخدادِ Webhook نامعتبر است.")

    # پردازشِ تأییدِ پرداخت به‌صورتِ جدا و امن انجام می‌شود؛ خطایِ کسب‌وکاری رویِ
    # خودِ رخداد ثبت و برایِ Retryِ مدیر در دسترس می‌ماند — پس همیشه ۲۰۰
    # برمی‌گردانیم تا Provider بی‌مورد Retry نکند.
    try:
        payment_flow_service.process_webhook_event(event)
    except Exception:  # noqa: BLE001 — خطا رویِ رخداد ثبت می‌شود، پاسخ ۲۰۰ می‌ماند
        logger.exception("webhook processing failed for event %s", event.pk)
    return HttpResponse("ok", status=200)


# --------------------------------------------------------------------------- بازگشتِ درگاه

#: حداقل فاصله‌یِ دو verify رویِ یک تلاش (ثانیه) — جلوگیری از تقویتِ DoS رویِ درگاه با رفرشِ پیاپی.
_VERIFY_MIN_INTERVAL = 8
_MAX_CALLBACK_KEYS = 20
_MAX_CALLBACK_VALUE = 200


def _lookup_attempt(token: str):
    """تلاش را از روی توکن پیدا می‌کند. پیشوندِ ``sms_`` فقط یک راهنماست؛ اگر در جدولِ پیامک نبود
    (توکنِ اشتراک به‌طورِ تصادفی با همان چهار نویسه شروع شده باشد) جدولِ اشتراک هم بررسی می‌شود."""
    if token.startswith(sms_purchase_payment_service.TOKEN_PREFIX):
        attempt = SmsPackagePaymentAttempt.objects.filter(public_token=token).select_related("purchase").first()
        if attempt is not None:
            return attempt, "sms"
    attempt = SubscriptionPaymentAttempt.objects.filter(public_token=token).select_related("invoice").first()
    return attempt, "subscription"


def _callback_data(request) -> dict:
    data = {}
    for source in (request.GET, request.POST):
        for key in list(source.keys())[:_MAX_CALLBACK_KEYS]:
            data[str(key)[:60]] = str(source.get(key, ""))[:_MAX_CALLBACK_VALUE]
    return data


_STATE_BY_STATUS = {"succeeded": "ok", "failed": "failed", "cancelled": "failed", "expired": "failed",
                    "requires_action": "action"}


@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
def payment_return(request, token):
    """مقصدِ بازگشتِ مرورگر از درگاهِ پلتفرم. **بازگشت هرگز مدرکِ پرداخت نیست**: توکنِ مسیر فقط
    تلاشِ ما را مشخص می‌کند؛ مبلغ/سفارش/موفقیت را فقط verify سرور-به-سرور با Provider تعیین می‌کند
    (idempotent؛ رفرش/تکرار اثری اضافه ندارد). سپس کاربر به ``return_to`` (مسیرِ نسبی) یا صفحهٔ وضعیت می‌رود."""
    attempt, kind = _lookup_attempt(token)
    if attempt is None:
        raise Http404

    if not attempt.is_final:
        throttle_key = f"billing:verify:{token}"
        if cache.add(throttle_key, 1, _VERIFY_MIN_INTERVAL):
            data = _callback_data(request)
            try:
                if kind == "sms":
                    attempt = sms_purchase_payment_service.verify_and_fulfill(attempt, callback_data=data)
                else:
                    attempt = payment_flow_service.confirm_from_provider_verification(attempt, callback_data=data)
            except (BillingProviderError, ConfirmationError, sms_purchase_payment_service.SmsPaymentConfirmationError) as exc:
                logger.warning("platform payment verify failed for %s: %s", kind, getattr(exc, "code", type(exc).__name__))
                attempt = type(attempt).objects.get(pk=attempt.pk)
            except Exception:  # noqa: BLE001 — هرگز ۵۰۰ به مرورگرِ بازگشتی؛ تطبیقِ بعدی دوباره تلاش می‌کند
                logger.exception("platform payment verify crashed for %s attempt %s", kind, attempt.pk)
                attempt = type(attempt).objects.get(pk=attempt.pk)

    state = _STATE_BY_STATUS.get(attempt.status, "pending")
    return_to = payment_flow_service.safe_return_to(attempt.return_to)
    if return_to:
        sep = "&" if "?" in return_to else "?"
        return HttpResponseRedirect(f"{return_to}{sep}payment={state}")
    return render(request, "billing/payment_return.html", {"state": state, "kind": kind, "amount": attempt.amount})
