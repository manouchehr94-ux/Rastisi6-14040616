"""Card-to-card (کارت‌به‌کارت) adapter — manual, admin-confirmed payment.

Like COD it is an OFFLINE adapter (no API, no redirect, never expired through the online-gateway path), but unlike COD it is
*payment by evidence*: the customer transfers money to the merchant's own card, then reports the last 4 digits of the card the money came
from plus the bank tracking number. Nothing here proves payment - ``verify_payment`` is always ``success=False`` - and the order only becomes
paid when an authorised merchant admin approves the submission (``card_transfer_service.approve`` -> ``lifecycle.apply_payment_success``).

The merchant's destination card is public information shown to customers at checkout; it is stored encrypted with the other gateway
credentials. The CUSTOMER's card number, CVV2 and passwords are never requested or stored (only the last 4 digits)."""

from __future__ import annotations

import re
import unicodedata
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


# Digit scripts accepted on input (anything else that is not a separator stays in the string and is REJECTED, never silently dropped).
_DIGIT_RANGES = ((0x30, 0x39), (0x6F0, 0x6F9), (0x660, 0x669), (0xFF10, 0xFF19))     # ASCII · Persian · Arabic-Indic · fullwidth
#: Separators people type or paste between the 4-digit groups, in addition to every Unicode separator/format/control/dash character.
_EXTRA_SEPARATORS = frozenset("_،٬,./\\·−")


def strip_display_formatting(raw) -> str:
    """The value without PRESENTATION formatting, with digits normalized to ASCII.

    Removed: every whitespace/separator (``Z*`` incl. NBSP / thin space), format characters (``Cf``: ZWNJ, ZWSP, LRM, RLM, bidi isolates, BOM — routine in RTL typing and
    copy/paste), control characters (tab/newline), dashes (``Pd``) and the common separators ``_ ، ٬ , . / \\``. Persian, Arabic-Indic and fullwidth digits become ASCII.
    Nothing else is touched: letters / symbols / other-script digits remain so validation can reject them. This is the ONE rule used by validation, storage, display
    and the customer page; the browser mask (``card_number_input.js``) mirrors it."""
    out = []
    for ch in str(raw or ""):
        if unicodedata.category(ch) in ("Zs", "Zl", "Zp", "Cf", "Cc", "Pd") or ch in _EXTRA_SEPARATORS:
            continue
        code = ord(ch)
        for low, high in _DIGIT_RANGES:
            if low <= code <= high:
                ch = str(code - low)
                break
        out.append(ch)
    return "".join(out)


def clean_card_number(raw) -> str:
    return strip_display_formatting(raw)


def clean_sheba(raw) -> str:
    return strip_display_formatting(raw).upper()


def card_number_error(raw) -> str:
    """"" when valid; else ONE specific Persian reason (not a generic "16 digits" message): empty / non-digit characters / digit COUNT / checksum.
    Length is judged on the digits only — never on grouped characters."""
    card = clean_card_number(raw)
    if not card:
        return "شماره کارت مقصد را وارد کنید."
    if not re.fullmatch(r"[0-9]+", card):
        return "شماره کارت مقصد فقط باید شامل رقم باشد (حرف یا نماد مجاز نیست)."
    if len(card) != 16:
        return "شماره کارت مقصد باید دقیقاً ۱۶ رقم باشد (فاصله و خط تیره حساب نمی‌شوند)."
    if not luhn_valid(card):
        return "شماره کارت مقصد معتبر نیست؛ ارقام را دوباره بررسی کنید."
    return ""


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
    def credential_aliases(self) -> dict[str, str]:
        # An alternate field naming (card_number / cardholder_name / iban) used by another implementation of the same
        # method: such stored configurations stay valid, readable and usable by the canonical card-transfer workflow.
        return {"card_number": "destination_card", "cardholder_name": "holder_name", "iban": "sheba"}

    @property
    def credential_fields(self) -> list[dict]:
        """Non-secret fields: shown (prefilled) to the merchant and to customers at checkout."""
        return [
            {"name": "destination_card", "label": "شماره کارت مقصد (۱۶ رقم)", "secret": False, "ltr": True, "max_length": 40, "placeholder": "6037 9970 0000 0000", "mask": "card"},
            {"name": "holder_name", "label": "نام صاحب کارت", "secret": False, "ltr": False, "max_length": 80, "placeholder": "مثلاً: علی رضایی"},
            {"name": "bank_name", "label": "نام بانک (اختیاری)", "secret": False, "ltr": False, "max_length": 60, "optional": True, "placeholder": "مثلاً: ملی"},
            {"name": "sheba", "label": "شماره شبا (اختیاری)", "secret": False, "ltr": True, "max_length": 48, "optional": True, "placeholder": "IR000000000000000000000000"},
        ]

    def normalize_credentials(self, credentials: dict) -> dict:
        """Aliases first, then the card / sheba READ in their canonical form: a value saved earlier with spaces or invisible RTL marks stays readable and usable
        (the stored ciphertext is untouched until the merchant saves the form again)."""
        out = super().normalize_credentials(credentials)
        if out.get("destination_card"):
            out["destination_card"] = clean_card_number(out["destination_card"])
        if out.get("sheba"):
            out["sheba"] = clean_sheba(out["sheba"])
        return out

    def field_errors(self, credentials: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        card_problem = card_number_error(credentials.get("destination_card"))
        if card_problem:
            out["destination_card"] = card_problem
        if not str(credentials.get("holder_name") or "").strip():
            out["holder_name"] = "نام صاحب کارت را وارد کنید."
        sheba = clean_sheba(credentials.get("sheba"))
        if sheba and not re.fullmatch(r"IR\d{24}", sheba):
            out["sheba"] = "شماره شبا باید با IR شروع شود و ۲۴ رقم داشته باشد."
        return out

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        return list(self.field_errors(credentials).values())

    def create_payment(self, *, amount: Decimal, currency: str, callback_url: str, credentials: dict[str, str],
                       order_code: str, description: str = "", sandbox: bool = False) -> PaymentCreationResult:
        return PaymentCreationResult(track_id=f"c2c-{order_code}", gateway_url=None)

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        return ""

    def verify_payment(self, *, track_id: str, expected_amount: Decimal, currency: str, credentials: dict[str, str],
                       callback_data: dict[str, Any], sandbox: bool = False) -> PaymentVerificationResult:
        """A tracking number alone is never proof: only a human approval marks the order paid."""
        return PaymentVerificationResult(success=False, message="کارت‌به‌کارت — تأیید پس از بررسی مدیر فروشگاه")
