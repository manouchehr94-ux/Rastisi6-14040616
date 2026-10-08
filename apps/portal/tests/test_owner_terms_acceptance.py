"""Mandatory, versioned, durable Terms acceptance for NEW owners.

Covers ``/register/`` → OTP → Owner and ``/login/`` → OTP → ``/signup/complete/`` → Owner:
required checkbox (server-side), the single authoritative terms version, session-bound trust,
durable ``OwnerTermsAcceptance`` rows (idempotent, only for a really-created Owner), and the
regressions around existing owners / closed registration / Turnstile / OTP failures.
"""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal import terms as terms_module
from apps.portal.models import OwnerOtpChallenge, OwnerProfile, OwnerTermsAcceptance, PlatformConfiguration
from apps.portal.services import owner_auth_service, owner_otp_service, provisioning_service
from apps.portal.terms import CURRENT_TERMS_VERSION, TERMS_ACCEPTANCE_REQUIRED_MESSAGE
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09121230777"
_NAME = "سارا احمدی"
_SESSION_KEY = "portal_otp_accepted_terms_version"


class _Base(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.base_store_ids = set(Store.objects.values_list("pk", flat=True))
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._fake_send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        return SmsSendResult(success=True, provider_ref_id="test")

    def new_stores(self):
        return Store.objects.exclude(pk__in=self.base_store_ids)

    def post_register(self, *, accept="1", phone=_PHONE, name=_NAME, **extra):
        data = {"full_name": name, "phone": phone, **extra}
        if accept is not None:
            data["accept_terms"] = accept
        return self.client.post("/register/", data, HTTP_HOST=_HOST)

    def verify(self, code=None):
        return self.client.post("/verify/", {"code": code or self.sent[-1]["code"]}, HTTP_HOST=_HOST)

    def assertNothingCreated(self, phone=_PHONE):
        self.assertFalse(User.objects.filter(username=phone).exists())
        self.assertFalse(OwnerProfile.objects.filter(phone=phone).exists())
        self.assertEqual(self.new_stores().count(), 0)
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegisterPageTests(_Base):
    def test_get_shows_an_unchecked_acceptance_checkbox_and_the_terms_link(self):
        html = self.client.get("/register/", HTTP_HOST=_HOST).content.decode()
        box = re.search(r'<input type="checkbox" id="id_accept_terms"[^>]*>', html, re.S).group(0)
        self.assertNotIn("checked", box)
        self.assertIn('name="accept_terms"', box)
        self.assertIn('value="1"', box)
        self.assertIn("required", box)
        self.assertIn("قوانین و مقررات و قرارداد استفاده از راستی‌سی را خوانده‌ام و می‌پذیرم.", html)
        link = re.search(r'<a class="r-terms-link" href="([^"]+)"([^>]*)>', html)
        self.assertEqual(link.group(1), "/terms/")
        self.assertIn('target="_blank"', link.group(2))
        self.assertIn('rel="noopener noreferrer"', link.group(2))
        self.assertIn("مشاهده قوانین و مقررات", html)
        # the vague passive-acceptance copy is gone
        self.assertNotIn("ادامه‌ی ثبت‌نام به معنی پذیرش", html)
        self.assertIn(CURRENT_TERMS_VERSION, html)

    def test_terms_link_target_is_readable_without_authentication(self):
        response = self.client.get("/terms/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="scope"')  # the real document, no modal copy

    def test_the_checkbox_markup_is_accessible_and_has_no_inline_style(self):
        html = self.client.get("/register/", HTTP_HOST=_HOST).content.decode()
        block = html[html.index('class="p-field r-terms-accept'):]
        block = block[:block.index("</div>\n</div>") if "</div>\n</div>" in block else 900]
        self.assertIn('<label class="r-terms-check" for="id_accept_terms">', html)
        self.assertIn('aria-describedby="id_accept_terms_hint"', html)
        self.assertNotIn("style=", block)

    def test_post_without_acceptance_is_rejected_and_creates_nothing(self):
        for accept in (None, "", "0", "false", "on", "yes"):
            with self.subTest(accept=accept):
                response = self.post_register(accept=accept)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, TERMS_ACCEPTANCE_REQUIRED_MESSAGE)
                self.assertContains(response, 'id="id_accept_terms_error"')
                self.assertContains(response, 'aria-invalid="true"')
                self.assertContains(response, 'aria-describedby="id_accept_terms_hint id_accept_terms_error"')
                self.assertEqual(OwnerOtpChallenge.objects.count(), 0)  # no challenge
                self.assertEqual(self.sent, [])  # no SMS
                self.assertNotIn("portal_otp_phone", self.client.session)
                self.assertNotIn(_SESSION_KEY, self.client.session)
                self.assertNothingCreated()

    def test_rejected_post_keeps_what_was_typed_but_never_pre_checks_the_box(self):
        response = self.post_register(accept=None)
        html = response.content.decode()
        self.assertIn(_NAME, html)
        self.assertNotRegex(html, r'id="id_accept_terms"[^>]*checked')

    def test_post_with_acceptance_requests_the_otp_and_binds_the_server_known_version(self):
        response = self.post_register()
        self.assertRedirects(response, "/verify/", fetch_redirect_response=False)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.client.session[_SESSION_KEY], CURRENT_TERMS_VERSION)
        # requesting a code is NOT acceptance: nothing durable yet
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)

    def test_a_forged_terms_version_in_the_post_is_ignored(self):
        self.post_register(terms_version="1999-forged", accepted_terms_version="1999-forged")
        self.assertEqual(self.client.session[_SESSION_KEY], CURRENT_TERMS_VERSION)
        self.verify()
        self.assertEqual(
            list(OwnerTermsAcceptance.objects.values_list("terms_version", flat=True)), [CURRENT_TERMS_VERSION],
        )

    def test_turnstile_failure_sends_no_otp_even_when_terms_were_checked(self):
        from apps.portal.services import turnstile_service

        denied = turnstile_service.TurnstileValidationResult(success=False, error_code="verification-failed")
        with override_settings(
            TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="1x00000000000000000000AA",
            TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA", TURNSTILE_EXPECTED_HOSTNAMES=(_HOST,),
        ), patch("apps.portal.services.turnstile_service.verify_request", return_value=denied):
            response = self.post_register()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertNothingCreated()

    def test_otp_rate_limit_or_sms_failure_creates_no_acceptance(self):
        with patch.object(
            owner_otp_service, "request_otp", side_effect=owner_otp_service.OtpRateLimitError("کند"),
        ):
            response = self.post_register()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(_SESSION_KEY, self.client.session)
        self.assertNothingCreated()


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegistrationFlowTests(_Base):
    def test_successful_registration_creates_one_versioned_acceptance_for_the_verified_user(self):
        self.post_register()
        response = self.verify()
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username=_PHONE)
        self.assertTrue(OwnerProfile.objects.filter(user=user).exists())
        self.assertEqual(self.new_stores().count(), 1)
        row = OwnerTermsAcceptance.objects.get()
        self.assertEqual((row.user_id, row.terms_version), (user.pk, CURRENT_TERMS_VERSION))
        self.assertEqual(row.source, OwnerTermsAcceptance.Source.REGISTRATION)
        self.assertIsNotNone(row.accepted_at)
        # the OTP code is never stored on the acceptance record
        self.assertNotIn(self.sent[-1]["code"], str(row.__dict__))

    def test_tampering_with_or_removing_the_session_acceptance_blocks_owner_creation(self):
        for label, mutate in (
            ("deleted", lambda s: s.pop(_SESSION_KEY)),
            ("forged", lambda s: s.__setitem__(_SESSION_KEY, "1999-forged")),
            ("blank", lambda s: s.__setitem__(_SESSION_KEY, "")),
        ):
            with self.subTest(case=label):
                cache.clear()
                self.client = self.client_class()
                self.post_register()
                session = self.client.session
                mutate(session)
                session.save()
                code = self.sent[-1]["code"]
                response = self.verify(code)
                self.assertRedirects(response, "/register/", fetch_redirect_response=False)
                self.assertNothingCreated()
                self.assertNotIn("portal_otp_phone", self.client.session)  # stale state cleared
                # fail-closed happens BEFORE the code is checked, so the OTP is not burned
                challenge = OwnerOtpChallenge.objects.filter(phone=_PHONE).order_by("-pk").first()
                self.assertIsNone(challenge.consumed_at)

    def test_a_terms_version_bump_between_request_and_verify_forces_reacceptance(self):
        self.post_register()
        with patch("apps.portal.views.CURRENT_TERMS_VERSION", "2099-01-v9"):
            response = self.verify()
        self.assertRedirects(response, "/register/", fetch_redirect_response=False)
        self.assertNothingCreated()

    def test_get_of_verify_without_trusted_acceptance_also_fails_closed(self):
        self.post_register()
        session = self.client.session
        del session[_SESSION_KEY]
        session.save()
        self.assertRedirects(self.client.get("/verify/", HTTP_HOST=_HOST), "/register/", fetch_redirect_response=False)

    def test_resend_keeps_the_trusted_acceptance_state(self):
        self.post_register()
        before = self.client.session[_SESSION_KEY]
        resend = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(resend.status_code, 302)
        self.assertEqual(self.client.session[_SESSION_KEY], before)
        self.verify()
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)

    def test_replay_of_the_verification_does_not_duplicate_acceptance(self):
        self.post_register()
        code = self.sent[-1]["code"]
        self.verify(code)
        self.client.logout()
        self.verify(code)  # the old code is single-use and the session state is gone
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)
        self.assertEqual(self.new_stores().count(), 1)

    def test_idempotent_when_an_acceptance_row_already_exists(self):
        user = User.objects.create_user(username=_PHONE)
        OwnerTermsAcceptance.objects.create(
            user=user, terms_version=CURRENT_TERMS_VERSION, source=OwnerTermsAcceptance.Source.REGISTRATION,
        )
        result = owner_auth_service.resolve_owner_identity_by_phone(
            phone=_PHONE, full_name=_NAME, accepted_terms_version=CURRENT_TERMS_VERSION,
        )
        self.assertTrue(result.owner_created)
        self.assertEqual(OwnerTermsAcceptance.objects.filter(user=user).count(), 1)

    def test_acceptance_rolls_back_with_the_owner_if_creation_fails(self):
        with patch.object(
            OwnerTermsAcceptance.objects, "get_or_create", side_effect=RuntimeError("boom"),
        ), self.assertRaises(RuntimeError):
            owner_auth_service.resolve_owner_identity_by_phone(
                phone=_PHONE, full_name=_NAME, accepted_terms_version=CURRENT_TERMS_VERSION,
            )
        self.assertNothingCreated()

    def test_registering_an_existing_owner_phone_creates_nothing_new(self):
        owner = User.objects.create_user(username=_PHONE)
        OwnerProfile.objects.create(user=owner, phone=_PHONE, full_name="Existing")
        store = provisioning_service.provision_trial_store(owner=owner, name="Old")
        stores_before = Store.objects.count()
        self.post_register()
        self.verify()
        self.assertEqual(Store.objects.count(), stores_before)
        self.assertTrue(Store.objects.filter(pk=store.pk).exists())
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)  # owner_created=False → no row

    def test_historical_rows_do_not_change_when_the_current_version_changes(self):
        self.post_register()
        self.verify()
        row = OwnerTermsAcceptance.objects.get()
        stamp = row.accepted_at
        with patch.object(terms_module, "CURRENT_TERMS_VERSION", "2099-01-v9"):
            row.refresh_from_db()
        self.assertEqual((row.terms_version, row.accepted_at), (CURRENT_TERMS_VERSION, stamp))

    def test_unique_constraint_is_per_user_and_version(self):
        user = User.objects.create_user(username="u1")
        OwnerTermsAcceptance.objects.create(user=user, terms_version="v1", source="registration")
        OwnerTermsAcceptance.objects.create(user=user, terms_version="v2", source="registration")
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            OwnerTermsAcceptance.objects.create(user=user, terms_version="v1", source="registration")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SignupCompleteTests(_Base):
    def verified_unknown_phone(self, phone=_PHONE):
        self.client.post("/login/", {"phone": phone}, HTTP_HOST=_HOST)
        response = self.verify()
        self.assertRedirects(response, "/signup/complete/", fetch_redirect_response=False)

    def complete(self, accept="1", **extra):
        data = {"full_name": _NAME, **extra}
        if accept is not None:
            data["accept_terms"] = accept
        return self.client.post("/signup/complete/", data, HTTP_HOST=_HOST)

    def test_page_shows_unchecked_required_checkbox_and_terms_link(self):
        self.verified_unknown_phone()
        html = self.client.get("/signup/complete/", HTTP_HOST=_HOST).content.decode()
        box = re.search(r'<input type="checkbox" id="id_accept_terms"[^>]*>', html, re.S).group(0)
        self.assertNotIn("checked", box)
        self.assertIn('href="/terms/"', html)
        self.assertIn("مشاهده قوانین و مقررات", html)
        self.assertIn(CURRENT_TERMS_VERSION, html)

    def test_without_acceptance_nothing_is_created_and_the_session_is_kept_for_retry(self):
        self.verified_unknown_phone()
        for accept in (None, "", "0", "false"):
            with self.subTest(accept=accept):
                response = self.complete(accept=accept)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, TERMS_ACCEPTANCE_REQUIRED_MESSAGE)
                self.assertNothingCreated()
                self.assertIn("portal_signup_pending", self.client.session)  # not consumed by a refusal

    def test_with_acceptance_creates_the_owner_store_and_one_acceptance_row(self):
        self.verified_unknown_phone()
        response = self.complete()
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username=_PHONE)
        self.assertEqual(self.new_stores().count(), 1)
        row = OwnerTermsAcceptance.objects.get()
        self.assertEqual((row.user_id, row.terms_version, row.source), (
            user.pk, CURRENT_TERMS_VERSION, OwnerTermsAcceptance.Source.SIGNUP_COMPLETE,
        ))
        # single use: a replay creates nothing more
        self.complete()
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)
        self.assertEqual(self.new_stores().count(), 1)

    def test_posted_phone_user_id_and_terms_version_are_ignored(self):
        other = User.objects.create_user(username="09000000000")
        self.verified_unknown_phone()
        self.complete(phone="09999999999", user=other.pk, user_id=other.pk, terms_version="1999-forged",
                      accepted_terms_version="1999-forged")
        self.assertTrue(OwnerProfile.objects.filter(phone=_PHONE).exists())
        self.assertFalse(OwnerProfile.objects.filter(phone="09999999999").exists())
        row = OwnerTermsAcceptance.objects.get()
        self.assertEqual(row.user.username, _PHONE)
        self.assertEqual(row.terms_version, CURRENT_TERMS_VERSION)
        self.assertFalse(OwnerTermsAcceptance.objects.filter(user=other).exists())

    def test_an_expired_signup_session_creates_nothing_even_with_acceptance(self):
        self.verified_unknown_phone()
        session = self.client.session
        pending = session["portal_signup_pending"]
        pending["verified_at"] -= 10_000
        session["portal_signup_pending"] = pending
        session.save()
        response = self.complete()
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNothingCreated()

    def test_no_session_at_all_creates_nothing(self):
        response = self.complete()
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNothingCreated()

    def test_registration_closed_behaviour_is_unchanged(self):
        self.verified_unknown_phone()
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.new_store_registration_enabled = False
        config.save()
        cache.clear()
        response = self.complete()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        self.assertNothingCreated()


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ExistingOwnersAndVersionTests(_Base):
    def test_existing_owner_login_never_requires_or_records_terms_acceptance(self):
        owner = User.objects.create_user(username=_PHONE)
        OwnerProfile.objects.create(user=owner, phone=_PHONE, full_name="Legacy")
        provisioning_service.provision_trial_store(owner=owner, name="Legacy Store")
        self.client.post("/login/", {"phone": _PHONE}, HTTP_HOST=_HOST)
        response = self.verify()
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)  # nothing fabricated for legacy owners

    def test_login_otp_page_has_no_terms_checkbox(self):
        self.assertNotContains(self.client.get("/login/", HTTP_HOST=_HOST), "accept_terms")

    def test_terms_page_registration_and_signup_use_the_same_single_version(self):
        terms_html = self.client.get("/terms/", HTTP_HOST=_HOST).content.decode()
        register_html = self.client.get("/register/", HTTP_HOST=_HOST).content.decode()
        self.assertRegex(terms_html, r'data-terms-version>نسخه‌ی قوانین: <bdi dir="ltr">%s</bdi>' % re.escape(CURRENT_TERMS_VERSION))
        self.assertIn(f'<bdi dir="ltr">{CURRENT_TERMS_VERSION}</bdi>', register_html)
        self.client.post("/login/", {"phone": _PHONE}, HTTP_HOST=_HOST)
        self.verify()
        signup_html = self.client.get("/signup/complete/", HTTP_HOST=_HOST).content.decode()
        self.assertIn(f'<bdi dir="ltr">{CURRENT_TERMS_VERSION}</bdi>', signup_html)

    def test_version_is_a_single_source_and_never_a_floating_label(self):
        import inspect

        from apps.portal import views

        self.assertNotIn(CURRENT_TERMS_VERSION, inspect.getsource(views))  # no duplicated literal
        self.assertNotEqual(CURRENT_TERMS_VERSION.lower(), "latest")
        self.assertRegex(CURRENT_TERMS_VERSION, r"^\d{4}-\d{2}-v\d+$")

    def test_terms_page_still_has_toc_anchors_and_the_draft_notice(self):
        html = self.client.get("/terms/", HTTP_HOST=_HOST).content.decode()
        self.assertIn("data-legal-toc", html)
        self.assertIn('href="#notifications"', html)
        self.assertIn("data-legal-draft-notice", html)

    def test_registration_closed_page_is_unchanged(self):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.new_store_registration_enabled = False
        config.save()
        cache.clear()
        response = self.client.post("/register/", {"full_name": _NAME, "phone": _PHONE, "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.assertContains(response, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        self.assertEqual(self.sent, [])
        self.assertNothingCreated()
