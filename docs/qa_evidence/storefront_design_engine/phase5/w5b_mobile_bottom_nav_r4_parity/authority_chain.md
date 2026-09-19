# W5B — Authority Chain Verification

Every step below is source-verified. Only the steps marked **NEW** were
added by W5B; every other step is pre-existing and byte-for-byte unmodified.

```
GLOBAL_MOBILE_NAV_REGION (global_region_registry.py, pre-existing)
    9 registered variants: hidden, luxury_floating_cart, four_item, five_item,
    raised_cart, floating_dock, glass_dock, minimal_icons, wide_cart
    |
    v
mobile_nav_variants read projection (r4_views.py::_build_global_design_context) -- NEW
    [{"key": v.key, "label_fa": v.label_fa} for v in list_global_variants(...)]
    (mirrors the existing header_variants/footer_variants entries exactly)
    |
    v
R4 selector (r4/editor.html) -- NEW
    <section data-r4-global-mutation="footer.update">
      <select data-r4-global-field="mobile_nav_variant"> ... </select>
    </section>
    |
    v
existing generic change handler (r4_editor.js) -- UNCHANGED, ZERO new code
    field.closest('[data-r4-global-mutation]') -> {type: "footer.update", patch: {mobile_nav_variant: <key>}}
    |
    v
footer.update mutation (r4_mutation_service.py::_apply_footer_update) -- EXTENDED
    _FOOTER_UPDATE_ALLOWED_PATCH_KEYS now includes "mobile_nav_variant"
    candidate["mobile_nav_variant"] = patch["mobile_nav_variant"] (new line)
    |
    v
layout_service.validate_footer_config() -- UNCHANGED
    already validated mobile_nav_variant against GLOBAL_MOBILE_NAV_REGION
    before W5B (lines 333-335) -- W5B did not touch this function at all
    |
    v
appearance_authority_service.apply_footer_variant(mobile_nav_variant=...) -- UNCHANGED
    already called on every footer.update (was already passing
    cleaned["mobile_nav_variant"] before W5B); W5B did not touch this
    function at all
    |
    v
typed manifest selections["bottom_nav"] + footer_config["mobile_nav_variant"] mirror -- UNCHANGED
    |
    v
existing Preview/Public renderer (storefront_appearance/rendering.py::global_renderer_template,
preview.html, ready_template_live_preview.html) -- UNCHANGED
    resolves the typed selection (or falls back to the footer_config mirror
    only while the typed selection is still at its safe default) to the
    variant's registered `renderer` template path -- the exact same
    resolution every other global-region family already uses
```

## No parallel authority

- **One registry**: `GLOBAL_MOBILE_NAV_REGION`. No second variant list anywhere
  (the R4 projection, the test suite's coverage tests, and the browser QA
  script's representative-variant selection all derive from it directly).
- **One mutation type**: `footer.update`. No new mutation type was added to
  `_dispatch_mutation`'s allowlist.
- **One validator**: `layout_service.validate_footer_config()`. Not touched.
- **One sync point**: `appearance_authority_service.apply_footer_variant()`.
  Not touched.
- **One renderer resolution function**: `global_renderer_template()`. Not
  touched.
- **Zero new JS**: the existing delegated `change` handler in `r4_editor.js`
  (`field.closest('[data-r4-global-mutation]')`) already covers any field
  nested inside any element carrying `data-r4-global-mutation`, so a
  brand-new sibling `<section>` works with no JS file change at all
  (verified: `git diff` shows zero changes to any `.js` file in this PR).

## Reset behavior (documented, unmodified)

`preset_service.reset_footer_to_baseline()` (called by the existing
`footer.reset_to_baseline` R4 mutation) replaces the ENTIRE `footer_config`
JSON — including `mobile_nav_variant` — with the Ready Template's baseline
snapshot. Mobile Bottom Navigation reset is already covered by the existing
Footer reset; W5B adds no independent "Reset Bottom Nav" control, per the
plan's explicit non-goal.
