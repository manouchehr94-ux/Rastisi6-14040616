"""URLconf for Rastisi's own platform-level host (marketing site + owner
portal) — see ``apps.portal.middleware.PlatformHostRoutingMiddleware`` and
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-97. Only
ever active on a Host listed in ``settings.RASTISI_PLATFORM_HOSTS``;
every other Host keeps using ``shop_core.urls`` (ROOT_URLCONF) untouched.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.portal.views import not_found as handler404  # noqa: F401 — Django urlconf convention

urlpatterns = [
    # Amazon SES -> SNS delivery/bounce/complaint events. This is the ONLY platform-owned, publicly reachable host
    # (the Platform Admin host is deliberately not public; tenant hosts resolve a Store first). Authenticity is
    # enforced by SNS signature + topic allowlist inside the view, not by the host.
    path("notifications/", include("apps.notifications.urls")),
    # Platform billing gateway callback (``billing/return/<token>/``) + signed webhook: the platform's OWN gateway
    # redirects the browser to the canonical platform host (the host registered with the gateway merchant account).
    # Authenticity: unguessable attempt token + server-to-server verify (callback) / HMAC signature (webhook).
    path("billing/", include("apps.billing.urls")),
    path("", include("apps.portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
