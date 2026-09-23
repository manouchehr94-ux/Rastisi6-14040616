# stores — State Machines

```
domain_id: D1
code_baseline: 5883a140
```

## Store.status — service-guarded (no table)
```
provisioning → active → suspended → closed
```
Writers: `store_status_service` (suspend/activate), `deletion_service` (→closed on soft delete),
`provisioning_service` (create ACTIVE). `suspended_*` fields kept as history even after reactivate.

## Store.onboarding_stage — soft progress pointer (not a hard lock)
```
identity → industry → branding → review → done
```
Documented as a save-progress pointer; the merchant may go back. Only the REVIEW transition sets
`onboarding_completed_at` (which flips the store from private to publicly visible, subject to
`publication_service`).

## StoreDomain verification lifecycle — guarded by service + 5 DB CheckConstraints
```
VerificationStatus: unverified → pending → {verified, failed}
RoutingStatus:      unchecked / connected / not_connected
TlsStatus:          unchecked / ready / not_ready
retired_at set ⇒ hostname permanently stops routing (never reassigned)
```
Writer: `domain_verification_service` (real DNS/TLS). CheckConstraints tie status↔timestamps↔token.

## StoreMembership.status
```
invited → active → revoked   (accepted_at / revoked_at required by CheckConstraints)
```
`uniq_active_owner_per_store` guarantees exactly one active OWNER.

## StoreOwnershipTransfer.status
```
pending → {completed, expired, cancelled}
```

## Derived: "is this store publicly visible?" (MEDIUM M8)
`publication_service.PublicationState` is derived from Store.status + onboarding_completed_at +
StoreDomain verification/routing + subscription entitlement — and **fails open** (AccessState.NONE
→ ACTIVE_PAID). It is a derived machine, not a stored field.
