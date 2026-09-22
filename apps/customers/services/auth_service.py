"""لایه‌ی سرویس احراز هویت — ثبت‌نام، ورود (موبایل + رمز) و ادغام سبد مهمان.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۵. شناسه‌ی ورود شماره موبایل
است (آماده برای جایگزینی رمز با کد یکبارمصرف در فازهای بعد)؛ نام کاربری داخلی
جنگو برای کاربران جدید همان شماره موبایل است، اما به آن گره نخورده‌ایم — ورود
همیشه از روی Customer.phone انجام می‌شود تا با کاربران seed (با نام کاربری
دلخواه) هم سازگار باشد.

ادغام «علاقه‌مندی‌ها»ی مهمان معنا ندارد چون Wishlist (مرحله‌ی ۱) از ابتدا فقط
برای کاربر واردشده تعریف شده و session_key ندارد؛ مهمان اصلاً نمی‌تواند پیش از
ورود چیزی به علاقه‌مندی اضافه کند.
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.crypto import get_random_string

from apps.cart.models import Cart
from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.customers.models import Customer
from apps.sms.events import SmsEvent
from apps.sms.services.sms_service import send_event_sms

User = get_user_model()

GUEST_PASSWORD_LENGTH = 24

#: پیامِ عمومیِ خطایِ ورود — یکپارچه‌سازیِ احرازِ هویت: هرگز فاش نمی‌کند
#: شناسه (ایمیل/موبایل) وجود دارد یا رمز نادرست بوده.
GENERIC_LOGIN_ERROR = "اطلاعات ورود صحیح نیست."


class AuthError(Exception):
    """خطای قابل‌نمایش به کاربر در فرم ورود/ثبت‌نام."""


@transaction.atomic
def signup(*, full_name: str, phone: str, password: str, store) -> Customer:
    """``store`` الزامی است — همان Store که برای پیامک خوش‌آمدگویی استفاده می‌شود."""
    if Customer.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
        raise AuthError("این شماره موبایل قبلاً ثبت‌نام کرده است")
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise AuthError(" ".join(exc.messages)) from exc

    user = User.objects.create_user(username=phone, password=password)
    customer = Customer.objects.create(user=user, full_name=full_name, phone=phone)
    transaction.on_commit(
        lambda: send_event_sms(SmsEvent.WELCOME, phone, {"customer_name": full_name}, store=store)
    )
    return customer


@transaction.atomic
def create_account_for_guest(*, full_name: str, phone: str, store) -> Customer:
    """برای مهمانی که در تسویه‌حساب با شماره‌ی بدون حساب خرید می‌کند، حساب خودکار می‌سازد.

    رمز عبور تصادفی و امن تولید می‌شود (کاربر هرگز آن را نمی‌بیند)؛ ورودهای
    بعدی این کاربر معمولاً از طریق کد یکبار مصرف پیامکی (نه رمز) خواهد بود،
    پس نیازی به validate_password روی رمز تصادفی خودمان نیست. ``store``
    الزامی است — همان Store که برای پیامک خوش‌آمدگویی استفاده می‌شود.
    """
    random_password = get_random_string(GUEST_PASSWORD_LENGTH)
    user = User.objects.create_user(username=phone, password=random_password)
    customer = Customer.objects.create(user=user, full_name=full_name, phone=phone)
    transaction.on_commit(
        lambda: send_event_sms(SmsEvent.WELCOME, phone, {"customer_name": full_name}, store=store)
    )
    return customer


def authenticate_customer(request, *, phone: str, password: str):
    """با موبایل و رمز احراز هویت می‌کند و در صورت موفقیت User را برمی‌گرداند، وگرنه None."""
    customer = Customer.objects.select_related("user").filter(phone=phone).first()
    if customer is None:
        return None
    return authenticate(request, username=customer.user.username, password=password)


def _looks_like_email(identifier: str) -> bool:
    return "@" in (identifier or "")


def authenticate_customer_by_identifier(request, *, identifier: str, password: str):
    """احرازِ هویتِ یکپارچه — شناسه می‌تواند ایمیل یا شماره موبایل باشد
    (یکپارچه‌سازیِ احرازِ هویت). ``Customer.phone`` یکتاست، اما ``Customer.
    email`` نه — پس اگر بیش از یک مشتری همان ایمیل را داشته باشد (یا هیچ‌
    کدام)، این تابع صادقانه ``None`` برمی‌گرداند (ابهام هرگز حدس زده
    نمی‌شود)، دقیقاً مثلِ شناسه‌ی ناموجود یا رمزِ نادرست — هیچ‌کدام از
    بیرون قابلِ تشخیص نیست."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return None

    if _looks_like_email(identifier):
        matches = list(Customer.objects.select_related("user").filter(email__iexact=identifier)[:2])
        if len(matches) != 1:
            return None
        customer = matches[0]
    else:
        try:
            phone = normalize_iranian_phone(identifier)
        except InvalidPhoneError:
            return None
        customer = Customer.objects.select_related("user").filter(phone=phone).first()
        if customer is None:
            return None

    return authenticate(request, username=customer.user.username, password=password)


@transaction.atomic
def merge_guest_cart(request, customer: Customer) -> None:
    """سبد خرید مهمان (بر اساس session_key) را با سبد کاربر واردشده ادغام می‌کند."""
    session_key = request.session.session_key
    if not session_key:
        return
    guest_cart = Cart.objects.filter(session_key=session_key, customer__isnull=True).first()
    if guest_cart is None:
        return

    user_cart, _ = Cart.objects.get_or_create(customer=customer)

    # CAT-002 حصارِ عضویت (membership fence) — این مسیر عضویتِ ``user_cart``
    # را عوض می‌کند (انتقالِ یک CartItem با ``item.cart = user_cart`` یا
    # افزایشِ تعدادِ یک قلمِ موجود). پیش از هر تغییرِ عضویت، خودِ ردیفِ
    # ``user_cart`` را قفل کن تا اگر تسویه‌حسابی روی همین Cart در جریان
    # باشد، این ادغام تا آزادشدنِ آن فنس مسدود بماند (و برعکس) — پس هیچ‌گاه
    # یک قلمِ منتقل‌شده بینِ اسنپ‌شاتِ نهاییِ تسویه‌حساب و commit سر نمی‌خورد.
    # این مسیر Product/Variant را قفل نمی‌کند، پس ترتیبِ قفلِ آن صرفاً
    # Cart → CartItem است و با ترتیبِ کلیِ Product/Variant → Cart → CartItem
    # سازگار می‌ماند (بدونِ وارونگیِ بن‌بست). فقط ``user_cart`` (هدفِ
    # عضویت) قفل می‌شود؛ ``guest_cart`` در پایان حذف می‌شود و هدفِ هیچ
    # تسویه‌حسابِ هم‌زمانی نیست.
    user_cart = Cart.objects.select_for_update().get(pk=user_cart.pk)

    for item in guest_cart.items.select_related("product", "variant"):
        existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
        if existing:
            existing.quantity += item.quantity
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            item.cart = user_cart
            item.save(update_fields=["cart", "updated_at"])
    guest_cart.delete()
