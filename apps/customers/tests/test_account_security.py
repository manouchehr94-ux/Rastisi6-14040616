"""«امنیت حساب»: تغییر رمز با رمز فعلی، تعیین رمز با کد پیامکی، CSRF، محدودیت نرخ، اعتبارسنجی، بدون ارسال واقعی."""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.customers.models import Customer
from apps.sms.models import OtpCode, SmsLog

User = get_user_model()
OLD = "OldPass#2026x"
NEW = "BrandNew#Pass9271"
PHONE = "09127771234"


class SecurityBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username=PHONE, password=OLD)
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری امنیت", phone=PHONE)
        self.client.force_login(self.user)
        self.change = reverse("customers:account-password-change")
        self.code_url = reverse("customers:account-password-code")
        self.set_url = reverse("customers:account-password-set")

    def valid(self, user=None):
        return authenticate(username=(user or self.user).username, password=NEW) is not None

    def post_change(self, current=OLD, new=NEW, confirm=None, client=None):
        return (client or self.client).post(self.change, {"current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm})


class PasswordChangeTests(SecurityBase):
    def test_success_changes_password_keeps_the_current_session_and_never_echoes_passwords(self):
        res = self.post_change()
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-testid="security-done"')
        self.assertNotContains(res, NEW)
        self.assertNotContains(res, OLD)
        self.assertIn("ok", res["HX-Trigger"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertFalse(self.user.check_password(OLD))
        self.assertEqual(self.client.get(reverse("customers:account")).status_code, 200)       # still logged in
        self.assertEqual(SmsLog.objects.count(), 0)                                             # no SMS for a password change

    def test_other_sessions_are_closed(self):
        other = Client(); other.force_login(self.user)
        self.assertEqual(other.get(reverse("customers:account")).status_code, 200)
        self.post_change()
        self.assertFalse(other.get(reverse("customers:account")).context["can_view"])           # the other session is now anonymous

    def test_wrong_current_password_is_refused_with_a_field_error_and_changes_nothing(self):
        res = self.post_change(current="not-my-password")
        self.assertContains(res, "رمز فعلی درست نیست")
        self.assertContains(res, 'aria-invalid="true"')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_new_password_is_validated(self):
        for bad, message in (("short1", "کوتاه"), ("12345678901", "فقط"), ("password", "رایج")):
            res = self.post_change(new=bad)
            self.assertEqual(res.status_code, 200)
            self.assertIn("new_password", res.context["security_errors"], bad)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_similarity_to_the_phone_number_is_refused(self):
        res = self.post_change(new=PHONE + "abc")
        self.assertIn("new_password", res.context["security_errors"])

    def test_confirmation_must_match_and_same_password_is_refused(self):
        self.assertIn("confirm_password", self.post_change(confirm="Different#Pass1234").context["security_errors"])
        self.assertIn("new_password", self.post_change(new=OLD).context["security_errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_guessing_the_current_password_is_rate_limited(self):
        for _ in range(5):
            self.post_change(current="wrong-guess-1")
        res = self.post_change()                                                                # even the right password is blocked now
        self.assertIn("general", res.context["security_errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_requires_login_post_and_csrf(self):
        anon = Client()
        self.assertEqual(anon.post(self.change, {"current_password": OLD, "new_password": NEW, "confirm_password": NEW}).status_code, 403)
        self.assertEqual(self.client.get(self.change).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(self.post_change(client=strict).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_staff_user_without_customer_profile_is_refused(self):
        staff = User.objects.create_user(username="staff-sec", password=OLD, is_staff=True)
        c = Client(); c.force_login(staff)
        self.assertEqual(self.post_change(client=c).status_code, 403)

    def test_a_customer_can_only_change_their_own_password(self):
        victim = User.objects.create_user(username="09127770000", password=OLD)
        Customer.objects.create(user=victim, full_name="قربانی", phone="09127770000")
        self.client.post(self.change, {"current_password": OLD, "new_password": NEW, "confirm_password": NEW, "user": victim.pk, "phone": victim.username})
        victim.refresh_from_db()
        self.assertTrue(victim.check_password(OLD))


class PasswordSetWithCodeTests(SecurityBase):
    CODE = "445566"

    def setUp(self):
        super().setUp()
        import apps.sms.services.otp_service as otp

        self.sent = []
        fake = lambda event, phone, ctx, *, store: (self.sent.append((event, phone)) or SimpleNamespace(status="sent", error_message=""))  # noqa: E731
        patcher = mock.patch.object(otp, "send_event_sms", fake)
        patcher.start(); self.addCleanup(patcher.stop)                                          # never touches a real SMS gateway
        gen = mock.patch.object(otp, "_generate_code", lambda: self.CODE)
        gen.start(); self.addCleanup(gen.stop)

    def request_code(self):
        return self.client.post(self.code_url)

    def post_set(self, code=None, new=NEW, confirm=None):
        return self.client.post(self.set_url, {"code": code or self.CODE, "new_password": new, "confirm_password": new if confirm is None else confirm})

    def test_code_goes_only_to_the_accounts_own_phone_and_moves_to_the_code_stage(self):
        res = self.request_code()
        self.assertContains(res, 'data-testid="password-set-form"')
        self.assertEqual([phone for _, phone in self.sent], [PHONE])
        self.client.post(self.code_url, {"phone": "09120000000"})                              # a posted phone is ignored
        self.assertEqual({phone for _, phone in self.sent}, {PHONE})

    def test_valid_code_sets_the_password_without_asking_for_the_old_one(self):
        self.request_code()
        res = self.post_set()
        self.assertContains(res, 'data-testid="security-done"')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertEqual(self.client.get(reverse("customers:account")).status_code, 200)

    def test_wrong_code_is_refused_and_a_weak_password_does_not_burn_the_code(self):
        self.request_code()
        self.assertIn("code", self.post_set(code="000000").context["security_errors"])
        self.assertIn("new_password", self.post_set(new="123456789012").context["security_errors"])
        self.assertTrue(self.post_set().context.get("security_done"))                            # the real code still works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))

    def test_code_is_single_use(self):
        self.request_code()
        self.post_set()
        again = self.post_set(new="Another#Pass8812")
        self.assertIn("code", again.context["security_errors"])

    def test_without_requesting_a_code_nothing_changes(self):
        res = self.post_set()
        self.assertIn("code", res.context["security_errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_code_requests_are_rate_limited(self):
        for _ in range(3):
            self.request_code()
        blocked = self.request_code()
        self.assertIn("general", blocked.context["security_errors"])
        self.assertEqual(OtpCode.objects.filter(phone=PHONE).count(), 3)

    def test_requires_login_and_csrf(self):
        self.assertEqual(Client().post(self.code_url).status_code, 403)
        self.assertEqual(Client().post(self.set_url, {"code": self.CODE}).status_code, 403)
        strict = Client(enforce_csrf_checks=True); strict.force_login(self.user)
        self.assertEqual(strict.post(self.code_url).status_code, 403)
        self.assertEqual(strict.post(self.set_url, {"code": self.CODE, "new_password": NEW, "confirm_password": NEW}).status_code, 403)


class SecurityTabRenderingTests(SecurityBase):
    def test_security_tab_is_in_the_account_page_with_labelled_password_fields(self):
        html = self.client.get(reverse("customers:account")).content.decode()
        self.assertIn('id="acct-panel-security"', html)
        self.assertIn('autocomplete="current-password"', html)
        self.assertEqual(html.count('autocomplete="new-password"'), 2)
        for field_id in ("acct_cur_pw", "acct_new_pw", "acct_conf_pw"):
            self.assertIn(f'for="{field_id}"', html)
