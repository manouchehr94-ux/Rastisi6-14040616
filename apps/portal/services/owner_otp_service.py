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
import logging
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.portal.models import OwnerOtpChallenge

from .owner_sms_service import send_platform_otp
from .rate_limit import UNAVAILABLE_MESSAGE, RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit

logger = logging.getLogger(__name__)

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


#: ردیفِ «در-جریان» (رزروِ سهمیه‌ای که پیامکش هنوز تحویل نشده): ``expires_at`` روی
#: این مقدارِ ثابتِ گذشته است. چنین ردیفی در ``_recent_request_count`` شمرده می‌شود
#: (پس هم‌زمانی از سقف رد نمی‌شود) ولی چون «منقضی» است هرگز توسط ``check_otp``/
#: ``resend_timing`` انتخاب نمی‌شود، تلاشِ تأیید نمی‌گیرد، و کدِ فعلیِ معتبر را
#: کنار نمی‌زند. پس از تحویلِ موفق، زیرِ همان قفل با TTLِ تازه فعال می‌شود.
#: بدونِ مایگریشن: فقط از فیلدهایِ موجود استفاده می‌کند.
PENDING_EXPIRES_AT = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)

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

    **تا تحویلِ موفق، کد قابلِ‌تأیید نیست:** ردیفِ جدید ابتدا «در-جریان» ساخته
    می‌شود (``PENDING_EXPIRES_AT``): سهمیه را نگه می‌دارد ولی توسط ``check_otp``
    دیده نمی‌شود، تلاشِ تأیید نمی‌گیرد و کدِ فعلیِ معتبر را کنار نمی‌زند. اگر
    تحویل شکست بخورد (یا Provider استثنا بدهد) فقط همان ردیف حذف می‌شود و کدِ
    قبلی بدونِ وقفه معتبر می‌ماند. پس از موفقیت، :func:`_activate_delivered_challenge`
    آن را با TTLِ تازه فعال و کدهایِ قدیمی‌تر را باطل می‌کند.

    **قاعده‌یِ ترتیب — «تازه‌ترین درخواستِ موفق برنده است»:** ترتیب = ترتیبِ
    پذیرشِ درخواست‌ها زیرِ قفلِ (هدف، شماره)، یعنی ``pk``؛ نه ترتیبِ رسیدنِ
    پیامک. تا وقتی درخواستِ جدیدتر در-جریان است، کدِ قدیمیِ تحویل‌شده معتبر
    می‌ماند؛ وقتی جدیدتر موفق شد قدیمی باطل می‌شود؛ و درخواستِ قدیمیِ دیرتمام
    هرگز جدیدتر را پس نمی‌گیرد."""
    try:
        enforce_rate_limit(
            f"owner_otp_request_ip:{purpose}", client_ip,
            max_attempts=IP_MAX_REQUESTS, window_seconds=IP_REQUEST_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise OtpRateLimitError(str(exc)) from exc
    except RateLimitUnavailable as exc:
        # Fail closed: no code is created and no SMS is sent while the shared
        # throttle store is down (an SMS-pumping/brute-force control must not vanish).
        raise OtpDeliveryError(UNAVAILABLE_MESSAGE) from exc

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
            phone=phone, purpose=purpose, code_hash=code_hash, expires_at=PENDING_EXPIRES_AT,
        )

    # متن نهایی OTP در Pattern تأییدشده Provider تعریف می‌شود. پارامتر
    # message برای سازگاری API قدیمی باقی مانده ولی کد خام دیگر وارد متن
    # آزاد/Console نمی‌شود.
    expire_minutes = max(1, OTP_TTL_SECONDS // 60)
    try:
        result = send_platform_otp(
            to=phone, code=code, purpose=purpose, expire_minutes=expire_minutes,
        )
    except Exception:
        # Only ``Exception``: KeyboardInterrupt/SystemExit must not be intercepted
        # here. An unexpected provider crash must not leak a quota slot, and the
        # cleanup must never mask the provider's own exception.
        _drop_pending_best_effort(challenge)
        raise

    # ── چرخه‌ی حیاتِ OTP همین‌جا و *پیش از* هر تله‌متری تمام می‌شود ──────────────
    # حالتِ احرازِ هویت هرگز نباید به موفقیتِ نوشتنِ SmsLog وابسته باشد.
    if result.success:
        try:
            _activate_delivered_challenge(challenge)
        except Exception:
            # فعال‌سازی (دیتابیس) خطای حیاتی است و بلعیده نمی‌شود؛ فقط تلاش
            # می‌کنیم رزروِ معلق نماند و خطای اصلی همان را بالا می‌دهیم.
            _drop_pending_best_effort(challenge)
            raise
        _record_sms_attempt_best_effort(phone=phone, code=code, expire_minutes=expire_minutes, result=result)
        return

    _drop_pending(challenge)
    _record_sms_attempt_best_effort(phone=phone, code=code, expire_minutes=expire_minutes, result=result)
    raise OtpDeliveryError(
        "ارسال کد تأیید موقتاً انجام نشد؛ لطفاً دوباره تلاش کنید."
    )


def _record_sms_attempt_best_effort(*, phone: str, code: str, expire_minutes: int, result) -> None:
    """لاگِ پلتفرمِ پیامک (بدونِ ذخیره‌ی متن/کدِ OTP؛ فقط طول، Provider و نتیجه).

    **تله‌متری است، نه بخشی از چرخه‌ی OTP:** هر خطایِ نوشتنِ SmsLog/قالب/
    محاسبه‌ی هزینه فقط برایِ اپراتور لاگ می‌شود و هرگز کدِ تحویل‌شده را
    بی‌اثر یا خطایِ کنترل‌شده‌ی تحویل را به 500 تبدیل نمی‌کند. نوشتن در یک
    savepoint انجام می‌شود تا شکستش تراکنشِ احتمالیِ بیرونی را خراب نکند.
    تولیدِ کد، سقفِ سهمیه، فعال‌سازیِ دیتابیس و خودِ ارسال عمداً *خارج* از
    این تابع‌اند و بلعیده نمی‌شوند."""
    try:
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
        with transaction.atomic():
            record_platform_attempt(
                event_key=SmsEvent.PLATFORM_OWNER_OTP, recipient=phone,
                message=rendered_for_count, result=result, protect_body=True,
            )
    except Exception:
        logger.error(
            "owner OTP SMS telemetry write failed; the OTP lifecycle is unaffected", exc_info=True,
        )


def _drop_pending_best_effort(challenge: OwnerOtpChallenge) -> None:
    """پاک‌سازی در مسیرِ خطا: اگر خودش هم شکست بخورد خطایِ اصلی را نمی‌پوشاند."""
    try:
        _drop_pending(challenge)
    except Exception:
        logger.error("could not release a pending OTP reservation", exc_info=True)


def _drop_pending(challenge: OwnerOtpChallenge) -> None:
    """رزروِ شکست‌خورده را حذف می‌کند؛ کدِ فعلیِ معتبر هرگز تغییر نمی‌کند."""
    OwnerOtpChallenge.objects.filter(pk=challenge.pk, expires_at=PENDING_EXPIRES_AT).delete()


def _activate_delivered_challenge(challenge: OwnerOtpChallenge) -> None:
    """پس از تحویلِ موفقِ پیامک، زیرِ **همان قفلِ (هدف، شماره)** و در یک تراکنش:

    * اگر درخواستی *جدیدتر* از این (``pk`` بزرگ‌تر) قبلاً با موفقیت صادر شده
      باشد (فعال، مصرف‌شده، منقضی یا باطل‌شده — هر ردیفِ غیرِ در-جریان)، این
      کد هرگز قابل‌استفاده نمی‌شود و باطل علامت می‌خورد؛ یک درخواستِ قدیمیِ دیرتمام
      کدِ جدیدتر را پس نمی‌گیرد و پس از مصرفِ کدِ جدیدتر دوباره زنده نمی‌شود.
    * وگرنه با TTLِ تازه فعال می‌شود و کدهایِ فعالِ قدیمی‌ترِ همین (شماره،
      هدف) باطل می‌شوند. ردیف‌هایِ قدیمی‌ترِ هنوز-در-جریان دست‌نخورده می‌مانند؛
      وقتی تمام شوند با قاعده‌یِ بالا باطل می‌شوند.

    ترتیب = ترتیبِ پذیرشِ درخواست‌ها زیرِ قفل (``pk``)، **نه** ترتیبِ رسیدنِ
    پیامک به گوشی — برنامه ترتیبِ تحویلِ اپراتور را نمی‌داند."""
    with transaction.atomic():
        _lock_phone_purpose(challenge.phone, challenge.purpose)
        now = timezone.now()
        newer_issued = (
            OwnerOtpChallenge.objects.filter(
                phone=challenge.phone, purpose=challenge.purpose, pk__gt=challenge.pk,
            ).exclude(expires_at=PENDING_EXPIRES_AT).exists()
        )
        if newer_issued:
            OwnerOtpChallenge.objects.filter(
                pk=challenge.pk, expires_at=PENDING_EXPIRES_AT,
            ).update(expires_at=now, updated_at=now)
            return
        activated = OwnerOtpChallenge.objects.filter(
            pk=challenge.pk, expires_at=PENDING_EXPIRES_AT, consumed_at__isnull=True,
        ).update(expires_at=now + timedelta(seconds=OTP_TTL_SECONDS), updated_at=now)
        if activated:
            OwnerOtpChallenge.objects.filter(
                phone=challenge.phone, purpose=challenge.purpose, consumed_at__isnull=True,
                pk__lt=challenge.pk, expires_at__gt=now,
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
    # فقط چالشِ «واقعاً فعال» (تحویل‌شده، مصرف‌نشده، منقضی‌نشده)؛ ردیفِ در-جریان
    # (PENDING_EXPIRES_AT) هرگز انتخاب نمی‌شود.
    challenge = (
        OwnerOtpChallenge.objects.filter(
            phone=phone, purpose=purpose, consumed_at__isnull=True, expires_at__gt=now,
        ).order_by("-pk").first()
    )
    if challenge is None:
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
        phone=phone, purpose=purpose, consumed_at__isnull=True, expires_at__gt=now,
    ).update(consumed_at=now, updated_at=now)  # ردیف‌هایِ در-جریان دست‌نخورده می‌مانند
    return OtpCheckResult.OK


def verify_otp(*, phone: str, purpose: str, code: str) -> bool:
    """نسخه‌ی bool از :func:`check_otp` — برایِ callerهایی (مثل step-up) که
    فقط موفق/ناموفق می‌خواهند."""
    return check_otp(phone=phone, purpose=purpose, code=code) is OtpCheckResult.OK


def resend_timing(*, phone: str, purpose: str) -> dict:
    """زمان‌هایِ باقی‌مانده برایِ نمایشِ UX (اعتبارِ کد و دکمه‌ی ارسال دوباره).
    فقط اطلاعاتی است؛ هیچ تصمیمِ امنیتی‌ای از آن گرفته نمی‌شود."""
    now = timezone.now()
    challenge = (
        OwnerOtpChallenge.objects.filter(
            phone=phone, purpose=purpose, consumed_at__isnull=True, expires_at__gt=now,
        ).order_by("-pk").first()
    )
    if challenge is None:
        return {"expires_in": 0, "resend_in": 0}
    expires_in = max(0, int((challenge.expires_at - now).total_seconds()))
    age = (now - challenge.created_at).total_seconds()
    resend_in = max(0, int(RESEND_UX_COOLDOWN_SECONDS - age))
    return {"expires_in": expires_in, "resend_in": resend_in}
