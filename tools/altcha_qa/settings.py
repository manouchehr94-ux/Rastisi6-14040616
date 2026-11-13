"""Explicit local preview: new SQLite file, local Redis, no real SMS/email.

Launch only using tools/altcha_qa/Start-Preview.ps1 (Windows) or the documented
Linux equivalent. Refuse inherited database/secret settings before importing
normal settings. The application security path remains the real ALTCHA path.
"""

import os
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured

if os.environ.get("DJANGO_DEBUG", "").lower() != "true":
    raise ImproperlyConfigured(
        "ALTCHA preview requires explicit DJANGO_DEBUG=true; never use in production."
    )
if os.environ.get("DATABASE_URL") or os.environ.get("DJANGO_SECRET_KEY"):
    raise ImproperlyConfigured(
        "Use a fresh local shell without DATABASE_URL or DJANGO_SECRET_KEY for the isolated preview."
    )
_redis = urlparse(os.environ.get("RASTISI_RATE_LIMIT_CACHE_URL", ""))
if (
    _redis.scheme != "redis"
    or _redis.hostname not in ("127.0.0.1", "localhost")
    or _redis.path != "/14"
):
    raise ImproperlyConfigured("Preview needs a dedicated loopback Redis database /14.")

from shop_core.settings import *  # noqa: E402,F403

_QA_ROOT = BASE_DIR / ".altcha-qa"  # noqa: F405
_QA_ROOT.mkdir(exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_QA_ROOT / "preview.sqlite3"),
    }
}
MEDIA_ROOT = str(_QA_ROOT / "media")
ALLOWED_HOSTS = ["127.0.0.1", "localhost", ".rastisi.localhost", "testserver"]
RASTISI_CAPTCHA_ENABLED = True
RASTISI_OWNER_SMS_BACKEND = "console"
RASTISI_OWNER_SMS_USERNAME = RASTISI_OWNER_SMS_PASSWORD = RASTISI_OWNER_SMS_API_KEY = ""
RASTISI_OWNER_SMS_SENDER = RASTISI_OWNER_SMS_OTP_BODY_ID = ""
RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP = True
RASTISI_DEV_OTP_CODE = (
    "123456"  # Public development-only test code, never a real credential.
)
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
RASTISI_EMAIL_PROVIDER = "fake"
RASTISI_NOTIF_EMAIL_ENABLED = False
RASTISI_EMAIL_DNS_ADVISORY_LOOKUP = False
