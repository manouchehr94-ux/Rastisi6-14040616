# RastiSi Admin Experience Upgrade — قرارداد فنی (M0)

شاخه: `feature/admin-panel-modernization-20261029` — مبنا: `6d6258d3316acb4284d2fe4bd6c7c0778310da14`
فقط QA/Dev. هیچ Migrationِ Production، Deploy یا Publish انجام نمی‌شود.

این سند نتیجه‌ی بررسی فقط‌خواندنیِ کد پیش از هر تغییر است. هر تصمیم با مسیر منبع ثبت شده تا در QA قابل ردیابی باشد.

---

## ۱. نقشه‌ی صفحه‌های تکراری

| موضوع | صفحه‌ی مرجع (ویرایش) | مسیر دوم (وضعیت امروز) | تصمیم |
|---|---|---|---|
| روش‌های ارسال | `/admin-portal/shipping/setup/` (`views.shipping_setup`, `shipping_method_simple_update`, مجوز `shipping.manage`) | `settings/?section=delivery-payment` فقط **خلاصه + لینک** است (partial `settings_delivery_payment.html`)؛ تستِ `test_followup09_shipping` از قبل «بدون سوییچ دوم» را تضمین می‌کند. مسیر قدیمی `settings/shipping/<pk>/toggle/` هنوز وجود دارد و در تست‌ها استفاده می‌شود. | دکمه‌ی لینک → «مدیریت ارسال». مسیر toggle قدیمی **حفظ** می‌شود (سازگاری، مجوز `settings.payment`، تست‌ها)؛ از هیچ فرمی صدا زده نمی‌شود. |
| مالیات | `/admin-portal/tax/settings/` (`views.tax_settings`، مجوز `tax.manage`) فقط **وضعیت/گردکردن/دسته‌ی پیش‌فرض** را ویرایش می‌کند | `settings/?section=finance` فرم `FinanceSettingsForm` را دارد که **نرخ کلی `tax_percent`** را ویرایش می‌کند (مجوز `settings.manage`) → نرخ و وضعیت در دو فرم مستقل. | نرخ کلی به `tax/settings` منتقل می‌شود. `finance` فقط خلاصه (وضعیت/نرخ) + «مدیریت مالیات». `POST settings-finance` فقط `free_shipping_threshold` را می‌پذیرد و `tax_percent` را **نادیده** می‌گیرد (فرم‌های قدیمی خطا نمی‌دهند اما نرخ عوض نمی‌شود). |
| آستانه‌ی ارسال رایگان، کادوپیچی | `finance` | — | در همان دسته‌ی «مالی» می‌ماند (مستقل از مالیات). |
| انقضای سفارش پرداخت‌نشده | کارت درون `finance` | — | دسته‌ی جدا «مدیریت سفارش‌های پرداخت‌نشده» (`?section=unpaid-orders`)؛ `POST settings-order-expiry` همان نام مسیر، مقصد بازگشت جدید. |

مصرف‌کنندگان لینک‌ها که نباید بشکنند: `checklist_service` (`shipping-setup`, `tax-settings`)، `navigation.py` (تب‌های ارسال/مالیات/تنظیمات مالی)، `gift_wrap_products.html` (`?section=finance`)، `test_admin_panel_compat_redirect` (`/admin-panel/settings/?section=finance`).

## ۲. موجودیت‌ها و مالکیت داده

- `core.ShopSettings` — یک ردیف به‌ازای هر Store. `tax_enabled`(default **True** امروز)، `tax_percent`(default 9)، `tax_setup_confirmed_at`، `unpaid_online_order_ttl_minutes`(0 = غیرفعال)، `unpaid_online_order_grace_minutes`(30)، `unpaid_expiry_notify_sms`(False)، `free_shipping_threshold`.
- محل‌های ساخت `ShopSettings`: `ShopSettings.provision_for` (مسیر واحد؛ فراخوانی از `portal/services/provisioning_service.py:154` و seedها)، Migration `0006_backfill` (تاریخی؛ **دست‌نخورده**)، تست‌ها (`ShopSettings.objects.create`). `ShopSettings.load` فقط می‌خواند و هرگز نمی‌سازد.
- `settings.SHOP_TAX_PERCENT = 9` فقط در `provision_for`/Migration 0006/context processor خوانده می‌شود.
- مالیات: `orders.TaxClass`, `orders.TaxRate` + `tax_service.calculate_order_taxes`: اگر `tax_enabled=False` → همه صفر؛ اگر Store هیچ `TaxRate` نداشته باشد → مسیر «تخت» با `ShopSettings.tax_percent`؛ وگرنه مسیر «دانه‌ریز» (ردیف بدون نرخ منطبق = صفر). اسنپ‌شات سفارش (`Order.tax`, `OrderItem.tax_rate_percent`) در لحظه‌ی ثبت پر می‌شود ⇒ تغییر تنظیمات هیچ سفارش قبلی را عوض نمی‌کند.
- پرداخت: `PaymentGateway` (ردیف قدیمی که Checkout از روی آن فهرست می‌سازد و `Order.payment_gateway` به آن اشاره دارد)، `PaymentGatewayConfig` (پیکربندی عملیاتی/اعتبارنامه‌ی رمزنگاری‌شده، یکتا به‌ازای `store+gateway_code`)، `PaymentAttempt` (state machine)، `Transaction` (رسید)، `PaymentReconciliation`، `Refund`. Registry فقط `zibal` و `cod`.
- واردات: `core.ImportJob`/`ImportRowResult`؛ موتور تک: `import_xlsx.py` (نگاشت هدر/مقدار فارسی) + `import_service.py` (اعتبارسنجی/اجرای همه‌یا‌هیچ). مدل‌ها: `Brand`(store, name, slug یکتا در store)، `Category`(store, parent, slug؛ کالا فقط روی **زیردسته**)، `Attribute`/`AttributeValue`/`ProductAttributeValue`، `Specification`(label/value).

## ۳. مجوزها (`apps/stores/authorization.py`)

| کار | مجوز امروز | تغییر |
|---|---|---|
| تنظیم مالیات | `tax.view` / `tax.manage` | بدون تغییر |
| تنظیم ارسال | `shipping.view` / `shipping.manage` | بدون تغییر |
| تنظیمات مالی/انقضا | `settings.manage` | بدون تغییر |
| پیکربندی درگاه | `settings.payment` | کارت‌به‌کارت از همین مجوز استفاده می‌کند |
| ورود اکسل | `import_export.view/manage` | بدون تغییر (ارسال فایل/پیش‌نمایش/اجرا) |
| تأیید/رد موجودیت پیشنهادی واردات | — | **`brand.manage` و `category.manage`** (مجوزهای موجود؛ برند/دسته‌ی جدید فقط کسی تأیید می‌کند که می‌تواند بسازد). ویژگی: `attribute.manage` |
| بررسی کارت‌به‌کارت | — | **جدید `order.review_card_transfer`** (Owner, Administrator, Order Manager — مشابه `order.confirm_cod_payment`) |

## ۴. وابستگی‌های پرداخت (الگوهای قابل استفاده‌ی مجدد)

- گذار «پرداخت موفق» **فقط** از `lifecycle.apply_payment_success` (UPDATE شرطی `payment_status`، `mark_redeemed`، Transaction OK، رویداد اعلان، hook کمپین، `PROCESSING`، پیامک). تأیید دستی COD (`cod_payment_service.confirm_collection`) الگوی دقیق ما: `select_for_update` روی Order، مبلغ دقیقاً برابر، `record_audit_event`، `AlreadyConfirmed` برای تأیید تکراری.
- `gateway_payment_service.initiate_payment`: برای درگاه آفلاین، Attempt را **فوراً `SUCCEEDED`** می‌کند (COD). کارت‌به‌کارت نباید چنین شود ⇒ ویژگی adapter `requires_manual_confirmation`؛ Attempt در `PENDING` می‌ماند تا تأیید مدیر.
- انقضا (`order_expiry_service`): فقط سفارش «قطعاً آنلاین». Adapter کارت‌به‌کارت `is_online=False` ⇒ هرگز از مسیر درگاه آنلاین منقضی نمی‌شود. (ریسک مستند: سفارش در انتظار بررسی تا لغو دستی موجودی را نگه می‌دارد.)
- Checkout: لیست روش‌های پرداخت از `PaymentGateway(is_active)`؛ `payment_start → payment_initiate` بر اساس `slug` ردیف قدیمی، `PaymentGatewayConfig` فعال را می‌یابد. مالکیت: `_get_own_order` (مشتری) + `request.store`.
- وضعیت «در انتظار بررسی پرداخت»: `Order.PaymentStatus` تغییر نمی‌کند (کوئری‌های `PENDING` در انقضا/COD/lifecycle بدون تغییر می‌مانند)؛ این وضعیت از مدل جدید `CardTransferSubmission` **مشتق** و در UI نمایش داده می‌شود.

## ۵. معماری واردات پیشرفته (بدون موتور دوم)

۱. ستون‌های قالب: ابتدا الزامی‌ها (نام، دسته، قیمت)، سپس هویت (شناسه/SKU)، سپس اختیاری (برند، موجودی، …)؛ رنگ‌بندی (الزامی/اختیاری/فقط‌برای‌به‌روزرسانی)؛ شیت‌ها: راهنما، داده‌ها، فهرست‌ها (+ نمونه). افزودن ستون «زیردسته» (مسیر والد > فرزند همچنان پذیرفته) و «مشخصات» (`برچسب: مقدار` در هر سلول) روی `Specification`، و «ویژگی‌ها» روی `Attribute` موجود.
۲. مرجع جدید: مدل `ImportProposal` (Store‑scoped؛ job، نوع [brand/category/subcategory/attribute/attribute_value]، نام، کلید نرمال، مسیر والد، ردیف‌های منبع، درخواست‌دهنده، وضعیت [pending/approved/rejected]، تصمیم‌گیرنده/زمان/دلیل، شیء ساخته‌شده). یکتایی: `(job, kind, parent_key, normalized_key)`.
۳. هم‌ارزی نام‌ها با `core.utils.normalization_key` (فارسی/ZWNJ/شکل حروف) — موجود ⇒ استفاده‌ی مجدد، نه پیشنهاد.
۴. پیش‌نمایش: ردیفِ دارای نام ناشناخته ⇒ «در انتظار تأیید» (نه خطای سخت)، اجرا تا تعیین‌تکلیف همه‌ی پیشنهادها مسدود. تأیید ⇒ ایجاد رکورد واقعی در جدول Store (تراکنش اتمیک، audit)، رد ⇒ ردیف وابسته خطای قابل‌اصلاح. اجرا مجدد همان فایل ⇒ بدون تکرار (هم‌ارزی + قید یکتا).
۵. دکمه‌ی «ورود گروهی کالا با اکسل» در فهرست کالا ⇒ همان `import-*` (جریان: قالب Store-specific ← آپلود ← پیش‌نمایش ← تأیید پیشنهادها ← اجرا ← گزارش).
۶. امنیت XLSX، Formula Injection، سقف حجم/ردیف، اتمیک‌بودن و سازگاری `ImportJob` دست‌نخورده می‌ماند.

## ۶. معیارهای پذیرش (ماتریس)

| # | معیار | تست |
|---|---|---|
| A1 | Storeِ تازه: `tax_enabled=False`, `tax_percent=10.00` (قابل تنظیم با Django settings)، مالیات سبد = ۰ | `test_new_store_tax_defaults` |
| A2 | فعال‌سازی ۱۰٪ ⇒ محاسبه‌ی درست در سبد/Checkout/سفارش | `test_enable_tax_10_percent_flow` |
| A3 | Storeهای قدیمی و سفارش‌های ثبت‌شده دست‌نخورده (داده‌ی `tax_enabled=True/9٪` بعد از Migration همان) | `test_legacy_tax_rows_unchanged` |
| A4 | نرخ مالیات فقط از `tax/settings` ویرایش می‌شود؛ `settings-finance` نرخ را عوض نمی‌کند | `test_tax_rate_single_editor` |
| A5 | ارسال: یک مرجع ویرایش، دکمه‌ی «مدیریت ارسال»؛ مسیر قدیمی سالم | `test_shipping_single_reference` |
| B1 | رمز عبور: دکمه‌ی چشم در جای ثابت، RTL+LTR، موبایل | browser + unit |
| B2 | انقضا: دسته‌ی جدید، پیش‌فرض خاموش، COD مستثنا، کارت‌به‌کارت منقضی نمی‌شود | تست‌های انقضا |
| C1 | ۵ برند جدید ⇒ بعد از تأیید دقیقاً ۵ برند؛ ورود مجدد ⇒ بدون تکرار | `test_import_five_new_brands` |
| C2 | رد پیشنهاد ⇒ کالا منتشر/وصل نمی‌شود | `test_rejected_proposal_blocks_row` |
| C3 | ایزولاسیون Store و مجوز تأیید | تست‌های مجوز |
| D1 | کارت‌به‌کارت تا تأیید Paid نیست؛ تأیید یک‌بار؛ رقابت همزمان | `test_card_transfer_*` |
| D2 | مشتری سفارش/پرداخت Store یا کاربر دیگر را نمی‌بیند/تغییر نمی‌دهد | `test_card_transfer_isolation` |
| D3 | هیچ‌گاه شماره‌ی کامل کارت/CVV2/رمز ذخیره نمی‌شود | `test_card_transfer_rejects_full_card_number` |
| D4 | Zibal و COD بدون تغییر رفتار | تست‌های موجود |
| E1 | Dashboard/Orders/Catalog/Tax/Shipping/Import موجود سبز؛ R4 و Vision Studio سالم | Regression |

## ۷. ریسک‌ها و مرزها

- تغییر پیش‌فرض مدل `tax_enabled`/`tax_percent` فقط ردیف‌های **تازه** را متأثر می‌کند (Migration `AlterField` بدون به‌روزرسانی داده). تست‌هایی که با `ShopSettings.objects.create` مالیات می‌خواهند باید صریحاً فعال کنند (فهرست در گزارش نهایی).
- Firefox/Windows در کانتینر قابل نصب نیست؛ فقط Chromium تست می‌شود.
- هیچ cron/سرویس زمان‌بندی فعال نمی‌شود؛ فقط مستند.
