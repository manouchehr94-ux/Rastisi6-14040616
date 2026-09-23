# content — Change Guide

```
domain_id: D10
code_baseline: 5883a140
open_decisions: DR-2
known_risks: H2, M2, M11
```

> **Before any content change:** content has **no write service**. All CRUD is in
> `apps/dashboard/views.py` (H2). You will be editing dashboard views, not a content service —
> unless DR-2 authorizes creating one.

## Recipe: Change content pages (ContentPage)
- **READ FIRST:** [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md), [STATE_MACHINES](STATE_MACHINES.md).
- **CANONICAL OWNER:** none (dashboard views `page_form`/`page_delete`/`page_publish`, ~4705-4790).
- **LIKELY CODE:** those dashboard views + `ContentPage` model (`clean()`, constraints).
- **DEPENDENT DOMAINS:** storefront render (reads published pages); `storefront_builder` shell.
- **MUTATION PATHS:** direct `.save()`/`.full_clean()` in the view; publish sets `published_at`.
- **INVARIANTS:** published requires timestamp (DB constraint); `uniq(store, slug)`; RESERVED_SLUGS.
- **SECURITY:** keep Store scope + `staff_required`/`permission_required`.
- **TESTS:** dashboard content-view tests; run those.
- **DOCS TO UPDATE:** this pack DATA_MODEL/STATE_MACHINES.
- **OPEN DECISION:** **DR-2** — if you want a service boundary, that is the DR-2 decision.

## Recipe: Change navigation (Menu / MenuItem)
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md) (2-level hierarchy), MUTATION_AUTHORITY.
- **LIKELY CODE:** dashboard `menu_*` / `menu_item_*` views (~5171-5368); `Menu`/`MenuItem` `clean()`.
- **INVARIANTS:** `uniq(store, location)`; child must have a destination; cross-store ownership.
- **REGRESSION RISK:** reordering menu items has no service transaction boundary (H2).

## Recipe: Change footer
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md) (M2 — footer ×3!), MUTATION_AUTHORITY.
- **⚠️ M2:** footer is represented THREE ways — `content.FooterSettings` (this domain),
  `StorefrontLayoutVersion.footer_config` (storefront_builder JSON), and `global_region_registry`
  footer variant. A footer change may need to touch more than one. Read the storefront_builder pack.
- **LIKELY CODE:** dashboard `footer_settings_page` / trust-badge / payment-logo views (~5397-5567).

## Recipe: Change section-scoped placements (Hero / Banner / Story)
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md) (M11 dual media; FK into StorefrontSection).
- **⚠️ Cross-domain:** placements FK into `storefront_builder.StorefrontSection` (CASCADE);
  `storefront_builder.layout_service` clones them on publish/restore. Changing placement fields may
  affect the layout clone path.
- **⚠️ M11 dual media:** both legacy ImageField and MediaAsset FK exist; `_resolve_placement_media_url`
  handles fallback. Do not assume a single media field.
- **LIKELY CODE:** dashboard `hero_*` / `banner_*` views; `storefront_builder` media clone.

## Recipe: Introduce a content write service (DR-2 territory)
- **BLOCKED BY DR-2.** This is exactly the open decision. Do not create a content service
  speculatively; document the need and leave DR-2 OPEN.

## Recipe: Change media handling
- **READ FIRST:** [SERVICES](SERVICES.md) (MED-001 no-ops), [INVARIANTS](INVARIANTS.md) O2.
- **⚠️ O2:** `cleanup_reusable_media_file`/`delete_media_asset_if_unreferenced` are intentional
  no-ops. "Fixing" them to actually delete re-introduces the TOCTOU race they were written to avoid.
