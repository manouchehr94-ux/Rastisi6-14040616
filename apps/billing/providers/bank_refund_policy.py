"""Fail-closed switch for AUTOMATIC bank reversals/refunds through Pasargad, Saman and Mellat.

Why it is off by default: for none of the three could an official, current contract be found that proves the reverse/refund call is
idempotent for a client-supplied key, or that a timed-out call can be queried afterwards (see docs/payments/BANK_REFUND_SAFETY_20261110.md).
Without that, a retry or an ambiguous outcome can pay the customer twice or record a refund that never happened.

Only gateways named in ``settings.RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS`` (comma separated, from the environment) may be called, and only
after the contract has been verified. While a gateway is not listed, a refund of its payment is recorded as «manual processing»:
no bank call, the amount stays reserved, nothing is marked refunded, and finance completes it with a bank reference."""

from django.conf import settings

BANK_REVERSAL_GATEWAYS = frozenset({"pasargad", "saman", "mellat"})
AUTOMATIC_REFUND_DISABLED = "automatic_refund_disabled"
DISABLED_MESSAGE = (
    "بازپرداختِ خودکارِ این درگاه غیرفعال است؛ هیچ درخواستی به بانک ارسال نشد. مبلغ رزرو می‌ماند. بازپرداخت را در پنلِ بانک انجام دهید "
    "و سپس با ارجاعِ بانکی تکمیل ثبت کنید.")


def enabled_gateways() -> frozenset:
    raw = getattr(settings, "RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS", "")
    if isinstance(raw, str):
        names = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        names = [str(n) for n in raw]
    else:
        return frozenset()                                    # anything unexpected fails closed
    return frozenset(n.strip().lower() for n in names if n and n.strip()) & BANK_REVERSAL_GATEWAYS


def automatic_refund_allowed(provider_code: str) -> bool:
    """False for Pasargad/Saman/Mellat unless explicitly enabled. Other providers are not governed by this switch."""
    code = (provider_code or "").strip().lower()
    return code not in BANK_REVERSAL_GATEWAYS or code in enabled_gateways()
