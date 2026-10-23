/*
 * RastiSi Design Studio — the announcement strip's picture (UI layer only).
 *
 * The strip's settings live in the Draft header_config and are written ONLY by the normal ``header.update`` mutation (the generic global-design
 * field handler of r4_editor.js: Revision, Undo/Redo, Draft isolation). This file does the one thing a header field cannot: it uploads the
 * chosen picture into THIS store's media library (the same MediaAsset model, size limit and image check as every storefront picture) and then
 * puts the returned asset id into the field, firing the field's own ``change`` event — the existing handler sends the mutation. Removing the
 * picture clears that field the same way. Nothing is stored in the browser; a failed upload changes nothing and says why.
 */
(function () {
  'use strict';

  var root = document.querySelector('.rs-studio[data-r4-shell]');
  if (!root) return;
  var MAX_BYTES = 5 * 1024 * 1024;
  var TYPES = ['image/png', 'image/jpeg', 'image/webp'];

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
      if (removeBox) { status(removeBox, 'تصویر حذف شد.', false); setAsset(removeBox, ''); }
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
        if (result && result.ok) { status(box, 'تصویر بارگذاری شد؛ در حال اعمال روی پیش‌نویس…', false); setAsset(box, result.asset_id); }
        else status(box, (result && result.message) || 'بارگذاری انجام نشد؛ هیچ تغییری ذخیره نشد.', true);
      })
      .catch(function () {
        box.removeAttribute('aria-busy');
        status(box, 'ارتباط با سرور برقرار نشد؛ هیچ تغییری ذخیره نشد.', true);
      });
  });
})();
