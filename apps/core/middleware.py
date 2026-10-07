"""Core request middleware."""

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from apps.core.services.client_ip import is_trusted_proxy_peer


class TrustedProxyHeaderMiddleware(MiddlewareMixin):
    """Make ``SECURE_PROXY_SSL_HEADER`` honour only trusted proxies.

    Django trusts the configured header (e.g. ``X-Forwarded-Proto: https``)
    from *any* peer. If a client can reach Django directly it could forge it
    and make a plain-HTTP request look secure (affecting
    ``SECURE_SSL_REDIRECT``, CSRF origin/referer checks, ``request.scheme`` in
    generated absolute URLs). This middleware therefore removes that header
    from ``request.META`` unless the direct peer is in
    ``RASTISI_TRUSTED_PROXY_CIDRS``.

    It MUST be first in ``MIDDLEWARE`` — before ``SecurityMiddleware`` and
    anything else that calls ``request.is_secure()``/``request.scheme``. The
    trusted proxy itself must still strip/overwrite client copies of the
    header (documented in PRODUCTION_CONFIGURATION.md §6).
    """

    def process_request(self, request):
        header = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
        if header and not is_trusted_proxy_peer(request):
            request.META.pop(header[0], None)
        return None
