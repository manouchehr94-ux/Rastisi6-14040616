# dashboard — Boundaries

```
domain_id: D11
code_baseline: 5883a140
known_risks: H2, M5
```

## Owns
- The merchant admin surface at `/admin-portal/`: routing (`urls.py`), views (`views.py`),
  auth/authorization decorators (`decorators.py`), embed frame-options middleware, forms,
  context processors, and admin-side orchestration services (`services/`). **No models.**

## Does NOT own
- **Any domain data model.** It writes other apps' models (see MUTATION_AUTHORITY).
- **Storefront layout** — delegates to `storefront_builder` views (registers their routes).
- **Owner/platform identity** — `portal` (dashboard is the per-Store admin, not the platform admin).

## The controller reality (thin vs thick)
- **Thin controller** (delegates to services): catalog, orders (status/refund/return), staff,
  import/export, subscription/billing reads.
- **Thick controller** (business logic + direct writes in views): **content** (no service — H2),
  **settings/ShopSettings**, **shipping/tax/gateway config** (M5). This asymmetry is the domain's
  defining smell and the source of DR-2/DR-3.

## Cross-domain relationships
Reads/writes into: catalog, orders, content, core, stores, subscriptions, sms, storefront_builder.
It is **the** cross-domain writer for content/settings/config.
