# Storefront Builder V2 — Phase 6 Read-Only Gap Audit: Preset System

**Base SHA**: `540b23352424ea5af3c0b9cdc107999e479e2657` (canonical synchronized HEAD, confirmed)
**Status**: audit only — no implementation in this document.

## 0. Critical framing — two unrelated "Preset" systems exist in this codebase

This is the single most important finding of this audit, and it must not be conflated.

There are **two entirely separate systems that both use the word "preset"**:

1. **The legacy Family/Preset/Palette system** — fully built, production code:
   `apps/storefront_builder/family_registry.py`, `apps/storefront_builder/preset_registry.py`,
   `apps/storefront_builder/appearance_registry.py`. This is the system behind the 11 legacy
   "storefront families" (Modern Fashion, Artisan Editorial, Nordic Living, Heritage Premium,
   Vibrant Catalog, Atlas Catalog, Ava Fashion, Toranj Gifting, Sarv Stock, Sepidar Handmade,
   Zarrin Jewelry). It composes **only the home page**, renders through **dedicated
   Django-template forks per family** (not the universal `StorefrontSection` engine), and is
   **explicitly frozen by owner decision**.
2. **The Universal Storefront Builder V2 Preset System** — the actual subject of this phase.
   Per `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` §5.7 ("A preset is **data**,
   not a new family implementation") and §Phase 6, and
   `docs/architecture/STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` §10 ("Phase 6 — Presets ...
   one neutral default preset, one complex real-world-inspired preset, and — later — migration
   of useful legacy Family designs into presets"), this system does **not exist yet**. It is
   meant to sit on top of the now-fully-generalized `StorefrontPage`/`StorefrontSection` engine
   that Phases 0.5–5 built (all 6 page types, registry-driven, allowlisted, context-aware).

**Freeze authority — `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md:35`:**
> "Preset Registry (11 per-family token bundles) | `apps/storefront_builder/preset_registry.py` |
> SOURCE_ONLY | LEGACY_KEEP / FREEZE **(now locked — Owner Decision 8)** | Same freeze as Family
> Registry — extract useful token combinations into V2 design presets rather than deleting, no
> new preset additions in the meantime | Structurally very close to what spec §22 calls a
> 'Preset' already — good extraction candidate, extraction itself is Phase 6"

**Consequence for this phase**: `family_registry.py`, `preset_registry.py`, `appearance_registry.py`
are read-only reference material for this audit. **Nothing in them is modified.** No new entries
are added to `PRESET_REGISTRY` (the legacy one). A new, separately-named registry is required for
the V2 system — see §7.

Also flagged by the reuse matrix as an unrelated naming collision to avoid: `apps/core/theme_presets.py`
(`ThemePreset` — 6 old color-only presets for `ShopSettings`, nothing to do with either system above).

## 1. Does a real V2 Preset concept already exist?

**MISSING.** No model, registry, or JSON structure scoped to `StorefrontPage`/`StorefrontSection`
across all 6 page types exists anywhere in the repo. The legacy `preset_registry.py` exists (see
§0) but is architecturally the wrong shape for V2 — see §4.

## 2. Is Palette already separate from Preset/appearance?

**ALREADY EXISTS**, and directly reusable as-is. `appearance_registry.py`:
- `PaletteDefinition(slug, name_fa, group_fa, colors: dict[str, str])` — exactly the 8
  `APPEARANCE_COLOR_KEYS` (primary/secondary/accent/background/surface/text/muted/border).
- `PALETTE_REGISTRY` — 20 registered palettes.
- `resolve_colors(appearance_config)` — base palette + merchant `color_overrides` merge.
- Palette is **global and independent of Family by explicit owner decision**
  (`family_registry.py:20`: "Palette همیشه Global می‌ماند (تصمیمِ مالک)" — "Palette always stays
  Global — owner's decision"), already selectable independently of Family/Template in the
  appearance editor UI (`appearance_panel.html`, `view === 'palettes'` tab).
- **Conclusion**: Palette needs zero new work for V2. A V2 Preset applies typography/density/
  motion/composition/header/footer; color always stays on the existing, separate `palette_slug`
  + `color_overrides` mechanism already on `appearance_config`. This directly satisfies the
  master prompt's "Preset A + Palette Light / Preset A + Palette Dark" requirement for free.

## 3. Are "family defaults" currently functioning as presets?

**Partially, and only for Home.** `FamilyDefinition.default_section_keys` (`family_registry.py:60`)
is a flat tuple of section keys applied only to `version.home_page()` via
`bootstrap_service.apply_family_default_sections()`
(`services/bootstrap_service.py:219-244`, read in full below). It is a real, working "apply a
default composition" mechanism — but it is 1:1-coupled to a Family (each family has exactly one
`default_preset_slug`, and `preset_registry.PresetDefinition.family_slug` is a required field,
`preset_registry.py:24`), home-page-only, and mutates by hard delete-and-recreate with no
Draft-only/Published-safety framing beyond "the caller passed a Draft." It is a working precedent
for *how* to safely replace a page's sections, not a preset system merchants can reuse across
structures.

## 4. Which values currently belong to Family but should belong to Preset (for V2)?

None need to move — Family (DOM/renderer identity, 11 legacy-only) and the new V2 Preset concept
are orthogonal: V2 Presets operate entirely within the **one** canonical Universal renderer, they
never select a family's `header_variant`/`hero_variant`/etc. Family is frozen and out of scope
here (Phase 7 territory).

## 5. Which values currently belong to Preset-like config but should stay global appearance?

**Color** — `palette_slug`/`color_overrides` must stay on `appearance_config` exactly as today
(§2). A V2 Preset should be able to *suggest* a default palette but must never own color storage
itself, mirroring the existing legacy `PresetDefinition.default_palette_slug` "suggestion, not
lock" pattern (`preset_registry.py:37-39`) — merchant remains free to pick any of the 20 palettes
after applying a preset.

## 6. Is Palette already a separate concept? (duplicate of Q2 in the master prompt's list)

Yes — see §2.

## 7. Are typography tokens structured?

**PARTIAL, reusable.** `appearance_registry.py`:
- `FONT_CHOICES` — 4-item curated enum.
- `TYPE_SCALE_CHOICES = ("compact", "normal", "large")` + `TYPE_SCALE_SIZES` — a real 3-tier,
  5-role (heading/body/product_name/price/muted) structured token dict, resolved via
  `resolve_typography(type_scale)`.
- This is directly reusable by a V2 Preset (a preset just picks one of the 3 `type_scale` values
  plus a `font`) — no new typography infrastructure needed.

## 8. Are spacing/density tokens structured?

**PARTIAL.** Only a coarse 3-value enum exists: `DENSITY_CHOICES = ("compact", "normal", "relaxed")`.
No granular spacing scale (no equivalent of `TYPE_SCALE_SIZES` for spacing). This is sufficient
for V2 Presets to consume as-is (a preset picks one of 3 density values) — building a finer-grained
spacing token system is **not required** by the master prompt ("Only expose settings that the real
rendering system can consume") and is out of scope for this phase.

## 9. Are motion tokens structured?

**PARTIAL**, same shape as density: `MOTION_CHOICES = ("none", "subtle", "dynamic")`, consumed as
a CSS custom property / `data-motion` attribute at render time. Sufficient for V2 Presets to
select from directly; no new motion infrastructure needed.

## 10. Are section compositions serializable as data?

**ALREADY EXISTS, and is exactly the right shape.** Two directly-reusable precedents from Phase 5:
- `section_registry.SectionDefinition.default_settings: Callable[[], dict]` — every section type
  already has a pure-data default-settings function.
- `bootstrap_service._DEFAULT_NON_HOME_SECTION_KEYS` (`bootstrap_service.py:111-117`) — literally
  `{page_type: [section_key, ...]}` for all 5 non-home pages, consumed by
  `build_default_non_home_sections(page_type)` which returns
  `[{"section_key", "order", "settings"}, ...]` — this **is** the "ordered section-key + settings
  list per page type" shape the master prompt asks a Preset's `pages.*` field to hold. A V2
  Preset's page composition field can be structured identically, just indexed by preset instead
  of being a single hardcoded default.

## 11. Can Header/Footer configs be preset as data?

**ALREADY EXISTS.** Phase 4 made `header_config`/`footer_config` structured JSON directly on
`StorefrontLayoutVersion` (`models.py`), validated by `layout_service`. A V2 Preset can carry a
`header` / `footer` dict that gets assigned wholesale to
`draft.header_config`/`draft.footer_config`, validated through the exact same validators the
manual Header/Footer composer UI already uses — no new schema needed, only reuse.

## 12. Can all six page compositions be preset as data?

**Architecture supports it (Phase 5); no preset-level implementation exists yet.** Every one of
the 6 `StorefrontPage` types now has ordered, registry-validated `StorefrontSection` rows and a
page-type allowlist (`section_registry.is_section_allowed_on_page`). Nothing prevents a Preset
definition from carrying a `pages: {home: [...], product_detail: [...], listing: [...],
collection: [...], search: [...], cart: [...]}` shape and looping the same
create-sections-per-page logic Phase 5's `apply_default_non_home_sections` already uses. This is
the core net-new implementation work of this phase (§16).

## 13-14. Is applying a preset Draft-only? Does it preserve Published until publish?

**No existing V2 mechanism to inherit this from directly, but a solid pattern exists to copy.**
`apply_family_default_sections(version, family)` (`bootstrap_service.py:219-244`) takes an
explicit `version` parameter (never resolves "the current draft" itself — caller's
responsibility), and is proven Draft-only/Published-safe by
`test_family_default_section_reset.py::test_published_version_untouched_until_republish`. The new
`preset_service.apply_preset(draft, preset)` (this phase's real work) must follow the identical
shape: take an explicit Draft `StorefrontLayoutVersion`, never resolve or touch
`layout.published_version`, and ship with an equivalent isolation test per page type (not just
home, since V2 spans 6 pages).

## 15. Does applying a preset overwrite merchant content?

**Precedent says yes for structure, no for business data — this needs an explicit, narrower rule
for V2.** The legacy `apply_family_default_sections` is a **full delete-and-recreate** of the home
page's sections — a destructive reset, gated by a UI confirmation checkbox
(`storefront_appearance_editor`, confirmed via `confirm_family_switch`). For V2 Presets, per the
master prompt's explicit STRUCTURAL vs. MERCHANT CONTENT distinction, the same delete-and-recreate
approach is architecturally correct for section composition/settings (that data is 100%
structural/presentational — see §12's evidence that `default_settings()` never contains
merchant-entered values), **provided** no default settings anywhere reference an actual product/
category/collection ID (confirmed clean — see §21). Uploaded media, manually-entered promotional
text values, and business data live in unrelated models (`catalog`, `content`, `core`) that a
section-replace operation never touches by construction (it only ever calls
`StorefrontSection.objects.all().delete()`/`bulk_create` scoped to page/version). This must be
carried forward and tested explicitly for V2 (all 6 pages, not just home).

## 16. Can applying a preset be safely repeated?

Precedent (`test_leaving_and_reselecting_same_family_yields_the_same_stable_default`) proves the
existing home-only mechanism is idempotent/deterministic on repeat. The V2 service must replicate
this: re-applying preset X to a Draft that already has preset X applied produces the same result,
no error, no accumulation.

## 17-18. Is there a reset-to-family-default flow, and can it become the basis of Preset application?

Yes — `apply_family_default_sections` is precisely that flow, and its delete-then-bulk-create
pattern, generalized across all 6 pages plus header/footer/appearance, **is** the basis for
`preset_service.apply_preset`. It should not be literally called (it is Family-scoped and frozen
by Owner Decision 8) but its pattern is the template to replicate in new, unfrozen code.

## 19. Are media assets safe during preset application?

Yes by construction, same reasoning as §15 — section-settings default values never carry media
IDs (verified §21), and the operation never touches media models directly.

## 20. Are tenant references safe?

Yes by construction — `apply_preset` must take an explicit Draft (already store-scoped via
`StorefrontLayout` OneToOne) and never accept or resolve any store/tenant ID itself, exactly like
every other service in this app (`layout_service`, `bootstrap_service`).

## 21. Are product/category/collection IDs embedded in defaults anywhere?

**Confirmed clean — no matches found.** Grepped `family_registry.py`/`preset_registry.py` for
`product_id|category_id|collection_id|brand_id|source_id`: zero hits.
`default_section_keys`/`_DEFAULT_NON_HOME_SECTION_KEYS` are always bare string section keys, never
numeric IDs; every section type's `default_settings()` returns store-agnostic literals
(booleans/enums/empty lists). Any product/category/collection a section actually needs is resolved
per-store at render time by `services/section_data_service.py`, never baked into a registry
default. This is the direct precedent for the master prompt's "use neutral defaults such as
`data_source = newest` ... never persist example IDs" requirement — the codebase already
enforces exactly this discipline for every existing default-composition mechanism, and the V2
Preset system must simply continue it.

## 22. What tests already exist?

Extensive coverage of the **legacy** system only:
`test_family_default_section_reset.py`, `test_family_registry.py`, `test_eleven_families.py`,
`test_preset_registry_import.py`, `test_appearance.py`
(`PaletteRegistryTests`/`TypographyScaleTests`/`AppearanceDraftPublishIsolationTests`), plus
per-family renderer/isolation tests. **No matches found** for any test scoped to a V2, multi-page,
`StorefrontSection`-based preset system — that category does not exist yet, per
`STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` §8's own test-plan categories (listed as future
work).

## 23. What browser behavior already exists?

The legacy family/palette/template gallery UI in `appearance_panel.html` — family cards with
apply+confirm, template gallery, palette gallery, colors tab, advanced tab (font/radius/density/
motion/type_scale/button_style/image behavior) — all htmx-loaded into the single-screen builder's
appearance tab, no separate page navigation. This is the correct **integration point** to extend
for V2 Preset selection (§17 UX requirement: "Do not create a completely disconnected settings
application... extend it coherently").

## 24. What legacy family behavior must wait for Phase 7?

All of it. Family retirement/migration is explicitly Phase 7. This phase touches none of
`family_registry.py`, `preset_registry.py`, the 11 family templates, or the family-switch view
logic in `storefront_appearance_editor` beyond additively wiring in a new, separate Preset
selector alongside the existing family/template/palette controls.

---

## Classification summary

| Item | Classification | Notes |
|---|---|---|
| Legacy `family_registry.py` (11 families, home-only DOM forks) | LEGACY COMPATIBILITY BOUNDARY | Frozen, Owner Decision 8. Read-only reference. Not touched this phase. |
| Legacy `preset_registry.py` (11 family-scoped token bundles) | LEGACY COMPATIBILITY BOUNDARY | Frozen. Wrong shape for V2 (1:1 family coupling, home-only, no multi-page composition applied automatically). Not extended. New, separately-named registry required. |
| `appearance_registry.py` (Palette, Template, typography/density/motion enums) | ALREADY EXISTS | Fully reused as-is by V2 Presets — palette stays independent, typography/density/motion enums consumed directly. |
| `apps/core/theme_presets.py` | OUT OF SCOPE | Unrelated naming collision only, not touched. |
| Section registry + page-type allowlists (Phase 5) | ALREADY EXISTS | Directly reused — every preset's page compositions validate against this. |
| `_DEFAULT_NON_HOME_SECTION_KEYS` / `build_default_non_home_sections` (Phase 5) | ALREADY EXISTS | Direct structural precedent for a preset's per-page section list; not modified (still the *no-preset-applied* fallback). |
| Header/footer structured config (Phase 4) | ALREADY EXISTS | Reused as-is — a preset assigns to `header_config`/`footer_config` through existing validators. |
| `apply_family_default_sections` (home-only, Family-scoped) | ALREADY EXISTS (pattern only) | Not called by V2; its delete-then-bulk-create-per-page pattern is the template to replicate, generalized to all 6 pages + header/footer/appearance, in new code. |
| V2 multi-page Preset registry/model | MISSING | This phase's core implementation work. |
| V2 preset application service (transactional, Draft-only, all 6 pages) | MISSING | This phase's core implementation work. |
| Built-in V2 preset definitions (3-5, structurally distinct) | MISSING | This phase's core implementation work. |
| Preset selector UI (extends existing appearance panel) | MISSING | This phase's core implementation work — additive to existing htmx panel. |
| Preset validation-at-import / preset service tests | MISSING | This phase's core implementation work. |

---

## Target data model decision

Per the master prompt's explicit instruction to audit first and "not introduce a database model
if a versioned Python/data registry is clearly the better architecture": the evidence strongly
favors a **Python data registry**, following the exact `section_registry.py`/`family_registry.py`/
`appearance_registry.py` pattern (frozen dataclass + module-level dict + `register_x()` +
`get_x()`/`list_x()` + import-time validation), for these reasons already proven true of every
sibling registry in this codebase:
- Built-in presets are platform-designed content ("templates the team designs," not something a
  merchant authors from scratch) — reviewed via code review/git history, exactly like the 22
  section types, 11 families, 10 templates, and 20 palettes already are.
- No requirement anywhere in the master prompt or existing spec docs for merchants to create/edit
  *new* presets — they select, apply, and then freely edit the *result* (which lives in the
  existing Draft `StorefrontSection`/`appearance_config`/`header_config`/`footer_config` rows,
  already DB-backed). The preset *definition* itself never needs per-tenant storage.
- A DB model would require a migration for every new built-in preset — the registry pattern lets a
  new preset ship as a pure code change, consistent with how every other "platform content"
  concept in this app already works.

**Proposed module name: `apps/storefront_builder/layout_preset_registry.py`** — deliberately
**not** `preset_registry.py` (already taken by the frozen legacy module — reusing or extending
that name risks exactly the confusion `STOREFRONT_BUILDER_V2_REUSE_MATRIX.md` already warns about
for `theme_presets.py`). "Layout" ties it to `StorefrontLayoutVersion`, the object a preset
ultimately configures.

Conceptual shape (to be finalized during implementation, validated at Python-import time exactly
like `_finalize_registry()` does for sections):

```python
@dataclasses.dataclass(frozen=True)
class LayoutPresetDefinition:
    key: str
    label_fa: str
    description_fa: str
    compatible_families: frozenset[str] | None  # None = compatible with the canonical shell only (all V2 stores); never auto-coupled 1:1 to a single family
    appearance: dict       # font, radius, button_radius, density, motion, type_scale, button_style, image_fit, image_hover, card_image_* — NEVER palette_slug/color_overrides (§2/§5)
    default_palette_slug: str | None  # suggestion only, merchant free to change (§5)
    header: dict | None
    footer: dict | None
    pages: dict[str, list[dict]]  # {"home": [...], "product_detail": [...], ...} — each entry {"section_key", "settings", "responsive"?}, all 6 keys optional (a preset may deliberately omit a page)
```

This shape directly satisfies the master prompt's "conceptual shape" example while grounding every
field in something already proven to exist and validate correctly (§7-§12 above).

## Application semantics (design, to be implemented)

Following the `apply_family_default_sections` precedent (§17-18), generalized:

1. `preset_service.apply_preset(draft: StorefrontLayoutVersion, preset: LayoutPresetDefinition) -> None`
   — explicit Draft parameter, never resolves "current draft" itself, never touches
   `layout.published_version`.
2. Wrapped in `transaction.atomic()` — validation happens fully before any write; if any page's
   composition or the header/footer/appearance config fails validation against the existing
   validators (`section_registry.is_section_allowed_on_page`, `layout_service.validate_appearance_config`,
   header/footer schema validators), the whole call raises and the Draft is left completely
   unchanged (master prompt: "If any validation fails: Draft must not be left half-applied").
3. Per page present in `preset.pages`: delete that page's existing sections, bulk-create the
   preset's list (same pattern as `apply_family_default_sections`, generalized across all 6 pages
   instead of home-only).
4. `header_config`/`footer_config` assigned wholesale if the preset defines them, through the same
   validation path the manual composer already uses.
5. `appearance_config`: only the structural keys (font/radius/density/motion/type_scale/
   button_style/image_*) are set from the preset; `palette_slug` is set only if the merchant
   hasn't already chosen one for this Draft (or is explicitly overridden — exact merchant-choice
   precedence to be confirmed during implementation, mirroring the existing family→preset→palette
   precedence chain in `storefront_appearance_editor`); `color_overrides` are never touched by a
   preset apply (merchant colors persist across a preset swap unless they explicitly also pick a
   new palette).

## Confirmation / destructive safety

Per the master prompt, applying a preset is presentation/structure-destructive (replaces section
composition) but never merchant-content-destructive (§15). The existing family-switch confirmation
pattern (`confirm_family_switch` checkbox + JS `confirm()` dialog, gated only when the Draft
already has non-empty sections) is the direct, already-proven UX precedent to replicate for preset
application — extended to check all 6 pages, not just home, since V2 presets can touch all of them.

## Family compatibility

Per the master prompt ("Preset X should not automatically become Family X"), and unlike the legacy
`PresetDefinition.family_slug` (required, 1:1), the new `LayoutPresetDefinition.compatible_families`
field is optional and, if omitted, means "compatible with the canonical Universal shell" (i.e. any
store, since Presets operate on the one shared renderer — Family is a legacy-only, frozen concept
that doesn't participate in the V2 rendering path at all). No new field is added to
`FamilyDefinition`; this compatibility concept lives entirely in the new registry.

## What this phase explicitly does NOT do

- Does not modify `family_registry.py`, `preset_registry.py`, or any of the 11 family templates.
- Does not add a 12th family or any new renderer/template architecture.
- Does not build a granular spacing-token scale beyond the existing 3-value density enum (no
  rendering-system consumer for anything finer exists today).
- Does not implement merge/non-destructive-apply strategies beyond the single documented
  delete-and-recreate-per-page mode (master prompt: "Do not over-engineer multiple merge
  strategies unless product evidence requires them").
- Does not touch legacy family switching behavior (still calls the frozen
  `apply_family_default_sections`, unchanged).
- Does not run the full cross-app regression suite unless a change's blast radius genuinely
  requires it (test policy, per master prompt).
