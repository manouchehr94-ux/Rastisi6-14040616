"""
URL configuration for shop_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.core.seo import robots_txt, sitemap_xml
from apps.core.views import admin_panel_compat_redirect, favicon_view

urlpatterns = [
    path("favicon.ico", favicon_view, name="favicon"),
    # SEO — tenant-safe, scoped to the Host-resolved Store (ADR-90).
    path("sitemap.xml", sitemap_xml, name="sitemap-xml"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("admin/", admin.site.urls),
    path("", include("apps.catalog.urls")),
    path("cart/", include("apps.cart.urls")),
    path("account/", include("apps.customers.urls")),
    # RastiChat adapter (storefront identity bootstrap) — 404 unless chat is enabled for the Host-resolved store.
    path("chat/", include("apps.chat_integration.urls")),
    path("checkout/", include("apps.orders.urls")),
    # Canonical Merchant Admin Portal route (Phase 1B, ADR-16). Not to be
    # confused with Django's own "admin/" (apps.stores.admin_permissions
    # restricts that one to Platform Superusers only) — this is the
    # merchant-facing dashboard, gated by apps.dashboard.decorators.staff_required.
    path("admin-portal/", include("apps.dashboard.urls")),
    # Temporary backward-compatible redirect from the pre-Phase-1B path.
    path("admin-panel/", admin_panel_compat_redirect, name="admin-panel-compat-redirect"),
    path("admin-panel/<path:rest>", admin_panel_compat_redirect, name="admin-panel-compat-redirect-path"),
    path("pages/", include("apps.content.urls")),
    # SaaS billing webhook endpoint (public, signature-verified, no CSRF).
    path("billing/", include("apps.billing.urls")),
    # SmsRasti Android gateway poll/ack endpoints (public, device-token-authenticated, no CSRF).
    path("sms/", include("apps.sms.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
