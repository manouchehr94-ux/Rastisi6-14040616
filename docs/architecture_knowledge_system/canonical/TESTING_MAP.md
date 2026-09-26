# Testing Map

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 11)
```

Behavior → test location. Authoritative detail: Phase 1
[`../phase1_code_discovery/11_TEST_MAP.md`](../phase1_code_discovery/11_TEST_MAP.md). Per-domain
`TESTING.md` in each pack. Total `def test_` functions: **8,665** (VERIFIED).

---

## Orders / payments / cart
| Behavior | Tests |
|---|---|
| Order creation, state machine, restock-on-cancel, coupon | `apps/orders/tests/test_order_service.py`, `test_checkout_*.py`, `test_cat002_checkout_valuation.py` |
| Legacy simulated payment | `apps/orders/tests/test_payment_service.py` |
| Real gateway payment + idempotent callback | `apps/orders/tests/test_gateway_payment_service.py` |
| Refund (manual) + tax | `apps/orders/tests/test_refund_service.py`, `test_refund_service_tax.py` |
| Returns lifecycle | `apps/orders/tests/test_return_service.py` |
| Cart pricing/security/gift-wrap | `apps/cart/tests/test_cart_service.py`, `test_pricing.py`, `test_cart_security.py`, `test_gift_wrap.py` |

## Billing / subscriptions
| Behavior | Tests |
|---|---|
| Payment confirmation + activation/renewal; webhook; idempotency; amount/currency mismatch | `apps/billing/tests/test_confirmation_activation.py` |
| Webhook inbox dedup | `apps/billing/tests/test_webhook_inbox.py` |
| Renewals / dunning / cancellation | `test_renewals.py`, `test_dunning_cancellation.py` |
| Credit notes / refunds | `test_credit_refund.py` |
| Plan-change billing | `test_plan_change_billing.py` |
| Providers & attempts; Zibal | `test_provider_and_attempts.py`, `test_zibal_platform_provider.py` |
| Invoice lines & numbering; consistency isolation | `test_invoice_lines_numbering.py`, `test_consistency_isolation.py` |
| Subscription state machine / plan change / trial / isolation | `apps/subscriptions/tests/test_state_machine.py`, `test_plan_change.py`, `test_manual_trial_controls.py`, `test_management_and_isolation.py` |

## Tenancy / identity / platform
| Behavior | Tests |
|---|---|
| Host→Store resolution / middleware / normalization | `apps/stores/tests/test_resolution.py`, `test_middleware.py`, `test_normalization.py` |
| Host routing / admin-host / canonical redirect | `apps/portal/tests/test_platform_host_routing.py`; `apps/stores/tests/test_admin_host_enforcement.py`, `test_storefront_canonical_redirect.py` |
| Provisioning / onboarding | `apps/portal/tests/test_provisioning.py`, `test_store_create_view.py`, `test_onboarding.py` |
| Domain verification / handle | `apps/stores/tests/test_domain_verification_service.py`, `test_handle_service.py`, `test_domain_namespace_write_guards.py` |
| Membership / ownership transfer / authorization | `apps/stores/tests/test_membership_service.py`, `test_ownership_transfer_service.py`, `test_authorization.py`, `test_constraints.py`; `apps/portal/tests/test_ownership_transfer_views.py` |
| Owner/customer auth + OTP + step-up | `apps/portal/tests/test_owner_auth.py`, `test_owner_otp.py`, `test_step_up_billing.py`; `apps/customers/tests/test_auth_service.py` |
| Publication / deletion / purge / admin gate | `apps/stores/tests/test_publication_service.py`, `test_deletion_service.py`, `test_purge_deleted_stores_command.py`, `test_admin_superuser_gate.py` |

## Dashboard (~17.5k test LOC) & storefront_builder (~61k test LOC)
Dashboard: heaviest product suite (views/variants/options/images), settings, commerce, auth/perm
(`test_permission_enforcement.py`), import/export, SMS admin, billing/subscription views; strong
multi-tenant isolation + permission themes. Storefront builder: `test_r4_*`, `test_render_service.py`,
`test_storefront_page.py`, `test_layout_preset_registry.py`, `test_u8_template_gallery.py`,
preview/certification tests.

## Apparent coverage gaps (INFERRED — carried from Phase 1)
- **No single `Order.payment_status` transition-legality test** (aligns with the missing guard, H1/DR-1).
- **No content-domain service test suite** (no content write service exists — H2).
- **`apps/blog`** minimal (`tests.py` 20 LOC); no storefront-integration test.
- **R4 client JS** not unit-tested directly (covered indirectly via server mutation tests).
