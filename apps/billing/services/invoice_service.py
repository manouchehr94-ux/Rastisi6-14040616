"""ساخت/بازکردن/محاسبه‌ی فاکتورهایِ اشتراک (ADR-74).

قواعد کلیدی:
- فاکتور در وضعیتِ ``draft`` ساخته می‌شود؛ ردیف‌ها فقط در حالتِ draft قابلِ
  افزودن‌اند. با ``open_invoice`` فاکتور به ``open`` می‌رود، ``issued_at`` ست
  می‌شود و از آن پس ردیف‌ها و مبالغِ مالیِ تاریخی تغییرناپذیرند.
- مبالغ فقط ``Decimal``‌اند؛ جمع‌ها از ردیف‌ها محاسبه می‌شوند، نه از ورودیِ
  مرورگر.
- شماره‌ی فاکتور از ``numbering_service`` (race-safe) می‌آید.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionInvoiceLine
from apps.billing.services import numbering_service
from apps.billing.services.account_service import get_or_create_billing_account
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.services import period_pricing

ZERO = Decimal("0")


class InvoiceError(Exception):
    """خطای قابل‌نمایش هنگام ساخت/تغییرِ فاکتور."""


def plan_version_snapshot(plan_version, billing_interval=None) -> dict:
    """اسنپ‌شاتِ تغییرناپذیر از شرایطِ نسخه‌ی پلن برایِ درج در فاکتور. ``billing_interval`` دوره‌ی خریداری‌شده است
    (پیش‌فرض: گزینه‌ی اصلیِ نسخه — رفتارِ قبلی)؛ قیمتِ ثبت‌شده همان قیمتِ همان دوره است."""
    interval = billing_interval or plan_version.billing_interval
    return {
        "plan_code": plan_version.plan.code,
        "plan_name": plan_version.plan.name,
        "version_number": plan_version.version_number,
        "currency": plan_version.currency,
        "billing_interval": interval,
        "display_price": str(plan_version.price_for(interval)),
    }


def invoice_billing_interval(invoice) -> str:
    """دوره‌ی خریداری‌شده‌ی یک فاکتور از اسنپ‌شاتِ ردیفِ پلن؛ فاکتورِ قدیمی/بدونِ اسنپ‌شات ⇒ دوره‌ی اصلیِ نسخه."""
    for line in invoice.lines.all():
        if line.line_type == SubscriptionInvoiceLine.LineType.PLAN:
            interval = (line.plan_version_snapshot or {}).get("billing_interval")
            if interval and invoice.plan_version.offers_interval(interval):
                return interval
    return invoice.plan_version.billing_interval


def plan_line_spec(plan_version, *, period_start=None, period_end=None, description="", billing_interval=None) -> dict:
    """یک ردیفِ «پلن» برایِ مبلغِ نسخه‌ی پلن (در دوره‌ی انتخابی) می‌سازد."""
    interval = billing_interval or plan_version.billing_interval
    if not plan_version.offers_interval(interval):
        raise InvoiceError("این نسخه‌ی پلن دوره‌ی انتخاب‌شده را عرضه نمی‌کند.")
    period_label = dict(plan_version.BillingInterval.choices).get(interval, "")
    default_description = f"اشتراکِ {plan_version.plan.name} (نسخه {plan_version.version_number})"
    if interval != plan_version.billing_interval and period_label:
        default_description += f" — {period_label}"
    return {
        "line_type": SubscriptionInvoiceLine.LineType.PLAN,
        "description": description or default_description,
        "quantity": Decimal("1"),
        "unit_amount": Decimal(plan_version.price_for(interval)),
        "discount": ZERO,
        "tax": ZERO,
        "plan_code_snapshot": plan_version.plan.code,
        "plan_version_snapshot": plan_version_snapshot(plan_version, interval),
        "service_period_start": period_start,
        "service_period_end": period_end,
        # ممیزیِ نحوه‌ی مشتق‌شدنِ مبلغ (دوره/ماه‌ها/تخفیف/جمعِ بدونِ تخفیف) — فقط توضیحی؛ مبلغِ ردیف همان ``unit_amount`` است.
        "metadata": period_pricing.invoice_metadata(plan_version, interval),
    }


def _build_line(invoice, spec) -> SubscriptionInvoiceLine:
    quantity = Decimal(spec.get("quantity", Decimal("1")))
    unit_amount = Decimal(spec.get("unit_amount", ZERO))
    discount = Decimal(spec.get("discount", ZERO))
    tax = Decimal(spec.get("tax", ZERO))
    subtotal = quantity * unit_amount
    total = subtotal - discount + tax
    return SubscriptionInvoiceLine(
        invoice=invoice,
        line_type=spec.get("line_type", SubscriptionInvoiceLine.LineType.PLAN),
        description=spec.get("description", ""),
        quantity=quantity, unit_amount=unit_amount, subtotal=subtotal,
        discount=discount, tax=tax, total=total,
        plan_code_snapshot=spec.get("plan_code_snapshot", ""),
        plan_version_snapshot=spec.get("plan_version_snapshot", {}),
        service_period_start=spec.get("service_period_start"),
        service_period_end=spec.get("service_period_end"),
        metadata=spec.get("metadata", {}),
    )


def recompute_totals(invoice):
    """جمع‌هایِ فاکتور را از ردیف‌هایش بازمحاسبه می‌کند (منبعِ حقیقت: ردیف‌ها)."""
    lines = list(invoice.lines.all())
    invoice.subtotal = sum((line.subtotal for line in lines), ZERO)
    invoice.discount_total = sum((line.discount for line in lines), ZERO)
    invoice.tax_total = sum((line.tax for line in lines), ZERO)
    invoice.grand_total = sum((line.total for line in lines), ZERO)
    invoice.recompute_amount_due()


@transaction.atomic
def create_invoice(subscription, *, kind, lines, plan_version=None, currency=None,
                   period_start=None, period_end=None, idempotency_key="", now=None, actor=None):
    """یک فاکتورِ draft با ردیف‌هایِ داده‌شده می‌سازد و جمع‌ها را محاسبه می‌کند.
    idempotent روی ``idempotency_key`` (به‌ازایِ فروشگاه)."""
    now = now or timezone.now()
    store = subscription.store
    plan_version = plan_version or subscription.plan_version
    currency = currency or plan_version.currency

    if idempotency_key:
        existing = SubscriptionInvoice.objects.filter(
            store=store, idempotency_key=idempotency_key,
        ).first()
        if existing is not None:
            return existing

    account = get_or_create_billing_account(store, currency=currency)

    invoice = SubscriptionInvoice(
        store=store, subscription=subscription, plan_version=plan_version,
        plan_code_snapshot=plan_version.plan.code,
        plan_version_snapshot=plan_version_snapshot(plan_version),
        billing_account_snapshot=account.snapshot(),
        number=numbering_service.next_invoice_number(now=now),
        kind=kind, status=SubscriptionInvoice.Status.DRAFT, currency=currency,
        billing_period_start=period_start, billing_period_end=period_end,
        idempotency_key=idempotency_key,
    )
    invoice.save()

    for spec in lines:
        _build_line(invoice, spec).save()
    recompute_totals(invoice)
    invoice.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    record_audit_event(
        store=store, actor=actor, action_code="billing.invoice_created",
        object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
        after={"kind": kind, "grand_total": str(invoice.grand_total), "currency": currency},
    )
    return invoice


@transaction.atomic
def open_invoice(invoice, *, due_at=None, now=None, actor=None):
    """فاکتور را از draft به open می‌برد و صدور را ثبت می‌کند. idempotent؛ روی
    فاکتورِ غیرِ draft خطا نمی‌دهد اگر از قبل open/در ادامه‌ی چرخه باشد."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != SubscriptionInvoice.Status.DRAFT:
        return locked  # از قبل صادر/در چرخه‌ی بعد — idempotent
    now = now or timezone.now()
    locked.status = SubscriptionInvoice.Status.OPEN
    locked.issued_at = now
    locked.due_at = due_at or now
    recompute_totals(locked)
    locked.save(update_fields=[
        "status", "issued_at", "due_at", "subtotal", "discount_total",
        "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.invoice_opened",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        after={"grand_total": str(locked.grand_total), "due_at": str(locked.due_at)},
    )
    return locked


@transaction.atomic
def void_invoice(invoice, *, actor=None, now=None, reason=""):
    """یک فاکتورِ پرداخت‌نشده را باطل می‌کند (ADR-79). فاکتورِ پرداخت‌شده/
    بازپرداخت‌شده باطل نمی‌شود؛ فاکتورِ از قبل باطل idempotent است."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == SubscriptionInvoice.Status.VOID:
        return locked
    if locked.status in (
        SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.REFUNDED,
        SubscriptionInvoice.Status.PARTIALLY_REFUNDED,
    ):
        raise InvoiceError("فاکتورِ پرداخت‌شده را نمی‌توان باطل کرد.")
    now = now or timezone.now()
    locked.status = SubscriptionInvoice.Status.VOID
    locked.voided_at = now
    locked.save(update_fields=["status", "voided_at", "updated_at"])
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.invoice_voided",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        metadata={"reason": reason},
    )
    return locked


@transaction.atomic
def add_line(invoice, spec, *, actor=None):
    """یک ردیف به فاکتورِ *draft* اضافه می‌کند و جمع‌ها را بازمحاسبه می‌کند.
    فاکتورِ غیرِ draft تغییرناپذیرِ مالی است و خطا می‌دهد."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != SubscriptionInvoice.Status.DRAFT:
        raise InvoiceError("فاکتورِ صادرشده تغییرناپذیر است؛ ردیفِ تازه نمی‌پذیرد.")
    _build_line(locked, spec).save()
    recompute_totals(locked)
    locked.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total", "amount_due", "updated_at",
    ])
    return locked
