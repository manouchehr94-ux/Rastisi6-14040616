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
from decimal import Decimal

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
)
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig, PaymentReconciliation, Transaction

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
        """Return a live attempt for THIS exact operation identity, or None.

        Scoped by store (tenant isolation), order, gateway_config, and amount.
        If an idempotency_key is supplied it must ALSO match — but a key that
        belongs to a different identity is simply not found here, so a reused
        foreign key can never surface a foreign attempt.
        """
        qs = PaymentAttempt.objects.filter(
            store=store,
            order=order,
            gateway_config=gateway_config,
            amount=order.grand_total,
            status__in=_reusable_statuses,
        )
        if idempotency_key:
            qs = qs.filter(idempotency_key=idempotency_key)
        return qs.order_by("-created_at").first()

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
    existing = _scoped_existing()
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

        # Re-check inside the lock: a concurrent winner may have just created a
        # live attempt for this exact operation.
        existing = _scoped_existing()
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
            existing = _scoped_existing()
            if existing is not None:
                return existing
            # The collision was with a row that is NOT a live attempt for this
            # exact identity (e.g. a dead prior attempt still holding the base
            # deterministic key). Mint a fresh disambiguated key and insert
            # again; _key_to_persist counts existing attempts, so the committed
            # racer shifts the count and yields a new, non-colliding key.
            attempt.idempotency_key = _key_to_persist()
            attempt.save()

    # Offline gateways never go through the online redirect/verify flow. The
    # two offline methods have OPPOSITE bookkeeping, distinguished by the
    # adapter's explicit ``auto_collects_offline`` signal (not a code string):
    #
    # * COD (auto_collects_offline=True): selecting it is a firm pay-on-
    #   delivery commitment, so record the attempt SUCCEEDED at selection with
    #   a cod- track id and a verified_at timestamp. The order itself is NOT
    #   marked paid — it stays pending until delivery confirmation.
    # * Card-to-card (auto_collects_offline=False): the customer transfers
    #   money out of band and nothing proves it arrived at selection time. The
    #   attempt stays PENDING (no verified_at, no cod- track id, order not
    #   paid) until an authorized merchant confirms the transfer.
    if not adapter.is_online:
        if adapter.auto_collects_offline:
            attempt.status = PaymentAttempt.Status.SUCCEEDED
            attempt.gateway_track_id = f"cod-{order.code}"
            attempt.verified_at = timezone.now()
            attempt.save(update_fields=["status", "gateway_track_id", "verified_at", "updated_at"])
            # COD does NOT mark order as paid — it stays pending until delivery
            logger.info("COD payment recorded: order=%s attempt=%s", order.code, attempt.public_id)
            return attempt
        # Non-auto-collecting offline method (card-to-card): leave PENDING for
        # manual merchant confirmation. No verified_at, order not marked paid.
        attempt.status = PaymentAttempt.Status.PENDING
        attempt.gateway_track_id = f"card2card-{order.code}"
        attempt.save(update_fields=["status", "gateway_track_id", "updated_at"])
        logger.info(
            "Card-to-card payment selected (pending merchant confirmation): order=%s attempt=%s",
            order.code, attempt.public_id,
        )
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
    attempt.gateway_redirect_url = redirect_url
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


def _callback_claims_success(callback_data: dict) -> bool:
    """آیا پارامترهایِ بازگشت از درگاه ادعای پرداخت می‌کند؟ (فقط برای «مشکوک» ثبت‌کردن؛ هرگز مدرکِ پرداخت نیست)."""
    cd = callback_data or {}
    return str(cd.get("success", "")).strip() == "1" or str(cd.get("status", "")).strip() in ("1", "2")


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

    was_final = attempt.is_final
    order = attempt.order
    open_statuses = [s for s in PaymentAttempt.Status.values if s not in PaymentAttempt.FINAL_STATUSES]
    if not was_final:
        # گذارِ شرطی (نه ذخیره‌ی کورکورانه): callbackِ همزمانی که همین تلاش را SUCCEEDED کرده نباید پاک شود.
        PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
            status=PaymentAttempt.Status.PENDING, updated_at=timezone.now(),
        )

    def fail(code: str, message: str, exc_message: str):
        if not was_final:  # یک تلاشِ نهایی‌شده با callbackِ تکراری/دیرهنگام بازنویسی نمی‌شود
            fresh_paid = Order.objects.filter(pk=order.pk, payment_status=Order.PaymentStatus.PAID).exists()
            PaymentAttempt.objects.filter(pk=attempt.pk, status__in=open_statuses).update(
                status=PaymentAttempt.Status.CANCELED if fresh_paid else PaymentAttempt.Status.FAILED,
                failure_code=code, failure_message=message[:300], updated_at=timezone.now(),
            )
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
        if isinstance(exc, (GatewayConnectionError, GatewayResponseError)) and _callback_claims_success(callback_data):
            ev = dict((exc.details or {}).get("evidence") or {})
            ev["error_code"] = getattr(exc, "code", "")
            ev["callback_claims_success"] = True
            _record_discrepancy(
                attempt.pk, confirmed=False, kind=PaymentReconciliation.Kind.VERIFY_AMBIGUOUS, evidence=ev,
                reported_amount=_toman_from_rial(ev.get("returned_rial")), error=str(exc),
            )
        fail(getattr(exc, "code", "verify_error"), str(exc), str(exc))

    if not result.success:
        logger.info("Verification returned failure: attempt=%s final=%s", attempt.public_id, was_final)
        fail(f"status_{result.status_code}", result.message or "تأیید پرداخت ناموفق", result.message or "تأیید پرداخت توسط درگاه ناموفق بود")

    # Capability-gated BNPL settle/capture (no provider conditionals): a provider
    # whose documented lifecycle separates verify from settle declares the SETTLE
    # capability. For such providers the money is NOT fully captured until settle
    # succeeds, so we invoke the adapter's settle step BEFORE the order is treated
    # as paid. Providers without SETTLE (ordinary PSPs, Zibal, Zarinpal) skip this
    # entirely. A provider that declares SETTLE but whose settle is unsupported
    # (documentation-blocked) never reaches here because readiness keeps it
    # non-selectable/non-routable.
    if adapter.supports(PaymentOperation.SETTLE):
        try:
            settle = adapter.settle_payment(
                track_id=attempt.gateway_track_id,
                amount=attempt.amount,
                currency=attempt.currency,
                credentials=credentials,
                sandbox=gateway_config.is_sandbox,
            )
        except GatewayError as exc:
            logger.warning("BNPL settle failed: attempt=%s error=%s", attempt.public_id, exc)
            fail(
                getattr(exc, "code", "settle_error"),
                str(exc),
                "تسویه‌ی نهاییِ پرداخت اقساطی ناموفق بود؛ سفارش پرداخت‌شده تلقی نمی‌شود.",
            )
        if not getattr(settle, "success", False):
            fail(
                "settle_failed",
                settle.message or "تسویه‌ی نهایی ناموفق",
                "تسویه‌ی نهاییِ پرداخت اقساطی ناموفق بود؛ سفارش پرداخت‌شده تلقی نمی‌شود.",
            )

    return _apply_verified_payment(attempt.pk, result, store)
