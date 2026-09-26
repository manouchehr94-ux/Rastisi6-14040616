# Storefront Builder V2 — Phase 6 Completion Report

**Phase**: 6 — Preset System
**Base SHA**: `540b23352424ea5af3c0b9cdc107999e479e2657` (canonical synchronized HEAD, confirmed at phase start)
**Final commit this phase**: `000f0c6`
**Commits this phase**: 2

```
000f0c6 Phase 6: multi-page Preset System — registry, application service, builder UI, tests
d242081 Phase 6 read-only gap audit: Preset System
```

## 1. Initial audit findings

Full detail: `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_6_AUDIT.md`.

The single most important finding: **two entirely separate "Preset" concepts exist in this
codebase**, and this phase concerns only the second one.

1. The **legacy Family/Preset/Palette system** (`family_registry.py`, `preset_registry.py`,
   `appearance_registry.py`) — fully built, home-page-only, 1:1-coupled to one of 11 legacy
   storefront families, and **frozen by Owner Decision 8**
   (`STOREFRONT_BUILDER_V2_REUSE_MATRIX.md:35`). Nothing in it was touched this phase.
2. The **Universal Storefront Builder V2 Preset System** — the actual subject of this phase,
   per spec §5.7 ("A preset is data, not a new family implementation") — did not exist before
   this phase.

## 2. Existing systems reused

- `section_registry.py` (Phase 5): page-type allowlists (`is_section_allowed_on_page`),
  per-type `default_settings()`/`validate_settings()` — reused directly for preset section
  validation, zero new validation logic duplicated.
- `bootstrap_service._DEFAULT_NON_HOME_SECTION_KEYS` (Phase 5): direct structural precedent
  for "ordered section-key list per page type" — the shape a preset's `pages` field mirrors.
- Header/footer structured config + validators (Phase 4): `layout_service.validate_header_config`/
  `validate_footer_config` reused as-is; a preset's header/footer overlay is merged with the
  Draft's current config and validated through the exact same functions the manual composer uses.
- `appearance_registry.py` (Palette, typography/density/motion enums): fully reused — Palette
  stays completely independent of Preset, exactly as it already was independent of Family/Template.
- `layout_service.validate_appearance_config`: extended (not replaced) with one new key
  (`layout_preset_key`), following the exact pattern already used for `family_slug`/`preset_slug`.
- `apply_family_default_sections`'s delete-then-bulk-create pattern (Phase 1A): the direct
  template for `preset_service.apply_preset`'s per-page section replacement, generalized from
  home-only to all 6 pages and wrapped in a stricter validate-everything-first + atomic-transaction
  discipline.
- The existing appearance editor panel (`appearance_panel.html`) and its Alpine `view` tab
  mechanism: extended with one new tab, not replaced or forked.

## 3. Final preset architecture

New module `apps/storefront_builder/layout_preset_registry.py` — deliberately **not** an
extension of the frozen `preset_registry.py` (naming collision risk explicitly flagged in the
audit and in the pre-existing reuse matrix for the unrelated `theme_presets.py`). Follows the
exact registry pattern already established by `section_registry.py`/`family_registry.py`/
`appearance_registry.py`: frozen dataclasses, a module-level dict, `register_x`/`get_x`/`list_x`,
pure Python with zero Django/model dependency (safe to import at any time).

```python
@dataclass(frozen=True)
class PresetSectionEntry:
    section_key: str
    settings: dict | None = None  # None = use the section type's own default_settings()

@dataclass(frozen=True)
class LayoutPresetDefinition:
    key: str
    label_fa: str
    description_fa: str
    appearance: dict = {}                    # structural keys only — never palette/color
    default_palette_slug: str | None = None   # a suggestion, never a lock
    header: dict | None = None
    footer: dict | None = None
    pages: dict[str, tuple[PresetSectionEntry, ...]] = {}  # any of the 6 page types, each optional
    compatible_families: frozenset[str] | None = None      # None = universal (no 1:1 Family coupling)
```

Validation is split across two layers by design, to avoid a circular import between the pure
registry and the Django-model-dependent `layout_service`:

- **At registration time** (`register_layout_preset`, i.e. at Python import time — before any
  Django app is even necessarily ready): section/page shape — unknown section keys, section
  types used on a disallowed page type, and per-section `settings` shape, all checked directly
  against `section_registry` (itself fully pure). An invalid built-in preset raises
  `InvalidLayoutPresetError` immediately and is never added to the registry.
- **In `services/preset_service.validate_layout_preset`**: appearance/header/footer shape,
  which needs `layout_service`'s validators (Django-model-dependent). Exercised both by a
  dedicated test (`test_all_built_in_presets_pass_validate_layout_preset`) and defensively
  inside `apply_preset` itself before any write.

## 4. Built-in presets

Four, per the master instruction's "3-5 clearly different data presets... not merely color":

| Key | Label | Home sections | Differentiators |
|---|---|---|---|
| `clean_minimal` | ساده و مینیمال | 4 | compact density, no motion, outline buttons, no announcement bar |
| `editorial_story` | روایت‌محور | 6 | serif font, relaxed density, large type scale, story-rail-led |
| `dense_catalog` | کاتالوگ فشرده | 7 | multiple stacked product grids, compact/no-motion, utilitarian |
| `premium_boutique` | پرمیوم بوتیک | 8 | relaxed density, dynamic motion, large type, marketing-forward |

Each defines a full composition for all 6 page types (home varies 4-8 sections; the 5 commerce
pages use the same required non-removable Phase 5 sections plus each preset's own choice of
optional extras, e.g. `product_video`/`related_products` included or omitted). Confirmed
structurally distinct via both an automated section-count assertion and live browser screenshots
(see §12) — not a color-only reskin.

## 5. Palette separation

Palette remains fully independent, exactly as the audit required:

- A preset's `default_palette_slug` is applied **only if the merchant hasn't already chosen a
  palette** for the current Draft — verified by `PaletteSeparationTests` (both directions: sets
  default when none chosen, never overrides an existing choice or its `color_overrides`).
- Live-confirmed in browser QA: switching the palette independently, then applying a different
  preset, left the manually-chosen palette (and its resulting colors) unchanged — proving
  "Preset A + Palette X" and "Preset B + Palette X" both work without coupling.

## 6. Application semantics

`services/preset_service.apply_preset(draft, preset)`:

1. Takes an **explicit Draft** — never resolves "the current draft" itself, never touches
   `layout.published_version`, mirroring `apply_family_default_sections`'s contract.
2. **Validates everything before writing anything**: appearance, header, footer overlays are all
   merged against the Draft's *current* effective config and validated through
   `layout_service`'s real validators; any failure raises `InvalidPresetError` with zero writes.
3. Wrapped in `@transaction.atomic` — even a database-level failure partway through writing
   per-page sections rolls back the earlier `appearance_config`/`header_config`/`footer_config`
   save too (proven by `test_db_failure_mid_apply_rolls_back_everything`, which mocks
   `bulk_create` to fail and asserts the Draft is byte-identical to before the call).
4. Only pages the preset actually lists in `pages` are touched — a page a preset omits is left
   completely alone (both its existing sections and, implicitly, any other page's data).
5. Idempotent — re-applying the same preset object twice produces byte-identical section rows
   (same keys, same settings, same count), not accumulation or duplication.

## 7. Merchant-content preservation semantics

Exactly the STRUCTURAL/VISUAL vs. MERCHANT CONTENT split the master instruction required:

- **Replaced**: `StorefrontSection` rows (key/order/settings) on pages the preset covers;
  `appearance_config`'s structural keys; `header_config`/`footer_config` toggle/responsive keys
  the preset explicitly overrides.
- **Preserved unconditionally**: all catalog/product/category/collection data (never queried or
  written by this module at all); `header_config.announcement_text` (a preset never sets this
  key, confirmed by `test_custom_announcement_text_survives_preset_apply`); `color_overrides`
  and any already-chosen `palette_slug` (§5); any page a preset doesn't list.
- **Merged**: header/footer/appearance overlays are merged onto the Draft's *current* effective
  config, not onto platform defaults — so any structural key a preset doesn't mention keeps
  whatever the merchant had before.

## 8. Reference safety

No built-in preset embeds a tenant-specific ID anywhere — verified both by direct code review
(every `PresetSectionEntry.settings` is either `None` or a small dict of enum/int literals) and
by an automated regression test (`test_no_built_in_preset_embeds_a_tenant_specific_id`) scanning
every entry for `product_id`/`category_id`/`collection_id`/`brand_id`/`source_id`/`product_ids`/
`manual_product_ids` keys.

## 9. Validation

Every built-in preset is validated two ways, both exercised by tests rather than left to
runtime failure for a merchant:
- Section/page shape at Python import time (registry-level, `InvalidLayoutPresetError`).
- Appearance/header/footer shape via `preset_service.validate_layout_preset`, exercised by
  `test_all_built_in_presets_pass_validate_layout_preset`.

`RejectsInvalidPresetShapeTests` and `ValidationRejectionTests` prove the negative cases too:
unknown section key, section not allowed on the target page, invalid section settings, invalid
appearance/header/footer overrides — all rejected before registration or before any write.

## 10. Draft/Published lifecycle

Verified end-to-end, both in targeted tests and live browser QA:
- Applying a preset changes the Draft only; the Published version's home-page sections are
  byte-identical before/after (`test_apply_targets_draft_only_published_unchanged`); the public
  route's rendered section count is unchanged.
- Preview (staff-only, always renders Draft) reflects the new composition immediately.
- Publish swaps the pointer; the public route's rendered section count then matches the preset.
- The next Draft created after that publish (via the existing generic version-cloning mechanism)
  preserves the applied preset's composition and its `layout_preset_key` marker with zero new
  cloning code (`test_next_draft_after_publish_preserves_preset_result`).

## 11. All-six-page coverage & Header/Footer handling

Every built-in preset defines a composition for all 6 `StorefrontPage` types (verified by
`test_every_built_in_preset_covers_all_six_pages`); `apply_preset` populates all 6 in one call.
Header/footer changes land on `StorefrontLayoutVersion.header_config`/`footer_config` exactly as
Phase 4 designed — never as page sections. Confirmed by
`test_header_footer_config_land_on_version_not_sections`, which also confirms the one section
type with "header" in its name (`collection_header`) is a genuine per-page content section, not
a global-region duplicate.

## 12. Family compatibility & legacy boundary

`LayoutPresetDefinition.compatible_families` defaults to `None` ("universal" — compatible with
the canonical Universal shell any store renders through), deliberately **not** the legacy
`PresetDefinition.family_slug`'s required 1:1 coupling. `apply_preset` succeeds regardless of a
Draft's current `family_slug`/legacy `preset_slug` value, and leaves those fields completely
untouched (`FamilyCompatibilityTests`). No file under `family_registry.py`/`preset_registry.py`/
the 11 family templates was modified. Existing legacy regression suites — family switching
(`test_family_registry.py`, `test_family_default_section_reset.py`), the 11-preset registry
import guard (`test_preset_registry_import.py`), and all 11-family tests
(`test_eleven_families.py`) — 117 tests total, all still pass unchanged, confirming the shared
`layout_service.validate_appearance_config`/`models.APPEARANCE_CONFIG_DEFAULTS` extension didn't
regress the frozen system.

## 13. Tests run

- New: `test_layout_preset_registry.py` (9 tests — built-in preset validity, reference safety,
  family-compatibility default, rejection of malformed definitions) +
  `test_preset_service.py` (30 tests — validation rejection, Draft-only/publish lifecycle,
  all-six-pages/ordering/responsive/settings preservation, merchant-content preservation, tenant
  isolation, transactional rollback, idempotent re-apply, next-draft preservation, palette
  separation, family-compatibility independence, auth/CSRF/unknown-key safety at the view level).
  **39/39 pass.**
- Directly-affected regression (shared `layout_service.py`/`models.py` changes): full
  `test_family_registry.py` + `test_family_default_section_reset.py` + `test_appearance.py` +
  `test_preset_registry_import.py` + `test_eleven_families.py` — **117/117 pass, unchanged.**
- Full `test_views.py` (shared `views.py` module touched) — **159/159 pass** (one expected
  simulated-failure traceback logged by an existing flaky-update test, matching prior-phase
  behavior, not a new failure).
- `manage.py check`: clean. `manage.py makemigrations --check --dry-run`: no changes detected
  (the new `layout_preset_key` default is a plain Python dict key, not a schema change — no
  migration needed, consistent with how `family_slug`/`preset_slug` were added previously).
- Not run this phase: the full `apps.storefront_builder` suite (814+ tests) or the cross-app
  suite — the change's blast radius (one new module, one new service, one new view, additive
  template/panel changes, two new keys in a shared but already-tested validator) was judged to
  not justify it; the directly-affected suites above cover every shared file actually modified.

## 14. Browser QA

Playwright, desktop (1440×900) and mobile (375×812), against the `sfb-phase4-qa` store, using
the **real** user flow (editor page → htmx-loaded "ظاهر سایت" tab → "پیش‌تنظیمِ صفحه‌آرایی" tab,
not direct navigation to the partial's URL, which — as expected — renders unstyled since it's an
htmx-fragment-only endpoint by design):

- Preset gallery renders correctly inside the single-screen builder, all 4 cards with label/
  description/apply button, active preset highlighted — both viewports, screenshot-confirmed.
- Applying `premium_boutique` (with the JS confirm dialog, same pattern as the existing family
  switcher) succeeds; Draft preview immediately shows the new 8-section composition; the public
  homepage's rendered section count stays unchanged until publish.
- Manual edit controls (section toggle/reorder) remain present and functional in the editor
  immediately after a preset apply.
- Publish activates the preset publicly (public section count changes to match; success toast
  shown).
- Palette switched independently of the applied preset; composition unaffected.
- Applying a second, structurally different preset (`clean_minimal`) changed the Draft's section
  count from 8 to 4 and visibly changed density/button style/card layout in the live preview
  screenshot — confirmed **not** a color-only difference.
- All 6 page types (`home`/`product_detail`/`listing`/`collection`/`search`/`cart`) preview
  successfully (HTTP 200) after preset application.
- Zero console errors on both viewports across the entire flow.

## 15. Known limitations

- Built-in presets number 4, not a merchant-authorable set — per the audit's explicit data-model
  decision (Python registry, not a DB model), adding a new preset is a code change, not a UI
  action. This matches every sibling registry in this codebase and was an explicit,
  evidence-based choice, not an oversight.
- `compatible_families` is currently descriptive only — `apply_preset` does not gate on it (no
  built-in preset restricts itself to a subset of families, and Family/Preset are architecturally
  orthogonal in this phase). Should a future preset genuinely need a structural assumption that
  only holds for specific families, the field is ready to be enforced without a schema change.
- No merge/non-destructive-apply mode was built beyond full delete-and-recreate per covered page
  — per the master instruction's explicit "do not over-engineer multiple merge strategies unless
  product evidence requires them."

## 16. Phase 7 prerequisites

The Preset System is fully additive and orthogonal to the legacy Family/Preset/Palette system —
Phase 7 (Legacy Family Migration/Retirement) can proceed independently. When Phase 7 extracts
useful token combinations from the frozen `preset_registry.py` (Owner Decision 8's stated
long-term intent), `layout_preset_registry.py`'s `LayoutPresetDefinition` is the ready target
shape — no further registry/service work is needed to receive that extraction.

## Owner-local Heavy Gate (PowerShell)

```powershell
cd <repo-root>
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.storefront_builder
python manage.py test apps.catalog apps.cart apps.dashboard
```

## Report status

`IMPLEMENTATION_COMPLETE`
`TARGETED_RUNTIME_VERIFIED`
`BROWSER_VERIFIED`
`OWNER_HEAVY_GATE_PENDING`
