"""FOLLOWUP-01 — the owner can create an article, write/edit its full text, set the cover and publish explicitly — all in one form."""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.blog.models import BlogPost
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "journaleditor.rastisi.localhost"
_MEDIA = tempfile.mkdtemp(prefix="fu01-media-")


def png(name="c.png"):
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), "teal").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"], MEDIA_ROOT=_MEDIA)
class JournalEditorTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09127920001", password="pass12345")
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127920001", password="pass12345")
        self.create_url = reverse("dashboard:journal-create")

    def make(self, **extra):
        data = {"title": "راهنمای خرید کفش", "excerpt": "خلاصه", "body": "پاراگراف اول\n\nپاراگراف دوم", "category_label": "راهنما", "slug": "", "action": "save"}
        data.update(extra)
        return self.client.post(self.create_url, data)

    def test_the_list_offers_new_article_and_the_form_has_every_field(self):
        self.assertContains(self.client.get(reverse("dashboard:journal-list")), self.create_url)
        html = self.client.get(self.create_url).content.decode()
        for needle in ('name="title"', 'name="excerpt"', 'name="body"', 'name="category_label"', 'name="slug"', 'name="cover_image"', 'name="action"', "ذخیره و انتشار"):
            self.assertIn(needle, html)
        self.assertIn('class="inp"', html)  # same control style as the other admin forms

    def test_a_new_article_is_always_a_draft_and_invisible_publicly(self):
        r = self.make()
        self.assertEqual(r.status_code, 302)
        post = BlogPost.objects.get(title="راهنمای خرید کفش")
        self.assertEqual((post.store_id, post.published_at), (self.store.pk, None))
        self.assertEqual(post.body, "پاراگراف اول\n\nپاراگراف دوم")
        self.assertTrue(post.slug)
        public = self.client.get(f"/journal/{post.slug}/")
        self.assertEqual(public.status_code, 404)

    def test_publish_is_only_by_the_explicit_button(self):
        self.make(action="save")
        self.assertIsNone(BlogPost.objects.get(title="راهنمای خرید کفش").published_at)
        self.make(title="مقالهٔ دوم", action="publish")
        post = BlogPost.objects.get(title="مقالهٔ دوم")
        self.assertIsNotNone(post.published_at)
        self.assertEqual(self.client.get(f"/journal/{post.slug}/").status_code, 200)

    def test_editing_the_body_keeps_status_cover_and_slug_and_shows_on_the_public_page(self):
        self.make(action="publish", cover_image=png())
        post = BlogPost.objects.get(title="راهنمای خرید کفش")
        old_slug, old_cover, published = post.slug, post.cover_image.name, post.published_at
        r = self.client.post(reverse("dashboard:journal-edit", args=[post.pk]), {
            "title": "راهنمای خرید کفش (ویرایش)", "excerpt": "خلاصه", "body": "متنِ تازه\n\nبند دوم", "category_label": "", "slug": "hacked-slug", "action": "save",
        })
        self.assertEqual(r.status_code, 302)
        post.refresh_from_db()
        self.assertEqual((post.slug, post.cover_image.name, post.published_at), (old_slug, old_cover, published))  # published ⇒ slug locked, cover kept
        self.assertEqual(post.body, "متنِ تازه\n\nبند دوم")
        html = self.client.get(f"/journal/{old_slug}/").content.decode()
        self.assertIn("متنِ تازه", html)
        self.assertIn("<p>بند دوم</p>", html)

    def test_slug_rules_for_drafts_uniqueness_and_autogeneration(self):
        self.make(title="مقالهٔ A", slug="my-article")
        self.assertTrue(BlogPost.objects.filter(slug="my-article", store=self.store).exists())
        r = self.make(title="مقالهٔ B", slug="my-article")                       # explicit clash ⇒ form error, nothing created
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "قبلاً استفاده شده")
        self.assertFalse(BlogPost.objects.filter(title="مقالهٔ B").exists())
        self.make(title="مقالهٔ A")                                               # auto slug clash ⇒ suffix, still created
        slugs = list(BlogPost.objects.filter(title="مقالهٔ A").values_list("slug", flat=True))
        self.assertEqual(len(set(slugs)), 2)

    def test_required_fields_and_html_is_never_executed(self):
        r = self.make(title="", body="")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "عنوان مقاله لازم است.")
        self.assertContains(r, "متن مقاله را بنویسید.")
        self.make(title="امنیت", body="<script>alert(1)</script>\n\n<b>x</b>", action="publish")
        post = BlogPost.objects.get(title="امنیت")
        html = self.client.get(f"/journal/{post.slug}/").content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_other_stores_articles_cannot_be_edited_and_legacy_platform_posts_are_not_listed(self):
        other = Store.objects.create(name="B", slug="fu01-other", status=Store.Status.ACTIVE)
        foreign = BlogPost.objects.create(store=other, title="بیگانه", slug="fu01-foreign", body="x", published_at=timezone.now())
        legacy = BlogPost.objects.create(store=None, title="قدیمی", slug="fu01-legacy", body="x", published_at=timezone.now())
        for post in (foreign, legacy):
            url = reverse("dashboard:journal-edit", args=[post.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"title": "x", "body": "y"}).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.title, "بیگانه")

    def test_roles_without_content_permission_cannot_create_or_edit(self):
        analyst = User.objects.create_user(username="09127920002", password="pass12345")
        StoreMembership.objects.create(store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        c = Client(HTTP_HOST=HOST)
        c.login(username="09127920002", password="pass12345")
        self.assertEqual(c.get(self.create_url).status_code, 403)
        self.assertEqual(c.post(self.create_url, {"title": "x", "body": "y"}).status_code, 403)
        self.assertFalse(BlogPost.objects.filter(title="x").exists())
