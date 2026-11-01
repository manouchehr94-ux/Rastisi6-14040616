"""Google Search Console, as far as it can be automated: the seller grants access ONCE (OAuth) and RastiSi then submits the store's sitemap and reads its status.

What this layer does (all through an INJECTED transport — nothing here opens a connection by itself):

* ``authorization_url`` / ``complete_authorization`` — the OAuth code flow with a signed, expiring, STORE-BOUND ``state`` (a callback can only ever attach tokens to the store
  that started the flow, and only for the logged-in seller's own session);
* tokens live encrypted in ``StoreIntegrationConnection`` (provider ``google_search_console``, a service-only row: it has no seller-facing form, so tokens can never
  be typed in by hand); refresh happens once on a 401; a revoked / expired grant (``invalid_grant`` / 401 after refresh) turns the connection into «access lost» —
  nothing is retried against Google with a dead grant;
* ``resolve_property`` — picks the seller's OWN verified Search Console property that covers this store's canonical origin (a URL-prefix or ``sc-domain:`` property with
  owner / full-user permission); an unverified or foreign property is never used;
* ``sync_sitemap`` — a shared-engine operation: submits ``<origin>/sitemap.xml`` for that property and reads back its status (submitted / errors / warnings as reported by
  Google). Google accepting a sitemap is NOT indexing and is never reported as such.

What it deliberately does NOT do: use the Indexing API (it is not for product pages), create or verify properties for the seller (ownership proof stays with the account
owner), claim anything about index coverage or ranking, or run unless ``RASTISI_GSC_OAUTH_ENABLED`` AND an OAuth client are configured by the platform owner."""

from __future__ import annotations

from urllib.parse import quote, urlencode, urlsplit

from django.conf import settings
from django.core import signing
from django.utils import timezone

from apps.core import automation
from apps.core.automation import PermanentError, TransientError

PROVIDER_CODE = "google_search_console"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters"                 # needed to SUBMIT a sitemap (…readonly cannot)
STATE_SALT = "rastisi.gsc.state"
STATE_MAX_AGE = 15 * 60
OK_PERMISSIONS = {"siteOwner", "siteFullUser"}
OPERATION = "gsc_sitemap"

# plain-language reasons (the seller never reads an HTTP code)
MESSAGES = {
    "disabled": "اتصال خودکار هنوز در دسترس نیست.",
    "not_configured": "اتصال گوگل هنوز توسط مدیر پلتفرم آماده نشده است.",
    "not_connected": "حساب گوگل هنوز متصل نشده است.",
    "access_lost": "دسترسی داده‌شده به حساب گوگل منقضی یا لغو شده؛ دوباره اجازه دهید.",
    "no_property": "در حساب گوگل شما سایتی که این آدرس را پوشش بدهد پیدا نشد؛ ابتدا سایت را در Search Console اضافه و مالکیتش را تأیید کنید.",
    "not_owner": "مالکیت این سایت در Search Console هنوز تأیید نشده یا دسترسی شما کافی نیست.",
    "forbidden": "گوگل اجازهٔ این کار را نداد.",
    "rate_limited": "گوگل موقتاً درخواست‌ها را محدود کرد؛ بعداً دوباره بررسی می‌شود.",
    "google_error": "سرویس گوگل موقتاً پاسخ نداد.",
    "bad_request": "گوگل درخواست را نپذیرفت.",
}


class GscError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, MESSAGES["bad_request"])


def enabled() -> bool:
    return bool(getattr(settings, "RASTISI_GSC_OAUTH_ENABLED", False))


def configured() -> bool:
    return bool(getattr(settings, "RASTISI_GOOGLE_OAUTH_CLIENT_ID", "") and getattr(settings, "RASTISI_GOOGLE_OAUTH_CLIENT_SECRET", ""))


# ---- state of the connection (what the page shows) ---------------------------------------------------------------------------------
def _connection(store):
    from apps.stores.models import StoreIntegrationConnection

    return StoreIntegrationConnection.objects.filter(store=store, provider_code=PROVIDER_CODE).first()


def status(store) -> dict:
    """``{"state", "text"}`` — ``disabled`` is the default everywhere: the page then says «اتصال خودکار هنوز در دسترس نیست»."""
    if not enabled():
        return {"state": "disabled", "text": MESSAGES["disabled"]}
    if not configured():
        return {"state": "not_configured", "text": MESSAGES["not_configured"]}
    conn = _connection(store)
    creds = conn.get_credentials() if conn else {}
    if not conn or not creds.get("refresh_token"):
        return {"state": "not_connected", "text": MESSAGES["not_connected"]}
    if creds.get("access_lost") or not conn.is_active:
        return {"state": "access_lost", "text": MESSAGES["access_lost"]}
    last = automation.last_result(store, OPERATION)
    if last and not last["ok"]:
        detail = (last["metadata"] or {}).get("detail", "")                  # the engine keeps our reason code here
        return {"state": "error", "text": MESSAGES.get(detail, MESSAGES["google_error"])}
    return {"state": "connected", "text": "متصل است؛ نقشهٔ سایت از طریق حساب خودتان ثبت می‌شود."}


# ---- OAuth -----------------------------------------------------------------------------------------------------------------------
def authorization_url(store, redirect_uri: str) -> str:
    if not (enabled() and configured()):
        raise GscError("disabled" if not enabled() else "not_configured")
    state = signing.dumps({"store": str(store.public_id)}, salt=STATE_SALT)
    query = urlencode({"client_id": settings.RASTISI_GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
                       "access_type": "offline", "prompt": "consent", "state": state})
    return f"{AUTH_URL}?{query}"


def complete_authorization(store, *, code: str, state: str, redirect_uri: str, transport) -> dict:
    """Exchange the code. The signed state must name THIS store and be fresh; only then are tokens stored — for this store only."""
    if not (enabled() and configured()):
        raise GscError("disabled" if not enabled() else "not_configured")
    try:
        payload = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature as exc:
        raise GscError("forbidden") from exc
    if payload.get("store") != str(store.public_id):
        raise GscError("forbidden")
    status_code, body = transport("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                                  urlencode({"code": code, "client_id": settings.RASTISI_GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.RASTISI_GOOGLE_OAUTH_CLIENT_SECRET,
                                             "redirect_uri": redirect_uri, "grant_type": "authorization_code"}))
    if status_code != 200 or not body.get("refresh_token"):
        raise GscError("bad_request")
    _save(store, {"refresh_token": body["refresh_token"], "access_token": body.get("access_token", ""), "access_lost": False}, active=True)
    return status(store)


def disconnect(store) -> None:
    conn = _connection(store)
    if conn:
        conn.set_credentials({})
        conn.is_active = False
        conn.save(update_fields=["encrypted_credentials", "is_active", "updated_at"])


def _save(store, creds: dict, *, active: bool):
    from apps.stores.models import StoreIntegrationConnection

    conn, _ = StoreIntegrationConnection.objects.get_or_create(store=store, provider_code=PROVIDER_CODE)
    merged = {**conn.get_credentials(), **creds}
    conn.set_credentials(merged)
    conn.is_active = active
    conn.connected_at = conn.connected_at or timezone.now()
    conn.save(update_fields=["encrypted_credentials", "is_active", "connected_at", "updated_at"])
    return conn


# ---- API ------------------------------------------------------------------------------------------------------------------------------
def _refresh(store, transport) -> str:
    creds = _connection(store).get_credentials()
    code, body = transport("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                           urlencode({"refresh_token": creds["refresh_token"], "client_id": settings.RASTISI_GOOGLE_OAUTH_CLIENT_ID,
                                      "client_secret": settings.RASTISI_GOOGLE_OAUTH_CLIENT_SECRET, "grant_type": "refresh_token"}))
    if code == 200 and body.get("access_token"):
        _save(store, {"access_token": body["access_token"]}, active=True)
        return body["access_token"]
    if code in (400, 401) and body.get("error") == "invalid_grant":
        _save(store, {"access_lost": True, "access_token": ""}, active=False)
        raise GscError("access_lost")
    raise GscError("rate_limited" if code == 429 else "google_error")


def _call(store, transport, method: str, path: str, body=None):
    token = _connection(store).get_credentials().get("access_token") or _refresh(store, transport)
    for attempt in (1, 2):
        code, data = transport(method, f"{API}{path}", {"Authorization": f"Bearer {token}"}, body)
        if code == 401 and attempt == 1:
            token = _refresh(store, transport)
            continue
        break
    if code == 401:
        _save(store, {"access_lost": True, "access_token": ""}, active=False)
        raise GscError("access_lost")
    if code in (200, 204):
        return data or {}
    if code == 403:
        raise GscError("not_owner")
    if code == 404:
        raise GscError("no_property")
    if code == 429:
        raise GscError("rate_limited")
    if code >= 500:
        raise GscError("google_error")
    raise GscError("bad_request")


def resolve_property(sites: list[dict], origin: str) -> str | None:
    """The seller's OWN verified property covering ``origin``: an exact URL-prefix property, or an ``sc-domain:`` one for the host / its parent domain."""
    host = urlsplit(origin).netloc
    best = None
    for entry in sites or []:
        if entry.get("permissionLevel") not in OK_PERMISSIONS:
            continue
        url = entry.get("siteUrl", "")
        if url.rstrip("/") == origin.rstrip("/"):
            return url
        if url.startswith("sc-domain:") and (host == url[10:] or host.endswith("." + url[10:])):
            best = best or url
    return best


def sync_sitemap(store, origin: str, *, transport, dry_run: bool = False, sleep=None, host: str = "") -> automation.Result:
    """Submit the store's sitemap through the seller's own Search Console access and read its status. One idempotent pass (re-submitting a sitemap is harmless)."""
    def work(dry: bool) -> dict:
        if not configured():
            raise PermanentError("not_configured")
        conn = _connection(store)
        if conn is None or not conn.is_active or not conn.get_credentials().get("refresh_token"):
            raise PermanentError("not_connected")
        try:
            sites = _call(store, transport, "GET", "/sites").get("siteEntry", [])
            prop = resolve_property(sites, origin)
            if prop is None:
                unverified = any(s.get("permissionLevel") == "siteUnverifiedUser" and s.get("siteUrl", "").rstrip("/") == origin.rstrip("/") for s in sites)
                raise GscError("not_owner" if unverified else "no_property")
            feed = f"{origin}/sitemap.xml"
            metrics = {"property": prop, "sitemap": feed}
            if dry:
                return metrics
            _call(store, transport, "PUT", f"/sites/{quote(prop, safe='')}/sitemaps/{quote(feed, safe='')}")
            info = _call(store, transport, "GET", f"/sites/{quote(prop, safe='')}/sitemaps/{quote(feed, safe='')}")
        except GscError as exc:
            if exc.code in ("rate_limited", "google_error"):
                raise TransientError(exc.code) from exc
            raise PermanentError(exc.code) from exc
        return {**metrics, "errors": int(info.get("errors", 0) or 0), "warnings": int(info.get("warnings", 0) or 0), "pending": bool(info.get("isPending")),
                "note": "sitemap accepted by Search Console; indexing is not guaranteed"}

    kwargs = {"sleep": sleep} if sleep else {}
    return automation.run(OPERATION, store, work, enabled=enabled(), dry_run=dry_run, host=host or urlsplit(origin).netloc, **kwargs)
