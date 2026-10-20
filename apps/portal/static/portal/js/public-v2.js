/* Progressive enhancement for the public website (Sardar design). Every page works without it. */
(function () {
  'use strict';
  var $ = function (s, e) { return (e || document).querySelector(s); };
  var $$ = function (s, e) { return Array.prototype.slice.call((e || document).querySelectorAll(s)); };
  var icon = function (id) { return '<svg><use href="#i-' + id + '"/></svg>'; };

  /* theme toggle */
  (function () {
    var btn = $('#themeBtn');
    if (!btn) return;
    var root = document.documentElement, mq = window.matchMedia('(prefers-color-scheme: dark)');
    var mode = root.getAttribute('data-theme');
    if (mode !== 'light' && mode !== 'dark') mode = mq.matches ? 'dark' : 'light';
    var set = function (m, save) {
      mode = m; root.setAttribute('data-theme', m);
      var next = m === 'dark' ? 'حالت روشن' : 'حالت تاریک';
      btn.innerHTML = icon(m === 'dark' ? 'sun' : 'moon');
      btn.setAttribute('aria-label', 'رفتن به ' + next); btn.title = next;
      if (save) { try { localStorage.setItem('rs-theme', m); } catch (e) { /* optional */ } }
    };
    set(mode);
    btn.addEventListener('click', function () { set(mode === 'dark' ? 'light' : 'dark', true); });
  })();

  /* mobile menu */
  (function () {
    var btn = $('#menuBtn'), nav = $('#mnav');
    if (!btn || !nav) return;
    btn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    $$('a', nav).forEach(function (a) { a.addEventListener('click', function () { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }); });
  })();

  /* landing demo: one shop window, four looks */
  (function () {
    var store = $('#store'), dataEl = $('#ps-demo-data');
    if (!store || !dataEl) return;
    var data; try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }
    var IMG = data.IMG || {}, THEMES = data.THEMES || [];
    if (!THEMES.length) return;
    var idx = 0, timer = null;
    function apply(i) {
      idx = i; var t = THEMES[i];
      Object.keys(t.v).forEach(function (k) { store.style.setProperty(k, t.v[k]); });
      store.className = 'store ' + t.layout;
      $('#sLogo').textContent = t.name; $('#sTitle').textContent = t.title; $('#sSub').textContent = t.sub;
      $('#demoUrl').textContent = t.url; $('#sHeroImg').src = IMG[t.hero] || '';
      $('#sGrid').innerHTML = t.p.map(function (p) {
        var d = document.createElement('div'); d.className = 's-p';
        var im = document.createElement('div'); im.className = 'im';
        var img = document.createElement('img'); img.alt = ''; img.src = IMG[p[0]] || ''; im.appendChild(img);
        var tt = document.createElement('div'); tt.className = 't'; tt.appendChild(document.createTextNode(p[1]));
        var sp = document.createElement('span'); sp.textContent = p[2] + ' هزار'; tt.appendChild(sp);
        d.appendChild(im); d.appendChild(tt); return d.outerHTML;
      }).join('');
      $$('#demoTags .tag').forEach(function (b) { b.setAttribute('aria-pressed', String(+b.dataset.t === i)); });
    }
    apply(0);
    $$('#demoTags .tag').forEach(function (b) {
      b.addEventListener('click', function () { clearInterval(timer); apply(+b.dataset.t); });
    });
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && THEMES.length > 1) {
      setTimeout(function () { timer = setInterval(function () { apply((idx + 1) % THEMES.length); }, 4500); }, 2200);
    }
  })();

  /* landing workbench: toggle blocks, colour, radius, font */
  (function () {
    var cv = $('#cv');
    if (!cv) return;
    var COLORS = { green: '#177a5f', blue: '#2346b8', brick: '#b4441a', plum: '#a3195b', black: '#1a1a1a' };
    $$('.blk input').forEach(function (c) {
      c.addEventListener('change', function () {
        var target = $('.' + c.dataset.b, cv);
        if (target) target.classList.toggle('hide', !c.checked);
        c.closest('.blk').classList.toggle('off', !c.checked);
      });
    });
    $$('#sw button').forEach(function (b) {
      b.addEventListener('click', function () {
        cv.style.setProperty('--c-acc', COLORS[b.dataset.c] || COLORS.green);
        $$('#sw button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      });
    });
    var rad = $('#rad'); if (rad) rad.addEventListener('input', function (e) { cv.style.setProperty('--c-r', e.target.value + 'px'); });
    var FONTS = { text: 'var(--text)', display: 'var(--display)', tahoma: 'Tahoma,sans-serif' };
    $$('#fontSeg button').forEach(function (b) {
      b.addEventListener('click', function () {
        cv.style.fontFamily = FONTS[b.dataset.f] || FONTS.text;
        $$('#fontSeg button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      });
    });
  })();

  /* template filter (design page) */
  (function () {
    var bar = $('#tplFilters'); if (!bar) return;
    var cards = $$('#tplAll .tpl');
    $$('button', bar).forEach(function (b) {
      b.addEventListener('click', function () {
        $$('button', bar).forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        var cat = b.dataset.cat;
        cards.forEach(function (c) { c.hidden = !(cat === '*' || c.dataset.cat === cat); });
      });
    });
  })();

  /* faq search */
  (function () {
    var input = $('#faqQ'), box = $('#faqAll'); if (!input || !box) return;
    var none = $('.faq-none', box.parentNode);
    input.addEventListener('input', function () {
      var q = input.value.trim(), any = false;
      $$('.faq-group', box).forEach(function (g) {
        var shown = 0;
        $$('details', g).forEach(function (d) {
          var hit = !q || d.textContent.indexOf(q) !== -1;
          d.hidden = !hit; if (hit) shown++;
        });
        g.hidden = shown === 0; if (shown) any = true;
      });
      if (none) none.hidden = any;
    });
  })();

  /* supported industries filter */
  (function () {
    var search = $('[data-ind-search]'), grid = $('[data-ind-grid]'); if (!grid) return;
    var cards = $$('.ind-card', grid), empty = $('[data-ind-empty]'), sector = 'all';
    function paint() {
      var q = (search ? search.value : '').trim(), n = 0;
      cards.forEach(function (c) {
        var ok = (sector === 'all' || c.dataset.sector === sector) && (!q || c.dataset.name.indexOf(q) !== -1);
        c.hidden = !ok; if (ok) n++;
      });
      if (empty) empty.hidden = n > 0;
    }
    if (search) search.addEventListener('input', paint);
    $$('[data-ind-tab]').forEach(function (b) {
      b.addEventListener('click', function () {
        sector = b.dataset.indTab;
        $$('[data-ind-tab]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        paint();
      });
    });
  })();
})();
