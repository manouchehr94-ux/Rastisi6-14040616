"""لایه‌ی سرویسِ هویتِ مالک — هویتِ موبایل+OTP، ورود با موبایل/ایمیل/نام کاربری و بازیابی رمز.

عمداً از ``apps.customers.services.auth_service`` جداست (ADR-93): آن سرویس
مشتریِ فروشگاه می‌سازد (همیشه به یک ``store`` وابسته است)؛ این‌جا مالکِ پلتفرم
(``OwnerProfile``) مدیریت می‌شود، مستقل از هر Store‌ای.

* ثبتِ‌نامِ عمومیِ مالک **فقط با موبایلِ تأییدشده با OTP** است
  (:func:`resolve_owner_identity_by_phone`).
* ورود با ایمیل/نام‌کاربری + رمز و بازیابیِ رمز برایِ حساب‌هایِ *موجود* باقی است.
* :func:`register_owner` (ایمیل+رمز) فقط سرویسِ داخلی است — هیچ مسیرِ عمومی
  ندارد.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.core.services.rate_limit import RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit
from apps.portal.models import OwnerProfile, OwnerTermsAcceptance

User = get_user_model()

#: پیامِ عمومیِ خطایِ ورود — یکپارچه‌سازیِ احرازِ هویت: هرگز فاش نمی‌کند
#: شناسه (ایمیل/موبایل) وجود دارد یا رمز نادرست بوده — یکی از دو حالت را
#: نمی‌توان از روی پیام تشخیص داد.
GENERIC_LOGIN_ERROR = "اطلاعات ورود صحیح نیست."

#: سقفِ طولِ ورودی‌هایِ ورود با رمز. بلندتر از این هرگز یک حسابِ واقعی نیست و
#: نباید پرس‌وجو/هشِ سنگین بسازد (حدِ ایمیل در RFC 5321: ۲۵۴؛ رمز: سقفِ سخاوتمندانه).
LOGIN_IDENTIFIER_MAX_LENGTH = 254
LOGIN_PASSWORD_MAX_LENGTH = 1024


class OwnerAuthError(Exception):
    """خطای قابل‌نمایش به کاربر در فرم ثبت‌نام/ورود/بازیابیِ رمزِ پرتال."""


class PasswordPolicyError(OwnerAuthError):
    """رمزِ جدید توسطِ ``AUTH_PASSWORD_VALIDATORS`` رد شد؛ ``messages`` فهرستِ
    پیام‌هایِ (فارسیِ) همان اعتبارسنج‌هاست — بدونِ بازنویسی یا تضعیفِ قواعد."""

    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__(" ".join(self.messages))


class NewOwnerRegistrationClosedError(OwnerAuthError):
    """ثبت‌نامِ مالکِ تازه (``PlatformConfiguration.new_store_registration_enabled``)
    بسته است و این شماره هنوز هویتِ مالک ندارد."""


class OwnerAccountInactiveError(OwnerAuthError):
    """``User`` این شماره غیرفعال است؛ نه ورود انجام می‌شود نه چیزی ساخته می‌شود."""


class OwnerCredentialsError(OwnerAuthError):
    """ایمیل/رمزِ لازم برایِ ساختنِ مالکِ تازه نیامده یا نامعتبر است؛ هیچ ``User``/مالکی ساخته نمی‌شود."""


class OwnerEmailError(OwnerCredentialsError):
    """ایمیل خالی/نامعتبر/بلندتر از حد است."""


class OwnerEmailConflictError(OwnerEmailError):
    """این ایمیل (بدونِ حساسیت به بزرگی/کوچکیِ حروف) از قبل مالِ ``User``ِ دیگری است."""


OWNER_FULL_NAME_MIN_LENGTH = 2
OWNER_FULL_NAME_MAX_LENGTH = 100
#: نویسه‌هایِ نامرئی/کنترلی که نباید در نام بمانند (ZWNJ — نیم‌فاصله — عمداً مجاز است).
_ZWNJ = "\u200c"
_INVISIBLE_RE = re.compile("[\u200b\u200d\u200e\u200f\u202a-\u202e\u2060\ufeff]")


def normalize_owner_full_name(raw_value: str) -> str:
    """نامِ مالک را نرمال می‌کند: NFKC، حذفِ نویسه‌هایِ نامرئی/کنترلی، فشرده‌سازیِ
    فاصله‌ها، و اعتبارسنجیِ طول و حداقل یک حرف. نام‌هایِ فارسی و لاتین هر دو
    معتبرند. ``OwnerAuthError`` می‌دهد اگر نامعتبر باشد."""
    value = unicodedata.normalize("NFKC", str(raw_value or ""))
    value = _INVISIBLE_RE.sub("", value)
    value = "".join(
        " " if ch.isspace() else ch for ch in value if ch == _ZWNJ or ch.isprintable() or ch.isspace()
    )
    value = " ".join(value.split())
    value = re.sub(f"{_ZWNJ}+", _ZWNJ, value)
    value = re.sub(f" ?{_ZWNJ} ?", lambda m: " " if m.group(0) != _ZWNJ else _ZWNJ, value).strip(f" {_ZWNJ}")
    if not value:
        raise OwnerAuthError("نام و نام خانوادگی را وارد کنید.")
    if len(value) < OWNER_FULL_NAME_MIN_LENGTH or not any(ch.isalpha() for ch in value):
        raise OwnerAuthError("نام واردشده معتبر نیست؛ نام و نام خانوادگی خود را با حروف بنویسید.")
    if len(value) > OWNER_FULL_NAME_MAX_LENGTH:
        raise OwnerAuthError(f"نام نباید بیشتر از {OWNER_FULL_NAME_MAX_LENGTH} نویسه باشد.")
    return value


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


#: ``User.email`` در جنگو ``max_length=254`` است (حدِ RFC 5321).
EMAIL_MAX_LENGTH = 254
EMAIL_REQUIRED_MESSAGE = "ایمیل را وارد کنید."
EMAIL_INVALID_MESSAGE = "ایمیل واردشده معتبر نیست؛ مثلاً name@example.com."
EMAIL_CONFLICT_MESSAGE = "این ایمیل قبلاً برای حساب دیگری ثبت شده است؛ ایمیل دیگری وارد کنید."
PASSWORD_REQUIRED_MESSAGE = "رمز عبور را وارد کنید."


def normalize_and_validate_email(raw_email: str) -> str:
    """ایمیل را نرمال (trim + حروفِ کوچک) و اعتبارسنجی می‌کند؛ ``OwnerEmailError`` اگر خالی/نامعتبر/
    بلند باشد. یک منبعِ واحد برایِ فرم و سرویس."""
    email = _normalize_email(raw_email)
    if not email:
        raise OwnerEmailError(EMAIL_REQUIRED_MESSAGE)
    if len(email) > EMAIL_MAX_LENGTH:
        raise OwnerEmailError(EMAIL_INVALID_MESSAGE)
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise OwnerEmailError(EMAIL_INVALID_MESSAGE) from exc
    return email


def email_belongs_to_another_user(email: str, *, exclude_user=None) -> bool:
    """آیا این (نرمال‌شده) ایمیل — بدونِ حساسیت به حروف — از آنِ ``User``ِ دیگری است؟ ایمیلِ خودِ همان
    ``exclude_user`` تعارض نیست."""
    queryset = User.objects.filter(email__iexact=email)
    if exclude_user is not None and exclude_user.pk is not None:
        queryset = queryset.exclude(pk=exclude_user.pk)
    return queryset.exists()


def _lock_email(email: str) -> None:
    """درخواست‌هایِ هم‌زمان با یک ایمیل را در PostgreSQL سریال می‌کند (``User.email`` unique نیست؛ این قفل
    جلوی دو حسابِ هم‌زمان با یک ایمیل را می‌گیرد). SQLite: نوشتن‌ها از پیش سریال‌اند."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"owner_account_email:{email}"],
            )


@dataclass(frozen=True)
class SignupRequirements:
    """آنچه یک شمارهٔ تأییدشده برایِ مالک‌شدن لازم دارد — از وضعیتِ *واقعیِ* همان ``User`` در دیتابیس
    (نه از کلاینت). ``existing_owner``: ``OwnerProfile`` دارد؛ هیچ مرحله‌ای لازم نیست. وگرنه
    ``need_email``/``need_password`` می‌گویند اعتبارنامه‌یِ این حساب چه کم دارد: ``User``ِ تازه هر دو؛
    ``User``ِ موجودِ بدونِ رمزِ قابل‌استفاده رمز؛ ``User``ِ موجودِ بدونِ ایمیل ایمیل. رمزِ قابل‌استفاده یا
    ایمیلِ ثبت‌شده هرگز بازنویسی نمی‌شود."""

    existing_owner: bool
    need_email: bool
    need_password: bool
    user: "User | None" = None

    @property
    def needs_credentials(self) -> bool:
        return self.need_email or self.need_password


def signup_requirements_for_phone(phone: str) -> SignupRequirements:
    if OwnerProfile.objects.filter(phone=phone).exists():
        return SignupRequirements(existing_owner=True, need_email=False, need_password=False)
    user = User.objects.filter(username=phone).first()
    if user is None:
        return SignupRequirements(existing_owner=False, need_email=True, need_password=True)
    if OwnerProfile.objects.filter(user=user).exists():
        return SignupRequirements(existing_owner=True, need_email=False, need_password=False, user=user)
    return SignupRequirements(
        existing_owner=False,
        need_email=not (user.email or "").strip(),
        need_password=not user.has_usable_password(),
        user=user,
    )


def validate_new_account_password(password: str, *, user) -> None:
    """رمزِ تازه را فقط با ``AUTH_PASSWORD_VALIDATORS`` می‌سنجد (سیاستِ جداگانه‌ای نیست). ``user`` می‌تواند
    نمونه‌یِ ذخیره‌نشده باشد (برایِ اعتبارسنجِ شباهت به نام‌کاربری/ایمیل). ``PasswordPolicyError`` اگر رد شود."""
    if not password:
        raise PasswordPolicyError([PASSWORD_REQUIRED_MESSAGE])
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise PasswordPolicyError(_persian_policy_messages(exc)) from exc


def _looks_like_email(identifier: str) -> bool:
    return "@" in (identifier or "")


@transaction.atomic
def register_owner(*, full_name: str, email: str, password: str) -> User:
    """**Internal only** (management commands, fixtures, tests): creates an
    email+password Owner. There is deliberately NO public route for this — public
    registration is mobile OTP only (``/register/`` or ``/login/`` →
    ``/signup/complete/``). Do not wire it to an anonymous view."""
    email = _normalize_email(email)
    if not email:
        raise OwnerAuthError("ایمیل الزامی است")
    if User.objects.filter(email__iexact=email).exists():
        raise OwnerAuthError("این ایمیل قبلاً ثبت‌نام کرده است")
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise OwnerAuthError(" ".join(exc.messages)) from exc

    user = User.objects.create_user(username=email, email=email, password=password)
    OwnerProfile.objects.create(user=user, full_name=full_name.strip())
    return user


def authenticate_owner(request, *, email: str, password: str):
    """با ایمیل و رمز احراز هویت می‌کند و در صورت موفقیت User را برمی‌گرداند، وگرنه None."""
    return authenticate(request, username=_normalize_email(email), password=password)


def _burn_password_hash(password: str) -> None:
    """هزینه‌یِ یک هشِ رمز را می‌پردازد تا پاسخِ «حسابی نیست / حسابِ ورودِ-با-رمز
    نیست» از نظرِ زمانی با «رمز نادرست» تفاوتِ قابلِ‌اندازه‌گیری نداشته باشد
    (همان تکنیکِ ``ModelBackend.authenticate`` برایِ کاربرِ ناموجود)."""
    User().set_password(password)


def _is_owner_portal_identity(user) -> bool:
    """فقط هویت‌هایِ «مالک/کارمند/مدیرِ پلتفرم» از ورودِ رمزیِ پرتال عبور می‌کنند:
    مدیرِ پلتفرم، یا دارایِ ``OwnerProfile``، یا عضوِ **فعالِ** دست‌کم یک Store.
    یک ``User`` که فقط مشتریِ فروشگاه است (حتی اگر ایمیل/رمز داشته باشد) هرگز
    از این مسیر وارد پرتال نمی‌شود."""
    from apps.stores.models import StoreMembership

    return bool(
        user.is_superuser
        or OwnerProfile.objects.filter(user=user).exists()
        or StoreMembership.objects.filter(
            user=user, status=StoreMembership.MembershipStatus.ACTIVE
        ).exists()
    )


def _resolve_login_candidate(identifier: str):
    """شناسه (ایمیل / موبایل / نام‌کاربری) را به *یک* ``User`` تبدیل می‌کند، یا
    ``None``. مبهم (چند حسابِ هم‌نام) fail-closed است. اهلیتِ پرتال و رمز را
    بررسی نمی‌کند — آن‌ها کارِ :func:`authenticate_owner_by_identifier` است."""
    user = None
    if _looks_like_email(identifier):
        matches = list(User.objects.filter(email__iexact=_normalize_email(identifier))[:2])
        if len(matches) > 1:
            return None
        if matches:
            user = matches[0]
    else:
        try:
            phone = normalize_iranian_phone(identifier)
        except InvalidPhoneError:
            phone = None
        if phone is not None:
            profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
            user = profile.user if profile is not None else None

            # Legacy merchant staff can have User.username == phone without
            # an OwnerProfile. Only an existing merchant membership or a
            # platform superuser may use this compatibility path.
            if user is None:
                candidate = User.objects.filter(username=phone).first()
                if candidate is not None and _is_owner_portal_identity(candidate):
                    user = candidate

    if user is None:
        # A legacy arbitrary username (including an email-shaped username
        # with no User.email) is allowed only for owner/staff identities.
        matches = list(User.objects.filter(username__iexact=identifier)[:2])
        if len(matches) != 1:
            return None
        user = matches[0]
    return user


def authenticate_owner_by_identifier(request, *, identifier: str, password: str):
    """Authenticate with email, mobile number or username + password.

    This resolves *identity* only. Access to a specific merchant dashboard
    still requires an ACTIVE StoreMembership and a valid admin host, enforced
    by the existing handoff and dashboard permission layers. A plain Customer
    never gains merchant privileges simply by sharing a username, phone or
    email: every resolved account — whichever identifier matched — must be a
    platform superuser, an Owner, or an ACTIVE Store member
    (:func:`_is_owner_portal_identity`).

    Ambiguous case-insensitive identifiers fail closed instead of selecting
    an arbitrary account. Password validation remains Django's authenticate().

    Every failure returns ``None`` after doing the cost of one password hash
    (:func:`_burn_password_hash`), so unknown, ineligible, OTP-only (unusable
    password) and wrong-password accounts are not distinguishable by latency.
    """
    identifier = (identifier or "").strip()
    password = password or ""
    if (
        not identifier or not password
        or len(identifier) > LOGIN_IDENTIFIER_MAX_LENGTH or len(password) > LOGIN_PASSWORD_MAX_LENGTH
    ):
        _burn_password_hash(password[:LOGIN_PASSWORD_MAX_LENGTH])
        return None

    user = _resolve_login_candidate(identifier)
    if user is None or not user.has_usable_password() or not _is_owner_portal_identity(user):
        _burn_password_hash(password)
        return None

    return authenticate(request, username=user.username, password=password)


def login_identifier_throttle_key(identifier: str) -> str:
    """کلیدِ پایدارِ throttle برایِ یک شناسه‌یِ ورود — بدونِ حساس‌بودن به
    حروف/ارقامِ فارسی/فاصله، و هشِ SHA-256 (هیچ ایمیل/شماره‌ای خام در cache
    نمی‌ماند). برایِ هر رشته‌ای ساخته می‌شود، پس خودِ throttle هرگز فاش
    نمی‌کند که حسابی وجود دارد."""
    value = (identifier or "").strip().lower()[:LOGIN_IDENTIFIER_MAX_LENGTH * 2]
    value = value.translate(_FA_AR_DIGIT_MAP)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


_FA_AR_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


#: سقفِ درخواستِ ایمیلِ بازیابی به‌ازایِ هر ایمیل (جدا از سقفِ IP در ویو) — تا
#: نشود صندوقِ یک نفر را با درخواستِ پشت‌سرهم پر کرد. عبور از سقف *بی‌صدا* است
#: (پاسخِ عمومی همان «ارسال شد» می‌ماند) پس چیزی فاش نمی‌شود.
PASSWORD_RESET_EMAIL_MAX_PER_HOUR = 3


def _can_use_password_reset(user) -> bool:
    """بازیابیِ رمز فقط برایِ حسابی که خودش می‌تواند با رمز وارد پرتال شود:
    فعال، دارایِ رمزِ قابل‌استفاده (مثلِ ``PasswordResetForm.get_users`` جنگو) و
    هویتِ مالک/کارمند/مدیر. مشتریِ تنها و حسابِ غیرفعال ایمیل نمی‌گیرند و
    پیوندشان هم کار نمی‌کند."""
    return bool(user.is_active and user.has_usable_password() and _is_owner_portal_identity(user))


def request_password_reset(*, email: str, base_url: str) -> None:
    # LEGACY / INTERNAL: no public view calls this any more. Public password recovery is
    # mobile + SMS OTP (``/reset-password/`` -> ``/verify/`` -> ``/reset-password/new/``).
    # Kept (with ``get_user_from_reset_link`` and ``/reset-password/<uidb64>/<token>/``) so
    # already-issued email links and internal tooling keep working.
    """اگر ایمیل متعلق به **یک** مالکِ فعال باشد ایمیل بازیابی می‌فرستد؛ در غیر
    این صورت بی‌صدا کاری نمی‌کند — تا فرمِ عمومی هرگز فاش نکند کدام ایمیل
    ثبت‌نام کرده (enumeration-safety). چند حسابِ هم‌ایمیل مبهم است و مثلِ ورود
    fail-closed (ارسال نمی‌شود). ``base_url`` مثلِ ``"https://rastisi.ir"`` —
    بدونِ اسلشِ پایانی؛ ویو آن را از ``request.get_host()`` می‌سازد که پیش‌تر
    توسطِ ``ALLOWED_HOSTS`` اعتبارسنجی شده و این URLconf فقط روی hostهایِ
    پلتفرم سرو می‌شود."""
    normalized = _normalize_email(email)
    if not normalized:
        return
    matches = list(User.objects.filter(email__iexact=normalized)[:2])
    if len(matches) != 1 or not _can_use_password_reset(matches[0]):
        return
    user = matches[0]
    try:
        enforce_rate_limit(
            "password_reset_email", hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32],
            max_attempts=PASSWORD_RESET_EMAIL_MAX_PER_HOUR, window_seconds=3600,
        )
    except RateLimitExceeded:
        return
    except RateLimitUnavailable:
        # Fail closed AND silent: no reset mail is sent while the shared counter
        # is down, and (enumeration safety) the caller cannot tell an eligible
        # account from an ineligible one by this branch.
        return
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{base_url}/reset-password/{uidb64}/{token}/"
    body = render_to_string(
        "portal/public/emails/password_reset.txt",
        {"user": user, "reset_url": reset_url},
    )
    send_mail(
        subject="بازیابی رمز عبور راستیسی",
        message=body,
        from_email=None,
        recipient_list=[user.email],
        fail_silently=True,
    )


def find_reset_eligible_user_by_phone(phone: str):
    """Mobile password-recovery eligibility (public SMS-OTP reset).

    Returns the existing, **active** ``User`` that owns an ``OwnerProfile`` with this
    (already normalised) phone, else ``None``. It only *reads*: it never creates a
    ``User``/``OwnerProfile``/Store, so an unknown mobile stays unknown. A usable password is
    deliberately NOT required — an OTP-created owner (unusable password) may set a first one.
    A customer-only account (no ``OwnerProfile``) is not eligible."""
    profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
    if profile is None or not profile.user.is_active:
        return None
    return profile.user


def get_reset_eligible_user_by_id(user_id):
    """Re-check, at password-setting time, that the OTP-authorised user is still an active
    owner (the id comes only from the server-side session proof, never from the request)."""
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not OwnerProfile.objects.filter(user=user).exists():
        return None
    return user


def get_user_from_reset_link(*, uidb64: str, token: str):
    """کاربر را از uid رمزگشایی‌شده برمی‌گرداند اگر توکن معتبر باشد و حساب هنوز
    اجازه‌یِ بازیابی داشته باشد، وگرنه None. توکنِ جنگو به هشِ رمز و ``last_login``
    بسته است؛ پس با تغییرِ رمز (یا یک ورودِ تازه) خودبه‌خود باطل می‌شود."""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token) or not _can_use_password_reset(user):
        return None
    return user


_ARABIC_SCRIPT_RE = re.compile("[\u0600-\u06FF]")
_POLICY_FALLBACK_MESSAGE = "این رمز عبور پذیرفته نیست؛ رمز دیگری انتخاب کنید."


def _persian_policy_messages(exc: DjangoValidationError) -> list[str]:
    """پیام‌هایِ اعتبارسنج‌هایِ تنظیم‌شده را فارسی نگه می‌دارد. فایلِ ترجمه‌یِ ``fa``
    جنگو پیامِ «حداقل طول» را (به‌خاطرِ شکلِ جمع) ندارد و انگلیسی برمی‌گرداند؛ آن را
    از رویِ ``code``/``params`` همان اعتبارسنج فارسی می‌کنیم. قاعده تغییر نمی‌کند، فقط
    متنِ نمایشی؛ و هر پیامِ بدونِ حرفِ فارسی هرگز به کاربر نشان داده نمی‌شود."""
    out = []
    for error in exc.error_list:
        params = error.params or {}
        if error.code == "password_too_short" and "min_length" in params:
            text = f"رمز عبور باید دست‌کم {params['min_length']} نویسه باشد."
        else:
            text = str(error.message % params if params else error.message)
        out.append(text if _ARABIC_SCRIPT_RE.search(text) else _POLICY_FALLBACK_MESSAGE)
    return list(dict.fromkeys(out))


@transaction.atomic
def set_new_password(*, user, password: str) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise PasswordPolicyError(_persian_policy_messages(exc)) from exc
    user.set_password(password)
    user.save(update_fields=["password"])


@dataclass(frozen=True)
class OwnerIdentityResult:
    """نتیجه‌ی صریحِ تعیینِ هویتِ مالک با موبایل.

    * ``user_created`` — ردیفِ ``User`` همین الان ساخته شد (برایِ مشتریِ
      موجود ``False`` است).
    * ``owner_created`` — ``OwnerProfile`` همین الان ساخته شد؛ یعنی این اولین
      باری است که این شخص «مالک» می‌شود. **همین** (نه ``user_created``) تعیین
      می‌کند که فروشگاهِ آزمایشیِ اول ساخته شود: مشتریِ موجودی که برایِ اولین بار
      مالک می‌شود هم باید همان تجربه‌ی اولِ هر مالکِ تازه را بگیرد."""

    user: "User"
    user_created: bool
    owner_created: bool


def resolve_owner_identity_by_phone(
    *, phone: str, full_name: str = "", allow_new_owner: bool = True, require_active: bool = True,
    accepted_terms_version: str = "", terms_source: str = "",
    require_credentials: bool = False, email: str = "", password: str = "",
) -> OwnerIdentityResult:
    """شناسه‌ی اصلیِ ورودِ مالک موبایل+OTP است (Section 3؛ ایمیل+رمز فقط برایِ
    حساب‌هایِ قدیمی/بازیابی/مدیرِ پلتفرم مانده).

    تصمیمِ عمدیِ هویتِ مشترک: چون ``apps.customers`` هم از ``User.username =
    phone`` استفاده می‌کند، شمارهٔ یکسان به همان ردیفِ ``User`` می‌رسد — یک
    موبایلِ تأییدشده با OTP، اثباتِ هویتیِ به‌همان‌اندازه (یا قوی‌تر از) رمزِ
    مشتری است؛ همان شخص فقط قابلیتِ «مالک» را هم می‌گیرد (``OwnerProfile``
    ساخته می‌شود)، نه یک حسابِ جدا یا یتیم. ``Customer`` و هر داده‌ی آن هرگز
    تغییر نمی‌کند.

    ``allow_new_owner=False`` (سیاستِ بسته‌بودنِ ثبت‌نام) فقط ساختنِ مالکِ
    **تازه** را رد می‌کند (``NewOwnerRegistrationClosedError``)؛ مالکِ موجود
    همیشه شناسایی می‌شود. کاربرِ غیرفعال ``OwnerAccountInactiveError`` می‌دهد
    (مگر ``require_active=False``).

    هم‌زمانی: یکتاییِ ``User.username`` و ``OwnerProfile.user``/``phone`` در
    دیتابیس تضمین می‌کند دو درخواستِ هم‌زمان حداکثر یک ``OwnerProfile`` بسازند؛
    فقط برنده ``owner_created=True`` می‌گیرد (و تنها او فروشگاهِ اول را می‌سازد).

    پذیرشِ قوانین: اگر ``accepted_terms_version`` داده شود، ردیفِ ماندگارِ
    ``OwnerTermsAcceptance`` **در همان تراکنش و فقط برایِ برنده‌ی ساختِ
    ``OwnerProfile``** نوشته می‌شود (idempotent با ``get_or_create``)؛ برایِ مالکِ
    موجود یا بازنده‌ی مسابقه هرگز چیزی ثبت نمی‌شود، و اگر ساختنِ مالک شکست بخورد
    پذیرشی هم باقی نمی‌ماند.

    اعتبارنامه (``require_credentials=True``، مسیرهایِ عمومیِ ثبت‌نام): پیش از ساختنِ هر چیز و **در همان
    تراکنش** — ``User``ِ تازه *باید* ایمیلِ معتبرِ یکتا (بدونِ حساسیت به حروف) و رمزِ معتبر (با
    ``AUTH_PASSWORD_VALIDATORS``) بگیرد؛ ``User``ِ موجود فقط آنچه ندارد (ایمیلِ خالی / رمزِ غیرِ قابل‌استفاده)
    را می‌گیرد و رمزِ قابل‌استفاده یا ایمیلِ ثبت‌شده‌اش هرگز بازنویسی نمی‌شود. رمز فقط همین‌جا هش می‌شود و در
    هیچ نشست/لاگ/ردیفِ میانی نیست. خطا ⇒ rollbackِ کامل (نه User، نه OwnerProfile، نه پذیرشِ قوانین)."""
    full_name = " ".join(str(full_name or "").split())

    with transaction.atomic():
        profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
        if profile is not None:
            if require_active and not profile.user.is_active:
                raise OwnerAccountInactiveError("حساب غیرفعال است.")
            return OwnerIdentityResult(profile.user, user_created=False, owner_created=False)

        user = User.objects.select_for_update().filter(username=phone).first()
        user_created = False
        if user is None:
            if not allow_new_owner:
                raise NewOwnerRegistrationClosedError("ثبت‌نام فروشگاهِ تازه موقتاً بسته است.")
            clean_email = ""
            if require_credentials:
                clean_email = normalize_and_validate_email(email)
                validate_new_account_password(password, user=User(username=phone, email=clean_email))
                _lock_email(clean_email)
                # ثبتِ هم‌زمانِ همین شماره (دوبار کلیک/دو تب) تا همین‌جا منتظرِ قفلِ ایمیل مانده؛ اگر برنده کارش را
                # کرده، ایمیلِ او «ایمیلِ دیگری» نیست — همان کاربرِ همین شماره است.
                user = User.objects.select_for_update().filter(username=phone).first()
                if user is None and email_belongs_to_another_user(clean_email):
                    raise OwnerEmailConflictError(EMAIL_CONFLICT_MESSAGE)
            if user is None:
                try:
                    with transaction.atomic():
                        if require_credentials:
                            user = User.objects.create_user(username=phone, email=clean_email, password=password)
                        else:
                            user = User.objects.create_user(username=phone)
                            user.set_unusable_password()
                            user.save(update_fields=["password"])
                    user_created = True
                except IntegrityError:  # درخواستِ هم‌زمانِ دیگری همین شماره را ساخت
                    user = User.objects.select_for_update().get(username=phone)
        if require_active and not user.is_active:
            raise OwnerAccountInactiveError("حساب غیرفعال است.")

        existing_profile = OwnerProfile.objects.select_for_update().filter(user=user).first()
        if existing_profile is None:
            if not allow_new_owner:
                raise NewOwnerRegistrationClosedError("ثبت‌نام فروشگاهِ تازه موقتاً بسته است.")
            if require_credentials and not user_created:
                _apply_missing_credentials(user, email=email, password=password)
            try:
                with transaction.atomic():
                    OwnerProfile.objects.create(user=user, phone=phone, full_name=full_name)
                    if accepted_terms_version:
                        OwnerTermsAcceptance.objects.get_or_create(
                            user=user, terms_version=accepted_terms_version,
                            defaults={"source": terms_source or OwnerTermsAcceptance.Source.REGISTRATION},
                        )
            except IntegrityError:
                # برنده‌ی مسابقه کسِ دیگری بود؛ این درخواست «مالکِ تازه» نیست.
                winner = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
                if winner is None:
                    raise
                return OwnerIdentityResult(winner.user, user_created=False, owner_created=False)
            return OwnerIdentityResult(user, user_created=user_created, owner_created=True)

        if not existing_profile.phone:
            # اتصالِ اولین‌باریِ موبایل به مالکی که از قبل OwnerProfile داشته
            # (مثلاً با ایمیل ثبت‌نام کرده بود). نامِ ثبت‌شده هرگز با نامِ جدید
            # (یا خالی) بازنویسی نمی‌شود؛ فقط اگر خالی بود پر می‌شود.
            fields = ["phone", "updated_at"]
            existing_profile.phone = phone
            if full_name and not existing_profile.full_name:
                existing_profile.full_name = full_name
                fields.append("full_name")
            existing_profile.save(update_fields=fields)
        return OwnerIdentityResult(user, user_created=user_created, owner_created=False)


def _apply_missing_credentials(user, *, email: str, password: str) -> None:
    """برایِ ``User``ِ *موجود* (مثلاً مشتریِ فروشگاه) که مالک می‌شود: فقط جاهایِ خالی پر می‌شود. ایمیلِ
    ثبت‌شده و رمزِ قابل‌استفاده **هرگز** بازنویسی نمی‌شوند؛ ایمیلِ تازه نباید مالِ کسِ دیگری باشد. زیرِ
    قفلِ سطرِ همین ``User`` (فراخوان ``select_for_update`` کرده) و در تراکنشِ فراخوان."""
    fields = []
    if not (user.email or "").strip():
        clean_email = normalize_and_validate_email(email)
        _lock_email(clean_email)
        if email_belongs_to_another_user(clean_email, exclude_user=user):
            raise OwnerEmailConflictError(EMAIL_CONFLICT_MESSAGE)
        user.email = clean_email
        fields.append("email")
    if not user.has_usable_password():
        validate_new_account_password(password, user=user)
        user.set_password(password)
        fields.append("password")
    if fields:
        user.save(update_fields=fields)


def get_or_create_owner_by_phone(*, phone: str, full_name: str = "") -> tuple[User, bool]:
    """سازگاری با callerهایِ قدیمی (انتقالِ مالکیت و تست‌ها). خروجی
    ``(user, owner_created)`` است — یعنی «مالک» ساخته شد، نه صرفاً ``User``
    (معنایِ قبلی مبهم بود و مشتریِ موجود را به‌اشتباه «تازه نیست» می‌شمرد).
    رفتارِ قبلی (بدونِ رد کردنِ کاربرِ غیرفعال) حفظ شده تا انتقالِ مالکیت
    تغییر نکند. کدِ جدید باید مستقیم از :func:`resolve_owner_identity_by_phone`
    استفاده کند."""
    result = resolve_owner_identity_by_phone(phone=phone, full_name=full_name, require_active=False)
    return result.user, result.owner_created
