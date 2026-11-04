"""Tejarat (تجارت) PSP adapter — DOCUMENTATION_BLOCKED skeleton (special handling).

IMPORTANT — display label vs technical identity:
    "Tejarat" here is a STOREFRONT DISPLAY LABEL (associated with Bank Tejarat).
    The actual PSP that technically processes/settles the transaction is a
    SEPARATE question. IranKish (ایران‌کیش / https://irankish.com/) is a
    frequently associated PSP, but this adapter does NOT hardcode an
    IranKish↔Tejarat relationship: no official source confirming the mapping was
    reachable from this environment during the FEAT-004 research pass
    (2026-11-03) — both the IranKish site and any Tejarat IPG docs were
    unreachable (connection reset / timeout).

Because the real technical PSP, its endpoints, auth, currency unit, error codes,
signing, and sandbox are NOT verified from an official source, this adapter
registers, declares its real category (PSP) and ``documentation_blocked = True``
so the readiness derivation surfaces DOCUMENTATION_BLOCKED and it is NEVER
selectable at real (non-sandbox) checkout. It declares NO capabilities and
raises ``GatewayUnsupportedOperationError`` from every money-moving method. The
display label (``display_name``) is kept strictly separate from any future
technical PSP identity; the technical identity must be confirmed from an official
source before any capability is declared.
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


class TejaratAdapter(PaymentGatewayAdapter):
    """Tejarat (display label) PSP adapter (documentation-blocked skeleton)."""

    @property
    def code(self) -> str:
        return "tejarat"

    @property
    def display_name(self) -> str:
        # Storefront display label ONLY — not an assertion of the technical PSP.
        return "بانک تجارت"

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
        # Generic terminal id field name only; the real credential set depends
        # on the (unconfirmed) technical PSP and must be set once verified.
        return ["terminal_id"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("terminal_id") or "").strip():
            errors.append("شناسه‌ی پایانه الزامی است")
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
