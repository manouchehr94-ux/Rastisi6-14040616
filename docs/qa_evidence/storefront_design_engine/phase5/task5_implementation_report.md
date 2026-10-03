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
| Evidence HEAD (before this report's own commit) | `e061d714098cef13123c79305d8a8c11a4342a66` |
| Final HEAD | see the report-commit SHA in the PR / `git log` (this doc is committed last; its own commit SHA is necessarily created after this line is written) |
| Migrations added | **ZERO** (`makemigrations --check` → "No changes detected"; no migration files changed vs base) |
| Task 6 started | **NO** |

> All test counts, the browser-QA result, and the changed-file list in this
> report are the state at evidence HEAD `e061d71` (the last code/evidence commit
> before the first report commit). The final PR head SHA is reported in the
> delivery response and visible on the Draft PR.
>
> **Micro-remediation follow-up.** Two more small changes landed after `e061d71`
> (still zero migrations, browser QA re-run: still **92/92**, 0 console errors):
> (a) the MODAL quick-view `@click` handler now uses Alpine `$event`
> consistently (no bare/global `event`), with a source-contract test; (b) the
> PDTX browser-QA seed helper (`tools/storefront_builder_qa/_pdtx_seed.py`) is
> now non-destructive/fail-closed. These do not change any test count or the QA
> result reported below.

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
| PDTX — PDP trust/delivery | **C — merchant-editable via the existing Draft-aware `trust_features` owner (implemented; no new model)** | M |

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

All six areas were implemented in the approved order (STRANS → PDT → MDR →
MODAL → PDTX → HDR) with strict RED→GREEN TDD, reusing canonical owners, with
**zero database migrations**.

## 3. STRANS — Hero slider transition (Classification B / S) — DONE ✅

- **Owner reused:** the existing slider schema/validator (`_validate_slider_settings`, `default_slider_settings`, `HERO_BANNER_SCHEMA`, `IMAGE_SLIDER_SCHEMA`) in `section_registry.py` and the existing Alpine slider mechanic in `hero_slider_body.html`. No new field library, no JS carousel dependency.
- **What shipped:** one closed enum `transition ∈ {cut, fade, slide}`, advanced field, **default `cut`** (byte-identical to the pre-existing instant hard cut → fully backward-compatible). `cut` keeps the exact existing `x-show` display toggle; `fade`/`slide` add a `.is-active` class + `data-hero-transition` attribute driving CSS presets. `prefers-reduced-motion` collapses `fade`/`slide` back to `cut`.
- **Files:** `section_registry.py`, `partials/hero_slider_body.html`, `apps/catalog/static/css/home.css`.
- **Tests (RED→GREEN):** `test_r4_settings_schema.py` (`SliderTransitionValidatorTests`, `SliderTransitionSchemaFieldTests`), `test_render_service.py` (`SliderTransitionRenderTests`, `SliderTransitionRuntimeContractTests`); hero field-order test updated to include `transition`.
- **Commit:** `13dddc2`.

## 4. PDT — Product detail tabs / accordion (Classification C / S–M) — DONE ✅

- **Owner reused:** `render_service._product_description_context` (unchanged data owner); `product_description` stays a context-aware, schema-less section. No second data source.
- **What shipped:** an accessible rewrite of `product_description.html` — desktop ARIA `role="tablist"/tab/tabpanel` with `aria-selected/controls/labelledby`, roving tabindex, Arrow/Home/End keyboard nav; mobile = the same tabs/panels stacked as a full-width accordion (one DOM, one Alpine state). IDs namespaced per `product.pk`. Static first-tab-active attributes give a working no-JS baseline (Alpine `:attr` bindings do not render statically). Added the missing mobile `@media` breakpoint + `:focus-visible`.
- **Files:** `sections/product_description.html`, `apps/catalog/static/css/product_detail.css`.
- **Tests (RED→GREEN):** `test_views.py::ProductDetailContextAwareSectionsPreviewTests` (ARIA roles + all three panes reachable + real-accordion structure + Persian ZWNJ + no-JS visibility).
- **No-JS progressive-enhancement fix (final micro-remediation).** A regression was found: the panels carry `class="tabpane pdp-tab-panel"` with no static `active` class, and a blanket `.tabpane{display:none}` rule (equal specificity, later in source) plus `x-cloak` hid ALL panels when JavaScript was disabled. **Fix (smallest):** removed the blanket `.tabpane{display:none}`/`.tabpane.active{display:block}` rules (kept only `.pdp-tab-panel{display:block}` visible-by-default + `.tabpane.active{animation}`), and removed `x-cloak` from the three panels. With JS off, all three panels stay visible/reachable; once Alpine boots, `x-show` sets an inline `display:none` on the inactive panels so only the active one shows. One DOM, no content duplication, no new JS component, PDP data ownership unchanged. Proven by two focused Django tests (`test_no_js_panels_are_visible_by_default`, `test_no_js_panels_template_has_no_static_hidden_state`) and a JS-disabled Playwright PDP check (all 3 panels computed-visible + canonical content reachable).
- **Commits:** `1f9b3a9` (initial), `50cf399` (real accordion + ZWNJ), plus the no-JS fix commit in this final micro-remediation.

## 5. MDR — Mobile navigation drawer + shared overlay primitive (Classification D / M) — DONE ✅

- **Owners reused:** canonical `content.Menu` authority via the already-exposed `NAV_MOBILE` context var (falling back to `NAV_HEADER`) — no second menu source, no hard-coded links. Responsive breakpoints owned by `core/static/css/layout.css`.
- **Shared overlay primitive (built once, used by MDR + MODAL):** `apps/core/static/js/storefront_overlay.js` registers `Alpine.data('sfbOverlay')` — generic mechanics ONLY (open/close/Escape/backdrop/focus-trap/focus-return/scroll-lock). It owns **no** domain data (enforced by a source-contract test banning `cart/product/price/menu/nav_/quantity`). Loaded before `alpine.min.js` so `alpine:init` sees it.
- **What shipped:** one accessible off-canvas drawer, `role="dialog" aria-modal`, consuming `NAV_MOBILE|default:NAV_HEADER`, RTL-safe off-canvas CSS (logical `inset-inline`, dir-aware transform), reduced-motion safe. **Corrective fix (browser-QA-driven):** the live public storefront overrides `{% block header %}` with the canonical `page_shell_header.html` shell, so the drawer was extracted into **one shared partial** (`templates/partials/mobile_nav_drawer.html`) included by BOTH `base.html` and `page_shell_header.html` (live-storefront only; the read-only Builder Preview keeps the legacy desktop-nav toggle). Single drawer implementation across every header shell — no second copy.
- **Files:** `apps/core/static/js/storefront_overlay.js`, `templates/base.html`, `templates/partials/mobile_nav_drawer.html`, `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html`, `apps/core/static/css/layout.css`.
- **Tests (RED→GREEN):** `apps/content/tests/test_mobile_nav_drawer.py` (12 source-contract tests incl. shared-partial single-owner + canonical-shell wiring).
- **Commits:** `79f812f` (drawer + primitive), `4d3daaa` (canonical-shell corrective fix + browser QA evidence).

## 6. MODAL — Public product quick view (Classification D / M–L) — DONE ✅

- **STOP condition avoided:** the quick-view is rendered **server-side inside the existing product card** from the SAME `card` (`ProductCardData`) truth already resolved by `product_card_service` — **no new backend endpoint, no client fetch, no second serializer**. This is why the "STOP BEFORE CREATING a new product endpoint" condition never triggered.
- **Owners reused:** `product_card_service.build_product_card_data` / `product_card_data` filter (card truth), `cart:add` (add-to-cart — verbatim, respecting the `show_quick_add` capability), the shared `sfbOverlay()` primitive (open/close/Escape/focus/scroll-lock).
- **What shipped:** per-card quick-view trigger (`aria-haspopup="dialog"`, `aria-controls="quick-view-{{ pk }}"`) + a hidden in-card `role="dialog" aria-modal` panel (unique id per product) showing brand/name/rating/price/discount + add-to-cart (gated on `show_quick_add is not False and is_quick_add_eligible`, honoring the existing card contract) + PDP link. RTL-safe centered dialog CSS.
- **Files:** `catalog/partials/product_card.html`, `apps/catalog/static/css/product_card.css`.
- **Tests (RED→GREEN):** `apps/catalog/tests/test_product_quick_view.py` (6 tests: dialog semantics, unique id per product, canonical card truth reuse, `cart:add` reuse, `sfbOverlay` reuse, OOS has no cart action).
- **Commit:** `ed60030`.

## 7. PDTX — merchant-editable PDP trust/delivery (Classification C / M) — DONE ✅ (IMPLEMENTED)

> **Remediation update (evidence HEAD `e061d71`).** The first pass only *proved
> the owner exists* (gate/verification). Independent review correctly flagged
> that this did NOT complete PDTX. PDTX is now **actually implemented**: the PDP
> trust experience is editable through the existing R4/Draft system, and the
> hard-coded strip is now a suppressed fallback.

- **Gate outcome (still true):** the Draft-aware canonical owner for PDP trust
  content is the existing **`trust_features`** section — a first-class
  `StorefrontSection` with a real validating schema (`TRUST_FEATURES_SCHEMA` /
  `validate_trust_features_settings`, `has_settings_form=True`). It declares no
  `page_types` so it inherits `ALL_PAGE_TYPES` (incl. `product_detail`); its
  `settings.items` ride the full Draft → validate → publish → render lifecycle.
  `ShopSettings.free_shipping_threshold` is IMMEDIATE-LIVE and was correctly
  **rejected** as the owner. **No new model, no new schema, no second authority.**
- **What shipped (implementation):**
  1. A `product_detail` `trust_features` section is the canonical, merchant-
     editable PDP trust block. Merchants edit its items through the existing R4
     mutation path (`r4_mutation_service.apply_mutation` →
     `section.update_settings`); Draft Preview shows the edit; the public
     storefront keeps the Published state until publish.
  2. **Backward-compatible suppression** so the two trust modules never both
     show: `render_service._build_items_from_sections` computes a single
     `has_sibling_trust_features` flag over the in-scope page sections and
     threads `suppress_guarantee_strip` onto the `product_main` render context
     (also added to the `responsive_section_wrapper.html` `{% include … with %}`
     allowlist so the flag reaches the template). `product_main.html` guards its
     hard-coded `.guarantee` strip with `{% if not suppress_guarantee_strip %}`.
  3. **Fallback preserved:** stores with NO PDP `trust_features` section keep the
     original hard-coded guarantee strip exactly as before — no existing store
     loses trust content, no visual flip.
- **Files:** `apps/storefront_builder/services/render_service.py`,
  `apps/storefront_builder/templates/storefront_builder/sections/product_main.html`,
  `apps/storefront_builder/templates/storefront_builder/partials/responsive_section_wrapper.html`,
  `apps/storefront_builder/tests/test_pdp_trust_editable.py` (NEW),
  `apps/storefront_builder/tests/test_pdp_trust_owner_gate.py` (the earlier gate proof, retained).
- **Tests (RED→GREEN):** `test_pdp_trust_editable.py` (9 acceptance proofs:
  R4 edit; Draft preview shows edit; Published unchanged before publish;
  Published shows edit after publish; no Home dependency; Home trust content
  never leaks to the PDP; hard-coded fallback preserved when no PDP section;
  hard-coded strip suppressed when the canonical section exists; no second
  authority/model; tenant isolation) + the 6 gate tests. Browser QA additionally
  asserts published-trust-visible + hard-coded-strip-suppressed on the live PDP.
- **Commits:** `4f57a16` (gate proof), `f3f59c1` (implementation + suppression + 9 tests).

## 8. HDR — Header (Classification A — canonical reuse, verify only) — DONE ✅ (NO-OP)

- **NEW HEADER SETTING AUTHORITY CREATED: NO.**
- **Verification:** the canonical header authority is a **single owner** — `StorefrontLayoutVersion.header_config` (JSONField), validated once by `layout_service.validate_header_config`, applied via `r4_mutation_service._apply_header_update` → `appearance_authority_service.apply_header_variant`. `global_region_registry.py` documents explicitly that `header_config`'s shape is "one single schema, validated once"; variants only select a trusted renderer partial. No second header settings authority exists.
- **Result:** 246 existing header/appearance tests pass (`test_u2a_global_header_system`, `test_u2b_global_footer_system`, `test_r4_store_appearance_mutations`, `test_phase1_appearance_authority`, `test_r4_store_appearance_rendering`) → **no defect**. Per the approved override (verification-only, NO-OP unless a test proves a real defect), **no production code and no new test file were added for HDR.**

## 9. Shared overlay primitive (built once, reused)

`Alpine.data('sfbOverlay')` in `apps/core/static/js/storefront_overlay.js` is the single accessible overlay-mechanics primitive, consumed by **MDR** (mobile nav drawer) and **MODAL** (product quick view). It owns only generic mechanics — a source-contract test forbids any domain data (cart/product/price/menu/nav_/quantity) leaking into it. This realized the single biggest reuse opportunity called out in discovery §"Shared primitives".

## 10. Architecture Gate — **PASS**

- ONE concept = ONE owner upheld: **no** second renderer, menu authority, product/card data path, cart path, header settings authority, or persistence model was introduced.
- Only additive, closed-enum / presentation / render-time changes. PDTX added **no new persistence**: it reuses the existing Draft-aware `trust_features` owner and its schema, plus one render-time boolean (`suppress_guarantee_strip`) computed from sibling sections — not a new field, model, or settings authority. MODAL uses Alpine `x-id` (client-side ids) — no data-model change.
- **Zero DB migrations** (`makemigrations --check` → "No changes detected"; no migration files changed vs base).
- Official branch `feature/phase5-design-expansion` untouched.

## 11. Changed files (vs `0d16b6a`)

Exact `git diff --name-status 0d16b6a..e061d71` (excluding the 10 browser-QA
`*.png` screenshots under `task5_browser_qa/`):

Production / templates / assets (M = modified, A = added):
- M `apps/catalog/static/css/home.css` (STRANS presets)
- M `apps/catalog/static/css/product_card.css` (MODAL dialog)
- M `apps/catalog/static/css/product_detail.css` (PDT desktop tabs + real mobile accordion)
- M `apps/catalog/templates/catalog/partials/product_card.html` (MODAL quick view + instance-safe `x-id` ids + focus-return trigger)
- M `apps/core/static/css/layout.css` (MDR off-canvas drawer)
- M `apps/core/static/css/theme_palette.css` (PDT `.pdp-acc-header.active` theme-primary color, moved off `.tabline`)
- A `apps/core/static/js/storefront_overlay.js` (shared overlay primitive — NEW; focus-return now accepts an explicit trigger)
- M `apps/storefront_builder/section_registry.py` (STRANS closed enum)
- M `apps/storefront_builder/services/render_service.py` (PDTX `suppress_guarantee_strip` sibling flag)
- M `apps/storefront_builder/templates/storefront_builder/partials/hero_slider_body.html` (STRANS runtime)
- M `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html` (MDR canonical-shell wiring)
- M `apps/storefront_builder/templates/storefront_builder/partials/responsive_section_wrapper.html` (PDTX: thread `suppress_guarantee_strip` through the include allowlist)
- M `apps/storefront_builder/templates/storefront_builder/sections/product_description.html` (PDT accordion-native rewrite + Persian ZWNJ fixes)
- M `apps/storefront_builder/templates/storefront_builder/sections/product_main.html` (PDTX guard the hard-coded guarantee strip)
- M `templates/base.html` (MDR burger + shared-partial include)
- A `templates/partials/mobile_nav_drawer.html` (MDR shared drawer — NEW)

Tests:
- A `apps/catalog/tests/test_product_quick_view.py` (MODAL — NEW; incl. instance-safe id proofs)
- A `apps/content/tests/test_mobile_nav_drawer.py` (MDR — NEW)
- A `apps/storefront_builder/tests/test_pdp_trust_owner_gate.py` (PDTX gate — NEW)
- A `apps/storefront_builder/tests/test_pdp_trust_editable.py` (PDTX acceptance — NEW)
- M `apps/storefront_builder/tests/test_r4_settings_schema.py` (STRANS)
- M `apps/storefront_builder/tests/test_render_service.py` (STRANS incl. image_slider proof)
- M `apps/storefront_builder/tests/test_views.py` (PDT incl. real-accordion proofs)

Docs / QA harness / evidence:
- A `docs/qa_evidence/storefront_design_engine/phase5/task5_implementation_report.md` (this report)
- A `docs/qa_evidence/storefront_design_engine/phase5/task5_browser_qa/report.json` + 10 `*.png` screenshots
- A `tools/storefront_builder_qa/public_task5_qa.mjs` (deepened public-storefront QA runner — NEW)
- A `tools/storefront_builder_qa/_pdtx_seed.py` (PDTX QA seed/revert helper — NEW)
- M `docs/superpowers/plans/2026-09-11-phase5-design-expansion-implementation-plan.md` (Task-5 fast-track override note)

## 12. Commits

| SHA | Area | Message |
| --- | --- | --- |
| `b6767ea` | docs | align task5 with approved fast track |
| `13dddc2` | STRANS | add hero slider transition control |
| `1f9b3a9` | PDT | make product detail panels accessible and responsive |
| `79f812f` | MDR | add canonical mobile navigation drawer |
| `ed60030` | MODAL | add storefront product quick view |
| `4f57a16` | PDTX | prove draft-aware canonical owner for PDP trust content (gate) |
| `4d3daaa` | MDR | render mobile nav drawer on canonical storefront shell |
| `896c069` | docs | finalize task5 implementation report (first pass) |
| `f3f59c1` | PDTX | **make PDP trust content merchant-editable via trust_features (remediation)** |
| `96e6604` | MODAL | **make quick view IDs instance-safe with Alpine x-id (remediation)** |
| `6b5dbdb` | STRANS | **prove image_slider transition reaches the shared slider runtime (remediation)** |
| `50cf399` | PDT | **make PDP mobile a real accordion + fix Persian ZWNJ (remediation)** |
| `e061d71` | QA | **deepen public Task-5 browser QA + fix quick-view focus return (remediation)** |

Evidence HEAD (last commit before this report commit): `e061d71`. The report's
own commit SHA is created after this table and is visible on the Draft PR.

## 13. Test evidence (focused + regression, at evidence HEAD `e061d71`)

- **Focused Task-5 + core (batch 1): 420 tests OK** —
  `test_pdp_trust_owner_gate` (6), `test_pdp_trust_editable` (9),
  `test_product_quick_view` (7), `test_mobile_nav_drawer` (12),
  `test_r4_settings_schema`, `test_render_service` (incl. STRANS +
  image_slider proofs), `test_views.ProductDetailContextAwareSectionsPreviewTests`
  (15, incl. real-accordion + Persian-ZWNJ proofs), `test_a8_product_card_presentations`,
  `test_product_card_service`, `test_product_card_cover_image`,
  `test_product_detail_view`, `test_product_detail_videos`, `test_navigation`.
- **R4 + header/footer + page_shell (batch 2): 325 tests OK** —
  `test_r4_inspector`, `test_r4_appearance_overrides`, `test_r4_foundation`,
  `test_u2a_global_header_system`, `test_u2b_global_footer_system`,
  `test_page_shell`.
- **cart + product_list (batch 3): 147 tests OK** in isolation.
- **Known PRE-EXISTING failures (NOT introduced here):** running the R4 header
  suites together with `apps.cart` in one process yields exactly 3 errors in
  `apps.cart.tests.test_cart_views.CartItemUpdateUsesComposedCartSectionsTests`
  (a test-ordering/isolation quirk). This was **reproduced identically on the
  certified base `0d16b6a`** via a clean `git worktree` with the exact same
  module combination during this remediation — same 3 tests, same `errors=3`.
  They are pre-existing and independent of Task 5; they are not new failures
  relabelled as pre-existing.
- **HDR:** 246 header/appearance tests OK (no defect; NO-OP).

## 14. Django / static gates

- `manage.py check` → no issues.
- `makemigrations --check --dry-run` → **No changes detected** (ZERO migrations).
- `git diff --check` → clean (no whitespace/conflict markers).

## 15. Browser QA (real published tenant, RTL)

Ran against the live published storefront (`rastisi-fashion-test`, 94 active products) via headless Chrome at three viewports (1440×900, 768×1024, 390×844), RTL confirmed (`dir="rtl"`). Runner: `tools/storefront_builder_qa/public_task5_qa.mjs`; evidence: `task5_browser_qa/report.json` + 10 screenshots.

### QA scope split (accepted for final acceptance)

PDTX acceptance is verified across two complementary layers — we deliberately do
NOT build a new authenticated browser-editing framework:

- **Django integration tests** (`test_pdp_trust_editable.py`, `test_pdp_trust_owner_gate.py`) prove the full lifecycle logic:
  - a merchant edit through the real R4 mutation path (`section.update_settings`),
  - Draft Preview shows the edited trust content,
  - the public Published PDP is **unchanged before publish**,
  - the public Published PDP is **updated after publish**,
  - **tenant isolation** (a foreign store's trust edit never appears on this PDP).
- **Browser QA** (`public_task5_qa.mjs`, this section) proves the real public rendering:
  - the editable trust marker is **visible on the public PDP after publish**,
  - the hard-coded fallback strip is **suppressed** when the canonical section exists (no double trust module),
  - RTL correctness + per-viewport render health.

The browser QA seeds/reverts its PDTX fixture with
`tools/storefront_builder_qa/_pdtx_seed.py` (`PDTX_QA_MODE=seed|revert`), which
is **non-destructive and fail-closed**: it only ever touches its own helper-owned
QA section (recognised by its marker content), aborts (exit 3, changes nothing)
if any non-QA `trust_features` already exists on the PDP, and restores the exact
prior tenant state on revert.

**Result (deepened harness, after the final micro-remediation): 95/95 PASS,
0 warnings, 0 failures, 0 console errors.** (92 JS-enabled checks + 3 new no-JS
PDP checks.)

- **PDT no-JS (JavaScript disabled context):** the PDP returns 200; **all 3 panels are computed-visible** (`display` ≠ none); the canonical `desc-text` / `spec-table` / `review-sum` content is reachable in the DOM. Screenshot: `pdp-nojs-desktop-1440.png`.

- **STRANS:** `data-hero-transition` present AND carries a valid closed-enum value (`cut`/`fade`/`slide`) at every viewport (proves the setting reaches the real runtime).
- **MODAL:** quick-view trigger + dialog on every card (52/52); **unique** dialog + title ids across the whole page (52/52 unique — instance-safe); trigger `aria-controls` resolves to the opened dialog; PDP link present; cart-affordance consistent with card settings; **opens**, **focus enters overlay**, **Tab stays trapped**, **body scroll-locked**, **backdrop/explicit/Escape all close**, **focus returns to the trigger**.
- **MDR (390px):** burger opens the drawer; **canonical `NAV_MOBILE` links present** (13); focus enters + Tab trapped; scroll-locked; **explicit/backdrop/Escape close**; **focus returns to the burger**.
- **PDT:** 3 tabs / 3 panels; exactly one active panel; selected tab ↔ shown panel `aria-controls`/`aria-labelledby` paired; desktop **Arrow/Home/End keyboard nav** works; mobile **real accordion** verified (DOM source order = header,panel,header,panel,header,panel AND the open panel sits directly under its own header); RTL + no overflow.
- **PDTX:** with a seeded+published PDP `trust_features` edit, the public PDP **shows the edited trust content** and the **hard-coded strip is suppressed** (no double trust module) at all 3 viewports. The seed was reverted after QA, restoring the tenant's default PDP.

## 16. Deferred scope (explicitly NOT done)

- **HDR:** no schema-validated header-variant field was added (the discovery's "B" idea) — the approved override made HDR verify-only. Legacy full-page header editor retirement also deferred.
- **PDTX further placement polish:** the canonical editable PDP trust block renders via the `trust_features` section (page-level features strip). Visually re-homing it *inside* the `product_main` `.pinfo` column is a styling refinement, not required for the editable-trust acceptance, and is left for a later visual pass.
- Configurable Mega Menu family, Showcase (Task 6), Theme Overlay (Task 12), full 50-template QA (Task 16) — out of Task-5 scope.
- **Task 6 was NOT started.**

## 17. Final verdict

Task 5 (with the independent-review remediation) is **COMPLETE**:

- **STRANS** — closed-enum transition, live on BOTH hero_banner and image_slider (shared runtime; no dead control).
- **PDT** — accessible desktop tablist + **real** mobile accordion from one accordion-native DOM; Persian ZWNJ fixed.
- **MDR** — one shared accessible drawer on the canonical storefront shell.
- **MODAL** — quick view with **instance-safe `x-id` ids** (no duplicate ids when a product repeats on a page) + focus return.
- **PDTX** — **actually implemented**: PDP trust is merchant-editable through the existing R4/Draft `trust_features` owner (Draft preview shows edits, public uses Published until publish), with a backward-compatible suppression of the hard-coded fallback so the two never both show. No new model, no second authority.
- **HDR** — verified NO-OP; **NEW HEADER SETTING AUTHORITY CREATED: NO**.

Architecture Gate **PASS**; **ZERO DB migrations**; one shared overlay primitive
reused by MDR + MODAL; deepened browser QA **92/92** at three RTL viewports, 0
console errors; the 3 cart-isolation errors are proven pre-existing on the
certified base. The official branch `feature/phase5-design-expansion` is
untouched; delivery is Draft PR #2 into it (not merged).
