"""Platform Admin (Section M) — host-isolated, staff/superuser-only, no
tenant resolution. Only ever reachable on a Host listed in ``settings.
RASTISI_PLATFORM_ADMIN_HOSTS`` (``apps.portal.middleware.
PlatformHostRoutingMiddleware``); every other Host 404s before this module
is even consulted, since ``request.urlconf`` never points here.

This is an intentionally minimal first slice: real, query-backed summary
counts (not mocked), a real branded login gate — but not yet the full
operational tooling (Store search/detail, billing overrides, ...) the wider
program describes. Extending it is additive, later work.
"""

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.models import AuditLogEntry
from apps.core.services.audit_service import record_audit_event
from apps.stores.hostnames import build_cross_host_url
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import StoreSubscription

from apps.core.services import session_service

from .forms import OwnerLoginForm, PlatformConfigurationForm, PlatformSmsConfigForm
from .models import PlatformAuditLogEntry
from .services.platform_config_service import get_platform_configuration, record_platform_audit_event
from .services.rate_limit import RateLimitExceeded, enforce_rate_limit


def _is_platform_staff(user):
    return user.is_authenticated and user.is_staff and user.is_superuser


def login_view(request):
    if _is_platform_staff(request.user):
        return redirect("portal_platform_admin:home")

    if request.method == "POST":
        form = OwnerLoginForm(request.POST)
        try:
            enforce_rate_limit(
                "platform_admin_login", request.META.get("REMOTE_ADDR", "unknown"),
                max_attempts=10, window_seconds=600,
            )
        except RateLimitExceeded:
            form.add_error(None, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/platform_admin/login.html", {"form": form})
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            # AUTH_USER_MODEL's USERNAME_FIELD is "username", not "email" — so
            # authenticate() must be called with the real username. We look the
            # user up by email first (this form is email-only, unlike the
            # identifier-based owner login) and authenticate with their actual
            # username, exactly like apps.portal.services.owner_auth_service.
            # authenticate_owner_by_identifier does for its email branch.
            candidate = get_user_model().objects.filter(email__iexact=email).first()
            user = None
            if candidate is not None:
                user = authenticate(
                    request, username=candidate.username, password=form.cleaned_data["password"],
                )
            if user is not None and _is_platform_staff(user):
                auth_login(request, user)
                session_service.apply_remember_me(request, form.cleaned_data.get("remember_me", False))
                record_platform_audit_event(
                    actor=user, action_code="platform_admin.login_succeeded",
                    object_type="User", object_id=user.pk, object_label=user.get_username(),
                )
                return redirect("portal_platform_admin:home")
            record_platform_audit_event(
                actor=user, action_code="platform_admin.login_failed",
                object_type="User", object_id=user.pk if user else None, object_label=email,
                result="failure",
            )
            form.add_error(None, "ایمیل، رمز عبور، یا دسترسی نامعتبر است")
    else:
        form = OwnerLoginForm()
    return render(request, "portal/platform_admin/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    return redirect("portal_platform_admin:login")


def not_found(request, exception=None):
    """``handler404`` for ``shop_core.urls_platform_admin`` — self-contained
    within ``portal/platform_admin/base.html``, same reasoning as ``apps.
    portal.views.not_found`` (ADR-97)."""
    return render(request, "portal/platform_admin/404.html", status=404)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def home(request):
    """داشبوردِ مدیرِ پلتفرم (بخشِ ۴) — همه‌ی KPIها از پرس‌وجویِ واقعی؛ هر
    معیاری که این معماری واقعاً اندازه نمی‌گیرد (صفِ کار، فضایِ ذخیره‌سازی)
    صادقانه «اطلاعات در دسترس نیست» نشان داده می‌شود، نه مقدارِ ساختگی."""
    from datetime import timedelta

    from django.db.models import Sum
    from django.utils import timezone

    from apps.billing.models import SubscriptionInvoice
    from apps.catalog.models import StoreIndustryInstallation
    from apps.core.models import ExportJob, ImportJob
    from apps.orders.models import ShippingMethod
    from apps.portal.services.platform_config_service import get_platform_configuration
    from apps.sms.models import SmsBalance, SmsLog

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    soon = now + timedelta(days=3)

    stores_without_subscription = Store.objects.exclude(
        subscriptions__is_current=True,
        subscriptions__status__in=[StoreSubscription.Status.ACTIVE, StoreSubscription.Status.TRIALING, StoreSubscription.Status.GRACE_PERIOD],
    ).count()
    month_revenue = SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.PAID, paid_at__gte=month_start,
    ).aggregate(total=Sum("amount_paid"))["total"] or 0
    sms_sent_this_month = SmsLog.objects.filter(status=SmsLog.Status.SENT, created_at__gte=month_start).count()
    recent_failures = (
        PlatformAuditLogEntry.objects.filter(result="failure", created_at__gte=week_ago).count()
        + AuditLogEntry.objects.filter(result="failure", created_at__gte=week_ago).count()
    )

    config = get_platform_configuration()
    failed_jobs = (
        ExportJob.objects.filter(status=ExportJob.Status.FAILED, created_at__gte=week_ago).count()
        + ImportJob.objects.filter(status=ImportJob.Status.FAILED, created_at__gte=week_ago).count()
    )
    domain_dns_errors = StoreDomain.objects.filter(verification_status=StoreDomain.VerificationStatus.FAILED).count()

    attention = []
    for sub in (
        StoreSubscription.objects.filter(is_current=True, status__in=[StoreSubscription.Status.EXPIRED, StoreSubscription.Status.PAST_DUE])
        .select_related("store").order_by("-updated_at")[:8]
    ):
        attention.append({"store": sub.store, "label": "اشتراکِ منقضی/معوق", "icon": "⏳"})
    for sub in (
        StoreSubscription.objects.filter(is_current=True, status=StoreSubscription.Status.TRIALING, trial_end_at__lte=soon, trial_end_at__gte=now)
        .select_related("store").order_by("trial_end_at")[:8]
    ):
        attention.append({"store": sub.store, "label": "پایانِ دوره‌ی آزمایشی تا ۳ روزِ آینده", "icon": "⌛"})
    for balance in SmsBalance.objects.filter(credits__lt=20).select_related("store")[:8]:
        attention.append({"store": balance.store, "label": f"اعتبارِ پیامکِ کم ({balance.credits})", "icon": "📉"})
    for domain in StoreDomain.objects.filter(verification_status=StoreDomain.VerificationStatus.FAILED).select_related("store")[:8]:
        attention.append({"store": domain.store, "label": f"خطایِ DNS دامنه‌ی {domain.hostname}", "icon": "🌐"})
    for store in Store.objects.filter(status=Store.Status.SUSPENDED)[:8]:
        attention.append({"store": store, "label": "فروشگاهِ تعلیق‌شده", "icon": "⛔"})
    for invoice in (
        SubscriptionInvoice.objects.filter(status=SubscriptionInvoice.Status.PAST_DUE).select_related("store")[:8]
    ):
        attention.append({"store": invoice.store, "label": f"فاکتورِ معوق ({invoice.number})", "icon": "💳"})
    active_store_ids = set(Store.objects.filter(status=Store.Status.ACTIVE).values_list("pk", flat=True))
    stores_with_shipping = set(
        ShippingMethod.objects.filter(is_active=True, store_id__in=active_store_ids).values_list("store_id", flat=True)
    )
    for store in Store.objects.filter(pk__in=active_store_ids - stores_with_shipping)[:8]:
        attention.append({"store": store, "label": "بدونِ روشِ ارسالِ فعال", "icon": "🚚"})
    for installation in (
        StoreIndustryInstallation.objects.filter(status=StoreIndustryInstallation.Status.FAILED).select_related("store")[:8]
    ):
        attention.append({"store": installation.store, "label": "نصبِ قالبِ صنف ناموفق", "icon": "🧱"})

    is_console_backend = config.sms_backend in ("", "console")
    context = {
        "store_count": Store.objects.count(),
        "active_store_count": Store.objects.filter(status=Store.Status.ACTIVE).count(),
        "trialing_count": StoreSubscription.objects.filter(status=StoreSubscription.Status.TRIALING, is_current=True).count(),
        "suspended_store_count": Store.objects.filter(status=Store.Status.SUSPENDED).count(),
        "stores_without_subscription": stores_without_subscription,
        "month_revenue": month_revenue,
        "sms_sent_this_month": sms_sent_this_month,
        "recent_failures": recent_failures,
        "attention": attention[:20],
        "sms_backend_label": "Console (توسعه — پیامکِ واقعی ارسال نمی‌شود)" if is_console_backend else config.get_sms_backend_display(),
        "sms_backend_ok": not is_console_backend,
        "payment_gateway_label": "پرداختِ دستی (بدونِ درگاهِ واقعی متصل)" if config.default_payment_provider == "manual" else config.default_payment_provider,
        "payment_gateway_ok": config.default_payment_provider != "manual",
        "failed_jobs": failed_jobs,
        "domain_dns_errors": domain_dns_errors,
        "active_nav": "dashboard",
    }
    return render(request, "portal/platform_admin/home.html", context)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def configuration(request):
    """تنظیماتِ عمومیِ پلتفرم — هویت/پیش‌فرض‌هایِ تجاری/عملیات (بخشِ ۲۰).
    پیکربندیِ درگاهِ پیامکِ مرکزی این‌جا نیست — نگاه کنید به ``sms_settings``."""
    config = get_platform_configuration()
    if request.method == "POST":
        form = PlatformConfigurationForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            changed = form.changed_data
            before = {name: getattr(config, name) for name in changed}
            form.save()

            from django.core.cache import cache

            cache.delete("portal:platform_configuration")
            record_platform_audit_event(
                actor=request.user, action_code="platform_configuration.updated",
                object_type="PlatformConfiguration", object_id=1,
                before=before, after={name: form.cleaned_data[name] for name in changed},
            )
            messages.success(request, "تنظیمات پلتفرم به‌روزرسانی شد.")
            return redirect("portal_platform_admin:configuration")
    else:
        form = PlatformConfigurationForm(instance=config)
    return render(request, "portal/platform_admin/configuration.html", {"form": form, "active_nav": "platform-settings"})


# ---------------------------------------------------------------- مرکز کنترل پیامک

_SMS_PROVIDER_NONSECRET_KEYS = (
    "melipayamak_enabled", "melipayamak_sender", "kavenegar_enabled",
    "kavenegar_sender", "otp_fallback_enabled",
)


def _sms_provider_context(*, config, test_result=None):
    from apps.sms.models import SmsBillingPolicy
    credentials = config.get_sms_credentials()
    return {
        "config": config,
        "policy": SmsBillingPolicy.load(),
        "credentials": credentials,
        "test_result": test_result,
        "melipayamak_password_is_configured": bool(credentials.get("melipayamak_password")),
        "kavenegar_api_key_is_configured": bool(credentials.get("kavenegar_api_key")),
        "melipayamak_enabled": credentials.get("melipayamak_enabled", "1") != "0",
        "kavenegar_enabled": credentials.get("kavenegar_enabled", "1") != "0",
        "otp_fallback_enabled": credentials.get("otp_fallback_enabled", "0") == "1",
        "active_nav": "sms-providers",
    }


def _save_provider_settings(request, config):
    from django.core.cache import cache

    primary = (request.POST.get("primary_provider") or request.POST.get("sms_backend") or "melipayamak").strip()
    if primary not in {"melipayamak", "kavenegar", "console"}:
        primary = "melipayamak"

    # legacy sender remains as fallback; provider-specific sender lives encrypted.
    legacy_sender = (request.POST.get("sms_sender_number") or "").strip()
    mel_sender = (request.POST.get("melipayamak_sender") or legacy_sender).strip()
    kav_sender = (request.POST.get("kavenegar_sender") or legacy_sender).strip()
    config.sms_backend = primary
    config.sms_sender_number = mel_sender if primary == "melipayamak" else kav_sender
    config.save(update_fields=["sms_backend", "sms_sender_number", "updated_at"])

    credentials = config.get_sms_credentials()
    updates = {
        "melipayamak_username": (request.POST.get("sms_melipayamak_username") or request.POST.get("melipayamak_username") or "").strip(),
        "melipayamak_password": (request.POST.get("sms_melipayamak_password") or request.POST.get("melipayamak_password") or "").strip(),
        "kavenegar_api_key": (request.POST.get("sms_kavenegar_api_key") or request.POST.get("kavenegar_api_key") or "").strip(),
        "melipayamak_sender": mel_sender,
        "kavenegar_sender": kav_sender,
        "melipayamak_enabled": "1" if ("melipayamak_enabled" in request.POST or request.POST.get("action") not in {"save_providers"}) else "0",
        "kavenegar_enabled": "1" if ("kavenegar_enabled" in request.POST or request.POST.get("action") not in {"save_providers"}) else "0",
        "otp_fallback_enabled": "1" if ("otp_fallback_enabled" in request.POST or "sms_otp_fallback_enabled" in request.POST) else "0",
    }
    # Legacy Phase-1 POSTs are copied to the new platform-owner OTP template too.
    body_id = (request.POST.get("sms_melipayamak_otp_body_id") or "").strip()
    variables_order = (request.POST.get("sms_melipayamak_otp_variables_order") or "").strip()
    k_template = (request.POST.get("sms_kavenegar_otp_template") or "").strip()
    if body_id or variables_order or k_template:
        from apps.sms.events import SmsEvent
        from apps.sms.models import SmsTemplate
        SmsTemplate.ensure_defaults()
        template = SmsTemplate.objects.get(event_key=SmsEvent.PLATFORM_OWNER_OTP)
        if body_id:
            template.melipayamak_body_id = body_id
        if variables_order:
            template.melipayamak_variables_order = variables_order
        if k_template:
            template.kavenegar_template = k_template
        template.save()
        # keep old encrypted keys as rollback/backward fallback
        updates.update({
            "melipayamak_otp_body_id": body_id,
            "melipayamak_otp_variables_order": variables_order or credentials.get("melipayamak_otp_variables_order", "otp_code"),
            "kavenegar_otp_template": k_template,
        })

    config.set_sms_credentials(remove_keys=_SMS_PROVIDER_NONSECRET_KEYS, **updates)
    config.save(update_fields=["encrypted_sms_credentials", "updated_at"])
    cache.delete("portal:platform_configuration")


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_settings(request):
    """Legacy URL؛ همان مرکز جدید شرکت‌های پیامکی را نمایش می‌دهد."""
    return sms_providers(request)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_providers(request):
    from apps.sms.events import SmsEvent
    from apps.sms.models import SmsBillingPolicy
    from apps.sms.services.billing_policy_service import record_platform_attempt
    from apps.portal.services.owner_sms_service import send_platform_sms

    config = get_platform_configuration()
    test_result = None
    if request.method == "POST":
        action = request.POST.get("action") or "legacy_save"
        if action == "save_policy":
            try:
                chars = int(request.POST.get("chars_per_credit") or 0)
                price = int(request.POST.get("price_per_credit_toman") or 0)
                overdraft = int(request.POST.get("otp_overdraft_limit") or 0)
            except ValueError:
                chars = price = overdraft = -1
            if not (1 <= chars <= 1000) or not (0 <= price <= 10_000_000) or not (0 <= overdraft <= 1000):
                messages.error(request, "مقادیر سیاست هزینه نامعتبر است.")
            else:
                policy = SmsBillingPolicy.load()
                before = {"chars": policy.chars_per_credit, "price": policy.price_per_credit_toman, "overdraft": policy.otp_overdraft_limit}
                policy.chars_per_credit = chars
                policy.price_per_credit_toman = price
                policy.otp_overdraft_limit = overdraft
                policy.save()
                record_platform_audit_event(
                    actor=request.user, action_code="platform_sms_policy.updated",
                    object_type="SmsBillingPolicy", object_id=policy.pk,
                    before=before, after={"chars": chars, "price": price, "overdraft": overdraft},
                )
                messages.success(request, "سیاست محاسبه و اعتبار پیامک ذخیره شد.")
                return redirect("portal_platform_admin:sms-providers")
        elif action == "test_provider":
            phone = (request.POST.get("test_phone") or "").strip()
            provider = (request.POST.get("provider") or "").strip()
            if not phone or provider not in {"melipayamak", "kavenegar"}:
                messages.error(request, "شماره موبایل و شرکت پیامکی معتبر لازم است.")
            else:
                result = send_platform_sms(to=phone, text="پیامک آزمایشی راستیسی", provider=provider)
                record_platform_attempt(
                    event_key=SmsEvent.PLATFORM_TEST, recipient=phone,
                    message="پیامک آزمایشی راستیسی", result=result,
                )
                test_result = {"provider": provider, "success": result.success, "error": result.error_message, "ref": result.provider_ref_id}
        else:
            _save_provider_settings(request, config)
            record_platform_audit_event(
                actor=request.user, action_code="platform_sms_providers.updated",
                object_type="PlatformConfiguration", object_id=1,
                metadata={"primary_provider": config.sms_backend},
            )
            messages.success(request, "تنظیمات شرکت‌های پیامکی ذخیره شد.")
            return redirect("portal_platform_admin:sms-providers")

    return render(request, "portal/platform_admin/sms_providers.html", _sms_provider_context(config=config, test_result=test_result))


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_templates(request):
    from apps.sms.events import SmsEvent
    from apps.sms.models import SmsTemplate
    from apps.sms.services.billing_policy_service import quote_message

    SmsTemplate.ensure_defaults()
    templates = list(SmsTemplate.objects.exclude(event_key__in=[SmsEvent.PLATFORM_TEST, SmsEvent.NOTIFICATION]).order_by("event_key"))
    for item in templates:
        item.preview_quote = quote_message(item.body)
    return render(request, "portal/platform_admin/sms_templates.html", {
        "templates": templates, "active_nav": "sms-templates",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_template_edit(request, event_key):
    from apps.sms.events import EVENT_VARIABLES, SmsEvent
    from apps.sms.models import SmsBillingPolicy, SmsTemplate
    from apps.sms.services.billing_policy_service import quote_message, record_platform_attempt
    from apps.sms.services.sms_service import SmsTemplateError, validate_template_body
    from apps.portal.services.owner_sms_service import send_platform_otp, send_platform_sms

    SmsTemplate.ensure_defaults()
    template = get_object_or_404(SmsTemplate, event_key=event_key)
    if request.method == "POST":
        action = request.POST.get("action") or "save"
        if action == "test":
            phone = (request.POST.get("test_phone") or "").strip()
            if not phone:
                messages.error(request, "شماره موبایل تست را وارد کنید.")
            else:
                if template.event_key in {SmsEvent.OTP, SmsEvent.PLATFORM_OWNER_OTP}:
                    result = send_platform_otp(
                        to=phone, code="123456", purpose="platform_admin_template_test",
                        template_event_key=template.event_key,
                    )
                    sample = template.body.replace("{otp_code}", "123456").replace("{expire_minutes}", "2").replace("{shop_name}", "فروشگاه آزمایشی")
                    record_platform_attempt(event_key=template.event_key, recipient=phone, message=sample, result=result, protect_body=True)
                else:
                    sample = template.body
                    samples = {"customer_name": "کاربر آزمایشی", "shop_name": "فروشگاه آزمایشی", "order_code": "TEST-1", "amount": "100000", "tracking_code": "TRACK-1"}
                    for key, value in samples.items():
                        sample = sample.replace("{" + key + "}", value)
                    # تست باید دقیقاً مسیر واقعی Production را امتحان کند: اگر
                    # Provider اصلی ملی‌پیامک و BodyId موجود است، Pattern ارسال شود.
                    from apps.portal.services.owner_sms_service import get_platform_sms_backend
                    from apps.sms.services.backends import MelipayamakBackend
                    backend = get_platform_sms_backend()
                    if isinstance(backend, MelipayamakBackend) and template.melipayamak_body_id:
                        result = backend.send_pattern(
                            to=phone, body_id=template.melipayamak_body_id,
                            variables=samples, variables_order=template.melipayamak_variables_order or "otp_code",
                        )
                        result.provider = "melipayamak"
                    else:
                        result = send_platform_sms(to=phone, text=sample)
                    record_platform_attempt(event_key=template.event_key, recipient=phone, message=sample, result=result)
                if result.success:
                    messages.success(request, "پیامک تست با موفقیت به Provider تحویل شد.")
                else:
                    messages.error(request, f"ارسال تست ناموفق بود: {result.error_message}")
        else:
            title = (request.POST.get("title") or "").strip()
            body = (request.POST.get("body") or "").strip()
            try:
                validate_template_body(template.event_key, body)
            except SmsTemplateError as exc:
                messages.error(request, str(exc))
            else:
                if not title or not body:
                    messages.error(request, "عنوان و متن قالب الزامی‌اند.")
                else:
                    body_id = (request.POST.get("melipayamak_body_id") or "").strip()
                    variables_order = (request.POST.get("melipayamak_variables_order") or "").strip() or "otp_code"
                    order_keys = [key.strip() for key in variables_order.replace(";", ",").split(",") if key.strip()]
                    allowed_keys = set(EVENT_VARIABLES.get(template.event_key, {}))
                    unknown_order = [key for key in order_keys if key not in allowed_keys]
                    if body_id and not body_id.isdigit():
                        messages.error(request, "BodyId ملی‌پیامک باید عدد باشد.")
                    elif body_id and unknown_order:
                        messages.error(request, "ترتیب متغیرهای Pattern شامل متغیر نامعتبر است: " + "، ".join(unknown_order))
                    else:
                        template.title = title
                        template.body = body
                        template.is_active = "is_active" in request.POST
                        template.melipayamak_body_id = body_id
                        template.melipayamak_variables_order = variables_order
                        template.kavenegar_template = (request.POST.get("kavenegar_template") or "").strip()
                        template.save()
                        record_platform_audit_event(
                            actor=request.user, action_code="platform_sms_template.updated",
                            object_type="SmsTemplate", object_id=template.pk, object_label=template.title,
                        )
                        messages.success(request, "قالب پیامک ذخیره شد.")
                        return redirect("portal_platform_admin:sms-template-edit", event_key=template.event_key)
                    # validation error: remain on edit page without mutating the template
                    quote = quote_message(template.body)
                    return render(request, "portal/platform_admin/sms_template_edit.html", {
                        "template": template, "quote": quote, "policy": SmsBillingPolicy.load(),
                        "variables": EVENT_VARIABLES.get(template.event_key, {}),
                        "active_nav": "sms-templates",
                    })

    quote = quote_message(template.body)
    return render(request, "portal/platform_admin/sms_template_edit.html", {
        "template": template, "quote": quote, "policy": SmsBillingPolicy.load(),
        "variables": EVENT_VARIABLES.get(template.event_key, {}),
        "active_nav": "sms-templates",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_messages(request):
    from apps.sms.events import SmsEvent
    from apps.sms.models import SmsLog

    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    event_key = (request.GET.get("event_key") or "").strip()
    provider = (request.GET.get("provider") or "").strip()
    queryset = SmsLog.objects.select_related("store").order_by("-created_at")
    if query:
        queryset = queryset.filter(Q(recipient__icontains=query) | Q(store__name__icontains=query))
    if status in SmsLog.Status.values:
        queryset = queryset.filter(status=status)
    if event_key in SmsEvent.values:
        queryset = queryset.filter(event_key=event_key)
    if provider in {"melipayamak", "kavenegar", "smsrasti", "console"}:
        queryset = queryset.filter(provider=provider)
    paginator = Paginator(queryset, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/sms_messages.html", {
        "page": page, "query": query, "status": status, "event_key": event_key,
        "provider": provider, "status_choices": SmsLog.Status.choices,
        "event_choices": SmsEvent.choices,
        "provider_choices": [("melipayamak", "ملی‌پیامک"), ("kavenegar", "کاوه‌نگار"), ("smsrasti", "SmsRasti"), ("console", "Console")],
        "active_nav": "sms-messages",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def stores(request):
    """جست‌وجو/فهرستِ فروشگاه‌ها (بخشِ ۵) — نام/مالک/موبایل/ایمیل، وضعیتِ
    فروشگاه، وضعیتِ اشتراک، پلن، صنف، بازه‌ی تاریخِ ایجاد."""
    from django.db.models import Count, Prefetch

    from apps.subscriptions.models import Plan

    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    sub_status = (request.GET.get("subscription_status") or "").strip()
    plan_id = (request.GET.get("plan") or "").strip()
    industry_id = (request.GET.get("industry") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    queryset = (
        Store.objects.select_related("industry_installation__industry_template")
        .prefetch_related(
            Prefetch(
                "memberships",
                queryset=StoreMembership.objects.filter(
                    role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
                ).select_related("user", "user__owner_profile"),
                to_attr="owner_memberships",
            ),
            Prefetch(
                "subscriptions",
                queryset=StoreSubscription.objects.filter(is_current=True).select_related("plan_version__plan"),
                to_attr="current_subscriptions",
            ),
            Prefetch(
                "domains",
                queryset=StoreDomain.objects.filter(
                    domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                    verification_status=StoreDomain.VerificationStatus.VERIFIED,
                ),
                to_attr="verified_custom_domains",
            ),
        )
        .annotate(product_count=Count("products", distinct=True), order_count=Count("orders", distinct=True))
        .order_by("-created_at")
    )

    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(slug__icontains=query) | Q(platform_code__icontains=query)
            | Q(admin_subdomain__icontains=query)
            | Q(memberships__user__owner_profile__full_name__icontains=query)
            | Q(memberships__user__owner_profile__phone__icontains=query)
            | Q(memberships__user__email__icontains=query)
        ).distinct()
    if status in Store.Status.values:
        queryset = queryset.filter(status=status)
    if sub_status in StoreSubscription.Status.values:
        queryset = queryset.filter(subscriptions__is_current=True, subscriptions__status=sub_status)
    if plan_id.isdigit():
        queryset = queryset.filter(subscriptions__is_current=True, subscriptions__plan_version__plan_id=plan_id)
    if industry_id.isdigit():
        queryset = queryset.filter(industry_installation__industry_template_id=industry_id)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/stores.html", {
        "page": page, "query": query, "status": status, "sub_status": sub_status,
        "plan_id": plan_id, "industry_id": industry_id, "date_from": date_from, "date_to": date_to,
        "status_choices": Store.Status.choices, "subscription_status_choices": StoreSubscription.Status.choices,
        "plans": Plan.objects.filter(is_active=True).order_by("display_order"),
        "active_nav": "stores",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_detail(request, store_public_id):
    from apps.sms.services.balance_service import get_or_create_balance

    store = get_object_or_404(Store, public_id=store_public_id)
    domains = store.domains.all().order_by("-is_primary", "-created_at")
    memberships = store.memberships.select_related("user", "user__owner_profile").order_by("-status", "role")
    owner_membership = next(
        (m for m in memberships if m.role == StoreMembership.Role.OWNER
         and m.status == StoreMembership.MembershipStatus.ACTIVE), None,
    )
    current_subscription = store.subscriptions.filter(is_current=True).select_related("plan_version__plan").first()
    subscription_history = store.subscriptions.exclude(pk=current_subscription.pk if current_subscription else None).select_related("plan_version__plan").order_by("-created_at")[:20]
    invoices = store.subscription_invoices.order_by("-created_at")[:20]
    audit_entries = store.audit_log_entries.order_by("-created_at")[:30]
    notes = store.platform_internal_notes.select_related("author").order_by("-created_at")
    sms_balance = get_or_create_balance(store=store)
    industry_installation = getattr(store, "industry_installation", None)
    product_count = store.products.filter(status="active").count()
    order_count = store.orders.count()
    tab = request.GET.get("tab", "overview")

    return render(request, "portal/platform_admin/store_detail.html", {
        "store": store, "domains": domains, "memberships": memberships, "owner_membership": owner_membership,
        "current_subscription": current_subscription, "subscription_history": subscription_history,
        "invoices": invoices, "audit_entries": audit_entries, "notes": notes, "sms_balance": sms_balance,
        "industry_installation": industry_installation, "product_count": product_count, "order_count": order_count,
        "tab": tab, "active_nav": "stores",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_suspend(request, store_public_id):
    from apps.stores.services.store_status_service import StoreStatusError, suspend_store

    store = get_object_or_404(Store, public_id=store_public_id)
    reason = (request.POST.get("reason") or "").strip()
    note = (request.POST.get("note") or "").strip()
    try:
        suspend_store(store, actor=request.user, reason=reason, note=note)
        messages.success(request, f"فروشگاه «{store.name}» تعلیق شد.")
    except StoreStatusError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_activate(request, store_public_id):
    from apps.stores.services.store_status_service import StoreStatusError, activate_store

    store = get_object_or_404(Store, public_id=store_public_id)
    try:
        activate_store(store, actor=request.user)
        messages.success(request, f"فروشگاه «{store.name}» فعال شد.")
    except StoreStatusError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_support_login(request, store_public_id):
    """ورودِ پشتیبانی (بخشِ ۷) — بلیتِ یک‌بارمصرف صادر و به میزبانِ مدیریتِ
    همان فروشگاه هدایت می‌کند، دقیقاً مثلِ ``apps.portal.views.enter_admin``
    (همان الگویِ میزبان/پورت، از جمله حالتِ DEBUG)."""
    from django.conf import settings as dj_settings

    from apps.portal.services import handoff_service

    store = get_object_or_404(Store, public_id=store_public_id)
    try:
        ticket = handoff_service.issue_support_ticket(actor=request.user, store=store)
    except handoff_service.HandoffError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:store-detail", store_public_id)

    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.support_login_issued",
        object_type="Store", object_id=str(store.pk), object_label=store.name,
    )
    admin_host = f"{store.admin_subdomain}.{dj_settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    return redirect(build_cross_host_url(
        request, hostname=admin_host, path=f"/admin-portal/handoff/{ticket.token}/",
    ))


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_extend_trial(request, store_public_id):
    from apps.subscriptions.services.subscription_service import SubscriptionError, extend_trial

    store = get_object_or_404(Store, public_id=store_public_id)
    subscription = store.subscriptions.filter(is_current=True).first()
    if subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    raw_days = (request.POST.get("days") or "").strip()
    days = int(raw_days) if raw_days.isdigit() and int(raw_days) > 0 else None
    if days is None:
        messages.error(request, "تعدادِ روزهایِ افزوده باید یک عددِ مثبت باشد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    reason = (request.POST.get("reason") or "").strip() or f"تمدیدِ دستیِ {days} روزه توسطِ مدیرِ پلتفرم"
    try:
        extend_trial(subscription, days=days, actor=request.user, reason=reason)
    except SubscriptionError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:store-detail", store_public_id)

    messages.success(request, f"دوره‌ی آزمایشیِ «{store.name}» به‌مدتِ {days} روز تمدید شد.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_set_trial_end(request, store_public_id):
    from datetime import datetime

    from django.utils import timezone

    from apps.subscriptions.services.subscription_service import SubscriptionError, set_trial_end

    store = get_object_or_404(Store, public_id=store_public_id)
    subscription = store.subscriptions.filter(is_current=True).first()
    if subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    raw_end = (request.POST.get("trial_end_at") or "").strip()
    parsed = None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw_end, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        messages.error(request, "تاریخ/زمانِ پایانِ تریال معتبر نیست.")
        return redirect("portal_platform_admin:store-detail", store_public_id)
    end_at = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed

    reason = (request.POST.get("reason") or "").strip()
    try:
        set_trial_end(subscription, end_at=end_at, actor=request.user, reason=reason)
    except SubscriptionError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:store-detail", store_public_id)

    messages.success(request, f"پایانِ دوره‌ی آزمایشیِ «{store.name}» تنظیم شد.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_end_trial_now(request, store_public_id):
    from apps.subscriptions.services.subscription_service import SubscriptionError, end_trial_now

    store = get_object_or_404(Store, public_id=store_public_id)
    subscription = store.subscriptions.filter(is_current=True).first()
    if subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    reason = (request.POST.get("reason") or "").strip()
    try:
        end_trial_now(subscription, actor=request.user, reason=reason)
    except SubscriptionError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:store-detail", store_public_id)

    messages.success(request, f"دوره‌ی آزمایشیِ «{store.name}» همین حالا پایان یافت.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_change_plan(request, store_public_id):
    """SUB-001 (بازبینیِ مستقلِ معماری، Repair 2): این یک overrideِ اپراتوریِ
    صریحِ مدیرِ پلتفرم است — نه یک مسیرِ جایگزینِ خریدِ مرچنت — پس بدونِ
    round-tripِ preview_token (که ذاتاً برایِ محافظتِ خریدِ مرچنتِ 5A طراحی
    شده بود و قبلاً هم به‌اشتباه به کلیدِ نادرستِ ``preview["preview_token"]``
    دسترسی پیدا می‌کرد، در حالی‌که ``preview_plan_change`` کلیدِ ``token`` را
    برمی‌گرداند) مستقیماً از ``execute_platform_admin_plan_override`` عبور
    می‌کند."""
    from apps.subscriptions.models import PlanVersion
    from apps.subscriptions.services.plan_change_service import (
        PlanChangeError,
        execute_platform_admin_plan_override,
    )
    from apps.subscriptions.services.subscription_service import SubscriptionError

    store = get_object_or_404(Store, public_id=store_public_id)
    target_version_id = (request.POST.get("plan_version_id") or "").strip()
    target_version = PlanVersion.objects.filter(pk=target_version_id, status=PlanVersion.Status.PUBLISHED).first()
    if target_version is None:
        messages.error(request, "نسخه‌ی پلنِ انتخاب‌شده معتبر نیست.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    try:
        execute_platform_admin_plan_override(
            store, target_version, actor=request.user,
            reason=(request.POST.get("reason") or "").strip(),
        )
        messages.success(request, f"پلنِ «{store.name}» به «{target_version.plan.name}» تغییر کرد.")
    except (PlanChangeError, SubscriptionError) as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_extend_subscription(request, store_public_id):
    from datetime import timedelta

    from django.utils import timezone

    from apps.subscriptions.services.subscription_service import renew_subscription

    store = get_object_or_404(Store, public_id=store_public_id)
    subscription = store.subscriptions.filter(is_current=True).first()
    if subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    raw_days = (request.POST.get("days") or "").strip()
    days = int(raw_days) if raw_days.isdigit() and int(raw_days) > 0 else None
    if days is None:
        messages.error(request, "تعدادِ روزهایِ تمدید باید یک عددِ مثبت باشد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)

    period_start = subscription.current_period_start or timezone.now()
    period_end = (subscription.current_period_end or timezone.now()) + timedelta(days=days)
    renew_subscription(subscription, period_start=period_start, period_end=period_end, actor=request.user)
    messages.success(request, f"اشتراکِ «{store.name}» به‌مدتِ {days} روز تمدید شد.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def store_add_note(request, store_public_id):
    from .models import PlatformInternalNote

    store = get_object_or_404(Store, public_id=store_public_id)
    body = (request.POST.get("body") or "").strip()
    if not body:
        messages.error(request, "متنِ یادداشت نمی‌تواند خالی باشد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)
    PlatformInternalNote.objects.create(store=store, author=request.user, body=body)
    record_audit_event(
        store=store, actor=request.user, action_code="platform_admin.note_added",
        object_type="Store", object_id=store.pk, object_label=store.name,
    )
    messages.success(request, "یادداشت ثبت شد.")
    return redirect("portal_platform_admin:store-detail", store_public_id)

# ---------------------------------------------------------------- کاربران و مالکین

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def users(request):
    from django.contrib.auth import get_user_model
    from django.db.models import Count

    User = get_user_model()
    query = (request.GET.get("q") or "").strip()
    owner_user_ids = StoreMembership.objects.filter(
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
    ).values("user_id").distinct()
    queryset = (
        User.objects.filter(pk__in=owner_user_ids)
        .select_related("owner_profile")
        .annotate(
            owned_store_count=Count(
                "store_memberships",
                filter=Q(store_memberships__role=StoreMembership.Role.OWNER,
                          store_memberships__status=StoreMembership.MembershipStatus.ACTIVE),
                distinct=True,
            ),
        )
        .order_by("-date_joined")
    )
    if query:
        queryset = queryset.filter(
            Q(owner_profile__full_name__icontains=query) | Q(owner_profile__phone__icontains=query)
            | Q(email__icontains=query) | Q(username__icontains=query)
        )
    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/users.html", {"page": page, "query": query, "active_nav": "users"})


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def user_detail(request, user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("owner_profile"), pk=user_id)
    memberships = (
        StoreMembership.objects.filter(user=user, status=StoreMembership.MembershipStatus.ACTIVE)
        .select_related("store").order_by("-role")
    )
    notes = user.platform_internal_notes_about.select_related("author").order_by("-created_at")
    return render(request, "portal/platform_admin/user_detail.html", {
        "profile_user": user, "memberships": memberships, "notes": notes, "active_nav": "users",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def user_activate(request, user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    user.is_active = True
    user.save(update_fields=["is_active"])
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.user_activated",
        object_type="User", object_id=user.pk, object_label=user.get_username(),
    )
    messages.success(request, "کاربر فعال شد.")
    return redirect("portal_platform_admin:user-detail", user_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def user_suspend(request, user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "دلیلِ تعلیقِ حساب الزامی است.")
        return redirect("portal_platform_admin:user-detail", user_id)
    user.is_active = False
    user.save(update_fields=["is_active"])
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.user_suspended",
        object_type="User", object_id=user.pk, object_label=user.get_username(),
        metadata={"reason": reason},
    )
    messages.success(request, "کاربر تعلیق شد.")
    return redirect("portal_platform_admin:user-detail", user_id)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def user_add_note(request, user_id):
    from django.contrib.auth import get_user_model

    from .models import PlatformInternalNote

    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)
    body = (request.POST.get("body") or "").strip()
    if not body:
        messages.error(request, "متنِ یادداشت نمی‌تواند خالی باشد.")
        return redirect("portal_platform_admin:user-detail", user_id)
    PlatformInternalNote.objects.create(about_user=user, author=request.user, body=body)
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.user_note_added",
        object_type="User", object_id=user.pk, object_label=user.get_username(),
    )
    messages.success(request, "یادداشت ثبت شد.")
    return redirect("portal_platform_admin:user-detail", user_id)


# ---------------------------------------------------------------- پلن‌های اشتراک

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plans(request):
    from apps.subscriptions.models import Plan

    plan_list = Plan.objects.prefetch_related("versions").order_by("display_order", "code")
    return render(request, "portal/platform_admin/plans.html", {"plans": plan_list, "active_nav": "plans"})


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plan_form(request, plan_id=None):
    """ساختِ پلن + نسخه‌ی پیش‌نویسِ آن، یا افزودنِ یک نسخه‌ی تازه به پلنِ
    موجود — هرگز شرایطِ یک نسخه‌ی ``published`` را ویرایش نمی‌کند (ADR-63)؛
    ویرایشِ یک پلنِ موجود همیشه یک نسخه‌ی پیش‌نویسِ تازه می‌سازد."""
    from apps.subscriptions.models import EntitlementDefinition, Plan
    from apps.subscriptions.services.plan_service import create_plan_version, set_plan_entitlement

    plan = get_object_or_404(Plan, pk=plan_id) if plan_id else None
    entitlements = EntitlementDefinition.objects.filter(is_active=True).order_by("key")
    latest_version = plan.versions.order_by("-version_number").first() if plan else None

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        code = (request.POST.get("code") or "").strip()
        public_title = (request.POST.get("public_title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        display_price = request.POST.get("display_price") or "0"
        trial_days = request.POST.get("trial_days") or "0"
        billing_interval = request.POST.get("billing_interval") or "monthly"
        display_order = request.POST.get("display_order") or "0"
        is_recommended = request.POST.get("is_recommended") == "on"

        if not name or not code:
            messages.error(request, "نام و کدِ پلن الزامی است.")
            return render(request, "portal/platform_admin/plan_form.html", {
                "plan": plan, "entitlements": entitlements, "latest_version": latest_version, "active_nav": "plans",
            })

        if plan is None:
            plan = Plan.objects.create(
                code=code, name=name, public_title=public_title, description=description,
                display_order=int(display_order) if display_order.isdigit() else 0,
                is_recommended=is_recommended,
            )
            action_code = "platform_admin.plan_created"
        else:
            plan.name = name
            plan.public_title = public_title
            plan.description = description
            plan.display_order = int(display_order) if display_order.isdigit() else 0
            plan.is_recommended = is_recommended
            plan.save(update_fields=["name", "public_title", "description", "display_order", "is_recommended", "updated_at"])
            action_code = "platform_admin.plan_updated"

        version = create_plan_version(
            plan,
            display_price=display_price or 0, trial_days=trial_days or 0,
            billing_interval=billing_interval,
        )
        for entitlement in entitlements:
            field_prefix = f"entitlement_{entitlement.key}"
            if entitlement.entitlement_type == EntitlementDefinition.EntitlementType.BOOLEAN:
                set_plan_entitlement(version, entitlement.key, is_enabled=request.POST.get(field_prefix) == "on")
            elif entitlement.entitlement_type == EntitlementDefinition.EntitlementType.INTEGER_LIMIT:
                is_unlimited = request.POST.get(f"{field_prefix}_unlimited") == "on"
                raw_limit = (request.POST.get(field_prefix) or "").strip()
                if is_unlimited:
                    set_plan_entitlement(version, entitlement.key, is_unlimited=True)
                elif raw_limit.isdigit():
                    set_plan_entitlement(version, entitlement.key, is_unlimited=False, integer_limit=int(raw_limit))
                # نه «نامحدود» و نه مقداری وارد شده — این حق‌دسترسی برایِ این
                # نسخه نامشخص می‌ماند (رفتارِ پیش‌فرضِ معماریِ Entitlement)،
                # به‌جایِ ساختِ یک ردیفِ نامعتبر با هردو مقدار خالی.

        record_platform_audit_event(
            actor=request.user, action_code=action_code,
            object_type="Plan", object_id=plan.pk, object_label=plan.name,
            after={"new_draft_version": version.version_number},
        )
        messages.success(request, f"پلن «{plan.name}» ذخیره شد (نسخه‌ی پیش‌نویسِ جدید: v{version.version_number}).")
        return redirect("portal_platform_admin:plans")

    existing_entitlements = {}
    if latest_version:
        existing_entitlements = {pe.entitlement_id: pe for pe in latest_version.plan_entitlements.all()}
    for entitlement in entitlements:
        entitlement.existing = existing_entitlements.get(entitlement.pk)
    return render(request, "portal/platform_admin/plan_form.html", {
        "plan": plan, "entitlements": entitlements, "latest_version": latest_version, "active_nav": "plans",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plan_archive(request, plan_id):
    from apps.subscriptions.models import Plan, StoreSubscription as _StoreSub

    plan = get_object_or_404(Plan, pk=plan_id)
    in_use = _StoreSub.objects.filter(
        plan_version__plan=plan, is_current=True,
    ).exists()
    if in_use:
        messages.error(request, "این پلن هم‌اکنون توسطِ فروشگاه‌هایی استفاده می‌شود؛ به‌جایِ حذف، غیرفعالش کنید.")
        return redirect("portal_platform_admin:plans")
    plan.is_active = not plan.is_active
    plan.save(update_fields=["is_active", "updated_at"])
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.plan_archived" if not plan.is_active else "platform_admin.plan_unarchived",
        object_type="Plan", object_id=plan.pk, object_label=plan.name,
    )
    messages.success(request, f"پلن «{plan.name}» {'غیرفعال' if not plan.is_active else 'فعال'} شد.")
    return redirect("portal_platform_admin:plans")


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plan_version_publish(request, plan_id, version_id):
    from apps.subscriptions.models import PlanVersion
    from apps.subscriptions.services.plan_service import publish_plan_version

    version = get_object_or_404(PlanVersion, pk=version_id, plan_id=plan_id)
    try:
        publish_plan_version(version, actor=request.user)
        messages.success(request, f"نسخه‌ی v{version.version_number} پلنِ «{version.plan.name}» منتشر شد.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:plans")


# ---------------------------------------------------------------- اشتراک فروشگاه‌ها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def subscriptions(request):
    from apps.subscriptions.models import Plan

    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    plan_id = (request.GET.get("plan") or "").strip()

    queryset = (
        StoreSubscription.objects.filter(is_current=True)
        .select_related("store", "plan_version__plan").order_by("-created_at")
    )
    if query:
        queryset = queryset.filter(store__name__icontains=query)
    if status in StoreSubscription.Status.values:
        queryset = queryset.filter(status=status)
    if plan_id.isdigit():
        queryset = queryset.filter(plan_version__plan_id=plan_id)

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/subscriptions.html", {
        "page": page, "query": query, "status": status, "plan_id": plan_id,
        "status_choices": StoreSubscription.Status.choices,
        "plans": Plan.objects.filter(is_active=True).order_by("display_order"),
        "active_nav": "subscriptions",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def subscription_cancel(request, subscription_id):
    from apps.subscriptions.services.subscription_service import cancel_immediately

    subscription = get_object_or_404(StoreSubscription, pk=subscription_id)
    reason = (request.POST.get("reason") or "").strip()
    cancel_immediately(subscription, actor=request.user, reason=reason)
    messages.success(request, f"اشتراکِ «{subscription.store.name}» لغو شد.")
    return redirect("portal_platform_admin:subscriptions")


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def subscription_suspend(request, subscription_id):
    from apps.subscriptions.services.subscription_service import suspend_subscription

    subscription = get_object_or_404(StoreSubscription, pk=subscription_id)
    reason = (request.POST.get("reason") or "").strip()
    try:
        suspend_subscription(subscription, actor=request.user, reason=reason)
        messages.success(request, f"اشتراکِ «{subscription.store.name}» معلق شد.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:subscriptions")


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def subscription_resume(request, subscription_id):
    from apps.subscriptions.services.subscription_service import resume_subscription

    subscription = get_object_or_404(StoreSubscription, pk=subscription_id)
    try:
        resume_subscription(subscription, actor=request.user)
        messages.success(request, f"اشتراکِ «{subscription.store.name}» از سر گرفته شد.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:subscriptions")


# ---------------------------------------------------------------- پرداخت‌ها و فاکتورها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payments(request):
    from apps.billing.models import SubscriptionInvoice

    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    queryset = SubscriptionInvoice.objects.select_related("store", "plan_version__plan").order_by("-created_at")
    if query:
        queryset = queryset.filter(Q(store__name__icontains=query) | Q(number__icontains=query))
    if status in SubscriptionInvoice.Status.values:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/payments.html", {
        "page": page, "query": query, "status": status,
        "status_choices": SubscriptionInvoice.Status.choices, "active_nav": "payments",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_invoice_detail(request, invoice_id):
    from apps.billing.models import SubscriptionInvoice

    invoice = get_object_or_404(
        SubscriptionInvoice.objects.select_related("store", "plan_version__plan").prefetch_related("lines", "payment_attempts"),
        pk=invoice_id,
    )
    return render(request, "portal/platform_admin/payment_invoice_detail.html", {
        "invoice": invoice, "active_nav": "payments",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_manual_add(request):
    """ثبتِ پرداختِ دستی (بخشِ ۱۱) — از همان مسیرِ واقعیِ ``confirmation_
    service.mark_invoice_paid_manually`` عبور می‌کند (نه یک رخدادِ حسابرسیِ
    مجزا بدونِ اثرِ مالی)، پس فاکتور واقعاً پرداخت‌شده علامت می‌خورد و
    اشتراک هم فعال/تمدید می‌شود؛ همیشه با ذکرِ مرجع/دلیل/مدیرِ مسئول و
    حسابرسی‌شده. مبلغ باید دقیقاً با مبلغِ باقی‌مانده‌ی فاکتور برابر باشد
    (سرویسِ پایه پرداختِ جزئی را پشتیبانی نمی‌کند)."""
    from apps.billing.models import SubscriptionInvoice
    from apps.billing.services.confirmation_service import ConfirmationError, mark_invoice_paid_manually

    if request.method == "POST":
        invoice_id = (request.POST.get("invoice_id") or "").strip()
        amount = (request.POST.get("amount") or "").strip()
        reference = (request.POST.get("reference") or "").strip()
        note = (request.POST.get("note") or "").strip()
        invoice = SubscriptionInvoice.objects.filter(pk=invoice_id).select_related("store").first()
        if invoice is None or not amount or not reference or not note:
            messages.error(request, "فاکتور، مبلغ، مرجع و دلیل همگی الزامی‌اند.")
        elif amount != str(invoice.amount_due):
            messages.error(request, f"مبلغ باید دقیقاً برابرِ مبلغِ باقی‌مانده‌ی فاکتور ({invoice.amount_due}) باشد.")
        else:
            try:
                mark_invoice_paid_manually(
                    invoice, actor=request.user, note=f"مرجع: {reference} — {note}",
                )
                messages.success(request, f"پرداختِ دستیِ فاکتورِ «{invoice.number}» ثبت و اعمال شد.")
                return redirect("portal_platform_admin:payment-invoice-detail", invoice.pk)
            except ConfirmationError as exc:
                messages.error(request, str(exc))

    invoices = SubscriptionInvoice.objects.filter(
        status__in=SubscriptionInvoice.PAYABLE_STATUSES,
    ).select_related("store").order_by("-created_at")[:100]
    return render(request, "portal/platform_admin/payment_manual_add.html", {
        "invoices": invoices, "active_nav": "payments",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def billing_zibal_settings(request):
    """پیکربندیِ زیبال برایِ پرداختِ اشتراکِ خودِ پلتفرم (Phase 3) — کاملاً جدا
    از اعتبارنامه‌ی زیبالِ هر Store برایِ سفارش‌هایِ مشتریانش
    (``apps.orders.PaymentGatewayConfig`` / Merchant Admin › درگاه‌ها).
    Secretِ خالی یعنی «بدون تغییر» (همان الگویِ تنظیماتِ پیامک)."""
    from django.core.cache import cache

    from apps.billing.providers import registry as billing_registry

    config = get_platform_configuration()
    if request.method == "POST":
        active_provider = (request.POST.get("default_payment_provider") or "manual").strip()
        if active_provider not in {"manual", "zibal"}:
            messages.error(request, "درگاهِ انتخاب‌شده معتبر نیست.")
        else:
            before = {
                "default_payment_provider": config.default_payment_provider,
                "zibal_sandbox_mode": config.zibal_sandbox_mode,
            }
            config.default_payment_provider = active_provider
            config.zibal_sandbox_mode = "zibal_sandbox_mode" in request.POST
            merchant = (request.POST.get("zibal_merchant") or "").strip()
            config.set_zibal_credentials(merchant=merchant)
            config.save(update_fields=[
                "default_payment_provider", "zibal_sandbox_mode",
                "encrypted_zibal_credentials", "updated_at",
            ])
            cache.delete("portal:platform_configuration")
            record_platform_audit_event(
                actor=request.user, action_code="platform_billing_zibal.updated",
                object_type="PlatformConfiguration", object_id=1,
                before=before,
                after={"default_payment_provider": active_provider, "zibal_sandbox_mode": config.zibal_sandbox_mode},
                metadata={"merchant_configured": bool(merchant)},
            )
            messages.success(request, "تنظیماتِ زیبالِ پلتفرم ذخیره شد.")
            return redirect("portal_platform_admin:billing-zibal-settings")

    credentials = config.get_zibal_credentials()
    return render(request, "portal/platform_admin/billing_zibal_settings.html", {
        "config": config,
        "merchant_is_configured": bool(credentials.get("merchant")),
        "active_provider_code": billing_registry.active_provider_code(),
        "active_nav": "payments",
    })


# ---------------------------------------------------------------- بسته‌های پیامک

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_packages(request):
    from apps.sms.models import SmsPackage

    package_list = SmsPackage.objects.order_by("display_order", "credit_amount")
    return render(request, "portal/platform_admin/sms_packages.html", {
        "packages": package_list, "active_nav": "sms-packages",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_package_form(request, package_id=None):
    from apps.sms.models import SmsPackage

    package = get_object_or_404(SmsPackage, pk=package_id) if package_id else None
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        credit_amount = (request.POST.get("credit_amount") or "").strip()
        price = (request.POST.get("price") or "").strip()
        display_order = (request.POST.get("display_order") or "0").strip()

        errors = []
        if not name:
            errors.append("نام بسته الزامی است.")
        if not credit_amount.isdigit() or int(credit_amount) <= 0:
            errors.append("تعدادِ اعتبار باید یک عددِ مثبت باشد.")
        if not price.replace(".", "", 1).isdigit() or float(price or 0) < 0:
            errors.append("قیمت باید عددی نامنفی باشد.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            if package is None:
                package = SmsPackage.objects.create(
                    name=name, credit_amount=int(credit_amount), price=price,
                    display_order=int(display_order) if display_order.isdigit() else 0,
                )
                action_code = "platform_admin.sms_package_created"
            else:
                package.name = name
                package.credit_amount = int(credit_amount)
                package.price = price
                package.display_order = int(display_order) if display_order.isdigit() else 0
                package.save(update_fields=["name", "credit_amount", "price", "display_order", "updated_at"])
                action_code = "platform_admin.sms_package_updated"
            record_platform_audit_event(
                actor=request.user, action_code=action_code,
                object_type="SmsPackage", object_id=package.pk, object_label=package.name,
            )
            messages.success(request, f"بسته‌ی «{package.name}» ذخیره شد.")
            return redirect("portal_platform_admin:sms-packages")

    return render(request, "portal/platform_admin/sms_package_form.html", {
        "package": package, "active_nav": "sms-packages",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_package_archive(request, package_id):
    from apps.sms.models import SmsPackage

    package = get_object_or_404(SmsPackage, pk=package_id)
    package.is_active = not package.is_active
    package.save(update_fields=["is_active", "updated_at"])
    record_platform_audit_event(
        actor=request.user,
        action_code="platform_admin.sms_package_deactivated" if not package.is_active else "platform_admin.sms_package_activated",
        object_type="SmsPackage", object_id=package.pk, object_label=package.name,
    )
    messages.success(request, f"بسته‌ی «{package.name}» {'غیرفعال' if not package.is_active else 'فعال'} شد.")
    return redirect("portal_platform_admin:sms-packages")


# ---------------------------------------------------------------- اعتبار پیامک فروشگاه‌ها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_credits(request):
    from apps.sms.models import SmsBalance

    query = (request.GET.get("q") or "").strip()
    queryset = SmsBalance.objects.select_related("store").order_by("credits")
    if query:
        queryset = queryset.filter(store__name__icontains=query)
    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/sms_credits.html", {
        "page": page, "query": query, "active_nav": "sms-credits",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_credit_adjust(request, store_public_id):
    from apps.sms.services.balance_service import InvalidAdjustmentError, adjust_credit

    store = get_object_or_404(Store, public_id=store_public_id)
    raw_delta = (request.POST.get("delta") or "").strip()
    reason = (request.POST.get("reason") or "").strip()
    note = (request.POST.get("note") or "").strip()
    try:
        delta = int(raw_delta)
    except ValueError:
        messages.error(request, "مقدارِ تغییر باید یک عددِ صحیح باشد.")
        return redirect("portal_platform_admin:sms-credits")

    try:
        adjustment = adjust_credit(store=store, delta=delta, reason=reason, note=note, actor=request.user)
        record_audit_event(
            store=store, actor=request.user, action_code="platform_admin.sms_credit_adjusted",
            object_type="SmsCreditAdjustment", object_id=adjustment.pk, object_label=store.name,
            before={"balance": adjustment.balance_before}, after={"balance": adjustment.balance_after},
            metadata={"delta": delta, "reason": reason, "note": note} if note else {"delta": delta, "reason": reason},
        )
        messages.success(request, f"اعتبارِ «{store.name}» اصلاح شد.")
    except InvalidAdjustmentError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:sms-credits")


# ---------------------------------------------------------------- گزارش ارسال پیامک

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_logs(request):
    """Legacy URL for old bookmarks."""
    query = request.GET.urlencode()
    target = reverse("portal_platform_admin:sms-messages")
    return redirect(f"{target}?{query}" if query else target)


# ---------------------------------------------------------------- صنف‌ها و قالب‌ها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def industries(request):
    from django.db.models import Count, Q

    from apps.catalog.models import IndustryTemplate
    from apps.catalog.services.industry_catalog_service import SECTOR_TABS

    q = (request.GET.get("q") or "").strip()
    sector = request.GET.get("sector") or ""
    active = request.GET.get("active") or ""
    readiness = request.GET.get("readiness") or ""

    template_list = IndustryTemplate.objects.annotate(
        installation_count=Count("installations", distinct=True),
        category_count=Count("categories", distinct=True),
        attribute_count=Count("attributes", distinct=True),
    )
    if q:
        template_list = template_list.filter(Q(name__icontains=q) | Q(slug__icontains=q))
    if sector:
        template_list = template_list.filter(sector=sector)
    if active == "active":
        template_list = template_list.filter(is_active=True)
    elif active == "inactive":
        template_list = template_list.filter(is_active=False)
    if readiness:
        template_list = template_list.filter(readiness=readiness)
    template_list = template_list.order_by("slug", "-version")

    return render(request, "portal/platform_admin/industries.html", {
        "templates": template_list, "active_nav": "industries",
        "sector_tabs": SECTOR_TABS, "readiness_choices": IndustryTemplate.Readiness.choices,
        "q": q, "selected_sector": sector, "selected_active": active, "selected_readiness": readiness,
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def industry_detail(request, template_id):
    from apps.catalog.models import IndustryTemplate

    template = get_object_or_404(
        IndustryTemplate.objects.prefetch_related("categories", "attributes"), pk=template_id,
    )
    validation_result = getattr(template, "validation_result", None)
    installations = template.installations.select_related("store").order_by("-created_at")[:50]

    if request.method == "POST" and request.POST.get("action") == "validate":
        from apps.catalog.services.template_validation_service import validate_and_persist

        result = validate_and_persist(template)
        record_platform_audit_event(
            actor=request.user, action_code="platform_admin.industry_template_validated",
            object_type="IndustryTemplate", object_id=template.pk, object_label=template.name,
            metadata={"is_valid": result.is_valid, "error_count": len(result.errors)},
        )
        if result.is_valid:
            messages.success(request, f"قالبِ «{template.name}» معتبر است.")
        else:
            messages.error(request, f"قالبِ «{template.name}» {len(result.errors)} خطای اعتبارسنجی دارد.")
        return redirect("portal_platform_admin:industry-detail", template_id)

    if request.method == "POST" and request.POST.get("action") == "toggle_active":
        template.is_active = not template.is_active
        template.save(update_fields=["is_active", "updated_at"])
        record_platform_audit_event(
            actor=request.user,
            action_code="platform_admin.industry_template_deactivated" if not template.is_active else "platform_admin.industry_template_activated",
            object_type="IndustryTemplate", object_id=template.pk, object_label=template.name,
        )
        messages.success(request, f"قالبِ «{template.name}» {'غیرفعال' if not template.is_active else 'فعال'} شد.")
        return redirect("portal_platform_admin:industry-detail", template_id)

    return render(request, "portal/platform_admin/industry_detail.html", {
        "template": template, "validation_result": validation_result, "installations": installations,
        "active_nav": "industries",
    })


# ---------------------------------------------------------------- دامنه‌ها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def domains(request):
    query = (request.GET.get("q") or "").strip()
    domain_type = (request.GET.get("domain_type") or "").strip()
    verification_status = (request.GET.get("verification_status") or "").strip()

    queryset = StoreDomain.objects.select_related("store").filter(retired_at__isnull=True).order_by("-created_at")
    if query:
        queryset = queryset.filter(Q(hostname__icontains=query) | Q(store__name__icontains=query))
    if domain_type in StoreDomain.DomainType.values:
        queryset = queryset.filter(domain_type=domain_type)
    if verification_status in StoreDomain.VerificationStatus.values:
        queryset = queryset.filter(verification_status=verification_status)

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/domains.html", {
        "page": page, "query": query, "domain_type": domain_type, "verification_status": verification_status,
        "domain_type_choices": StoreDomain.DomainType.choices,
        "verification_status_choices": StoreDomain.VerificationStatus.choices,
        "active_nav": "domains",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def domain_check(request, domain_id):
    from apps.stores.services.domain_verification_service import check_dns_verification, check_ssl_connection

    domain = get_object_or_404(StoreDomain, pk=domain_id)
    if domain.verification_status == StoreDomain.VerificationStatus.PENDING and domain.verification_token:
        try:
            verified = check_dns_verification(domain=domain, actor=request.user)
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
            return redirect("portal_platform_admin:domains")
        if verified:
            messages.success(request, f"دامنه‌ی «{domain.hostname}» با موفقیت تأیید شد.")
        else:
            messages.warning(request, f"رکوردِ DNS برایِ «{domain.hostname}» هنوز یافت نشد.")
    else:
        ssl_result = check_ssl_connection(domain.hostname)
        if ssl_result.reachable:
            messages.success(request, f"اتصالِ HTTPS به «{domain.hostname}» برقرار است.")
        else:
            messages.warning(request, f"اتصالِ HTTPS به «{domain.hostname}» ناموفق بود: {ssl_result.error}")
    return redirect("portal_platform_admin:domains")


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def domain_set_primary(request, domain_id):
    from apps.stores.services.domain_verification_service import DomainVerificationError, activate_custom_domain

    domain = get_object_or_404(StoreDomain, pk=domain_id)
    try:
        activate_custom_domain(store=domain.store, domain=domain, actor=request.user)
        messages.success(request, f"دامنه‌ی «{domain.hostname}» دامنه‌ی اصلیِ فروشگاه شد.")
    except DomainVerificationError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:domains")


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def audit_log(request):
    """تاریخچه‌ی رخدادهای حسابرسیِ سطحِ پلتفرم (Section 13) — رخدادهای
    مختصِ یک Store (مثلِ ``store.handle_claimed``) هم این‌جا ثبت می‌شوند چون
    ``record_audit_event`` جداگانه (Store-owned) است؛ این صفحه فقط
    ``PlatformAuditLogEntry`` (تنظیماتِ سراسری/پلن/دسترسیِ خودِ Platform
    Admin) را نشان می‌دهد — نگاه کنید به جزئیاتِ همان Store در
    ``store_detail`` برایِ رخدادهای Store-owned آن."""
    entries = PlatformAuditLogEntry.objects.select_related("actor").order_by("-created_at")
    action_code = (request.GET.get("action_code") or "").strip()
    result = (request.GET.get("result") or "").strip()
    if action_code:
        entries = entries.filter(action_code__icontains=action_code)
    if result in PlatformAuditLogEntry.ResultStatus.values:
        entries = entries.filter(result=result)
    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/audit_log.html", {
        "page": page, "action_code": action_code, "result": result,
        "result_choices": PlatformAuditLogEntry.ResultStatus.choices, "active_nav": "audit",
    })
