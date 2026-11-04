# گزارش — گالریِ ۱۹ قالبِ منتخب، هدر/فوترِ مستقل در Studio، ویترینِ ریسپانسیو و صفحهٔ یکپارچه‌سازی‌ها (۱۴۰۵/۰۸/۰۹)

> مبنا: `56f25ab43c3a0a37a2204f6f84b80befcfc30803` (= آخرین نسخهٔ منتقل‌شده به QA ویندوز؛ شاخهٔ Remote هم همین بود و قبل از شروع با `git ls-remote` تأیید شد).
> **Push / Merge / Deploy / Migration / Backfill انجام نشد.** همه‌چیز Commit محلی است. Windows QA، Production و RastiService دست‌نخورده‌اند؛ هیچ سرویس خارجی (Google/Bing/IndexNow) فعال و هیچ ردیابی روشن نشد.

## ۰. ممیزی فنی (پاسخ به ۸ پرسشِ M0)
1. **ثبت و بارگذاریِ قالب‌ها:** هر قالب یک `LayoutPresetDefinition` است که در import زمانِ `layout_preset_registry` ثبت می‌شود (`register_layout_preset`)؛ `list_ready_templates()` آخرین نسخهٔ هر «قالبِ آمادهٔ رسمی» (۶۳ عدد) را می‌دهد، `get_layout_preset_version(key, version)` هر نسخهٔ تاریخی را. هیچ جدول/Migrationی برای قالب‌ها نیست.
2. **تفاوت‌ها:** *Template (Ready Template)* = یک Preset با `is_ready_template=True` (چیدمانِ صفحات + ظاهر + هدر + فوتر + پالت + سنجه‌ها). *Preset* = همان ساختار (۶۸ ثبت؛ ۵ تای دیگر داخلی/ساختاری‌اند). *Section Recipe* = ورودی‌های `PresetSectionEntry` برای هر صفحه (نوع بخش + تنظیمات). *Header Variant* = یکی از ۲۵ طرحِ ثبت‌شده در `global_region_registry.GLOBAL_HEADER_REGION` (و ۱۹ طرحِ فوتر) که Preset فقط نامش را انتخاب می‌کند.
3. **مشترک / مختص:** رندر، CSS (`base.css`, `layout.css`, `product_card.css`, `storefront_builder.css`)، Rendererهای هدر/فوتر و کارت محصول همه مشترک‌اند؛ مختصِ قالب فقط داده است (Recipe، پالت، `content_width`، تراکم، نام Variant).
4. **Schema/Renderer هدر و فوتر:** `GlobalRegionDefinition` + `GlobalVariantDefinition` (قالبِ `partials/global_header/<variant>.html`)، تنظیمات در `header_config`/`footer_config` هر Draft؛ تغییر با میوتیشن‌های استانداردِ R4 `header.update` / `footer.update` (یک Revision، یک گامِ Undo/Redo، فقط Draft).
5. **Hero Stage:** بخشِ `hero_stage` با `header_mode` ∈ {`merged`, `overlay`, `independent`} — در حالتِ merged/overlay، **همان هدرِ سراسریِ فروشگاه** داخلِ بوم رندر می‌شود (`render_service.header_embedded_for`) و هدرِ پوسته حذف می‌گردد؛ پس هدرِ تکراری وجود ندارد.
6. **عرض و کارت:** `.wrap` در `base.css`/`layout.css`، متغیرِ `--sfb-content-width` از قالب؛ کارت در `catalog/partials/product_card.html` + `product_card.css` (یک کامپوننتِ مشترک برای فهرست/دسته/جست‌وجو/کالکشن/ردیف‌های خانه).
7. **اثرِ تغییرِ قالب:** قالب فقط Draft (و پس از انتشار، Published) را عوض می‌کند؛ صفحاتِ محصول/دسته/جست‌وجو/سبد همان Rendererِ مشترک را با Appearance/Header/Footerِ جدید می‌گیرند.
8. **تغییرِ مستقلِ هدر/فوتر:** بله، از قبل ممکن بود و اکنون در مسیرِ بوم کامل شد (§۴).

## ۱. علتِ واقعیِ مشکلاتِ عرض و کارتِ موبایل
اندازه‌گیریِ واقعی (Chromium، فروشگاهِ نمایشیِ ۱۰۰ کالا، ماتریسِ ۱۹ قالب × ۷ عرض × ۴ صفحه = ۵۳۲ بارگذاری):

| علت | شواهد | اصلاح (کامپوننتِ مشترک) |
|---|---|---|
| **`.wrap` تودرتو** — ۱۲ تمپلیتِ Section هنوز `<div class="wrap">` خودشان را دارند و داخلِ ظرفِ صفحه (`.wrap.sfb-preview-sections`) دوباره عرض + حاشیه + پدینگِ تراکم اعمال می‌شد | روی ۳۹۰px شبکهٔ ۲ستونه فقط ۲۵۰px می‌گرفت (کارت ۱۱۳px) ⇒ عنوان و «تومان» چندخطی؛ در دسکتاپ ~۱۰۰px از هر طرف هدر می‌رفت | یک توکنِ `--sfb-gutter` به‌ازای تراکم (در موبایل حداکثر ۱۲px) + قاعدهٔ یک‌باره `.wrap .wrap{width:auto;padding-inline:0…}` + محاسبهٔ Full-bleed با همان توکن |
| **عرضِ ثابتِ قالب** (مثلاً ۱۲۰۰px) روی مانیتور ۱۹۲۰px | ~۳۸۵px فضای مرده از هر طرف | یک تصمیمِ قابل‌استفادهٔ مجدد: `--sfb-page-width = max(عرضِ قالب, min(84vw, 1720px))` — هرگز باریک‌تر از قالب نمی‌شود |
| **پدینگِ ۱۸px بدنهٔ کارت در تراکمِ «باز»** حتی روی موبایل | ~۱۳۰px برای متن؛ قیمت و واحد جدا می‌شکستند (بلوکِ قیمت ۱۱۳px) | بدنهٔ کارت در موبایل `10px 10px 12px` با همان Specificity، قیمت+واحد `nowrap`، قیمتِ قبلی در خطِ جدا، نسبتِ تصویرِ عمودی ۴/۵ |
| **«نمای سریع»** روی لمس همیشه به‌شکلِ Pill پهن روی تصویر | تصویر را می‌پوشاند | روی لمس: دکمهٔ گردِ فقط‌آیکون ۳۲px زیرِ قلب، ناحیهٔ لمسِ ≥۴۴px، `aria-label` حفظ شد |
| **هدرِ «کارت شناور»** (`decor_sand_boutique`) | ۸ لینکِ هم‌ردیف در ۷۶۸–۱۴۴۰px صفحه را تا +۷۰۳px عریض می‌کرد | منو Wrap می‌شود و منوی همبرگری از ۱۰۰۰px شروع می‌شود |

**قبل/بعد روی دقیقاً همان ابزار:** بارگذاری‌های معیوب **۱۳۷ از ۵۳۲ → ۰**؛ قالب‌های دارای ایراد **۱۸ از ۱۹ → ۰**؛ کارت‌های با قیمتِ شکسته **۱٬۱۳۲ → ۰**؛ سرریزِ افقی **۱۲ → ۰**. روی ۳۹۰px عرضِ کارت **۱۱۳–۱۶۲ → ۱۶۷–۱۷۴px** و بیشینهٔ نسبتِ ارتفاع/عرضِ کارت **۳٫۴۶ → ۲٫۱۹**.

## ۲. ۱۹ قالبِ منتخب و شناسه‌های Registry
(نام‌ها دقیقاً با `label_fa` Registry تطبیق داده شده‌اند؛ حدس زده نشد — تست `test_the_nineteen_names_map_to_real_registry_keys_in_the_owners_order`. دو دامِ نام‌های مشابه: «آتلیه نوآر»=`editorial_jewelry` و «پالس نئون»=`dark_digital` در فهرست **نیستند**.)

| # | نام در گالری | شناسه Registry | نسخه | طرح هدر | هرو | پیش‌نمایش واقعی | قبل: بارهای معیوب / کارتِ با قیمتِ شکسته | بعد |
|---|---|---|---|---|---|---|---|---|
| 1 | کارگاه لاله | `warm_boutique` | v3 | `compact_menu` | معمولی | ✅ | 12/28 · 108 | 28/28 سالم |
| 2 | نسخه | `utility_catalog` | v2 | `marketplace_search` | معمولی | ✅ | 10/28 · 222 | 28/28 سالم |
| 3 | خیابان | `street_drop` | v1 | `promo_bar` | معمولی | ✅ | 2/28 · 4 | 28/28 سالم |
| 4 | گالری آب | `gallery_minimal` | v1 | `editorial_row` | معمولی | ✅ | 0/28 · 0 | 28/28 سالم |
| 5 | آچار | `tool_finder` | v1 | `marketplace_search` | معمولی | ✅ | 7/28 · 29 | 28/28 سالم |
| 6 | رایان | `rayan_tech` | v2 | `marketplace_search` | معمولی | ✅ | 7/28 · 29 | 28/28 سالم |
| 7 | زیبایی ارغوانی | `magenta_beauty_retail` | v1 | `beauty_search_nav` | معمولی | ✅ | 4/28 · 28 | 28/28 سالم |
| 8 | کاغذ پاستلی | `pastel_kawaii_stationery` | v1 | `kawaii_center` | معمولی | ✅ | 7/28 · 57 | 28/28 سالم |
| 9 | بوتیک شنی (دکور و لوازم خانه) | `decor_sand_boutique` | v1 | `floating_card` | معمولی | ✅ | 21/28 · 80 | 28/28 سالم |
| 10 | رز کرمی (آرایشی و بهداشتی) | `rose_beauty_store` | v1 | `beauty_search_nav` | معمولی | ✅ | 10/28 · 127 | 28/28 سالم |
| 11 | گالری فوشیا (زیبایی) | `pink_beauty_gallery` | v1 | `beauty_search_nav` | معمولی | ✅ | 7/28 · 52 | 28/28 سالم |
| 12 | هاب کمپینی عسلی (آرایشی) | `campaign_beauty_hub` | v1 | `promo_search_nav` | معمولی | ✅ | 3/28 · 26 | 28/28 سالم |
| 13 | هدیه و ماگ کاکائویی | `cocoa_gift_shop` | v1 | `chocolate_centered_search` | معمولی | ✅ | 8/28 · 68 | 28/28 سالم |
| 14 | فروشگاه دیجیتال نئونی | `neon_digital_store` | v1 | `marketplace_search_first` | معمولی | ✅ | 9/28 · 90 | 28/28 سالم |
| 15 | آتلیه دوپنل (هدر یکپارچه با دو تصویر) | `dual_atelier` | v1 | `atelier_nav` | **Hero Stage** | ✅ | 8/28 · 68 | 28/28 سالم |
| 16 | نشریهٔ نوآر (هیروی مجله‌ای با کارت محصول) | `editorial_noir` | v1 | `editorial_masthead` | **Hero Stage** | ✅ | 7/28 · 40 | 28/28 سالم |
| 17 | تجارت شیشه‌ای (هیرو با نوار دسته‌بندی) | `glass_commerce` | v1 | `centered_brand` | **Hero Stage** | ✅ | 4/28 · 28 | 28/28 سالم |
| 18 | بوم نامتقارن (هدر شناور روی تصویر) | `asymmetric_canvas` | v1 | `floating_compact` | **Hero Stage** | ✅ | 8/28 · 66 | 28/28 سالم |
| 19 | تحریر رنگی | `stationery_spectrum` | v2 | `stationery_search` | معمولی | ✅ | 3/28 · 10 | 28/28 سالم |

«۲۸ بارگذاری» = ۴ صفحه (خانه، فهرست محصولات، جزئیاتِ محصول، سبد) × ۷ عرض (۳۲۰/۳۶۰/۳۹۰/۷۶۸/۱۰۲۴/۱۴۴۰/۱۹۲۰). صفحات دیگر (دسته، جست‌وجو، فهرست و جزئیاتِ کالکشن، تسویه‌حساب، علاقه‌مندی‌ها) روی ۶ قالبِ نماینده (`dual_atelier`، `decor_sand_boutique`، `glass_commerce`، `tool_finder`، `warm_boutique`، `stationery_spectrum`) × ۷ عرض = ۲۵۲ بارگذاریِ دیگر بدونِ هیچ ایراد (سرریز ۰، قیمتِ شکسته ۰، خطای JS ۰، همه HTTP 200). پیش‌نمایش‌های واقعیِ ۱۳ قالب (که فقط SVGِ عمومی داشتند) از روی رندرِ واقعی ساخته و Commit شدند (۱۹/۱۹ تازه، ۱۹ تصویرِ متمایز).

## ۳. سیاستِ پنهان‌سازیِ سایر قالب‌ها
* **یک منبعِ مشترک:** `apps/storefront_builder/template_gallery_policy.py` (`SELECTABLE_TEMPLATE_KEYS` به ترتیبِ فهرستِ مالک) ⇒ `layout_preset_registry.list_selectable_templates()` ⇒ گالریِ Studio، جست‌وجو، شمارنده‌ها، Context، گالریِ Onboarding. هیچ `display:none` و هیچ فیلترِ CSS/JS نیست.
* **چیزی حذف نشد:** هر ۶۳ قالب Registry/Recipe/تصویر/دیتابیس سر جایشان‌اند؛ `list_ready_templates()` بدونِ تغییر؛ مهاجرتی نیست.
* **فروشگاهی که قالبِ پنهان دارد:** هویتش حفظ می‌شود (اعمال‌شده، قابل‌ویرایش/پیش‌نمایش/انتشار) و در گالری به‌صورت کارتِ «قالب فعلی» سنجاق می‌شود (برچسبِ `is_hidden_current`)؛ هرگز خودکار جایگزین نمی‌شود.
* **اجرای سمتِ سرور:** نقاطِ ورودیِ انتخابِ فروشنده (سوئیچِ Studio، `appearance.template.apply` از Studio، فرمِ preset داشبورد، `select_ready_template` در Onboarding) قالبِ پنهان را با `template_not_selectable` / `template_not_available` رد می‌کنند؛ اعمالِ دوبارهٔ قالبِ خودِ Draft مجاز است. خودِ موتور (`apply_mutation`، `switch_template`، دستورهای ترمیم/پیش‌نمایش) عمداً بدون قید است.
* **بازگرداندنِ آینده بدون Migration:** افزودنِ کلید به tuple، یا `RASTISI_TEMPLATE_GALLERY_RESTRICTED=0` در محیط ⇒ همهٔ قالب‌ها دوباره پیشنهاد می‌شوند.

## ۴. تغییرِ مستقلِ هدر و فوتر در Studio
* **دکمهٔ «فقط هدرِ این قالب» از گالری حذف شد** (میوتیشنِ `header.apply_template` و API باقی ماند). دکمهٔ «فقط هیرو» دست‌نخورده ماند؛ اگر مالک خواهدش حذف هم همین‌قدر ساده است (تصمیمِ محصولی — §۱۱).
* **جریان:** کلیک روی هدر/فوتر در بوم ⇒ پنلِ «طراحی سراسری» روی بخشِ سربرگ/فوتر باز می‌شود (`rsGlobalHeader`/`rsGlobalFooter`) ⇒ انتخابگرِ «نوع هدر» (۲۵ طرحِ ثبت‌شده)/«نوع فوتر» (۱۹ طرح) + کلیدها + ابعاد/رنگ ⇒ پیش‌نمایشِ فوری بدونِ Publish ⇒ Undo/Redo. فقط همان بخش تغییر می‌کند، نه قالبِ کامل.
* **نقصی که واقعاً وجود داشت و اصلاح شد:** در قالب‌هایی که هدر داخلِ Hero Stage است، کلیک روی **لینکِ** هدر (لوگو/منو) بخشِ هرو را انتخاب می‌کرد و انتخابگرِ هدر باز نمی‌شد؛ علت: Handlerِ پنجره‌ایِ Composer هر لینکِ داخلِ Section را به انتخابِ همان Section تبدیل می‌کند. اکنون هر کلیک روی `.hs-header` انتخابگرِ هدر را باز می‌کند و `isInteractive` دیگر آن را دور نمی‌زند.
* **Hero Stage / هدر یکپارچه:** روی هر چهار قالب (`dual_atelier`، `editorial_noir`، `glass_commerce`، `asymmetric_canvas`) تست و QAِ مرورگر: تغییرِ طرحِ هدر ⇒ هدرِ تکراری نمی‌شود (۱ هدر)، هرو/تصاویر/متن/تنظیماتِ Stage/منوها/لوگو/تماس/فوتر دست‌نخورده، هویتِ قالب عوض نمی‌شود، دقیقاً یک Revision، Undo/Redo درست، Draft-only تا Publish، Tenant Isolation (Draftِ فروشگاهِ دیگر دست‌نخورده).
* **فوتر:** زیرساختِ واقعی (`footer.update` + ۱۹ طرح) از قبل کامل بود؛ نمایشی/جعلی چیزی ساخته نشد؛ همین قراردادها برایش تست شد.

## ۵. وضعیتِ Hero Stage و هدر یکپارچه
حالت‌های `merged`/`overlay`/`independent` سالم‌اند و هدرِ سراسری یک‌بار رندر می‌شود. ماتریسِ ریسپانسیو روی هر ۴ قالبِ Stage در ۳۲۰–۱۹۲۰px بدونِ سرریز؛ مرورگر: هدر یکپارچه + کلیک + تغییر + Undo/Redo ✅.

## ۶. وضعیتِ Responsive
۱۹ قالب × ۷ عرض (۳۲۰، ۳۶۰، ۳۹۰، ۷۶۸، ۱۰۲۴، ۱۴۴۰، ۱۹۲۰) × (خانه، فهرست محصولات، جزئیات، سبد) = **۵۳۲ بارگذاریِ بدونِ ایراد**: سرریزِ افقی ۰، قیمتِ شکسته ۰، خطای JS ۰، وضعیتِ HTTP ≥۵۰۰ ۰. صفحاتِ دیگر (دسته، جست‌وجو، کالکشن، تسویه‌حساب، علاقه‌مندی‌ها) روی ۶ قالبِ نماینده بدونِ ایراد. Studio (گالری/انتخابگر) در ۳۹۰/۷۶۸/۱۰۲۴/۱۴۴۰ بدونِ سرریز، ۱۹ کارت. هیچ Patchِ CSSِ مختصِ قالب ساخته نشد (فقط یک قاعدهٔ اختصاصیِ `floating_card` که ریشه‌اش یک Bug در Recipe/CSSِ همان هدر بود).

## ۷. اسکرین‌شاتِ قبل/بعد
`docs/admin-modernization/screenshots_templates_20261031/` (WebP فشرده، ≈۴۱۰KB): `products_mobile_390_{warm_boutique,decor_sand_boutique,dual_atelier,glass_commerce}`، `products_desktop_1440_dual_atelier`، `home_mobile_390_decor_sand_boutique`، `integrations_{390,1440}`، `gallery_19_real_previews`، `studio_gallery_19_templates`، `studio_header_picker_after_click`، `studio_header_changed_preview`، `studio_footer_changed_preview`.

## ۸. صفحهٔ Integrations
خلاصهٔ وضعیت (تیتر + «قدم بعدی» یا «فعلاً نیازی به انجام کاری از طرف شما نیست.» + سه شمارنده) و پنج گروهِ `<details>`: **A** دیده‌شدن در گوگل و جست‌وجوی هوشمند (ردیف‌های قابل‌اقدام باز؛ نقشهٔ سایت/robots/Canonical/JSON-LD/سیاستِ ربات‌های AI/IndexNow زیرِ «جزئیات فنی»)، **B** آمار و بازدیدکنندگان (GA4/GTM/Meta Pixel — ردیابی همچنان پیش‌فرض خاموش، هیچ Consent دور زده نشد)، **C** ابزارهای فروش و مقایسهٔ قیمت (ترب)، **D** نمادها و اعتماد (اینماد؛ «شناسهٔ ذخیره‌شده» ≠ «تأییدِ واقعی»)، **E** امکانات آینده (Search Console، Bing، Merchant، فیدِ ترب — بدونِ فرم و بدونِ ادعای اتصال). ارتفاعِ صفحه ≈۴۵٪ کمتر (۱۹۴۵→۱۰۷۳px در دسکتاپ، ۲۵۱۵→۱۴۰۳px در موبایل). Backend دست‌نخورده؛ Tenant Isolation تست شد؛ هیچ ادعای رتبه/ایندکس. یک باگِ خودم (کامنتِ چندخطیِ `{# #}` که به‌صورت متن نمایش می‌یافت) در QAِ مرورگر دیده و با تستِ ردیاب اصلاح شد.

## ۹. Commitها و فایل‌ها (روی `56f25ab`)
| Commit | محتوا |
|---|---|
| `dd73192` | **Integrations** (M6، Commitِ مستقل): خلاصه + پنج گروه، جزئیاتِ فنی بسته، وضعیتِ صادقانه |
| `c7d27c9` | **M1+M2:** سیاستِ ۱۹ قالب (منبعِ مشترک + اجرای سمتِ سرور)، حذفِ «فقط هدرِ این قالب»، کلیکِ هدرِ یکپارچه ⇒ انتخابگرِ هدر، تست‌ها |
| `76bcba3` | **M3+M4+M5:** `.wrap` تودرتو، توکنِ Gutter، عرضِ صفحه، کارتِ فشرده در موبایل، «نمای سریع»، هدرِ کارت‌شناور — CSS مشترک + تستِ قراردادها |
| `1d45758` | **پیش‌نمایش‌های واقعی** ۱۳ قالب + اصلاحِ یافتنِ Chromium در دستورِ Capture |
| `1d036dd` | رفعِ نشتِ کامنتِ چندخطیِ `{# #}` در Integrations + تستِ ردیاب |
| `89e1c0c` | رفعِ نگارشِ پرانتز در RTL |
| (Commitِ مستندات) | این گزارش، راهنمای QA ویندوز، اسکرین‌شات‌ها |

فایل‌های تغییرکرده (`git diff --stat 56f25ab..HEAD`: ۷۰ فایل، +۱٬۱۴۷/−۱۰۱ — بیشترش ۲۶ فایل WebP/JSON پیش‌نمایش و تست‌ها): کد — `template_gallery_policy.py` (جدید)، `layout_preset_registry.py`، `services/{ready_template_card_service,store_template_service,r4_mutation_service}.py`، `r4_views.py`، `views.py`، `shop_core/settings.py`، `static/storefront_builder/{r4_studio,r4_composer}.js`، `templates/storefront_builder/preview.html`، CSS مشترک (`base.css`, `layout.css`, `product_card.css`, `storefront_builder.css`)، `dashboard/{views.py, services/search_visibility_service.py, templates/.../settings_integrations.html, static/css/admin_ui.css}`. تست — ۳ فایلِ جدید + یک کلاسِ جدید در `test_integrations_visibility_page` + به‌روزرسانیِ ده‌ها فایلِ موجود (هیچ تستی حذف نشد؛ تست‌های قراردادِ قدیمیِ گالری مطابقِ تصمیمِ مالک بازنویسی شدند).

## ۱۰. تست‌ها و مقایسه با Baseline
| اجرا | HEAD | تعداد | Failure | Error | Skip | نتیجه |
|---|---|---|---|---|---|---|
| Full (Python 3.11، `--parallel 4`) | `89e1c0c` | ۱۲٬۰۹۱ | ۲۹ | ۴ | ۲۳۷ | **۳۳ شناسه — همه در Baseline، ۰ شکستِ جدید** |

* مبنا: `TEST_RECONCILIATION_20261029.md` (۳۸ شناسه). **۵ شناسهٔ Baseline با این کار سبز شد** (قراردادِ گالری ۵۰→۱۹ و پیش‌نمایشِ واقعی: `test_card_screenshots_use_the_existing_preview_authority`، `test_gallery_exposes_exactly_the_canonical_current_ready_templates`، `test_every_card_has_a_persian_name_a_lazy_preview_and_a_large_view_link`، `test_search_is_client_side_and_a_get_never_mutates`، `test_every_card_has_an_explicit_choose_affordance_and_a_sample_content_label`). سه شناسهٔ دیگر (`test_export_views…`، `test_product_image_views…reorders`، `test_views…sidebar…`) در این اجرا گذشتند؛ این‌ها وابسته به ترتیب/محیط‌اند و به این کار نسبت داده نمی‌شوند.
* **مسیرِ اشکال‌یابی (صادقانه):** نخستین تلاش، قفلِ «قالبِ پنهان» را داخلِ خودِ موتور گذاشته بود و ۱۱۷ تستِ موتور را شکست؛ تصمیم عوض شد: قفل فقط در نقاطِ ورودیِ انتخابِ فروشنده است و Suiteهای موتور با `override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False)` صریحاً از آن معاف شده‌اند (ماهیتِ تست‌ها «سیاستِ گالری» نیست). بقیهٔ شکست‌ها (۴۹) یکی‌یکی بررسی و اصلاح شد؛ ران‌های میانی Baselineِ سبز را نشان می‌داد.
* تازه: `test_template_gallery_policy` (۱۴)، `test_studio_header_footer_independence` (۸)، `test_storefront_width_and_card_contracts` (۹)، `IntegrationsFiveGroupStructureTests` (۹، شاملِ ردیابِ نشتِ کامنت)؛ همه سبز.
* **QA مرورگر (Chromium):** ماتریسِ ۵۳۲ + ۲۵۲ بارگذاری ✅؛ Studio ۲۶ بررسی ✅ (۱۹ کارت، بدونِ دکمهٔ «فقط هدر»، جست‌وجو، کلیکِ لینکِ هدرِ یکپارچه، تغییر، Undo/Redo، فوتر، بدونِ خطای JS)؛ Integrations در ۳۹۰/۷۶۸/۱۴۴۰ بدونِ سرریز. **Firefox و PostgreSQL اجرا نشد.**

## ۱۱. محدودیت‌های باقی‌مانده / تصمیم‌های محصولی
* **Firefox** در این محیط نصب نیست (فقط Chromium) ⇒ تست نشد. **PostgreSQL** اجرا نشد.
* **انتخابگرِ هدر/فوتر یک `<select>` با نامِ طرح است**، نه کارت‌های تصویری؛ «مشاهدهٔ طرح‌ها» = فهرستِ نام‌دارِ ۲۵/۱۹ طرح. نسخهٔ بصری (پیش‌نمایشِ تصویریِ هر طرح) نیازمندِ ساختِ ۴۴ تصویرِ مرجع است و انجام نشد.
* دکمهٔ «فقط هیرو» در گالری باقی است (فقط «فقط هدر» خواسته شده بود).
* ۱۲ تمپلیتِ Section هنوز `<div class="wrap">` داخلی دارند؛ CSS آن‌ها را خنثی می‌کند ولی پاک‌سازیِ مارک‌آپ (کاری ایمن‌تر برای یک Task جدا) انجام نشد.
* چک‌اوتِ کامل (پرداخت) و سبدِ پر در مرورگر فقط تا حدِ بارگذاری/Redirect بررسی شد (حالتِ سبدِ خالی/نیازِ ورود)؛ جریانِ پرداخت واقعی آزموده نشد (ممنوع).
* رگرسیونِ احتمالیِ ظاهری در فروشگاه‌های **زنده**ی با تراکمِ «باز» یا `content_width` باریک: چون عرضِ صفحه روی مانیتورهای عریض حداکثر تا `84vw` رشد می‌کند و حاشیهٔ موبایل کمتر شد، ظاهرِ همهٔ فروشگاه‌ها (نه فقط ۱۹ قالب) کمی تغییر می‌کند؛ پیش از Push در QA ویندوز با چشم بررسی شود. مقدارِ سقف قابل‌تنظیم است (`--sfb-page-width-cap`).
* Windows QA: پیش‌نمایش‌های واقعی با Chromium این محیط ساخته شد (۱۴۴۰×۱۱۰۰)؛ اگر فونت/رندرِ ویندوز فرق کند ظاهرِ تصویرِ Gallery ریزه‌کاری‌هایی دارد.

## ۱۲. راهنمای QA ویندوز
→ `docs/admin-modernization/WINDOWS_QA_GUIDE_TEMPLATES_20261031.md`

## ۱۳. Pre-Push Gate
**نتیجه: آمادهٔ بررسیِ شما؛ Push انجام نشده است.**

| شرط | مقدار |
|---|---|
| Remote | `origin` = `https://github.com/manouchehr94-ux/Rastisi6-14040616` (بدونِ تغییر) |
| SHA ریموتِ شاخهٔ `feature/admin-panel-modernization-20261029` (پایانِ کار) | `56f25ab43c3a0a37a2204f6f84b80befcfc30803` = مبنا |
| آخرین کامیتِ کدِ تست‌شده (Full Suite) | `89e1c0c99503fdd2b1cb1defa8bc4647b6c48698`؛ کامیت(های) پس از آن **فقط مستندات و اسکرین‌شات** |
| HEAD / تعداد کامیت روی مبنا | شاخهٔ محلی `claude/great-cori-6oox1r`؛ SHAِ نهایی در پاسخِ ارائه‌شده؛ ۶ کامیتِ کد + ۱ کامیتِ مستندات = ۷ (همه Fast-forward روی مبنا) |
| Working tree | تمیز پس از کامیتِ مستندات |
| Migration / مدل | **هیچ** (`makemigrations --check`: No changes detected؛ فایلِ Migration یا `models.py` در Diff نیست) |
| فایل‌های ممنوع | بدونِ `graphify-out/`، `.graphify-venv/`، DB، Media، Secret، `.env`؛ اسکنِ الگوی Secret در Diff خالی |
| دارایی‌های ثابتِ کامیت‌شده | ۱۳ WebP پیش‌نمایشِ قالب (≈۰٫۶MB، همان نوعِ دارایی که برای ۶ قالبِ دیگر از قبل Commit است) + ۱۳ WebP اسکرین‌شاتِ مستندات (≈۰٫۴MB) |
| تست | Full: ۳۳ شناسه همه در Baseline، ۰ جدید؛ ۵ شناسهٔ Baseline سبز شد |
| محدودیت‌های اجرا (صریح) | Firefox و PostgreSQL اجرا نشد؛ جریانِ پرداخت/پیامکِ واقعی آزموده نشد؛ Full Suite با Python 3.11 |
| تأثیرِ ظاهریِ گسترده | CSSِ مشترک است ⇒ ظاهرِ **همهٔ** فروشگاه‌ها (نه فقط ۱۹ قالب) در عرضِ صفحه/کارتِ موبایل تغییر می‌کند؛ پیش از Push یک بازبینیِ چشمیِ شما روی ویندوز توصیه می‌شود (§۱۱) |

درخواستِ مجوزِ Push را جدا و شرطی (Remote/SHA/تعداد کامیت/عدم Migration) بدهید؛ پیش از Push همین شرط‌ها را دوباره بررسی می‌کنم.
