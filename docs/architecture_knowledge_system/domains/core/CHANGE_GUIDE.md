# core — Change Guide

```
domain_id: D14
code_baseline: 5883a140
open_decisions: DR-3
```

## Recipe: Change ShopSettings
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md), [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md).
- **⚠️ M5/DR-3:** ShopSettings is owned by core but **written directly by `dashboard.views`**
  (settings pages) and `sms_service` (device token). A change likely means editing dashboard views,
  not a core service — read [`../dashboard/CHANGE_GUIDE.md`](../dashboard/CHANGE_GUIDE.md).
- **INVARIANTS:** `load(store=)` raises if unprovisioned; one row per Store; `provision_for` idempotent.
- **⚠️ D4:** legacy SMS credential fields are POTENTIALLY_DEAD (ignored except SMSRASTI). Don't wire
  new SMS behavior to them — real creds are on `portal.PlatformConfiguration`.
- **OPEN DECISION:** DR-3 (settings service discipline).

## Recipe: Change export / import
- **READ FIRST:** `export_service` (here) + `dashboard.import_service` (there — M14).
- **INVARIANTS:** synchronous run; private_storage outside MEDIA_ROOT; formula-injection-safe CSV;
  export budget enforced via subscriptions; import idempotency per store.

## Recipe: Change audit logging
- **READ FIRST:** `audit_service.record_audit_event`.
- **INVARIANTS:** redact sensitive keys; omit IP/UA (ADR-36); idempotent by request_id; called from
  services, not views.

## Recipe: Change SEO (sitemap/robots)
- **READ FIRST:** `seo.py`. **INVARIANT:** tenant-safe (host-resolved store; published content only).

## Recipe: Change the shared TimeStampedModel
- **⚠️ M13:** `stores` deliberately does NOT use it (has its own base). A change here does not affect
  `stores`. Do not "fix" stores to import core's base — that would create a future cycle.
