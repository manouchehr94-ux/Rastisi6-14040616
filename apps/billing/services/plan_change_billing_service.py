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


def supersede_scheduled_plan_change(subscription, *, actor=None, reason="", replacement_intent=""):
    """پیاده‌سازیِ کانونیک و **تنها** برایِ لغو/جانشین‌سازیِ یک
    ``ScheduledPlanChange`` حل‌نشده (SUB-001، تصمیمِ معمار — ناوردایِ
    «حداکثر یک تصمیمِ تغییرِ پلنِ حل‌نشده به‌ازایِ هر اشتراک»: یا یک
    ``ScheduledPlanChange`` یا یک فاکتورِ قابلِ‌پرداختِ ``PLAN_CHANGE``، هرگز
    هر دو هم‌زمان).

    هرگاه یک تصمیمِ *اجراشده*‌یِ تازه (ارتقایِ پرداختیِ واقعاً اجراشده، یک
    overrideِ فوریِ مدیرِ پلتفرم، یا یک همگراییِ دفاعیِ داده‌یِ ناهم‌خوانِ
    تاریخی) جایِ یک تنزل/برابرِ زمان‌بندی‌شده‌یِ حل‌نشده را می‌گیرد، همه‌ی
    فراخوان‌ها باید دقیقاً از همینجا عبور کنند — نه یک منطقِ حذفِ موازیِ
    دیگر در جایِ دیگری از کد. پیش از حذفِ ردیف، یک رخدادِ حسابرسی با کدِ
    ``billing.plan_change_schedule_superseded`` (فروشگاه، هدفِ قدیمیِ
    زمان‌بندی‌شده، actor، دلیل، و نوعِ تصمیمِ جانشین) ثبت می‌شود — تا این
    جانشینی هیچ‌وقت بی‌ردِپا نباشد.

    اگر برایِ این اشتراک اصلاً ``ScheduledPlanChange``ای وجود نداشته باشد
    کاری نمی‌کند (idempotent) و ``None`` برمی‌گرداند — پس می‌توان این تابع
    را بی‌قیدوشرط، پیش از هر تصمیمِ تازه‌یِ اجراشده، فراخوانی کرد.

    ترتیبِ قفل: فراخواننده باید از قبل ``StoreSubscription`` را با
    ``select_for_update`` قفل کرده باشد (ترتیبِ کانونیکِ SUB-001:
    Subscription → Scheduled) — این تابع خودش رویِ همان ردیفِ
    ``ScheduledPlanChange`` (نه رویِ اشتراک) ``select_for_update`` می‌گیرد؛
    چون این ردیف یک ``OneToOneField(subscription)`` است، هیچ ترتیبِ قفلِ
    دیگری وارد نمی‌شود و هرگز منتظرِ قفلِ ``SubscriptionInvoice`` نمی‌ماند.

    مهم: باطل/ناموفق‌شدنِ بعدیِ تصمیمِ جانشین (مثلاً VOIDِ فاکتورِ ارتقایِ
    تازه) هرگز به‌صورتِ خودکار این تنزلِ جانشین‌شده را احیا نمی‌کند — مرچنت
    در صورتِ نیاز باید صریحاً دوباره تنزلی را زمان‌بندی کند."""
    scheduled = ScheduledPlanChange.objects.select_for_update().filter(subscription=subscription).first()
    if scheduled is None:
        return None
    record_audit_event(
        store=scheduled.store, actor=actor, action_code="billing.plan_change_schedule_superseded",
        object_type="ScheduledPlanChange", object_id=scheduled.pk,
        object_label=scheduled.target_plan_version.plan.code,
        before={"target_version": scheduled.target_plan_version_id},
        metadata={"reason": reason, "replacement_intent": replacement_intent},
    )
    scheduled.delete()
    return scheduled


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

    ناوردایِ تصمیمِ واحد (SUB-001، تصمیمِ معمار): برایِ هر ``StoreSubscription``
    در هر لحظه حداکثر یک تصمیمِ تغییرِ پلنِ حل‌نشده می‌تواند وجود داشته باشد —
    یا یک ``ScheduledPlanChange`` (تنزل/برابر — بدونِ پول) یا یک فاکتورِ
    قابلِ‌پرداختِ ``PLAN_CHANGE`` (ارتقا — پرداختی)، هرگز هر دو هم‌زمان.
    «پیش‌نمایش» هیچ‌چیزی را جانشین نمی‌کند؛ فقط **اجرا** (همینجا) مرزِ
    جانشینیِ تصمیم است:

    * اگر این فراخوانی به ارتقا برسد و یک ``ScheduledPlanChange`` قدیمی
      برایِ همینِ اشتراک موجود باشد، آن تنزلِ اجراشده‌یِ قدیمی‌تر توسطِ همینِ
      ارتقایِ تازه‌ی *اجراشده* جانشین/حذف می‌شود (از طریقِ
      ``supersede_scheduled_plan_change`` — با ثبتِ حسابرسی) پیش از ساختن/
      بازیابیِ فاکتور؛ هرگز پشتِ تصمیمِ تازه باقی نمی‌ماند تا در تمدیدِ بعدی
      بی‌صدا آن را برگرداند.
    * اگر این فراخوانی به تنزل/برابر برسد در حالی‌که یک فاکتورِ
      ``PLAN_CHANGE`` قابلِ‌پرداخت از قبل برایِ همینِ اشتراک باز است،
      ``PlanChangeBillingError`` می‌اندازد — بدونِ ساختن/به‌روزرسانیِ هیچ
      ``ScheduledPlanChange``ای، بدونِ تغییرِ پلن، بدونِ تغییرِ فاکتور. یک
      سندِ مالیِ باز فقط از طریقِ چرخه‌یِ کانونیکِ خودش (پرداخت یا
      ``invoice_service.void_invoice``) حل می‌شود — هرگز به‌صورتِ خودکار
      به‌خاطرِ یک درخواستِ تنزلِ تازه باطل نمی‌شود.

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

        # SUB-001 Repair 3 (ناوردایِ مالی): در هر لحظه حداکثر *یک* فاکتورِ
        # ``PLAN_CHANGE`` قابلِ‌پرداخت به‌ازایِ هر اشتراک مجاز است. اگر
        # فاکتورِ تطبیق‌یافته‌ی بالا (همینِ اثرانگشتِ منبع/هدف) پیدا نشد اما
        # یک فاکتورِ ``PLAN_CHANGE`` قابلِ‌پرداختِ *دیگری* برایِ همینِ اشتراک
        # از قبل باز است — چه هدفش فرق داشته باشد (مثلاً A→C باز است و حالا
        # A→D درخواست شده) چه اثرانگشتِ منبعش قدیمی باشد — این یک تصمیمِ
        # مالیِ حل‌نشده‌ی رقیب است: نباید سندِ دومی ساخته شود، نباید فاکتورِ
        # قدیمی بی‌صدا تصاحب/بازتخصیص شود، و نباید خودکار شارژ/تغییری داده
        # شود. کاربر باید صریحاً منتظرِ حل شدن (پرداخت) یا باطل‌کردنِ آن
        # فاکتور بمانَد؛ فقط سپس تصمیمِ تازه می‌تواند فاکتورِ تازه‌ی خودش را
        # بسازد. این بررسی زیرِ همان قفلِ ``StoreSubscription``ی است که همین
        # بالا گرفته شد، پس با هیچ ``start_plan_change``ی هم‌زمانِ دیگر race
        # نمی‌کند (تنها سازنده‌ی این فاکتورها همینجاست، و آن هم پیش از
        # نوشتن همینِ قفل را می‌گیرد). این بررسی عمداً *بعد* از
        # ``existing_payable`` است — یک فاکتورِ رقیبِ واقعی هرگز با همینِ
        # فاکتورِ همینِ‌تصمیم یکی نیست، پس این حذفِ ``existing_payable``
        # (``exclude(idempotency_key=expected)``) هرگز تصمیمِ همین
        # فاکتور را رقیب حساب نمی‌کند.
        if SubscriptionInvoice.objects.filter(
            subscription=current, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
            status__in=SubscriptionInvoice.PAYABLE_STATUSES,
        ).exclude(idempotency_key=expected).exists():
            raise PlanChangeBillingError(
                "یک فاکتورِ تغییرِ پلنِ حل‌نشده برایِ این اشتراک وجود دارد؛ "
                "پیش از درخواستِ تغییرِ تازه، آن فاکتور را پرداخت یا باطل کنید."
            )

        # ناوردایِ تصمیمِ واحد (تصمیمِ معمار — ترمیمِ لبه‌ایِ ضروری): این ارتقا
        # واقعاً در حالِ *اجرا*شدن است (نه صرفِ پیش‌نمایش) — چه یک فاکتورِ
        # تازه ساخته شود چه همینِ فاکتورِ همین‌تصمیمِ از‌قبل‌موجود
        # (``existing_payable``) به‌صورتِ ایده‌پوتنت دوباره استفاده شود، هر دو
        # حالت یک «اجرایِ معتبرِ ارتقا» هستند. پس هر ``ScheduledPlanChange``
        # قدیمی‌تر (تنزل/برابرِ حل‌نشده) باید همینجا — پیش از هر دو مسیرِ
        # بازگشت، نه فقط مسیرِ ساختنِ فاکتورِ تازه — جانشین شود؛ در
        # غیرِاین‌صورت (مثلاً داده‌یِ ناهم‌خوانِ تاریخی که یک
        # ``ScheduledPlanChange`` بعداً و بیرون از این تابع کنارِ یک فاکتورِ
        # از‌قبل‌موجود ساخته شده) یک اجرایِ *تکراریِ* همینِ تصمیمِ ارتقا هرگز
        # به مسیرِ ساختنِ فاکتورِ تازه نمی‌رسید و آن تنزلِ زمان‌بندی‌شده پشتِ
        # تصمیمِ ارتقا باقی می‌ماند تا در تمدیدِ بعدی بی‌صدا آن را برگرداند.
        supersede_scheduled_plan_change(
            current, actor=actor, reason="ارتقایِ اجراشده جایِ تنزلِ زمان‌بندی‌شده را گرفت",
            replacement_intent=f"upgrade:{target_version.pk}",
        )

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

    # ناوردایِ تصمیمِ واحد (تصمیمِ معمار، جهتِ مخالف): اگر یک فاکتورِ
    # ``PLAN_CHANGE`` قابلِ‌پرداخت از قبل برایِ همینِ اشتراک باز است، یک
    # درخواستِ تنزل/برابرِ تازه هرگز نباید آن سندِ مالی را به‌صورتِ خودکار
    # بی‌اثر/باطل کند یا کنارش یک ``ScheduledPlanChange`` تازه بسازد —
    # مرچنت باید ابتدا آن تصمیمِ مالی را صریحاً حل کند (پرداخت یا
    # ``invoice_service.void_invoice``).
    if SubscriptionInvoice.objects.filter(
        subscription=current, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
        status__in=SubscriptionInvoice.PAYABLE_STATUSES,
    ).exists():
        raise PlanChangeBillingError(
            "یک فاکتورِ تغییرِ پلنِ حل‌نشده برایِ این اشتراک وجود دارد؛ "
            "پیش از زمان‌بندیِ تنزل/برابر، آن فاکتور را پرداخت یا باطل کنید."
        )

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
