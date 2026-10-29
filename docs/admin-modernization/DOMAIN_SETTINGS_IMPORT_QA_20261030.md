# Domain guide · Settings IA · Excel quick guide — QA report (local, not pushed)

Base: `ccdf0dd1` (remote). Local commits on top: `0198da3d`, `cfceab30`, `f26d8af7`, `4294a25e` (+ this report).
Untouched on purpose: domain verification / TLS / freshness / DOMAIN_MANAGE / Step-Up / audit services, models, migrations, Cart.store, production.

| وضعیت | فایل | تغییر | تست | ریسک |
|---|---|---|---|---|
| انجام | `apps/stores/services/domain_guide_service.py`, `apps/portal/templates/portal/app/custom_domains.html`, `apps/portal/views.py` | راهنمای ۶مرحله‌ای دامنه در پورتال: TXT/A/CNAME با Host/Type/Value و Copy، فقط از `RASTISI_CUSTOM_DOMAIN_*`، حالت صادقانهٔ «آماده نیست»، فعال‌سازی فقط با آمادگی تازه | `test_domain_guide_service`, `test_domain_guide_views` | بدون تنظیم `RASTISI_CUSTOM_DOMAIN_A_TARGETS/CNAME_TARGET` در Production، جدول اتصال نمایش داده نمی‌شود (عمداً) |
| انجام | `apps/dashboard/views.py`, `services/domain_settings_service.py`, `partials/settings_domain.html` | صفحهٔ «تنظیمات ← دامنه و آدرس» (فقط‌خواندنی، لینک به پورتال با reverse، بدون دسترسی = بدون دکمه) | `test_domain_settings` | DNS/TLS واقعی در QA اجرا نشده (Mock) |
| انجام | `apps/dashboard/navigation.py`, `settings.html`, `_admin_section_tabs.html`, `admin_ui.{css,js}` | معماری اطلاعات تنظیمات: ۸ دسته + زیرصفحه، یک ردیف تب، جستجوی واقعی با فیلتر دسترسی، لینک‌های قدیمی `?section=` | `test_admin_navigation` (+IA), `test_settings_views`, `test_permission_enforcement` | برچسب‌ها تغییر کرده‌اند؛ تست‌های متنِ قدیمی عمداً به‌روز شدند |
| انجام | `import_xlsx.py`, `import_upload.html` | راهنمای سریع ۴ مرحله‌ای + شیت «نمونه» برای قالب تنوع‌ها (از اسکیمای واقعی) | `test_import_modernization` (Preview 3/3/0 + اجرا؛ پیش‌نمایش چیزی را تغییر نمی‌دهد) | نمونه فقط آموزشی است؛ dropdown پویا (Jules) پیاده نشد |
| انجام | `settings_unpaid_orders.html` | بازگرداندن عنوان کامل صفحهٔ مدیریت سفارش‌های پرداخت‌نشده | `test_order_expiry` | — |

## Tests
- Full suite at `f26d8af7`: 11 774 tests, 36 FAIL + 4 ERROR (209 skipped). Versus the 39-id baseline (`TEST_RECONCILIATION_20261029.md`): 2 new failures (`ExpirySettingsViewTests` ×2, caused by this work, fixed in `4294a25e`; targeted re-run of 178 tests OK). The remaining ids are the baseline set (`test_product_image_views…reorders_by_posted_sequence` passed this time — order-dependent, not claimed fixed). The full suite has not been re-run after `4294a25e`; no green full-suite claim.
- Import suites (209 tests) OK.
- Browser (Chromium only; Firefox unavailable here): 390/768/1440, no horizontal scroll, one tab row, no page errors; 3 sequential checkouts on the isolated QA env gave 3 distinct orders. Media 404s are missing demo images, not code.
- Screenshots: before = `ccdf0dd1` served on a copy of the QA DB, after = this branch.
