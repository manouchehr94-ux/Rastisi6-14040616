(() => {
  const doc = document.documentElement;
  const body = document.body;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  doc.classList.add('rs-js');

  const revealSelectors = [
    '.rs-section-head > *',
    '.rs-intro > *',
    '.rs-gallery-card',
    '.rs-operation',
    '.rs-admin',
    '.rs-mobile > *',
    '.rs-journey-item',
    '.rs-pricing-strip > *',
    '.rs-home-faq > *',
    '.rs-feature',
    '.rs-plan-card',
    '.rs-pricing-principles > *',
    '.rs-contact > *',
    '.rs-faq-item',
    '.rs-about-panel',
    '.rs-about-principle',
    '.rs-bento-card',
    '.rs-flow-step',
    '.rs-final-inner > *',
    '.r-industries-page .industry-card'
  ];

  const revealNodes = [...new Set(revealSelectors.flatMap((selector) => [...document.querySelectorAll(selector)]))];
  revealNodes.forEach((node, index) => {
    node.dataset.rsReveal = '';
    node.style.setProperty('--rs-reveal-delay', `${Math.min(index % 6, 5) * 70}ms`);
  });

  if (reduceMotion) {
    revealNodes.forEach((node) => node.classList.add('is-visible'));
  } else if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    revealNodes.forEach((node) => observer.observe(node));
  } else {
    revealNodes.forEach((node) => node.classList.add('is-visible'));
  }

  const progress = document.querySelector('.rs-scroll-progress');
  const header = document.querySelector('.r-header');
  let ticking = false;
  const syncScroll = () => {
    ticking = false;
    const max = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    const ratio = Math.min(Math.max(window.scrollY / max, 0), 1);
    if (progress) progress.style.setProperty('--rs-page-progress', ratio);
    if (header) header.classList.toggle('is-scrolled', window.scrollY > 18);
  };
  window.addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(syncScroll);
  }, { passive: true });
  syncScroll();

  if (!reduceMotion) {
    document.querySelectorAll('.rs-hero-art, .rs-playground-stage').forEach((stage) => {
      stage.addEventListener('pointermove', (event) => {
        const rect = stage.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        stage.style.setProperty('--rs-pointer-x', x.toFixed(3));
        stage.style.setProperty('--rs-pointer-y', y.toFixed(3));
      });
      stage.addEventListener('pointerleave', () => {
        stage.style.setProperty('--rs-pointer-x', 0);
        stage.style.setProperty('--rs-pointer-y', 0);
      });
    });

    document.querySelectorAll('.rs-gallery-card, .rs-bento-card, .rs-plan-card').forEach((card) => {
      card.addEventListener('pointermove', (event) => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--rs-card-x', `${((event.clientX - rect.left) / rect.width * 100).toFixed(1)}%`);
        card.style.setProperty('--rs-card-y', `${((event.clientY - rect.top) / rect.height * 100).toFixed(1)}%`);
      });
    });
  }

  const studio = document.querySelector('[data-rs-design-studio]');
  if (studio) {
    const stage = studio.querySelector('[data-rs-stage]');
    const store = studio.querySelector('[data-rs-store]');
    const themeButtons = [...studio.querySelectorAll('[data-rs-theme]')];
    const paletteButtons = [...studio.querySelectorAll('[data-rs-palette]')];
    const deviceButtons = [...studio.querySelectorAll('[data-rs-device]')];
    const reset = studio.querySelector('[data-rs-reset]');

    const setPressed = (buttons, selected, attr) => {
      buttons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset[attr] === selected)));
    };

    const setTheme = (theme) => {
      store.dataset.theme = theme;
      setPressed(themeButtons, theme, 'rsTheme');
    };
    const setPalette = (palette) => {
      store.dataset.palette = palette;
      setPressed(paletteButtons, palette, 'rsPalette');
    };
    const setDevice = (device) => {
      stage.dataset.device = device;
      setPressed(deviceButtons, device, 'rsDevice');
    };

    themeButtons.forEach((button) => button.addEventListener('click', () => setTheme(button.dataset.rsTheme)));
    paletteButtons.forEach((button) => button.addEventListener('click', () => setPalette(button.dataset.rsPalette)));
    deviceButtons.forEach((button) => button.addEventListener('click', () => setDevice(button.dataset.rsDevice)));
    if (reset) reset.addEventListener('click', () => {
      setTheme('calm');
      setPalette('brand');
      setDevice('desktop');
    });

    const demoProducts = [...studio.querySelectorAll('[data-rs-demo-product]')];
    const cartCount = studio.querySelector('[data-rs-cart-count]');
    let count = 0;
    demoProducts.forEach((product) => {
      product.addEventListener('click', () => {
        count += 1;
        if (cartCount) {
          cartCount.textContent = new Intl.NumberFormat('fa-IR').format(count);
          cartCount.classList.remove('is-pop');
          requestAnimationFrame(() => cartCount.classList.add('is-pop'));
        }
        product.classList.remove('is-added');
        requestAnimationFrame(() => product.classList.add('is-added'));
      });
    });
  }

  const faqSearch = document.querySelector('[data-rs-faq-search]');
  if (faqSearch) {
    const faqItems = [...document.querySelectorAll('.rs-faq-list .rs-faq-item')];
    const faqCount = document.querySelector('[data-rs-faq-count]');
    const normalize = (value) => value.toLocaleLowerCase('fa-IR').replace(/ي/g, 'ی').replace(/ك/g, 'ک').trim();
    const applyFaqSearch = () => {
      const query = normalize(faqSearch.value);
      let visible = 0;
      faqItems.forEach((item) => {
        const matches = !query || normalize(item.textContent || '').includes(query);
        item.hidden = !matches;
        if (matches) visible += 1;
      });
      document.querySelectorAll('.rs-faq-list > .rs-eyebrow[id]').forEach((heading) => {
        let node = heading.nextElementSibling;
        let hasVisible = false;
        while (node && !node.matches('.rs-eyebrow[id]')) {
          if (node.matches('.rs-faq-item') && !node.hidden) hasVisible = true;
          node = node.nextElementSibling;
        }
        heading.hidden = !hasVisible;
      });
      if (faqCount) {
        faqCount.textContent = query ? `${new Intl.NumberFormat('fa-IR').format(visible)} پاسخ مرتبط` : '';
      }
    };
    faqSearch.addEventListener('input', applyFaqSearch);
    applyFaqSearch();
  }

  document.querySelectorAll('.rs-faq-item').forEach((item) => {
    item.addEventListener('toggle', () => {
      if (!item.open) return;
      item.parentElement?.querySelectorAll('.rs-faq-item[open]').forEach((other) => {
        if (other !== item && other.closest('.rs-home-faq')) other.removeAttribute('open');
      });
    });
  });
})();