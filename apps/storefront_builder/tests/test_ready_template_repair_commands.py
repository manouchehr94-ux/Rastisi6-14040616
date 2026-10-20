"""The repair path for an accumulated Draft: a read-only diagnosis and a gated, recoverable, Draft-only apply."""

import io
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Product
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class RepairCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.owner = User.objects.create_user(username="repair_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.owner)
        self.a = lpr.get_layout_preset("aftab_price")
        self.b = lpr.get_layout_preset("almas_luxury")
        preset_service.apply_preset(self.draft, self.a)
        # an "accumulated" Draft: a merchant-made section + a locked old-template section
        home = self.draft.get_page("home")
        StorefrontSection.objects.create(page=home, section_key="rich_text", order=998, settings={"content": "x"})
        first = home.sections.order_by("order", "id").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])

    def run_cmd(self, name, *args):
        out = io.StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def snapshot(self):
        draft = StorefrontLayoutVersion.objects.get(pk=self.draft.pk)
        return (
            draft.edit_revision, draft.template_provenance,
            list(StorefrontSection.objects.filter(page__version=draft).order_by("pk").values_list("pk", flat=True)),
            StorefrontLayoutVersion.objects.filter(layout=draft.layout).count(),
        )

    def test_diagnose_is_strictly_read_only_and_reports_the_leftovers(self):
        before = self.snapshot()
        report = json.loads(self.run_cmd(
            "diagnose_ready_template_composition", "--store", self.store.slug, "--template", self.b.key,
        ))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(report["writes_performed"])
        self.assertTrue(report["replacement"]["locked_sections"])
        self.assertTrue(report["replacement"]["needs_confirmation"])
        home = report["composition"]["home"]
        self.assertGreater(home["from_other_template_or_version_count"], 0)
        self.assertEqual(home["merchant_created_count"], 1)

    def test_apply_without_confirmation_changes_nothing(self):
        before = self.snapshot()
        out = self.run_cmd(
            "apply_ready_template_exact", "--store", self.store.slug, "--template", self.b.key,
            "--actor-username", "repair_owner",
        )
        self.assertIn("هیچ تغییری انجام نشد", out)
        self.assertEqual(self.snapshot(), before)

    def test_locked_sections_block_even_with_confirmation_unless_explicitly_allowed(self):
        before = self.snapshot()
        with self.assertRaises(CommandError) as ctx:
            self.run_cmd(
                "apply_ready_template_exact", "--store", self.store.slug, "--template", self.b.key,
                "--actor-username", "repair_owner", "--confirm-replace",
            )
        self.assertIn("locked_sections_present", str(ctx.exception))
        self.assertEqual(self.snapshot(), before)

    def test_full_repair_is_exact_recoverable_draft_only_and_keeps_business_data(self):
        products = list(Product.objects.filter(store=self.store).order_by("pk").values_list("pk", "price", "stock"))
        published_before = svc.get_or_create_layout(self.store).published_version_id
        self.run_cmd(
            "apply_ready_template_exact", "--store", self.store.slug, "--template", self.b.key,
            "--actor-username", "repair_owner", "--confirm-replace", "--allow-locked",
        )
        draft = StorefrontLayoutVersion.objects.get(pk=self.draft.pk)
        self.assertEqual(draft.get_page("home").sections.count(), len(self.b.pages["home"]))
        self.assertTrue(all(
            s.template_slot_key.startswith(f"{self.b.key}:") for s in draft.get_page("home").sections.all()
        ))
        archived = StorefrontLayoutVersion.objects.filter(
            layout=draft.layout, status=StorefrontLayoutVersion.Status.ARCHIVED,
        )
        self.assertTrue(archived.exists())
        self.assertTrue(StorefrontSection.objects.filter(
            page__version__in=archived, section_key="rich_text", settings={"content": "x"},
        ).exists())
        self.assertEqual(svc.get_or_create_layout(self.store).published_version_id, published_before)
        self.assertEqual(
            list(Product.objects.filter(store=self.store).order_by("pk").values_list("pk", "price", "stock")), products,
        )
        again = self.run_cmd(
            "apply_ready_template_exact", "--store", self.store.slug, "--template", self.b.key,
            "--actor-username", "repair_owner", "--confirm-replace", "--allow-locked",
        )
        self.assertIn("از قبل دقیقاً", again)

    def test_unknown_store_and_template_are_clean_errors(self):
        with self.assertRaises(CommandError):
            self.run_cmd("diagnose_ready_template_composition", "--store", "nope", "--template", self.b.key)
        with self.assertRaises(CommandError):
            self.run_cmd("diagnose_ready_template_composition", "--store", self.store.slug, "--template", "nope")
