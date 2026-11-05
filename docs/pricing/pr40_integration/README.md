# التزامِ PR #41 (تعرفه) با PR #40 (پرداختِ پلتفرم) — ممیزیِ سازگاری (۲۰۲۶-۱۱-۰۵)

روش: ادغامِ آزمایشیِ `pricing/dynamic-plans-20261105` روی سرِ `financial/platform-billing-20261105` (`e6f57b93`) در یک worktreeِ موقت؛ **هیچ‌یک از دو شاخه‌ی PR تغییر نکرد** و چیزی push نشد. هر دو از `0f95379a` منشعب شده‌اند.

## نتیجه

| بررسی | نتیجه |
|---|---|
| فایل‌هایِ مشترکِ تغییریافته | `billing/services/confirmation_service.py`، `dashboard/views.py`، `portal/platform_admin_urls.py`، `portal/platform_admin_views.py`، `portal/templates/portal/app/billing_plans.html`، `portal/views.py` |
| تداخلِ متنی (۲ فایل) | `portal/views.py` و `billing_plans.html` — هر دو در همان تابعِ checkout: PR #40 پارامترِ `gateway` را افزوده، PR #41 پارامترِ `billing_interval` را |
| **نقصِ معنایی که git بی‌صدا ادغام کرد (بدونِ conflict)** | در `billing_step_up_verify`، ادغامِ خودکار `return _start_purchase(..., gateway=...)` را *پیش از* خطوطِ مربوط به `billing_interval` گذاشت ⇒ کدِ دوره **dead code** می‌شد و پس از OTP همیشه دوره‌ی پیش‌فرض خرید می‌شد. اصلاح در `portal_checkout_combined.patch` است |
| گرافِ مهاجرت | هیچ leaf-nodeِ متعارض نیست: PR #40 فقط `portal.0017/0018`، `billing.0010`؛ PR #41 فقط `subscriptions.0009–0012`. `migrate` از صفر روی PostgreSQL ۱۶ و `makemigrations --check` ⇒ «No changes detected» |
| تست‌هایِ ترکیبی | `apps.subscriptions apps.billing apps.portal(billing/step-up/pricing/journeys/public-site) apps.dashboard(billing/subscription)` روی ادغامِ حل‌شده: **۷۰۰ تست OK** (۱۱ skip) + سه تستِ تازه‌ی ترکیبی (`test_pricing_x_platform_billing_integration.py.txt`): دوره‌ی سالانه از درگاهِ پلتفرم پرداخت و فعال می‌شود و تمدیدِ سالانه صادر می‌شود؛ ناهم‌خوانیِ مبلغِ دوره با درگاه هرگز فعال نمی‌کند؛ ادامه‌ی step-up هم `gateway` و هم `interval` را نگه می‌دارد |
| جداییِ درگاه‌ها | هیچ تغییری در `PlatformGatewayConfig`/`PaymentGatewayConfig` در PR #41 نیست |

## ترتیبِ پیشنهادیِ ادغامِ نهایی
1. PR #40 اول (مالی/درگاه، ریسکِ بیشتر، آماده‌ی بازبینی مالک). 
2. سپس PR #41 روی آن: ادغام، حل‌ِ دو conflict با `portal_checkout_combined.patch` (فایل‌هایِ حل‌شده‌ی `portal/views.py` و `billing_plans.html` نسبت به سرِ PR #40)، افزودنِ `test_pricing_x_platform_billing_integration.py.txt` به `apps/billing/tests/` با پسوندِ `.py`، سپس `makemigrations --check` و اجرایِ تست‌هایِ بالا.
3. یا برعکس: PR #41 اول و سپس PR #40 — در این حالت conflictِ مشابه روی PR #40 است و همان patch معیار است.

## نکته‌ی UI
در `billing_plans.html` انتخابگرِ درگاه (PR #40) داخلِ فرمِ هر دوره قرار می‌گیرد؛ برایِ پلن‌هایِ چنددوره‌ای انتخابگر در هر فرم تکرار می‌شود. پیشنهاد: پس از ادغام، انتخابگرِ درگاه یک‌بار بالایِ فهرست (خارج از فرم‌ها، با `form` attribute) قرار گیرد — تغییرِ ظاهری، نه منطقی.
