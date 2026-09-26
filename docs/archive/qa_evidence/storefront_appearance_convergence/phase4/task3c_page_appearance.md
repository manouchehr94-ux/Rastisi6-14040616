# Task 3C — Canonical Page Appearance inheritance tier

## Result: PASS

## Scope

Implement the approved Page Appearance precedence (Ruling F): Template DNA → Store Global → Page →
Section/Component — a bounded, typed, sparse override tier that did not exist at all before this
task (the audit's §8 concept C: "Page Appearance — N/A — does not exist").

## Investigation (per Ruling F's explicit instruction: check for an existing canonical surface first)

`StorefrontPage` (the versioned, typed-slot, per-page model already generalized in Task 3B) has no
JSON field of its own — only `version` FK and `page_type`. No existing canonical JSON surface could
hold a per-page override cleanly. Per Ruling F, a minimal forward migration is therefore authorized
for this specific approved requirement: `0019_page_appearance_overrides.py` adds
`StorefrontPage.page_appearance_overrides` (`JSONField(default=dict, blank=True)`). Verified the
migration applies and reverses cleanly (`migrate` forward → back to `0018` → forward again),
`makemigrations --check --dry-run` clean.

## Key architecture decision: which fields belong in this tier

`apps.core.context_processors._global_identity_version`'s own docstring encodes an explicit,
already-reviewed architecture decision: core brand-identity tokens (colors/font/button_style/
motion/type_scale/palette_slug/template_slug) must stay Store-global — "a customer must never see
a different brand on product-detail than on Home." The Page Appearance tier must never violate this.

Separately, `layout_service.validate_appearance_config` already has 5 fields
(`content_width`/`grid_density`/`card_shadow`/`card_hover`/`hero_style`) that are *already*
sparse-by-design at the Store-Global level (a Phase-8 comment: "absence means not yet explicitly
changed — falls back to the Template's own default, never a fabricated value") — i.e., already
architecturally distinct from the core-identity fields. These 5 pre-existing, already-registered,
already-choice-validated fields are exactly the correct, evidence-grounded candidate set for the
Page tier: `layout_service.PAGE_APPEARANCE_KEYS`.

## Implementation

1. **`layout_service.py`**: extracted the 5 fields' existing validation into `_apply_structural_page_fields`
   (shared, not duplicated) and added `validate_page_appearance_overrides(raw)` — a genuinely sparse
   validator (only keys present in `raw` are validated/kept; unknown keys, including every
   core-identity field, are silently dropped, matching this module's existing "unknown key ignored"
   convention).
2. **Migration `0019`**: `StorefrontPage.page_appearance_overrides` JSONField.
3. **`appearance_authority_service.py`**: the ONE canonical write primitive,
   `apply_page_appearance_patch(*, page, patch)` — Draft-only (raises `PageAppearanceNotDraftError`
   against a Published/Archived version), sparse-merge (only patched keys change, others survive).
   The ONE canonical resolver, `effective_page_appearance_config(*, store_appearance_config, page)` —
   Store Global merged with the page's own override for exactly the bounded key set.
4. **`storefront_context_service.py`**: `build_universal_storefront_context` (the confirmed single
   entry point for all 6 public page types) now also sets `request.storefront_appearance_page = page`,
   mirroring the pre-existing `request.storefront_appearance_version = version` pattern exactly.
5. **`context_processors.py`**: `_versioned_appearance` (the function that already resolves
   `_MANAGED`-style structural config into the `SHOP_CONTENT_WIDTH`/`SHOP_GRID_DENSITY`/
   `SHOP_CARD_SHADOW`/`SHOP_CARD_HOVER`/`SHOP_HERO_STYLE` template variables `templates/base.html`
   renders as CSS custom properties — `--sfb-content-width`, etc. — and `data-sfb-*` attributes on
   every single page's `<html>` tag) now merges in `request.storefront_appearance_page`'s override
   when present, via `effective_page_appearance_config`. `_global_identity_version`/`_versioned_colors`
   (the brand-identity resolvers) are completely untouched — confirmed by a dedicated test that
   brand colors stay byte-identical across pages regardless of a Page Appearance override.
6. **`views.py::storefront_preview`**: sets the same `request.storefront_appearance_page` attribute
   (Preview builds its own context independently of `build_universal_storefront_context` — a
   pre-existing architecture fact, not introduced by this task — so it needs the same one-line
   mirror the pre-existing `storefront_appearance_version` attribute already has there).
7. **Real regression found and fixed during testing**: `layout_service._clone_version_content`
   (used whenever a new Draft is spun off a Published version — the normal "resume editing after
   publish" flow, also used by Restore and pre-replacement checkpoints) copied
   `header_config`/`footer_config`/`appearance_config`/`template_provenance`/`template_baseline_snapshot`
   for the whole version but never `page_appearance_overrides` per page — a real, Draft/Published-
   lifecycle latent bug this task's own end-to-end test caught: publish a Page Appearance override,
   then resume editing (or reload Preview, which internally re-creates a Draft), and the override
   would have silently vanished. Fixed by copying `page_appearance_overrides` in the same per-page
   clone loop.

## Tests (`apps/storefront_builder/tests/test_phase4_task3c_page_appearance.py`, 18 tests)

- `ValidatePageAppearanceOverridesTests` (6): sparse validation, unknown/core-identity keys dropped,
  invalid choices/types rejected, non-dict input rejected.
- `EffectivePageAppearanceConfigTests` (2): no-override falls through to Store Global; page override
  wins for its own key while unrelated Store-Global keys survive.
- `ApplyPageAppearancePatchTests` (4): persists validated sparse override; merges without clobbering
  prior keys; an invalid patch leaves the prior valid state untouched (no partial corruption);
  **rejected on a Published version** (`PageAppearanceNotDraftError`).
- `PageAppearanceEndToEndRenderingTests` (4): real HTTP requests against `catalog:home`/`cart:detail`
  — Home renders the Store-Global `--sfb-content-width`, Cart renders its own page override and
  never the Store-Global value, **brand-identity colors are byte-identical across both pages**
  (the one invariant this tier must never violate), and a page that never uses this tier is
  completely unaffected (exact pre-Task-3C rendered value).
- `PageAppearancePreviewMatchesPublicTests` (2): Preview reflects the override before publish;
  Preview and Public agree after publish — this second test is what caught the `_clone_version_content`
  gap (RED before the fix, confirmed by direct reproduction).

## Verification

- New suite: **18/18 pass**.
- Regression sweep: `test_phase4_task3c_page_appearance`, `test_phase1_appearance_authority`,
  `test_phase_1b_render_and_context`, `test_r4_vertical_slice`, `test_public_homepage_integration`,
  `test_views` — **395 tests, 2 failures + 1 error**, both/all matching the known pre-existing
  signatures (`test_validate_appearance_config_is_the_validator_boundary`,
  `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`,
  `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`) — zero new regressions.
- `python manage.py makemigrations --check --dry-run`: no changes detected (model matches the one
  new migration exactly). `git diff --check`: clean.
- Migration reversibility verified directly (`migrate 0018` → `migrate` forward again, clean both
  ways).

## STOP conditions checked

No second appearance/lifecycle engine was created — this tier reuses the existing Draft/Publish
lifecycle, the existing single renderer entry point, and the existing `_versioned_appearance`
consumption path in `templates/base.html`, unchanged in shape. The migration is exactly the one
Ruling F pre-authorized (a page-level appearance override, nothing broader) — no other schema
change was made. Core brand-identity resolution (`_global_identity_version`) was not touched.
No new merchant-facing selector UI was added (Ruling J's constraint applies to the four Store-Appearance
component families, not this tier, but the same restraint was applied here too — this task delivers
the canonical service-layer contract only, per Ruling F's explicit scope; a merchant-facing editor
control for these 5 fields is a UI-layer follow-up, not required by this task's text).

## Note: environment ordering incident

Partway through this task's implementation, a background review agent (running Task 3's 3A/3B/3D/3E
review on the same shared working tree) performed a temporary `git checkout <parent-commit> --
<file>` / restore sequence as part of its own RED-verification for an *unrelated, already-committed*
commit. This transiently reverted two of this task's in-progress, not-yet-committed edits
(`models.py`'s new field, `views.py`'s `storefront_preview` change) before the agent restored the
tree to the last commit's state (correct for its own purposes, since it had no visibility into this
session's uncommitted work). Both edits were independently detected as missing (via `git status`/
grep) and re-applied before proceeding; `makemigrations --check` and the full test suite were
re-verified clean afterward. No data loss beyond momentary in-memory edit state; the committed
history and this evidence file are unaffected. Reviewers of future Task 4+ work in this same
environment should be aware background agents and the primary session can share one working tree.
