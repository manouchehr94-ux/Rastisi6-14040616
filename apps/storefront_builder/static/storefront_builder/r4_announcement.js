/*
 * RastiSi Design Studio — the announcement strip's editor (UI layer only).
 *
 * V5-UI-014: the strip is selected and edited like any other Section — click it in the live preview (the preview document's own selection:
 * data-section-id="announcement"), the standard dark R4 toolbar appears (r4_resize.js; «ویرایش» + on/off only — the strip is fixed above the
 * header, so no move / duplicate), and «ویرایش» opens the standard settings workspace (محتوا / طراحی / پیشرفته) rendered by the server from the
 * Draft header_config. That workspace is a VIEW: it owns no data. Every change is sent through the ONE existing write authority —
 * ``R4.enqueueMutation({type: 'header.update'})`` — so Revision, Undo/Redo and Draft/Published isolation are exactly those of the header.
 * Nothing is stored in the browser. The one thing a header field cannot do — uploading the small picture — goes into THIS store's media
 * library (the same MediaAsset model, size limit and image check as every storefront picture) and only its id is then written the same way.
 */
(function () {
  'use strict';

  var R4 = window.RastiSiR4;
  var root = document.querySelector('.rs-studio[data-r4-shell]');
  if (!root || !R4) return;
  var ID = 'announcement';
  var MAX_BYTES = 5 * 1024 * 1024;
  var TYPES = ['image/png', 'image/jpeg', 'image/webp'];
  var DATA = {};
  try { DATA = JSON.parse(document.getElementById('rsStudioData').textContent) || {}; } catch (e) { DATA = {}; }
  var inspector = document.getElementById('r4Inspector');
  // a refreshed preview is a NEW iframe that takes over the id (twin swap, r4_editor.js): always look the frame up, never keep a reference
  function frameEl() { return document.getElementById('r4PreviewFrame'); }
  var isOpen = false;
  var sent = {};
  var textTimer = null;

  function notify(text) { if (R4.studio && R4.studio.notify) R4.studio.notify(text); }
  function panel() { return inspector ? inspector.querySelector('[data-r4-announcement-inspector]') : null; }

  // ---- the settings workspace ------------------------------------------------------------------------------------------------
  function activeTab() {
    var tab = inspector && inspector.querySelector('[data-r4-tab][aria-selected="true"]');
    return tab ? tab.getAttribute('data-r4-tab') : 'content';
  }

  function show(tab) {
    var target = inspector.querySelector('[data-r4-tab="' + (tab || 'content') + '"]');
    if (target) target.click();                      // the Inspector's own tab handler (r4_editor.js) switches the panels
  }

  function load(tab) {
    if (!inspector || !DATA.announcement_inspector_url) return Promise.resolve(false);
    return fetch(DATA.announcement_inspector_url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
      .then(function (response) { return response.ok ? response.text() : null; })
      .then(function (html) {
        if (html == null) { notify('تنظیمات نوار اطلاعیه بارگذاری نشد؛ دوباره تلاش کنید.'); return false; }
        inspector.innerHTML = html;
        sent = {};
        show(tab);
        return true;
      })
      .catch(function () { notify('ارتباط با سرور برقرار نشد؛ تنظیمات نوار اطلاعیه باز نشد.'); return false; });
  }

  function open(tab) {
    if (R4.isGlobalDesignOpen && R4.isGlobalDesignOpen()) R4.closeGlobalDesign();
    if (R4.inspectorOpen && !isOpen && R4.closeInspector) R4.closeInspector();      // a Section workspace never stays open under this one
    return load(tab).then(function (ok) {
      if (!ok) return;
      inspector.hidden = false;
      root.dataset.r4InspectorOpen = 'true';
      R4.inspectorOpen = true;
      isOpen = true;
      R4.previewSelected = ID;
      postSelection();
      R4.emit('r4:inspector-opened', { sectionId: ID });
      openLive();
    });
  }

  function postSelection() {
    try { frameEl().contentWindow.postMessage({ type: 'sfb:setSelection', sectionId: ID }, window.location.origin); } catch (e) { /* preview not ready */ }
  }

  // ---- writes: ONE authority ---------------------------------------------------------------------------------------------------
  function send(patch) {
    return R4.enqueueMutation({ type: 'header.update', patch: patch }).then(function (result) {
      if (result && result.ok) {
        R4.refreshPreview();
        reloadLive();
      }
      return result;
    });
  }

  function readColor(control) {
    var select = control.querySelector('[data-r4-color-token]');
    var custom = control.querySelector('[data-r4-color-custom]');
    if (select && select.value === 'custom') return custom ? String(custom.value).toUpperCase() : '';
    return select ? select.value : '';
  }

  function links(wrapper) {
    return Array.prototype.map.call(wrapper.querySelectorAll('[data-r4-repeater-row]'), function (row) {
      var label = row.querySelector('[data-r4-repeater-subfield="label"]');
      var url = row.querySelector('[data-r4-repeater-subfield="url"]');
      return { label: label ? label.value.trim() : '', url: url ? url.value.trim() : '' };
    }).filter(function (link) { return link.label || link.url; });
  }

  function commit(evt, fromInput) {
    var box = evt.target.closest ? evt.target.closest('[data-r4-announcement-inspector]') : null;
    if (!box) return;
    var target = evt.target;
    var geometryColor = target.closest('[data-r4-color-control][data-r4-global-geometry-key]');
    if (geometryColor) {
      if (fromInput) return;
      var colorPatch = { geometry: {} };
      colorPatch.geometry[geometryColor.getAttribute('data-r4-global-geometry-key')] = readColor(geometryColor);
      send(colorPatch);
      return;
    }
    var toggle = target.closest('[data-r4-global-responsive-toggle]');
    if (toggle) {
      var inner = {};
      inner[toggle.getAttribute('data-r4-global-responsive-prop')] = toggle.checked;
      var responsive = {};
      responsive[toggle.getAttribute('data-r4-global-responsive-key')] = inner;
      send({ responsive: responsive });
      return;
    }
    var repeater = target.closest('[data-r4-ann-repeater]');
    if (repeater && target.closest('[data-r4-repeater-subfield]')) {
      var rows = links(repeater);
      var signature = JSON.stringify(rows);
      if (sent.announcement_links === signature) return;
      sent.announcement_links = signature;
      send({ announcement_links: rows });
      return;
    }
    var field = target.closest('[data-r4-global-field]');
    if (!field) return;
    var key = field.getAttribute('data-r4-global-field');
    var value = field.type === 'checkbox' ? field.checked : field.value;
    var patch = {};
    var token = key;
    if (key === 'geometry') {
      var geometryKey = field.getAttribute('data-r4-global-geometry-key');
      if (!geometryKey) return;
      patch.geometry = {};
      patch.geometry[geometryKey] = value;
      token = 'geometry.' + geometryKey;
    } else {
      patch[key] = value;
    }
    if (sent[token] === String(value)) return;        // typing then leaving the field must not store the same value twice
    sent[token] = String(value);
    send(patch);
  }

  if (inspector) {
    inspector.addEventListener('change', function (evt) { clearTimeout(textTimer); commit(evt, false); });
    // typing in a text field shows in the live preview without waiting for the field to lose focus (one write per pause, latest value wins)
    inspector.addEventListener('input', function (evt) {
      var t = evt.target;
      if (!t || !t.closest || !t.closest('[data-r4-announcement-inspector]')) return;
      if (!t.matches('input[type="text"]')) return;
      clearTimeout(textTimer);
      textTimer = setTimeout(function () { commit(evt, true); }, 700);
    });
  }

  // ---- repeater (extra links) ----------------------------------------------------------------------------------------------------
  function repeaterOf(el) { return el.closest('[data-r4-ann-repeater]'); }
  function patchLinks(wrapper) {
    var rows = links(wrapper);
    sent.announcement_links = JSON.stringify(rows);
    send({ announcement_links: rows });
  }

  root.addEventListener('click', function (evt) {
    var add = evt.target.closest('[data-r4-ann-add]');
    if (add) {
      var wrapper = repeaterOf(add);
      var template = wrapper && wrapper.querySelector('[data-r4-ann-row-template]');
      var rowsBox = wrapper && wrapper.querySelector('[data-r4-repeater-rows]');
      if (template && rowsBox) {
        rowsBox.appendChild(template.content.cloneNode(true));
        var input = rowsBox.querySelector('[data-r4-repeater-row]:last-child [data-r4-repeater-subfield]');
        if (input) input.focus();
      }
      return;
    }
    var remove = evt.target.closest('[data-r4-ann-remove]');
    if (remove) {
      var removeWrapper = repeaterOf(remove);
      var row = remove.closest('[data-r4-repeater-row]');
      if (removeWrapper && row) { row.remove(); patchLinks(removeWrapper); }
      return;
    }
    var move = evt.target.closest('[data-r4-ann-move]');
    if (move) {
      var moveWrapper = repeaterOf(move);
      var moveRow = move.closest('[data-r4-repeater-row]');
      var up = move.getAttribute('data-r4-ann-move') === 'up';
      var neighbour = moveRow && (up ? moveRow.previousElementSibling : moveRow.nextElementSibling);
      if (moveWrapper && moveRow && neighbour) {
        if (up) moveRow.parentNode.insertBefore(moveRow, neighbour); else moveRow.parentNode.insertBefore(neighbour, moveRow);
        patchLinks(moveWrapper);
      }
      return;
    }
    if (evt.target.closest('[data-rastisi-action="edit-announcement"]')) open('content');
  });

  // ---- the small picture ---------------------------------------------------------------------------------------------------------
  function block(el) { return el.closest('[data-r4-announce-image]'); }
  function status(box, text, bad) {
    var line = box && box.querySelector('[data-r4-announce-status]');
    if (!line) return;
    line.textContent = text;
    line.classList.toggle('is-error', !!bad);
  }
  function cookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }
  function thumb(box, url) {
    var holder = box.querySelector('[data-r4-announce-thumb]');
    var removeButton = box.querySelector('[data-r4-announce-remove]');
    if (holder) {
      holder.textContent = '';
      if (url) { var img = document.createElement('img'); img.src = url; img.alt = ''; holder.appendChild(img); }
      else { var none = document.createElement('span'); none.textContent = 'بدون تصویر'; holder.appendChild(none); }
    }
    if (removeButton) removeButton.disabled = !url;
  }
  function setAsset(box, value) {
    var field = box.querySelector('[data-r4-global-field="announcement_image_asset_id"]');
    if (!field) return;
    field.value = value == null ? '' : String(value);
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  root.addEventListener('click', function (evt) {
    var pick = evt.target.closest('[data-r4-announce-pick]');
    if (pick) {
      var box = block(pick);
      var file = box && box.querySelector('[data-r4-announce-file]');
      if (file) { file.value = ''; file.click(); }
      return;
    }
    var remove = evt.target.closest('[data-r4-announce-remove]');
    if (remove && !remove.disabled) {
      var removeBox = block(remove);
      if (removeBox) { status(removeBox, 'تصویر حذف شد.', false); thumb(removeBox, ''); setAsset(removeBox, ''); }
    }
  });

  root.addEventListener('change', function (evt) {
    var input = evt.target.closest ? evt.target.closest('[data-r4-announce-file]') : null;
    if (!input || !input.files || !input.files[0]) return;
    var box = block(input);
    var file = input.files[0];
    if (TYPES.indexOf(file.type) === -1) { status(box, 'فقط تصویر PNG، JPG یا WebP پذیرفته می‌شود.', true); return; }
    if (file.size > MAX_BYTES) { status(box, 'حجم تصویر نباید بیشتر از ۵ مگابایت باشد.', true); return; }
    var url = box.getAttribute('data-r4-announce-upload-url');
    var body = new FormData();
    body.append('image', file);
    status(box, 'در حال بارگذاری…', false);
    box.setAttribute('aria-busy', 'true');
    fetch(url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': cookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (response) { return response.json().catch(function () { return { ok: false }; }); })
      .then(function (result) {
        box.removeAttribute('aria-busy');
        if (result && result.ok) {
          status(box, 'تصویر بارگذاری شد؛ در حال اعمال روی پیش‌نویس…', false);
          thumb(box, result.url || '');
          setAsset(box, result.asset_id);
        } else status(box, (result && result.message) || 'بارگذاری انجام نشد؛ هیچ تغییری ذخیره نشد.', true);
      })
      .catch(function () {
        box.removeAttribute('aria-busy');
        status(box, 'ارتباط با سرور برقرار نشد؛ هیچ تغییری ذخیره نشد.', true);
      });
  });

  // ---- live view of THIS strip inside the workspace (same aside, same draft page, only the strip shown) -----------------------------------
  var live = { frame: null, stage: null, sizer: null, aside: null, timers: [] };

  function fitLive() {
    if (!live.frame) return;
    try {
      var doc = live.frame.contentDocument;
      var strip = doc && doc.querySelector('[data-builder-announcement]');
      if (!strip) return;
      var logicalWidth = parseInt(frameEl() && frameEl().style.width, 10) || 1440;
      var avail = live.stage.clientWidth;
      if (!avail) return;
      var scale = Math.min(1, avail / logicalWidth);
      var height = Math.max(32, Math.ceil(strip.getBoundingClientRect().height + 2));
      live.frame.style.width = logicalWidth + 'px';
      live.frame.style.height = height + 'px';
      live.frame.style.transform = 'scale(' + scale + ')';
      live.sizer.style.height = Math.ceil(height * scale) + 'px';
    } catch (e) { /* the frame is still loading */ }
  }

  function focusLive() {
    try {
      var doc = live.frame.contentDocument;
      if (!doc || !doc.head || !doc.querySelector('[data-builder-announcement]')) return;
      var style = doc.getElementById('r4-ann-focus');
      if (!style) { style = doc.createElement('style'); style.id = 'r4-ann-focus'; doc.head.appendChild(style); }
      style.textContent =
        'html,body{overflow:hidden!important;background:transparent!important}body{pointer-events:none!important;margin:0!important}' +
        'header,main,footer,.mobile-bottom-nav,.sfb-storefront-canvas,.gh-shell>:not([data-builder-announcement]){display:none!important}' +
        '.sfb-builder-announcement{outline:none!important}';
      var loading = live.aside.querySelector('[data-r4-ws-live-loading]');
      if (loading) loading.hidden = true;
    } catch (e) { /* best effort: the live view is an aid, never a dependency */ }
    fitLive();
    live.timers.push(setTimeout(fitLive, 450), setTimeout(fitLive, 1500));
  }

  function openLive() {
    var aside = document.querySelector('[data-r4-ws-live]');
    var preview = frameEl();
    if (!aside || !preview || !window.matchMedia('(min-width:1101px)').matches) return;
    var src = preview.getAttribute('data-rs-draft-src') || preview.getAttribute('src');
    var stage = aside.querySelector('[data-r4-ws-live-stage]');
    var sizer = aside.querySelector('[data-r4-ws-live-sizer]');
    var frame = aside.querySelector('[data-r4-ws-live-frame]');
    if (!src || !stage || !sizer || !frame) return;
    var loading = aside.querySelector('[data-r4-ws-live-loading]');
    if (loading) loading.hidden = false;
    var head = aside.querySelector('.r4-ws-live-head strong');
    if (head && head.lastChild) head.lastChild.textContent = 'پیش‌نمایش زندهٔ نوار اطلاعیه';
    sizer.style.height = '';
    frame.style.transform = '';
    frame.onload = function () { if (live.frame === frame && frame.getAttribute('src') && frame.getAttribute('src') !== 'about:blank') focusLive(); };
    aside.hidden = false;
    live = { frame: frame, stage: stage, sizer: sizer, aside: aside, timers: [] };
    live.timers.push(setTimeout(function () { if (live.frame === frame) frame.setAttribute('src', src); }, 300));
  }

  function reloadLive() {
    if (!live.frame || !live.frame.contentWindow) return;
    try { live.frame.contentWindow.location.reload(); } catch (e) { /* ignore */ }
  }

  function closeLive() {
    live.timers.forEach(clearTimeout);
    if (live.frame) { try { live.frame.removeAttribute('src'); live.frame.src = 'about:blank'; } catch (e) { /* ignore */ } }
    if (live.aside) live.aside.hidden = true;
    live = { frame: null, stage: null, sizer: null, aside: null, timers: [] };
  }

  root.addEventListener('r4:inspector-closed', function () {
    if (!isOpen) return;
    isOpen = false;
    clearTimeout(textTimer);
    closeLive();
  });
  root.addEventListener('r4:inspector-opened', function (evt) {
    // a Section workspace opened while this one was open (never both)
    if (isOpen && evt.detail && evt.detail.sectionId !== ID) { isOpen = false; closeLive(); }
  });
  // Undo / Redo: the open workspace shows the restored values (the same tab stays active)
  root.addEventListener('r4:history', function () {
    if (!isOpen || !panel()) return;
    load(activeTab());
    window.setTimeout(reloadLive, 400);
  });

  // ---- selection coming from the preview (the preview document's own click / double-click: sfb:selectSection / sfb:openSectionSettings) ----
  window.addEventListener('message', function (evt) {
    if (evt.origin !== window.location.origin || !evt.data || !frameEl() || evt.source !== frameEl().contentWindow) return;
    if (String(evt.data.sectionId) !== ID) return;
    if (evt.data.type === 'sfb:selectSection') {
      R4.previewSelected = ID;
      R4.emit('r4:section-selected', { sectionId: ID });
    } else if (evt.data.type === 'sfb:openSectionSettings') {
      R4.previewSelected = ID;
      R4.emit('r4:direct-edit', { sectionId: ID });
      open('content');
    }
  });

  // a refreshed preview document starts without the selection frame: put it back while the strip is selected / its workspace is open
  document.addEventListener('load', function (evt) {
    var f = evt.target;
    if (!f || f.tagName !== 'IFRAME' || !f.hasAttribute('data-rs-draft-src')) return;
    if (isOpen || (R4.studio && R4.studio.selectedId && R4.studio.selectedId() === ID)) window.setTimeout(postSelection, 80);
  }, true);

  // ---- what the standard toolbar needs (r4_resize.js / r4_studio.js) ---------------------------------------------------------------------
  function stripState() {
    try {
      var doc = frameEl().contentDocument;
      var strip = doc && doc.querySelector('[data-builder-announcement]');
      return { present: !!strip, off: !!(strip && strip.hasAttribute('data-builder-announcement-off')) };
    } catch (e) { return { present: false, off: false }; }
  }

  R4.announcement = {
    id: ID,
    open: open,
    state: stripState,
    // on / off: ONE header.update (Undo-able); every stored value of the strip stays
    toggle: function () {
      var enable = stripState().off;
      return send({ announcement_enabled: enable }).then(function (result) {
        if (result && result.ok) notify(enable ? 'نوار اطلاعیه فعال شد.' : 'نوار اطلاعیه غیرفعال شد؛ متن و تنظیمات آن حفظ شد.');
        return result;
      });
    },
  };
})();
