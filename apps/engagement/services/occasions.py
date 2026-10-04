"""یافتنِ مشتریانِ مشمولِ یک مناسبت در یک روز.

``resolve_candidates(campaign, today)`` → ``{customer_id: cycle_key}``.
``cycle_key`` چرخه‌ی تکرارِ پاداش را تعیین می‌کند (مثلاً سالِ جلالیِ تولد) و
همراهِ یکتاییِ ``CampaignIssuance`` از صدورِ دوبارِ همان پاداش در همان چرخه
جلوگیری می‌کند.

* ``occasion_offset_days``: منفی = پیش از مناسبت، ۰ = همان روز، مثبت = پس از.
  یعنی تاریخِ مناسبت = ``today − offset``.
* تولدِ ۳۰ اسفندِ سالِ غیرکبیسه ⇒ ۲۹ اسفند (``jalali_utils``).
* مشتریانِ هر Store: فقط کسانی که با همین Store سفارش/پروفایل دارند.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from apps.core.jalali_utils import (
    gregorian_to_jalali, jalali_year_of, month_day_keys_for_date, occurrence_in_jalali_year, store_timezone,
)
from apps.customers.models import Customer
from apps.engagement.models import Campaign
from apps.engagement.services import rule_data

K = Campaign.Occasion


class OccasionError(ValueError):
    """پارامترهایِ مناسبت نامعتبر است."""


def validate_params(kind: str, params: dict) -> dict:
    params = params or {}
    if kind in (K.BIRTHDAY, K.REGISTRATION_ANNIVERSARY, K.FIRST_PURCHASE_ANNIVERSARY):
        return {}
    if kind == K.ORDER_MILESTONE:
        n = params.get("n")
        if not (isinstance(n, int) and n >= 1):
            raise OccasionError("تعدادِ سفارش برایِ نقطه‌ی عطف باید عددِ صحیحِ مثبت باشد.")
        return {"n": n}
    if kind == K.SPENDING_MILESTONE:
        try:
            amount = Decimal(str(params.get("amount")))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise OccasionError("مبلغِ نقطه‌ی عطف نامعتبر است.") from exc
        if amount <= 0 or amount != amount.to_integral_value():
            raise OccasionError("مبلغِ نقطه‌ی عطف باید عددِ صحیحِ مثبت باشد.")
        return {"amount": int(amount)}
    if kind == K.REACTIVATION:
        days = params.get("days")
        if not (isinstance(days, int) and days >= 1):
            raise OccasionError("تعدادِ روزِ عدمِ خرید باید عددِ صحیحِ مثبت باشد.")
        return {"days": days}
    if kind == K.HOLIDAY:
        month, day = params.get("month"), params.get("day")
        if not (isinstance(month, int) and 1 <= month <= 12 and isinstance(day, int) and 1 <= day <= 31):
            raise OccasionError("ماه/روزِ شمسی نامعتبر است.")
        if day > 30 and month > 6:
            raise OccasionError("روزِ واردشده برایِ این ماه معتبر نیست.")
        return {"month": month, "day": day}
    if kind == K.CUSTOM_DATE:
        try:
            date = dt.date.fromisoformat(str(params.get("date")))
        except ValueError as exc:
            raise OccasionError("تاریخِ مناسبت نامعتبر است.") from exc
        return {"date": date.isoformat()}
    raise OccasionError("نوعِ مناسبت نامعتبر است.")


def _store_customers(store):
    return rule_data.store_customer_ids(store)


def _anniversary_candidates(pairs, occasion_date, keys) -> dict:
    """``pairs``: ``(customer_id, datetime)`` — ماه/روزِ جلالیِ ``datetime`` با
    کلیدهایِ روزِ مناسبت یکی و حداقل یک سال گذشته باشد."""
    tz = store_timezone()
    year = jalali_year_of(occasion_date)
    out = {}
    for customer_id, when in pairs:
        if when is None:
            continue
        jy, jm, jd = gregorian_to_jalali(when.astimezone(tz).date())
        if jm * 100 + jd in keys and year > jy:
            out[customer_id] = str(year)
    return out


def resolve_candidates(campaign: Campaign, today: dt.date) -> dict[int, str]:
    store = campaign.store
    kind = campaign.occasion_kind
    params = campaign.occasion_params or {}
    occasion_date = today - dt.timedelta(days=campaign.occasion_offset_days)
    keys = month_day_keys_for_date(occasion_date)
    valid = campaign.valid_payment_statuses or ["paid"]
    customers = _store_customers(store)

    if kind == K.BIRTHDAY:
        ids = Customer.objects.filter(pk__in=customers, birth_month_day__in=keys).values_list("pk", flat=True)
        cycle = str(jalali_year_of(occasion_date))
        return {cid: cycle for cid in ids}

    if kind == K.REGISTRATION_ANNIVERSARY:
        pairs = Customer.objects.filter(pk__in=customers).values_list("pk", "created_at").iterator()
        return _anniversary_candidates(pairs, occasion_date, keys)

    if kind == K.FIRST_PURCHASE_ANNIVERSARY:
        from django.db.models import Min

        rows = (
            rule_data.valid_orders_qs(store, valid).values("customer_id").annotate(first=Min("created_at"))
            .values_list("customer_id", "first")
        )
        return _anniversary_candidates(rows, occasion_date, keys)

    if kind in (K.ORDER_MILESTONE, K.SPENDING_MILESTONE, K.REACTIVATION):
        from django.db.models import Count, Max, Sum

        stats = (
            rule_data.valid_orders_qs(store, valid).values("customer_id")
            .annotate(n=Count("id"), spent=Sum("grand_total"), last=Max("created_at"))
        )
        out = {}
        tz = store_timezone()
        for row in stats:
            if kind == K.ORDER_MILESTONE and row["n"] >= params["n"]:
                out[row["customer_id"]] = f"orders:{params['n']}"
            elif kind == K.SPENDING_MILESTONE and (row["spent"] or 0) >= params["amount"]:
                out[row["customer_id"]] = f"spent:{params['amount']}"
            elif kind == K.REACTIVATION:
                last_day = row["last"].astimezone(tz).date()
                if (today - last_day).days >= params["days"]:
                    out[row["customer_id"]] = f"inactive-since:{last_day.isoformat()}"
        return out

    if kind == K.HOLIDAY:
        jy = gregorian_to_jalali(today)[0]
        for year in (jy - 1, jy, jy + 1):
            if occurrence_in_jalali_year(params["month"], params["day"], year) == occasion_date:
                return {cid: str(year) for cid in customers}
        return {}

    if kind == K.CUSTOM_DATE:
        if dt.date.fromisoformat(params["date"]) == occasion_date:
            return {cid: params["date"] for cid in customers}
        return {}

    return {}


def notification_event_key(campaign: Campaign) -> str:
    """رویدادِ اعلانِ این کمپین. پیامِ هر ترکیبِ «زمان‌بندی × نوعِ هدیه» قالبِ مستقلِ پلتفرم دارد:
    پیامِ «فقط تبریک» هرگز وعده‌یِ هدیه/کد نمی‌دهد و پیامِ پیش/پس از مناسبت با زمانِ واقعیِ
    صدورِ پاداش سازگار است."""
    has_gift = campaign.reward_type == Campaign.Reward.COUPON
    if campaign.trigger_type != Campaign.Trigger.OCCASION:
        if not has_gift:
            return "campaign.announce"
        return {
            "percent": "campaign.offer_percent", "fixed": "campaign.offer_fixed",
        }.get(campaign.coupon_type, "campaign.offer_free_ship")
    offset = campaign.occasion_offset_days
    timing = "before" if offset < 0 else "after" if offset > 0 else "on"
    family = "birthday" if campaign.occasion_kind == K.BIRTHDAY else "generic"
    return _OCCASION_EVENT_KEYS[(family, timing, has_gift)]


_OCCASION_EVENT_KEYS = {
    ("birthday", "before", True): "occasion.birthday_before",
    ("birthday", "on", True): "occasion.birthday",
    ("birthday", "after", True): "occasion.birthday_after",
    ("birthday", "before", False): "occasion.birthday_before_greeting",
    ("birthday", "on", False): "occasion.birthday_greeting",
    ("birthday", "after", False): "occasion.birthday_after_greeting",
    ("generic", "before", True): "occasion.generic_before",
    ("generic", "on", True): "occasion.generic",
    ("generic", "after", True): "occasion.generic_after",
    ("generic", "before", False): "occasion.generic_before_greeting",
    ("generic", "on", False): "occasion.generic_greeting",
    ("generic", "after", False): "occasion.generic_after_greeting",
}
