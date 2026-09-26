(function () {
  function q(sel, root) { return (root || document).querySelector(sel); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function initOffer() {
    var offer = q('.elementor-element-493e643c .dina-offer-block > .owl-carousel');
    if (!offer) return;

    if (window.jQuery && jQuery.fn && typeof jQuery.fn.owlCarousel === 'function') {
      try {
        var $offer = jQuery(offer);
        if (!$offer.hasClass('owl-loaded')) {
          $offer.owlCarousel({
            rtl: true, nav: false, dots: false, loop: true, margin: 0,
            items: 1, autoplay: true, autoplayTimeout: 7500,
            autoplayHoverPause: false, mouseDrag: false, touchDrag: false
          });
        }
        return;
      } catch (e) { /* fall through to dependency-free replay */ }
    }

    var items = qa(':scope > .item', offer);
    if (!items.length) return;
    var idx = 0;
    offer.style.display = 'block';
    items.forEach(function (el, i) { el.style.display = i === 0 ? 'block' : 'none'; });
    window.setInterval(function () {
      items[idx].style.display = 'none';
      idx = (idx + 1) % items.length;
      items[idx].style.display = 'block';
    }, 7500);
  }

  function initSpecialOffer() {
    qa('.dina-special-box').forEach(function (box) {
      var slider = q('.owl-carousel.dina-special-slider', box);
      var nav = q('.dina-slider-nav', box);
      if (!slider) return;

      // This widget normally starts from Elementor's frontend hook.  Static
      // replay does not dispatch that hook, so initialize the captured Owl
      // slider directly using the exact settings from Dinakala's theme JS.
      if (window.jQuery && jQuery.fn && typeof jQuery.fn.owlCarousel === 'function') {
        try {
          var $slider = jQuery(slider);
          if (!$slider.hasClass('owl-loaded')) {
            var $nav = nav ? jQuery(nav) : undefined;
            $slider.owlCarousel({
              rtl: slider.getAttribute('data-dir') !== 'false',
              margin: 1,
              autoplay: slider.getAttribute('data-itemplay') !== 'false',
              autoplayTimeout: parseInt(slider.getAttribute('data-itemtime') || '5000', 10),
              autoplayHoverPause: slider.getAttribute('data-itemover') === 'true',
              animateOut: 'fadeOut',
              nav: false,
              pagination: false,
              loop: true,
              dotsContainer: $nav,
              responsive: {
                0: { items: 1, mouseDrag: true, touchDrag: true },
                1024: { items: 1, mouseDrag: false, touchDrag: false }
              }
            });
            if ($nav) {
              $nav.on('click', 'li', function () {
                $slider.trigger('to.owl.carousel', [jQuery(this).index(), 300]);
              });
            }
          }
          return;
        } catch (e) { /* fall through */ }
      }

      // Dependency-free fallback: show one captured offer and let the right
      // list switch it. This prevents the large blank 2/3 panel when Owl is
      // not initialized offline.
      var items = qa(':scope > .item', slider);
      if (!items.length) return;
      var navItems = nav ? qa(':scope > li', nav) : [];
      var current = 0;
      slider.style.display = 'block';
      slider.classList.add('offline-special-fallback');

      function show(i) {
        if (i < 0) i = items.length - 1;
        if (i >= items.length) i = 0;
        current = i;
        items.forEach(function (el, k) {
          el.style.display = (k === i ? 'flex' : 'none');
        });
        navItems.forEach(function (el, k) {
          el.classList.toggle('active', k === i);
        });
      }
      navItems.forEach(function (el, i) {
        el.addEventListener('click', function () { show(i); });
      });
      show(0);
      if (slider.getAttribute('data-itemplay') !== 'false') {
        window.setInterval(function () { show(current + 1); }, parseInt(slider.getAttribute('data-itemtime') || '5000', 10));
      }
    });
  }

  function repairHeroHeight() {
    var con = q('.elementor-element-43f074b2 .dina-slider-con');
    if (!con) return;
    if (window.jQuery && jQuery.fn && con.classList.contains('owl-loaded')) {
      try { jQuery(con).trigger('refresh.owl.carousel'); } catch (e) {}
    }
  }

  function repairProductImages() {
    // Primary product images are authoritative. Some captured cards have a
    // second hover image; make sure the first frame is never hidden merely
    // because the original site's lazy/hover lifecycle did not fire offline.
    qa('.dina-img-con').forEach(function (con) {
      var imgs = qa('img', con);
      if (!imgs.length) return;
      var primary = imgs.find(function (im) { return !im.classList.contains('dina-second-img'); }) || imgs[0];
      primary.style.opacity = '1';
      primary.style.visibility = 'visible';
      primary.style.display = 'block';
      primary.addEventListener('error', function () {
        var second = imgs.find(function (im) { return im.classList.contains('dina-second-img'); });
        if (second) {
          primary.style.display = 'none';
          second.style.opacity = '1';
          second.style.visibility = 'visible';
          second.style.position = 'static';
        }
      }, { once: true });
    });
  }

  function start() {
    initOffer();
    initSpecialOffer();
    repairProductImages();
    repairHeroHeight();
    window.setTimeout(repairHeroHeight, 500);
    window.setTimeout(repairHeroHeight, 1500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
