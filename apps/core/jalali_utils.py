"""ابزارهای تقویم جلالی — تنها منبعِ تبدیل جلالی↔میلادی برای کمپین‌ها،
مناسبت‌ها (تولد…) و ورودی‌های فرم.

سیاست‌های صریح:

* بازه‌ی «ماهِ X تا ماهِ Y» همیشه **کل** هر دو ماه را شامل می‌شود: از
  ۰۰:۰۰ روزِ اولِ ماهِ شروع تا (و بدونِ) ۰۰:۰۰ روزِ بعد از آخرین روزِ ماهِ
  پایان — بازه‌ی نیم‌باز ``[start, end)``، در منطقه‌ی زمانیِ فروشگاه.
* تولدِ ۳۰ اسفند در سالِ غیرکبیسه به **۲۹ اسفند** منتقل می‌شود (آخرین روزِ
  ماه)؛ تولدِ ۳۰ اسفند در سالِ کبیسه همان روز جشن گرفته می‌شود.
* کبیسه‌بودن از ``jdatetime`` (قاعده‌ی ۳۳ساله) گرفته می‌شود.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import jdatetime
from django.conf import settings

from apps.core.utils import normalize_digits


class JalaliDateError(ValueError):
    """تاریخِ جلالیِ نامعتبر — پیام برای نمایش به کاربر مناسب است."""


def store_timezone() -> ZoneInfo:
    """منطقه‌ی زمانیِ فروشگاه — فعلاً سراسریِ پروژه (``TIME_ZONE``)؛ هیچ
    فیلدِ منطقه‌ی زمانیِ per-store وجود ندارد."""
    return ZoneInfo(settings.TIME_ZONE)


def is_jalali_leap(year: int) -> bool:
    return jdatetime.date(year, 1, 1).isleap()


def jalali_days_in_month(year: int, month: int) -> int:
    if not 1 <= month <= 12:
        raise JalaliDateError("ماه باید بین ۱ تا ۱۲ باشد.")
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_jalali_leap(year) else 29


def jalali_to_gregorian(year: int, month: int, day: int) -> dt.date:
    if not 1 <= month <= 12:
        raise JalaliDateError("ماه باید بین ۱ تا ۱۲ باشد.")
    if not 1 <= day <= jalali_days_in_month(year, month):
        raise JalaliDateError("روزِ واردشده برای این ماه معتبر نیست.")
    return jdatetime.date(year, month, day).togregorian()


def gregorian_to_jalali(value: dt.date) -> tuple[int, int, int]:
    if isinstance(value, dt.datetime):
        value = value.date()
    jd = jdatetime.date.fromgregorian(date=value)
    return jd.year, jd.month, jd.day


def jalali_year_of(value: dt.date) -> int:
    return gregorian_to_jalali(value)[0]


def parse_jalali_date(raw: str) -> dt.date:
    """«۱۳۷۰/۰۵/۲۳» (یا با ``-``/``.``، ارقام فارسی/عربی/لاتین) → ``date`` میلادی.

    تاریخِ آینده/غیرمنطقی را این تابع رد نمی‌کند (فقط اعتبارِ تقویمی)؛
    محدوده‌ی منطقی (مثلاً تولد) را فراخوان بررسی می‌کند."""
    text = normalize_digits(raw or "").strip().replace("-", "/").replace(".", "/")
    parts = text.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise JalaliDateError("تاریخ را به صورت ۱۳۷۰/۰۵/۲۳ وارد کنید.")
    year, month, day = (int(p) for p in parts)
    if not 1200 <= year <= 1600:
        raise JalaliDateError("سالِ واردشده معتبر نیست.")
    return jalali_to_gregorian(year, month, day)


def format_jalali(value: dt.date | None, fmt: str = "%Y/%m/%d") -> str:
    if not value:
        return ""
    if isinstance(value, dt.datetime):
        value = value.astimezone(store_timezone()).date()
    return jdatetime.date.fromgregorian(date=value).strftime(fmt)


def jalali_month_range_bounds(
    year: int, start_month: int, end_month: int, tz: ZoneInfo | None = None,
) -> tuple[dt.datetime, dt.datetime]:
    """بازه‌ی ``[start, end)`` از اولِ ``start_month`` تا پایانِ کاملِ
    ``end_month`` (هر دو شاملِ کلِ ماه). ``end`` دقیقاً ۰۰:۰۰ روزِ بعد از
    آخرین روزِ ماهِ پایان است — پس سفارشی در ۲۳:۵۹:۵۹ آخرین روز داخل و
    سفارشِ ۰۰:۰۰ روزِ بعد خارج است."""
    if start_month > end_month:
        raise JalaliDateError("ماهِ شروع نباید بعد از ماهِ پایان باشد.")
    tz = tz or store_timezone()
    first_day = jalali_to_gregorian(year, start_month, 1)
    last_day = jalali_to_gregorian(year, end_month, jalali_days_in_month(year, end_month))
    start = dt.datetime.combine(first_day, dt.time.min, tzinfo=tz)
    end = dt.datetime.combine(last_day + dt.timedelta(days=1), dt.time.min, tzinfo=tz)
    return start, end


def jalali_date_range_bounds(
    start: dt.date, end: dt.date, tz: ZoneInfo | None = None,
) -> tuple[dt.datetime, dt.datetime]:
    """بازه‌ی نیم‌باز از ۰۰:۰۰ روزِ ``start`` تا ۰۰:۰۰ روزِ بعد از ``end``
    (هر دو میلادی و شاملِ کلِ روز) در منطقه‌ی زمانیِ فروشگاه."""
    if start > end:
        raise JalaliDateError("تاریخ شروع نباید بعد از تاریخ پایان باشد.")
    tz = tz or store_timezone()
    return (
        dt.datetime.combine(start, dt.time.min, tzinfo=tz),
        dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=tz),
    )


def birthday_month_day(value: dt.date) -> tuple[int, int]:
    """ماه/روزِ جلالیِ یک تاریخِ تولد (میلادی‌ذخیره‌شده)."""
    _, month, day = gregorian_to_jalali(value)
    return month, day


def birthday_month_day_key(value: dt.date | None) -> int | None:
    """کلیدِ عددیِ قابل‌ایندکس ``ماه*100+روز`` (مثلاً ۱۲۲۹) یا ``None``."""
    if value is None:
        return None
    month, day = birthday_month_day(value)
    return month * 100 + day


def occurrence_in_jalali_year(month: int, day: int, year: int) -> dt.date:
    """تاریخِ میلادیِ وقوعِ سالانه‌ی «ماه/روزِ جلالی» در یک سالِ جلالی —
    با سیاستِ ۳۰ اسفندِ غیرکبیسه ⇒ ۲۹ اسفند (و به‌طور کلی روزِ بیش از
    طولِ ماه ⇒ آخرین روزِ همان ماه)."""
    day = min(day, jalali_days_in_month(year, month))
    return jalali_to_gregorian(year, month, day)


def birthday_occurrence(birth_date: dt.date, year: int) -> dt.date:
    month, day = birthday_month_day(birth_date)
    return occurrence_in_jalali_year(month, day, year)


def month_day_keys_for_date(target: dt.date) -> list[int]:
    """همه‌ی کلیدهای ماه/روزِ جلالیِ تولد که در ``target`` جشن گرفته می‌شوند.

    معمولاً یک کلید است؛ برایِ ۲۹ اسفندِ سالِ غیرکبیسه کلیدِ ۱۲۳۰ هم
    اضافه می‌شود (سیاستِ انتقالِ ۳۰ اسفند)."""
    year, month, day = gregorian_to_jalali(target)
    keys = [month * 100 + day]
    if month == 12 and day == 29 and not is_jalali_leap(year):
        keys.append(1230)
    return keys
