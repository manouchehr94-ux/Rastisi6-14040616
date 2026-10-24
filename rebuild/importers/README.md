# importers

کد importer عمداً داخل Django app است (نه اسکریپت جدا) تا به مدل‌ها، تراکنش و `manage.py` دسترسی کامل داشته باشد:

- `apps/stores/services/demo_bundle/contract.py` — قرارداد bundle و دامنه‌ی مدل‌ها
- `…/exporter.py` · `…/validator.py` · `…/importer.py` · `…/integrity.py` · `…/accounts.py` · `…/targets.py` · `…/report.py`
- فرمان‌ها: `apps/stores/management/commands/{export_store_bundle,validate_demo_bundle,import_demo_bundle,verify_demo_integrity,provision_shop_settings,create_install_accounts,retire_seed_store}.py`

نگاشت دو فروشگاه: `../manifests/demo_stores.json`. توضیح کامل: `docs/rebuild/DATA_MAPPING.md`.
