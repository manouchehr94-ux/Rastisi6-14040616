"""Configuration of the RastiChat integration (adapter) — everything is read from Django settings (environment).

RastiChat is a standalone, reusable chat service; RastiSi is just a host application that talks to it through the
generic Integration Contract v1 (see the RastiChat repository: docs/integrations/INTEGRATION_CONTRACT_V1.md and
docs/integrations/RASTISI.md). Nothing in here is RastiSi business logic; it only maps RastiSi concepts (Store,
StoreMembership, Customer, platform superuser) onto the contract's generic ones.

Safety: the whole integration is OFF unless ``RASTICHAT_INTEGRATION_ENABLED`` is true, and even then a store only gets
chat when the platform explicitly enables it for that store (``services.enablement``).
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

REQUIRED_WHEN_ENABLED = (
    "RASTICHAT_BASE_URL", "RASTICHAT_KEY_ID", "RASTICHAT_WIDGET_URL", "RASTICHAT_DASHBOARD_URL",
)


def globally_enabled() -> bool:
    return bool(getattr(settings, "RASTICHAT_INTEGRATION_ENABLED", False))


def private_key_pem() -> str:
    """The Ed25519 private key (PEM) of THIS host. Only ever read from the environment / a root-readable file —
    never from the database, never logged, never sent anywhere."""
    pem = getattr(settings, "RASTICHAT_PRIVATE_KEY", "") or ""
    if not pem and getattr(settings, "RASTICHAT_PRIVATE_KEY_FILE", ""):
        with open(settings.RASTICHAT_PRIVATE_KEY_FILE, encoding="utf-8") as fh:
            pem = fh.read()
    return pem.replace("\\n", "\n").strip() + "\n" if pem.strip() else ""


def validate_settings():
    """Fail fast at startup when the integration is switched on but not fully configured (a half-configured chat must
    not be discovered by a customer)."""
    if not globally_enabled():
        return
    missing = [name for name in REQUIRED_WHEN_ENABLED if not getattr(settings, name, "")]
    if not (getattr(settings, "RASTICHAT_PRIVATE_KEY", "") or getattr(settings, "RASTICHAT_PRIVATE_KEY_FILE", "")):
        missing.append("RASTICHAT_PRIVATE_KEY or RASTICHAT_PRIVATE_KEY_FILE")
    if missing:
        raise ImproperlyConfigured(
            "RASTICHAT_INTEGRATION_ENABLED=True requires: " + ", ".join(missing)
            + ". (See docs/integrations/RASTICHAT.md.)"
        )


def api_base() -> str:
    return settings.RASTICHAT_BASE_URL.rstrip("/") + "/api/v1"


def ws_base() -> str:
    explicit = getattr(settings, "RASTICHAT_WS_BASE", "")
    if explicit:
        return explicit.rstrip("/")
    return settings.RASTICHAT_BASE_URL.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"
