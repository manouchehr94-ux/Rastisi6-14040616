/* RastiSi — تقویم و ورودیِ تاریخِ شمسی (جلالی)، یک کامپوننتِ مرکزی برایِ کل رابطِ فارسی (FOLLOWUP-14).
 *
 * فقط لایهٔ نمایش/ورودی شمسی است: ورودی‌هایِ native ‏<input type="date|datetime-local"> به یک فیلدِ متنیِ شمسی + تقویم ارتقا می‌یابند
 * و *همان* ورودیِ اصلی (با همان name) به‌صورتِ hidden و با مقدارِ ISO میلادیِ محلی («YYYY-MM-DD» یا «YYYY-MM-DDTHH:MM») ارسال می‌شود؛
 * پس قراردادِ سرور (میلادی، منطقهٔ زمانیِ فروشگاه) دست‌نخورده است. برایِ مستثنا کردن: data-native-date.
 * وابستگیِ بیرونی ندارد؛ الگوریتمِ تبدیل همان جدولِ breaks سالِ کبیسهٔ ۳۳ساله (هم‌ارز jdatetime) است و با آزمون مقایسه می‌شود. */
(function (root) {
  'use strict';

  /* ---------- تبدیل جلالی ↔ میلادی (jalaali algorithm) ---------- */
  var BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
  function div(a, b) { return ~~(a / b); }
  function mod(a, b) { return a - ~~(a / b) * b; }
  function jalCal(jy, withoutLeap) {
    var bl = BREAKS.length, gy = jy + 621, leapJ = -14, jp = BREAKS[0], jm, jump = 0, leap, leapG, march, n, i;
    if (jy < jp || jy >= BREAKS[bl - 1]) throw new Error('Invalid Jalaali year ' + jy);
    for (i = 1; i < bl; i += 1) {
      jm = BREAKS[i];
      jump = jm - jp;
      if (jy < jm) break;
      leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
      jp = jm;
    }
    n = jy - jp;
    leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
    if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
    leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
    march = 20 + leapJ - leapG;
    if (withoutLeap) return { gy: gy, march: march };
    if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
    leap = mod(mod(n + 1, 33) - 1, 4);
    if (leap === -1) leap = 4;
    return { leap: leap, gy: gy, march: march };
  }
  function g2d(gy, gm, gd) {
    var d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
    return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
  }
  function d2g(jdn) {
    var j = 4 * jdn + 139361631, i, gd, gm, gy;
    j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
    i = div(mod(j, 1461), 4) * 5 + 308;
    gd = div(mod(i, 153), 5) + 1;
    gm = mod(div(i, 153), 12) + 1;
    gy = div(j, 1461) - 100100 + div(8 - gm, 6);
    return { gy: gy, gm: gm, gd: gd };
  }
  function j2d(jy, jm, jd) {
    var r = jalCal(jy, true);
    return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  }
  function d2j(jdn) {
    var gy = d2g(jdn).gy, jy = gy - 621, r = jalCal(jy, false), jdn1f = g2d(gy, 3, r.march), jd, jm, k;
    k = jdn - jdn1f;
    if (k >= 0) {
      if (k <= 185) return { jy: jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
      k -= 186;
    } else {
      jy -= 1; k += 179;
      if (r.leap === 1) k += 1;
    }
    return { jy: jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
  }
  function isLeap(jy) { return jalCal(jy, false).leap === 0; }
  function monthLength(jy, jm) { return jm <= 6 ? 31 : (jm <= 11 ? 30 : (isLeap(jy) ? 30 : 29)); }
  function toJalali(gy, gm, gd) { return d2j(g2d(gy, gm, gd)); }
  function toGregorian(jy, jm, jd) { return d2g(j2d(jy, jm, jd)); }
  /* روزِ هفته با شنبه=۰ */
  function weekdayOf(jy, jm, jd) { return mod(j2d(jy, jm, jd) + 2, 7); }

  /* ---------- رشته‌ها/ارقام ---------- */
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  var MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
  var WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
  var WEEKDAY_NAMES = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
  function faDigits(s) { return String(s).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
  function enDigits(s) {
    return String(s).replace(/[۰-۹]/g, function (d) { return String(FA.indexOf(d)); })
      .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 1632); });
  }
  function pad(n, w) { n = String(n); while (n.length < (w || 2)) n = '0' + n; return n; }

  function fmtJalali(jy, jm, jd) { return faDigits(pad(jy, 4) + '/' + pad(jm) + '/' + pad(jd)); }
  function isoDate(g) { return pad(g.gy, 4) + '-' + pad(g.gm) + '-' + pad(g.gd); }

  /* «۱۴۰۵/۰۷/۲۴» یا «۱۴۰۵/۰۷/۲۴ ۱۴:۳۰» (ارقامِ فارسی/عربی/لاتین، جداکنندهٔ / - .) یا ISO میلادی. ⇒ {jy,jm,jd,h,mi,iso} یا null */
  function parseText(raw, withTime) {
    var text = enDigits(raw || '').replace(/‏|‎/g, '').trim();
    var m = /^(\d{3,4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})(?:[ T]+(\d{1,2}):(\d{2}))?$/.exec(text);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3], h = m[4] === undefined ? 0 : +m[4], mi = m[5] === undefined ? 0 : +m[5];
    if (h > 23 || mi > 59 || mo < 1 || mo > 12 || d < 1) return null;
    var g, j;
    if (y >= 1700) {                     /* میلادی چسبانده‌شده */
      if (d > 31) return null;
      g = { gy: y, gm: mo, gd: d };
      try { j = toJalali(y, mo, d); } catch (e) { return null; }
      var back = toGregorian(j.jy, j.jm, j.jd);
      if (back.gy !== y || back.gm !== mo || back.gd !== d) return null;
    } else {
      if (y < 1200 || y > 1600 || d > monthLength(y, mo)) return null;
      j = { jy: y, jm: mo, jd: d };
      g = toGregorian(y, mo, d);
    }
    return { jy: j.jy, jm: j.jm, jd: j.jd, h: h, mi: mi, iso: isoDate(g) + (withTime ? 'T' + pad(h) + ':' + pad(mi) : '') };
  }
  function fromISO(value, withTime) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(value || '');
    if (!m) return null;
    var j = toJalali(+m[1], +m[2], +m[3]);
    var h = m[4] ? +m[4] : 0, mi = m[5] ? +m[5] : 0;
    return { jy: j.jy, jm: j.jm, jd: j.jd, h: h, mi: mi, iso: isoDate({ gy: +m[1], gm: +m[2], gd: +m[3] }) + (withTime ? 'T' + pad(h) + ':' + pad(mi) : '') };
  }
  function displayOf(v, withTime) { return fmtJalali(v.jy, v.jm, v.jd) + (withTime ? ' ' + faDigits(pad(v.h) + ':' + pad(v.mi)) : ''); }

  var api = {
    toJalali: toJalali, toGregorian: toGregorian, isLeap: isLeap, monthLength: monthLength, weekdayOf: weekdayOf,
    parseText: parseText, fromISO: fromISO, displayOf: displayOf, faDigits: faDigits, enDigits: enDigits,
  };
  root.RastiJalali = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof document === 'undefined') return;

  /* ---------- ویجت ---------- */
  var openPicker = null;
  var uid = 0;

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function upgrade(native) {
    if (native.dataset.jalaliUpgraded || native.hasAttribute('data-native-date')) return;
    var type = native.getAttribute('type');
    if (type !== 'date' && type !== 'datetime-local') return;
    var withTime = type === 'datetime-local';
    native.dataset.jalaliUpgraded = '1';
    uid += 1;

    var minV = fromISO(native.getAttribute('min'), withTime), maxV = fromISO(native.getAttribute('max'), withTime);
    var wrap = el('span', { 'class': 'jdp', dir: 'rtl' });
    var text = el('input', {
      type: 'text', 'class': (native.className ? native.className + ' ' : '') + 'jdp-text', dir: 'ltr', inputmode: 'numeric',
      autocomplete: 'off', placeholder: withTime ? '۱۴۰۵/۰۷/۲۴ ۱۴:۳۰' : '۱۴۰۵/۰۷/۲۴',
      'aria-haspopup': 'dialog', 'aria-label': native.getAttribute('aria-label') || '',
    });
    if (!text.getAttribute('aria-label')) text.removeAttribute('aria-label');
    if (native.id) { text.id = native.id; native.removeAttribute('id'); }
    if (native.required) text.required = true;
    if (native.disabled) text.disabled = true;
    ['style', 'title'].forEach(function (a) { if (native.hasAttribute(a)) text.setAttribute(a, native.getAttribute(a)); });
    var button = el('button', { type: 'button', 'class': 'jdp-btn', 'aria-label': 'باز کردن تقویم شمسی' }, '📅');
    var pop = el('div', { 'class': 'jdp-pop', role: 'dialog', 'aria-modal': 'false', 'aria-label': 'تقویم شمسی', id: 'jdp-pop-' + uid, hidden: '' });

    native.parentNode.insertBefore(wrap, native);
    wrap.appendChild(text);
    wrap.appendChild(button);
    wrap.appendChild(native);
    wrap.appendChild(pop);
    native.type = 'hidden';
    native.removeAttribute('required');
    native.removeAttribute('min');
    native.removeAttribute('max');

    var current = fromISO(native.value, withTime);
    var view = null;                          /* {jy, jm} ماهِ نمایش‌داده‌شده */
    var draft = null;                         /* انتخابِ جاری در پنجره */

    function setValue(v, silent) {
      current = v;
      native.value = v ? v.iso : '';
      text.value = v ? displayOf(v, withTime) : '';
      text.setCustomValidity('');
      text.removeAttribute('aria-invalid');
      if (!silent) {
        native.dispatchEvent(new Event('input', { bubbles: true }));
        native.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    function outOfRange(v) {
      if (minV && v.iso < minV.iso) return 'تاریخ نباید قبل از ' + displayOf(minV, withTime) + ' باشد.';
      if (maxV && v.iso > maxV.iso) return 'تاریخ نباید بعد از ' + displayOf(maxV, withTime) + ' باشد.';
      return '';
    }
    function invalid(msg) {
      text.setCustomValidity(msg);
      text.setAttribute('aria-invalid', 'true');
      native.value = '';
    }
    function commitText() {
      var raw = text.value.trim();
      if (!raw) { setValue(null); return true; }
      var v = parseText(raw, withTime);
      if (!v) { invalid(withTime ? 'تاریخ و ساعت را مثل ۱۴۰۵/۰۷/۲۴ ۱۴:۳۰ وارد کنید.' : 'تاریخ را مثل ۱۴۰۵/۰۷/۲۴ وارد کنید.'); return false; }
      var range = outOfRange(v);
      if (range) { invalid(range); return false; }
      setValue(v);
      return true;
    }
    text.addEventListener('change', commitText);
    text.addEventListener('blur', function () { if (!pop.hidden) return; commitText(); });

    /* ---------- پنجرهٔ تقویم ---------- */
    function close(returnFocus) {
      if (pop.hidden) return;
      pop.hidden = true;
      text.setAttribute('aria-expanded', 'false');
      if (openPicker === api2) openPicker = null;
      if (returnFocus) text.focus();
    }
    function today() {
      var n = new Date();
      var j = toJalali(n.getFullYear(), n.getMonth() + 1, n.getDate());
      return { jy: j.jy, jm: j.jm, jd: j.jd, h: n.getHours(), mi: n.getMinutes(),
        iso: isoDate({ gy: n.getFullYear(), gm: n.getMonth() + 1, gd: n.getDate() }) + (withTime ? 'T' + pad(n.getHours()) + ':' + pad(n.getMinutes()) : '') };
    }
    function makeValue(jy, jm, jd, h, mi) {
      var g = toGregorian(jy, jm, jd);
      return { jy: jy, jm: jm, jd: jd, h: h, mi: mi, iso: isoDate(g) + (withTime ? 'T' + pad(h) + ':' + pad(mi) : '') };
    }
    function dayDisabled(jy, jm, jd) {
      var v = makeValue(jy, jm, jd, 0, 0), d = v.iso.slice(0, 10);
      if (minV && d < minV.iso.slice(0, 10)) return true;
      if (maxV && d > maxV.iso.slice(0, 10)) return true;
      return false;
    }
    function render(focusDay) {
      while (pop.firstChild) pop.removeChild(pop.firstChild);
      var head = el('div', { 'class': 'jdp-head' });
      var prev = el('button', { type: 'button', 'class': 'jdp-nav', 'aria-label': 'ماه بعد' }, '‹');
      var next = el('button', { type: 'button', 'class': 'jdp-nav', 'aria-label': 'ماه قبل' }, '›');
      var monthSel = el('select', { 'aria-label': 'ماه' });
      MONTHS.forEach(function (name, i) { var o = el('option', { value: i + 1 }, name); if (i + 1 === view.jm) o.selected = true; monthSel.appendChild(o); });
      var yearIn = el('input', { type: 'text', inputmode: 'numeric', 'aria-label': 'سال', 'class': 'jdp-year', value: faDigits(view.jy), maxlength: '4', dir: 'ltr' });
      head.appendChild(next); head.appendChild(monthSel); head.appendChild(yearIn); head.appendChild(prev);
      pop.appendChild(head);
      function go(dm) {
        var m = view.jm + dm, y = view.jy;
        if (m < 1) { m = 12; y -= 1; } else if (m > 12) { m = 1; y += 1; }
        if (y >= 1200 && y <= 1600) { view = { jy: y, jm: m }; render(); }
      }
      prev.addEventListener('click', function () { go(1); });
      next.addEventListener('click', function () { go(-1); });
      monthSel.addEventListener('change', function () { view = { jy: view.jy, jm: +monthSel.value }; render(); });
      yearIn.addEventListener('change', function () {
        var y = +enDigits(yearIn.value);
        if (y >= 1200 && y <= 1600) { view = { jy: y, jm: view.jm }; }
        render();
      });

      var grid = el('div', { 'class': 'jdp-grid', role: 'grid', 'aria-label': MONTHS[view.jm - 1] + ' ' + faDigits(view.jy) });
      WEEKDAYS.forEach(function (w, i) { grid.appendChild(el('div', { 'class': 'jdp-wd', role: 'columnheader', 'aria-label': WEEKDAY_NAMES[i] }, w)); });
      var first = weekdayOf(view.jy, view.jm, 1), len = monthLength(view.jy, view.jm), t = today();
      var i, cells = [];
      for (i = 0; i < first; i += 1) grid.appendChild(el('div', { 'class': 'jdp-empty', 'aria-hidden': 'true' }));
      for (var d = 1; d <= len; d += 1) {
        var cls = 'jdp-day', disabled = dayDisabled(view.jy, view.jm, d);
        var isSel = current && current.jy === view.jy && current.jm === view.jm && current.jd === d;
        if (isSel) cls += ' is-selected';
        if (t.jy === view.jy && t.jm === view.jm && t.jd === d) cls += ' is-today';
        var b = el('button', { type: 'button', 'class': cls, 'data-day': d, 'aria-label': faDigits(d) + ' ' + MONTHS[view.jm - 1] + ' ' + faDigits(view.jy),
          tabindex: -1, role: 'gridcell' }, faDigits(d));
        if (isSel) b.setAttribute('aria-selected', 'true');
        if (disabled) b.disabled = true;
        grid.appendChild(b); cells.push(b);
      }
      pop.appendChild(grid);

      var foot = el('div', { 'class': 'jdp-foot' });
      var hour, minute;
      if (withTime) {
        var seed = draft || current || { h: 0, mi: 0 };
        hour = el('input', { type: 'text', inputmode: 'numeric', 'class': 'jdp-time', 'aria-label': 'ساعت (۰ تا ۲۳)', maxlength: '2', dir: 'ltr', value: faDigits(pad(seed.h)) });
        minute = el('input', { type: 'text', inputmode: 'numeric', 'class': 'jdp-time', 'aria-label': 'دقیقه (۰ تا ۵۹)', maxlength: '2', dir: 'ltr', value: faDigits(pad(seed.mi)) });
        var tw = el('span', { 'class': 'jdp-timewrap', dir: 'ltr' });
        tw.appendChild(hour); tw.appendChild(el('span', {}, ':')); tw.appendChild(minute);
        foot.appendChild(tw);
      }
      var todayBtn = el('button', { type: 'button', 'class': 'jdp-link' }, 'امروز');
      foot.appendChild(todayBtn);
      var clearBtn = null;
      if (!native.dataset.jdpRequired && !text.required) { clearBtn = el('button', { type: 'button', 'class': 'jdp-link' }, 'پاک کردن'); foot.appendChild(clearBtn); }
      var okBtn = null;
      if (withTime) { okBtn = el('button', { type: 'button', 'class': 'jdp-ok' }, 'تأیید'); foot.appendChild(okBtn); }
      pop.appendChild(foot);

      function timeParts() {
        var h = +enDigits(hour.value), mi = +enDigits(minute.value);
        return { h: (h >= 0 && h <= 23) ? h : 0, mi: (mi >= 0 && mi <= 59) ? mi : 0 };
      }
      function pick(day) {
        var tp = withTime ? timeParts() : { h: 0, mi: 0 };
        var v = makeValue(view.jy, view.jm, day, tp.h, tp.mi);
        var range = withTime ? outOfRange(v) : '';
        if (range) { text.value = displayOf(v, withTime); invalid(range); close(true); return; }
        setValue(v);
        if (withTime) { draft = v; render(day); } else close(true);
      }
      cells.forEach(function (b) {
        b.addEventListener('click', function () { pick(+b.getAttribute('data-day')); });
        b.addEventListener('keydown', function (e) {
          var d0 = +b.getAttribute('data-day'), step = 0;
          if (e.key === 'ArrowLeft') step = 1; else if (e.key === 'ArrowRight') step = -1;
          else if (e.key === 'ArrowDown') step = 7; else if (e.key === 'ArrowUp') step = -7;
          else if (e.key === 'PageDown') { go(1); return; } else if (e.key === 'PageUp') { go(-1); return; }
          else if (e.key === 'Home') step = -(d0 - 1); else if (e.key === 'End') step = len - d0;
          else return;
          e.preventDefault();
          var nd = d0 + step;
          if (nd >= 1 && nd <= len) { var nb = grid.querySelector('[data-day="' + nd + '"]'); if (nb && !nb.disabled) nb.focus(); }
        });
      });
      todayBtn.addEventListener('click', function () {
        var n = today();
        view = { jy: n.jy, jm: n.jm };
        if (withTime) { draft = n; render(n.jd); } else { setValue(n); close(true); }
      });
      if (clearBtn) clearBtn.addEventListener('click', function () { setValue(null); close(true); });
      if (okBtn) okBtn.addEventListener('click', function () { if (draft || current) setValue(makeValueFromTimes()); close(true); });
      function makeValueFromTimes() {
        var base = draft || current, tp = timeParts();
        return makeValue(base.jy, base.jm, base.jd, tp.h, tp.mi);
      }
      if (focusDay !== false) {
        var target = grid.querySelector('.is-selected:not(:disabled)') || grid.querySelector('.is-today:not(:disabled)') || grid.querySelector('.jdp-day:not(:disabled)');
        if (focusDay && grid.querySelector('[data-day="' + focusDay + '"]')) target = grid.querySelector('[data-day="' + focusDay + '"]');
        if (target && pop.contains(document.activeElement) || focusDay === true) { if (target) target.focus(); }
      }
    }
    function open() {
      if (text.disabled || !pop.hidden) return;
      if (openPicker) openPicker.close(false);
      if (text.value.trim()) commitText();
      var base = current || today();
      view = { jy: base.jy, jm: base.jm };
      draft = current;
      pop.hidden = false;
      text.setAttribute('aria-expanded', 'true');
      render(true);
      openPicker = api2;
    }
    var api2 = { close: close, root: wrap };
    button.addEventListener('click', function () { if (pop.hidden) open(); else close(true); });
    text.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || (e.altKey && e.key === 'ArrowDown')) { e.preventDefault(); open(); }
      else if (e.key === 'Enter' && !pop.hidden) { e.preventDefault(); }
      else if (e.key === 'Enter') { commitText(); }
    });
    pop.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.stopPropagation(); close(true); } });

    setValue(current, true);
    var form = native.form;
    if (form) form.addEventListener('reset', function () { setTimeout(function () { setValue(fromISO(native.defaultValue, withTime), true); }, 0); });
    if (form) form.addEventListener('submit', function (e) {
      if (text.value.trim() && !commitText()) { e.preventDefault(); text.reportValidity(); }
    }, true);
  }

  document.addEventListener('click', function (e) {
    if (openPicker && !openPicker.root.contains(e.target)) openPicker.close(false);
  });

  function scan(rootNode) {
    var list = (rootNode || document).querySelectorAll('input[type="date"], input[type="datetime-local"]');
    Array.prototype.forEach.call(list, upgrade);
  }
  api.scan = scan;
  api.upgrade = upgrade;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { scan(); });
  else scan();
  if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(function (records) {
      records.forEach(function (r) { Array.prototype.forEach.call(r.addedNodes, function (n) { if (n.nodeType === 1) scan(n); }); });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})(typeof window !== 'undefined' ? window : globalThis);
