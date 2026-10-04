# Browser-level E2E for campaigns / occasions / gift wrap / notifications

Manual (not part of `manage.py test`) Playwright suites run against a **throw-away staging database**.
Never point them at a shared or production database (`reset.sh` drops `stg_e2e`).

Requirements: PostgreSQL reachable at `127.0.0.1:5544` (trust auth), `pip install playwright`,
Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.

```
bash tools/engagement_e2e/reset.sh            # recreate DB, migrate, seed, start runserver on :8765
export DATABASE_URL=postgres://postgres@127.0.0.1:5544/stg_e2e DJANGO_DEBUG=True DJANGO_SECRET_KEY=e2e-secret-key-not-for-prod
python tools/engagement_e2e/rule_builder_e2e.py   # 22 checks: nested AND/OR builder, save, edit, validation
python tools/engagement_e2e/workflow_e2e.py       # 27 checks: PDP→cart→checkout→account, admin order/invoice, templates, birthday
```
Re-run `reset.sh` between runs (the workflow suite creates a customer).

## Cross-viewport / accessibility suite (H9)

```
cd tools/engagement_e2e && npm i axe-core && cd ../..        # node_modules is git-ignored
E2E_PG_BASE=postgres://user:pw@localhost:5432 bash tools/engagement_e2e/reset.sh   # E2E_PG_BASE overrides the default server
python tools/engagement_e2e/accessibility_e2e.py              # 67 checks: 3 viewports x (keyboard-only, names/roles, tab order, RTL/Persian, touch, axe WCAG 2.1 A/AA)
```
Engines: Chromium always. Firefox/WebKit run automatically when installed (`PLAYWRIGHT_BROWSERS_PATH`) and are reported as
`NOT RUN` otherwise — they are **not** claimed as passed. Report: `/tmp/e2e/a11y_report.json`.
Templates are cached by `runserver --noreload`: re-run `reset.sh` after editing a template.

## Note: simplified campaign/occasion form

`/admin-portal/campaigns/add/` is now the 3-step simple wizard (`cw-*` classes). The nested AND/OR rule builder
lives inside **«مخاطب خاص می‌خواهم» → «شرط‌های ترکیبی… (پیشرفته)»** and must be enabled with the
`#cw-use-custom` checkbox. `rule_builder_e2e.py`, `workflow_e2e.py` and `accessibility_e2e.py` were written for the
old single-page form and have **not** been updated/run against the wizard (they need the Postgres staging DB above).
Browser coverage of the wizard is in `apps/dashboard/tests/test_campaign_wizard_browser.py` (part of `manage.py test`).
