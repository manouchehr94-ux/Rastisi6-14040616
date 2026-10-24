# rebuild/ — نصب تازه و ریبیلد RastiSi (فقط ابزار و مستند؛ بدون داده‌ی محرمانه)

این پوشه همراه با `docs/rebuild/` و فرمان‌های `manage.py` در `apps/stores` و `apps/core`، «بسته‌ی نصب تمیز» را می‌سازد.

| پوشه | محتوا |
|---|---|
| `manifests/demo_stores.json` | تعریف دقیق دو فروشگاه هدف (`demo_v5`, `demo_arch02`)، host و انتظارات گزارش‌شده‌ی استقرار قبلی |
| `importers/` | اشاره‌گر به کد importer (کد اصلی در `apps/stores/services/demo_bundle/` است تا از `manage.py` در دسترس باشد) |
| `checks/` | `test_cleanup_guards.sh`، `run_all_checks.sh` (مجموعه‌ی بررسی‌های آفلاین) |
| `deployment/` | `rastisi.env.example`، `gunicorn.conf.py`، `systemd/`، `nginx/`، `scripts/` (provision, deploy, backup, restore, healthcheck, smoke, import, cleanup)، `requirements-production.txt` |
| `examples/` | ساختار نمونه‌ی bundle |
| `tools/build_release_zip.py` | ساخت ZIP نهایی (با/بدون bundle) |

## جریان کار
```
[ماشین با داده‌ی اصلی]  export_store_bundle  ─►  bundle/ (خارج از Git)
[محیط ساخت]             validate_demo_bundle ─►  PASS / FAIL(1) / BLOCKED(2)
                         build_release_zip.py --bundle bundle/  ─►  rastisi-release.zip + .sha256
[VPS]                    provision_host → deploy_app → import_demo_stores → create_install_accounts → smoke_test
```

## فرمان‌ها (همه از `manage.py`)
| فرمان | کار |
|---|---|
| `export_store_bundle` | صادرکردن محتوای یک/چند فروشگاه (بدون کاربر/سفارش/اسرار) |
| `validate_demo_bundle` | اعتبارسنجی بدون دسترسی به DB؛ کد خروج 0/1/2 |
| `import_demo_bundle` | واردسازی idempotent دو فروشگاه (`--dry-run`, `--prune`, `--allow-blocked CODE`) |
| `verify_demo_integrity [--http]` | ShopSettings، فایل‌ها، جداسازی tenant، صفحات Studio، رندر HTTP |
| `provision_shop_settings` | ساخت ردیف‌های ShopSettings/FooterSettings مفقود (علت ریشه‌ای خطای ۵۰۰) |
| `create_install_accounts` | دو حساب نصب، رمز تعاملی |
| `retire_seed_store` | حذف Store خالی `akhlaghi` از migration |
| `rastisi_healthcheck` | DB، migration، cache، مسیرهای static/media |

مستندات: `docs/rebuild/` (INVENTORY, MISSING_INPUTS, DATA_MAPPING, VALIDATION_REPORT, INSTALL_GUIDE, SERVER_CLEANUP_PLAN, SECURITY_NOTES).
