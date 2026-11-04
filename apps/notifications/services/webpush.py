"""Web Push (استانداردِ W3C/RFC 8030 + VAPID RFC 8292) — بدونِ وابستگیِ جدید (فقط ``cryptography`` و ``requests`` که از قبل در پروژه‌اند).

طراحیِ امن: **Push بدونِ Payload** — نه متنِ اعلان، نه نامِ مشتری، نه مبلغ از سرویسِ Pushِ مرورگر عبور نمی‌کند. Service Worker پس از دریافتِ Push، خودش با نشستِ همان
کاربر ``summary`` را می‌خواند و (فقط اگر هنوز مجاز بود) اعلانِ سیستمی را نشان می‌دهد؛ اگر نشست نبود، یک متنِ عمومیِ بی‌اطلاعات.

* کلیدِ خصوصیِ VAPID فقط از محیط (``RASTISI_VAPID_PRIVATE_KEY``) خوانده می‌شود؛ هیچ کلیدی در Repository نیست.
* نشانیِ Subscription و کلیدهایش با Fernet رمزنگاری و فقط هشِ آن برایِ یکتایی ذخیره می‌شود؛ هرگز در لاگ/خطا نمی‌آید.
* ارسالِ واقعی فقط وقتی ``RASTISI_NOTIF_WEBPUSH_ENABLED`` روشن و کلید تنظیم باشد؛ در تست‌ها ``transport`` تزریق می‌شود (هیچ اتصالِ واقعی)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from apps.notifications.models import WebPushSubscription

logger = logging.getLogger(__name__)

ALLOWED_PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com", "web.push.apple.com", "updates.push.services.mozilla.com",
)


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------------------------------------------------------------------------------------------------------- کلیدهای VAPID
def _load_private_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = (getattr(settings, "RASTISI_VAPID_PRIVATE_KEY", "") or "").strip()
    if not raw:
        return None
    try:
        if "BEGIN" in raw:
            return serialization.load_pem_private_key(raw.replace("\\n", "\n").encode(), password=None)
        return ec.derive_private_key(int.from_bytes(_b64u_decode(raw), "big"), ec.SECP256R1())
    except Exception:  # noqa: BLE001 — کلیدِ خراب = «تنظیم‌نشده»، هرگز افشا نمی‌شود
        logger.error("RASTISI_VAPID_PRIVATE_KEY is set but invalid")
        return None


def public_key_b64u() -> str:
    """کلیدِ عمومیِ نامشروط (applicationServerKey) برایِ مرورگر؛ رشته‌ی خالی اگر کلید تنظیم نیست."""
    from cryptography.hazmat.primitives import serialization

    key = _load_private_key()
    if key is None:
        return ""
    return _b64u(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def is_configured() -> bool:
    return bool(public_key_b64u()) and bool(getattr(settings, "RASTISI_VAPID_SUBJECT", ""))


def generate_keypair() -> dict:
    """فقط برایِ فرمانِ مدیریتیِ ``generate_vapid_keys`` (چاپ در خروجی؛ هرگز ذخیره نمی‌شود)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64u(key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64u(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return {"private": private, "public": public}


def vapid_headers(endpoint: str, *, now: float | None = None) -> dict:
    """سرایندِ Authorization (JWT ES256 با aud = origin سرویسِ Push). ``ValueError`` اگر کلید/Subject تنظیم نیست."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key = _load_private_key()
    subject = getattr(settings, "RASTISI_VAPID_SUBJECT", "")
    if key is None or not subject:
        raise ValueError("vapid_not_configured")
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": subject}
    signing_input = f"{_b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())}.{_b64u(json.dumps(claims, separators=(',', ':')).encode())}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    token = f"{signing_input}.{_b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return {"Authorization": f"vapid t={token}, k={public_key_b64u()}", "TTL": "3600", "Urgency": "normal", "Content-Length": "0"}


# ---------------------------------------------------------------------------------------------------------------- Subscription
class SubscriptionError(ValueError):
    pass


def validate_subscription(payload: dict) -> tuple[str, str, str]:
    """Endpoint باید HTTPS و از یکی از Push Serviceهای شناخته‌شده باشد (جلوگیری از SSRF: کارگر هرگز به نشانیِ دلخواه درخواست نمی‌زند)."""
    endpoint = str((payload or {}).get("endpoint") or "")
    keys = (payload or {}).get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or len(endpoint) > 1000:
        raise SubscriptionError("نشانیِ اشتراک معتبر نیست.")
    if not any(host == suf or host.endswith("." + suf) for suf in ALLOWED_PUSH_HOST_SUFFIXES):
        raise SubscriptionError("سرویسِ Pushِ این مرورگر پشتیبانی نمی‌شود.")
    if not (p256dh and auth) or len(p256dh) > 200 or len(auth) > 100:
        raise SubscriptionError("کلیدهای اشتراک ناقص است.")
    try:
        _b64u_decode(p256dh), _b64u_decode(auth)
    except Exception as exc:  # noqa: BLE001
        raise SubscriptionError("کلیدهای اشتراک معتبر نیست.") from exc
    return endpoint, p256dh, auth


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def register(user, scope_key: str, payload: dict, *, device_label: str = "", user_agent: str = "") -> WebPushSubscription:
    from apps.orders.encryption import encrypt_credential

    endpoint, p256dh, auth = validate_subscription(payload)
    blob = encrypt_credential(json.dumps({"endpoint": endpoint, "p256dh": p256dh, "auth": auth}))
    sub, _ = WebPushSubscription.objects.update_or_create(
        endpoint_hash=_endpoint_hash(endpoint),
        defaults={"user": user, "scope_key": scope_key, "secret_blob": blob, "device_label": device_label[:80], "user_agent": user_agent[:120],
                  "revoked_at": None, "failure_count": 0, "last_error": "", "last_seen_at": timezone.now()},
    )
    return sub


def unregister(user, endpoint: str = "", *, public_id: int | None = None) -> int:
    qs = WebPushSubscription.objects.filter(user=user, revoked_at__isnull=True)
    if endpoint:
        qs = qs.filter(endpoint_hash=_endpoint_hash(endpoint))
    elif public_id is not None:
        qs = qs.filter(pk=public_id)
    return qs.update(revoked_at=timezone.now())


def decrypt(sub: WebPushSubscription) -> dict:
    from apps.orders.encryption import decrypt_credential

    return json.loads(decrypt_credential(sub.secret_blob))


def revoke_all_for_user(user, scope_key: str | None = None) -> int:
    qs = WebPushSubscription.objects.filter(user=user, revoked_at__isnull=True)
    if scope_key:
        qs = qs.filter(scope_key=scope_key)
    return qs.update(revoked_at=timezone.now())


# ---------------------------------------------------------------------------------------------------------------- ارسال
@dataclass
class PushResult:
    status: int | None
    error: str = ""


def default_transport(endpoint: str, headers: dict) -> PushResult:
    """ارسالِ واقعی — فقط توسطِ کارگر و فقط وقتی پرچم روشن است (در تست‌ها همیشه جایگزین می‌شود)."""
    import requests

    try:
        response = requests.post(endpoint, headers=headers, data=b"", timeout=10, allow_redirects=False)
    except requests.RequestException as exc:
        return PushResult(None, type(exc).__name__)
    return PushResult(response.status_code)


def send(sub: WebPushSubscription, *, transport=None) -> PushResult:
    data = decrypt(sub)
    return (transport or default_transport)(data["endpoint"], vapid_headers(data["endpoint"]))
