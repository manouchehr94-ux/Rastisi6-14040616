# چک‌لیست قطعیِ تطبیقِ «هر مسئله ← پیاده‌سازی ← راستی‌آزمایی»

> وضعیت‌ها: **✅ انجام و راستی‌آزمایی‌شده** · **🟡 انجام شده، با محدودیتِ ذکرشده** · **⛔ مسدود (فایل‌های ویندوز/بستهٔ بازیابی لازم است)** · **❓ نیازمند تصمیم مالک**
> «راستی‌آزمایی» یعنی: آزمونِ خودکار (نامِ ماژول) و/یا اندازه‌گیریِ مرورگر واقعی (Chromium، سه عرضِ ۱۴۴۰/۸۲۰/۳۹۰) — نه صرفاً توضیح.

## ۱) هستهٔ موتور و قالب آماده (P0)
| شناسه | مسئله | وضعیت | پیاده‌سازی | راستی‌آزمایی |
|---|---|---|---|---|
| ENG-1 | انتخابِ صریحِ قالب باید ترکیبِ دقیقِ همان قالب را بسازد (نه کمبود، نه بخشِ قبلی) | ✅ | `preset_service.replace_with_ready_template_exact` — یک‌خطِ اعمالِ قالب روی همان Draft؛ مسیرِ «حفظ و ادغام» فقط با `mode="preserve"` صریح | `test_exact_template_replace` (نصب دقیق، بدون باقی‌ماندهٔ قالبِ قبلی) |
| ENG-2 | انباشتِ ۴۵/۵۰ بخش پس از تعویض | ✅ | همان؛ بازتولیدِ زنجیرهٔ واقعیِ حادثه | `LiteralIncidentReproductionTests`: `stationery_spectrum` (۲۶ اسلات) + بخشِ قفلِ اسلاتِ ۱۴ ← `kamand_artisan` ⇒ دقیقاً ۵ بخش، صفر اسلاتِ قدیمی؛ رفت‌وبرگشتِ ۴ بار بدونِ انباشت |
| ENG-3 | A→B→A→B و انتخابِ مجددِ همان قالب | ✅ | همان + no-op واقعی (`already_applied`) | `test_a_b_a_b_never_accumulates`, `test_same_template_again_is_a_true_noop` (pk بخش‌ها/revision/تعداد نسخه‌ها بی‌تغییر) |
| ENG-4 | قالب ۵۱ نسخهٔ ۲ = دقیقاً ۲۱ اسلات | ✅ | ریسیپیِ `stationery_spectrum` v2 (۲۱ ورودیِ home) از بستهٔ بازیابی؛ نصبِ دقیق با `replace_with_ready_template_exact` | `Template51V2CompositionTests` (نصبِ دقیق، A→B→A→B، no-op، ترمیمِ انباشتِ ≥۴۵ به ۲۱)؛ مرورگر: صفحهٔ منتشرشده ۲۱ `.rsec` |
| ENG-5 | ارتقای نسخه ۱→۲ یک کلید بدونِ ادغام نسخه‌ها | ✅ | جایگزینیِ دقیقِ ریسیپیِ نسخهٔ هدف؛ اسلات‌های `v1` باقی نمی‌مانند | سناریوی «۲۴ بخشِ v1 انباشته + نصب» ⇒ ۲۱ |
| ENG-6 | طراحیِ قبلی باید قابل‌بازیابی باشد؛ نه حفظِ بخش‌های قدیمی داخلِ ترکیبِ جدید | ✅ | نسخهٔ ARCHIVEDِ کامل پیش از جایگزینی (`layout_service.archive_draft_snapshot`) + Undo؛ رسانهٔ بخش‌محور (حتی فقط‌فایل/legacy) هم کلون می‌شود | `test_previous_design_is_recoverable_via_version_history`, `test_section_scoped_media_is_restored_with_the_previous_design` |
| ENG-7 | تأییدِ صریح پیش از جایگزینیِ مخرب | ✅ | `replace_confirmation_required` (سمتِ سرور، نه فقط مرورگر) + دیالوگِ فارسیِ Studio | `ConfirmationAndRecoveryTests`, `test_template_refusal_http_contract`; مرورگر: POST اول ۴۰۰، دیالوگ، POST دوم ۲۰۰ |
| ENG-8 | قفل‌ها: نه دورزدنِ بی‌صدا، نه ۵۰۰ | ✅ | `locked_sections_present` با فهرستِ بخش‌ها؛ `allow_locked` فقط با تأییدِ جداگانه؛ نسخهٔ پشتیبان همیشه | `LockTests`, `test_template_refusal_http_contract` |
| ENG-9 | پیش‌نمایشِ فقط‌خواندنیِ `kamand_artisan` با بخشِ قفل = HTTP 500 | ✅ | `resolve_preset_candidate` دیگر قفل را نمی‌سنجد (چیزی نمی‌نویسد)؛ `apply_preset` مخرب همچنان می‌سنجد | `test_preview_candidate_never_fails_because_of_a_lock`, `test_read_only_template_preview_survives_a_locked_section`, `test_preset_candidate_preview` |
| ENG-10 | Reset ← ۴۰۰ و پیامِ عمومیِ «ذخیره کامل نشد» | ✅ | کدِ پایدار + پیامِ فارسیِ دقیق + فهرستِ بخش‌های قفل‌شده در JSON؛ قفل **پیش از** checkpoint سنجیده می‌شود | مرورگر: همان ۴۰۰ ⇒ «این کار انجام نشد چون بخش قفل‌شده‌ای… هیچ تغییری ذخیره نشد. (۱ بخش قفل‌شده)»، بدون مودالِ عمومی؛ `RefusalHttpContractTests` |
| ENG-11 | Reset نباید تغییرِ جزئی بگذارد | ✅ | همه‌چیز در یک تراکنش؛ اکنون قفل پیش از هر نوشتن بررسی می‌شود | `test_reset_with_locked_section_reports_precisely_and_does_not_mutate` |
| ENG-12 | Draft/Published: Published فقط با Publish عوض شود | ✅ | تغییر فقط روی Draft | `test_published_version_is_not_mutated_before_publish`; مرورگر: Published بعد از تعویضِ Draft همان ۲۲ بخشِ قبلی ماند |
| ENG-13 | اطلاعاتِ تجاری/دموی مشترک/فروشگاهِ دیگر دست‌نخورده | ✅ | قالب فقط «دستور طراحی» است | `test_business_data_is_untouched`, `test_other_store_design_is_untouched` (فروشگاهِ دومِ واقعی) |
| ENG-14 | مسیرِ ترمیمِ امنِ Draftِ انباشته (بدون SQL) | ✅ | `diagnose_ready_template_composition` (فقط‌خواندنی) و `apply_ready_template_exact` (پیش‌فرض dry-run) | `test_ready_template_repair_commands` |

## ۲) قراردادِ حالتِ خالی
| EMP-1 | بخشِ قالب نباید به‌خاطرِ نبودِ داده حذف شود؛ در Studio پیامِ فارسیِ روشن | ✅ | `section_empty_state_service` + قالبِ مشترک؛ «فروشگاه شما هنوز برندی تعریف نکرده است.» با لینکِ مدیریتِ برند | مرورگر (استودیو) + `EmptyStateContractTests` |
| EMP-2 | در ویترین عمومی: نمایشِ مؤدبِ غیرمدیریتی؛ داده/لوگوی جعلی ساخته نشود | ✅ | متنِ خنثی («به‌زودی…»)؛ هیچ دستورِ ادمین/لینکِ مدیریت | `test_studio_and_public_markup_differ_only_in_audience`, `test_a_empty_data_driven_sections_stay_on_public_home_with_a_neutral_note` |
| EMP-3 | با افزودنِ داده، *همان* بخش پر شود (بدون نصبِ دوباره) | ✅ | همان بخش؛ فقط نمایش عوض می‌شود | `test_adding_data_later_fills_the_same_section_without_reinstalling` |
| EMP-4 | کلیدهای ثبت‌شده باید با سازندهٔ همان بخش بخوانند | ✅ | (خطایی که در حینِ کار یافت شد: `single_banner`) | `test_every_registered_spec_reads_a_key_its_builder_actually_provides` |

## ۳) پیشنهاد شگفت‌انگیز، قیمت و موجودی
| COM-1 | ISSUE-01: تایمر با هر رفرش دوباره ۸ ساعت | ✅ | ریشه: `now + deadline_hours` در هر رندر. اکنون پایانِ ذخیره‌شده (`Product.discount_ends_at`)؛ بدونِ پایان ⇒ بدونِ تایمرِ ساختگی | مرورگر: ۳ رفرش + دستگاهِ دوم ⇒ یک deadline، باقی‌ماندهٔ ۲۱۵۹۶←۲۱۵۸۰ ثانیه (فقط کاهشی)؛ `AmazingOffersCountdownTests` |
| COM-2 | تخفیفِ منقضی نباید در سبد/پرداخت اعمال شود | ✅ | `Product.is_discount_active` مرجعِ واحد؛ `resolve_effective_price` و کارت/ریل/فیلتر از همان | `CheckoutExpiryTests` (سبدِ ۷۵٬۰۰۰ ← پس از انقضا سفارش ساخته نمی‌شود، قیمتِ جدید ۱۰۰٬۰۰۰) |
| COM-3 | شروعِ کمپین (تبدیلِ «N ساعت» به پایانِ ذخیره‌شده) | 🟡 | `promotion_service.start_promotion` + فیلدهای شروع/پایان در فرمِ کالا. دکمهٔ «شروع کمپین» در Studio ساخته نشد | `test_promotion_window` |
| AVL-1 | ناموجود در صفحهٔ اصلی انتخاب نشود (بدونِ جایگزینیِ ناموجود) | ✅ | `availability_service` (موجودی−رزرو؛ تنوع برایِ کالایِ متغیر) | `HomeRailTests`; مرورگر: ۰ کارتِ ناموجود در صفحهٔ اصلی |
| AVL-2 | در فهرست/کالکشن: موجودها اول، ناموجودها آخر؛ مرتب‌سازی/فیلتر محفوظ | ✅ | `order_available_first` / کالکشن | `OrderingTests`; مرورگر: در همهٔ صفحه‌ها ۴ کالای ناموجود پیوسته در انتهای فهرست |
| AVL-3 | نشانِ «ناموجود»ِ کارت با همان تعریف | ✅ | (خطایی که در مرورگر یافت شد: ۵ کالای متغیر با موجودیِ والدِ ۰ ولی تنوعِ موجود). کالایِ متغیری که اصلاً ردیفِ تنوع ندارد با موجودیِ خودش سنجیده می‌شود | `CardFlagFollowsTheContractTests` |
| PRC-1 | «استعلام قیمت» برای کالا/گروه/کالکشن | ✅ | `pricing_mode_service` + سیگنال‌ها؛ تقدم: صریحِ کالا > دسته (و والدها)/کالکشن > عادی | `PrecedenceTests` (۸ آزمون) |
| PRC-2 | به‌جای قیمت «استعلام قیمت» و رفتن به «درباره ما»؛ ادعای ثبتِ درخواست نشود | ✅ | کارت/PDP/ریل/سبد؛ مقصد = صفحهٔ منتشرشدهٔ `about-us` همان فروشگاه (یا صفحهٔ انتخابی در تنظیمات)؛ نبودنِ صفحه ⇒ بدونِ لینکِ ساختگی | مرورگر: کلیک ⇒ `/pages/about-us/`؛ قیمت در کدِ صفحه نیست؛ JSON-LD بدونِ `offers` |
| PRC-3 | دورزدنِ خرید ممنوع (سبد، Quick Add، سبدِ کهنه، API) | ✅ | رد در `add_item_to_cart` و در ثبتِ سفارش | `PurchaseBlockingTests`، با جهش‌آزمایی (حذفِ گارد ⇒ ۴ آزمون شکست) |
| PRC-4 | قیمت/موجودی/تخفیفِ واقعی دست‌نخورده | ✅ | فقط نمایش و قابلیتِ خرید | `test_real_price_stock_and_discount_are_never_modified` |
| PRC-5 | ثبتِ واقعیِ درخواست/اعلان به مالک | ❓ | عمداً ساخته نشد (طبقِ همین پیام: فقط ناوبری) | نیازمندِ تصمیم |
| PRC-6 | Bulk-select در فهرستِ محصولات | 🟡 | «انتخابِ چندتایی» از راهِ کالکشن + سرویسِ `bulk_set_product_mode`؛ ستونِ انتخابِ گروهی در جدولِ محصولات ساخته نشد | سرویس تست شده (`test_bulk_set_never_touches_other_store`) |

## ۴) صفحهٔ فهرست
| LST-1 | فضای خالیِ زیادِ بالای محصولات | ✅ | سه ردیفِ جدا (ردیفِ بارگذاریِ مخفی + شمارنده + چیپ) ← یک ردیفِ فشرده؛ نشانگرِ بارگذاری overlay | مرورگر: اولین کارت از y=۳۶۲←۲۸۸ (۱۴۴۰)، ۴۵۴←۳۸۰ (۸۲۰)، ۴۴۵←۳۷۱ (۳۹۰) |
| LST-2 | جایگاه/هم‌پوشانیِ «اعمال فیلتر» و «حذف همه» | ✅ | یک کانتینرِ `.plp-actions`؛ ۴۴px؛ کارتِ فیلتر محدود به ارتفاعِ نمایشگر | مرورگر: قبل: هم‌پوشانی (`applyResetOverlap=true`) در هر سه عرض؛ بعد: `false`، بدونِ overflow افقی |
| LST-3 | سایدبار/جستجو/مرتب‌سازی/صفحه‌بندی با هم | ✅ | بدونِ تغییرِ منطقِ فیلتر | `test_listing_layout_contract` + سوئیت‌های قدیمیِ catalog |

## ۵) ردیف‌های دوستونه
| ROW-1 | سازندهٔ ردیفِ دوستونه (برند + مقالات) ۵۰/۵۰، ۳۳/۶۷، ۶۷/۳۳ | ✅ | موتورِ Container/Cell **از قبل** داشت (`half`، `third_*`، `quarter_*`)؛ ساختِ موازی نشد | `TwoColumnRowTests`: ساخت، تغییرِ نسبت بدونِ از دست رفتنِ بخش/هویت، تنظیماتِ مستقل، Undo، ایزولاسیونِ فروشگاه؛ مرورگر: سلولِ برندِ خالی کنارِ سلولِ مقالات |

## ۶) مجله، خبرنامه/فوتر، دمو (از بستهٔ بازیابی؛ در درخت یکپارچه)
| ID | مورد | وضعیت | پیاده‌سازی | راستی‌آزمایی |
|---|---|---|---|---|
| J-1 | مجله: لیست `/journal/` و جزئیات | ✅ | پچ ۰۲؛ هدر/فوترِ موتور واحد | `JournalPublicPagesTests`؛ مرورگر: ۲۰۰ در سه عرض، بدونِ overflow |
| J-2 | `BlogPost.store` + مهاجرت `blog.0002` | ✅ | پچ ۰۳ | `JournalStoreIsolationTests`؛ `migrate` روی کپیِ DB موفق |
| J-3 | چهار مقالهٔ دموی پوشاک (opt-in، idempotent) | ✅ | `seed_rasti_mode_demo_journal` | `DemoJournalSeedTests`؛ مرورگر: ۴ مقاله در فروشگاهِ scratch |
| J-4 | پیش‌نویس/آینده عمومی نیست | ✅ | `published_posts_for_store` | `test_drafts_and_future_posts_are_not_public` |
| J-5 | کاورِ گم‌شده: جایگزینِ بصریِ غیرجعلی، DB بازنویسی نمی‌شود | ✅ | `has_available_cover` | `test_missing_cover_has_safe_visual_fallback_without_mutating_data` |
| K-1 | خبرنامه: رضایتِ صریح، اعتبارسنجی، تفکیکِ فروشگاه، rate-limit | ✅ | پچ ۰۲/۰۵ | `NewsletterConsentContractTests`؛ مرورگر: بدونِ تیک ثبت نمی‌شود، با تیک موفق |
| K-2 | فوتر / لینکِ نقشه | 🟡 | لینکِ جست‌وجوی نشانی فقط وقتی `FooterSettings.address` ثبت باشد؛ **نقشهٔ جاسازی‌شده ساخته نشد** | مرورگر (آدرسِ موجودِ scratch) |
| K-3 | اینماد/نشان‌های اعتماد | 🟡 | فقط نشانِ واقعاً تنظیم‌شده رندر می‌شود؛ هیچ نشانِ پیش‌فرض/جعلی نیست | نیازمندِ کد/لینکِ رسمیِ فروشگاه (مالک) |
| K-4 | ارسالِ کمپین / لغوِ عضویتِ یک‌کلیکی / تحویلِ ایمیل | ❓ | ساخته نشده (ادعا نمی‌شود) | تصمیمِ مالک |
| K-5 | دو پرچمِ نمایشِ خبرنامه (FooterSettings + footer_config) | ✅ (مستند) | نصب تغییرشان نمی‌دهد | مرورگر پس از فعال‌سازیِ هر دو |
| I-1 | دموی مشترکِ پوشاک + قالب ۵۱ کامل | ✅ | خطِ بازیابی‌شده | `Template51OverSharedDemoTests`، `test_template51_completion_browser` |
| I-2 | پیشنهادهای لحظه‌ای/هیرو/بنر/ناوبری | ✅ (آزمونِ مرورگرِ خطِ بازیابی‌شده) | همان | همان |
| I-3 | تصاویرِ واقعیِ دمو | ⛔ (بیرون از این محیط) | رسانه فقط روی لپ‌تاپ؛ این محیط ۲۲۰ ارجاعِ بی‌فایل دارد؛ گروهِ کنترل نشان داد اتصالِ داده سالم است | ممیزیِ `audit_rasti_mode_demo_media` روی لپ‌تاپ |
| L-1 | پالت/رنگِ سراسری/provenance/variant | ✅ | خطِ بازیابی‌شده + سازگاری با جایگزینیِ دقیق | `test_palette_engine_contract` + `MerchantColourChoicesSurviveExactReplaceTests` |

## ۷) یکپارچه‌سازی
| مورد | وضعیت |
|---|---|
| ادغامِ سه‌طرفه، دو تعارضِ متنی حل‌شده | ✅ |
| حذفِ تکرار (حالتِ خالیِ دوگانه) | ✅ |
| سازگاریِ مهاجرت‌ها (`makemigrations --check` تمیز؛ `migrate` روی کپی OK) | ✅ |
| عدمِ تغییر در لپ‌تاپ/DB ویندوز؛ بدونِ Push/PR/Merge/Deploy | ✅ |