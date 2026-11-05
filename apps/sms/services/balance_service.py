"""اعتبارِ پیامکِ Store و خریدِ بسته — لایه‌ی سرویسِ ``SmsBalance``/
``SmsPackage``/``SmsPackagePurchase`` (نگاه کنید به داکیومنتِ آن مدل‌ها
برای سیاستِ کاملِ کسر/تکمیل)."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import SmsBalance, SmsCreditAdjustment, SmsCreditLedger, SmsPackage, SmsPackagePurchase


def get_or_create_balance(*, store) -> SmsBalance:
    balance, _created = SmsBalance.objects.get_or_create(store=store)
    return balance


def deduct_credit(*, store) -> None:
    """Helper قدیمی برای سازگاری تست/کدهای قبلی.

    مسیر ارسال واقعی دیگر از این تابع استفاده نمی‌کند؛ قبل از تماس Provider
    از ``billing_policy_service.reserve_credits`` استفاده می‌شود تا ارسال عادی
    بدون موجودی مسدود و OTP فقط تا سقف بدهی مجاز شود.
    """
    get_or_create_balance(store=store)
    SmsBalance.objects.filter(store=store).update(credits=F("credits") - 1)


class InvalidAdjustmentError(Exception):
    """اصلاحِ درخواست‌شده معتبر نیست (مثلاً بدونِ دلیل یا تغییرِ صفر)."""


@transaction.atomic
def adjust_credit(*, store, delta: int, reason: str, note: str = "", actor=None) -> SmsCreditAdjustment:
    """اعتبارِ Store را به‌صورتِ دستی تغییر می‌دهد و یک ردیفِ دفترِ اصلاح
    (``SmsCreditAdjustment``) با مقدارِ قبل/تغییر/بعد ثبت می‌کند — تنها راهِ
    مجازِ Platform Admin برایِ تغییرِ اعتبار، هرگز نوشتنِ مستقیمِ فیلد."""
    if delta == 0:
        raise InvalidAdjustmentError("مقدارِ تغییر نمی‌تواند صفر باشد.")
    if not reason.strip():
        raise InvalidAdjustmentError("دلیلِ اصلاح الزامی است.")

    balance = SmsBalance.objects.select_for_update().filter(store=store).first()
    if balance is None:
        balance = get_or_create_balance(store=store)
        balance = SmsBalance.objects.select_for_update().get(pk=balance.pk)

    before = balance.credits
    after = before + delta
    balance.credits = after
    balance.save(update_fields=["credits", "updated_at"])

    return SmsCreditAdjustment.objects.create(
        store=store, actor=actor, delta=delta, balance_before=before, balance_after=after,
        reason=reason.strip(), note=note.strip(),
    )


def list_active_packages():
    return SmsPackage.objects.filter(is_active=True).order_by("display_order", "credit_amount")


def request_purchase(*, store, package: SmsPackage) -> SmsPackagePurchase:
    """درخواستِ خریدِ یک بسته را با وضعیتِ ``pending`` ثبت می‌کند — اعتباری
    فوراً افزوده نمی‌شود (نگاه کنید به ``SmsPackagePurchase`` docstring)."""
    return SmsPackagePurchase.objects.create(
        store=store, package=package,
        credit_amount=package.credit_amount, price=package.price,
    )


class PurchaseNotPendingError(Exception):
    """فقط خریدهای در وضعیتِ pending قابلِ تکمیل/لغو هستند."""


class PurchaseRefundError(Exception):
    """بازپرداختِ خرید ممکن نیست (وضعیت/اعتبارِ مصرف‌شده)."""


def _locked_balance(store):
    balance = get_or_create_balance(store=store)
    return SmsBalance.objects.select_for_update().get(pk=balance.pk)


@transaction.atomic
def complete_purchase(*, purchase: SmsPackagePurchase, attempt=None, actor=None) -> SmsPackagePurchase:
    """تنها مسیرِ افزودنِ اعتبارِ خرید — از Platform Admin (دستی) یا پس از پرداختِ آنلاینِ **تأییدشده**
    (``attempt``). با قفلِ ردیفِ خرید و موجودی، idempotent و بدونِ از دست رفتنِ به‌روزرسانی:
    وضعیتِ غیرِ pending خطا می‌دهد، و قیدِ یکتایِ دفتر ``(purchase, kind)`` حتی در صورتِ باگ از
    افزودنِ دوباره جلوگیری می‌کند. هر افزودن یک ردیفِ ``SmsCreditLedger`` دارد."""
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PurchaseNotPendingError("این خرید در وضعیتِ در انتظار نیست")

    balance = _locked_balance(locked.store)
    before = balance.credits
    after = before + locked.credit_amount
    balance.credits = after
    balance.save(update_fields=["credits", "updated_at"])

    SmsCreditLedger.objects.create(
        store=locked.store, purchase=locked, payment_attempt=attempt, actor=actor,
        kind=SmsCreditLedger.Kind.PURCHASE, delta=locked.credit_amount,
        balance_before=before, balance_after=after,
        note="پرداخت آنلاینِ تأییدشده" if attempt is not None else "تکمیلِ دستی توسطِ مدیرِ پلتفرم",
    )
    locked.status = SmsPackagePurchase.Status.COMPLETED
    locked.completed_at = timezone.now()
    locked.save(update_fields=["status", "completed_at", "updated_at"])
    return locked


@transaction.atomic
def cancel_purchase(*, purchase: SmsPackagePurchase) -> SmsPackagePurchase:
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.PENDING:
        raise PurchaseNotPendingError("این خرید در وضعیتِ در انتظار نیست")
    locked.status = SmsPackagePurchase.Status.CANCELED
    locked.save(update_fields=["status", "updated_at"])
    return locked


@transaction.atomic
def reverse_purchase_credits(*, purchase: SmsPackagePurchase, actor=None, note: str = "") -> SmsPackagePurchase:
    """بازگرداندنِ اعتبارِ یک خریدِ تکمیل‌شده (بازپرداخت). فقط اگر **کلِ** اعتبارِ بسته هنوز در موجودیِ
    Store هست (مصرف‌نشده)؛ در غیرِ این صورت خطا — تصمیمِ مالیِ «بازپرداختِ جزئی/اعتبارِ مصرف‌شده» یک
    سیاستِ تأییدنشده است و خودکار گرفته نمی‌شود. موجودی هرگز منفی نمی‌شود. دقیقاً یک‌بار (قیدِ یکتا)."""
    locked = SmsPackagePurchase.objects.select_for_update().get(pk=purchase.pk)
    if locked.status != SmsPackagePurchase.Status.COMPLETED:
        raise PurchaseRefundError("فقط خریدِ تکمیل‌شده قابلِ بازپرداخت است.")
    if SmsCreditLedger.objects.filter(purchase=locked, kind=SmsCreditLedger.Kind.PURCHASE_REVERSAL).exists():
        raise PurchaseRefundError("اعتبارِ این خرید پیش‌تر بازگردانده شده است.")

    balance = _locked_balance(locked.store)
    if balance.credits < locked.credit_amount:
        raise PurchaseRefundError(
            "بخشی از اعتبارِ این بسته مصرف شده؛ بازپرداخت نیازمندِ تصمیمِ مالیِ دستی است."
        )
    before = balance.credits
    after = before - locked.credit_amount
    balance.credits = after
    balance.save(update_fields=["credits", "updated_at"])
    SmsCreditLedger.objects.create(
        store=locked.store, purchase=locked, actor=actor, kind=SmsCreditLedger.Kind.PURCHASE_REVERSAL,
        delta=-locked.credit_amount, balance_before=before, balance_after=after,
        note=(note or "بازپرداختِ خرید")[:300],
    )
    locked.status = SmsPackagePurchase.Status.REFUNDED
    locked.refunded_at = timezone.now()
    locked.save(update_fields=["status", "refunded_at", "updated_at"])
    return locked
