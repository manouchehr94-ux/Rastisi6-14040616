/*
 * RastiSi Design Studio — on-canvas layer: contextual section toolbar + visual resize handles.
 *
 * UI-ONLY. It lives in the Studio shell (a transparent overlay above #r4PreviewFrame), never inside the storefront document, so nothing of it
 * can reach the published page and no invisible layer lies over the content: the overlay itself has pointer-events:none, only the toolbar
 * buttons and the handles are hit-testable. It owns no business state — selection, dialogs and toasts stay in r4_studio.js (R4.studio) and
 * every write goes through the ONE mutation queue (R4.enqueueStructuralMutation):
 *
 *   section.resize    one section's manual size  (settings.design: min_height / width_pct / width_align; Auto = key absent)
 *   container.resize  column widths (Cell.span) and the stacked layout's height split (Container.settings.stack_split)
 *
 * A drag previews LIVE by writing temporary inline CSS custom properties on the preview elements (the same variables the stylesheet reads),
 * sends NOTHING while the pointer moves, and on release sends exactly ONE mutation (= one Revision, one Undo step). Escape cancels and
 * restores the exact previous state; a refused or failed save restores it too and tells the merchant in Persian.
 */
(function () {
  'use strict';

  var R4 = window.RastiSiR4;
  var S = R4 && R4.studio;
  var root = document.querySelector('.rs-studio[data-r4-shell]');
  var canvas = root && root.querySelector('.canvas');
  if (!R4 || !S || !root || !canvas) return;

  var FRAMES = '.hero-inner, .fashion-hero-inner, .hero-split-inner, .hero-atelier-inner, .hero-luxury-stage, .promo-dark';
  var MAX_HEIGHT = 1600;
  var MIN_WIDTH_PCT = 30;
  var STACKED = 'big_right_two_left';
  var STACKED_BIG = [4, 9];
  var SPLIT_RANGE = [25, 75];
  var KEY_STEP = 16;

  // ---- overlay skeleton ----------------------------------------------------
  var overlay = document.createElement('div');
  overlay.className = 'rs-overlay';
  overlay.setAttribute('data-rs-overlay', '');
  overlay.innerHTML =
    '<div class="rs-sel-toolbar" role="toolbar" aria-label="ابزار بخش انتخاب‌شده" data-rs-sel-toolbar hidden>' +
      tbButton('edit', 'edit', 'ویرایش', true) + tbButton('duplicate', 'copy', 'تکثیر بخش') + tbButton('up', 'up', 'انتقال به بالا') +
      tbButton('down', 'down', 'انتقال به پایین') + tbButton('remove', 'trash', 'حذف بخش') + tbButton('close', 'close', 'بستن منو') +
    '</div>' +
    '<div class="rs-hint" role="status" data-rs-hint hidden></div>' +
    '<button type="button" class="rs-auto-chip" data-rs-auto hidden>اندازه خودکار</button>';
  canvas.appendChild(overlay);

  function tbButton(action, iconName, label, primary) {
    return '<button type="button" class="rs-tb-btn' + (primary ? ' primary' : '') + '" data-rs-sel="' + action + '" aria-label="' + label + '" title="' + label + '">' +
      S.icon(iconName) + (primary ? '<span>' + label + '</span>' : '') + '</button>';
  }

  var toolbar = overlay.querySelector('[data-rs-sel-toolbar]');
  var hintEl = overlay.querySelector('[data-rs-hint]');
  var autoChip = overlay.querySelector('[data-rs-auto]');
  var handles = {};            // key -> element (reused between renders)
  var hoverContainerId = null;
  var drag = null;             // the one active drag / keyboard session
  var frameWindows = [];

  // ---- geometry ------------------------------------------------------------
  function frame() { return document.getElementById('r4PreviewFrame'); }

  function mapping() {
    var f = frame();
    if (!f || !f.contentWindow) return null;
    var doc;
    try { doc = f.contentDocument; } catch (e) { return null; }
    if (!doc || !doc.documentElement) return null;
    var fr = f.getBoundingClientRect();
    var width = f.clientWidth || fr.width;
    return { f: f, doc: doc, win: f.contentWindow, fr: fr, k: width ? fr.width / width : 1, ov: overlay.getBoundingClientRect() };
  }

  // a preview element's rect in OVERLAY coordinates (the iframe may be scaled by the device / zoom mode)
  function box(m, el) {
    var r = el.getBoundingClientRect();
    return { l: m.fr.left + r.left * m.k - m.ov.left, t: m.fr.top + r.top * m.k - m.ov.top, w: r.width * m.k, h: r.height * m.k };
  }

  function visibleArea(m) {
    return { l: m.fr.left - m.ov.left, t: m.fr.top - m.ov.top, r: m.fr.right - m.ov.left, b: m.fr.bottom - m.ov.top };
  }

  // Everything the contextual toolbar / handles must not lie on: the Studio's floating «افزودن بخش / لایه‌ها» bar, the visible handles, the
  // note, and the in-page «افزودن بخش به همین خانه» controls (their labels). Rectangles are in overlay coordinates.
  function obstacles(m, skip, controlsOnly) {
    var list = [];
    function add(r, margin) { if (r.width > 0 && r.height > 0) list.push({ l: r.left - m.ov.left - margin, t: r.top - m.ov.top - margin, r: r.right - m.ov.left + margin, b: r.bottom - m.ov.top + margin }); }
    Array.prototype.forEach.call(canvas.querySelectorAll('.rs-float-bar'), function (el) { add(el.getBoundingClientRect(), 8); });
    if (!controlsOnly) {
      Object.keys(handles).forEach(function (key) { var h = handles[key]; if (!h.hidden && h !== skip) add(h.getBoundingClientRect(), 4); });
      if (!hintEl.hidden && skip !== hintEl) add(hintEl.getBoundingClientRect(), 4);
    }
    Array.prototype.forEach.call(m.doc.querySelectorAll('.sfb-cell-add-more, .sfb-empty-cell-add'), function (el) {
      var parts = el.children.length ? Array.prototype.slice.call(el.children) : [el];
      var l = Infinity, t = Infinity, r = -Infinity, bt = -Infinity;
      parts.forEach(function (n) { var q = n.getBoundingClientRect(); if (q.width > 0) { l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); bt = Math.max(bt, q.bottom); } });
      if (l === Infinity) return;
      var o = box(m, { getBoundingClientRect: function () { return { left: l, top: t, width: r - l, height: bt - t }; } });
      list.push({ l: o.l - 4, t: o.t - 4, r: o.l + o.w + 4, b: o.t + o.h + 4 });
    });
    return list;
  }

  // how many sample points of a rectangle (overlay coordinates) lie on REAL content of the preview: a picture, a control, or actual text glyph boxes
  function contentHits(m, x, y, w, h) {
    var hits = 0;
    var sx = (m.fr.left - m.ov.left);
    var sy = (m.fr.top - m.ov.top);
    var cols = 7, rows = 3;
    for (var cx = 0; cx < cols; cx += 1) {
      for (var cy = 0; cy < rows; cy += 1) {
        var px = (x + (w * (cx + 0.5)) / cols - sx) / m.k;
        var py = (y + (h * (cy + 0.5)) / rows - sy) / m.k;
        var stack;
        try { stack = m.doc.elementsFromPoint(px, py); } catch (e) { return hits; }
        var el = stack && stack[0];
        if (!el || el === m.doc.documentElement || el === m.doc.body) continue;
        if (/^(IMG|SVG|VIDEO|CANVAS|BUTTON|A|INPUT|SELECT|TEXTAREA|PICTURE)$/i.test(el.tagName)) { hits += 1; continue; }
        if (hasTextAt(m, el, px, py)) hits += 1;
      }
    }
    return hits;
  }

  function hasTextAt(m, el, px, py) {
    var node = el.firstChild;
    while (node) {
      if (node.nodeType === 3 && /\S/.test(node.nodeValue)) {
        var range = m.doc.createRange();
        range.selectNodeContents(node);
        var rects = range.getClientRects();
        for (var i = 0; i < rects.length; i += 1) {
          var r = rects[i];
          if (px >= r.left - 2 && px <= r.right + 2 && py >= r.top - 2 && py <= r.bottom + 2) return true;
        }
      }
      node = node.nextSibling;
    }
    return false;
  }

  function overlapArea(x, y, w, h, list) {
    return list.reduce(function (sum, o) {
      var ix = Math.min(x + w, o.r) - Math.max(x, o.l);
      var iy = Math.min(y + h, o.b) - Math.max(y, o.t);
      return ix > 0 && iy > 0 ? sum + ix * iy : sum;
    }, 0);
  }

  // the nearest left coordinate (to `want`) at which a w x h box at height `t` clears every obstacle and stays inside [min, max]
  function clearX(want, t, w, h, list, min, max) {
    var candidates = [Math.max(min, Math.min(want, max - w))];
    list.forEach(function (o) { candidates.push(o.l - w, o.r); });
    var best = null;
    candidates.forEach(function (x) {
      if (x < min || x + w > max) return;
      var hit = list.some(function (o) { return x < o.r && x + w > o.l && t < o.b && t + h > o.t; });
      if (hit) return;
      if (best == null || Math.abs(x - want) < Math.abs(best - want)) best = x;
    });
    return best == null ? candidates[0] : best;
  }

  // Sizes are a DESKTOP-composition decision (the phone preview reflows the same rows): handles are offered on the desktop preview only,
  // the contextual toolbar is available everywhere
  function resizeAllowed() {
    var viewport = canvas.querySelector('.preview-viewport');
    var device = viewport ? viewport.getAttribute('data-r4-device') : 'desktop';
    return !device || device === 'desktop';
  }

  function sectionEl(m, id) { return id ? m.doc.querySelector('.rsec[data-section-id="' + id + '"]') : null; }
  function cellsOf(container) { return Array.prototype.filter.call(container.children, function (n) { return n.classList && n.classList.contains('rcontainer-cell'); }); }
  function isRtl(m) { return m.win.getComputedStyle(m.doc.documentElement).direction === 'rtl'; }

  // ---- render ---------------------------------------------------------------
  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () { scheduled = false; render(); });
  }

  function hideAll() {
    toolbar.hidden = true;
    autoChip.hidden = true;
    if (!drag) hintEl.hidden = true;
    Object.keys(handles).forEach(function (key) { handles[key].hidden = true; });
  }

  function handle(key, cls, label, orientation) {
    var el = handles[key];
    if (!el) {
      el = document.createElement('button');
      el.type = 'button';
      el.className = 'rs-handle ' + cls;
      el.setAttribute('data-rs-handle', key.split(':')[0]);
      el.setAttribute('role', 'separator');
      el.setAttribute('aria-orientation', orientation);
      el.tabIndex = 0;
      el.innerHTML = '<i aria-hidden="true"></i>';
      overlay.appendChild(el);
      handles[key] = el;
    }
    el.setAttribute('aria-label', label);
    el.title = label;
    el.hidden = false;
    return el;
  }

  function place(el, l, t, w, h) {
    el.style.left = Math.round(l) + 'px';
    el.style.top = Math.round(t) + 'px';
    if (w != null) el.style.width = Math.round(w) + 'px';
    if (h != null) el.style.height = Math.round(h) + 'px';
  }

  function render() {
    var m = mapping();
    var id = S.selectedId();
    var blocked = S.blocked();
    var usedKeys = {};
    var sectionBox = null;
    if (!m || blocked) { hideAll(); return; }
    var area = visibleArea(m);
    var sec = sectionEl(m, id);

    if (sec) {
      var b = box(m, sec);
      var onScreen = b.t + b.h > area.t + 4 && b.t < area.b - 4 && b.l + b.w > area.l && b.l < area.r;
      // an empty / hidden Section is only a placeholder in the builder: there is no real surface to size yet
      if (onScreen && resizeAllowed() && !sec.classList.contains('sfb-rsec-builder-empty')) renderSectionHandles(m, sec, b, area, usedKeys);
      sectionBox = onScreen ? b : null;
    }

    var container = null;
    if (hoverContainerId) container = m.doc.querySelector('.rcontainer[data-container-id="' + hoverContainerId + '"]');
    if (!container && sec) container = sec.closest('.rcontainer[data-container-id]');
    if (container && resizeAllowed()) renderContainerHandles(m, container, area, usedKeys);

    Object.keys(handles).forEach(function (key) { if (!usedKeys[key]) handles[key].hidden = true; });

    // the toolbar goes last: it is placed AROUND the handles and in-page controls, never on them
    if (sec && sectionBox) renderToolbar(m, id, sectionBox, area, sec);
    else { toolbar.hidden = true; autoChip.hidden = true; }
  }

  function renderToolbar(m, id, b, area, sec) {
    var state = S.rowState(id) || {};
    toolbar.hidden = false;
    toolbar.querySelector('[data-rs-sel="duplicate"]').disabled = state.locked === true || state.canDuplicate === false;
    toolbar.querySelector('[data-rs-sel="up"]').disabled = state.locked === true || state.canUp === false;
    toolbar.querySelector('[data-rs-sel="down"]').disabled = state.locked === true || state.canDown === false;
    toolbar.querySelector('[data-rs-sel="remove"]').disabled = state.canRemove === false;
    toolbar.querySelector('[data-rs-sel="edit"]').disabled = false;
    // a disabled control says WHY (never a silently dead button)
    [['duplicate', 'تکثیر بخش', 'این بخش قابل تکثیر نیست'], ['up', 'انتقال به بالا', 'این بخش از قبل بالاترین است'],
     ['down', 'انتقال به پایین', 'این بخش از قبل پایین‌ترین است'], ['remove', 'حذف بخش', 'این بخش قابل حذف نیست']].forEach(function (row) {
      var button = toolbar.querySelector('[data-rs-sel="' + row[0] + '"]');
      var why = state.locked === true ? 'بخش قفل است' : row[2];
      button.title = button.disabled ? why : row[1];
      button.setAttribute('aria-label', button.disabled ? row[1] + ' — ' + why : row[1]);
    });
    var tw = toolbar.offsetWidth || 230;
    var th = toolbar.offsetHeight || 40;
    var gap = 8;
    var list = obstacles(m, toolbar);
    var minL = area.l + 6, maxL = area.r - tw - 6;
    var right = Math.max(minL, Math.min(b.l + b.w - tw, maxL));       // aligned to the inline-start (right) edge of the section in this RTL shell
    var leftAligned = Math.max(minL, Math.min(b.l, maxL));
    function clampTop(t) { return Math.max(area.t + 2, Math.min(t, area.b - th - 2)); }
    // Candidate spots, best first: outside the section (above, then below), then along the section's own top edge. Each is scored by what it
    // would lie on — handles / in-page controls (heavily) and REAL content of the preview (text, pictures, buttons — sampled in the preview
    // document) — so the toolbar settles where it covers nothing important; the first clean spot wins.
    var step = Math.max(0, (b.w - tw) / 4);
    var candidates = [
      { x: right, y: b.t - th - gap, kind: 'above', pen: 0 }, { x: leftAligned, y: b.t - th - gap, kind: 'above', pen: 3 },
      { x: right, y: b.t + b.h + gap + 20, kind: 'below', pen: 6 }, { x: leftAligned, y: b.t + b.h + gap + 20, kind: 'below', pen: 9 },
    ];
    [0, 1, 2, 3, 4].forEach(function (n) { candidates.push({ x: b.l + b.w - tw - step * n, y: b.t + gap, kind: 'inside', pen: 12 + n }); });
    var best = null;
    for (var i = 0; i < candidates.length; i += 1) {
      var cand = candidates[i];
      if (cand.kind === 'above' && cand.y < area.t + 2) continue;
      if (cand.kind === 'below' && cand.y + th > area.b - 2) continue;
      var cx0 = Math.max(minL, Math.min(cand.x, maxL));
      var cy0 = clampTop(cand.y);
      var score = overlapArea(cx0, cy0, tw, th, list) * 10 + contentHits(m, cx0, cy0, tw, th) * 40 + cand.pen;
      if (best == null || score < best.score) best = { x: cx0, y: cy0, score: score };
      if (score <= 12) break;
    }
    if (best == null) best = { x: right, y: clampTop(b.t + gap), score: 1 };
    var left = clearX(best.x, best.y, tw, th, best.score ? list : [], minL, area.r - 6);
    var top = best.y;
    place(toolbar, left, top);
    // «اندازه خودکار» sits beside the toolbar while a manual size is set (one reset for height + width + placement)
    var manual = manualState(sec);
    var locked = state.locked === true;
    if ((manual.height || manual.width) && !locked) {
      autoChip.hidden = false;
      var cw = autoChip.offsetWidth || 96;
      var cx = clearX(left - cw - 8, top, cw, th, obstacles(m, autoChip).concat([{ l: left - 2, t: top - 2, r: left + tw + 2, b: top + th + 2 }]), area.l + 6, area.r - 6);
      place(autoChip, cx, top + (th - (autoChip.offsetHeight || 28)) / 2);
    } else { autoChip.hidden = true; }
  }

  // does a sibling Cell of this Section's row touch its left / right edge (a column boundary lies there)?
  function sharedEdges(m, sec, b) {
    var out = { left: false, right: false };
    var cell = sec.closest('.rcontainer-cell');
    var container = cell && cell.parentElement;
    if (!container) return out;
    cellsOf(container).forEach(function (other) {
      if (other === cell) return;
      var o = box(m, other);
      if (o.t > b.t + b.h || o.t + o.h < b.t) return;
      if (Math.abs((o.l + o.w) - b.l) < 28) out.left = true;
      if (Math.abs(o.l - (b.l + b.w)) < 28) out.right = true;
    });
    return out;
  }

  function manualState(sec) {
    var tokens = (sec.getAttribute('data-d') || '').split(/\s+/);
    return { height: tokens.indexOf('minh') !== -1, width: tokens.indexOf('w') !== -1 };
  }

  function renderSectionHandles(m, sec, b, area, used) {
    var manual = manualState(sec);
    var locked = (S.rowState(sec.getAttribute('data-section-id')) || {}).locked;
    // height: a bar centred on the bottom edge
    var bottomVisible = b.t + b.h <= area.b + 1 && b.t + b.h >= area.t + 4;
    if (bottomVisible && !locked) {
      var key = 'h';
      used[key] = true;
      var hb = handle(key, 'rs-handle-h', 'تغییر ارتفاع بخش — بکشید یا با کلیدهای بالا/پایین تنظیم کنید؛ دوبار کلیک: ارتفاع خودکار', 'horizontal');
      var hy = Math.min(b.t + b.h - 9, area.b - 20);
      place(hb, clearX(b.l + b.w / 2 - 36, hy - 12, 72, 42, obstacles(m, null, true), Math.max(b.l, area.l) + 4, Math.min(b.l + b.w, area.r) - 4), hy, 72, 18);
    }
    // width: pills inside both side edges, vertically centred in the visible part of the section
    if (!locked && b.w > 120) {
      var midY = Math.max(b.t, area.t) + (Math.min(b.t + b.h, area.b) - Math.max(b.t, area.t)) / 2;
      var left = handle('wl', 'rs-handle-w', 'تغییر عرض بخش (از چپ) — دوبار کلیک: عرض خودکار', 'vertical');
      var right = handle('wr', 'rs-handle-w', 'تغییر عرض بخش (از راست) — دوبار کلیک: عرض خودکار', 'vertical');
      used.wl = true; used.wr = true;
      // an edge shared with a neighbouring column belongs to the COLUMN handle: that side's pill moves inside the section so they never overlap
      var shared = sharedEdges(m, sec, b);
      place(left, shared.left ? b.l + 6 : Math.max(area.l + 2, b.l - 8), midY - 22, 16, 44);
      place(right, shared.right ? b.l + b.w - 22 : Math.min(area.r - 18, b.l + b.w - 8), midY - 22, 16, 44);
    }
    if (!drag) {
      var note = capNote(sec);
      if (note && bottomVisible) {
        hintEl.hidden = false;
        hintEl.textContent = note;
        hintEl.classList.add('note');
        place(hintEl, Math.max(area.l + 8, b.l + 8), Math.max(area.t + 4, b.t + b.h - 54));
      } else if (!drag) { hintEl.hidden = true; hintEl.classList.remove('note'); }
    }
  }

  // Auto growth is bounded (a picture is never zoomed to an extreme): tell the merchant when blank room remains under the visible frame
  function capNote(sec) {
    var frameEl = sec.querySelector(FRAMES);
    if (!frameEl) return '';
    var manual = manualState(sec);
    if (manual.height) return '';
    var gap = sec.getBoundingClientRect().bottom - frameEl.getBoundingClientRect().bottom;
    return gap > 48 ? 'ارتفاع خودکار تا سقف ایمن رشد کرد تا تصویر بی‌قاعده بزرگ نشود. برای پر کردن بیشتر، دستگیرهٔ پایین را بکشید.' : '';
  }

  function renderContainerHandles(m, container, area, used) {
    var cells = cellsOf(container);
    if (cells.length < 2) return;
    var id = container.getAttribute('data-container-id');
    overlay.setAttribute('data-rs-container', id);
    var locked = container.getAttribute('data-container-locked') === '1';
    if (locked) return;
    var cr = box(m, container);
    var rects = cells.map(function (c) { return box(m, c); });
    var stacked = container.getAttribute('data-layout') === STACKED;
    var sideBySide = Math.abs(rects[0].t - rects[1].t) < 4 || stacked ? rects[0].l !== rects[1].l : false;
    if (!sideBySide && !stacked) return;
    if (stacked && Math.abs(rects[0].l - rects[1].l) < 4) return;        // the mobile stack: no column handles
    var top = Math.max(cr.t, area.t + 2);
    var bottom = Math.min(cr.t + cr.h, area.b - 2);
    if (bottom - top < 40) return;
    var n = stacked ? 1 : cells.length - 1;
    for (var i = 0; i < n; i += 1) {
      var a = rects[i], bb = rects[i + 1];
      var edgeA = a.l < bb.l ? a.l + a.w : a.l;                       // the facing edges (cells may be ordered right-to-left)
      var edgeB = a.l < bb.l ? bb.l : bb.l + bb.w;
      var center = (edgeA + edgeB) / 2;
      var key = 'c:' + i;
      used[key] = true;
      var col = handle(key, 'rs-handle-c', 'تغییر عرض ستون‌ها — بکشید یا با کلیدهای چپ/راست تنظیم کنید؛ دوبار کلیک: نسبت اولیه', 'vertical');
      col.setAttribute('data-rs-index', String(i));
      place(col, center - 10, top, 20, bottom - top);
    }
    if (stacked && cells.length === 3) {
      var upper = rects[1], lower = rects[2];
      var cy = (upper.t + upper.h + lower.t) / 2;
      var sk = 's';
      if (cy < area.t + 12 || cy > area.b - 12) return;               // the divider is scrolled out of view: scroll to it, then drag
      used[sk] = true;
      var sp = handle(sk, 'rs-handle-s', 'تغییر نسبت ارتفاع دو خانهٔ کوچک — بکشید یا با کلیدهای بالا/پایین تنظیم کنید؛ دوبار کلیک: نسبت خودکار', 'horizontal');
      place(sp, upper.l, cy - 9, upper.w, 18);
    }
  }

  // ---- drag engine ------------------------------------------------------------
  function toIframeX(m, clientX) { return (clientX - m.fr.left) / m.k; }
  function toIframeY(m, clientY) { return (clientY - m.fr.top) / m.k; }

  function showHint(text, clientX, clientY) {
    hintEl.classList.remove('note');
    hintEl.hidden = false;
    hintEl.textContent = text;
    var ov = overlay.getBoundingClientRect();
    place(hintEl, Math.max(6, Math.min(clientX - ov.left + 14, ov.width - 190)), Math.max(6, clientY - ov.top - 34));
  }

  function fa(n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; }); }

  function startDrag(kind, evt, handleEl, ctx) {
    if (drag || S.blocked() || (evt.button != null && evt.button !== 0 && evt.pointerType === 'mouse')) return;
    var m = mapping();
    if (!m) return;
    drag = { kind: kind, ctx: ctx, m: m, undo: [], start: { x: evt.clientX, y: evt.clientY }, value: null, el: handleEl, source: 'pointer', pointerId: evt.pointerId };
    try { handleEl.setPointerCapture(evt.pointerId); } catch (e) { /* synthetic pointers */ }
    handleEl.classList.add('dragging');
    overlay.classList.add('is-dragging');
    try { handleEl.focus({ preventScroll: true }); } catch (e) { /* best effort */ }
    drivers[kind].begin(drag);
    evt.preventDefault();
  }

  function moveDrag(evt) {
    if (!drag || drag.source !== 'pointer') return;
    drag.latest = evt;
    if (drag.raf) return;
    drag.raf = window.requestAnimationFrame(function () {
      if (!drag) return;
      drag.raf = 0;
      var e = drag.latest;
      drag.m = mapping() || drag.m;
      drivers[drag.kind].move(drag, e.clientX, e.clientY);
      render();
    });
  }

  function endDrag(evt, cancelled) {
    if (!drag || drag.source !== 'pointer') return;
    var d = drag;
    if (d.raf) { window.cancelAnimationFrame(d.raf); d.raf = 0; }
    if (!cancelled && evt) drivers[d.kind].move(d, evt.clientX, evt.clientY);
    finish(d, cancelled);
  }

  function finish(d, cancelled) {
    drag = null;
    d.el.classList.remove('dragging');
    overlay.classList.remove('is-dragging');
    hintEl.hidden = true;
    var mutation = cancelled ? null : drivers[d.kind].result(d);
    if (!mutation) { restore(d); schedule(); return; }
    // the live preview stays until the saved state arrives (the preview re-renders from the server); a refusal / failure restores it
    R4.enqueueStructuralMutation(mutation).then(function (result) {
      if (result && result.ok) return;
      restore(d);
      if (!result || !result.message) S.notify('اندازه ذخیره نشد؛ به آخرین وضعیت معتبر برگشت.');
      schedule();
    }, function () {
      restore(d);
      S.notify('اندازه ذخیره نشد؛ به آخرین وضعیت معتبر برگشت.');
      schedule();
    });
    schedule();
  }

  function restore(d) {
    while (d.undo.length) { try { d.undo.pop()(); } catch (e) { /* the element may be gone after a refresh */ } }
  }

  // temporary inline style / attribute writes, each with its exact undo
  function setProp(d, el, name, value) {
    var prev = el.style.getPropertyValue(name);
    var prevPriority = el.style.getPropertyPriority(name);
    el.style.setProperty(name, value);
    d.undo.push(function () { if (prev) el.style.setProperty(name, prev, prevPriority); else el.style.removeProperty(name); });
  }
  function setAttr(d, el, name, value) {
    var had = el.getAttribute(name);
    el.setAttribute(name, value);
    d.undo.push(function () { if (had == null) el.removeAttribute(name); else el.setAttribute(name, had); });
  }
  function dTokens(el) { return (el.getAttribute('data-d') || '').split(/\s+/).filter(Boolean); }
  function withTokens(d, el, add, removePrefix) {
    var tokens = dTokens(el).filter(function (t) { return !(removePrefix && t.indexOf(removePrefix) === 0); });
    add.forEach(function (t) { if (tokens.indexOf(t) === -1) tokens.push(t); });
    setAttr(d, el, 'data-d', tokens.join(' '));
  }

  var drivers = {};

  // ---- section height ----------------------------------------------------------
  drivers.height = {
    begin: function (d) {
      var el = d.ctx.el;
      d.start.h = el.getBoundingClientRect().height;
      // the content's own height (the floor): measure with a zero minimum, then put everything back
      var prev = el.getAttribute('data-d');
      var prevVar = el.style.getPropertyValue('--d-minh');
      withTokens({ undo: [] }, el, ['minh']);
      el.style.setProperty('--d-minh', '0px');
      d.natural = Math.max(1, el.getBoundingClientRect().height);
      if (prevVar) el.style.setProperty('--d-minh', prevVar); else el.style.removeProperty('--d-minh');
      if (prev == null) el.removeAttribute('data-d'); else el.setAttribute('data-d', prev);
      d.wasManual = manualState(el).height;
    },
    move: function (d, x, y) {
      var el = d.ctx.el;
      var next = Math.round(d.start.h + (y - d.start.y) / d.m.k);
      next = Math.max(d.natural, Math.min(MAX_HEIGHT, next));
      var auto = next <= d.natural + 6;
      d.value = auto ? null : next;
      if (auto) {
        restoreHeightPreview(d);
        showHint('ارتفاع خودکار (' + fa(Math.round(d.natural)) + ' پیکسل)', x, y);
      } else {
        if (!d.previewing) { withTokens(d, el, ['minh']); d.previewing = true; }
        setProp(d, el, '--d-minh', next + 'px');
        showHint('ارتفاع ' + fa(next) + ' پیکسل', x, y);
      }
    },
    result: function (d) {
      if (d.value == null) return d.wasManual ? { type: 'section.resize', section_id: d.ctx.id, height: null } : null;
      return { type: 'section.resize', section_id: d.ctx.id, height: d.value };
    },
  };
  function restoreHeightPreview(d) {
    if (!d.previewing) return;
    var el = d.ctx.el;
    if (!d.wasManual) {
      var tokens = dTokens(el).filter(function (t) { return t !== 'minh'; });
      if (tokens.length) el.setAttribute('data-d', tokens.join(' ')); else el.removeAttribute('data-d');
    }
    el.style.removeProperty('--d-minh');
    d.previewing = false;
  }

  // ---- section width -------------------------------------------------------------
  drivers.width = {
    begin: function (d) {
      var el = d.ctx.el;
      var cell = el.parentElement || el;
      d.cellW = Math.max(1, cell.getBoundingClientRect().width);
      d.start.w = el.getBoundingClientRect().width;
      d.rtl = isRtl(d.m);
    },
    move: function (d, x, y) {
      var el = d.ctx.el;
      var dx = (x - d.start.x) / d.m.k;
      // the LEFT pill moves the left edge (anchor = the right side), the RIGHT pill the right edge (anchor = the left side)
      var next = d.ctx.side === 'left' ? d.start.w - dx : d.start.w + dx;
      var pct = Math.round(next / d.cellW * 100);
      pct = Math.max(MIN_WIDTH_PCT, Math.min(100, pct));
      if (pct >= 98) pct = 100;
      var anchorRight = d.ctx.side === 'left';
      d.anchor = (anchorRight === d.rtl) ? 'start' : 'end';     // RTL: the right side is the inline start
      d.value = pct >= 100 ? null : pct;
      if (d.value == null) {
        withTokens(d, el, [], 'w');
        d.undo.pop();
        el.style.removeProperty('--d-w');
        showHint('عرض کامل خانه (خودکار)', x, y);
      } else {
        withTokens(d, el, ['w', 'wa-' + d.anchor], 'w');
        setProp(d, el, '--d-w', pct + '%');
        showHint('عرض ' + fa(pct) + '٪ از خانه', x, y);
      }
    },
    result: function (d) {
      if (d.value == null) return d.ctx.wasManual ? { type: 'section.resize', section_id: d.ctx.id, width: null } : null;
      return { type: 'section.resize', section_id: d.ctx.id, width: d.value, align: d.anchor };
    },
  };

  // ---- column boundaries (Cell.span) ------------------------------------------------
  function currentSpans(cells) {
    return cells.map(function (c) { return parseInt(c.style.getPropertyValue('--cell-span'), 10) || 12; });
  }
  drivers.column = {
    begin: function (d) {
      var c = d.ctx.container;
      d.cells = cellsOf(c);
      d.spans = currentSpans(d.cells);
      var cs = d.m.win.getComputedStyle(c);
      d.gap = parseFloat(cs.columnGap) || 0;
      d.rtl = isRtl(d.m);
      d.cr = c.getBoundingClientRect();
      d.stacked = c.getAttribute('data-layout') === STACKED;
      d.track = (d.cr.width - 11 * d.gap) / 12;
    },
    move: function (d, x, y) {
      var px = toIframeX(d.m, x);
      var rel = d.rtl ? (d.cr.right - px) : (px - d.cr.left);
      var units = Math.round((rel + d.gap / 2) / (d.track + d.gap));
      var spans = d.spans.slice();
      var i = d.ctx.index;
      if (d.stacked) {
        var big = Math.max(STACKED_BIG[0], Math.min(STACKED_BIG[1], units));
        spans = [big, 12 - big, 12 - big];
      } else {
        var floor = spans.length === 2 ? 3 : 2;
        var before = spans.slice(0, i).reduce(function (a, v) { return a + v; }, 0);
        var after = spans.slice(i + 2).reduce(function (a, v) { return a + v; }, 0);
        var pair = d.spans[i] + d.spans[i + 1];
        var first = Math.max(floor, Math.min(pair - floor, units - before));
        spans[i] = first;
        spans[i + 1] = pair - first;
        void after;
      }
      d.value = spans;
      d.cells.forEach(function (c, idx) { setProp(d, c, '--cell-span', String(spans[idx])); });
      showHint(spans.map(function (s) { return fa(Math.round(s / 12 * 100)) + '٪'; }).join('  |  '), x, y);
    },
    result: function (d) {
      if (!d.value || d.value.join() === d.spans.join()) return null;
      return { type: 'container.resize', container_id: d.ctx.containerId, spans: d.value };
    },
  };

  // ---- the stacked layout's height divider ---------------------------------------------
  drivers.split = {
    begin: function (d) {
      var c = d.ctx.container;
      d.cells = cellsOf(c);
      d.upper = d.cells[1].getBoundingClientRect();
      d.lower = d.cells[2].getBoundingClientRect();
      d.wasManual = c.hasAttribute('data-stack-split');
    },
    move: function (d, x, y) {
      var c = d.ctx.container;
      var py = toIframeY(d.m, y);
      var top = d.upper.top, total = d.lower.bottom - d.upper.top;
      var pct = Math.round((py - top) / Math.max(1, total) * 100);
      pct = Math.max(SPLIT_RANGE[0], Math.min(SPLIT_RANGE[1], pct));
      d.value = pct;
      setAttr(d, c, 'data-stack-split', String(pct));
      setProp(d, c, '--stack-top', pct + 'fr');
      setProp(d, c, '--stack-bottom', (100 - pct) + 'fr');
      showHint('بالا ' + fa(pct) + '٪  |  پایین ' + fa(100 - pct) + '٪', x, y);
    },
    result: function (d) {
      if (d.value == null) return null;
      return { type: 'container.resize', container_id: d.ctx.containerId, stack_split: d.value };
    },
  };

  // ---- wiring: handles ---------------------------------------------------------------------
  function ctxFor(kind, el) {
    var m = mapping();
    if (!m) return null;
    var id = S.selectedId();
    var key = el.getAttribute('data-rs-handle');
    if (kind === 'height' || kind === 'width') {
      var sec = sectionEl(m, id);
      if (!sec) return null;
      return { id: Number(id), el: sec, side: key === 'wl' ? 'left' : 'right', wasManual: manualState(sec)[kind === 'height' ? 'height' : 'width'] };
    }
    var cid = overlay.getAttribute('data-rs-container');
    var container = cid ? m.doc.querySelector('.rcontainer[data-container-id="' + cid + '"]') : null;
    if (!container) return null;
    return { container: container, containerId: Number(cid), index: Number(el.getAttribute('data-rs-index') || 0) };
  }

  function kindOf(el) {
    var key = el.getAttribute('data-rs-handle');
    if (key === 'h') return 'height';
    if (key === 'wl' || key === 'wr') return 'width';
    if (key === 'c') return 'column';
    if (key === 's') return 'split';
    return null;
  }

  overlay.addEventListener('pointerdown', function (evt) {
    var el = evt.target.closest ? evt.target.closest('[data-rs-handle]') : null;
    if (!el) return;
    var kind = kindOf(el);
    var ctx = kind && ctxFor(kind, el);
    if (kind && ctx) startDrag(kind, evt, el, ctx);
  });
  overlay.addEventListener('pointermove', moveDrag);
  overlay.addEventListener('pointerup', function (evt) { endDrag(evt, false); });
  overlay.addEventListener('pointercancel', function (evt) { endDrag(evt, true); });

  // double click = back to Auto for that dimension
  overlay.addEventListener('dblclick', function (evt) {
    var el = evt.target.closest ? evt.target.closest('[data-rs-handle]') : null;
    if (!el || drag) return;
    var kind = kindOf(el);
    var ctx = kind && ctxFor(kind, el);
    if (!ctx) return;
    if (kind === 'height' && ctx.wasManual) R4.enqueueStructuralMutation({ type: 'section.resize', section_id: ctx.id, height: null });
    else if (kind === 'width' && ctx.wasManual) R4.enqueueStructuralMutation({ type: 'section.resize', section_id: ctx.id, width: null });
    else if (kind === 'split') R4.enqueueStructuralMutation({ type: 'container.resize', container_id: ctx.containerId, stack_split: null });
    else if (kind === 'column') {
      var m = mapping();
      var layout = ctx.container.getAttribute('data-layout');
      if (m && layout) R4.enqueueStructuralMutation({ type: 'container.change_layout', container_id: ctx.containerId, layout_key: layout === STACKED ? STACKED : presetFor(ctx.container) });
    }
  });

  // the plain preset a dragged row returns to: the registry's own equal split for that cell count
  function presetFor(container) {
    var n = cellsOf(container).length;
    return n === 2 ? 'half' : n === 3 ? 'thirds' : n === 4 ? 'quarters' : 'single';
  }

  // keyboard: arrow keys preview, Enter / idle for 800 ms commits ONE mutation, Escape cancels
  overlay.addEventListener('keydown', function (evt) {
    var el = evt.target.closest ? evt.target.closest('[data-rs-handle]') : null;
    if (!el) return;
    if (evt.key === 'Escape' && drag && drag.source === 'keyboard') { evt.preventDefault(); cancelKeyboard(); return; }
    var kind = kindOf(el);
    if (!kind) return;
    var sx = 0, sy = 0;
    if (evt.key === 'ArrowUp') sy = -1;
    else if (evt.key === 'ArrowDown') sy = 1;
    else if (evt.key === 'ArrowLeft') sx = -1;
    else if (evt.key === 'ArrowRight') sx = 1;
    else if (evt.key === 'Enter' && drag && drag.source === 'keyboard') { evt.preventDefault(); commitKeyboard(); return; }
    else return;
    evt.preventDefault();
    var horizontal = kind === 'column' || kind === 'width';
    if ((horizontal && !sx) || (!horizontal && !sy)) return;
    if (!drag) {
      var ctx = ctxFor(kind, el);
      var m = mapping();
      if (!ctx || !m) return;
      var rect = el.getBoundingClientRect();
      drag = { kind: kind, ctx: ctx, m: m, undo: [], start: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }, value: null, el: el, source: 'keyboard', pos: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } };
      drivers[kind].begin(drag);
      el.classList.add('dragging');
      overlay.classList.add('is-dragging');
    }
    // one press = one grid column for a column boundary, KEY_STEP px otherwise (Shift = four times as far)
    var unit = drag.kind === 'column' ? Math.max(KEY_STEP, (drag.track + drag.gap) * drag.m.k) : KEY_STEP;
    var press = unit * (evt.shiftKey ? 4 : 1);
    drag.pos.x += sx * press; drag.pos.y += sy * press;
    drag.m = mapping() || drag.m;
    drivers[drag.kind].move(drag, drag.pos.x, drag.pos.y);
    clearTimeout(drag.timer);
    drag.timer = setTimeout(commitKeyboard, 800);
    render();
  });
  function commitKeyboard() { if (drag && drag.source === 'keyboard') { clearTimeout(drag.timer); finish(drag, false); } }
  function cancelKeyboard() { if (drag && drag.source === 'keyboard') { clearTimeout(drag.timer); finish(drag, true); } }

  // Escape cancels a drag from anywhere (the Studio shell OR the preview document, where the keyboard focus usually is); with no drag and no
  // dialog it closes the contextual menu (no mutation)
  function onEscape(evt) {
    if (evt.key !== 'Escape') return;
    if (drag) { if (drag.source === 'pointer') { endDrag(null, true); } else cancelKeyboard(); evt.preventDefault(); return; }
    var t = evt.target;
    var typing = t && /^(input|textarea|select)$/i.test(t.tagName || '');
    if (!typing && !S.blocked() && S.selectedId() && !toolbar.hidden) { S.clearSelection(); schedule(); }
  }
  document.addEventListener('keydown', onEscape);

  // «اندازه خودکار»: one mutation returning every manual size of the selected section to Auto
  autoChip.addEventListener('click', function () {
    var id = S.selectedId();
    var m = mapping();
    var sec = m && sectionEl(m, id);
    if (!sec) return;
    var manual = manualState(sec);
    var mutation = { type: 'section.resize', section_id: Number(id) };
    if (manual.height) mutation.height = null;
    if (manual.width) { mutation.width = null; mutation.align = null; }
    if (Object.keys(mutation).length > 2) R4.enqueueStructuralMutation(mutation);
  });

  // ---- wiring: the contextual toolbar (REAL operations only) --------------------------------------------
  toolbar.addEventListener('click', function (evt) {
    var button = evt.target.closest ? evt.target.closest('[data-rs-sel]') : null;
    if (!button || button.disabled) return;
    var id = S.selectedId();
    if (!id) return;
    var action = button.getAttribute('data-rs-sel');
    if (action === 'edit') S.edit(Number(id));
    else if (action === 'duplicate') S.command(id, 'duplicate');
    else if (action === 'up') S.command(id, 'up');
    else if (action === 'down') S.command(id, 'down');
    else if (action === 'remove') S.askRemove(Number(id));
    else if (action === 'close') { S.clearSelection(); hideAll(); }
  });

  // ---- wiring: state sources --------------------------------------------------------------------------
  ['r4:section-selected', 'r4:direct-edit', 'r4:inspector-opened', 'r4:inspector-closed', 'r4:device', 'r4:history', 'r4:lab'].forEach(function (name) {
    root.addEventListener(name, function () { window.setTimeout(schedule, 30); });
  });
  root.addEventListener('r4:structure-refreshed', function () {
    var id = S.selectedId();
    if (id && !S.rowState(id)) S.clearSelection();            // the section no longer exists (deleted / undone)
    window.setTimeout(schedule, 60);
  });
  window.addEventListener('resize', schedule);
  canvas.addEventListener('scroll', schedule, true);

  // The storefront preview marks itself «hosted by the Studio» (body[data-sfb-studio-host]) only while its own frame element still carries
  // #r4PreviewFrame. A refreshed preview is loaded in a hidden TWIN iframe whose id is removed until it is swapped in (r4_editor.js), so the
  // twin's document never got the marker — and with it every Studio-only rule that hides the OLD in-page section toolbar / drag handle /
  // name tag was off: the old strip came back next to this layer's toolbar after the first refresh. The Studio owns that frame, so the
  // Studio (re)asserts the marker on every load, before the twin becomes visible. Builder previews only; the storefront itself is untouched.
  function markStudioHost(win) {
    try {
      var doc = win.document;
      if (doc && doc.body && doc.querySelector('.sfb-preview-sections')) doc.body.setAttribute('data-sfb-studio-host', '1');
    } catch (e) { /* a document we cannot reach is not a Studio preview */ }
  }

  function bindFrame(f) {
    var win;
    try { win = f && f.contentWindow; if (!win || !win.document) return; } catch (e) { return; }
    markStudioHost(win);
    if (win.__rsResizeBound) return;
    win.__rsResizeBound = true;
    win.addEventListener('keydown', onEscape);
    win.addEventListener('scroll', schedule, { passive: true });
    win.addEventListener('resize', schedule);
    win.addEventListener('pointermove', function (evt) {
      if (drag) return;
      var container = evt.target && evt.target.closest ? evt.target.closest('.rcontainer[data-container-id]') : null;
      var next = container ? container.getAttribute('data-container-id') : null;
      if (next !== hoverContainerId) { hoverContainerId = next; schedule(); }
    }, { passive: true });
    if (win.ResizeObserver) {
      try { new win.ResizeObserver(schedule).observe(win.document.documentElement); } catch (e) { /* best effort */ }
    }
    frameWindows.push(win);
    schedule();
  }
  document.addEventListener('load', function (evt) {
    var f = evt.target;
    if (f && f.tagName === 'IFRAME' && f.hasAttribute('data-rs-draft-src')) { bindFrame(f); window.setTimeout(schedule, 120); }
  }, true);
  bindFrame(frame());

  // a cheap guard for layout shifts nothing else reports (late images, fonts, carousels): geometry only, no writes
  window.setInterval(function () { if (!document.hidden && (S.selectedId() || hoverContainerId)) schedule(); }, 700);

  S.resizeLayer = { render: render };
  schedule();
})();
