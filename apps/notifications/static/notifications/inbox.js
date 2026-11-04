/* زنگ/Toast/Polling اعلانِ مدیران — بدونِ وابستگی، بدونِ تزریقِ HTML (همه‌چیز با textContent/DOM API).
   * Polling کنترل‌شده: فقط تبِ قابل‌مشاهده، فقط «تبِ رهبر» (چندتبی)، backoff روی خطا، کندتر شدن در نبودِ تغییر، توقف در خروج/تغییرِ کاربر.
   * Toast: هر اعلان در همه‌ی تب‌ها فقط یک‌بار (BroadcastChannel + localStorage کلیددار به کاربر)؛ وضعیتِ خوانده‌شدن همیشه از سرور است (نه localStorage). */
(function () {
  'use strict';
  var root = document.querySelector('[data-nt-bell]');
  if (!root) { initPushUI(); return; }

  var cfg = { summary: root.dataset.summaryUrl, inbox: root.dataset.inboxUrl, base: Math.max(15, parseInt(root.dataset.poll, 10) || 30), user: root.dataset.userKey, csrf: root.dataset.csrf };
  var btn = root.querySelector('[data-nt-toggle]'), panel = root.querySelector('#nt-panel'), list = root.querySelector('[data-nt-list]');
  var badge = root.querySelector('[data-nt-badge]'), sr = root.querySelector('[data-nt-sr]'), live = root.querySelector('[data-nt-live]');
  var emptyEl = root.querySelector('[data-nt-empty]'), errEl = root.querySelector('[data-nt-error]');
  var tabId = Math.random().toString(36).slice(2), delay = cfg.base, timer = null, since = Date.now() - 1000, lastSig = '', stopped = false;
  var chan = ('BroadcastChannel' in window) ? new BroadcastChannel('rs-notif') : null;
  var SHOWN_KEY = 'nt_shown:' + cfg.user, LEADER_KEY = 'nt_leader';

  function ls(op, k, v) { try { return op === 'get' ? window.localStorage.getItem(k) : window.localStorage.setItem(k, v); } catch (e) { return null; } }
  function shown() { try { return JSON.parse(ls('get', SHOWN_KEY) || '[]'); } catch (e) { return []; } }
  function remember(id) { var s = shown(); if (s.indexOf(id) < 0) { s.push(id); ls('set', SHOWN_KEY, JSON.stringify(s.slice(-100))); } }

  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function toFa(n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.charAt(d); }); }
  function itemHref(i) { return cfg.inbox + i.id + '/' + (i.has_link ? 'go/' : ''); }
  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': cfg.csrf, 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' }, body: body || null });
  }

  /* ---- شمارنده ---- */
  function setUnread(n) {
    badge.hidden = !n; badge.textContent = n > 99 ? '۹۹+' : toFa(n);
    sr.textContent = 'اعلان‌ها؛ ' + toFa(n) + ' خوانده‌نشده';
    root.dataset.unread = n;
  }

  /* ---- لیست درونِ پنل ---- */
  function render(items) {
    while (list.firstChild) list.removeChild(list.firstChild);
    emptyEl.hidden = items.length > 0;
    items.forEach(function (i) {
      var li = el('li', 'nt-item nt-item--' + i.tone + (i.read ? '' : ' is-unread'));
      var a = el('a', 'nt-item__link'); a.href = itemHref(i);
      var top = el('div', 'nt-item__top');
      top.appendChild(el('span', 'nt-chip nt-chip--' + i.tone, i.severity_label));
      top.appendChild(el('span', 'nt-item__cat', i.category_label));
      a.appendChild(top);
      a.appendChild(el('div', 'nt-item__title', i.title + (i.count > 1 ? ' (×' + toFa(i.count) + ')' : '')));
      if (i.summary) a.appendChild(el('div', 'nt-item__sum', i.summary));
      li.appendChild(a); list.appendChild(li);
    });
  }

  /* ---- Toast ---- */
  var stack = el('div', 'nt-toasts'); stack.setAttribute('aria-label', 'اعلان‌های فوری'); document.body.appendChild(stack);
  function toast(i) {
    if (shown().indexOf(i.id) >= 0 || stack.querySelector('[data-id="' + i.id + '"]')) return;
    remember(i.id); if (chan) chan.postMessage({ t: 'shown', id: i.id, user: cfg.user });
    while (stack.children.length >= 3) stack.removeChild(stack.firstChild);
    var t = el('div', 'nt-toast nt-toast--' + i.tone); t.dataset.id = i.id; t.setAttribute('role', i.severity >= 4 ? 'alert' : 'status');
    var head = el('div', 'nt-toast__head'); head.appendChild(el('span', 'nt-chip nt-chip--' + i.tone, i.severity_label)); head.appendChild(el('strong', null, i.title));
    var x = el('button', 'nt-toast__x', '✕'); x.type = 'button'; x.setAttribute('aria-label', 'بستن اعلان'); x.addEventListener('click', function () { dismiss(t); });
    head.appendChild(x); t.appendChild(head);
    if (i.summary) t.appendChild(el('div', 'nt-toast__sum', i.summary));
    var a = el('a', 'nt-link', 'مشاهده'); a.href = itemHref(i); t.appendChild(a);
    stack.appendChild(t);
    if (i.severity < 4) setTimeout(function () { dismiss(t); }, 9000);
  }
  function dismiss(t) { if (t.parentNode) t.parentNode.removeChild(t); }

  /* ---- Polling ---- */
  function isLeader() {
    var now = Date.now(), cur = null; try { cur = JSON.parse(ls('get', LEADER_KEY) || 'null'); } catch (e) {}
    if (!cur || cur.id === tabId || now - cur.ts > cfg.base * 2500 || cur.hidden) { ls('set', LEADER_KEY, JSON.stringify({ id: tabId, ts: now, hidden: document.hidden })); return true; }
    return false;
  }
  function apply(data, fromPeer) {
    if (data.user_key && data.user_key !== cfg.user) { stopped = true; window.location.reload(); return; }       // نشستِ کاربرِ دیگر: نمایشِ اعلانِ حسابِ قبلی ممنوع
    setUnread(data.unread); errEl.hidden = true;
    var sig = data.unread + ':' + (data.items[0] ? data.items[0].id : '');
    render(data.items);
    (data.toasts || []).forEach(toast);
    if (data.toasts && data.toasts.length && live) live.textContent = 'اعلان جدید: ' + data.toasts[0].title;
    if (!fromPeer) { delay = sig !== lastSig ? cfg.base : Math.min(Math.round(delay * 1.25), cfg.base * 3); lastSig = sig; since = data.now_ms; if (chan) chan.postMessage({ t: 'data', data: data, user: cfg.user }); }
  }
  function poll() {
    clearTimeout(timer); if (stopped) return;
    if (document.hidden || !isLeader()) { timer = setTimeout(poll, cfg.base * 1000); return; }
    fetch(cfg.summary + '?since=' + since, { credentials: 'same-origin', headers: { Accept: 'application/json' }, cache: 'no-store' })
      .then(function (r) {
        if (!r.ok || (r.headers.get('content-type') || '').indexOf('json') < 0) { stopped = true; throw new Error('auth'); }   // خروج از حساب/ریدایرکت به ورود ⇒ توقف
        return r.json();
      })
      .then(function (d) { apply(d, false); })
      .catch(function (e) { if (!stopped) { errEl.hidden = false; delay = Math.min(delay * 2, 300); } })
      .then(function () { timer = setTimeout(poll, delay * 1000); });
  }
  if (chan) chan.onmessage = function (m) {
    var d = m.data || {}; if (d.user !== cfg.user) return;
    if (d.t === 'shown') { return; }
    if (d.t === 'data') apply(d.data, true);
  };
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { delay = cfg.base; poll(); } });
  window.addEventListener('storage', function (e) { if (e.key === SHOWN_KEY) { /* تب دیگر نشان داد */ } });

  /* ---- پنل ---- */
  btn.setAttribute('aria-expanded', 'false');        // الگوی ARIA فقط با JS اضافه می‌شود (بدونِ JS دکمه کاری نمی‌کند)
  function open() { panel.hidden = false; btn.setAttribute('aria-expanded', 'true'); var f = panel.querySelector('a, button'); if (f) f.focus(); poll(); }
  function close(back) { panel.hidden = true; btn.setAttribute('aria-expanded', 'false'); if (back) btn.focus(); }
  btn.addEventListener('click', function () { panel.hidden ? open() : close(true); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) close(true); });
  document.addEventListener('click', function (e) { if (!panel.hidden && !root.contains(e.target)) close(false); });
  root.querySelector('[data-nt-readall]').addEventListener('click', function () {
    post(cfg.inbox + 'read-all/').then(function (r) { return r.json(); }).then(function () { delay = cfg.base; poll(); }).catch(function () { errEl.hidden = false; });
  });

  setUnread(parseInt(root.dataset.unread, 10) || 0);
  poll();
  initPushUI();

  /* ============================== اعلانِ سیستمِ مرورگر (صفحه‌ی تنظیمات) ============================== */
  function initPushUI() {
    var box = document.querySelector('[data-nt-push]'); if (!box) return;
    var statusEl = box.querySelector('[data-nt-push-status]'), enable = box.querySelector('[data-nt-push-enable]'), disable = box.querySelector('[data-nt-push-disable]');
    var csrf = box.dataset.csrf, key = box.dataset.publicKey, swUrl = box.dataset.swUrl, scope = swUrl.replace(/sw\.js$/, '').replace(/inbox\/$/, ''), subUrl = box.dataset.subscribeUrl, unsubUrl = box.dataset.unsubscribeUrl;
    function say(msg) { statusEl.textContent = msg; }
    function b64u(s) { var p = '='.repeat((4 - s.length % 4) % 4), b = (s + p).replace(/-/g, '+').replace(/_/g, '/'), r = atob(b), out = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) out[i] = r.charCodeAt(i); return out; }
    var secure = window.isSecureContext, supported = secure && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    if (box.dataset.serverReady !== '1') { say('ارسالِ اعلانِ مرورگر روی این سرور فعال نشده است؛ صندوق و اعلانِ درون‌برنامه‌ای مستقل کار می‌کنند.'); enable.hidden = true; disable.hidden = true; return; }
    if (!supported) { say(secure ? 'این مرورگر از اعلانِ سیستم (Web Push) پشتیبانی نمی‌کند؛ صندوق و اعلانِ درون‌برنامه‌ای کار می‌کنند.' : 'اعلانِ سیستم فقط روی HTTPS (یا localhost) کار می‌کند؛ در این آدرس فعال نیست.'); enable.hidden = true; disable.hidden = true; return; }
    function refresh() {
      var perm = Notification.permission;
      navigator.serviceWorker.getRegistration(scope).then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; }).then(function (sub) {
        enable.hidden = !!sub || perm === 'denied'; disable.hidden = !sub;
        say(perm === 'denied' ? 'مجوزِ اعلان در این مرورگر مسدود است؛ برای فعال‌سازی باید آن را در تنظیماتِ مرورگر (نمادِ قفل کنارِ آدرس) آزاد کنید.' : sub ? 'اعلانِ سیستم در این مرورگر فعال است.' : perm === 'granted' ? 'مجوز داده شده؛ برای ثبتِ این دستگاه دکمه‌ی «فعال‌سازی» را بزنید.' : 'غیرفعال. با زدنِ «فعال‌سازی» مرورگر از شما مجوز می‌خواهد.');
      });
    }
    enable.addEventListener('click', function () {                                   // مجوز فقط پس از اقدامِ آگاهانه‌ی کاربر
      Notification.requestPermission().then(function (perm) {
        if (perm !== 'granted') return refresh();
        return navigator.serviceWorker.register(swUrl, { scope: scope }).then(function (reg) {
          return navigator.serviceWorker.ready.then(function () { return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u(key) }); });
        }).then(function (sub) {
          var j = sub.toJSON(); j.label = (navigator.userAgent.match(/(Firefox|Edg|Chrome|Safari)/) || ['مرورگر'])[0];
          return fetch(subUrl, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/json' }, body: JSON.stringify(j) });
        }).then(function (r) { if (!r.ok) throw new Error('subscribe'); window.location.reload(); });
      }).catch(function () { say('ثبتِ این دستگاه انجام نشد؛ دوباره تلاش کنید.'); });
    });
    disable.addEventListener('click', function () {
      navigator.serviceWorker.getRegistration(scope).then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; }).then(function (sub) {
        if (!sub) return null; var ep = sub.endpoint;
        return sub.unsubscribe().then(function () { return fetch(unsubUrl, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: ep }) }); });
      }).then(function () { window.location.reload(); });
    });
    refresh();
  }
})();
