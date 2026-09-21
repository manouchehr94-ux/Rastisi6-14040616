"""تولیدِ فاکتورِ تمدید (ADR-78).

برایِ اشتراک‌هایِ فعالِ نزدیک به پایانِ دوره، دقیقاً یک فاکتورِ تمدید به‌ازایِ
هر دوره ساخته می‌شود — idempotent (قیدِ یکتا رویِ subscription + دوره)، batch-
safe، با احترام به «لغو در پایانِ دوره» و رد کردنِ اشتراک‌هایِ نهایی‌شده. مبلغ
و ارز رویِ فاکتور از نسخه‌ی پلنِ جاری *فریز* می‌شوند."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.billing.services.period_utils import next_period_end
from apps.subscriptions.models import PlanVersion, StoreSubscription

#: وضعیت‌هایی که تمدید برایشان معنا دارد (دوره‌ی جاری دارند).
RENEWABLE_STATUSES = (
    StoreSubscription.Status.ACTIVE,
    StoreSubscription.Status.GRACE_PERIOD,
    StoreSubscription.Status.PAST_DUE,
)


def _lead_days(lead_days=None) -> int:
    if lead_days is not None:
        return lead_days
    return getattr(settings, "RASTISI_BILLING_RENEWAL_LEAD_DAYS", 3)


def _due_subscriptions(now, lead_days, store=None):
    cutoff = now + timezone.timedelta(days=lead_days)
    qs = (
        StoreSubscription.objects.filter(
            is_current=True, status__in=RENEWABLE_STATUSES,
            cancel_at_period_end=False,
            current_period_end__isnull=False, current_period_end__lte=cutoff,
        )
        .exclude(plan_version__billing_interval=PlanVersion.BillingInterval.NONE)
        .select_related("plan_version", "plan_version__plan", "store")
    )
    if store is not None:
        qs = qs.filter(store=store)
    return qs


@transaction.atomic
def _generate_one(subscription, *, now):
    """یک فاکتورِ تمدید برایِ دوره‌ی بعدیِ این اشتراک می‌سازد و باز می‌کند، اگر
    از قبل وجود نداشته باشد. ``(invoice, created)`` را برمی‌گرداند.

    ترتیبِ قفل (SUB-001 Repair 4، بازبینیِ مستقلِ معماری — ترمیمِ لازم):
    پیش‌تر این تابع ابتدا ``ScheduledPlanChange`` را قفل می‌کرد و سپس از
    طریقِ ``subscription_service.change_plan_version`` رویِ
    ``StoreSubscription`` قفل می‌گرفت — یعنی ترتیبِ Scheduled→Subscription،
    برعکسِ ترتیبِ کانونیکِ خودِ ``plan_change_billing_service.
    start_plan_change`` (که همیشه Subscription→Scheduled قفل می‌گیرد). این
    دو ترتیبِ معکوس زیرِ PostgreSQL می‌توانست deadlock بسازد. اکنون این تابع
    هم دقیقاً همان ترتیبِ کانونیک را رعایت می‌کند: ابتدا ``StoreSubscription``
    با ``select_for_update`` قفل می‌شود، سپس ``ScheduledPlanChange``ی همان
    اشتراک بررسی/قفل می‌شود، سپس هدفِ زمان‌بندی‌شده (اگر باشد) رویِ همان
    نمونه‌یِ قفل‌شده اعمال و ردیفِ زمان‌بندی‌شده حذف می‌شود، و بقیه‌ی کارِ
    تمدید با همان وضعیتِ اشتراکِ قفل‌شده/تازه ادامه می‌یابد."""
    from apps.billing.models import ScheduledPlanChange
    from apps.subscriptions.models import StoreSubscription
    from apps.subscriptions.services import subscription_service as sub_svc

    subscription = StoreSubscription.objects.select_for_update().get(pk=subscription.pk)

    # تنزلِ زمان‌بندی‌شده (ADR-80) در آغازِ دوره‌ی بعد اعمال می‌شود: نسخه‌ی پلن
    # به هدف سوییچ می‌شود و فاکتورِ تمدید با همان نسخه‌ی تازه ساخته می‌شود.
    scheduled = ScheduledPlanChange.objects.select_for_update().filter(subscription=subscription).first()
    if scheduled is not None:
        sub_svc.change_plan_version(
            subscription, scheduled.target_plan_version, reason="تنزلِ مؤثر در دوره‌ی بعد",
        )
        scheduled.delete()
        subscription.refresh_from_db()

    version = subscription.plan_version
    period_start = subscription.current_period_end
    period_end = next_period_end(period_start, version.billing_interval)

    existing = SubscriptionInvoice.objects.filter(
        subscription=subscription, kind=SubscriptionInvoice.Kind.RENEWAL,
        billing_period_start=period_start,
    ).first()
    if existing is not None:
        return existing, False

    try:
        invoice = invoice_service.create_invoice(
            subscription, kind=SubscriptionInvoice.Kind.RENEWAL, plan_version=version,
            currency=version.currency, period_start=period_start, period_end=period_end,
            lines=[invoice_service.plan_line_spec(version, period_start=period_start, period_end=period_end)],
            now=now,
        )
    except IntegrityError:
        # مسابقه: تولیدِ هم‌زمانِ همان دوره — همان فاکتور را برگردان.
        return SubscriptionInvoice.objects.get(
            subscription=subscription, kind=SubscriptionInvoice.Kind.RENEWAL,
            billing_period_start=period_start,
        ), False
    invoice = invoice_service.open_invoice(invoice, due_at=period_start, now=now)
    return invoice, True


def generate_renewals(*, now=None, store=None, lead_days=None, dry_run=False) -> dict:
    """فاکتورِ تمدید برایِ همه‌ی اشتراک‌هایِ سررسیدشده تولید می‌کند. ``dry_run``
    فقط می‌شمارد."""
    now = now or timezone.now()
    lead = _lead_days(lead_days)
    result = {"scanned": 0, "created": 0, "skipped_existing": 0}
    for subscription in _due_subscriptions(now, lead, store=store).iterator(chunk_size=200):
        result["scanned"] += 1
        if dry_run:
            existing = SubscriptionInvoice.objects.filter(
                subscription=subscription, kind=SubscriptionInvoice.Kind.RENEWAL,
                billing_period_start=subscription.current_period_end,
            ).exists()
            if existing:
                result["skipped_existing"] += 1
            else:
                result["created"] += 1
            continue
        _invoice, created = _generate_one(subscription, now=now)
        result["created" if created else "skipped_existing"] += 1
    return result
