# P5-W5 Discovery — Current-State Inventory

Status: DISCOVERY ONLY — no production code changed.
Source commit: `81abb435c6421197117f8f570993b64ca485d4af` (official W4C merge checkpoint).

---

## 1. Current merchant-facing Storefront Builder

Two builder surfaces are wired into `apps/dashboard/urls.py` (mounted under `admin-portal/`), but only one is authoritative:

| | R4 (authoritative, live default) | R3 (legacy, rollback-only) |
|---|---|---|
| URL | `/admin-portal/storefront-builder/r4/` | `/admin-portal/storefront-builder/` |
| Route name | `dashboard:storefront-builder-r4-editor` | `dashboard:storefront-builder-editor` |
| View | `apps/storefront_builder/r4_views.py:523 storefront_r4_editor` | `apps/storefront_builder/views.py:113 storefront_editor` |
| Template | `.../r4/editor.html` | `.../storefront_builder/editor.html` |
| Nav | Primary "سازنده فروشگاه" dashboard nav item (`base_admin.html:297-299`) | Small, deprioritized "ادیتور قدیمی (تنظیمات پیشرفته)" link (`base_admin.html:301-302`) |

R4 is definitively authoritative: `StorefrontLayout.r4_editor_enabled` (models.py:211-220) defaults `True`, with a docstring stating R4 "is now the default canonical merchant editor"; migration `0020_r4_editor_enabled_default_true.py` back-fills every existing Store. See `authority_map.md` Finding #1 for the R3/R4 duplication risk this creates.

- **Store resolution**: `apps/stores/resolution.py:277 resolve_store_for_service(request)` — never a bare `Store.objects.first()`.
- **Tenant isolation**: `apps/dashboard/decorators.py:48 staff_required` (resolves admin host → Store, requires active `StoreMembership`) + `:108 permission_required` (role check, e.g. `STOREFRONT_LAYOUT_MANAGE`). Every mutation service re-scopes by `store=` with `select_for_update()`.
- **Draft loading**: `services/layout_service.py::get_or_create_draft(store, user)`. Model: `StorefrontLayoutVersion` (status DRAFT/PUBLISHED/ARCHIVED), anchored per-Store by `StorefrontLayout`.
- **Stale-write protection**: `StorefrontLayoutVersion.edit_revision` (monotonic optimistic-concurrency token, migration `0018`). `r4_mutation_service.py:1137 _lock_active_draft` compares it to the client's `base_revision`; mismatch → `R4StaleRevision` → **HTTP 409** `{"code":"stale_revision", ...}`. All R4 write endpoints (mutate/publish/discard/reset/switch-template) enforce this. Legacy R3 form POSTs carry no revision token.
- **Preview**: (a) in-editor live iframe of the Draft with a UI-only Desktop/Tablet/Mobile switcher; (b) non-destructive Ready-Template candidate preview (`views.py:2286 storefront_template_live_preview`) — zero DB writes.
- **Publish**: `storefront-builder/r4/publish/` → `r4_views.py:1298` → `r4_mutation_service.py:1281 publish_draft` → `layout_service.py:852 publish()` — a pure atomic pointer-swap (`draft.status=PUBLISHED`, archive old published, swap FKs). No Draft content mutation happens inside Publish itself.
- **Undo/Redo**: `StorefrontEditHistoryEntry` + `edit_history_service.py`. Both R4 (`storefront_r4_history_command`) and legacy (`storefront_undo`/`storefront_redo`) delegate to the **same** shared contract `r4_mutation_service.py:1208 _run_history_command` — confirmed converged, not duplicated.
- **Controls visible to an ordinary merchant** (read from `r4/editor.html`): page switcher; Structure panel (sections/containers/layout presets); "Storefront Showcase" quick-add facade; Section Inspector; Global Design panel (appearance/header/footer + reset-to-baseline); **Ready-Template switch dropdown listing all 50 templates** + "تعویضِ قالب (حفظِ محتوا)" (switch template, preserve content); a full **Design Lab** panel (Random Mix, per-family locks, Compare, Return to original DNA, Remove theme, Apply); Undo/Redo/Discard/Publish; Desktop/Tablet/Mobile device switcher.
- **Production vs dev/QA-only**: no `settings.DEBUG` branches, no `staff_member_required` gates in `views.py`/`r4_views.py` — every merchant view is real production auth. Dev/QA-only surfaces are separate, URL-unreachable management commands (`qa_storefront_builder_r4.py`, `capture_ready_template_previews.py`).

---

## 2. Ready-Template merchant UX

| Capability | Status | Evidence |
|---|---|---|
| Merchant can see Ready Templates in Builder UI | **IMPLEMENTED** | Real page `storefront-builder/templates/` → `views.py:2194 storefront_template_gallery`, plus dashboard nav "قالب‌های آماده" and the in-editor switch dropdown |
| Can see all 50 | **IMPLEMENTED** | `a8_ready_templates.py::_SPECS` = 50 rows; `list_ready_templates()` filters `is_ready_template=True`; asserted `==50` by 3+ test files; Gallery/dropdown both iterate the full list, no slicing |
| "Show all 50" path | **YES** | No pagination/cap in Gallery template or view |
| Industry/category tags hide/restrict templates? | **NO — recommendation only** (not found as a gate). A *separate, unrelated* "industry template" catalog-install system exists (`storefront_apply_industry_layout`) — do not conflate with the 50 Ready Templates. |
| Real preview images displayed | **IMPLEMENTED** | `apps/storefront_builder/static/ready_template_previews/<key>/v<version>.webp`, 50 subdirectories on disk; SVG-schematic fallback only if a real screenshot is missing/stale |
| Enlarge/lightbox | **PARTIAL** | Thumbnail is a plain `<a target="_blank">` opening the raw image in a new tab — no in-page modal |
| Desktop/Tablet/Mobile preview per (not-yet-applied) template | **PARTIAL/MISSING at Gallery-card level** | Gallery preview links open `ready_template_live_preview.html`, a plain full-width page with no device-switcher markup. Only the in-editor R4 preview (of the *current* Draft) has the Desktop/Tablet/Mobile switcher |
| Choose + apply via real UI control | **IMPLEMENTED** | Real `<form method="post" action=...apply-preset>` with CSRF + overwrite-confirm dialog |
| Canonical preset/apply authority | **IMPLEMENTED** | `services/preset_service.py:436 apply_preset()` — see authority_map.md |
| Catalog/business data preserved | **CONFIRMED** | `preset_service.py` has zero references to Product/Category/Brand/Collection models |
| Only Draft modified, never Published | **CONFIRMED** | `apply_preset()` docstring: "never resolves/touches `layout.published_version`" |
| Provenance/DNA retained | **IMPLEMENTED** | `StorefrontLayoutVersion.template_provenance` + `template_baseline_snapshot` (models.py 286-316), written by `apply_preset()` |

**Note on a stale code comment**: `views.py:2255-2259` still says "only the 8 official Ready Templates" — contradicted by the actual `list_ready_templates()` filter and by tests. The real, current behavior is 50. This is a documentation/comment lag, not a functional gap — worth a one-line cleanup, not a W5 workstream.

---

## 3. Ready-Template Apply flow (exact mutation path)

Three legitimate entry points, **not** competing implementations — all converge on the same low-level write:

- **Path A — full Apply, from the Gallery**: form POST → `views.py:2392 storefront_apply_layout_preset` → confirm-overwrite gate → `preset_service.py:921 apply_preset_with_checkpoint` (checkpoints current Draft first) → **`preset_service.py:436 apply_preset(draft, preset)`**.
- **Path B — full Apply, in-editor, via R4 mutation dispatcher**: `{"type":"appearance.template.apply"}` → `r4_mutation_service.py:1165 apply_mutation` → `_lock_active_draft` → `_apply_appearance_template` → same **`apply_preset()`**.
- **Path C — DNA-only switch, content-preserving** (a genuinely different, documented-as-intentional operation): "تعویضِ قالب (حفظِ محتوا)" → `r4_mutation_service.py:1340 switch_template` → `preset_service.py:953 switch_template_preserving_content` → clones the Draft (preserving merchant-authored Sections/Containers) and applies only the appearance/DNA via `appearance_authority_service.apply_ready_template_appearance`.

Confirmed: single canonical low-level Apply authority; tenant protection on every path; stale-write/revision checks on Paths B/C (Path A/legacy has none); Draft locking (`select_for_update`/`@transaction.atomic`); history/checkpoint on every path; content preservation (grep-confirmed no catalog-model references in `preset_service.py`); no Public mutation before Publish; provenance recorded.

**Is this backend flow connected to a merchant-facing UI? → YES** on all three paths — real, rendered, clickable, live-nav-reachable controls, not test-only.

---

## 4. Demo Store vs real merchant Store

- Canonical Demo Store: fixed slug `rasti-mode-demo` (`RASTI_MODE_DEMO_STORE_SLUG`), seeded by `apps/stores/management/commands/seed_ready_template_fashion_demo.py` — its own docstring states it is strictly scoped to that one slug, never any real merchant Store.
- Template exploration uses **two live-data render modes**, both real (non-static, non-placeholder) renders at preview time:
  - Default preview: renders against the Demo Store's real seeded catalog.
  - `?data=merchant` mode: renders against the merchant's own real Store, resolved exclusively via `resolve_store_for_service(request)` — never accepts a Store id from request input, never falls back to Demo data, 404s rather than silently bootstrapping a Draft.
  - Gallery thumbnails are pre-captured `.webp` screenshots of the Demo Store (thumbnail purpose only) — the "preview" *links* open a live, non-mutating render.
- **Does applying a Ready Template ever copy Demo catalog/business data into a merchant's Store? → NO, verified.** `preset_service.py` (sole Apply write path) has zero references to Product/Category/Brand/Collection models. Every Ready-Template section's product/brand/category/collection content is expressed as `mode="auto"` rules (`resource_source.py`) resolved live, at render time, against whichever Store the Draft belongs to — never baked-in Demo product IDs. No cross-reference from the apply pipeline to `RASTI_MODE_DEMO_STORE_SLUG` exists.
- A separate, unrelated "industry vertical" catalog-template system (`storefront_apply_industry_layout`) is out of scope for this check and should not be conflated with Ready-Template Apply.

---

## 5. Store Appearance editing — per-family vertical slice inventory

Two appearance systems exist and both matter:
1. **Typed Design Engine** — `apps/storefront_builder/storefront_appearance/` — 11-entry `ComponentFamilyDefinition` catalog: header, mega_menu, hero, layout, product_view, card, badge, motion, footer, bottom_nav, theme.
2. **Legacy/general appearance tokens** — `StorefrontLayoutVersion.appearance_config` JSON — palette_slug, font, type_scale, radius, button_radius, density, motion, content_width, grid_density, card_shadow, card_hover, hero_style.

Both mutate through the **one** R4 mutation boundary (`r4_mutation_service.py::apply_mutation`). Draft persistence for the typed manifest lives *inside* the same `appearance_config` JSON field (not a second table), so Undo/Redo covers every family uniformly via whole-Draft snapshot. Isolation (changing one family leaves others untouched) is enforced generically by `_apply_appearance_component_update`, confirmed by `AppearanceMutationIsolationTests`.

| Family | Classification | Key detail / gap |
|---|---|---|
| **Header** | **COMPLETE VERTICAL SLICE** | Registry+Draft+mutation (`header.update`)+renderer (preview & public)+dedicated selector in editor+isolation+Undo/Redo+tests (`test_u2a_global_header_system.py`) |
| **Mega Menu** | **MISSING (as an independent family)** | Registry has exactly **one** component (`mega_menu.none.v1`) — no second option exists. No renderer consumes `component("mega_menu")` anywhere. The *real* mega-menu UI exists but is owned by specific **Header** variants, not by an independently switchable `mega_menu` family. No selector in editor.html. |
| **Hero** | **PARTIAL** | Full registry (13 variants) + renderer + Design-Lab wiring + tests, but **no persistent, always-on merchant selector** in the editor's Global Design panel — reachable only via Design Lab or whole-template Apply. (A *different* token, `hero_style`, has a UI selector but is a separate structural setting, not the `hero` family.) |
| **Layout/Composition** | **BACKEND ONLY** for the typed `layout` family (registered, 9 variants, but **zero render consumers found** — selecting a different `layout.*` key has no traced visual effect). A **separate, genuinely COMPLETE** system — per-container `layout_key` (2/3/4-column rows) — is real, wired, tested, and undoable, but answers a different question ("columns in this row") than a store-wide composition archetype. Do not conflate the two when scoping W5. |
| **Product View** | **PARTIAL** | Same shape as Hero — full registry (7 variants) + renderer + Design-Lab wiring, no persistent selector |
| **Product Card** | **PARTIAL** | Rich registry (19 variants) + renderer + tests, but family-level variant is Design-Lab/preset-only. Adjacent style toggles (shadow/hover/crossfade/zoom) **do** have real dedicated UI and could be mistaken for full card-family control. |
| **Badge/promo treatment** | **PARTIAL** | Thin registry (2 variants: none/sale) but real render wiring + tests; no standalone control outside Design Lab |
| **Motion** | **COMPLETE VERTICAL SLICE** | The only family with a real, always-visible, non-Design-Lab selector feeding directly into the typed manifest (`#r4GlobalMotion`) |
| **Footer** | **COMPLETE VERTICAL SLICE** | Registry (8 variants) + Draft + mutation (`footer.update`) + renderer + dedicated selector + tests (`test_u2b_global_footer_system.py`) |
| **Mobile Bottom Navigation** | **PARTIAL — real gap** | Real registry (7 variants) + real renderer (both preview and public), but the field (`mobile_nav_variant`) is **not** in the R4 `footer.update` allowed-patch-keys list — the canonical R4 mutation contract **cannot change it**. A selector exists **only in the legacy (non-canonical) footer editor partial**, absent from `r4/editor.html`'s footer group. Since R4 is the default editor for most Stores, most merchants land on an editor that cannot directly change this family; Design Lab is the only R4-reachable path (bottom_nav *is* randomizable there). |
| **Palette** | **COMPLETE VERTICAL SLICE** | `appearance.update` patch key `palette_slug`, dedicated selector + custom-color pickers, tests |
| **Typography** | **COMPLETE VERTICAL SLICE** | `font`/`type_scale` patch keys, dedicated selectors |
| **Density** | **COMPLETE VERTICAL SLICE** | `density` patch key, dedicated selector, tests |
| **Radius** | **COMPLETE VERTICAL SLICE** | `radius`/`button_radius` patch keys, dedicated inputs, tests |
| **Content Width** | **COMPLETE VERTICAL SLICE** (documented scope limit) | `content_width` patch key, dedicated selector; intentionally applied only to homepage-type pages, not checkout/product pages — a documented architectural decision, not a gap |
| **Theme/Occasion** | **COMPLETE VERTICAL SLICE — most thoroughly tested family** | 7 real occasions + none, dedicated `theme.apply`/`theme.clear` mutations, dedicated selectors + Apply/Clear buttons, `test_w2_theme_overlay.py` (14 test classes incl. Preview/Public parity) |

---

## 6. Design Lab inventory

**DESIGN LAB STATUS: IMPLEMENTED** — real production merchant-facing feature (not a prototype, not dead code, not spec-only).

- Core module `services/design_lab_service.py` (P5-W3): "a Design Lab candidate is a transient experiment, never a second source of truth."
- Endpoint `r4_views.py:740 storefront_r4_design_lab` — explicitly **read-only** (never writes); the actual write happens only via the separate `design_lab.apply_candidate` mutation through the normal `apply_mutation` boundary.
- Real UI in `r4/editor.html`: Random Mix, Reset, per-family lock toggle, per-family "randomize only this," Compare, Return-to-DNA, Remove Theme, Apply (disabled until a candidate exists).

| Sub-feature | Status | Detail |
|---|---|---|
| Transient Lab state | **YES** | In-memory dataclass, opaque signed `candidate_token`, never a DB row |
| Random Mix | **YES** | Scoped to 7 families (header, hero, product_view, card, footer, badge, bottom_nav) — deliberately excludes mega_menu/layout/motion/theme "so Random Mix changes visible chrome without touching page composition" |
| Per-family locks | **YES** | Client-supplied, server-validated, transient — never persisted |
| Compare | **YES** | Diffs candidate vs. committed Draft's live selections |
| Return to original DNA | **YES** | `return_to_original_dna(draft, base)` |
| Desktop/Tablet/Mobile preview (Lab context) | **YES** | Same single iframe scaled — never a second preview surface; the iframe URL carries the candidate token into the same `storefront_preview` route |
| Apply Lab state to Draft | **YES** | Re-validated for staleness server-side, materializes a single canonical `design_lab.apply_candidate` mutation, re-validated again inside the locked transaction (closing a documented TOCTOU race) |

Test coverage: `test_w3_design_lab.py` — 13 test classes. No competing static-HTML prototype or spec-only Design Lab found outside this implementation.

---

## 7. Preview systems map

Every meaning of "Preview" and the public storefront trace down to **exactly one** low-level function, `render_service.py::_build_items_from_sections`, reached via three thin, documented wrappers (`build_page_render_items`, `build_candidate_render_items`, `build_render_items`):

| # | Preview meaning | Owner | Renders via |
|---|---|---|---|
| 1 | Merchant Draft Preview | `storefront_builder`, `views.py::storefront_preview` | `build_page_render_items` |
| 2 | Design Lab Preview | Same route, `?design_lab=<token>` | Same `build_page_render_items` call, only the resolved appearance state is swapped |
| 3 | Non-destructive Template Preview (within Draft Preview) | Same route, `?preview_template=<slug>` | Same |
| 4 | Public Storefront | `storefront_context_service.py::build_universal_storefront_context` (6 call sites) | Same underlying `render_service.py` primitives |
| 5 | Ready Template Gallery Live Preview (Demo/Merchant data) | `views.py:2286 storefront_template_live_preview` | `build_candidate_render_items` — explicit docstring: "the exact same shared rendering path... not a second renderer" |
| 6 | Template Gallery thumbnails | `template_preview_service.py` | Static SVG schematic or cached real screenshot — not a page render, no conflict |
| 7 | QA/Dev screenshot tooling | `scripts/verify_*.py` | Playwright scripts driving the same production URLs — dev/QA-only, not a new renderer |
| 8 | Preview/Public parity (test-only) | `ThemeRenderedPreviewPublicParityTests`, `PreviewPublicStoreAppearanceParityTests` | Direct regression evidence for the single-renderer claim |

Global-region (header/footer/bottom_nav) rendering is likewise centralized in one function, `rendering.py::global_renderer_template`, called identically from public and preview contexts. Theme/motion/content_width/palette/radius/density/typography all flow through the one shared context processor `apps.core.context_processors.shop_settings`.

**Duplicate-renderer check — VERDICT: NO VIOLATION FOUND.** No second/competing renderer, no separately-maintained public-vs-preview template-selection logic.

---

## 8. Caveats

- Source-level tracing only; no Django test runner was available during this discovery pass, so "tests exist" means the file/class is present at this commit, not that it was re-run and confirmed passing today (the W4C checkpoint's own certification evidence already covers pass/fail status as of the merge).
- Not every one of the ~150+ registered component implementations was individually visually diffed — only that the dispatch mechanism connecting registry → renderer is real and shared.
