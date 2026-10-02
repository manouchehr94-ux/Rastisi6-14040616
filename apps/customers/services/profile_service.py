"""به‌روزرسانیِ پروفایلِ مشتری: تاریخ تولد و ترجیحاتِ ارتباطی.

سیاستِ تولد:

* ورودیِ جلالی (``۱۳۷۰/۰۵/۲۳``) یا میلادی (``1991-08-14``)؛ در ``Customer.birth_date``
  به‌صورتِ میلادی ذخیره می‌شود (قراردادِ تاریخ‌هایِ پروژه).
* ورودیِ **خالی هرگز** تولدِ ذخیره‌شده را پاک نمی‌کند.
* تاریخِ آینده یا بیش از ۱۲۰ سال پیش رد می‌شود.
* سوءاستفاده از تغییرِ تولد برایِ دریافتِ پاداشِ مکرر: پاداشِ هر چرخه‌ی سالانه
  با یکتاییِ (کمپین، مشتری، سالِ جلالی) محدود است، نه به تاریخِ ثبت‌شده.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.core.jalali_utils import JalaliDateError, parse_jalali_date, store_timezone

MAX_AGE_YEARS = 120


class BirthDateError(ValueError):
    """ورودیِ تاریخ تولد نامعتبر — پیام برایِ نمایش به کاربر مناسب است."""


def parse_birth_date(raw) -> dt.date | None:
    """متنِ ورودی → ``date`` میلادی؛ خالی → ``None``؛ نامعتبر → ``BirthDateError``."""
    if isinstance(raw, dt.date):
        value = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return None
        from apps.core.utils import normalize_digits

        normalized = normalize_digits(text).replace("/", "-").replace(".", "-")
        try:
            head = int(normalized.split("-")[0])
        except ValueError as exc:
            raise BirthDateError("تاریخ تولد را به صورت ۱۳۷۰/۰۵/۲۳ وارد کنید.") from exc
        try:
            value = dt.date.fromisoformat(normalized) if head >= 1700 else parse_jalali_date(text)
        except (ValueError, JalaliDateError) as exc:
            raise BirthDateError(f"تاریخ تولد معتبر نیست. {exc}" if isinstance(exc, JalaliDateError) else "تاریخ تولد معتبر نیست.") from exc
    today = timezone.now().astimezone(store_timezone()).date()
    if value > today:
        raise BirthDateError("تاریخ تولد نمی‌تواند در آینده باشد.")
    if (today.year - value.year) > MAX_AGE_YEARS:
        raise BirthDateError("تاریخ تولد معتبر نیست.")
    return value


def update_birth_date(customer, raw) -> bool:
    """تولد را فقط وقتی ورودیِ معتبرِ غیرخالی هست ذخیره می‌کند. → آیا تغییر کرد."""
    value = parse_birth_date(raw)
    if value is None or customer.birth_date == value:
        return False
    customer.birth_date = value
    customer.save(update_fields=["birth_date", "updated_at"])
    return True


def update_communication_preferences(customer, *, sms: bool | None = None, email: bool | None = None) -> bool:
    fields = []
    if sms is not None and customer.accepts_promotional_sms != sms:
        customer.accepts_promotional_sms = sms
        fields.append("accepts_promotional_sms")
    if email is not None and customer.accepts_promotional_email != email:
        customer.accepts_promotional_email = email
        fields.append("accepts_promotional_email")
    if fields:
        customer.save(update_fields=fields + ["updated_at"])
    return bool(fields)
