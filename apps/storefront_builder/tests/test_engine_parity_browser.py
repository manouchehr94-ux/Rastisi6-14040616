"""Real-browser geometry parity for the Template 51 engine stabilization (Chromium + Playwright).

Preview (the Draft, with builder chrome) and Published (the public storefront) must lay the storefront out
IDENTICALLY — section order, x / y / width / height, document height, header / footer rects, the appearance token
set — at 1440 / 1024 / 768 / 390, with real classic scrollbars, and the document must never scroll horizontally.
The overflow audit lifts the canvas clip and the bleed layers first, so the canvas clip can never hide a genuine
overflow defect. The Design Studio iframe and the atomic preview refresh are checked as well.

Opt-in (needs a browser, runs a live server): ``SFB_BROWSER_TESTS=1 python manage.py test
apps.storefront_builder.tests.test_engine_parity_browser``. Chromium path: ``SFB_BROWSER_PATH``; screenshots:
``SFB_SCREENSHOT_DIR``."""

import os
import unittest
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import MediaAsset
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.qa import geometry_parity as gp
from apps.storefront_builder.services import layout_service, preset_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
HOST = f"sfb-parity.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"   # Design Studio / admin host
PUBLIC_HOST = "sfb-parity-public.example.com"                 # the published storefront
WIDTHS = (1440, 1024, 768, 390)
BROWSER_CANDIDATES = (
    os.environ.get("SFB_BROWSER_PATH", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium",
)


def _browser_path():
    for path in BROWSER_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class EngineGeometryParityBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1, MAP {PUBLIC_HOST} 127.0.0.1"],
                  "ignore_default_args": ["--hide-scrollbars"]}  # real classic scrollbars
        path = _browser_path()
        if path:
            launch["executable_path"] = path
        try:
            cls.browser = cls.pw.chromium.launch(**launch)
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            super().tearDownClass()
            raise unittest.SkipTest(f"Chromium is not available: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه پاریتی", slug="sfb-parity-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain=HOST.split(".")[0],
        )
        ShopSettings.provision_for(self.store)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="parity-vendor")
        roots = [Category.objects.create(store=self.store, name=f"دسته {i}", slug=f"root-{i}", order=i, is_active=True)
                 for i in range(3)]
        children = [Category.objects.create(store=self.store, name=f"زیر {i}-{j}", slug=f"kid-{i}{j}", order=j,
                                            parent=roots[i], is_active=True) for i in range(3) for j in range(2)]
        for n in range(24):
            Product.objects.create(
                store=self.store, vendor=vendor, category=(roots + children)[n % 9], name=f"کالای شماره {n}",
                slug=f"parity-{n}", sku=f"PAR-{n}", price=Decimal(100000 + n * 1000),
                discount_percent=15 if n % 3 == 0 else 0,
                stock=5, status=Product.Status.ACTIVE,
            )
        user = get_user_model().objects.create_user(username="09125550777", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        draft = layout_service.get_or_create_draft(self.store, user=user)
        layout = layout_service.get_or_create_layout(self.store)
        layout.r4_editor_enabled = True
        layout.save(update_fields=["r4_editor_enabled"])
        preset_service.apply_preset(draft, lpr.get_layout_preset("stationery_spectrum"))
        layout_service.publish(self.store)
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="09125550777", password="pass12345")
        port = self.live_server_url.rsplit(":", 1)[1]
        self.base = f"http://{HOST}:{port}"
        self.public_base = f"http://{PUBLIC_HOST}:{port}"
        self.cookie = {"name": "sessionid", "value": client.cookies["sessionid"].value, "domain": HOST, "path": "/"}
        self.user = user

    # -------------------------------------------------------------------------------------------- helpers
    def _page(self, width, path, *, authed=False, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="fa-IR")
        if authed:
            context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(f"{self.base if authed else self.public_base}{path}", wait_until="networkidle")
        gp.settle(page)
        return context, page

    def _probe(self, width, path, **kwargs):
        context, page = self._page(width, path, **kwargs)
        try:
            return gp.collect(page), gp.overflow_audit(page)
        finally:
            context.close()

    def _shot(self, name, width=1440, path="/", **kwargs):
        directory = os.environ.get("SFB_SCREENSHOT_DIR")
        if not directory:
            return
        Path(directory).mkdir(parents=True, exist_ok=True)
        context, page = self._page(width, path, **kwargs)
        try:
            page.screenshot(path=str(Path(directory) / f"{name}.png"), full_page=True)
        finally:
            context.close()

    # ------------------------------------------------------------------------------------------- the checks
    def test_preview_matches_published_at_every_width_with_zero_document_overflow(self):
        for width in WIDTHS:
            published, published_audit = self._probe(width, "/")
            preview, preview_audit = self._probe(width, "/admin-portal/storefront-builder/preview/?page=home", authed=True)
            problems = gp.compare(published, preview)
            self.assertEqual(problems, [], f"{width}px: {problems[:6]}")
            for label, audit in (("published", published_audit), ("preview", preview_audit)):
                self.assertEqual(audit["scrollWidth"], audit["clientWidth"],
                                 f"{width}px {label}: hidden overflow (clip lifted) {audit['offenders']}")
                self.assertEqual(audit["offenders"], [], f"{width}px {label}")

    def test_document_has_no_horizontal_scroll_range_at_all(self):
        for width in WIDTHS:
            context, page = self._page(width, "/")
            try:
                moved = page.evaluate("()=>{scrollTo(-600,0);const a=scrollX;scrollTo(600,0);const b=scrollX;scrollTo(0,0);return [a,b]}")
                self.assertEqual(moved, [0, 0], f"{width}px")
            finally:
                context.close()

    def test_bleed_layers_reach_the_canvas_edges_exactly_in_public_and_preview(self):
        script = """()=>{const m=document.querySelector('main').getBoundingClientRect();
          return [...document.querySelectorAll('.rsec-bleed')].map(e=>{const r=e.getBoundingClientRect();
          const l=Math.max(r.left,m.left),rt=Math.min(r.right,m.right);return {l:Math.round(l-m.left),rt:Math.round(m.right-rt),w:Math.round(r.width)}})}"""
        for width in WIDTHS:
            for path, authed in (("/", False), ("/admin-portal/storefront-builder/preview/?page=home", True)):
                context, page = self._page(width, path, authed=authed)
                try:
                    layers = page.evaluate(script)
                finally:
                    context.close()
                self.assertEqual(len(layers), 5, (width, path))
                for layer in layers:
                    self.assertLessEqual(layer["l"], 1, (width, path, layer))   # fill starts at the canvas' left edge
                    self.assertLessEqual(layer["rt"], 1, (width, path, layer))  # and ends at its right edge

    def test_pair_panels_have_no_scroll_rail_and_three_visible_cards(self):
        context, page = self._page(1440, "/")
        try:
            panels = page.evaluate("""()=>[...document.querySelectorAll('.rsec[data-bg-mode="surface"]')].filter(e=>e.querySelector('.pcard')).map(e=>{
              const t=e.querySelector('.pcarousel,.grid');const cs=getComputedStyle(t);
              return {cards:e.querySelectorAll('.pcard').length,layout:t.dataset.desktopLayout,overflowX:cs.overflowX,rail:t.scrollWidth>t.clientWidth+1,display:cs.display}})""")
        finally:
            context.close()
        self.assertEqual(len(panels), 4)
        for panel in panels:
            self.assertEqual(panel["cards"], 3)
            self.assertEqual(panel["layout"], "grid")
            self.assertFalse(panel["rail"], panel)
            self.assertEqual(panel["display"], "grid", panel)

    def test_six_real_categories_fill_the_circles(self):
        context, page = self._page(1440, "/")
        try:
            items = page.evaluate("()=>[...document.querySelectorAll('.category-grey-item')].map(e=>e.className.includes('empty'))")
        finally:
            context.close()
        self.assertEqual(items, [False] * 6)

    def test_builder_chrome_never_changes_section_boxes_when_selected_or_hovered(self):
        context, page = self._page(1440, "/admin-portal/storefront-builder/preview/?page=home", authed=True)
        try:
            before = gp.collect(page)["sections"]
            page.evaluate("()=>{document.documentElement.setAttribute('data-sfb-builder-mode','edit');"
                          "const c=document.querySelector('.rcontainer-cell');c.classList.add('sfb-cell-selected');"
                          "document.querySelector('.rsec').classList.add('sfb-rsec-selected');"
                          "document.querySelector('.rcontainer').classList.add('sfb-builder-container-selected')}")
            page.hover(".rsec[data-section-id]", force=True)
            after = gp.collect(page)["sections"]
        finally:
            context.close()
        for a, b in zip(before, after):
            for key in ("x", "y", "w", "h"):
                self.assertAlmostEqual(a[key], b[key], delta=0.6, msg=(a["sig"], key))

    def test_studio_iframe_matches_published_and_atomic_refresh_never_shows_a_partial_document(self):
        context, page = self._page(1600, "/admin-portal/storefront-builder/r4/", authed=True, height=900)
        try:
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            frame = page.frame_locator("#r4PreviewFrame")
            frame.locator(".rsec").first.wait_for()
            inner = next(f for f in page.frames if f != page.main_frame and "preview" in f.url)
            studio = inner.evaluate(gp.PROBE_JS)
            self.assertEqual(studio["doc"]["scrollWidth"], studio["doc"]["clientWidth"])
            published, _audit = self._probe(1440, "/")
            self.assertEqual([s["sig"] for s in studio["sections"]], [s["sig"] for s in published["sections"]])
            self.assertEqual(studio["tokens"], published["tokens"])
            # atomic refresh: scroll, refresh, and watch the VISIBLE frame the whole time
            page.evaluate("document.getElementById('r4PreviewFrame').contentWindow.scrollTo(0,3300)")
            page.wait_for_timeout(400)
            before = page.evaluate("""()=>{const w=document.getElementById('r4PreviewFrame').contentWindow;
              const a=[...w.document.querySelectorAll('[data-section-id]')].find(e=>e.getBoundingClientRect().bottom>1);
              return {id:a.dataset.sectionId,top:Math.round(a.getBoundingClientRect().top),y:Math.round(w.scrollY),
                      sections:w.document.querySelectorAll('.rsec').length}}""")
            page.evaluate("""()=>{window.__seen=[];window.__iv=setInterval(()=>{
              const vis=[...document.querySelectorAll('.r4-preview-canvas iframe')].filter(f=>getComputedStyle(f).opacity!=='0');
              const f=vis[0];try{window.__seen.push([vis.length,f.contentDocument.readyState,f.contentDocument.querySelectorAll('.rsec').length])}catch(e){window.__seen.push([vis.length,'err',0])}},25);
              window.RastiSiR4.reloadPreview().then(()=>{window.__finished=true})}""")
            page.wait_for_function("window.__finished === true", timeout=20000)
            seen = page.evaluate("window.__seen")
            page.evaluate("clearInterval(window.__iv)")
            after = page.evaluate("""()=>{const w=document.getElementById('r4PreviewFrame').contentWindow;
              const el=w.document.querySelector('[data-section-id="'+arguments[0]+'"]');return null}""") if False else page.evaluate(
                """(id)=>{const w=document.getElementById('r4PreviewFrame').contentWindow;
                const el=w.document.querySelector('[data-section-id="'+id+'"]');
                return {top:Math.round(el.getBoundingClientRect().top),iframes:document.querySelectorAll('.r4-preview-canvas iframe').length,
                        sections:w.document.querySelectorAll('.rsec').length}}""", before["id"])
        finally:
            context.close()
        self.assertTrue(seen)
        for visible, state, sections in seen:
            self.assertEqual(visible, 1, "exactly one visible preview frame at any moment")
            self.assertEqual(state, "complete")
            self.assertEqual(sections, before["sections"], "a half-parsed document was visible")
        self.assertEqual(after["iframes"], 1)
        self.assertEqual(after["sections"], before["sections"])
        self.assertAlmostEqual(after["top"], before["top"], delta=2)  # anchored by section id, not pixels


    # ------------------------------------------------- Template 51 designability + display type wiring
    def _band_in_draft(self):
        draft = layout_service.get_or_create_draft(self.store, user=self.user)
        bands = draft.sections.filter(section_key="product_section", page__page_type="home").order_by("order")
        return draft, next(b for b in bands if (b.settings.get("background") or {}).get("mode") == "palette_pattern")

    def test_image_background_band_has_no_overflow_and_preview_equals_published(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (1600, 400), (30, 90, 200)).save(buf, "PNG")
        asset = MediaAsset.objects.create(store=self.store, image=SimpleUploadedFile("band.png", buf.getvalue(), "image/png"))
        _draft, band = self._band_in_draft()
        band.settings = {**band.settings, "background": {
            "mode": "image", "color": "", "media_asset_id": asset.pk, "pattern_slug": "", "palette_role": "",
            "bleed": True, "image_fit": "cover", "image_position_x": "left", "overlay_color": "token:text", "overlay_opacity": 35}}
        band.save()
        layout_service.publish(self.store)
        for width in WIDTHS:
            published, published_audit = self._probe(width, "/")
            preview, preview_audit = self._probe(width, "/admin-portal/storefront-builder/preview/?page=home", authed=True)
            self.assertEqual(gp.compare(published, preview), [], f"{width}px")
            for label, audit in (("published", published_audit), ("preview", preview_audit)):
                self.assertEqual(audit["scrollWidth"], audit["clientWidth"], f"{width}px {label}: {audit['offenders']}")
                self.assertEqual(audit["offenders"], [], f"{width}px {label}")
        context, page = self._page(1440, "/")
        try:
            image_layers = page.evaluate("""()=>[...document.querySelectorAll('.rsec-bleed')].filter(e=>getComputedStyle(e).backgroundImage.includes('band'))
                .map(e=>[Math.round(e.getBoundingClientRect().width),getComputedStyle(e).backgroundSize,getComputedStyle(e).backgroundPosition])""")
        finally:
            context.close()
        self.assertEqual(len(image_layers), 1)

    def test_inspector_background_and_display_type_changes_show_in_the_preview_immediately(self):
        _draft, band = self._band_in_draft()
        context, page = self._page(1600, "/admin-portal/storefront-builder/r4/", authed=True, height=900)
        try:
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)

            def preview():
                return next(f for f in page.frames if f != page.main_frame and "preview" in f.url)

            def wait_preview(expression, timeout=15000):
                # the test DB is in-process SQLite: let the previous refresh/status requests finish first
                page.wait_for_load_state("networkidle")
                page.wait_for_function(
                    """(args)=>{const f=[...document.querySelectorAll('iframe')].find(i=>i.id==='r4PreviewFrame');
                    try{return !!f.contentWindow.eval(args)}catch(e){return false}}""", arg=expression, timeout=timeout)

            sel = f'[data-section-id="{band.pk}"]'
            preview().locator(sel).first.scroll_into_view_if_needed()
            preview().locator(sel).first.dblclick(position={"x": 20, "y": 20})   # double-click opens settings (a single click only selects)
            page.wait_for_selector('select[data-r4-field-key="display_mode"]')
            # the background control lives in the workspace's «طراحی» (Design) tab
            self.assertFalse(page.locator(".r4-background-picker").first.is_visible())
            page.click('[data-r4-tab="design"]')
            self.assertTrue(page.locator(".r4-background-picker").first.is_visible())
            # red -> blue (custom colour), visible in the Preview straight away
            page.select_option(".r4-background-picker [data-r4-background-mode]", "color")
            page.wait_for_load_state("networkidle")
            page.fill(".r4-background-picker [data-r4-background-color]", "#2f6fed")
            wait_preview(f"getComputedStyle(document.querySelector('{sel} .rsec-bleed')).backgroundColor==='rgb(47, 111, 237)'")
            page.wait_for_load_state("networkidle")
            page.fill(".r4-background-picker [data-r4-background-color]", "#d62828")
            wait_preview(f"getComputedStyle(document.querySelector('{sel} .rsec-bleed')).backgroundColor==='rgb(214, 40, 40)'")
            # display type: every option changes the visible composition
            expected = {
                "campaign_band": f"!!document.querySelector('{sel} .product-campaign-band')",
                "catalog_grid": f"!!document.querySelector('{sel} .catalog-grid-bar-row')",
                "grid": f"!!document.querySelector('{sel} .grid.rsec-cols') && !document.querySelector('{sel} .pcarousel')",
                "carousel": f"!!document.querySelector('{sel} .pcarousel') && !document.querySelector('{sel} .product-campaign-band')",
            }
            page.click('[data-r4-tab="content"]')
            for mode, expression in expected.items():
                page.wait_for_load_state("networkidle")
                page.select_option('select[data-r4-field-key="display_mode"]', mode)
                wait_preview(expression)
                # nothing hidden by the engine can leave the Inspector showing a control that does nothing
                page.wait_for_selector(f'select[data-r4-field-key="display_mode"] >> nth=0')
                hidden = page.evaluate("()=>[...document.querySelectorAll('[data-r4-field-row][hidden]')].map(r=>r.dataset.r4FieldKey)")
                if mode in ("grid", "campaign_band", "catalog_grid"):
                    self.assertIn("overflow_mode", hidden, mode)
                    self.assertIn("carousel_navigation", hidden, mode)
                else:
                    self.assertNotIn("overflow_mode", hidden)
            self.assertEqual(preview().evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0)
        finally:
            context.close()
        band.refresh_from_db()
        self.assertEqual(band.settings["display_mode"], "carousel")
        self.assertEqual(band.settings["background"]["color"].lower(), "#d62828")

    # ------------------------------------------------ interaction performance (partial refresh) + campaign panel
    def _studio_with_band(self, *, viewport=(1600, 900), open_settings=True, **settings_over):
        """Open the Studio on the first palette band, optionally pre-configured; returns (context, page, section id)."""
        _draft, band = self._band_in_draft()
        band.settings = {**band.settings, **settings_over}
        band.save()
        context, page = self._page(viewport[0], "/admin-portal/storefront-builder/r4/", authed=True, height=viewport[1])
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        frame = next(f for f in page.frames if f != page.main_frame and "preview" in f.url)
        selector = f'[data-section-id="{band.pk}"]'
        frame.locator(selector).first.scroll_into_view_if_needed()
        if open_settings:
            frame.locator(selector).first.dblclick(position={"x": 20, "y": 20})   # double-click opens settings (a single click only selects)
            page.wait_for_selector('input[data-r4-field-key="title"]')
        return context, page, band

    def _preview_geometry(self, page, section_id):
        """The Preview iframe's measured box + effective breakpoint + one section's geometry (in the frame's own px)."""
        page.wait_for_function("""(sid)=>{const f=document.getElementById('r4PreviewFrame');
          try{return !!f.contentDocument.querySelector('[data-section-id="'+sid+'"]')}catch(e){return false}}""", arg=section_id, timeout=20000)
        return page.evaluate("""(sid)=>{const f=document.getElementById('r4PreviewFrame'); const r=f.getBoundingClientRect();
          const w=f.contentWindow; const sec=f.contentDocument.querySelector('[data-section-id="'+sid+'"]'); const sr=sec&&sec.getBoundingClientRect();
          return {frameW:r.width, frameH:r.height, frameX:r.x, frameY:r.y, viewport:w.innerWidth, styleW:f.style.width, transform:f.style.transform,
            bp1024:w.matchMedia('(min-width:1024px)').matches, bp768:w.matchMedia('(min-width:768px)').matches,
            secW:sr&&sr.width, secH:sr&&sr.height, secTop:sr&&sr.top+w.scrollY,
            pageOverflow:document.documentElement.scrollWidth-document.documentElement.clientWidth}}""", section_id)

    def test_settings_workspace_is_a_large_overlay_that_never_changes_the_preview_geometry(self):
        """The section settings workspace opens ABOVE the Studio: the Preview iframe (width, height, position), its
        effective breakpoint, the right-edge column and the section's own geometry are byte-identical before / while
        open / after closing — on desktop, laptop, tablet and phone — and it is a big, internally scrolling surface
        (desktop 86–94vw x 86–92vh, capped at 1550px) that is full-screen on a phone."""
        for viewport in ((1440, 900), (1280, 720), (1024, 768), (390, 844)):
            with self.subTest(viewport=viewport):
                context, page, band = self._studio_with_band(viewport=viewport, open_settings=False, display_mode="campaign_band")
                try:
                    page.wait_for_load_state("networkidle")
                    before = self._preview_geometry(page, band.pk)
                    frame = next(f for f in page.frames if f != page.main_frame and "preview" in f.url)
                    frame.locator(f'[data-section-id="{band.pk}"]').first.dblclick(position={"x": 20, "y": 20})   # double-click opens settings (a single click only selects)
                    page.wait_for_selector('[data-rs-workspace]:not([hidden]) input[data-r4-field-key="title"]')
                    page.wait_for_timeout(600)
                    during = self._preview_geometry(page, band.pk)
                    self.assertEqual(before, during, "opening the settings workspace changed the Preview geometry")
                    box = page.evaluate("""()=>{const d=document.querySelector('[data-rs-workspace-dialog]'); const r=d.getBoundingClientRect(); const cs=getComputedStyle(document.querySelector('[data-rs-workspace]'));
                      const body=document.querySelector('.r4-ws-body'); return {w:r.width,h:r.height,vw:innerWidth,vh:innerHeight,pos:cs.position,
                        insidePanel:!!document.getElementById('r4Inspector').closest('[data-rs-context-panel]'), scrolls:body.scrollHeight>=body.clientHeight,
                        bodyOverflowY:getComputedStyle(body).overflowY, docScroll:document.documentElement.scrollHeight>innerHeight}}""")
                    self.assertEqual(box["pos"], "fixed")
                    self.assertFalse(box["insidePanel"], "the settings form must not live in the right-edge panel")
                    self.assertEqual(box["bodyOverflowY"], "auto")
                    if viewport[0] > 850:
                        self.assertGreaterEqual(box["h"] / box["vh"], 0.86)
                        self.assertLessEqual(box["h"] / box["vh"], 0.92)
                        self.assertLessEqual(box["w"], 1550)
                        self.assertTrue(0.86 <= box["w"] / box["vw"] <= 0.94 or box["w"] >= 1500, box)
                    else:
                        self.assertEqual((round(box["w"]), round(box["h"])), (viewport[0], viewport[1]))
                    # the same three primary tabs, whatever the device
                    tabs = page.evaluate("[...document.querySelectorAll('.r4-ws-tab')].map(t=>t.dataset.r4Tab)")
                    self.assertEqual(tabs, ["content", "design", "advanced"])
                    page.click('[data-r4-tab="design"]')
                    page.wait_for_timeout(200)
                    self.assertEqual(self._preview_geometry(page, band.pk), before)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    self.assertTrue(page.evaluate("document.querySelector('[data-rs-workspace]').hidden"))
                    self.assertEqual(self._preview_geometry(page, band.pk), before, "closing the workspace changed the Preview geometry")
                finally:
                    context.close()

    def test_structure_drawer_and_settings_workspace_float_above_a_full_width_preview(self):
        """Default state = the storefront owns the whole canvas (no docked panel). The page-structure drawer and the
        settings workspace are on-demand overlays: A (none) / B (drawer) / C (workspace) leave the Preview iframe's
        width, height, x/y, breakpoint and the section's own geometry byte-identical at every viewport; the two overlays
        are mutually exclusive, the selected section survives drawer -> settings, Escape closes the active overlay and
        focus returns to its opener."""
        nav = lambda action: f'.top-nav [data-rastisi-action="{action}"]'
        for viewport in ((1920, 1080), (1440, 900), (1280, 720), (1024, 768), (390, 844)):
            with self.subTest(viewport=viewport):
                context, page, band = self._studio_with_band(viewport=viewport, open_settings=False, display_mode="campaign_band")
                try:
                    page.wait_for_load_state("networkidle")
                    state = lambda: page.evaluate("""()=>({drawer:document.querySelector('.rs-studio').dataset.rsDrawer,
                        workspace:!document.querySelector('[data-rs-workspace]').hidden,
                        drawerShown:getComputedStyle(document.querySelector('[data-rs-context-panel]')).display!=='none',
                        panelPos:getComputedStyle(document.querySelector('[data-rs-context-panel]')).position,
                        layoutW:document.querySelector('.studio-layout').getBoundingClientRect().width,
                        canvasW:document.querySelector('.canvas').getBoundingClientRect().width})""")
                    # A — default: nothing open, nothing docked, the canvas spans the whole Studio width
                    a_ui = state()
                    self.assertEqual((a_ui["drawer"], a_ui["workspace"], a_ui["drawerShown"]), ("closed", False, False))
                    self.assertEqual(a_ui["panelPos"], "fixed")
                    self.assertLessEqual(a_ui["layoutW"] - a_ui["canvasW"], 60, "something is still docked beside the canvas")
                    geo_a = self._preview_geometry(page, band.pk)
                    # B — page structure drawer
                    page.click(nav("structure"))
                    page.wait_for_selector('[data-rs-context-panel].panel-visible')
                    page.wait_for_timeout(300)
                    b_ui = state()
                    self.assertEqual((b_ui["drawer"], b_ui["workspace"], b_ui["drawerShown"]), ("structure", False, True))
                    self.assertEqual(self._preview_geometry(page, band.pk), geo_a, "the structure drawer changed the Preview geometry")
                    row_gear = f'[data-r4-structure-row][data-r4-structure-section-id="{band.pk}"] .rs-row-settings'
                    # select (no settings yet), then open its settings from the drawer
                    page.click(f'[data-rastisi-action="row-select"][data-id="{band.pk}"]')
                    page.wait_for_timeout(300)
                    self.assertTrue(page.evaluate(f"document.querySelector('[data-r4-structure-section-id=\"{band.pk}\"]').classList.contains('selected')"))
                    self.assertFalse(state()["workspace"], "selecting a row must not open settings by itself")
                    geo_a = self._preview_geometry(page, band.pk)   # selecting scrolled the Preview document (not the frame box)
                    page.click(row_gear)
                    page.wait_for_selector('[data-rs-workspace]:not([hidden]) input[data-r4-field-key="title"]')
                    page.wait_for_timeout(500)
                    c_ui = state()
                    self.assertEqual((c_ui["drawer"], c_ui["workspace"], c_ui["drawerShown"]), ("closed", True, False),
                                     "the drawer and the settings workspace must never be open together")
                    self.assertEqual(page.evaluate("document.querySelector('[data-r4-section-inspector]').dataset.r4SectionId"), str(band.pk))
                    geo_c = self._preview_geometry(page, band.pk)
                    for key in ("frameW", "frameH", "frameX", "frameY", "viewport", "styleW", "transform", "bp1024", "bp768", "secW", "secH", "pageOverflow"):
                        self.assertEqual(geo_a[key], geo_c[key], f"{key}: the settings workspace changed the Preview geometry")
                    # mutual exclusion the other way round: asking for the drawer while settings are open closes settings
                    page.evaluate("document.querySelector('.top-nav [data-rastisi-action=\"structure\"]').click()")
                    page.wait_for_timeout(500)
                    d_ui = state()
                    self.assertEqual((d_ui["drawer"], d_ui["workspace"]), ("structure", False))
                    # Escape closes the drawer; focus returns to the button that opened it
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
                    self.assertEqual((state()["drawer"], state()["workspace"]), ("closed", False))
                    page.click(nav("structure"))
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    self.assertEqual(page.evaluate("document.activeElement.dataset.rastisiAction"), "structure")
                    # top-bar "تنظیمات بخش" reopens the SAME selected section; Escape closes it and returns focus
                    page.click(nav("section-settings"))
                    page.wait_for_selector('[data-rs-workspace]:not([hidden])')
                    self.assertEqual(page.evaluate("document.querySelector('[data-r4-section-inspector]').dataset.r4SectionId"), str(band.pk))
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    self.assertEqual(page.evaluate("document.activeElement.dataset.rastisiAction"), "section-settings")
                    final = self._preview_geometry(page, band.pk)
                    for key in ("frameW", "frameH", "frameX", "frameY", "viewport", "transform", "bp1024", "bp768", "secW", "secH"):
                        self.assertEqual(geo_a[key], final[key], f"{key}: back on the full canvas the geometry differs")
                    self.assertEqual(state()["canvasW"], a_ui["canvasW"])
                    self.assertEqual(self.errors, [])
                finally:
                    context.close()

    def test_structure_drawer_keeps_every_structure_capability_and_partial_refresh_still_works(self):
        context, page, band = self._studio_with_band(viewport=(1440, 900), open_settings=False, display_mode="campaign_band")
        try:
            page.wait_for_load_state("networkidle")
            page.click('.top-nav [data-rastisi-action="structure"]')
            row = f'[data-r4-structure-row][data-r4-structure-section-id="{band.pk}"]'
            page.wait_for_selector(row)
            # every quick action exists on the row, wired to the existing structure hooks (move / show / lock / duplicate / remove)
            for hook in ("data-r4-structure-move=\"up\"", "data-r4-structure-move=\"down\"", "data-r4-structure-toggle-active",
                         "data-r4-structure-toggle-locked", "data-r4-structure-duplicate", "data-r4-structure-remove"):
                self.assertEqual(page.locator(f"{row} [{hook}]").count(), 1, hook)
            self.assertEqual(page.locator('[data-rastisi-action="add-section"]').count(), 1)
            geo = self._preview_geometry(page, band.pk)
            self.assertEqual(page.evaluate("document.querySelector('.rs-studio').dataset.rsDrawer"), "structure")
            # filter, then open settings from the drawer and make a partial-refresh edit
            page.fill("[data-rs-structure-search]", "zzzz-no-match")
            self.assertEqual(page.evaluate(f"document.querySelector('{row}').classList.contains('ws-filtered-out')"), True)
            page.fill("[data-rs-structure-search]", "")
            page.click(f"{row} .rs-row-settings")
            page.wait_for_selector('[data-rs-workspace]:not([hidden]) input[data-r4-field-key="title"]')
            page.evaluate("RastiSiR4.metrics.length = 0")
            page.fill('input[data-r4-field-key="title"]', "عنوان از کشو")
            page.dispatch_event('input[data-r4-field-key="title"]', "change")
            page.wait_for_function("(RastiSiR4.metrics||[]).some(m=>m.path==='fragment')", timeout=10000)
            self.assertEqual(self._preview_geometry(page, band.pk)["frameW"], geo["frameW"])
            # a drawer quick action really mutates the draft (hide the section). It is the LAST browser step on purpose: the
            # structure mutation fires concurrent preview + status GETs that race on the in-process SQLite test database
            # ("no such savepoint"), so nothing is read back through the UI afterwards; the DB is checked after the browser closes.
            page.keyboard.press("Escape")
            page.wait_for_function("document.querySelector('[data-rs-workspace]').hidden")
            page.click('.top-nav [data-rastisi-action="structure"]')
            before_revision = page.evaluate("RastiSiR4.revision")
            page.click(f"{row} [data-r4-structure-toggle-active]")
            page.wait_for_function(f"RastiSiR4.revision>{before_revision}", timeout=15000)
            # let the refresh GETs this mutation triggers finish before the test database is torn down
            page.wait_for_timeout(2500)
            page.wait_for_load_state("networkidle")
            page.wait_for_function("document.querySelectorAll('.r4-preview-canvas iframe').length===1", timeout=20000)
            page.wait_for_load_state("networkidle")
        finally:
            context.close()
        band.refresh_from_db()
        self.assertEqual(band.settings["title"], "عنوان از کشو")
        self.assertFalse(band.is_active, "the drawer's show/hide quick action did not reach the draft")

    def test_settings_workspace_live_view_follows_the_same_fragment_as_the_main_preview(self):
        context, page, band = self._studio_with_band(viewport=(1440, 900), display_mode="campaign_band", campaign_panel_title="هنر")
        try:
            page.wait_for_function(f"""()=>{{const f=document.querySelector('[data-r4-ws-live-frame]');
              try{{return !!f.contentDocument.querySelector('[data-section-id="{band.pk}"]')}}catch(e){{return false}}}}""", timeout=30000)
            page.click('[data-r4-tab="design"]')
            page.fill('input[data-r4-field-key="campaign_panel_title"]', "عنوان زنده")
            page.dispatch_event('input[data-r4-field-key="campaign_panel_title"]', "change")
            page.wait_for_function("(RastiSiR4.metrics||[]).some(m=>m.path==='fragment')", timeout=10000)
            sel = f'[data-section-id="{band.pk}"] .product-campaign-copy h2'
            page.wait_for_function("""(sel)=>{const frames=[...document.querySelectorAll('iframe')].filter(f=>f.contentDocument&&f.contentDocument.querySelector(sel));
              return frames.length===2&&frames.every(f=>f.contentDocument.querySelector(sel).textContent==='عنوان زنده')}""", arg=sel, timeout=10000)
            # the live view is the SAME canonical server page: one rendering authority, no JS storefront renderer
            self.assertEqual(page.evaluate("document.querySelectorAll('[data-r4-ws-live-stage] iframe').length"), 1)
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            # closed: the live column is hidden and its (static) frame no longer points at any page
            self.assertTrue(page.evaluate("document.querySelector('[data-r4-ws-live]').hidden"))
            self.assertEqual(page.evaluate("document.querySelector('[data-r4-ws-live-frame]').getAttribute('src')"), "about:blank")
        finally:
            context.close()

    def test_partial_refresh_swaps_only_the_section_keeps_the_document_and_reinitialises_alpine(self):
        context, page, band = self._studio_with_band(
            display_mode="carousel", carousel_navigation="arrows", desktop_columns=3, item_limit=6)
        try:
            frame_script = "document.getElementById('r4PreviewFrame').contentWindow"
            page.evaluate(f"{frame_script}.__marker = 'same-document'; window.__frameEl = document.getElementById('r4PreviewFrame')")
            sel = f'[data-section-id="{band.pk}"]'
            page.wait_for_load_state("networkidle")
            page.fill('input[data-r4-field-key="title"]', "عنوان جزئی")
            page.dispatch_event('input[data-r4-field-key="title"]', "change")
            page.wait_for_function("(RastiSiR4.metrics||[]).some(m=>m.path==='fragment')", timeout=10000)
            state = page.evaluate(f"""()=>{{const w={frame_script};return {{marker:w.__marker, same:window.__frameEl===document.getElementById('r4PreviewFrame'),
              title:(w.document.querySelector('{sel} .sec-head h2')||{{}}).textContent||'', frames:document.querySelectorAll('.r4-preview-canvas iframe').length}}}}""")
            self.assertEqual(state["marker"], "same-document")   # the document was NOT reloaded
            self.assertTrue(state["same"])                       # nor was a twin frame swapped in
            self.assertIn("عنوان جزئی", state["title"])
            self.assertEqual(state["frames"], 1)
            # Alpine was re-initialised on the swapped subtree: its component methods run (the builder chrome intercepts
            # real clicks inside the Studio preview, so the component is driven through its own API)
            page.wait_for_timeout(300)
            moved = page.evaluate(f"""()=>{{const w={frame_script};const shell=w.document.querySelector('{sel} .pcarousel-shell');
              if(!shell||!shell._x_dataStack) return null; const data=shell._x_dataStack[0]; const before=data.page;
              data.go(before+1); return [before,data.page,data.pages,shell.querySelector('.pcarousel-next')!==null]}}""")
            self.assertIsNotNone(moved, "the swapped carousel has no Alpine state: not re-initialised")
            self.assertEqual(moved[0], 0)
            self.assertGreaterEqual(moved[2], 2)
            self.assertEqual(moved[1], 1)
        finally:
            context.close()

    def test_rapid_input_is_coalesced_into_one_write_and_the_last_value_wins(self):
        context, page, band = self._studio_with_band(display_mode="campaign_band")
        requests = []
        page.on("request", lambda r: requests.append(r.post_data) if r.method == "POST" and "/r4/mutate/" in r.url else None)
        try:
            page.wait_for_load_state("networkidle")
            page.evaluate("""()=>{const t=document.querySelector('input[data-r4-field-key="title"]');
              for(let i=1;i<=25;i++){t.value='عنوان '+i;t.dispatchEvent(new Event('input',{bubbles:true}))}}""")
            page.wait_for_function("(RastiSiR4.metrics||[]).length>=1", timeout=10000)
            page.wait_for_timeout(600)
            title_writes = [r for r in requests if '"title"' in (r or "")]
            self.assertLessEqual(len(title_writes), 2, title_writes)
            self.assertIn("عنوان 25", title_writes[-1])
            # a colour drag: dozens of input events, one write, last colour wins
            requests.clear()
            page.evaluate("""()=>{const c=document.querySelector('.r4-background-picker [data-r4-background-color]');
              const modeSel=document.querySelector('.r4-background-picker [data-r4-background-mode]'); modeSel.value='color'; modeSel.dispatchEvent(new Event('change',{bubbles:true}));
              const palette=['#101010','#202020','#303030','#404040','#505050','#606060','#707070','#808080'];
              for(let i=0;i<40;i++){c.value=palette[i%8];c.dispatchEvent(new Event('input',{bubbles:true}))}c.value='#2f6fed';c.dispatchEvent(new Event('input',{bubbles:true}))}""")
            page.wait_for_timeout(900)
            colour_writes = [r for r in requests if '"background"' in (r or "")]
            self.assertLessEqual(len(colour_writes), 3, len(colour_writes))
            self.assertIn("#2f6fed", colour_writes[-1])
        finally:
            context.close()
        band.refresh_from_db()
        self.assertEqual(band.settings["title"], "عنوان 25")
        self.assertEqual(band.settings["background"]["color"], "#2f6fed")

    def test_measured_latency_of_inspector_edits_reaching_the_preview(self):
        import statistics

        context, page, band = self._studio_with_band(display_mode="campaign_band", campaign_panel_title="هنر")
        try:
            page.wait_for_load_state("networkidle")
            samples = {"simple": [], "structural": []}

            def measure(action, bucket):
                page.evaluate("()=>{window.__m0=(RastiSiR4.metrics||[]).length;window.__t0=performance.now();window.__lat=null;"
                              "const tick=()=>{const m=RastiSiR4.metrics||[];if(m.length>window.__m0&&m[m.length-1].path==='fragment'){window.__lat=performance.now()-window.__t0;return}"
                              "if(performance.now()-window.__t0<8000)setTimeout(tick,1)};tick()}")
                action()
                page.wait_for_function("window.__lat!==null||performance.now()-window.__t0>8000", timeout=10000)
                latency = page.evaluate("window.__lat")
                self.assertIsNotNone(latency, "the Preview never reached the new state")
                samples[bucket].append(latency)
                page.wait_for_timeout(250)

            page.click('[data-r4-tab="design"]')
            for i in range(8):
                measure(lambda i=i: (page.fill('input[data-r4-field-key="campaign_panel_title"]', f"پنل {i}"),
                                     page.dispatch_event('input[data-r4-field-key="campaign_panel_title"]', "change")), "simple")
            page.click('[data-r4-tab="content"]')
            for i, mode in enumerate(["grid", "catalog_grid", "campaign_band", "carousel"] * 2):
                measure(lambda mode=mode: page.select_option('select[data-r4-field-key="display_mode"]', mode), "structural")
        finally:
            context.close()
        report = {k: (round(statistics.median(v)), round(sorted(v)[max(0, int(len(v) * .95) - 1)])) for k, v in samples.items()}
        print("latency (median, p95) ms:", report)
        # Local QA targets are 200/500 ms (simple) and 350/800 ms (structural); the assertion leaves headroom for a loaded
        # CI box. The measured numbers are printed above and recorded in the report.
        self.assertLessEqual(report["simple"][0], 450, report)
        self.assertLessEqual(report["structural"][0], 600, report)
