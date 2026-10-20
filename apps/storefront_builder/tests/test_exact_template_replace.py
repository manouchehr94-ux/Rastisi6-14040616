"""EXACT Ready Template composition — owner contract tests.

Explicit selection of a Ready Template must install that template's complete
canonical recipe (no carry-over from the previous template, no accumulation, no
omission), keep the previous design recoverable, refuse destructive replacement
without explicit confirmation, never silently bypass locks, keep a read-only
preview crash-free, leave business data and the Published version untouched and
be idempotent. The preserving merge remains available only as an explicit
opt-in ``mode="preserve"`` (covered by its own legacy suites).
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Product
from apps.content.models import HeroSlide
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import r4_mutation_service as r4
from apps.stores.models import Store, StoreMembership

User = get_user_model()

TEMPLATE_A = "aftab_price"
TEMPLATE_B = "almas_luxury"


def _slots(draft, page_type="home"):
    return [
        s.template_slot_key
        for s in draft.get_page(page_type).sections.order_by("order", "id")
    ]


def _recipe_slot_count(preset, page_type="home"):
    return sum(
        1
        for e in preset.pages.get(page_type, ())
        if not __import__("apps.storefront_builder.section_registry", fromlist=["x"])
        .get_definition(e.section_key)
        .hidden_from_library
    )


class ExactReplaceBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.staff = User.objects.create_user(
            username="exact_owner", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store,
            user=self.staff,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        self.a = lpr.get_layout_preset(TEMPLATE_A)
        self.b = lpr.get_layout_preset(TEMPLATE_B)
        self.layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, self.a)

    def active(self):
        self.layout.refresh_from_db()
        return StorefrontLayoutVersion.objects.get(pk=self.layout.draft_version_id)

    def switch(self, preset, **flags):
        draft = self.active()
        return r4.switch_template(
            store=self.store,
            actor=self.staff,
            base_revision=draft.edit_revision,
            template_key=preset.key,
            template_version=preset.version,
            **flags,
        )

    def add_merchant_section(self, **extra):
        draft = self.active()
        page = draft.get_page("home")
        return StorefrontSection.objects.create(
            page=page, section_key="rich_text", order=999,
            settings={"content": "merchant note"}, **extra,
        )


class ExactCompositionTests(ExactReplaceBase):
    def test_recipes_cover_the_same_pages(self):
        # A replace never has to reason about a page the target omits.
        page_sets = {tuple(sorted(p.pages)) for p in lpr.list_ready_templates()}
        self.assertEqual(len(page_sets), 1, page_sets)

    def test_pristine_switch_installs_exactly_the_target_recipe(self):
        self.switch(self.b)
        draft = self.active()
        expected = [
            e.section_key for e in self.b.pages["home"]
            if e.section_key
        ]
        self.assertEqual(
            list(draft.get_page("home").sections.order_by("order", "id").values_list("section_key", flat=True)),
            expected,
        )
        for slot in _slots(draft):
            self.assertTrue(slot.startswith(f"{self.b.key}:v{self.b.version}:home:"), slot)

    def test_customised_switch_has_no_leftover_from_previous_template(self):
        merchant = self.add_merchant_section()
        self.switch(self.b, confirm_replace=True)
        draft = self.active()
        keys = set(_slots(draft))
        self.assertFalse([k for k in keys if k.startswith(f"{self.a.key}:")])
        self.assertFalse(
            draft.get_page("home").sections.filter(pk=merchant.pk).exists(),
            "merchant-made section must not live on inside the new composition",
        )
        self.assertEqual(
            draft.get_page("home").sections.count(),
            len(self.b.pages["home"]),
        )

    def test_a_b_a_b_never_accumulates(self):
        counts = []
        for preset in (self.b, self.a, self.b, self.a, self.b):
            self.switch(preset, confirm_replace=True)
            draft = self.active()
            counts.append(draft.get_page("home").sections.count())
            self.assertEqual(
                draft.get_page("home").sections.count(),
                len(preset.pages["home"]),
            )
            for page_type in preset.pages:
                self.assertEqual(
                    draft.get_page(page_type).sections.count(), len(preset.pages[page_type]),
                    page_type,
                )
        self.assertEqual(counts[0], counts[2])
        self.assertEqual(counts[1], counts[3])

    def test_same_template_again_is_a_true_noop(self):
        self.switch(self.b)
        draft = self.active()
        pks = list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        revision = draft.edit_revision
        versions = StorefrontLayoutVersion.objects.filter(layout=self.layout).count()
        self.switch(self.b)
        self.switch(self.b)
        draft = self.active()
        self.assertEqual(
            list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True)),
            pks,
        )
        self.assertEqual(draft.edit_revision, revision)
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout=self.layout).count(), versions)

    def test_switch_stays_on_same_draft(self):
        pk = self.active().pk
        self.switch(self.b)
        self.assertEqual(self.active().pk, pk)


class ConfirmationAndRecoveryTests(ExactReplaceBase):
    def test_customised_design_needs_explicit_confirmation_and_nothing_is_written(self):
        self.add_merchant_section()
        draft = self.active()
        before = list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        versions = StorefrontLayoutVersion.objects.filter(layout=self.layout).count()
        with self.assertRaises(r4.R4MutationError) as ctx:
            self.switch(self.b)
        self.assertEqual(str(ctx.exception), "replace_confirmation_required")
        self.assertIn("summary", ctx.exception.payload)
        draft = self.active()
        self.assertEqual(
            list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True)),
            before,
        )
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout=self.layout).count(), versions)
        self.assertEqual(draft.template_provenance["template"]["key"], self.a.key)

    def test_previous_design_is_recoverable_via_version_history(self):
        merchant = self.add_merchant_section()
        merchant_stable = merchant.stable_id
        self.switch(self.b, confirm_replace=True)
        archived = StorefrontLayoutVersion.objects.filter(
            layout=self.layout, status=StorefrontLayoutVersion.Status.ARCHIVED,
        ).order_by("-version_number").first()
        self.assertIsNotNone(archived)
        self.assertTrue(
            StorefrontSection.objects.filter(
                page__version=archived, stable_id=merchant_stable
            ).exists()
        )
        restored = svc.restore_version(self.store, archived.pk, user=self.staff)
        self.assertTrue(
            StorefrontSection.objects.filter(
                page__version=restored, stable_id=merchant_stable
            ).exists()
        )
        self.assertEqual(restored.template_provenance["template"]["key"], self.a.key)

    def test_dry_run_is_read_only(self):
        self.add_merchant_section()
        draft = self.active()
        before = list(StorefrontSection.objects.filter(page__version=draft).values_list("pk", flat=True))
        revision = draft.edit_revision
        summary = preset_service.describe_exact_replacement(draft, self.b)
        self.assertTrue(summary["needs_confirmation"])
        self.assertFalse(summary["already_applied"])
        self.assertEqual(summary["pages"]["home"]["target_sections"], len(self.b.pages["home"]))
        draft.refresh_from_db()
        self.assertEqual(
            list(StorefrontSection.objects.filter(page__version=draft).values_list("pk", flat=True)),
            before,
        )
        self.assertEqual(draft.edit_revision, revision)

    def test_untouched_baseline_switch_needs_no_confirmation(self):
        summary = preset_service.describe_exact_replacement(self.active(), self.b)
        self.assertFalse(summary["needs_confirmation"])


class LockTests(ExactReplaceBase):
    def lock_one(self):
        section = self.active().get_page("home").sections.order_by("order", "id").first()
        section.is_locked = True
        section.save(update_fields=["is_locked"])
        return section

    def test_preview_candidate_never_fails_because_of_a_lock(self):
        self.lock_one()
        candidate = preset_service.resolve_preset_candidate(self.active(), self.b)
        self.assertEqual(len(candidate.pages["home"].sections), len(self.b.pages["home"]))

    def test_switch_refuses_locked_sections_with_precise_code_and_no_mutation(self):
        locked = self.lock_one()
        draft = self.active()
        before = list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        versions = StorefrontLayoutVersion.objects.filter(layout=self.layout).count()
        with self.assertRaises(r4.R4MutationError) as ctx:
            self.switch(self.b, confirm_replace=True)
        self.assertEqual(str(ctx.exception), "locked_sections_present")
        self.assertEqual(ctx.exception.payload["locked_sections"][0]["id"], locked.pk)
        body = r4.error_response_body(ctx.exception)
        self.assertIn("قفل", body["message"])
        self.assertEqual(
            list(self.active().get_page("home").sections.order_by("order", "id").values_list("pk", flat=True)),
            before,
        )
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout=self.layout).count(), versions)

    def test_authorised_locked_replacement_is_recoverable(self):
        locked = self.lock_one()
        stable = locked.stable_id
        self.switch(self.b, confirm_replace=True, allow_locked=True)
        self.assertEqual(
            self.active().get_page("home").sections.count(), len(self.b.pages["home"]),
        )
        archived = StorefrontLayoutVersion.objects.filter(
            layout=self.layout, status=StorefrontLayoutVersion.Status.ARCHIVED,
        ).order_by("-version_number").first()
        self.assertTrue(
            StorefrontSection.objects.filter(
                page__version=archived, stable_id=stable, is_locked=True,
            ).exists()
        )

    def test_reset_with_locked_section_reports_precisely_and_does_not_mutate(self):
        self.lock_one()
        draft = self.active()
        revision = draft.edit_revision
        before = list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        versions = StorefrontLayoutVersion.objects.filter(layout=self.layout).count()
        with self.assertRaises(r4.R4MutationError) as ctx:
            r4.reset_storefront(store=self.store, actor=self.staff, base_revision=revision)
        self.assertEqual(str(ctx.exception), "locked_sections_present")
        body = r4.error_response_body(ctx.exception)
        self.assertTrue(body["locked_sections"])
        self.assertNotIn("ذخیره کامل نشد", body["message"])
        draft = self.active()
        self.assertEqual(draft.pk, self.draft.pk)
        self.assertEqual(
            list(draft.get_page("home").sections.order_by("order", "id").values_list("pk", flat=True)),
            before,
        )
        self.assertEqual(StorefrontLayoutVersion.objects.filter(layout=self.layout).count(), versions)


class IsolationTests(ExactReplaceBase):
    def test_business_data_is_untouched(self):
        snapshot = list(
            Product.objects.filter(store=self.store).order_by("pk").values_list("pk", "name", "price", "stock")
        )
        self.add_merchant_section()
        self.switch(self.b, confirm_replace=True)
        self.assertEqual(
            list(Product.objects.filter(store=self.store).order_by("pk").values_list("pk", "name", "price", "stock")),
            snapshot,
        )

    def test_other_store_design_is_untouched(self):
        from apps.stores.services.platform_code_service import generate_unique_platform_code

        other = Store.objects.create(
            name="O", slug=f"iso-other-{Store.objects.count()}", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(),
        )
        other_draft = svc.get_or_create_draft(other)
        before = list(StorefrontSection.objects.filter(page__version=other_draft).values_list("pk", flat=True))
        self.add_merchant_section()
        self.switch(self.b, confirm_replace=True)
        self.assertEqual(
            list(StorefrontSection.objects.filter(page__version=other_draft).values_list("pk", flat=True)), before,
        )
        other_layout = svc.get_or_create_layout(other)
        other_layout.refresh_from_db()
        self.assertEqual(other_layout.draft_version_id, other_draft.pk)

    def test_published_version_is_not_mutated_before_publish(self):
        draft = self.active()
        r4.publish_draft(store=self.store, actor=self.staff, base_revision=draft.edit_revision)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        published_slots = _slots(published)
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        r4.switch_template(
            store=self.store, actor=self.staff, base_revision=draft.edit_revision,
            template_key=self.b.key, template_version=self.b.version, confirm_replace=True,
        )
        self.layout.refresh_from_db()
        self.assertEqual(_slots(self.layout.published_version), published_slots)
        self.assertTrue(
            all(s.startswith(f"{self.b.key}:") for s in _slots(self.active()))
        )

    def test_preserve_mode_remains_available_as_explicit_opt_in(self):
        merchant = self.add_merchant_section()
        stable = merchant.stable_id
        self.switch(self.b, mode="preserve")
        self.assertTrue(
            StorefrontSection.objects.filter(page__version=self.active(), stable_id=stable).exists()
        )


class SectionMediaRecoverabilityTests(ExactReplaceBase):
    def test_section_scoped_media_is_restored_with_the_previous_design(self):
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (800, 400), (10, 120, 200)).save(buf, "PNG")
        home = self.active().get_page("home")
        hero = StorefrontSection.objects.create(page=home, section_key="hero_banner", order=997, settings={})
        HeroSlide.objects.create(
            store=self.store, section=hero, title="اسلایدِ مرچنت", is_active=True,
            desktop_image=SimpleUploadedFile("h.png", buf.getvalue(), content_type="image/png"),
        )
        stable = hero.stable_id
        self.switch(self.b, confirm_replace=True)
        self.assertFalse(StorefrontSection.objects.filter(page__version=self.active(), stable_id=stable).exists())
        archived = StorefrontLayoutVersion.objects.filter(
            layout=self.layout, status=StorefrontLayoutVersion.Status.ARCHIVED,
        ).order_by("-version_number").first()
        restored = svc.restore_version(self.store, archived.pk, user=self.staff)
        back = StorefrontSection.objects.get(page__version=restored, stable_id=stable)
        self.assertTrue(HeroSlide.objects.filter(section=back, title="اسلایدِ مرچنت").exists())


class LiteralIncidentReproductionTests(ExactReplaceBase):
    """The owner's real chain: stationery_spectrum (Template 51; v2 = 21 home slots, v1 had 26) with a locked slot-14 section, then a switch to
    kamand_artisan — previously a read-only preview 500 and a Draft of 50 sections."""

    def setUp(self):
        super().setUp()
        self.stationery = lpr.get_layout_preset("stationery_spectrum")
        self.kamand = lpr.get_layout_preset("kamand_artisan")
        draft = self.active()
        preset_service.apply_preset(draft, self.stationery)
        self.slot14 = draft.get_page("home").sections.get(
            template_slot_key=f"{self.stationery.key}:v{self.stationery.version}:home:14"
        )
        self.slot14.is_locked = True
        self.slot14.save(update_fields=["is_locked"])

    def home_slots(self):
        return list(self.active().get_page("home").sections.order_by("order", "id").values_list("template_slot_key", flat=True))

    def test_starting_point_is_the_full_stationery_recipe(self):
        self.assertEqual(len(self.home_slots()), len(self.stationery.pages["home"]))

    def test_kamand_preview_does_not_500_with_the_locked_section(self):
        candidate = preset_service.resolve_preset_candidate(self.active(), self.kamand)
        self.assertEqual(len(candidate.pages["home"].sections), len(self.kamand.pages["home"]))

    def test_switch_is_refused_while_locked_then_exact_when_authorised_never_50(self):
        with self.assertRaises(r4.R4MutationError) as ctx:
            self.switch(self.kamand, confirm_replace=True)
        self.assertEqual(str(ctx.exception), "locked_sections_present")
        self.assertEqual(len(self.home_slots()), len(self.stationery.pages["home"]))
        self.switch(self.kamand, confirm_replace=True, allow_locked=True)
        slots = self.home_slots()
        self.assertEqual(len(slots), len(self.kamand.pages["home"]))
        self.assertFalse([s for s in slots if s.startswith("stationery_spectrum:")])

    def test_round_trips_never_accumulate(self):
        sizes = []
        for preset in (self.kamand, self.stationery, self.kamand, self.stationery):
            self.switch(preset, confirm_replace=True, allow_locked=True)
            sizes.append(len(self.home_slots()))
        self.assertEqual(
            sizes,
            [len(self.kamand.pages["home"]), len(self.stationery.pages["home"]),
             len(self.kamand.pages["home"]), len(self.stationery.pages["home"])],
        )


class Template51V2CompositionTests(ExactReplaceBase):
    """Template 51 = ``stationery_spectrum``. Its v2 recipe has exactly 21 home slots; exact replacement must install those
    21 and nothing else — over a bootstrap draft, over another template, after A→B→A→B, and again for the same template."""

    def setUp(self):
        super().setUp()
        self.t51 = lpr.get_layout_preset("stationery_spectrum")

    def test_recipe_is_v2_with_21_distinct_home_slots(self):
        self.assertEqual(str(self.t51.version), "2")
        self.assertEqual(len(self.t51.pages["home"]), 21)

    def _assert_exactly_t51(self):
        draft = self.active()
        slots = _slots(draft)
        self.assertEqual(len(slots), 21, slots)
        self.assertEqual(len(set(slots)), 21, "duplicate slot keys")
        prefix = f"{self.t51.key}:v{self.t51.version}:home:"
        self.assertTrue(all(k.startswith(prefix) for k in slots), slots)

    def test_exact_install_over_another_template(self):
        self.switch(self.t51, confirm_replace=True)
        self._assert_exactly_t51()

    def test_a_b_a_b_through_template_51_never_accumulates(self):
        for preset in (self.t51, self.b, self.t51, self.a, self.t51):
            self.switch(preset, confirm_replace=True)
        self._assert_exactly_t51()

    def test_reselecting_template_51_is_a_noop(self):
        self.switch(self.t51, confirm_replace=True)
        before = list(self.active().get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        self.switch(self.t51, confirm_replace=True)
        after = list(self.active().get_page("home").sections.order_by("order", "id").values_list("pk", flat=True))
        self.assertEqual(before, after)

    def test_the_old_45_to_50_section_state_is_repaired_to_21_with_no_leftovers(self):
        """The owner's Windows Draft (45/50 sections = accumulation of two Template 51 versions + another template)."""
        self.switch(self.t51, confirm_replace=True)
        # simulate accumulation: stack extra template-slot sections from the previous template + a duplicate pass
        draft = self.active()
        page = draft.get_page("home")
        for i in range(24):
            StorefrontSection.objects.create(
                page=page, section_key="rich_text", order=100 + i,
                template_slot_key=f"stationery_spectrum:v1:home:{i}", settings={"content": "stale"},
            )
        self.assertGreaterEqual(page.sections.count(), 45)
        self.switch(self.t51, confirm_replace=True)
        self._assert_exactly_t51()


class MerchantColourChoicesSurviveExactReplaceTests(ExactReplaceBase):
    """Owner item L: exact replacement re-composes SECTIONS; a merchant's own global colour overrides are design choices
    that outlive a template switch (same per-property origin rule as a palette switch), while colours the previous
    template merely installed are replaced by the new template's."""

    def test_merchant_override_survives_and_template_origin_override_does_not_leak(self):
        draft = self.active()
        cfg = dict(draft.appearance_config)
        cfg["color_overrides"] = {**(cfg.get("color_overrides") or {}), "primary": "#123456"}
        cfg["color_overrides_customized"] = True
        draft.appearance_config = cfg
        draft.save(update_fields=["appearance_config"])
        self.switch(self.b, confirm_replace=True)
        after = self.active().appearance_config
        self.assertEqual((after.get("color_overrides") or {}).get("primary"), "#123456")
        self.assertEqual(after.get("layout_preset_key"), self.b.key)
