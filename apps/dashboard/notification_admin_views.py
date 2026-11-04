"""Store-admin pages for the notification channels: sender identity (diagnostics + retry) and per-event channel
switches. Same decorators and the same ``request.store`` as the rest of the merchant dashboard; every query is
filtered by that Store — a store user can never read or change another store's sender, templates or history."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.services.audit_service import record_audit_event
from apps.notifications import events as notif_events
from apps.notifications.mail import provisioning_service
from apps.notifications.services import template_service
from apps.stores.authorization import SETTINGS_MANAGE
from apps.stores.models import StoreDomain

from .decorators import permission_required, staff_required


@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_sender(request):
    store = request.store
    diag = provisioning_service.diagnostics(store)
    domains = StoreDomain.objects.filter(store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN)\
        .exclude(retired_at__isnull=False)
    return render(request, "dashboard/notification_sender.html", {
        "diag": diag, "domains": domains, "active_page": "notifications",
        "status_labels": {
            "active": "فعال", "inactive": "غیرفعال", "pending": "در انتظارِ تأیید", "error": "خطا",
        },
    })


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_sender_retry(request):
    """«بررسیِ دوباره»: یک بررسیِ واقعی با ارائه‌دهنده انجام می‌شود؛ فعال‌شدن فقط با تأییدِ خودِ ارائه‌دهنده است."""
    identity = provisioning_service.sync_sender_identity(request.store, actor=request.user)
    record_audit_event(store=request.store, actor=request.user, action_code="notifications.sender_retry",
                       object_type="EmailSenderIdentity", object_id=identity.pk, object_label=identity.domain_name)
    if identity.status == identity.Status.ACTIVE:
        messages.success(request, f"تأیید شد؛ ایمیل‌ها از {identity.from_address} ارسال می‌شوند.")
    else:
        messages.info(request, "بررسی انجام شد؛ هنوز تأییدی از سوی ارائه‌دهنده نیامده است. وضعیت را در همین صفحه ببینید.")
    return redirect("dashboard:notification-sender")


@staff_required
@permission_required(SETTINGS_MANAGE)
def notification_channels(request):
    store = request.store
    if request.method == "POST":
        errors = 0
        for key, event in notif_events.EVENTS.items():
            if event.sender == "platform":
                continue
            for channel in notif_events.CHANNELS:
                field = f"{key}__{channel}"
                if f"seen__{field}" not in request.POST:
                    continue  # this switch was not rendered as editable for this user
                wanted = request.POST.get(field) == "on"
                current = template_service.get_template(store, key, channel)
                if wanted == current["enabled"]:
                    continue
                try:
                    template_service.set_channel_enabled(store, key, channel, wanted, actor=request.user)
                except template_service.TemplateError:
                    errors += 1
        record_audit_event(store=store, actor=request.user, action_code="notifications.channels_saved",
                           object_type="NotificationTemplate", object_id=0, object_label="channels")
        if errors:
            messages.warning(request, "برخی کلیدها تغییر نکردند (سیاستِ پلتفرم یا قفلِ متن).")
        else:
            messages.success(request, "تنظیماتِ کانال‌ها ذخیره شد")
        return redirect("dashboard:notification-channels")
    rows = []
    for key, event in notif_events.EVENTS.items():
        if event.sender == "platform":
            continue
        cells = {}
        for channel in notif_events.CHANNELS:
            tpl = template_service.get_template(store, key, channel)
            editable = not (
                template_service._reads_from_sms_template(key, channel)
                or event.category == notif_events.SECURITY
                or tpl.get("locked")
            )
            cells[channel] = {"enabled": tpl["enabled"], "editable": editable, "source": tpl.get("source", "")}
        rows.append({"event": event, "category": notif_events.CATEGORY_LABELS[event.category], "cells": cells})
    return render(request, "dashboard/notification_channels.html", {
        "rows": rows, "active_page": "notifications", "diag": provisioning_service.diagnostics(store),
    })
