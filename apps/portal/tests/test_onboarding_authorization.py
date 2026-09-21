"""AUTH-001 — Portal merchant-mutation authorization convergence.

These tests prove the canonical authorization contract for the portal
onboarding *mutation* routes:

    onboarding_identity   -> writes Store.name + ShopSettings identity/contact
    onboarding_industry   -> installs a StoreIndustryInstallation
    onboarding_branding   -> writes ShopSettings.logo
    onboarding_review     -> publishes the store (Store.onboarding_completed_at)

The single canonical authority for *action* authorization is
``apps/stores/authorization.py`` (``ROLE_PERMISSIONS`` +
``user_has_permission``). Every one of these routes mutates Store-scoped
business truth that the Merchant Admin dashboard already gates with the
``SETTINGS_MANAGE`` permission (``settings_appearance`` for identity/logo,
``settings_industry_install`` for industry). ``ANALYST`` does **not** hold
``SETTINGS_MANAGE``.

The defect (AUTH-001): these portal routes were protected only by
``owner_required`` (authentication) + an ACTIVE ``StoreMembership`` — i.e.
tenant scope — and never consulted the canonical action permission. An
authenticated ACTIVE ANALYST could therefore mutate Store settings through
the portal even though the same action is denied on the dashboard.

Authentication is not authorization; tenant membership is not action
authorization. A request must satisfy BOTH correct Store scope AND the
required action permission.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core.models import ShopSettings
from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.portal.services import provisioning_service
from apps.stores.models import StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"

_STRONG_PASS = "a-very-strong-pass-1"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingMutationAuthorizationTests(TestCase):
    """AUTH-001 role/tenant matrix for the four portal onboarding mutations."""

    def setUp(self):
        # The store owner (holds an ACTIVE OWNER membership via provisioning).
        self.owner = User.objects.create_user(
            username="auth001-owner@example.com", email="auth001-owner@example.com",
            password=_STRONG_PASS,
        )
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه اصلی")

        # An ACTIVE ANALYST member of the SAME store. ANALYST intentionally
        # lacks SETTINGS_MANAGE in the canonical ROLE_PERMISSIONS matrix.
        self.analyst = User.objects.create_user(
            username="auth001-analyst@example.com", email="auth001-analyst@example.com",
            password=_STRONG_PASS,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.analyst,
            role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE,
        )

        # An ACTIVE ADMINISTRATOR member of the SAME store. ADMINISTRATOR
        # holds SETTINGS_MANAGE (it is not an _OWNER_ONLY key) and must be
        # allowed — proving the fix keys off the permission matrix, not a
        # hardcoded "OWNER only" role-name check.
        self.administrator = User.objects.create_user(
            username="auth001-admin@example.com", email="auth001-admin@example.com",
            password=_STRONG_PASS,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.administrator,
            role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE,
        )

    # -- url helpers -------------------------------------------------------

    def _url(self, stage):
        return f"/app/stores/{self.store.public_id}/onboarding/{stage}/"

    def _snapshot(self):
        """A tuple of every business field the four mutations can touch."""
        self.store.refresh_from_db()
        shop = ShopSettings.load(store=self.store)
        return (
            self.store.name,
            self.store.onboarding_stage,
            self.store.onboarding_completed_at,
            shop.name,
            shop.tagline,
            shop.description,
            shop.contact_phone,
            shop.contact_email,
            shop.contact_address,
            shop.logo.name if shop.logo else "",
            StoreIndustryInstallation.objects.filter(store=self.store).count(),
        )

    # -- (4) ACTIVE ANALYST without the action permission cannot mutate ----
    #    and (7) denial leaves ZERO persistent writes ----------------------

    def test_analyst_cannot_mutate_identity_and_leaves_zero_writes(self):
        self.client.force_login(self.analyst)
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"),
            {
                "name": "نامِ تزریق‌شده",
                "tagline": "شعارِ تزریق‌شده",
                "description": "توضیحِ تزریق‌شده",
                "contact_phone": "021-99999999",
                "contact_email": "attacker@example.com",
                "contact_address": "آدرسِ تزریق‌شده",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._snapshot(), before)

    def test_analyst_cannot_install_industry(self):
        template = IndustryTemplate.objects.create(
            slug="perfume-auth001", name="عطر", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        self.client.force_login(self.analyst)
        before = self._snapshot()
        response = self.client.post(
            self._url("industry"), {"industry_template_id": template.pk}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 0)
        self.assertEqual(self._snapshot(), before)

    def test_analyst_cannot_publish_via_review(self):
        self.client.force_login(self.analyst)
        before = self._snapshot()
        response = self.client.post(self._url("review"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.onboarding_completed_at)
        self.assertEqual(self._snapshot(), before)

    def test_analyst_cannot_mutate_branding(self):
        self.client.force_login(self.analyst)
        before = self._snapshot()
        response = self.client.post(self._url("branding"), {"action": "skip"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._snapshot(), before)

    # -- (1) unauthenticated cannot mutate ---------------------------------

    def test_unauthenticated_cannot_mutate_identity(self):
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"), {"name": "ناشناس"}, HTTP_HOST=_HOST,
        )
        # owner_required redirects unauthenticated users to portal login.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertEqual(self._snapshot(), before)

    # -- (2) user with no membership cannot mutate -------------------------

    def test_non_member_cannot_mutate_identity(self):
        stranger = User.objects.create_user(
            username="auth001-stranger@example.com", email="auth001-stranger@example.com",
            password=_STRONG_PASS,
        )
        self.client.force_login(stranger)
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"), {"name": "غریبه"}, HTTP_HOST=_HOST,
        )
        # No ACTIVE membership -> _get_owned_store_or_404 raises 404.
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._snapshot(), before)

    # -- (3) ACTIVE membership in ANOTHER store cannot mutate target -------

    def test_member_of_other_store_cannot_mutate_target_store(self):
        other_owner = User.objects.create_user(
            username="auth001-other@example.com", email="auth001-other@example.com",
            password=_STRONG_PASS,
        )
        # other_owner owns a DIFFERENT store, and is even an OWNER there,
        # but has no membership in self.store.
        provisioning_service.provision_trial_store(owner=other_owner, name="فروشگاه دیگر")
        self.client.force_login(other_owner)
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"), {"name": "از فروشگاهِ دیگر"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._snapshot(), before)

    # -- (5) revoked / invited (non-ACTIVE) membership cannot mutate -------

    def test_revoked_member_cannot_mutate_identity(self):
        revoked = User.objects.create_user(
            username="auth001-revoked@example.com", email="auth001-revoked@example.com",
            password=_STRONG_PASS,
        )
        StoreMembership.objects.create(
            store=self.store, user=revoked,
            role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.REVOKED,
        )
        self.client.force_login(revoked)
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"), {"name": "لغوشده"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._snapshot(), before)

    def test_invited_member_cannot_mutate_identity(self):
        invited = User.objects.create_user(
            username="auth001-invited@example.com", email="auth001-invited@example.com",
            password=_STRONG_PASS,
        )
        StoreMembership.objects.create(
            store=self.store, user=invited,
            role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.INVITED,
        )
        self.client.force_login(invited)
        before = self._snapshot()
        response = self.client.post(
            self._url("identity"), {"name": "دعوت‌شده"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._snapshot(), before)

    # -- (6) authorized roles still work -----------------------------------

    def test_owner_can_still_mutate_identity(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self._url("identity"),
            {"name": "نامِ مجاز", "tagline": "شعارِ مجاز"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "نامِ مجاز")
        shop = ShopSettings.load(store=self.store)
        self.assertEqual(shop.name, "نامِ مجاز")
        self.assertEqual(shop.tagline, "شعارِ مجاز")

    def test_administrator_with_settings_manage_can_mutate_identity(self):
        # ADMINISTRATOR holds SETTINGS_MANAGE (not _OWNER_ONLY). This proves
        # the gate is a permission check, not an "OWNER only" role-name check.
        self.client.force_login(self.administrator)
        response = self.client.post(
            self._url("identity"),
            {"name": "توسطِ ادمین"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "توسطِ ادمین")
