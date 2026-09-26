# content — Services

```
domain_id: D10
code_baseline: 5883a140
open_decisions: DR-2
known_risks: H2, O2
```

> **There is no content *write* service (H2).** `apps/content/` has a single `services.py` (no
> `services/` package). It contains only read/resolve helpers, a newsletter write, and the MED-001
> no-op cleanup functions. All CRUD is in `dashboard.views` (see [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md)).

## `apps/content/services.py` (VERIFIED — the complete function list)
| Function | Kind | Purpose |
|---|---|---|
| `resolve_destination_url(instance)` | read/resolve | safe-link URL for a `DestinationMixin` instance |
| `resolve_destination_context(instance)` | read/resolve | destination context dict |
| `resolve_destination_setting(store, destination)` | read/resolve | resolve a JSON-stored destination (used for `StorefrontSection.settings`) |
| `resolve_background_media_url(store, background)` | read/resolve | background media URL |
| `_category_url` / `_product_url` / `_brand_url` / `_collection_url` | read/resolve | catalog destination URL helpers |
| `_reusable_media_placement_models()` | read | placement models scanning MediaAsset references |
| `cleanup_reusable_media_file(...)` | **no-op (MED-001)** | intentionally does nothing (TOCTOU-avoidance; O2) |
| `delete_media_asset_if_unreferenced(asset)` | **no-op (MED-001)** | intentionally does nothing (O2) |
| `subscribe_to_newsletter(store, raw_email)` | **write** | the ONLY content-service write (creates `NewsletterSubscriber`) |

## Implication
- Content is resolved for rendering here; it is **written** in the dashboard view layer.
- The MED-001 cleanup functions are **live-but-inert** (called but do nothing) — a deliberate
  retention-first choice to eliminate a delete/reference TOCTOU race (O2). Media bytes/rows are
  never deleted by these functions.

## If you need a content write path
Today: add a dashboard view (the current pattern). A content service layer would be the DR-2
decision — do not create one speculatively in this phase.
