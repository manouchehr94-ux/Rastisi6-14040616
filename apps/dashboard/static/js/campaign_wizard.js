/* رابطِ ساده‌ی ساختِ کمپین/مناسبت (طرحِ تأییدشده‌ی v2).
   این فایل فقط رابط است: فیلدهایِ واقعیِ فرم (name=…) همان‌هایی‌اند که سرور (CampaignForm) می‌خوانَد
   و اعتبارسنجیِ نهایی همیشه سمتِ سرور انجام می‌شود. متنِ پیامک هیچ‌جا در این فرم ویرایش نمی‌شود؛
   پیش‌نمایشِ آن از سرور (همان قالبِ پلتفرم و همان رندرِ ارسالِ واقعی) گرفته و فقط‌خواندنی نمایش داده می‌شود. */
(function () {
  'use strict';
  var root = document.getElementById('cw-root');
  var form = document.getElementById('cw-form');
  if (!root || !form) return;
  var cfg = JSON.parse(document.getElementById('cw-config').textContent);
  var MODE = cfg.mode;
  var state = { step: 1, prevAudience: 'all' };
  var amountMemory = {};

  function $(s, c) { return (c || root).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || root).querySelectorAll(s)); }
  function field(name) { return form.querySelector('[name="' + name + '"]'); }
  function val(name) { var e = field(name); return e ? String(e.value || '').trim() : ''; }
  function setVal(name, v) { var e = field(name); if (e) e.value = v; }
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(n) { return String(n).replace(/[0-9]/g, function (c) { return FA[+c]; }); }
  function digits(s) {
    return String(s || '').replace(/[۰-۹]/g, function (c) { return String(FA.indexOf(c)); })
      .replace(/[٠-٩]/g, function (c) { return String('٠١٢٣٤٥٦٧٨٩'.indexOf(c)); }).replace(/[\s,٬،]/g, '');
  }
  function num(name, fb) { var raw = digits(val(name)); return raw === '' ? (fb === undefined ? 0 : fb) : Number(raw); }
  function fmt(n) { var x = Number(digits(n)); return isFinite(x) ? fa(x.toLocaleString('en-US')).replace(/,/g, '٬') : String(n); }
  function isDate(s) { return /^\d{4}\/\d{1,2}\/\d{1,2}$/.test(digits(s).replace(/-/g, '/')) || /^\d{4}-\d{1,2}-\d{1,2}$/.test(digits(s)); }

  var OCC = {
    birthday: 'تولد هر مشتری، سالی یک بار', registration_anniversary: 'سالگرد ثبت‌نام هر مشتری',
    first_purchase_anniversary: 'سالگرد اولین خرید هر مشتری', reactivation: 'بازگشت مشتری غیرفعال',
    order_milestone: 'رسیدن به تعداد خرید مشخص', spending_milestone: 'رسیدن به مبلغ خرید مشخص',
    holiday: 'روز ویژه سال', custom_date: 'تاریخ اختصاصی فروشگاه'
  };
  var AUD = {
    all: 'همه مشتری‌های فروشگاه', 'new': 'مشتری‌هایی که در ۳۰ روز اخیر ثبت‌نام کرده‌اند',
    loyal: 'مشتری‌هایی با حداقل ۳ سفارش پرداخت‌شده', dormant: 'مشتری‌هایی که ۹۰ روز است خرید نکرده‌اند',
    custom: 'قواعد سفارشی (شرط‌های ترکیبی)'
  };
  var EXTRA_WORD = { city: 'شهر', category: 'دسته', tag: 'برچسب', segment: 'گروه' };
  var MORE_OCC = ['order_milestone', 'spending_milestone', 'holiday', 'custom_date'];
  var NO_OFFSET = ['reactivation', 'order_milestone', 'spending_milestone'];
  var PARAM_OCC = ['reactivation', 'order_milestone', 'spending_milestone', 'holiday', 'custom_date'];

  function toast(msg) {
    var t = $('#cw-toast'); t.textContent = msg; t.classList.add('cw-show');
    clearTimeout(window.__cwToast); window.__cwToast = setTimeout(function () { t.classList.remove('cw-show'); }, 4200);
  }

  // ------------------------------------------------------------------ وضعیتِ فعلی
  function rewardChoice() { return val('reward_type') === 'none' ? 'none' : (val('coupon_type') || 'percent'); }
  function checkedLabels(name) {
    return $$('input[name="' + name + '"]:checked', form).filter(function (e) { return !e.disabled; })
      .map(function (e) { return e.parentNode.textContent.trim(); });
  }
  function audienceText() {
    var kind = val('audience_kind') || 'all', base = AUD[kind] || AUD.all;
    var extra = val('audience_extra_kind');
    if (kind !== 'custom' && extra) {
      var picked = checkedLabels('audience_extra_values');
      if (picked.length) base += '، فقط ' + EXTRA_WORD[extra] + ': ' + picked.join('، ');
    }
    return base;
  }
  function occasionText() {
    var o = val('occasion_kind');
    if (o === 'reactivation') return 'مشتری‌هایی که ' + fmt(val('occ_days') || 90) + ' روز خرید نکرده‌اند';
    if (o === 'order_milestone') return 'بعد از خرید شماره ' + fmt(val('occ_n') || 3);
    if (o === 'spending_milestone') return 'پس از مجموع خرید ' + fmt(val('occ_amount') || 5000000) + ' تومان';
    if (o === 'holiday') { var m = field('occ_month'); return 'هر سال در ' + fa(num('occ_day', 1)) + ' ' + (m && m.selectedOptions[0] ? m.selectedOptions[0].textContent : ''); }
    if (o === 'custom_date') return 'در تاریخ ' + (val('occ_date') || 'تعیین‌نشده');
    return OCC[o] || 'مناسبت انتخاب نشده';
  }
  function rewardText() {
    var r = rewardChoice();
    if (r === 'none') return 'بدون کد تخفیف؛ فقط پیام تبریک';
    if (r === 'free_ship') return 'ارسال رایگان';
    if (r === 'fixed') return fmt(num('coupon_value', 0)) + ' تومان تخفیف';
    return fa(num('coupon_value', 0)) + '٪ تخفیف';
  }
  function fullReward() {
    if (rewardChoice() === 'none') return rewardText();
    var sel = field('code_valid_days'), days = sel && sel.value ? fa(sel.value) + ' روز' : 'طبق تاریخ انقضای ثابت';
    var p = (field('personalized') && field('personalized').checked) ? 'کد اختصاصی' : 'کد مشترک';
    var out = rewardText() + '، ' + p + ' با اعتبار ' + days;
    if (num('coupon_min_order') > 0) out += '، حداقل خرید ' + fmt(num('coupon_min_order')) + ' تومان';
    if (num('coupon_max_discount') > 0 && rewardChoice() === 'percent') out += '، تا سقف ' + fmt(num('coupon_max_discount')) + ' تومان';
    return out;
  }
  function timeText() {
    if (MODE === 'occasion') {
      if (NO_OFFSET.indexOf(val('occasion_kind')) >= 0) return 'خودکار؛ به‌محض برقرارشدن شرط مناسبت';
      var o = Number(val('occasion_offset_days') || 0);
      if (o === 0) return 'خودکار؛ در روز مناسبت';
      return 'خودکار؛ ' + fa(Math.abs(o)) + (o < 0 ? ' روز پیش از مناسبت' : ' روز پس از مناسبت');
    }
    var t = val('trigger_type');
    if (t === 'event') return 'پس از هر خرید موفق، برای مشتری واجد شرایط';
    if (t === 'scheduled') return 'شروع زمان‌بندی‌شده از ' + (val('active_from') || 'تاریخ تعیین‌نشده');
    return 'اجرای دستی، پس از بررسی و فعال‌سازی';
  }
  function notifyText() {
    var a = [];
    if (rewardChoice() !== 'none') a.push('نمایش کد در حساب مشتری');
    if (field('channels') && $('#cw-notify-sms').checked) a.push('پیامک با متن آماده راستی‌سی، در صورت رضایت و اتصال سرویس');
    if ($('#cw-notify-email').checked) a.push('ایمیل در صورت رضایت و اتصال سرویس');
    return a.length ? a.join(' + ') : 'بدون پیام ارسالی';
  }
  function renderSummary() {
    $('#cw-sum-hero').textContent = (MODE === 'occasion' ? '🎂 ' : '🎯 ') + (val('name') || (MODE === 'occasion' ? 'هدیه جدید' : 'کمپین جدید'));
    $('#cw-sum-audience').textContent = MODE === 'occasion' ? occasionText() : audienceText();
    $('#cw-sum-reward').textContent = fullReward();
    $('#cw-sum-time').textContent = timeText();
    $('#cw-sum-notify').textContent = notifyText();
  }

  // ------------------------------------------------------------------ نمایشِ شرطیِ بخش‌ها
  function applyVisibility() {
    $$('[data-show-field]').forEach(function (el) {
      var want = el.getAttribute('data-show-values').split(',');
      var hide = want.indexOf(val(el.getAttribute('data-show-field'))) < 0;
      el.classList.toggle('cw-hidden', hide);
      if (el.hasAttribute('data-disable-hidden')) $$('input,select,textarea', el).forEach(function (i) { i.disabled = hide; });
    });
    if (MODE === 'occasion') {
      var o = val('occasion_kind');
      if (NO_OFFSET.indexOf(o) >= 0 && val('occasion_offset_days') !== '0') setVal('occasion_offset_days', '0');
      $('#cw-occ-params').classList.toggle('cw-hidden', PARAM_OCC.indexOf(o) < 0);
      if (MORE_OCC.indexOf(o) >= 0) setMoreOcc(true);
    }
    var r = rewardChoice(), none = r === 'none', free = r === 'free_ship';
    $('#cw-reward-details').classList.toggle('cw-hidden', none);
    $('#cw-advanced-reward').classList.toggle('cw-hidden', none);
    $('#cw-amount-block').classList.toggle('cw-hidden', free || none);
    $('#cw-max-discount-block').classList.toggle('cw-hidden', r !== 'percent');
    $('#cw-amount-label').textContent = r === 'fixed' ? 'چه مبلغی تخفیف بدهیم؟ (تومان)' : 'چند درصد تخفیف بدهیم؟';
    $('#cw-amount-unit').textContent = r === 'fixed' ? 'تومان' : 'درصد';
    $('#cw-account-help').textContent = none ? 'این پیشنهاد کد تخفیف ندارد؛ فقط پیام تبریک ارسال می‌شود.' : 'در صورت صدور پاداش، کد در حساب مشتری قرار می‌گیرد.';
    if (MODE === 'campaign') $('#cw-scheduled-box').classList.toggle('cw-hidden', val('trigger_type') !== 'scheduled');
  }
  function setMoreOcc(open) {
    var box = $('#cw-more-occ'), btn = $('#cw-more-occ-btn'); if (!box) return;
    box.classList.toggle('cw-hidden', !open);
    btn.textContent = open ? '− بستن مناسبت‌های دیگر' : '+ دیدن مناسبت‌های دیگر';
    btn.setAttribute('aria-expanded', String(open));
  }
  function setActive(el, on) { el.classList.toggle('cw-active', on); el.setAttribute('aria-pressed', String(on)); }
  function syncChoices() {
    $$('[data-field]').forEach(function (b) { setActive(b, val(b.getAttribute('data-field')) === b.getAttribute('data-value')); });
    $$('[data-reward]').forEach(function (b) { setActive(b, rewardChoice() === b.getAttribute('data-reward')); });
    $$('[data-offset]').forEach(function (b) { setActive(b, String(val('occasion_offset_days') || 0) === b.getAttribute('data-offset')); });
    $$('[data-timing]').forEach(function (b) { setActive(b, val('trigger_type') === b.getAttribute('data-timing')); });
    var custom = $('#cw-use-custom'); if (custom) custom.checked = val('audience_kind') === 'custom';
  }
  function refresh() { applyVisibility(); syncChoices(); renderSummary(); schedulePreview(); }

  // ------------------------------------------------------------------ اعتبارسنجیِ سمتِ کاربر (ملایم؛ سرور مرجعِ نهایی است)
  function fail(msg, name) {
    toast(msg); var e = typeof name === 'string' ? field(name) : name;
    if (e) { e.classList.add('cw-invalid'); try { e.focus(); } catch (x) { /* ignore */ } }
    return false;
  }
  function clearInvalid() { $$('.cw-invalid').forEach(function (e) { e.classList.remove('cw-invalid'); }); $$('.cw-error').forEach(function (e) { e.classList.remove('cw-show'); }); }
  function validate1() {
    clearInvalid();
    if (!val('name')) { $('#cw-name-error').classList.add('cw-show'); return fail('یک نام کوتاه برای پیشنهاد وارد کن.', 'name'); }
    if (MODE === 'occasion') {
      var o = val('occasion_kind');
      if (!o) return fail('مناسبت را انتخاب کن.');
      var fld = { reactivation: 'occ_days', order_milestone: 'occ_n', spending_milestone: 'occ_amount', holiday: 'occ_day' }[o];
      if (fld && !(num(fld, 0) >= 1)) return fail('لطفاً مقدار مناسب برای این مناسبت وارد کن.', fld);
      if (o === 'holiday' && num('occ_day') > 31) return fail('روز ماه باید بین ۱ تا ۳۱ باشد.', 'occ_day');
      if (o === 'custom_date' && !isDate(val('occ_date'))) return fail('تاریخ شمسی را مانند ۱۴۰۵/۰۸/۱۵ وارد کن.', 'occ_date');
    } else if (val('audience_extra_kind') && val('audience_kind') !== 'custom' && !checkedLabels('audience_extra_values').length) {
      return fail('برای «مخاطب خاص» حداقل یک مورد را انتخاب کن.', 'audience_extra_kind');
    }
    return true;
  }
  function validate2() {
    clearInvalid();
    var r = rewardChoice();
    if (r === 'percent') { var n = num('coupon_value', NaN); if (!(n >= 1 && n <= 100)) { $('#cw-amount-error').textContent = 'درصد تخفیف باید بین ۱ تا ۱۰۰ باشد.'; $('#cw-amount-error').classList.add('cw-show'); return fail('درصد تخفیف باید بین ۱ تا ۱۰۰ باشد.', 'coupon_value'); } }
    if (r === 'fixed') { var m = num('coupon_value', NaN); if (!(m >= 1)) { $('#cw-amount-error').textContent = 'مبلغ تخفیف باید بزرگ‌تر از صفر باشد.'; $('#cw-amount-error').classList.add('cw-show'); return fail('مبلغ تخفیف باید بزرگ‌تر از صفر باشد.', 'coupon_value'); } }
    if (r !== 'none' && !val('code_valid_days') && !val('code_expires_at')) { return fail('مدتِ اعتبارِ کد را انتخاب کن.', 'code_valid_days'); }
    if (r !== 'none') {
      var bad = ['coupon_min_order', 'coupon_max_discount', 'max_issuances'].filter(function (id) { return val(id) !== '' && num(id, -1) < (id === 'coupon_min_order' ? 0 : 1); });
      if (bad.length) return fail('تنظیمات پیشرفته باید عدد صحیح و مثبت باشند.', bad[0]);
    }
    return true;
  }
  function validate3() {
    clearInvalid();
    if (MODE === 'campaign' && val('trigger_type') === 'scheduled' && !isDate(val('active_from'))) return fail('تاریخ شروع را مانند ۱۴۰۵/۰۸/۱۵ وارد کن.', 'active_from');
    return true;
  }
  var validators = { 1: validate1, 2: validate2, 3: validate3 };

  // ------------------------------------------------------------------ مراحل
  function go(n) {
    state.step = n;
    [1, 2, 3].forEach(function (i) { $('#cw-step' + i).classList.toggle('cw-hidden', i !== n); });
    $$('.cw-step-pill').forEach(function (b, i) {
      var k = i + 1; b.classList.toggle('cw-current', k === n); b.classList.toggle('cw-done', k < n);
      b.setAttribute('aria-current', k === n ? 'step' : 'false'); b.querySelector('.cw-num').textContent = k < n ? '✓' : fa(k);
    });
    if (window.innerWidth < 801) window.scrollTo({ top: 0, behavior: 'smooth' });
    renderSummary(); if (n === 3) loadPreview();
  }
  function goChecked(n) {
    for (var i = 1; i < n; i++) { if (!validators[i]()) { go(i); validators[i](); return; } }
    go(n);
  }
  $$('[data-next]').forEach(function (b) { b.addEventListener('click', function () { goChecked(Number(b.getAttribute('data-next'))); }); });
  $$('[data-go]').forEach(function (b) { b.addEventListener('click', function () { var n = Number(b.getAttribute('data-go')); if (n < state.step) go(n); else goChecked(n); }); });

  // ------------------------------------------------------------------ انتخاب‌ها
  $$('[data-field]').forEach(function (b) {
    b.addEventListener('click', function () {
      var name = b.getAttribute('data-field'), v = b.getAttribute('data-value');
      if (name === 'audience_kind' && val('audience_kind') !== 'custom') state.prevAudience = val('audience_kind') || 'all';
      setVal(name, v); refresh();
    });
  });
  $$('[data-reward]').forEach(function (b) {
    b.addEventListener('click', function () {
      var prev = rewardChoice(), v = b.getAttribute('data-reward');
      // مقدارِ هر نوع جداگانه به خاطر سپرده می‌شود (۱۵ «درصد» نباید به ۱۵ «تومان» تبدیل شود)
      if (prev === 'percent' || prev === 'fixed') amountMemory[prev] = val('coupon_value');
      if (v === 'none') setVal('reward_type', 'none');
      else { setVal('reward_type', 'coupon'); setVal('coupon_type', v); }
      if (prev !== v && (v === 'percent' || v === 'fixed')) setVal('coupon_value', amountMemory[v] || (v === 'fixed' ? '100000' : '15'));
      $('#cw-amount-error').classList.remove('cw-show'); refresh();
    });
  });
  $$('[data-offset]').forEach(function (b) { b.addEventListener('click', function () { setVal('occasion_offset_days', b.getAttribute('data-offset')); refresh(); }); });
  $$('[data-timing]').forEach(function (b) {
    b.addEventListener('click', function () {
      var was = val('trigger_type'), v = b.getAttribute('data-timing');
      setVal('trigger_type', v);
      if (was === 'scheduled' && v !== 'scheduled') setVal('active_from', '');
      refresh();
    });
  });
  var moreBtn = $('#cw-more-occ-btn');
  if (moreBtn) moreBtn.addEventListener('click', function () { setMoreOcc($('#cw-more-occ').classList.contains('cw-hidden')); });
  var useCustom = $('#cw-use-custom');
  if (useCustom) useCustom.addEventListener('change', function () {
    if (useCustom.checked) { if (val('audience_kind') !== 'custom') state.prevAudience = val('audience_kind') || 'all'; setVal('audience_kind', 'custom'); }
    else setVal('audience_kind', state.prevAudience && state.prevAudience !== 'custom' ? state.prevAudience : 'all');
    refresh();
  });
  var extraSel = field('audience_extra_kind');
  if (extraSel) extraSel.addEventListener('change', refresh);
  form.addEventListener('input', function () { refresh(); });
  form.addEventListener('change', function () { refresh(); });

  // ------------------------------------------------------------------ پیش‌نمایشِ فقط‌خواندنیِ پیامک (از سرور)
  var previewTimer = null, previewSeq = 0;
  function schedulePreview() { if (state.step === 3) { clearTimeout(previewTimer); previewTimer = setTimeout(loadPreview, 350); } }
  function renderPreview(data) {
    var on = $('#cw-notify-sms').checked, bubble = $('#cw-sms-bubble');
    bubble.replaceChildren();
    (data.parts || []).forEach(function (p) {
      if (p.variable) { var sp = document.createElement('span'); sp.className = 'cw-var'; sp.textContent = p.text; bubble.appendChild(sp); }
      else bubble.appendChild(document.createTextNode(p.text));
    });
    $('#cw-sms-template-name').textContent = 'قالب آماده راستی‌سی: ' + data.label;
    var vars = $('#cw-sms-vars'); vars.replaceChildren();
    var lead = document.createElement('span'); lead.textContent = 'به‌صورت خودکار پر می‌شود:'; vars.appendChild(lead);
    (data.variables || []).forEach(function (v) { var c = document.createElement('span'); c.className = 'cw-chip-tag'; c.textContent = v; vars.appendChild(c); });
    $('#cw-sms-preview').classList.toggle('cw-is-off', !on);
    var st = $('#cw-sms-state'); st.replaceChildren();
    var note;
    if (!on) { st.className = 'cw-sms-state cw-off'; note = 'ارسال پیامک خاموش است؛ برای ارسال، کلید «ارسال پیامک» را روشن کن.'; }
    else if (!data.template_active) { st.className = 'cw-sms-state cw-off'; note = 'ارسال این نوع پیامک فعلاً از طرف راستی‌سی غیرفعال است.'; }
    else if (!data.store_sms_enabled) {
      st.className = 'cw-sms-state cw-off'; note = 'ارسال پیامک روشن است، اما پیامک فروشگاه هنوز فعال نشده است. ';
      var a = document.createElement('a'); a.href = cfg.smsSettingsUrl; a.textContent = 'فعال‌سازی پیامک فروشگاه'; st.appendChild(document.createTextNode(note)); st.appendChild(a); return;
    } else { st.className = 'cw-sms-state cw-on'; note = '✓ ارسال پیامک روشن است؛ فقط به مشتریان دارای رضایت و بدون ارسال تکراری فرستاده می‌شود.'; }
    st.textContent = note;
  }
  function loadPreview() {
    var seq = ++previewSeq, body = new URLSearchParams(new FormData(form));
    return fetch(cfg.previewUrl, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': (field('csrfmiddlewaretoken') || {}).value || '', 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { if (!r.ok) throw new Error('status ' + r.status); return r.json(); })
      .then(function (data) { if (seq === previewSeq) renderPreview(data); })
      .catch(function () { if (seq === previewSeq) { $('#cw-sms-bubble').textContent = 'پیش‌نمایش پیامک در حال حاضر در دسترس نیست؛ ذخیره‌ی پیش‌نویس تحت‌تأثیر قرار نمی‌گیرد.'; } });
  }

  // ------------------------------------------------------------------ مرور نهایی و ارسال
  function showReview() {
    for (var i = 1; i <= 3; i++) { if (!validators[i]()) { go(i); validators[i](); return; } }
    renderSummary();
    var smsOn = $('#cw-notify-sms').checked;
    var entries = [
      ['نام پیشنهاد', val('name')], ['نوع', MODE === 'occasion' ? 'مناسبت خودکار' : 'کمپین تخفیف'],
      [MODE === 'occasion' ? 'چه مناسبتی؟' : 'برای چه کسانی؟', MODE === 'occasion' ? occasionText() : audienceText()],
      ['هدیه', fullReward()], ['زمان اجرا', timeText()], ['اطلاع‌رسانی', notifyText()],
      ['متن پیامک', smsOn ? ($('#cw-sms-template-name').textContent + ' (غیرقابل ویرایش)\n' + $('#cw-sms-bubble').textContent) : 'ارسال پیامک خاموش است'],
      ['وضعیت اولیه', 'پیش‌نویس؛ بدون فعال‌سازی یا ارسال خودکار']
    ];
    var ul = $('#cw-review-list'); ul.replaceChildren();
    entries.forEach(function (e) {
      var li = document.createElement('li'), b = document.createElement('b'), sp = document.createElement('span');
      b.textContent = e[0]; sp.textContent = e[1]; li.appendChild(b); li.appendChild(sp); ul.appendChild(li);
    });
    $('#cw-review-overlay').classList.add('cw-open'); $('#cw-close-review').focus();
  }
  function closeReview() { var o = $('#cw-review-overlay'), was = o.classList.contains('cw-open'); o.classList.remove('cw-open'); if (was) { var t = $('#cw-view-review'); if (t) t.focus(); } }
  $('#cw-view-review').addEventListener('click', function () {
    for (var i = 1; i <= 3; i++) { if (!validators[i]()) { go(i); validators[i](); return; } }
    loadPreview().then(showReview, showReview);  // متنِ پیش‌نمایش پیش از مرور نهایی تازه می‌شود
  });
  $('#cw-close-review').addEventListener('click', closeReview);
  $('#cw-review-overlay').addEventListener('click', function (e) { if (e.target === this) closeReview(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeReview(); });
  form.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'BUTTON') return;
    e.preventDefault(); if (state.step < 3) goChecked(state.step + 1);
  });
  form.addEventListener('submit', function (e) {
    for (var i = 1; i <= 3; i++) { if (!validators[i]()) { e.preventDefault(); closeReview(); go(i); validators[i](); return; } }
  });

  // ------------------------------------------------------------------ آغاز: خطایِ سرور → رفتن به مرحله‌ی مربوط
  state.prevAudience = val('audience_kind') === 'custom' ? 'all' : (val('audience_kind') || 'all');
  refresh();
  var firstErr = $('.cw-panel .cw-inline-err');
  if (firstErr) { var host = firstErr.closest('[data-step]'); if (host) go(Number(host.getAttribute('data-step'))); else go(1); }
  else go(1);
})();
