"""The MANDATORY industry rule (owner decision) at the service / view level — see also the onboarding journey tests."""

from django.test import TestCase


class MandatoryIndustryRuleTests(TestCase):
    """Owner decision: a new shop must choose an industry («سایر (صنف آزاد)» if its business is not listed). The CHOICE is enforced at the
    onboarding steps and at publication; existing, already-published shops are never sent back."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.portal.services import provisioning_service

        self.owner = get_user_model().objects.create_user(username="mand@example.com", email="mand@example.com", password="a-very-strong-pass-1")
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه الزامی")

    def test_publication_is_refused_without_an_industry(self):
        from apps.portal.services import onboarding_publish_service as svc

        with self.assertRaises(svc.OnboardingPublishError) as ctx:
            svc.complete_onboarding(store=self.store, actor=self.owner)
        self.assertEqual(ctx.exception.code, "no_industry")
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)

    def test_once_an_industry_is_chosen_the_next_missing_thing_is_reported_instead(self):
        from apps.portal.services import onboarding_publish_service as svc
        from apps.portal.tests._industry import install_other_industry

        install_other_industry(self.store)
        with self.assertRaises(svc.OnboardingPublishError) as ctx:
            svc.complete_onboarding(store=self.store, actor=self.owner)
        self.assertEqual(ctx.exception.code, "no_template")

    def test_a_shop_that_is_already_published_is_not_sent_back_to_the_industry_step(self):
        from django.utils import timezone

        from apps.portal.views import _industry_missing_redirect
        from apps.stores.models import Store

        Store.objects.filter(pk=self.store.pk).update(onboarding_completed_at=timezone.now(), onboarding_stage=Store.OnboardingStage.DONE)
        self.store.refresh_from_db()
        self.assertIsNone(_industry_missing_redirect(None, self.store))        # grandfathered: no retro-active change, no backfill

    def test_the_free_form_choice_is_a_valid_complete_industry_for_the_checklist(self):
        from django.test import RequestFactory

        from apps.dashboard.services.checklist_service import build_setup_checklist
        from apps.portal.tests._industry import install_other_industry

        before = {s["key"]: s["is_complete"] for s in build_setup_checklist(self.store, RequestFactory().get("/"))["steps"]}
        self.assertFalse(before["industry"])
        install_other_industry(self.store)
        after = {s["key"]: s["is_complete"] for s in build_setup_checklist(self.store, RequestFactory().get("/"))["steps"]}
        self.assertTrue(after["industry"] and after["industry_template"])
        self.assertTrue(after["product_groups"])                               # the generic top-level category exists
        self.assertFalse(after["product_categories"])                          # …but no sub-category yet: the checklist stays honest

    def test_a_second_store_choosing_other_gets_its_own_rows(self):
        from django.contrib.auth import get_user_model

        from apps.catalog.models import Category
        from apps.portal.services import provisioning_service
        from apps.portal.tests._industry import install_other_industry

        other_owner = get_user_model().objects.create_user(username="mand2@example.com", email="mand2@example.com", password="a-very-strong-pass-1")
        second = provisioning_service.provision_trial_store(owner=other_owner, name="فروشگاه دوم")
        install_other_industry(self.store)
        install_other_industry(second)
        self.assertEqual(Category.objects.filter(store=self.store).count(), 1)
        self.assertEqual(Category.objects.filter(store=second).count(), 1)
        self.assertNotEqual(Category.objects.get(store=self.store).pk, Category.objects.get(store=second).pk)
