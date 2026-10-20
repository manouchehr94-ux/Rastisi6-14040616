"""تست‌های بلوکِ «خبرنامه» — مدل، سرویسِ ثبت، و ویوی عمومی."""

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.content.models import NewsletterSubscriber
from apps.content.services import NewsletterSubscribeError, subscribe_to_newsletter
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(name="فروشگاه دیگر", slug="newsletter-other", admin_subdomain="newsletter-other")


class NewsletterSubscriberModelTests(TestCase):
    def test_unique_per_store(self):
        store = _akhlaghi()
        NewsletterSubscriber.objects.create(store=store, email="a@example.com")
        with self.assertRaises(IntegrityError):
            NewsletterSubscriber.objects.create(store=store, email="a@example.com")

    def test_same_email_allowed_across_different_stores(self):
        NewsletterSubscriber.objects.create(store=_akhlaghi(), email="cross@example.com")
        # هیچ استثنایی نباید پرتاب شود — دی‌دوپ فقط per-store است.
        NewsletterSubscriber.objects.create(store=_other_store(), email="cross@example.com")
        self.assertEqual(NewsletterSubscriber.objects.filter(email="cross@example.com").count(), 2)


class SubscribeToNewsletterServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_email_creates_subscriber(self):
        subscriber, created = subscribe_to_newsletter(self.store, "new@example.com")
        self.assertTrue(created)
        self.assertEqual(subscriber.email, "new@example.com")
        self.assertEqual(subscriber.store_id, self.store.pk)

    def test_resubscribe_is_idempotent_not_an_error(self):
        subscribe_to_newsletter(self.store, "dup@example.com")
        subscriber, created = subscribe_to_newsletter(self.store, "dup@example.com")
        self.assertFalse(created)
        self.assertEqual(NewsletterSubscriber.objects.filter(store=self.store, email="dup@example.com").count(), 1)

    def test_email_normalized_case_and_whitespace(self):
        subscribe_to_newsletter(self.store, "  MixedCase@Example.com  ")
        self.assertTrue(NewsletterSubscriber.objects.filter(store=self.store, email="mixedcase@example.com").exists())

    def test_empty_email_rejected(self):
        with self.assertRaises(NewsletterSubscribeError):
            subscribe_to_newsletter(self.store, "")

    def test_malformed_email_rejected(self):
        with self.assertRaises(NewsletterSubscribeError):
            subscribe_to_newsletter(self.store, "not-an-email")
        self.assertFalse(NewsletterSubscriber.objects.filter(store=self.store).exists())


class NewsletterSubscribeViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_valid_post_subscribes_and_shows_success(self):
        resp = self.client.post(reverse("content:newsletter-subscribe"), {"email": "view-ok@example.com", "consent": "yes"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "متشکریم")
        self.assertTrue(NewsletterSubscriber.objects.filter(store=_akhlaghi(), email="view-ok@example.com").exists())

    def test_invalid_email_shows_error_without_creating_row(self):
        resp = self.client.post(reverse("content:newsletter-subscribe"), {"email": "nope"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(NewsletterSubscriber.objects.filter(store=_akhlaghi(), email="nope").exists())

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("content:newsletter-subscribe"))
        self.assertEqual(resp.status_code, 405)

    def test_rate_limit_blocks_excessive_attempts(self):
        for i in range(8):
            self.client.post(reverse("content:newsletter-subscribe"), {"email": f"rl{i}@example.com", "consent": "yes"})
        resp = self.client.post(reverse("content:newsletter-subscribe"), {"email": "rl-over@example.com", "consent": "yes"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(NewsletterSubscriber.objects.filter(store=_akhlaghi(), email="rl-over@example.com").exists())


class NewsletterConsentContractTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unchecked_consent_never_registers_email(self):
        resp = self.client.post(reverse("content:newsletter-subscribe"), {"email": "no-consent@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "رضایت")
        self.assertFalse(NewsletterSubscriber.objects.filter(email="no-consent@example.com").exists())

    def test_consent_is_scoped_to_host_resolved_store(self):
        from django.test import Client
        from apps.stores.models import Store

        store = _akhlaghi()
        store.admin_subdomain = "akhlaghi"
        store.save(update_fields=["admin_subdomain"])
        client = Client(HTTP_HOST="akhlaghi.rastisi.localhost")
        resp = client.post(reverse("content:newsletter-subscribe"), {
            "email": "subscribed@example.com", "consent": "yes",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(NewsletterSubscriber.objects.filter(store=store, email="subscribed@example.com").exists())
