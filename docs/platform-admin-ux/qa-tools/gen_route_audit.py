import inspect, json, re
from apps.portal import platform_admin_urls as m
before = json.load(open('/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad/ux_before/before-report.json'))
M = {}
for r in before:
    if r['w'] == 1440 and r['status'] == 200: M[r['name']] = r
OV320 = {r['name'] for r in before if r['w'] == 320 and r.get('overflow', 0) > 0}
OLD_NAV = {"home":"مدیریت اصلی","stores":"مدیریت اصلی","users":"مدیریت اصلی","plans":"اشتراک‌ها ▸ (زیرمنو)","features":"اشتراک‌ها ▸ (زیرمنو)","assignment-matrix":"اشتراک‌ها ▸ (زیرمنو)","subscriptions":"اشتراک‌ها ▸ (زیرمنو)","payments":"اشتراک‌ها ▸ (زیرمنو)","billing-zibal-settings":"اشتراک‌ها ▸ (زیرمنو)","sms-providers":"پیامک ▸ (زیرمنو)","sms-templates":"پیامک ▸ (زیرمنو)","sms-messages":"پیامک ▸ (زیرمنو)","notification-catalog":"اعلان‌ها","notification-senders":"اعلان‌ها","notification-delivery":"اعلان‌ها","notification-audit":"اعلان‌ها","industries":"محتوا و زیرساخت","public-site":"محتوا و زیرساخت","public-photos":"محتوا و زیرساخت","domains":"محتوا و زیرساخت","audit-log":"محتوا و زیرساخت","configuration":"محتوا و زیرساخت"}
NEW_NAV = {}
from apps.portal.platform_admin_nav import NAV
for g in NAV:
    for i in g.items:
        for n in i.matches: NEW_NAV[n] = f"{g.label} ▸ {i.label}"
P = {
 "home":"داشبورد KPIهای زنده و «نیازمند توجه»","login":"ورود مدیر پلتفرم","logout":"خروج (POST)","stores":"فهرست/فیلتر فروشگاه‌ها","store-detail":"جزئیات فروشگاه در تب‌ها (نمای‌کلی/اشتراک/مصرف/دامنه/اعتبار پیامک/یادداشت/حسابرسی)",
 "users":"فهرست مالکان/کاربران","user-detail":"جزئیات کاربر، تعلیق/فعال‌سازی، یادداشت","public-photos":"تصاویر سایت عمومی","public-photo-edit":"بارگذاری تصویر یک جایگاه","public-site":"مرکز متن/رنگ/فونت سایت عمومی + سوییچ طراحی","public-site-edit":"ویرایش یک گروه از متن‌ها","plans":"فهرست پلن‌ها و نسخه‌ها (انتشار/بایگانی)","pricing-content":"متن ردیف‌ها، FAQ، خدمات اختیاری، گزارش شکاف","assignment-matrix":"ماتریس قابلیت×پلن (پیش‌نویس)","plan-migration":"مهاجرت صریح مشترکان بین نسخه‌ها","features":"کاتالوگ قابلیت‌ها","feature-add":"ساخت قابلیت","feature-edit":"مدیریت قابلیت (وضعیت‌ها/قطع اضطراری)","plan-add":"پلن تازه","plan-edit":"ویرایش پیش‌نویس پلن","subscriptions":"اشتراک فروشگاه‌ها","payments":"فاکتورها","payment-invoice-detail":"جزئیات فاکتور","payment-manual-add":"ثبت پرداخت دستی","billing-zibal-settings":"درگاه زیبالِ اشتراک پلتفرم","sms-settings":"تنظیم درگاه پیامک (alias قدیمی)","sms-providers":"شرکت‌های پیامکی + قانون هزینه + تست","sms-templates":"قالب‌های پیامک","sms-template-edit":"ویرایش/تست یک قالب","sms-messages":"گزارش پیامک‌ها","sms-packages":"بسته‌های پیامک","sms-package-add":"بسته‌ی تازه","sms-package-edit":"ویرایش بسته","sms-credits":"اعتبار پیامک فروشگاه‌ها","sms-logs":"redirect قدیمی به sms-messages","notification-catalog":"کاتالوگ رویدادهای اعلان","notification-senders":"هویت فرستنده ایمیل فروشگاه‌ها","notification-delivery":"ارسال‌ها و شکست‌ها","notification-audit":"تاریخچه تغییر اعلان‌ها","notification-platform-template":"ویرایش قالب پیش‌فرض یک رویداد","industries":"قالب‌های صنفی","industry-detail":"جزئیات/اعتبارسنجی قالب صنفی","domains":"دامنه‌ها و وضعیت DNS","audit-log":"گزارش رخدادهای پلتفرم","configuration":"تنظیمات پلتفرم/اینماد/عملیات","inbox-home":"صندوق اعلان (قالبِ مشترک با داشبورد فروشنده؛ داخل همین پوسته)","inbox-summary":"API شمارنده‌ی زنگ (JSON)","inbox-read-all":"علامت‌گذاری همه به‌عنوان خوانده (POST)","inbox-push-subscribe":"ثبت Web Push (POST/API)","inbox-push-unsubscribe":"لغو Web Push (POST/API)","inbox-test":"ارسال اعلان آزمایشی (POST)","inbox-sw":"Service Worker اعلان (JS)","inbox-preferences":"ترجیحات اعلان"}
PROB = {
 "home":"KPI با سایه سنگین؛ اقدام سریع با ایموجی ناهم‌شکل","stores":"فیلتر ۶ کنترلی بدون برچسب (فقط placeholder)؛ ایمیل/آیدی در سلول RTL می‌شکند؛ ۴ ارتفاع دکمه","store-detail":"«تغییر پلن» شناسه‌ی عددی نسخه را از مالک می‌خواست (خطاپذیر)؛ مودال‌ها وابسته به Alpine بدون فوکوس‌تله/Esc؛ عنوان h2",
 "plans":"سه دکمه‌ی ناوبری درون صفحه تکرار منو؛ بایگانی/انتشار بدون تأیید","plan-edit":"فرم یک‌تکه‌ی ۴۰۰+ پیکسلی با ۱۸ فیلد عددی؛ فهرست بلندِ حق‌دسترسی با کم‌رنگ‌کردن (opacity) ردیف‌های غیرفعال","pricing-content":"فقط از دکمه‌ای در صفحه‌ی پلن‌ها در دسترس بود؛ ۴ کار نامرتبط در یک صفحه‌ی بلند (۲۱۳ style درون‌خطی، ۶۴ فیلد عددی)؛ پیام‌ها دوبار رندر می‌شد","assignment-matrix":"پیام‌ها دوبار؛ ۲۴ فیلد عددی با فلش","features":"پیام‌ها دوبار؛ ۶۴ style درون‌خطی","public-photos":"۱۶ تصویر پیش‌فرض (extra01–16.webp) در مخزن نیست ⇒ ۱۶ تصویر شکسته (۴۰۴)؛ ۵۵ style","public-site-edit":"۹۵ style درون‌خطی؛ تأیید با confirm() درون‌خطی","sms-packages":"هیچ پیوندی به آن در پنل وجود نداشت (فقط با تایپِ URL قابل‌دسترس بود)","sms-credits":"در منو نبود (فقط از تبِ «اعتبارِ پیامک» جزئیاتِ فروشگاه)؛ مودال داخل <tr> (HTML نامعتبر)","sms-logs":"فقط redirect؛ در منو نبود","pricing-content-note":"","payments":"دکمه‌ی اصلی بیرون از سرصفحه‌ی استاندارد","sms-settings":"هم‌پوشان با sms-providers (دو فرمِ هم‌موضوع)","configuration":"کارت‌های جدا و دکمه‌ی ذخیره‌ی شناور بدون نوار فرم","login":"<style> محلی و ۱۰ style درون‌خطی","notification-platform-template":"دکمه‌ی «پیش‌نمایش» (htmx) کار نمی‌کرد: htmx در پوسته بارگذاری نمی‌شد؛ onclick درون‌خطی؛ ۱۴ style","domains":"«اصلی‌کردن» بدون تأیید","notification-audit":"فهرست متنی بدون ساختار","industry-detail":"عنوان h2؛ تأیید غیرفعال‌سازی ندارد"}
RISK = {
 "store-detail":"تغییر پلن با شناسه‌ی نادرست ⇒ خطای سرور/پلن اشتباه","pricing-content":"فرمِ ذخیره پس از POST تبِ فعلی را از دست می‌داد","plan-edit":"هر ذخیره یک پیش‌نویس اضافه می‌ساخت (قبلاً اصلاح شده در PR #41)","sms-credits":"HTML نامعتبر ⇒ رفتار مرورگرها متفاوت","notification-platform-template":"عملکرد تبلیغ‌شده (پیش‌نمایش) غیرفعال بود","public-photos":"تصویر شکسته ⇒ مالک نمی‌داند پیش‌فرض چیست"}
POST = re.compile(r"(suspend|activate|extend|set-trial|end-trial|support-login|add-note|archive|publish|cancel|resume|adjust|check|set-primary|reset|switch|toggle|test|preview|logout|verify|refund|action|receipt)$")
rows = []
for p in m.urlpatterns:
    name = p.name; route = str(p.pattern); fn = p.callback
    try: src = inspect.getsource(fn)
    except Exception: src = ''
    tm = re.findall(r'portal/platform_admin/([\w]+\.html)', src)
    tpl = tm[0] if tm else ('— (redirect/POST)' if POST.search(name or '') or 'redirect' in src else '—')
    mod = fn.__module__.split('.')[-1]
    met = M.get(name)
    metr = ''
    if met:
        bits = []
        if met.get('inlineStyle', 0) > 3: bits.append(f"{met['inlineStyle']} style درون‌خطی")
        if met.get('numInputs'): bits.append(f"{met['numInputs']} فیلد عددی با فلش")
        hs = sorted((met.get('btnHeights') or {}).keys(), key=int)
        if len(hs) > 1: bits.append(f"{len(hs)} ارتفاع دکمه ({'/'.join(hs)}px)")
        metr = '؛ '.join(bits)
    if name in OV320: metr = (metr + '؛ ' if metr else '') + 'overflow افقی در ۳۲۰px'
    prob = '؛ '.join(x for x in [PROB.get(name, ''), metr] if x) or ('اقدام POST — بدون صفحه' if (not met and POST.search(name or '')) else '—')
    old = OLD_NAV.get(name) or ('— (API/POST)' if (name or '').startswith('inbox-') and name not in ('inbox-home','inbox-preferences') else None) or ('— (از منو در دسترس نبود)' if met and name in ('sms-packages','sms-credits','sms-logs','pricing-content','sms-settings','payment-manual-add') else ('زیرصفحه (از صفحه‌ی والد)' if met else '—'))
    new = NEW_NAV.get(name, '—')
    isget = bool(met) or name in ('login',)
    action = 'keep'
    if name in ('pricing-content',): action = 'split (تب‌ها، همان URL)'
    elif name in ('sms-settings',): action = 'merge → sms-providers (alias حفظ شد)'
    elif name in ('sms-logs',): action = 'merge → sms-messages (redirect حفظ شد)'
    elif (name or '').startswith('inbox-') and name not in ('inbox-home','inbox-preferences'): action = 'keep'
    elif met or name == 'login': action = 'redesign'
    elif POST.search(name or ''): action = 'keep (+تأیید در رابط)' if any(k in name for k in ('suspend','archive','cancel','publish','reset','switch','set-primary','toggle','end-trial','change-plan','adjust')) else 'keep'
    rows.append((f"/{route}", name or '—', PURPOSE_OR(P, name), f"{mod}.{fn.__name__} / {tpl}", old, new, prob, RISK.get(name, '—'), action))
def PURPOSE_OR(P, n): return P.get(n, 'اقدام POST' if POST.search(n or '') else '—')
out = ["# ممیزیِ کاملِ مسیرها و UXِ پنلِ مالکِ پلتفرم — ۲۰۲۶-۱۱-۰۵", "", "پایه: `260c5555` (شاخه‌ی `pricing/dynamic-plans-20261105`). روش: خواندنِ `platform_admin_urls.py`، viewها، قالب‌ها، CSS؛ و **خزشِ مرورگر** (Chromium، ۵ عرض، داده‌ی QAِ واقعی در PostgreSQL موقت) پیش از هر تغییر. ستونِ «مشکلاتِ UX» از اندازه‌گیریِ همان خزشِ «قبل» می‌آید (style درون‌خطی، فیلدِ عددیِ دارایِ فلش، ارتفاعِ دکمه‌ها، overflowِ ۳۲۰px).", "", f"**{len(rows)} مسیر** در `platform_admin_urls` ({sum(1 for r in rows if r[6]!='اقدام POST — بدون صفحه' and not r[8].startswith('keep'))} صفحه‌ی GET + بقیه اقدام‌های POST).", "",
 "| # | URL | نام | هدفِ صفحه | View / قالب | جایگاهِ قبلی در ناوبری | جایگاهِ جدید | مشکلاتِ UX | ریسکِ کارکردی | تصمیم |", "|---|---|---|---|---|---|---|---|---|---|"]
for i, r in enumerate(rows, 1):
    out.append(f"| {i} | `{r[0]}` | `{r[1]}` | {r[2]} | `{r[3]}` | {r[4]} | {r[5]} | {r[6]} | {r[7]} | {r[8]} |")
open('/home/user/rastisi-uxadmin/docs/platform-admin-ux/ROUTE_AND_UX_AUDIT_20261105.md', 'w').write('\n'.join(out) + '\n')
print(len(rows))
