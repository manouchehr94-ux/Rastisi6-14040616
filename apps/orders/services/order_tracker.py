"""ردیابِ گرافیکیِ سفارش برایِ مشتری — «پرداخت» و «اجرایِ سفارش» دو مسیرِ مستقل.

همه‌چیز از دادهٔ واقعیِ ``Order`` / ``OrderStatusHistory`` / ``CardTransferSubmission`` / ``Transaction`` می‌آید؛ مرحله‌ای که داده‌ی
واقعی ندارد هرگز «انجام‌شده» نشان داده نمی‌شود (مثلاً «بسته‌بندی شد» یا «آماده‌ی تحویل» وجود ندارد چون وضعیتِ واقعی ندارد).
پرداختِ موفق به معنایِ ارسال/تحویل نیست: مسیرِ پرداخت و مسیرِ اجرا جدا محاسبه و جدا نمایش داده می‌شوند. این ماژول فقط می‌خواند."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from apps.orders.models import CardTransferSubmission, Order

DONE, CURRENT, TODO, FAILED = "done", "current", "todo", "failed"
S = CardTransferSubmission.Status


@dataclass
class Step:
    key: str
    label: str
    state: str
    at: datetime | None = None
    note: str = ""


@dataclass
class Track:
    title: str
    steps: list
    headline: str = ""
    description: str = ""
    tone: str = "info"          # info | ok | warn | danger
    state_key: str = ""


@dataclass
class OrderTracker:
    payment: Track
    fulfillment: Track
    summary: str
    submissions: list = field(default_factory=list)       # تاریخچه‌ی ثبت‌هایِ کارت‌به‌کارت (جدید → قدیم)
    rejection: CardTransferSubmission | None = None       # فقط وقتی «آخرین» ثبت ردشده و ثبتِ بازِ دیگری نیست
    can_resubmit: bool = False
    is_card_transfer: bool = False


def _first_time(order: Order, status: str):
    for entry in order.status_history.all():
        if entry.to_status == status:
            return entry.created_at
    return None


def _history_times(order: Order) -> dict:
    """نخستین زمانِ هر وضعیت (قدیمی‌ترین ردیفِ تاریخچه)؛ تاریخچه‌ی ناقصِ سفارش‌هایِ قدیمی بی‌خطا پشتیبانی می‌شود."""
    times: dict = {}
    for entry in sorted(order.status_history.all(), key=lambda e: (e.created_at, e.pk)):
        times.setdefault(entry.to_status, entry.created_at)
    return times


def _payment_time(order: Order):
    tx = next((t for t in order.transactions.all() if t.status == "ok"), None)
    return (tx.confirmed_at or tx.created_at) if tx else None


def build(order: Order) -> OrderTracker:
    """``order`` باید با ``prefetch_related("status_history", "transactions", "card_transfers")`` و ``select_related("payment_gateway")`` بیاید."""
    gateway_slug = order.payment_gateway.slug if order.payment_gateway_id else ""
    is_c2c = gateway_slug == "card_to_card"
    is_cod = gateway_slug == "cod"
    canceled = order.status == Order.Status.CANCELED
    paid = order.payment_status == Order.PaymentStatus.PAID
    submissions = sorted(order.card_transfers.all(), key=lambda s: (s.created_at, s.pk), reverse=True) if is_c2c else []
    latest = submissions[0] if submissions else None
    times = _history_times(order)

    # ───────── مسیرِ پرداخت ─────────
    placed = Step("placed", "ثبت سفارش", DONE, order.created_at)
    if order.payment_status == Order.PaymentStatus.REFUNDED:
        payment = Track("پرداخت", [placed, Step("paid", "پرداخت دریافت شد", DONE, _payment_time(order)), Step("refund", "مسترد شد", FAILED)],
                        "مبلغ سفارش مسترد شده است", "استرداد طبق ثبتِ فروشگاه انجام شده است.", "warn", "refunded")
    elif order.payment_status == Order.PaymentStatus.FAILED:
        payment = Track("پرداخت", [placed, Step("pay", "پرداخت", FAILED)], "پرداخت ناموفق بود",
                        "پرداختی ثبت نشد. اگر مبلغی کسر شده، با فروشگاه تماس بگیرید.", "danger", "failed")
    elif is_c2c:
        if paid:
            steps = [placed, Step("transfer", "ثبت اطلاعات واریز", DONE, latest.created_at if latest else None),
                     Step("review", "بررسی فروشگاه", DONE, latest.reviewed_at if latest else None),
                     Step("paid", "پرداخت تأیید شد", DONE, _payment_time(order))]
            payment = Track("پرداخت", steps, "پرداخت تأیید شد", "فروشگاه واریز شما را تأیید کرد.", "ok", "approved")
        elif latest is None:
            steps = [placed, Step("transfer", "واریز و ثبت اطلاعات", CURRENT), Step("review", "بررسی فروشگاه", TODO), Step("paid", "پرداخت تأیید شد", TODO)]
            payment = Track("پرداخت", steps, "در انتظار واریز و ثبت اطلاعات",
                            "مبلغ را به کارتِ فروشگاه واریز کنید و ۴ رقمِ آخرِ کارتِ خود و شماره‌ی پیگیری را ثبت کنید.", "warn", "awaiting_transfer")
        elif latest.status == S.SUBMITTED:
            again = len(submissions) > 1
            steps = [placed, Step("transfer", "اطلاعات واریز ثبت شد", DONE, latest.created_at), Step("review", "بررسی فروشگاه", CURRENT), Step("paid", "پرداخت تأیید شد", TODO)]
            payment = Track("پرداخت", steps, "اطلاعاتِ جدید برای بررسی دوباره ثبت شد" if again else "در انتظار بررسی پرداخت",
                            "فروشگاه واریز را بررسی می‌کند؛ تا تأیید، سفارش پرداخت‌نشده است.", "info", "resubmitted" if again else "under_review")
        else:  # آخرین ثبت ردشده
            steps = [placed, Step("transfer", "اطلاعات واریز ثبت شد", DONE, latest.created_at),
                     Step("review", "پرداخت تأیید نشد", FAILED, latest.reviewed_at), Step("paid", "پرداخت تأیید شد", TODO)]
            payment = Track("پرداخت", steps, "پرداخت تأیید نشد — نیازمند اصلاح", "اطلاعاتِ درست را دوباره ثبت کنید.", "danger", "rejected")
    elif is_cod:
        if paid:
            payment = Track("پرداخت", [placed, Step("cod", "پرداخت هنگام تحویل", DONE), Step("paid", "مبلغ دریافت شد", DONE, _payment_time(order))],
                            "مبلغ دریافت شد", "فروشگاه دریافت وجه را ثبت کرده است.", "ok", "paid")
        else:
            payment = Track("پرداخت", [placed, Step("cod", "پرداخت هنگام تحویل", CURRENT), Step("paid", "مبلغ دریافت شد", TODO)],
                            "پرداخت هنگام تحویل", "مبلغ هنگام تحویل سفارش پرداخت می‌شود.", "info", "cod_pending")
    elif paid:
        payment = Track("پرداخت", [placed, Step("pay", "پرداخت آنلاین", DONE), Step("paid", "پرداخت تأیید شد", DONE, _payment_time(order))],
                        "پرداخت تأیید شد", "پرداخت شما با موفقیت انجام شد.", "ok", "paid")
    else:
        payment = Track("پرداخت", [placed, Step("pay", "پرداخت", CURRENT), Step("paid", "پرداخت تأیید شد", TODO)],
                        "در انتظار پرداخت", "پرداختِ این سفارش هنوز کامل نشده است.", "warn", "pending")

    # ───────── مسیرِ اجرایِ سفارش (فقط وضعیت‌هایِ واقعیِ Order.Status) ─────────
    pickup = bool(order.is_pickup)
    last_label = "تحویلِ حضوری انجام شد" if pickup else "تحویل داده شد"
    f_placed = Step("placed", "ثبت سفارش", DONE, order.created_at)
    if canceled:
        fulfillment = Track("اجرای سفارش", [f_placed, Step("canceled", "لغو شد", FAILED, times.get(Order.Status.CANCELED))],
                            "سفارش لغو شده است", "این سفارش لغو شده و ادامه نمی‌یابد.", "danger", "canceled")
    else:
        rank = {Order.Status.PENDING: 0, Order.Status.PROCESSING: 1, Order.Status.SHIPPED: 2, Order.Status.DELIVERED: 3}[order.status]
        defs = [("processing", "در حال پردازش", 1, times.get(Order.Status.PROCESSING))]
        # «ارسال‌شده» تنها وضعیتِ واقعیِ میانیِ سفارش است؛ برایِ تحویلِ حضوری همان وضعیت با برچسبِ حضوری نمایش داده می‌شود.
        defs.append(("shipped", "آماده‌ی دریافت حضوری" if pickup else "ارسال شد", 2, times.get(Order.Status.SHIPPED)))
        defs.append(("delivered", last_label, 3, times.get(Order.Status.DELIVERED)))
        steps = [f_placed]
        for key, label, need, at in defs:
            if rank > need or (rank == need and key == "delivered"):
                state = DONE
            elif rank == need:
                state = CURRENT
            else:
                state = TODO
            steps.append(Step(key, label, state, at))
        if rank == 0:
            f_placed.state = CURRENT if not paid and not is_cod else DONE
        notes = {
            0: ("سفارش ثبت شده است", "فروشگاه پس از تأیید پرداخت سفارش را به پردازش می‌برد." if not (paid or is_cod) else "فروشگاه به‌زودی سفارش را به پردازش می‌برد.", "info"),
            1: ("سفارش در حال پردازش است", "فروشگاه در حال آماده‌سازی سفارش شماست.", "info"),
            2: ("سفارش ارسال شده است" if not pickup else "سفارش آماده‌ی دریافت حضوری است",
                "سفارش شما تحویل مرسوله‌بر شده است." if not pickup else "برای دریافت سفارش به فروشگاه مراجعه کنید.", "info"),
            3: ("سفارش تحویل داده شد", "سفارش شما تحویل شد." if not pickup else "سفارش شما به‌صورت حضوری تحویل شد.", "ok"),
        }
        headline, desc, tone = notes[rank]
        fulfillment = Track("اجرای سفارش", steps, headline, desc, tone, order.status)

    # ───────── خلاصه‌ی یک‌خطی (پرداخت و اجرا جدا گفته می‌شوند) ─────────
    if canceled:
        summary = "سفارش لغو شده است."
    elif paid and rank_of(order) == 1:
        summary = "پرداخت شما تأیید شده و فروشگاه در حال آماده‌سازی سفارش است."
    elif paid:
        summary = f"پرداخت تأیید شده است. {fulfillment.headline}."
    elif payment.state_key in ("under_review", "resubmitted"):
        summary = "اطلاعات واریز شما ثبت شده و در انتظار بررسی فروشگاه است؛ سفارش هنوز پرداخت‌نشده است."
    elif payment.state_key == "rejected":
        summary = "پرداخت شما تأیید نشد؛ لطفاً اطلاعات واریز را اصلاح و دوباره ثبت کنید."
    elif payment.state_key == "cod_pending":
        summary = f"{fulfillment.headline}؛ مبلغ هنگام تحویل پرداخت می‌شود."
    else:
        summary = payment.headline + "."

    rejection = latest if (is_c2c and latest is not None and latest.status == S.REJECTED and not paid) else None
    can_resubmit = bool(is_c2c and not paid and not canceled and (latest is None or latest.status == S.REJECTED))
    return OrderTracker(payment, fulfillment, summary, submissions, rejection, can_resubmit, is_c2c)


def rank_of(order: Order) -> int:
    return {Order.Status.PENDING: 0, Order.Status.PROCESSING: 1, Order.Status.SHIPPED: 2, Order.Status.DELIVERED: 3}.get(order.status, -1)
