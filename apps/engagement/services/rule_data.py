"""بارگذاریِ دسته‌ایِ دادهٔ تاریخیِ سفارش‌ها/مشتریان برایِ موتورِ قواعد.

تصمیمِ مهم: قواعدِ محصول از **اسنپ‌شاتِ تاریخیِ ردیفِ سفارش**
(``OrderItem.attributes_snapshot``) ارزیابی می‌شوند، نه از وضعیتِ فعلیِ
کاتالوگ؛ برایِ ردیف‌هایِ قدیمی (بدونِ اسنپ‌شات) بازسازیِ زنده با علامتِ
``source="live"`` استفاده می‌شود."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Exists, Max, Min, OuterRef, Subquery, Sum
from django.utils import timezone

from apps.core.jalali_utils import store_timezone
from apps.customers.models import Address, Customer, CustomerProfile, CustomerSegmentMembership
from apps.orders.models import CouponRedemption, Order, ReturnRequest
from apps.orders.services import order_definitions
from apps.orders.services.item_snapshot_service import effective_item_snapshot

ZERO = Decimal("0")


@dataclass
class LineView:
    product_id: int | None
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    snapshot: dict


@dataclass
class OrderView:
    pk: int
    code: str
    created_at: dt.datetime  # در منطقه‌ی زمانیِ فروشگاه
    grand_total: Decimal
    items_total: Decimal
    refunded: Decimal
    shipping_cost: Decimal
    status: str
    payment_status: str
    gateway_id: int | None
    shipping_method_id: int | None
    province: str
    city: str
    coupon_id: int | None
    discount_total: Decimal
    has_return: bool
    #: ``None`` = not loaded yet. Rules that never look at order lines (order totals/counts/cities…) never
    #: pay for loading them; ``get_lines()`` loads the whole chunk's lines with a handful of queries.
    lines: list | None = None
    _loader: object = field(default=None, repr=False, compare=False)

    def get_lines(self) -> list:
        if self.lines is None:
            self.lines = self._loader(self.pk) if self._loader is not None else []
        return self.lines

    def amount(self, basis: str) -> Decimal:
        if basis == "items_total":
            return self.items_total
        if basis == "grand_total":
            return self.grand_total
        return max(ZERO, self.grand_total - self.refunded)

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.get_lines())


@dataclass
class CustomerFacts:
    customer: Customer
    lifetime_orders: int = 0
    lifetime_spent: Decimal = ZERO
    first_purchase: dt.datetime | None = None
    last_purchase: dt.datetime | None = None
    province: str = ""
    city: str = ""
    segment_ids: set = field(default_factory=set)
    tag_ids: set = field(default_factory=set)
    campaign_ids: set = field(default_factory=set)
    redeemed_coupon_ids: set = field(default_factory=set)

    @property
    def average_order_value(self) -> Decimal:
        return (self.lifetime_spent / self.lifetime_orders) if self.lifetime_orders else ZERO


def store_customer_ids(store):
    """مشتریانِ این Store: کسانی که از این فروشگاه سفارش دارند یا پروفایلِ
    Store‌-scoped دارند. (Customer سراسری است؛ این تنها مرزِ ایزولاسیون است.)"""
    from_orders = set(Order.objects.filter(store=store).values_list("customer_id", flat=True).distinct())
    from_profiles = set(CustomerProfile.objects.filter(store=store).values_list("customer_id", flat=True))
    return from_orders | from_profiles


def valid_orders_qs(store, valid_statuses, start=None, end=None):
    """تعریفِ مشترکِ «سفارشِ معتبر» — ``apps.orders.services.order_definitions``."""
    return order_definitions.valid_orders(store, valid_statuses, start, end)


def customers_with_valid_orders(store, valid_statuses, start=None, end=None) -> set:
    return set(valid_orders_qs(store, valid_statuses, start, end).values_list("customer_id", flat=True).distinct())


class _ChunkLines:
    """بارگذاریِ تنبلِ ردیف‌هایِ همه‌ی سفارش‌هایِ یک دسته — با اولین نیاز، همه با چند query (نه N+1)."""

    def __init__(self, order_ids):
        self.order_ids = list(order_ids)
        self.by_order = None

    def __call__(self, order_pk):
        if self.by_order is None:
            from django.db.models import Prefetch

            from apps.catalog.models import ProductAttributeValue
            from apps.orders.models import OrderItem

            items = (
                OrderItem.objects.filter(order_id__in=self.order_ids)
                .select_related("product", "product__brand", "product__category", "product__category__parent", "variant")
                .prefetch_related(
                    Prefetch("product__attribute_values", queryset=ProductAttributeValue.objects.select_related("attribute", "value")),
                    "variant__option_values__option__attribute", "variant__option_values__option_value",
                )
                .order_by("order_id", "pk")
            )
            self.by_order = {}
            for item in items:
                self.by_order.setdefault(item.order_id, []).append(LineView(
                    product_id=item.product_id, sku=item.sku, name=item.product_name, quantity=item.quantity,
                    unit_price=item.unit_price, line_total=item.line_total, snapshot=effective_item_snapshot(item),
                ))
        return self.by_order.get(order_pk, [])


def _order_views(orders, tz) -> list[OrderView]:
    loader = _ChunkLines(o.pk for o in orders)
    views = []
    for order in orders:
        address = order.address or {}
        views.append(OrderView(
            pk=order.pk, code=order.code, created_at=order.created_at.astimezone(tz),
            grand_total=order.grand_total, items_total=order.items_total, refunded=order.refunded_sum or ZERO,
            shipping_cost=order.shipping_cost, status=order.status, payment_status=order.payment_status,
            gateway_id=order.payment_gateway_id, shipping_method_id=order.shipping_method_id,
            province=address.get("province", ""), city=address.get("city", ""), coupon_id=order.coupon_id,
            discount_total=order.product_discount + order.coupon_discount, has_return=order.has_return,
            _loader=loader,
        ))
    return views


def load_orders(store, customer_ids, valid_statuses, start=None, end=None):
    """→ ``(valid_by_customer, all_by_customer)`` — فقط سفارش‌هایِ همین Store و
    بازه‌ی نیم‌باز ``[start, end)``. ``valid``: وضعیتِ پرداختِ معتبر و لغونشده؛
    ``all``: همه‌ی وضعیت‌ها (برایِ قواعدِ لغو/مرجوعی/استرداد)."""
    tz = store_timezone()
    refunded = order_definitions.refunded_amount_subquery(OuterRef("pk"))
    returned = ReturnRequest.objects.filter(order=OuterRef("pk")).exclude(
        status__in=(ReturnRequest.Status.REJECTED, ReturnRequest.Status.CANCELLED, ReturnRequest.Status.REQUESTED),
    )
    qs = (
        Order.objects.filter(store=store, customer_id__in=list(customer_ids))
        .annotate(refunded_sum=Subquery(refunded), has_return=Exists(returned))
        .order_by("created_at", "pk")
    )
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    valid_by, all_by = {}, {}
    orders = list(qs)
    views = {o.pk: v for o, v in zip(orders, _order_views(orders, tz))}
    for order in orders:
        view = views[order.pk]
        all_by.setdefault(order.customer_id, []).append(view)
        if order.payment_status in valid_statuses and order.status != Order.Status.CANCELED:
            valid_by.setdefault(order.customer_id, []).append(view)
    return valid_by, all_by


def load_facts(store, customer_ids, valid_statuses) -> dict[int, CustomerFacts]:
    from apps.engagement.models import CampaignIssuance

    ids = list(customer_ids)
    tz = store_timezone()
    customers = {c.pk: c for c in Customer.objects.filter(pk__in=ids)}
    facts = {cid: CustomerFacts(customer=c) for cid, c in customers.items()}

    stats = (
        valid_orders_qs(store, valid_statuses).filter(customer_id__in=ids).values("customer_id")
        .annotate(n=Count("id"), spent=Sum("grand_total"), first=Min("created_at"), last=Max("created_at"))
    )
    for row in stats:
        f = facts[row["customer_id"]]
        f.lifetime_orders = row["n"]
        f.lifetime_spent = row["spent"] or ZERO
        f.first_purchase = row["first"].astimezone(tz) if row["first"] else None
        f.last_purchase = row["last"].astimezone(tz) if row["last"] else None

    seen = set()
    for addr in Address.objects.filter(customer_id__in=ids).order_by("-is_default", "-created_at"):
        if addr.customer_id not in seen:
            seen.add(addr.customer_id)
            facts[addr.customer_id].province = addr.province
            facts[addr.customer_id].city = addr.city

    for m in CustomerSegmentMembership.objects.filter(segment__store=store, customer_id__in=ids):
        facts[m.customer_id].segment_ids.add(m.segment_id)
    for profile in CustomerProfile.objects.filter(store=store, customer_id__in=ids).prefetch_related("tags"):
        facts[profile.customer_id].tag_ids.update(t.pk for t in profile.tags.all())
    for cid, camp in CampaignIssuance.objects.filter(campaign__store=store, customer_id__in=ids).values_list("customer_id", "campaign_id"):
        facts[cid].campaign_ids.add(camp)
    for cid, coupon_id in CouponRedemption.objects.filter(
        coupon__store=store, customer_id__in=ids, status__in=CouponRedemption.COUNTED_STATUSES,
    ).values_list("customer_id", "coupon_id"):
        facts[cid].redeemed_coupon_ids.add(coupon_id)
    return facts


def utcnow():
    return timezone.now()
