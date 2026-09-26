# storefront_builder — Invariants

```
domain_id: D9
code_baseline: 5883a140
known_risks: M1, M12
```

## Enforced in code (VERIFIED)
1. **Publish is a pointer swap** — exactly one PUBLISHED version per layout; the previous published
   version is ARCHIVED, not overwritten.
2. **Restore never publishes** — it always creates a new DRAFT.
3. **Published/archived appearance is immutable** — `persist_store_appearance_manifest` raises
   `ImmutableStoreAppearanceError` unless the version is a DRAFT.
4. **R4 mutation is optimistic** — `base_revision` must match `edit_revision`; success increments it.
5. **Single active write surface** — R3 mutation routes fail-closed (Http404) when
   `r4_editor_enabled=True`.
6. **6 typed pages** — `StorefrontPage.ensure_version_pages` guarantees the 6 page slots
   (home/product_detail/listing/collection/search/cart); `uniq(version, page_type)`.
7. **Section keys are allowlisted** — validated against `SECTION_REGISTRY` in the service layer.
8. **Cell span 1–12** — CheckConstraint on `StorefrontCell.span`.
9. **stable_id preserved across clone/restore** — sections keep identity; duplicates get a fresh id.
10. **Edit history wiped at publish.**

## Duplication-sync invariants (M1) — must be kept true by writers
- Appearance selectors exist in the typed manifest AND mirrored `header_config`/`footer_config`
  keys; `persist_store_appearance_manifest` keeps them in sync. A writer bypassing it would break
  this.

## Parallel-mechanism caution (M12)
Three section-placement mechanisms coexist (`StorefrontCell.section` OneToOne = executing truth;
`StorefrontSection.cell` FK = parallel/future; legacy `row_key/row_span`). The **executing** truth
is `StorefrontCell.section`. Do not assume a single placement field.
