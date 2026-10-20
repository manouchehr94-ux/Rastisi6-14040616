from pathlib import Path


from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase33BuilderUXCompletionTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)


    def test_rich_text_registry_name_is_plain_merchant_language(self):
        definition = section_registry.get_definition("rich_text")
        self.assertEqual(definition.label_fa, "متن")
        self.assertIn("پاراگراف", definition.description_fa)
        self.assertIn("HTML", definition.description_fa)


    def test_base_admin_storefront_editor_toolbar_is_intentionally_small(self):
        base = (
            Path(__file__).resolve().parents[2]
            / "dashboard"
            / "templates"
            / "dashboard"
            / "base_admin.html"
        ).read_text(encoding="utf-8")
        start = base.index("function storefrontRichTextEditor()")
        end = base.index("\n</script>", start)
        function = base[start:end]
        for key in ('"heading"', '"bold"', '"italic"', '"bulletedList"', '"numberedList"', '"link"'):
            self.assertIn(key, function)
        self.assertNotIn('"uploadImage"', function)
        self.assertNotIn('"mediaEmbed"', function)
        self.assertNotIn('"insertTable"', function)
