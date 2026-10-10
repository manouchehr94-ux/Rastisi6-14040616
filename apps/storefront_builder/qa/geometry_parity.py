"""Browser geometry probes shared by the parity test and the dev CLI.

The probes read real layout from a live page (Playwright ``page`` or ``frame``):

* ``collect``        — document size, header/footer rects, every section's
                       (signature, x, y, width, height), the appearance token set;
* ``compare``        — Preview-vs-Published verdict (order, width <= 1px,
                       height <= 2px, no document overflow, same tokens);
* ``overflow_audit`` — document overflow with the canvas clip and the full-bleed
                       layers lifted, so the canvas clip can never hide a real
                       overflow defect.

Builder chrome (toolbars, add buttons, selection outlines) is intentionally NOT
measured: it is an overlay and must not influence storefront geometry. Only the
storefront sections (``.rsec``), the header and the footer are compared.
"""

from __future__ import annotations

WIDTH_TOLERANCE = 1.0
HEIGHT_TOLERANCE = 2.0

PROBE_JS = r"""
() => {
  const de = document.documentElement;
  const canvas = document.querySelector('main') || document.body;
  const cr = canvas.getBoundingClientRect();
  const R = (e) => {
    const r = e.getBoundingClientRect();
    return { x: +(r.left - cr.left).toFixed(1), y: +(r.top + window.scrollY).toFixed(1),
             w: +r.width.toFixed(1), h: +r.height.toFixed(1) };
  };
  const sig = (e) => {
    const s = [...e.children].find((c) => !c.matches('.rsec-bleed,.sfb-rsec-toolbar,.sfb-rsec-drag-handle'));
    // An empty section has no storefront child: its own classes may carry builder chrome, so it is just 'rsec-empty'.
    return s ? s.className.toString().trim().split(/\s+/).slice(0, 3).join('.') : 'rsec-empty';
  };
  const sections = [...document.querySelectorAll('.rsec')].map((e, i) => ({ order: i, sig: sig(e), ...R(e) }));
  const header = document.querySelector('header');
  const footer = document.querySelector('footer');
  const tokens = {};
  const style = de.getAttribute('style') || '';
  style.split(';').forEach((p) => {
    const i = p.indexOf(':');
    if (i > 0) tokens[p.slice(0, i).trim()] = p.slice(i + 1).trim();
  });
  [...de.attributes].forEach((a) => { if (a.name.startsWith('data-sfb-')) tokens[a.name] = a.value; });
  return {
    doc: { clientWidth: de.clientWidth, scrollWidth: de.scrollWidth, height: de.scrollHeight },
    header: header ? R(header) : null,
    footer: footer ? R(footer) : null,
    sections, tokens,
  };
}
"""

OVERFLOW_AUDIT_JS = r"""
() => {
  const style = document.createElement('style');
  style.textContent = 'main.sfb-storefront-canvas{overflow-x:visible!important}.rsec-bleed{display:none!important}';
  document.head.appendChild(style);
  const de = document.documentElement;
  const out = { clientWidth: de.clientWidth, scrollWidth: de.scrollWidth, offenders: [] };
  const vw = de.clientWidth;
  const canvas = document.querySelector('main');
  for (const e of document.querySelectorAll('main *, header *, footer *')) {
    if (e.closest('.sfb-rsec-toolbar,.sfb-rcontainer-toolbar,.sfb-cell-add-more,.sfb-empty-cell-add,svg')) continue;
    let scrolled = false;
    for (let n = e.parentElement; n && n !== canvas && n !== document.body; n = n.parentElement) {
      const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') { scrolled = true; break; }
    }
    if (scrolled) continue;
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.position === 'fixed') continue;
    const r = e.getBoundingClientRect();
    if (r.width && (r.right > vw + 1 || r.left < -1)) {
      out.offenders.push((e.tagName + '.' + (e.className || '').toString().split(' ')[0]).slice(0, 60) + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
    }
  }
  style.remove();
  out.offenders = out.offenders.slice(0, 12);
  return out;
}
"""


def settle(page, *, pause_ms: int = 60) -> None:
    """Scroll once through the page so lazy media loads, then wait for fonts."""
    page.evaluate("document.fonts && document.fonts.ready")
    height = page.evaluate("document.documentElement.scrollHeight")
    y = 0
    while y < height:
        page.evaluate(f"window.scrollTo(0,{y})")
        page.wait_for_timeout(pause_ms)
        y += 700
        height = page.evaluate("document.documentElement.scrollHeight")
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(400)


def collect(page) -> dict:
    return page.evaluate(PROBE_JS)


def overflow_audit(page) -> dict:
    return page.evaluate(OVERFLOW_AUDIT_JS)


def compare(published: dict, preview: dict, *, width_tol: float = WIDTH_TOLERANCE,
            height_tol: float = HEIGHT_TOLERANCE, scale: float = 1.0) -> list[str]:
    """Return a list of human-readable parity violations (empty == parity)."""
    problems: list[str] = []
    for label, probe in (("published", published), ("preview", preview)):
        doc = probe["doc"]
        if doc["scrollWidth"] != doc["clientWidth"]:
            problems.append(f"{label}: document horizontal overflow {doc['scrollWidth']} > {doc['clientWidth']}")
    if published["tokens"] != preview["tokens"]:
        diff = {k: (published["tokens"].get(k), preview["tokens"].get(k))
                for k in set(published["tokens"]) | set(preview["tokens"])
                if published["tokens"].get(k) != preview["tokens"].get(k)}
        problems.append(f"appearance tokens differ: {diff}")
    ps, vs = published["sections"], preview["sections"]
    if [s["sig"] for s in ps] != [s["sig"] for s in vs]:
        first = next((i for i, (a, b) in enumerate(zip(ps, vs)) if a["sig"] != b["sig"]), min(len(ps), len(vs)))
        problems.append(f"section order/signature differs at #{first}: "
                        f"published={ps[first]['sig'] if first < len(ps) else None} "
                        f"preview={vs[first]['sig'] if first < len(vs) else None} "
                        f"(counts {len(ps)}/{len(vs)})")
        return problems

    def delta(a, b, key, tol, label):
        d = abs(a[key] - b[key] / scale)
        if d > tol:
            problems.append(f"{label}: {key} delta {d:.1f} > {tol} ({a[key]} vs {b[key]})")

    for a, b in zip(ps, vs):
        tag = f"section #{a['order']} {a['sig']}"
        delta(a, b, "x", width_tol, tag)
        delta(a, b, "w", width_tol, tag)
        delta(a, b, "y", height_tol, tag)
        delta(a, b, "h", height_tol, tag)
    for name in ("header", "footer"):
        a, b = published.get(name), preview.get(name)
        if bool(a) != bool(b):
            problems.append(f"{name} present in only one render")
        elif a:
            for key, tol in (("x", width_tol), ("w", width_tol), ("h", height_tol)):
                delta(a, b, key, tol, name)
    if abs(published["doc"]["height"] - preview["doc"]["height"] / scale) > height_tol:
        problems.append(f"document height {published['doc']['height']} vs {preview['doc']['height']}")
    return problems
