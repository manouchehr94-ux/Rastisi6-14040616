# Event Catalog — اعلان‌های مدیران RastiSi (۱۴۰۵/۰۸/۱۰)

این جدول از خودِ رجیستری (`apps/notifications/registry.py`) تولید شده و یک تست (`test_inbox_wiring.CatalogTruthTests`) تضمین می‌کند هر نوعِ ثبت‌شده واقعاً در کد منتشر می‌شود و هیچ رویدادِ «فقط برنامه‌ریزی‌شده» در رجیستری نیست.

## رویدادهای پیاده‌سازی‌شده و متصل (منبع واقعی دارند)
| کلید | عنوان | دسته | محدوده | اهمیت | مخاطب (مجوز) | فوری/Toast | تجمیع | منبع واقعی (Trigger) | شرط جلوگیری از تکرار |
|---|---|---|---|---|---|---|---|---|---|
| `order.created` | سفارش جدید | سفارش‌ها | فروشگاه | معمولی | ORDERS | فوری | خیر | orders.order_service.place_order → business_events.order_created | `order:<pk>` |
| `order.canceled` | لغو سفارش | سفارش‌ها | فروشگاه | مهم | ORDERS | — | خیر | orders.order_service.change_status(canceled) → business_events.order_status_changed | `order-canceled:<pk>` |
| `return.requested` | درخواست مرجوعی | سفارش‌ها | فروشگاه | مهم | RETURN_VIEW | — | خیر | orders.return_service.create_return_request → business_events.return_event(requested) | `return:<pk>` |
| `payment.failed` | پرداخت ناموفق | پرداخت و امور مالی | فروشگاه | معمولی | ORDERS | — | بله | orders.gateway_payment_service.process_callback_and_verify (فقط شکستِ قطعیِ PaymentAttempt: `fail(..., definitive=True)`، پس از commit) → admin_events.payment_attempt_failed؛ شبیه‌ساز: payment_service.simulate_payment | `payattempt:<public_id>` (هر تلاش یک بار) + گروه `pay-failed:order:<pk>` |
| `payment.suspicious` | پرداخت مشکوک / مغایرت | پرداخت و امور مالی | فروشگاه | بحرانی | REFUND_MANAGE | — | خیر | orders.gateway_payment_service → business_events.late_payment | `reconcile:<pk>[:confirmed]` |
| `refund.completed` | بازپرداخت انجام شد | پرداخت و امور مالی | فروشگاه | معمولی | REFUND_VIEW | — | خیر | orders.refund_service → business_events.refund_completed | `refund:<pk>` |
| `payment.card_transfer_submitted` | رسید کارت‌به‌کارت منتظر بررسی | پرداخت و امور مالی | فروشگاه | مهم | ORDER_REVIEW_CARD_TRANSFER | فوری | خیر | orders.card_transfer_service.submit | `c2c:<pk>` |
| `import.failed` | خطا در ورود گروهی | کالا و موجودی | فروشگاه | مهم | IMPORT_EXPORT_VIEW | — | خیر | dashboard.import_service (وضعیت FAILED / COMPLETED_WITH_ERRORS) | `import-failed:<pk>` |
| `stock.out` | اتمام موجودی | کالا و موجودی | فروشگاه | مهم | INVENTORY_MANAGE | — | بله | catalog.inventory_service.decrement_stock_for_order_item (رسیدن به صفر) | گروه `stock:<store>:<product>` + فقط لحظه‌ی صفر شدن |
| `stock.low` | موجودی کم | کالا و موجودی | فروشگاه | مهم | INVENTORY_MANAGE | — | بله | catalog.inventory_service.decrement_stock_for_order_item (عبور از آستانه‌ی low_stock_threshold) | گروه `stock:<store>:<product>` + فقط لحظه‌ی عبور از آستانه |
| `review.pending` | نظر جدید نیازمند بررسی | مشتریان و پیام‌ها | فروشگاه | معمولی | CONTENT | — | بله | catalog.views.product_review_submit → business_events.review_created | گروه `reviews:<store>` |
| `staff.role_changed` | تغییر نقش یا سطح دسترسی | امنیت | فروشگاه | مهم | MEMBERSHIP | — | خیر | stores.membership_service.change_role | `role:<pk>:<role>:<دقیقه>` |
| `staff.access_revoked` | لغو دسترسی یک عضو | امنیت | فروشگاه | مهم | MEMBERSHIP | — | خیر | stores.membership_service.revoke_membership | `revoked:<pk>` |
| `subscription.grace_period` | اشتراک وارد مهلت پرداخت شد | اشتراک و حساب | فروشگاه | مهم | SUBSCRIPTION_VIEW | — | خیر | subscriptions.subscription_service.enter_grace_period (فقط در گذارِ واقعیِ وضعیت؛ مسیرِ Dunning: `_process_invoice`) | `sub:<pk>:grace_period:<شناسه‌ی آخرین SubscriptionEvent>` |
| `subscription.past_due` | اشتراک معوق شد (**خفته** — `lifecycle=dormant`، `wired=False`) | اشتراک و حساب | فروشگاه | بحرانی | SUBSCRIPTION_VIEW | — | خیر | subscriptions.subscription_service.mark_past_due — در جریانِ تولیدی هیچ مسیرِ فراخوانی ندارد؛ فقط تعریف و تست | `sub:<pk>:past_due:<شناسه‌ی آخرین SubscriptionEvent>` |
| `subscription.suspended` | اشتراک تعلیق شد | اشتراک و حساب | فروشگاه | بحرانی | SUBSCRIPTION_VIEW | — | خیر | subscriptions.subscription_service.suspend_subscription (فقط در گذارِ واقعی) | `sub:<pk>:suspended:<شناسه‌ی آخرین SubscriptionEvent>` |
| `domain.verified` | دامنه تأیید شد | دامنه و زیرساخت | فروشگاه | معمولی | DOMAIN_MANAGE | — | خیر | stores.domain_verification_service.check_dns_verification (موفق) | `domain-ok:<pk>` |
| `domain.verification_failed` | تأیید دامنه ناموفق بود | دامنه و زیرساخت | فروشگاه | مهم | DOMAIN_MANAGE | — | بله | stores.domain_verification_service.check_dns_verification (ناموفق) | گروه `domain:<pk>` |
| `integration.sync_failed` | خطا در عملیات خودکار SEO/IndexNow | یکپارچه‌سازی‌ها | فروشگاه | مهم | SETTINGS | — | بله | core.automation.run (نتیجه‌ی FAILED با کدِ خطا) | گروه `automation:<store>:<operation>` |
| `system.test` | اعلان آزمایشی | رویدادهای سیستمی | فروشگاه | معمولی | هر عضو فعال فروشگاه | فوری | خیر | inbox_views.send_test (فقط به خودِ درخواست‌دهنده) | کلید یکتا برای هر درخواست |
| `platform.store_created` | فروشگاه جدید ساخته شد | اشتراک و حساب | پلتفرم | معمولی | staff + superuser | — | خیر | portal.provisioning_service (ساخت Store) | `store-created:<pk>` |
| `platform.store_status_changed` | تغییر وضعیت فروشگاه | اشتراک و حساب | پلتفرم | مهم | staff + superuser | — | خیر | stores.store_status_service.suspend_store/activate_store | `store-status:<pk>:<وضعیت>:<دقیقه>` |
| `platform.contact_message` | پیام جدید از فرم تماس | مشتریان و پیام‌ها | پلتفرم | معمولی | staff + superuser | — | بله | portal.views.contact (ContactMessage) | گروه `contact` |
| `platform.jobs_unhealthy` | هشدار عملیاتی: کارهای زمان‌بندی‌شده | دامنه و زیرساخت | پلتفرم | بحرانی | staff + superuser | — | خیر | core.management.commands.check_background_jobs (سطح CRITICAL) | `jobs:<ساعت>` |
| `platform.test` | اعلان آزمایشی پلتفرم | رویدادهای سیستمی | پلتفرم | معمولی | staff + superuser | فوری | خیر | inbox_views.send_test | کلید یکتا برای هر درخواست |

سیاستِ مشترک: متن‌ها بدونِ نام/تلفن/آدرسِ مشتری و بدونِ Secret؛ کانال‌ها: صندوقِ دائمی (همیشه) + Toast (طبق تنظیماتِ کاربر) + Web Push (پیش‌فرض خاموش) + ایمیل/موبایل (فقط قرارداد، خاموش). اعلان‌های دسته‌ی «امنیت» و سطحِ «بحرانی» هرگز با تنظیماتِ کاربر از صندوق حذف نمی‌شوند.

## رویدادهای هدف که هنوز منبعِ واقعی ندارند (هیچ اعلانِ ساختگی ساخته نمی‌شود)
| رویداد هدف | چرا هنوز ساخته نشده (منبع/Trigger واقعی وجود ندارد) |
|---|---|
| `payment.gateway_error` | خطای درگاه — لاگ/وضعیتِ ساختاریافته‌ای که برای مدیر قابل‌اطلاع باشد وجود ندارد (فقط ``PaymentTransaction`` با پیامِ خام). |
| `payment.refund_failed` | شکستِ بازپرداخت — ``refund_service`` وضعیتِ نهایی FAILED را به‌عنوان رویداد جدا نمی‌دهد. |
| `settlement.status` | وضعیتِ تسویه — دادهٔ معتبرِ تسویه از درگاه دریافت نمی‌شود. |
| `security.suspicious_login` | تلاشِ ورودِ مشکوکِ مدیر — شمارنده‌ی rate-limit هست اما رویدادِ ساختاریافته برای مدیر نیست. |
| `security.password_changed_admin` | تغییرِ رمزِ مدیر — مسیرِ مستقلِ تغییرِ رمزِ ادمین ثبت‌شده‌ی رویداد نیست (فقط مشتری: ``account.sensitive_changed`` در Outbox). |
| `customers.support_ticket` | تیکت پشتیبانی — ماژولِ تیکت وجود ندارد. |
| `customers.message` | پیامِ مشتری — صندوقِ پیامِ مشتری وجود ندارد. |
| `store.template_published` | انتشار قالب — Trigger واقعی در Studio هنوز رویدادِ دامنه‌ای نمی‌دهد (``StorefrontLayoutVersion`` بدون hook). |
| `store.template_publish_failed` | شکستِ انتشار — همان محدودیت. |
| `vision_studio.error` | خطای Vision Studio — این قابلیت در این کدبیس منبعِ خطای ساختاریافته ندارد. |
| `infra.backup` | پشتیبان‌گیری — زیرساخت Backup در Repository نیست. |
| `integration.token_expired` | انقضای دسترسی سرویس — هیچ Integrationی OAuth/Token منقضی‌شونده ندارد (فقط ID). |
| `integration.torob_readiness` | آمادگی کالا برای ترب — فقط محاسبهٔ نمایشی در صفحه است؛ رویدادِ زمان‌بندی‌شده ندارد. |
| `platform.subscription_event` | رخدادهای اشتراکِ مؤثر بر پلتفرم — ``process_subscription_dunning`` خروجیِ رویداد نمی‌دهد (فقط شمارنده). |


## کلاس‌های چرخه‌ی حیات (`EventType.lifecycle`) و صحتِ رجیستری (۱۴۰۵/۰۸/۱۲)
`production` = تولیدکننده‌ی واقعی در مسیر تولیدی؛ `feature_flagged` / `cron_dependent` = تولیدکننده هست ولی پشتِ پرچم/Cron است؛ `dormant` = ثبت‌شده و دارای تابع، **بدونِ** فراخوانِ تولیدی؛ `test_only` = فقط اعلان آزمایشی؛ `planned` = در `PLANNED` (ثبت‌نشده). کلیدهای بیرونی (`key`) بدونِ تغییر و سازگارِ عقب‌رو هستند. درستیِ هر ادعا را `apps/notifications/producers.py` (جدولِ زنجیره‌ی فراخوانی) و `test_producer_wiring` با تحلیلِ AST می‌سنجد، نه جست‌وجوی رشته.

`payment.refund_failed` همچنان **PLANNED** است: نه Orders `record_refund_result` (بدونِ فراخوانِ تولیدی؛ بازپرداختِ GATEWAY رد می‌شود) و نه Billing `SubscriptionRefund` (ارائه‌دهنده‌ها هرگز `FAILED` تعیین نمی‌کنند) تولیدکننده‌ی قطعیِ شکست ندارند. وابستگی: یک قراردادِ قطعیِ شکست در سرویسِ بازپرداخت (تغییر ماشینِ حالتِ مالی ← نیازمندِ تأییدِ مالک). یک تستِ نگهبان تضمین می‌کند هیچ کدِ تولیدی `Refund.status=FAILED` را ننویسد.
