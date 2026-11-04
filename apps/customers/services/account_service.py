"""دادهٔ «حساب مشتری» به‌صورت Store-scoped.

``Customer`` عمداً سراسری است (یک هویت، چند فروشگاه)، امّا هر چیزی که تجاریِ یک فروشگاه است (سفارش‌ها، آمار خرید، سطحِ مشتری)
فقط از رویِ همان فروشگاهِ جاری خوانده می‌شود: هیچ سفارش/مبلغ/وضعیتی از فروشگاهِ دیگر در صفحه‌ی حساب نمی‌آید.
آمار هرگز از فیلدهای سراسریِ ``Customer.orders_count/total_spent`` (که مجموعِ همه‌ی فروشگاه‌ها می‌شود) خوانده نمی‌شود."""

from __future__ import annotations

from django.db.models import Count, Q, Sum

from apps.customers.models import CustomerProfile
from apps.orders.models import Order


def store_orders(store, customer):
    return Order.objects.filter(store=store, customer=customer)


def store_summary(store, customer) -> dict:
    """``{"orders_count", "total_spent", "is_vip"}`` — فقط همین فروشگاه. مجموع خرید = سفارش‌های پرداخت‌شده‌ی غیرلغوشده."""
    agg = store_orders(store, customer).aggregate(
        orders_count=Count("pk"),
        total_spent=Sum("grand_total", filter=Q(payment_status=Order.PaymentStatus.PAID) & ~Q(status=Order.Status.CANCELED)),
    )
    profile = CustomerProfile.objects.filter(store=store, customer=customer).only("internal_status").first()
    return {
        "orders_count": agg["orders_count"] or 0,
        "total_spent": agg["total_spent"] or 0,
        # فقط «ویژه» به مشتری نشان داده می‌شود؛ وضعیت‌های داخلی دیگر (مثلاً «تحتِ نظر») هرگز.
        "is_vip": bool(profile and profile.internal_status == CustomerProfile.InternalStatus.VIP),
    }
