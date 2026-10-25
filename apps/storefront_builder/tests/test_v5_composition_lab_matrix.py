"""The five composition-lab scenarios (``qa/composition_lab.py``) run through the WHOLE chain, one by one:

  real Mutation path  →  Draft (public page still untouched)  →  Preview  →  Undo / Redo of the last edit  →  Publish (public page)

The lab builds with nothing but the Inspector's mutation entry point, so a green row here means the layout is made, edited, previewed,
undone, redone and published by generic R4 controls only — no recipe, no template key, no site CSS."""

import re
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.content.models import PromotionalBanner
from apps.storefront_builder.qa import composition_lab
from apps.storefront_builder.services import layout_service as svc

from .test_media_views import HOST
from .test_v5_composition_lab import LAB_HOST, _LabBase
from .test_v5_pdp_design_controls import _data_attrs, _pdp_tag

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82")
_MEDIA = tempfile.mkdtemp(prefix="sfb-lab-media-")


def _flag(name):
    return lambda html: bool(re.search(r'data-d="[^"]*\b%s\b' % re.escape(name), html))


def _all(*probes):
    return lambda html: all(probe(html) for probe in probes)


def _has(text):
    return lambda html: text in html


# the second text tile of the wide row is the lab's last edit: it adds its colour twice (background + section variable) to the one already there
_TILE_COLOUR_BEFORE_LAST_EDIT = 2


# lab -> (probe for the whole composition, probe for the effect of its LAST edit)
SCENARIOS = {
    "lab_tiles": (_all(_has("--cell-span:5"), _has("--cell-span:3"), _has("--container-gap:18px"), _flag("valign"), _flag("ratio")),
                  lambda html: html.count("#FCE588") > _TILE_COLOUR_BEFORE_LAST_EDIT),
    "lab_hero_panels": (_all(_has("--cell-span:7"), _flag("m-slider2"), _flag("valign")), _has("--d-fit:contain")),
    "lab_advisors": (_all(_flag("m-slider"), _flag("m-stack"), _flag("ratio")), _flag("m-stack")),
    "lab_seventh": (_all(_has('data-mobile-order="reverse"'), _has('data-mobile-mode="slider"'), _has("--gf-o-contact:1"),
                         _has("--gf-cols:3"), _flag("m-slider2")), _has("--gf-o-contact:1")),
}


@override_settings(MEDIA_ROOT=_MEDIA, ALLOWED_HOSTS=[HOST, LAB_HOST, "testserver"])
class CompositionLabEndToEndTests(_LabBase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def picture(self, section):
        row = PromotionalBanner(store=self.store, section=section, is_active=True, display_order=0)
        row.desktop_image = SimpleUploadedFile("lab.png", _PNG, content_type="image/png")
        row.save()

    def chain(self, name):
        probe_all, probe_last = SCENARIOS[name]
        composition_lab.build(name, self.store, self.staff, picture=self.picture, publish=False)
        # Draft + Preview carry it; the public page does not yet
        self.assertTrue(probe_all(self.home_preview()), f"{name}: Preview misses the composition")
        self.assertFalse(probe_all(self.home_public()), f"{name}: an unpublished Draft leaked to the public page")
        # Undo / Redo of the last edit
        self.assertTrue(probe_last(self.home_preview()))
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertFalse(probe_last(self.home_preview()), f"{name}: Undo must remove the last edit")
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertTrue(probe_last(self.home_preview()), f"{name}: Redo must bring it back")
        self.assertTrue(probe_all(self.home_preview()))
        # Publish
        svc.publish(self.store)
        self.assertTrue(probe_all(self.home_public()), f"{name}: the published page misses the composition")

    def test_lab_tiles(self):
        self.chain("lab_tiles")

    def test_lab_hero_panels(self):
        self.chain("lab_hero_panels")

    def test_lab_advisors(self):
        self.chain("lab_advisors")

    def test_lab_seventh(self):
        self.chain("lab_seventh")

    def test_lab_pdp(self):
        composition_lab.build("lab_pdp", self.store, self.staff, publish=False)
        probe = lambda html: (lambda attrs: attrs.get("info-order") == "custom" and attrs.get("gallery-pos") == "end")(_data_attrs(_pdp_tag(html)))
        public_url = reverse("catalog:product-detail", args=[self.product.slug])

        def public():
            response = self.public.get(public_url, HTTP_HOST=LAB_HOST)
            self.assertEqual(response.status_code, 200)
            return response.content.decode()

        self.assertTrue(probe(self._preview()))
        self.assertNotIn('data-info-order="custom"', public())
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertFalse(probe(self._preview()))
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertTrue(probe(self._preview()))
        svc.publish(self.store)
        self.assertTrue(probe(public()))
