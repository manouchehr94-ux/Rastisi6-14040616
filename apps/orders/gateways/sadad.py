"""Sadad (سداد / بانک ملی) PSP adapter — DOCUMENTATION_BLOCKED skeleton.

Sadad Informatics (Bank Melli Iran) IPG, which historically uses a key/merchant
signing scheme over a token/redirect/callback/verify flow. The official current
documentation (https://sadadpsp.ir/) was NOT reachable from this environment
during the FEAT-004 research pass (2026-11-03): the host timed out.

Because the real contract (auth, the exact current signing/encryption scheme,
token/redirect/callback/verify endpoints, currency unit, error codes, sandbox)
is NOT verified from an official source, this adapter registers, declares its
real category (PSP) and ``documentation_blocked = True`` so the readiness
derivation surfaces DOCUMENTATION_BLOCKED and it is NEVER selectable at real
(non-sandbox) checkout. It declares NO capabilities and raises
``GatewayUnsupportedOperationError`` from every money-moving method. Request
signing/encryption must be implemented strictly per the documented CURRENT
crypto once the official contract is read — never guessed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .base import (
    GatewayCategory,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentVerificationResult,
)


class SadadAdapter(PaymentGatewayAdapter):
    """Sadad (Bank Melli) PSP adapter (documentation-blocked skeleton)."""

    @property
    def code(self) -> str:
        return "sadad"

    @property
    def display_name(self) -> str:
        return "بانک ملی (سداد)"

    @property
    def is_online(self) -> bool:
        return True

    @property
    def category(self) -> GatewayCategory:
        return GatewayCategory.PSP

    @property
    def documentation_blocked(self) -> bool:
        return True

    @property
    def required_credentials(self) -> list[str]:
        # Sadad merchants hold a merchant id, terminal id and a signing key.
        # Field names only; asserts nothing about the unverified signing contract.
        return ["merchant_id", "terminal_id", "key"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("merchant_id") or "").strip():
            errors.append("شناسه‌ی پذیرنده (MerchantId) الزامی است")
        if not (credentials.get("terminal_id") or "").strip():
            errors.append("شناسه‌ی پایانه (TerminalId) الزامی است")
        if not (credentials.get("key") or "").strip():
            errors.append("کلید امضا (Key) الزامی است")
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
        raise self._unsupported(PaymentOperation.CREATE)

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        raise self._unsupported(PaymentOperation.CREATE)

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
        raise self._unsupported(PaymentOperation.VERIFY)
