from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.stores.middleware import StoreResolutionMiddleware
from apps.stores.models import Store, StoreDomain
from apps.stores.resolution import resolve_store_for_request

User = get_user_model()


def _make_verified_domain(store, hostname, is_primary=True):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=is_primary,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=["a.example.com"])
class StoreResolutionMiddlewareUnitTests(TestCase):
    """Direct middleware tests using a dummy get_response, isolated from the
    rest of the request/response cycle."""

    def setUp(self):
        self.factory = RequestFactory()
        self.store = Store.objects.create(
            name="Store A", slug="store-a", status=Store.Status.ACTIVE
        )
        _make_verified_domain(self.store, "a.example.com")

    def _run(self, request):
        seen = {}

        def get_response(req):
            seen["store"] = getattr(req, "store", "MISSING")
            return HttpResponse("ok")

        middleware = StoreResolutionMiddleware(get_response)
        response = middleware(request)
        return response, seen["store"]

    def test_matched_host_attaches_correct_store(self):
        request = self.factory.get("/", HTTP_HOST="a.example.com")
        response, seen_store = self._run(request)
        self.assertEqual(seen_store.pk, self.store.pk)
        self.assertEqual(request.store.pk, self.store.pk)

    def test_unknown_host_attaches_none(self):
        with self.settings(ALLOWED_HOSTS=["a.example.com", "unknown.example.com"]):
            request = self.factory.get("/", HTTP_HOST="unknown.example.com")
            response, seen_store = self._run(request)
        self.assertIsNone(seen_store)
        self.assertIsNone(request.store)

    def test_invalid_host_attaches_none_without_raising(self):
        # A Host header Django itself disallows (not in ALLOWED_HOSTS) must
        # not propagate an exception through the middleware.
        request = self.factory.get("/", HTTP_HOST="not-an-allowed-host.evil")
        response, seen_store = self._run(request)
        self.assertIsNone(seen_store)
        self.assertIsNone(request.store)
        self.assertEqual(response.status_code, 200)

    def test_middleware_performs_no_redirect(self):
        request = self.factory.get("/", HTTP_HOST="a.example.com")
        response, _ = self._run(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(response.status_code, (301, 302, 303, 307, 308))

    def test_one_store_resolution_occurs_per_request(self):
        request = self.factory.get("/", HTTP_HOST="a.example.com")
        with mock.patch(
            "apps.stores.middleware.resolve_store_for_request",
            wraps=resolve_store_for_request,
        ) as spy:
            self._run(request)
        self.assertEqual(spy.call_count, 1)

    def test_resolution_is_a_bounded_query_count(self):
        request = self.factory.get("/", HTTP_HOST="a.example.com")
        with self.assertNumQueries(1):
            self._run(request)


@override_settings(ALLOWED_HOSTS=["a.example.com", "b.example.com", "testserver"])
class StoreResolutionMiddlewareAuthenticationIsolationTests(TestCase):
    """Confirms the middleware does not touch request.user or session state,
    and that authentication continues to work end-to-end through the full
    middleware stack (StoreResolutionMiddleware runs before
    AuthenticationMiddleware — see shop_core/settings.py)."""

    def setUp(self):
        self.user = User.objects.create_user(username="staffuser", password="pass12345", is_staff=True)

    def test_authentication_state_is_unchanged_by_store_resolution(self):
        client = Client()
        client.login(username="staffuser", password="pass12345")
        response = client.get("/admin-portal/", HTTP_HOST="testserver")
        # The request still carries an authenticated user after passing
        # through StoreResolutionMiddleware (it runs first in the chain).
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.pk, self.user.pk)


class StoreResolutionEndToEndSmokeTests(TestCase):
    """Existing Akhlaghi storefront and dashboard requests must still
    render normally under approved development hosts, with the new
    middleware active in MIDDLEWARE."""

    def test_storefront_home_renders_under_testserver_host(self):
        client = Client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(hasattr(response.wsgi_request, "store"))

    def test_storefront_home_resolves_akhlaghi_via_compatibility_mode(self):
        client = Client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.wsgi_request.store)
        self.assertEqual(response.wsgi_request.store.slug, "akhlaghi")

    def test_dashboard_login_page_redirects_under_testserver_host(self):
        # Store resolution still runs; the legacy login URL then redirects to
        # the canonical central login instead of rendering a local form.
        client = Client()
        response = client.get("/admin-portal/login/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertTrue(hasattr(response.wsgi_request, "store"))

    def test_localhost_host_header_also_resolves_akhlaghi(self):
        with self.settings(ALLOWED_HOSTS=["localhost"]):
            client = Client()
            response = client.get("/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.store.slug, "akhlaghi")

    def test_disallowed_host_through_the_real_middleware_chain_does_not_500(self):
        # A Host header Django itself disallows, exercised through the real,
        # fully configured MIDDLEWARE chain (not a direct middleware call).
        # Django's own DisallowedHost handling (a SuspiciousOperation
        # subclass) converts this to a clean 400 response — it must not
        # surface as an unhandled exception/500, and StoreResolutionMiddleware
        # (which runs before whatever else might call get_host() again) must
        # not make this any worse.
        with self.settings(ALLOWED_HOSTS=["testserver"]):
            client = Client()
            response = client.get("/", HTTP_HOST="totally-disallowed-host.evil")
        self.assertEqual(response.status_code, 400)
