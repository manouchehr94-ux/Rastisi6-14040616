"""FOLLOWUP-05 — تأییدِ سمت‌سرورِ عملیاتِ حساسِ اعضای تیم.

یک POST دستکاری‌شده نباید مرحلهٔ بازبینی/تأیید را دور بزند: هر عملیات (افزودن، لغو، تغییر نقش، فعال‌سازی مجدد، انتقال مالکیت)
فقط با یک «توکنِ تأیید» امضاشده اجرا می‌شود که فقط صفحهٔ بازبینی/تأییدِ همان عملیات صادر می‌کند. توکن به فروشگاه، کاربرِ
انجام‌دهنده، نوع عملیات، هدف و مقادیرِ دقیق (مثلاً نقشِ جدید) گره خورده و عمرش کوتاه است؛ با تغییرِ هر مقدار نامعتبر می‌شود."""

from __future__ import annotations

from django.core import signing

SALT = "rastisi.dashboard.staff-confirm.v1"
MAX_AGE_SECONDS = 15 * 60


def _payload(request, op: str, target, values: dict) -> dict:
    return {
        "op": op, "s": request.store.pk, "u": request.user.pk,
        "t": target, "v": {k: str(values[k]) for k in sorted(values)},
    }


def make_token(request, op: str, target=None, **values) -> str:
    return signing.dumps(_payload(request, op, target, values), salt=SALT, compress=True)


def check_token(request, token: str, op: str, target=None, **values) -> bool:
    if not token:
        return False
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:  # SignatureExpired is a subclass
        return False
    return data == _payload(request, op, target, values)
