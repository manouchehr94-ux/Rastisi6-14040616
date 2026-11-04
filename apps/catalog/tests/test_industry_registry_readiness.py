"""Platform bootstrap of the industry (صنف) catalogue: read-only readiness, a safe ``--apply`` that loads only what is missing, an operator
warning, and the guarantee that no customer request ever seeds or changes anything."""

import json
from io import StringIO

from django.core.checks import Warning as CheckWarning
from django.core.management import call_command
from django.db.utils import OperationalError
from django.test import TestCase
from unittest import mock

from apps.catalog.checks import industry_registry_warnings
from apps.catalog.industry_templates.registry import ALL_INDUSTRY_TEMPLATES, DEPRECATED_LEGACY_SLUGS
from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.catalog.services import industry_catalog_service, industry_registry_readiness as readiness


def run(*args):
    out, err = StringIO(), StringIO()
    code = 0
    try:
        call_command("ensure_industry_registry", *args, stdout=out, stderr=err)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


class RegistryReadinessTests(TestCase):
    def setUp(self):
        IndustryTemplate.objects.all().delete()          # a database that never ran the bootstrap

    def test_empty_database_is_reported_as_not_ready_without_writing_anything(self):
        status = readiness.check_registry()
        self.assertEqual(status.state, "empty")
        self.assertFalse(status.is_ready)
        self.assertEqual(status.database_total, 0)
        self.assertEqual(status.registry_total, len({(e["slug"], e["version"]) for e in ALL_INDUSTRY_TEMPLATES}))
        self.assertTrue(any("ensure_industry_registry" in p for p in status.problems))
        self.assertEqual(IndustryTemplate.objects.count(), 0)

    def test_the_readiness_check_is_cheap_and_read_only(self):
        with self.assertNumQueries(2):
            readiness.check_registry()

    def test_command_without_apply_only_reports_and_exits_non_zero(self):
        code, out, _err = run()
        self.assertEqual(code, 1)
        self.assertIn("هیچ الگوی صنفی", out)
        self.assertEqual(IndustryTemplate.objects.count(), 0)

    def test_apply_loads_the_catalogue_and_makes_every_seller_able_to_choose(self):
        code, out, _err = run("--apply")
        self.assertEqual(code, 0, out)
        status = readiness.check_registry()
        self.assertTrue(status.is_ready, status.problems)
        self.assertEqual(status.database_total, status.registry_total)
        self.assertTrue(status.other_offerable)
        offerable = {t.slug for t in industry_catalog_service.offerable_industry_templates()}
        self.assertIn("other", offerable)
        self.assertFalse(offerable & set(DEPRECATED_LEGACY_SLUGS))          # deprecated templates are never shown to sellers
        self.assertEqual(IndustryTemplate.objects.filter(slug="other").get().name, "سایر (صنف آزاد)")

    def test_apply_is_idempotent_and_never_rewrites_existing_rows(self):
        run("--apply")
        snapshot = dict(IndustryTemplate.objects.values_list("pk", "updated_at"))
        IndustryTemplate.objects.filter(slug="womens-clothing").update(name="نام ویرایش‌شده توسط اپراتور")
        code, out, _err = run("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(IndustryTemplate.objects.filter(slug="womens-clothing").get().name, "نام ویرایش‌شده توسط اپراتور")   # untouched
        after = dict(IndustryTemplate.objects.values_list("pk", "updated_at"))
        changed = {pk for pk in snapshot if snapshot[pk] != after[pk] and pk != IndustryTemplate.objects.get(slug="womens-clothing").pk}
        self.assertEqual(changed, set())
        self.assertEqual(IndustryTemplate.objects.count(), len(snapshot))

    def test_apply_fills_only_the_missing_templates(self):
        run("--apply")
        IndustryTemplate.objects.filter(slug="other").delete()
        status = readiness.check_registry()
        self.assertEqual(status.state, "partial")
        self.assertIn("other", status.missing)
        self.assertFalse(status.other_offerable)
        before = IndustryTemplate.objects.count()
        code, _out, _err = run("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(IndustryTemplate.objects.count(), before + 1)
        self.assertTrue(readiness.check_registry().is_ready)

    def test_apply_never_touches_a_stores_existing_installation(self):
        from apps.stores.models import Store

        run("--apply")
        store = Store.objects.create(name="Installed", slug="installed-registry", status=Store.Status.ACTIVE)
        template = IndustryTemplate.objects.get(slug="other")
        StoreIndustryInstallation.objects.create(store=store, industry_template=template, installed_version=1,
                                                 status=StoreIndustryInstallation.Status.COMPLETED)
        run("--apply")
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=store).count(), 1)

    def test_json_report(self):
        code, out, _err = run("--json")
        payload = json.loads(out)
        self.assertEqual(code, 1)
        self.assertFalse(payload["after"]["is_ready"])
        self.assertFalse(payload["applied"])

    def test_a_customer_request_never_seeds_the_catalogue(self):
        from django.contrib.auth import get_user_model
        from django.test import override_settings

        from apps.portal.services import provisioning_service

        owner = get_user_model().objects.create_user(username="reg-owner@example.com", email="reg-owner@example.com", password="a-very-strong-pass-1")
        store = provisioning_service.provision_trial_store(owner=owner, name="فروشگاه رجیستری")
        self.client.force_login(owner)
        with override_settings(ALLOWED_HOSTS=["rastisi.localhost", "testserver"]), self.assertLogs("apps.portal.views", level="ERROR"):
            response = self.client.get(f"/app/stores/{store.public_id}/onboarding/industry/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="industry-registry-not-ready"')
        self.assertEqual(IndustryTemplate.objects.count(), 0)               # the page told the truth; it did not seed


class RegistrySystemCheckTests(TestCase):
    def test_warns_the_operator_when_the_catalogue_is_not_loaded(self):
        IndustryTemplate.objects.all().delete()
        messages = industry_registry_warnings()
        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], CheckWarning)
        self.assertEqual(messages[0].id, "rastisi.W010")
        self.assertIn("ensure_industry_registry", messages[0].hint)

    def test_silent_when_ready(self):
        run("--apply")
        self.assertEqual(industry_registry_warnings(), [])

    def test_silent_before_the_first_migrate(self):
        with mock.patch.object(readiness, "check_registry", side_effect=OperationalError("no such table")):
            self.assertEqual(industry_registry_warnings(), [])

