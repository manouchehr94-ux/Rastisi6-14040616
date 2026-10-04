# R4 browser regression — merged branch vs current `main` (41c2569)

Command (identical on both trees, fresh SQLite DB each, sole migration-seeded `akhlaghi` Store, `harness/seed.py` + `harness/run.sh`):

    manage.py qa_storefront_builder_r4 --store-slug akhlaghi --username r4owner --phase3 --report-dir <dir>

Fixture = the project's own `--phase3` fixture (sections, hero slide + media, products, brands, collections, tenant negatives, broken-image/task6/final-remediation families).

Runner: `tools/storefront_builder_r4_qa/run.mjs`, **ported to the Design Studio editor** (the committed runner pre-dated it and failed 18/20 identically on `main` and on the merged tree before the port — see report §20). Port = test-tool only: Studio save-state labels; Structure as panel mode; add-section / publish / discard / template-switch via the Studio dialogs; move/enable/lock via inspector actions; inline R4-native media manager; row layout disclosure; Studio conflict dialog; `?studio_notice=` replaceState counted with its reload; one narrowly-allowed ERR_ABORTED (Studio background status-refresh GET superseded by a reload, within 2s of a real navigation). No scenario assertion was removed or weakened; where the Studio replaced a control, the same contract is asserted on its replacement.

Result (20 scenario entries = 17 numbered + final/phase3 gates): **merged 20/20 PASS, main 20/20 PASS, command exit 0 on both.** `main/` and `merged/` hold browser.log, per-scenario JSON (`r4-browser-result.json`), metrics, fixture, db-restore-proof and screenshots.
