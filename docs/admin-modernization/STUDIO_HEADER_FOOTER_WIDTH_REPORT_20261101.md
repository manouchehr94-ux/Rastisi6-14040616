# RastiSi — ویرایش هدر/فوتر در Studio و عرض قابل‌تنظیم Storefront (گزارش ۱۴۰۵/۰۸/۱۰ — 2026-11-01)

> مبنا: نسخهٔ Pushشدهٔ `e7a479492b2b46016e89195ad52914163b4f94a7` (همان که روی ویندوز QA شد).
> وضعیت: ۶ Commit محلی روی `claude/great-cori-6oox1r`؛ **Push / Merge / Deploy / Migration / Backfill انجام نشده**. Production، Windows QA (پورت ۸۰۰۸) و دادهٔ Storeهای موجود دست‌نخورده‌اند.

## ۰. خلاصه در یک نگاه

| درخواست | نتیجه |
|---|---|
| کلیک روی هدر/فوتر پنجرهٔ بزرگ باز نکند | ✅ Inspector کناری (بدون تیره‌کردن صفحه، Canvas قابل‌کلیک) |
| مدل هدر/فوتر داخل Inspector با کارت تصویری واقعی | ✅ تب «مدل‌ها» (۲۵ مدل هدر، ۱۹ مدل فوتر، تصویر واقعی، «مدل فعلی» علامت‌دار) |
| هدر حرفه‌ای ۴ قالب مستقل از قالب | ✅ مدل + جایگاه، قابل‌اعمال روی هر قالب؛ ناسازگار = صادقانه (بدون هدر نیمه‌رندر/دوتایی) |
| عرض صفحات قابل‌تنظیم | ✅ استاندارد / عریض / تمام‌عرض / سفارشی؛ Draft→Preview→Publish؛ بدون Migration |
| رگرسیون | ✅ ماتریس ۱۹ قالب × ۸ عرض × ۴ صفحه = ۶۰۸ بارگذاری بدون خطا/Overflow/شکستن قیمت |

## ۱. معماری واقعی هدر و فوتر (از کد، نه از حافظه)

| لایه | جای واقعی | نکته |
|---|---|---|
| فهرست مدل‌ها | `global_region_registry.py` — `GLOBAL_HEADER_REGION` (۲۵ مدل)، `GLOBAL_FOOTER_REGION` (۱۹ مدل) | هر مدل: `key`، `label_fa`، Template رندر زیر `storefront_builder/partials/global_header|global_footer/` |
| ذخیره | `StorefrontLayoutVersion.header_config / footer_config` (JSON در Draft/Published) | Store-scoped؛ با Publish کپی می‌شود |
| نوشتن | `r4_mutation_service`: `header.update` / `footer.update` (+ همگام‌سازی Manifest طراحی) | Undo/Redo و Revision همان موتور R4 |
| رندر | `render_service` + `header_variant_template` (یک Renderer ثبت‌شده برای Preview/Draft/Live) | |
| هدر داخل هیرو | `hero_stage.py`: `header_mode` = `independent` / `merged` / `overlay`؛ تصمیم «هدر داخل Stage رندر شود؟» فقط در `render_service.header_embedded_for` | همان تابع برای Preview، Draft Preview و صفحهٔ زنده |
| تصویر مدل‌ها | `vision/region_previews/{header,footer}/<مدل>.{desktop,mobile}.webp` + `manifest.json` (اثرانگشت تازگی) + `vision_ux.gallery_data()` | مدل‌هایی که پیکسل‌به‌پیکسل مثل هم‌اند `same_as` دارند |
| لایهٔ Vision | `vision/vision.js` روی همان فرم R4 (`#r4GlobalDesign` → `#rsGlobalHeader` / `#rsGlobalFooter`) | انتخاب مدل = تغییر `<select>` بومی + رویداد `change` → همان `header.update` |

دو مسیر Studio وجود دارد: **Vision Studio** (`/admin-portal/vision-studio/` — همان که روی ویندوز QA شد) و مسیر قدیمی‌تر R4 (`/admin-portal/storefront-builder/r4/`). هر دو یک Backend و یک فرم دارند.

## ۲. علت پنجرهٔ بزرگ

در Vision Studio، «طراحی سراسری» (Global Design) همیشه داخل یک **Dialog مودال** (`.vs-dlayer` / `[data-vs-design-modal]`، ۹۶۰×۹۰۰، پس‌زمینهٔ تیره، `role=dialog aria-modal=true`) نشان داده می‌شد. کلیک روی هدر/فوتر در Canvas → `S.openGlobal('header'|'footer')` → رویداد `r4:global-opened` → `vision.js` دستهٔ «سربرگ/پابرگ» را در همان Dialog باز می‌کرد. یعنی **هر دو (هدر و فوتر)** همین رفتار را داشتند و گالری مدل‌ها (با تصویر واقعی) از قبل وجود داشت، فقط داخل مودال بود. شواهد قبل: `screenshots_studio_20261101/before_header_click_big_modal.webp` و `before_footer_click_big_modal.webp`.
(QA قبلیِ من روی مسیر R4 بود و مودال را نمی‌دید؛ این بار QA روی خود Vision Studio انجام شد.)

## ۳. وضعیت واقعی هدر چهار قالب حرفه‌ای

| قالب | مدل ثبت‌شده (`header_variant`) | جایگاه (`header_mode` هیرو) | وضعیت در گالری قبلی |
|---|---|---|---|
| آتلیه دوپنل (`dual_atelier`) | `atelier_nav` | `merged` | مدل مستقل |
| نشریهٔ نوآر (`editorial_noir`) | `editorial_masthead` | `merged` | «هم‌ظاهر» با `boutique_centered` (پنهان در گروه بستهٔ هم‌ظاهرها) |
| تجارت شیشه‌ای (`glass_commerce`) | `centered_brand` | `merged` | «هم‌ظاهر» با `premium_three_column` |
| بوم نامتقارن (`asymmetric_canvas`) | `floating_compact` | `overlay` | «هم‌ظاهر» با `atelier_nav` |

نتیجه: هدر این چهار قالب **مدل‌های ثبت‌شدهٔ قابل‌انتخاب** هستند، نه بخشی از Hero Stage؛ اما حس «حرفه‌ای/یکپارچه»‌شان از **جایگاه** (`header_mode` هیروی صفحهٔ اصلی) می‌آید که در هیچ کارت مدلی نبود، و سه‌تا از چهار مدل در گالری عملاً پنهان بودند. تصویر کارت‌ها هم همیشه هدر «مستقل» بود، نه نمای یکپارچه.

## ۴. انتخاب مستقل هدر و فوتر

- **Inspector کناری** (`vision.js` + `vision.css`): کلیک روی هدر یا فوتر در Canvas آن را انتخاب و Inspector را کنار Canvas باز می‌کند (۴۲۰px؛ زیر ۱۱۰۰px پنل پایین). `role=complementary`، بدون Focus-trap، Esc می‌بندد.
- **تب‌ها** (از ساختار همان فرم واقعی ساخته می‌شوند، نه کپی کنترل‌ها): «مدل‌ها» | «محتوا و نمایش» | «طراحی» | «پیشرفته». ناوبری با کلیک و کلیدهای ←/→/Home/End (RTL‌-آگاه).
- **مدل‌ها**: کارت تصویری واقعی، «مدل فعلی»، «انتخاب این مدل» (= `select.change` → `header.update`/`footer.update`)، «مشاهدهٔ بزرگ‌تر» (پیش‌نمایش فقط‌خواندنی اختیاری، چیزی را تغییر نمی‌دهد). Canvas همان لحظه Draft را نشان می‌دهد؛ ذخیره/Undo/Redo/Preview/Publish همان موتور قبلی.
- Undo/Redo در R4 با Reload کامل صفحه تمام می‌شود؛ یک نشانهٔ ۲۰ثانیه‌ای `sessionStorage` (نه داده) همان Inspector و همان تب را بعد از Reload برمی‌گرداند.
- فوتر همان ساختار؛ تغییر فوتر هدر/هیرو/محتوا را تغییر نمی‌دهد (Contact/لوگو/لینک‌ها از Store می‌آیند، نه از مدل).

## ۵. انتقال «هدر حرفه‌ای» بین قالب‌ها (Header Recipe)

طراحی: هدر حرفه‌ای = **مدل** (Store-global) + **جایگاه** (`header_mode` اولین Hero Stage صفحهٔ اصلی). `header_placement.py`:

- `placement_state(draft)`: همان تصمیم تولید (`render_service.header_embedded_for` با آیتم‌های سبک) — بازتولید دوم وجود ندارد.
- `list_recipes()`: از رجیستری Ready Templateها (فقط قابل‌انتخاب‌ها) خوانده می‌شود: هر قالبی که Hero Stage با هدر یکپارچه دارد یک Recipe (مدل + جایگاه) می‌دهد → امروز ۴ تا؛ قالب Stageدار جدید خودکار اضافه می‌شود. نام قالب در هیچ Renderer/CSS نیست.
- `header.set_placement` (`independent|merged|overlay`) = یک `section.update_settings` اعتبارسنجی‌شدهٔ Hero Stage اول صفحه؛ id از کلاینت نمی‌آید (Store/Draft خود فراخواننده).
- `header.apply_recipe`: مدل همیشه اعمال می‌شود؛ جایگاه فقط اگر Stage قابل‌استفاده باشد. هرگز Hero اضافه/حذف/جایگزین نمی‌کند؛ فوتر، پالت، صفحات، نوار اعلان فروشنده دست نمی‌خورد؛ یک قدم History.
- ناسازگاری صادقانه: بدون Stage بالای صفحه → دو گزینهٔ یکپارچه غیرفعال + دلیل؛ Recipe فقط مدل را می‌گذارد و پیام می‌دهد. Stage پنهان در یک دستگاه → `header_placement_stage_hidden` (سبد خرید همیشه در دسترس بماند)؛ Stage قفل → `section_locked`.

## ۶. ساختار تنظیمات «چیدمان و عرض صفحات»

- **ذخیره (بدون Migration)**: کلیدهای Sparse در `StorefrontLayoutVersion.appearance_config`: `page_width_mode` (`wide|full|custom`؛ غیبت = استاندارد = رفتار دقیقاً قبلی)، `page_max_width` (۹۶۰–۲۴۰۰)، `page_gutter` (۸–۶۴) فقط برای سفارشی. Storeهای موجود شکل ذخیره و CSS قبلی را حفظ می‌کنند.
- **یک واژگان + یک Resolver**: `appearance_registry.PAGE_WIDTH_MODES` / `resolve_page_layout()` (هرگز Exception نمی‌دهد؛ مقدار خراب → استاندارد/پیش‌فرض). Validator: `layout_service._apply_page_layout_fields`؛ خطا با جملهٔ فارسی که کنترل و بازه را می‌گوید.
- **نوشتن**: همان `appearance.update` (Undo/Redo، Revision). انتخاب «استاندارد» کلیدها را حذف می‌کند.
- **خواندن**: Context Processor از نسخهٔ هویت سراسری (Preview = Public، همهٔ صفحات: خانه، دسته/جست‌وجو/لیست، محصول، Collection، سبد، پرداخت، فوتر). `base.html` فقط `data-sfb-page-width` و دو عدد صحیح اعتبارسنجی‌شده می‌نویسد.
- **CSS** (`base.css`، یک توکن `--sfb-page-width` که همهٔ Containerها می‌خوانند):
  - استاندارد: بدون تغییر (`max(عرض قالب, min(84vw, 1720px))`)؛
  - عریض: `max(عرض قالب, min(92vw, 1920px))`؛
  - تمام‌عرض: `100%` منهای Gutter؛
  - سفارشی: ستون محتوا دقیقاً عدد فروشنده + Gutter دلخواه دورش (در موبایل Gutter ≤ ۱۲px می‌ماند، `layout.css` عرض را به Viewport محدود می‌کند).
- **عرض پس‌زمینهٔ Section ≠ عرض محتوا**: `data-width="full"` هر Section دست‌نخورده است و فقط تا لبهٔ Container می‌رود؛ متن و گرید محصول هیچ‌وقت به لبهٔ مانیتور نمی‌چسبند. نسبت کارت/تصویر دست‌نخورده.
- انتخاب عرض بعد از تعویض قالب حفظ می‌شود (تنظیم فروشنده است، نه جزء قالب).
- Studio: دستهٔ جدید «چیدمان و عرض صفحات» در تب طراحی. برچسب «عرض پایهٔ قالب» برای `content_width` قدیمی (کف عرض در استاندارد/عریض).

## ۷. تصاویر قبل/بعد (`screenshots_studio_20261101/`)

| قبل | بعد |
|---|---|
| `before_header_click_big_modal.webp` | `after_header_click_docked_inspector.webp`، `after_header_inspector_content_tab.webp` |
| `before_footer_click_big_modal.webp` | `after_footer_click_docked_inspector.webp` |
| — | `after_model_picked_canvas_updated.webp` (انتخاب مدل → Canvas) |
| — | `after_overlay_header_asymmetric_canvas.webp` (هدر شناور) |
| — | `after_template_without_stage_honest_reason.webp`، `after_pro_header_recipe_on_other_template.webp` |
| — | `after_width_category_custom.webp`، `width_{standard,wide,full,custom}_{1920,390}.webp` |

## ۸. تست‌ها، محدودیت‌ها، مقایسهٔ رگرسیون

### ۸.۱ تست خودکار جدید
- `test_vision_region_inspector.py` — قرارداد Inspector (Dock فقط هدر/فوتر، تب‌ها از فرم واقعی، غیرمودال، بدون Focus-trap، انتخاب مدل فقط با `change`، بازگشت بعد از Undo/Redo، فوکوس تب).
- `test_header_placement.py` — Recipeها از رجیستری، جابه‌جایی جایگاه یک‌قدمی با Undo، رد صادقانه بدون Stage / Stage پنهان / نامعتبر، فقط‌مدل روی قالب بدون Stage، یک هدر در خروجی، ایزولاسیون Store، Markup Inspector.
- `test_page_layout_width.py` — Resolver، Validator، History، Preview/Publish، همهٔ صفحات Storefront، تزریق امن، قرارداد CSS.
- به‌روزرسانی: `test_r4_mutation_security_coverage.py` (۳۳ نوع Mutation در جدول حفاظت)، `test_vision_studio.py` (دستهٔ جدید).

### ۸.۲ Chromium (Vision Studio + R4)
۶۵ بررسی روی ۴ قالب Stageدار + قالب بدون Stage + کلید‌بورد/RTL + مسیر R4: کلیک هدر/فوتر بدون مودال، کارت‌های تصویری واقعی، انتخاب مدل با یک هدر و Hero حفظ‌شده، فوتر ثابت، Undo/Redo، جایگاه، Recipe روی قالب بدون Stage (چهار Recipe: مدل اعمال، Stage اضافه نشد، یک هدر)، ←/→/Home/End، عدم Trap، Esc. اجرای اول ۶۳/۶۵: دو شکست **واقعی** (فوکوس بعد از ناوبری تب؛ Inspector بعد از کلیک فوتر هنگام باز بودن هدر) و یک مورد وسط راه (اسکرول لایهٔ Dock زیر Toolbar) پیدا و رفع شد؛ اجرای مجدد کامل شد.

### ۸.۳ رگرسیون Responsive
| ماتریس | بارگذاری | خطا / Overflow / قیمت شکسته / خطای JS |
|---|---|---|
| ۱۹ قالب × (۳۲۰،۳۶۰،۳۹۰،۷۶۸،۱۰۲۴،**۱۳۶۶**،۱۴۴۰،۱۹۲۰) × (خانه، لیست، محصول، سبد) — استاندارد | ۶۰۸ | ۰ / ۰ / ۰ / ۰ |
| حالت‌های عریض/تمام‌عرض/سفارشی × ۷ قالب (۳ منتخب + ۴ قدیمی/پنهان) × همان ۸ عرض × ۴ صفحه | ۶۷۲ | ۰ / ۰ / ۰ / ۰ |
| ۴ حالت × ۷ عرض × (خانه، لیست، سبد، پرداخت) | ۱۱۲ | Overflow ۰ |

عرض‌های اندازه‌گیری‌شدهٔ Container (قالب Rose، نمونه): ۱۴۴۰ → استاندارد ۱۲۱۰ / عریض ۱۳۲۵ / تمام‌عرض ۱۴۱۲؛ ۱۹۲۰ → ۱۶۱۳ / ۱۷۶۶ / ۱۸۹۲؛ سفارشی ۱۴۰۰ → ستون محتوا ۱۴۰۰ + Gutter.

### ۸.۴ Full Suite در برابر Baseline رسمی
| اجرا | تست | شکست/خطا | نتیجه |
|---|---|---|---|
| Baseline رسمی (`TEST_RECONCILIATION_20261029.md`) | — | ۳۸ شناسه (۲۹ + ۸ محیطی + ۲ فقط‌موازی) | مرجع |
| اجرای قبل از این ماموریت (e7a4794، ماموریت ۲) | ۱۲٬۰۹۱ | ۳۳ | همگی در Baseline |
| **این ماموریت، Full Suite روی `87dd388`** (`--parallel 4`، Python 3.11) | **۱۲٬۱۲۱** (+۳۰ تست جدید) | ۳۵ (۳۱ شکست + ۴ خطا) | ۳۳ همان‌های Baseline (۳۲ شناسهٔ تست + `setUpClass` تست پروتکل زندهٔ SMS که محیطی است) + **۲ شکست جدید که کار خودم بود** |
| شکست‌های جدید | | | `test_no_state_fades_text_with_element_opacity` و `test_disabled_states_never_use_element_opacity`: CSS جدید Inspector برای حالت غیرفعال/مشغول از `opacity` استفاده می‌کرد (افت کنتراست). رفع در `ef5a500` (رنگ صریح، نه opacity) — پنهان نشد، رفع شد |
| بازاجرا بعد از رفع: `apps.core` + `apps.storefront_builder` + `apps.dashboard` | ۷٬۱۱۴ | ۳۰ | همگی در مجموعهٔ ۳۳تایی Baseline؛ ۲ شناسهٔ جدید دیگر نیستند؛ **هیچ شناسهٔ جدیدی نیست**. ۳ شناسهٔ باقی‌ماندهٔ Baseline در اپ‌هایی هستند که بازاجرا نشدند (فقط دو فایل CSS Studio عوض شده) |

تست‌هایی که این ماموریت اضافه/بازنویسی کرد همه سبزند: `test_vision_region_inspector` (۹)، `test_header_placement` (۱۱)، `test_page_layout_width` (۱۰)، `test_r4_mutation_security_coverage`، `test_vision_studio`.
**هیچ شکست Baseline پنهان یا «سبز» نشده؛ هیچ تستی skip/حذف نشد.**

### ۸.۵ محدودیت‌ها و تصمیم‌هایی که لازم است مالک ببیند
1. **جایگاه یکپارچه فقط با Hero Stage بالای صفحهٔ اصلی**. روی قالبی با Slider/Banner نمی‌توان «داخل هیرو» گذاشت؛ تبدیل خودکار Slider به Stage هیرو را جایگزین می‌کرد (خلاف «هیرو خراب نشود»)، پس انجام نشد. اگر می‌خواهید «تبدیل هیرو به Stage با حفظ تصاویر» اضافه شود، تصمیم جدا و طراحی جدا می‌خواهد (بدون Migration قابل‌انجام است).
2. تصویر کارت Recipeها = تصویر واقعی مدل (نمای مستقل)؛ تصویر «نمای یکپارچه روی هیرو» ساخته نشد (نیاز به خط‌لولهٔ ضبط جدید). نتیجهٔ واقعی را Canvas همان لحظه نشان می‌دهد.
3. Studio مسیر R4 قدیمی Dock ندارد (همان کشوی قبلی)، ولی کنترل جایگاه و Recipeها را دارد (یک Partial مشترک).
4. زیر ۱۱۰۰px Inspector پنل پایین است؛ روی ۱۰۲۴px بررسی شد. روی گوشی ۳۹۰px Studio طراحی دسکتاپ‌محور قبلی را دارد و تغییری نکرد. بهبود ارتفاع پنل پایین (پنهان‌کردن نوار «اثر») به‌عنوان پولیش جداگانه پیشنهاد می‌شود.
5. «تمام‌عرض» عمداً ۱۴px حاشیهٔ بیرونی `layout.css` + Gutter دارد (به لبهٔ مانیتور نمی‌چسبد).
6. Checkout با Cart خالی در Sandbox خودش ۲۰۰ می‌دهد؛ عرض از همان نسخهٔ هویت سراسری خوانده می‌شود (تست «همهٔ صفحات»).

## ۹. Commitها (محلی، مستقل)
| Commit | موضوع |
|---|---|
| `d526fe5` | Inspector هدر/فوتر کنار Canvas + کارت‌های «مدل‌ها» (بدون مودال) |
| `b28febf` | جایگاه هدر + Header Recipe (`header_placement.py`، `header.set_placement`، `header.apply_recipe`) |
| `b47aa82` | کنترل جایگاه و Recipeهای حرفه‌ای در Inspector هدر |
| `1fc1bad` | «چیدمان و عرض صفحات» (استاندارد/عریض/تمام‌عرض/سفارشی) |
| `55ea89b` | بازگشت Inspector بعد از Undo/Redo |
| `87dd388` | رفع فوکوس صفحه‌کلید و دنبال‌کردن کلیک ناحیهٔ دیگر (یافتهٔ QA) |
| `ef5a500` | رفع opacity (یافتهٔ مقایسهٔ Full Suite) + بهبود پنل پایین |
| (آخرین) | مستندات: همین گزارش، راهنمای QA ویندوز، تصاویر WebP |

## ۱۰. راهنمای QA ویندوز
`WINDOWS_QA_GUIDE_STUDIO_20261101.md`

## ۱۱. Pre-Push Gate
| شرط | وضعیت |
|---|---|
| شاخه / مبنا | `claude/great-cori-6oox1r` روی `e7a4794…` (همان که Push شده و روی ویندوز QA شد)؛ ۷ Commit کد + ۱ مستندات جلوتر |
| Fast-forward خالص | بله (هیچ Rebase/Merge/Force؛ مبنا تغییر نکرده) |
| Remote | فقط `origin = https://github.com/manouchehr94-ux/Rastisi6-14040616` (بدون افزودن/تغییر/حذف Remote؛ `rastisi5` استفاده نشد) |
| Migration / Model / DB / Backfill | **هیچ** (`git diff e7a4794..HEAD` فایل `migrations/` یا `models.py` ندارد؛ کلیدهای Sparse در JSON موجود `appearance_config`) |
| Store‌های موجود | بدون Backfill؛ بدون کلید = رفتار و CSS قبلی (تست) |
| Production / Windows QA (۸۰۰۸) / RastiService | دست‌نخورده |
| درخواست خارجی / DNS / HTTPS / SMS / ردیابی / IndexNow | هیچ |
| فایل‌های ممنوع | `graphify-out/`، `.graphify-venv/`، `.env`، کلید/توکن، `db.sqlite3` در Commit نیستند (بررسی با `git ls-files`) |
| حجم تغییرات | ۲۱ فایل کد/تست (+۱۱۲۷/−۱۵) + ۱۸ تصویر WebP (~۵۲۸KB) + ۲ سند |
| تست‌ها | تست‌های جدید سبز؛ Full Suite: هیچ شکست جدیدی نسبت به Baseline (بند ۸.۴) |
| Chromium | Studio ۶۵ بررسی، ماتریس‌ها ۱٬۳۹۲ بارگذاری، بدون خطا (بند ۸.۲–۸.۳). Firefox اجرا نشد (در این محیط نصب نیست) |

**دستور Push پس از مجوز جداگانهٔ مالک** (اجرا نشده):
```bash
git push origin HEAD:refs/heads/feature/admin-panel-modernization-20261029
```
پیش‌شرط‌ها: `git rev-parse HEAD` برابر آخرین Commit همین شاخه؛ `git ls-remote origin refs/heads/feature/admin-panel-modernization-20261029` برابر `e7a479492b2b46016e89195ad52914163b4f94a7`؛ دقیقاً ۸ Commit جلوتر؛ بدون `--force`؛ شاخهٔ محلی `claude/great-cori-6oox1r` هرگز Push نشود.
