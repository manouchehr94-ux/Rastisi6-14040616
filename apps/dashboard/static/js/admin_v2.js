(function () {
  'use strict';

  function normalize(value) {
    return String(value || '')
      .trim()
      .toLocaleLowerCase('fa')
      .replace(/[يى]/g, 'ی')
      .replace(/ك/g, 'ک')
      .replace(/[ۀة]/g, 'ه')
      .replace(/[ؤ]/g, 'و')
      .replace(/[إأ]/g, 'ا')
      .replace(/[\u064B-\u065F\u0670]/g, '')
      .replace(/[\u200c\u200d]/g, ' ')
      .replace(/[\/_\-–—|]+/g, ' ')
      .replace(/\s+/g, ' ');
  }

  function isEmbedded() {
    try {
      return window.self !== window.top || new URL(window.location.href).searchParams.get('embed') === '1';
    } catch (_) {
      return new URL(window.location.href).searchParams.get('embed') === '1';
    }
  }

  function initEmbeddedMode() {
    if (!isEmbedded()) return;
    document.body.classList.add('admin-v2-embedded');
  }

  function makeItem(node, fallbackPath) {
    const title = (node.dataset && node.dataset.title) || node.textContent.trim();
    const path = (node.dataset && node.dataset.path) || fallbackPath || '';
    const keywords = (node.dataset && node.dataset.keywords) || '';
    const icon = (node.dataset && node.dataset.icon) || '↗';
    const href = node.getAttribute('href') || '#';
    const aria = node.getAttribute('aria-label') || '';
    const page = (node.dataset && node.dataset.page) || '';
    return {
      title: title,
      path: path,
      keywords: keywords,
      icon: icon,
      href: href,
      haystack: normalize([title, path, keywords, aria, page].join(' ')),
      normalizedTitle: normalize(title),
      normalizedPath: normalize(path),
    };
  }

  function collectNavigationItems() {
    // Sidebar sections and section tabs are already in the generated
    // palette index (data-palette-skip), so only harvest what it lacks.
    const selectors = [
      '.sidebar a.nav-item[href]',
      '.sidebar a[href][data-page]',
      '.admin-section-tabs a[href]',
      '.settings-nav a[href]',
      '[data-admin-v2-searchable][href]'
    ];
    const nodes = Array.from(document.querySelectorAll(selectors.join(',')));
    return nodes
      .filter((node) => !node.closest('#adminV2CommandIndex'))
      .filter((node) => !node.hasAttribute('data-palette-skip'))
      .filter((node) => {
        const href = node.getAttribute('href') || '';
        return href && href !== '#' && !href.toLowerCase().startsWith('javascript:');
      })
      .map((node) => {
        const inSettings = node.closest('.settings-nav');
        return makeItem(node, inSettings ? 'تنظیمات ← بخش‌های تنظیمات' : 'پنل مدیریت');
      });
  }

  function readIndex() {
    const root = document.getElementById('adminV2CommandIndex');
    const explicit = root
      ? Array.from(root.querySelectorAll('[data-search-item]')).map((node) => makeItem(node, ''))
      : [];
    const merged = explicit.concat(collectNavigationItems());
    const seen = new Set();
    return merged.filter((item) => {
      // One entry per destination; the generated index comes first and wins.
      const key = normalize(item.href);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function rankItems(items, query) {
    const q = normalize(query);
    if (!q) return items.slice(0, 14);
    const tokens = q.split(' ').filter(Boolean);
    return items
      .map((item, order) => {
        const allTokensMatch = tokens.every((token) => item.haystack.includes(token));
        if (!allTokensMatch) return null;
        let score = 0;
        if (item.normalizedTitle === q) score += 120;
        if (item.normalizedTitle.startsWith(q)) score += 70;
        if (item.normalizedTitle.includes(q)) score += 45;
        if (item.normalizedPath.includes(q)) score += 20;
        if (item.haystack.includes(q)) score += 12;
        score += Math.max(0, 10 - order * 0.01);
        return { item: item, score: score, order: order };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || a.order - b.order)
      .slice(0, 14)
      .map((entry) => entry.item);
  }

  function initCommandPalette() {
    const overlay = document.getElementById('adminV2CommandPalette');
    const input = document.getElementById('adminV2CommandInput');
    const results = document.getElementById('adminV2CommandResults');
    const trigger = document.getElementById('adminV2SearchTrigger');
    if (!overlay || !input || !results) return;

    const items = readIndex();
    let visible = [];
    let activeIndex = 0;

    function escapeHtml(value) {
      return String(value).replace(/[&<>'"]/g, function (char) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char];
      });
    }

    function render() {
      visible = rankItems(items, input.value);
      activeIndex = Math.min(activeIndex, Math.max(visible.length - 1, 0));
      if (!visible.length) {
        results.innerHTML = '<div class="admin-v2-command-empty">چیزی پیدا نشد. نام کار را ساده بنویسید؛ مثلاً «پیامک»، «لوگو»، «مالیات» یا «کالا».</div>';
        return;
      }
      results.innerHTML = visible.map((item, index) => (
        '<button type="button" class="admin-v2-command-item' + (index === activeIndex ? ' active' : '') + '" data-index="' + index + '">' +
          '<span class="cmd-icon">' + escapeHtml(item.icon) + '</span>' +
          '<span class="cmd-copy"><b>' + escapeHtml(item.title) + '</b><small>' + escapeHtml(item.path) + '</small></span>' +
          '<span aria-hidden="true">↵</span>' +
        '</button>'
      )).join('');
    }

    function openPalette(seed) {
      overlay.classList.add('open');
      overlay.setAttribute('aria-hidden', 'false');
      input.value = seed || '';
      activeIndex = 0;
      render();
      window.setTimeout(function () { input.focus(); input.select(); }, 0);
    }

    function closePalette() {
      overlay.classList.remove('open');
      overlay.setAttribute('aria-hidden', 'true');
      if (trigger) trigger.focus({ preventScroll: true });
    }

    function go(index) {
      const item = visible[index];
      if (!item) return;
      window.location.assign(item.href);
    }

    input.addEventListener('input', function () { activeIndex = 0; render(); });
    results.addEventListener('click', function (event) {
      const button = event.target.closest('[data-index]');
      if (!button) return;
      go(parseInt(button.dataset.index, 10));
    });
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) closePalette();
    });
    if (trigger) {
      trigger.addEventListener('click', function () { openPalette(''); });
      trigger.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openPalette(''); }
      });
    }

    document.addEventListener('keydown', function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        overlay.classList.contains('open') ? closePalette() : openPalette('');
        return;
      }
      if (!overlay.classList.contains('open')) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closePalette();
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        activeIndex = Math.min(activeIndex + 1, Math.max(visible.length - 1, 0));
        render();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        render();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        go(activeIndex);
      }
    });

    window.RastiSiAdminV2 = {
      openSearch: openPalette,
      closeSearch: closePalette,
      normalizeSearch: normalize,
      collectNavigationItems: collectNavigationItems,
      rankItems: rankItems,
      isEmbedded: isEmbedded,
    };
  }

  // On narrow screens the tab strip scrolls horizontally; make sure the
  // active tab is not hidden off-screen when the page loads.
  function initSectionTabs() {
    const active = document.querySelector('.admin-section-tab.active');
    const strip = document.querySelector('.admin-section-tablist');
    if (!active || !strip || strip.scrollWidth <= strip.clientWidth) return;
    // scrollIntoView handles RTL scroll origins; block:'nearest' never moves the page.
    active.scrollIntoView({ inline: 'center', block: 'nearest' });
  }

  function boot() {
    initEmbeddedMode();
    initSectionTabs();
    initCommandPalette();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
