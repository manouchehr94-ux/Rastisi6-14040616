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
