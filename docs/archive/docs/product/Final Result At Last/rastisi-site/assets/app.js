/* ============================================
   RastiSi (راستیسی) - اسکریپت مشترک
   ============================================ */

// ---------- Toast ----------
function toast(message, type) {
  type = type || 'info';
  const t = document.createElement('div');
  t.className = 'toast';
  const styles = {
    success: 'background:linear-gradient(135deg, rgba(16,185,129,0.95), rgba(5,150,105,0.95));',
    error: 'background:linear-gradient(135deg, rgba(239,68,68,0.95), rgba(220,38,38,0.95));',
    info: 'background:linear-gradient(135deg, rgba(13,148,136,0.95), rgba(15,118,110,0.95));',
    warning: 'background:linear-gradient(135deg, rgba(245,158,11,0.95), rgba(249,115,22,0.95));'
  };
  t.style.cssText = styles[type] || styles.info;
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(function () {
    t.style.transition = 'all 0.3s';
    t.style.opacity = '0';
    t.style.transform = 'translate(-50%, 20px)';
    setTimeout(function () { t.remove(); }, 300);
  }, 2500);
}

// ---------- Mobile menu ----------
function toggleMobileMenu() {
  const menu = document.getElementById('navbarMenu');
  const overlay = document.getElementById('menuOverlay');
  if (menu) menu.classList.toggle('open');
  if (overlay) overlay.classList.toggle('show');
}

function closeMobileMenu() {
  const menu = document.getElementById('navbarMenu');
  const overlay = document.getElementById('menuOverlay');
  if (menu) menu.classList.remove('open');
  if (overlay) overlay.classList.remove('show');
}

document.addEventListener('DOMContentLoaded', function () {
  const overlay = document.getElementById('menuOverlay');
  if (overlay) overlay.addEventListener('click', closeMobileMenu);
});

// ---------- Dashboard sidebar toggle (mobile) ----------
function toggleDashSidebar() {
  const sb = document.getElementById('dashSidebar');
  if (sb) sb.classList.toggle('open');
}

// ---------- Demo form handlers ----------
document.addEventListener('DOMContentLoaded', function () {
  // Demo forms: show toast and prevent submit
  document.querySelectorAll('form[data-demo-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const msg = this.getAttribute('data-demo-form') || 'اطلاعات با موفقیت ثبت شد';
      const redirect = this.getAttribute('data-redirect');
      toast(msg, 'success');
      if (redirect) {
        setTimeout(function () { window.location.href = redirect; }, 900);
      }
    });
  });

  // Buttons with data-toast
  document.querySelectorAll('[data-toast]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      toast(this.getAttribute('data-toast'), this.getAttribute('data-toast-type') || 'info');
    });
  });

  // Buttons with data-redirect
  document.querySelectorAll('[data-redirect]').forEach(function (btn) {
    if (btn.tagName === 'BUTTON' || btn.tagName === 'A') {
      btn.addEventListener('click', function (e) {
        const r = this.getAttribute('data-redirect');
        if (r && !this.hasAttribute('data-toast')) {
          e.preventDefault();
          setTimeout(function () { window.location.href = r; }, 100);
        }
      });
    }
  });
});

// ---------- Category search & filter ----------
function filterCategories(query) {
  query = (query || '').toLowerCase().trim();
  const cards = document.querySelectorAll('.category-card');
  let visibleCount = 0;
  cards.forEach(function (card) {
    const name = (card.getAttribute('data-name') || '').toLowerCase();
    const sector = (card.getAttribute('data-sector') || '').toLowerCase();
    if (query === '' || name.includes(query) || sector.includes(query)) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });
  const emptyMsg = document.getElementById('catEmpty');
  if (emptyMsg) emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
}

function filterBySector(sector) {
  // Update tabs
  document.querySelectorAll('.cat-tab').forEach(function (t) {
    t.classList.toggle('active', t.getAttribute('data-sector') === sector);
  });

  const cards = document.querySelectorAll('.category-card');
  let visibleCount = 0;
  cards.forEach(function (card) {
    if (sector === 'all' || card.getAttribute('data-sector') === sector) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });
  const emptyMsg = document.getElementById('catEmpty');
  if (emptyMsg) emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
}

// ---------- Category selection ----------
function selectCategory(card) {
  document.querySelectorAll('.category-card').forEach(function (c) {
    c.classList.remove('selected');
  });
  card.classList.add('selected');
  const name = card.getAttribute('data-name');
  const hidden = document.getElementById('selectedCategory');
  if (hidden) hidden.value = name;
  const display = document.getElementById('selectedCategoryDisplay');
  if (display) display.textContent = name;
}

// ---------- Wizard navigation ----------
function goToWizardStep(stepNum) {
  // Hide all panels
  document.querySelectorAll('.wizard-panel').forEach(function (p) {
    p.classList.remove('active');
  });
  // Show target
  const target = document.querySelector('.wizard-panel[data-step="' + stepNum + '"]');
  if (target) target.classList.add('active');

  // Update progress dots
  document.querySelectorAll('.wizard-step-dot').forEach(function (dot) {
    const ds = parseInt(dot.getAttribute('data-step'));
    dot.classList.remove('active', 'done');
    if (ds < stepNum) dot.classList.add('done');
    else if (ds === stepNum) dot.classList.add('active');
  });

  // Update lines
  document.querySelectorAll('.wizard-step-line').forEach(function (line) {
    const ls = parseInt(line.getAttribute('data-step'));
    line.classList.toggle('done', ls < stepNum);
  });

  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function nextStep(currentStep) {
  // Demo: just go to next step
  goToWizardStep(currentStep + 1);
}

function prevStep(currentStep) {
  goToWizardStep(currentStep - 1);
}

// ---------- Subdomain live check (demo) ----------
function checkSubdomain(input) {
  const val = input.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
  input.value = val;
  const hint = document.getElementById('subdomainHint');
  if (!hint) return;
  if (val.length < 3) {
    hint.className = 'form-hint';
    hint.textContent = 'حداقل ۳ کاراکتر وارد کنید';
  } else {
    hint.className = 'form-hint success';
    hint.innerHTML = '✓ زیردامنه <strong>' + val + '.rastisi.ir</strong> آزاد است';
  }
}

// ---------- Domain connection demo ----------
function checkDomain(input) {
  const val = input.value.trim();
  const hint = document.getElementById('domainHint');
  if (!hint) return;
  if (val.length < 5 || !val.includes('.')) {
    hint.className = 'form-hint';
    hint.textContent = 'یک دامنه معتبر وارد کنید (مثال: myshop.ir)';
  } else {
    hint.className = 'form-hint success';
    hint.innerHTML = '✓ دامنه <strong>' + val + '</strong> آماده اتصال است. روی «اتصال دامنه» کلیک کنید.';
  }
}

// ---------- Smooth scroll for anchor links ----------
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      const target = this.getAttribute('href');
      if (target === '#' || target.length < 2) return;
      const el = document.querySelector(target);
      if (el) {
        e.preventDefault();
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
});

// ---------- Pricing selection ----------
function selectPlan(planName, price) {
  // Store selection
  try {
    sessionStorage.setItem('rastisi_plan', planName);
    sessionStorage.setItem('rastisi_price', price);
  } catch (e) {}
  toast('پلن «' + planName + '» انتخاب شد. در حال انتقال به پرداخت...', 'success');
  setTimeout(function () {
    window.location.href = 'checkout.html';
  }, 1000);
}

// ---------- Checkout: pre-fill from session ----------
document.addEventListener('DOMContentLoaded', function () {
  const planDisplay = document.getElementById('selectedPlan');
  const priceDisplay = document.getElementById('selectedPrice');
  if (planDisplay && priceDisplay) {
    try {
      const plan = sessionStorage.getItem('rastisi_plan') || 'حرفه‌ای';
      const price = sessionStorage.getItem('rastisi_price') || '۸۹۰٬۰۰۰';
      planDisplay.textContent = plan;
      priceDisplay.textContent = price + ' تومان';
    } catch (e) {}
  }
});

// ---------- Store activation success animation ----------
function activateStore() {
  toast('در حال راه‌اندازی فروشگاه شما...', 'info');
  setTimeout(function () {
    toast('فروشگاه شما با موفقیت فعال شد! 🎉', 'success');
  }, 1500);
  setTimeout(function () {
    window.location.href = 'store-success.html';
  }, 3000);
}
