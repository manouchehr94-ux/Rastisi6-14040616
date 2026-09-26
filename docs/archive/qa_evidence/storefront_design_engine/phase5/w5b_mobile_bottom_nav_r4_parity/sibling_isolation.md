# W5B — Sibling-State Isolation Evidence

Changing ONLY `mobile_nav_variant` through the R4 `footer.update` mutation
must not accidentally change any other Footer field, any other global
region, or any unrelated Store Appearance family. Proven by
`MobileNavSiblingIsolationTests` (`test_phase5_w5b_mobile_bottom_nav_r4_parity.py`):

| Assertion | Test | Result |
|---|---|---|
| `footer_variant` unchanged | `test_changing_only_mobile_nav_preserves_footer_variant` | PASS |
| `FOOTER_TOGGLE_FIELDS` (`show_copyright`, `show_social`, ...) unchanged | `test_changing_only_mobile_nav_preserves_footer_toggles_and_blocks` | PASS |
| `extra_blocks` unchanged | `test_changing_only_mobile_nav_preserves_footer_toggles_and_blocks` | PASS |
| Every OTHER typed Store Appearance family selection (header, hero,
  product_view, card, badge, theme, template, palette, footer, ...)
  unchanged | `test_changing_only_mobile_nav_preserves_unrelated_appearance_and_header` | PASS |
| `header_config` unchanged | `test_changing_only_mobile_nav_preserves_unrelated_appearance_and_header` | PASS |
| Typed `selections["bottom_nav"]` IS synchronized to the new selection | `test_typed_bottom_nav_selection_is_synchronized` | PASS |
| Typed `selections["footer"]` does NOT change merely because Bottom Nav changed | `test_typed_footer_selection_does_not_change_merely_because_bottom_nav_changed` | PASS |
| A foreign Store's Draft is never touched | `test_mutation_never_touches_a_foreign_stores_draft` (`MobileNavTenantIsolationTests`) | PASS |

## A note on test-fixture correctness (not a production defect)

Early iterations of these tests directly wrote `draft.footer_config[...]`
without also syncing the typed manifest (via
`appearance_authority_service.apply_footer_variant()`), which is *not* what
any real write path does (`_apply_footer_update` always keeps both in sync
on every save). That inconsistent fixture setup produced two misleading
failures — the typed `selections["footer"]`/`appearance_config` appeared to
"change" on the very first real mutation, because the fixture's own
`footer_variant="marketplace_dense"` had never actually been synced to the
typed manifest before that point. Fixed by syncing the fixture's starting
state the same way `_apply_footer_update` already does, before capturing the
"before" snapshot — not by weakening any assertion. See `code_review.md` and
the TDD RED/GREEN evidence for the full account.

## Independent mutation confirmed at the HTTP boundary

Every assertion above exercises the real `dashboard:storefront-builder-r4-mutation`
endpoint with a `footer.update` patch containing `mobile_nav_variant` alone —
never a direct service-layer call — so the isolation guarantee is proven at
the actual merchant-facing contract boundary, not just at a lower internal
layer.
