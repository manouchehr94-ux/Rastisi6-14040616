# storefront_builder — Testing

```
domain_id: D9
code_baseline: 5883a140
```

Largest test footprint in the repo (~61k test LOC). Source: `apps/storefront_builder/tests/`.

| Behavior | Test file |
|---|---|
| R4 inspector / showcase / appearance registry | `test_r4_inspector.py`, `test_r4_showcase_facade.py`, `test_r4_store_appearance_registry.py` |
| Page slots / scoped section resolution | `test_storefront_page.py` |
| Render contract (`build_render_items`) | `test_render_service.py` |
| Layout preset registry | `test_layout_preset_registry.py` |
| Template gallery / preset-would-replace-content | `test_u8_template_gallery.py` |
| Ready Template preview UX / live/merchant preview | `test_phase5_w5c_ready_template_preview_ux.py`, `test_task2_live_demo_template_preview.py`, `test_task3_merchant_template_preview.py` |
| Capability metadata wiring | `test_u1b2_capability_metadata_wiring.py` |
| PageType-constants-match-model guard | `test_section_registry.py::PageTypeConstantsMatchModelTests` (keeps the duplicated 6 PageType strings in sync — L3) |

## Notes
- The `PageTypeConstantsMatchModelTests` guard exists because the 6 page-type strings are hardcoded
  in `section_registry.py`/`a8_ready_templates.py` rather than imported from the model enum (L3).
- Client-side R4 JS is not unit-tested directly; the mutation boundary is covered via server tests
  of `r4_mutation_service`.

See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
