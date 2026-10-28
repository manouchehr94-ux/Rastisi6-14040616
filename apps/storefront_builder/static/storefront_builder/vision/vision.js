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

  // ---- switches: a word for the state, next to the control -------------------------
  // The wording follows the field's own meaning: «پنهان …» fields are ON when the thing is hidden. Only the label next to the switch is added; the
  // checkbox / aria-pressed value that R4 reads and writes is never touched.
  function switchLabel(ctl) {
    var text = '';
    var wrap = ctl.closest('label');
    if (wrap) {
      var own = wrap.querySelector('span:not(.vs-sw-text)');
      text = (own || wrap).textContent;
    } else if (ctl.id) {
      var forLabel = document.querySelector('label[for="' + ctl.id + '"]');
      text = forLabel ? forLabel.textContent : '';
    }
    if (!text) {
      var row = ctl.closest('.toggle-row, .r4-field');
      var first = row && row.querySelector('span, label');
      text = (ctl.getAttribute('aria-label') || (first && first !== ctl ? first.textContent : '') || '');
    }
    return String(text).replace(/\s+/g, ' ').trim();
  }
  function switchWords(label, on) {
    if (/^(پنهان|مخفی)/.test(label)) return on ? 'پنهان است' : 'نمایش داده می‌شود';
    if (/^نمایش/.test(label)) return on ? 'نمایش داده می‌شود' : 'پنهان است';
    if (/قفل/.test(label)) return on ? 'قفل است' : 'باز است';
    return on ? 'روشن' : 'خاموش';
  }
  function switchOn(ctl) { return ctl.tagName === 'INPUT' ? ctl.checked : ctl.getAttribute('aria-pressed') === 'true'; }
  function paintSwitch(ctl) {
    var text = ctl.__vsText;
    if (!text) return;
    var on = switchOn(ctl);
    var disabled = ctl.disabled;
    text.dataset.on = on ? 'true' : 'false';
    text.dataset.disabled = disabled ? 'true' : 'false';
    text.textContent = disabled ? 'غیرفعال' : switchWords(switchLabel(ctl), on);
  }
  function enhanceSwitches(scope) {
    $all('input.r4-switch, button.switch', scope || root).forEach(function (ctl) {
      if (ctl.closest('template')) return;
      if (!ctl.__vsText) {
        var text = document.createElement('span');
        text.className = 'vs-sw-text';
        text.setAttribute('aria-hidden', 'true');
        ctl.insertAdjacentElement('afterend', text);
        ctl.__vsText = text;
        if (ctl.tagName === 'INPUT') ctl.addEventListener('change', function () { paintSwitch(ctl); });
        else if (window.MutationObserver) new MutationObserver(function () { paintSwitch(ctl); }).observe(ctl, { attributes: true, attributeFilter: ['aria-pressed', 'disabled'] });
      }
      paintSwitch(ctl);
    });
  }
  // a click on a button switch is repainted after R4 has toggled aria-pressed; inputs repaint on change; a refreshed form is re-dressed
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
    header: { title: 'سربرگ فروشگاه', region: 'rsGlobalHeader' },
    footer: { title: 'پابرگ فروشگاه', region: 'rsGlobalFooter' },
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
    if (info.palette) filterPalettes();
    var scroller = $('.vs-modal__scroll', designModal);
    if (scroller) scroller.scrollTop = 0;
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
      mirrorSaveState();
    }, 20);
  });
  root.addEventListener('r4:global-closed', clearCategory);
  root.addEventListener('r4:global-refreshed', function () { later(refreshDesign, 0); });
  var designHost = gd();
  if (designHost && window.MutationObserver) {
    new MutationObserver(function () { later(refreshDesign, 0); }).observe(designHost, { childList: true });
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
  refreshDesign();
  enhanceSwitches(root);
})();
