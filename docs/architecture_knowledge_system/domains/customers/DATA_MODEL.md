# customers — Data Model

```
domain_id: D3
code_baseline: 5883a140
source: apps/customers/models.py (9 models)
```

| Model | Key fields | Notes |
|---|---|---|
| **Customer** | OneToOne User; `phone` unique | **GLOBAL — no store FK** (ADR-50/93). Login identity. Shared with owner via `username == phone` (ADR-102) |
| **CustomerProfile** | cached stats; `internal_status` | **Store-scoped** projection (`uniq_customerprofile_per_store`). Stats refreshed explicitly (no signals, ADR-50) |
| **CustomerTag** | store-scoped | `uniq_customertag_code_per_store` |
| **CustomerNote** | store-scoped internal note | — |
| **CustomerSegment** (+**Rule**, +**Membership**) | `segment_type`, `match_mode` | store-scoped; `uniq_segment_membership` |
| **Address** | shipping/billing address | — |
| **Wishlist** | customer + product | unique (customer, product) |

## Key facts
- **`Customer` is deliberately global** (no store FK) — one shopper account across the platform;
  the per-Store view is `CustomerProfile`.
- Stats on `CustomerProfile` are recomputed from the Store's Orders **explicitly** (ADR-50 — no
  signal), by `dashboard.customer_crm_service.refresh_customer_profile_stats`.
