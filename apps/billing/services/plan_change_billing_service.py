"""صورتحسابِ تغییرِ پلن — بدونِ پروریشنِ جعلی (ADR-80).

سیاستِ صادقانه:
- **ارتقا** (قیمتِ هدف > قیمتِ فعلی): نیازمندِ پرداخت. یک فاکتورِ «تغییرِ پلن»
  برایِ مبلغِ کاملِ نسخه‌ی هدف ساخته و باز می‌شود؛ نسخه‌ی پلنِ اشتراک تا
  *پرداختِ کاملِ* آن فاکتور عوض نمی‌شود (تأیید در ``confirmation_service``).
- **تنزل / قیمتِ برابر**: در دوره‌ی بعد اثر می‌کند. یک ``ScheduledPlanChange``
  ثبت می‌شود که هنگامِ تولیدِ فاکتورِ تمدید اعمال می‌گردد؛ هیچ مبلغی گرفته و
  هیچ Entitlementی بلافاصله کم نمی‌شود.

محافظت در برابرِ پیش‌نمایشِ کهنه (5A) حفظ می‌شود."""

from decimal import Decimal

from django.db import transaction

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import plan_change_service as pcs


class PlanChangeBillingError(Exception):
    """خطای قابل‌نمایش هنگام صورتحسابِ تغییرِ پلن."""


def is_upgrade(current_version, target_version) -> bool:
    return Decimal(target_version.display_price) > Decimal(current_version.display_price)


def preview(subscription, target_version) -> dict:
    """پیش‌نمایشِ 5A را با اطلاعاتِ صورتحساب (ارتقا/تنزل + مبلغِ قابلِ‌پرداخت)
    غنی می‌کند."""
    base = pcs.preview_plan_change(subscription.store, target_version)
    upgrade = is_upgrade(base["current_version"], target_version)
    base["is_upgrade"] = upgrade
    base["billing_effect"] = "upgrade_requires_payment" if upgrade else "downgrade_next_period"
    base["payable_amount"] = Decimal(target_version.display_price) if upgrade else Decimal("0")
    return base


@transaction.atomic
def start_plan_change(subscription, target_version, *, preview_token, actor=None, now=None):
    """تغییرِ پلن را آغاز می‌کند. برایِ ارتقا ``("invoice", invoice)`` و برایِ
    تنزل ``("scheduled", scheduled_change)`` برمی‌گرداند. توکنِ کهنه رد می‌شود.

    ایمنیِ هم‌زمانی (SUB-001، بازبینیِ معماری): پیش از هر بررسی/نوشتنِ دیگری،
    ``StoreSubscription`` جاری با ``select_for_update`` قفل می‌شود — صرفِ
    ``transaction.atomic`` دو درخواستِ هم‌زمان را serialize نمی‌کند؛ این قفل
    آن را تضمین می‌کند (دو ترانزاکشنِ هم‌زمانی که همین ردیف را قفل می‌کنند
    به‌ترتیب اجرا می‌شوند، نه هم‌پوشان).

    ایده‌پوتنسیِ مالی (اصلاحِ بازبینیِ مستقلِ معماری): برایِ ارتقا، اگر یک
    فاکتورِ ``PLAN_CHANGE`` هنوز قابلِ‌پرداخت (``PAYABLE_STATUSES``) برایِ
    *همینِ تصمیم* از قبل وجود داشته باشد، همان بازگردانده می‌شود — سندِ مالیِ
    تازه‌ای ساخته نمی‌شود. «همینِ تصمیم» یعنی همینِ اشتراک + همینِ **وضعیتِ
    منبع** (نسخه‌ی پلنِ فعلی + زمانِ آخرین تغییرِ اشتراک، همان اثرانگشتی که
    ``_preview_token`` می‌سازد) + همینِ نسخه‌ی هدف — نه صرفاً همینِ رکوردِ
    ``StoreSubscription`` (که وقتی ``plan_version``اش عوض می‌شود همان pk را
    نگه می‌دارد). اگر اشتراک بینِ دو فراخوانی از حالتِ منبعِ دیگری (مثلاً یک
    override دستیِ مدیرِ پلتفرم) عبور کرده باشد، فاکتورِ متعلق به تصمیمِ
    منبعِ *قدیمی* هرگز برایِ تصمیمِ *تازه* دوباره استفاده نمی‌شود، حتی اگر
    هدف یکسان باشد — چون اثرانگشتِ منبع دیگر یکسان نیست. این تصمیمِ
    کسب‌وکاری را با یک فاکتورِ باطل‌شده/بسته‌شده‌ی مالی (VOID/PAID/...) که
    Store قصدِ تلاشِ دوباره دارد اشتباه نمی‌گیرد — آن‌ها هرگز دوباره استفاده
    نمی‌شوند، حتی اگر اثرانگشتِ منبعشان هم‌خوان باشد."""
    # عمداً از رویِ Store دوباره resolve می‌شود (نه صرفاً ``subscription.pk``ی
    # ورودی) تا اگر همین لحظه یک تغییرِ هم‌زمانِ دیگر اشتراکِ جاری را عوض کرده
    # باشد (مثلاً پایانِ تریال/لغو)، همیشه دقیقاً همان ردیفی که *الان* جاری
    # است قفل و بررسی شود — درست مثلِ رفتارِ قبلیِ
    # ``pcs.ent.get_current_subscription``، فقط این‌بار زیرِ قفل.
    current = (
        StoreSubscription.objects.select_for_update()
        .filter(store=subscription.store_id, is_current=True)
        .first()
    )
    if current is None:
        raise PlanChangeBillingError("اشتراکِ جاری یافت نشد.")
    # محافظتِ پیش‌نمایشِ کهنه (همان توکنِ 5A) — روی نسخه‌ی *قفل‌شده* بررسی
    # می‌شود تا یک تغییرِ هم‌زمانِ دیگر (که تا همین لحظه منتظرِ همین قفل بود)
    # همیشه به‌درستی توکن را کهنه ببیند.
    expected = pcs._preview_token(current, target_version)
    if not preview_token or preview_token != expected:
        raise pcs.StalePreviewError("پیش‌نمایش دیگر معتبر نیست؛ دوباره پیش‌نمایش بگیرید.")

    if is_upgrade(current.plan_version, target_version):
        # ارتقا: یک فاکتورِ قابلِ‌پرداختِ تغییرِ پلن که متعلق به همینِ *تصمیمِ
        # منبع* است (همینِ اشتراک + همینِ اثرانگشتِ وضعیتِ منبع/هدف، یعنی
        # ``expected`` که همین بالا محاسبه و تأیید شد) را دوباره برمی‌گرداند
        # به‌جایِ ساختنِ سندِ تکراری. عمداً رویِ ``idempotency_key`` (نه صرفاً
        # subscription+target) فیلتر می‌شود: ``StoreSubscription`` هنگامِ
        # تغییرِ ``plan_version``اش همان pk را نگه می‌دارد، پس «همینِ اشتراک و
        # همینِ هدف» به‌تنهایی کافی نیست — یک تصمیمِ منبعِ *قدیمی* (پیش از یک
        # override/تغییرِ داخلیِ دیگر) هرگز نباید فاکتورِ تصمیمِ *تازه* را
        # جا بزند، حتی اگر هدف یکسان باشد.
        existing_payable = SubscriptionInvoice.objects.filter(
            subscription=current, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=target_version,
            idempotency_key=expected, status__in=SubscriptionInvoice.PAYABLE_STATUSES,
        ).order_by("-created_at").first()
        if existing_payable is not None:
            return "invoice", existing_payable

        # ``idempotency_key`` عمداً به ``invoice_service.create_invoice``
        # پاس داده نمی‌شود: بررسیِ idempotency‌ی خودِ آن تابع فقط رویِ
        # store+idempotency_key است (بدونِ فیلترِ وضعیت) و فاکتورِ
        # باطل‌شده‌ی هم‌فاکتورِ قبلی (VOID) را هم برمی‌گرداند — دقیقاً همان
        # رفتاری که اینجا صریحاً نمی‌خواهیم (فاکتورِ باطل‌شده هرگز دوباره
        # استفاده نمی‌شود). به‌جایش، پس از ساختن، اثرانگشت را مستقیماً رویِ
        # همین فاکتورِ تازه می‌نویسیم.
        invoice = invoice_service.create_invoice(
            current, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=target_version,
            currency=target_version.currency,
            lines=[invoice_service.plan_line_spec(
                target_version, description=f"ارتقا به {target_version.plan.name}",
            )],
            now=now,
        )
        invoice.idempotency_key = expected
        invoice.save(update_fields=["idempotency_key", "updated_at"])
        invoice = invoice_service.open_invoice(invoice, now=now)
        record_audit_event(
            store=current.store, actor=actor, action_code="billing.plan_change_invoiced",
            object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
            after={"target_version": target_version.pk, "amount": str(invoice.grand_total)},
        )
        return "invoice", invoice

    # تنزل/برابر: زمان‌بندی برایِ دوره‌ی بعد — ``update_or_create`` رویِ
    # ``OneToOneField(subscription)`` خودش idempotent است (یک تغییرِ
    # زمان‌بندی‌شده به‌ازایِ هر اشتراک)، پس تکرارِ همین درخواست فقط همان
    # ردیف را به‌روزرسانی می‌کند، نه ردیفِ تازه.
    scheduled, _created = ScheduledPlanChange.objects.update_or_create(
        subscription=current,
        defaults={"store": current.store, "target_plan_version": target_version},
    )
    record_audit_event(
        store=current.store, actor=actor, action_code="billing.plan_change_scheduled",
        object_type="ScheduledPlanChange", object_id=scheduled.pk, object_label=target_version.plan.code,
        after={"target_version": target_version.pk, "effective": "next_period"},
    )
    return "scheduled", scheduled
