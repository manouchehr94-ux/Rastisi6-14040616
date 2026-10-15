# گزارش نهایی تحویل — یکپارچه‌سازی دو خط توسعه (RastiSi) — ۱۴ اکتبر ۲۰۲۶

> **خلاصهٔ صادقانه.** بستهٔ بازیابی این‌بار در دسترس بود، باز و راستی‌آزمایی شد (SHA-256 همهٔ فایل‌ها درست) و دو خط توسعه (خطِ بازیابی‌شده تا `317216a` + پچ‌های ویندوز، و خطِ ۱۴ کامیتِ من) در یک شاخهٔ ایزوله **ادغام** شدند — بدونِ اعمالِ کورکورانهٔ پچِ تجمعی روی HEAD.
> نتیجهٔ آزمون‌های درخت یکپارچه: **هیچ شکستِ جدیدِ ناشی از ادغام باقی نمانده است**؛ شکست‌های باقی‌مانده همگی از قبل (روی `af4adb7d` یا روی خطِ بازیابی‌شدهٔ تنها) وجود داشته‌اند (بخش ۶).
> **دربارهٔ لپ‌تاپ ویندوز:** هیچ دسترسی/دست‌کاری‌ای روی آن یا پایگاه‌دادهٔ آن انجام نشد و ادعای «ترمیم/آزمونِ دیتابیسِ ویندوز» نمی‌شود. فقط روشِ امن و برگشت‌پذیر ارائه شده است (`WINDOWS_APPLY_PROCEDURE_FA.md`).
> هیچ Push / PR / Merge به remote / Deploy انجام نشد.

## ۱) مرحلهٔ ۱ و ۲ — حفظ کار و راستی‌آزمایی بسته
- پیش از هر تغییر، ۱۴ کامیتِ قبلی + همهٔ خروجی‌ها در یک ZIP ساخته، بازبینی (`unzip -t` و `sha256sum -c`) و به‌عنوان فایل ضمیمه تحویل شد: `RastiSi_Delivery1_SecuredWork_af4adb7_to_1b99c344.zip` (SHA-256: `bb85d7274470474f452432a6b90d55d4dc2d278cfea6f63b3115d199d7d9200b`).
- بستهٔ بازیابی: ۱۲ فایل، همهٔ `SHA256SUMS` درست (OK). README خوانده شد. شامل ۵ پچ + راهنماهای QA + گزارش حادثه + دو تصویر.
- نکتهٔ فنی: پچ‌های ۰۲ تا ۰۵ دارای پایان‌خطِ CRLF (ویندوز) بودند و مستقیماً روی فایل‌های LF اعمال نمی‌شدند؛ پس از تبدیلِ CRLF→LF (بدونِ هیچ تغییرِ محتوایی) هر چهار پچ بی‌خطا اعمال شد. پچ ۰۱ (تجمعی تا `317216a`) مستقیم و تمیز اعمال شد. کامیت `317216a` خودش در بسته نیست؛ پچ ۰۱ جایگزینِ آن است.

## ۲) مرحلهٔ ۳ — روشِ ادغام (شاخهٔ `integration/final-merge`)
1. شاخهٔ `integration/recovery-317216a` از `af4adb7` + اعمالِ پچ‌های ۰۱..۰۵ (هر کدام یک کامیتِ جدا، بدونِ دست‌کاریِ محتوا).
2. `git merge` سه‌طرفهٔ شاخهٔ ۱۴ کامیتی ← خطِ بازیابی‌شده. فقط دو تعارضِ متنی:
   - `apps/catalog/views.py`: خطِ بازیابی‌شده **صفحهٔ اصلیِ قدیمیِ هاردکد را حذف کرده** (`catalog/home.html` و `home_best_products` دیگر نیستند؛ فقط موتور واحد). نسخهٔ خطِ بازیابی‌شده حفظ شد؛ قاعدهٔ «ناموجود در صفحهٔ اصلی نیاید» در لایهٔ دادهٔ موتور (`section_data_service`/`availability_service`) من هست و برقرار ماند.
   - `storefront_builder.css`: هر دو مجموعه‌قاعده نگه داشته شد.
3. تعارض‌های معنایی (بدونِ تعارضِ متنی) که با آزمون/مرورگر پیدا و رفع شد:
   | مورد | علت | اقدام |
   |---|---|---|
   | پرچمِ `r4_editor_enabled` | خطِ بازیابی‌شده آن را حذف کرد (`storefront_builder.0021`) | فیکسچرهای آزمون‌های جدیدِ من اصلاح شد |
   | **دو پیاده‌سازیِ حالتِ خالی** | خطِ بازیابی‌شده برای `brand_carousel` و `blog_posts` شاخهٔ داخلیِ `.sfb-content-empty` داشت؛ قراردادِ مشترکِ من (`section_empty_state_service`) آن‌ها را قبل از رسیدن به قالب جایگزین می‌کند ⇒ شاخه‌های داخلی کدِ مرده | شاخه‌های مرده حذف شد؛ **یک** پیاده‌سازی ماند (متنِ مالک «فروشگاه شما هنوز برندی تعریف نکرده است.» همان است). `.sfb-content-empty` فقط برایِ صفحهٔ مجله (صفحه، نه بخش) می‌ماند |
   | قراردادِ پس‌زمینهٔ بخش (آزمونِ مرورگرِ Inspector واقعی) | بدنهٔ حالتِ خالیِ من پس‌زمینهٔ مات داشت و پس‌زمینهٔ بخش را می‌پوشاند (`HIDDEN BY INNER SURFACE`) | بدنهٔ حالتِ خالی شفاف + نشانگر `data-sfb-section-surface="ink"`؛ آزمونِ مرورگر پس از رفع پاس شد |
   | `test_r4_mutation_security_coverage` (آزمونِ خطِ بازیابی‌شده) | `appearance.template.apply` اکنون (طبقِ قراردادِ مالک) بدونِ تأیید ۴۰۰ می‌دهد | فرمانِ آزمون `confirm_replace`/`allow_locked` گرفت (اعتبارِ آزمون حفظ شد) |
   | `test_blog_posts_respects_item_limit` (آزمونِ قدیمی) | مقالاتِ فیکسچر `published_at` نداشتند؛ قاعدهٔ نشرِ خطِ بازیابی‌شده آن‌ها را پنهان می‌کند | فیکسچر `published_at` گرفت (این آزمون روی خطِ بازیابی‌شدهٔ تنها هم می‌شکست) |
4. بررسی سازگاریِ مهاجرت‌ها: برگِ هر اپ یکی است؛ `makemigrations --check` ⇒ «No changes detected»؛ مهاجرتِ خطِ بازیابی‌شده (`storefront_builder.0021_remove_r4_editor_enabled`، `blog.0002_blogpost_store`) و مهاجرت‌های من (`catalog.0041`، `catalog.0042`، `core.0021`) در اپ‌های متفاوتند و تداخل ندارند. اجرا روی **کپیِ** پایگاه‌دادهٔ scratch (که پیش‌تر ساخته شده بود): `migrate` فقط `blog.0002` و `storefront_builder.0021` را اعمال کرد و موفق بود.
5. عدمِ تکرار: جست‌وجوی تکرار انجام شد (حالتِ خالی، صفحهٔ اصلی، مسیر Studio) — موارد بالا تنها تکرارها بودند.

## ۳) آنچه اکنون در درخت یکپارچه برقرار است (و کجا راستی‌آزمایی شد)
| الزام | وضعیت | شاهد |
|---|---|---|
| جایگزینیِ دقیقِ قالب آماده (تأیید، قفل، snapshot بازیابی‌پذیر) | ✅ | `test_exact_template_replace` + Studio واقعی: POST اول ۴۰۰ ← دیالوگ ← تأیید ← ۲۰۰؛ بخشِ دست‌ساز حذف، ۲۱ بخش، نسخهٔ ARCHIVED ساخته شد |
| **قالب ۵۱ نسخهٔ ۲ = دقیقاً ۲۱ بخش، بدون ارث/تکرار** | ✅ | `Template51V2CompositionTests` (۲۱ اسلاتِ متمایز؛ A→B→A→B؛ انتخابِ مجددِ همان قالب = no-op؛ **ترمیمِ حالتِ انباشتهٔ ≥۴۵ بخش به ۲۱ بدونِ باقی‌مانده**) + مرورگر: صفحهٔ اصلیِ منتشرشده ۲۱ `.rsec` |
| دموی مشترکِ پوشاک + قالب ۵۱ | ✅ (خطِ بازیابی‌شده) | `test_template51_shared_demo_completion`، `test_template51_completion_browser` (پاس) |
| پالت / رنگِ سراسری / provenance | ✅ | `test_palette_engine_contract` + تست جدید: رنگِ سفارشیِ مرچنت از جایگزینیِ دقیق جان به‌در می‌برد |
| مجلهٔ store-scoped + `blog.0002` + ۴ مقاله + `/journal/` | ✅ (خطِ بازیابی‌شده) | `apps.blog.tests` (جداسازیِ فروشگاه‌ها، پیش‌نویس/آینده ۴۰۴، idempotency seed)؛ مرورگر: `/journal/` در سه عرض ۲۰۰ و بدون overflow |
| خبرنامه (رضایتِ صریح، تفکیکِ فروشگاه، rate-limit)، فوتر | ✅ (خطِ بازیابی‌شده) | مرورگر: بدون تیکِ رضایت ثبت نمی‌شود؛ با تیک پیامِ موفقیت؛ لینکِ نقشه فقط چون آدرسِ **موجود** در تنظیماتِ همان فروشگاه بود |
| تایمرِ پایدار + قیمتِ سمتِ سرور | ✅ | مرورگر روی درخت یکپارچه: یک deadline، باقی‌مانده ۲۱۵۳۶←۲۱۵۳۰←۲۱۵۲۴←۲۱۵۱۷ ثانیه (۳ رفرش + دستگاهِ دوم) |
| ترتیبِ موجودی (خانه حذف، فهرست ناموجود آخر) | ✅ | مرورگر: ۰ کارتِ ناموجود در خانه؛ فهرست ۱۲ کارت، هیچ موجودی بعد از ناموجود نیست |
| «استعلام قیمت» | ✅ | مرورگر: PDP بدونِ دکمهٔ خریدِ کالا و بدونِ قیمت در کد و بدونِ `offers`؛ کلیک ⇒ `/pages/about-us/` |
| Container/Cell و ردیفِ دوستونه | ✅ | `TwoColumnRowTests` |
| فهرست: فاصله و دکمه‌های فیلتر | ✅ | مرورگر: `applyResetOverlap=false` در هر سه عرض |
| پیش‌نمایش/Reset ایمن و ترمیم | ✅ | `test_template_refusal_http_contract`، `test_ready_template_repair_commands` |

## ۴) پاسخ به پرسشِ شما دربارهٔ «کارت‌های خالی/تصاویر خالی» در اسکرین‌شات
**علت: نبودِ فایل‌های رسانه در محیط scratch — نه خطای رندر یا اتصالِ داده.** شواهد:
- پایگاه‌دادهٔ scratch ۲۲۰ ارجاعِ تصویرِ محصول دارد و **هر ۲۲۰ فایل روی دیسک وجود ندارد** (پوشهٔ `media/` تقریباً خالی است). مرورگر: ۴۳ درخواستِ تصویر، همه ۴۰۴؛ در همان صفحه همهٔ ۵۸ کارت `<img>`، نام و قیمتِ درست دارند (اتصالِ داده سالم است).
- **گروهِ کنترل (فقط تشخیصی):** برای همان ارجاعاتِ موجود در DB، فایل‌های تک‌رنگِ تشخیصی در یک MEDIA_ROOT موقتِ بیرون از مخزن ساخته و سرور با آن اجرا شد: ۴۹ درخواستِ تصویر همه ۲۰۰، ۱۵۶ تصویر و **صفر تصویرِ شکسته**، ۲۱ بخش، صفر حالتِ خالی (`DIAGNOSTIC_home_1440_with_valid_media_refs.png`). این فایل‌ها محصول/تصویرِ جایگزین نیستند، به DB نوشته نشدند و در تحویل نیستند؛ فقط ثابت می‌کنند اتصالِ داده/رندر درست است.
- یک مورد دیگر در اسکرین‌شات‌های اولیه: بخشِ «برندها» حالتِ خالی نشان می‌داد چون ۶ برندِ scratch در جلسهٔ قبل برای نمایشِ حالتِ خالی **غیرفعال** شده بودند؛ برای گروهِ کنترل دوباره فعال شدند (۶ برندِ واقعیِ DB با لوگو).
- **آنچه همچنان لازم است:** رسانهٔ واقعیِ دمو فقط روی لپ‌تاپ شماست (ممیزیِ شما: ۳۱۰ ارجاع، ۰ گم‌شده). فیدلیتیِ تصویریِ نهایی فقط روی همان قابل تأیید است: بعد از اعمال، `python manage.py audit_rasti_mode_demo_media` را اجرا و اسکرین‌شاتِ لپ‌تاپ را با اسکرین‌شاتِ تشخیصیِ این گزارش مقایسه کنید.

## ۵) تأییدِ قالب ۵۱ نسخهٔ ۲ (۲۱ بخش)
- ریسیپی: `stationery_spectrum`، نسخهٔ `2`، صفحهٔ home با ۲۱ ورودی؛ ترتیب: `product_section, hero_banner, category_grid, trust_features, multi_banner, product_section, amazing_offers, product_section×13, brand_carousel, blog_posts`.
- روی DB scratch با مسیرِ واقعی (`r4_mutation_service.switch_template`, `confirm_replace=True`): بخش‌های home از ۴ به **۲۱** (= ریسیپی) رسید؛ انتشار ⇒ صفحهٔ عمومی ۲۱ `.rsec`؛ در Studio نیز با افزودنِ یک بخشِ دست‌ساز و تعویض، بخشِ دست‌ساز حذف و تعدادِ نهایی ۲۱ شد (۶ نسخهٔ ARCHIVED برای بازیابی).
- آزمون: همهٔ اسلات‌ها با پیشوندِ `stationery_spectrum:v2:home:` و بدونِ تکرار؛ سناریوی «انباشتِ ۲۴ بخشِ اضافهٔ v1» به ۲۱ برمی‌گردد.

## ۶) نتایجِ آزمون (درختِ یکپارچه)
اجرا: Python 3.13، SQLite، چهار گروهِ سریالِ هم‌زمان. مرجعِ مقایسه: (الف) `af4adb7d` دست‌نخورده، (ب) خطِ بازیابی‌شدهٔ تنها (`68d247d0`).

| گروه | آزمون | شکست/خطا | طبقه‌بندی |
|---|---|---|---|
| storefront_builder a–m | ۸۱۴ | ۱۱ | همه از قبل: `dense_marketplace_beraito_v2` / `editorial_jewelry_saremi_v2` (روی `af4adb7d` هم و روی خطِ بازیابی‌شدهٔ تنها هم همین ۱۱) ⇒ ۰ جدید |
| storefront_builder n–z | ۳٬۰۰۵ | ۱۱ | ۹ از قبل (Warm Boutique/Shokolati) + ۲ آزمونِ ایستای CSS قدیمیِ Phase28/28C که روی **خطِ بازیابی‌شدهٔ تنها** هم می‌شکنند (بلوکِ CSS «V3 Free Layout» را پچ ۰۱ همراه Studio قدیمی حذف کرده؛ آزمونِ کهنه‌شده) ⇒ ۰ ناشی از ادغام |
| catalog + dashboard + blog + content + stores (درخت نهایی) | ۳٬۸۴۲ | ۴ | هر ۴ (`apps.stores`: `test_D_official_a8_catalog…`، `test_a8_ready_template_registry…`، `test_refresh_applies_curated…`، `test_second_run_is_content_idempotent`) در فهرستِ شکست‌های `af4adb7d` هستند ⇒ ۰ جدید |
| portal/stores/orders/core/content/sms/billing/… (گروه ۴) | ۴٬۱۲۴ | ۱۴ | زیرمجموعهٔ دقیقِ ۱۵ شکستِ `af4adb7d` (یکی — آزمونِ کنتراستِ CSS — اکنون پاس) ⇒ ۰ جدید |
| مرورگرِ opt-in (`SFB_BROWSER_TESTS=1`): template51 completion/palette/background-inspector | ۱۸ | ۱ → رفع | شکستِ واقعیِ ادغام (حالتِ خالی پس‌زمینهٔ بخش را می‌پوشاند) پیدا و رفع شد؛ بازاجرا پاس |
| آزمون‌های جدید/ادغام‌شده (exact replace، ۲۱-اسلات، مرجوعیت‌های HTTP، دستورهای ترمیم، حالتِ خالی، تایمر، موجودی، استعلام، فهرست) | ۹۵+ | ۰ | پاس |

شکست‌های از پیش موجود را **نه حذف و نه تضعیف** کردم؛ فهرست‌های نام‌دار در `qa_evidence_integrated/test_classification/`. ریشهٔ ماژول‌های از قبل شکسته: نبودنِ `asyncore` در Python 3.13 (`test_email_transport`)، رقابتِ ContentType در `setUpClass` آزمونِ زنده، قراردادهای قدیمیِ ساختاری/CSS قالب‌ها.

### ۶-ب) توضیحِ تکمیلی
- گروهِ catalog/dashboard/blog روی درخت پیش از اصلاحِ نهایی (۲٬۶۷۸ آزمون) کاملاً OK بود؛ پس از اصلاحاتِ نهایی (CSS/قالبِ حالتِ خالی + دو آزمونِ هم‌ترازشده) همراه با content و stores دوباره اجرا شد (جدولِ بالا).
- گروه ۴ روی درختِ یک کامیت قبل از اصلاحِ CSS اجرا شد؛ اصلاحِ نهایی فقط `_empty_state_body.html`، CSS حالتِ خالی و دو فایلِ آزمونِ storefront_builder است و گروه‌های storefront/content/stores پس از آن دوباره اجرا شدند. (درخت نهاییِ دقیقاً HEAD فهرست‌شده در بخش ۸ است؛ پس از آن فقط یک آزمونِ افزوده شد که جداگانه پاس شد.)

## ۷) محدودیت‌ها و موانعِ باقی‌مانده (دقیق)
1. **رسانهٔ واقعی دمو** فقط روی لپ‌تاپ شماست؛ ارزیابیِ فیدلیتیِ تصویریِ نهایی و «اسکرین‌شاتِ بدونِ کارتِ خالی» فقط آنجا ممکن است (این محیط ندارد).
2. **اینماد/آدرس/نقشهٔ واقعی:** هیچ مقدارِ ساختگی ساخته نشد. نشانِ اینماد فقط با کد/لینکِ رسمیِ همان فروشگاه؛ لینکِ نقشه فقط وقتی آدرس در `FooterSettings.address` باشد (نقشهٔ جاسازی‌شده ساخته نشده). خبرنامه با **دو پرچم** کنترل می‌شود (`FooterSettings.show_newsletter` و `footer_config.show_newsletter`) و نصب، آن‌ها را تغییر نمی‌دهد.
3. **خبرنامه:** ثبتِ ایمیل با رضایت هست؛ ارسالِ کمپین، لغوِ عضویتِ یک‌کلیکی و تحویلِ ایمیل ساخته نشده (ادعا نمی‌شود).
4. **استعلام قیمت:** فقط ناوبری به «درباره ما»؛ ثبت/اعلانِ درخواست = تصمیمِ بعدیِ شما.
5. **نساخته‌ها:** دکمهٔ «شروع کمپین» در Studio؛ ستونِ انتخابِ گروهیِ جدولِ محصولات برای استعلام قیمت (سرویس و فرم‌ها هست).
6. **مقالاتِ قدیمیِ سراسری** (`store=NULL`) طبقِ طراحیِ خطِ بازیابی‌شده برای سازگاری در همهٔ فروشگاه‌ها دیده می‌شوند؛ مقالاتِ جدیدِ دمو فقط در فروشگاهِ خودشان.
7. **دو آزمونِ ایستای CSS قدیمیِ Phase28** روی خطِ بازیابی‌شده می‌شکنند؛ آزمونِ کهنه‌شده‌اند، حذف/تضعیف نشدند؛ تصمیمِ بازنویسی/بازنشستگیِ آن‌ها با شماست.
8. **پایگاه‌دادهٔ ویندوز** آزموده/ترمیم نشد؛ تنها روشِ امن در سند `WINDOWS_APPLY_PROCEDURE_FA.md`. وضعیتِ DB ویندوز (Draft با ۵۰ بخش + ۱ بخشِ قفلِ قدیمی) نباید با SQL دستی اصلاح شود؛ مسیرِ مجاز: دستورهای `diagnose_ready_template_composition` و `apply_ready_template_exact` (پیش‌فرض: فقط گزارش).

## ۸) کامیت‌ها و فایل‌ها
**الف) خطِ بازیابی‌شده (بستهٔ شما؛ هر پچ یک کامیت، محتوا بدونِ تغییر):**

1. `9c89dd9d2c75e0fe99893662a0240d0ecf306376` — Recovery bundle patch 01: 01_rastisi_template51_complete_af4adb7_to_317216a.patch
2. `e07dcac71483ec0fa4b8efcad117a5b4752208bc` — Recovery bundle patch 02: 02_RastiSi_Demo_Completion_Phase1_20261013.patch
3. `fd514c7bed5e70764b0445c3dd0e942fdeee90a4` — Recovery bundle patch 03: 03_RastiSi_Demo_Phase2_Store_Scoped_Journal_20261013.patch
4. `810013f38e5280dbb3af3a52485e205983271dc5` — Recovery bundle patch 04: 04_RastiSi_Journal_Test_Domain_Fix_20261013.patch
5. `68d247d0f745dc67c4502cc341873041b1b361f8` — Recovery bundle patch 05: 05_RastiSi_Newsletter_Manual_Text_Fix_20261013.patch

**ب) خطِ ۱۴ کامیتیِ تحویلِ اول (پایه `af4adb7d`):**

1. `62a7d2354b069d9e38ca50425d8dd494c83c18ce` — Explicit Ready Template selection installs the exact recipe, recoverably
2. `d5ddccf21c2f86045973bc883748f42f35ed4bf6` — Fix listing dead space and the overlapping Apply / Reset filter buttons
3. `e0d207db95f89816e364cd900c3377524c5a5419` — Commerce integrity, template-owned empty states and price inquiry
4. `262750d4539817fac1faa95c0f1f67ba9735d2d6` — Lossless pre-replacement snapshot and a gated repair path for accumulated Drafts
5. `3cc40227735a8d7bd15f419415ddc6bf7d7a09c8` — Refuse a locked reset before checkpointing; HTTP-level refusal contract tests
6. `962e4bc99d197253ee7ba018be091e017fa8f4e7` — Studio: show the locked-section count in Persian digits
7. `e79ad44275328b23d6387bcadc830396ee6781c5` — Product card "out of stock" follows the availability contract
8. `74781bac4537a528683c7e21084e3d2601349b0b` — Reproduce the owner's literal incident chain (stationery_spectrum 26 slots + locked slot 14 -> kamand_artisan)
9. `64c9ccf66efab47e9023e00e4cdd553ac0f2dd32` — Price-inquiry sync: recompute only on inquiry-relevant changes; cascade-delete safe
10. `c0aa9685e83d5608ee3285574f379c14d51bca3e` — Empty states keep each section's own shell; old hide-contract tests rewritten
11. `a0c0e6ca2029e4bc4e0323db882b123d55ea9775` — Align fixtures and old-contract tests with the new availability/empty-state/preview rules
12. `c00a67b07b8a663da1ea39d0a6da86d26dccc315` — First-run fixture: the first product is in stock so it can appear on the home rails
13. `714928b69ce196b4b4e7cef688e4385b0d93f47e` — Availability: VARIABLE products without any variant rows fall back to their own stock
14. `1b99c3445619bae9d3d0dceea55e1d7932340bb2` — Add recovery delivery docs: Persian report, issue checklist, Windows procedure, QA evidence and scripts

**ج) کامیت‌های یکپارچه‌سازی (روی شاخهٔ `integration/final-merge`):**

1. `ef27524c7aab3617431c1bdb1f4f5bb837e6174f` — Integrate the recovered engine line (317216a + Windows patches) with the exact-replace / commerce line
2. `f5e84b21a6aa21ac5e278bd8aca2a0e9b1e05268` — Tests: drop removed r4_editor_enabled flag from new fixtures
3. `83fb8bf233a7b636763dd2eeb99f6fd7481bc52b` — One empty-state implementation (drop the recovered inline duplicates); Template 51 v2 21-slot exact-install tests
4. `16154384f400f3bf1a58793108a4390d5cb75447` — Empty state paints no opaque surface (section background contract); align two recovered-line tests with exact replace / publication rules
5. `a731b3c06349c306b0f5b271e3b23756fa06187b` — Test: a merchant's global colour override survives an exact template replacement

کامیتِ نهاییِ «فقط مستندات و شواهد» = `HEAD` (SHA کامل در `MANIFEST.txt`؛ این گزارش درونِ همان کامیت است، پس SHAاش نمی‌تواند در همین متن باشد).

## ۹) فایل‌های تحویل
در `deliverables_20261014/` (خارج از Git) و ZIPِ ضمیمه: سری‌پچِ کامل از `af4adb7`، پچِ واحدِ کامل `af4adb7..HEAD`، **پچِ دلتا برای QA ویندوز** (`68d247d0..HEAD`؛ روی درختی که پچ‌های ۰۱..۰۵ را دارد)، `SHA256SUMS.txt`، `MANIFEST.txt`، فهرستِ مهاجرت‌ها، گزارش، چک‌لیست، روشِ ویندوز، شواهدِ مرورگر.