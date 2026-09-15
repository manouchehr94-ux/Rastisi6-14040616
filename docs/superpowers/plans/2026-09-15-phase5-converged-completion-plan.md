# RastiSi Phase 5 Converged Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Phase 5 using only the five evidence-supported remaining workstreams, reusing all canonical architecture delivered by Tasks 1–8.

**Architecture:** Continue the existing single-authority Storefront architecture. New capabilities extend existing canonical owners; no second renderer, Draft lifecycle, appearance manifest, preview engine, cart flow, navigation system, ProductCard path, or tenant resolver may be introduced.

**Tech Stack:** Python 3.12, Django 5.2, Django Templates, Alpine.js, HTMX, existing Playwright QA infrastructure.

**Spec:** `docs/qa_evidence/storefront_design_engine/phase5/phase5_convergence_audit.md`

---

Date: 2026-09-15
Status: AUTHORITATIVE — replaces Tasks 9–18 of `docs/superpowers/plans/2026-09-11-phase5-design-expansion-implementation-plan.md` (now marked SUPERSEDED AFTER TASK 8).
Planning checkpoint: `feature/phase5-design-expansion @ 804f734a18d7504fb62f9db595433b0a4bf82fcd` (post-Task-8; Tasks 1–8 CLOSED). This SHA is the base for **P5-W1 only** — every later workstream re-bases on the latest merged official checkpoint (see §Checkpoints).

This plan is intentionally precise: every owner, file, and symbol below was SOURCE-VERIFIED at the planning checkpoint. Where an exact new filename is given it is the recommended path; an implementer may adjust a *new* file's name if it collides, but must never introduce a second copy of a named canonical owner.

---

## Global Constraints

### Architecture — `ONE CONCEPT = ONE CANONICAL OWNER`

Forbidden across ALL workstreams (introducing any of these is an automatic STOP for architecture review):

- second Storefront renderer (canonical: `apps/storefront_builder/services/render_service.py`)
- second Ready Template registry (canonical: `apps/storefront_builder/layout_preset_registry.py`, populated by `apps/storefront_builder/a8_ready_templates.py`)
- second appearance manifest (canonical: `StoreAppearanceManifest` in `apps/storefront_builder/storefront_appearance/contracts.py`)
- second Draft model/lifecycle (canonical: `StorefrontLayoutVersion` + `apps/storefront_builder/services/layout_service.py`)
- second publish lifecycle (canonical: `layout_service.publish` / `r4_mutation_service.publish_draft`)
- second edit-history system (canonical: `apps/storefront_builder/services/edit_history_service.py`)
- second candidate-preview engine (canonical: `preset_service.resolve_preset_candidate` + `storefront_builder/views.py::storefront_preview`)
- second R4 mutation boundary (canonical: `apps/storefront_builder/services/r4_mutation_service.py::apply_mutation`)
- second tenant resolver (canonical: `apps/stores/resolution.py`)
- second ResourceSource authority (canonical: `apps/storefront_builder/resource_source.py`)
- second ProductCard path (canonical: `apps/catalog/templates/catalog/partials/product_card.html` + `product_card_service`)
- second cart / add-to-cart path (canonical: `apps/cart/` `cart:add` + `apps/cart/services/pricing.py::cart_totals`)
- second Bottom Navigation system (canonical: `_navigation.html` renderer + `--gmn-clearance` geometry token)
- second overlay/modal/drawer mechanics system (canonical: `apps/core/static/js/storefront_overlay.js::sfbOverlay`)
- second search backend
- duplicate recommendation logic
- per-template business logic
- per-template SATC fixes
- per-template mobile-navigation engines

### Git safety

Every implementation workstream must: (1) start from the latest certified official Phase-5 checkpoint; (2) use its own branch; (3) use TDD (RED → GREEN → focused → regression → browser evidence → architecture/duplication gate → review); (4) produce evidence; (5) open an **unmerged** PR into `feature/phase5-design-expansion`; (6) receive independent Architect review; (7) merge only after Product Owner/Architect approval. Never work directly on the official branch. No force push, reset, stash, clean, or destructive rebase without explicit approval.

### Migrations

Expected default: **ZERO MIGRATIONS.** Any proposed database migration must STOP for architecture review before implementation. The current architecture already has suitable persisted JSON/Draft authorities (`StorefrontLayoutVersion.appearance_config` / `StoreAppearanceManifest.settings` / `template_baseline_snapshot`) for the remaining design capabilities unless source investigation proves otherwise.

### Evidence & verification (every workstream)

Each workstream's PR must show: focused test command + output, relevant regression command + output, browser evidence where visual, `python manage.py check` clean, `python manage.py makemigrations --check --dry-run` = "No changes detected" (unless an approved migration), and `git diff --check` clean. Tests run with `--settings=shop_core.settings` (SQLite; Python 3.12).

---

## The five remaining workstreams

Old Tasks 9–18 are replaced by exactly five workstreams: `P5-W1` … `P5-W5`. Do NOT reuse old Task 9–18 numbering for new implementation work.

---

## P5-W1 — Cart Conversion Micro-Pass (Free-Shipping Goal)

**Goal:** Add a Free-Shipping Goal / progress indicator to the cart, driven entirely by existing pricing/threshold data. Presentation-only.

**Non-goals:** Cross-Sell (→ BACKLOG). No new shipping threshold. No cart commerce math in JavaScript. No new cart model. No standalone recommendation service. No change to totals/coupon/tax computation.

**Certified starting checkpoint:** `804f734…` (planning checkpoint). Branch off the official branch at this SHA.

**Exact canonical owners consumed (SOURCE-VERIFIED):**
- Threshold: `ShopSettings.free_shipping_threshold` (`apps/core/models.py`), default from `SHOP_FREE_SHIPPING_THRESHOLD` (`shop_core/settings.py:357`); Store-scoped via `ShopSettings.load(store=store)`.
- Eligible amount for the threshold comparison = **`items_total`** — SOURCE-VERIFIED in `apps/cart/services/pricing.py`: `free_by_threshold = items_total >= _free_shipping_threshold(store)` (`pricing.py:125`), where `items_total = Σ(item.unit_price × item.quantity)` after per-item product discounts (`pricing.py:101–108`). `cart_totals(...)` returns a dict that already includes `items_total` and `free_shipping` (`pricing.py` return block ~`:177`).
- Context delivery: `render_service._cart_summary_context` (`render_service.py:696`) already passes `totals` (the `cart_totals` dict) to the template.

**Exact files expected to change:**
- `apps/storefront_builder/templates/storefront_builder/sections/cart_summary.html` — add the goal/progress presentation reading `totals.items_total`, `totals.free_shipping`, and the Store threshold (exposed via the existing context; if the raw threshold is not yet in `totals`, add it to the returned dict in `_cart_summary_context` from `ShopSettings.load(store).free_shipping_threshold` — a context addition, NOT a new setting).
- `apps/catalog/static/css/product_detail.css` **is NOT** the owner here; cart styling lives with the cart section CSS — use the existing cart/summary stylesheet the section already loads (confirm during implementation; do not create a new global sheet).
- Tests: `apps/cart/tests/` (extend the pricing/threshold suite) and/or a `render_service`/section render test asserting the goal context + template output.

**Files forbidden to duplicate:** `pricing.py` (`cart_totals`), `ShopSettings`, the cart page/route, `cart:add`.

**Interfaces produced/consumed:** consumes `totals` (existing). Produces only template markup + a possible single added context key (`free_shipping_threshold`) in `_cart_summary_context`.

**TDD RED tests (write first):**
1. cart **below** threshold → goal shows a remaining-amount to the threshold (remaining = `threshold − items_total`, > 0).
2. cart **exactly at** threshold → goal shows the "achieved" state; `free_shipping` truthy.
3. cart **above** threshold → achieved state; progress clamped at 100% (never > valid range).
4. **empty cart** → goal renders safely (no negative/NaN; either hidden or 0%).
5. threshold source is **Store-scoped** (two stores with different `free_shipping_threshold` render different remaining amounts).
6. **Persian/RTL** presentation (fa digits; RTL-safe markup).
7. **no fabricated shipping promise** when `requires_shipping=False`/no shipping context (do not claim free physical shipping where none applies — mirror existing honesty gates).
8. existing totals/coupon/tax outputs unchanged (regression assertion on `cart_totals`).

**Expected RED reason:** the goal markup/context does not exist yet in `cart_summary.html` / `_cart_summary_context`.

**Minimal GREEN implementation:** render the progress/goal from `totals` (+ threshold context key) in `cart_summary.html`; no JS math (progress computed server-side or via a bounded CSS width from server values); clamp width to `[0,100]`.

**Focused test command:** `python manage.py test apps.cart.tests apps.storefront_builder.tests.test_render_service --settings=shop_core.settings`

**Regression command:** `python manage.py test apps.cart apps.storefront_builder.tests.test_views apps.orders.tests.test_checkout_correctness --settings=shop_core.settings`

**Browser QA:** cart at below/at/above threshold + empty, at 1440×900 / 768×1024 / 390×844, RTL; screenshot the goal states. Reuse `tools/storefront_builder_qa/`.

**Tenant/security:** threshold read Store-scoped; no cross-store leakage; no PII.

**Architecture duplication gate:** confirm no second threshold source, no JS commerce math, no new model, no recommendation code.

**Checks:** `check`, `makemigrations --check --dry-run` (expect 0), `git diff --check`.

**Evidence paths:** `docs/qa_evidence/storefront_design_engine/phase5/w1_free_shipping_goal/` (report.json + screenshots) + a `w1_implementation_report.md`.

**Branch:** `feature/phase5-w1-cart-free-shipping-goal`. **Commit boundary:** one focused commit `feat(cart): free-shipping goal progress indicator`. **PR gate:** unmerged PR into `feature/phase5-design-expansion`; independent Architect review; Product Owner approval before merge.

**Cross-Sell disposition:** `BACKLOG`. Do NOT implement random-category, arbitrary related products, fabricated "you may also like," or any duplicate recommendation logic.

**Expected size:** small / bounded.

---

## P5-W2 — Reversible Theme Overlay

**Goal:** A reversible occasion/seasonal Theme layer that modifies presentation (accents/motifs/decoration/motion tone) without rewriting base Ready-Template DNA. Supports نوروز, یلدا, ولنتاین, رمضان, عید فطر, عید قربان, محرم/عاشورا and future Iranian/Islamic occasions through the same canonical mechanism.

**Theme intensity:** bounded enum, internal vocabulary `subtle` / `balanced` / `strong`. No unbounded values.

**Non-goals:** not a new Ready Template; not a second appearance manifest; not a second Draft; not a parallel renderer; not a per-template CSS fork; not a destructive DNA rewrite.

**Certified starting checkpoint:** the official checkpoint **after P5-W1 merges** (record the SHA at kickoff; do NOT hard-code `804f734…`).

**Exact canonical owner (SOURCE-VERIFIED) — verify before coding:**
- `apps/storefront_builder/services/appearance_authority_service.py` — `apply_appearance_patch` (`:113`), `apply_store_appearance_manifest` (`:132`), `apply_header_variant` (`:171`), `apply_footer_variant` (`:194`), `apply_ready_template_appearance` (`:230`).
- Manifest contract: `StoreAppearanceManifest` (`storefront_appearance/contracts.py:149`) = `{schema_version (== SUPPORTED_MANIFEST_SCHEMA_VERSION = 1), selections: Mapping, settings: Mapping (default {})}`. **`settings` is the extension slot** for typed theme fields (theme key + intensity), validated the same way palette/font/density are — NOT a new JSON blob outside the manifest.
- Persistence: `storefront_appearance/persistence.py::persist_store_appearance_manifest` (`:106`).
- Reversibility source: `StorefrontLayoutVersion.template_baseline_snapshot` (`apps/storefront_builder/models.py:296`) + the granular reset family in `preset_service.py` (`reset_storefront_to_baseline:714`, etc.).
- Render application: `render_service._build_items_from_sections` (`:806`) — theme overlay is applied at render time over the resolved appearance, exactly like the existing hero/product_view/card/badge overlay; theme adds decoration/accents, it does not rewrite persisted structural selections.

**Exact files expected to change (verify/confirm during implementation):**
- `apps/storefront_builder/storefront_appearance/contracts.py` — add typed theme fields to the manifest `settings` contract + validators (occasion key from a bounded catalog; intensity enum). No schema_version bump unless Architect approves.
- `apps/storefront_builder/services/appearance_authority_service.py` — a narrow `apply_theme(occasion, intensity)` / `clear_theme()` operation (mirroring `apply_header_variant`), writing only theme-owned fields.
- `apps/storefront_builder/services/render_service.py` — read theme fields and apply the presentation overlay (accents/motifs/motion) over the resolved appearance.
- A theme catalog module (new, e.g. `apps/storefront_builder/theme_catalog.py`) listing the supported occasions + their overlay tokens + tone flags — a data catalog, not a registry that competes with `layout_preset_registry`.
- CSS: theme accent/motif variables consumed by existing sections (reuse existing CSS-variable/token pattern; no per-template fork).
- R4 UI: expose Theme + Intensity as controls in the existing R4 inspector (Advanced tier), reusing Task-4 patterns.
- Tests under `apps/storefront_builder/tests/`.

**Files forbidden to duplicate:** the manifest contract, `appearance_authority_service`, `render_service`, `layout_preset_registry`, Draft/lifecycle.

**Required invariants (tests):**
- Applying a Theme leaves base structural DNA **byte-for-byte unchanged**: header, footer, bottom_nav, hero family, product_view family, product_card family, section composition (only theme-overlay-owned fields change).
- **Remove Theme reproduces the exact pre-Theme base state** (compare persisted manifest + rendered output before/after).
- Theme participates in the existing Draft lifecycle, stale-write protection (`edit_revision`), history/undo-redo, Preview, and Publish/public rendering — via existing authorities (no new lifecycle).
- Bounded intensity only.

**TDD RED tests:** (a) theme applied → only theme fields change, structural selections identical; (b) remove theme → exact restore; (c) intensity is bounded (invalid intensity rejected); (d) theme flows through publish → public render; (e) mourning-occasion tone flags present (see below). **Expected RED reason:** no theme field/symbol exists anywhere today (`grep theme_overlay|occasion|campaign_overlay|seasonal|intensity` is empty at `804f734`).

**Tone constraints (catalog review):** mourning themes (محرم/عاشورا) must NOT auto-introduce sale countdowns, confetti, high-pressure discount messaging, or celebratory motifs. Encode a per-occasion `tone` flag; the initial catalog copy is flagged for Product Owner review.

**Focused test command:** `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings` (theme + appearance suites).
**Regression command:** full `appearance_authority_service`, `render_service`, `preset_service` suites (`test_r4_store_appearance_*`, `test_render_service`, `test_preset_service`).
**Browser QA:** ≥3 themes (one festive Iranian, one Islamic, one neutral/sale) × 3 intensities on 2–3 base templates × 3 viewports RTL; plus Remove-Theme restore proof.
**Tenant/security:** theme is Store-scoped through the manifest; no cross-store leakage.
**Architecture duplication gate:** confirm theme lives inside `StoreAppearanceManifest.settings`, no second registry/manifest/Draft.
**Checks:** expect **ZERO migrations** (theme lives in the existing JSON manifest). If a migration seems needed → STOP for Architect review.
**Evidence:** `docs/qa_evidence/storefront_design_engine/phase5/w2_theme_overlay/` + `w2_implementation_report.md`.
**Branch:** `feature/phase5-w2-theme-overlay`. **Commits:** e.g. `feat(storefront_builder): reversible Theme Overlay (manifest settings)` + catalog/UI commits. **PR gate:** unmerged; Architect + Product Owner (catalog tone) approval before merge.

---

## P5-W3 — Design Lab / Random Mix

**Goal:** The Product-Owner-approved visual exploration experience, with candidate exploration **transient until explicit Apply**.

**Required conceptual capabilities:** Random Mix; Randomize One / Header / Hero / Product Cards / Footer (and other DNA families where source justifies); lock/unlock individual families; Compare with Base; Return to Original DNA; Reset candidate; Remove Theme; Preview Candidate; explicit Apply.

**Non-goals / forbidden:** no `RandomMixModel`; no second Draft JSON field acting as another design truth; no second Preview DB version; no hidden auto-save of every candidate; no client-only fake renderer; no Cartesian raw-random (reuse recipe validation); no localStorage-as-authority.

**Certified starting checkpoint:** the official checkpoint **after P5-W2 merges** (record SHA at kickoff). W3 depends on W2 because Remove-Theme / Theme-aware compare must use the real Theme owner.

**Infrastructure that MUST be reused (SOURCE-VERIFIED):**
- Candidate resolution: `preset_service.resolve_preset_candidate` (`:646`), `resolve_preset_candidate_by_key` (`:689`), dataclasses `ResolvedPresetCandidate` (`:611`) / `ResolvedPresetCandidatePage` (`:595`). These resolve a candidate with **zero writes** and share `_prepare_preset_application` with the real apply path.
- Ready Template DNA manifest + provenance/baseline: `a8_ready_templates` manifests; `StorefrontLayoutVersion.template_provenance` (`models.py:286`) + `template_baseline_snapshot` (`models.py:296`) → Compare-with-Base / Return-to-Original data source.
- Canonical appearance manifest: `StoreAppearanceManifest` (theme fields from W2).
- Preview: `storefront_builder/views.py::storefront_preview` (`:249`) + `_preview_page_context` (`:202`) — the existing candidate-preview iframe path.
- Apply/persistence + concurrency: `r4_mutation_service.apply_mutation` (`:1003`), `apply_history_command` (`:1031`), `publish_draft` (`:1119`); stale-write via `edit_revision != base_revision` under `select_for_update`; history via `edit_history_service`.
- Remove Theme: the `clear_theme()` operation built in W2.

**Exact files expected to change:**
- `apps/storefront_builder/services/` — a Design-Lab service that GENERATES a candidate manifest (random-but-validated combination) and resolves it through `resolve_preset_candidate`; NO persistence. Locks are a transient (request/session-scoped) concept — explicitly NOT `StorefrontSection.is_locked`/`StorefrontContainer.is_locked` (structural lock, different semantics).
- **Write-time reconciliation for hero/product_view/card/badge (absorbs old Task 13):** extend `appearance_authority_service.py` with `apply_component_variant(family, value)` (or per-family `apply_hero_variant`/`apply_product_view_variant`/`apply_card_variant`/`apply_badge_variant`) mirroring `apply_header_variant`, so Apply persists these families through the canonical manifest instead of only the render-time overlay. This is the write path Random-Mix Apply needs.
- R4 UI (existing inspector/preview) — Design-Lab panel + controls, reusing the preview iframe and mutation boundary.
- Tests under `apps/storefront_builder/tests/`.

**Files forbidden to duplicate:** candidate primitive, preview view, `apply_mutation`, Draft model, appearance manifest, `edit_history_service`.

**Critical state rule:** before Apply, candidate state is transient; after explicit Apply, state flows through `apply_mutation`/`appearance_authority_service` only.

**Determinism:** provide a bounded **test seed / deterministic generation seam** so QA can reproduce a generated candidate; do not surface meaningless technical seeds in production UX unless needed.

**Apply gate (tests):** Apply respects `edit_revision` and fails stale; preserves tenant isolation; creates normal history evidence; never bypasses `apply_mutation`.

**TDD RED tests:** (a) Random Mix never changes a **locked** family; (b) Random Mix never produces a combination failing existing recipe validation; (c) Compare-with-Base diffs current vs `template_baseline_snapshot` correctly; (d) candidate state performs **no writes** until Apply; (e) Apply is stale-safe and goes through `apply_mutation`; (f) Remove Theme uses the W2 owner and restores exact pre-theme state. **Expected RED reason:** no Design-Lab/Random-Mix symbol exists at checkpoint.

**Focused/regression/browser/tenant/duplication/checks:** focused = Design-Lab + appearance suites; regression = W1/W2 suites + candidate/preview/mutation suites together; browser = Random Mix (all-open + single-family), a Lock preventing change, Compare-with-Base real diff, Remove Theme restore, at 3 viewports RTL; tenant isolation asserted at Apply; duplication gate confirms transient candidate + single persistence; expect **ZERO migrations** (transient state; persisted fields already exist).
**Evidence:** `docs/qa_evidence/storefront_design_engine/phase5/w3_design_lab/` + `w3_implementation_report.md`.
**Branch:** `feature/phase5-w3-design-lab`. **Commits:** separate boundaries (write-time reconciliation; Random Mix + Locks; Compare-with-Base; Remove-Theme wiring). **PR gate:** unmerged; Architect + Product Owner approval.

---

## P5-W4 — Public Storefront Shell Convergence + 50-Template Curation & Certification

Combined convergence + final rendering-quality workstream, in THREE ordered stages. **Certified starting checkpoint:** the official checkpoint **after P5-W3 merges** (record SHA). W4 must run after all rendering changes so certification reflects the final state.

### P5-W4A — Public Storefront Shell Convergence

**Goal:** Converge public merchant-facing surfaces that still use the legacy `base.html` path onto the canonical universal storefront shell + context, preserving domain-specific content.

**SOURCE-VERIFIED known gaps (at `804f734`):**
- **Wishlist:** `apps/customers/views.py::wishlist_list` (`:25`) renders `customers/wishlist.html` with a plain dict (no `build_universal_storefront_context`); `apps/customers/templates/customers/wishlist.html` extends `base.html` (line 1).
- **Content/CMS:** `apps/content/views.py::page_detail` (`:11`) renders `content/page_detail.html` with `{page}` only; `apps/content/templates/content/page_detail.html` extends `base.html` (line 1).

**Mandatory bounded inventory first:** enumerate ALL public merchant-facing views/templates and classify each as: (1) **canonical universal shell** (view calls `build_universal_storefront_context` and/or template extends `storefront_shell.html` — e.g. `catalog.product_list`, `catalog.product_detail`, `catalog.home`, `cart`); (2) **intentionally non-storefront** (transactional/account flows — candidates observed: `customers/account`, `customers/order_detail`, `orders/checkout_step1`, `orders/payment_result`; classify explicitly, do NOT assume); (3) **legacy-shell public gap** (must converge — confirmed: `content/page_detail`, `customers/wishlist`). Note: `storefront_shell.html` itself extends `base.html`, so "extends base.html" alone is NOT the gap — the gap is extending `base.html` **directly** instead of `storefront_shell.html` AND the view not building the universal context. Do NOT migrate admin/dashboard pages.

**Repair (genuine public gaps only):** route the view through `build_universal_storefront_context` and make the template extend the canonical `storefront_shell.html`, reusing the canonical Header/Footer/Bottom Navigation and `apps/stores/resolution.py`. Domain content stays domain-owned (Wishlist products/empty-state remain Wishlist's; CMS body/SEO remain Content's). **No new shell, no context-builder clone, no duplicate Header/Footer.**

**Files expected to change:** `apps/customers/views.py` (`wishlist_list`), `apps/customers/templates/customers/wishlist.html`, `apps/content/views.py` (`page_detail`), `apps/content/templates/content/page_detail.html` (+ any additional confirmed public gap). **Forbidden to duplicate:** `storefront_shell.html`, `build_universal_storefront_context`, header/footer/bottom-nav partials, `resolution.py`.

**TDD RED:** wishlist + CMS pages render with the universal storefront chrome (header/footer/bottom-nav present) while preserving their domain content and tenant scoping; **expected RED reason:** they currently render bare `base.html` without the universal context. **Browser QA:** wishlist (empty + populated) and a CMS page at 3 viewports RTL, showing the storefront envelope. **Checks:** expect ZERO migrations. **Branch:** `feature/phase5-w4a-public-shell-convergence` (W4 may use sub-branches per §Branch naming).

### P5-W4B — 50-Template Curation

**Goal:** Reuse existing section families to make each Template materially distinct; do not build a new editorial subsystem.

**Reality (SOURCE-VERIFIED recipe usage in `a8_ready_templates.py`):** used — testimonials(7), newsletter(13), rich_text/story_rail/image_text(1). Zero usage — faq, video_section, blog_posts, promo_cards, quick_links, collection_tiles, image_slider. **Zero usage does NOT mean "must use."** Curation is intentional and per-Template; do not insert every component everywhere for coverage stats.

**Scope of change:** data-level edits to the composition tuples in `apps/storefront_builder/a8_ready_templates.py` (which sections each of the 50 recipes composes). Build a new section ONLY if a curated Template genuinely needs one that does not exist (e.g. STAT) — and only with Product Owner sign-off; STAT is otherwise BACKLOG. **Invariant:** exactly **50** Ready Templates remain, and `apps/storefront_builder/tests/test_a8_template_diversity.py` (50 pairwise-unique structural signatures, palette/font ignored) stays green. **Regression:** `test_a8_ready_template_catalog.py`, `test_a8_template_diversity.py`, composition-validation tests. **Branch:** `feature/phase5-w4b-template-curation`.

### P5-W4C — All-50 Browser Certification

**Goal:** Real closure gate — automated browser matrix for ALL 50 Ready Templates. Representative QA does not count.

**Matrix (per Template):** Desktop (1440×900), Tablet (768×1024), Mobile (390×844), RTL; horizontal-overflow check; presence/health of Header, Hero, Product Cards, Footer, Bottom Navigation; core page load; Listing; PDP; Cart; Theme interaction where applicable; accessibility-critical controls; console/page/request error capture. Reuse the existing harness `tools/storefront_builder_r4_qa/run.mjs` (and/or `tools/storefront_builder_qa/`) — **do NOT build a second harness.**

**Evidence-volume discipline:** machine-readable JSON matrix for every Template/page/viewport; representative retained screenshots; mandatory home-template gallery assets for all 50 (for W5 review); failure screenshots only for failing non-home cases. Do not commit thousands of redundant screenshots.

**Visual distinctness:** all 50 materially distinguishable across Header/Hero/layout/composition/Product Card/density/typography/Footer/Bottom Navigation — palette-only difference is insufficient. Structural test uniqueness (W4B) and rendered visual certification are **different gates**; both required.

**Branch:** `feature/phase5-w4c-all50-certification`. **Evidence:** `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/` (JSON matrix + curated screenshots + 50 home gallery assets). **PR gate:** each W4 sub-branch unmerged; Architect review; Product Owner approval.

---

## P5-W5 — Product Owner Review + Final Phase-5 Closure

**Goal:** Human closure — a real Product Owner review surface plus the final technical closure gate. **Certified starting checkpoint:** after P5-W4 merges (record SHA).

**Review surface:** reuse the existing live/candidate-preview + Task-2 gallery infrastructure (no second gallery renderer). For each of the 50 Ready Templates record a status: `APPROVED` / `NEEDS POLISH` / `REJECTED`, allowing inspection of Desktop + Mobile storefront, template identity, Header, Hero, Product Cards, Footer, Bottom Navigation, and Theme examples where relevant.

**Closure rules:** Phase 5 cannot close with unresolved `REJECTED` items. `NEEDS POLISH` items require repair + re-review OR explicit Product Owner acceptance.

**Final technical closure gate (all must pass):** full relevant regression; `python manage.py check`; `python manage.py makemigrations --check --dry-run`; `git diff --check`; tenant-isolation verification; architecture duplication audit; Preview/Public parity; Draft/Published lifecycle verification; all-50 certification green; final evidence pack; official Phase-5 checkpoint (SHA + backup branch per the repo's Phase-4 convention). **Branch:** QA/evidence/finalization branch(es) as appropriate. **Evidence:** `docs/qa_evidence/storefront_design_engine/phase5/w5_closure/` + PO review record.

---

## Old Tasks 9–18 → New Workstream Reconciliation

| Old Task | Original goal (summary) | New disposition |
|---|---|---|
| Task 9 | Free-Shipping Goal + Cross-Sell | **SHRINK → P5-W1** (Free-Shipping Goal); **Cross-Sell → BACKLOG** (no canonical recommendation authority) |
| Task 10 | Activate editorial sections in recipes; build STAT | **MERGE → P5-W4B** (data-level recipe curation); STAT → BACKLOG unless a curated Template needs it |
| Task 11 | Generic utility primitives (Drawer/Overlay/Toast/Tabs/Tooltip/Skeleton/Floating/Scroll-Reveal/Menu-transition) | **DROP as standalone** — Drawer/Overlay/Toast/Tabs/Menu-transition already exist (Task 5); missing low-value utilities (Tooltip/Skeleton/Back-to-Top/Scroll-Reveal/generic Tabs) → BACKLOG |
| Task 12 | Theme Overlay + intensity | **REDESIGN → P5-W2** (on `StoreAppearanceManifest.settings`) |
| Task 13 | Write-time reconciliation for hero/product_view/card/badge | **MERGE → P5-W3** (the write path Random-Mix Apply needs) |
| Task 14 | Random Mix / Randomize One / Locks / Remove Theme / Compare-with-Base | **REDESIGN/MERGE → P5-W3** (transient candidate until Apply) |
| Task 15 | R4 controls simplification pass | **MERGE** into the quality/simplicity gates across P5-W2/W3/W4 |
| Task 16 | Cross-template QA (all 50) | **KEEP, redesigned → P5-W4C** |
| Task 17 | Product Owner gallery/review | **KEEP → P5-W5** |
| Task 18 | Final Phase-5 closure checkpoint | **KEEP → P5-W5** |

---

## Explicitly Deferred — Not Phase-5 Blockers

- **Cross-Sell / recommendation engine** — BACKLOG until a legitimate recommendation authority/product strategy exists. Do NOT fabricate recommendation truth (no random-category, no arbitrary "you may also like").
- **Tooltip / Popover** generic primitive — BACKLOG unless remaining work requires it.
- **Skeleton / loading state** generic primitive — BACKLOG unless remaining work requires it.
- **Floating Action / Back-to-Top** — BACKLOG unless real UX evidence justifies it.
- **Additional generic utility abstractions** — do not create merely for architectural completeness (YAGNI).
- **Countdown / urgency commerce components** — do NOT fabricate countdown/urgency truth.
- **Stats / Social-Proof numbers (STAT)** — do NOT fabricate social-proof metrics; real Product data only; build only if a curated Template needs it with PO sign-off.
- **In-cart coupon-entry UI** — BACKLOG (coupon domain exists; not a closure blocker).
- **Importing the 670 AI reference variants** — excluded (per the charters/old plan).

---

## Sequencing

```
P5-W1  →  P5-W2  →  P5-W3  →  P5-W4 (A→B→C)  →  P5-W5
```

Rationale: W1 is small/isolated; W2 establishes the Theme owner; W3 consumes Theme + candidate infra; W4 certifies the final rendering state after all rendering changes; W5 is final human review + closure. **Do not parallelize by default;** the Architect may explicitly approve parallelization later.

## Branch naming

- W1: `feature/phase5-w1-cart-free-shipping-goal`
- W2: `feature/phase5-w2-theme-overlay`
- W3: `feature/phase5-w3-design-lab`
- W4: `feature/phase5-w4-certification-convergence` (or sub-branches `…-w4a-public-shell-convergence`, `…-w4b-template-curation`, `…-w4c-all50-certification` if Shell convergence and curation need independent review gates)
- W5: QA/evidence/finalization branch(es) as appropriate

No implementation branch is created during THIS planning task.

## Checkpoints

Each workstream begins from the **latest merged official Phase-5 checkpoint**, not a hard-coded SHA. `804f734…` is only the base for P5-W1. After W1 merges, W2 re-bases on the new official checkpoint; after W2 merges, W3 re-bases; and so on. **Record the exact SHA at every gate** (kickoff base + merge result) in each workstream's implementation report.

---

## Planning Self-Review (against the convergence audit)

- **Coverage:** every remaining BUILD/PARTIAL requirement in the audit maps to a workstream — Free-Shipping Goal → W1; Theme Overlay → W2; Design Lab/Random Mix (+ Task-13 write path) → W3; Public shell convergence (Wishlist + CMS) + editorial curation + all-50 certification → W4; PO review + closure → W5.
- **Duplication:** no workstream creates a parallel authority (Global Constraints enumerate the forbidden owners; W2/W3 extend the single manifest + candidate primitive; W4A adopts the single shell).
- **Old-plan retirement:** old Tasks 9–18 are marked SUPERSEDED and non-executable; this plan is authoritative.
- **YAGNI:** Cross-Sell, STAT, and missing utility primitives are BACKLOG, not built to satisfy the old 67-family MISSING rows.
- **Product Owner intent preserved:** 50 materially distinct Templates; multiple Bottom-Navigation visual models under one canonical system; Theme overlays for Iranian/Islamic/seasonal occasions; Random Mix / بازگشت به DNA اصلی; simple merchant controls; mobile-first quality; no architecture duplication.
- **No premature implementation:** this planning PR changes only documentation.
