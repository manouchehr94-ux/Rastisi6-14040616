# P5-W4B — 50-Template Curation: Implementation Plan

**Approved design head:** `75decc08d9569b45744930044cc29a4dce65bb43`
**Certified official base:** `707dd631e851bdd13173bf3950489142f3e526b1`
**Branch:** `feature/phase5-w4b-template-curation`

This plan implements the approved design exactly — no reinterpretation.
Source documents: `docs/superpowers/specs/2026-09-16-phase5-w4b-50-template-curation-design.md`
and `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/w4b_curation_inventory.md`
(§15 final implementation matrix, §16 newsletter-terminal contract) at
the head above.

## Scope lock

21 curated keys, all `1`→`2`. Mechanisms: `collection_tiles`×7,
`brand_carousel`×7, `story_rail`×7. Placement: append at end for 14 keys
(+ `harbor_imports`/C10); insert immediately before `newsletter` for 7
keys (`niloufar_glass`, `beauty_dew`, `laleh_play`, `almas_luxury`,
`green_workshop`, `pine_eco`, `mirror_beauty`). One new
`_STATIC_SECTIONS` token: `"collection_tiles"`. `layout_preset_registry.py`
is not touched. Migrations: 0.

## Task sequence

### 1. Capture certified W4A fingerprints (before any production edit)

While `a8_ready_templates.py` still matches the certified base exactly,
write a one-off script that imports the current module, computes
`fingerprint(get_layout_preset_version(key, "1"))` for the 21 curated
keys using the exact freeze algorithm from the design (§11:
`dataclasses.asdict` + deterministic recursive freeze + sha256), and
prints the resulting `{(key, "1"): sha256hex}` dict literal. Paste that
literal as `CERTIFIED_W4A_FINGERPRINT` into the new test module (task 2).
Evidence: save the script's exact output.

### 2. Write RED contract tests

New test module: `apps/storefront_builder/tests/test_w4b_template_curation.py`
(follows repository naming convention, sits beside the existing
`test_a8_*`/`test_u10_*` modules). Covers, in one `SimpleTestCase`-based
suite (no DB needed — mirrors `test_a8_ready_template_contracts.py`'s own
class, except the fingerprint/safety-scan tests reuse `dataclasses.asdict`
which is DB-free too):

- exact-50 (`A8_READY_TEMPLATES`, `list_ready_templates()`)
- explicit 21-key version map (`1`→`2`)
- historical resolvability + fingerprint equality against the frozen
  `CERTIFIED_W4A_FINGERPRINT` from step 1
- historical forbidden-payload scan (reuses
  `test_a8_ready_template_catalog.py`'s own `_walk`/`FORBIDDEN_DATA_KEYS`/
  regex pattern, imported or duplicated verbatim, over the 21 historical
  entries)
- exact composition-token matrix per curated key (old vs new tuple,
  reading `apps.storefront_builder.a8_ready_templates._SPECS` /
  `_HISTORICAL_SPECS` directly)
- newsletter-terminal assertion for the 7 keys
- composition compiles through `_home()`, resulting section keys
  registered + home-allowed
- rejected mechanisms (`blog_posts`, `promo_cards`, `image_slider`,
  `trust_features`) absent from all 21 *new* additions (pre-existing
  baseline uses elsewhere untouched — not asserted against)
- `recipe_signature()` 50/50 unique

### 3. Prove RED

`python manage.py test apps.storefront_builder.tests.test_w4b_template_curation --settings=shop_core.settings`
against unmodified production code. Expect failures for: versions still
`"1"`; `_HISTORICAL_SPECS` not defined; `"collection_tiles"` token not
compiling. Save exact output as evidence.

### 4. Implement the approved curation

`apps/storefront_builder/a8_ready_templates.py` only:
- `_STATIC_SECTIONS["collection_tiles"] = "collection_tiles"`.
- Edit each of the 21 `_RecipeSpec` rows in place: `version` `"1"`→`"2"`,
  `composition` per the approved matrix (append or insert-before-newsletter
  per key). No other field changes.
- Before editing each row, copy its exact pre-edit `_RecipeSpec` literal
  into a new `_HISTORICAL_SPECS` tuple.
- After the existing `A8_READY_TEMPLATES = tuple(_build(spec) for spec in
  _SPECS)` + registration loop, add:
  ```python
  for _historical_spec in _HISTORICAL_SPECS:
      register_layout_preset(_build(_historical_spec))
  ```

### 5. Focused GREEN

New tests + `test_a8_ready_template_catalog`, `test_a8_template_diversity`,
`test_a8_component_coverage`, `test_a8_ready_template_contracts`,
`test_u10_ready_template_catalog`, plus source-discovered canonical
preset/candidate/apply tests (`test_preset_service`,
`test_layout_preset_registry`, `test_preset_candidate_preview`).

### 6. Exact-50 / version / history regression

Covered by step 5's suites directly (no separate run needed — the same
tests assert this).

### 7. All-50 canonical apply/resolve regression

Reuse `test_u10_ready_template_catalog.py::ApplyAndRenderSmokeTests`'
pattern (or the actual existing test if it already iterates all 50) to
confirm every latest Ready Template resolves/applies without error.

### 8. Bounded W4B browser QA

Reuse `tools/storefront_builder_r4_qa/run.mjs` infra. One shared fixture
Store with ≥1 active `MerchantCollection`, ≥1 active `Brand`, ≥1
`StoryRailItem`. For each of the 21 curated latest v2 templates: 3
viewports, RTL, header/footer/bottom-nav-once, new section visible with a
real (non-`#`) link where applicable, newsletter terminal for the 7.
Latest-vs-historical (v2 vs v1) same-fixture comparison per key.

### 9. Full `storefront_builder` regression

`python manage.py test apps.storefront_builder.tests --settings=shop_core.settings`,
diffed by failure/error identity against
`docs/qa_evidence/storefront_design_engine/phase5/w4a_public_shell_convergence/32_full_storefront_builder_exact_head.txt`.

### 10. Architecture/duplication gate

Confirm no new renderer/registry/section type/Theme/Random-Mix/tenant-
resolver/ProductCard path/CMS subsystem/merchant-policy subsystem; zero
migrations; `layout_preset_registry.py` untouched.

### 11. Evidence + implementation report

Under `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/`.

### 12. PR — OPEN, UNMERGED

base `feature/phase5-design-expansion`, head
`feature/phase5-w4b-template-curation`.

## Self-review against the approved design

- Mechanisms/placement/version map/token: copied verbatim from design
  §8/§10 and inventory §15/§16 — no deviation introduced.
- No file outside `a8_ready_templates.py` is planned for production
  edits; `EXPECTED_LATEST_VERSIONS` in the existing catalog test is a test
  file, in scope per the design's own "files expected to change" list.
- No TODO/TBD left in this plan.
