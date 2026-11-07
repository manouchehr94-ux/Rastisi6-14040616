"""LOCAL-QA fake of the Zibal *platform* gateway — so the official subscription checkout can be exercised end to end without a real bank.

It plugs in BELOW the official flow: ``ZibalBillingProvider`` asks ``handle()`` instead of ``requests.post`` and sends the browser to the local
start page. Invoice → checkout → attempt → public callback → server-side verify → ``confirm_payment`` → activation are all the normal code paths
(amount checks, idempotency, row locks, tenant scoping). Nothing here can mark an invoice paid: it only answers the provider's ``verify`` call,
exactly like the bank would.

Active ONLY when ALL hold: ``RASTISI_QA_PAYMENT_SIMULATOR`` (explicit opt-in; startup fails if set with DEBUG off), ``DEBUG`` is on, not production mode, and
the database is an isolated QA one (its name contains «qa», or ``RASTISI_QA_SIMULATOR_DB_CONFIRM`` equals the exact name). In every other
situation ``is_active()`` is False, the provider uses the real gateway code unchanged and the local views answer 404."""

from urllib.parse import urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

_TTL = 6 * 3600
RESULT_OK, RESULT_ALREADY, RESULT_NOT_PAID, RESULT_BAD = 100, 201, 202, 102


def is_active() -> bool:
    if not getattr(settings, "RASTISI_QA_PAYMENT_SIMULATOR", False):
        return False
    if not getattr(settings, "DEBUG", False) or getattr(settings, "RASTISI_PRODUCTION_MODE", True):
        return False
    name = str(connection.settings_dict.get("NAME", ""))
    confirm = getattr(settings, "RASTISI_QA_SIMULATOR_DB_CONFIRM", "") or ""
    return "qa" in name.lower() or (bool(confirm) and confirm == name)


def _key(track_id) -> str:
    return f"qa-sim:zibal:{track_id}"


def handle(path: str, payload: dict) -> dict:
    """Answer the two Zibal v1 calls the provider makes (``request`` / ``verify``) from local state. No HTTP."""
    if not is_active():                                    # defence in depth: never answer unless the full guard holds
        raise RuntimeError("QA payment simulator is not active")
    if path == "request":
        cache.add("qa-sim:zibal:counter", 70000, None)
        track_id = cache.incr("qa-sim:zibal:counter")
        cache.set(_key(track_id), {"amount": int(payload["amount"]), "orderId": str(payload["orderId"]), "callbackUrl": str(payload["callbackUrl"]),
                                   "status": "created", "verified": False}, _TTL)
        return {"result": RESULT_OK, "trackId": track_id, "message": "success (QA simulator)"}
    if path == "verify":
        state = cache.get(_key(payload.get("trackId")))
        if state is None:
            return {"result": RESULT_BAD, "message": "unknown trackId (QA simulator)"}
        if state["status"] != "paid":
            return {"result": RESULT_NOT_PAID, "message": "not paid (QA simulator)"}
        already = state["verified"]
        state["verified"] = True
        cache.set(_key(payload["trackId"]), state, _TTL)
        return {"result": RESULT_ALREADY if already else RESULT_OK, "amount": state["amount"], "status": 1,
                "refNumber": str(900000 + int(payload["trackId"])), "orderId": state["orderId"], "message": "success (QA simulator)"}
    raise ValueError(f"unsupported simulator call {path!r}")


def start_url(return_url: str, track_id) -> str:
    """The local «bank page» — same origin as the callback URL (always a host this app serves)."""
    parts = urlsplit(return_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/billing/qa-simulator/start/{track_id}/", "", ""))


# --------------------------------------------------------------------------------------------------------------------------------- views

_OUTCOMES = {
    "success": ("پرداخت موفق", {"success": "1", "status": "2"}),
    "failed": ("پرداخت ناموفق", {"success": "0", "status": "3"}),
    "cancel": ("انصراف کاربر", {"success": "0", "status": "4"}),
}


def _state_or_404(track_id):
    if not is_active():
        raise Http404
    state = cache.get(_key(track_id))
    if state is None:
        raise Http404
    return state


def _callback(track_id, state, outcome) -> str:
    query = dict(_OUTCOMES[outcome][1], trackId=str(track_id))
    base = state["callbackUrl"]
    return f"{base}{'&' if '?' in base else '?'}{urlencode(query)}"


@require_http_methods(["GET", "POST"])
def start_page(request, track_id):
    state = _state_or_404(track_id)
    if request.method == "POST":
        outcome = request.POST.get("outcome", "")
        if outcome not in _OUTCOMES:
            raise Http404
        if outcome == "success":
            state["status"] = "paid"
        elif state["status"] != "paid":
            state["status"] = outcome
        cache.set(_key(track_id), state, _TTL)
        return HttpResponseRedirect(_callback(track_id, state, outcome))
    from django.middleware.csrf import get_token

    amount_toman = state["amount"] // 10
    buttons = "".join(f'<button type="submit" name="outcome" value="{k}" data-testid="sim-{k}">{escape(label)}</button> ' for k, (label, _q) in _OUTCOMES.items())
    replay = ""
    if state["status"] in ("paid", "failed", "cancel"):
        replay = (f'<p><a data-testid="sim-replay" href="{escape(_callback(track_id, state, "success" if state["status"] == "paid" else state["status"]))}">'
                  "تکرار بازگشت به سایت (Callback)</a></p>")
    html = f"""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>درگاه آزمایشی QA</title>
<body style="font-family:sans-serif;max-width:520px;margin:40px auto;padding:0 16px">
<div style="background:#fff4d6;border:1px solid #e0b84a;padding:10px 14px;border-radius:8px"><b>درگاه شبیه‌سازی‌شده — فقط QA محلی.</b> هیچ پولی جابه‌جا نمی‌شود و هیچ درخواستی به بانک ارسال نمی‌شود.</div>
<h2>پرداخت آزمایشی</h2>
<p>مبلغ: <b data-testid="sim-amount">{amount_toman:,}</b> تومان ({state["amount"]:,} ریال) — پیگیری {escape(str(track_id))}</p>
<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">{buttons}</form>{replay}</body></html>"""
    return HttpResponse(html)
