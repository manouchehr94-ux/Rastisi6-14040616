/* RastiSi Vision Studio — shell controller (presentation only).
 *
 * Vision is a second PRESENTATION of the one R4 Studio session. Every operation still belongs to the existing owners:
 *   r4_editor.js  (window.RastiSiR4: mutation queue, history, publish, Preview, Inspector, Global Design)
 *   r4_studio.js  (UI state, dialogs, toasts; R4.studio)
 * This file only decides WHICH pane / dialog category is visible, dresses real R4 controls (switch wording, palette cards, Persian option
 * labels) and routes a few Vision-only buttons to those owners. It never sends a request, never stores design data and never keeps state
 * beyond the current tab / open category / open menu (in memory).
 */
(function () {
  'use strict';
  var root = document.querySelector('.rs-studio.vs[data-r4-shell]');
  var R4 = window.RastiSiR4;
  if (!root || !R4) return;

  function $(selector, scope) { return (scope || root).querySelector(selector); }
  function $all(selector, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(selector)); }
  function faDigits(text) { return String(text).replace(/[0-9]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.charAt(Number(d)); }); }
  function readJson(id) {
    var el = document.getElementById(id);
    try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
  }
  function later(fn, ms) { return window.setTimeout(fn, ms || 0); }

  // ---- studio menu ---------------------------------------------------------
  var menu = $('[data-vs-menu]');
  var menuButton = menu && $('#vsMenuButton', menu);
  var menuList = menu && $('#vsMenuList', menu);
  function setMenu(open) {
    if (!menu) return;
    menuList.hidden = !open;
    menuButton.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      var first = menuList.querySelector('[role="menuitem"]');
      if (first) first.focus({ preventScroll: true });
    }
  }
  if (menu) {
    menuButton.addEventListener('click', function () { setMenu(menuList.hidden); });
    menuList.addEventListener('click', function (evt) { if (evt.target.closest('[role="menuitem"]')) setMenu(false); });
    document.addEventListener('click', function (evt) { if (!menuList.hidden && !menu.contains(evt.target)) setMenu(false); });
    document.addEventListener('keydown', function (evt) {
      if (evt.key === 'Escape' && !menuList.hidden) { setMenu(false); menuButton.focus(); }
      if (!menuList.hidden && (evt.key === 'ArrowDown' || evt.key === 'ArrowUp')) {
        var items = $all('[role="menuitem"]', menuList);
        var at = items.indexOf(document.activeElement);
        evt.preventDefault();
        items[(at + (evt.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length].focus();
      }
    });
  }

  // ---- properties panel tabs -----------------------------------------------
  var tabButtons = $all('[data-vs-tab-button]');
  var panes = $all('[data-vs-pane]');
  function setActiveTab(name) {
    root.dataset.vsTab = name;
    tabButtons.forEach(function (b) {
      var on = b.getAttribute('data-vs-tab-button') === name;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    panes.forEach(function (p) { p.hidden = p.getAttribute('data-vs-pane') !== name; });
  }
  tabButtons.forEach(function (b) {
    b.addEventListener('click', function () { setActiveTab(b.getAttribute('data-vs-tab-button')); });
    b.addEventListener('keydown', function (evt) {
      var at = tabButtons.indexOf(b);
      var next = evt.key === 'ArrowLeft' ? at + 1 : evt.key === 'ArrowRight' ? at - 1 : null;   // RTL: left = next
      if (next == null) return;
      evt.preventDefault();
      var target = tabButtons[(next + tabButtons.length) % tabButtons.length];
      target.focus();
      setActiveTab(target.getAttribute('data-vs-tab-button'));
    });
  });

  // ---- save state, mirrored into the dialogs' headers -------------------------------
  var saveFeedback = $('[data-rs-save-feedback]');
  function saveState() { return R4.saveState || 'saved'; }
  function mirrorSaveState() {
    var state = saveState();
    $all('[data-vs-modal-status]').forEach(function (box) {
      box.dataset.state = state;
      box.innerHTML = saveFeedback ? saveFeedback.innerHTML : '';
    });
  }
  if (saveFeedback && window.MutationObserver) {
    new MutationObserver(mirrorSaveState).observe(saveFeedback, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  }
  root.addEventListener('r4:savestate', function () { later(mirrorSaveState, 0); });
  mirrorSaveState();

  // closing a dialog must never drop a change silently: an error / conflict keeps the dialog open and says why; a write still in flight is
  // awaited first (R4 keeps writing after a close, but the seller should see it finish)
  var bypassGuard = false;
  function reportUnsaved() {
    var again = $('[data-rs-save-feedback] [data-rastisi-action="save-issue"]');
    if (again) again.click();
    $all('[data-vs-modal-status], .vs-workspace .r4-ws-save').forEach(function (box) {
      box.classList.add('is-shaking');
      later(function () { box.classList.remove('is-shaking'); }, 600);
    });
  }
  function guardClose(evt, proceed) {
    if (bypassGuard) return false;
    var state = saveState();
    if (state === 'error' || state === 'conflict') {
      evt.preventDefault();
      evt.stopImmediatePropagation();
      reportUnsaved();
      return true;
    }
    if (state === 'saving' || R4.pendingWrites > 0) {
      evt.preventDefault();
      evt.stopImmediatePropagation();
      var started = Date.now();
      (function wait() {
        var now = saveState();
        if (now === 'saved' && !(R4.pendingWrites > 0)) { bypassGuard = true; try { proceed(); } finally { bypassGuard = false; } return; }
        if (now === 'error' || now === 'conflict' || Date.now() - started > 8000) { reportUnsaved(); return; }
        later(wait, 150);
      }());
      return true;
    }
    return false;
  }

  // ---- navigator -----------------------------------------------------------
  var pageSelect = document.getElementById('r4PageSwitcherSelect');
  $all('[data-vs-page]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var value = btn.getAttribute('data-vs-page');
      if (!pageSelect || pageSelect.value === value) return;
      pageSelect.value = value;
      pageSelect.dispatchEvent(new Event('change', { bubbles: true }));   // r4_studio.js navigates (keeps ?page=, asks first inside the Design Lab)
    });
  });

  // a section row selects the section AND opens its settings (a canvas click only selects: the Composer toolbar has «ویرایش»)
  var lastOpener = null;
  root.addEventListener('click', function (evt) {
    var select = evt.target.closest('[data-rastisi-action="row-select"]');
    if (!select) return;
    var row = select.closest('[data-r4-structure-row]');
    var id = row && Number(row.getAttribute('data-r4-structure-section-id'));
    if (!id) return;
    lastOpener = select;
    evt.stopImmediatePropagation();
    if (R4.studio && R4.studio.edit) R4.studio.edit(id);
  }, true);

  // ---- section settings dialog -------------------------------------------------
  function closeInspectorGuarded(evt) {
    var trigger = evt.target.closest('[data-r4-inspector-close], [data-rastisi-action="workspace-backdrop"]');
    if (!trigger || !R4.inspectorOpen) return;
    guardClose(evt, function () { R4.closeInspector(); });
  }
  root.addEventListener('click', closeInspectorGuarded, true);
  document.addEventListener('keydown', function (evt) {
    if (evt.key !== 'Escape') return;
    if (vpOpen()) { evt.stopPropagation(); closePreview(); return; }
    if (R4.inspectorOpen && !$('.vs-workspace').hidden) guardClose(evt, function () { R4.closeInspector(); });
    else if (!$('.vs-dlayer').hidden && root.dataset.rsDrawer === 'global') guardClose(evt, closeDesignDialog);
  }, true);

  // each titled card of a settings form is collapsible (presentation only; the form values stay in the DOM)
  function enhanceInspector() {
    var inspector = document.getElementById('r4Inspector');
    if (!inspector) return;
    $all('.r4-ws-card', inspector).forEach(function (card) {
      var head = card.querySelector('.r4-ws-card-head');
      if (!head || head.dataset.vsBound) return;
      head.dataset.vsBound = '1';
      head.setAttribute('role', 'button');
      head.tabIndex = 0;
      head.setAttribute('aria-expanded', 'true');
      function toggle() {
        var collapsed = card.classList.toggle('is-collapsed');
        head.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      }
      head.addEventListener('click', toggle);
      head.addEventListener('keydown', function (evt) {
        if (evt.key === 'Enter' || evt.key === ' ') { evt.preventDefault(); toggle(); }
      });
    });
    enhanceSwitches(inspector);
    // «ذخیره خودکار» says where: in the Draft, not on the live store
    $all('.r4-ws-footnote', inspector).forEach(function (note) {
      Array.prototype.forEach.call(note.childNodes, function (node) {
        if (node.nodeType === 3 && node.textContent.trim()) node.textContent = 'تغییرات خودکار در پیش‌نویس ذخیره می‌شوند؛ تا «انتشار» نزنید فروشگاه عمومی تغییر نمی‌کند.';
      });
    });
  }
  function markOpenRow() {
    var id = R4.inspectorOpen ? String(R4.selected) : null;
    $all('[data-r4-structure-row]').forEach(function (row) {
      row.classList.toggle('is-open', id !== null && row.getAttribute('data-r4-structure-section-id') === id);
    });
  }
  root.addEventListener('r4:inspector-opened', function () { enhanceInspector(); later(enhanceInspector, 0); markOpenRow(); mirrorSaveState(); });
  root.addEventListener('r4:inspector-closed', function () {
    markOpenRow();
    // r4_studio.js returns focus to its own top-bar button, which Vision does not have: give it back to what opened the dialog
    later(function () {
      var target = lastOpener && document.contains(lastOpener) && lastOpener.getClientRects().length ? lastOpener : $('.tree-row .rs-row-select');
      if (target && (!document.activeElement || document.activeElement === document.body)) target.focus({ preventScroll: true });
    }, 60);
  });
  root.addEventListener('r4:structure-refreshed', markOpenRow);
  var inspectorHost = document.getElementById('r4Inspector');
  if (inspectorHost && window.MutationObserver) {
    new MutationObserver(function () { enhanceInspector(); }).observe(inspectorHost, { childList: true });
  }

  // ---- switches: one meaning per control, decided by the REAL field key -------------------------
  // R4 owns the value: its checkbox (or aria-pressed button) is what R4 reads and writes, and it is never replaced. Vision only decides how that
  // value is SHOWN. A control's identity comes from the attributes R4 itself uses (data-r4-global-field / -responsive-prop / data-r4-field-key /
  // data-rastisi-action), never from its label text. Fields stored as "hidden" (hide_on_tablet, hide_on_mobile - the vsUx rule: key starts with
  // «hide_») are shown INVERTED, as «visible»: stored false => ON / green / «نمایش داده می‌شود», stored true => OFF / grey / «پنهان است».
  // An inverted switch gets a real role="switch" proxy button whose aria-checked is the shown state; a click on it clicks R4's checkbox, so the
  // ordinary R4 change handler (the same mutation, Revision and History) does the saving. Nothing is stored by Vision.
  var UX = readJson('vsUx') || { settings: {}, responsive: {}, inverted_prefixes: ['hide_'] };
  function isInvertedKey(key) {
    return (UX.inverted_prefixes || []).some(function (prefix) { return key.indexOf(prefix) === 0; });
  }
  function switchSpec(ctl) {
    var prop = ctl.getAttribute('data-r4-global-responsive-prop');
    if (prop) {
      var resp = (UX.responsive || {})[prop] || {};
      return { key: prop, group: ctl.getAttribute('data-r4-global-responsive-key') || '', inverted: isInvertedKey(prop), kind: 'visibility', title: resp.title || '', device: resp.device || '' };
    }
    var key = ctl.getAttribute('data-r4-global-field') || ctl.getAttribute('data-r4-field-key') || ctl.getAttribute('data-r4-repeater-subfield');
    if (key) {
      var copy = (UX.settings || {})[key];
      return { key: key, inverted: isInvertedKey(key), kind: /^(show_|visible_)/.test(key) ? 'visibility' : 'toggle', title: copy ? copy.title : '' };
    }
    var action = ctl.getAttribute('data-rastisi-action');
    if (action === 'section-enable') return { key: 'is_active', inverted: false, kind: 'visibility', title: '' };
    if (action === 'section-lock') return { key: 'locked', inverted: false, kind: 'lock', title: '' };
    return { key: '', inverted: false, kind: 'toggle', title: '' };
  }
  var SWITCH_WORDS = {
    visibility: ['نمایش داده می‌شود', 'پنهان است'],
    lock: ['قفل است', 'باز است'],
    toggle: ['روشن', 'خاموش']
  };
  function storedValue(ctl) { return ctl.tagName === 'INPUT' ? ctl.checked : ctl.getAttribute('aria-pressed') === 'true'; }
  function shownValue(ctl) { return ctl.__vsSpec && ctl.__vsSpec.inverted ? !storedValue(ctl) : storedValue(ctl); }
  function paintSwitch(ctl) {
    var text = ctl.__vsText;
    var spec = ctl.__vsSpec;
    if (!text || !spec) return;
    var on = shownValue(ctl);
    var disabled = !!ctl.disabled;
    text.dataset.on = on ? 'true' : 'false';
    text.dataset.disabled = disabled ? 'true' : 'false';
    text.textContent = disabled ? 'غیرفعال' : (SWITCH_WORDS[spec.kind] || SWITCH_WORDS.toggle)[on ? 0 : 1];
    ctl.dataset.vsShown = on ? 'on' : 'off';           // what the seller sees (tests read this; R4 never does)
    var proxy = ctl.__vsProxy;
    if (proxy) {
      proxy.setAttribute('aria-checked', on ? 'true' : 'false');
      proxy.dataset.on = on ? 'true' : 'false';
      proxy.disabled = disabled;
    }
  }
  function buildSwitch(ctl) {
    var spec = switchSpec(ctl);
    ctl.__vsSpec = spec;
    var text = document.createElement('span');
    text.className = 'vs-sw-text';
    text.setAttribute('aria-hidden', 'true');
    var after = ctl;
    if (spec.inverted && ctl.tagName === 'INPUT') {
      var proxy = document.createElement('button');
      proxy.type = 'button';
      proxy.className = 'vs-sw';
      proxy.setAttribute('role', 'switch');
      proxy.setAttribute('aria-label', spec.title || 'نمایش');
      proxy.addEventListener('click', function () { if (!ctl.disabled) ctl.click(); });
      ctl.classList.add('vs-sw-native');
      ctl.tabIndex = -1;
      ctl.setAttribute('aria-hidden', 'true');
      ctl.insertAdjacentElement('afterend', proxy);
      ctl.__vsProxy = proxy;
      after = proxy;
    } else if (ctl.tagName === 'INPUT') {
      ctl.setAttribute('role', 'switch');
    }
    after.insertAdjacentElement('afterend', text);
    ctl.__vsText = text;
    // the visible name: the plain-language title of the real key (the original wording is kept in data-vs-orig)
    var wrap = ctl.closest('label.r4-checkbox-row');
    var nameNode = wrap && wrap.querySelector('span:not(.vs-sw-text)');
    if (nameNode && spec.title) {
      if (!nameNode.dataset.vsOrig) nameNode.dataset.vsOrig = nameNode.textContent;
      nameNode.textContent = spec.title;
    }
    if (ctl.tagName === 'INPUT') ctl.addEventListener('change', function () { paintSwitch(ctl); });
    else if (window.MutationObserver) new MutationObserver(function () { paintSwitch(ctl); }).observe(ctl, { attributes: true, attributeFilter: ['aria-pressed', 'disabled'] });
    if (window.MutationObserver && ctl.tagName === 'INPUT') new MutationObserver(function () { paintSwitch(ctl); }).observe(ctl, { attributes: true, attributeFilter: ['disabled', 'checked'] });
  }
  function enhanceSwitches(scope) {
    $all('input.r4-switch, button.switch', scope || root).forEach(function (ctl) {
      if (ctl.closest('template')) return;
      if (!ctl.__vsText) buildSwitch(ctl);
      paintSwitch(ctl);
    });
  }
  // a click on a button switch is repainted after R4 has toggled aria-pressed
  document.addEventListener('click', function (evt) {
    var btn = evt.target.closest && evt.target.closest('button.switch');
    if (btn) later(function () { paintSwitch(btn); }, 30);
  });

  // ---- Global Design: a list of categories, each a large dialog over the real panel ------------------
  var gd = function () { return document.getElementById('r4GlobalDesign'); };
  var proxyGlobal = $('[data-vs-proxy="global"]');
  var designLayer = $('.vs-dlayer');
  var designModal = $('[data-vs-design-modal]');
  var palettes = {};
  (readJson('vsPalettes') || []).forEach(function (p) { palettes[p.slug] = p; });

  var CATS = {
    colors: { title: 'برند و رنگ‌ها', palette: true },
    typography: { title: 'نوع نوشته و فونت‌ها' },
    buttons: { title: 'دکمه‌ها' },
    shape: { title: 'شکل و تراکم' },
    images: { title: 'تصاویر و رسانه‌ها' },
    motion: { title: 'حرکت و افکت‌ها' },
    header: { title: 'سربرگ (هدر)', region: 'rsGlobalHeader' },
    footer: { title: 'پابرگ (فوتر)', region: 'rsGlobalFooter' },
    bottom_nav: { title: 'ناوبری موبایل', region: 'rsGlobalMobileNav' },
    theme: { title: 'تم مناسبتی', tab: 'theme' }
  };
  // which dialog category each real appearance field belongs to (a field can serve two: «motion» and «shape» share the card hover)
  var FIELD_CAT = {
    palette_slug: 'colors', color_overrides: 'colors', theme_overrides: 'colors',
    font: 'typography', type_scale: 'typography', heading_style: 'typography',
    button_style: 'buttons', button_radius: 'buttons',
    radius: 'shape', density: 'shape', content_width: 'shape', grid_density: 'shape', card_shadow: 'shape', hero_style: 'shape',
    template_slug: 'shape', card_hover: 'shape motion',
    image_fit: 'images', image_hover: 'images motion', card_image_crossfade: 'images', card_image_zoom: 'images',
    motion: 'motion'
  };
  // the partial prints some raw registry values; the seller reads Persian (the option VALUES are untouched)
  var OPTION_FA = {
    motion: { none: 'بدون حرکت', subtle: 'ملایم', dynamic: 'پویا' },
    button_style: { filled: 'توپر', soft: 'نرم', outline: 'دورخط' },
    density: { compact: 'فشرده', normal: 'معمولی', relaxed: 'باز' },
    image_fit: { cover: 'پر کردن قاب', contain: 'نمایش کامل تصویر' },
    image_hover: { none: 'بدون افکت', zoom: 'بزرگ‌نمایی' },
    card_shadow: { none: 'بدون سایه', soft: 'سایهٔ ملایم', strong: 'سایهٔ پررنگ' },
    card_hover: { none: 'بدون افکت', lift: 'بلند شدن', zoom: 'بزرگ‌نمایی' },
    hero_style: { wide: 'عریض', tall: 'بلند', split: 'دوبخشی' }
  };
  var currentCat = null;
  // the dialog role exists only while the dialog is open (a closed, hidden layer must not be a dialog to assistive tech, nor to scripts that look for the open one)
  function setDialogRole(open) {
    if (!designModal) return;
    if (open) { designModal.setAttribute('role', 'dialog'); designModal.setAttribute('aria-modal', 'true'); }
    else { designModal.removeAttribute('role'); designModal.removeAttribute('aria-modal'); }
  }

  function fieldKeyOf(node) {
    var ctl = node.matches('[data-r4-global-field]') ? node : node.querySelector('[data-r4-global-field]');
    return ctl ? ctl.getAttribute('data-r4-global-field') : null;
  }
  function relabelOptions() {
    $all('#r4GlobalDesign select[data-r4-global-field]').forEach(function (select) {
      var map = OPTION_FA[select.getAttribute('data-r4-global-field')];
      if (!map) return;
      $all('option', select).forEach(function (opt) {
        if (map[opt.value] && opt.textContent.trim() === opt.value) opt.textContent = map[opt.value];
      });
    });
  }
  // tag every piece of the (flat) panel with the category it belongs to; the DOM keeps its R4 shape and ids
  function tagCategories() {
    var panel = gd();
    var group = panel && panel.querySelector('[data-rs-tab-pane="visual"] > .r4-global-design-group');
    if (!group) return;
    var last = null;
    Array.prototype.forEach.call(group.children, function (node) {
      if (node.id === 'rsGlobalDetails') {
        var body = node.querySelector('.rs-more-body');
        var cat = null;
        Array.prototype.forEach.call(body ? body.children : [], function (item) {
          if (item.matches('label.r4-field-sublabel')) {
            var control = document.getElementById(item.getAttribute('for'));
            var key = control && control.getAttribute('data-r4-global-field');
            if (key && FIELD_CAT[key]) cat = FIELD_CAT[key];
          } else if (item.matches('h5')) {
            cat = 'colors';
          } else {
            var own = fieldKeyOf(item);
            if (own && FIELD_CAT[own]) cat = FIELD_CAT[own];
          }
          item.dataset.vsCat = cat || '';
        });
        return;
      }
      var key = fieldKeyOf(node) || (node.matches('[data-r4-global-reset-field]') ? node.getAttribute('data-r4-global-reset-field') : null);
      var kind = key && FIELD_CAT[key];
      if (!kind && node.matches('.section-label')) kind = /پالت/.test(node.textContent) ? 'colors' : /بسته/.test(node.textContent) ? 'shape' : last;
      if (!kind && node.matches('.section-divider, .visually-hidden')) { node.dataset.vsCat = ''; return; }
      kind = kind || last;
      node.dataset.vsCat = kind || '';
      if (kind) last = kind;
    });
  }
  function clearCategory() {
    delete root.dataset.vsCat;
    currentCat = null;
    setDialogRole(false);
    $all('#r4GlobalDesign .vs-hide, #r4GlobalDesign .vs-flat, #r4GlobalDesign .vs-cat-target').forEach(function (el) {
      el.classList.remove('vs-hide', 'vs-flat', 'vs-cat-target');
    });
    var tools = $('[data-vs-palette-tools]');
    if (tools) tools.hidden = true;
  }
  function applyCategory(cat) {
    var info = CATS[cat];
    var panel = gd();
    if (!info || !panel) return;
    $all('.vs-hide, .vs-flat, .vs-cat-target', panel).forEach(function (el) { el.classList.remove('vs-hide', 'vs-flat', 'vs-cat-target'); });
    root.dataset.vsCat = cat;
    currentCat = cat;
    var tools = $('[data-vs-palette-tools]');
    if (tools) tools.hidden = !info.palette;
    if (info.region) {
      var target = document.getElementById(info.region);
      if (target) { target.classList.add('vs-cat-target'); target.open = true; }
      return;
    }
    if (info.tab) return;
    var group = panel.querySelector('[data-rs-tab-pane="visual"] > .r4-global-design-group');
    if (!group) return;
    var details = document.getElementById('rsGlobalDetails');
    var items = Array.prototype.slice.call(group.children).filter(function (n) { return n !== details; });
    if (details) {
      items = items.concat(Array.prototype.slice.call((details.querySelector('.rs-more-body') || { children: [] }).children));
      details.open = true;
      details.classList.add('vs-flat');
    }
    items.forEach(function (node) {
      var tokens = (node.dataset.vsCat || '').split(' ');
      node.classList.toggle('vs-hide', tokens.indexOf(cat) === -1);
    });
    // the palette / style-pack lists that R4 folds under «همه …» are shown in full inside their category
    $all('details.rs-more-choices', group).forEach(function (more) {
      var tokens = (more.dataset.vsCat || '').split(' ');
      if (tokens.indexOf(cat) !== -1) { more.open = true; more.classList.add('vs-flat'); }
    });
  }

  // palette cards: the registry's own colours (primary, secondary, accent, background, surface, text) in a swatch strip + a tiny mock
  function enhancePalettes() {
    $all('#r4GlobalDesign label.swatch').forEach(function (label) {
      if (label.querySelector('.vs-pal')) return;
      var input = label.querySelector('input[data-r4-global-field="palette_slug"]');
      var data = input && palettes[input.value];
      if (!data || !data.swatches) return;
      var c = data.swatches;
      var pal = document.createElement('span');
      pal.className = 'vs-pal';
      pal.setAttribute('aria-hidden', 'true');
      pal.innerHTML = '<span class="vs-pal__bar">' + c.map(function (color) { return '<i style="background:' + color + '"></i>'; }).join('') + '</span>' +
        '<span class="vs-pal__mock" style="background:' + c[3] + ';color:' + c[5] + '"><b>Aa</b><em style="background:' + c[0] + '"></em></span>';
      label.insertBefore(pal, label.firstChild);
      label.dataset.vsName = (data.label_fa || '').toLowerCase();
    });
  }
  var paletteSearch = $('[data-vs-palette-search]');
  var paletteCount = $('[data-vs-palette-count]');
  function filterPalettes() {
    var q = paletteSearch ? paletteSearch.value.trim().toLowerCase() : '';
    var shown = 0;
    $all('#r4GlobalDesign label.swatch').forEach(function (label) {
      var hit = !q || (label.dataset.vsName || label.title || '').toLowerCase().indexOf(q) !== -1;
      label.classList.toggle('vs-filtered-out', !hit);
      if (hit) shown += 1;
    });
    if (paletteCount) paletteCount.textContent = faDigits(shown) + ' پالت';
  }
  if (paletteSearch) paletteSearch.addEventListener('input', filterPalettes);

  // the list's summaries read the real controls
  function optionText(select) { return select && select.selectedOptions && select.selectedOptions[0] ? select.selectedOptions[0].textContent.trim() : ''; }
  function ctl(key) { return document.querySelector('#r4GlobalDesign [data-r4-global-field="' + key + '"]'); }
  function setSummary(cat, text) {
    var el = $('[data-vs-summary="' + cat + '"]');
    if (el && text) el.textContent = text;
  }
  function updateSummaries() {
    var checked = document.querySelector('#r4GlobalDesign input[data-r4-global-field="palette_slug"]:checked');
    var pal = checked && palettes[checked.value];
    if (pal) {
      setSummary('colors', 'پالت «' + pal.label_fa + '»');
      var strip = $('[data-vs-strip]');
      if (strip) strip.innerHTML = pal.swatches.slice(0, 5).map(function (c) { return '<i style="background:' + c + '"></i>'; }).join('');
    }
    var font = optionText(ctl('font'));
    var scale = optionText(ctl('type_scale'));
    if (font) setSummary('typography', font + (scale ? ' · ' + scale : ''));
    var buttonStyle = optionText(ctl('button_style'));
    var buttonRadius = ctl('button_radius');
    if (buttonStyle) setSummary('buttons', buttonStyle + (buttonRadius && buttonRadius.value !== '' ? ' · گردی ' + faDigits(buttonRadius.value) : ''));
    var radius = ctl('radius');
    var density = optionText(ctl('density'));
    if (density) setSummary('shape', (radius && radius.value !== '' ? 'گردی ' + faDigits(radius.value) + ' · ' : '') + 'تراکم ' + density);
    var fit = optionText(ctl('image_fit'));
    if (fit) setSummary('images', fit);
    [['header', 'r4GlobalHeaderVariant'], ['footer', 'r4GlobalFooterVariant'], ['bottom_nav', 'r4GlobalMobileNavVariant']].forEach(function (pair) {
      var text = optionText(document.getElementById(pair[1]));
      if (text) setSummary(pair[0], 'مدل: ' + text);
    });
  }
  function refreshDesign() {
    relabelOptions();
    tagCategories();
    enhancePalettes();
    enhanceSwitches(gd());
    enhanceClarity();
    enhanceGalleries();
    renameRegions();
    updateSummaries();
    if (currentCat) { applyCategory(currentCat); filterPalettes(); }
  }

  function openCategory(cat) {
    var info = CATS[cat];
    if (!info) return;
    if (!R4.isGlobalDesignOpen() && proxyGlobal) proxyGlobal.click();   // the one Studio mode switch (r4_studio.js): shows the dialog layer
    var tabButton = $('[data-rastisi-action="global-tab"][data-tab="' + (info.tab || 'visual') + '"]');
    if (tabButton) tabButton.click();
    refreshDesign();
    applyCategory(cat);
    var title = $('[data-vs-design-title]');
    if (title) title.textContent = info.title;
    setDialogRole(true);
    paintScope(cat);
    if (info.palette) filterPalettes();
    var scroller = $('.vs-modal__scroll', designModal);
    if (scroller) scroller.scrollTop = 0;
    keptScroll = 0;
    mirrorSaveState();
    later(function () { if (designModal) designModal.focus({ preventScroll: true }); }, 40);
  }
  function closeDesignDialog() {
    var closer = $('[data-vs-design-head] [data-rastisi-action="panel-close"]');
    bypassGuard = true;
    try { if (closer) closer.click(); } finally { bypassGuard = false; }
  }

  root.addEventListener('click', function (evt) {
    var card = evt.target.closest('[data-vs-open-cat]');
    if (card) { openCategory(card.getAttribute('data-vs-open-cat')); return; }
    // the navigator's header / footer rows and the Composer's header/footer chips open their category dialog
    var trigger = evt.target.closest('[data-rs-global-focus]');
    if (trigger) {
      var region = trigger.getAttribute('data-rs-global-focus');
      later(function () { if (R4.isGlobalDesignOpen()) { refreshDesign(); applyCategory(region === 'footer' ? 'footer' : 'header'); setTitle(region === 'footer' ? 'footer' : 'header'); } }, 0);
    }
    var close = evt.target.closest('[data-vs-design-head] [data-rastisi-action="panel-close"], .vs-modal__foot [data-rastisi-action="panel-close"]');
    if (close) guardClose(evt, closeDesignDialog);
  }, true);
  function setTitle(cat) {
    var title = $('[data-vs-design-title]');
    if (title && CATS[cat]) title.textContent = CATS[cat].title;
  }
  // a click on the dimmed area closes the dialog, like the section settings' backdrop
  if (designLayer) designLayer.addEventListener('mousedown', function (evt) {
    if (evt.target !== designLayer || root.dataset.rsDrawer !== 'global') return;
    var fake = { preventDefault: function () {}, stopImmediatePropagation: function () {} };
    if (!guardClose(fake, closeDesignDialog)) closeDesignDialog();
  });

  // the Global Design can also be opened by r4_studio.js itself (e.g. a Composer header chip): pick the category from what it opened
  root.addEventListener('r4:global-opened', function () {
    later(function () {
      if (currentCat) return;
      var cat = 'colors';
      if (document.getElementById('rsGlobalHeader') && document.getElementById('rsGlobalHeader').open) cat = 'header';
      else if (document.getElementById('rsGlobalFooter') && document.getElementById('rsGlobalFooter').open) cat = 'footer';
      refreshDesign();
      applyCategory(cat);
      setTitle(cat);
      setDialogRole(true);
      paintScope(cat);
      mirrorSaveState();
    }, 20);
  });
  root.addEventListener('r4:global-closed', clearCategory);
  root.addEventListener('r4:global-refreshed', function () { later(refreshDesign, 0); });
  var designHost = gd();
  // R4 replaces the panel's innerHTML after a save. Re-dress it in the same microtask (before the browser paints) and keep the dialog where the seller
  // was: a frame without the gallery would shrink the content and throw the scroll position to the top.
  var keptScroll = 0;
  function dialogScroller() { return $('.vs-modal__scroll', designModal); }
  if (designModal) {
    var scroller = dialogScroller();
    if (scroller) scroller.addEventListener('scroll', function () { keptScroll = scroller.scrollTop; }, { passive: true });
  }
  function restoreScroll() {
    var scroller = dialogScroller();
    if (scroller && keptScroll > 0 && Math.abs(scroller.scrollTop - keptScroll) > 4) scroller.scrollTop = keptScroll;
  }
  if (designHost && window.MutationObserver) {
    new MutationObserver(function () { refreshDesign(); restoreScroll(); later(restoreScroll, 60); later(restoreScroll, 400); }).observe(designHost, { childList: true });
  }
  if (designHost) designHost.addEventListener('change', function () { later(updateSummaries, 500); });

  // Tab keeps focus inside the open design dialog
  document.addEventListener('keydown', function (evt) {
    if (evt.key !== 'Tab' || !designModal || designLayer.hidden || !designLayer.classList.contains('panel-visible') || root.dataset.rsDrawer !== 'global') return;
    var focusable = $all('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex="0"]', designModal)
      .filter(function (el) { return el.getClientRects().length > 0 && !el.closest('[hidden]') && !el.closest('.vs-hide') && !el.closest('.vs-filtered-out'); });
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    var inside = designModal.contains(document.activeElement);
    if (!inside || (evt.shiftKey && document.activeElement === first)) { evt.preventDefault(); last.focus(); }
    else if (!evt.shiftKey && document.activeElement === last) { evt.preventDefault(); first.focus(); }
  });

  // «باز کردن تنظیم حرکت»: the real appearance controls of motion
  // (the buttons carry data-vs-open-cat, handled above)

  // ---- names: one wording for the two regions and the two history commands (display text only) ---------------------------
  // R4 renders «سربرگ فروشگاه» / «پایین صفحه» (navigator rows), «هدر» / «فوتر» (headings of the design panel) and «واگرد» / «بازگردانی» (history dialog);
  // Vision shows the same things under one name each. Only the visible text / aria-label changes - never a key, an id, a route or an action.
  var REGION_NAME = { header: 'سربرگ (هدر)', footer: 'پابرگ (فوتر)' };
  function setLabelText(node, text) {
    var done = false;
    Array.prototype.forEach.call(node.childNodes, function (child) {
      if (child.nodeType === 3 && child.textContent.trim()) { if (!done) { child.textContent = ' ' + text + ' '; done = true; } else child.textContent = ''; }
    });
  }
  function renameRegions() {
    $all('.common-region').forEach(function (row) {
      var button = row.querySelector('[data-rs-global-focus]');
      var region = button && button.getAttribute('data-rs-global-focus');
      if (!REGION_NAME[region] || row.dataset.vsNamed === region) return;
      row.dataset.vsNamed = region;
      setLabelText(row, REGION_NAME[region]);
      button.setAttribute('aria-label', 'تنظیم ظاهر مشترک ' + REGION_NAME[region]);
    });
    var panel = gd();
    if (panel) {
      $all('[data-r4-global-mutation="header.update"]>h4', panel).forEach(function (h) { h.textContent = REGION_NAME.header; });
      $all('[data-r4-global-mutation="footer.update"]>h4', panel).forEach(function (h) { h.textContent = REGION_NAME.footer; });
    }
  }
  // the history dialog and the shortcut help are rendered by R4 into the modal root
  var HISTORY_WORDS = [[/واگرد/g, 'Undo'], [/بازگردانی/g, 'Redo'], [/از ?نو(?![\u0600-\u06FF])/g, 'Redo']];
  function renameHistoryWords(scope) {
    var targets = $all('[data-rastisi-action="history-undo"], [data-rastisi-action="history-redo"], .modal p.small.muted', scope);
    var historyButton = scope.querySelector('[data-rastisi-action="history-undo"]');
    var historyModal = historyButton && historyButton.closest('.modal, [role="dialog"]');
    if (historyModal) targets.push(historyModal);                 // the whole history dialog, and only that dialog
    targets.forEach(function (node) {
      var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      var text;
      while ((text = walker.nextNode())) {
        var value = text.nodeValue;
        HISTORY_WORDS.forEach(function (pair) { value = value.replace(pair[0], pair[1]); });
        if (value !== text.nodeValue) text.nodeValue = value;
      }
    });
  }
  var modalRoot = $('[data-rs-modal-root]');
  if (modalRoot && window.MutationObserver) {
    new MutationObserver(function () { renameHistoryWords(modalRoot); }).observe(modalRoot, { childList: true, subtree: true });
  }
  var structureHost = document.getElementById('r4Structure');
  if (structureHost && window.MutationObserver) {
    new MutationObserver(function () { renameRegions(); }).observe(structureHost, { childList: true, subtree: true });
  }

  // ---- clarity: plain names, one sentence of effect, where it acts, what state it is in ------------------------
  // Wording only (vsUx, keyed by the real field key). Controls without an entry keep R4's own label. Nothing here changes a value.
  var SCOPES = {
    colors: 'کل فروشگاه', typography: 'کل فروشگاه', buttons: 'کل فروشگاه', shape: 'کل فروشگاه', images: 'کل فروشگاه', motion: 'کل فروشگاه',
    header: 'کل فروشگاه · بالای همهٔ صفحه‌ها', footer: 'کل فروشگاه · پایین همهٔ صفحه‌ها', bottom_nav: 'کل فروشگاه · نوار پایین صفحه',
    theme: 'کل فروشگاه'
  };
  var DEVICES_OF = { bottom_nav: 'فقط موبایل' };
  function paintScope(cat) {
    var bar = $('[data-vs-scopebar]');
    if (!bar) return;
    bar.innerHTML = '';
    function chip(text, cls) {
      var el = document.createElement('span');
      el.className = 'vs-scopechip' + (cls ? ' ' + cls : '');
      el.textContent = text;
      bar.appendChild(el);
    }
    chip('اثر: ' + (SCOPES[cat] || 'کل فروشگاه'));
    chip(DEVICES_OF[cat] || 'دسکتاپ، تبلت و موبایل');
    chip('ذخیره در پیش‌نویس · منتشر نمی‌شود', 'vs-scopechip--draft');
  }
  function labelNodeFor(panel, ctl) {
    var label = ctl.id ? panel.querySelector('label[for="' + ctl.id + '"]') : null;
    if (label) return label.children.length ? null : label;
    var wrap = ctl.closest('label.field');
    return wrap ? wrap.querySelector(':scope > span') : null;
  }
  function addHelp(after, text) {
    var p = document.createElement('p');
    p.className = 'vs-help';
    p.textContent = text;
    after.insertAdjacentElement('afterend', p);
  }
  function enhanceClarity() {
    var panel = gd();
    if (!panel) return;
    $all('[data-r4-global-field]', panel).forEach(function (ctl) {
      if (ctl.type === 'radio' || ctl.dataset.vsHelp) return;
      var copy = (UX.settings || {})[ctl.getAttribute('data-r4-global-field')];
      if (!copy) return;
      ctl.dataset.vsHelp = '1';
      var isSwitch = ctl.classList.contains('r4-switch');
      if (!isSwitch) {
        var node = labelNodeFor(panel, ctl);
        if (node) { if (!node.dataset.vsOrig) node.dataset.vsOrig = node.textContent; node.textContent = copy.title; }
      }
      var wrap = ctl.closest('label.r4-checkbox-row');
      addHelp(wrap || ctl, copy.effect);
    });
    // header / footer «نمایش در دستگاه‌ها»: one row per component, two switches (tablet, mobile); the desktop always shows it
    $all('.r4-responsive-row', panel).forEach(function (row) {
      if (row.dataset.vsHelp) return;
      row.dataset.vsHelp = '1';
      var first = row.querySelector('[data-r4-global-responsive-key]');
      var item = first && (UX.settings || {})[first.getAttribute('data-r4-global-responsive-key')];
      var head = row.querySelector('.r4-field-sublabel');
      if (head && item) { if (!head.dataset.vsOrig) head.dataset.vsOrig = head.textContent; head.textContent = item.title; }
      var p = document.createElement('p');
      p.className = 'vs-help';
      p.textContent = 'هر دستگاهی که خاموش شود، این بخش فقط روی همان دستگاه پنهان می‌شود؛ روی دسکتاپ همیشه دیده می‌شود.';
      row.appendChild(p);
    });
  }
  // a change shows its own small state next to the control: saving -> saved in the Draft (or failed)
  var touched = null;
  function describeControl(ctl) {
    if (ctl.hasAttribute('data-r4-global-responsive-prop')) {
      return '[data-r4-global-responsive-key="' + ctl.getAttribute('data-r4-global-responsive-key') + '"][data-r4-global-responsive-prop="' + ctl.getAttribute('data-r4-global-responsive-prop') + '"]';
    }
    var key = ctl.getAttribute('data-r4-global-field');
    return key && ctl.type !== 'radio' ? '[data-r4-global-field="' + key + '"]' : null;
  }
  function setBadge(ctl, state, text) {
    var anchor = ctl.__vsText || ctl;
    var old = anchor.parentNode && anchor.parentNode.querySelector(':scope > .vs-rowbadge');
    if (old) old.remove();
    if (!state) return;
    var badge = document.createElement('span');
    badge.className = 'vs-rowbadge vs-rowbadge--' + state;
    badge.setAttribute('role', 'status');
    badge.textContent = text;
    anchor.insertAdjacentElement('afterend', badge);
    if (state === 'saved') later(function () { if (badge.parentNode) badge.remove(); }, 2600);
  }
  if (gd()) {
    gd().addEventListener('change', function (evt) {
      var ctl = evt.target;
      var selector = ctl && ctl.matches && describeControl(ctl);
      if (!selector) return;
      touched = { selector: selector };
      setBadge(ctl, 'saving', 'در حال ذخیره…');
    });
  }
  function settleTouched() {
    if (!touched) return;
    var ctl = gd() && gd().querySelector(touched.selector);
    var state = saveState();
    if (!ctl) return;
    if (state === 'saved') { setBadge(ctl, 'saved', '✓ در پیش‌نویس ذخیره شد'); touched = null; }
    else if (state === 'error' || state === 'conflict') { setBadge(ctl, 'error', state === 'conflict' ? 'تعارض: صفحه را تازه کنید' : 'ذخیره نشد'); touched = null; }
  }
  root.addEventListener('r4:savestate', function () { later(settleTouched, 700); });
  root.addEventListener('r4:global-refreshed', function () { later(settleTouched, 50); });

  // ---- model galleries (header / footer): real pictures of the registry's own models ------------------
  // The cards come from vsVariantGallery (registry key, Persian name, description, thumbnails photographed from the REAL renderer). The original
  // <select> stays in the DOM and is the only thing that is written: choosing a card sets it and fires its change event, so R4's own handler sends
  // header.update / footer.update (Revision, History, Undo, Preview refresh - unchanged). «مشاهده بزرگ‌تر» opens a read-only live preview and writes nothing.
  var GALLERY = readJson('vsVariantGallery') || {};
  var GALLERY_SELECT = { header: 'r4GlobalHeaderVariant', footer: 'r4GlobalFooterVariant' };
  var galleryFlash = null;
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function thumb(item) {
    var media = el('div', 'vs-gcard__media');
    if (item.status === 'ok' && item.desktop) {
      var img = el('img');
      img.src = item.desktop;
      img.alt = '';
      img.loading = 'lazy';
      media.appendChild(img);
      if (item.mobile) {
        var phone = el('span', 'vs-gcard__phone');
        var pimg = el('img');
        pimg.src = item.mobile;
        pimg.alt = '';
        pimg.loading = 'lazy';
        phone.appendChild(pimg);
        media.appendChild(phone);
      }
    } else {
      var none = el('div', 'vs-gcard__none');
      none.appendChild(el('strong', null, 'پیش‌نمایش موجود نیست'));
      none.appendChild(el('small', null, item.status === 'stale' ? 'تصویر این مدل قدیمی است؛ با «مشاهده بزرگ‌تر» نمای زندهٔ آن را ببینید.' : 'تصویر این مدل هنوز ساخته نشده؛ با «مشاهده بزرگ‌تر» نمای زندهٔ آن را ببینید.'));
      media.appendChild(none);
    }
    return media;
  }
  function card(region, item, currentKey, isTwin) {
    var li = el('li', 'vs-gcard' + (item.key === currentKey ? ' is-current' : '') + (isTwin ? ' is-twin' : ''));
    li.dataset.key = item.key;
    li.appendChild(thumb(item));
    var body = el('div', 'vs-gcard__body');
    var head = el('div', 'vs-gcard__head');
    head.appendChild(el('h5', null, item.label));
    if (item.key === currentKey) head.appendChild(el('span', 'vs-badge', 'مدل فعلی'));
    body.appendChild(head);
    if (item.description) body.appendChild(el('p', 'vs-gcard__desc', item.description));
    if (item.same_as_label) body.appendChild(el('p', 'vs-gcard__twin', 'ظاهر این مدل با «' + item.same_as_label + '» یکسان است.'));
    var actions = el('div', 'vs-gcard__actions');
    var view = el('button', 'vs-btn', 'مشاهده بزرگ‌تر');
    view.type = 'button';
    view.dataset.vsGalView = item.key;
    view.setAttribute('aria-label', 'مشاهده بزرگ‌تر مدل ' + item.label);
    var pick = el('button', 'vs-btn vs-btn--accent', item.key === currentKey ? 'مدل فعلی' : 'انتخاب این مدل');
    pick.type = 'button';
    pick.dataset.vsGalPick = item.key;
    pick.setAttribute('aria-label', (item.key === currentKey ? 'مدل فعلی: ' : 'انتخاب مدل ') + item.label);
    if (item.key === currentKey) { pick.disabled = true; pick.setAttribute('aria-pressed', 'true'); }
    actions.appendChild(view);
    actions.appendChild(pick);
    body.appendChild(actions);
    if (galleryFlash && galleryFlash.region === region && galleryFlash.key === item.key && item.key === currentKey) {
      body.appendChild(el('p', 'vs-gcard__flash', '✓ اعمال شد و در پیش‌نویس ذخیره شد'));
    }
    li.appendChild(body);
    return li;
  }
  function enhanceGalleries() {
    Object.keys(GALLERY_SELECT).forEach(function (region) {
      var select = document.getElementById(GALLERY_SELECT[region]);
      var data = GALLERY[region];
      if (!select || !data || select.dataset.vsGallery) return;
      select.dataset.vsGallery = '1';
      select.classList.add('vs-gal-native');
      var current = select.value;
      var wrap = el('div', 'vs-gal');
      wrap.dataset.vsGal = region;
      wrap.appendChild(el('p', 'vs-gal__lead', 'یک مدل را انتخاب کنید. تصویر هر مدل از نمای واقعی همین سیستم برداشته شده است. «مشاهده بزرگ‌تر» فقط نشان می‌دهد و چیزی را تغییر نمی‌دهد؛ «انتخاب این مدل» آن را در پیش‌نویس ذخیره می‌کند.'));
      var distinct = data.items.filter(function (item) { return !item.same_as; });
      // the model in use comes first, so the seller sees it without scrolling
      distinct.sort(function (a, b) { return (b.key === current) - (a.key === current); });
      var twins = data.items.filter(function (item) { return item.same_as; });
      var grid = el('ul', 'vs-gal__grid');
      distinct.forEach(function (item) { grid.appendChild(card(region, item, current, false)); });
      wrap.appendChild(grid);
      if (twins.length) {
        var more = el('details', 'vs-gal__twins');
        if (twins.some(function (item) { return item.key === current; })) more.open = true;
        more.appendChild(el('summary', null, 'مدل‌های هم‌ظاهر (' + faDigits(twins.length) + ') — ظاهرشان با یکی از مدل‌های بالا یکسان است'));
        var tgrid = el('ul', 'vs-gal__grid');
        twins.forEach(function (item) { tgrid.appendChild(card(region, item, current, true)); });
        more.appendChild(tgrid);
        wrap.appendChild(more);
      }
      var help = select.nextElementSibling;
      (help && help.classList.contains('vs-help') ? help : select).insertAdjacentElement('afterend', wrap);
      if (galleryFlash && galleryFlash.region === region) later(function () { galleryFlash = null; var f = wrap.querySelector('.vs-gcard__flash'); if (f) f.remove(); }, 3200);
    });
  }
  function pickModel(region, key) {
    var select = document.getElementById(GALLERY_SELECT[region]);
    if (!select || select.value === key) return;
    select.value = key;
    galleryFlash = { region: region, key: key };
    var li = gd() && gd().querySelector('.vs-gal[data-vs-gal="' + region + '"] .vs-gcard[data-key="' + key + '"]');
    if (li) { li.classList.add('is-pending'); li.setAttribute('aria-busy', 'true'); }
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ---- the large read-only preview of one model ------------------------------------------------------
  var vp = $('[data-vs-vp]');
  var vpBox = vp && $('[data-vs-vp-box]', vp);
  var vpFrame = vp && $('[data-vs-vp-frame]', vp);
  var vpState = { region: null, key: null, device: 'desktop', opener: null };
  function vpOpen() { return !!vp && !vp.hidden; }
  function pageType() { return root.getAttribute('data-r4-page-type') || 'home'; }
  // The preview page holds ONE region and nothing else, so the frame is as tall as that region really is (at the chosen device width); a tall
  // footer scrolls inside the stage, a short header leaves no empty space. Re-measured after load, fonts and images.
  function regionHeight() {
    try {
      var doc = vpFrame.contentDocument;
      var region = doc && doc.querySelector('[data-vs-region]');
      return region ? Math.ceil(region.getBoundingClientRect().height) : 0;
    } catch (e) { return 0; }
  }
  function layoutPreview() {
    if (!vpOpen() || !vpFrame) return;
    var stage = $('[data-vs-vp-stage]', vp);
    var box = $('[data-vs-vp-framebox]', vp);
    var width = vpState.device === 'mobile' ? 390 : 1280;
    var scale = Math.min(1, Math.max(0.2, (stage.clientWidth - 24) / width));
    vpFrame.style.width = width + 'px';
    var natural = regionHeight();                       // measured after the width is applied, so it is the height at THIS device width
    var height = natural > 0 ? natural : 160;
    vpFrame.style.height = height + 'px';
    vpFrame.style.transform = 'scale(' + scale + ')';
    box.style.width = Math.round(width * scale) + 'px';
    box.style.height = Math.round(height * scale) + 'px';
  }
  function setPreviewDevice(device) {
    vpState.device = device;
    $all('[data-vs-vp-device]', vp).forEach(function (btn) {
      var on = btn.getAttribute('data-vs-vp-device') === device;
      btn.classList.toggle('is-on', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    layoutPreview();
  }
  function openPreview(region, key, opener) {
    var data = GALLERY[region];
    var item = data && data.items.filter(function (it) { return it.key === key; })[0];
    if (!vp || !item) return;
    vpState.region = region;
    vpState.key = key;
    vpState.opener = opener || null;
    $('[data-vs-vp-title]', vp).textContent = data.title + ': ' + item.label;
    $('[data-vs-vp-desc]', vp).textContent = item.description || '';
    var select = document.getElementById(GALLERY_SELECT[region]);
    var isCurrent = !!select && select.value === key;
    var choose = $('[data-vs-vp-choose]', vp);
    choose.disabled = isCurrent;
    choose.textContent = isCurrent ? 'مدل فعلی' : 'انتخاب این مدل';
    $('[data-vs-vp-status]', vp).textContent = isCurrent ? 'این مدل همین حالا روی پیش‌نویس شما اعمال است.' : 'فقط پیش‌نمایش است؛ پیش‌نویس تغییر نکرده.';
    vp.hidden = false;
    vpFrame.src = vpFrame.getAttribute('data-vs-vp-url') + '?region=' + encodeURIComponent(region) + '&variant=' + encodeURIComponent(key) + '&page=' + encodeURIComponent(pageType());
    setPreviewDevice(window.matchMedia('(max-width:700px)').matches ? 'mobile' : 'desktop');   // a phone looks at the phone layout first
    later(function () { layoutPreview(); vpBox.focus({ preventScroll: true }); }, 30);
  }
  function closePreview() {
    if (!vpOpen()) return;
    vp.hidden = true;
    vpFrame.src = 'about:blank';
    var opener = vpState.opener;
    vpState.opener = null;
    later(function () { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); }, 30);
  }
  if (vp) {
    vp.addEventListener('click', function (evt) {
      if (evt.target === vp || evt.target.closest('[data-vs-vp-close]')) { closePreview(); return; }
      var dev = evt.target.closest('[data-vs-vp-device]');
      if (dev) { setPreviewDevice(dev.getAttribute('data-vs-vp-device')); return; }
      if (evt.target.closest('[data-vs-vp-choose]')) {
        var region = vpState.region;
        var key = vpState.key;
        vpState.opener = null;                       // the gallery is rebuilt after saving: focus goes to the dialog's category instead
        closePreview();
        pickModel(region, key);
      }
    });
    window.addEventListener('resize', layoutPreview);
    vpFrame.addEventListener('load', function () {
      if (!vpOpen()) return;
      layoutPreview();
      later(layoutPreview, 250);
      later(layoutPreview, 900);                        // late web fonts / images can change the region's height
    });
    // Tab stays inside the preview dialog
    vp.addEventListener('keydown', function (evt) {
      if (evt.key !== 'Tab') return;
      var items = $all('button:not(:disabled)', vpBox).filter(function (n) { return n.getClientRects().length > 0; });
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (evt.shiftKey && (document.activeElement === first || document.activeElement === vpBox)) { evt.preventDefault(); last.focus(); }
      else if (!evt.shiftKey && document.activeElement === last) { evt.preventDefault(); first.focus(); }
    });
  }
  root.addEventListener('click', function (evt) {
    var view = evt.target.closest('[data-vs-gal-view]');
    if (view) {
      var holder = view.closest('[data-vs-gal]');
      openPreview(holder.getAttribute('data-vs-gal'), view.getAttribute('data-vs-gal-view'), view);
      return;
    }
    var pickBtn = evt.target.closest('[data-vs-gal-pick]');
    if (pickBtn && !pickBtn.disabled) {
      var pickHolder = pickBtn.closest('[data-vs-gal]');
      pickModel(pickHolder.getAttribute('data-vs-gal'), pickBtn.getAttribute('data-vs-gal-pick'));
    }
  });

  // ---- first Preview load ------------------------------------------------------
  var loading = $('[data-vs-loading]');
  function doneLoading() { if (loading) loading.hidden = true; }
  var preview = document.getElementById('r4PreviewFrame');
  if (preview) {
    preview.addEventListener('load', doneLoading);
    try { if (preview.contentDocument && preview.contentDocument.readyState === 'complete' && preview.contentDocument.URL !== 'about:blank') doneLoading(); } catch (e) { /* same origin always */ }
    later(doneLoading, 15000);   // never leave the overlay up if the Preview is slow: the Preview itself shows its own state
  }

  // ---- zoom read-out ------------------------------------------------------
  var zoomOut = $('[data-vs-zoom-out]');
  function syncZoom() {
    if (!zoomOut || !preview) return;
    var match = /scale\(([0-9.]+)\)/.exec(preview.style.transform || '');
    if (match) zoomOut.textContent = faDigits(Math.round(parseFloat(match[1]) * 100)) + '٪';
  }
  if (preview && window.MutationObserver) {
    new MutationObserver(syncZoom).observe(preview, { attributes: true, attributeFilter: ['style'] });
  }
  syncZoom();

  // a phone shows the store at its real phone width (the device switch is UI-only state; nothing is stored)
  if (window.matchMedia('(max-width:700px)').matches && typeof R4.setDevice === 'function') R4.setDevice('mobile');

  // ---- small screens: the navigator and the panel become drawers -----------------
  $all('[data-vs-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var which = btn.getAttribute('data-vs-toggle');
      root.dataset.vsDrawer = root.dataset.vsDrawer === which ? '' : which;
    });
  });
  $all('[data-vs-drawer-close]').forEach(function (btn) {
    btn.addEventListener('click', function () { root.dataset.vsDrawer = ''; });
  });

  // ---- first paint -------------------------------------------------------------
  renameRegions();
  refreshDesign();
  enhanceSwitches(root);
})();
