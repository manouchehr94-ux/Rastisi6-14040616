/* R4-09 — the ONE colour picker of the Design Studio.
 *
 * Progressive enhancement of the colour controls that already exist, so there is no second storage path and no second
 * contract: every control keeps its native element(s) as the SOURCE OF TRUTH (and as the no-JS fallback) and this module
 * only puts a better picker in front of them.
 *
 *   semantic control  [data-r4-color-control]   <select data-r4-color-token> + <input type=color data-r4-color-custom>
 *                     value "" (automatic) | "token:<role>" (palette role) | "#RRGGBB" (custom)
 *   plain hex control input[type=color]          value "#rrggbb"
 *
 * Every R4 colour (section design block, standalone colour fields, background colour, overlay, Global Design, header /
 * footer geometry, container background) goes through the same code, found by a MutationObserver because the Inspector and
 * the Global Design panel re-render their markup.
 *
 * Behaviour contract
 *   - opening the picker or cancelling it (Esc / outside click / «انصراف») NEVER changes the value and sends nothing;
 *   - one click on «خودکار», a palette role or a suggested colour applies it at once (ONE change event);
 *   - free colour (spectrum / HEX) is a draft until «اعمال رنگ» (or Enter in the HEX field); an invalid HEX is refused
 *     in place and nothing is dispatched;
 *   - applying dispatches the same bubbling `change` the native controls always did, so live preview, the mutation queue,
 *     autosave and the Draft/Published separation are exactly what they were.
 */
(function () {
  'use strict';

  // The URL this script was loaded from (the stylesheet fallback below derives from it).
  var SCRIPT_SRC = (document.currentScript && document.currentScript.src) || '';

  var HEX6 = /^#[0-9a-f]{6}$/i;
  var NAMED = [
    // neutrals
    ['#FFFFFF', 'سفید'], ['#F1F5F9', 'خاکستری بسیار روشن'], ['#CBD5E1', 'خاکستری روشن'], ['#94A3B8', 'خاکستری'],
    ['#64748B', 'خاکستری متوسط'], ['#334155', 'خاکستری تیره'], ['#1E293B', 'سرمه‌ای تیره'], ['#000000', 'مشکی'],
    // light
    ['#FECACA', 'قرمز روشن'], ['#FED7AA', 'نارنجی روشن'], ['#FEF08A', 'زرد روشن'], ['#BBF7D0', 'سبز روشن'],
    ['#99F6E4', 'فیروزه‌ای روشن'], ['#BFDBFE', 'آبی روشن'], ['#DDD6FE', 'بنفش روشن'], ['#FBCFE8', 'صورتی روشن'],
    // base
    ['#EF4444', 'قرمز'], ['#F97316', 'نارنجی'], ['#EAB308', 'زرد'], ['#22C55E', 'سبز'],
    ['#14B8A6', 'فیروزه‌ای'], ['#3B82F6', 'آبی'], ['#8B5CF6', 'بنفش'], ['#EC4899', 'صورتی'],
    // dark
    ['#B91C1C', 'قرمز تیره'], ['#C2410C', 'نارنجی تیره'], ['#A16207', 'زرد تیره'], ['#15803D', 'سبز تیره'],
    ['#0F766E', 'فیروزه‌ای تیره'], ['#1D4ED8', 'آبی تیره'], ['#6D28D9', 'بنفش تیره'], ['#BE185D', 'صورتی تیره']
  ];

  // ---- colour maths ------------------------------------------------------------------------------------------
  function normHex(raw) {
    var s = String(raw == null ? '' : raw).trim();
    // Persian / Arabic-Indic digits are digits too
    s = s.replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); })
         .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); });
    if (s.charAt(0) === '#') s = s.slice(1);
    if (/^[0-9a-f]{3}$/i.test(s)) s = s.charAt(0) + s.charAt(0) + s.charAt(1) + s.charAt(1) + s.charAt(2) + s.charAt(2);
    return /^[0-9a-f]{6}$/i.test(s) ? '#' + s.toUpperCase() : '';
  }
  function hexToRgb(hex) {
    return [parseInt(hex.substr(1, 2), 16), parseInt(hex.substr(3, 2), 16), parseInt(hex.substr(5, 2), 16)];
  }
  function rgbToHex(r, g, b) {
    function h(n) { n = Math.max(0, Math.min(255, Math.round(n))); return (n < 16 ? '0' : '') + n.toString(16); }
    return ('#' + h(r) + h(g) + h(b)).toUpperCase();
  }
  function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, h = 0;
    if (d) {
      if (max === r) h = ((g - b) / d) % 6;
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60; if (h < 0) h += 360;
    }
    return { h: h, s: max ? d / max : 0, v: max };
  }
  function hsvToRgb(h, s, v) {
    var c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c, r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
    else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
    return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
  }
  function hsvToHex(h, s, v) { var rgb = hsvToRgb(h, s, v); return rgbToHex(rgb[0], rgb[1], rgb[2]); }
  function inkFor(hex) {
    var c = hexToRgb(hex);
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) > 150 ? '#111827' : '#FFFFFF';
  }
  function fa(n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.charAt(d); }); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function fire(target, type) { target.dispatchEvent(new Event(type, { bubbles: true })); }

  // ---- control adapters --------------------------------------------------------------------------------------
  function ariaLabelOf(node) {
    var own = node.getAttribute('aria-label');
    if (own) return own;
    if (node.id) {
      var lab = document.querySelector('label[for="' + node.id + '"]');
      if (lab && lab.textContent.trim()) return lab.textContent.trim();
    }
    var row = node.closest('[data-r4-design-prop],.r4-color-row,.r4-field');
    var sub = row && row.querySelector('.r4-field-sublabel,.r4-field-label');
    return sub ? sub.textContent.trim() : 'رنگ';
  }

  function semanticAdapter(host) {
    var select = host.querySelector('[data-r4-color-token]');
    var custom = host.querySelector('[data-r4-color-custom]');
    if (!select || !custom) return null;
    var tokens = [];
    Array.prototype.forEach.call(select.options, function (opt) {
      if (opt.value.indexOf('token:') !== 0) return;
      tokens.push({ value: opt.value, label: opt.textContent.trim(), hex: normHex(opt.getAttribute('data-hex')) });
    });
    return {
      kind: 'semantic', host: host, label: ariaLabelOf(select), allowAuto: true, tokens: tokens,
      disabled: function () { return select.disabled; },
      read: function () {
        var v = select.value;
        if (!v) return { type: 'auto', name: 'خودکار (پیش‌فرض قالب)', hex: '' };
        if (v === 'custom') {
          var hx = normHex(custom.value);
          return { type: 'custom', name: 'رنگ دلخواه', hex: hx };
        }
        var t = tokens.filter(function (x) { return x.value === v; })[0];
        return { type: 'token', value: v, name: t ? t.label : v, hex: t ? t.hex : '' };
      },
      applyAuto: function () { select.value = ''; fire(select, 'change'); },
      applyToken: function (value) { select.value = value; fire(select, 'change'); },
      applyCustom: function (hex) { select.value = 'custom'; custom.value = hex.toLowerCase(); fire(custom, 'change'); }
    };
  }

  function hexAdapter(input) {
    return {
      kind: 'hex', host: input, label: ariaLabelOf(input), allowAuto: false, tokens: [],
      disabled: function () { return input.disabled; },
      read: function () { return { type: 'custom', name: 'رنگ', hex: normHex(input.value) }; },
      applyCustom: function (hex) {
        input.value = hex.toLowerCase();
        fire(input, 'change');   // ONE change: the Studio's own listeners treat `input` as a continuous drag
      }
    };
  }

  function adapterOf(host) {
    return host.matches('[data-r4-color-control]') ? semanticAdapter(host) : hexAdapter(host);
  }

  // ---- robustness: never depend on a stylesheet to keep the native control out of the way ------------------------
  // A cached / missing stylesheet must not bring the Windows colour dialog back, so the native element is neutralised
  // by the script itself: not rendered (inline, !important), not focusable, not reachable by assistive tech and `inert`
  // (no pointer / keyboard activation). Its `.value` stays the source of truth and `change` is still dispatched on it.
  function neutralise(node) {
    node.setAttribute('data-r4-cp-native', '1');
    node.style.setProperty('display', 'none', 'important');
    node.tabIndex = -1;
    node.setAttribute('aria-hidden', 'true');
    node.setAttribute('inert', '');
    try { node.inert = true; } catch (err) { /* attribute above is enough */ }
  }

  // The picker's own stylesheet is expected from the template (content-hash URL). If the sentinel rule is not applied,
  // load it from the script's own location so the popover is fully styled in any case.
  function stylesApplied() {
    var probe = el('div', 'r4-cp-probe');
    document.body.appendChild(probe);
    var ok = window.getComputedStyle(probe).getPropertyValue('--r4-cp-css').trim() === '1';
    document.body.removeChild(probe);
    return ok;
  }
  function ensureStyles() {
    if (stylesApplied()) { document.documentElement.setAttribute('data-r4-cp-css', 'applied'); return; }
    if (document.querySelector('link[data-r4-cp-css-fallback]')) return;
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.setAttribute('data-r4-cp-css-fallback', '1');
    link.href = (SCRIPT_SRC ? SCRIPT_SRC.replace(/r4_color_picker\.js.*$/, 'r4_color_picker.css') : '/static/storefront_builder/r4_color_picker.css') + '?fb=' + Date.now();
    link.onload = function () { document.documentElement.setAttribute('data-r4-cp-css', 'loaded-by-script'); };
    document.head.appendChild(link);
    document.documentElement.setAttribute('data-r4-cp-css', 'missing');
  }

  // ---- the trigger (what the merchant sees in the Inspector) -------------------------------------------------
  function paintSwatch(swatch, state) {
    swatch.className = 'r4-cp-swatch';
    swatch.style.background = '';
    swatch.style.color = '';
    if (state.type === 'auto') { swatch.classList.add('is-auto'); return; }
    if (state.hex) { swatch.style.background = state.hex; swatch.style.color = inkFor(state.hex); }
    else swatch.classList.add('is-unknown');
  }

  function syncTrigger(entry) {
    var state = entry.adapter.read();
    var label = entry.adapter.label;
    paintSwatch(entry.swatch, state);
    entry.button.setAttribute('data-state', state.type);
    entry.name.textContent = state.type === 'custom' ? 'رنگ دلخواه' : state.name;
    entry.hex.textContent = state.hex || '';
    entry.hex.hidden = !state.hex;
    entry.button.disabled = entry.adapter.disabled();
    entry.button.setAttribute('aria-label',
      label + ': ' + (state.type === 'custom' ? 'رنگ دلخواه ' + (state.hex || '') : state.name) + (state.type === 'token' && state.hex ? ' (' + state.hex + ')' : '') + ' — برای تغییر، انتخابگر رنگ را باز کنید');
  }

  var entries = [];

  function enhance(host) {
    if (host.getAttribute('data-r4-cp')) return;
    var adapter = adapterOf(host);
    if (!adapter) return;
    host.setAttribute('data-r4-cp', '1');
    var button = el('button', 'r4-cp-trigger');
    button.type = 'button';
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-expanded', 'false');
    var swatch = el('span', 'r4-cp-swatch');
    swatch.setAttribute('aria-hidden', 'true');
    var text = el('span', 'r4-cp-text');
    var name = el('span', 'r4-cp-name');
    var hex = el('span', 'r4-cp-hex');
    hex.setAttribute('dir', 'ltr');
    text.appendChild(name); text.appendChild(hex);
    var caret = el('span', 'r4-cp-caret', '▾');
    caret.setAttribute('aria-hidden', 'true');
    button.appendChild(swatch); button.appendChild(text); button.appendChild(caret);
    var entry = { adapter: adapter, button: button, swatch: swatch, name: name, hex: hex, host: host };
    if (adapter.kind === 'semantic') {
      host.classList.add('r4-cp-ready');
      neutralise(host.querySelector('[data-r4-color-token]'));
      neutralise(host.querySelector('[data-r4-color-custom]'));
      host.insertBefore(button, host.firstChild);
    } else {
      host.classList.add('r4-cp-native');
      neutralise(host);
      host.insertAdjacentElement('afterend', button);
    }
    button.addEventListener('click', function (evt) {
      // the ONE way in: never let a click on the trigger also activate a native control (e.g. through a wrapping label)
      evt.preventDefault();
      openPicker(entry);
    });
    entries.push(entry);
    syncTrigger(entry);
  }

  function scan(root) {
    var scope = root || document;
    Array.prototype.forEach.call(scope.querySelectorAll('[data-r4-color-control]:not([data-r4-cp])'), enhance);
    Array.prototype.forEach.call(scope.querySelectorAll('.rs-studio input[type="color"]:not([data-r4-cp])'), function (input) {
      if (input.closest('[data-r4-color-control]')) return;
      enhance(input);
    });
    entries = entries.filter(function (e) { return document.documentElement.contains(e.host); });
  }

  // ---- the popover -------------------------------------------------------------------------------------------
  var open = null;

  function closePicker(restoreFocus) {
    if (!open) return;
    var state = open;
    open = null;
    document.removeEventListener('keydown', state.onKey, true);
    document.removeEventListener('pointerdown', state.onOutside, true);
    window.removeEventListener('resize', state.onReflow);
    window.removeEventListener('scroll', state.onReflow, true);
    if (state.pop.parentNode) state.pop.parentNode.removeChild(state.pop);
    state.entry.button.setAttribute('aria-expanded', 'false');
    if (restoreFocus !== false && document.documentElement.contains(state.entry.button)) state.entry.button.focus();
  }

  function openPicker(entry) {
    if (open && open.entry === entry) { closePicker(true); return; }
    closePicker(false);
    if (entry.adapter.disabled()) return;
    var adapter = entry.adapter;
    var current = adapter.read();
    var draftHex = current.hex || '';
    var hsv = rgbToHsv.apply(null, hexToRgb(draftHex || '#E11D48'));
    var dirty = false;

    ensureStyles();
    var pop = el('div', 'r4-cp');
    // Safety net: the layout-critical declarations travel with the element, so even a stale stylesheet can never leave the
    // popover unpositioned over the page (the full look comes from r4_color_picker.css).
    pop.style.cssText = 'position:fixed;z-index:2147483000;box-sizing:border-box;width:304px;max-width:calc(100vw - 16px);'
      + 'max-height:calc(100vh - 16px);max-height:calc(100dvh - 16px);overflow:auto;padding:10px;background:#fff;color:#252635;'
      + 'border:1px solid #e7e7ee;border-radius:14px;display:flex;flex-direction:column;gap:8px;font-size:12.5px;';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'انتخاب رنگ — ' + adapter.label);
    pop.setAttribute('dir', 'rtl');
    pop.tabIndex = -1;

    // current vs new
    var compare = el('div', 'r4-cp-compare');
    function chip(title) {
      var box = el('div', 'r4-cp-chip');
      var sw = el('span', 'r4-cp-swatch'); sw.setAttribute('aria-hidden', 'true');
      var txt = el('span', 'r4-cp-chip-text');
      txt.appendChild(el('small', null, title));
      var strong = el('strong');
      txt.appendChild(strong);
      box.appendChild(sw); box.appendChild(txt);
      return { box: box, sw: sw, strong: strong };
    }
    var chipNow = chip('فعلی'), chipNew = chip('جدید');
    chipNow.strong.setAttribute('dir', 'auto'); chipNew.strong.setAttribute('dir', 'ltr');
    paintSwatch(chipNow.sw, current);
    chipNow.strong.textContent = current.type === 'custom' ? (current.hex || '—') : current.name;
    compare.appendChild(chipNow.box); compare.appendChild(chipNew.box);
    pop.appendChild(compare);

    var swatchButtons = [];
    function swatchButton(hex, label, pressed, onPick) {
      var b = el('button', 'r4-cp-sw');
      b.type = 'button';
      b.style.background = hex;
      b.style.color = inkFor(hex);
      b.setAttribute('aria-label', label + ' ' + hex);
      b.setAttribute('aria-pressed', pressed ? 'true' : 'false');
      b.title = label + ' ' + hex;
      b.tabIndex = -1;
      b.addEventListener('click', onPick);
      swatchButtons.push(b);
      return b;
    }
    function applyAndClose(fn) { closePicker(true); fn(); syncTrigger(entry); }

    if (adapter.allowAuto) {
      var auto = el('button', 'r4-cp-auto' + (current.type === 'auto' ? ' is-current' : ''), 'خودکار (پیش‌فرض قالب)');
      auto.type = 'button';
      auto.setAttribute('aria-pressed', current.type === 'auto' ? 'true' : 'false');
      auto.addEventListener('click', function () { applyAndClose(function () { adapter.applyAuto(); }); });
      pop.appendChild(auto);
    }

    var paletteTokens = adapter.tokens.filter(function (t) { return t.hex; });
    if (paletteTokens.length) {
      var sec = el('section', 'r4-cp-sec');
      var h4 = el('h4', null, 'رنگ‌های پالت فروشگاه');
      h4.title = 'با تغییر پالت فروشگاه، این رنگ‌ها هم همراه می‌شوند.';
      sec.appendChild(h4);
      var grid = el('div', 'r4-cp-grid r4-cp-grid--palette');
      grid.setAttribute('role', 'group'); grid.setAttribute('aria-label', 'رنگ‌های پالت فروشگاه');
      paletteTokens.forEach(function (t) {
        grid.appendChild(swatchButton(t.hex, t.label, current.type === 'token' && current.value === t.value, function () {
          applyAndClose(function () { adapter.applyToken(t.value); });
        }));
      });
      sec.appendChild(grid);
      pop.appendChild(sec);
    }

    var sec2 = el('section', 'r4-cp-sec');
    sec2.appendChild(el('h4', null, 'رنگ‌های پیشنهادی'));
    var grid2 = el('div', 'r4-cp-grid');
    grid2.setAttribute('role', 'group'); grid2.setAttribute('aria-label', 'رنگ‌های پیشنهادی');
    NAMED.forEach(function (pair) {
      grid2.appendChild(swatchButton(pair[0], pair[1], current.type === 'custom' && current.hex === pair[0], function () {
        applyAndClose(function () { adapter.applyCustom(pair[0]); });
      }));
    });
    sec2.appendChild(grid2);
    pop.appendChild(sec2);

    // free colour
    var sec3 = el('section', 'r4-cp-sec');
    sec3.appendChild(el('h4', null, 'انتخاب آزاد رنگ'));
    var sv = el('div', 'r4-cp-sv');
    sv.tabIndex = 0;
    sv.setAttribute('role', 'slider');
    sv.setAttribute('aria-label', 'اشباع و روشنایی؛ با کلیدهای جهت‌دار تغییر می‌کند');
    sv.setAttribute('aria-valuemin', '0'); sv.setAttribute('aria-valuemax', '100');
    var svThumb = el('span', 'r4-cp-sv-thumb');
    svThumb.setAttribute('aria-hidden', 'true');
    sv.appendChild(svThumb);
    var hue = el('input', 'r4-cp-hue');
    hue.type = 'range'; hue.min = '0'; hue.max = '360'; hue.step = '1';
    hue.setAttribute('aria-label', 'گونهٔ رنگ'); hue.setAttribute('dir', 'ltr');
    var hexRow = el('div', 'r4-cp-hexrow');
    var hexLabel = el('label', 'r4-cp-hexlabel', 'کد رنگ (HEX)');
    var hexInput = el('input', 'r4-cp-hexinput');
    hexInput.type = 'text'; hexInput.maxLength = 9; hexInput.autocomplete = 'off'; hexInput.spellcheck = false;
    hexInput.setAttribute('dir', 'ltr'); hexInput.setAttribute('inputmode', 'text'); hexInput.placeholder = '#E11D48';
    var hexId = 'r4CpHex' + Math.random().toString(36).slice(2, 8);
    hexInput.id = hexId; hexLabel.setAttribute('for', hexId);
    var err = el('p', 'r4-cp-error', 'کد رنگ معتبر نیست؛ مثل #E11D48 (سه یا شش رقم هگزا).');
    err.id = hexId + 'Err'; err.setAttribute('role', 'alert'); err.hidden = true;
    hexInput.setAttribute('aria-describedby', err.id);
    hexRow.appendChild(hexLabel); hexRow.appendChild(hexInput);
    sec3.appendChild(sv); sec3.appendChild(hue); sec3.appendChild(hexRow); sec3.appendChild(err);
    pop.appendChild(sec3);

    var actions = el('div', 'r4-cp-actions');
    var apply = el('button', 'r4-cp-apply', 'اعمال رنگ'); apply.type = 'button';
    var cancel = el('button', 'r4-cp-cancel', 'انصراف'); cancel.type = 'button';
    actions.appendChild(apply); actions.appendChild(cancel);
    pop.appendChild(actions);

    var announce = el('p', 'visually-hidden');
    announce.setAttribute('aria-live', 'polite');
    pop.appendChild(announce);

    function renderDraft(fromHexField) {
      var valid = HEX6.test(draftHex);
      var hueBase = hsvToHex(hsv.h, 1, 1);
      sv.style.background = 'linear-gradient(to top,#000,rgba(0,0,0,0)),linear-gradient(to right,#fff,' + hueBase + ')';
      svThumb.style.left = (hsv.s * 100) + '%';
      svThumb.style.top = ((1 - hsv.v) * 100) + '%';
      svThumb.style.background = valid ? draftHex : '#fff';
      hue.value = String(Math.round(hsv.h));
      sv.setAttribute('aria-valuetext', 'اشباع ' + fa(Math.round(hsv.s * 100)) + ' درصد، روشنایی ' + fa(Math.round(hsv.v * 100)) + ' درصد');
      sv.setAttribute('aria-valuenow', String(Math.round(hsv.s * 100)));
      if (!fromHexField) hexInput.value = draftHex;
      if (dirty && valid) {
        paintSwatch(chipNew.sw, { type: 'custom', hex: draftHex });
        chipNew.strong.textContent = draftHex;
      } else {
        paintSwatch(chipNew.sw, { type: 'unknown' });
        chipNew.strong.textContent = '—';
      }
      apply.disabled = !(dirty && valid);
    }
    function setFromHsv() {
      draftHex = hsvToHex(hsv.h, hsv.s, hsv.v);
      dirty = true;
      err.hidden = true; hexInput.removeAttribute('aria-invalid');
      renderDraft(false);
    }

    // spectrum: pointer + keyboard
    function svFromPointer(evt) {
      var r = sv.getBoundingClientRect();
      hsv.s = Math.max(0, Math.min(1, (evt.clientX - r.left) / r.width));
      hsv.v = Math.max(0, Math.min(1, 1 - (evt.clientY - r.top) / r.height));
      setFromHsv();
    }
    sv.addEventListener('pointerdown', function (evt) {
      sv.setPointerCapture && sv.setPointerCapture(evt.pointerId);
      sv.focus();
      svFromPointer(evt);
      function move(e) { svFromPointer(e); }
      function up() { sv.removeEventListener('pointermove', move); sv.removeEventListener('pointerup', up); sv.removeEventListener('pointercancel', up); }
      sv.addEventListener('pointermove', move); sv.addEventListener('pointerup', up); sv.addEventListener('pointercancel', up);
      evt.preventDefault();
    });
    sv.addEventListener('keydown', function (evt) {
      var step = evt.shiftKey ? 0.1 : 0.02, used = true;
      if (evt.key === 'ArrowLeft') hsv.s = Math.max(0, hsv.s - step);
      else if (evt.key === 'ArrowRight') hsv.s = Math.min(1, hsv.s + step);
      else if (evt.key === 'ArrowUp') hsv.v = Math.min(1, hsv.v + step);
      else if (evt.key === 'ArrowDown') hsv.v = Math.max(0, hsv.v - step);
      else used = false;
      if (used) { evt.preventDefault(); setFromHsv(); }
    });
    hue.addEventListener('input', function () { hsv.h = Number(hue.value) || 0; if (hsv.s === 0) hsv.s = 0.01; setFromHsv(); });

    // HEX field: validated in place, never dispatched until applied
    hexInput.addEventListener('input', function () {
      var raw = hexInput.value.trim();
      var parsed = normHex(raw);
      dirty = true;
      if (parsed) {
        draftHex = parsed;
        var c = rgbToHsv.apply(null, hexToRgb(parsed));
        hsv = { h: c.s === 0 ? hsv.h : c.h, s: c.s, v: c.v };
        err.hidden = true; hexInput.removeAttribute('aria-invalid');
      } else {
        draftHex = '';
        // still typing valid hex characters (fewer than 6): no scolding yet — the error shows on blur / Enter
        var typing = /^#?[0-9a-f\u06F0-\u06F9\u0660-\u0669]{0,5}$/i.test(raw);
        err.hidden = typing;
        if (raw !== '') hexInput.setAttribute('aria-invalid', 'true');
      }
      renderDraft(true);
    });
    hexInput.addEventListener('blur', function () {
      var raw = hexInput.value.trim();
      if (raw !== '' && !normHex(raw)) { err.hidden = false; hexInput.setAttribute('aria-invalid', 'true'); }
    });
    hexInput.addEventListener('keydown', function (evt) {
      if (evt.key === 'Enter') {
        evt.preventDefault();
        if (!normHex(hexInput.value)) { err.hidden = false; hexInput.setAttribute('aria-invalid', 'true'); return; }
        apply.click();
      }
    });

    apply.addEventListener('click', function () {
      if (apply.disabled || !HEX6.test(draftHex)) return;
      var chosen = draftHex;
      applyAndClose(function () { adapter.applyCustom(chosen); });
    });
    cancel.addEventListener('click', function () { closePicker(true); });

    // roving focus across swatch buttons (arrows), first one tabbable
    var firstPressed = swatchButtons.filter(function (b) { return b.getAttribute('aria-pressed') === 'true'; })[0];
    (firstPressed || swatchButtons[0]).tabIndex = 0;
    pop.addEventListener('keydown', function (evt) {
      var idx = swatchButtons.indexOf(document.activeElement);
      if (idx === -1) return;
      var move = 0;
      var rtl = true;
      if (evt.key === 'ArrowRight') move = rtl ? -1 : 1;
      else if (evt.key === 'ArrowLeft') move = rtl ? 1 : -1;
      else if (evt.key === 'ArrowDown') move = 8;
      else if (evt.key === 'ArrowUp') move = -8;
      else return;
      var next = swatchButtons[idx + move];
      if (!next) return;
      evt.preventDefault();
      swatchButtons.forEach(function (b) { b.tabIndex = -1; });
      next.tabIndex = 0; next.focus();
    });

    // mount + position
    var mountPoint = entry.button.closest('[role="dialog"]') || entry.button.closest('.rs-studio') || document.body;
    mountPoint.appendChild(pop);
    entry.button.setAttribute('aria-expanded', 'true');

    function place() {
      if (!open || open.pop !== pop) return;
      var vw = window.innerWidth, vh = window.innerHeight;
      if (vw <= 600) {
        pop.classList.add('is-sheet');
        pop.style.left = '8px'; pop.style.right = '8px'; pop.style.top = 'auto'; pop.style.bottom = '8px';
        pop.style.width = 'auto'; pop.style.maxHeight = '82vh'; pop.style.maxHeight = '82dvh';
        return;
      }
      pop.classList.remove('is-sheet');
      pop.style.right = 'auto'; pop.style.bottom = 'auto'; pop.style.width = '304px';
      pop.style.maxHeight = 'calc(100vh - 16px)'; pop.style.maxHeight = 'calc(100dvh - 16px)';
      var rect = entry.button.getBoundingClientRect();
      var w = pop.offsetWidth, h = pop.offsetHeight;
      var left = document.documentElement.dir === 'ltr' ? rect.left : rect.right - w;
      left = Math.max(8, Math.min(left, vw - w - 8));
      var top = rect.bottom + 6;
      if (top + h > vh - 8) top = Math.max(8, rect.top - 6 - h);
      if (top + h > vh - 8) top = Math.max(8, vh - 8 - h);
      pop.style.left = left + 'px';
      pop.style.top = top + 'px';
    }

    function onKey(evt) {
      if (evt.key === 'Escape') {
        evt.preventDefault(); evt.stopPropagation(); evt.stopImmediatePropagation();
        closePicker(true);
        return;
      }
      if (evt.key !== 'Tab') return;
      var focusable = Array.prototype.filter.call(
        pop.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="0"]'),
        function (n) { return n.tabIndex >= 0 && n.getClientRects().length > 0; });
      if (!focusable.length) return;
      var first = focusable[0], last = focusable[focusable.length - 1];
      var inside = pop.contains(document.activeElement);
      evt.stopPropagation();
      if (!inside) { evt.preventDefault(); first.focus(); return; }
      if (evt.shiftKey && document.activeElement === first) { evt.preventDefault(); last.focus(); }
      else if (!evt.shiftKey && document.activeElement === last) { evt.preventDefault(); first.focus(); }
    }
    function onOutside(evt) {
      if (pop.contains(evt.target) || entry.button.contains(evt.target)) return;
      closePicker(false);
    }
    open = { pop: pop, entry: entry, onKey: onKey, onOutside: onOutside, onReflow: place };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onOutside, true);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    renderDraft(false);
    place();
    // initial focus: the current swatch (or the HEX field when the colour is custom and not in the grids)
    var target = firstPressed || (adapter.allowAuto && current.type === 'auto' ? pop.querySelector('.r4-cp-auto') : null) || swatchButtons[0] || hexInput;
    target.focus();
  }

  // A <label for=…> pointing at a (hidden) native colour input would still activate it and open the OS dialog. Clicks that
  // would reach a neutralised native control are cancelled; a label click opens the shared picker instead.
  document.addEventListener('click', function (evt) {
    var target = evt.target;
    if (!target || !target.closest) return;
    var native = target.closest('[data-r4-cp-native]');
    if (native) { evt.preventDefault(); return; }
    var label = target.closest('label');
    if (!label) return;
    var control = label.control || (label.htmlFor ? document.getElementById(label.htmlFor) : null);
    if (!control || !control.hasAttribute || !control.hasAttribute('data-r4-cp-native')) return;
    evt.preventDefault();
    var owner = entries.filter(function (e) { return e.host === control || e.host.contains(control); })[0];
    if (owner && !owner.button.disabled) openPicker(owner);
  }, true);

  // keep the triggers honest when a value is changed by anything else (undo, reset, hydration …)
  document.addEventListener('change', function (evt) {
    entries.forEach(function (entry) {
      if (entry.host === evt.target || entry.host.contains(evt.target)) syncTrigger(entry);
    });
  });

  function start() {
    ensureStyles();
    scan(document);
    var queued = false;
    new MutationObserver(function () {
      if (queued) return;
      queued = true;
      (window.requestAnimationFrame || setTimeout)(function () {
        queued = false;
        scan(document);
        entries.forEach(syncTrigger);
      });
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();

  window.RastiSiColorPicker = { normHex: normHex, scan: scan, ensureStyles: ensureStyles, close: function () { closePicker(false); } };
})();
