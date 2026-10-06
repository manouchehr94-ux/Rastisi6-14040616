"""لایه‌ی سرویسِ هویتِ مالک — ثبت‌نام، ورود با موبایل/ایمیل/نام کاربری و بازیابی رمز.

عمداً از ``apps.customers.services.auth_service`` جداست (ADR-93): آن سرویس
مشتریِ فروشگاه می‌سازد (شناسه = موبایل، همیشه به یک ``store`` وابسته است)؛
این‌جا مالکِ پلتفرم ساخته می‌شود (شناسه = ایمیل، مستقل از هر Store‌ای —
مالک قبل از ساختِ اولین Store هم باید بتواند ثبت‌نام کند).
"""

import re
import unicodedata
from dataclasses import dataclass

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.portal.models import OwnerProfile

User = get_user_model()

#: پیامِ عمومیِ خطایِ ورود — یکپارچه‌سازیِ احرازِ هویت: هرگز فاش نمی‌کند
#: شناسه (ایمیل/موبایل) وجود دارد یا رمز نادرست بوده — یکی از دو حالت را
#: نمی‌توان از روی پیام تشخیص داد.
GENERIC_LOGIN_ERROR = "اطلاعات ورود صحیح نیست."


class OwnerAuthError(Exception):
    """خطای قابل‌نمایش به کاربر در فرم ثبت‌نام/ورود/بازیابیِ رمزِ پرتال."""


class NewOwnerRegistrationClosedError(OwnerAuthError):
    """ثبت‌نامِ مالکِ تازه (``PlatformConfiguration.new_store_registration_enabled``)
    بسته است و این شماره هنوز هویتِ مالک ندارد."""


class OwnerAccountInactiveError(OwnerAuthError):
    """``User`` این شماره غیرفعال است؛ نه ورود انجام می‌شود نه چیزی ساخته می‌شود."""


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


def _looks_like_email(identifier: str) -> bool:
    return "@" in (identifier or "")


@transaction.atomic
def register_owner(*, full_name: str, email: str, password: str) -> User:
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


def authenticate_owner_by_identifier(request, *, identifier: str, password: str):
    """Authenticate with email, mobile number or username + password.

    This resolves *identity* only. Access to a specific merchant dashboard
    still requires an ACTIVE StoreMembership and a valid admin host, enforced
    by the existing handoff and dashboard permission layers. A plain Customer
    never gains merchant privileges simply by sharing a username or phone.

    Ambiguous case-insensitive identifiers fail closed instead of selecting
    an arbitrary account. Password validation remains Django's authenticate().
    """
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return None

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
                from apps.stores.models import StoreMembership

                candidate = User.objects.filter(username=phone).first()
                if candidate is not None and (
                    candidate.is_superuser
                    or StoreMembership.objects.filter(
                        user=candidate, status=StoreMembership.MembershipStatus.ACTIVE
                    ).exists()
                ):
                    user = candidate

    if user is None:
        # A legacy arbitrary username (including an email-shaped username
        # with no User.email) is allowed only for owner/staff identities.
        matches = list(User.objects.filter(username__iexact=identifier)[:2])
        if len(matches) != 1:
            return None
        candidate = matches[0]
        from apps.stores.models import StoreMembership

        if not (
            candidate.is_superuser
            or OwnerProfile.objects.filter(user=candidate).exists()
            or StoreMembership.objects.filter(
                user=candidate, status=StoreMembership.MembershipStatus.ACTIVE
            ).exists()
        ):
            return None
        user = candidate

    return authenticate(request, username=user.username, password=password)


def request_password_reset(*, email: str, base_url: str) -> None:
    """اگر ایمیل متعلق به کاربری باشد ایمیل بازیابی می‌فرستد؛ در غیر این صورت
    بی‌صدا کاری نمی‌کند — تا فرمِ عمومی هرگز فاش نکند کدام ایمیل ثبت‌نام کرده
    (enumeration-safety). ``base_url`` مثلِ ``"https://rastisi.ir"`` — بدونِ
    اسلش پایانی."""
    user = User.objects.filter(email__iexact=_normalize_email(email)).first()
    if user is None:
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


def get_user_from_reset_link(*, uidb64: str, token: str):
    """کاربر را از uid رمزگشایی‌شده برمی‌گرداند اگر توکن معتبر باشد، وگرنه None."""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user


@transaction.atomic
def set_new_password(*, user, password: str) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise OwnerAuthError(" ".join(exc.messages)) from exc
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
    فقط برنده ``owner_created=True`` می‌گیرد (و تنها او فروشگاهِ اول را می‌سازد)."""
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
            try:
                with transaction.atomic():
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
            try:
                with transaction.atomic():
                    OwnerProfile.objects.create(user=user, phone=phone, full_name=full_name)
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


def get_or_create_owner_by_phone(*, phone: str, full_name: str = "") -> tuple[User, bool]:
    """سازگاری با callerهایِ قدیمی (انتقالِ مالکیت و تست‌ها). خروجی
    ``(user, owner_created)`` است — یعنی «مالک» ساخته شد، نه صرفاً ``User``
    (معنایِ قبلی مبهم بود و مشتریِ موجود را به‌اشتباه «تازه نیست» می‌شمرد).
    رفتارِ قبلی (بدونِ رد کردنِ کاربرِ غیرفعال) حفظ شده تا انتقالِ مالکیت
    تغییر نکند. کدِ جدید باید مستقیم از :func:`resolve_owner_identity_by_phone`
    استفاده کند."""
    result = resolve_owner_identity_by_phone(phone=phone, full_name=full_name, require_active=False)
    return result.user, result.owner_created
