/* Progressive enhancement for the public auth pages (register / verify).
 *
 * Everything here is UX only. The server stays authoritative for rate limits,
 * OTP expiry/attempts and idempotency; with JavaScript disabled every form
 * still works and every button stays enabled.
 */
(() => {
  const fa = new Intl.NumberFormat('fa-IR');

  // Put the cursor where the user must act: the first invalid field, or the
  // code box on the verify page.
  const focusTarget = document.querySelector('[aria-invalid="true"]') || document.querySelector('#id_code')
    || document.querySelector('[data-autofocus]');
  if (focusTarget) focusTarget.focus({ preventScroll: false });

  // Double-submit protection: lock the submit button once a form is sent.
  document.querySelectorAll('form[data-auth-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.submitting === '1') {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = '1';
      form.setAttribute('aria-busy', 'true');
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.dataset.label = button.textContent;
        // Disable on the next tick so the click's own submit still goes out.
        setTimeout(() => {
          button.disabled = true;
          if (form.dataset.loadingText) button.textContent = form.dataset.loadingText;
        }, 0);
      }
    });
  });

  // Returning with the back/forward cache must not leave a dead button.
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    document.querySelectorAll('form[data-auth-form]').forEach((form) => {
      form.dataset.submitting = '0';
      form.removeAttribute('aria-busy');
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = false;
        if (button.dataset.label) button.textContent = button.dataset.label;
      }
    });
  });

  // Resend countdown (cosmetic; the backend rate limit is what actually applies).
  const resendForm = document.querySelector('[data-resend-form]');
  const resendButton = document.querySelector('[data-resend-button]');
  if (resendForm && resendButton) {
    const label = resendButton.textContent.trim();
    let remaining = parseInt(resendForm.dataset.resendIn || '0', 10) || 0;
    const paint = () => {
      if (remaining > 0) {
        resendButton.disabled = true;
        resendButton.textContent = `${label} (${fa.format(remaining)} ثانیه)`;
      } else {
        resendButton.disabled = false;
        resendButton.textContent = label;
      }
    };
    paint();
    if (remaining > 0) {
      const timer = setInterval(() => {
        remaining -= 1;
        paint();
        if (remaining <= 0) clearInterval(timer);
      }, 1000);
    }
    resendForm.addEventListener('submit', () => {
      setTimeout(() => { resendButton.disabled = true; }, 0);
    });
  }

  // Code validity countdown.
  const expiry = document.querySelector('[data-otp-expires]');
  if (expiry) {
    let left = parseInt(expiry.dataset.otpExpires || '0', 10) || 0;
    const tick = () => {
      if (left > 0) {
        const m = Math.floor(left / 60);
        const s = String(left % 60).padStart(2, '0');
        expiry.textContent = `اعتبار این کد: ${fa.format(m)}:${s.replace(/\d/g, (d) => fa.format(d))}`;
      } else {
        expiry.textContent = 'این کد منقضی شده است؛ کد جدید دریافت کنید.';
        expiry.classList.add('is-expired');
      }
    };
    tick();
    if (left > 0) {
      const timer = setInterval(() => {
        left -= 1;
        tick();
        if (left <= 0) clearInterval(timer);
      }, 1000);
    }
  }
})();
