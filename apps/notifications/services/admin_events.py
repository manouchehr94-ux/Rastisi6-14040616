"""نقاطِ اتصالِ رویدادهایِ واقعیِ RastiSi به موتورِ اعلانِ مدیران — هر تابع از یک Trigger موجود صدا زده می‌شود و ``safe_publish`` می‌کند (هرگز استثنا نمی‌اندازد،
در همان تراکنشِ کسب‌وکار انجام می‌شود). متن‌ها عمداً بدونِ نام/تلفن/آدرسِ مشتری و بدونِ هرگونه Secret نوشته شده‌اند (فقط کدِ سفارش/مبلغ/نامِ کالا)."""

from __future__ import annotations

from django.utils import timezone

from apps.core.utils import format_toman
from apps.notifications.registry import CRITICAL, IMPORTANT
from apps.notifications.services.inbox_engine import safe_publish


def order_created(order):
    safe_publish("order.created", store=order.store, title=f"سفارش جدید {order.code}", summary=f"مبلغ {format_toman(order.grand_total, with_unit=False)} تومان",
                 entity=("Order", order.pk), link_kwargs={"code": order.code}, dedupe_key=f"order:{order.pk}")


def order_canceled(order):
    safe_publish("order.canceled", store=order.store, title=f"سفارش {order.code} لغو شد", entity=("Order", order.pk), link_kwargs={"code": order.code},
                 dedupe_key=f"order-canceled:{order.pk}")


def payment_failed(order):
    """مسیرِ شبیه‌سازی/توسعه (``simulate_payment``): پرداختِ شبیه‌سازی‌شده ناموفق شد."""
    safe_publish("payment.failed", store=order.store, title="تلاش پرداخت ناموفق بود", summary=f"پرداختِ سفارش {order.code} کامل نشد.", entity=("Order", order.pk),
                 link_kwargs={"code": order.code}, group_key=f"pay-failed:order:{order.pk}")


def payment_attempt_failed(order, attempt_public_id: str):
    """یک «تلاشِ پرداختِ» واقعی را درگاه قطعاً ناموفق اعلام کرد. این به‌معنیِ شکستِ نهاییِ سفارش نیست: سفارش باز است و مشتری می‌تواند دوباره تلاش کند.
    dedupe: شناسه‌ی پایدارِ تلاش (callbackِ تکراری ⇒ هیچ اعلانِ دوم)؛ تلاش‌هایِ مجددِ همان سفارش در یک ردیفِ صندوق (شمارنده) تجمیع می‌شوند."""
    safe_publish("payment.failed", store=order.store, title="تلاش پرداخت ناموفق بود",
                 summary=f"درگاه پرداختِ سفارش {order.code} را تأیید نکرد؛ سفارش هنوز باز است و مشتری می‌تواند دوباره تلاش کند.",
                 entity=("Order", order.pk), link_kwargs={"code": order.code}, dedupe_key=f"payattempt:{attempt_public_id}", group_key=f"pay-failed:order:{order.pk}")


def return_requested(return_request):
    safe_publish("return.requested", store=return_request.store, title=f"درخواست مرجوعی {return_request.return_number}",
                 summary=f"برای سفارش {return_request.order.code}", entity=("ReturnRequest", return_request.pk), link_kwargs={"pk": return_request.pk},
                 dedupe_key=f"return:{return_request.pk}")


def refund_completed(refund):
    order = refund.order
    safe_publish("refund.completed", store=refund.store, title=f"بازپرداخت سفارش {order.code} انجام شد",
                 summary=f"مبلغ {format_toman(refund.approved_amount, with_unit=False)} تومان", entity=("Refund", refund.pk),
                 link_kwargs={"code": order.code}, dedupe_key=f"refund:{refund.pk}")


def suspicious_payment(record, *, upgraded: bool = False):
    safe_publish("payment.suspicious", store=record.store, title="پرداخت مشکوک / مغایرت نیازمند رسیدگی",
                 summary=f"سفارش {record.order.code} — {record.get_kind_display()}", entity=("PaymentReconciliation", record.pk),
                 dedupe_key=f"reconcile:{record.pk}" + (":confirmed" if upgraded else ""), severity=CRITICAL)


def review_pending(review, store):
    safe_publish("review.pending", store=store, title="نظر جدید نیازمند بررسی", summary=f"برای «{review.product.name}»", entity=("Review", review.pk),
                 group_key=f"reviews:{store.pk}")


def card_transfer_submitted(submission):
    safe_publish("payment.card_transfer_submitted", store=submission.store, title="رسید کارت‌به‌کارت منتظر بررسی",
                 summary=f"سفارش {submission.order.code} — {format_toman(submission.amount, with_unit=False)} تومان", entity=("CardTransferSubmission", submission.pk),
                 dedupe_key=f"c2c:{submission.pk}")


def import_failed(job):
    safe_publish("import.failed", store=job.store, title="ورود گروهی ناموفق بود", summary=f"{job.get_import_type_display()} — هیچ تغییری اعمال نشد.",
                 entity=("ImportJob", job.pk), link_kwargs={"pk": job.pk}, dedupe_key=f"import-failed:{job.pk}")


def stock_crossed(store, product, variant, stock_before: int, stock_after: int, threshold: int):
    """فقط لحظه‌ی «عبور» از آستانه یا رسیدن به صفر اعلان می‌شود (نه هر کاهشِ موجودی)."""
    name = product.name + (f" — {variant}" if variant is not None else "")
    if stock_after <= 0 < stock_before:
        safe_publish("stock.out", store=store, title="موجودی تمام شد", summary=name, entity=("Product", product.pk), group_key=f"stock:{store.pk}:{product.pk}")
    elif stock_before > threshold >= stock_after > 0:
        safe_publish("stock.low", store=store, title="موجودی کم شد", summary=f"{name} — {stock_after} عدد مانده", entity=("Product", product.pk),
                     group_key=f"stock:{store.pk}:{product.pk}")


def role_changed(membership, old_role: str):
    safe_publish("staff.role_changed", store=membership.store, title="نقش یک عضو تغییر کرد",
                 summary=f"«{membership.user.get_username()}» اکنون {membership.get_role_display()} است.", entity=("StoreMembership", membership.pk),
                 dedupe_key=f"role:{membership.pk}:{membership.role}:{timezone.now():%Y%m%d%H%M}")


def access_revoked(membership):
    safe_publish("staff.access_revoked", store=membership.store, title="دسترسیِ یک عضو لغو شد", summary=f"«{membership.user.get_username()}»",
                 entity=("StoreMembership", membership.pk), dedupe_key=f"revoked:{membership.pk}")


def subscription_state(subscription, kind: str):
    """``kind``: grace (مهلتِ ارفاقی؛ مسیرِ واقعیِ dunning/ارزیابی) | past_due (حالتِ PAST_DUE — در تولید فراخوانِ واقعی ندارد) | suspended.
    dedupe روی «آخرین رخدادِ گذار» (``SubscriptionEvent``) ⇒ هر گذارِ واقعی دقیقاً یک اعلان؛ اجرای تکراری هیچ‌چیز نمی‌سازد."""
    key = {"grace": "subscription.grace_period", "past_due": "subscription.past_due", "suspended": "subscription.suspended"}[kind]
    label = {"grace": "مهلت ارفاقی اشتراک شروع شد", "past_due": "اشتراک معوق شد", "suspended": "اشتراک تعلیق شد"}[kind]
    summary = {"grace": "برای جلوگیری از تعلیق، صورتحساب/تمدید اشتراک را در مهلت ارفاقی پرداخت کنید.",
               "past_due": "برای جلوگیری از محدودشدنِ فروشگاه، صورتحساب را بررسی کنید.",
               "suspended": "برای جلوگیری از محدودشدنِ فروشگاه، صورتحساب را بررسی کنید."}[kind]
    last = subscription.events.order_by("-id").values_list("pk", flat=True).first()
    safe_publish(key, store=subscription.store, title=label, summary=summary, entity=("StoreSubscription", subscription.pk),
                 dedupe_key=f"sub:{subscription.pk}:{kind}:{last or ''}")


def domain_verification(domain, ok: bool):
    if ok:
        safe_publish("domain.verified", store=domain.store, title="دامنه تأیید شد", summary=domain.hostname, entity=("StoreDomain", domain.pk),
                     dedupe_key=f"domain-ok:{domain.pk}")
    else:
        safe_publish("domain.verification_failed", store=domain.store, title="تأیید دامنه هنوز انجام نشد", summary=f"{domain.hostname}: رکورد DNS پیدا نشد.",
                     entity=("StoreDomain", domain.pk), group_key=f"domain:{domain.pk}")


def automation_failed(store, operation: str, reason: str):
    safe_publish("integration.sync_failed", store=store, title="عملیات خودکار با خطا روبه‌رو شد", summary=f"{operation}: {reason}"[:200], entity=("Automation", operation),
                 group_key=f"automation:{store.pk}:{operation}", metadata={"operation": operation})


# ---- پلتفرم -----------------------------------------------------------------------------------------------------------------------------
def platform_store_created(store):
    safe_publish("platform.store_created", title="فروشگاه جدید ساخته شد", summary=store.name, entity=("Store", store.pk), dedupe_key=f"store-created:{store.pk}")


def platform_store_status(store, status_label: str):
    safe_publish("platform.store_status_changed", title=f"وضعیت فروشگاه «{store.name}» تغییر کرد", summary=status_label, entity=("Store", store.pk),
                 dedupe_key=f"store-status:{store.pk}:{status_label}:{timezone.now():%Y%m%d%H%M}")


def platform_contact_message(message):
    safe_publish("platform.contact_message", title="پیام جدید از فرم تماس", summary="یک پیام تازه در انتظار بررسی است.", entity=("ContactMessage", message.pk), group_key="contact")


def platform_jobs_unhealthy(problems: list[str]):
    safe_publish("platform.jobs_unhealthy", title="کارهای زمان‌بندی‌شده مشکل دارند", summary="، ".join(problems)[:250],
                 dedupe_key=f"jobs:{timezone.now():%Y%m%d%H}", severity=CRITICAL)
