"""امنیتِ حسابِ مشتری: تغییرِ رمز (با رمزِ فعلی) و تعیین/بازنشانیِ رمز با کدِ پیامکیِ همان موبایل.

* حساب‌هایی که هنگامِ تسویه‌حساب ساخته می‌شوند رمزی دارند که مشتری هرگز ندیده است؛ برایِ آن‌ها «رمزِ فعلی» بی‌معناست و احرازِ هویتِ
  مجدد با کدِ یک‌بارمصرفِ همان موبایل انجام می‌شود (همان ``otp_service``: محدودیتِ نرخ، انقضا، حداکثر تلاش، و فرستنده‌ی پیکربندی‌شده‌ی
  فروشگاه — این ماژول خودش هیچ پیامکی را جدا یا مستقیم نمی‌فرستد).
* اعتبارسنجیِ رمز با اعتبارسنج‌هایِ استانداردِ Django؛ رمز هرگز لاگ یا ذخیره‌ی خام نمی‌شود.
* پس از تغییر، نشستِ فعلی معتبر می‌ماند و نشست‌هایِ دیگر باطل می‌شوند (``update_session_auth_hash``)."""

from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit
from apps.sms.services import otp_service

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 600


class PasswordChangeError(Exception):
    """خطای قابل‌نمایش؛ ``errors`` = ``{field: message}`` (کلیدِ ``""`` = خطای کلیِ فرم)."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


def _throttle(action: str, key) -> None:
    try:
        enforce_rate_limit(action, str(key), max_attempts=MAX_ATTEMPTS, window_seconds=WINDOW_SECONDS)
    except RateLimitExceeded as exc:
        raise PasswordChangeError({"": "تعداد تلاش‌ها بیش از حد مجاز است؛ چند دقیقه‌ی دیگر دوباره تلاش کنید."}) from exc
    except RateLimitUnavailable as exc:
        raise PasswordChangeError({"": UNAVAILABLE_MESSAGE}) from exc


def _validate_new(user, new: str, confirm: str) -> None:
    errors: dict[str, str] = {}
    if not new:
        errors["new_password"] = "رمز جدید را وارد کنید."
    else:
        try:
            validate_password(new, user)
        except ValidationError as exc:
            errors["new_password"] = " ".join(exc.messages)
    if new and confirm != new:
        errors["confirm_password"] = "تکرار رمز با رمز جدید یکسان نیست."
    if errors:
        raise PasswordChangeError(errors)


def _apply(request, customer, new: str, store) -> None:
    user = customer.user
    user.set_password(new)
    user.save(update_fields=["password"])
    if request is not None:
        update_session_auth_hash(request, user)
    from apps.notifications.services import business_events

    business_events.account_sensitive_changed(customer, store, "رمز عبور")


def change_password(request, customer, *, current: str, new: str, confirm: str, store) -> None:
    """تغییرِ رمز با رمزِ فعلی. تلاشِ ناموفق شمرده می‌شود (ضدِ حدس‌زدن)."""
    user = customer.user
    _throttle("customer_password_change", user.pk)
    if not current or not user.check_password(current):
        raise PasswordChangeError({"current_password": "رمز فعلی درست نیست."})
    _validate_new(user, new, confirm)
    if user.check_password(new):
        raise PasswordChangeError({"new_password": "رمز جدید باید با رمز فعلی متفاوت باشد."})
    _apply(request, customer, new, store)


def request_password_code(customer, *, store, ip_address: str) -> None:
    """ارسالِ کدِ تأیید به موبایلِ همین حساب (فقط موبایلِ خودِ مشتری؛ هیچ ورودیِ شمارهٔ دلخواهی وجود ندارد)."""
    try:
        otp_service.request_otp(customer.phone, store=store, ip_address=ip_address)
    except otp_service.OtpRateLimitError as exc:  # includes delivery errors (OtpDeliveryError)
        raise PasswordChangeError({"": str(exc)}) from exc


def set_password_with_code(request, customer, *, code: str, new: str, confirm: str, store) -> None:
    """تعیین/بازنشانیِ رمز پس از تأییدِ کدِ پیامکی. اعتبارسنجیِ رمز پیش از مصرفِ کد انجام می‌شود تا کدِ درست بی‌دلیل نسوزد."""
    user = customer.user
    _throttle("customer_password_set", user.pk)
    _validate_new(user, new, confirm)
    try:
        otp_service.verify_otp(customer.phone, (code or "").strip())
    except otp_service.OtpInvalidError as exc:
        raise PasswordChangeError({"code": str(exc)}) from exc
    _apply(request, customer, new, store)
