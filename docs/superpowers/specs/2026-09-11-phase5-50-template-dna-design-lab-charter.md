# RASTISI PHASE 5 — 50 TEMPLATE DNA & DESIGN LAB CHARTER

**سند مستقل الزامات سیستم ۵۰ قالب، ترکیب طراحی، Random Mix و Theme Overlay**

- Date: 2026-09-11
- Source reviewed: `RastiSi_50_Storefront_Design_Lab_TABBED_THEMES(1).html`
- Status: APPROVED AS REFERENCE / NOT PRODUCTION CODE
- Relationship: Companion document to the main Phase 5 Design Expansion Charter

---

## ۱. تصمیم اجرایی

این فایل از نظر محصول و طراحی، مرجع مناسبی برای بخش «۵۰ قالب + Design Lab + Template DNA» در Phase 5 است؛ اما نباید به‌عنوان Production Code مستقیماً وارد RastiSi شود.

ارزش اصلی فایل در ایده‌ها، دامنه انتخاب‌ها، نحوه ترکیب اجزا، Random Mix، قفل‌کردن اجزا، مقایسه با DNA اصلی، تم‌های مناسبتی مستقل و امکان بازگشت کنترل‌شده به طرح پایه است.

هدف این سند آن است که همین ایده‌ها را به یک قرارداد محصولی و معماری قابل‌استفاده برای Claude Code تبدیل کند؛ بدون اینکه HTML خام، localStorage، ساختار JSON نمایشی یا وابستگی‌های این Prototype به مرجع Production تبدیل شوند.

> **نکته کلیدی:** حکم نهایی: KEEP THE PRODUCT MODEL — DO NOT COPY THE PROTOTYPE IMPLEMENTATION

## ۲. Audit Snapshot فایل مرجع

| موضوع | آنچه در Prototype وجود دارد | نتیجه بررسی |
| --- | --- | --- |
| قالب‌های پایه | ۵۰ Template | تأیید شد؛ ۵۰ شناسه یکتا |
| امضای ساختاری قالب‌ها | Header + Hero + Card + Grid + Categories + Footer + Mobile Nav | ۵۰ امضای ساختاری یکتا؛ Duplicate کامل پیدا نشد |
| Header | ۱۲ مدل | قوی؛ قابل نگهداری به‌عنوان Reference |
| Hero | ۲۰ مدل | بسیار غنی؛ از مینیمال تا ویدئو/موزاییک/فروش عمده |
| Category Layout | ۱۰ مدل | کامل از نظر هدف Design Factory |
| Product Card | ۱۶ مدل | بالاتر از حداقل ۱۰؛ مناسب Curation |
| Product Layout | ۹ مدل | یک مدل کمتر از حداقل ۱۰ Family target |
| Section Recipe | ۱۰ مدل | مناسب برای تفاوت واقعی Template DNA |
| Footer | ۸ مدل | برای Phase 5 باید به حداقل ۱۰ مدل قوی برسد |
| Mobile Navigation | ۷ مدل | برای Phase 5 باید به حداقل ۱۰ مدل قوی برسد |
| Promotion | ۱۰ مدل | مناسب |
| Palette | ۵۰ انتخاب | هر Template پالت خودش را دارد |
| Typography | ۸ سیستم | مناسب؛ باید با فونت‌های مجاز Production تطبیق یابد |
| Density | ۵ سطح | مناسب |
| Content Width | ۵ سطح | مناسب |
| Radius | ۶ سطح | مناسب |
| Theme / Campaign | ۲۲ تم فعال + حالت بدون تم | پوشش ایرانی، اسلامی و عمومی خوب |
| Theme Intensity | ۳ سطح | ظریف / متعادل / کامل |
| Device Preview | 1440 / 820 / 390 | برای Production: 1440 / 768 / 390 معیار رسمی QA باشد |

## ۳. چیزی که باید از این Prototype به Phase 5 منتقل شود

- ۵۰ Template DNA واقعی و از نظر ساختار متمایز، نه ۵۰ Skin یا Recolor.
- انتخاب Template پایه به‌عنوان نقطه شروع فروشنده.
- امکان تغییر کنترل‌شده Header، Hero، دسته‌بندی، Product Card، Product Layout، ترتیب Sectionها، Footer و Mobile Navigation.
- کنترل‌های ظاهری ساده: Palette، Typography، Density، Content Width و Radius.
- Theme Overlay مستقل از DNA اصلی و قابل حذف بدون تخریب قالب.
- سه شدت Theme: ظریف، متعادل و کامل.
- Random Mix برای کشف ترکیب‌های تازه، همراه با Lock برای ثابت نگه‌داشتن انتخاب‌های موردعلاقه.
- Randomize One برای تصادفی‌کردن فقط یک خانواده، نه همه طراحی.
- بازگشت به DNA اصلی بدون حذف اجباری Theme Overlay.
- دکمه جداگانه برای حذف Theme و بازگشت به نمای پایه.
- مقایسه Current Design با Base Template برای تشخیص تغییرات.
- Preview واقعی در Desktop / Tablet / Mobile.
- استفاده از داده ثابت در Design QA تا تفاوت طراحی از تفاوت محتوا جدا بماند.

## ۴. تعریف رسمی Template DNA در RastiSi

Template DNA باید یک Composition از قابلیت‌های موجود باشد، نه یک اپلیکیشن یا Renderer مستقل. هر Template مشخص می‌کند چه Variantهایی و چه Design Tokenهایی در کنار هم استفاده شوند و ترتیب بخش‌ها چگونه باشد.

در Production، Template DNA فقط باید انتخاب‌هایی را بیان کند که Owner canonical آن‌ها در معماری موجود RastiSi مشخص است. هر فیلدی که Owner واقعی آن در Repository نامشخص است، ابتدا باید توسط Claude Code Audit شود؛ هیچ Model، Table، Registry یا API جدیدی نباید از روی Prototype حدس زده شود.

| لایه DNA | نمونه انتخاب | معنای Production |
| --- | --- | --- |
| Structure | Header / Hero / Categories / Card / Grid / Footer / Mobile Nav | Variantهای canonical موجود یا توسعه‌یافته |
| Composition | Section Recipe | ترتیب و حضور Sectionهای مجاز |
| Appearance | Palette / Type / Density / Width / Radius | Design tokens / appearance selections |
| Campaign | Theme + Intensity | Overlay برگشت‌پذیر روی DNA پایه |
| Discovery | Random + Locks | کمک برای انتخاب، نه Source of Truth مستقل |

## ۵. معماری غیرقابل‌مذاکره

- R4 Editor → Canonical Services → One Draft Lifecycle / History → One Shared Renderer → Preview / Publish / Public Storefront.
- One concept = one canonical owner.
- هیچ Second Renderer برای ۵۰ Template ساخته نشود.
- هیچ Persistence جدا برای Design Lab یا Random Mix ساخته نشود.
- localStorage فایل Prototype نباید Merchant Source of Truth شود.
- JSON خروجی Prototype قرارداد دیتابیس یا API محسوب نمی‌شود.
- هیچ Ready Template authority موازی ساخته نشود.
- هر تغییر Merchant-facing باید از همان Mutation / Validation / Tenant / Draft semantics موجود عبور کند.
- Preview و Public Storefront باید از همان Shared Renderer استفاده کنند تا Drift ایجاد نشود.
- فایل HTML مرجع فقط برای فهم رفتار و تنوع بصری است.

> **نکته کلیدی:** اگر برای اجرای این قابلیت نیاز به Owner دوم برای یک مفهوم پیدا شد، اجرای آن متوقف و معماری دوباره بررسی شود.

## ۶. هدف Production برای ۵۰ قالب

پنجاه قالب باید در نگاه و تجربه فروشنده و خریدار واقعاً متفاوت باشند. تفاوت باید حتی با یک Palette و Font یکسان نیز قابل تشخیص باشد.

- هر Template حداقل یک امضای ساختاری یکتا داشته باشد.
- تفاوت فقط در رنگ، Radius یا Font قابل قبول نیست.
- تفاوت در Hierarchy، Layout Geometry، Navigation Model، Density، Merchandising Priority، Responsive Transformation و Section Recipe ایجاد شود.
- قالب‌ها Store Typeهای مختلف را پوشش دهند: Luxury، Marketplace، Fashion، Beauty، Home، Electronics، Local Store، Editorial، Cultural، High-density، Minimal، Campaign-heavy و غیره.
- هر Template باید در Mobile هویت خودش را حفظ کند؛ Mobile فقط Desktop کوچک‌شده نباشد.
- همه Templateها باید از داده واقعی Catalog/Brand/Collection/Product در معماری موجود استفاده کنند.

> **نکته کلیدی:** Acceptance Gate: ۵۰ Template فقط وقتی پذیرفته می‌شوند که QA بتواند تفاوت ساختاری آن‌ها را بدون اتکا به رنگ تشخیص دهد.

## ۷. Component Set مخصوص Template DNA

| خانواده | Prototype | هدف پیشنهادی Phase 5 |
| --- | --- | --- |
| Header | ۱۲ | ۱۲ گزینه قوی یا بیشتر؛ پس از Curation |
| Hero | ۲۰ | حداقل ۱۰؛ ۲۰ گزینه موجود می‌تواند پس از QA حفظ شود |
| Category Layout | ۱۰ | حداقل ۱۰ |
| Product Card | ۱۶ | حداقل ۱۰؛ بهترین گزینه‌های ۱۶تایی حفظ شوند |
| Product / Merchandising Layout | ۹ | حداقل ۱۰؛ یک الگوی materially different اضافه شود |
| Section Recipe | ۱۰ | حداقل ۱۰ |
| Footer | ۸ | حداقل ۱۰؛ دو الگوی materially different اضافه شود |
| Mobile Bottom / Navigation | ۷ | حداقل ۱۰؛ سه الگوی materially different اضافه شود |
| Promotion / Campaign block | ۱۰ | حداقل ۱۰ |
| Appearance controls | Palette 50 / Type 8 / Density 5 / Width 5 / Radius 6 | پس از Audit با سیستم appearance canonical تطبیق داده شود |

## ۸. Theme Overlay System

Theme نباید Template را Fork کند. تعریف رسمی باید همان اصل زیر باشد: Base Template DNA + Optional Reversible Theme Overlay = Seasonal Storefront.

Prototype از این جهت ایده خوبی دارد که Theme و Reset DNA را از هم جدا کرده است. در Phase 5 نیز این جداسازی حفظ شود.

| گروه | پوشش Prototype | الزام |
| --- | --- | --- |
| ایرانی | نوروز، یلدا، چهارشنبه‌سوری، سیزده‌بدر، مهرگان، تیرگان، سده، سپندارمذگان | قابل انتخاب و برگشت‌پذیر |
| اسلامی | رمضان، عید فطر، عید قربان، غدیر، نیمه‌شعبان، مبعث، میلاد پیامبر، محرم/عاشورا | قابل انتخاب با لحن مناسب هر مناسبت |
| عمومی/فصلی | ولنتاین، Black Friday، بازگشت به مدرسه، تابستان، زمستان، سالگرد فروشگاه | قابل انتخاب |
| Intensity | ظریف / متعادل / کامل | سه سطح رسمی یا معادل canonical |

> **نکته کلیدی:** برای مناسبت‌های سوگ مانند محرم/عاشورا، UI نباید پیام فروش تهاجمی، Countdown هیجانی یا تخفیف‌نمایی نامتناسب تحمیل کند.

## ۹. Random Mix و Lock System

Random Mix یکی از بهترین ایده‌های این Prototype است و ارزش تبدیل‌شدن به قابلیت Merchant-facing را دارد، به شرطی که کاملاً کنترل‌شده و سازگار با معماری R4 باشد.

- فروشنده بتواند «همه اجزای باز» را Random کند.
- فروشنده بتواند فقط یک خانواده، مانند Header یا Product Card، را Random کند.
- هر انتخاب قابل Lock باشد تا Random Mix آن را تغییر ندهد.
- Random Mix نباید Cartesian random خام باشد؛ فقط ترکیب‌های compatible و QA-approved تولید کند.
- نتیجه Random باید قابل مشاهده، قابل Undo و قابل بازگشت به DNA اصلی باشد.
- اگر R4 autosave دارد، semantics موجود آن حفظ شود؛ اگر Preview-before-apply دارد، Random نیز همان الگو را دنبال کند.
- هر Mutation پایدار باید از Draft/History canonical عبور کند.
- Random Mix نباید Template جدید یا Source of Truth جدید ایجاد کند؛ فقط Selectionهای موجود را تغییر می‌دهد.

> **نکته کلیدی:** پیشنهاد UX: «ترکیب تصادفی» + Lockهای ساده + «بازگشت به DNA اصلی» سه کنترل اصلی باشند؛ پیچیدگی فنی از Merchant پنهان بماند.

## ۱۰. تجربه ساده فروشنده در R4

| تب | چیزی که فروشنده می‌بیند |
| --- | --- |
| قالب | انتخاب یکی از ۵۰ Template با Preview تصویری |
| ساختار | Header، Hero، دسته‌ها، Card، Layout، Section Order، Footer، Mobile Nav |
| ظاهر | رنگ، تایپوگرافی، تراکم، عرض، گردی |
| مناسبت‌ها | Theme، شدت Theme، Promotion |
| کشف ترکیب | Random Mix، Randomize One، Lock |
| بازگشت | Reset DNA و Remove Theme به‌صورت دو عمل مستقل |

> **نکته کلیدی:** JSON، Registry ID، Model name و جزئیات فنی نباید در UI عادی Merchant نمایش داده شوند.

## ۱۱. Design Lab در برابر Merchant Editor

Prototype فعلی Design Lab و Merchant customization را تا حدی در یک سطح نمایش می‌دهد. در Production باید نقش‌ها روشن باشند.

| قابلیت | Merchant R4 | Internal Design/QA Lab |
| --- | --- | --- |
| انتخاب Template | بله | بله |
| Preview دستگاه | بله | بله |
| تغییر Variantهای مجاز | بله | بله |
| Theme / Random Mix / Locks | بله | بله |
| Compare با Base | پیشنهادی | الزامی برای QA |
| نمایش JSON خام | خیر | در صورت نیاز برای Debug/Review |
| ذخیره در localStorage | خیر به‌عنوان authority | فقط برای ابزار QA موقت مجاز |
| Persistence واقعی | Draft/History canonical | نباید authority دوم ایجاد کند |

## ۱۲. تفاوت Prototype با Production

| مورد Prototype | چرا مستقیم وارد Production نشود | الزام جایگزین |
| --- | --- | --- |
| یک HTML حدود 252KB با CSS/JS داخلی | Maintainability و ownership ضعیف برای repo واقعی | تقسیم طبق boundaries موجود RastiSi |
| Google Fonts external runtime | وابستگی خارجی و کنترل محدود | Font strategy موجود پروژه / assets مجاز |
| localStorage برای Saved Mix | Source of Truth مرورگری و خارج از Draft history | Canonical persistence یا صرفاً scratch داخلی |
| Global LAB state در JS | مناسب Demo، نه معماری production | State/mutation semantics موجود R4 |
| Preview tablet = 820px | با معیار Master Brief یکی نیست | QA رسمی 768x1024؛ 820 می‌تواند تست اضافی باشد |
| prefers-reduced-motion تعریف نشده | Motion accessibility ناقص | الزام reduced motion |
| ARIA state محدود | Interactive controls نیازمند audit | WCAG 2.2 AA + keyboard/focus semantics |
| JSON export نمایشی | ممکن است اشتباه به persistence contract تبدیل شود | فقط debug/reference؛ schema production از repo استخراج شود |

## ۱۳. QA و Acceptance Gates

- ۵۰/۵۰ Template موجود و هرکدام دارای DNA مشخص.
- تست uniqueness روی امضای ساختاری Templateها.
- تست Material Difference برای جلوگیری از Recolor-only templates.
- Browser QA در 1440x900، 768x1024 و 390x844.
- RTL primary و LTR compatibility در جاهایی که لازم است.
- عدم horizontal overflow ناخواسته.
- Keyboard navigation و focus-visible برای کنترل‌های Editor و Storefront.
- prefers-reduced-motion برای Motionها و transitionهای ضروری.
- Theme Clear باید دقیقاً DNA زیرین را حفظ کند.
- Reset DNA باید انتخاب‌های ساختاری/ظاهری پایه را بازگرداند و Theme مستقل را فقط طبق action جداگانه تغییر دهد.
- Lock test: Random Mix هیچ کلید Lock‌شده‌ای را تغییر ندهد.
- Compatibility test: Random Mix ترکیب نامعتبر نسازد.
- Preview و Public Storefront از Shared Renderer یکسان نتیجه دهند.
- Tenant isolation، stale-write protection و Draft history مطابق معماری موجود.
- Evidence برای هر Task و Browser QA قبل از بستن Phase 5.

## ۱۴. ترتیب پیشنهادی اجرای این زیرسیستم در Phase 5

| مرحله | خروجی |
| --- | --- |
| 1. Repository Audit | شناسایی Ownerهای واقعی appearance/template/rendering/mutations |
| 2. Canonical Contract Map | تطبیق قابلیت‌های این سند با قراردادهای موجود؛ بدون حدس |
| 3. Variant Expansion | تکمیل Variantهای انتخاب‌شده و رفع کمبود Footer/Mobile/Product Layout |
| 4. 50 DNA Definitions | تعریف ۵۰ ترکیب materially distinct |
| 5. R4 Controls | UI ساده تب‌دار برای انتخاب و تغییر |
| 6. Theme Overlay | تم‌های reversible + intensity |
| 7. Random Mix & Locks | با compatibility rules و history |
| 8. Preview / Compare | device preview و baseline compare طبق معماری مجاز |
| 9. Browser QA | Desktop/Tablet/Mobile + RTL + accessibility |
| 10. Product Owner Review | بازبینی بصری ۵۰ Template و قابلیت‌های ترکیب |
| 11. Freeze | Evidence کامل و بستن زیرسیستم |

## ۱۵. Definition of Done این زیرسیستم

- ۵۰ Template production-ready و materially distinct در RastiSi وجود دارد.
- هر ۵۰ Template از یک Shared Renderer و canonical architecture استفاده می‌کنند.
- فروشنده می‌تواند Template پایه را در R4 انتخاب کند.
- فروشنده می‌تواند Variantهای مجاز را با UI ساده تغییر دهد.
- حداقل مجموعه Componentهای موردنیاز این سند و Master Brief پس از Curation در سیستم موجود است.
- Random Mix، Randomize One و Lock بدون ایجاد Source of Truth دوم کار می‌کنند.
- Reset to DNA نتیجه قابل پیش‌بینی و تست‌شده دارد.
- Themeها reversible هستند و حذف Theme ساختار Template را خراب نمی‌کند.
- مناسبت‌های ایرانی، اسلامی و عمومی با لحن مناسب پوشش داده شده‌اند.
- Desktop/Tablet/Mobile و RTL QA سبز است.
- Accessibility و reduced-motion QA سبز است.
- Draft/History/Tenant/Stale-write tests سبز هستند.
- هیچ Renderer، persistence، registry یا template authority موازی ایجاد نشده است.
- Product Owner خروجی بصری را تأیید کرده است.
- QA evidence در repo ثبت شده و هیچ Blocker شناخته‌شده‌ای باقی نمانده است.

> **نکته کلیدی:** وقتی همه موارد بالا سبز باشند، بخش «50 Template DNA & Design Lab» از Phase 5 قابل CLOSED اعلام‌کردن است.

## ۱۶. خارج از Scope و ممنوع

- Copy/Paste کردن HTML Prototype به Production.
- ساخت ۵۰ اپ یا ۵۰ Renderer مستقل.
- ساخت persistence جدا برای Random Mix یا Saved Mix.
- قرار دادن localStorage به‌عنوان Merchant authority.
- تبدیل JSON Prototype به schema canonical بدون Architecture Decision.
- افزودن dependencyهای frontend صرفاً چون Prototype از آن‌ها استفاده کرده است.
- اجبار به حفظ دقیق نام‌ها یا IDهای h1/x1/c-flat و مشابه آن‌ها.
- ساخت Templateهایی که فقط Palette/Font متفاوت دارند.
- اجازه Random Mix برای تولید ترکیب‌های ناسازگار یا شکسته.
- اعلام COMPLETE فقط بر اساس وجود ۵۰ نام Template بدون Browser QA و evidence.

## ۱۷. بسته پیشنهادی برای شروع Claude Code

- RASTISI_PHASE5_DESIGN_EXPANSION_CHARTER — سند اصلی محدوده Phase 5.
- این سند: RASTISI_PHASE5_50_TEMPLATE_DNA_DESIGN_LAB_CHARTER — قرارداد زیرسیستم ۵۰ قالب و Design Lab.
- فایل HTML مرجع فقط به‌عنوان Visual/Behavioral Reference و با برچسب DO NOT COPY AS PRODUCTION CODE.
- Master AI Design Generation Brief برای دامنه تنوع 67 Family و اصول Reference Library.
- Checkpoint رسمی و clean Phase 4 که در زمان شروع Phase 5 مشخص خواهد شد.

> **نکته کلیدی:** Claude Code باید ابتدا Repository را Audit کند و Implementation Plan مبتنی بر Ownerهای واقعی بنویسد؛ سپس با TDD و Evidence Task-by-Task جلو برود.
