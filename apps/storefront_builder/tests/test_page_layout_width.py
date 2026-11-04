"""«چیدمان و عرض صفحات» — the Store-global page-width choice (standard / wide / full / custom).

One vocabulary + one resolver (``appearance_registry.resolve_page_layout``), stored sparsely in the Draft's ``appearance_config`` (no migration), set
through ``appearance.update`` (Undo/Redo, revisions), carried by Publish, written into every storefront page by ``templates/base.html`` as ONE data
attribute + two validated custom properties, and turned into the page container by ONE rule-set in ``base.css``. Legacy Stores (no key) render exactly
as before. Throw-away database only."""

import json
import re
from pathlib import Path

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import appearance_registry as registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

from .test_hero_stage_templates import PUBLIC_A
from .test_r4_mutation_api import R4MutationApiTestCase

REPO = Path(__file__).resolve().parents[3]
BASE_CSS = (REPO / "apps/core/static/css/base.css").read_text(encoding="utf-8")
LAYOUT_CSS = (REPO / "apps/core/static/css/layout.css").read_text(encoding="utf-8")
BASE_HTML = (REPO / "templates/base.html").read_text(encoding="utf-8")
KEYS = registry.PAGE_LAYOUT_KEYS


class ResolverAndValidatorTests(R4MutationApiTestCase):
    def test_resolver_is_total_and_never_trusts_stored_values(self):
        self.assertEqual(registry.resolve_page_layout(None)["mode"], "standard")
        self.assertEqual(registry.resolve_page_layout({})["mode"], "standard")
        self.assertEqual(registry.resolve_page_layout({"page_width_mode": "sideways"})["mode"], "standard")
        for mode in ("wide", "full"):
            self.assertEqual(registry.resolve_page_layout({"page_width_mode": mode}), {"mode": mode, "max_width": None, "gutter": None})
        custom = registry.resolve_page_layout({"page_width_mode": "custom", "page_max_width": "1500", "page_gutter": 30})
        self.assertEqual(custom, {"mode": "custom", "max_width": 1500, "gutter": 30})
        broken = registry.resolve_page_layout({"page_width_mode": "custom", "page_max_width": "<script>", "page_gutter": 99999})
        self.assertEqual((broken["max_width"], broken["gutter"]), (1320, 24))

    def test_validator_is_sparse_and_bounded(self):
        base = svc.validate_appearance_config({})
        self.assertFalse(set(KEYS) & set(base), "an untouched Store keeps its stored shape")
        self.assertFalse(set(KEYS) & set(svc.validate_appearance_config({"page_width_mode": "standard"})))
        wide = svc.validate_appearance_config({"page_width_mode": "wide", "page_max_width": 1500})
        self.assertEqual({k: wide[k] for k in KEYS if k in wide}, {"page_width_mode": "wide"})
        custom = svc.validate_appearance_config({"page_width_mode": "custom"})
        self.assertEqual((custom["page_max_width"], custom["page_gutter"]), (1320, 24))
        low, high = registry.PAGE_MAX_WIDTH_RANGE
        for bad in (low - 1, high + 1, "abc", "12.5"):
            with self.subTest(width=bad), self.assertRaises(svc.AppearanceConfigValidationError):
                svc.validate_appearance_config({"page_width_mode": "custom", "page_max_width": bad})
        glow, ghigh = registry.PAGE_GUTTER_RANGE
        for bad in (glow - 1, ghigh + 1, "x"):
            with self.subTest(gutter=bad), self.assertRaises(svc.AppearanceConfigValidationError):
                svc.validate_appearance_config({"page_width_mode": "custom", "page_gutter": bad})
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"page_width_mode": "huge"})
        ok = svc.validate_appearance_config({"page_width_mode": "custom", "page_max_width": low, "page_gutter": ghigh})
        self.assertEqual((ok["page_max_width"], ok["page_gutter"]), (low, ghigh))


@override_settings(ALLOWED_HOSTS=["*"])
class PageWidthMutationAndRenderTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=PUBLIC_A)

    def _draft(self):
        return svc.get_or_create_draft(self.store, user=self.staff)

    def _post(self, url_name, body):
        return self.client.post(reverse(url_name), data=json.dumps(body), content_type="application/json")

    def _set(self, patch, *, expect=200):
        response = self._post("dashboard:storefront-builder-r4-mutation", {
            "base_revision": self._draft().edit_revision, "mutation": {"type": "appearance.update", "patch": patch}})
        self.assertEqual(response.status_code, expect, response.content[:300])
        return response

    def _history(self, command):
        response = self._post("dashboard:storefront-builder-r4-history", {"base_revision": self._draft().edit_revision, "command": command})
        self.assertEqual(response.status_code, 200, response.content[:300])

    def _stored(self):
        return {k: v for k, v in (self._draft().appearance_config or {}).items() if k in KEYS}

    def _publish(self):
        response = self._post("dashboard:storefront-builder-r4-publish", {"base_revision": self._draft().edit_revision})
        self.assertEqual(response.status_code, 200, response.content[:300])
        cache.clear()

    @staticmethod
    def _html_attr(html):
        match = re.search(r'<html\b[^>]*?data-sfb-page-width="(\w+)"', html, re.S)
        return match.group(1) if match else None

    # --- storage / history ---------------------------------------------------------------------------------------------------
    def test_each_mode_is_one_undoable_step_and_standard_restores_the_stored_shape(self):
        self.assertEqual(self._stored(), {})
        revision = self._draft().edit_revision
        self._set({"page_width_mode": "wide"})
        self.assertEqual(self._stored(), {"page_width_mode": "wide"})
        self.assertEqual(self._draft().edit_revision, revision + 1)
        self._set({"page_width_mode": "custom", "page_max_width": "1500", "page_gutter": "32"})
        self.assertEqual(self._stored(), {"page_width_mode": "custom", "page_max_width": 1500, "page_gutter": 32})
        self._set({"page_width_mode": "full"})
        self.assertEqual(self._stored(), {"page_width_mode": "full"}, "the custom numbers are dropped with the custom mode")
        self._set({"page_width_mode": "standard"})
        self.assertEqual(self._stored(), {})
        self._history("undo")
        self.assertEqual(self._stored(), {"page_width_mode": "full"})
        self._history("undo")
        self.assertEqual(self._stored(), {"page_width_mode": "custom", "page_max_width": 1500, "page_gutter": 32})
        self._history("redo")
        self.assertEqual(self._stored(), {"page_width_mode": "full"})

    def test_an_invalid_custom_width_is_refused_with_a_reason_and_nothing_is_saved(self):
        self._set({"page_width_mode": "wide"})
        before, revision = self._stored(), self._draft().edit_revision
        for patch in ({"page_width_mode": "custom", "page_max_width": "50"}, {"page_width_mode": "custom", "page_gutter": "500"},
                      {"page_width_mode": "custom", "page_max_width": "<b>"}, {"page_width_mode": "nope"}):
            with self.subTest(patch=patch):
                response = self._set(patch, expect=400)
                self.assertEqual(response.json()["code"], "invalid_appearance_config")
                self.assertTrue(response.json().get("message"))
                self.assertEqual(self._stored(), before)
                self.assertEqual(self._draft().edit_revision, revision)

    def test_other_appearance_edits_keep_the_width_choice(self):
        self._set({"page_width_mode": "custom", "page_max_width": "1500", "page_gutter": "32"})
        self._set({"density": "compact"})
        self._set({"motion": "none"})
        self.assertEqual(self._stored(), {"page_width_mode": "custom", "page_max_width": 1500, "page_gutter": 32})

    # --- preview / publish / every page -----------------------------------------------------------------------------------
    def test_standard_changes_nothing_in_the_page_markup(self):
        html = self.public.get("/").content.decode()
        self.assertIsNone(self._html_attr(html))
        self.assertNotIn("--sfb-page-width-custom", html)
        self.assertNotIn("--sfb-gutter-custom", html)

    def test_draft_preview_shows_the_choice_and_the_public_page_waits_for_publish(self):
        self._set({"page_width_mode": "wide"})
        preview = self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()
        self.assertEqual(self._html_attr(preview), "wide")
        self.assertIsNone(self._html_attr(self.public.get("/").content.decode()), "Draft only until Publish")
        self._publish()
        self.assertEqual(self._html_attr(self.public.get("/").content.decode()), "wide")
        published = self._draft().layout.published_version
        self.assertEqual({k: v for k, v in published.appearance_config.items() if k in KEYS}, {"page_width_mode": "wide"})

    def test_every_storefront_page_carries_the_choice_after_publish(self):
        self._set({"page_width_mode": "custom", "page_max_width": "1440", "page_gutter": "28"})
        self._publish()
        seen = {}
        for path in ("/", "/products/", "/collections/", "/cart/", "/checkout/"):
            response = self.public.get(path, follow=True)
            self.assertEqual(response.status_code, 200, path)
            html = response.content.decode()
            seen[path] = self._html_attr(html)
            if path == "/checkout/":
                # an empty cart may bounce to the cart page: remember where the checkout really rendered, so the report is honest about it
                self.checkout_landed = response.redirect_chain[-1][0] if response.redirect_chain else path
            self.assertIn("--sfb-page-width-custom:1440px", html, path)
            self.assertIn("--sfb-gutter-custom:28px", html, path)
        self.assertEqual(set(seen.values()), {"custom"}, seen)

    def test_the_numbers_written_into_the_page_are_validated_integers_only(self):
        self._set({"page_width_mode": "custom", "page_max_width": "1500", "page_gutter": "32"})
        stored = self._draft().appearance_config
        stored["page_max_width"] = "1500px;} body{display:none"        # a hand-edited / corrupted stored value
        self._draft().__class__.objects.filter(pk=self._draft().pk).update(appearance_config=stored)
        self._publish()
        html = self.public.get("/").content.decode()
        self.assertNotIn("display:none", html.split("</head>")[0])
        self.assertIn("--sfb-page-width-custom:1320px", html)              # fell back to the default, never echoed

    # --- stylesheet contract -----------------------------------------------------------------------------------------------
    def test_one_token_feeds_every_container_and_legacy_rules_are_untouched(self):
        self.assertIn(":root{--sfb-page-width:max(var(--sfb-content-width,1240px),min(84vw,var(--sfb-page-width-cap,1720px)))}", BASE_CSS)
        for mode in ("wide", "full", "custom"):
            self.assertRegex(BASE_CSS, r'html\[data-sfb-page-width="%s"\]\{[^}]*--sfb-page-width:' % mode)
        # the custom gutter beats the density gutter (same specificity → it must come later)
        self.assertLess(BASE_CSS.index('html[data-sfb-density="relaxed"]'), BASE_CSS.index('html[data-sfb-page-width="custom"]'))
        self.assertIn(".wrap{max-width:var(--sfb-page-width, 1240px)", BASE_CSS)
        self.assertIn(".wrap{width:min(var(--sfb-page-width,1320px),calc(100% - 28px))}", LAYOUT_CSS)
        self.assertIn("data-sfb-page-width", BASE_HTML)
        self.assertEqual(len(re.findall(r"--sfb-page-width-custom", BASE_HTML)), 1)
