"""ARCH-02b — the Design Studio gallery is the ONE official experience to preview, choose and apply a template.

* The old dashboard gallery URL and every dashboard link to it forward to the Studio gallery and open it directly.
* Following that URL writes nothing; access control is unchanged.
* The old "apply" endpoint and the Studio's own switch lead to the SAME Draft result (one service, no second path);
  non-ready structural presets are refused without a write.
* Apply changes the Draft only — Published is untouched until an explicit Publish.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import apps.storefront_builder as sfb_package
from apps.dashboard import navigation
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import r4_mutation_service as r4
from apps.storefront_builder.tests._gallery_support import legacy_gallery_url
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "sfb-arch02b.rastisi.localhost"
TEMPLATE = "almas_luxury"


def _design(draft):
    """The template-owned design of a Draft, comparable across Drafts (no ids)."""
    draft.refresh_from_db()
    pages = {}
    for page_type, _label in StorefrontPage.PageType.choices:
        page = draft.get_page(page_type)
        pages[page_type] = [
            (s.section_key, s.settings, s.row_key, s.row_span, s.template_slot_key)
            for s in page.sections.order_by("order", "id")
        ]
    return {
        "pages": pages,
        "appearance": draft.appearance_config,
        "header": draft.header_config,
        "footer": draft.footer_config,
        "provenance": draft.template_provenance,
    }


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class GalleryUnificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="arch02b_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="arch02b_owner", password="pass12345")
        self.studio_url = reverse("dashboard:storefront-builder-r4-editor")
        self.preset = lpr.get_layout_preset(TEMPLATE)

    # ------------------------------------------------------------ redirect + access
    def test_old_gallery_url_forwards_to_the_studio_and_opens_the_gallery(self):
        response = self.client.get(legacy_gallery_url())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{self.studio_url}?open=templates")
        final = self.client.get(response["Location"])
        self.assertEqual(final.status_code, 200)
        self.assertContains(final, 'data-rastisi-action="templates"')

    def test_the_studio_script_opens_the_gallery_from_the_deep_link_without_writing(self):
        js = (Path(sfb_package.__file__).parent / "static" / "storefront_builder" / "r4_studio.js").read_text(
            encoding="utf-8",
        )
        self.assertIn("deepParams.get('open') === 'templates'", js)
        self.assertIn("openTemplateGallery();", js[js.index("deepParams.get('open')"):])
        self.assertIn("history.replaceState", js[js.index("deepParams.get('open')"):])

    def test_the_old_gallery_page_and_its_script_are_gone(self):
        root = Path(sfb_package.__file__).parent
        self.assertFalse((root / "templates" / "dashboard" / "storefront_builder" / "template_gallery.html").exists())
        self.assertFalse((root / "static" / "storefront_builder" / "template_gallery_preview.js").exists())

    def test_dashboard_navigation_leads_to_the_studio_gallery(self):
        store_section = next(section for section in navigation.SECTIONS if section.key == "store")
        tab = next(t for t in store_section.tabs if t.key == "templates")
        url = reverse(f"dashboard:{tab.url_name}")
        response = self.client.get(url, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], f"{self.studio_url}?open=templates")
        self.assertEqual(response.status_code, 200)

    def test_live_preview_back_link_returns_to_the_studio_gallery(self):
        layout = svc.get_or_create_layout(self.store)
        svc.get_or_create_draft(self.store, user=self.staff)
        self.assertIsNotNone(layout)
        response = self.client.get(
            reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": TEMPLATE}), {"data": "merchant"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{legacy_gallery_url()}"')
        self.assertContains(response, "Design Studio")

    def test_access_control_is_unchanged(self):
        anonymous = Client(HTTP_HOST=HOST).get(legacy_gallery_url())
        self.assertNotEqual(anonymous.status_code, 200)
        self.assertNotIn(self.studio_url, anonymous.get("Location", ""))
        outsider = User.objects.create_user(username="arch02b_outsider", password="pass12345", is_staff=True)
        client = Client(HTTP_HOST=HOST)
        client.login(username="arch02b_outsider", password="pass12345")
        response = client.get(legacy_gallery_url())
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn(f"{self.studio_url}?open=templates", response.get("Location", ""))
        self.assertIsNotNone(outsider.pk)

    def test_following_the_old_url_writes_nothing(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        before = (
            StorefrontLayoutVersion.objects.count(), draft.pk, draft.edit_revision, _design(draft),
            StorefrontLayout.objects.get(store=self.store).published_version_id,
        )
        self.client.get(legacy_gallery_url(), {"page": "home"})
        draft.refresh_from_db()
        after = (
            StorefrontLayoutVersion.objects.count(), draft.pk, draft.edit_revision, _design(draft),
            StorefrontLayout.objects.get(store=self.store).published_version_id,
        )
        self.assertEqual(before, after)

    def test_with_no_draft_the_old_url_creates_none(self):
        # Published only, no active Draft (as right after a Publish): the forwarding itself must not create one.
        svc.get_or_create_draft(self.store, user=self.staff)
        svc.publish(self.store, user=self.staff)
        layout = StorefrontLayout.objects.get(store=self.store)
        self.assertIsNone(layout.draft_version_id)
        versions = StorefrontLayoutVersion.objects.count()
        self.client.get(legacy_gallery_url())
        layout.refresh_from_db()
        self.assertIsNone(layout.draft_version_id)
        self.assertEqual(StorefrontLayoutVersion.objects.count(), versions)

    # ------------------------------------------------------------ one Draft-changing path
    def test_legacy_apply_endpoint_and_the_studio_switch_produce_the_same_draft_design(self):
        svc.get_or_create_draft(self.store, user=self.staff)
        response = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": TEMPLATE, "confirm_preset_apply": "1"},
        )
        self.assertEqual(response.status_code, 302)
        via_endpoint = _design(svc.get_or_create_draft(self.store, user=self.staff))

        svc.discard_draft(self.store)
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        r4.switch_template(
            store=self.store, actor=self.staff, base_revision=draft.edit_revision,
            template_key=self.preset.key, template_version=self.preset.version, confirm_replace=True,
        )
        via_studio = _design(svc.get_or_create_draft(self.store, user=self.staff))
        self.assertEqual(via_endpoint, via_studio)
        self.assertEqual(via_studio["provenance"]["template"]["key"], TEMPLATE)

    def test_apply_changes_the_draft_only_never_published(self):
        svc.get_or_create_draft(self.store, user=self.staff)
        published = svc.publish(self.store, user=self.staff)
        fingerprint = published.compute_fingerprint()
        svc.get_or_create_draft(self.store, user=self.staff)
        self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": TEMPLATE, "confirm_preset_apply": "1"},
        )
        published.refresh_from_db()
        layout = StorefrontLayout.objects.get(store=self.store)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertEqual(published.status, StorefrontLayoutVersion.Status.PUBLISHED)
        self.assertEqual(published.compute_fingerprint(), fingerprint)
        self.assertEqual(layout.draft_version.template_provenance["template"]["key"], TEMPLATE)

    def test_a_structural_preset_is_refused_without_any_write_by_the_old_endpoint(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        before = (draft.pk, draft.edit_revision, _design(draft), StorefrontLayoutVersion.objects.count())
        response = self.client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.studio_url)
        draft.refresh_from_db()
        self.assertEqual(before, (draft.pk, draft.edit_revision, _design(draft), StorefrontLayoutVersion.objects.count()))

    def test_an_unknown_preset_key_is_refused_without_any_write(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        before = (draft.edit_revision, _design(draft))
        response = self.client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "nope"})
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(before, (draft.edit_revision, _design(draft)))

    def test_the_old_apply_endpoint_is_post_only_and_staff_only(self):
        anonymous = Client(HTTP_HOST=HOST).post(
            reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": TEMPLATE, "confirm_preset_apply": "1"},
        )
        self.assertNotEqual(anonymous.status_code, 200)
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        draft.refresh_from_db()
        self.assertNotEqual(draft.template_provenance.get("template", {}).get("key"), TEMPLATE)
