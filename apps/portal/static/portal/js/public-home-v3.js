/*
 * RastiSi landing page (home) — v3 behaviour.
 * 1. Hero: a short, finite, decorative "builder" sequence (skipped for reduced motion).
 * 2. Live demo: rename / re-template / re-colour a sample store, desktop or mobile.
 *    Nothing is sent to the server or persisted — it is purely a demonstration.
 * 3. Admin-panel tabs (WAI-ARIA tabs pattern).
 */
(() => {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const LAYOUTS = { classic: 'ساده', editorial: 'مجله‌ای', compact: 'فشرده' };
  const PALETTES = { forest: 'سبز جنگلی', indigo: 'نیلی', copper: 'مسی', graphite: 'زغالی' };
  const DEVICES = { desktop: 'دسکتاپ', mobile: 'موبایل' };
  const DEFAULTS = { name: 'فروشگاه من', layout: 'classic', palette: 'forest', device: 'desktop' };

  const press = (buttons, attr, value) => {
    buttons.forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset[attr] === value));
    });
  };

  /* ───── Live demo ───── */
  const demo = document.querySelector('[data-rh-demo]');
  if (demo) {
    const form = demo.querySelector('form');
    const stage = demo.querySelector('[data-rh-stage]');
    const store = demo.querySelector('[data-rh-store] .rh-store');
    const nameInput = demo.querySelector('[data-rh-input-name]');
    const summary = demo.querySelector('[data-rh-summary]');
    const layoutButtons = [...demo.querySelectorAll('[data-rh-layout]')];
    const paletteButtons = [...demo.querySelectorAll('[data-rh-palette]')];
    const deviceButtons = [...demo.querySelectorAll('[data-rh-device]')];
    const state = { ...DEFAULTS };

    const render = () => {
      const name = state.name.trim() || 'نام فروشگاه';
      store.dataset.layout = state.layout;
      store.dataset.palette = state.palette;
      stage.dataset.device = state.device;
      store.querySelectorAll('[data-rh-name]').forEach((node) => { node.textContent = name; });
      press(layoutButtons, 'rhLayout', state.layout);
      press(paletteButtons, 'rhPalette', state.palette);
      press(deviceButtons, 'rhDevice', state.device);
      if (summary) {
        summary.textContent = `قالب ${LAYOUTS[state.layout]} · ${PALETTES[state.palette]} · ${DEVICES[state.device]}`;
      }
    };

    if (form) form.addEventListener('submit', (event) => event.preventDefault());
    nameInput.addEventListener('input', () => { state.name = nameInput.value; render(); });
    layoutButtons.forEach((button) => button.addEventListener('click', () => { state.layout = button.dataset.rhLayout; render(); }));
    paletteButtons.forEach((button) => button.addEventListener('click', () => { state.palette = button.dataset.rhPalette; render(); }));
    deviceButtons.forEach((button) => button.addEventListener('click', () => { state.device = button.dataset.rhDevice; render(); }));
    demo.querySelector('[data-rh-reset]').addEventListener('click', () => {
      Object.assign(state, DEFAULTS);
      nameInput.value = DEFAULTS.name;
      render();
    });
    render();
  }

  /* ───── Hero builder: one finite orchestrated moment ───── */
  const hero = document.querySelector('[data-rh-hero]');
  if (hero && !reduceMotion) {
    const store = hero.querySelector('[data-rh-hero-store] .rh-store');
    const nameField = hero.querySelector('[data-rh-hero-name]');
    const layoutChips = [...hero.querySelectorAll('[data-rh-hero-layout]')];
    const paletteDots = [...hero.querySelectorAll('[data-rh-hero-palette]')];
    const scenes = [
      { name: 'خانه نمونه', layout: 'editorial', palette: 'copper' },
      { name: 'بوتیک من', layout: 'compact', palette: 'indigo' },
      { name: 'فروشگاه من', layout: 'classic', palette: 'forest' },
    ];
    const timers = [];
    const later = (fn, ms) => timers.push(window.setTimeout(fn, ms));

    const setName = (text) => {
      nameField.textContent = text;
      store.querySelectorAll('[data-rh-name]').forEach((node) => { node.textContent = text; });
    };
    const setLook = (scene) => {
      store.dataset.layout = scene.layout;
      store.dataset.palette = scene.palette;
      layoutChips.forEach((chip) => chip.classList.toggle('is-on', chip.dataset.rhHeroLayout === scene.layout));
      paletteDots.forEach((dot) => dot.classList.toggle('is-on', dot.dataset.rhHeroPalette === scene.palette));
    };
    const typeName = (text, done) => {
      let i = 0;
      const tick = () => {
        i += 1;
        setName(text.slice(0, i));
        if (i < text.length) later(tick, 55); else done();
      };
      setName('');
      later(tick, 120);
    };
    const play = (index) => {
      if (index >= scenes.length) return;
      const scene = scenes[index];
      setLook(scene);
      typeName(scene.name, () => later(() => play(index + 1), 1700));
    };

    const start = () => later(() => play(0), 1400);
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        start();
      }, { threshold: 0.4 });
      observer.observe(hero);
    } else {
      start();
    }
    // Stop the sequence as soon as the visitor goes to the real demo.
    document.querySelectorAll('a[href="#demo"]').forEach((link) => link.addEventListener('click', () => {
      timers.forEach((id) => window.clearTimeout(id));
    }));
  }

  /* ───── Admin panel tabs ───── */
  document.querySelectorAll('[data-rh-tabs]').forEach((root) => {
    const tabs = [...root.querySelectorAll('[role="tab"]')];
    const select = (tab, focus) => {
      tabs.forEach((other) => {
        const active = other === tab;
        other.setAttribute('aria-selected', String(active));
        other.tabIndex = active ? 0 : -1;
        const panel = document.getElementById(other.getAttribute('aria-controls'));
        if (panel) panel.hidden = !active;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab, false));
      tab.addEventListener('keydown', (event) => {
        // RTL: ArrowLeft moves to the next tab, ArrowRight to the previous.
        const step = { ArrowLeft: 1, ArrowRight: -1 }[event.key];
        if (step) {
          event.preventDefault();
          select(tabs[(index + step + tabs.length) % tabs.length], true);
        } else if (event.key === 'Home') {
          event.preventDefault();
          select(tabs[0], true);
        } else if (event.key === 'End') {
          event.preventDefault();
          select(tabs[tabs.length - 1], true);
        }
      });
    });
  });
})();
