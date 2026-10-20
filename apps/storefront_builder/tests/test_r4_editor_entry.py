"""The Studio (R4) is the one editor entry: first visit bootstraps a Draft, ``?page=`` is validated, and the retired
classic URL forwards to it."""

from django.urls import reverse

from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase


class R4EditorEntryTests(StorefrontBuilderViewsTestCase):
    def _editor(self, **params):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor"), params)

    def test_first_visit_creates_a_bootstrapped_draft(self):
        self.assertEqual(self._editor().status_code, 200)
        layout = svc.get_or_create_layout(self.store)
        self.assertIsNotNone(layout.draft_version_id)
        self.assertEqual(layout.draft_version.source, StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP)

    def test_default_and_invalid_page_resolve_to_home(self):
        for params in ({}, {"page": "not-a-page"}):
            response = self._editor(**params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_type"], StorefrontPage.PageType.HOME)

    def test_each_requested_page_is_edited_and_the_switcher_offers_all_six(self):
        for value, _label in StorefrontPage.PageType.choices:
            response = self._editor(page=value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_type"], value)
            self.assertContains(response, f'data-r4-page-type="{value}"')
        content = self._editor().content.decode()
        for value, _label in StorefrontPage.PageType.choices:
            self.assertIn(f'<option value="{value}"', content)

    def test_the_classic_editor_url_forwards_to_the_studio_keeping_the_page(self):
        response = self.client.get(reverse("dashboard:storefront-builder-editor"), {"page": "cart"})
        self.assertRedirects(
            response, reverse("dashboard:storefront-builder-r4-editor") + "?page=cart", fetch_redirect_response=False,
        )
        plain = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertRedirects(plain, reverse("dashboard:storefront-builder-r4-editor"), fetch_redirect_response=False)
