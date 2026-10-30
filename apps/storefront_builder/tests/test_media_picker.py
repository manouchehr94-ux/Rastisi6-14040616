"""Picture picker for the Inspector's ``media`` fields: in-place upload, file names instead of «رسانه #12», per-slot size guidance, and
Store isolation of every picture. Throw-away database only; the real-browser flow lives in ``test_hero_stage_browser`` (opt-in)."""

import json
import re
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.content.models import MediaAsset
from apps.storefront_builder import hero_stage, media_guide
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service as structure
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase

APP = Path(hero_stage.__file__).resolve().parent


def _image(name="pick.png", size=(640, 360), fmt="PNG"):
    buf = BytesIO()
    Image.new("RGB", size, (30, 120, 90)).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(ALLOWED_HOSTS=["*"])
class MediaUploadAndInspectorTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("dashboard:storefront-builder-r4-media-upload")
        self.other_store = Store.objects.create(name="فروشگاه دیگر", slug="mp-other", admin_subdomain="mp-other", status=Store.Status.ACTIVE)
        self.foreign = MediaAsset.objects.create(store=self.other_store, image=_image("foreign-secret.png"))

    def _stage(self):
        return structure.add_section(draft=self.draft, section_key="hero_stage", page_type="home")

    def _inspector(self, section):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))

    # ------------------------------------------------------------------------------------------------------------ upload endpoint
    def test_an_upload_creates_an_asset_in_this_store_only_and_returns_what_the_picker_needs(self):
        response = self.client.post(self.url, {"image": _image("my-hero.png", (1920, 900))})
        self.assertEqual(response.status_code, 200, response.content[:300])
        data = response.json()
        asset = MediaAsset.objects.get(pk=data["id"])
        self.assertEqual(asset.store_id, self.store.pk)
        self.assertTrue(data["name"].startswith("my-hero"))
        self.assertEqual(data["url"], asset.image.url)
        self.assertFalse(MediaAsset.objects.filter(store=self.other_store).exclude(pk=self.foreign.pk).exists())

    def test_a_non_image_an_empty_request_and_a_get_are_refused_without_creating_anything(self):
        before = MediaAsset.objects.count()
        fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
        self.assertEqual(self.client.post(self.url, {"image": fake}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(MediaAsset.objects.count(), before)

    def test_an_oversized_picture_is_refused_with_a_readable_message(self):
        big = SimpleUploadedFile("big.png", b"\x89PNG" + b"0" * (6 * 1024 * 1024), content_type="image/png")
        response = self.client.post(self.url, {"image": big})
        self.assertEqual(response.status_code, 400)
        self.assertIn("مگابایت", response.json()["message"])

    def test_anonymous_and_unprivileged_users_cannot_upload(self):
        self.client.logout()
        before = MediaAsset.objects.count()
        response = self.client.post(self.url, {"image": _image()})
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertEqual(MediaAsset.objects.count(), before)

    # ------------------------------------------------------------------------------------------------------------ inspector markup
    def test_the_stage_inspector_shows_file_names_the_upload_url_and_the_guide_spec_never_another_stores_pictures(self):
        mine = MediaAsset.objects.create(store=self.store, image=_image("brand-banner.png"))
        html = self._inspector(self._stage()).content.decode()
        self.assertIn("data-r4-media-picker", html)
        self.assertIn(f'data-r4-media-upload-url="{self.url}"', html)
        self.assertIn('data-name="brand-banner', html)
        self.assertNotIn(f"رسانه #{mine.pk}", html, "no opaque «رسانه #id» labels")
        self.assertIn('data-r4-field-type="media"', html, "the native select stays the data carrier")
        self.assertNotIn("foreign-secret", html)
        self.assertNotIn(f'value="{self.foreign.pk}"', html)
        spec = json.loads(re.search(r'<script id="r4MediaGuideSpec" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(set(spec["slots"]), set(hero_stage.MEDIA_KEYS))

    def test_a_section_without_a_guide_still_gets_the_shared_picker(self):
        section = structure.add_section(draft=self.draft, section_key="decorative_strip", page_type="home")
        html = self._inspector(section).content.decode()
        self.assertIn("data-r4-media-picker", html)
        self.assertNotIn("r4MediaGuideSpec", html)

    def test_a_picture_of_another_store_is_still_refused_at_write_time(self):
        stage = self._stage()
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": draft.edit_revision, "mutation": {
                "type": "section.update_settings", "section_id": stage.pk, "patch": {"bg_a_media_asset_id": self.foreign.pk}}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content[:200])
        stage.refresh_from_db()
        self.assertNotEqual(stage.settings.get("bg_a_media_asset_id"), self.foreign.pk)


class GuideSpecPinsTests(SimpleTestCase):
    """The Studio computes the guide from these constants: they must mirror what the stylesheet really does."""

    def test_split_fractions_mirror_the_stylesheet_columns(self):
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf8")
        for name, (first, second) in hero_stage.GUIDE_SPLITS.items():
            if name == "equal":
                continue
            match = re.search(rf'data-hs-split="{name}"\] \.hs-bg\{{grid-template-columns:minmax\(0,(\d+)fr\) minmax\(0,(\d+)fr\)\}}', css)
            self.assertIsNotNone(match, name)
            self.assertEqual([int(match.group(1)), int(match.group(2))], [first, second], name)
        self.assertEqual(set(hero_stage.GUIDE_SPLITS), {value for value, _label in dict((k, c) for k, _l, c, *_ in hero_stage.CHOICES)["bg_split"]})

    def test_every_setting_the_guide_depends_on_exists_in_the_schema(self):
        keys = {key for key, *_rest in hero_stage.CHOICES} | {key for key, *_rest in hero_stage.INTEGERS}
        for key in media_guide.spec_for_section("hero_stage")["driven_by"]:
            self.assertIn(key, keys)

    def test_unknown_sections_have_no_spec(self):
        self.assertIsNone(media_guide.spec_for_section("rich_text"))
