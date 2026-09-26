# content — Security

```
domain_id: D10
code_baseline: 5883a140
known_risks: H2
```

## Tenancy (VERIFIED)
- All content models are Store-owned (FK Store). `DestinationMixin.clean()` enforces cross-store
  ownership — a link/placement cannot point at another Store's Category/Product/Brand/Collection.
- Content CRUD runs through `dashboard` views gated by `staff_required` + `permission_required`
  (e.g. content-editor permission); scoped to `request.store`.

## Write-boundary risk (H2)
- Because content has **no write service**, the security/validation posture depends on each
  dashboard view calling `full_clean()` and enforcing Store scope. There is no single content
  service to centralize authorization/validation. A new content write path that forgets the Store
  scope or `full_clean()` would bypass content's only guards. This is part of the DR-2 concern.

## Media
- `MediaAsset` files are Store-owned. `is_referenced()` is fail-closed (treats uncertainty as
  referenced), and MED-001 cleanup is a no-op — so media is never deleted out from under a
  reference (a safety choice, O2).
- Uploaded media uses Pillow content/size validators (on the ImageField).

## Public surface
- `page_detail` renders only **published** `ContentPage`s. `newsletter_subscribe` creates a
  `NewsletterSubscriber` (dedup per store). No other public write.
