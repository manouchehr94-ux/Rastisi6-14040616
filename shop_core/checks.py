"""Django system checks for production authentication infrastructure.

Registered from ``apps.core.apps.CoreConfig.ready``. They validate the
*effective* settings (not just the environment) and key off
``settings.RASTISI_PRODUCTION_MODE`` — the real configured ``DEBUG=False`` —
never ``settings.DEBUG``, which Django's test runner forces to False.

They complement, and share their predicates with, the import-time
``ImproperlyConfigured`` raises in ``shop_core/settings.py`` (needed because
gunicorn/uWSGI never run ``check``). Run ``python manage.py check`` (and
``check --deploy``) in the deploy pipeline; run
``python manage.py verify_rate_limit_cache`` for the live Redis probe. No
check here opens a network connection.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

from shop_core import env_config


def _production():
    return bool(getattr(settings, "RASTISI_PRODUCTION_MODE", False))


def _errors(check_id, problems, hint=None):
    return [Error(problem, hint=hint, id=check_id) for problem in problems]


@register(Tags.security)
def check_rate_limit_cache(app_configs, **kwargs):
    if not _production():
        return []
    problems = env_config.rate_limit_cache_problems(
        getattr(settings, "CACHES", {}),
        alias=getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", env_config.RATE_LIMIT_CACHE_ALIAS),
    )
    return _errors(
        "rastisi.E001", problems,
        hint="Set RASTISI_RATE_LIMIT_CACHE_URL to a redis:// or rediss:// URL shared by all workers.",
    )


@register(Tags.security)
def check_turnstile(app_configs, **kwargs):
    problems = env_config.turnstile_config_problems(
        enabled=bool(getattr(settings, "TURNSTILE_ENABLED", False)),
        site_key=getattr(settings, "TURNSTILE_SITE_KEY", ""),
        secret_key=getattr(settings, "TURNSTILE_SECRET_KEY", ""),
        expected_hostnames=tuple(getattr(settings, "TURNSTILE_EXPECTED_HOSTNAMES", ()) or ()),
        production=_production(),
    )
    return _errors("rastisi.E002", problems)


@register(Tags.security)
def check_trusted_proxy(app_configs, **kwargs):
    errors = []
    try:
        problems = env_config.trusted_proxy_problems(
            trusted_cidrs=tuple(getattr(settings, "RASTISI_TRUSTED_PROXY_CIDRS", ()) or ()),
            secure_proxy_ssl_header=getattr(settings, "SECURE_PROXY_SSL_HEADER", None),
            use_x_forwarded_host=_production() and bool(getattr(settings, "USE_X_FORWARDED_HOST", False)),
        )
    except ValueError:
        problems = ["RASTISI_TRUSTED_PROXY_CIDRS contains an invalid network."]
    errors += _errors("rastisi.E003", problems)

    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        middleware = list(getattr(settings, "MIDDLEWARE", ()))
        sanitizer = "apps.core.middleware.TrustedProxyHeaderMiddleware"
        security = "django.middleware.security.SecurityMiddleware"
        if sanitizer not in middleware or (
            security in middleware and middleware.index(sanitizer) > middleware.index(security)
        ):
            errors.append(Error(
                "SECURE_PROXY_SSL_HEADER is set but TrustedProxyHeaderMiddleware is not before "
                "SecurityMiddleware, so a direct client could spoof HTTPS detection.",
                id="rastisi.E004",
            ))
    return errors


@register(Tags.security)
def check_auth_cookies(app_configs, **kwargs):
    if not _production():
        return []
    problems = env_config.cookie_security_problems(
        session_secure=settings.SESSION_COOKIE_SECURE,
        csrf_secure=settings.CSRF_COOKIE_SECURE,
        session_httponly=settings.SESSION_COOKIE_HTTPONLY,
        session_samesite=settings.SESSION_COOKIE_SAMESITE,
        csrf_samesite=settings.CSRF_COOKIE_SAMESITE,
        session_domain=settings.SESSION_COOKIE_DOMAIN,
        csrf_domain=settings.CSRF_COOKIE_DOMAIN,
    )
    return _errors("rastisi.E005", problems)
