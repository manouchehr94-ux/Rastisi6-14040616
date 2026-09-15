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
- `apps/cart/services/pricing.py` — extend the `cart_totals()` return dict with the precomputed `free_shipping_threshold`, `free_shipping_by_threshold`, `free_shipping_by_coupon`, `free_shipping_goal_remaining`, `free_shipping_goal_progress_percent` fields (all math here; see Canonical-math rule below).
- `apps/storefront_builder/templates/storefront_builder/sections/cart_summary.html` — add the goal/progress **display** markup reading only `totals.free_shipping_goal_*` and `totals.free_shipping_by_threshold`/`free_shipping_by_coupon`.
- `apps/cart/static/css/cart.css` — the canonical cart stylesheet (loaded by `apps/cart/templates/cart/cart_detail.html:16`); add the goal/progress bar styles here. Do NOT create a new global sheet and do NOT put cart styles in `product_detail.css`.
- Tests: `apps/cart/tests/` (extend the pricing/threshold suite against `cart_totals()`) plus a `render_service`/section render test asserting the goal fields reach the template and the view/template performs no threshold math.

**Files forbidden to duplicate:** `pricing.py` (`cart_totals` — it is the sole math owner), `ShopSettings` threshold read (only the existing `_free_shipping_threshold` call), the cart page/route, `cart:add`. `render_service._cart_summary_context` must NOT read `ShopSettings` or compute goal values.

**Canonical-math rule (non-negotiable):** ALL Free-Shipping Goal math lives in `apps/cart/services/pricing.py::cart_totals()` — the canonical pricing/coupon/free-shipping/tax authority. The View/render-context layer and the Template/CSS/JS layers perform **display only**. There must be **no second `ShopSettings.load()` threshold read** in the render/view/template layer, and **no pricing math in JavaScript**.

**Interfaces produced/consumed:**
- **Extend `cart_totals()`'s returned dict** (in `pricing.py`, reusing the already-computed `items_total`, existing `_free_shipping_threshold(store)`, and the existing `free_by_threshold` / `free_shipping_by_coupon` locals — `pricing.py:114–126`) with these precomputed, presentation-ready fields (names may follow project conventions; ownership stays in `pricing.py`):
  - `free_shipping_threshold` — the Store-scoped threshold Decimal (from the existing `_free_shipping_threshold(store)`).
  - `free_shipping_by_threshold` — bool: `items_total >= threshold` (the existing `free_by_threshold`).
  - `free_shipping_by_coupon` — bool: coupon granted free shipping (the existing `free_shipping_by_coupon`), so the reason is distinguishable and coupon-granted free shipping is **never** misreported as "threshold reached."
  - `free_shipping_goal_remaining` — `max(Decimal("0"), threshold − items_total)` (Decimal, never negative), computed in pricing.
  - `free_shipping_goal_progress_percent` — `0` when threshold ≤ 0 or empty cart, else `min(100, round(items_total * 100 / threshold))`, **clamped to `[0,100]`** in pricing.
- `_cart_summary_context` (`render_service.py:696`) continues to pass the existing `totals` dict unchanged (it now carries the new fields). **It must NOT read `ShopSettings` or compute anything.**
- Template consumes only `totals.free_shipping_goal_*` / `totals.free_shipping_by_threshold` / `totals.free_shipping_by_coupon` for display.

**TDD RED tests (write first) — in `apps/cart/tests/` against `cart_totals()`:**
1. **below** threshold, no coupon → `free_shipping_by_threshold=False`, `free_shipping_goal_remaining = threshold − items_total > 0`, `progress_percent` in `(0,100)`.
2. **exactly at** threshold → `free_shipping_by_threshold=True`, `remaining=0`, `progress_percent=100`.
3. **above** threshold → `free_shipping_by_threshold=True`, `remaining=0`, `progress_percent` clamped to `100`.
4. **free-shipping coupon while still below threshold** → `free_shipping=True`, `free_shipping_by_coupon=True`, `free_shipping_by_threshold=False` (coupon-granted free shipping NOT reported as threshold reached).
5. **threshold reached without coupon** → `free_shipping_by_threshold=True`, `free_shipping_by_coupon=False`.
6. **empty cart** → `remaining = threshold`, `progress_percent=0`, no negative/NaN.
7. **two Stores with different `free_shipping_threshold`** → different `remaining`/`progress_percent` (Store-scoped).
8. **progress bounded 0–100** for arbitrary large `items_total`.
9. **presentation consumes precomputed values only** — a render/template test asserting `_cart_summary_context` adds no `ShopSettings`/threshold computation and the template references only `totals.free_shipping_goal_*`/flags (assert no `ShopSettings.load` in the view layer for this path; template contains no arithmetic).
Also: existing `items_total`/`grand_total`/`tax`/coupon outputs of `cart_totals()` remain unchanged (regression assertion).

**Expected RED reason:** `cart_totals()` does not yet return the `free_shipping_goal_*` / `free_shipping_by_threshold` fields, and `cart_summary.html` has no goal markup.

**Minimal GREEN implementation:** add the precomputed fields to the `cart_totals()` return dict (reusing existing locals; no new `ShopSettings` read beyond the existing `_free_shipping_threshold`); render them for display in `cart_summary.html` (progress width driven by the server-computed `free_shipping_goal_progress_percent`; no JS/template arithmetic).

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

### Architecture decision (made now from source — not deferred)

**A. Theme is a new optional canonical Store-Appearance FAMILY, not a free-form `settings` bag.** SOURCE-VERIFIED: `storefront_appearance/validation.py` closes `settings` — `_validate_typed_settings` rejects any top-level key not in `COMPONENT_FAMILIES` (`validation.py:107–110`) and any per-family key not in `ALLOWED_SETTINGS_BY_FAMILY[family]` (`validation.py:116–119`), and every family's allowed set is currently `frozenset()` (`validation.py:52–53`). So a bare "put theme key + intensity in settings" is invalid. Instead:
- **Add a `theme` family** to `apps/storefront_builder/storefront_appearance/families.py` (`_FAMILY_DEFINITIONS`) as a `ComponentFamilyDefinition(key="theme", label_fa="تمِ مناسبتی", storage_adapter_key="theme_overlay", safe_default_component_key="theme.none.v1", renderer_role="theme_overlay", optional=True, capabilities={"responsive","rtl"})`. `optional=True` + a `theme.none.v1` safe default means **no theme by default**; the occasion is a bounded **component selection** in `manifest.selections["theme"]`.
- **Register the occasion components** (`theme.none.v1`, `theme.nowruz.v1`, `theme.yalda.v1`, `theme.valentine.v1`, `theme.ramadan.v1`, `theme.eid_fitr.v1`, `theme.eid_qorban.v1`, `theme.muharram.v1`, …) in the canonical component catalog consumed by `apps/storefront_builder/storefront_appearance/registry.py` (`_DEFINITIONS` → `COMPONENT_REGISTRY`), validated by the existing `validate_component_catalog`. This is the SAME registration path header/footer/hero components use — **not a second registry.**
- **Add intensity as a bounded family setting:** set `ALLOWED_SETTINGS_BY_FAMILY["theme"] = frozenset({"intensity"})` in `validation.py`, and add a typed validator that constrains `settings["theme"]["intensity"]` to the bounded enum `{"subtle","balanced","strong"}` (default `balanced`). Intensity lives in `manifest.settings["theme"]` — now a *validated, closed* family setting, not a free-form field.
- If, on inspection, an existing family representation is provably safer, the implementer must document the source reason in the W2 report; the default and expected path is the dedicated `theme` family above.

**B. Reversibility is the family's own `theme.none.v1` default — NOT `template_baseline_snapshot`.** SOURCE-VERIFIED: `template_baseline_snapshot` (`models.py:296`) is the *immutable Ready-Template baseline captured at Template Apply time*, NOT a snapshot of the merchant's appearance immediately before enabling a Theme. Using it for theme reversibility would wrongly discard non-theme merchant customizations. Because Theme is an independent overlay family, **`clear_theme()` = set `selections["theme"]="theme.none.v1"` and drop `settings["theme"]`, changing ONLY theme-owned state.** Every non-theme field (header/footer/bottom_nav/hero/product_view/card/badge selections, palette/font/density, section composition) is untouched — so removing a theme reproduces the exact prior non-theme state with no extra pre-theme snapshot. Undo/Redo/history use the existing `edit_history_service` mechanism.

**C. Theme resolves through the canonical Store-Appearance resolution path, covering global chrome AND sections.** SOURCE-VERIFIED: `storefront_appearance/rendering.py::resolve_store_appearance_manifest_state` (`:67`) → `ResolvedStoreAppearance` (`:48`) is the single resolver used by BOTH the public render path (`resolve_store_appearance_render_state:105`) AND the candidate path (`preset_service.resolve_preset_candidate`, per its `rendering.py:74–75` docstring). The `theme` family (`renderer_role="theme_overlay"`) is resolved there once, so Preview/Public/Header/Footer/BottomNav/Sections all see one resolved theme state. `render_service` **consumes** the resolved theme result (e.g. exposing theme accent/motif CSS variables + a `data-theme`/`data-theme-intensity` attribute on the storefront shell, and letting section variants read the same resolved state) — it must **NOT** create a second independent theme resolver. Add a `theme_overlay_state(state)` accessor on the rendering module (mirroring `global_renderer_template`) so consumers read the resolved theme without re-resolving.

**Exact files that MUST change (named now):**
- `apps/storefront_builder/storefront_appearance/families.py` — add the `theme` `ComponentFamilyDefinition`.
- `apps/storefront_builder/storefront_appearance/registry.py` (+ its `_DEFINITIONS` component source) — register the occasion `ComponentDefinition`s (incl. `theme.none.v1`).
- `apps/storefront_builder/storefront_appearance/validation.py` — `ALLOWED_SETTINGS_BY_FAMILY["theme"] = frozenset({"intensity"})` + bounded intensity enum validation.
- `apps/storefront_builder/storefront_appearance/rendering.py` — resolve the `theme` family into `ResolvedStoreAppearance` and add the `theme_overlay_state` accessor (the single resolution point for global + section consumers).
- `apps/storefront_builder/services/appearance_authority_service.py` — narrow `apply_theme(occasion_component_key, intensity)` / `clear_theme()` writing only `selections["theme"]` + `settings["theme"]` through the existing manifest persistence (`persist_store_appearance_manifest`), mirroring `apply_header_variant` (`:171`).
- `apps/storefront_builder/theme_catalog.py` (NEW data module) — the bounded occasion catalog: for each occasion the component key, human label, accent/motif tokens, and a `tone` flag (`festive`/`neutral`/`mourning`). A data catalog, NOT a registry competing with `layout_preset_registry`.
- `templates/storefront_shell.html` (+ the relevant section/global CSS) — consume the resolved theme (accent/motif CSS variables + `data-theme`/`data-theme-intensity`), reusing the existing CSS-variable/token pattern; no per-template CSS fork.
- R4 inspector template/JS — expose Theme + Intensity controls (Advanced tier), reusing the Task-4 inspector pattern and the canonical R4 mutation boundary.
- Tests under `apps/storefront_builder/tests/`.

**Files forbidden to duplicate:** the manifest contract/validator, `appearance_authority_service`, the `rendering.py` resolver (`resolve_store_appearance_manifest_state`), `render_service`, `layout_preset_registry`, `COMPONENT_REGISTRY`, Draft/lifecycle. No second theme registry/manifest/persistence/resolver.

**Required invariants (tests):**
- Applying a Theme leaves base structural DNA **byte-for-byte unchanged**: `selections` for header, footer, bottom_nav, hero, product_view, card, badge, layout, mega_menu, motion and section composition are identical before/after; only `selections["theme"]` + `settings["theme"]` change.
- **Remove Theme (`clear_theme`) reproduces the exact pre-Theme state for all non-theme fields.** Concrete scenario asserted: (1) apply Ready Template → (2) merchant changes header/font/radius/cards → (3) enable Yalda theme → (4) disable theme ⇒ manifest + rendered output for all non-theme fields equals state (2), NOT the Ready-Template baseline.
- Theme participates in the existing Draft lifecycle, stale-write protection (`edit_revision`), `edit_history_service` undo/redo, Preview, and Publish/public rendering — via existing authorities (no new lifecycle).
- Bounded intensity only (`{subtle,balanced,strong}`; invalid rejected by the validator).
- **Preview/Public parity** + **global-region AND section proof:** the same resolved theme appears in the shell chrome (header/footer/bottom-nav) and in section variants, identically in Preview and Public render.

**TDD RED tests:** (a) apply theme → only `selections["theme"]`/`settings["theme"]` change, all other selections identical; (b) `clear_theme` after non-theme edits → exact restore of the non-theme state (the 4-step scenario), NOT the template baseline; (c) intensity outside the enum is rejected by `validate_store_appearance_manifest`; (d) theme flows through publish → public render AND appears on global chrome + a section (parity); (e) `theme.none.v1` is the safe default (no theme unless selected); (f) mourning occasions carry `tone="mourning"` in the catalog. **Expected RED reason:** no `theme` family, no theme components, no `ALLOWED_SETTINGS_BY_FAMILY["theme"]`, and no theme resolution exist at `804f734` (`grep theme_overlay|occasion|campaign_overlay|seasonal|intensity` is empty).

**Tone constraints (catalog review):** mourning themes (محرم/عاشورا) must NOT auto-introduce sale countdowns, confetti, high-pressure discount messaging, or celebratory motifs. Encode a per-occasion `tone` flag; the initial catalog copy is flagged for Product Owner review.

**Focused test command:** `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings` (theme + appearance suites).
**Regression command:** full appearance + render suites: `python manage.py test apps.storefront_builder.tests.test_r4_store_appearance_rendering apps.storefront_builder.tests.test_r4_store_appearance_registry apps.storefront_builder.tests.test_r4_store_appearance_contracts apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_preset_service --settings=shop_core.settings`.
**Browser QA:** ≥3 themes (one festive Iranian, one Islamic, one neutral/sale) × 3 intensities on 2–3 base templates × 3 viewports RTL; plus the 4-step Remove-Theme restore proof and a global-chrome + section parity capture.
**Tenant/security:** theme selection/intensity are Store-scoped through the per-version manifest; no cross-store leakage.
**Architecture duplication gate:** confirm theme is a `theme` family in the single `COMPONENT_FAMILIES`/`COMPONENT_REGISTRY`, resolved by the single `rendering.py` resolver; no second registry/manifest/Draft/resolver; `render_service` only consumes the resolved state.
**Checks:** expect **ZERO migrations** (theme lives in the existing JSON manifest). If a migration seems needed → STOP for Architect review.
**Evidence:** `docs/qa_evidence/storefront_design_engine/phase5/w2_theme_overlay/` + `w2_implementation_report.md`.
**Branch:** `feature/phase5-w2-theme-overlay`. **Commits (boundaries):** (1) `feat(storefront_builder): add reversible Theme appearance family + validator`; (2) theme catalog + resolution/consumption; (3) R4 Theme/Intensity controls. **PR gate:** unmerged; Architect + Product Owner (catalog tone) approval before merge.

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

### Exact candidate interface (decided now — Option A: transient `LayoutPresetDefinition`)

SOURCE-VERIFIED: the canonical read-only resolver is `resolve_preset_candidate(draft: StorefrontLayoutVersion, preset: LayoutPresetDefinition) -> ResolvedPresetCandidate` (`preset_service.py:646`). It takes a **`LayoutPresetDefinition`**, NOT an arbitrary manifest, and performs zero writes (shares `_prepare_preset_application`; validates `preset.store_appearance` via `validate_store_appearance_manifest`; resolves appearance via `resolve_store_appearance_manifest_state`). SOURCE-VERIFIED: `LayoutPresetDefinition` is a **pure, Store-agnostic Python data object** (`layout_preset_registry.py`) with `key`, `version`, `default_palette_slug`, a `store_appearance` `StoreAppearanceManifest`, and `pages` = tuples of `PresetSectionEntry` — it is "data, not a new family implementation" and requires **no registration/persistence**.

**Therefore the Design-Lab candidate = an in-memory transient `LayoutPresetDefinition` built by a pure generator, then passed straight to the existing `resolve_preset_candidate`.** No new candidate engine, no new manifest type, no persistence.

- **Exact new service file:** `apps/storefront_builder/services/design_lab_service.py`.
- **Transient candidate data contract (in-memory only; never saved):**
  - `DesignLabCandidate` — a frozen dataclass holding: `base_selections: Mapping[str,str]` (the current Draft's resolved family selections), `candidate_selections: Mapping[str,str]` (per-family chosen component keys, incl. `theme`), `settings: Mapping` (bounded per-family settings, incl. `theme.intensity`), `locked_families: frozenset[str]` (transient locks), and `seed: int | None` (deterministic generation seam).
  - `generate_candidate(draft, *, randomize_families: set[str], locked_families: set[str], seed: int | None) -> DesignLabCandidate` — a **pure** function: for each requested (unlocked) family it picks a component from that family's registered, compatible options (reusing the canonical `COMPONENT_REGISTRY` / family compatibility metadata), never changing a locked family, never producing a combination that fails the canonical validators. Randomize-One = a `randomize_families` of size 1 (Header/Hero/Product Cards/Footer/etc.).
  - `candidate_to_preset(draft, candidate) -> LayoutPresetDefinition` — builds the transient `LayoutPresetDefinition` (page composition = the Draft's current pages preserved; `store_appearance` = a `StoreAppearanceManifest` with `candidate_selections` + `settings`; `default_palette_slug` = current). It is passed to `resolve_preset_candidate(draft, preset)` for **preview only** — no registration, no `register_layout_preset`.
- **R4 preview handoff:** the Design-Lab panel previews the candidate through the EXISTING iframe path — `storefront_builder/views.py::storefront_preview` (`:249`) / `_preview_page_context` (`:202`) — fed by the `resolve_preset_candidate` result. No second preview view.
- **Apply handoff:** explicit Apply commits the candidate's selections/settings through the EXISTING canonical mutation boundary `r4_mutation_service.apply_mutation(store, actor, base_revision, mutation)` (`:1003`) — which enforces `edit_revision != base_revision` stale-write (`:996-997`), tenant scope, and writes via `appearance_authority_service`/`edit_history_service`. Design-Lab NEVER writes directly.
- **Locks:** live only in `DesignLabCandidate.locked_families` (transient request/session state) — explicitly NOT `StorefrontSection.is_locked`/`StorefrontContainer.is_locked` (structural lock; different semantics). No persistence of locks unless source proves a canonical persisted lock already exists (it does not at `804f734`).
- **Zero persistence before Apply:** `generate_candidate`/`candidate_to_preset`/`resolve_preset_candidate` perform no `.save()`, no row create/delete, no manifest write, no history entry, no new `StorefrontLayoutVersion`.

**Other exact files that change:**
- **Write-time reconciliation for hero/product_view/card/badge (absorbs old Task 13):** extend `apps/storefront_builder/services/appearance_authority_service.py` with `apply_component_variant(draft, family, component_key)` (single generalized writer mirroring `apply_header_variant:171`/`apply_footer_variant:194`) so Apply persists these families into `StoreAppearanceManifest.selections` through the canonical manifest instead of only the render-time overlay in `render_service._build_items_from_sections`. This is the write path Random-Mix Apply uses.
- `apps/storefront_builder/services/design_lab_service.py` (NEW, per above).
- R4 inspector template/JS — Design-Lab panel + controls (Randomize / Randomize-One / lock toggles / Compare-with-Base / Return-to-Original / Reset / Remove-Theme / Preview / Apply), reusing the existing preview iframe and `apply_mutation` boundary.
- Tests under `apps/storefront_builder/tests/`.

**Files forbidden to duplicate:** `resolve_preset_candidate` (candidate primitive), `LayoutPresetDefinition`/`register_layout_preset` (no registration of candidates), `storefront_preview` (preview view), `apply_mutation`, Draft model, appearance manifest/validator/resolver, `edit_history_service`.

**Critical state rule:** before Apply, candidate state is transient; after explicit Apply, state flows through `apply_mutation`/`appearance_authority_service` only.

**Determinism:** provide a bounded **test seed / deterministic generation seam** so QA can reproduce a generated candidate; do not surface meaningless technical seeds in production UX unless needed.

**Apply gate (tests):** Apply respects `edit_revision` and fails stale; preserves tenant isolation; creates normal history evidence; never bypasses `apply_mutation`.

**TDD RED tests:** (a) `generate_candidate` never changes a **locked** family; (b) `candidate_to_preset` + `resolve_preset_candidate` never produce a combination that fails the canonical validators (invalid combos raise the same `InvalidPresetError`/`InvalidStoreAppearanceContract`); (c) **Compare-with-Base** correctly diffs the candidate's selections/settings against the **current committed Draft state** (base = the Draft's present manifest selections; "Return to Original DNA" restores that base — and, where the merchant is still on an unmodified Ready Template, that base equals `template_baseline_snapshot`); (d) candidate generation + preview perform **no writes** (assert no `.save()`/row/history/manifest write) until Apply; (e) Apply is stale-safe (wrong `base_revision` → `R4StaleRevision`) and goes through `apply_mutation`; (f) `generate_candidate` with the same `seed` is deterministic (reproducible for QA); (g) Remove Theme uses the W2 `clear_theme` owner and restores the exact pre-theme non-theme state. **Expected RED reason:** no `design_lab_service`/Design-Lab/Random-Mix symbol and no `apply_component_variant` exist at checkpoint.

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
