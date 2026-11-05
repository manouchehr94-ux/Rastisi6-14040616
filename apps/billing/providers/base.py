"""قراردادِ Provider-نِیوترالِ پرداختِ اشتراک (ADR-75).

هر Provider باید این رابط را پیاده کند. کدِ اختصاصیِ Provider فقط پشتِ این
رابط زندگی می‌کند — هرگز در Viewها/سرویس‌هایِ اشتراک پخش نمی‌شود.

قواعد:
- هرگز داده‌ی خامِ کارت لاگ/ذخیره نمی‌شود.
- هرگز موفقیتِ پرداختِ واقعی جعل نمی‌شود.
- تماس‌هایِ HTTPِ خارجی باید timeoutِ صریح داشته باشند.
- خروجی‌ها dataclassِ ساخت‌یافته‌اند، نه dictِ خام.
- همه‌ی حالت‌هایِ خطا زیرمجموعه‌ی ``BillingProviderError``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


# --------------------------------------------------------------------------- نتایج

@dataclass(frozen=True)
class PaymentSessionResult:
    """نتیجه‌ی ساختِ یک جلسه‌ی پرداخت."""

    session_id: str
    redirect_url: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookEventData:
    """رخدادِ Webhookِ تجزیه‌شده — فقط فیلدهایِ غیرِحساس."""

    event_id: str
    event_type: str
    provider_payment_id: str = ""
    session_id: str = ""
    amount: Decimal | None = None
    currency: str = ""
    succeeded: bool = False
    raw_summary: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentStatusResult:
    provider_payment_id: str
    succeeded: bool
    amount: Decimal | None = None
    currency: str = ""
    raw_summary: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    provider_refund_id: str
    succeeded: bool
    raw_summary: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- خطاها

class BillingProviderError(Exception):
    """پایه‌ی خطاهایِ Provider — پیام امن برایِ لاگ/ادمین (بدونِ راز/PII)."""

    def __init__(self, message: str, code: str = "", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ProviderConnectionError(BillingProviderError):
    """خطایِ شبکه (timeout/DNS/اتصال)."""


class ProviderResponseError(BillingProviderError):
    """پاسخِ نامعتبر/غیرمنتظره از Provider."""


class WebhookVerificationError(BillingProviderError):
    """امضا/زمان/شکلِ Webhook معتبر نیست."""


# --------------------------------------------------------------------------- رابط

class BillingPaymentProvider(ABC):
    """رابطِ Provider-نِیوترال. پیاده‌سازی‌ها پشتِ ``registry.get_provider`` قرار
    می‌گیرند."""

    #: کدِ پایدارِ Provider (در ``SubscriptionPaymentAttempt.provider`` ذخیره می‌شود).
    code: str = ""
    #: آیا این Provider می‌تواند پرداختِ واقعی را به‌صورتِ خودکار (server-side)
    #: تأیید کند؟ Providerِ دستی/تستی ``False`` است (تأیید نیازمندِ اقدامِ صریح).
    supports_automatic_capture: bool = False

    @abstractmethod
    def create_payment_session(self, *, attempt, invoice, return_url: str) -> PaymentSessionResult:
        """یک جلسه‌ی پرداخت می‌سازد و آدرسِ hosted-payment را برمی‌گرداند."""

    @abstractmethod
    def verify_webhook(self, *, headers: dict, body: bytes, secret: str) -> bool:
        """امضا/صحتِ Webhook را بررسی می‌کند (پیش از هر تغییرِ کسب‌وکاری)."""

    @abstractmethod
    def parse_webhook_event(self, *, body: bytes) -> WebhookEventData:
        """بدنه‌ی Webhook را به یک ``WebhookEventData`` تجزیه می‌کند."""

    @abstractmethod
    def fetch_payment_status(self, *, provider_payment_id: str) -> PaymentStatusResult:
        """وضعیتِ پرداخت را server-side از Provider می‌پرسد."""

    @abstractmethod
    def refund_payment(self, *, provider_payment_id: str, amount: Decimal, currency: str,
                       idempotency_key: str) -> RefundResult:
        """بازپرداختِ (کاملِ/جزئیِ) یک پرداخت را از Provider درخواست می‌کند."""

    def verify_attempt(self, *, attempt, callback_data: dict | None = None) -> PaymentStatusResult:
        """تأییدِ سرور-به-سرورِ یک تلاشِ مشخص (نه پارامترهایِ مرورگر). پیش‌فرض: همان
        ``fetch_payment_status`` با شناسه‌یِ جلسه‌ی خودِ تلاش. Providerهایی که برایِ تأیید به
        مبلغِ مورد انتظار یا داده‌یِ بازگشت نیاز دارند آن را override می‌کنند."""
        return self.fetch_payment_status(provider_payment_id=attempt.provider_session_id)

    def callback_claims_failure(self, callback_data: dict | None) -> bool:
        """آیا دادهٔ بازگشتِ مرورگر *ادعا* می‌کند پرداخت ناموفق/لغو شد؟ فقط یک راهنما: هرگز به‌تنهایی
        وضعیتِ مالی را عوض نمی‌کند؛ فقط همراهِ «verify سرور هم تأیید نکرد» یک تلاش را ناموفق علامت می‌زند."""
        return False
