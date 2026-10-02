"""صفحه‌های مدیریتیِ سامانه‌های کادوپیچی، کمپین/مناسبت و اعلان‌ها.

جدا از ``views.py`` (که بسیار بزرگ است) نگه داشته شده؛ همه‌ی ویوها از همان
دکوراتورهایِ ``staff_required``/``permission_required`` و همان Storeِ
resolve‌شده‌ی ``request.store`` استفاده می‌کنند — هیچ کوئری‌ای بدونِ فیلترِ
Store نیست.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.core.models import ShopSettings
from apps.core.services.audit_service import record_audit_event
from apps.stores.authorization import PRODUCT_EDIT, PRODUCT_VIEW

from .decorators import permission_required, staff_required


@staff_required
@permission_required(PRODUCT_VIEW)
def gift_wrap_products(request):
    """فهرستِ کالاها با کنترلِ کادوپیچیِ هر کالا (فعال/غیرفعال + قیمتِ اختصاصی)."""
    store = request.store
    shop = ShopSettings.load(store=store)
    q = request.GET.get("q", "").strip()
    flt = request.GET.get("filter", "")
    products = Product.objects.filter(store=store, is_draft_placeholder=False).order_by("name")
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if flt == "disabled":
        products = products.filter(gift_wrap_enabled=False)
    elif flt == "custom_price":
        products = products.filter(gift_wrap_price__isnull=False)
    page = Paginator(products, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/gift_wrap_products.html", {
        "page": page, "q": q, "filter": flt, "shop": shop, "active_page": "settings",
        "can_edit": request.store_membership is not None and _can(request, PRODUCT_EDIT),
    })


def _can(request, permission) -> bool:
    from apps.stores.authorization import membership_has_permission

    return membership_has_permission(request.store_membership, permission)


@require_POST
@staff_required
@permission_required(PRODUCT_EDIT)
def gift_wrap_product_update(request, pk):
    product = get_object_or_404(Product, pk=pk, store=request.store)
    enabled = request.POST.get("gift_wrap_enabled") == "on"
    raw_price = request.POST.get("gift_wrap_price", "").strip()
    price = None
    if raw_price:
        try:
            price = Decimal(raw_price)
        except InvalidOperation:
            messages.error(request, "قیمت کادوپیچی نامعتبر است.")
            return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")
        if price < 0 or price != price.to_integral_value():
            messages.error(request, "قیمت کادوپیچی باید عددی صحیح و غیرمنفی باشد.")
            return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")
    before = {"enabled": product.gift_wrap_enabled, "price": str(product.gift_wrap_price)}
    product.gift_wrap_enabled = enabled
    product.gift_wrap_price = price
    product.save(update_fields=["gift_wrap_enabled", "gift_wrap_price", "updated_at"])
    record_audit_event(
        store=request.store, actor=request.user, action_code="product.gift_wrap_updated",
        object_type="Product", object_id=product.pk, object_label=product.name,
        before=before, after={"enabled": enabled, "price": str(price)},
    )
    messages.success(request, f"تنظیمات کادوپیچیِ «{product.name}» ذخیره شد")
    return redirect(request.POST.get("next") or "dashboard:gift-wrap-products")


# ====================================================================== کمپین‌ها و مناسبت‌ها

import json  # noqa: E402

from django.db.models import Count  # noqa: E402
from django.http import Http404  # noqa: E402

from apps.engagement.models import Campaign, CampaignIssuance, CampaignRun  # noqa: E402
from apps.engagement.services import campaign_service, ui_schema  # noqa: E402
from apps.orders.models import CouponRedemption  # noqa: E402
from apps.stores.authorization import COUPON_VIEW, DISCOUNT_MANAGE  # noqa: E402

from .engagement_forms import CampaignForm  # noqa: E402


def _campaign(request, pk) -> Campaign:
    return get_object_or_404(Campaign, pk=pk, store=request.store)


@staff_required
@permission_required(COUPON_VIEW, DISCOUNT_MANAGE)
def campaign_list(request):
    kind = request.GET.get("kind", "")  # occasions | campaigns | ""
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    qs = Campaign.objects.filter(store=request.store).annotate(issued_count=Count("issuances")).order_by("-created_at")
    if kind == "occasions":
        qs = qs.filter(trigger_type=Campaign.Trigger.OCCASION)
    elif kind == "campaigns":
        qs = qs.exclude(trigger_type=Campaign.Trigger.OCCASION)
    if status in Campaign.Status.values:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(name__icontains=q)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "dashboard/campaign_list.html", {
        "page": page, "kind": kind, "status": status, "q": q, "statuses": Campaign.Status.choices,
        "active_page": "occasions" if kind == "occasions" else "campaigns",
        "can_manage": _can(request, DISCOUNT_MANAGE),
    })


def _form_context(request, form, campaign):
    schema = ui_schema.build_schema(request.store)
    return {
        "form": form, "campaign": campaign, "schema_json": schema,
        "active_page": "occasions" if (campaign and campaign.trigger_type == "occasion") or request.GET.get("kind") == "occasions" else "campaigns",
        "errors_text": [],
        "months": [(i, n) for i, n in enumerate(
            ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"], start=1)],
    }


@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_form(request, pk=None):
    campaign = _campaign(request, pk) if pk else None
    editable = campaign is None or campaign.status != Campaign.Status.ACTIVE
    if request.method == "POST":
        if not editable:
            messages.error(request, "کمپینِ فعال قابلِ ویرایش نیست؛ ابتدا آن را متوقف کنید.")
            return redirect("dashboard:campaign-detail", pk=campaign.pk)
        form = CampaignForm(request.POST)
        if form.is_valid():
            target = campaign or Campaign(store=request.store, created_by=request.user)
            form.apply_to(target)
            try:
                campaign_service.save_campaign(target, actor=request.user)
            except campaign_service.CampaignError as exc:
                form.add_error(None, str(exc))
            else:
                problems = campaign_service.validate_campaign(target)
                if problems:
                    messages.warning(request, "ذخیره شد، اما برایِ فعال‌سازی باید این موارد رفع شود: " + "؛ ".join(problems))
                else:
                    messages.success(request, f"کمپین «{target.name}» ذخیره شد")
                return redirect("dashboard:campaign-detail", pk=target.pk)
    else:
        if campaign:
            form = CampaignForm(initial=CampaignForm.initial_from(campaign))
        else:
            kind = request.GET.get("kind")
            form = CampaignForm(initial={
                "trigger_type": "occasion" if kind == "occasions" else "manual", "rule_scope": "aggregate",
                "period_mode": "none", "amount_basis": "net_total", "reward_type": "coupon", "coupon_type": "percent",
                "personalized": True, "channels": ["sms", "email"], "valid_payment_statuses": ["paid"], "per_customer_limit": 1,
                "total_redemption_limit": 1, "occasion_offset_days": 0, "rules_json": "{}",
            })
    context = _form_context(request, form, campaign)
    context["editable"] = editable
    return render(request, "dashboard/campaign_form.html", context)


@staff_required
@permission_required(COUPON_VIEW, DISCOUNT_MANAGE)
def campaign_detail(request, pk):
    campaign = _campaign(request, pk)
    tab = request.GET.get("tab", "overview")
    perf = campaign_service.performance(campaign)
    context = {
        "campaign": campaign, "perf": perf, "tab": tab, "active_page": "campaigns",
        "can_manage": _can(request, DISCOUNT_MANAGE),
        "validation_errors": campaign_service.validate_campaign(campaign) if campaign.status in ("draft", "paused") else [],
        "runs": campaign.runs.exclude(trigger=CampaignRun.Trigger.PREVIEW)[:10],
    }
    if tab == "issued":
        from apps.notifications.models import NotificationOutbox

        qs = campaign.issuances.select_related("customer", "coupon").order_by("-created_at")
        context["page"] = Paginator(qs, 25).get_page(request.GET.get("page"))
        issuance_ids = [i.pk for i in context["page"]]
        notes = {}
        for row in NotificationOutbox.objects.filter(metadata__campaign_id=campaign.pk, metadata__issuance_id__in=issuance_ids):
            notes.setdefault(row.metadata.get("issuance_id"), []).append(row)
        for issuance in context["page"]:
            issuance.notes = notes.get(issuance.pk, [])
    elif tab == "redemptions":
        coupon_ids = campaign.issuances.exclude(coupon__isnull=True).values("coupon_id")
        qs = CouponRedemption.objects.filter(coupon_id__in=coupon_ids).select_related("coupon", "order", "customer").order_by("-created_at")
        context["page"] = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "dashboard/campaign_detail.html", context)


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_activate(request, pk):
    campaign = _campaign(request, pk)
    try:
        campaign_service.activate(campaign, actor=request.user)
        messages.success(request, f"کمپین «{campaign.name}» فعال شد")
    except campaign_service.CampaignError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:campaign-detail", pk=campaign.pk)


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_pause(request, pk):
    campaign = _campaign(request, pk)
    try:
        campaign_service.pause(campaign, actor=request.user)
        messages.info(request, f"کمپین «{campaign.name}» متوقف شد")
    except campaign_service.CampaignError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:campaign-detail", pk=campaign.pk)


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_run(request, pk):
    campaign = _campaign(request, pk)
    if campaign.trigger_type == Campaign.Trigger.OCCASION:
        run = campaign_service.run_occasion_campaign(campaign)
    else:
        run = campaign_service.execute_campaign(campaign, trigger=CampaignRun.Trigger.MANUAL)
    if run.error_text and not run.issued:
        messages.error(request, run.error_text.strip())
    else:
        messages.success(request, f"اجرا انجام شد — مشمول: {run.eligible}، صادرشده: {run.issued}، قبلاً صادرشده: {run.skipped_existing}، خطا: {run.errors}")
    record_audit_event(store=request.store, actor=request.user, action_code="campaign.run_manual", object_type="Campaign",
                       object_id=campaign.pk, object_label=campaign.name, after={"issued": run.issued, "eligible": run.eligible})
    return redirect("dashboard:campaign-detail", pk=campaign.pk)


@require_POST
@staff_required
@permission_required(COUPON_VIEW, DISCOUNT_MANAGE)
def campaign_preview(request, pk):
    campaign = _campaign(request, pk)
    try:
        info = campaign_service.preview(campaign, actor=request.user)
    except Exception as exc:  # noqa: BLE001 — پیکربندیِ ناقص نباید صفحه را بشکند
        return render(request, "dashboard/partials/campaign_preview.html", {"error": f"پیش‌نمایش ممکن نشد: {exc}"})
    return render(request, "dashboard/partials/campaign_preview.html", {"info": info, "campaign": campaign})


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_delete(request, pk):
    campaign = _campaign(request, pk)
    if campaign.status != Campaign.Status.DRAFT or campaign.issuances.exists():
        messages.error(request, "فقط کمپینِ پیش‌نویسِ بدونِ کدِ صادرشده قابلِ حذف است.")
        return redirect("dashboard:campaign-detail", pk=campaign.pk)
    name = campaign.name
    campaign.delete()
    record_audit_event(store=request.store, actor=request.user, action_code="campaign.deleted", object_type="Campaign",
                       object_id=pk, object_label=name)
    messages.info(request, f"کمپین «{name}» حذف شد")
    return redirect("dashboard:campaign-list")


# ====================================================================== اعلان‌ها (قالب‌ها و تاریخچه)

import datetime as _dt  # noqa: E402

from django.core.cache import cache  # noqa: E402
from django.utils import timezone as _tz  # noqa: E402

from apps.notifications import events as notif_events  # noqa: E402
from apps.notifications.models import NotificationOutbox  # noqa: E402
from apps.notifications.services import template_service  # noqa: E402
from apps.notifications.services.dispatcher import dispatch_event  # noqa: E402
from apps.notifications.services.notification_service import RetryNotAllowed, deliver_single, retry_notification  # noqa: E402
from apps.stores.authorization import SETTINGS_MANAGE  # noqa: E402

TEST_SEND_LIMIT_PER_HOUR = 10


@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_templates(request):
    rows = []
    for key, event in notif_events.EVENTS.items():
        sms = template_service.get_template(request.store, key, "sms")
        email = template_service.get_template(request.store, key, "email")
        rows.append({
            "event": event, "category": notif_events.CATEGORY_LABELS[event.category],
            "sms": sms, "email": email, "legacy_sms": bool(event.legacy_sms_event),
        })
    return render(request, "dashboard/notification_templates.html", {"rows": rows, "active_page": "notifications"})


def _event_or_404(key):
    if key not in notif_events.EVENTS:
        raise Http404
    return notif_events.EVENTS[key]


@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_template_edit(request, event_key):
    event = _event_or_404(event_key)
    store = request.store
    errors = {}
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "reset":
            channel = request.POST.get("channel")
            if channel in notif_events.CHANNELS:
                template_service.reset_template(store, event_key, channel)
                messages.info(request, "قالب به حالتِ پیش‌فرض بازگشت")
            return redirect("dashboard:notification-template-edit", event_key=event_key)
        saved = False
        for channel in notif_events.CHANNELS:
            try:
                template_service.save_template(
                    store, event_key, channel, enabled=request.POST.get(f"{channel}_enabled") == "on",
                    subject=request.POST.get("email_subject", "") if channel == "email" else "",
                    body=request.POST.get(f"{channel}_body", ""),
                    extra_recipients=request.POST.get("extra_recipients", "") if channel == "email" or event.audience == "staff" else "",
                )
                saved = True
            except template_service.TemplateError as exc:
                errors[channel] = str(exc)
        if not errors:
            record_audit_event(store=store, actor=request.user, action_code="notification.template_saved",
                               object_type="NotificationTemplate", object_id=0, object_label=event_key)
            messages.success(request, "قالب‌ها ذخیره شد")
            return redirect("dashboard:notification-template-edit", event_key=event_key)
        if saved:
            messages.warning(request, "بخشی از قالب‌ها ذخیره نشد؛ خطاها را بررسی کنید.")
    templates = {ch: template_service.get_template(store, event_key, ch) for ch in notif_events.CHANNELS}
    if request.method == "POST":  # ورودیِ کاربر را در خطا حفظ کن
        for channel in notif_events.CHANNELS:
            templates[channel] = {**templates[channel], "body": request.POST.get(f"{channel}_body", templates[channel]["body"]),
                                  "enabled": request.POST.get(f"{channel}_enabled") == "on"}
        templates["email"]["subject"] = request.POST.get("email_subject", templates["email"]["subject"])
    return render(request, "dashboard/notification_template_form.html", {
        "event": event, "templates": templates, "errors": errors, "active_page": "notifications",
        "variables": sorted(event.variables.items()), "category_label": notif_events.CATEGORY_LABELS[event.category],
        "extra_recipients": templates["email"].get("extra_recipients", "") or templates["sms"].get("extra_recipients", ""),
    })


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_template_preview(request, event_key):
    _event_or_404(event_key)
    channel = request.POST.get("channel", "sms")
    try:
        result = template_service.preview(
            request.store, event_key, channel, body=request.POST.get(f"{channel}_body"),
            subject=request.POST.get("email_subject") if channel == "email" else None,
        )
    except template_service.TemplateError as exc:
        return render(request, "dashboard/partials/notification_preview.html", {"error": str(exc), "channel": channel})
    return render(request, "dashboard/partials/notification_preview.html", {"result": result, "channel": channel})


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_template_test(request, event_key):
    event = _event_or_404(event_key)
    channel = request.POST.get("channel", "sms")
    recipient = request.POST.get("recipient", "").strip()
    if channel not in notif_events.CHANNELS or not recipient:
        messages.error(request, "کانال و گیرنده‌ی آزمایشی را مشخص کنید.")
        return redirect("dashboard:notification-template-edit", event_key=event_key)
    limit_key = f"notif-test:{request.store.pk}"
    count = cache.get(limit_key, 0)
    if count >= TEST_SEND_LIMIT_PER_HOUR:
        messages.error(request, "سقفِ ارسالِ آزمایشی در هر ساعت تکمیل شده است.")
        return redirect("dashboard:notification-template-edit", event_key=event_key)
    cache.set(limit_key, count + 1, 3600)
    rows = dispatch_event(
        event_key, store=request.store, context=dict(event.sample, store_name=request.store.name),
        channels=[channel], is_test=True, test_recipient=recipient,
        overrides={channel: {"body": request.POST.get(f"{channel}_body", ""), "subject": request.POST.get("email_subject", "")}}
        if request.POST.get(f"{channel}_body") else None,
    )
    if not rows:
        messages.error(request, "ارسالِ آزمایشی ساخته نشد.")
    else:
        row = rows[0]
        if row.status == NotificationOutbox.Status.SKIPPED:
            messages.error(request, f"ارسالِ آزمایشی انجام نشد: {row.skip_reason}")
        else:
            row = deliver_single(row)
            if row.status == NotificationOutbox.Status.SENT:
                messages.success(request, "پیامِ آزمایشی ارسال شد.")
            else:
                messages.error(request, f"ارسالِ آزمایشی ناموفق بود: {row.last_error or row.get_status_display()}")
    return redirect("dashboard:notification-template-edit", event_key=event_key)


@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_history(request):
    from .engagement_forms import _jdate

    store = request.store
    qs = NotificationOutbox.objects.filter(store=store).select_related("customer", "order")
    g = request.GET
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(customer__full_name__icontains=q) | Q(customer__phone__icontains=q)
                       | Q(recipient_phone__icontains=q) | Q(recipient_email__icontains=q))
    if g.get("order", "").strip():
        qs = qs.filter(order__code__icontains=g["order"].strip())
    if g.get("event") in notif_events.EVENTS:
        qs = qs.filter(event_key=g["event"])
    if g.get("channel") in notif_events.CHANNELS:
        qs = qs.filter(channel=g["channel"])
    if g.get("status") in NotificationOutbox.Status.values:
        qs = qs.filter(status=g["status"])
    if g.get("provider", "").strip():
        qs = qs.filter(provider__icontains=g["provider"].strip())
    if g.get("error", "").strip():
        qs = qs.filter(Q(last_error__icontains=g["error"].strip()) | Q(skip_reason__icontains=g["error"].strip()))
    tz = _tz.get_current_timezone()
    for key, op, end in (("date_from", "gte", False), ("date_to", "lt", True)):
        try:
            day = _jdate(g.get(key))
        except Exception:  # noqa: BLE001 — تاریخِ نامعتبر فیلتر را نادیده می‌گیرد
            day = None
        if day:
            bound = _dt.datetime.combine(day + _dt.timedelta(days=1 if end else 0), _dt.time.min, tzinfo=tz)
            qs = qs.filter(**{f"created_at__{op}": bound})
    page = Paginator(qs.order_by("-created_at"), 30).get_page(g.get("page"))
    query = g.copy()
    query.pop("page", None)
    return render(request, "dashboard/notification_history.html", {
        "page": page, "events": notif_events.event_choices(), "statuses": NotificationOutbox.Status.choices,
        "filters": g, "query": query.urlencode(), "active_page": "notifications",
    })


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_retry(request, pk):
    notification = get_object_or_404(NotificationOutbox, pk=pk, store=request.store)
    try:
        retry_notification(notification)
    except RetryNotAllowed as exc:
        messages.error(request, str(exc))
    else:
        record_audit_event(store=request.store, actor=request.user, action_code="notification.retry",
                           object_type="NotificationOutbox", object_id=notification.pk, object_label=notification.event_key)
        messages.success(request, "اعلان برایِ تلاشِ دوباره در صف قرار گرفت.")
    return redirect(request.POST.get("next") or "dashboard:notification-history")
