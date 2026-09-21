"""AUTH-001 — Portal merchant-mutation authorization convergence.

These tests prove the canonical authorization contract for the portal
onboarding *mutation* routes:

    onboarding_identity   -> writes Store.name + ShopSettings identity/contact
    onboarding_industry   -> installs a StoreIndustryInstallation OR (if one
                             already exists) advances Store.onboarding_stage
    onboarding_branding   -> writes ShopSettings.logo
    onboarding_review     -> publishes the store (Store.onboarding_completed_at)

...and the wider AUTH-001 repair inventory:

    billing_checkout / billing_step_up_verify        -> SUBSCRIPTION_CHANGE + BILLING_PAYMENT_MANAGE
    claim_handle / claim_handle_step_up              -> DOMAIN_MANAGE
    custom_domains (add) / custom_domain_begin_verify
    / custom_domain_check / custom_domain_final_check
    / custom_domain_activate / _activate_step_up     -> DOMAIN_MANAGE
    request_store_deletion / store_deletion_step_up
    / cancel_store_deletion                          -> STORE_DELETE (new, Owner-only)
    initiate_ownership_transfer / _step_up
    / cancel_ownership_transfer                       -> STAFF_MANAGE

The single canonical authority for *action* authorization is
``apps/stores/authorization.py`` (``ROLE_PERMISSIONS`` +
``user_has_permission``). Every one of these routes mutates Store-scoped
business truth that the Merchant Admin dashboard already gates with the
matching canonical permission. ``ANALYST``/``ADMINISTRATOR`` do **not** hold
any of the Owner-only keys used here (``SUBSCRIPTION_CHANGE``,
``DOMAIN_MANAGE``, ``STAFF_MANAGE``, ``STORE_DELETE``); ``ANALYST`` also
lacks ``SETTINGS_MANAGE``. ``BILLING_PAYMENT_MANAGE`` — the other half of
the subscription-purchase AND gate — is deliberately NOT Owner-only
(``ADMINISTRATOR`` holds it); the purchase gate is still effectively
Owner-only only because it also requires ``SUBSCRIPTION_CHANGE``.

The defect (AUTH-001): these portal routes were protected only by
``owner_required`` (authentication) + an ACTIVE ``StoreMembership`` — i.e.
tenant scope — and never consulted the canonical action permission.
Authentication is not authorization; tenant membership is not action
authorization; and — the specific regression this file's second half closes
— proving one's identity again via OTP Step-Up is not a substitute for
action authorization either. A request must satisfy Store scope AND the
required action permission BEFORE any Step-Up challenge or business mutation,
and every Step-Up *continuation* endpoint re-checks the same permission
before completing the mutation.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.portal.models import OwnerProfile
from apps.portal.services import provisioning_service
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.authorization import (
    ALL_PERMISSIONS,
    BILLING_PAYMENT_MANAGE,
    ROLE_PERMISSIONS,
    STORE_DELETE,
    SUBSCRIPTION_CHANGE,
    _OWNER_ONLY,
)
from apps.stores.models import Store, StoreDomain, StoreMembership, StoreOwnershipTransfer
from apps.subscriptions.models import Plan, PlanVersion

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
            # AUTH-001 real-QA repair (independent re-review): the canonical
            # ``active_membership_requires_accepted_at`` CHECK constraint
            # requires accepted_at whenever status=ACTIVE.
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
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
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
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
        """This is the representative denial test locking the platform-
        host-safe denial contract (AUTH-001 real-QA repair — independent
        re-review, Root Cause 1): every request in this file already runs
        with ``HTTP_HOST="rastisi.localhost"`` (a platform host routed to
        ``shop_core.urls_platform``), so it already exercises the REAL
        ``portal_permission_denied`` rendering path, unmocked. Asserting
        the template used here pins that the denial response renders the
        portal-scoped ``portal/403.html`` (which only reverses ``portal:*``
        URL names) rather than the global Storefront-scoped
        ``templates/403.html`` (whose ``catalog:home``/``customers:account``
        reversals raise ``NoReverseMatch`` under this host's URLconf, in
        which case the response would not even reach this assertion)."""
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
        self.assertTemplateUsed(response, "portal/403.html")
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

    def test_analyst_cannot_advance_stage_when_industry_already_installed(self):
        """BLOCKER 1 regression (independent architect review of commit
        557d1742): the ``elif request.method == "POST":`` branch of
        ``onboarding_industry`` — reached only when a
        ``StoreIndustryInstallation`` already exists — mutates
        ``Store.onboarding_stage`` via ``_advance_onboarding_stage`` and was
        left unprotected by the first commit, which only gated the
        ``installation is None`` branch. This is the exact branch the
        blocker identified; it must now be denied identically."""
        template = IndustryTemplate.objects.create(
            slug="books-auth001-blocker1", name="کتاب", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        from apps.catalog.services.industry_template_service import install_industry_template

        install_industry_template(self.store, template)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

        self.client.force_login(self.analyst)
        before = self._snapshot()
        response = self.client.post(self._url("industry"), {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        # The installation itself, and every other mutable field, is untouched.
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)
        self.assertEqual(self._snapshot(), before)

    def test_owner_can_still_advance_stage_when_industry_already_installed(self):
        """Positive control for the Blocker-1 repair: an authorized OWNER
        must still be able to advance past this step once a template is
        already installed (the legitimate, intended behavior)."""
        template = IndustryTemplate.objects.create(
            slug="books-auth001-blocker1-owner", name="کتاب", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        from apps.catalog.services.industry_template_service import install_industry_template

        install_industry_template(self.store, template)

        self.client.force_login(self.owner)
        response = self.client.post(self._url("industry"), {}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._url("branding"))
        self.store.refresh_from_db()
        self.assertEqual(self.store.onboarding_stage, Store.OnboardingStage.BRANDING)

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
            # AUTH-001 real-QA repair: represents a formerly-accepted
            # membership that was later revoked — the canonical
            # ``revoked_membership_requires_revoked_at`` CHECK constraint
            # requires revoked_at whenever status=REVOKED; accepted_at is
            # kept too, since a revoked membership was necessarily accepted
            # at some earlier point.
            status=StoreMembership.MembershipStatus.REVOKED,
            accepted_at=timezone.now(), revoked_at=timezone.now(),
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


# ===========================================================================
# STORE_DELETE — canonical registry change (new granular permission)
# ===========================================================================


class StoreDeletePermissionRegistryTests(TestCase):
    """AUTH-001 architect decision: STORE_DELETE is a new granular key added
    to the single canonical registry (apps/stores/authorization.py) — never
    a second registry, and never a hardcoded role-name check in a view."""

    def test_store_delete_is_a_member_of_all_permissions(self):
        self.assertIn(STORE_DELETE, ALL_PERMISSIONS)

    def test_store_delete_is_owner_only(self):
        self.assertIn(STORE_DELETE, _OWNER_ONLY)

    def test_owner_role_holds_store_delete(self):
        self.assertIn(STORE_DELETE, ROLE_PERMISSIONS[StoreMembership.Role.OWNER])

    def test_administrator_role_does_not_hold_store_delete(self):
        self.assertNotIn(STORE_DELETE, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])

    def test_analyst_role_does_not_hold_store_delete(self):
        self.assertNotIn(STORE_DELETE, ROLE_PERMISSIONS[StoreMembership.Role.ANALYST])

    def test_catalog_manager_role_does_not_hold_store_delete(self):
        self.assertNotIn(STORE_DELETE, ROLE_PERMISSIONS[StoreMembership.Role.CATALOG_MANAGER])


# ===========================================================================
# B. SUBSCRIPTION PURCHASE — billing_checkout / billing_step_up_verify
# ===========================================================================


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SubscriptionPurchaseAuthorizationTests(TestCase):
    """SUBSCRIPTION_CHANGE + BILLING_PAYMENT_MANAGE (AND semantics, via
    ``portal_actions_allowed``) gate reaching the subscription-purchase
    mutation.

    AUTH-001 test-repair correction (independent architect re-review): only
    ``SUBSCRIPTION_CHANGE`` is an ``_OWNER_ONLY`` key in the canonical
    registry — ``BILLING_PAYMENT_MANAGE`` is NOT. ``ADMINISTRATOR`` (whose
    permission set is ``ALL_PERMISSIONS - _OWNER_ONLY``) therefore actually
    *holds* ``BILLING_PAYMENT_MANAGE`` and only *lacks*
    ``SUBSCRIPTION_CHANGE``. The combined AND gate is still effectively
    Owner-only under the current role matrix — not because both keys are
    individually Owner-only, but because the gate requires *every* listed
    permission and ``SUBSCRIPTION_CHANGE`` alone is enough to deny any
    non-Owner role. ``test_permission_matrix_administrator_holds_billing_payment_manage_but_not_subscription_change``
    below pins this exact canonical fact directly against
    ``ROLE_PERMISSIONS``/``_OWNER_ONLY``, so the view must express the
    denial through the canonical permission check (not a hardcoded
    role-name check) — proven by testing ADMINISTRATOR, who is denied here
    despite holding ``BILLING_PAYMENT_MANAGE`` and many other permissions."""

    def setUp(self):
        cache.clear()
        # Step-Up is turned OFF here: this test suite is about the action-
        # authorization boundary reached *before* Step-Up ever begins, not
        # about OTP mechanics (covered by test_step_up_billing.py).
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.owner = User.objects.create_user(
            username="09121380011", password=_STRONG_PASS,
        )
        OwnerProfile.objects.create(user=self.owner, phone="09121380011", full_name="مالک")
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه صورتحساب مجوز")

        self.administrator = User.objects.create_user(username="09121380022", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.administrator, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.analyst = User.objects.create_user(username="09121380033", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

        self.plan = Plan.objects.create(code="pro-auth001", name="Pro", is_active=True, is_publicly_selectable=True)
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )

    def _checkout_url(self):
        return f"/app/stores/{self.store.public_id}/billing/checkout/{self.plan_version.pk}/"

    def test_permission_matrix_administrator_holds_billing_payment_manage_but_not_subscription_change(self):
        """Pins the exact canonical registry fact this suite depends on
        (AUTH-001 test-repair — independent architect re-review):

            SUBSCRIPTION_CHANGE     is Owner-only  (in _OWNER_ONLY)
            BILLING_PAYMENT_MANAGE  is NOT Owner-only (not in _OWNER_ONLY)
            ADMINISTRATOR           holds BILLING_PAYMENT_MANAGE
            ADMINISTRATOR           lacks SUBSCRIPTION_CHANGE

        The registry (apps/stores/authorization.py) is the sole authority;
        this test would need to change if the registry legitimately changes
        — it must never be "fixed" by editing ROLE_PERMISSIONS to match a
        stale assumption."""
        self.assertIn(SUBSCRIPTION_CHANGE, _OWNER_ONLY)
        self.assertNotIn(BILLING_PAYMENT_MANAGE, _OWNER_ONLY)
        self.assertIn(
            BILLING_PAYMENT_MANAGE, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR],
        )
        self.assertNotIn(
            SUBSCRIPTION_CHANGE, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR],
        )

    def test_administrator_is_denied_before_any_billing_side_effect(self):
        from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt

        self.client.force_login(self.administrator)
        invoices_before = SubscriptionInvoice.objects.count()
        attempts_before = SubscriptionPaymentAttempt.objects.count()

        with patch(
            "apps.portal.views.plan_change_billing_service.start_plan_change"
        ) as mocked_start_plan_change, patch(
            "apps.portal.views.payment_flow_service.start_payment"
        ) as mocked_start_payment:
            response = self.client.post(self._checkout_url(), HTTP_HOST=_HOST)

        self.assertEqual(response.status_code, 403)
        mocked_start_plan_change.assert_not_called()
        mocked_start_payment.assert_not_called()
        self.assertEqual(SubscriptionInvoice.objects.count(), invoices_before)
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), attempts_before)

    def test_analyst_is_denied_before_any_billing_side_effect(self):
        from apps.billing.models import SubscriptionInvoice

        self.client.force_login(self.analyst)
        before = SubscriptionInvoice.objects.count()
        with patch("apps.portal.views.plan_change_billing_service.start_plan_change") as mocked:
            response = self.client.post(self._checkout_url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        self.assertEqual(SubscriptionInvoice.objects.count(), before)

    def test_owner_reaches_the_real_purchase_flow(self):
        """Positive control (AUTH-001 test-repair — independent architect
        re-review): asserting merely ``status_code != 403`` is too weak,
        because this fixture deliberately does NOT guarantee a current
        subscription (that would depend on RASTISI_DEFAULT_PLAN_CODE); an
        OWNER request could pass authorization and then exit early/differ
        for an unrelated billing-setup reason, which would *also* not be a
        403 and would falsely look like a passing test.

        Mock the exact continuation the view calls once authorization
        passes (``_start_purchase``) and assert it is invoked, with the
        correct Store and PlanVersion, and that its return value is what
        the view returns — proving OWNER concretely crossed the canonical
        authorization gate, independent of any billing/subscription
        business-setup concern (which is SUB-001/billing territory, not
        AUTH-001)."""
        from django.http import HttpResponse

        sentinel = HttpResponse("owner-crossed-the-gate", status=278)
        self.client.force_login(self.owner)
        with patch("apps.portal.views._start_purchase", return_value=sentinel) as mocked_start_purchase:
            response = self.client.post(self._checkout_url(), HTTP_HOST=_HOST)

        self.assertEqual(response.status_code, 278)
        self.assertEqual(response.content, b"owner-crossed-the-gate")
        mocked_start_purchase.assert_called_once()
        _args, kwargs = mocked_start_purchase.call_args
        self.assertEqual(kwargs["store"], self.store)
        self.assertEqual(kwargs["plan_version"], self.plan_version)

    def test_step_up_continuation_rechecks_permission_for_administrator(self):
        """Step-Up ordering requirement: even if an ADMINISTRATOR somehow
        reaches the Step-Up continuation view directly (stale session,
        role change after a challenge was issued by another session, etc.),
        the continuation must re-check the canonical permission and deny —
        Step-Up proof of identity must never substitute for authorization."""
        self.client.force_login(self.administrator)
        with patch("apps.portal.views._start_purchase") as mocked_start_purchase:
            response = self.client.get(
                f"/app/stores/{self.store.public_id}/billing/step-up/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked_start_purchase.assert_not_called()


# ===========================================================================
# C. PERMANENT HANDLE / DOMAIN MANAGEMENT — DOMAIN_MANAGE
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
    # AUTH-001 test-repair (independent architect re-review): this suite must
    # not depend on deployment/default-plan configuration. Explicitly force
    # RASTISI_DEFAULT_PLAN_CODE empty (the project default) so
    # provision_trial_store()'s internal, fail-open
    # provision_default_subscription() call is guaranteed to find no default
    # plan and do nothing — the paid/active subscription below is instead
    # built explicitly and deterministically via the canonical
    # subscription_service, exactly like apps/portal/tests/test_claim_handle_views.py.
    RASTISI_DEFAULT_PLAN_CODE="",
)
class HandleAndDomainAuthorizationTests(TestCase):
    """DOMAIN_MANAGE gates the permanent-handle claim and every custom-domain
    mutation. Step-Up remains required in addition where it already was;
    this suite proves the permission gate runs first and that a denied
    request never reaches StoreDomain creation/update or the DNS/TLS
    verification services."""

    def setUp(self):
        cache.clear()
        update_platform_configuration(
            actor=None, step_up_actions={"permanent_handle_claim": False, "custom_domain_activate": False},
        )
        self.owner = User.objects.create_user(username="09121390011", password=_STRONG_PASS)
        OwnerProfile.objects.create(user=self.owner, phone="09121390011", full_name="مالک")
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه دامنه مجوز")

        self.administrator = User.objects.create_user(username="09121390022", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.administrator, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.analyst = User.objects.create_user(username="09121390033", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self._activate_paid_subscription()

    def _activate_paid_subscription(self):
        """Deterministically gives ``self.store`` a real ACTIVE paid
        subscription through the canonical subscription_service, so
        ``claim_handle``'s own ``can_claim`` business precondition is
        genuinely satisfied — never faked by direct-writing
        StoreSubscription fields, and never dependent on
        RASTISI_DEFAULT_PLAN_CODE / provision_trial_store()'s own (fail-open,
        possibly no-op) default-subscription provisioning. With
        RASTISI_DEFAULT_PLAN_CODE="" (forced above),
        provision_trial_store() never creates any subscription for this
        Store, so ``create_subscription`` is guaranteed to find none and
        will not raise the "already has a current subscription" error."""
        from apps.subscriptions.models import StoreSubscription
        from apps.subscriptions.services import subscription_service

        self.assertFalse(
            StoreSubscription.objects.filter(store=self.store, is_current=True).exists(),
            "precondition: provision_trial_store must not have created a subscription "
            "when RASTISI_DEFAULT_PLAN_CODE is empty — otherwise this fixture is not "
            "actually exercising the explicit create_subscription/activate_subscription path.",
        )
        plan = Plan.objects.create(
            code=f"pro-auth001-domain-{self.store.pk}", name="Pro", is_active=True, is_publicly_selectable=True,
        )
        version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        subscription = subscription_service.create_subscription(self.store, version, actor=self.owner)
        subscription_service.activate_subscription(subscription, actor=self.owner)
        self.assertTrue(
            StoreSubscription.objects.filter(
                store=self.store, is_current=True, status=StoreSubscription.Status.ACTIVE,
            ).exists(),
            "precondition: the store must now have a real, current, ACTIVE subscription.",
        )

    def _claim_handle_url(self):
        return f"/app/stores/{self.store.public_id}/handle/"

    def _domains_url(self):
        return f"/app/stores/{self.store.public_id}/domains/"

    def test_fixture_precondition_can_claim_is_true_for_the_owner(self):
        """Explicit fixture-validity check (test-repair requirement): before
        any authorization distinction is tested, prove — through the real
        view, not just the service layer — that ``can_claim`` is actually
        True. If this precondition test itself fails, every other test in
        this handle-claim block would be denied by the business
        precondition rather than by the authorization gate under test, and
        must be treated as invalid."""
        self.client.force_login(self.owner)
        response = self.client.get(self._claim_handle_url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_claim"])
        self.assertIsNotNone(response.context["current_subscription"])

    # -- (3) permanent handle -----------------------------------------------

    def test_administrator_cannot_claim_handle_and_no_domain_is_created(self):
        self.client.force_login(self.administrator)
        domains_before = StoreDomain.objects.filter(store=self.store).count()
        with patch("apps.portal.views.handle_service.claim_platform_handle") as mocked_claim:
            response = self.client.post(self._claim_handle_url(), {"label": "myshop"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        mocked_claim.assert_not_called()
        self.assertEqual(StoreDomain.objects.filter(store=self.store).count(), domains_before)

    def test_analyst_cannot_claim_handle(self):
        self.client.force_login(self.analyst)
        with patch("apps.portal.views.handle_service.claim_platform_handle") as mocked_claim:
            response = self.client.post(self._claim_handle_url(), {"label": "myshop2"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 403)
        mocked_claim.assert_not_called()

    def test_owner_can_claim_handle(self):
        self.client.force_login(self.owner)
        with patch("apps.portal.views.handle_service.claim_platform_handle") as mocked_claim:
            response = self.client.post(self._claim_handle_url(), {"label": "myshop3"}, HTTP_HOST=_HOST)
        self.assertNotEqual(response.status_code, 403)
        mocked_claim.assert_called_once()

    def test_handle_claim_step_up_continuation_rechecks_permission(self):
        """Step-Up ordering requirement for the handle-claim continuation."""
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.handle_service.claim_platform_handle") as mocked:
            response = self.client.get(
                f"/app/stores/{self.store.public_id}/handle/step-up/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()

    # -- (4) custom-domain add -----------------------------------------------

    def test_administrator_cannot_add_custom_domain_and_no_row_is_created(self):
        self.client.force_login(self.administrator)
        before = StoreDomain.objects.filter(store=self.store).count()
        response = self.client.post(
            self._domains_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StoreDomain.objects.filter(store=self.store).count(), before)
        self.assertFalse(StoreDomain.objects.filter(store=self.store, hostname="shop.example.com").exists())

    def test_analyst_cannot_add_custom_domain(self):
        self.client.force_login(self.analyst)
        before = StoreDomain.objects.filter(store=self.store).count()
        response = self.client.post(
            self._domains_url(), {"action": "add", "hostname": "shop2.example.com"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(StoreDomain.objects.filter(store=self.store).count(), before)

    def test_owner_can_add_custom_domain(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self._domains_url(), {"action": "add", "hostname": "shop3.example.com"}, HTTP_HOST=_HOST,
        )
        self.assertNotEqual(response.status_code, 403)
        self.assertTrue(StoreDomain.objects.filter(store=self.store, hostname="shop3.example.com").exists())

    # -- (5) custom-domain verification/activation ---------------------------

    def _create_domain(self, **kwargs):
        defaults = dict(
            store=self.store, hostname="verify.example.com", is_primary=False,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED,
        )
        defaults.update(kwargs)
        return StoreDomain.objects.create(**defaults)

    def test_administrator_cannot_begin_dns_verification(self):
        domain = self._create_domain()
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.domain_verification_service.begin_dns_verification") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.UNVERIFIED)

    def test_administrator_cannot_check_dns_verification(self):
        # AUTH-001 real-QA repair (independent re-review): the canonical
        # ``pending_status_requires_verification_requested_at`` CHECK
        # constraint requires verification_requested_at whenever
        # verification_status=PENDING (in addition to a non-empty token).
        domain = self._create_domain(
            verification_status=StoreDomain.VerificationStatus.PENDING, verification_token="tok123",
            verification_requested_at=timezone.now(),
        )
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.domain_verification_service.check_dns_verification") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()

    def test_administrator_cannot_run_final_readiness_check(self):
        # AUTH-001 real-QA repair: same PENDING-state constraint as above.
        domain = self._create_domain(
            verification_status=StoreDomain.VerificationStatus.PENDING, verification_token="tok456",
            verification_requested_at=timezone.now(),
        )
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.domain_verification_service.refresh_custom_domain_readiness") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/final-check/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()

    def test_administrator_cannot_activate_custom_domain(self):
        domain = self._create_domain(
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.domain_verification_service.activate_custom_domain") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/activate/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        domain.refresh_from_db()
        self.assertFalse(domain.is_primary)

    def test_owner_can_activate_custom_domain(self):
        domain = self._create_domain(
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        with patch("apps.portal.views.domain_verification_service.activate_custom_domain") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/activate/", HTTP_HOST=_HOST,
            )
        self.assertNotEqual(response.status_code, 403)
        mocked.assert_called_once()

    def test_domain_activate_step_up_continuation_rechecks_permission(self):
        """Step-Up ordering requirement for the activation continuation."""
        domain = self._create_domain(
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.domain_verification_service.activate_custom_domain") as mocked:
            response = self.client.get(
                f"/app/stores/{self.store.public_id}/domains/activate/step-up/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()


# ===========================================================================
# D. STORE DELETION — STORE_DELETE (Owner-only)
# ===========================================================================


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StoreDeletionAuthorizationTests(TestCase):
    """STORE_DELETE gates requesting, Step-Up-continuing, and cancelling a
    store-deletion request. Both ADMINISTRATOR and ANALYST are denied
    (STORE_DELETE is Owner-only), proving this is not merely
    ``ALL_PERMISSIONS - _OWNER_ONLY`` reasoning error — Store.status and the
    deletion-lifecycle fields must remain completely untouched on denial."""

    def setUp(self):
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"store_delete": False})
        self.owner = User.objects.create_user(username="09121400011", password=_STRONG_PASS)
        OwnerProfile.objects.create(user=self.owner, phone="09121400011", full_name="مالک")
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه حذف مجوز")

        self.administrator = User.objects.create_user(username="09121400022", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.administrator, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.analyst = User.objects.create_user(username="09121400033", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def _snapshot(self):
        self.store.refresh_from_db()
        return (
            self.store.status, self.store.deletion_requested_at,
            self.store.deletion_scheduled_purge_at, self.store.pre_deletion_status,
        )

    def _request_deletion_url(self):
        return f"/app/stores/{self.store.public_id}/delete/"

    def test_administrator_cannot_request_deletion(self):
        self.client.force_login(self.administrator)
        before = self._snapshot()
        with patch("apps.portal.views.deletion_service.request_deletion") as mocked:
            response = self.client.post(
                self._request_deletion_url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        self.assertEqual(self._snapshot(), before)

    def test_analyst_cannot_request_deletion(self):
        self.client.force_login(self.analyst)
        before = self._snapshot()
        with patch("apps.portal.views.deletion_service.request_deletion") as mocked:
            response = self.client.post(
                self._request_deletion_url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        self.assertEqual(self._snapshot(), before)

    def test_administrator_cannot_cancel_deletion(self):
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.deletion_service.cancel_deletion") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/delete/cancel/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()

    def test_owner_can_request_deletion(self):
        self.client.force_login(self.owner)
        with patch("apps.portal.views.deletion_service.request_deletion") as mocked:
            response = self.client.post(
                self._request_deletion_url(), {"typed_confirmation": self.store.slug}, HTTP_HOST=_HOST,
            )
        self.assertNotEqual(response.status_code, 403)
        mocked.assert_called_once()

    def test_deletion_step_up_continuation_rechecks_permission(self):
        """Step-Up ordering requirement: an ADMINISTRATOR reaching the
        deletion Step-Up continuation directly must still be denied —
        identity re-proof never completes a forbidden deletion."""
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.deletion_service.request_deletion") as mocked:
            response = self.client.get(
                f"/app/stores/{self.store.public_id}/delete/step-up/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()


# ===========================================================================
# E. OWNER-SIDE OWNERSHIP TRANSFER — STAFF_MANAGE
# ===========================================================================


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnershipTransferAuthorizationTests(TestCase):
    """STAFF_MANAGE gates initiating, Step-Up-continuing, and cancelling an
    ownership transfer from the current-owner side. The public recipient-
    side ``accept_ownership_transfer`` is explicitly out of AUTH-001 scope
    and is not touched or tested here."""

    def setUp(self):
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"store_ownership_transfer": False})
        self.owner = User.objects.create_user(username="09121410011", password=_STRONG_PASS)
        OwnerProfile.objects.create(user=self.owner, phone="09121410011", full_name="مالک")
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه انتقال مجوز")

        self.administrator = User.objects.create_user(username="09121410022", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.administrator, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.analyst = User.objects.create_user(username="09121410033", password=_STRONG_PASS)
        StoreMembership.objects.create(
            store=self.store, user=self.analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def _initiate_url(self):
        return f"/app/stores/{self.store.public_id}/transfer/"

    def test_administrator_cannot_initiate_transfer_and_no_transfer_is_created(self):
        self.client.force_login(self.administrator)
        before = StoreOwnershipTransfer.objects.filter(store=self.store).count()
        with patch("apps.portal.views.ownership_transfer_service.initiate_transfer") as mocked:
            response = self.client.post(
                self._initiate_url(), {"target_phone": "09121999999"}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        self.assertEqual(StoreOwnershipTransfer.objects.filter(store=self.store).count(), before)

    def test_analyst_cannot_initiate_transfer(self):
        self.client.force_login(self.analyst)
        with patch("apps.portal.views.ownership_transfer_service.initiate_transfer") as mocked:
            response = self.client.post(
                self._initiate_url(), {"target_phone": "09121999998"}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()

    def test_owner_can_initiate_transfer(self):
        self.client.force_login(self.owner)
        with patch("apps.portal.views.ownership_transfer_service.initiate_transfer") as mocked:
            response = self.client.post(
                self._initiate_url(), {"target_phone": "09121999997"}, HTTP_HOST=_HOST,
            )
        self.assertNotEqual(response.status_code, 403)
        mocked.assert_called_once()

    def test_administrator_cannot_cancel_transfer_and_no_cancellation_occurs(self):
        transfer = StoreOwnershipTransfer.objects.create(
            store=self.store, initiated_by=self.owner, target_phone="09121999996",
            expires_at=timezone.now() + timezone.timedelta(days=3),
        )
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.ownership_transfer_service.cancel_transfer") as mocked:
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/transfer/cancel/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StoreOwnershipTransfer.Status.PENDING)

    def test_transfer_step_up_continuation_rechecks_permission(self):
        """Step-Up ordering requirement: an ADMINISTRATOR reaching the
        ownership-transfer Step-Up continuation directly must still be
        denied — identity re-proof never completes a forbidden transfer."""
        self.client.force_login(self.administrator)
        with patch("apps.portal.views.ownership_transfer_service.initiate_transfer") as mocked:
            response = self.client.get(
                f"/app/stores/{self.store.public_id}/transfer/step-up/", HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
