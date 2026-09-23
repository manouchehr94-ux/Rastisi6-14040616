# 03 — Ownership Validation

Validates every `AMBIGUOUS_OWNERSHIP` item (A1–A9, Phase 1 doc 14 §1), every claimed
**duplicate source of truth** (doc 12 M1, M2, M11), and every claimed **parallel
implementation** (doc 12 M3, M4, M6, M10, M12; H3). Evidence from frozen snapshot `5883a140`.

Classification: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED / UPGRADED / NOT_PROVEN / DISPROVED.

---

## Ambiguous-ownership items

| # | Item | Phase 2 evidence | Classification |
|---|---|---|---|
| A1 | `stores.Store` vs `catalog.Vendor` | Both classes exist; `Store` docstring asserts distinctness (ADR-1). The live *role* of `Vendor` vs `Store` as the "seller" boundary was not fully traced (Vendor is FK'd by Order). Remains genuinely ambiguous from code alone. | CONFIRMED (as AMBIGUOUS/UNKNOWN) |
| A2 | Footer ×3 | `StorefrontLayoutVersion.footer_config` (JSON, in migrations/model), `content.FooterSettings` (model class present), footer chrome variant (`global_region_registry.py` present). Three representations verified to exist. | CONFIRMED |
| A3 | "Page" ×2 | `storefront_builder.StorefrontPage` and `content.ContentPage` both exist as distinct models. | CONFIRMED |
| A4 | Order gateway ×2 | `orders/models.py`: `class PaymentGateway` (line 311) AND `class PaymentGatewayConfig` (line 574). Both present. | CONFIRMED |
| A5 | `ShopSettings` write authority | Owned by `core`; written by dashboard views + sms_service; read widely. Verified in doc 02. | CONFIRMED |
| A6 | Subscription lifecycle (subscriptions vs billing) | billing drives transitions through `subscription_service` (funneled). Effectively co-owned. | CONFIRMED |
| A7 | Storefront write surface (R3 vs R4) | Both wired; legacy fail-closed via `_require_legacy_editor_active`; R4 default. | CONFIRMED (see H3) |
| A8 | Ownership transfer ×2 | **Both paths are LIVE**: `membership_service.transfer_ownership` (dashboard `staff/<pk>/transfer-ownership/`) and `ownership_transfer_service` (portal OTP flow). | **UPGRADED** (both confirmed live; Phase 1 hedged one as possibly dead) |
| A9 | Section placement ×3 | `StorefrontCell.section` (OneToOne), `StorefrontSection.cell` (FK), legacy `row_key/row_span` — all present on the models (Phase 1 read; not contradicted). | CONFIRMED |

---

## Duplicate sources of truth

| # | Item | Phase 2 evidence | Classification |
|---|---|---|---|
| M1 | Appearance/theme/palette across registries | `appearance_registry.py`, `palette_pack_64.py`, `theme_catalog.py` all present; palettes in ≥2, re-projected into `storefront_appearance` typed registry; appearance also mirrored into header/footer_config by persistence. | CONFIRMED |
| M2 | Footer ×3 | Same as A2. | CONFIRMED |
| M11 | Dual media representation on placements | Legacy ImageField + MediaAsset FK on Hero/Banner/Story (Phase 1 model read). Not contradicted. | CONFIRMED |

---

## Parallel implementations

| # | Item | Phase 2 evidence | Classification |
|---|---|---|---|
| H1/H3 | Two order-payment impls; three storefront editor generations | Verified in doc 01. | CONFIRMED |
| M3 | Two "page" concepts | Same as A3. | CONFIRMED |
| M4 | Dual gateway representation | Same as A4. | CONFIRMED |
| M6 | Two ownership-transfer implementations | Both live (A8). | **UPGRADED** (both live) |
| M10 | Dual settings validation (Strangler) | `settings_schema.clean_schema_patch` + legacy `SectionDefinition.validate_settings` (Phase 1 read). Not contradicted. | CONFIRMED |
| M12 | Dual/parallel section-placement mechanisms | Same as A9. | CONFIRMED |

---

## Net ownership-validation result

- **8 of 9 ambiguous-ownership items CONFIRMED as-is.**
- **A8 / M6 UPGRADED:** the ownership-transfer duplication is stronger than Phase 1 stated —
  **two live paths**, not one-live-plus-one-possibly-dead. This is a genuine duplicate mutation
  path for `StoreMembership` owner reassignment and is carried into Phase 4 as a decision-required
  item.
- **No ambiguous-ownership or duplicate claim was DISPROVED.**
- A1 (Store vs Vendor) remains the least-resolved item; it stays AMBIGUOUS/UNKNOWN pending a
  dedicated Vendor-role trace (recorded as an unknown, not asserted either way).
