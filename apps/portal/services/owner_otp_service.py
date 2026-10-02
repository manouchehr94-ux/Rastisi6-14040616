"""صدور/تأییدِ کدِ یکبارمصرفِ ورود و ثبت‌نامِ مالک با موبایل (Section 3).

محدودیت‌ها (مطابق §3.19، و هم‌راستا با ``apps.sms.services.otp_service``ی
موجود برایِ مشتری):
* انقضایِ کوتاه (۲ دقیقه)
* حداکثر تعداد درخواستِ کد در بازه، هم به‌ازایِ شماره هم به‌ازایِ IP
* حداکثر تعداد تلاشِ تأییدِ هر کد
* تک‌مصرفی (replay-proof)
* هرگز کدِ خام لاگ/افشا نمی‌شود؛ فقط هَش ذخیره می‌شود
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.portal.models import OwnerOtpChallenge

from .owner_sms_service import send_platform_otp
from .rate_limit import RateLimitExceeded, enforce_rate_limit

OTP_LENGTH = 6
OTP_TTL_SECONDS = 120
MAX_REQUESTS_PER_PHONE_WINDOW = 3
PHONE_REQUEST_WINDOW_SECONDS = 600
MAX_VERIFY_ATTEMPTS = 5
IP_MAX_REQUESTS = 10
IP_REQUEST_WINDOW_SECONDS = 600


class OtpRateLimitError(Exception):
    """تعداد درخواست/تلاشِ کد برای این شماره یا IP بیش از حد مجاز است."""


class OtpInvalidError(Exception):
    """کدِ واردشده معتبر نیست یا منقضی/مصرف‌شده است."""


class OtpDeliveryError(OtpRateLimitError):
    """تحویل واقعی OTP انجام نشده است.

    ارث‌بری از OtpRateLimitError فقط برای سازگاری callerهای فعلی است تا
    همه‌ی فرم‌ها خطای کنترل‌شده نشان دهند و هیچ مسیر قدیمی 500 نشود.
    """


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def request_otp(*, phone: str, purpose: str, client_ip: str, message: str | None = None) -> None:
    """کدِ تازه می‌سازد و پیامک می‌کند. اگر تعداد درخواست‌های اخیر (برایِ این
    شماره یا این IP) بیش از حد باشد، ``OtpRateLimitError`` می‌دهد — و در آن
    حالت هیچ کدِ تازه‌ای ساخته/ارسال نمی‌شود (جلوگیری از حدس‌زدنِ شماره و
    اسپم). ``message`` برایِ متنِ سفارشیِ پیامک است (مثلاً Section 10 —
    تأییدِ عملیاتِ حساس — که نباید بگوید «کد ورود»)."""
    try:
        enforce_rate_limit(
            f"owner_otp_request_ip:{purpose}", client_ip,
            max_attempts=IP_MAX_REQUESTS, window_seconds=IP_REQUEST_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise OtpRateLimitError(str(exc)) from exc

    window_start = timezone.now() - timedelta(seconds=PHONE_REQUEST_WINDOW_SECONDS)
    recent_count = OwnerOtpChallenge.objects.filter(
        phone=phone, purpose=purpose, created_at__gte=window_start,
    ).count()
    if recent_count >= MAX_REQUESTS_PER_PHONE_WINDOW:
        raise OtpRateLimitError("تعداد درخواست کد برای این شماره بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.")

    code = _generate_code()
    challenge = OwnerOtpChallenge.objects.create(
        phone=phone, purpose=purpose, code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(seconds=OTP_TTL_SECONDS),
    )

    # متن نهایی OTP در Pattern تأییدشده Provider تعریف می‌شود. پارامتر
    # message برای سازگاری API قدیمی باقی مانده ولی کد خام دیگر وارد متن
    # آزاد/Console نمی‌شود.
    expire_minutes = max(1, OTP_TTL_SECONDS // 60)
    result = send_platform_otp(
        to=phone, code=code, purpose=purpose, expire_minutes=expire_minutes,
    )

    # لاگ پلتفرم بدون ذخیره متن/کد OTP؛ فقط طول، Provider و نتیجه نگهداری می‌شود.
    from apps.sms.events import SmsEvent
    from apps.sms.models import SmsTemplate
    from apps.sms.services.billing_policy_service import record_platform_attempt
    template = SmsTemplate.objects.filter(event_key=SmsEvent.PLATFORM_OWNER_OTP).first()
    reference_body = (template.body if template else "کد تأیید راستیسی: {otp_code}")
    try:
        from apps.sms.services import template_renderer
        rendered_for_count = template_renderer.render(
            reference_body, {"otp_code": code, "expire_minutes": expire_minutes},
            ("otp_code", "expire_minutes"),
        )
    except ValueError:
        rendered_for_count = ""
    record_platform_attempt(
        event_key=SmsEvent.PLATFORM_OWNER_OTP, recipient=phone,
        message=rendered_for_count, result=result, protect_body=True,
    )

    if not result.success:
        challenge.delete()
        raise OtpDeliveryError(
            "ارسال کد تأیید موقتاً انجام نشد؛ لطفاً دوباره تلاش کنید."
        )


def verify_otp(*, phone: str, purpose: str, code: str) -> bool:
    """آخرین کدِ فعالِ این (شماره، هدف) را بررسی می‌کند. با موفقیت، همان
    ردیف را مصرف‌شده علامت می‌زند (تک‌مصرفی) و True برمی‌گرداند. تعداد
    تلاشِ ناموفق را می‌شمارد و پس از ``MAX_VERIFY_ATTEMPTS`` آن کد را باطل
    می‌کند (حتی اگر کدِ درست بعداً حدس زده شود)."""
    challenge = (
        OwnerOtpChallenge.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at").first()
    )
    if challenge is None or challenge.is_expired:
        return False
    if challenge.attempt_count >= MAX_VERIFY_ATTEMPTS:
        return False

    if not check_password(code, challenge.code_hash):
        challenge.attempt_count += 1
        challenge.save(update_fields=["attempt_count", "updated_at"])
        return False

    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["consumed_at", "updated_at"])
    return True
