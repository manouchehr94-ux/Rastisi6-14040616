# R4 browser regression — merged branch vs current `main` (41c2569)

Fixture: the project's own `manage.py qa_storefront_builder_r4 --phase3` (sections, hero slide + media, products, brands, collections, tenant negatives), against the sole migration-seeded `akhlaghi` Store in a fresh SQLite DB per tree (`harness/seed.py`, `harness/run.sh`). Both trees ran the identical command with identical runner (`harness/save_state_labels.patch` aligns the runner's save-state labels with the Design Studio's current labels; without it 01 also fails).

Result (20 scenario entries incl. phase3 gates, identical on both trees): **2 PASS** (`01-initial-r4`, `02-hero-basic-autosave`), **18 FAIL** — the same 18 on `main` and on the merged branch. Failures are timeouts on selectors the pre-Design-Studio runner expects (`[data-r4-inspector-close]` hidden, `#r4StructureAddSelect`, `[data-r4-resource-picker-open]`), i.e. `run.mjs` (last changed 2026-09-18) is stale against the Design Studio editor on `main` (landed 2026-09-26+). This is **not a passing gate**; it is evidence of no *differential* regression plus a tooling defect on `main`.

Code diff of the merge vs `main` inside R4/storefront areas is only: `render_service.py` (+1 line), `sections/cart_items.html`, `sections/product_main.html` (gift-wrap UI).

`main/` and `merged/` hold browser.log, per-scenario JSON, metrics, fixture and failure screenshots.
