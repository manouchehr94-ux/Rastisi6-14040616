from django.test import TestCase
from django.utils import timezone

from .models import BlogPost


class BlogModelsTests(TestCase):
    def test_blogpost_creation(self):
        post = BlogPost.objects.create(
            title="راهنمای خرید کالای دیجیتال",
            slug="digital-buying-guide",
            category_label="راهنمای خرید",
            cover_emoji="🛍️",
            tint="#f1ecfd",
            excerpt="چند نکته‌ی کاربردی برای خرید کالای دیجیتال",
            body="متن کامل مطلب...",
            published_at=timezone.now(),
        )
        self.assertEqual(str(post), "راهنمای خرید کالای دیجیتال")
        self.assertIsNotNone(post.created_at)


class JournalPublicPagesTests(TestCase):
    """The journal uses one published-shell authority and no dead links."""

    def setUp(self):
        from apps.stores.models import Store

        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = "akhlaghi"
        self.store.save(update_fields=["admin_subdomain"])
        self.host = "akhlaghi.rastisi.localhost"

    def test_published_article_is_readable_and_uses_live_store_shell(self):
        post = BlogPost.objects.create(
            slug="journal-article", title="راهنمای نگهداری کیف",
            excerpt="نکات کاربردی برای انتخاب", body="متن کامل و نکات نگهداری",
            published_at=timezone.now(),
        )
        response = self.client.get(post.get_absolute_url(), HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, post.title)
        self.assertContains(response, "متن کامل و نکات نگهداری")
        self.assertContains(response, "بازگشت به مجله")
        index = self.client.get("/journal/", HTTP_HOST=self.host)
        self.assertEqual(index.status_code, 200)
        self.assertContains(index, post.get_absolute_url())

    def test_drafts_and_future_posts_are_not_public(self):
        from datetime import timedelta

        for slug, when in (("draft-private", None), ("future-private", timezone.now() + timedelta(days=3))):
            post = BlogPost.objects.create(slug=slug, title=slug, body="private", published_at=when)
            response = self.client.get(post.get_absolute_url(), HTTP_HOST=self.host)
            self.assertEqual(response.status_code, 404)
        index = self.client.get("/journal/", HTTP_HOST=self.host)
        self.assertNotContains(index, "draft-private")
        self.assertNotContains(index, "future-private")

    def test_missing_cover_has_safe_visual_fallback_without_mutating_data(self):
        post = BlogPost.objects.create(
            slug="missing-photo", title="بدون عکس", body="متن", published_at=timezone.now(),
            cover_image="blog/covers/this-file-does-not-exist.jpg",
        )
        self.assertFalse(post.has_available_cover)
        response = self.client.get("/journal/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "this-file-does-not-exist.jpg")
        post.refresh_from_db()
        self.assertEqual(post.cover_image.name, "blog/covers/this-file-does-not-exist.jpg")


class JournalStoreIsolationTests(TestCase):
    def setUp(self):
        from apps.stores.models import Store, StoreDomain
        from django.test import Client

        self.first = Store.objects.get(slug="akhlaghi")
        self.first.admin_subdomain = "akhlaghi"
        self.first.save(update_fields=["admin_subdomain"])
        self.second = Store.objects.create(
            name="Journal Store B", slug="journal-store-b", admin_subdomain="journal-store-b",
        )
        # With two Stores the single-Store compatibility fallback is disabled.
        # Use a verified test-only public domain, as production resolution does.
        StoreDomain.objects.create(
            store=self.first,
            hostname="akhlaghi.rastisi.localhost",
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.a_client = Client(HTTP_HOST="akhlaghi.rastisi.localhost")

    def test_store_articles_only_visible_in_own_store_and_shell(self):
        from .services import published_posts_for_store

        a = BlogPost.objects.create(
            store=self.first, slug="owner-a", title="مطلب فروشگاه الف",
            body="متن اختصاصی الف", published_at=timezone.now(),
        )
        b = BlogPost.objects.create(
            store=self.second, slug="owner-b", title="مطلب فروشگاه ب",
            body="متن اختصاصی ب", published_at=timezone.now(),
        )
        self.assertIn(a, published_posts_for_store(self.first))
        self.assertNotIn(b, published_posts_for_store(self.first))
        self.assertIn(b, published_posts_for_store(self.second))
        self.assertNotIn(a, published_posts_for_store(self.second))
        index = self.a_client.get("/journal/")
        self.assertEqual(index.status_code, 200)
        self.assertContains(index, a.title)
        self.assertNotContains(index, b.title)
        self.assertEqual(self.a_client.get(a.get_absolute_url()).status_code, 200)
        self.assertEqual(self.a_client.get(b.get_absolute_url()).status_code, 404)

    def test_legacy_platform_post_stays_available_for_backward_compatibility(self):
        from .services import published_posts_for_store
        post = BlogPost.objects.create(
            slug="legacy-global", title="مطلب قدیمی عمومی",
            body="مطلب سراسری", published_at=timezone.now(),
        )
        self.assertIn(post, published_posts_for_store(self.first))
        self.assertIn(post, published_posts_for_store(self.second))
        self.assertEqual(self.a_client.get(post.get_absolute_url()).status_code, 200)


class DemoJournalSeedTests(TestCase):
    def test_idempotent_opt_in_seed_touches_only_demo_articles(self):
        from io import StringIO
        from django.core.management import call_command
        from django.test import override_settings
        from apps.stores.models import Store

        demo = Store.objects.create(
            slug="rasti-mode-demo", admin_subdomain="rasti-mode-demo",
            name="Demo Rasti Mode",
        )
        foreign = Store.objects.get(slug="akhlaghi")
        out = StringIO()
        with override_settings(DEBUG=True):
            call_command("seed_rasti_mode_demo_journal", "--dry-run", stdout=out)
            self.assertEqual(BlogPost.objects.filter(store=demo).count(), 0)
            call_command("seed_rasti_mode_demo_journal", stdout=out)
            self.assertEqual(BlogPost.objects.filter(store=demo).count(), 4)
            self.assertEqual(BlogPost.objects.filter(store=foreign).count(), 0)
            call_command("seed_rasti_mode_demo_journal", stdout=out)
            self.assertEqual(BlogPost.objects.filter(store=demo).count(), 4)
