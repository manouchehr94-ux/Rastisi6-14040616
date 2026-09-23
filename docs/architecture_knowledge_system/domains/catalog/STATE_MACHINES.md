# catalog — State Machines

```
domain_id: D4
code_baseline: 5883a140
```

## Product — two orthogonal lifecycles (not one machine)
- **Publish axis:** `status` (draft/active/inactive) + `publish_at` (scheduled) + `visibility`
  (public/link_only). Publish-readiness gated by `product_publish_service.validate_product_for_publish`.
- **Build axis:** `is_draft_placeholder` (True → False). Managed by `product_draft_service`; a real
  Product row exists while a merchant is still adding it. Independent of `status`.

## WarehouseTransfer — GUARDED (table)
```
draft → requested → in_transit → received
                              ↘ cancelled
```
`ALLOWED_TRANSITIONS` in `catalog/models.py` + `transfer_service`.

## InventoryReservation.status
```
active → {consumed, released, expired, cancelled}
```
Created + consumed synchronously in `create_order_from_cart` (ADR-39).

## IndustryTemplate.Readiness
```
draft → validation_failed / review_required → production_ready → deprecated → archived
```

## StoreTemplateUpdate.status
```
pending → {completed, failed}
```

## PlanVersion-like note
Industry template **versions are immutable snapshots**; existing installations never auto-update
(ADR-25); updates default to additive-only auto-apply, everything else needs explicit review
(ADR-29).
