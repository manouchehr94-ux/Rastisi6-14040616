"""یک‌جا کردنِ گذارِ «پرداختِ تأییدشده» (L1) — حداقلیِ لازم، نه بازنویسیِ سیستمِ سفارش.

پیش از این، همین دنباله‌ی هفت‌مرحله‌ای (پرداخت‌شده‌شدن، مصرفِ کد، رویدادِ اعلان، hookِ
کمپین، تراکنشِ سازگاری، گذار به PROCESSING، پیامکِ on_commit) دو بار کپی شده بود:
``payment_service.simulate_payment`` و ``gateway_payment_service.process_callback_and_verify``.
هر دو اکنون فقط این تابع را صدا می‌زنند؛ نگهبان‌ها (چه وضعیتی قابل پرداخت است،
idempotency، تولیدِ ref_id) نزدِ فراخوان می‌مانند.

صراحتاً **خارج از دامنه**: لغو (``order_service.change_order_status`` از قبل تنها مسیر است)،
استرداد (``refund_service.execute_order_refund`` تنها مسیر است)، شکستِ پرداخت (یک مسیر)،
و پرداخت در محل — ``COD`` هرگز این تابع را صدا نمی‌زند و هرگز خودکار «پرداخت‌شده» نمی‌شود."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.engagement import hooks as engagement_hooks
from apps.notifications.services import business_events
from apps.orders.models import Order, Transaction
from apps.orders.services.coupon_redemption_service import mark_redeemed


def apply_payment_success(
    order: Order, *, store, ref_id: str, note: str, from_statuses=None, gateway=None,
    advance_to_processing: bool = True, send_sms: bool = True, method: str = Transaction.Method.GATEWAY,
    confirmed_by=None,
) -> Transaction | None:
    """سفارش را «پرداخت‌شده» می‌کند و همه‌ی اثرهای جانبیِ این گذار را دقیقاً یک‌بار اجرا می‌کند.

    ``advance_to_processing=False``: وضعیتِ سفارش دست‌نخورده می‌ماند (تأییدِ دریافتِ COD — سفارش ممکن است
    ارسال‌شده/تحویل‌شده باشد). ``send_sms=False``: پیامکِ «پرداخت موفق» ارسال نمی‌شود (ایمیلِ رخداد همچنان).
    ``method``/``confirmed_by``: برایِ تأییدِ دستی روی تراکنش ثبت می‌شود.
    ``gateway``: درگاهِ ثبت‌شده در تراکنشِ سازگاری (پیش‌فرض: درگاهِ سفارش).
    ``from_statuses``: وضعیت‌هایِ پرداختی که این گذار از آن‌ها مجاز است؛ ``None`` یعنی هر وضعیتِ
    غیر از ``paid``. گذار با یک UPDATE شرطی انجام می‌شود (رقابتِ دو درخواستِ همزمان: فقط یکی
    برنده است). اگر شرط برقرار نبود → ``None`` و **هیچ اثرِ جانبی‌ای** اجرا نمی‌شود.

    باید داخلِ ``transaction.atomic`` فراخوانی شود (هر دو فراخوان همین‌طورند): اگر هر مرحله
    خطا دهد (مثلاً سفارشِ لغوشده که دیگر به PROCESSING نمی‌رود) همه‌چیز برمی‌گردد."""
    from apps.orders.services.order_service import _order_sms_context, change_order_status
    from apps.orders.services.payment_service import _generate_transaction_code
    from apps.sms.events import SmsEvent
    from apps.sms.services.sms_service import send_event_sms

    qs = Order.objects.filter(pk=order.pk)
    qs = qs.filter(payment_status__in=list(from_statuses)) if from_statuses else qs.exclude(payment_status=Order.PaymentStatus.PAID)
    if qs.update(payment_status=Order.PaymentStatus.PAID, updated_at=timezone.now()) == 0:
        return None
    order.refresh_from_db(fields=["payment_status", "updated_at"])

    mark_redeemed(order)
    business_events.payment_result(order, success=True)
    engagement_hooks.on_payment_success(order)

    tx = Transaction.objects.create(
        code=_generate_transaction_code(), order=order, gateway=gateway or order.payment_gateway,
        amount=order.grand_total, status=Transaction.Status.OK, ref_id=ref_id, method=method,
        confirmed_by=confirmed_by, confirmed_at=timezone.now() if confirmed_by is not None else None,
    )
    if advance_to_processing:
        change_order_status(order, Order.Status.PROCESSING, note=note, store=store)
    if send_sms:
        transaction.on_commit(
            lambda: send_event_sms(SmsEvent.PAYMENT_SUCCESS, order.customer.phone, _order_sms_context(order), store=store)
        )
    return tx
