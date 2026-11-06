"""Shared synthetic fixtures for the platform-payment test modules. NO real provider, NO real credentials, NO network:
every gateway HTTP call is answered by an in-process fake. Merchant ids below are fake strings."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.portal.services import platform_gateway_service as pgs
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

PLATFORM_MERCHANT = "PLATFORM-FAKE-MERCHANT-0001"
STORE_MERCHANT = "STORE-FAKE-MERCHANT-9999"
ZARINPAL_PLATFORM = "a" * 36
ZARINPAL_STORE = "b" * 36


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code = payload, status_code

    def json(self):
        return self._payload


class FakeZibal:
    """In-process stand-in for gateway.zibal.ir/v1/{request,verify}. Records every call (never the secrets in logs)."""

    def __init__(self):
        self.track_id = 777
        self.verify_payload = {"result": 202, "message": "not paid"}
        self.calls = []

    def paid(self, *, amount_rial, order_id="", result=100):
        self.verify_payload = {"result": result, "amount": amount_rial, "status": 1, "refNumber": "123456", "orderId": order_id}

    def __call__(self, url, json=None, timeout=None, **kwargs):
        path = url.rsplit("/", 1)[-1]
        self.calls.append((path, dict(json or {})))
        if path == "request":
            return _Resp({"result": 100, "trackId": self.track_id, "message": "success"})
        if path == "verify":
            return _Resp(dict(self.verify_payload))
        raise AssertionError(f"unexpected zibal call {url}")

    def calls_to(self, path):
        return [payload for (p, payload) in self.calls if p == path]


class FakeZarinpal:
    AUTHORITY = "A" + "0" * 34 + "1"

    def __init__(self):
        self.verify_payload = {"data": {"code": 101}, "errors": []}
        self.calls = []

    def __call__(self, url, json=None, timeout=None, **kwargs):
        self.calls.append((url, dict(json or {})))
        if "request" in url:
            return _Resp({"data": {"code": 100, "authority": self.AUTHORITY, "message": "Success"}, "errors": []})
        if "verify" in url:
            return _Resp(dict(self.verify_payload))
        raise AssertionError(f"unexpected zarinpal call {url}")

    def paid(self):
        self.verify_payload = {"data": {"code": 100, "ref_id": 99, "card_pan": "603799******0019"}, "errors": []}


def patch_zibal(case):
    fake = FakeZibal()
    patcher = patch("apps.billing.providers.zibal.requests.post", fake)
    patcher.start()
    case.addCleanup(patcher.stop)
    return fake


def patch_zarinpal(case):
    fake = FakeZarinpal()
    patcher = patch("apps.orders.gateways.zarinpal.requests.post", fake)
    patcher.start()
    case.addCleanup(patcher.stop)
    return fake


def ready_platform_zibal(case, *, merchant=PLATFORM_MERCHANT, default=True):
    case.addCleanup(cache.clear)
    cache.clear()
    pgs.save_gateway("zibal", credentials={"merchant": merchant}, sandbox=False, enabled=True)
    if default:
        pgs.set_default("zibal")
    cache.clear()


def ready_platform_zarinpal(case, *, merchant_id=ZARINPAL_PLATFORM, default=False):
    case.addCleanup(cache.clear)
    cache.clear()
    pgs.save_gateway("zarinpal", credentials={"merchant_id": merchant_id}, sandbox=False, enabled=True)
    if default:
        pgs.set_default("zarinpal")
    cache.clear()


def open_invoice_for(store, *, code, price="490000"):
    plan = Plan.objects.create(code=f"pl-{code}", name="Plan " + code)
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)],
    )
    return sub, invoice_service.open_invoice(invoice)


class FakePasargad:
    """In-process stand-in for the Dorsa IPG REST API (https://pep.shaparak.ir/dorsa1/…). Mirrors the documented
    contract: getToken(Bearer) · purchase → data.urlId/url · payment-inquiry → data.status/amount · verify-transactions ·
    reverse-transactions. Synthetic ids only."""

    URL_ID = "URLID-SYNTHETIC-0001"

    def __init__(self):
        self.calls = []
        self.inquiry = {"status": 2}                       # 2 = unknown/not paid (documented code)
        self.purchase_result = {"resultCode": 0, "data": {"urlId": self.URL_ID, "url": f"https://pep.shaparak.ir/dorsa1/{self.URL_ID}"}}
        self.verify_result = {"resultCode": 0, "data": {"referenceNumber": "REF-1", "maskedCardNumber": "603799******0019"}}
        self.reverse_result = {"resultCode": 0}
        self.token_result = {"resultCode": 0, "token": "TOKEN-SYNTHETIC"}

    def paid(self, *, amount_rial, status=13029):
        self.inquiry = {"status": status, "amount": amount_rial, "referenceNumber": "REF-1", "cardNumber": "603799******0019"}

    def __call__(self, url, json=None, headers=None, timeout=None, **kwargs):
        name = url.rstrip("/").rsplit("/", 1)[-1]
        self.calls.append((name, dict(json or {}), dict(headers or {})))
        if name == "getToken":
            return _Resp(dict(self.token_result))
        if name == "purchase":
            return _Resp(dict(self.purchase_result))
        if name == "payment-inquiry":
            return _Resp({"resultCode": 0, "data": dict(self.inquiry)})
        if name == "verify-transactions":
            return _Resp(dict(self.verify_result))
        if name == "reverse-transactions":
            return _Resp(dict(self.reverse_result))
        raise AssertionError(f"unexpected dorsa call {url}")

    def calls_to(self, name):
        return [payload for (n, payload, _h) in self.calls if n == name]


PASARGAD_CREDS = {"username": "synthetic-user", "password": "synthetic-pass-NEVER-SHOWN", "terminalNumber": "000111", "serviceCode": "8"}


def patch_pasargad(case):
    fake = FakePasargad()
    patcher = patch("apps.orders.gateways.pasargad.requests.post", fake)
    patcher.start()
    case.addCleanup(patcher.stop)
    return fake


def ready_platform_pasargad(case, *, creds=None, default=False):
    case.addCleanup(cache.clear)
    cache.clear()
    pgs.save_gateway("pasargad", credentials=dict(creds or PASARGAD_CREDS), sandbox=False, enabled=True)
    if default:
        pgs.set_default("pasargad")
    cache.clear()


# ---------------------------------------------------------------------------------------------------------------------
# Unified-checkout helpers: the merchant journey is now  portal/dashboard "buy" → invoice/pending purchase → unified checkout
# page → POST pay (method) → provider redirect.  Older tests that only cared about what happens AFTER the redirect use these
# to walk the real path instead of the removed direct-to-gateway shortcut.
# ---------------------------------------------------------------------------------------------------------------------

def admin_client_for(store, user):
    """A logged-in test client on the store's real admin host (the unified checkout lives there)."""
    from django.conf import settings
    from django.test import Client

    host = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    client = Client(HTTP_HOST=host)
    client.force_login(user)
    return client, host


def pay_on_checkout(case, store, user, kind, pk, *, method="", extra=None):
    """POST the unified checkout pay endpoint as the store owner; returns the response (a provider redirect on success)."""
    from django.conf import settings
    from django.test import override_settings
    from django.urls import reverse

    from apps.stores.models import Store

    Store.objects.filter(pk=store.pk).update(status=Store.Status.ACTIVE)          # real stores are provisioned ACTIVE; admin hosts resolve only those
    client, host = admin_client_for(store, user)
    with override_settings(ALLOWED_HOSTS=list(settings.ALLOWED_HOSTS) + [host]):
        data = {"method": method} if method else {}
        data.update(extra or {})
        return client.post(reverse("dashboard:platform-checkout-pay", args=[kind, pk]), data)


def portal_buy_and_pay(case, client, store, user, version, *, method=None, host="rastisi.localhost", **extra):
    """Portal 'buy' (creates the invoice + hands off to the checkout) then pay on the unified checkout with ``method``."""
    from apps.billing.models import SubscriptionInvoice as Invoice

    method = extra.pop("gateway", None) or method
    response = client.post(f"/app/stores/{store.public_id}/billing/checkout/{version.pk}/", dict(extra), HTTP_HOST=host)
    invoice = Invoice.objects.filter(store=store).order_by("-pk").first()
    if invoice is None or response.status_code != 302 or "/handoff/" not in response["Location"]:
        return response
    method = method or pgs.default_code("subscription")
    return pay_on_checkout(case, store, user, "subscription", invoice.pk, method=method)
