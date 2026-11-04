"""Platform Admin — notification event catalog, platform default templates (SMS+email), channel policy, sender
identities across all Stores, test sending and delivery/failure review. Host-isolated and staff+superuser-only,
same gate as the rest of ``portal.platform_admin_views`` (``_is_platform_staff``)."""

from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.services.audit_service import record_audit_event
from apps.notifications import events as notif_events
from apps.notifications.mail import provisioning_service
from apps.notifications.models import EmailSenderIdentity, NotificationOutbox, NotificationTemplateRevision
from apps.notifications.services import template_service
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.services.notification_service import deliver_single
from apps.stores.models import Store

from .models import PlatformAuditLogEntry
from .services.platform_config_service import record_platform_audit_event

# Granular platform permissions (declared on PlatformNotificationTemplate.Meta.permissions). Superusers (the RastiSi
# owner) hold all of them; a platform team member (is_staff) needs the specific permission. Authenticated but
# unauthorized -> 403 (never a silent redirect); anonymous -> platform login.
CATALOG, TEMPLATES, DELIVERY, SENDERS, TESTS = (
    "view_notification_catalog", "manage_platform_templates", "view_notification_delivery",
    "manage_email_senders", "send_notification_tests",
)
ALL_PERMS = (CATALOG, TEMPLATES, DELIVERY, SENDERS, TESTS)


def has_platform_perm(user, codename: str) -> bool:
    return bool(user.is_authenticated and user.is_active and user.is_staff
                and (user.is_superuser or user.has_perm(f"notifications.{codename}")))


def is_notification_team(user) -> bool:
    return any(has_platform_perm(user, c) for c in ALL_PERMS)


def platform_perm(codename: str):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("portal_platform_admin:login")
            if not has_platform_perm(request.user, codename):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


@platform_perm(CATALOG)
def notification_catalog(request):
    """Full event catalog: who it goes to, which category, whether the platform locked it, SMS/email defaults."""
    rows = []
    for key, event in notif_events.EVENTS.items():
        platform_sms = template_service.get_template(None, key, "sms") if event.legacy_sms_event or event.platform_sms_event else None
        rows.append({
            "event": event, "category": notif_events.CATEGORY_LABELS[event.category],
            "locked": template_service.is_store_locked(key, "email") or template_service.is_store_locked(key, "sms"),
            "audience": "کارکنان" if event.audience == notif_events.AUDIENCE_STAFF else "مشتری",
            "platform_sms": platform_sms,
        })
    return render(request, "portal/platform_admin/notification_catalog.html", {
        "rows": rows, "active_nav": "notification-catalog",
    })


def _event_or_404(key):
    if key not in notif_events.EVENTS:
        from django.http import Http404

        raise Http404
    return notif_events.EVENTS[key]


@platform_perm(TEMPLATES)
def notification_platform_template(request, event_key):
    event = _event_or_404(event_key)
    errors = {}
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "reset":
            channel = request.POST.get("channel")
            if channel in notif_events.CHANNELS:
                template_service.reset_platform_template(event_key, channel, actor=request.user)
                messages.info(request, "قالبِ پیش‌فرضِ پلتفرم حذف شد؛ پیش‌فرضِ داخلِ سیستم دوباره مؤثر است.")
            return redirect("portal_platform_admin:notification-platform-template", event_key=event_key)
        with transaction.atomic():  # all-or-nothing: a rejected channel must not leave the other one half-saved
            for channel in notif_events.CHANNELS:
                if channel == "sms" and (event.legacy_sms_event or event.platform_sms_event):
                    continue  # پیامکِ این رویداد از «قالب‌های پیامک» پلتفرم مدیریت می‌شود، نه اینجا
                try:
                    template_service.save_platform_template(
                        event_key, channel, enabled=request.POST.get(f"{channel}_enabled") == "on",
                        subject=request.POST.get("email_subject", "") if channel == "email" else "",
                        body=request.POST.get(f"{channel}_body", ""),
                        body_html=request.POST.get("email_html", "") if channel == "email" else "",
                        locked_for_stores=request.POST.get(f"{channel}_locked") == "on", actor=request.user,
                    )
                except template_service.TemplateError as exc:
                    errors[channel] = str(exc)
            if errors:
                transaction.set_rollback(True)
        if not errors:
            record_platform_audit_event(actor=request.user, action_code="notifications.platform_template_saved",
                                        object_type="PlatformNotificationTemplate", object_label=event_key)
            messages.success(request, "قالبِ پیش‌فرضِ پلتفرم ذخیره شد")
            return redirect("portal_platform_admin:notification-platform-template", event_key=event_key)
    templates = {ch: template_service.get_template(None, event_key, ch) for ch in notif_events.CHANNELS}
    return render(request, "portal/platform_admin/notification_platform_template.html", {
        "event": event, "templates": templates, "errors": errors, "active_nav": "notification-catalog",
        "variables": sorted(event.variables.items()), "required_variables": event.required_variables,
        "revisions": template_service.list_revisions(scope="platform", store=None, event_key=event_key, limit=20),
    })


@require_POST
@platform_perm(TEMPLATES)
def notification_platform_template_preview(request, event_key):
    _event_or_404(event_key)
    channel = request.POST.get("channel", "email")
    try:
        result = template_service.preview(
            None, event_key, channel, body=request.POST.get(f"{channel}_body"),
            subject=request.POST.get("email_subject") if channel == "email" else None,
            body_html=request.POST.get("email_html") if channel == "email" else None,
        )
    except template_service.TemplateError as exc:
        return render(request, "dashboard/partials/notification_preview.html", {"error": str(exc), "channel": channel})
    return render(request, "dashboard/partials/notification_preview.html", {"result": result, "channel": channel})


@require_POST
@platform_perm(TESTS)
def notification_platform_template_test(request, event_key):
    event = _event_or_404(event_key)
    channel = request.POST.get("channel", "email")
    recipient = request.POST.get("recipient", "").strip()
    if channel not in notif_events.CHANNELS or not recipient:
        messages.error(request, "کانال و گیرنده را مشخص کنید.")
        return redirect("portal_platform_admin:notification-platform-template", event_key=event_key)
    store_id = request.POST.get("store_id", "").strip()
    if not store_id.isdigit():
        messages.error(request, "برای ارسالِ آزمایشی شناسه‌ی فروشگاه لازم است؛ فرستنده همیشه از دامنه‌ی همان فروشگاه تعیین می‌شود.")
        return redirect("portal_platform_admin:notification-platform-template", event_key=event_key)
    store = get_object_or_404(Store, pk=int(store_id))
    rows = dispatch_event(
        event_key, store=store, context=dict(event.sample, store_name=store.name), channels=[channel], is_test=True,
        test_recipient=recipient,
    )
    if not rows:
        messages.error(request, "ارسالِ آزمایشی ساخته نشد.")
    else:
        row = deliver_single(rows[0])
        record_platform_audit_event(actor=request.user, action_code="notifications.platform_test_sent",
                                    object_type="NotificationOutbox", object_id=row.pk, object_label=event_key)
        if row.status == NotificationOutbox.Status.SENT:
            messages.success(request, "پیامِ آزمایشی ارسال شد.")
        elif row.status == NotificationOutbox.Status.PENDING and row.last_error == "sender_not_active":
            messages.error(request, "ارسال نشد: فرستنده‌ی ایمیلِ این فروشگاه فعال نیست (جایگزینِ مشترک وجود ندارد).")
        else:
            messages.error(request, f"ارسالِ آزمایشی ناموفق بود: {row.last_error or row.skip_reason or row.get_status_display()}")
    return redirect("portal_platform_admin:notification-platform-template", event_key=event_key)


@platform_perm(SENDERS)
def notification_senders(request):
    """Every Store's email-sender status across the platform — operational review, not editing."""
    qs = EmailSenderIdentity.objects.select_related("store").order_by("-updated_at")
    status = request.GET.get("status", "").strip()
    if status in EmailSenderIdentity.Status.values:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(store__name__icontains=q) | Q(domain_name__icontains=q))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "portal/platform_admin/notification_senders.html", {
        "page": page, "active_nav": "notification-senders", "statuses": EmailSenderIdentity.Status.choices,
        "filters": request.GET,
    })


@require_POST
@platform_perm(SENDERS)
def notification_sender_toggle(request, pk):
    identity = get_object_or_404(EmailSenderIdentity, pk=pk)
    identity.platform_disabled = not identity.platform_disabled
    identity.save(update_fields=["platform_disabled", "updated_at"])
    record_audit_event(
        store=identity.store, actor=request.user, action_code="notifications.sender_platform_toggle",
        object_type="EmailSenderIdentity", object_id=identity.pk, object_label=identity.domain_name,
        after={"platform_disabled": identity.platform_disabled},
    )
    if not identity.platform_disabled:
        provisioning_service.sync_sender_identity(identity.store, actor=request.user)
    messages.success(request, "وضعیت به‌روزرسانی شد.")
    return redirect("portal_platform_admin:notification-senders")


@platform_perm(DELIVERY)
def notification_delivery(request):
    """Platform-wide delivery/failure review and usage (last 7 days), plus the list of rows needing attention."""
    since = timezone.now() - timedelta(days=7)
    usage = (
        NotificationOutbox.objects.filter(created_at__gte=since)
        .values("channel", "status").annotate(n=Count("id")).order_by("channel", "status")
    )
    qs = NotificationOutbox.objects.select_related("store").order_by("-created_at")
    g = request.GET
    if g.get("channel") in notif_events.CHANNELS:
        qs = qs.filter(channel=g["channel"])
    if g.get("status") in NotificationOutbox.Status.values:
        qs = qs.filter(status=g["status"])
    if g.get("attention"):
        qs = qs.filter(Q(status__in=("failed", "dead")) | Q(held_since__isnull=False)
                       | Q(status="expired", is_promotional=False))
    if g.get("store", "").strip():
        qs = qs.filter(store__name__icontains=g["store"].strip())
    page = Paginator(qs, 40).get_page(g.get("page"))
    return render(request, "portal/platform_admin/notification_delivery.html", {
        "page": page, "usage": list(usage), "active_nav": "notification-delivery",
        "statuses": NotificationOutbox.Status.choices, "channels": notif_events.CHANNELS, "filters": g,
    })


@platform_perm(DELIVERY)
def notification_audit(request):
    """Who changed what: platform template revisions and notification-related platform audit entries."""
    revisions = NotificationTemplateRevision.objects.filter(scope="platform").select_related("actor")[:100]
    entries = PlatformAuditLogEntry.objects.filter(action_code__startswith="notifications.").select_related("actor")[:100]
    return render(request, "portal/platform_admin/notification_audit.html", {
        "revisions": revisions, "entries": entries, "active_nav": "notification-audit",
    })
