# V5 Composer — ادامهٔ کار (Checkpoint جلسهٔ قطع‌شده)

## وضعیت Git
* Worktree: `/home/user/V5_STUDIO_WT_20261023` — شاخهٔ محلی `local/v5-linked-image-announce` — HEAD `522c0645e240de6ce535c8c857cc676e711eabf9`
* پاک است (فقط symlink عمدی `media` untracked؛ هرگز Commit نشود). هیچ Reset/Clean/Checkout مخرب انجام نشده.
* شاخهٔ ریموت `feature/v5-design-studio-20261020` هنوز روی `4a6ee64` است؛ چهار Commit زیر **Push نشده‌اند** (Push فقط پس از تأیید Regression، به‌صورت fast-forward: `git fetch origin` + بررسی ancestor + `git push origin HEAD:refs/heads/feature/v5-design-studio-20261020`؛ نه main، نه force).
* Commitهای محلی (۲۸ فایل، +۳۶۳۷/−۲۶۶):
  1. `ade93ce` مدل Group تو در تو (`parent_cell`، migration 0022، سرویس‌ها، Mutationها، تاریخچه) — ۱۹ تست سرویس
  2. `054f4b9` رندر بازگشتی + CSS گروه/محور عمودی + fragment آگاه از تو در تویی + endpoint خواندن
  3. `6ed3630` UI: `r4_composer.js`، توسعهٔ `r4_resize.js`، endpoint `layout-tree`، سناریوهای Chromium A–C، به‌روزرسانی چهار تست Pin
  4. `522c064` سناریوهای Chromium D–F + `V5_COMPOSER_ARCHITECTURE.md`
* انتقال امن: Bundle و Patch در `/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/checkpoint/` (`v5-composer-4a6ee64..522c064.bundle`، `patches/0001..0004`). اعمال: `git fetch <bundle> HEAD` یا `git am patches/*.patch`.

## نتایج تست (تکرار نشود)
* `test_v5_groups_service` (۱۹) و `test_v5_groups_render` (۷): همه سبز.
* Chromium (`SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests`) ماژول `test_v5_composer_browser`: سناریوهای A (۹ سلول تو در تو)، B (طراحی گروه والد/فرزند مستقل)، C (تغییر اندازه والد/فرزند/ردیف عمودی + Undo/Redo + Refresh)، D (کامپوننت‌های واقعی Registry)، E (هدر/فوتر روی بوم + PDP با یک فرم خرید + سبد/Checkout)، F (ساخت/ویرایش/Refresh/Undo/Redo/حذف با تأیید/پیش‌نمایش Draft/انتشار دسکتاپ و موبایل) — هر شش تک‌تک سبز؛ اجرای یکجا همراه ۶ تست قدیمی استودیو هم سبز (۱۲ تست، ۴۷۹ ثانیه).
* اسکرین‌شات‌ها: `/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/shots/composer_*.png`.
* Regression کامل #۱ (قبل از اصلاح Pinها، لاگ `/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/full_run12.log`): ۱۱٬۴۷۲ تست، ۴۱ شکست/خطا؛ ۴ مورد نسبت به Baseline (`/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/run7_sorted.txt`، ۳۸ شناسه) جدید بودند: سه Pin که فایل قالب را می‌خوانند (اصلاح و سبز شد) و یک تست زمان‌بندی `test_contrast_utils...cheap_enough` (Flaky زیر بار؛ تنها اجرا شد و سبز بود).
* Regression کامل #۲ روی Snapshot نهایی (`/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/snap7`، HEAD فعلی) **در حال اجرا بود**: لاگ `/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/full_run13.log` (آخرین خط `exit=` پایان را نشان می‌دهد). مقایسه: 
  `grep -E "^(FAIL|ERROR): " /tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/full_run13.log | sed -E 's/^(FAIL|ERROR): [^ ]+ \((.*)\)$/\1/' | sort -u > run13.txt; sed -E 's/^[^ ]+ \((.*)\)$/\1/' /tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/run7_sorted.txt | sort -u > run7n.txt; comm -13 run7n.txt run13.txt`
  انتظار: هیچ شکست جدید جز Flakyهای زمان‌بندی. اگر لاگ ناقص ماند (سشن قطع شد)، فقط همین یک اجرا تکرار شود.

## کامل‌شده
مدل/سرویس/History/Publish/Clone Group؛ رندر یکسان Preview و Published؛ UI انتخاب خانه/گروه، نوار ابزار یکسان، منوی چیدمان (۲/۳ افقی و عمودی + افزودن خانه)، لایه‌ها (هدر ← صفحه ← فوتر)، بازرس گروه (محتوا، تم، متن، رنگ، پس‌زمینه ساده/گرادیان/تصویر کتابخانه/الگو، فاصله، حاشیه، دستگاه‌ها، موبایل)، ویرایش درجای عنوان، دستگیره‌های درصدی (ستونی و ردیف عمودی)، حذف با تأیید، هدر/فوتر کلیک‌پذیر، PDP با یک جریان خرید.

## نیمه‌تمام / ادامه
1. تأیید نتیجهٔ Regression #۲ سپس Push fast-forward (بالا).
2. PDP: `product_main` به اسلات تقسیم نمی‌شود (عمداً؛ قرارداد خرید). اگر لازم شد، فقط از طریق تنظیمات `product_main` موجود.
3. ویرایش درجای متن Sectionها (فعلاً فقط عنوان/توضیح گروه؛ بقیه از بازرس Section).
4. جابه‌جایی با کشیدن (Drag & Drop) خانه‌ها؛ فعلاً دکمهٔ ↑↓/→←.
5. تبلت: فقط پرچم پنهان‌سازی جدا؛ بقیه از دسکتاپ.
6. رنگ پس‌زمینهٔ Group هگز است؛ توکن پالت فقط برای متن/حاشیه.
7. ویندوز/QA ویندوز بررسی نشده.
8. مستندات تکمیلی: `V5_COMPOSER_ARCHITECTURE.md` (ماتریس EXISTS/PARTIAL/MISSING).

## نکات اجرا
* تست‌های محلی: `DJANGO_MEDIA_ROOT` و `DJANGO_PRIVATE_MEDIA_ROOT` ایزوله؛ venv در `/tmp/claude-0/-home-user-Rastisi6-14040616/dcd3e3c2-3881-52c2-a73d-f1546e95622e/scratchpad/venv`.
* معماری R4 حفظ شده: هر تغییر = یک Mutation = یک Revision؛ هیچ رندر/ذخیرهٔ موازی نیست.

## تحدیث پس از پایان Regression #۲ (full_run13.log)
۱۱٬۴۷۹ تست؛ ۴۴ شکست/خطا. نسبت به Baseline هفت مورد جدید بود که همه اصلاح و تک‌تک سبز شد (Pinهای شل استودیو: تعداد دکمه‌های ریل ۱۰→۱۲، اسکریپت‌ها ۶→۷، اکشن‌های مجاز، نوع Mutationهای لایهٔ resize و ترتیب نوار ابزار؛ opacity دکمهٔ غیرفعال؛ regex تست رندر). بقیهٔ شکست‌ها = Baseline (از جمله `test_phase28_canvas_first_ux...three_column_contract`). Regression کامل سوم اجرا نشد؛ فقط ماژول‌های مرتبط بعد از اصلاح اجرا شدند.
