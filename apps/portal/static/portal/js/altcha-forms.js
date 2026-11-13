/* Official widget + Persian translation are local modules; no CDN/Cloud calls. */
import '../vendor/altcha/3.6.0/fa.js';
import '../vendor/altcha/3.6.0/altcha.min.js';

const widgets = [...document.querySelectorAll('.rasti-altcha altcha-widget')];
widgets.forEach((widget) => {
  const status = widget.parentElement.querySelector('.rasti-altcha-status');
  widget.addEventListener('statechange', (event) => {
    const state = event.detail.state;
    widget.dataset.state = state;
    status.textContent = state === 'verifying' ? 'در حال بررسی امنیتی…'
      : state === 'verified' ? 'تأیید شد؛ اکنون می‌توانید ادامه دهید.'
        : state === 'expired' ? 'تأیید منقضی شد؛ دوباره تأیید کنید.'
          : state === 'error' ? 'تأیید انجام نشد؛ اتصال را بررسی و دوباره تلاش کنید.' : '';
  });
});
// Capture before auth-forms.js locks submit buttons. This is UX only: the
// server always verifies the PoW and consumes it atomically, even without JS.
document.addEventListener('submit', (event) => {
  const widget = event.target.querySelector?.('.rasti-altcha altcha-widget');
  if (!widget || widget.getState() === 'verified') return;
  event.preventDefault();
  event.stopImmediatePropagation();
  widget.parentElement.querySelector('.rasti-altcha-status').textContent = 'ابتدا «من ربات نیستم» را تأیید کنید.';
  const checkbox = widget.querySelector('input[type="checkbox"]') || widget.shadowRoot?.querySelector('input[type="checkbox"]');
  if (checkbox) checkbox.focus(); else widget.focus();
}, true);
// Never reuse a solved widget restored from the browser's back/forward cache.
window.addEventListener('pageshow', (event) => {
  if (event.persisted) widgets.forEach((widget) => widget.reset());
});
