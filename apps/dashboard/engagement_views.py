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
from django.urls import reverse
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
from django.http import Http404, JsonResponse  # noqa: E402

from apps.engagement.models import Campaign, CampaignIssuance, CampaignRun  # noqa: E402
from apps.engagement.services import campaign_service, simple_setup, ui_schema  # noqa: E402
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


MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
VALIDITY_DAYS = (3, 7, 14, 30, 90)


def _wizard_sources(store, schema=None) -> dict:
    """گزینه‌هایِ «مخاطبِ خاص» — فقط از دادهٔ همین فروشگاه."""
    from apps.customers.models import Address, Customer
    from apps.engagement.services import rule_data

    schema = schema or ui_schema.build_schema(store)
    ids = rule_data.store_customer_ids(store)
    # همان منبعی که قاعده‌ی «شهرِ مشتری» ارزیابی می‌کند: آدرسِ پیش‌فرض، و در نبودِ آن شهرِ پروفایل
    cities = sorted(
        {c.strip() for c in Customer.objects.filter(pk__in=ids).exclude(city="").values_list("city", flat=True).distinct()[:500]}
        | {c.strip() for c in Address.objects.filter(customer_id__in=ids).exclude(city="").values_list("city", flat=True).distinct()[:500]}
    )
    sources = schema["sources"]
    return {
        "city": [[c, c] for c in cities],
        "category": sources["categories"], "tag": sources["tags"], "segment": sources["segments"],
    }


def _form_context(request, form, campaign):
    schema = ui_schema.build_schema(request.store)
    trigger = form["trigger_type"].value() or ("occasion" if request.GET.get("kind") == "occasions" else "manual")
    is_occasion = trigger == "occasion"
    days = {str(d) for d in VALIDITY_DAYS}
    current_days = str(form["code_valid_days"].value() or "")
    shop_sms_enabled = _sms_globally_enabled(request.store)
    sources = _wizard_sources(request.store, schema)
    try:
        offset_value = int(form["occasion_offset_days"].value() or 0)
    except (TypeError, ValueError):
        offset_value = 0
    custom_offset = offset_value if offset_value not in (0, -3, 1) else None
    return {
        "form": form, "campaign": campaign, "schema_json": schema,
        "active_page": "occasions" if is_occasion else "campaigns",
        "is_occasion": is_occasion, "errors_text": [],
        "months": list(enumerate(MONTHS, start=1)),
        "validity_days": [(d, f"{d} روز") for d in VALIDITY_DAYS] + ([(int(current_days), f"{current_days} روز (مقدار قبلی)")] if current_days and current_days not in days else []),
        "extra_groups": [
            (kind, label, sources[kind]) for kind, label in (
                ("city", "شهرها"), ("category", "دسته‌ها"), ("tag", "برچسب‌ها"), ("segment", "گروه‌هایِ مشتری"),
            )
        ],
        "selected_extra": {str(v) for v in (form["audience_extra_values"].value() or [])},
        "custom_offset": custom_offset, "custom_offset_abs": abs(custom_offset) if custom_offset is not None else None,
        "wizard_config": {
            "mode": "occasion" if is_occasion else "campaign", "previewUrl": reverse("dashboard:campaign-sms-preview"),
            "smsSettingsUrl": "/admin-portal/settings/?section=sms", "shopSmsEnabled": shop_sms_enabled,
        },
        "shop_sms_enabled": shop_sms_enabled,
        "audience_is_custom": (form["audience_kind"].value() == "custom"),
        "has_fixed_expiry": bool(form["code_expires_at"].value()),
    }


def _form_initial_for_new(kind):
    occasion = kind == "occasions"
    return {
        "trigger_type": "occasion" if occasion else "manual", "rule_scope": "aggregate",
        "period_mode": "none", "amount_basis": "net_total", "reward_type": "coupon", "coupon_type": "percent",
        "coupon_value": 15, "code_valid_days": 7, "personalized": True, "channels": [], "channels_explicit": True,
        "valid_payment_statuses": ["paid"], "per_customer_limit": 1, "occasion_offset_days": 0,
        "occasion_kind": "birthday" if occasion else "", "rules_json": "{}", "audience_kind": "all",
        "audience_extra_kind": "", "occ_days": 90, "occ_n": 3, "occ_amount": 5000000, "occ_month": 1, "occ_day": 1,
        "name": "هدیه تولد مشتریان" if occasion else "",
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
            try:
                form.apply_to(target)
                campaign_service.save_campaign(target, actor=request.user)
            except (simple_setup.AudienceError, campaign_service.CampaignError) as exc:
                form.add_error(None, str(exc))
            else:
                problems = campaign_service.validate_campaign(target)
                if problems:
                    messages.warning(request, "پیش‌نویس ذخیره شد، اما برایِ فعال‌سازی باید این موارد رفع شود: " + "؛ ".join(problems))
                else:
                    messages.success(request, f"«{target.name}» به‌صورتِ پیش‌نویس ذخیره شد؛ پس از بررسی آن را فعال کنید")
                return redirect("dashboard:campaign-detail", pk=target.pk)
    else:
        if campaign:
            form = CampaignForm(initial=CampaignForm.initial_from(campaign))
        else:
            form = CampaignForm(initial=_form_initial_for_new(request.GET.get("kind")))
    context = _form_context(request, form, campaign)
    context["editable"] = editable
    return render(request, "dashboard/campaign_form.html", context)


def _lenient(form, name):
    """مقدارِ یک فیلد از POST؛ اگر نامعتبر بود ``None`` (پیش‌نمایش نباید با ورودیِ نیمه‌کاره بشکند)."""
    field = form.fields[name]
    try:
        return field.clean(field.widget.value_from_datadict(form.data, form.files, form.add_prefix(name)))
    except Exception:  # noqa: BLE001
        return None


def _campaign_from_post(request) -> Campaign:
    """کمپینِ ذخیره‌نشده (فقط حافظه) از ورودیِ نیمه‌کاره‌یِ فرم، برایِ پیش‌نمایشِ پیام."""
    form = CampaignForm(request.POST)
    trigger = _lenient(form, "trigger_type") or "manual"
    campaign = Campaign(
        store=request.store, name=(_lenient(form, "name") or "").strip() or "پیشنهاد جدید", trigger_type=trigger,
        reward_type=_lenient(form, "reward_type") or Campaign.Reward.COUPON, coupon_type=_lenient(form, "coupon_type") or "percent",
        coupon_value=Decimal(_lenient(form, "coupon_value") or 0),
        coupon_max_discount=Decimal(_lenient(form, "coupon_max_discount")) if _lenient(form, "coupon_max_discount") else None,
        code_valid_days=_lenient(form, "code_valid_days"), code_prefix=(_lenient(form, "code_prefix") or "").strip().upper(),
        validity_from_delivery=bool(_lenient(form, "validity_from_delivery")),
        occasion_offset_days=_lenient(form, "occasion_offset_days") or 0,
    )
    code_expires = _lenient(form, "code_expires_at")
    if code_expires:
        campaign.code_expires_at = CampaignForm._end_of_day(code_expires)
    if trigger == Campaign.Trigger.OCCASION:
        campaign.occasion_kind = _lenient(form, "occasion_kind") or Campaign.Occasion.BIRTHDAY
        campaign.occasion_params = {
            "n": _lenient(form, "occ_n"), "amount": _lenient(form, "occ_amount"),
        }
    return campaign


@require_POST
@staff_required
@permission_required(DISCOUNT_MANAGE)
def campaign_sms_preview(request):
    """پیش‌نمایشِ فقط‌خواندنیِ پیامکِ این پیشنهاد (برایِ مرحله‌ی «اطلاع‌رسانی»). چیزی ذخیره/ارسال/صادر نمی‌شود."""
    campaign = _campaign_from_post(request)
    result = campaign_service.preview_message(campaign, channel="sms")
    return JsonResponse({
        "text": result["text"], "parts": result["parts"], "label": result["event_label"], "variables": result["variables"],
        "template_active": result["enabled"], "incomplete": bool(result["missing"]),
        "store_sms_enabled": _sms_globally_enabled(request.store),
    })


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
from apps.stores.authorization import SETTINGS_MANAGE, SMS_SETTINGS_MANAGE, membership_has_permission  # noqa: E402

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
            "platform_sms": bool(event.platform_sms_event),
        })
    return render(request, "dashboard/notification_templates.html", {
        "rows": rows, "active_page": "notifications", "sms_globally_enabled": _sms_globally_enabled(request.store),
    })


def _sms_globally_enabled(store) -> bool:
    """کلیدِ کلیِ پیامکِ فروشگاه؛ خاموش یعنی هیچ قالبِ پیامکی اثری ندارد."""
    from apps.core.models import ShopSettings

    try:
        return bool(ShopSettings.load(store=store).sms_enabled)
    except Exception:  # noqa: BLE001 — فروشگاهِ بدونِ ShopSettings: هشدار نشان داده می‌شود
        return False


def _event_or_404(key):
    if key not in notif_events.EVENTS:
        raise Http404
    return notif_events.EVENTS[key]


def _variables_for_editor(event):
    return sorted(event.variables.items())


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
            if channel == "sms" and event.platform_sms_event:
                messages.error(request, "متنِ این پیامک را راستی‌سی مدیریت می‌کند و قابلِ بازنشانی نیست.")
            elif channel == "sms" and event.legacy_sms_event and not membership_has_permission(
                    request.store_membership, SMS_SETTINGS_MANAGE):
                messages.error(request, "برایِ بازگشتِ قالبِ پیامک دسترسیِ «تنظیماتِ پیامک» لازم است.")
            elif channel in notif_events.CHANNELS:
                template_service.reset_template(store, event_key, channel)
                messages.info(request, "قالب به حالتِ پیش‌فرض بازگشت")
            return redirect("dashboard:notification-template-edit", event_key=event_key)
        saved = False
        can_legacy = membership_has_permission(request.store_membership, SMS_SETTINGS_MANAGE)
        for channel in notif_events.CHANNELS:
            if channel == "sms" and event.platform_sms_event:
                continue  # متنِ پیامکِ کمپین/مناسبت فقط در اختیارِ پلتفرم است؛ ورودیِ فروشنده کاملاً نادیده گرفته می‌شود
            if channel == "sms" and event.legacy_sms_event and not can_legacy:
                if request.POST.get("sms_body") is not None and request.POST.get("sms_body") != \
                        template_service.get_template(store, event_key, "sms")["body"]:
                    errors["sms"] = "برایِ ویرایشِ قالبِ پیامک دسترسیِ «تنظیماتِ پیامک» لازم است."
                continue
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
            if channel == "sms" and event.platform_sms_event:
                continue
            templates[channel] = {**templates[channel], "body": request.POST.get(f"{channel}_body", templates[channel]["body"]),
                                  "enabled": request.POST.get(f"{channel}_enabled") == "on"}
        templates["email"]["subject"] = request.POST.get("email_subject", templates["email"]["subject"])
    return render(request, "dashboard/notification_template_form.html", {
        "event": event, "templates": templates, "errors": errors, "active_page": "notifications",
        "variables": _variables_for_editor(event), "category_label": notif_events.CATEGORY_LABELS[event.category],
        "extra_recipients": templates["email"].get("extra_recipients", "") or templates["sms"].get("extra_recipients", ""),
        "sms_globally_enabled": _sms_globally_enabled(store),
        "can_edit_legacy_sms": membership_has_permission(request.store_membership, SMS_SETTINGS_MANAGE),
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
