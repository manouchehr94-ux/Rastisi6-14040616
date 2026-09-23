# Change-Impact Guide (Phase 7 — Change Navigation)

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: DR-1..DR-8
```

> **Start here when you are about to change something.** Each change family maps: domain · read
> first · canonical models · canonical services · other writers · dependent domains · runtime flows
> · state machines · tests · known risks · open decisions. Then go to the domain pack's
> `CHANGE_GUIDE.md` for step-by-step recipes.

How to use: (1) find your change family below; (2) read the linked "read first" docs; (3) open the
owning domain's `CHANGE_GUIDE.md`; (4) check the listed OPEN decisions — some **block** the change.

---

## CF-1 — "I want to change payment verification" (or anything about payment state)
| | |
|---|---|
| **Domain** | orders (D6) |
| **Read first** | [`../domains/orders/CHANGE_GUIDE.md`](../domains/orders/CHANGE_GUIDE.md), [`../domains/orders/MUTATION_AUTHORITY.md`](../domains/orders/MUTATION_AUTHORITY.md), [`STATE_MACHINE_INDEX.md`](STATE_MACHINE_INDEX.md) |
| **Canonical models** | `Order` (status, **payment_status**), `PaymentAttempt`, legacy `Transaction`, `PaymentGatewayConfig` |
| **Canonical services** | `gateway_payment_service` (verify), `order_service.change_order_status` |
| **Other writers** | `payment_service.simulate_payment` (legacy, gated), `refund_service` — **3 writers of payment_status** |
| **Dependent domains** | cart (reprice/delete), catalog (stock), sms (on_commit) |
| **Runtime flows** | Flow 3a (simulation), Flow 3b (gateway) — [`RUNTIME_FLOW_INDEX.md`](RUNTIME_FLOW_INDEX.md) |
| **State machines** | `Order.payment_status` (**NOT guarded**), `PaymentAttempt.status` (is_final) |
| **Tests** | `apps/orders/tests/test_gateway_payment_service.py`, `test_payment_service.py` |
| **Known risks** | **H1** (duplicate paths, unguarded payment_status), M4, L1, L4 |
| **Open decisions** | **DR-1 (blocks payment_status semantics)**, DR-5 (gateway model), DR-6 (retire simulation/Transaction) |

## CF-2 — "I want to add a new Store status"
| | |
|---|---|
| **Domain** | stores (D1) |
| **Read first** | [`../domains/stores/CHANGE_GUIDE.md`](../domains/stores/CHANGE_GUIDE.md), [`../domains/stores/STATE_MACHINES.md`](../domains/stores/STATE_MACHINES.md) |
| **Canonical models** | `Store` (status) |
| **Canonical services** | `store_status_service`, `deletion_service`, `publication_service` (visibility classification!) |
| **Other writers** | `provisioning_service` (create), `platform_admin_views` |
| **Dependent domains** | everything reading visibility: storefront render, dashboard gating; `resolution` eligibility (routes only ACTIVE) |
| **Runtime flows** | Flow 0 (resolution), Flow 14 (deletion) |
| **State machines** | `Store.status`; derived visibility (`publication_service`, fails open — M8) |
| **Tests** | `apps/stores/tests/test_publication_service.py`, `test_resolution.py`, `test_deletion_service.py` |
| **Known risks** | M8 (fail-open visibility) |
| **Open decisions** | — (but must update `publication_service.NON_PUBLIC_STATES` + resolution eligibility) |

## CF-3 — "I want to modify storefront appearance"
| | |
|---|---|
| **Domain** | storefront_builder (D9) |
| **Read first** | [`../domains/storefront_builder/GENERATIONS.md`](../domains/storefront_builder/GENERATIONS.md), [`../domains/storefront_builder/CHANGE_GUIDE.md`](../domains/storefront_builder/CHANGE_GUIDE.md) |
| **Canonical models** | `StorefrontLayoutVersion.appearance_config` (mirrored into header/footer_config) |
| **Canonical services** | `appearance_authority_service` / `storefront_appearance.persistence` |
| **Other writers** | registries (appearance_registry/palette_pack_64/theme_catalog) are config sources (M1) |
| **Dependent domains** | content (footer M2), catalog (render) |
| **Runtime flows** | Flow 10 (edit→publish), Flow 11 (render) |
| **State machines** | `StorefrontLayoutVersion.status`; editor-generation gate (`r4_editor_enabled`) |
| **Tests** | `apps/storefront_builder/tests/test_r4_store_appearance_registry.py`, `test_render_service.py` |
| **Known risks** | **H3** (generations), **M1** (duplicate appearance/palette/theme + mirror), M2 (footer ×3), M10 |
| **Open decisions** | DR-6 (legacy R3); (M1 consolidation would be a new decision) |

## CF-4 — "I want to change content pages" (or menus/footer/hero/banner)
| | |
|---|---|
| **Domain** | content (D10) — but **written by dashboard** (H2) |
| **Read first** | [`../domains/content/CHANGE_GUIDE.md`](../domains/content/CHANGE_GUIDE.md), [`../domains/content/MUTATION_AUTHORITY.md`](../domains/content/MUTATION_AUTHORITY.md) |
| **Canonical models** | `ContentPage`, `Menu`/`MenuItem`, `FooterSettings`, `HeroSlide`/`PromotionalBanner`/`StoryRailItem` |
| **Canonical services** | **NONE (H2)** — CRUD is in `apps/dashboard/views.py` (~4705-5610) |
| **Other writers** | `storefront_builder` clones placement media |
| **Dependent domains** | storefront render (reads published content); storefront_builder (placements FK sections) |
| **State machines** | `ContentPage.status` (draft/published) |
| **Tests** | dashboard content-view tests (no content service tests) |
| **Known risks** | **H2** (no write service), M2 (footer ×3), M11 (dual media) |
| **Open decisions** | **DR-2 (content write boundary)** |

## CF-5 — "I want to modify subscription renewal"
| | |
|---|---|
| **Domain** | billing (D8) drives subscriptions (D7) |
| **Read first** | [`../domains/billing/CHANGE_GUIDE.md`](../domains/billing/CHANGE_GUIDE.md), [`../domains/billing/FLOWS.md`](../domains/billing/FLOWS.md) |
| **Canonical models** | `SubscriptionInvoice`, `ScheduledPlanChange`, `StoreSubscription` (via subscription_service) |
| **Canonical services** | `renewal_service` (billing) → `subscription_service.change_plan_version` (subscriptions) |
| **Other writers** | none direct (billing funnels through subscription_service — M7) |
| **Dependent domains** | subscriptions (state), numbering |
| **Runtime flows** | Flow 8 (renewal + dunning) |
| **State machines** | `SubscriptionInvoice.status`, `StoreSubscription.status` |
| **Tests** | `apps/billing/tests/test_renewals.py` |
| **Known risks** | M7 (billing co-owns subscription lifecycle) |
| **Open decisions** | — (respect canonical lock order Subscription→ScheduledPlanChange) |

## CF-6 — "I want to change SMS sending"
| | |
|---|---|
| **Domain** | sms (D12) |
| **Read first** | [`../domains/sms/CHANGE_GUIDE.md`](../domains/sms/CHANGE_GUIDE.md), [`../domains/sms/SERVICES.md`](../domains/sms/SERVICES.md) |
| **Canonical models** | `SmsLog`, `SmsOutboxItem`, `SmsBalance`, `OtpCode` |
| **Canonical services** | `sms_service._dispatch` (single funnel) |
| **Other writers** | `gateway_views` (device poll/ack); platform path `portal.owner_sms_service` |
| **Dependent domains** | orders/customers (on_commit senders), notifications, portal (OTP) |
| **Runtime flows** | Flow 13 (SMS send) |
| **State machines** | `SmsOutboxItem.status` (pending→sending→sent/failed) |
| **Tests** | `apps/sms/tests/*`, `apps/orders/tests/test_order_service.py` |
| **Known risks** | wide send surface (funneled); ShopSettings legacy SMS fields dead (D4) |
| **Open decisions** | — |

## CF-7 — "I want to change owner authentication"
| | |
|---|---|
| **Domain** | portal (D2) — **shared identity with customers (D3)** |
| **Read first** | [`../domains/portal/CHANGE_GUIDE.md`](../domains/portal/CHANGE_GUIDE.md), [`../domains/portal/SECURITY.md`](../domains/portal/SECURITY.md) |
| **Canonical models** | `OwnerProfile`, `OwnerOtpChallenge`, `auth.User` (shared, username==phone) |
| **Canonical services** | `owner_auth_service`, `owner_otp_service`, `step_up_service` |
| **Other writers** | `stores.membership_service.add_staff_member` (creates is_staff User) |
| **Dependent domains** | **customers (shared User — ADR-102)**, stores (membership), dashboard (handoff) |
| **Runtime flows** | Flow 6 (owner auth + step-up) |
| **State machines** | OwnerOtpChallenge lifecycle |
| **Tests** | `apps/portal/tests/test_owner_auth.py`, `test_owner_otp.py`, `test_unified_login.py` |
| **Known risks** | **M15** (`is_staff` overloaded 3 ways); shared identity affects customer login |
| **Open decisions** | — (DR-4 if touching ownership transfer) |

## CF-8 — "I want to change product inventory"
| | |
|---|---|
| **Domain** | catalog (D4) |
| **Read first** | [`../domains/catalog/CHANGE_GUIDE.md`](../domains/catalog/CHANGE_GUIDE.md), [`../domains/catalog/INVARIANTS.md`](../domains/catalog/INVARIANTS.md) |
| **Canonical models** | `Product.stock`/`ProductVariant.stock`, `StockMovement`, `WarehouseInventory`, `InventoryReservation` |
| **Canonical services** | `inventory_service` (the ONLY stock writer, ledgered), `reservation_service` |
| **Other writers** | none for stock (QuerySet blocks bulk bypass); orders reserves/consumes cross-domain |
| **Dependent domains** | orders (reserve/consume at order creation), cart (availability), dashboard (import) |
| **Runtime flows** | Flow 2 (order creation consumes inventory) |
| **State machines** | `InventoryReservation.status`, `WarehouseTransfer` (ALLOWED_TRANSITIONS) |
| **Tests** | catalog inventory tests; `verify_inventory_consistency` |
| **Known risks** | — (strongly guarded); ADR-31/38/39/40 |
| **Open decisions** | — (DR-7 only if touching Vendor) |

---

## Additional change families (quick reference)
| Change | Domain(s) | Read first | Blocking DR |
|---|---|---|---|
| Change order status lifecycle | orders | orders/STATE_MACHINES | — (guarded; use change_order_status) |
| Change refund behavior | orders | orders/CHANGE_GUIDE | (GATEWAY refunds = new decision, ADR-33) |
| Change shop settings / shipping / tax / gateway config | core/orders via dashboard | dashboard/CHANGE_GUIDE | **DR-3** |
| Change ownership transfer | stores + portal + dashboard | stores/CHANGE_GUIDE | **DR-4** (two live paths) |
| Add a payment provider (storefront) | orders | orders/CHANGE_GUIDE | DR-5 |
| Add a billing provider (SaaS) | billing | billing/CHANGE_GUIDE | — |
| Change store provisioning | portal (+4 apps) | portal/CHANGE_GUIDE | — (4-app atomic) |
| Change custom domain verification | stores | stores/CHANGE_GUIDE | — |
| Change catalog import | dashboard + catalog | catalog/CHANGE_GUIDE | — (ADR-58 service-only) |
| Retire simulation / legacy Transaction / R3 editor | orders / storefront_builder | orders + storefront_builder CHANGE_GUIDE | **DR-6** |
| Make Customer store-scoped | customers | customers/CHANGE_GUIDE | (significant design change, ADR-6/50) |

## Blocking-decision index
- **DR-1** blocks: payment_status semantics / new payment state (CF-1).
- **DR-2** blocks: introducing a content service (CF-4).
- **DR-3** blocks: routing settings/config writes through services.
- **DR-4** blocks: unifying ownership transfer.
- **DR-5** blocks: clean gateway-config mapping (CF-1).
- **DR-6** blocks: retiring simulation / legacy Transaction / R3 editor (CF-1, CF-3).
- **DR-7** blocks: defining Store vs Vendor (CF-8 boundary).
- **DR-8** blocks: adopting/removing `require_resolved_store`.

See [`ARCHITECTURAL_DECISION_REGISTER.md`](ARCHITECTURAL_DECISION_REGISTER.md).
