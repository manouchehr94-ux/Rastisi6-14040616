# مشخصات اجرایی پنج قالب RastiSi — نسخه سبک

## 1. هدف

این بسته ده صفحه کم‌حجم را به‌عنوان قرارداد دیداری و ساختاری ارائه می‌کند:

| شماره | خانواده | مرجع تحلیلی | صفحه اصلی | صفحه محصول |
|---|---|---|---|---|
| 1 | `Vibrant Catalog` | Beraito | Promo dashboard و کاتالوگ پرتراکم | خرید سریع و قیمت‌محور |
| 2 | `Heritage Premium` | Cactus Leather | Full-bleed campaign و Photography-first | Gallery بزرگ، رنگ و سایز |
| 3 | `Artisan Editorial` | Deeyar | Storytelling، About، کارگاه و مجله | محصول همراه داستان |
| 4 | `Modern Fashion` | iBolak | Story rail، دسته Editorial و کارت 9:12 | Gallery، رنگ، سایز و Size chart |
| 5 | `Nordic Living` | IkalaJam | Search-first و بنرهای خنثی | محصول خانگی با تصویر دوم و ویژگی متوسط |

هدف ساخت پنج سایت ایستا نیست. هدف افزودن پنج خانواده Presentation به Builder موجود است، به‌گونه‌ای که Preview و Public Storefront از Renderer مشترک استفاده کنند.

## 2. قانون اصلی درباره ایموجی

هر `.emoji-media` یک Media slot است. Claude باید این موارد را از روی آن استخراج کند:

1. نسبت تصویر و حداقل ارتفاع؛
2. Crop و Fit پیش‌فرض؛
3. جایگاه متن، Badge و CTA نسبت به تصویر؛
4. رفتار Desktop/Mobile؛
5. امکان تصویر مخصوص Mobile؛
6. تصویر دوم یا Gallery چندتصویری، اگر در مشخصات آمده است.

خود ایموجی نباید وارد Template نهایی شود، مگر به‌عنوان محتوای دمو در Gallery داخلی توسعه.

## 3. جداسازی سطوح

### Template-level

- ترکیب Header و Navigation؛
- راهبرد عرض Container؛
- ریتم عمودی Sectionها؛
- ترتیب پیشنهادی Homepage؛
- Product Card renderer؛
- نسبت تصویر پیش‌فرض؛
- Hero treatment؛
- Category presentation؛
- Footer composition؛
- Motion family؛
- قرارداد رفتار Mobile.

### Section-level

- داده، عنوان و visibility؛
- انتخاب Collection و ترتیب محصولات؛
- Variant نمایش Section؛
- تعداد ستون/کارت؛
- Background و spacing مجاز؛
- لینک «مشاهده همه»؛
- رسانه Desktop و Mobile.

### Component-level

- Button، Badge، Search، Product Card، Price، Wishlist، Action rail، Thumbnail؛
- Radius، Border، Shadow و stateها؛
- line clamp و جایگاه قیمت؛
- Touch fallback و focus state.

### Palette/Typography/Motion/Density

این چهار سطح از Template جدا هستند. Merchant پس از انتخاب Template باید بتواند Palette و Typography را عوض کند، بدون اینکه DOM کارت یا ترکیب Header به کارت عمومی تبدیل شود.

### Content

نام برند، لوگو، عکس، متن کمپین، درصد تخفیف، تلفن، آدرس، نام دسته و محصولات مرجع فقط Content هستند و نباید در Template عمومی hard-code شوند.

## 4. پنج Product Card renderer اجباری

### `square_centered_commerce`

- تصویر `1:1`؛
- عنوان و قیمت وسط‌چین؛
- قیمت قبلی/جدید؛
- Discount badge؛
- CTA ثابت در Touch و اختیاری در Hover؛
- مناسب SKU زیاد.

### `premium_portrait` و حالت `premium_campaign`

- تصویر نزدیک `3:4`؛
- اطلاعات در بلوک پایین تصویر؛
- ابزار کم؛
- Overlay کمپین یا پرداخت فقط در حالت campaign؛
- Actionهای Desktop دارای Touch fallback.

### `artisan_story_card`

- نسبت تصویر قابل تنظیم؛
- عنوان آرام و وسط‌چین؛
- Metadata اختیاری سازنده/منطقه؛
- Border/Shadow ظریف؛
- Motion کم.

### `fashion_portrait_gallery`

- تصویر `9:12`؛
- Wishlist؛
- عنوان راست و قیمت چپ؛
- تصویر دوم/سوم روی Desktop؛
- Swipe/Tap در Mobile؛
- کارت Mobile نزدیک `70vw` در Rail افقی.

### `catalog_second_image`

- تصویر نزدیک `7:8`؛
- عنوان دوخطی و توضیح کوتاه اختیاری؛
- Crossfade تصویر دوم حدود `0.6s`؛
- Action rail در Desktop؛
- CTA ثابت در Mobile.

این rendererها باید Branch واقعی markup/partial/component داشته باشند. یک DOM ثابت با پنج کلاس رنگی پذیرفته نیست.

## 5. ترتیب Sectionها

### قالب 1 — Vibrant Catalog

1. Utility bar؛
2. Logo/Search/Account/Cart؛
3. Navigation/Mega Menu؛
4. Promo dashboard؛
5. Quick category grid؛
6. Service strip؛
7. Dense product collection؛
8. Promo banner grid؛
9. چند Collection دیگر؛
10. Brand/Blog اختیاری؛
11. Dark service footer.

### قالب 2 — Heritage Premium

1. Promotion strip؛
2. Premium header و category navigation؛
3. Full-bleed campaign hero؛
4. Portrait category row؛
5. Campaign product grid؛
6. New arrivals؛
7. Promotional image grid؛
8. Service strip؛
9. Best sellers؛
10. Blog اختیاری؛
11. Light identity footer.

### قالب 3 — Artisan Editorial

1. Quiet two-level header؛
2. Editorial hero؛
3. Four artisan category banners؛
4. New products؛
5. Industry/craft banners؛
6. Tabbed collections؛
7. About split؛
8. Workshop/blog cards؛
9. Social gallery اختیاری؛
10. Trust/story footer.

### قالب 4 — Modern Fashion

1. Social/search header؛
2. Story rail اختیاری؛
3. Fashion carousel؛
4. Editorial category tiles؛
5. Product rails؛
6. Blog اختیاری؛
7. Minimal footer.

### قالب 5 — Nordic Living

1. Announcement؛
2. Utility؛
3. Search-first header؛
4. Grouped mega navigation؛
5. Neutral living hero؛
6. Service strip؛
7. Second-image product collections؛
8. Two-up/four-up category banners؛
9. Multi-tier information footer.

## 6. قرارداد صفحه محصول

هر پنج صفحه محصول از Product و Variant واقعی استفاده می‌کنند، اما Presentation آن‌ها مستقل است:

| خانواده | Gallery | پنل خرید | محتوای پایین |
|---|---|---|---|
| Vibrant Catalog | استاندارد و فشرده | قیمت و CTA غالب | مشخصات، ارسال، Related |
| Heritage Premium | بزرگ و Thumbnail عمودی | رنگ، سایز، موجودی، کمپین اختیاری | تب، ویدیو اختیاری، Related |
| Artisan Editorial | ساده و گرم | داستان کوتاه نزدیک خرید | داستان بلند، سازنده، Related |
| Modern Fashion | Gallery عمودی و چندتصویری | رنگ، سایز، Size chart | FAQ، تب، Editorial، Related |
| Nordic Living | Gallery دو ستونه/استاندارد | برند، ویژگی کوتاه، Favorite | ویژگی متوسط، توضیح بلند، Related |

انتخاب رنگ باید تصویر/Gallery همان Variant را فعال کند. ویدیوی Aparat/YouTube باید Media capability اختیاری باشد. CTA موبایل همواره قابل لمس است.

## 7. رفتار Responsive

### Desktop

- Container و چگالی هر Template حفظ شود؛
- Hover فقط Enhancement است؛
- Header و Hero پنج خانواده قابل تشخیص باشند؛
- Product grid تعداد ستون مناسب خانواده داشته باشد.

### Tablet

- Navigation عمیق به نسخه کوتاه‌تر تبدیل شود؛
- Grid معمولاً سه ستونه؛
- Container margin حداقل 14px؛
- Product panel صفحه محصول زیر Gallery منتقل شود اگر عرض کافی نیست.

### Mobile

- Header مستقل و Touch-friendly؛
- CTA حیاتی ثابت؛
- Gallery قابل Swipe/Tap؛
- Rail افقی برای Fashion و محتوای روایی؛
- Grid/rail متناسب با DNA، نه یک fallback یکسان؛
- Sticky add-to-cart فقط صفحه محصول؛
- متن فارسی بلند، قیمت بزرگ و عنوان دوخطی آزمایش شود.

## 8. Motion و دسترس‌پذیری

- `prefers-reduced-motion` رعایت شود؛
- Focus visible برای لینک‌ها، دکمه‌ها، Selectorها و کارت‌های قابل کلیک؛
- Hover action معادل Touch و Keyboard داشته باشد؛
- Beraito: shadow/zoom/shine کوتاه؛
- Cactus: side action/fade آرام؛
- Deeyar: border/shadow بسیار ملایم؛
- iBolak: zoom و thumbnail reveal؛
- IkalaJam: second-image crossfade و action rail.

## 9. Builder و Publish

- Sectionها قابل افزودن، حذف، مخفی‌کردن و جابه‌جایی باشند؛
- Merchant بتواند Collection، عنوان، ترتیب محصول، لینک و variant را تعیین کند؛
- Draft تغییر کند ولی Public تا Publish ثابت بماند؛
- Preview و Public از یک Rendering pipeline استفاده کنند؛
- Template switching داده محصول/دسته را حذف نکند؛
- Rollback نسخه Published را بازگرداند؛
- Tenant isolation در تمام مسیرها حفظ شود.

## 10. معیار پذیرش

1. هر پنج قالب با Palette یکسان نیز قابل تشخیص باشند.
2. Header، Hero، Product Card و Footer پنج خانواده واقعاً متفاوت باشند.
3. ده مسیر Home/Product ساخته و قابل تست باشند.
4. Preview/Public parity برقرار باشد.
5. Templateها از داده Merchant استفاده کنند و به محتوای مرجع وابسته نباشند.
6. Desktop، Tablet و Mobile جداگانه بررسی شوند.
7. کنترل بی‌اثر در Builder وجود نداشته باشد.
8. CTA حیاتی بدون Hover قابل دسترسی باشد.
9. Tenant isolation، Draft/Publish، Template switch و Product variant تست شوند.
10. هیچ‌کدام به پنج سایت HTML جدا و خارج از Builder تبدیل نشوند.
