"""Card-to-card (کارت‌به‌کارت) adapter — manual, admin-confirmed payment.

Like COD it is an OFFLINE adapter (no API, no redirect, never expired through the online-gateway path), but unlike COD it is
*payment by evidence*: the customer transfers money to the merchant's own card, then reports the last 4 digits of the card the money came
from plus the bank tracking number. Nothing here proves payment - ``verify_payment`` is always ``success=False`` - and the order only becomes
paid when an authorised merchant admin approves the submission (``card_transfer_service.approve`` -> ``lifecycle.apply_payment_success``).

The merchant's destination card is public information shown to customers at checkout; it is stored encrypted with the other gateway
credentials. The CUSTOMER's card number, CVV2 and passwords are never requested or stored (only the last 4 digits)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from apps.core.utils import normalize_digits

from .base import PaymentCreationResult, PaymentGatewayAdapter, PaymentVerificationResult


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number]
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def clean_card_number(raw) -> str:
    return re.sub(r"[\s\-_]", "", normalize_digits(str(raw or "")))


class CardToCardAdapter(PaymentGatewayAdapter):
    @property
    def code(self) -> str:
        return "card_to_card"

    @property
    def display_name(self) -> str:
        return "کارت‌به‌کارت"

    @property
    def is_online(self) -> bool:
        return False

    @property
    def requires_manual_confirmation(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        return ["destination_card", "holder_name"]

    @property
    def credential_fields(self) -> list[dict]:
        """Non-secret fields: shown (prefilled) to the merchant and to customers at checkout."""
        return [
            {"name": "destination_card", "label": "شماره کارت مقصد (۱۶ رقم)", "secret": False, "ltr": True, "max_length": 19, "placeholder": "6037 9970 0000 0000"},
            {"name": "holder_name", "label": "نام صاحب کارت", "secret": False, "ltr": False, "max_length": 80, "placeholder": "مثلاً: علی رضایی"},
            {"name": "bank_name", "label": "نام بانک (اختیاری)", "secret": False, "ltr": False, "max_length": 60, "optional": True, "placeholder": "مثلاً: ملی"},
            {"name": "sheba", "label": "شماره شبا (اختیاری)", "secret": False, "ltr": True, "max_length": 30, "optional": True, "placeholder": "IR000000000000000000000000"},
        ]

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        card = clean_card_number(credentials.get("destination_card"))
        if not card:
            errors.append("شماره کارت مقصد را وارد کنید.")
        elif not (card.isdigit() and len(card) == 16 and luhn_valid(card)):
            errors.append("شماره کارت مقصد باید یک شماره کارت معتبر ۱۶ رقمی باشد.")
        if not str(credentials.get("holder_name") or "").strip():
            errors.append("نام صاحب کارت را وارد کنید.")
        sheba = re.sub(r"\s", "", str(credentials.get("sheba") or "")).upper()
        if sheba and not re.fullmatch(r"IR\d{24}", sheba):
            errors.append("شماره شبا باید با IR شروع شود و ۲۴ رقم داشته باشد.")
        return errors

    def create_payment(self, *, amount: Decimal, currency: str, callback_url: str, credentials: dict[str, str],
                       order_code: str, description: str = "", sandbox: bool = False) -> PaymentCreationResult:
        return PaymentCreationResult(track_id=f"c2c-{order_code}", gateway_url=None)

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        return ""

    def verify_payment(self, *, track_id: str, expected_amount: Decimal, currency: str, credentials: dict[str, str],
                       callback_data: dict[str, Any], sandbox: bool = False) -> PaymentVerificationResult:
        """A tracking number alone is never proof: only a human approval marks the order paid."""
        return PaymentVerificationResult(success=False, message="کارت‌به‌کارت — تأیید پس از بررسی مدیر فروشگاه")
