"""RS-02 — journal admin (cover upload/replace/remove in plain language) and the public journal grid contract."""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.blog.models import BlogPost
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "journaladmin.rastisi.localhost"
_MEDIA = tempfile.mkdtemp(prefix="rs02-media-")


def png(name="c.png", color="blue", size=(60, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"], MEDIA_ROOT=_MEDIA)
class JournalAdminTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123600001", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123600001", password="pass12345")
        self.post = BlogPost.objects.create(store=self.store, title="مقاله یک", slug="rs02-one", body="متن", published_at=timezone.now())

    def edit(self, **data):
        payload = {"title": self.post.title, "body": self.post.body, **data}
        return self.client.post(reverse("dashboard:journal-edit", args=[self.post.pk]), payload)

    def test_list_names_the_missing_cover_in_plain_language_and_scopes_to_the_store(self):
        other = Store.objects.create(name="B", slug="rs02-other", status=Store.Status.ACTIVE)
        BlogPost.objects.create(store=other, title="مقاله دیگران", slug="rs02-other-post", body="x", published_at=timezone.now())
        BlogPost.objects.create(store=None, title="سراسری قدیمی", slug="rs02-legacy", body="x", published_at=timezone.now())
        r = self.client.get(reverse("dashboard:journal-list"))
        self.assertContains(r, "مقاله یک")
        self.assertContains(r, "ندارد")
        self.assertContains(r, "تصویر کاور قابل‌نمایش ندارد")
        self.assertNotContains(r, "مقاله دیگران")
        self.assertNotContains(r, "سراسری قدیمی")

    def test_upload_replace_and_remove_cover(self):
        r = self.edit(title="مقاله یک", excerpt="", category_label="", cover_image=png("a.png"))
        self.assertEqual(r.status_code, 302, r.content[:300])
        self.post.refresh_from_db()
        first = self.post.cover_image.name
        self.assertTrue(self.post.has_available_cover)
        self.edit(title="مقاله یک", excerpt="", category_label="", cover_image=png("b.png", "red"))
        self.post.refresh_from_db()
        self.assertNotEqual(self.post.cover_image.name, first)
        self.assertTrue(self.post.cover_image.storage.exists(first), "the replaced file is never deleted from storage")
        self.edit(title="مقاله یک", excerpt="", category_label="", remove_cover="on")
        self.post.refresh_from_db()
        self.assertFalse(self.post.cover_image)
        self.assertTrue(self.post.cover_image.storage.exists(first))

    def test_saving_without_a_file_keeps_the_existing_cover(self):
        self.edit(title="مقاله یک", excerpt="", category_label="", cover_image=png())
        self.post.refresh_from_db()
        name = self.post.cover_image.name
        self.edit(title="عنوان جدید", excerpt="خلاصه", category_label="")
        self.post.refresh_from_db()
        self.assertEqual((self.post.cover_image.name, self.post.title), (name, "عنوان جدید"))

    def test_non_images_oversized_and_svg_are_refused_without_a_500(self):
        bad = SimpleUploadedFile("x.png", b"<html><script>alert(1)</script></html>", content_type="image/png")
        r = self.edit(title="مقاله یک", excerpt="", category_label="", cover_image=bad)
        self.assertEqual(r.status_code, 200)
        svg = SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml")
        self.assertEqual(self.edit(title="مقاله یک", excerpt="", category_label="", cover_image=svg).status_code, 200)
        self.post.refresh_from_db()
        self.assertFalse(self.post.cover_image)

    def test_a_missing_cover_file_is_reported_not_hidden(self):
        self.post.cover_image.save("gone.png", ContentFile(png().read()))
        self.post.cover_image.storage.delete(self.post.cover_image.name)
        r = self.client.get(reverse("dashboard:journal-list"))
        self.assertContains(r, "فایل تصویر پیدا نشد")
        self.assertContains(self.client.get(reverse("dashboard:journal-edit", args=[self.post.pk])), "پیدا نشد")

    def test_foreign_or_legacy_posts_404_and_permissions_and_csrf_hold(self):
        other = Store.objects.create(name="B", slug="rs02-o2", status=Store.Status.ACTIVE)
        foreign = BlogPost.objects.create(store=other, title="f", slug="rs02-f", body="x")
        legacy = BlogPost.objects.create(store=None, title="l", slug="rs02-l", body="x")
        for post in (foreign, legacy):
            self.assertEqual(self.client.get(reverse("dashboard:journal-edit", args=[post.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("dashboard:journal-publish", args=[post.pk])).status_code, 404)
        analyst = User.objects.create_user(username="09123600002", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        c = Client(HTTP_HOST=HOST)
        c.login(username="09123600002", password="pass12345")
        self.assertEqual(c.get(reverse("dashboard:journal-list")).status_code, 403)
        c2 = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        c2.login(username="09123600001", password="pass12345")
        self.assertEqual(c2.post(reverse("dashboard:journal-publish", args=[self.post.pk])).status_code, 403)

    def test_publish_toggle(self):
        self.client.post(reverse("dashboard:journal-publish", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertIsNone(self.post.published_at)
        self.client.post(reverse("dashboard:journal-publish", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.published_at)


@override_settings(MEDIA_ROOT=_MEDIA)
class PublicJournalTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.posts = [
            BlogPost.objects.create(store=self.store, title=f"مقاله {i}", slug=f"rs02-pub-{i}", body="متن", published_at=timezone.now())
            for i in range(4)
        ]

    def test_cover_is_used_on_the_card_and_the_article_and_without_it_a_slim_band(self):
        with_cover = self.posts[0]
        with_cover.cover_image.save("p.png", ContentFile(png().read()))
        index = self.client.get(reverse("blog:index")).content.decode()
        self.assertEqual(index.count("journal-tile"), 4 + index.count("journal-tile-copy"))  # 4 tiles (+ their copy divs)
        self.assertIn(with_cover.cover_image.url, index)
        self.assertEqual(index.count("journal-cover--none"), 3)
        detail = self.client.get(reverse("blog:detail", args=[with_cover.slug])).content.decode()
        self.assertIn("journal-article-cover", detail)
        self.assertIn(with_cover.cover_image.url, detail)
        self.assertNotIn("journal-article-cover", self.client.get(reverse("blog:detail", args=[self.posts[1].slug])).content.decode())

    def test_grid_css_is_four_two_one(self):
        from pathlib import Path

        css = (Path(__file__).resolve().parents[2] / "storefront_builder" / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn(".journal-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))", css)
        self.assertIn("@media(max-width:1000px){.journal-grid{grid-template-columns:repeat(2,minmax(0,1fr))", css)
        self.assertIn("@media(max-width:560px){.journal-grid{grid-template-columns:1fr}", css)
