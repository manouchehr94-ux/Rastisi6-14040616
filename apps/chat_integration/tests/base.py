"""Shared fixtures for the RastiChat adapter tests. The adapter talks to RastiChat only through
`apps.chat_integration.client`; tests patch that module's `request` (the single HTTP seam) and verify the signed tokens
with the matching public key — i.e. they check exactly what RastiChat would receive."""
import base64
import json
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
PASSWORD = "a-very-strong-pass-1"
PLATFORM_ADMIN_HOST = "platformadmins.rastisi.localhost"

_PRIVATE = Ed25519PrivateKey.generate()
PRIVATE_PEM = _PRIVATE.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUBLIC_KEY = _PRIVATE.public_key()

CHAT_SETTINGS = dict(
    RASTICHAT_INTEGRATION_ENABLED=True, RASTICHAT_BASE_URL="https://chat.example.test",
    RASTICHAT_WIDGET_URL="https://chat.example.test/widget.js", RASTICHAT_DASHBOARD_URL="https://chat.example.test/admin",
    RASTICHAT_PLATFORM_DASHBOARD_URL="https://chat.example.test/platform", RASTICHAT_KEY_ID="ick_testkey",
    RASTICHAT_PRIVATE_KEY=PRIVATE_PEM, RASTICHAT_INTEGRATION_SLUG="rastisi", RASTICHAT_TOKEN_AUDIENCE="rastichat",
    ALLOWED_HOSTS=["testserver", "localhost", PLATFORM_ADMIN_HOST, ".rastisi.localhost", "shop-a.example.com", "shop-b.example.com"],
)


def b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def verify_jwt(token: str, public_key: Ed25519PublicKey = PUBLIC_KEY):
    """Verify an EdDSA JWT with the host's PUBLIC key (what RastiChat does) and return (header, claims)."""
    header_b64, payload_b64, sig_b64 = token.split(".")
    public_key.verify(b64url_decode(sig_b64), f"{header_b64}.{payload_b64}".encode())   # raises InvalidSignature if forged
    return json.loads(b64url_decode(header_b64)), json.loads(b64url_decode(payload_b64))


def fragment_assertion(response) -> tuple[str, str, str]:
    """(base url, assertion, next) from a redirect whose assertion travels in the URL FRAGMENT."""
    location = response["Location"]
    assert "#assertion=" in location, location
    base, fragment = location.split("#", 1)
    assert "?" not in location.split("#")[0], "no query string"
    params = dict(p.split("=", 1) for p in fragment.split("&"))
    return base, params["assertion"], params["next"]


def make_store(slug, *, admin_sub=None, host=None, active=True):
    store = Store.objects.create(
        name=f"Store {slug}", slug=slug, status=Store.Status.ACTIVE if active else Store.Status.SUSPENDED,
        platform_code=generate_unique_platform_code(), admin_subdomain=admin_sub or slug,
    )
    if host:
        StoreDomain.objects.create(
            store=store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
    return store


def make_member(store, username, role):
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password=PASSWORD)
    StoreMembership.objects.create(store=store, user=user, role=role, status=StoreMembership.MembershipStatus.ACTIVE,
                                   accepted_at=timezone.now())
    return user


def make_customer(username, phone):
    user = User.objects.create_user(username=username, password=PASSWORD)
    return Customer.objects.create(user=user, full_name=f"مشتری {username}", phone=phone)


@override_settings(**CHAT_SETTINGS)
class ChatTestCase(TestCase):
    """Chat globally ON; RastiChat itself is faked at `client.request` (records calls, returns plausible answers)."""

    def setUp(self):
        self.calls = []
        patcher = mock.patch("apps.chat_integration.client.request", side_effect=self._fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fail_requests = False

    def _fake_request(self, method, path, body=None, **kw):
        from apps.chat_integration.client import RastiChatError
        self.calls.append({"method": method, "path": path, "body": body, **kw})
        if self.fail_requests:
            raise RastiChatError("down", status=503)
        if method == "PUT" and "/members/" not in path and "/platform/" not in path and path.endswith("/") and body and "display_name" in body:
            return {"project_public_key": "11111111-2222-3333-4444-555555555555", "workspace_id": 1, "created": True}
        if path.endswith("/support-conversations/"):
            return {"conversation_id": "conv-1", "created": True}
        return {}

    def enable(self, store, actor=None):
        from apps.chat_integration.services import enablement
        enablement.enable_for_store(store, actor=actor)
        self.calls.clear()
