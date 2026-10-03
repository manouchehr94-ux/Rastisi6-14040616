# W4B — Architecture / Duplication Audit

**Scope of production change:** `apps/storefront_builder/a8_ready_templates.py`
only. `apps/storefront_builder/layout_preset_registry.py` is byte-for-byte
unchanged (`git diff` against the certified base shows no hunks in that
file).

| Item | Introduced? | Evidence |
|---|---|---|
| New renderer | **NO** | No new template engine/render path; `render_service.py` untouched. |
| New Ready Template registry | **NO** | `LAYOUT_PRESET_REGISTRY` remains the sole latest-catalog dict; `_HISTORICAL_SPECS` registers through the same `register_layout_preset`. |
| New version registry | **NO** | `LAYOUT_PRESET_VERSION_REGISTRY` unchanged; no second version-tracking structure. |
| New section type | **NO** | `collection_tiles`, `story_rail`, `brand_carousel` all pre-existed in `section_registry.py` before W4B. |
| New Store Appearance family | **NO** | `families.py` untouched. |
| New Theme mechanism | **NO** | Every one of the 50 latest + 21 historical recipes still selects `theme.none.v1` (verified: `test_a8_ready_template_contracts.py::AllReadyTemplatesDeclareCompleteManifestTests` green; the fingerprint equality test independently proves the 21 historical manifests, theme selection included, are untouched). |
| New Random Mix engine | **NO** | `design_lab_service.py` untouched. |
| New tenant resolver | **NO** | `apps/stores/resolution.py` untouched; recipes remain Store-agnostic Python data. |
| New ProductCard path | **NO** | `product_card_service`/`product_card.html` untouched. |
| New CMS/blog subsystem | **NO** | `blog_posts` was rejected and is not used anywhere in this curation; no Blog detail route was added. |
| New merchant-policy subsystem | **NO** | `trust_features` was rejected for new usage; no policy-configuration model/UI added. |
| New browser rendering/QA authority | **NO** | Reused `capture_ready_template_previews.py` (unmodified) + the existing `apply_preset_with_checkpoint`/`publish` path for the responsive supplementary checks — no new harness committed. |
| Merchant IDs/content in Template DNA | **NO** | `_STATIC_SECTIONS["collection_tiles"] = "collection_tiles"` and the 21 edited `composition` tuples add only section-type tokens; every added section's settings stay at the section type's own neutral defaults (`collection_ids: []`, `brand_ids: []`, no settings for `story_rail`) — confirmed both by the RED/GREEN historical-forbidden-payload scan and by the existing `test_recipes_contain_no_tenant_executable_or_prototype_payload` (still green over `list_ready_templates()`). |
| New migrations | **NO** | `makemigrations --check --dry-run` → "No changes detected" (evidence 07). |

## Registry-shape verification

- `A8_READY_TEMPLATES` (module-level tuple) — exactly 50, built only from
  `_SPECS` (test: `ExactFiftyLatestCatalogTests.test_a8_ready_templates_is_exactly_fifty`).
- `lpr.list_ready_templates()` — exactly 50 (same test class, second
  method) — the dedup-by-key max-version-wins behavior in
  `register_layout_preset` was not touched.
- `lpr.list_layout_presets()` (ALL registered, latest+historical+internal)
  grew by exactly 21 (the new `_HISTORICAL_SPECS` entries) —
  `test_layout_preset_registry.py::test_five_internal_plus_fifty_latest_ready_templates_are_registered`
  stayed green, meaning the "5 internal + 50 latest" surfaced count is
  unaffected by the 21 additional historical-only registrations (they are
  invisible to that surfaced count by construction, exactly as designed).
- Historical resolvability: `get_layout_preset_version(key, "1")` returns
  a distinct object from `get_layout_preset(key)` for all 21 curated keys,
  and its full-object fingerprint matches the pre-curation capture exactly
  (companion evidence: `00_certified_w4a_fingerprints.md`,
  `02_green_w4b_contract_tests.txt`).

## Files changed (complete list, this workstream)

Production:
- `apps/storefront_builder/a8_ready_templates.py`

Tests:
- `apps/storefront_builder/tests/test_a8_ready_template_catalog.py` (`EXPECTED_LATEST_VERSIONS` literal update only)
- `apps/storefront_builder/tests/test_w4b_template_curation.py` (new)

Docs/plans/evidence:
- `docs/superpowers/plans/2026-09-16-phase5-w4b-50-template-curation-implementation.md` (new)
- `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/*` (new, this workstream's evidence)

No file under `apps/storefront_builder/layout_preset_registry.py`,
`render_service.py`, `section_registry.py`, `families.py`,
`design_lab_service.py`, `resolution.py`, or any product_card/cart file
was touched.
