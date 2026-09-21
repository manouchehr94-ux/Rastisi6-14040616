"""پیش‌نمایش و اجرایِ تغییرِ پلن برایِ Merchant Admin (ADR-70/71/72).

تغییرِ پلن یک عملِ دومرحله‌ای است: (۱) پیش‌نمایش که تفاوتِ قابلیت‌ها و
هشدارهایِ تنزل (متریک‌هایی که مصرفِ فعلی از سقفِ پلنِ هدف بیشتر است) را نشان
می‌دهد و یک «توکنِ پیش‌نمایش» تولید می‌کند؛ (۲) اجرا که فقط اگر توکن با
وضعیتِ فعلیِ اشتراک هم‌خوان باشد انجام می‌شود — در غیر این صورت پیش‌نمایش
کهنه شده (اشتراک بینِ پیش‌نمایش و اجرا تغییر کرده) و اجرا رد می‌شود تا کاربر
تصمیمی بر اساسِ داده‌ی قدیمی نگیرد.

در Checkpoint 5A هیچ پولی جابه‌جا نمی‌شود (ADR-72) — تغییرِ پلن فقط
Entitlementها را عوض می‌کند. جمع‌آوریِ پرداختِ آنلاین کارِ Checkpoint 5B است.
"""

import hashlib

from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import EntitlementDefinition, PlanVersion
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc
from apps.subscriptions.services import usage_service as usage


class PlanChangeError(Exception):
    """خطای قابل‌نمایش هنگام پیش‌نمایش/اجرایِ تغییرِ پلن."""


class StalePreviewError(PlanChangeError):
    """پیش‌نمایش کهنه شده — اشتراک از زمانِ تولیدِ پیش‌نمایش تغییر کرده است."""


def _preview_token(subscription, target_version) -> str:
    """توکنی که وضعیتِ اشتراک (نسخه‌ی پلن + زمانِ آخرین تغییر) و نسخه‌ی هدف را
    اثرانگشت می‌کند؛ اگر هرکدام عوض شود توکن دیگر هم‌خوان نیست."""
    raw = (
        f"{subscription.pk}:{subscription.plan_version_id}:"
        f"{subscription.updated_at.isoformat()}:{target_version.pk}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _entitlement_value(store, key, entitlement_type, *, plan_version):
    """مقدارِ قابل‌مقایسه‌ی یک Entitlement رویِ یک نسخه‌ی پلن. برایِ boolean یک
    bool، برایِ سقف‌ها ``None`` (نامحدود)/``0`` (خاموش)/عدد."""
    if entitlement_type == EntitlementDefinition.EntitlementType.BOOLEAN:
        return ent.has_entitlement(store, key, plan_version=plan_version)
    return ent.get_entitlement_limit(store, key, plan_version=plan_version)


def preview_plan_change(store, target_version) -> dict:
    """تفاوتِ قابلیت‌ها و هشدارهایِ تنزل را بینِ پلنِ فعلی و ``target_version``
    محاسبه می‌کند و یک توکنِ پیش‌نمایش برمی‌گرداند.

    اگر Store اشتراکِ جاری نداشته باشد یا نسخه‌ی هدف منتشرشده نباشد
    ``PlanChangeError`` می‌اندازد."""
    subscription = ent.get_current_subscription(store)
    if subscription is None:
        raise PlanChangeError("این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
    if target_version.status != PlanVersion.Status.PUBLISHED:
        raise PlanChangeError("فقط نسخه‌ی «منتشرشده» را می‌توان انتخاب کرد.")

    current_version = subscription.plan_version
    is_same = current_version.pk == target_version.pk

    # تفاوتِ Entitlementها
    entitlement_changes = []
    definitions = {d.key: d for d in EntitlementDefinition.objects.filter(is_active=True)}
    for key, definition in definitions.items():
        current_value = _entitlement_value(store, key, definition.entitlement_type, plan_version=current_version)
        target_value = _entitlement_value(store, key, definition.entitlement_type, plan_version=target_version)
        if current_value != target_value:
            entitlement_changes.append({
                "key": key,
                "name": definition.name,
                "type": definition.entitlement_type,
                "current": current_value,
                "target": target_value,
            })

    # هشدارهایِ تنزل: متریک‌هایی که مصرفِ فعلی از سقفِ پلنِ هدف بیشتر است.
    over_limit_warnings = []
    for key, label in {**ekeys.COUNT_METRIC_KEYS, **ekeys.PERIOD_METRIC_KEYS}.items():
        target_limit = ent.get_entitlement_limit(store, key, plan_version=target_version)
        if target_limit is None:
            continue  # نامحدود در پلنِ هدف — هشداری نیست
        if key in ekeys.COUNT_METRIC_KEYS:
            current_usage = usage.get_count_usage(store, key)
        else:
            current_usage = usage.get_period_usage(store, key)
        if current_usage > target_limit:
            over_limit_warnings.append({
                "key": key,
                "label": label,
                "current": current_usage,
                "target_limit": target_limit,
            })

    return {
        "subscription": subscription,
        "current_version": current_version,
        "current_plan": current_version.plan,
        "target_version": target_version,
        "target_plan": target_version.plan,
        "is_same": is_same,
        "entitlement_changes": entitlement_changes,
        "over_limit_warnings": over_limit_warnings,
        "has_downgrade_risk": bool(over_limit_warnings),
        "token": _preview_token(subscription, target_version),
    }


def execute_platform_admin_plan_override(store, target_version, *, actor, reason="", idempotency_key=""):
    """SUB-001 (بازبینیِ مستقلِ معماری، Repair 2) — مرزِ صریحِ overrideِ
    اپراتوریِ مدیرِ پلتفرم: نسخه‌ی پلنِ اشتراکِ جاریِ ``store`` را بلافاصله و
    بدونِ فاکتور/پرداخت عوض می‌کند (بدونِ preview_token — این یک تصمیمِ
    مستقلِ عملیاتیِ مدیرِ پلتفرم است، نه یک خریدِ مرچنت که نیازمندِ محافظتِ
    پیش‌نمایشِ کهنه‌ی 5A باشد).

    این تابع مستقیماً از همان پرایمیتیوِ سطحِ‌پایینِ چرخه‌ی‌حیاتی که تأییدِ
    پرداخت/تمدید هم از آن عبور می‌کنند صدا می‌زند
    (``subscription_service.change_plan_version``) — یک موتورِ صورتحسابِ
    دوم یا یک انشعابِ منطقیِ تازه ساخته نمی‌شود. (SUB-001 Repair 3: تابعِ
    عمومیِ قدیمیِ ``execute_plan_change`` — که preview_token را بررسی
    می‌کرد و سپس بلافاصله بدونِ صورتحساب تغییرِ پلن می‌داد — کاملاً حذف
    شده است؛ هیچ نقطه‌ی ورودِ تولیدیِ دیگری با همین معنا
    («preview_token معتبرِ مرچنت → تغییرِ فوریِ بدونِ صورتحساب») در این
    فایل باقی نمانده.)

    ایمنی (Master Architecture Ledger — «امتیازاتِ پلتفرم» یک دامنه‌یِ
    امنیتیِ کاملاً جدا از «مجوزدهیِ Store-scopedِ مرچنت» است، نه یک نقشِ
    StoreMembership تازه):

    * ``actor`` الزامی است و باید دقیقاً همان معیارِ سه‌بخشیِ کانونیکِ
      ``apps.portal.platform_admin_views._is_platform_staff`` را برآورده
      کند: ``is_authenticated and is_staff and is_superuser`` (SUB-001،
      بازبینیِ مستقلِ معماری، Repair 3 — نسخه‌ی قبلی فقط
      ``is_authenticated and is_superuser`` را بررسی می‌کرد، ضعیف‌تر از
      مرزِ کانونیکِ Platform Admin و ناهم‌خوان با مستندسازیِ خودش). این
      تابع عمداً خودِ ``_is_platform_staff`` را import نمی‌کند —
      ``apps.portal.platform_admin_views`` در سطحِ ماژول از
      ``apps.subscriptions`` وارد می‌کند، پس importِ برعکس از این‌جا به
      آن ویو یک import cycle می‌سازد؛ به‌جایش همان سه‌شرط مستقیماً اینجا
      هم بررسی می‌شود (نه یک رجیستریِ مجوزِ دومی — صرفاً تکرارِ همان
      معیارِ Django staff/superuser).
    * نسخه‌ی پلنِ هدف باید «منتشرشده» باشد.
    * اشتراکِ جاری باید وجود داشته باشد.
    * SUB-001 Repair 3 — قبل از هرگونه تغییرِ فوری، اگر یک فاکتورِ
      ``PLAN_CHANGE`` هنوز قابلِ‌پرداخت برایِ همینِ اشتراک وجود داشته باشد،
      override رد می‌شود (``PlanChangeError``): یک تصمیمِ مالیِ حل‌نشده
      نباید توسطِ یک overrideِ اپراتوریِ بی‌ارتباط با پرداخت، بی‌اثر/کهنه
      شود. مدیرِ پلتفرم باید ابتدا آن فاکتور را از طریقِ چرخه‌ی کانونیکِ
      صورتحساب (مثلاً ``invoice_service.void_invoice``) حل کند.
    * ``StoreMembership``/``ROLE_PERMISSIONS``یِ مرچنت — از جمله
      ``SUBSCRIPTION_CHANGE`` — هرگز دسترسی به این override نمی‌دهد؛ این
      تابع صراحتاً یک override اپراتوری است، نه یک مسیرِ جایگزینِ خریدِ
      مرچنت.

    ترتیبِ قفل (SUB-001 Repair 3، بازبینیِ ترتیبِ قفل): این تابع، همانندِ
    ``plan_change_billing_service.start_plan_change``، ابتدا
    ``StoreSubscription`` جاری را با ``select_for_update`` قفل می‌کند —
    پیش از هر بررسیِ فاکتورِ رقیب. سپس بررسیِ وجودِ فاکتورِ رقیبِ
    قابلِ‌پرداخت یک خوانشِ *بدونِ قفل* رویِ ``SubscriptionInvoice`` است (نه
    ``select_for_update``) — تنها سازنده‌ی فاکتورهایِ ``PLAN_CHANGE``
    (``start_plan_change``) خودش پیش از ساختن، همینِ ردیفِ اشتراک را قفل
    می‌کند، پس نگه‌داشتنِ همین قفل کافی است تا هیچ ``start_plan_change``ی
    هم‌زمان نتواند وسطِ ساختنِ فاکتور باشد — بدونِ نیاز به قفلِ اضافی رویِ
    فاکتور. این هرگز ترتیبِ قفلِ ``confirm_payment``
    (Attempt→Invoice→Subscription) را معکوس نمی‌کند، چون هرگز منتظرِ قفلِ
    Invoice/Attempt نمی‌ماند — فقط می‌خواند."""
    if (
        actor is None
        or not getattr(actor, "is_authenticated", False)
        or not getattr(actor, "is_staff", False)
        or not getattr(actor, "is_superuser", False)
    ):
        raise PlanChangeError("این عملیات فقط برایِ مدیرِ پلتفرمِ احرازشده (staff + superuser) مجاز است.")
    from django.db import transaction as _transaction

    from apps.subscriptions.models import StoreSubscription

    with _transaction.atomic():
        locked_subscription = (
            StoreSubscription.objects.select_for_update()
            .filter(store=store, is_current=True)
            .first()
        )
        if locked_subscription is None:
            raise PlanChangeError("این فروشگاه اشتراکِ جاری ندارد؛ تغییرِ پلن ممکن نیست.")
        if target_version.status != PlanVersion.Status.PUBLISHED:
            raise PlanChangeError("فقط نسخه‌ی «منتشرشده» را می‌توان انتخاب کرد.")

        from apps.billing.models import SubscriptionInvoice

        if SubscriptionInvoice.objects.filter(
            subscription=locked_subscription, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
            status__in=SubscriptionInvoice.PAYABLE_STATUSES,
        ).exists():
            raise PlanChangeError(
                "یک فاکتورِ تغییرِ پلنِ حل‌نشده برایِ این فروشگاه وجود دارد؛ "
                "پیش از overrideِ فوری، آن فاکتور را باطل یا حل کنید."
            )

        updated = svc.change_plan_version(
            locked_subscription, target_version, actor=actor, reason=reason, idempotency_key=idempotency_key,
        )
    ent.clear_entitlement_cache()
    return updated
