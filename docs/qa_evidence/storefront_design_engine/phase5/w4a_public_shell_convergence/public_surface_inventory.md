# P5-W4A — Public Surface Inventory

Certified starting checkpoint: `5628d6ee31e177d0b4fa1dddad550f894bca540a`
(merged P5-W3 official checkpoint). Branch: `feature/phase5-w4a-public-shell-convergence`.

**Correction (Architect spec-repair round, INVENTORY MINOR CLEANUP):** the
"Home (unpublished fallback)" row originally said its current path uses
"neither `build_universal_storefront_context` nor `storefront_shell.html`."
That was source-inaccurate — `catalog.views.home` DOES call
`build_universal_storefront_context` unconditionally, first, before
choosing the fallback; it just discards that dict for the unpublished
branch. Corrected below. The row's Class-A documented-exception
disposition is unchanged — this is a wording fix only, no new evidence
changes the classification.

Method: enumerated every `urls.py` reachable from `shop_core/urls.py` (the
public site's root URLconf — `apps.catalog`, `apps.cart`, `apps.customers`,
`apps.orders`, `apps.content`), plus a search for any other app with a public
URLconf. `apps.storefront_builder` has NO public URLs of its own beyond what
`apps.catalog`/`apps.cart` already call into (its own `admin-portal/`
namespace is the R4 editor, gated by `apps.dashboard.decorators.staff_required`
— explicitly out of scope per the plan's "Do NOT migrate admin/dashboard
pages"). There is no dedicated `search` app — search is the `catalog.product_list`
view with a query string, sharing the same URL/view/template as Listing.
`apps.blog` has a 3-line stub `views.py` and no `urls.py` — not wired into
any URLconf, not a live public surface. `apps.portal` is the **platform's own**
marketing/account site (a different product surface entirely — Rastisi-the-SaaS
selling itself, account/billing/domain management for Store owners), not a
per-Store shopper-facing storefront; out of scope for the same reason
admin/dashboard is (see "Explicitly out of scope" below).

Evidence for "current shell/context" column: grep for
`build_universal_storefront_context` in the view, and the literal first line
of the rendered template for `{% extends %}`.

## Legend

- **Class A** — canonical universal storefront (already correct).
- **Class B** — intentionally non-storefront (reduced/no merchant chrome by design).
- **Class C** — genuine legacy public shell gap (W4A repair target).
- Fragment/partial endpoints (AJAX/htmx responses, never a full HTML document)
  are listed but not classified A/B/C — they have no `<html>`/shell at all by
  design and are out of scope for "shell convergence."

## Full-page public surfaces

| Surface | Route | View | Template | Current shell/context | Classification | Evidence | W4A action |
|---|---|---|---|---|---|---|---|
| Home (unpublished fallback) | `catalog:home` | `catalog.views.home` | `catalog/home.html` | Calls `build_universal_storefront_context` (unconditionally, first — used to test `uses_universal_shell`), but the returned dict is DISCARDED for this branch in favor of a separately-built legacy context; template does not extend `storefront_shell.html` | A (documented exception) | `apps/catalog/views.py:48-120` — `home()` always calls `build_universal_storefront_context(request, store, PageType.HOME)` first; when `uses_universal_shell` is `False` it builds an entirely separate `context` dict (lines 96-119) and renders `catalog/home.html`, never reusing `universal_context`; this template predates the shell and is legacy-only content for a Store that has never published, not a merchant-designed page | NONE |
| Home (published/universal) | `catalog:home` | `catalog.views.home` | `catalog/home_visual.html` | Calls `build_universal_storefront_context`; template extends `base.html` directly | A (documented exception) | `templates/storefront_shell.html`'s own top-of-file comment: `home_visual.html` deliberately does not migrate to `storefront_shell.html` because it already directly includes the same `header_variant_template`/`footer_variant_template` partials itself — not a second shell, just a different structural path to the identical chrome | NONE |
| Product Listing / Search | `catalog:product-list` | `catalog.views.product_list` | `catalog/product_list.html` | Calls `build_universal_storefront_context` with `page_type = SEARCH` or `LISTING`; extends `storefront_shell.html` | A | `apps/catalog/views.py:395-418` | NONE |
| Product Detail | `catalog:product-detail` | `catalog.views.product_detail` | `catalog/product_detail.html` | Calls `build_universal_storefront_context`; extends `storefront_shell.html` | A | `apps/catalog/views.py:560-568` | NONE |
| Collection Index | `catalog:collection-index` | `catalog.views.collection_index` | `catalog/collection_index.html` | Calls `build_universal_storefront_context`; extends `storefront_shell.html` | A | `apps/catalog/views.py:627-645` | NONE |
| Collection Detail | `catalog:collection-detail` | `catalog.views.collection_detail` | `catalog/collection_detail.html` | Calls `build_universal_storefront_context`; extends `storefront_shell.html` | A | `apps/catalog/views.py:658-664` | NONE |
| Cart | `cart:detail` | `cart.views.cart_detail` | `cart/cart_detail.html` | Calls `build_universal_storefront_context` with `page_type = CART`; extends `storefront_shell.html` | A | `apps/cart/views.py:88-94` | NONE |
| **Wishlist** | `customers:wishlist` | `customers.views.wishlist_list` | `customers/wishlist.html` | No `build_universal_storefront_context` call at all (no `store` even resolved); extends `base.html` directly | **C** | `apps/customers/views.py:25-36`; `apps/customers/templates/customers/wishlist.html:1` | **CONVERGE** |
| **CMS content page** | `content:page-detail` | `content.views.page_detail` | `content/page_detail.html` | Resolves `store` via the canonical `resolve_store_for_storefront` but does not call `build_universal_storefront_context`; extends `base.html` directly | **C** | `apps/content/views.py:11-17`; `apps/content/templates/content/page_detail.html:1` | **CONVERGE** |
| Account home | `customers:account` | `customers.views.account_home` | `customers/account.html` | No universal context; `base.html` directly; explicit `noindex,nofollow` | B | Authenticated account workspace (profile/addresses), not a shopping surface; `robots_meta` already marks it non-indexable; no product/category browsing UI | NONE |
| Order detail | `customers:account-order-detail` | `customers.views.account_order_detail` | `customers/order_detail.html` | No universal context; `base.html` directly; explicit `noindex,nofollow` | B | Authenticated, order-code-scoped receipt view (`can_view` gate on the order's own customer); security-sensitive, single-purpose, no merchant chrome by design (matches Order-detail pattern used platform-wide) | NONE |
| Checkout step 1 | `orders:checkout-step1` | `orders.views.checkout_step1` | `orders/checkout_step1.html` | No universal context; `base.html` directly; explicit `noindex,nofollow` | B | Transaction-focused checkout funnel; deliberately minimal chrome (no header nav distractions during payment) — a standard e-commerce conversion pattern; matches the plan's own explicit Class-B candidate list | NONE |
| Payment result | `orders:payment-result` | `orders.views.payment_result`, `orders.views.payment_initiate` | `orders/payment_result.html` | No universal context; `base.html` directly | B | Security/flow boundary — final state of a payment attempt, order-code-scoped, no browsing UI; matches the plan's own explicit Class-B candidate list | NONE |

## Fragment / partial (AJAX-htmx) endpoints — not full pages, out of shell-convergence scope

| Route | View | Renders | Why excluded |
|---|---|---|---|
| `catalog:home-best-products` | `home_best_products` | `catalog/partials/product_grid.html` | Partial grid fragment |
| `catalog:product-review-create` | `product_review_create` | `catalog/partials/review_form.html` | Partial form fragment |
| `cart:add`, `cart:item-update`, `cart:item-remove`, `cart:preview` | `cart_add`, `cart_item_update`, `cart_item_remove`, `cart_preview_partial` | `cart/partials/*.html` | OOB/partial fragments, no `<html>` document |
| `customers:wishlist-toggle` | `wishlist_toggle` | `customers/partials/wishlist_button.html` | Partial button fragment (already Store-scoped — see `apps/customers/tests/test_wishlist_store_isolation.py`) |
| `customers:login`, `customers:signup`, `customers:otp-*`, `customers:logout` | various | `customers/partials/auth_forms.html`, `otp_login_body.html` | Auth widget fragments embedded in other pages' chrome, or a redirect |
| `customers:account-profile-update`, `customers:address-*` | various | `customers/partials/*.html` | Account-workspace fragments (Class-B domain, same as `account_home`) |
| `content:newsletter-subscribe` | `newsletter_subscribe` | `content/partials/newsletter_form.html` | Partial form fragment (embedded in the footer newsletter block on already-canonical pages) |
| `orders:checkout-pay`, `checkout-otp-*`, `checkout-item-*`, `checkout-set-*`, `checkout-coupon-*`, `gateway-callback` | various | `orders/partials/*.html` or redirects/JSON | Checkout-flow fragments/webhook, same Class-B domain as `checkout_step1` |

## Explicitly out of scope (not a per-Store public storefront surface)

| App | Reason |
|---|---|
| `apps.dashboard` (`admin-portal/`) | Merchant admin dashboard — explicitly excluded by the plan ("Do NOT migrate admin/dashboard pages"); gated by `staff_required`, not a shopper surface at all |
| `apps.portal` | The **platform's own** marketing site + Store-owner account/billing/domain-management portal (`portal:home`, `portal:app-home`, `portal:store-create`, `portal:billing-*`, `portal:custom-domains`, etc.) — this is Rastisi-the-SaaS-product's own site, never rendered inside any merchant's storefront envelope; same exclusion rationale as admin/dashboard, one level up the tenancy stack |
| `apps.blog` | Stub only (`views.py` is the unmodified Django scaffold comment, no `urls.py`, not included from `shop_core/urls.py`) — not a live route |
| `apps.billing`, `apps.sms` | Public but non-HTML: signature-verified webhook endpoints (`billing/`, `sms/`), never render a page |
| `sitemap.xml`, `robots.txt`, `favicon.ico` | Non-HTML SEO/asset endpoints, not shell surfaces |

## Summary counts

- Full-page public surfaces inventoried: **13**
- Class A (canonical universal storefront): **7** (Home ×2 templates, Listing/Search, Product Detail, Collection Index, Collection Detail, Cart)
- Class B (intentionally non-storefront): **4** (Account home, Order detail, Checkout step 1, Payment result)
- Class C (genuine legacy public shell gap): **2** (Wishlist, CMS content page)
- Fragment/partial endpoints inventoried (out of scope by nature): **~20** across catalog/cart/customers/content/orders
- NEEDS ARCHITECT DECISION: **NONE** — every Class-B item has documented, source-verified reasoning; no ambiguous cases were found.
