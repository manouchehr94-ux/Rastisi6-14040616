"""Background-ownership audit (QA tooling, not runtime).

For every ``.rsec`` section the page renders, measure how much of the section's visible area is actually painted by the
fill the merchant chose in «پس‌زمینه این بخش» — as opposed to being hidden under an inner component surface.

``MEASURE_JS`` samples a grid across each section; for every sample point it walks from the topmost element up to the
section wrapper and asks "which element paints this pixel's background?". A point is *owned by the section fill* when the walk
reaches the wrapper (or its edge-to-edge bleed layer) without meeting an inner element that paints an opaque background
colour / image. ``coverage`` is the share of such points.

``classify`` turns two measurements (the same section with #FFFFFF and with #0057FF) into the verdicts used in the report."""

BLUE = "#0057FF"
WHITE = "#FFFFFF"

MEASURE_JS = """(args)=>{
  const out = {};
  const want = args && args.fill ? args.fill : null;           // the colour the merchant chose, e.g. [0,87,255]
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(',').map(s => parseFloat(s)); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const near = (c) => want && c && Math.abs(c.r - want[0]) < 3 && Math.abs(c.g - want[1]) < 3 && Math.abs(c.b - want[2]) < 3 && c.a > 0.9;
  const painterInfo = (el) => { const s = getComputedStyle(el); const c = parse(s.backgroundColor); const bi = s.backgroundImage || 'none'; const img = bi !== 'none' && (/url\\(/.test(bi) || !/^linear-gradient\\(rgba\\(0, 0, 0, 0\\), rgba\\(0, 0, 0, 0\\)\\), none$/.test(bi));  // an all-transparent overlay layer paints nothing
    return {paints: (c && c.a > 0.2) || img, colour: c, image: img}; };
  for (const sec of document.querySelectorAll('.rsec[data-section-id]')) {
    const id = sec.dataset.sectionId; const key = sec.dataset.sectionKey;
    const r = sec.getBoundingClientRect();
    if (r.height < 24 || r.width < 24) { out[id] = {key, empty: true, h: Math.round(r.height)}; continue; }
    const wrapperStyle = getComputedStyle(sec);
    const bleed = sec.querySelector(':scope > .rsec-bleed');
    const fill = parse((bleed ? getComputedStyle(bleed) : wrapperStyle).backgroundColor);
    const hmax = Math.min(r.height, 700);
    let own = 0, consumer = 0, total = 0, ringTotal = 0, ringOwn = 0; const inner = new Map(); let blueSeen = !!near(fill);
    for (let y = 4; y < hmax - 3; y += 12) {
      for (let x = 4; x < r.width - 3; x += 12) {
        const px = r.left + x, py = r.top + y;
        if (py < 0 || py > innerHeight) continue;
        const el = document.elementFromPoint(px, py);
        if (!el || !sec.contains(el)) continue;
        total++;
        const ring = x < 12 || y < 12 || x > r.width - 12 || y > hmax - 12;
        if (ring) ringTotal++;
        let outer = null;                                     // the OUTERMOST element below the wrapper that paints this pixel
        for (let e = el; e && e !== sec; e = e.parentElement) { if (painterInfo(e).paints) outer = e; }
        if (!outer) { own++; if (ring) ringOwn++; continue; }
        const info = painterInfo(outer);
        if (near(info.colour) && !info.image) { consumer++; blueSeen = true; if (ring) ringOwn++; continue; }
        inner.set(outer, (inner.get(outer) || 0) + 1);
      }
    }
    let dominant = null, dominantShare = 0;
    for (const [el, n] of inner) { const share = n / Math.max(total, 1); if (share > dominantShare) { dominantShare = share; dominant = el; } }
    const nm = (e) => e ? e.tagName.toLowerCase() + '.' + String(e.className || '').split(/\\s+/).filter(Boolean).slice(0, 2).join('.') : null;
    const dInfo = dominant ? painterInfo(dominant) : null;
    out[id] = {key, mode: sec.dataset.bgMode || null, bleed: !!bleed, h: Math.round(r.height), w: Math.round(r.width),
      fill: fill ? [fill.r, fill.g, fill.b, fill.a] : null, wrapperBg: wrapperStyle.backgroundColor,
      styleHasFill: want ? (sec.getAttribute('style') || '').toLowerCase().includes(want.hex) : false,
      coverage: total ? Math.round(1000 * (own + consumer) / total) / 10 : 0, ring: ringTotal ? Math.round(1000 * ringOwn / ringTotal) / 10 : 0,
      consumerShare: total ? Math.round(1000 * consumer / total) / 10 : 0, blueSeen,
      dominant: nm(dominant), dominantShare: Math.round(1000 * dominantShare) / 10, dominantIsMedia: !!(dInfo && dInfo.image), dominantIsCard: !!(dominant && (dominant.matches('.pcard,.promo-card,.tile,.brand-tile') || dominant.querySelector('img,video,picture'))),
      samples: total, overflowX: sec.scrollWidth - sec.clientWidth};
  }
  return out;
}"""


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def classify(white, blue, *, dominant_limit=50.0, frame_min=60.0):
    """Verdict for one section from its measurement with a white fill and with a blue fill.

    * PASS                    the chosen fill is visibly painted by the section (or by a primary surface that consumes it) and no single
                              inner opaque surface hides it;
    * HIDDEN BY INNER SURFACE one inner opaque panel covers >= ``dominant_limit`` % of the section: the fill survives only as a thin frame;
    * OVERRIDDEN BY CSS       the wrapper carries the fill inline but nothing paints it (a stylesheet wins);
    * NO CONSUMER             the colour changed nothing measurable (nothing in the section paints it);
    * PASS (CARD / MEDIA TILES) the dominant inner element is a product card / image tile — a component surface by design, the fill frames it;
    * PARTIAL ONLY            painted, but over less than ``frame_min`` % of the outer frame (parts of the edge are hidden)."""
    if blue.get("empty") or white.get("empty"):
        return "NO CONTENT"
    if not blue.get("blueSeen"):
        return "OVERRIDDEN BY CSS" if blue.get("styleHasFill") else "NO CONSUMER"
    # an inner product card / media tile is a component surface by design (the section fill frames it); it is reported
    # separately so the report never hides that the tile, not the fill, owns most of the pixels
    card = blue.get("dominantIsCard") or blue.get("dominantIsMedia")
    hidden = blue.get("dominantShare", 0) >= dominant_limit and not blue.get("dominantIsMedia")
    partial = blue.get("ring", 0) < frame_min and blue.get("coverage", 0) < 12
    if (hidden or partial) and card and blue.get("dominantShare", 0) >= 15:
        return "PASS (CARD / MEDIA TILES)"
    if hidden:
        return "HIDDEN BY INNER SURFACE"
    if partial:
        return "PARTIAL ONLY"
    return "PASS"
