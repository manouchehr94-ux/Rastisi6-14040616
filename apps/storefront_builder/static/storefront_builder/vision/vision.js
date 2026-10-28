/* RastiSi Vision Studio — shell controller (presentation only).
 *
 * Vision is a second PRESENTATION of the one R4 Studio session. Every operation still belongs to the existing owners:
 *   r4_editor.js  (window.RastiSiR4: mutation queue, history, publish, Preview, Inspector, Global Design)
 *   r4_studio.js  (UI state, dialogs, toasts; R4.studio)
 * This file only decides WHICH pane of the new layout is visible and routes a few Vision-only controls to those owners. It never sends a
 * request, never stores design data and never keeps state beyond the current tab / open menu (in memory).
 */
(function () {
  'use strict';
  var root = document.querySelector('.rs-studio.vs[data-r4-shell]');
  var R4 = window.RastiSiR4;
  if (!root || !R4) return;

  function $(selector, scope) { return (scope || root).querySelector(selector); }
  function $all(selector, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(selector)); }
  function faDigits(text) { return String(text).replace(/[0-9]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.charAt(Number(d)); }); }

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
  var proxyGlobal = $('[data-vs-proxy="global"]');

  function setActiveTab(name) {
    root.dataset.vsTab = name;
    tabButtons.forEach(function (b) {
      var on = b.getAttribute('data-vs-tab-button') === name;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    panes.forEach(function (p) { p.hidden = p.getAttribute('data-vs-pane') !== name; });
  }

  function selectTab(name) {
    if (name === 'design') {
      if (!R4.isGlobalDesignOpen() && proxyGlobal) proxyGlobal.click();   // the one Studio mode switch (r4_studio.js)
    } else if (R4.isGlobalDesignOpen()) {
      R4.closeGlobalDesign();
    }
    setActiveTab(name);
  }

  tabButtons.forEach(function (b) {
    b.addEventListener('click', function () { clearRegionFocus(); selectTab(b.getAttribute('data-vs-tab-button')); });
    b.addEventListener('keydown', function (evt) {
      var at = tabButtons.indexOf(b);
      var next = evt.key === 'ArrowLeft' ? at + 1 : evt.key === 'ArrowRight' ? at - 1 : null;   // RTL: left = next
      if (next == null) return;
      evt.preventDefault();
      var target = tabButtons[(next + tabButtons.length) % tabButtons.length];
      target.focus();
      selectTab(target.getAttribute('data-vs-tab-button'));
    });
  });

  // the Global Design panel can be opened from elsewhere (rail buttons, header/footer rows, the Studio): follow it
  root.addEventListener('r4:global-opened', function () { setActiveTab('design'); });
  root.addEventListener('r4:global-closed', function () {
    clearRegionFocus();
    if (root.dataset.vsTab === 'design') setActiveTab('templates');
  });

  // ---- global regions as elements (header / footer / mobile bar) ---------------------------------------
  var REGIONS = {
    header: { id: 'rsGlobalHeader', name: 'سربرگ فروشگاه' },
    footer: { id: 'rsGlobalFooter', name: 'پایین صفحه (فوتر)' },
    bottom_nav: { id: 'rsGlobalMobileNav', name: 'ناوبری پایین موبایل' },
  };
  var focusHead = $('[data-vs-focus-head]');
  var focusName = $('[data-vs-focus-name]');
  var regionsBar = $('[data-vs-regions]');

  function clearRegionFocus() {
    delete root.dataset.vsFocusRegion;
    $all('.vs-focus-target').forEach(function (el) { el.classList.remove('vs-focus-target'); });
    if (focusHead) focusHead.hidden = true;
  }
  function focusRegion(region) {
    var info = REGIONS[region];
    var details = info && document.getElementById(info.id);
    if (!details) return;
    clearRegionFocus();
    root.dataset.vsFocusRegion = region;
    details.classList.add('vs-focus-target');
    details.open = true;
    if (focusName) focusName.textContent = info.name;
    if (focusHead) focusHead.hidden = false;
    var scroller = $('.vs-panes');
    if (scroller) scroller.scrollTop = 0;   // r4_studio scrolled before the other groups were hidden
  }
  // the rail / navigator rows open a region through r4_studio's own action; Vision only presents it as an element
  root.addEventListener('click', function (evt) {
    var trigger = evt.target.closest('[data-rs-global-focus]');
    if (!trigger) return;
    var region = trigger.getAttribute('data-rs-global-focus');
    window.setTimeout(function () { if (R4.isGlobalDesignOpen()) focusRegion(region); }, 0);
  });
  $all('[data-vs-region]').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var region = chip.getAttribute('data-vs-region');
      selectTab('design');
      window.setTimeout(function () { focusRegion(region); }, 30);
    });
  });
  var focusBack = $('[data-vs-focus-back]');
  if (focusBack) focusBack.addEventListener('click', function () {
    clearRegionFocus();
    if (R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
    setActiveTab('templates');
  });

  // «باز کردن تنظیم …»: open the real Global Design panel and focus the real control
  root.addEventListener('click', function (evt) {
    var btn = evt.target.closest('[data-vs-focus]');
    if (!btn) return;
    var id = btn.getAttribute('data-vs-focus');
    selectTab('design');
    window.setTimeout(function () {
      var control = document.getElementById(id);
      if (!control) return;
      var details = control.closest('details');
      if (details) details.open = true;
      control.scrollIntoView({ block: 'center' });
      control.focus({ preventScroll: true });
    }, 60);
  });

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

  // a section row selects the section AND shows its settings in the properties panel (the reference's «ظاهر عنصر»)
  root.addEventListener('click', function (evt) {
    var select = evt.target.closest('[data-rastisi-action="row-select"]');
    if (!select) return;
    var row = select.closest('[data-r4-structure-row]');
    var id = row && Number(row.getAttribute('data-r4-structure-section-id'));
    if (!id) return;
    evt.stopImmediatePropagation();
    if (R4.studio && R4.studio.edit) R4.studio.edit(id);
  }, true);

  // A click on the canvas only SELECTS (the Composer toolbar with «ویرایش», move, duplicate, delete appears); its «ویرایش» / a double click
  // opens the settings, exactly like R4. Only a navigator row opens them directly.

  // the back button lives outside #r4Inspector (where r4_editor.js listens for [data-r4-inspector-close]), so it asks R4 to close directly
  var wsBack = $('.vs-workspace .vs-back');
  if (wsBack) wsBack.addEventListener('click', function () { if (R4.inspectorOpen) R4.closeInspector(); });

  // ---- inspector chrome ----------------------------------------------------
  // each titled card of the settings form becomes a collapsible group (presentation only; the form values stay in the DOM)
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
    var title = $('[data-rs-inspector-title]', inspector);
    var label = $('.vs-ws-head__title');
    if (title && label) label.textContent = title.textContent;
  }
  // the open section's row stays highlighted in the navigator
  function markOpenRow() {
    var id = R4.inspectorOpen ? String(R4.selected) : null;
    $all('[data-r4-structure-row]').forEach(function (row) {
      row.classList.toggle('is-open', id !== null && row.getAttribute('data-r4-structure-section-id') === id);
    });
  }
  root.addEventListener('r4:inspector-opened', function () { enhanceInspector(); window.setTimeout(enhanceInspector, 0); markOpenRow(); });
  root.addEventListener('r4:inspector-closed', markOpenRow);
  root.addEventListener('r4:structure-refreshed', markOpenRow);
  var inspectorHost = document.getElementById('r4Inspector');
  if (inspectorHost && window.MutationObserver) {
    new MutationObserver(function () { enhanceInspector(); }).observe(inspectorHost, { childList: true });
  }

  // ---- first Preview load ------------------------------------------------------
  var loading = $('[data-vs-loading]');
  function doneLoading() { if (loading) loading.hidden = true; }
  var preview = document.getElementById('r4PreviewFrame');
  if (preview) {
    preview.addEventListener('load', doneLoading);
    try { if (preview.contentDocument && preview.contentDocument.readyState === 'complete' && preview.contentDocument.URL !== 'about:blank') doneLoading(); } catch (e) { /* cross-origin never happens here */ }
    window.setTimeout(doneLoading, 15000);   // never leave the overlay up if the Preview is slow: the Preview itself shows its own state
  }

  // ---- zoom read-out ------------------------------------------------------
  var zoomOut = $('[data-vs-zoom-out]');
  var frame = document.getElementById('r4PreviewFrame');
  function syncZoom() {
    if (!zoomOut || !frame) return;
    var match = /scale\(([0-9.]+)\)/.exec(frame.style.transform || '');
    if (match) zoomOut.textContent = faDigits(Math.round(parseFloat(match[1]) * 100)) + '٪';
  }
  if (frame && window.MutationObserver) {
    new MutationObserver(syncZoom).observe(frame, { attributes: true, attributeFilter: ['style'] });
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

  // opening the settings of a section on a small screen must show the panel
  root.addEventListener('r4:inspector-opened', function () {
    if (window.matchMedia('(max-width:1023px)').matches) root.dataset.vsDrawer = 'panel';
  });
})();
