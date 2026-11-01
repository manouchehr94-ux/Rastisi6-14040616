/* RastiSi — visitor consent for analytics / advertising tags (opt-in, no tag before a real choice).
   Reads the validated JSON config the server prints (#rs-consent-config). It never builds tag code from server text: ids are re-validated here, tags are created with DOM APIs.
   Consent Mode v2 signals default to "denied" BEFORE any Google tag exists; the visitor's choice is a first-party cookie they can reopen and change at any time. */
(function () {
  'use strict';
  var node = document.getElementById('rs-consent-config');
  if (!node) return;
  var cfg;
  try { cfg = JSON.parse(node.textContent); } catch (e) { return; }
  if (!cfg || cfg.policy !== 'opt_in' || !cfg.ids) return;

  var PATTERN = { ga4: /^G-[A-Z0-9]{6,10}$/, gtm: /^GTM-[A-Z0-9]{4,8}$/, meta_pixel: /^\d{10,20}$/ };
  var ids = {};
  Object.keys(cfg.ids).forEach(function (k) { if (PATTERN[k] && PATTERN[k].test(String(cfg.ids[k]))) ids[k] = String(cfg.ids[k]); });
  if (!Object.keys(ids).length) return;
  var T = cfg.texts || {};
  var gpc = !!(navigator.globalPrivacyControl);

  // ---- Consent Mode v2: everything denied (except security) before any tag is even defined ----------------------------------------
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  var defaults = {};
  (cfg.signals.default_denied || []).forEach(function (s) { defaults[s] = 'denied'; });
  (cfg.signals.default_granted || []).forEach(function (s) { defaults[s] = 'granted'; });
  defaults.wait_for_update = 500;
  gtag('consent', 'default', defaults);

  // ---- the stored choice ---------------------------------------------------------------------------------------------------------
  function readChoice() {
    var m = document.cookie.match(new RegExp('(?:^|; )' + cfg.cookie + '=([^;]*)'));
    if (!m) return null;
    try {
      var c = JSON.parse(decodeURIComponent(m[1]));
      if (c && c.v === cfg.version && (c.a === 0 || c.a === 1) && (c.m === 0 || c.m === 1)) return c;
    } catch (e) { /* unreadable = no choice */ }
    return null;
  }
  function writeChoice(a, m) {
    var c = { v: cfg.version, a: a ? 1 : 0, m: (m && !gpc) ? 1 : 0, t: Math.floor(Date.now() / 1000) };
    document.cookie = cfg.cookie + '=' + encodeURIComponent(JSON.stringify(c)) + '; Max-Age=' + cfg.max_age + '; Path=/; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
    return c;
  }

  // ---- loaders (only ever called after a matching grant) --------------------------------------------------------------------------
  var loaded = {};
  function script(src) { var s = document.createElement('script'); s.async = true; s.src = src; document.head.appendChild(s); }
  var LOAD = {
    gtm: function (id) {
      window.dataLayer.push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
      script('https://www.googletagmanager.com/gtm.js?id=' + encodeURIComponent(id));
    },
    ga4: function (id) {
      script('https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id));
      gtag('js', new Date());
      gtag('config', id);
    },
    meta_pixel: function (id) {
      var f = window, n;
      if (!f.fbq) {
        n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
        if (!f._fbq) f._fbq = n;
        n.push = n; n.loaded = true; n.version = '2.0'; n.queue = [];
        script('https://connect.facebook.net/en_US/fbevents.js');
      }
      f.fbq('init', id);
      f.fbq('track', 'PageView');
    }
  };
  function applyChoice(c) {
    var update = {};
    (cfg.signals.analytics || []).forEach(function (s) { update[s] = c.a ? 'granted' : 'denied'; });
    (cfg.signals.marketing || []).forEach(function (s) { update[s] = c.m ? 'granted' : 'denied'; });
    gtag('consent', 'update', update);
    (cfg.load || []).forEach(function (item) {
      var ok = item.needs === 'analytics' ? c.a : item.needs === 'marketing' ? c.m : (c.a || c.m);
      if (ok && ids[item.tracker] && !loaded[item.tracker]) { loaded[item.tracker] = true; LOAD[item.tracker](ids[item.tracker]); }
    });
  }

  // ---- UI -----------------------------------------------------------------------------------------------------------------------------
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  var banner = null, reopen = null;
  function closeBanner() { if (banner) { banner.remove(); banner = null; } if (reopen) reopen.hidden = false; }
  function choose(a, m) {
    var before = readChoice();
    var c = writeChoice(a, m);
    var revoked = before && ((before.a && !c.a) || (before.m && !c.m));
    applyChoice(c);
    closeBanner();
    if (revoked) location.reload();                         // a tag that was granted cannot be un-loaded: start the page again without it
  }
  function openBanner() {
    if (banner) return;
    if (reopen) reopen.hidden = true;
    var cur = readChoice() || { a: 0, m: 0 };
    banner = el('section', 'rs-consent');
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-modal', 'false');
    banner.setAttribute('aria-labelledby', 'rs-consent-title');
    banner.setAttribute('data-testid', 'consent-banner');
    banner.tabIndex = -1;
    var title = el('h2', 'rs-consent__title', T.title); title.id = 'rs-consent-title';
    var body = el('p', 'rs-consent__body', T.body);
    var panel = el('div', 'rs-consent__panel'); panel.hidden = true; panel.id = 'rs-consent-panel';
    var boxes = {};
    (cfg.categories || []).forEach(function (cat) {
      var row = el('label', 'rs-consent__row');
      var input = el('input'); input.type = 'checkbox';
      input.checked = cat.required ? true : false; input.disabled = !!cat.required;      // never pre-ticked (the required one is not a choice)
      if (!cat.required) input.checked = !!cur[cat.key === 'analytics' ? 'a' : 'm'];
      if (cat.key === 'marketing' && gpc) { input.checked = false; input.disabled = true; }
      boxes[cat.key] = input;
      var txt = el('span'); txt.appendChild(el('b', '', cat.label)); txt.appendChild(document.createElement('br')); txt.appendChild(document.createTextNode(cat.desc));
      row.appendChild(input); row.appendChild(txt); panel.appendChild(row);
    });
    if (gpc) panel.appendChild(el('p', 'rs-consent__note', T.gpc));
    var actions = el('div', 'rs-consent__actions');
    var accept = el('button', 'rs-consent__btn', T.accept_all); accept.type = 'button'; accept.setAttribute('data-testid', 'consent-accept');
    var reject = el('button', 'rs-consent__btn', T.reject_all); reject.type = 'button'; reject.setAttribute('data-testid', 'consent-reject');
    var custom = el('button', 'rs-consent__btn rs-consent__btn--link', T.customize); custom.type = 'button'; custom.setAttribute('aria-expanded', 'false'); custom.setAttribute('aria-controls', 'rs-consent-panel');
    custom.setAttribute('data-testid', 'consent-customize');
    var save = el('button', 'rs-consent__btn', T.save); save.type = 'button'; save.hidden = true; save.setAttribute('data-testid', 'consent-save');
    accept.addEventListener('click', function () { choose(true, true); });
    reject.addEventListener('click', function () { choose(false, false); });
    custom.addEventListener('click', function () {
      var open = panel.hidden; panel.hidden = !open; save.hidden = !open; custom.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    save.addEventListener('click', function () { choose(boxes.analytics && boxes.analytics.checked, boxes.marketing && boxes.marketing.checked); });
    [accept, reject, custom, save].forEach(function (b) { actions.appendChild(b); });
    [title, body, panel, actions].forEach(function (n) { banner.appendChild(n); });
    document.body.appendChild(banner);
    banner.focus({ preventScroll: true });
  }
  function mountReopen() {
    reopen = el('button', 'rs-consent-reopen', T.reopen);
    reopen.type = 'button'; reopen.setAttribute('data-rs-consent-open', ''); reopen.setAttribute('data-testid', 'consent-reopen');
    reopen.addEventListener('click', openBanner);
    document.body.appendChild(reopen);
  }

  function start() {
    mountReopen();
    var c = readChoice();
    if (c) { applyChoice(c); } else { openBanner(); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
}());
