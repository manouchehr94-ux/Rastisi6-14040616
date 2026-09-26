# بسته اجرایی ۱۱ Family برای RastiSi4

این بسته مرجع قطعی اجرای شش Family جدید در کنار پنج Family موجود است. هدف آن این است که Kiro برای تعداد Familyها، نام‌ها، ترتیب بخش‌ها، آیکون‌ها، Badgeها، صفحه محصول، موبایل، داده‌های فروشنده و معیار قبولی مجبور به حدس‌زدن یا پرسیدن سؤال نباشد.

## تصمیم قفل‌شده

- پنج Family موجود حذف، ادغام یا تغییر نام داده نمی‌شوند.
- شش Family جدید افزوده می‌شوند؛ مجموع نهایی دقیقاً ۱۱ است.
- شش Family جدید: `atlas_catalog`، `ava_fashion`، `toranj_gifting`، `sarv_stock`، `sepidar_handmade` و `zarrin_jewelry`.
- نام‌های عمومی آن‌ها: اطلس، آوا، ترنج، سرو، سپیدار و زرین.
- نام، لوگو، متن، تصویر، محصول و کد سایت‌های مرجع وارد خروجی عمومی RastiSi نمی‌شود.
- ظاهر و رفتار با کد مستقل پروژه بازسازی می‌شود و تمام محتوا از داده‌های همان فروشنده می‌آید.
- مدیر فروشگاه باید همچنان بتواند Sectionها را جابه‌جا، مخفی، تکرار و ویرایش کند.
- Preview و Public باید از Renderer مشترک استفاده کنند.
- Draft، Preview، Publish و Rollback، جداسازی Tenant و صفحات محصول واقعی باید حفظ شوند.

## ترتیب اعتبار منابع

اگر دو مدرک ظاهراً متفاوت بودند، Kiro بدون سؤال این ترتیب را اعمال کند:

1. `decision-lock.yaml`
2. قرارداد اختصاصی Family در `contracts/`
3. Screenshot همان صفحه در `screenshots/`
4. `machine/reference-dna.json`
5. رفتار فعلی و معماری سالم ریپازیتوری
6. Fallbackهای صریح همین بسته

هیچ ناسازگاری مجوز حذف قابلیت موجود، Hard-code کردن محتوای سایت مرجع یا ساخت Layout ثابت و غیرقابل‌ویرایش نیست.

## محتویات بسته

- `KIRO_MASTER_PROMPT_FA.md`: دستور کامل و بدون توقف برای Kiro.
- `decision-lock.yaml`: تصمیم‌های غیرقابل تفسیر پروژه.
- `contracts/section-blueprints.yaml`: ترتیب پیش‌فرض Sectionها و ساختار Home/Product.
- `contracts/icon-manifest.yaml`: آیکون، Stroke، اندازه، کادر و حالت‌های Hover/Active.
- `contracts/badge-matrix.yaml`: تخفیف، موجودی، جدید، ویژه و ناموجود.
- `contracts/interactions.yaml`: Slider، Story، Cart، Wishlist، Compare، Zoom و Variant.
- `contracts/dynamic-data-mapping.yaml`: اتصال هر بخش به داده‌های فروشنده و Fallbackها.
- `RESPONSIVE_CONTRACT_FA.md`: رفتار دقیق Desktop/Tablet/Mobile/390px.
- `ACCEPTANCE_GATES_FA.md`: تست‌ها و شرط پایان کار.
- `SOURCE_AUDIT_FA.md`: وضعیت مدارک خام و خطاهای Snapshot.
- `machine/reference-dna.json`: استخراج ماشینی از HTML/CSSهای ارسالی.
- `machine/source-manifest.json`: مسیر، اندازه و SHA-256 مدارک ساختاری.
- `screenshots/`: تصاویر Home و Product ثبت‌شده در 10 اوت 2026.

## اصل مهم

Screenshotها «محتوای فروشگاه نمونه» را نشان می‌دهند، اما در پیاده‌سازی فقط هندسه، سبک و رفتار مرجع هستند. مثلاً کارت محصول اطلس باید همان تراکم، Radius، Badge و کنترل تعداد را داشته باشد، ولی نام، تصویر، قیمت و موجودی آن باید از Product همان Tenant خوانده شود.

## وضعیت خاص سپیدار

نسخه زنده Gallery Chiic هنگام بررسی روی Loader می‌ماند. Snapshot ارسالی کاربر، DOM/CSS کامل Home و Product را دارد و منبع اصلی قرارداد سپیدار است. Kiro نباید Loader دائمی، وابستگی به JavaScript شخص ثالث یا خطای همان سایت را بازسازی کند.

