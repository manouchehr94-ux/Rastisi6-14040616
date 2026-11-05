"""Providerِ زیبال برایِ پرداختِ اشتراکِ خودِ پلتفرمِ RastiSi (Phase 3).

Zibal IPG API — نسخه‌یِ v1 (https://gateway.zibal.ir/v1/): درخواست
(``/request``)، تأیید (``/verify``)، بازگشتِ کاربر به یک URLِ hosted-payment
(``/start/{trackId}``). زیبال Webhookِ فشاریِ امضاشده ارسال نمی‌کند — تأییدِ
پرداخت فقط از راهِ بازگشتِ کاربر (که هرگز به‌تنهایی مدرک نیست) + یک تماسِ
verify سرور-به-سرورِ صریح انجام می‌شود (``fetch_payment_status``). این دقیقاً
همان الگویی است که ``apps.orders.gateways.zibal.ZibalAdapter`` برایِ
پرداختِ سفارش‌هایِ مرچنت استفاده می‌کند — امّا این Providerِ کاملاً جداگانه
است: اعتبارنامه از ``PlatformConfiguration`` (پرداختِ خودِ پلتفرم) خوانده
می‌شود، نه از ``PaymentGatewayConfig`` (پرداختِ سفارشِ مشتریانِ یک Store).

تبدیلِ واحدِ پول:
    مبالغِ داخلیِ RastiSi (فاکتور/تلاش) به تومان (IRT) هستند. زیبال ریال
    می‌خواهد. تبدیل (تومان × ۱۰ = ریال) *فقط* همین‌جا انجام می‌شود — هیچ‌جایِ
    دیگری این ضرب/تقسیم را تکرار نمی‌کند."""

from __future__ import annotations

import logging
from decimal import Decimal

import requests

from apps.billing.providers.base import (
    BillingPaymentProvider,
    BillingProviderError,
    PaymentSessionResult,
    PaymentStatusResult,
    ProviderConnectionError,
    ProviderResponseError,
    RefundResult,
    WebhookEventData,
    WebhookVerificationError,
)

logger = logging.getLogger("billing")

IPG_BASE_URL = "https://gateway.zibal.ir/v1/"
PAYMENT_BASE_URL = "https://gateway.zibal.ir/start/"

#: طبقِ مستنداتِ زیبال، merchant=="zibal" یک مقدارِ ثابتِ Sandbox است که بدونِ
#: ثبتِ مرچنتِ واقعی هم کار می‌کند.
SANDBOX_MERCHANT = "zibal"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30

RESULT_SUCCESS = 100
RESULT_ALREADY_VERIFIED = 201

TOMAN_TO_RIAL = 10


class ZibalBillingProvider(BillingPaymentProvider):
    code = "zibal"
    supports_automatic_capture = True

    @classmethod
    def _resolve_merchant(cls, config=None) -> tuple[str, bool]:
        """مرچنتِ زیبالِ **پلتفرم** — فقط از ``platform_gateway_service`` (هرگز از
        ``orders.PaymentGatewayConfig`` که مالِ Storeهاست)."""
        from apps.portal.services.platform_gateway_service import credentials_and_mode

        creds, sandbox, _source = credentials_and_mode(cls.code)
        if sandbox:
            return SANDBOX_MERCHANT, True
        merchant = (creds.get("merchant") or "").strip()
        if not merchant:
            raise BillingProviderError(
                "درگاهِ زیبالِ پلتفرم پیکربندی نشده است.", code="not_configured",
            )
        return merchant, False

    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        merchant, sandbox = self._resolve_merchant()

        # تبدیلِ تومان→ریال — تنها جایِ مجازِ این ضرب در کلِ کدبیسِ Billing.
        amount_rial = int(attempt.amount) * TOMAN_TO_RIAL

        payload = {
            "merchant": merchant,
            "amount": amount_rial,
            "callbackUrl": return_url,
            "orderId": attempt.public_token,
            "description": (
                getattr(invoice, "payment_description", "") or f"اشتراکِ راستیسی — فاکتورِ {invoice.number}"
            )[:255],
        }
        logger.info(
            "Zibal platform billing create_payment_session: attempt=%s amount_rial=%d sandbox=%s",
            attempt.public_token, amount_rial, sandbox,
        )
        data = self._post("request", payload, context="create_payment_session")

        result_code = data.get("result")
        if result_code is None:
            raise ProviderResponseError(
                "ساختارِ پاسخِ زیبال نامعتبر است.", code="missing_result",
            )
        if result_code != RESULT_SUCCESS:
            raise ProviderResponseError(
                "درخواستِ پرداخت توسطِ زیبال رد شد.",
                code=f"zibal_{result_code}",
                details={"result": result_code, "message": data.get("message", "")},
            )
        track_id = data.get("trackId")
        if not track_id:
            raise ProviderResponseError(
                "شناسه‌ی پیگیری از زیبال دریافت نشد.", code="missing_track_id",
            )
        track_id_str = str(track_id)
        return PaymentSessionResult(
            session_id=track_id_str,
            redirect_url=f"{PAYMENT_BASE_URL}{track_id_str}",
            extra={"track_id": track_id_str, "sandbox": sandbox, "amount_rial_sent": amount_rial},
        )

    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        # زیبال Webhookِ فشاریِ امضاشده ارسال نمی‌کند — این مسیر هرگز برایِ
        # کدِ "zibal" فراخوانی نمی‌شود (تأیید از راهِ fetch_payment_status
        # پس از بازگشتِ کاربر انجام می‌شود). صادقانه شکست می‌خورد تا هرگز به
        # اشتباه «تأییدشده» تلقی نشود.
        raise WebhookVerificationError(
            "زیبال از Webhookِ فشاری پشتیبانی نمی‌کند؛ تأیید فقط از راهِ "
            "بازگشتِ کاربر و verify سرور-به-سرور انجام می‌شود.",
            code="unsupported",
        )

    def parse_webhook_event(self, *, body: bytes) -> WebhookEventData:
        raise ProviderResponseError(
            "زیبال Webhookِ فشاری ارسال نمی‌کند.", code="unsupported",
        )

    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        """تأییدِ سرور-به-سرورِ واقعی — تنها مسیرِ مجازِ اعلامِ موفقیتِ پرداخت.
        هرگز بازگشتِ مرورگر را به‌تنهایی مدرک نمی‌گیرد."""
        merchant, _sandbox = self._resolve_merchant()
        track_id = provider_payment_id

        data = self._post(
            "verify", {"merchant": merchant, "trackId": track_id}, context="fetch_payment_status",
        )
        result_code = data.get("result")
        if result_code is None:
            raise ProviderResponseError(
                "ساختارِ پاسخِ تأییدِ زیبال نامعتبر است.", code="verify_missing_result",
            )

        succeeded = result_code in (RESULT_SUCCESS, RESULT_ALREADY_VERIFIED)
        amount_toman = None
        if succeeded and data.get("amount") is not None:
            # زیبال مبلغ را به ریال برمی‌گرداند — تنها جایِ مجازِ این تقسیم.
            amount_toman = Decimal(int(data["amount"])) / TOMAN_TO_RIAL

        return PaymentStatusResult(
            provider_payment_id=track_id,
            succeeded=succeeded,
            amount=amount_toman,
            currency="IRT" if succeeded else "",
            raw_summary={
                "result": result_code,
                "message": data.get("message", ""),
                "status": data.get("status"),
                "ref_number": data.get("refNumber", ""),
                "order_id": str(data.get("orderId", "") or ""),
            },
        )

    def callback_claims_failure(self, callback_data) -> bool:
        return str((callback_data or {}).get("success", "")).strip() == "0"

    def verify_attempt(self, *, attempt, callback_data=None) -> PaymentStatusResult:
        """verify سرور-به-سرور + تطبیقِ ``orderId`` پاسخ با توکنِ تلاش (جلوگیری از اینکه
        پرداختِ موفقِ یک سفارشِ دیگر به این تلاش نسبت داده شود)."""
        status = self.fetch_payment_status(provider_payment_id=attempt.provider_session_id)
        order_id = (status.raw_summary or {}).get("order_id", "")
        if status.succeeded and order_id and order_id != attempt.public_token:
            raise ProviderResponseError("شناسه‌یِ سفارشِ پرداخت با این تلاش نمی‌خواند.", code="order_mismatch")
        return status

    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str,
                       idempotency_key: str) -> RefundResult:
        # زیبال (نسخه‌ی v1) هیچ endpoint مستندِ بازپرداختِ خودکار ندارد —
        # صادقانه به‌عنوانِ «نیازمندِ پردازشِ دستی» برمی‌گردد (مثلِ ManualProvider).
        return RefundResult(
            provider_refund_id=f"zibal-manual-refund-{idempotency_key}",
            succeeded=False,
            raw_summary={"manual": True, "reason": "بازپرداختِ زیبال نیازمندِ پردازشِ دستی است."},
        )

    def _post(self, path: str, payload: dict, *, context: str) -> dict:
        try:
            response = requests.post(
                f"{IPG_BASE_URL}{path}", json=payload, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.ConnectionError as exc:
            logger.error("Zibal platform billing connection error during %s", context)
            raise ProviderConnectionError(
                "اتصال به درگاهِ زیبال برقرار نشد. لطفاً دوباره تلاش کنید.",
                code="connection_error",
            ) from exc
        except requests.Timeout as exc:
            logger.error("Zibal platform billing timeout during %s", context)
            raise ProviderConnectionError(
                "پاسخِ درگاهِ زیبال در زمانِ مقرر دریافت نشد.", code="timeout",
            ) from exc
        except requests.RequestException as exc:
            logger.error("Zibal platform billing request error during %s: %s", context, type(exc).__name__)
            raise ProviderConnectionError(
                "خطا در ارتباط با درگاهِ زیبال.", code="request_error",
            ) from exc

        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            logger.error("Zibal platform billing non-JSON response during %s: status=%d", context, response.status_code)
            raise ProviderResponseError(
                "پاسخِ نامعتبر از درگاهِ زیبال دریافت شد.", code="invalid_json",
            ) from exc
        if not isinstance(data, dict):
            raise ProviderResponseError(
                "ساختارِ پاسخِ زیبال نامعتبر است.", code="bad_shape",
            )
        return data
