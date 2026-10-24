# INVENTORY — آنچه واقعاً در مخزن موجود است

> تاریخ بررسی: 2026-10-24 · مخزن: `manouchehr94-ux/Rastisi6-14040616` · همه‌ی اعداد از اجرای واقعی دستور روی checkout گرفته شده‌اند، نه از حافظه یا گزارش قبلی.

## ۱. وضعیت Git

| مورد | مقدار |
|---|---|
| شاخه‌ی مبنا | `main` = `origin/main` = `7d3115564569509f1da442fdc4aeacc9f855a81d` |
| شاخه‌ی کار این مأموریت | `claude/rastisi-complete-rebuild-20261024` (از `main` ساخته شد) |
| worktree | `/home/user/rastisi-complete-rebuild` (worktree واقعیِ جدا از `/home/user/Rastisi6-14040616`) |
| تاریخچه | ۲۶۴ کامیت، از 2026-09-04 تا 2026-10-22 |
| شاخه‌های دیگر | فقط `main` و شاخه‌ی نشست `claude/festive-wozniak-0bnu6o` (دست نخورد) |
| Git LFS | استفاده نشده (`git lfs ls-files` خالی) |
| فایل حذف‌شده‌ی دیتابیس/آرشیو در تاریخچه | **هیچ** (`git log --all --diff-filter=D` برای `*.sqlite3, *.db, *.zip, *.sql, *.dump` نتیجه‌ای ندارد) |
| remote | فقط `origin` (آدرس بالا)؛ `CLAUDE.md` از remote با نام `rastisi5` سخن می‌گوید که در این محیط وجود ندارد — push روی `origin` فقط برای همین شاخه و به‌صراحت خواسته‌ی کاربر انجام می‌شود |

### کامیت `7d31155…`
دستور کار آن را «نقطه‌ی مرجع ادغام Studio V5» توصیف کرده بود. **بررسی واقعی:** این کامیت دقیقاً HEAD فعلی `main` است (نه نسخه‌ی قدیمی‌تر)، پس «مقایسه با HEAD» تفاوتی ندارد. پیام و diff آن (۱۳ فایل، +437/−63) مربوط به **صفحه‌ی لندینگ عمومی** است (فروشگاه نمایشیِ قابل‌ویرایش در سایت rastisi.ir، برچسب «قالب‌های بیشتر»، صفحه‌ی `/design/`) و به Studio/Storefront Builder دست نمی‌زند. کدهای Studio R4 / ARCH-02 در کامیت‌های قبلی (مثلاً `676d609 sync(r4)`) هستند و همگی در `main` فعلی موجودند. بنابراین هیچ کدی از «نسخه‌ی قدیمی» جایگزین نشد.

## ۲. ساختار کد (از `manage.py check` تا مدل‌ها)

- Django 5.2، Python ≥ 3.10 (اجرا شده روی 3.13)، ۱۷ پوشه‌ی `apps/*`، **۱۴۵ مدل**، **۲۱۰ فایل migration**.
- `manage.py check` → `System check identified no issues`؛ `makemigrations --check --dry-run` → `No changes detected`.

| app | مدل | migration | فایل تست | قالب HTML | توضیح |
|---|---:|---:|---:|---:|---|
| `stores` | 6 | 20 | 35 | 0 | Store، StoreDomain، StoreMembership، مالکیت، یکپارچگی؛ تفکیک tenant بر اساس Host |
| `core` | 6 | 21 | 21 | 0 | **ShopSettings**، AuditLog، Import/ExportJob، middleware، rate-limit |
| `catalog` | 38 | 42 | 62 | 16 | محصول، دسته، برند، واریانت، انبار، کالکشن، قالب‌های صنفی |
| `content` | 13 | 25 | 15 | 2 | MediaAsset، Hero/Banner/Story، منو، فوتر، صفحات |
| `storefront_builder` | 7 | 21 | 187 | 180 | Studio/صفحه‌ساز R4: Layout/Version/Page/Section/Container/Cell؛ ۵۴ Ready Template؛ ۳۸ نوع Section |
| `portal` | 10 | 14 | 57 | 114 | سایت عمومی `rastisi.ir`، ورود/ثبت‌نام مالک، پنل مدیر پلتفرم، handoff |
| `dashboard` | 0 | 0 | 83 | 163 | پنل مدیریت فروشگاه (`/admin-portal/`) |
| `orders` | 18 | 19 | 32 | 4 | سفارش، پرداخت، مالیات، ارسال، مرجوعی |
| `cart` | 3 | 9 | 10 | 5 | سبد خرید |
| `customers` | 9 | 7 | 9 | 8 | مشتری، آدرس، بخش‌بندی |
| `billing` / `subscriptions` | 10 / 7 | 7 / 8 | 12 / 11 | 0 | اشتراک و صورتحساب SaaS |
| `sms` / `notifications` / `engagement` | 9 / 2 / 3 | 9 / 3 / 3 | 12 / 6 / 8 | 0/1/0 | پیامک، اعلان، کمپین |
| `blog` | 1 | 2 | 1 | 2 | ژورنال |

- مجموع: ۵۸۷ فایل HTML (۸ قالب ریشه + قالب‌های app)، حدود ۱۱٬۰۰۰ متد تست (`def test_`)، ۱۱٬۱۴۱ تست توسط runner کشف می‌شود.
- استاتیک: ۲۱۹ فایل ردیابی‌شده در `apps/*/static` (۲۲ فایل JS، ۳۳ فایل CSS، بقیه تصویر/فونت/vendor مثل CKEditor 5 در `apps/core/static/js/vendor`)؛ `static/` ریشه فقط `favicon.ico` دارد.
- مسیرهای host:
  - `rastisi.ir`, `www.rastisi.ir` → `shop_core.urls_platform` (سایت عمومی + `/login/` مرکزی + `/app/`)
  - `platformadmins.rastisi.ir` → `shop_core.urls_platform_admin` (فقط `is_staff and is_superuser`)
  - هر `StoreDomain` تأییدشده → `shop_core.urls` (فروشگاه + `/admin-portal/`)

## ۳. دارایی‌های داده‌ای که در Git هست

| مسیر | تعداد/اندازه | منشأ | وضعیت صحت (بررسی‌شده) |
|---|---|---|---|
| `apps/stores/demo_assets/rasti_mode_demo/products/FSH-001…050/01-03.webp` | ۱۵۰ فایل، 9.2 MB | عکس‌های QA ارائه‌شده‌ی کاربر، پردازش‌شده با `scripts/select_and_process_media.py` | **۱۵۰/۱۵۰ sha256 مطابق** `selected_product_media_manifest.json`، ۰ مفقود |
| `…/curated/` (banner 12، category 10، hero 8، brand 6، branding 2، …) | ۴۱ فایل، 3.8 MB | همان منشأ | **۴۰/۴۰ sha256 مطابق** `curated/SHA256SUMS.txt` |
| `…/raw_user_catalog/1-5/` | ۳۴۵ عکس خام، 8.5 MB | عکس‌های QA کاربر | فقط منشأ (provenance)؛ در زمان اجرا خوانده نمی‌شود؛ در ZIP نهایی پیش‌فرض حذف است |
| `apps/portal/static/portal/images/public/` | ۱۱ تصویر | سایت عمومی rastisi.ir | — |
| `apps/storefront_builder/static/ready_template_previews/fashion_promo_catalog/` | ۸ تصویر | پیش‌نمایش قالب | — |
| `docs/reference-kits`, `docs/references`, `docs/qa_evidence` | ۲٬۳۱۴ تصویر در `docs/`، کل `docs/` ≈ 242 MB | مرجع طراحی و شواهد QA | **داده‌ی فروشگاه نیستند**؛ از ZIP نهایی حذف می‌شوند |

### Seed/ابزار داده‌ای موجود در کد
`seed_ready_template_fashion_demo` (فروشگاه `rasti-mode-demo`: ۵۰ محصول، ۱۳ دسته، ۶ برند، ۲۰۶ واریانت، **۱۵۰ تصویر محصول**، ۶ کالکشن، منو/فوتر، قابل‌اعمال با `--ready-template <key>`)، `seed_rastisi_fashion_demo`, `seed_kianstock_qa_demo`, `apply_ready_template_exact`, `apply_golden_reference_storefront`.

## ۴. آنچه در Git **نیست** (جستجوی کامل انجام شد)

جستجوی کل درخت و کل تاریخچه برای `*.sqlite3|*.db|*.sql|*.dump|*.zip|*.tar*|*.7z|*.bak|fixtures/|demo_v5|demo_arch02|demo-v5|demo-arch02|rastisi-server-bundle` **هیچ** دیتابیس، dump، fixture، آرشیو رسانه یا فایلی مربوط به دو فروشگاه `demo-v5` / `demo-arch02` پیدا نکرد (تنها اشاره‌ها نام تست‌های ARCH-02 است که یک «مأموریت» کدنویسی بوده، نه فروشگاه). جزئیات و فهرست دقیق: [`MISSING_INPUTS.md`](MISSING_INPUTS.md).

## ۵. ابزارهای ریبیلد افزوده‌شده (این شاخه)

مسیرها: `apps/stores/services/demo_bundle/`، `apps/stores/management/commands/{export_store_bundle,validate_demo_bundle,import_demo_bundle,verify_demo_integrity,provision_shop_settings,create_install_accounts,retire_seed_store}.py`، `apps/core/management/commands/rastisi_healthcheck.py`، `rebuild/**`، `docs/rebuild/**` و تست‌ها `apps/stores/tests/test_demo_bundle.py`. فهرست کامل فایل‌ها در گزارش نهایی PR.
