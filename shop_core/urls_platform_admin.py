"""URLconf for Rastisi's Platform Admin host — see
``apps.portal.middleware.PlatformHostRoutingMiddleware`` and ADR-97. Only
ever active on a Host listed in ``settings.RASTISI_PLATFORM_ADMIN_HOSTS``;
completely host-isolated from both per-Store routing and the owner-portal
host.

Delegates to ``apps.portal.platform_admin_urls`` via ``include()`` rather
than defining ``app_name``/patterns directly in this module: a namespace
declared on a URLconf module only takes effect when that module is the
target of ``include()`` — a module used directly as ``request.urlconf`` (as
this one is) never registers its own ``app_name`` as a namespace, so
``reverse("portal_platform_admin:...")`` would silently fail to find it.
"""

from django.urls import include, path

from apps.portal.platform_admin_views import not_found as handler404  # noqa: F401 — Django urlconf convention
from apps.portal.platform_admin_views import permission_denied as handler403  # noqa: F401 — Django urlconf convention

urlpatterns = [
    path("", include("apps.portal.platform_admin_urls")),
]
