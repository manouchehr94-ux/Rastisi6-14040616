"""صدور/تأییدِ کدِ یکبارمصرفِ ورود و ثبت‌نامِ مالک با موبایل (Section 3).

محدودیت‌ها (مطابق §3.19، و هم‌راستا با ``apps.sms.services.otp_service``ی
موجود برایِ مشتری):
* انقضایِ کوتاه (۲ دقیقه)
* حداکثر تعداد درخواستِ کد در بازه، هم به‌ازایِ شماره هم به‌ازایِ IP
* حداکثر تعداد تلاشِ تأییدِ هر کد
* تک‌مصرفی (replay-proof)
* هرگز کدِ خام لاگ/افشا نمی‌شود؛ فقط هَش ذخیره می‌شود
"""

import enum
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.db.models import F
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
#: صرفاً برایِ UX (شمارش‌معکوسِ دکمه‌ی «ارسال دوباره»). هیچ اثرِ امنیتی ندارد؛
#: سقفِ واقعی همان ``MAX_REQUESTS_PER_PHONE_WINDOW``/``IP_MAX_REQUESTS`` است که
#: سمتِ سرور اعمال می‌شود.
RESEND_UX_COOLDOWN_SECONDS = 30


class OtpCheckResult(enum.Enum):
    """نتیجه‌ی بررسیِ یک کد — فقط برایِ پیامِ دقیق‌تر به صاحبِ همان شماره
    (نشستِ او)؛ ``verify_otp`` همچنان فقط bool برمی‌گرداند."""

    OK = "ok"
    INVALID = "invalid"          # کدِ فعال هست ولی کدِ واردشده نادرست است
    EXPIRED = "expired"          # کدِ فعالی نیست (منقضی، مصرف‌شده یا هرگز ساخته نشده)
    TOO_MANY_ATTEMPTS = "locked"  # سقفِ تلاشِ همین کد پر شده


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


_PHONE_LIMIT_MESSAGE = "تعداد درخواست کد برای این شماره بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید."


def _recent_request_count(phone: str, purpose: str) -> int:
    window_start = timezone.now() - timedelta(seconds=PHONE_REQUEST_WINDOW_SECONDS)
    return OwnerOtpChallenge.objects.filter(
        phone=phone, purpose=purpose, created_at__gte=window_start,
    ).count()


def _lock_phone_purpose(phone: str, purpose: str) -> None:
    """درخواست‌هایِ هم‌زمانِ یک (شماره، هدف) را در دیتابیس سریال می‌کند.

    PostgreSQL: ``pg_advisory_xact_lock`` — قفلِ سطحِ تراکنش که با commit/
    rollback خودکار آزاد می‌شود و بینِ همه‌ی processها/workerها مشترک است (نه
    قفلِ محلیِ process یا cache). برخوردِ هشِ دو کلیدِ متفاوت فقط یک سریال‌سازیِ
    اضافیِ بی‌ضرر است. SQLite (فقط توسعه/تست): نوشتن‌ها از پیش سریال‌اند و
    قفلِ مشورتی وجود ندارد."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"owner_otp_request:{purpose}:{phone}"],
            )


def request_otp(*, phone: str, purpose: str, client_ip: str, message: str | None = None) -> None:
    """کدِ تازه می‌سازد و پیامک می‌کند. اگر تعداد درخواست‌های اخیر (برایِ این
    شماره یا این IP) بیش از حد باشد، ``OtpRateLimitError`` می‌دهد — و در آن
    حالت هیچ کدِ تازه‌ای ساخته/ارسال نمی‌شود (جلوگیری از حدس‌زدنِ شماره و
    اسپم). ``message`` برایِ متنِ سفارشیِ پیامک است (مثلاً Section 10 —
    تأییدِ عملیاتِ حساس — که نباید بگوید «کد ورود»).

    **سقفِ شماره (اتمیک):** بررسیِ «تعداد اخیر < سقف» و ساختنِ ردیفِ چالش در
    *یک* تراکنش و زیرِ قفلِ مشورتیِ دیتابیس برایِ همان (شماره، هدف) انجام
    می‌شود؛ پس درخواست‌هایِ هم‌زمان نمی‌توانند هم‌زمان همان شمارش را ببینند و
    از سقف عبور کنند. قفل فقط دورِ «شمارش + درج» است، نه دورِ ارسالِ پیامک.

    **سیاستِ سهمیه (صریح):** فقط کدهایی که واقعاً تحویلِ موفق گرفته‌اند — به
    اضافه‌ی تلاش‌هایِ هنوز-در-جریان — از سقف مصرف می‌کنند. یک تلاشِ در-جریان
    تا روشن‌شدنِ نتیجه یک سهمیه را نگه می‌دارد (تا هم‌زمانی از سقف رد نشود)؛ اگر
    تحویل شکست بخورد ردیف حذف و سهمیه آزاد می‌شود. پس شکستِ Provider سهمیه‌ی
    موفق را نمی‌سوزاند (ولی درخواست‌هایی که همان لحظه رد شده بودند خودکار
    تکرار نمی‌شوند؛ کاربر دوباره تلاش می‌کند). سقفِ IP جدا و مستقل است.

    **تازه‌ترین کدِ تحویل‌شده معتبر است:** پس از تحویلِ موفق، چالش‌هایِ قدیمیِ
    همین (شماره، هدف) باطل می‌شوند. ترتیب بر اساس ``pk`` است که زیرِ همان قفل
    به‌ترتیبِ درج صادر می‌شود."""
    try:
        enforce_rate_limit(
            f"owner_otp_request_ip:{purpose}", client_ip,
            max_attempts=IP_MAX_REQUESTS, window_seconds=IP_REQUEST_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise OtpRateLimitError(str(exc)) from exc

    # ردِ سریعِ بدون قفل: درخواستِ آشکارا بیش از سقف، هشِ کندِ PBKDF2 نمی‌سوزاند.
    if _recent_request_count(phone, purpose) >= MAX_REQUESTS_PER_PHONE_WINDOW:
        raise OtpRateLimitError(_PHONE_LIMIT_MESSAGE)

    code = _generate_code()
    code_hash = make_password(code)  # کند؛ عمداً بیرون از قفل

    with transaction.atomic():
        _lock_phone_purpose(phone, purpose)
        if _recent_request_count(phone, purpose) >= MAX_REQUESTS_PER_PHONE_WINDOW:
            raise OtpRateLimitError(_PHONE_LIMIT_MESSAGE)
        challenge = OwnerOtpChallenge.objects.create(
            phone=phone, purpose=purpose, code_hash=code_hash,
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

    # فقط «تازه‌ترین» کد معتبر است: پس از تحویلِ موفق، کدهای قبلیِ همین
    # (شماره، هدف) باطل می‌شوند تا یک کدِ قدیمیِ هنوز-منقضی‌نشده بعد از
    # مصرفِ کدِ تازه دوباره قابلِ استفاده نباشد.
    now = timezone.now()
    OwnerOtpChallenge.objects.filter(
        phone=phone, purpose=purpose, consumed_at__isnull=True, pk__lt=challenge.pk,
        expires_at__gt=now,
    ).update(expires_at=now, updated_at=now)


def check_otp(*, phone: str, purpose: str, code: str) -> OtpCheckResult:
    """آخرین کدِ فعالِ این (شماره، هدف) را بررسی می‌کند.

    طراحیِ هم‌زمانی (هر دو گامِ حساس یک ``UPDATE`` شرطیِ اتمیک در دیتابیس‌اند،
    نه «خواندن، سپس نوشتن» در پایتون — بنابراین روی SQLite و PostgreSQL هر دو
    درست‌اند و به قفلِ سطحِ برنامه/JavaScript وابسته نیستند):

    1. «رزروِ تلاش»: ``attempt_count`` فقط وقتی یکی زیاد می‌شود که کد هنوز
       مصرف/منقضی نشده و شمارنده < ``MAX_VERIFY_ATTEMPTS`` باشد. بنابراین
       حدس‌هایِ هم‌زمان هم در مجموع از سقفِ ۵ تلاش فراتر نمی‌روند.
    2. مصرفِ کد: ``UPDATE ... SET consumed_at=now WHERE id=? AND consumed_at IS
       NULL AND expires_at > now`` — فقط یک درخواست تعدادِ سطرِ تغییرکرده = ۱
       می‌گیرد؛ دیگری (replay/race) صفر می‌گیرد و رد می‌شود. در PostgreSQL
       درخواستِ دوم روی قفلِ سطر منتظر می‌ماند و بعد شرط را دوباره می‌سنجد.
    3. پس از مصرفِ موفق، کدهایِ فعالِ دیگرِ همین (شماره، هدف) هم باطل می‌شوند.

    هَشِ کد (PBKDF2، کند) عمداً بیرون از هر تراکنش/قفلی بررسی می‌شود."""
    now = timezone.now()
    challenge = (
        OwnerOtpChallenge.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True)
        .order_by("-pk").first()
    )
    if challenge is None or challenge.expires_at <= now:
        return OtpCheckResult.EXPIRED

    reserved = OwnerOtpChallenge.objects.filter(
        pk=challenge.pk, consumed_at__isnull=True, expires_at__gt=now,
        attempt_count__lt=MAX_VERIFY_ATTEMPTS,
    ).update(attempt_count=F("attempt_count") + 1, updated_at=now)
    if not reserved:
        fresh = OwnerOtpChallenge.objects.filter(pk=challenge.pk).first()
        if fresh is not None and fresh.attempt_count >= MAX_VERIFY_ATTEMPTS and fresh.is_usable:
            return OtpCheckResult.TOO_MANY_ATTEMPTS
        return OtpCheckResult.EXPIRED

    if not check_password(code, challenge.code_hash):
        return OtpCheckResult.INVALID

    consumed = OwnerOtpChallenge.objects.filter(
        pk=challenge.pk, consumed_at__isnull=True, expires_at__gt=timezone.now(),
    ).update(consumed_at=now, updated_at=now)
    if consumed != 1:
        return OtpCheckResult.EXPIRED  # دیگری همین کد را همین لحظه مصرف کرد

    OwnerOtpChallenge.objects.filter(
        phone=phone, purpose=purpose, consumed_at__isnull=True,
    ).update(consumed_at=now, updated_at=now)
    return OtpCheckResult.OK


def verify_otp(*, phone: str, purpose: str, code: str) -> bool:
    """نسخه‌ی bool از :func:`check_otp` — برایِ callerهایی (مثل step-up) که
    فقط موفق/ناموفق می‌خواهند."""
    return check_otp(phone=phone, purpose=purpose, code=code) is OtpCheckResult.OK


def resend_timing(*, phone: str, purpose: str) -> dict:
    """زمان‌هایِ باقی‌مانده برایِ نمایشِ UX (اعتبارِ کد و دکمه‌ی ارسال دوباره).
    فقط اطلاعاتی است؛ هیچ تصمیمِ امنیتی‌ای از آن گرفته نمی‌شود."""
    challenge = (
        OwnerOtpChallenge.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True)
        .order_by("-pk").first()
    )
    if challenge is None:
        return {"expires_in": 0, "resend_in": 0}
    now = timezone.now()
    expires_in = max(0, int((challenge.expires_at - now).total_seconds()))
    age = (now - challenge.created_at).total_seconds()
    resend_in = max(0, int(RESEND_UX_COOLDOWN_SECONDS - age))
    return {"expires_in": expires_in, "resend_in": resend_in}
