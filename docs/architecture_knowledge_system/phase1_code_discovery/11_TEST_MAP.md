# 11 — Test Map

Behavior → implementation → tests. Evidence class: test file existence is VERIFIED (from tree +
grep). Individual test-body assertions are INFERRED from filenames/names unless noted. Total
`def test_` functions: **8,665** (VERIFIED via grep count).

---

## 1. Orders / payments / cart

| Behavior | Implementation | Tests |
|---|---|---|
| Order creation, state machine, restock-on-cancel, coupon usage | `order_service.create_order_from_cart`, `change_order_status` | `orders/tests/test_order_service.py`, `test_checkout_*.py`, `test_cat002_checkout_valuation.py` |
| Legacy simulated payment | `payment_service.simulate_payment` | `orders/tests/test_payment_service.py` |
| Real gateway payment + idempotent callback | `gateway_payment_service` | `orders/tests/test_gateway_payment_service.py` |
| Refund (manual) + tax | `refund_service` | `orders/tests/test_refund_service.py`, `test_refund_service_tax.py` |
| Returns lifecycle | `return_service` | `orders/tests/test_return_service.py` |
| Cart pricing/security/gift-wrap | `cart_service`, `pricing`, `gift_wrap_service` | `cart/tests/test_cart_service.py`, `test_pricing.py`, `test_cart_security.py`, `test_gift_wrap.py` |

## 2. Billing / subscriptions

| Behavior | Implementation | Tests |
|---|---|---|
| Payment confirmation + subscription activation/renewal; webhook activation; duplicate-webhook idempotency; amount/currency mismatch | `confirmation_service`, `payment_flow_service` | `billing/tests/test_confirmation_activation.py` |
| Webhook inbox dedup | `webhook_service` | `billing/tests/test_webhook_inbox.py` |
| Renewals | `renewal_service` | `billing/tests/test_renewals.py` |
| Dunning + cancellation | `dunning_service`, `cancellation_service` | `billing/tests/test_dunning_cancellation.py` |
| Credit notes / refunds | `credit_note_service`, `refund_service` | `billing/tests/test_credit_refund.py` |
| Plan-change billing | `plan_change_billing_service` | `billing/tests/test_plan_change_billing.py` |
| Providers & attempts; Zibal provider | providers, `attempt_service` | `billing/tests/test_provider_and_attempts.py`, `test_zibal_platform_provider.py` |
| Invoice lines & numbering | `invoice_service`, `numbering_service` | `billing/tests/test_invoice_lines_numbering.py` |
| Account/invoice; consistency isolation | `account_service`, `consistency_service` | `billing/tests/test_account_and_invoice.py`, `test_consistency_isolation.py` |
| Billing admin actions | `billing/admin.py` | `billing/tests/test_billing_admin.py` |
| Subscription state machine, plan change, manual trial, isolation | `subscription_service`, `plan_change_service` | `subscriptions/tests/test_state_machine.py`, `test_plan_change.py`, `test_manual_trial_controls.py`, `test_management_and_isolation.py` |

## 3. Tenancy / identity / platform

| Behavior | Implementation | Tests |
|---|---|---|
| Host→Store resolution, middleware, normalization | `resolution.py`, middleware, `hostnames.py` | `stores/tests/test_resolution.py`, `test_middleware.py`, `test_normalization.py` |
| Host routing / admin-host enforcement / canonical redirect | `PlatformHostRoutingMiddleware`, admin-host resolver | `portal/tests/test_platform_host_routing.py`, `stores/tests/test_admin_host_enforcement.py`, `test_admin_subdomain.py`, `test_storefront_canonical_redirect.py` |
| Trial provisioning / onboarding | `provisioning_service` | `portal/tests/test_provisioning.py`, `test_store_create_view.py`, `test_onboarding.py`, `test_onboarding_authorization.py` |
| Domain verification / handle / namespace guards | `domain_verification_service`, `handle_service` | `stores/tests/test_domain_verification_service.py`, `test_handle_service.py`, `test_domain_namespace_write_guards.py`, `test_domain_consistency.py`, `test_domain_typo_service.py`, `test_enamad_verification.py`; `portal/tests/test_custom_domain_views.py`, `test_claim_handle_views.py` |
| Membership / ownership transfer / authorization / constraints | `membership_service`, `ownership_transfer_service`, `authorization.py` | `stores/tests/test_membership_service.py`, `test_ownership_transfer_service.py`, `test_authorization.py`, `test_constraints.py`; `portal/tests/test_ownership_transfer_views.py`, `test_my_stores.py` |
| Owner/customer auth + OTP + step-up + handoff | `owner_auth_service`, `owner_otp_service`, `step_up_service`, `customers.auth_service` | `portal/tests/test_owner_auth.py`, `test_owner_otp.py`, `test_unified_login.py`, `test_step_up_billing.py`, `test_central_admin_login.py`, `test_handoff*.py`; `customers/tests/test_auth_service.py`, `test_auth_views.py` |
| Publication / status / deletion / purge / admin gate | `publication_service`, `store_status_service`, `deletion_service`, `admin_permissions` | `stores/tests/test_publication_service.py`, `test_deletion_service.py`, `test_purge_deleted_stores_command.py`, `test_admin_superuser_gate.py` |
| Platform admin console | `platform_admin_views` | `portal/tests/test_platform_admin*.py` |

## 4. Dashboard (merchant admin) — ~17.5k test LOC (VERIFIED)
Largest groupings: **products** (`test_product_views` 770, `test_product_variant_views` 1107,
`test_product_options_views` 872, `test_product_image_views` 511, + entry-draft/quick-add/sku/wizard/
bulk-actions); **settings** (`test_settings_views` 1044, `setup_checklist` 633, industry/template,
shipping/tax, integration, payment/gateway); **commerce** (order/invoice/return-refund/coupon/customer
CRM/segment); **auth/permission** (`test_admin_login`, `test_decorators`, `test_permission_enforcement`
308, `test_membership_authorization`, `test_staff_views`); **import/export**; **sms admin**;
**billing/subscription views**. Strong recurring theme: **multi-tenant store isolation** and
**permission enforcement** tests.

## 5. Storefront builder — ~61k test LOC (VERIFIED)
`test_r4_inspector.py`, `test_r4_showcase_facade.py`, `test_r4_store_appearance_registry.py`,
`test_storefront_page.py`, `test_render_service.py`, `test_layout_preset_registry.py`,
`test_u8_template_gallery.py`, `test_phase5_w5c_ready_template_preview_ux.py`, live/merchant template
preview tests, `test_u1b2_capability_metadata_wiring.py`. `section_registry`'s
`PageTypeConstantsMatchModelTests` guards the duplicated 6 PageType strings against the model enum.

## 6. SMS / notifications / core
- SMS send + credit/overdraft + gateway poll/ack: `sms/tests/*`.
- Order-status→SMS on_commit: `orders/tests/test_order_service.py`.
- Export/import: `core` + `dashboard` export/import view tests.

## 7. Apparent coverage gaps (INFERRED — for later verification)
- **`Order.payment_status` transition legality** — no single test proving the (missing) transition
  table; individual writers are tested but not the combined invariant (aligns with the doc 09 gap).
- **`content.*` write paths** — content CRUD is tested via dashboard view tests, but there is no
  content-domain service test suite (because there is no content write service).
- **`apps/blog`** — `tests.py` is 20 LOC; no storefront-integration test (consistent with no urls/views).
- **Payment SMS events** (PAYMENT_SUCCESS/FAILED) — wired in both payment services; test presence
  in `orders/tests/test_payment_service.py` is likely but the exact assertion was not opened (INFERRED).
- **Client-side R4 JS** — no JS unit tests read; behavior is covered indirectly via server mutation tests.

## 8. Note on test evidence
Per the governing document: tests evidence *intended/verified* behavior, not that all production
paths conform. Where a behavior has both an implementation and a matching test, doc 15's matrix
treats it as VERIFIED; where only a filename suggests coverage, the mapping is INFERRED.
