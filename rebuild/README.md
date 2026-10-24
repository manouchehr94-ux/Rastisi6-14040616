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
| `tools/build_bundle_offline.py` | راه‌انداز یک‌دستوری آفلاین `build_demo_bundle` (venv + اجرا) |
| `tools/make_sample_sources.py` | ساخت دو SQLite مستقل **نمونه** با PKهای یکسان برای تمرین |
| `windows/` | `build_demo_bundle.ps1` / `.bat` — اجرای آفلاین روی Windows |

## جریان کار
```
[لپ‌تاپ Windows، آفلاین]  demo_v5.sqlite3 + demo_v5_media.zip  +  demo_arch02.sqlite3 + demo_arch02_media.zip
                         build_demo_bundle(.ps1)  ─►  bundle/ (نگاشت شناسه + اعتبارسنجی کامل)  [docs/rebuild/OFFLINE_WINDOWS_GUIDE.md]
--- یا، اگر هر دو فروشگاه در یک دیتابیس‌اند ---
[ماشین با داده‌ی اصلی]  export_store_bundle  ─►  bundle/ (خارج از Git)
[محیط ساخت]             validate_demo_bundle ─►  PASS / FAIL(1) / BLOCKED(2)
                         build_release_zip.py --bundle bundle/  ─►  rastisi-release.zip + .sha256
[VPS]                    provision_host → deploy_app → import_demo_stores → create_install_accounts → smoke_test
```

## فرمان‌ها (همه از `manage.py`)
| فرمان | کار |
|---|---|
| `build_demo_bundle` | **دو SQLite مستقل + دو ZIP رسانه → یک bundle معتبر** (نگاشت PK/FK/JSON، ادغام رسانه، بررسی کامل scratch) |
| `render_store_signatures` | (داخلی) امضای رندر صفحات برای مقایسه‌ی منبع با import |
| `export_store_bundle` | صادرکردن محتوای یک/چند فروشگاه (بدون کاربر/سفارش/اسرار) |
| `validate_demo_bundle` | اعتبارسنجی بدون دسترسی به DB؛ کد خروج 0/1/2 |
| `import_demo_bundle` | واردسازی idempotent دو فروشگاه (`--dry-run`, `--prune`, `--allow-blocked CODE`) |
| `verify_demo_integrity [--http]` | ShopSettings، فایل‌ها، جداسازی tenant، صفحات Studio، رندر HTTP |
| `provision_shop_settings` | ساخت ردیف‌های ShopSettings/FooterSettings مفقود (علت ریشه‌ای خطای ۵۰۰) |
| `create_install_accounts` | دو حساب نصب، رمز تعاملی |
| `retire_seed_store` | حذف Store خالی `akhlaghi` از migration |
| `rastisi_healthcheck` | DB، migration، cache، مسیرهای static/media |

مستندات: `docs/rebuild/` (INVENTORY, MISSING_INPUTS, DATA_MAPPING, VALIDATION_REPORT, INSTALL_GUIDE, SERVER_CLEANUP_PLAN, SECURITY_NOTES).
