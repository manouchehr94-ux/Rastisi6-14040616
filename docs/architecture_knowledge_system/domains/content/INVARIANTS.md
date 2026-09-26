# content — Invariants

```
domain_id: D10
code_baseline: 5883a140
known_risks: H2, O2
```

## Enforced in code (VERIFIED — via model `clean()` / DB constraints)
1. **`ContentPage` published requires `published_at`** (DB CheckConstraint).
2. **`uniq(store, slug)`** for `ContentPage`; RESERVED_SLUGS blocked in `clean()`.
3. **`uniq(store, location)`** for `Menu`.
4. **Destination coherence + cross-store ownership** — `DestinationMixin.clean()` /
   `_validate_destination_store_ownership` prevents pointing a link at another Store's entity.
5. **`MenuItem` hierarchy** — max 2 levels; a child must have a destination.
6. **`uniq(store, email)`** for `NewsletterSubscriber`.
7. **`MediaAsset.is_referenced()` is fail-closed** — treats uncertainty as "referenced."

## NOT enforced by a service boundary (⚠️ H2)
- Because there is **no content write service**, invariants beyond model `clean()`/DB constraints
  are only as strong as each dashboard view remembers to call `full_clean()`. There is no
  content-domain transaction boundary for multi-object edits (e.g. menu reordering).

## Deliberate non-invariant (O2 / MED-001)
- Unreferenced media is **not** deleted (`cleanup_reusable_media_file` /
  `delete_media_asset_if_unreferenced` are no-ops). A small storage leak is accepted to avoid a
  delete/reference TOCTOU race. "Media is garbage-collected" is explicitly **not** an invariant.
