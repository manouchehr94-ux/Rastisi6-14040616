# مأموریت Kiro: افزودن شش Family جدید و رسیدن به ۱۱ Family

ریپازیتوری رسمی: `https://github.com/manouchehr94-ux/RastiSi4`

Branch فعلی: `claude/family-visual-fidelity-fix`

این مأموریت را از ابتدا تا انتها بدون پرسیدن سؤال اجرا کن. هر ابهام با `decision-lock.yaml` و ترتیب اعتبار `README_FA.md` حل می‌شود. فقط اگر مانع امنیتی/دسترسی واقعی وجود داشت، آن را با Command و Error کامل ثبت کن؛ در سایر موارد متوقف نشو.

## ابتدا این فایل‌ها را کامل بخوان

1. `README_FA.md`
2. `decision-lock.yaml`
3. همه فایل‌های `contracts/`
4. `RESPONSIVE_CONTRACT_FA.md`
5. `ACCEPTANCE_GATES_FA.md`
6. `SOURCE_AUDIT_FA.md`
7. `machine/reference-dna.json`
8. Screenshotهای `screenshots/`

## نتیجه غیرقابل تغییر

- پنج Family موجود را حفظ کن.
- شش Family `atlas_catalog`، `ava_fashion`، `toranj_gifting`، `sarv_stock`، `sepidar_handmade` و `zarrin_jewelry` را اضافه کن.
- Count نهایی Registry و UI دقیقاً ۱۱ باشد.
- نام‌های عمومی: اطلس، آوا، ترنج، سرو، سپیدار و زرین.
- نام سایت مرجع فقط در Documentation مجاز است و در Public UI، Seed، Fixture، CSS class تولیدی یا نام Component دیده نشود.

## مرحله 1 — Audit و Plan، بدون توقف

معماری موجود `apps/storefront_builder`، Registry، Models، Schemaهای Section، Renderer مشترک Preview/Public، Templateها، Staticها، URLها، تست‌ها و Migrationها را بررسی کن. سپس فایل `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` بساز. Plan باید مسیر دقیق فایل‌ها، Migration مورد نیاز یا عدم نیاز، ریسک Regression و ترتیب Batchها را بنویسد. بعد بلافاصله اجرای مرحله 2 را شروع کن؛ منتظر تأیید نشو.

## مرحله 2 — Registry و Data Contract

- شش Family را بدون تغییر Slugهای موجود ثبت کن.
- Default section tree هر Family را دقیقاً طبق `section-blueprints.yaml` بساز.
- همه Sectionها باید به Data bindingهای `dynamic-data-mapping.yaml` وصل باشند.
- هیچ Product/Banner/Price فرضی در Public render نگذار.
- اگر داده اختیاری وجود ندارد، Section را بدون Gap مخفی کن؛ در Preview فقط Editor hint نمایش بده.

## مرحله 3 — Component و Renderer مستقل

برای هر Family، Home، Header، Footer، Product card، Badgeها و Product page را مستقل بساز؛ فقط Primitiveهای واقعاً مشترک را Share کن. یک DOM مشترک با شش Theme رنگی ممنوع است. تفاوت‌ها باید در ساختار، ترتیب، Card anatomy، Navigation، Hero و Product page واقعی باشند.

## مرحله 4 — آیکون و Badge

- از Registry SVG خود پروژه استفاده کن؛ Icon font جدید اضافه نکن.
- اندازه، Stroke، کادر، رنگ و Hover هر Family را از `icon-manifest.yaml` بگیر.
- منطق و ظاهر تخفیف/جدید/ویژه/ناموجود را از `badge-matrix.yaml` پیاده کن.
- آیکون‌های Icon-only باید `aria-label` داشته باشند.

## مرحله 5 — تعاملات

تمام موارد `interactions.yaml` را Functional کن: Search، Menu، Story، Slider، Cart، Mini cart، Wishlist، Compare، Gallery، Zoom، Video، Share، Variant، Quantity، Tabs، FAQ و Size guide. هیچ دکمه نمایشیِ بدون عملکرد نگذار.

## مرحله 6 — Responsive

`RESPONSIVE_CONTRACT_FA.md` را در تمام Viewportهای اجباری اجرا کن. مشکل زوم iPhone با `font-size >= 16px` برای Inputها را به‌صورت تست Regression پوشش بده. Hoverها باید جایگزین Touch-safe داشته باشند.

## مرحله 7 — تست و Screenshot

همه Gateهای `ACCEPTANCE_GATES_FA.md` را اجرا کن. برای Home و Product هر شش Family در `1440×1000` و `390×844` Screenshot بگیر. Screenshotهای جدید را کنار Referenceها در گزارش نهایی لینک کن. پنج Family قدیمی نیز حداقل Smoke visual و Regression test داشته باشند.

## مرحله 8 — کیفیت و Git

- قبل از Commit: `git diff --check`، Django check، migration plan و Suiteهای مرتبط را اجرا کن.
- تغییرات unrelated را دست نزن.
- Media فروشگاه‌ها و Secretها را Commit نکن.
- Commitها کوچک و موضوعی باشند.
- فقط روی Branch فعلی Push کن؛ `main` را Merge نکن.
- GitHub مرجع رسمی است؛ پس از Push، HEAD محلی و Remote را مقایسه و Hash را گزارش کن.

## گزارش نهایی اجباری

فایل `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` شامل این موارد باشد:

- Count و Slug هر ۱۱ Family؛
- فایل‌های تغییرکرده به تفکیک Batch؛
- Data binding و Default sections هر Family؛
- وضعیت Home/Product/Desktop/Mobile؛
- آیکون‌ها، Badgeها و تعاملات؛
- Migrationها؛
- Command، Exit code و نتیجه هر Test؛
- مسیر Screenshotهای Desktop/Mobile؛
- مواردی که عمداً کپی نشده‌اند؛
- Commit hash و Remote hash؛
- اعلام صریح اینکه Merge انجام نشده است.

معیار پایان: فقط زمانی `READY_FOR_VISUAL_QA` اعلام کن که همه Gateها مدرک داشته باشند. در غیر این صورت وضعیت دقیق `BLOCKED_WITH_EVIDENCE` یا `IMPLEMENTATION_INCOMPLETE` بده؛ عبارت کلی «انجام شد» کافی نیست.

