"""Environment-variable parsing and production-safety validation for ``shop_core.settings``.

These are plain functions with no side effects and no dependency on Django's
settings machinery — kept separate from ``settings.py`` specifically so they
can be unit-tested directly with arbitrary input dictionaries. ``settings.py``
is imported exactly once per process (by Django's own startup), so its
module-level code cannot be re-exercised with different environment variables
inside the same test run; the parsing/validation logic below can be, because
each function accepts an explicit ``environ`` mapping instead of always
reading the real ``os.environ``.
"""

import ipaddress
import os
import re
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

# The literal key Django's ``startproject`` generated for this repository.
# Kept as the *only* allowed fallback, and only while DEBUG=True — production
# must never run with this (or any other hardcoded) key.
DEV_INSECURE_SECRET_KEY = "django-insecure-an#yw@3zj9_hmh3^9t&(4+eu^a8mwtbii9b68yus3q=xnu%f%i"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_SUPPORTED_DATABASE_URL_SCHEMES = {"postgres", "postgresql"}

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _environ(environ):
    return os.environ if environ is None else environ


def env_str(name, default="", *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None:
        return default
    return raw.strip()


def env_bool(name, default, *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f"Environment variable {name}={raw!r} is not a valid boolean "
        "(use one of: true/false, 1/0, yes/no, on/off)."
    )


def env_int(name, default, *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {name}={raw!r} is not a valid integer."
        ) from exc


def env_list(name, default=(), *, environ=None):
    raw = _environ(environ).get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def resolve_secret_key(debug, *, environ=None):
    """Return the SECRET_KEY to use, enforcing production safety.

    Raises ``ImproperlyConfigured`` when ``debug`` is False and no real
    secret key is configured, or the configured value is the known
    development-only key.
    """
    secret_key = env_str("DJANGO_SECRET_KEY", "", environ=environ)
    if not secret_key:
        if debug:
            return DEV_INSECURE_SECRET_KEY
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when DJANGO_DEBUG=False. Generate one with "
            '`python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` '
            "and set it as an environment variable — never commit it."
        )
    if not debug and secret_key == DEV_INSECURE_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is set to the known development-only insecure key. "
            "Set a real, unique secret key before running with DJANGO_DEBUG=False."
        )
    return secret_key


def resolve_allowed_hosts(debug, *, environ=None):
    hosts = env_list("DJANGO_ALLOWED_HOSTS", default=(), environ=environ)
    if not debug and not hosts:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be set (comma-separated hostnames) when DJANGO_DEBUG=False."
        )
    return hosts


def resolve_secure_proxy_ssl_header(*, environ=None):
    """Return a ``SECURE_PROXY_SSL_HEADER`` tuple, or ``None`` if unconfigured.

    Only takes effect when explicitly set to a specific header/value pair —
    this must never be enabled unless the reverse proxy strips/overwrites the
    header for all client traffic, since Django trusts it unconditionally
    once configured.
    """
    raw = env_str("DJANGO_SECURE_PROXY_SSL_HEADER", "", environ=environ)
    if not raw:
        return None
    header_name, sep, header_value = raw.partition(":")
    header_name = header_name.strip()
    header_value = header_value.strip()
    if not sep or not header_name or not header_value:
        raise ImproperlyConfigured(
            "DJANGO_SECURE_PROXY_SSL_HEADER must be 'Header-Name:expected-value', "
            "e.g. 'X-Forwarded-Proto:https' — only set this if your reverse proxy "
            "strips/overwrites this header for all client traffic."
        )
    return (f"HTTP_{header_name.upper().replace('-', '_')}", header_value)


def build_database_config(base_dir, *, environ=None):
    """Build the ``DATABASES["default"]`` dict.

    Falls back to a local SQLite file under ``base_dir`` when ``DATABASE_URL``
    is unset (the local development/test default, unchanged from before this
    module existed). When ``DATABASE_URL`` is set, it must be a valid
    ``postgres://`` URL with a host and a database name — anything else
    raises ``ImproperlyConfigured`` rather than silently falling back to
    SQLite in what was meant to be a production deployment.
    """
    database_url = env_str("DATABASE_URL", "", environ=environ)
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(base_dir / "db.sqlite3"),
        }
    parsed = urlparse(database_url)
    if parsed.scheme not in _SUPPORTED_DATABASE_URL_SCHEMES:
        raise ImproperlyConfigured(
            f"DATABASE_URL scheme {parsed.scheme!r} is not supported; use postgres:// or postgresql://."
        )
    database_name = parsed.path.lstrip("/")
    if not parsed.hostname or not database_name:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a host and a database name, e.g. "
            "postgres://user:password@host:5432/dbname."
        )
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname,
        "PORT": str(parsed.port) if parsed.port else "",
    }


def resolve_log_level(*, environ=None):
    level = env_str("DJANGO_LOG_LEVEL", "INFO", environ=environ).upper()
    if level not in _VALID_LOG_LEVELS:
        raise ImproperlyConfigured(
            f"DJANGO_LOG_LEVEL={level!r} is invalid; use one of {sorted(_VALID_LOG_LEVELS)}."
        )
    return level


# ---------------------------------------------------------------------------
# Production authentication infrastructure (shared rate-limit cache, trusted
# proxies, Turnstile). See docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md §6.
#
# Every function below is pure (explicit ``environ``), never touches the
# network, and never echoes a URL/secret back in an error message — a cache
# URL commonly embeds the Redis password.
# ---------------------------------------------------------------------------

#: Alias of the cache that holds the anonymous-auth rate-limit counters. It is
#: deliberately NOT ``default``: ``default`` stays process-local and is used
#: for non-security caching (e.g. the platform configuration row), so a Redis
#: outage can only ever affect the throttled anonymous endpoints, never every
#: page render.
RATE_LIMIT_CACHE_ALIAS = "ratelimit"

REDIS_CACHE_BACKEND = "django.core.cache.backends.redis.RedisCache"
_LOCMEM_CACHE_BACKEND = "django.core.cache.backends.locmem.LocMemCache"

#: Name of the shared in-process LocMem store used for local development/tests.
#: ``default`` and ``ratelimit`` use the *same* LOCATION so they share storage:
#: ``cache.clear()`` (used throughout the test suite) resets rate-limit state.
_DEV_LOCMEM_LOCATION = "rastisi-local-dev"

#: Seconds. Bound the time an unreachable Redis can stall a request: without
#: a socket timeout a blackholed connection would hang the worker instead of
#: failing closed promptly.
RATE_LIMIT_CACHE_CONNECT_TIMEOUT = 2
RATE_LIMIT_CACHE_SOCKET_TIMEOUT = 2

_REDIS_URL_SCHEMES = {"redis", "rediss"}

#: Cache backends acceptable as the production rate-limit store: shared across
#: processes AND with a server-side atomic INCR / SET-NX-EX.
PRODUCTION_RATE_LIMIT_BACKENDS = frozenset({REDIS_CACHE_BACKEND})

#: Environment token meaning "the peer is a unix-domain-socket / empty
#: REMOTE_ADDR" (gunicorn/uWSGI bound to a socket behind a local proxy).
TRUSTED_PROXY_UNIX_TOKEN = "unix"


def validate_redis_cache_url(url, *, name):
    """Validate a ``redis://`` / ``rediss://`` URL without connecting.

    The URL is never included in the raised message (it may hold a password).
    Query strings are rejected: redis-py would honour options such as
    ``ssl_cert_reqs=none`` there, silently weakening TLS verification.
    """
    try:
        parsed = urlparse(url)
        port = parsed.port  # raises ValueError for a malformed/out-of-range port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} is not a valid URL (bad host/port).") from exc
    if parsed.scheme not in _REDIS_URL_SCHEMES:
        raise ImproperlyConfigured(
            f"{name} must use the redis:// or rediss:// (TLS) scheme."
        )
    if not hostname:
        raise ImproperlyConfigured(f"{name} must include a host, e.g. rediss://:<password>@<host>:6379/0.")
    if parsed.query or parsed.fragment or parsed.params:
        raise ImproperlyConfigured(
            f"{name} must not contain query parameters or fragments; "
            "use the rediss:// scheme for TLS."
        )
    db_path = parsed.path.lstrip("/")
    if db_path and not db_path.isdigit():
        raise ImproperlyConfigured(f"{name} database must be a number, e.g. /0.")
    return port


def build_cache_config(debug, *, environ=None):
    """Build ``CACHES``.

    * ``default`` — always process-local LocMem (non-security caching only).
    * ``ratelimit`` — the anonymous-auth rate-limit store:

      - ``RASTISI_RATE_LIMIT_CACHE_URL`` set -> Django's built-in Redis backend
        (``redis://`` or ``rediss://``), in any mode;
      - unset and ``debug`` -> the shared local LocMem store (dev/tests);
      - unset and not ``debug`` -> ``ImproperlyConfigured``. Production never
        silently falls back to a process-local counter.
    """
    name = "RASTISI_RATE_LIMIT_CACHE_URL"
    url = env_str(name, "", environ=environ)
    default_cache = {"BACKEND": _LOCMEM_CACHE_BACKEND, "LOCATION": _DEV_LOCMEM_LOCATION}
    if not url:
        if not debug:
            raise ImproperlyConfigured(
                f"{name} is required when DJANGO_DEBUG=False: anonymous-auth rate limits "
                "must live in a cache shared by every worker (Redis). Example: "
                "rediss://:<password>@<host>:6379/0 — never commit the real value."
            )
        return {
            "default": default_cache,
            RATE_LIMIT_CACHE_ALIAS: dict(default_cache),
        }
    validate_redis_cache_url(url, name=name)
    return {
        "default": default_cache,
        RATE_LIMIT_CACHE_ALIAS: {
            "BACKEND": REDIS_CACHE_BACKEND,
            "LOCATION": url,
            "OPTIONS": {
                "socket_connect_timeout": RATE_LIMIT_CACHE_CONNECT_TIMEOUT,
                "socket_timeout": RATE_LIMIT_CACHE_SOCKET_TIMEOUT,
            },
        },
    }


def rate_limit_cache_problems(caches, *, alias=RATE_LIMIT_CACHE_ALIAS):
    """Return a list of human-readable problems with the *effective* ``CACHES``
    as a production rate-limit store (empty list = acceptable)."""
    config = (caches or {}).get(alias)
    if not config:
        return [f"CACHES[{alias!r}] is not configured; the rate limiter needs a shared cache."]
    backend = config.get("BACKEND", "")
    if backend not in PRODUCTION_RATE_LIMIT_BACKENDS:
        return [
            f"CACHES[{alias!r}] uses {backend or 'no backend'!r}, which is process-local or "
            "not atomic across workers; production requires the Redis cache backend."
        ]
    if not config.get("LOCATION"):
        return [f"CACHES[{alias!r}] has no LOCATION."]
    return []


def resolve_trusted_proxy_cidrs(*, environ=None):
    """Parse ``DJANGO_TRUSTED_PROXY_CIDRS`` (comma-separated IPv4/IPv6 networks).

    Returns a tuple of canonical network strings; the special token ``unix``
    marks an empty/unix-socket peer as trusted. An unset/empty variable means
    *no* proxy is trusted: forwarded headers are ignored. A bare address
    (``10.0.0.5``) is accepted as a /32 (or /128) host network.
    """
    name = "DJANGO_TRUSTED_PROXY_CIDRS"
    result = []
    for item in env_list(name, default=(), environ=environ):
        if item.lower() == TRUSTED_PROXY_UNIX_TOKEN:
            canonical = TRUSTED_PROXY_UNIX_TOKEN
        else:
            try:
                canonical = str(ipaddress.ip_network(item, strict=False))
            except ValueError as exc:
                raise ImproperlyConfigured(
                    f"{name} contains an invalid network {item!r}; expected comma-separated "
                    "IPv4/IPv6 CIDRs such as '10.0.0.0/8,2001:db8::/32'."
                ) from exc
        if canonical not in result:
            result.append(canonical)
    return tuple(result)


def trusted_proxy_problems(*, trusted_cidrs, secure_proxy_ssl_header, use_x_forwarded_host=False):
    """Contradictory/unsafe proxy configuration (empty list = fine)."""
    problems = []
    if secure_proxy_ssl_header and not trusted_cidrs:
        problems.append(
            "DJANGO_SECURE_PROXY_SSL_HEADER is set but DJANGO_TRUSTED_PROXY_CIDRS is empty: "
            "the forwarded-proto header is only honoured from a trusted proxy, so HTTPS "
            "detection could never work. Configure the proxy network(s) or unset the header."
        )
    for cidr in trusted_cidrs:
        if cidr == TRUSTED_PROXY_UNIX_TOKEN:
            continue
        network = ipaddress.ip_network(cidr, strict=False)
        if network.prefixlen == 0:
            problems.append(
                f"DJANGO_TRUSTED_PROXY_CIDRS contains {cidr}, which trusts every address on the "
                "internet as a proxy and defeats client-IP and HTTPS spoofing protection."
            )
    if use_x_forwarded_host:
        problems.append(
            "USE_X_FORWARDED_HOST must stay False: Store/tenant resolution uses the Host header "
            "(see docs/architecture/SAAS_ARCHITECTURE.md)."
        )
    return problems


_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


def turnstile_config_problems(*, enabled, site_key, secret_key, expected_hostnames, production):
    """Problems with the effective Turnstile configuration (empty list = fine).

    ``production`` is the *real configured* ``DEBUG=False`` state — never
    Django's test-runner-forced ``settings.DEBUG``.
    """
    problems = []
    if production and not enabled:
        problems.append(
            "TURNSTILE_ENABLED must be true when DJANGO_DEBUG=False (bot protection is "
            "never silently disabled in production)."
        )
    if enabled or production:
        if not site_key:
            problems.append("TURNSTILE_SITE_KEY is required.")
        if not secret_key:
            problems.append("TURNSTILE_SECRET_KEY is required.")
        if production and not expected_hostnames:
            problems.append(
                "TURNSTILE_EXPECTED_HOSTNAMES is required (comma-separated bare hostnames, "
                "e.g. rastisi.ir,www.rastisi.ir)."
            )
        for hostname in expected_hostnames:
            if not _HOSTNAME_RE.match(hostname):
                problems.append(
                    "TURNSTILE_EXPECTED_HOSTNAMES entries must be bare hostnames "
                    "(no scheme, port, path or wildcard)."
                )
                break
    return problems


def cookie_security_problems(*, session_secure, csrf_secure, session_httponly, session_samesite,
                             csrf_samesite, session_domain, csrf_domain):
    """Unsafe production auth-cookie configuration (empty list = fine)."""
    problems = []
    if not session_secure:
        problems.append("SESSION_COOKIE_SECURE must be true when DJANGO_DEBUG=False (DJANGO_SESSION_COOKIE_SECURE).")
    if not csrf_secure:
        problems.append("CSRF_COOKIE_SECURE must be true when DJANGO_DEBUG=False (DJANGO_CSRF_COOKIE_SECURE).")
    if not session_httponly:
        problems.append("SESSION_COOKIE_HTTPONLY must be true.")
    for label, value in (("SESSION_COOKIE_SAMESITE", session_samesite), ("CSRF_COOKIE_SAMESITE", csrf_samesite)):
        if str(value or "").lower() not in {"lax", "strict"}:
            problems.append(f"{label} must be 'Lax' or 'Strict'.")
    if session_domain or csrf_domain:
        problems.append(
            "SESSION_COOKIE_DOMAIN/CSRF_COOKIE_DOMAIN must stay unset: sessions are host-only by "
            "design; Merchant Admin uses the one-time handoff ticket, never a parent-domain cookie."
        )
    return problems


def resolve_turnstile_settings(debug, *, environ=None):
    """Parse the ``TURNSTILE_*`` variables and enforce production fail-closed.

    ``TURNSTILE_ENABLED`` defaults to ``not debug``: local development may run
    without it, a ``DEBUG=False`` process may not. Raises ``ImproperlyConfigured``
    listing every problem (never a secret value).
    """
    enabled = env_bool("TURNSTILE_ENABLED", default=not debug, environ=environ)
    site_key = env_str("TURNSTILE_SITE_KEY", "", environ=environ)
    secret_key = env_str("TURNSTILE_SECRET_KEY", "", environ=environ)
    hostnames = tuple(
        value.strip().lower().rstrip(".")
        for value in env_list("TURNSTILE_EXPECTED_HOSTNAMES", default=(), environ=environ)
        if value.strip()
    )
    problems = turnstile_config_problems(
        enabled=enabled, site_key=site_key, secret_key=secret_key,
        expected_hostnames=hostnames, production=not debug,
    )
    if problems:
        raise ImproperlyConfigured("Invalid Turnstile configuration: " + " ".join(problems))
    timeout = env_int("TURNSTILE_VERIFY_TIMEOUT_SECONDS", default=5, environ=environ)
    return {
        "enabled": enabled, "site_key": site_key, "secret_key": secret_key,
        "expected_hostnames": hostnames, "timeout_seconds": timeout,
    }


# ---------------------------------------------------------------------------
# Local-QA owner OTP (DEVELOPMENT ONLY)
# ---------------------------------------------------------------------------

_DEV_OTP_RE = re.compile(r"[0-9]{6}")


def resolve_dev_otp_code(debug, *, environ=None):
    """Parse ``RASTISI_DEV_OTP_CODE`` — the opt-in fixed owner-OTP for local browser QA.

    * empty / unset -> ``""`` (disabled; the secure default).
    * non-empty -> must be exactly six ASCII digits, and ``debug`` must be true:
      with ``DJANGO_DEBUG=False`` this raises, so a production process can never
      start with a known OTP. The value is never echoed in the error message.
    """
    name = "RASTISI_DEV_OTP_CODE"
    raw = env_str(name, "", environ=environ)
    if not raw:
        return ""
    if not debug:
        raise ImproperlyConfigured(
            f"{name} is a DEVELOPMENT-ONLY local-QA setting and must be unset when DJANGO_DEBUG=False."
        )
    if not (raw.isascii() and _DEV_OTP_RE.fullmatch(raw)):
        raise ImproperlyConfigured(f"{name} must be exactly 6 ASCII digits (e.g. 123456), or empty to disable it.")
    return raw


def resolve_allow_console_otp(debug, *, running_tests, environ=None):
    """``RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP``: lets the *console* platform provider report
    success. Defaults to on only for ``manage.py test``. Explicitly enabling it with
    ``DJANGO_DEBUG=False`` is refused, so it cannot become a production escape hatch."""
    name = "RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP"
    value = env_bool(name, default=running_tests, environ=environ)
    if value and not debug and not running_tests:
        raise ImproperlyConfigured(
            f"{name} must not be enabled when DJANGO_DEBUG=False (it would fake OTP delivery in production)."
        )
    return value


def dev_otp_problems(*, dev_otp_code, allow_console_otp, production, running_tests=False):
    """Problems with the effective local-QA OTP settings (empty list = fine)."""
    problems = []
    if production and dev_otp_code:
        problems.append("RASTISI_DEV_OTP_CODE must be empty when DJANGO_DEBUG=False (development-only setting).")
    if production and allow_console_otp and not running_tests:
        problems.append(
            "RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP must be false when DJANGO_DEBUG=False "
            "(it would report fake OTP delivery)."
        )
    return problems
