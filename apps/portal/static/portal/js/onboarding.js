/* RastiSi onboarding journey — progressive enhancement only.
 * Every flow still works without this file: radios submit, forms post, skip posts.
 * Server-side checks (offerable template, one-time install, permissions) are the
 * source of truth; nothing here is a security control.
 */
(function () {
  'use strict';

  function norm(value) {
    return (value || '').toString().toLowerCase()
      .replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/‌/g, ' ').trim();
  }

  /* ── Industry selector ───────────────────────────────────────────────── */
  function initIndustry(root) {
    var cards = Array.prototype.slice.call(root.querySelectorAll('[data-ob-card]'));
    var panels = Array.prototype.slice.call(root.querySelectorAll('[data-ob-panel]'));
    var emptyPreview = root.querySelector('[data-ob-preview-empty]');
    var noResults = root.querySelector('[data-ob-no-results]');
    var search = root.querySelector('[data-ob-search]');
    var chips = Array.prototype.slice.call(root.querySelectorAll('[data-ob-sector]'));
    var confirmBox = root.querySelector('[data-ob-confirm-check]');
    var confirmName = root.querySelector('[data-ob-selected-name]');
    var submit = document.querySelector('[data-ob-install-submit]');
    var status = root.querySelector('[data-ob-selection-status]');
    var sector = 'all';

    function selectedRadio() {
      var checked = root.querySelector('input[name="industry_template_id"]:checked');
      return checked || null;
    }

    function refreshSubmit() {
      if (!submit) return;
      var ready = !!selectedRadio() && (!confirmBox || confirmBox.checked);
      submit.disabled = !ready;
      submit.setAttribute('aria-disabled', ready ? 'false' : 'true');
    }

    function showSelection(scroll) {
      var radio = selectedRadio();
      var id = radio ? radio.value : '';
      cards.forEach(function (card) {
        card.classList.toggle('is-selected', !!radio && card.getAttribute('data-id') === id);
      });
      var anyPanel = false;
      panels.forEach(function (panel) {
        var match = panel.getAttribute('data-ob-panel') === id;
        panel.hidden = !match;
        if (match) anyPanel = true;
      });
      if (emptyPreview) emptyPreview.hidden = anyPanel;
      var card = radio && radio.closest('[data-ob-card]');
      if (confirmName) confirmName.textContent = card ? card.getAttribute('data-name') : '—';
      if (status) status.textContent = card ? ('صنف «' + card.getAttribute('data-name') + '» انتخاب شد.') : '';
      if (scroll && radio && window.matchMedia && window.matchMedia('(max-width: 960px)').matches) {
        var preview = root.querySelector('[data-ob-preview]');
        if (preview && preview.scrollIntoView) preview.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
      refreshSubmit();
    }

    function applyFilter() {
      var query = norm(search && search.value);
      var visible = 0;
      cards.forEach(function (card) {
        var okSector = sector === 'all' || card.getAttribute('data-sector') === sector;
        var haystack = norm(card.getAttribute('data-name') + ' ' + card.getAttribute('data-sector-label'));
        var show = okSector && (!query || haystack.indexOf(query) !== -1);
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (noResults) noResults.hidden = visible !== 0;
    }

    cards.forEach(function (card) {
      var radio = card.querySelector('input[type="radio"]');
      if (radio) radio.addEventListener('change', function () { showSelection(true); });
    });
    if (search) search.addEventListener('input', applyFilter);
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        sector = chip.getAttribute('data-ob-sector');
        chips.forEach(function (c) { c.setAttribute('aria-pressed', c === chip ? 'true' : 'false'); });
        applyFilter();
      });
    });
    if (confirmBox) confirmBox.addEventListener('change', refreshSubmit);

    showSelection(false);
    applyFilter();
  }

  /* ── Double-submit guard ─────────────────────────────────────────────── */
  function initOnce(form) {
    var submitted = false;
    form.addEventListener('submit', function (event) {
      if (submitted) { event.preventDefault(); return; }
      submitted = true;
      var buttons = Array.prototype.slice.call(form.querySelectorAll('button[type="submit"]'));
      if (form.id) {
        buttons = buttons.concat(Array.prototype.slice.call(document.querySelectorAll('button[form="' + form.id + '"]')));
      }
      // Disable on the next tick so the clicked button's own name/value still posts.
      window.setTimeout(function () {
        buttons.forEach(function (button) {
          button.setAttribute('aria-disabled', 'true');
          button.disabled = true;
          var text = button.getAttribute('data-loading-text');
          if (text) button.textContent = text;
        });
      }, 0);
    });
    // Back/forward cache: a restored page must be usable again.
    window.addEventListener('pageshow', function (event) {
      if (event.persisted) {
        submitted = false;
        document.querySelectorAll('button[aria-disabled="true"][data-loading-text]').forEach(function (b) { b.disabled = false; b.removeAttribute('aria-disabled'); });
      }
    });
  }

  /* ── Logo preview ────────────────────────────────────────────────────── */
  function initLogo(input) {
    var preview = document.querySelector('[data-ob-logo-preview]');
    var note = document.querySelector('[data-ob-logo-note]');
    var warnBytes = 2 * 1024 * 1024;
    if (!preview) return;
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (note) note.textContent = '';
      if (!file) return;
      if (file.type && file.type.indexOf('image/') !== 0) {
        if (note) note.textContent = 'این فایل تصویر نیست؛ لطفاً یک تصویر PNG، JPG یا WebP انتخاب کنید.';
        return;
      }
      var stale = document.querySelector('[data-ob-error-summary]');
      if (stale) stale.hidden = true;
      var boxText = document.querySelector('[data-ob-logo-text]');
      if (boxText) boxText.textContent = 'فایلِ انتخاب‌شده: ' + file.name + ' — با «ذخیره و ادامه» ذخیره می‌شود.';
      var url = URL.createObjectURL(file);
      var img = document.createElement('img');
      img.alt = 'پیش‌نمایش لوگو';
      img.onload = function () { URL.revokeObjectURL(url); };
      img.src = url;
      preview.textContent = '';
      preview.appendChild(img);
      if (note) {
        var mb = (file.size / (1024 * 1024)).toFixed(1);
        note.textContent = file.size > warnBytes
          ? ('حجم فایل حدود ' + mb + ' مگابایت است؛ تصویر سنگین ممکن است ویترین را کند کند — اگر می‌توانید فایل سبک‌تری انتخاب کنید.')
          : 'پیش‌نمایش لوگو بالا نشان داده شد؛ با «ادامه» ذخیره می‌شود.';
      }
    });
  }

  /* ── Ready Template gallery ─────────────────────────────────────────── */
  function initTemplates(form) {
    var cards = Array.prototype.slice.call(form.querySelectorAll('[data-ob-tpl-card]'));
    var search = form.querySelector('[data-ob-tpl-search]');
    var visibleCount = form.querySelector('[data-ob-tpl-visible]');
    var empty = form.querySelector('[data-ob-tpl-empty]');
    var status = form.querySelector('[data-ob-tpl-status]');
    var submit = document.querySelector('[data-ob-template-submit]');
    var dialog = document.querySelector('[data-ob-lightbox]');

    // Palette swatch colours come from the canonical registry; applied via CSSOM (no inline style attribute in HTML).
    form.querySelectorAll('.ob-swatch[data-color]').forEach(function (el) {
      el.style.backgroundColor = el.getAttribute('data-color');
    });

    function refresh() {
      var checked = form.querySelector('input[name="template_key"]:checked');
      cards.forEach(function (card) {
        var input = card.querySelector('input[type="radio"]');
        card.classList.toggle('is-selected', !!input && input.checked);
      });
      if (submit) {
        submit.disabled = !checked;
        submit.setAttribute('aria-disabled', checked ? 'false' : 'true');
      }
      if (status) {
        var card = checked && checked.closest('[data-ob-tpl-card]');
        status.textContent = card ? ('قالبِ «' + card.getAttribute('data-name') + '» انتخاب شد.') : '';
      }
    }

    function filter() {
      var query = norm(search && search.value);
      var shown = 0;
      cards.forEach(function (card) {
        var match = !query || norm(card.getAttribute('data-name')).indexOf(query) !== -1;
        card.hidden = !match;
        if (match) shown += 1;
      });
      if (visibleCount) visibleCount.textContent = shown;
      if (empty) empty.hidden = shown !== 0;
    }

    cards.forEach(function (card) {
      var input = card.querySelector('input[type="radio"]');
      if (input) input.addEventListener('change', refresh);
    });
    if (search) search.addEventListener('input', filter);

    if (dialog && typeof dialog.showModal === 'function') {
      var img = dialog.querySelector('[data-ob-lightbox-img]');
      var title = dialog.querySelector('[data-ob-lightbox-title]');
      form.querySelectorAll('[data-ob-zoom]').forEach(function (link) {
        link.addEventListener('click', function (event) {
          event.preventDefault();
          img.src = link.getAttribute('href');
          img.alt = 'پیش‌نمایشِ بزرگ‌ترِ قالبِ ' + link.getAttribute('data-title');
          title.textContent = link.getAttribute('data-title');
          dialog.showModal();
        });
      });
      var close = dialog.querySelector('[data-ob-lightbox-close]');
      if (close) close.addEventListener('click', function () { dialog.close(); });
      dialog.addEventListener('click', function (event) { if (event.target === dialog) dialog.close(); });
      dialog.addEventListener('close', function () { img.removeAttribute('src'); });
    }

    refresh();
    filter();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-ob-industry]').forEach(initIndustry);
    document.querySelectorAll('[data-ob-templates]').forEach(initTemplates);
    document.querySelectorAll('form[data-ob-once]').forEach(initOnce);
    document.querySelectorAll('[data-ob-logo-input]').forEach(initLogo);
    var summary = document.querySelector('[data-ob-error-summary]');
    if (summary && summary.focus) summary.focus({ preventScroll: false });
  });
})();
