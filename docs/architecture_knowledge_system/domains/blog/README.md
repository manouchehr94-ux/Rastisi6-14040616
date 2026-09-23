# Domain: blog (D15) — Blog (near-dead)

```
domain_id: D15
app: apps/blog
status: CANONICAL
readiness: MISSING → (this pack is the first doc)
code_baseline: 5883a140
open_decisions: —
known_risks: D1 (POTENTIALLY_DEAD storefront wiring)
```

> **This is a deliberately small pack.** `blog` is a **near-dead** domain: a single `BlogPost`
> model administered via Django admin, with **no storefront URLs or views**. Per the task's
> "near-dead / low-documentation" instruction, this documents exactly what exists — no architecture
> is manufactured.

## What exists (VERIFIED)
- **Model:** `BlogPost(TimeStampedModel)` — `title`, unicode `slug`, `category_label`,
  `cover_emoji`/`cover_image`, `tint`, `excerpt`, `body`, `published_at`; ordered by `-published_at`
  (`apps/blog/models.py`, 1 model class).
- **Admin:** `apps/blog/admin.py` (11 lines) registers `BlogPost` — editable in Django admin
  (superuser-only, per `stores.admin_permissions`).
- **Views:** `apps/blog/views.py` is a **stub** (`from django.shortcuts import render` + a comment;
  **no views defined**).
- **URLs:** **no `apps/blog/urls.py`.** `blog` appears in `shop_core/urls.py` only inside the
  Django boilerplate example comment (`# path('blog/', include('blog.urls'))`) — it is **not**
  actually included in any URLconf.
- **Tests:** `apps/blog/tests.py` (20 LOC).
- **Services:** none.

## Status: POTENTIALLY_DEAD storefront wiring (D1)
- The **model is not orphaned** — it is reachable and editable via Django admin.
- The **storefront wiring is POTENTIALLY_DEAD** — there is no public route, no view, and no
  storefront/dashboard integration. A merchant cannot display blog posts on their storefront at
  `5883a140` (no rendering path exists).
- Verified via `grep`: `blog` is referenced in a real URLconf/include **nowhere** except the
  boilerplate comment.

## Mutation authority
`BlogPost` is written **only** via Django admin. No service, no signals, no cross-domain writers.

## Dependencies
- Uses `core.TimeStampedModel`. No other domain depends on `blog`; `blog` depends on nothing beyond
  core/admin.

## Change guide (minimal)
- **To make blog usable on the storefront** would require adding `urls.py` + views + templates +
  a render path — i.e. building the currently-absent storefront wiring. That is a feature addition,
  not a change to existing behavior.
- **Deletion/remediation decision:** none has been made. Phase 1/2 classify the storefront wiring
  as POTENTIALLY_DEAD (D1); the model itself is live in admin. **Do not delete** — that is a future,
  separately-authorized decision.

## Open decisions
None on the DR register. The only note is **D1** (POTENTIALLY_DEAD storefront wiring) — a dead-code
observation, not an architectural decision requiring resolution.

## Historical context
Root `SIX_NEW_FAMILIES_*` docs concern a storefront "families" effort, not this blog model; there is
no dedicated blog design doc (readiness MISSING). This pack is the first blog documentation.
