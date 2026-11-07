"""Unified merchant checkout for PLATFORM purchases (RastiSi charging a store): subscription invoice and SMS package.

One page, one state machine, both products. No payment logic lives here — online payments go through
``payment_flow_service`` / ``sms_purchase_payment_service`` (server-generated attempt, server-side amount, authoritative
server-to-server verification, exactly-once fulfilment) and card-to-card through ``manual_card_service`` (claim ⇒ finance
approval ⇒ fulfilment). The merchant never picks a method that is not currently ready, and never reaches a flow that
cannot finish. Store-scoped on every lookup; the Platform Owner Admin shell is NOT used."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.billing.services import platform_checkout_service as pcs
from apps.portal.services import platform_gateway_service as pgs
from apps.sms.models import SmsPackagePurchase
from apps.stores.authorization import BILLING_PAYMENT_MANAGE, SMS_SETTINGS_MANAGE, membership_has_permission

from .decorators import staff_required

SMS_SETTINGS_PATH = "/admin-portal/settings/?section=sms"


def checkout_url(kind: str, pk: int) -> str:
    return reverse("dashboard:platform-checkout", args=[kind, pk])


def resolve_target(request, kind, pk):
    """هدفِ خرید فقط از میانِ رکوردهایِ **همین Store**؛ مجوزِ لازم برایِ هر نوعِ محصول جدا بررسی می‌شود."""
    from apps.billing.models import SubscriptionInvoice

    store = request.store
    if kind == pcs.KIND_SUBSCRIPTION:
        needed = BILLING_PAYMENT_MANAGE
        invoice = get_object_or_404(
            SubscriptionInvoice.objects.select_related("plan_version__plan", "store"), pk=pk, store=store,
        )
        target = pcs.invoice_target(invoice)
    elif kind == pcs.KIND_SMS:
        needed = SMS_SETTINGS_MANAGE
        purchase = get_object_or_404(SmsPackagePurchase.objects.select_related("package", "store"), pk=pk, store=store)
        target = pcs.sms_target(purchase)
    else:
        from django.http import Http404

        raise Http404
    if not membership_has_permission(request.store_membership, needed):
        raise PermissionDenied
    return target


def _method_codes(target):
    return {m["code"]: m for m in pcs.methods(target)}


def _settle_free(request, target, page):
    """مبلغِ صفرِ **سمتِ سرور**: بدونِ درگاه تسویه می‌شود؛ هر مقدارِ ``method``/``amount`` از مرورگر نادیده گرفته می‌شود.
    سخت‌گیریِ نهایی (جمعِ ردیف‌ها، وضعیت، تازگیِ تصمیم) داخلِ سرویس‌هاست — پلنِ پولی هرگز رایگان نمی‌شود."""
    from apps.billing.services import confirmation_service, sms_purchase_payment_service
    from apps.billing.services.payment_flow_service import PaymentFlowError

    from apps.billing.services import platform_coupon_service as coupons

    try:
        if target.kind == pcs.KIND_SUBSCRIPTION and target.obj.coupon_snapshot:
            # تخفیفِ کامل: تسویهی داخلیِ حسابرسیشده (بدونِ درگاه و بدونِ callbackِ جعلی)
            coupons.settle_zero_value_invoice(target.obj, actor=request.user)
        elif target.kind == pcs.KIND_SUBSCRIPTION:
            confirmation_service.settle_zero_due_invoice(target.obj, actor=request.user)
        else:
            sms_purchase_payment_service.settle_free_purchase(target.obj, actor=request.user)
    except (confirmation_service.ConfirmationError, PaymentFlowError, coupons.CouponError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "خرید بدونِ پرداخت تأیید و اعمال شد.")
    return redirect(page)


def start_checkout(request, target, requested: str):
    """شروعِ پرداخت با روشِ انتخابی. ``requested`` باید دقیقاً یکی از روش‌هایِ **آمادهٔ همین خرید** باشد. بازگشتِ
    مقصد همیشه صفحه‌یِ تسویه است (وضعیت از رکوردِ سرور)."""
    from apps.billing.services import payment_flow_service, sms_purchase_payment_service
    from apps.billing.services.payment_flow_service import PaymentFlowError

    page = checkout_url(target.kind, target.pk)
    state = pcs.state(target)
    if not state.can_pay:
        messages.error(request, state.message)
        return redirect(page)
    if state.free:
        return _settle_free(request, target, page)
    if state.needs_ack and request.POST.get("ack") != "1":
        messages.error(request, "پرداختِ قبلی هنوز تأیید نشده است. اگر آن را کامل نکرده‌اید، تأییدِ «پرداختِ قبلی را کامل نکرده‌ام» را بزنید؛ وگرنه «بررسیِ وضعیت» را بزنید.")
        return redirect(page)
    options = _method_codes(target)
    requested = (requested or "").strip()[:40]
    if not requested:
        if len(options) == 1:
            requested = next(iter(options))
        elif not options:
            messages.error(request, "در حال حاضر هیچ روشِ پرداختی برای این خرید فعال نیست.")
            return redirect(page)
        else:
            messages.error(request, "یکی از روش‌هایِ پرداخت را انتخاب کنید.")
            return redirect(page)
    if requested not in options:
        messages.error(request, "روشِ انتخاب‌شده برایِ این خرید در دسترس نیست.")
        return redirect(page)

    if options[requested]["kind"] == "manual":
        name = "dashboard:billing-card-claim" if target.kind == pcs.KIND_SUBSCRIPTION else "dashboard:sms-purchase-card-claim"
        return redirect(name, pk=target.pk)

    try:
        provider = pgs.resolve_checkout_provider(requested, target.purchase_type, store=request.store)
    except pgs.PlatformGatewayError as exc:
        messages.error(request, str(exc))
        return redirect(page)
    return_to = request.build_absolute_uri(page)
    try:
        if target.kind == pcs.KIND_SUBSCRIPTION:
            attempt, session = payment_flow_service.start_payment(
                target.obj, actor=request.user, provider=provider,
                callback_base_url=pgs.callback_base_url(request), return_to=return_to,
            )
            request.session["billing_last_attempt"] = attempt.public_token
        else:
            attempt, session = sms_purchase_payment_service.start_payment(
                target.obj, callback_base_url=pgs.callback_base_url(request), return_to=return_to,
                actor=request.user, provider=provider,
            )
    except PaymentFlowError as exc:
        messages.error(request, str(exc))
        return redirect(page)
    if session is None:                                   # تکرارِ idempotent: جلسه‌یِ قبلی؛ به صفحه برگرد
        return redirect(page)
    return payment_flow_service.gateway_redirect(attempt.provider, session.redirect_url, (session.extra or {}).get("post_fields"))


def _back_to_plans_url(target) -> str:
    """بازگشت به انتخابِ پلن با همان دورهی فاکتور (دورهی مرجعِ سرور، نه ورودیِ کلاینت)."""
    from apps.billing.services import invoice_service
    from apps.dashboard.views import _plans_url

    return _plans_url(invoice_service.invoice_billing_interval(target.obj))


def coupon_context(target, state):
    """نمای تخفیفِ فاکتورِ اشتراک: همه از رکوردِ سرور (اسنپشاتِ فاکتور)؛ مبلغی از مرورگر خوانده نمیشود."""
    if target.kind != pcs.KIND_SUBSCRIPTION:
        return None
    from apps.billing.services import platform_coupon_service as coupons
    from apps.billing.models import SubscriptionInvoice

    invoice = target.obj
    S = SubscriptionInvoice.Status
    snap = invoice.coupon_snapshot or {}
    editable = (
        invoice.status in (S.DRAFT, S.OPEN, S.PAST_DUE) and invoice.amount_paid == 0 and state.can_pay
        and not coupons._has_inflight_payment(invoice) and invoice.lines.count() == 1
    )
    return {
        "applied": bool(snap), "code": snap.get("code") or "", "automatic": bool(snap.get("automatic")),
        "original": invoice.subtotal, "discount": invoice.discount_total, "payable": invoice.amount_due,
        "editable": editable,
        "apply_url": reverse("dashboard:platform-checkout-coupon-apply", args=[target.kind, invoice.pk]),
        "remove_url": reverse("dashboard:platform-checkout-coupon-remove", args=[target.kind, invoice.pk]),
    }


@require_POST
@staff_required
def platform_checkout_coupon_apply(request, kind, pk):
    """اعمال/جایگزینیِ کد. فقط ``coupon_code`` از مرورگر خوانده میشود؛ تخفیف/مبلغ/فروشگاه را سرور میسازد."""
    from django.db import transaction

    from apps.billing.services import platform_coupon_service as coupons

    target = resolve_target(request, kind, pk)
    page = checkout_url(kind, pk)
    if kind != pcs.KIND_SUBSCRIPTION:
        messages.error(request, coupons.MESSAGES["unsupported_invoice"])
        return redirect(page)
    code = coupons.normalize_code(request.POST.get("coupon_code"))
    if not code:
        messages.error(request, "کد تخفیف را وارد کنید.")
        return redirect(page)
    invoice = target.obj
    try:
        coupons.check_attempt_rate(request.user, invoice.store)
        with transaction.atomic():
            existing = getattr(invoice, "coupon_redemption", None) if invoice.coupon_snapshot else None
            if existing is not None and existing.code_snapshot != code and not existing.coupon.is_automatic:
                coupons.remove_coupon_from_invoice(invoice, actor=request.user)     # جایگزینی؛ در صورتِ خطا همه برمیگردد
            coupons.apply_coupon_to_invoice(invoice, code=code, actor=request.user)
    except coupons.CouponError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, "کد تخفیف اعمال شد؛ مبلغِ نهایی بهروز شد. این تخفیف فقط برایِ همین فاکتور است.")
    return redirect(page)


@require_POST
@staff_required
def platform_checkout_coupon_remove(request, kind, pk):
    from apps.billing.services import platform_coupon_service as coupons

    target = resolve_target(request, kind, pk)
    page = checkout_url(kind, pk)
    if kind != pcs.KIND_SUBSCRIPTION:
        return redirect(page)
    try:
        coupons.remove_coupon_from_invoice(target.obj, actor=request.user)
    except coupons.CouponError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, "کد تخفیف برداشته شد.")
    return redirect(page)


@staff_required
def platform_checkout(request, kind, pk):
    target = resolve_target(request, kind, pk)
    state = pcs.state(target)
    options = pcs.methods(target) if state.can_pay and not state.free else []
    default = next((m["code"] for m in options if m.get("is_default")), options[0]["code"] if options else "")
    return render(request, "dashboard/platform_checkout.html", {
        "target": target, "state": state, "methods": options, "coupon": coupon_context(target, state), "default_method": default,
        "post_url": reverse("dashboard:platform-checkout-pay", args=[kind, pk]),
        "status_url": reverse("dashboard:platform-checkout-status", args=[kind, pk]),
        "back_url": _back_to_plans_url(target) if kind == pcs.KIND_SUBSCRIPTION else SMS_SETTINGS_PATH,
        "back_label": "بازگشت به پلن‌ها" if kind == pcs.KIND_SUBSCRIPTION else "بازگشت به تنظیماتِ پیامک",
        "invoice_url": reverse("dashboard:billing-invoice-detail", args=[pk]) if kind == pcs.KIND_SUBSCRIPTION else "",
        "no_method": state.can_pay and not options and not state.free,
        "hide_section_nav": True,
        "active_page": "billing" if kind == pcs.KIND_SUBSCRIPTION else "settings",
    })


@require_POST
@staff_required
def platform_checkout_pay(request, kind, pk):
    target = resolve_target(request, kind, pk)
    return start_checkout(request, target, request.POST.get("method") or request.POST.get("gateway") or "")


@require_POST
@staff_required
def platform_checkout_status(request, kind, pk):
    """«بررسیِ وضعیت»: همان verify سرور-به-سرورِ بازگشتِ درگاه (idempotent، محدودِ نرخ) — هرگز اعتماد به مرورگر."""
    from django.core.cache import cache

    from apps.billing.providers.base import BillingProviderError
    from apps.billing.services import payment_flow_service, sms_purchase_payment_service
    from apps.billing.services.confirmation_service import ConfirmationError

    target = resolve_target(request, kind, pk)
    state = pcs.state(target)
    attempt = state.attempt
    if attempt is not None and not attempt.is_final:
        if cache.add(f"billing:verify:{attempt.public_token}", 1, 8):
            try:
                if target.kind == pcs.KIND_SMS:
                    sms_purchase_payment_service.verify_and_fulfill(attempt, actor=request.user)
                else:
                    payment_flow_service.confirm_from_provider_verification(attempt, actor=request.user)
            except (BillingProviderError, ConfirmationError, sms_purchase_payment_service.SmsPaymentConfirmationError):
                pass
        else:
            messages.info(request, "چند لحظه بعد دوباره بررسی کنید.")
    return redirect(checkout_url(kind, pk))
