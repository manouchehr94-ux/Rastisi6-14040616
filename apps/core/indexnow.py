"""IndexNow (Bing, Yandex, Seznam, Naver…) — tell participating search engines that URLs of a Store changed.

What this is NOT: a promise of indexing or ranking. IndexNow is only a hint that a URL changed; the engine decides whether and when to
crawl it. Google does not use IndexNow.

Design (no migration, no new tables):
* the key is derived, not stored: ``HMAC(SECRET_KEY, "indexnow:<store public id>")`` — stable per store, never shared across stores,
  nothing secret to display (IndexNow keys are public by protocol: they are served as a text file on the site itself);
* the key file is served only by the Store's own public host (``/<key>.txt``), and only when the SEO policy says the host is public;
* a submission contains only URLs of the Store's own canonical host, at most 10 000, public pages only (sitemap entries);
* nothing is sent unless the platform enables it (``RASTISI_INDEXNOW_ENABLED``) AND the store is publicly indexable; the transport is
  injectable so tests and QA never touch the network;
* failures are returned/logged, never raised into the publish flow (publishing must not depend on a search engine);
* retries are bounded with backoff; a persisted queue needs a table and is a proposed migration (see the delivery report)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

from django.conf import settings

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10_000
KEY_LEN = 32


def indexnow_enabled() -> bool:
    return bool(getattr(settings, "RASTISI_INDEXNOW_ENABLED", False))


def key_for_store(store) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), f"indexnow:{store.public_id}".encode(), hashlib.sha256).hexdigest()
    return digest[:KEY_LEN]


def key_matches(store, candidate: str) -> bool:
    return bool(candidate) and hmac.compare_digest(key_for_store(store), candidate)


@dataclass(frozen=True)
class IndexNowResult:
    sent: bool
    status: str            # disabled | not_public | nothing_to_send | sent | failed
    submitted: int = 0
    http_status: int | None = None
    detail: str = ""


def build_payload(store, origin: str, urls: Iterable[str]) -> dict:
    """Payload for ``origin`` (the Store's canonical origin): only URLs on that exact host, de-duplicated, capped."""
    parts = urlsplit(origin)
    host = parts.netloc
    seen: list[str] = []
    for url in urls:
        u = urlsplit(url)
        if u.scheme in ("http", "https") and u.netloc == host and url not in seen:
            seen.append(url)
        if len(seen) >= MAX_URLS:
            break
    key = key_for_store(store)
    return {"host": host, "key": key, "keyLocation": f"{origin}/{key}.txt", "urlList": seen}


def _post(payload: dict, *, timeout: float = 10.0) -> int:
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:      # noqa: S310 - fixed https endpoint
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def submit(store, origin: str, urls: Iterable[str], *, indexable: bool,
           transport: Callable[[dict], int] | None = None, attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> IndexNowResult:
    """Send changed URLs. ``indexable`` is the SEO policy's verdict for this store/host (the caller computes it once).
    200/202 = accepted. 429/5xx are retried with backoff; other codes (e.g. 403 key not found, 422 bad URLs) are final."""
    if not indexnow_enabled():
        return IndexNowResult(False, "disabled", detail="IndexNow is not enabled on this platform.")
    if not indexable:
        return IndexNowResult(False, "not_public", detail="The store is not publicly indexable yet.")
    payload = build_payload(store, origin, urls)
    if not payload["urlList"]:
        return IndexNowResult(False, "nothing_to_send")
    send = transport or _post
    last = None
    for attempt in range(max(1, attempts)):
        try:
            last = int(send(payload))
        except Exception as exc:                                            # noqa: BLE001 - never raise into the caller
            logger.warning("IndexNow transport error for store %s: %s", store.pk, exc.__class__.__name__)
            last = None
        if last in (200, 202):
            return IndexNowResult(True, "sent", submitted=len(payload["urlList"]), http_status=last)
        if last is not None and last not in (429,) and last < 500:
            break
        if attempt + 1 < attempts:
            sleep(2 ** attempt)
    return IndexNowResult(False, "failed", http_status=last, detail="The search engine did not accept the submission.")
