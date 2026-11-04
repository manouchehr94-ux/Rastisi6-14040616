"""زنجیره‌ی تولیدِ هر نوعِ رویدادِ اعلان — از «نقطه‌ی ورودِ سرویس» تا ``safe_publish`` با همان کلید.

این جدول داده است، نه منطق: ``tests/test_producer_wiring.py`` هر حلقه را با تحلیلِ AST (نه جست‌وجوی رشته) راستی‌آزمایی می‌کند:
تابعِ ``function`` در ``module`` باید واقعاً ``callee`` را صدا بزند و حلقه‌ی آخر باید ``safe_publish``/``publish`` را با **همان کلیدِ رویداد** (ثابتِ رشته‌ای در همان تابع) صدا بزند.
دسته‌بندیِ «ثبت‌شده / تولیدکننده‌ی قابل‌فراخوانی / مسیرِ تولیدیِ قابل‌رسیدن / پرچم‌دار یا خفته / برنامه‌ریزی‌شده / فقط آزمایشی» = ``EventType.lifecycle`` + ``registry.PLANNED``."""

AE = "apps.notifications.services.admin_events"
BE = "apps.notifications.services.business_events"
OS = "apps.orders.services.order_service"
GW = "apps.orders.services.gateway_payment_service"
MS = "apps.stores.services.membership_service"
SS = "apps.subscriptions.services.subscription_service"
SP = "safe_publish"

#: کلید → فهرستِ حلقه‌ها ``(module, function, callee)``؛ حلقه‌ی اول نقطه‌ی ورودِ سرویسِ تولیدی است.
CHAINS = {
    "order.created": [(OS, "create_order_from_cart", "order_created"), (BE, "order_created", "order_created"), (AE, "order_created", SP)],
    "order.canceled": [(OS, "change_order_status", "order_status_changed"), (BE, "order_status_changed", "order_canceled"), (AE, "order_canceled", SP)],
    "payment.failed": [(GW, "process_callback_and_verify", "payment_attempt_failed"), (AE, "payment_attempt_failed", SP)],
    "return.requested": [("apps.orders.services.return_service", "create_return_request", "return_event"), (BE, "return_event", "return_requested"), (AE, "return_requested", SP)],
    "payment.suspicious": [(GW, "_open_reconciliation", "late_payment"), (BE, "late_payment", "suspicious_payment"), (AE, "suspicious_payment", SP)],
    "refund.completed": [("apps.orders.services.refund_service", "execute_order_refund", "refund_completed"), (BE, "refund_completed", "refund_completed"), (AE, "refund_completed", SP)],
    "payment.card_transfer_submitted": [("apps.orders.services.card_transfer_service", "submit", "card_transfer_submitted"), (AE, "card_transfer_submitted", SP)],
    "import.failed": [("apps.dashboard.services.import_service", "_finalize_rollback", "import_failed"), (AE, "import_failed", SP)],
    "stock.low": [("apps.catalog.services.inventory_service", "decrement_stock_for_order_item", "_announce_stock_crossing"),
                  ("apps.catalog.services.inventory_service", "_announce_stock_crossing", "stock_crossed"), (AE, "stock_crossed", SP)],
    "stock.out": [("apps.catalog.services.inventory_service", "decrement_stock_for_order_item", "_announce_stock_crossing"),
                  ("apps.catalog.services.inventory_service", "_announce_stock_crossing", "stock_crossed"), (AE, "stock_crossed", SP)],
    "review.pending": [("apps.catalog.views", "product_review_create", "review_created"), (BE, "review_created", "review_pending"), (AE, "review_pending", SP)],
    "staff.role_changed": [(MS, "change_role", "role_changed"), (AE, "role_changed", SP)],
    "staff.access_revoked": [(MS, "revoke_membership", "access_revoked"), (AE, "access_revoked", SP)],
    "subscription.grace_period": [(SS, "enter_grace_period", "subscription_state"), (AE, "subscription_state", SP)],
    "subscription.past_due": [(SS, "mark_past_due", "subscription_state"), (AE, "subscription_state", SP)],
    "subscription.suspended": [(SS, "suspend_subscription", "subscription_state"), (AE, "subscription_state", SP)],
    "domain.verified": [("apps.stores.services.domain_verification_service", "check_dns_verification", "domain_verification"), (AE, "domain_verification", SP)],
    "domain.verification_failed": [("apps.stores.services.domain_verification_service", "check_dns_verification", "domain_verification"), (AE, "domain_verification", SP)],
    "integration.sync_failed": [("apps.core.automation", "run", "automation_failed"), (AE, "automation_failed", SP)],
    "platform.store_created": [("apps.portal.services.provisioning_service", "_create_store_with_unique_platform_code", "platform_store_created"), (AE, "platform_store_created", SP)],
    "platform.store_status_changed": [("apps.stores.services.store_status_service", "suspend_store", "platform_store_status"), (AE, "platform_store_status", SP)],
    "platform.contact_message": [("apps.portal.views", "contact", "platform_contact_message"), (AE, "platform_contact_message", SP)],
    "platform.jobs_unhealthy": [("apps.core.management.commands.check_background_jobs", "handle", "platform_jobs_unhealthy"), (AE, "platform_jobs_unhealthy", SP)],
    "system.test": [("apps.notifications.inbox_views", "build", "publish")],
    "platform.test": [("apps.notifications.inbox_views", "build", "publish")],
}

#: برای رویدادهای تولیدی: نقطه‌ی ورودِ سرویس باید خودش از کدِ غیرتستی فراخوانی شود. ``(module, function, callee)`` — حداقل یکی باید برقرار باشد.
ENTRIES = {
    "payment.failed": [("apps.orders.views", "gateway_callback", "process_callback_and_verify")],
    "subscription.grace_period": [("apps.billing.services.dunning_service", "_process_invoice", "enter_grace_period"), (SS, "_apply_due_action", "enter_grace_period")],
    "subscription.suspended": [(SS, "_apply_due_action", "suspend_subscription"), ("apps.billing.services.dunning_service", "_process_invoice", "suspend_subscription")],
}
