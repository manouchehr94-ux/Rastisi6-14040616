"""Providerِ «کارت‌به‌کارتِ پلتفرم» — **یک درگاهِ آنلاین نیست**.

برای این روش هیچ جلسه‌ی پرداخت، redirect، callback یا verify سرور-به-سرور وجود ندارد؛ پرداخت فقط با ادعای مالک و تأییدِ دستیِ
مدیرِ مالی (``manual_card_service``) اعمال می‌شود. این کلاس فقط برای یکپارچگیِ ثبتِ تلاش‌ها (``provider="platform_card"``) و
مسیرِ بازپرداخت در registry هست: هرگز موفقیتی جعل نمی‌کند و هیچ تماسِ بیرونی نمی‌زند."""

from __future__ import annotations

from decimal import Decimal

from apps.billing.providers.base import (
    BillingPaymentProvider,
    BillingProviderError,
    PaymentSessionResult,
    PaymentStatusResult,
    ProviderResponseError,
    RefundResult,
    WebhookEventData,
    WebhookVerificationError,
)

CODE = "platform_card"


class ManualCardProvider(BillingPaymentProvider):
    code = CODE
    supports_automatic_capture = False

    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        raise BillingProviderError("کارت‌به‌کارت پرداختِ آنلاین ندارد؛ ادعای پرداخت ثبت کنید.", code="manual_only")

    def verify_attempt(self, *, attempt, callback_data=None) -> PaymentStatusResult:
        return PaymentStatusResult(provider_payment_id="", succeeded=False, raw_summary={"manual": True})

    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        raise ProviderResponseError("کارت‌به‌کارت وضعیتِ سرور-به-سرور ندارد.", code="manual_only")

    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        raise WebhookVerificationError("کارت‌به‌کارت Webhook ندارد.", code="unsupported")

    def parse_webhook_event(self, *, body: bytes) -> WebhookEventData:
        raise ProviderResponseError("کارت‌به‌کارت Webhook ندارد.", code="unsupported")

    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str, idempotency_key: str) -> RefundResult:
        # بازپرداخت = انتقالِ دستیِ پول به مالک؛ همیشه «در انتظارِ پردازشِ دستی» تا مدیرِ مالی انجامش را ثبت کند.
        return RefundResult(
            provider_refund_id=f"{CODE}-manual-refund-{idempotency_key}", succeeded=False,
            raw_summary={"manual": True, "reason": "بازپرداخت باید با انتقالِ بانکیِ دستی انجام و ثبت شود."},
        )
