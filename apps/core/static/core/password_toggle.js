/* RastiSi — shared password visibility toggle. See password_toggle.css for the layout contract.
 *
 * Progressive enhancement: every <input type="password"> is wrapped in .pw-field with an eye button.
 *  - default hidden (type=password); the button flips password <-> text and nothing else: name, id, value,
 *    autocomplete and validation are untouched, so browser autofill and form posts behave exactly as before;
 *  - the field returns to hidden on submit, reset and bfcache restore;
 *  - opt out with data-pw-toggle="off"; fields added later (htmx/Alpine) are picked up by a MutationObserver.
 */
(function () {
  'use strict';
  var SHOW = 'نمایش رمز';
  var HIDE = 'پنهان‌کردن رمز';
  var ICON_ON = '<svg class="pw-ico-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  var ICON_OFF = '<svg class="pw-ico-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.9 17.9A10.9 10.9 0 0 1 12 19c-6.4 0-10-7-10-7a18.5 18.5 0 0 1 5.1-5.9M9.9 4.2A9.9 9.9 0 0 1 12 4c6.4 0 10 8 10 8a18.6 18.6 0 0 1-2.2 3.2M1 1l22 22"/><path d="M14.1 14.1a3 3 0 1 1-4.2-4.2"/></svg>';
  var uid = 0;

  function enhance(input) {
    if (!input || input.dataset.pwReady === '1' || input.dataset.pwToggle === 'off') return;
    if (input.type !== 'password') return;
    var parent = input.parentNode;
    if (!parent) return;
    input.dataset.pwReady = '1';

    var wrap = document.createElement('span');
    wrap.className = 'pw-field';
    // The gutter follows the INPUT's own text direction, never the page's.
    var dir = (input.getAttribute('dir') || '').toLowerCase();
    if (dir !== 'ltr' && dir !== 'rtl') {
      try { dir = window.getComputedStyle(input).direction === 'ltr' ? 'ltr' : 'rtl'; } catch (e) { dir = 'rtl'; }
    }
    wrap.setAttribute('dir', dir);
    parent.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-toggle';
    btn.setAttribute('aria-pressed', 'false');
    btn.setAttribute('aria-label', SHOW);
    btn.title = SHOW;
    if (!input.id) { input.id = 'pw-input-' + (++uid); }
    btn.setAttribute('aria-controls', input.id);
    btn.innerHTML = ICON_ON + ICON_OFF;
    wrap.appendChild(btn);

    function paint(show) {
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
      var label = show ? HIDE : SHOW;
      btn.setAttribute('aria-label', label);
      btn.title = label;
    }
    btn.addEventListener('click', function () {
      var start = input.selectionStart, end = input.selectionEnd, had = document.activeElement === input;
      paint(input.type === 'password');
      if (had) { try { input.focus(); input.setSelectionRange(start, end); } catch (e) { /* not selectable */ } }
    });
    // keep the field hidden whenever the form is submitted/reset or the page is restored from bfcache
    var form = input.form || input.closest('form');
    if (form) {
      form.addEventListener('submit', function () { paint(false); });
      form.addEventListener('reset', function () { paint(false); });
    }
    window.addEventListener('pageshow', function () { paint(false); });
  }

  function scan(root) {
    var list = (root && root.querySelectorAll ? root : document).querySelectorAll('input[type="password"]');
    for (var i = 0; i < list.length; i++) enhance(list[i]);
  }

  function boot() {
    scan(document);
    if (typeof MutationObserver === 'function') {
      new MutationObserver(function (records) {
        for (var i = 0; i < records.length; i++) {
          var added = records[i].addedNodes;
          for (var j = 0; j < added.length; j++) {
            var n = added[j];
            if (n.nodeType !== 1) continue;
            if (n.matches && n.matches('input[type="password"]')) enhance(n); else scan(n);
          }
        }
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
