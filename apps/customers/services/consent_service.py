"""سیاستِ واحدِ رضایتِ تبلیغاتی (پیامک/ایمیل) — تنها نقطه‌ی تغییر و ارزیابی.

* رضایتِ نامعلوم = عدمِ رضایت؛ فقط ``accepts_promotional_<ch> is True`` رضایتِ ثبت‌شده است (مدرکِ قدیمیِ
  بدونِ شواهد در مهاجرتِ ``customers.0007`` به False/``legacy_unverified`` رفت).
* کانال‌ها مستقل‌اند؛ هر تغییر منبع (``Customer.ConsentSource``) و زمان ثبت می‌کند و (وقتی ``store`` معلوم است)
  در دفترِ حسابرسیِ موجود می‌نشیند. پیام‌هایِ تراکنشی/امنیتی هرگز از اینجا عبور نمی‌کنند.
* ارزیابی هنگامِ **ایجادِ** اعلان (dispatcher) و دوباره هنگامِ **ارسال** (notification_service) انجام می‌شود تا
  پس‌گرفتنِ رضایتِ بعد از صف‌شدن مانع ارسال شود.
"""

from __future__ import annotations

from django.utils import timezone

SMS, EMAIL = "sms", "email"
_FIELDS = {SMS: "accepts_promotional_sms", EMAIL: "accepts_promotional_email"}


def has_promotional_consent(customer, channel: str) -> bool:
    if customer is None or channel not in _FIELDS:
        return False
    return getattr(customer, _FIELDS[channel]) is True


def fresh_promotional_consent(customer_id, channel: str) -> bool:
    """مقدارِ فعلیِ پایگاه‌داده (نه شیِ کهنه‌ی حافظه) — برایِ بازبینیِ لحظه‌ی ارسال."""
    from apps.customers.models import Customer

    if not customer_id or channel not in _FIELDS:
        return False
    return Customer.objects.filter(pk=customer_id, **{_FIELDS[channel]: True}).exists()


def set_promotional_consent(customer, *, source: str, sms: bool | None = None, email: bool | None = None,
                            store=None, actor=None) -> bool:
    """رضایت را (مستقل برایِ هر کانال) تغییر می‌دهد؛ ``None`` یعنی «دست نزن». → آیا چیزی تغییر کرد."""
    now = timezone.now()
    changed, before, after = [], {}, {}
    for channel, value in ((SMS, sms), (EMAIL, email)):
        if value is None:
            continue
        flag = _FIELDS[channel]
        if getattr(customer, flag) is bool(value):
            continue
        before[channel], after[channel] = getattr(customer, flag), bool(value)
        setattr(customer, flag, bool(value))
        setattr(customer, f"promo_{channel}_consent_source", source)
        setattr(customer, f"promo_{channel}_consent_changed_at", now)
        changed += [flag, f"promo_{channel}_consent_source", f"promo_{channel}_consent_changed_at"]
    if not changed:
        return False
    customer.save(update_fields=changed + ["updated_at"])
    if store is not None:
        from apps.core.services.audit_service import record_audit_event

        record_audit_event(
            store=store, actor=actor if getattr(actor, "pk", None) else None, action_code="customer.consent_changed",
            object_type="Customer", object_id=customer.pk, object_label=f"customer-{customer.pk}",
            before=before, after=after, metadata={"source": source},
        )
    return True


def grant_at_opt_in(customer, *, source: str, sms: bool = False, email: bool = False, store=None) -> bool:
    """ثبت‌نام/تسویه‌حساب: فقط **اعطا** (تیکِ صریح). نزدنِ تیک هرگز رضایتِ قبلی را پس نمی‌گیرد
    (پس‌گرفتن فقط از تنظیماتِ حساب)."""
    return set_promotional_consent(
        customer, source=source, sms=True if sms else None, email=True if email else None, store=store,
    )
