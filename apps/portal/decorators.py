from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse

from apps.stores.authorization import user_has_permission


def portal_action_allowed(request, store, permission) -> bool:
    """Whether the requesting user may perform ``permission`` on ``store``.

    Thin delegation to the single canonical action-authorization authority,
    ``apps.stores.authorization.user_has_permission`` (``ROLE_PERMISSIONS`` +
    the user's ACTIVE ``StoreMembership``). The portal deliberately owns no
    role matrix or permission registry of its own — it is only a second
    *consumer* of the same authority the Merchant Admin dashboard uses.

    Tenant scope and action authorization stay separate concepts: the caller
    is expected to have already resolved ``store`` to one the user is an
    ACTIVE member of (``portal.views._get_owned_store_or_404``); this adds the
    orthogonal check that the member's role actually grants the action.
    """
    return user_has_permission(request.user, store, permission)


def portal_actions_allowed(request, store, *permissions) -> bool:
    """Whether the requesting user holds *every* one of ``permissions`` on
    ``store`` (AND semantics). Same thin delegation to the canonical
    ``user_has_permission`` authority as :func:`portal_action_allowed`; used
    where an action's authorization requires more than one canonical key
    (e.g. subscription purchase needs both the plan-change decision and the
    billing-payment authority)."""
    return all(user_has_permission(request.user, store, p) for p in permissions)


def portal_permission_denied(request):
    """The portal's canonical fail-closed response for an authenticated,
    correctly-scoped member who lacks the required action permission — an
    explicit HTTP 403 (never a silent redirect or a 404), mirroring the
    dashboard's ``permission_required`` behavior so denied requests are
    unambiguous and, crucially, perform zero mutation.

    Renders ``portal/403.html``, NOT the global Storefront-scoped
    ``templates/403.html`` — that template extends ``base.html`` and
    reverses Storefront-only URL names (``catalog:home``,
    ``customers:account``), which do not exist under
    ``shop_core.urls_platform`` (the URLconf that serves every portal/
    owner-facing request; see ``apps.portal.middleware.
    PlatformHostRoutingMiddleware`` and ADR-97). Using the global template
    here would turn a correct 403 decision into a ``NoReverseMatch``/500.
    This mirrors ``apps.portal.views.not_found``'s identical host-boundary
    handling for 404 (``portal/public/404.html``, self-contained within
    ``portal/base_platform.html``)."""
    return render(request, "portal/403.html", status=403)


def owner_required(view_func):
    """معادلِ ``login_required`` جنگو، اما مخصوصِ پرتالِ مالکان — به صفحه‌ی
    ورودِ اختصاصیِ پرتال (``portal:login``) هدایت می‌کند، نه ``settings.
    LOGIN_URL`` سراسری (که اینجا دست‌نخورده می‌ماند تا هیچ مسیرِ ورودِ دیگری
    در پروژه، مثلِ ویوهای مشتری، تحتِ تأثیر قرار نگیرد)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            params = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('portal:login')}?{params}")
        return view_func(request, *args, **kwargs)

    return wrapper
