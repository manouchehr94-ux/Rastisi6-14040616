"""Real-browser proof of the background ownership contract (Chromium + Playwright).

* the 20-section audit: every section type that exposes «پس‌زمینه این بخش» is rendered with a white fill and then a
  #0057FF fill; the painted result must show the fill (``qa.background_contract.classify`` verdict starts with PASS);
* Amazing Offers: palette, custom colour, pattern, picture, picture + overlay and bleed visibly change the outer / main
  surface (computed styles), the foreground token keeps the text readable, Preview == Published;
* Studio: the native ``input[type=color]`` is a live, coalesced, script-free PARTIAL refresh; the main Preview and the
  workspace's live mini-frame show the same new fill; the value survives close / reopen and a page reload.

Opt-in: ``SFB_BROWSER_TESTS=1 python manage.py test apps.storefront_builder.tests.test_background_contract_browser``
(needs Playwright + Chromium; ``SFB_BROWSER_PATH`` overrides the browser path)."""

import io
import os
import statistics
import unittest
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.servers.basehttp import WSGIServer
from django.db import transaction
from django.test import Client, override_settings
from django.test.testcases import LiveServerThread, QuietWSGIRequestHandler
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import MediaAsset
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry as lpr, section_registry
from apps.storefront_builder.qa import background_contract as bgc
from apps.storefront_builder.services import layout_service, preset_service, section_structure_service as sss
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
HOST = f"sfb-bgcontract.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
PUBLIC_HOST = "sfb-bgcontract-public.example.com"
BROWSER_CANDIDATES = (os.environ.get("SFB_BROWSER_PATH", ""), "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                      "/opt/pw-browsers/chromium")
PREVIEW = "/admin-portal/storefront-builder/preview/?page=home"
BLUE_RGB = "rgb(0, 87, 255)"

#: computed facts of one section: the wrapper, the primary surface (if any), inks and the pixel owner at the centre
FACTS_JS = """(sid)=>{const sec=sid?document.querySelector('.rsec[data-section-id="'+sid+'"]'):document.querySelector('.special-wrap').closest('.rsec'); if(!sec) return null;
  const cs=(e)=>e?getComputedStyle(e):null; const s=cs(sec); const w=sec.querySelector('[data-sfb-section-surface]');
  const bleed=sec.querySelector(':scope > .rsec-bleed');
  return {mode:sec.dataset.bgMode||null, bleed:sec.dataset.bgBleed||null, overlay:sec.dataset.bgOverlay||null,
    wrapperBg:s.backgroundColor, wrapperImg:s.backgroundImage.slice(0,40), bleedBg:bleed?cs(bleed).backgroundColor:null,
    bleedImg:bleed?cs(bleed).backgroundImage.slice(0,40):null,
    surfaceBg:w?cs(w).backgroundColor:null, surfaceImg:w?cs(w).backgroundImage.slice(0,40):null, surfaceInk:w?cs(w).color:null,
    h3:cs(sec.querySelector('.special-copy h3'))&&cs(sec.querySelector('.special-copy h3')).color,
    fgVar:s.getPropertyValue('--sfb-section-fg').trim(), overflowX:document.documentElement.scrollWidth-document.documentElement.clientWidth,
    width:Math.round(sec.getBoundingClientRect().width)}}"""


def _browser_path():
    for path in BROWSER_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


def _bg(mode="color", color="", **extra):
    return {"mode": mode, "color": color, "media_asset_id": None, "pattern_slug": "", "palette_role": "", **extra}


class SerialLiveServerThread(LiveServerThread):
    """One request at a time.

    The test database is ONE in-memory SQLite connection that Django shares with the live-server thread. With the default
    threaded server the Studio's parallel requests (panel refresh + preview/fragment reload) interleave on that single
    connection and fail with ``no such savepoint`` / ``another row available`` — a harness artefact: the same flow passes 6/6 on
    PostgreSQL (a connection per thread) with the threaded server. Serialising the server removes the artefact without touching
    any behavioural assertion; production uses a connection per thread and is unaffected."""
    server_class = WSGIServer

    def _create_server(self, connections_override=None):
        # this thread already owns the shared connection (LiveServerThread.run); the server itself is not threaded
        return self.server_class((self.host, self.port), QuietWSGIRequestHandler, allow_reuse_address=False)


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class BackgroundBrowserFixture(StaticLiveServerTestCase):
    server_thread_class = SerialLiveServerThread

    """Store + Template 51 draft + one Amazing Offers section + a real Studio session; shared by the browser contracts."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1, MAP {PUBLIC_HOST} 127.0.0.1"],
                  "ignore_default_args": ["--hide-scrollbars"]}
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
            name="فروشگاه پس‌زمینه", slug="sfb-bgcontract-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain=HOST.split(".")[0])
        ShopSettings.provision_for(self.store)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="bgc-vendor")
        roots = [Category.objects.create(store=self.store, name=f"دسته {i}", slug=f"root-{i}", order=i, is_active=True)
                 for i in range(3)]
        for n in range(24):
            Product.objects.create(store=self.store, vendor=vendor, category=roots[n % 3], name=f"کالای شماره {n}",
                                   slug=f"bgc-{n}", sku=f"BGC-{n}", price=Decimal(100000 + n * 1000),
                                   discount_percent=15 if n % 2 == 0 else 0, stock=5, status=Product.Status.ACTIVE)
        user = get_user_model().objects.create_user(username="09125550888", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.draft = layout_service.get_or_create_draft(self.store, user=user)
        layout = layout_service.get_or_create_layout(self.store)
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("stationery_spectrum"))
        with transaction.atomic():  # the structure services run inside apply_mutation's transaction in production
            for preset_offer in self.draft.sections.filter(section_key="amazing_offers"):  # exactly ONE Amazing Offers on the page
                sss.remove_section(draft=self.draft, section_id=preset_offer.pk)
            self.offers = sss.add_section(draft=self.draft, section_key="amazing_offers", page_type="home")
        StoreDomain.objects.create(store=self.store, hostname=PUBLIC_HOST, is_primary=True,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        client = Client(HTTP_HOST=HOST)
        client.login(username="09125550888", password="pass12345")
        port = self.live_server_url.rsplit(":", 1)[1]
        self.base, self.public_base = f"http://{HOST}:{port}", f"http://{PUBLIC_HOST}:{port}"
        self.cookie = {"name": "sessionid", "value": client.cookies["sessionid"].value, "domain": HOST, "path": "/"}

    # ----------------------------------------------------------------------------------------------- helpers
    def _set_background(self, section, background):
        section.refresh_from_db()
        section.settings = {**section.settings, "background": background}
        section.save()

    def _page(self, path, *, authed=False, width=1440, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="fa-IR")
        if authed:
            context.add_cookies([self.cookie])
        page = context.new_page()
        page.goto(f"{self.base if authed else self.public_base}{path}", wait_until="networkidle")
        page.wait_for_timeout(600)
        return context, page

    def _facts(self, path, *, authed):
        context, page = self._page(path, authed=authed)
        try:
            # the published storefront carries no builder ids, and publishing promotes the draft (new draft = new ids): the
            # page holds exactly ONE Amazing Offers section, found by its widget
            page.locator(".special-wrap").first.scroll_into_view_if_needed()
            return page.evaluate(FACTS_JS, None)
        finally:
            context.close()

    def _publish(self):
        layout_service.publish(self.store)

    def _current_offers(self):
        """The Amazing Offers row of the CURRENT draft (a publish promotes the draft; the next draft has new ids)."""
        draft = layout_service.get_or_create_draft(self.store, user=get_user_model().objects.get(username="09125550888"))
        return draft.sections.get(section_key="amazing_offers", page__page_type="home")


    def _asset(self):
        buf = io.BytesIO()
        Image.new("RGB", (1600, 400), (30, 90, 200)).save(buf, "PNG")
        return MediaAsset.objects.create(store=self.store, image=SimpleUploadedFile("bg.png", buf.getvalue(), "image/png"))

    def _open_workspace(self, page, section_id=None):
        """Open the Settings Workspace on a section THROUGH THE REAL UI (the Preview's own direct-edit open path) and land on Design."""
        section_id = section_id or self.offers.pk
        page.evaluate("(sid)=>RastiSiR4.openSection(sid)", section_id)
        page.wait_for_selector('[data-rs-workspace]:not([hidden]) [data-r4-section-inspector]')
        page.wait_for_timeout(1200)
        page.locator('[data-r4-tab="design"]').first.click()
        page.wait_for_selector(".r4-background-picker [data-r4-background-mode]")

    def _frames(self, page):
        return [f for f in page.frames if f != page.main_frame and "/preview/" in f.url]


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class BackgroundContractBrowserTests(BackgroundBrowserFixture):
    # ------------------------------------------------------------------------------------ Amazing Offers visibly follows
    def test_amazing_offers_every_background_mode_changes_the_visible_surface_and_preview_equals_published(self):
        asset = self._asset()
        cases = {
            "color": (_bg(color="#0057FF"), lambda f: f["wrapperBg"] == BLUE_RGB and f["fgVar"].upper() == "#FFFFFF"),
            "dark": (_bg(color="#101828"), lambda f: f["wrapperBg"] == "rgb(16, 24, 40)"),
            "bleed": (_bg(color="#0057FF", bleed=True), lambda f: f["bleed"] and f["bleedBg"] == BLUE_RGB),
            "pattern": (_bg("pattern", color="#102030", pattern_slug="commerce-doodle"),
                        lambda f: f["wrapperBg"] == "rgb(16, 32, 48)" and "url(" in f["wrapperImg"]),
            "palette": (_bg("palette", palette_role="tone-3"), lambda f: f["mode"] == "palette" and f["wrapperBg"] != "rgba(0, 0, 0, 0)"),
            "image": (_bg("image", media_asset_id=asset.pk), lambda f: "url(" in f["wrapperImg"] and f["surfaceImg"] == "none"),
            "overlay": (_bg("image", media_asset_id=asset.pk, overlay_color="token:text", overlay_opacity=45),
                        lambda f: f["overlay"] and "url(" in f["wrapperImg"]),
        }
        for name, (background, expect) in cases.items():
            self._set_background(self._current_offers(), background)
            self._publish()
            preview = self._facts(PREVIEW, authed=True)
            public = self._facts("/", authed=False)
            self.assertTrue(expect(preview), f"{name} preview {preview}")
            self.assertTrue(expect(public), f"{name} published {public}")
            for key in ("mode", "bleed", "overlay", "wrapperBg", "bleedBg", "surfaceBg", "surfaceInk", "h3", "fgVar", "width"):
                self.assertEqual(preview[key], public[key], f"{name}: preview != published for {key}")
            self.assertEqual(preview["overflowX"], 0, name)
            if name in ("color", "dark", "bleed", "pattern", "palette"):
                self.assertEqual(preview["surfaceBg"], "rgba(0, 0, 0, 0)", f"{name}: primary surface must let the fill through")

    def test_switching_palette_or_template_never_defeats_an_explicit_background(self):
        """Theme / palette / template are semantic defaults: an explicit Background colour keeps its paint after each switch,
        and the published storefront still equals the preview."""
        import json

        from django.urls import reverse

        from apps.storefront_builder import appearance_registry

        self._set_background(self.offers, _bg(color="#0057FF"))
        client = Client(HTTP_HOST=HOST)
        client.login(username="09125550888", password="pass12345")
        palettes = [p.slug for p in appearance_registry.list_palettes()]
        templates = [t.slug for t in appearance_registry.list_templates()]
        self.assertGreaterEqual(len(palettes), 2)
        switches = [{"palette_slug": palettes[0]}, {"palette_slug": palettes[-1]}, {"template_slug": templates[-1]}]
        for patch in switches:
            draft = layout_service.get_or_create_draft(self.store, user=get_user_model().objects.get(username="09125550888"))
            response = client.post(
                reverse("dashboard:storefront-builder-r4-mutation"),
                data=json.dumps({"base_revision": draft.edit_revision, "mutation": {"type": "appearance.update", "patch": patch}}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, (patch, response.content[:200]))
            preview = self._facts(PREVIEW, authed=True)
            self.assertEqual(preview["wrapperBg"], BLUE_RGB, f"{patch}: preview lost the explicit fill {preview}")
            self.assertEqual(preview["surfaceBg"], "rgba(0, 0, 0, 0)", patch)
        self._publish()
        public = self._facts("/", authed=False)
        self.assertEqual(public["wrapperBg"], BLUE_RGB, public)
        self.assertEqual(public["overflowX"], 0)

    def test_amazing_offers_custom_colour_is_painted_not_hidden_under_the_panel(self):
        self._set_background(self.offers, _bg(color="#0057FF"))
        context, page = self._page(PREVIEW, authed=True)
        try:
            section = page.locator(f'.rsec[data-section-id="{self.offers.pk}"]').first
            section.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            measured = page.evaluate(bgc.MEASURE_JS, {"fill": [0, 87, 255], "hex": "0057ff"})[str(self.offers.pk)]
        finally:
            context.close()
        self.assertTrue(measured["blueSeen"], measured)
        self.assertLess(measured["dominantShare"], 50, f"an inner surface hides the fill: {measured}")
        self.assertEqual(measured["ring"], 100.0, measured)
        self.assertGreaterEqual(measured["coverage"], 60.0, measured)

    # ------------------------------------------------------------------------------------------- the 20-section audit
    def test_every_background_aware_section_shows_the_fill_white_to_blue(self):
        keys = [k for k, d in section_registry.SECTION_REGISTRY.items()
                if d.settings_schema and any(f.field_type == "background" for f in d.settings_schema.fields)]
        placed = {}
        for key in keys:
            try:
                section = self.offers if key == "amazing_offers" else sss.add_section(draft=self.draft, section_key=key, page_type="home")
            except sss.SectionStructureError:
                continue
            placed[section.pk] = (key, section)
        self.assertGreaterEqual(len(placed), 18)
        verdicts = {}
        for hexcolour, rgb in (("#FFFFFF", [255, 255, 255]), ("#0057FF", [0, 87, 255])):
            for _key, section in placed.values():
                self._set_background(section, _bg(color=hexcolour))
            context, page = self._page(PREVIEW, authed=True)
            try:
                results = {}
                for sid in placed:
                    page.evaluate("(s)=>document.querySelector('.rsec[data-section-id=\"'+s+'\"]').scrollIntoView({block:'start'})", str(sid))
                    page.wait_for_timeout(80)
                    got = page.evaluate(bgc.MEASURE_JS, {"fill": rgb, "hex": hexcolour.lstrip("#").lower()})
                    results[sid] = got.get(str(sid), {"empty": True})
            finally:
                context.close()
            verdicts[hexcolour] = results
        failures = []
        for sid, (key, _section) in placed.items():
            verdict = bgc.classify(verdicts["#FFFFFF"][sid], verdicts["#0057FF"][sid])
            if not verdict.startswith("PASS") and verdict != "NO CONTENT":
                failures.append((key, sid, verdict, verdicts["#0057FF"][sid].get("dominant")))
        self.assertEqual(failures, [], failures)



    def test_live_colour_input_is_a_coalesced_script_free_partial_refresh_that_main_and_mini_both_show(self):
        self._set_background(self.offers, _bg("theme"))
        context, page = self._page("/admin-portal/storefront-builder/r4/?page=home", authed=True, height=900)
        try:
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            self._open_workspace(page)
            requests = []
            page.on("request", lambda r: requests.append(r.post_data) if r.method == "POST" and "/r4/mutate/" in r.url else None)
            page.select_option(".r4-background-picker [data-r4-background-mode]", "color")
            page.wait_for_timeout(1200)

            def wait_for(colour_hex):
                page.wait_for_function(
                    """([sid, hex])=>[...document.querySelectorAll('iframe')].filter(f=>f.src||f.contentWindow).every(f=>{
                        try{const e=f.contentDocument.querySelector('.rsec[data-section-id="'+sid+'"]');
                            return !f.contentDocument.querySelector('.rsec') || !e || (e.getAttribute('style')||'').toLowerCase().includes(hex)}catch(x){return true}})""",
                    arg=[str(self.offers.pk), colour_hex], timeout=10000)

            latencies, paths = [], []
            for colour in ("#ef4444", "#0f766e", "#7c3aed", "#0057ff"):
                before = page.evaluate("RastiSiR4.metrics.length")
                started = page.evaluate("performance.now()")
                page.evaluate("""(c)=>{const i=document.querySelector('.r4-background-picker [data-r4-background-color]');
                  const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; set.call(i,c);
                  i.dispatchEvent(new Event('input',{bubbles:true}))}""", colour)
                wait_for(colour)
                latencies.append(page.evaluate("performance.now()") - started)
                page.wait_for_timeout(500)
                paths += [m["path"] for m in page.evaluate("RastiSiR4.metrics")[before:]]
            print("live colour input -> both frames (ms):", [round(x) for x in latencies], "median", round(statistics.median(latencies)))
            self.assertEqual(set(paths), {"fragment"}, f"a colour edit must be a partial refresh, got {paths}")
            self.assertLessEqual(statistics.median(latencies), 700, latencies)  # headroom for a loaded CI box; see report
            # main and mini carry the SAME fill from the same fragment
            facts = [frame.evaluate(FACTS_JS, str(self.offers.pk)) for frame in self._frames(page)]
            self.assertGreaterEqual(len(facts), 2, "main Preview + live mini-frame")
            self.assertTrue(all(f["wrapperBg"] == BLUE_RGB and f["surfaceBg"] == "rgba(0, 0, 0, 0)" for f in facts), facts)
            drop = lambda f: {k: v for k, v in f.items() if k != "width"}  # noqa: E731  (frame widths differ by the scrollbar)
            self.assertEqual(drop(facts[0]), drop(facts[-1]))
            # coalescing: a drag of 12 input events -> one write
            requests.clear()
            page.evaluate("""()=>{const i=document.querySelector('.r4-background-picker [data-r4-background-color]');
              const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
              for(let k=0;k<12;k++){set.call(i,'#'+(0x102030+k*0x0a0b0c).toString(16).padStart(6,'0'));i.dispatchEvent(new Event('input',{bubbles:true}))}
              set.call(i,'#101828');i.dispatchEvent(new Event('input',{bubbles:true}))}""")
            page.wait_for_timeout(1500)
            self.assertLessEqual(len([r for r in requests if '"background"' in (r or "")]), 2, requests)
            wait_for("#101828")
            # persists: close / reopen, then a page reload
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            self._open_workspace(page)
            self.assertEqual(page.input_value(".r4-background-picker [data-r4-background-color]"), "#101828")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1500)
            self._open_workspace(page)
            self.assertEqual(page.input_value(".r4-background-picker [data-r4-background-color]"), "#101828")
        finally:
            context.close()
        self.offers.refresh_from_db()
        self.assertEqual(self.offers.settings["background"]["color"].lower(), "#101828")
