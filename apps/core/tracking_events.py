"""Canonical e-commerce tracking events (GA4 / GTM dataLayer / Meta Pixel) — ONE builder layer on top of the existing consent pipeline.

Rules enforced here (not in the browser):
* every amount is server-resolved from the real pricing service / cart / order snapshot — never from POST or any other browser input;
* money leaves the platform ONLY through ``apps.core.currency`` (Toman → ISO ``IRR``, ×10); a source currency that is not Toman is refused, not guessed;
* items must belong to the request's store (tenant isolation by construction);
* no customer data of any kind — only item ids/names/variants/quantities/prices (and, for a purchase, the order code as ``transaction_id``);
* the dict is JSON-safe and small; ``consent.js`` re-validates it and decides per provider/consent category what (if anything) is dispatched.

``build_purchase`` exists, is unit-tested and is intentionally NOT connected to any view: a purchase must be recorded once, durably, and that needs a unique-constrained ledger
(see docs/notifications/… report: ``TrackingEmission``). Until that is approved no code path emits a Purchase."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from apps.core import currency

logger = logging.getLogger(__name__)

EVENT_NAMES = ("view_item", "add_to_cart", "begin_checkout", "purchase")
META_NAMES = {"view_item": "ViewContent", "add_to_cart": "AddToCart", "begin_checkout": "InitiateCheckout", "purchase": "Purchase"}
SOURCE_CURRENCIES = frozenset({"IRT", "TOMAN"})        # Toman spellings used by the models (Order/Product: IRT; PaymentAttempt: TOMAN)
MAX_ITEMS = 50


class TrackingEventError(ValueError):
    """The event cannot be built truthfully (wrong store, unknown currency, ineligible order…) — nothing is emitted."""


def queue(request, build, *args, **kwargs) -> dict | None:
    """Build an event for THIS page render and hand it to the template (``TRACKING_EVENTS``). Never raises into the view; builds nothing unless tracking is active for the request
    (platform flag on, store connected a provider, indexable public host, not an admin preview), so a store without tracking pays no cost and a preview never carries a payload."""
    from apps.core.context_processors import tracking_active

    try:
        if not tracking_active(request):
            return None
        event = build(*args, **kwargs)
    except TrackingEventError as exc:                   # expected: nothing truthful to report for this request
        logger.debug("tracking event skipped: %s", exc)
        return None
    except Exception:                                   # noqa: BLE001 — tracking must never break a storefront page
        logger.warning("tracking event not built", exc_info=True)
        return None
    if event:
        request.rs_track_events = [*getattr(request, "rs_track_events", []), event]
    return event


def iso_amount(amount, source_currency: str = "IRT") -> int:
    """Whole ISO-4217 ``IRR`` units for an amount stored in Toman. Refuses any other source currency instead of guessing a unit."""
    if str(source_currency or "").upper() not in SOURCE_CURRENCIES:
        raise TrackingEventError(f"unsupported source currency: {source_currency!r}")
    value = Decimal(amount)
    if value < 0:
        raise TrackingEventError("negative amount")
    return currency.toman_to_rial(value)


def _clean(text, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def _item(store, product, variant, quantity: int, unit_price, source_currency: str = "IRT") -> dict:
    if getattr(product, "store_id", None) != store.pk:
        raise TrackingEventError("product does not belong to this store")
    if variant is not None and variant.product_id != product.pk:
        raise TrackingEventError("variant does not belong to this product")
    quantity = int(quantity)
    if quantity <= 0:
        raise TrackingEventError("quantity must be positive")
    if Decimal(unit_price) <= 0:
        raise TrackingEventError("no price (price-on-inquiry / free items are not reported as a zero-value event)")
    item = {"item_id": _clean(product.sku or product.pk, 64), "item_name": _clean(product.name, 100), "price": iso_amount(unit_price, source_currency), "quantity": quantity}
    if variant is not None:
        item["item_variant"] = _clean(getattr(variant, "sku", "") or variant.pk, 64)
    return item


def _event(name: str, event_id: str, items: list[dict], *, value: int | None = None, **extra) -> dict:
    if name not in EVENT_NAMES:
        raise TrackingEventError(f"unknown event: {name!r}")
    if not items or len(items) > MAX_ITEMS:
        raise TrackingEventError("an event needs 1..%d items" % MAX_ITEMS)
    total = sum(i["price"] * i["quantity"] for i in items) if value is None else int(value)
    event = {"name": name, "id": _clean(event_id, 120), "currency": currency.ISO_CURRENCY, "value": total, "items": items}
    event.update({k: v for k, v in extra.items() if v not in (None, "")})
    return event


def build_view_item(store, product, variant=None) -> dict:
    from apps.catalog.services.pricing_service import resolve_effective_price

    if variant is not None and variant.product_id != product.pk:
        raise TrackingEventError("variant does not belong to this product")
    price = resolve_effective_price(product, variant)
    return _event("view_item", f"vi-{uuid.uuid4().hex}", [_item(store, product, variant, 1, price)])


def build_add_to_cart(store, product, variant, quantity: int, unit_price) -> dict:
    """Called only AFTER a successful, committed cart mutation; ``quantity`` is the quantity just added, ``unit_price`` the server-resolved price stored on the cart item."""
    return _event("add_to_cart", f"atc-{uuid.uuid4().hex}", [_item(store, product, variant, quantity, unit_price)])


def checkout_cycle(store, cart) -> int:
    """How many checkout cycles of THIS cart already ended in an order (0 = the cart's first cycle).

    The platform already records which cart an order came from: ``create_order_from_cart`` reserves + consumes stock per cart line with ``cart=cart, source="order"`` and
    ``consume_inventory_reservation`` stamps the resulting ``order`` on the reservation, atomically with the order. Counting the DISTINCT orders reached that way is therefore
    (a) a read of validated lifecycle data — no write on the checkout GET, no new table, no touch of ``Cart.checkout_token`` (the payment idempotency key stays exactly as it was);
    (b) tenant-scoped (``store`` filter); (c) identical for guests and logged-in customers (it is keyed by the cart row, not by who the visitor is);
    (d) constant for every render, reload, HTMX partial and second tab while the checkout is open, and (e) bumped by exactly the order that closes the cycle — so the next purchase
    made from the same, now re-used, cart row gets a new identity. Orders placed elsewhere (other devices' carts, admin-created orders) do not move it."""
    from apps.catalog.models import InventoryReservation

    return (InventoryReservation.objects.filter(store=store, cart=cart, source="order", order__isnull=False)
            .values("order_id").distinct().count())


def build_begin_checkout(store, cart) -> dict | None:
    """One event per checkout cycle of a non-empty cart. ``once=True`` tells the browser to dispatch THIS identity at most once (across reloads / tabs; best effort — begin_checkout
    is not a financial event). Suppression is by identity, never by a time window: a new cycle has a new identity and is always dispatched. Partial (HTMX) re-renders, failed
    validation and payment never reach this builder: it is called from the full-page checkout entry only."""
    if cart is None:
        return None
    rows = list(cart.items.select_related("product", "variant").all())
    items = [_item(store, r.product, r.variant, r.quantity, r.unit_price) for r in rows if r.product_id and r.product.store_id == store.pk][:MAX_ITEMS]
    if not items:
        return None
    return _event("begin_checkout", f"bc-{store.pk}-{cart.pk}-{checkout_cycle(store, cart)}", items, once=True)


def build_purchase(store, order) -> dict:
    """Server-side builder for a verified online purchase (NOT wired to any view — see module docstring). Eligible only when the order is PAID through a verified gateway
    transition; COD / card-to-card are never eligible here (their paid transition happens later in the admin panel, without a customer browser)."""
    from apps.orders.models import Order, Transaction

    if order.store_id != store.pk:
        raise TrackingEventError("order does not belong to this store")
    if order.payment_status != Order.PaymentStatus.PAID:
        raise TrackingEventError("order is not paid")
    tx = order.transactions.filter(status=Transaction.Status.OK, method=Transaction.Method.GATEWAY).first()
    if tx is None:
        raise TrackingEventError("no verified gateway transaction")
    items = []
    for row in order.items.all():
        if row.product_id is None:
            continue
        item = {"item_id": _clean(row.sku or row.product_id, 64), "item_name": _clean(row.product_name, 100), "price": iso_amount(row.unit_price), "quantity": int(row.quantity)}
        if row.variant_id:
            item["item_variant"] = _clean(row.variant_id, 64)
        items.append(item)
    return _event("purchase", f"purchase:{order.code}", items, value=iso_amount(order.grand_total), transaction_id=order.code,
                  tax=iso_amount(order.tax), shipping=iso_amount(order.shipping_cost), coupon=_clean(order.coupon.code, 40) if order.coupon_id else "")
