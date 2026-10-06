"""HTTP surfaces of the RastiChat adapter. Every view 404s unless the integration is globally on AND (for storefront
and merchant views) enabled for the resolved store — so deploying this code exposes nothing.

Tenant selection is ALWAYS server-side: the storefront Host resolves the store (``request.store``), the merchant admin
Host resolves it for staff (``staff_required``), and the platform page carries the store's public id in the URL of a
superuser-only view. No view reads a store/tenant/user/role from a query or form value to decide authorization.
"""
import uuid
from urllib.parse import quote

from django.contrib.auth.decorators import user_passes_test
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings
from django.contrib import messages

from apps.core.services.audit_service import record_audit_event
from apps.dashboard.decorators import staff_required
from apps.stores.models import Store

from . import client, conf
from .services import enablement, identity_service, tenant_service


def _is_platform_staff(user):
    # the platform-owner semantics RastiSi already has (portal.platform_admin_views._is_platform_staff)
    return user.is_authenticated and user.is_staff and user.is_superuser


def _text(body: str, status: int = 200) -> HttpResponse:
    response = HttpResponse(body, status=status, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["Vary"] = "Cookie"
    return response


# ----------------------------------------------------------------------------------------------- storefront
@never_cache
@require_GET
def customer_identity(request):
    """`GET /chat/identity/` — the widget's `bootstrap()` target: a fresh single-use assertion for the CURRENT customer of
    THIS storefront, or 401 (guest). Store = Host-resolved; customer = the authenticated session; nothing from the browser."""
    store = getattr(request, "store", None)
    if not enablement.chat_enabled_for_store(store):
        raise Http404
    user = request.user
    customer = getattr(user, "customer_profile", None) if user.is_authenticated else None
    if customer is None or not user.is_active:
        return _text("not signed in", 401)
    origin = f"{request.scheme}://{request.get_host()}"
    return _text(identity_service.customer_assertion(store=store, customer=customer, origin=origin))


# ----------------------------------------------------------------------------------------------- merchant
def _sso_redirect(base_url: str, assertion: str, next_path: str):
    # the assertion travels in the URL FRAGMENT: never sent to a server, never in an access log or Referer
    response = HttpResponseRedirect(f"{base_url.rstrip('/')}/sso#assertion={assertion}&next={quote(next_path, safe='/')}")
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _merchant_chat(request, *, surface: str, next_path: str):
    store = request.store                       # resolved from the ADMIN host by staff_required; membership already checked
    if not enablement.chat_enabled_for_store(store):
        raise Http404
    role = identity_service.staff_role_for(request.store_membership, surface=surface)
    if role is None:
        from django.shortcuts import render as _render
        return _render(request, "dashboard/403.html", status=403)
    tenant_service_role_sync(store, request.user, role)
    return _sso_redirect(settings.RASTICHAT_DASHBOARD_URL, identity_service.staff_assertion(store=store, user=request.user, role=role),
                         next_path)


def tenant_service_role_sync(store, user, role):
    """Make sure the dedicated RastiChat account + membership exist with exactly this role BEFORE the browser arrives
    (idempotent; failures are not fatal — the assertion exchange itself also ensures the membership)."""
    try:
        client.set_staff_member(tenant_service.external_tenant_id(store), identity_service.external_user_id(user), role,
                                identity_service.display_name(user))
    except client.RastiChatError:
        pass


@staff_required
def merchant_customer_chat(request):
    """`/admin-portal/chat/customers/` — the store's customer inbox (owner, administrator, order manager)."""
    return _merchant_chat(request, surface="customers", next_path="/")


@staff_required
def merchant_platform_support(request):
    """`/admin-portal/chat/support/` — talk to the RastiSi platform team (owner, administrator)."""
    return _merchant_chat(request, surface="platform_support", next_path="/support")


# ----------------------------------------------------------------------------------------------- platform owner
platform_only = user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")


@platform_only
@require_POST
def platform_store_chat_enable(request, store_public_id):
    store = get_object_or_404(Store, public_id=store_public_id)
    try:
        enablement.enable_for_store(store, actor=request.user)
        messages.success(request, f"گفتگوی آنلاین برای «{store.name}» فعال شد.")
    except enablement.ChatEnablementError as exc:
        messages.error(request, str(exc))
    except client.RastiChatError:
        messages.error(request, "ارتباط با RastiChat برقرار نشد؛ گفتگو فعال نشد. کمی بعد دوباره تلاش کنید.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@platform_only
@require_POST
def platform_store_chat_disable(request, store_public_id):
    store = get_object_or_404(Store, public_id=store_public_id)
    enablement.disable_for_store(store, actor=request.user)
    messages.success(request, f"گفتگوی آنلاین برای «{store.name}» غیرفعال شد.")
    return redirect("portal_platform_admin:store-detail", store_public_id)


@platform_only
def platform_store_chat_message(request, store_public_id):
    """Platform owner -> store: open (or resume) the support conversation with this store, even if the store never wrote.

    The request to RastiChat is made by THIS server through the trusted contract (`conversations:initiate`), authored by
    the logged-in superuser, with an Idempotency-Key minted when the form is rendered (a double click or a retry cannot
    create a second message)."""
    store = get_object_or_404(Store, public_id=store_public_id)
    if not enablement.chat_enabled_for_store(store):
        raise Http404
    if request.method == "POST":
        subject = (request.POST.get("subject") or "").strip()[:200] or "پیام پلتفرم"
        body = (request.POST.get("message") or "").strip()
        key = request.POST.get("idempotency_key") or ""
        try:
            uuid.UUID(key)
        except ValueError:
            messages.error(request, "درخواست نامعتبر است. صفحه را دوباره باز کنید.")
            return redirect("portal_platform_admin:store-chat-message", store_public_id)
        if not body:
            messages.error(request, "متن پیام نمی‌تواند خالی باشد.")
            return redirect("portal_platform_admin:store-chat-message", store_public_id)
        try:
            client.set_platform_member(identity_service.external_user_id(request.user), "owner",
                                       identity_service.display_name(request.user))
            result = client.start_support_conversation(
                tenant_service.external_tenant_id(store), initiator_user_id=identity_service.external_user_id(request.user),
                subject=subject, message=body, subject_key="platform-message", idempotency_key=f"rs-{key}",
                client_message_id=f"rs-{key}")
        except client.RastiChatError:
            messages.error(request, "ارسال پیام ناموفق بود. دوباره تلاش کنید.")
            return redirect("portal_platform_admin:store-chat-message", store_public_id)
        record_audit_event(
            store=store, actor=request.user, action_code="chat.platform_message_sent", object_type="Store", object_id=store.pk,
            object_label=store.name, metadata={"conversation_id": result.get("conversation_id", ""), "created": bool(result.get("created"))},
        )
        messages.success(request, "پیام برای مدیر فروشگاه ارسال شد." if result.get("created") else "پیام به گفتگوی باز با این فروشگاه افزوده شد.")
        return redirect("portal_platform_admin:store-chat-message", store_public_id)
    return render(request, "chat_integration/platform_message.html", {
        "store": store, "idempotency_key": uuid.uuid4(), "active_nav": "stores",
    })


@platform_only
def platform_chat_inbox(request):
    """Platform owner -> the RastiChat platform inbox, signed in through SSO (no second login)."""
    if not conf.globally_enabled():
        raise Http404
    base = getattr(settings, "RASTICHAT_PLATFORM_DASHBOARD_URL", "") or settings.RASTICHAT_DASHBOARD_URL
    return _sso_redirect(base, identity_service.platform_assertion(user=request.user), "/inbox")
