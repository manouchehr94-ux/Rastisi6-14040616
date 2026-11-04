"""Abstract gateway adapter contract.

Every payment gateway adapter must implement this interface. The contract is
deliberately minimal and focused on the payment lifecycle:

1. validate_credentials — can this config initiate payments?
2. create_payment      — server-to-server request to create a payment session
3. build_redirect_url  — where to send the customer's browser
4. verify_payment      — server-to-server verification after callback

Adapters must:
- Never log credentials or sensitive customer data
- Always use explicit timeouts for external HTTP calls
- Return structured results (dataclasses below), never raw dicts/responses
- Raise GatewayError subclasses for all failure modes
- Never modify Order/PaymentAttempt state directly (caller's responsibility)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Capability + category declarations (M1 additive extension)
# ---------------------------------------------------------------------------


class PaymentOperation(str, Enum):
    """Operations a gateway adapter may declare support for.

    CREATE and VERIFY are the baseline operations every online adapter must
    support (they map to the original abstract ``create_payment`` /
    ``verify_payment`` contract). The remaining operations are optional and
    capability-gated: an adapter declares them in ``capabilities`` ONLY when
    the provider's official documentation specifies the operation. Declaring a
    capability without a real implementation is a bug — the default
    implementations below raise ``GatewayUnsupportedOperationError``.
    """

    CREATE = "create"      # Create a payment session (server-to-server)
    VERIFY = "verify"      # Authoritative server-to-server verification
    INQUIRE = "inquire"    # Query the current status of a payment
    CANCEL = "cancel"      # Cancel/void a not-yet-settled payment
    REFUND = "refund"      # Refund a settled payment (full/partial)
    SETTLE = "settle"      # Explicitly settle/capture an authorized payment


class GatewayCategory(str, Enum):
    """Business category of a payment provider.

    PSP         — bank-connected payment service provider (IPG).
    FACILITATOR — payment facilitator / aggregator riding on top of PSPs.
    BNPL        — buy-now-pay-later / installment provider.
    OFFLINE     — no online money movement (e.g. cash on delivery).
    """

    PSP = "psp"
    FACILITATOR = "facilitator"
    BNPL = "bnpl"
    OFFLINE = "offline"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentCreationResult:
    """Result of a successful create_payment call."""

    track_id: str  # Gateway's tracking/session identifier
    gateway_url: str | None = None  # If gateway returns redirect URL directly
    extra: dict | None = None  # Any additional gateway-specific data


@dataclass(frozen=True)
class PaymentVerificationResult:
    """Result of a successful verify_payment call."""

    success: bool
    ref_id: str = ""  # Bank reference number (for successful payments)
    card_number: str = ""  # Masked card number (if provided by gateway)
    status_code: int = 0  # Gateway-specific status code
    message: str = ""  # Human-readable status message


@dataclass(frozen=True)
class PaymentInquiryResult:
    """Result of an inquire_payment call (status query).

    ``settled`` mirrors the provider's authoritative state. ``status`` is a
    free-form provider status token (kept for evidence); callers must map it
    through the adapter, never interpret raw provider tokens elsewhere.
    """

    paid: bool
    settled: bool = False
    ref_id: str = ""
    status: str = ""
    status_code: int = 0
    message: str = ""
    #: True ONLY when the provider's authoritative status proves the payment will not complete (e.g. CANCEL / REVERT).
    #: A merely "not paid yet" / pending / unknown status is NOT terminal and must never be treated as a failure.
    terminal_negative: bool = False


@dataclass(frozen=True)
class PaymentRefundResult:
    """Result of a refund_payment call.

    ``amount`` is expressed in the same unit the adapter was asked to refund
    (Toman at the service boundary). ``pending`` is True when the provider
    accepted the refund but has not yet confirmed settlement of the reversal.
    """

    success: bool
    refund_ref: str = ""
    amount: Decimal | None = None
    pending: bool = False
    status_code: int = 0
    message: str = ""


@dataclass(frozen=True)
class PaymentCancelResult:
    """Result of a cancel_payment call (void of a not-yet-settled payment)."""

    success: bool
    status_code: int = 0
    message: str = ""


@dataclass(frozen=True)
class PaymentSettleResult:
    """Result of a settle_payment call (explicit capture/settlement)."""

    success: bool
    settle_ref: str = ""
    status_code: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class GatewayError(Exception):
    """Base exception for all gateway adapter errors.

    IMPORTANT: Never include credentials, full card numbers, or customer PII
    in error messages. These exceptions may be logged and their messages may
    appear in admin UI (though never in customer-facing pages).
    """

    def __init__(self, message: str, code: str = "", details: dict | None = None):
        super().__init__(message)
        self.code = code  # Machine-readable error code
        self.details = details or {}  # Safe-to-log additional context


class GatewayConnectionError(GatewayError):
    """Network-level failure (timeout, DNS, connection refused)."""


class GatewayResponseError(GatewayError):
    """Gateway returned an unexpected or malformed response."""


class GatewayPaymentError(GatewayError):
    """Gateway explicitly rejected the payment request."""


class GatewayVerificationError(GatewayError):
    """Verification failed — payment should NOT be marked successful."""


class GatewayAmountMismatchError(GatewayVerificationError):
    """The gateway CONFIRMED a payment, but for a different amount than the order expects.

    Money has moved (the gateway said so), so this is not an ordinary verification failure: the
    caller must preserve ``details["evidence"]`` (reported/expected Rial, ref id, masked card) in a
    ``PaymentReconciliation`` and must NOT mark the order paid."""


class GatewayCredentialError(GatewayError):
    """Credentials are invalid, expired, or missing."""


class GatewayUnsupportedOperationError(GatewayError):
    """The adapter does not declare support for the requested operation.

    Raised by the DEFAULT implementations of the optional capability-gated
    methods (inquire/cancel/refund/settle). An unsupported financial operation
    must NEVER be silently emulated — the caller gets an explicit error so it
    can fall back to a manual/offline workflow instead of pretending money
    moved. ``code`` carries the attempted :class:`PaymentOperation` value.
    """


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class PaymentGatewayAdapter(ABC):
    """Abstract base class for payment gateway adapters.

    Each adapter instance is stateless and can be reused across requests.
    Configuration (merchant ID, etc.) is passed per-call from the
    PaymentGatewayConfig model, never stored on the adapter instance.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Unique gateway code matching GATEWAY_CHOICES and PaymentGatewayConfig.gateway_code."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Persian display name for admin/checkout UI."""

    @property
    @abstractmethod
    def is_online(self) -> bool:
        """True for online payment gateways, False for offline (COD)."""

    @property
    def requires_manual_confirmation(self) -> bool:
        """True when the payment is confirmed by a human (card-to-card): the attempt stays PENDING until an admin approves."""
        return False

    @property
    def credential_fields(self) -> list[dict]:
        """Field metadata for the admin form. Default: every required credential is a secret (password-type) field."""
        labels = self.credential_labels or {}
        return [{"name": n, "label": labels.get(n, n), "secret": True, "ltr": True} for n in self.required_credentials]

    def field_errors(self, credentials: dict[str, str]) -> dict[str, str]:
        """``validate_credentials`` mapped to the form field each message belongs to (``""`` = a message about the whole form).

        Lets the admin page show the error under the exact input. Default: with a single required credential every error belongs to it."""
        errors = self.validate_credentials(credentials)
        if not errors:
            return {}
        required = self.required_credentials
        if len(required) == 1:
            return {required[0]: " ".join(errors)}
        return {"": " ".join(errors)}

    @property
    def redirect_host_suffixes(self) -> tuple[str, ...]:
        """Registrable host suffixes the customer may be redirected to for this provider (live mode).

        Empty = no provider-specific allowlist (the redirect must still be a plain HTTPS URL without credentials).
        A provider response can never send the customer to an arbitrary external host."""
        return ()

    @property
    def auto_collects_offline(self) -> bool:
        """For an offline method (``is_online`` False), whether selecting the
        method at checkout already constitutes collected money.

        The two offline methods look identical on ``is_online`` and
        ``capabilities`` (both empty), yet they have OPPOSITE bookkeeping:

        * Cash on Delivery collects the money physically when the courier
          hands over the goods. Selecting COD is a firm commitment to pay on
          delivery, so the attempt is recorded SUCCEEDED at selection time
          (the order still stays PENDING until delivery confirmation).
        * Manual card-to-card moves money fully out of band. A customer who
          picks card-to-card (or even uploads a receipt) has NOT proven any
          money arrived; only an authorized merchant confirming the transfer
          does. So the attempt must stay PENDING at selection.

        This explicit, documentation-backed flag lets the orchestrator branch
        on an adapter capability instead of string-matching a gateway code.
        The name reads as a predicate on the attempt row: does picking this
        offline method auto-record collected money? Default True preserves the
        historical COD behavior for any offline adapter that does not override
        it; card-to-card overrides it to False. It is meaningless (and ignored)
        for online adapters, which never take the offline branch.
        """
        return True

    @property
    def required_credentials(self) -> list[str]:
        """List of credential field names required for this gateway.

        Used by admin UI to validate configuration completeness.
        Default: empty (no credentials needed, e.g., COD).
        """
        return []

    # --- Capability + category declarations (additive, non-abstract) --------

    @property
    def capabilities(self) -> frozenset[PaymentOperation]:
        """The set of operations this adapter actually supports.

        An adapter MUST only list an operation here if it has a real,
        documentation-backed implementation. The default is the baseline for
        an online gateway (CREATE + VERIFY). Offline adapters override this to
        an empty set. Capability declarations drive readiness derivation and
        which optional methods the orchestrator is allowed to call.
        """
        return frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY})

    @property
    def category(self) -> GatewayCategory:
        """Business category of this provider (PSP/FACILITATOR/BNPL/OFFLINE)."""
        return GatewayCategory.FACILITATOR

    @property
    def documentation_blocked(self) -> bool:
        """True when the provider's official current contract is unverifiable.

        A documentation-blocked adapter must not be selectable at real
        (non-sandbox) checkout. Default False; providers whose official docs
        are unreachable/incomplete override this to True so readiness
        derivation can surface DOCUMENTATION_BLOCKED. Keeps the checkout code
        free of provider conditionals.
        """
        return False

    def supports(self, operation: PaymentOperation) -> bool:
        """Convenience check: does this adapter declare ``operation``?"""
        return operation in self.capabilities

    # --- Admin-UI presentation metadata (additive, non-abstract) ------------

    @property
    def supports_sandbox(self) -> bool:
        """Whether a genuine sandbox/test mode exists for this provider.

        Drives whether the admin finance UI offers a sandbox toggle. Default:
        online adapters that are not documentation-blocked may expose sandbox.
        Offline adapters and documentation-blocked skeletons have no real
        sandbox, so the toggle is hidden for them. Adapters with no verified
        sandbox host override this to ``False``.
        """
        return self.is_online and not self.documentation_blocked

    @property
    def credential_labels(self) -> dict[str, str]:
        """Optional Persian labels for credential fields.

        Maps a ``required_credentials`` key to a human-readable Persian label
        for the admin form. Missing keys fall back to the raw key name. Keeps
        provider-specific field wording inside the adapter (no view
        conditionals).
        """
        return {}

    @property
    def onboarding_help(self) -> str:
        """Persian merchant onboarding help text shown in the admin finance UI.

        Explains, per provider, where to obtain credentials and any readiness
        caveats. Default empty (the UI falls back to a generic note).
        """
        return ""

    @abstractmethod
    def validate_credentials(self, credentials: dict[str, str]) -> list[str]:
        """Validate that credentials are sufficient for this gateway.

        Args:
            credentials: Decrypted credential dict from PaymentGatewayConfig.

        Returns:
            List of validation error messages (empty = valid).
            Never includes the actual credential values in error messages.
        """

    @abstractmethod
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
        cart_items: list[dict] | None = None,
        cart_totals: dict | None = None,
    ) -> PaymentCreationResult:
        """Create a payment session with the gateway.

        Args:
            amount: Payment amount in the currency unit stored in the database.
            currency: Currency code (e.g., "TOMAN").
            callback_url: Full URL the gateway should redirect to after payment.
            credentials: Decrypted credential dict.
            order_code: Order identifier for the gateway's records.
            description: Optional payment description.
            sandbox: Whether to use sandbox/test mode.
            cart_items: Optional authoritative per-line order snapshot used by
                itemized providers (BNPL: SnappPay/TorobPay) to build a real
                cartList that reconciles EXACTLY to the order amount. Each entry
                is an immutable dict in TOMAN with keys:
                ``id`` (product id or sku), ``name`` (product_name),
                ``count`` (quantity), ``unit_amount`` (unit_price),
                ``line_amount`` (unit_price * quantity),
                ``discount_allocation`` and ``total_tax``; plus, as the first
                allowed convention, order-level totals are forwarded via the
                ``cart_totals`` companion argument.
                Defaults to None so non-itemized adapters (PSPs, offline) and
                every existing call site/test keep working unchanged. A
                non-itemized adapter simply ignores it (or never receives it).
            cart_totals: Optional order-level TOMAN scalars that accompany
                ``cart_items`` for itemized providers. Keys: ``grand_total``
                (int, must equal the order amount), ``shipping`` (shipping_cost),
                ``shipping_tax``, ``tax`` (line tax added to the grand total,
                already 0 when prices are tax-inclusive), ``gift_wrap`` and
                ``discount`` (total coupon discount). The adapter allocates
                these to the documented cartList-level fields so that the built
                cartList reconciles EXACTLY to the Rial grand total. Defaults to
                None.

        Returns:
            PaymentCreationResult with track_id and optional redirect URL.

        Raises:
            GatewayConnectionError: Network failure.
            GatewayResponseError: Malformed/unexpected response.
            GatewayPaymentError: Gateway rejected the request.
            GatewayCredentialError: Invalid credentials.
        """

    @abstractmethod
    def build_redirect_url(
        self,
        track_id: str,
        *,
        sandbox: bool = False,
    ) -> str:
        """Build the URL to redirect the customer's browser to.

        Args:
            track_id: The tracking identifier from create_payment result.
            sandbox: Whether to use sandbox/test mode URL.

        Returns:
            Full URL string for browser redirect.
        """

    @abstractmethod
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
        """Verify a payment after callback.

        This is the authoritative server-to-server verification. A browser
        callback parameter alone NEVER proves payment success.

        Args:
            track_id: The tracking identifier from the payment attempt.
            expected_amount: The amount we expect (from our database, not browser).
            currency: Currency code.
            credentials: Decrypted credential dict.
            callback_data: Data received in the callback (query params, etc.).
            sandbox: Whether sandbox mode.

        Returns:
            PaymentVerificationResult indicating success/failure.

        Raises:
            GatewayConnectionError: Network failure during verification.
            GatewayResponseError: Malformed verification response.
            GatewayVerificationError: Verification explicitly failed.
        """

    # -----------------------------------------------------------------------
    # Optional capability-gated operations (M1 additive extension)
    #
    # These are NOT @abstractmethod on purpose: existing adapters (zibal, cod)
    # must keep instantiating without change. The default implementations
    # raise GatewayUnsupportedOperationError so an undeclared operation can
    # never be silently emulated. An adapter enables one of these by (a)
    # listing the matching PaymentOperation in ``capabilities`` AND
    # (b) overriding the method with a real, documentation-backed body.
    # -----------------------------------------------------------------------

    def _unsupported(self, operation: PaymentOperation) -> GatewayUnsupportedOperationError:
        return GatewayUnsupportedOperationError(
            f"درگاه «{self.display_name}» از عملیات «{operation.value}» پشتیبانی نمی‌کند.",
            code=operation.value,
            details={"gateway": self.code, "operation": operation.value},
        )

    def inquire_payment(
        self,
        *,
        track_id: str,
        expected_amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentInquiryResult:
        """Query the current status of a payment (optional capability).

        Default: raise GatewayUnsupportedOperationError. Override only when the
        provider documents a status-inquiry endpoint and INQUIRE is declared in
        ``capabilities``.
        """
        raise self._unsupported(PaymentOperation.INQUIRE)

    def cancel_payment(
        self,
        *,
        track_id: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentCancelResult:
        """Cancel/void a not-yet-settled payment (optional capability).

        Default: raise GatewayUnsupportedOperationError. Override only when the
        provider documents a cancel/void endpoint and CANCEL is declared.
        """
        raise self._unsupported(PaymentOperation.CANCEL)

    def refund_payment(
        self,
        *,
        track_id: str,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        reason: str = "",
        sandbox: bool = False,
    ) -> PaymentRefundResult:
        """Refund a settled payment, full or partial (optional capability).

        Default: raise GatewayUnsupportedOperationError. Override only when the
        provider documents a refund endpoint and REFUND is declared. A refund
        must never be faked — if unsupported, the caller falls back to the
        manual (out-of-band) refund workflow.
        """
        raise self._unsupported(PaymentOperation.REFUND)

    def settle_payment(
        self,
        *,
        track_id: str,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> PaymentSettleResult:
        """Explicitly settle/capture an authorized payment (optional capability).

        Default: raise GatewayUnsupportedOperationError. Override only when the
        provider documents a separate settle/capture step and SETTLE is
        declared.
        """
        raise self._unsupported(PaymentOperation.SETTLE)

    def check_bnpl_eligibility(
        self,
        *,
        amount: Decimal,
        currency: str,
        credentials: dict[str, str],
        customer: dict[str, Any] | None = None,
        sandbox: bool = False,
    ) -> dict[str, Any]:
        """BNPL eligibility hook (optional, BNPL category only).

        Default: raise GatewayUnsupportedOperationError. BNPL adapters override
        this to query installment eligibility. Non-BNPL adapters never
        implement it.
        """
        raise GatewayUnsupportedOperationError(
            f"درگاه «{self.display_name}» از اعتبارسنجی اقساطی (BNPL) پشتیبانی نمی‌کند.",
            code="bnpl_eligibility",
            details={"gateway": self.code},
        )
