# Storefront Vertical-Slice Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Follow the single master execution block below. Preparation does not authorize starting Task1. Each future task uses checkbox steps, RED before GREEN for changed behavior, review, evidence and a bounded commit.

**Goal:** Certify Brand first, then Collection, across domain references, settings, variants, canonical mutation, shared rendering, assets, media and desktop/mobile behavior.

**Architecture:** Hybrid/vertical-first over the existing Section registry, ResourceSource, SettingsSchema, lifecycle and shared renderer. Collection can refine the Brand-derived contract; it keeps route context, visibility and membership semantics. No new renderer or fragment endpoint.

**Tech Stack:** Python3.12.10, Django5.2.16, Django TestCase/SimpleTestCase, Django templates, existing CSS/JS and Playwright-core R4 runner.

**Spec:** `docs/superpowers/specs/2026-09-06-storefront-vertical-slice-phase3-design.md`.

**Baseline:** `e244619f395ebf0dbebc77d2033841e17f1cd099`; current authorized worktree `RastiSi5_Phase3`, branch `feature/storefront-vertical-slice-phase3`. The starting implementation commit must be the four-file preparation commit or its reviewed descendant, never a guessed SHA.

## Global constraints

- Brand before Collection generalization; shared extraction only when both have evidence.
- Preview reads Draft; Public reads Published; ordinary Brand/Collection records remain domain-owned/live.
- Approved normal Appearance precedence remains Template DNA → Store Global → Page → Section/Component. Preserve Phase1 authority and Phase2 lifecycle. Structure lock is structure-only.
- No new renderer/fragment engine, no migration, no business ownership migration, no media deletion/cleanup/TTL, no legacy retirement, no all-family rollout, no broad CSS/variant/Page Override/Template Switch work, no Phase4/5. The existing Cart fragment presentation helper is allowed in Task3 for Brand proof and Task6 only for a refinement demonstrated by both pilots.
- Existing persisted brand_ids/collection_ids remain canonical. Typed source is an adapter, not a second persisted owner.
- No normal Product Owner confirmation between future tasks; task review is required. CRITICAL or unresolved IMPORTANT means STOP. No push/PR/merge/rebase.
- Future evidence root `docs/qa_evidence/storefront_appearance_convergence/phase3/`. Preparation itself may create only baseline.md and vertical_slice_inventory.md there, plus spec/plan.
- Baseline exceptions: the exact four method/signature entries in baseline.md; no entire-module exclusions. One fixture-dependent skip must remain visible, not counted as pass.

## Existing interface/file map

Paths prefixed `B/` below expand to `apps/storefront_builder/`, `C/` to `apps/catalog/`. This abbreviation is normative; paths in commands are fully spelled out.

|Existing file|Interfaces to preserve/use|
|---|---|
|B/section_registry.py|get_definition; BRAND_CAROUSEL_SCHEMA; _validate_brand_carousel_settings; _validate_collection_tiles_settings; _with_resource_source; _with_appearance_overrides; _finalize_registry|
|B/settings_schema.py|clean_section_schema_patch(definition,raw_patch,current_settings); clean_schema_patch; mark_explicit_variant_override(*,settings,variant_setting_key,patch)|
|B/resource_source.py|ResourceSource; resource_source_from_section_settings(section_key,settings); resource_source_to_legacy_patch(section_key,source); _SECTION_ADAPTERS|
|B/variant_contract.py|VariantDefinition supported_settings/required_data/capabilities; resolve_active_variant; resolve_renderer_template|
|B/services/render_service.py|build_page_render_items(page,store,page_context=None,*,store_appearance=None); _build_items_from_sections; _brand_carousel_context; _collection_tiles_context; _collection_header_context; _collection_products_context|
|B/services/r4_mutation_service.py|apply_mutation(*,store,actor,base_revision,mutation); _apply_section_update_settings; _validate_resource_source_ownership|
|B/views.py|storefront_section_settings; _record_edit_history; _get_scoped_section; _preview_page_context; storefront_preview|
|B/r4_views.py|storefront_r4_section_inspector; storefront_r4_resource_picker; _RESOURCE_SEARCHERS; _resolve_selected_items; _serialize_picker_item; _PICKER_UI_KINDS|
|B/services/layout_service.py|get_or_create_draft; publish; restore_version; discard_draft — use, do not redesign|
|B/services/edit_history_service.py|record_change; snapshot_draft; restore_draft_state — regression boundary, no planned production edits|
|C/services/collection_service.py|public_collection_queryset(store); collection_visible_items(collection,store); get_scoped_collection(store,pk)|
|B/services/section_data_service.py|products_in_collection(store,collection,limit); resolve_products(store,settings)|
|B/management/commands/qa_storefront_builder_r4.py|Command.add_arguments/handle/_prepare_r4_sandbox/_build_manifest/_sqlite_backup/_sqlite_restore/_make_session_cookie|
|tools/storefront_builder_r4_qa/run.mjs|scenario; capture; existing browser context/manifest/report flow|

No test module is invented. Extend existing test files named in each task; proposed new method names/snippets below are future additions, not assertions that those tests already exist. No new public production API is required. Collection's two small adapter functions below are explicitly proposed private implementation within resource_source.py, not pre-existing services.

## Review and evidence protocol for every task

Before moving on, review the actual diff for (1) spec conformity and forbidden scope, (2) correctness/tenant/lifecycle/preservation, (3) tests proving a behavioral outcome rather than mirroring code, (4) browser/computed-style evidence where rendering changes. Record each finding with file/function, severity, disposition and verification. Do an independent second reading of the cumulative task diff; do not substitute a green test count for review. No unresolved IMPORTANT/CRITICAL finding can pass. Record MINOR deferrals with reason.

Evidence file must include starting HEAD, exact command, test total/pass/fail/error/skip, expected RED signatures, GREEN result, browser scenario filenames or why that task has no browser action, review outcome, allowed-files audit, commit message and next-task readiness. Stage explicit changed paths only. `git diff --check` must pass before each commit. Do not commit a RED to production: Task1's test-only RED commit is explicitly identified and immediately followed by Task2; no deployment or push is allowed.

## Task 0 — preparation and decision lock

Preconditions: authorized baseline and clean initial worktree. Allowed production/test files: none. Output: exactly the four approved docs. RED/GREEN: not applicable to documentation; execute existing baseline tests, record actual failures, never change them. Browser: inventory only. Review: spec26 sections, V01–V10 mapping and user checklist. Evidence: baseline.md and vertical_slice_inventory.md. Commit: `docs: lock storefront vertical slice phase3 plan`. STOP after this commit. Next readiness: Product Owner/Architect review of these documents, then a separate execution instruction.

## Task 1 — Brand RED characterization and existing QA setup

**Preconditions:** separate implementation authorization; read spec/inventory/baseline; same branch, baseline ancestor, clean worktree. Verify via `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, `git merge-base --is-ancestor e244619f395ebf0dbebc77d2033841e17f1cd099 HEAD`.

**Allowed production files:** none. Test/harness files: B/tests/test_r4_settings_schema.py, B/tests/test_render_service.py, B/tests/test_g22_preview_media_render_consistency.py, B/tests/test_qa_harness_contract.py, B/management/commands/qa_storefront_builder_r4.py, tools/storefront_builder_r4_qa/run.mjs. Harness edits here only enable reusable evidence output/viewport setup and safe local fixture; do not enable Collection production behavior.

**Interfaces:** consume get_definition/clean_section_schema_patch/build_page_render_items and current R4 harness manifest. Produce tests and repeatable existing command execution, no rendering service API.

- [ ] Add this desired-invariant method to a SimpleTestCase in the existing schema test module (use the existing imports or add these exact imports). It must fail because the marker is absent after title edit, not because of an import/fixture error:

```python
from django.test import SimpleTestCase
from apps.storefront_builder.section_registry import get_definition
from apps.storefront_builder.settings_schema import clean_section_schema_patch

class Phase3BrandPreservationTests(SimpleTestCase):
    def test_variant_intent_survives_title_patch(self):
        definition = get_definition('brand_carousel')
        selected = clean_section_schema_patch(
            definition, {'display_mode': 'carousel'}, definition.default_settings())
        renamed = clean_section_schema_patch(definition, {'title': 'Phase3'}, selected)
        self.assertTrue(renamed.get('appearance_overrides', {}).get('variant_explicit'))
        self.assertEqual(renamed['display_mode'], 'carousel')
```

- [ ] Run `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema.Phase3BrandPreservationTests --noinput -v2`. Exact RED: assertTrue receives None/false on title patch. Do not change production.
- [ ] Extend existing BrandCarouselRenderTests using its real fixture style: two own active Brands, one inactive and a second explicit Store with a foreign Brand; requested order `[own_b.pk, foreign.pk, own_a.pk]`; assert output `[own_b,own_a]` for all three display modes. These characterization cases should be GREEN now. Also assert independent sibling sections do not borrow data and unknown persisted mode falls back safely. Do not force a passing characterization to fail.
- [ ] In existing media-render test module, build the item through build_page_render_items and render `storefront_builder/partials/responsive_section_wrapper.html` with `{'item':item,'is_preview':True}` using render_to_string. Compare resource links/title/background/hide flags against the wrapper in full Preview, separating editor handles. Record baseline asset tags from full envelopes. No fake fragment URL.
- [ ] Extend current harness capture path to `manifest.report_dir` and existing browser context to iterate the three specified viewports. Keep original scenarios and default behavior; add phase3 mode via an explicitly introduced optional `--phase3` argument to the SAME command and a boolean `phase3` manifest field. No new command/runner/package.
- [ ] Establish disposable local QA state using the exact bounded setup below. This is future local fixture work, not preparation. It applies existing migrations; it creates no migration file. Stop if DATABASE_URL targets a remote DB, DEBUG is false, or local db is not the known empty baseline. Back up the exact local db bytes before setup and retain that backup until all browser work/restoration completes.

```powershell
# Future implementation only, from verified workspace.
# Record these resolved paths and hash; do not proceed on a different database.
$phase3Db = Join-Path (Get-Location) 'db.sqlite3'
$phase3Backup = Join-Path ([System.IO.Path]::GetTempPath()) ('rastisi-phase3-' + [guid]::NewGuid().ToString() + '.sqlite3')
Copy-Item -LiteralPath $phase3Db -Destination $phase3Backup
Get-FileHash -LiteralPath $phase3Backup -Algorithm SHA256
python manage.py migrate --noinput
python manage.py shell -c "from django.contrib.auth import get_user_model; from apps.stores.models import Store,StoreMembership; from django.utils import timezone; s=Store.objects.get(slug='akhlaghi'); u=get_user_model().objects.create(username='phase3_qa_owner',is_staff=True,is_active=True); u.set_unusable_password(); u.save(update_fields=['password']); StoreMembership.objects.create(store=s,user=u,role=StoreMembership.Role.OWNER,status=StoreMembership.MembershipStatus.ACTIVE,accepted_at=timezone.now())"
python manage.py qa_storefront_builder_r4 --store-slug akhlaghi --username phase3_qa_owner --port 8765 --browser-channel auto --install-node-deps --phase3 --report-dir docs/qa_evidence/storefront_appearance_convergence/phase3/browser
```

Wrap setup+QA in a PowerShell try/finally that restores `Copy-Item -LiteralPath $phase3Backup -Destination $phase3Db -Force` only after the harness server has stopped and only after re-verifying the same workspace/database target. Compare restored hash to backup hash. Preserve backup on failure. Never remove a populated database to make these preconditions pass. The existing command's internal backup/restore remains required for each run. Existing seed migration provides akhlaghi; if absent, stop on fixture drift rather than guessing another merchant. If rerunning, recreate dedicated fixture from the restored empty baseline; do not overwrite an existing real user. Do not commit node_modules/runtime cookies/generated media.

**Exact GREEN:** characterization tests pass; only V01 desired RED remains. Harness setup/restore is verified; initial pilot screenshots are baseline observations, not certification. RED V01 may be committed only in this test-only task.

**Focused command:** `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_qa_harness_contract --noinput -v2`.

**Browser:** Brand3 modes×3 viewports initial observations, URLs/paths from inventory; flag missing assets, do not suppress failures. **Review:** fixture ownership, accurate RED, no domain mutation outside disposable setup, restore and output paths. **Evidence:** task1_red_characterization.md. **Commit:** `test: characterize phase3 brand contracts and browser prerequisites`. **STOP:** global conditions, unexpected failures, inability to restore DB, setup requiring another harness. **Next readiness:** expected RED isolated and logged, fixtures/harness available, no production edits.

## Task 2 — Brand canonical preservation and capability truth

**Preconditions:** Task1 reviewed/committed with only expected V01 RED. **Allowed production files:** B/settings_schema.py, B/section_registry.py, B/views.py (Brand settings branch only), B/r4_views.py (inspector field filtering only), B/variant_contract.py (existing metadata/resolver use only), B/templates/dashboard/storefront_builder/partials/section_settings_form.html, B/templates/dashboard/storefront_builder/r4/partials/section_inspector.html, B/static/storefront_builder/r4_editor.js (refresh inspector after variant changes). **Forbidden:** lifecycle/authority/domain services, new variant/renderer, other-family behavior. **Tests:** existing test_r4_settings_schema.py, test_r4_inspector.py, test_phase1_appearance_authority.py, test_views.py, test_shared_capabilities.py.

**Interfaces:** existing clean_section_schema_patch still returns validated persisted dict; no change to ResourceSource persistence. Use VariantDefinition.supported_settings/required_data and existing variant helpers; no separate capabilities owner.

- [ ] Run Task1 RED selector unchanged before editing.
- [ ] Preserve trusted current `appearance_overrides.variant_explicit` through Brand validation/title/source edits; stamp true only for a genuine variant edit. Never copy this marker from raw client payload. Legacy reads trusted section.settings and preserves the marker during a non-variant edit. Keep historical unmarked rows unmarked. Restrict the fix to pilot preservation; no authority rewrite.

```python
# Algorithm inside the existing bridge, after ordinary schema+definition validation:
# current_settings is trusted persisted state; raw_patch is never trusted for marker authority.
if definition.key == 'brand_carousel':
    trusted = (current_settings.get('appearance_overrides') or {}).get('variant_explicit')
    if trusted is True:
        overrides = dict(validated.get('appearance_overrides') or {})
        overrides['variant_explicit'] = True
        validated['appearance_overrides'] = overrides
# Then use existing mark_explicit_variant_override as before.
```

- [ ] Add tests for variant→title→source, legacy title form after R4 switch, no-op history/revision, spoofed marker rejection and unchanged unmarked state. Use existing R4MutationApiTestCase `_post_json` fixtures for HTTP tests; no mock business ownership.
- [ ] Declare Brand's variant-specific supported settings using existing metadata. Grid/carousel support show_view_all; beauty_tabs omits it. Filter inspector fields and legacy form control accordingly. Preserve dormant stored show_view_all/destination on variant switch and unrelated edits. Reject an explicit show_view_all patch when the resulting variant is beauty_tabs; do not reject a variant-only switch because current stored show_view_all is true. After variant change reload the existing inspector endpoint so controls reflect server metadata.

```python
# Desired mutation test additions in existing R4 test fixture:
response = self._post_json({'base_revision': self.draft.edit_revision,
    'mutation': {'type': 'section.update_settings', 'section_id': brand_section.pk,
                 'patch': {'display_mode': 'beauty_tabs', 'show_view_all': True}}})
self.assertEqual(response.status_code, 400)
# brand_section is explicitly created in setUp with section_key='brand_carousel'.
```

- [ ] Keep columns hidden and local typography unexposed; prove common background/spacing/responsive blocks survive supported R4 patches and complete legacy forms. No new generic controls are necessary for this task.
- [ ] Run `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_r4_inspector apps.storefront_builder.tests.test_phase1_appearance_authority apps.storefront_builder.tests.test_shared_capabilities --noinput -v2`, plus the exact new legacy methods in test_views (do not exclude known Fullscreen failures if running the whole module).

**RED:** V01 false marker; V02 inspector still displays unsupported View-all / patch incorrectly succeeds. **GREEN:** marker preserved, unsupported explicit write400/no state change, hidden dormant settings restored when switching back, known unaffected contracts pass.

**Browser:** Brand grid→beauty_tabs→carousel; inspect no unsupported control, title/source unchanged and correct View-all behavior. **Review:** preserved authority, no client marker injection, dormant settings distinction, no unrelated family changes. **Evidence:** task2_brand_contract.md. **Commit:** `fix: preserve brand variant intent and supported controls`. **STOP:** authority/lifecycle redesign needed or global conditions. **Next readiness:** Brand settings/resource/capability contract GREEN before any Collection production work.

## Task 3 — Brand end-to-end renderer/asset/media proof

**Preconditions:** Task2 contract GREEN. **Allowed production files:** B/services/render_service.py (_brand_carousel_context and existing item projection only), B/templates/storefront_builder/sections/brand_carousel.html, B/templates/storefront_builder/partials/responsive_section_wrapper.html (Brand projection only), B/static/css/storefront_builder.css (Brand-scoped rules only), B/templates/storefront_builder/preview.html; C/templates/catalog/home_visual.html, product_list.html, product_detail.html, collection_detail.html and apps/cart/templates/cart/cart_detail.html (only loading existing required Builder styles if missing). QA command/runner from Task1. **Forbidden:** new renderer/route, global theme edits, new variant, media lifetime, commerce behavior. **Tests:** test_render_service, test_g22_preview_media_render_consistency, test_g23_builder_public_content_appearance, test_public_homepage_integration, test_responsive_rendering, test_page_shell, test_stable_section_identity.

**Interfaces:** produce the same render-item dict with Brand models/settings; use build_page_render_items and responsive_section_wrapper. No mandatory typed result class.

**Additional bounded allowed file:** `apps/cart/views.py:_render_cart_container`, presentation assembly only. Add tests in `apps/cart/tests/test_cart_views.py`; run `test_cart_security.py` unchanged. No cart mutation/price/stock function may change. Brand's real Cart-fragment proof must pass here, before Collection work.

- [ ] Add behavioral tests for all3 Brand variants in Draft/Published using identical live resources, followed by Draft-only title edit. Assert Public unchanged until publish, including source order; compare stable_id across clones, not database PK.
- [ ] Add wrapper isolation proof in existing media module: render an item with hidden-mobile/background settings and verify wrapper data attributes/background URL/resource anchors match full Preview. The RED is any omitted field, not differing editor envelope HTML. Existing field-complete cases may already pass.
- [ ] Place Brand in an explicit published Cart container using existing fixture patterns. POST real `cart:item-update` and `cart:item-remove` routes; assert response context includes use_container_layout/render_containers and retains Brand placement, source/order/settings/media. RED baseline: those context keys are absent. Adapt only the presentation helper to the existing full Public context, keeping the response template, domain operations and OOB counts:

```python
# Inside _render_cart_container, after _cart_context and store resolution:
from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context
context.update(build_universal_storefront_context(
    request, store, StorefrontPage.PageType.CART, page_context=context))
return render(request, 'cart/partials/cart_sections_body.html', context)
```

Run `python manage.py test apps.cart.tests.test_cart_views apps.cart.tests.test_cart_security apps.storefront_builder.tests.test_phase2_universal_renderer --noinput -v2`. Exercise real Cart update/remove in the browser for Brand at all3 viewports, alongside Preview wrapper projection. No Collection production work is needed for this Brand gate.
- [ ] Before the Brand browser gate, create one active disposable MerchantCollection host fixture through the existing QA command so the Collection detail route resolves. This is a route fixture only; Collection schema/generalization remains Task4 onward. Task5 extends this fixture with the full Collection matrix. Run baseline browser on Brand placed on Home and Collection page in the disposable fixture. Compare logo size, display/flex/overflow/gap, text and wrapper background in Preview vs Public at1440/390/768. Record A06 RED where required rules are absent from Public Collection envelope.
- [ ] Make the smallest Brand-scoped CSS correction in already-loaded storefront_builder.css, with selectors restricted to Brand markup. Preserve inline fallback until a browser test proves safe removal; do not delete legacy home.css rules or change unrelated selectors. Required family styling must not depend on home.css being loaded by accident. Do not add global styles/scripts per fragment.
- [ ] Verify contain/fallback/long names/native horizontal scrolling/RTL, repeat wrapper replacement3 times, assert no extra stylesheet/script elements and one editor action per click. If preview delegated event handling already works, add no JS. If it does not, stop and record the needed exact listener site before widening production JS scope.

```javascript
// Add within the existing runner scenario, using its actual page/iframe locator.
const assetCount = await frame.locator('link[rel="stylesheet"],script[src]').count();
const before = await brandWrapper.locator('a.brand-tile').evaluateAll(
  nodes => nodes.map(n => n.getAttribute('href')));
// Fetch the existing Preview page; parse and replace only the matched wrapper.
// Use the section PK read from the current DOM; never assume a fixed database ID.
const after = await brandWrapper.locator('a.brand-tile').evaluateAll(
  nodes => nodes.map(n => n.getAttribute('href')));
assert(JSON.stringify(after) === JSON.stringify(before), 'Brand order after replacement');
assert(await frame.locator('link[rel="stylesheet"],script[src]').count() === assetCount,
  'Replacement must not multiply assets');
```

Use actual existing runner locators/context (frame=Preview iframe, brandWrapper=its `[data-section-key="brand_carousel"]` wrapper); fragment extraction/replacement operation is specified in Task7, not a production API. Public locators use `.brand-tile` because editor section hooks are absent by design.

**Command:** `python manage.py test apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_g23_builder_public_content_appearance apps.storefront_builder.tests.test_public_homepage_integration apps.storefront_builder.tests.test_responsive_rendering apps.storefront_builder.tests.test_page_shell apps.storefront_builder.tests.test_stable_section_identity --noinput -v2`.

**RED/GREEN:** missing Public styles or semantics demonstrated before scoped fix, then equal component metrics under equal inputs; no source/lifecycle regressions. **Browser:** inventory Brand paths/screenshots plus Collection-page Brand. **Review:** source queries unchanged, no broad CSS spill, image/network checks, true clone identity. **Evidence:** task3_brand_gate.md. **Commit:** `fix: prove brand rendering across preview public and wrapper replacement`. **STOP:** Brand cannot pass without new renderer/domain/asset framework. **Next readiness:** Brand family gate PASS; only now permit Collection generalization.

## Task 4 — Collection characterization and canonical adapter convergence

**Preconditions:** Brand gate PASS. **Allowed production files:** B/resource_source.py, B/section_registry.py, B/settings_schema.py (pilot preservation only), B/services/r4_mutation_service.py (Collection ownership branch only), B/r4_views.py (Collection picker/schema support only), B/views.py (Collection tile settings compatibility only), B/services/render_service.py (_collection_tiles_context query reuse only), B/templates/dashboard/storefront_builder/r4/partials/resource_picker.html, B/static/storefront_builder/r4_editor.js (existing picker dispatch only). **Forbidden:** C/models/service business behavior, header/products R4 rollout, Product redesign, new persisted source field, migrations. **Tests:** test_r4_resource_source.py, test_r4_resource_picker.py, test_r4_settings_schema.py, test_r4_mutation_api.py, test_render_service.py; catalog test_collection_service.py/test_collection_integration.py.

**Interfaces:** extend existing resource_source router to collection_tiles. New adapter implementation names, defined here for this task only:

```python
def collection_resource_source_from_settings(settings):
    ids = settings.get('collection_ids') or []
    if ids:
        return ResourceSource(kind='collection', mode='manual', manual_ids=tuple(ids))
    return ResourceSource(kind='collection', mode='auto', auto_rule='all_active')

def collection_resource_source_to_legacy_patch(source):
    if source.kind != 'collection':
        raise ResourceSourceError('expected collection source')
    if source.mode == 'manual':
        return {'collection_ids': list(source.manual_ids)}
    if source.auto_rule == 'all_active':
        return {'collection_ids': []}
    raise ResourceSourceError('unsupported collection source')
```

Inputs are validated ResourceSource/Mapping; output remains ordinary existing settings dict. Register them only for collection_tiles in `_SECTION_ADAPTERS`; extend `_RESOURCE_SOURCE_AWARE_SECTION_KEYS` and existing error-class mapping.

- [ ] In existing ResourceSource tests, assert roundtrip for Collection manual `[7,3]`, auto-all, max12, wrong kind rejected, nonpositive/duplicate policy matches existing typed validator. RED currently unsupported section_key. No database needed for adapter tests.

```python
source = resource_source_from_section_settings('collection_tiles', {'collection_ids': [7, 3]})
self.assertEqual(source.manual_ids, (7, 3))
self.assertEqual(resource_source_to_legacy_patch('collection_tiles', source), {'collection_ids': [7, 3]})
```

- [ ] Characterize total membership count vs visible products with one active and one inactive member: tile item_count2, visible domain list1. Preserve this current meaning. Prove manual order and auto newest-first differ deliberately from index name ordering. Query via `public_collection_queryset(store)` for active scoped tiles; add `.order_by('-created_at')` for auto tiles. Do not modify collection_visible_items or move domain records into Builder.
- [ ] Add tile SettingsSchema fields title/text, source/resource_source, tile_style/choice grid/carousel; preserve common blocks and internal variant intent with the tested pilot bridge. No separate content blob. Add R4 POST desired test expecting200 for valid own-source; RED baseline returns section_not_schema_enabled.
- [ ] Before enabling schema/picker, implement Collection ownership check analogous to Brand using MerchantCollection.objects.filter(store=store,pk__in=manual_ids). Reject a foreign/missing ID before save; assert settings/revision/history unchanged. Add collection picker search/selected serialization using `.name`, not Brand-only name_en; same-store query, bounded results, all_active rule. Explicitly handle collection in every kind dispatch; do not let it fall through to Brand.
- [ ] Keep legacy collection_ids form; validate through the same definition. Preserve dormant fields/common settings/variant marker across legacy→R4→legacy. Add schema/picker/HTTP negative tests for unknown fields, gate-disabled, foreign/published/archived section, anonymous actor and spoofed marker.
- [ ] Run `python manage.py test apps.storefront_builder.tests.test_r4_resource_source apps.storefront_builder.tests.test_r4_resource_picker apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_r4_mutation_api apps.storefront_builder.tests.test_render_service apps.catalog.tests.test_collection_service apps.catalog.tests.test_collection_integration --noinput -v2`.

**RED:** adapter unsupported, inspector404/settings400 for valid own Collection source. **GREEN:** valid writes succeed through same transaction/revision boundary, invalid ownership writes nothing; selection/count/domain contracts preserved. **Browser:** existing R4 picker now selects2 Collections, reorders, switches tile_style, reloads, preserves references. **Review:** no unguarded kind fallback, exact ID authority, count policy unchanged, Brand tests still pass. **Evidence:** task4_collection_contract.md. **Commit:** `feat: converge collection tiles on typed source and r4 settings`. **STOP:** ownership/domain changes, unplanned schema, Brand-derived abstraction distorting detail context. **Next readiness:** Collection typed mutation gate GREEN; Brand gate unchanged.

## Task 5 — Collection end-to-end and page integration

**Preconditions:** Task4 GREEN. **Allowed production files:** B/services/render_service.py (Collection builders only), B/templates/storefront_builder/sections/collection_tiles.html, collection_header.html, collection_products.html; B/templates/storefront_builder/partials/responsive_section_wrapper.html (Collection context only); B/static/css/storefront_builder.css (Collection scoped styles only); C/templates/catalog/collection_detail.html and collection_index.html (pilot assets/presentation only); B/templates/storefront_builder/preview.html; existing QA command/runner. **Forbidden:** domain queries' business rules, ProductCardData/card redesign, new pagination/fragment route, non-Home R4 UI. **Tests:** test_render_service, test_u4_component_variants, test_g22_preview_media_render_consistency, test_phase_1b_render_and_context, test_responsive_rendering, catalog test_collection_public_views/test_collection_integration.

**Interfaces:** tile context stays collection_tiles rows; detail stays collection/products/page_obj. Existing domain service remains source of visible products.

- [ ] Extend existing `_prepare_r4_sandbox` with MerchantCollection fixtures p3-collection-1/2 and membership in existing t12-products. Make Collection1 deterministically newest for Preview comparison; include >PRODUCTS_PER_PAGE visible items for real Public page2 proof, one inactive member, one no-image Collection and one generated image fixture. Use existing Product/Vendor/Category fixture patterns. Use temporary media storage and clean only those generated test files; never domain production media.
- [ ] Add tests: both tile variants select/order identically; title/source change preserves variant/local intent; Published unchanged after Draft edit; publish/restore retains selection and stable_id; context-aware header/products receive same collection/products/page_obj as domain view. Compare Collection1 Preview to Collection1 Public explicitly.
- [ ] Prove `GET /collections/p3-collection-1/?page=2` uses domain visible membership and shared cards; no HX branch is expected. Assert Collection index remains a separate direct listing without a fabricated current Collection. Test anonymous/foreign host access through existing domain fixtures.
- [ ] Record browser RED for missing tile/Brand family rules on Collection page where reproduced; correct only scoped rules in existing Builder CSS/allowed envelopes. Preserve fixed tile grid/carousel choices, header flex-wrap and product columns. Do not import the whole home.css into every public page.
- [ ] Render isolated wrappers from actual shared items; assert tile links/count/image/title plus detail header/products/paginator under same page context. Browser replacement then proves CSS/media/interaction parity; source already-proven invariants need no artificial production changes.
- [ ] Place Collection tiles on Cart and exercise actual update/remove responses with the presentation adapter proven by Brand in Task3. Extend existing test_cart_views for Collection resources/order/container identity; run test_cart_views/test_cart_security and capture all3 viewport before/update/remove screenshots. Collection's family gate includes this real fragment path before Task6 generalization; a newly exposed defect reopens Task3 under its existing allowed presentation-adapter scope for RED, correction, review and Brand re-verification before resuming Task5; Task5 does not independently expand its allowed production files.

```python
# Add to existing CollectionContextAwareSectionsTests using its store/draft fixture.
items = build_page_render_items(page, store, page_context={
    'collection': collection, 'products': products, 'page_obj': page_obj})
body = next(x for x in items if x['section'].section_key == 'collection_products')
self.assertEqual(body['context']['collection'], collection)
self.assertEqual(body['context']['products'], products)
self.assertIs(body['context']['page_obj'], page_obj)
# Explicit setup creates the collection page's existing registered sections.
```

**Command:** `python manage.py test apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_u4_component_variants apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_phase_1b_render_and_context apps.storefront_builder.tests.test_responsive_rendering apps.catalog.tests.test_collection_public_views apps.catalog.tests.test_collection_integration --noinput -v2`.

**RED/GREEN:** prove any changed presentation mismatch before its fix; unchanged domain/context characterizations remain GREEN. **Browser:** inventory Collection Home/detail/page2/index, both variants3 viewports, images/absence/long text/RTL/internal scroll. **Review:** route context is not tile selection, count meaning explicit, stable identity vs PK, no product business redesign. **Evidence:** task5_collection_gate.md. **Commit:** `fix: prove collection preview public and page integration`. **STOP:** Collection cannot pass within existing renderer/domain ownership; global conditions. **Next readiness:** both family gates PASS, differences documented before shared hardening.

## Task 6 — shared hardening justified by both pilots

**Preconditions:** Tasks3/5 family gates PASS, including their actual Cart-fragment qualification. **Allowed production files:** B/settings_schema.py, B/section_registry.py, B/services/render_service.py, B/templates/storefront_builder/partials/responsive_section_wrapper.html, B/static/css/storefront_builder.css — only duplicated or defective pilot-specific contract portions proven by BOTH; `apps/cart/views.py:_render_cart_container` only for an evidenced refinement of shared presentation-context assembly. No other Cart function may change. **Forbidden:** all-family framework/generalization, new engine, authority/lifecycle/domain/commerce edits. **Tests:** test_r4_settings_schema, test_shared_capabilities, test_phase1_appearance_authority, test_phase2_lifecycle_safety, test_render_service, test_stable_section_identity, apps/cart/tests/test_cart_views.py and test_cart_security.py.

**Interfaces:** keep all public signatures/return shapes in file map unchanged. Do not introduce a universal Brand DTO. Consolidate only common marker-preservation/metadata/projection checks; keep separate query adapters and route context.

- [ ] Write two-family parameterized assertions in existing test modules: variant→title→source preserves compatible state; source order stable; unsupported new writes rejected but dormant values retained; render two same-family instances without leaks. Include Brand and Collection in every proposed shared helper test.
- [ ] Add combined two-family Cart assertions to existing test_cart_views using its real cart/item fixture and a published Cart page containing Brand and tiles in distinct containers/cells. POST real update/remove routes; assert use_container_layout and both placements/resources/settings match full cart_detail. Task3's presentation adapter should already pass; do not claim a new RED if it does. If Collection exposes a new defect, record its failing invariant before a bounded refinement. Test unpublished fallback, absence of editor handles and unchanged cart quantities/totals/errors. Do not extend to Listing/Newsletter.
- [ ] For any shared production change, first run its desired assertion with the current code and record the failure. If tests already pass, retain code and document the shared conclusion; do not manufacture a refactor.
- [ ] Re-run lifecycle rollback/stale/non-Draft/cross-tenant tests and media reachability boundaries; no fixes there are authorized by this task. Run `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_shared_capabilities apps.storefront_builder.tests.test_phase1_appearance_authority apps.storefront_builder.tests.test_phase2_lifecycle_safety apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_stable_section_identity apps.content.tests.test_phase2_media_reachability --noinput -v2`.
- [ ] Run `python manage.py test apps.cart.tests.test_cart_views apps.cart.tests.test_cart_security apps.storefront_builder.tests.test_phase2_universal_renderer --noinput -v2`; both new context assertions and original cart behavior must pass.

**RED/GREEN:** a new evidenced defect fails then passes; otherwise task is proof-only with existing tests GREEN. **Browser:** rerun both affected family scenarios after any shared edit. **Review:** evidence from both families, no universal query policy, no namespace/asset duplication, Phase1/2 preserved. **Evidence:** task6_shared_contract.md. **Commit:** `test: lock shared contracts proven by brand and collection` (use `fix: harden shared pilot contract` only if production correction occurred and evidence names it). **STOP:** requires all-family redesign or global conditions. **Next readiness:** shared contracts and intentional differences accepted by task review.

## Task 7 — complete browser/full-fragment/asset/responsive matrix

**Preconditions:** both family gates and shared review passed. **Allowed production files:** none; QA command/runner only for completing evidence instrumentation. **Tests:** B/tests/test_qa_harness_contract.py for command safety; run existing regression modules. **Interfaces:** existing preview/public routes, existing wrapper, same QA manifest; no HTTP endpoint addition.

- [ ] Run exact Task1 setup and QA command with --phase3 (restore the original DB in finally). The mode now includes both families and all inventory scenarios. Avoid concurrent database users/runservers. Capture exit code and restored SHA256.
- [ ] For each Brand variant and each Collection tile variant at1440x900,390x844,768x1024: Preview→publish→Public→Draft-only change→Public unchanged; then restore/reset only through existing supported lifecycle controls in fixture. Save screenshot and metrics for each phase; confirm selected resources and logical IDs.
- [ ] Implement the precise harness-only replacement using the existing Preview route; start from full loaded Preview. Extract the wrapper for the observed physical section ID from freshly fetched full HTML, replace it3 times, and compare before/after metrics and editor action count. Do not run global scripts from fetched markup:

```javascript
await frame.evaluate(async (sectionId) => {
  const selector = '[data-section-id="' + sectionId + '"]';
  const html = await (await fetch(location.href, {credentials: 'same-origin'})).text();
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  const next = parsed.querySelector(selector);
  const previous = document.querySelector(selector);
  if (!next || !previous) throw new Error('Missing resolved section wrapper');
  previous.replaceWith(document.importNode(next, true));
}, observedSectionId);
```

In the actual runner use the existing Frame object (not FrameLocator) for evaluate; obtain it from the Preview iframe. `observedSectionId` is read from current DOM. Record that this is a wrapper projection from full Preview, not a server fragment response. Separately exercise real admin HTMX inspector/picker replacement and its real save→iframe reload path.

- [ ] Assert component computed display/gridTemplateColumns/gap/overflowX, wrapper background/padding/font and descendant image objectFit; images with URLs must satisfy complete && naturalWidth>0. No-image fallbacks have no failed request. Inject a broken URL only in disposable fixture and record the defined degraded state separately. Assert document.scrollWidth <= viewport width +1 while allowing internal rail overflow. Verify touch/native scroll and keyboard link focus in RTL.
- [ ] Count stylesheet/script URLs before/after replacements (stable count and no duplicate new URLs), record network failures/console/page errors. Do not suppress errors except the existing exact intentional stale409 scenario. Compare same-input Preview/Public component metrics, tolerating only documented editor wrapper handles and intended Page envelopes.
- [ ] Test Collection detail/page2 and index plus a Brand/tile section on Collection page to expose Home-only asset assumptions. Test published host selection and unauthorized Preview with Django client negatives; never fake tenant proof via skipped fixture.
- [ ] Place both pilots on the disposable published Cart page using existing container_service fixture patterns. Add an available fixture product to Cart using existing product/cart UI, then exercise the real quantity update and item removal forms (URLs read from hx-post, item IDs never hard-coded). Compare source anchors, container/cell placement, variant styles/backgrounds and media before/after the actual server HTMX swaps. Screenshot `browser/fragments/cart/{viewport}/before.png`, update.png and remove.png; record totals/quantity correctness separately. This is the real fragment proof complementing harness-only Preview replacement.
- [ ] Run `python manage.py test apps.storefront_builder.tests.test_qa_harness_contract apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_responsive_rendering apps.storefront_builder.tests.test_r4_resource_picker --noinput -v2`.

**RED/GREEN:** any browser invariant failing blocks certification; fix only by returning to its owning task's allowed scope with a RED, updated review and evidence, not silently changing production here. **Review:** full matrix completeness, actual screenshots readable, console/network metrics, restore hash, no invented fragment route, both families proven. **Evidence:** task7_browser_matrix.md plus browser/{brand,collection,controls}/ files specified in inventory. **Commit:** `test: certify pilot browser fragment assets and responsive behavior`. **STOP:** browser missing, un-restored DB, unresolved visual/semantic mismatch or global conditions. **Next readiness:** all required real-browser scenarios pass with linked screenshots/metrics.

## Task 8 — final architecture/regression gate

**Preconditions:** Tasks1–7 reviewed/committed; both family gates PASS. **Allowed production/test files:** none. **Interfaces:** unchanged existing production interfaces; evidence only.

- [ ] Run both exact commands RunA/RunB from baseline.md fresh, including all newly added tests in those modules. Also run added-method modules not in that baseline: `python manage.py test apps.storefront_builder.tests.test_r4_inspector apps.storefront_builder.tests.test_g23_builder_public_content_appearance apps.storefront_builder.tests.test_page_shell apps.storefront_builder.tests.test_views --noinput -v2`. Record actual counts; exact known exceptions only. If wider test_views reveals another pre-existing signature, characterize it against the unchanged baseline before acceptance; do not invent an exemption.
- [ ] Run baseline RunC (Cart/renderer) with new Task6 assertions; require no new cart failures. Record real Public fragment evidence separately from Preview projection tests.
- [ ] Run `python manage.py check` and `python manage.py makemigrations --check --dry-run`; expect clean/no changes. Run `git diff --check` and `git diff --name-only e244619f395ebf0dbebc77d2033841e17f1cd099 HEAD` and inspect cumulative production diff. No forbidden source/migration/new renderer/domain ownership/legacy retirement.
- [ ] Re-read spec26 sections and evaluate each exit item with evidence from both families. A04 pilot V05 may close; original other-family A04 stays open/deferred. A06 closes only for demonstrated pilot envelopes, not global CSS ownership. Record V04 count semantics and V09/V10 deferrals.
- [ ] Review the whole branch for correctness, tenant/lifecycle, compatible source/common-setting preservation, variants, typed controls, assets/media/JS, responsive/RTL, rollback. Any IMPORTANT/CRITICAL blocks final gate.
- [ ] Commit final_gate.md with exact test/browser/review/scope status. Do not push, create PR, merge, rebase or begin Phase4.

**RED/GREEN:** verification only; no intentional RED remains. Pass criterion is no unexplained failure, exact known exceptions retained, mandatory browser matrix PASS and no unresolved IMPORTANT/CRITICAL. **Browser:** consume Task7 fresh evidence; rerun affected scenarios only if code changed afterward. **Evidence:** final_gate.md. **Commit:** `docs: close storefront vertical slice phase3`. **STOP:** any global condition or unmet exit criterion; do not write a false PASS. **Next readiness:** Product Owner/Architect review of completed Phase3; no automatic Phase4.

## One future master execution prompt

> Execute the approved Phase3 spec and this implementation plan in the current authorized Phase3 worktree, sequentially Task1 through Task8, using superpowers:executing-plans. Read the spec, inventory and baseline first; confirm the preparation commit, branch, clean status and required baseline ancestor. Do not create or switch branch/worktree. Task0 is already complete. Follow each task's preconditions, exact allowed files, RED→GREEN steps, browser evidence, review, evidence file and commit. Proceed to the next task automatically only after its readiness gate passes; no normal Product Owner confirmation between tasks. Brand must pass before Collection generalization; Collection may refine the abstraction. Preserve domain ownership, Phase1 authority and Phase2 safety. Reuse existing QA harness and restore local fixture data. Stop immediately on any global STOP condition listed in spec23, unresolved IMPORTANT/CRITICAL finding, unexplained regression, unsafe scope change or required push/merge/rebase. Never silently expand scope or claim global A04/A06 closure. After Task8 report evidence and stop; no push/PR/Phase4.

## Traceability/self-review

|Preparation requirement|Execution coverage|
|---|---|
|Baseline/current-state inventory|Task0; fresh Task8 checks|
|Business domain/resource/typed schema|T2 Brand, T4 Collection; no domain copies|
|Common appearance/settings/capabilities|T2/T4, shared T6|
|Variant/selection/order preservation|T1 RED,T2 Brand,T4 Collection,T6 mixed paths|
|Canonical mutation/Draft/Published/history/identity|T2/T3/T4/T5,T6 regression|
|Shared renderer/Preview/Public|T3 Brand,T5 Collection,T7 browser|
|Full/fragment A04|T1 wrapper characterization,T3/T5 proof,T6 actual Cart context,T7 real HTMX and Preview replacement|
|CSS/JS/A06/media|T3/T5 scoped evidence,T6 shared contract,T7 assets/init|
|Desktop/mobile/tablet/RTL|T3/T5/T7|
|Tenant/cross-host/security|T1 explicit second store,T4 source ownership,T6/T7 negatives|
|Legacy/R4 roles/no retirement|T2/T4 adaptation,T8 scope audit|
|V01|T1,T2,T4,T6|
|V02|T2,T3|
|V03/V04|T4,T5; V04 meaning change deferred|
|V05/V06/V07|T3,T5,T6,T7|
|V08|T1,T7|
|V09/V10|T8 explicit defer ledger; Phase4/separate approval|
|Failure/rollback/STOP/master readiness|Global protocol, every task, spec23|

Self-review covers all17 requested criteria: requirement/task mapping; every gap assigned/deferred; Brand first; Collection may refine; no Brand framework; explicit fragment/Preview/Public/assets/desktop-mobile/tenant evidence; domain/Phase1/Phase2 preservation; no retirement/expansion; no unresolved placeholders; single sequential master prompt. Nine tasks numbered0–8, of which Task0 is preparation and eight are future execution tasks. Preparation completion does not mean browser prerequisites or production gates already pass.
