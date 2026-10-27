/*
 * RastiSi Design Studio — Visual Layout Composer (the on-canvas layout layer for rows, cells and nested Groups).
 *
 * UI-ONLY. It owns no business state and no write path of its own:
 *   - the structure it shows (rows -> cells -> Groups -> Blocks) is read from the server (layout-tree endpoint) after every committed change;
 *   - every change is one R4 mutation (row.add, cell.split, container.set_layout, container.add_cell, cell.remove, container.remove_group,
 *     cell.duplicate, container.duplicate, cell.move, container.move, container.update_settings) through the ONE mutation queue
 *     (R4.enqueueStructuralMutation / R4.enqueueMutation) — so Draft, Undo/Redo, Preview and Publish behave exactly as for every other edit;
 *   - the canvas it draws on is the real R4 preview iframe (same renderer as the published page).
 *
 * What it adds on top of r4_resize.js (sections + column handles) / r4_studio.js (dialogs, drawers):
 *   - selecting a cell or a Group (click the hover chip on the canvas, a heading, the layers tree, or «چیدمان» in the section toolbar);
 *   - a uniform toolbar: ویرایش · چیدمان (2/3 horizontal and 2/3 vertical splits, add cell) · کپی · جابه‌جایی · حذف · انتخاب والد · بستن;
 *   - the layers tree (Header / Main / Footer / rows / cells / Groups / components) and the Group inspector (content, look, background,
 *     spacing, responsive behaviour), both built from the server's own registries;
 *   - inline editing of a Group's title / description directly on the canvas.
 */
(function () {
  'use strict';

  var R4 = window.RastiSiR4;
  var S = R4 && R4.studio;
  var root = document.querySelector('.rs-studio[data-r4-shell]');
  var canvas = root && root.querySelector('.canvas');
  var dataNode = document.getElementById('rsStudioData');
  if (!R4 || !S || !root || !canvas || !dataNode) return;

  var DATA = {};
  try { DATA = JSON.parse(dataNode.textContent || '{}'); } catch (e) { DATA = {}; }
  if (!DATA.layout_tree_url) return;

  var st = {
    tree: [], limits: { max_cells: 6, max_depth: 8 }, media: [], patterns: [], palette: {}, paletteLabels: {},
    sel: null,               // {kind: 'cell'|'group', id}
    panel: false, tab: 'layers', menu: false, loaded: false, revision: null,
    side: readSide(),         // which edge of the canvas the floating panel sits on (the seller can swap it so it never covers what is being edited)
  };
  function readSide() { try { return window.localStorage.getItem('rsCmpSide') === 'start' ? 'start' : 'end'; } catch (e) { return 'end'; } }
  var cellIdx = {}, groupIdx = {};
  var pending = {};          // container id -> accumulated unsent settings patch (so rapid edits never overwrite each other)
  var busy = false;

  // ---- tiny helpers ------------------------------------------------------------------------------------------------------
  function esc(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function fa(n) { return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; }); }
  function pct(span) { return fa(Math.round(span / 12 * 100)) + '٪'; }
  function icon(name) { return S.icon(name); }
  function pageType() { return (root.dataset && root.dataset.r4PageType) || 'home'; }
  function notify(text) { S.notify(text); }

  // ---- the tree ------------------------------------------------------------------------------------------------------------
  function indexTree() {
    cellIdx = {}; groupIdx = {};
    function walk(group, parentCellId, parentGroupId, position) {
      groupIdx[group.id] = { group: group, parentCellId: parentCellId, parentGroupId: parentGroupId, position: position };
      group.cells.forEach(function (cell, i) {
        cellIdx[cell.id] = { cell: cell, group: group, index: i, count: group.cells.length };
        if (cell.group) walk(cell.group, cell.id, group.id, null);
      });
    }
    st.tree.forEach(function (row, i) { walk(row, null, null, i); });
  }

  function loadTree() {
    var url = DATA.layout_tree_url + (DATA.layout_tree_url.indexOf('?') === -1 ? '?' : '&') + 'page=' + encodeURIComponent(pageType());
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return null;
        st.tree = data.tree || [];
        st.limits = data.limits || st.limits;
        st.media = data.media || [];
        st.patterns = data.patterns || [];
        st.palette = data.palette || {};
        st.paletteLabels = data.palette_labels || {};
        st.revision = data.revision;
        st.loaded = true;
        indexTree();
        if (st.sel && !exists(st.sel)) st.sel = null;
        return data;
      }, function () { return null; });
  }

  function exists(sel) { return sel.kind === 'cell' ? Boolean(cellIdx[sel.id]) : Boolean(groupIdx[sel.id]); }
  function contentCount(node, isCell) {
    var n = 0;
    function g(group) { group.cells.forEach(function (c) { n += c.blocks.length; if (c.group) g(c.group); }); }
    if (isCell) { n += node.blocks.length; if (node.group) g(node.group); } else g(node);
    return n;
  }

  // ---- geometry (iframe -> overlay) ------------------------------------------------------------------------------------------
  var layer = document.createElement('div');
  layer.className = 'rs-cmp-layer';
  layer.setAttribute('data-rs-cmp-layer', '');
  layer.innerHTML =
    '<div class="rs-cmp-outline" data-cmp-outline hidden><span class="rs-cmp-tag" data-cmp-tag></span></div>' +
    '<div class="rs-cmp-toolbar" role="toolbar" aria-label="ابزار چیدمان" data-cmp-toolbar hidden></div>' +
    '<div class="rs-cmp-menu" role="menu" aria-label="چیدمان" data-cmp-menu hidden></div>';
  canvas.appendChild(layer);
  var outline = layer.querySelector('[data-cmp-outline]');
  var tagEl = layer.querySelector('[data-cmp-tag]');
  var toolbar = layer.querySelector('[data-cmp-toolbar]');
  var menu = layer.querySelector('[data-cmp-menu]');
  var pctPool = [];

  function frame() { return document.getElementById('r4PreviewFrame'); }
  function mapping() {
    var f = frame();
    if (!f || !f.contentWindow) return null;
    var doc;
    try { doc = f.contentDocument; } catch (e) { return null; }
    if (!doc || !doc.documentElement) return null;
    var fr = f.getBoundingClientRect();
    var width = f.clientWidth || fr.width;
    return { f: f, doc: doc, win: f.contentWindow, fr: fr, k: width ? fr.width / width : 1, ov: layer.getBoundingClientRect() };
  }
  function box(m, el) {
    var r = el.getBoundingClientRect();
    return { l: m.fr.left + r.left * m.k - m.ov.left, t: m.fr.top + r.top * m.k - m.ov.top, w: r.width * m.k, h: r.height * m.k };
  }
  function place(el, l, t, w, h) {
    el.style.left = Math.round(l) + 'px'; el.style.top = Math.round(t) + 'px';
    if (w != null) el.style.width = Math.round(w) + 'px';
    if (h != null) el.style.height = Math.round(h) + 'px';
  }
  function targetEl(m, sel) {
    if (!sel) return null;
    if (sel.kind === 'cell') return m.doc.querySelector('.rcontainer-cell[data-cell-id="' + sel.id + '"]');
    return m.doc.querySelector('.rgroup[data-group-id="' + sel.id + '"]') || m.doc.querySelector('.rcontainer[data-container-id="' + sel.id + '"]');
  }

  // ---- selection ---------------------------------------------------------------------------------------------------------------
  function select(sel, opts) {
    opts = opts || {};
    selToken += 1;
    if (sel && !exists(sel)) sel = null;
    st.sel = sel;
    st.menu = sel && opts.menu ? true : false;
    if (sel && S.selectedId()) { selfChange = true; S.clearSelection(); selfChange = false; }
    if (sel && opts.reveal !== false) revealTarget();
    renderAll();
  }
  var selfChange = false;
  var selToken = 0;           // bumped by every selection: a result that arrives late never overrides a newer choice
  function revealTarget() {
    var m = mapping();
    var el = m && targetEl(m, st.sel);
    if (!el) return;
    var r = el.getBoundingClientRect();
    var h = m.win.innerHeight;
    if (r.top < 40 || r.bottom > h - 20) m.win.scrollTo({ top: Math.max(0, r.top + m.win.scrollY - Math.max(40, (h - Math.min(r.height, h)) / 2)) });
  }

  // ---- mutations -----------------------------------------------------------------------------------------------------------------
  function send(mutation) {
    return R4.enqueueStructuralMutation(mutation).then(function (result) {
      // a refusal that names its cause is already shown (R4 reportKnownRefusal); only an unexplained failure needs a word here
      if (!result) { notify('انجام نشد؛ چیدمان قبلی حفظ شد.'); return result; }
      if (!result.ok) { if (!result.message) notify('انجام نشد؛ چیدمان قبلی حفظ شد.'); return result; }
      return loadTree().then(function () { return result; });
    });
  }

  function patchGroup(containerId, flat, style) {
    var slot = pending[containerId] = pending[containerId] || { flat: {}, style: {} };
    Object.keys(flat || {}).forEach(function (k) { slot.flat[k] = flat[k]; });
    Object.keys(style || {}).forEach(function (k) { slot.style[k] = style[k]; });
    var patch = Object.assign({}, slot.flat);
    if (Object.keys(slot.style).length) patch.style = Object.assign({}, slot.style);
    // optimistic local copy: the controls and tags keep showing what the merchant just set
    var g = groupIdx[containerId] && groupIdx[containerId].group;
    if (g) {
      Object.keys(slot.flat).forEach(function (k) { g.settings[k] = slot.flat[k]; });
      if ('title' in slot.flat) { g.title = slot.flat.title || ''; toolbar.removeAttribute('data-sig'); schedule(); renderLayersOnly(); }
      g.settings.style = Object.assign({}, g.settings.style || {});
      Object.keys(slot.style).forEach(function (k) {
        if (slot.style[k] === null || slot.style[k] === '') delete g.settings.style[k]; else g.settings.style[k] = slot.style[k];
      });
    }
    return R4.enqueueMutation({ type: 'container.update_settings', container_id: Number(containerId), patch: patch }).then(function (result) {
      if (pending[containerId] === slot) delete pending[containerId];
      if (!result || result.ok === false) { notify('این تغییر ذخیره نشد؛ مقدار قبلی برگردانده شد.'); return loadTree().then(renderAll); }
      return loadTree().then(function () { renderOverlays(); renderLayersOnly(); return result; });
    });
  }

  // ---- toolbar actions -------------------------------------------------------------------------------------------------------------

  // ---- the selected thing: a layout target (cell / Group, st.sel) OR a Section (the Studio's own selection) — never both ------------------
  function sectionSel() { var id = S.selectedId(); return id && /^\d+$/.test(id) ? Number(id) : null; }
  function findBlock(id) {
    var found = null;
    Object.keys(cellIdx).forEach(function (cid) {
      var c = cellIdx[cid];
      c.cell.blocks.forEach(function (b) { if (b.id === id) found = { block: b, cell: c.cell, group: c.group, index: c.index, count: c.count }; });
    });
    return found;
  }

  // the structural operand of an action on the current selection
  function operand() {
    if (st.sel) {
      if (st.sel.kind === 'cell') {
        var c = cellIdx[st.sel.id];
        if (!c) return null;
        var single = c.count === 1;
        var topRow = groupIdx[c.group.id].parentCellId == null;
        return { kind: 'cell', cell: c.cell, group: c.group, index: c.index, count: c.count, single: single, topRow: topRow };
      }
      var g = groupIdx[st.sel.id];
      if (!g) return null;
      return { kind: 'group', group: g.group, hostCellId: g.parentCellId, topRow: g.parentCellId == null, position: g.position };
    }
    var sid = sectionSel();
    if (sid) {
      var f = findBlock(sid);
      return { kind: 'section', id: sid, block: f ? f.block : null, cell: f ? f.cell : null, group: f ? f.group : null, topRow: f ? groupIdx[f.group.id].parentCellId == null : true };
    }
    return null;
  }

  // ---- names: always read from the real tree (Group title, Section Registry label) — never a second, separate label -------------------
  function pageName() {
    var sel = document.getElementById('r4PageSwitcherSelect');
    return sel && sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent.trim() : 'صفحه';
  }
  function groupName(g) {
    var gi = groupIdx[g.id];
    if (gi && gi.parentCellId == null) return g.title ? 'ردیف: ' + g.title : 'ردیف ' + fa((gi.position || 0) + 1);
    return g.title ? 'گروه: ' + g.title : 'گروه بدون‌نام (' + fa(g.cells.length) + (axisOf(g) === 'vertical' ? ' ردیف' : ' ستون') + ')';
  }
  function cellName(entry) {
    if (!entry) return 'سلول';
    return entry.count > 1 ? (axisOf(entry.group) === 'vertical' ? 'ردیف ' : 'ستون ') + fa(entry.index + 1) + ' از ' + fa(entry.count) : 'سلول';
  }
  function nameOf(op) {
    if (op.kind === 'section') return op.block ? op.block.label : 'بخش';
    if (op.kind === 'cell') return cellName(cellIdx[op.cell.id]);
    return groupName(op.group);
  }
  function pathOf(op) {
    var tail = [];
    var gid = op.group ? op.group.id : null;
    while (gid != null) {
      var gi = groupIdx[gid];
      if (!gi) break;
      tail.unshift(groupName(gi.group));
      if (gi.parentCellId != null) { var hc = cellIdx[gi.parentCellId]; tail.unshift(cellName(hc)); gid = hc ? hc.group.id : null; } else gid = null;
    }
    var parts = [pageName()].concat(tail);
    if (op.kind === 'cell') parts.push(cellName(cellIdx[op.cell.id]));
    if (op.kind === 'section') { if (op.cell) parts.push(cellName(cellIdx[op.cell.id])); parts.push(nameOf(op)); }
    return parts.join(' ← ');
  }

  function axisOf(group) { return group && group.axis === 'vertical' ? 'vertical' : 'horizontal'; }

  function doSplit(axis, count) {
    var op = operand();
    if (!op) return;
    st.menu = false;
    var token = selToken;
    var p;
    if (op.kind === 'cell') {
      var hostId = op.cell.id;
      p = send({ type: 'cell.split', cell_id: hostId, axis: axis, count: count }).then(function (r) {
        if (r && r.ok && token === selToken) {
          // the new Group (or the re-laid-out single-cell row) becomes the selection so it can be resized / styled right away
          var c = cellIdx[hostId];
          if (c && c.cell.group) select({ kind: 'group', id: c.cell.group.id });
          else if (c) select({ kind: 'group', id: c.group.id });
        }
      });
    } else {
      var gid = op.group.id;
      p = send({ type: 'container.set_layout', container_id: gid, axis: axis, count: count }).then(function (r) { if (r && r.ok && token === selToken) select({ kind: 'group', id: gid }); });
    }
    return p;
  }

  function doAddCell() {
    var op = operand();
    var gid = op ? (op.kind === 'cell' ? op.group.id : op.group.id) : null;
    if (!gid) return;
    st.menu = false;
    send({ type: 'container.add_cell', container_id: gid }).then(renderAll);
  }

  function doDuplicate() {
    var op = operand();
    if (!op) return;
    var m;
    if (op.kind === 'cell') m = op.single && op.topRow ? { type: 'container.duplicate', container_id: op.group.id } : { type: 'cell.duplicate', cell_id: op.cell.id };
    else m = op.topRow ? { type: 'container.duplicate', container_id: op.group.id } : { type: 'cell.duplicate', cell_id: op.hostCellId };
    send(m).then(function (r) { if (r && r.ok) notify('نسخه‌ای از همهٔ محتوا ساخته شد؛ واگرد آن را برمی‌گرداند.'); renderAll(); });
  }

  // what "move" means for the selection: a single-cell page row and a top-level Group move the ROW; any other cell / nested Group moves its Cell
  function moveInfo(op) {
    if (op.kind === 'cell' && !(op.single && op.topRow)) {
      return { m: { type: 'cell.move', cell_id: op.cell.id }, idx: op.index, count: op.count, vertical: axisOf(op.group) === 'vertical' };
    }
    if (op.kind === 'cell' || op.topRow) {
      var gid = op.group.id;
      return { m: { type: 'container.move', container_id: gid }, idx: groupIdx[gid].position, count: st.tree.length, vertical: true };
    }
    var host = cellIdx[op.hostCellId];
    return { m: { type: 'cell.move', cell_id: op.hostCellId }, idx: host ? host.index : 0, count: host ? host.count : 1, vertical: host ? axisOf(host.group) === 'vertical' : true };
  }

  function doMove(dir) {
    var op = operand();
    if (!op) return;
    var info = moveInfo(op);
    send(Object.assign({}, info.m, { direction: dir })).then(renderAll);
  }

  function confirmBox(message, accept) {
    return new Promise(function (resolve) {
      var wrap = document.createElement('div');
      wrap.className = 'rs-cmp-confirm-wrap';
      wrap.innerHTML = '<div class="rs-cmp-confirm" role="alertdialog" aria-modal="true" aria-label="تأیید حذف"><p>' + esc(message) + '</p>' +
        '<div class="rs-cmp-confirm-actions"><button type="button" class="rs-cmp-danger" data-cmp-yes>' + esc(accept) + '</button><button type="button" data-cmp-no>انصراف</button></div></div>';
      root.appendChild(wrap);
      var done = function (v) { if (wrap.parentNode) wrap.parentNode.removeChild(wrap); resolve(v); };
      wrap.querySelector('[data-cmp-yes]').addEventListener('click', function () { done(true); });
      wrap.querySelector('[data-cmp-no]').addEventListener('click', function () { done(false); });
      wrap.addEventListener('keydown', function (e) { if (e.key === 'Escape') done(false); });
      wrap.querySelector('[data-cmp-no]').focus();
    });
  }

  function doRemove() {
    var op = operand();
    if (!op) return;
    var count, m, noun;
    if (op.kind === 'cell') {
      count = contentCount(op.cell, true);
      noun = op.single && op.topRow ? 'این ردیف' : 'این خانه';
      m = op.single && op.topRow ? { type: 'container.remove_group', container_id: op.group.id } : { type: 'cell.remove', cell_id: op.cell.id };
      if (op.single && !op.topRow) m = { type: 'container.remove_group', container_id: op.group.id };
    } else {
      count = contentCount(op.group, false);
      noun = op.topRow ? 'این ردیف' : 'این گروه';
      m = { type: 'container.remove_group', container_id: op.group.id };
    }
    var go = function () {
      st.sel = null; st.menu = false;
      return send(m).then(function () { renderAll(); });
    };
    if (!count) return go();
    confirmBox(noun + ' شامل ' + fa(count) + ' بخش است و با حذف، همهٔ محتوای آن هم پاک می‌شود (با «واگرد» برمی‌گردد). حذف شود؟', 'بله، همراه محتوا حذف شود').then(function (yes) { if (yes) go(); });
  }

  function selectParent() {
    var op = operand();
    if (!op) return;
    if (op.kind === 'cell') {
      if (op.single && op.topRow) { select({ kind: 'group', id: op.group.id }); return; }
      select({ kind: 'group', id: op.group.id });
      return;
    }
    if (op.hostCellId != null) select({ kind: 'cell', id: op.hostCellId });
    else select(null);
  }

  function doEdit() {
    var op = operand();
    if (!op) return;
    if (op.kind === 'section') { S.edit(op.id); return; }
    if (op.kind === 'group') { openWorkspace(op.group.id); return; }
    if (op.cell.group) { select({ kind: 'group', id: op.cell.group.id }); openWorkspace(op.cell.group.id); return; }
    if (op.cell.blocks.length > 1) { st.menu = 'pick'; toolbar.removeAttribute('data-sig'); schedule(); return; }      // never guess which Section is meant
    if (op.cell.blocks.length) { var b = op.cell.blocks[0]; st.sel = null; renderAll(); S.select(b.id); S.edit(b.id); return; }
    S.addToCell(op.cell.id);
  }

  // actions of the toolbar while a SECTION is selected: the Studio's own commands (same ones the structure list uses)
  function sectionAction(action, op) {
    var id = String(op.id);
    if (action === 'edit') S.edit(op.id);
    else if (action === 'layout') { if (op.cell) select({ kind: 'cell', id: op.cell.id }, { menu: true }); }
    else if (action === 'duplicate') S.command(id, 'duplicate');
    else if (action === 'up') S.command(id, 'up');
    else if (action === 'down') S.command(id, 'down');
    else if (action === 'remove') S.askRemove(op.id);
    else if (action === 'parent') { if (op.cell) select({ kind: 'cell', id: op.cell.id }); }
    else if (action === 'close') { S.clearSelection(); renderAll(); }
  }

  function addRow() {
    var token = selToken;
    send({ type: 'row.add', page_type: pageType() }).then(function (r) {
      if (!r || !r.ok || token !== selToken) return;
      var last = st.tree[st.tree.length - 1];
      if (last) select({ kind: 'group', id: last.id });
    });
  }

  // ---- overlay rendering -----------------------------------------------------------------------------------------------------------
  var SPLITS = [
    ['horizontal', 2, 'columns', '۲ ستون'], ['horizontal', 3, 'columns3', '۳ ستون'],
    ['vertical', 2, 'rows', '۲ ردیف'], ['vertical', 3, 'rows3', '۳ ردیف'],
  ];
  var GLYPH = {
    columns: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/></svg>',
    columns3: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/></svg>',
    rows: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 12h18"/></svg>',
    rows3: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9.4h18M3 14.6h18"/></svg>',
    add: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 9v6M9 12h6"/></svg>',
  };

  function nameChip(op) {
    var name = nameOf(op);
    var short = name.length > 34 ? name.slice(0, 33) + '…' : name;
    return '<span class="rs-cmp-name" data-cmp-name title="' + esc(pathOf(op)) + '"><i aria-hidden="true"></i><b>' + esc(short) + '</b></span>';
  }

  function btnHtml(action, ic, label, extra) {
    return '<button type="button" class="rs-cmp-btn' + ((extra && extra.cls) || '') + '" data-cmp="' + action + '" aria-label="' + label + '" title="' + label + '"' + ((extra && extra.disabled) ? ' disabled' : '') + '>' + icon(ic) + ((extra && extra.text) ? '<span>' + extra.text + '</span>' : '') + '</button>';
  }
  function layoutBtn() {
    return '<button type="button" class="rs-cmp-btn rs-cmp-layout" data-cmp="layout" aria-haspopup="menu" aria-expanded="' + (st.menu === true ? 'true' : 'false') + '" title="چیدمان: تقسیم افقی/عمودی"><span>چیدمان</span>' + icon('chevron') + '</button>';
  }

  function toolbarHtml(op) {
    if (op.kind === 'section') {
      var state = S.rowState(String(op.id)) || {};
      var locked = state.locked === true;
      return nameChip(op) + btnHtml('edit', 'edit', 'ویرایش', { cls: ' primary', text: 'ویرایش' }) +
        (op.cell ? layoutBtn() : '') +
        btnHtml('duplicate', 'copy', 'کپی بخش', { disabled: locked || state.canDuplicate === false }) +
        btnHtml('up', 'up', 'انتقال به بالا', { disabled: locked || state.canUp === false }) + btnHtml('down', 'down', 'انتقال به پایین', { disabled: locked || state.canDown === false }) +
        btnHtml('remove', 'trash', 'حذف بخش', { disabled: state.canRemove === false }) +
        btnHtml('parent', 'layers', 'انتخاب سلول والد', { disabled: !op.cell }) + btnHtml('close', 'close', 'بستن');
    }
    var info = moveInfo(op);
    var mv = info.vertical ? { up: 'انتقال به بالا', down: 'انتقال به پایین' } : { up: 'انتقال به راست', down: 'انتقال به چپ' };
    var canParent = !(op.kind === 'group' && op.topRow);
    return nameChip(op) + btnHtml('edit', 'edit', 'ویرایش', { cls: ' primary', text: 'ویرایش' }) + layoutBtn() +
      btnHtml('duplicate', 'copy', 'کپی همراه با محتوا') +
      btnHtml('up', 'up', mv.up, { disabled: info.idx <= 0 }) + btnHtml('down', 'down', mv.down, { disabled: info.idx >= info.count - 1 }) +
      btnHtml('remove', 'trash', 'حذف') +
      btnHtml('parent', 'layers', 'انتخاب والد', { disabled: !canParent }) +
      btnHtml('close', 'close', 'بستن');
  }

  function pickHtml(op) {
    var html = '<p class="rs-cmp-menu-title">کدام بخش ویرایش شود؟</p><div class="rs-cmp-picks">';
    op.cell.blocks.forEach(function (b) {
      html += '<button type="button" role="menuitem" class="rs-cmp-pick" data-cmp-pick="' + b.id + '">' + icon('card') + '<span>' + esc(b.label) + '</span>' + (b.active ? '' : '<small>پنهان</small>') + '</button>';
    });
    return html + '</div>';
  }

  function menuHtml(op) {
    var group = op.group;
    var html = '<p class="rs-cmp-menu-title">' + (op.kind === 'cell' ? 'تقسیم این خانه' : 'چیدمان این ' + (op.topRow ? 'ردیف' : 'گروه')) + '</p><div class="rs-cmp-splits">';
    SPLITS.forEach(function (s) {
      html += '<button type="button" role="menuitem" class="rs-cmp-split" data-cmp-split="' + s[0] + ':' + s[1] + '" title="' + s[3] + '">' + GLYPH[s[2]] + '<span>' + s[3] + '</span></button>';
    });
    html += '</div>';
    var full = !group.can_add_cell;
    html += '<button type="button" role="menuitem" class="rs-cmp-add" data-cmp-add ' + (full ? 'disabled title="به سقف خانه‌های این گروه رسیده‌اید"' : '') + '>' + GLYPH.add + '<span>افزودن خانه به این ' + (axisOf(group) === 'vertical' ? 'گروه عمودی' : 'گروه') + '</span></button>';
    html += '<p class="rs-cmp-menu-note">' + (op.kind === 'cell' ? 'محتوای فعلی خانه در اولین بخش جدید می‌ماند.' : 'محتوای خانه‌ها به ترتیب حفظ می‌شود.') + ' هر بخش را بعد از تقسیم می‌توان دوباره تقسیم کرد.</p>';
    return html;
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () { scheduled = false; renderOverlays(); });
  }

  function clampTop(v, area, h) { return Math.max(area.t + 2, Math.min(v, area.b - h - 2)); }

  function hideOverlays() {
    outline.hidden = true; toolbar.hidden = true; menu.hidden = true;
    pctPool.forEach(function (n) { n.hidden = true; });
  }

  function renderOverlays() {
    var m = mapping();
    var op = operand();
    if (!m || !op || S.blocked()) { hideOverlays(); return; }
    var el = op.kind === 'section' ? m.doc.querySelector('.rsec[data-section-id="' + op.id + '"]') : targetEl(m, st.sel);
    if (!el) { hideOverlays(); return; }
    var b = box(m, el);
    var area = { l: m.fr.left - m.ov.left, t: m.fr.top - m.ov.top, r: m.fr.right - m.ov.left, b: m.fr.bottom - m.ov.top };
    // the floating panel is an obstacle: the toolbar and the menu stay on the free side of it
    if (!panel.hidden) {
      var pb = panel.getBoundingClientRect();
      var pl = pb.left - m.ov.left, pr = pb.right - m.ov.left;
      if (pl + pb.width / 2 > (area.l + area.r) / 2) area.r = Math.min(area.r, pl - 8); else area.l = Math.max(area.l, pr + 8);
    }
    if (op.kind === 'section') {
      outline.hidden = true;            // the preview already rings the selected Section
    } else {
      outline.hidden = false;
      place(outline, b.l, b.t, b.w, b.h);
      outline.setAttribute('data-kind', st.sel.kind);
      tagEl.textContent = nameOf(op);
    }
    // toolbar: rebuilt only when the operand (or its name / state) changes — keeps hover and focus stable while scrolling
    var state = op.kind === 'section' ? S.rowState(String(op.id)) || {} : {};
    var sig = [op.kind, op.kind === 'section' ? op.id : st.sel.id, nameOf(op), st.menu, op.kind === 'cell' ? op.index + '/' + op.count : (op.group ? op.group.cells.length : 0), st.tree.length,
               state.canUp, state.canDown, state.canDuplicate, state.canRemove, state.locked].join('|');
    if (toolbar.getAttribute('data-sig') !== sig) { toolbar.innerHTML = toolbarHtml(op); toolbar.setAttribute('data-sig', sig); }
    toolbar.hidden = false;
    var tw = toolbar.offsetWidth || 420, th = toolbar.offsetHeight || 40;
    var left = Math.max(area.l + 6, Math.min(b.l + b.w - tw, area.r - tw - 6));
    var above = b.t - th - 8;
    var top = above >= area.t + 2 ? above : clampTop(b.t + 8, area, th);
    place(toolbar, left, top);
    // layout / pick menu under the toolbar
    if (st.menu && op.kind !== 'section') {
      menu.innerHTML = st.menu === 'pick' ? pickHtml(op) : menuHtml(op);
      menu.hidden = false;
      var mw = menu.offsetWidth || 270, mh = menu.offsetHeight || 190;
      var mtop = top + th + 6 + mh > area.b ? Math.max(area.t + 2, top - mh - 6) : top + th + 6;
      place(menu, Math.max(area.l + 6, Math.min(left + tw - mw, area.r - mw - 6)), mtop);
    } else { menu.hidden = true; }
    if (op.kind === 'section') pctPool.forEach(function (n) { n.hidden = true; }); else renderPct(m, op);
  }

  // every cell of the selected row / Group shows its share (the numbers the handles change)
  function renderPct(m, op) {
    var cid = op.kind === 'cell' ? op.group.id : op.group.id;
    var group = groupIdx[cid] && groupIdx[cid].group;
    var tags = [];
    if (group) {
      group.cells.forEach(function (cell) {
        var cellEl = m.doc.querySelector('.rcontainer-cell[data-cell-id="' + cell.id + '"]');
        if (cellEl) tags.push({ el: cellEl, text: pct(cell.span) });
      });
    }
    if (group && group.cells.length < 2) tags = [];
    while (pctPool.length < tags.length) {
      var n = document.createElement('span');
      n.className = 'rs-cmp-pct';
      layer.appendChild(n);
      pctPool.push(n);
    }
    pctPool.forEach(function (n, i) {
      if (i >= tags.length) { n.hidden = true; return; }
      var bb = box(m, tags[i].el);
      n.hidden = false;
      n.textContent = tags[i].text;
      place(n, bb.l + bb.w / 2 - 20, bb.t + bb.h - 24);
    });
  }

  // ---- floating panel: the layers tree (Header -> page -> Footer). Group SETTINGS open in the big workspace dialog below. -------------------
  var panel = document.createElement('aside');
  panel.className = 'rs-cmp-panel';
  panel.setAttribute('data-cmp-panel', '');
  panel.setAttribute('aria-label', 'لایه‌ها');
  panel.hidden = true;
  canvas.appendChild(panel);
  function applySide() { panel.setAttribute('data-side', st.side); }
  applySide();

  function nodeBtn(depth, selected, kind, id, html, extra) {
    return '<button type="button" class="rs-cmp-node' + (selected ? ' on' : '') + '" style="--d:' + depth + '" data-cmp-node="' + kind + ':' + id + '"' + (extra || '') + '>' + html + '</button>';
  }
  function layersHtml() {
    var out = '<div class="rs-cmp-tree" role="tree">';
    out += nodeBtn(0, false, 'header', 0, icon('header') + '<b>هدر سایت</b><small>همه صفحه‌ها</small>');
    out += '<div class="rs-cmp-sec">محتوای صفحه</div>';
    st.tree.forEach(function (row, i) { out += rowHtml(row, 1, i); });
    if (!st.tree.length) out += '<p class="rs-cmp-empty">هنوز ردیفی نیست؛ «ردیف ساده» یا «افزودن بخش» را بزنید.</p>';
    out += nodeBtn(0, false, 'footer', 0, icon('footer') + '<b>فوتر سایت</b><small>همه صفحه‌ها</small>');
    return out + '</div><button type="button" class="rs-cmp-wide" data-cmp-add-row>' + icon('plus') + 'ردیف ساده</button>';
  }
  function rowHtml(group, depth) {
    var selected = st.sel && st.sel.kind === 'group' && st.sel.id === group.id;
    var axis = axisOf(group) === 'vertical' ? 'عمودی' : 'افقی';
    var html = nodeBtn(depth, selected, 'group', group.id, icon('grid') + '<b>' + esc(groupName(group)) + '</b><small>' + fa(group.cells.length) + ' خانه · ' + axis + '</small>');
    group.cells.forEach(function (cell, i) {
      var cs = st.sel && st.sel.kind === 'cell' && st.sel.id === cell.id;
      html += nodeBtn(depth + 1, cs, 'cell', cell.id, icon('columns') + '<b>' + esc(cellName(cellIdx[cell.id])) + (group.cells.length > 1 ? ' · ' + pct(cell.span) : '') + '</b><small>' + (cell.group ? 'گروه' : (cell.blocks.length ? fa(cell.blocks.length) + ' بخش' : 'خالی')) + '</small>');
      cell.blocks.forEach(function (blk) {
        html += nodeBtn(depth + 2, sectionSel() === blk.id, 'block', blk.id, icon('card') + '<b>' + esc(blk.label) + '</b>' + (blk.active ? '' : '<small>پنهان</small>'));
      });
      if (cell.group) html += rowHtml(cell.group, depth + 2);
    });
    return html;
  }

  function renderPanel() {
    if (!st.panel) { panel.hidden = true; return; }
    panel.hidden = false;
    panel.innerHTML = '<header class="rs-cmp-ph"><b class="rs-cmp-ph-title">لایه‌ها</b>' +
      '<span class="rs-cmp-ph-actions"><button type="button" class="rs-cmp-x" data-cmp-panel-side aria-label="جابه‌جایی پنل به طرف دیگر صفحه" title="جابه‌جایی پنل به طرف دیگر">⇄</button>' +
      '<button type="button" class="rs-cmp-x" data-cmp-panel-close aria-label="بستن پنل">' + icon('close') + '</button></span></header><div class="rs-cmp-pb">' + layersHtml() + '</div>';
  }
  function renderLayersOnly() { if (st.panel) { var pb = panel.querySelector('.rs-cmp-pb'); if (pb) pb.innerHTML = layersHtml(); } }

  function renderAll() { renderPanel(); schedule(); railState(); if (S.resizeLayer && S.resizeLayer.render) window.setTimeout(S.resizeLayer.render, 30); }
  function railState() {
    Array.prototype.forEach.call(root.querySelectorAll('[data-rastisi-action="composer-panel"]'), function (b) { b.setAttribute('aria-pressed', st.panel ? 'true' : 'false'); b.classList.toggle('on', st.panel); });
  }

  // ---- the Group settings WORKSPACE: the standard large R4 settings dialog (same shell as a Section's), with a Group body -----------------
  // r4_studio.js owns the dialog (mode, Escape, focus trap, backdrop, close); this file only fills #r4Inspector and announces it the way the
  // announcement strip does. Every control writes through container.update_settings (patchGroup) — the one mutation path.
  var inspectorEl = document.getElementById('r4Inspector');
  var ws = { open: false, id: null, tab: 'content' };

  var BG_MODES = [['transparent', 'بدون پس‌زمینه'], ['color', 'رنگ ساده'], ['gradient', 'گرادیان'], ['image', 'تصویر'], ['pattern', 'الگو']];
  var MOBILE_MODES = [['stack', 'زیر هم'], ['same', 'مثل دسکتاپ'], ['slider', 'اسلایدر افقی']];
  var VALIGN = [['start', 'بالا'], ['center', 'وسط'], ['end', 'پایین']];
  var HEIGHT_MODES = [['natural', 'طبیعی'], ['equal', 'هم‌قد']];
  var THEMES = [
    ['روشن', { text_color: '#1F2937', title_color: '#111827' }, { background_mode: 'color', background_color: '#FFFFFF' }],
    ['تیره', { text_color: '#F8FAFC', title_color: '#FFFFFF' }, { background_mode: 'color', background_color: '#111827' }],
    ['ملایم', { text_color: 'token:text', title_color: 'token:primary' }, { background_mode: 'color', background_color: '#EEF6F2' }],
    ['برند', { text_color: 'token:primary', title_color: 'token:primary' }, { background_mode: 'gradient', background_color: '#FFFFFF', background_color2: '#DDF4EC' }],
  ];
  var WS_TABS = [['content', 'محتوا و تم'], ['text', 'متن و فونت'], ['look', 'رنگ و پس‌زمینه'], ['box', 'فاصله و حاشیه'], ['device', 'دستگاه‌ها و موبایل']];

  function selectOpts(list, value) {
    return list.map(function (o) { return '<option value="' + esc(o[0]) + '"' + (String(value) === String(o[0]) ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('');
  }
  function colorControl(scope, key, label, value, allowEmpty) {
    var sw = '';
    Object.keys(st.palette).forEach(function (token) {
      sw += '<button type="button" class="rs-cmp-sw' + (value === token ? ' on' : '') + '" style="background:' + esc(st.palette[token]) + '" data-cmp-color="' + scope + ':' + key + '" data-value="' + esc(token) + '" title="' + esc(st.paletteLabels[token.replace('token:', '')] || token) + '"></button>';
    });
    var hex = /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : '#888888';
    return '<div class="rs-cmp-field"><label>' + esc(label) + '</label><div class="rs-cmp-colors">' + sw +
      '<input type="color" value="' + esc(hex) + '" data-cmp-color-input="' + scope + ':' + key + '" aria-label="' + esc(label) + ' (دلخواه)">' +
      (allowEmpty ? '<button type="button" class="rs-cmp-sw clear" data-cmp-color="' + scope + ':' + key + '" data-value="" title="خودکار">×</button>' : '') + '</div></div>';
  }
  function intControl(scope, key, label, value, min, max) {
    var v = value == null ? '' : value;
    return '<div class="rs-cmp-field"><label>' + esc(label) + '</label><div class="rs-cmp-range"><input type="range" min="' + min + '" max="' + max + '" value="' + (v === '' ? min : v) + '" data-cmp-int="' + scope + ':' + key + '">' +
      '<input type="number" min="' + min + '" max="' + max + '" value="' + v + '" placeholder="خودکار" data-cmp-int-num="' + scope + ':' + key + '"></div></div>';
  }
  function choiceControl(scope, key, label, choices, value) {
    return '<div class="rs-cmp-field"><label>' + esc(label) + '</label><select data-cmp-choice="' + scope + ':' + key + '">' + selectOpts(choices.map(function (c) { return [c.value, c.label]; }), value || '') + '</select></div>';
  }
  function wsCard(title, note, body) {
    return '<section class="r4-ws-card" data-r4-ws-card="cmp" data-r4-ws-manage><header class="r4-ws-card-head"><h3>' + esc(title) + '</h3>' + (note ? '<p>' + esc(note) + '</p>' : '') + '</header><div class="r4-ws-card-body">' + body + '</div></section>';
  }
  function propsOf(key, style) {
    var grp = (DATA.group_inspector || []).filter(function (x) { return x.key === key; })[0];
    if (!grp) return '';
    return wsCard(grp.label, '', grp.properties.map(function (p) {
      var val = style[p.key];
      if (p.kind === 'color') return colorControl('style', p.key, p.label, val || '', true);
      if (p.kind === 'int') return intControl('style', p.key, p.label, val, p.min, p.max);
      return choiceControl('style', p.key, p.label, p.choices, val || '');
    }).join(''));
  }
  function bgHtml(s) {
    var mode = s.background_mode || 'transparent';
    var html = '<div class="rs-cmp-bg"><div class="rs-cmp-field"><label>نوع پس‌زمینه</label><select data-cmp-bg-mode>' + selectOpts(BG_MODES, mode) + '</select></div>';
    if (mode === 'color' || mode === 'gradient' || mode === 'pattern') html += colorControl('flat', 'background_color', mode === 'gradient' ? 'رنگ اول' : 'رنگ پس‌زمینه', s.background_color || '', false);
    if (mode === 'gradient') html += colorControl('flat', 'background_color2', 'رنگ دوم', s.background_color2 || '', false);
    if (mode === 'pattern') html += '<div class="rs-cmp-field"><label>الگو</label><select data-cmp-pattern>' + selectOpts(st.patterns.map(function (p) { return [p.key, p.label]; }), s.background_pattern || (st.patterns[0] && st.patterns[0].key) || '') + '</select></div>';
    if (mode === 'image') {
      html += '<div class="rs-cmp-field"><label>تصویر از کتابخانهٔ رسانه</label><div class="rs-cmp-media">';
      if (!st.media.length) html += '<p class="rs-cmp-note">هنوز تصویری در کتابخانه نیست؛ از «رسانه» تصویر بیفزایید.</p>';
      st.media.forEach(function (a) {
        html += '<button type="button" class="rs-cmp-thumb' + (Number(s.background_media_asset_id) === a.id ? ' on' : '') + '" data-cmp-media="' + a.id + '" title="' + esc(a.name) + '"><img src="' + esc(a.url) + '" alt="" loading="lazy"></button>';
      });
      html += '</div></div>';
    }
    return html + '</div>';
  }

  function workspaceHtml(g) {
    var s = g.settings || {};
    var style = s.style || {};
    var crumb = pathOf({ kind: 'group', group: g });
    var panels = {
      content: wsCard('محتوای گروه', 'عنوان و توضیح روی صفحه بالای گروه نمایش داده می‌شود.',
        '<div class="rs-cmp-field"><label for="rsCmpTitle">عنوان گروه</label><input id="rsCmpTitle" type="text" maxlength="120" value="' + esc(s.title || '') + '" data-cmp-text="title" placeholder="مثلاً پیشنهاد ویژه"></div>' +
        '<div class="rs-cmp-field"><label for="rsCmpDesc">توضیح</label><textarea id="rsCmpDesc" maxlength="300" rows="2" data-cmp-text="description" placeholder="یک خط توضیح کوتاه">' + esc(s.description || '') + '</textarea></div>' +
        '<label class="rs-cmp-check"><input type="checkbox" data-cmp-titlevis ' + (s.title_visible === false ? '' : 'checked') + '> نمایش عنوان روی صفحه</label>') +
        wsCard('تم گروه', 'رنگ پس‌زمینه و نوشته‌های همین گروه را یکجا می‌گذارد؛ هر مورد را می‌توان جداگانه تغییر داد.',
          '<div class="rs-cmp-themes">' + THEMES.map(function (t, i) { return '<button type="button" data-cmp-theme="' + i + '">' + esc(t[0]) + '</button>'; }).join('') + '</div>'),
      text: propsOf('text', style),
      look: propsOf('colors', style) + wsCard('پس‌زمینهٔ گروه', 'رنگ ساده، گرادیان، تصویر از کتابخانهٔ رسانه یا الگو.', bgHtml(s)),
      box: propsOf('spacing', style) + propsOf('border', style) + propsOf('size', style) +
        wsCard('فاصله و چینش خانه‌ها', '', intControl('flat', 'gap', 'فاصلهٔ بین خانه‌ها (px)', s.gap, 0, 64) +
          '<div class="rs-cmp-field"><label>تراز عمودی خانه‌ها</label><select data-cmp-choice="flat:vertical_align">' + selectOpts(VALIGN, s.vertical_align) + '</select></div>' +
          '<div class="rs-cmp-field"><label>ارتفاع خانه‌ها</label><select data-cmp-choice="flat:height_mode">' + selectOpts(HEIGHT_MODES, s.height_mode) + '</select></div>'),
      device: propsOf('visibility', style) + wsCard('رفتار در موبایل', 'چیدمان در تبلت از دسکتاپ پیروی می‌کند؛ فقط پنهان‌سازی برای تبلت جداست.',
        '<div class="rs-cmp-field"><label>نمایش در موبایل</label><select data-cmp-choice="flat:mobile_mode">' + selectOpts(MOBILE_MODES, s.mobile_mode) + '</select></div>' +
        '<label class="rs-cmp-check"><input type="checkbox" data-cmp-reverse ' + (s.mobile_order === 'reverse' ? 'checked' : '') + '> ترتیب معکوس در موبایل</label>'),
    };
    var tabs = WS_TABS.map(function (t) {
      return '<button type="button" class="r4-inspector-tab r4-ws-tab" role="tab" data-cmp-wtab="' + t[0] + '" aria-selected="' + (ws.tab === t[0]) + '" tabindex="' + (ws.tab === t[0] ? 0 : -1) + '">' + t[1] + '</button>';
    }).join('');
    var body = '<div class="r4-inspector-body r4-ws-body">' + WS_TABS.map(function (t) {
      return '<section class="r4-inspector-panel-fields r4-ws-panel" role="tabpanel" data-cmp-wpanel="' + t[0] + '"' + (ws.tab === t[0] ? '' : ' hidden') +
        '><div class="r4-ws-cols r4-ws-cols--single"><div class="r4-ws-col r4-ws-col--main">' + panels[t[0]] + '</div></div></section>';
    }).join('') + '</div>';
    return '<div class="r4-inspector-panel r4-ws" data-cmp-ws data-cmp-ws-id="' + g.id + '">' +
      '<header class="r4-ws-header"><div class="r4-ws-identity"><span class="r4-ws-glyph" aria-hidden="true">' + icon('grid') + '</span><div class="r4-ws-titles">' +
      '<div class="r4-ws-crumb"><span>' + esc(crumb) + '</span></div>' +
      '<div class="r4-ws-titlerow"><h2 class="r4-inspector-title r4-ws-title" data-cmp-ws-title>' + esc(groupName(g)) + '</h2><span class="r4-ws-scope">' + fa(g.cells.length) + ' ' + (axisOf(g) === 'vertical' ? 'ردیف' : 'ستون') + ' · ' + (axisOf(g) === 'vertical' ? 'عمودی' : 'افقی') + '</span></div></div></div>' +
      '<div class="r4-ws-save" data-r4-ws-save role="status" aria-live="polite">' + icon('check') + '<span data-r4-ws-save-text>پیش‌نویس ذخیره شد</span></div>' +
      '<button type="button" class="r4-ws-close" data-r4-inspector-close aria-label="بستن تنظیمات">' + icon('close') + '<span>بستن</span></button></header>' +
      '<div class="r4-inspector-tabs r4-ws-tabs" role="tablist" aria-label="دسته‌بندی تنظیمات گروه">' + tabs + '</div>' +
      '<div class="r4-ws-main">' + body + '</div></div>';
  }

  function wsGroup() { return ws.open && groupIdx[ws.id] ? groupIdx[ws.id].group : null; }

  function renderWorkspace(force) {
    if (!ws.open || !inspectorEl) return;
    var g = wsGroup();
    if (!g) { if (R4.closeInspector) R4.closeInspector(); return; }
    var active = document.activeElement;
    if (!force && active && inspectorEl.contains(active) && /^(INPUT|TEXTAREA)$/.test(active.tagName) && !/^(checkbox|color|range)$/.test(active.type)) return;
    var main = inspectorEl.querySelector('.r4-ws-main');
    var top = main ? main.scrollTop : 0;
    inspectorEl.innerHTML = workspaceHtml(g);
    var again = inspectorEl.querySelector('.r4-ws-main');
    if (again) again.scrollTop = top;
  }

  function openWorkspace(groupId) {
    if (!inspectorEl || !groupIdx[groupId]) return;
    if (R4.isGlobalDesignOpen && R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
    if (R4.inspectorOpen && !ws.open && R4.closeInspector) R4.closeInspector();       // a Section workspace never stays open under this one
    ws.id = groupId;
    ws.open = true;
    ws.tab = 'content';
    st.menu = false;
    renderWorkspace(true);
    inspectorEl.hidden = false;
    root.dataset.r4InspectorOpen = 'true';
    R4.inspectorOpen = true;
    var dialog = document.querySelector('[data-rs-workspace-dialog]');
    if (dialog) dialog.setAttribute('aria-label', 'تنظیمات گروه');
    R4.emit('r4:inspector-opened', { sectionId: null, group: true });
    window.setTimeout(function () { var f = inspectorEl.querySelector('[data-cmp-text="title"]'); if (f) f.focus({ preventScroll: true }); }, 60);
  }

  root.addEventListener('r4:inspector-closed', function () {
    if (!ws.open) return;
    ws.open = false;
    ws.id = null;
    var dialog = document.querySelector('[data-rs-workspace-dialog]');
    if (dialog) dialog.setAttribute('aria-label', 'تنظیمات بخش');
    renderAll();
  });
  root.addEventListener('r4:inspector-opened', function (evt) {
    if (ws.open && !(evt.detail && evt.detail.group)) {       // a Section (or the announcement) workspace replaced this one
      ws.open = false;
      ws.id = null;
      var dialog = document.querySelector('[data-rs-workspace-dialog]');
      if (dialog) dialog.setAttribute('aria-label', 'تنظیمات بخش');
    }
  });

  // ---- events ---------------------------------------------------------------------------------------------------------------------------------
  layer.addEventListener('click', function (evt) {
    var pick = evt.target.closest ? evt.target.closest('[data-cmp-pick]') : null;
    if (pick) { var bid = Number(pick.getAttribute('data-cmp-pick')); st.sel = null; st.menu = false; renderAll(); S.select(bid); S.edit(bid); return; }
    var btn = evt.target.closest ? evt.target.closest('[data-cmp]') : null;
    if (btn && !btn.disabled) {
      var action = btn.getAttribute('data-cmp');
      var op = operand();
      if (op && op.kind === 'section') { sectionAction(action, op); return; }
      if (action === 'edit') doEdit();
      else if (action === 'layout') { st.menu = st.menu === true ? false : true; toolbar.removeAttribute('data-sig'); schedule(); }
      else if (action === 'duplicate') doDuplicate();
      else if (action === 'up') doMove('up');
      else if (action === 'down') doMove('down');
      else if (action === 'remove') doRemove();
      else if (action === 'parent') selectParent();
      else if (action === 'close') { st.sel = null; st.menu = false; renderAll(); }
      return;
    }
    var split = evt.target.closest ? evt.target.closest('[data-cmp-split]') : null;
    if (split) { var p = split.getAttribute('data-cmp-split').split(':'); doSplit(p[0], Number(p[1])); return; }
    if (evt.target.closest && evt.target.closest('[data-cmp-add]')) doAddCell();
  });

  panel.addEventListener('click', function (evt) {
    var t = evt.target.closest ? evt.target : null;
    if (!t) return;
    if (t.closest('[data-cmp-panel-close]')) { st.panel = false; renderAll(); return; }
    if (t.closest('[data-cmp-panel-side]')) { st.side = st.side === 'start' ? 'end' : 'start'; try { window.localStorage.setItem('rsCmpSide', st.side); } catch (e) { /* best effort */ } applySide(); renderAll(); return; }
    if (t.closest('[data-cmp-add-row]')) { addRow(); return; }
    var node = t.closest('[data-cmp-node]');
    if (node) {
      var p = node.getAttribute('data-cmp-node').split(':');
      var kind = p[0], id = Number(p[1]);
      if (kind === 'header') S.openGlobal('header');
      else if (kind === 'footer') S.openGlobal('footer');
      else if (kind === 'block') { st.sel = null; st.menu = false; S.select(id); renderAll(); }
      else select({ kind: kind, id: id });
    }
  });

  function patchOne(flat, style) {
    var g = wsGroup();
    if (!g) return Promise.resolve();
    return patchGroup(g.id, flat, style);
  }
  function setColor(scope, key, value) {
    var o = {};
    o[key] = scope === 'style' ? (value || null) : value;
    return (scope === 'style' ? patchOne({}, o) : patchOne(o)).then(function () { renderWorkspace(true); });
  }
  function applyTheme(i) {
    var t = THEMES[i];
    if (!t) return;
    patchOne(t[2], t[1]).then(function () { renderWorkspace(true); });
  }

  if (inspectorEl) {
    inspectorEl.addEventListener('click', function (evt) {
      var t = evt.target.closest ? evt.target : null;
      if (!t || !ws.open || !t.closest('[data-cmp-ws]')) return;
      var tab = t.closest('[data-cmp-wtab]');
      if (tab) {
        ws.tab = tab.getAttribute('data-cmp-wtab');
        Array.prototype.forEach.call(inspectorEl.querySelectorAll('[data-cmp-wtab]'), function (b) { var on = b.getAttribute('data-cmp-wtab') === ws.tab; b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
        Array.prototype.forEach.call(inspectorEl.querySelectorAll('[data-cmp-wpanel]'), function (pn) { pn.hidden = pn.getAttribute('data-cmp-wpanel') !== ws.tab; });
        return;
      }
      var color = t.closest('[data-cmp-color]');
      if (color) { var cp = color.getAttribute('data-cmp-color').split(':'); setColor(cp[0], cp[1], color.getAttribute('data-value')); return; }
      var theme = t.closest('[data-cmp-theme]');
      if (theme) { applyTheme(Number(theme.getAttribute('data-cmp-theme'))); return; }
      var media = t.closest('[data-cmp-media]');
      if (media) patchOne({ background_mode: 'image', background_media_asset_id: Number(media.getAttribute('data-cmp-media')) }).then(function () { renderWorkspace(true); });
    });

    inspectorEl.addEventListener('input', function (evt) {
      var t = evt.target;
      if (!ws.open || !t.getAttribute || !t.closest('[data-cmp-ws]')) return;
      var intKey = t.getAttribute('data-cmp-int') || t.getAttribute('data-cmp-int-num');
      if (intKey) {
        var parts = intKey.split(':');
        var raw = t.value;
        var twin = inspectorEl.querySelector('[data-cmp-int' + (t.hasAttribute('data-cmp-int') ? '-num' : '') + '="' + intKey + '"]');
        if (twin) twin.value = raw;
        var val = raw === '' ? null : Number(raw);
        if (val !== null && isNaN(val)) return;
        if (parts[0] === 'style') { var so = {}; so[parts[1]] = val; patchOne({}, so); } else { var fo = {}; fo[parts[1]] = val == null ? 0 : val; patchOne(fo); }
        return;
      }
      var textKey = t.getAttribute('data-cmp-text');
      if (textKey) {
        var to = {}; to[textKey] = t.value;
        patchOne(to).then(function () { renderLayersOnly(); var h = inspectorEl.querySelector('[data-cmp-ws-title]'); var g = wsGroup(); if (h && g) h.textContent = groupName(g); });
        return;
      }
      var colorInput = t.getAttribute('data-cmp-color-input');
      if (colorInput) { var cp = colorInput.split(':'); setColor(cp[0], cp[1], t.value.toUpperCase()); }
    });

    inspectorEl.addEventListener('change', function (evt) {
      var t = evt.target;
      var g = wsGroup();
      if (!g || !t.getAttribute || !t.closest('[data-cmp-ws]')) return;
      var choice = t.getAttribute('data-cmp-choice');
      if (choice) {
        var parts = choice.split(':');
        var o = {}; o[parts[1]] = t.value === '' ? null : t.value;
        if (parts[0] === 'style') patchOne({}, o); else patchOne(o);
        return;
      }
      if (t.hasAttribute('data-cmp-titlevis')) { patchOne({ title_visible: t.checked }); return; }
      if (t.hasAttribute('data-cmp-reverse')) { patchOne({ mobile_order: t.checked ? 'reverse' : 'normal' }); return; }
      if (t.hasAttribute('data-cmp-bg-mode')) {
        var mode = t.value, flat = { background_mode: mode };
        var s = g.settings || {};
        if (mode === 'color' && !s.background_color) flat.background_color = '#F3F4F6';
        if (mode === 'gradient') { if (!s.background_color) flat.background_color = '#FFFFFF'; if (!s.background_color2) flat.background_color2 = '#DDF4EC'; }
        if (mode === 'pattern') { if (!s.background_color) flat.background_color = '#F3F4F6'; flat.background_pattern = (st.patterns[0] && st.patterns[0].key) || 'commerce-doodle'; }
        patchOne(flat).then(function () { renderWorkspace(true); });
        return;
      }
      if (t.hasAttribute('data-cmp-pattern')) patchOne({ background_pattern: t.value });
    });
  }

  // ---- canvas integration (the preview iframe) -------------------------------------------------------------------------------------------
  function bindFrame(f) {
    var win;
    try { win = f && f.contentWindow; if (!win || !win.document) return; } catch (e) { return; }
    if (win.__rsCmpBound) return;
    win.__rsCmpBound = true;
    win.addEventListener('click', function (evt) {
      if (win.document.documentElement.getAttribute('data-sfb-builder-mode') === 'preview') return;
      var t = evt.target && evt.target.closest ? evt.target : null;
      if (!t) return;
      var chip = t.closest('[data-cell-layout], [data-group-layout]');
        if (chip) {
        evt.preventDefault(); evt.stopPropagation();
        if (chip.hasAttribute('data-cell-layout')) select({ kind: 'cell', id: Number(chip.getAttribute('data-cell-layout')) }, { menu: false });
        else select({ kind: 'group', id: Number(chip.getAttribute('data-group-layout')) }, { menu: false });
        return;
      }
      // a click on a link inside a Section (a product card, a banner …) selects that Section instead of navigating the seller away; real
      // buttons / controls keep working, and the customer preview and the published storefront never see this listener
      if (R4.previewInteractive !== false) {
        var anchor = t.closest('a[href], .pcard');            // a product card's own quick actions (add to cart, wishlist …) select the shelf in design mode too
        var owner = anchor && anchor.closest('.rsec[data-section-id]');
        if (owner && /^\d+$/.test(owner.getAttribute('data-section-id'))) {
          evt.preventDefault(); evt.stopPropagation();
          st.sel = null; st.menu = false;
          S.select(Number(owner.getAttribute('data-section-id')));
          renderAll();
          return;
        }
      }
      // a click on a Group's frame / heading (not on a component) selects the Group
      var frameEl = t.closest('.rgroup[data-group-id]');
      if (frameEl && !t.closest('[data-section-id]') && !t.closest('.rcontainer-cell')) {
        evt.preventDefault(); evt.stopPropagation();
        select({ kind: 'group', id: Number(frameEl.getAttribute('data-group-id')) });
      }
    }, true);
    win.addEventListener('dblclick', function (evt) {
      var t = evt.target && evt.target.closest ? evt.target : null;
      var field = t && t.closest('.rgroup-title, .rgroup-description');
      if (!field) return;
      var frameEl = field.closest('.rgroup[data-group-id]');
      if (!frameEl) return;
      evt.preventDefault(); evt.stopPropagation();
      inlineEdit(field, Number(frameEl.getAttribute('data-group-id')), field.classList.contains('rgroup-title') ? 'title' : 'description');
    }, true);
    win.addEventListener('keydown', function (evt) { if (evt.key === 'Escape' && !evt.defaultPrevented) clearAny(); });
    win.addEventListener('scroll', schedule, { passive: true });
    win.addEventListener('resize', schedule);
    if (win.ResizeObserver) { try { new win.ResizeObserver(schedule).observe(win.document.documentElement); } catch (e) { /* best effort */ } }
    schedule();
  }

  function inlineEdit(el, groupId, key) {
    var original = el.textContent;
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('role', 'textbox');
    el.focus();
    try { var range = el.ownerDocument.createRange(); range.selectNodeContents(el); var sel = el.ownerDocument.defaultView.getSelection(); sel.removeAllRanges(); sel.addRange(range); } catch (e) { /* best effort */ }
    var finished = false;
    function finish(commit) {
      if (finished) return;
      finished = true;
      el.removeAttribute('contenteditable');
      el.removeAttribute('role');
      var value = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!commit || value === original.trim()) { el.textContent = original; return; }
      var patch = {}; patch[key] = value;
      patchGroup(groupId, patch).then(function () { renderWorkspace(); });
    }
    el.addEventListener('blur', function () { finish(true); }, { once: true });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); el.blur(); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); el.blur(); }
    });
  }

  document.addEventListener('load', function (evt) {
    var f = evt.target;
    if (f && f.tagName === 'IFRAME' && f.hasAttribute('data-rs-draft-src')) { bindFrame(f); window.setTimeout(schedule, 150); }
  }, true);
  bindFrame(frame());

  // the header / footer drawn on the canvas open the real Global Design editors
  window.addEventListener('message', function (evt) {
    var f = frame();
    if (!f || evt.source !== f.contentWindow || evt.origin !== window.location.origin || !evt.data) return;
    if (evt.data.type === 'sfb:openHeaderSettings') S.openGlobal('header');
    else if (evt.data.type === 'sfb:openFooterSettings') S.openGlobal('footer');
  });

  // ---- rail buttons + state sources ---------------------------------------------------------------------------------------------------------
  root.addEventListener('r4:section-selected', function () {
    if (selfChange) return;
    if (S.selectedId() && st.sel) { st.sel = null; st.menu = false; }
    renderAll();
  });
  root.addEventListener('r4:structure-refreshed', function () { loadTree().then(function () { renderAll(); renderWorkspace(); }); });
  root.addEventListener('r4:history', function () { window.setTimeout(function () { loadTree().then(function () { renderAll(); renderWorkspace(true); }); }, 200); });
  ['r4:device', 'r4:inspector-opened', 'r4:inspector-closed'].forEach(function (name) { root.addEventListener(name, function () { window.setTimeout(schedule, 40); }); });
  window.addEventListener('resize', schedule);
  canvas.addEventListener('scroll', schedule, true);
  window.setInterval(function () { if (!document.hidden && (st.sel || sectionSel())) schedule(); }, 800);
  function clearAny() {
    if (st.menu) { st.menu = false; toolbar.removeAttribute('data-sig'); schedule(); return; }
    if (st.sel) { st.sel = null; renderAll(); return; }
    if (sectionSel()) { S.clearSelection(); renderAll(); }
  }
  document.addEventListener('keydown', function (evt) {
    if (evt.key !== 'Escape' || S.blocked()) return;
    var tg = evt.target;
    if (tg && /^(input|textarea|select)$/i.test(tg.tagName || '')) return;
    clearAny();
  });

  // exposed for the section toolbar («چیدمان» next to «ویرایش») and for tests
  R4.composer = {
    layoutOfSection: function (sectionId) {
      var found = null;
      Object.keys(cellIdx).forEach(function (cid) { if (cellIdx[cid].cell.blocks.some(function (b) { return b.id === Number(sectionId); })) found = Number(cid); });
      if (found) select({ kind: 'cell', id: found }, { menu: true });
    },
    select: function (kind, id, opts) { select({ kind: kind, id: Number(id) }, opts); },
    // the rows / Groups whose boundaries the resize layer should offer for the current selection (its own and its parent's)
    containersOfSelection: function () {
      var op = operand();
      if (!op) return [];
      if (!op.group) return [];
      var out = [op.group.id];
      if (op.kind === 'group' && op.hostCellId != null) { var h = cellIdx[op.hostCellId]; if (h) out.push(h.group.id); }
      if (op.kind === 'cell') { var gi = groupIdx[op.group.id]; if (gi && gi.parentGroupId != null) out.push(gi.parentGroupId); }
      return out;
    },
    tree: function () { return st.tree; },
    reload: function () { return loadTree().then(function (d) { renderAll(); return d; }); },
    selection: function () { return st.sel; },
    // true while the toolbar on the canvas is this file's (every Section / cell / Group selection): the resize layer then keeps its own hidden
    ownsToolbar: function () { return true; },
    openGroupSettings: function (id) { openWorkspace(Number(id)); },
    addRow: addRow,
    togglePanel: function () { st.panel = !st.panel; if (st.panel && !st.loaded) loadTree().then(renderAll); renderAll(); },
  };

  loadTree().then(renderAll);
})();
