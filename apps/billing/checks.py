"""System checks for the billing configuration (F-12). Warnings only: an empty secret already fails closed (the signed webhook
channel rejects every delivery), so this only catches a secret that is present but weak."""

from django.conf import settings
from django.core.checks import Tags, Warning, register

MIN_SECRET_LENGTH = 32
_PLACEHOLDERS = {"changeme", "change-me", "secret", "password", "test", "example", "your-secret-here", "billing-secret"}


def weak_secret_reason(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) < MIN_SECRET_LENGTH:
        return f"shorter than {MIN_SECRET_LENGTH} characters"
    if secret.lower() in _PLACEHOLDERS or len(set(secret)) < 8:
        return "looks like a placeholder or has too little variety"
    return ""


@register(Tags.security)
def check_billing_webhook_secret(app_configs, **kwargs):
    if not getattr(settings, "RASTISI_PRODUCTION_MODE", False):
        return []
    reason = weak_secret_reason(getattr(settings, "RASTISI_BILLING_WEBHOOK_SECRET", "") or "")
    if not reason:
        return []
    return [Warning(
        f"RASTISI_BILLING_WEBHOOK_SECRET is weak ({reason}).",
        hint="Use at least 32 random characters, for example secrets.token_urlsafe(48).",
        id="rastisi.W020",
    )]
