/* Progressive enhancement for the public auth pages (register / login / verify / reset).
 *
 * Everything here is UX only. The server stays authoritative for rate limits,
 * OTP expiry/attempts and idempotency; with JavaScript disabled every form
 * still works and every button stays enabled.
 */
(() => {
  const fa = new Intl.NumberFormat('fa-IR');

  // Put the cursor where the user must act: the first invalid field, or the
  // code box on the verify page.
  // Only look inside visible panels: the login page keeps both forms in the DOM.
  const visible = (el) => el && !el.closest('[hidden]');
  const firstVisible = (selector) => [...document.querySelectorAll(selector)].find(visible);
  const focusTarget = firstVisible('[aria-invalid="true"]') || firstVisible('.p-alert[role="alert"]')
    || document.querySelector('#id_code') || document.querySelector('[data-autofocus]');
  if (focusTarget) focusTarget.focus({ preventScroll: false });

  // Login method tabs. They are real links (?mode=…) so the page works without
  // JavaScript; with it, switching is instant and the URL is kept in sync.
  const loginModes = document.querySelector('[data-login-modes]');
  if (loginModes) {
    const tabs = [...loginModes.querySelectorAll('[data-login-tab]')];
    const panels = [...loginModes.querySelectorAll('[data-login-panel]')];
    tabs.forEach((tab) => tab.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button) return;
      event.preventDefault();
      const mode = tab.dataset.loginTab;
      tabs.forEach((other) => {
        const on = other === tab;
        other.classList.toggle('is-active', on);
        if (on) other.setAttribute('aria-current', 'true'); else other.removeAttribute('aria-current');
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.loginPanel !== mode; });
      try { history.replaceState(null, '', tab.getAttribute('href')); } catch (_) { /* optional */ }
    }));
  }

  // Optional show/hide for password fields (added by JS only, so no-JS layout is unchanged).
  document.querySelectorAll('[data-password-field]').forEach((wrap) => {
    const input = wrap.querySelector('input');
    if (!input) return;
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'r-password-toggle';
    toggle.textContent = 'نمایش';
    toggle.setAttribute('aria-label', 'نمایش رمز عبور');
    toggle.setAttribute('aria-pressed', 'false');
    if (input.id) toggle.setAttribute('aria-controls', input.id);
    const paint = (show) => {
      input.type = show ? 'text' : 'password';
      toggle.textContent = show ? 'پنهان' : 'نمایش';
      toggle.setAttribute('aria-pressed', show ? 'true' : 'false');
    };
    toggle.addEventListener('click', () => paint(input.type === 'password'));
    wrap.appendChild(toggle);
    wrap.closest('form')?.addEventListener('submit', () => paint(false));
    window.addEventListener('pageshow', () => paint(false));
  });

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

  // Resend countdown. The server is the authority (a direct POST inside the cooldown is rejected);
  // this only counts down the server-rendered value ``data-resend-in`` and states when resend opens.
  const resendForm = document.querySelector('[data-resend-form]');
  const resendButton = document.querySelector('[data-resend-button]');
  const resendHint = document.querySelector('[data-resend-hint]');
  if (resendForm && resendButton) {
    const label = resendButton.textContent.trim();
    const idleHint = resendHint ? resendHint.textContent : '';
    const cooldown = resendHint ? (parseInt(resendHint.dataset.cooldown || '0', 10) || 0) : 0;
    let remaining = parseInt(resendForm.dataset.resendIn || '0', 10) || 0;
    const clock = (total) => {
      const m = Math.floor(total / 60);
      const sec = String(total % 60).padStart(2, '0');
      return `${fa.format(m)}:${sec.replace(/\d/g, (d) => fa.format(d))}`;
    };
    const paint = () => {
      if (remaining > 0) {
        resendButton.disabled = true;
        resendButton.textContent = `${label} (${clock(remaining)})`;
        if (resendHint) {
          resendHint.textContent = `کد نرسید؟ ارسال دوباره‌ی کد پس از ${clock(remaining)} ممکن می‌شود` +
            (cooldown ? ` (پس از هر ارسال ${fa.format(cooldown)} ثانیه صبر لازم است).` : '.');
        }
      } else {
        resendButton.disabled = false;
        resendButton.textContent = label;
        if (resendHint) resendHint.textContent = idleHint && !/پس از/.test(idleHint)
          ? idleHint : 'کد نرسید؟ حالا می‌توانید کد جدید بگیرید؛ کد قبلی باطل می‌شود.';
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
