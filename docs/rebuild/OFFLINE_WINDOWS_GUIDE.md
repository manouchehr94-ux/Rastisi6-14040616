# OFFLINE_WINDOWS_GUIDE — تبدیل دو SQLite مستقل + دو ZIP رسانه به یک bundle نهایی

> این مرحله **کاملاً آفلاین** است: به VPS، PostgreSQL، Redis، اینترنت (پس از نصب بسته‌های پایتون) و هیچ دیتابیس موجودی نیاز ندارد. فایل‌های ورودی فقط خوانده می‌شوند و هرگز تغییر نمی‌کنند.
> وضعیت: ابزار آماده و با داده‌ی تستیِ هم‌ساختار آزمایش شده؛ **داده‌ی واقعی شما هنوز اجرا نشده ⇒ `DATA BLOCKED`** تا خروجی واقعی را اجرا کنید.

## ۱. پیش‌نیاز
- Windows 10/11 + Python **3.10 تا 3.13** (`py -3 --version`). نصب از https://www.python.org/downloads/ با گزینه‌ی *Add python.exe to PATH*.
- کلون همین شاخه (`claude/rastisi-complete-rebuild-20261024`) — مسیر **کوتاه** بهتر است، مثلاً `C:\rb\rastisi` (نام‌های فارسیِ فایل‌های تصویر طولانی‌اند؛ ابزار از پیشوند `\\?\` استفاده می‌کند، ولی مسیر کوتاه امن‌تر است).
- فضای آزاد دیسک ≈ ۴× مجموع اندازه‌ی ورودی‌ها (snapshot دیتابیس‌ها، رسانه‌ی bundle، دیتابیس scratch برای بررسی کامل).
- چهار فایل (نام دلخواه است): `demo_v5.sqlite3`, `demo_v5_media.zip`, `demo_arch02.sqlite3`, `demo_arch02_media.zip`. **آن‌ها را در Git قرار ندهید** (`.gitignore` الگوهای `*.sqlite3` و `*_media.zip` را می‌بندد).

## ۲. دستور دقیق (PowerShell)

```powershell
cd C:\rb\rastisi

# الف) فقط بازرسی: فروشگاه‌ها، شناسه‌ها، ساختار ZIP و کلیدهای ناشناخته‌ی JSON — هیچ‌چیز نوشته نمی‌شود
.\rebuild\windows\build_demo_bundle.ps1 `
    -V5Sqlite      D:\in\demo_v5.sqlite3      -V5MediaZip      D:\in\demo_v5_media.zip `
    -Arch02Sqlite  D:\in\demo_arch02.sqlite3  -Arch02MediaZip  D:\in\demo_arch02_media.zip `
    -Out D:\out\rastisi-demo-bundle -InspectOnly

# ب) ساخت واقعی (با بررسی کامل)
.\rebuild\windows\build_demo_bundle.ps1 `
    -V5Sqlite      D:\in\demo_v5.sqlite3      -V5MediaZip      D:\in\demo_v5_media.zip `
    -Arch02Sqlite  D:\in\demo_arch02.sqlite3  -Arch02MediaZip  D:\in\demo_arch02_media.zip `
    -Out D:\out\rastisi-demo-bundle
```

معادل در Command Prompt (یک خط):
```bat
rebuild\windows\build_demo_bundle.bat --v5-sqlite D:\in\demo_v5.sqlite3 --v5-media-zip D:\in\demo_v5_media.zip --arch02-sqlite D:\in\demo_arch02.sqlite3 --arch02-media-zip D:\in\demo_arch02_media.zip --out D:\out\rastisi-demo-bundle
```
اجرای مستقیم پایتون (همه‌ی سیستم‌عامل‌ها): `py -3 rebuild\tools\build_bundle_offline.py <همان گزینه‌ها>`.

بار اول `.venv` در پوشه‌ی پروژه ساخته و `requirements.txt` نصب می‌شود. بدون اینترنت: روی ماشین دارای اینترنت `pip download -r requirements.txt -d D:\wheels` و سپس `-WheelDir D:\wheels`.

**خروجی نهایی:** `D:\out\rastisi-demo-bundle\` شامل `manifest.json`، `stores\demo_v5\`، `stores\demo_arch02\`، `media\` و `CONVERSION_REPORT.txt/.json`. این پوشه **فقط** وقتی ساخته می‌شود که همه‌ی اعتبارسنجی‌ها PASS باشد.
**کد خروج:** `0` موفق · `1` FAIL (گزارش علت را می‌گوید، هیچ bundleای ساخته نمی‌شود) · `2` BLOCKED (ورودی ناقص/مفقود).

## ۳. ابزار چه می‌کند (به ترتیب)
1. از هر SQLite با API پشتیبان‌گیری SQLite یک **snapshot** می‌گیرد (فایل اصلی فقط‌خواندنی است؛ `integrity_check` اجرا می‌شود). اگر نسخه‌ی کدِ سازنده‌ی دیتابیس قدیمی‌تر باشد، migrationهای جا‌افتاده روی **کپی** اجرا می‌شود؛ migrationِ ناشناس = توقف (مگر `--allow-unknown-migrations`).
2. فروشگاه دمو را پیدا می‌کند (تنها فروشگاهِ دارای محصول؛ `akhlaghi`ِ خالی نادیده گرفته می‌شود). اگر چند فروشگاه محصول دارد: `-V5Store` / `-Arch02Store`.
3. ردیف‌های محتوا را می‌خواند: ShopSettings، FooterSettings، دسته/برند/محصول/واریانت/تصویر، کالکشن، منو، MediaAsset، HeroSlide، Banner، StoryRail، صفحات، **همه‌ی نسخه‌های Studio (منتشرشده، پیش‌نویس، بایگانی)** با Page/Container/Cell/Section. کاربر/سفارش/مشتری/اسرار خوانده نمی‌شود.
4. **نگاشت شناسه:** چون هر دو دیتابیس از ۱ شروع می‌شوند، فروشگاه اول بدون تغییر می‌ماند و فروشگاه دوم با offset ثابت (`stride` = توان ۱۰ بزرگ‌تر از هر کلید، حداقل ۱٬۰۰۰٬۰۰۰) جابه‌جا می‌شود. با همان offset: کلید اصلی، همه‌ی ForeignKeyها، M2M، **شناسه‌های عددی داخل JSON** (`product_ids`, `category_ids`, `brand_ids`, `collection_ids`, `menu_id`, `media_asset_id`, `image_media_asset_id`, `campaign_media_asset_id`, `destination_id` با `destination_type`، `source_id` با `data_source`/`auto_rule`، `source.manual_ids`) و `combination_key` واریانت‌ها بازنویسی می‌شود. کلیدهای ارجاع رسانه با هر نام (هر `*asset_id(s)` و هر `*image/logo/banner/…_id(s)`، مثل `announcement_image_asset_id` در هدر) با همان offset بازنگاشت می‌شوند و در گزارش `remap.pattern_key` می‌آیند. هر کلید ناشناسِ دیگرِ شبیه شناسه (`*_id`/`*_ids`) = **توقف** نه رهاکردنِ بی‌صدا؛ با `-MapJsonKey KEY` (یک شناسه) یا `-MapJsonListKey KEY` (فهرست) تعریف یا با `-IgnoreJsonKey KEY` نادیده بگیرید.
5. **رسانه:** پوشه‌ی ریشه‌ی `MEDIA_ROOT` داخل هر ZIP خودکار پیدا می‌شود (با/بدون پوشه‌ی wrapper، `\` ویندوز، NFD مک، رمزگذاریِ قدیمی OEM، فایل‌های `Thumbs.db`/`__MACOSX` نادیده). فایل با مسیر یکسان و محتوای یکسان = یک نسخه‌ی مشترک؛ مسیر یکسان با محتوای **متفاوت** = فایلِ فروشگاه دوم با پسوند `--demo_arch02` تغییر نام می‌دهد و مقدار ستون تصویر بازنویسی می‌شود. هیچ فایلی حذف نمی‌شود (حتی بدون ارجاع، مگر `--drop-unreferenced-media`). ZIPِ ناامن (`..`، مسیر مطلق، symlink، رمزگذاری‌شده، بمب فشرده‌سازی) رد می‌شود.
6. bundle را در پوشه‌ی موقت می‌سازد و با validator کامل (هش رسانه، decode تصاویر، بسته‌بودن FK، شش نوع صفحه در نسخه‌ی منتشرشده، عدم ارجاع JSON شکسته‌ی **جدید**، نبودن اسرار، تفکیک کلیدها) می‌سنجد.
7. **بررسی کامل (پیش‌فرض):** یک دیتابیس scratch تازه، bundle را **دو بار** import می‌کند (بار دوم نباید چیزی تغییر دهد)، یکپارچگی + رندر HTTP هر دو فروشگاه را می‌سنجد، و **همه‌ی صفحات** (خانه، فهرست، جست‌وجو، کالکشن‌ها، سبد، صفحات محتوا، تک‌تک محصولات) را یک بار از دیتابیس اصلی و یک بار از نتیجه‌ی import رندر و از نظر متن، لینک، تصویر، CSS درون‌خطی (رنگ/فونت تم) و ساختار عناصر مقایسه می‌کند. فقط با برابری، bundle منتشر می‌شود. (`-SkipFullCheck` فقط برای عیب‌یابی.)

## ۴. بعد از موفقیت
- گزارش را بخوانید: `D:\out\rastisi-demo-bundle\CONVERSION_REPORT.txt`. `WARN`ها (مثل «۱۵۰ فایل بدون ارجاع» = نسخه‌ی originalِ آپلود) خطا نیستند.
- اختیاری، ZIP نهایی دارای داده: `py -3 rebuild\tools\build_release_zip.py --out D:\out\rastisi-release.zip --bundle D:\out\rastisi-demo-bundle` (bundle دوباره اعتبارسنجی می‌شود؛ ZIP فقط کد+داده است، بدون اسرار).
- انتقال به VPS (مرحله‌ی جدا و با مجوز شما): `docs/rebuild/INSTALL_GUIDE.md` بخش ۸.
- **هیچ‌یک از این فایل‌ها (SQLite، ZIP رسانه، bundle) را commit نکنید.** bundle شامل تصاویر/برندینگ فروشگاه است ولی اسرار ندارد؛ باز هم خصوصی بماند.

## ۵. اگر خطا داد
| پیام | معنی / اقدام |
|---|---|
| `remap.unmapped_json_key` | کلید `*_id(s)` ناشناس در JSON Studio؛ مسیرش چاپ می‌شود. اگر شناسه است `-MapJsonKey` وگرنه `-IgnoreJsonKey` و دوباره اجرا. اگر مطمئن نیستید گزارش را برای من بفرستید |
| `media.missing_at_export` (BLOCKED) | فایلی که دیتابیس به آن ارجاع می‌دهد در ZIP نیست؛ ZIP کامل‌تری بدهید یا `-V5MediaPrefix <پوشه‌ی MEDIA_ROOT داخل ZIP>` را دستی بدهید |
| `more than one store has products` | `-V5Store <slug>` |
| `applied migration(s) are unknown to this code base` | دیتابیس با نسخه‌ی دیگری از کد ساخته شده؛ هم‌نسخه‌ی کد را checkout کنید |
| `singleton.missing` (BLOCKED) | ShopSettings/FooterSettings در دیتابیس منبع نیست؛ ابزار آن را جعل نمی‌کند |
| `equivalence.differs` | رندر پس از import با اصل فرق دارد؛ فرق چاپ می‌شود و bundle ساخته **نمی‌شود** |
| `Persian/UnicodeEncodeError` در کنسول | `chcp 65001` یا PowerShell 7؛ ابزار خودش `PYTHONUTF8=1` می‌گذارد |

## ۶. تمرین بدون داده‌ی واقعی
`py -3 rebuild\tools\make_sample_sources.py C:\rb\sample` دو SQLite مستقل با PKهای یکسان از کاتالوگ مرجعِ مخزن می‌سازد (≈ ۳ دقیقه)؛ سپس همان دستور بالا را روی آن‌ها اجرا کنید. این **داده‌ی نمونه** است، نه دموی واقعی.
