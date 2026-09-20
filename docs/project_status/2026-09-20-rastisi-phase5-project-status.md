# RastiSi — گزارش رسمی وضعیت پروژه

**تاریخ وضعیت:** ۲۰ سپتامبر ۲۰۲۶  
**حوزه فعلی:** Storefront Builder / Store Appearance / Design Engine — Phase 5  
**وضعیت کلی:** پایدار، checkpoint شده، W5A تا W5C بسته شده‌اند و آماده شروع W5D هستیم.  
**Official Integration Branch:** `feature/phase5-design-expansion`  
**Official Integration HEAD:** `851181c31a0ee224b5cec8a8ae7793eca4a96621`

---

## 1. خلاصه مدیریتی

در بخش طراحی فروشگاه RastiSi، هدف ما ساخت ۵۰ سایت جداگانه یا ۵۰ مجموعه کد مستقل نبود. معماری نهایی بر این مبنا قرار گرفته که **یک Design Engine و یک Store Appearance architecture مشترک** داشته باشیم و روی آن دقیقاً **۵۰ Ready Template** متفاوت قرار بگیرد.

تا این لحظه زیرساخت اصلی طراحی، ۵۰ قالب، Preview/Public renderer، امنیت مسیرهای ویرایش، Bottom Navigation موبایل و تجربه پیش‌نمایش قالب‌ها تکمیل شده‌اند.

وضعیت W5 اکنون چنین است:

| Workstream | وضعیت | نتیجه |
|---|---|---|
| W5A — Canonical Editor Safety | ✅ CLOSED | فقط یک مسیر canonical برای mutation؛ R3 فقط rollback |
| W5B — Mobile Bottom Navigation | ✅ CLOSED | Bottom Navigation وارد Normal R4 Builder شد |
| W5C — Ready Template Preview UX | ✅ CLOSED | Preview داخل Gallery + Desktop/Tablet/Mobile + Merchant/Demo |
| W5D — Merchant Design IA Closure | ⬜ NOT STARTED | مرحله بعد |
| W5E — Merchant Journey Certification | ⬜ NOT STARTED | مرحله نهایی W5 |

بنابراین **هیچ کار نیمه‌تمام یا PR باز از W5C نداریم**.

---

## 2. نقطه رسمی فعلی Git

Repository فعلی R4/Phase 5 روی شاخه زیر قرار دارد:

`feature/phase5-design-expansion`

**Official HEAD فعلی:**

`851181c31a0ee224b5cec8a8ae7793eca4a96621`

آخرین Merge اصلی:

**W5C Merge Commit**

`2943d1247b5a2bfff241b6d644fad957e4fb567b`

و بعد از آن فقط checkpoint evidence ثبت شده است:

**W5C Merge Checkpoint**

`851181c31a0ee224b5cec8a8ae7793eca4a96621`

در آخرین بررسی مستقل، remote branch و این checkpoint دقیقاً با هم منطبق بودند.

بنابراین این SHA باید **مبدأ هر کار جدید W5D** باشد.

---

## 3. معماری نهایی Storefront Design Engine

معماری مورد تأیید ما این است:

**یک Store Appearance / Design Engine**

که روی آن Component Familyهای reusable داریم و ۵۰ Ready Template صرفاً DNA/Recipeهای versioned هستند.

یعنی:

**Ready Template ≠ یک سایت جداگانه**

بلکه چیزی شبیه:

`Template DNA → Header + Hero + Layout + Product View + Card + Footer + Bottom Nav + Palette + Typography + ...`

است.

اعمال یک Ready Template، اطلاعات تجاری فروشگاه مانند Product/Catalog را کپی یا جایگزین نمی‌کند. Template فقط Draft appearance/layout را تغییر می‌دهد.

چرخه canonical سیستم نیز همچنان:

**Draft → Preview → Publish → Public**

است.

فقط Publish اجازه دارد سایت عمومی را تغییر دهد.

---

## 4. اصل مهم «یک منبع حقیقت»

یکی از ریسک‌های اصلی که در پروژه دائماً کنترل کرده‌ایم، ایجاد معماری‌های موازی بوده است.

بنابراین اکنون عمداً این اصول داریم:

- **یک Builder architecture**
- **یک Draft lifecycle**
- **یک Preview/Public rendering architecture**
- **یک Ready Template Registry**
- **یک Store Appearance contract**
- **یک canonical mutation architecture**

و نه:

- ۵۰ renderer جدا
- ۵۰ Builder جدا
- Preview renderer دوم
- Mobile renderer دوم
- mutation pipeline جدا برای هر component
- Template HTML/CSS مستقل برای هر قالب

این اصل تا پایان W5C حفظ شده و آخرین audit نیز Architectural Duplication جدید را **0** گزارش می‌کند.

---

## 5. وضعیت ۵۰ Ready Template

۵۰ Ready Template رسمی در سیستم وجود دارد.

همه آنها از یک engine استفاده می‌کنند ولی از نظر ترکیب اجزای طراحی تفاوت دارند.

در W4C این مجموعه تحت Browser Certification بسیار گسترده قرار گرفت.

Certification شامل:

- ۵۰ Template
- صفحات Base
- Desktop / Tablet / Mobile
- Theme coverage
- visual distinctness
- console/page/request error checks

بود.

مجموع matrix تأییدشده:

**704 / 704 PASS**

همچنین:

**50 / 50 rendered visual distinctness PASS**

و gallery screenshots نیز برای ۵۰ قالب تولید و بررسی شد.

این بدان معنا نیست که دیگر هیچ polish بصری در آینده انجام نمی‌شود؛ معنایش این است که **زیرساخت و differentiation مورد نیاز ۵۰ قالب اثبات شده است.**

---

## 6. W5A — Canonical Editor Safety

### وضعیت

**✅ CLOSED**

W5A یکی از مهم‌ترین بخش‌های معماری W5 بود.

هدف آن جلوگیری از این بود که R3 و R4 همزمان بتوانند Draft یک Store را بدون یک concurrency contract مشترک تغییر دهند.

اکنون تصمیم معماری نهایی این است:

**R4 = canonical/default editor**

R3 فقط زمانی writable است که Store صریحاً به حالت rollback قدیمی pin شده باشد.

برای Store معمولی R4، legacy Class-A mutation routeها fail closed هستند.

نتیجه inventory نهایی:

**32 Class-A route**

همگی:

**32 / 32 GUARDED**

دو عملیات legacy حساس دیگر:

- Restore Version
- Apply Industry Layout

به canonical R4-safe concurrency boundary منتقل شدند.

بنابراین:

**Class C = 2 / 2 converged**

و مجموع functionهای legacy-guarded:

**34**

### امنیت concurrent mutation در W5A

Restore و Industry Apply اکنون فقط revision را بررسی نمی‌کنند.

Contract جدید:

**Draft ID + Edit Revision**

است.

بنابراین مشکل ABA نیز پوشش داده شد.

مثلاً اگر:

Draft A revision 0

جای خود را به:

Draft B revision 0

بدهد، درخواست stale متعلق به Draft A دیگر به اشتباه روی Draft B پذیرفته نمی‌شود.

Rate limiting نیز به response کنترل‌شده **429** تبدیل شد.

### Certification W5A

Focused final:

**60 / 60 PASS**

Browser QA:

**14 / 14 PASS**

Full suite آن مرحله:

**3478 tests**

با:

- 30 historical failures
- 2 historical errors
- 1 skip
- 0 new failure/error identities
- 0 changed historical reasons

W5A سپس Merge و checkpoint شد.

---

## 7. W5B — Mobile Bottom Navigation R4 Parity

### وضعیت

**✅ CLOSED**

Bottom Navigation از قبل در engine و renderer وجود داشت، اما merchant در Normal R4 Builder نمی‌توانست مستقیماً آن را انتخاب کند.

در W5B هیچ سیستم جدیدی ساخته نشد.

همان chain موجود استفاده شد:

`GLOBAL_MOBILE_NAV_REGION`

→ R4 Global Design

→ existing `footer.update`

→ existing validation

→ existing appearance authority

→ typed `bottom_nav`

→ existing Preview/Public renderer

### نتیجه W5B

تعداد Bottom Navigation variantهای canonical:

**9**

شامل گزینه‌هایی مانند:

- `hidden`
- `four_item`
- `five_item`
- `raised_cart`
- `floating_dock`
- `glass_dock`

و variantهای دیگر ثبت‌شده در registry.

در W5B:

**New Variant = 0**  
**New Renderer = 0**  
**New Mutation Type = 0**  
**Migration = 0**

### یک نکته مهم QA که پیدا کردیم

در اولین Browser QA، اسکریپت ادعا می‌کرد Mobile را تست کرده اما Playwright واقعاً در viewport موبایل نبود.

در Independent Review این را پیدا کردیم.

QA دوباره اصلاح شد تا واقعاً در:

**390px mobile viewport**

اجرا شود.

نتیجه واقعی:

Draft Preview Bottom Nav:

`display: block`

و bounding box واقعی:

`370 × 64`

بعد از Publish نیز Public storefront در viewport موبایل همین رفتار را نشان داد.

Hidden variant نیز واقعاً هیچ Bottom Navigation تولید نکرد.

Browser QA نهایی:

**23 / 23 PASS**

### Regression W5B

Full suite:

**3502 tests**

با همان:

- 30 historical failures
- 2 historical errors
- 1 skip
- 0 new identities

Post-Merge focused:

**24 / 24 PASS**

W5B سپس Merge و checkpoint شد.

---

## 8. W5C — Ready Template Preview UX

### وضعیت

**✅ CLOSED**

W5C تجربه Merchant هنگام انتخاب یکی از ۵۰ Ready Template را ارتقا داد.

قبل از W5C، merchant برای Preview مجبور بود لینک‌ها را در tab جدا باز کند.

اکنون:

**Gallery → Preview داخل همان صفحه**

داریم.

Preview دارای:

**Merchant Data / Demo Data**

و:

**Desktop / Tablet / Mobile**

است.

همه اینها با **همان یک iframe** انجام می‌شوند.

هیچ Preview renderer یا route دوم ساخته نشده است.

---

## 9. قرارداد Preview در W5C

Canonical Preview route همچنان فقط یکی است.

اکنون این endpoint واقعاً:

**GET-only**

است.

یعنی:

Merchant POST → **405**

Demo POST → **405**

Preview دیگر در هیچ modeای Draft ایجاد نمی‌کند.

هر دو mode از:

`layout_service.get_existing_draft()`

استفاده می‌کنند.

اگر Draft وجود نداشته باشد:

**fail closed**

می‌شود.

نه اینکه Preview به‌صورت مخفی persistence ایجاد کند.

---

## 10. Demo Store مشکل مهمی که در W5C پیدا شد

در Independent Review متوجه شدیم پس از Publish کردن Golden Reference Demo Store، Draft تازه‌ای باقی نمی‌ماند.

این باعث می‌شد وقتی Preview را read-only کردیم، Demo Preview بعد از seed شدن محیط 404 بدهد.

راه‌حل درست این نبود که Preview دوباره Draft بسازد.

بلکه seeding command اصلاح شد.

اکنون:

`apply_golden_reference_storefront`

بعد از Publish، از lifecycle service رسمی استفاده کرده و یک Draft تازه از Published state می‌سازد.

بنابراین:

**Seed/Operator action می‌تواند Draft بسازد**

اما:

**Preview GET هرگز Draft نمی‌سازد.**

این تفکیک معماری مهم است.

---

## 11. W5C Preview UX فعلی

داخل Gallery اکنون merchant می‌تواند قالب را باز کند و در همان dialog ببیند.

Device contract:

**Tablet = 768**

**Mobile = 390**

Merchant می‌تواند بین:

**اطلاعات فروشگاه من**

و:

**اطلاعات نمایشی**

سوییچ کند.

همه این تغییرات با **همان iframe** انجام می‌شوند.

Preview:

- Template را Apply نمی‌کند.
- Draft را تغییر نمی‌دهد.
- Revision را تغییر نمی‌دهد.
- History نمی‌سازد.
- Public را تغییر نمی‌دهد.

Apply همچنان action جدا و canonical خود را دارد.

---

## 12. Accessibility W5C

Modal Preview دارای contract دسترس‌پذیری شده است:

- `role="dialog"`
- `aria-modal="true"`
- accessible title
- Focus on open
- Focus restore on close
- Escape close
- Focus trap

همچنین در review متوجه شدیم وقتی focus داخل iframe قرار دارد، Escape توسط parent document دیده نمی‌شود.

برای همین listener روی document داخلی iframe نیز نصب شد.

Browser QA واقعی ثابت کرد:

**Escape داخل iframe → modal close → focus به trigger اصلی برمی‌گردد.**

---

## 13. Browser Certification W5C

Browser QA نهایی:

**28 / 28 PASS**

از جمله:

- 50/50 Ready Template card
- یک iframe
- Merchant Preview
- Demo Preview
- Desktop
- Tablet 768
- Mobile 390
- Template retarget
- Apply control preserved
- Parent Escape
- Iframe Escape
- Focus restore
- keyboard activation
- Draft non-mutation

Merchant Draft قبل و بعد byte-identical باقی ماند.

Demo Draft قبل و بعد نیز byte-identical باقی ماند.

---

## 14. Full Regression نهایی فعلی

آخرین exact-source Full Regression معتبر بعد از W5C:

**3531 tests**

نتیجه:

| مورد | مقدار |
|---|---:|
| کل تست‌ها | 3531 |
| Historical Failures | 30 |
| Historical Errors | 2 |
| Skip | 1 |
| New Failure/Error Identities | **0** |
| Missing Historical Identities | **0** |
| Changed Historical Reasons | **0** |

نکته مهم این است که ما ادعا نمی‌کنیم Full Suite صفر failure دارد.

۳۰ failure و ۲ error قدیمی از قبل وجود داشته‌اند.

معیار ما این بوده که featureهای جدید **هیچ failure/error جدیدی ایجاد نکنند** و identity/reason خطاهای تاریخی تغییر نکند.

این معیار تا W5C حفظ شده است.

---

## 15. Post-Merge W5C

پس از Merge نیز lightweight certification انجام شد.

W5C focused:

**29 / 29 PASS**

Task-2 live Demo Preview:

**20 / 20 PASS**

Django system check:

**PASS**

Migration check:

**0**

Git diff check:

**PASS**

Certified app/test tree نیز در Merge تغییر نکرده است.

---

## 16. چیزی که الان یک Merchant واقعاً دارد

در وضعیت فعلی، merchant دارای این امکانات پایه طراحی است:

- Normal R4 Builder به‌عنوان Editor اصلی
- Ready Template Gallery با تمام ۵۰ قالب
- Preview قبل از Apply
- Preview با اطلاعات خودش یا Demo
- نمایش Desktop/Tablet/Mobile
- Apply به Draft
- Undo/Redo
- History
- Publish
- Global Design controls
- Theme/Palette/Typography
- Mobile Bottom Navigation

در بخش پیشرفته نیز Design Lab همچنان روی همان Store Appearance state کار می‌کند و معماری جدا ندارد.

Design Lab برای قابلیت‌هایی مانند Random Mix، Locks، Compare و Return DNA استفاده می‌شود.

Hero / Product View / Product Card / Badge در حال حاضر عمداً بیشتر در Design Lab باقی مانده‌اند و قرار نیست صرفاً برای پر کردن UI وارد Normal Builder شوند.

---

## 17. اصطلاحات رسمی که باید حفظ کنیم

دو مفهوم نباید دوباره با هم مخلوط شوند:

### Ready Template — قالب آماده

همان مجموعه **۵۰ Template** بزرگ و کامل طراحی فروشگاه است.

### Style Pack — بسته سبک

Registry داخلی کوچک‌تر مربوط به style-token/template appearance قدیمی‌تر است.

نام‌های داخلی بعضی کلاس‌ها و فیلدها ممکن است همچنان `template` داشته باشند، اما در UX merchant نباید این دو مفهوم یکی نشان داده شوند.

این یکی از مواردی است که W5D باید بیشتر تمیز کند.

---

## 18. `layout` و `mega_menu`

دو خانواده typed در architecture وجود دارند که فعلاً deliberately reserved هستند.

`layout`

نباید تبدیل به composition renderer دوم شود. Layout واقعی صفحات از canonical container/page architecture می‌آید.

`mega_menu`

نیز در حال حاضر نباید یک subsystem مستقل جدید پیدا کند. رفتار Mega Menu فعلی عمدتاً توسط Header/navigation architecture کنترل می‌شود.

این دو باید همچنان:

**RESERVED / COMPATIBILITY**

باقی بمانند تا duplication ایجاد نشود.

---

## 19. R3 الان چه وضعیتی دارد؟

R3 حذف نشده است.

ولی دیگر canonical editor نیست.

هدف آن فقط:

**rollback / compatibility**

است.

برای Store عادی R4 فعال است و legacy Class-A write routes مسدود هستند.

این تصمیم مهمی است چون یکی از بزرگ‌ترین ریسک‌های قبلی سیستم این بود که یک Draft بتواند از دو editor architecture متفاوت تغییر کند.

W5A این خطر را بست.

---

## 20. مرحله بعد — W5D

مرحله بعدی:

# W5D — Merchant Design IA Closure

هنوز شروع نشده است.

W5D بیشتر از اینکه یک پروژه backend بزرگ باشد، باید تجربه merchant را منظم و قابل‌فهم کند.

موضوع اصلی آن این است که merchant دقیقاً بفهمد:

- کجا Ready Template انتخاب می‌کند
- کجا طراحی ساده روزمره را تغییر می‌دهد
- چه چیزهایی در Design Lab هستند
- فرق Ready Template و Style Pack چیست
- Global Design کجاست
- History/Restore کجاست
- جریان درست Preview → Apply → Edit → Publish چیست

در این مرحله باید مراقب باشیم UI polish بهانه‌ای برای ایجاد architecture دوم نشود.

---

## 21. مرحله آخر — W5E

بعد از W5D:

# W5E — Merchant Journey Browser Certification

قرار است مسیر واقعی merchant را از ابتدا تا انتها به‌صورت Browser QA بررسی کند.

این مرحله دیگر بیشتر **Certification** است تا feature construction.

یعنی باید ثابت کنیم کاربر واقعی می‌تواند بدون شکستن contractها این چرخه را طی کند:

انتخاب فروشگاه → Gallery → Preview → Apply → Builder → Global Design → تغییر ظاهر → Bottom Nav → Undo/Redo → History → Preview → Publish → Public

همچنین failure pathها، stale-write safety و مرز Draft/Public نیز باید حفظ شوند.

بعد از W5E می‌توانیم W5 را برای closure نهایی بررسی کنیم.

---

## 22. وضعیت ابزار اجرا: Claude Code / Kiro / Codex

Claude Code فعلاً به علت تمام شدن quota/token چند روز قابل استفاده نیست.

این **هیچ مشکلی برای وضعیت repository ایجاد نکرده است**، چون Claude دقیقاً بعد از:

- Merge W5C
- Post-Merge Checkpoint

متوقف شده است.

بنابراین هیچ feature branch نیمه‌کاره‌ای وجود ندارد که لازم باشد نجات دهیم.

Kiro هنوز در انتظار پاسخ/دسترسی است.

تا آن زمان می‌توانیم Codex را برای ادامه W5D/W5E ارزیابی کنیم، اما workflow معماری پروژه نباید تغییر کند:

**Architect / Independent Reviewer → Prompt دقیق → Coding Agent → Tests/Evidence → Independent Review → Repair → Merge Authorization**

Coding Agent ممکن است Claude Code، Kiro یا Codex باشد؛ authority معماری و acceptance criteria ثابت می‌مانند.

---

## 23. مهم‌ترین SHAهای فعلی برای آرشیو

| نقطه | SHA |
|---|---|
| W5A post-merge checkpoint | `e8a0a33841cf1eff289f76588d95491558ba9348` |
| W5B merge | `5e5d0180d1efbd7aec351891e4049df1715b2b50` |
| W5B checkpoint | `3125a3250b1284ba216ac8c125257b7e48aaf0bf` |
| W5C production source | `868e0c0badac13b30f0cb9efdd3e3ed5a1d1e9ea` |
| W5C exact-source regression | `bfcedb96693602f9ff21e7c8c1b105631608a2b5` |
| W5C approved PR head | `97191d2d666d64dc4bd6426956d966a97372d4cb` |
| W5C merge | `2943d1247b5a2bfff241b6d644fad957e4fb567b` |
| **Current official integration HEAD** | **`851181c31a0ee224b5cec8a8ae7793eca4a96621`** |

---

## 24. چیزهایی که نباید در W5D خراب شوند

این‌ها اکنون خطوط قرمز معماری هستند:

1. **R4 canonical editor باقی بماند.**
2. **Draft/Public lifecycle دست نخورد.**
3. **Preview هیچ mutation نکند.**
4. **۵۰ Ready Template همچنان از یک Engine استفاده کنند.**
5. **Ready Template و Style Pack دوباره با هم قاطی نشوند.**
6. **Normal Builder و Design Lab architecture جدا پیدا نکنند.**
7. **Renderer دوم ساخته نشود.**
8. **Bottom Navigation subsystem دوم ساخته نشود.**
9. **R3 دوباره به write surface موازی R4 تبدیل نشود.**
10. **Public فقط با Publish تغییر کند.**

این‌ها باید داخل Prompt هر Coding Agent برای W5D نیز صریحاً تکرار شوند.

---

## 25. ارزیابی وضعیت فعلی پروژه

از دید فنی، الان دیگر در مرحله «ساخت زیرساخت اولیه طراحی فروشگاه» نیستیم.

آن بخش تا حد زیادی انجام شده است.

الان وارد مرحله:

**بستن تجربه Merchant + مرتب‌کردن UX + Certification نهایی**

شده‌ایم.

به زبان ساده:

> موتور ساخته شده، ۵۰ قالب روی آن قرار گرفته، Preview و Publish داریم، امنیت ویرایش تثبیت شده، Bottom Navigation موبایل آمده، Preview قالب‌ها حرفه‌ای‌تر شده؛ حالا باید تجربه استفاده از همه این امکانات را برای صاحب فروشگاه ساده و مرتب کنیم و در پایان کل مسیر را یک‌جا تست کنیم.

---

## 26. وضعیت رسمی برای شروع جلسه بعدی

اگر بعداً یک Chat یا Coding Agent جدید باز کردیم، این عبارت وضعیت صحیح شروع کار است:

> **RastiSi Phase 5 is currently at official integration checkpoint `851181c31a0ee224b5cec8a8ae7793eca4a96621`. W5A, W5B and W5C are merged, independently verified and CLOSED. W5D and W5E have not started. The next authorized workstream is P5-W5D Merchant Design IA Closure. No work may start from an older checkpoint.**

این جمله عملاً **handoff رسمی پروژه در این لحظه** است.

---

## 27. مراحل فوری بعدی

ترتیب کار بعدی باید این باشد:

1. این گزارش در repository تحت `docs/` قرار بگیرد و با یک commit مستقل ثبت شود.
2. شاخه رسمی `feature/phase5-design-expansion` روی لپ‌تاپ با remote به‌صورت `ff-only` sync شود.
3. یک verification محلی انجام شود که HEAD لپ‌تاپ دقیقاً همان HEAD رسمی GitHub باشد.
4. در صورت نیاز یک backup/archive محلی از repository و evidenceها نگهداری شود.
5. سپس Codex به‌عنوان Coding Agent احتمالی برای W5D ارزیابی شود.
6. تا قبل از تعریف Prompt/Acceptance Criteria رسمی W5D، هیچ feature implementation جدیدی شروع نشود.

---

## 28. نتیجه نهایی

تا این لحظه کار گم نشده، چیزی نیمه‌Merge نمانده و توقف Claude Code هیچ ریسکی برای repository ایجاد نکرده است.

**نقطه امن فعلی:**

`851181c31a0ee224b5cec8a8ae7793eca4a96621`

**مرحله بعد:**

`P5-W5D — Merchant Design IA Closure`

و بعد:

`P5-W5E — Merchant Journey Browser Certification`

بعد از W5E باید closure رسمی W5 و تصمیم مرحله بعد پروژه انجام شود.

---

## 29. پیشنهاد مسیر ذخیره در Repository

مسیر پیشنهادی برای این سند:

`docs/project_status/2026-09-20-rastisi-phase5-project-status.md`

Commit پیشنهادی:

`docs(phase5): record official project status after W5C closure`

این commit باید فقط همین سند وضعیت را اضافه کند و هیچ production/test/migration file را تغییر ندهد.
