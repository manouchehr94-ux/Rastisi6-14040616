# سند مرجع بازسازی شش فروشگاه برای موتور RastiSi R4 / V5

**نسخه سند:** 1.0 — ۲۲ اکتبر ۲۰۲۶  
**هدف:** مشخصات طراحی، ساختار و رفتار شش سایت مرجع، به‌همراه ممیزی قابلیت‌های موجود و فاصله‌ها در موتور R4، با قابلیت تحویل مستقل به Claude Code بدون ارسال ZIP یا تصاویر سایت‌ها.  
**شاخه کد بررسی‌شده:** `feature/v5-design-studio-20261020` در `manouchehr94-ux/Rastisi6-14040616`؛ SHA مشاهده‌شده در زمان بررسی `3a746ce82a8cd44d55ce4ee5002ddaac1ab34ddd`. این SHA باید در محیط اجرایی دوباره سنجیده شود.  
**احتیاط:** وضعیت «وجود در کد» به معنی PASS شدن تست واقعی Windows/Browser نیست. در این بررسی هیچ تغییری در ریپو، دیتابیس یا شاخه‌ها انجام نشده و مجموعه تست‌ها اجرا نشده‌اند.

## 0) دامنه و اعتبار شواهد

برای هر مرجع ZIP صفحه اصلی و چهار تصویر بلند بررسی شد: HOME دسکتاپ، PRODUCT دسکتاپ، PRODUCT موبایل، HOME موبایل. ۲۴ اسکرین‌شات وجود دارد. HTML ذخیره‌شده *عمدتاً صفحه اصلی* است؛ برای PDP عمده استنباط از تصویر انجام شده، نه DOM صفحه محصول. شش سایت فارسی/راست‌به‌چپ‌اند. اسکرین‌شات‌ها به عرض‌های تصویری ۱۸۴۷ یا ۱۸۵۸ (دسکتاپ)، و ۴۸۷ یا ۵۰۳ پیکسل (موبایل) ذخیره شده‌اند. این ابعاد، اندازه خود تصویرند؛ لزوماً معادل `CSS viewport width` نیستند. برخی تنظیمات توسط ابزار capture ممکن است ظاهر اسلایدر/آیکن را با وضعیت اصلی متفاوت کرده باشند.

**درجه اطمینان:** `C` یعنی در CSS/HTML نسخه ذخیره‌شده قابل استناد؛ `V` یعنی در تصویر دیده شده ولی مقدار دقیق CSS مشخص نیست؛ `T` یعنی محدوده عددی هدف *پیشنهادی برای بازآفرینی*، نه مقدار استخراج‌شده؛ `U` یعنی مدرک کافی وجود ندارد و باید از مرجع زنده/DevTools به‌دست آید. عددهای `T` نباید به Claude به‌عنوان measured/exact معرفی شوند. برای رنگ، کد hex تنها زمانی `C` محسوب می‌شود که به‌عنوان متغیر/قاعده مرتبط استخراج شده باشد؛ شمارش فراوانی رنگ در تمام CSS (به‌ویژه کتابخانه‌ها و Elementor) مدرک فعال‌بودن آن در صفحه نیست.

**قید حقوقی و محتوایی:** فقط از ساختار و زبان طراحی الهام گرفته شود؛ نام، لوگو، بنر، تصویر محصول، متن ویژه و کپی‌رایت منابع ثالث داخل قالب عمومی قرار نگیرد. تصاویر قالب واقعی باید متعلق به تاجر/با مجوز، و داده‌ها scoped به همان Store باشند.

## 1) قرارداد طراحی مشترک برای همه شش مرجع

### 1.1 ساختار لایه‌های صفحه

```
STORE DESIGN (Draft/Published per Store)
 ├─ Foundation: palette, color roles, typography, spacing, radius, elevation, breakpoints
 ├─ Global Shell: announcement/topbar | header | nav/mega menu | mobile menu | bottom dock | footer
 ├─ HOME: sortable sections composed of Container > Cell > Block/Section
 │   ├─ hero/banner; image slider; campaign/mosaic; category/story/brand shortcuts
 │   ├─ product shelves; product collections; editorial split; testimonial/trust; blog/FAQ
 │   └─ newsletter/social/SEO content
 ├─ PDP: breadcrumbs | product gallery | buying panel | variants | purchase actions |
 │        shipping/trust/promises | rich details | comments/reviews | FAQs | related items
 ├─ COLLECTION/LISTING/SEARCH: category intro | filters | sort | product list | pagination
 ├─ CART/CHECKOUT/ACCOUNT: same storefront appearance contract where theming is supported
 └─ Shared utilities: sticky elements, drawers, floating contact/help, compare, wishlist
```

### 1.2 اجزای مشترک قابل تنظیم (نه CSS کپی شده از سایت)

- **Global tokens:** `surface.canvas`, `surface.default`, `surface.raised`, `surface.inverse`, `border.subtle`, `border.strong`, `text.primary`, `text.muted`, `text.inverse`, `action.primary`, `action.primary.hover`, `action.secondary`, `brand.accent`, `price.current`, `price.previous`, `sale.badge`, `state.success/warning/danger`, `focus.ring`, `shadow.soft/medium`, `radius.card/button/pill`, `space.1..N`, `font.body/heading/price`, `z.header/popover/sticky`; فقط اگر در سامانه موجود R4 معادل ندارد و پس از ارزیابی معماری، تعریف شود.
- **هر ناحیه Global:** ارتفاع/عرض، ترازبندی، رنگ از semantic roles، تعداد ردیف، لوگو، جست‌وجو، حساب، سبد، ناوبری، sticky، حالت موبایل/RTL، کنتراست و focus.
- **Container/Cell:** max-width و full-bleed، Grid/Flex، ستون/ردیف/نسبت، gap، padding، background، stacking در سه breakpoint، محتوای اختیاری، مستقل‌بودن هر Cell، ترتیب موبایل.
- **Section:** منبع داده، ترتیب کالا/دسته، شمار نمایش، grid vs carousel، heading/action، رسانه و نسبت تصویر، border/shadow/radius، responsive visibility، empty state، selected variant و Inspector.
- **Product card:** ratio تصویر و fit، نام/برند، چندخطی و ellipsis، قیمت جاری/قبلی، تخفیف، ستاره، وضعیت موجودی، badges، wishlist/compare/quick action، نمایش hover/keyboard/focus، اندازه عمودی در گرید، نوع checkout.
- **PDP:** کنترل‌های ساختاری *درون بلوک اصلی واحد* بدون شکستن مالکیت قیمت/تنوع/سبد؛ نسبت عکس/پنل در دسکتاپ؛ استک در موبایل؛ گالری تصاویر و thumbnails؛ sticky purchase؛ variants با انتخاب معتبر و نمایش قیمت/موجودی؛ tabs/accordion؛ اطلاعات/ویژگی‌ها/ریویو/FAQ؛ سفارش‌گذاری ایمن.
- **Mobile-first:** یک breakpoint کافی نیست؛ برای ۳۲۰/۳۷۵/۳۹۰/۴۳۰/۷۶۸/۱۰۲۴/۱۳۶۶/۱۴۴۰ و RTL بررسی شود. عرض عناصر تعاملی، اسکرول افقی، bottom dock و safe-area، جایگاه menu/search، ترتیب تصویری و sticky purchase آزمایش شوند.
- **No duplicated engines:** قالب فقط recipe از رجیستری عمومی با مقادیر پیش‌فرض مجاز است. هیچ `if (template == ...)` در renderer محوری، renderer مجزا، دیتابیس موازی یا Mutation جدید خارج از مسیر مرکزی به ازای هر سایت ساخته نشود.

### 1.3 مقیاس‌های پیشنهادی برای معادل‌سازی (T، مقادیر استخراج‌شده واقعی نیست)

- **Desktop content width:** ۱۲۰۰ تا ۱۳۲۰ پیکسل برای سایت‌های روشن، ۱۳۲۰ برای ژیمون و ۱۲۰۰ برای دیزه؛ تنظیم موجود R4 باید اول آزموده شود.
- **Gutters:** ۲۴–۴۰ دسکتاپ؛ ۱۲–۲۰ موبایل. **Vertical rhythm:** ۳۲–۸۰ دسکتاپ؛ ۲۰–۴۸ موبایل.
- **Body:** ۱۳–۱۶px؛ captions ۱۰–۱۳px؛ section heading ۱۸–۲۶px؛ PDP title ۲۰–۳۰px؛ hero heading ۲۸–۵۲px desktop / ۲۰–۳۶px mobile، بسته به هویت.
- **Card radius:** ۴–۱۶px بسته به قالب؛ pill chips ۹۹۹px. **Cards grid:** دسکتاپ عموماً ۴–۵، موبایل ۲؛ دیزه ۴/۲؛ سایت‌های شلوغ گاهی carousel با محصول نیمه‌نمایان.
- **Image fit:** کالاهای بسته‌بندی/لوازم آرایشی `contain`، عکس lifestyle/دکور `cover`؛ قابلیت باید per-section/per-product-card قابل انتخاب باشد.
- **Contrast:** متن عادی >=4.5:1، متن بزرگ >=3:1 در اجزایی که مشمول WCAG هستند؛ badges/button text باید برای همه پالت‌ها و حالت‌ها خوانا باشند.

---

# 2) سایت A — لیلیکا | `lilikacosmetics.zip`

**حوزه:** آرایشی/بهداشتی، هویت زنانه مینیمال، صورتی چرک/رزگلد، کرم و زغالی. **منبع:** ۱ فایل home HTML، ۴ اسکرین‌شات؛ اسکرین PDP مربوط به «ریمل حجم‌دهنده و بلندکننده بیولیس».

### 2.1 هویت، رنگ، فونت

- `C` متغیر مؤثر پایه Woodmart: `--wd-primary-color: rgb(175,114,109)` = **#AF726D**. `--wd-text-font` و `--wd-title-font`: `iranyekan, sans-serif`. CSS افزوده‌شده شامل font-face برای `dana`, `IRANSansx`, `YekanBakh`, `shabnam` نیز هست؛ این‌ها به معنی فعال‌بودن هم‌زمان نیست.
- `V` سطح پایه شیری/صورتی بسیار روشن؛ نوارهای اطلاعاتی صورتی مات؛ متن زغالی؛ هدر و فوتر به‌ظاهر تیره؛ دکمه‌های خرید رزگلد. `T` palette پیشنهادی برای ساخت بدون دارایی سایت: `canvas=#F9F0ED`, `surface=#FFFFFF`, `soft=#EBC9C3`, `accent=#AF726D`, `ink=#302E2D`, `footer=#333333`. hexهایی که با T آمده‌اند هدف طراحی‌اند، نه exact extraction.
- `T` فونت UI: iranyekan یا نزدیک‌ترین فونت مجاز موتور؛ body ۱۳–۱۴، کارت ۱۲–۱۳، h2 ۲۰–۲۴، hero copy ۲۴–۳۶، CTA ۱۲–۱۴px. وزن ۴۰۰ متن/۶۰۰–۷۰۰ تیتر؛ کارت با گوشه‌های کم‌گرد و سایه ظریف.

### 2.2 صفحه اصلی دسکتاپ — ترتیب و مشخصات جزءبه‌جزء

1. **هدر دو‌سطحی:** ردیف روشن شامل لوگوی دست‌نویس/لوکس سمت راست در RTL، جست‌وجوی میانی، حساب/مقایسه/علاقه‌مندی/سبد و منوی مجله؛ ردیف ناوبری ذغالی با دسته‌بندی/منو. `T` ارتفاع ترکیبی ۹۰–۱۴۰px؛ جست‌وجو full input با گوشه متوسط؛ موبایل تبدیل به لوگوی مرکزی و آیکن‌های کناری.
2. **Hero سرتاسری تبلیغاتی:** تصویر کمپین آرایشی با تایپوگرافی بزرگ و متن رنگی روی رسانه؛ روی دسکتاپ عریض (تقریباً ۲.۵:۱ در قاب نمایان)، روی موبایل crop/reflow متفاوت. قابلیت لازم: cover/position focal point مستقل برای موبایل، optional overlay.
3. **نوار مزیت‌های فروشگاه** روی سطح صورتی: ۳ تا ۴ آیکن ظریف خطی با تیتر/توضیح، فاصله یکنواخت؛ mobile در دو ستون/ردیف.
4. **کاروسل تازه‌ترین محصولات:** عنوان RTL، تب/فیلتر نزدیک heading، کارت‌های تمیز سفید با عکس کالای isolated، نمایش قیمت و نام، arrow/dot navigation؛ `T` دسکتاپ ۴–۵ کارت، موبایل ۲ با حفظ اسکرول.
5. **نوار مزیت دوم / pictogram strip:** چهار آیکن زنانه با توضیح کوتاه روی سطح رز روشن؛ در عکس موبایل به ۲×۲ تبدیل می‌شود.
6. **بخش محصول/کالکشن منتخب دیگر:** کاروسل کالاهای آرایشی، با عنوان/فلش/تب.
7. **CTA مشاوره/پاسخ‌گویی:** نوار تیره با متن سفید و گرادیان/رز، button تک در سمت روبرو.
8. **داستان برند/تصویر + متن:** تصویری مربعی/لنداسکیپ با متن فروشگاه/خدمات و ۳–۴ آیتم امتیاز در مجاورت؛ موبایل استک.
9. **محتوای آموزشی/مجله:** کارت‌های تصویری editorial روی سطح تیره (عکس بزرگ بالا، caption سفید پایین).
10. **ردیف محصولات دیگر** و سپس **فوتر زغالی** با لوگو، متن معرفی، اطلاعات تماس، لینک‌ها، نشان اعتماد و social.

### 2.3 صفحه محصول — دسکتاپ و موبایل

- **Desktop PDP:** breadcrumb بالای main؛ ستون راست/چپ به‌صورت RTL تصویر اصلی بلند/پرتره سفید با thumbnails پایین در یک طرف، پنل خرید شامل نام چندخطی، برند، قیمت، وضعیت موجودی، تعداد، CTA «افزودن به سبد» رزگلد، wishlist/compare/share؛ description/reviews پایین؛ related carousel؛ فوتر ثابت از shell.
- **Mobile PDP:** تصویر بزرگ تقریباً تمام عرض، thumbnails افقی زیر تصویر، آیکن زوم، strip کوچک از لینک‌های shop attributes، عنوان و قیمت و کنترل qty سپس CTA. بخش متن/اطلاعات و **فرم دیدگاه** طولانی، محصولات مشابه دو‌ستونه؛ در screenshot شواهدی از پنل خرید sticky ثابت دیده نشد (`U`).
- **کارت‌ها:** عکس isolated سفید/نزدیک سفید با `contain`، padding بالا، عنوان ۱–۲ خط، قیمت کوتاه، border خیلی ظریف؛ قلب/hover actions در صورت فعال‌بودن داده واقعی. `T` radius ۲–۸px و ratio عکس ۱:۱ تا ۴:۵.
- **الزامات خاص:** دو نوع نوار اعتماد/خدمات، آیکن‌های خطی هماهنگ با پالت، بنر سؤال/مشاوره، responsive crop مستقل، فرم نظر و نمایش نظرات، مستقل‌بودن نوارها.

### 2.4 نقشه R4 و ریسک

- **قابل پوشش با موجودی کد:** `hero_banner` (beauty_editorial/overlay)، `trust_features`، `product_section`، `image_text`، `blog_posts`، `related_products`، `product_description`، header/footer variants و theme palette.
- **نیازمند اثبات یا تکمیل:** Inspector برای carousel tabs و نمایش آیکن مزایا؛ mobile image focal point؛ انعطاف ساختار PDP و فرم بازخورد؛ سازگاری رنگ icon/caption با palette؛ قابلیت ویرایش نوار داستان/مشاوره به‌صورت عمومی.
- **عدم مجوز توسعه خاص سایت:** logo/brand images واقعی لیلیکا و متن اختصاصی نباید وارد recipe عمومی شود.

---

# 3) سایت B — لیلیوم گالری | `lilium-gallery.zip`

**حوزه:** زیبایی/کالکشن، هویت صورتی پررنگ و سفید، تاکیدی شبیه boutique market؛ PDP نمونه «پک آرایشی ماتریکس شیگلم».

### 3.1 هویت، رنگ، فونت

- `C` CSS پرکاربرد و مرتبط با استایل اختصاصی: **#DB2777** (pink-600)، `#BE185D` (hover/dark pink)، `#FDF2F8` (pink surface)، `#0F172A` (ink)، `#94A3B8` و `#E2E8F0` (secondary/border). این‌ها در استایل‌های سایت ذخیره‌شده حضور پررنگ دارند.
- `C` font-face برای **Vazirmatn** و `fontsans` موجود؛ انتخاب قطعی فونت هر عنصر نیازمند computed-style مرورگر است (`U`). `T`: Vazirmatn برای ساخت قابل‌ویرایش، body ۱۳–۱۴، heading ۱۷–۲۲، PDP title ۲۲–۲۸، برچسب ۱۰–۱۲؛ دکمه ۱۲–۱۴.
- `V` background سفید گسترده، card pink border/hover، accent بسیار اشباع، فوتر سفید با نوار magenta، chips و نشان‌های فروش صورتی.

### 3.2 صفحه اصلی

1. **هدر مینیمال دو سطحی:** ردیف روشن با لوگوی متنی/نماد صورتی در راست، جست‌وجو، حساب/علاقه‌مندی/سبد؛ نوار ناوبری صورتی ممتد در پایین؛ دسکتاپ nav افقی با submenu، موبایل منوی hamburger.
2. **Hero wide campaign:** بنر Sheglam قهوه‌ای/برند همراه تصویر با چاپ درشت سفید؛ نقاط اسلایدر زیر. پیام تبلیغ روی خود asset است، بنابراین رنگ تصویر *جزو theme recolor* نیست.
3. **Trust mini features:** ردیف ۴ مزیت با icon گرد صورتی و عنوان کوتاه، فاصله زیاد از background.
4. **دو بنر کوتاه کنار هم** در رنگ‌های صورتی (تبلیغات محصولات شیگلم و برند دوم)، radius متوسط؛ دسکتاپ دو ستون و موبایل استک یا دو ستون باریک برحسب screenshot.
5. **جدیدترین محصولات:** carousel/card row با عکس کالا روی سفید، نوار/کادر صورتی، badge درصد/جدید، title دوخطی، قیمت؛ تیتر راست و لینک «مشاهده همه» در سمت مقابل.
6. **محصولات تخفیف خورده:** کارت‌ها با sale badge و قیمت قدیم/جدید؛ تکرار استایل مشترک کارت.
7. **بنر افقی علمی/مراقبتی** با برند Kerrastase در میانه صفحه؛ برچسب کمپین.
8. **پک آرایشی:** ردیف محصولات پک با تصویر حجیم و carousel.
9. **فوتر:** نوار فوشیا بالایی، چهار ستون اطلاعات معرفی، لینک‌ها، اطلاعات تماس، نشان اعتماد، social؛ whitespace فراوان، floating contact badge پایین.

### 3.3 صفحه محصول

- **Desktop:** پیشانی بالایی title + مجموعه tabs/chips کوچک؛ gallery تصویر محصول در سمت راست و thumbnail strip افقی؛ پنل سمت چپ با عنوان چندخطی، قیمت حدود ۱۷٬۳۶۷٬۰۰۰ تومان در لحظه screenshot (محتوای نمونه، نه قیمت قالب)، CTA خرید صورتی بسیار شاخص، quantity، وضعیت انبار، reassurance strips در سبز ملایم/صورتی، آیکن علاقه‌مندی/اشتراک. توضیحات طولانی زیر یک ردیف tabs (توضیحات/مشخصات/دیدگاه‌ها) و related products.
- **Mobile:** تصویر اصلی روی زمینه سفید و thumbnails کوچک در یک ردیف، title و قیمت بزرگ، CTA full-width صورتی، notices پاستلی و اطلاعات محصول، tabهای compact و مقاله طولانی با زیرتیتر و bullet‌های صورتی، related cards و فوتر.
- **PDP design-specific:** inline alert/success strips، قلب floating، pink minimal breadcrumb، sale percent badge، دکمه primary با `T` radius ۶–۱۲px و ارتفاع ۴۲–۵۲px، کنترل variant/quantity متصل به دیتای محصول.
- **Required responsive:** نه فقط کوچک کردن دسکتاپ؛ در موبایل gallery بالای خرید، notices تمام‌عرض و tabs به کنترل فشرده/scrollable تبدیل شوند.

### 3.4 نقشه R4

- **موجود در کد:** hero_banner / multi_banner / product_section / trust_features / product_main / product_description / related_products / رنگ semantic و gallery.
- **نیازمند اثبات/توسعه عمومی:** کنترل استایل PDP alerts، CTA و buy panel؛ card accent border و badge variant؛ کنترل تاب‌های PDP (نمایش، سبک و الگوی mob)، هماهنگی رنگ theme در alert و mobile nav؛ آرایش دو بنر با Ratio مستقل.

---

# 4) سایت C — عسل بانو | `AsalBanoo.zip`

**حوزه:** لوازم آرایشی و مراقبت پوست، پرتراکم و کمپینی. PDP نمونه «اسپری ضد آفتاب مای SPF50». تفاوت شدید بین بخش‌های بنری خانه و صفحه محصول؛ UI ترکیب نارنجی، زرد، کرم، آبی آسمانی.

### 4.1 هویت، رنگ، فونت

- `C` Woodmart global `--wd-primary-color: rgb(237,181,31)` = **#EDB51F**؛ font-family پایه `IRANSansWeb_FaNum`. `C` رنگ CSS `#FF6E1E` نیز ثبت شده که با نوارهای نارنجی پرقدرت screenshot سازگار است. **در این سایت رنگ `primary` ثبت‌شده لزوماً رنگ dominant همه ناحیه‌ها نیست.**
- `V` نوار تبلیغ بالا آبی خیلی روشن؛ CTA و نوارهای کمپینی نارنجی؛ پس‌زمینه cream/yellow روشن برای تیم و توضیح؛ سبز در CTA افزودن به سبد PDP. `T`: `canvas=#FFFFFF`,`campaign=#FF6E1E`,`primary=#EDB51F`,`soft=#FFF2CC`,`info=#BFE9F6`,`ctaSuccess=#6BBE39`؛ سه رنگ action باید معنایی باشند، نه رنگ ثابت هر قالب.
- `T` IRANSansWeb_FaNum body ۱۳–۱۴؛ card title ۱۲–۱۴؛ banner header ۲۴–۴۴؛ heading ۲۰–۲۶؛ badges ۱۰–۱۲؛ border radius card ۸–۱۶.

### 4.2 صفحه اصلی

1. **Announcement top strip** رنگ آبی روشن با پیام تجاری و icon؛ **header** لوگوی سمت راست، جست‌وجو، سبد/حساب؛ navigation و دسته‌بندی‌های عمیق، مخصوصاً در موبایل hamburger.
2. **Hero full-width promotional:** کمپین عطر/محصولات آرایشی با تصاویر چندگانه و copy سفید/تیره روی پس‌زمینه گرم؛ slider dots و prev-next. در اسکرین موبایل اسلاید صورتی با محصولات صورتی دیده می‌شود، دسکتاپ یک اسلاید دیگر قهوه‌ای؛ *محتوای اسلاید متفاوت لزوماً layout موبایل متفاوت نیست*.
3. **دسته‌بندی‌های دایره‌ای** با حاشیه نارنجی، عکس محصول کوچک داخل، label زیر، carousel navigations.
4. **بخش شگفت‌انگیز:** بک‌گراند نارنجی تمام‌عرض، چند کارت سفید با borders نارنجی، badge تخفیف و قیمت، CTA «مشاهده همه»، mobile cards ۲ عدد نمایان و slider. اهمیت بالای contrast orange/white.
5. **کارت‌های کالکشن/دسته تصویرمحور:** چهار تصویر مربعی محصولات چهره/عطر در پس‌زمینه زرد کرم با کادر گرد.
6. **پرفروش‌ها:** ردیف کالاها با card سفید، نام/امتیاز/قیمت، بعضاً دکمه افزودن سریع در تصویر؛ mobile carousel دو کارتی.
7. **گروه بنرهای promotion:** بنرهای افقی pastel، بعضاً ۲/۳ در grid؛ عطرها/کرم‌ها و مدل انسانی.
8. **تیم/مشاوران:** نوار زرد روشن، کارت پرتره واقعی مشاور همراه نام و CTA. *کارت personnel با review/testimonial اشتباه نشود*: داده، عکس، نقش و اقدام مستقل نیاز دارد.
9. **تازه‌ها و چند shelf** محصولات واقعی با تنوع متعدد.
10. **Blog/ویدئو و مقالات:** کارت‌های آموزشی ۲–۴ ستونی؛ یک نوار قوی نارنجی در میانه/پایین. **Brand story/About** با عکس فروشگاه و متن.
11. **اعتماد و اطلاعات:** ویژگی‌ها/مزایا/عضویت اجتماعی، چند ستون footer کرمی/طلایی و نوار badgeهای پرداخت/اعتماد در انتها.

### 4.3 صفحه محصول

- **Desktop:** breadcrumb، gallery محصول اسپری با یک تصویر بزرگ isolated سمت راست؛ پنل title/rating/قیمت در کنار آن؛ ویژگی‌ها به شکل bullet لیست؛ CTA سبز و qty؛ تخفیف به عنوان indicator. زیر آن متن بلند و headingهای H2/H3، tab/accordion، FAQ، نظرات و فرم ارسال دیدگاه، related products، footer.
- **Mobile:** **hero gallery تمام‌عرض** + یک floating دایره درصد/discount، title و امتیاز در ابتدای ستون، bullet-heavy مشخصات (نسبتاً طولانی)، CTA سبز پس از مشخصات؛ سپس تیترها و متن کاملاً ستونی، tabs در یک ردیف با underline accent، بخش FAQ آکاردئونی، نظر/فرم، مشابه‌ها و footer.
- **تمایز عملکردی:** نمایش فهرست ویژگی‌ها درست کنار add-to-cart، پیام ارسال/مزایا، وضعیت موجودی واقعی، نظرات و FAQ مستقل؛ متن SEO بلند نباید به HTML خام غیرقابل‌ویرایش در preset تبدیل شود.

### 4.4 نقشه R4

- **قابل ساخت از موجودی:** `hero_banner`, `category_grid.circular`, `amazing_offers`, `promo_cards`, `product_section`, `testimonials`, `blog_posts`, `faq`, `rich_text`, `image_text` و `product_main`.
- **نیازمند بررسی/توسعه:** کارت اعضای تیم با عکس/سمت/CTA به صورت عمومی (ممکن است با collection_tiles یا image_text کافی باشد؛ قبل از ساخت تعیین شود)، ردیف promotion چندخانواده‌ای، configurable buy bullet list، FAQ منبع داده مربوط به محصول، رنگ‌های `success/action` و تطابق palette، card add-to-cart quick action.

---

# 5) سایت D — دیزه | `Dize.zip`

**حوزه:** لوازم خانه و دکوراسیون، لوکس آرام و عکاسی lifestyle. PDP «کاسه شیشه و سنگ تراورتن سایز کوچک». نسبت به مراجع دیگر کم‌متن، whitespace زیاد و محوریت تصویر.

### 5.1 هویت، رنگ، فونت

- `V` پس‌زمینه سفید گرم؛ نوار خاکی/قهوه‌ای تیره با نوشتار طلایی؛ صفحات با تاوپ/بژ روشن و دکمه خرید شنی؛ قیمت متن ذغالی؛ امتیاز طلایی.
- `C` فایل CSS بسیار بزرگ، `@font-face`‌های متعدد شامل `Anjoman`, `IRANYekanX`, `dana`, `IRANSansX`, `Kalameh` و `Noto Sans` دارد؛ **از حضور فایل‌ها نمی‌توان فونت فعال body را قطعاً تعیین کرد**. `T` فونت ایرانی با فرم ساده (ابتدا IRANYekanX را در computed screenshot مقایسه کنید)، body ۱۳–۱۴، h2 ۲۲، product title ۲۰–۲۶؛ در لوگو از فونت تصویری لوگوی اختصاصی نباید در قالب عمومی استفاده شود.
- `T` palette برای ساخت: `canvas=#FCFBF9`, `surface=#FFFFFF`, `sand=#C1B59A`, `brown=#58472E`, `ink=#27221C`, `subtle=#E8E4DA`, `price=#464136`, `star=#DEA833`. **این hexها اندازه‌گیری دقیق از CSS نیستند**؛ target بصری‌اند.
- `V` دکمه‌ها rectangular با radius ناچیز ۰–۴px، product card عکس بزرگ سبک editorial، shadow بسیار کم/none؛ متن محصول کوتاه و قیمت زیر.

### 5.2 صفحه اصلی

1. **نوار اعلان خاکی تیره** با برچسب زرد و پیام دعوت کانال؛ لوگوی سفید/آیکن سمت راست؛ `T` height ۳۲–۴۸px.
2. **Header سفید بسیار باز:** لوگوی typographic بزرگ و مرکز‌گرا، cart/search در یک سمت، منوی کم‌تراکم در سمت دیگر؛ sticky محتمل ولی از اسکرین ثابت نمی‌توان تأیید کرد (`U`). موبایل logo مرکز، cart/search/hamburger اطراف.
3. **Hero عکاسی دکور:** تصویر lifestyle وسیع با ظروف و گل؛ بدون CTA پرتکست؛ در موبایل نسبت تصویر portrait/crop و dots/slider.
4. **دو بنر دکور کنار هم:** عکس tabletop و سرویس غذاخوری با کپشن کوتاه و فاصله بین کارت‌ها.
5. **سه کارت showcase/image-first:** عکس‌های lifestyle بلند با نام کالای زیر تصویر، قیمت و دکمه سبز افزودن؛ arrows کاروسل. این ترکیب از carousel فروشگاهی استاندارد با عکس بسیار بزرگ و text minimal حاصل می‌شود.
6. **بخش محصولات گرید:** چند ردیف چهارستونی دسکتاپ/دوستونی موبایل، ratio عکس نزدیک مربع یا ۴:۵، قیمت زیر، حاشیه کارت بسیار کم.
7. **دعوت به شبکه اجتماعی:** نوار نازک بژ با icon Instagram، copy کوتاه.
8. **Footer یکپارچه ساده:** سطح بژ/شنی با contact/social/نشان اعتماد؛ دکمه floating chat و بازگشت بالا.

### 5.3 صفحه محصول

- **Desktop:** breadcrumb/عنوان، چیدمان دو‌ستونی: یک تصویر lifestyle بزرگ در راست و summary در چپ، امتیاز ستاره، قیمت، qty و دکمه خرید به رنگ شنی؛ زیر آن tabs باریک با خط جداکننده، **بخش مشابه‌ها** ۴ کارت lifestyle، فوتر بژ.
- **Mobile:** ابتدا گالری/تصویر اصلی و سپس عنوان، امتیاز و قیمت، qty + CTA شنی و یک خط اطلاعات وضعیت. سپس فضای قابل‌توجه سفید، تب/accordion توصیف یا توضیحات، دو کارت محصول مشابه در عرض، footer.
- **ویژگی‌های مهم:** قابلیت عکس lifestyle با cover، نسبت رسانه قابل ویرایش، panel compact بدون ازدحام، CTA با weight متوسط، card body کم‌متن، تقویم/ویژگی‌های خدماتی در navbar اگر در داده وجود داشته باشد.

### 5.4 نقشه R4

- **موجود:** hero overlay و banner، `multi_banner`, `product_section`, `product_main`, `related_products`, `product_description`, palette، card variants.
- **نیازمند اثبات:** variant کارت کاملاً minimal بدون badge و hover؛ محصول با تصویر cover و جلوگیری از crop نامناسب؛ اندازه متفاوت لوگوی desktop/mobile؛ امکان کم‌کردن چگالی و spacing به‌اندازه سبک editorial، page container narrow/wide؛ تصاویر placeholder مناسب خانه/دکور.

---

# 6) سایت E — خانه شکلاتی | `khanehshokolati.zip`

**حوزه:** تراول‌ماگ، ماگ، giftshop و محصولات کلکسیونی؛ طراحی شلوغ ولی ساخت‌یافته، با قهوه‌ای، طلایی، آبی بسیار کم‌رنگ و فوتر مشکی. PDP نمونه «تراول ماگ ۱۰۵۰ میل تایسو».

### 6.1 هویت، رنگ، فونت

- `C` متغیر اصلی `--primary-color:#704012`؛ رنگ دیگر ثبت‌شده `#FFAF00` (طلایی) در استایل‌ها. font-face فعال محتمل `iransansdn` از CSS (قواعد body با همین family موجود). `V` background صفحه به آبی/خاکستری خیلی روشن تمایل دارد، header قهوه‌ای، دکمه خرید زرد طلایی و دکمه مکمل قرمز، فوتر سیاه و موجی.
- `T` palette: `canvas=#EAF3FB`, `surface=#FFFFFF`, `primary=#704012`, `gold=#FBCB60`, `ink=#24170E`, `black=#090909`, `danger=#F5224C`. `T` body ۱۲–۱۴، headings ۱۸–۲۴، PDP title ۲۰–۲۶، prices ۱۸–۲۴، card badge ۱۰–۱۲؛ radius کارت ۱۰–۲۰.

### 6.2 صفحه اصلی

1. **Header قهوه‌ای دو‌ردیفی:** نوار بالایی با گزینه‌های درباره/ورود و لوگوی مرکزی؛ جست‌وجوی طولانی و آیکن‌ها؛ ردیف دسته‌های متنی. موبایل هدر فشرده و **bottom navigation** ثابت با آیکن‌های خانه، دسته‌ها، سبد و حساب.
2. **Story/category rail:** ردیف ۸ تا ۱۰ آیکن/تصویر دایره‌ای یا کوچک، label کوتاه، border برند؛ باید با real store categories و تصاویر واقعی باشد.
3. **Hero دو اسلاید تصویری کنار هم** در دسکتاپ/کاروسل با تصویر وسایل هدیه و overlay buttons؛ mobile یک کارت/اسلاید نمایان با فلش.
4. **دسته‌بندی‌های تصویری بدون کارت:** چند ردیف **خروجی cutout روی background**، نام در pill قهوه‌ای؛ در موبایل ۲ ستون، گاهی grid نامتقارن.
5. **بنر برند Stanley** عریض و lifestyle سبز/قهوه‌ای با logo embedded داخل تصویر.
6. **ویترین محصولات جدید** ۴ کارت با عکس غالب، badge تخفیف، قیمت، button قهوه‌ای زیر card؛ card های مشابه در طول صفحه تکرار می‌شوند.
7. **بنرهای mosaic نسپرسو/کالکشن‌ها:** یک تصویر بزرگ + چند کارت تصویری اطراف با نسبت‌های متفاوت؛ اجرای درست نیازمند container/cell مستقل است.
8. **پیشنهاد ویژه/تخفیف:** row محصول با badge% و قیمت قدیم/جدید؛ badge زمان‌دار اگر داده real دارد.
9. **جدول یا بخش داستان فروشگاه + مجله:** متن SEO با تصاویر؛ چند نوع row کالا؛ editorial story cards.
10. **Footer تیره با بالای موجی:** برند، مجوز/اینماد، تماس، social، لینک‌ها و disclaimer؛ موج decorative باید از مکانیزم عمومی decorative strip یا background shape استفاده کند، نه کد مخصوص قالب.

### 6.3 صفحه محصول

- **Desktop:** عکس بزرگ رنگارنگ تراول ماگ‌ها در سمت راست، thumbnails زیر؛ title و price current/previous و sale % در سمت چپ؛ **پنل خرید کادربندی‌شده با حاشیه طلایی**. انتخاب واریانت رنگ با چند chip مستطیلی دو تا سه‌ردیفه، اطلاع موجودی variant، optional checkbox افزونه/هدیه/بسته‌بندی، تعداد و CTA خرید زرد طلایی؛ trust/status cards آبی و دکمه دوم قرمز برای نوع اقدام مکمل. زیر پنل، توضیحات/ویژگی‌ها، Related 4 cards.
- **Mobile:** gallery بالای screen با تصویر عریض و thumbnails، زیر آن buy panel تمام‌عرض با border طلایی radius زیاد؛ title، price، swatches/chips در grid دو تا سه ستون، کنترل موجودی و اطلاعات ارسال، qty و CTA اصلی و مکمل؛ پس از panel توضیح محصول؛ related دو‌ستونی؛ floating bottom nav روی mobile، footer سیاه.
- **نیاز ویژه:** واریانت‌ها می‌توانند ۶–۸ رنگ داشته باشند؛ انتخاب باید قیمت/موجودی صحیح Django را تغییر دهد و combo نامعتبر به cart ارسال نشود. Optional extras (هدیه/بسته‌بندی) تنها اگر مدل تجاری پشتیبانی کند؛ UI ظاهری نباید چنین add-on را بدون داده/price logic جعل کند.

### 6.4 نقشه R4

- **موجود:** `category_grid`, `story_rail`, `hero_banner.chocolate_carousel`, `multi_banner`, `promo_cards`, `product_section`, `product_main` دارای selector موجود Alpine برای variant، `related_products`, footer variants, `decorative_strip` و mobile nav.
- **ریسک اصلی:** config عمومی ساختار PDP و ترازبندی thumbnail/chips/CTA؛ extra purchase options و add-on price logic (قبل از طراحی نیازمند تحلیل models/order/cart)؛ ترکیب mosaic container/cells، موج footer، هویت دو CTA متفاوت، تداوم palette در پیام‌های ارسال و sale.

---

# 7) سایت F — ژیمون پلاس | `zhimunplus.zip`

**حوزه:** فروش خدمات دیجیتال/اکانت اشتراکی، تم تیره آینده‌نگر؛ مرجع مهم برای غیرپوشاک و کالاهای غیر‌فیزیکی. PDP نمونه «اکانت ChatGPT».

### 7.1 هویت، رنگ، فونت

- `C` `--wd-primary-color: rgb(6,9,127)` = **#06097F**، font text/title=`yekanbakh`. CSS سایت رنگ‌های بسیار پرکاربرد `#151B2D` (raised navy), `#070E1C` (deep dark), `#202A83` (blue), `#03BFAC` (teal), `#BABFC4` (muted). `@font-face` شامل `rokh` برای headline است؛ در بعضی headingهای Elementor همین فونت ارجاع شده.
- `V` background بسیار تیره و سطوح gradient/indigo؛ اکثر لوگو و کارت‌ها neon/cyber، CTA آبی برقی، occasional green pricing و red/orange option tiles؛ footer تیره و تفکیک اندک از بدنه.
- `T`: base body YekanBakh و heading optional Rokh؛ body ۱۳–۱۵، h2 ۲۰–۲۸، hero ۳۰–۴۸ desktop/۲۴–۳۴ mobile، card name ۱۲–۱۶، pricing ۱۲–۱۸؛ radii ۱۰–۱۸ و shadow accent subtle؛ text `#F8FAFC`, muted `#BABFC4`. contrast verification critical.

### 7.2 صفحه اصلی

1. **Header تاریک دسکتاپ** logo راست، جست‌وجوی طویل وسط، منوی دسته خدمات AI/ویدئو/موسیقی، سبد، علاقه‌مندی، حساب؛ mobile hamburger + logo و search minimal.
2. **Hero دو‌ستونی دیجیتال:** تصویر ربات کارتونی سه‌بعدی سمت راست یا چپ متناسب RTL، headline چند سطری سفید، subtitle کم‌رنگ، CTA آبی و secondary CTA، و **چهار mini-panel gradient** با آیکن و پیشنهاد کوتاه (پشتیبانی، تحویل، هزینه، پکیج). Desktop side-by-side؛ mobile art بالا و متن/CTA پایین و mini-panels ۲×۲.
3. **Latest products:** shelf از خدمات/اکانت جدید؛ تصاویر مربع بسیار رنگی با headline داخل *asset*، کارت dark outlined، name، price و button blue.
4. **پرفروش‌ترین‌ها:** carousel پنج‌تایی Canva/ChatGPT/Gemini و غیره؛ img square/portrait، badge کوچک، قیمت، ستاره در صورت داده، CTA.
5. **دسته خدمات دیجیتال:** ردیف shortcut آیکنی مربعی بنفش/آبی و عنوان کوتاه.
6. **چندین shelf محصول موضوعی** برای AI، آموزشی، ویدئو، موزیک، ویژه/پیشنهادی، هرکدام title و «مشاهده همه»؛ data source باید category/collection واقعی باشد و ترتیب قابل تغییر.
7. **Customer feedback / trust:** چند کارت testimonial تیره با آواتار و نقل‌قول واقعی، badge امتیاز.
8. **Footer:** چند ستون dark معرفی خدمات، CTA پیام‌رسان، خدمات، قوانین، شبکه‌های اجتماعی داخل کاشی‌های مربعی بنفش/آبی، نوار پایانی.

### 7.3 صفحه محصول

- **Desktop:** hero محصول ChatGPT با تصویر اصلی گرافیک سبز/مشکی و title بسیار واضح؛ قیمت/وضعیت و CTA آبی؛ overlay trust message و share؛ زیر آن tab description، بخش مقاله بلند و graphic explanation، related products gallery، footer.
- **Mobile:** تصویر square تمام‌عرض بالا؛ title، قیمت و وضعیت؛ جزئیات مزیت/شرایط، bullets و آیکن‌های delivery/support؛ سپس بخش‌های طولانی توضیح/راهنما، محصول پیشنهادشده دیگر و footer. در اسکرین‌شات موبایل PDP حدود ۲۶هزار پیکسل ارتفاع ثبت شده که نشان‌دهنده متن بسیار طولانی است؛ **نباید تمام متن در قالب hardcoded باشد**.
- **تمایز دامنه داده:** کالا ممکن است دیجیتال، دارای مدت اعتبار/روش تحویل/لایسنس/پلن و بدون ارسال فیزیکی باشد. صرفاً زیباتر کردن template جایگزین پشتیبانی business logic و فیلدهای catalog/cart نمی‌شود. مشخصات مدت اعتبار و روش تحویل تنها با اتصال به داده موجود یا مدل موردتأیید قابل ارائه‌اند.

### 7.4 نقشه R4

- **موجود:** `hero_banner`/variant های dark، `product_section`, `category_grid`, `trust_features`, `testimonials`, `rich_text`, `product_main`, `related_products`, `blog_posts`, `theme.palette`, `dark_digital` ready template.
- **نیازمند بررسی جدی:** font چندخانواده‌ای برای hero، dark theme contrast همه صفحات، gradient mini-panels به‌صورت shared `promo_cards`/Container، image badges، card CTA styles و badge، delivery-type مخصوص دیجیتال، نمایش مدت پلن/فعال‌سازی، purchase model compatibility، کنترل‌های PDP با استایل neon.

---

# 8) کتابخانه کامل اجزای مشترک استخراج‌شده از شش سایت

| کد | کامپوننت عمومی | ویژگی‌های ساختاری/Inspector مورد انتظار | نمونه‌ها |
|---|---|---|---|
| G01 | announcement bar | متن/لینک/آیکن/رنگ/height/visibility/sticky | عسل‌بانو، دیزه |
| G02 | header variants | ۱–۳ ردیف، logo position، search، actions، nav، responsive collapse | هر شش |
| G03 | mega navigation | دسته‌های تو در تو، عرض/ستون، promo panel اختیاری، keyboard/focus، mobile drawer | عسل‌بانو، لیلیکا، ژیمون |
| G04 | mobile bottom nav | ۳–۵ action، labels، safe-area، active states، visibility | خانه‌شکلاتی |
| G05 | hero slider | overlay/split/poster، autoplay/dots/arrows، focal points، different breakpoints | هر شش |
| G06 | asymmetrical collage | ۲–۵ سلول، نسبت‌های ترکیبی، ترتیب موبایل، slot مستقل | خانه‌شکلاتی، لیلیکا |
| G07 | promo card row | image/text/button/link/background/radius/gradient | لیلیوم، عسل‌بانو، ژیمون |
| G08 | circular category rail | thumbnail/icons، border/text، overflow/carousel | عسل‌بانو، خانه‌شکلاتی |
| G09 | image/category tiles | square/portrait/cutout، overlay/pill label، CTA | خانه‌شکلاتی، دیزه |
| G10 | brand carousel | لوگو، لینک، مدیریت نسبت و grayscale/hover | مراجع آرایشی |
| G11 | product carousel/grid | source/count/sort/filters/title/tab/layout/nav | هر شش |
| G12 | product card variants | minimal, outlined pink, sale orange, lifestyle, deep digital, warm retail | هر شش |
| G13 | campaign offer shelf | colored campaign background, countdown if real, discount badges | عسل‌بانو |
| G14 | editorial image + text | image order, rich text, bullet/icon list, responsive | لیلیکا، دیزه |
| G15 | services/trust strip | آیکن سبک خطی یا filled، ۲–۵ خانه، توضیح | لیلیکا، لیلیوم |
| G16 | consultant/personnel cards | portrait/name/role/CTA, carousel | عسل‌بانو |
| G17 | testimonials | avatar/quote/rating/verified (when data exists) | ژیمون، عسل‌بانو |
| G18 | blog/news rail | picture, title, excerpt, meta/link, tag | لیلیکا، عسل‌بانو |
| G19 | video block | thumbnail/media/consent/play overlay | عسل‌بانو/موارد اختیاری |
| G20 | FAQ | accordion, per-product/global sources, ARIA | عسل‌بانو |
| G21 | newsletter/social/contact | signup/form rules, social list, icons | تمام فوترها |
| G22 | decorative strips | wave, simple stripes, gradient/shape only if generalized | خانه‌شکلاتی |
| G23 | product gallery | image thumbnails, main lightbox, zoom, touch swipe, contain/cover | تمام PDPها |
| G24 | PDP purchase panel | title, price, compare price, offers, ratings, qty, CTA, stock, delivery, mobile stack | تمام PDPها |
| G25 | variant selector | available options/range, disabled variants, dynamic price/inventory | خانه‌شکلاتی/لیلیکا |
| G26 | PDP tabs/accordion | description/specs/reviews/faqs, placement/style/visibility | ۶ PDP |
| G27 | cross-sell/related | actual products, count, grid/carousel, empty-state | ۶ PDP |
| G28 | feature/bullet list PDP | sourced attributes, seller-approved claims, icons | عسل‌بانو/ژیمون |
| G29 | digital goods detail | delivery method, subscription duration, license properties tied to model | ژیمون |
| G30 | global floating actions | help/call/chat/back-to-top, positions, overlap safety | دیزه/دیگران |
| G31 | responsive header/search/menu | no clipping, one source of data, auth/cart state | همه |
| G32 | semantic palette system | colors roles, inheritance, provenance, reset, contrast, mobile + PDP + cart | همه |
| G33 | typography controls | font family, roles, sizes/weights/line height/RTL fallback | همه |
| G34 | layout controls | breakpoints, container widths, gaps, order/visibility, empty cell mutation | همه |
| G35 | safe design lifecycle | draft only, preview, publish, undo/redo, revision, tenant isolation | همه |

**توجه:** این جدول «نیازهای نهایی» است، نه فهرست قطعی نواقص. تطبیق واقعی در فصل بعد انجام می‌شود.

---

# 9) ممیزی معماری و میزان آمادگی R4 نسبت به نیازها

## 9.1 کدها و درجه‌بندی وضعیت

- **CODE PRESENT:** کد/رجیستری/قرارداد مشخص در شاخه بررسی‌شده دیده شد؛ نه پذیرش مرورگر.
- **PARTIAL / DESIGN GAP:** primitive اصلی هست، اما تنظیم‌پذیری، توان بیان طرح، یکپارچگی/تجربه کاربر یا تست به سطح خواسته نرسیده یا شاهد کامل وجود ندارد.
- **NOT FOUND / RESERVED:** شواهد صریح درباره نبود قابلیت یا reserved بودن آن دیده شد؛ پیش از افزودن باید کد/منتظر تصمیم معماری بررسی شود.
- **UNVERIFIED:** فقط screenshot نیاز را ثابت می‌کند، ولی برای وضعیت کد R4 بررسی فایل‌های بیشتر، اجرای تست یا QA لازم است. «unverified» به معنی «مفقود» نیست.

## 9.2 موجود در کد R4 — با شاهد مستقیم

| نیاز | وضعیت | شاهد قابل بررسی |
|---|---|---|
| رجیستری رسمی Section | CODE PRESENT | `apps/storefront_builder/section_registry.py` حدود خطوط 3090–3685 |
| Hero overlay/split، beauty، chocolate، atelier، luxury، poster | CODE PRESENT | `section_registry.py` حدود 3104–3164 |
| `image_slider`, `single_banner`, `multi_banner` | CODE PRESENT | `section_registry.py` 3173–3220 |
| دسته‌بندی grid/carousel/circular/mosaic | CODE PRESENT | `section_registry.py` 3220–3271 |
| محصول تازه/ویژه/پرفروش/تخفیفی/شگفت‌انگیز | CODE PRESENT | `section_registry.py` 3272–3318 |
| `product_section` carousel/grid/campaign/catalog و تنظیمات تعداد/columns | CODE PRESENT | `section_registry.py` حدود 254–500 و 3391–3431 |
| برند، promo cards، rich text، image_text، blog | CODE PRESENT | `section_registry.py` حدود 3319–3390 |
| `trust_features`, `collection_tiles`, `quick_links`, `faq`, `testimonials`, `video_section`, `story_rail`, `newsletter`, `decorative_strip`, `surface_panel` | CODE PRESENT | `section_registry.py` حدود 3455–3569 |
| بلوک‌های اصلی صفحه محصول `product_main`, `product_description`, `product_video`, `related_products` | CODE PRESENT | `section_registry.py` حدود 3571–3618 |
| listing/search/collection/cart sections | CODE PRESENT | `section_registry.py` حدود 3619–3680 |
| Header/footer/mobile bottom nav families | CODE PRESENT | `storefront_appearance/families.py` |
| Ready Templates چندصفحه‌ای و گالری | CODE PRESENT | `layout_preset_registry.py`, `a8_ready_templates.py`, `services/preset_service.py` |
| container/cell structured composition | CODE PRESENT | `services/container_service.py`, `services/section_structure_service.py`, `services/render_service.py` |
| `container.add` برای ساخت اتمیک | CODE PRESENT | `services/r4_mutation_service.py` حوالی 523–537 |
| تست‌های نوشته‌شده برای atomicity, rollback, one history, undo, publish | CODE PRESENT (tests authored) | `tests/test_v5_container_add.py` test methods حدود 51–195؛ اجرا در این بررسی NOT EXECUTED |
| مرزبندی یک Mutation service و optimistic revision | CODE PRESENT | docstring و dispatcher `services/r4_mutation_service.py` |
| رنگ/پالت/تم منطقه‌ای و reset/override provenance | CODE PRESENT | `appearance_registry.py` حدود 20–48, 186–310 |
| طبقات component مشترک | CODE PRESENT | `storefront_appearance/families.py`, `storefront_appearance/registry.py` |
| theme CSS و تست ساختاری «تمام صفحات» | CODE PRESENT (test authored) | `tests/test_phase39_full_site_palette_system.py` + `apps/core/static/css/theme_palette.css` |
| Draft و Renderer مشترک | CODE PRESENT | `services/render_service.py` docstring و `services/preset_service.py` |

## 9.3 قابلیت‌های ناقص / ریسک واقعی / ابهام مهم

| شناسه | نیاز | وضعیت فعلی با شواهد | اثر بر شش مرجع | تصمیم پیشنهادی |
|---|---|---|---|---|
| P01 | **کنترل layout و style خود `product_main` در V5** | **PARTIAL:** در `section_registry.py` `capabilities=frozenset()` و `validate_settings=_passthrough_dict`؛ تصویر/قیمت/variant/خرید در renderer واحد هست ولی Inspector ساختاری مستقیم دیده نشده | شش PDP، به‌خصوص پنل خرید خانه‌شکلاتی و فرم ژیمون | ابتدا inventory دقیق renderer و settings؛ در صورت نبود، schema/config عمومی در همان یک بلوک و renderer اصلی؛ بدون جداکردن تجارت |
| P02 | **کنترل سبک tabs/مشخصات/دیدگاه‌ها** | **PARTIAL:** `product_description` تنها قابلیت `background`, `spacing` دارد، خود tabها یک Alpine block مشترکند | شش PDP با جزئیات متفاوت | style/layout/visibility controls در block موجود به صورت schema-safe؛ همه tabs از داده واقعی |
| P03 | **مگامنوی قابل طراحی مستقل** | **RESERVED:** `families.py` می‌گوید `mega_menu.none.v1` تنها مورد و ارائه مگامنو در برخی header variants است؛ مستقل‌سازی نیازمند تصمیم Product | منوی عمیق ۳ فروشگاه | در فاز اول با header موجود؛ اگر شباهت کافی نبود، proposal معماری جداگانه، نه سرویس دوم |
| P04 | **کنترل دقیق فونت‌ها** | **PARTIAL:** `appearance_registry.FONT_CHOICES=(Vazirmatn,Tahoma,Arial,Georgia)`، `TYPE_SCALE_CHOICES=(compact,normal,large)` | YekanBakh/IRANYekan/IRANSansDN/heading Rokh | ارزیابی امکان افزودن فونت مجاز با license و mapping role، نه upload arbitrary CSS؛ fallback RTL |
| P05 | **کنترل دقیق اندازه‌ها و gap در همه اجزا** | **PARTIAL:** ابزار global `content_width` فقط 1100,1200,1320,1500 و type_scale ۳ حالت؛ sectionها capabilityهای متفاوت دارند | فیدلیتی pixel-level هر شش | mismatch ها با screenshot تایید، کنترل‌های role-based محدود و مشترک، جلوگیری از random magic px |
| P06 | **دو تصویر/فوکال پوینت مستقل desktop/mobile** | **UNVERIFIED:** hero variants و image position وجود دارند؛ pipeline دو رسانه مستقل در schema باید چک شود | کراپ hero و product gallery | بررسی media schema و Preview; اگر فقدان، responsive art direction reusable |
| P07 | **پالت «سراسری واقعی» در PDP/cart/account** | **PARTIAL/UNVERIFIED:** resolver مرکزی و تست CSS وجود دارند؛ هیچ Browser QA در این بررسی اجرا نشد؛ تست خود CSS قبلاً hotfix thumbnail اشاره کرده | هر شش | تست دو پالت خیلی متفاوت در Home/PDP/Listing/Cart/Checkout/Account + Preview/Published؛ بدون PASS خودکار |
| P08 | **قالب‌های مرجع دقیق شش‌گانه** | **NOT YET AUTHORED:** presetهای فعلی شامل `dark_digital`, `warm_boutique`, `editorial_jewelry` و غیره‌اند؛ هیچ ادعای ثبت شش مرجع در این گزارش نیست | تمام | هر کدام recipe جدید فقط پس از تایید design gap؛ نخست pilot |
| P09 | **product-card controls مطابق شش سبک** | **PARTIAL/UNVERIFIED:** card family/variants و shadow/hover/global exist، ولی بررسی exact border, media ratio, inline action و sale layout لازم است | هر شش home/related | variant قابل‌استفاده مجدد، shared registry، no template-specific CSS branch |
| P10 | **واریانت محصول/extra options** | **PARTIAL:** `product_main` خود Alpine `variantSelector(...)` دارد؛ optional extras/plan price mapping اثبات نشده | خانه‌شکلاتی و ژیمون | backend catalog/cart/order audit، بعد UI؛ هیچ fake add-on محصولی |
| P11 | **نام مشاور، نقش، عکس و CTA** | **UNVERIFIED:** با `collection_tiles`, `image_text`, `testimonials` ممکن است کافی باشد؛ نوع اختصاصی staff پیدا نشده | عسل‌بانو | اول قابل بیان بودن با primitives؛ اگر نه، reusable person card data/config با مجوز |
| P12 | **mosaicهای نامتقارن و خانه مستقل** | **CODE PRESENT but QA PENDING:** container/cell و `container.add`; جدید است و screenshot فقط وجود layout را اثبات نمی‌کند | خانه‌شکلاتی و کامپوزیشن‌های عکس‌محور | اجرای تست اتمیک و Windows QA، mobile stacking order، empty cell; بعد ساخت قالب |
| P13 | **موبایل bottom-nav با انواع فرم و safe area** | **CODE PRESENT but QA PENDING:** family وجود دارد، exact visual/overlap نیاز تست | خانه‌شکلاتی، ژیمون | تست keyboard/viewport/cart badge/footer/CTA sticky |
| P14 | **مدل محتوای کالاهای دیجیتال** | **UNVERIFIED:** فروش خدمات دیجیتال از عکس قابل مشاهده است؛ مدل subscription/licensing RastiSi در این بررسی ممیزی نشده | ژیمون | دامنه تجاری separate approval؛ preset بدون ساخت منطق فروش جعلی |
| P15 | **hover/focus/keyboard/tab accessibility** | **UNVERIFIED:** وجود schema/style اثبات QA واقعی نمی‌کند | همه | آزمون کیبورد، focus states، reduced motion و contrast |
| P16 | **نوار موجی فوتر و gradient CTA** | **PARTIAL:** decorative strip و region variants وجود؛ پارامتر exact waves/gradient نیاز بررسی renderer | خانه‌شکلاتی/ژیمون | اول overlay/decorative tokens/section؛ در صورت نبود generalized feature |
| P17 | **قابلیت نمایش قیمت/موجودی بر حسب variant** | **CODE PRESENT at base, integration unverified** | خانه‌شکلاتی و سایر PDP | end-to-end variations and cart tests، no store data overwrite |
| P18 | **صفحات داخلی دیگر غیر از PDP** | **UNVERIFIED:** رجیستری listing/cart موجود؛ **تصویر مرجع listing/cart/checkout/account در این بسته‌ها وجود ندارد** | همه | سطح دقت فقط در حد اشتراک semantic/theme نه clone مرجع؛ تصاویر جدا برای تقلید دقیق لازم‌اند |
| P19 | **محصولات دمو/سایر فروشگاه‌ها** | قاعده معماری لازم، تست رگرسیون لازمه | همه | scope به Store؛ empty-state بدون محتوای جعلی؛ fixture Rasti Mode Demo |
| P20 | **پاریتی Preview / Published و ریویژن/Undo** | کد و تست‌های قبلی وجود دارند؛ وضعیت شش recipe فعلی هنوز NOT EXECUTED | همه | test matrix با PASS/FAIL/NOT EXECUTED، تست regression روی baseline templates |

## 9.4 نکات معماری که در توسعه نباید اشتباه شوند

- در `appearance_registry.py` قرارداد صریح override پنج‌لایه‌ای وجود دارد: **default -> preset baseline -> palette -> merchant global overrides -> explicit section/component overrides**. تغییر palette فقط لایه inherited را عوض می‌کند، و overrideهای تاجر باقی می‌مانند مگر آگاهانه reset شوند. بنابراین جمله «با عوض‌کردن palette همیشه همه رنگ‌ها بدون استثنا تغییر کنند» با قرارداد override آگاهانه سازگار نیست؛ استثناء باید در UI قابل فهم، قابل مشاهده و reset باشد.
- کلیدهای `THEME_ROLE_KEYS` موجود فعلی: `header_bg`, `header_text`, `nav_bg`, `nav_text`, `card_bg`, `footer_bg`, `footer_text`, `price`. semantic palette بیشتر در `DEFAULT_COLORS` و فایل CSS دارد؛ توسعه role جدید تنها بعد از inventory و contract tests.
- `layout` family طبق docstring `families.py` **reserved/inert** است؛ layout واقعی از `StorefrontContainer.layout_key` کنترل می‌شود. هرگز family مستقل دیگری برای انجام همان کار فعال نشود.
- `product_main` یک Alpine component یکپارچه برای گالری/variant/price/cart است؛ شکستن آن به چهار widget مستقل که منبع state جدا داشته باشند ممنوع، مگر با refactor عمومی و بررسی جدی transaction و owner gate.
- برخی Variants موجود مانند `beauty_editorial`, `chocolate_carousel`, `atelier_triptych`, `luxury_showcase` قبلاً در موتور هستند؛ قبل از طراحی component جدید باید همین‌ها واقعاً inspect/render و مقایسه شوند.
- `container.add` در کد شاخه مشاهده شد، ولی این بررسی *اجرای* tests/Windows یا SHA جاری worktree Claude را تضمین نمی‌کند.

---

# 10) معیارهای تطبیق و آزمون نهایی هر قالب

### 10.1 قرارداد fidelity به‌صورت قابل اندازه‌گیری

1. **Structure**: ترتیب همه sectionها، وجود هر بلوک مهم، تعداد ستون، اندازه نسبی hero/کاروسل/فوتر در دسکتاپ و موبایل.
2. **Visual**: رنگ‌های semantic، font family/weight/size/line-height، ratio رسانه، grid gap، border radius، shadow، alignment، icon treatments. Pixel matching فقط پس از render screenshots واقعی قابل سنجش است.
3. **Behavior**: carousel/touch swipe، toggle tabs/accordion، mobile menu، dropdown/focus، CTA، qty/variant، back/forward/cart flows.
4. **Content semantics**: data source واقعی per Store، brand/category/product ownership، عدم تزریق تصاویر کپی‌رایتی سایت مرجع و قیمت دمو.
5. **Theme**: دو پالت بسیار متفاوت، inherited vs overrides، home/PDP/list/search/cart/checkout/account، desktop & mobile؛ contrast و keyboard focus.
6. **Durability**: create/preview/edit/autosave/refresh/undo/redo/publish/recover، switching template، second store isolation، repeatable test fixture.

### 10.2 ماتریس اجرای QA (در زمان نوشتن همه NOT EXECUTED)

| تست | محیط/صفحات | وضعیت فعلی |
|---|---|---|
| Unit: section settings validity and capabilities | Django test / registry | NOT EXECUTED |
| Unit: container.add 1 revision, rollback, Undo/Redo | `test_v5_container_add.py` | NOT EXECUTED |
| Unit: palette inheritance & overrides | appearance registry / mutation | NOT EXECUTED |
| Integration: preview vs publish | R4 shared renderer | NOT EXECUTED |
| Browser desktop/mobile home & PDP | ۶ recipe @ 1440, 390 و 768 | NOT EXECUTED |
| Browser home/product/list/cart across 2 themes | each template | NOT EXECUTED |
| Browser product variants, stock, quantities, cart | demo store + products with variants | NOT EXECUTED |
| Browser keyboard/tab/contrast/reduced-motion | ۶ recipe | NOT EXECUTED |
| Browser template switching without catalog change | ۲ stores | NOT EXECUTED |
| Browser legacy template preservation and Recovery | QA Windows R4/V5 isolated | NOT EXECUTED |

**No PASS claims** تا زمانی که خروجی واقعی Django + Browser QA با تاریخ/SHA/Store ID و خطاهای شناخته‌شده ثبت شود.

---

# 11) ترتیب پیشنهادی توسعه برای Claude Code — بدون ارسال ZIP

1. **فاز صفر: baseline audit read-only.** ابتدا worktree و commit را تعیین کند؛ فقط inventory کد، available variants، mutation، theme/typography و Inspector؛ هیچ تغییر کد. خروجی باید برای هر `Gxx` و `Pxx` با path/line/Status و evidence باشد. `container.add` regression در QA مستقل باید ارزیابی شود.
2. **فاز اول: capability matrix و gap prioritization.** به‌جای شروع شش قالب، هر مؤلفه را `present`, `present-but-limited`, `not-found`, `risky/scope-out`, `unverified` با شاهد واقعی علامت بزند. در عین حال `reference spec` این سند جای ZIP را می‌گیرد.
3. **فاز دوم: رفع gapهای عمومی با تأیید معماری.** اول قالب/کاروسل/صفحه محصول/تم/فونت را بر اساس نیاز واقعی و test design حل کند. برای `P01`, `P02`, `P03`, `P10`, `P14` بدون تأیید معماری تغییری اجرا نشود؛ این‌ها به قراردادهای حساس مربوط‌اند.
4. **فاز سوم: یک pilot.** پیشنهاد از نظر توان نمایش: **دیزه** برای حداقل‌گرایی و `product_main`، یا **لیلیوم** برای رنگ/کارت/بنر و PDP، انتخاب با کارفرما. پس از PASS کامل، توسعه ۵ قالب بعدی با همان primitives و recipe تکرار شود.
5. **فاز چهارم: گسترش چندسایتی.** ۶ recipe و paletteهای پیشنهادی مستقل؛ هر تغییر تنها روی Draft، بدون تغییر محصول و سفارش، با Preview تصویری واقعی دسکتاپ/موبایل؛ شماره نسخه و امکان برگشت.

## 11.1 دستور آماده برای Claude Code — فاز «فقط ممیزی»، بدون تغییر

> **ROLE:** You are auditing RastiSi Django Storefront Builder R4 and V5, on the existing V5 feature worktree only. No code writes or migrations, no checkout/reset/seed, no main changes. Verify current `pwd`, git branch, SHA, dirty status, database path and media path BEFORE any test. Preserve the protected main and QA_ARCH02 environments.  
> **INPUT:** The complete document `RastiSi_V5_Six_References_Design_Audit.md` is the reference specification. The six ZIP files, images and third-party logos are NOT accessible to you. Do not assert you viewed them. Treat CSS dimensions marked `T` as targets, not measured exact values.  
> **TASK:** Inspect `apps/storefront_builder/section_registry.py`, `services/{render_service,r4_mutation_service,section_structure_service,preset_service}.py`, `layout_preset_registry.py`, `appearance_registry.py`, `storefront_appearance/*`, V5 Inspector/JS/CSS, PDP templates, global CSS and relevant tests. Produce a complete G01–G35 and P01–P20 capability matrix: `PRESENT / PARTIAL / NOT FOUND / UNVERIFIED`, exact file path and line evidence, owner for edits, backend/frontend/preview/publish behavior and planned QA. Identify any false gaps because existing primitives already cover them.  
> **MUST VERIFY:** `container.add` atomically creates empty and prefilled layouts; single revision/undo/redo; behavior of one cell when another changes; palette roles and overrides across Home/PDP/Listing/Cart/Checkout/Account; current product_main and description configuration boundaries; mega-menu family reserved status; allowed fonts/type scales; actual real browser QA status. Explicitly distinguish authored tests from executed tests and mock/snapshot from Windows QA.  
> **OUTPUT:** `Audit report only` with traceable evidence, smallest viable architecture changes, priority P0/P1/P2, migration and compatibility risks, tests to add, and exact points requiring owner approval. Do not implement any capability or template in this step.

## 11.2 دستور آماده برای Claude Code — بعد از تأیید ممیزی (فعلاً اجرا نشود)

> Build exactly **one approved ready-template pilot** as a *recipe* using the existing R4 Section Registry / Container-Cell-Block / store appearance system / one mutation boundary and shared renderer. No template-specific models, migrations, custom renderer path, global `if template == ...` CSS patches, hardcoded products or copied assets. Use only merchant-owned products, brands, media and links; preserve store data and all existing template rendering. Apply to explicit Draft with checkpoint, preview before publish, keep undo/redo/revision, protect multi-tenant ownership. Reuse existing components first; any missing shared component requires separate architecture proposal/approval and invariant tests before implementation. Do not change `main`. Provide unified diff, test commands, PASS/FAIL/NOT EXECUTED and screenshots from real Windows browser QA for both desktop/mobile and two dramatically different palettes across Home/PDP/List/Cart.

---

# 12) جمع‌بندی تصمیم‌گیری و محدودیت‌های قطعی

**قوی‌ترین فرصت بازاستفاده:** همه سایت‌ها از قطعات تکرارشونده‌ای ساخته شده‌اند که بخش بزرگشان در R4 موجود است. توسعه شش موتور جدا یا شش template HTML مستقل نه لازم است نه مجاز. چالش اصلی *درجه تنظیم‌پذیری*، *فیدلیتی استایل*، *صفحه محصول*، *رنگ سراسری* و *عملکرد موبایل* است.

**مهم‌ترین گلوگاه پیش از ساخت:** `product_main` در رجیستری تنظیمات صریح طراحی ندارد؛ `product_description` فقط محدودیت قابلیت دارد؛ mega-menu مستقل reserved؛ فونت‌ها فقط مجموعه محدودی دارند. این‌ها موارد واقعی audit هستند، ولی قبل از تغییر باید بررسی شود `DesignBlock`, appearance overrides, variant registry یا Inspector موجود همان نیاز را پوشش می‌دهد یا خیر.

**آنچه با منابع فعلی دقیقاً قابل اندازه‌گیری نیست:** `computed CSS` برای صفحات PDP، breakpointهای اجرایی واقعی پس از JS، انیمیشن، hover/focus، اسلایدر autoplay، تمام footer copy و تعداد دقیق بعضی محصولات در هر viewport، business rules خرید دیجیتال/extra products، تمام صفحات داخلی غیر از PDP، و اجرای تست واقعی R4. هیچ اندازه T نباید به عنوان CSS استخراج‌شده به کار رود.

**اصل نهایی:** تمام تغییرها روی feature branch و worktree مستقل با تست regression؛ Preview/Draft/Publish یک مسیر مشترک؛ palette roles و overrides شفاف؛ no data cross-store; هیچ توسعه بنیادین بدون تأیید جداگانه.

### پیوست: مسیرهای منبع فنی برای ممیز

- `apps/storefront_builder/section_registry.py`
- `apps/storefront_builder/layout_preset_registry.py`
- `apps/storefront_builder/a8_ready_templates.py`
- `apps/storefront_builder/a9_reference_templates.py`
- `apps/storefront_builder/appearance_registry.py`
- `apps/storefront_builder/services/r4_mutation_service.py`
- `apps/storefront_builder/services/section_structure_service.py`
- `apps/storefront_builder/services/render_service.py`
- `apps/storefront_builder/services/preset_service.py`
- `apps/storefront_builder/storefront_appearance/{families,registry,adapters}.py`
- `apps/storefront_builder/tests/test_v5_container_add.py`
- `apps/storefront_builder/tests/test_phase39_full_site_palette_system.py`
- `apps/storefront_builder/templates/storefront_builder/sections/{product_main,product_description}.html`
- `apps/core/static/css/theme_palette.css`

---

# 13) پیوست اندازه‌های **واقعاً استخراج‌شده** از فایل‌های رسانه (C)

این ابعاد مربوط به *فایل رسانه* در ZIP است، **نه اندازه CSS رندر شده**. این اطلاعات برای انتخاب ratio و جلوگیری از کش‌آمدن بنر یا crop اشتباه سودمند است. تصویر اصلی متعلق به مرجع است و نباید کپی شود.

| مرجع | فایل/نوع موجود در ZIP | ابعاد source | نسبت عرض به ارتفاع | کاربرد طراحی |
|---|---|---:|---:|---|
| لیلیکا | `s4.jpg` | 1800×771 | 2.33:1 | بنر افقی کمپین |
| لیلیکا | `s3.jpg` | 2500×1401 | 1.78:1 | تصویر کمپین عریض‌تر از portrait |
| لیلیوم | بنرهای اصلی محصولات/کمپین | 1200×480 | **2.50:1** | نسبت مطلوب Hero دسکتاپ |
| عسل‌بانو | `cosmetic.webp` و `perfume.webp` و مشابه‌ها | 1920×786 | **2.44:1** | اسلایدر/بنر افقی |
| عسل‌بانو | `free-postd.gif` و `free-postm.gif` | 1920×60 / 800×94 | 32:1 / 8.51:1 | نمونه **art direction** دسکتاپ و موبایل؛ مستقل از محصول |
| عسل‌بانو | `pattern-video-row.webp` | 2142×734 | 2.92:1 | نوار عریض تصویر/ویدئو |
| دیزه | `slide_1_wide-scaled.jpg` | 2560×1691 | 1.51:1 | تصویر wide سبک editorial |
| دیزه | `slide_2_wide-scaled.jpg` | 2560×1767 | 1.45:1 | تصویر wide دوم |
| دیزه | `slide_1-scaled.jpg` | 1920×2560 | **0.75:1** | گرافیک پرتره برای hero/گالری |
| خانه شکلاتی | نمونه بنر عریض  | 1400×467 | **3.00:1** | نوار promo/brand |
| خانه شکلاتی | lifestyle editorial images | 1458×1079 | 1.35:1 | کارت/بنر تصویری |
| ژیمون | `3Size-scaled.png` | 2560×827 | **3.10:1** | بنر عریض تبلیغاتی |
| ژیمون | کارت‌های محصول دیجیتال متعدد | 2048×2048 | **1.00:1** | آیکن/تصویر مربع خدمات |

### 13.1 پیام مهندسی درباره تصاویر

- **هیروهای ۲.۳۳، ۲.۵، ۲.۴۴ و ۳.۱ به ۱ نباید یک اندازه واحد تحمیلی بگیرند**؛ section media ratio (content/default/explicit) و object-position لازم است.
- **دیزه** هم تصویر wide و هم portrait دارد، پس mobile art direction مهم‌تر از scale-down ساده است.
- **لیلیکا، عسل‌بانو و لیلیوم** تصاویر محصول isolated مربع دارند؛ `contain` و `padding` برای جلوگیری از بریدن بسته‌ها مهم‌تر از cover عمومی است.
- **خانه شکلاتی** lifestyle card نزدیک ۴:۳ دارد؛ گالری کالای تراول ماگ عکس‌های بلند دارد که باید امکان انتخاب fit و thumbnail را داشته باشد.
- **ژیمون** تصاویر دیجیتال اغلب مربع‌اند و کنتراست خود تصویر را نمی‌توان به تغییر palette گره زد؛ پس backdrop/card/chip باید جدا از artwork و قابل‌تغییر باشد.

# 14) رهنمود دقیق بازآفرینی برای طراحِ بدون دسترسی به اسکرین‌شات

طراح برای هر مرجع باید به‌ترتیب این لایه‌ها را بسازد. مقادیر پایین «Target پیشنهادی T» هستند و برای گزارش میدانی به‌عنوان CSS اصلی مرجع ادعا نمی‌شوند.

| شاخص | لیلیکا | لیلیوم | عسل بانو | دیزه | خانه شکلاتی | ژیمون |
|---|---|---|---|---|---|---|
| فونت محوری | iranyekan (C) | Vazirmatn/ fontsans (font-face C، انتخاب U) | IRANSansWeb_FaNum (C) | IRANYekanX/سایر؛ انتخاب U | iransansdn (C در CSS) | yekanbakh + rokh بعضی هدینگ‌ها (C) |
| احساس کلی | soft beauty | pink boutique | energetic campaign | quiet luxe | warm gifting | futuristic digital |
| رنگ شاخص | #AF726D (C) | #DB2777 (C stylesheet) | #EDB51F (C primary) + #FF6E1E (C stylesheet) | بژ/خاکی (T) | #704012 (C) | #06097F (C primary), #151B2D (C CSS) |
| سطح بدنه | صورتی خیلی کم‌رنگ (T) | سفید (V) | سفید/کرم (V) | سفید گرم (V) | آبی بسیار کم‌رنگ (V) | #070E1C (C CSS/V dark) |
| سطح کارت | سفید با border کم | سفید با border صورتی | سفید روی نارنجی/کرم | تقریبا بی‌کادر | سفید روی آبی کم‌رنگ | #151B2D / navy |
| تصویر کالا | white isolated | white isolated/pack | white isolated | lifestyle editorial | lifestyle/isolated | colorful square digital |
| ratio تصویر کارت هدف | 1:1/4:5 | 1:1 | 1:1 | 4:5 | 4:5 / 1:1 | 1:1 |
| CTA | رزگلد-filled | pink-filled | orange و success-green در PDP | sandy-muted | gold-filled + red secondary | electric-blue-filled |
| radius کارت هدف | 4–8 | 8–12 | 8–16 | 0–4 | 10–20 | 10–18 |
| homepage product view | carousel rows | carousel rows | campaign + carousel | editorial grid | mosaic + carousel | dense digital rows |
| PDP خاص | صورتی و فرم نظر | pink notices and tabs | bullet + FAQ + SEO | minimal photo-first | variant chips + buy outline | long digital description |
| mobile | stacking + 2-column cards | pink CTA full width | stories + orange deals | spacious photo grid | fixed bottom nav | robot hero stacked + gradient tiles |

### 14.1 دستورالعمل نمایش هر کامپوننت برای تیم فرانت‌اند

1. **Header:** لوگو و actions در desktop یک ردیف پایدار دارند؛ اگر design nav دوم می‌خواهد آن را از پیکربندی Global Header بساز. mobile: لوگو، search، menu trigger و سبد باید touch targets 44×44 CSS px هدف داشته باشند؛ هیچ آیکنی فقط بر اساس hover قابل استفاده نباشد.
2. **Hero:** main image wrap با `aspect-ratio` انتخابی و `object-fit`؛ content می‌تواند overlay یا split باشد. روی mobile حداقل ارتفاع ثابت نباید باعث crop نام محصولات شود. hide/show caption با breakpoints معنادار؛ alt text از merchant.
3. **Product shelves:** هر ردیف heading/optional subtitle/action link دارد؛ کارت‌ها در یک ردیف هم‌ارتفاع، با image frame مستقل، text clamping ۲ خط و price safe wrapping. Navigation RTL درست؛ Tab key و pointer/touch. Carousel باید با list/grid fallback برای reduced motion و بدون JS هم semantics معقول داشته باشد.
4. **Product card state:** sale item دارای old price strike و current price، بی‌تخفیف badge ندارد، ناموجود CTA disabled با text واضح، بدون تصویر placeholder عمومی، خرید دیجیتال label ارسال فیزیکی نگیرد. دکمه compare و wishlist تنها وقتی قابلیت فروشگاه وجود دارد نمایان شود.
5. **PDP:** انتخاب واریانت، قیمت و تعداد یک منبع state دارند؛ اگر CTA sticky موبایل فعال باشد با bottom nav overlap نداشته باشد. محصول بدون واریانت selector خالی نشان ندهد. thumbnails باید `contain` و object-position مناسب داشته باشند؛ Main gallery نباید به‌خاطر CSS تم background-image را از دست بدهد.
6. **Footer:** ترکیب سه‌تاچهار ستون desktop و آکاردئون/استک در mobile؛ social/contact/trust از Store data؛ لینک‌های خالی/شماره نمونه هرگز در Store منتشرشده ظاهر نشوند.
7. **Palette:** روی `canvas`, `card`, `modal`, `price`, `footer`, `nav`, `menu`, `hover`, `focus`, `disabled`, `sale`, `status` تست contrast انجام شود؛ تصاویر شخص ثالث بیرون حوزه theme هستند. Explicit overrides از Global Palette مستقل‌اند؛ UI باید provenance نمایش دهد و «بازگشت به پالت» داشته باشد.
8. **Designer controls:** هر control با typed schema، default/validation، preview و publish یکسان، Undo/Redo و version serialization؛ در Inspector «عدم پشتیبانی» به‌صورت disabled/hidden صریح و نه کنترل ظاهری بدون اثر نشان داده شود.
9. **Performance:** lazy loading برای تصاویر محصول نه first hero، image sizes و WebP/AVIF when available، جلوگیری از LCP hero بسیار بزرگ، offscreen carousel rendering فقط در حدی که SSR/SEO و accessibility آسیب نبیند.
10. **Localization:** همه labels/price units/digit styles از storefront locale و data واقعی؛ RTL `logical properties` (`margin-inline`, `inset-inline`) نه صدها override left/right مخصوص هر template؛ متن‌های طولانی، نام برند لاتین و قیمت فارسی کنار هم تست شوند.

*پایان سند.*
