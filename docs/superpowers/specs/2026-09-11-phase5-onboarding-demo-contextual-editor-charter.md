# RASTISI PHASE 5 — ONBOARDING DEMO & CONTEXTUAL STOREFRONT EDITOR CHARTER

**سند رسمی تجربه انتخاب قالب، فروشگاه دمو، پیش‌نمایش با داده واقعی و ویرایش مستقیم هر بخش**

- Date: 2026-09-11
- Source architecture reviewed: `2026-09-01-storefront-design-engine-50-templates-design(4).md`
- Status: APPROVED PRODUCT REQUIREMENTS / PHASE 5 COMPANION CHARTER
- Production rule: REUSE CANONICAL R4 OWNERS — NO PARALLEL RENDERER / DRAFT / PERSISTENCE

---

## ۱. حکم و هدف سند

این سند سومین Charter مکمل Phase 5 است و تجربه کامل Merchant از «اولین مشاهده قالب» تا «ویرایش دقیق همان بخشی که روی آن کلیک کرده» را قفل می‌کند.

هدف محصولی ساده است: فروشنده باید ابتدا با یک فروشگاه دمو بتواند ۵۰ قالب را با محتوای ثابت مقایسه کند؛ سپس بعد از ورود داده‌های واقعی خود، همان قالب‌ها را با محصولات، دسته‌ها، برندها و رسانه‌های خودش ببیند؛ بعد قالب موردنظر را انتخاب کند و هر بخش را مستقل، ساده و کنترل‌شده ویرایش کند.

این Charter معماری جدیدی خارج از R4 ایجاد نمی‌کند. تمام Preview، Apply، Draft، History، Publish و Public Storefront باید از Ownerهای canonical موجود استفاده کنند.

> **نکته کلیدی:** اصل تجربه: اول ببین، بعد با داده خودت مقایسه کن، سپس انتخاب کن، و بعد فقط همان چیزی را که روی آن کلیک می‌کنی ویرایش کن.

## ۲. رابطه با دو Charter اصلی Phase 5

| سند | نقش |
| --- | --- |
| RASTISI_PHASE5_DESIGN_EXPANSION_CHARTER | Scope کل Phase 5 و معیار نهایی بسته‌شدن فاز. |
| RASTISI_PHASE5_50_TEMPLATE_DNA_DESIGN_LAB_CHARTER | قرارداد ۵۰ Template DNA، Design Lab، Random Mix و Theme Overlay. |
| این سند | Onboarding Demo، Preview با داده Merchant، Apply Template، Contextual Click-to-Edit و Basic/Advanced Editor. |

> **نکته کلیدی:** هیچ‌کدام از این اسناد مجوز ساخت Renderer، Draft lifecycle، Registry یا Persistence موازی نیستند.

## ۳. آنچه سند معماری ارسالی از قبل درست تعریف کرده است

سند 2026-09-01 پایه معماری مناسبی دارد: ۵۰ Ready Template را Recipe روی یک Store Appearance Engine مشترک می‌داند، Template Demo را از Template Preset جدا می‌کند، Rasti Mode Demo را fixture canonical برای مقایسه معرفی می‌کند، و تأکید دارد که انتخاب Template نباید Demo catalog را داخل فروشگاه Merchant کپی کند.

همان سند همچنین می‌گوید پس از آنکه Merchant فروشگاه واقعی دارد، Template exploration باید تا حد امکان از داده واقعی خودش استفاده کند؛ Design Lab نیز باید transient باشد و فقط با Apply صریح وارد Draft/History شود.

- One Builder shell و One shared Draft mutation contract حفظ شود.
- Preview/Public از یک rendering engine مشترک استفاده کنند.
- Global Design first، local overrides sparse باشند.
- Public فقط از Publish تغییر کند.
- ۵۰ Template کدبیس جداگانه نباشند.
- All 50 برای همه صنایع قابل مشاهده باشند؛ صنعت فقط ranking/recommendation را تغییر دهد.

> **نکته کلیدی:** این Charter موارد بالا را جایگزین نمی‌کند؛ فقط تجربه Onboarding و Contextual Editing را دقیق‌تر می‌کند.

## ۴. مسیر نهایی Merchant — از ثبت‌نام تا سایت شخصی

| مرحله | آنچه Merchant می‌بیند | State واقعی |
| --- | --- | --- |
| ۱. ثبت‌نام اولیه | معرفی کوتاه و ورود به انتخاب ظاهر | هنوز Demo data به Store کپی نشده |
| ۲. گالری ۵۰ قالب | همه قالب‌ها با Canonical Demo Store | Preview-only |
| ۳. مقایسه | Desktop / Tablet / Mobile و Shortlist/Compare | Transient selection |
| ۴. انتخاب شروع | Apply یک Template DNA | Draft appearance تغییر می‌کند؛ business data دست‌نخورده |
| ۵. ورود اطلاعات واقعی | محصول، دسته، برند، تصاویر، قیمت و سایر محتوای Store | Ownerهای commerce/catalog خودشان |
| ۶. بازگشت به گالری قالب | همان ۵۰ قالب با «اطلاعات من» | Preview-only روی Merchant data |
| ۷. انتخاب یا تعویض قالب | Apply صریح Template جدید | فقط Design DNA/typed settings تغییر می‌کند |
| ۸. ویرایش صفحه | کلیک روی هر بخش → Inspector همان بخش | Contextual editor روی Draft canonical |
| ۹. انتشار | Preview نهایی و Publish | Public فقط از مسیر Publish تغییر می‌کند |

## ۵. Canonical Demo Store برای Onboarding

فروشگاه دمو باید baseline ثابت و قابل تکرار برای مقایسه ۵۰ قالب باشد تا تفاوت محتوا باعث اشتباه در قضاوت طراحی نشود. سند معماری موجود نام canonical آن را Rasti Mode Demo با slug برابر rasti-mode-demo تعیین کرده است.

در سند معماری ارسالی برای این fixture مجموعه‌ای شامل ۵۰ محصول، ۱۰ دسته، ۶ برند، ۱۵۰ تصویر محصول، ۲۰۶ Variant روی ۴۱ محصول، ۶ Collection، چهار Hero item، شش Banner و ۱۰ Story item ذکر شده است. این اعداد در Phase 5 باید به‌عنوان target/source claim بررسی شوند؛ کامل‌بودن فعلی آن‌ها در repository فقط با Audit واقعی قابل تأیید است.

- Demo content فقط برای Preview/QA/Onboarding است.
- انتخاب Template هرگز محصولات، دسته‌ها، برندها، قیمت، موجودی یا تصاویر Demo را وارد Store واقعی نمی‌کند.
- تمام ۵۰ Template باید روی همین dataset قابل مقایسه باشند.
- Demo Store باید representative stateهای لازم برای sale، out-of-stock، long Persian text، missing/alternative media و responsive QA را پوشش دهد.
- هر تغییر در dataset دمو باید controlled/versioned باشد تا مقایسه بصری تاریخی بی‌معنا نشود.

> **نکته کلیدی:** در Kickoff Phase 5 ابتدا وضعیت واقعی rasti-mode-demo Audit می‌شود؛ چیزی که از قبل سالم ساخته شده دوباره از صفر ساخته نشود.

## ۶. گالری ۵۰ قالب برای کاربر تازه‌وارد

اولین برخورد Merchant با ۵۰ قالب باید یک تجربه انتخاب باشد، نه پنل تنظیمات فنی. هر کارت Template باید Preview واضح، نام، سبک، مناسب‌بودن تقریبی و گزینه مشاهده کامل داشته باشد.

Merchant باید بتواند بدون ورود به Editor پیشرفته، Templateها را روی محتوای Demo ببیند، بین چند گزینه جابه‌جا شود و تفاوت Desktop/Mobile را درک کند.

- Show all 50 همیشه وجود داشته باشد.
- فیلتر و recommendation فقط برای پیدا کردن سریع‌تر است، نه محدودسازی دسترسی.
- Preview هر Template از Shared Renderer واقعی Production ساخته شود؛ screenshot جعلی یا renderer مخصوص Gallery مرجع truth نباشد.
- Preview باید Template DNA و responsive behavior واقعی همان Template را نشان دهد.
- انتخاب نهایی با Action صریح مانند «استفاده از این قالب» انجام شود.

## ۷. پیش‌نمایش همان ۵۰ قالب با داده واقعی Merchant

بعد از آنکه Merchant حداقل بخشی از Catalog و Brand/Category data خود را وارد کرد، گالری Template باید بتواند همان ۵۰ DNA را روی context واقعی فروشگاه او رندر کند.

این قابلیت Preview است و تا زمان Apply هیچ تغییری در Draft اصلی ایجاد نمی‌کند. هدف این است که Merchant ببیند «محصولات من در Template 17 چه شکلی می‌شوند؟» و بلافاصله Template 31 را نیز با همان داده مقایسه کند.

| حالت Preview | داده | کاربرد |
| --- | --- | --- |
| فروشگاه دمو | Canonical Demo Store | Onboarding اولیه و مقایسه استاندارد |
| اطلاعات من | Catalog/Brand/Category/Media واقعی Merchant | تصمیم واقعی بعد از ورود محتوا |
| طرح فعلی من | Draft appearance فعلی + Merchant data | Baseline برای Compare |
| Template پیشنهادی | Candidate DNA + Merchant data | Preview بدون Mutation |

> **نکته کلیدی:** Demo و Merchant data هرگز در یک preview بدون برچسب با هم مخلوط نشوند. اگر داده Merchant کم است، کمبود باید شفاف باشد یا با placeholder غیرتجاری نمایش داده شود، نه با کپی مخفی Demo data.

## ۸. Apply Template — چه چیزی تغییر می‌کند و چه چیزی نباید تغییر کند

- Apply باید server-validated و tenant-safe باشد.
- Apply کامل Template یک operation منطقی/اتمیک روی Draft باشد.
- Stale-write/version preconditionهای موجود حفظ شوند.
- پس از Apply، Merchant به Template قفل نمی‌شود و هر component مجاز را مستقل تغییر می‌دهد.
- Reset to original DNA اگر وجود دارد، به Design DNA مربوط است و نباید content Merchant را پاک کند.

| باید تغییر کند | نباید تغییر کند |
| --- | --- |
| Template DNA / registered component selections | محصولات و SKUهای Merchant |
| Section recipe و layout selections مجاز | دسته‌ها و برندهای Merchant |
| Palette/Typography/Density/Radius/Width در قرارداد موجود | قیمت، موجودی، Variantهای محصول |
| Theme/appearance defaults اگر جزو Recipe باشند | تصاویر Catalog و مالکیت Media |
| Template provenance برای reset/support در صورت وجود Owner canonical | Order/Customer/Business data |

## ۹. قانون اصلی Contextual Editing — روی هرچه کلیک می‌کنی همان را ویرایش کن

در حالت Editor، کلیک روی یک بخش قابل ویرایش باید همان بخش یا Global Region مربوط را انتخاب کند و Inspector فقط تنظیمات مرتبط با همان Target را نشان دهد.

Merchant نباید برای تغییر Hero روی صفحه، از بین ده‌ها منوی نامرتبط دنبال Hero بگردد. صفحه خودش navigation اصلی Editor است.

- کلیک Hero → فقط Hero Editor.
- کلیک Header → Header/Global Region Editor.
- کلیک Product Showcase → فقط همان Showcase Section Editor.
- کلیک Product Card داخل Showcase → اگر card style در سطح Section قابل Override است، context همان Section حفظ شود؛ اگر Global Card style است، UI صریحاً scope را نشان دهد.
- کلیک Footer → Footer Editor.
- کلیک تصویر/پس‌زمینه قابل انتخاب → Media/Background control همان Section.
- Selected section روی Preview highlight واضح داشته باشد و Inspector عنوان Target را نشان دهد.
- با انتخاب Target جدید، پنل قبلی جایگزین شود؛ چند Inspector نامرتبط همزمان باز نباشد.

> **نکته کلیدی:** Product principle: Click what you want to edit. Edit only what you clicked.

## ۱۰. رفتار کلیک در Editor در برابر رفتار سایت واقعی

چون Preview شامل لینک، Add to Cart و عناصر تعاملی است، Editor باید بین «انتخاب برای ویرایش» و «آزمایش تعامل» تمایز روشن داشته باشد.

حالت پیش‌فرض Editor selection-first است: کلیک یک Section را انتخاب می‌کند و navigation/checkout تصادفی اتفاق نمی‌افتد. در صورت نیاز، یک Preview/Interaction mode مشخص می‌تواند رفتار واقعی لینک‌ها و کنترل‌ها را آزمایش کند.

> **نکته کلیدی:** این جداسازی از خطای کاربر جلوگیری می‌کند و Contextual Editing را قابل پیش‌بینی نگه می‌دارد.

## ۱۱. دو سطح تنظیمات برای هر بخش: معمول و پیشرفته

- تب «معمول» همیشه پیش‌فرض باشد.
- «پیشرفته» collapsed/secondary باشد و UI عادی را شلوغ نکند.
- تنظیم پیشرفته فقط typed/allowlisted values داشته باشد؛ arbitrary CSS/HTML/JS ممنوع.
- هر Family فقط کنترل‌های مرتبط با خودش را نشان دهد؛ تنظیمات بی‌اثر یا نامرتبط نمایش داده نشوند.
- Reset همان Section و Reset همان property به inherited/default باید واضح باشد.

| سطح | هدف | نمونه کنترل‌ها |
| --- | --- | --- |
| معمول / ساده | ۸۰٪ کارهای روزمره بدون اصطلاح فنی | عنوان، متن، تصویر، CTA، چیدمان، منبع داده، تعداد آیتم، نمایش/عدم نمایش، رنگ یا پس‌زمینه ساده |
| پیشرفته | کنترل بیشتر برای Merchant حرفه‌ای‌تر | local typography، spacing، alignment، overlay، height/aspect behavior، motion profile، responsive options، advanced background، visibility rules مجاز |

## ۱۲. رنگ، فونت، عکس و پس‌زمینه هر Section

Merchant باید بتواند در حدی که contract آن Section پشتیبانی می‌کند ظاهر همان Section را تغییر دهد، بدون ساخت CSS آزاد یا Theme engine دوم.

اصل همچنان Global Design first است. Local Section Override فقط وقتی ثبت می‌شود که Merchant عمداً مقدار متفاوتی انتخاب کند؛ در غیر این صورت Section مقدار Global یا Template DNA را inherit می‌کند.

| نوع Override | رفتار پیشنهادی |
| --- | --- |
| رنگ | انتخاب از token/palette مجاز یا typed color contract موجود؛ همراه گزینه «استفاده از رنگ کلی سایت» |
| فونت | انتخاب از typography/fontهای allowlisted سیستم؛ همراه گزینه inherit |
| تصویر | انتخاب از Media متعلق به همان tenant/store و media role مجاز Section |
| پس‌زمینه | none / color / image / gradient یا گزینه‌های registered که contract اجازه می‌دهد |
| Overlay | typed opacity/treatment؛ نه CSS expression |
| Spacing/Height | preset/typed rangeهای امن و responsive-aware |
| Motion | registered motion profile + reduced-motion fallback |

> **نکته کلیدی:** Sparse override مهم است: اگر Merchant override را پاک کند، Section دوباره از Global/Template value ارث ببرد؛ مقدار Global نباید داخل هر Section کپی شود.

## ۱۳. Scope و ارث‌بری تنظیمات

| Scope | مثال | اثر |
| --- | --- | --- |
| Global Appearance | فونت پایه، Palette، Radius، Density | پیش‌فرض کل Store |
| Global Region | Header / Footer / Bottom Navigation | در صفحات مرتبط مشترک |
| Page/Section | Hero یا Showcase خاص همان صفحه | فقط همان instance |
| Component Family Default | Product Card style canonical | همه محل‌هایی که از همان default استفاده می‌کنند مگر override مجاز |
| Local Override | پس‌زمینه Hero صفحه اصلی | فقط همان Target |

> **نکته کلیدی:** Inspector باید Scope هر تغییر را قبل از Apply روشن نشان دهد تا Merchant ناخواسته کل سایت را تغییر ندهد.

## ۱۴. Storefront Showcase Section در Contextual Editor

قابلیت «ویترین فروشگاه» که در Charter اصلی Phase 5 تعریف شد باید یکی از بهترین نمونه‌های Contextual Editing باشد. Merchant یک Section دارد که می‌تواند Categories، Products، Collections یا Brands را از Ownerهای واقعی Catalog انتخاب و با layoutهای registered نمایش دهد.

- نوع محتوا: دسته‌ها / محصولات / مجموعه‌ها / برندها.
- منبع: انتخاب دستی یا query/preset مجاز مانند جدیدترین، پرفروش، تخفیف‌دار؛ فقط اگر commerce/catalog domain آن را پشتیبانی کند.
- Layout: انتخاب تصویری از Variantهای معتبر.
- عنوان و CTA: ساده و مستقیم.
- تعداد آیتم و «مشاهده همه»: typed controls.
- Basic tab برای موارد بالا؛ Advanced tab برای spacing، appearance overrides، motion و responsive options مجاز.
- همان Section بتواند در Home، Category landing، Brand page، Campaign landing و سایر page typeهای پشتیبانی‌شده reuse شود.

## ۱۵. Builder معمولی در برابر Design Lab

| Builder معمولی | Design Lab |
| --- | --- |
| برای ویرایش سریع سایت واقعی | برای کشف ترکیب‌ها و مقایسه طراحی |
| Contextual click-to-edit | Template/Component exploration |
| Basic tab پیش‌فرض | کنترل‌های ترکیبی بیشتر، Random Mix و Locks |
| تغییرات روی Draft canonical طبق semantics موجود | Transient candidate state تا Apply |
| فقط تنظیمات Target انتخاب‌شده | نمای وسیع‌تر از Engine |
| همان Shared Renderer | همان Shared Renderer |

> **نکته کلیدی:** Design Lab نباید قابلیت ظاهری‌ای بسازد که Normal Builder/production contracts نتوانند نمایندگی کنند.

## ۱۶. مسیر داده و معماری canonical

پیاده‌سازی باید روی Ownerهای واقعی repository سوار شود. نام package/model/service از روی این Charter حدس زده نمی‌شود و Claude Code در Kickoff موظف است owner map واقعی را استخراج کند.

| جریان | مسیر مفهومی |
| --- | --- |
| Demo Template Preview | Template DNA + Demo Store context → validation/resolution → Shared Renderer → Preview |
| Merchant-data Template Preview | Candidate DNA + Merchant context → tenant-safe resolution → Shared Renderer → Preview |
| Contextual edit | Selected target → typed mutation → existing stale-write/tenant checks → Draft/History |
| Apply Template | Validated full DNA operation → Draft/History canonical |
| Public | Published state → Shared Renderer → Public Storefront |

> **نکته کلیدی:** One concept = one canonical owner. Preview mode، onboarding و contextual editor فقط مصرف‌کننده Ownerهای موجود هستند، نه Owner جدید.

## ۱۷. Draft، History، Undo/Redo و Autosave

- ویرایش پایدار Normal Builder از همان Draft lifecycle موجود استفاده کند.
- هر تغییر Section باید history semantics موجود را رعایت کند؛ per-section save lifecycle جدید ساخته نشود.
- Design Lab exploration یا Template preview تا Apply نباید history را با هر کلیک آزمایشی پر کند.
- Apply Template یا Apply Lab candidate یک operation منطقی و قابل رهگیری باشد.
- Undo/Redo باید تغییر ظاهر را بدون آسیب به Catalog/Business data برگرداند.
- Autosave اگر در R4 canonical است reuse شود؛ اگر نیست، این Charter مجوز ساخت autosave موازی نیست.

## ۱۸. Responsive، RTL و Accessibility

- معیار رسمی QA: Desktop 1440×900، Tablet 768×1024، Mobile 390×844.
- RTL/Persian مسیر اصلی است و LTR نباید contract جداگانه‌ای بسازد.
- Contextual target highlight و Inspector با keyboard قابل دسترسی باشند.
- Focus-visible، labelهای واضح، semantic controls و contrast مناسب الزامی است.
- Motionهای قابل ویرایش reduced-motion equivalent داشته باشند.
- تغییر device preview باید همان responsive behavior واقعی component را نشان دهد، نه نسخه screenshot ثابت.

## ۱۹. امنیت، Tenant Isolation و Media

- Preview با Merchant data فقط به Catalog/Brand/Category/Media همان tenant/store دسترسی داشته باشد.
- Media picker فقط resourceهای مجاز همان Merchant را resolve کند.
- Template DNA و Section settings فقط stable registered keys و typed schema values ذخیره کنند.
- HTML/CSS/JS آزاد، raw JSON بدون validation، arbitrary template path و renderer name ورودی Merchant ممنوع است.
- Invalid/unknown component یا setting با typed error رد شود.
- Demo Store context هرگز مجوز دسترسی cross-tenant ایجاد نکند.

## ۲۰. Empty، Loading و Failure States

| وضعیت | رفتار مطلوب |
| --- | --- |
| Merchant هنوز محصول ندارد | پیشنهاد روشن برای استفاده از Demo preview یا تکمیل Catalog؛ بدون کپی داده Demo |
| تصویر ندارد | placeholder استاندارد و شفاف، نه تصویر Demo با ظاهر واقعی |
| Template reference نامعتبر | Preview fail-safe + پیام قابل فهم؛ Apply ممنوع |
| Stale Draft | Mutation رد شود و مسیر refresh/retry مطابق R4 |
| Media متعلق به tenant دیگر | رد کامل server-side |
| Preview در حال ساخت | Skeleton/progress بدون Mutation |
| Component unsupported | fallback safe/default فقط طبق contract و با evidence؛ نه silent arbitrary substitution |

## ۲۱. Audit اجباری در شروع Phase 5

قبل از ساخت هر قسمت از این Charter، Claude Code باید وضعیت واقعی repository را Audit کند تا از دوباره‌کاری جلوگیری شود. به‌خصوص کاربر اشاره کرده که بخش زیادی از Demo Store احتمالاً از قبل ساخته شده است؛ این ادعا باید با evidence کد و data fixture بررسی شود، نه با حدس.

- وجود و وضعیت rasti-mode-demo و seed command/fixture مربوط.
- تعداد واقعی محصولات، دسته‌ها، برندها، تصاویر، Variantها، Collections، Hero/Banner/Story در fixture.
- مسیر فعلی onboarding و template selection.
- مسیر فعلی Template Demo preview و Template apply.
- Owner canonical فعلی Ready Templates و Store Appearance selections.
- قابلیت Preview با Merchant data، اگر از قبل وجود دارد.
- Editor selection/section focus موجود و امکان contextual click targeting.
- Basic/Advanced settings pattern موجود در R4، اگر قبلاً ساخته شده است.
- Local appearance override contract موجود یا gap واقعی آن.
- Draft/History/Undo/Redo/Publish و Shared Renderer parity.

> **نکته کلیدی:** نتیجه Audit باید به سه ستون تقسیم شود: EXISTS & REUSE / EXISTS BUT NEEDS REPAIR / MISSING & BUILD. هیچ قابلیت سالمی دوباره ساخته نشود.

## ۲۲. ترتیب پیشنهادی پیاده‌سازی

| گام | خروجی |
| --- | --- |
| ۱ | Repository audit و canonical owner map + Demo Store inventory |
| ۲ | تکمیل/repair Demo Store و Template Demo rendering روی Shared Renderer |
| ۳ | Onboarding Gallery برای ۵۰ Template با Demo context |
| ۴ | Merchant-data Template Preview بدون Mutation |
| ۵ | Atomic Apply Template با حفظ Catalog/Business data |
| ۶ | Contextual selection model: click target → inspector target |
| ۷ | Basic settings contracts برای familyهای اصلی |
| ۸ | Advanced settings + sparse local appearance overrides |
| ۹ | Showcase Section contextual editing و data-source controls |
| ۱۰ | Design Lab integration / Compare / Random Mix روی همان contracts |
| ۱۱ | Desktop/Tablet/Mobile + RTL/LTR + accessibility/browser QA |
| ۱۲ | Evidence matrix، Product Owner review و closure gate |

> **نکته کلیدی:** Order می‌تواند بر اساس dependencies واقعی repository اصلاح شود، اما canonical owners و Shared Renderer parity نباید دور زده شوند.

## ۲۳. Acceptance Criteria

- کاربر تازه‌وارد می‌تواند ۵۰ Template را با Canonical Demo Store ببیند و مقایسه کند.
- هیچ Demo catalog/business data با انتخاب Template به Store Merchant کپی نمی‌شود.
- پس از ورود داده واقعی، Merchant می‌تواند همان ۵۰ Template را با اطلاعات خودش Preview کند بدون اینکه Draft تا Apply تغییر کند.
- Apply Template فقط DNA/appearance مجاز را تغییر می‌دهد و Merchant content/business data را حفظ می‌کند.
- در Editor، کلیک روی هر Section قابل ویرایش Inspector همان Target را باز می‌کند.
- Inspector دو سطح معمول و پیشرفته دارد و معمول پیش‌فرض است.
- Merchant می‌تواند color/font/image/background هر Section را فقط در محدوده typed/allowlisted contract تغییر دهد.
- Local override sparse و قابل Reset به inherited Global/Template value است.
- Global vs Section scope برای Merchant روشن است.
- Storefront Showcase Section برای Categories/Products/Collections/Brands از همان Contextual Editor استفاده می‌کند.
- Normal Builder و Design Lab از یک appearance model و Shared Renderer استفاده می‌کنند.
- Preview Demo، Preview Merchant و Public rendering renderer موازی ندارند.
- Draft/History/stale-write/tenant security/Publish semantics موجود حفظ شده‌اند.
- Desktop 1440، Tablet 768 و Mobile 390 به همراه RTL و accessibility evidence سبز است.
- وضعیت واقعی Demo Store قبل از implementation با evidence Audit شده و duplicate implementation ایجاد نشده است.

## ۲۴. Definition of Done این زیرسیستم

این زیرسیستم فقط وقتی DONE است که Merchant بتواند بدون دانش فنی مسیر کامل زیر را با UI قابل فهم طی کند و تمام مسیر از architecture canonical R4 عبور کند:

- ثبت‌نام → مشاهده ۵۰ قالب با Demo Store.
- مقایسه و انتخاب starter Template.
- ورود Catalog/Brand/Category/Media واقعی.
- مشاهده دوباره همان Templateها با «اطلاعات من».
- Apply یک Template بدون از دست‌رفتن محتوا.
- کلیک روی هر Section و بازشدن Editor همان Section.
- ویرایش ساده در تب «معمول».
- کنترل بیشتر در تب «پیشرفته».
- تغییر کنترل‌شده رنگ، فونت، تصویر و پس‌زمینه Section با inheritance صحیح.
- Preview responsive و Publish نهایی با Shared Renderer.
- تست، browser QA، tenant/security checks و evidence کامل.

> **نکته کلیدی:** اگر یکی از این حلقه‌ها با مسیر موازی، renderer جدا، Demo-data copy، local CSS آزاد یا editor نامرتبط پیاده شود، این Charter کامل نشده است.

## ۲۵. جمله نهایی محصول

RastiSi باید به Merchant اجازه دهد قبل از تصمیم، فروشگاه‌های آماده را با یک Demo واقعی ببیند؛ بعد همان طراحی‌ها را با داده خودش امتحان کند؛ سپس قالب را انتخاب کند و صفحه را دقیقاً از همان جایی که می‌بیند ویرایش کند. قدرت سیستم باید زیاد باشد، اما تجربه Merchant باید ساده بماند.

> **نکته کلیدی:** See first. Preview with your own data. Choose. Click. Edit. Publish.
