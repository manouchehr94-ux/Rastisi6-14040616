"""The shared engine for everything RastiSi does for a store by itself (search-engine hints, account-status sync, channel checks …).

It is deliberately small and built ONLY on what the project already has — no queue table, no new scheduler, no migration:

* the scheduler is the existing cron + ``manage.py`` commands (``deploy/cron``, ``check_background_jobs``) — an operation is a plain function a
  command (or a request, or a test) calls;
* the persistent record is the existing ``AuditLogEntry`` (store-scoped, idempotent by ``request_id``, secrets redacted) — the last result of an
  operation is read back from it, so the Studio/settings page can show the REAL outcome;
* mutual exclusion is the Django cache lock (``cache.add``); if the cache is not shared between workers the lock only protects one process and the
  operations are written to be harmless when repeated (idempotent by construction: they derive «what changed» from stored watermarks).

Every operation therefore gets, by construction:

1. Store scoping — it only ever receives ONE store and only reads/writes that store's rows;
2. an explicit enable flag (platform switch) — disabled means «nothing happens, nothing is recorded as done»;
3. the public-host guard — never on localhost / test hosts / unknown hosts / unpublished or inactive stores (``seo_policy``);
4. dry run — returns what WOULD happen and touches nothing (no lock, no audit, no transport call);
5. mutual exclusion + de-duplication by key;
6. bounded retries with back-off for TRANSIENT failures only (a permanent failure is final and honestly reported);
7. a recorded, redacted, honest result (``done`` / ``failed`` / ``skipped`` / ``blocked`` / ``disabled``) — never a made-up success;
8. a transport that is injected (tests and QA use fakes; nothing here opens a network connection by itself).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from django.core.cache import cache

from apps.core import seo_policy
from apps.core.models import AuditLogEntry
from apps.core.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)

DONE, DRY_RUN, SKIPPED, BLOCKED, DISABLED, FAILED = "done", "dry_run", "skipped", "blocked", "disabled", "failed"
ACTION_PREFIX = "automation."
MAX_ATTEMPTS = 3


class TransientError(Exception):
    """The other side (or the network) may succeed on a retry — retried with back-off, at most ``attempts`` times."""


class PermanentError(Exception):
    """A refusal that retrying cannot fix (bad key, rejected URLs, revoked permission) — reported at once, never retried."""


@dataclass
class Result:
    status: str
    reason: str = ""
    detail: str = ""
    attempts: int = 0
    metrics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (DONE, DRY_RUN)

    def as_metadata(self) -> dict:
        return {"status": self.status, "reason": self.reason, "detail": self.detail, "attempts": self.attempts, "metrics": dict(self.metrics)}


def host_guard(store, host: str) -> str:
    """Why this store/host must NOT receive automatic outside actions (``""`` = allowed). One policy, the SEO one."""
    if store is None or getattr(store, "status", None) != store.Status.ACTIVE:
        return "store_inactive"
    from apps.stores.services.publication_service import is_publicly_visible

    if not host or seo_policy.is_non_public_host(host):
        return "test_host"
    if not is_publicly_visible(store):
        return "store_not_public"
    return ""


def _lock_key(operation: str, store, key: str) -> str:
    return f"rs:automation:{operation}:{store.pk}:{key}"


def run(operation: str, store, fn: Callable[[bool], dict | None], *, enabled: bool = True, dry_run: bool = False, host: str = "",
        require_public: bool = True, key: str = "", attempts: int = MAX_ATTEMPTS, backoff: float = 2.0, sleep: Callable[[float], None] = time.sleep,
        lock_ttl: int = 300, actor=None, record: bool = True) -> Result:
    """Run ``fn(dry_run)`` for ONE store under the guarantees listed in the module docstring. ``fn`` returns a metrics dict (or ``None``), raises
    ``TransientError`` to be retried, ``PermanentError`` to stop. ``key`` identifies one logical run (the same key is never executed twice)."""
    if not enabled:
        return Result(DISABLED, "platform_disabled", "این قابلیت توسط مدیر پلتفرم فعال نشده است.")
    if store is None:
        return Result(BLOCKED, "store_missing")
    if require_public:
        reason = host_guard(store, host)
        if reason:
            return Result(BLOCKED, reason, "فروشگاه یا آدرس برای این کار مجاز نیست.")
    if dry_run:
        try:
            metrics = fn(True) or {}
        except (TransientError, PermanentError) as exc:
            return Result(FAILED, exc.__class__.__name__, str(exc))
        return Result(DRY_RUN, "dry_run", "فقط بررسی شد؛ چیزی ارسال یا ذخیره نشد.", 0, metrics)

    request_id = f"{operation}:{key}"[:64] if key else ""
    if request_id and AuditLogEntry.objects.filter(store=store, action_code=ACTION_PREFIX + operation, request_id=request_id).exists():
        return Result(SKIPPED, "duplicate", "همین اجرا قبلاً انجام شده است.")
    lock = _lock_key(operation, store, key or "-")
    if not cache.add(lock, 1, lock_ttl):
        return Result(SKIPPED, "already_running", "اجرای دیگری در حال انجام است.")
    try:
        result = _attempt(fn, attempts, backoff, sleep)
    finally:
        cache.delete(lock)
    if record and result.status in (DONE, FAILED):
        record_audit_event(
            store=store, actor=actor, action_code=ACTION_PREFIX + operation, object_type="Automation", object_label=operation,
            metadata=result.as_metadata(), request_id=request_id,
            result=AuditLogEntry.ResultStatus.SUCCESS if result.status == DONE else AuditLogEntry.ResultStatus.FAILURE,
        )
    return result


def _attempt(fn, attempts: int, backoff: float, sleep) -> Result:
    last = ""
    for number in range(1, max(1, min(attempts, MAX_ATTEMPTS)) + 1):
        try:
            metrics = fn(False) or {}
        except TransientError as exc:
            last = str(exc) or exc.__class__.__name__
            logger.warning("automation transient failure (attempt %s): %s", number, exc.__class__.__name__)
            if number < attempts:
                sleep(backoff ** (number - 1))
            continue
        except PermanentError as exc:
            return Result(FAILED, "permanent", str(exc), number)
        except Exception as exc:                                                         # noqa: BLE001 - never raise into a request / cron loop
            logger.error("automation unexpected failure: %s", exc.__class__.__name__)       # class only: a message may carry a secret
            return Result(FAILED, "unexpected", exc.__class__.__name__, number)
        return Result(DONE, "", "", number, metrics)
    return Result(FAILED, "transient_exhausted", last, min(attempts, MAX_ATTEMPTS))


def last_result(store, operation: str) -> dict | None:
    """The most recent RECORDED outcome of ``operation`` for this store (``None`` if it never ran) — what the page shows as the real status."""
    entry = AuditLogEntry.objects.filter(store=store, action_code=ACTION_PREFIX + operation).order_by("-created_at", "-pk").first()
    if entry is None:
        return None
    return {"at": entry.created_at, "ok": entry.result == AuditLogEntry.ResultStatus.SUCCESS, "metadata": dict(entry.metadata or {})}
