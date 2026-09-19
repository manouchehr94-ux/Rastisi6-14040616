// P5-W5C — Ready Template Gallery in-page Preview controller.
//
// Owns ONLY: opening/closing the ONE shared preview dialog, retargeting
// its ONE iframe to the existing canonical
// dashboard:storefront-builder-template-live-preview route (Demo or
// ?data=merchant — both URLs are pre-built server-side, in the template,
// via {% url %}; this file never constructs or guesses a URL), toggling
// the Merchant/Demo data-source control, and applying Desktop/Tablet/
// Mobile presentation to that same iframe (independent reimplementation
// of R4's own 1200/768/390 device-switcher contract — see the
// implementation plan's §11 for why this is not a shared/imported
// module). It owns NO Ready Template definitions, no Store/tenant
// identity, no Draft state, no mutation, no catalog data, and renders no
// storefront HTML itself — the iframe's document is entirely the
// existing server-rendered live-preview page.
(function () {
  'use strict';

  function boot() {
    var root = document.querySelector('[data-tpl-preview-root]');
    var dialog = root && root.querySelector('.tpl-preview-dialog');
    var titleEl = root && root.querySelector('[data-tpl-preview-title]');
    var closeBtn = root && root.querySelector('[data-tpl-preview-close]');
    var canvas = root && root.querySelector('[data-tpl-preview-canvas]');
    var frame = root && root.querySelector('[data-tpl-preview-frame]');
    var newTabLink = root && root.querySelector('[data-tpl-preview-new-tab]');
    var datasourceButtons = root ? root.querySelectorAll('[data-tpl-preview-datasource]') : [];
    var deviceButtons = root ? root.querySelectorAll('[data-tpl-preview-device]') : [];
    if (!root || !dialog || !frame || !canvas) return;

    var state = {
      urls: { demo: '', merchant: '' },
      dataSource: 'merchant',
      device: 'desktop',
      lastTrigger: null,
    };

    function currentUrl() {
      return state.dataSource === 'merchant' ? state.urls.merchant : state.urls.demo;
    }

    function syncViewport() {
      var widths = {
        desktop: parseInt(frame.dataset.desktopViewportWidth, 10) || 1200,
        tablet: parseInt(frame.dataset.tabletViewportWidth, 10) || 768,
        mobile: parseInt(frame.dataset.mobileViewportWidth, 10) || 390,
      };
      if (state.device === 'desktop') {
        frame.style.width = '';
        frame.style.height = '';
        frame.style.transform = '';
        frame.style.margin = '';
        return;
      }
      var requestedWidth = widths[state.device] || widths.desktop;
      var availableWidth = Math.max(1, canvas.clientWidth - 2);
      var fitScale = Math.min(1, availableWidth / requestedWidth);
      var scale = Math.max(0.35, fitScale);
      frame.style.width = requestedWidth + 'px';
      frame.style.height = Math.ceil(canvas.clientHeight / scale) + 'px';
      frame.style.transform = 'scale(' + scale + ')';
      frame.style.transformOrigin = 'top center';
      frame.style.margin = '0 auto';
    }

    function setDevice(device) {
      if (['desktop', 'tablet', 'mobile'].indexOf(device) === -1) return;
      state.device = device;
      canvas.setAttribute('data-tpl-preview-device', device);
      deviceButtons.forEach(function (btn) {
        btn.setAttribute('aria-pressed', btn.getAttribute('data-tpl-preview-device') === device ? 'true' : 'false');
      });
      syncViewport();
    }

    // Only updates the toggle-button state; never touches the iframe by
    // itself — callers decide whether a (re)load is actually needed, so a
    // click that re-selects the ALREADY-active mode is a true no-op
    // instead of forcing an unnecessary iframe reload.
    function setDataSourceButtonState(mode) {
      if (mode !== 'merchant' && mode !== 'demo') return;
      state.dataSource = mode;
      datasourceButtons.forEach(function (btn) {
        btn.setAttribute('aria-pressed', btn.getAttribute('data-tpl-preview-datasource') === mode ? 'true' : 'false');
      });
    }

    function loadCurrentUrl() {
      var url = currentUrl();
      if (!url) return;
      frame.src = url;
      if (newTabLink) newTabLink.href = url;
    }

    function focusableElements() {
      return Array.prototype.slice.call(
        dialog.querySelectorAll('button:not([disabled]), a[href], iframe, [tabindex]:not([tabindex="-1"])'),
      );
    }

    function openFromTrigger(trigger) {
      var demoUrl = trigger.getAttribute('data-tpl-preview-url-demo');
      var merchantUrl = trigger.getAttribute('data-tpl-preview-url-merchant');
      var label = trigger.getAttribute('data-tpl-preview-label') || '';
      var defaultMode = trigger.getAttribute('data-tpl-preview-default-mode') === 'demo' ? 'demo' : 'merchant';
      if (!demoUrl || !merchantUrl) return;

      state.urls.demo = demoUrl;
      state.urls.merchant = merchantUrl;
      state.lastTrigger = trigger;

      if (titleEl) titleEl.textContent = 'پیش‌نمایشِ قالبِ «' + label + '»';
      setDataSourceButtonState(defaultMode);
      setDevice('desktop');
      // A fresh open/retarget always (re)loads — unlike the toggle-button
      // click handler below, there is no "already showing this" case here:
      // the template (and therefore the URL) just changed.
      loadCurrentUrl();

      root.classList.add('is-open');
      root.setAttribute('aria-hidden', 'false');
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }

    function closeDialog() {
      root.classList.remove('is-open');
      root.setAttribute('aria-hidden', 'true');
      frame.src = 'about:blank';
      if (state.lastTrigger) state.lastTrigger.focus({ preventScroll: true });
    }

    function isOpen() {
      return root.classList.contains('is-open');
    }

    // P5-W5C Independent Architect repair — Escape must also close the
    // dialog when keyboard focus has moved INSIDE the (same-origin)
    // preview iframe's own document, since keydown events fired there
    // never bubble up to this (parent) document's listener below. Each
    // navigation of the iframe (open, retarget, data-source switch) gets
    // a brand-new Document object, so this attaches once per `load`
    // event — never accumulating duplicate listeners on a stale
    // document. Wrapped in try/catch purely as defense-in-depth (the
    // canonical live-preview route is always same-origin in this
    // deployment); a cross-origin access exception here would just mean
    // Escape-from-inside-the-iframe silently does nothing, never an
    // uncaught error.
    frame.addEventListener('load', function () {
      try {
        var frameDoc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
        if (!frameDoc) return;
        frameDoc.addEventListener('keydown', function (evt) {
          if (evt.key === 'Escape' && isOpen()) {
            evt.preventDefault();
            closeDialog();
          }
        });
      } catch (err) {
        // Cross-origin or otherwise inaccessible — nothing to attach.
      }
    });

    document.addEventListener('click', function (evt) {
      var trigger = evt.target.closest('[data-tpl-preview-trigger]');
      if (!trigger) return;
      // Let the browser's native "open in new tab" (Ctrl/Cmd/Shift-click)
      // pass through untouched — only a plain click opens the in-page
      // dialog. The trigger's own href already targets the canonical
      // live-preview URL for this fallback.
      if (evt.ctrlKey || evt.metaKey || evt.shiftKey || evt.button === 1) return;
      evt.preventDefault();
      openFromTrigger(trigger);
    });

    if (closeBtn) closeBtn.addEventListener('click', closeDialog);
    root.addEventListener('click', function (evt) {
      if (evt.target === root) closeDialog();
    });
    document.addEventListener('keydown', function (evt) {
      if (!isOpen()) return;
      if (evt.key === 'Escape') {
        evt.preventDefault();
        closeDialog();
        return;
      }
      // Focus trap: role="dialog" aria-modal="true" promises assistive
      // tech that Tab/Shift+Tab never leaves the dialog while it is open.
      if (evt.key === 'Tab') {
        var focusable = focusableElements();
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (evt.shiftKey && document.activeElement === first) {
          evt.preventDefault();
          last.focus();
        } else if (!evt.shiftKey && document.activeElement === last) {
          evt.preventDefault();
          first.focus();
        }
      }
    });

    datasourceButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mode = btn.getAttribute('data-tpl-preview-datasource');
        if (mode === state.dataSource) return;
        setDataSourceButtonState(mode);
        loadCurrentUrl();
      });
    });
    deviceButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        setDevice(btn.getAttribute('data-tpl-preview-device'));
      });
    });

    if (window.ResizeObserver) {
      new ResizeObserver(function () { syncViewport(); }).observe(canvas);
    } else {
      window.addEventListener('resize', syncViewport);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
