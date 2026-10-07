"""لایه‌ی سرویس کد یکبار مصرف (OTP) — تولید، محدودیت نرخ، و تأیید.

مطابق خواسته: انقضای ۲ دقیقه، حداکثر ۳ درخواست در ۱۰ دقیقه برای هر شماره
(تا اسپم/حدس‌زدن ممکن نباشد)، حداکثر تعداد درخواست به‌ازایِ IP (تا یک
مهاجم با شماره‌های زیاد نتواند از یک IP واحد پیامک‌بمب‌گذاری کند — همان
محافظتی که ``apps.portal.services.owner_otp_service`` از قبل داشت)، و
محدودیت تعداد تلاش تأیید برای هر کد.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.core.services.rate_limit import (
    UNAVAILABLE_MESSAGE,
    RateLimitExceeded,
    RateLimitUnavailable,
    enforce_rate_limit,
)

from ..events import SmsEvent
from ..models import OtpCode
from .sms_service import send_event_sms

OTP_LENGTH = 6
OTP_TTL_SECONDS = 120
MAX_REQUESTS_PER_WINDOW = 3
REQUEST_WINDOW_SECONDS = 600
MAX_VERIFY_ATTEMPTS = 5
IP_MAX_REQUESTS = 10
IP_REQUEST_WINDOW_SECONDS = 600


class OtpRateLimitError(Exception):
    """تعداد درخواست کد برای این شماره یا IP در بازه‌ی زمانی اخیر بیش از حد مجاز بوده است."""


class OtpInvalidError(Exception):
    """کد وارد‌شده معتبر/صحیح نیست."""


class OtpDeliveryError(OtpRateLimitError):
    """OTP به دلیل اعتبار/درگاه ارسال نشده است؛ caller همان خطای کنترل‌شده را نشان می‌دهد."""


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def request_otp(phone: str, *, store, ip_address: str) -> OtpCode:
    """کد جدید می‌سازد و پیامک می‌کند؛ اگر تعداد درخواست‌های اخیر (برایِ این
    شماره یا این IP) بیش از حد باشد، هیچ کدِ تازه‌ای ساخته/ارسال نمی‌شود.

    ``store`` الزامی است — همان Store که برای پیامک کد یکبار مصرف استفاده
    می‌شود؛ فراخوان (view) مسئول resolve کردن آن است. ``ip_address`` هم
    الزامی است — فراخوان (view) مسئول استخراجش از request است."""
    try:
        enforce_rate_limit(
            "sms_otp_request_ip", ip_address, max_attempts=IP_MAX_REQUESTS, window_seconds=IP_REQUEST_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise OtpRateLimitError(str(exc)) from exc
    except RateLimitUnavailable as exc:
        # Fail closed: never send an SMS while the shared throttle store is down.
        raise OtpDeliveryError(UNAVAILABLE_MESSAGE) from exc

    window_start = timezone.now() - timedelta(seconds=REQUEST_WINDOW_SECONDS)
    recent_count = OtpCode.objects.filter(phone=phone, created_at__gte=window_start).count()
    if recent_count >= MAX_REQUESTS_PER_WINDOW:
        raise OtpRateLimitError("تعداد درخواست کد بیش از حد مجاز است؛ چند دقیقه‌ی دیگر دوباره تلاش کنید")

    code = _generate_code()
    otp = OtpCode.objects.create(
        phone=phone, code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(seconds=OTP_TTL_SECONDS),
    )
    log = send_event_sms(SmsEvent.OTP, phone, {"otp_code": code, "expire_minutes": "2"}, store=store)
    if log is None or log.status != "sent":
        otp.delete()
        raise OtpDeliveryError(
            log.error_message if log is not None and log.error_message else
            "ارسال کد تأیید انجام نشد؛ لطفاً دوباره تلاش کنید"
        )
    return otp


def verify_otp(phone: str, code: str) -> OtpCode:
    """آخرین کد مصرف‌نشده‌ی این شماره را با کد ورودی مقایسه می‌کند؛ در صورت تأیید، مصرف‌شده علامت می‌زند."""
    otp = OtpCode.objects.filter(phone=phone, is_used=False).order_by("-created_at").first()
    if otp is None:
        raise OtpInvalidError("کدی برای این شماره یافت نشد؛ ابتدا درخواست کد کنید")

    if otp.expires_at < timezone.now():
        raise OtpInvalidError("کد منقضی شده است؛ کد جدید درخواست کنید")

    if otp.attempt_count >= MAX_VERIFY_ATTEMPTS:
        raise OtpInvalidError("تعداد تلاش برای این کد بیش از حد مجاز است؛ کد جدید درخواست کنید")

    otp.attempt_count += 1
    otp.save(update_fields=["attempt_count", "updated_at"])

    if not check_password(code.strip(), otp.code_hash):
        raise OtpInvalidError("کد وارد‌شده صحیح نیست")

    otp.is_used = True
    otp.save(update_fields=["is_used", "updated_at"])
    return otp
