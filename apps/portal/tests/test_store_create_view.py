from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.catalog.models import IndustryTemplate
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StoreCreateViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner@example.com", email="owner@example.com", password="a-very-strong-pass-1",
        )
        self.client.force_login(self.owner)

    def _get_token(self):
        response = self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        return response.context["submission_token"]

    def test_get_renders_form(self):
        response = self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فروشگاه تازه بسازید")

    def test_post_creates_store_and_redirects_to_success_page(self):
        token = self._get_token()
        response = self.client.post(
            "/app/stores/new/", {"name": "My New Shop", "submission_token": token}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Store.objects.filter(name="My New Shop").exists())
        store = Store.objects.get(name="My New Shop")
        self.assertIn(str(store.public_id), response["Location"])

    def test_success_page_shows_trial_hostname(self):
        token = self._get_token()
        response = self.client.post(
            "/app/stores/new/", {"name": "Show Case Shop", "submission_token": token}, HTTP_HOST=_HOST,
            follow=True,
        )
        store = Store.objects.get(name="Show Case Shop")
        self.assertContains(response, store.platform_code)

    def test_reused_submission_token_does_not_create_a_second_store(self):
        token = self._get_token()
        self.client.post("/app/stores/new/", {"name": "Once Shop", "submission_token": token}, HTTP_HOST=_HOST)
        # Same token, resubmitted (e.g. back-button double submit) — must be rejected.
        response = self.client.post(
            "/app/stores/new/", {"name": "Once Shop Retry", "submission_token": token}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Store.objects.filter(name="Once Shop Retry").exists())
        self.assertEqual(Store.objects.filter(name__startswith="Once Shop").count(), 1)

    def test_missing_or_wrong_token_is_rejected(self):
        response = self.client.post(
            "/app/stores/new/", {"name": "No Token Shop", "submission_token": "bogus"}, HTTP_HOST=_HOST,
        )
        self.assertFalse(Store.objects.filter(name="No Token Shop").exists())

    def test_store_create_requires_login(self):
        self.client.logout()
        response = self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    @override_settings(RASTISI_MAX_STORES_PER_OWNER=0)
    def test_shows_error_message_when_over_cap(self):
        token = self._get_token()
        response = self.client.post(
            "/app/stores/new/", {"name": "Over Cap Shop", "submission_token": token}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Store.objects.filter(name="Over Cap Shop").exists())

    def test_store_creation_never_installs_an_industry_template(self):
        """Policy: the irreversible one-time install lives only on the onboarding «صنف» step behind a
        server-validated acknowledgement. Even a hand-forged ``industry_template_id`` (with or without a
        confirmation flag, offerable or not) must not install anything at store creation."""
        from apps.catalog.models import Category, StoreIndustryInstallation

        template = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        held = IndustryTemplate.objects.create(
            slug="held-skeleton", name="نیازمند بازبینی", version=1,
            readiness=IndustryTemplate.Readiness.REVIEW_REQUIRED, is_active=True,
        )
        for index, extra in enumerate((
            {"industry_template_id": template.pk},
            {"industry_template_id": template.pk, "confirm_industry_install": "1"},
            {"industry_template_id": held.pk, "confirm_industry_install": "1"},
        )):
            with self.subTest(extra=extra):
                token = self._get_token()
                name = f"Clothing Co {index}"
                response = self.client.post(
                    "/app/stores/new/", {"name": name, "submission_token": token, **extra}, HTTP_HOST=_HOST,
                )
                self.assertEqual(response.status_code, 302)
                store = Store.objects.get(name=name)
                self.assertFalse(StoreIndustryInstallation.objects.filter(store=store).exists())
                self.assertEqual(Category.objects.filter(store=store).count(), 0)

    def test_page_has_no_industry_selector_and_points_to_the_onboarding_step(self):
        IndustryTemplate.objects.create(
            slug="clothing-page", name="پوشاکِ صفحه", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=True,
        )
        response = self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "پوشاکِ صفحه")
        self.assertNotContains(response, "industry_template_id")
        self.assertContains(response, "در این صفحه هیچ قالبی نصب نمی‌شود")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StoreCreatedViewIsolationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner@example.com", email="owner@example.com", password="a-very-strong-pass-1",
        )
        self.other = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="a-very-strong-pass-1",
        )

    def test_other_owner_cannot_view_someone_elses_success_page(self):
        self.client.force_login(self.owner)
        token = self.client.get("/app/stores/new/", HTTP_HOST=_HOST).context["submission_token"]
        self.client.post(
            "/app/stores/new/", {"name": "Private Shop", "submission_token": token}, HTTP_HOST=_HOST,
        )
        store = Store.objects.get(name="Private Shop")

        self.client.force_login(self.other)
        response = self.client.get(f"/app/stores/{store.public_id}/created/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)
