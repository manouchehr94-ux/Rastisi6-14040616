"""What the Studio actually receives when the server refuses a template switch / reset / preview: a stable code, a
precise Persian message (never the generic "save incomplete"), the exact locked sections — and NOTHING was mutated."""

import json

from django.urls import reverse

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import preset_service

from .test_r4_mutation_api import R4MutationApiTestCase


class RefusalHttpContractTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.a = lpr.get_layout_preset("aftab_price")
        self.b = lpr.get_layout_preset("almas_luxury")
        preset_service.apply_preset(self.draft, self.a)
        self.draft.refresh_from_db()
        home = self.draft.get_page("home")
        self.locked = home.sections.order_by("order", "id").first()
        self.locked.is_locked = True
        self.locked.save(update_fields=["is_locked"])

    def post(self, name, payload):
        return self.client.post(
            reverse(f"dashboard:storefront-builder-r4-{name}"),
            data=json.dumps(payload), content_type="application/json",
        )

    def state(self):
        draft = StorefrontLayoutVersion.objects.get(pk=self.draft.pk)
        return (
            draft.edit_revision,
            list(StorefrontSection.objects.filter(page__version=draft).order_by("pk").values_list("pk", flat=True)),
            StorefrontLayoutVersion.objects.filter(layout=draft.layout).count(),
        )

    def test_reset_storefront_with_a_locked_section_is_a_precise_400_and_changes_nothing(self):
        before = self.state()
        response = self.post("reset-storefront", {"base_revision": self.draft.edit_revision})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "locked_sections_present")
        self.assertIn("قفل", body["message"])
        self.assertEqual([s["id"] for s in body["locked_sections"]], [self.locked.pk])
        self.assertNotIn("ذخیره کامل نشد", body["message"])
        self.assertEqual(self.state(), before)

    def test_reset_page_with_a_locked_section_is_the_same_precise_400(self):
        before = self.state()
        response = self.post("reset-page", {"base_revision": self.draft.edit_revision, "page_type": "home"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "locked_sections_present")
        self.assertEqual(self.state(), before)

    def test_switch_template_reports_locked_sections_then_confirmation(self):
        before = self.state()
        payload = {
            "base_revision": self.draft.edit_revision,
            "template_key": self.b.key, "template_version": self.b.version,
        }
        locked = self.post("switch-template", payload)
        self.assertEqual(locked.status_code, 400)
        self.assertEqual(locked.json()["code"], "locked_sections_present")
        self.assertEqual(self.state(), before)
        self.locked.is_locked = False
        self.locked.save(update_fields=["is_locked"])
        StorefrontSection.objects.create(
            page=self.draft.get_page("home"), section_key="rich_text", order=999, settings={"content": "x"},
        )
        unconfirmed = self.post("switch-template", payload)
        self.assertEqual(unconfirmed.status_code, 400)
        body = unconfirmed.json()
        self.assertEqual(body["code"], "replace_confirmation_required")
        self.assertIn("summary", body)
        self.assertIn("تأیید", body["message"])
        confirmed = self.post("switch-template", {**payload, "confirm_replace": True})
        self.assertEqual(confirmed.status_code, 200)

    def test_read_only_template_preview_survives_a_locked_section(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-template-live-preview", args=[self.b.key]) + "?data=merchant",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.state()[0], self.draft.edit_revision)

    def test_stale_revision_is_still_a_409_not_a_known_refusal(self):
        response = self.post("reset-storefront", {"base_revision": self.draft.edit_revision + 5})
        self.assertEqual(response.status_code, 409)
