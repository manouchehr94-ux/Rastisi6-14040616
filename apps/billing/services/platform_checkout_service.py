"""Merchant-side checkout for PLATFORM purchases (subscription invoice or SMS package) — read-only composition.

This module owns NO payment logic: it only (1) describes what is being bought from the server-side record, (2) lists the
methods that are *really* usable right now (``platform_gateway_service.checkout_options`` — enabled + credentials complete
+ contractual gates open + allowed for this purchase type), and (3) derives the checkout state from server records
(invoice/purchase status, payment attempts, manual claims). Money movement stays in ``payment_flow_service`` /
``sms_purchase_payment_service`` / ``manual_card_service``; amounts never come from the browser."""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.billing.models import PlatformManualPaymentClaim as Claim, SubscriptionInvoice
from apps.core.utils import format_toman
from apps.portal.services import platform_gateway_service as pgs

KIND_SUBSCRIPTION = "subscription"
KIND_SMS = "sms"
KINDS = (KIND_SUBSCRIPTION, KIND_SMS)

#: یک تلاشِ آنلاینِ pending که بیش از این قدیمی است «منقضی» حساب می‌شود تا مرچنت برای همیشه قفل نماند (verify همچنان ممکن است).
ATTEMPT_PENDING_WINDOW = timedelta(minutes=45)

def checkout_path(kind: str, pk: int) -> str:
    """مسیرِ صفحه‌ی تسویه در پنلِ مدیریتِ فروشگاه. ثابت (بدونِ reverse) تا پرتال — که urlconfِ داشبورد را ندارد — هم بتواند آن را
    برایِ handoff بسازد؛ برابریِ آن با ``reverse("dashboard:platform-checkout")`` در تست قفل شده است."""
    return f"/admin-portal/billing/checkout/{kind}/{int(pk)}/"


PAYABLE, VERIFYING, PENDING_REVIEW, NEEDS_ACTION = "payable", "verifying", "pending_review", "needs_action"
PAID, FAILED, CLOSED, REFUNDED = "paid", "failed", "closed", "refunded"


@dataclass(frozen=True)
class Target:
    kind: str
    obj: object
    store: object
    purchase_type: str
    title: str
    subtitle: str
    amount: Decimal
    currency: str
    lines: tuple = field(default_factory=tuple)         # ((label, amount), ...)

    @property
    def pk(self):
        return self.obj.pk


@dataclass(frozen=True)
class CheckoutState:
    code: str
    tone: str            # ok | warn | bad | info
    title: str
    message: str
    can_pay: bool
    attempt: object = None
    claim: object = None
    needs_ack: bool = False        # یک تلاشِ آنلاینِ نامعلوم هست: پرداختِ دوباره فقط با تأییدِ صریحِ مرچنت (جلوگیری از پرداختِ دوباره)


def invoice_target(invoice) -> Target:
    lines = tuple((line.description, line.total) for line in invoice.lines.all())
    plan_version = getattr(invoice, "plan_version", None)
    interval = ""
    if plan_version is not None:
        interval = plan_version.get_billing_interval_display() if hasattr(plan_version, "get_billing_interval_display") else ""
    return Target(
        kind=KIND_SUBSCRIPTION, obj=invoice, store=invoice.store, purchase_type=pgs.PURCHASE_SUBSCRIPTION,
        title=f"اشتراک — {plan_version.plan.public_title or plan_version.plan.name}" if plan_version is not None else f"فاکتور {invoice.number}",
        subtitle=" · ".join(x for x in (f"فاکتور {invoice.number}", invoice.get_kind_display(), interval) if x),
        # قابلِ پرداخت = باقی‌مانده؛ پس از پرداخت/بازپرداخت باقی‌مانده صفر است و جمعِ فاکتور نمایش داده می‌شود (نه «۰ تومان»)
        amount=Decimal(invoice.amount_due if invoice.is_payable else invoice.grand_total), currency=invoice.currency, lines=lines,
    )


def sms_target(purchase) -> Target:
    return Target(
        kind=KIND_SMS, obj=purchase, store=purchase.store, purchase_type=pgs.PURCHASE_SMS,
        title=f"بسته‌ی پیامک «{purchase.package.name}»",
        subtitle=f"{format_toman(purchase.credit_amount, with_unit=False)} اعتبار پیامک",
        amount=Decimal(purchase.price), currency="IRT",
        lines=((f"بسته‌ی «{purchase.package.name}» — {format_toman(purchase.credit_amount, with_unit=False)} اعتبار", Decimal(purchase.price)),),
    )


def methods(target: Target) -> list[dict]:
    """روش‌هایِ واقعاً قابلِ‌استفاده برای این خرید و این فروشگاه. هرگز اعتبارنامه برنمی‌گرداند."""
    out = []
    for option in pgs.checkout_options(target.purchase_type, store=target.store):
        if option.get("manual"):
            out.append({**option, "kind": "manual", "description": "واریز به حسابِ راستیسی و ثبتِ رسید؛ پس از تأییدِ مالی فعال می‌شود."})
        else:
            out.append({**option, "kind": "online", "description": "پرداختِ امن از درگاهِ بانکی؛ پس از تأییدِ سرور فعال می‌شود."})
    return out


def _attempts(target):
    return list(target.obj.payment_attempts.order_by("-created_at")[:5])


def _claims(target):
    return list(target.obj.manual_claims.order_by("-created_at")[:5])


def _terminal(target):
    obj = target.obj
    if target.kind == KIND_SUBSCRIPTION:
        S = SubscriptionInvoice.Status
        if obj.status == S.PAID:
            return PAID
        if obj.status == S.REFUNDED:
            return REFUNDED
        if obj.status in (S.VOID, S.UNCOLLECTIBLE, S.DRAFT):
            return CLOSED
        return None
    from apps.sms.models import SmsPackagePurchase as P

    return {P.Status.COMPLETED: PAID, P.Status.REFUNDED: REFUNDED, P.Status.CANCELED: CLOSED}.get(obj.status)


def state(target: Target, *, now=None) -> CheckoutState:
    """وضعیتِ تسویه فقط از رکوردهایِ سمتِ سرور؛ بازگشتِ مرورگر/پارامترِ query هرگز اثری ندارد."""
    now = now or timezone.now()
    terminal = _terminal(target)
    if terminal == PAID:
        return CheckoutState(PAID, "ok", "پرداخت تأیید شد", "پرداخت شما از سمتِ سرور تأیید و خرید اعمال شد.", False)
    if terminal == REFUNDED:
        return CheckoutState(REFUNDED, "info", "بازپرداخت شد", "مبلغِ این خرید بازپرداخت شده است.", False)
    if terminal == CLOSED:
        return CheckoutState(CLOSED, "bad", "این خرید بسته شده است", "امکانِ پرداخت برای این مورد وجود ندارد؛ از ابتدا خرید کنید.", False)

    attempts, claims = _attempts(target), _claims(target)
    latest_attempt = attempts[0] if attempts else None
    latest_claim = claims[0] if claims else None
    use_claim = latest_claim is not None and (latest_attempt is None or latest_claim.created_at >= latest_attempt.created_at)

    if use_claim:
        C = Claim.Status
        if latest_claim.status == C.PENDING_REVIEW:
            return CheckoutState(
                PENDING_REVIEW, "warn", "در انتظارِ بررسیِ مالی",
                "ادعای پرداختِ شما ثبت شد. تا تأییدِ مدیرِ مالیِ راستیسی هیچ سرویسی فعال نمی‌شود و اعتباری اضافه نمی‌شود؛ دوباره واریز نکنید.",
                False, claim=latest_claim,
            )
        if latest_claim.status in (C.NEEDS_ACTION, C.APPROVED):
            return CheckoutState(
                NEEDS_ACTION, "bad", "نیازمندِ بررسیِ پشتیبانی",
                "واریزِ شما تأیید شد امّا اعمالِ نهایی کامل نشد؛ پشتیبانی پیگیری می‌کند. دوباره پرداخت نکنید.", False, claim=latest_claim,
            )
        reason = f" دلیل: {latest_claim.review_note}" if latest_claim.status == C.REJECTED and latest_claim.review_note else ""
        label = {C.REJECTED: "ردشد", C.CANCELLED: "لغو شد", C.EXPIRED: "منقضی شد"}.get(latest_claim.status, "پایان یافت")
        return CheckoutState(
            FAILED, "bad", "ادعای قبلی " + label, f"ادعای کارت‌به‌کارتِ قبلی شما {label}.{reason} می‌توانید دوباره تلاش کنید.", True, claim=latest_claim,
        )

    if latest_attempt is not None:
        A = type(latest_attempt).Status
        if latest_attempt.status in (A.CREATED, A.PENDING):
            if now - latest_attempt.created_at <= ATTEMPT_PENDING_WINDOW:
                return CheckoutState(
                    VERIFYING, "warn", "در انتظارِ تأییدِ درگاه",
                    "پرداختِ شما هنوز از سمتِ سرور تأیید نشده است. اگر پرداخت کرده‌اید «بررسیِ وضعیت» را بزنید و دوباره پرداخت نکنید.",
                    True, attempt=latest_attempt, needs_ack=True,
                )
            return CheckoutState(FAILED, "bad", "مهلتِ پرداخت تمام شد", "تلاشِ قبلی کامل نشد. اگر مبلغی کسر شده، ابتدا «بررسیِ وضعیت» را بزنید؛ وگرنه دوباره تلاش کنید.", True, attempt=latest_attempt)
        if latest_attempt.status == A.REQUIRES_ACTION or latest_attempt.status == A.SUCCEEDED:
            return CheckoutState(
                NEEDS_ACTION, "bad", "نیازمندِ بررسیِ پشتیبانی",
                "پرداخت شما نیازمندِ بررسیِ پشتیبانی است؛ دوباره پرداخت نکنید.", False, attempt=latest_attempt,
            )
        label = {A.FAILED: "ناموفق بود", A.CANCELLED: "لغو شد", A.EXPIRED: "منقضی شد"}.get(latest_attempt.status, "ناموفق بود")
        return CheckoutState(FAILED, "bad", "پرداخت انجام نشد", f"تلاشِ قبلیِ پرداخت {label}. هیچ مبلغی از شما تأیید نشده؛ می‌توانید دوباره تلاش کنید.", True, attempt=latest_attempt)

    return CheckoutState(PAYABLE, "info", "آماده‌ی پرداخت", "روشِ پرداخت را انتخاب کنید.", True)
