# stores — Data Model

```
domain_id: D1
code_baseline: 5883a140
source: apps/stores/models.py (6 model classes incl. StoresTimestampedModel base)
```

| Model | Key fields / lifecycle | Constraints |
|---|---|---|
| **StoresTimestampedModel** (abstract) | created_at/updated_at | local base (NOT `core.TimeStampedModel` — M13) |
| **Store** | `status` (provisioning/active/suspended/closed); `onboarding_stage` (identity→industry→branding→review→done, soft); `onboarding_completed_at` (null ⇒ private); soft-delete (`deletion_requested_at/by`, `deletion_scheduled_purge_at`, `pre_deletion_status`); suspension (`suspended_at/by`, `suspension_reason`) | `slug` unique (global), `admin_subdomain` unique (ASCII DNS), `platform_code` unique (9-char, editable=False), `public_id` unique UUID. **No `owner` field.** |
| **StoreDomain** | `verification_status` (unverified/pending/verified/failed); `routing_status`; `tls_status`; `retired_at`; `is_primary`; `domain_type` (generated_trial/platform_subdomain/custom_domain, descriptive) | `hostname` unique (normalized); partial `uniq_primary_domain_per_store`, `uniq_verification_token_when_set`; 5 CheckConstraints tying status↔timestamps↔token; `retired_domain_is_never_primary`. `StoreDomainQuerySet` blocks `.update(hostname=)` |
| **StoreMembership** | `role` (owner/administrator/catalog_manager/order_manager/content_editor/analyst); `status` (invited/active/revoked) | `uniq_membership_per_store_user`; **`uniq_active_owner_per_store`**; accepted/revoked timestamp checks. `user` on_delete=PROTECT |
| **StoreOwnershipTransfer** | `status` (pending/completed/expired/cancelled); `expires_at`; `token` (auto secrets) | `uniq_pending_ownership_transfer_per_store` |
| **StoreIntegrationConnection** | `provider_code`, `is_active`, `encrypted_credentials` | `uniq_integration_per_store_provider`. Reuses `orders.encryption` |

## Key facts
- Store ownership = an active OWNER `StoreMembership` (ADR-2); there is no `Store.owner`.
- `onboarding_completed_at` is read for public-visibility decisions **only** via
  `publication_service` (ADR/comment-enforced convention).
- `admin_subdomain` is platform-assigned and independent of `StoreDomain` (ADR-16).
