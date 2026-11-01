"""Inbox HTTP layer (store dashboard + platform admin): bell, page, detail, actions, summary API, preferences, push subscription endpoints, test notification, service worker.
CSRF, permission, tenant isolation, IDOR (uuid of someone else's item = 404), XSS, rate limit. No external service."""

import json
import socket
from unittest import mock

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase, _user_with_role
from apps.notifications.models import InboxItem, NotificationEvent, NotificationPreference, WebPushSubscription
from apps.notifications.services import inbox_engine as eng
from apps.notifications.services import inbox_service as svc
from apps.notifications.services import scope as S
from apps.notifications.tests.test_inbox_engine import VALID_SUB
from apps.stores.models import Store, StoreMembership

PLATFORM_HOST = "platformadmins.rastisi.localhost"


class _V(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        guard = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection attempted"))
        guard.start()
        self.addCleanup(guard.stop)
        from django.conf import settings
        from apps.core.models import ShopSettings
        from apps.stores.models import StoreDomain

        self.other = Store.objects.create(name="Other", slug="nv-other", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.other)
        self.other_owner = _user_with_role(self.other, "nv-other-owner", StoreMembership.Role.OWNER)
        hosts = {}
        for store, label in ((self.store, "nv-a"), (self.other, "nv-b")):                                # two stores ⇒ host-based admin resolution (as in production)
            hosts[label] = f"{label}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
            StoreDomain.objects.create(store=store, hostname=hosts[label], is_primary=True, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                       verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
            store.admin_subdomain = label
            store.save(update_fields=["admin_subdomain"])
        self.host_a, self.host_b = hosts["nv-a"], hosts["nv-b"]
        self.enterContext(override_settings(ALLOWED_HOSTS=[self.host_a, self.host_b, PLATFORM_HOST, "testserver"]))
        self.client = Client(HTTP_HOST=self.host_a)
        from django.contrib.auth import get_user_model
        self.platform = get_user_model().objects.create_user(username="nv-platform", password="x", is_staff=True, is_superuser=True)
        self._login(self.owner)

    def ev(self, key="order.canceled", **kw):
        kw.setdefault("title", "لغو سفارش DM-1")
        kw.setdefault("link_kwargs", {"code": self.order.code})
        return eng.publish(key, store=self.store, **kw)

    def item(self, user=None, event=None):
        return InboxItem.objects.get(event=event or NotificationEvent.objects.latest("id"), user=user or self.owner)

    def url(self, name, **kw):
        return reverse(f"dashboard:{name}", kwargs=kw)


class BellAndPageTests(_V):
    def test_bell_is_rendered_with_the_unread_count_for_members_only(self):
        self.ev(dedupe_key="b1")
        self.ev(dedupe_key="b2")
        html = self.client.get(self.url("dashboard")).content.decode()
        self.assertIn('data-nt-bell', html)
        self.assertIn('data-unread="2"', html)
        self.assertIn('notifications/inbox.js', html)
        self.assertIn(self.url("inbox-summary"), html)
        self.assertEqual(Client(HTTP_HOST=self.host_a).get(self.url("dashboard")).status_code, 302)                      # anonymous: no page, therefore no bell

    def test_the_counter_belongs_to_the_user_and_the_store(self):
        self.ev(dedupe_key="c1")
        self._login(self.catalog_manager)                                                         # no ORDER_VIEW → sees nothing
        self.assertIn('data-unread="0"', self.client.get(self.url("dashboard")).content.decode().replace("&quot;", '"'))

    def test_inbox_page_lists_filters_and_paginates(self):
        for i in range(25):
            self.ev(dedupe_key=f"p{i}", title=f"اعلان شماره {i}")
        html = self.client.get(self.url("inbox-home")).content.decode()
        self.assertEqual(html.count('data-testid="inbox-row"'), svc.PAGE_SIZE)
        self.assertIn("صفحه ۱ از ۲", html)
        self.assertEqual(self.client.get(self.url("inbox-home") + "?page=2").content.decode().count('data-testid="inbox-row"'), 5)
        self.assertEqual(self.client.get(self.url("inbox-home") + "?q=شماره 7").content.decode().count('data-testid="inbox-row"'), 1)
        empty = self.client.get(self.url("inbox-home") + "?q=چیزیکهنیست").content.decode()
        self.assertIn('data-testid="inbox-empty"', empty)
        self.assertIn("نتیجه‌ای پیدا نشد", empty)

    def test_empty_inbox_has_an_explanatory_state(self):
        html = self.client.get(self.url("inbox-home")).content.decode()
        self.assertIn('data-testid="inbox-empty"', html)
        self.assertIn("اعلانی نیست", html)

    def test_titles_are_escaped_everywhere_no_xss(self):
        self.ev(dedupe_key="x1", title="<script>alert(1)</script>", summary="<img src=x onerror=alert(2)>")
        for url in (self.url("inbox-home"), self.url("inbox-detail", public_id=self.item().public_id)):
            html = self.client.get(url).content.decode()
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertNotIn("<img src=x", html)
            self.assertIn("&lt;script&gt;", html)

    def test_the_page_never_shows_another_stores_or_users_items(self):
        eng.publish("order.canceled", store=self.other, title="راز فروشگاه دیگر", link_kwargs={"code": "X"})
        self.assertNotIn("راز فروشگاه دیگر", self.client.get(self.url("inbox-home")).content.decode())
        self._login(self.analyst)
        self.ev(dedupe_key="own")
        self.assertIn("لغو سفارش DM-1", self.client.get(self.url("inbox-home")).content.decode())
        self._login(self.catalog_manager)
        self.assertNotIn("لغو سفارش DM-1", self.client.get(self.url("inbox-home")).content.decode())


class ActionTests(_V):
    def post(self, name, user_client=None, **kw):
        return (user_client or self.client).post(self.url(name, **kw))

    def test_actions_persist_and_the_json_mode_returns_the_new_counter(self):
        ev = self.ev(dedupe_key="a1")
        item = self.item(event=ev)
        r = self.client.post(self.url("inbox-action", public_id=item.public_id, action="read"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.json(), {"ok": True, "unread": 0})
        self.assertIsNotNone(InboxItem.objects.get(pk=item.pk).read_at)
        for action, field in (("pin", "pinned"), ("archive", "archived_at")):
            self.client.post(self.url("inbox-action", public_id=item.public_id, action=action))
            self.assertTrue(getattr(InboxItem.objects.get(pk=item.pk), field))
        bad = self.client.post(self.url("inbox-action", public_id=item.public_id, action="explode"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(bad.status_code, 400)

    def test_html_form_post_redirects_back_only_inside_the_inbox(self):
        item = self.item(event=self.ev(dedupe_key="a2"))
        r = self.client.post(self.url("inbox-action", public_id=item.public_id, action="read"), {"next": self.url("inbox-home") + "?view=unread"})
        self.assertEqual(r["Location"], self.url("inbox-home") + "?view=unread")
        r = self.client.post(self.url("inbox-action", public_id=item.public_id, action="unread"), {"next": "https://evil.example/phish"})
        self.assertEqual(r["Location"], self.url("inbox-home"))
        r = self.client.post(self.url("inbox-action", public_id=item.public_id, action="unread"), {"next": "/admin-portal/orders/"})
        self.assertEqual(r["Location"], self.url("inbox-home"))

    def test_idor_someone_elses_item_is_404_for_every_action_and_page(self):
        ev = self.ev(dedupe_key="idor")
        theirs = self.item(user=self.administrator, event=ev)
        self.assertEqual(self.client.post(self.url("inbox-action", public_id=theirs.public_id, action="read"), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 404)
        self.assertEqual(self.client.get(self.url("inbox-detail", public_id=theirs.public_id)).status_code, 404)
        self.assertEqual(self.client.get(self.url("inbox-go", public_id=theirs.public_id)).status_code, 404)
        self.assertIsNone(InboxItem.objects.get(pk=theirs.pk).read_at)

    def test_cross_store_member_cannot_read_this_stores_item_even_with_its_uuid(self):
        item = self.item(event=self.ev(dedupe_key="xs"))
        client = Client(HTTP_HOST=self.host_a)                                                    # this store's admin host, but a member of ANOTHER store
        client.force_login(self.other_owner)
        self.assertIn(client.get(self.url("inbox-detail", public_id=item.public_id)).status_code, (302, 403, 404))
        theirs = Client(HTTP_HOST=self.host_b)                                                    # their own host: the uuid still resolves to nothing
        theirs.force_login(self.other_owner)
        self.assertEqual(theirs.get(self.url("inbox-detail", public_id=item.public_id)).status_code, 404)

    def test_mark_all_read(self):
        for i in range(3):
            self.ev(dedupe_key=f"m{i}")
        r = self.client.post(self.url("inbox-read-all"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.json()["marked"], 3)
        self.assertEqual(svc.unread_count(self.owner, self.store), 0)

    def test_csrf_is_enforced_on_every_mutating_endpoint(self):
        item = self.item(event=self.ev(dedupe_key="csrf"))
        strict = Client(enforce_csrf_checks=True, HTTP_HOST=self.host_a)
        strict.force_login(self.owner)
        for url in (self.url("inbox-action", public_id=item.public_id, action="read"), self.url("inbox-read-all"), self.url("inbox-test"),
                    self.url("inbox-push-subscribe"), self.url("inbox-push-unsubscribe"), self.url("inbox-preferences")):
            self.assertEqual(strict.post(url, {}).status_code, 403, url)
        self.assertIsNone(InboxItem.objects.get(pk=item.pk).read_at)

    def test_get_is_rejected_for_mutations(self):
        item = self.item(event=self.ev(dedupe_key="get"))
        self.assertEqual(self.client.get(self.url("inbox-action", public_id=item.public_id, action="read")).status_code, 405)
        self.assertEqual(self.client.get(self.url("inbox-read-all")).status_code, 405)

    def test_go_marks_read_and_opens_the_entity_only_when_the_destination_is_permitted(self):
        item = self.item(event=self.ev(dedupe_key="go1"))
        r = self.client.get(self.url("inbox-go", public_id=item.public_id))
        self.assertEqual(r["Location"], self.url("order-detail", code=self.order.code))
        self.assertIsNotNone(InboxItem.objects.get(pk=item.pk).read_at)
        NotificationEvent.objects.filter(pk=item.event_id).update(link_permission="settings.manage")        # destination needs more than the receiver has
        self._login(self.order_manager)
        mine = self.item(user=self.order_manager, event=item.event)
        r = self.client.get(self.url("inbox-go", public_id=mine.public_id))
        self.assertEqual(r["Location"], self.url("inbox-detail", public_id=mine.public_id))        # not bypassing the destination's permission
        self.assertNotIn("order-detail", r["Location"])

    def test_a_stored_link_cannot_become_an_open_redirect(self):
        ev = self.ev(dedupe_key="redir")
        NotificationEvent.objects.filter(pk=ev.pk).update(link_name="https://evil.example/", link_kwargs={})
        item = self.item(event=ev)
        r = self.client.get(self.url("inbox-go", public_id=item.public_id))
        self.assertTrue(r["Location"].startswith("/admin-portal/"))
        self.assertNotIn("evil.example", r["Location"])

    def test_revoking_membership_blocks_the_inbox_pages_themselves(self):
        self.ev(dedupe_key="rev")
        m = StoreMembership.objects.get(user=self.order_manager, store=self.store)
        StoreMembership.objects.filter(pk=m.pk).update(status=StoreMembership.MembershipStatus.REVOKED, revoked_at=timezone.now())
        self._login(self.order_manager)
        for url in (self.url("inbox-home"), self.url("inbox-summary")):
            self.assertEqual(self.client.get(url).status_code, 302)                                  # staff_required: no active membership ⇒ out


class SummaryApiTests(_V):
    def test_summary_is_json_no_store_and_scoped(self):
        self.ev(dedupe_key="s1", title="مهم")
        r = self.client.get(self.url("inbox-summary"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])
        data = r.json()
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["items"][0]["title"], "مهم")
        self.assertEqual(data["user_key"], f"{self.owner.pk}:{S.key_for(self.store)}")
        self.assertNotIn("id", {k for k in data["items"][0] if isinstance(data["items"][0][k], int) and k == "id"})        # public uuid only
        self.assertEqual(len(data["items"][0]["id"]), 36)

    def test_toast_once_then_not_again_with_the_cursor(self):
        self.ev(dedupe_key="s2", title="فوری")
        first = self.client.get(self.url("inbox-summary")).json()
        self.assertEqual(len(first["toasts"]), 1)
        second = self.client.get(self.url("inbox-summary") + f"?since={first['now_ms']}").json()
        self.assertEqual(second["toasts"], [])

    def test_anonymous_gets_a_redirect_not_data(self):
        r = Client(HTTP_HOST=self.host_a).get(self.url("inbox-summary"))
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("application/json", r.get("Content-Type", ""))

    def test_a_malformed_cursor_is_ignored(self):
        self.assertEqual(self.client.get(self.url("inbox-summary") + "?since=abc").status_code, 200)

    def test_polling_cost_is_constant_in_queries(self):
        for i in range(12):
            self.ev(dedupe_key=f"q{i}")
        with self.assertNumQueries(self._queries()):
            self.client.get(self.url("inbox-summary"))

    def _queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url("inbox-summary"))
        self.assertLessEqual(len(ctx), 14)
        return len(ctx)


class PreferenceTests(_V):
    def test_save_and_reload_persists_per_user_and_scope(self):
        r = self.client.post(self.url("inbox-preferences"), {"toast_enabled": "", "mute_low": "1", "min_toast_severity": "4", "categories": ["orders", "security"], "browser_enabled": "1"})
        self.assertEqual(r.status_code, 302)
        pref = NotificationPreference.objects.get(user=self.owner, scope_key=S.key_for(self.store))
        self.assertFalse(pref.toast_enabled)
        self.assertTrue(pref.mute_low and pref.browser_enabled)
        self.assertEqual(pref.min_toast_severity, 4)
        self.assertIn("finance", pref.disabled_categories)
        self.assertNotIn("orders", pref.disabled_categories)
        self.assertNotIn("security", pref.disabled_categories)                                    # security can never be switched off
        self.assertFalse(NotificationPreference.objects.filter(user=self.administrator).exists())
        page = self.client.get(self.url("inbox-preferences")).content.decode()
        self.assertIn('data-testid="prefs-form"', page)

    def test_only_categories_the_user_may_receive_are_offered(self):
        self._login(self.content_editor)
        page = self.client.get(self.url("inbox-preferences")).content.decode()
        self.assertIn('data-cat="customers"', page)                                              # review.pending (CONTENT_MANAGE)
        self.assertNotIn('data-cat="finance"', page)
        self.assertNotIn('data-cat="security"', page)

    def test_invalid_severity_input_is_ignored(self):
        self.client.post(self.url("inbox-preferences"), {"min_toast_severity": "999", "categories": ["orders"]})
        self.assertEqual(NotificationPreference.objects.get(user=self.owner).min_toast_severity, 3)

    def test_the_page_states_email_and_mobile_are_not_active(self):
        page = self.client.get(self.url("inbox-preferences")).content.decode()
        self.assertIn("به‌زودی", page)
        self.assertNotIn("name=\"email_enabled\"", page)

    def test_platform_and_store_preferences_are_independent(self):
        NotificationPreference.objects.create(user=self.owner, scope_key=S.key_for(self.store), toast_enabled=False)
        self.assertTrue(svc.get_preference(self.owner, self.other).toast_enabled)


class PushEndpointTests(_V):
    def sub(self, payload=None, **kw):
        return self.client.post(self.url("inbox-push-subscribe"), data=json.dumps(payload or VALID_SUB), content_type="application/json", **kw)

    def test_subscribe_validates_registers_and_unsubscribes(self):
        self.assertEqual(self.sub().status_code, 200)
        self.assertEqual(WebPushSubscription.objects.filter(user=self.owner, revoked_at__isnull=True).count(), 1)
        self.assertEqual(self.sub({"endpoint": "https://evil.example/x", "keys": VALID_SUB["keys"]}).status_code, 400)
        self.assertEqual(self.sub({"endpoint": "http://fcm.googleapis.com/x", "keys": VALID_SUB["keys"]}).status_code, 400)
        r = self.client.post(self.url("inbox-push-unsubscribe"), data=json.dumps({"endpoint": VALID_SUB["endpoint"]}), content_type="application/json")
        self.assertEqual(r.json()["revoked"], 1)

    def test_subscribe_requires_login_and_garbage_is_a_400(self):
        self.assertEqual(Client(HTTP_HOST=self.host_a).post(self.url("inbox-push-subscribe"), data="{}", content_type="application/json").status_code, 302)
        r = self.client.post(self.url("inbox-push-subscribe"), data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_form_removal_of_a_device_cannot_touch_someone_elses(self):
        self.sub()
        mine = WebPushSubscription.objects.get(user=self.owner)
        self._login(self.administrator)
        self.client.post(self.url("inbox-push-unsubscribe"), {"device": mine.pk})
        mine.refresh_from_db()
        self.assertIsNone(mine.revoked_at)

    def test_subscription_rate_limit(self):
        codes = [self.sub().status_code for _ in range(23)]
        self.assertIn(429, codes)

    def test_the_stored_endpoint_never_appears_in_any_page_or_api_response(self):
        self.sub()
        pages = [self.client.get(self.url(n)).content.decode() for n in ("inbox-preferences", "inbox-home", "inbox-summary")]
        for body in pages:
            self.assertNotIn("abc123", body)
            self.assertNotIn(VALID_SUB["keys"]["auth"], body)


class TestNotificationAndWorkerFileTests(_V):
    def test_the_test_notification_goes_to_the_requester_only_and_is_visible_even_if_the_category_is_off(self):
        NotificationPreference.objects.create(user=self.owner, scope_key=S.key_for(self.store), disabled_categories=["system"])
        r = self.client.post(self.url("inbox-test"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(svc.unread_count(self.owner, self.store), 1)
        self.assertEqual(svc.unread_count(self.administrator, self.store), 0)
        self.assertEqual(svc.summary(self.owner, self.store)["toasts"][0]["title"], "اعلان آزمایشی")

    def test_the_test_notification_is_rate_limited(self):
        codes = [self.client.post(self.url("inbox-test"), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code for _ in range(12)]
        self.assertEqual(codes[:10], [200] * 10)
        self.assertIn(429, codes[10:])

    def test_service_worker_is_served_with_scope_header_and_receives_no_payload_logic(self):
        r = self.client.get(self.url("inbox-sw"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertEqual(r["Service-Worker-Allowed"], "/admin-portal/")
        body = r.content.decode()
        self.assertIn(self.url("inbox-summary"), body)
        self.assertNotIn("__SUMMARY_URL__", body)
        self.assertNotIn("event.data", body)                                                      # nothing is read from the push payload
        self.assertEqual(Client(HTTP_HOST=self.host_a).get(self.url("inbox-sw")).status_code, 302)

    def test_management_commands_run_and_are_safe_with_flags_off(self):
        from django.core.management import call_command
        from io import StringIO

        self.ev(dedupe_key="cmd")
        out = StringIO()
        call_command("process_inbox_deliveries", stdout=out)
        self.assertIn("0 processed", out.getvalue())
        call_command("prune_notifications", stdout=out)
        self.assertIn("deleted_events=0", out.getvalue())
        out = StringIO()
        call_command("generate_vapid_keys", stdout=out)
        self.assertIn("RASTISI_VAPID_PRIVATE_KEY=", out.getvalue())


class PlatformScopeTests(_V):
    def c(self, user):
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(user)
        return client

    def purl(self, name, **kw):
        return reverse(f"portal_platform_admin:{name}", kwargs=kw, urlconf="shop_core.urls_platform_admin")

    def test_platform_staff_sees_platform_events_with_a_bell_and_a_store_owner_gets_a_404(self):
        eng.publish("platform.store_created", title="فروشگاه تازه")
        staff = self.c(self.platform)
        page = staff.get(self.purl("inbox-home"))
        self.assertEqual(page.status_code, 200)
        self.assertIn("فروشگاه تازه", page.content.decode())
        home = staff.get(self.purl("home")).content.decode()
        self.assertIn("data-nt-bell", home)
        self.assertEqual(self.c(self.owner).get(self.purl("inbox-home")).status_code, 404)
        self.assertEqual(self.c(self.owner).get(self.purl("inbox-summary")).status_code, 404)

    def test_platform_items_are_invisible_in_store_panels_and_vice_versa(self):
        eng.publish("platform.store_created", title="فقط پلتفرم")
        self.ev(dedupe_key="pv", title="فقط فروشگاه")
        self.assertNotIn("فقط پلتفرم", self.client.get(self.url("inbox-home")).content.decode())
        self.assertNotIn("فقط فروشگاه", self.c(self.platform).get(self.purl("inbox-home")).content.decode())
        self.assertEqual(svc.unread_count(self.platform, None), 1)

    def test_platform_item_ids_cannot_be_used_from_a_store_panel(self):
        eng.publish("platform.store_created", title="x")
        item = InboxItem.objects.get(user=self.platform)
        self.assertEqual(self.client.get(self.url("inbox-detail", public_id=item.public_id)).status_code, 404)

    def test_platform_preferences_do_not_touch_store_preferences(self):
        self.c(self.platform).post(self.purl("inbox-preferences"), {"toast_enabled": "1", "categories": ["system"]})
        self.assertTrue(NotificationPreference.objects.filter(user=self.platform, scope_key="platform").exists())
        self.assertFalse(NotificationPreference.objects.filter(user=self.platform, scope_key__startswith="store:").exists())

    def test_platform_test_notification_and_sw_scope(self):
        staff = self.c(self.platform)
        self.assertEqual(staff.post(self.purl("inbox-test"), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200)
        self.assertEqual(svc.unread_count(self.platform, None), 1)
        self.assertEqual(staff.get(self.purl("inbox-sw"))["Service-Worker-Allowed"], "/")


class ScriptContractTests(PermissionEnforcementTestCase):
    """inbox.js / sw.js run in the browser (exercised in Chromium — see the QA report); these pin the invariants that must never regress."""

    @classmethod
    def _read(cls, name):
        from pathlib import Path

        return (Path(__file__).resolve().parents[1] / "static" / "notifications" / name).read_text(encoding="utf-8")

    def test_inbox_js_builds_dom_safely_and_polls_responsibly(self):
        js = self._read("inbox.js")
        for forbidden in ("innerHTML", "outerHTML", "document.write", "eval(", "insertAdjacentHTML", "new Function"):
            self.assertNotIn(forbidden, js)
        self.assertIn("textContent", js)
        self.assertIn("document.hidden", js)                       # no polling from a hidden tab
        self.assertIn("BroadcastChannel", js)                      # multi-tab coordination
        self.assertIn("Math.min(delay * 2, 300)", js)              # exponential backoff on errors, capped
        self.assertIn("user_key", js)                              # account-switch guard
        self.assertIn("window.location.reload()", js)
        self.assertNotIn("localStorage.setItem('nt_unread", js)    # read/unread state lives in the database, never in the browser
        self.assertIn("requestPermission", js)                     # permission only from an explicit click
        self.assertEqual(js.count("requestPermission"), 1)

    def test_permission_is_requested_only_inside_a_click_handler(self):
        js = self._read("inbox.js")
        before = js[: js.index("requestPermission")]
        self.assertIn("enable.addEventListener('click'", before[-400:])

    def test_service_worker_never_reads_a_push_payload_and_only_opens_same_site_paths(self):
        sw = self._read("sw.js")
        self.assertNotIn("event.data", sw)
        self.assertNotIn("innerHTML", sw)
        self.assertIn("target.charAt(0) !== '/'", sw)
        self.assertIn("credentials: 'same-origin'", sw)
        self.assertIn("if (!item) return;", sw)                   # nothing unread ⇒ no OS notification

    def test_templates_do_not_inline_user_content_into_scripts(self):
        from pathlib import Path

        tpl = Path(__file__).resolve().parents[1] / "templates" / "notifications"
        for path in tpl.rglob("*.html"):
            body = path.read_text(encoding="utf-8")
            self.assertNotIn("|safe", body, path.name)
            self.assertNotIn("mark_safe", body, path.name)
            self.assertNotIn("{% autoescape off", body, path.name)
