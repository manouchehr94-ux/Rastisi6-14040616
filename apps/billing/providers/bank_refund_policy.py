"""Fail-closed policy: NO automatic post-payment refund/reversal for platform-owned payments (owner decision, 2026-11-10).

Product decision: a refund of a platform payment (subscription purchase/renewal, SMS package, any other platform product) is reviewed
and approved by the platform administrator and is then performed MANUALLY through an authorised banking channel; its verified outcome
is recorded in RastiSi with a bank reference. Approval never calls a provider and never executes a refund.

Enforcement (backend, not UI): ``refund_service._execute_with_provider``, ``duplicate_payment_service.refund_duplicate`` and
``AdapterBackedBillingProvider.refund_payment`` all stop on ``automatic_refund_allowed() == False`` BEFORE a provider is resolved, a
credential is read or a network call is made, for EVERY provider code (not only Pasargad/Saman/Mellat).

Why the switch is a code constant and not an environment variable: an environment flag can be flipped in production by a
configuration change nobody reviews. Re-enabling an automatic path needs a code change, a written bank contract that proves idempotency
and result inquiry (see docs/payments/BANK_REFUND_SAFETY_20261110.md) and a new owner decision.

This does NOT touch payment cancellation / authorisation reversal of an unsettled payment, verification, settlement reconciliation,
webhook recovery or fulfilment: only ``refund_payment`` of an already successful platform payment is governed here."""

from django.conf import settings

#: Owner decision: automatic refunds after a successful platform payment are NOT approved. Do not change without a new decision.
AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED = False

BANK_REVERSAL_GATEWAYS = frozenset({"pasargad", "saman", "mellat"})
AUTOMATIC_REFUND_DISABLED = "automatic_refund_disabled"
DISABLED_MESSAGE = (
    "بازپرداختِ خودکارِ پرداختهای پلتفرم غیرفعال است؛ هیچ درخواستی به بانک یا درگاه ارسال نشد. مبلغ رزرو میماند. "
    "درخواست باید توسط مدیر بررسی و تأیید شود، بازپرداخت بهصورت دستی از مسیرِ بانکیِ مجاز انجام شود و سپس با ارجاعِ بانکی تکمیل ثبت شود.")


def enabled_gateways() -> frozenset:
    """Per-gateway opt-in list (environment). It is only consulted when ``AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED`` is True."""
    raw = getattr(settings, "RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS", "")
    if isinstance(raw, str):
        names = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        names = [str(n) for n in raw]
    else:
        return frozenset()                                    # anything unexpected fails closed
    return frozenset(n.strip().lower() for n in names if n and n.strip()) & BANK_REVERSAL_GATEWAYS


def automatic_refund_allowed(provider_code: str) -> bool:
    """False for EVERY provider while ``AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED`` is False (the approved state).

    Even if a future decision sets the constant, Pasargad/Saman/Mellat additionally need an explicit environment opt-in per gateway."""
    if AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED is not True:
        return False
    code = (provider_code or "").strip().lower()
    return code not in BANK_REVERSAL_GATEWAYS or code in enabled_gateways()
