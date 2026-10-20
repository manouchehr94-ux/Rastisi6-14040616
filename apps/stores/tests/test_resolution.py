from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.resolution import (
    AKHLAGHI_SLUG,
    CompatibilityFallbackUnavailableError,
    IneligibleStoreDomainError,
    InvalidHostnameError,
    StoreNotResolvedError,
    UnknownStoreDomainError,
    _is_development_host,
    _strip_port,
    domain_is_eligible_for_routing,
    require_resolved_store,
    resolve_store_for_hostname,
    resolve_store_for_hostname_or_none,
    resolve_store_for_request,
    resolve_storefront_url_for_store,
)


class StripPortTests(SimpleTestCase):
    def test_removes_port_from_plain_host(self):
        self.assertEqual(_strip_port("shop.example.com:8080"), "shop.example.com")

    def test_no_port_is_unchanged(self):
        self.assertEqual(_strip_port("shop.example.com"), "shop.example.com")

    def test_bracketed_ipv6_with_port(self):
        self.assertEqual(_strip_port("[::1]:8000"), "[::1]")

    def test_bracketed_ipv6_without_port(self):
        self.assertEqual(_strip_port("[::1]"), "[::1]")

    def test_empty_string(self):
        self.assertEqual(_strip_port(""), "")

    def test_none_input(self):
        self.assertEqual(_strip_port(None), "")


def _make_verified_domain(store, hostname, is_primary=True):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=is_primary,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


class ResolveStoreForHostnameNormalizationTests(TestCase):
    """Normalization + lookup: resolve_store_for_hostname must reach the
    same StoreDomain row for every equivalent representation of one host."""

    def setUp(self):
        self.store = Store.objects.create(
            name="Shop", slug="shop-a", status=Store.Status.ACTIVE
        )
        self.domain = _make_verified_domain(self.store, "shop.example.com")

    def test_uppercase_hostname_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("SHOP.EXAMPLE.COM").pk, self.store.pk
        )

    def test_trailing_dot_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com.").pk, self.store.pk
        )

    def test_hostname_with_port_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com:8080").pk, self.store.pk
        )

    def test_mixed_case_whitespace_and_port_resolves(self):
        self.assertEqual(
            resolve_store_for_hostname(" Shop.Example.COM:443 ").pk, self.store.pk
        )

    def test_idna_unicode_input_resolves_the_punycode_domain(self):
        store = Store.objects.create(name="IDN Store", slug="idn-store", status=Store.Status.ACTIVE)
        _make_verified_domain(store, "xn--mgbh0fb.example")
        self.assertEqual(resolve_store_for_hostname("مثال.example").pk, store.pk)

    def test_malformed_url_like_input_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("https://shop.example.com/path")

    def test_input_with_query_string_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("shop.example.com?x=1")

    def test_input_with_credentials_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("user:pass@shop.example.com")

    def test_malformed_label_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("-bad.example.com")

    def test_empty_host_is_invalid(self):
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("")


class EligibilityTests(TestCase):
    """A StoreDomain must resolve only when both the domain is VERIFIED and
    its Store is ACTIVE — every other combination fails closed."""

    def setUp(self):
        self.store = Store.objects.create(
            name="Shop", slug="shop-a", status=Store.Status.ACTIVE
        )

    def test_verified_domain_and_active_store_resolves(self):
        _make_verified_domain(self.store, "shop.example.com")
        self.assertEqual(
            resolve_store_for_hostname("shop.example.com").pk, self.store.pk
        )

    def test_domain_is_eligible_for_routing_true_case(self):
        domain = _make_verified_domain(self.store, "shop.example.com")
        self.assertTrue(domain_is_eligible_for_routing(domain))

    def test_unverified_domain_does_not_resolve(self):
        StoreDomain.objects.create(store=self.store, hostname="shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_pending_domain_does_not_resolve(self):
        StoreDomain.objects.create(
            store=self.store,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.PENDING,
            verification_requested_at=timezone.now(),
            verification_token="pending-token",
        )
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_failed_domain_does_not_resolve(self):
        StoreDomain.objects.create(
            store=self.store,
            hostname="shop.example.com",
            verification_status=StoreDomain.VerificationStatus.FAILED,
        )
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_suspended_store_does_not_resolve(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_closed_store_does_not_resolve(self):
        self.store.status = Store.Status.CLOSED
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_provisioning_store_does_not_resolve(self):
        self.store.status = Store.Status.PROVISIONING
        self.store.save(update_fields=["status"])
        _make_verified_domain(self.store, "shop.example.com")
        with self.assertRaises(IneligibleStoreDomainError):
            resolve_store_for_hostname("shop.example.com")

    def test_unknown_hostname_raises_unknown_not_ineligible(self):
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("totally-unregistered-host.example")


class CompatibilityModeTests(TestCase):
    """The temporary, narrow Akhlaghi compatibility fallback.

    The Akhlaghi Store already exists in every test's starting database
    state — it is created by the ``stores.0002_create_akhlaghi_store`` data
    migration when the test database itself is built (verified: it is not
    created fresh per test). These tests use that existing row via
    ``_akhlaghi()`` rather than creating a second, colliding one.
    """

    def _akhlaghi(self, status=Store.Status.ACTIVE):
        store = Store.objects.get(slug=AKHLAGHI_SLUG)
        if store.status != status:
            store.status = status
            store.save(update_fields=["status"])
        return store

    def test_localhost_resolves_to_akhlaghi_when_sole_active_store(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("localhost").pk, akhlaghi.pk)

    def test_127_0_0_1_resolves_under_the_same_condition(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("127.0.0.1").pk, akhlaghi.pk)

    def test_bracketed_ipv6_localhost_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("[::1]").pk, akhlaghi.pk)

    def test_django_test_host_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("testserver").pk, akhlaghi.pk)

    def test_localhost_with_port_resolves(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(resolve_store_for_hostname("localhost:8000").pk, akhlaghi.pk)

    def test_arbitrary_unknown_public_hostname_does_not_fallback(self):
        self._akhlaghi()
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("some-random-public-host.example")

    def test_fallback_refused_when_a_second_store_exists(self):
        self._akhlaghi()
        Store.objects.create(name="Second", slug="second-store", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")
        self.assertIsNone(resolve_store_for_hostname_or_none("localhost"))

    def test_fallback_refused_when_second_store_is_inactive(self):
        # The "exactly one Store" rule must count every Store row regardless
        # of status — a second Store that is merely provisioning/suspended/
        # closed (not active) must still disable the fallback. This guards
        # against a regression where the count is mistakenly filtered to
        # active Stores only, which would incorrectly keep the fallback
        # available as long as Akhlaghi alone was active.
        self._akhlaghi()
        Store.objects.create(
            name="Second", slug="second-store", status=Store.Status.PROVISIONING
        )
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_when_second_store_is_suspended(self):
        self._akhlaghi()
        Store.objects.create(
            name="Second", slug="second-store", status=Store.Status.SUSPENDED
        )
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_when_second_store_is_closed(self):
        self._akhlaghi()
        Store.objects.create(
            name="Second", slug="second-store", status=Store.Status.CLOSED
        )
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_hostname_ending_in_localhost_is_not_treated_as_a_development_host(self):
        # "localhost.example.com" must never be confused with "localhost"
        # via a substring/suffix match — only an exact match to an allowlist
        # entry may take the compatibility path. Guards against a regression
        # to e.g. `.endswith()`/`in` substring matching, which an attacker
        # could exploit by registering a hostname like this to try to reach
        # the compatibility fallback instead of the authoritative lookup.
        self._akhlaghi()
        self.assertFalse(_is_development_host("localhost.example.com"))
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("localhost.example.com")

    def test_hostname_ending_in_loopback_ip_is_not_treated_as_a_development_host(self):
        self._akhlaghi()
        self.assertFalse(_is_development_host("127.0.0.1.example.com"))
        with self.assertRaises(UnknownStoreDomainError):
            resolve_store_for_hostname("127.0.0.1.example.com")

    def test_development_host_shadows_a_real_storedomain_with_the_same_hostname(self):
        # "127.0.0.1" is, unusually, a syntactically valid hostname per
        # normalize_hostname (four numeric labels joined by dots), so it is
        # theoretically possible to create a real, verified StoreDomain row
        # for it. The development-host allowlist check runs BEFORE, and
        # instead of, the authoritative StoreDomain lookup (by design — see
        # resolution.py's module docstring), so such a row is unreachable
        # via resolution: the compatibility path always wins for this exact
        # string, and the authoritative lookup is never even attempted. No
        # legitimate merchant would ever use a loopback IP as a real custom
        # domain, so this is accepted as a documented quirk, not a tenant-
        # isolation risk — this test pins that the *current* documented
        # behavior does not silently change.
        from unittest import mock

        akhlaghi = self._akhlaghi()
        _make_verified_domain(akhlaghi, "127.0.0.1")

        with mock.patch(
            "apps.stores.models.StoreDomain.objects.select_related"
        ) as select_related_spy:
            resolved = resolve_store_for_hostname("127.0.0.1")

        self.assertEqual(resolved.pk, akhlaghi.pk)
        select_related_spy.assert_not_called()

    def test_fallback_refused_if_sole_store_is_not_akhlaghi(self):
        Store.objects.filter(slug=AKHLAGHI_SLUG).delete()
        Store.objects.create(name="Not Akhlaghi", slug="not-akhlaghi", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_if_akhlaghi_is_not_active(self):
        self._akhlaghi(status=Store.Status.SUSPENDED)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    def test_fallback_refused_when_no_store_exists_at_all(self):
        Store.objects.all().delete()
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            resolve_store_for_hostname("localhost")

    @override_settings(STORES_DEVELOPMENT_HOST_ALLOWLIST={"custom-dev-host"})
    def test_development_allowlist_is_overridable_via_setting(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(
            resolve_store_for_hostname("custom-dev-host").pk, akhlaghi.pk
        )
        # And the default list is no longer active once overridden: "localhost"
        # has no dot, so once it isn't treated as a dev-compat host it fails
        # hostname *syntax* validation outright (never reaches the StoreDomain
        # lookup at all) — proving it was only ever resolvable via the
        # explicitly isolated compatibility path, never as a "real" hostname.
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("localhost")

    @override_settings(STORES_DEVELOPMENT_HOST_ALLOWLIST="prod.example.com")
    def test_bare_string_allowlist_setting_fails_loudly_not_silently(self):
        # A bare string is iterable character-by-character in Python. If
        # this were accepted as-is, "prod.example.com" would silently
        # decompose into single-character "hosts" ('p', 'r', 'o', ...) that
        # can never match a real Host header — a silent misconfiguration
        # that quietly disables the allowlist instead of doing what whoever
        # set it obviously intended. This must fail loudly instead.
        with self.assertRaises(ImproperlyConfigured):
            resolve_store_for_hostname("localhost")

    @override_settings(STORES_DEVELOPMENT_HOST_ALLOWLIST=["Custom-Dev-Host"])
    def test_allowlist_entries_are_matched_case_insensitively(self):
        akhlaghi = self._akhlaghi()
        self.assertEqual(
            resolve_store_for_hostname("custom-dev-host").pk, akhlaghi.pk
        )

    @override_settings(STORES_DEVELOPMENT_HOST_ALLOWLIST=[])
    def test_empty_allowlist_disables_compatibility_mode_entirely(self):
        self._akhlaghi()
        with self.assertRaises(InvalidHostnameError):
            resolve_store_for_hostname("localhost")


class ResolveStoreForHostnameOrNoneTests(TestCase):
    def test_returns_none_instead_of_raising(self):
        self.assertIsNone(resolve_store_for_hostname_or_none("https://bad"))
        self.assertIsNone(resolve_store_for_hostname_or_none("unknown-host.example"))


class RequireResolvedStoreTests(SimpleTestCase):
    class _FakeRequest:
        def __init__(self, store=None):
            if store is not None:
                self.store = store

    def test_raises_when_store_attribute_absent(self):
        with self.assertRaises(StoreNotResolvedError):
            require_resolved_store(self._FakeRequest())

    def test_raises_when_store_is_none(self):
        with self.assertRaises(StoreNotResolvedError):
            require_resolved_store(self._FakeRequest(store=None))

    def test_returns_store_when_resolved(self):
        sentinel = object()
        self.assertIs(require_resolved_store(self._FakeRequest(store=sentinel)), sentinel)


@override_settings(ALLOWED_HOSTS=["a.example.com", "b.example.com"])
class IsolationAdversarialTests(TestCase):
    """Store A's hostname must never resolve Store B, and nothing but the
    Host header may influence resolution.

    ALLOWED_HOSTS is overridden for this class because ``resolve_store_for_request``
    goes through ``request.get_host()``, which is Django's own Host-header
    validation — with the project's default ``ALLOWED_HOSTS = []`` and
    ``DEBUG = True``, only localhost/127.0.0.1/[::1] pass that check, so
    arbitrary test hostnames must be explicitly allowed here.
    """

    def setUp(self):
        self.store_a = Store.objects.create(name="Store A", slug="store-a", status=Store.Status.ACTIVE)
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        self.domain_a = _make_verified_domain(self.store_a, "a.example.com")
        self.domain_b = _make_verified_domain(self.store_b, "b.example.com")

    def test_store_a_hostname_never_resolves_store_b(self):
        resolved = resolve_store_for_hostname("a.example.com")
        self.assertEqual(resolved.pk, self.store_a.pk)
        self.assertNotEqual(resolved.pk, self.store_b.pk)

    def test_store_b_hostname_never_resolves_store_a(self):
        resolved = resolve_store_for_hostname("b.example.com")
        self.assertEqual(resolved.pk, self.store_b.pk)
        self.assertNotEqual(resolved.pk, self.store_a.pk)

    def test_duplicate_hostname_across_stores_is_impossible(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StoreDomain.objects.create(store=self.store_b, hostname="a.example.com")

    def test_request_headers_other_than_host_do_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(
            "/", HTTP_HOST="a.example.com", HTTP_X_FORWARDED_FOR="b.example.com",
            HTTP_X_STORE_ID=str(self.store_b.pk),
        )
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_query_parameters_do_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/?store={self.store_b.pk}", HTTP_HOST="a.example.com")
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_url_path_does_not_affect_resolution(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/stores/{self.store_b.slug}/", HTTP_HOST="a.example.com")
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)

    def test_session_values_do_not_affect_resolution(self):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="a.example.com")
        request.session = SessionStore()
        request.session["store_id"] = self.store_b.pk
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.store_a.pk)


@override_settings(ALLOWED_HOSTS=["a.example.com", "unknown-public-host.example"])
class QueryCountTests(TestCase):
    """Empirically pins the query counts reported for this PR: one bounded
    query for a matched domain, one bounded query for the compatibility
    fallback, one query for an unknown host, and zero queries for an
    invalid host (which fails before any database access)."""

    def setUp(self):
        self.store = Store.objects.create(name="Store A", slug="store-a", status=Store.Status.ACTIVE)
        _make_verified_domain(self.store, "a.example.com")

    def test_matched_verified_domain_is_one_query(self):
        with self.assertNumQueries(1):
            resolve_store_for_hostname("a.example.com")

    def test_development_fallback_is_one_query(self):
        # Isolate to the sole-Store condition the fallback requires — undo
        # setUp's extra Store so only the seeded Akhlaghi Store remains.
        self.store.delete()
        with self.assertNumQueries(1):
            resolve_store_for_hostname("localhost")

    def test_unknown_public_host_is_one_query(self):
        with self.assertNumQueries(1):
            resolve_store_for_hostname_or_none("unknown-public-host.example")

    def test_invalid_hostname_is_zero_queries(self):
        with self.assertNumQueries(0):
            resolve_store_for_hostname_or_none("https://bad/path")


class UnexpectedErrorPropagationTests(TestCase):
    """An unexpected database/programming error must propagate, not be
    silently converted into "unknown tenant". Only StoreResolutionError
    subclasses (and DisallowedHost, one layer up) are ever swallowed."""

    def setUp(self):
        self.store = Store.objects.create(name="Store A", slug="store-a", status=Store.Status.ACTIVE)
        _make_verified_domain(self.store, "a.example.com")

    def test_unexpected_database_error_propagates_from_hostname_lookup(self):
        from django.db import DatabaseError
        from unittest import mock

        with mock.patch(
            "apps.stores.models.StoreDomain.objects.select_related",
            side_effect=DatabaseError("connection lost"),
        ):
            with self.assertRaises(DatabaseError):
                resolve_store_for_hostname("a.example.com")

    def test_unexpected_database_error_is_not_converted_to_none_by_or_none_wrapper(self):
        from django.db import DatabaseError
        from unittest import mock

        with mock.patch(
            "apps.stores.models.StoreDomain.objects.select_related",
            side_effect=DatabaseError("connection lost"),
        ):
            with self.assertRaises(DatabaseError):
                resolve_store_for_hostname_or_none("a.example.com")

    def test_unexpected_database_error_propagates_through_request_resolution(self):
        from django.db import DatabaseError
        from django.test import RequestFactory
        from unittest import mock

        request = RequestFactory().get("/", HTTP_HOST="a.example.com")
        with override_settings(ALLOWED_HOSTS=["a.example.com"]):
            with mock.patch(
                "apps.stores.models.StoreDomain.objects.select_related",
                side_effect=DatabaseError("connection lost"),
            ):
                with self.assertRaises(DatabaseError):
                    resolve_store_for_request(request)


@override_settings(ALLOWED_HOSTS=["trusted.example.com"])
class ForwardedHostTests(TestCase):
    """USE_X_FORWARDED_HOST is False by default in this project (verified:
    not set in shop_core/settings.py, so Django's own default applies), so
    request.get_host() currently uses only the real Host header — an
    X-Forwarded-Host header is inert. This is documented as a required
    operational precondition in SAAS_ARCHITECTURE.md: enabling
    USE_X_FORWARDED_HOST is only safe if the reverse proxy is trusted to
    set/strip that header, since it would otherwise let any client
    influence Store resolution directly."""

    def setUp(self):
        self.trusted_store = Store.objects.create(
            name="Trusted", slug="trusted-store", status=Store.Status.ACTIVE
        )
        _make_verified_domain(self.trusted_store, "trusted.example.com")

    def test_x_forwarded_host_is_ignored_by_default(self):
        from django.test import RequestFactory

        request = RequestFactory().get(
            "/", HTTP_HOST="trusted.example.com", HTTP_X_FORWARDED_HOST="attacker.example.com"
        )
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.trusted_store.pk)

    @override_settings(
        ALLOWED_HOSTS=["trusted.example.com", "attacker.example.com"],
        USE_X_FORWARDED_HOST=True,
    )
    def test_x_forwarded_host_is_honored_once_explicitly_enabled(self):
        # This demonstrates the risk, it does not endorse enabling the
        # setting without a trusted proxy: once USE_X_FORWARDED_HOST=True,
        # Django's own get_host() prefers X-Forwarded-Host over Host, so an
        # untrusted client that can reach the app directly (bypassing any
        # proxy) could influence Store resolution. Deployers must only set
        # USE_X_FORWARDED_HOST=True behind a proxy that strips/overwrites
        # any client-supplied X-Forwarded-Host.
        from django.test import RequestFactory

        request = RequestFactory().get(
            "/", HTTP_HOST="attacker.example.com", HTTP_X_FORWARDED_HOST="trusted.example.com"
        )
        resolved = resolve_store_for_request(request)
        self.assertEqual(resolved.pk, self.trusted_store.pk)


class ResolveStorefrontUrlForStoreTests(TestCase):
    """Back to Store button: resolve_storefront_url_for_store must never use
    admin_subdomain, must respect the explicit custom domain > platform
    subdomain > trial subdomain priority, and must fail closed to None."""

    def setUp(self):
        self.store = Store.objects.create(name="Shop", slug="shop-a", status=Store.Status.ACTIVE)

    def test_no_domain_returns_none(self):
        self.assertIsNone(resolve_storefront_url_for_store(self.store))

    def test_unverified_primary_domain_returns_none(self):
        StoreDomain.objects.create(store=self.store, hostname="shop-a.example.com", is_primary=True)
        self.assertIsNone(resolve_storefront_url_for_store(self.store))

    @override_settings(DEBUG=False)
    def test_verified_primary_domain_used_in_production(self):
        _make_verified_domain(self.store, "shop-a.example.com")
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "https://shop-a.example.com/")

    @override_settings(DEBUG=False)
    def test_uses_request_scheme_when_given(self):
        from django.test import RequestFactory

        _make_verified_domain(self.store, "shop-a.example.com")
        request = RequestFactory().get("/", secure=False)
        url = resolve_storefront_url_for_store(self.store, request)
        self.assertEqual(url, "http://shop-a.example.com/")

    @override_settings(DEBUG=True)
    def test_dev_mode_preserves_localhost_port_8000(self):
        _make_verified_domain(self.store, "code123.rastisi.localhost")
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "http://code123.rastisi.localhost:8000/")

    @override_settings(DEBUG=False)
    def test_never_built_from_admin_subdomain(self):
        _make_verified_domain(self.store, "totally-different-domain.com")
        url = resolve_storefront_url_for_store(self.store)
        self.assertNotIn(self.store.admin_subdomain, url)

    def test_suspended_store_returns_none_even_with_primary_domain(self):
        _make_verified_domain(self.store, "shop-a.example.com")
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        self.assertIsNone(resolve_storefront_url_for_store(self.store))

    def test_retired_domain_is_never_primary_so_returns_none(self):
        # DB constraint (retired_domain_is_never_primary) already forbids a
        # domain being both retired and primary at once — retiring the only
        # domain a Store has (without a replacement becoming primary) must
        # leave it with no eligible storefront URL.
        domain = _make_verified_domain(self.store, "shop-a.example.com")
        domain.is_primary = False
        domain.retired_at = timezone.now()
        domain.save(update_fields=["is_primary", "retired_at"])
        self.assertIsNone(resolve_storefront_url_for_store(self.store))

    @override_settings(DEBUG=False)
    def test_active_custom_domain_outranks_retired_trial_domain(self):
        # Mirrors what activate_custom_domain() does: the previous primary
        # (trial) is retired and un-primaried, the custom domain becomes
        # primary — resolve_storefront_url_for_store just reads is_primary,
        # it never re-derives priority from domain_type itself.
        trial = _make_verified_domain(self.store, "code123.rastisi.ir", is_primary=True)
        trial.is_primary = False
        trial.retired_at = timezone.now()
        trial.save(update_fields=["is_primary", "retired_at"])
        _make_verified_domain(self.store, "digigol.ir", is_primary=True)
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "https://digigol.ir/")

    @override_settings(DEBUG=False)
    def test_custom_domain_takes_priority_over_trial_domain(self):
        StoreDomain.objects.create(
            store=self.store, hostname="code123.rastisi.ir", is_primary=False,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store, hostname="mystore.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "https://mystore.ir/")

    @override_settings(DEBUG=False)
    def test_custom_domain_optional_falls_through_to_platform_subdomain(self):
        """A Store must always have a working link even without ever having
        set up a custom domain — the trial/platform subdomain alone must be
        enough. Custom Domain must never block this."""
        StoreDomain.objects.create(
            store=self.store, hostname="myhandle.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "https://myhandle.rastisi.ir/")

    @override_settings(DEBUG=False)
    def test_falls_through_to_trial_domain_when_nothing_else_exists(self):
        StoreDomain.objects.create(
            store=self.store, hostname="code123.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "https://code123.rastisi.ir/")

    @override_settings(DEBUG=True)
    def test_dev_mode_skips_an_unresolvable_custom_domain_and_falls_through(self):
        """A custom domain with no real DNS (e.g. leftover/seed test data)
        must never leave "Back to Store" pointing at a broken host in local
        development — it must fall through to the next eligible tier."""
        StoreDomain.objects.create(
            store=self.store, hostname="shop-test-domain.local", is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store, hostname="code123.rastisi.localhost", is_primary=False,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "http://code123.rastisi.localhost:8000/")

    @override_settings(DEBUG=True)
    def test_dev_mode_accepts_127_0_0_1(self):
        # "localhost" (no dot) can never actually be stored as a
        # StoreDomain.hostname — normalize_hostname rejects it — so this
        # exercises the realistic case; the bare "localhost"/"127.0.0.1"
        # branch of _is_dev_resolvable_hostname itself is unit-tested
        # directly below regardless of that DB-level constraint.
        StoreDomain.objects.create(
            store=self.store, hostname="127.0.0.1", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        url = resolve_storefront_url_for_store(self.store)
        self.assertEqual(url, "http://127.0.0.1:8000/")

    @override_settings(DEBUG=True)
    def test_is_dev_resolvable_hostname_unit(self):
        from apps.stores.resolution import _is_dev_resolvable_hostname

        self.assertTrue(_is_dev_resolvable_hostname("localhost"))
        self.assertTrue(_is_dev_resolvable_hostname("127.0.0.1"))
        self.assertTrue(_is_dev_resolvable_hostname("teststore.rastisi.localhost"))
        self.assertFalse(_is_dev_resolvable_hostname("shop-test-domain.local"))
        self.assertFalse(_is_dev_resolvable_hostname("mystore.ir"))


class DevStorefrontUrlFollowsTheRequestPortTests(TestCase):
    """FOLLOWUP-03 — the Studio's public/back-to-store link must not hard-code :8000."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        _make_verified_domain(self.store, "code123.rastisi.localhost")

    @override_settings(DEBUG=True, ALLOWED_HOSTS=["*"])
    def test_request_port_is_used(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", HTTP_HOST="x.rastisi.localhost:8003")
        self.assertEqual(resolve_storefront_url_for_store(self.store, request), "http://code123.rastisi.localhost:8003/")

    @override_settings(DEBUG=True, ALLOWED_HOSTS=["*"])
    def test_default_http_port_adds_no_suffix_and_no_request_keeps_8000(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", HTTP_HOST="x.rastisi.localhost")
        self.assertEqual(resolve_storefront_url_for_store(self.store, request), "http://code123.rastisi.localhost/")
        self.assertEqual(resolve_storefront_url_for_store(self.store), "http://code123.rastisi.localhost:8000/")
