/*
 * RastiSi Design Studio — presentation layer for the R4 editor.
 *
 * Visual/interaction reference: RastiSi_Design_Studio.html (approved).
 *
 * UI-ONLY. This file owns workspace presentation state (mode, panel view,
 * global tab, dialogs, gallery filter/search, toast, focus) and nothing else.
 * Every business operation goes through the single owner, window.RastiSiR4
 * (r4_editor.js): the mutation queue, history, publish/discard/template
 * switch, the Design Lab endpoint and the ONE #r4PreviewFrame surface.
 * This file never sends a write request, never stores state in the browser,
 * and never renders the storefront itself.
 */
(function () {
  'use strict';

  var R4 = window.RastiSiR4;
  var root = document.querySelector('.rs-studio[data-r4-shell]');
  if (!R4 || !root) return;

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return {};
    try { return JSON.parse(el.textContent) || {}; } catch (e) { return {}; }
  }

  var DATA = readJson('rsStudioData');
  var PATHS = readJson('rsStudioIcons');
  var FAMILIES = ['header', 'hero', 'product_view', 'card', 'footer', 'badge', 'bottom_nav'];
  var THEME_NONE = DATA.theme_none_key || 'theme.none.v1';
  var FAMILY_LABELS = {
    header: 'سربرگ', hero: 'بنر اصلی', product_view: 'چیدمان محصولات', card: 'کارت محصول',
    footer: 'پایین صفحه', badge: 'نشان محصول', bottom_nav: 'نوار موبایل',
  };

  // ---- small render helpers (same vocabulary as the reference) ----------
  function icon(name) {
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="' +
      (PATHS[name] || PATHS.grid || '') + '"/></svg>';
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(n) { return Number(n || 0).toLocaleString('fa-IR'); }
  function faDigits(text) { return String(text == null ? '' : text).replace(/[0-9]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; }); }
  function btn(action, text, iconName, cls, attrs) {
    return '<button type="button" data-rastisi-action="' + action + '" class="' + (cls || '') + '" ' + (attrs || '') + '>' +
      (iconName ? icon(iconName) : '') + (text || '') + '</button>';
  }
  function $(selector, scope) { return (scope || root).querySelector(selector); }
  function $all(selector, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(selector)); }

  // ---- stable elements ---------------------------------------------------
  var app = $('.rs-app');
  var layout = $('.studio-layout');
  var contextPanel = $('[data-rs-context-panel]');
  var labDock = $('[data-r4-design-lab-panel]');
  var modalRoot = $('[data-rs-modal-root]');
  var toast = $('[data-rs-toast]');
  var structurePanel = document.getElementById('r4Structure');
  var inspectorAside = document.getElementById('r4Inspector');
  var undoButton = document.getElementById('r4UndoButton');
  var redoButton = document.getElementById('r4RedoButton');
  var publishButton = document.getElementById('r4PublishButton');
  var publicButton = $('[data-rastisi-action="public-preview"]');
  var pageSelect = document.getElementById('r4PageSwitcherSelect');
  var zoomSelect = $('[data-control="zoom"]');
  var saveFeedback = $('[data-rs-save-feedback]');
  var projectSub = $('[data-rs-project-sub]');
  var statusPill = $('[data-rs-status-pill]');
  var pageLabel = DATA.page_label || '';
  var draftProjectSub = projectSub ? projectSub.textContent : '';

  var ui = {
    mode: 'structure',
    panelVisible: true,
    modal: null,
    lastFocus: null,
    filter: 'all',
    query: '',
    previewTemplate: null,
    busy: false,
    publishing: false,
    saveState: 'saved',
    draftChanged: Boolean(DATA.draft_changed),
    hasPublished: Boolean(DATA.has_published),
    publishedAt: DATA.published_at || '',
    canUndo: Boolean(undoButton && !undoButton.disabled),
    canRedo: Boolean(redoButton && !redoButton.disabled),
    history: DATA.history_entries || [],
    selectedSectionId: null,
    lab: { active: false, busy: false, status: 'idle', locked: [], diffs: [], candidateLabels: {}, baseLabels: {}, compareBase: false, stale: false, canApply: false },
    labBaseTheme: null,
    conflictShown: false,
  };

  // ---- toast -------------------------------------------------------------
  var toastTimer = null;
  function notify(text) {
    if (!toast || !text) return;
    clearTimeout(toastTimer);
    toast.textContent = text;
    toast.classList.add('visible');
    toastTimer = setTimeout(function () {
      toast.classList.remove('visible');
      setTimeout(function () { if (!toast.classList.contains('visible')) toast.textContent = ''; }, 220);
    }, 3800);
  }

  // ---- workspace chrome --------------------------------------------------
  var MODE_NAMES = {
    lab: 'آزمایش موقت',
    global: 'طراحی سراسری',
    inspector: 'تنظیمات همین بخش',
  };

  function labActive() { return ui.lab.active; }

  function currentTemplate() {
    return (DATA.templates || []).filter(function (t) { return t.is_current; })[0] || null;
  }

  function browserUrlText() {
    var host = '';
    try { host = DATA.public_url ? new URL(DATA.public_url).host : ''; } catch (e) { host = ''; }
    var page = DATA.page_type && DATA.page_type !== 'home' ? DATA.page_type.replace(/_/g, '-') : '';
    return (host || DATA.store_name || '') + (page ? ' / ' + page : ' /');
  }

  function renderChrome() {
    var isLab = ui.mode === 'lab';
    var lab = ui.lab;
    var block = ui.busy || lab.active;
    root.dataset.rsMode = ui.mode;

    // top navigation
    $all('.top-nav [data-rastisi-action]').forEach(function (b) {
      var action = b.getAttribute('data-rastisi-action');
      var active = ui.mode === action || (action === 'structure' && (ui.mode === 'inspector' || ui.mode === 'template-preview'));
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', active ? 'true' : 'false');
      b.disabled = ui.busy;
    });

    // layout + panel views
    var showPanel = !isLab;
    if (layout) {
      layout.classList.toggle('lab-layout', isLab);
      layout.classList.toggle('no-panel', !showPanel);
    }
    if (contextPanel) {
      contextPanel.hidden = !showPanel;
      contextPanel.classList.toggle('panel-visible', ui.panelVisible);
      contextPanel.setAttribute('data-rastisi-panel', ui.mode === 'global' ? 'global-design' : ui.mode === 'inspector' ? 'inspector' : 'structure');
    }
    $all('[data-rs-view]').forEach(function (view) {
      view.hidden = view.getAttribute('data-rs-view') !== ui.mode;
    });
    if (labDock) labDock.hidden = !isLab;

    // stage toolbar
    $all('[data-rs-lab-only]').forEach(function (el) { el.hidden = !lab.active; });
    $all('[data-rs-edit-only]').forEach(function (el) {
      el.hidden = lab.active || (el.getAttribute('data-rastisi-action') === 'panel-toggle' && !showPanel);
      el.disabled = ui.busy;
    });
    var scopeTag = $('[data-rs-scope-tag]');
    if (scopeTag) scopeTag.textContent = MODE_NAMES[ui.mode] || 'ساختار صفحه';
    var browserState = $('[data-rs-browser-state]');
    if (browserState) {
      browserState.textContent = ui.previewTemplate ? 'پیش‌نمایش قالب'
        : lab.active ? (lab.compareBase ? 'پیش از آزمایش' : 'آزمایش موقت') : 'پیش‌نمایش زنده';
    }
    var browserUrl = $('[data-rs-browser-url]');
    if (browserUrl) browserUrl.textContent = browserUrlText();
    var caption = $('[data-rs-caption]');
    if (caption) {
      caption.textContent = lab.active
        ? (lab.compareBase ? 'طرح هنگام شروع؛ برای مقایسه ثابت می‌ماند.' : 'فقط ظاهر تغییر می‌کند؛ محصولات و متن‌ها محفوظ‌اند.')
        : ui.previewTemplate ? 'همان محتوای فروشگاه شما، با ظاهر این قالب؛ هنوز چیزی تغییر نکرده.'
          : 'برای ویرایش، روی بخش موردنظر کلیک کنید.';
    }
    var captionIcon = caption && caption.parentElement ? caption.parentElement.querySelector('.icon') : null;
    if (captionIcon && caption) captionIcon.outerHTML = icon(lab.active ? 'spark' : 'eye');
    var captionSide = $('[data-rs-caption-side]');
    if (captionSide) {
      captionSide.textContent = pageLabel + ' · ' + (lab.active ? 'آزمایش موقت' : ui.previewTemplate ? 'پیش‌نمایش قالب' : 'پیش‌نویس');
    }
    var compareButtons = { base: $('[data-rastisi-action="show-base"]'), candidate: $('[data-rastisi-action="show-candidate"]') };
    if (compareButtons.base) {
      compareButtons.base.classList.toggle('active', lab.compareBase);
      compareButtons.base.setAttribute('aria-pressed', lab.compareBase ? 'true' : 'false');
    }
    if (compareButtons.candidate) {
      compareButtons.candidate.classList.toggle('active', !lab.compareBase);
      compareButtons.candidate.setAttribute('aria-pressed', lab.compareBase ? 'false' : 'true');
    }
    var diffCount = $('[data-rs-diff-count]');
    if (diffCount) diffCount.textContent = num(familyDiffs().length) + ' تغییر';

    // project bar
    if (statusPill) {
      statusPill.className = 'pill ' + (lab.active ? 'purple' : ui.draftChanged ? 'amber' : 'green');
      statusPill.textContent = lab.active ? 'آزمایش موقت' : ui.draftChanged ? 'منتشرنشده' : 'همگام با سایت';
    }
    if (projectSub) projectSub.textContent = lab.active ? 'تا تأیید شما، پیش‌نویس تغییر نمی‌کند.' : draftProjectSub;
    if (undoButton) undoButton.disabled = !ui.canUndo || block;
    if (redoButton) redoButton.disabled = !ui.canRedo || block;
    var historyButton = $('.history-buttons [data-rastisi-action="history"]');
    if (historyButton) historyButton.disabled = ui.busy;
    if (publicButton) publicButton.disabled = block || !DATA.public_url;
    if (publishButton) publishButton.disabled = block || !ui.draftChanged || ui.saveState !== 'saved';
    if (pageSelect) pageSelect.disabled = ui.busy;

    renderLabDock();
    if (R4.syncPreviewViewport) R4.syncPreviewViewport();
  }

  // ---- save feedback -----------------------------------------------------
  var SAVE_LABELS = { saved: 'پیش‌نویس ذخیره شد', saving: 'در حال ذخیره…', error: 'ذخیره ناموفق', conflict: 'تعارض نسخه' };
  function renderSaveFeedback() {
    if (!saveFeedback) return;
    var state = ui.saveState;
    saveFeedback.className = 'save-feedback ' + state;
    var lead = state === 'saving' ? '<i class="spinner"></i>' : icon(state === 'saved' ? 'check' : 'help');
    var extra = (state === 'error' || state === 'conflict') ? btn('save-issue', 'بررسی', '', 'small') : '';
    saveFeedback.innerHTML = lead + '<span id="r4SaveState">' + esc(SAVE_LABELS[state] || '') + '</span>' + extra;
  }

  // Server-authoritative status after edits: re-read the editor's own GET
  // projection (history entries, undo/redo availability, unpublished flag).
  var statusTimer = null;
  function scheduleStatusRefresh() {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(refreshStatus, 700);
  }
  function refreshStatus() {
    return fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.ok ? response.text() : null; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = {};
        var dataEl = doc.getElementById('rsStudioData');
        try { fresh = dataEl ? JSON.parse(dataEl.textContent) : {}; } catch (e) { fresh = {}; }
        if ('draft_changed' in fresh) ui.draftChanged = Boolean(fresh.draft_changed);
        if (fresh.history_entries) ui.history = fresh.history_entries;
        var freshUndo = doc.getElementById('r4UndoButton');
        var freshRedo = doc.getElementById('r4RedoButton');
        if (freshUndo) ui.canUndo = !freshUndo.hasAttribute('disabled');
        if (freshRedo) ui.canRedo = !freshRedo.hasAttribute('disabled');
        renderChrome();
        if (ui.modal && ui.modal.type === 'history') renderModal();
      })
      .catch(function () { /* status stays as last known; nothing is lost */ });
  }

  // ---- modes -------------------------------------------------------------
  function setMode(mode, options) {
    if (ui.lab.active && mode !== 'lab') {
      openModal('exit-lab', { nextMode: mode });
      return;
    }
    if (ui.mode === 'template-preview' && mode !== 'template-preview') {
      ui.previewTemplate = null;
      R4.showPreview(null);
    }
    ui.panelVisible = true;
    if (mode === 'global') {
      R4.openGlobalDesign();
      if (options && options.tab) setGlobalTab(options.tab);
    } else if (mode === 'structure') {
      if (R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
      if (R4.inspectorOpen) R4.closeInspector();
      markSelectedRow();
    } else if (mode === 'lab') {
      if (R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
      if (R4.inspectorOpen) R4.closeInspector();
      if (zoomSelect) { zoomSelect.value = 'width'; R4.setZoom && R4.setZoom('width'); }
    }
    ui.mode = mode;
    renderChrome();
  }

  function setGlobalTab(tab) {
    if (['visual', 'template', 'theme'].indexOf(tab) === -1) return;
    root.dataset.rsGlobalTab = tab;
    $all('[data-rastisi-action="global-tab"]').forEach(function (b) {
      var active = b.getAttribute('data-tab') === tab;
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function focusGlobalRegion(region) {
    setMode('global', { tab: 'visual' });
    if (ui.mode !== 'global') return;
    var details = document.getElementById(region === 'footer' ? 'rsGlobalFooter' : 'rsGlobalHeader');
    if (details) {
      details.open = true;
      details.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
  }

  // ---- structure / inspector --------------------------------------------
  function rowFor(sectionId) {
    return structurePanel ? structurePanel.querySelector('[data-r4-structure-row][data-r4-structure-section-id="' + sectionId + '"]') : null;
  }

  function markSelectedRow() {
    $all('[data-r4-structure-row]', structurePanel || root).forEach(function (row) {
      row.classList.toggle('selected', ui.mode === 'inspector' && String(ui.selectedSectionId) === row.getAttribute('data-r4-structure-section-id'));
    });
  }

  function containerOrdinal(containerId) {
    var ids = $all('[data-r4-structure-container-id]', structurePanel || root).map(function (el) { return el.getAttribute('data-r4-structure-container-id'); });
    var at = ids.indexOf(String(containerId));
    return at === -1 ? ids.length + 1 : at + 1;
  }

  function renderInspectorChrome() {
    var row = rowFor(ui.selectedSectionId);
    var title = $('[data-rs-inspector-title]');
    var scope = $('[data-rs-inspector-scope] span');
    var lockedNote = $('[data-rs-inspector-locked]');
    var actions = $('[data-rs-section-actions]');
    if (!row) {
      if (actions) actions.innerHTML = '';
      return;
    }
    var label = row.getAttribute('data-rs-section-label') || '';
    var locked = row.getAttribute('data-rs-section-locked') === 'true';
    var active = row.getAttribute('data-rs-section-active') === 'true';
    var duplicable = row.getAttribute('data-rs-section-duplicable') === 'true';
    var removable = row.getAttribute('data-rs-section-removable') === 'true';
    var baseline = row.getAttribute('data-rs-section-baseline') === 'true';
    var rows = $all('[data-r4-structure-row]', structurePanel);
    var index = rows.indexOf(row);
    if (title) title.textContent = label;
    if (scope) scope.textContent = pageLabel + ' / ' + label;
    if (lockedNote) lockedNote.hidden = !locked;
    if (inspectorAside) inspectorAside.inert = locked;
    if (!actions) return;
    var dis = locked ? 'disabled' : '';
    var html = '<div class="section-divider"></div>' +
      '<div class="toggle-row"><span>نمایش در صفحه</span>' + btn('section-enable', '', '', 'switch', 'aria-label="نمایش بخش" aria-pressed="' + active + '" ' + dis) + '</div>' +
      '<div class="toggle-row"><span>قفل ویرایش</span>' + btn('section-lock', '', '', 'switch', 'aria-label="قفل بخش" aria-pressed="' + locked + '"') + '</div>' +
      '<div class="section-divider"></div><div class="section-label">جایگاه در صفحه</div>' +
      '<div class="inspector-actions">' +
        btn('section-up', 'بالاتر', 'up', 'outline', locked || index <= 0 ? 'disabled' : '') +
        btn('section-down', 'پایین‌تر', 'down', 'outline', locked || index === rows.length - 1 ? 'disabled' : '') +
      '</div><div class="inspector-actions">' +
        btn('section-duplicate', 'تکثیر بخش', 'copy', 'outline', locked || !duplicable ? 'disabled' : '') +
        btn('section-remove', 'حذف بخش', 'trash', 'outline danger', locked || !removable ? 'disabled' : '') +
      '</div>';
    var emptyCells = DATA.empty_cells || [];
    if (emptyCells.length) {
      html += '<div class="section-divider"></div><label class="field"><span>انتقال به یک خانهٔ خالی</span><div class="rs-inline-fields"><select data-rs-move-cell ' + dis + ' aria-label="خانهٔ مقصد">' +
        '<option value="">یک خانه انتخاب کنید…</option>' +
        emptyCells.map(function (cell, i) {
          return '<option value="' + esc(cell.cell_id) + '">ردیف ' + num(containerOrdinal(cell.container_id)) + ' · خانهٔ خالی ' + num(i + 1) + '</option>';
        }).join('') +
        '</select>' + btn('section-move-cell', 'انتقال', '', 'outline', dis) + '</div></label>';
    }
    if (baseline) {
      html += btn('section-reset', 'بازگرداندن این بخش به حالت قالب', 'refresh', 'full quiet small', dis);
    }
    actions.innerHTML = html;
  }

  function sectionCommand(command, extra) {
    if (ui.selectedSectionId == null) return;
    var row = rowFor(ui.selectedSectionId);
    if (row && row.getAttribute('data-rs-section-locked') === 'true' && command !== 'toggle_locked') {
      notify('ابتدا قفل این بخش را باز کنید.');
      return;
    }
    R4.sectionCommand(ui.selectedSectionId, command, extra);
  }

  // ---- template gallery / temporary preview ------------------------------
  function templateByKey(key) {
    return (DATA.templates || []).filter(function (t) { return t.key === key; })[0] || null;
  }

  function templateThumb(t) {
    if (t.thumbnail_kind === 'screenshot' && t.thumbnail_url) {
      return '<div class="template-thumb rs-real-thumb"><img src="' + esc(t.thumbnail_url) + '" alt="" loading="lazy"></div>';
    }
    // Server-generated gallery SVG from the canonical preview service.
    return '<div class="template-thumb rs-real-thumb">' + (t.thumbnail_svg || '') + '</div>';
  }

  function templateTiles() {
    var q = ui.query.trim();
    var catalog = (DATA.templates || []).filter(function (t) { return t.is_current; })
      .concat((DATA.templates || []).filter(function (t) { return !t.is_current; }));
    var list = catalog.filter(function (t) {
      if (ui.filter === 'current' && !t.is_current) return false;
      if (!q) return true;
      return [t.label, t.description, t.header_label, t.footer_label].some(function (v) { return String(v || '').indexOf(q) !== -1; });
    });
    if (!list.length) return '<div class="empty">نتیجه‌ای نیست. نام دیگری را جست‌وجو کنید.</div>';
    return list.map(function (t) {
      var sub = [t.header_label, t.footer_label].filter(Boolean).join(' · ') || t.description || '';
      return '<article class="template-tile ' + (t.is_current ? 'active' : '') + '">' + templateThumb(t) +
        '<div class="tile-info">' + (t.is_current ? '<span class="pill green">قالب فعلی</span>' : '') +
        '<strong>' + esc(t.label) + '</strong><small>' + esc(sub) + '</small></div>' +
        '<div class="tile-actions">' +
          btn('preview-template', 'پیش‌نمایش', 'eye', 'outline', 'data-key="' + esc(t.key) + '" aria-label="پیش‌نمایش قالب ' + esc(t.label) + '" ' + (ui.busy ? 'disabled' : '')) +
          btn('switch-template', 'اعمال', 'check', '', 'data-key="' + esc(t.key) + '" aria-label="اعمال قالب ' + esc(t.label) + '" ' + (ui.busy || t.is_current ? 'disabled' : '')) +
        '</div></article>';
    }).join('');
  }

  function openTemplateGallery() {
    if (ui.lab.active) { notify('برای تغییر قالب، ابتدا از آزمایشگاه خارج شوید.'); return; }
    if (ui.mode === 'template-preview') setMode('structure');
    ui.filter = 'all';
    ui.query = '';
    openModal('templates');
  }

  function liveTemplateUrl(key) {
    var url = new URL(String(DATA.live_preview_url || '').replace('__KEY__', encodeURIComponent(key)), window.location.href);
    url.searchParams.set('data', 'merchant');
    url.searchParams.set('page', DATA.page_type || 'home');
    return url.pathname + url.search;
  }

  function previewTemplate(key) {
    var t = templateByKey(key);
    if (!t || ui.busy || ui.lab.active) return;
    closeModal(false);
    if (R4.inspectorOpen) R4.closeInspector();
    if (R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
    ui.previewTemplate = t;
    ui.mode = 'template-preview';
    ui.panelVisible = true;
    var title = $('[data-rs-peek-title]');
    var sub = $('[data-rs-peek-sub]');
    var palette = $('[data-rs-peek-palette]');
    var apply = $('[data-rs-peek-apply]');
    if (title) title.textContent = t.label;
    if (sub) sub.textContent = t.description || '';
    if (palette) {
      palette.innerHTML = (t.palette_swatch || []).length
        ? '<span>رنگ‌های قالب</span>' + t.palette_swatch.map(function (c) { return '<i style="background:' + esc(c) + '"></i>'; }).join('')
        : '';
    }
    if (apply) {
      apply.setAttribute('data-key', t.key);
      apply.disabled = Boolean(t.is_current);
    }
    R4.showPreview(liveTemplateUrl(t.key), { state: 'template' });
    renderChrome();
  }

  function cancelTemplatePreview() {
    ui.previewTemplate = null;
    R4.showPreview(null);
    setMode('structure');
  }

  function switchTemplate(key) {
    var t = templateByKey(key);
    if (!t || ui.busy || ui.lab.active || t.is_current) return;
    ui.busy = true;
    if (ui.modal) renderModal();
    else openModal('templates');
    renderChrome();
    R4.switchTemplate(t.key, t.version).then(function (result) {
      if (result && result.ok) return; // the workspace reloads
      ui.busy = false;
      renderChrome();
      if (ui.modal) renderModal();
      if (ui.saveState !== 'conflict') notify('تغییر قالب انجام نشد؛ دوباره تلاش کنید.');
    });
  }

  // ---- Design Lab dock (renders R4.lab state) ----------------------------
  function familyDiffs() {
    return (ui.lab.diffs || []).filter(function (d) { return FAMILIES.indexOf(d.family) !== -1; });
  }
  function themeDiff() {
    return (ui.lab.diffs || []).filter(function (d) { return d.family === 'theme'; })[0] || null;
  }
  function committedTheme() {
    var activeButton = document.querySelector('#r4GlobalDesign [data-r4-theme-apply][aria-pressed="true"]');
    var intensity = document.querySelector('#r4GlobalDesign [data-r4-theme-intensity]');
    return {
      key: activeButton ? activeButton.getAttribute('data-r4-theme-apply') : THEME_NONE,
      intensity: intensity ? intensity.value : 'balanced',
    };
  }
  function candidateTheme() {
    var diff = themeDiff();
    if (!diff) return ui.labBaseTheme || committedTheme();
    var settings = diff.candidate_settings || {};
    return { key: diff.candidate_key || THEME_NONE, intensity: settings.intensity || 'balanced' };
  }

  var BUSY_TITLES = { generating: 'در حال ساخت ترکیب…', comparing: 'در حال مقایسه…', applying: 'در حال اعمال…' };

  function renderLabDock() {
    if (!labDock) return;
    var lab = ui.lab;
    labDock.classList.toggle('lab-start', !lab.active);
    labDock.classList.toggle('stale', lab.stale);
    $all('[data-rs-lab-start]', labDock).forEach(function (el) { el.hidden = lab.active; });
    $all('[data-rs-lab-active]', labDock).forEach(function (el) { el.hidden = !lab.active; });
    var staleLine = $('[data-rs-lab-stale]', labDock);
    if (staleLine) {
      staleLine.hidden = !(lab.active && lab.stale);
      var restart = staleLine.querySelector('button');
      if (restart) restart.disabled = lab.busy;
    }
    var errorLine = $('[data-rs-lab-error]', labDock);
    if (errorLine) {
      errorLine.hidden = !(lab.active && !lab.stale && lab.status === 'error');
      errorLine.textContent = lab.error === 'template_dna_unavailable'
        ? 'سبک اولیهٔ قالب فعلی در دسترس نیست؛ ترکیب موقت شما دست‌نخورده ماند.'
        : 'درخواست انجام نشد؛ ایده موقت شما محفوظ است. دوباره تلاش کنید.';
    }
    var orb = $('[data-rs-lab-orb]', labDock);
    if (orb) orb.innerHTML = lab.busy ? '<i class="spinner"></i>' : icon('spark');
    var title = $('[data-rs-lab-title]', labDock);
    if (title) title.textContent = lab.busy ? (BUSY_TITLES[lab.status] || 'در حال پردازش…') : 'آزمایش شما';
    var summary = $('[data-rs-lab-summary]', labDock);
    if (summary) summary.textContent = num(familyDiffs().length) + ' تغییر · ' + num(lab.locked.length) + ' قفل · هنوز اعمال نشده';
    $all('.dock-actions button', labDock).forEach(function (b) {
      if (b.hasAttribute('data-r4-design-lab-apply')) b.disabled = !lab.canApply;
      else b.disabled = lab.busy;
    });
    var changed = {};
    familyDiffs().forEach(function (d) { changed[d.family] = true; });
    $all('[data-rastisi-family]', labDock).forEach(function (card) {
      var family = card.getAttribute('data-rastisi-family');
      var isLocked = lab.locked.indexOf(family) !== -1;
      var isChanged = Boolean(changed[family]);
      card.classList.toggle('changed', isChanged);
      card.classList.toggle('locked', isLocked);
      var lock = card.querySelector('[data-rastisi-action="lock-family"]');
      if (lock) {
        lock.innerHTML = icon(isLocked ? 'lock' : 'unlock');
        lock.setAttribute('aria-pressed', isLocked ? 'true' : 'false');
        lock.title = isLocked ? 'باز کردن قفل' : 'این انتخاب را نگه دار';
        lock.disabled = lab.busy;
      }
      var name = card.querySelector('[data-rs-family-current]');
      if (name) {
        if (lab.candidateLabels && lab.candidateLabels[family]) name.textContent = lab.candidateLabels[family];
        name.disabled = lab.busy;
      }
      var one = card.querySelector('[data-rastisi-action="random-family"]');
      if (one) one.disabled = lab.busy || isLocked;
      var before = card.querySelector('[data-rs-family-before]');
      if (before) {
        before.textContent = isChanged ? 'پایه: ' + ((lab.baseLabels && lab.baseLabels[family]) || '—')
          : isLocked ? 'این انتخاب حفظ می‌شود' : 'بدون تغییر';
      }
    });
  }

  var LAB_NOTICES = {
    reset_to_base: 'آزمایش به نقطهٔ شروع برگشت؛ پیش‌نویس تغییری نکرد.',
    return_to_template_dna: 'سبک اولیهٔ قالب به آزمایش برگشت؛ محتوا و مناسبت حفظ شدند. قفل‌ها فقط بر ترکیب تصادفی اثر دارند.',
    remove_theme: 'پوشش مناسبتی برداشته شد؛ طراحی زیر آن بدون تغییر است.',
  };

  function onLabState(detail) {
    var wasActive = ui.lab.active;
    ui.lab = detail;
    if (detail.active && !wasActive) ui.labBaseTheme = committedTheme();
    if (!detail.active) ui.labBaseTheme = null;
    if (detail.notice === 'all_locked') notify('همهٔ بخش‌ها قفل هستند. حداقل یک قفل را باز کنید.');
    if (detail.action && detail.ok && LAB_NOTICES[detail.action]) notify(LAB_NOTICES[detail.action]);
    if (detail.action && detail.ok === false) {
      if (detail.stale) notify('کار جدیدتر حفظ شد؛ این آزمایش قابل اعمال نیست.');
      else if (detail.error !== 'template_dna_unavailable') notify('آزمایش انجام نشد. ترکیب قبلی حفظ شده؛ دوباره تلاش کنید.');
    }
    renderChrome();
    if (ui.modal && (ui.modal.type === 'lab-theme' || ui.modal.type === 'lab-diffs')) renderModal();
  }

  function focusPreviewFamily(family) {
    if (ui.lab.busy || FAMILIES.indexOf(family) === -1) return;
    if (family === 'bottom_nav' && R4.setDevice) R4.setDevice('mobile');
    var targets = {
      header: 'header, .gh',
      hero: '.section.hero, [data-section-key*="hero"]',
      product_view: '.product-section, .catalog-product-wall, [data-section-key*="product"]',
      card: '.pcard, [class*="product-card"]',
      footer: 'footer, .gf',
      badge: '.pcard .badges, .pcard',
      bottom_nav: '.gmn, [class*="bottom-nav"], [class*="mobile-nav"]',
    };
    var frame = document.getElementById('r4PreviewFrame');
    function reveal(attempt) {
      var doc = null;
      try { doc = frame && frame.contentDocument; } catch (e) { doc = null; }
      var target = doc ? doc.querySelector(targets[family]) : null;
      if (!target) {
        if (attempt < 8) setTimeout(function () { reveal(attempt + 1); }, 120);
        else if (family === 'bottom_nav' && frame && frame.contentWindow) frame.contentWindow.scrollTo(0, 0);
        return;
      }
      if (family === 'bottom_nav') frame.contentWindow.scrollTo(0, 0);
      else target.scrollIntoView({ block: family === 'footer' ? 'end' : 'start', behavior: 'instant' });
    }
    setTimeout(function () { reveal(0); }, 80);
  }

  function themeControls(theme, forLab) {
    var occasions = DATA.theme_occasions || [];
    var current = occasions.filter(function (o) { return o.component_key === theme.key; })[0];
    var active = theme.key && theme.key !== THEME_NONE;
    var slug = active ? String(theme.key).split('.')[1] || '' : 'none';
    var demo = active ? (current ? current.label_fa : '') + '؛ روی طراحی شما' : 'طراحی شما، بدون پوشش مناسبتی';
    var busy = ui.lab.busy ? 'disabled' : '';
    var html = '<div class="theme-demo ' + esc(slug) + '">' + esc(demo) + '</div>' +
      '<div class="section-label"><span>حال‌وهوای فروشگاه</span><span class="pill">برگشت‌پذیر</span></div>' +
      '<div class="theme-grid">' + occasions.map(function (o) {
        var on = o.component_key === theme.key || (!active && o.component_key === THEME_NONE);
        return btn(forLab ? 'lab-set-theme' : 'noop', esc(o.label_fa), '', on ? 'active' : '', 'data-theme-key="' + esc(o.component_key) + '" aria-pressed="' + on + '" ' + busy);
      }).join('') + '</div>';
    if (active) {
      html += '<label class="field" style="margin-top:21px"><span>شدت حضور مناسبت</span><select data-control="lab-intensity" ' + busy + '>' +
        (DATA.theme_intensities || ['subtle', 'balanced', 'strong']).map(function (v) {
          var label = v === 'subtle' ? 'ملایم؛ یک اشارهٔ کوچک' : v === 'balanced' ? 'متعادل؛ هماهنگ با طراحی' : 'پررنگ؛ حال‌وهوای کامل';
          return '<option value="' + esc(v) + '" ' + (theme.intensity === v ? 'selected' : '') + '>' + label + '</option>';
        }).join('') + '</select></label>' +
        btn('lab-remove-theme', 'برداشتن پوشش، حفظ طراحی', 'close', 'full outline small', busy);
    }
    html += '<div class="note" style="margin-top:17px">مناسبت، یک لایه روی طراحی شماست. برداشتن آن، رنگ‌ها و چیدمان زیر آن را تغییر نمی‌دهد و ترکیب تصادفی هم آن را عوض نمی‌کند.</div>';
    return html;
  }

  // ---- modal -------------------------------------------------------------
  var confirmResolver = null;

  function openModal(type, extra) {
    var focused = document.activeElement;
    ui.lastFocus = focused && root.contains(focused) ? focused : null;
    ui.modal = Object.assign({ type: type }, extra || {});
    if (app) app.inert = true;
    renderModal();
    requestAnimationFrame(function () {
      var first = modalRoot.querySelector('.modal button:not(:disabled), .modal input, .modal select');
      if (first) first.focus();
    });
  }

  function closeModal(restore) {
    if (ui.busy && !ui.publishing) return;
    if (ui.publishing) return;
    var modal = ui.modal;
    ui.modal = null;
    if (app) app.inert = false;
    modalRoot.innerHTML = '';
    if (modal && modal.type === 'confirm' && confirmResolver) {
      var resolve = confirmResolver;
      confirmResolver = null;
      resolve(Boolean(modal.accepted));
    }
    if (restore !== false && ui.lastFocus && document.body.contains(ui.lastFocus)) {
      ui.lastFocus.focus({ preventScroll: true });
    }
  }

  function renderModal() {
    var m = ui.modal;
    if (!m) { modalRoot.innerHTML = ''; return; }
    var focus = document.activeElement;
    var restoreFocus = focus && modalRoot.contains(focus);
    var focusControl = restoreFocus ? focus.getAttribute('data-control') : null;
    var focusAction = restoreFocus ? focus.getAttribute('data-rastisi-action') : null;
    var focusKey = restoreFocus ? (focus.getAttribute('data-theme-key') || focus.getAttribute('data-key') || focus.getAttribute('data-filter')) : null;
    var busy = ui.busy;
    var title = '', sub = '', body = '', foot = '', top = '', cls = '';
    var tmpl = currentTemplate();
    switch (m.type) {
      case 'templates':
        cls = 'gallery-modal';
        title = 'فروشگاه شما، با یک نگاه تازه.';
        sub = num((DATA.templates || []).length) + ' قالب آماده؛ هر قالب دستور طراحی تمام فروشگاه است و محتوای شما حفظ می‌شود.';
        top = '<div class="gallery-topline"><div class="filters">' +
          [['all', 'همه'], ['current', 'قالب فعلی']].map(function (f) {
            return btn('template-filter', f[1], '', ui.filter === f[0] ? 'active' : '', 'data-filter="' + f[0] + '" aria-pressed="' + (ui.filter === f[0]) + '" ' + (busy ? 'disabled' : ''));
          }).join('') + '</div><label><span class="visually-hidden">جست‌وجوی قالب</span><input class="input" data-control="template-search" placeholder="نام قالب را پیدا کنید…" value="' + esc(ui.query) + '" ' + (busy ? 'disabled' : '') + '></label></div>';
        body = (busy ? '<div class="note"><i class="spinner"></i> در حال آماده‌سازی قالب؛ محتوای شما محفوظ است…</div>' : '') +
          '<div class="gallery-grid" data-rs-gallery-grid>' + templateTiles() + '</div>';
        foot = '<p>' + icon('lock') + ' محصولات، تصاویر و متن‌ها حفظ می‌شوند. تغییر قالب قابل واگرد است.</p>' + btn('close-modal', 'بازگشت به استودیو', 'arrow', 'outline', busy ? 'disabled' : '');
        break;
      case 'add-section':
        title = 'چه چیزی به این صفحه اضافه کنیم؟';
        sub = 'یک بخش جدید، فقط در همین صفحه.';
        body = '<div data-rs-add-section-slot></div>';
        break;
      case 'remove-section':
        title = 'این بخش از صفحه حذف شود؟';
        body = '<p class="modal-message">محصولات فروشگاه حذف نمی‌شوند؛ فقط این بخش از چیدمان صفحه برداشته می‌شود. می‌توانید آن را واگرد کنید.</p>';
        foot = btn('confirm-remove', 'حذف بخش', 'trash', 'outline danger') + btn('close-modal', 'نگه داشتن بخش', '', 'primary');
        break;
      case 'confirm':
        title = m.title || 'ادامه می‌دهید؟';
        body = '<p class="modal-message">' + esc(m.message) + '</p>';
        foot = btn('confirm-accept', m.acceptLabel || 'ادامه', '', 'outline danger') + btn('close-modal', 'انصراف', '', 'primary');
        break;
      case 'exit-lab':
        title = 'این ایدهٔ موقت را کنار بگذاریم؟';
        body = '<p class="modal-message">با خروج، ترکیب آزمایشی و قفل‌های آن از بین می‌روند. هیچ چیزی از پیش‌نویس یا نسخهٔ عمومی تغییر نمی‌کند.</p>';
        foot = btn('confirm-exit', 'خروج بدون اعمال', '', 'outline danger') + btn('close-modal', 'ادامهٔ آزمایش', '', 'primary');
        break;
      case 'restart-lab':
        title = 'با آخرین پیش‌نویس شروع کنید';
        body = '<p class="modal-message">پیش‌نویس در جای دیگری تغییر کرده است. ترکیب موقت قدیمی کنار گذاشته می‌شود و آزمایش تازه از جدیدترین طرح شروع خواهد شد. هیچ کار جدیدتری بازنویسی نمی‌شود.</p>';
        foot = btn('confirm-restart', 'شروع آزمایش تازه', 'refresh', 'primary') + btn('close-modal', 'بازگشت', '', 'outline');
        break;
      case 'lab-theme':
        title = 'یک مناسبت، روی طرح شما';
        sub = 'موقت؛ فقط در آزمایش. تا قبل از اعمال وارد پیش‌نویس نمی‌شود.';
        body = themeControls(candidateTheme(), true);
        foot = btn('close-modal', 'دیدن نتیجه در فروشگاه', 'eye', 'primary');
        break;
      case 'lab-diffs': {
        title = 'در این آزمایش چه چیزی تغییر کرده؟';
        sub = 'سمت راست، نام بخش؛ از طرح شروع به انتخاب آزمایشی شما.';
        var fd = familyDiffs();
        body = '<div class="diff-list">' + (fd.length ? fd.map(function (d) {
          var values = d.base_label === d.candidate_label && d.settings_changed
            ? '<span class="pill purple">تنظیمات تغییر کرده</span>'
            : '<del>' + esc(d.base_label || '—') + '</del> ← ' + esc(d.candidate_label || '—');
          return '<div class="diff-row"><strong>' + esc(FAMILY_LABELS[d.family] || d.family_label) + '</strong><span class="diff-values">' + values + '</span></div>';
        }).join('') : '<div class="empty">بخش‌های طراحی هنوز تغییری نکرده‌اند.</div>') +
          (themeDiff() ? '<div class="diff-row"><strong>پوشش مناسبتی</strong><span class="pill purple">تغییر کرده</span></div>' : '') + '</div>';
        foot = btn('dock-compare', 'مقایسه در پیش‌نمایش', 'eye', 'primary') + btn('close-modal', 'بستن', '', 'outline');
        break;
      }
      case 'lab-options':
        title = 'ابزارهای آزمایش';
        sub = 'این کارها فقط روی ترکیب موقت شما اثر دارند.';
        body = '<div class="lab-options-grid"><div class="lab-option">' + icon('undo') + '<h3>شروع آزمایش از نو</h3><p>برگشت به طرح هنگام شروع آزمایش؛ قفل‌ها هم باز می‌شوند.</p>' + btn('dock-reset', 'برگشت به شروع', '', 'outline full') + '</div>' +
          '<div class="lab-option">' + icon('refresh') + '<h3>سبک اولیهٔ قالب</h3><p>برگشت به ترکیب اصلی قالب فعلی؛ مستقل از قفل‌ها و با حفظ مناسبت.</p>' + btn('dock-dna', 'بازگشت به سبک اولیه', '', 'outline full') + '</div></div>' +
          '<div class="note">هیچ‌کدام به معنی حذف پیش‌نویس یا تغییر نسخهٔ عمومی نیست. اعمال طراحی و انتشار، دو تصمیم جداگانه‌اند.</div>';
        foot = btn('dock-exit', 'خروج از آزمایش', '', 'danger outline') + btn('close-modal', 'ادامهٔ آزمایش', '', 'primary');
        break;
      case 'publish':
        title = 'این طراحی را به مشتری‌ها نشان دهیم؟';
        sub = 'انتشار تمام فروشگاه';
        body = '<p class="modal-message">پیش‌نویس فعلی به نسخهٔ عمومی تبدیل می‌شود. همهٔ صفحه‌های فروشگاه با همین طراحی نمایش داده خواهند شد.</p>' +
          '<div class="publish-summary"><div><span>فروشگاه</span><strong>' + esc(DATA.store_name) + '</strong></div><div><span>قالب</span><strong>' + esc(tmpl ? tmpl.label : '—') + '</strong></div><div><span>محدودهٔ انتشار</span><strong>تمام صفحه‌ها</strong></div></div>' +
          (ui.publishing ? '<div class="progress"></div><p class="small muted" role="status">در حال انتشار طراحی…</p>' : '<p class="small muted">پس از انتشار، پیش‌نویس و نسخهٔ عمومی همگام می‌شوند.</p>');
        foot = btn('confirm-publish', ui.publishing ? 'در حال انتشار…' : 'بله، منتشر کن', 'globe', 'primary', ui.publishing ? 'disabled' : '') + btn('close-modal', 'هنوز نه', '', 'outline', ui.publishing ? 'disabled' : '');
        break;
      case 'published':
        title = 'طراحی تازه، منتشر شد.';
        body = '<div class="success-body"><div class="success-art">' + icon('check') + '</div><h2>به ویترین تازه‌تان خوش آمدید.</h2><p>پیش‌نویس و نسخهٔ عمومی همگام هستند.' + (ui.publishedAt ? '<br>منتشرشده در ساعت ' + esc(faDigits(ui.publishedAt)) : '') + '</p></div>';
        foot = (DATA.public_url ? btn('view-published', 'دیدن فروشگاه', 'external', 'primary') : '') + btn('close-modal', 'بازگشت به استودیو', '', 'outline');
        break;
      case 'publish-error':
        title = 'انتشار انجام نشد';
        body = '<div class="note error">انتشار کامل نشد. پیش‌نویس و نسخهٔ عمومی قبلی حفظ شده‌اند. دوباره تلاش کنید.</div>';
        foot = btn('confirm-publish', 'تلاش دوباره', 'refresh', 'primary') + btn('close-modal', 'بعداً', '', 'outline');
        break;
      case 'history':
        title = 'مسیر تغییرات شما';
        sub = 'تاریخچهٔ پیش‌نویس؛ آزمایش‌های اعمال‌نشده اینجا ثبت نمی‌شوند.';
        body = '<div class="row">' + btn('history-undo', 'واگرد', 'undo', 'outline', !ui.canUndo || ui.lab.active ? 'disabled' : '') + btn('history-redo', 'بازگردانی', 'redo', 'outline', !ui.canRedo || ui.lab.active ? 'disabled' : '') + '</div>' +
          (ui.history.length ? ui.history.map(function (h, i) {
            return '<div class="history-item"><span class="muted">' + num(ui.history.length - i) + ' / </span>' + esc(h.label) + (h.at ? ' <small class="muted">· ' + esc(faDigits(h.at)) + '</small>' : '') + '</div>';
          }).join('') : '<div class="empty">هنوز تغییری ثبت نشده است.<br>یک بخش را ویرایش کنید یا ایده‌ای را اعمال کنید.</div>') +
          '<div class="section-divider"></div><div class="note">' + (ui.hasPublished ? 'آخرین انتشار: ' + esc(faDigits(ui.publishedAt || '')) : 'فروشگاه هنوز منتشر نشده است.') + '<br>واگرد، نسخهٔ عمومی را تغییر نمی‌دهد.</div>';
        foot = btn('discard', 'کنار گذاشتن پیش‌نویس', 'trash', 'danger', ui.lab.active || !ui.draftChanged ? 'disabled' : '') + btn('close-modal', 'بستن', '', 'outline');
        break;
      case 'discard':
        title = 'از تمام تغییرات منتشرنشده صرف‌نظر می‌کنید؟';
        body = '<p class="modal-message">پیش‌نویس با ' + (ui.hasPublished ? 'آخرین نسخهٔ منتشرشده' : 'طرح اولیهٔ فروشگاه') + ' جایگزین می‌شود. این کار با از نو شروع کردن آزمایش یا تغییر قالب فرق دارد.</p><div class="note warn" style="margin-top:18px">نسخهٔ عمومی تغییر نمی‌کند. کنار گذاشتن پیش‌نویس قابل واگرد نیست.</div>';
        foot = btn('confirm-discard', 'کنار گذاشتن پیش‌نویس', 'trash', 'danger outline', busy ? 'disabled' : '') + btn('close-modal', 'حفظ تغییرات', '', 'primary', busy ? 'disabled' : '');
        break;
      case 'save-issue':
        title = ui.saveState === 'conflict' ? 'پیش‌نویس در جای دیگری تغییر کرده' : 'ذخیره کامل نشد';
        body = '<p class="modal-message">' + (ui.saveState === 'conflict'
          ? 'نسخهٔ جدیدتر را دریافت کنید تا هیچ کار جدیدی بازنویسی نشود. آزمایش قدیمی قابل اعمال نخواهد بود.'
          : 'آخرین تغییر روی سرور ثبت نشد و پیش‌نویس ذخیره‌شده دست‌نخورده است. برای ادامه، نسخهٔ ذخیره‌شده را دوباره بارگذاری کنید.') + '</p>';
        foot = btn('save-reload', ui.saveState === 'conflict' ? 'دریافت نسخهٔ جدید' : 'بارگذاری نسخهٔ ذخیره‌شده', 'refresh', 'primary') + btn('close-modal', 'بعداً', '', 'outline');
        break;
      case 'help':
        title = 'راهنمای استودیوی طراحی';
        sub = 'هر تغییر، اول در پیش‌نویس ذخیره می‌شود و فقط با «انتشار» به مشتری‌ها می‌رسد.';
        body = '<div class="note" style="margin-bottom:18px">از نوار بالایی، بین ویرایش صفحه، طراحی سراسری و آزمایشگاه جابه‌جا شوید. میز آزمایش پایین بوم است؛ هر هفت بخش طراحی را کنار هم می‌بینید.</div>' +
          '<div class="lab-options-grid">' +
            '<div class="lab-option">' + icon('layers') + '<h3>ویرایش صفحه</h3><p>روی هر بخش در پیش‌نمایش یا فهرست ساختار کلیک کنید تا تنظیمات همان بخش باز شود.</p></div>' +
            '<div class="lab-option">' + icon('sliders') + '<h3>طراحی سراسری</h3><p>رنگ، نوشتار، قالب و مناسبت؛ روی تمام صفحه‌های فروشگاه.</p></div>' +
            '<div class="lab-option">' + icon('spark') + '<h3>آزمایشگاه</h3><p>ترکیب‌های تازه را موقت ببینید و فقط اگر دوست داشتید در پیش‌نویس اعمال کنید.</p></div>' +
            '<div class="lab-option">' + icon('globe') + '<h3>انتشار</h3><p>پیش‌نویس را به نسخهٔ عمومی تبدیل می‌کند؛ تا آن لحظه مشتری‌ها طرح قبلی را می‌بینند.</p></div>' +
          '</div><div class="section-divider"></div><p class="small muted">Ctrl / ⌘ + Z: واگرد · Shift + Z: بازگردانی · Escape: بستن پنجره</p>';
        foot = btn('close-modal', 'متوجه شدم', '', 'primary');
        break;
      default:
        return;
    }
    modalRoot.innerHTML = '<div class="modal-backdrop"><section class="modal ' + cls + '" role="dialog" aria-modal="true" aria-labelledby="rsDialogTitle">' +
      '<header class="modal-head"><div><h2 id="rsDialogTitle">' + title + '</h2>' + (sub ? '<p>' + sub + '</p>' : '') + '</div>' +
      btn('close-modal', '', 'close', 'icon-btn', 'aria-label="بستن پنجره" ' + (busy || ui.publishing ? 'disabled' : '')) + '</header>' +
      top + '<div class="modal-body">' + body + '</div>' + (foot ? '<footer class="modal-foot">' + foot + '</footer>' : '') + '</section></div>';

    if (m.type === 'add-section') {
      // The chooser markup is the server-rendered one from the Structure
      // panel (its controls keep the R4 hooks R4 handles).
      var slot = modalRoot.querySelector('[data-rs-add-section-slot]');
      var template = structurePanel ? structurePanel.querySelector('template[data-rs-add-section-template]') : null;
      if (slot && template) slot.appendChild(template.content.cloneNode(true));
    }
    if (restoreFocus) {
      var target = null;
      if (focusControl) target = modalRoot.querySelector('[data-control="' + focusControl + '"]');
      else if (focusAction) {
        target = $all('[data-rastisi-action="' + focusAction + '"]', modalRoot).filter(function (b) {
          return (b.getAttribute('data-theme-key') || b.getAttribute('data-key') || b.getAttribute('data-filter')) === focusKey;
        })[0];
      }
      if (target) target.focus({ preventScroll: true });
    }
  }

  // Lifecycle confirmations (reset page / reset storefront) use the
  // workspace dialog instead of the browser prompt.
  R4.confirm = function (message) {
    return new Promise(function (resolve) {
      if (confirmResolver) confirmResolver(false);
      confirmResolver = resolve;
      openModal('confirm', { message: message, title: 'تأیید بازنشانی', acceptLabel: 'بله، بازنشانی کن' });
    });
  };

  // ---- publish / discard -------------------------------------------------
  function publish() {
    if (ui.lab.active || ui.publishing) return;
    if (!ui.modal || (ui.modal.type !== 'publish' && ui.modal.type !== 'publish-error')) return;
    ui.modal = { type: 'publish' };
    ui.publishing = true;
    ui.busy = true;
    renderModal();
    renderChrome();
    R4.publish().then(function (result) {
      if (result && result.ok) return; // the workspace reloads
      ui.publishing = false;
      ui.busy = false;
      if (ui.saveState === 'conflict') {
        ui.modal = { type: 'save-issue' };
      } else {
        ui.modal = { type: 'publish-error' };
      }
      renderModal();
      renderChrome();
    });
  }

  function discard() {
    if (ui.lab.active || ui.busy) return;
    ui.busy = true;
    renderModal();
    R4.discard().then(function (result) {
      if (result && result.ok) return; // the workspace reloads
      ui.busy = false;
      renderChrome();
      closeModal();
      if (ui.saveState !== 'conflict') notify('کنار گذاشتن پیش‌نویس انجام نشد؛ دوباره تلاش کنید.');
    });
  }

  function historyCommand(command) {
    if (ui.lab.active) return;
    var run = command === 'redo' ? R4.redo : R4.undo;
    run().then(function (result) {
      if (result && result.ok && !result.changed) notify(command === 'redo' ? 'چیزی برای بازگردانی نیست.' : 'چیزی برای واگرد نیست.');
    });
  }

  // ---- click routing (UI actions only) -----------------------------------
  // Actions owned by r4_editor.js listeners on the same element are NOT
  // handled here (device buttons, #r4UndoButton/#r4RedoButton, section rows,
  // add-section choices, theme/global fields): one event, one operation.
  root.addEventListener('click', function (evt) {
    var el = evt.target.closest('[data-rastisi-action]');
    if (!el || el.disabled || !root.contains(el)) return;
    var action = el.getAttribute('data-rastisi-action');
    if (ui.busy && ['panel-toggle', 'panel-close', 'show-base', 'show-candidate', 'close-modal'].indexOf(action) === -1) return;
    switch (action) {
      case 'structure': setMode('structure'); break;
      case 'global':
        if (el.hasAttribute('data-rs-global-focus')) focusGlobalRegion(el.getAttribute('data-rs-global-focus'));
        else setMode('global');
        break;
      case 'lab': setMode('lab'); break;
      case 'help': openModal('help'); break;
      case 'templates': openTemplateGallery(); break;
      case 'panel-toggle': ui.panelVisible = !ui.panelVisible; renderChrome(); break;
      case 'panel-close': ui.panelVisible = false; renderChrome(); break;
      case 'global-tab': setGlobalTab(el.getAttribute('data-tab')); break;
      case 'add-section': openModal('add-section'); break;
      case 'section-enable': sectionCommand('toggle_active'); break;
      case 'section-lock': sectionCommand('toggle_locked'); break;
      case 'section-up': sectionCommand('up'); break;
      case 'section-down': sectionCommand('down'); break;
      case 'section-duplicate': sectionCommand('duplicate'); break;
      case 'section-reset': sectionCommand('reset_to_baseline'); break;
      case 'section-move-cell': {
        var cellSelect = $('[data-rs-move-cell]');
        if (cellSelect && cellSelect.value) sectionCommand('move_to_cell', { cellId: cellSelect.value });
        break;
      }
      case 'section-remove': openModal('remove-section', { sectionId: ui.selectedSectionId }); break;
      case 'confirm-remove': {
        var removeId = ui.modal && ui.modal.sectionId;
        closeModal(false);
        if (removeId != null) R4.sectionCommand(removeId, 'remove');
        break;
      }
      case 'confirm-accept':
        if (ui.modal) ui.modal.accepted = true;
        closeModal(false);
        break;
      case 'close-modal': closeModal(); break;
      case 'template-filter':
        ui.filter = el.getAttribute('data-filter') || 'all';
        renderModal();
        break;
      case 'preview-template': previewTemplate(el.getAttribute('data-key')); break;
      case 'cancel-template-preview': cancelTemplatePreview(); break;
      case 'switch-template': switchTemplate(el.getAttribute('data-key')); break;
      case 'public-preview':
      case 'view-published':
        if (ui.lab.active) { notify('ابتدا آزمایش را اعمال کنید یا از آن خارج شوید.'); return; }
        if (DATA.public_url) window.open(DATA.public_url, '_blank', 'noopener');
        break;
      case 'history': openModal('history'); refreshStatus(); break;
      case 'history-undo': historyCommand('undo'); break;
      case 'history-redo': historyCommand('redo'); break;
      case 'publish': if (!ui.lab.active) openModal('publish'); break;
      case 'confirm-publish': publish(); break;
      case 'discard': openModal('discard'); break;
      case 'confirm-discard': discard(); break;
      case 'save-issue': openModal('save-issue'); break;
      case 'save-reload': window.location.reload(); break;
      // Design Lab — every operation is R4.lab (r4_editor.js).
      case 'start-lab': R4.lab.start(); break;
      case 'restart-lab': openModal('restart-lab'); break;
      case 'confirm-restart': closeModal(false); R4.lab.restart(); break;
      case 'confirm-exit': {
        var next = (ui.modal && ui.modal.nextMode) || 'structure';
        var navigate = ui.modal && ui.modal.navigate;
        closeModal(false);
        R4.lab.exit();
        if (navigate) window.location.assign(navigate);
        else setMode(next);
        break;
      }
      case 'random-mix': R4.lab.randomMix(); break;
      case 'random-family': R4.lab.randomizeFamily(el.getAttribute('data-family')); break;
      case 'lock-family': R4.lab.toggleLock(el.getAttribute('data-family')); break;
      case 'focus-family': focusPreviewFamily(el.getAttribute('data-family')); break;
      case 'show-base': R4.lab.showBase(); break;
      case 'show-candidate': R4.lab.showCandidate(); break;
      case 'apply-candidate': R4.lab.apply(); break;
      case 'lab-theme': openModal('lab-theme'); break;
      case 'lab-diffs': openModal('lab-diffs'); break;
      case 'lab-options': openModal('lab-options'); break;
      case 'lab-set-theme': {
        var key = el.getAttribute('data-theme-key');
        if (key === THEME_NONE) R4.lab.removeTheme();
        else R4.lab.setTheme(key, candidateTheme().intensity || 'balanced');
        break;
      }
      case 'lab-remove-theme': R4.lab.removeTheme(); break;
      case 'dock-reset': closeModal(false); R4.lab.resetToBase(); break;
      case 'dock-dna': closeModal(false); R4.lab.returnToTemplateDna(); break;
      case 'dock-exit':
        closeModal(false);
        if (ui.lab.diffs && ui.lab.diffs.length) openModal('exit-lab', { nextMode: 'structure' });
        else { R4.lab.exit(); setMode('structure'); }
        break;
      case 'dock-compare':
        closeModal(false);
        if (ui.lab.compareBase) R4.lab.showCandidate(); else R4.lab.showBase();
        break;
      default: break;
    }
  });

  // Showcase / add choices inside the dialog: R4 performs the mutation; the
  // dialog simply closes.
  modalRoot.addEventListener('click', function (evt) {
    var choice = evt.target.closest('[data-r4-showcase-choice], #r4StructureAddButton');
    if (!choice || !ui.modal || ui.modal.type !== 'add-section') return;
    if (choice.id === 'r4StructureAddButton') {
      var select = modalRoot.querySelector('#r4StructureAddSelect');
      if (!select || !select.value) { notify('یک بخش انتخاب کنید.'); return; }
    }
    setTimeout(function () { closeModal(); notify('بخش تازه به انتهای صفحه اضافه شد.'); }, 0);
  });

  modalRoot.addEventListener('click', function (evt) {
    if (evt.target.classList && evt.target.classList.contains('modal-backdrop') && !ui.busy) closeModal();
  });

  root.addEventListener('input', function (evt) {
    if (evt.target.getAttribute('data-control') === 'template-search') {
      ui.query = evt.target.value;
      var grid = modalRoot.querySelector('[data-rs-gallery-grid]');
      if (grid) grid.innerHTML = templateTiles();
    }
  });

  root.addEventListener('change', function (evt) {
    var control = evt.target.getAttribute('data-control');
    if (control === 'zoom' && R4.setZoom) R4.setZoom(evt.target.value);
    if (control === 'lab-intensity') {
      var theme = candidateTheme();
      if (theme.key && theme.key !== THEME_NONE) R4.lab.setTheme(theme.key, evt.target.value);
    }
    if (control === 'page') {
      var target = new URL(window.location.href);
      target.searchParams.set('page', evt.target.value);
      target.searchParams.delete('studio_notice');
      if (ui.lab.active) {
        evt.target.value = DATA.page_type;
        openModal('exit-lab', { navigate: target.pathname + target.search });
        return;
      }
      window.location.assign(target.pathname + target.search);
    }
  });

  // ---- keyboard ----------------------------------------------------------
  document.addEventListener('keydown', function (evt) {
    // Escape only closes presentation layers (dialog first, then the admin
    // navigation overlay). It never mutates, never discards, never exits the
    // Design Lab and never answers a confirmation with "yes".
    if (evt.key === 'Escape' && !ui.modal && root.dataset.r4SidebarExpanded === 'true') {
      var sidebarToggle = document.getElementById('r4SidebarToggle');
      if (sidebarToggle) { sidebarToggle.click(); sidebarToggle.focus(); }
      return;
    }
    if (evt.key === 'Escape' && ui.modal && !ui.busy && !ui.publishing) {
      evt.preventDefault();
      closeModal();
      return;
    }
    if (evt.key === 'Tab' && ui.modal) {
      var focusable = $all('.modal button:not(:disabled), .modal input:not(:disabled), .modal select:not(:disabled), .modal summary, .modal [tabindex="0"]', modalRoot);
      if (!focusable.length) return;
      var inside = document.activeElement && modalRoot.contains(document.activeElement);
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (!inside) {
        evt.preventDefault();
        (evt.shiftKey ? last : first).focus();
      } else if (evt.shiftKey && document.activeElement === first) {
        evt.preventDefault();
        last.focus();
      } else if (!evt.shiftKey && document.activeElement === last) {
        evt.preventDefault();
        first.focus();
      }
      return;
    }
    if ((evt.ctrlKey || evt.metaKey) && String(evt.key).toLowerCase() === 'z') {
      var tag = evt.target && evt.target.tagName;
      if (['INPUT', 'TEXTAREA', 'SELECT'].indexOf(tag) !== -1 || (evt.target && evt.target.isContentEditable)) return;
      if (ui.modal || ui.lab.active || ui.busy) return;
      if (evt.shiftKey ? !ui.canRedo : !ui.canUndo) return;
      evt.preventDefault();
      historyCommand(evt.shiftKey ? 'redo' : 'undo');
    }
  });

  // ---- R4 state events ---------------------------------------------------
  root.addEventListener('r4:savestate', function (evt) {
    var previous = ui.saveState;
    ui.saveState = evt.detail.state;
    renderSaveFeedback();
    if (ui.saveState === 'saved' && previous === 'saving') {
      ui.draftChanged = true;
      scheduleStatusRefresh();
    }
    if (ui.saveState === 'conflict' && !ui.conflictShown) {
      ui.conflictShown = true;
      if (!ui.modal) openModal('save-issue');
      else if (ui.modal.type === 'publish' || ui.modal.type === 'discard') { ui.modal = { type: 'save-issue' }; renderModal(); }
    }
    renderChrome();
  });

  root.addEventListener('r4:inspector-opened', function (evt) {
    ui.selectedSectionId = evt.detail.sectionId;
    if (ui.mode === 'template-preview') { ui.previewTemplate = null; R4.showPreview(null); }
    ui.mode = 'inspector';
    ui.panelVisible = true;
    renderInspectorChrome();
    markSelectedRow();
    renderChrome();
  });

  root.addEventListener('r4:inspector-closed', function () {
    if (inspectorAside) inspectorAside.inert = false;
    if (ui.mode === 'inspector') {
      ui.mode = 'structure';
      renderChrome();
    }
    markSelectedRow();
  });

  root.addEventListener('r4:global-opened', function () {
    if (ui.mode !== 'global' && !ui.lab.active) {
      ui.mode = 'global';
      renderChrome();
    }
  });

  root.addEventListener('r4:structure-refreshed', function () {
    var countPill = $('[data-rs-section-count]');
    if (countPill) countPill.textContent = num($all('[data-r4-structure-row]', structurePanel).length) + ' بخش';
    if (ui.mode === 'inspector') renderInspectorChrome();
    markSelectedRow();
  });

  root.addEventListener('r4:global-refreshed', function () {
    if (ui.mode === 'global') setGlobalTab(root.dataset.rsGlobalTab || 'visual');
  });

  root.addEventListener('r4:device', function (evt) {
    var width = $('[data-rs-device-width]');
    if (width) width.textContent = evt.detail.width + ' px';
  });

  root.addEventListener('r4:lab', function (evt) { onLabState(evt.detail); });

  root.addEventListener('r4:lab-applied', function () {
    ui.mode = 'structure';
    ui.draftChanged = true;
    notify('طراحی به پیش‌نویس اعمال شد. برای نمایش عمومی، منتشر کنید.');
    scheduleStatusRefresh();
    renderChrome();
  });

  // ---- initial state -----------------------------------------------------
  (function init() {
    // Deep links (?panel=appearance|header|footer) already opened Global
    // Design inside R4; follow it.
    if (R4.isGlobalDesignOpen && R4.isGlobalDesignOpen()) ui.mode = 'global';
    renderSaveFeedback();
    setGlobalTab(root.dataset.rsGlobalTab || 'visual');
    renderChrome();

    var params = new URLSearchParams(window.location.search);
    var notice = params.get('studio_notice');
    if (notice) {
      params.delete('studio_notice');
      var clean = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState(null, '', clean);
      if (notice === 'published') {
        openModal('published');
        notify('فروشگاه با موفقیت منتشر شد.');
      } else if (notice === 'template') {
        notify('قالب تغییر کرد؛ محصولات، محتوا و ساختار صفحه حفظ شدند.');
      } else if (notice === 'discarded') {
        notify(ui.hasPublished ? 'پیش‌نویس به آخرین نسخهٔ منتشرشده برگشت.' : 'پیش‌نویس به طراحی اولیه برگشت.');
      }
    }
  })();
})();
