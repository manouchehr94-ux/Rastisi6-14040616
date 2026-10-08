from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import (
    Category,
    IndustryTemplate,
    IndustryTemplateAttribute,
    IndustryTemplateAttributeValue,
    IndustryTemplateCategory,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.industry_templates.registry import (
    ALL_INDUSTRY_TEMPLATES as INDUSTRY_TEMPLATES,
    DEPRECATED_LEGACY_SLUGS,
)
from apps.catalog.services.industry_template_service import install_industry_template
from apps.stores.models import Store


def _run_seed():
    call_command("seed_industry_templates", stdout=StringIO())


class SeedIndustryTemplatesCommandTests(TestCase):
    def test_creates_expected_number_of_templates(self):
        _run_seed()
        self.assertEqual(IndustryTemplate.objects.count(), len(INDUSTRY_TEMPLATES))
        self.assertGreaterEqual(len(INDUSTRY_TEMPLATES), 30)

    def test_seed_converges_readiness_to_the_merchant_completeness_gate(self):
        """Structural validity alone is not enough: after seeding, a template
        is PRODUCTION_READY only when the sector-aware completeness gate
        (``template_validation_service``) agrees; otherwise it is
        REVIEW_REQUIRED and therefore never offered to merchants."""
        from apps.catalog.services import template_validation_service as tvs

        _run_seed()
        for template in IndustryTemplate.objects.exclude(slug__in=DEPRECATED_LEGACY_SLUGS):
            with self.subTest(template=template.slug):
                expected = tvs.validate_industry_template(template).recommended_readiness
                self.assertEqual(template.readiness, expected)
                self.assertIn(
                    template.readiness,
                    (IndustryTemplate.Readiness.PRODUCTION_READY, IndustryTemplate.Readiness.REVIEW_REQUIRED),
                )
                self.assertTrue(template.content_fingerprint)
        self.assertTrue(
            IndustryTemplate.objects.filter(readiness=IndustryTemplate.Readiness.PRODUCTION_READY).exists()
        )
        # صنف‌های قدیمیِ منسوخ‌شده (بدونِ تناظرِ یک‌به‌یک با کاتالوگِ تأییدشده‌ی
        # ۱۰۰ صنفی) عمداً پس از seed غیرفعال/منسوخ می‌شوند — رکوردشان می‌ماند،
        # اما دیگر برای نصبِ جدید پیشنهاد نمی‌شوند (نگاه کنید به بخشِ ۱).
        for template in IndustryTemplate.objects.filter(slug__in=DEPRECATED_LEGACY_SLUGS):
            with self.subTest(template=template.slug):
                self.assertEqual(template.readiness, IndustryTemplate.Readiness.DEPRECATED)
                self.assertFalse(template.is_active)

    def test_every_template_slug_is_seeded_and_active(self):
        _run_seed()
        seeded_slugs = set(IndustryTemplate.objects.values_list("slug", flat=True))
        expected_slugs = {entry["slug"] for entry in INDUSTRY_TEMPLATES}
        self.assertEqual(seeded_slugs, expected_slugs)
        inactive_slugs = set(IndustryTemplate.objects.filter(is_active=False).values_list("slug", flat=True))
        self.assertEqual(inactive_slugs, set(DEPRECATED_LEGACY_SLUGS))

    def test_every_template_has_real_categories_and_attributes(self):
        """صنف‌های غنی (دستی) همچنان معیارِ قدیمی را دارند؛ صنف‌های «کمینه‌یِ
        مفید» (بخشِ ۹ — یک دسته‌بندیِ تک‌سطحی + چند ویژگیِ متنی، یا برایِ
        رستهِ خدماتی/سایر حتی بدونِ ویژگی) فقط باید حداقل یک دسته‌بندیِ
        واقعی داشته باشند."""
        _run_seed()
        for template in IndustryTemplate.objects.all():
            with self.subTest(template=template.slug):
                self.assertGreaterEqual(template.categories.count(), 1)
                if template.sector in (IndustryTemplate.Sector.SERVICES, IndustryTemplate.Sector.OTHER):
                    continue
                self.assertGreaterEqual(template.attributes.count(), 1)

    def test_running_twice_does_not_duplicate_records(self):
        _run_seed()
        counts_after_first = {
            "templates": IndustryTemplate.objects.count(),
            "categories": IndustryTemplateCategory.objects.count(),
            "attributes": IndustryTemplateAttribute.objects.count(),
            "values": IndustryTemplateAttributeValue.objects.count(),
            "mappings": IndustryTemplateCategoryAttributeMapping.objects.count(),
            "recommended": IndustryTemplateRecommendedOption.objects.count(),
        }

        _run_seed()

        counts_after_second = {
            "templates": IndustryTemplate.objects.count(),
            "categories": IndustryTemplateCategory.objects.count(),
            "attributes": IndustryTemplateAttribute.objects.count(),
            "values": IndustryTemplateAttributeValue.objects.count(),
            "mappings": IndustryTemplateCategoryAttributeMapping.objects.count(),
            "recommended": IndustryTemplateRecommendedOption.objects.count(),
        }
        self.assertEqual(counts_after_first, counts_after_second)

    def test_category_hierarchy_is_stable_across_reruns(self):
        _run_seed()
        _run_seed()
        clothing_template = IndustryTemplate.objects.get(slug="clothing-fashion")
        tshirts = IndustryTemplateCategory.objects.get(
            industry_template=clothing_template, code="clothing-mens-tshirts",
        )
        self.assertEqual(tshirts.parent.code, "clothing-mens")
        self.assertEqual(tshirts.parent.parent.code, "clothing")

    def test_recommended_options_only_reference_variant_axis_attributes(self):
        _run_seed()
        for option in IndustryTemplateRecommendedOption.objects.select_related("template_attribute"):
            with self.subTest(option=str(option)):
                self.assertTrue(option.template_attribute.is_variant_axis)

    def test_mappings_reference_attribute_and_category_from_same_template(self):
        _run_seed()
        for mapping in IndustryTemplateCategoryAttributeMapping.objects.select_related(
            "template_category", "template_attribute",
        ):
            with self.subTest(mapping=str(mapping)):
                self.assertEqual(
                    mapping.template_category.industry_template_id,
                    mapping.template_attribute.industry_template_id,
                )


class ProductionDeploymentSequenceTests(TestCase):
    """Regression test for Issue 2 (production had zero Industry Templates).

    Root cause: ``seed_industry_templates`` is a correct, idempotent,
    production-safe management command — but purely opt-in. Nothing ever
    invoked it automatically, so a fresh production database that no
    operator remembered to run it against silently ended up with zero
    ``IndustryTemplate`` rows, and the onboarding "choose your industry"
    step fell back to its (otherwise correct) empty state for every
    merchant.

    The fix is *not* a schema migration — ``IndustryTemplate`` rows are
    living, version-controlled platform *content*
    (``apps.catalog.industry_templates.registry``), not a one-time historical
    fact. Baking a snapshot of the live registry into a migration would mean
    a fresh database, replayed years from now, runs *today's* registry
    against whatever schema existed at that migration's point in history —
    silently breaking fresh installs the moment a later migration changes an
    ``IndustryTemplate``-family field. The correct, documented fix is the
    explicit production deployment sequence (see
    ``docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md`` §3/§11):
    ``migrate`` → ``seed_industry_templates`` → ``validate_industry_templates``.

    This test proves that exact sequence end to end: a freshly-migrated
    database starts with zero Industry Templates (no migration silently
    seeds them), running ``seed_industry_templates`` once populates the full
    active/production-ready catalog, and running it again is a genuine no-op
    (no duplicates) — so it is always safe to include in an idempotent
    deploy pipeline."""

    def test_fresh_database_has_no_industry_templates_before_seeding(self):
        self.assertEqual(IndustryTemplate.objects.count(), 0)

    def test_seed_command_populates_the_full_active_registry(self):
        _run_seed()
        self.assertGreater(IndustryTemplate.objects.count(), 0)
        self.assertGreater(
            IndustryTemplate.objects.filter(
                is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
            ).count(),
            0,
        )
        seeded_slugs = set(IndustryTemplate.objects.values_list("slug", flat=True))
        expected_slugs = {entry["slug"] for entry in INDUSTRY_TEMPLATES}
        self.assertEqual(seeded_slugs, expected_slugs)

    def test_re_running_the_seed_command_does_not_duplicate_catalog_records(self):
        _run_seed()
        count_after_first_run = IndustryTemplate.objects.count()
        _run_seed()
        self.assertEqual(IndustryTemplate.objects.count(), count_after_first_run)

    def test_onboarding_shows_active_templates_only_after_the_seed_command_runs(self):
        """Closes the loop for the exact production symptom: before the
        deployment sequence's ``seed_industry_templates`` step runs, the
        onboarding industry list is correctly empty; once it runs, active
        production-ready templates are visible for onboarding to offer."""
        from apps.catalog.services import industry_catalog_service

        self.assertEqual(industry_catalog_service.offerable_industry_templates(), [])
        _run_seed()
        offerable = industry_catalog_service.offerable_industry_templates()
        self.assertGreater(len(offerable), 0)
        for template in offerable:
            self.assertTrue(template.is_active)
            self.assertEqual(template.readiness, IndustryTemplate.Readiness.PRODUCTION_READY)


class InstallEverySeededIndustryTests(TestCase):
    """§36.11 — هر صنف ساخته‌شده باید بدون خطا روی یک Store واقعی نصب شود."""

    def setUp(self):
        _run_seed()
        self.store = Store.objects.get(slug="akhlaghi")

    def test_every_offerable_industry_installs_cleanly(self):
        offerable = list(IndustryTemplate.objects.filter(
            is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        ))
        self.assertGreater(len(offerable), 0)
        for template in offerable:
            with self.subTest(template=template.slug):
                store = Store.objects.create(
                    name=f"فروشگاه آزمایشی {template.slug}",
                    slug=f"test-store-{template.slug}",
                    status=Store.Status.ACTIVE,
                )
                result = install_industry_template(store, template)
                self.assertEqual(len(result.categories_created), template.categories.count())
                self.assertGreater(Category.objects.filter(store=store).count(), 0)

    def test_review_required_templates_are_structurally_installable_but_not_offered(self):
        """«REVIEW_REQUIRED» یعنی کاملیِ صنفی کم است، نه اینکه ساختار خراب باشد:
        محتوای آن‌ها هنوز باید بی‌خطا نصب‌پذیر باشد (تا پس از غنی‌سازی فقط
        readiness تغییر کند)، اما تا آن زمان نصبِ جدید رد می‌شود."""
        from apps.catalog.services.industry_template_service import IndustryInstallationError

        held_back = list(IndustryTemplate.objects.filter(
            is_active=True, readiness=IndustryTemplate.Readiness.REVIEW_REQUIRED,
        ))
        self.assertGreater(len(held_back), 0)
        for template in held_back:
            with self.subTest(template=template.slug):
                store = Store.objects.create(
                    name=f"فروشگاه {template.slug}", slug=f"held-{template.slug}",
                    status=Store.Status.ACTIVE,
                )
                with self.assertRaises(IndustryInstallationError):
                    install_industry_template(store, template)
                self.assertEqual(Category.objects.filter(store=store).count(), 0)
                IndustryTemplate.objects.filter(pk=template.pk).update(
                    readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
                )
                template.refresh_from_db()
                result = install_industry_template(store, template)
                self.assertEqual(len(result.categories_created), template.categories.count())
