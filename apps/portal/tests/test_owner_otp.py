from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.customers.models import Customer
from apps.portal.models import OwnerOtpChallenge, OwnerProfile
from apps.portal.phone import InvalidPhoneError, normalize_iranian_phone
from apps.portal.services import owner_auth_service, owner_otp_service

User = get_user_model()
_HOST = "rastisi.localhost"


class NormalizeIranianPhoneTests(TestCase):
    def test_accepts_canonical_form(self):
        self.assertEqual(normalize_iranian_phone("09121234567"), "09121234567")

    def test_accepts_plus98_form(self):
        self.assertEqual(normalize_iranian_phone("+989121234567"), "09121234567")

    def test_accepts_0098_form(self):
        self.assertEqual(normalize_iranian_phone("00989121234567"), "09121234567")

    def test_accepts_bare_98_form(self):
        self.assertEqual(normalize_iranian_phone("989121234567"), "09121234567")

    def test_accepts_without_leading_zero(self):
        self.assertEqual(normalize_iranian_phone("9121234567"), "09121234567")

    def test_accepts_persian_digits(self):
        self.assertEqual(normalize_iranian_phone("۰۹۱۲۱۲۳۴۵۶۷"), "09121234567")

    def test_accepts_with_dashes_and_spaces(self):
        self.assertEqual(normalize_iranian_phone("0912 123 4567"), "09121234567")

    def test_rejects_too_short(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("0912123")

    def test_rejects_landline_looking_number(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("02112345678")

    def test_rejects_garbage(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone("not-a-phone")

    def test_rejects_none(self):
        with self.assertRaises(InvalidPhoneError):
            normalize_iranian_phone(None)


class OwnerOtpServiceTests(TestCase):
    def setUp(self):
        cache.clear()  # OTP rate-limit counters are cache-backed and leak across tests otherwise

    def test_request_creates_a_pending_challenge(self):
        owner_otp_service.request_otp(phone="09121234567", purpose="login", client_ip="1.2.3.4")
        challenge = OwnerOtpChallenge.objects.get(phone="09121234567")
        self.assertTrue(challenge.is_usable)

    def test_wrong_code_does_not_verify_and_counts_attempt(self):
        owner_otp_service.request_otp(phone="09121234568", purpose="login", client_ip="1.2.3.4")
        ok = owner_otp_service.verify_otp(phone="09121234568", purpose="login", code="000000")
        self.assertFalse(ok)
        challenge = OwnerOtpChallenge.objects.get(phone="09121234568")
        self.assertEqual(challenge.attempt_count, 1)

    def test_correct_code_verifies_and_is_single_use(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "123456"
        try:
            svc.request_otp(phone="09121234569", purpose="login", client_ip="1.2.3.4")
            ok = svc.verify_otp(phone="09121234569", purpose="login", code="123456")
            self.assertTrue(ok)
            replay = svc.verify_otp(phone="09121234569", purpose="login", code="123456")
            self.assertFalse(replay)
        finally:
            svc._generate_code = original

    def test_exceeding_max_verify_attempts_permanently_invalidates_code(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "654321"
        try:
            svc.request_otp(phone="09121234570", purpose="login", client_ip="1.2.3.4")
            for _ in range(svc.MAX_VERIFY_ATTEMPTS):
                svc.verify_otp(phone="09121234570", purpose="login", code="000000")
            # Even the real code no longer works once max attempts is hit.
            ok = svc.verify_otp(phone="09121234570", purpose="login", code="654321")
            self.assertFalse(ok)
        finally:
            svc._generate_code = original

    def test_phone_request_rate_limit_blocks_excessive_requests(self):
        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW):
            owner_otp_service.request_otp(phone="09121234571", purpose="login", client_ip="1.2.3.4")
        with self.assertRaises(owner_otp_service.OtpRateLimitError):
            owner_otp_service.request_otp(phone="09121234571", purpose="login", client_ip="1.2.3.4")

    def test_ip_request_rate_limit_blocks_excessive_requests_across_phones(self):
        for i in range(owner_otp_service.IP_MAX_REQUESTS):
            owner_otp_service.request_otp(phone=f"0912000{i:04d}", purpose="login", client_ip="9.9.9.9")
        with self.assertRaises(owner_otp_service.OtpRateLimitError):
            owner_otp_service.request_otp(phone="09120009999", purpose="login", client_ip="9.9.9.9")

    def test_code_is_never_stored_in_plaintext(self):
        owner_otp_service.request_otp(phone="09121234572", purpose="login", client_ip="1.2.3.4")
        challenge = OwnerOtpChallenge.objects.get(phone="09121234572")
        self.assertNotRegex(challenge.code_hash, r"^\d{6}$")
        self.assertTrue(challenge.code_hash.startswith("pbkdf2") or "$" in challenge.code_hash)


class GetOrCreateOwnerByPhoneTests(TestCase):
    def test_creates_new_user_and_owner_profile(self):
        user, created = owner_auth_service.get_or_create_owner_by_phone(phone="09121234573", full_name="Ali")
        self.assertTrue(created)
        self.assertEqual(user.username, "09121234573")
        self.assertFalse(user.has_usable_password())
        profile = OwnerProfile.objects.get(user=user)
        self.assertEqual(profile.phone, "09121234573")
        self.assertEqual(profile.full_name, "Ali")

    def test_returning_owner_reuses_same_user(self):
        first, created_first = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234574", full_name="Sara",
        )
        second, created_second = owner_auth_service.get_or_create_owner_by_phone(phone="09121234574")
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)

    def test_login_call_without_full_name_does_not_erase_existing_name(self):
        owner_auth_service.get_or_create_owner_by_phone(phone="09121234575", full_name="Real Name")
        owner_auth_service.get_or_create_owner_by_phone(phone="09121234575", full_name="")
        profile = OwnerProfile.objects.get(phone="09121234575")
        self.assertEqual(profile.full_name, "Real Name")

    def test_existing_customer_with_same_phone_gains_owner_capability_without_losing_customer_data(self):
        # Deliberate shared-identity decision (see owner_auth_service
        # docstring): a phone that already belongs to a storefront Customer
        # simply gains OwnerProfile too, on the SAME User row — not a
        # duplicate/orphaned account.
        customer_user = User.objects.create_user(username="09121234576", password="whatever")
        customer = Customer.objects.create(user=customer_user, full_name="Customer Person", phone="09121234576")

        owner_user, owner_created = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234576", full_name="Owner Name",
        )
        # The flag means "OwnerProfile created" (the first-store trigger), not
        # "User row created" — see OwnerIdentityResult.
        self.assertTrue(owner_created)
        self.assertEqual(owner_user.pk, customer_user.pk)
        self.assertTrue(OwnerProfile.objects.filter(user=owner_user).exists())
        customer.refresh_from_db()
        self.assertEqual(customer.full_name, "Customer Person")  # untouched


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OtpViewFlowTests(TestCase):
    def setUp(self):
        cache.clear()  # OTP rate-limit counters are cache-backed and leak across tests otherwise

    def _fixed_code(self):
        import apps.portal.services.owner_otp_service as svc

        original = svc._generate_code
        svc._generate_code = lambda: "111222"
        self.addCleanup(setattr, svc, "_generate_code", original)
        return "111222"

    def test_register_request_then_verify_creates_account_and_logs_in(self):
        code = self._fixed_code()
        response = self.client.post(
            "/register/", {"full_name": "New Owner", "phone": "09121234577"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify/", response["Location"])

        response = self.client.post(
            "/verify/", {"phone": "09121234577", "full_name": "New Owner", "code": code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.filter(username="09121234577").exists())

    def test_resend_keeps_registration_name_and_remember_me_from_the_server_session(self):
        code = self._fixed_code()
        self.client.post(
            "/register/",
            {"full_name": "Resend Owner", "phone": "09121234582", "remember_me": "on"},
            HTTP_HOST=_HOST,
        )

        verify_page = self.client.get("/verify/", HTTP_HOST=_HOST)
        # The client is never asked to round-trip name / remember_me / next.
        self.assertNotContains(verify_page, 'name="full_name"')
        self.assertNotContains(verify_page, 'name="remember_me"')

        response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify/", response["Location"])

        response = self.client.post(
            "/verify/", {"phone": "09121234582", "code": code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        profile = OwnerProfile.objects.get(phone="09121234582")
        self.assertEqual(profile.full_name, "Resend Owner")
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_trial_store_provisioning_failure_is_visible_to_new_owner(self):
        code = self._fixed_code()
        self.client.post(
            "/register/",
            {"full_name": "Provision Failure", "phone": "09121234583"},
            HTTP_HOST=_HOST,
        )

        from apps.portal.services import provisioning_service

        with patch(
            "apps.portal.views.provisioning_service.provision_trial_store",
            side_effect=provisioning_service.ProvisioningError("boom"),
        ):
            response = self.client.post(
                "/verify/",
                {"phone": "09121234583", "code": code},
                HTTP_HOST=_HOST,
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ساخت فروشگاه آزمایشی کامل نشد")
        self.assertIn("_auth_user_id", self.client.session)

    def test_verify_with_wrong_code_shows_error_and_does_not_log_in(self):
        self._fixed_code()
        self.client.post("/login/", {"phone": "09121234578"}, HTTP_HOST=_HOST)
        response = self.client.post(
            "/verify/", {"phone": "09121234578", "code": "000000"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verify_page_without_a_pending_request_redirects_to_login(self):
        response = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_login_next_redirect_is_honored_for_a_returning_owner(self):
        # A brand-new phone number always lands in onboarding first (Section
        # 3.1) regardless of "next" — "next" only applies to a RETURNING
        # owner, who already has an account (and presumably a Store).
        owner_auth_service.get_or_create_owner_by_phone(phone="09121234579", full_name="Existing")

        code = self._fixed_code()
        self.client.post("/login/?next=/app/", {"phone": "09121234579"}, HTTP_HOST=_HOST)
        response = self.client.post(
            "/verify/", {"phone": "09121234579", "code": code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/app/")

    def test_new_phone_via_login_is_verified_then_completes_signup_before_getting_a_trial_store(self):
        # A never-seen phone on /login/ only proves phone ownership: no Owner and
        # no Store exist until the «تکمیل ثبت‌نام» step receives a name.
        from apps.stores.models import Store

        stores_before = Store.objects.count()
        code = self._fixed_code()
        self.client.post("/login/", {"phone": "09121234581"}, HTTP_HOST=_HOST)
        response = self.client.post(
            "/verify/", {"phone": "09121234581", "code": code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/signup/complete/")
        self.assertFalse(OwnerProfile.objects.filter(phone="09121234581").exists())
        self.assertEqual(Store.objects.count(), stores_before)

        response = self.client.post("/signup/complete/", {"full_name": "Login Newcomer"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/onboarding/", response["Location"])
        self.assertEqual(Store.objects.count(), stores_before + 1)
        self.assertEqual(OwnerProfile.objects.get(phone="09121234581").full_name, "Login Newcomer")

    def test_second_owner_verify_reuses_account_across_login_sessions(self):
        code = self._fixed_code()
        self.client.post("/register/", {"full_name": "Returning", "phone": "09121234580"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09121234580", "code": code}, HTTP_HOST=_HOST)
        self.client.post("/logout/", HTTP_HOST=_HOST)

        code2 = self._fixed_code()
        self.client.post("/login/", {"phone": "09121234580"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09121234580", "code": code2}, HTTP_HOST=_HOST)
        self.assertEqual(User.objects.filter(username="09121234580").count(), 1)

    def test_invalid_phone_format_is_rejected_with_no_otp_sent(self):
        response = self.client.post("/login/", {"phone": "notaphone"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
