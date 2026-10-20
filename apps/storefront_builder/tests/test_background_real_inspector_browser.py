"""«پس‌زمینه این بخش» through the REAL Inspector (Chromium + Playwright) — visible paint, not stored state.

The earlier audit set backgrounds through the ORM. This suite drives the actual Settings Workspace controls (the mode
select, the native colour input, the palette / pattern / media selects, the design «رنگ سطح» control) and then inspects
what the main Preview and the live mini-frame really PAINT:

* an ordinary ``product_section`` in every display mode (carousel / grid / campaign_band / catalog_grid), with and
  without a ``design.surface_color``: #FFFFFF → #0057FF must change the outer canvas, both frames identically;
* every background mode (theme / palette / palette_pattern / color / image / pattern / surface): persisted, painted, mini
  == main, kept on reload — no silent no-op;
* mode-then-colour in quick succession with a held (slow) first response: the LAST user value always wins;
* ownership: Background paints the section canvas, «رنگ سطح» only the internal cards — they never compete;
* every section type that offers the Background control answers the real Inspector (failures are classified).

Opt-in: ``SFB_BROWSER_TESTS=1 python manage.py test apps.storefront_builder.tests.test_background_real_inspector_browser``."""

import time
import unittest
import os

from django.db import transaction
from django.test import override_settings

from apps.storefront_builder import section_registry
from apps.storefront_builder.qa import background_contract as bgc
from apps.storefront_builder.services import section_structure_service as sss
from apps.storefront_builder.models import StorefrontSection

from .test_background_contract_browser import (
    BackgroundBrowserFixture, HOST, PREVIEW, PUBLIC_HOST, sync_playwright,
)

STUDIO = "/admin-portal/storefront-builder/r4/?page=home"
BLUE = "rgb(0, 87, 255)"

#: the outer canvas as painted: wrapper + its edge-to-edge layer + the first painted layer under the cards
CANVAS_JS = """(sid)=>{const e=document.querySelector('.rsec[data-section-id="'+sid+'"]'); if(!e) return null; const b=e.querySelector(':scope > .rsec-bleed');
  const cs=(x)=>x?getComputedStyle(x):null; const s=cs(e); const pc=e.querySelector('.pcard'); const band=e.querySelector('.product-campaign-band');
  return {mode:e.dataset.bgMode||null, d:e.dataset.d||null, style:(e.getAttribute('style')||''), wrapper:s.backgroundColor, wrapperImg:s.backgroundImage.slice(0,30),
    bleed:b?cs(b).backgroundColor:null, bleedImg:b?cs(b).backgroundImage.slice(0,30):null, band:band?cs(band).backgroundColor:null, bandImg:band?cs(band).backgroundImage.slice(0,30):null,
    card:pc?cs(pc).backgroundColor:null, overflowX:document.documentElement.scrollWidth-document.documentElement.clientWidth}}"""


def _signature(c):
    return (c["mode"], c["wrapper"], c["wrapperImg"], c["bleed"], c["bleedImg"], c["band"], c["bandImg"])


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class RealInspectorBackgroundTests(BackgroundBrowserFixture):
    def setUp(self):
        super().setUp()
        with transaction.atomic():
            self.products = sss.add_section(draft=self.draft, section_key="product_section", page_type="home")
        self._configure_products(display_mode="carousel", design=None)

    # ------------------------------------------------------------------------------------------------ helpers
    def _configure_products(self, *, display_mode, design, bleed=False):
        self.products.refresh_from_db()
        settings = {**self.products.settings, "display_mode": display_mode, "item_limit": 6, "title": "شش کارت",
                    "background": {"mode": "theme", "color": "", "media_asset_id": None, "pattern_slug": "", "palette_role": "",
                                   **({"bleed": True} if bleed else {})}}
        settings.pop("design", None)
        if design:
            settings["design"] = design
        self.products.settings = settings
        self.products.save()

    def _studio(self, section_id=None):
        context, page = self._page(STUDIO, authed=True, height=900)
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        self.requests = []
        page.on("request", lambda r: self.requests.append(r.post_data) if r.method == "POST" and "/r4/mutate/" in (r.url or "") else None)
        self._open_workspace(page, section_id or self.products.pk)
        return context, page

    def _canvas(self, frame, sid):
        return frame.evaluate(CANVAS_JS, str(sid))

    def _both(self, page, sid):
        frames = self._frames(page)
        self.assertGreaterEqual(len(frames), 2, "main Preview + live mini-frame")
        return self._canvas(frames[0], sid), self._canvas(frames[-1], sid)

    def _wait_canvas(self, page, sid, predicate_js, timeout=12000):
        """Wait until BOTH frames satisfy ``predicate_js(canvas)``; returns (main, mini)."""
        page.wait_for_function(
            """([sid, pred])=>{const f=eval(pred); const frames=[...document.querySelectorAll('iframe')].filter(x=>x.contentDocument&&x.contentDocument.querySelector('.rsec[data-section-id=\"'+sid+'\"]'));
              if(frames.length<2) return false; return frames.every(fr=>{const e=fr.contentDocument.querySelector('.rsec[data-section-id=\"'+sid+'\"]'); const b=e.querySelector(':scope > .rsec-bleed'); const band=e.querySelector('.product-campaign-band'); const cs=(x)=>x?fr.contentWindow.getComputedStyle(x):null;
                return f({style:e.getAttribute('style')||'',d:e.dataset.d||null,mode:e.dataset.bgMode||null,wrapper:cs(e).backgroundColor,bleed:b?cs(b).backgroundColor:null,band:band?cs(band).backgroundColor:null})})}""",
            arg=[str(sid), predicate_js], timeout=timeout)
        return self._both(page, sid)

    def _paint(self, page, sid, rgb):
        frame = self._frames(page)[0]
        frame.evaluate("(s)=>document.querySelector('.rsec[data-section-id=\"'+s+'\"]').scrollIntoView({block:'start'})", str(sid))
        page.wait_for_timeout(250)
        return frame.evaluate(bgc.MEASURE_JS, {"fill": rgb, "hex": "%02x%02x%02x" % tuple(rgb)}).get(str(sid), {"empty": True})

    def _set_mode(self, page, mode):
        page.select_option(".r4-background-picker [data-r4-background-mode]", mode)

    def _set_colour(self, page, value):
        page.fill(".r4-background-picker [data-r4-background-color]", value)

    def _pick_colour(self, page, sid, value, rgb_css):
        self._set_colour(page, value)
        return self._wait_canvas(page, sid, f"(c)=>(c.mode==='color'&&(c.style.toLowerCase().includes('{value.lower()}')))")

    def _persist_wait(self, page):
        page.wait_for_function("RastiSiR4.pendingWrites===0", timeout=10000)
        page.wait_for_timeout(300)
        page.wait_for_function("RastiSiR4.pendingWrites===0", timeout=10000)

    # ------------------------------------------------------------------- product_section × display modes × surface colour
    def test_product_section_custom_colour_through_the_real_inspector_is_visibly_painted_in_every_display_mode(self):
        failures = []
        for display_mode in ("carousel", "grid", "campaign_band", "catalog_grid"):
            for design in (None, {"surface_color": "#FFFFFF"}):
                self._configure_products(display_mode=display_mode, design=design)
                context, page = self._studio()
                try:
                    sid = self.products.pk
                    self._set_mode(page, "color")
                    page.wait_for_timeout(900)
                    white = None
                    self._pick_colour(page, sid, "#ffffff", "rgb(255, 255, 255)")
                    white = self._paint(page, sid, [255, 255, 255])
                    main, mini = self._pick_colour(page, sid, "#0057ff", BLUE)
                    blue = self._paint(page, sid, [0, 87, 255])
                    self._persist_wait(page)
                    verdict = bgc.classify(white, blue)
                    # the outer canvas (wrapper / bleed / band) really is the chosen colour, in BOTH frames, identically
                    owner = main["band"] if main["band"] not in (None, "rgba(0, 0, 0, 0)") and "campaign_band" == display_mode else (
                        main["bleed"] or main["wrapper"])
                    if owner != BLUE or _signature(main) != _signature(mini) or not verdict.startswith("PASS"):
                        failures.append((display_mode, bool(design), verdict, main, mini, blue.get("dominant")))
                    self.assertEqual(main["overflowX"], 0, (display_mode, main))
                    self.assertTrue(main["card"] in (None, "rgb(255, 255, 255)"), f"product cards must stay their own surface: {main}")
                finally:
                    context.close()
        self.assertEqual(failures, [], failures)

    # ------------------------------------------------------------------------------------------ every background mode
    def test_every_background_mode_through_the_real_inspector_is_persisted_painted_matched_and_survives_reload(self):
        from apps.content.models import MediaAsset  # noqa: F401  (the asset helper lives on the fixture)

        asset = self._asset()
        context, page = self._studio()
        sid = self.products.pk
        try:
            base_main, _ = self._both(page, sid)
            seen = {"theme": _signature(base_main)}

            def apply(mode, *, expect, prepare=None):
                self._set_mode(page, mode)
                page.wait_for_timeout(500)
                if prepare:
                    prepare()
                main, mini = self._wait_canvas(page, sid, f"(c)=>({expect})")
                self._persist_wait(page)
                self.assertEqual(_signature(main), _signature(mini), f"{mode}: mini != main")
                self.assertNotEqual(_signature(main), seen["last"], f"{mode} silently did nothing") if "last" in seen else None
                seen["last"] = _signature(main)
                seen[mode] = _signature(main)
                return main

            seen["last"] = seen["theme"]
            apply("palette", expect="c.mode==='palette'", prepare=lambda: page.select_option(".r4-background-picker [data-r4-background-palette-role]", "tone-2"))
            apply("palette_pattern", expect="c.mode==='palette_pattern'", prepare=lambda: page.select_option(".r4-background-picker [data-r4-background-pattern]", index=1))
            apply("color", expect="c.mode==='color'", prepare=lambda: self._set_colour(page, "#0057ff"))
            apply("image", expect="c.mode==='image'", prepare=lambda: page.select_option(".r4-background-picker [data-r4-background-media]", str(asset.pk)))
            apply("pattern", expect="c.mode==='pattern'", prepare=lambda: page.select_option(".r4-background-picker [data-r4-background-pattern]", index=1))
            apply("surface", expect="c.mode==='surface'")
            apply("theme", expect="c.mode===null")
            self.assertEqual(seen["theme"], seen["last"], "reverting to the theme must restore the original canvas")
            # a mode kept after reload: re-pick colour, reload, reopen
            self._set_mode(page, "color")
            self._set_colour(page, "#101828")
            self._wait_canvas(page, sid, "(c)=>c.mode==='color'&&c.style.toLowerCase().includes('#101828')")
            self._persist_wait(page)
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1500)
            self._open_workspace(page, sid)
            self.assertEqual(page.input_value(".r4-background-picker [data-r4-background-mode]"), "color")
            self.assertEqual(page.input_value(".r4-background-picker [data-r4-background-color]"), "#101828")
            main, mini = self._both(page, sid)
            self.assertEqual(main["wrapper"], "rgb(16, 24, 40)")
            self.assertEqual(_signature(main), _signature(mini))
        finally:
            context.close()
        self.products.refresh_from_db()
        self.assertEqual(self.products.settings["background"]["color"].lower(), "#101828")

    # -------------------------------------------------------------------------------- the last user value always wins
    def test_mode_then_colour_in_quick_succession_with_a_held_response_ends_on_the_last_value(self):
        context, page = self._studio()
        sid = self.products.pk
        try:
            # hold the FIRST write's response for 0.8 s (inside the page) while the later edits are already queued
            page.evaluate("""()=>{const of=window.fetch; let n=0; window.fetch=function(u,o){const p=of.apply(this,arguments);
              if(String(u&&u.url||u).includes('/r4/mutate/')&&(++n)===1) return p.then(r=>new Promise(res=>setTimeout(()=>res(r),800))); return p;}}""")
            self.requests.clear()
            self._set_mode(page, "color")              # 1. choose «رنگ دلخواه» …
            self._set_colour(page, "#ffffff")          # 2. … immediately pick hexes, one after the other
            self._set_colour(page, "#ef4444")
            self._set_colour(page, "#0057ff")
            self._wait_canvas(page, sid, "(c)=>c.mode==='color'&&c.style.toLowerCase().includes('#0057ff')", timeout=20000)
            self._persist_wait(page)
            page.wait_for_timeout(1200)
            main, mini = self._both(page, sid)
            self.assertEqual(main["wrapper"], BLUE, main)
            self.assertEqual(mini["wrapper"], BLUE, mini)
            sent = [r for r in self.requests if r and '"background"' in r]
            order = [__import__("json").loads(r)["mutation"]["patch"]["background"] for r in sent]
            self.assertEqual(order[-1]["color"].lower(), "#0057ff", order)
            revisions = [__import__("json").loads(r)["base_revision"] for r in sent]
            self.assertEqual(revisions, sorted(revisions), "writes must be sent in order, each on the previous response's revision")
        finally:
            context.close()
        self.products.refresh_from_db()
        self.assertEqual(self.products.settings["background"]["color"].lower(), "#0057ff")
        self.assertEqual(self.products.settings["background"]["mode"], "color")

    # ------------------------------------------------- the native colour picker's own event pattern (Chromium / Windows)
    def test_native_picker_event_pattern_sends_exactly_one_final_write_with_the_latest_hex(self):
        """The OS picker fires many ``input`` events while the thumb is dragged, then ONE ``change`` when it closes.
        Each ``input`` becomes a debounced synthetic change; the closing ``change`` finds the value already sent (or pending)."""
        context, page = self._studio()
        sid = self.products.pk
        try:
            self._set_mode(page, "color")
            page.wait_for_timeout(1000)
            self.requests.clear()
            events = page.evaluate("""()=>{const i=document.querySelector('.r4-background-picker [data-r4-background-color]'); const log=[];
              ['input','change'].forEach(n=>i.addEventListener(n,e=>log.push(n+':'+i.value)));
              const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
              for(const c of ['#101010','#303030','#5050a0','#2060d0','#0057ff']){ set.call(i,c); i.dispatchEvent(new Event('input',{bubbles:true})); }
              i.dispatchEvent(new Event('change',{bubbles:true}));      // the picker closing
              return log;}""")
            kinds = [e.split(":")[0] for e in events]
            # 5 native inputs; each also yields the editor's own synthetic change (input phase), then the closing change
            self.assertEqual((kinds.count("input"), kinds[-1], events[-1].split(":")[1]), (5, "change", "#0057ff"), events)
            self._wait_canvas(page, sid, "(c)=>c.mode==='color'&&c.style.toLowerCase().includes('#0057ff')")
            self._persist_wait(page)
            page.wait_for_timeout(800)
            writes = [__import__("json").loads(r)["mutation"]["patch"]["background"] for r in self.requests if r and '"background"' in r]
            self.assertEqual(len(writes), 1, writes)                  # one burst -> exactly one write …
            self.assertEqual(writes[0]["color"].lower(), "#0057ff")   # … carrying the LATEST hex (no lost final value)
            main, mini = self._both(page, sid)
            self.assertEqual((main["wrapper"], mini["wrapper"]), (BLUE, BLUE))
        finally:
            context.close()

    # --------------------------------------------------------------------------- Background vs «رنگ سطح» ownership
    def test_background_owns_the_canvas_and_surface_colour_owns_only_the_cards(self):
        # the reported failure: «رنگ سطح» (even plain white) used to repaint the whole section over the chosen Background
        self._configure_products(display_mode="carousel", design={"surface_color": "#FFFFFF"})
        context, page = self._studio()
        sid = self.products.pk
        try:
            self._set_mode(page, "color")
            main, mini = self._pick_colour(page, sid, "#0057ff", BLUE)
            self.assertEqual(main["wrapper"], BLUE, "surface colour must not repaint the section canvas")
            self.assertEqual(main["card"], "rgb(255, 255, 255)")
            # now recolour the CARDS through the real design control: the canvas keeps the Background
            page.evaluate("""()=>{const row=document.querySelector('[data-r4-design-prop="surface_color"]'); const sel=row.querySelector('[data-r4-color-token]');
              sel.value='custom'; sel.dispatchEvent(new Event('change',{bubbles:true}));
              const c=row.querySelector('[data-r4-color-custom]'); c.value='#ff0000'; c.dispatchEvent(new Event('change',{bubbles:true}));}""")
            main, mini = self._wait_canvas(page, sid, "(c)=>c.d&&c.d.includes('surface')&&c.style.toLowerCase().includes('--d-surface:#ff0000')")
            self.assertEqual(main["wrapper"], BLUE)
            self.assertEqual(main["card"], "rgb(255, 0, 0)")
            self.assertEqual(_signature(main), _signature(mini))
            # honest labels: the two controls say which rectangle they paint
            self.assertIn("رنگ یا تصویر پشت کل این بخش", page.inner_text("[data-rs-workspace]"))
            self.assertIn("رنگ کارت‌ها یا پنل‌های داخلی این بخش", page.inner_text("[data-rs-workspace]"))
        finally:
            context.close()

    # ------------------------------------------------------- every section that exposes the Background control
    def test_every_section_that_offers_a_background_answers_the_real_inspector(self):
        keys = [k for k, d in section_registry.SECTION_REGISTRY.items()
                if d.settings_schema and any(f.field_type == "background" for f in d.settings_schema.fields)]
        placed = {}
        for key in keys:
            if key == "product_section":
                placed[self.products.pk] = key
                continue
            if key == "amazing_offers":
                placed[self.offers.pk] = key
                continue
            try:
                placed[sss.add_section(draft=self.draft, section_key=key, page_type="home").pk] = key
            except sss.SectionStructureError:
                # a single-instance section the Ready Template already placed: audit that one
                existing = self.draft.sections.filter(section_key=key, page__page_type="home").first()
                if existing is not None:
                    placed[existing.pk] = key
        self.assertGreaterEqual(len(placed), 20)
        context, page = self._page(STUDIO, authed=True, height=900)
        report, failures = {}, []
        try:
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(2000)
            for sid, key in placed.items():
                frame = self._frames(page)[0]
                if not frame.evaluate("(s)=>!!document.querySelector('.rsec[data-section-id=\"'+s+'\"]')", str(sid)):
                    continue
                self._open_workspace(page, sid)
                self._set_mode(page, "color")
                page.wait_for_timeout(700)
                self._set_colour(page, "#ffffff")
                self._wait_canvas_any(page, sid, "#ffffff")
                white = self._paint(page, sid, [255, 255, 255])
                self._set_colour(page, "#0057ff")
                self._wait_canvas_any(page, sid, "#0057ff")
                blue = self._paint(page, sid, [0, 87, 255])
                self._persist_wait(page)
                verdict = bgc.classify(white, blue)
                report[(key, sid)] = verdict
                if blue.get("empty") or verdict == "NO CONTENT":
                    continue
                if not verdict.startswith("PASS"):
                    failures.append((key, sid, verdict, blue.get("dominant")))
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
        finally:
            context.close()
        print("real-Inspector background audit:", report)
        self.assertEqual(failures, [], failures)

    def _wait_canvas_any(self, page, sid, hex_value, timeout=12000):
        page.wait_for_function(
            """([sid, hex])=>{const fr=[...document.querySelectorAll('iframe')].filter(x=>x.contentDocument&&x.contentDocument.querySelector('.rsec[data-section-id=\"'+sid+'\"]'));
              return fr.length>=1&&fr.every(f=>(f.contentDocument.querySelector('.rsec[data-section-id=\"'+sid+'\"]').getAttribute('style')||'').toLowerCase().includes(hex))}""",
            arg=[str(sid), hex_value], timeout=timeout)
        page.wait_for_timeout(250)


# ---------------------------------------------------------------------------------------------------------------------
# Ink / contrast, legacy rows, campaign panel, Template-51 surface panels, Preview == Published (computed styles)
# ---------------------------------------------------------------------------------------------------------------------
INK_JS = """()=>{const sec=[...document.querySelectorAll('.rsec')].find(e=>{const h=e.querySelector('.sec-head h2,.product-campaign-heading h2'); return h&&h.textContent.trim()==='شش کارت'});
  const parse=(c)=>{ if(!c) return null; let m=c.match(/rgba?\\(([^)]+)\\)/); if(m){const p=m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};}
    m=c.match(/color\\(srgb ([^)]+)\\)/); if(m){const p=m[1].split(/[ \\/]+/).filter(Boolean).map(Number); return {r:p[0]*255,g:p[1]*255,b:p[2]*255,a:p.length>3?p[3]:1};} return null; };
  const over=(f,b)=>({r:f.r*f.a+b.r*(1-f.a),g:f.g*f.a+b.g*(1-f.a),b:f.b*f.a+b.b*(1-f.a),a:1});
  const lum=(c)=>{const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)}; return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b)};
  const ratio=(a,b)=>{const x=lum(a),y=lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05)};
  const white={r:255,g:255,b:255,a:1};
  const bgOf=(el)=>{ for(let e=el;e;e=e.parentElement){const c=parse(getComputedStyle(e).backgroundColor); if(c&&c.a>0.5) return c;} return white; };
  const ink=(el)=>{ if(!el) return null; const bg=bgOf(el); const fg=over(parse(getComputedStyle(el).color),bg); return {color:getComputedStyle(el).color,bg:getComputedStyle(el).backgroundColor===undefined?null:`rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,ratio:Math.round(ratio(fg,bg)*100)/100}; };
  const card=sec.querySelector('.pcard'); const q=(s)=>card?card.querySelector(s):null;
  const canvasEl=sec.querySelector(':scope > .rsec-bleed')||sec; const heading=sec.querySelector('.sec-head h2,.product-campaign-heading h2');
  const cb=parse(getComputedStyle(card||sec).backgroundColor);
  return {card:card?getComputedStyle(card).backgroundColor:null, name:ink(q('.name')), price:ink(q('.price .now')), muted:ink(q('.brand')||q('.old')),
    link:ink(sec.querySelector('.sec-head .more,.sec-head .btn,.product-campaign-heading a')), heading:ink(heading), wrapper:getComputedStyle(sec).backgroundColor, bleed:(sec.querySelector(':scope > .rsec-bleed')?getComputedStyle(sec.querySelector(':scope > .rsec-bleed')).backgroundColor:null),
    band:(sec.querySelector('.product-campaign-band')?getComputedStyle(sec.querySelector('.product-campaign-band')).backgroundColor:null),
    copy:(sec.querySelector('.product-campaign-copy')?getComputedStyle(sec.querySelector('.product-campaign-copy')).backgroundColor:null),
    productSection:(sec.querySelector('.product-section')?getComputedStyle(sec.querySelector('.product-section')).backgroundColor:null),
    flags:sec.dataset.d||''}}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class OwnershipInksAndLegacyLayoutTests(BackgroundBrowserFixture):
    def setUp(self):
        super().setUp()
        self.products = sss.add_section(draft=self.draft, section_key="product_section", page_type="home")

    def _configure(self, *, display_mode="carousel", background=None, design=None, **extra):
        self.products.refresh_from_db()
        settings = {**self.products.settings, "display_mode": display_mode, "item_limit": 6, "title": "شش کارت", **extra}
        settings["background"] = background or {"mode": "theme", "color": "", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}
        settings.pop("design", None)
        if design:
            settings["design"] = design
        self.products.settings = settings
        self.products.save()

    def _inks(self, path, *, authed=True):
        context, page = self._page(path, authed=authed)
        try:
            page.wait_for_selector(".pcard")
            page.evaluate("()=>{const s=[...document.querySelectorAll('.rsec')].find(e=>{const h=e.querySelector('.sec-head h2,.product-campaign-heading h2'); return h&&h.textContent.trim()==='شش کارت'}); s&&s.scrollIntoView()}")
            return page.evaluate(INK_JS)
        finally:
            context.close()

    # ----------------------------------------------------------------------------------- dark / light contrast matrix
    def test_card_inks_stay_accessible_on_light_and_dark_internal_surfaces_under_light_and_dark_backgrounds(self):
        def bg(colour):
            return {"mode": "color", "color": colour, "media_asset_id": None, "pattern_slug": "", "palette_role": ""}

        cases = (
            ("light background + dark surface", bg("#F4F5F9"), {"surface_color": "#101828"}),
            ("dark background + light surface", bg("#101828"), {"surface_color": "#FFFFFF"}),
            ("dark background + dark surface", bg("#0B1020"), {"surface_color": "#1F2937"}),
            ("blue background + palette-tone surface", bg("#0057FF"), {"surface_color": "token:tone-3"}),
            ("light background + brand surface", bg("#FFFFFF"), {"surface_color": "token:surface"}),
        )
        for label, background, design in cases:
            self._configure(background=background, design=design)
            inks = self._inks(PREVIEW)
            self.assertIsNotNone(inks["name"], label)
            for part in ("name", "price", "muted", "link"):
                if inks[part] is None:
                    continue
                self.assertGreaterEqual(inks[part]["ratio"], 4.5, f"{label}: {part} {inks[part]} card {inks['card']}")
            self.assertGreaterEqual(inks["heading"]["ratio"], 4.5, f"{label}: heading {inks['heading']}")

    def test_merchant_overrides_for_price_heading_and_text_still_win_over_the_surface_inks(self):
        self._configure(background={"mode": "color", "color": "#FFFFFF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""},
                        design={"surface_color": "#101828", "price_color": "#FFD60A", "heading_color": "#C2410C", "text_color": "#0F766E"})
        inks = self._inks(PREVIEW)
        self.assertEqual(inks["price"]["color"], "rgb(255, 214, 10)")      # explicit price colour on the dark card
        self.assertEqual(inks["heading"]["color"], "rgb(194, 65, 12)")     # explicit heading colour on the canvas
        self.assertEqual(inks["card"], "rgb(16, 24, 40)")
        self.assertEqual(inks["name"]["color"], "rgb(15, 118, 110)")       # explicit text colour

    # ------------------------------------------------------------------------------------------------ legacy row layout
    def test_a_product_section_in_a_legacy_row_respects_its_background_and_keeps_the_theme_card_without_one(self):
        reparent = """()=>{ const sec=[...document.querySelectorAll('.rsec')].find(e=>{const h=e.querySelector('.sec-head h2'); return h&&h.textContent.trim()==='شش کارت'});
          const row=document.createElement('div'); row.className='rsec-row'; const item=document.createElement('div'); item.className='rsec-row-item';
          sec.parentNode.insertBefore(row,sec); row.appendChild(item); item.appendChild(sec); return true }"""
        measure = "()=>{const sec=document.querySelector('.rsec-row-item > .rsec'); const ps=sec.querySelector(':scope > .product-section'); const b=sec.querySelector(':scope > .rsec-bleed');" \
                  "return {mode:sec.dataset.bgMode||null,wrapper:getComputedStyle(sec).backgroundColor,bleed:b?getComputedStyle(b).backgroundColor:null,box:getComputedStyle(ps).backgroundColor}}"
        results = {}
        for label, background, bleed in (
            ("color", {"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}, False),
            ("bleed", {"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": "", "bleed": True}, True),
            ("palette", {"mode": "palette", "color": "", "media_asset_id": None, "pattern_slug": "", "palette_role": "tone-2"}, False),
            ("theme", None, False),
        ):
            self._configure(background=background)
            context, page = self._page(PREVIEW, authed=True)
            try:
                page.evaluate(reparent)
                results[label] = page.evaluate(measure)
            finally:
                context.close()
        for label in ("color", "palette"):
            self.assertEqual(results[label]["box"], "rgba(0, 0, 0, 0)", f"{label}: the row painter hid the Background: {results[label]}")
        self.assertEqual(results["color"]["wrapper"], BLUE)
        self.assertEqual(results["bleed"]["bleed"], BLUE)
        self.assertEqual(results["bleed"]["box"], "rgba(0, 0, 0, 0)")
        self.assertNotEqual(results["theme"]["box"], "rgba(0, 0, 0, 0)")   # theme default: the legacy card look is unchanged

    # --------------------------------------------------------------------------------------------- campaign independence
    def test_campaign_panel_colour_is_independent_of_the_background_and_the_surface_colour(self):
        self._configure(display_mode="campaign_band", campaign_panel_title="هنر", campaign_panel_bg="#B91C1C",
                        background={"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""},
                        design={"surface_color": "#101828"})
        inks = self._inks(PREVIEW)
        self.assertEqual(inks["band"], BLUE)                        # the Background owns the band fill
        self.assertEqual(inks["copy"], "rgb(185, 28, 28)")          # the campaign panel keeps its own colour
        self.assertEqual(inks["card"], "rgb(16, 24, 40)")           # the surface colour owns the cards only
        for part in ("name", "price"):
            if inks[part]:
                self.assertGreaterEqual(inks[part]["ratio"], 4.5, (part, inks[part]))
        self._configure(display_mode="campaign_band", campaign_panel_title="هنر", campaign_panel_bg="#B91C1C",
                        background={"mode": "color", "color": "#101828", "media_asset_id": None, "pattern_slug": "", "palette_role": ""},
                        design={"surface_color": "#101828"})
        again = self._inks(PREVIEW)
        self.assertEqual((again["band"], again["copy"]), ("rgb(16, 24, 40)", "rgb(185, 28, 28)"))

    # ----------------------------------------------------------------------------------- Template-51 «surface» panels
    def test_background_mode_surface_panels_stay_controllable_and_cards_keep_their_own_surface(self):
        surface_bg = {"mode": "surface", "color": "", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}
        self._configure(background=surface_bg)
        base = self._inks(PREVIEW)
        self.assertNotEqual(base["wrapper"], "rgba(0, 0, 0, 0)")             # the Background's surface mode paints the panel
        self._configure(background=surface_bg, design={"surface_color": "#7C3AED"})
        coloured = self._inks(PREVIEW)
        self.assertEqual(coloured["wrapper"], "rgb(124, 58, 237)")           # the one surface colour recolours THE panel (merchant control kept)
        self.assertEqual(coloured["card"], base["card"])                     # cards inside keep their own surface (no blending)
        # switching the Background to an explicit colour hands the canvas to the Background; the surface colour then owns the cards
        self._configure(background={"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""},
                        design={"surface_color": "#7C3AED"})
        switched = self._inks(PREVIEW)
        self.assertEqual((switched["wrapper"], switched["card"]), (BLUE, "rgb(124, 58, 237)"))

    # ------------------------------------------------------------------------------------------ Preview == Published
    def test_ownership_and_inks_are_identical_in_preview_and_published(self):
        for label, background, design in (
            ("blue + white surface", {"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": "", "bleed": True}, {"surface_color": "#FFFFFF"}),
            ("white + dark surface", {"mode": "color", "color": "#FFFFFF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}, {"surface_color": "#101828"}),
            ("surface mode", {"mode": "surface", "color": "", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}, {"surface_color": "#7C3AED"}),
        ):
            self._configure(background=background, design=design)
            self._publish()
            preview = self._inks(PREVIEW)
            public = self._inks("/", authed=False)
            for key in ("card", "name", "price", "muted", "heading", "wrapper", "bleed", "flags"):
                self.assertEqual(preview[key], public[key], f"{label}: {key} differs between Preview and Published")
