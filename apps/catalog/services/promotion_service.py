"""مرجعِ واحدِ «تخفیفِ معتبر» برایِ کالا.

``Product.discount_percent`` همراه با بازه‌ی اختیاریِ
``discount_starts_at``/``discount_ends_at`` تعیین می‌کند آیا تخفیف *الان*
معتبر است. این ماژول همان قاعده را برای کوئری‌ها (ریل‌ها، فیلترها) و زمانِ
پایانِ تایمر ارائه می‌دهد تا هیچ مسیری قاعده را جداگانه تکرار نکند.
"""

from django.db.models import Q, QuerySet
from django.utils import timezone


def active_discount_q(now=None) -> Q:
    """کالاهایی که تخفیفشان الان معتبر *و قابل‌نمایش* است. کالای «استعلام قیمت»
    قیمت/تخفیفِ عمومی ندارد، پس هرگز در ریل‌های تخفیف نمی‌آید."""
    now = now or timezone.now()
    return (
        Q(is_price_inquiry=False)
        & Q(discount_percent__gt=0)
        & (Q(discount_starts_at__isnull=True) | Q(discount_starts_at__lte=now))
        & (Q(discount_ends_at__isnull=True) | Q(discount_ends_at__gt=now))
    )


def with_active_discount(queryset: QuerySet, now=None) -> QuerySet:
    """فقط کالاهایی که تخفیفِ آن‌ها در ``now`` معتبر است."""
    return queryset.filter(active_discount_q(now))


def earliest_discount_end(products, now=None):
    """زودترین پایانِ *آینده‌ی* تخفیفِ این کالاها، یا ``None`` اگر هیچ‌کدام
    پایانِ ثبت‌شده‌ای ندارند. تایمرِ «پیشنهاد شگفت‌انگیز» فقط از همین مقدارِ
    ذخیره‌شده ساخته می‌شود؛ هیچ مهلتِ ساختگی (مثلاً «الان + ۸ ساعت») وجود ندارد."""
    now = now or timezone.now()
    ends = [
        p.discount_ends_at
        for p in products
        if p.discount_ends_at is not None and p.discount_ends_at > now
    ]
    return min(ends) if ends else None


class PromotionError(ValueError):
    """درخواستِ نامعتبرِ شروعِ کمپین (مدت، درصد یا مالکیتِ کالا)."""


def start_promotion(store, products, *, hours, discount_percent=None, now=None) -> int:
    """شروعِ آگاهانه‌ی یک کمپین: بازه‌ی اعتبارِ تخفیفِ همه‌ی ``products`` را
    ``[now, now + hours)`` می‌کند (و اگر ``discount_percent`` داده شود، درصد را).

    این *تنها* جایی است که «N ساعت» به یک پایانِ ذخیره‌شده تبدیل می‌شود؛
    فراخوانی مجددِ آن همان «تمدید/بازتنظیمِ آگاهانه» است. کالاهایِ فروشگاهِ
    دیگر رد می‌شوند. تعدادِ کالاهایِ به‌روز‌شده را برمی‌گرداند."""
    from datetime import timedelta

    try:
        hours = int(hours)
    except (TypeError, ValueError):
        raise PromotionError("مدت کمپین باید عدد ساعت باشد.") from None
    if not 1 <= hours <= 24 * 90:
        raise PromotionError("مدت کمپین باید بین ۱ ساعت تا ۹۰ روز باشد.")
    if discount_percent is not None and not 1 <= int(discount_percent) <= 100:
        raise PromotionError("درصد تخفیف باید بین ۱ تا ۱۰۰ باشد.")
    now = now or timezone.now()
    ids = []
    for product in products:
        if product.store_id != store.pk:
            raise PromotionError("کالا متعلق به این فروشگاه نیست.")
        ids.append(product.pk)
    if not ids:
        return 0
    from apps.catalog.models import Product

    updates = {"discount_starts_at": now, "discount_ends_at": now + timedelta(hours=hours)}
    if discount_percent is not None:
        updates["discount_percent"] = int(discount_percent)
    return Product.objects.filter(store=store, pk__in=ids).update(**updates)


# ---------------------------------------------------------------------------------------------------------------
# RS-01 — کمپینِ زمان‌دار روی یک کالکشنِ موجود. مدلِ موازی نیست: همان فیلدهای ``Product.discount_percent`` /
# ``discount_starts_at`` / ``discount_ends_at`` (تنها منبعِ حقیقتِ قیمت و Deadline) برایِ اعضایِ کالکشن نوشته می‌شود.
# هیچ‌چیز خودکار اعمال نمی‌شود: فقط ``schedule_collection_promotion`` با تأییدِ صریحِ مالک آن را می‌نویسد.
# ---------------------------------------------------------------------------------------------------------------

MAX_CAMPAIGN_DAYS = 90


def _collection_products(collection):
    from apps.catalog.models import Product

    return Product.objects.filter(
        store_id=collection.store_id, collection_items__collection=collection,
    ).distinct()


def _classify(product, now) -> str:
    if product.is_price_inquiry:
        return "inquiry"
    if not product.discount_percent:
        return "none"
    if product.discount_ends_at is None:
        # بدونِ پایان ⇒ تخفیفِ ثابتِ خودِ کالا (نه کمپین)؛ کمپین/«پایان فوری» هرگز به آن دست نمی‌زند.
        return "standing"
    if product.discount_starts_at is not None and now < product.discount_starts_at:
        return "scheduled"
    if now >= product.discount_ends_at:
        return "ended"
    return "active"


def collection_promotion_summary(collection, now=None) -> dict:
    """وضعیتِ کمپینِ اعضایِ کالکشن: ``none`` / ``scheduled`` / ``active`` / ``ended`` به‌همراهِ شمارش و Deadlineِ واقعیِ
    ذخیره‌شده. فقط می‌خواند؛ هیچ مقداری نمی‌سازد."""
    now = now or timezone.now()
    products = list(_collection_products(collection))
    counts = {k: 0 for k in ("none", "scheduled", "active", "standing", "ended", "inquiry")}
    for product in products:
        counts[_classify(product, now)] += 1
    if counts["active"]:
        status = "active"
    elif counts["scheduled"]:
        status = "scheduled"
    elif counts["ended"]:
        status = "ended"
    else:
        status = "none"
    starts = [p.discount_starts_at for p in products if _classify(p, now) == "scheduled" and p.discount_starts_at]
    return {
        "status": status,
        "member_count": len(products),
        "counts": counts,
        "deadline": earliest_discount_end(products, now),
        "next_start": min(starts) if starts else None,
        "percents": sorted({p.discount_percent for p in products if p.discount_percent and not p.is_price_inquiry}),
    }


def _validate_campaign(discount_percent, starts_at, ends_at, now):
    try:
        percent = int(discount_percent)
    except (TypeError, ValueError):
        raise PromotionError("درصد تخفیف باید عدد باشد.") from None
    if not 1 <= percent <= 100:
        raise PromotionError("درصد تخفیف باید بین ۱ تا ۱۰۰ باشد.")
    if ends_at is None:
        raise PromotionError("زمان پایان کمپین را مشخص کنید؛ تایمر فقط از پایانِ واقعیِ ثبت‌شده ساخته می‌شود.")
    if timezone.is_naive(ends_at) or (starts_at is not None and timezone.is_naive(starts_at)):
        raise PromotionError("زمان‌ها باید با منطقه‌ی زمانی معتبر باشند.")
    starts_at = starts_at or now
    if ends_at <= starts_at:
        raise PromotionError("پایان کمپین باید بعد از شروع آن باشد.")
    if ends_at <= now:
        raise PromotionError("پایان کمپین باید در آینده باشد.")
    from datetime import timedelta

    if ends_at - starts_at > timedelta(days=MAX_CAMPAIGN_DAYS):
        raise PromotionError("مدت کمپین نباید بیشتر از ۹۰ روز باشد.")
    return percent, starts_at


def preview_collection_promotion(collection, *, discount_percent, starts_at, ends_at, now=None) -> dict:
    """بدون هیچ نوشتنی: چه تعداد کالا تغییر می‌کند و چه تعداد تخفیفِ فعلیِ متفاوتی دارند که جایگزین می‌شود."""
    now = now or timezone.now()
    percent, starts_at = _validate_campaign(discount_percent, starts_at, ends_at, now)
    eligible = [p for p in _collection_products(collection) if not p.is_price_inquiry]
    overwritten = [
        p for p in eligible
        if p.discount_percent and (
            p.discount_percent != percent or p.discount_starts_at != starts_at or p.discount_ends_at != ends_at
        )
    ]
    rows = [
        {"sku": p.sku, "name": p.name, "price": int(p.price), "now": p.final_price, "after": _price_after(p, percent),
         "changes_existing": bool(p.discount_percent) and (p.discount_percent != percent or p.discount_starts_at != starts_at or p.discount_ends_at != ends_at)}
        for p in eligible
    ]
    return {
        "rows": rows,
        "percent": percent, "starts_at": starts_at, "ends_at": ends_at,
        "eligible": len(eligible),
        "skipped_inquiry": sum(1 for p in _collection_products(collection) if p.is_price_inquiry),
        "overwritten": len(overwritten),
        "unchanged": sum(
            1 for p in eligible
            if (p.discount_percent, p.discount_starts_at, p.discount_ends_at) == (percent, starts_at, ends_at)
        ),
    }


def schedule_collection_promotion(collection, *, discount_percent, starts_at, ends_at, actor=None, now=None) -> dict:
    """نوشتنِ آگاهانه‌ی بازه‌ی کمپین برایِ اعضایِ *همین* کالکشن (هم‌فروشگاهی). کالاهایِ «استعلام قیمت» رد می‌شوند.
    تکرارِ همان ورودی اثرِ اضافه ندارد (idempotent)."""
    from django.db import transaction

    from apps.catalog.models import Product
    from apps.core.services.audit_service import record_audit_event

    now = now or timezone.now()
    percent, starts_at = _validate_campaign(discount_percent, starts_at, ends_at, now)
    with transaction.atomic():
        ids = list(
            Product.objects.select_for_update()
            .filter(pk__in=_collection_products(collection).values("pk"), store_id=collection.store_id, is_price_inquiry=False)
            .values_list("pk", flat=True)
        )
        before = collection_promotion_summary(collection, now)
        snapshot = {
            str(p.pk): [p.discount_percent, _iso(p.discount_starts_at), _iso(p.discount_ends_at)]
            for p in Product.objects.filter(store_id=collection.store_id, pk__in=ids)
        }
        updated = Product.objects.filter(store_id=collection.store_id, pk__in=ids).update(
            discount_percent=percent, discount_starts_at=starts_at, discount_ends_at=ends_at,
        )
        record_audit_event(
            store=collection.store, actor=actor, action_code="campaign.scheduled",
            object_type="MerchantCollection", object_id=collection.pk, object_label=collection.name,
            before={"status": before["status"], "percents": before["percents"]},
            after={"percent": percent, "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "products": updated},
            metadata={"snapshot": snapshot, "applied": {"percent": percent, "starts_at": _iso(starts_at), "ends_at": _iso(ends_at)}},
        )
    return {"updated": updated, "percent": percent, "starts_at": starts_at, "ends_at": ends_at}


def _iso(value):
    return value.isoformat() if value else None


def _from_iso(value):
    import datetime as _dt

    return _dt.datetime.fromisoformat(value) if value else None


def _price_after(product, percent) -> int:
    from decimal import ROUND_HALF_UP, Decimal

    factor = (Decimal(100) - Decimal(percent or 0)) / Decimal(100)
    return int((product.price * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def last_campaign_snapshot(collection):
    """آخرین کمپینِ ثبت‌شدهٔ همین کالکشن (از ردیفِ حسابرسی: مقادیرِ قبل/بعدِ هر کالا) یا ``None``. فقط برایِ «بازگرداندنِ تخفیفِ قبلی»."""
    from apps.core.models import AuditLogEntry

    entry = (
        AuditLogEntry.objects.filter(store=collection.store, action_code="campaign.scheduled", object_type="MerchantCollection",
                                     object_id=str(collection.pk)).order_by("-created_at", "-pk").first()
    )
    if entry is None or not (entry.metadata or {}).get("snapshot"):
        return None
    return entry.metadata


def preview_end_collection_promotion(collection, *, mode="end", now=None) -> dict:
    """بدونِ هیچ نوشتنی: دقیقاً کدام کالاها (SKU، قیمتِ فعلی ← قیمتِ پس از عملیات) تغییر می‌کنند و کدام‌ها دست‌نخورده می‌مانند.

    * ``end``: فقط کمپینِ زمان‌دار (دارایِ پایان) *همین الان* تمام می‌شود؛ تخفیفِ ثابتِ کالا (بدونِ پایان) و اعضایِ دیگر دست‌نخورده‌اند.
    * ``restore``: تخفیفِ *قبل از کمپین* برایِ کالاهایی که هنوز دقیقاً با مقدارِ کمپین هستند برمی‌گردد؛ کالایی که بعدِ کمپین ویرایش شده دست نمی‌خورد."""
    now = now or timezone.now()
    products = list(_collection_products(collection))
    rows, untouched = [], {"standing": 0, "changed_since": 0, "other": 0}
    if mode == "restore":
        snap = last_campaign_snapshot(collection)
        if snap is None:
            return {"mode": mode, "rows": [], "untouched": untouched, "available": False, "reason": "کمپینِ ثبت‌شده‌ای برای بازگرداندن پیدا نشد."}
        applied = snap["applied"]
        applied_t = (applied["percent"], _from_iso(applied["starts_at"]), _from_iso(applied["ends_at"]))
        before = snap["snapshot"]
        for p in products:
            prior = before.get(str(p.pk))
            if prior is None:
                untouched["other"] += 1
            elif (p.discount_percent, p.discount_starts_at, p.discount_ends_at) != applied_t:
                untouched["changed_since"] += 1
            else:
                bp, bs, be = prior
                rows.append({"sku": p.sku, "name": p.name, "price": int(p.price), "now": p.final_price, "after": _price_after(p, bp),
                             "pk": p.pk, "restore": (bp, _from_iso(bs), _from_iso(be))})
        return {"mode": mode, "rows": rows, "untouched": untouched, "available": True, "reason": ""}
    for p in products:
        state = _classify(p, now)
        if state in ("active", "scheduled"):
            rows.append({"sku": p.sku, "name": p.name, "price": int(p.price), "now": p.final_price, "after": int(p.price), "pk": p.pk})
        elif state == "standing":
            untouched["standing"] += 1
        else:
            untouched["other"] += 1
    return {"mode": mode, "rows": rows, "untouched": untouched, "available": bool(rows), "reason": "" if rows else "کمپینِ زمان‌دارِ فعال یا برنامه‌ریزی‌شده‌ای وجود ندارد."}


def end_collection_promotion(collection, *, actor=None, now=None, mode="end") -> dict:
    """پایانِ فوریِ *کمپین* (نه تخفیفِ ثابتِ کالاها). ``mode="end"``: ``discount_ends_at`` برایِ کالاهایِ دارایِ پایانِ فعال/برنامه‌ریزی‌شده
    «همین الان» می‌شود (درصد حذف نمی‌شود)؛ ``mode="restore"``: تخفیفِ قبل از کمپین بازگردانده می‌شود. کالاهایِ بدونِ پایان، کالاهایِ
    ویرایش‌شده پس از کمپین و فروشگاه‌هایِ دیگر هرگز تغییر نمی‌کنند."""
    from django.db import transaction

    from apps.catalog.models import Product
    from apps.core.services.audit_service import record_audit_event

    now = now or timezone.now()
    with transaction.atomic():
        plan = preview_end_collection_promotion(collection, mode=mode, now=now)
        updated = 0
        if mode == "restore":
            for row in plan["rows"]:
                percent, starts, ends = row["restore"]
                updated += Product.objects.filter(store_id=collection.store_id, pk=row["pk"]).update(
                    discount_percent=percent, discount_starts_at=starts, discount_ends_at=ends,
                )
        else:
            updated = Product.objects.filter(store_id=collection.store_id, pk__in=[r["pk"] for r in plan["rows"]]).update(discount_ends_at=now)
        record_audit_event(
            store=collection.store, actor=actor, action_code="campaign.restored" if mode == "restore" else "campaign.ended",
            object_type="MerchantCollection", object_id=collection.pk, object_label=collection.name,
            after={"products": updated, "at": now.isoformat(), "untouched": plan["untouched"]},
        )
    return {"updated": updated, "untouched": plan["untouched"]}


__all__ = [
    "active_discount_q", "with_active_discount", "earliest_discount_end", "start_promotion", "PromotionError",
    "collection_promotion_summary", "preview_collection_promotion", "schedule_collection_promotion",
    "end_collection_promotion", "preview_end_collection_promotion", "last_campaign_snapshot", "MAX_CAMPAIGN_DAYS",
]
