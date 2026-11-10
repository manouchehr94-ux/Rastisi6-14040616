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
from apps.core.services.client_ip import get_client_ip_bucket
from apps.stores.hostnames import build_cross_host_url
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import StoreSubscription

from apps.core.services import session_service

from .forms import OwnerLoginForm, PlatformConfigurationForm, PlatformSmsConfigForm
from .models import PlatformAuditLogEntry
from .services.platform_config_service import get_platform_configuration, record_platform_audit_event
from .services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit


def _is_platform_staff(user):
    return user.is_authenticated and user.is_staff and user.is_superuser


def sub_svc_is_financially_suspended(subscription) -> bool:
    from apps.subscriptions.services.subscription_service import is_financially_suspended

    return is_financially_suspended(subscription)


def _is_notification_team(user) -> bool:
    """Platform team member with at least one granular notification permission (NOT a superuser): may sign in to
    the platform host, but every non-notification page still requires ``_is_platform_staff``."""
    from .notification_admin_views import is_notification_team

    return bool(user.is_authenticated and not user.is_superuser and is_notification_team(user))


def login_view(request):
    if _is_platform_staff(request.user):
        return redirect("portal_platform_admin:home")
    if _is_notification_team(request.user):
        return redirect("portal_platform_admin:notification-catalog")

    if request.method == "POST":
        form = OwnerLoginForm(request.POST)
        try:
            enforce_rate_limit(
                "platform_admin_login", get_client_ip_bucket(request),
                max_attempts=10, window_seconds=600,
            )
        except RateLimitExceeded:
            form.add_error(None, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/platform_admin/login.html", {"form": form})
        except RateLimitUnavailable:
            form.add_error(None, UNAVAILABLE_MESSAGE)
            return render(request, "portal/platform_admin/login.html", {"form": form})
        if form.is_valid():
            from .services import owner_auth_service

            identifier = form.cleaned_data["identifier"]
            # Same password/identity resolver as the canonical portal login.
            # This endpoint remains on its own Platform Admin Host and STILL
            # requires both global is_staff AND is_superuser after auth.
            user = owner_auth_service.authenticate_owner_by_identifier(
                request, identifier=identifier, password=form.cleaned_data["password"],
            )
            if user is None:
                # a platform TEAM member (is_staff + a granted notification permission, no store/owner profile)
                user = owner_auth_service.authenticate_platform_team_by_identifier(
                    request, identifier=identifier, password=form.cleaned_data["password"],
                    is_team_member=_is_notification_team,
                )
            if user is not None and (_is_platform_staff(user) or _is_notification_team(user)):
                auth_login(request, user)
                session_service.apply_remember_me(request, form.cleaned_data.get("remember_me", False))
                record_platform_audit_event(
                    actor=user, action_code="platform_admin.login_succeeded",
                    object_type="User", object_id=user.pk, object_label=user.get_username(),
                )
                if not _is_platform_staff(user):
                    return redirect("portal_platform_admin:notification-catalog")
                return redirect("portal_platform_admin:home")
            record_platform_audit_event(
                actor=user, action_code="platform_admin.login_failed",
                object_type="User", object_id=user.pk if user else None,
                object_label=identifier, result="failure",
            )
            form.add_error(None, "شناسه، رمز عبور، یا دسترسی نامعتبر است")
    else:
        form = OwnerLoginForm()
    return render(request, "portal/platform_admin/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    return redirect("portal_platform_admin:login")


def permission_denied(request, exception=None):
    """``handler403`` for ``shop_core.urls_platform_admin``: the shared storefront 403 page reverses ``catalog:`` URLs
    that do not exist on the Platform Admin host, so it would crash; this one stays self-contained (like ``not_found``)."""
    return render(request, "portal/platform_admin/403.html", status=403)


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
                    samples = {
                        "customer_name": "کاربر آزمایشی", "shop_name": "فروشگاه آزمایشی", "order_code": "TEST-1", "amount": "100000",
                        "tracking_code": "TRACK-1", "discount_code": "GIFT-AB12CD34", "discount_amount": "۱۵٪",
                        "discount_expires_at": "۱۴۰۵/۰۹/۳۰", "campaign_name": "کمپین نمونه", "occasion_name": "تولد شما", "days_left": "۳",
                    }
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
    from apps.subscriptions.models import PlanVersion

    # فهرستِ نسخه‌هایِ منتشرشده برایِ «تغییرِ پلن» (به‌جایِ واردکردنِ دستیِ شناسه)
    target_versions = (PlanVersion.objects.filter(status=PlanVersion.Status.PUBLISHED, plan__is_active=True)
                       .select_related("plan").order_by("plan__display_order", "plan__code", "-version_number"))

    return render(request, "portal/platform_admin/store_detail.html", {
        "target_versions": target_versions,
        "store": store, "domains": domains, "memberships": memberships, "owner_membership": owner_membership,
        "current_subscription": current_subscription, "subscription_history": subscription_history,
        "financially_suspended": bool(current_subscription) and sub_svc_is_financially_suspended(current_subscription),
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

    if sub_svc_is_financially_suspended(subscription):
        messages.error(request, "این اشتراک در تعلیقِ مالی است؛ ابتدا با «رفعِ تعلیقِ مالی» (و ثبتِ دلیل) آن را رفع کنید.")
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
def store_reinstate_financial_suspension(request, store_public_id):
    """F-08: lift a FINANCIAL suspension (caused by a full refund of the period in force). Platform superusers only (enforced
    again in the service), reason mandatory, audited on the store and on the platform log."""
    from django.utils import timezone

    from apps.billing.services import financial_suspension_service as fss

    store = get_object_or_404(Store, public_id=store_public_id)
    subscription = store.subscriptions.filter(is_current=True).first()
    if subscription is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد.")
        return redirect("portal_platform_admin:store-detail", store_public_id)
    try:
        updated = fss.reinstate(subscription, actor=request.user, reason=request.POST.get("reason", ""))
    except fss.FinancialSuspensionError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:store-detail", store_public_id)
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.financial_suspension_reinstated", object_type="StoreSubscription",
        object_id=str(subscription.pk), object_label=store.name, metadata={"reason": (request.POST.get("reason") or "")[:300]},
    )
    if updated.current_period_end is not None and updated.current_period_end <= timezone.now():
        messages.warning(request, "تعلیق رفع شد؛ امّا پایانِ دورهٔ جاری گذشته است و اشتراک در بررسیِ بعدی وارد مهلتِ ارفاقی می‌شود. در صورتِ نیاز دورهٔ اشتراک را تمدید کنید.")
    else:
        messages.success(request, "تعلیقِ مالی رفع شد.")
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


def _apply_echo(review, echo):
    """مقدارهایِ واردشده‌یِ مالک (پس از خطا) را به ردیف‌هایِ بازبینی برمی‌گرداند؛ بدونِ echo، پیش‌فرض: قدیمی‌ها «حفظ» می‌شوند."""
    for row in review["rows"]:
        saved = (echo or {}).get("rows", {}).get(row["interval"])
        if saved is not None:
            row.update(offered=saved["offered"], discount=saved["discount"], keep_checked=saved["keep_legacy"], ack_checked=saved["ack"])
        else:
            row.setdefault("keep_checked", row["legacy"])
            row.setdefault("ack_checked", False)
    return review


def _pricing_js_config():
    """پیکربندیِ پیش‌نمایشِ زنده (فقط نمایش؛ سرور مرجع است): تعدادِ ماه‌ها و سیاستِ گرد‌کردن — همان ثابت‌هایِ ``period_pricing``."""
    import json

    from apps.subscriptions.services import period_pricing as pp

    return json.dumps({"months": pp.PERIOD_MONTHS, "rounding": "half_up_whole_toman", "max_monthly": int(pp.MAX_MONTHLY)})


def _with_enforced(entitlements, latest_version, capability_registry):
    """مارکِ ``existing/enforced`` را برایِ بازنمایی پس از خطای اعتبارسنجی دوباره می‌گذارد."""
    existing = {pe.entitlement_id: pe for pe in latest_version.plan_entitlements.all()} if latest_version else {}
    for entitlement in entitlements:
        entitlement.existing = existing.get(entitlement.pk)
        entitlement.enforced = capability_registry.is_registered(entitlement.key)
    return entitlements


def _parse_formula_pricing(post, review):
    """فرمِ قیمت‌گذاریِ ساده (یک قیمتِ ماهانه + درصدِ تخفیفِ ۳/۶/۱۲ ماهه) را **در سرور** اعتبارسنجی می‌کند. هیچ مبلغِ محاسبه‌شده‌ای
    از مرورگر پذیرفته نمی‌شود (فقط قیمتِ ماهانه و درصدها). ``(cleaned, errors, echo)`` برمی‌گرداند؛ ``cleaned`` در خطا ``None`` است."""
    from apps.subscriptions.services import period_pricing as pp

    errors, echo = [], {"monthly": (post.get("monthly_price") or "").strip(), "rows": {}}
    free = post.get("plan_kind") == "free"
    echo["free"] = free
    if free:
        return {"free": True}, errors, echo
    rows = {r["interval"]: r for r in review["rows"]}
    discounts, offered, keep_legacy = {}, [], []
    try:
        monthly = pp.validate_monthly_price(post.get("monthly_price"))
    except pp.PricingError as exc:
        errors.append(str(exc))
        monthly = None
    for interval in pp.DISCOUNTED_PERIODS:
        r = rows[interval]
        raw = (post.get(f"discount_{interval}") or "").strip()
        is_offered = post.get(f"offer_{interval}") == "on"
        keep = post.get(f"keep_legacy_{interval}") == "on" and r["legacy"]
        echo["rows"][interval] = {"discount": raw, "offered": is_offered, "keep_legacy": keep, "ack": post.get(f"ack_{interval}") == "on"}
        if keep:
            keep_legacy.append(interval)
            continue
        if not is_offered:
            continue
        try:
            discounts[interval] = pp.validate_discount(raw)
        except pp.PricingError as exc:
            errors.append(f"{r['label']}: {exc}")
            continue
        if r["legacy"] and r["needs_review"] and not echo["rows"][interval]["ack"]:
            errors.append(f"{r['label']}: تبدیلِ قیمتِ ثابتِ قدیمی به فرمول ارزشِ تجاری را عوض می‌کند؛ یا «حفظِ قیمتِ فعلی» را بزنید یا تغییر را صراحتاً تأیید کنید.")
        offered.append(interval)
    if monthly is not None and not errors:
        try:
            pp.compute_all(monthly, discounts)
        except pp.PricingError as exc:
            errors.append(str(exc))
    if errors:
        return None, errors, echo
    return {"free": False, "monthly": monthly, "discounts": discounts, "offered": offered, "keep_legacy": keep_legacy}, errors, echo


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plan_form(request, plan_id=None):
    """ساختِ پلن + نسخه‌ی پیش‌نویسِ آن، یا افزودنِ یک نسخه‌ی تازه به پلنِ
    موجود — هرگز شرایطِ یک نسخه‌ی ``published`` را ویرایش نمی‌کند (ADR-63)؛
    ویرایشِ یک پلنِ موجود همیشه یک نسخه‌ی پیش‌نویسِ تازه می‌سازد."""
    from apps.subscriptions import capability_registry
    from apps.subscriptions.models import EntitlementDefinition, Plan, PlanVersion
    from apps.subscriptions.services.plan_service import (
        PlanServiceError, clear_version_price, create_plan_version, get_or_create_draft, set_formula_pricing,
        set_plan_entitlement, set_version_price, update_draft_version,
    )
    from apps.subscriptions.services import period_pricing

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
        tagline = (request.POST.get("tagline") or "").strip()[:160]
        badge_text = (request.POST.get("badge_text") or "").strip()[:40]
        promo_label = (request.POST.get("promo_label") or "").strip()[:60]
        cta_label = (request.POST.get("cta_label") or "").strip()[:40]
        # فرم‌هایِ قدیمی/تست‌ها این فیلدها را نمی‌فرستند؛ مقدارِ فعلی حفظ می‌شود.
        marketing_submitted = "marketing_submitted" in request.POST
        # Old API/test POST payloads omit this new field; preserve their old
        # default. The new form sends the hidden submitted marker explicitly.
        is_publicly_selectable = (
            request.POST.get("is_publicly_selectable") == "on"
            if "public_selectable_submitted" in request.POST
            else (plan.is_publicly_selectable if plan else True)
        )

        formula = None
        if "pricing_formula_submitted" in request.POST:
            review = period_pricing.owner_review(latest_version)
            formula, price_errors, echo = _parse_formula_pricing(request.POST, review)
            if price_errors:
                _apply_echo(review, echo)
                for message in price_errors:
                    messages.error(request, message)
                return render(request, "portal/platform_admin/plan_form.html", {
                    "plan": plan, "entitlements": _with_enforced(entitlements, latest_version, capability_registry),
                    "latest_version": latest_version, "active_nav": "plans", "pricing": review, "pricing_echo": echo,
                    "pricing_json": _pricing_js_config(), "form_post": request.POST,
                })

        if not name or not code:
            messages.error(request, "نام و کدِ پلن الزامی است.")
            return render(request, "portal/platform_admin/plan_form.html", {
                "plan": plan, "entitlements": entitlements, "latest_version": latest_version, "active_nav": "plans",
            })

        if plan is None and Plan.objects.filter(code=code).exists():
            messages.error(request, "پلنی با این کد از قبل وجود دارد؛ برایِ تغییر آن را ویرایش کنید.")
            return render(request, "portal/platform_admin/plan_form.html", {
                "plan": plan, "entitlements": entitlements, "latest_version": latest_version, "active_nav": "plans",
                "price_rows": [], "primary_interval": "monthly",
            })

        plan_is_new = plan is None
        if plan is None:
            plan = Plan.objects.create(
                code=code, name=name, public_title=public_title, description=description,
                display_order=int(display_order) if display_order.isdigit() else 0,
                is_recommended=is_recommended,
                is_publicly_selectable=is_publicly_selectable,
                tagline=tagline, badge_text=badge_text, cta_label=cta_label, promo_label=promo_label,
            )
            action_code = "platform_admin.plan_created"
        else:
            plan.name = name
            plan.public_title = public_title
            plan.description = description
            plan.display_order = int(display_order) if display_order.isdigit() else 0
            plan.is_recommended = is_recommended
            plan.is_publicly_selectable = is_publicly_selectable
            fields = ["name", "public_title", "description", "display_order", "is_recommended", "is_publicly_selectable", "updated_at"]
            if marketing_submitted:
                plan.tagline, plan.badge_text, plan.cta_label, plan.promo_label = tagline, badge_text, cta_label, promo_label
                fields += ["tagline", "badge_text", "cta_label", "promo_label"]
            plan.save(update_fields=fields)
            action_code = "platform_admin.plan_updated"

        # قیمتِ گزینه‌ی اصلی: ``price_<دوره>`` اگر فرمِ تازه فرستاده باشد، وگرنه ``display_price`` (فرم/تستِ قدیمی).
        if formula is not None:
            billing_interval = "none" if formula["free"] else "monthly"
            display_price = "0" if formula["free"] else str(formula["monthly"])
        primary_price = (request.POST.get(f"price_{billing_interval}") or "").strip() or display_price
        trial_once = request.POST.get("trial_once_per_store", "on" if "trial_once_submitted" not in request.POST else "") == "on"
        try:
            if plan_is_new:
                version = create_plan_version(plan, display_price=primary_price or 0, trial_days=trial_days or 0,
                                              billing_interval=billing_interval, trial_once_per_store=trial_once)
            else:
                # ویرایشِ پلنِ موجود: همان پیش‌نویس در جا ویرایش می‌شود؛ اگر پیش‌نویسی نبود از آخرین نسخه کپی می‌شود (نسخه‌ی
                # منتشرشده هرگز دست نمی‌خورد و پیش‌نویسِ اضافه ساخته نمی‌شود).
                version = get_or_create_draft(plan, actor=request.user)
                version = update_draft_version(version, actor=request.user, display_price=primary_price or 0, trial_days=trial_days or 0,
                                               billing_interval=billing_interval, trial_once_per_store=trial_once)
        except PlanServiceError as exc:
            messages.error(request, str(exc))
            return redirect("portal_platform_admin:plan-edit", plan.pk) if not plan_is_new else redirect("portal_platform_admin:plans")
        prices_submitted = any(f"price_{i}" in request.POST for i in PlanVersion.PAID_INTERVALS)
        try:
            if formula is not None:
                if formula["free"]:
                    for interval in PlanVersion.PAID_INTERVALS:
                        clear_version_price(version, interval)
                else:
                    set_formula_pricing(
                        version, monthly_price=formula["monthly"], discounts=formula["discounts"], offered=formula["offered"],
                        keep_legacy=formula["keep_legacy"], actor=request.user,
                    )
                prices_submitted = False
            for interval in (PlanVersion.PAID_INTERVALS if formula is None else ()):
                raw_price = (request.POST.get(f"price_{interval}") or "").strip()
                if not raw_price:
                    if prices_submitted and interval != billing_interval:
                        clear_version_price(version, interval)
                    continue
                set_version_price(
                    version, interval, price=raw_price,
                    compare_at_price=(request.POST.get(f"compare_{interval}") or "").strip() or None,
                    label=(request.POST.get(f"label_{interval}") or "").strip(),
                )
        except PlanServiceError as exc:
            messages.error(request, f"قیمتِ دوره‌ها ذخیره نشد: {exc}")
        # فقط کلیدهایی که *در رجیستریِ کد* ثبت‌اند از این فرم قابلِ‌تنظیم‌اند؛ قابلیت‌هایِ آینده در «ماتریسِ تخصیص» مدیریت می‌شوند.
        for entitlement in entitlements:
            if not capability_registry.is_registered(entitlement.key):
                continue
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
                # نه «نامحدود» و نه مقداری وارد شده — بدونِ تغییر می‌ماند.

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
        entitlement.enforced = capability_registry.is_registered(entitlement.key)
    price_rows = []   # (قدیمی) فقط برایِ سازگاری با قالب‌هایِ قدیمی؛ فرمِ تازه از ``pricing`` استفاده می‌کند
    options = latest_version.price_options() if latest_version else {}
    primary = latest_version.billing_interval if latest_version else "monthly"
    for interval in PlanVersion.PAID_INTERVALS:
        opt = options.get(interval) or {}
        price_rows.append({
            "interval": interval, "label": dict(PlanVersion.BillingInterval.choices)[interval],
            "price": opt.get("price", ""), "compare_at": opt.get("compare_at") or "", "custom_label": opt.get("label", ""),
            "is_primary": interval == primary,
        })
    return render(request, "portal/platform_admin/plan_form.html", {
        "plan": plan, "entitlements": entitlements, "latest_version": latest_version, "active_nav": "plans",
        "price_rows": price_rows, "primary_interval": primary,
        "pricing": _apply_echo(period_pricing.owner_review(latest_version), None), "pricing_echo": None, "pricing_json": _pricing_js_config(),
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def plan_archive(request, plan_id):
    """بایگانی/بازگردانیِ پلن. بایگانی حتی برایِ پلنِ دارایِ مشترک مجاز است: فقط فروشِ تازه/نمایشِ عمومی بسته می‌شود و
    اشتراک‌ها، تمدیدها و دسترسیِ مشترکانِ فعلی دست‌نخورده می‌ماند."""
    from apps.subscriptions.models import Plan
    from apps.subscriptions.services.plan_service import PlanServiceError, set_plan_archived

    plan = get_object_or_404(Plan, pk=plan_id)
    try:
        updated = set_plan_archived(plan, archived=plan.is_active, actor=request.user)
    except PlanServiceError as exc:
        messages.error(request, str(exc))
        return redirect("portal_platform_admin:plans")
    messages.success(request, f"پلن «{updated.name}» {'بایگانی شد؛ مشترکانِ فعلی بدونِ تغییر ادامه می‌دهند' if not updated.is_active else 'دوباره فعال شد'}.")
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


# ---------------------------------------------------------------- محتوایِ صفحه‌ی تعرفه

_PRICING_TABS = ("rows", "faq", "services", "gap")


def _pricing_content_redirect(request):
    """بازگشت به همان تبِ صفحه‌یِ محتوایِ تعرفه پس از ذخیره (تب از نوعِ عمل مشتق می‌شود)."""
    from django.urls import reverse

    action = request.POST.get("action", "")
    tab = "faq" if action.startswith("faq") else "services" if action.startswith("service") else "rows"
    return redirect(f"{reverse('portal_platform_admin:pricing-content')}?tab={tab}")


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def pricing_content(request):
    """مدیریتِ متنِ نمایشیِ ماتریس، پرسش‌هایِ متداول و خدماتِ اختیاری. ساختارِ ردیف‌ها (دسته/اتصال/وضعیتِ پیاده‌سازی)
    از کد می‌آید و اینجا قابلِ‌ویرایش نیست؛ فقط عنوان/توضیح/ترتیب/نمایش. ردیفِ «پیاده نشده» هرگز عمومی نمی‌شود."""
    from apps.subscriptions.feature_catalog import BY_KEY, sync_feature_catalog
    from apps.subscriptions.models import OptionalService, Plan, PlanFaq, PlanOptionalService, PricingFeature
    from apps.subscriptions.services.pricing_page_service import gap_report

    sync_feature_catalog()
    plans_all = list(Plan.objects.filter(is_active=True).order_by("display_order", "code"))

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "feature":
            feature = get_object_or_404(PricingFeature, pk=request.POST.get("id"))
            feature.title = (request.POST.get("title") or feature.title).strip()[:140]
            feature.description = (request.POST.get("description") or "").strip()
            feature.display_order = int(request.POST["display_order"]) if (request.POST.get("display_order") or "").isdigit() else feature.display_order
            feature.is_visible = request.POST.get("is_visible") == "on" and feature.is_publishable
            feature.save()
            obj_label = feature.key
        elif action == "faq_save":
            faq = PlanFaq.objects.filter(pk=request.POST.get("id")).first() or PlanFaq()
            question, answer = (request.POST.get("question") or "").strip(), (request.POST.get("answer") or "").strip()
            if not question or not answer:
                messages.error(request, "پرسش و پاسخ الزامی است.")
                return _pricing_content_redirect(request)
            faq.question, faq.answer = question[:240], answer
            faq.plan = Plan.objects.filter(pk=request.POST.get("plan")).first() if request.POST.get("plan") else None
            faq.display_order = int(request.POST["display_order"]) if (request.POST.get("display_order") or "").isdigit() else 0
            faq.is_published = request.POST.get("is_published") == "on"
            faq.save()
            obj_label = f"faq:{faq.pk}"
        elif action == "faq_delete":
            PlanFaq.objects.filter(pk=request.POST.get("id")).delete()
            obj_label = "faq_delete"
        elif action == "service_save":
            service = OptionalService.objects.filter(pk=request.POST.get("id")).first() or OptionalService()
            title = (request.POST.get("title") or "").strip()
            code = (request.POST.get("code") or service.code or "").strip()
            if not title or not code:
                messages.error(request, "کد و عنوانِ خدمت الزامی است.")
                return _pricing_content_redirect(request)
            service.code, service.title = code[:50], title[:140]
            service.description = (request.POST.get("description") or "").strip()
            raw_price = (request.POST.get("price") or "").strip().replace(",", "")
            service.price = int(raw_price) if raw_price.isdigit() else None
            service.price_note = (request.POST.get("price_note") or "").strip()[:80]
            service.display_order = int(request.POST["display_order"]) if (request.POST.get("display_order") or "").isdigit() else 0
            service.is_active = request.POST.get("is_active") == "on"
            service.save()
            for plan in plans_all:
                mode = request.POST.get(f"mode_{plan.pk}", PlanOptionalService.Mode.UNAVAILABLE)
                if mode in PlanOptionalService.Mode.values:
                    PlanOptionalService.objects.update_or_create(plan=plan, service=service, defaults={"mode": mode})
            obj_label = f"service:{service.code}"
        else:
            messages.error(request, "عملیاتِ نامعتبر.")
            return _pricing_content_redirect(request)
        record_platform_audit_event(
            actor=request.user, action_code=f"platform_admin.pricing_content_{action}", object_type="PricingContent",
            object_id=0, object_label=obj_label,
        )
        messages.success(request, "ذخیره شد.")
        return _pricing_content_redirect(request)

    features = list(PricingFeature.objects.select_related("entitlement").order_by("category", "display_order", "key"))
    for f in features:
        spec = BY_KEY.get(f.key)
        f.control = "پیاده نشده" if not f.is_publishable else ("قابلِ کنترل در پلن" if spec and spec.entitlement else "همراهِ همه‌ی پلن‌ها")
    services = list(OptionalService.objects.order_by("display_order", "code"))
    modes = {(m.service_id, m.plan_id): m.mode for m in PlanOptionalService.objects.all()}
    for service in services:
        service.rows = [(plan, modes.get((service.pk, plan.pk), "unavailable")) for plan in plans_all]
    tab = request.GET.get("tab") if request.GET.get("tab") in _PRICING_TABS else "rows"
    return render(request, "portal/platform_admin/pricing_content.html", {
        "tab": tab,
        "features": features, "faqs": PlanFaq.objects.select_related("plan").order_by("display_order", "id"),
        "services": services, "plans_all": plans_all, "gap": gap_report(), "active_nav": "plans",
        "modes": PlanOptionalService.Mode.choices,
    })


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
    if sub_svc_is_financially_suspended(subscription):
        messages.error(request, "این اشتراک در تعلیقِ مالی است؛ فقط با «رفعِ تعلیقِ مالی» در صفحهٔ فروشگاه (با ثبتِ دلیل) رفع می‌شود.")
        return redirect("portal_platform_admin:subscriptions")
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
    import secrets

    return render(request, "portal/platform_admin/payment_invoice_detail.html", {
        "invoice": invoice, "active_nav": "payments",
        "refund_form_key": f"refund-{invoice.pk}-{secrets.token_hex(8)}",    # one per render: a double submit hits the same key
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
    """مسیرِ قدیمیِ زیبال (فقط برایِ لینک/نشانک‌هایِ قدیمی). **هیچ چیزی نمی‌نویسد**: منبعِ یگانه‌یِ پیکربندیِ
    همه‌یِ درگاه‌هایِ پلتفرم «درگاه‌هایِ پرداختِ پلتفرم» است. دسترسیِ کارمندِ پلتفرم پیش از ریدایرکت بررسی می‌شود
    (کاربرِ غیرمجاز به لاگین می‌رود، نه به صفحه‌یِ درگاه‌ها)؛ POST هم بدونِ اثر ریدایرکت می‌شود."""
    if request.method == "POST":
        messages.info(request, "تنظیمِ زیبال به «درگاه‌هایِ پرداختِ پلتفرم» منتقل شده است؛ تغییرِ شما اعمال نشد.")
    return redirect(reverse("portal_platform_admin:payment-gateways") + "#gw-zibal")


# ------------------------------------------------- درگاه‌های پرداختِ پلتفرم (مدیریت یکپارچه)

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_gateways(request):
    """Platform Admin → درگاه‌های پرداخت: پیکربندی، فعال/غیرفعال‌سازی، آمادگی و خطاهای قابلِ‌اقدام.

    اعتبارنامه‌ها فقط نوشته می‌شوند (خالی = بدون تغییر) و هرگز در HTML/پاسخ برنمی‌گردند. فقط
    درگاه‌های تأییدشده قابلِ پیکربندی‌اند؛ بقیه فقط‌خواندنی با دلیل."""
    from apps.portal.services import platform_gateway_service as pgs

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        code = (request.POST.get("gateway_code") or "").strip()
        try:
            if action == "save":
                adapter_fields = [f["name"] for f in pgs.gateway_state(code).fields]
                types = None
                if "ptypes_submitted" in request.POST:
                    types = [t for t in pgs.PURCHASE_TYPES if f"ptype_{t}" in request.POST]
                pgs.save_gateway(
                    code, credentials={n: request.POST.get(f"cred_{n}", "") for n in adapter_fields},
                    sandbox="sandbox_mode" in request.POST, enabled="is_enabled" in request.POST,
                    actor=request.user, display_order=request.POST.get("display_order") or None, purchase_types=types,
                )
                state = pgs.gateway_state(code)
                if state.enabled and not state.ready:
                    messages.warning(request, f"ذخیره شد؛ امّا «آماده» نیست: {state.status_label} — {state.status_detail}")
                else:
                    messages.success(request, "تنظیماتِ روش ذخیره شد.")
            elif action in ("attest", "revoke_gate"):
                gate = (request.POST.get("gate") or "").strip()
                pgs.record_attestation(
                    code, gate, reference=request.POST.get("reference", ""), actor=request.user,
                    purchase_types=[t for t in pgs.PURCHASE_TYPES if f"atype_{t}" in request.POST], revoke=(action == "revoke_gate"),
                )
                messages.success(request, "گواهیِ گیت ثبت شد." if action == "attest" else "گواهیِ گیت باطل شد.")
            elif action == "set_default":
                pgs.set_default(code, actor=request.user)
                messages.success(request, "درگاهِ پیش‌فرض تغییر کرد.")
            elif action == "test":
                from apps.portal.services.platform_gateway_service import callback_base_url

                result = pgs.run_connection_test(code, callback_base=callback_base_url(request), actor=request.user)
                (messages.success if result.ok else messages.error)(request, f"تستِ پیکربندی: {result.message}")
            else:
                messages.error(request, "عملیاتِ نامعتبر.")
        except (pgs.PlatformGatewayError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("portal_platform_admin:payment-gateways")

    config = get_platform_configuration()
    states = pgs.catalog()
    return render(request, "portal/platform_admin/payment_gateways.html", {
        "states": states, "default_code": config.default_payment_provider,
        "effective_default": pgs.default_code(),
        "default_choices": [{"code": s.code, "label": s.label, "ready": s.ready, "status_label": s.status_label}
                            for s in states if s.eligible and s.kind == "online"],
        "purchase_labels": pgs.matrix.PURCHASE_LABELS,
        "pending_claims": _pending_claims_count(),
        "summary": {"ready": sum(1 for s in states if s.ready), "total": len(states)},
        "audit": pgs.audit_trail(15), "active_nav": "payment-gateways",
    })


def _pending_claims_count() -> int:
    from apps.billing.models import PlatformManualPaymentClaim

    return PlatformManualPaymentClaim.objects.filter(status=PlatformManualPaymentClaim.Status.PENDING_REVIEW).count()


def _attempt_row_order(row):
    """The ONE total order of the transactions list, newest first: ``created_at`` desc, then subscription before SMS, then ``pk`` desc.

    Explicit (not an accident of list concatenation) so rows that share a timestamp — common for rows written in one transaction/bulk — keep a
    stable position across page requests. It is consistent with each part's own queryset order (``-created_at, -pk``), which is what makes the
    "read at most ``stop`` rows per part" over-fetch in ``_MergedAttemptRows`` exact: the merged order restricted to one part IS that part's order."""
    return (row["created_at"], row["kind"] == "subscription", row["attempt"].pk)


class _MergedAttemptRows:
    """Newest-first merge of several attempt querysets, usable by ``Paginator`` (``len`` + slicing) without loading the whole history.

    Each part is ``(queryset ordered by -created_at, row_builder)``. ``len`` is the sum of COUNTs; a slice ``[a:b]`` reads at most ``b`` rows from every part
    and merges them, so page N costs O(N x page_size) rows — never an arbitrary cut-off that would hide older financial records."""

    def __init__(self, parts):
        self._parts = parts

    def __len__(self):
        return sum(qs.count() for qs, _build in self._parts)

    def __getitem__(self, item):
        if not isinstance(item, slice):
            raise TypeError("only slicing is supported")
        start, stop = item.start or 0, item.stop
        rows = []
        for qs, build in self._parts:
            rows.extend(build(a) for a in (qs[:stop] if stop is not None else qs))
        rows.sort(key=_attempt_row_order, reverse=True)
        return rows[start:stop]


def _attempt_rows(*, kind="", status="", provider="", query=""):
    from apps.billing.models import SubscriptionPaymentAttempt
    from apps.sms.models import SmsPackagePaymentAttempt

    parts = []
    if kind in ("", "subscription"):
        qs = SubscriptionPaymentAttempt.objects.select_related("store", "invoice").order_by("-created_at", "-pk")
        if status:
            qs = qs.filter(status=status)
        if provider:
            qs = qs.filter(provider=provider)
        if query:
            qs = qs.filter(Q(store__name__icontains=query) | Q(invoice__number__icontains=query) | Q(public_token__icontains=query))
        parts.append((qs, lambda a: {"kind": "subscription", "kind_label": "اشتراک", "attempt": a, "ref": a.invoice.number,
                                     "store": a.store, "created_at": a.created_at}))
    if kind in ("", "sms"):
        qs = SmsPackagePaymentAttempt.objects.select_related("store", "purchase__package").order_by("-created_at", "-pk")
        if status:
            qs = qs.filter(status=status)
        if provider:
            qs = qs.filter(provider=provider)
        if query:
            qs = qs.filter(Q(store__name__icontains=query) | Q(public_token__icontains=query))
        parts.append((qs, lambda a: {"kind": "sms", "kind_label": "بسته پیامک", "attempt": a, "ref": f"SMS-{a.purchase_id}",
                                     "store": a.store, "created_at": a.created_at}))
    return _MergedAttemptRows(parts)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_transactions(request):
    """همهٔ تراکنش‌های پلتفرم (اشتراک + بستهٔ پیامک): موفق، ناموفق، در انتظار، نیازمندِ اقدام. فقط‌خواندنی."""
    kind = (request.GET.get("kind") or "").strip()
    status = (request.GET.get("status") or "").strip()
    provider = (request.GET.get("provider") or "").strip()
    query = (request.GET.get("q") or "").strip()
    rows = _attempt_rows(kind=kind if kind in ("subscription", "sms") else "", status=status, provider=provider, query=query)
    page = Paginator(rows, 25).get_page(request.GET.get("page"))
    from apps.billing.models import SubscriptionPaymentAttempt

    return render(request, "portal/platform_admin/payment_transactions.html", {
        "page": page, "kind": kind, "status": status, "provider": provider, "query": query,
        "status_choices": SubscriptionPaymentAttempt.Status.choices, "active_nav": "payment-transactions",
    })


STALE_PENDING_MINUTES = 15


def reconciliation_snapshot():
    """فهرست‌های تطبیق: پرداخت‌هایِ نیازمندِ اقدام، در انتظارِ کهنه، موفقِ بدونِ اثر، رخدادهایِ ناموفق، خریدهایِ
    پیامکِ بدونِ ردیفِ دفتر و بازپرداخت‌هایِ باز."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.billing.models import (
        BillingWebhookEvent, PlatformManualPaymentClaim, SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund,
    )
    from apps.billing.providers.registry import MANUAL_PROVIDER_CODES
    from apps.sms.models import SmsCreditLedger, SmsPackagePaymentAttempt, SmsPackagePurchase

    now = timezone.now()
    cutoff = now - timedelta(minutes=STALE_PENDING_MINUTES)
    manual = list(MANUAL_PROVIDER_CODES)
    sub_s, sms_s = SubscriptionPaymentAttempt.Status, SmsPackagePaymentAttempt.Status
    from apps.billing.services import duplicate_payment_service as dups

    def _open_requires_action(model, related):
        rows = list(model.objects.filter(status=model.Status.REQUIRES_ACTION).select_related("store", related)[:200])
        for row in rows:                                     # فقط برایِ نمایش: «پرداختِ تکراری» و نتیجه‌ی ثبت‌شده
            row.is_duplicate = dups.is_duplicate(row)
            row.resolution = dups.resolution_of(row)
            row.resolved = dups.is_resolved(row)
        return rows

    sub_ra, sms_ra = _open_requires_action(SubscriptionPaymentAttempt, "invoice"), _open_requires_action(SmsPackagePaymentAttempt, "purchase")
    return {
        "requires_action": ([r for r in sub_ra if not r.resolved][:100], [r for r in sms_ra if not r.resolved][:100]),
        "duplicates_resolved": ([r for r in sub_ra if r.resolved][:50], [r for r in sms_ra if r.resolved][:50]),
        "stale_pending": (
            list(SubscriptionPaymentAttempt.objects.filter(status__in=(sub_s.CREATED, sub_s.PENDING), created_at__lt=cutoff)
                 .exclude(provider_session_id="").exclude(provider__in=manual).select_related("store", "invoice")[:100]),
            list(SmsPackagePaymentAttempt.objects.filter(status__in=(sms_s.CREATED, sms_s.PENDING), created_at__lt=cutoff)
                 .exclude(provider_session_id="").exclude(provider__in=manual).select_related("store", "purchase")[:100]),
        ),
        # پرداخت‌هایی که verify شده‌اند امّا settle هنوز تأیید نشده (BNPL/ملت): پول نزدِ درگاه است، اثر هنوز اعمال نشده
        "verified_unsettled": (
            list(SubscriptionPaymentAttempt.objects.filter(status__in=(sub_s.CREATED, sub_s.PENDING), provider_extra__verified=True)
                 .select_related("store", "invoice")[:100]),
            list(SmsPackagePaymentAttempt.objects.filter(status__in=(sms_s.CREATED, sms_s.PENDING), provider_extra__verified=True)
                 .select_related("store", "purchase")[:100]),
        ),
        "manual_claims": {
            "pending": PlatformManualPaymentClaim.objects.filter(status=PlatformManualPaymentClaim.Status.PENDING_REVIEW).count(),
            "overdue": PlatformManualPaymentClaim.objects.filter(
                status=PlatformManualPaymentClaim.Status.PENDING_REVIEW, created_at__lt=now - timedelta(hours=24)).count(),
            "needs_action": list(PlatformManualPaymentClaim.objects.filter(status=PlatformManualPaymentClaim.Status.NEEDS_ACTION)
                                 .select_related("store", "invoice", "sms_purchase")[:50]),
        },
        "paid_without_effect": (
            list(SubscriptionPaymentAttempt.objects.filter(status=sub_s.SUCCEEDED)
                 .exclude(invoice__status__in=(SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.REFUNDED,
                                               SubscriptionInvoice.Status.PARTIALLY_REFUNDED)).select_related("store", "invoice")[:100]),
            list(SmsPackagePaymentAttempt.objects.filter(status=sms_s.SUCCEEDED)
                 .exclude(purchase__status__in=(SmsPackagePurchase.Status.COMPLETED, SmsPackagePurchase.Status.REFUNDED))
                 .select_related("store", "purchase")[:100]),
        ),
        "sms_completed_without_ledger": list(
            SmsPackagePurchase.objects.filter(status=SmsPackagePurchase.Status.COMPLETED, payment_attempts__status=sms_s.SUCCEEDED)
            .exclude(ledger_entries__kind=SmsCreditLedger.Kind.PURCHASE).select_related("store", "package").distinct()[:100]
        ),
        # FAILED events, plus RECEIVED events that have been stuck for more than 15 minutes (a crashed worker leaves them
        # `received`; they used to be invisible to staff) (F-16).
        "failed_webhooks": list(BillingWebhookEvent.objects.filter(
            Q(processing_status=BillingWebhookEvent.ProcessingStatus.FAILED)
            | Q(processing_status=BillingWebhookEvent.ProcessingStatus.RECEIVED, created_at__lt=now - timedelta(minutes=15))
        ).order_by("created_at")[:50]),
        "open_refunds": list(SubscriptionRefund.objects.filter(status__in=SubscriptionRefund.OPEN_STATUSES).select_related("store", "invoice")[:50]),
    }


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_reconciliation(request):
    snapshot = reconciliation_snapshot()
    totals = {
        "requires_action": sum(len(x) for x in snapshot["requires_action"]),
        "stale_pending": sum(len(x) for x in snapshot["stale_pending"]),
        "paid_without_effect": sum(len(x) for x in snapshot["paid_without_effect"]),
        "verified_unsettled": sum(len(x) for x in snapshot["verified_unsettled"]),
        "claims_needs_action": len(snapshot["manual_claims"]["needs_action"]),
    }
    return render(request, "portal/platform_admin/payment_reconciliation.html", {
        "snapshot": snapshot, "totals": totals, "stale_minutes": STALE_PENDING_MINUTES,
        "active_nav": "payment-reconciliation",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_verify_now(request, kind, attempt_id):
    """بررسیِ دستیِ یک تلاش با verify سرور-به-سرور (همان مسیرِ بازگشت). هیچ موفقیتِ دستی/جعلی نمی‌سازد."""
    from apps.billing.models import SubscriptionPaymentAttempt
    from apps.billing.providers.base import BillingProviderError
    from apps.billing.services import payment_flow_service, sms_purchase_payment_service
    from apps.billing.services.confirmation_service import ConfirmationError
    from apps.sms.models import SmsPackagePaymentAttempt

    try:
        if kind == "sms":
            attempt = get_object_or_404(SmsPackagePaymentAttempt, pk=attempt_id)
            result = sms_purchase_payment_service.verify_and_fulfill(attempt, actor=request.user)
        else:
            attempt = get_object_or_404(SubscriptionPaymentAttempt, pk=attempt_id)
            result = payment_flow_service.confirm_from_provider_verification(attempt, actor=request.user)
    except (BillingProviderError, ConfirmationError, sms_purchase_payment_service.SmsPaymentConfirmationError) as exc:
        messages.error(request, f"بررسی ناموفق بود ({getattr(exc, 'code', '') or type(exc).__name__}).")
    else:
        messages.success(request, f"وضعیتِ تلاش پس از بررسی: {result.get_status_display()}")
    record_platform_audit_event(
        actor=request.user, action_code="platform_payment.verify_now", object_type=f"{kind}_attempt", object_id=attempt_id,
    )
    return redirect(request.POST.get("next") if (request.POST.get("next") or "").startswith("/") and not (request.POST.get("next") or "").startswith("//") else reverse("portal_platform_admin:payment-reconciliation"))


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_duplicate_action(request, kind, attempt_id, action):
    """پرداختِ تکراری (دو تلاش هر دو تسویه شدند): بازپرداخت از همان درگاه یا ثبتِ تسویه‌ی بیرونی. فقط مدیرِ مالیِ مجاز
    (همان گیتِ تأییدِ کارت‌به‌کارت)؛ هیچ اثری رویِ فاکتور/خریدِ اعمال‌شده ندارد و idempotent است."""
    from django.http import Http404, HttpResponseForbidden

    from apps.billing.services import duplicate_payment_service as dups
    from apps.billing.services import manual_card_service as mcs

    if kind not in ("subscription", "sms") or action not in ("refund", "resolve"):
        raise Http404
    if not mcs.can_review(request.user):
        return HttpResponseForbidden("دسترسیِ مدیرِ مالی لازم است.")
    try:
        if action == "refund":
            _attempt, outcome = dups.refund_duplicate(kind, attempt_id, actor=request.user, reason=request.POST.get("reason", ""))
            messages.success(request, "بازپرداخت از درگاه انجام شد." if outcome == "refunded" else
                             "درخواستِ بازپرداخت ثبت شد؛ درگاه بازپرداختِ خودکار ندارد — پس از انجامِ دستی «ثبتِ تسویه‌ی بیرونی» را بزنید.")
        else:
            dups.mark_resolved(kind, attempt_id, actor=request.user, outcome=request.POST.get("outcome", ""),
                               reference=request.POST.get("reference", ""), note=request.POST.get("note", ""))
            messages.success(request, "تسویه‌ی پرداختِ تکراری ثبت شد.")
    except dups.DuplicatePaymentError as exc:
        messages.error(request, str(exc))
    except dups.attempt_model(kind).DoesNotExist:
        raise Http404
    record_platform_audit_event(
        actor=request.user, action_code=f"platform_payment.duplicate_{action}", object_type=f"{kind}_attempt", object_id=attempt_id,
    )
    return redirect("portal_platform_admin:payment-reconciliation")


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_purchases(request):
    """خریدهای بستهٔ پیامک با اقدام‌های مالیِ ایمن: تکمیلِ دستی، لغو، بازپرداخت (با دفترِ اعتبار)."""
    from apps.billing.services import sms_purchase_payment_service
    from apps.sms.models import SmsPackagePurchase

    status = (request.GET.get("status") or "").strip()
    qs = SmsPackagePurchase.objects.select_related("store", "package").prefetch_related("payment_attempts", "ledger_entries")
    if status in SmsPackagePurchase.Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by("-created_at"), 25).get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/sms_purchases.html", {
        "page": page, "status": status, "status_choices": SmsPackagePurchase.Status.choices, "active_nav": "sms-purchases",
        "sms_refund_enabled": sms_purchase_payment_service.sms_refunds_enabled(),
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def sms_purchase_action(request, purchase_id, action):
    from apps.billing.services import sms_purchase_payment_service as svc
    from apps.sms.models import SmsPackagePurchase
    from apps.sms.services import balance_service

    purchase = get_object_or_404(SmsPackagePurchase, pk=purchase_id)
    try:
        if action == "complete":
            balance_service.complete_purchase(purchase=purchase, actor=request.user)
            messages.success(request, "خرید تکمیل و اعتبار افزوده شد.")
        elif action == "cancel":
            balance_service.cancel_purchase(purchase=purchase)
            messages.success(request, "خرید لغو شد.")
        elif action == "refund":
            svc.ensure_refunds_enabled()                 # disabled -> controlled error; refund_purchase re-checks (defence in depth)
            svc.refund_purchase(purchase, actor=request.user, reason=(request.POST.get("reason") or "").strip())
            messages.success(request, "بازپرداخت ثبت شد؛ اعتبار برگردانده شد (بازپرداختِ پول طبقِ وضعیتِ درگاه).")
        else:
            messages.error(request, "عملیاتِ نامعتبر.")
            return redirect("portal_platform_admin:sms-purchases")
    except (balance_service.PurchaseNotPendingError, svc.SmsRefundError) as exc:
        messages.error(request, str(exc))
    else:
        record_platform_audit_event(
            actor=request.user, action_code=f"platform_sms_purchase.{action}", object_type="SmsPackagePurchase",
            object_id=purchase.pk, object_label=str(purchase.pk),
        )
    return redirect("portal_platform_admin:sms-purchases")


# ------------------------------------------------- کارت‌به‌کارتِ پلتفرم: بررسیِ مالیِ ادعاها

@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def manual_claims(request):
    """صفِ ادعاهایِ پرداختِ کارت‌به‌کارت. رسید مدرکِ پرداخت نیست؛ تأیید فقط با صورتحسابِ بانکیِ مستقل."""
    from apps.billing.models import PlatformManualPaymentClaim
    from apps.billing.services import manual_card_service as mcs

    status = (request.GET.get("status") or "pending_review").strip()
    qs = PlatformManualPaymentClaim.objects.select_related("store", "invoice", "sms_purchase__package", "submitted_by", "reviewed_by")
    if status in PlatformManualPaymentClaim.Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by("created_at" if status == "pending_review" else "-created_at"), 25).get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/manual_claims.html", {
        "page": page, "status": status, "status_choices": PlatformManualPaymentClaim.Status.choices,
        "can_review": mcs.can_review(request.user), "active_nav": "manual-claims",
    })


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def manual_claim_detail(request, claim_id):
    from apps.billing.models import PlatformManualPaymentClaim
    from apps.billing.services import manual_card_service as mcs

    claim = get_object_or_404(
        PlatformManualPaymentClaim.objects.select_related("store", "invoice", "sms_purchase__package", "submitted_by", "reviewed_by"),
        pk=claim_id,
    )
    same_ref = PlatformManualPaymentClaim.objects.filter(reference_key=claim.reference_key).exclude(pk=claim.pk).count()
    store_claims = PlatformManualPaymentClaim.objects.filter(store=claim.store).exclude(pk=claim.pk)
    return render(request, "portal/platform_admin/manual_claim_detail.html", {
        "claim": claim, "events": mcs.history(claim), "can_review": mcs.can_review(request.user),
        "is_self": claim.submitted_by_id == request.user.pk, "same_reference_elsewhere": same_ref,
        "store_rejected": store_claims.filter(status="rejected").count(), "store_total": store_claims.count(),
        "active_nav": "manual-claims",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def manual_claim_action(request, claim_id, action):
    from apps.billing.models import PlatformManualPaymentClaim
    from apps.billing.services import manual_card_service as mcs

    claim = get_object_or_404(PlatformManualPaymentClaim, pk=claim_id)
    try:
        if action == "approve":
            mcs.approve_claim(
                claim, reviewer=request.user, bank_confirmation_reference=request.POST.get("bank_reference", ""),
                confirmed_amount=request.POST.get("confirmed_amount", ""), note=(request.POST.get("note") or "").strip(),
            )
            messages.success(request, "پرداخت تأیید و (دقیقاً یک‌بار) اعمال شد.")
        elif action == "reject":
            mcs.reject_claim(claim, reviewer=request.user, reason=request.POST.get("reason", ""))
            messages.success(request, "ادعا رد شد؛ مالک می‌تواند ادعای اصلاح‌شده ثبت کند.")
        else:
            messages.error(request, "عملیاتِ نامعتبر.")
    except mcs.ClaimError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:manual-claim-detail", claim_id=claim.pk)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def manual_claim_receipt(request, claim_id):
    """رسیدِ ادعا از ذخیره‌سازیِ خصوصی؛ فقط مدیرِ پلتفرمِ احرازشده؛ هرگز لینکِ عمومی/قابلِ‌حدس."""
    from django.http import FileResponse, Http404

    from apps.billing.models import PlatformManualPaymentClaim

    claim = get_object_or_404(PlatformManualPaymentClaim, pk=claim_id)
    if not claim.receipt:
        raise Http404
    response = FileResponse(claim.receipt.open("rb"), content_type=claim.receipt_content_type or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = "inline; filename=receipt"
    return response


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_invoice_refund(request, invoice_id):
    """بازپرداختِ فاکتور از مسیرِ کانونیکِ ``refund_service`` (مبلغِ قابلِ‌بازپرداخت، idempotent، حسابرسی‌شده). Providerهایِ
    بدونِ API بازپرداخت «در انتظارِ پردازشِ دستی» می‌مانند تا مدیر پس از انتقالِ واقعیِ پول آن را تکمیل کند."""
    import hashlib
    from decimal import Decimal, InvalidOperation

    from apps.billing.models import SubscriptionInvoice
    from apps.billing.services import refund_service

    invoice = get_object_or_404(SubscriptionInvoice, pk=invoice_id)
    try:
        amount = Decimal((request.POST.get("amount") or "").strip())
        reason = (request.POST.get("reason") or "").strip()
        key = (request.POST.get("idempotency_key") or "").strip()[:100]
        if not key:
            # No form token (script/old page): derive a key from the request and the number of refunds already on the invoice,
            # so two simultaneous identical submissions collapse into one refund while a later, deliberate one is still allowed.
            digest = hashlib.sha256(
                f"{invoice.pk}|{amount}|{reason}|{request.user.pk}|{invoice.refunds.count()}".encode("utf-8")).hexdigest()[:32]
            key = f"refund-{invoice.pk}-{digest}"
        refund = refund_service.request_refund(
            invoice, amount=amount, reason=reason, requested_by=request.user, idempotency_key=key,
        )
        if refund.failure_code == refund_service.UNKNOWN_OUTCOME:
            messages.warning(request, "نتیجهٔ بازپرداخت نزد درگاه نامشخص است؛ دوباره درخواست نکنید و با بانک تطبیق دهید.")
        else:
            messages.success(request, f"بازپرداخت ثبت شد ({refund.get_status_display()}).")
    except (InvalidOperation, ValueError):
        messages.error(request, "مبلغِ بازپرداخت معتبر نیست.")
    except refund_service.RefundError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:payment-invoice-detail", invoice_id=invoice.pk)


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def payment_refund_complete(request, refund_id):
    from apps.billing.models import SubscriptionRefund
    from apps.billing.services import refund_service

    refund = get_object_or_404(SubscriptionRefund, pk=refund_id)
    try:
        if request.POST.get("resolution") == "not_executed":
            refund_service.fail_refund_manually(
                refund, actor=request.user, reference=request.POST.get("reference", ""), note=request.POST.get("note", ""))
            messages.success(request, "عدمِ انجامِ بازپرداخت ثبت شد؛ مبلغ آزاد شد.")
        else:
            refund_service.complete_refund_manually(refund, actor=request.user, reference=request.POST.get("reference", ""))
            messages.success(request, "بازپرداخت پس از پردازشِ دستی تکمیل ثبت شد.")
    except refund_service.RefundError as exc:
        messages.error(request, str(exc))
    return redirect("portal_platform_admin:payment-invoice-detail", invoice_id=refund.invoice_id)


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
