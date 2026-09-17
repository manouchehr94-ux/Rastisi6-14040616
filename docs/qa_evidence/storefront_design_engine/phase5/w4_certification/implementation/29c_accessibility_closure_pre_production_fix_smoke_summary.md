# W4C Accessibility Closure Round — Phase A.5: pre-production-fix smoke

Per Section 2 of the directive: after Phase A GREEN but BEFORE touching
production templates, exactly ONE fresh bounded smoke
(`--only editorial_jewelry`, new empty campaign root) to PROVE the new
`w4cAccessibilityChecksPass` gate is real against the current,
unrepaired production markup.

## Command

```
/usr/bin/python3 manage.py qa_storefront_builder_r4 \
  --store-slug rasti-mode-demo --username w4c_qa_owner \
  --w4c-all50 --only editorial_jewelry \
  --report-dir /tmp/w4c_a11y_closure_smoke --settings=shop_core.settings
```

Fresh empty `/tmp/w4c_a11y_closure_smoke` campaign root. Ran at branch
HEAD `a09673839000b4f1b6500925da0dfc4462391ed8` (the Phase A GREEN
commit, `a0967383`).

## Result — exactly as predicted, no source changes made

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- selected_keys=editorial_jewelry,
cells_recorded_this_run=13, cumulative_total_cells_recorded=13/704,
cumulative_missing=691, cumulative_fail_count=6, cumulative_blocked_count=0
Local database restored — pre=d008ecf54d4ad8e73c0aa44a443d1ceeb87f958a0d5c4097b7d831dea1b6efad
  post=d008ecf54d4ad8e73c0aa44a443d1ceeb87f958a0d5c4097b7d831dea1b6efad match=True
```

Full command output: `29a_accessibility_closure_pre_production_fix_smoke_output.txt`.
Full matrix: `29b_accessibility_closure_pre_production_fix_smoke_matrix.json`.

Per-cell results (recorded honestly, not hardcoded/predicted before the run):

- **Home** (desktop/tablet/mobile): all `result: PASS`,
  `accessibility_checks: {"mobile_nav_opener": "n/a"}`.
- **Listing** (desktop/tablet/mobile): all `result: FAIL`,
  `accessibility_checks: {"search_input": "PASS", "sort_control": "FAIL",
  "category_filter": "FAIL", "product_card": "PASS", "quick_view": "PASS"}`,
  `reason` ends `accessibility_ok=false`. Every other sub-check
  (cards=12, linkResolves=true) is genuinely fine — the cell fails
  **solely** because of the two real, pre-existing production
  accessibility gaps (Finding A from Repair Round 2), which the harness
  now correctly refuses to hide behind an overall PASS.
- **PDP** (desktop/tablet/mobile): all `result: FAIL`,
  `accessibility_checks: {"variant_control": "FAIL", "quantity_control":
  "PASS", "add_to_cart": "PASS"}`, `reason` ends `accessibility_ok=false`.
  Every other sub-check is genuinely fine (real variant transition
  attempted+changed, real Add-to-Cart attempted+changed, real
  navigation resolved, tabs/satc/bottomNav all ok) — the cell fails
  **solely** because of the real, pre-existing production swatch
  keyboard-focus gap (Finding B from Repair Round 2).
- **Cart** (desktop/tablet/mobile): all `result: PASS`,
  `accessibility_checks: {"quantity_control": "PASS", "remove_control":
  "PASS", "checkout": "PASS"}`.
- **Theme** (Tier 1, nowruz/balanced/desktop): `result: PASS`,
  `cleanup_verified: true` (Theme correctly untouched by the new gate,
  per the directive's explicit exclusion).
- `cumulative_fail_count: 6` = 3 Listing viewports + 3 PDP viewports,
  exactly matching the two genuine unrepaired production findings —
  not hardcoded, the actual recorded count.
- SQLITE RESTORE: PASS (`pre=<sha256> post=<sha256> match=True`).

## Conclusion

The gate is proven real, not cosmetic: it now genuinely flips Listing
and PDP from PASS to FAIL specifically because of the two unrepaired
production accessibility defects, while leaving Home/Cart/Theme
(which have no outstanding accessibility FAIL in their own checks)
at PASS. This is the required proof before Phase B (production
template repair) may begin.

No production template was modified in this step. No source file was
modified in this step (evidence-only). Not the 704-cell campaign — a
single bounded 13-cell smoke against one Ready Template key, as
required.
