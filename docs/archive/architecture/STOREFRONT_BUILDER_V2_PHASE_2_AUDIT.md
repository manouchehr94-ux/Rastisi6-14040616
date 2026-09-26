# Storefront Builder V2 — Phase 2 (Single-Screen Visual Builder) Read-Only Audit

**Branch:** `claude/family-visual-fidelity-fix`
**Audited at commit:** `5a1b39f119609244f4607ed7154961bfd64b2b78` (Phase 1B handoff HEAD)
**Method:** Full reads of `apps/storefront_builder/views.py`, `apps/dashboard/urls.py` (builder routes), `services/layout_service.py`, `services/render_service.py`, `services/page_resolution_service.py`, `services/storefront_context_service.py`, `section_registry.py`, `templates/dashboard/storefront_builder/editor.html` and all its partials, `header_editor.html`, `footer_editor.html`, `history.html`, and the existing `tests/test_views.py` / `tests/test_layout_service.py` test classes.

---

## 1. Summary finding

The dashboard editor (`storefront_editor` + its htmx partials) is **entirely Home-page-only** — it predates Phase 1A/1B's `StorefrontPage` model. No URL, view, or template anywhere in the builder accepts or threads a `page`/`page_type` parameter. Four views explicitly call `draft.home_page()` (a hardcoded Home lookup): `storefront_editor`, `storefront_section_list_partial`, `storefront_section_add`, `storefront_section_reorder`. The remaining pk-scoped mutation endpoints (`settings`, `remove`, `toggle`, `collapse`, `duplicate`, `move`, `product-search`) resolve their target section via `_get_scoped_section` (store + Draft status only) and operate on `section.page` — already page-agnostic in principle, but unreachable for any page other than Home today because nothing ever creates a section anywhere else.

This is corroborated by explicit comments already in the code (`views.py:40-43`, `555-559`, `612-616`) acknowledging the limitation as a known, intentional scope boundary of Phase 1A/1B, not an oversight.

The codebase is otherwise **more advanced than the Phase 1B handoff summary suggested**: `section_registry.py` already implements a full typed registry of 22 section types (hero/banner/product/category/brand/content/structure), each with a `validate_settings`/`default_settings` pair, a shared `responsive` (Desktop/Tablet/Mobile visibility + per-device column count) contract, and a shared `destination` (typed internal/external link) contract applied uniformly via `_with_responsive`/`_with_destination` wrappers. A rich dashboard editor UI already exists (Alpine.js + htmx, no SPA framework, no build step) with: device preview toggle (Desktop/Tablet/Mobile), a fullscreen mode (pure CSS class toggle, Escape-bound), native HTML5 drag-and-drop reorder (both in the sidebar list and directly in the live preview iframe, cross-synced via `postMessage`), a settings drawer, and a non-destructive template/family candidate-preview mechanism. Much of what the master roadmap frames as later-phase work (typed block registry, responsive settings, device preview, fullscreen) is therefore already Phase-2-and-beyond-ready infrastructure — it only needed a page dimension threaded through it.

## 2. Endpoint-by-endpoint findings

| View | Page-hardcoded today? | Change needed |
|---|---|---|
| `storefront_editor` | Yes (`draft.home_page()`) | Resolve `page_type` from `?page=`, pass `page`/`page_type`/`page_types` to template |
| `storefront_preview` | Yes (via `build_render_items(draft, store)` → home only) | Resolve `page_type` from `?page=`, call `build_page_render_items(page, store)` |
| `storefront_section_list_partial` | Yes | Accept `page_type` (explicit kwarg from internal callers, or resolved from request) |
| `storefront_section_add` | Yes | Resolve `page_type` from POST, create section under that page |
| `storefront_section_reorder` | Yes | Resolve `page_type` from POST, scope `valid_ids` to that page |
| `storefront_section_remove/toggle/collapse/duplicate` | No (uses `section.page`) | Only need to forward `page_type=section.page.page_type` to the returned partial so the re-rendered list matches the section's actual page |
| `storefront_section_move` | No (uses `section.page.sections`) | Same as above |
| `storefront_section_settings`, `product_search` | No | No change — pk-scoped, page-agnostic already |
| `storefront_header_editor`, `storefront_footer_editor`, `appearance_editor`, `publish`, `discard`, `restore`, `apply_industry_layout`, `history` | N/A | Version-level by design (header/footer/appearance/publish operate on the whole `StorefrontLayoutVersion`, never a single page) — no page concept applies, no change |

Underlying model/service layer was already substantially page-aware from Phase 1A: `StorefrontPage.PageType` (six typed choices), `StorefrontLayoutVersion.home_page()`, `layout_service._clone_version_content` (clones all six pages on draft-create/restore), `render_service.build_page_render_items(page, store)`, and `storefront_context_service.build_universal_storefront_context(request, store, page_type)` (used by the six *public* routes since Phase 1B). Phase 2's job is exclusively to expose this existing page dimension in the *merchant-facing builder*, which had no page parameter anywhere in its URL/view/template surface.

## 3. Design decision: URL scheme

Chose a **query parameter** (`?page=<page_type>`) over a path segment (e.g. `/storefront-builder/<page_type>/`). Rationale:
- 16 files across the codebase (`dashboard/urls.py`, editor/history/header/footer templates, banner/hero list templates, `base_admin.html`, multiple test files) `reverse()`/hardcode the existing URL names. A path-segment change would require touching every one of them and is a much larger, riskier slice than Phase 2 needs.
- A query parameter is still "explicit in URL/state" (the master requirement) — it is bookmarkable, visible, and never silently inferred — while requiring zero URL-name/`reverse()` call-site changes; every existing `reverse("dashboard:storefront-builder-editor")` call keeps working unchanged, and simply omitting `?page=` defaults to Home, exactly matching every existing test's assumption.
- Page switching itself is implemented as a **full browser navigation** (`<a href="?page=...">`), not a client-side/htmx swap — this matches the existing simple pattern already used by `history.html`/`header_editor.html` (separate full pages, no SPA state machine) and guarantees the sidebar, canvas iframe, and Draft state can never drift out of sync with each other, which a partial htmx-only page switch would risk.

## 4. Non-goals confirmed out of scope for this slice

- Per-page-type block library restriction (which section types are offered for Product Detail vs. Cart, etc.) — not required by Phase 2 ("does not need the final complete block library yet"); today any registered section type can be added to any page, matching Home's current behavior exactly.
- Commerce-specific composition (product gallery, variant selector, cart line items as typed blocks) — explicitly Phase 5.
- Any change to `layout_service`'s version-level operations (publish/discard/restore/header/footer/appearance) — these are correctly version-scoped already and Phase 2 does not touch them.

---

Implementation of the resulting slice ("page-aware editor core") is documented in `STOREFRONT_BUILDER_V2_PHASE_2_REPORT.md`.
