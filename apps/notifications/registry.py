"""رجیستریِ نوعِ رویدادهایِ اعلانِ مدیران (Event Catalog) — تنها منبعِ حقیقتِ «چه رویدادی، برای چه کسی، با چه اهمیتی، از کجا».

* فقط رویدادهایی که **منبعِ واقعی** در کد دارند اینجا ``EventType`` هستند (``source`` مسیرِ دقیقِ Trigger را می‌گوید).
* رویدادهایِ «بدونِ منبع» در ``PLANNED`` مستند شده‌اند و **هرگز** اعلانِ ساختگی تولید نمی‌کنند.
* گیرندگان از روی ``permission`` (کلیدِ ``apps.stores.authorization``) تعیین می‌شوند؛ ``scope="platform"`` فقط برای staff+superuser."""

from __future__ import annotations

from dataclasses import dataclass

from apps.stores import authorization as A

INFO, NORMAL, IMPORTANT, CRITICAL = 1, 2, 3, 4

# دسته‌ها (کلیدِ پایدار → برچسب). «امنیت» هرگز قابلِ خاموش‌کردن در صندوق نیست.
CATEGORIES = {
    "orders": "سفارش‌ها",
    "finance": "پرداخت و امور مالی",
    "catalog": "کالا و موجودی",
    "customers": "مشتریان و پیام‌ها",
    "security": "امنیت",
    "account": "اشتراک و حساب",
    "infra": "دامنه و زیرساخت",
    "integrations": "یکپارچه‌سازی‌ها",
    "system": "رویدادهای سیستمی",
}
CATEGORY_HINTS = {
    "orders": "سفارش جدید، لغو، مرجوعی",
    "finance": "پرداخت مشکوک، بازپرداخت، کارت‌به‌کارت",
    "catalog": "موجودی کم، خطای ورود گروهی",
    "customers": "نظرهای جدید و درخواست‌ها",
    "security": "تغییر نقش و دسترسی — همیشه در صندوق ثبت می‌شود",
    "account": "وضعیت اشتراک و صورتحساب",
    "infra": "دامنه، DNS و عملیات زمان‌بندی‌شده",
    "integrations": "سرویس‌های بیرونی و همگام‌سازی",
    "system": "اعلان‌های آزمایشی و پیام‌های سامانه",
}
ALWAYS_INBOX_CATEGORIES = frozenset({"security"})

STORE, PLATFORM = "store", "platform"


@dataclass(frozen=True)
class EventType:
    key: str
    label: str
    category: str
    severity: int
    scope: str = STORE
    permission: str = ""            # مجوزِ لازم برای دریافت (خالی: هر عضوِ فعالِ فروشگاه / هر ادمینِ پلتفرم)
    link_name: str = ""             # نامِ URL در namespace ``dashboard`` (store) یا ``portal_platform_admin`` (platform)
    link_permission: str = ""       # مجوزِ صفحه‌ی مقصد (اگر با ``permission`` فرق دارد)
    urgent: bool = False            # فوری: صرف‌نظر از حداقلِ اهمیتِ کاربر Toast می‌شود (سفارش جدید…)
    groupable: bool = False         # رخدادِ تکراری در یک بازه به‌جای ردیفِ جدید شمارنده را زیاد می‌کند
    retention_days: int = 90
    source: str = ""                # Trigger واقعی در کد (برایِ ممیزی/گزارش)
    wired: bool = True
    #: چرخه‌ی تولیدکننده: production (مسیرِ تولیدیِ فعال) | feature_flagged (فقط وقتی پرچمِ پلتفرم روشن شود) | cron_dependent (نیازمندِ Cron نصب‌شده)
    #: | dormant (تولیدکننده هست اما هیچ فراخوانِ تولیدی ندارد) | test_only (دکمه‌ی اعلانِ آزمایشی). زنجیره‌ی تولید در ``producers.py`` با AST راستی‌آزمایی می‌شود.
    lifecycle: str = "production"


def _t(*types: EventType) -> dict:
    return {t.key: t for t in types}


EVENT_TYPES: dict[str, EventType] = _t(
    # ---------------------------------------------------------------- سفارش‌ها
    EventType("order.created", "سفارش جدید", "orders", NORMAL, permission=A.ORDER_VIEW, link_name="order-detail", urgent=True, retention_days=60,
              source="orders.order_service.place_order → business_events.order_created"),
    EventType("order.canceled", "لغو سفارش", "orders", IMPORTANT, permission=A.ORDER_VIEW, link_name="order-detail",
              source="orders.order_service.change_status(canceled) → business_events.order_status_changed"),
    EventType("return.requested", "درخواست مرجوعی", "orders", IMPORTANT, permission=A.RETURN_VIEW, link_name="return-detail",
              source="orders.return_service.create_return_request → business_events.return_event(requested)"),
    # ---------------------------------------------------------------- پرداخت و مالی
    EventType("payment.failed", "تلاش پرداخت ناموفق", "finance", NORMAL, permission=A.ORDER_VIEW, link_name="order-detail", groupable=True, retention_days=30,
              source="orders.gateway_payment_service.process_callback_and_verify (تأییدِ server-to-server ناموفق؛ on_commit، dedupe روی PaymentAttempt) + simulate_payment (فقط توسعه)"),
    EventType("payment.suspicious", "پرداخت مشکوک / مغایرت", "finance", CRITICAL, permission=A.REFUND_MANAGE, link_name="payment-reconciliations",
              source="orders.gateway_payment_service → business_events.late_payment"),
    EventType("refund.completed", "بازپرداخت انجام شد", "finance", NORMAL, permission=A.REFUND_VIEW, link_name="order-detail",
              source="orders.refund_service → business_events.refund_completed"),
    EventType("payment.card_transfer_submitted", "رسید کارت‌به‌کارت منتظر بررسی", "finance", IMPORTANT, permission=A.ORDER_REVIEW_CARD_TRANSFER,
              link_name="card-transfer-list", urgent=True, source="orders.card_transfer_service.submit"),
    # ---------------------------------------------------------------- کالا و موجودی
    EventType("import.failed", "خطا در ورود گروهی", "catalog", IMPORTANT, permission=A.IMPORT_EXPORT_VIEW, link_name="import-detail",
              source="dashboard.import_service (وضعیت FAILED / COMPLETED_WITH_ERRORS)"),
    EventType("stock.out", "اتمام موجودی", "catalog", IMPORTANT, permission=A.INVENTORY_MANAGE, link_name="inventory-list", groupable=True,
              source="catalog.inventory_service.decrement_stock_for_order_item (رسیدن به صفر)"),
    EventType("stock.low", "موجودی کم", "catalog", IMPORTANT, permission=A.INVENTORY_MANAGE, link_name="inventory-list", groupable=True,
              source="catalog.inventory_service.decrement_stock_for_order_item (عبور از آستانه‌ی low_stock_threshold)"),
    # ---------------------------------------------------------------- مشتریان
    EventType("review.pending", "نظر جدید نیازمند بررسی", "customers", NORMAL, permission=A.CONTENT_MANAGE, link_name="dashboard", groupable=True,
              source="catalog.views.product_review_submit → business_events.review_created"),
    # ---------------------------------------------------------------- امنیت
    EventType("staff.role_changed", "تغییر نقش یا سطح دسترسی", "security", IMPORTANT, permission=A.STAFF_MANAGE, link_name="staff-list",
              source="stores.membership_service.change_role"),
    EventType("staff.access_revoked", "لغو دسترسی یک عضو", "security", IMPORTANT, permission=A.STAFF_MANAGE, link_name="staff-list",
              source="stores.membership_service.revoke_membership"),
    # ---------------------------------------------------------------- اشتراک و حساب
    EventType("subscription.grace_period", "مهلت ارفاقی اشتراک شروع شد", "account", IMPORTANT, permission=A.SUBSCRIPTION_VIEW, link_name="subscription-overview",
              source="subscriptions.subscription_service.enter_grace_period ← billing.dunning_service + evaluate_subscription_states (مسیرِ واقعی)"),
    EventType("subscription.past_due", "اشتراک معوق شد", "account", CRITICAL, permission=A.SUBSCRIPTION_VIEW, link_name="subscription-overview", lifecycle="dormant", wired=False,
              source="subscriptions.subscription_service.mark_past_due (حالتِ PAST_DUE؛ هیچ فراخوانِ تولیدیِ فعلی ندارد — dunning از GRACE_PERIOD عبور می‌کند)"),
    EventType("subscription.suspended", "اشتراک تعلیق شد", "account", CRITICAL, permission=A.SUBSCRIPTION_VIEW, link_name="subscription-overview",
              source="subscriptions.subscription_service.suspend_subscription"),
    # ---------------------------------------------------------------- دامنه و زیرساخت
    EventType("domain.verified", "دامنه تأیید شد", "infra", NORMAL, permission=A.DOMAIN_MANAGE, link_name="settings",
              source="stores.domain_verification_service.check_dns_verification (موفق)"),
    EventType("domain.verification_failed", "تأیید دامنه ناموفق بود", "infra", IMPORTANT, permission=A.DOMAIN_MANAGE, link_name="settings", groupable=True,
              source="stores.domain_verification_service.check_dns_verification (ناموفق)"),
    # ---------------------------------------------------------------- یکپارچه‌سازی‌ها
    EventType("integration.sync_failed", "خطا در عملیات خودکار SEO/IndexNow", "integrations", IMPORTANT, permission=A.SETTINGS_MANAGE, link_name="settings",
              groupable=True, lifecycle="feature_flagged", source="core.automation.run (نتیجه‌ی FAILED با کدِ خطا)"),
    # ---------------------------------------------------------------- سیستمی
    EventType("system.test", "اعلان آزمایشی", "system", NORMAL, link_name="inbox-home", urgent=True, retention_days=7, lifecycle="test_only",
              source="inbox_views.send_test (فقط به خودِ درخواست‌دهنده)"),
    # ================================================================ پلتفرم
    EventType("platform.store_created", "فروشگاه جدید ساخته شد", "account", NORMAL, scope=PLATFORM, link_name="stores",
              source="portal.provisioning_service (ساخت Store)"),
    EventType("platform.store_status_changed", "تغییر وضعیت فروشگاه", "account", IMPORTANT, scope=PLATFORM, link_name="stores",
              source="stores.store_status_service.suspend_store/activate_store"),
    EventType("platform.contact_message", "پیام جدید از فرم تماس", "customers", NORMAL, scope=PLATFORM, link_name="home", groupable=True,
              source="portal.views.contact (ContactMessage)"),
    EventType("platform.jobs_unhealthy", "هشدار عملیاتی: کارهای زمان‌بندی‌شده", "infra", CRITICAL, scope=PLATFORM, link_name="home", lifecycle="cron_dependent",
              source="core.management.commands.check_background_jobs (سطح CRITICAL)"),
    EventType("platform.test", "اعلان آزمایشی پلتفرم", "system", NORMAL, scope=PLATFORM, link_name="inbox-home", urgent=True, retention_days=7, lifecycle="test_only",
              source="inbox_views.send_test"),
)

#: رویدادهایی که منبعِ واقعی ندارند (قابلیتِ متناظر ساخته نشده) — فقط مستندسازی؛ هیچ اعلانی ساخته نمی‌شود.
PLANNED = {
    "payment.gateway_error": "خطای درگاه — لاگ/وضعیتِ ساختاریافته‌ای که برای مدیر قابل‌اطلاع باشد وجود ندارد (فقط ``PaymentTransaction`` با پیامِ خام).",
    "payment.refund_failed": "شکستِ بازپرداخت — ``refund_service`` وضعیتِ نهایی FAILED را به‌عنوان رویداد جدا نمی‌دهد.",
    "settlement.status": "وضعیتِ تسویه — دادهٔ معتبرِ تسویه از درگاه دریافت نمی‌شود.",
    "security.suspicious_login": "تلاشِ ورودِ مشکوکِ مدیر — شمارنده‌ی rate-limit هست اما رویدادِ ساختاریافته برای مدیر نیست.",
    "security.password_changed_admin": "تغییرِ رمزِ مدیر — مسیرِ مستقلِ تغییرِ رمزِ ادمین ثبت‌شده‌ی رویداد نیست (فقط مشتری: ``account.sensitive_changed`` در Outbox).",
    "customers.support_ticket": "تیکت پشتیبانی — ماژولِ تیکت وجود ندارد.",
    "customers.message": "پیامِ مشتری — صندوقِ پیامِ مشتری وجود ندارد.",
    "store.template_published": "انتشار قالب — Trigger واقعی در Studio هنوز رویدادِ دامنه‌ای نمی‌دهد (``StorefrontLayoutVersion`` بدون hook).",
    "store.template_publish_failed": "شکستِ انتشار — همان محدودیت.",
    "vision_studio.error": "خطای Vision Studio — این قابلیت در این کدبیس منبعِ خطای ساختاریافته ندارد.",
    "infra.backup": "پشتیبان‌گیری — زیرساخت Backup در Repository نیست.",
    "integration.token_expired": "انقضای دسترسی سرویس — هیچ Integrationی OAuth/Token منقضی‌شونده ندارد (فقط ID).",
    "integration.torob_readiness": "آمادگی کالا برای ترب — فقط محاسبهٔ نمایشی در صفحه است؛ رویدادِ زمان‌بندی‌شده ندارد.",
    "platform.subscription_event": "رخدادهای اشتراکِ مؤثر بر پلتفرم — ``process_subscription_dunning`` خروجیِ رویداد نمی‌دهد (فقط شمارنده).",
}


def get_type(key: str) -> EventType:
    try:
        return EVENT_TYPES[key]
    except KeyError as exc:
        raise KeyError(f"unknown notification event type: {key!r}") from exc


def category_label(key: str) -> str:
    return CATEGORIES.get(key, key)


def store_categories() -> list[str]:
    return list(CATEGORIES)
