
from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase34NaturalHeightAndAnnouncementTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)


    def test_announcement_links_accept_internal_external_and_phone_toggle(self):
        cleaned = layout_service.validate_header_config({
            "show_search": True,
            "show_account": True,
            "show_cart": True,
            "show_wishlist": True,
            "sticky": True,
            "announcement_enabled": True,
            "announcement_text": "پیام",
            "announcement_links": [
                {"label": "پیگیری", "url": "/track/"},
                {"label": "راهنما", "url": "https://example.com/help"},
            ],
            "announcement_show_phone": False,
        })
        self.assertEqual(cleaned["announcement_links"][0], {"label": "پیگیری", "url": "/track/"})
        self.assertEqual(cleaned["announcement_links"][1]["label"], "راهنما")
        self.assertFalse(cleaned["announcement_show_phone"])

    def test_announcement_rejects_unsafe_link_scheme(self):
        with self.assertRaises(layout_service.HeaderConfigValidationError):
            layout_service.validate_header_config({
                "show_cart": True,
                "announcement_links": [{"label": "بد", "url": "javascript:alert(1)"}],
            })


    def test_preview_renders_configured_announcement_and_direct_edit_control(self):
        self.draft.header_config = {
            **self.draft.effective_header_config(),
            "announcement_enabled": True,
            "announcement_text": "اعلان قابل ویرایش",
            "announcement_links": [
                {"label": "رهگیری من", "url": "/my-track/"},
                {"label": "کمک", "url": "#help"},
            ],
            "announcement_show_phone": False,
        }
        self.draft.save(update_fields=["header_config", "updated_at"])

        response = self.client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=home"
        )
        html = response.content.decode("utf-8")
        self.assertIn("اعلان قابل ویرایش", html)
        self.assertIn('href="/my-track/"', html)
        self.assertIn(">رهگیری من</a>", html)
        self.assertNotIn('class="sfb-announcement-phone"', html)
        # V5-UI-014: the strip is selected like any Section (standard R4 toolbar → «ویرایش»); the old in-bar «⚙ ویرایش» button is gone
        self.assertIn('data-section-id="announcement"', html)
        self.assertNotIn("sfb-announcement-edit-button", html)
