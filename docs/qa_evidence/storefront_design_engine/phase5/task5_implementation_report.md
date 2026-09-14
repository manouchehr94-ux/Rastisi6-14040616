# Phase 5 Task 5 Discovery Report
# Phase 5 Task 5 — High-Impact Primitive Expansion

Single canonical Task-5 implementation report (evolved from the approved
discovery audit). This is the only Task-5 report; the earlier
`task5_discovery_report.md` was renamed into this file — no competing Task-5
evidence documents exist.

## 1. Checkpoint

| Item | Value |
| --- | --- |
| Certified base SHA | `0d16b6aeda7974b7454beb844ebbdb292840e034` |
| Official branch | `feature/phase5-design-expansion` (untouched) |
| Working branch | `kiro/phase5-task5-fast-track` (from the certified SHA) |
| Final HEAD | _updated at completion_ |
| Remote branch HEAD | _updated at completion_ |
| Migrations added | **ZERO (expected)** |
| Task 6 started | **NO** |

## 2. Approved Fast-Track Architecture (Product-Owner override)

The approved master prompt SUPERSEDES the discovery classification for HDR.
Final classifications:

| Area | Classification | Complexity |
| --- | --- | --- |
| HDR — Header | **A — canonical reuse (verify only; NO new Header SettingsSchema)** | S |
| STRANS — Hero slider transition | **B — small repair (closed enum on existing slider schema)** | S |
| PDT — Product detail tabs/accordion | **C — clean a11y UI rewrite over existing data** | S–M |
| MDR — Mobile Navigation Drawer | **D — new presentation primitive (reuses canonical Menu/NAV_MOBILE + shared overlay)** | M |
| MODAL — Product Quick View | **D — new presentation primitive (reuses product_card_service + cart:add + shared overlay)** | M–L |
| PDTX — PDP trust/delivery | **C — clean UI/config repair, GATED on a Draft-aware canonical owner** | M |

Legend: A reuse-as-is · B small repair · C clean UI rewrite/reuse core · D new presentation primitive.

**HDR is explicitly NOT a new SettingsSchema authority.** The certified
architecture already has the canonical chain (R4 Global Design header selector →
`header.update` → `layout_service.validate_header_config` → Draft `header_config`
→ `appearance_authority_service.apply_header_variant` → manifest/render). HDR is
a verification task; production code changes only if a real defect is proven.

Per-area implementation sections (3–8), Overlay reuse (9), Architecture Gate
(10), Changed Files (11), Commits (12), Test Evidence (13), Django/Static Gates
(14), Browser QA (15), Deferred Scope (16), and Final Verdict (17) are appended
as each area completes.

---

# Appendix A — Approved discovery findings (current-state evidence)

The following per-area investigation is the evidence base the approved
fast-track is built on, kept for reviewer traceability. (Note: the discovery's
HDR "B" recommendation is overridden to "A" per §2 above.)

## HDR — Header R4

**Existing (works):**
- **All 22 header variants are registered and renderable.** `global_region_registry.py` `GLOBAL_HEADER_REGION.variants` = 10 named (`legacy_default` … `luxury_search`) + 12 `_A8_HEADER_VARIANTS` (lines ~183–305). 21 variant partials confirmed on disk under `templates/.../partials/global_header/` (+ `legacy_default` → `page_shell_header.html`); reusable `_shared/` partials exist (`category_mega_menu`, `search_form`, `logo`, `cart_action`, `account_action`, `wishlist_action`, `announcement_bar`, `icon`, `nav_header_items`).
- **All 22 are merchant-selectable today** via the R4 Global Design `header.update` group: a `data-r4-global-field="header_variant"` `<select>` over `global_design.header_variants` (r4/editor.html ~line 366), plus 6 toggle fields (`show_search/show_account/show_cart/show_wishlist/sticky/announcement_enabled`), announcement text/phone, and `announcement_links`/`extra_blocks` repeaters.
- **Selection + persistence is canonical.** `header_variant` lives in `StorefrontLayoutVersion.header_config` (legacy mirror), validated by `layout_service.validate_header_config` (variant validated against the registry; `show_cart=False` hard-rejected), applied by `r4_mutation_service._apply_header_update` (allowlist `_HEADER_UPDATE_ALLOWED_PATCH_KEYS`) which then syncs the typed Store Appearance manifest via `appearance_authority_service.apply_header_variant`. Read-time resolution is fail-safe (`resolve_active_global_variant` → `legacy_default`).
- Sticky/logo/search/burger/mega-menu render in `page_shell_header.html`; category mega-menu is driven by `nav_categories`.

**Missing / incomplete:**
- No **dedicated R4 `SettingsSchema`** for header-variant selection — it is a Global Design `data-r4-global-field`, not a schema field. Per the Phase-5 plan (Task 5 HDR note), the real gap the plan calls out is exactly this: variant selection is still a legacy `header_variant` config key rather than a schema-validated R4 field, following the `header_config` extra-blocks pattern.
- No configurable **Mega Menu** family (`mega_menu.none.v1` is a virtual no-op; the header mega-menu is a fixed category dropdown, not merchant-configurable). This is a Task-5-adjacent gap, not core-missing.
- No per-device responsive header UI surfaced in R4 (server accepts `responsive` key; no control renders it).

**Canonical owners (MUST reuse):** `global_region_registry.GLOBAL_HEADER_REGION` (variant registry — do NOT rebuild the 22 variants), `layout_service.validate_header_config`, `r4_mutation_service._apply_header_update`, `appearance_authority_service.apply_header_variant`, `content.Menu/MenuItem`, the `_shared/` header partials, `page_shell_header.html` renderer.

**Legacy/deletable UI:** the legacy full-page header editor (`dashboard:storefront-builder-header` + `header_editor.html`/`header_panel.html`) is the retirement candidate — the R4 Global Design header group already supersedes it. Do NOT delete the variant registry or `_shared/` partials.

**Recommended approach:** **B (small repair).** Add a canonical, schema-validated R4 field for header-variant selection (mirroring the existing `header_config` extra-blocks schema / the Task-4 capability-projection pattern) so the variant choice becomes a typed `SettingsSchema`/appearance field rather than a raw config key — without touching the variant registry or the manifest authority. Optionally retire the legacy full-page header editor.

**Classification:** B / S–M. **Risk:** MEDIUM (touches header persistence + manifest sync — canonical lifecycle).

**Tests:** existing — `test_u2a_global_header_system`, `test_u2b_global_footer_system`, `test_r4_store_appearance_mutations` (header.update, 31 test refs), `test_phase1_appearance_authority` (apply_header_variant), `test_r4_store_appearance_rendering` (safe-default/tampered). New RED: a schema/mutation test that the new typed header-variant field persists + reflects in render AND keeps the manifest mirror in sync. Regression: the appearance-manifest + header-config suites.

---

## MDR — Mobile Navigation Drawer

**Existing (works):**
- A **hamburger burger** exists (`page_shell_header.html:51`, `templates/base.html:58`) but only toggles a `hidden` class on the in-flow `<nav class="nav">` (`page_shell_header.html:168`) — a collapse/expand, **not** an off-canvas drawer.
- A **separate** mobile bottom-nav family exists and must stay separate: `GLOBAL_MOBILE_NAV_REGION` (`global_region_registry.py:427–440`), 9 variants, persisted in `footer_config.mobile_nav_variant`.
- Canonical Store-scoped menu source exists: `content.Menu/MenuItem` with a **`MOBILE` menu location** and a `NAV_MOBILE` context var (`content/context_processors.navigation_menus`). **`NAV_MOBILE` is consumed by zero templates today** (confirmed) — dead wiring ready to be used.
- Admin builder has real drawer/backdrop patterns (reference only).

**Missing:**
- No public off-canvas nav drawer (overlay + slide-in panel + backdrop).
- No public **body-scroll-lock** or **focus-trap** utility (only admin `editor.html` has `trapModalFocus`).
- `mobileNavOpen` defaults to `true` (nav open on load) — a known quirk.

**Canonical owners (MUST reuse):** `content.Menu/MenuItem` + `navigation_menus` context (already exposes `NAV_MOBILE`) — do NOT create a second menu authority. Responsive breakpoints owned by `core/static/css/layout.css` (1000/680px).

**Legacy/deletable UI:** none to delete — the current burger→`.nav` collapse can be **replaced** by the drawer (cleaner than patching the collapse). The bottom-nav family is untouched.

**Recommended approach:** **D (new primitive, UI-only).** Build one accessible off-canvas drawer (Alpine open/close + backdrop + focus-trap + `overflow:hidden` scroll-lock) that consumes the already-exposed `NAV_MOBILE` (falling back to `NAV_HEADER`/categories). It renders in the shared header, keyed to the existing 680px breakpoint. No new menu model, no second nav authority.

**Classification:** D / M. **Risk:** LOW–MEDIUM (UI/interaction; the only risk is a11y focus-trap correctness — no persistence/tenant/renderer change).

**Tests:** existing — `test_u2a_global_header_system` (burger/mobileNav assertions). New RED: a template/markup test that the drawer renders `NAV_MOBILE` items Store-scoped + accessible attributes (role/aria/focusable). Browser: open→focus-trap→escape→backdrop-close→body-scroll-lock at 390px. LOW-risk QA (UI/interaction) + one Store-scoping assertion (tenant, but menu is already scoped).

---

## PDT — Product Tabs / Accordion

**Existing (works, but not accessible):**
- The PDP **already has 3 tabs** (desc / spec / reviews) in `sections/product_description.html` via Alpine `x-data="{ tab: 'desc' }"` with `.tabline`/`.tabpane`. It is **not flat** and **not accordion**.
- Content sources are canonical and already wired via context-aware builders: `render_service._product_description_context` forwards `spec_variant_summary`, `approved_reviews`, `review_count`, `rating_breakdown` from `catalog.views.build_product_detail_context`. Description = `Product.description`; reviews = `Review` model (`is_approved`); spec table = category/brand/SKU/stock + `spec_variant_summary` (variant axes).

**Missing / incomplete:**
- **Zero ARIA/keyboard semantics** (no `role="tablist"/tab/tabpanel`, no `aria-selected/controls`, no arrow-key nav, no roving tabindex) — confirmed.
- **No accordion** and **no mobile handling**: `.tabline` uses `overflow-x:auto` (horizontal scroll), `product_detail.css` has **no `@media` queries** → the known mobile tab-overflow issue.
- True descriptive specs (`ProductAttributeValue`, `catalog/models.py`) are **not surfaced** on the PDP (spec tab shows only variant axes) — an optional enrichment, not required.

**Canonical owners (MUST reuse):** `render_service._product_description_context`, `catalog.views.build_product_detail_context` (spec/reviews/rating owners), `Review` model, `Product.description`. `product_description` is context-aware (schema-less, `_passthrough_dict`) — keep it context-aware.

**Legacy/deletable UI:** the current non-accessible `.tabline`/`.tabpane` Alpine tabs are the **replace** candidate (rewrite as one accessible widget: desktop tablist + mobile accordion sharing ONE content source), rather than patching ARIA piecemeal.

**Recommended approach:** **C (clean R4/a11y UI rewrite, reuse core).** One shared tab/accordion component fed by the existing `_product_description_context` — desktop = ARIA tablist with keyboard nav; mobile = accordion (`<details>` or ARIA), same three content panes; add the missing `@media` breakpoint. No schema/data change.

**Classification:** C / S–M. **Risk:** LOW (presentation/interaction only; data owners unchanged).

**Tests:** existing — `test_render_service.test_product_description_receives_review_and_spec_data`, `test_views.test_product_main_reaches_rendered_html`, `catalog test_product_detail_view`. New RED: markup test asserting ARIA tablist/tabpanel roles + all three panes reachable at mobile width. Browser: keyboard tab nav (desktop) + accordion reachability at 390px. LOW-risk QA.

---

## PDTX — Product Trust / Delivery

**Existing:**
- PDP `product_main.html` has a hard-coded `.guarantee` trust strip: `ضمانت اصالت کالا` (shield-check), `ارسال سریع و بیمه‌شده` / `بدون نیاز به ارسال فیزیکی` (truck / 📦, branched on `product.requires_shipping`), `۷ روز ضمانت بازگشت` (return-policy). All **hard-coded**, not merchant-editable.
- Reusable merchant-editable primitive exists: **`trust_features` section** (`TRUST_FEATURES_SCHEMA`, a `repeater` of up to 6 `{icon,title,subtitle}` items, `validate_trust_features_settings`) — but it is a generic Home feature row, not wired to the PDP strip.
- Real delivery datum exists: `ShopSettings.free_shipping_threshold` → `SHOP_FREE_SHIPPING_THRESHOLD` (core context processor).
- Named icon partial: `_shared/icon.html` (`shield-check`/`truck`/`return-policy`).

**Missing:**
- No merchant-editable **PDP-specific** trust/delivery/warranty/returns config anywhere. `product_main` is schema-less (`_passthrough_dict`, `settings_schema=None`).

**Canonical owners (MUST reuse):** the `trust_features` **schema shape** (repeater of icon/title/subtitle) as the model to imitate — do NOT duplicate its registry entry; `ShopSettings.free_shipping_threshold` as the delivery datum; `_shared/icon.html` for icons; `render_service._product_main_context` plumbing.

**Legacy/deletable UI:** the hard-coded `.guarantee` strings in `product_main.html` are the **replace** candidate → merchant-editable content.

**Recommended approach:** **C (clean UI rewrite, reuse existing settings authority).** Make the PDP trust/delivery strip merchant-editable by attaching a small `SettingsSchema` to `product_main` (reusing the `trust_features` repeater shape, NOT a new model/registry) OR sourcing from `ShopSettings`/appearance — decide via Product Owner. Keep `trust_features` as a standalone Home section. No new persistence model.

**Classification:** C / M. **Risk:** MEDIUM (adds a schema to a mandatory PDP section — validate through existing schema/mutation boundary; no new persistence).

**Tests:** existing — `test_views.test_trust_features_settings_form_saves_items`, `test_section_registry` (trust_features max_instances). New RED: schema/mutation test that PDP trust items persist + render (replacing hard-coded strings); a test that the strings are no longer hard-coded. MEDIUM-risk QA (new functionality on canonical services).

---

## MODAL — Public Quick View

**Existing:**
- Exactly **one** public overlay: the login `.overlay/.modal` (`templates/base.html:298–311`) with `@click.self` + `@keydown.escape.window` but **no focus-trap, no `role="dialog"`/`aria-modal`** — not a reusable accessible primitive.
- Canonical card data: `product_card_service.build_product_card_data` (`ProductCardData`) via `product_card_data` filter — single source for price/badge/availability/quick-add.
- Canonical add-to-cart: `cart:add` → `cart_add` (`cart/views.py:106`, `@require_POST`, server-side variant/quantity validation, `HX-Trigger` toast + OOB counters). Cards already call it via htmx.
- Public JS: Alpine + htmx; admin `#sfbAddModal` has a real focus-trap (reference only).

**Missing:**
- **No public quick-view** (confirmed — only a WordPress reference dump + planning docs mention it).
- No accessible public modal shell (focus-trap/`role=dialog`) and no modal-embeddable product body partial (the PDP body `product_main.html` is page/section-oriented).

**Canonical owners (MUST reuse):** `product_card_service`/`product_card.html` (card data), `cart:add`/`cart_add` (commerce authority — reuse verbatim, htmx + `HX-Trigger` toast), Alpine+htmx primitives. A quick-view must NOT create a second product rendering path — it should render a shared product partial/context (e.g. a trimmed reuse of the PDP gallery/price/variant context, or an htmx fragment served by an existing product view).

**Legacy/deletable UI:** none (net-new). Build the accessible public modal shell as a shared primitive Tasks 6/11 can reuse.

**Recommended approach:** **D (new primitive).** Build one accessible public modal shell (Alpine open/close + backdrop + focus-trap + scroll-lock — the same primitive MDR needs) and a quick-view that loads a product fragment via htmx from an existing product view, reusing `product_card_service` data and the `cart:add` endpoint for add-to-cart. No second product renderer, no second cart path.

**Classification:** D / M–L. **Risk:** MEDIUM (reuses canonical commerce + product data, but a new fragment endpoint/partial touches the render/data boundary — must not fork it).

**Tests:** existing — `catalog test_a8_product_card_presentations` (asserts `cart:add` present), `test_product_card_service`. New RED: quick-view fragment renders canonical card/product data + add-to-cart posts to `cart:add`; tenant-scoping of the fragment. Browser: open from card → focus-trap → add-to-cart → toast → escape/backdrop close, at all 3 viewports. MEDIUM-risk QA + one HIGH-risk tenant/commerce assertion.

---

## STRANS — Carousel transition

**Existing:**
- Slider fields (hero_banner + image_slider) are exactly: `autoplay`, `interval_ms`, `show_arrows`, `show_dots`, `loop`, `text_position`, `hero_style` (structural layout, NOT a between-slide animation). `product_section` carousel: `carousel_autoplay`, `carousel_interval_ms`, `carousel_show_arrows`, `header_position`.
- Slider mechanic: Alpine `x-show="slide === N"` in `hero_slider_body.html` (and `product_section.html`) with **zero `x-transition`** (confirmed), and `.hero-slide` CSS has **no transition/opacity/transform/@keyframes** → slides swap as an **instant hard cut**.

**Missing:**
- A merchant-editable **transition style** (fade/slide/none) is **genuinely absent** at every layer — schema, validator, Alpine JS, and CSS. It does not exist under another name (`hero_style` is layout; `MOTION_AWARE_SECTION_KEYS` is entrance/hover metadata, not per-slide).

**Canonical owners (MUST reuse):** the existing slider validators/schema (`_validate_slider_settings`, `HERO_BANNER_SCHEMA`/`IMAGE_SLIDER_SCHEMA`) and the existing Alpine slider mechanic — add ONE typed enum field and hook it to `x-transition`/a CSS class.

**Legacy/deletable UI:** none — additive only.

**Recommended approach:** **D-small (smallest typed enum).** Add one `choice` field `transition` (e.g. `none`/`fade`/`slide`) to the slider schema (via the existing schema + R4 renderer allowlist), map it to a fixed CSS class / `x-transition` preset. **No arbitrary CSS/JS** — closed enum only.

**Classification:** D / S. **Risk:** LOW (typed enum + presentation).

**Tests:** existing — `test_section_registry` (carousel defaults/clamping), `test_r4_settings_schema` (hero field list), `test_render_service` (slider defaults). New RED: schema test that `transition` is a closed enum persisted + rendered as a class; R4 inspector renders it. LOW-risk QA (visual/interaction).

---

## Shared primitives / dependency opportunities

**Share (build once, reuse):**
- **Accessible overlay primitive** (backdrop + focus-trap + `overflow:hidden` scroll-lock + escape/`@click.self`): needed by **MDR** (drawer) AND **MODAL** (quick-view). Build ONE public primitive; the login modal should ideally adopt it too. This is the single biggest reuse opportunity.
- **`_shared/` header partials + icon partial**: reused across HDR variants, PDTX icons, MDR drawer.
- **`product_card_service` + `cart:add`**: reused by MODAL quick-view and any Task-6 Showcase / Task-9 cart work.
- **Tab/accordion a11y pattern (PDT)**: a generic reusable Tabs primitive is a Task-11 family; PDT should build the shared version so Task-11 consumes it, not a PDP-only copy.

**Do NOT share despite looking similar:**
- **MDR drawer vs bottom-nav**: different families/authorities (`GLOBAL_MOBILE_NAV_REGION` vs a nav drawer) — keep separate.
- **Mega-menu (category dropdown) vs MDR drawer**: different data (categories vs Menu) and surface — do not merge.
- **`hero_style` (layout) vs STRANS `transition` (motion)**: orthogonal axes — separate fields.
- **`trust_features` Home section vs PDTX PDP strip**: same schema *shape*, but distinct instances/surfaces — reuse the shape, not the instance.

**What Task 5 should build that 6/7/8/11 reuse:**
- The accessible overlay primitive (→ Task 11 Drawer/Modal families, Task 6 Showcase quick actions).
- The a11y Tabs/Accordion primitive (→ Task 11 generic Tabs, Task 8 PDP).
- The schema-validated header-variant field pattern (→ Task 6 Showcase Header composition).

**Defer to later tasks:** configurable Mega Menu family (not in Task-5 six), Showcase (Task 6), full 50-template QA (Task 16), Theme Overlay (Task 12).

## Architecture risks

- **HIGH:** HDR + PDTX touch canonical persistence/lifecycle (header_config + manifest; a new PDP schema through the mutation boundary). Must route through `r4_mutation_service` + `layout_service`/schema validation + `appearance_authority_service`; no second persistence.
- **MEDIUM:** MODAL quick-view must reuse `product_card_service` data + `cart:add` and serve the fragment from an existing product view — risk of accidentally forking the render/product path.
- **LOW:** MDR/PDT/STRANS are UI/interaction/enum; the main risk is a11y correctness (focus-trap, ARIA) and keeping MDR from becoming a second menu authority.
- Cross-cutting: do not let the shared overlay primitive become a second modal system per feature — build it once.

## Proposed implementation order

1. **STRANS** (D/S) — smallest, self-contained typed enum; warms up the slider schema path.
2. **PDT** (C/S–M) — a11y tab/accordion rewrite; produces the shared Tabs primitive.
3. **Shared overlay primitive** (inside MDR) then **MDR** (D/M) — builds the focus-trap/scroll-lock/backdrop primitive.
4. **MODAL** (D/M–L) — reuses the overlay primitive from step 3 + card/cart authority.
5. **PDTX** (C/M) — PDP trust schema (reuses trust_features shape).
6. **HDR** (B/S–M) — schema-validated header-variant field + optional legacy-editor retirement (do last; highest lifecycle/manifest risk, benefits from settled schema patterns).

## Fast-Track QA strategy

Lightest sufficient level per area (do NOT run huge unrelated suites):

| Area | Risk tier | Focused tests | Regression | Browser |
| --- | --- | --- | --- | --- |
| HDR | MEDIUM (persistence/manifest) | new header-variant schema/mutation RED | appearance-manifest + header-config suites (`test_r4_store_appearance_mutations`, `test_phase1_appearance_authority`, `test_u2a/u2b`) | header variant switch + manifest mirror, 3 viewports |
| MDR | LOW–MED | drawer markup + Store-scoped `NAV_MOBILE` RED | `test_u2a_global_header_system` | open/focus-trap/escape/backdrop/scroll-lock @390px |
| PDT | LOW | ARIA tablist/panes RED | `test_render_service`, `catalog test_product_detail_view` | keyboard tabs (desktop) + accordion @390px |
| PDTX | MEDIUM | PDP trust schema persist+render RED | `test_views` trust_features, `test_section_registry` | PDP trust strip editable, 3 viewports |
| MODAL | MED + HIGH (commerce/tenant) | quick-view fragment reuses card data + `cart:add`; tenant-scope RED | `test_a8_product_card_presentations`, `test_product_card_service`, cart tests | open→add-to-cart→toast→close, 3 viewports |
| STRANS | LOW | `transition` closed-enum schema RED | `test_section_registry`, `test_r4_settings_schema` | slider transition visual, desktop |

HIGH-risk (security/tenant/persistence/lifecycle/renderer): the HDR manifest sync and the MODAL commerce/tenant path — full focused + relevant regression. MEDIUM (new functionality on canonical services): PDTX schema, MODAL fragment. LOW (UI/interaction/visual): MDR, PDT, STRANS — focused markup/a11y tests + one browser scenario each.

## Final recommendation

Proceed with Task 5 as **five small/medium repairs + rewrites over existing
core, plus one shared overlay primitive built once** (used by both MDR and
MODAL). Reuse every canonical authority listed; the only genuinely new
persistence is a PDP trust schema (PDTX) and one slider enum (STRANS), both
routed through the existing schema/mutation boundary. Retire (not patch) the
non-accessible PDP tabs, the hard-coded PDP trust strings, the burger-collapse
mobile nav, and optionally the legacy full-page header editor. Recommended
sequence: STRANS → PDT → MDR(+overlay) → MODAL → PDTX → HDR.

---

# Implementation log (sections 3–17)

_Populated as each area reaches GREEN. See §2 for the approved classifications._
