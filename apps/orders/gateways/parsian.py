"""Parsian / PEC (پارسیان / پک) PSP adapter — DOCUMENTATION_BLOCKED skeleton.

Parsian e-Commerce (PEC), historically a SOAP/WSDL IPG. The official current
documentation (https://pec.ir/) was NOT reachable from this environment during
the FEAT-004 research pass (2026-11-03). The current protocol (SOAP vs REST),
token create/confirm/reverse endpoints and WSDL, pin/auth scheme, currency unit,
error codes, and sandbox are therefore NOT verified from an official source.

Rather than invent a SOAP envelope or endpoint, this adapter registers, declares
its real category (PSP) and ``documentation_blocked = True`` so the readiness
derivation surfaces DOCUMENTATION_BLOCKED and it is NEVER selectable at real
(non-sandbox) checkout. It declares NO capabilities and raises
``GatewayUnsupportedOperationError`` from every money-moving method. When the
official WSDL/contract becomes reachable, implement a maintainable tested client
(requests-based SOAP envelope or stdlib) and verify token create/confirm/reverse
before declaring any capability.
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


class ParsianAdapter(PaymentGatewayAdapter):
    """Parsian / PEC PSP adapter (documentation-blocked skeleton)."""

    @property
    def code(self) -> str:
        return "parsian"

    @property
    def display_name(self) -> str:
        return "بانک پارسیان"

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
        # PEC merchants hold a "LoginAccount" (pin) credential. Field name only.
        return ["login_account"]

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        errors = []
        if not (credentials.get("login_account") or "").strip():
            errors.append("پین پذیرنده (LoginAccount) الزامی است")
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
