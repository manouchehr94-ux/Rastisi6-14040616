"""Regression tests for owner-managed public-site photography."""

import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.portal.models import PlatformAuditLogEntry, PublicSitePhoto


ADMIN_HOST = "platformadmins.rastisi.localhost"
PUBLIC_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class PublicSitePhotoManagementTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name, MEDIA_URL="/media/")
        storage.enable()
        self.addCleanup(storage.disable)

        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="photo-platform-owner", password="secure-pass-2026",
            is_staff=True, is_superuser=True,
        )
        self.other = user_model.objects.create_user(
            username="photo-store-owner", password="secure-pass-2026",
        )

    def _image(self, filename="photo.png"):
        stream = io.BytesIO()
        Image.new("RGB", (32, 32), (160, 180, 160)).save(stream, format="PNG")
        return SimpleUploadedFile(filename, stream.getvalue(), content_type="image/png")

    def test_public_page_falls_back_to_bundled_photo(self):
        response = self.client.get("/", HTTP_HOST=PUBLIC_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/portal/images/public/stilllife.webp")

    def test_platform_owner_can_upload_and_public_page_uses_override(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/public-photos/stilllife/",
            {"image": self._image(), "alt_text": "محصولات سرامیکی جدید"},
            HTTP_HOST=ADMIN_HOST,
        )
        self.assertEqual(response.status_code, 302)
        photo = PublicSitePhoto.objects.get(slot="stilllife")
        self.assertEqual(photo.updated_by, self.owner)
        self.assertEqual(photo.alt_text, "محصولات سرامیکی جدید")
        self.assertTrue(photo.image.name.startswith("portal/public-photos/"))
        response = self.client.get("/", HTTP_HOST=PUBLIC_HOST)
        self.assertContains(response, "/media/" + photo.image.name)
        self.assertContains(response, "محصولات سرامیکی جدید")
        self.assertTrue(
            PlatformAuditLogEntry.objects.filter(
                action_code="platform_admin.public_photo_saved", object_id="stilllife",
            ).exists(),
        )

    def test_reset_restores_static_image(self):
        self.client.force_login(self.owner)
        self.client.post(
            "/public-photos/stilllife/",
            {"image": self._image(), "alt_text": "تصویر جدید"},
            HTTP_HOST=ADMIN_HOST,
        )
        response = self.client.post(
            "/public-photos/stilllife/reset/", HTTP_HOST=ADMIN_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PublicSitePhoto.objects.filter(slot="stilllife").exists())
        response = self.client.get("/", HTTP_HOST=PUBLIC_HOST)
        self.assertContains(response, "/static/portal/images/public/stilllife.webp")

    def test_non_platform_user_cannot_modify_public_photos(self):
        self.client.force_login(self.other)
        response = self.client.post(
            "/public-photos/stilllife/",
            {"image": self._image(), "alt_text": "غیرمجاز"},
            HTTP_HOST=ADMIN_HOST,
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(PublicSitePhoto.objects.exists())

    def test_invalid_image_is_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/public-photos/stilllife/",
            {"image": SimpleUploadedFile(
                "not-a-photo.png", b"not-an-image", content_type="image/png",
            ), "alt_text": "نامعتبر"},
            HTTP_HOST=ADMIN_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PublicSitePhoto.objects.exists())
        self.assertContains(response, "تصویر")

    def test_disallowed_svg_extension_is_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/public-photos/stilllife/",
            {"image": self._image("photo.svg"), "alt_text": "نامعتبر"},
            HTTP_HOST=ADMIN_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PublicSitePhoto.objects.exists())

    def test_unknown_slot_is_not_editable(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/public-photos/unlisted/",
            {"image": self._image(), "alt_text": "غیرمجاز"},
            HTTP_HOST=ADMIN_HOST,
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(PublicSitePhoto.objects.exists())
