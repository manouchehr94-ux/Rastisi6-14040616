# شرط‌های اجباری قبولی

## Gate 1 — معماری

- دقیقاً ۱۱ Family در Registry و UI انتخاب قالب دیده شود.
- پنج Family قبلی بدون Regression باقی بمانند.
- شش Family جدید Renderer مستقل Home و Product داشته باشند.
- Preview/Public از مسیر Render مشترک استفاده کنند.
- هیچ Query بدون Tenant scope نباشد.
- هیچ متن، لوگو، تصویر، قیمت یا Product سایت مرجع در Fixture تولیدی وجود نداشته باشد.

## Gate 2 — Builder

برای هر شش Family، Sectionهای پیش‌فرض قابل Reorder، Hide/Show، Duplicate، Edit و Delete باشند. تغییرات باید Draft شوند، Preview بدون Publish دیده شود و Publish/Rollback کار کند.

## Gate 3 — عملکرد UI

- Menu، Search، Story، Slider، Cart، Wishlist، Compare، Gallery، Zoom، Share، Variant، Quantity، Add-to-cart، Tabs و FAQ در صورت حضور واقعاً کار کنند.
- کنترل تزئینی یا `href="#"` بدون Handler پذیرفته نیست.
- انتخاب Variant باید تصویر، قیمت، SKU و موجودی را به‌روزرسانی کند.
- ناموجود به Cart اضافه نشود.

## Gate 4 — Responsive و iPhone

- آزمون در شش Viewport قرارداد Responsive انجام شود.
- `document.documentElement.scrollWidth === document.documentElement.clientWidth`.
- همه Inputهای قابل تایپ در Mobile حداقل 16px باشند.
- Touch targetها حداقل 44px.
- Drawer، Modal و Sticky CTA با Safe Area تداخل نداشته باشند.

## Gate 5 — Visual

- Screenshotهای Reference در این بسته برای Desktop مقایسه شوند.
- Header، Hero، Section order، Card anatomy، Badge، Radius، رنگ غالب، تراکم و Footer باید مطابق Contract باشند.
- Pixel diff خام معیار انحصاری نیست چون محتوای فروشنده متفاوت است؛ هندسه و Style-regionها باید با Threshold زیر مقایسه شوند:
  - اختلاف موقعیت Regionهای اصلی: حداکثر 12px در Desktop و 8px در Mobile.
  - اختلاف Radius/Spacing token: حداکثر 2px.
  - اختلاف رنگ اصلی: `DeltaE <= 6`.
  - CLS در بارگذاری Public: کمتر از 0.1.

## Gate 6 — تست‌ها

- تست Registry و Count=11.
- تست Seed/Default sections برای هر Family.
- تست Home render و Product render برای هر Family.
- تست Tenant isolation.
- تست Draft/Preview/Publish/Rollback.
- تست Variant-image mapping.
- تست Cart/Wishlist/Compare.
- تست Mobile no-horizontal-overflow و iOS input font-size.
- Django check، migration plan و کل Suiteهای مرتبط سبز باشند.

## Gate 7 — گزارش نهایی Kiro

Kiro باید فایل `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` بسازد و برای هر Gate، Command، Exit code، تعداد Test و مسیر Screenshot را بنویسد. عبارت «انجام شد» بدون مدرک پذیرفته نیست. تا عبور همه Gateها Merge به `main` ممنوع است.

