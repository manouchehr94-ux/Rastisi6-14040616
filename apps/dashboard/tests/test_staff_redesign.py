"""RS-14 — the redesigned team-management flow: Persian input, review step, inline errors that keep the input,
existing accounts reused (never overwritten), plan-limit errors (no 500), self-protection, tenant isolation,
search/filters, audit trail and CSRF."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.dashboard.tests.staff_flow import confirmed_action, token_from
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreMembership
from apps.stores.services import membership_service as ms
from apps.subscriptions.services.entitlement_service import UsageLimitExceeded

User = get_user_model()
HOST = "staffredesign.rastisi.localhost"
ROLE = StoreMembership.Role


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class Base(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123300001", password="pass12345", is_staff=True)
        self.owner_m = StoreMembership.objects.create(
            store=self.store, user=self.owner, role=ROLE.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123300001", password="pass12345")
        self.add_url = reverse("dashboard:staff-add")
        self.list_url = reverse("dashboard:staff-list")

    def add(self, **data):
        """FOLLOWUP-05: «confirm» (or no step) goes review → confirm exactly like the browser; other steps are sent as-is."""
        if data.get("step") in (None, "confirm"):
            review = self.client.post(self.add_url, {**data, "step": "review"})
            token = token_from(review)
            if token is None:
                return review
            return self.client.post(self.add_url, {**data, "step": "confirm", "review_token": token})
        return self.client.post(self.add_url, data)


class InputNormalisationTests(Base):
    def test_persian_digits_and_plus98_are_accepted(self):
        for raw, canonical in (("۰۹۱۲۳۳۰۰۱۰۱", "09123300101"), ("+989123300102", "09123300102"), ("9123300103", "09123300103")):
            with self.subTest(raw=raw):
                r = self.add(phone=raw, role=ROLE.ANALYST)
                self.assertEqual(r.status_code, 302, r.content[:300])
                self.assertTrue(StoreMembership.objects.filter(store=self.store, user__username=canonical).exists())

    def test_invalid_phone_keeps_every_entered_value_and_shows_the_error_beside_the_field(self):
        r = self.add(phone="12ab", full_name="سارا محمدی", email="sara@example.com", role=ROLE.ORDER_MANAGER, step="review")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "شماره موبایل باید")
        self.assertContains(r, 'value="12ab"')
        self.assertContains(r, 'value="سارا محمدی"')
        self.assertContains(r, 'value="sara@example.com"')
        self.assertContains(r, "checked")
        self.assertFalse(User.objects.filter(username="12ab").exists())

    def test_all_field_errors_are_reported_at_once(self):
        r = self.add(phone="bad", email="not-an-email", role="", step="review")
        self.assertContains(r, "شماره موبایل باید")
        self.assertContains(r, "ایمیل واردشده معتبر نیست")
        self.assertContains(r, "یک نقش انتخاب کنید")

    def test_owner_role_cannot_be_granted_through_the_form(self):
        r = self.add(phone="09123300110", role=ROLE.OWNER, step="review")
        self.assertContains(r, "نقش انتخاب‌شده نامعتبر")
        self.assertFalse(User.objects.filter(username="09123300110").exists())


class ReviewStepTests(Base):
    def test_review_writes_nothing_and_confirm_creates_exactly_one_member(self):
        users, memberships = User.objects.count(), StoreMembership.objects.count()
        r = self.add(phone="09123300120", full_name="علی", role=ROLE.CATALOG_MANAGER, step="review")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "تأیید و افزودن")
        self.assertContains(r, "حسابِ تیمی ساخته می‌شود")
        self.assertEqual((User.objects.count(), StoreMembership.objects.count()), (users, memberships))
        r2 = self.add(phone="09123300120", full_name="علی", role=ROLE.CATALOG_MANAGER, step="confirm")
        self.assertEqual(r2.status_code, 302)
        r3 = self.add(phone="09123300120", role=ROLE.ANALYST, step="confirm")  # double submit
        self.assertEqual(r3.status_code, 200)
        self.assertContains(r3, "از قبل عضو فعال")
        self.assertEqual(StoreMembership.objects.filter(store=self.store, user__username="09123300120").count(), 1)
        self.assertEqual(User.objects.filter(username="09123300120").count(), 1)

    def test_edit_returns_to_the_form_with_the_values(self):
        r = self.add(phone="09123300121", full_name="نام", role=ROLE.ANALYST, step="edit")
        self.assertContains(r, 'value="09123300121"')
        self.assertContains(r, "بررسی و ادامه")

    def test_review_of_an_active_member_is_refused_inline(self):
        ms.add_staff_member(self.store, phone="09123300122", role=ROLE.ANALYST, invited_by=self.owner)
        r = self.add(phone="09123300122", role=ROLE.ANALYST, step="review")
        self.assertContains(r, "از قبل عضو فعال")

    def test_existing_account_is_reused_not_overwritten(self):
        other = User.objects.create_user(username="09123300123", first_name="نامِ قبلی", email="old@example.com")
        r = self.add(phone="09123300123", full_name="نامِ جدید", email="new@example.com", role=ROLE.ANALYST, step="review")
        self.assertContains(r, "این شماره از قبل حسابی")
        self.add(phone="09123300123", full_name="نامِ جدید", email="new@example.com", role=ROLE.ANALYST)
        other.refresh_from_db()
        self.assertEqual((other.first_name, other.email), ("نامِ قبلی", "old@example.com"))
        self.assertEqual(User.objects.filter(username="09123300123").count(), 1)

    def test_email_owned_by_another_account_is_refused(self):
        User.objects.create_user(username="09123300124", email="taken@example.com")
        r = self.add(phone="09123300125", email="Taken@Example.com", role=ROLE.ANALYST)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "برای حسابِ دیگری ثبت شده")
        self.assertFalse(StoreMembership.objects.filter(user__username="09123300125").exists())


class LimitsAndSafetyTests(Base):
    def test_plan_seat_limit_is_a_form_error_not_a_500(self):
        with patch("apps.subscriptions.services.enforcement.enforce_can_add_staff", side_effect=UsageLimitExceeded("staff.members")):
            r = self.add(phone="09123300130", role=ROLE.ANALYST)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "به سقفِ پلنِ فعلیِ شما")
        self.assertFalse(User.objects.filter(username="09123300130").exists(), "no orphan account on a refused add")

    def test_service_keeps_the_plan_limit_exception_and_reactivation_view_shows_it_as_a_message(self):
        revoked_user = User.objects.create_user(username="09123300140")
        m = StoreMembership.objects.create(
            store=self.store, user=revoked_user, role=ROLE.ANALYST,
            status=StoreMembership.MembershipStatus.REVOKED, accepted_at=timezone.now(), revoked_at=timezone.now(),
        )
        with patch("apps.subscriptions.services.enforcement.enforce_can_add_staff", side_effect=UsageLimitExceeded("staff.members")):
            with self.assertRaises(UsageLimitExceeded):          # service contract (subscription tests rely on it)
                ms.reactivate_membership(m)
            r = confirmed_action(self.client, reverse("dashboard:staff-reactivate", args=[m.pk]), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "به سقفِ پلنِ فعلیِ شما")
        m.refresh_from_db()
        self.assertEqual(m.status, StoreMembership.MembershipStatus.REVOKED)

    def test_cannot_change_or_revoke_yourself(self):
        admin_user = User.objects.create_user(username="09123300131")
        m = StoreMembership.objects.create(
            store=self.store, user=admin_user, role=ROLE.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        with self.assertRaises(ms.MembershipError):
            ms.change_role(m, new_role=ROLE.ANALYST, actor=admin_user)
        with self.assertRaises(ms.MembershipError):
            ms.revoke_membership(m, actor=admin_user)

    def test_the_owner_row_offers_no_destructive_action(self):
        r = self.client.get(self.list_url)
        self.assertNotContains(r, reverse("dashboard:staff-revoke", args=[self.owner_m.pk]))
        self.assertNotContains(r, reverse("dashboard:staff-transfer-ownership", args=[self.owner_m.pk]))

    def test_post_without_csrf_token_is_rejected(self):
        c = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        c.login(username="09123300001", password="pass12345")
        self.assertEqual(c.post(self.add_url, {"phone": "09123300140", "role": ROLE.ANALYST}).status_code, 403)
        self.assertFalse(User.objects.filter(username="09123300140").exists())

    def test_non_owner_roles_cannot_reach_any_staff_endpoint(self):
        m = ms.add_staff_member(self.store, phone="09123300141", role=ROLE.ADMINISTRATOR, invited_by=self.owner)
        self.client.logout()
        user = m.user
        user.set_password("pass12345")
        user.save()
        self.client.login(username=user.username, password="pass12345")
        for url in (self.list_url, self.add_url):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.add_url, {"phone": "09123300142", "role": ROLE.ANALYST}).status_code, 403)


class TenantIsolationAndListTests(Base):
    def setUp(self):
        super().setUp()
        self.other = Store.objects.create(name="B", slug="staff-redesign-b", status=Store.Status.ACTIVE, admin_subdomain="staffredesign-b")
        self.other_owner = User.objects.create_user(username="09123300150")
        StoreMembership.objects.create(
            store=self.other, user=self.other_owner, role=ROLE.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.other_member = ms.add_staff_member(self.other, phone="09123300151", role=ROLE.ANALYST, invited_by=self.other_owner)

    def test_list_search_and_detail_never_include_another_store(self):
        ms.add_staff_member(self.store, phone="09123300152", role=ROLE.ORDER_MANAGER, invited_by=self.owner, full_name="مریم")
        r = self.client.get(self.list_url)
        self.assertContains(r, "09123300152")
        self.assertNotContains(r, "09123300151")
        self.assertNotContains(r, "09123300150")
        self.assertNotContains(self.client.get(self.list_url, {"q": "09123300151"}), "09123300151</b>")
        self.assertEqual(ms.list_memberships(self.store, q="09123300151"), [])

    def test_every_mutating_endpoint_404s_for_a_foreign_membership(self):
        for name in ("staff-change-role", "staff-revoke", "staff-reactivate", "staff-transfer-ownership"):
            with self.subTest(name=name):
                resp = self.client.post(reverse(f"dashboard:{name}", args=[self.other_member.pk]), {"role": ROLE.ANALYST})
                self.assertEqual(resp.status_code, 404)
        self.other_member.refresh_from_db()
        self.assertEqual(self.other_member.status, StoreMembership.MembershipStatus.ACTIVE)

    def test_search_works_with_persian_digits_name_and_filters(self):
        ms.add_staff_member(self.store, phone="09123300153", role=ROLE.CONTENT_EDITOR, invited_by=self.owner, full_name="نیلوفر")
        m = ms.add_staff_member(self.store, phone="09123300154", role=ROLE.ANALYST, invited_by=self.owner)
        ms.revoke_membership(m, actor=self.owner)
        self.assertEqual([x.user.username for x in ms.list_memberships(self.store, q="۰۹۱۲۳۳۰۰۱۵۳")], ["09123300153"])
        self.assertEqual([x.user.username for x in ms.list_memberships(self.store, q="نیلوفر")], ["09123300153"])
        self.assertEqual([x.user.username for x in ms.list_memberships(self.store, status="revoked")], ["09123300154"])
        self.assertEqual({x.role for x in ms.list_memberships(self.store, role=ROLE.OWNER)}, {ROLE.OWNER})
        self.assertContains(self.client.get(self.list_url, {"q": "zzz-none"}), "عضوی با این فیلتر پیدا نشد")

    def test_audit_trail_records_who_what_and_shows_on_the_page(self):
        m = ms.add_staff_member(self.store, phone="09123300155", role=ROLE.ANALYST, invited_by=self.owner)
        ms.change_role(m, new_role=ROLE.ORDER_MANAGER, actor=self.owner)
        ms.revoke_membership(m, actor=self.owner)
        ms.add_staff_member(self.store, phone="09123300155", role=ROLE.CATALOG_MANAGER, invited_by=self.owner)  # reactivation
        codes = list(AuditLogEntry.objects.filter(store=self.store).values_list("action_code", flat=True))
        for code in ("staff.added", "staff.role_changed", "staff.revoked", "staff.reactivated"):
            self.assertIn(code, codes)
        r = self.client.get(self.list_url)
        self.assertContains(r, "آخرین تغییرات تیم")
        self.assertContains(r, "نقش تغییر کرد")
        self.assertFalse(AuditLogEntry.objects.filter(store=self.other).exists() and AuditLogEntry.objects.filter(store=self.other, actor=self.owner).exists())


class TeamActivityRowsTests(Base):
    """FOLLOWUP-04 — «آخرین تغییرات تیم» is a list of structured rows: Jalali date + time, action badge, target, role change,
    actor and result; newest first; nothing is deleted or reordered by the presentation."""

    def test_rows_show_when_what_who_and_role_change(self):
        m = ms.add_staff_member(self.store, phone="09123300161", role=ROLE.ANALYST, invited_by=self.owner,
                                full_name="کارمند با یک نام خیلی خیلی طولانی برای آزمون بریده نشدن متن")
        ms.change_role(m, new_role=ROLE.ORDER_MANAGER, actor=self.owner)
        before = AuditLogEntry.objects.filter(store=self.store, action_code__startswith="staff.").count()
        html = self.client.get(self.list_url).content.decode()
        rows = html.split('class="team-event"')[1:]
        self.assertEqual(len(rows), before)
        newest = rows[0]
        self.assertIn('data-event="staff.role_changed"', newest)
        self.assertIn('class="te-badge info"', newest)
        self.assertIn("نقش تغییر کرد", newest)
        self.assertIn("09123300161", newest)
        self.assertIn(ROLE.ANALYST.label + " ← " + ROLE.ORDER_MANAGER.label, newest)    # "before ← after"
        self.assertIn("توسط", newest)
        self.assertRegex(newest, r"۱۴\d\d/\d\d/\d\d")                                   # Jalali date, Persian digits
        self.assertRegex(newest, r"ساعت [۰-۹]{2}:[۰-۹]{2}")                              # readable time
        self.assertNotIn("202", newest.split("</li>")[0].split('datetime="')[0])          # no Gregorian date shown to the owner
        self.assertIn("data-event=\"staff.added\"", rows[1])                              # order: newest first

    def test_presentation_is_responsive_and_never_clips_text(self):
        ms.add_staff_member(self.store, phone="09123300162", role=ROLE.ANALYST, invited_by=self.owner)
        html = self.client.get(self.list_url).content.decode()
        for rule in ("overflow-wrap:anywhere", "grid-template-columns:minmax(0,1fr)", ".team-event{"):
            self.assertIn(rule, html)
        self.assertNotIn("text-overflow:ellipsis", html[html.index(".team-events{"):html.index("</style>")])

    def test_failed_events_are_flagged_not_hidden(self):
        from apps.core.services.audit_service import record_audit_event

        record_audit_event(store=self.store, actor=self.owner, action_code="staff.revoked", object_type="StoreMembership",
                           object_id="1", object_label="09123300163", result=AuditLogEntry.ResultStatus.FAILURE)
        html = self.client.get(self.list_url).content.decode()
        self.assertIn("te-status-bad", html)
