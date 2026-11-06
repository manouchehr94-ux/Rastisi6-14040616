"""The public /design/ page and the home shelf must advertise exactly what a seller can choose (PUBLIC-01).

Before: ``/design/`` listed every registered Ready Template (63) while the Studio / merchant gallery / onboarding offered the owner-approved subset (19), so 44 public
templates could not be selected. The public rows now come from the same service and scope as the galleries; these tests pin that and prevent drift in count, key,
version and name, and keep hidden / unregistered / disabled templates off the page. No second registry exists: every assertion reads the shared catalog."""

from django.test import TestCase, override_settings

from apps.portal.public_site import services
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import template_gallery_policy as policy
from apps.storefront_builder.services import ready_template_card_service as cards_service

PUBLIC_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[PUBLIC_HOST, "testserver"])
class PublicDesignCatalogParityTests(TestCase):
    def _gallery(self):
        return cards_service.build_ready_template_cards(None, current_template_key=None, current_template_version=None, scope=cards_service.SCOPE_GALLERY)

    def test_public_rows_are_exactly_the_selectable_gallery_templates(self):
        public = [r["key"] for r in services.ready_template_rows()]
        gallery = [c["preset"].key for c in self._gallery()]
        self.assertEqual(public, gallery)                                   # same set, same order
        self.assertEqual(len(public), len(lpr.list_selectable_templates()))

    def test_every_public_template_is_selectable_and_resolves_to_the_same_version_and_name(self):
        by_key = {c["preset"].key: c["preset"] for c in self._gallery()}
        for row in services.ready_template_rows():
            self.assertTrue(policy.is_selectable_key(row["key"]), row["key"])
            preset = by_key[row["key"]]
            latest = max((p for p in lpr.list_ready_templates() if p.key == row["key"]), key=lambda p: int(p.version))
            self.assertEqual(preset.version, latest.version, f"{row['key']}: public and gallery must show the same (latest) version")
            self.assertEqual(row["name"], preset.label_fa, f"{row['key']}: public name must equal the gallery name")

    def test_a_registered_template_that_is_not_selectable_is_never_shown_publicly(self):
        hidden = [p.key for p in lpr.list_ready_templates() if not policy.is_selectable_key(p.key)]
        self.assertTrue(hidden, "the catalog should still contain registered-but-not-offered templates (this is what drifted)")
        public = {r["key"] for r in services.ready_template_rows()}
        self.assertFalse(public & set(hidden))

    def test_the_design_page_renders_exactly_those_cards_and_the_count_label_matches(self):
        response = self.client.get("/design/", HTTP_HOST=PUBLIC_HOST)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        expected = len(services.ready_template_rows())
        self.assertEqual(html.count('class="tpl"'), expected)
        self.assertIn(str(expected).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")), html)

    def test_the_home_shelf_only_features_selectable_templates(self):
        html = self.client.get("/", HTTP_HOST=PUBLIC_HOST).content.decode()
        self.assertEqual(html.count('class="tpl"'), 4)
        selectable_names = {c["preset"].label_fa for c in self._gallery()}
        for row in services.ready_template_rows():
            self.assertIn(row["name"], selectable_names)

    def test_the_owner_hide_override_still_removes_a_selectable_template_from_the_public_page(self):
        from apps.portal.models import PublicSiteSetting

        key = self._gallery()[0]["preset"].key
        PublicSiteSetting.objects.create(key=f"rt.{key}.hide", value="1")
        self.assertNotIn(key, [r["key"] for r in services.ready_template_rows()])

    def test_lifting_the_restriction_offers_everything_again_to_both_surfaces_together(self):
        with override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False):
            self.assertFalse(policy.is_restricted())
            public = {r["key"] for r in services.ready_template_rows()}
            self.assertEqual(public, {p.key for p in lpr.list_selectable_templates()})
            self.assertEqual(public, {p.key for p in lpr.list_ready_templates()})
