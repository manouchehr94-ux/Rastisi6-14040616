# 05 — Dependency Validation

Spot-validates the highest-impact cross-domain dependency claims from Phase 1 doc 07, especially
the cross-domain mutation edges and the deliberate cycle-avoidance claims. Evidence from frozen
snapshot `5883a140`.

Classification: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED / UPGRADED / NOT_PROVEN / DISPROVED.

---

## Cross-domain mutation edges

| Edge | Phase 2 evidence | Classification |
|---|---|---|
| `dashboard` → `content` (direct writes) | 83 save/delete/clean sites in `dashboard/views.py`; content has no write service | CONFIRMED |
| `dashboard` → `core.ShopSettings` (direct save) | Verified in doc 02 | CONFIRMED |
| `orders` → `cart` (reprice/delete/coupon) | Phase 1 read; not contradicted | CONFIRMED |
| `billing` → `subscriptions` (funneled via subscription_service) | Verified in doc 04 (no direct status write outside subscription_service) | CONFIRMED |
| `portal.provisioning_service` → stores+core+catalog+subscriptions (one atomic) | Phase 1 read; not contradicted | CONFIRMED |
| `stores` services → `notifications` (notify_security_event) | Callers verified in Phase 1 STEP-0 correction (deletion/handle/ownership_transfer) | CONFIRMED |
| `content` models → `storefront_builder.StorefrontSection` (FK CASCADE) | Placement models FK into StorefrontSection (Phase 1 model read) | CONFIRMED |
| **`dashboard` → `stores.membership_service.transfer_ownership`** | **NEW edge confirmed:** `dashboard/views.py:5896` calls `transfer_ownership` | CONFIRMED (adds a live dashboard→stores mutation edge for ownership) |

---

## No-signal coupling claim

- Phase 1: **0 Django signals** in production; side effects via explicit calls +
  `transaction.on_commit`.
- Phase 2: re-grep for `@receiver` / `post_save.` / `pre_save.` / `.connect(` in production found
  no signal receivers (only unrelated `sqlite3.connect` in QA commands and a service method
  literally named `.connect`). **CONFIRMED.**

---

## Deliberate cycle-avoidance claims

| Claim | Phase 2 evidence | Classification |
|---|---|---|
| `stores` duplicates `core.TimeStampedModel` to avoid future `core→stores` cycle | `StoresTimestampedModel` docstring states this explicitly (Phase 1 read) | CONFIRMED |
| `publication_service` uses local `subscriptions` import to avoid `stores→subscriptions` module cycle | Phase 1 read | CONFIRMED |
| `catalog.home` / `content.page_detail` import `storefront_builder` lazily | Phase 1 read | CONFIRMED |

These remain **latent cycle risks** (managed), consistent with Phase 1 MEDIUM M13.

---

## Highest-coupling nodes (re-affirmed)

`stores.Store` (universal FK + resolution), `dashboard` (controller fan-out incl. direct writes),
`portal.provisioning_service` (4-app atomic), `billing → subscriptions`,
`storefront_builder ↔ content ↔ catalog`. **CONFIRMED** (unchanged).

---

## Result
- All spot-validated dependency edges **CONFIRMED**; none DISPROVED.
- One dependency edge **added** to the map: `dashboard → stores.membership_service.transfer_ownership`
  (a live cross-domain ownership-mutation edge), consistent with the A8/M6 upgrade in doc 03.
