"""Mellat / Behpardakht (ملت / به‌پرداخت) PSP adapter — DOCUMENTATION_BLOCKED skeleton.

Behpardakht Mellat, historically a SOAP IPG (``bpPayRequest`` family) with a
distinct request / verify / settle / inquiry / reversal lifecycle where SETTLE
(finalization) is a separate step from VERIFY. The official current documentation
(https://www.behpardakht.com/) was NOT reachable from this environment during
the FEAT-004 research pass (2026-11-03): the host timed out.

Because the real contract (endpoints, terminalId/username/password auth,
verify vs settle vs reverse semantics, currency unit, error codes, sandbox) is
NOT verified from an official source, this adapter registers, declares its real
category (PSP) and ``documentation_blocked = True`` so the readiness derivation
surfaces DOCUMENTATION_BLOCKED and it is NEVER selectable at real (non-sandbox)
checkout. It declares NO capabilities and raises
``GatewayUnsupportedOperationError`` from every money-moving method. The correct
settle (finalization) semantics must be implemented as a distinct SETTLE
capability — never conflated with verify — once the official contract is read.
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


class MellatAdapter(PaymentGatewayAdapter):
    """Behpardakht Mellat PSP adapter (documentation-blocked skeleton)."""

    @property
    def code(self) -> str:
        return "mellat"

    @property
    def display_name(self) -> str:
        return "بانک ملت (به‌پرداخت)"

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
        # Behpardakht merchants hold terminalId + username + password. Field
        # names only; asserts nothing about the unverified request contract.
        return ["terminal_id", "username", "password"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("terminal_id") or "").strip():
            errors.append("شناسه‌ی پایانه (terminalId) الزامی است")
        if not (credentials.get("username") or "").strip():
            errors.append("نام کاربری پذیرنده الزامی است")
        if not (credentials.get("password") or "").strip():
            errors.append("گذرواژه‌ی پذیرنده الزامی است")
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
