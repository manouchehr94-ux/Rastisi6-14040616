# Storefront Builder V2 — Phase 1B (Routing + Rendering + Shell Integration) Implementation Report

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit for this phase:** `99e12fa631d03d038c381fdba0b8585fc565a54d`
**Status:** Implemented, **NOT executed against a live Django runtime** in this sandbox. Awaiting the owner's local test run before this phase is considered verified — same posture as every prior checkpoint on this branch.

Phase 1B connects the Phase 1A `StorefrontPage` data architecture to the real public storefront routing/rendering layer. By the end of this phase, all six page types (`home`, `product_detail`, `listing`, `collection`, `search`, `cart`) resolve through the **same** published `StorefrontLayoutVersion` and the **same** global shell contract, for any store that has published a Storefront V2 layout. Stores that have never published one are completely unaffected — every route falls back to exactly the same rendering it had before this phase.

This phase is **routing + rendering + shell integration only**. It does not build the final visual editor, does not implement drag/drop for non-home pages, does not build a full block library for commerce pages, does not migrate/remove any legacy Family, and does not touch commerce/catalog/cart business logic.

---

## 0. Evidence-level note

Per the established convention on this branch: `SOURCE_ONLY` / `SOURCE_WITH_TEST_COVERAGE` / `RUNTIME_VERIFIED` / `BROWSER_VERIFIED`. **Everything in this report is `SOURCE_ONLY`** — no Django runtime was available in this sandbox this session (no PyPI access, no cached wheel, re-confirmed). Nothing here is claimed as `RUNTIME_VERIFIED` or `BROWSER_VERIFIED`.

---

## 1. Before architecture (confirmed by the Phase 1B audit)

Full detail in `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1B_AUDIT.md`. Summary: only two templates in the entire repository (`catalog/home_visual.html`, `storefront_builder/preview.html`) ever included the shared, Family-aware shell partials (`page_shell_header.html`/`page_shell_footer.html`). Every other public route — Product Detail, Product Listing, Search (a `?q=` variant of Listing), Collection Index/Detail, Cart, and the legacy (unpublished) Home — extended `templates/base.html` directly with zero header/footer block overrides, rendering `base.html`'s own hardcoded, non-Family-aware shell. `build_render_items(version, store)` could only ever render the Home page's sections (it called `version.home_page()` internally, with no way to target any other `StorefrontPage`). The "which store has a published V2 layout" query was independently duplicated in exactly two places (`apps.catalog.views.home()` and `apps.core.context_processors._global_identity_version`).

---

## 2. New route/page resolution architecture

### 2.1 Central page resolution (`apps/storefront_builder/services/page_resolution_service.py`, new file)

- `get_published_layout(store)` / `get_published_layout_for_store_id(store_id)` — the **single** place the `uses_visual_storefront_layout=True AND published_version__isnull=False` query is now written. Both prior duplicate call sites migrated to call these.
- `resolve_published_page(store, page_type) -> ResolvedStorefrontPage` — the one central, typed resolver required by the task's Part A. Returns a `NamedTuple(version, page)` with an `is_resolved` property; both fields are `None` together (a store that has never published) or both populated together (never a half-resolved state). Never returns a Draft — if a store has no published layout, the result is unresolved, full stop; the caller decides the legacy fallback, exactly matching `home()`'s pre-existing responsibility split.

### 2.2 Central universal storefront context (`apps/storefront_builder/services/storefront_context_service.py`, new file)

- `build_universal_storefront_context(request, store, page_type) -> dict` — the single central helper required by Part B. Always returns the same dict shape (`uses_universal_shell`, `storefront_version`, `storefront_page`, `page_type`, `layout_header_config`, `layout_footer_config`, `render_items`, `top_level_categories`), whether or not the store has published anything — callers never need to branch on missing keys.
- Sets `request.storefront_appearance_version` as a side effect when a store has published — the same attribute `home()` alone used to set, now set uniformly by every one of the six routes that call this function. This is what makes global color/font/family tokens (via `apps.core.context_processors`) consistent across all six routes for a published store, without touching that context-processor's own logic.
- Tenant/store scoping is fail-closed by construction: the function only ever receives an already-resolved `store` (via each view's own pre-existing `resolve_store_for_storefront`/equivalent call) and never independently re-derives one from a Host, ID, or session.

### 2.3 Page-aware rendering (`apps/storefront_builder/services/render_service.py`, modified)

- `build_page_render_items(page, store) -> list[dict]` (new) — the real implementation, now genuinely page-aware; contains the exact same section-iteration/context-building/per-instance-caching logic the old `build_render_items` had, just parameterized on a `page` instead of hardcoding `version.home_page()`.
- `build_render_items(version, store) -> list[dict]` (kept, now a two-line wrapper: `return build_page_render_items(version.home_page(), store)`) — preserves the exact external contract both pre-existing production callers (`apps.catalog.views.home()`, `apps.storefront_builder.views.storefront_preview()`) and the entire pre-existing `test_render_service.py` suite depend on. **Neither existing caller was modified for this reason** — `home()` was changed for a different reason (see §2.4), and `storefront_preview()` was not touched at all.

### 2.4 Six page types → six routes (all in `apps/catalog/views.py` and `apps/cart/views.py`, modified)

| Page type | View | Change |
|---|---|---|
| `home` | `apps.catalog.views.home()` | Replaced the inline duplicate-query + inline context construction with one call to `build_universal_storefront_context(request, store, StorefrontPage.PageType.HOME)`. Renders `catalog/home_visual.html` with that dict directly (its shape is a superset of what the template already consumed: `render_items`, `layout_header_config`, `layout_footer_config`, `top_level_categories` — same keys, same values, now centrally produced). |
| `product_detail` | `apps.catalog.views.product_detail()` | `build_product_detail_context(...)` (commerce logic — **untouched**) is still called first; `build_universal_storefront_context(..., PRODUCT_DETAIL)`'s dict is merged into the same context via `.update()`. |
| `listing` / `search` | `apps.catalog.views.product_list()` | The existing filter/sort/paginate logic (**untouched**) still builds `qs`/`page_obj`/etc exactly as before. `page_type` is chosen as `SEARCH` if `query` (the existing `?q=` value) is non-empty, else `LISTING` — this is the one place Phase 1B makes an explicit design decision the audit flagged as not pre-existing: Search has no dedicated route, so it is mapped onto the `listing` view's own already-existing `q`-vs-no-`q` branch, not a new URL. |
| `collection` | `apps.catalog.views.collection_index()` and `collection_detail()` | Both existing collection-listing/data logic (**untouched**) merged with `build_universal_storefront_context(..., COLLECTION)`. |
| `cart` | `apps.cart.views.cart_detail()` | Existing `_cart_context(request, cart)` (**untouched** — commerce totals/pricing logic) merged with `build_universal_storefront_context(..., CART)`. This view did not previously call `resolve_store_for_storefront` at all (it resolved the store only indirectly, inside `cart_totals()`, via `resolve_store_for_service`); it now calls `resolve_store_for_storefront` explicitly, once, at the top — the same fail-closed resolver every other public route already used. This is the **one behavioral change** in this view beyond adding shell context: an unresolvable Host on the Cart page now 404s the same way it already did on every other public route, instead of only failing later inside `cart_totals`. This is flagged explicitly as a minor tightening, not something silently introduced — see §7 Known Limitations. |

---

## 3. Shared shell implementation

**`templates/storefront_shell.html`** (new file) — the one shared shell contract required by Part C. `{% extends "base.html" %}`, overriding `{% block header %}`/`{% block footer %}` with a single `{% if uses_universal_shell %}...{% else %}{{ block.super }}{% endif %}` branch each. When `uses_universal_shell` is `True` (i.e., the store has published a V2 layout), it includes the exact same `page_shell_header.html`/`page_shell_footer.html` partials `home_visual.html`/`preview.html` already used — **no new shell markup was written**, the existing Family-aware partial is reused verbatim. When `False` (legacy/never-published store), `{{ block.super }}` renders `base.html`'s own hardcoded header/footer exactly as before this phase — byte-for-byte the same markup, same context variables, same behavior.

Five templates were changed to extend this new shell instead of `base.html` directly: `catalog/product_detail.html`, `catalog/product_list.html`, `catalog/collection_index.html`, `catalog/collection_detail.html`, `cart/cart_detail.html`. **No other part of any of these five templates was touched** — every `{% block content %}`, `{% block extra_css %}`, `{% block title %}`, etc. is unchanged; only the `{% extends %}` target line changed. `catalog/home_visual.html` was deliberately **not** migrated to this new shell template — it already included the same two partials directly, and changing it would add churn with zero behavioral difference; both mechanisms converge on the identical partials, satisfying "do NOT create six separate shells" without needing six templates to look identical at the file level.

`top_level_categories` (needed by `page_shell_footer.html`'s `fc.show_categories` block) is now computed once, centrally, inside `build_universal_storefront_context` (`_top_level_categories(store)`) — previously only `home()` computed this query; now it's available uniformly wherever the universal context is built.

---

## 4. Legacy compatibility boundary

Explicitly isolated and documented, per Part H:

- **The 11 legacy Families, `family_registry.py`, `preset_registry.py`, `appearance_registry.py` were not touched at all** — confirmed by `git diff` scope (§9). Family dispatch continues to work exactly as before, unconditionally, for both the universal-shell branch (via the reused `page_shell_header.html`/`page_shell_footer.html`, which still do `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.header_variant %}`) and the legacy branch (via `base.html`'s own shell, which was never Family-aware and remains so).
- **`storefront_shell.html`'s `{% else %}{{ block.super }}{% endif %}` branch is the entire compatibility boundary** for stores that have never published a V2 layout — a single, explicit, one-line-per-block fallback, not a parallel renderer. There is no second "legacy mode" code path anywhere else in the views or services; the boundary is exactly this one template-level branch, exactly as narrow as Part H's "put it behind a clearly named compatibility boundary" instruction asked for.
- **No 12th Family was added. No family-specific business logic was added.** No new renderer architecture was introduced — `build_page_render_items` is the same, single, existing Section Registry-driven renderer extended to accept any page, not a second implementation.

---

## 5. Files changed

### New files
- `apps/storefront_builder/services/page_resolution_service.py`
- `apps/storefront_builder/services/storefront_context_service.py`
- `templates/storefront_shell.html`
- `apps/storefront_builder/tests/test_phase_1b_page_resolution.py`
- `apps/storefront_builder/tests/test_phase_1b_render_and_context.py`
- `apps/storefront_builder/tests/test_phase_1b_routes.py`
- `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1B_AUDIT.md`
- `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1B_REPORT.md` (this file)

### Modified files
- `apps/storefront_builder/services/render_service.py` — added `build_page_render_items`; `build_render_items` is now a thin wrapper around it.
- `apps/core/context_processors.py` — `_global_identity_version` now calls the centralized `get_published_layout_for_store_id` instead of its own duplicated query.
- `apps/catalog/views.py` — `home()`, `product_detail()`, `product_list()`, `collection_index()`, `collection_detail()` all updated to call `build_universal_storefront_context`.
- `apps/cart/views.py` — `cart_detail()` updated the same way, plus the explicit `resolve_store_for_storefront` call noted in §2.4/§7.
- `apps/catalog/templates/catalog/product_detail.html`, `product_list.html`, `collection_index.html`, `collection_detail.html` — `{% extends "base.html" %}` → `{% extends "storefront_shell.html" %}` (one line each, nothing else changed).
- `apps/cart/templates/cart/cart_detail.html` — same one-line change.

### Not changed (confirmed by design and by `git diff` scope)
- No migration. No model change. No change to `apps/storefront_builder/models.py`, `family_registry.py`, `preset_registry.py`, `appearance_registry.py`, `section_registry.py`.
- No change to `apps/cart/services/*`, `apps/orders/*`, `apps/catalog/services/product_publish_service.py`, `collection_service.py`, or any pricing/inventory/variant logic.
- No change to `StorefrontLayout.OneToOneField(Store)`, or any Phase 1A ownership model (`StorefrontSection.page`, `stable_id` scope, etc.).
- `catalog/home.html` (legacy homepage template) and `catalog/home_visual.html` — untouched.
- `apps/storefront_builder/views.py` (`storefront_preview`), `apps/storefront_builder/templates/storefront_builder/preview.html` — untouched; the staff Draft preview mechanism is completely unaffected by this phase.

---

## 6. Tests added

Three new test files, ~40 test methods total, covering every one of the 14 required scenarios:

- **`test_phase_1b_page_resolution.py`** — scenarios 1-7 (all six page types resolve, each to its own correctly-typed page, all from the same published version), 9 (unpublished/draft-only resolves to nothing), 10 (publish atomically changes resolution for all six at once), 11 (tenant isolation at the resolver level).
- **`test_phase_1b_render_and_context.py`** — scenario 14 (`build_render_items` backward compatibility, both by direct assertion and by proving it's now a thin wrapper around `build_page_render_items`), 12 (empty non-home page renders zero items, no crash), 8 (`build_universal_storefront_context` returns the same header/footer/appearance source across all six page types, and the disabled/unresolved shape contract for never-published stores).
- **`test_phase_1b_routes.py`** — full HTTP-level coverage: 14 (legacy stores render every route exactly as before — status codes and template names asserted), 8 (all six real routes, hit via the test client, share the same announcement-text marker and both shell partial template names), 9 (Draft changes never leak into any of the six routes' actual HTTP responses), 12/D (existing commerce content — product name, collection name — still renders alongside the new shell), 11 (tenant isolation at the full HTTP route level, using two stores with verified custom domains).
- **13** (legacy compatibility behavior has explicit tests) is satisfied by `LegacyStoreRoutesUnaffectedTests` in `test_phase_1b_routes.py` — every one of its five tests exercises the `{{ block.super }}` compatibility branch specifically.

---

## 7. Known limitations / risks

1. **Cart's new explicit `resolve_store_for_storefront` call** (§2.4) is a minor behavior tightening: an unresolvable Host on `/cart/` now 404s immediately at the top of the view instead of only failing later inside `cart_totals()`. This should be a strict improvement (consistent with every other public route), but it was not present before this phase and is called out explicitly rather than silently bundled in.
2. **Search has no dedicated `StorefrontPage` route of its own in the URL sense** — it is still the `?q=` branch of the `listing` view, now mapped onto `StorefrontPage.PageType.SEARCH` only for the purpose of which page's header/footer/sections get resolved. If a future phase gives Search a real, distinct URL, this mapping will need revisiting.
3. **Non-home `StorefrontPage`s have no merchant-facing editor yet** — a merchant can only add sections to them today via direct service/ORM calls (as the Phase 1B tests do), not through the existing Builder UI (which still only edits Home). This is intentional and explicitly in-scope as a non-goal ("It is NOT yet the final visual editor... NOT yet full block composition for all commerce pages") but is recorded here as the most consequential Phase 2 prerequisite.
4. **`resolve_store_for_admin_host`/`resolve_store_for_admin_request`** (pre-existing, `apps/stores/resolution.py`, marked "Phase 1B" in its own docstring but not the same Phase 1B as this report — it predates this checkpoint on this branch, added by a separate line of work) is unrelated to this phase's routing changes; noted here only to avoid confusion since it shares the "Phase 1B" label in the codebase's own comments.
5. **No `StorefrontPage`-level caching was added** — `build_universal_storefront_context` runs the same "is this store published" query on every request for every route, exactly as `home()` alone used to. This is consistent with the project's own stated non-goal of avoiding premature optimization, not an oversight.

---

## 8. What Phase 2 will build next

Per the locked roadmap this checkpoint operates under:
- The single-screen visual Builder UI (page selector, block library, live canvas, inspector) — extended to actually edit the five non-home pages this phase made resolvable/renderable but not yet editable.
- A real block library for Product Detail/Listing/Collection/Search/Cart composition (this phase proves the shell is shared; it does not give merchants a way to compose blocks on these pages yet).
- Presets built on top of the now-unified shell.
- Eventual legacy Family migration/retirement, once Phase 2's block library can express what the Families currently hardcode.

---

## 9. Tests actually run, with exact results

**None.** No Django runtime was available in this sandbox this session (no PyPI access, no cached wheel — re-confirmed at the start of this session, consistent with every prior checkpoint on this branch). Every new service function, template, and test was written and then read back carefully against the actual production code it touches, and every changed/new file passed a direct `ast.parse()` + UTF-8 decode check, but this is explicitly not a substitute for running the suite.

## 10. Tests not run

All of the following, in full:
- The 3 new Phase 1B test files (`test_phase_1b_page_resolution.py`, `test_phase_1b_render_and_context.py`, `test_phase_1b_routes.py`).
- The entire pre-existing `apps.storefront_builder` test suite (to confirm zero regression — in particular `test_render_service.py`, `test_page_shell.py`, `test_public_homepage_integration.py`, and every Phase 0.5/1A test file already on this branch).
- Relevant `apps.catalog` tests (`test_collection_public_views.py`, `test_product_detail_view.py`, `test_product_list_view.py`, and any other test touching the five modified views/templates).
- `apps.cart` tests (`test_cart_views.py` in particular, given the `cart_detail` view change).
- `apps.content` tests (footer/navigation context processors were not modified, but are exercised indirectly by the shared shell partials).

---

## 11. Recommended owner-local targeted validation commands

**Run these first — do NOT run the entire project suite until these are green**, per the task's explicit instruction:

```bash
python manage.py check

python manage.py makemigrations --check --dry-run
# ^ expect "No changes detected" — this phase introduces zero model/schema
#   changes; this command should be a pure confirmation, not a discovery step.

python manage.py test \
  apps.storefront_builder.tests.test_phase_1b_page_resolution \
  apps.storefront_builder.tests.test_phase_1b_render_and_context \
  apps.storefront_builder.tests.test_phase_1b_routes \
  --verbosity 2
# ^ the new Phase 1B suite itself.

python manage.py test \
  apps.storefront_builder.tests.test_render_service \
  apps.storefront_builder.tests.test_page_shell \
  apps.storefront_builder.tests.test_public_homepage_integration \
  --verbosity 2
# ^ the most directly-affected pre-existing tests (render_service's
#   signature, the shared-shell mechanism, Home's own Draft/Published
#   isolation) — must remain green with the exact same pass count as
#   before this phase.

python manage.py test apps.storefront_builder --verbosity 1
# ^ the full app suite (all Phase 0.5/1A tests, all family/section/
#   registry tests) — strongest confirmation nothing outside this
#   phase's direct scope regressed.
```

**Only once the above are fully green**, run the broader storefront-adjacent suites:

```bash
python manage.py test apps.catalog apps.cart apps.content --verbosity 1
```

Do not run the entire 1800+-test project suite as the first validation step for this phase — the task explicitly asks for targeted validation first.
