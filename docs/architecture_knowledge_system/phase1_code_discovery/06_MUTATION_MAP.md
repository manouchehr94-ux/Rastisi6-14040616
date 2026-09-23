# 06 — Mutation Map (WHO MUTATES WHAT)

This is the mandatory deliverable. For each important persisted entity, every meaningful writer
is listed and classified:

- **CANONICAL_WRITER** — the intended primary mutation boundary.
- **SECONDARY_WRITER** — a legitimate additional writer within the same domain.
- **DIRECT_MODEL_WRITE** — a `.save()`/`.update()`/`.create()` bypassing the owning domain's service.
- **CROSS_DOMAIN_WRITE** — a writer belonging to a different domain than the entity's owner.
- **UNKNOWN_WRITE_PATH** — a writer that could exist but was not conclusively located.

Evidence class legend as in doc 01.

---

## 1. `Order.status` (owner: orders) — VERIFIED

| Writer | Classification | Evidence |
|---|---|---|
| `order_service.change_order_status` | **CANONICAL_WRITER** | guards module `ALLOWED_TRANSITIONS` + FINAL_STATUSES; writes status + OrderStatusHistory |
| `order_service.create_order_from_cart` | SECONDARY_WRITER | writes initial status via same service |
| (callers of change_order_status) payment_service, gateway_payment_service, dashboard `order_detail` | via canonical | all funnel through `change_order_status` |

**Risk:** LOW — single guarded writer. Admin is read-only for order status.

## 2. `Order.payment_status` (owner: orders) — VERIFIED — **DUPLICATE MUTATION PATH**

| Writer | Classification | Evidence |
|---|---|---|
| `payment_service.simulate_payment` (LEGACY) | SECONDARY_WRITER | `payment_service.py:86-98` direct `order.save(update_fields=["payment_status",…])` → PAID/FAILED |
| `gateway_payment_service.process_callback_and_verify` (NEW) | CANONICAL_WRITER (intended) | `gateway_payment_service.py:315` conditional `Order.objects.filter(...PENDING).update(payment_status=PAID)` under lock |
| `refund_service.execute_order_refund` | SECONDARY_WRITER | `refund_service.py:234-235` PAID→REFUNDED direct save |

**Risk:** HIGH — three writers, **no guarded state-machine table** for `payment_status` (unlike
`Order.status`). Only the gateway path re-locks + conditionally updates; simulate/refund do plain
assignment. See doc 09 (state machines) and doc 13 (smell CRIT/HIGH).

## 3. `Transaction` (orders, legacy payment record) — VERIFIED
| Writer | Classification |
|---|---|
| `payment_service.simulate_payment` | SECONDARY_WRITER (creates) |
| `gateway_payment_service.process_callback_and_verify` | SECONDARY_WRITER (creates "for dashboard back-compat") |

**Risk:** MEDIUM — two paths create the legacy record; both a Transaction and a PaymentAttempt exist
for a gateway-paid order.

## 4. `PaymentAttempt` (orders, new) — VERIFIED
| Writer | Classification |
|---|---|
| `gateway_payment_service` (initiate/process) | CANONICAL_WRITER |

**Risk:** LOW.

## 5. `CartItem` / `Cart` (owner: cart) — VERIFIED — **CROSS-DOMAIN**
| Writer | Classification | Evidence |
|---|---|---|
| `cart.cart_service.add_item_to_cart/reprice_cart_items` | CANONICAL_WRITER | membership-fence locking |
| `orders.order_service.create_order_from_cart` (`_lock_cart_items_and_resolve_final_prices`) | CROSS_DOMAIN_WRITE | writes `CartItem.unit_price` |
| `orders.checkout_service.finalize_order` | CROSS_DOMAIN_WRITE | `cart.items.all().delete()` |
| `orders.views.checkout_item_update/checkout_item_remove` | CROSS_DOMAIN_WRITE (view) | `item.save()/item.delete()` |
| `customers.auth_service.merge_guest_cart` | CROSS_DOMAIN_WRITE | merges/deletes guest cart |

**Risk:** MEDIUM — cart is written by orders + customers; cart exposes no deletion service for orders.

## 6. `Coupon.used_count` (owner: cart) — VERIFIED
| Writer | Classification |
|---|---|
| `orders.order_service.create_order_from_cart` (+=1) | CROSS_DOMAIN_WRITE |

**Risk:** LOW-MEDIUM (documented, atomic).

## 7. `StoreSubscription.status` (owner: subscriptions) — VERIFIED
| Writer | Classification | Evidence |
|---|---|---|
| `subscription_service` transitions | **CANONICAL_WRITER** | `ALLOWED_TRANSITIONS`, select_for_update, idempotent |
| billing `confirmation_service._activate_or_renew` | CROSS_DOMAIN_WRITE **via canonical** | calls subscription_service (never direct) |
| billing `dunning_service` | CROSS_DOMAIN_WRITE via canonical | enter_grace/suspend |
| billing `cancellation_service` | CROSS_DOMAIN_WRITE via canonical | cancel_* |
| billing `renewal_service` | CROSS_DOMAIN_WRITE via canonical | change_plan_version |
| subscriptions `plan_change_service` override | SECONDARY_WRITER via canonical | staff override |

**Risk:** MEDIUM — subscription lifecycle is effectively co-owned by billing, but **all writes are
funneled through `subscription_service`** (no direct status write elsewhere). Tight but disciplined coupling.

## 8. `SubscriptionInvoice.status` (owner: billing) — VERIFIED
| Writer | Classification |
|---|---|
| `invoice_service` (draft/open/void) | CANONICAL_WRITER |
| `confirmation_service.confirm_payment` (→paid) | SECONDARY_WRITER |
| `dunning_service` (→past_due/uncollectible) | SECONDARY_WRITER |
| `refund_service._sync_invoice_refund_status` (→refunded/partially) | SECONDARY_WRITER |
| `payment_flow_service.start_payment` (→payment_pending) | SECONDARY_WRITER |
| admin `action_mark_paid` | via `mark_invoice_paid_manually` → confirmation_service |

**Risk:** MEDIUM — many writers but all in-domain, each guarded by `is_payable`/`is_financially_locked`.
No single transition table (unlike subscription/order.status).

## 9. `Product` (owner: catalog) — VERIFIED — mixed
| Writer | Classification | Evidence |
|---|---|---|
| `catalog.product_draft_service` | CANONICAL_WRITER (draft placeholder) | creates `is_draft_placeholder=True` |
| `dashboard.views._save_product` | CROSS_DOMAIN_WRITE (view direct `.save()`) | flips is_draft_placeholder, sets status/publish_at |
| `dashboard.catalog_admin_service` bulk ops | CROSS_DOMAIN_WRITE (service, `Product.objects.filter(...).update()`) | bulk status/delete/assign |
| `catalog.import`/`industry_template_service` | SECONDARY/CROSS | install deep-copy |

**Risk:** MEDIUM — Product is written both via catalog services and directly by dashboard views.

## 10. `Product.stock` / `ProductVariant.stock` (owner: catalog) — VERIFIED
| Writer | Classification |
|---|---|
| `catalog.inventory_service` (+ StockMovement) | **CANONICAL_WRITER (only)** |

**Risk:** LOW — ledgered, atomic, single owner; QuerySet blocks bulk bypass.

## 11. `ShopSettings` (owner: core) — VERIFIED — **cross-domain / direct**
| Writer | Classification | Evidence |
|---|---|---|
| `core.ShopSettings.provision_for` | CANONICAL_WRITER (create) | idempotent |
| `dashboard.views.settings_shop_info/finance/gift_wrap/appearance/branding` | CROSS_DOMAIN_WRITE (view direct `.save()`) | views.py:4308/4326/4346/4393/4423/4458 |
| `sms.sms_service.regenerate_smsrasti_device_token` | CROSS_DOMAIN_WRITE | writes smsrasti_device_token |
| portal onboarding identity/branding | CROSS_DOMAIN_WRITE (INFERRED) | onboarding views |

**Risk:** MEDIUM — no write-service layer; core owns the model, dashboard is de-facto writer.

## 12. `content.*` (ContentPage/Menu/MenuItem/FooterSettings/HeroSlide/PromotionalBanner/SocialLink/…) — VERIFIED — **direct from dashboard**
| Writer | Classification | Evidence |
|---|---|---|
| `dashboard.views` (page_form/hero/banner/social/menu/footer …) | CROSS_DOMAIN_WRITE (view direct `.save()`/`.full_clean()`/`.delete()`) | views.py:4744–5633 |
| `storefront_builder.layout_service._clone_section_scoped_media` + `media_views` | CROSS_DOMAIN_WRITE | writes content placement rows |

**Risk:** HIGH — `content` has **no write service**; all mutation done by another app's view layer.

## 13. Orders commerce config (`ShippingZone/Method/RateRule`, `TaxClass/TaxRate`, `PaymentGatewayConfig`) (owner: orders) — VERIFIED
| Writer | Classification | Evidence |
|---|---|---|
| `dashboard.views.settings_*` | CROSS_DOMAIN_WRITE (view direct `.save()`) | views.py:6866–7281, 5726–5784 (gateway config incl. credential encryption) |
| `dashboard.settings_admin_service.toggle_*` | CROSS_DOMAIN_WRITE (service) | is_active toggles |

**Risk:** MEDIUM — config models mutated directly by dashboard views.

## 14. Store tenancy entities — VERIFIED
| Entity | Canonical writer(s) | Other |
|---|---|---|
| `Store.status/suspension` | `store_status_service`, `deletion_service` | provisioning (create), platform_admin_views, `Store.save()` fallbacks |
| `Store.onboarding_*` | portal onboarding views (INFERRED) | publication_service reads only |
| `StoreMembership` | `membership_service`, `ownership_transfer_service.accept` | provisioning (initial OWNER) |
| `StoreDomain` verification/routing/tls | `domain_verification_service` | `handle_service` (claim/rename), provisioning (trial), platform_admin domain views |
| `StoreOwnershipTransfer` | `ownership_transfer_service` | — |

**Risk:** MEDIUM — two ownership-transfer code paths (`membership_service.transfer_ownership`
direct vs `ownership_transfer_service` OTP flow) — see doc 13.

## 15. `Customer` / auth `User` — VERIFIED
| Writer | Classification |
|---|---|
| `customers.auth_service` (signup/guest) | CANONICAL_WRITER |
| `portal.owner_auth_service` (register / get_or_create_by_phone) | CANONICAL_WRITER (owner side) |
| `stores.membership_service.add_staff_member` | CROSS_DOMAIN_WRITE (creates is_staff User) |
| platform_admin_views user_activate/suspend | SECONDARY (INFERRED) |

**Risk:** MEDIUM — the shared-identity model (username == phone/email) unifies owner + customer
Users; `is_staff` has three meanings (doc 13).

## 16. SMS entities — VERIFIED
| Entity | Writer |
|---|---|
| `SmsLog`, credit reservation | `sms_service._dispatch` (single funnel) |
| `SmsOutboxItem` | `SmsRastiBackend` (enqueue), `gateway_views` (poll→SENDING, ack→SENT/FAILED) |
| `OtpCode` | sms/otp path + owner_otp_service equivalents |

**Risk:** LOW — single dispatch funnel.

## 17. Notification outbox — VERIFIED
| Writer | Classification |
|---|---|
| `notification_service.enqueue/notify_security_event` | CANONICAL_WRITER |
| `notification_service.deliver_pending` | SECONDARY_WRITER (status/attempts) |
| callers: `stores.deletion_service/handle_service/ownership_transfer_service` | enqueue only |

**Risk:** LOW.

## 18. Storefront layout entities — VERIFIED
| Entity | Canonical writer | Other |
|---|---|---|
| `StorefrontLayoutVersion` status/pointers | `layout_service` (publish/draft/restore) | — |
| `StorefrontSection/Container/Cell` | `r4_mutation_service` (R4), `layout_service`/`container_service`/`preset_service` | legacy `views.py` (fail-closed when R4 active) |
| appearance_config | `appearance_authority_service`/`storefront_appearance.persistence` | mirrors into header/footer_config (dup — doc 13) |

**Risk:** MEDIUM — two editor write surfaces exist; legacy is guarded fail-closed.

---

## 19. Summary — most at-risk entities

| Entity | Writers | Guarded? | Severity |
|---|---|---|---|
| **Order.payment_status** | 3 | **No transition table** | HIGH |
| **content.* (pages/menus/footer/media)** | dashboard views (no service) | model `clean()` only | HIGH |
| Order.Transaction (legacy) | 2 create paths | n/a | MEDIUM |
| CartItem | cart + orders + customers | locking yes | MEDIUM |
| ShopSettings | core + dashboard + sms | model validation | MEDIUM |
| StoreSubscription.status | subscriptions + billing (funneled) | yes (table) | MEDIUM |
| Product | catalog services + dashboard views | partial | MEDIUM |
| Order.status | 1 (funneled) | yes (table) | LOW |
| stock | 1 (ledgered) | yes | LOW |
