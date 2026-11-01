"""IndexNow, automatically: tell participating search engines which public URLs of ONE store appeared, changed or were retired.

Built on the shared engine (``apps.core.automation``) — and, like the engine, WITHOUT a queue table: «what changed» is derived from the store's own rows and
a watermark kept in the engine's recorded results:

* appeared / changed — sitemap entries (the SAME list robots/sitemap use) whose ``lastmod`` is newer than the watermark; on the first run, or when the
  store's public host changed (new / switched domain), every URL;
* retired — products touched since the watermark that are no longer listable (unpublished / inactive / out of the storefront): their former URL is sent
  so the engine learns it is gone. A product HARD-deleted leaves no row, so ``apps.catalog.signals`` records a ``product.hard_deleted`` audit row (store + slug) when the
  delete commits, and its former URL is retired from there (no new table, no migration; a product that was never publicly listed records nothing).

Hard rules (all enforced here, none by the caller): the platform switch ``RASTISI_INDEXNOW_ENABLED`` (default OFF), the public-host guard, a VERIFIED
domain of THIS store (``indexnow.is_verified_host``), the key of THIS store, only URLs on that exact host (no private paths, no localhost), de-duplication,
bounded retries with back-off for transient answers only, and a truthful result: «accepted by the endpoint» (HTTP 200/202) is never reported as «indexed».
The transport is injected — tests use a fake; nothing opens a connection unless the platform enabled it and the command was run with ``--send``."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlsplit

from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.core import automation, indexnow, seo, seo_policy
from apps.core.automation import PermanentError, TransientError

OPERATION = "indexnow_sync"
TRANSIENT_HTTP = {None, 429}                      # 5xx is added below


def _verified_domain(store):
    from apps.stores.models import StoreDomain

    verified = StoreDomain.objects.filter(store=store, retired_at__isnull=True, verification_status=StoreDomain.VerificationStatus.VERIFIED)
    return verified.filter(is_primary=True).first() or verified.first()


def _request_for(store, host: str):
    """A synthetic request that says «this store, on this exact verified host» — the cron job has no real request. ``get_host`` is pinned so the answer
    does not depend on ALLOWED_HOSTS (the host comes from the store's own VERIFIED domain row, never from outside input)."""
    request = RequestFactory().get("/", HTTP_HOST=host or "invalid.invalid", secure=True)
    request.get_host = lambda: host
    request.store = store
    return request


def _watermark(store) -> tuple[datetime | None, str]:
    """(last successful watermark, host it was sent for) — read back from the engine's recorded result."""
    info = automation.last_result(store, OPERATION)
    metrics = ((info or {}).get("metadata") or {}).get("metrics") or {}
    if not info or not info["ok"] or not metrics.get("watermark"):
        return None, ""
    try:
        return datetime.fromisoformat(metrics["watermark"]), metrics.get("host", "")
    except ValueError:
        return None, ""


def _retired_product_urls(store, request, origin, since) -> list[str]:
    from apps.catalog.models import Product
    from apps.catalog.services.product_publish_service import storefront_listing_products
    from apps.catalog.signals import PRODUCT_HARD_DELETED
    from apps.core.models import AuditLogEntry

    if since is None:
        return []
    listed = set(storefront_listing_products(store).values_list("pk", flat=True))
    touched = list(Product.objects.filter(store=store, updated_at__gt=since).exclude(pk__in=listed).values_list("slug", flat=True)[:5000])
    # rows that no longer exist: slugs recorded when a publicly listed product was hard-deleted since the watermark (this store only)
    deleted = AuditLogEntry.objects.filter(store=store, action_code=PRODUCT_HARD_DELETED, created_at__gt=since).values_list("metadata", flat=True)[:5000]
    existing = set(Product.objects.filter(store=store, slug__in=[m.get("slug") for m in deleted if isinstance(m, dict) and m.get("slug")]).values_list("slug", flat=True))
    gone = [m["slug"] for m in deleted if isinstance(m, dict) and m.get("slug") and m["slug"] not in existing]       # a re-used slug is a live URL again: not «gone»
    return [seo._abs(request, reverse("catalog:product-detail", args=[slug]), origin=origin) for slug in dict.fromkeys(touched + gone)]


def plan(store, request, origin, *, since, previous_host, host) -> dict:
    """What would be sent — pure reading, no I/O to the outside."""
    entries = seo._sitemap_entries(request, store, origin=origin)
    everything = since is None or previous_host != host
    changed = [e["loc"] for e in entries if everything or (e["lastmod"] is not None and e["lastmod"] > since)]
    retired = [] if everything else _retired_product_urls(store, request, origin, since)
    private = tuple(seo_policy.PRIVATE_DISALLOW)
    urls = [u for u in dict.fromkeys(changed + retired) if urlsplit(u).scheme == "https" and not urlsplit(u).path.startswith(private)]
    return {"urls": urls, "changed": len(changed), "retired": len(retired), "everything": everything}


def sync(store, *, dry_run: bool = False, transport=None, sleep=None, now=None, actor=None) -> automation.Result:
    """One idempotent pass for ONE store. Safe to run from cron every few minutes: with nothing changed it sends nothing and records nothing."""
    domain = _verified_domain(store)
    host = domain.hostname if domain else ""
    now = now or timezone.now()
    if indexnow.indexnow_enabled() and domain is None:
        return automation.Result(automation.BLOCKED, "no_verified_domain", "IndexNow فقط برای دامنهٔ اختصاصیِ تأییدشده کار می‌کند.")

    def work(dry: bool) -> dict:
        request = _request_for(store, host)
        state = seo_policy.indexability(request, store)
        if not state.indexable:
            raise PermanentError(seo_policy.REASONS_FA[state.code])
        origin = seo_policy.canonical_origin(request, store)
        since, previous_host = _watermark(store)
        found = plan(store, request, origin, since=since, previous_host=previous_host, host=urlsplit(origin).netloc)
        metrics = {"urls": len(found["urls"]), "changed": found["changed"], "retired": found["retired"], "full_resubmit": found["everything"],
                   "host": urlsplit(origin).netloc, "watermark": now.astimezone(dt_timezone.utc).isoformat()}
        if dry or not found["urls"]:
            return metrics
        result = indexnow.submit(store, origin, found["urls"], indexable=True, transport=transport, attempts=1)
        if result.status == "sent":
            return {**metrics, "submitted": result.submitted, "http": result.http_status, "note": "request accepted; indexing is not guaranteed"}
        if result.status == "failed" and (result.http_status in TRANSIENT_HTTP or (result.http_status or 0) >= 500):
            raise TransientError(f"http={result.http_status}")
        raise PermanentError(f"{result.status} http={result.http_status}")

    kwargs = {"sleep": sleep} if sleep else {}
    return automation.run(OPERATION, store, work, enabled=indexnow.indexnow_enabled(), dry_run=dry_run, host=host,
                          require_public=True, key="", actor=actor, should_record=lambda m: m.get("urls", 0) > 0, **kwargs)
