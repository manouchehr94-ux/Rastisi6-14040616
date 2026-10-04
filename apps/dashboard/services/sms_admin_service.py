"""سرویس پنل مدیریت برای بخش پیامک تنظیمات — ویرایش قالب‌ها، اتصال، و گزارش.

هیچ منطق ارسال/اعتبارسنجی‌ای اینجا تکرار نمی‌شود؛ همه چیز از apps.sms.services
فراخوانی می‌شود (طبق اصل «منطق در لایه‌ی سرویس»، نه در ویو یا اینجا دوباره).
"""

from apps.sms.events import EVENT_VARIABLES, STORE_HIDDEN_EVENTS, SmsEvent
from apps.sms.models import SmsLog, SmsOutboxItem, SmsTemplate

LOG_STATUS_FILTERS = [("", "همه وضعیت‌ها")] + list(SmsLog.Status.choices)

LOG_STATUS_BADGE = {
    SmsLog.Status.SENT: "b-green",
    SmsLog.Status.PENDING: "b-amber",
    SmsLog.Status.FAILED: "b-red",
    # ``SmsOutboxItem`` (صفِ SmsRasti) مقدارهایِ pending/sent/failed را با
    # SmsLog به‌اشتراک می‌گذارد؛ sending فقط مالِ اوست — همین دیکشنری برای
    # هر دو template filter استفاده می‌شود (sms_status_badge).
    SmsOutboxItem.Status.SENDING: "b-amber",
}


def templates_with_variables():
    """قالب‌ها را به‌ترتیب رویدادها برمی‌گرداند؛ هرکدام همراه با فهرست متغیرهای مجازش."""
    SmsTemplate.ensure_defaults()
    templates = {t.event_key: t for t in SmsTemplate.objects.all()}
    rows = []
    for event_key in SmsEvent.values:
        if event_key in STORE_HIDDEN_EVENTS:
            continue
        template = templates.get(event_key)
        if template is None:
            continue
        rows.append({"template": template, "variables": EVENT_VARIABLES.get(event_key, {})})
    return rows


def filtered_logs(*, status: str = "", store):
    """``store`` الزامی است — ردیف‌های ``store=NULL`` (پیش از افزودنِ این
    فیلد) عمداً هرگز به هیچ داشبوردی نشان داده نمی‌شوند، نه فقط به بقیه‌ی
    Storeها (ایزوله‌سازیِ چندمستأجری، نه فقط استثناکردنِ Storeِ اشتباه)."""
    qs = SmsLog.objects.filter(store=store).order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs


def filtered_outbox_items(*, status: str = "", store):
    qs = SmsOutboxItem.objects.filter(store=store).order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs
