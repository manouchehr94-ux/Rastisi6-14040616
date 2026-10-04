import jdatetime
from django import template

from apps.core.utils import format_toman, to_fa_digits

register = template.Library()


@register.filter
def fa_number(value):
    """اعداد لاتین را به ارقام فارسی تبدیل می‌کند: 123 -> ۱۲۳"""
    if value is None:
        return ""
    return to_fa_digits(value)


@register.filter
def toman(value):
    """قیمت را با جداکننده‌ی هزارگان فارسی و واحد «تومان» نمایش می‌دهد."""
    return format_toman(value)


@register.filter
def toman_raw(value):
    """قیمت را فقط با جداکننده‌ی هزارگان فارسی، بدون واحد «تومان»، نمایش می‌دهد."""
    return format_toman(value, with_unit=False)


@register.filter
def jalali(value, fmt="%Y/%m/%d"):
    """تاریخ میلادی را به تاریخ شمسی (جلالی) با ارقام فارسی تبدیل می‌کند."""
    if not value:
        return ""
    try:
        jd = jdatetime.date.fromgregorian(date=value)
    except (TypeError, ValueError):
        return ""
    return to_fa_digits(jd.strftime(fmt))


@register.filter
def jalali_input(value):
    """مقدارِ فیلدِ تاریخ برایِ ``<input>``: ``date`` میلادی → ``۱۳۷۰/۰۵/۲۳``؛ متنِ
    کاربر (خطایِ اعتبارسنجی) دست‌نخورده برگردانده می‌شود."""
    import datetime as _dt

    if not value:
        return ""
    if isinstance(value, _dt.date):
        return to_fa_digits(jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d"))
    return value
