/* ============================================
   پنل مدیریت فروشگاه ساز - اسکریپت مشترک
   ============================================ */

// ---------- Sidebar toggle ----------
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const mainArea = document.getElementById('mainArea');
  const overlay = document.getElementById('sidebarOverlay');

  if (window.innerWidth <= 992) {
    sidebar.classList.toggle('collapsed');
    overlay.classList.toggle('show');
  } else {
    sidebar.classList.toggle('collapsed');
    mainArea.classList.toggle('full');
  }
}

// Close sidebar on mobile when clicking overlay
document.addEventListener('DOMContentLoaded', function () {
  const overlay = document.getElementById('sidebarOverlay');
  if (overlay) {
    overlay.addEventListener('click', function () {
      const sidebar = document.getElementById('sidebar');
      sidebar.classList.add('collapsed');
      overlay.classList.remove('show');
    });
  }

  // Auto-close on mobile after navigation
  if (window.innerWidth <= 992) {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.add('collapsed');
  }
});

// ---------- Menu group expand/collapse ----------
function toggleMenuGroup(header) {
  const group = header.closest('.menu-group');
  const sub = group.querySelector('.menu-sub');
  if (!sub) return;
  sub.classList.toggle('open');
  header.classList.toggle('expanded');
}

// Auto-expand menu group that contains active item
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.menu-sub').forEach(function (sub) {
    if (sub.querySelector('a.active')) {
      sub.classList.add('open');
      const header = sub.previousElementSibling;
      if (header) header.classList.add('expanded');
    }
  });
});

// ---------- Modal helpers ----------
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('open');
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('open');
}

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) {
        overlay.classList.remove('open');
      }
    });
  });
});

// ---------- Filter tabs ----------
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.filter-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      const siblings = this.parentElement.querySelectorAll('.filter-tab');
      siblings.forEach(function (s) { s.classList.remove('active'); });
      this.classList.add('active');
    });
  });
});

// ---------- Generic toast (alert) ----------
function toast(message, type) {
  type = type || 'info';
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%);padding:14px 26px;border-radius:14px;font-size:13.5px;font-weight:600;font-family:inherit;z-index:9999;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.3);animation:toastIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);box-shadow:0 12px 32px rgba(0,0,0,0.2);';
  const styles = {
    success: 'background:linear-gradient(135deg, rgba(16,185,129,0.95), rgba(5,150,105,0.95));',
    error: 'background:linear-gradient(135deg, rgba(239,68,68,0.95), rgba(220,38,38,0.95));',
    info: 'background:linear-gradient(135deg, rgba(59,130,246,0.95), rgba(37,99,235,0.95));',
    warning: 'background:linear-gradient(135deg, rgba(245,158,11,0.95), rgba(249,115,22,0.95));'
  };
  t.style.cssText += styles[type] || styles.info;
  t.style.color = '#fff';
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(function () {
    t.style.transition = 'all 0.3s';
    t.style.opacity = '0';
    t.style.transform = 'translate(-50%, 20px)';
    setTimeout(function () { t.remove(); }, 300);
  }, 2500);
}

// ---------- Demo button handlers ----------
document.addEventListener('DOMContentLoaded', function () {
  // Any button with data-toast="message" shows toast on click
  document.querySelectorAll('[data-toast]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      toast(this.getAttribute('data-toast'), this.getAttribute('data-toast-type') || 'info');
    });
  });

  // Logout "button" — just show toast (no real backend)
  document.querySelectorAll('[data-action="logout"]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      toast('در حال خروج از حساب کاربری... (نسخه دمو)', 'info');
    });
  });

  // View-store button
  document.querySelectorAll('[data-action="view-store"]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      toast('باز کردن فروشگاه در تب جدید... (نسخه دمو)', 'info');
    });
  });
});

// ---------- Form submit demo ----------
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('form[data-demo-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const msg = this.getAttribute('data-demo-form') || 'اطلاعات با موفقیت ثبت شد';
      toast(msg, 'success');
    });
  });
});

// ---------- Toggle checklist item (visual only) ----------
function toggleChecklist(item) {
  item.classList.toggle('done');
}

// ---------- Search input demo ----------
document.addEventListener('DOMContentLoaded', function () {
  const searchInputs = document.querySelectorAll('.search-box input');
  searchInputs.forEach(function (input) {
    input.addEventListener('input', function () {
      const q = this.value.toLowerCase().trim();
      const table = this.closest('.content').querySelector('.data-table tbody');
      if (!table) return;
      table.querySelectorAll('tr').forEach(function (row) {
        const text = row.textContent.toLowerCase();
        row.style.display = (q === '' || text.includes(q)) ? '' : 'none';
      });
    });
  });
});

// Storefront integration
window.addEventListener('DOMContentLoaded', function(){
  document.querySelectorAll('[data-action="view-store"]').forEach(function(btn){
    btn.setAttribute('href','storefront.html'); btn.setAttribute('target','_blank');
    const clean=btn.cloneNode(true); btn.parentNode.replaceChild(clean,btn);
  });
  const contentGroup=[...document.querySelectorAll('.menu-item')].find(x=>x.textContent.includes('محتوای فروشگاه'));
  if(contentGroup && contentGroup.nextElementSibling && !document.querySelector('[data-key="store-editor"]')){
    const li=document.createElement('li'); li.innerHTML='<a href="store-editor.html" data-key="store-editor">ویرایش نمایش مشتری</a>'; contentGroup.nextElementSibling.appendChild(li);
  }
});
