"""محاسبه‌ی مرزِ دوره‌ی صورتحساب از روی ``billing_interval`` نسخه‌ی پلن.

از افزودنِ تقویمیِ ماه/سال استفاده می‌کند (نه صرفاً ۳۰/۳۶۵ روز)، با کلمپِ روز
برایِ ماه‌هایِ کوتاه‌تر (مثلاً ۳۱ فروردین + ۱ ماه → آخرِ ماهِ بعد)."""

import calendar

from apps.subscriptions.models import PlanVersion


def _add_months(dt, months):
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def next_period_end(start, billing_interval):
    """پایانِ دوره را از ``start`` بر اساسِ فاصله برمی‌گرداند؛ برایِ فاصله‌ی
    ``none`` (رایگان/legacy) ``None`` برمی‌گرداند."""
    months = PlanVersion.INTERVAL_MONTHS.get(billing_interval)
    if months:
        return _add_months(start, months)
    return None
