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


def portal_permission_denied(request):
    """The portal's canonical fail-closed response for an authenticated,
    correctly-scoped member who lacks the required action permission — an
    explicit HTTP 403 (never a silent redirect or a 404), mirroring the
    dashboard's ``permission_required`` behavior so denied requests are
    unambiguous and, crucially, perform zero mutation."""
    return render(request, "403.html", status=403)


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
