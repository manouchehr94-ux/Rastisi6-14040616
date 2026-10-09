/*
 * RastiSi runtime contrast probe (injected into a page by tools/contrast_audit).
 *
 * The probe ONLY gathers raw facts from the live, laid-out DOM:
 *   - the computed foreground colour of every visible piece of text,
 *   - the stack of paint layers behind it at the text's real screen position
 *     (resolved with document.elementsFromPoint, so absolutely-positioned
 *     scrims, sibling overlays, images, gradients and ::before/::after covers
 *     are seen — not just ancestor background-colors),
 *   - font size / weight (for the WCAG "large text" threshold).
 * It deliberately does NOT compute a contrast ratio: all alpha compositing and
 * WCAG math happens in Python through apps/core/color_utils.py, the one
 * canonical implementation, so the audit and the product can never disagree.
 *
 * Layers are returned top -> bottom as one of:
 *   {t:'c', c:[r,g,b,a]}           solid colour (alpha already multiplied by
 *                                    the element's cumulative CSS opacity)
 *   {t:'g', s:[[r,g,b,a], ...]}    gradient (every colour stop)
 *   {t:'i'}                        image / video / canvas: unknown pixels
 * and always end in an opaque layer (the canvas is white if nothing else).
 */
(() => {
  if (window.__contrastProbe) return;

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION', 'OPTGROUP', 'HEAD', 'TITLE', 'META', 'LINK']);
  const MEDIA_TAGS = new Set(['IMG', 'VIDEO', 'CANVAS', 'PICTURE', 'IFRAME', 'OBJECT', 'EMBED']);
  const INTERACTIVE_SELECTOR = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea', 'summary',
    '[role=button]', '[role=tab]', '[role=menuitem]', '[role=option]', '[role=switch]',
    '[role=checkbox]', '[role=radio]', '[role=link]', '[tabindex]:not([tabindex="-1"])',
    'label[for]', '[onclick]', '[data-action]', '[data-toggle]', '[data-open]',
  ].join(',');

  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const colourCache = new Map();

  /** Any CSS colour string -> [r, g, b, a(0..1)] (canvas handles color-mix/oklch/lab/…). */
  function parseColour(value) {
    if (!value) return [0, 0, 0, 0];
    const cached = colourCache.get(value);
    if (cached) return cached;
    let out;
    const m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(value);
    if (m) {
      let a = 1;
      if (m[4] !== undefined) a = m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
      out = [parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3]), a];
    } else if (value === 'transparent') {
      out = [0, 0, 0, 0];
    } else {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = '#000';
      ctx.fillStyle = value;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      out = [d[0], d[1], d[2], d[3] / 255];
    }
    colourCache.set(value, out);
    return out;
  }

  const opacityCache = new WeakMap();
  function cumulativeOpacity(el) {
    if (!el || el.nodeType !== 1) return 1;
    const hit = opacityCache.get(el);
    if (hit !== undefined) return hit;
    const own = parseFloat(getComputedStyle(el).opacity);
    const value = (Number.isNaN(own) ? 1 : own) * cumulativeOpacity(el.parentElement);
    opacityCache.set(el, value);
    return value;
  }

  function scaleAlpha(rgba, k) {
    return [rgba[0], rgba[1], rgba[2], rgba[3] * k];
  }

  /** colour stops of a CSS gradient string (computed values are rgb()/rgba()). */
  function gradientStops(image) {
    const stops = [];
    const re = /rgba?\([^)]*\)|color\([^)]*\)|(?:ok)?l(?:ab|ch)\([^)]*\)|hsla?\([^)]*\)/g;
    let m;
    while ((m = re.exec(image)) !== null) stops.push(parseColour(m[0]));
    return stops;
  }

  /** Split on commas / whitespace that are not inside parentheses. */
  function splitTop(str, sep) {
    const out = [];
    let depth = 0;
    let cur = '';
    for (const ch of str) {
      if (ch === '(') depth += 1;
      if (ch === ')') depth -= 1;
      if (depth === 0 && (sep === ',' ? ch === ',' : /\s/.test(ch))) {
        if (cur.trim()) out.push(cur.trim());
        cur = '';
      } else cur += ch;
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }

  /** CSS background-image value -> top-level layer strings (first = topmost). */
  function imageLayers(value) {
    return splitTop(value, ',');
  }

  function mixRgba(a, b, f) {
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f];
  }

  /**
   * Colour of a linear-gradient at viewport point (x, y) of element `el`, or null
   * when the gradient cannot be resolved exactly (radial / conic / repeating / odd
   * positions) — the caller then falls back to the conservative "any stop" bound.
   */
  function sampleLinearGradient(layer, el, x, y) {
    const m = /^linear-gradient\((.*)\)$/s.exec(layer);
    if (!m) return null;
    const args = splitTop(m[1], ',');
    let angle = 180;
    const first = args[0];
    const dir = /^to\s+(.+)$/.exec(first);
    const ang = /^(-?[\d.]+)(deg|grad|rad|turn)$/.exec(first);
    if (dir || ang) {
      args.shift();
      if (ang) {
        const v = parseFloat(ang[1]);
        angle = ang[2] === 'deg' ? v : ang[2] === 'grad' ? v * 0.9 : ang[2] === 'rad' ? v * 180 / Math.PI : v * 360;
      } else {
        const words = dir[1].split(/\s+/).sort().join(' ');
        const table = { top: 0, 'right top': 45, right: 90, 'bottom right': 135, bottom: 180, 'bottom left': 225, left: 270, 'left top': 315 };
        if (!(words in table)) return null;
        angle = table[words];
      }
    }
    const rect = el.getBoundingClientRect();
    const rad = angle * Math.PI / 180;
    const len = Math.abs(rect.width * Math.sin(rad)) + Math.abs(rect.height * Math.cos(rad));
    if (!len) return null;
    const stops = [];
    for (const arg of args) {
      const parts = splitTop(arg, ' ');
      const colour = parseColour(parts[0]);
      let pos = null;
      if (parts[1]) {
        if (parts[1].endsWith('%')) pos = parseFloat(parts[1]) / 100;
        else if (parts[1].endsWith('px')) pos = parseFloat(parts[1]) / len;
        else return null;
      }
      stops.push({ c: colour, pos });
    }
    if (stops.length < 2) return null;
    if (stops[0].pos === null) stops[0].pos = 0;
    if (stops[stops.length - 1].pos === null) stops[stops.length - 1].pos = 1;
    let i = 0;
    while (i < stops.length) {
      if (stops[i].pos === null) {
        let j = i;
        while (stops[j].pos === null) j += 1;
        const a0 = stops[i - 1].pos;
        const a1 = stops[j].pos;
        for (let k = i; k < j; k += 1) stops[k].pos = a0 + (a1 - a0) * (k - i + 1) / (j - i + 1);
        i = j;
      } else i += 1;
    }
    for (let k = 1; k < stops.length; k += 1) stops[k].pos = Math.max(stops[k].pos, stops[k - 1].pos);
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const t = ((x - cx) * Math.sin(rad) - (y - cy) * Math.cos(rad)) / len + 0.5;
    if (t <= stops[0].pos) return stops[0].c;
    if (t >= stops[stops.length - 1].pos) return stops[stops.length - 1].c;
    for (let k = 1; k < stops.length; k += 1) {
      if (t <= stops[k].pos) {
        const span = stops[k].pos - stops[k - 1].pos;
        const f = span > 0 ? (t - stops[k - 1].pos) / span : 1;
        return mixRgba(stops[k - 1].c, stops[k].c, f);
      }
    }
    return null;
  }

  function pseudoCovers(el, pseudo) {
    const cs = getComputedStyle(el, pseudo);
    if (!cs || cs.content === 'none' || cs.content === 'normal' || cs.display === 'none') return null;
    if (cs.position !== 'absolute' && cs.position !== 'fixed') return null;
    const fullInset = ['top', 'right', 'bottom', 'left'].every((p) => parseFloat(cs[p]) === 0);
    const full = (cs.width === '100%' || /^\d/.test(cs.width) && Math.abs(parseFloat(cs.width) - el.getBoundingClientRect().width) < 2)
      && (cs.height === '100%' || /^\d/.test(cs.height) && Math.abs(parseFloat(cs.height) - el.getBoundingClientRect().height) < 2);
    if (!fullInset && !full) return null;
    return cs;
  }

  function layersOf(el, out, x, y) {
    const cs = getComputedStyle(el);
    const k = cumulativeOpacity(el);
    // pseudo-element covers sit above the element's own background
    for (const pseudo of ['::after', '::before']) {
      const pcs = pseudoCovers(el, pseudo);
      if (!pcs) continue;
      const pk = k * (parseFloat(pcs.opacity) || 1);
      pushBackground(pcs, pk, out, el, x, y);
    }
    if (MEDIA_TAGS.has(el.tagName)) {
      out.push({ t: 'i' });
      return;
    }
    pushBackground(cs, k, out, el, x, y);
  }

  function pushBackground(cs, k, out, el, x, y) {
    const image = cs.backgroundImage;
    if (image && image !== 'none') {
      for (const layer of imageLayers(image)) {
        if (/^url\(|^image-set\(|^-webkit-image-set\(/i.test(layer)) {
          out.push({ t: 'i' });
        } else if (/gradient\(/i.test(layer)) {
          const exact = sampleLinearGradient(layer, el, x, y);
          const stops = exact ? [exact] : gradientStops(layer);
          if (stops.length) out.push({ t: 'g', s: stops.map((c) => scaleAlpha(c, k)), exact: !!exact });
        }
      }
    }
    const bg = parseColour(cs.backgroundColor);
    if (bg[3] > 0) out.push({ t: 'c', c: scaleAlpha(bg, k) });
  }

  /**
   * The page canvas. CSS propagates <body>'s background to the canvas when <html> has none, so a point
   * outside body's box (short body, overscroll area) still shows body's colour — not browser-default white.
   */
  function canvasLayer() {
    for (const el of [document.documentElement, document.body]) {
      const bg = parseColour(getComputedStyle(el).backgroundColor);
      if (bg[3] > 0) return { t: 'c', c: [bg[0], bg[1], bg[2], 1] };
    }
    return { t: 'c', c: [255, 255, 255, 1] };
  }

  function layerIsOpaque(layer) {
    if (layer.t === 'i') return true;
    if (layer.t === 'c') return layer.c[3] >= 0.999;
    return layer.s.every((c) => c[3] >= 0.999);
  }

  /** Paint layers behind (and including) `el` at viewport point (x, y), top -> bottom. */
  function layersAt(el, x, y) {
    const stack = document.elementsFromPoint(x, y);
    const idx = stack.indexOf(el);
    if (idx === -1) return null; // clipped / covered at this point
    const out = [];
    for (let i = idx; i < stack.length; i += 1) {
      layersOf(stack[i], out, x, y);
      if (out.length && layerIsOpaque(out[out.length - 1])) break;
    }
    if (!out.length || !layerIsOpaque(out[out.length - 1])) out.push(canvasLayer());
    return out;
  }

  function isVisible(el) {
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    return true;
  }

  function signature(el) {
    const cls = (el.getAttribute('class') || '').split(/\s+/).filter(Boolean)
      .filter((c) => !/^(is-|has-|js-|active$|open$|show$|hover$|focus$)/.test(c)).slice(0, 4).sort();
    let sig = el.tagName.toLowerCase();
    if (cls.length) sig += '.' + cls.join('.');
    const type = el.getAttribute('type');
    if (type) sig += `[type=${type}]`;
    const role = el.getAttribute('role');
    if (role) sig += `[role=${role}]`;
    return sig;
  }

  function path(el) {
    const parts = [];
    let cur = el;
    for (let i = 0; cur && cur.nodeType === 1 && i < 3; i += 1) {
      parts.unshift(signature(cur));
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function disabledState(el) {
    if (el.matches && el.matches(':disabled')) return true;
    return !!(el.closest && el.closest('[aria-disabled="true"], [disabled], fieldset:disabled'));
  }

  function stateFlags(el) {
    const flags = [];
    if (el.closest('[aria-selected="true"]')) flags.push('selected');
    if (el.closest('[aria-current]')) flags.push('current');
    if (el.closest('[aria-pressed="true"]')) flags.push('pressed');
    if (el.closest('[aria-expanded="true"]')) flags.push('expanded');
    if (el.matches && el.matches(':checked, :has(:checked)')) flags.push('checked');
    if (el.closest('.is-active, .active, .is-selected, .selected, .current')) flags.push('active-class');
    if (disabledState(el)) flags.push('disabled');
    if (el.closest('[aria-invalid="true"], .is-invalid, .has-error, .error')) flags.push('error');
    return flags;
  }

  function fgOf(el, cs) {
    const isSvg = el instanceof SVGElement;
    let raw = isSvg ? cs.fill : cs.color;
    const fill = cs.webkitTextFillColor;
    if (!isSvg && fill && fill !== raw && fill !== 'currentcolor') raw = fill;
    return parseColour(raw);
  }

  const HAS_WORD = /[\p{L}\p{N}]/u;
  const EMOJI_ONLY = /^[\s\p{Extended_Pictographic}\uFE0F\u200D\u20E3\p{Emoji_Modifier}]+$/u;

  function describe(el, text, fg, rect, points, extra) {
    const cs = getComputedStyle(el);
    return Object.assign({
      sel: signature(el),
      path: path(el),
      text: text.replace(/\s+/g, ' ').trim().slice(0, 48),
      fg: scaleAlpha(fg, cumulativeOpacity(el)),
      size: parseFloat(cs.fontSize),
      weight: parseInt(cs.fontWeight, 10) || 400,
      iconOnly: !HAS_WORD.test(text),
      flags: stateFlags(el),
      points,
    }, extra || {});
  }

  function samplePoints(rect) {
    const ys = rect.height > 8 ? [rect.top + 1.5, rect.top + rect.height / 2, rect.bottom - 1.5] : [rect.top + rect.height / 2];
    const pts = [];
    for (const f of [0.1, 0.5, 0.9]) for (const y of ys) pts.push([rect.left + rect.width * f, y]);
    return pts;
  }

  function inViewport(rect) {
    return rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;
  }

  function measure(el, text, rect, extra, fgOverride) {
    const cs = getComputedStyle(el);
    if (parseFloat(cs.fontSize) === 0) return null;
    const fg = fgOverride || fgOf(el, cs);
    if (fg[3] * cumulativeOpacity(el) <= 0.01) return null; // fully transparent text
    const points = [];
    for (const [x, y] of samplePoints(rect)) {
      if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) continue;
      const layers = layersAt(el, x, y);
      if (layers) points.push(layers);
    }
    if (!points.length) return null;
    return describe(el, text, fg, rect, points, extra);
  }

  /** Collect every visible text / control-value item under `root`. */
  function collect(root, options) {
    const opts = Object.assign({ maxItems: 4000 }, options || {});
    const scope = root || document.body;
    const candidates = [];

    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue;
      if (!text || !text.trim()) continue;
      if (EMOJI_ONLY.test(text)) continue;
      const el = node.parentElement;
      if (!el || SKIP_TAGS.has(el.tagName) || el.closest('option, script, style, noscript, template')) continue;
      if (!isVisible(el)) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = Array.from(range.getClientRects()).filter((r) => r.width >= 3 && r.height >= 3);
      if (!rects.length) continue;
      const rect = rects[0];
      const abs = rect.top + window.scrollY;
      candidates.push({ kind: 'text', el, text, rect, abs });
    }
    // form control values / placeholders (not text nodes)
    scope.querySelectorAll('input, textarea, select').forEach((el) => {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (['hidden', 'checkbox', 'radio', 'range', 'color', 'file', 'image'].includes(type)) return;
      if (!isVisible(el)) return;
      const rect = el.getBoundingClientRect();
      if (rect.width < 3 || rect.height < 3) return;
      candidates.push({ kind: 'control', el, rect, abs: rect.top + window.scrollY });
    });

    candidates.sort((a, b) => a.abs - b.abs);
    const items = [];
    let skippedCovered = 0;
    for (const cand of candidates) {
      if (items.length >= opts.maxItems) break;
      let rect = cand.rect;
      if (!inViewport(rect) || rect.top < 0 || rect.bottom > window.innerHeight) {
        window.scrollTo({ top: Math.max(0, cand.abs - window.innerHeight / 3), left: window.scrollX, behavior: 'instant' });
        if (cand.kind === 'text') {
          const r = document.createRange();
          const textNode = Array.from(cand.el.childNodes).find((n) => n.nodeType === 3 && n.nodeValue === cand.text);
          if (!textNode) continue;
          r.selectNodeContents(textNode);
          const rs = Array.from(r.getClientRects()).filter((q) => q.width >= 3 && q.height >= 3);
          if (!rs.length) continue;
          rect = rs[0];
        } else {
          rect = cand.el.getBoundingClientRect();
        }
      }
      if (rect.right <= 0 || rect.left >= window.innerWidth) continue;
      if (cand.kind === 'text') {
        const item = measure(cand.el, cand.text, rect);
        if (item) items.push(item); else skippedCovered += 1;
      } else {
        const el = cand.el;
        const cs = getComputedStyle(el);
        const value = el.value || '';
        const placeholder = el.getAttribute('placeholder') || '';
        const isSelect = el.tagName === 'SELECT';
        if (value || isSelect) {
          const label = isSelect ? (el.selectedOptions[0] ? el.selectedOptions[0].text : '') : value;
          const it = measure(el, label || 'value', rect, { control: 'value' });
          if (it) items.push(it);
        }
        if (placeholder && !value) {
          const pcs = getComputedStyle(el, '::placeholder');
          const fg = parseColour(pcs.color);
          const it = measure(el, placeholder, rect, { control: 'placeholder' },
            [fg[0], fg[1], fg[2], fg[3] * (parseFloat(pcs.opacity) || 1)]);
          if (it) items.push(it);
        }
      }
    }
    return { items, candidates: candidates.length, skippedCovered };
  }

  /** Interactive controls under document, one per visual signature (max `perSignature`). */
  function interactiveTargets(perSignature) {
    const per = perSignature || 2;
    const seen = new Map();
    const out = [];
    const all = new Set(document.querySelectorAll(INTERACTIVE_SELECTOR));
    document.querySelectorAll('body *').forEach((el) => {
      if (all.has(el)) return;
      if (SKIP_TAGS.has(el.tagName)) return;
      const cs = getComputedStyle(el);
      if (cs.cursor === 'pointer' && el.parentElement && getComputedStyle(el.parentElement).cursor !== 'pointer') all.add(el);
    });
    all.forEach((el) => {
      if (!isVisible(el)) return;
      const rect = el.getBoundingClientRect();
      if (rect.width < 6 || rect.height < 6) return;
      const sig = signature(el) + (disabledState(el) ? '[disabled]' : '');
      const count = seen.get(sig) || 0;
      if (count >= per) return;
      seen.set(sig, count + 1);
      const idx = out.length;
      el.setAttribute('data-ca-target', String(idx));
      out.push({ idx, sig, text: (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 40),
        disabled: disabledState(el), tag: el.tagName.toLowerCase(), href: el.getAttribute('href') || '',
        type: el.getAttribute('type') || '', role: el.getAttribute('role') || '',
        opener: !!(el.matches('[hx-target*="modal" i], [data-open-modal], [data-modal-open], [data-modal], [aria-haspopup="dialog"], '
          + '.pcard-qv-trigger, .login-btn, [data-open-login], [data-drawer], [data-open-drawer], .mobile-menu-btn, '
          + '[data-open-settings], [data-r4-open], [data-open-template-gallery], [data-open-add-section]')),
        toggle: ['aria-expanded', 'aria-pressed', 'aria-selected', 'aria-haspopup', 'aria-controls', 'data-toggle',
          'data-bs-toggle', 'data-open', 'data-tab', 'data-target'].some((a) => el.hasAttribute(a)) });
    });
    return out;
  }

  /** Paint layers at a viewport point regardless of which element is under it. */
  function layersAtPoint(x, y) {
    const stack = document.elementsFromPoint(x, y);
    const out = [];
    for (let i = 0; i < stack.length; i += 1) {
      layersOf(stack[i], out, x, y);
      if (out.length && layerIsOpaque(out[out.length - 1])) break;
    }
    if (!out.length || !layerIsOpaque(out[out.length - 1])) out.push(canvasLayer());
    return out;
  }

  /** Backdrops adjacent to the control's box on each side (an outline is painted over THESE, not over the control). */
  function outsideBackdrops(el) {
    const r = el.getBoundingClientRect();
    const pts = [[r.left - 5, r.top + r.height / 2], [r.right + 5, r.top + r.height / 2],
      [r.left + r.width / 2, r.top - 5], [r.left + r.width / 2, r.bottom + 5]];
    const out = [];
    for (const [x, y] of pts) {
      if (x < 1 || y < 1 || x >= window.innerWidth - 1 || y >= window.innerHeight - 1) continue;
      const top = document.elementFromPoint(x, y);
      if (top && (top === el || el.contains(top))) continue;
      out.push(layersAtPoint(x, y));
    }
    return out;
  }

  /** Style facts used to decide whether a keyboard-focus indicator is perceivable. */
  function focusFacts(el) {
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const cx = Math.min(Math.max(rect.left + rect.width / 2, 0), window.innerWidth - 1);
    const cy = Math.min(Math.max(rect.top + rect.height / 2, 0), window.innerHeight - 1);
    return {
      sel: signature(el), path: path(el), text: (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 40),
      outlineStyle: cs.outlineStyle, outlineWidth: parseFloat(cs.outlineWidth) || 0,
      outlineColor: parseColour(cs.outlineColor), outlineOffset: parseFloat(cs.outlineOffset) || 0,
      boxShadow: cs.boxShadow, borderColor: cs.borderTopColor, borderWidth: parseFloat(cs.borderTopWidth) || 0,
      background: cs.backgroundColor, textDecoration: cs.textDecorationLine,
      backdrop: layersAt(el, cx, cy),
      outside: outsideBackdrops(el),
      shadowColours: (cs.boxShadow && cs.boxShadow !== 'none')
        ? (cs.boxShadow.match(/rgba?\([^)]*\)/g) || []).map(parseColour) : [],
    };
  }

  function withPointerEvents(fn) {
    const style = document.createElement('style');
    style.id = '__ca_pointer_events';
    style.textContent = '*, *::before, *::after { pointer-events: auto !important; }';
    document.head.appendChild(style);
    try { return fn(); } finally { style.remove(); }
  }

  function settle() {
    try {
      document.getAnimations().forEach((a) => {
        try { a.finish(); } catch (_e) { a.cancel(); }
      });
    } catch (_e) { /* old engines */ }
  }

  window.__contrastProbe = {
    collect(rootIndex, options) {
      return withPointerEvents(() => {
        settle();
        const root = rootIndex === null || rootIndex === undefined
          ? document.body
          : document.querySelector(`[data-ca-target="${rootIndex}"]`);
        if (!root) return { items: [], candidates: 0, skippedCovered: 0 };
        if (rootIndex !== null && rootIndex !== undefined) {
          root.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
        }
        return collect(root, options);
      });
    },
    interactiveTargets,
    focusFacts() {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      return withPointerEvents(() => { settle(); return Object.assign(focusFacts(el), { matchesFocusVisible: el.matches(':focus-visible') }); });
    },
    /** Facts while focused vs the same control blurred, then restore focus (keeps Tab order intact). */
    focusPair() {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      return withPointerEvents(() => {
        settle();
        document.querySelectorAll('[data-ca-target="focus"]').forEach((n) => n.removeAttribute('data-ca-target'));
        el.setAttribute('data-ca-target', 'focus');
        const focused = Object.assign(focusFacts(el), { matchesFocusVisible: el.matches(':focus-visible') });
        el.blur();
        settle();
        const rest = focusFacts(el);
        el.focus({ preventScroll: true });
        settle();
        return { focused, rest };
      });
    },
    restFacts(index) {
      const el = document.querySelector(`[data-ca-target="${index}"]`);
      return el ? withPointerEvents(() => focusFacts(el)) : null;
    },
    targetRect(index) {
      const el = document.querySelector(`[data-ca-target="${index}"]`);
      if (!el) return null;
      el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      const r = el.getBoundingClientRect();
      const x = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 2);
      const y = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 2);
      const top = document.elementFromPoint(x, y);
      return { x, y, reachable: !!top && (top === el || el.contains(top) || top.contains(el)) };
    },
    settle,
    pageFacts() {
      return { scrollHeight: document.documentElement.scrollHeight, width: window.innerWidth,
        overflowX: document.documentElement.scrollWidth > window.innerWidth + 1 };
    },
  };
})();
