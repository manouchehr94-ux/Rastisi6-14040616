"""A platform TEAM member (is_staff + a granted notification permission, no store, no OwnerProfile) must be able to sign in
to the platform-admin host with a password — found by the real-HTTP acceptance run (force_login-based tests missed it) —
without widening who may use the owner portal."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()
HOST = "platformadmins.rastisi.localhost"
URLCONF = "shop_core.urls_platform_admin"
PW = "a-very-strong-pass-1"


def make(username, *perms, **flags):
    user = User.objects.create_user(username=username, email=f"{username}@team.test", password=PW, **flags)
    for c in perms:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="notifications", codename=c))
    return user


@override_settings(ALLOWED_HOSTS=[HOST, "testserver", "rastisi.localhost"])
class PlatformTeamLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.login_url = reverse("portal_platform_admin:login", urlconf=URLCONF)

    def attempt(self, ident, password=PW):
        return self.client.post(self.login_url, {"identifier": ident, "password": password}, HTTP_HOST=HOST)

    def test_team_member_with_permission_signs_in_and_lands_on_the_catalog(self):
        make("limited", "view_notification_catalog", is_staff=True)
        for ident in ("limited", "limited@team.test"):
            self.client.logout()
            r = self.attempt(ident)
            self.assertEqual(r.status_code, 302, ident)
            self.assertTrue(r["Location"].endswith("/notifications/"), r["Location"])
            self.assertEqual(self.client.get(r["Location"], HTTP_HOST=HOST).status_code, 200)

    def test_wrong_password_unknown_user_staff_without_permission_and_non_staff_are_all_refused(self):
        make("limited", "view_notification_catalog", is_staff=True)
        make("noperm", is_staff=True)
        make("notstaff", "view_notification_catalog")
        inactive = make("inactive", "view_notification_catalog", is_staff=True)
        inactive.is_active = False
        inactive.save()
        for ident, pw in (("limited", "wrong-password-1"), ("ghost", PW), ("noperm", PW), ("notstaff", PW), ("inactive", PW)):
            r = self.attempt(ident, pw)
            self.assertEqual(r.status_code, 200, ident)   # re-rendered login form, no redirect
            self.assertNotIn("_auth_user_id", self.client.session, ident)

    def test_limited_member_still_cannot_use_other_platform_pages_or_the_owner_portal(self):
        make("limited", "view_notification_catalog", is_staff=True)
        self.attempt("limited")
        self.assertEqual(self.client.get(reverse("portal_platform_admin:notification-senders", urlconf=URLCONF), HTTP_HOST=HOST).status_code, 403)
        from django.test import Client

        owner_portal = Client()
        owner_portal.post("/login/password/", {"identifier": "limited", "password": PW}, HTTP_HOST="rastisi.localhost")
        self.assertNotIn("_auth_user_id", owner_portal.session)  # owner-portal eligibility was NOT widened

    def test_permission_check_is_live_revoking_the_permission_closes_the_door(self):
        user = make("limited", "view_notification_catalog", is_staff=True)
        user.user_permissions.clear()
        self.assertEqual(self.attempt("limited").status_code, 200)
