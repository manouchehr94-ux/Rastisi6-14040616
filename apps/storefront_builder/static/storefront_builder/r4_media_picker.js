/* R4 picture picker — dresses every Inspector `media` field.
 *
 * The native <select data-r4-field-key data-r4-field-type="media"> stays the ONE data carrier (value = MediaAsset id, "" = none): the generic
 * scalar path hydrates it, saves it, undoes and redoes it. This file only adds what a merchant needs around it:
 *   - a real thumbnail, the file name and the pixel size of the chosen picture (never «رسانه #12»);
 *   - choose from the Store's own library (thumbnail grid), upload a NEW picture in place, replace, remove;
 *   - size / ratio / safe-area guidance for THIS slot — computed live from the stage's own settings (layout, split, height, fit, text
 *     position, header mode) when the section registered a guide spec (see media_guide.py), a neutral hint otherwise;
 *   - a non-blocking warning when the picture is too small, would be cropped hard, or is very heavy.
 * No picture is ever written here: every change goes through `select.value = id` + a bubbling `change`, exactly like the old control. */
(function () {
  'use strict';

  var DIGITS = '۰۱۲۳۴۵۶۷۸۹';
  function fa(value) { return String(value).replace(/\d/g, function (d) { return DIGITS.charAt(+d); }); }
  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function round10(n) { return Math.max(10, Math.round(n / 10) * 10); }

  var nativeValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  var dimsCache = {};
  function readDims(url) {
    if (!url) return Promise.resolve(null);
    if (!dimsCache[url]) {
      dimsCache[url] = new Promise(function (resolve) {
        var img = new Image();
        img.onload = function () { resolve({ w: img.naturalWidth, h: img.naturalHeight }); };
        img.onerror = function () { resolve(null); };
        img.src = url;
      });
    }
    return dimsCache[url];
  }

  function guideSpec() {
    var node = document.getElementById('r4MediaGuideSpec');
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch (err) { return null; }
  }

  // ---- the guide: the recommended pixels for the composition the merchant has CHOSEN ------------------------------------------------
  function fieldValue(scope, key) {
    // the field ROW carries the same data attribute (and a value of its own): only a real form control tells the current setting
    var control = scope.querySelector('select[data-r4-field-key="' + key + '"], input[data-r4-field-key="' + key + '"], textarea[data-r4-field-key="' + key + '"]');
    return control ? control.value : '';
  }

  function computeGuide(spec, key, scope) {
    var slot = spec && spec.slots && spec.slots[key];
    if (!slot) return null;
    var desktop = spec.viewports.desktop, mobile = spec.viewports.mobile;
    var layout = fieldValue(scope, 'bg_layout') || 'single';
    var split = fieldValue(scope, 'bg_split') || 'equal';
    var hd = parseInt(fieldValue(scope, 'height_desktop'), 10) || 85;
    var hm = parseInt(fieldValue(scope, 'height_mobile'), 10) || 70;
    var mobileDual = fieldValue(scope, 'mobile_dual') || 'stack';
    var fit = fieldValue(scope, 'image_fit') || 'cover';
    var align = fieldValue(scope, 'content_align') || 'center';
    var valign = fieldValue(scope, 'content_valign') || 'middle';
    var headerMode = fieldValue(scope, 'header_mode') || 'merged';
    var dual = layout === 'dual';
    var fractions = spec.splits[split] || [1, 1];
    var share = !dual ? 1 : (slot.slot === 'a' ? fractions[0] : fractions[1]) / (fractions[0] + fractions[1]);
    var inactive = !dual && slot.slot === 'b';

    var stageH = desktop[1] * hd / 100;
    var rec = { w: round10(desktop[0] * share), h: round10(stageH) };
    var min = { w: round10(rec.w * 0.65), h: round10(rec.h * 0.65) };
    var mobileStage = mobile[1] * hm / 100;
    var mobilePanelH = dual && mobileDual === 'stack' ? mobileStage / 2 : mobileStage;
    var mobileHidden = dual && slot.slot === 'b' && mobileDual === 'first_only';
    var ratio = rec.w / rec.h;

    var hText = { start: 'سمت راست', center: 'مرکز', end: 'سمت چپ' }[align] || 'مرکز';
    var vText = { top: 'بالا', middle: 'وسط', bottom: 'پایین' }[valign] || 'وسط';
    var lines = [];
    if (inactive) {
      lines.push(['نقش', slot.role_single]);
    } else {
      lines.push(['نقش', dual ? slot.role_dual : slot.role_single]);
      lines.push(['اندازهٔ پیشنهادی', fa(rec.w) + '×' + fa(rec.h) + ' پیکسل (روی نمایشگر ' + fa(desktop[0]) + '×' + fa(desktop[1]) + ')']);
      lines.push(['حداقل قابل‌قبول', fa(min.w) + '×' + fa(min.h) + ' پیکسل']);
      lines.push(['نسبت پیشنهادی', 'حدود ' + fa(ratio.toFixed(2)) + ' به ۱ (' + (ratio >= 1 ? 'افقی' : 'عمودی') + ')']);
      lines.push(['نحوهٔ نمایش', fit === 'contain'
        ? 'کلِ تصویر دیده می‌شود؛ اگر نسبتش فرق کند کنارش رنگِ پس‌زمینه دیده می‌شود.'
        : 'تصویر کادر را کامل می‌پوشاند و اگر نسبتش فرق کند لبه‌ها بریده می‌شوند — «کانونِ تصویر» را روی سوژهٔ اصلی بگذارید.']);
      lines.push(['منطقهٔ امن', 'متن و دکمه در ' + vText + ' و ' + hText + ' کادر می‌نشینند؛ سوژهٔ مهمِ تصویر را از آن ناحیه دور نگه دارید.' +
        (headerMode === 'independent' ? '' : ' هدر روی بالای تصویر قرار می‌گیرد؛ حدود ۹۰ پیکسلِ بالا را از جزئیات مهم خالی بگذارید.')]);
      lines.push(['موبایل', mobileHidden
        ? 'در موبایل (حالتِ «فقط پنل اول») این پنل نمایش داده نمی‌شود.'
        : 'روی موبایل (' + fa(mobile[0]) + '×' + fa(mobile[1]) + ') این تصویر حدود ' + fa(mobile[0]) + '×' + fa(round10(mobilePanelH)) +
          ' نمایش داده می‌شود؛ تصویر بیشتر از دو طرف بریده می‌شود.']);
    }
    return { lines: lines, rec: rec, min: min, ratio: ratio, mobileRatio: mobile[0] / mobilePanelH, inactive: inactive, mobileHidden: mobileHidden };
  }

  function judge(guide, dims, bytes) {
    if (!dims) return { level: 'info', text: 'اندازهٔ این تصویر خوانده نشد؛ پس از ذخیره در پیش‌نمایش بررسی کنید.' };
    var warnings = [];
    if (guide && !guide.inactive) {
      if (dims.w < guide.min.w || dims.h < guide.min.h) {
        warnings.push('تصویر (' + fa(dims.w) + '×' + fa(dims.h) + ') از حداقلِ پیشنهادی (' + fa(guide.min.w) + '×' + fa(guide.min.h) +
          ') کوچک‌تر است؛ روی نمایشگرهای بزرگ ممکن است تار دیده شود.');
      }
      var imageRatio = dims.w / dims.h;
      var skew = imageRatio / guide.ratio;
      if (skew < 0.65 || skew > 1.55) {
        warnings.push('نسبتِ تصویر با کادرِ این قالب فرق دارد؛ بخش‌هایی از آن بریده می‌شود. کانونِ تصویر را تنظیم کنید یا تصویری با نسبتِ نزدیک‌تر بگذارید.');
      } else if (!guide.mobileHidden && imageRatio / guide.mobileRatio > 2.6) {
        warnings.push('این تصویر خیلی پهن است؛ روی موبایل فقط بخشِ میانیِ آن دیده می‌شود. سوژهٔ اصلی را وسط بگذارید.');
      }
    }
    if (bytes && bytes > 1.5 * 1024 * 1024) warnings.push('حجمِ فایل زیاد است (' + fa((bytes / 1048576).toFixed(1)) + ' مگابایت)؛ بارگذاریِ صفحه کند می‌شود. نسخهٔ فشرده‌تر پیشنهاد می‌شود.');
    if (warnings.length) return { level: 'warn', text: warnings.join(' ') };
    return { level: 'ok', text: guide && !guide.inactive ? 'اندازه و نسبتِ این تصویر برای این چیدمان مناسب است.' : 'تصویر انتخاب شد.' };
  }

  // ---- one picker -------------------------------------------------------------------------------------------------------------------
  function enhance(select) {
    if (select.__r4mp) return;
    select.__r4mp = true;
    // the inspector may move the control into its own card: the picker is created right next to the select, wherever that is
    var box = el('div', 'r4-mp is-enhanced');
    select.parentNode.insertBefore(box, select);
    box.appendChild(select);
    select.classList.add('r4-mp-native');
    var key = select.getAttribute('data-r4-field-key');
    var scope = select.closest('[data-r4-section-inspector]') || document;
    var uploadUrl = scope.getAttribute ? (scope.getAttribute('data-r4-media-upload-url') || '') : '';

    var current = el('div', 'r4-mp-current');
    var thumb = el('div', 'r4-mp-thumb');
    var meta = el('div', 'r4-mp-meta');
    var nameNode = el('strong', 'r4-mp-name');
    var dimsNode = el('small', 'r4-mp-dims');
    meta.appendChild(nameNode); meta.appendChild(dimsNode);
    current.appendChild(thumb); current.appendChild(meta);

    var actions = el('div', 'r4-mp-actions');
    var libraryBtn = el('button', 'r4-mp-btn', 'انتخاب از کتابخانه');
    libraryBtn.type = 'button'; libraryBtn.setAttribute('aria-expanded', 'false');
    var uploadLabel = el('label', 'r4-mp-btn r4-mp-upload', uploadUrl ? 'بارگذاریِ تصویر جدید' : 'بارگذاری از «رسانه‌ها»');
    var fileInput = document.createElement('input');
    fileInput.type = 'file'; fileInput.accept = 'image/jpeg,image/png,image/webp,image/gif'; fileInput.className = 'r4-mp-file';
    if (uploadUrl) uploadLabel.appendChild(fileInput);
    var removeBtn = el('button', 'r4-mp-btn r4-mp-remove', 'حذف تصویر');
    removeBtn.type = 'button';
    actions.appendChild(libraryBtn);
    if (uploadUrl) actions.appendChild(uploadLabel);
    actions.appendChild(removeBtn);

    var grid = el('div', 'r4-mp-grid'); grid.hidden = true;
    var status = el('p', 'r4-mp-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    var guideBox = el('div', 'r4-mp-guide');
    var warnBox = el('p', 'r4-mp-warn'); warnBox.setAttribute('role', 'status'); warnBox.setAttribute('aria-live', 'polite');

    box.appendChild(current); box.appendChild(actions); box.appendChild(grid); box.appendChild(status); box.appendChild(warnBox); box.appendChild(guideBox);

    var lastBytes = 0;

    function selectedOption() {
      var value = nativeValue.get.call(select);
      return value ? select.querySelector('option[value="' + value + '"]') : null;
    }

    function paintGuide() {
      var spec = guideSpec();
      var guide = spec ? computeGuide(spec, key, scope) : null;
      guideBox.textContent = '';
      if (!guide) {
        var generic = el('p', 'r4-mp-guide-line', 'پیشنهاد: تصویر افقی و باکیفیت با عرض حداقل ۱۲۰۰ پیکسل (JPG، PNG یا WebP؛ حداکثر ۵ مگابایت).');
        guideBox.appendChild(generic);
        return null;
      }
      var title = el('p', 'r4-mp-guide-title', 'راهنمای اندازهٔ همین جایگاه');
      guideBox.appendChild(title);
      var list = el('dl', 'r4-mp-guide-list');
      guide.lines.forEach(function (pair) {
        list.appendChild(el('dt', null, pair[0]));
        list.appendChild(el('dd', null, pair[1]));
      });
      guideBox.appendChild(list);
      return guide;
    }

    function render() {
      var option = selectedOption();
      var url = option ? option.getAttribute('data-url') : '';
      thumb.textContent = '';
      if (option) {
        var img = document.createElement('img');
        img.src = url; img.alt = ''; img.loading = 'lazy'; img.setAttribute('data-img-role', 'media-thumb');
        thumb.appendChild(img);
        nameNode.textContent = option.getAttribute('data-name') || option.textContent;
      } else {
        thumb.appendChild(el('span', 'r4-mp-empty', '—'));
        nameNode.textContent = 'بدون تصویر';
      }
      removeBtn.disabled = !option;
      dimsNode.textContent = '';
      warnBox.textContent = ''; warnBox.className = 'r4-mp-warn';
      var guide = paintGuide();
      if (option) {
        var wanted = url;
        readDims(url).then(function (dims) {
          if (selectedOption() !== option || option.getAttribute('data-url') !== wanted) return;
          dimsNode.textContent = dims ? fa(dims.w) + '×' + fa(dims.h) + ' پیکسل' : '';
          var verdict = judge(guide, dims, lastBytes);
          warnBox.textContent = verdict.text;
          warnBox.className = 'r4-mp-warn is-' + verdict.level;
        });
      }
      Array.prototype.forEach.call(grid.querySelectorAll('.r4-mp-tile'), function (tile) {
        tile.setAttribute('aria-pressed', tile.getAttribute('data-id') === nativeValue.get.call(select) ? 'true' : 'false');
      });
    }

    // a programmatic value (hydration, Undo/Redo, refresh) must repaint the picker too
    Object.defineProperty(select, 'value', {
      configurable: true,
      get: function () { return nativeValue.get.call(this); },
      set: function (next) { nativeValue.set.call(this, next); render(); }
    });
    select.addEventListener('change', render);

    function choose(id) {
      nativeValue.set.call(select, id);
      lastBytes = 0;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      render();
    }

    function buildGrid() {
      grid.textContent = '';
      Array.prototype.forEach.call(select.options, function (option) {
        if (!option.value) return;
        var tile = el('button', 'r4-mp-tile');
        tile.type = 'button'; tile.setAttribute('data-id', option.value);
        tile.setAttribute('aria-label', 'انتخاب ' + (option.getAttribute('data-name') || option.textContent));
        var img = document.createElement('img');
        img.src = option.getAttribute('data-url'); img.alt = ''; img.loading = 'lazy'; img.setAttribute('data-img-role', 'media-thumb');
        tile.appendChild(img);
        tile.appendChild(el('span', 'r4-mp-tile-name', option.getAttribute('data-name') || option.textContent));
        tile.addEventListener('click', function () { choose(option.value); grid.hidden = true; libraryBtn.setAttribute('aria-expanded', 'false'); });
        grid.appendChild(tile);
      });
      if (!grid.children.length) grid.appendChild(el('p', 'r4-mp-grid-empty', 'هنوز تصویری در کتابخانه نیست — یک تصویر بارگذاری کنید.'));
    }

    libraryBtn.addEventListener('click', function () {
      var open = grid.hidden;
      if (open) buildGrid();
      grid.hidden = !open;
      libraryBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      render();
    });
    removeBtn.addEventListener('click', function () { choose(''); status.textContent = 'تصویر برداشته شد؛ از «بازگرداندن» می‌توانید برش گردانید.'; });

    fileInput.addEventListener('change', function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      status.textContent = 'در حال بارگذاری «' + file.name + '»…'; status.className = 'r4-mp-status';
      var form = new FormData();
      form.append('image', file);
      fetch(uploadUrl, { method: 'POST', body: form, credentials: 'same-origin', headers: { 'X-CSRFToken': getCookie('csrftoken') } })
        .then(function (response) { return response.json().then(function (data) { return { ok: response.ok && data && data.ok, data: data || {} }; }, function () { return { ok: false, data: {} }; }); })
        .then(function (result) {
          fileInput.value = '';
          if (!result.ok) {
            status.textContent = result.data.message || 'بارگذاری انجام نشد؛ فایل را بررسی کنید.';
            status.className = 'r4-mp-status is-error';
            return;
          }
          var option = document.createElement('option');
          option.value = String(result.data.id);
          option.setAttribute('data-url', result.data.url);
          option.setAttribute('data-name', result.data.name);
          option.textContent = result.data.name;
          select.insertBefore(option, select.options[1] || null);
          // the new picture is visible to every picker of this Inspector (each owns its own <select>)
          Array.prototype.forEach.call(scope.querySelectorAll('select[data-r4-field-type="media"]'), function (other) {
            if (other === select || other.querySelector('option[value="' + result.data.id + '"]')) return;
            var clone = option.cloneNode(true);
            other.insertBefore(clone, other.options[1] || null);
          });
          lastBytes = file.size;
          choose(String(result.data.id));
          status.textContent = '«' + result.data.name + '» بارگذاری و انتخاب شد.'; status.className = 'r4-mp-status is-ok';
        })
        .catch(function () {
          fileInput.value = '';
          status.textContent = 'ارتباط با سرور برقرار نشد؛ بارگذاری انجام نشد.'; status.className = 'r4-mp-status is-error';
        });
    });

    // the guide depends on the stage's own composition: repaint when one of those settings changes (see the document-level listener below)
    select.__r4mpRender = render;
    render();
  }

  // ONE capture-phase listener for every picker: a change of any field of the same Inspector may alter the guide (layout, split, height…)
  function repaintSiblings(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var scope = target.closest('[data-r4-section-inspector]');
    if (!scope || !target.getAttribute('data-r4-field-key')) return;
    Array.prototype.forEach.call(scope.querySelectorAll('select[data-r4-media-picker]'), function (picker) {
      if (picker !== target && picker.__r4mpRender) picker.__r4mpRender();
    });
  }
  document.addEventListener('change', repaintSiblings, true);
  document.addEventListener('input', repaintSiblings, true);

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches && root.matches('select[data-r4-media-picker]')) enhance(root);
    Array.prototype.forEach.call(root.querySelectorAll('select[data-r4-media-picker]'), enhance);
  }

  function start() {
    scan(document);
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        Array.prototype.forEach.call(record.addedNodes, function (node) { if (node.nodeType === 1) scan(node); });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
}());
