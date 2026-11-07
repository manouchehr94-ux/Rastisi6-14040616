/* صفحه‌ی تعرفه (طراحیِ v2، بدونِ فریم‌ورک): انتخابگرِ دوره + تبِ پلن در مقایسه‌ی موبایل.
   بدونِ JS هم صفحه کامل خوانا است: دوره‌ی پیش‌فرض نمایش داده می‌شود، ماتریس و توضیح‌ها (<details>) باز/قابل‌باز شدن‌اند. */
(function () {
  var root = document.querySelector('[data-pricing]');
  if (!root) return;
  var period = root.getAttribute('data-initial');
  var buttons = root.querySelectorAll('.pz-seg [data-period]');
  var cards = root.querySelectorAll('.pz-tag[data-plan]');
  var matrix = root.querySelector('.pz-matrix');
  var tabs = root.querySelectorAll('.pz-tabs [data-tab]');

  function effective(card) {
    var offered = (card.getAttribute('data-offered') || '').split(',').filter(Boolean);
    return offered.indexOf(period) !== -1 ? period : card.getAttribute('data-default');
  }
  function render() {
    buttons.forEach(function (b) { b.setAttribute('aria-checked', String(b.getAttribute('data-period') === period)); });
    cards.forEach(function (card) {
      var eff = effective(card);
      card.querySelectorAll('[data-price]').forEach(function (el) { el.hidden = el.getAttribute('data-price') !== eff; });
      // every CTA that carries the plan (register / upgrade / «I already have a store») keeps the CHOSEN period; ``data-sep`` is the
      // separator for links whose plan lives inside an encoded ``next=`` parameter (login)
      card.querySelectorAll('a[data-base]').forEach(function (cta) {
        cta.setAttribute('href', cta.getAttribute('data-base') + (cta.getAttribute('data-sep') || '&period=') + encodeURIComponent(eff));
      });
      var note = card.querySelector('[data-note]');
      var offered = (card.getAttribute('data-offered') || '').split(',').filter(Boolean);
      if (note) note.hidden = !offered.length || offered.indexOf(period) !== -1;
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { period = b.getAttribute('data-period'); render(); });
  });
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      if (matrix) matrix.setAttribute('data-sel', t.getAttribute('data-tab'));
      tabs.forEach(function (o) { o.setAttribute('aria-selected', String(o === t)); });
    });
  });
  render();
})();
