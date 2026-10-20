"""Authoritative request-time Store resolution.

This module is the ONLY place in the codebase that decides "which Store
does this HTTP request belong to." No view, context processor, dashboard
service, or future business-logic code should independently guess a Store
from a hostname, a caller-supplied ID, the authenticated user, a Vendor, a
Product, a Cart, or a session value. See
``docs/architecture/SAAS_ARCHITECTURE.md`` ("Request Store Context") for
the policy this module implements, and
``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` for why tenant resolution,
authentication, authorization, and data filtering are kept as separate
concerns.

Resolution source of truth: ``StoreDomain.hostname`` — verified domains of
an active Store only (``domain_is_eligible_for_routing``). A narrow,
explicitly isolated, temporary compatibility fallback additionally allows a
fixed allowlist of local-development hosts to resolve to the Akhlaghi Store,
but only while the database contains exactly one, active, "akhlaghi" Store
(``resolve_compatibility_store``). The fallback fails closed the moment a
second Store exists — it is not a permanent behavior.
"""

from django.conf import settings as django_settings
from django.core.exceptions import DisallowedHost, ImproperlyConfigured, ValidationError

from .hostnames import normalize_hostname
from .models import Store, StoreDomain

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StoreResolutionError(Exception):
    """Base class for all Store-resolution failures.

    Never surface ``str(exc)`` from one of these directly in an HTTP
    response — these messages exist for logs and tests, not public callers
    (see module docstring: resolution must not leak tenant-existence
    details). ``resolve_store_for_request`` never raises these; it converts
    every one of them into ``None``.
    """


class InvalidHostnameError(StoreResolutionError):
    """The supplied host is not a syntactically valid, resolvable hostname."""


class UnknownStoreDomainError(StoreResolutionError):
    """The hostname is syntactically valid, but no ``StoreDomain`` row matches it."""


class IneligibleStoreDomainError(StoreResolutionError):
    """A ``StoreDomain`` matches, but it — or its Store — is not eligible for
    request routing right now. See ``domain_is_eligible_for_routing``."""


class CompatibilityFallbackUnavailableError(StoreResolutionError):
    """The host is an approved development host, but the narrow conditions
    required for the temporary Akhlaghi compatibility fallback are not met
    (more than one Store exists, the sole Store isn't Akhlaghi, or it isn't
    active)."""


class StoreNotResolvedError(StoreResolutionError):
    """Raised by ``require_resolved_store`` when a caller needs a Store that
    was never resolved for this request."""


# ---------------------------------------------------------------------------
# Routing eligibility policy
# ---------------------------------------------------------------------------


def domain_is_eligible_for_routing(domain: StoreDomain) -> bool:
    """The exact, minimal routing-eligibility policy for this PR.

    A ``StoreDomain`` may route a request only when ALL of:

    * its Store's ``status`` is ``ACTIVE`` — not provisioning, suspended, or closed;
    * its own ``verification_status`` is ``VERIFIED`` — not unverified, pending, or failed;
    * it has not been retired (``retired_at is None``) — a retired hostname
      (e.g. a generated trial hostname superseded by a paid permanent handle,
      ADR-101) never routes again, and never redirects either; it simply
      stops resolving, exactly like an unverified domain would.

    Anything else fails closed. An unverified, pending, failed, or retired
    domain, or a domain whose Store is not active, must never resolve —
    even if the hostname otherwise matches a real, existing row.
    """
    return (
        domain.store.status == Store.Status.ACTIVE
        and domain.verification_status == StoreDomain.VerificationStatus.VERIFIED
        and domain.retired_at is None
    )


# ---------------------------------------------------------------------------
# Hostname helpers
# ---------------------------------------------------------------------------


def _strip_port(host: str) -> str:
    """Remove a trailing ``:port`` from an HTTP host value, safely.

    Bracketed IPv6 literals (e.g. ``[::1]:8000``) are handled explicitly so
    the brackets are never mistaken for part of the hostname or the port.
    """
    host = (host or "").strip()
    if not host:
        return host
    if host.startswith("["):
        closing = host.find("]")
        return host[: closing + 1] if closing != -1 else host
    if host.count(":") == 1:
        base, _, _port = host.rpartition(":")
        return base
    return host


#: Public alias of ``_strip_port`` for external callers (e.g.
#: ``apps.portal.middleware.PlatformHostRoutingMiddleware``) that need the
#: same Host normalization without reaching into a name-mangled "private"
#: helper.
strip_port = _strip_port


# ---------------------------------------------------------------------------
# Development/compatibility fallback — deliberately isolated from the
# authoritative StoreDomain lookup path below.
# ---------------------------------------------------------------------------

#: Hosts that may ever attempt the temporary Akhlaghi compatibility
#: fallback. These are not, and must never become, real StoreDomain rows —
#: that is precisely why this list is checked BEFORE, and instead of, the
#: authoritative StoreDomain lookup. Overridable via the
#: ``STORES_DEVELOPMENT_HOST_ALLOWLIST`` Django setting (tests use this).
DEFAULT_DEVELOPMENT_HOST_ALLOWLIST = frozenset({
    "localhost",
    "127.0.0.1",
    "[::1]",
    "testserver",  # Django test client's default HTTP Host
})

#: Duplicates apps/stores/migrations/0002_create_akhlaghi_store.py's seed
#: slug value intentionally. Runtime code must never import a migration
#: module, so this is a small, deliberate, documented duplication rather
#: than a shared import.
AKHLAGHI_SLUG = "akhlaghi"


def _development_host_allowlist():
    configured = getattr(
        django_settings, "STORES_DEVELOPMENT_HOST_ALLOWLIST", DEFAULT_DEVELOPMENT_HOST_ALLOWLIST
    )
    # A bare string is iterable character-by-character in Python. Silently
    # accepting one here would decompose e.g. "prod.example.com" into
    # single-character "hosts" that can never match a real Host header —
    # not a security hole by itself (no real request ever has a one-
    # character Host), but a silent misconfiguration that quietly disables
    # the allowlist instead of doing what whoever set it obviously intended.
    # Fail loudly instead: a bare string is always a configuration mistake.
    if isinstance(configured, str):
        raise ImproperlyConfigured(
            "STORES_DEVELOPMENT_HOST_ALLOWLIST must be a list/tuple/set of "
            "hostnames, not a bare string (a string would be iterated "
            "character-by-character)."
        )
    return frozenset(h.lower() for h in configured)


def _is_development_host(stripped_host: str) -> bool:
    return stripped_host.lower() in _development_host_allowlist()


def resolve_compatibility_store() -> Store:
    """The narrow, temporary single-Store compatibility fallback.

    Returns the Akhlaghi Store only when ALL of the following hold:

    * exactly one Store exists in the entire database;
    * that Store's slug is ``"akhlaghi"``;
    * that Store's status is ``ACTIVE``.

    Raises ``CompatibilityFallbackUnavailableError`` otherwise. In
    particular, the moment a second Store is created anywhere on the
    platform, this fails closed instead of guessing — it never falls back
    to "the first Store" or any other heuristic. This exists only to let
    Akhlaghi keep working locally before a real, verified ``StoreDomain``
    is provisioned for it; it is not a permanent behavior and must not be
    relied upon once a real domain exists.

    Public (not host-specific) on purpose: this same "is there exactly one
    active Akhlaghi Store" check is also the compatibility rule for
    Store-scoped settings retrieval (``apps.core.models.ShopSettings.load()``,
    ``apps.content.models.FooterSettings.load()``) when no explicit Store is
    given — reusing it here keeps there being exactly one fail-closed check,
    not two independently-maintained copies of the same safety rule.
    """
    stores = list(Store.objects.all()[:2])
    if len(stores) != 1:
        raise CompatibilityFallbackUnavailableError(
            "compatibility fallback requires exactly one Store to exist"
        )
    store = stores[0]
    if store.slug != AKHLAGHI_SLUG:
        raise CompatibilityFallbackUnavailableError("the sole Store is not Akhlaghi")
    if store.status != Store.Status.ACTIVE:
        raise CompatibilityFallbackUnavailableError("the Akhlaghi Store is not active")
    return store


# ---------------------------------------------------------------------------
# Public resolution interface
# ---------------------------------------------------------------------------


def resolve_store_for_hostname(raw_host: str) -> Store:
    """Resolve a Store from a raw HTTP host value (may include a port).

    Raises one of the ``StoreResolutionError`` subclasses above on any
    failure, so callers (typically tests) can distinguish *why* resolution
    failed. Use ``resolve_store_for_hostname_or_none`` when only a
    yes/no-with-fallback-to-None result is needed.
    """
    stripped = _strip_port(raw_host)

    if _is_development_host(stripped):
        return resolve_compatibility_store()

    try:
        normalized = normalize_hostname(stripped)
    except ValidationError as exc:
        raise InvalidHostnameError(str(exc)) from exc

    domain = (
        StoreDomain.objects.select_related("store").filter(hostname=normalized).first()
    )
    if domain is None:
        raise UnknownStoreDomainError(f"no StoreDomain matches {normalized!r}")

    if not domain_is_eligible_for_routing(domain):
        raise IneligibleStoreDomainError(
            f"StoreDomain {normalized!r} is not eligible for routing"
        )

    return domain.store


def resolve_store_for_hostname_or_none(raw_host: str):
    """Same as ``resolve_store_for_hostname``, but returns ``None`` instead
    of raising on any ``StoreResolutionError``."""
    try:
        return resolve_store_for_hostname(raw_host)
    except StoreResolutionError:
        return None


def resolve_store_for_request(request):
    """Resolve a Store for an in-flight ``HttpRequest``. Never raises.

    Uses ``request.get_host()`` — Django's own Host-header parsing and
    ``ALLOWED_HOSTS`` validation — as the sole source of the hostname.
    Never a caller-supplied Store ID, a query parameter, a header other
    than ``Host``, the URL path, a session value, or an authenticated
    membership. Returns ``None`` for any failure, including an
    already-disallowed Host header: this function must never raise, since
    it is what the middleware calls directly on every request.
    """
    try:
        raw_host = request.get_host()
    except DisallowedHost:
        return None
    return resolve_store_for_hostname_or_none(raw_host)


def resolve_store_for_service(request) -> Store:
    """The authoritative Store for a service call triggered by an HTTP request.

    Returns ``request.store`` if the resolution middleware already resolved
    one for this request; otherwise falls back to the same narrow,
    fail-closed compatibility check every other caller uses
    (``resolve_compatibility_store``) — never a bare ``Store.objects.first()``
    or any other guess. Raises ``CompatibilityFallbackUnavailableError`` if
    neither source yields a Store.

    Call this ONCE, at the HTTP boundary (a view, or a request-aware service
    function), then pass the concrete ``Store`` object down explicitly to
    deeper service functions (pricing, SMS, order creation, ...) as a
    required argument. Those deeper functions must never re-derive a Store
    from the Host themselves — resolution happens here, exactly once per
    request, not repeatedly deep inside domain services.
    """
    store = getattr(request, "store", None)
    if store is not None:
        return store
    return resolve_compatibility_store()


def resolve_store_for_storefront(request) -> Store:
    """Storefront entry-point resolver (Checkpoint 6, ADR-83): like
    ``resolve_store_for_service`` but converts an unresolved Host into a clean
    ``Http404`` instead of a 500.

    A customer hitting an unknown, inactive, suspended, or closed store's host
    must see a normal not-found page, never a server error. Inactive/suspended/
    closed stores never resolve (their ``StoreDomain`` only matches while
    ``status == ACTIVE``), so they land here and 404 — the fail-closed customer-
    facing behavior. Use this in public storefront views; deeper service code
    keeps using ``resolve_store_for_service`` with the concrete Store passed in.

    Section 6 (ADR-103): a resolved Store that exists but is not currently
    *publicly visible* (still onboarding, trial-restricted, subscription-
    restricted, suspended, or inactive — ``apps.stores.services.
    publication_service.is_publicly_visible``) raises ``PermissionDenied``
    instead of returning it — Django's own ``handler403`` renders
    ``templates/403.html`` with the explanatory message. This is
    deliberately distinct from ``Http404``: the Store is real, the host is
    real, the visitor just isn't allowed to see it *right now*.
    """
    from django.core.exceptions import PermissionDenied
    from django.http import Http404

    try:
        store = resolve_store_for_service(request)
    except CompatibilityFallbackUnavailableError as exc:
        raise Http404("no storefront for this host") from exc

    from .services.publication_service import get_store_publication_state, is_publicly_visible

    if not is_publicly_visible(store):
        raise PermissionDenied(
            f"store_not_publicly_visible:{get_store_publication_state(store)}"
        )
    return store


def require_resolved_store(request) -> Store:
    """For future Store-aware service code: return ``request.store``, or raise.

    Nothing in this PR consumes this helper — no business logic depends on
    Store resolution yet. It is provided now as the single, documented way
    later code should assert "this operation requires an already-resolved
    Store," instead of each future caller re-deriving or re-guessing one
    independently.
    """
    store = getattr(request, "store", None)
    if store is None:
        raise StoreNotResolvedError("no Store was resolved for this request")
    return store


# ---------------------------------------------------------------------------
# Admin-subdomain resolution (Phase 1B) — a second, independent resolution
# path from the public-domain one above.
# ---------------------------------------------------------------------------


def resolve_store_for_admin_host(raw_host: str):
    """Resolve a Store from a raw admin Host value, or ``None``.

    Unlike ``resolve_store_for_hostname`` (which looks up a verified,
    merchant-supplied ``StoreDomain``), this only ever matches a Host of the
    exact shape ``f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"``
    — the platform-assigned merchant-admin host, completely independent of
    any public storefront domain. Returns ``None`` (never raises) for a Host
    that isn't under the admin suffix at all, has more/fewer than one label
    before it, doesn't match any Store's ``admin_subdomain``, or whose Store
    isn't ``ACTIVE`` — same fail-closed spirit as
    ``resolve_store_for_hostname_or_none``.

    This function exists as new, tested, standalone infrastructure. It is
    not yet wired into ``StoreResolutionMiddleware`` or
    ``apps.dashboard.decorators.staff_required`` — doing so safely requires
    updating every existing multi-Store dashboard test's Host fixtures to
    use an admin-suffixed host instead of a generic one, which is separate,
    larger follow-up work (see the Phase 1B report's Known Limitations).
    """
    stripped = _strip_port(raw_host).lower()
    suffix = "." + django_settings.RASTISI_ADMIN_DOMAIN_SUFFIX.lower()
    if not stripped.endswith(suffix):
        return None

    label = stripped[: -len(suffix)]
    if not label or "." in label:
        return None

    try:
        store = Store.objects.get(admin_subdomain=label)
    except Store.DoesNotExist:
        return None

    if store.status != Store.Status.ACTIVE:
        return None
    return store


def resolve_store_for_admin_request(request):
    """The authoritative Store resolution for the Merchant Admin Portal
    (Phase 1C). Never raises; returns ``None`` for any host the admin
    portal must not be served from.

    Tries, in order:

    1. ``resolve_store_for_admin_host`` — a real
       ``f"{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}"`` match. This is
       the only path a real deployment's admin traffic should ever take.
    2. If the Host is on the narrow, approved local-development/test
       allowlist (``testserver``, ``localhost``, ``127.0.0.1``, ...| — the
       same list ``apps.stores.resolution`` already uses for public-domain
       resolution), falls back to ``resolve_store_for_request`` (the
       ordinary public-domain-or-single-Store-compatibility resolver).
       This is what lets local development and the existing test suite's
       single-Store fixtures reach the dashboard without a real
       admin-subdomain-shaped Host configured; it is not available for a
       Host that isn't on the allowlist.

    Any other Host — including a real, syntactically valid, verified
    public ``StoreDomain`` that simply isn't this Store's admin subdomain —
    resolves to ``None``. This is the fix for the Phase 1B "Known
    Limitations" gap: a Store's public storefront domain must not also
    serve its Merchant Admin Portal.
    """
    try:
        raw_host = request.get_host()
    except DisallowedHost:
        return None

    admin_store = resolve_store_for_admin_host(raw_host)
    if admin_store is not None:
        return admin_store

    if _is_development_host(_strip_port(raw_host).lower()):
        return resolve_store_for_request(request)

    return None


# ---------------------------------------------------------------------------
# Storefront URL resolution ("Back to Store") — the reverse of admin-host
# resolution above: given a Store, what is its current public storefront URL?
# ---------------------------------------------------------------------------


#: ترتیبِ صریحِ اولویتِ دامنه برایِ لینکِ «بازگشت به فروشگاه»: دامنه‌ی
#: اختصاصیِ تأییدشده → زیردامنه‌ی دائمیِ عمومیِ راستیسی (نامِ ادعاشده) →
#: زیردامنه‌ی آزمایشی. عمداً به ``is_primary`` تکیه نمی‌کند — آن پرچم برایِ
#: تشخیصِ «کدام دامنه اکنون درخواست‌های عمومی را مسیریابی می‌کند» است، نه
#: قراردادی که این تابع باید حفظ کند؛ شمارشِ صریحِ نوع، حتی اگر داده‌ی
#: توسعه/تست دامنه‌ای غیرِ Primary اما دومینِ نوعِ بالاترِ اولویت داشته
#: باشد (یا برعکس، Primary فعلی یک دامنه‌ی واقعی/نامعتبر برایِ محیطِ فعلی
#: باشد)، درست کار می‌کند.
_STOREFRONT_DOMAIN_TYPE_PRIORITY = (
    StoreDomain.DomainType.CUSTOM_DOMAIN,
    StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
    StoreDomain.DomainType.GENERATED_TRIAL,
)


def _is_dev_resolvable_hostname(hostname: str) -> bool:
    """آیا این میزبان در محیطِ توسعه/سندباکسِ محلی واقعاً قابلِ‌بازکردن است؟

    فقط در ``settings.DEBUG`` استفاده می‌شود — یک دامنه‌ی اختصاصیِ واقعی که
    به‌اشتباه (مثلاً داده‌ی آزمایشی) به‌عنوانِ تأییدشده ثبت شده اما اصلاً DNSِ
    واقعی/قابلِ‌حلی ندارد (مثلاً یک ``.local`` جعلی) نباید کاربر را به یک
    میزبانِ غیرقابلِ‌بازشدن بفرستد؛ در آن صورت باید به لایه‌ی بعدیِ اولویت
    (زیردامنه‌ی دائمی، سپس آزمایشی) سقوط کند — هر دو همیشه زیرِ همان
    ``RASTISI_ADMIN_DOMAIN_SUFFIX``ی ساخته می‌شوند که در DEBUG همیشه
    ``rastisi.localhost`` است، پس همیشه در همین سندباکس قابلِ‌بازشدن‌اند."""
    stripped = _strip_port(hostname).lower()
    if stripped in ("localhost", "127.0.0.1", "[::1]"):
        return True
    # ``.rastisi.localhost`` بررسیِ صریح و ثابت است، نه فقط از رویِ
    # ``RASTISI_ADMIN_DOMAIN_SUFFIX`` فعلی — آن مقدار فقط یک‌بار، هنگامِ
    # بارگذاریِ settings (بر اساسِ DEBUGِ واقعیِ فرایند)، تنظیم می‌شود، نه
    # هر بار که یک تست با ``@override_settings(DEBUG=True)`` آن را شبیه‌سازی
    # می‌کند؛ این قراردادِ محلیِ توسعه‌ی این کدبیس همیشه باید تشخیص داده شود.
    if stripped.endswith(".rastisi.localhost"):
        return True
    suffix = "." + django_settings.RASTISI_ADMIN_DOMAIN_SUFFIX.lower()
    return stripped.endswith(suffix)


def _dev_port_suffix(request) -> str:
    """Development only: the port of the server that is actually answering (never a hard-coded ``8000``), so the
    Studio "public view" / "back to store" links work on whatever port ``runserver`` was started with. Without a
    request (management commands, tests) the historical default ``:8000`` is kept; the default HTTP ports add no suffix."""
    if request is None:
        return ":8000"
    try:
        from django.http.request import split_domain_port

        port = split_domain_port(request.get_host())[1] or str(request.get_port())
    except Exception:  # defensive: a malformed Host must never break a page that only renders a link
        return ":8000"
    if not port.isdigit() or port in ("80", "443"):
        return ""
    return f":{port}"


def resolve_storefront_url_for_store(store: Store, request=None):
    """The Store's current best public storefront URL, or ``None``.

    Priority is explicit, not derived from ``is_primary``:

    1. a verified, eligible custom domain (``DomainType.CUSTOM_DOMAIN``);
    2. a claimed, active public Rastisi subdomain (``DomainType.PLATFORM_SUBDOMAIN``);
    3. the generated trial subdomain (``DomainType.GENERATED_TRIAL``).

    Each tier still goes through ``domain_is_eligible_for_routing`` (the
    same fail-closed eligibility check ``resolve_store_for_hostname`` uses),
    so a suspended/closed Store or an unverified/retired domain never
    produces a URL that would just 404. A custom domain must never block a
    trial store from having a working "Back to Store" link — this function
    always falls through to the next tier rather than stopping at the first
    *matching* (but ineligible or, in DEBUG, unresolvable) domain.

    In development (``settings.DEBUG``), a domain whose hostname isn't
    actually resolvable in this sandbox (not ``localhost``/``127.0.0.1``/
    ``*.{RASTISI_ADMIN_DOMAIN_SUFFIX}``) is skipped even if it is otherwise
    "verified" — e.g. test/seed data for a real-looking custom domain that
    has no real DNS. This is what makes local development always reach a
    working link instead of a broken external host.

    Never built from ``store.admin_subdomain`` — that is the Merchant Admin
    Portal's own host and is never a public storefront domain (see
    ``Store.admin_subdomain``'s docstring).

    In development (``settings.DEBUG``), preserves the dev server port of the
    CURRENT request (``:8000`` only when there is no request) — mirroring the same pattern ``apps.portal.views.enter_admin`` uses
    for the admin-host equivalent of this link. Otherwise uses ``request``'s
    scheme when given, defaulting to ``https``.
    """
    domains_by_type: dict[str, list] = {}
    for domain in store.domains.filter(domain_type__in=_STOREFRONT_DOMAIN_TYPE_PRIORITY).order_by(
        "-is_primary", "hostname"
    ):
        domains_by_type.setdefault(domain.domain_type, []).append(domain)

    for domain_type in _STOREFRONT_DOMAIN_TYPE_PRIORITY:
        for domain in domains_by_type.get(domain_type, []):
            if not domain_is_eligible_for_routing(domain):
                continue
            if django_settings.DEBUG and not _is_dev_resolvable_hostname(domain.hostname):
                continue
            if django_settings.DEBUG:
                return f"http://{domain.hostname}{_dev_port_suffix(request)}/"
            scheme = request.scheme if request is not None else "https"
            return f"{scheme}://{domain.hostname}/"
    return None
