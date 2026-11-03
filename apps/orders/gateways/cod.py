"""Cash on Delivery (پرداخت در محل) adapter.

COD is modeled as a gateway adapter for uniform dispatch — checkout code
doesn't need gateway-specific conditionals. However, COD differs from
online gateways:

- No external API calls
- No redirect
- No server-to-server verification
- Order is NOT marked as paid immediately — it remains in payment_status=PENDING
  (or a COD-specific status) until delivery confirmation
- No credentials required

The adapter's create_payment returns a result with a synthetic track_id
(the payment attempt's own public_id) and no redirect URL. The checkout
service uses the is_online=False signal to skip the redirect flow entirely.
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


class CodAdapter(PaymentGatewayAdapter):
    """Cash on Delivery adapter — no external API, no redirect."""

    @property
    def code(self) -> str:
        return "cod"

    @property
    def display_name(self) -> str:
        return "پرداخت در محل"

    @property
    def is_online(self) -> bool:
        return False

    @property
    def required_credentials(self) -> list[str]:
        return []

    @property
    def onboarding_help(self) -> str:
        return "پرداخت در محل نیازی به اعتبارنامه ندارد — فقط فعال کنید. مبلغ هنگام تحویل دریافت می‌شود."

    @property
    def category(self) -> GatewayCategory:
        # Cash on delivery: no online money movement at all.
        return GatewayCategory.OFFLINE

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        # COD performs no online operations. An empty capability set makes it
        # explicit that CREATE/VERIFY here are offline bookkeeping, not
        # server-to-server gateway calls.
        return frozenset()

    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """COD requires no credentials — always valid."""
        return []

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
        """Record a COD payment selection.

        No external call is made. Returns a synthetic track_id.
        """
        logger.info("COD payment selected: order=%s amount=%s", order_code, amount)
        return PaymentCreationResult(
            track_id=f"cod-{order_code}",
            gateway_url=None,  # No redirect for COD
        )

    def build_redirect_url(self, track_id: str, *, sandbox: bool = False) -> str:
        """COD has no redirect URL — this should never be called in normal flow."""
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
        """COD verification is a no-op — payment is confirmed at delivery.

        This returns success=False because COD should NOT mark orders as
        paid at checkout time. The actual payment confirmation happens
        through the order status transition (DELIVERED).
        """
        return PaymentVerificationResult(
            success=False,
            message="پرداخت در محل — تأیید پس از تحویل",
        )
