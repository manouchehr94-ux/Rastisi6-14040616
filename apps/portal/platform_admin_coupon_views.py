"""Platform Admin: platform (SaaS) coupons and campaigns.

Owner-only (same ``_is_platform_staff`` gate as every other platform admin page); every write is POST + CSRF and goes
through ``platform_coupon_service`` (validation, audit trail). Dates are entered with the shared Persian date picker,
which submits a local ISO value; it is converted to a timezone-aware instant on the server (never trusts the client zone).
Stacking is not supported by the engine, so combinability is shown as a fixed fact, not an option."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.billing.models import PlatformCoupon, PlatformCouponAuditEvent, PlatformCouponRedemption
from apps.billing.platform_coupon_models import STACKING_ALLOWED, _interval_choices
from apps.billing.services import platform_coupon_service as svc
from apps.stores.models import Store
from apps.subscriptions.models import Plan

from .platform_admin_views import _is_platform_staff

LOGIN = "portal_platform_admin:login"
LIST = "portal_platform_admin:coupons"
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،,", "01234567890123456789" + "   ")

STATE_LABELS = {
    "active": ("فعال", "pa-ok"), "inactive": ("غیرفعال", "pa-off"), "scheduled": ("زمان‌بندی‌شده", "pa-info"),
    "expired": ("منقضی", "pa-warn"), "exhausted": ("تمام‌شده", "pa-warn"),
}
AUDIT_LABELS = {
    "created": "ایجاد", "updated": "ویرایش", "enabled": "فعال‌سازی", "disabled": "غیرفعال‌سازی", "archived": "بایگانی",
    "duplicated": "کپی از کوپن دیگر", "reserved": "رزرو برای فاکتور", "redeemed": "مصرف", "released": "آزادسازی رزرو",
    "reversed": "برگشت مصرف", "zero_value_settled": "تسویه فاکتور صفر",
}


def _owner(view):
    return user_passes_test(_is_platform_staff, login_url=LOGIN)(view)


def _num(raw):
    return (raw or "").translate(DIGITS).replace(" ", "").strip()


def _int_or_none(raw, label, errors, *, minimum=1):
    value = _num(raw)
    if not value:
        return None
    if not value.isdigit() or int(value) < minimum:
        errors.append(f"{label} باید یک عدد صحیح و حداقل {minimum} باشد.")
        return None
    return int(value)


def _money_or_none(raw, label, errors):
    value = _num(raw)
    if not value:
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        errors.append(f"{label} معتبر نیست.")
        return None
    if amount < 0 or amount != amount.to_integral_value():
        errors.append(f"{label} باید یک مبلغ صحیح و نامنفی (تومان) باشد.")
        return None
    return amount


def _datetime_or_none(raw, label, errors):
    """مقدارِ محلیِ ISO که انتخابگرِ تاریخِ شمسی میفرستد → لحظهی aware در منطقهی زمانیِ پروژه (Asia/Tehran)."""
    value = _num_dt(raw)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    errors.append(f"{label} معتبر نیست.")
    return None


def _num_dt(raw):
    return (raw or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()


def _form_value(coupon):
    """مقدارهای اولیهی فرم از یک کوپن (یا پیشفرضِ کوپنِ تازه)."""
    if coupon is None:
        return {"kind": "percent", "allow_initial": True, "intervals": [], "plan_ids": [], "store_slugs": ""}
    return {
        "name": coupon.name, "description": coupon.description, "code": coupon.code or "", "is_automatic": coupon.is_automatic,
        "kind": coupon.kind, "percent": coupon.percent, "fixed_amount": coupon.fixed_amount, "max_discount_amount": coupon.max_discount_amount,
        "min_amount": coupon.min_amount, "starts_at": _local_input(coupon.starts_at), "ends_at": _local_input(coupon.ends_at),
        "max_redemptions": coupon.max_redemptions, "max_per_store": coupon.max_per_store, "allow_initial": coupon.allow_initial,
        "allow_renewal": coupon.allow_renewal, "allow_plan_change": coupon.allow_plan_change,
        "first_purchase_only": coupon.first_purchase_only, "intervals": list(coupon.intervals or []),
        "plan_ids": list(coupon.plans.values_list("pk", flat=True)),
        "store_slugs": "\n".join(coupon.stores.values_list("slug", flat=True)),
    }


def _local_input(value):
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M") if value else ""


def _parse_post(post):
    """(fields, plans, stores, errors) از ورودیِ POST. فقط فیلدهایِ تعریفِ کوپن؛ هرگز مبلغی از فاکتور."""
    errors = []
    kind = post.get("kind")
    if kind not in PlatformCoupon.Kind.values:
        errors.append("نوعِ تخفیف نامعتبر است.")
        kind = PlatformCoupon.Kind.PERCENT
    valid_intervals = {value for value, _ in _interval_choices()}
    intervals = [i for i in post.getlist("intervals") if i in valid_intervals]
    is_automatic = post.get("is_automatic") == "on"
    code = (post.get("code") or "").strip()
    fields = {
        "name": (post.get("name") or "").strip(), "description": (post.get("description") or "").strip(),
        "code": code or None, "is_automatic": is_automatic, "kind": kind,
        "percent": None, "fixed_amount": None,
        "max_discount_amount": _money_or_none(post.get("max_discount_amount"), "سقفِ تخفیف", errors),
        "min_amount": _money_or_none(post.get("min_amount"), "حداقلِ مبلغ", errors),
        "intervals": intervals,
        "starts_at": _datetime_or_none(post.get("starts_at"), "تاریخِ شروع", errors),
        "ends_at": _datetime_or_none(post.get("ends_at"), "تاریخِ پایان", errors),
        "max_redemptions": _int_or_none(post.get("max_redemptions"), "سقفِ کلِ استفاده", errors),
        "max_per_store": _int_or_none(post.get("max_per_store"), "سقفِ استفاده برایِ هر فروشگاه", errors),
        "allow_initial": post.get("allow_initial") == "on", "allow_renewal": post.get("allow_renewal") == "on",
        "allow_plan_change": post.get("allow_plan_change") == "on", "first_purchase_only": post.get("first_purchase_only") == "on",
    }
    if kind == PlatformCoupon.Kind.PERCENT:
        fields["percent"] = _int_or_none(post.get("percent"), "درصد", errors)
    else:
        fields["fixed_amount"] = _money_or_none(post.get("fixed_amount"), "مبلغِ ثابت", errors)
    if not fields["name"]:
        errors.append("نامِ داخلی الزامی است.")
    if not (fields["allow_initial"] or fields["allow_renewal"] or fields["allow_plan_change"]):
        errors.append("حداقل یک نوعِ خرید (اولیه، تمدید یا تغییرِ پلن) باید مجاز باشد.")
    plan_ids = [int(v) for v in post.getlist("plans") if v.isdigit()]
    plans = list(Plan.objects.filter(pk__in=plan_ids))
    slugs = [s.strip() for s in (post.get("store_slugs") or "").replace(",", "\n").splitlines() if s.strip()]
    stores = list(Store.objects.filter(slug__in=slugs))
    missing = sorted(set(slugs) - {s.slug for s in stores})
    if missing:
        errors.append("فروشگاهی با این شناسه(slug) یافت نشد: " + "، ".join(missing[:5]))
    return fields, plans, stores, errors


def _validation_messages(exc):
    if hasattr(exc, "message_dict"):
        return [m for msgs in exc.message_dict.values() for m in msgs]
    return list(exc.messages)


def _stats(coupon, now=None):
    now = now or timezone.now()
    S = PlatformCouponRedemption.Status
    qs = coupon.redemptions.all()
    redeemed = qs.filter(status=S.REDEEMED)
    counted = coupon.counted_redemptions(now=now)
    agg = redeemed.aggregate(discount=Sum("discount_amount"), revenue=Sum("final_amount"), original=Sum("original_amount"))
    remaining = None if coupon.max_redemptions is None else max(coupon.max_redemptions - counted, 0)
    return {
        "redeemed": redeemed.count(),
        "reserved": qs.filter(status=S.RESERVED, expires_at__gt=now).count(),
        "counted": counted, "remaining": remaining,
        "affected_invoices": qs.filter(status__in=(S.RESERVED, S.REDEEMED)).count(),
        "total_discount": agg["discount"] or 0, "revenue": agg["revenue"] or 0, "original": agg["original"] or 0,
        "reversed": qs.filter(status=S.REVERSED).count(),
    }


# ------------------------------------------------------------------------------------------------ list

@_owner
def coupons(request):
    query = (request.GET.get("q") or "").strip()
    state_filter = request.GET.get("state") or ""
    qs = PlatformCoupon.objects.annotate(
        redeemed_count=Count("redemptions", filter=Q(redemptions__status=PlatformCouponRedemption.Status.REDEEMED)),
    ).order_by("-created_at", "-id")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query.upper()))
    if state_filter == "archived":
        qs = qs.filter(status=PlatformCoupon.Status.ARCHIVED)
    elif state_filter != "all":
        qs = qs.exclude(status=PlatformCoupon.Status.ARCHIVED)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    now = timezone.now()
    rows = []
    for coupon in page:
        state = coupon.derived_state(now=now)
        if coupon.status == PlatformCoupon.Status.ARCHIVED:
            label, css = "بایگانی‌شده", "pa-off"
        else:
            label, css = STATE_LABELS[state]
        rows.append({"coupon": coupon, "state": state, "state_label": label, "state_class": css,
                     "counted": coupon.counted_redemptions(now=now)})
    return render(request, "portal/platform_admin/coupons.html", {
        "rows": rows, "page": page, "query": query, "state_filter": state_filter, "active_nav": "coupons",
    })


# ------------------------------------------------------------------------------------------------ create / edit

@_owner
def coupon_form(request, coupon_id=None):
    coupon = get_object_or_404(PlatformCoupon, pk=coupon_id) if coupon_id else None
    if coupon is not None and coupon.status == PlatformCoupon.Status.ARCHIVED:
        messages.error(request, "کوپنِ بایگانی‌شده قابلِ ویرایش نیست؛ ابتدا آن را بازگردانی کنید.")
        return redirect("portal_platform_admin:coupon-detail", coupon.pk)
    value = _form_value(coupon)
    if request.method == "POST":
        fields, plans, stores, errors = _parse_post(request.POST)
        value = {**{k: v for k, v in fields.items() if k not in ("starts_at", "ends_at")},
                 "starts_at": _num_dt(request.POST.get("starts_at")), "ends_at": _num_dt(request.POST.get("ends_at")),
                 "plan_ids": [p.pk for p in plans], "store_slugs": request.POST.get("store_slugs", ""),
                 "code": (request.POST.get("code") or "").strip()}
        if not errors:
            try:
                if coupon is None:
                    saved = svc.create_coupon(actor=request.user, plans=plans, stores=stores, **fields)
                else:
                    saved = svc.update_coupon(coupon, actor=request.user, plans=plans, stores=stores, **fields)
            except svc.CouponError as exc:
                errors.append(exc.message)
            except ValidationError as exc:
                errors.extend(_validation_messages(exc))
            else:
                messages.success(request, f"کوپنِ «{saved.name}» ذخیره شد.")
                return redirect("portal_platform_admin:coupon-detail", saved.pk)
        for error in errors:
            messages.error(request, error)
    return render(request, "portal/platform_admin/coupon_form.html", {
        "coupon": coupon, "v": value, "plans": Plan.objects.order_by("display_order", "name"),
        "interval_choices": _interval_choices(), "stacking_allowed": STACKING_ALLOWED, "active_nav": "coupons",
    })


# ------------------------------------------------------------------------------------------------ detail / stats / history

@_owner
def coupon_detail(request, coupon_id):
    coupon = get_object_or_404(PlatformCoupon, pk=coupon_id)
    now = timezone.now()
    state = coupon.derived_state(now=now)
    label, css = ("بایگانی‌شده", "pa-off") if coupon.status == PlatformCoupon.Status.ARCHIVED else STATE_LABELS[state]
    redemptions = list(svc.redemptions_for(coupon)[:50])
    events = [{"event": e, "label": AUDIT_LABELS.get(e.action, e.action)}
              for e in coupon.audit_events.select_related("actor", "store", "invoice").order_by("-created_at", "-id")[:100]]
    return render(request, "portal/platform_admin/coupon_detail.html", {
        "coupon": coupon, "state_label": label, "state_class": css, "stats": _stats(coupon, now),
        "redemptions": redemptions, "events": events, "plans": coupon.plans.all(), "stores": coupon.stores.all(),
        "interval_labels": [dict(_interval_choices()).get(i, i) for i in (coupon.intervals or [])],
        "stacking_allowed": STACKING_ALLOWED, "active_nav": "coupons",
    })


# ------------------------------------------------------------------------------------------------ writes (POST only)

@require_POST
@_owner
def coupon_status(request, coupon_id, action):
    coupon = get_object_or_404(PlatformCoupon, pk=coupon_id)
    target = {"enable": PlatformCoupon.Status.ACTIVE, "disable": PlatformCoupon.Status.DISABLED,
              "archive": PlatformCoupon.Status.ARCHIVED}.get(action)
    if target is None:
        messages.error(request, "عملیاتِ نامعتبر.")
        return redirect("portal_platform_admin:coupon-detail", coupon.pk)
    try:
        svc.set_coupon_status(coupon, target, actor=request.user)
    except svc.CouponError as exc:
        messages.error(request, exc.message)
    else:
        done = {"enable": "فعال شد", "disable": "غیرفعال شد", "archive": "بایگانی شد؛ سابقهٔ مصرف و فاکتورها حفظ می‌شود"}[action]
        messages.success(request, f"کوپنِ «{coupon.name}» {done}.")
    return redirect("portal_platform_admin:coupon-detail", coupon.pk)


@require_POST
@_owner
def coupon_duplicate(request, coupon_id):
    """کپیِ پیکربندی به صورتِ یک کوپنِ **غیرفعال** (کدِ کپی یکتا میشود؛ ابتدا بازبینی کنید و سپس فعال کنید)."""
    source = get_object_or_404(PlatformCoupon, pk=coupon_id)
    code = None
    if source.code:
        base = f"{source.code}-COPY"[:40]
        code, n = base, 1
        while PlatformCoupon.objects.filter(code=code).exists():
            n += 1
            code = f"{base[:36]}-{n}"
    fields = {name: getattr(source, name) for name in svc.EDITABLE_FIELDS if name not in ("code", "name")}
    fields["intervals"] = list(source.intervals or [])
    try:
        copy = svc.create_coupon(
            actor=request.user, code=code, name=f"{source.name} (کپی)"[:120],
            plans=list(source.plans.all()), stores=list(source.stores.all()), **fields,
        )
        svc.set_coupon_status(copy, PlatformCoupon.Status.DISABLED, actor=request.user)
        svc._coupon_event(copy, "duplicated", actor=request.user, detail={"source_id": source.pk})
    except (svc.CouponError, ValidationError) as exc:
        messages.error(request, getattr(exc, "message", None) or "; ".join(_validation_messages(exc)))
        return redirect("portal_platform_admin:coupon-detail", source.pk)
    messages.success(request, "کپی ساخته شد و غیرفعال است؛ آن را بازبینی و سپس فعال کنید.")
    return redirect("portal_platform_admin:coupon-edit", copy.pk)
