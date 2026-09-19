# P5-W5 — Merchant-Facing Storefront Design Experience: Discovery & Implementation Planning

Status: **DISCOVERY AND PLANNING ONLY — no W5 implementation has started.**
Official starting branch: `feature/phase5-design-expansion`
Official starting HEAD (checkpoint honored): `81abb435c6421197117f8f570993b64ca485d4af`
W4C merge commit: `742fda5e88ec7c0bdd5bf17c6c7f4e839fde82f6` (PR #12, MERGED, APPROVED)

Supporting evidence (read alongside this document):
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/current_state_inventory.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/gap_matrix.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/authority_map.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w5_discovery/merchant_journeys.md`

---

## 0. A note on how this discovery was conducted

The local checkout of `feature/phase5-design-expansion` was found, at the start of this round, to be **107 commits behind** `origin/feature/phase5-design-expansion` — still sitting at the P5-W2 merge point, missing all P5-W3 (Design Lab), P5-W4A (public shell convergence), P5-W4B (template curation) and P5-W4C (all-50 certification) work on disk. `origin/feature/phase5-design-expansion` itself was found to be exactly at the expected checkpoint `81abb435c6421197117f8f570993b64ca485d4af`.

Per the safety-gate rules (no reset/rebase/stash/clean, report and stop if HEAD has moved), the situation was reported and a **pure fast-forward** (a strict ancestor advance — local had zero commits not already on origin, so nothing could be discarded) was proposed and explicitly approved by the Product Owner before being applied. The local checkout now matches the checkpoint exactly (`git status --short` clean, `HEAD == 81abb435...`). All research below was additionally cross-verified against an isolated read-only worktree pinned to the checkpoint commit before the fast-forward, so no finding depends on the timing of that sync.

The Graphify graph present in the repository (`graphify-out/graph.json`) was found to be stale — built against the old pre-fast-forward commit — and was **not used** as a source of truth for this discovery; all findings are direct source reads/greps against the checkpoint commit, cited by exact file and function/class name.

---

## 1. What already exists (do not rebuild)

Full detail in `current_state_inventory.md` and `authority_map.md`. Headline findings:

- **The R4 Builder is the live, authoritative merchant Storefront Builder** (`/admin-portal/storefront-builder/r4/`), default-enabled for every Store. A legacy "R3" surface remains wired in only as an explicit, flagged rollback valve, sharing all underlying services.
- **The 50-Template Gallery already exists and is fully merchant-facing**: real page, real nav entry, all 50 templates, real static preview screenshots, real Apply-to-Draft flow with content preservation, provenance tracking, and Demo-vs-merchant-data preview modes. This is not QA tooling — it is production.
- **The canonical Apply-to-Draft flow is a single, well-tested authority** (`preset_service.apply_preset()`) reached from three legitimate entry points (Gallery form, R4 full-apply mutation, R4 content-preserving template-switch), never copying catalog/business data.
- **Design Lab already exists and is fully implemented**: transient candidate state, Random Mix (compatibility-scoped, not raw Cartesian), per-family locks, Compare, Return-to-original-DNA, and a real Apply-to-Draft path — all reusing the canonical renderer, mutation dispatcher, and component registry. This is P5-W3, already merged.
- **Reversible Theme Overlay already exists and is the most thoroughly tested family in the system** — this is P5-W2, already merged.
- **There is exactly one shared renderer** for Preview, Design Lab preview, non-destructive template preview, and the public storefront — verified with no violations found.
- **6 of 16 Store-Appearance families are COMPLETE vertical slices today** (Header, Motion, Footer, Palette, Typography, Density, Radius, Content Width, Theme — that's actually 9; see the gap matrix for the exact per-family table). The remaining families are registered and rendered, but reachable only through Design Lab/whole-template Apply, not through a persistent, always-on Normal-Builder control.

## 2. What is built but not yet merchant-visible

- **Hero, Product View, Product Card (family-level), Badge**: full registry + renderer + Design-Lab wiring, but no persistent selector in the Normal Builder's Global Design panel. A merchant reaches these only via Design Lab or by re-applying a whole template.
- **Mobile Bottom Navigation**: real registry and real renderer for both Preview and Public, but the canonical R4 `footer.update` mutation contract does not accept the `mobile_nav_variant` field — a merchant on the default R4 editor literally cannot change it directly; only the legacy editor (or Design Lab) can. This is the single highest-priority closable gap found in this discovery (see gap_matrix.md).
- **Template provenance**: recorded on every Apply, never surfaced to the merchant in any UI.

## 3. What exists only as dead/placeholder registry

- **Mega Menu** as an independent, switchable family: the registry has exactly one component (`mega_menu.none.v1`). The real mega-menu experience is owned by specific Header variants, not by this family. This is a product-decision gap, not an engineering gap — see §4.
- **The typed `layout` (composition) family**: registered with 9 variants, but zero render consumers were found anywhere in the codebase. A separate, fully working per-container layout system (2/3/4-column rows) already covers the practical merchant need — the typed `layout` family appears to be unused scaffolding.

## 4. Architectural findings requiring an explicit W5 decision

Two duplication findings from `authority_map.md`, both documented/intentional states rather than accidents, but both need a Product-Owner-level decision before W5 IA work proceeds:

1. **R3/R4 dual mutation surface.** R4 is default and canonical; R3 remains a flagged, wired-in rollback valve with two capabilities (restore/history browser, industry-vertical preset installer) that have no R4 equivalent. Legacy write endpoints remain server-reachable without stale-write protection regardless of the flag. **Decision needed**: keep R3 permanently as a documented safety valve (acceptable, but the gap should be named), or use W5 to close the remaining capability gaps and retire R3's write surface.
2. **Two "Template" registries sharing a name.** The 50 Ready Templates (this initiative) and a separate, older 10-item style-token registry (`appearance_registry.TEMPLATE_REGISTRY`, exposed as `template_slug`) both live in the R4 editor's Appearance panel and can silently override overlapping fields (font/density/radius/width) with no coupling or warning. **Decision needed**: rename one concept (e.g. "Style Pack" for the 10-item set) before W5 gives either concept more prominence in the IA.

---

## 5. Simple Builder vs. Design Lab boundary (§15)

Derived from the actual R4 UX already shipped, not invented from scratch. The existing editor already embodies most of this split:

**NORMAL BUILDER (what's already there, kept as the default surface):**
- Ready Template picker (all 50, switch-with-content-preservation)
- Global Design: Palette, Typography, Density, Radius, Content Width, Motion (all already COMPLETE, always-on controls)
- Header, Footer (already COMPLETE, always-on controls)
- Theme/Occasion (already COMPLETE)
- Section/Page structure editing (Structure panel, Storefront Showcase facade)
- Preview (device switcher), Undo/Redo, Publish

**ADVANCED DESIGN LAB (already exists, stays the "everything else" surface):**
- Hero, Product View, Product Card, Badge, Mobile Bottom Nav (the PARTIAL families — until/unless a Product Owner decision promotes any of them to a Normal Builder control)
- Random Mix, per-family locks, Compare, Return-to-original-DNA
- Full component-library exploration

This matches the spec's §23 boundary almost exactly as already implemented; the only real IA question W5 needs to answer is **whether any of the five PARTIAL families should be promoted to a persistent Normal Builder control** (most likely candidate: Mobile Bottom Nav, since it's mobile-navigation-critical and currently has the R4-editor gap described in §2).

## 6. Proposed W5 information architecture (§16)

The existing R4 Builder shell already owns this navigation shape; W5 should evolve it, not replace it:

```
Storefront Builder (existing R4 shell, apps/storefront_builder/r4_views.py)
  Structure (existing: sections/containers/Showcase facade)
  Design
    Ready Templates          — EXISTS (Gallery), needs: in-page lightbox, device preview on pre-apply preview
    Colors & Typography      — EXISTS (Palette/Typography/Density/Radius/Width)
    Header                   — EXISTS
    Footer                   — EXISTS
    Mobile Navigation        — GAP: needs promotion from legacy-only to R4 (§2 priority fix)
    [Hero / Products / Cards — pending the promotion decision in §5]
  Advanced Design Lab        — EXISTS, unchanged
  Preview                    — EXISTS
  Publish                    — EXISTS
```

No second application shell is proposed or needed — everything above already lives inside the one existing R4 editor template and its existing panel structure.

---

## 7. W5 architecture self-review (§22)

Checked against every item on RastiSi's forbidden-duplication list before finalizing this plan:

- Second renderer? **No** — the plan explicitly reuses the single verified renderer chain.
- Second Draft? **No** — every proposed workstream writes through the existing `StorefrontLayoutVersion`/`apply_mutation` boundary.
- Second Store Appearance state? **No** — proposed family promotions (e.g. Bottom Nav) reuse the existing `storefront_appearance` typed manifest and `r4_mutation_service` dispatcher; the fix is adding an allowed patch key and a UI selector, not new state.
- Second Ready Template registry? **No** — Gallery/preview improvements reuse `layout_preset_registry`/`a8_ready_templates.py` verbatim.
- Second mutation path? **No** — no new mutation types beyond widening `footer.update`'s allowed-keys set (or an equally narrow, single-purpose addition) are proposed.
- Separate mobile builder? **No** — the plan explicitly keeps one responsive shell.
- Lab-only production model? **No** — every family promotion moves a Design-Lab-reachable capability into the Normal Builder using the *same* underlying mutation; nothing new is invented for Lab-only use.
- Demo-data copying? **No** — confirmed absent today (see current_state_inventory.md §4); no workstream below touches the Apply pipeline's catalog-preservation guarantee.
- Redundant UI implementation / functionality that already exists? **This is the primary risk this discovery was built to catch.** The workstreams below are deliberately scoped to close *named, verified* gaps (Bottom Nav's R4 mutation gap, Gallery device-preview, Mega Menu product decision, `layout` family disposition) rather than re-implementing anything already complete (Header, Footer, Palette, Typography, Density, Radius, Content Width, Motion, Theme, Design Lab, the 50-template browser, or the Apply flow).

No corrections to the plan were needed as a result of this review.

---

## 8. Proposed W5 workstream decomposition (§17)

Named for traceability; not pre-approved, and deliberately does **not** include a workstream for anything already complete.

### W5A — Bottom Navigation R4 Parity (highest-priority closable gap)
- **Problem**: merchants on the canonical R4 editor cannot change Mobile Bottom Navigation directly; the R4 mutation contract itself excludes the field.
- **PO-visible outcome**: a real Bottom-Nav selector appears in the R4 editor's footer group; changing it works exactly like Header/Footer today.
- **Existing code reused**: `_apply_footer_update`, `global_region_registry`'s 7 bottom_nav variants, `global_renderer_template`, the existing footer-group UI pattern.
- **Exact missing code**: add `mobile_nav_variant` to `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS` in `r4_mutation_service.py`; add a `#r4GlobalMobileNav` selector to `r4/editor.html`'s footer group, mirroring the existing `#r4GlobalFooterVariant` pattern.
- **Architectural authorities used**: existing `footer.update` mutation, existing stale-write/tenant guards — no new mutation type.
- **Explicit non-goals**: no change to the legacy editor's existing (working) selector; no new registry entries.
- **Dependencies**: none — self-contained.
- **TDD strategy**: extend the existing `footer.update` mutation test suite with a Bottom-Nav-specific case; add a Playwright smoke check that the R4 editor's new selector round-trips through Preview → Publish → Public identically to the legacy editor's existing behavior.
- **Browser QA strategy**: reuse the W4C harness pattern — verify no regression in the 704-cell certification baseline; add targeted Bottom-Nav-selector interaction coverage.
- **Security/tenant risks**: none beyond the existing footer-update guards (already tenant/stale-write protected).
- **Duplication risk**: none — one field addition to one existing allowed-keys set.
- **Definition of done**: merchant can change Bottom Nav from the R4 editor; Undo/Redo, Preview, and Public all reflect it; zero migrations.

### W5B — Ready Template Gallery Polish
- **Problem**: pre-apply template preview has no in-page lightbox and no device (Desktop/Tablet/Mobile) toggle.
- **PO-visible outcome**: merchant can enlarge a template preview in-page and toggle device sizes before applying.
- **Existing code reused**: `ready_template_live_preview.html`, `storefront_template_live_preview` view, the existing device-switcher pattern already built for the in-editor Draft preview.
- **Exact missing code**: a modal/lightbox wrapper for the existing preview link; port the existing device-switcher markup/JS onto the Gallery preview page (same iframe-scaling technique, no new renderer).
- **Non-goals**: no new preview renderer, no new preview route.
- **Dependencies**: none.
- **Duplication risk**: none, provided the device switcher is copied/reused, not reinvented.
- **Definition of done**: Gallery preview supports in-page enlarge + 3-viewport toggle; zero migrations.

### W5C — Mega Menu & `layout` Family Disposition (product decision, minimal code)
- **Problem**: two registered "families" (`mega_menu`, `layout`) are currently non-functional placeholders that could mislead future development or merchant expectations.
- **PO-visible outcome**: a documented, explicit decision — either (a) formally mark both as non-production/reserved-for-future in the registry with a code comment and remove any merchant-facing implication that they're switchable today, or (b) scope real variants/renderer wiring for one or both as a future workstream.
- **Existing code reused**: registry definitions as-is.
- **Non-goals**: do not silently leave them as-is without a decision — that risks a future engineer building against `layout` assuming it renders.
- **Dependencies**: Product Owner decision first; code change (if any) is small.
- **Definition of done**: registry entries are either wired to a real renderer or explicitly documented as reserved/inert; zero migrations either way.

### W5D — Family Promotion Decision for Hero/Product View/Card/Badge
- **Problem**: four PARTIAL families are fully built but reachable only via Design Lab.
- **PO-visible outcome**: Product Owner decides which (if any) graduate to a persistent Normal Builder control, following the §5 boundary rule (don't put 13 heroes/19 cards on one giant screen).
- **Existing code reused**: 100% — registries, renderers, and the generic `appearance.component.update` mutation already work; only a UI selector (mirroring Header/Footer's existing pattern) would be added per promoted family.
- **Non-goals**: no new registry entries, no new mutation types.
- **Dependencies**: Product Owner decision.
- **Definition of done**: for each promoted family, a selector exists in the Normal Builder; non-promoted families remain Design-Lab-only by design, not by gap.

### W5E — R3/R4 and "Template" Naming Disposition
- **Problem**: the two architectural findings in §4 need an explicit decision before further IA work risks compounding them.
- **PO-visible outcome**: a documented decision recorded (e.g. in this plan's changelog or a follow-up ADR) on (a) R3's long-term status and (b) a rename for one "Template" concept.
- **Dependencies**: none technical; Product Owner input required.
- **Definition of done**: decision recorded; if a rename is chosen, it is planned as its own small, isolated workstream (UI label + docs only, no registry restructuring) to avoid scope creep into this discovery round.

### W5F — End-to-End Certification Refresh
- **Problem**: any of W5A-D touch merchant-facing surfaces the W4C harness already certifies.
- **PO-visible outcome**: confidence that W5 changes didn't regress the 704-cell certified baseline.
- **Existing code reused**: the entire W4C harness (`tools/storefront_builder_r4_qa/run.mjs`, `qa_storefront_builder_r4.py`).
- **Non-goals**: no new harness, no new matrix shape — extend the existing one only if a new merchant-facing control (e.g. Bottom Nav selector) needs its own interaction assertion.
- **Definition of done**: harness re-run clean against the W5 head; new interaction coverage added only for genuinely new controls (W5A/B).

---

## 9. Recommended first W5 implementation slice (§18)

**W5A — Bottom Navigation R4 Parity.**

Why it goes first: it is the single gap in this entire discovery that is (a) small — one allowed-key addition plus one UI selector mirroring an existing pattern, (b) vertical — touches mutation contract, UI, and render output for a real user-visible capability, (c) testable — extends existing, well-understood test suites, (d) merchant-visible — closes a real capability gap for mobile-first storefronts, and (e) architecture-safe — reuses every existing authority with zero new concepts, zero new mutation types, and zero migrations. Every other proposed workstream either requires a Product Owner decision first (W5C, W5D, W5E) or is lower-priority polish (W5B) or is a downstream verification step (W5F).

**This is not being implemented in this round.** No implementation branch has been created.

---

## 10. Persian summary for the Product Owner (§19)

### توضیح برای صاحب فروشگاه

**۱. امروز صاحب فروشگاه واقعاً چه امکانات طراحی‌ای دارد؟**

صاحب فروشگاه امروز می‌تواند: هر ۵۰ قالب آماده را مرور کند و با اطلاعات نمایشی یا اطلاعات واقعی فروشگاه خودش پیش‌نمایش بگیرد؛ یک قالب را روی طرح پیش‌نویس (Draft) خودش اعمال کند بدون این‌که محصولات، دسته‌بندی‌ها یا قیمت‌هایش تغییر کند؛ هدر، فوتر، رنگ‌بندی، فونت، تراکم چیدمان، گردی گوشه‌ها، عرض محتوا، حرکت (Motion) و تم‌های مناسبتی (نوروز، رمضان، محرم و...) را مستقل از هم تغییر دهد؛ از «آزمایشگاه طراحی» (Design Lab) برای امتحان کردن ترکیب‌های تصادفی هدر/هیرو/کارت/فوتر استفاده کند بدون این‌که هر کلیک آزمایشی در تاریخچهٔ فروشگاهش ثبت شود؛ تغییرات را Undo/Redo کند؛ پیش‌نمایش دسکتاپ/موبایل بگیرد؛ و در نهایت با یک کلیک منتشر (Publish) کند.

**۲. چه چیزهایی پشت صحنه ساخته شده ولی هنوز در اختیار صاحب فروشگاه نیست؟**

چهار خانوادهٔ طراحی — هیرو (بخش اصلی بالای صفحه)، نحوهٔ نمایش محصولات، طرح کارت محصول، و نشان‌های تبلیغاتی (Badge) — به‌طور کامل ساخته و تست شده‌اند، اما صاحب فروشگاه فقط از طریق «آزمایشگاه طراحی» یا با اعمال یک قالب کامل جدید به آن‌ها دسترسی دارد، نه با یک دکمهٔ ثابت و همیشه در دسترس مثل هدر و فوتر.

**۳. W5 قرار است دقیقاً چه چیزی به محصول اضافه کند؟**

مهم‌ترین بخش W5 یک اصلاح مشخص است: «نویگیشن پایین صفحه در موبایل» (Bottom Navigation) در ویرایشگر اصلی و پیش‌فرض فروشگاه اصلاً قابل تغییر نیست — فقط از ویرایشگر قدیمی یا آزمایشگاه طراحی قابل دسترسی است. W5 این را در ویرایشگر اصلی هم در دسترس می‌کند. علاوه بر آن، W5 پیش‌نمایش قالب‌ها را کمی بهتر می‌کند (بزرگ‌نمایی در همان صفحه، پیش‌نمایش موبایل/دسکتاپ پیش از انتخاب قالب)، و دو تصمیم محصولی را از شما می‌خواهد: آیا «منوی مگا» (Mega Menu) باید یک قابلیت واقعی و مستقل شود یا همان‌طور که هست (وابسته به انتخاب هدر) بماند؛ و آیا نام دو مفهوم مختلف که هر دو «Template» نامیده می‌شوند باید برای جلوگیری از سردرگمی تغییر کند.

**۴. وقتی W5 تمام شود، صاحب فروشگاه چه کارهایی می‌تواند انجام دهد؟**

همهٔ امکانات فعلی، به‌علاوه: تغییر مستقیم نویگیشن پایین موبایل از ویرایشگر اصلی؛ پیش‌نمایش بهتر قالب‌ها پیش از انتخاب؛ و (بسته به تصمیم شما) احتمالاً امکان انتخاب مستقیم هیرو/کارت محصول/نشان تبلیغاتی بدون نیاز به ورود به آزمایشگاه طراحی.

**۵. بعد از W5 چه بخش‌هایی از کل RastiSi هنوز باقی می‌ماند؟**

W5 فقط تجربهٔ طراحی فروشگاه را کامل می‌کند. بخش‌های دیگر RastiSi — مثل سیستم سفارش، پرداخت، حمل‌ونقل، مدیریت موجودی، گزارش‌ها، و بازاریابی — بخشی از این فاز (Phase 5) نیستند و در فازهای بعدی بررسی خواهند شد. همچنین، تصمیم دربارهٔ آیندهٔ ویرایشگر قدیمی (R3) و تغییر نام احتمالی یکی از دو مفهوم «Template» باید توسط شما گرفته شود؛ این‌ها هنوز باز هستند.

---

## 11. Change policy compliance

No production code, migrations, models, views, URLs, templates, JavaScript, CSS, services, registries, Ready Template definitions, renderer, mutation service, or Draft/Published behavior was modified during this discovery round. The only repository changes are this document and the four evidence documents listed at the top, plus a git-history-safe fast-forward of the local branch checkout to the already-existing, already-merged origin checkpoint (see §0) — no new commits were created.
