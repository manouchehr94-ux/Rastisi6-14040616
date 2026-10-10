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
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry as lpr
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
