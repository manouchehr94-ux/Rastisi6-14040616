# قرارداد Responsive قطعی

Viewportهای اجباری آزمون: `1440×1000`، `1366×768`، `1024×768`، `768×1024`، `390×844` و `360×800`.

## قواعد مشترک

- هیچ Scroll افقی در Body مجاز نیست.
- متن Inputها روی iOS حداقل `16px` باشد تا صفحه هنگام Focus زوم نشود.
- دکمه‌های لمسی حداقل `44×44px` باشند.
- Hover روی موبایل نباید تنها راه دسترسی به Action باشد.
- منوی Desktop در `<=1024px` به Drawer تبدیل شود، مگر Breakpoint اختصاصی Family زودتر باشد.
- Product rail در `390px` باید حدود 2.15 کارت را نشان دهد تا قابل‌اسکرول بودن مشخص باشد.
- تصاویر Variant پس از انتخاب رنگ/ترکیب ویژگی باید همان Media نگاشت‌شده را نشان دهند.
- Bottom sheet یا Drawer نباید پشت Safari toolbar پنهان شود؛ از Safe Area استفاده شود.

## اطلس

- Desktop: Hero به نسبت 3/1؛ Collectionها 6 کارت؛ دو Collection فشرده می‌توانند کنار هم باشند.
- Tablet: Hero به 2/1؛ کارت‌ها 4تایی؛ Collectionهای جفت زیر هم قرار گیرند.
- Mobile 390: Topbar ساده، Header دو ردیف، Search تمام‌عرض، منو Drawer؛ Hero اصلی تمام‌عرض و پیشنهاد لحظه‌ای زیر آن؛ دسته‌ها Rail افقی؛ کارت‌ها 2.15تایی؛ کنترل تعداد داخل کارت حفظ شود.
- Footer در موبایل Accordion چهارگروهی است.

## آوا

- Desktop: Story rail تک‌ردیف، Hero عریض، Mosaic چهارستونه، Rail پنج‌کارت.
- Tablet: Mosaic دوستونه، Rail سه‌کارت.
- Mobile 390: Campaign strip، Header فشرده، Story rail دایره‌ای؛ Hero نسبت تقریبی 4/5؛ Mosaic دوستونه؛ کارت محصول 2.15تایی با تصویر 3/4؛ Variant picker به Bottom sheet تبدیل شود.
- تصویر دوم Hover در موبایل با Swipe/indicator یا دکمه مشاهده جایگزین شود.

## ترنج

- Desktop: Header قهوه‌ای، Navigation دو ردیف، Hero سه کارت بزرگ، Grid دسته دو ردیف.
- Tablet: Hero دو کارت با بخشی از کارت بعدی.
- Mobile 390: Logo/Search/Cart در دو ردیف؛ Story rail افقی؛ Hero یک کارت با Peek کارت بعدی؛ دسته‌ها سه‌ستونه؛ Product rail دوکارت؛ Product page ابتدا Gallery سپس Card خرید.
- Footer موج‌دار مشکی به Accordion تبدیل شود و فضای خالی ایجاد نکند.

## سرو

- Desktop: Header شناور Rounded، کارت‌ها 6تایی، صفحه محصول سه‌ستونه.
- Tablet: کارت‌ها 4تایی، صفحه محصول Gallery سپس Facts/Purchase دو ستون.
- Mobile 390: Campaign strip کوتاه؛ Header شامل Logo/Menu/Cart؛ Hero نسبت 16/9؛ دسته‌ها Rail؛ کارت‌ها 2.15تایی؛ دکمه Cart سبز همیشه قابل مشاهده؛ Purchase box پس از Gallery و Facts؛ CTA خرید Sticky پایین مجاز است.

## سپیدار

- Desktop: Header Capsule، Search Capsule دوم، Hero Editorial، پس‌زمینه Cream.
- Tablet: Navigation به Drawer؛ Hero نسبت 4/3.
- Mobile 390: Header یک Capsule فشرده، Search ردیف بعد، Hero تمام‌عرض، Trustها دوستونه، Product rail دوکارت، Blog تک‌ستون. Loader بیشتر از 2500ms مجاز نیست.
- صفحه محصول: Gallery سپس Summary؛ Guarantee tileها دو ستون؛ Review تمام‌عرض.

## زرین

- Desktop: Header مینیمال تک‌ردیف، Category mosaic چهارستونه، دو Campaign بزرگ.
- Tablet: Mosaic سه‌ستونه.
- Mobile 390: Header با Menu/Logo/Search/Cart؛ Hero عمودی؛ Mosaic دوستونه؛ دو Campaign زیر هم؛ کارت‌ها دو ستون یا Rail 2.15تایی طبق نوع Section؛ FAQ تمام‌عرض.
- صفحه محصول: عنوان، Gallery swipe، قیمت، Variant، Quantity، CTA؛ Share در ردیف جدا؛ Size guide در Modal/Panel قابل بستن.

