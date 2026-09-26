# سند مرجع محصول و معماری فنی Rastisi — جلد اول

**نسخه:** 1.0  
**مبنای بررسی:** `rastisi-site.zip` و `novinshop-x25-industry-variants-cashback(2).zip`  
**ماهیت فایل‌های بررسی‌شده:** نمونه‌های Frontend/UX بدون Backend عملیاتی  
**هدف سند:** تبدیل دو نمونه بصری به مشخصات قابل پیاده‌سازی یک فروشگاه‌ساز SaaS چندمستاجری

> این سند از روی ساختار، صفحات، فرم‌ها، اسکریپت‌ها و READMEهای خود دو بسته تهیه شده است. هرجا درباره وضعیت موجود صحبت می‌شود، منظور قابلیت قابل مشاهده در Prototype است، نه Backend اجراشده. هرجا مدل، API یا سرویس پیشنهاد می‌شود، آن بخش طراحی لازم برای تکمیل محصول است.

## خلاصه اجرایی

Rastisi باید یک **پلتفرم SaaS فروشگاه‌ساز چندمستاجری** باشد، نه یک فروشگاه منفرد و نه صرفاً یک قالب HTML. مشتری در `rastisi.ir` ثبت‌نام می‌کند، پلن می‌خرد، صنف خود را انتخاب می‌کند و سامانه یک فروشگاه آماده با کاتالوگ و تنظیمات اولیه متناسب با صنف می‌سازد. دامنه عمومی فروشگاه می‌تواند کاملاً مستقل باشد؛ برای نمونه `digilool.ir`. پنل مدیریت همان فروشگاه باید روی زیردامنه پایدار Rastisi در دسترس باشد: `digilool.rastisi.ir/admin-portal/`.

دو فایل فعلی، در کنار هم، تقریباً Scope کامل محصول را نشان می‌دهند: فایل اول سایت بازاریابی، ثبت‌نام، پلن، پرداخت اشتراک و راه‌اندازی فروشگاه را نمایش می‌دهد؛ فایل دوم پنل فروشنده، تنظیمات، کاتالوگ، سفارش، پرداخت، پیامک، بازاریابی، گزارش، کیف پول و نمونه ویترین فروشگاه را نمایش می‌دهد. اما هیچ‌کدام Backend، دیتابیس، API، مجوز، Job، اتصال درگاه، تأیید دامنه یا جداسازی داده بین فروشگاه‌ها ندارند.

## دامنه دقیق محصول

- نوع محصول: SaaS چندفروشگاهی و چندمستاجری برای ساخت و اداره فروشگاه اینترنتی.
- کاربر خریدار پلتفرم: صاحب کسب‌وکار یا تیم فروشگاه (Merchant).
- کاربر فروشگاه: مشتری نهایی که از دامنه عمومی فروشگاه خرید می‌کند.
- اپراتور پلتفرم: تیم Rastisi که پلن‌ها، فروشگاه‌ها، دامنه‌ها، پرداخت اشتراک، پشتیبانی و تخلفات را مدیریت می‌کند.
- اصل مالکیت دامنه: دامنه عمومی متعلق به فروشنده است؛ پنل مدیریت روی زیرساخت و دامنه Rastisi می‌ماند.
- اصل جداسازی: همه داده‌های تجاری باید با `store_id` یا Tenant context جداسازی شوند.
- اصل آماده‌سازی صنفی: انتخاب صنف باید دسته‌ها، ویژگی‌ها، فیلترها، Variantها و محتوای پیشنهادی را Seed کند، اما فروشنده امکان ویرایش داشته باشد.

## معماری دامنه‌ها و URLها

### دامنه پلتفرم
- `https://rastisi.ir/` — سایت معرفی و جذب مشتری
- `https://rastisi.ir/register/` — ثبت‌نام فروشنده
- `https://rastisi.ir/login/` — ورود مرکزی فروشنده
- `https://rastisi.ir/plans/` — پلن‌ها
- `https://rastisi.ir/checkout/` — پرداخت اشتراک
- `https://rastisi.ir/account/` — حساب پلتفرمی فروشنده و فهرست فروشگاه‌ها

### دامنه پنل فروشنده
- الگو: `https://<admin_slug>.rastisi.ir/admin-portal/`
- نمونه: `https://digilool.rastisi.ir/admin-portal/`
- `admin_slug` باید یکتا، پایدار، رزروشده و مستقل از دامنه عمومی باشد.
- تغییر `digilool.ir` به دامنه دیگری نباید URL پنل را تغییر دهد.

### دامنه عمومی فروشگاه
- نمونه: `https://digilool.ir/`
- دامنه موقت قبل از اتصال دامنه شخصی می‌تواند `https://digilool.rastisi.shop/` یا زیردامنه‌ای جدا از دامنه پنل باشد.
- نباید پنل و Storefront روی یک Host با قواعد مبهم Resolver شوند.
- `www`، دامنه اصلی، دامنه جایگزین و Redirect canonical باید صریح مدیریت شوند.

### دامنه داخلی اپراتور
- پیشنهاد: `https://ops.rastisi.ir/` برای Super Admin پلتفرم
- این پنل از پنل فروشنده جداست و به StoreMembership وابسته نیست.
- دسترسی آن باید MFA، IP/risk controls و Audit Log سخت‌گیرانه داشته باشد.

### قواعد نام‌گذاری و رزرو زیردامنه

- حروف لاتین کوچک، عدد و خط تیره؛ بدون نقطه، underscore یا نویسه فارسی.
- طول پیشنهادی 3 تا 40 نویسه.
- نام‌های رزروشده: `www`, `api`, `admin`, `ops`, `static`, `media`, `mail`, `support`, `status`, `cdn`, `docs`, `blog`, `login` و همه نام‌های زیرساختی.
- بررسی شباهت و سوءاستفاده برای برندهای شناخته‌شده و نام‌های گمراه‌کننده.
- امکان تغییر کنترل‌شده با Redirect و دوره گذار، ولی نه تغییر خودکار پس از تغییر دامنه عمومی.

## آنچه دو فایل واقعاً پوشش می‌دهند

| بسته | تعداد صفحات HTML | نقش در محصول | وضعیت فنی |
| --- | --- | --- | --- |
| rastisi-site | 14 | سایت پلتفرم، معرفی، ثبت‌نام، پلن، Checkout اشتراک، Wizard ساخت فروشگاه و داشبورد ابتدایی | Static Frontend؛ فرم‌ها و جریان‌ها فاقد Backend |
| novinshop X25 | 45 | پنل فروشنده، تنظیمات، کاتالوگ، سفارش، گزارش، پیامک، بازاریابی، کیف پول، پشتیبانی و نمونه Storefront | Prototype؛ READMEها صریحاً localStorage و داده نمایشی را ذکر می‌کنند |

## شواهد فنی Prototype بودن

- README-X22 ذخیره برندها و چند قابلیت را نمایشی و مبتنی بر `localStorage` معرفی می‌کند.
- README-X23 ذخیره تنظیمات درگاه پرداخت و پیامک را در `localStorage` اعلام می‌کند.
- README-X24 پروژه را Frontend Prototype می‌نامد و نیاز Backend به whitelist و ذخیره JSON ساختاریافته را تصریح می‌کند.
- README-X25 نیاز به مدل داده، API، مجوز و اعتبارسنجی Backend را صریحاً ذکر می‌کند.
- در صفحات، endpoint واقعی API، session server-side، migration، model، queue و webhook وجود ندارد.

## نقش‌ها و بازیگران سیستم

| بازیگر | دامنه فعالیت | نیازهای اصلی |
| --- | --- | --- |
| بازدیدکننده پلتفرم | rastisi.ir | مشاهده امکانات، صنوف، پلن، FAQ و محتوا |
| فروشنده متقاضی | rastisi.ir | ثبت‌نام، تأیید موبایل/ایمیل، خرید پلن و ساخت فروشگاه |
| مالک فروشگاه | admin subdomain | مدیریت کامل فروشگاه، اشتراک، اعضا و تنظیمات حساس |
| مدیر فروشگاه | admin subdomain | مدیریت عملیاتی طبق مجوزهای واگذارشده |
| مدیر کاتالوگ | admin subdomain | محصول، دسته، برند، موجودی و Import |
| مدیر سفارش | admin subdomain | سفارش، ارسال، مرجوعی و مشتری |
| بازاریاب/محتوا | admin subdomain | CMS، کوپن، کمپین، شبکه اجتماعی و پیامک |
| حسابدار | admin subdomain | پرداخت، فاکتور، گزارش مالی و تسویه |
| مشتری نهایی | custom domain | مرور، سبد، Checkout، پرداخت، حساب، کیف پول و نظر |
| اپراتور Rastisi | ops.rastisi.ir | مدیریت Merchant، Store، Plan، Subscription، Domain، Support و Risk |
| Worker/System | داخلی | ایمیل، پیامک، webhook، verification، گزارش، import و زمان‌بندی |

## مرزهای زیرسیستم‌ها

| Bounded Context | مسئولیت |
| --- | --- |
| Platform Website | صفحات عمومی Rastisi، SEO، محتوا، پلن و Lead |
| Identity & Access | حساب فروشنده، OTP/MFA، Session، Membership و RBAC |
| Subscription & Billing | پلن، Trial، فاکتور اشتراک، پرداخت، تمدید و محدودیت |
| Store Provisioning | ساخت Store، Seed صنف، تنظیمات پیش‌فرض، admin slug و onboarding |
| Domain Management | دامنه عمومی، DNS challenge، SSL، canonical و health |
| Merchant Admin | پنل عملیاتی فروشنده روی زیردامنه Rastisi |
| Catalog | دسته، برند، محصول، ویژگی، Variant، قیمت، موجودی و Import |
| Storefront/CMS | صفحات، Theme، Section builder، منو، بنر، محتوا و SEO |
| Commerce | Cart، Checkout، Coupon، Order، Return، Payment و Shipping |
| CRM & Loyalty | Customer، Segment، Wallet، Cashback و Referral |
| Communication | SMS، Email، Template، Delivery log و notification |
| Analytics | KPI، report، export، attribution و event tracking |
| Support | Ticket، knowledge base و تعامل اپراتور |
| Platform Operations | Super admin، audit، monitoring، abuse و feature flags |

## تحلیل صفحه‌به‌صفحه سایت اصلی Rastisi

### درباره ما · راستیسی — `about.html`

**هدف UX:** درباره شرکت  
**Backend لازم:** CMS و داده‌های سازمانی  
**اجزای مشهود:** درباره راستیسی؛ چرا راستیسی به وجود آمد؟؛ راستیسی در یک نگاه؛ آنچه ما را متمایز می‌کند؛ سادگی اولویت اول؛ شفافیت کامل؛ نوآوری مستمر؛ ساخته شده برای ایران؛ به خانواده راستیسی بپیوندید  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### صنوف پشتیبانی‌شده · راستیسی — `categories.html`

**هدف UX:** فهرست صنوف قابل پشتیبانی  
**Backend لازم:** IndustryTemplate، جستجو، درخواست صنف جدید  
**اجزای مشهود:** صنوف پشتیبانی‌شده؛ صنف مورد نظر یافت نشد؛ صنف خود را پیدا نکردید؟  
**ورودی‌های مشهود:** جستجوی صنف شغلی...  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### تکمیل خرید · راستیسی — `checkout.html`

**هدف UX:** خرید اشتراک  
**Backend لازم:** SubscriptionCheckout، BillingProfile، PlatformPaymentAttempt  
**اجزای مشهود:** تکمیل خرید؛ اطلاعات صورتحساب؛ روش پرداخت؛ خلاصه سفارش  
**ورودی‌های مشهود:** نام شما، ۰۹۱۲...، you@example.com، کد ملی ۱۰ رقمی، payment، checkbox  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### تماس با ما · راستیسی — `contact.html`

**هدف UX:** تماس و Lead  
**Backend لازم:** ContactMessage، anti-spam، assignment و notification  
**اجزای مشهود:** با ما در تماس باشید؛ ارسال پیام  
**ورودی‌های مشهود:** نام شما، ۰۹۱۲...، you@example.com، select، پیام خود را بنویسید...  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### داشبورد · راستیسی — `dashboard.html`

**هدف UX:** داشبورد حساب پلتفرمی  
**Backend لازم:** Merchant account، subscriptions، stores، invoices و support  
**اجزای مشهود:** داشبورد فروشگاه؛ فروشگاه شما فعال است!؛ اقدامات سریع؛ آخرین سفارش‌ها  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### سوالات متداول · راستیسی — `faq.html`

**هدف UX:** پرسش‌های متداول  
**Backend لازم:** FAQCategory و FAQItem  
**اجزای مشهود:** سوالات متداول؛ سوال دیگری دارید؟  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### امکانات · راستیسی — `features.html`

**هدف UX:** شرح قابلیت‌ها  
**Backend لازم:** Feature catalog، مقایسه پلن و Feature availability  
**اجزای مشهود:** امکانات راستیسی؛ ۱۰۰+ قالب آماده صنفی؛ مدیریت محصولات پیشرفته؛ درگاه پرداخت چندگانه؛ مدیریت ارسال و لجستیک؛ داشبورد آماری کامل؛ کد تخفیف و کمپین؛ سرویس پیامک؛ مدیریت مشتریان (CRM)؛ اتصال دامنه اختصاصی؛ بهینه‌سازی موتور جستجو (SEO)؛ افزونه اینستاگرام  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### روش کار · راستیسی — `how-it-works.html`

**هدف UX:** آموزش جریان راه‌اندازی  
**Backend لازم:** CMS و onboarding steps  
**اجزای مشهود:** روش کار راستیسی؛ ثبت‌نام کنید؛ پلن خود را انتخاب کنید؛ فروشگاه خود را بسازید؛ دامنه اختصاصی (اختیاری)؛ فعال‌سازی و فروش؛ همین امروز شروع کنید  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### ساخت فروشگاه اینترنتی · راستیسی — `index.html`

**هدف UX:** صفحه فرود و معرفی ارزش محصول  
**Backend لازم:** CMS پلتفرم، Testimonial، Industry highlights، CTA tracking، SEO  
**اجزای مشهود:** فروشگاه اینترنتی خود را در ۵ دقیقه بسازید؛ هرآنچه برای فروش آنلاین نیاز دارید؛ راه‌اندازی سریع؛ ۱۰۰+ صنف آماده؛ زیردامنه اختصاصی؛ درگاه پرداخت؛ مدیریت محصولات؛ گزارش و تحلیل؛ از ثبت‌نام تا اولین فروش در ۵ گام؛ ثبت‌نام؛ انتخاب پلن؛ ساخت فروشگاه  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### ورود · راستیسی — `login.html`

**هدف UX:** ورود مرکزی  
**Backend لازم:** Authentication، session، MFA و store chooser  
**اجزای مشهود:** ورود به حساب  
**ورودی‌های مشهود:** ۰۹۱۲... یا you@example.com، ••••••••، checkbox  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### پلن‌ها و قیمت‌ها · راستیسی — `plans.html`

**هدف UX:** نمایش پلن‌ها  
**Backend لازم:** Plan، PricingVersion، FeatureLimit، مالیات و تخفیف  
**اجزای مشهود:** پلن خود را انتخاب کنید؛ سوالات متداول قیمت‌گذاری  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### ثبت‌نام · راستیسی — `register.html`

**هدف UX:** ثبت‌نام فروشنده  
**Backend لازم:** PlatformUser، OTPChallenge، Consent و anti-abuse  
**اجزای مشهود:** ساخت حساب کاربری  
**ورودی‌های مشهود:** مثال: علی محمدی، ۰۹۱۲۳۴۵۶۷۸۹، you@example.com، حداقل ۸ کاراکتر، checkbox  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### ساخت فروشگاه · راستیسی — `store-setup.html`

**هدف UX:** Wizard ساخت فروشگاه  
**Backend لازم:** ProvisioningRequest، Industry، Store، admin_slug و DomainIntent  
**اجزای مشهود:** صنف شغلی خود را انتخاب کنید؛ اطلاعات فروشگاه؛ انتخاب زیردامنه؛ اتصال دامنه اختصاصی (اختیاری)؛ فعال‌سازی فروشگاه؛ خلاصه اطلاعات فروشگاه  
**ورودی‌های مشهود:** جستجوی صنف (مثال: پوشاک، دیجیتال، خوراک...)، مثال: فروشگاه نوین، selectedCategoryDisplay، selectedCategory، مثال: بهترین کیفیت، بهترین قیمت، در یک یا دو خط، فروشگاه خود را معرفی کنید...، select، نام شهر، ۰۲۱-...، myshop، domain، myshop.ir  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

### فروشگاه فعال شد · راستیسی — `store-success.html`

**هدف UX:** نتیجه Provisioning  
**Backend لازم:** Provisioning status، next actions و domain instructions  
**اجزای مشهود:** فروشگاه شما فعال شد!  
**وضعیت فعلی:** فقط رابط کاربری؛ نیازمند validation سمت سرور، persistence، authorization، audit و handling خطا.

## تحلیل صفحه‌به‌صفحه پنل X25

### طراحی بصری · نوین‌شاپ — `appearance-settings.html`

**هدف UX:** تنظیم ظاهر  
**Backend لازم:** DesignToken، fonts، colors، logo، validation  
**بخش‌های دیده‌شده:** طراحی بصری  
**عملیات دیده‌شده:** ذخیره تغییرات  
**ورودی‌های دیده‌شده:** color، select  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### برندها · نوین‌شاپ — `brands.html`

**هدف UX:** برند  
**Backend لازم:** Brand CRUD، logo media، merge/disable  
**بخش‌های دیده‌شده:** مدیریت برندها؛ هنوز برندی ثبت نشده است  
**عملیات دیده‌شده:** + افزودن برند، دریافت فایل برندها، افزودن اولین برند، ✕، ＋ انتخاب یا کشیدن تصویر PNG، JPG، WEBP — حداکثر ۲ مگابایت، حذف تصویر، انصراف، ذخیره برند  
**ورودی‌های دیده‌شده:** جستجو با نام فارسی یا انگلیسی برند...، brandStatusFilter، brandId، brandLogoInput، مثلاً لانکوم، LANCOME، lancome، مثلاً فرانسه، معرفی کوتاه برند برای مشتری...، brandActive  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### اطلاعات حقوقی · نوین‌شاپ — `business-info.html`

**هدف UX:** اطلاعات حقوقی  
**Backend لازم:** LegalProfile، tax/business identifiers و verification  
**بخش‌های دیده‌شده:** اطلاعات حقوقی  
**عملیات دیده‌شده:** ذخیره اطلاعات  
**ورودی‌های دیده‌شده:** select، text، textarea  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### کش‌بک و کیف پول · نوین‌شاپ — `cashback-settings.html`

**هدف UX:** کش‌بک و کیف پول  
**Backend لازم:** CashbackRule، WalletLedger، expiry و return reversal  
**بخش‌های دیده‌شده:** دسته‌بندی‌ها؛ کش‌بک و کیف پول مشتریان؛ قانون کش‌بک؛ کنترل‌های مالی و بازگشت کالا؛ گردش نمونه کیف پول  
**عملیات دیده‌شده:** + افزودن دسته، 📊 خروجی اکسل، ویرایش، ›، ۱، ‹، ✕، ثبت، انصراف، ☰، ذخیره تنظیمات  
**ورودی‌های دیده‌شده:** جستجو...، text، cashbackEnabled، cashbackMin، cashbackPercent، cashbackDays، select، checkbox  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### دسته‌بندی‌ها · نوین‌شاپ — `categories.html`

**هدف UX:** دسته‌بندی  
**Backend لازم:** Category tree، ordering، slug، SEO، delete guards  
**بخش‌های دیده‌شده:** دسته‌بندی‌ها  
**عملیات دیده‌شده:** + افزودن دسته، 📊 خروجی اکسل، ویرایش، ›، ۱، ‹، ✕، ثبت، انصراف  
**ورودی‌های دیده‌شده:** جستجو...، text  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### بنرها و تخفیف · نوین‌شاپ — `coupons.html`

**هدف UX:** تخفیف و بنر  
**Backend لازم:** Coupon rule engine، Campaign، Banner و usage limits  
**بخش‌های دیده‌شده:** بنرها و تخفیف  
**عملیات دیده‌شده:** + ساخت کد تخفیف، ویرایش، حذف، ›، ۱، ‹، ✕، ساخت، انصراف  
**ورودی‌های دیده‌شده:** جستجوی کد...، مثال: NOVIN20، select، ۲۰، number، ۱۴۰۵/۰۶/۰۱  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### رفتار مشتریان · نوین‌شاپ — `customer-report.html`

**هدف UX:** تحلیل مشتری  
**Backend لازم:** cohort، RFM، retention و segment  
**بخش‌های دیده‌شده:** رفتار مشتریان  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### پایگاه مشتریان · نوین‌شاپ — `customers.html`

**هدف UX:** پایگاه مشتری  
**Backend لازم:** Customer profile، address، tags، consent، merge  
**بخش‌های دیده‌شده:** پایگاه مشتریان  
**عملیات دیده‌شده:** + افزودن مشتری، 📊 خروجی اکسل، مشاهده، ›، ۱، ‹، ✕، ثبت، انصراف  
**ورودی‌های دیده‌شده:** جستجوی مشتری...، text، email  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### سبدهای رها شده · نوین‌شاپ — `draft-orders.html`

**هدف UX:** سبد رهاشده  
**Backend لازم:** Cart session persistence، recovery campaign و consent  
**بخش‌های دیده‌شده:** سبدهای رها شده  
**عملیات دیده‌شده:** 📊 خروجی اکسل، یادآوری، ›، ۱، ‹  
**ورودی‌های دیده‌شده:** جستجو...  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### تنظیمات پایه · نوین‌شاپ — `general-configs.html`

**هدف UX:** تنظیمات پایه  
**Backend لازم:** StoreSetting schema، locale، currency، timezone  
**بخش‌های دیده‌شده:** تنظیمات پایه  
**عملیات دیده‌شده:** ذخیره تنظیمات  
**ورودی‌های دیده‌شده:** text، example.ir، email  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### مرکز آموزش · نوین‌شاپ — `guide.html`

**هدف UX:** مرکز آموزش  
**Backend لازم:** KnowledgeArticle، category، search و contextual help  
**بخش‌های دیده‌شده:** مرکز آموزش  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### صفحه نخست · نوین‌شاپ — `home-page-content.html`

**هدف UX:** محتوای خانه  
**Backend لازم:** HomepageSection، ordering، scheduling  
**بخش‌های دیده‌شده:** صفحه نخست  
**عملیات دیده‌شده:** ذخیره  
**ورودی‌های دیده‌شده:** text، textarea، checkbox، number  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### ورود گروهی محصولات · نوین‌شاپ — `import-products.html`

**هدف UX:** ورود گروهی  
**Backend لازم:** ImportJob، mapping، validation، dry-run، error file  
**بخش‌های دیده‌شده:** ورود گروهی محصولات  
**عملیات دیده‌شده:** دانلود فایل نمونه، شروع پردازش  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### داشبورد · نوین‌شاپ — `index.html`

**هدف UX:** داشبورد فروشنده  
**Backend لازم:** KPI service، aggregates، alerts، recent activity  
**بخش‌های دیده‌شده:** داشبورد  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### ساختار صنف و کاتالوگ · نوین‌شاپ — `industry-setup.html`

**هدف UX:** تنظیم ساختار صنف  
**Backend لازم:** IndustryTemplate copy، attribute schema، admin confirmation  
**بخش‌های دیده‌شده:** دسته‌بندی‌ها؛ ساختار صنف و کاتالوگ؛ پروفایل صنف؛ نتیجه راه‌اندازی؛ درخت دسته‌بندی پیشنهادی؛ ویژگی‌های استاندارد صنف  
**عملیات دیده‌شده:** + افزودن دسته، 📊 خروجی اکسل، ویرایش، ›، ۱، ‹، ✕، ثبت، انصراف، ☰، ذخیره ساختار فروشگاه، بارگذاری پیش‌نویس صنف  
**ورودی‌های دیده‌شده:** جستجو...، text، industrySelect  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### شبکه‌های اجتماعی · نوین‌شاپ — `instagram.html`

**هدف UX:** شبکه اجتماعی  
**Backend لازم:** SocialLink و در صورت API رسمی OAuth/token lifecycle  
**بخش‌های دیده‌شده:** شبکه‌های اجتماعی؛ اتصال به اینستاگرام  
**عملیات دیده‌شده:** اتصال اکانت  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### همکاری در فروش · نوین‌شاپ — `invite-friends.html`

**هدف UX:** همکاری در فروش/دعوت  
**Backend لازم:** ReferralProgram، ReferralCode، attribution و reward  
**بخش‌های دیده‌شده:** همکاری در فروش  
**عملیات دیده‌شده:** کپی  
**ورودی‌های دیده‌شده:** text  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### فاکتورها · نوین‌شاپ — `invoices.html`

**هدف UX:** فاکتورها  
**Backend لازم:** Invoice sequence، PDF، tax snapshot و immutable records  
**بخش‌های دیده‌شده:** فاکتورها  
**عملیات دیده‌شده:** دانلود  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### ورود · نوین‌شاپ — `login.html`

**هدف UX:** ورود پنل  
**Backend لازم:** در معماری نهایی redirect به ورود مرکزی یا session مشترک امن  
**عملیات دیده‌شده:** ورود به پنل  
**ورودی‌های دیده‌شده:** نام کاربری، ••••••••  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### رویدادهای سیستم · نوین‌شاپ — `logs.html`

**هدف UX:** رویدادهای سیستم  
**Backend لازم:** AuditEvent، security event و retention  
**بخش‌های دیده‌شده:** رویدادهای سیستم  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### بازاریابی و رشد · نوین‌شاپ — `marketing.html`

**هدف UX:** بازاریابی  
**Backend لازم:** Campaign، segment، channel، attribution و consent  
**بخش‌های دیده‌شده:** بازاریابی و رشد  
**عملیات دیده‌شده:** شروع، مدیریت، فعال‌سازی، مشاهده  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### ثبت و مدیریت سفارش · نوین‌شاپ — `order-new.html`

**هدف UX:** سفارش دستی  
**Backend لازم:** Draft order، customer lookup، pricing، stock reservation  
**بخش‌های دیده‌شده:** ثبت و مدیریت سفارش  
**عملیات دیده‌شده:** ✕، + افزودن محصول، ثبت نهایی سبد، ذخیره یادداشت، تایید، آماده‌سازی، ارسال، تحویل، لغو، اعمال، + مشتری جدید، ثبت کد  
**ورودی‌های دیده‌شده:** توضیحات سفارش از دید مشتری...، select، text، کد رهگیری پستی، number  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### تحلیل فروش · نوین‌شاپ — `order-report.html`

**هدف UX:** تحلیل فروش  
**Backend لازم:** revenue، AOV، status، channel، date dimensions  
**بخش‌های دیده‌شده:** تحلیل فروش  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### قوانین سفارش · نوین‌شاپ — `order-settings.html`

**هدف UX:** قوانین سفارش  
**Backend لازم:** OrderPolicy، minimum، cancellation و numbering  
**بخش‌های دیده‌شده:** قوانین سفارش  
**عملیات دیده‌شده:** ذخیره  
**ورودی‌های دیده‌شده:** checkbox، حداقل مبلغ به تومان، حداکثر مبلغ  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### لیست سفارش‌ها · نوین‌شاپ — `orders.html`

**هدف UX:** لیست سفارش  
**Backend لازم:** Order search، state machine، export، permissions  
**بخش‌های دیده‌شده:** لیست سفارش‌ها  
**عملیات دیده‌شده:** 📊 خروجی اکسل، ›، ۱، ۲، ‹  
**ورودی‌های دیده‌شده:** جستجوی شماره سفارش یا نام مشتری...  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### بازخورد صفحات · نوین‌شاپ — `page-comments.html`

**هدف UX:** بازخورد صفحات  
**Backend لازم:** PageFeedback، moderation و privacy  
**بخش‌های دیده‌شده:** بازخورد صفحات؛ بازخوردی ثبت نشده  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### صفحات سایت · نوین‌شاپ — `pages.html`

**هدف UX:** صفحات سایت  
**Backend لازم:** Page CRUD، slug، SEO، draft/version/publish  
**بخش‌های دیده‌شده:** صفحات سایت  
**عملیات دیده‌شده:** + افزودن صفحه، 📊 خروجی اکسل، ویرایش، ›، ۱، ‹، ✕، ثبت، انصراف  
**ورودی‌های دیده‌شده:** جستجو...، text  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### درگاه‌های پرداخت · نوین‌شاپ — `payment-settings.html`

**هدف UX:** درگاه‌ها  
**Backend لازم:** GatewayAccount encrypted config، test/live mode، webhook secret  
**بخش‌های دیده‌شده:** روش‌های پرداخت  
**عملیات دیده‌شده:** ✕، ذخیره، انصراف  
**ورودی‌های دیده‌شده:** جستجو در درگاه‌های پرداخت...، gatewayType، codEnabled، codTitle، codMax، modalEnabled، modalOrder، modalCustomTitle، modalSandbox  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### تراکنش‌های مالی · نوین‌شاپ — `payments.html`

**هدف UX:** تراکنش‌ها  
**Backend لازم:** PaymentAttempt، verification، reconcile و refund  
**بخش‌های دیده‌شده:** تراکنش‌های مالی  
**عملیات دیده‌شده:** 📊 خروجی اکسل، ›، ۱، ‹  
**ورودی‌های دیده‌شده:** جستجوی تراکنش...  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### نظرات کاربران · نوین‌شاپ — `product-comments.html`

**هدف UX:** نظرات محصول  
**Backend لازم:** Review moderation، rating، abuse و merchant reply  
**بخش‌های دیده‌شده:** نظرات کاربران  
**عملیات دیده‌شده:** مشاهده، تایید  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### افزودن محصول جدید · نوین‌شاپ — `product-create.html`

**هدف UX:** ساخت محصول  
**Backend لازم:** Product aggregate، media upload، variant builder، validation  
**بخش‌های دیده‌شده:** افزودن محصول جدید  
**عملیات دیده‌شده:** + برند جدید، + افزودن تنوع، B، I، U، ≡، 🔗، عطر و ادکلن، پوشاک، لوازم یدکی، موبایل، سفارشی  
**ورودی‌های دیده‌شده:** نام محصول، English Title، select، ۰، checkbox، ۶۲۶...، SKU، طول × عرض × ارتفاع، مشکی، سفید، آبی، پلاستیک، فلز، ژاپن، ۱۸ ماه، productBrandSelect، با کاما جدا کنید، توضیحات کامل محصول...، https://www.aparat.com/v/... یا https://youtu.be/...، مثلاً بررسی و روش استفاده، اختیاری، عنوان برای موتورهای جستجو، توضیحات متای محصول  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### ویرایش محصول · نوین‌شاپ — `product-edit.html`

**هدف UX:** ویرایش محصول  
**Backend لازم:** Optimistic locking/version، audit، draft/publish  
**بخش‌های دیده‌شده:** ویرایش محصول  
**عملیات دیده‌شده:** + برند جدید، + افزودن تنوع، B، I، U، ≡، 🔗، عطر و ادکلن، پوشاک، لوازم یدکی، موبایل، سفارشی  
**ورودی‌های دیده‌شده:** نام محصول، English Title، select، ۰، checkbox، ۶۲۶...، SKU، طول × عرض × ارتفاع، مشکی، سفید، آبی، پلاستیک، فلز، ژاپن، ۱۸ ماه، productBrandSelect، با کاما جدا کنید، توضیحات کامل محصول...، https://www.aparat.com/v/... یا https://youtu.be/...، مثلاً بررسی و روش استفاده، اختیاری، عنوان برای موتورهای جستجو، توضیحات متای محصول  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### عملکرد محصولات · نوین‌شاپ — `product-report.html`

**هدف UX:** تحلیل محصول  
**Backend لازم:** sales، margin، conversion، stock turns  
**بخش‌های دیده‌شده:** عملکرد محصولات  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### همه محصولات · نوین‌شاپ — `products.html`

**هدف UX:** لیست محصولات  
**Backend لازم:** Product query/filter، pagination، bulk actions، permissions  
**بخش‌های دیده‌شده:** همه محصولات  
**عملیات دیده‌شده:** ویرایش گروهی، 📊 خروجی اکسل، ›، ۱، ‹  
**ورودی‌های دیده‌شده:** جستجوی محصول...  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### لجستیک و ارسال · نوین‌شاپ — `shipping-settings.html`

**هدف UX:** ارسال  
**Backend لازم:** ShippingMethod، zone، rate rule، carrier integration  
**بخش‌های دیده‌شده:** لجستیک و ارسال  
**عملیات دیده‌شده:** + افزودن روش ارسال، ویرایش، ✕، ثبت، انصراف  
**ورودی‌های دیده‌شده:** text، select، number  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### قالب‌های پیام · نوین‌شاپ — `sms-custom.html`

**هدف UX:** قالب پیامک  
**Backend لازم:** MessageTemplate، variables، approval و version  
**بخش‌های دیده‌شده:** قالب‌های پیامک  
**ورودی‌های دیده‌شده:** جستجو در عنوان یا متن قالب...، categoryFilter  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### تنظیمات درگاه پیامک · نوین‌شاپ — `sms-gateway-settings.html`

**هدف UX:** درگاه پیامک  
**Backend لازم:** ProviderCredential encrypted، sender line، health check  
**بخش‌های دیده‌شده:** تنظیمات درگاه پیامک؛ تنظیمات ارسال  
**عملیات دیده‌شده:** نمایش، ذخیره تنظیمات، آزمایش اتصال، ارسال پیام آزمایشی  
**ورودی‌های دیده‌شده:** smsProvider، gatewayEnabled، API Key، مثلاً 3000xxxx، smsUsername، smsPassword، https://api.example.com/v1/sms، countryCode، retryCount، normalizePhone، deliveryReport، 0912xxxxxxx، testMessage  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### صندوق پیام‌ها · نوین‌شاپ — `sms-list.html`

**هدف UX:** صندوق پیام  
**Backend لازم:** MessageLog، status، filtering و PII protection  
**بخش‌های دیده‌شده:** صندوق پیام‌ها  
**عملیات دیده‌شده:** + ارسال پیام، 📊 خروجی اکسل، ✕، ارسال، انصراف  
**ورودی‌های دیده‌شده:** ۰۹۱۲...، textarea  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### آمار پیام‌ها · نوین‌شاپ — `sms-report.html`

**هدف UX:** گزارش پیامک  
**Backend لازم:** delivery metrics، cost، provider و failure reason  
**بخش‌های دیده‌شده:** آمار پیام‌ها  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### استودیو ساخت فروشگاه — `store-editor.html`

**هدف UX:** صفحه‌ساز/طراحی  
**Backend لازم:** ThemeVersion، section schema، preview، publish rollback  
**بخش‌های دیده‌شده:** خانه‌ی طراحی  
**عملیات دیده‌شده:** ↶ بازگشت، ذخیره، پیش‌نمایش، رایانه، تبلت، موبایل، بستن  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### برندها | فروشگاه — `storefront-brands.html`

**هدف UX:** ویترین برندها  
**Backend لازم:** Storefront query و brand landing pages  
**بخش‌های دیده‌شده:** برند دلخواهتان را پیدا کنید  
**ورودی‌های دیده‌شده:** مثلاً لانکوم یا LANCOME  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### فروشگاه زیبایی — `storefront.html`

**هدف UX:** نمونه ویترین  
**Backend لازم:** Storefront read model، cart، checkout و customer identity  
**بخش‌های دیده‌شده:** سبد خرید  
**عملیات دیده‌شده:** ☰، ♙، 🛍 ۰، عضویت، ×، ادامه فرایند خرید، ⌂ خانه، ⌕ محصولات، ♙ حساب، 🛍 سبد خرید  
**ورودی‌های دیده‌شده:** جستجو میان محصولات و برندها...، شماره موبایل شما  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### پلن اشتراک · نوین‌شاپ — `subscription.html`

**هدف UX:** اشتراک Rastisi  
**Backend لازم:** Subscription، usage، invoice، upgrade/downgrade  
**بخش‌های دیده‌شده:** پلن اشتراک؛ پایه؛ حرفه‌ای؛ سازمانی  
**عملیات دیده‌شده:** انتخاب، فعلی  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### پشتیبانی · نوین‌شاپ — `ticketing.html`

**هدف UX:** پشتیبانی  
**Backend لازم:** Ticket، message، attachment، SLA و assignment  
**بخش‌های دیده‌شده:** پشتیبانی  
**عملیات دیده‌شده:** + تیکت جدید، مشاهده، ✕، ثبت، انصراف  
**ورودی‌های دیده‌شده:** جستجو...، text، select، textarea  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

### گردش کیف پول · نوین‌شاپ — `wallet-transactions.html`

**هدف UX:** گردش کیف پول  
**Backend لازم:** Immutable ledger، balance projection، adjustment permission  
**بخش‌های دیده‌شده:** گردش کیف پول  
**الزامات مشترک:** Tenant scope، permission، validation، audit، pagination/locking در صورت نیاز، پیام خطای قابل فهم و تست مستقل.

## مدل دامنه پیشنهادی

در این بخش مدل‌ها به‌عنوان Aggregate و Entity پیشنهادی تعریف می‌شوند. نام‌ها نمونه‌اند و می‌توانند در Django مطابق Naming Convention پروژه نهایی شوند.
### هویت و سازمان

- `User`
- `UserIdentity`
- `OTPChallenge`
- `MFADevice`
- `LoginSession`
- `Merchant`
- `MerchantProfile`
- `ConsentRecord`

### فروشگاه و عضویت

- `Store`
- `StoreMembership`
- `StoreRole`
- `RolePermission`
- `Invitation`
- `StoreStatusHistory`

### دامنه و زیرساخت

- `StoreAdminHost`
- `StoreDomain`
- `DomainVerification`
- `DomainDNSRecord`
- `CertificateRecord`
- `DomainHealthCheck`

### اشتراک پلتفرم

- `Plan`
- `PlanVersion`
- `PlanFeature`
- `Subscription`
- `SubscriptionChange`
- `SubscriptionInvoice`
- `PlatformPaymentAttempt`
- `UsageCounter`
- `FeatureEntitlement`

### راه‌اندازی و صنف

- `ProvisioningRequest`
- `ProvisioningStep`
- `Industry`
- `IndustryTemplate`
- `IndustryCategoryTemplate`
- `IndustryAttributeTemplate`
- `IndustryFilterTemplate`
- `TemplateVersion`

### کاتالوگ

- `Category`
- `Brand`
- `Product`
- `ProductTranslation`
- `ProductMedia`
- `ProductContentBlock`
- `AttributeDefinition`
- `AttributeOption`
- `ProductAttributeValue`
- `VariantAxis`
- `ProductVariant`
- `VariantOptionValue`
- `VariantMedia`
- `Price`
- `InventoryItem`
- `StockMovement`
- `ImportJob`
- `ImportRowError`

### فروش و سفارش

- `Cart`
- `CartItem`
- `CheckoutSession`
- `Coupon`
- `CouponRedemption`
- `Order`
- `OrderItem`
- `OrderAddressSnapshot`
- `OrderStatusHistory`
- `Invoice`
- `ReturnRequest`
- `ReturnItem`
- `Refund`

### پرداخت و ارسال

- `StoreGatewayAccount`
- `PaymentAttempt`
- `PaymentEvent`
- `Payout/ReconciliationRecord`
- `ShippingMethod`
- `ShippingZone`
- `ShippingRateRule`
- `Shipment`
- `ShipmentEvent`

### مشتری و وفاداری

- `Customer`
- `CustomerIdentity`
- `CustomerAddress`
- `CustomerTag`
- `CustomerConsent`
- `WalletAccount`
- `WalletTransaction`
- `CashbackRule`
- `CashbackGrant`
- `ReferralProgram`
- `ReferralCode`
- `ReferralAttribution`
- `ReferralReward`

### محتوا و ظاهر

- `Page`
- `PageVersion`
- `Menu`
- `MenuItem`
- `Theme`
- `ThemeVersion`
- `DesignTokenSet`
- `HomepageSection`
- `Banner`
- `SEORecord`
- `SocialLink`

### ارتباطات

- `Notification`
- `MessageTemplate`
- `TemplateVersion`
- `SMSProviderAccount`
- `EmailProviderAccount`
- `MessageDelivery`
- `WebhookEndpoint`
- `WebhookDelivery`

### پشتیبانی و عملیات

- `Ticket`
- `TicketMessage`
- `TicketAttachment`
- `KnowledgeArticle`
- `AuditEvent`
- `SecurityEvent`
- `FeatureFlag`
- `BackgroundJobRecord`
- `DataExportJob`

## مشخصات مدل‌های هسته‌ای

| مدل | نقش | فیلدهای کلیدی | قید/قاعده مهم |
| --- | --- | --- | --- |
| Store | tenant اصلی | id, merchant_id, name, slug, admin_slug, status, industry_id, timezone, locale, currency, created_at | admin_slug یکتا؛ soft-delete/status؛ هیچ Query تجاری بدون store scope |
| StoreAdminHost | Host پنل | store_id, hostname, is_primary, status | برای `<slug>.rastisi.ir`؛ رزرو نام؛ history تغییر |
| StoreDomain | دامنه عمومی | store_id, hostname, type, is_primary, status, verified_at | hostname globally unique؛ canonical redirect؛ www policy |
| StoreMembership | عضویت تیم | store_id, user_id, role_id, status, joined_at | unique(store,user)؛ owner protection؛ invitation lifecycle |
| PlanVersion | تعریف نسخه‌دار پلن | plan_id, version, price, billing_period, limits_json, active_from | قیمت و Limit گذشته نباید mutate شود |
| Subscription | اشتراک فروشنده | merchant/store scope, plan_version_id, status, trial_end, current_period_end | state machine؛ grace period؛ entitlement snapshot |
| IndustryTemplate | الگوی صنفی | industry_id, version, status, schema_json | فقط نسخه تأییدشده Seed شود؛ Store copy مستقل ایجاد شود |
| Product | ریشه محصول | store_id, category_id, brand_id, title, slug, status, description, seo | unique(store,slug)؛ draft/published؛ optimistic version |
| ProductVariant | ترکیب قابل فروش | product_id, sku, price, compare_at_price, stock_policy, active | SKU حداقل در Store یکتا؛ تصویر و موجودی اختصاصی |
| Order | سفارش immutable نسبی | store_id, customer_id, number, status, totals, currency, snapshots | شماره در Store یکتا؛ قیمت و آدرس snapshot؛ transition کنترل‌شده |
| PaymentAttempt | تلاش پرداخت | store_id/order_id, gateway, amount, status, authority, idempotency_key | idempotency؛ callback verify؛ raw payload redaction |
| WalletTransaction | دفتر کل کیف پول | wallet_id, type, amount, reference, expires_at, reversal_of | append-only؛ balance از ledger؛ adjustment audit |
| AuditEvent | رخداد ممیزی | store_id?, actor_id, action, entity, entity_id, metadata, ip, created_at | append-only؛ اطلاعات حساس redact؛ retention policy |

## روابط اصلی داده

```text
Merchant 1 ── * Store
User * ── * Store  (through StoreMembership)
Store 1 ── * StoreDomain
Store 1 ── 1..* StoreAdminHost
Store * ── 1 Industry
Industry 1 ── * IndustryTemplate(versioned)
Store 1 ── * Category / Brand / Product / Customer / Order / Page
Product 1 ── * ProductVariant
ProductVariant 1 ── * InventoryItem / VariantMedia
Customer 1 ── * Order / Address / WalletAccount
Order 1 ── * OrderItem / PaymentAttempt / Shipment / Refund
Store 1 ── * StoreGatewayAccount / SMSProviderAccount / ShippingMethod
Subscription * ── 1 PlanVersion
```

## معماری چندمستاجری و جداسازی داده

- مدل پیشنهادی اولیه: Shared database و Shared schema با `store_id` روی همه داده‌های Tenant-owned.
- Tenant از Host و Session resolution می‌شود، اما `store_id` هرگز از ورودی خام کاربر بدون کنترل گرفته نمی‌شود.
- تمام Repository/Managerها باید scoped باشند؛ استفاده مستقیم از Model manager عمومی در لایه View ممنوع شود.
- Unique constraintها Tenant-aware باشند، مانند `UniqueConstraint(store_id, slug)` و `UniqueConstraint(store_id, sku)`.
- Cache key، فایل media، export، task و webhook باید `store_id` را در namespace داشته باشند.
- Jobها باید Store context را در payload داشته و پیش از اجرا فعال بودن Store و entitlement را دوباره بررسی کنند.
- تست‌های cross-tenant برای Read، Update، Delete، Export، Media و Background jobs اجباری‌اند.
- برای عملیات حساس می‌توان PostgreSQL Row-Level Security را در فاز سخت‌سازی بررسی کرد؛ ولی جایگزین scope در برنامه نیست.

## احراز هویت و مجوزها

### جریان ورود فروشنده
```text
rastisi.ir/login → احراز هویت → انتخاب Membership فعال → صدور/تثبیت Session → redirect به <admin_slug>.rastisi.ir/admin-portal/
```

- Cookie دامنه مشترک فقط در صورت نیاز و با `Domain=.rastisi.ir`, `Secure`, `HttpOnly`, `SameSite=Lax/Strict` و rotation مدیریت شود.
- روش امن‌تر برای cross-subdomain می‌تواند Authorization Code یک‌بارمصرف کوتاه‌عمر باشد که پنل آن را exchange می‌کند.
- فروشنده بدون Membership فعال نباید با صرف `is_staff` یا دانستن URL وارد Store شود.
- Owner، Admin، CatalogManager، OrderManager، ContentEditor، Marketer، Accountant، Analyst و SupportAgent نقش‌های پایه‌اند.
- MFA برای Owner، تغییر دامنه، درگاه، اعضا، برداشت/تسویه و تغییر اشتراک توصیه و برای عملیات حساس اجباری شود.
- مجوزها action-based باشند: `catalog.product.create`, `orders.refund`, `settings.gateway.update` و غیره.

## ماتریس مجوز پیشنهادی

| قابلیت | Owner | Admin | Catalog | Orders | Marketing | Accounting | Analyst |
| --- | --- | --- | --- | --- | --- | --- | --- |
| مدیریت اعضا | ✓ | محدود | — | — | — | — | — |
| دامنه و اشتراک | ✓ | مشاهده/محدود | — | — | — | مشاهده | — |
| محصول و موجودی | ✓ | ✓ | ✓ | مشاهده | مشاهده | مشاهده | مشاهده |
| سفارش و مرجوعی | ✓ | ✓ | مشاهده | ✓ | مشاهده | مشاهده | مشاهده |
| Refund | ✓ | طبق سقف | — | طبق سقف | — | ✓ | — |
| محتوا و کمپین | ✓ | ✓ | مشاهده | — | ✓ | — | مشاهده |
| درگاه و مالی | ✓ | محدود | — | — | — | ✓ | مشاهده |
| گزارش | ✓ | ✓ | محصول | سفارش | کمپین | مالی | ✓ |

## چرخه ثبت‌نام، خرید و تحویل فروشگاه

| مرحله | Backend/کنترل لازم |
| --- | --- |
| ثبت حساب | موبایل/ایمیل، رمز یا OTP، پذیرش قوانین، anti-bot |
| تأیید هویت پایه | تأیید کانال ارتباطی و جلوگیری از حساب تکراری |
| انتخاب پلن | PlanVersion و نمایش Limits دقیق |
| پرداخت اشتراک | PlatformPaymentAttempt، verify و invoice |
| ایجاد Merchant | پروفایل صاحب حساب |
| دریافت اطلاعات فروشگاه | نام، صنف، admin_slug، locale و currency |
| رزرو admin_slug | transactional uniqueness و reserved words |
| Provisioning | ایجاد Store، Owner Membership، تنظیمات، Theme و Seed صنف |
| فعال‌سازی پنل | صدور Session/redirect به admin host |
| اتصال دامنه عمومی | ثبت DomainIntent، نمایش DNS، verification و SSL |
| Go-live checklist | درگاه، ارسال، قوانین، محصول، test order و انتشار |

## سیستم صنف و کاتالوگ آماده

X25 صفحه `industry-setup.html` و اسکریپت `x25-catalog.js` را برای ساختار صنف معرفی می‌کند. این قابلیت نباید مستقیماً Categoryهای سراسری را به Store متصل کند؛ باید یک Template نسخه‌دار داشته باشیم و هنگام Provisioning نسخه‌ای قابل ویرایش در Store ساخته شود.

- Industry: شناسه صنف مانند پوشاک، عطر، موبایل، لوازم یدکی.
- Category template: درخت دسته پیشنهادی.
- Attribute template: ویژگی‌هایی مثل رنگ، سایز، رایحه، حافظه، مدل خودرو.
- Usage: هر ویژگی مشخص کند برای Specification، Filter، Variant axis یا Rich content استفاده می‌شود.
- Option set: گزینه‌های استاندارد و قابل توسعه توسط فروشنده.
- Validation schema: نوع داده، واحد، محدوده، required و الگوی نمایش.
- Versioning: تغییر Template جدید نباید Storeهای موجود را ناخواسته mutate کند.
- Admin approval: Template قبل از انتشار باید review و publish شود.
- Override: فروشنده می‌تواند نسخه Store خود را ویرایش کند، بدون تغییر Template مرکزی.

## Variant Engine

- Variant axisها مانند رنگ، سایز و جنس باید از AttributeDefinition قابل انتخاب باشند.
- ترکیب Variantها باید server-side تولید و از انفجار ترکیبی کنترل شود.
- هر Variant: SKU، barcode، قیمت، compare price، cost، موجودی، وزن، تصویر و وضعیت مستقل.
- تصویر اختصاصی Variant برای سناریوی انتخاب رنگ ضروری است؛ Storefront پس از انتخاب رنگ باید رسانه مرتبط را نمایش دهد.
- قواعد جلوگیری از SKU تکراری، Variant تکراری و Option نامعتبر لازم است.
- برای محصول بدون Variant نیز یک default sellable unit داخلی یا مسیر ساده مشخص شود.
- ویرایش bulk و matrix برای قیمت/موجودی لازم است.
- حذف Attribute استفاده‌شده باید guard و migration UX داشته باشد.

## Rich Product Content و ویدئو

- ProductContentBlock با انواع text، image، video، feature_group، comparison و FAQ.
- ذخیره ساختاریافته JSON با schema version؛ نه HTML خام بدون کنترل.
- Whitelist و normalize لینک YouTube/آپارات؛ iframe خام از کاربر پذیرفته نشود.
- Sanitization برای محتوای HTML و سیاست CSP مناسب.
- ترتیب، draft/publish، preview و قابلیت غیرفعال‌سازی Blockها.
- Media باید Store-scoped، دارای size/type validation و پردازش async باشد.

## Commerce: سبد، Checkout، سفارش و پرداخت

### Cart و Checkout
- Cart مهمان با token امن و Cart کاربر ثبت‌شده با merge policy.
- قیمت، موجودی، Coupon و Shipping در لحظه Checkout دوباره محاسبه شوند.
- CheckoutSession دارای expiry و idempotency باشد.
- اطلاعات سفارش snapshot شود تا تغییر محصول/قیمت سابقه را تغییر ندهد.
- قوانین حداقل سفارش، مناطق ارسال و ظرفیت موجودی Store-specific باشند.

### Order state machine
```text
draft → pending_payment → paid → processing → ready_to_ship → shipped → delivered
             ↘ payment_failed / cancelled
delivered → return_requested → returned → refunded(partial/full)
```

### پرداخت
- درگاه فروشگاه با Credential رمزگذاری‌شده و جداسازی test/live.
- PaymentAttempt با idempotency key و authority unique مناسب.
- Callback مرورگر فقط trigger است؛ نتیجه نهایی با verify سرور-به-سرور تعیین شود.
- Webhook/callback تکراری نباید سفارش را دوبار Paid کند.
- Reconciliation job برای تطبیق تراکنش‌های نامشخص.
- Refund و partial refund باید مدل و مجوز مستقل داشته باشند.

## Subscription و Billing پلتفرم

- پرداخت اشتراک Rastisi از پرداخت سفارش‌های فروشگاه کاملاً جدا باشد.
- Planها versioned باشند و Limits شامل تعداد محصول، کاربر، دامنه، پیامک، Storage و امکانات شوند.
- وضعیت‌ها: trialing، active، past_due، grace_period، suspended، cancelled، expired.
- Upgrade فوری با proration یا از دوره بعد؛ Downgrade با بررسی مصرف فعلی.
- عدم تمدید ابتدا Grace، سپس محدودکردن عملیات write و در نهایت تعلیق کنترل‌شده؛ داده فوراً حذف نشود.
- Entitlement در Backend enforce شود، نه فقط مخفی‌کردن دکمه در UI.
- Invoice و PaymentAttempt اشتراک قابل Audit و مستقل از Store order باشند.

## مدیریت دامنه عمومی

### جریان
```text
Add domain → Normalize → Ownership challenge → DNS check → Verified → Route config → Certificate → Health check → Primary/canonical
```

- پشتیبانی از A/AAAA یا CNAME طبق معماری Hosting.
- TXT challenge برای اثبات مالکیت، مخصوصاً هنگام انتقال دامنه بین Storeها.
- Worker دوره‌ای برای DNS propagation و health check.
- صدور و تمدید خودکار TLS؛ ثبت خطا و هشدار قبل از انقضا.
- جلوگیری از ثبت localhost، IP، دامنه Rastisi رزروشده و Hostهای نامعتبر.
- مدیریت apex و www، HTTPS redirect و canonical host.
- حذف دامنه با cooldown و جلوگیری از takeover.

## Store Builder و CMS

- نسخه اول به‌جای Drag & Drop آزاد، Section Builder schema-driven باشد.
- Section types: Hero، ProductCollection، CategoryGrid، Banner، Text، Image، Video، BrandGrid، Newsletter و FAQ.
- هر Section دارای schema معتبر، visibility، schedule و ordering.
- ThemeVersion و PageVersion برای Draft، Preview، Publish و Rollback.
- Design tokens برای رنگ، فونت، spacing، radius و button style.
- Preview token کوتاه‌عمر؛ Preview منتشرنشده نباید عمومی index شود.
- SEORecord برای title، description، canonical، open graph و structured data.

## Cashback، Wallet و Referral

### Wallet Ledger
- Balance نباید یک عدد قابل ویرایش مستقیم باشد؛ از جمع تراکنش‌های immutable محاسبه یا projection شود.
- انواع تراکنش: cashback_credit، referral_credit، purchase_debit، expiry، refund_reversal، admin_adjustment.
- هر تراکنش reference یکتا و idempotency داشته باشد.
- انقضا با Job و ledger entry انجام شود، نه حذف رکورد.
- مرجوعی باید Cashback اعطاشده را طبق Rule معکوس کند.

### Cashback Rule
- درصد/مبلغ ثابت، حداقل سفارش، سقف، محصولات/دسته‌های مشمول، زمان فعال، expiration و stack policy.
- زمان اعطا بهتر است پس از Delivered یا پایان پنجره مرجوعی باشد.
- نمایش شفاف شرایط به مشتری و ثبت Rule snapshot روی Grant.

### Referral
- کد/لینک یکتا، attribution window، first/last touch مشخص، جلوگیری از self-referral و abuse.
- پاداش دعوت‌کننده و دعوت‌شونده با status pending/approved/rejected.
- تأیید پس از رخداد معتبر مثل اولین سفارش تحویل‌شده.

## پیامک و ارتباطات

- Provider adapter برای سرویس‌های مختلف؛ Credential رمزگذاری‌شده.
- Templateهای سیستمی و سفارشی با متغیرهای whitelist شده.
- Queue برای ارسال، retry با backoff و dead-letter handling.
- MessageDelivery شامل provider message id، هزینه، status و failure reason.
- Consent و opt-out برای پیام‌های تبلیغاتی؛ پیام تراکنشی جدا.
- Rate limit و جلوگیری از ارسال تکراری.
- گزارش تحویل از callback provider و reconciliation دوره‌ای.

## گزارش و رویداد

- Event taxonomy از ابتدا تعریف شود: product_view، add_to_cart، checkout_started، order_paid و غیره.
- رویداد Analytics از AuditEvent جداست؛ یکی محصولی و دیگری امنیتی/عملیاتی است.
- گزارش‌های سنگین async ساخته و فایل Export با URL امضاشده و expiry ارائه شود.
- Timezone Store و currency در aggregation رعایت شود.
- KPIهای نمونه: GMV، net revenue، AOV، conversion، repeat rate، abandonment، refund rate و stock-out.

## API پیشنهادی

| حوزه | Endpointهای نمونه |
| --- | --- |
| Platform Auth | POST /api/platform/auth/register, verify, login, logout, refresh |
| Plans | GET /api/platform/plans; POST /api/platform/subscription-checkouts |
| Provisioning | POST /api/platform/stores; GET /api/platform/provisioning/{id} |
| Store switch | POST /api/platform/store-sessions یا code exchange |
| Domains | POST/GET/DELETE /api/admin/domains; POST verify; POST make-primary |
| Catalog | /api/admin/products, variants, categories, brands, attributes |
| Imports | POST /api/admin/imports; GET status/errors |
| Orders | /api/admin/orders; transitions; refunds; shipments |
| Customers | /api/admin/customers, tags, segments, wallet |
| CMS | /api/admin/pages, versions, themes, sections, publish |
| Marketing | /api/admin/coupons, campaigns, cashback-rules, referrals |
| Messaging | /api/admin/message-templates, deliveries, providers |
| Reports | /api/admin/reports/* و export jobs |
| Storefront | /api/storefront/catalog, cart, checkout, account, reviews |
| Webhooks | /webhooks/payments/{provider}, /webhooks/sms/{provider} |

قواعد API: versioning، pagination، filtering مشخص، error envelope یکنواخت، idempotency برای writes حساس، ETag/version برای ویرایش هم‌زمان، OpenAPI و tenant resolution اجباری.

## سرویس‌ها و Jobهای پس‌زمینه

| سرویس/Job | وظیفه |
| --- | --- |
| ProvisionStore | ساخت Atomic فروشگاه و Seed داده‌ها |
| VerifyDomain | بررسی DNS challenge و route readiness |
| IssueCertificate | صدور/تمدید TLS |
| SubscriptionRenewal | صدور Invoice و پیگیری تمدید |
| EnforceEntitlements | اعمال Limit و وضعیت اشتراک |
| ProductImport | پردازش فایل، validation و ثبت خطا |
| MediaProcessing | resize، optimize، virus scan و metadata |
| SendMessage | SMS/Email queue و retry |
| PaymentReconciliation | تطبیق پرداخت‌های نامشخص |
| ExpireWalletCredits | ثبت تراکنش انقضا |
| GrantCashback | اعطای امن پس از تحقق شرط |
| AbandonedCartDetection | شناسایی Cart واجد شرایط با consent |
| ReportExport | ساخت CSV/XLSX/PDF async |
| DomainHealthCheck | بررسی DNS/HTTPS دوره‌ای |
| DataRetention | پاک‌سازی طبق policy و legal hold |

## ذخیره‌سازی فایل و رسانه

- Object storage سازگار با S3؛ مسیرها با `store_id` namespace شوند.
- Upload مستقیم با signed URL و تأیید نهایی Backend.
- Whitelist MIME واقعی، سقف اندازه، image decode validation و malware scan.
- Derivativeها برای thumbnail/webp/avif توسط Worker.
- فایل خصوصی مثل Export و Ticket attachment با signed URL کوتاه‌عمر.
- عدم اعتماد به extension و عدم سرو HTML/SVG خام کاربر از origin اصلی بدون کنترل.

## امنیت ضروری

- CSRF، XSS، SQL injection، SSRF و Open Redirect controls.
- Host header validation و allowlist پویا برای دامنه‌های verified.
- Password hashing استاندارد، rate limit، credential stuffing protection و MFA.
- Encryption at rest برای credential درگاه/پیامک و key rotation.
- عدم log کردن token، رمز، PAN یا payload حساس.
- CSP، HSTS، secure cookies، frame-ancestors و referrer policy.
- Permission check در service layer، نه فقط template/view.
- Idempotency برای Payment، Refund، Cashback و Provisioning.
- Audit برای login، member، domain، gateway، refund، wallet adjustment و publish.
- Backup رمزگذاری‌شده، restore drill و disaster recovery plan.
- Data export/delete برای الزامات حریم خصوصی و retention مشخص.
- وابستگی‌ها با lockfile، vulnerability scan و secret scan در CI.

## نیازمندی‌های غیرعملکردی

| حوزه | هدف پیشنهادی MVP/Production |
| --- | --- |
| Availability | حداقل 99.9% برای storefront و admin پس از تثبیت |
| Performance | TTFB صفحات cacheable کمتر از 500ms در شرایط عادی؛ APIهای لیست p95 کمتر از 800ms |
| Scalability | Web stateless؛ PostgreSQL، Redis، Worker و object storage مستقل |
| Consistency | تراکنش برای Order/Payment/Wallet؛ eventual consistency برای analytics |
| RPO/RTO | RPO حداکثر 15 دقیقه و RTO حداکثر 2 ساعت به‌عنوان هدف اولیه |
| Observability | structured logs، metrics، tracing، error tracking و alerting |
| Localization | RTL، Persian calendar در UI، زمان UTC در DB و timezone در نمایش |
| Accessibility | keyboard، contrast، labels و semantic markup |
| SEO | SSR/storefront، sitemap، canonical، structured data و robots controls |
| Browser | نسخه‌های پایدار Chrome/Firefox/Edge و Safari متناسب بازار |

## معماری Deployment پیشنهادی

```text
Internet
  → CDN/WAF
  → Load Balancer / Nginx
      → Django Web (stateless, multiple instances)
      → Static assets / Object Storage CDN
  → PostgreSQL primary + backup/PITR
  → Redis (cache/session/queue broker as selected)
  → Celery/RQ workers + scheduler
  → Object Storage
  → Monitoring / Logs / Error tracking
```

- Wildcard DNS و certificate برای `*.rastisi.ir` پنل‌ها.
- Certificate جدا/خودکار برای دامنه‌های عمومی فروشندگان.
- Environmentهای local، staging و production جدا با داده و secret مستقل.
- Migration قبل از rollout با backward-compatible strategy.
- Health/readiness endpoint و graceful shutdown.
- CDN cache فقط برای پاسخ‌های عمومی و با cache key صحیح Host/Store.

## ساختار پیشنهادی Backend

```text
apps/
  accounts/       # platform identity, auth, MFA
  merchants/      # merchant profile and teams
  stores/         # tenant, membership, resolver
  subscriptions/  # plans, billing, entitlements
  provisioning/   # store setup orchestration
  domains/        # verification, certificates
  industries/     # templates and schemas
  catalog/        # product/category/brand/variant/inventory
  commerce/       # cart/checkout/order/return
  payments/       # merchant gateways and payment lifecycle
  shipping/       # zones/rates/shipments
  customers/      # CRM, consent, addresses
  loyalty/        # wallet/cashback/referral
  cms/            # pages/menu/sections/SEO
  themes/         # design tokens/version/publish
  messaging/      # sms/email/templates/delivery
  analytics/      # events/reports/exports
  support/        # tickets/knowledge
  audit/          # audit/security events
  platform_ops/   # super admin operations
```

## تست‌های اجباری

- Unit test برای state machineها، pricing، coupon، entitlement و wallet ledger.
- Integration test برای database constraints، payment callback، domain verification و queue.
- Cross-tenant test برای تمام Entityهای Store-owned.
- Contract test برای درگاه پرداخت، SMS و carrier adapters.
- E2E برای ثبت‌نام تا تحویل Store، ورود پنل، ساخت محصول، خرید و سفارش.
- Property-based test برای Variant combination، coupon rules و money arithmetic در صورت امکان.
- Security test برای Host spoofing، IDOR، CSRF، XSS، upload و rate limit.
- Migration test روی snapshot داده نزدیک Production.
- Load test برای storefront، checkout و callbackهای پرتکرار.
- Restore test دوره‌ای Backup.

## شکاف‌ها: از Prototype تا محصول کامل

| حوزه | وضعیت در دو فایل | کار لازم |
| --- | --- | --- |
| Backend و DB | فاقد | طراحی و ساخت کل مدل‌ها، migrationها، serviceها و APIها |
| Multi-tenancy | فاقد | Store context، constraints، resolver و isolation tests |
| ورود مرکزی و Membership | فاقد | Auth واقعی، session exchange، RBAC |
| اشتراک و Billing | فقط UI | Plan version، invoice، payment، entitlement و renewal |
| Provisioning | فقط Wizard | orchestrator اتمیک، retry، status و seed |
| دامنه عمومی | فقط فرم | DNS verification، routing، TLS و health |
| کاتالوگ صنفی | Prototype | Template versioning، schema، copy/override و approval |
| Variant | Prototype JS | مدل، validation، SKU، media و inventory |
| محصول و Media | فقط فرم | storage، processing، draft/publish و SEO |
| Order/Payment | فقط صفحات | state machine، gateway integration، idempotency و refund |
| Shipping | فقط تنظیمات | zones، rates، shipment و carrier |
| Wallet/Cashback | فقط UI | immutable ledger، rules، reversal و expiry |
| Referral | فقط UI | attribution، anti-fraud و reward lifecycle |
| SMS | localStorage | provider adapters، queue، delivery callbacks و consent |
| CMS/Builder | Prototype | versioning، schema validation، preview/publish/rollback |
| Reports | داده نمایشی | event pipeline، aggregates و async export |
| Support/Audit | فقط UI | ticket workflow و append-only audit |
| Security/Operations | فاقد | secret، monitoring، backup، CI/CD و incident response |

## اولویت‌بندی ساخت

| فاز | خروجی |
| --- | --- |
| P0 — Specification freeze | تثبیت دامنه محصول، نقش‌ها، مدل Tenant، URL policy و MVP |
| P1 — Foundation | Django/PostgreSQL، accounts، Store، Membership، resolver، RBAC، audit پایه |
| P2 — SaaS Core | Plan، Subscription، Billing، Provisioning، admin_slug و central login |
| P3 — Catalog & Industry | Template صنفی، category، brand، product، attribute، variant، media، inventory |
| P4 — Storefront Commerce | Theme/CMS پایه، catalog storefront، cart، checkout، order، payment، shipping |
| P5 — Domain & Go-live | custom domain، verification، TLS، canonical و operational checks |
| P6 — Merchant Operations | reports پایه، SMS، coupons، reviews، imports و invoices |
| P7 — Loyalty & Growth | wallet، cashback، referral، abandoned cart و campaigns |
| P8 — Advanced Builder/Analytics | page builder پیشرفته، cohorts، attribution و integrations |

## تعریف MVP قابل فروش

- ثبت‌نام و ورود فروشنده با تأیید موبایل/ایمیل.
- حداقل دو پلن و پرداخت واقعی اشتراک.
- Provisioning خودکار Store و `admin_slug.rastisi.ir/admin-portal/`.
- یک صنف عمومی + چند Template منتخب قابل ویرایش.
- محصول، دسته، برند، Variant با تصویر رنگ/Variant و موجودی.
- ویترین Responsive، دامنه موقت و اتصال یک دامنه شخصی.
- Cart، Checkout، یک درگاه واقعی، COD اختیاری و روش ارسال پایه.
- Order management، مشتری، Coupon، صفحات پایه و تنظیم ظاهر.
- RBAC حداقلی Owner/Admin/Operator.
- Audit حساس، Backup، monitoring و cross-tenant tests.
- Subscription enforcement و Grace/Suspension امن.

قابلیت‌هایی مانند Cashback، Referral، Wallet، Instagram integration، Page Builder آزاد و گزارش‌های پیشرفته بهتر است پس از پایدارشدن MVP اضافه شوند؛ هرچند مدل‌سازی آن‌ها باید از ابتدا با معماری سازگار باشد.

## معیار پذیرش کلیدی

- دو Store با کاربران و داده‌های متفاوت ایجاد شوند و هیچ endpoint، export، media URL یا job نتواند داده دیگری را ببیند.
- کاربر پس از ورود مرکزی فقط Storeهای دارای Membership فعال را انتخاب کند.
- `digilool.rastisi.ir/admin-portal/` همیشه Store درست را resolve کند و Host جعلی رد شود.
- `digilool.ir` پس از verification به Store درست route شود و HTTPS معتبر داشته باشد.
- تغییر دامنه عمومی، admin_slug و آدرس پنل را تغییر ندهد.
- انتخاب رنگ محصول، تصویر و Variant درست را در Storefront عوض کند.
- Callback تکراری پرداخت فقط یک Order payment و یک اثر مالی ایجاد کند.
- Cashback/Wallet هیچ‌گاه با retry دو بار ثبت نشود.
- تعلیق اشتراک Storefront/پنل را طبق policy محدود کند ولی داده را حذف نکند.
- تمام تغییرات حساس Actor، زمان، IP و before/after مناسب در Audit داشته باشند.

## تصمیم‌های معماری تثبیت‌شده (ADR خلاصه)

| شناسه | تصمیم |
| --- | --- |
| ADR-001 | Rastisi یک SaaS Multi-Tenant است، نه deployment جداگانه پیش‌فرض برای هر مشتری. |
| ADR-002 | دامنه عمومی فروشگاه از Host پنل مدیریت مستقل است. |
| ADR-003 | پنل فروشنده روی `<admin_slug>.rastisi.ir/admin-portal/` قرار می‌گیرد. |
| ADR-004 | `admin_slug` شناسه پایدار Store است و از دامنه عمومی به‌صورت خودکار مشتق و همگام نمی‌شود. |
| ADR-005 | Authorization بر اساس StoreMembership و Permission است، نه `is_staff` عمومی. |
| ADR-006 | Industry Template نسخه‌دار است و هنگام Provisioning به ساختار Store تبدیل می‌شود. |
| ADR-007 | Variant و Attribute generic و schema-driven طراحی می‌شوند. |
| ADR-008 | Wallet یک ledger append-only است. |
| ADR-009 | پرداخت اشتراک پلتفرم و پرداخت سفارش فروشگاه دو bounded context مستقل‌اند. |
| ADR-010 | Prototypeهای HTML مرجع UX و Scope هستند، نه منبع حقیقت داده یا Backend. |

## مواردی که پیش از کدنویسی باید نهایی شوند

- کشور/بازار هدف قطعی، واحد پول، مالیات و الزامات حقوقی.
- درگاه‌های پرداخت و پیامک اولویت‌دار.
- سیاست دامنه موقت Storefront و اینکه از `rastisi.ir` جدا باشد یا نه.
- فهرست MVP صنف‌ها و Template دقیق هرکدام.
- Limits هر Plan و سیاست Trial/Grace/Suspension.
- سیاست مالکیت داده، Export و حذف حساب.
- مدل تسویه در صورتی که Rastisi واسط مالی شود یا فقط Credential فروشنده را نگه دارد.
- سطح Page Builder در MVP.
- الزام MFA و احراز حقوقی فروشندگان.
- زیرساخت Hosting و Storage انتخابی.

## ضمیمه A — فهرست کامل صفحات

| بسته | فایل | عنوان |
| --- | --- | --- |
| Rastisi | about.html | درباره ما · راستیسی |
| Rastisi | categories.html | صنوف پشتیبانی‌شده · راستیسی |
| Rastisi | checkout.html | تکمیل خرید · راستیسی |
| Rastisi | contact.html | تماس با ما · راستیسی |
| Rastisi | dashboard.html | داشبورد · راستیسی |
| Rastisi | faq.html | سوالات متداول · راستیسی |
| Rastisi | features.html | امکانات · راستیسی |
| Rastisi | how-it-works.html | روش کار · راستیسی |
| Rastisi | index.html | ساخت فروشگاه اینترنتی · راستیسی |
| Rastisi | login.html | ورود · راستیسی |
| Rastisi | plans.html | پلن‌ها و قیمت‌ها · راستیسی |
| Rastisi | register.html | ثبت‌نام · راستیسی |
| Rastisi | store-setup.html | ساخت فروشگاه · راستیسی |
| Rastisi | store-success.html | فروشگاه فعال شد · راستیسی |
| X25 | appearance-settings.html | طراحی بصری · نوین‌شاپ |
| X25 | brands.html | برندها · نوین‌شاپ |
| X25 | business-info.html | اطلاعات حقوقی · نوین‌شاپ |
| X25 | cashback-settings.html | کش‌بک و کیف پول · نوین‌شاپ |
| X25 | categories.html | دسته‌بندی‌ها · نوین‌شاپ |
| X25 | coupons.html | بنرها و تخفیف · نوین‌شاپ |
| X25 | customer-report.html | رفتار مشتریان · نوین‌شاپ |
| X25 | customers.html | پایگاه مشتریان · نوین‌شاپ |
| X25 | draft-orders.html | سبدهای رها شده · نوین‌شاپ |
| X25 | general-configs.html | تنظیمات پایه · نوین‌شاپ |
| X25 | guide.html | مرکز آموزش · نوین‌شاپ |
| X25 | home-page-content.html | صفحه نخست · نوین‌شاپ |
| X25 | import-products.html | ورود گروهی محصولات · نوین‌شاپ |
| X25 | index.html | داشبورد · نوین‌شاپ |
| X25 | industry-setup.html | ساختار صنف و کاتالوگ · نوین‌شاپ |
| X25 | instagram.html | شبکه‌های اجتماعی · نوین‌شاپ |
| X25 | invite-friends.html | همکاری در فروش · نوین‌شاپ |
| X25 | invoices.html | فاکتورها · نوین‌شاپ |
| X25 | login.html | ورود · نوین‌شاپ |
| X25 | logs.html | رویدادهای سیستم · نوین‌شاپ |
| X25 | marketing.html | بازاریابی و رشد · نوین‌شاپ |
| X25 | order-new.html | ثبت و مدیریت سفارش · نوین‌شاپ |
| X25 | order-report.html | تحلیل فروش · نوین‌شاپ |
| X25 | order-settings.html | قوانین سفارش · نوین‌شاپ |
| X25 | orders.html | لیست سفارش‌ها · نوین‌شاپ |
| X25 | page-comments.html | بازخورد صفحات · نوین‌شاپ |
| X25 | pages.html | صفحات سایت · نوین‌شاپ |
| X25 | payment-settings.html | درگاه‌های پرداخت · نوین‌شاپ |
| X25 | payments.html | تراکنش‌های مالی · نوین‌شاپ |
| X25 | product-comments.html | نظرات کاربران · نوین‌شاپ |
| X25 | product-create.html | افزودن محصول جدید · نوین‌شاپ |
| X25 | product-edit.html | ویرایش محصول · نوین‌شاپ |
| X25 | product-report.html | عملکرد محصولات · نوین‌شاپ |
| X25 | products.html | همه محصولات · نوین‌شاپ |
| X25 | shipping-settings.html | لجستیک و ارسال · نوین‌شاپ |
| X25 | sms-custom.html | قالب‌های پیام · نوین‌شاپ |
| X25 | sms-gateway-settings.html | تنظیمات درگاه پیامک · نوین‌شاپ |
| X25 | sms-list.html | صندوق پیام‌ها · نوین‌شاپ |
| X25 | sms-report.html | آمار پیام‌ها · نوین‌شاپ |
| X25 | store-editor.html | استودیو ساخت فروشگاه |
| X25 | storefront-brands.html | برندها | فروشگاه |
| X25 | storefront.html | فروشگاه زیبایی |
| X25 | subscription.html | پلن اشتراک · نوین‌شاپ |
| X25 | ticketing.html | پشتیبانی · نوین‌شاپ |
| X25 | wallet-transactions.html | گردش کیف پول · نوین‌شاپ |

## ضمیمه B — فایل‌های JavaScript و نقش آن‌ها

| بسته | فایل | اندازه تقریبی | کلیدهای localStorage مشهود |
| --- | --- | --- | --- |
| Rastisi | app.js | 259 خط | — |
| X25 | app.js | 182 خط | — |
| X25 | product-rich-content.js | 47 خط | — |
| X25 | store-config.js | 45 خط | — |
| X25 | storefront.js | 42 خط | novin-cart |
| X25 | x25-catalog.js | 14 خط | — |
| X25 | x25-product-variants.js | 2 خط | — |

## ضمیمه C — نتیجه نهایی

دو فایل بررسی‌شده از نظر طراحی محصول مکمل یکدیگرند: یکی قیف جذب و ایجاد فروشگاه را تعریف می‌کند و دیگری عملیات روزانه فروشنده و بخشی از تجربه خریدار را. برای کامل‌شدن، باید یک Backend SaaS چندمستاجری با حدود دوازده bounded context، ده‌ها مدل نسخه‌دار و Store-scoped، ورود مرکزی، اشتراک، Provisioning، دامنه، کاتالوگ صنفی، Commerce، وفاداری، Messaging، Audit و زیرساخت Production ساخته شود. مهم‌ترین ترتیب کار، ابتدا هویت و Tenant isolation، سپس SaaS core، سپس Catalog/Commerce و در پایان قابلیت‌های رشد است. شروع از تبدیل مستقیم همه صفحات HTML به View بدون این Foundation، ریسک بازنویسی و نشت داده را بالا می‌برد.

**پایان جلد اول — این سند مبنای طراحی و برنامه‌ریزی است و باید با هر تصمیم قطعی محصول نسخه‌بندی شود.**