# Storefront vertical-slice Phase 3 design

Date: 2026-09-06. Status: preparation decision lock, awaiting Product Owner / Architect review. Production implementation has not begun.

## 1. Purpose

Prove the binding five-phase architecture end-to-end on Brand Showcase first and Collection second. The vertical contract is Business Domain → Canonical Data/Resource Contract → Typed Content Schema → Common Appearance → Component Settings → Variant → Canonical Mutation → Draft/Published → Shared Renderer → Full Page/Fragment → CSS/JS/Media → Preview/Public → Desktop/Mobile. A family gate requires evidence at every link; shared templates alone are insufficient.

## 2. Official Phase-2 baseline

Repository `manouchehr94-ux/rastisi5`; integration branch `docs/storefront-appearance-convergence`; official merged baseline and preparation starting HEAD `e244619f395ebf0dbebc77d2033841e17f1cd099`. Verified workspace `D:/Projects/RastiSi5_Phase3`, branch `feature/storefront-vertical-slice-phase3`, initially clean. No branch/worktree creation or switching is authorized.

Binding references: `2026-09-05-storefront-appearance-convergence-5-phase-design.md`, `2026-09-06-storefront-lifecycle-safety-phase2-design.md`, the corresponding Phase-2 implementation plan, and `docs/qa_evidence/storefront_appearance_convergence/phase2/final_gate.md`. Phase1 and Phase2 remain closed. Current Python/Django and newly executed baseline results are recorded in Phase3 `baseline.md`, not copied from the earlier machine.

## 3. Scope/non-goals

Implement later only the Brand `brand_carousel` family and Collection `collection_tiles`, with existing `collection_header`/`collection_products` page integration proof. Characterize `product_section` Collection source and Collection index as domain integration boundaries. No broad non-Home R4 editor rollout.

No new renderer, independent Preview/Public/fragment engine, ordinary domain-data migration, legacy retirement, all-family schema work, commerce/auth change, migration, media cleanup/TTL, broad CSS redesign, Header/Footer/Hero/Slider/Product-card redesign, broad new variants, Ready Templates, Template51+, 50-template certification, broad Page Override, Template Switch, Phase4 or Phase5 implementation.

Preparation modifies exactly this spec, its matching plan, Phase3 baseline.md and vertical_slice_inventory.md; commits those four files and stops.

## 4. Brand current state

`apps/storefront_builder/section_registry.py` defines `brand_carousel`, variants grid/carousel/beauty_tabs on display_mode, one template `storefront_builder/sections/brand_carousel.html`. `_brand_carousel_context` in services/render_service.py loads active store Brands once per instance, preserving manual brand_ids order (max24) or auto sort_order/name. No variant queries business data independently. No corresponding Brand entry in the typed component registry was found; the section family name is not a new alias.

BRAND_CAROUSEL_SCHEMA exposes title/source/display_mode/show_view_all; source projects via ResourceSource to brand_ids. Shared wrapper supports responsive visibility/background/spacing/motion. Columns are persisted but not visually supported; local typography is not schema-enabled. V01 is a reproduced internal variant-intent preservation gap; V02 is exposed View-all ignoring both variant support and its trusted resolved-destination dependency. Full inventory answers A–G in `vertical_slice_inventory.md` are part of this spec's evidence.

## 5. Collection current state

Tiles grid/carousel use tile_style and `_collection_tiles_context`; selection cap12, manual order or auto newest first. Total membership count differs from visible item count. No SettingsSchema/section source adapter/R4 picker exists for tiles. Collection header/products consume current Collection, visible products and page_obj supplied by domain context; they have no tile variants and must not be forced into tile semantics.

Catalog collection_service owns records/membership/visibility/order; Builder owns presentation and IDs. Public Collection detail resolves slug; Preview selects newest active representative. Index is a direct companion template. Inventory answers A–F are binding evidence, including the distinction between tile list, route-owned page and product_section source.

## 6. Shared renderer topology

Retain `services/render_service.py:build_page_render_items(page,store,page_context=None,*,store_appearance=None)` and `_build_items_from_sections`. It resolves effective settings/variant, per-instance data, local appearance and same-store background URLs. `responsive_section_wrapper.html` includes the registered inner template with explicit context keys; render_rows/render_containers remain composition authorities.

Preview entry is `views.storefront_preview`; Public entry uses `services/storefront_context_service.py:build_universal_storefront_context` and `page_resolution_service.resolve_published_page`. Exact paths, fallback behavior and asset envelopes are mapped in the inventory. Preserve existing unpublished fallback and editor/public empty-state differences.

## 7. Preview/Public contract

Preview reads current Draft. Public reads Published only. For equivalent versioned presentation and equivalent live resource inputs, both use identical family selection/order/variant/settings/media semantics. Do not compare the newest representative Preview Collection to a different Public slug and call it a parity failure. Domain names/images/membership remain live; publishing Builder presentation does not snapshot ordinary business records.

Test Draft-only edits leaving Public unchanged; publish exposing the new presentation; restore returning a new Draft with stable identity/settings. No editor-only handles or staff data may leak into Public. Cross-host store resolution and staff permission requirements remain unchanged.

## 8. Full/Fragment contract

No dedicated pilot component-fragment HTTP endpoint exists at baseline. R4 refreshes the Preview iframe; admin HTMX partials are settings/structure/picker surfaces. Preserve that behavior. Prove the existing wrapper can be rendered with a resolved item and substituted in a controlled browser harness without losing variant, source order, common appearance, settings, media, responsive configuration or identity. The harness may fetch the existing Preview page and extract its wrapper; label this a projection/replacement test, not an invented production endpoint.

Also prove the real indirect Public path: both pilots are allowed on Cart, whose update/remove endpoints call apps/cart/views.py:_render_cart_container. It reuses shared items but omits render_containers/use_container_layout supplied on full pages. Adapt only this presentation context during Brand Task3, verify Collection in Task5, then prove the combined two-family case in Task6. Cart price/stock/ownership/mutation semantics remain unchanged.

Use the actual shared renderer to produce items. Never reconstruct context by separately querying Brands/Collections in a test-only or production parallel renderer. Inner-template-only rendering does not promise wrapper background/visibility. Fragment asset dependency is explicit: the host must establish the same required pilot assets once; replacement must not inject repeated global runtimes.

## 9. A04 conclusion

PARTIAL for the pilot contract: family data/settings are shared; actual Cart fragment container projection is incomplete and isolated Preview wrapper proof is absent. Remaining original A04 across Listing/Newsletter belongs to Phase4. Phase3 includes the Cart presentation adapter because it directly renders both pilots, and can close V05 without claiming global A04 closure. No new endpoint is required. If implementation discovers that success would require a new fragment engine, STOP.

## 10. A06 conclusion

The real registry allows both pilots on exactly home, product_detail, listing, collection, search and cart. The inventory maps all six to routes/templates/CSS/JS: five distinct pilot envelopes E1 Home, E2 Product detail, E3 Listing/Search, E4 Collection detail, E5 Cart. E6 Collection index is a direct-listing companion with no pilot rendering. Tasks3/5 must assert every allowed type's actual pilot shell/assets; Task7 supplies browser proof per distinct envelope, with browser deduplication permitted only for proven identical CSS AND runtime. For each envelope require component CSS, shared JS exactly once, computed layout, resolved media, no Home-only dependency, no duplicate assets after replacement, no document horizontal overflow and applicable Preview/Public semantics. Use the smallest existing canonical Builder stylesheet/loading mechanism; no blanket home.css imports. Task8 checks matrix completeness before accepting pilot-only closure.

OPEN. Preview loads Home CSS, while Public Collection detail loads product_list CSS; registered Brand/tiles can appear there. Inner fragments establish neither envelope. Brand inline flex/grid provides only partial resilience; it does not establish typography/media/variant styling. Fix only proven pilot asset dependencies, using existing page templates/CSS. Never make unrelated global selectors the vehicle for pilot fixes. Browser computed styles, network status and repeated replacement provide closure evidence.

## 11. Family canonical data/resource contracts

Brand's current ResourceSource adapter and ordered context are the baseline contract; reuse them. Typed content means validated reference selection plus presentation fields, not JSON copies of Brand records. Preserve manual ordering, max24, auto-all-active, safe exclusion at read time and strict same-store source writes.

For Collection tiles, extend the existing ResourceSource section adapter router and existing SettingsSchema bridge to map `kind=collection, mode=manual, manual_ids` to collection_ids, or auto all_active to an empty collection_ids list. Cap12. Do not persist a second source blob. Add ownership validation and picker support atomically with enabling the schema. Use existing public_collection_queryset for scoped active reads, retaining newest-first tile ordering deliberately. Preserve total membership-count meaning in this phase and label it; changing to visible-product count requires a separate product decision. Collection detail retains collection_visible_items and item order,id, pagination and route context. An empty manual list keeps current auto interpretation; changing that behavior is outside this phase.

No mandatory new family class hierarchy or generic loader is justified. Existing typed ResourceSource plus validated settings and an explicitly documented context shape is sufficient unless both pilots prove a stricter type useful.

## 12. Common Appearance

Approved normal precedence remains Template DNA → Store Global → Page → Section/Component. Do not invent a broad Page Override implementation. `appearance_authority_service` remains canonical transformation owner; `resolve_section_appearance` remains the effective local typography resolver. Preserve the existing server-derived variant_explicit marker across compatible pilot edits; never accept that marker as client authority.

Initially promise only supported wrapper background/spacing/responsive behavior and inherited global appearance. Local typography controls for pilots may be added only with schema, resolver and actual template proof in the allowed task; otherwise remain hidden. Do not generalize Hero's typography control by merely copying its schema. Stored compatible common settings survive variant/source/title changes.

## 13. SettingsSchema/capability contract

Builder must not promise an unsupported control. Use existing SectionDefinition/VariantDefinition metadata and existing Inspector; no parallel capability registry. Brand View-all is actionable only when BOTH the resulting active variant supports it (grid/carousel) AND the trusted current destination validates and resolves to a non-none valid URL for the current store. Grid/carousel without such a destination and beauty_tabs with any destination must not present an actionable control; explicit enable requests fail before settings/revision/history change. Do not trust a client capability flag, resolved href or unsupported destination patch. Reuse existing destination validation and store-scoped resolution; resolution alone does not validate external URLs.

Preserve compatible stored show_view_all and destination on a variant-only switch to beauty_tabs and on unrelated edits. Switching back to grid/carousel recovers their effect when the destination remains valid. Brand R4 has no destination editor through its current SettingsSchema: preserve legacy/template authoring, and do not add a broad R4 destination editor or second destination system. An existing canonical generic control may be reused only if its current existence and unchanged authority are evidenced; this plan requires no new destination authoring. Task2 proves valid grid, invalid/absent destination, beauty_tabs, both switch directions and spoofing rejection; Task3 verifies visible controls and rendered anchors together.

Brand columns remain hidden because columns_visual is absent. Collection tiles remain fixed-layout unless a separately evidenced bounded change is required; no fabricated column support. Collection page products retain existing columns_visual/card capability. R4 Collection tiles schema exposes title/source/tile_style. Generic capability expansion to other families is forbidden. Malformed source IDs and unknown R4 fields fail before mutation; persisted invalid variant safely resolves to default.

## 14. Variant semantics

Keep three Brand and two tile variants. Switching changes visual presentation only; selected resources, order, common compatible settings, logical stable_id and domain records survive. Same-template variants are not independent render engines. Explicit local intent survives a later non-variant edit; historical unmarked content remains unmarked until a genuine variant edit. Public/Preview resolve from their own version. No new store manifest Brand/Collection family is required just to certify local variants.

## 15. Mutation/lifecycle integration

R4 uses existing apply_mutation/_apply_section_update_settings/clean_section_schema_patch. Legacy uses storefront_section_settings and _record_edit_history; both persist existing Section.settings. Keep single revision/history rules established in Phase2: active Draft/store targeting, atomicity, one increment per real change, none on no-op, stale R4409, history/recovery preservation. Legacy two-tab last-writer-wins remains the accepted Phase2 limitation; do not mislabel it solved. Structure lock remains structure-only.

Do not refactor lifecycle or authority services to solve presentation. A direct safety regression is a STOP condition, not permission for broad Phase1/2 reopening. No new migration is expected or authorized.

## 16. Media presentation

Brand logo uses contain and name fallback; tiles use cover/folder fallback; Collection header96px image is omitted if absent; index16:9 and shared product media remain distinct. Background URLs must remain store-scoped. Verify no-image and broken-file cases separately; no-image is supported, broken URL does not currently have an explicit fallback. Any bounded presentation improvement must be supported by RED/browser evidence. Do not modify deletion, retention, references, cleanup or TTL.

## 17. Responsive/mobile

Verify1440x900 desktop,390x844 mobile and768x1024 tablet. Common hide flags and product-grid columns must work through the wrapper. Brand inline auto-fill and fixed-width rails, Collection g4 tiles/carousel widths, header flex-wrap are family-specific/hard-coded contracts. Test native horizontal scroll, RTL reading/order, long Persian/Latin names, image aspect, heading overflow and no unintended document horizontal scroll. A carousel may scroll internally; that is not a document-overflow failure.

## 18. Browser QA

Reuse qa_storefront_builder_r4.py and tools/storefront_builder_r4_qa/run.mjs, sharing existing playwright-core dependency and backup/restore/auth pattern. Extend these files only, with deterministic Collection fixture and viewport/matrix support. Application DB currently lacks stores_store and dependencies are absent; plan Task1 supplies a bounded local QA bootstrap before browser evidence. No browser evidence is claimed in preparation.

Exact future commands, fixtures, URLs, screenshots and assertions are in inventory and plan. Run real variant changes, source/order preservation, publication isolation, wrapper replacement, media and responsive checks for both families. Record computed styles and network/console outcomes, not screenshots alone. No second harness. The inventory's six-page registry matrix is binding: automated asset/shell coverage for every page type and each pilot, browser proof for every distinct E1–E5 pilot envelope. Listing/Search may share one browser smoke only after ordered asset/runtime equivalence assertions for both types. Collection detail is distinct from Listing because their inline runtime differs. Include E6 Collection-index companion shell proof without claiming pilot placement there. Verify View-all inspector truth and resolved anchor truth for the full V02 matrix.

## 19. Tenant/security

Renderer queries use the request-resolved Store. Source mutation rejects foreign/missing IDs indistinguishably; read-time stale references omit safely. Collection adapter must add ownership before UI exposure because current Collection-kind branch is intentionally no-op. Existing background ownership validation remains. Tests cover foreign store, same-store Published/Archived targets, unauthorized/anonymous Preview, verified domain routing and R4 gate. No raw template path, arbitrary renderer, domain business payload or internal variant marker is client-controlled.

## 20. Legacy/R4 roles

Inventory's role table is binding: Brand R4/legacy ADAPT; Collection tiles legacy/R4 ADAPT; Collection page legacy, domain CRUD, existing Preview refresh, unpublished fallbacks KEEP; product_section Collection source and Collection index CHARACTERIZE; all-family/non-Home R4 migration DEFER to Phase4. No RETIRE decision is permitted. Adapters converge settings while retaining active routes and rollback-readable persisted keys.

## 21. Hybrid architecture

A independent fixes would duplicate cross-cutting rules. B platform-first rewrite would violate the evidence-before-generalization requirement. Choose C: Brand proof → only evidenced contract refinement → Collection proof → common hardening needed by both. Collection can invalidate a Brand-derived assumption, especially around pagination, resource counts, domain visibility and current-route identity. Preserve its distinctions rather than pretending every family is a Brand list.

## 22. Gap register V01+

The complete evidence/risk/invariant/test/browser/defer register is in inventory. Task mapping is locked here:

|Gap|Severity|Owner|Task/defer|
|---|---|---|---|
|V01 local variant intent preservation|P1|Brand/shared|1,2,4,6|
|V02 View-all variant AND trusted destination dependency; dormant roundtrip|P2|Brand|2,3|
|V03 typed Collection source/schema/picker/ownership|P1|Collection|4,5|
|V04 count/query semantic distinction|P2|Collection|4,5; count meaning change separately deferred|
|V05 Cart fragment context and isolated wrapper proof A04|P1|shared|1,3,5,6,7|
|V06 asset-envelope mismatch A06|P1|shared|3,5,6,7|
|V07 responsive/media/common-control truth|P2|both|2–5,7|
|V08 browser reproducibility|P1|QA|1,3,5,7|
|V09 original other-family A04|P2|shared|Phase4; Task8 carry-forward|
|V10 broad migration/closed Phase2 nits|P3|shared|Phase4 or separately approved cleanup|

No P0 was found. Prior failures are recorded separately from these proposed behavioral tests; preparation fixes none.

## 23. Failure/rollback

Stop on CRITICAL finding, unresolved IMPORTANT review, new renderer requirement, business ownership migration, unplanned migration, tenant/Phase1 authority/Phase2 lifecycle regression, destructive media behavior, all-family redesign, Phase4 need, unexplained baseline regression, unsafe scope expansion, push/merge/rebase requirement, or architecture ambiguity where every safe path is guesswork.

Future commits are bounded and independently reviewed. Rollback by a separately authorized revert of the bounded change; never reset user work. Existing settings keys/legacy routes allow old readers to operate; no data rewrite/deletion is required. Browser harness restores SQLite in finally and records backup/hash and process shutdown; restoration failure stops further QA. Do not claim exit gate while recovery is uncertain.

## 24. Evidence strategy

Task0 is preparation. Tasks1–8 record exact commands/counts/RED failures/GREEN results, source diff, browser scenario IDs, review findings and commit. Baseline exceptions remain exact-name/signature allowlist, not blanket permission to ignore a module. Preserve skip counts separately. Tests extend existing modules; newly proposed test methods are clearly future assertions, not baseline tests. Browser runtime cookies/passwords stay outside committed evidence.

## 25. Phase-3 exit gate

Both families must separately pass selection/order/domain ownership, typed source/schema, capability truth, variant preservation, canonical mutation/lifecycle/identity, Preview/Public, wrapper/fragment, assets/JS/media, desktop/mobile/tablet and tenant checks. Brand gate precedes Collection generalization. Collection detail/index integration remains valid without non-Home R4 redesign. Shared conclusions must cite evidence from both families.

V02 exit requires the six explicit Task2 cases and browser control/anchor proof: valid grid destination succeeds; invalid/absent destination and beauty_tabs enable requests reject without state/revision/history changes; roundtrip preserves and recovers compatible values; spoofing never grants capability. A06 may be CLOSED FOR THE TWO PHASE-3 PILOT FAMILIES only when every declared allowed Public pilot envelope has direct distinct-envelope browser proof or an automated per-page assertion linked to proof of an identical shared envelope. Any unproven allowed pilot envelope leaves A06 PARTIAL/OPEN and prevents full family certification PASS. Global/all-family A06 is never certified by Phase3.

Final gate requires fresh focused baseline matrix plus added tests, check/migration check, exact pre-existing failures only, zero CRITICAL/unresolved IMPORTANT findings, scoped browser screenshots+metrics, no forbidden files/behavior, documented rollback and deferred original A04. Preparation completion is not Phase3 implementation certification.

## 26. Deferred Phase-4/5 items

Phase4: remaining families, non-Home R4 migration, other-family fragments, broad capability/asset consolidation, evidence-based legacy migration/retirement. Phase5: design expansion, new variants, Ready Templates and full-store50-template certification. Template Switch, broad Page Override, forced styles, changed Collection count meaning and media cleanup/TTL require separate decisions; none is implicitly authorized by this plan.
