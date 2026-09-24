# W4C Final Certification Campaign — Architecture/Duplication Audit

FINAL_CAMPAIGN_HEAD: `0d2ab09ed40c9df566b9bc551e3065ecf95ce281` (repaired source)

## Scope note

This round certifies the **repaired** source: `green_workshop`,
`laleh_play`, `parnian_editorial` bumped v2 -> v3 (hero changed only) plus
2 test-bookkeeping updates and 3 fresh static preview artifacts. All other
production/harness code is byte-identical to the previously-audited state.
The checks below re-confirm the architectural invariants still hold on this
exact source, and add the two checks this round's directive specifically
calls out: no new Ready-Template/version-history authority, and the visual
repair used only existing registered components.

## Checks performed (this round, against current source)

| Authority | Check | Result |
|---|---|---|
| Browser harness | `tools/` contains exactly two runner directories: `storefront_builder_qa` (R3) and `storefront_builder_r4_qa` (R4/W4C) | Unchanged; `storefront_builder_r4_qa/run.mjs` still reuses R3's `playwright-core` via `createRequire`, not a vendored second copy |
| Ready-Template registry | `grep -rn "def list_ready_templates"` | Exactly one definition: `apps/storefront_builder/layout_preset_registry.py:221` |
| Version-history authority | `grep -n "def register_layout_preset\|def get_layout_preset\b\|def get_layout_preset_version"` | Exactly one of each, all in `layout_preset_registry.py` (190/208/212). The repair's 3 new historical rows were registered through this same single authority — `_HISTORICAL_SPECS` is one tuple, not a second registry |
| Preset-apply authority | `apply_preset` / `apply_preset_with_checkpoint` | Unchanged, single definition in `apps/storefront_builder/services/preset_service.py` |
| Publish authority | `layout_service.publish` | Unchanged, single definition in `apps/storefront_builder/services/layout_service.py` |
| Theme owner | Theme cell mutation path | Unchanged; no parallel Theme-mutation path introduced |
| Cart implementation | `grep -rln "cart:item-remove"` across templates | Exactly one file: `apps/storefront_builder/templates/storefront_builder/sections/cart_items.html` |
| ProductCard implementation | Card rendering driven by the single shared `card` appearance-selection pipeline | Confirmed — no duplicate `product_card` template tree |
| Bottom Navigation system | Rendered via the single shared `bottom_nav` appearance-selection pipeline | Confirmed |
| Search backend | No second `search_products`/search-backend implementation found | Confirmed |
| Tenant resolver | Single tenant/host resolver remains `apps/stores/resolution.py`; `storefront_appearance/rendering.py`'s `resolve_store_appearance_render_state` resolves an appearance/theme manifest, a distinct concern | Confirmed — no duplication |
| Template-name render branches | `grep -n "green_workshop\|laleh_play\|parnian_editorial"` across `apps/storefront_builder/services/*.py` and `apps/storefront_builder/*.py` (excluding `a8_ready_templates.py` and `tests/`) | **Zero matches.** The visual repair changed only each key's `hero` field in its `_RecipeSpec`/`_HISTORICAL_SPECS` row — no `if key == "green_workshop"` (or similar) branch exists anywhere in the rendering, service, or registry layers. The repair used exclusively existing, already-registered hero/header/layout/card/footer/bottom_nav component keys (`hero.product_focus.v1`, `hero.typographic.v1`) — no new component, no new renderer branch |
| `capture_ready_template_previews.py` | Referenced only by this round's Section 2 static-preview refresh (an explicitly authorized, separate dev/build tool invocation against a dedicated port-8766 server) — `grep -rn "capture_ready_template_previews"` inside `qa_storefront_builder_r4.py`/`run.mjs` | **Not referenced** by the browser-certification harness itself; the campaign's own `qa_storefront_builder_r4.py` + `run.mjs` remain the sole certification authority |

## Conclusion

No second implementation of the browser harness, renderer, Ready-Template
registry, version-history authority, preset-apply authority, publish
authority, Theme owner, Cart implementation, ProductCard implementation,
Bottom-Navigation system, search backend, or tenant resolver was found. The
visual repair introduced zero Template-name-specific CSS/render branches and
used only pre-existing registered components. `capture_ready_template_previews.py`
was not used as certification authority. **Architecture/duplication audit:
CLEAN. 0/0.**
