from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
import logging
import time
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.password_validation import password_validators_help_texts
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from django.conf import settings

from apps.catalog.models import IndustryTemplate
from apps.catalog.services import industry_catalog_service, template_summary_service
from apps.storefront_builder.services import ready_template_card_service, store_template_service
from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service
from apps.billing.services import plan_change_billing_service
from apps.stores.hostnames import build_cross_host_url
from apps.stores.models import Store, StoreDomain, StoreMembership, StoreOwnershipTransfer
from apps.stores.services import deletion_service, domain_verification_service, handle_service, ownership_transfer_service, publication_service
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service

from apps.stores.authorization import (
    BILLING_PAYMENT_MANAGE,
    DOMAIN_MANAGE,
    SETTINGS_MANAGE,
    STAFF_MANAGE,
    STORE_DELETE,
    SUBSCRIPTION_CHANGE,
)

from .decorators import (
    owner_required,
    portal_action_allowed,
    portal_actions_allowed,
    portal_permission_denied,
)
from .forms import (
    ContactForm,
    CreateStoreForm,
    OnboardingBrandingForm,
    OnboardingIdentityForm,
    OnboardingIndustryForm,
    OwnerIdentifierLoginForm,
    OwnerOtpVerifyForm,
    OwnerPhoneRequestForm,
    OwnerRegistrationRequestForm,
    OwnerAccountCompletionForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from apps.core.services.client_ip import get_client_ip_bucket

from .models import ContactMessage, OwnerOtpChallenge, OwnerTermsAcceptance
from .phone import InvalidPhoneError, normalize_iranian_phone
from .terms import CURRENT_TERMS_VERSION, TERMS_ACCEPTANCE_REQUIRED_MESSAGE
from .services import (
    handoff_service,
    onboarding_publish_service,
    owner_auth_service,
    owner_otp_service,
    owner_sms_service,
    platform_config_service,
    provisioning_service,
    session_service,
    step_up_service,
    turnstile_service,
)
from .services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit

logger = logging.getLogger(__name__)

_STORE_CREATE_TOKEN_SESSION_KEY = "portal_store_create_token"
DEFAULT_TRIAL_STORE_NAME = "فروشگاه من"
_OTP_SESSION_PHONE_KEY = "portal_otp_phone"
_OTP_SESSION_PURPOSE_KEY = "portal_otp_purpose"
_OTP_SESSION_FULL_NAME_KEY = "portal_otp_full_name"
_OTP_SESSION_NEXT_KEY = "portal_otp_next"
_OTP_SESSION_ADMIN_RETURN_KEY = "portal_otp_admin_return"
_OTP_SESSION_REMEMBER_KEY = "portal_otp_remember_me"
_OTP_SESSION_FLASH_KEY = "portal_otp_flash"
_OTP_SESSION_STARTED_KEY = "portal_otp_started_at"
#: نسخه‌ی قوانینی که /register/ (پس از اعتبارسنجیِ چک‌باکسِ الزامی) در نشستِ *سمتِ سرور*
#: گذاشته؛ /verify/ هرگز نسخه‌ای از کلاینت نمی‌پذیرد و فقط همین مقدار را می‌خواند.
_OTP_SESSION_TERMS_VERSION_KEY = "portal_otp_accepted_terms_version"
#: «اجازه‌ی تعیینِ رمزِ جدید» — فقط سمتِ سرور (نشست)، کوتاه‌عمر و تک‌مصرف؛ تنها پس از
#: موفقیتِ OTPِ هدفِ «بازیابی رمز» نوشته می‌شود. صفحه‌ی رمزِ جدید کاربر را *فقط* از همین
#: می‌خواند، هرگز از بدنه‌ی درخواست. این OTP هرگز کسی را وارد نمی‌کند.
_RESET_PENDING_KEY = "portal_password_reset_pending"
RESET_PENDING_TTL_SECONDS = 600
#: «شمارهٔ تأییدشده، منتظرِ تکمیلِ ثبت‌نام» — فقط سمتِ سرور (نشست)، با عمرِ کوتاه،
#: و تنها پس از موفقیتِ OTP نوشته می‌شود. مرحله‌ی تکمیل شماره را *فقط* از همین
#: می‌خواند، هرگز از بدنه‌ی درخواست.
_SIGNUP_PENDING_KEY = "portal_signup_pending"
SIGNUP_PENDING_TTL_SECONDS = 600
_OTP_SESSION_KEYS = (
    _OTP_SESSION_PHONE_KEY, _OTP_SESSION_PURPOSE_KEY, _OTP_SESSION_FULL_NAME_KEY,
    _OTP_SESSION_NEXT_KEY, _OTP_SESSION_ADMIN_RETURN_KEY, _OTP_SESSION_REMEMBER_KEY,
    _OTP_SESSION_FLASH_KEY, _OTP_SESSION_STARTED_KEY, _OTP_SESSION_TERMS_VERSION_KEY,
)


def _turnstile_form_is_valid(request, form, *, action: str) -> bool:
    result = turnstile_service.verify_request(
        request, expected_action=action
    )
    if result.success:
        return True
    form.add_error(None, turnstile_service.PUBLIC_ERROR_MESSAGE)
    return False


# ---------------------------------------------------------------------------
# Public marketing pages (Section A)
# ---------------------------------------------------------------------------


def home(request):
    return render(request, "portal/public/home.html")


def features(request):
    return render(request, "portal/public/features.html")


def design(request):
    return render(request, "portal/public/design.html")


def about(request):
    return render(request, "portal/public/about.html")


def supported_industries(request):
    """صفحه‌ی عمومیِ «صنوفِ پشتیبانی‌شده» — بخشِ ۶. تمامِ کارت‌ها از رکوردهایِ
    واقعیِ ``IndustryTemplate`` خوانده می‌شوند (تکِ منبعِ حقیقتِ کاتالوگِ
    صنف)، نه یک فهرستِ ثابتِ HTML."""
    templates = industry_catalog_service.offerable_industry_templates()
    return render(request, "portal/public/supported_industries.html", {
        "industry_templates": templates,
        "industry_sector_tabs": industry_catalog_service.SECTOR_TABS,
        "industry_count": len(templates),
    })


def plans(request):
    plan_rows = []
    for plan in Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order", "code"):
        version = plan.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first()
        if version is not None:
            plan_rows.append({"plan": plan, "version": version})
    return render(request, "portal/public/plans.html", {"plan_rows": plan_rows})


def help_center(request):
    return render(request, "portal/public/help.html")


def terms(request):
    return render(request, "portal/public/terms.html", {"terms_version": CURRENT_TERMS_VERSION})


def privacy(request):
    return render(request, "portal/public/privacy.html")


def platform_robots_txt(request):
    """robots.txt برایِ خودِ سایتِ راستیسی (Section 18) — مجزا از ``apps.core.
    seo.robots_txt``ی tenant-scoped که مخصوصِ storefront هر Store است. فقط
    ناحیه‌ی احرازهویت‌شده (``/app/``) را از crawl کنار می‌گذارد؛ صفحاتِ ورود/
    ثبت‌نام/بازیابیِ رمز از طریقِ noindex در خودِ صفحه مدیریت می‌شوند (نه
    Disallow اینجا)، تا در دسترسِ ربات بمانند ولی ایندکس نشوند."""
    from django.http import HttpResponse

    lines = [
        "User-agent: *",
        "Disallow: /app/",
        f"Sitemap: {request.build_absolute_uri(reverse('portal:sitemap-xml'))}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def platform_sitemap_xml(request):
    """sitemap.xmlِ سایتِ عمومیِ راستیسی — فقط صفحاتِ واقعاً عمومی/ایندکس‌پذیر."""
    entries = [
        {"loc": request.build_absolute_uri(reverse("portal:home")), "priority": "1.0", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:features")), "priority": "0.8", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:design")), "priority": "0.8", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:about")), "priority": "0.6", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:supported-industries")), "priority": "0.8", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:plans")), "priority": "0.9", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:help")), "priority": "0.6", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:contact")), "priority": "0.5", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:register")), "priority": "0.9", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:terms")), "priority": "0.3", "lastmod": None},
        {"loc": request.build_absolute_uri(reverse("portal:privacy")), "priority": "0.3", "lastmod": None},
    ]
    return render(request, "seo/sitemap.xml", {"entries": entries}, content_type="application/xml")


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        try:
            enforce_rate_limit(
                "contact", get_client_ip_bucket(request), max_attempts=5, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد ارسال پیام بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/contact.html", {"form": form})
        except RateLimitUnavailable:
            messages.error(request, UNAVAILABLE_MESSAGE)
            return render(request, "portal/public/contact.html", {"form": form})
        if form.is_valid() and _turnstile_form_is_valid(
            request, form, action="contact"
        ):
            ContactMessage.objects.create(**form.cleaned_data)
            messages.success(request, "پیام شما دریافت شد؛ به‌زودی با شما تماس می‌گیریم.")
            return redirect("portal:contact")
    else:
        form = ContactForm()
    return render(request, "portal/public/contact.html", {"form": form})


# ---------------------------------------------------------------------------
# Owner identity (Section B)
# ---------------------------------------------------------------------------


_NEXT_MAX_LENGTH = 2000


def _is_safe_next(next_url: str) -> bool:
    """فقط مسیرِ محلیِ هم‌میزبان («/…») پذیرفته می‌شود. علاوه بر ردِ «//host» و
    «scheme:»، قاعده‌یِ خودِ جنگو (``url_has_allowed_host_and_scheme`` با
    ``allowed_hosts=None``، یعنی هیچ hostِ خارجی) شکل‌هایِ مرورگریِ بک‌اسلش
    (slash+backslash+host)، tab/newlineِ میانه، «///host» و نویسه‌هایِ کنترلی را
    هم می‌بندد؛ یک ``startswith('//')`` ساده این‌ها را رد نمی‌کرد (open redirect)."""
    if not next_url or len(next_url) > _NEXT_MAX_LENGTH or not next_url.startswith("/"):
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in next_url):
        return False
    return url_has_allowed_host_and_scheme(next_url, allowed_hosts=None)


def _request_otp_and_go_to_verify(
    request, *, phone_raw: str, full_name: str, purpose: str,
    next_url: str = "", admin_return: str = "", remember_me: bool = False,
    accepted_terms_version: str = "",
):
    try:
        phone = normalize_iranian_phone(phone_raw)
    except InvalidPhoneError as exc:
        return None, str(exc.messages[0] if exc.messages else exc)

    try:
        owner_otp_service.request_otp(
            phone=phone, purpose=purpose, client_ip=get_client_ip_bucket(request),
        )
    except owner_otp_service.OtpRateLimitError as exc:
        return None, str(exc)

    request.session.pop(_SIGNUP_PENDING_KEY, None)
    request.session.pop(_RESET_PENDING_KEY, None)
    request.session[_OTP_SESSION_PHONE_KEY] = phone
    request.session[_OTP_SESSION_PURPOSE_KEY] = purpose
    request.session[_OTP_SESSION_FULL_NAME_KEY] = full_name
    request.session[_OTP_SESSION_NEXT_KEY] = next_url
    request.session[_OTP_SESSION_ADMIN_RETURN_KEY] = admin_return
    request.session[_OTP_SESSION_REMEMBER_KEY] = bool(remember_me)
    request.session[_OTP_SESSION_STARTED_KEY] = int(time.time())
    if accepted_terms_version:
        request.session[_OTP_SESSION_TERMS_VERSION_KEY] = accepted_terms_version
    else:
        request.session.pop(_OTP_SESSION_TERMS_VERSION_KEY, None)
    return phone, None


def _post_login_redirect(request, user, *, next_url: str, admin_return: str):
    """مقصدِ مشترکِ پس از ورودِ موفق — چه با رمز عبور چه با OTP (Section 4،
    یکپارچه‌سازیِ احرازِ هویت). ابتدا هندشیکِ Merchant Admin (اگر این ورود
    از یک درخواستِ بدونِ احرازِ پنلِ مدیریت آمده)، وگرنه ``next`` امن، وگرنه
    My Stores."""
    if admin_return:
        decoded = handoff_service.decode_admin_return_token(admin_return)
        if decoded is not None:
            admin_subdomain, destination_path = decoded
            target_store = Store.objects.filter(admin_subdomain=admin_subdomain).first()
            if target_store is not None:
                try:
                    ticket = handoff_service.issue_ticket(
                        user=user, store=target_store, destination_path=destination_path,
                    )
                except handoff_service.HandoffError:
                    messages.error(request, "شما عضوِ فعالِ آن فروشگاه نیستید.")
                else:
                    admin_host = f"{admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
                    return redirect(build_cross_host_url(
                        request, hostname=admin_host,
                        path=f"/admin-portal/handoff/{ticket.token}/",
                    ))

    if _is_safe_next(next_url):
        return redirect(next_url)
    return redirect("portal:app-home")


def register(request):
    """Section 3: owner registration is phone + OTP only. There is no public
    email+password registration (``/register-email/`` just redirects here);
    email accounts that already exist keep logging in through ``/login/``.

    نامِ کامل الزامی است و فقط از همین فرم می‌آید؛ شماره و نام در نشستِ
    سمتِ سرور نگه داشته می‌شوند و ``/verify/`` هیچ نامی را از کلاینت نمی‌پذیرد.
    وقتی ``new_store_registration_enabled`` خاموش است، این صفحه اطلاعِ
    ناموجود بودنِ ثبت‌نام را می‌دهد و هیچ OTPی صادر نمی‌شود؛ مالکانِ موجود از
    ``/login/`` وارد می‌شوند."""
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    if not platform_config_service.is_new_store_registration_enabled():
        return render(
            request, "portal/public/register.html",
            {"form": OwnerRegistrationRequestForm(), "registration_open": False, "terms_version": CURRENT_TERMS_VERSION},
        )

    if request.method == "POST":
        form = OwnerRegistrationRequestForm(request.POST)
        if form.is_valid() and _turnstile_form_is_valid(
            request, form, action="register"
        ):
            phone, error = _request_otp_and_go_to_verify(
                request, phone_raw=form.cleaned_data["phone"],
                full_name=form.cleaned_data["full_name"], purpose=OwnerOtpChallenge.Purpose.REGISTER,
                remember_me=form.cleaned_data.get("remember_me", False),
                # نسخه را سرور می‌داند؛ فقط چون چک‌باکس معتبر بود در نشستِ سرور گذاشته می‌شود.
                accepted_terms_version=CURRENT_TERMS_VERSION,
            )
            if error:
                form.add_error(None, error)
            else:
                return redirect("portal:otp-verify")
    else:
        form = OwnerRegistrationRequestForm()
    return render(
        request, "portal/public/register.html",
        {"form": form, "registration_open": True, "terms_version": CURRENT_TERMS_VERSION},
    )


def login_view(request):
    """Section 4/یکپارچه‌سازیِ احرازِ هویت — صفحه‌ی یکپارچه‌ی ورود: فرمِ
    رمزِ عبور (ایمیل یا موبایل) پیش‌فرض، فرمِ درخواستِ OTP گزینه‌ی ثانویه.
    این هم‌چنان همان مقصدی است که یک درخواستِ بدونِ احرازِ Merchant Admin
    (``apps.dashboard.decorators.staff_required``'s ``admin_return``) به
    آن هدایت می‌شود — Rastisi employees/owners always authenticate
    centrally, never via a per-Store login form.

    این ویو فقط مسیرِ درخواستِ OTP را مدیریت می‌کند (POST بدونِ ``mode``
    یا با آن — تاریخی، همیشه همین بوده)؛ POSTِ فرمِ رمزِ عبور به
    ``portal:login-password`` جداگانه می‌رود (نگاه کنید به ``login_
    password`` پایین‌تر) تا هیچ‌کدام منطقِ دیگری را پیچیده نکند."""
    if request.user.is_authenticated:
        # An already signed-in owner arriving with a signed admin_return (for
        # example from the legacy /admin-portal/login/ redirect) continues to
        # that store's handoff; ACTIVE membership is still enforced by
        # ``issue_ticket``. Without one this is the usual My Stores redirect.
        admin_return = request.GET.get("admin_return") or ""
        return _post_login_redirect(
            request, request.user, next_url=request.GET.get("next") or "", admin_return=admin_return,
        )

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    admin_return = request.GET.get("admin_return") or request.POST.get("admin_return") or ""
    if request.method == "POST":
        otp_form = OwnerPhoneRequestForm(request.POST)
        if otp_form.is_valid() and _turnstile_form_is_valid(
            request, otp_form, action="login_otp"
        ):
            phone, error = _request_otp_and_go_to_verify(
                request, phone_raw=otp_form.cleaned_data["phone"], full_name="",
                purpose=OwnerOtpChallenge.Purpose.LOGIN, next_url=next_url, admin_return=admin_return,
                remember_me=otp_form.cleaned_data.get("remember_me", False),
            )
            if error:
                otp_form.add_error(None, error)
            else:
                return redirect("portal:otp-verify")
    else:
        otp_form = OwnerPhoneRequestForm()
    password_form = OwnerIdentifierLoginForm()
    # POST here is always the OTP form; ``?mode=otp`` is the no-JS tab link.
    mode = "otp" if request.method == "POST" or request.GET.get("mode") == "otp" else "password"
    return render(
        request, "portal/public/login.html",
        {
            "otp_form": otp_form, "password_form": password_form, "mode": mode,
            "next": next_url, "admin_return": admin_return,
            "registration_open": platform_config_service.is_new_store_registration_enabled(),
        },
    )


_LOGIN_THROTTLED_MESSAGE = "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید."
LOGIN_IDENTIFIER_MAX_ATTEMPTS = 10
LOGIN_IDENTIFIER_WINDOW_SECONDS = 600


def _login_identifier_throttled(form) -> bool:
    """سقفِ تلاشِ ورود به‌ازایِ *شناسه* (جدا از سقفِ IP): پشتِ IPهایِ چرخان نمی‌شود
    یک حساب را بی‌نهایت حدس زد. کلید از متنِ واردشده ساخته می‌شود (نه از وجودِ
    حساب)، پس خودِ این سقف چیزی دربارهٔ وجودِ حساب فاش نمی‌کند. قربانیِ
    قفل‌شدن همچنان با کدِ پیامکی می‌تواند وارد شود."""
    key = owner_auth_service.login_identifier_throttle_key(form.cleaned_data["identifier"])
    try:
        enforce_rate_limit(
            "login_password_identifier", key,
            max_attempts=LOGIN_IDENTIFIER_MAX_ATTEMPTS, window_seconds=LOGIN_IDENTIFIER_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        return True
    # RateLimitUnavailable deliberately propagates: the caller must fail closed.
    return False


@require_http_methods(["GET", "HEAD", "POST"])
def login_password(request):
    """POSTِ فرمِ رمزِ عبورِ صفحه‌ی یکپارچه‌ی ورود — شناسه (ایمیل یا
    موبایل) + رمز عبور. پیامِ خطا همیشه عمومی است؛ هرگز فاش نمی‌کند کدام
    بخش نادرست بود یا اصلاً چنین حسابی هست یا نه.

    پس از یک ورودِ ناموفق نشانیِ مرورگر همین آدرس است؛ بارگذاریِ دوباره/نشانک
    (GET) به‌جای 405 به صفحه‌ی ورود می‌رود (``next``/``admin_return`` حفظ می‌شوند)
    — هیچ ورودی‌ای با GET انجام نمی‌شود."""
    if request.method != "POST":
        params = {k: request.GET[k] for k in ("next", "admin_return") if request.GET.get(k)}
        target = reverse("portal:login")
        return redirect(f"{target}?{urlencode(params)}" if params else target)
    if request.user.is_authenticated:
        return redirect("portal:app-home")

    next_url = request.POST.get("next") or ""
    admin_return = request.POST.get("admin_return") or ""
    form = OwnerIdentifierLoginForm(request.POST)
    try:
        enforce_rate_limit(
            "login_password", get_client_ip_bucket(request), max_attempts=15, window_seconds=600,
        )
    except RateLimitExceeded:
        form.add_error(None, "تعداد تلاش ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
    except RateLimitUnavailable:
        # Fail closed: no password authentication while the shared counter is down.
        form.add_error(None, UNAVAILABLE_MESSAGE)
    else:
        if form.is_valid() and _turnstile_form_is_valid(
            request, form, action="login_password"
        ):
            # Turnstile first: only a solved challenge may spend (or lock) an
            # identifier's attempt budget, so an anonymous script cannot lock a victim out.
            try:
                throttled = _login_identifier_throttled(form)
            except RateLimitUnavailable:
                # Fail closed: the per-identifier budget cannot be charged, so no authentication.
                form.add_error(None, UNAVAILABLE_MESSAGE)
            else:
                if throttled:
                    form.add_error(None, _LOGIN_THROTTLED_MESSAGE)
                else:
                    user = owner_auth_service.authenticate_owner_by_identifier(
                        request, identifier=form.cleaned_data["identifier"],
                        password=form.cleaned_data["password"],
                    )
                    if user is None:
                        form.add_error(None, owner_auth_service.GENERIC_LOGIN_ERROR)
                    else:
                        auth_login(request, user)
                        session_service.apply_remember_me(request, form.cleaned_data.get("remember_me", False))
                        return _post_login_redirect(
                            request, user, next_url=next_url, admin_return=admin_return,
                        )

    otp_form = OwnerPhoneRequestForm()
    return render(
        request, "portal/public/login.html",
        {
            "otp_form": otp_form, "password_form": form, "mode": "password",
            "next": next_url, "admin_return": admin_return, "password_mode": True,
            "registration_open": platform_config_service.is_new_store_registration_enabled(),
        },
    )


_OTP_CHECK_MESSAGES = {
    owner_otp_service.OtpCheckResult.INVALID: "کد واردشده درست نیست؛ دوباره بررسی کنید.",
    owner_otp_service.OtpCheckResult.EXPIRED: "این کد منقضی یا قبلاً استفاده شده است؛ کد جدید دریافت کنید.",
    owner_otp_service.OtpCheckResult.TOO_MANY_ATTEMPTS: "تعداد تلاش‌های این کد به حد مجاز رسید؛ کد جدید دریافت کنید.",
}
_REGISTRATION_CLOSED_LOGIN_MESSAGE = (
    "حسابی با این شماره پیدا نشد و ساخت فروشگاه تازه موقتاً در دسترس نیست."
)
_INACTIVE_ACCOUNT_MESSAGE = "ورود با این شماره امکان‌پذیر نیست؛ لطفاً با پشتیبانی تماس بگیرید."


_RESET_GENERIC_NOTICE = "اگر حساب فعالی با این شماره وجود داشته باشد، کد تأیید برای آن ارسال می‌شود."
_RESET_RESEND_NOTICE = "اگر حساب فعالی با این شماره وجود داشته باشد، کد جدید برای آن ارسال می‌شود."
_RESET_OTP_FAILURE_MESSAGE = "کد واردشده نادرست یا منقضی شده است؛ در صورت نیاز کد جدید دریافت کنید."
_SMS_UNAVAILABLE_MESSAGE = "ارسال پیامک در حال حاضر در دسترس نیست؛ لطفاً کمی بعد دوباره تلاش کنید."
_RESET_SESSION_EXPIRED_MESSAGE = "زمانِ تعیینِ رمز عبور به پایان رسید؛ لطفاً دوباره کد تأیید بگیرید."


def _clear_otp_session(request) -> None:
    for key in _OTP_SESSION_KEYS:
        request.session.pop(key, None)


def _reset_otp_timing(request) -> dict:
    """UX countdowns for the password-reset verify page, computed from the *session* only. The
    real challenge row exists only for an eligible account, so reading it would leak whether the
    phone has an account; this makes the page identical for known and unknown numbers."""
    started = request.session.get(_OTP_SESSION_STARTED_KEY)
    elapsed = max(0, int(time.time()) - started) if isinstance(started, int) else owner_otp_service.OTP_TTL_SECONDS
    return {
        "expires_in": max(0, owner_otp_service.OTP_TTL_SECONDS - elapsed),
        "resend_in": max(0, owner_otp_service.RESEND_COOLDOWN_SECONDS - elapsed),
        "cooldown_seconds": owner_otp_service.RESEND_COOLDOWN_SECONDS,
    }


def _render_otp_verify(request, form, *, phone: str, purpose: str):
    is_registration = purpose == OwnerOtpChallenge.Purpose.REGISTER
    is_reset = purpose == OwnerOtpChallenge.Purpose.PASSWORD_RESET
    if is_registration:
        change_phone_url = reverse("portal:register")
    elif is_reset:
        change_phone_url = reverse("portal:password-reset-request")
    else:
        change_phone_url = reverse("portal:login")
    return render(
        request, "portal/public/otp_verify.html",
        {
            "form": form, "phone": phone, "purpose": purpose, "is_registration": is_registration,
            "is_reset": is_reset,
            "resend_url": reverse("portal:otp-resend"),
            "change_phone_url": change_phone_url,
            "timing": (
                _reset_otp_timing(request) if is_reset
                else owner_otp_service.resend_timing(phone=phone, purpose=purpose)
            ),
            "otp_ttl_minutes": max(1, owner_otp_service.OTP_TTL_SECONDS // 60),
            "flash": request.session.pop(_OTP_SESSION_FLASH_KEY, None),
        },
    )


def otp_verify(request):
    """تأییدِ کدِ OTP و تکمیلِ ورود/ثبت‌نام.

    همه‌ی وضعیت (شماره، هدف، نامِ ثبت‌نام، next، …) از **نشستِ سمتِ سرور** که
    درخواستِ OTP ساخته می‌آید؛ بدنه‌ی POST فقط ``code`` (و یک ``phone`` برایِ
    تشخیصِ صفحه‌ی کهنه) را می‌دهد. فروشگاهِ آزمایشیِ اول فقط وقتی ساخته می‌شود
    که همین درخواست ``OwnerProfile`` را واقعاً ساخته باشد (``owner_created``)
    — چه ``User`` تازه باشد چه مشتریِ موجود."""
    phone = request.session.get(_OTP_SESSION_PHONE_KEY)
    purpose = request.session.get(_OTP_SESSION_PURPOSE_KEY)
    if not phone or not purpose:
        return redirect("portal:login")

    is_registration = purpose == OwnerOtpChallenge.Purpose.REGISTER
    is_reset = purpose == OwnerOtpChallenge.Purpose.PASSWORD_RESET
    if is_registration and not request.session.get(_OTP_SESSION_FULL_NAME_KEY):
        # نشستِ ثبت‌نام بدونِ نام معتبر نیست (نباید رخ دهد)؛ از ابتدا شروع شود.
        _clear_otp_session(request)
        return redirect("portal:register")
    if is_registration and request.session.get(_OTP_SESSION_TERMS_VERSION_KEY) != CURRENT_TERMS_VERSION:
        # بدونِ تأییدِ معتبرِ نسخه‌ی *فعلیِ* قوانین در نشستِ سرور (دست‌کاری/حذف، یا نسخه بینِ
        # درخواستِ کد و تأیید عوض شده) fail-closed: حالت پاک می‌شود، هیچ مالک/فروشگاهی ساخته
        # نمی‌شود و کدِ OTP هم مصرف نمی‌شود.
        _clear_otp_session(request)
        messages.error(request, TERMS_ACCEPTANCE_REQUIRED_MESSAGE)
        return redirect("portal:register")

    if request.method != "POST":
        return _render_otp_verify(request, OwnerOtpVerifyForm(initial={"phone": phone}), phone=phone, purpose=purpose)

    form = OwnerOtpVerifyForm(request.POST)
    if not form.is_valid():
        return _render_otp_verify(request, form, phone=phone, purpose=purpose)
    posted_phone = form.cleaned_data.get("phone")
    if posted_phone and posted_phone != phone:
        form.add_error(None, "این صفحه مربوط به درخواستِ قدیمی است؛ صفحه را دوباره باز کنید.")
        return _render_otp_verify(request, form, phone=phone, purpose=purpose)

    result = owner_otp_service.check_otp(phone=phone, purpose=purpose, code=form.cleaned_data["code"])
    if result is not owner_otp_service.OtpCheckResult.OK:
        # Reset: ONE message for every failure kind — a precise one ("wrong" vs "expired") would
        # tell an attacker whether this phone has an active challenge, i.e. an account.
        form.add_error("code", _RESET_OTP_FAILURE_MESSAGE if is_reset else _OTP_CHECK_MESSAGES[result])
        return _render_otp_verify(request, form, phone=phone, purpose=purpose)

    if is_reset:
        return _begin_password_reset_authorization(request, phone=phone)

    full_name = request.session.get(_OTP_SESSION_FULL_NAME_KEY, "") if is_registration else ""
    accepted_terms_version = request.session.get(_OTP_SESSION_TERMS_VERSION_KEY, "") if is_registration else ""
    next_url = request.session.get(_OTP_SESSION_NEXT_KEY, "")
    admin_return = request.session.get(_OTP_SESSION_ADMIN_RETURN_KEY, "")
    remember_me = request.session.get(_OTP_SESSION_REMEMBER_KEY, False)
    _clear_otp_session(request)

    registration_open = platform_config_service.is_new_store_registration_enabled()
    try:
        # OTP only proves the phone. An EXISTING Owner is recognised (and logged in) here; a phone with
        # no Owner NEVER gets one created at this step — whether it came from /register/ or /login/ — it
        # continues to the single «اطلاعات حساب» step where email + password (and, for /login/, name +
        # Terms) are collected, so no Owner/Store can exist without credentials.
        identity = owner_auth_service.resolve_owner_identity_by_phone(
            phone=phone, full_name=full_name, allow_new_owner=False,
        )
    except owner_auth_service.NewOwnerRegistrationClosedError:
        if registration_open:
            return _begin_account_completion(
                request, phone=phone, full_name=full_name, terms_version=accepted_terms_version,
                origin="register" if is_registration else "login",
                next_url=next_url, admin_return=admin_return, remember_me=bool(remember_me),
            )
        messages.warning(request, _REGISTRATION_CLOSED_LOGIN_MESSAGE)
        return redirect("portal:login")
    except owner_auth_service.OwnerAccountInactiveError:
        messages.error(request, _INACTIVE_ACCOUNT_MESSAGE)
        return redirect("portal:login")

    return _finish_owner_login(
        request, identity, next_url=next_url, admin_return=admin_return, remember_me=remember_me,
    )


def _finish_owner_login(request, identity, *, next_url: str, admin_return: str, remember_me: bool):
    """ورودِ نهایی پس از تعیینِ هویتِ مالک — مشترک بینِ تأییدِ OTP و مرحله‌ی
    «تکمیل ثبت‌نام». فروشگاهِ آزمایشیِ اول فقط وقتی ساخته می‌شود که همین درخواست
    ``OwnerProfile`` را واقعاً ساخته باشد (``owner_created``)."""
    auth_login(request, identity.user)
    session_service.apply_remember_me(request, remember_me)

    if identity.owner_created:
        # Section 3.1 ("onboarding mode C"): the first time a person becomes
        # an Owner (new User OR an existing storefront Customer) exactly one
        # trial Store is provisioned — the owner never sees an empty My
        # Stores page on their very first visit.
        try:
            store, store_created = provisioning_service.provision_initial_trial_store(
                owner=identity.user, name=DEFAULT_TRIAL_STORE_NAME,
            )
        except provisioning_service.RegistrationClosedError:
            messages.error(request, provisioning_service.REGISTRATION_CLOSED_MESSAGE)
        except provisioning_service.ProvisioningError:
            messages.error(
                request,
                "حساب شما ساخته شد، اما ساخت فروشگاه آزمایشی کامل نشد؛ "
                "از صفحه «فروشگاه‌های من» دوباره تلاش کنید.",
            )
        else:
            if store_created:
                return redirect("portal:onboarding", store_public_id=store.public_id)

    return _post_login_redirect(request, identity.user, next_url=next_url, admin_return=admin_return)


def _get_pending_signup(request):
    """وضعیتِ «شمارهٔ تأییدشده» از نشستِ سرور؛ منقضی/خراب → پاک و ``None``."""
    pending = request.session.get(_SIGNUP_PENDING_KEY)
    if isinstance(pending, dict):
        phone, verified_at = pending.get("phone"), pending.get("verified_at")
        if (
            isinstance(phone, str) and phone and isinstance(verified_at, int)
            and 0 <= time.time() - verified_at <= SIGNUP_PENDING_TTL_SECONDS
        ):
            return pending
    request.session.pop(_SIGNUP_PENDING_KEY, None)
    return None


def _begin_account_completion(
    request, *, phone: str, full_name: str, terms_version: str, origin: str,
    next_url: str, admin_return: str, remember_me: bool,
):
    """اثباتِ «این شماره با OTP تأیید شد» را (فقط سمتِ سرور، کوتاه‌عمر) می‌نویسد و به مرحله‌یِ
    «اطلاعات حساب» می‌رود. **رمز و ایمیل هرگز اینجا نیستند**: آن‌ها فقط در همان POSTِ مرحله‌یِ بعد
    می‌آیند و بلافاصله در تراکنشِ ساختِ حساب هش/ذخیره می‌شوند. ``full_name``/``terms_version`` فقط
    وقتی پر هستند که ``/register/`` آن‌ها را پیش‌تر (با چک‌باکسِ معتبر) سمتِ سرور گرفته باشد."""
    pending = {
        "phone": phone, "verified_at": int(time.time()), "next": next_url, "admin_return": admin_return,
        "remember_me": bool(remember_me), "full_name": full_name or "", "terms_version": terms_version or "",
        "origin": origin,
    }
    request.session[_SIGNUP_PENDING_KEY] = pending
    # A verified phone whose existing User already has an email AND a usable password, coming from /register/
    # (name + Terms already captured server-side), has nothing left to ask: complete right away. The existing
    # password/email are preserved untouched. Any hiccup falls back to the visible step (the proof stays valid).
    requirements = owner_auth_service.signup_requirements_for_phone(phone)
    if not requirements.existing_owner:
        form = _signup_form_for(request, pending, requirements, data={})
        if not form.fields and form.is_valid():
            response = _finish_account_completion(request, pending, form, _signup_context(pending))
            if response.status_code == 302:
                return response
    return redirect("portal:signup-complete")


def _signup_context(pending) -> dict:
    return {
        "phone": pending["phone"], "registration_open": True, "terms_version": CURRENT_TERMS_VERSION,
        "password_help": password_validators_help_texts(), "full_name": pending.get("full_name", ""),
        "from_register": pending.get("origin") == "register",
    }


def _signup_form_for(request, pending, requirements, *, data=None):
    terms_ok = pending.get("terms_version") == CURRENT_TERMS_VERSION
    return OwnerAccountCompletionForm(
        data, phone=pending["phone"], need_full_name=not pending.get("full_name"), need_terms=not terms_ok,
        need_email=requirements.need_email, need_password=requirements.need_password, user=requirements.user,
    )


def signup_complete(request):
    """«اطلاعات حساب»: شمارهٔ تأییدشده با OTP هنوز مالک ندارد؛ **ایمیل + رمز عبور** (و در مسیرِ
    ``/login/`` نام و قوانین) را می‌گیرد و سپس — فقط در صورتِ موفقیتِ همه — دقیقاً یک ``User``/
    ``OwnerProfile``/پذیرشِ قوانین و یک فروشگاهِ آزمایشی می‌سازد.

    امنیت: شماره **فقط** از نشستِ سمتِ سرور (که تنها پس از موفقیتِ OTP نوشته می‌شود و عمرِ کوتاه دارد)
    خوانده می‌شود؛ هیچ شماره/نسخه‌یِ قوانینی از بدنه نمی‌آید. اثباتِ شماره با خطایِ فرم سوخته نمی‌شود
    (کاربر می‌تواند اصلاح کند) و فقط پس از موفقیت پاک می‌شود (تک‌مصرف)؛ تکرار/دابل‌سابمیت/مسابقه را
    یکتاییِ دیتابیس و قفلِ سرویس ایمن می‌کند. اگر ``new_store_registration_enabled`` خاموش شده باشد
    هیچ‌چیز ساخته نمی‌شود. نیازِ فرم (ایمیل/رمز) از وضعیتِ *واقعیِ* ``User`` می‌آید: رمزِ قابل‌استفاده یا
    ایمیلِ ثبت‌شده‌یِ یک کاربرِ موجود هرگز خواسته/بازنویسی نمی‌شود."""
    pending = _get_pending_signup(request)
    if pending is None:
        return redirect("portal:login")
    if request.user.is_authenticated:
        request.session.pop(_SIGNUP_PENDING_KEY, None)
        return redirect("portal:app-home")

    phone = pending["phone"]
    context = _signup_context(pending)
    if not platform_config_service.is_new_store_registration_enabled():
        context.update(form=None, registration_open=False)
        return render(request, "portal/public/signup_complete.html", context)

    requirements = owner_auth_service.signup_requirements_for_phone(phone)
    if requirements.existing_owner:
        # Someone (this phone's owner, another tab) already completed it: the verified phone is the same
        # proof OTP login uses, so this is just a login. Nothing is created.
        request.session.pop(_SIGNUP_PENDING_KEY, None)
        try:
            identity = owner_auth_service.resolve_owner_identity_by_phone(phone=phone, allow_new_owner=False)
        except owner_auth_service.OwnerAccountInactiveError:
            messages.error(request, _INACTIVE_ACCOUNT_MESSAGE)
            return redirect("portal:login")
        return _finish_owner_login(
            request, identity, next_url=pending.get("next", ""),
            admin_return=pending.get("admin_return", ""), remember_me=bool(pending.get("remember_me")),
        )

    if request.method == "POST":
        form = _signup_form_for(request, pending, requirements, data=request.POST)  # a posted "phone" is never read
        if form.is_valid():
            return _finish_account_completion(request, pending, form, context)
    else:
        form = _signup_form_for(request, pending, requirements)
    context["form"] = form
    return render(request, "portal/public/signup_complete.html", context)


def _finish_account_completion(request, pending, form, context):
    cleaned = form.cleaned_data
    source = (
        OwnerTermsAcceptance.Source.REGISTRATION if pending.get("origin") == "register"
        else OwnerTermsAcceptance.Source.SIGNUP_COMPLETE
    )
    try:
        identity = owner_auth_service.resolve_owner_identity_by_phone(
            phone=pending["phone"], full_name=pending.get("full_name") or cleaned.get("full_name", ""),
            allow_new_owner=platform_config_service.is_new_store_registration_enabled(),
            # قوانین: یا همین فرم چک‌باکسِ معتبر داشت یا نسخه‌یِ فعلی پیش‌تر سمتِ سرور ثبت شده بود؛
            # نسخه همیشه ثابتِ سرور است نه مقدارِ ارسالی.
            accepted_terms_version=CURRENT_TERMS_VERSION, terms_source=source,
            require_credentials=True, email=cleaned.get("email", ""), password=cleaned.get("password", ""),
        )
    except owner_auth_service.NewOwnerRegistrationClosedError:
        context.update(form=None, registration_open=False)
        return render(request, "portal/public/signup_complete.html", context)
    except owner_auth_service.OwnerAccountInactiveError:
        request.session.pop(_SIGNUP_PENDING_KEY, None)
        messages.error(request, _INACTIVE_ACCOUNT_MESSAGE)
        return redirect("portal:login")
    except owner_auth_service.PasswordPolicyError as exc:
        form.add_error("password" if "password" in form.fields else None, ValidationError(exc.messages))
    except owner_auth_service.OwnerEmailError as exc:  # incl. a conflict found inside the transaction (race)
        form.add_error("email" if "email" in form.fields else None, str(exc))
    except owner_auth_service.OwnerCredentialsError as exc:
        form.add_error(None, str(exc))
    else:
        request.session.pop(_SIGNUP_PENDING_KEY, None)  # single use
        return _finish_owner_login(
            request, identity, next_url=pending.get("next", ""),
            admin_return=pending.get("admin_return", ""), remember_me=bool(pending.get("remember_me")),
        )
    context["form"] = form
    return render(request, "portal/public/signup_complete.html", context)


@require_POST
def otp_resend(request):
    """ارسالِ دوباره‌ی کد برایِ همان درخواستِ در-جریان. شماره/هدف/نام/next همه
    از نشستِ سرور می‌آید (هیچ فیلدِ پنهانِ کلاینتی خوانده نمی‌شود). سقفِ
    درخواست به‌ازایِ شماره و IP همان سقف‌هایِ ``request_otp`` است؛ شمارشِ
    معکوسِ صفحه فقط UX است. Turnstile در همان درخواستِ اولِ ثبت‌نام/ورود
    اعمال شده و هر حلِ آن حداکثر به سقفِ شماره (۳ پیامک/۱۰ دقیقه) می‌رسد."""
    phone = request.session.get(_OTP_SESSION_PHONE_KEY)
    purpose = request.session.get(_OTP_SESSION_PURPOSE_KEY)
    if not phone or not purpose:
        return redirect("portal:login")

    if (
        purpose == OwnerOtpChallenge.Purpose.REGISTER
        and not platform_config_service.is_new_store_registration_enabled()
    ):
        _clear_otp_session(request)
        return redirect("portal:register")

    if purpose == OwnerOtpChallenge.Purpose.PASSWORD_RESET:
        # The resend cooldown for a reset is judged from the SESSION only (``_reset_otp_timing``): the same answer
        # for a known and an unknown phone, so it cannot reveal whether an account exists. The service enforces the
        # real per-(phone, purpose) cooldown as well. Both clocks start when the request is ACCEPTED (the session stamp is taken
        # before the send), so provider latency never shifts the countdown.
        wait = _reset_otp_timing(request)["resend_in"]
        if wait > 0:
            request.session[_OTP_SESSION_FLASH_KEY] = {
                "kind": "error", "text": owner_otp_service.OtpCooldownError(wait).args[0],
            }
            return redirect("portal:otp-verify")
        # Never the generic sender: that would create/send a reset challenge for ANY phone.
        # The helper re-checks that this phone belongs to an eligible owner, and answers the
        # same way for known and unknown numbers.
        requested_at = int(time.time())
        error = _send_reset_otp_if_eligible(request, phone=phone)
        if error:
            request.session[_OTP_SESSION_FLASH_KEY] = {"kind": "error", "text": error}
        else:
            request.session[_OTP_SESSION_STARTED_KEY] = requested_at
            request.session[_OTP_SESSION_FLASH_KEY] = {"kind": "ok", "text": _RESET_RESEND_NOTICE}
        return redirect("portal:otp-verify")

    try:
        owner_otp_service.request_otp(
            phone=phone, purpose=purpose, client_ip=get_client_ip_bucket(request),
        )
    except owner_otp_service.OtpRateLimitError as exc:
        request.session[_OTP_SESSION_FLASH_KEY] = {"kind": "error", "text": str(exc)}
    else:
        request.session[_OTP_SESSION_FLASH_KEY] = {"kind": "ok", "text": "کد جدید ارسال شد."}
    return redirect("portal:otp-verify")


@csrf_exempt  # reads nothing from the request: a stale cached form POST redirects instead of 403
def register_email(request):
    """Compatibility redirect — anonymous email+password registration no longer exists.

    New merchant/Owner registration must go through a verified mobile OTP:
    ``/register/`` (name + phone) or ``/login/`` → ``/signup/complete/``. Any
    method (GET *or* POST) is sent to ``/register/``; the body is never read,
    so nothing is created, nobody is authenticated and no Store is provisioned.
    Existing email accounts keep logging in via ``/login/`` (email + password)
    and ``/reset-password/``."""
    return redirect("portal:register")


def login_email(request):
    """جایگزین شد با صفحه‌ی یکپارچه‌ی ورود (یکپارچه‌سازیِ احرازِ هویت) —
    این آدرس فقط برایِ لینک‌های قدیمی/بوکمارک‌شده نگه داشته شده و همیشه
    به ``portal:login`` هدایت می‌کند؛ ``next``/``admin_return`` حفظ
    می‌شوند تا هیچ لینکِ موجودی نشکند."""
    params = request.GET.urlencode()
    target = reverse("portal:login")
    if params:
        target = f"{target}?{params}"
    return redirect(target)


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("portal:home")


def _send_reset_otp_if_eligible(request, *, phone: str) -> str | None:
    """Issue a password-reset OTP **only** to an existing, active owner — and answer identically
    for every phone, so the public flow is not an account-enumeration oracle.

    Returns a user-facing error only for *account-independent* failures (SMS not deliverable at
    all, per-IP budget, shared rate-limit store down). Everything that depends on the account —
    unknown/ineligible phone, per-phone budget, a provider failure for this send — is swallowed
    into the same generic success path: no *verifiable* challenge exists in those cases (a failed
    delivery leaves only a never-verifiable row that still holds the resend cooldown) and nothing is
    ever created for an unknown phone. The per-IP budget is charged for every phone, known or not."""
    if not owner_sms_service.otp_delivery_available():
        return _SMS_UNAVAILABLE_MESSAGE
    client_ip = get_client_ip_bucket(request)
    try:
        owner_otp_service.charge_ip_budget(purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET, client_ip=client_ip)
    except owner_otp_service.OtpRateLimitError as exc:  # incl. OtpDeliveryError("temporarily unavailable")
        return str(exc)

    if owner_auth_service.find_reset_eligible_user_by_phone(phone) is None:
        return None  # unknown / inactive / not an owner: send nothing, create nothing, say nothing
    try:
        owner_otp_service.request_otp(
            phone=phone, purpose=OwnerOtpChallenge.Purpose.PASSWORD_RESET, client_ip=client_ip, charge_ip=False,
        )
    except owner_otp_service.OtpRateLimitError:
        # Per-phone budget or SMS delivery failure. Not shown (it would reveal the account); the
        # operator-side detail is logged by the SMS layer. No active challenge remains.
        logger.warning("password-reset OTP was not issued (phone budget or SMS delivery failure)")
    except Exception as exc:  # noqa: BLE001 — deliberately NOT BaseException (Ctrl-C/SystemExit propagate)
        # An unexpected provider/infrastructure exception must not become a 500: that would be an
        # account-dependent response (an unknown phone never reaches the provider). ``request_otp``
        # leaves only the never-verifiable "pending" row, so no usable reset code and no authorization exist. Only the
        # exception CLASS is logged: its text may carry credentials, URLs or the code.
        logger.error("password-reset OTP failed unexpectedly: %s", exc.__class__.__name__)
    return None


def password_reset_request(request):
    """بازیابی/تعیینِ رمز با **موبایل + کدِ پیامکی** (جایگزینِ ایمیلِ عمومی).

    جریان: شماره → OTPِ هدفِ «بازیابی رمز» → ``/verify/`` → ``/reset-password/new/`` → ورود.
    هیچ ``User``/``OwnerProfile``/Store ساخته نمی‌شود و پاسخِ عمومی برایِ شمارهٔ ناشناخته،
    مالکِ فعال و حسابِ بدونِ رمز یکسان است. سقفِ IP همان ``password_reset`` است؛ Turnstile و
    fail-closed بودنِ شمارنده‌ی مشترک حفظ شده‌اند."""
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        try:
            enforce_rate_limit(
                "password_reset", get_client_ip_bucket(request), max_attempts=5, window_seconds=600,
            )
        except RateLimitExceeded:
            messages.error(request, "تعداد درخواست بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")
            return render(request, "portal/public/password_reset_request.html", {"form": form})
        except RateLimitUnavailable:
            messages.error(request, UNAVAILABLE_MESSAGE)
            return render(request, "portal/public/password_reset_request.html", {"form": form})
        if form.is_valid() and _turnstile_form_is_valid(
            request, form, action="password_reset"
        ):
            phone = form.cleaned_data["phone"]
            requested_at = int(time.time())  # the cooldown clock starts at acceptance, not after the provider answers
            error = _send_reset_otp_if_eligible(request, phone=phone)
            if error:
                form.add_error(None, error)
            else:
                for key in _OTP_SESSION_KEYS + (_SIGNUP_PENDING_KEY, _RESET_PENDING_KEY):
                    request.session.pop(key, None)
                request.session[_OTP_SESSION_PHONE_KEY] = phone
                request.session[_OTP_SESSION_PURPOSE_KEY] = OwnerOtpChallenge.Purpose.PASSWORD_RESET
                request.session[_OTP_SESSION_STARTED_KEY] = requested_at
                request.session[_OTP_SESSION_FLASH_KEY] = {"kind": "ok", "text": _RESET_GENERIC_NOTICE}
                return redirect("portal:otp-verify")
    else:
        form = PasswordResetRequestForm()
    return render(request, "portal/public/password_reset_request.html", {"form": form})


def _get_reset_authorization(request):
    """اجازه‌ی تعیینِ رمز از نشستِ سرور؛ نبود/خراب/منقضی → پاک و ``None``."""
    pending = request.session.get(_RESET_PENDING_KEY)
    if isinstance(pending, dict):
        uid, verified_at = pending.get("uid"), pending.get("verified_at")
        if (
            isinstance(uid, int) and not isinstance(uid, bool) and isinstance(verified_at, int)
            and 0 <= time.time() - verified_at <= RESET_PENDING_TTL_SECONDS
        ):
            return pending
    request.session.pop(_RESET_PENDING_KEY, None)
    return None


def _begin_password_reset_authorization(request, *, phone: str):
    """پس از موفقیتِ OTPِ بازیابی: هیچ ورودی انجام نمی‌شود و هیچ‌چیز ساخته نمی‌شود؛ فقط یک
    مجوزِ کوتاه‌عمر و تک‌مصرفِ سمتِ سرور (متصل به همین کاربر) نوشته و OTP session پاک می‌شود."""
    user = owner_auth_service.find_reset_eligible_user_by_phone(phone)
    _clear_otp_session(request)
    if user is None:  # became ineligible between issue and verify
        messages.error(request, _RESET_OTP_FAILURE_MESSAGE)
        return redirect("portal:password-reset-request")
    request.session.cycle_key()  # fresh session id for the new privilege
    request.session[_RESET_PENDING_KEY] = {"uid": user.pk, "verified_at": int(time.time())}
    return redirect("portal:password-reset-new")


@never_cache
def password_reset_new(request):
    """تعیینِ رمزِ جدید پس از تأییدِ موبایل با OTP.

    کاربر **فقط** از مجوزِ سمتِ سرور (نه از بدنه‌ی درخواست) خوانده و دوباره از نظرِ اهلیت
    سنجیده می‌شود؛ مجوز ۱۰ دقیقه اعتبار دارد و با موفقیت مصرف می‌شود (تک‌مصرف). رمز فقط از
    ``owner_auth_service.set_new_password`` (اعتبارسنجی‌هایِ Django) می‌گذرد. خودکار وارد
    نمی‌کند؛ به صفحه‌ی ورود می‌رود. حسابِ بدونِ رمز (ساخته‌شده با OTP) اولین رمزش را همین‌جا می‌گذارد."""
    pending = _get_reset_authorization(request)
    if pending is None:
        messages.warning(request, _RESET_SESSION_EXPIRED_MESSAGE)
        return redirect("portal:password-reset-request")
    user = owner_auth_service.get_reset_eligible_user_by_id(pending["uid"])
    if user is None:
        request.session.pop(_RESET_PENDING_KEY, None)
        messages.warning(request, _RESET_SESSION_EXPIRED_MESSAGE)
        return redirect("portal:password-reset-request")

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            try:
                owner_auth_service.set_new_password(user=user, password=form.cleaned_data["password"])
            except owner_auth_service.PasswordPolicyError as exc:
                for message in exc.messages:
                    form.add_error("password", message)
            else:
                request.session.pop(_RESET_PENDING_KEY, None)  # single use
                messages.success(request, "رمز عبور با موفقیت تعیین شد؛ اکنون می‌توانید با شماره موبایل و رمز جدید وارد شوید.")
                return redirect("portal:login")
    else:
        form = PasswordResetConfirmForm()
    return render(
        request, "portal/public/password_reset_confirm.html",
        {"form": form, "password_help": password_validators_help_texts(), "via_sms": True},
    )


#: The reset token lives in the URL path; see ``password_reset_confirm``.
RESET_CONFIRM_REFERRER_POLICY = "origin"


@never_cache
def password_reset_confirm(request, uidb64, token):
    """تعیینِ رمزِ جدید با پیوندِ ایمیلی. توکن در مسیرِ URL است، پس مسیر هرگز نباید
    به‌عنوانِ Referer فرستاده شود — حتی برایِ درخواست‌هایِ هم‌مبدأِ CSS/JS که در
    لاگِ وب‌سرور/پروکسی/CDN می‌نشینند. به همین دلیل ``Referrer-Policy: origin``
    (فقط scheme+host+port) و ``Cache-Control: no-store`` روی هر دو پاسخ (معتبر و
    نامعتبر) می‌آید.

    چرا نه ``no-referrer``: مرورگر در POSTِ فرم ``Origin: null`` می‌فرستد و بررسیِ
    Originِ CSRFِ جنگو فرمِ رمزِ جدید را رد می‌کند. چرا نه ``same-origin``: مسیرِ
    کاملِ (توکن‌دار) را در Refererِ درخواست‌هایِ هم‌مبدأ می‌فرستد. ``origin`` هر
    دو را برآورده می‌کند و Originِ واقعیِ POST حفظ می‌شود.
    اعتبارِ رمز فقط با ``AUTH_PASSWORD_VALIDATORS``ِ تنظیم‌شده سنجیده می‌شود."""
    user = owner_auth_service.get_user_from_reset_link(uidb64=uidb64, token=token)
    if user is None:
        response = render(request, "portal/public/password_reset_invalid.html", status=400)
        response["Referrer-Policy"] = RESET_CONFIRM_REFERRER_POLICY
        return response

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            try:
                owner_auth_service.set_new_password(
                    user=user, password=form.cleaned_data["password"]
                )
            except owner_auth_service.PasswordPolicyError as exc:
                for message in exc.messages:
                    form.add_error("password", message)
            else:
                messages.success(request, "رمز عبور با موفقیت تغییر کرد؛ اکنون می‌توانید وارد شوید.")
                return redirect("portal:login-email")
    else:
        form = PasswordResetConfirmForm()
    response = render(
        request, "portal/public/password_reset_confirm.html",
        {"form": form, "password_help": password_validators_help_texts()},
    )
    response["Referrer-Policy"] = RESET_CONFIRM_REFERRER_POLICY
    return response


# ---------------------------------------------------------------------------
# Owner account portal (Section E/F — My Stores; provisioning/onboarding
# lands in a later slice, so today this is a real, honest empty/list state)
# ---------------------------------------------------------------------------


def not_found(request, exception=None):
    """``handler404`` for ``shop_core.urls_platform`` (ADR-97) — the global
    ``templates/404.html`` extends the Store-scoped ``base.html`` (catalog/
    cart/customers nav links), which does not exist under this urlconf, so
    it cannot be reused here. Self-contained within ``portal/base_
    platform.html`` instead, which only ever references ``portal:*`` names."""
    return render(request, "portal/public/404.html", status=404)


@owner_required
def app_home(request):
    memberships = (
        StoreMembership.objects.filter(
            user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
        )
        .select_related("store")
        .order_by("store__name")
    )
    return render(request, "portal/app/my_stores.html", {"memberships": memberships})


@owner_required
def store_create(request):
    """Section D (lite) + Section G: one-step store name, then immediate atomic
    trial provisioning (``provisioning_service.provision_trial_store``).
    No industry template is installed here — that irreversible, one-time action
    lives on the onboarding «صنف» step behind a server-validated
    acknowledgement. Double-submit
    protection is a per-session, single-use token — a genuine, truly
    concurrent double-submit within the same session is not fully excluded
    (no DB-level mutex), but sequential double-clicks/back-button resubmits
    are: the token is rotated the moment a valid submission is accepted."""
    if request.method == "POST":
        form = CreateStoreForm(request.POST)
        session_token = request.session.get(_STORE_CREATE_TOKEN_SESSION_KEY)
        submitted_token = request.POST.get("submission_token")
        if not session_token or submitted_token != session_token:
            messages.error(request, "این درخواست قبلاً پردازش شده یا نامعتبر است؛ دوباره تلاش کنید.")
            return redirect("portal:store-create")

        if form.is_valid():
            request.session[_STORE_CREATE_TOKEN_SESSION_KEY] = get_random_string(32)
            # Policy (documented in ONBOARDING_JOURNEY_AUDIT.md): store creation NEVER installs an
            # industry template. The one-time, irreversible install happens only on the onboarding
            # «صنف» step, behind a server-validated acknowledgement. A posted
            # ``industry_template_id`` is deliberately not even read here.
            try:
                store = provisioning_service.provision_trial_store(
                    owner=request.user, name=form.cleaned_data["name"],
                )
            except provisioning_service.ProvisioningError as exc:
                messages.error(request, str(exc))
            else:
                return redirect("portal:store-created", store_public_id=store.public_id)
    else:
        request.session[_STORE_CREATE_TOKEN_SESSION_KEY] = get_random_string(32)
        form = CreateStoreForm()

    return render(
        request, "portal/app/store_create.html",
        {"form": form, "submission_token": request.session[_STORE_CREATE_TOKEN_SESSION_KEY]},
    )


@owner_required
@require_POST
def enter_admin(request, store_public_id):
    """Section H: issues a short-lived handoff ticket for a Store the
    caller actively belongs to and redirects to that Store's own admin
    host to consume it — never the portal's own session cookie, which has
    no meaning on that other host (ADR-98)."""
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    store = membership.store
    next_path = request.POST.get("next") or "/admin-portal/"
    if not next_path.startswith("/admin-portal/"):
        next_path = "/admin-portal/"
    try:
        ticket = handoff_service.issue_ticket(user=request.user, store=store, destination_path=next_path)
    except handoff_service.HandoffError:
        raise Http404
    admin_host = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    return redirect(build_cross_host_url(
        request, hostname=admin_host, path=f"/admin-portal/handoff/{ticket.token}/",
    ))


def _get_owned_store_or_404(request, store_public_id) -> Store:
    """فروشگاهی که کاربرِ جاری عضوِ فعالش است، وگرنه ``Http404`` — بدونِ افشای
    اینکه آیا اصلاً چنین Storeای وجود دارد (همان الگوی بقیه‌ی ویوهای پرتال)."""
    membership = get_object_or_404(
        StoreMembership.objects.select_related("store"),
        store__public_id=store_public_id, user=request.user, status=StoreMembership.MembershipStatus.ACTIVE,
    )
    return membership.store


# Section 5 — order of the onboarding wizard's stages. ``Store.onboarding_stage``
# always holds one of these; the dispatcher below sends the owner to wherever
# they left off (save-progress), but every stage remains freely revisitable —
# this is a memory of where to resume, not a hard sequential gate.
_ONBOARDING_STAGE_ORDER = [
    Store.OnboardingStage.IDENTITY,
    Store.OnboardingStage.INDUSTRY,
    Store.OnboardingStage.TEMPLATE,
    Store.OnboardingStage.BRANDING,
    Store.OnboardingStage.REVIEW,
]
_ONBOARDING_STAGE_URL_NAMES = {
    Store.OnboardingStage.IDENTITY: "portal:onboarding-identity",
    Store.OnboardingStage.INDUSTRY: "portal:onboarding-industry",
    Store.OnboardingStage.TEMPLATE: "portal:onboarding-template",
    Store.OnboardingStage.BRANDING: "portal:onboarding-branding",
    Store.OnboardingStage.REVIEW: "portal:onboarding-review",
}


#: برچسبِ مرحله‌ها در نوارِ پیشرفتِ ویزارد؛ ``True`` یعنی مرحله اختیاری است.
_ONBOARDING_STEP_META = {
    Store.OnboardingStage.IDENTITY: ("معرفی", False),
    Store.OnboardingStage.INDUSTRY: ("صنف", True),
    Store.OnboardingStage.TEMPLATE: ("قالب فروشگاه", False),
    Store.OnboardingStage.BRANDING: ("برند", True),
    Store.OnboardingStage.REVIEW: ("بازبینی", False),
}


def _publication_context(store) -> dict:
    """وضعیتِ *واقعیِ* انتشار (همان تک‌مرجعِ ``publication_service``) برای صفحه‌هایِ
    بازبینی/فروشگاهِ آماده — هرگز ادعایی درباره‌ی عمومی‌بودن بدونِ این سیگنال نمی‌شود."""
    state = publication_service.get_store_publication_state(store)
    return {
        "publication_state": state,
        "publication_state_label": publication_service.PublicationState(state).label,
        "is_publicly_visible": state not in publication_service.NON_PUBLIC_STATES,
        "private_until_publish": state == publication_service.PublicationState.TRIAL_PRIVATE,
        "publication_blocked_by_status": state in (
            publication_service.PublicationState.RESTRICTED,
            publication_service.PublicationState.SUSPENDED,
            publication_service.PublicationState.INACTIVE,
        ),
    }


INDUSTRY_CONFIRM_REQUIRED_MESSAGE = (
    "برای نصبِ قالبِ صنف باید تأیید کنید که این نصب یک‌بارمصرف است؛ کادرِ تأیید را علامت بزنید و دوباره تلاش کنید."
)


def _sector_tabs_for(template_cards) -> list:
    """فقط رسته‌هایی که واقعاً قالبِ قابل‌ارائه دارند (تبِ خالی دیده نمی‌شود)."""
    present = {card["sector"] for card in template_cards}
    return [tab for tab in industry_catalog_service.SECTOR_TABS if tab[0] == "all" or tab[0] in present]


def _onboarding_shell_context(store, current: str, *, applied_template="__lookup__") -> dict:
    """زمینه‌ی مشترکِ پوسته‌ی ویزارد (نوارِ پیشرفت، قبلی/بعدی) — فقط نمایشی.

    ``store.onboarding_stage`` دورترین مرحله‌ی رسیده است؛ مرحله‌هایِ قبل از آن
    «انجام‌شده» و آزادانه قابلِ بازدیدند، مرحله‌هایِ بعد از آن هنوز قفل‌اند
    (فقط با «ادامه» باز می‌شوند). هیچ منطقِ دسترسی/مجوزی اینجا نیست.

    مرحله‌ی «قالب فروشگاه» فقط وقتی «انجام‌شده» نشان داده می‌شود که قالبِ آماده‌ی
    معتبری واقعاً روی Draft/نسخه‌ی منتشرشده اعمال شده باشد (نه صرفاً چون
    ``onboarding_stage`` از آن گذشته — مثلاً فروشگاه‌هایِ قدیمیِ پیش از این مرحله)."""
    if applied_template == "__lookup__":
        applied_template = store_template_service.get_applied_template(store)
    order = _ONBOARDING_STAGE_ORDER
    if store.onboarding_stage in order:
        reached = order.index(store.onboarding_stage)
    elif store.onboarding_stage == Store.OnboardingStage.DONE or store.onboarding_completed_at:
        reached = len(order) - 1
    else:
        reached = 0
    steps = []
    for index, stage in enumerate(order):
        label, optional = _ONBOARDING_STEP_META[stage]
        is_current = stage == current
        steps.append({
            "key": stage, "number": index + 1, "label": label, "optional": optional,
            "url": reverse(_ONBOARDING_STAGE_URL_NAMES[stage], kwargs={"store_public_id": store.public_id}),
            "is_current": is_current,
            "is_done": index < reached and not is_current and (
                stage != Store.OnboardingStage.TEMPLATE or applied_template is not None
            ),
            "is_available": index <= reached,
        })
    current_index = order.index(current)
    return {
        "store": store,
        "ob_steps": steps,
        "ob_current": steps[current_index],
        "ob_total": len(order),
        "ob_previous_url": steps[current_index - 1]["url"] if current_index > 0 else None,
        "template_applied": applied_template is not None,
    }


def _advance_onboarding_stage(store, *, completed: str) -> None:
    """پس از تکمیلِ موفقِ یک مرحله، ``onboarding_stage`` را فقط رو به جلو
    می‌برد (هرگز عقب) — بازدیدِ دوباره‌ی یک مرحله‌ی قبلی هرگز پیشرفتِ
    ثبت‌شده را از دست نمی‌دهد."""
    current_index = _ONBOARDING_STAGE_ORDER.index(store.onboarding_stage) if (
        store.onboarding_stage in _ONBOARDING_STAGE_ORDER
    ) else -1
    completed_index = _ONBOARDING_STAGE_ORDER.index(completed)
    if completed_index >= current_index:
        next_index = completed_index + 1
        store.onboarding_stage = (
            _ONBOARDING_STAGE_ORDER[next_index] if next_index < len(_ONBOARDING_STAGE_ORDER)
            else Store.OnboardingStage.REVIEW
        )
        store.save(update_fields=["onboarding_stage", "updated_at"])


@owner_required
def onboarding(request, store_public_id):
    """نقطه‌ی ورودِ ویزاردِ آنبوردینگ (Section 5): مالک را به همان مرحله‌ای
    که رها کرده هدایت می‌کند (save-progress، ``Store.onboarding_stage``)."""
    store = _get_owned_store_or_404(request, store_public_id)
    if store.onboarding_stage == Store.OnboardingStage.DONE or store.onboarding_completed_at:
        return redirect("portal:store-created", store_public_id=store.public_id)
    stage = store.onboarding_stage if store.onboarding_stage in _ONBOARDING_STAGE_URL_NAMES else (
        Store.OnboardingStage.IDENTITY
    )
    if stage in (Store.OnboardingStage.BRANDING, Store.OnboardingStage.REVIEW) and (
        store_template_service.get_applied_template(store) is None
    ):
        # A Store from before the «قالب فروشگاه» step (or one that skipped past it) that is still
        # unpublished must choose a Ready Template before it can be published. Stored progress is
        # left untouched; already-completed Stores returned above and are never sent back.
        stage = Store.OnboardingStage.TEMPLATE
    return redirect(_ONBOARDING_STAGE_URL_NAMES[stage], store_public_id=store.public_id)


@owner_required
def onboarding_identity(request, store_public_id):
    """مرحله‌ی ۱: معرفیِ فروشگاه — نام، شعار، توضیحات، اطلاعاتِ تماس
    (``ShopSettings``، همان مدلی که پنلِ مدیریت هم ویرایش می‌کند)."""
    from apps.core.models import ShopSettings

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)

    if request.method == "POST":
        # AUTH-001: mutating store identity/ShopSettings requires the canonical
        # SETTINGS_MANAGE action permission — the same gate the Merchant Admin
        # ``settings_appearance`` view uses — not merely an ACTIVE membership.
        if not portal_action_allowed(request, store, SETTINGS_MANAGE):
            return portal_permission_denied(request)
        form = OnboardingIdentityForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            store.name = data["name"]
            store.save(update_fields=["name", "updated_at"])
            shop_settings.name = data["name"]
            shop_settings.tagline = data["tagline"]
            shop_settings.description = data["description"]
            shop_settings.contact_phone = data["contact_phone"]
            shop_settings.contact_email = data["contact_email"]
            shop_settings.contact_address = data["contact_address"]
            shop_settings.save()
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.IDENTITY)
            return redirect("portal:onboarding-industry", store_public_id=store.public_id)
    else:
        form = OnboardingIdentityForm(initial={
            "name": store.name, "tagline": shop_settings.tagline,
            "description": shop_settings.description, "contact_phone": shop_settings.contact_phone,
            "contact_email": shop_settings.contact_email, "contact_address": shop_settings.contact_address,
        })

    return render(request, "portal/app/onboarding_identity.html", {
        **_onboarding_shell_context(store, Store.OnboardingStage.IDENTITY), "form": form,
    })


@owner_required
def onboarding_industry(request, store_public_id):
    """مرحله‌ی ۲: انتخابِ صنف — اختیاری و رد-شدنی، اما فقط یک‌بار قابلِ نصب
    (``apps.catalog.services.industry_template_service``، ADR-25). اگر
    Store از قبل یک قالب نصب کرده، این مرحله فقط اطلاعِ همان نصب را نشان
    می‌دهد؛ هرگز دوباره نصب صدا زده نمی‌شود (idempotent-safe در برابرِ
    GET/POST مکرر یا دکمه‌ی back مرورگر)."""
    from apps.catalog.models import StoreIndustryInstallation
    from apps.catalog.services.industry_template_service import IndustryInstallationError, install_industry_template

    store = _get_owned_store_or_404(request, store_public_id)
    installation = StoreIndustryInstallation.objects.select_related("industry_template").filter(store=store).first()
    templates = provisioning_service.latest_offerable_industry_templates()
    selected_template_id = ""
    confirm_error = False

    if request.method == "POST":
        # AUTH-001: EVERY mutating POST path through this step (installing a
        # template, skipping, or — when a template is already installed —
        # advancing the onboarding stage) requires the canonical
        # SETTINGS_MANAGE permission, checked once before any persistent
        # mutation, regardless of whether an installation already exists.
        # This is the same gate the Merchant Admin ``settings_industry_install``
        # view uses.
        if not portal_action_allowed(request, store, SETTINGS_MANAGE):
            return portal_permission_denied(request)

    if request.method == "POST" and installation is None:
        action = request.POST.get("action")
        if action == "skip":
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
            return redirect("portal:onboarding-template", store_public_id=store.public_id)

        form = OnboardingIndustryForm(request.POST)
        valid = form.is_valid()
        template_id = form.cleaned_data["industry_template_id"] if valid else None
        if not template_id:
            messages.error(request, "ابتدا یک صنف را انتخاب کنید؛ یا اگر صنفِ شما در فهرست نیست، این مرحله را رد کنید.")
        else:
            selected_template_id = str(template_id)
            if not form.cleaned_data["confirm_industry_install"]:
                # سمتِ سرور مرجعِ تأیید است: بدونِ تأییدِ صریحِ «نصبِ یک‌بارمصرف» هیچ نصبی انجام نمی‌شود
                # (دکمه‌ی غیرفعال در JS فقط تجربه‌ی کاربری است).
                confirm_error = True
                messages.error(request, INDUSTRY_CONFIRM_REQUIRED_MESSAGE)
            else:
                template = IndustryTemplate.objects.filter(pk=template_id).first()
                if template is None or not template.is_offerable_for_new_installation:
                    # شناسه‌ی جعلی/منسوخ/«نیازمند بازبینی»: هرگز نصب نمی‌شود
                    # (``install_industry_template`` هم همین را تضمین می‌کند)؛ پیامِ
                    # دوستانه به‌جایِ ۴۰۴ تا مالک بتواند صنفِ دیگری انتخاب یا رد کند.
                    messages.error(request, "این صنف در حال حاضر برای نصب در دسترس نیست؛ صنفِ دیگری انتخاب کنید یا این مرحله را رد کنید.")
                else:
                    try:
                        install_industry_template(store, template)
                    except IndustryInstallationError as exc:
                        if StoreIndustryInstallation.objects.filter(store=store).exists():
                            # دابل‌کلیک/درخواستِ هم‌زمان: نصبِ اول موفق بوده؛ خطا نشان نده، فقط جلو ببر.
                            _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
                            return redirect("portal:onboarding-template", store_public_id=store.public_id)
                        messages.error(request, str(exc))
                    else:
                        _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
                        return redirect("portal:onboarding-template", store_public_id=store.public_id)
    elif request.method == "POST":
        # از قبل نصب‌شده — POST دیگری اینجا معنایی ندارد جز عبور به مرحله‌ی بعد.
        _advance_onboarding_stage(store, completed=Store.OnboardingStage.INDUSTRY)
        return redirect("portal:onboarding-template", store_public_id=store.public_id)

    template_cards = template_summary_service.attach_summaries(templates)
    installed_summary = (
        template_summary_service.summarize_template(installation.industry_template) if installation else None
    )
    return render(request, "portal/app/onboarding_industry.html", {
        **_onboarding_shell_context(store, Store.OnboardingStage.INDUSTRY),
        "template_cards": template_cards, "installation": installation, "installed_summary": installed_summary,
        "selected_template_id": selected_template_id, "confirm_error": confirm_error,
        "industry_sector_tabs": _sector_tabs_for(template_cards),
    })


@owner_required
def onboarding_template(request, store_public_id):
    """مرحله‌ی «قالب فروشگاه»: انتخابِ قالبِ آمادهٔ ظاهریِ فروشگاه (Ready Template) — الزامی و بدونِ رد کردن.

    کاتالوگ فقط همان ۵۰ قالبِ رسمیِ Storefront Builder است
    (``layout_preset_registry.list_ready_templates()``)، و کارت‌ها از همان projectionِ مشترکِ
    گالریِ مرچنت (``ready_template_card_service``) می‌آیند — نه کاتالوگ/تصویرِ دومی. POST فقط
    ``template_key`` را می‌پذیرد؛ نسخه/ظاهر/پالت/مانیفست همیشه سمتِ سرور از کاتالوگِ کانونی
    resolve می‌شوند و اعمال کاملاً توسطِ سرویس‌هایِ Storefront Builder انجام می‌شود (هیچ منطقِ
    اعمالِ قالب در پرتال نیست). GET هیچ نوشتنی ندارد (حتی Draft نمی‌سازد)."""
    store = _get_owned_store_or_404(request, store_public_id)
    if store.onboarding_stage == Store.OnboardingStage.DONE or store.onboarding_completed_at:
        # فروشگاهِ منتشرشده هرگز از این مسیر دوباره قالب عوض نمی‌کند؛ تغییرِ قالب در Storefront Builder است.
        return redirect("portal:store-created", store_public_id=store.public_id)

    error = None
    if request.method == "POST":
        if not portal_action_allowed(request, store, SETTINGS_MANAGE):
            return portal_permission_denied(request)
        if request.POST.get("action") == "keep_current":
            # Zero-mutation advance: only valid when the Store REALLY carries a valid
            # applied Ready Template (read from the Draft/Published provenance, never from
            # the client). No select/apply/switch is called, so the Storefront Draft, its
            # history and its revision stay untouched; only the wizard stage moves.
            if store_template_service.get_applied_template(store) is None:
                error = "فروشگاهِ شما هنوز قالبِ آماده‌ای ندارد؛ یکی از قالب‌هایِ فهرست را انتخاب کنید."
                messages.error(request, error)
            else:
                _advance_onboarding_stage(store, completed=Store.OnboardingStage.TEMPLATE)
                return redirect("portal:onboarding-branding", store_public_id=store.public_id)
        else:
            try:
                store_template_service.select_ready_template(
                    store=store, actor=request.user, template_key=request.POST.get("template_key"),
                )
            except store_template_service.ReadyTemplateSelectionError as exc:
                error = str(exc)
                messages.error(request, error)
            except RateLimitExceeded:
                error = "تعدادِ تغییرِ قالب در این بازه بیش از حدِ مجاز است؛ کمی بعد دوباره تلاش کنید."
                messages.error(request, error)
            else:
                _advance_onboarding_stage(store, completed=Store.OnboardingStage.TEMPLATE)
                return redirect("portal:onboarding-branding", store_public_id=store.public_id)

    applied = store_template_service.get_applied_template(store)
    cards = ready_template_card_service.build_ready_template_cards(
        None,
        current_template_key=applied.key if applied else None,
        current_template_version=applied.version if applied else None,
    )
    # A gallery card is "selected" only by an explicit choice or when it is the EXACT applied
    # (key AND version) template. A Store on a historical version of a key never gets the latest
    # same-key card pre-selected — that would let "Continue" silently upgrade it.
    exact_current = next((card["preset"].key for card in cards if card["is_current"]), "")
    selected_key = request.POST.get("template_key", "") if error else exact_current
    return render(request, "portal/app/onboarding_template.html", {
        **_onboarding_shell_context(store, Store.OnboardingStage.TEMPLATE, applied_template=applied),
        "template_cards": cards, "applied_template": applied, "selected_key": selected_key,
        "applied_is_older_version": bool(applied and not applied.is_current_version),
    })


@owner_required
def onboarding_branding(request, store_public_id):
    """مرحله‌ی ۳: هویتِ بصری — فقط لوگو (اختیاری، رد-شدنی). انتخابِ رنگ از
    این مرحله حذف شده؛ ``ShopSettings.primary_color``/``accent_color`` از
    قبل مقادیرِ پیش‌فرضِ معتبر دارند (``provision_for``) و هر زمان از
    Storefront Builder/پنلِ مدیریت قابلِ‌تغییرند."""
    from apps.core.models import ShopSettings

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)

    if request.method == "POST":
        # AUTH-001: mutating branding (ShopSettings.logo) or advancing the
        # onboarding stage requires the canonical SETTINGS_MANAGE permission —
        # the same gate the Merchant Admin ``settings_appearance`` view uses.
        if not portal_action_allowed(request, store, SETTINGS_MANAGE):
            return portal_permission_denied(request)
        if request.POST.get("action") == "skip":
            _advance_onboarding_stage(store, completed=Store.OnboardingStage.BRANDING)
            return redirect("portal:onboarding-review", store_public_id=store.public_id)

        form = OnboardingBrandingForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("logo"):
                shop_settings.logo = data["logo"]
            try:
                shop_settings.full_clean()
            except ValidationError as exc:
                for field, errs in exc.message_dict.items():
                    for err in errs:
                        form.add_error(field if field in form.fields else None, err)
            else:
                shop_settings.save()
                _advance_onboarding_stage(store, completed=Store.OnboardingStage.BRANDING)
                return redirect("portal:onboarding-review", store_public_id=store.public_id)
    else:
        form = OnboardingBrandingForm()

    return render(request, "portal/app/onboarding_branding.html", {
        **_onboarding_shell_context(store, Store.OnboardingStage.BRANDING),
        "form": form, "shop_settings": shop_settings,
    })


@owner_required
def onboarding_review(request, store_public_id):
    """مرحله‌ی ۴ (نهایی): بازبینی و انتشار. تنها همین POST است که
    ``Store.onboarding_completed_at`` را مقداردهی می‌کند — پیش از آن،
    فروشگاه برای بازدیدکنندهٔ ناشناس همیشه خصوصی می‌ماند (Section 6)."""
    from apps.core.models import ShopSettings
    from apps.catalog.models import StoreIndustryInstallation

    store = _get_owned_store_or_404(request, store_public_id)
    shop_settings = ShopSettings.load(store=store)
    installation = StoreIndustryInstallation.objects.select_related("industry_template").filter(store=store).first()
    trial_domain = store.domains.filter(is_primary=True).first()

    if request.method == "POST":
        # AUTH-001: publishing the store (completing onboarding) is a
        # store-level configuration mutation and requires the canonical
        # SETTINGS_MANAGE permission, not merely an ACTIVE membership.
        if not portal_action_allowed(request, store, SETTINGS_MANAGE):
            return portal_permission_denied(request)
        # One transaction: publish the Storefront Draft through the canonical layout service, and only
        # then mark onboarding complete. Idempotent (an already-completed Store is a no-op: no second
        # publish, the first completion timestamp is preserved).
        try:
            outcome = onboarding_publish_service.complete_onboarding(store=store, actor=request.user)
        except onboarding_publish_service.OnboardingPublishError as exc:
            messages.error(request, str(exc))
            if exc.code in ("no_template", "no_draft"):
                return redirect("portal:onboarding-template", store_public_id=store.public_id)
            return redirect("portal:onboarding-review", store_public_id=store.public_id)
        if not outcome.already_completed:
            messages.success(request, "فروشگاه شما منتشر شد!")
        return redirect("portal:store-created", store_public_id=store.public_id)

    installed_summary = (
        template_summary_service.summarize_template(installation.industry_template) if installation else None
    )
    applied = store_template_service.get_applied_template(store)
    template_card = None
    if applied is not None:
        template_card = ready_template_card_service.build_ready_template_card(None, applied.preset, is_current=True)
    return render(request, "portal/app/onboarding_review.html", {
        **_onboarding_shell_context(store, Store.OnboardingStage.REVIEW, applied_template=applied),
        "shop_settings": shop_settings, "installation": installation, "installed_summary": installed_summary,
        "trial_domain": trial_domain, "applied_template": applied, "template_card": template_card,
        **_publication_context(store),
    })


@owner_required
def store_created(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    trial_domain = store.domains.filter(is_primary=True).first()
    if trial_domain is None:
        raise Http404
    return render(request, "portal/app/store_created.html", {
        "store": store, "trial_domain": trial_domain,
        "onboarding_complete": bool(store.onboarding_completed_at), **_publication_context(store),
        "onboarding_resume_url": reverse("portal:onboarding", kwargs={"store_public_id": store.public_id}),
    })


# ---------------------------------------------------------------------------
# Platform billing — subscription purchase (Section 8/9)
# ---------------------------------------------------------------------------
#
# Consumes the pre-existing, mature apps.billing domain (StoreBillingAccount/
# SubscriptionInvoice/SubscriptionPaymentAttempt, plan_change_billing_service,
# payment_flow_service, the provider abstraction) exactly the way apps.
# dashboard's Merchant Admin billing views already do — the portal is a
# second *consumer* of that one billing system, never a parallel one
# (technical-consolidation pass; see ADR-105/ADR-106).
#
# A Store's very first paid purchase is modeled as an "upgrade" out of its
# free trial plan_version via plan_change_billing_service.start_plan_change
# — the same mechanism Merchant Admin plan changes use. The only registered
# payment provider is "manual" (apps.billing.providers.manual.ManualProvider):
# it never auto-succeeds — real confirmation is always either a signed
# provider webhook (apps.billing:webhook) or an explicit Platform Admin
# action (confirmation_service.mark_invoice_paid_manually), so this checkout
# view only ever creates the invoice/attempt and shows the resulting pending/
# paid/failed state — it can never activate anything by itself (browser
# return is never proof of payment).


@owner_required
def billing_plans(request, store_public_id):
    """فهرستِ پلن‌هایِ پولیِ قابلِ‌خرید برایِ این Store — فقط نسخه‌هایِ
    منتشرشده و پولی (Section 9)."""
    store = _get_owned_store_or_404(request, store_public_id)
    current_subscription = ent.get_current_subscription(store)

    offerable_versions = []
    for plan in Plan.objects.filter(is_active=True, is_publicly_selectable=True).order_by("display_order"):
        version = (
            plan.versions.filter(status=PlanVersion.Status.PUBLISHED)
            .exclude(billing_interval=PlanVersion.BillingInterval.NONE)
            .filter(display_price__gt=0)
            .order_by("-version_number")
            .first()
        )
        if version is not None:
            offerable_versions.append(version)

    return render(request, "portal/app/billing_plans.html", {
        "store": store, "plan_versions": offerable_versions, "current_subscription": current_subscription,
    })


_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE = "subscription_purchase_confirm"
_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY = "portal_pending_purchase_plan_version_id"


def _start_purchase(request, *, store, plan_version):
    """هسته‌ی مشترکِ خرید — چه بلافاصله (وقتی نیازی به تأییدِ گام‌دوم نیست)
    چه پس از تأییدِ موفقِ OTP گام‌دوم فراخوانی می‌شود. از همان
    ``plan_change_billing_service``ای عبور می‌کند که تغییرِ پلنِ Merchant
    Admin هم از آن استفاده می‌کند — اولین خریدِ یک Store چیزی نیست جز
    «ارتقا» از نسخه‌ی پلنِ آزمایشیِ رایگان."""
    current = ent.get_current_subscription(store)
    if current is None:
        messages.error(request, "این فروشگاه اشتراکِ جاری ندارد؛ امکانِ خرید نیست.")
        return redirect("portal:billing-plans", store_public_id=store.public_id)

    token = plan_change_service._preview_token(current, plan_version)
    try:
        kind, result = plan_change_billing_service.start_plan_change(
            current, plan_version, preview_token=token, actor=request.user,
        )
    except (plan_change_service.PlanChangeError, plan_change_billing_service.PlanChangeBillingError) as exc:
        # SUB-001 Repair 3: ``start_plan_change`` now also raises
        # ``PlanChangeBillingError`` when a competing, unresolved
        # PLAN_CHANGE invoice already exists for this subscription (the
        # financial invariant added in this repair) — this is a normal,
        # user-facing rejection, not a 500.
        messages.error(request, str(exc))
        return redirect("portal:billing-plans", store_public_id=store.public_id)

    if kind == "scheduled":
        messages.success(request, "تغییرِ پلن برایِ دوره‌ی بعد زمان‌بندی شد؛ نیازی به پرداخت نیست.")
        return redirect("portal:billing-plans", store_public_id=store.public_id)

    invoice = result
    return_url = request.build_absolute_uri(reverse("portal:billing-plans", args=[store.public_id]))
    try:
        attempt, _session = payment_flow_service.start_payment(invoice, return_url=return_url, actor=request.user)
    except payment_flow_service.PaymentFlowError as exc:
        messages.error(request, str(exc))
        return redirect("portal:billing-plans", store_public_id=store.public_id)
    return redirect("portal:billing-return", store_public_id=store.public_id, attempt_public_token=attempt.public_token)


@owner_required
@require_POST
def billing_checkout(request, store_public_id, plan_version_id):
    """فاکتور می‌سازد و تلاشِ پرداخت را شروع می‌کند — مگر اینکه سیاستِ
    پلتفرم برایِ ``subscription_purchase_confirm`` تأییدِ گام‌دومِ OTP
    بخواهد (Section 10) و این نشست هنوز آن را برایِ همین Store تأیید
    نکرده باشد، که در آن صورت ابتدا به مرحله‌ی تأییدِ کد هدایت می‌شود."""
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: reaching the subscription-purchase mutation requires the
    # canonical plan-change decision permission AND the billing-payment
    # authority — checked BEFORE any Step-Up challenge, invoice, scheduled
    # plan-change, or payment attempt. Step-Up (identity re-proof) is an
    # additional layer, never a substitute for action authorization.
    if not portal_actions_allowed(request, store, SUBSCRIPTION_CHANGE, BILLING_PAYMENT_MANAGE):
        return portal_permission_denied(request)
    plan_version = get_object_or_404(PlanVersion, pk=plan_version_id, status=PlanVersion.Status.PUBLISHED)

    target = str(store.public_id)
    if step_up_service.is_step_up_required(_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE) and not step_up_service.is_verified(
        request, action=_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE, target=target,
    ):
        phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
        if not phone:
            messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
            return redirect("portal:billing-plans", store_public_id=store.public_id)
        try:
            step_up_service.begin_challenge(
                request, action=_STEP_UP_ACTION_SUBSCRIPTION_PURCHASE, target=target, phone=phone,
                message="کدِ تأییدِ خریدِ اشتراک در راستیسی: {code}",
                client_ip=get_client_ip_bucket(request),
            )
        except step_up_service.OtpRateLimitError as exc:
            messages.error(request, str(exc))
            return redirect("portal:billing-plans", store_public_id=store.public_id)
        request.session[_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY] = plan_version.pk
        return redirect("portal:billing-step-up", store_public_id=store.public_id)

    return _start_purchase(request, store=store, plan_version=plan_version)


@owner_required
def billing_step_up_verify(request, store_public_id):
    """صفحه‌ی تأییدِ کدِ گام‌دوم پیش از ادامه‌ی خرید (Section 10). فقط برایِ
    چالشی که خودِ ``billing_checkout`` در همین نشست ایجاد کرده معنا دارد —
    شناسه‌ی نسخه‌ی پلن از session خوانده می‌شود، نه از ورودیِ کاربر."""
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: re-check action authorization on the Step-Up continuation —
    # a user who lost (or never had) the permission must not complete the
    # purchase merely by proving identity, even if a challenge exists.
    if not portal_actions_allowed(request, store, SUBSCRIPTION_CHANGE, BILLING_PAYMENT_MANAGE):
        return portal_permission_denied(request)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:billing-plans", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            plan_version_id = request.session.pop(_SESSION_PENDING_PURCHASE_PLAN_VERSION_KEY, None)
            plan_version = PlanVersion.objects.filter(pk=plan_version_id).first() if plan_version_id else None
            if plan_version is None:
                messages.error(request, "درخواستِ خرید یافت نشد؛ دوباره تلاش کنید.")
                return redirect("portal:billing-plans", store_public_id=store.public_id)
            return _start_purchase(request, store=store, plan_version=plan_version)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
def billing_return(request, store_public_id, attempt_public_token):
    """وضعیتِ فعلیِ یک تلاشِ پرداخت را نشان می‌دهد — همیشه از رکوردِ
    سمتِ سرور خوانده می‌شود، هرگز از بازگشتِ مرورگر؛ تأییدِ واقعی فقط از
    راهِ Webhookِ امضاشده یا اقدامِ صریحِ مدیرِ پلتفرم انجام می‌شود (نگاه
    کنید به ``apps.billing.services.payment_flow_service``)."""
    store = _get_owned_store_or_404(request, store_public_id)
    attempt = get_object_or_404(
        SubscriptionPaymentAttempt.objects.select_related("invoice"),
        public_token=attempt_public_token, store=store,
    )
    return render(request, "portal/app/billing_return.html", {
        "store": store, "attempt": attempt, "invoice": attempt.invoice,
    })


# ---------------------------------------------------------------------------
# Permanent Store handle claim (Section 11)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_HANDLE_CLAIM = "permanent_handle_claim"
_SESSION_PENDING_HANDLE_LABEL_KEY = "portal_pending_handle_label"


@owner_required
def claim_handle(request, store_public_id):
    """صفحه‌ی ثبتِ نامِ دائمی — فقط برایِ فروشگاهی که اشتراکِ پولیِ فعال
    دارد و هنوز نامِ دائمی ثبت نکرده (Section 11). ثبت غیرقابلِ بازگشت
    است — این هشدار در قالب هم آشکارا نمایش داده می‌شود."""
    store = _get_owned_store_or_404(request, store_public_id)
    already_claimed = handle_service.has_claimed_handle(store)
    current_subscription = store.subscriptions.filter(is_current=True).first()
    can_claim = (
        not already_claimed
        and current_subscription is not None
        and current_subscription.status == StoreSubscription.Status.ACTIVE
    )

    if request.method == "POST" and can_claim:
        # AUTH-001: claiming the permanent handle mutates Store-scoped domain
        # state and requires the canonical DOMAIN_MANAGE permission — checked
        # before any Step-Up challenge or handle_service mutation.
        if not portal_action_allowed(request, store, DOMAIN_MANAGE):
            return portal_permission_denied(request)
        label = (request.POST.get("label") or "").strip()
        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_HANDLE_CLAIM) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_HANDLE_CLAIM, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_HANDLE_CLAIM, target=target, phone=phone,
                    message="کدِ تأییدِ ثبتِ نامِ دائمیِ فروشگاه: {code}",
                    client_ip=get_client_ip_bucket(request),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_HANDLE_LABEL_KEY] = label
            return redirect("portal:claim-handle-step-up", store_public_id=store.public_id)

        try:
            handle_service.claim_platform_handle(store=store, label=label, actor=request.user)
        except handle_service.HandleError as exc:
            messages.error(request, str(exc))
            return redirect("portal:claim-handle", store_public_id=store.public_id)
        messages.success(request, "نامِ دائمیِ فروشگاه با موفقیت ثبت شد.")
        return redirect("portal:claim-handle", store_public_id=store.public_id)

    claimed_domain = StoreDomain.objects.filter(
        store=store, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN, is_primary=True,
    ).first()
    return render(request, "portal/app/claim_handle.html", {
        "store": store, "already_claimed": already_claimed, "can_claim": can_claim,
        "claimed_domain": claimed_domain, "current_subscription": current_subscription,
    })


@owner_required
def claim_handle_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: re-check action authorization on the Step-Up continuation.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:claim-handle", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            label = request.session.pop(_SESSION_PENDING_HANDLE_LABEL_KEY, "")
            try:
                handle_service.claim_platform_handle(store=store, label=label, actor=request.user)
            except handle_service.HandleError as exc:
                messages.error(request, str(exc))
                return redirect("portal:claim-handle", store_public_id=store.public_id)
            messages.success(request, "نامِ دائمیِ فروشگاه با موفقیت ثبت شد.")
            return redirect("portal:claim-handle", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


# ---------------------------------------------------------------------------
# Custom domain — DNS verification and activation (Section 12)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_DOMAIN_ACTIVATE = "custom_domain_activate"
_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY = "portal_pending_activate_domain_id"


def _domains_view_context(store):
    domains = store.domains.filter(domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN).order_by("-created_at")
    rows = []
    for domain in domains:
        record_name = domain_verification_service.verification_record_name(domain.hostname) if domain.verification_token else ""
        expected_value = (
            f"{domain_verification_service.VERIFICATION_VALUE_PREFIX}{domain.verification_token}"
            if domain.verification_token else ""
        )
        rows.append({
            "domain": domain,
            "record_name": record_name,
            "expected_value": expected_value,
            "connection": domain_verification_service.custom_domain_connection_instructions(
                domain.hostname
            ),
        })
    return rows


@owner_required
def custom_domains(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)

    if request.method == "POST" and request.POST.get("action") == "add":
        # AUTH-001: adding a custom domain mutates Store-scoped domain state
        # and requires the canonical DOMAIN_MANAGE permission.
        if not portal_action_allowed(request, store, DOMAIN_MANAGE):
            return portal_permission_denied(request)
        hostname = (request.POST.get("hostname") or "").strip()
        try:
            domain_verification_service.request_custom_domain(store=store, hostname=hostname, actor=request.user)
        except domain_verification_service.DomainVerificationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "دامنه ثبت شد؛ اکنون می‌توانید تأییدِ DNS را شروع کنید.")
            typo_suggestion = _custom_domain_typo_suggestion(store=store, hostname=hostname)
            if typo_suggestion:
                messages.warning(
                    request,
                    f"⚠️ این دامنه شبیهِ «{typo_suggestion}» به نظر می‌رسد — اگر اشتباهِ تایپی "
                    "بوده، دامنه‌ی درست را جداگانه اضافه کنید (هرگز خودکار اصلاح نمی‌شود).",
                )
        return redirect("portal:custom-domains", store_public_id=store.public_id)

    return render(request, "portal/app/custom_domains.html", {
        "store": store, "rows": _domains_view_context(store),
    })


def _custom_domain_typo_suggestion(*, store, hostname: str):
    """پیشنهادِ اشتباهِ تایپیِ محتمل — بدونِ استثنا برایِ فرمت‌های نامعتبر
    (خودِ ``request_custom_domain`` قبلاً این حالت را رد کرده)."""
    from django.core.exceptions import ValidationError

    from apps.stores.hostnames import normalize_hostname
    from apps.stores.services.domain_typo_service import suggest_domain_typo

    try:
        normalized = normalize_hostname(hostname)
    except ValidationError:
        return None
    return suggest_domain_typo(store=store, hostname=normalized)


@owner_required
@require_POST
def custom_domain_begin_verify(request, store_public_id, domain_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: DNS verification mutates domain verification state — DOMAIN_MANAGE.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    try:
        domain_verification_service.begin_dns_verification(domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دستورالعملِ تأییدِ DNS آماده شد؛ رکوردِ TXT زیر را در DNS دامنه‌تان اضافه کنید.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
@require_POST
def custom_domain_check(request, store_public_id, domain_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: persisting DNS-verification result mutates domain state — DOMAIN_MANAGE.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    try:
        verified = domain_verification_service.check_dns_verification(domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        if verified:
            messages.success(request, "دامنه با موفقیت تأیید شد.")
        else:
            messages.error(request, "رکوردِ TXT هنوز پیدا نشد یا مقدارش درست نیست؛ کمی صبر کنید و دوباره بررسی کنید.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
@require_POST
def custom_domain_final_check(request, store_public_id, domain_id):
    """Run and persist the real A/CNAME + HTTPS readiness checks."""
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: refreshing/persisting readiness mutates domain state — DOMAIN_MANAGE.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    try:
        result = domain_verification_service.refresh_custom_domain_readiness(
            domain=domain, actor=request.user
        )
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        if not result.routing.configured:
            messages.warning(
                request,
                "مقصد اتصال دامنه‌های اختصاصی هنوز در زیرساخت RastiSi پیکربندی نشده است؛ "
                "فعال‌سازی تا تکمیل تنظیمات زیرساخت ممکن نیست.",
            )
        elif not result.routing.connected:
            messages.warning(
                request,
                f"⚠️ رکوردهای A/CNAME دامنه «{domain.hostname}» هنوز به مقصد RastiSi نرسیده‌اند.",
            )
        elif result.tls and result.tls.reachable:
            messages.success(
                request,
                f"✅ DNS و اتصال HTTPS برای «{domain.hostname}» آماده است؛ دامنه قابل فعال‌سازی است.",
            )
        else:
            messages.warning(
                request,
                f"⚠️ DNS دامنه «{domain.hostname}» به RastiSi متصل است، اما HTTPS/TLS هنوز آماده نیست.",
            )
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
@require_POST
def custom_domain_activate(request, store_public_id, domain_id):
    """فعال‌سازیِ دامنه‌ی تأییدشده به‌عنوانِ دامنه‌ی اصلی — پشتِ تأییدِ گام‌دوم
    (Section 10، action=``custom_domain_activate``)، دقیقاً مثلِ الگویِ
    خریدِ اشتراک/ثبتِ نامِ دائمی."""
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: activating a custom domain requires DOMAIN_MANAGE — checked
    # before any Step-Up challenge or activation mutation.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    domain = get_object_or_404(StoreDomain, pk=domain_id, store=store)
    target = str(store.public_id)

    if step_up_service.is_step_up_required(_STEP_UP_ACTION_DOMAIN_ACTIVATE) and not step_up_service.is_verified(
        request, action=_STEP_UP_ACTION_DOMAIN_ACTIVATE, target=target,
    ):
        phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
        if not phone:
            messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        try:
            step_up_service.begin_challenge(
                request, action=_STEP_UP_ACTION_DOMAIN_ACTIVATE, target=target, phone=phone,
                message="کدِ تأییدِ فعال‌سازیِ دامنه‌ی اختصاصی: {code}",
                client_ip=get_client_ip_bucket(request),
            )
        except step_up_service.OtpRateLimitError as exc:
            messages.error(request, str(exc))
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        request.session[_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY] = domain.pk
        return redirect("portal:custom-domain-activate-step-up", store_public_id=store.public_id)

    try:
        domain_verification_service.activate_custom_domain(store=store, domain=domain, actor=request.user)
    except domain_verification_service.DomainVerificationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "دامنه‌ی اختصاصی اکنون دامنه‌ی اصلیِ فروشگاه است.")
    return redirect("portal:custom-domains", store_public_id=store.public_id)


@owner_required
def custom_domain_activate_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: re-check action authorization on the Step-Up continuation.
    if not portal_action_allowed(request, store, DOMAIN_MANAGE):
        return portal_permission_denied(request)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:custom-domains", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            domain_id = request.session.pop(_SESSION_PENDING_ACTIVATE_DOMAIN_ID_KEY, None)
            domain = StoreDomain.objects.filter(pk=domain_id, store=store).first() if domain_id else None
            if domain is None:
                messages.error(request, "درخواستِ فعال‌سازی یافت نشد؛ دوباره تلاش کنید.")
                return redirect("portal:custom-domains", store_public_id=store.public_id)
            try:
                domain_verification_service.activate_custom_domain(store=store, domain=domain, actor=request.user)
            except domain_verification_service.DomainVerificationError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "دامنه‌ی اختصاصی اکنون دامنه‌ی اصلیِ فروشگاه است.")
            return redirect("portal:custom-domains", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


# ---------------------------------------------------------------------------
# Store deletion — soft, typed-confirmation, step-up gated (Section 14)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_STORE_DELETE = "store_delete"
_SESSION_PENDING_DELETE_CONFIRMATION_KEY = "portal_pending_delete_confirmation"


@owner_required
def request_store_deletion(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)

    if request.method == "POST":
        # AUTH-001: requesting store deletion requires the canonical
        # STORE_DELETE permission (Owner-only) — checked before any Step-Up
        # challenge or deletion_service mutation.
        if not portal_action_allowed(request, store, STORE_DELETE):
            return portal_permission_denied(request)
        typed_confirmation = (request.POST.get("typed_confirmation") or "").strip()
        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_STORE_DELETE) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_STORE_DELETE, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:request-store-deletion", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_STORE_DELETE, target=target, phone=phone,
                    message="کدِ تأییدِ حذفِ فروشگاه: {code}",
                    client_ip=get_client_ip_bucket(request),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:request-store-deletion", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_DELETE_CONFIRMATION_KEY] = typed_confirmation
            return redirect("portal:store-deletion-step-up", store_public_id=store.public_id)

        try:
            deletion_service.request_deletion(store=store, actor=request.user, typed_confirmation=typed_confirmation)
        except deletion_service.DeletionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "درخواستِ حذفِ فروشگاه ثبت شد.")
        return redirect("portal:request-store-deletion", store_public_id=store.public_id)

    return render(request, "portal/app/request_store_deletion.html", {"store": store})


@owner_required
def store_deletion_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: re-check action authorization on the Step-Up continuation —
    # identity re-proof must never complete a deletion the role cannot perform.
    if not portal_action_allowed(request, store, STORE_DELETE):
        return portal_permission_denied(request)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:request-store-deletion", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            typed_confirmation = request.session.pop(_SESSION_PENDING_DELETE_CONFIRMATION_KEY, "")
            try:
                deletion_service.request_deletion(
                    store=store, actor=request.user, typed_confirmation=typed_confirmation,
                )
            except deletion_service.DeletionError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "درخواستِ حذفِ فروشگاه ثبت شد.")
            return redirect("portal:request-store-deletion", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
@require_POST
def cancel_store_deletion(request, store_public_id):
    """لغوِ درخواستِ حذف — یک اقدامِ ایمن است (بازگرداندن، نه ایجادِ خطر)،
    پس نیازِ تأییدِ گام‌دومِ OTP ندارد."""
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: cancelling a deletion request mutates the store's deletion
    # lifecycle state and is part of the STORE_DELETE authorization surface.
    if not portal_action_allowed(request, store, STORE_DELETE):
        return portal_permission_denied(request)
    try:
        deletion_service.cancel_deletion(store=store, actor=request.user)
    except deletion_service.DeletionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "درخواستِ حذفِ فروشگاه لغو شد.")
    return redirect("portal:request-store-deletion", store_public_id=store.public_id)


# ---------------------------------------------------------------------------
# Ownership transfer — two-party OTP-gated (Section 15)
# ---------------------------------------------------------------------------

_STEP_UP_ACTION_OWNERSHIP_TRANSFER = "store_ownership_transfer"
_SESSION_PENDING_TRANSFER_PHONE_KEY = "portal_pending_transfer_phone"


@owner_required
def initiate_ownership_transfer(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    pending_transfer = store.ownership_transfers.filter(status=StoreOwnershipTransfer.Status.PENDING).first()

    if request.method == "POST" and pending_transfer is None:
        # AUTH-001: initiating an ownership transfer controls StoreMembership
        # OWNER truth and requires the canonical STAFF_MANAGE permission
        # (Owner-only) — checked before any Step-Up challenge or transfer
        # mutation. The ownership_transfer_service.initiate_transfer business
        # invariant (OWNER-membership validation) is preserved unchanged.
        if not portal_action_allowed(request, store, STAFF_MANAGE):
            return portal_permission_denied(request)
        target_phone_raw = (request.POST.get("target_phone") or "").strip()
        try:
            target_phone = normalize_iranian_phone(target_phone_raw)
        except InvalidPhoneError as exc:
            messages.error(request, str(exc.messages[0] if exc.messages else exc))
            return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

        target = str(store.public_id)
        if step_up_service.is_step_up_required(_STEP_UP_ACTION_OWNERSHIP_TRANSFER) and not step_up_service.is_verified(
            request, action=_STEP_UP_ACTION_OWNERSHIP_TRANSFER, target=target,
        ):
            phone = getattr(getattr(request.user, "owner_profile", None), "phone", None)
            if not phone:
                messages.error(request, "این عملیات نیاز به شماره موبایلِ ثبت‌شده در حساب دارد.")
                return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
            try:
                step_up_service.begin_challenge(
                    request, action=_STEP_UP_ACTION_OWNERSHIP_TRANSFER, target=target, phone=phone,
                    message="کدِ تأییدِ انتقالِ مالکیتِ فروشگاه: {code}",
                    client_ip=get_client_ip_bucket(request),
                )
            except step_up_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
                return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
            request.session[_SESSION_PENDING_TRANSFER_PHONE_KEY] = target_phone
            return redirect("portal:ownership-transfer-step-up", store_public_id=store.public_id)

        try:
            ownership_transfer_service.initiate_transfer(
                store=store, initiated_by=request.user, target_phone=target_phone,
            )
        except ownership_transfer_service.OwnershipTransferError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "درخواستِ انتقالِ مالکیت ثبت شد؛ تا پذیرشِ طرفِ مقابل در انتظار می‌ماند.")
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

    return render(request, "portal/app/ownership_transfer.html", {
        "store": store, "pending_transfer": pending_transfer,
    })


@owner_required
def ownership_transfer_step_up(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: re-check action authorization on the Step-Up continuation —
    # identity re-proof must never complete a transfer the role cannot perform.
    if not portal_action_allowed(request, store, STAFF_MANAGE):
        return portal_permission_denied(request)
    pending = step_up_service.pending_challenge(request)
    if not pending or pending.get("target") != str(store.public_id):
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)

    if request.method == "POST":
        code = request.POST.get("code", "")
        if step_up_service.confirm_challenge(request, code=code):
            target_phone = request.session.pop(_SESSION_PENDING_TRANSFER_PHONE_KEY, "")
            try:
                ownership_transfer_service.initiate_transfer(
                    store=store, initiated_by=request.user, target_phone=target_phone,
                )
            except ownership_transfer_service.OwnershipTransferError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "درخواستِ انتقالِ مالکیت ثبت شد؛ تا پذیرشِ طرفِ مقابل در انتظار می‌ماند.")
            return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
        messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/app/step_up_verify.html", {"store": store})


@owner_required
@require_POST
def cancel_ownership_transfer(request, store_public_id):
    store = _get_owned_store_or_404(request, store_public_id)
    # AUTH-001: cancelling a pending transfer is part of the ownership-
    # transfer authorization surface and requires STAFF_MANAGE.
    if not portal_action_allowed(request, store, STAFF_MANAGE):
        return portal_permission_denied(request)
    transfer = store.ownership_transfers.filter(status=StoreOwnershipTransfer.Status.PENDING).first()
    if transfer is None:
        messages.error(request, "انتقالِ در-انتظاری برایِ لغو وجود ندارد.")
        return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)
    try:
        ownership_transfer_service.cancel_transfer(transfer=transfer, actor=request.user)
    except ownership_transfer_service.OwnershipTransferError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "درخواستِ انتقالِ مالکیت لغو شد.")
    return redirect("portal:initiate-ownership-transfer", store_public_id=store.public_id)


def accept_ownership_transfer(request, token):
    """صفحه‌ی عمومیِ پذیرشِ انتقال — طرفِ مقابل ممکن است اصلاً هنوز حسابی
    نداشته باشد، پس ``owner_required`` نیست. تنها با OTPِ خودِ
    ``transfer.target_phone`` (نه نشستِ مالکِ فعلی) قابلِ پذیرش است."""
    transfer = ownership_transfer_service.get_pending_transfer_by_token(token)
    if transfer is None or transfer.is_expired:
        return render(request, "portal/public/ownership_transfer_accept.html", {"transfer": None}, status=404)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "request_code":
            try:
                owner_otp_service.request_otp(
                    phone=transfer.target_phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP,
                    client_ip=get_client_ip_bucket(request),
                    message="کدِ پذیرشِ مالکیتِ فروشگاه: {code}",
                )
                messages.success(request, "کد ارسال شد.")
            except owner_otp_service.OtpRateLimitError as exc:
                messages.error(request, str(exc))
        elif action == "verify_code":
            code = request.POST.get("code", "")
            ok = owner_otp_service.verify_otp(
                phone=transfer.target_phone, purpose=OwnerOtpChallenge.Purpose.STEP_UP, code=code,
            )
            if ok:
                try:
                    _updated, new_owner = ownership_transfer_service.accept_transfer(transfer=transfer)
                except ownership_transfer_service.OwnershipTransferError as exc:
                    messages.error(request, str(exc))
                else:
                    auth_login(request, new_owner)
                    messages.success(request, "مالکیتِ فروشگاه با موفقیت به شما منتقل شد.")
                    return redirect("portal:app-home")
            else:
                messages.error(request, "کدِ واردشده نادرست یا منقضی است.")

    return render(request, "portal/public/ownership_transfer_accept.html", {"transfer": transfer})


# ---------------------------------------------------------------------------
# In-app notifications (Section 16)
# ---------------------------------------------------------------------------


@owner_required
def notifications_list(request):
    from apps.notifications.models import NotificationOutbox

    notifications = NotificationOutbox.objects.filter(
        recipient_user=request.user, channel=NotificationOutbox.Channel.IN_APP,
    ).order_by("-created_at")[:100]

    if request.method == "POST":
        NotificationOutbox.objects.filter(
            recipient_user=request.user, channel=NotificationOutbox.Channel.IN_APP, read_at__isnull=True,
        ).update(read_at=timezone.now())
        return redirect("portal:notifications")

    return render(request, "portal/app/notifications.html", {"notifications": notifications})
