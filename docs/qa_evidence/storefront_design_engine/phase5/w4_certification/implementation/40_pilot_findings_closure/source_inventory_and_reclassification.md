# W4C Pilot Findings Closure — Home expectation reclassification (Section 2)

Confirmed by direct source reading, before any implementation.

## A. `premium_leather`'s raw composition

`apps/storefront_builder/a8_ready_templates.py:234`:

```python
_RecipeSpec("premium_leather", "3", ..., ("ticker", "chip_categories", "product_grid", "editorial_note")),
```

Confirmed: 4 raw recipe tokens.

## B. `ticker` compiles to `announcement_bar`

`apps/storefront_builder/a8_ready_templates.py:55`:

```python
"ticker": "announcement_bar",
```

## C. `announcement_bar` is `hidden_from_library=True`

`apps/storefront_builder/section_registry.py:2533-2545`:

```python
"announcement_bar": SectionDefinition(
    key="announcement_bar", ...,
    hidden_from_library=True,
),
```

Comment confirms exactly the stated reason: the canonical Header's own
announcement-bar setting already covers this same capability in a
genuinely configurable way; instantiating a second, separately-hidden
one would only double-render or mislead, so the definition is hidden
from the merchant-facing library entirely.

## D. `preset_service` filters hidden entries BEFORE writing the Draft

`apps/storefront_builder/services/preset_service.py:387-390`:

```python
entries = [
    e for e in raw_entries
    if not section_registry.get_definition(e.section_key).hidden_from_library
]
```

Confirmed exactly, with an explicit comment: "a preset recipe must not
be able to create an instance of a section the library itself hides
(e.g. `announcement_bar` ...)". `entries` (not `raw_entries`) is what
`_build_sections_for_page` actually writes as real `StorefrontSection`
rows. **`premium_leather`'s canonically-applied/published Home
therefore contains exactly 3 real Sections** (`chip_categories`,
`product_grid`, `editorial_note`), never 4.

## E. Current W4C sends the pre-filter raw count

`apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`
(pre-repair): `expected_rsec_count=len(preset.pages.get("home", ()))` —
`preset.pages` is the raw, uncompiled `LayoutPresetDefinition.pages`
dict (`tuple[PresetSectionEntry, ...]` built directly from the
`_RecipeSpec` tuple, confirmed via
`apps/storefront_builder/layout_preset_registry.py:146`), never passed
through `preset_service`'s `hidden_from_library` filter. This is the
exact bug: the harness expected 4 (raw) where the real, canonically
published, publicly-rendered page has 3.

## F. `_home_hero_index` also walks the raw recipe — broader than `premium_leather`

Same file, `_home_hero_index(self, preset)` iterates
`preset.pages.get("home", ())` (raw). Source-grepped every current spec
containing `"ticker"`:

```
premium_leather:      ("ticker", "chip_categories", "product_grid", "editorial_note")   -- no hero at all
street_drop:           ("ticker", "hero", "chip_categories", "product_rail", "sale_products")
racer_tech:            ("ticker", "hero", "chip_categories", "product_rail", "sale_products")
anniversary_mosaic:    ("ticker", "hero", "circular_categories", "bento_products", "testimonials", "newsletter")
```

For `street_drop`/`racer_tech`/`anniversary_mosaic`, `"hero"` is raw
index 1 (`_home_hero_index` currently returns `1`), but after the
canonical `hidden_from_library` filter removes `ticker`/`announcement_bar`,
the actually-published Home sequence has Hero at index **0**. The raw
index is off by exactly one position for every ticker-before-Hero
Template. (`premium_leather` itself has no `"hero"` token at all, so
`_home_hero_expected`/`_home_hero_index` correctly report
`False`/`None` for it regardless — its bug is purely the `rsec_count`,
not Hero.)

## Confirmed repro of the pilot finding

The pilot's `premium_leather Home` FAIL
(`39_rate_limit_sharding_repair/pilot_matrix.json`) showed
`rsec_count: 3, expected_rsec_count: 4` with `accessibility_ok: true`
and zero console/page/request errors — this is **not** a public
rendering regression, not an accessibility defect, and not a rate-limit
symptom. It is the harness comparing the real (correct) rendered count
against a wrong (raw, pre-filter) expectation. The real published page
was correct the whole time.

## What is explicitly NOT changed (Section 3)

- `apps/storefront_builder/a8_ready_templates.py` — `premium_leather`'s
  (or any other Template's) recipe composition is untouched. The
  `ticker` token stays exactly where the Ready Template's design
  intends it.
- `section_registry.py` — `announcement_bar.hidden_from_library` stays
  `True`. This production rule is correct and intentional; weakening it
  to satisfy a raw-count comparison would be backwards.
- `preset_service.py` — the filtering behavior at apply time is
  correct and unchanged.

The repair (Section 5) is entirely in the W4C harness's own expectation
derivation: verify the REAL canonical published/renderable composition,
not the raw recipe, reusing the exact same public render pipeline
(`render_service.build_page_render_items` +
`render_service.hide_empty_public_sections`,
`storefront_context_service.py:205-213` confirmed as the identical
two-call sequence the live public Home page itself uses) rather than
re-implementing a second hidden-section filter inside the harness.
