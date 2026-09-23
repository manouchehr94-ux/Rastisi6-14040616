# stores — Services

```
domain_id: D1
code_baseline: 5883a140
source: apps/stores/services/ (13 files) + resolution.py + authorization.py
```

| Service / module | Responsibility | External side effects |
|---|---|---|
| `resolution.resolve_store_for_hostname` | **Sole** authoritative Host→Store resolver (eligibility: Store ACTIVE + domain VERIFIED + not retired). Also `resolve_store_for_admin_host`/`_request`, `resolve_store_for_storefront`, `resolve_storefront_url_for_store` | — |
| `authorization.py` | role→permission matrix; `user_has_permission`, `get_active_membership` | — |
| `publication_service` | **Sole** reader of `onboarding_completed_at` for visibility; combines Store.status + onboarding + subscription entitlement (fail-open). PublicationState enum | reads subscriptions (local import) |
| `store_status_service` | `suspend_store` / `activate_store` (keeps suspended_* as history) | audit |
| `domain_verification_service` | custom-domain lifecycle: begin/check DNS, routing, TLS, activate | **real DNS TXT (dnspython) + SSL socket** |
| `platform_code_service` | `generate_unique_platform_code` (collision-checked) | — |
| `deletion_service` | `request_deletion` (soft, schedule purge), `cancel_deletion`, `purge_due_stores` | `notify_security_event`; PlatformAuditLogEntry |
| `membership_service` | add/change/revoke/reactivate staff; **`transfer_ownership`** (direct) | subscription seat enforcement; audit; creates is_staff User |
| `ownership_transfer_service` | two-party OTP transfer (initiate/accept/cancel) | `portal.owner_auth_service`; `notify_security_event` |
| `handle_service` | claim/rename platform subdomain handle | — |
| `integration_service` | connect/disconnect/test non-payment integrations | — |
| domain_consistency / domain_namespace / domain_typo / enamad_verification services | domain safety/namespace/typo/eNamad checks | some external (eNamad) |

All mutation services use `@atomic` + `select_for_update` on the mutated aggregate where relevant
(domain verification, membership, ownership transfer).
