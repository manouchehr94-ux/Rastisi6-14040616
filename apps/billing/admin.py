"""Django Admin پلتفرمیِ صورتحساب (ADR-73) — فقط superuser. فیلدهایِ مالیِ
نهایی‌شده read-only می‌مانند؛ payloadِ Webhook از قبل ردکت‌شده نمایش داده
می‌شود؛ هیچ کلیدِ رازی نشان داده نمی‌شود. اقدام‌هایِ دستی (mark-paid، Retryِ
Webhook) امن و idempotent‌اند و Audit ثبت می‌کنند.

هیچ‌کدام در Merchant Admin دیده نمی‌شوند — فقط در ``/admin/`` پشتِ superuser."""

from django.contrib import admin, messages

from apps.billing.models import (
    BillingSequence,
    BillingWebhookEvent,
    ScheduledPlanChange,
    StoreBillingAccount,
    SubscriptionCreditNote,
    SubscriptionDunningState,
    SubscriptionInvoice,
    SubscriptionInvoiceLine,
    SubscriptionPaymentAttempt,
    SubscriptionRefund,
)


class SuperuserOnlyBillingAdmin(admin.ModelAdmin):
    """پایه‌ی همه‌ی ثبت‌هایِ صورتحساب — فقط superuser، بدونِ افزودن/حذف از UI
    (رکوردهایِ مالی از مسیرِ سرویس ساخته می‌شوند)."""

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StoreBillingAccount)
class StoreBillingAccountAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("store", "legal_name", "billing_email", "currency", "updated_at")
    search_fields = ("store__slug", "legal_name", "billing_email", "tax_identifier")
    readonly_fields = ("store", "currency", "created_at", "updated_at")


class SubscriptionInvoiceLineInline(admin.TabularInline):
    model = SubscriptionInvoiceLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "line_type", "description", "quantity", "unit_amount", "subtotal",
        "discount", "tax", "total", "service_period_start", "service_period_end",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("number", "store", "kind", "status", "grand_total", "amount_paid", "currency", "due_at")
    list_filter = ("status", "kind", "currency")
    search_fields = ("number", "store__slug", "idempotency_key")
    date_hierarchy = "created_at"
    inlines = [SubscriptionInvoiceLineInline]
    # F-07: the bulk «mark paid» action was removed. Marking an invoice paid moves money-equivalent state, so it must carry an
    # amount, a bank/receipt reference and a reason: use Platform Admin > Payments > manual payment (audited, one invoice at a time).
    # فیلدهایِ مالی همیشه read-only در Admin — تغییرِ مالی فقط از سرویس.
    readonly_fields = (
        "store", "subscription", "plan_version", "number", "kind", "status", "currency",
        "plan_code_snapshot", "plan_version_snapshot", "billing_account_snapshot",
        "billing_period_start", "billing_period_end", "issued_at", "due_at", "paid_at",
        "voided_at", "subtotal", "discount_total", "tax_total", "grand_total",
        "amount_paid", "amount_due", "provider_reference", "idempotency_key",
        "created_at", "updated_at",
    )


@admin.register(SubscriptionPaymentAttempt)
class SubscriptionPaymentAttemptAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("public_token", "store", "invoice", "provider", "status", "amount", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("public_token", "provider_payment_id", "idempotency_key", "store__slug")

    def has_change_permission(self, request, obj=None):
        return False  # تلاش‌ها تغییرناپذیرند


@admin.register(BillingWebhookEvent)
class BillingWebhookEventAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("provider", "external_event_id", "event_type", "processing_status", "signature_valid", "created_at")
    list_filter = ("processing_status", "provider", "signature_valid")
    search_fields = ("external_event_id", "provider")
    actions = ["action_retry"]
    # payload از قبل ردکت‌شده است؛ همه‌چیز read-only.
    readonly_fields = (
        "provider", "external_event_id", "event_type", "signature_valid", "processing_status",
        "payload_hash", "sanitized_payload", "received_at", "processed_at", "error_summary",
        "retry_count", "related_payment_attempt", "related_invoice", "created_at", "updated_at",
    )

    @admin.action(description="پردازشِ دوباره‌ی رخداد (idempotent)")
    def action_retry(self, request, queryset):
        from apps.billing.services import payment_flow_service

        processed = 0
        for event in queryset:
            event.processing_status = BillingWebhookEvent.ProcessingStatus.RECEIVED
            event.save(update_fields=["processing_status"])
            payment_flow_service.process_webhook_event(event, actor=request.user)
            processed += 1
        self.message_user(request, f"{processed} رخداد دوباره پردازش شد.", level=messages.SUCCESS)


@admin.register(SubscriptionCreditNote)
class SubscriptionCreditNoteAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("number", "store", "invoice", "status", "amount", "currency", "issued_at")
    list_filter = ("status", "currency")
    search_fields = ("number", "store__slug", "invoice__number")
    readonly_fields = (
        "store", "invoice", "number", "currency", "amount", "issued_at", "voided_at",
        "actor", "created_at", "updated_at",
    )


@admin.register(SubscriptionRefund)
class SubscriptionRefundAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("invoice", "store", "status", "amount", "currency", "provider", "created_at")
    list_filter = ("status", "provider", "currency")
    search_fields = ("invoice__number", "store__slug", "provider_refund_id", "idempotency_key")
    # Read-only on purpose: a refund changes state ONLY through refund_service (approve / reject / complete with a bank reference),
    # which also syncs the invoice, the coupon and the subscription entitlement exactly once. Editing status here would bypass that.
    readonly_fields = (
        "store", "invoice", "payment_attempt", "credit_note", "provider", "provider_refund_id",
        "status", "amount", "currency", "reason", "failure_code", "failure_message",
        "requested_by", "requested_at", "completed_at", "idempotency_key", "created_at", "updated_at",
    )

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionDunningState)
class SubscriptionDunningStateAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("invoice", "store", "status", "stage", "attempt_count", "next_retry_at")
    list_filter = ("status",)
    search_fields = ("invoice__number", "store__slug")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ScheduledPlanChange)
class ScheduledPlanChangeAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("subscription", "store", "target_plan_version", "created_at")
    search_fields = ("store__slug",)

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BillingSequence)
class BillingSequenceAdmin(SuperuserOnlyBillingAdmin):
    list_display = ("key", "last_value", "updated_at")

    def has_change_permission(self, request, obj=None):
        return False
