# W4C Final Certification Campaign — Architecture/Duplication Audit

CAMPAIGN_HEAD: `1e4efad80fbfc998cfd05d79658955193e1799d5`

## Scope note

This campaign round (the rate-limit-aware sharded execution of the final
704-cell certification, Attempt 1 preserved as infrastructure-interrupted /
not certifiable, Attempt 2 certified clean) made **zero source code
changes**. `git status --short` before evidence materialization showed a
clean worktree at `CAMPAIGN_HEAD`; every file touched during this round is
new evidence under
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`. No new
duplicate authority could have been introduced by this round's own work.

The checks below re-confirm, on the actual current source tree, that the
architectural invariants established and audited in earlier W4B/W4C rounds
still hold.

## Checks performed (this round, against current source)

| Authority | Check | Result |
|---|---|---|
| Browser harness | `tools/` contains exactly two runner directories: `storefront_builder_qa` (R3) and `storefront_builder_r4_qa` (R4/W4C) | `storefront_builder_r4_qa/run.mjs` explicitly reuses R3's `playwright-core` dependency via `createRequire(new URL('../storefront_builder_qa/package.json', ...))` rather than vendoring a second copy — one browser-driving dependency, not two harnesses |
| Ready-Template registry | `grep -rn "def list_ready_templates"` | Exactly one definition: `apps/storefront_builder/layout_preset_registry.py:221` |
| Preset-apply authority | `apply_preset` / `apply_preset_with_checkpoint` | Unchanged, single definition in `apps/storefront_builder/services/preset_service.py` (read-only reference this round) |
| Publish authority | `layout_service.publish` | Unchanged, single definition in `apps/storefront_builder/services/layout_service.py` (read-only reference this round) |
| Theme owner | Theme cell mutation path | Unchanged; W4C harness calls the same `layout_service`/`preset_service` entry points as Base/Tier-1 cells, no parallel Theme-mutation path introduced |
| Cart implementation | `grep -rln "cart:item-remove"` across templates | Exactly one file: `apps/storefront_builder/templates/storefront_builder/sections/cart_items.html` |
| ProductCard implementation | Card rendering driven by the `card` appearance selection (e.g. `card.marketplace_price.v1`) resolved through the single shared appearance/rendering pipeline; no second card renderer found | Confirmed — no duplicate `product_card` template tree |
| Bottom Navigation system | Rendered via the single `bottom_nav` appearance selection resolved by the shared appearance rendering pipeline (`apps/storefront_builder/storefront_appearance/rendering.py`); no second bottom-nav system found | Confirmed |
| Search backend | No second `search_products`/search-backend implementation found outside the existing catalog search path | Confirmed |
| Tenant resolver | `grep` initially also matched `storefront_appearance/rendering.py`'s `resolve_store_appearance_render_state` — inspected directly: that function resolves a Store's **appearance/theme manifest**, not host/domain routing, and is unrelated to tenant resolution. The real (single) tenant/host resolver remains `apps/stores/resolution.py` (`domain_is_eligible_for_routing`, `_strip_port`, `_is_development_host`, etc.) | Confirmed — one tenant resolver, one appearance-manifest resolver, distinct concerns, no duplication |
| `capture_ready_template_previews.py` | `grep -rn "capture_ready_template_previews"` inside `qa_storefront_builder_r4.py` and `run.mjs` | **Not referenced.** The static preview-capture script was not used as browser-certification authority for this campaign — the campaign's own live browser harness (`qa_storefront_builder_r4.py` + `run.mjs`) is the sole certification authority |

## Conclusion

No second implementation of the browser harness, renderer, Ready-Template
registry, preset-apply authority, publish authority, Theme owner, Cart
implementation, ProductCard implementation, Bottom-Navigation system, search
backend, or tenant resolver was found. `capture_ready_template_previews.py`
was not used as certification authority. **Architecture/duplication audit:
CLEAN.**
