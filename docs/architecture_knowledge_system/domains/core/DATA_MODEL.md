# core — Data Model

```
domain_id: D14
code_baseline: 5883a140
source: apps/core/models.py (6 models incl. abstract base)
```

| Model | Scope / lifecycle | Notes |
|---|---|---|
| **TimeStampedModel** (abstract) | created_at/updated_at | Shared base across apps. **NOT reused by `stores`** (M13 cycle-avoidance) |
| **ShopSettings** | **store-scoped** (OneToOne Store) | Single per-Store identity/tax/branding source. `load(store=)` **raises `ShopSettingsNotProvisionedError`** if unprovisioned (no read-time create); `provision_for(store)` idempotent. Holds `TaxRoundingPolicy`, tax config, gift-wrap, branding colors, and **legacy SMS fields (`sms_backend`/`melipayamak_*`/`kavenegar_api_key`) that are POTENTIALLY_DEAD** (D4) |
| **AuditLogEntry** | store-scoped, immutable (created_at only) | Redacts sensitive keys at write time; omits IP/UA (ADR-36); idempotent by request_id |
| **ExportJob** | store-scoped; `status`; `type` (products/variants/inventory/customers/orders) | Synchronous run; UUID upload path; private_storage |
| **ImportJob** (+**ImportRowResult**) | store-scoped; `status`; `mode` (dry-run/execute) | `uniq_importjob_idempotency_key_per_store` |

## Platform-global vs store-scoped clarification
In core, ONLY `TimeStampedModel` is truly shared/abstract. `ShopSettings`, `AuditLogEntry`,
`ExportJob`, `ImportJob` are all **store-scoped**. There is **no** platform-global config in core —
that lives in `portal.PlatformConfiguration`.

## ExportJob / ImportJob status
```
pending → running → {completed, failed}   (synchronous; no task queue)
```
