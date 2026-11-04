"""SMS ↔ email parity inventory, COMPUTED from the code registries (never hand-maintained).

Sources of truth:
* ``apps.sms.events.SmsEvent``            — every SMS the platform can send through ``apps.sms``;
* ``apps.notifications.events.EVENTS``    — every notification event (SMS and/or email) with its recipient,
                                           category, variables and default templates;
* ``TRIGGERS`` below                      — the real call site of each event; ``test_sms_email_parity`` opens each
                                           file and asserts the call text exists, so a removed/renamed trigger
                                           fails the build instead of silently leaving the matrix stale.
"""

from __future__ import annotations

from apps.notifications import events as ev
from apps.sms.events import STORE_HIDDEN_EVENTS, SmsEvent

#: phone-possession proofs: NEVER emailed (an emailed code proves access to a mailbox, not to the phone)
OTP_EVENTS = {SmsEvent.OTP, SmsEvent.PLATFORM_OWNER_OTP}
#: plumbing-only SMS "events": ``notification`` is the generic carrier the outbox uses to send any rendered SMS
#: (its email counterpart IS the outbox email row), ``platform_test`` is the platform's provider self-test.
INFRA_SMS_EVENTS = {SmsEvent.NOTIFICATION, SmsEvent.PLATFORM_TEST}

OTP_REASON = (
    "OTP اثباتِ مالکیتِ شماره است؛ ایمیل‌کردنِ آن فقط دسترسی به صندوقِ ایمیل را ثابت می‌کند، نه شماره را. "
    "معنایِ تأییدِ شماره دست‌نخورده می‌ماند. تأییدِ ایمیل (در صورت نیاز) باید جریانِ جداگانه‌ی «تأییدِ ایمیل» با توکنِ "
    "مخصوصِ ایمیل باشد؛ در کدِ فعلی هیچ جریانِ ثبت/ورودی ایمیل‌محور وجود ندارد که نیازمندِ آن باشد."
)

# event_key -> (file, literal text that must appear in that file, trigger description)
TRIGGERS = {
    "account.registered": ("apps/customers/services/auth_service.py", "business_events.account_registered(", "ثبت‌نام مشتری (دو مسیر)"),
    "account.sensitive_changed": ("apps/customers/views.py", "business_events.account_sensitive_changed(", "تغییر ایمیلِ حساب"),
    "order.created": ("apps/orders/services/order_service.py", "business_events.order_created(", "ثبت سفارش"),
    "staff.order_created": ("apps/notifications/services/business_events.py", '"staff.order_created"', "ثبت سفارش (کارکنان)"),
    "order.processing": ("apps/notifications/services/business_events.py", '"processing": "order.processing"', "تغییر وضعیت سفارش"),
    "order.shipped": ("apps/notifications/services/business_events.py", '"shipped": "order.shipped"', "تغییر وضعیت سفارش"),
    "order.delivered": ("apps/notifications/services/business_events.py", '"delivered": "order.delivered"', "تغییر وضعیت سفارش"),
    "order.canceled": ("apps/notifications/services/business_events.py", '"canceled": "order.canceled"', "تغییر وضعیت سفارش"),
    "payment.succeeded": ("apps/orders/services/lifecycle.py", "business_events.payment_result(order, success=True)", "پرداخت موفق (رخداد مالی — فقط مصرف‌کننده)"),
    "payment.failed": ("apps/orders/services/payment_service.py", "business_events.payment_result(order, success=False)", "پرداخت ناموفق (رخداد مالی — فقط مصرف‌کننده)"),
    "refund.completed": ("apps/orders/services/refund_service.py", "business_events.refund_completed(", "تکمیل استرداد (رخداد مالی — فقط مصرف‌کننده)"),
    "staff.late_payment": ("apps/orders/services/gateway_payment_service.py", "business_events.late_payment(", "مغایرت پرداخت (رخداد مالی — فقط مصرف‌کننده)"),
    "coupon.redeemed": ("apps/orders/services/coupon_redemption_service.py", "business_events.coupon_redeemed(", "استفاده از کد"),
    "return.requested": ("apps/orders/services/return_service.py", 'business_events.return_event(return_request, "requested")', "ثبت مرجوعی"),
    "return.approved": ("apps/orders/services/return_service.py", 'business_events.return_event(return_request, "approved")', "تأیید مرجوعی"),
    "return.rejected": ("apps/orders/services/return_service.py", 'business_events.return_event(return_request, "rejected"', "رد مرجوعی"),
    "staff.return_requested": ("apps/notifications/services/business_events.py", '"staff.return_requested"', "ثبت مرجوعی (کارکنان)"),
    "staff.review_created": ("apps/catalog/views.py", "business_events.review_created(", "ثبت نظر"),
    "campaign.activated": ("apps/engagement/services/campaign_service.py", '"campaign.activated"', "فعال‌سازی کمپین"),
    "coupon.issued": ("apps/engagement/services/campaign_service.py", "dispatch_event(", "صدور کد (کمپین/مناسبت)"),
    "platform.email_sender_active": ("apps/notifications/mail/provisioning_service.py", '"platform.email_sender_active"', "تغییر وضعیتِ فرستنده"),
    "platform.email_sender_problem": ("apps/notifications/mail/provisioning_service.py", '"platform.email_sender_problem"', "تغییر وضعیتِ فرستنده"),
}
#: events dispatched by campaign/occasion runs through a computed key (``dispatch_event(`` in campaign_service)
CAMPAIGN_DRIVEN_PREFIXES = ("occasion.", "campaign.offer_", "campaign.announce", "coupon.expiring", "reward.")


def trigger_for(event_key: str):
    if event_key in TRIGGERS:
        return TRIGGERS[event_key]
    if event_key.startswith(CAMPAIGN_DRIVEN_PREFIXES):
        return ("apps/engagement/services/campaign_service.py", "dispatch_event(", "اجرای کمپین/مناسبت")
    return None


def build() -> list[dict]:
    rows: list[dict] = []
    wired_sms: set[str] = set()
    for d in ev.EVENTS.values():
        sms_source = d.legacy_sms_event or d.platform_sms_event
        if sms_source:
            wired_sms.add(str(sms_source))
        if d.legacy_sms_event:
            origin = "قدیمی (apps.sms / SmsTemplate)"
        elif d.platform_sms_event:
            origin = "پلتفرم‌محور (SmsTemplate سراسری)"
        elif d.default_sms:
            origin = "موتور اعلان (outbox)"
        else:
            origin = "—"
        trig = trigger_for(d.key)
        rows.append({
            "event_key": d.key, "label": d.label, "category": d.category, "audience": d.audience,
            "sms_event": str(sms_source) if sms_source else "", "sms_origin": origin,
            "has_sms": bool(sms_source or d.default_sms),
            "has_email": bool(d.default_email_subject and d.default_email_body),
            "sender": d.sender, "variables": sorted(d.variables),
            "sms_default_on": d.sms_enabled_default, "email_default_on": d.email_enabled_default,
            "required_variables": list(d.required_variables),
            "trigger_file": trig[0] if trig else "", "trigger_text": trig[1] if trig else "",
            "trigger_desc": trig[2] if trig else "",
            "security": d.category == ev.SECURITY,
        })
    for sms in SmsEvent:
        if str(sms.value) in wired_sms:
            continue
        if sms in OTP_EVENTS:
            note = OTP_REASON
        elif sms in INFRA_SMS_EVENTS:
            note = "زیرساختی؛ معادلِ ایمیلیِ آن همان ردیفِ ایمیلِ outbox است."
        else:
            note = "نامشخص"
        rows.append({
            "event_key": "", "label": sms.label, "category": "otp" if sms in OTP_EVENTS else "infra", "audience": "",
            "sms_event": str(sms.value), "sms_origin": "قدیمی (apps.sms)", "has_sms": True, "has_email": False,
            "sender": "", "variables": [], "sms_default_on": True, "email_default_on": False,
            "required_variables": [], "trigger_file": "", "trigger_text": "", "trigger_desc": "", "security": False,
            "note": note,
        })
    return rows


def to_markdown(rows: list[dict] | None = None) -> str:
    rows = rows if rows is not None else build()
    out = [
        "| رویداد (شناسه) | عنوان | دسته | مخاطب | پیامک (منبع) | ایمیل | فرستنده | محرک (فایل) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["event_key"]:
            out.append(
                f"| `{r['event_key']}` | {r['label']} | {r['category']} | {r['audience']} | "
                f"{r['sms_event'] or ('✔ ' + r['sms_origin'] if r['has_sms'] else '—')} ({r['sms_origin']}) | "
                f"{'✔' if r['has_email'] else '✘'} | {r['sender']} | `{r['trigger_file']}` |"
            )
        else:
            out.append(f"| — | {r['label']} (`{r['sms_event']}`) | {r['category']} | — | {r['sms_origin']} | ✘ (عمدی) | — | — |")
    return "\n".join(out)
