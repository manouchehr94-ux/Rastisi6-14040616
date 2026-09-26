# customers — Change Guide

```
domain_id: D3
code_baseline: 5883a140
```

## Recipe: Change customer authentication
- **READ FIRST:** [SECURITY](SECURITY.md), `auth_service`.
- **⚠️ Shared identity (ADR-102):** customer and owner share `auth.User` (username == phone). A
  change to customer auth can affect owner login — read [`../portal/CHANGE_GUIDE.md`](../portal/CHANGE_GUIDE.md).
- **INVARIANTS:** username == phone; enumeration-safe; guest accounts get random passwords.
- **TESTS:** `test_auth_service.py`, `test_auth_views.py`.

## Recipe: Change guest→user cart merge
- **READ FIRST:** `auth_service.merge_guest_cart` (CAT-002 fence).
- **⚠️ Cross-domain:** writes `cart`. Keep the `select_for_update` membership fence; quantity merge
  then delete guest cart.

## Recipe: Change CRM (profiles/tags/notes/segments)
- **⚠️** these services live in **`dashboard`** (`customer_crm_service`, `segment_service`), not
  customers. Read [`../dashboard/CHANGE_GUIDE.md`](../dashboard/CHANGE_GUIDE.md).
- **INVARIANTS:** CustomerProfile stats refreshed **explicitly** (ADR-50 — never add a signal);
  `uniq_customerprofile_per_store`; segment rule engine is allowlisted (no eval).

## Recipe: Make Customer store-scoped (would be a design change)
- **⚠️** `Customer` is deliberately global (ADR-6/50). Changing this is a significant design change
  affecting the shared-identity model — not a routine change. No DR currently covers it.
