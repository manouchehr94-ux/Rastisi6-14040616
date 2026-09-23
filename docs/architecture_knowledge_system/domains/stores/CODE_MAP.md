# stores — Code Map

```
domain_id: D1
code_baseline: 5883a140
```

```
apps/stores/
├── models.py               Store, StoreDomain (+QuerySet guard), StoreMembership,
│                           StoreOwnershipTransfer, StoreIntegrationConnection, StoresTimestampedModel
├── resolution.py           resolve_store_for_hostname (SOLE resolver) + admin-host resolver + storefront helpers
├── authorization.py        role→permission matrix; get_active_membership; user_has_permission
├── hostnames.py            normalize_hostname / normalize_admin_subdomain
├── middleware.py           StoreResolutionMiddleware, StorefrontCanonicalRedirectMiddleware
├── admin_permissions.py    superuser-only Django admin (ADR-8)
├── admin.py
├── integrations/           non-payment integration registry
├── services/               13 files: publication_service, store_status_service,
│                           domain_verification_service, platform_code_service, deletion_service,
│                           membership_service (transfer_ownership), ownership_transfer_service,
│                           handle_service, integration_service, domain_consistency/namespace/typo,
│                           enamad_verification
├── management/commands/    purge_deleted_stores, rename_store_handle, verify_domain_consistency,
│                           apply_golden_reference_storefront, seed_*, kianstock_qa_data, refresh_rasti_mode_demo_visuals
├── migrations/
└── tests/                  resolution, middleware, membership, ownership_transfer, domain_verification,
                            publication, deletion, purge, admin_superuser_gate, constraints
```

## Where to look
| Concern | File |
|---|---|
| Which store is this request? | `resolution.py` |
| Can this user do X? | `authorization.py` + `dashboard.decorators` |
| Store lifecycle | `services/store_status_service.py`, `services/deletion_service.py` |
| Ownership transfer (two paths) | `services/membership_service.py` (dashboard) + `services/ownership_transfer_service.py` (portal OTP) |
| Custom domains | `services/domain_verification_service.py`, `services/handle_service.py` |
| Visibility | `services/publication_service.py` |
