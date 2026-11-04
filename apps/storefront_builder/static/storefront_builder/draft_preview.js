/* «پیش‌نمایش» (Draft customer view) — presentation only: no fetch, no storage, no write. Keeps the visitor inside the Draft view:
   an internal storefront link / search form is mapped to the matching Draft PAGE TYPE (home, listing, search, product, collection, cart) and opened
   here; anything else (checkout, account, add-to-cart, a domain page) is refused with a visible note — it never opens the published storefront. */
(function () {
  var script = document.currentScript;
  var base = script ? script.getAttribute('data-page-url') : '';
  var note = document.querySelector('[data-sfb-draft-note]');
  var timer = null;

  function say(text) {
    if (!note) return;
    note.textContent = text;
    note.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(function () { note.hidden = true; }, 5000);
  }

  function pageTypeFor(url) {
    var path = url.pathname.replace(/\/+$/, '') || '/';
    if (path === '/') return 'home';
    if (path === '/products') return url.searchParams.get('q') ? 'search' : 'listing';
    if (/^\/products\/[^/]+$/.test(path)) return 'product_detail';
    if (path === '/collections' || /^\/collections\/[^/]+$/.test(path)) return 'collection';
    if (path === '/cart') return 'cart';
    return '';
  }

  function go(type) { window.location.assign(base + '?page=' + encodeURIComponent(type)); }

  document.addEventListener('click', function (evt) {
    var a = evt.target.closest ? evt.target.closest('a[href]') : null;
    if (!a || evt.defaultPrevented) return;
    var href = a.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#' || /^(mailto|tel):/i.test(href)) return;
    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return; }
    if (url.origin !== window.location.origin) return;               // an external link (e.g. Instagram) behaves as for a customer
    if (url.pathname === window.location.pathname) return;
    evt.preventDefault();
    var type = pageTypeFor(url);
    if (type) { go(type); return; }
    say('این پیوند در پیش‌نمایش پیش‌نویس باز نمی‌شود؛ پیش‌نمایش فقط صفحه‌های اصلی، محصولات، جستجو، کالکشن و سبد را نشان می‌دهد.');
  }, true);

  document.addEventListener('submit', function (evt) {
    evt.preventDefault();
    var form = evt.target;
    var q = form && form.querySelector ? form.querySelector('input[name="q"]') : null;
    if (q && /\/products\/?$/.test(new URL(form.getAttribute('action') || '/products/', window.location.href).pathname)) { go('search'); return; }
    say('در پیش‌نمایش پیش‌نویس ثبت فرم، افزودن به سبد و ورود انجام نمی‌شود.');
  }, true);
})();
