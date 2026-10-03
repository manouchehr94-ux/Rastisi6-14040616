# Phase 4 Architecture Audit — Storefront Builder & Legacy Convergence

**Status:** AUDIT ONLY. No production code, test code, or migration was changed to produce this document.
**Scope:** Read-only research across the entire `apps/storefront_builder/` domain plus its `apps/catalog/`, `apps/cart/`, and `apps/content/` integration surfaces, cross-checked against the approved architecture specs and the actual current code at the SHA below.

---

## 1. Executive summary

RastiSi's Storefront Builder has converged much further than the historical planning documents assume, but Phase 3's closure exposed the exact class of gap that remains: **individually-correct pieces that were never wired to each other end-to-end.** The audit's headline findings:

1. **The lifecycle/mutation-safety contract is genuinely unified** (`edit_revision`, `edit_history_service`, media reachability). Undo/Redo/Publish already run through one shared implementation for both legacy and R4 callers. This part of the "one canonical write contract" goal is essentially done.
2. **Three concrete parallel-authority defects exist and are new findings of this audit, not previously documented**: (a) `preset_service.apply_preset`/`reset_appearance_setting_to_baseline` write `appearance_config` directly, bypassing `appearance_authority_service`, and can silently erase the typed `store_appearance` manifest on any non-Ready-Template preset apply; (b) `resource_source.py`'s typed contract is used for R4 write-time ownership validation only — every read path (`render_service`, `section_data_service`) independently re-derives `brand_ids`/`collection_ids`/`data_source` semantics, and the two ownership-check implementations (legacy vs. R4) disagree on whether `category_ids` need ownership validation at all; (c) `appearance_authority_service.apply_ready_template_appearance` — the tested, designed-as-canonical Ready-Template application primitive — has **zero production callers**; `preset_service.apply_preset` reimplements the same three-step sequence inline, which is *why* defect (a) exists.
3. **The Home-only CSS dependency bug Phase 3 found and fixed for Brand/Collection is a widespread pattern, not an isolated incident.** A dedicated audit pass found the identical defect class in the **default Hero slider itself** (`hero_banner`'s default `overlay` variant and `image_slider`, both `page_types=ALL_PAGE_TYPES`, zero inline fallback, 100% dependent on `home.css`), plus `category_grid` (10 of its 11 display modes — including its plain-grid default, since that mode's `.tile` core box is also `home.css`-only; only `luxury_shortcuts` is confirmed cross-page-safe), `product_section`'s `campaign_band`/spotlight modes, and further section families (`multi_banner`, `promo_cards`, `blog_posts`, `amazing_offers`, `single_banner`, `image_text`, `faq`, `testimonials`, `trust_features`, `video_section`). This is the single largest concrete Phase-4 remediation surface by section count.
4. **R4 (the intended final editor) is functionally Home-only in code, but the underlying model/registry/render pipeline and the legacy editor already fully support all 6 page types.** `section_structure_service.py` and `r4_views.py` hardcode `StorefrontPage.PageType.HOME`; `r4_mutation_service.py` inherits this only transitively (it calls into `section_structure_service.py`, it does not hardcode Home itself); `r4_editor.js` has no page-switcher at all. This is a mechanical generalization, not new architecture — the pattern to copy already exists in `views.py::storefront_editor`.
5. **R4 has no live UI entry point today.** `StorefrontLayout.r4_editor_enabled` defaults `False`, and no dashboard nav link anywhere points at the R4 editor route. Every real merchant edit today goes through the legacy editor by construction, not by remaining technical necessity. This materially changes Phase-4 sequencing: legacy-retirement "usage evidence" cannot be gathered honestly until R4 is reachable, so **making R4 reachable is a precondition for the whole legacy-migration ladder**, not a parallel workstream.
6. Only **5 of 36** registered section types have an R4 `SettingsSchema`; only **3** have a typed `ResourceSource` adapter; only **2** (`brand_carousel`, `collection_tiles`) are Phase-3 browser-certified. **23 of 36** section types have no dedicated legacy settings-form write path either (the legacy form has 11 distinct field-parsing branches covering 13 keys, plus 2 banner-management-link-only keys, plus 9 context-aware page-restricted sections with no settings form at all) — their own specific fields are only editable by direct database/fixture manipulation today, not through any UI.
7. Ready Template DNA fidelity ("declared = persisted = effective") **was certified CLOSED in Phase 1** and remains true. The 50-Ready-Template count is **confirmed accurate** by direct re-derivation. Content-preserving Template Switch (the subject of a stale, never-implemented 2026-09-03 plan) **has never been built** and remains correctly deferred at every phase gate through Phase 3.
8. Media reachability (A05, the Phase-2 gap) is **confirmed CLOSED** — `MediaAsset.is_referenced()` now correctly scans the JSON-background and history/baseline-snapshot reference classes, tenant-scoped and fail-closed.
9. A real, previously undocumented gap: **Collection Index and Collection Detail share one `StorefrontPage.PageType.COLLECTION` composition slot**, but `collection_index.html` never renders the computed items — any section a merchant edits under "Collection" silently applies to both URLs while only ever being visible on Collection Detail.

None of these findings requires new architecture. Every one of them is closeable by extending an existing, already-proven contract to more callers/families — exactly the convergence model the binding Product Owner decisions require.

---

## 2. Exact starting repository / SHA

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Audit branch: `feature/phase4-architecture-audit`, created from and currently at `185166a138e47c012b3af7f53ea6bcb94fb84bd0` (commit subject: `docs: close storefront vertical slice phase3`)
- Verified before starting: `origin/feature/phase3-task7-task8` == `185166a1...`; `origin/backup/rastisi6-phase3-task8-final-20260907` == `185166a1...`; worktree clean; `e244619f395ebf0dbebc77d2033841e17f1cd099` (Phase-2 baseline) and `c34a04e71cc62d191d6fe8238ef4e6735fb6642f` (Phase-3 prep baseline) both confirmed ancestors of HEAD; `origin/main` unchanged at `973c1dc00bacb6f2f7d2604fa3880bb4d6250579`.
- No code was changed to produce this document. `git status --short` at time of writing shows only this new file (plus, if applicable, its sibling companion inventory).

---

## 3. Product Owner binding decisions (this session, override historical assumptions where they conflict)

1. **Clean convergence model** — family-by-family: existing implementation → identify canonical replacement → migrate → certify → *then* retire the redundant legacy path. No indefinitely-preserved co-equal systems.
2. **No important real data exists.** Stores/Products/demo content/Builder state/template state/QA data/seed data may be recreated from scratch. Do not design complex historical-data migration for current test/demo rows.
3. **Migration history is preserved** — no squash/reset/rewrite of Django migrations, even though data itself is disposable. Schema changes use normal forward migrations if genuinely needed.
4. **Phase 4 is architecture/migration only** — no new visual variants, no seasonal themes, no 50-template certification, no mass beautification. That is Phase 5.
5. **Business domain logic is not rewritten without need** — Product/pricing/stock/Cart/auth/tenant-domain-ownership stay authoritative; Builder consumes domain services and never becomes a parallel commerce system.

**Architectural prime directive (repeated from the audit brief, load-bearing for every finding below):** ONE CONCEPT = ONE CANONICAL STATE + ONE CANONICAL WRITE CONTRACT + ONE CANONICAL EFFECTIVE RESOLVER + ONE CLEAR OWNER. Compatibility adapters are acceptable temporarily; co-equal parallel authorities are not.

---

## 4. Documents reviewed

Specs (all read in full this session): `2026-08-31-storefront-builder-r4-design.md`, `2026-09-01-storefront-design-engine-50-templates-design.md` *(referenced via its downstream unified doc and plan; content confirmed consistent, not separately re-quoted)*, `2026-09-03-rastisi-storefront-builder-product-architecture.md`, `2026-09-03-rastisi-storefront-builder-unified-architecture-design.md`, `2026-09-04-golden-reference-storefront-design.md`, `2026-09-05-storefront-appearance-convergence-5-phase-design.md` *(read in a prior session this conversation; content already integrated into Phase 1-3 execution understanding)*, `2026-09-06-storefront-lifecycle-safety-phase2-design.md`, `2026-09-06-storefront-vertical-slice-phase3-design.md` *(read in a prior session this conversation)*.

Plans: `2026-09-03-storefront-unified-implementation-roadmap.md`, `2026-09-03-template-switch-preservation-implementation-plan.md` (read in full; **confirmed stale/unimplemented — see §5**), `2026-09-06-storefront-vertical-slice-phase3-implementation-plan.md` *(already deeply familiar from executing Phase 3 in this same session)*. The 50-templates implementation plan and the A8 template-DNA plan were used only indirectly (via the roadmap's summary and via direct code inspection of `a8_ready_templates.py`) to keep this audit's effort proportionate to Phase-4 relevance, per the instruction to treat that lineage as context for the intended final product, not as Phase-4 authorization.

Evidence: `docs/qa_evidence/storefront_appearance_convergence/{phase1,phase2,phase3}/final_gate.md`, `phase3/execution_ledger.md`, `phase3/task6_shared_contract.md`, `phase3/task7_browser_matrix.md`, `phase3/vertical_slice_inventory.md`.

Code (verified directly, not from documentation claims): `apps/storefront_builder/{models.py, section_registry.py, resource_source.py, variant_contract.py, settings_schema.py, views.py, r4_views.py, layout_preset_registry.py, a8_ready_templates.py, global_region_registry.py, storefront_appearance/{contracts,families,adapters,registry,validation,compatibility,persistence,rendering,inventory}.py, services/{render_service,storefront_context_service,page_resolution_service,preset_service,r4_mutation_service,layout_service,edit_history_service,section_structure_service,container_service,appearance_authority_service,section_appearance_service,section_data_service,golden_reference_service}.py}`, `apps/content/{models.py, services.py, media_reachability.py}`, `apps/catalog/{views.py, urls.py}`, `apps/cart/{views.py, urls.py}`, `apps/storefront_builder/static/storefront_builder/r4_editor.js`, `tools/storefront_builder_r4_qa/run.mjs`, `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`, static CSS across `apps/catalog/static/css/`, `apps/storefront_builder/static/css/`, `apps/cart/static/css/`, `apps/core/static/css/`.

---

## 5. Conflicts / superseded assumptions

| # | Documents/claim involved | Actual current code behavior | Ruling | PO input needed? |
|---|---|---|---|---|
| 1 | 2026-09-03 "Template Switch Preservation" plan (`build_authored_baseline`, `draft_matches_own_baseline`, `apply_ready_template(mode=...)`) — an old, detailed, *pre-5-phase-program* plan | **None of these functions/kwargs exist anywhere in the codebase** (repo-wide grep: zero hits). `apply_preset` on a customized Draft still deletes/rebuilds page composition for every page the preset's recipe covers, and `HeroSlide`/`PromotionalBanner`/`StoryRailItem` use `on_delete=CASCADE` on their `section` FK, so merchant-authored section-scoped media on a touched page is destroyed unless the legacy checkpoint path (`apply_preset_with_checkpoint`) was used. | **Historical plan is superseded and was never implemented.** Content-preserving Template Switch is explicitly listed as an unstarted non-goal in the Phase 1, Phase 2, *and* Phase 3 final gates. Treat it as a real, still-open Phase-4/5 candidate, designed fresh against *current* code — not as a design to resume. | No — docs/code already resolve this; only a scoping decision on *when* (Phase 4 vs Phase 5) is left, addressed in §17. |
| 2 | Old unified-roadmap's 9-phase numbering (its own "Phase 1" = Safe Template Switching, "Phase 5" = R4 shell consolidation, etc.) vs. the later 5-phase convergence program's Phase 1/2/3 (Authority/Lifecycle/Brand-Collection, now closed) | These are **two different, non-overlapping numbering schemes** from different planning generations. The 5-phase program's Phase 3 just closed; this session's "Phase 4" continues *that* numbering, not the old roadmap's. | The old roadmap's phase numbers are obsolete; do not reference "Phase 1–9" from that document when planning actual work — use the 5-phase program's numbering (this is "Phase 4"). Some of the *content* of the old roadmap's Phase 1–3 (template preservation, deep editing, component selection UX) is still relevant scope for the real Phase 4/5, just needs renumbering and re-validation against current code (this audit does that validation). | No. |
| 3 | Unified-architecture spec's "~119 ComponentDefinitions across 10 families... library targets ~20 Header/~20 Footer/~30 Card variants" | Confirmed 119 `ComponentDefinition`s exist, but **~29 are pure marketing aliases** pointing at an *already-counted* underlying variant (13 hero aliases, 9 layout aliases, 7 product_view aliases) and **16 more are a CSS-token enum** (`card` styles) with no distinct template at all. Real distinct renderers: 22 header, 16 footer, 9 bottom_nav (all real), 6 hero (5 with a distinct template), 8 layout compositions, 6 product_view, 1 badge treatment, 3 motion tokens. | The spec's "library target" counts describe an *aspiration* for Phase 5 design expansion, not Phase-4 ground truth. Phase 4 must not treat the 119/78 figures as evidence of 119/78 real implementations — see §7/§9's classification discipline. | No — this is exactly what the audit brief anticipated ("a different key does not count as a new visual implementation"); already resolved by direct code inspection. |
| 4 | R4 design spec's invariant "Adding a normal new Variant must not require a new View branch/save endpoint/modal/JS lifecycle" | True for the 5 schema-enabled section types. **Not yet true for the other 31** — they have no R4 schema at all, so today they cannot be edited through R4 in any form, schema-driven or otherwise. This isn't a violation of the invariant (the invariant is about *adding a variant to an already-migrated family*), but conflates easily with "R4 already covers everything" if read loosely. | Invariant is intact and worth preserving; the audit clarifies it applies per-family, not platform-wide, and 31 families haven't reached that gate yet. | No. |
| 5 | Golden Reference spec's demo store (`rasti-mode-demo`) and its "G1" branch reference | `rasti-mode-demo` exists and is real; `golden_reference_service.py` implements exactly the composition described. The literal branch name `golden/g1-reference-storefront` no longer exists (deleted after merge), but its commits (`9ec56c6`, `b887465`, and the full `golden-g2`/`g2.1`/`g2.2` series) are confirmed ancestors of current HEAD via `git merge-base --is-ancestor`. | Not a conflict — just confirms the work landed and the branch was cleaned up normally after merge, which is expected repo hygiene, not lost work. | No. |
| 6 | Phase-2 spec's mutation-safety baseline evidence (STRONG/PARTIAL/MISSING classification) | Materially improved since that baseline was written: Undo/Redo/Publish are now unified between legacy and R4 (the spec's baseline called legacy undo/redo "MISSING" — now false). But new, narrower drift was found that the spec's original matrix predates: legacy Section/Block move/remove/duplicate do not check container-level locks the way R4's equivalents do, and the real R3 toolbar form never actually sends `base_revision` on publish (the capability exists in code but isn't wired to the live button). | Phase-2's exit gate is still substantively met; these are narrower residual items, correctly scoped as Phase-4 hardening rather than a reopened Phase-2 failure (per the master convergence program's own rule: reopen a closed phase only for a genuine blocking regression — these are pre-existing narrow gaps, not a regression Phase 3/4 introduced). | Yes — see §22 STOP-condition framing: whether to fix these three items *inside* Phase 4 or carry them as an explicit deferred ledger item is a scoping call for the Product Owner, not something the code answers. |

---

## 6. Current architecture map

```
                     Store Content / Commerce Truth (Catalog, Cart, Orders, Content apps)
                                          │  (read-only from Builder's perspective)
                                          ▼
        ┌───────────────────────── Storefront Builder domain ─────────────────────────┐
        │                                                                              │
        │  section_registry.py (36 section types, page composition)                   │
        │       ├─ 5 have R4 SettingsSchema; 3 have typed ResourceSource              │
        │       └─ 2 (Brand, Collection) are Phase-3 browser-certified                │
        │                                                                              │
        │  storefront_appearance/ (10 Design-DNA families, 119 ComponentDefinitions,   │
        │       78 "A8-advertised" keys — header/footer/bottom_nav/motion genuinely    │
        │       synchronized via appearance_authority_service; hero/product_view/      │
        │       card/badge are a one-directional render-time overlay only)            │
        │                                                                              │
        │  global_region_registry.py (22 header / 16 footer / 9 bottom-nav variants —  │
        │       the real implementation layer storefront_appearance wraps for those 3) │
        │                                                                              │
        │  layout_preset_registry.py + a8_ready_templates.py (50 real Ready Templates, │
        │       "recipe directive" layer composing the two registries above)           │
        │                                                                              │
        │  appearance_authority_service.py — the ONE certified write boundary for      │
        │       Global/Header/Footer Appearance (Phase 1). NOT yet the write boundary  │
        │       for Ready-Template application itself — see §9 finding H.             │
        │                                                                              │
        │  layout_service.py + edit_history_service.py — the ONE lifecycle/history     │
        │       authority (Draft/Published/Archived, edit_revision, Undo/Redo).        │
        │       Genuinely unified between legacy and R4 for Undo/Redo/Publish.         │
        │                                                                              │
        │  render_service.py — the ONE renderer (build_page_render_items).             │
        │       Confirmed: no second renderer exists anywhere. Preview/Public/Cart-    │
        │       fragment/merchant-preview-of-unpublished-product all call it.          │
        │                                                                              │
        │  Two editor generations, converging but not yet parity:                      │
        │       legacy (views.py, editor.html) — reaches all 6 page types, is the      │
        │            ONLY reachable editor today (r4_editor_enabled defaults False,    │
        │            no nav link to R4 anywhere)                                       │
        │       R4 (r4_views.py, r4_mutation_service.py, r4_editor.js) — stronger      │
        │            safety contract (base_revision/select_for_update), but            │
        │            hardcoded to Home only, and not linked from any live UI           │
        └──────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                         Preview (Draft) / Public (Published) — same renderer,
                         same wrapper, same templates, both reading through
                         storefront_context_service.build_universal_storefront_context
```

---

## 7. Complete registered family/section inventory

**Exact current count: 36 registered section types** in `apps/storefront_builder/section_registry.py` (a stale in-file comment claims 34 — 34 was correct at an earlier point; U4 added variants and the registry has since grown to 36; re-verify this count directly at implementation time rather than trusting any document, including this one, if further sections are added).

| key | classification | template/renderer | data source | domain owner | SettingsSchema | ResourceSource | variants | page_types | Phase-3 certified | legacy write branch | Phase-4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `hero_banner` | REAL (6 variants; 5 have distinct templates — Pattern B) | `hero_banner*.html` / shared `hero_slider_body.html` | `_hero_banner_context` (HeroSlide) | storefront_builder (content: `apps.content`) | **yes** | no | 6 | all 6 | no | yes | **HIGH PRIORITY**: fix Home-only CSS dependency for default `overlay` variant (§9/§16); add ResourceSource-equivalent media adapter; strongest candidate for next browser certification |
| `fashion_lifestyle_hero` | REAL (static-content) | own template | `_static_context` (fixed asset) | storefront_builder | no | no | 0 | home only | no | no | Low priority (Home-only by design, page_types restricted) |
| `image_slider` | REAL (shares hero_banner's data fetch, own template) | shares `hero_slider_body.html` | `_image_slider_context`→`_hero_banner_context` | storefront_builder | no | no | 0 | all 6 | no | yes (shares hero_banner branch) | Same CSS fix as hero_banner (identical root cause) |
| `single_banner` | REAL | own template | `_single_banner_context` (PromotionalBanner) | storefront_builder/content | no | no | 0 | all 6 | no | banner-mgmt link only | Fix Home-only CSS (`.promo-dark`) |
| `multi_banner` | REAL | own template | `_multi_banner_context` | storefront_builder | no | no | 0 | all 6 | no | banner-mgmt link only | Fix Home-only CSS (`.promo-grid--*` layout-variant classes are `home.css`-only) |
| `category_grid` | REAL (11 display_modes, Pattern A) | own template | `_category_grid_context` (Category) | catalog | no | no | 11 | all 6 | no | yes | Fix Home-only CSS for 10 of 11 display_modes — the shared `.tile` core box is `home.css`-only, so even the plain-grid default mode is affected; only `luxury_shortcuts` is confirmed cross-page-safe |
| `featured_products` | **MARKETING ALIAS** of `newest_products` | own template, identical data | delegates to `_newest_products_context` (no `is_featured` field exists) | catalog | no | no | 0 | all 6 | no | no | Document as alias explicitly; do not count as a distinct family in any future inventory |
| `newest_products` | REAL | own template | `_newest_products_context` | catalog | no | no | 0 | all 6 | no | no | Candidate for R4 schema (simple auto-source pattern) |
| `best_sellers` | REAL | own template | `_best_sellers_context` (real order-derived service) | orders/catalog | no | no | 0 | all 6 | no | no | Candidate for R4 schema |
| `discounted_products` | REAL | own template | `_discounted_products_context` | catalog | no | no | 0 | all 6 | no | no | Candidate for R4 schema |
| `amazing_offers` | REAL (no UI edit path for its own fields today) | own template | `_amazing_offers_context` | storefront_builder | no | no | 0 | all 6 | no | no | Fix Home-only CSS; needs a legacy or R4 settings write path before Phase-4 migration |
| `brand_carousel` | **REAL, Phase-3 certified** | own template | `_brand_carousel_context` (Brand) | catalog | **yes** | **yes** | 3 | all 6 | **YES** | yes | Already done; `beauty_tabs` variant still has a cosmetic-only (non-structural) Home-only CSS gap for tab-chip styling |
| `promo_cards` | REAL | own template | `_category_context_for_promo_cards` | catalog | no | no | 0 | all 6 | no | no | Fix Home-only CSS |
| `rich_text` | REAL | own template | `_static_context` | storefront_builder | **yes** | no | 0 | all 6 | no | yes | Safe (inline-styled) |
| `image_text` | REAL | own template | `_resolved_destination_context` | storefront_builder | no | no | 2 | all 6 | no | yes | Fix Home-only CSS — closest analogue to Phase-3's exact root cause (inline override doesn't match the external rule's actual mechanism) |
| `blog_posts` | REAL | own template | `_blog_posts_context` (BlogPost) | blog | no | no | 0 | all 6 | no | no | Fix Home-only CSS |
| `product_section` | **REAL, R4-schema-enabled** | own template | `_product_section_context` | catalog | **yes** | **yes** | 3 | all 6 | no | yes | Fix Home-only CSS for `campaign_band` and spotlight-carousel modes; otherwise strong Phase-4 candidate (already has schema+ResourceSource) |
| `catalog_product_wall` | REAL (Ready-Template-oriented) | own template + 2 variant partials | `_catalog_product_wall_context` | catalog | no | no | 3 | home only | no | no | Low priority (Home-restricted) |
| `trust_features` | REAL (no UI edit path) | own template | `_static_context` | storefront_builder | no | no | 0 | all 6 | no | no | Fix Home-only CSS |
| `collection_tiles` | **REAL, Phase-3 certified** | own template | `_collection_tiles_context` (MerchantCollection) | catalog | **yes** | **yes** | 2 | all 6 | **YES** | yes | Already done |
| `quick_links` | REAL | own template | `_quick_links_context` (Menu) | content | no | no | 0 | all 6 | no | yes | Safe |
| `faq` | REAL (no UI edit path) | own template | `_static_context` | storefront_builder | no | no | 0 | all 6 | no | yes | Fix Home-only CSS |
| `testimonials` | REAL (no UI edit path) | own template | `_static_context` | storefront_builder | no | no | 0 | all 6 | no | yes | Fix Home-only CSS |
| `video_section` | REAL | own template | `_video_section_context` | storefront_builder | no | no | 0 | all 6 | no | yes | Fix Home-only CSS (`.video-embed-wrap` aspect-ratio box) |
| `story_rail` | REAL (no UI edit path; safe — uses globally-loaded `tokens.css`) | own template | `_story_rail_context` | content | no | no | 0 | all 6 | no | no | No CSS fix needed; still needs a settings write path |
| `newsletter` | REAL | own template | fallback `_static_context` | storefront_builder | no | no | 0 | all 6 | no | yes | Safe (inline-styled); no render-context builder exists — falls to generic default |
| `announcement_bar` | LEGACY (hidden_from_library — superseded by header notification bar) | own template | `_static_context` | storefront_builder | no | no | 0 | all 6 | no | no | Candidate for explicit deprecation documentation (not deletion — still functions) |
| `product_main` | REAL, mandatory, context-aware | own template | `_product_main_context` (page_context) | catalog | no | no | 0 | product_detail only | no | n/a | Safe by construction |
| `product_description` | REAL, mandatory, context-aware | own template | `_product_description_context` | catalog | no | no | 0 | product_detail only | no | n/a | Safe by construction |
| `product_video` | REAL, context-aware | own template | `_product_video_context` | catalog/content | no | no | 0 | product_detail only | no | n/a | Safe by construction |
| `related_products` | REAL, context-aware | own template | `_related_products_context` | catalog | no | no | 0 | product_detail only | no | n/a | Safe by construction |
| `product_listing` | REAL, mandatory, context-aware | own template | `_product_listing_context` | catalog | no | no | 0 | listing+search | no | n/a | Safe; HTMX-fragment context-propagation gap noted in §11 |
| `collection_header` | REAL, context-aware | own template | `_collection_header_context` | catalog | no | no | 0 | collection only | no | n/a | Safe by construction; see §12 Collection-Index conflation |
| `collection_products` | REAL, mandatory, context-aware | own template | `_collection_products_context` | catalog | no | no | 0 | collection only | no | n/a | Safe by construction; see §12 |
| `cart_items` | REAL, mandatory, context-aware | own template | `_cart_items_context` | cart | no | no | 0 | cart only | no | n/a | Safe by construction |
| `cart_summary` | REAL, mandatory, context-aware | own template | `_cart_summary_context` | cart | no | no | 0 | cart only | no | n/a | Safe by construction |

**Storefront Appearance component registry (a different, parallel-purpose system — see §9 for the relationship):** 10 families declared, exactly **119** `ComponentDefinition`s synthesized (22 header + 1 mega_menu-none + 19 hero incl. 13 aliases + 17 layout incl. 9 aliases + 13 product_view incl. 7 aliases + 17 card incl. 16 CSS-token "styles" + 2 badge + 3 motion + 16 footer + 9 bottom_nav), of which **78** are "A8-advertised." Real distinct renderers underneath the alias inflation: 22 header, 16 footer, 9 bottom_nav (all genuinely distinct), 6 hero (5 with a distinct template), 8 layout compositions, 6 product_view, 1 badge treatment, 3 motion tokens.

**`layout_preset_registry.py` + `a8_ready_templates.py` (Ready Templates):** 13 presets registered directly (5 non-Ready `is_ready_template=False` + 8 early Ready ones), plus 50 more via `a8_ready_templates.py`'s import (8 of which are version-bumped re-registrations of the early 8). **Net: exactly 50 distinct `is_ready_template=True` keys** — the historical "50 templates" claim is confirmed accurate, not stale.

---

## 8. Canonical ownership matrix

| Concept | Intended canonical owner | Actual current owner(s) | Parallel today? | Legacy paths | Phase-4 action | Final owner |
|---|---|---|---|---|---|---|
| A. Store Appearance manifest/state | `storefront_appearance.persistence.persist_store_appearance_manifest` | Same for all production writers | **TEMPORARY ADAPTER/UNKNOWN** — storage is converged, but an upstream bug (see H) can erase it | Legacy header/footer editors call `appearance_authority_service.apply_header_variant`/`apply_footer_variant`, which re-syncs correctly | Fix `preset_service.apply_preset`'s direct write so it always routes through the authority service (fixes both B and H) | `appearance_authority_service` + `storefront_appearance.persistence` |
| B. Global Appearance (palette/typography/motion/etc.) | `appearance_authority_service.apply_appearance_patch` | Converged for legacy view + R4; **`preset_service.apply_preset`/`reset_appearance_setting_to_baseline` bypass it**, writing `draft.appearance_config` directly via `layout_service.validate_appearance_config`, which silently drops the opaque `store_appearance` key | **YES (narrow but real)** | None — this is a preset-service-internal shortcut, not a legacy compatibility path | Route `preset_service`'s appearance overlay through `apply_appearance_patch`/`apply_ready_template_appearance` | `appearance_authority_service.apply_appearance_patch` |
| C. Page Appearance (page-level override tier) | N/A | N/A | **NO — does not exist** | N/A | Design decision, not a convergence fix: does Phase 4/5 want this layer at all? | Not yet built |
| D. Section/component local Appearance overrides | `section_appearance_service.resolve_section_appearance` | Same, single caller | NO | N/A | Converged; scope (typography-only) is a Phase-4/5 candidate to generalize, not a duplication to fix | `section_appearance_service` |
| E. Component variants (`variant_contract.py`) | `variant_contract.resolve_active_variant`/`resolve_renderer_template` | Same, single caller, with a documented `variant_explicit` precedence marker vs. the Store-Appearance family overlay | NO (see G' below for the render-time overlay nuance) | N/A | Converged — this precedence pattern (server-derived explicit-override marker) is the right model to copy for any future generalization | `variant_contract.py` |
| F. Section content/settings (`StorefrontSection.settings`) | `SectionDefinition.validate_settings`, schema-wrapped by `settings_schema.clean_section_schema_patch` | Same by construction (R4's schema cleaner always defers to `validate_settings` as final authority) | TEMPORARY ADAPTER (by design — the Strangler bridge) | 23 of 36 sections have no dedicated write UI at all (§7) | Extend schema coverage; the bridge itself is sound and should be kept as-is | `SectionDefinition.validate_settings` |
| G. ResourceSource / brand_ids / collection_ids / product sources | `resource_source.py` (typed contract, single semantic definition) | **Split**: `resource_source.py` used only for R4 write-time ownership validation; `render_service`/`section_data_service` independently re-derive the same semantics for reading; legacy and R4 ownership checks disagree on `category_ids` | **YES** | `views.py::_validate_universal_selection_ownership` (legacy) vs. `r4_mutation_service._validate_resource_source_ownership` (R4, `category` deliberately no-ops) | Route rendering through `resource_source.py`'s adapters; unify the two ownership checks into one function | `resource_source.py`, extended to own the read side |
| G′. Store-Appearance `hero`/`product_view`/`card`/`badge` family selection vs. per-section settings | Undecided — currently a render-time overlay, no write-time reconciliation exists | `render_service._build_items_from_sections` overlays the family selection onto section-local settings at render time only, guarded by the `variant_explicit` flag (same pattern as E) | **TEMPORARY ADAPTER, currently safe** — no merchant-facing family-selector UI exists yet, so live drift risk is low, but the code path is production-wired | N/A | If Phase 4/5 ever exposes a family-selector UI for these 4 families, build the same write-time reconciliation `header`/`footer`/`bottom_nav`/`motion` already have (`apply_header_variant`-equivalent) before shipping it | Needs a new `apply_*_family_selection` function mirroring the header/footer pattern |
| H. Ready Template / DNA application | `appearance_authority_service.apply_ready_template_appearance` (built, tested, Phase-1-intended-canonical) | **Zero production callers.** `preset_service.apply_preset` reimplements the same 3-step sequence inline, differently (causing defect B) | **YES** | `golden_reference_service.py` calls bare `apply_preset` directly (a documented, scoped, one-off exception for the fixed demo store) | Wire `apply_preset` to delegate to `apply_ready_template_appearance` (this was literally "Task 5" of an earlier, never-finished plan) — fixes B as a side effect | `preset_service.apply_preset`, refactored to delegate |
| I. Draft state / J. Published state / K. History/restore/discard | `layout_service` + `edit_history_service` | Same, single implementation, Undo/Redo/Publish already unified between legacy and R4 | NO (converged) | Legacy `storefront_discard`/`storefront_restore` call the same service functions bare, with no `base_revision`-style staleness guard (arguably acceptable — see §21) | Optional hardening: add an explicit staleness check to discard/restore if Phase 4 wants full parity | `layout_service` + `edit_history_service` |
| L. Preview rendering / M. Public rendering / N. Fragment rendering | `render_service.build_page_render_items` via `storefront_context_service.build_universal_storefront_context` | Same, confirmed single call site for all 6 page types, Preview, and the Cart HTMX fragment | **NO — confirmed, no second renderer anywhere** | N/A | None needed at the renderer level; extend CSS/asset completeness per §16 | `render_service.py` |
| O. Cart fragment presentation | `apps/cart/views.py::_render_cart_container` | Same, goes through the full shared pipeline (`render_rows.html`), not a hardcoded partial | NO | N/A | None | `_render_cart_container` |
| P. Container/row/cell/placement state | `container_service.py` + `section_structure_service.py` | Legacy has the full model (multi-column containers, rows, arbitrary cell placement); **R4 has a strictly flatter model** (one section per new single-cell container, no row grouping) | **TEMPORARY ADAPTER (asymmetric, not competing)** — R4 is a subset, not a rival implementation | Every legacy container/cell/row view has no R4 equivalent at all | This is the largest actual feature gap for R4 parity — needs real design work before legacy container UI can be retired | Undecided — R4's composition model needs to grow, not converge onto legacy's |
| Q/R. Header/Footer selection & rendering | `appearance_authority_service.apply_header_variant`/`apply_footer_variant` → `global_region_registry` | Same; genuinely synchronized between legacy editor and Store-Appearance family selection | NO (converged) | N/A | None | `appearance_authority_service` |
| S. Mobile Bottom Navigation | Same as Q/R pattern (`bottom_nav` family) | Same | NO | N/A | None | `appearance_authority_service` |
| T. Product-card presentation | `product_card.css` (cross-page) + `card` Store-Appearance family (CSS-token overlay) | Converged for the CSS; the `card` family is part of the G′ render-time-overlay-only pattern | Same caveat as G′ | N/A | Same as G′ | `render_service` + `appearance_authority_service` (once G′ is built) |
| U. Media references/resolution | `MediaAsset.is_referenced()` + `content.services.delete_media_asset_if_unreferenced` | Same, **A05 gap confirmed CLOSED** this audit | NO | N/A | None — monitor only | `apps/content/media_reachability.py` |
| V. CSS asset ownership/loading | Intended: every section's CSS reachable on every page_type it's allowed on | **Actual: `home.css` silently owns the base layout CSS for ~13 section families/variants that declare `page_types=ALL_PAGE_TYPES`** | **YES — widespread, see §16** | N/A | Mirror the missing rules into `storefront_builder.css` (Brand/Collection's proven pattern) or restructure CSS ownership | `storefront_builder.css` (the only stylesheet already loaded on all 5 non-Home public templates) |
| W. JS/HTMX/Alpine ownership | `base.html` (global htmx/alpine) + per-section inline `x-data` | Confirmed converged; no section registers global/collision-prone JS state | NO | N/A | None | `base.html` + per-section Alpine scopes |
| X/Y. Old Builder routes/forms vs. R4 routes/forms | Converging (Undo/Redo/Publish done); still two separate mutation surfaces for everything else | See §13 legacy classification in full | **TEMPORARY ADAPTER**, converging | Every legacy view listed in §13 | R4 must reach parity (page-type generalization, container/cell model, media UI, toggles, granular reset) before any legacy retirement is evidence-backed | R4, once parity is real and it has a live UI entry point |
| Z. Template switches/reset/recipe application | `preset_service.py` (apply/reset family) | Converged at the *service* level; **two different orchestration contracts** at the call-site level (legacy: checkpoint + confirmation gate; R4: bare atomic apply, no checkpoint, no gate) | **YES (orchestration only, not data-outcome)** | Legacy `views.py::storefront_template_gallery` etc. | Decide whether R4's `appearance.template.apply` should gain the same confirmation-gate/checkpoint semantics, or whether the asymmetry is acceptable given R4's stronger in-Draft undo | Needs an explicit Product Owner/Architect ruling — see §22 |

---

## 9. Parallel-system / source-of-truth matrix

*(This section restates the concepts already covered in §8's table in the exact format the audit brief requested, for concepts not already fully covered above, plus a consolidated verdict list.)*

| Concept | Canonical intended owner | Actual owner(s) | Competing state? | Competing renderer? | Competing persistence? | PARALLEL AUTHORITY? |
|---|---|---|---|---|---|---|
| Store Appearance manifest | `appearance_authority_service` | Same, with one bypass (preset_service) | Partial (see B) | No | No — one JSON field, two write paths into it | TEMPORARY ADAPTER |
| Global Appearance | `appearance_authority_service.apply_appearance_patch` | `preset_service` bypasses it | Yes | No | No | **YES** |
| ResourceSource | `resource_source.py` | Split read/write | Yes (semantics re-derived twice) | No | No | **YES** |
| Ready Template application | `apply_ready_template_appearance` (designed, unused) | `preset_service.apply_preset` (actual) | No (one field, two code paths compute it) | No | No | **YES** |
| Renderer (Preview/Public/Fragment) | `render_service.build_page_render_items` | Same, confirmed single implementation | No | No | No | **NO** |
| Header/Footer/Bottom-Nav/Motion selection | `appearance_authority_service` ↔ `global_region_registry` | Same, genuinely synchronized | No | No | No | **NO (real compatibility adapter)** |
| Hero/Product-View/Card/Badge family selection | Undecided | Render-time overlay only, no write-time owner | Latent | No | No | **TEMPORARY ADAPTER (currently dormant/safe)** |
| Container/Row/Cell composition | `container_service`/`section_structure_service` | Legacy = full model; R4 = subset | No (R4 is a strict subset, not a rival) | No | No | **NO (asymmetric maturity, not parallelism)** |
| Lifecycle/mutation safety contract | `edit_revision` + `edit_history_service` + `layout_service` | Unified for Undo/Redo/Publish; legacy still thinner on atomicity/lock-parity for a few structure ops | Narrow | No | No | **TEMPORARY ADAPTER, converging** |
| Media reachability | `MediaAsset.is_referenced()` | Same, single implementation | No | No | No | **NO** |
| CSS ownership for cross-page sections | Should be `storefront_builder.css` | Actually `home.css` for ~13 families/variants | Yes (two files claim to define the same section's base layout, only one is loaded off-Home) | No | No | **YES (asset-loading parallelism, not code-architecture parallelism, but produces the same class of bug)** |

---

## 10. Writer inventory

Concept → current writers → canonical writer → delegate/migrate/retire disposition:

| Concept | Current writers | Canonical writer | Disposition |
|---|---|---|---|
| Global/Header/Footer Appearance | Legacy `storefront_appearance_editor`/`storefront_header_editor`/`storefront_footer_editor`; R4 `appearance.update`/`header.update`/`footer.update`; `preset_service.apply_preset` (bypass) | `appearance_authority_service.apply_appearance_patch`/`apply_header_variant`/`apply_footer_variant` | Legacy+R4: DELEGATE (already correct). `preset_service`: MIGRATE (fix the bypass). |
| Section settings | Legacy `storefront_section_settings` (13 keys have a real field-parsing branch, spread across 11 distinct branches since `hero_banner`/`image_slider` share one; 2 more get a banner-management-link-only branch; the rest fall to a generic `else`); R4 `_apply_section_update_settings` (5 schema-enabled keys only) | `SectionDefinition.validate_settings`, schema-wrapped | DELEGATE for the 5+13 covered keys; MIGRATE (add schema/write-path) for the remaining ~23 |
| Structure (add/remove/duplicate/move/reorder) | Legacy `storefront_section_*` (all 6 page types, full container/cell/row model); R4 `section_structure_service` (Home only, flatter model) | Converging on R4's contract, but R4 must grow page-type + composition-model parity first | MIGRATE (R4 needs to reach feature parity before this can flip) |
| Toggle/collapse/lock | Legacy `storefront_section_toggle`/`collapse_toggle`/`lock_toggle` | None in R4 | MIGRATE THEN RETIRE (new R4 mutation types needed) |
| Publish | Legacy `storefront_publish` (optionally delegates to R4's stale-aware wrapper, but the real UI form never sends `base_revision`); R4 `publish_draft` | `layout_service.publish`, stale-aware via `r4_mutation_service.publish_draft` | KEEP AS FINAL (service level); wire the legacy form to send `base_revision` for full parity |
| Undo/Redo | Legacy `storefront_undo`/`storefront_redo`; R4 `apply_history_command` | `r4_mutation_service._run_history_command` (shared) | **Already converged — KEEP AS FINAL** |
| Discard/Restore | Legacy only (`storefront_discard`/`storefront_restore`) | `layout_service.discard_draft`/`restore_version` | MIGRATE THEN RETIRE (needs R4 mutation types — services themselves are already sound) |
| Ready Template apply/reset | Legacy `apply_preset_with_checkpoint` (checkpoint + confirmation gate); R4 `appearance.template.apply` (bare, no checkpoint/gate); `golden_reference_service` (one-off, documented exception) | Should converge on one orchestration contract | UNKNOWN — NEEDS PRODUCT OWNER RULING (see §22) |
| Section-scoped media (Hero slides/Banners/Story items) | Legacy `media_views.py` only | None in R4 | R4 has no Replacement Contract yet — UNKNOWN, not a near-term retirement candidate |
| Container/Cell/Row composition | Legacy only | None in R4 | Same — no Replacement Contract yet |
| Resource ownership validation | Legacy `_validate_universal_selection_ownership`; R4 `_validate_resource_source_ownership` (disagree on `category`) | Should be one function | MIGRATE (unify) |

---

## 11. Renderer / Preview / Public / fragment map

Confirmed via direct trace (not documentation) for all 6 registered `StorefrontPage.PageType` values (Home, Listing, Search, Product Detail, Collection, Cart) plus the Collection Index route, which shares the Collection page-type slot rather than owning a distinct one of its own (see the finding below):

- **Exactly one renderer** (`render_service.build_page_render_items`/`build_default_render_items`), reached by every public view (`apps/catalog/views.py`, `apps/cart/views.py`) through the single `storefront_context_service.build_universal_storefront_context` entry point, and reached identically by Preview (`storefront_preview`), the dashboard's unpublished-product preview (`apps.dashboard.views.product_preview`), and the Cart HTMX fragment (`_render_cart_container`). **No second renderer exists anywhere** — confirmed by grep for any other function that iterates `StorefrontSection` objects and resolves a template.
- **Shell differences are legitimate**: `home_visual.html` extends `base.html` directly; the other 5 templates extend `storefront_shell.html` — both resolve header/footer through the identical `global_region_registry`, differing only in surrounding chrome, not in section rendering.
- **Two real gaps found**, both asset/wiring issues, not architecture issues:
  1. **Home-only CSS dependency is widespread** — see §16 for the full list (13 families/variants beyond the already-fixed Brand/Collection, including the *default Hero* itself).
  2. **Collection Index never renders Builder content** — `catalog/views.py::collection_index` computes `render_items`/`rows` via the shared pipeline exactly like every other page, but `collection_index.html` never includes `render_rows.html` — the computed items are silently discarded, and the template is 100% hand-written HTML with no `storefront_builder.css` even loaded. Compounding this: `collection_index` and `collection_detail` **share one `StorefrontPage.PageType.COLLECTION` slot**, so any section a merchant edits under "Collection" applies to both URLs but is only ever visually realized on Collection Detail.
  3. **Minor**: the Listing/Search HTMX partial-swap path (`product_list_results.html`, used for filter/pagination) returns before `build_universal_storefront_context` runs and never receives `card_settings`, so a merchant's card-style override on the `product_listing` section silently reverts to template default until the next full page load. Same template, same renderer — a context-propagation bug, not a parallel engine.

---

## 12. Non-Home Builder status

| Page type | Builder-controlled today | Domain-owned parts | Full-page editing possible? | Missing contract | Phase-4 migration needed |
|---|---|---|---|---|---|
| Product Detail | PARTIAL — real `StorefrontSection` rows, Draft/Published, add/remove/reorder all work **via the legacy editor only** | `build_product_detail_context` (gallery, variants, pricing, reviews) | Yes, legacy editor only | R4 page-type parameterization; R4 UI page switcher | Y |
| Listing | PARTIAL, same pattern | `build_product_listing_context` (filter/sort/pagination/facets) | Yes, legacy editor only | Same | Y |
| Search | PARTIAL, same pattern, shares Listing's view/section (`product_listing`, `page_types={LISTING,SEARCH}`) but is its own independent `StorefrontPage` row | Same as Listing | Yes, legacy editor only | Same | Y (document the Listing/Search page-identity split explicitly so Phase 4 doesn't "rediscover" it) |
| Collection Detail | PARTIAL, same pattern | `collection_service` queryset/visibility/pagination | Yes, legacy editor only | Same, plus the Collection-Index conflation (§11) | Y — plus a scoping decision on Collection Index |
| Cart | PARTIAL, same pattern, and the **most mature** non-Home page (HTMX re-renders already go through the full Builder pipeline) | `_cart_context` (pricing/totals) | Yes, legacy editor only | Same R4 gap | Y |

**Root cause, single sentence:** the data model, `section_registry.py`, `render_service.py`, and the legacy editor are already fully generalized to all 6 `StorefrontPage.PageType` values (each has real per-version `StorefrontSection` rows and a working Preview route); only the **R4 editor's mutation/structure services and its JS UI** are hardcoded to Home (`section_structure_service.py`'s own docstring: *"Every function here operates on the active Home Draft page only"*; `_home_page(draft)` calls `draft.get_page(PageType.HOME)` with no parameter; `r4_editor.js` has zero page-type handling). This is Phase 4's most tractable, highest-leverage single fix — a mechanical generalization copying an already-proven pattern from `views.py`, not new design.

---

## 13. Legacy classification

Full detail, disposition, and evidence-needed-for-retirement for every legacy mutation surface is recorded in the companion document referenced at the top of this file's evidence trail (produced by dedicated research this session); summarized here:

| Legacy surface | R4 equivalent exists? | Classification |
|---|---|---|
| Undo, Redo, Publish | Yes — **already the same shared implementation** | KEEP AS FINAL |
| Settings save, 5 schema-enabled types | Yes, functionally | TEMPORARY ADAPTER |
| Settings save, ~23 non-schema types | No | MIGRATE THEN RETIRE (needs schema work first) |
| Container/Cell/Row composition (add/settings/layout/move/remove, cell add-section/clear, row layout) | **No — R4 has no equivalent model at all** | UNKNOWN — NEEDS EVIDENCE (no Replacement Contract exists yet; this is a real feature gap, not a near-term retirement candidate) |
| Section toggle/collapse/lock | No | MIGRATE THEN RETIRE |
| Discard, Restore, History browser | No | MIGRATE THEN RETIRE (underlying services already atomic/safe — only the HTTP surface is missing) |
| Ready Template gallery / apply (curated templates) | Partial (R4 covers the same 8+42 curated templates but with a weaker orchestration contract — no checkpoint, no confirmation gate) | TEMPORARY ADAPTER |
| Internal/industry-vertical layout presets | No | UNKNOWN — NEEDS EVIDENCE (confirm live usage before deciding) |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | No | MIGRATE THEN RETIRE (services already atomic/checkpointed) |
| Full Appearance/Header/Footer editor forms (fields beyond R4's allowlist) | Partial | UNKNOWN — NEEDS EVIDENCE (field-by-field parity matrix required first) |
| Section-scoped media CRUD (Hero slides/Banners/Story items) | **No** | UNKNOWN — NEEDS EVIDENCE (no Replacement Contract; not a near-term candidate) |
| Legacy editor shell itself (`editor.html`) | Yes (R4 shell exists) but **R4 has zero live nav entry and defaults disabled** | KEEP AS FINAL until R4 is actually reachable — retirement cannot be evidenced before then |

**Compatibility mirrors found** (legitimate, not duplicated logic): `appearance_authority_service` writes both the typed manifest and the legacy `header_config`/`footer_config` JSON keys in one call — shared by both legacy and R4 callers, not two implementations. `r4_mutation_service`'s `_LEGACY_SELECTOR_FAMILIES`/`_sync_manifest_from_live_selectors` is the R4-side half of that same mirror. `settings_schema.clean_section_schema_patch` is an explicitly self-documented "Strangler bridge" that always defers to the section's own legacy `validate_settings` as final authority — correct by design, not a bug.

**Structural precondition, repeated from §1:** `r4_editor_enabled` defaults `False` and no dashboard navigation anywhere links to the R4 editor route. Every one of the "UNKNOWN — NEEDS EVIDENCE" rows above cannot honestly gather usage evidence until R4 is reachable by real merchants. **This is a precondition for the whole retirement ladder, not an independent Phase-4 task.**

---

## 14. Database / data strategy

- **Schema migration need: essentially none identified by this audit.** Every gap found (CSS loading, R4 page-type hardcoding, missing R4 schemas/mutation types, the appearance-write bypass) is closeable through code changes to existing models/services. No new field, table, or relationship was identified as required.
- **Data migration need: NONE**, consistent with the binding Product-Owner decision ("no important real data exists"). Any Phase-4 fixture/demo work should use fresh deterministic seeds (the existing `seed_ready_template_fashion_demo.py`/`apply_golden_reference_storefront.py`/QA-harness fixture patterns from Phase 3 are the templates to reuse — see §21).
- **Migration history:** must remain untouched (no squash/reset), per the binding decision — nothing in this audit's findings requires or suggests otherwise.
- If a genuine schema need surfaces during actual Phase-4 implementation (e.g., a real page-level appearance tier, §8 concept C, if the Product Owner decides to build it), it should be added via a normal forward migration, following the existing model's conventions (`StorefrontLayoutVersion`'s JSON-config pattern is the established idiom for this kind of typed, versioned, sparse-override state).

---

## 15. Phase-3 reusable-contract extraction

What Brand/Collection proved and what genuinely generalizes to other families:

**Truly reusable (apply to any Phase-4 family migration as-is):**
- The `ResourceSource` typed contract shape (`kind`/`mode`/`auto_rule`/`manual_ids`) and its ownership-validation pattern — once §9's read/write split is fixed, this becomes a real one-time investment other resource-driven families (`newest_products`, `best_sellers`, `discounted_products`, `promo_cards`) can adopt directly.
- The `settings_schema.clean_section_schema_patch` Strangler-bridge pattern — schema-clean, then defer to `validate_settings` — is the correct template for migrating any of the remaining 31 families.
- The `appearance_overrides.variant_explicit` server-derived precedence marker (never trust a client-supplied flag) — the exact right pattern for any future family-level override reconciliation (including the still-unbuilt hero/product_view/card/badge write-time sync, §8 concept G′).
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`'s environment plumbing (session cookie, manifest building, port management, SQLite backup/restore safety wrapper) and `run.mjs`'s generic scenario/navigation/screenshot/network-instrumentation helpers — fully family-agnostic already.
- The pattern of extending *existing* shared test modules with new test classes per family, rather than creating per-family test files — Brand/Collection did this cleanly (24 of 108 test modules reference them via added classes, not new files).
- The "record a genuine RED, escalate, get bounded authorization, fix narrowly, re-certify" protocol Task 7 demonstrated for the Collection CSS regression — this is exactly the right model for closing the Home-only CSS gaps found in §16: each fix is small, testable, and independently reviewable.

**Must NOT be generalized (family-specific, correctly kept separate):**
- Brand's business-domain query (`Brand.objects.filter(store=store, ...)`) and Collection's (`MerchantCollection` + membership/visibility semantics, `Count("items")` total-vs-visible distinction) are genuinely different domain services — a "generic resource family" abstraction over both would have hidden Collection's real semantic differences (Phase 3's own evidence explicitly warns against this: "Collection can invalidate a Brand-derived assumption").
- Page context shape differs legitimately per family (`collection_header`/`collection_products` consume route-resolved `collection`/`products`/`page_obj`; `cart_items`/`cart_summary` consume `_cart_context`'s cart/totals shape) — these must stay bespoke per context-aware section, not unified into one generic "page data" contract.
- Destination/View-all semantics (Brand's V02 capability rule: supporting variant AND trusted resolved destination) is Brand-specific business logic, not a generic "every family gets a View-all" pattern.
- Media semantics differ per family (Brand logo = `contain`+name-fallback; Collection tile = `cover`+folder-glyph-fallback) — CSS/objectFit expectations must be asserted per-family in any browser gate, never assumed shared.
- Count/selection semantics (Collection's total-membership-vs-visible-count distinction) is a deliberate, documented domain decision — never flatten this into a generic "item count" field across families.

**Minimum reusable Phase-4 contract, stated plainly:** typed `ResourceSource` (once unified) + `SettingsSchema`-via-Strangler-bridge + server-derived override-precedence marker + the existing R4 QA harness's generic helpers. Everything else (domain query, page context shape, destination rules, media fallback behavior, count semantics) is legitimately per-family work that must be redone for each new family, not shared.

---

## 16. Family-specific semantics that must NOT be generalized

(Consolidated from §15's second half, restated as its own section per the required report structure.) See §15 above — the five bullet points under "Must NOT be generalized" are the complete list identified by this audit. No additional family-specific semantics beyond those were found to be at risk of improper generalization.

**The Home-only CSS dependency findings (the largest concrete remediation item), listed by severity:**

| Section / variant | Severity | Missing CSS (home.css-only) | Inline fallback? |
|---|---|---|---|
| `hero_banner` default `overlay` variant + `image_slider` (shared partial) | 🔴 Critical — default section, `page_types=ALL_PAGE_TYPES`, zero inline fallback | `.hero`, `.hero-inner`, `.hero-slide`, `.hero-media`, `.hero-text`, `.hero-cta`, `.hero-arrow*`, `.hero-tabs` | No |
| `hero_banner` variants `atelier_triptych`/`beauty_editorial`/`chocolate_carousel`/`split` | 🔴 High | Variant-specific `.hero-*` classes | No |
| `hero_banner` variant `luxury_showcase` | ✅ Safe | Already fully mirrored in `storefront_builder.css` | N/A |
| `category_grid` (10 of 11 display_modes, incl. the plain-grid default) | 🔴 Critical | `.tile` core box (shared by the default mode) + 9 further themed display-mode classes | No |
| `product_section` `campaign_band` + spotlight-carousel modes | 🔴 Critical — flagship commerce block | `.product-campaign-band*`, `.product-spotlight-*` | No |
| `multi_banner` | 🔴 High | `.promo-grid--*` layout-variant classes | No |
| `promo_cards` | 🔴 High | `.tile`/`.wm` card chrome | No |
| `blog_posts` | 🔴 High | `.blog-card`, `.blog-grid` | No |
| `amazing_offers` | 🔴 High | All `.special-*` classes | No |
| `single_banner` | 🔴 High | `.promo-dark` | Partial (cosmetic only) |
| `image_text` | 🔴 High — closest analogue to Phase-3's exact bug shape | `.cream`/`.rack` | Partial, and the inline override doesn't even match the external rule's real mechanism |
| `faq` | 🔴 High | `.faq-list`, `.faq-item` | No |
| `testimonials` | 🔴 High | `.testimonial-list`, `.testimonial-card` | No |
| `trust_features` | 🔴 High | `.features`, `.feat` | No |
| `video_section` | 🟡 Medium | `.video-embed-wrap` | Partial |
| `brand_carousel` `beauty_tabs` | 🟡 Medium — structural fix already holds, cosmetic gap only | `.beauty-section-title`, `.brand-beauty-tab` | Partial |

Confirmed **safe** (no fix needed): `brand_carousel` (grid/carousel), `collection_tiles` (Phase-3 fixed), `story_rail` (globally-loaded `tokens.css`), `announcement_bar` (globally-loaded `layout.css`), `product_section`/`featured_products`/`newest_products`/`best_sellers`/`discounted_products`/`related_products`/`product_listing`/`catalog_product_wall` (already migrated onto `product_card.css`'s `.grid.rsec-cols` pattern in an earlier, pre-Phase-3 effort), `rich_text`/`newsletter`/`quick_links` (inline-styled by design).

---

## 17. Phase-4 vs Phase-5 boundary

**Phase 4 (architecture convergence/migration only):**
- Fix the three parallel-authority defects in §8/§9 (appearance-write bypass, ResourceSource read/write split, Ready-Template-apply dead-code/reimplementation divergence).
- Close the Home-only CSS dependency gap for the 13 flagged families/variants in §16 (asset-loading fix, not new design).
- Generalize R4's mutation/structure layer from Home-only to all 6 page types (mechanical, pattern already exists in `views.py`).
- Give R4 a live UI entry point (nav link + default-enable decision) — **precondition for evidencing any legacy retirement.**
- Extend R4 `SettingsSchema`/`ResourceSource` coverage to the next real candidates (`hero_banner`, `product_section` are already schema-enabled and are the strongest next browser-certification targets; `category_grid`/`newsletter` need schema work first).
- Extend the certified Task-7 QA harness pattern (extract the duplicated computed-layout/RTL/native-scroll/keyboard-focus assertion block into a shared helper; replace the single `manifest.phase3` boolean with a per-family gate list) to certify each newly-migrated family.
- Resolve the Collection Index / Collection Detail page-identity conflation (§11/§12) — either wire the index template to the renderer or explicitly scope "collection" to mean Detail only.
- Harden the three narrow lifecycle-safety drift items from §5 conflict #6 (legacy structure-lock container-check parity, legacy publish's unwired `base_revision`, legacy view atomicity) if the Product Owner elects to fold them into Phase 4 rather than defer them.
- Design (fresh, against current code — not the stale 2026-09-03 plan) a content-preserving Template Switch, if the Product Owner elects to bring this into Phase 4 rather than Phase 5.

**Phase 5 (design expansion — explicitly NOT Phase 4):**
- New visual variants beyond what's needed to fix the CSS gaps above.
- Seasonal/campaign themes (Yalda/Nowruz/Valentine, etc.).
- 50-Ready-Template visual/browser certification and diversity-gate work.
- Growing the `storefront_appearance` component library toward its stated targets (~20 header/~20 footer/~30 card variants) — the *registry mechanism* is Phase-4-relevant (fixing the write-time reconciliation gap, §8 concept G′), but *adding more variants* is Phase 5.
- Building the currently-nonexistent page-level Appearance tier (§8 concept C) unless the Product Owner explicitly pulls it into Phase 4 as a Draft-lifecycle-safety matter.
- A merchant-facing UI for the `hero`/`product_view`/`card`/`badge` family selectors (once G′'s write-time reconciliation exists, exposing it to merchants is a design/UX decision, not an architecture one).

Validated against the actual registry rather than accepted blindly: the audit confirms this boundary is consistent with what's actually built today — no item on the Phase-4 list above requires new visual design work, and no item on the Phase-5 list is required to close any of this audit's parallel-authority or CSS-completeness findings.

---

## 18. Proposed migration waves/order

Derived from dependency/risk analysis, not an arbitrary Product-Owner choice:

**Wave 0 — Foundation fixes (no dependencies, unblocks everything else; do first):**
- Fix the appearance-write bypass (`preset_service` → `appearance_authority_service.apply_ready_template_appearance`). Files: `preset_service.py`. Tests: `test_phase1_appearance_authority.py`, `test_preset_service.py`.
- Unify the `resource_source.py` read/write split and the legacy-vs-R4 ownership-check divergence. Files: `resource_source.py`, `render_service.py`, `section_data_service.py`, `r4_mutation_service.py`, `views.py`. Tests: `test_r4_resource_source.py`, `test_r4_resource_picker.py`.
- Give R4 a live UI entry point. Files: `apps/dashboard/templates/dashboard/base_admin.html` (nav), a `StorefrontLayout.r4_editor_enabled` default-flip decision. Tests: whatever navigation/permission test exists for the dashboard shell.
- **Rollback boundary:** each of these three is independently revertible; none touches migrations.
- **STOP condition:** if unifying ResourceSource ownership checks reveals that legacy `category_ids` ownership validation was masking a real tenant-isolation gap in R4, STOP and treat it as a security fix, not routine convergence.

**Wave 1 — R4 non-Home generalization (depends on Wave 0's UI entry point to be meaningfully testable by real usage, but is code-independent of it):**
- Parameterize `section_structure_service.py`/`r4_mutation_service.py`/`r4_views.py` by `page_type` instead of hardcoded Home.
- Add a page switcher to `r4_editor.js`/`editor.html`, reusing the legacy editor's existing `page_types` dropdown pattern.
- Resolve the Collection Index/Detail page-identity conflation.
- **Files likely affected:** `apps/storefront_builder/services/section_structure_service.py`, `services/r4_mutation_service.py`, `r4_views.py`, `static/storefront_builder/r4_editor.js`, `templates/storefront_builder/dashboard/r4/editor.html`, `apps/catalog/templates/catalog/collection_index.html`.
- **Tests required:** extend `test_r4_vertical_slice.py`/`test_r4_foundation.py` with non-Home page-type cases; new browser QA scenarios for at least one non-Home page per the extended Task-7 harness pattern.
- **Browser evidence required:** yes — this changes real merchant-facing editing behavior.
- **Retirement possible after this wave?** No — legacy structure/container UI still has no R4 equivalent (Wave 3).
- **Rollback boundary:** feature-flaggable via `r4_editor_enabled` per store; safe to revert independently.

**Wave 2 — CSS completeness (independently certifiable per family, can run in parallel with Wave 1):**
- Mirror the missing rules from `home.css` into `storefront_builder.css` for each of the 13 flagged families/variants in §16, following the exact Task-7 "no-op on Home, byte-for-byte matching values" pattern.
- **Files likely affected:** `apps/storefront_builder/static/css/storefront_builder.css` only (plus, per Task-7 precedent, any public template found missing a stylesheet load — none currently identified beyond the already-fixed Cart case).
- **Tests required:** extend the R4 QA browser harness's computed-layout assertions (once extracted into a shared helper, per §21) to each fixed family.
- **STOP condition:** if a fix is found to require more than a CSS mirror (e.g., a template restructure), treat that specific family as its own bounded task, not part of this wave's blanket CSS pass.
- **Retirement possible after this wave?** N/A (not a retirement wave).

**Wave 3 — R4 composition-model parity (largest, riskiest, do last among "make R4 real" work):**
- Design and build R4 equivalents for: multi-column container/cell placement, row grouping, section-scoped media CRUD (Hero/Banner/Story), section toggle/collapse/lock, discard/restore/history-browser mutation types, granular baseline reset.
- **Dependencies:** Waves 0-1 (a working, live, non-Home-capable R4 editor to build these into).
- **Files likely affected:** `container_service.py`, `section_structure_service.py`, a new `media` mutation surface in `r4_mutation_service.py`/`r4_views.py`, corresponding `r4_editor.js` UI.
- **Tests/browser evidence required:** extensive — this is genuinely new capability, not a mechanical port.
- **STOP condition:** if the container/cell model proves impossible to represent in R4's flatter mutation shape without a schema change, STOP and escalate — this is exactly the kind of "requires a new persisted state" decision that needs explicit Product Owner sign-off per the binding migration-history-preservation rule.

**Wave 4 — Legacy retirement (only after Waves 0-3 make retirement evidence-backed):**
- For each legacy surface classified MIGRATE THEN RETIRE in §13, gather real usage evidence (now possible, since R4 is live), write parity tests, retire in a dedicated cleanup commit per surface — never a blanket deletion.
- **Dependencies:** all prior waves, plus real production usage data showing R4 adoption.
- **STOP condition:** any surface still classified UNKNOWN — NEEDS EVIDENCE at this point must get that evidence gathered explicitly before retirement, never assumed safe because "R4 exists now."

**Wave 5 (optional, Product-Owner-gated) — Content-preserving Template Switch and the three narrow lifecycle-safety hardening items from §5/§17**, if pulled into Phase 4 rather than deferred.

---

## 19. Likely file-impact map by wave

| Wave | Primary files |
|---|---|
| 0 | `preset_service.py`, `resource_source.py`, `render_service.py`, `section_data_service.py`, `r4_mutation_service.py`, `views.py`, `base_admin.html` |
| 1 | `section_structure_service.py`, `r4_mutation_service.py`, `r4_views.py`, `r4_editor.js`, `dashboard/r4/editor.html`, `catalog/collection_index.html` |
| 2 | `storefront_builder.css` only |
| 3 | `container_service.py`, `section_structure_service.py`, `r4_mutation_service.py`, `r4_views.py`, `r4_editor.js`, new media-mutation surface |
| 4 | Legacy `views.py` functions, one deletion commit per retired surface, corresponding templates |
| 5 | `preset_service.py` (new preservation-mode logic, designed fresh), `layout_service.py`/`views.py` (lock-parity + `base_revision` wiring) if pulled in |

No wave requires a new app, a new top-level service module, or a schema migration under current understanding; Wave 3 is the one wave where a migration *might* become necessary and must be escalated rather than assumed.

---

## 20. Legacy retirement candidates

(Consolidated from §13; no deletion performed or proposed as final in this audit — every row below requires the evidence column before any actual retirement.)

| Candidate | Why redundant (once its wave completes) | Replacement | Current callers | Evidence required |
|---|---|---|---|---|
| `storefront_section_toggle`/`collapse_toggle`/`lock_toggle` | R4 will gain equivalent mutation types (Wave 3) | New R4 mutation types | Legacy editor UI only | Parity tests + zero remaining legacy-editor traffic |
| `storefront_discard`/`storefront_restore`/`storefront_history` | Underlying services already shared; only HTTP surface duplicated | New R4 mutation types wrapping the same services | Legacy editor UI only | Parity tests + usage evidence |
| Granular reset views (`storefront_section_reset`, etc.) | Underlying `preset_service.reset_*` already atomic/shared | New R4 mutation types | Legacy editor UI only | Parity tests |
| Container/Cell/Row legacy views | R4 will gain composition-model parity (Wave 3) | New R4 container/cell/row mutation types | Legacy editor UI only, **currently the sole path — no retirement before Wave 3 completes** | Full behavioral parity tests, including multi-column layouts |
| Section-scoped media CRUD (`media_views.py`) | R4 will gain a media mutation surface (Wave 3) | New R4 media mutation types | Legacy editor UI only, **currently the sole path** | Full CRUD parity tests |
| Internal/industry-vertical layout presets | Possibly unused | Unclear — needs a usage check first | Unknown until checked | Confirm whether any live store still uses `storefront_apply_industry_layout` |
| `announcement_bar` section | Superseded by header notification bar per its own `hidden_from_library` flag | Header's notification capability | Any store still using it | Confirm zero live stores reference it before any deprecation messaging |

**Not proposed for retirement by this audit:** the legacy editor shell itself, Undo/Redo/Publish views (already converged, not redundant), and anything in the "UNKNOWN — NEEDS EVIDENCE" bucket from §13 that has no Replacement Contract yet.

---

## 21. Test/browser certification strategy

Building directly on the certified Phase-3 R4 QA infrastructure (`apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` + `tools/storefront_builder_r4_qa/run.mjs`) — **no second harness is proposed**, per the binding architecture rule.

**What Phase 3 proved reusable as-is:** environment plumbing (session cookie, manifest, port/backup/restore safety wrapper), the `place(section_key)` fixture helper and baseline catalog seed, and the generic JS scenario/navigation/screenshot/network-instrumentation helper functions (`scenario()`, `assert()`, `capture()`, `waitSaved()`, `previewFrame()`, `attachNetworkInstrumentation()`, etc.).

**What must be generalized before certifying a third family (concrete, found this audit, not hypothetical):**
1. Extract the ~85-line computed-layout/RTL/native-scroll/keyboard-focus assertion block — currently copy-pasted near-verbatim between Brand's and Collection's harness functions — into one shared, parameterized helper (expected `objectFit`, applicable-or-not native-scroll check, element selectors as parameters).
2. Replace the single `manifest.phase3` boolean gate with a per-family gate list, and change the current nested-call structure (Collection's gate is literally called *from inside* the function still named `phase3BrandGate`) into a real loop over registered per-family gate functions.
3. Backfill the `NoOtherSectionBecomesSchemaEnabledTests`-style guard to cover every non-schema-enabled family explicitly (today only 2 of 31 are asserted), so a future accidental schema-enable of any family is caught by a fast unit test.

**Per-family gate template (same shape Brand/Collection already used, repeat for each Phase-4 family):** Domain → Resource/data contract → typed settings (R4 `SettingsSchema`) → canonical mutation (R4 `_apply_section_update_settings`, extended once page-type-generalized) → Draft/Published (already generic) → renderer (already generic — zero work) → relevant full pages (extend the per-page registry/dispatch/asset test, same pattern as Task 3/5) → fragment where applicable (Cart, reusing `_render_cart_container` — already generic) → CSS/JS/media (fix per §16, then assert via the extracted shared helper) → Preview/Public (already generic) → desktop/tablet/mobile (already generic, reuse `PHASE3_VIEWPORTS`).

**Sequencing recommendation:** certify `hero_banner` next (already schema-enabled, already has ResourceSource-adjacent media, is the single highest-blast-radius CSS fix from §16, and already has partial legacy browser-scenario coverage in `run.mjs`'s scenarios 02/03 to build from) before `product_section` (also schema-enabled) before the schema-less families (`category_grid`, `newsletter`, etc., which need R4 schema work first per §7).

---

## 22. Risks and STOP conditions

Carried forward from the binding program-wide rules, applied specifically to Phase-4 scope:

- **STOP if** fixing the ResourceSource read/write unification (Wave 0) reveals that R4's `category` no-op is an actual, currently-exploitable tenant-isolation gap (not just an inconsistency) — escalate as a security fix, do not fold silently into routine convergence.
- **STOP if** R4's composition-model parity work (Wave 3) cannot represent legacy's Container/Cell/Row model without a schema migration — this requires explicit Product Owner sign-off before proceeding, per the migration-history-preservation rule.
- **STOP if** any CSS-completeness fix (Wave 2) is found to require more than a stylesheet mirror (e.g., a markup/template restructure) — treat that family as its own bounded, separately-reviewed task, not part of the blanket CSS pass.
- **STOP if** enabling R4 by default (Wave 0/1) surfaces a regression in the existing legacy-vs-R4 Undo/Redo/Publish unification — that convergence is Phase-2-certified and must not silently degrade.
- **Do not** treat "old test/demo data needs compatibility" as a reason to keep any parallel architecture — per the binding decision, fresh deterministic seeds are always available (the Phase-3 `_prepare_phase3_*_gate` fixture pattern and `apply_golden_reference_storefront.py` are the templates to reuse for any new family's QA fixtures).
- **Do not** retire any legacy surface classified UNKNOWN — NEEDS EVIDENCE in §13/§20 without first gathering that evidence — "R4 now exists" is not itself evidence of safe retirement.
- **Do not** let Wave 2's CSS fixes regress Home — every fix must use the exact "byte-for-byte matching value, no-op on Home" verification pattern Task 7 already proved, with the same computed-style Home-unchanged guard test.
- **Genuine architecture-ambiguity risk requiring Product Owner input (not resolvable from code alone):** whether to fold the content-preserving Template Switch design and the three narrow lifecycle-safety drift items (§5 conflict #6) into Phase 4 or explicitly defer them to a later decision — this audit surfaces the evidence but does not recommend a specific answer, since it is a scope/priority call, not a technical one.

---

## 23. Open questions (genuinely unresolved by docs/code)

1. **Should R4's Ready-Template application gain the legacy path's checkpoint + confirmation-gate semantics, or is the current asymmetry (R4 relies on its capped in-Draft undo stack only) an acceptable, permanent design choice?** Code shows both paths are individually safe; only a product decision resolves which orchestration contract is "the" canonical one going forward.
2. **Is the internal/industry-vertical layout-preset installer (`storefront_apply_industry_layout`, distinct from the 50 curated Ready Templates) still a live, used feature, or a candidate for explicit deprecation?** No code-level usage-frequency signal exists in this repo to answer this from static analysis alone; requires checking real store data or asking the team.
3. **Does Phase 4 want a page-level Appearance override tier (§8 concept C) at all, or should page-level customization remain expressed only through section-local overrides plus store-wide Global Appearance?** Nothing in the current architecture implies an answer either way — this is a genuine open product-design question, not a convergence gap.
4. **Should the `hero`/`product_view`/`card`/`badge` Store-Appearance families ever get a merchant-facing selector UI (which would require building the missing write-time reconciliation, §8 concept G′), or are they intended to remain Ready-Template-recipe-only, never merchant-editable directly?** The code is silent on intent here; it currently just doesn't expose a UI, which is consistent with either future.

No other open questions were identified — every other ambiguity this audit encountered was resolvable by direct code inspection and is answered in the sections above.

---

## 24. Recommended authoritative Phase-4 target architecture

1. **One appearance write boundary, no exceptions:** every code path that touches `appearance_config`/`header_config`/`footer_config`/the typed `store_appearance` manifest — including `preset_service.apply_preset` and its reset family — goes through `appearance_authority_service`. No direct `layout_service.validate_*_config` call from outside that service.
2. **One ResourceSource semantic layer, read and write:** `resource_source.py` owns the `kind`/`mode`/`auto_rule`/`manual_ids` interpretation and the single ownership-validation function; `render_service`/`section_data_service` consume it instead of re-deriving the same semantics.
3. **One Ready-Template application orchestration:** `preset_service.apply_preset` delegates to `appearance_authority_service.apply_ready_template_appearance` for the appearance/header/footer/manifest steps (fixing #1 as a side effect); the checkpoint-vs-no-checkpoint question (open question #1) is resolved explicitly, not left as an accident of which entry point a merchant happens to use.
4. **R4 is page-type-generic**, mirroring the legacy editor's existing 6-page-type support, with a live default-on (or clearly-communicated opt-in) UI entry point.
5. **`storefront_builder.css` is the complete cross-page CSS surface** for every section family whose `page_types` include more than Home — `home.css` becomes purely Home-specific presentation polish, never a hidden dependency for a cross-page-eligible section's base layout.
6. **The lifecycle/mutation-safety contract reaches full parity** between legacy and R4 for atomicity and structure-lock enforcement (or the legacy paths needing this are explicitly retired once R4 covers them — Wave 3/4), and the real legacy publish UI is wired to send `base_revision` for the same staleness protection R4 already has.
7. **Family migration to full Phase-3-grade certification** (typed schema + ResourceSource + browser matrix) proceeds one family at a time, in the dependency order recommended in §21, each independently reviewable and committable — never a single undifferentiated "migrate everything" change.
8. **No new registry, no new renderer, no new persistence model, no new Draft lifecycle** is introduced anywhere in this target architecture — every fix extends an existing, already-designed contract to more callers.

---

## 25. Recommended structure for the future ONE Master Implementation Prompt

When the Product Owner/Architect are ready to author the single future Master Implementation Prompt for Phase 4, it should:

1. **Bind to this audit document and this exact starting SHA** (`185166a138e47c012b3af7f53ea6bcb94fb84bd0`, or a later, explicitly-verified descendant), the same way the Phase-3 master prompt bound to the Phase-3 design/plan pair.
2. **Sequence work by the waves in §18**, with each wave as its own task boundary carrying: preconditions, exact allowed-file list (mirroring the discipline every Phase-1/2/3 task used), RED-before-GREEN requirement for changed behavior, an independent review gate, evidence file, and a bounded commit — internal gates inside the one master prompt, not a single unreviewable mega-diff.
3. **Explicitly resolve, or explicitly defer with a named owner, each of the four open questions in §23** before Wave 0 begins — do not let the implementing agent invent an answer mid-task.
4. **Repeat the exact STOP-condition discipline Phase 3 used**: if a wave's own implementation reveals a genuine blocking regression or an architecture ambiguity every safe path is guesswork on, STOP, record RED evidence, and escalate rather than silently deciding.
5. **Require the extended R4 QA harness (§21) to be the sole test/browser infrastructure** for every family certified during Phase 4 — explicitly forbid a second harness, mirroring this program's existing hard rule.
6. **Carry forward the binding Product-Owner decisions verbatim** (no important real data; migration history preserved; architecture/migration only, no Phase-5 design work; business domain logic untouched) as non-negotiable constraints on every wave.
7. **Name Wave 4 (legacy retirement) as conditionally scoped** — it only proceeds once its specific evidence requirements (§20) are actually gathered from a live R4 that Wave 0/1 made reachable; the master prompt should not pre-authorize any specific deletion, only the process for approving one once evidence exists.

---

## 26. Reviewer findings

A fresh-context reviewer, with no prior involvement in drafting this document, independently re-derived the ten highest-stakes claims directly against the current code (not against this document's prose): the 36-section count, the 5-SettingsSchema set, the 3-ResourceSource set, the 50-Ready-Template count, the Concept-B appearance-manifest-erasure mechanism, the R4 Home-hardcoding claim, the zero-live-UI-entry-point claim, three of the Home-only-CSS findings, the Collection-Index rendering gap, and the media-reachability A05 closure. **All ten were CONFIRMED** against the actual source (file:line citations independently re-verified, not merely re-quoted).

The reviewer found **0 CRITICAL** issues — no claim in the document was fabricated, and no cited file:line reference pointed at code that didn't say what the document claimed. It found **4 IMPORTANT** issues, all now corrected in this revision:

1. §7's `category_grid` row originally claimed "8 of 11 display_modes" need a CSS fix with "the plain grid mode" listed as safe — but the plain-grid default mode shares the same `.tile` core box that's `home.css`-only, so it is *not* safe; only `luxury_shortcuts` is confirmed cross-page-safe (10 of 11 affected, not 8 of 11 with a false extra safe mode). **Corrected** in §1, §7, and §16.
2. `multi_banner` was described in three places as having its Home-only CSS gap "self-documented in the registry's own code comment as a known unresolved instance." The reviewer traced the actual comment (`section_registry.py` near the `multi_banner` definition) and found it documents an *unvalidated `layout_variant` settings key* from an earlier hardening pass — it does not document a CSS-loading gap at all. The underlying CSS finding (`.promo-grid--*` classes are `home.css`-only) is independently confirmed and real; only the "self-documented" framing was incorrect. **Corrected** — the fabricated corroboration was removed in §1, §7, and §16, leaving the CSS finding itself intact and still flagged.
3. §1's summary said "8 of 10 display modes" for `category_grid`, contradicting §7/§16's "8 of 11" (the section actually has 11 display_modes). **Corrected** to "10 of 11" consistently across §1/§7/§16, reconciled with fix #1 above.
4. §1 named `r4_mutation_service.py` alongside `section_structure_service.py`/`r4_views.py` as hardcoding `PageType.HOME`. The reviewer confirmed `r4_mutation_service.py` contains no Home references at all — it is Home-only only transitively, by calling into `section_structure_service.py`. **Corrected** in §1.

It additionally flagged **4 MINOR** items, also corrected in this revision: the legacy settings-form branch count ("14 keys" corrected to "13 keys across 11 distinct branches, since `hero_banner`/`image_slider` share one") and the consequent "21 of 36 sections have no write path" figure (corrected to "23 of 36," reconciled across §1/§7/§10/§13); §11's parenthetical page-type list, which named 7 items while describing "all 6 page types" (corrected to name the 6 real `PageType` values plus the Collection Index route explicitly called out as sharing one of them, per §11/§12's own finding); this section itself being an empty placeholder in a document §27 declared complete (resolved by this section's content); and a pre-existing, unrelated code-level inconsistency the reviewer noticed in passing (`MULTI_BANNER_KNOWN_LAYOUT_VARIANTS` holds more values than an adjacent comment states) — noted here for completeness but out of scope for this audit to fix, since it is a documentation-comment drift inside production code, not an architecture finding.

**Reviewer's final verdict (pre-correction; the corrections above address every IMPORTANT/MINOR item raised, and no CRITICAL was found):**

```
ARCHITECTURE MAPPING: PASS
PARALLEL-SYSTEM ANALYSIS: PASS
LEGACY CLASSIFICATION: PASS
PHASE-4/5 SCOPE BOUNDARY: PASS
IMPLEMENTATION READINESS: PASS
CRITICAL: 0
IMPORTANT: 4 (all corrected above)
MINOR: 4 (all corrected above)
```

---

## 27. Final readiness verdict

**Audit status: COMPLETE AND REVIEWED.** All 12 requested audit areas were investigated against actual current code (not solely against prior documentation), using 9 independent parallel research passes plus the direct-reading work in §4–6. A fresh independent reviewer then re-derived the ten highest-stakes claims directly against the code and returned ARCHITECTURE MAPPING / PARALLEL-SYSTEM ANALYSIS / LEGACY CLASSIFICATION / PHASE-4/5 SCOPE BOUNDARY / IMPLEMENTATION READINESS all PASS, 0 CRITICAL, 4 IMPORTANT and 4 MINOR — all eight corrected in this revision (§26). Every remaining YES/parallel-authority finding in this document is backed by file:line evidence gathered this session and independently re-verified by the reviewer, not inferred from naming or docstrings.

**This audit's own recommendation:** now that the review cycle (§26) is closed with zero unresolved CRITICAL/IMPORTANT findings, the next step is Product Owner/Architect sign-off on the open questions in §23 and the wave sequencing in §18, followed by authoring the single future Master Implementation Prompt per §25's structure. **Phase 4 implementation has not started and should not start from this document alone.**

---

## Final architecture verdict (required explicit answers)

**A. Are there still parallel Appearance sources of truth?**
Mostly no, with three concrete exceptions found this audit: (1) `preset_service.apply_preset`'s direct `appearance_config` write bypasses `appearance_authority_service` and can erase the typed manifest; (2) the Store-Appearance `hero`/`product_view`/`card`/`badge` families exist as a render-time overlay with no write-time reconciliation (currently dormant/safe since no merchant UI exposes it, but latent); (3) Ready-Template application logic is duplicated between the designed-canonical `apply_ready_template_appearance` (unused) and the actual `apply_preset` (used, and the source of exception #1).

**B. Are there still parallel writers?**
Yes, narrowly: `resource_source.py`'s ownership-validation logic is reimplemented independently in the legacy view layer, with a real behavioral divergence on `category_ids`. Everywhere else (Global/Header/Footer Appearance for the legacy-view/R4 pair, section settings, structure mutations, Undo/Redo/Publish) either has one writer or a genuinely converged shared implementation.

**C. Are there parallel renderers, or only legitimate page shells/adapters?**
Only legitimate shells. Confirmed by direct trace: exactly one renderer (`render_service.build_page_render_items`) serves all 6 page types, Preview, Public, the unpublished-product dashboard preview, and the Cart HTMX fragment. `home_visual.html` vs. `storefront_shell.html` is the one shell difference, and it is architecturally acceptable per the audit's own distinguishing rule.

**D. Which old/R4 systems overlap?**
Undo/Redo/Publish overlap in name only — they are the same implementation now. Everything else in §13 (settings save, structure mutation, container/cell/row composition, section-scoped media, toggles, discard/restore/history, granular reset) overlaps as two genuinely separate implementations at different maturity levels, with R4 currently a strict subset of legacy's capability (Home-only, flatter composition model, no media UI).

**E. Which should survive?**
R4's mutation/safety contract (optimistic concurrency, atomicity, single history authority) should be the surviving pattern for everything. Legacy's *composition model* (multi-column containers, rows, arbitrary cell placement) has capability R4 doesn't yet have and must inform R4's design before anything is retired — R4 should not simply "win" by replacing legacy with something less capable.

**F. Which can be retired in Phase 4?**
Nothing should be retired *within* Phase 4 itself under this audit's findings — Phase 4's job is to make retirement possible (give R4 parity + a live UI + real usage evidence). The soonest-retirable candidates once that groundwork exists are the granular reset views and discard/restore/history browser (their underlying services are already fully safe; only the HTTP surface is duplicated).

**G. What must remain domain-owned?**
Confirmed intact everywhere checked: Product/pricing/stock/SKU (Catalog), cart totals/mutation (Cart), order-derived best-seller data (Orders), collection membership/visibility (Catalog's `collection_service`). No Builder code path was found writing into any of these domains — Builder consistently reads via context builders and stores only presentation/selection state.

**H. What can be rebuilt from fresh data/seed?**
Everything used for QA/demo/testing — the existing `seed_ready_template_fashion_demo.py`, `apply_golden_reference_storefront.py`, and the Phase-3 `_prepare_phase3_*_gate` fixture patterns are the proven templates; no historical test/demo data needs preservation, consistent with the binding Product-Owner decision.

**I. Does Phase 4 need schema migrations?**
Not identified as required by any finding in this audit. One area (R4 composition-model parity, Wave 3) *might* surface a genuine need — flagged as an explicit STOP-and-escalate condition in §22, not pre-authorized.

**J. Does Phase 4 need historical data migrations?**
No — confirmed consistent with the binding decision that no important real data exists.

**K. What exact internal sequence should the future Master Prompt execute?**
The five waves in §18, in order, each independently reviewable and committable, per the structure in §25.

**L. What evidence will prove Phase 4 complete?**
Per family migrated: the same Phase-3-grade evidence bar (typed schema + ResourceSource + canonical mutation + Draft/Published + renderer + relevant pages + fragment where applicable + CSS/JS/media completeness + Preview/Public parity + desktop/tablet/mobile browser certification via the extended, not duplicated, R4 QA harness) — plus, at the wave level: R4 reachable via a live UI with real usage, the three parallel-authority defects closed and regression-tested, the Home-only CSS gap closed for all 13 flagged families/variants with Home-unchanged guard tests, and — only where evidence-backed — specific legacy surfaces retired one at a time with their own bounded commits.
