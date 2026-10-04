"""لایه‌ی سرویسِ هویتِ مالک — ثبت‌نام، ورود با موبایل/ایمیل/نام کاربری و بازیابی رمز.

عمداً از ``apps.customers.services.auth_service`` جداست (ADR-93): آن سرویس
مشتریِ فروشگاه می‌سازد (شناسه = موبایل، همیشه به یک ``store`` وابسته است)؛
این‌جا مالکِ پلتفرم ساخته می‌شود (شناسه = ایمیل، مستقل از هر Store‌ای —
مالک قبل از ساختِ اولین Store هم باید بتواند ثبت‌نام کند).
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
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


@transaction.atomic
def get_or_create_owner_by_phone(*, phone: str, full_name: str = "") -> tuple[User, bool]:
    """شناسه‌ی اصلیِ ورودِ مالک اکنون موبایل+OTP است (Section 3، جایگزینِ
    ایمیل+رمز به‌عنوانِ روشِ اصلی — ایمیل+رمز فقط برایِ حساب‌هایِ قدیمی/
    بازیابی/مدیرِ پلتفرم نگه داشته شده، نه حذف شده).

    تصمیمِ عمدیِ هویتِ مشترک: چون ``apps.customers`` هم از ``User.username =
    phone`` استفاده می‌کند، شماره‌ی یکسان طبیعتاً به همان ردیفِ ``User``
    می‌رسد — نه یک ادغامِ نسنجیده، بلکه این‌که یک شماره‌ی موبایلِ تأییدشده با
    OTP، اثباتِ هویتیِ به همان اندازه (یا قوی‌تر از) رمزِ عبورِ مشتری است؛
    همان شخصِ واقعی صرفاً قابلیتِ «مالک» را هم به همان حساب اضافه می‌کند
    (``OwnerProfile`` ساخته می‌شود اگر نبود)، نه اینکه دو حسابِ جدا یا حسابِ
    یتیم بسازد. اگر آن User از قبل ``Customer`` هم داشته باشد، همان‌طور
    دست‌نخورده می‌ماند — این تابع هرگز آن را تغییر نمی‌دهد.

    خروجی: ``(user, created)`` — ``created`` یعنی این User تازه ساخته شد
    (نه اینکه OwnerProfile تازه بود)."""
    profile = OwnerProfile.objects.select_related("user").filter(phone=phone).first()
    if profile is not None:
        return profile.user, False

    user = User.objects.filter(username=phone).select_for_update().first()
    created = user is None
    if user is None:
        user = User.objects.create_user(username=phone)
        user.set_unusable_password()
        user.save(update_fields=["password"])

    existing_profile = OwnerProfile.objects.filter(user=user).first()
    if existing_profile is None:
        OwnerProfile.objects.create(user=user, phone=phone, full_name=full_name.strip())
    elif not existing_profile.phone:
        # A first-time phone attach for a User that already had an
        # OwnerProfile (e.g. registered by email earlier) — never overwrite
        # an already-set full_name with an empty one just because this
        # particular call (typically a login, not the registration form)
        # didn't collect a name.
        existing_profile.phone = phone
        if full_name.strip():
            existing_profile.full_name = full_name.strip()
        existing_profile.save(update_fields=["phone", "full_name", "updated_at"])
    return user, created
