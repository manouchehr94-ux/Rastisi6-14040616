# stores — Testing

```
domain_id: D1
code_baseline: 5883a140
```

| Behavior | Test file |
|---|---|
| Host→Store resolution / normalization | `apps/stores/tests/test_resolution.py`, `test_normalization.py` |
| Middleware / admin-host / canonical redirect | `test_middleware.py`, `test_admin_host_enforcement.py`, `test_admin_subdomain.py`, `test_storefront_canonical_redirect.py` |
| Membership / authorization / constraints | `test_membership_service.py`, `test_authorization.py`, `test_constraints.py` |
| Ownership transfer (OTP flow) | `test_ownership_transfer_service.py` (+ `apps/portal/tests/test_ownership_transfer_views.py`) |
| Domain verification / handle / namespace guards | `test_domain_verification_service.py`, `test_handle_service.py`, `test_domain_namespace_write_guards.py`, `test_domain_consistency.py`, `test_domain_typo_service.py`, `test_enamad_verification.py` |
| Publication / status / deletion / purge | `test_publication_service.py`, `test_deletion_service.py`, `test_purge_deleted_stores_command.py` |
| Django-admin superuser gate | `test_admin_superuser_gate.py` |

## Note
The `membership_service.transfer_ownership` path is referenced in membership tests; the portal OTP
flow is tested via `test_ownership_transfer_service.py` + portal view tests — reflecting the two
live transfer paths (DR-4).
