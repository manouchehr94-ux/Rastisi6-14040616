"""Manual Card-to-Card (کارت به کارت) offline payment adapter.

This is an OFFLINE payment method, mirroring ``cod.py``: the merchant shows the
customer a destination bank card / IBAN, the customer transfers the money out
of band and (optionally) submits a receipt, and a human at the merchant
approves the order. There is NO server-to-server verification and the customer
receipt NEVER auto-verifies the payment.

Like COD, it is modeled as a gateway adapter purely for uniform dispatch so
checkout code needs no provider conditionals. It differs from online gateways:

- No external API calls, no redirect.
- ``verify_payment`` returns ``success=False`` BY DESIGN — a customer-submitted
  card-to-card receipt can never prove the money arrived; only a manual merchant
  approval (an order status transition) confirms it.
- The destination card number and IBAN are sensitive merchant configuration and
  are stored via the encrypted credentials mechanism
  (``PaymentGatewayConfig.set_credentials`` / Fernet). They are declared as
  ``required_credentials`` so readiness derivation treats the method as
  configured only once they are present. They are never logged or placed in
  error messages / ``__repr__``.

Non-sensitive display fields (cardholder name, bank name, display label) can be
stored in the same encrypted credential blob for simplicity; nothing about this
adapter ever emits any credential value to logs.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from .base import (
    GatewayCategory,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)

logger = logging.getLogger("payment")

# Credential field names. ``card_number`` and ``iban`` are the sensitive ones
# (stored encrypted, never logged). The rest are descriptive display fields.
SENSITIVE_FIELDS = ("card_number", "iban")


class CardToCardAdapter(PaymentGatewayAdapter):
    """Manual Card-to-Card adapter — offline, no external API, no redirect."""

    @property
    def code(self) -> str:
        return "card_to_card"

    @property
    def display_name(self) -> str:
        return "کارت به کارت"

    @property
    def is_online(self) -> bool:
        return False

    @property
    def required_credentials(self) -> list[str]:
        # The destination card number and cardholder name are the minimum needed
        # to present the transfer instructions. Both are treated as credential
        # data; the card number is sensitive and stored encrypted.
        return ["card_number", "cardholder_name"]

    @property
    def category(self) -> GatewayCategory:
        # Manual card-to-card moves money out of band — no online settlement.
        return GatewayCategory.OFFLINE

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # No online operations. An empty capability set makes it explicit that
        # CREATE/VERIFY here are offline bookkeeping, not gateway calls, and
        # that this method never auto-settles.
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate card-to-card configuration.

        Error messages NEVER include the credential values themselves.
        """
        errors = []
        card_number = (credentials.get("card_number") or "").strip()
        cardholder = (credentials.get("cardholder_name") or "").strip()

        if not card_number:
            errors.append("شماره‌ی کارت مقصد الزامی است")
        else:
            digits = card_number.replace("-", "").replace(" ", "")
            if not digits.isdigit() or len(digits) != 16:
                errors.append("شماره‌ی کارت باید ۱۶ رقم باشد")

        if not cardholder:
            errors.append("نام صاحب کارت الزامی است")

        # IBAN is optional, but if provided it must be well-formed (IR + 24 digits).
        iban = (credentials.get("iban") or "").strip()
        if iban:
            normalized = iban.replace(" ", "").upper()
            if normalized.startswith("IR"):
                normalized = normalized[2:]
            if not normalized.isdigit() or len(normalized) != 24:
                errors.append("شماره‌ی شبا باید با IR و ۲۴ رقم باشد")

        return errors

    def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        callback_url: str,
        credentials: dict[str, str],
        order_code: str,
        description: str = "",
        sandbox: bool = False,
    ) -> PaymentCreationResult:
        """Record a card-to-card selection.

        No external call is made and no redirect is produced. Returns a
        synthetic track_id so the attempt has an identifier. The destination
        card/IBAN are intentionally NOT echoed into the result or the log.
        """
        logger.info(
            "Card-to-card payment selected: order=%s amount=%s", order_code, amount
        )
        return PaymentCreationResult(
            track_id=f"card2card-{order_code}",
            gateway_url=None,  # No redirect for an offline method
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """Card-to-card has no redirect URL — never called in normal flow."""
        return ""

    def verify_payment(
        self,
        *,
        track_id: str,
        expected_amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        callback_data: dict[str, Any],
        sandbox: bool = False,
    ) -> PaymentVerificationResult:
        """Card-to-card verification is a no-op — approval is manual.

        Returns ``success=False`` because a customer-submitted receipt must
        NEVER mark the order paid automatically. The real confirmation happens
        through a manual merchant approval (an order status transition), exactly
        like COD's delivery confirmation.
        """
        return PaymentVerificationResult(
            success=False,
            message="کارت به کارت — نیازمند تأیید دستی فروشنده",
        )
