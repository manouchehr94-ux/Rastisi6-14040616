"""Payment service — orchestrates real gateway payment lifecycle.

This service is the single entry point for:
1. Initiating a payment (online or COD)
2. Processing a gateway callback
3. Verifying and confirming a payment

It does NOT:
- Call gateway APIs directly (delegates to adapters)
- Modify Order status directly (delegates to order_service/payment_service)
- Resolve Store from request (caller's responsibility)
- Handle HTTP concerns (views' responsibility)

Concurrency guarantees:
- select_for_update on PaymentAttempt during verification
- Conditional status updates prevent double-processing
- Idempotency keys prevent duplicate attempts
- Already-paid order check prevents re-payment

State ownership:
- PaymentAttempt.status: owned by this service
- Order.payment_status: updated by this service on successful verification
- Order.status: transitions delegated to order_service.change_order_status
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import timedelta
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.orders.encryption import CredentialEncryptionError
from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayConnectionError,
    GatewayError,
    GatewayResponseError,
    PaymentOperation,
    PaymentVerificationResult,
)
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGatewayConfig,
    PaymentReconciliation,
    PaymentTransactionEvent,
    Transaction,
)

logger = logging.getLogger("payment")

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PaymentServiceError(Exception):
    """Base for payment service errors — safe message for logs/admin."""


class PaymentAlreadyPaidError(PaymentServiceError):
    """Order is already paid."""


class OrderNotPayableError(PaymentServiceError):
    """Order can no longer be paid (e.g. it was canceled)."""


class PaymentConfigError(PaymentServiceError):
    """Gateway configuration is invalid or incomplete."""


class PaymentInitiationError(PaymentServiceError):
    """Failed to initiate payment with gateway."""


class PaymentInitiationInProgress(PaymentServiceError):
    """Another request is currently preparing the payment for this exact operation.

    Raised instead of returning a CREATED/REQUESTING attempt that has no
    payment URL yet. The caller must show a "being prepared, retry shortly"
    outcome; it must NOT redirect and must NOT call the gateway again.
    """


class PaymentSettlementUnresolved(PaymentServiceError):
    """A previous attempt of this order verified at the provider but its settlement outcome is still unknown.

    Money may already have moved: no NEW chargeable operation may be started for the order until the unresolved attempt
    is reconciled (provider inquiry / administrative resolution)."""


class PaymentVerificationFailed(PaymentServiceError):
    """Verification failed — order not marked paid."""


class PaymentAmountMismatch(PaymentVerificationFailed):
    """Gateway confirmed a payment for a different amount: evidence kept, order NOT marked paid."""


# ---------------------------------------------------------------------------
# Itemized (BNPL) cart snapshot
# ---------------------------------------------------------------------------


def build_order_cart_snapshot(order: Order) -> tuple[list[dict], dict]:
    """Build an authoritative, immutable per-line cart snapshot for itemized
    (BNPL) providers plus the order-level totals needed to reconcile it.

    Amounts are kept in TOMAN here; the adapter performs the single
    Toman -> Rial x10 conversion. Every value is read from the order's own
    historical snapshot fields (OrderItem + Order money fields), never
    recomputed, so later catalog/price changes can never alter it.

    Returns a ``(cart_items, cart_totals)`` tuple where:
      * ``cart_items`` is one dict per :class:`OrderItem` with ``id``
        (product id or sku), ``name`` (product_name), ``count`` (quantity),
        ``unit_amount`` (unit_price), ``line_amount`` (line_total, gross),
        ``discount_allocation`` and ``total_tax``.
      * ``cart_totals`` carries the order-level TOMAN scalars. All Order money
        fields have 0 decimal places (integer TOMAN), so the following identity
        is EXACT with no rounding residual::

            grand_total = items_total + gift_wrap_total + shipping_cost
                          + tax_added - coupon_discount

        where ``tax_added = (0 if prices_include_tax else order.tax)
        + order.shipping_tax`` (line tax is already inside the line amounts when
        prices are tax-inclusive). ``sum(line_amount)`` equals ``items_total``.
    """
    cart_items: list[dict] = []
    for item in order.items.all().order_by("pk"):
        # id = real product identifier (product id) or the sku snapshot; never
        # fabricated. Falls back to the sku when the product row was later
        # SET_NULL, and finally to the order code so the id is always present.
        identifier = (
            str(item.product_id) if item.product_id
            else (item.sku or f"{order.code}-{item.pk}")
        )
        cart_items.append(
            {
                "id": identifier,
                "name": item.product_name,
                "count": int(item.quantity),
                "unit_amount": int(item.unit_price),
                "line_amount": int(item.line_total),
                "discount_allocation": int(item.discount_allocation or 0),
                "total_tax": int(item.total_tax or 0),
            }
        )

    # Line tax is already folded into the line amounts when prices are
    # tax-inclusive, so it must NOT be added again at the cart level.
    tax_added = (0 if order.prices_include_tax else int(order.tax)) + int(order.shipping_tax)
    cart_totals = {
        "grand_total": int(order.grand_total),
        "items_total": int(order.items_total),
        "shipping": int(order.shipping_cost),
        "shipping_tax": int(order.shipping_tax),
        "tax": tax_added,
        "gift_wrap": int(order.gift_wrap_total),
        "gift_wrap_discount": int(order.gift_wrap_discount),
        "discount": int(order.coupon_discount),
    }
    return cart_items, cart_totals


# ---------------------------------------------------------------------------
# Redirect safety
# ---------------------------------------------------------------------------


def is_safe_gateway_redirect(url: str, adapter, *, sandbox: bool = False) -> bool:
    """A provider-supplied payment-page URL is followed only if it is a plain HTTPS URL (no userinfo, no control chars) and,
    in live mode, its host belongs to one of the adapter's declared provider domains. Never trust an arbitrary external host."""
    from urllib.parse import urlsplit

    url = (url or "").strip()
    if not url or any(ord(ch) < 32 or ch in "\\ " for ch in url):
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or not host or parts.username is not None or parts.password is not None:
        return False
    suffixes = tuple(getattr(adapter, "redirect_host_suffixes", ()) or ())
    # Ops override for providers whose payment-page domain the contract does not name (or that moved it): settings
    # PAYMENT_REDIRECT_EXTRA_HOST_SUFFIXES = {"<gateway_code>": ("example.ir",)} widens (never replaces) the declared list.
    extra = (getattr(settings, "PAYMENT_REDIRECT_EXTRA_HOST_SUFFIXES", {}) or {}).get(getattr(adapter, "code", ""), ())
    suffixes = suffixes + tuple(s.lower() for s in extra)
    if suffixes and not sandbox:
        return any(host == s or host.endswith("." + s) for s in suffixes)
    return True


# ---------------------------------------------------------------------------
# In-flight (CREATED/REQUESTING) attempt handling
# ---------------------------------------------------------------------------

#: A concurrent caller that meets an in-flight attempt polls this many times,
#: this many seconds apart (bounded, ~0.6s total) BEFORE giving up with
#: PaymentInitiationInProgress. Never inside a transaction / row lock.
INFLIGHT_POLL_TRIES = 3
INFLIGHT_POLL_INTERVAL = 0.2
#: Default staleness window. Adapter HTTP timeouts are (connect=10, read=30),
#: so anything older than this was abandoned (crashed worker / lost request).
DEFAULT_INFLIGHT_STALE_SECONDS = 180

_IN_FLIGHT_STATUSES = (
    PaymentAttempt.Status.CREATED,
    PaymentAttempt.Status.REQUESTING,
)
_READY_STATUSES = (
    PaymentAttempt.Status.REDIRECT_READY,
    PaymentAttempt.Status.PENDING,
)


def is_attempt_in_flight(attempt: PaymentAttempt) -> bool:
    """True when the attempt cannot (yet) be used to send the customer anywhere.

    CREATED/REQUESTING are in flight by definition. A REDIRECT_READY/PENDING
    attempt that carries neither a persisted redirect URL nor a track id is
    treated the same way: it must never be returned as redirect-ready.
    """
    if attempt.status in _IN_FLIGHT_STATUSES:
        return True
    if attempt.status in _READY_STATUSES:
        return not ((attempt.gateway_redirect_url or "").strip() or (attempt.gateway_track_id or "").strip())
    return False


def _inflight_stale_after() -> timedelta:
    return timedelta(seconds=int(getattr(settings, "PAYMENT_INFLIGHT_STALE_SECONDS", DEFAULT_INFLIGHT_STALE_SECONDS)))


def _expire_if_stale(attempt: PaymentAttempt) -> bool:
    """Conditionally retire an abandoned in-flight attempt. Returns True if retired.

    The provider create call is NOT idempotent, so we never re-call it for the
    same attempt. The abandoned attempt is moved to EXPIRED with a distinctive
    failure_code (flag for operators / reconciliation); the customer was never
    given a payment URL for it, so a fresh attempt cannot double-charge. A late
    gateway callback for it is still verified by process_callback_and_verify.
    """
    cutoff = timezone.now() - _inflight_stale_after()
    if attempt.updated_at is None or attempt.updated_at > cutoff:
        return False
    updated = PaymentAttempt.objects.filter(
        pk=attempt.pk,
        status=attempt.status,
        updated_at__lte=cutoff,
    ).update(
        status=PaymentAttempt.Status.EXPIRED,
        failure_code="initiation_stale",
        failure_message="درخواست پرداخت در درگاه بیش از حد مجاز بیپاسخ ماند",
        updated_at=timezone.now(),
    )
    if updated:
        logger.error(
            "Stale in-flight payment attempt expired: order_id=%s attempt=%s status=%s",
            attempt.order_id, attempt.public_id, attempt.status,
        )
    return bool(updated)


# ---------------------------------------------------------------------------
# Initiate payment
# ---------------------------------------------------------------------------


def initiate_payment(
    *,
    order: Order,
    gateway_config: PaymentGatewayConfig,
    callback_url: str,
    store,
    idempotency_key: str = "",
    pre_public_id: str = "",
) -> PaymentAttempt:
    """Create a PaymentAttempt and (for online gateways) request payment from gateway.

    Args:
        order: The finalized order to pay for.
        gateway_config: The active, configured gateway to use.
        callback_url: Full URL for gateway to redirect back to.
        store: Authoritative store instance.
        idempotency_key: Optional key to prevent duplicate attempts.
        pre_public_id: Optional pre-generated public_id (allows caller to build
                       the callback URL before the attempt is created).

    Returns:
        PaymentAttempt in REDIRECT_READY (online) or SUCCEEDED (COD) state.

    Raises:
        PaymentAlreadyPaidError: Order already paid.
        PaymentConfigError: Gateway not configured properly.
        PaymentInitiationError: Gateway rejected the request.
    """
    # Guard: re-read the authoritative state (the caller's object may be stale — e.g. the order was
    # canceled by staff or by the expiry job while the customer was on the payment page).
    current = Order.objects.filter(pk=order.pk).values("status", "payment_status").first()
    if current is not None:
        order.status, order.payment_status = current["status"], current["payment_status"]
    if order.status == Order.Status.CANCELED:
        raise OrderNotPayableError("این سفارش لغو شده و قابل پرداخت نیست")
    if order.payment_status == Order.PaymentStatus.PAID:
        raise PaymentAlreadyPaidError("این سفارش قبلاً پرداخت شده است")

    # Guard: gateway config belongs to this store
    if gateway_config.store_id != store.pk:
        raise PaymentConfigError("پیکربندی درگاه متعلق به این فروشگاه نیست")

    # Guard: gateway is active and configured
    if not gateway_config.is_active:
        raise PaymentConfigError("درگاه پرداخت غیرفعال است")
    if not gateway_config.is_configured:
        raise PaymentConfigError("پیکربندی درگاه ناقص است")

    # Guard: readiness. A DOCUMENTATION_BLOCKED / not-ready provider must never
    # be routed to a real payment (single source of truth = readiness_status;
    # no per-gateway conditionals). Offline (COD/card-to-card) is CONNECTED once
    # configured, so this does not disturb offline methods.
    R = PaymentGatewayConfig.ReadinessStatus
    readiness = gateway_config.readiness_status
    ready = readiness == R.CONNECTED or (
        readiness == R.READY_FOR_TEST and gateway_config.is_sandbox
    )
    if not ready:
        if readiness == R.DOCUMENTATION_BLOCKED:
            raise PaymentConfigError(
                "قرارداد رسمی این درگاه تأیید نشده و برای پرداخت واقعی در دسترس نیست."
            )
        raise PaymentConfigError("درگاه پرداخت برای پرداخت واقعی آماده نیست.")

    # An earlier attempt of this order that verified at the provider but whose settlement outcome is unknown may already
    # have moved the customer's money. Never open a second chargeable operation (any provider) until it is reconciled.
    if _has_unresolved_settlement(order, store):
        raise PaymentSettlementUnresolved("پرداختِ قبلی این سفارش در حال بررسی است؛ تا روشن‌شدن نتیجه پرداخت تازه‌ای آغاز نمی‌شود.")

    # Manual, merchant-reviewed methods (card-to-card) have exactly ONE financial authority: the canonical
    # CardTransferSubmission workflow (customer receipt -> merchant approve/reject). It owns the PENDING attempt.
    try:
        _adapter_for_routing = get_adapter(gateway_config.gateway_code)
    except KeyError as exc:
        raise PaymentConfigError(f"کد درگاه نامعتبر: {gateway_config.gateway_code}") from exc
    if getattr(_adapter_for_routing, "requires_manual_confirmation", False) is True:
        from apps.orders.services.card_transfer_service import ensure_attempt

        return ensure_attempt(order, gateway_config)
    if getattr(_adapter_for_routing, "is_online", True) is False and getattr(_adapter_for_routing, "auto_collects_offline", True) is not True:
        # An offline method that is neither COD nor the canonical manual workflow has no defined finalization path here.
        raise PaymentConfigError("این روش پرداخت آفلاین پشتیبانی نمی‌شود.")

    # Idempotency + concurrency guard.
    #
    # The dedupe lookup is scoped by the FULL operation identity
    # (store, order, gateway_config, amount) in ADDITION to the key — never by
    # the key alone. This closes two holes:
    #   * tenant/operation isolation: a reused key that was created for a
    #     different store/order/gateway/amount is treated as a NON-match and is
    #     never returned, so one tenant can never receive another tenant's (or
    #     another order/gateway/amount's) attempt.
    #   * single external charge: an existing matching attempt that is already
    #     live/redirect-ready/succeeded (i.e. the gateway was already engaged)
    #     is returned WITHOUT calling the gateway again.
    #
    # Concurrency is serialized with select_for_update on the Order row: two
    # parallel requests for the SAME operation cannot both pass the check and
    # both create an attempt / both charge. The first request creates the
    # attempt (and makes the one external create_payment call) while holding
    # the row lock; the second blocks, then finds the existing live attempt and
    # returns it without charging again. The deterministic idempotency key
    # (built by the view from the same identity) plus the existing partial
    # unique(idempotency_key) constraint is the backstop even across separate
    # DB sessions, so NO new broad constraint (which would break legitimate
    # multi-attempt retry history) is introduced.
    #
    # Statuses that mean "the gateway was already engaged for this operation"
    # and must therefore be reused rather than re-charged.
    _reusable_statuses = (
        PaymentAttempt.Status.CREATED,
        PaymentAttempt.Status.REQUESTING,
        PaymentAttempt.Status.REDIRECT_READY,
        PaymentAttempt.Status.PENDING,
        PaymentAttempt.Status.SUCCEEDED,
        PaymentAttempt.Status.VERIFIED,
        PaymentAttempt.Status.FINALIZED,
    )

    def _scoped_existing():
        """Return the latest reusable attempt for THIS exact operation, or None.

        Reuse is keyed on the operation identity (store, order, gateway_config,
        amount), NOT on the verbatim idempotency-key string: a retry after a
        failed attempt persists a DIFFERENT (disambiguated) key, so a key-based
        lookup would miss that live attempt and create a duplicate. The key is
        only a DB uniqueness backstop and audit value. Tenant isolation is kept
        because store/order/gateway/amount are all in the filter, so a foreign
        key or foreign attempt can never match.

        Terminal failures (FAILED/CANCELED/EXPIRED) are not in
        ``_reusable_statuses``, so a legitimate retry still creates a new
        attempt. SUCCEEDED/VERIFIED/FINALIZED are returned (never re-charged);
        an order that is actually PAID is rejected earlier with
        PaymentAlreadyPaidError.
        """
        return (
            PaymentAttempt.objects.filter(
                store=store,
                order=order,
                gateway_config=gateway_config,
                amount=order.grand_total,
                status__in=_reusable_statuses,
            )
            .order_by("-created_at", "-pk")
            .first()
        )

    def _usable_existing(*, wait: bool):
        """Existing attempt that is safe to hand back, else None (create new).

        * ready / succeeded attempt  -> returned.
        * in-flight (no URL yet)     -> optionally polled a bounded number of
          times (outside any lock); if it becomes ready it is returned, if it
          is abandoned (stale) it is retired and None is returned, otherwise
          PaymentInitiationInProgress is raised. create_payment is never
          called for an in-flight attempt.
        """
        tries = INFLIGHT_POLL_TRIES if wait else 0
        for i in range(tries + 1):
            existing = _scoped_existing()
            if existing is None:
                return None
            if not is_attempt_in_flight(existing):
                return existing
            if _expire_if_stale(existing):
                continue  # retired: look again (maybe an older reusable one)
            if i < tries:
                time.sleep(INFLIGHT_POLL_INTERVAL)
        raise PaymentInitiationInProgress("پرداخت در حال آمادهسازی است؛ چند لحظه بعد دوباره تلاش کنید")

    def _key_to_persist():
        """Pick a safe idempotency key for a NEW attempt.

        The caller's key is honored only when NO row holds it yet. The DB
        enforces a GLOBAL partial unique(idempotency_key), so persisting a key
        that any existing attempt already carries would raise an IntegrityError.
        Two distinct situations reach this point (a live, reusable attempt for
        this identity was already returned by ``_scoped_existing`` before we get
        here, so it is never one of these):

          * foreign reuse: the supplied key was minted for a DIFFERENT
            operation (another store/order/gateway/amount), or
          * legitimate retry: a PRIOR attempt for THIS SAME operation is already
            final (FAILED/CANCELED/EXPIRED) and still carries the key, so it is
            not reusable but the key is taken.

        In BOTH cases the verbatim key is unusable. We substitute a
        DETERMINISTIC key derived from this operation's identity; to let a retry
        after a failed attempt (whose dead row may already hold the base
        deterministic key) proceed, the key is disambiguated by the count of
        existing attempts for this identity. The result is stable for a given
        retry round and never collides with an existing row.
        """
        if not idempotency_key:
            return ""
        taken = (
            PaymentAttempt.objects.filter(idempotency_key=idempotency_key).exists()
        )
        if not taken:
            return idempotency_key
        attempts_so_far = PaymentAttempt.objects.filter(
            store=store, order=order,
            gateway_config=gateway_config, amount=order.grand_total,
        ).count()
        seed = (
            f"{store.pk}:{order.pk}:{gateway_config.pk}:"
            f"{order.grand_total}:{attempts_so_far}"
        )
        return f"pay-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:48]}"

    # Fast path outside the lock: if a matching live attempt already exists,
    # reuse it without opening a write transaction.
    existing = _usable_existing(wait=True)
    if existing is not None:
        return existing

    # Get adapter
    try:
        adapter = get_adapter(gateway_config.gateway_code)
    except KeyError as exc:
        raise PaymentConfigError(f"کد درگاه نامعتبر: {gateway_config.gateway_code}") from exc

    # Decrypt credentials
    try:
        credentials = gateway_config.get_credentials()
    except CredentialEncryptionError as exc:
        logger.error("Failed to decrypt credentials for config %d", gateway_config.pk)
        raise PaymentConfigError(
            "خطا در خواندن اعتبارنامه‌ی درگاه. لطفاً اعتبارنامه را دوباره وارد کنید."
        ) from exc

    # Create attempt record under an order-row lock so concurrent
    # same-operation requests serialize. The winner creates the attempt; a
    # loser that was blocked here re-checks inside the lock, finds the live
    # attempt the winner just created, and returns it without creating a second
    # attempt or making a second external create_payment call. On databases
    # without row-level locking (e.g. SQLite) select_for_update is a no-op, but
    # the deterministic key + partial unique(idempotency_key) constraint still
    # prevents a duplicate row from being committed.
    with transaction.atomic():
        order_locked = (
            Order.objects.select_for_update()
            .filter(pk=order.pk, store=store)
            .first()
        )
        if order_locked is None:
            # Order vanished or does not belong to this store — never create a
            # cross-tenant attempt.
            raise OrderNotPayableError("سفارش برای این فروشگاه یافت نشد")

        if _has_unresolved_settlement(order, store):
            raise PaymentSettlementUnresolved("پرداختِ قبلی این سفارش در حال بررسی است؛ تا روشن‌شدن نتیجه پرداخت تازه‌ای آغاز نمی‌شود.")

        # Re-check inside the lock: a concurrent winner may have just created a
        # live attempt for this exact operation. No waiting here: we hold the
        # order row lock and must never sleep / do network I/O under it.
        existing = _usable_existing(wait=False)
        if existing is not None:
            return existing

        attempt = PaymentAttempt(
            store=store,
            order=order,
            gateway_config=gateway_config,
            amount=order.grand_total,
            currency="TOMAN",
            status=PaymentAttempt.Status.CREATED,
            idempotency_key=_key_to_persist(),
        )
        if pre_public_id:
            attempt.public_id = pre_public_id
        try:
            # ``save`` runs in its own savepoint so a unique-key collision does
            # not poison the surrounding atomic block (the row lock is still
            # held, so _scoped_existing re-queries cleanly below).
            with transaction.atomic():
                attempt.save()
        except IntegrityError:
            # Backend-agnostic safety net for the idempotency-key race.
            #
            # On Postgres the select_for_update row lock already serializes
            # same-operation requests, so the loser re-queries and reuses the
            # winner's attempt before ever reaching this insert. On SQLite (and
            # any backend without real row-level locking) select_for_update is a
            # no-op, so two racing requests can both compute the SAME
            # deterministic fallback key and both try to insert it; the second
            # insert hits the partial unique(idempotency_key) constraint. Rather
            # than let that surface as an uncaught 500, we re-query the now
            # committed live attempt and reuse it — no second external
            # create_payment call is ever made. The partial unique constraint
            # guarantees at most one row is committed either way.
            existing = _usable_existing(wait=False)
            if existing is not None:
                return existing
            # The collision was with a row that is NOT a live attempt for this
            # exact identity (e.g. a dead prior attempt still holding the base
            # deterministic key). Mint a fresh disambiguated key and insert
            # again; _key_to_persist counts existing attempts, so the committed
            # racer shifts the count and yields a new, non-colliding key.
            attempt.idempotency_key = _key_to_persist()
            attempt.save()

    # Offline gateways never go through the online redirect/verify flow. Manual card-to-card was routed to the
    # canonical card-transfer workflow above, so the only offline method that reaches this point is COD
    # (auto_collects_offline=True): selecting it is a firm pay-on-delivery commitment, so the attempt is recorded
    # SUCCEEDED at selection with a cod- track id and a verified_at timestamp. The order itself is NOT marked paid —
    # it stays pending until delivery confirmation.
    if not adapter.is_online:
        if adapter.auto_collects_offline:
            attempt.status = PaymentAttempt.Status.SUCCEEDED
            attempt.gateway_track_id = f"cod-{order.code}"
            attempt.verified_at = timezone.now()
            attempt.save(update_fields=["status", "gateway_track_id", "verified_at", "updated_at"])
            # COD does NOT mark order as paid — it stays pending until delivery
            logger.info("COD payment recorded: order=%s attempt=%s", order.code, attempt.public_id)
            return attempt

    # Online gateway: request payment
    attempt.status = PaymentAttempt.Status.REQUESTING
    attempt.initiated_at = timezone.now()
    attempt.save(update_fields=["status", "initiated_at", "updated_at"])

    # Forward authoritative per-line order-item snapshots to itemized (BNPL)
    # providers so their cartList reflects the real basket and reconciles
    # exactly to the order amount. Non-itemized adapters (PSPs) never receive
    # the keyword, so their signatures/tests are untouched. The adapter still
    # performs the single Toman -> Rial x10 conversion.
    create_kwargs = dict(
        amount=order.grand_total,
        currency="TOMAN",
        callback_url=callback_url,
        credentials=credentials,
        order_code=order.code,
        description=f"پرداخت سفارش {order.code}",
        sandbox=gateway_config.is_sandbox,
    )
    if adapter.category == GatewayCategory.BNPL:
        cart_items, cart_totals = build_order_cart_snapshot(order)
        if cart_items:
            create_kwargs["cart_items"] = cart_items
            create_kwargs["cart_totals"] = cart_totals

    try:
        result = adapter.create_payment(**create_kwargs)
    except GatewayError as exc:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = getattr(exc, "code", "gateway_error")
        attempt.failure_message = str(exc)[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.warning("Payment initiation failed: order=%s error=%s", order.code, exc)
        raise PaymentInitiationError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - never leave the attempt in REQUESTING
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = "unexpected_error"
        attempt.failure_message = f"{type(exc).__name__}"[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        logger.exception("Payment initiation crashed: order=%s", order.code)
        raise PaymentInitiationError("خطای غیرمنتظره در ارتباط با درگاه") from exc

    # Store track_id, persist the authoritative payment-page URL, and mark
    # ready for redirect. The URL is kept in a field distinct from the
    # tracking id so the view never redirects the customer to a bare token.
    # Prefer result.gateway_url; fall back to extra['paymentPageUrl']/['url']
    # only when gateway_url is empty. Adapters that DERIVE the redirect URL
    # from the track_id (zibal/zarinpal) legitimately return no URL here and
    # leave the field blank, so the view falls back to build_redirect_url.
    attempt.gateway_track_id = result.track_id
    redirect_url = (result.gateway_url or "").strip()
    if not redirect_url and result.extra:
        redirect_url = str(
            result.extra.get("paymentPageUrl") or result.extra.get("url") or ""
        ).strip()
    if redirect_url and not is_safe_gateway_redirect(redirect_url, adapter, sandbox=gateway_config.is_sandbox):
        # a provider answer pointing outside its own HTTPS domains is never stored nor followed
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = "unsafe_redirect"
        attempt.failure_message = "نشانیِ بازگشتیِ درگاه نامعتبر/ناامن بود"
        attempt.gateway_track_id = attempt.gateway_track_id or ""
        attempt.save(update_fields=["gateway_track_id", "status", "failure_code", "failure_message", "updated_at"])
        logger.error("Unsafe gateway redirect refused: order=%s attempt=%s", order.code, attempt.public_id)
        raise PaymentInitiationError("نشانیِ پرداختِ درگاه معتبر نبود")
    attempt.gateway_redirect_url = redirect_url
    if not ((attempt.gateway_track_id or "").strip() or redirect_url):
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_code = "empty_gateway_response"
        attempt.failure_message = "درگاه شناسه یا نشانیِ پرداخت برنگرداند"
        attempt.save(update_fields=[
            "gateway_track_id", "gateway_redirect_url", "status", "failure_code", "failure_message", "updated_at",
        ])
        raise PaymentInitiationError("درگاه شناسه یا نشانیِ پرداخت برنگرداند")
    attempt.status = PaymentAttempt.Status.REDIRECT_READY
    attempt.save(
        update_fields=["gateway_track_id", "gateway_redirect_url", "status", "updated_at"]
    )

    logger.info(
        "Payment initiated: order=%s attempt=%s trackId=%s",
        order.code, attempt.public_id, result.track_id,
    )
    return attempt


# ---------------------------------------------------------------------------
# Settlement uncertainty (BNPL: verify succeeded, settle outcome not proven)
# ---------------------------------------------------------------------------
#
# Financial rules (do not weaken):
#   * A provider timeout / transport error / malformed answer is NOT proof that the provider did nothing. It is never
#     recorded as a definitive failure and never produces ``payment.failed``.
#   * The order is never marked paid before the provider-required verify AND settle are proven (settle ok, or the
#     provider's own status inquiry says SETTLED).
#   * An unresolved attempt is stored as ``UNKNOWN`` (not final), with a durable ``PaymentReconciliation`` (suspected) and
#     append-only ``PaymentTransactionEvent`` evidence. While it exists, no new chargeable operation can be started for the
#     order (see ``_has_unresolved_settlement``) and a repeated callback never re-verifies / re-settles it.
#   * Only authoritative provider evidence closes it: inquiry SETTLED -> paid; inquiry CANCEL/REVERT (terminal_negative)
#     -> failed; anything else stays UNKNOWN for ``resolve_unknown_payment`` / the administrative reconciliation page.


def _open_attempt_statuses() -> list[str]:
    final = set(PaymentAttempt.FINAL_STATUSES) | set(PaymentAttempt.EXTENDED_FINAL_STATUSES)
    return [s for s in PaymentAttempt.Status.values if s not in final]


def _has_unresolved_settlement(order: Order, store) -> bool:
    return PaymentAttempt.objects.filter(order=order, store=store, status=PaymentAttempt.Status.UNKNOWN).exists()


def _record_event(attempt: PaymentAttempt, event_type: str, *, message: str = "", payload: dict | None = None, from_status: str = "", to_status: str = "") -> None:
    """Append-only evidence row (never updated/deleted). Failures here must never break a payment flow."""
    try:
        with transaction.atomic():
            PaymentTransactionEvent.objects.create(
                store=attempt.store, order_id=attempt.order_id, attempt=attempt, event_type=event_type,
                from_status=from_status[:20], to_status=to_status[:20], amount=attempt.amount, currency=attempt.currency,
                gateway_ref_id=(attempt.gateway_ref_id or "")[:100], message=message[:300], payload=payload or {},
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not record payment event: attempt=%s type=%s", attempt.pk, event_type)


@dataclass(frozen=True)
class SettleOutcome:
    kind: str  # "ok" | "failed" | "uncertain"
    ref: str = ""
    evidence: dict = field(default_factory=dict)


def _inquire_status(attempt: PaymentAttempt, adapter, credentials: dict, sandbox: bool):
    """Authoritative provider status, or None when the adapter cannot inquire / the inquiry itself is inconclusive."""
    if not adapter.supports(PaymentOperation.INQUIRE):
        return None
    try:
        return adapter.inquire_payment(
            track_id=attempt.gateway_track_id, expected_amount=attempt.amount, currency=attempt.currency,
            credentials=credentials, sandbox=sandbox,
        )
    except GatewayAmountMismatchError:
        raise
    except Exception as exc:  # noqa: BLE001 — an inconclusive inquiry is "still unknown", never a failure
        logger.warning("Status inquiry inconclusive: attempt=%s error=%s", attempt.public_id, type(exc).__name__)
        return None


def _settle_after_verify(attempt: PaymentAttempt, adapter, credentials: dict, sandbox: bool) -> SettleOutcome:
    """Run the provider settle step and classify the outcome; NEVER guesses.

    ok        settle reported success, or the provider's own status says SETTLED (late success).
    failed    the provider's own status proves it will not complete (CANCEL/REVERT) — authoritative evidence.
    uncertain everything else: timeout, transport error, malformed answer, a bare ``success=False`` that the provider's
              status cannot confirm, or an adapter that cannot inquire.
    """
    evidence: dict = {"stage": "settle"}
    settle = None
    try:
        settle = adapter.settle_payment(
            track_id=attempt.gateway_track_id, amount=attempt.amount, currency=attempt.currency,
            credentials=credentials, sandbox=sandbox,
        )
    except GatewayError as exc:
        evidence.update(error_type=type(exc).__name__, error_code=str(getattr(exc, "code", ""))[:40],
                        transport=isinstance(exc, (GatewayConnectionError, GatewayResponseError)))
        logger.warning("BNPL settle outcome unknown: attempt=%s error=%s", attempt.public_id, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        evidence.update(error_type=type(exc).__name__)
        logger.exception("BNPL settle crashed: attempt=%s", attempt.public_id)

    if settle is not None and getattr(settle, "success", False):
        return SettleOutcome("ok", ref=str(getattr(settle, "settle_ref", "") or ""), evidence=evidence)
    if settle is not None:
        evidence.update(settle_rejected=True, settle_status_code=getattr(settle, "status_code", 0),
                        settle_message=str(getattr(settle, "message", ""))[:200])

    # Settlement not proven: ask the provider instead of guessing.
    try:
        inquiry = _inquire_status(attempt, adapter, credentials, sandbox)
    except GatewayAmountMismatchError:
        evidence["inquiry_amount_mismatch"] = True
        inquiry = None
    if inquiry is not None:
        evidence.update(inquiry_status=str(inquiry.status)[:40], inquiry_settled=bool(inquiry.settled),
                        inquiry_terminal_negative=bool(inquiry.terminal_negative))
        if inquiry.settled:
            return SettleOutcome("ok", ref=str(inquiry.ref_id or ""), evidence=evidence)
        if inquiry.terminal_negative:
            return SettleOutcome("failed", evidence=evidence)
    return SettleOutcome("uncertain", evidence=evidence)


def _mark_settlement_uncertain(attempt_pk: int, result, evidence: dict) -> PaymentAttempt:
    """Verified-but-unsettled: store UNKNOWN + durable suspected reconciliation + evidence event. Idempotent. Never touches the order."""
    with transaction.atomic():
        pending = PaymentAttempt.objects.get(pk=attempt_pk)
        order = Order.objects.select_for_update().get(pk=pending.order_id)
        attempt = PaymentAttempt.objects.select_for_update().select_related("store").get(pk=attempt_pk)
        if attempt.status == PaymentAttempt.Status.SUCCEEDED:
            return attempt  # a concurrent callback already finished it
        previous = attempt.status
        attempt.status = PaymentAttempt.Status.UNKNOWN
        attempt.gateway_ref_id = (getattr(result, "ref_id", "") or attempt.gateway_ref_id or "")[:100]
        attempt.failure_code = "settle_uncertain"
        attempt.failure_message = "تأیید درگاه موفق بود ولی نتیجه‌ی تسویه نامشخص است؛ در انتظار بررسی"
        attempt.save(update_fields=["status", "gateway_ref_id", "failure_code", "failure_message", "updated_at"])
        ev = {**_sanitized_evidence(result), **evidence}
        _open_reconciliation(
            attempt=attempt, order=order, kind=PaymentReconciliation.Kind.SETTLEMENT_UNCERTAIN, evidence=ev,
            error=str(evidence.get("error_type") or evidence.get("settle_message") or "settlement outcome unknown"),
            level=PaymentReconciliation.EvidenceLevel.SUSPECTED,
        )
        _record_event(attempt, PaymentTransactionEvent.EventType.NOTE, message="settlement outcome unknown (verified, not proven settled)",
                      payload=ev, from_status=previous, to_status=attempt.status)
    logger.error("BNPL settlement UNKNOWN (no payment.failed, order untouched): order=%s attempt=%s", order.code, attempt.public_id)
    return attempt


def resolve_unknown_payment(attempt_pk: int, *, store=None) -> PaymentAttempt | None:
    """Try to close an UNKNOWN (verified, settlement-unproven) attempt with the provider's AUTHORITATIVE status.

    Safe to run concurrently / repeatedly (cron, admin action, a late callback): the provider call is made outside any lock and
    the outcome is applied under the order+attempt locks with a status re-check, so only one worker applies it.
    * inquiry SETTLED            -> the normal verified-payment path (order paid once, transaction once)
    * inquiry CANCEL / REVERT    -> attempt FAILED (authoritative), reconciliation resolved ``not_paid``, ``payment.failed`` once
    * anything else / no inquiry -> unchanged (still UNKNOWN; administrative reconciliation page applies)
    Never calls settle again (no duplicate settlement request).
    """
    qs = PaymentAttempt.objects.select_related("order", "gateway_config", "store").filter(pk=attempt_pk)
    if store is not None:
        qs = qs.filter(store=store)
    attempt = qs.first()
    if attempt is None or attempt.status != PaymentAttempt.Status.UNKNOWN:
        return attempt
    config = attempt.gateway_config
    try:
        adapter = get_adapter(config.gateway_code)
        credentials = config.get_credentials()
    except (KeyError, CredentialEncryptionError):
        return attempt
    try:
        inquiry = _inquire_status(attempt, adapter, credentials, config.is_sandbox)
    except GatewayAmountMismatchError as exc:
        ev = dict((exc.details or {}).get("evidence") or {})
        return _record_discrepancy(attempt.pk, confirmed=True, kind=PaymentReconciliation.Kind.AMOUNT_MISMATCH, evidence=ev,
                                   reported_amount=_toman_from_rial(ev.get("returned_rial")), error=str(exc))
    if inquiry is None:
        return attempt
    _record_event(attempt, PaymentTransactionEvent.EventType.INQUIRY, message=f"inquiry: {str(inquiry.status)[:40]}",
                  payload={"status": str(inquiry.status)[:40], "settled": bool(inquiry.settled), "terminal_negative": bool(inquiry.terminal_negative)})
    if inquiry.settled:
        result = PaymentVerificationResult(success=True, ref_id=str(inquiry.ref_id or attempt.gateway_ref_id or ""), status_code=100,
                                           message="تسویه توسط درگاه تأیید شد (استعلام).")
        return _apply_verified_payment(attempt.pk, result, attempt.store)
    if inquiry.terminal_negative:
        return _close_unknown_as_failed(attempt.pk, status_token=str(inquiry.status)[:40])
    return attempt


def _close_unknown_as_failed(attempt_pk: int, *, status_token: str) -> PaymentAttempt:
    with transaction.atomic():
        pending = PaymentAttempt.objects.get(pk=attempt_pk)
        order = Order.objects.select_for_update().get(pk=pending.order_id)
        attempt = PaymentAttempt.objects.select_for_update().select_related("store").get(pk=attempt_pk)
        if attempt.status != PaymentAttempt.Status.UNKNOWN:
            return attempt  # another worker already resolved it
        order_paid = order.payment_status == Order.PaymentStatus.PAID
        attempt.status = PaymentAttempt.Status.CANCELED if order_paid else PaymentAttempt.Status.FAILED
        attempt.failure_code = "settle_reverted"
        attempt.failure_message = f"درگاه اعلام کرد پرداخت تکمیل نمی‌شود ({status_token})"[:300]
        attempt.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        PaymentReconciliation.objects.filter(attempt=attempt, status=PaymentReconciliation.Status.OPEN).update(
            status=PaymentReconciliation.Status.RESOLVED, resolution=PaymentReconciliation.Resolution.NOT_PAID,
            resolution_note=f"وضعیت قطعیِ درگاه: {status_token}"[:500], resolved_at=timezone.now(),
        )
        _record_event(attempt, PaymentTransactionEvent.EventType.CANCELED if order_paid else PaymentTransactionEvent.EventType.STATUS_CHANGE,
                      message=f"provider status {status_token}", from_status=PaymentAttempt.Status.UNKNOWN, to_status=attempt.status)
        if not order_paid:
            from apps.notifications.services import admin_events

            public_id = attempt.public_id
            transaction.on_commit(lambda: admin_events.payment_attempt_failed(order, public_id))
    return attempt


# ---------------------------------------------------------------------------
# Process callback and verify
# ---------------------------------------------------------------------------


def _sanitized_evidence(result) -> dict:
    """شواهدِ تأییدِ درگاه برایِ ذخیره — فقط فیلدهایِ امن (کارتِ ماسک‌شده، بدونِ اعتبارنامه/PII)."""
    return {
        "ref_id": str(getattr(result, "ref_id", ""))[:100],
        "card_number": str(getattr(result, "card_number", ""))[:25],
        "status_code": getattr(result, "status_code", 0),
        "message": str(getattr(result, "message", ""))[:200],
    }


def _toman_from_rial(rial) -> Decimal | None:
    try:
        return (Decimal(int(rial)) / Decimal(10)).quantize(Decimal("0.1"))
    except (TypeError, ValueError):
        return None


def _open_reconciliation(
    *, attempt, order, kind, evidence, error="", level=None, reported_amount=None,
) -> PaymentReconciliation:
    """رکوردِ تطبیق (یکتا به‌ازای هر تلاش) + اعلانِ کارکنان. idempotent.

    اگر برایِ این تلاش قبلاً یک مورد «مشکوک» (تأییدنشده) باز شده و حالا درگاه پرداخت را تأیید کرده،
    همان رکورد به «تأییدشده» ارتقا می‌یابد (و اعلانِ تازه‌ای می‌رود) — رکوردِ دوم ساخته نمی‌شود."""
    from apps.notifications.services import business_events
    from apps.notifications.services.notification_service import sanitize_error

    L = PaymentReconciliation.EvidenceLevel
    level = level or L.CONFIRMED
    error = sanitize_error(error)
    record, created = PaymentReconciliation.objects.get_or_create(
        attempt=attempt,
        defaults=dict(
            store=attempt.store, order=order, kind=kind, evidence_level=level, amount=attempt.amount,
            reported_amount=reported_amount,
            gateway_track_id=attempt.gateway_track_id, gateway_ref_id=attempt.gateway_ref_id,
            order_status_at_detection=order.status, payment_status_at_detection=order.payment_status,
            evidence=evidence, error_message=(error or "")[:300],
        ),
    )
    if created:
        logger.error(
            "Gateway payment NOT applied (%s/%s): order=%s attempt=%s ref=%s expected=%s reported=%s",
            kind, level, order.code, attempt.public_id, attempt.gateway_ref_id, attempt.amount, reported_amount,
        )
        business_events.late_payment(record)
    elif (
        record.status == PaymentReconciliation.Status.OPEN
        and record.evidence_level == L.SUSPECTED and level == L.CONFIRMED
    ):
        record.kind, record.evidence_level, record.evidence = kind, level, evidence
        record.reported_amount, record.gateway_ref_id = reported_amount, attempt.gateway_ref_id
        record.order_status_at_detection, record.payment_status_at_detection = order.status, order.payment_status
        record.save()
        business_events.late_payment(record, upgraded=True)
    return record


def _close_suspected_record(attempt, note: str) -> None:
    """درگاه بعداً پرداخت را تأیید کرد و عادی اعمال شد ⇒ موردِ «مشکوکِ» باز بسته می‌شود (سیستمی، قابلِ ردیابی)."""
    PaymentReconciliation.objects.filter(
        attempt=attempt, status=PaymentReconciliation.Status.OPEN,
        evidence_level=PaymentReconciliation.EvidenceLevel.SUSPECTED,
    ).update(
        status=PaymentReconciliation.Status.RESOLVED, resolution=PaymentReconciliation.Resolution.AUTO_VERIFIED,
        resolution_note=note[:500], resolved_at=timezone.now(),
    )


def _record_discrepancy(attempt_pk: int, *, confirmed: bool, kind, evidence: dict, reported_amount, error: str) -> PaymentAttempt:
    """مغایرتِ مبلغ (تأییدشده) یا نتیجه‌ی نامشخصِ تأیید (مشکوک) را پایدار ثبت می‌کند — هرگز سفارش را پرداخت‌شده نمی‌کند.

    قفل: همان ترتیبِ ``_apply_verified_payment`` (ابتدا سفارش، بعد تلاش). تأییدشده ⇒ تلاش SUCCEEDED
    (پولِ درگاه واقعاً جابه‌جا شده؛ job انقضا هم از روی همین، سفارش را رها می‌کند) اما **Transaction** ساخته
    نمی‌شود و سفارش/کوپن/موجودی دست نمی‌خورد. مشکوک ⇒ وضعیتِ تلاش تغییر نمی‌کند."""
    L = PaymentReconciliation.EvidenceLevel
    with transaction.atomic():
        pending = PaymentAttempt.objects.get(pk=attempt_pk)
        order = Order.objects.select_for_update().get(pk=pending.order_id)
        attempt = PaymentAttempt.objects.select_for_update().select_related("store").get(pk=attempt_pk)
        if confirmed:
            attempt.status = PaymentAttempt.Status.SUCCEEDED
            attempt.gateway_ref_id = (evidence.get("ref_id") or attempt.gateway_ref_id or "")[:100]
            attempt.verified_at = timezone.now()
            attempt.failure_code = "amount_mismatch"
            attempt.failure_message = "مبلغِ تأییدشده با سفارش مغایرت دارد"
            attempt.save(update_fields=[
                "status", "gateway_ref_id", "verified_at", "failure_code", "failure_message", "updated_at",
            ])
        return_attempt = attempt
        _open_reconciliation(
            attempt=attempt, order=order, kind=kind, evidence=evidence, error=error,
            level=L.CONFIRMED if confirmed else L.SUSPECTED, reported_amount=reported_amount,
        )
    return return_attempt


def _apply_verified_payment(attempt_pk: int, result, store) -> PaymentAttempt:
    """درگاه پول را تأیید کرده؛ سفارش را (اگر هنوز قابل‌پرداخت است) پرداخت‌شده می‌کند، وگرنه
    شواهد را در ``PaymentReconciliation`` نگه می‌دارد — هرگز بی‌صدا گم نمی‌شود.

    قفل: ابتدا ردیفِ **سفارش** و بعد تلاش (همان ترتیبِ ``change_order_status``/job انقضا) تا لغو و
    پرداختِ همزمان سریال شوند: یا لغو برنده است (⇒ تطبیق) یا پرداخت (⇒ لغوِ بعدی از PROCESSING)."""
    from apps.orders.services.lifecycle import apply_payment_success

    with transaction.atomic():
        pending = PaymentAttempt.objects.get(pk=attempt_pk)
        order = Order.objects.select_for_update().get(pk=pending.order_id)
        attempt = PaymentAttempt.objects.select_for_update().select_related("store").get(pk=attempt_pk)
        if attempt.status == PaymentAttempt.Status.SUCCEEDED:
            return attempt  # رقابتِ دو callback: دیگری پردازش کرده است

        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.gateway_ref_id = result.ref_id
        attempt.verified_at = timezone.now()
        attempt.failure_code = ""
        attempt.failure_message = ""
        attempt.save(update_fields=["status", "gateway_ref_id", "verified_at", "failure_code", "failure_message", "updated_at"])
        evidence = _sanitized_evidence(result)
        K = PaymentReconciliation.Kind

        if order.status == Order.Status.CANCELED:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ORDER_CANCELED, evidence=evidence)
            return attempt
        if order.payment_status == Order.PaymentStatus.PAID:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ALREADY_PAID, evidence=evidence)
            return attempt
        if order.payment_status != Order.PaymentStatus.PENDING:
            _open_reconciliation(attempt=attempt, order=order, kind=K.NOT_PAYABLE, evidence=evidence)
            return attempt

        try:
            with transaction.atomic():  # savepoint: خطا نباید شواهدِ پرداخت را با خود ببرد
                tx = apply_payment_success(
                    order, store=store, ref_id=result.ref_id, from_statuses=(Order.PaymentStatus.PENDING,),
                    note="پرداخت آنلاین موفق — سفارش به پردازش منتقل شد",
                )
        except Exception as exc:  # noqa: BLE001 — حفظِ شواهد مهم‌تر از نوعِ خطاست
            logger.exception("Applying verified payment failed: order=%s attempt=%s", order.code, attempt.public_id)
            _open_reconciliation(
                attempt=attempt, order=order, kind=K.PROCESSING_ERROR, evidence=evidence,
                error=f"{type(exc).__name__}: {exc}",
            )
            return attempt
        if tx is None:
            _open_reconciliation(attempt=attempt, order=order, kind=K.ALREADY_PAID, evidence=evidence)
            return attempt
        _close_suspected_record(attempt, "تأیید بعدیِ درگاه و اعمالِ عادیِ پرداخت")
    logger.info("Payment verified and order paid: order=%s attempt=%s ref=%s", order.code, attempt.public_id, result.ref_id)
    return attempt


def _callback_claims_success(callback_data: dict, adapter=None) -> bool:
    """آیا پارامترهایِ بازگشت از درگاه ادعای پرداخت می‌کند؟ (فقط برای «مشکوک» ثبت‌کردن؛ هرگز مدرکِ پرداخت نیست).
    ادعا را خودِ آداپتور (``callback_claims_success``) می‌سنجد؛ بدونِ آداپتور همان قاعده‌ی عمومیِ پایه."""
    if adapter is not None and hasattr(adapter, "callback_claims_success"):
        return bool(adapter.callback_claims_success(callback_data))
    from apps.orders.gateways.base import PaymentGatewayAdapter

    return bool(PaymentGatewayAdapter.callback_claims_success(None, callback_data))


def process_callback_and_verify(
    *,
    attempt_public_id: str,
    callback_data: dict,
    store,
) -> PaymentAttempt:
    """Process a gateway callback: verify with the gateway, then apply or reconcile.

    * ``SUCCEEDED`` attempt → idempotent return (duplicate callback).
    * Any other attempt — **including final ones** (failed/canceled/expired) — is verified with the
      gateway: money may have been taken (late callback, duplicate attempt, expired session).
    * Verified success on a payable order → order paid via ``apply_payment_success``.
    * Verified success on a canceled / already-paid / non-payable order (or if applying fails) →
      attempt recorded ``SUCCEEDED`` + persistent ``PaymentReconciliation``; the order is **not**
      reopened, marked paid or given its coupon back.
    * Verification failure on an open attempt → attempt ``FAILED`` (or ``CANCELED`` if the order was
      already paid) and ``PaymentVerificationFailed``; on an already-final attempt nothing changes.
    """
    attempt = (
        PaymentAttempt.objects
        .select_related("order", "gateway_config")
        .filter(public_id=attempt_public_id, store=store)
        .first()
    )
    if attempt is None:
        raise PaymentVerificationFailed("تلاش پرداخت یافت نشد")

    if attempt.status == PaymentAttempt.Status.SUCCEEDED:
        logger.info("Callback for already-succeeded attempt: %s", attempt.public_id)
        return attempt

    if attempt.status == PaymentAttempt.Status.UNKNOWN:
        # Verified earlier, settlement unproven: a (duplicate / late) callback must NEVER re-verify or re-settle. Ask the provider's
        # authoritative status instead; the outcome (paid / failed / still unknown) is applied exactly once under the locks.
        resolved = resolve_unknown_payment(attempt.pk, store=store)
        if resolved is not None and resolved.status in (PaymentAttempt.Status.FAILED, PaymentAttempt.Status.CANCELED):
            raise PaymentVerificationFailed("تسویه‌ی نهاییِ پرداخت اقساطی انجام نشد؛ سفارش پرداخت‌شده تلقی نمی‌شود.")
        return resolved or attempt

    was_final = attempt.is_final
    order = attempt.order
    open_statuses = _open_attempt_statuses()
    if not was_final:
        # گذارِ شرطی (نه ذخیره‌ی کورکورانه): callbackِ همزمانی که همین تلاش را SUCCEEDED کرده نباید پاک شود.
        PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
            status=PaymentAttempt.Status.PENDING, updated_at=timezone.now(),
        )

    def fail(code: str, message: str, exc_message: str, *, definitive: bool = False):
        if not was_final:  # یک تلاشِ نهایی‌شده با callbackِ تکراری/دیرهنگام بازنویسی نمی‌شود
            fresh_paid = Order.objects.filter(pk=order.pk, payment_status=Order.PaymentStatus.PAID).exists()
            moved = PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
                status=PaymentAttempt.Status.CANCELED if fresh_paid else PaymentAttempt.Status.FAILED,
                failure_code=code, failure_message=message[:300], updated_at=timezone.now(),
            )
            if definitive and moved and not fresh_paid:
                # فقط «تلاشِ پرداخت» قطعاً ناموفق شد (نه کلِ سفارش) — اعلانِ مدیر پس از commitِ همین گذار؛ dedupe روی شناسه‌ی تلاش.
                from apps.notifications.services import admin_events

                public_id = attempt.public_id
                transaction.on_commit(lambda: admin_events.payment_attempt_failed(order, public_id))
        raise PaymentVerificationFailed(exc_message)

    if not attempt.gateway_track_id:
        fail("no_track_id", "شناسه‌ی پیگیریِ درگاه ثبت نشده", "تلاش پرداخت قابل‌تأیید نیست")

    gateway_config = attempt.gateway_config
    try:
        adapter = get_adapter(gateway_config.gateway_code)
        credentials = gateway_config.get_credentials()
    except (KeyError, CredentialEncryptionError) as exc:
        fail("config_error", "خطای پیکربندی درگاه", "خطای پیکربندی درگاه")
        raise exc  # unreachable — fail() always raises

    try:
        result = adapter.verify_payment(
            track_id=attempt.gateway_track_id,
            expected_amount=attempt.amount,
            currency=attempt.currency,
            credentials=credentials,
            callback_data=callback_data,
            sandbox=gateway_config.is_sandbox,
        )
    except GatewayAmountMismatchError as exc:
        # درگاه پرداخت را تأیید کرده اما با مبلغِ دیگر: شواهد ذخیره، سفارش پرداخت‌شده نمی‌شود.
        ev = dict((exc.details or {}).get("evidence") or {})
        _record_discrepancy(
            attempt.pk, confirmed=True, kind=PaymentReconciliation.Kind.AMOUNT_MISMATCH, evidence=ev,
            reported_amount=_toman_from_rial(ev.get("returned_rial")), error=str(exc),
        )
        raise PaymentAmountMismatch(
            "مبلغ تراکنش با مبلغ سفارش مطابقت ندارد. اگر مبلغی از حساب شما کسر شده، پشتیبانی آن را بررسی می‌کند."
        ) from exc
    except GatewayError as exc:
        logger.warning("Verification failed: attempt=%s error=%s", attempt.public_id, exc)
        # نتیجه‌ی نامشخص (قطع/تایم‌اوت/پاسخِ نامعتبر/مبلغِ اعلام‌نشده) در حالی که مشتری با ادعای موفقیت از
        # درگاه برگشته ⇒ مورد «مشکوک» برایِ بررسی؛ هیچ ادعایی دربارهٔ موفقیتِ پرداخت نمی‌شود.
        if isinstance(exc, (GatewayConnectionError, GatewayResponseError)) and _callback_claims_success(callback_data, adapter):
            ev = dict((exc.details or {}).get("evidence") or {})
            ev["error_code"] = getattr(exc, "code", "")
            ev["callback_claims_success"] = True
            _record_discrepancy(
                attempt.pk, confirmed=False, kind=PaymentReconciliation.Kind.VERIFY_AMBIGUOUS, evidence=ev,
                reported_amount=_toman_from_rial(ev.get("returned_rial")), error=str(exc),
            )
        fail(getattr(exc, "code", "verify_error"), str(exc), str(exc))

    settled_by_inquiry = False
    verify_failure_confirmed = True
    if not result.success and adapter.supports(PaymentOperation.SETTLE) and adapter.supports(PaymentOperation.INQUIRE):
        # Verified-at-provider but locally unfinished (crash/retry) looks like a "verify failure" on a repeated verify call
        # ("already verified"). For two-step providers the provider's own status decides before anything is called a failure.
        try:
            inquiry = _inquire_status(attempt, adapter, credentials, gateway_config.is_sandbox)
        except GatewayAmountMismatchError:
            inquiry = None
        if inquiry is not None and inquiry.paid:
            result = PaymentVerificationResult(success=True, ref_id=str(inquiry.ref_id or ""), status_code=100,
                                               message="تأیید توسط استعلامِ وضعیتِ درگاه")
            settled_by_inquiry = bool(inquiry.settled)
        elif inquiry is None:
            verify_failure_confirmed = False  # cannot tell "never paid" from "paid, unreadable": no definitive claim, no failure alert

    if not result.success:
        logger.info("Verification returned failure: attempt=%s final=%s", attempt.public_id, was_final)
        # «قطعی» = خودِ درگاه در تأییدِ server-to-server اعلامِ ناموفق کرد و callback ادعای موفقیت نداشت؛
        # قطع/تایم‌اوت/پاسخِ نامعتبر/مغایرتِ مبلغ/ادعای موفقیتِ callback هرگز اعلانِ «ناموفق» نمی‌سازند.
        fail(f"status_{result.status_code}", result.message or "تأیید پرداخت ناموفق", result.message or "تأیید پرداخت توسط درگاه ناموفق بود",
             definitive=verify_failure_confirmed and not _callback_claims_success(callback_data, adapter))

    # Capability-gated BNPL settle/capture (no provider conditionals): a provider whose documented lifecycle separates verify
    # from settle declares the SETTLE capability; the money is NOT fully captured until settle is proven, so the order is never
    # marked paid before that. Providers without SETTLE (ordinary PSPs, Zibal, Zarinpal) skip this entirely.
    # The outcome is classified, never guessed (see "Settlement uncertainty" above).
    if adapter.supports(PaymentOperation.SETTLE):
        _record_event(attempt, PaymentTransactionEvent.EventType.VERIFIED, message="provider verification succeeded",
                      payload=_sanitized_evidence(result), from_status=attempt.status, to_status=attempt.status)
        outcome = SettleOutcome("ok", evidence={"stage": "settle", "already_settled": True}) if settled_by_inquiry else \
            _settle_after_verify(attempt, adapter, credentials, gateway_config.is_sandbox)
        if outcome.kind == "uncertain":
            return _mark_settlement_uncertain(attempt.pk, result, outcome.evidence)
        if outcome.kind == "failed":
            fail("settle_reverted", "درگاه اعلام کرد پرداخت تکمیل نمی‌شود",
                 "تسویه‌ی نهاییِ پرداخت اقساطی انجام نشد؛ سفارش پرداخت‌شده تلقی نمی‌شود.", definitive=True)
        _record_event(attempt, PaymentTransactionEvent.EventType.SETTLED, message="provider settlement confirmed",
                      payload=outcome.evidence)

    return _apply_verified_payment(attempt.pk, result, store)
