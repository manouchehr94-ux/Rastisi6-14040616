# P5-W4A — Public Storefront Shell Convergence — Design Spec

**Status: DESIGN GATE — architecture/inventory/spec only. No production code, no
tests, no templates were written or modified for this round.**

## 1. Purpose

Converge the genuine legacy public-shell gaps — Wishlist and the CMS content
page — onto the canonical universal storefront shell/context, so a merchant's
published Header/Footer/Bottom-Navigation/appearance surrounds these pages
exactly as it already does Home/Listing/Product-Detail/Collection/Cart,
without moving any domain-owned business logic (Wishlist's product query,
CMS's SEO/body ownership) into `storefront_builder`.

## 2. Certified starting checkpoint

`5628d6ee31e177d0b4fa1dddad550f894bca540a` — the merged, certified P5-W3
official checkpoint on `feature/phase5-design-expansion`. Branch:
`feature/phase5-w4a-public-shell-convergence`, created exactly from this SHA
(`git merge-base HEAD 5628d6e... == 5628d6e...`, verified).

## 3. Current architecture (source-verified)

Six real page types back the universal shell/render pipeline —
`StorefrontPage.PageType`: `home`, `product_detail`, `listing`, `collection`,
`search`, `cart` (`apps/storefront_builder/models.py:540-546`). Every
published `StorefrontLayoutVersion` gets exactly these six `StorefrontPage`
rows via `ensure_version_pages` — no more, no fewer.

`apps/storefront_builder/services/storefront_context_service.py::build_universal_storefront_context(request, store, page_type, page_context=None)`
is the ONE function that turns `(store, page_type)` into the full shell
context dict. It does two structurally different things depending on whether
`page_resolution_service.resolve_published_page(store, page_type)` resolves:

- **Unresolved** (`Store` has no published `StorefrontLayout`, OR — as
  discovered in this inventory, see §11 — `page_type` doesn't match any real
  `StorefrontPage` row): returns a fixed-shape dict with
  `uses_universal_shell=False` and **no** `header_variant_template`/
  `footer_variant_template` keys at all. `render_items`/`rows` come from
  `render_service.build_default_render_items(page_type, store, page_context)`,
  which safely returns `[]` for any `page_type` string not present in
  `bootstrap_service._DEFAULT_NON_HOME_SECTION_KEYS` (a plain `dict.get(page_type, [])`
  — confirmed no exception path for an unrecognized string).
- **Resolved**: returns `uses_universal_shell=True` plus `header_variant_template`/
  `footer_variant_template`/`mobile_bottom_nav_template` (resolved through
  `global_region_registry` via `render_service.store_appearance_global_renderer_template`),
  `store_appearance`, `top_level_categories`, and the page's own
  `render_items`/`rows`/`render_containers`.

`templates/storefront_shell.html` (`{% extends "base.html" %}`) overrides
exactly two blocks — `header` and `footer` — and does so ONLY when
`uses_universal_shell` is truthy; otherwise `{{ block.super }}` renders
`base.html`'s own hardcoded legacy header/footer, unchanged. Every other
`base.html` block (`title`, `meta_description`, `robots_meta`, `canonical`,
`og_tags`, `extra_css`, `content`, `structured_data`, `extra_js`,
`storefront_attribution`) is untouched by `storefront_shell.html` — a page
extending it keeps 100% control of everything except header/footer.

## 4. Canonical owners (reused, never duplicated)

| Concept | Canonical owner |
|---|---|
| Universal shell context | `apps/storefront_builder/services/storefront_context_service.py::build_universal_storefront_context` |
| Shared public shell template | `templates/storefront_shell.html` |
| Header/Footer/Bottom-Nav variant resolution | `apps/storefront_builder/global_region_registry.py` via `render_service.store_appearance_global_renderer_template` |
| Page/section rendering | `apps/storefront_builder/services/render_service.py` |
| Published-page resolution | `apps/storefront_builder/services/page_resolution_service.py` |
| Tenant/Store resolution | `apps/stores/resolution.py` (`resolve_store_for_storefront` for public views) |
| Ready Template registry | `apps/storefront_builder/layout_preset_registry.py` (untouched — W4A carries zero Ready-Template data) |
| Product card | `apps/catalog/templates/catalog/partials/product_card.html` (already reused by Wishlist) |

W4A introduces **zero** new items to this table. §11 defines a bounded
extension **inside** `build_universal_storefront_context` itself — not a new
function, not a new file, not a new owner.

## 5. Full public-surface inventory summary

See `docs/qa_evidence/storefront_design_engine/phase5/w4a_public_shell_convergence/public_surface_inventory.md`
for the full table. Summary: **13** full-page public surfaces inventoried
across `catalog`, `cart`, `customers`, `content`, `orders` (no separate
`search` app — it's `catalog.product_list` with a query string; no live
public surface in `storefront_builder`/`blog`). **7** Class A, **4** Class B,
**2** Class C. `apps.portal` (platform marketing/owner-account site) and
`apps.dashboard` (merchant admin) are explicitly out of scope — neither is a
per-Store shopper-facing surface.

## 6. Classification rules applied

- **Class A**: the view calls `build_universal_storefront_context` (or is a
  documented, source-cited exception like `home_visual.html`) AND the
  template's chrome ultimately comes from the shared Header/Footer/Bottom-Nav
  partials.
- **Class B**: NOT classified by "extends base.html" alone. Every Class-B
  item required a specific, cited reason: authenticated account workspace,
  order-code-scoped security/receipt content, or a transaction funnel that
  deliberately reduces chrome. All four Class-B candidates were already named
  as such in the authoritative plan (`2026-09-15-phase5-converged-completion-plan.md:286`)
  and independently re-verified from source in this round (see inventory
  table's Evidence column) — none were assumed.
- **Class C**: shopper-facing, expected to inherit the merchant's published
  chrome, currently bypasses `storefront_shell.html` AND `build_universal_storefront_context`
  entirely. Both confirmed candidates satisfy every element of the gap
  definition (§8 of the task brief), not just "extends base.html."

No item was found that could not be classified from source — **NEEDS
ARCHITECT DECISION: NONE**.

## 7. Confirmed Class-C gaps

### Wishlist — `apps/customers/views.py::wishlist_list` (`:25-36`)

Does not resolve a `Store` at all today (no `resolve_store_for_service`/
`resolve_store_for_storefront` call), does not call
`build_universal_storefront_context`, and its template
(`apps/customers/templates/customers/wishlist.html:1`) extends `base.html`
directly. The domain body (`{% include "catalog/partials/product_card.html" %}`
loop, empty state, login-prompt state) is otherwise already correct and
canonical-reusing.

### CMS content page — `apps/content/views.py::page_detail` (`:11-17`)

Already resolves `store` via the canonical `resolve_store_for_storefront`
and already scopes the `ContentPage` lookup to that Store + `PUBLISHED`
status — the DATA-tenancy half of this gap is already correct. It simply
never calls `build_universal_storefront_context`, and its template
(`apps/content/templates/content/page_detail.html:1`) extends `base.html`
directly.

## 8. Explicit Class-B intentional exclusions

| Surface | Why intentionally non-storefront |
|---|---|
| `customers:account` (`account_home`) | Authenticated account workspace (profile/addresses), `noindex,nofollow` already set, no product/category browsing UI — an app-like surface, not a shopping page |
| `customers:account-order-detail` | Order-code-scoped, ownership-gated (`can_view`) receipt view; `noindex,nofollow`; security/audit content, not a marketing/browsing surface |
| `orders:checkout-step1` | Transaction funnel; deliberately reduced chrome to avoid distracting the shopper away from completing payment — a standard, deliberate e-commerce UX boundary; `noindex,nofollow` already set |
| `orders:payment-result` (`payment_result`/`payment_initiate`) | Final payment-attempt state, order-code-scoped; security/flow boundary, not a browsing surface |

None of these render a `<html>` document meant to look like "the merchant's
storefront" in the shopping sense — they are transactional/account screens
that share the site's base styling (`base.html`) but intentionally omit the
merchant's chosen Header/Footer/Bottom-Nav chrome. W4A does not touch them.

## 9. Data/domain ownership

W4A changes **only** the storefront envelope (Header/Footer/Bottom-Nav/
appearance chrome). Domain data keeps its existing owner, unchanged:

- **Wishlist domain** (`apps.customers`) keeps: the `Wishlist`/`Customer`
  query and its `.filter()`/`.select_related()`/`.prefetch_related()`/
  `.order_by()` shape in `wishlist_list`, the authentication/`can_view` gate,
  the empty state, the `ProductCard` iteration. **Revised per Architect
  IMPORTANT 2:** the `Store` resolved for shell purposes is ALSO used to
  scope that same query (`product__store=store`, §13/§17) — this is still a
  Wishlist-domain change made inside `apps.customers.views`, not a move of
  the query into `storefront_builder`; `storefront_builder` supplies the
  `Store` object (via the same canonical resolver every other view uses),
  it does not gain the query itself.
- **Content domain** (`apps.content`) keeps: the `ContentPage` lookup,
  `PUBLISHED`-only visibility, `store` scoping (already correct), title,
  summary, body, `effective_seo_title`/`effective_seo_description`.

`storefront_builder` owns the shell/context only — it gains no new knowledge
of Wishlist or CMS business rules.

## 10. Universal-shell data flow

```
view (customers.wishlist_list / content.page_detail)
  → resolve Store (apps.stores.resolution.resolve_store_for_storefront)
  → build domain context dict (unchanged: products/can_view, or {page: page})
  → universal_context = build_universal_storefront_context(
        request, store, <page_type>, page_context=<domain dict, optional>,
        shell_only=True,
    )
  → context = domain_context
    context.update(universal_context)   # `dict.update`, the SAME merge
                                          # pattern every existing canonical
                                          # view already uses (see
                                          # catalog.views.product_detail:565-566
                                          # / collection_index:632, etc. — no
                                          # second merge policy invented here).
                                          # Python's `dict.update` means the
                                          # LATER argument's keys win on
                                          # collision — universal_context's
                                          # keys are therefore canonical/
                                          # reserved and MUST NOT be reused as
                                          # domain-context keys. Verified: the
                                          # domain dicts' key sets
                                          # ({"products","can_view"} for
                                          # Wishlist; {"page"} for CMS) are
                                          # disjoint from every key
                                          # build_universal_storefront_context
                                          # returns (§3's dict-shape list) —
                                          # zero collision today. §18 adds a
                                          # regression assertion for this.
  → render(request, <template extending storefront_shell.html>, context)
```

`page_context` is passed through unchanged to
`render_service.build_page_render_items`/`build_default_render_items` for
context-aware Universal Renderer sections; Wishlist/CMS have no Universal
Renderer sections of their own (§11), so `page_context` is not required for
correctness here, but is passed anyway for forward consistency with every
other canonical view's call shape.

## 11. `page_type`/context-service architectural conclusion

**This is the key finding of this round.** Wishlist and CMS do not
correspond to any of the six real `StorefrontPage.PageType` values, and
naively reusing an existing one is wrong on both sides of the publish state:

- Reusing a **real** page_type (e.g. `home` or `cart`) would make
  `resolve_published_page` return that OTHER page's own `StorefrontPage` row
  — its own `render_items`/`rows`, computed from sections the merchant
  composed for a completely different page — silently leaking foreign
  section content into `page_context`/`rows` (wasted queries at minimum;
  wrong domain content at worst, if the template were ever to render `rows`).
- Passing a **synthetic** string (e.g. `"wishlist"`) through the EXISTING
  code path degrades to the **unresolved** branch even when the Store DOES
  have a published layout — `resolve_published_page` catches
  `StorefrontPage.DoesNotExist` and returns `_UNRESOLVED`
  (`page_resolution_service.py:97-101`), which means `uses_universal_shell`
  becomes `False` and `header_variant_template`/`footer_variant_template`
  are **absent from the dict entirely**. This would silently break exactly
  the requirement W4A exists to satisfy — the merchant's published Header/
  Footer would never appear on Wishlist/CMS even after "convergence."

**REVISED per Architect IMPORTANT 1** — the first draft of this spec
proposed inferring shell-only behavior implicitly ("`page_type` not in
`PageType.values`"). Rejected: `resolve_published_page`'s own fail-safe
design principle is that an invalid `page_type` string means "unresolved,"
full stop — including a *typo* in a real page_type (e.g. `"prodcut_detail"`).
An implicit inference rule would silently reinterpret that exact failure
mode as "this is a legitimate shell-only domain page" instead of the
programming error it actually is. Shell-only behavior must be **requested
explicitly by the caller**, never inferred from the shape of the string.

**Conclusion — explicit, additive keyword parameter, decided now, inside the
canonical context service:**

```python
def build_universal_storefront_context(
    request, store, page_type, page_context=None, *, shell_only=False,
):
    ...
```

- **Every existing caller is unchanged** — `shell_only` defaults to `False`,
  and with `shell_only=False` the function's behavior is **byte-for-byte
  identical** to today, for every `page_type` value, valid or invalid
  (including the typo case above, which still degrades to the unresolved
  shape — RED test 3, §18). This is not a new code path for existing
  callers; it is an unused default.
- **Wishlist calls it with `page_type="wishlist", shell_only=True`.** **CMS
  calls it with `page_type="content_page", shell_only=True`.** These two
  literals are non-model string labels — used ONLY as a dict key/label,
  never persisted, never validated against `PageType.choices` (§23).
- **When `shell_only=True`:** the function NEVER calls
  `resolve_published_page` (so no `StorefrontPage` lookup of any kind
  happens, and no foreign page's sections can ever be resolved — RED test
  4, §18). Instead it asks only "does this Store have a published layout at
  all?" via the ALREADY-EXISTING `page_resolution_service.get_published_layout(store)`
  (store-only lookup, no `page_type` involved, already used elsewhere in
  this exact module family).
  - **Published Store:** returns the **same published-shape dict** as
    today's resolved branch — `uses_universal_shell=True`, real
    `header_variant_template`/`footer_variant_template`/`mobile_bottom_nav_template`,
    real `store_appearance`, real `top_level_categories` — but with
    `storefront_page=None`, `render_items=[]`, `rows=[]`,
    `render_containers=[]`, `use_container_layout=False` (there is no
    per-version `StorefrontPage` row backing a domain-owned page, so there
    is nothing to resolve sections for — the domain view supplies 100% of
    its own body markup, matching §9) — RED test 1, §18.
  - **Unpublished Store:** falls through to **today's unchanged**
    unresolved-shape branch (already proven safe — `build_default_render_items`
    returns `[]` for an unrecognized `page_type` via a plain
    `dict.get(..., [])`, no exception path) — RED test 2, §18.
- **When `shell_only=False`** (the default, every existing call site): the
  function behaves exactly as it does today, unconditionally — a `page_type`
  not in `StorefrontPage.PageType.values` still degrades to the unresolved
  shape via `resolve_published_page`'s existing `StorefrontPage.DoesNotExist`
  fail-safe, published Store or not. No inference, no exception.

**No duplicated published-context assembly:** the published-shape dict
(`uses_universal_shell=True` plus `header_variant_template`/
`footer_variant_template`/`mobile_bottom_nav_template`/`store_appearance`/
`top_level_categories`) is assembled by ONE private helper inside
`storefront_context_service.py` — e.g. `_build_published_shell_context(request, store, version, page, page_context)`
— that both the normal resolved branch and the new `shell_only=True`
branch call, with `page=None` in the `shell_only` case (so `render_items`/
`rows`/`render_containers`/`use_container_layout` naturally reduce to their
empty defaults instead of duplicating that logic a second time). This is
private implementation factoring inside the SAME canonical owner, not a
second context authority — it is not importable/callable from outside this
module, and no other module gains a new dependency.

This is entirely additive to the existing function, in the existing file,
using an existing helper (`get_published_layout`) plus one new private
helper local to the same file. It creates:

- **NO** new `StorefrontPage.PageType` member (so **no** `AlterField`
  migration for the `choices=` metadata — see §23).
- **NO** new context-builder module (`wishlist_storefront_context`,
  `content_storefront_context`, `public_shell_context_service`, or similar —
  forbidden by the task brief and unnecessary given the above).
- **NO** new shell template.
- **NO** duplicated published-context assembly logic (one private helper,
  shared by both branches).

## 12. Fallback behavior

Defined for both cases, and unchanged from today's proven behavior in the
"no published layout" case:

- **A. Store WITH a published universal storefront:** Wishlist/CMS render
  the same Header/Footer/Bottom-Nav variants as every other page on that
  Store, per §11's bounded extension.
- **B. Store WITHOUT a published universal storefront:** `build_universal_storefront_context`
  takes its existing unresolved branch unchanged — `uses_universal_shell=False`,
  and `storefront_shell.html`'s `{{ block.super }}` renders `base.html`'s own
  hardcoded legacy header/footer (the same header/footer every other
  unpublished-Store page — Listing, Product Detail, Cart — already gets
  today). Wishlist/CMS remain fully usable; their own domain body/state is
  entirely independent of publish state, exactly as it is today.

Neither page is made to depend on a published Ready Template — an
unpublished Store's Wishlist/CMS pages work exactly as they do right now,
just wrapped in `storefront_shell.html` instead of `base.html` directly
(functionally identical in that state, since `storefront_shell.html`
delegates to `base.html`'s own header/footer whenever `uses_universal_shell`
is false).

## 13. Wishlist design

**View (`wishlist_list`):** add `store = resolve_store_for_storefront(request)`
(the same resolver every other public view in `catalog`/`cart`/`content`
already uses) as the first line. Merge
`build_universal_storefront_context(request, store, "wishlist", shell_only=True)`
into the context alongside the existing `{"products": products, "can_view": can_view}`,
using `dict.update` per §10.

**REVISED per Architect IMPORTANT 2** — the product query itself changes,
narrowly. Today:

```python
items = (
    Wishlist.objects.filter(customer=request.user.customer_profile)
    .select_related("product", "product__brand")
    .prefetch_related("product__images")
    .order_by("-created_at")
)
```

`Customer` is a single global identity (no `store` FK — see `apps/customers/models.py:7-52`);
`Wishlist` links `customer` → `product` with no `store` FK of its own
(`apps/customers/models.py:250-264`); `Product` is Store-owned. So today a
customer's full wishlist can already contain products from multiple Stores,
and `wishlist_list` renders ALL of them regardless of which Store's site the
customer is currently browsing — while `wishlist_toggle` (the write path)
already rejects adding a foreign Store's product by slug 404
(`test_wishlist_store_isolation.py`). W4A is already introducing the current
`store` into this view for shell purposes, and tenant isolation is a
mandatory W4A gate — leaving the read path unscoped while the write path is
scoped is an inconsistency this workstream must not ship. The minimal fix,
confined to this one queryset's `filter()`:

```python
items = (
    Wishlist.objects.filter(customer=request.user.customer_profile, product__store=store)
    .select_related("product", "product__brand")
    .prefetch_related("product__images")
    .order_by("-created_at")
)
```

This is the **only** change to Wishlist domain logic in W4A. Explicitly
preserved: no `Wishlist`/`Customer` model change, no migration (a `FilteredRelation`-free
`product__store=store` filter on an existing FK path requires none), no new
Wishlist service, no recommendation logic. Explicitly NOT done: `wishlist_list`
does not adopt `storefront_visible_products`/`publicly_visible_products` or
any other canonical visibility filter — that helper is already used
elsewhere in this same file (`wishlist_toggle`, `apps/customers/views.py:42`)
but NOT by `wishlist_list` today, so adopting it here would be a genuine
visibility-semantics change outside this fix's minimal scope, not merely a
Store-scoping fix. Product active/public visibility semantics for the
listing itself are unchanged — only which Store's products are eligible to
appear changes (§18 RED tests A-C).

**Template (`customers/wishlist.html`):** change `{% extends "base.html" %}`
to `{% extends "storefront_shell.html" %}`. Keep `{% block robots_meta %}`
(already `noindex,nofollow` — preserved verbatim, see §16 for why this is
safe), `{% block title %}`, `{% block extra_css %}`, and the entire
`{% block content %}` body (breadcrumb, empty/login-prompt/populated states,
the existing `{% include "catalog/partials/product_card.html" %}` loop)
unchanged. No `header`/`footer` block override needed — `storefront_shell.html`
supplies those.

**Behavior change to flag explicitly:** today, `wishlist_list` never 404s on
an unresolvable Host (it never resolves a Store). After this change, an
unresolvable Host will 404 the Wishlist page too, matching every other
public page's behavior (`resolve_store_for_storefront` raises `Http404` via
`CompatibilityFallbackUnavailableError`, per `apps/stores/resolution.py`).
This is a deliberate consistency fix, not a side effect to hide — call it out
in the PR description, alongside the read-scoping fix above.

## 14. CMS design

**View (`page_detail`):** already resolves `store` correctly. Compute
`universal_context = build_universal_storefront_context(request, store, "content_page", shell_only=True)`,
then `context = {"page": page}; context.update(universal_context)` (per §10's
merge semantics), and pass `context` to `render`.

**Template (`content/page_detail.html`):** change `{% extends "base.html" %}`
to `{% extends "storefront_shell.html" %}`. Keep `{% block title %}`,
`{% block meta_description %}`, `{% block extra_css %}`, and `{% block content %}`
(the `page.title`/`page.summary`/`page.body` markup) byte-for-byte unchanged.
No `robots_meta` override exists today and none is added — CMS pages stay
indexable, unlike Wishlist/account pages.

## 15. Additional genuine gap design

None found beyond Wishlist and CMS — the inventory in §5/§7 is exhaustive
for this checkpoint. If a reviewer identifies another candidate, it must go
through the same Class A/B/C test in §6 before being added to W4A's scope.

## 16. Alternatives considered

**Option A (recommended, selected):** inventory-driven convergence through
the existing universal context/shell owner, extended minimally (§11) to
support domain-owned shell-only pages. Confirmed to require zero new owners,
zero migrations, and keeps both domains' business logic under its existing
owner — CMS's is fully untouched; Wishlist's gains exactly one narrow
Store-scoping filter (§13/§17), made inside `apps.customers.views` itself,
required to keep the read path consistent with the already-Store-scoped
write path.

**Option B — blindly convert every direct-`base.html` public template:**
rejected. This would sweep in `customers/account.html`, `customers/order_detail.html`,
`orders/checkout_step1.html`, `orders/payment_result.html` — all four of
which deliberately omit merchant browsing chrome for security/conversion
reasons (§8). Converting them would silently change UX contracts the plan
never asked to change and risks reintroducing distracting navigation into a
payment flow.

**Option C — repair only the already-known Wishlist/CMS pages without a
full inventory:** rejected. Without the inventory in §5, there is no way to
prove W4A actually converged every genuine gap, nor to prove the four
Class-B pages were excluded on purpose rather than by omission. The task
brief's own point of this round is proving coverage, not just fixing the two
pages already named in the plan.

**Selected: Option A**, exactly as scoped in §11-§14.

## 17. Security/tenant rules

- **Shell context tenant isolation:** `build_universal_storefront_context`
  already takes `store` as an explicit argument and every value it returns
  (header/footer/bottom-nav templates, `store_appearance`, `top_level_categories`)
  is derived from that `store` alone — there is no code path in this
  function, today or after §11's extension, that can read another Store's
  published layout. The existing `SharedPageShellTests`-style pattern
  (`apps/storefront_builder/tests/test_page_shell.py`) and the existing
  `WishlistToggleCrossStoreTests` pattern (`apps/customers/tests/test_wishlist_store_isolation.py`
  — two real Stores, two verified `StoreDomain`s, distinct `HTTP_HOST`s) are
  the reusable harnesses for proving "Store A shell cannot leak into Store B
  Wishlist/CMS" (§20).
- **Wishlist product-query scoping (REVISED per Architect IMPORTANT 2 — no
  longer out of scope):** `wishlist_list`'s product query gains
  `product__store=store` (§13) so that the READ path is scoped exactly like
  the WRITE path (`wishlist_toggle`) already is. A global `Customer`'s
  wishlist may still contain rows for products from multiple Stores (that
  fact is unchanged — `Wishlist`/`Customer` still have no `store` FK, §9);
  what changes is that any single **render** of the Wishlist page shows only
  the rows whose product belongs to the Store currently being browsed. This
  is the minimum fix that makes the read path consistent with the write
  path and with every other tenant-scoped view in this codebase — it does
  not broaden product visibility (§13), does not touch the `Wishlist`/`Customer`
  models, and does not introduce any new domain concept (no "primary Store"
  on `Customer`, no cross-Store wishlist merging/UI). §9's "Wishlist domain
  owns the wishlist product query" statement still holds — W4A does not move
  this query into `storefront_builder`; it only adds the Store filter that
  domain-consistency already demanded.
- **CMS tenant scoping:** already correct and untouched — `ContentPage`
  lookup is `store`-scoped and `PUBLISHED`-only (`apps/content/views.py:14-16`).

## 18. TDD RED matrix (to be written in the implementation round, not now)

### `build_universal_storefront_context` shell-only contract (§11) — write these FIRST

| # | Scenario | Expected RED reason today |
|---|---|---|
| 1 | `shell_only=True` + published Store ⇒ canonical shell works | `shell_only` parameter does not exist yet |
| 2 | `shell_only=True` + unpublished Store ⇒ today's legacy fallback shape (`uses_universal_shell=False`, no `header_variant_template` key) | same — parameter does not exist yet |
| 3 | An invalid **normal** `page_type` (e.g. `"prodcut_detail"`, a typo) with `shell_only=False` (the default) on a published Store still returns the unresolved shape, unchanged from today — proves no implicit "unknown page_type ⇒ shell-only" inference was introduced | should PASS unchanged once `shell_only` defaults to `False` — a regression guard proving existing callers are byte-for-byte unaffected, not new RED |
| 4 | `shell_only=True` never resolves or references ANY `StorefrontPage` row (assert zero `StorefrontPage.objects` queries with `page_type` in the SQL captured via `assertNumQueries`/query-log inspection, or equivalently assert `storefront_page is None` in the returned dict and that a decoy `StorefrontPage` for a real page_type on the same Store is never touched) | proves no foreign page's sections can leak into a shell-only context |

### Wishlist

| # | Scenario | Expected RED reason today |
|---|---|---|
| A | Published-universal Store: Wishlist renders the canonical Header | `wishlist_list` never calls `build_universal_storefront_context`; no `header_variant_template` in context |
| B | Canonical Footer present | same as A |
| C | Canonical Bottom Navigation present where the contract says applicable | same as A (`mobile_bottom_nav_template`) |
| D | Empty wishlist domain state preserved | should already pass unchanged — regression guard, not new RED |
| E | Populated wishlist `ProductCard`s preserved | should already pass unchanged — regression guard |
| F | Anonymous/not-`can_view` state preserved | should already pass unchanged — regression guard |
| G | Store A shell cannot leak into Store B Wishlist | new: two real Stores + verified `StoreDomain`s (reuse `test_wishlist_store_isolation.py`'s fixture shape), assert Store B's header/footer variant never appears when browsing Store A's Wishlist |
| H (REVISED, two-Store read isolation) | A single global `Customer` has `Wishlist(Product A @ Store A)` AND `Wishlist(Product B @ Store B)`. **GET Wishlist on `HOST_A`:** Product A visible, Product B absent. **GET Wishlist on `HOST_B`:** Product B visible, Product A absent. Reuses `test_wishlist_store_isolation.py`'s exact two-Store/verified-`StoreDomain`/distinct-`HTTP_HOST` fixture pattern (`HOST_A`/`HOST_B`, `_verified_domain`); no `request.store` mocking. | `wishlist_list`'s query has no `product__store` filter today — both products would appear on both hosts |
| I | Shell for `HOST_A` is Store A's shell only; shell for `HOST_B` is Store B's shell only (combined with H in the same two-Store fixture) | same root cause as G, exercised together with the read-isolation fixture |

### CMS

| # | Scenario | Expected RED reason today |
|---|---|---|
| A | Published page renders canonical Header/Footer/Bottom-Nav | `page_detail` never calls `build_universal_storefront_context` |
| B | Body remains exact CMS page content | regression guard |
| C | `effective_seo_title` preserved | regression guard (already covered by `ContentPageStorefrontViewTests.test_seo_title_in_html`) |
| D | `effective_seo_description` preserved | regression guard |
| E | Unpublished page remains inaccessible (404) | regression guard (already covered by `test_draft_page_returns_404`) |
| F | Store A's CMS page cannot resolve on Store B | regression guard — `page_detail` is already Store-scoped; assert this survives the shell change |
| G | No shell context from another Store | new — same two-Store harness as Wishlist G/I |

### Fallback Store (no published R4/universal layout)

| # | Scenario |
|---|---|
| A | Wishlist/CMS pages still render (200, not 500) if the Store has no published layout |
| B | Domain body/state (products, empty state, CMS title/body) remains usable and unchanged in that state |

## 19. Focused/regression plan

**Focused (new/changed behavior):** `apps/customers/tests/test_wishlist_views.py`,
new Wishlist-shell tests (co-located or a new `test_wishlist_shell_convergence.py`),
`apps/content/tests/test_content_pages.py` (`ContentPageStorefrontViewTests`),
new CMS-shell tests.

**Regression (must stay green, run in the implementation round):**
- `apps/customers/tests/` (all — `test_wishlist_views.py`,
  `test_wishlist_store_isolation.py`, `test_account_views.py`, `test_auth_views.py`, `test_models.py`)
- `apps/content/tests/` (all — `test_content_pages.py`, `test_footer_config.py`,
  `test_navigation.py`, `test_mobile_nav_drawer.py`, `test_social_links.py`, etc.)
- `apps/storefront_builder/tests/test_page_shell.py`,
  `test_render_service.py` (the shell/context/render-service suites
  W4A's bounded extension touches)
- `apps/catalog/tests/` public-shell-adjacent suites (header/footer/nav,
  `test_g2_listing_context_and_chips.py`) — regression guard that Class-A
  pages are untouched
- Tenant/security: `apps/stores/tests/test_resolution.py`

Not required for the first focused GREEN step: the full 3210-test
`apps.storefront_builder.tests` suite — but the eventual W4A PR review must
include a base-comparison against the certified checkpoint if any broad,
unexplained failures appear (same discipline as W1-W3).

## 20. Browser QA plan

Reuse the existing Playwright infrastructure
(`tools/storefront_builder_r4_qa/` and/or `tools/storefront_builder_qa/`) —
no second harness. Scenarios:

**Wishlist:** anonymous/login-required state, empty authenticated wishlist,
populated wishlist (reusing an existing ProductCard-bearing Store fixture).

**CMS:** one published content page.

**Viewports:** 1440×900, 768×1024, 390×844. **All:** RTL, no horizontal
overflow, Header healthy, Footer healthy, Bottom-Nav healthy where
applicable, domain content visible (products/CMS body), 0 console errors,
0 unexpected failed requests.

Use two materially different templates (e.g. `dark_digital`, `warm_boutique`
— the same pair already used for W2/W3 evidence) where practical, so the
converged chrome is proven against more than one visual identity.

## 21. Evidence plan

`docs/qa_evidence/storefront_design_engine/phase5/w4a_public_shell_convergence/`
(this same directory) — RED, GREEN, focused, regression, browser QA JSON +
screenshots, repo gates, architecture-duplication gate, exactly the
established W1-W3 evidence convention. No new evidence directory scheme.

## 22. Zero-migration rule

Confirmed: §11's bounded extension touches only `storefront_context_service.py`
(the new `shell_only` keyword parameter, the private `_build_published_shell_context`
helper, and reusing the existing `page_resolution_service.get_published_layout`)
— no model field changes, no new `StorefrontPage.PageType` member, no schema
change of any kind. `page_type` stays a plain Python string parameter, never
written to `PageType`'s `choices=` metadata. `apps/customers/views.py`'s
`product__store=store` filter addition (§13) is an ORM filter on an existing
FK path, not a schema change. **Expected: MIGRATIONS = 0.**
If implementation reveals this is not achievable as designed, the
implementer must STOP and record **ARCHITECTURE ESCALATION REQUIRED** rather
than add a migration.

## 23. Architecture duplication gate

| Forbidden duplicate | Introduced by this design? |
|---|---|
| Second public storefront shell | NO — reuses `storefront_shell.html` |
| Second global storefront context builder | NO — explicit `shell_only` keyword parameter on the existing `build_universal_storefront_context`, not a new function/module |
| Duplicated published-context assembly (two copies of the header/footer/bottom-nav/appearance projection logic) | NO — ONE private helper (`_build_published_shell_context`) inside `storefront_context_service.py`, called by both the normal resolved branch and the `shell_only=True` branch (§11) |
| Second Header/Footer/Bottom-Nav renderer | NO — reuses `global_region_registry` resolution |
| Second appearance resolver | NO — reuses `render_service.resolved_store_appearance_for_request` |
| Second Ready Template registry | NO — untouched |
| Second tenant resolver | NO — reuses `resolve_store_for_storefront` |
| Second page renderer | NO — reuses `render_service` |
| Second wishlist/product-query service | NO — the `product__store=store` filter is added directly to the existing queryset in `wishlist_list`, not extracted into a new service |
| Per-page storefront chrome logic | NO — Wishlist/CMS get the same chrome as every other page, from the same source |
| Per-domain Header/Footer copies | NO |
| Per-template shell forks | NO |
| New `StorefrontPage.PageType` | NO — deliberately avoided; `shell_only` is explicit instead (§11) |
| Implicit/inferred shell-only behavior | NO — REMOVED per Architect IMPORTANT 1; `shell_only` must be passed explicitly, default `False` |

**Gate: PASS** (by design — to be re-verified against the actual diff in the
implementation round).

## 24. Exact implementation scope (for the future round — not done now)

- `apps/customers/views.py` — `wishlist_list`: add Store resolution, add
  `product__store=store` to the existing `Wishlist` queryset filter, add the
  `shell_only=True` context merge.
- `apps/customers/templates/customers/wishlist.html` — change `extends`.
- `apps/content/views.py` — `page_detail`: add the `shell_only=True` context merge.
- `apps/content/templates/content/page_detail.html` — change `extends`.
- `apps/storefront_builder/services/storefront_context_service.py` —
  `build_universal_storefront_context`: add the explicit `shell_only`
  keyword parameter (default `False`, byte-identical behavior for every
  existing caller) and the private `_build_published_shell_context` helper
  factoring (§11).
- New/updated tests per §18-19.
- New evidence per §21.

## 25. Explicit non-goals

- No change to `customers/account.html`, `customers/order_detail.html`,
  `orders/checkout_step1.html`, `orders/payment_result.html`, or any other
  Class-B surface.
- No change to Wishlist's product-query scoping BEYOND the single
  `product__store=store` filter addition (§13/§17) — no visibility-semantics
  change, no `storefront_visible_products` adoption, no cross-Store wishlist
  UI/merging, no `Wishlist`/`Customer` model change.
- No new `StorefrontPage.PageType`.
- No implicit/inferred shell-only behavior — `shell_only` is always explicit (§11).
- No P5-W4B (50-Template Curation) or P5-W4C (All-50 Browser Certification)
  work — both remain FROZEN until W4A is reviewed, approved, and merged.
- No implementation, no RED tests, no template edits in this round.

## 26. Open questions

None. Every question the task brief raised (page-type ownership, fallback
behavior, tenant isolation, Class-B boundaries) was resolved from source in
this round (§11, §12, §17, §8), including the exact `page_type` literals
(§11, §13, §14) and the explicit `shell_only` contract (§11, revised per
Architect IMPORTANT 1) and Wishlist read-scoping (§13/§17, revised per
Architect IMPORTANT 2). No item requires Architect escalation before
implementation.

## 27. Self-review

Checked for: TBD/TODO markers (none — the draft "TBD" this spec originally
contained, the exact `page_type` literal in §11, was resolved before the
first commit), broad "unknown page type == shell-only" inference (REMOVED —
§11 now requires an explicit `shell_only` keyword, default `False`, with
existing-caller behavior byte-identical and RED test 3 (§18) proving an
invalid *normal* `page_type` still degrades exactly as it does today),
invalid-`page_type` behavior preserved (§11/§18 RED test 3), new
`StorefrontPage.PageType` (none — explicitly rejected, §11/§23), new context
builder (none — one keyword parameter on the existing function, §11/§23),
duplicated published-context assembly (none — one private helper shared by
both branches, §11/§23), ambiguous ownership (none — §9/§13/§17 name the
owner of every piece of state, including the revised Wishlist read-scoping),
duplicate authority (none — §23), second shell (none), unsupported
assumptions (every claim in §3/§11/§12/§13 is cited to a specific file/line
or an existing test), missing public surface (full inventory in §5,
cross-checked against `shop_core/urls.py`'s complete include list),
contradictory fallback rules (§12's two branches match the existing,
already-tested behavior exactly), unclear tenant boundaries (§9/§13/§17
state exactly what changes — the new `product__store=store` filter — and
what doesn't, for both Wishlist and CMS), Wishlist read scoped to current
Store (§13 — `product__store=store`), two-Store read-isolation RED test
defined (§18 Wishlist H), shell-isolation RED test defined (§18 Wishlist
G/I, CMS G), context-merge semantics corrected to `dict.update` (§10, MINOR
1), Home inventory wording corrected (see the inventory file's own changelog
note), W4B/W4C still frozen (§25).
