/* R4-14 — راهنمای هوشمند آپلود تصویر: پس از انتخابِ فایل (و پیش از ذخیره) نوعِ واقعی، حجم، ابعاد و نسبتِ تصویر را می‌سنجد،
 * هشدارِ قابل‌فهم می‌دهد و پیش‌نمایشِ «نمایش کامل» / «پر کردن قاب» (با کانون و بزرگ‌نمایی) را در قاب‌های واقعیِ قالبِ فروشگاه نشان می‌دهد.
 * فقط سمتِ مرورگر و غیرمخرب است: فایلِ کاربر خوانده می‌شود، تغییر نمی‌کند و به سرور فرستاده نمی‌شود مگر با «ذخیره».
 * اعتبارسنجیِ واقعی همچنان در سرور انجام می‌شود (apps/core/image_validation.py)؛ این‌جا فقط همان حدها پیشاپیش گفته می‌شود. */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(n) { return String(n).replace(/[0-9]/g, function (d) { return FA[+d]; }); }
  function num(v, d) { var t = Number(v).toFixed(d === undefined ? 0 : d); if (t.indexOf('.') !== -1) t = t.replace(/0+$/, '').replace(/\.$/, ''); return fa(t).replace('.', '٫'); }
  function mb(bytes) { var t = (bytes / 1048576).toFixed(bytes < 1048576 ? 2 : 1); if (t.indexOf('.') !== -1) t = t.replace(/0+$/, '').replace(/\.$/, ''); return fa(t).replace('.', '٫'); }
  var FORMAT_LABEL = { JPEG: 'JPG', PNG: 'PNG', WEBP: 'WebP', GIF: 'GIF', BMP: 'BMP', TIFF: 'TIFF', ICO: 'ICO', SVG: 'SVG', HEIC: 'HEIC', AVIF: 'AVIF' };
  var POSITIONS = { center: 'وسط', top: 'بالا', bottom: 'پایین', left: 'چپ', right: 'راست' };
  var POS_CSS = { center: 'center', top: 'center top', bottom: 'center bottom', left: 'left center', right: 'right center' };
  var ZOOMS = [1, 1.1, 1.25, 1.5, 1.75];
  /* «W×H» — or only the width when the placement leaves the height free (the picture keeps its own ratio) */
  function dim(a) { return a[1] ? fa(a[0]) + '×' + fa(a[1]) : 'عرض ' + fa(a[0]); }

  /* نوعِ واقعیِ فایل از بایت‌های ابتدایی (نه از پسوند) — همان چیزی که Pillow در سرور تشخیص می‌دهد */
  function detectFormat(b) {
    function at(i, s) { for (var k = 0; k < s.length; k++) if (b[i + k] !== s.charCodeAt(k)) return false; return true; }
    if (b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF) return 'JPEG';
    if (b[0] === 0x89 && at(1, 'PNG')) return 'PNG';
    if (at(0, 'RIFF') && at(8, 'WEBP')) return 'WEBP';
    if (at(0, 'GIF8')) return 'GIF';
    if (at(0, 'BM')) return 'BMP';
    if ((b[0] === 0x49 && b[1] === 0x49 && b[2] === 0x2A) || (b[0] === 0x4D && b[1] === 0x4D && b[3] === 0x2A)) return 'TIFF';
    if (b[0] === 0 && b[1] === 0 && b[2] === 1 && b[3] === 0) return 'ICO';
    if (at(4, 'ftypavif') || at(4, 'ftypavis')) return 'AVIF';
    if (at(4, 'ftypheic') || at(4, 'ftypheix') || at(4, 'ftypmif1')) return 'HEIC';
    var head = ''; for (var i = 0; i < Math.min(b.length, 64); i++) head += String.fromCharCode(b[i]);
    if (/^\s*(<\?xml|<svg)/i.test(head)) return 'SVG';
    return null;
  }
  function readBytes(blob) {
    return new Promise(function (resolve) {
      var r = new FileReader();
      r.onload = function () { resolve(new Uint8Array(r.result)); };
      r.onerror = function () { resolve(new Uint8Array(0)); };
      r.readAsArrayBuffer(blob);
    });
  }
  function readHead(file) { return readBytes(file.slice(0, 32)); }
  /* فایلِ نیمه‌کاره (قطع‌شده در آپلود/دانلود) را از انتهای ساختارِ فرمت می‌شناسیم؛ مرورگر همان تصویر را ناقص نشان می‌دهد */
  function looksTruncated(format, head, tail, size) {
    if (format === 'JPEG') { for (var i = tail.length - 1; i > 0 && i > tail.length - 8; i--) if (tail[i - 1] === 0xFF && tail[i] === 0xD9) return false; return true; }
    if (format === 'PNG') { var t = ''; for (var k = 0; k < tail.length; k++) t += String.fromCharCode(tail[k]); return t.indexOf('IEND') === -1; }
    if (format === 'WEBP') { var riff = head[4] | (head[5] << 8) | (head[6] << 16) | (head[7] << 24); return riff + 8 > size; }
    return false;
  }
  function analyze(file) {
    return Promise.all([readHead(file), readBytes(file.slice(Math.max(0, file.size - 16)))]).then(function (parts) {
      var head = parts[0];
      return new Promise(function (resolve) {
        var info = { file: file, name: file.name, size: file.size, format: detectFormat(head), ext: ('.' + (file.name.split('.').pop() || '')).toLowerCase(), url: URL.createObjectURL(file) };
        info.truncated = info.format ? looksTruncated(info.format, head, parts[1], file.size) : false;
        var img = new Image();
        img.onload = function () { info.w = img.naturalWidth; info.h = img.naturalHeight; info.ok = true; resolve(info); };
        img.onerror = function () { info.ok = false; resolve(info); };
        img.src = info.url;
      });
    });
  }

  /* ----------------------------------------------------------------------------------------------- سنجش */
  function crop(iw, ih, fw, fh, fit, zoom) {
    var s = (fit === 'cover' ? Math.max(fw / iw, fh / ih) : Math.min(fw / iw, fh / ih)) * zoom;
    var vw = Math.min(1, fw / (iw * s)), vh = Math.min(1, fh / (ih * s));
    var drawn = Math.min(1, (iw * s) / fw) * Math.min(1, (ih * s) / fh); // سهمِ قاب که عکس می‌پوشاند
    return { cropped: Math.max(0, 1 - vw * vh), empty: Math.max(0, 1 - drawn) };
  }
  function verdict(spec, info) {
    var errors = [], warns = [], oks = [], infos = [];
    if (!info.ok) { errors.push('این فایل به‌عنوان تصویر خوانده نشد؛ فایل خراب است یا نوعِ آن پشتیبانی نمی‌شود. تصویر JPG، PNG یا WebP بگذارید.'); return { errors: errors, warns: warns, oks: oks, infos: infos }; }
    var label = FORMAT_LABEL[info.format] || '';
    if (!info.format || spec.pil.indexOf(info.format) === -1) {
      errors.push('فرمتِ واقعیِ فایل' + (label ? ' «' + label + '»' : '') + ' است و این جایگاه فقط ' + spec.formats.join('، ') + ' می‌پذیرد؛ فایل را با یکی از این فرمت‌ها ذخیره کنید، وگرنه ذخیره نمی‌شود.');
    } else if (spec.exts && spec.exts.indexOf(info.ext) === -1) {
      errors.push('پسوندِ فایل («' + info.ext.replace('.', '') + '») مجاز نیست؛ پسوندِ ' + spec.exts.join('، ').replace(/\./g, '') + ' لازم است.');
    }
    if (info.size > spec.maxBytes) {
      var m = 'حجمِ فایل ' + mb(info.size) + ' مگابایت است و از ' + mb(spec.maxBytes) + ' مگابایت بیشتر است';
      (spec.maxEnforced ? errors : warns).push(m + (spec.maxEnforced ? '؛ ذخیره نمی‌شود. تصویر را فشرده‌تر یا کوچک‌تر ذخیره کنید.' : ' (سایت کندتر می‌شود).'));
    }
    if (info.truncated) errors.push('فایل ناقص یا خراب است (پایانِ فایل نیامده)؛ ذخیره نمی‌شود. دوباره از منبع بگیرید یا خروجی بگیرید.');
    var px = info.w * info.h;
    infos.push('ابعاد: ' + fa(info.w) + '×' + fa(info.h) + ' پیکسل (' + fa((px / 1e6).toFixed(1)) + ' مگاپیکسل)');
    if (px > spec.maxPixels) errors.push('ابعاد تصویر بیش از حد بزرگ است (بیش از ' + fa(Math.round(spec.maxPixels / 1e6)) + ' مگاپیکسل)؛ ذخیره نمی‌شود.');
    if (info.w < spec.min[0] || (spec.min[1] && info.h < spec.min[1])) {
      warns.push('وضوح کمتر از حداقلِ ' + dim(spec.min) + ' است؛ در فروشگاه کدر یا پیکسلی دیده می‌شود. بزرگ‌ترش نکنید؛ تصویرِ اصلیِ بزرگ‌تر بگیرید.');
    } else if (info.w < spec.rec[0] * 0.6) {
      warns.push('برای صفحه‌های پرتراکم (رتینا) تصویرِ بزرگ‌تر، نزدیک به ' + dim(spec.rec) + '، شفاف‌تر دیده می‌شود.');
    }
    var r = info.w / info.h;
    if (r > 4 || r < 0.25) warns.push('نسبتِ تصویر (' + num(r, 2) + ' به ۱) بسیار کشیده است و در بیشتر قاب‌ها بخش بزرگی از آن دیده نمی‌شود.');
    if ((info.format === 'JPEG' || info.format === 'WEBP') && px > 150000 && info.size / px < 0.035) {
      warns.push('تصویر بسیار فشرده شده است و ممکن است لکه‌دار یا بلوکی دیده شود؛ نسخه‌ای با کیفیتِ بالاتر بدهید.');
    }
    (spec.frames || []).forEach(function (f) {
      if (f.shape === 'circle' || f.free) return;   // a free-height placement keeps the picture's own ratio: nothing is cropped or left empty
      var c = crop(info.w, info.h, f.ratio, 1, f.fit, f.zoom || 1);
      var name = '«' + f.label + '»' + (f.approx ? ' (تقریبی)' : '');
      if (f.fit === 'cover' && c.cropped > 0.12) warns.push('در قابِ ' + name + ' حدود ' + fa(Math.round(c.cropped * 100)) + '٪ از تصویر بریده می‌شود؛ سوژه را وسطِ عکس نگه دارید یا نسبتِ عکس را به ' + num(f.ratio, 2) + ' نزدیک کنید.');
      if (f.fit === 'contain' && c.empty > 0.25) infos.push('در قابِ ' + name + ' حدود ' + fa(Math.round(c.empty * 100)) + '٪ قاب خالی می‌ماند (کلِ تصویر دیده می‌شود)؛ «پر کردن قاب» یا نسبتِ نزدیک‌تر این را کم می‌کند.');
    });
    if (!errors.length && !warns.length) oks.push('تصویر برای این جایگاه مناسب است.');
    if (spec.key === 'product_image' && (info.w > 2000 || info.h > 2000)) infos.push('تصویر بزرگ‌تر از ۲۰۰۰ پیکسل است؛ برای نمایش یک نسخهٔ ۲۰۰۰px ساخته می‌شود و فایلِ اصلیِ شما هم بدونِ تغییر نگه داشته می‌شود.');
    return { errors: errors, warns: warns, oks: oks, infos: infos };
  }

  /* ----------------------------------------------------------------------------------------------- رابط */
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function listOf(cls, items) { return items.map(function (t) { return el('p', cls, t); }); }

  function renderPreview(host, spec, info) {
    var frames = spec.frames && spec.frames.length ? spec.frames : [{ label: 'کادرِ پیشنهادی', ratio: spec.ratio[0] / spec.ratio[1], fit: spec.contain ? 'contain' : 'cover', pos: 'center', zoom: 1, shape: spec.key === 'story_item' ? 'circle' : 'rect', approx: false, used_by: [] }];
    var state = { fit: '', pos: '', zoom: 0 }; // مقدارِ خالی = تنظیمِ فعلیِ همان قاب
    var box = el('div', 'imgguide-preview');
    box.appendChild(el('h4', 'imgguide-h', 'پیش‌نمایش در فروشگاه شما (پیش از ذخیره)'));
    var ctl = el('div', 'imgguide-controls');
    var groups = [];
    function group(title, items, key, parse) {
      var g = el('div', 'imgguide-group'); g.appendChild(el('span', 'imgguide-gl', title));
      var wrap = el('div', 'imgguide-seg'); wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-label', title);
      items.forEach(function (it) {
        var b = el('button', 'imgguide-seg-btn', it.t); b.type = 'button'; b.setAttribute('data-val', String(it.v)); b.setAttribute('data-key', key);
        b.addEventListener('click', function () { state[key] = parse ? parse(it.v) : it.v; paint(); });
        wrap.appendChild(b);
      });
      g.appendChild(wrap); ctl.appendChild(g); groups.push(wrap);
    }
    group('نحوهٔ جاگیری', [{ t: 'تنظیمِ فعلی', v: '' }, { t: 'نمایش کامل', v: 'contain' }, { t: 'پر کردن قاب', v: 'cover' }], 'fit');
    group('کانونِ تصویر', [{ t: 'فعلی', v: '' }].concat(Object.keys(POSITIONS).map(function (k) { return { t: POSITIONS[k], v: k }; })), 'pos');
    group('بزرگ‌نمایی', [{ t: 'فعلی', v: 0 }].concat(ZOOMS.map(function (z) { return { t: fa(Math.round(z * 100)) + '٪', v: z }; })), 'zoom', Number);
    box.appendChild(ctl);
    var grid = el('div', 'imgguide-tiles');
    box.appendChild(grid);
    box.appendChild(el('p', 'imgguide-note', 'این فقط پیش‌نمایش است و فایل شما تغییری نمی‌کند. برای اعمال دائمی، «نحوهٔ جاگیری»، «کانون» و «بزرگ‌نمایی» را در استودیوی طراحی ← تصاویرِ همان بخش انتخاب کنید.'));

    var tiles = frames.map(function (f) {
      var tile = el('figure', 'imgguide-tile');
      var frame = el('div', 'imgguide-frame' + (f.shape === 'circle' ? ' is-circle' : ''));
      frame.style.aspectRatio = String(f.free ? info.w / info.h : f.ratio);
      frame.style.width = f.ratio >= 2 ? '100%' : (f.ratio >= 1.2 ? 'min(100%,260px)' : 'min(100%,200px)');
      var img = el('img'); img.src = info.url; img.alt = 'پیش‌نمایشِ ' + f.label; img.decoding = 'async';
      frame.appendChild(img);
      var cap = el('figcaption', 'imgguide-cap');
      var stat = el('span', 'imgguide-stat'), cur = el('span', 'imgguide-cur');
      cap.appendChild(el('strong', '', f.label + ' · ' + (f.free ? 'ارتفاع آزاد' : num(f.ratio, 2) + ':۱' + (f.approx ? ' (تقریبی)' : ''))));
      cap.appendChild(stat); cap.appendChild(cur);
      if (f.used_by && f.used_by.length) cap.appendChild(el('span', 'imgguide-used', 'بخش‌ها: ' + f.used_by.join('، ')));
      if (f.note) cap.appendChild(el('span', 'imgguide-used', f.note));
      tile.appendChild(frame); tile.appendChild(cap); grid.appendChild(tile);
      return { f: f, img: img, stat: stat, cur: cur };
    });

    function paint() {
      groups.forEach(function (g) {
        Array.prototype.forEach.call(g.children, function (b) {
          var key = b.getAttribute('data-key'), v = b.getAttribute('data-val'), cur = state[key];
          b.setAttribute('aria-pressed', String(String(cur) === v));
        });
      });
      tiles.forEach(function (t) {
        var fit = state.fit || t.f.fit, pos = state.pos || t.f.pos || 'center', zoom = state.zoom || t.f.zoom || 1;
        t.img.style.objectFit = fit; t.img.style.objectPosition = POS_CSS[pos] || 'center';
        t.img.style.transform = zoom !== 1 ? 'scale(' + zoom + ')' : ''; t.img.style.transformOrigin = POS_CSS[pos] || 'center';
        var c = crop(info.w, info.h, t.f.free ? info.w / info.h : t.f.ratio, 1, fit, zoom), parts = [];
        parts.push(t.f.free ? 'نسبتِ طبیعیِ تصویر' : (fit === 'cover' ? 'پر کردن قاب' : 'نمایش کامل'));
        parts.push(c.cropped > 0.005 ? 'حدود ' + fa(Math.round(c.cropped * 100)) + '٪ از تصویر بریده می‌شود' : 'تمامِ تصویر دیده می‌شود');
        if (fit === 'contain' && c.empty > 0.05) parts.push('حدود ' + fa(Math.round(c.empty * 100)) + '٪ قاب خالی می‌ماند');
        if (t.f.shape === 'circle') parts.push('گوشه‌ها در دایره دیده نمی‌شوند');
        t.stat.textContent = parts.join(' — ');
        t.cur.textContent = 'تنظیمِ فعلیِ این قاب: ' + (t.f.fit === 'cover' ? 'پر کردن قاب' : 'نمایش کامل') + (t.f.zoom && t.f.zoom !== 1 ? '، بزرگ‌نمایی ' + fa(Math.round(t.f.zoom * 100)) + '٪' : '') + (t.f.pos && t.f.pos !== 'center' ? '، کانون ' + POSITIONS[t.f.pos] : '');
      });
    }
    paint();
    host.appendChild(box);
  }

  function showFile(guide, spec, info) {
    var live = guide.querySelector('.imgguide-live');
    Array.prototype.slice.call(live.querySelectorAll('.imgguide-detail')).forEach(function (n) { n.remove(); });
    var detail = el('div', 'imgguide-detail');
    var v = verdict(spec, info);
    detail.appendChild(el('p', 'imgguide-file', info.name + ' — ' + (FORMAT_LABEL[info.format] || 'نامشخص') + ' — ' + mb(info.size) + ' مگابایت'));
    listOf('imgguide-bad', v.errors).concat(listOf('imgguide-warn', v.warns), listOf('imgguide-ok', v.oks), listOf('imgguide-info', v.infos)).forEach(function (n) { detail.appendChild(n); });
    live.appendChild(detail);
    guide.setAttribute('data-state', v.errors.length ? 'error' : (v.warns.length ? 'warn' : 'ok'));
    if (info.ok && !v.errors.length) renderPreview(detail, spec, info); // a file the server would refuse gets no «preview» that suggests it could be shown
  }

  function setSpec(guide, open) {
    var t = guide.querySelector('.imgguide-toggle'), body = guide.querySelector('.imgguide-spec-body');
    if (!t || !body) return;
    t.setAttribute('aria-expanded', String(open)); body.hidden = !open;
  }
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.imgguide-toggle') : null;
    if (t) setSpec(t.closest('[data-image-guide]'), t.getAttribute('aria-expanded') !== 'true');
  });

  function handle(guide, input) {
    var spec; try { spec = JSON.parse(guide.getAttribute('data-spec')); } catch (e) { return; }
    var live = guide.querySelector('.imgguide-live');
    (guide._urls || []).forEach(function (u) { try { URL.revokeObjectURL(u); } catch (e) { /* noop */ } });
    guide._urls = [];
    while (live.firstChild) live.removeChild(live.firstChild);
    guide.removeAttribute('data-state');
    setSpec(guide, !(input.files && input.files.length));
    var seq = guide._seq = (guide._seq || 0) + 1; // every selection supersedes the previous one
    var files = input.files ? Array.prototype.slice.call(input.files) : [];
    if (!files.length) return;
    Promise.all(files.slice(0, 12).map(analyze)).then(function (infos) {
      if (guide._seq !== seq) { infos.forEach(function (i) { try { URL.revokeObjectURL(i.url); } catch (e) { /* noop */ } }); return; } // a newer choice already replaced this one
      infos.forEach(function (i) { guide._urls.push(i.url); });
      if (files.length > 1) {
        var summary = el('div', 'imgguide-files'); summary.setAttribute('role', 'group'); summary.setAttribute('aria-label', 'تصاویر انتخاب‌شده');
        var bad = 0, warn = 0;
        infos.forEach(function (info, idx) {
          var v = verdict(spec, info); bad += v.errors.length ? 1 : 0; warn += (!v.errors.length && v.warns.length) ? 1 : 0;
          var b = el('button', 'imgguide-chip imgguide-chip--' + (v.errors.length ? 'bad' : (v.warns.length ? 'warn' : 'ok')), fa(idx + 1) + '. ' + info.name);
          b.type = 'button'; b.title = v.errors.concat(v.warns).join(' | ') || 'مناسب';
          b.addEventListener('click', function () { showFile(guide, spec, info); });
          summary.appendChild(b);
        });
        live.appendChild(el('p', 'imgguide-info', fa(files.length) + ' تصویر انتخاب شد: ' + fa(files.length - bad - warn) + ' مناسب، ' + fa(warn) + ' با هشدار، ' + fa(bad) + ' نامعتبر. برای دیدنِ پیش‌نمایشِ هر تصویر روی نامش بزنید.'));
        live.appendChild(summary);
      }
      showFile(guide, spec, infos[0]);
      if (guide.getAttribute('data-confirm-event')) addActions(guide, spec, input, infos);
      else if (infos.some(function (i) { return verdict(spec, i).errors.length > 0; })) {
        // a plain form posts whatever the input holds: an invalid file is dropped from the input so it can never be sent
        // (the form still saves its other fields; the picture already stored is untouched)
        input.value = '';
        var live2 = guide.querySelector('.imgguide-live');
        live2.insertBefore(el('p', 'imgguide-bad imgguide-blocked', 'این فایل ارسال نمی‌شود و تصویرِ فعلی تغییری نمی‌کند. تصویر معتبر دیگری انتخاب کنید.'), live2.firstChild);
      }
    });
  }

  /* فرمِ آپلودِ فوریِ کالا (htmx): ارسال تا «ذخیره» به تعویق می‌افتد و فقط تصویرهای معتبر فرستاده می‌شود؛ فایل‌های نامعتبر هرگز ارسال نمی‌شوند. */
  function resetGuide(guide) {
    var live = guide.querySelector('.imgguide-live');
    (guide._urls || []).forEach(function (u) { try { URL.revokeObjectURL(u); } catch (e) { /* noop */ } });
    guide._urls = [];
    while (live.firstChild) live.removeChild(live.firstChild);
    guide.removeAttribute('data-state');
    setSpec(guide, true);
  }
  function addActions(guide, spec, input, infos) {
    var live = guide.querySelector('.imgguide-live');
    var good = infos.filter(function (i) { return verdict(spec, i).errors.length === 0; });
    var bad = infos.length - good.length;
    var bar = el('div', 'imgguide-actions');
    var msg = el('p', good.length ? 'imgguide-info' : 'imgguide-bad',
      good.length ? (bad ? fa(bad) + ' تصویرِ نامعتبر ارسال نمی‌شود؛ ' : '') + fa(good.length) + ' تصویر آمادهٔ ذخیره است. تا «ذخیره» نزنید چیزی ارسال نمی‌شود.' : 'هیچ‌کدام از تصاویر انتخاب‌شده قابل ذخیره نیست؛ تصویرِ دیگری انتخاب کنید.');
    var save = el('button', 'btn btn-primary btn-sm', 'ذخیرهٔ ' + fa(good.length) + ' تصویر'); save.type = 'button'; save.disabled = !good.length;
    var cancel = el('button', 'btn btn-ghost btn-sm', 'انصراف'); cancel.type = 'button';
    save.addEventListener('click', function () {
      var dt = new DataTransfer(); good.forEach(function (i) { dt.items.add(i.file); });
      input.files = dt.files; save.disabled = true;
      input.dispatchEvent(new CustomEvent(guide.getAttribute('data-confirm-event'), { bubbles: true }));
    });
    cancel.addEventListener('click', function () { input.value = ''; resetGuide(guide); });
    bar.appendChild(msg); bar.appendChild(save); bar.appendChild(cancel);
    live.appendChild(bar);
  }
  document.addEventListener('htmx:afterRequest', function (e) {
    var scope = (e.target && e.target.closest && (e.target.closest('form') || document)) || document;
    Array.prototype.forEach.call(scope.querySelectorAll('[data-image-guide][data-confirm-event]'), function (g) { resetGuide(g); });
  });

  document.addEventListener('change', function (e) {
    var input = e.target;
    if (!input || input.tagName !== 'INPUT' || input.type !== 'file') return;
    var scope = input.closest('form') || document;
    Array.prototype.forEach.call(scope.querySelectorAll('[data-image-guide]'), function (g) {
      var name = g.getAttribute('data-input-name') || '';
      if (!name || name === input.name) handle(g, input);
    });
  }, true);
})();
