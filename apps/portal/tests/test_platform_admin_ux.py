"""Platform Owner Admin UX contract: one navigation source, one shell, one design system — and every owner page still works.

Covers: nav registry integrity (no orphan/hidden pages), single sidebar on every page, URL smoke for every GET route,
permission checks, CSRF on every POST form, shared button/numeric-input/namespace rules, and the changed workflows."""

import re
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.catalog.models import IndustryTemplate
from apps.portal import platform_admin_nav as nav
from apps.portal import platform_admin_urls as admin_urls
from apps.portal.models import PublicSitePhoto
from apps.sms.models import SmsPackage, SmsTemplate
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import plan_service as ps
from apps.subscriptions.tests.test_pricing_dynamic import make_plan

User = get_user_model()
ADMIN = "platformadmins.rastisi.localhost"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "portal" / "platform_admin"
CSS = ROOT / "static" / "portal" / "css" / "platform-admin-panel.css"

# Routes that are deliberately NOT sidebar destinations: auth, POST-only actions, or contextual sub-pages reached from a listed page.
POST_ONLY = {
    "logout", "store-suspend", "store-activate", "store-support-login", "store-extend-trial", "store-set-trial-end",
    "store-end-trial-now", "store-change-plan", "store-extend-subscription", "store-add-note", "user-activate", "user-suspend",
    "user-add-note", "public-photo-reset", "public-site-switch", "public-site-reset", "plan-archive", "plan-version-publish",
    "subscription-cancel", "subscription-suspend", "subscription-resume", "sms-package-archive", "sms-credit-adjust",
    "domain-check", "domain-set-primary", "notification-sender-toggle", "notification-platform-template-preview",
    "notification-platform-template-test",
    # PR #40 finance actions
    "coupon-duplicate", "coupon-status", "payment-verify-now", "payment-duplicate-action", "manual-claim-action", "payment-invoice-refund", "payment-refund-complete", "sms-purchase-action",
}
FILE_DOWNLOADS = {"manual-claim-receipt"}          # streams a private receipt file; not an HTML page
NOT_IN_SIDEBAR = POST_ONLY | FILE_DOWNLOADS | {"login"}
INBOX_NAMES = {"inbox-home", "inbox-summary", "inbox-preferences", "inbox-read-all", "inbox-push-subscribe",
               "inbox-push-unsubscribe", "inbox-sw", "inbox-detail", "inbox-open", "inbox-read"}


def url_names():
    return [p.name for p in admin_urls.urlpatterns if p.name]


@override_settings(ROOT_URLCONF="shop_core.urls_platform_admin")
class NavRegistryTests(SimpleTestCase):
    def test_every_nav_target_exists_and_reverses(self):
        names = set(url_names())
        for group in nav.NAV:
            for item in group.items:
                if item.optional and item.url_name not in names:
                    continue
                self.assertIn(item.url_name, names, item.url_name)
                reverse(f"{nav.NS}:{item.url_name}")
                for extra in item.also:
                    self.assertIn(extra, names, f"{item.url_name} also→{extra}")

    def test_no_owner_page_is_hidden_from_navigation(self):
        covered = nav.all_nav_url_names()
        orphan = [n for n in url_names() if n not in covered and n not in NOT_IN_SIDEBAR and not n.startswith("inbox-")]
        self.assertEqual(orphan, [], "every GET page must belong to a nav item (or be declared contextual/POST-only)")

    def test_sub_pages_activate_their_parent_item_and_open_the_group(self):
        for current, parent in (("store-detail", "stores"), ("plan-edit", "plans"), ("feature-edit", "features"), ("sms-package-add", "sms-packages"),
                                ("sms-logs", "sms-messages"), ("payment-invoice-detail", "payments"), ("public-site-edit", "public-site")):
            built = nav.build_nav(current)
            active = [(g["key"], i["name"]) for g in built["groups"] for i in g["items"] if i["active"]]
            self.assertEqual([n for _g, n in active], [parent], current)
            self.assertTrue(all(g["open"] for g in built["groups"] if any(i["active"] for i in g["items"])))
            self.assertIsNotNone(built["breadcrumb"])

    def test_optional_items_appear_exactly_when_their_route_exists(self):
        """PR #40 finance modules are optional: no dead link before the merge, automatic entry after it."""
        names = set(url_names())
        built = nav.build_nav("home")
        flat = {i["name"] for g in built["groups"] for i in g["items"]}
        for group in nav.NAV:
            for item in group.items:
                if item.optional:
                    self.assertEqual(item.url_name in flat, item.url_name in names, item.url_name)
        self.assertIn("payments", flat)

    def test_nav_has_a_single_definition_site(self):
        base = (TEMPLATES / "base.html").read_text()
        self.assertEqual(base.count("pa_sidebar"), 1)
        self.assertNotIn("<aside", base)
        sidebar_users = [p.name for p in TEMPLATES.glob("*.html") if "pa_sidebar" in p.read_text() or "<aside" in p.read_text()]
        self.assertEqual(sorted(sidebar_users), ["_sidebar.html", "base.html"])


class TemplateContractTests(SimpleTestCase):
    def files(self):
        return [p for p in TEMPLATES.glob("*.html")]

    def test_no_inline_styles_scripts_handlers_or_local_style_blocks(self):
        offenders = []
        for p in self.files():
            text = p.read_text()
            for pattern in (r'\sstyle="', r"<style\b", r"\sonclick=", r"\sonsubmit=", r"\sonchange="):
                if re.search(pattern, text):
                    offenders.append(f"{p.name}: {pattern}")
        self.assertEqual(offenders, [])

    def test_every_post_form_carries_a_csrf_token(self):
        missing = []
        for p in self.files():
            text = p.read_text()
            for m in re.finditer(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>', text, re.S | re.I):
                if "csrf_token" not in m.group(0) and "csrfmiddlewaretoken" not in m.group(0):
                    missing.append(p.name)
        self.assertEqual(missing, [])

    def test_buttons_use_the_shared_button_system(self):
        offenders = []
        allowed = ("pa-btn", "pa-x", "pa-linkbtn")
        for p in self.files():
            for m in re.finditer(r"<button\b([^>]*)>", p.read_text()):
                attrs = m.group(1)
                if not any(a in attrs for a in allowed):
                    offenders.append(f"{p.name}: {attrs.strip()[:60]}")
        self.assertEqual(offenders, [])

    def test_no_page_defines_its_own_primary_button_colours(self):
        for p in self.files():
            self.assertNotRegex(p.read_text(), r"background:\s*(linear-gradient|#)", p.name)


class DesignSystemCssTests(SimpleTestCase):
    css = CSS.read_text()

    def test_numeric_spinners_are_hidden_without_custom_stepper_controls(self):
        self.assertIn("input[type=number]::-webkit-inner-spin-button", self.css)
        self.assertRegex(self.css, r"input\[type=number\]\{[^}]*appearance:textfield")
        self.assertRegex(self.css, r"input\[type=number\]\{[^}]*direction:ltr")        # digits never reverse in RTL
        for tpl in TEMPLATES.glob("*.html"):
            self.assertNotRegex(tpl.read_text(), r"(stepper|spin-up|plus-minus)", tpl.name)

    @staticmethod
    def leaking_selectors(css):
        text = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        text = re.sub(r"@font-face\{[^}]*\}", "", text)
        text = re.sub(r"@keyframes [\w-]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", text)
        selectors, depth, buf = [], 0, ""
        for ch in text:
            if ch == "{":
                selectors.append(buf.strip())
                buf, depth = "", depth + 1
            elif ch == "}":
                buf, depth = "", depth - 1
            else:
                buf += ch
        leaks = []
        for sel in selectors:
            if not sel or sel.startswith("@") or sel == ":root":
                continue
            for part in (p.strip() for p in sel.split(",")):
                if part and not (".pa" in part or "pa-" in part or part in ("[x-cloak]", "dialog.pa-dialog")):
                    leaks.append(part)
        return leaks

    def test_every_rule_is_namespaced_to_the_platform_admin_body(self):
        self.assertEqual(self.leaking_selectors(self.css), [], "design-system CSS must not restyle anything outside .pa / pa-* components")

    def test_the_namespace_check_really_detects_a_leak(self):
        self.assertEqual(self.leaking_selectors(self.css + "\nbody{color:red}\ninput[type=number]{appearance:none}\n.btn{margin:0}"),
                         ["body", "input[type=number]", ".btn"])

    def test_design_system_stylesheet_is_loaded_only_by_the_platform_admin_shell(self):
        users = []
        for tpl in (ROOT.parents[1]).rglob("*.html"):
            if "platform-admin-panel.css" in tpl.read_text(errors="ignore"):
                users.append(tpl.relative_to(ROOT.parents[1]).as_posix())
        self.assertEqual(users, ["apps/portal/templates/portal/platform_admin/base.html"])

    def test_sr_only_text_is_contained_by_its_scroll_container_and_stays_readable_by_screen_readers(self):
        """Regression (mobile overflow): an absolutely positioned .pa-sr inside a wide table must be anchored to the table wrapper/card."""
        self.assertRegex(self.css, r"\.pa-tablewrap,\.pa-card\{position:relative\}")
        rule = re.search(r"\.pa-sr\{([^}]*)\}", self.css).group(1)
        for needed in ("position:absolute", "width:1px", "height:1px", "overflow:hidden", "clip:rect(0 0 0 0)", "white-space:nowrap"):
            self.assertIn(needed, rule)
        self.assertNotIn("display:none", rule)               # removing it from the accessibility tree would break screen readers
        self.assertNotIn("visibility:hidden", rule)

    def test_one_control_height_token_drives_buttons_and_inputs(self):
        self.assertIn("--pa-ctl-h:38px", self.css)
        self.assertRegex(self.css, r"\.pa-btn\{[^}]*height:var\(--pa-ctl-h\)")
        self.assertRegex(self.css, r"\.pa-input[^{]*\{[^}]*height:var\(--pa-ctl-h\)")


FINANCE_PAGES = ("payment-gateways", "payment-transactions", "payment-reconciliation", "manual-claims", "manual-claim-detail", "sms-purchases")
FINANCE_TEMPLATES = ("payment_gateways", "payment_transactions", "payment_reconciliation", "manual_claims", "manual_claim_detail",
                     "sms_purchases", "payment_invoice_detail")


class FinanceTemplateContractTests(SimpleTestCase):
    """The PR #40 finance pages use the very same design system — no second styling system for finance."""

    def test_finance_templates_extend_the_shared_shell_and_use_shared_components_only(self):
        for name in FINANCE_TEMPLATES:
            text = (TEMPLATES / f"{name}.html").read_text()
            self.assertIn('{% extends "portal/platform_admin/base.html" %}', text, name)
            self.assertIn('class="pa-pagehead"', text, name)
            self.assertNotRegex(text, r'\sstyle="|<style\b|\sonclick=|\sonsubmit=', name)
            self.assertNotIn("{% if messages %}", text, f"{name}: flash messages are rendered once by the shell")

    def test_money_moving_actions_confirm_before_submitting(self):
        confirms = {
            "payment_invoice_detail": ["payment-refund-complete"],
            "sms_purchases": ["'complete'", "'cancel'", "'refund'"],
            "manual_claim_detail": ["'approve'", "'reject'"],
            "payment_gateways": ["revoke_gate"],
        }
        for name, markers in confirms.items():
            text = (TEMPLATES / f"{name}.html").read_text()
            for marker in markers:
                i = text.index(marker)
                form_start = text.rfind("<form", 0, i)
                self.assertIn("data-confirm=", text[form_start:text.index(">", form_start)], f"{name}: {marker}")


@override_settings(ALLOWED_HOSTS=[ADMIN, "testserver"])
class OwnerPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cache.clear()
        cls.owner = User.objects.create_user(username="uxowner@example.com", email="uxowner@example.com", password="a-very-strong-pass-1",
                                             is_staff=True, is_superuser=True)
        cls.ordinary = User.objects.create_user(username="ux-ord@example.com", email="ux-ord@example.com", password="a-very-strong-pass-1")
        cls.plan, cls.version = make_plan("uxplan", base=100000, limits={"catalog.products": 50})
        cls.store = Store.objects.create(name="فروشگاه UX", slug="ux-store", admin_subdomain="uxs", status=Store.Status.ACTIVE,
                                         platform_code=generate_unique_platform_code())
        StoreMembership.objects.create(store=cls.store, user=cls.ordinary, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        cls.sub = StoreSubscription.objects.create(store=cls.store, plan_version=cls.version, status=StoreSubscription.Status.ACTIVE, is_current=True)
        cls.invoice = SubscriptionInvoice.objects.create(
            store=cls.store, subscription=cls.sub, plan_version=cls.version, kind=SubscriptionInvoice.Kind.INITIAL, number="INV-UX-1",
            currency="IRT", subtotal=100000, tax_total=0, grand_total=100000, amount_paid=0, amount_due=100000, status=SubscriptionInvoice.Status.OPEN)
        cls.domain = StoreDomain.objects.create(store=cls.store, hostname="ux.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                                verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        cls.template = IndustryTemplate.objects.create(slug="uxind", name="صنفِ تست", version=1)
        cls.package = SmsPackage.objects.create(name="بسته‌یِ تست", credit_amount=100, price=10000)
        from apps.billing.services import platform_coupon_service as _pcs

        cls.coupon = _pcs.create_coupon(actor=cls.owner, code="UXCOUPON", name="کوپن UX", kind="percent", percent=10)
        from apps.billing.models import PlatformManualPaymentClaim

        cls.claim = PlatformManualPaymentClaim.objects.create(
            store=cls.store, invoice=cls.invoice, expected_amount=100000, reference_raw="TRK-UX-1", reference_key="trkux1",
            transferred_at=timezone.now(), expires_at=timezone.now() + timedelta(days=2))

    def params(self):
        from apps.notifications import events as notif_events
        from apps.portal.public_site import registry

        SmsTemplate.ensure_defaults()
        return {
            "store_public_id": str(self.store.public_id), "user_id": self.owner.pk, "plan_id": self.plan.pk, "version_id": self.version.pk,
            "subscription_id": self.sub.pk, "invoice_id": self.invoice.pk, "template_id": self.template.pk, "domain_id": self.domain.pk,
            "package_id": self.package.pk, "feature_id": self._feature_id(), "claim_id": self.claim.pk,
            "coupon_id": self.coupon.pk, "event_key": None, "slot": PublicSitePhoto.SLOT_CHOICES[0][0], "slug": registry.GROUPS[0].slug,
            "sms_event": SmsTemplate.objects.order_by("event_key").first().event_key, "notif_event": next(iter(notif_events.EVENTS)), "pk": 1,
        }

    def _feature_id(self):
        from apps.subscriptions.models import PricingFeature

        return PricingFeature.objects.first().pk

    def concrete_get_routes(self):
        p = self.params()
        out = []
        for pattern in admin_urls.urlpatterns:
            name = pattern.name
            if not name or name in POST_ONLY or name in ("logout",) or name in FILE_DOWNLOADS or name in ("inbox-sw",) or name.startswith("inbox-") and name != "inbox-home" and name != "inbox-preferences":
                continue
            route = str(pattern.pattern)
            def fill(m):
                key = m.group(2)
                if key == "event_key":
                    return str(p["sms_event"] if route.startswith("sms/") else p["notif_event"])
                return str(p[key])
            out.append((name, "/" + re.sub(r"<(\w+):(\w+)>", fill, route)))
        return out

    def test_every_get_route_renders_for_staff(self):
        self.client.force_login(self.owner)
        routes = self.concrete_get_routes()
        self.assertGreater(len(routes), 35)
        failures = []
        redirects = {"login": 302, "sms-logs": 302, "billing-zibal-settings": 302}   # /login/ bounces staff; /sms/logs/ and /payments/zibal/ are legacy bookmark redirects
        for name, path in routes:
            response = self.client.get(path, HTTP_HOST=ADMIN)
            if response.status_code != redirects.get(name, 200):
                failures.append((name, path, response.status_code))
        self.assertEqual(failures, [])

    def test_every_rendered_page_has_exactly_one_sidebar_one_h1_and_the_shared_assets(self):
        self.client.force_login(self.owner)
        problems = []
        for name, path in self.concrete_get_routes():
            if name in ("login", "sms-logs", "billing-zibal-settings"):
                continue
            html = self.client.get(path, HTTP_HOST=ADMIN).content.decode()
            if "<html" not in html:
                continue
            checks = {
                "sidebar": html.count("data-pa-sidebar") == 1, "aside": html.count("<aside") == 1,
                "nav": html.count('class="pa-nav"') == 1,
                # inbox pages are the notifications app's template shared with the merchant dashboard (own <h2>), rendered inside this shell
                "h1": html.count("<h1") >= 1 or name.startswith("inbox-"),
                "css": "platform-admin-panel.css" in html, "js": "platform-admin-ui.js" in html,
                "active": 'aria-current="page"' in html or name in ("inbox-home", "inbox-preferences", "audit-log", "home"),
                "no-style-tag": "<style" not in html,
            }
            for label, ok in checks.items():
                if not ok:
                    problems.append((name, label))
        self.assertEqual(problems, [])

    def test_anonymous_and_non_staff_users_never_get_an_owner_page(self):
        sample = [path for name, path in self.concrete_get_routes() if name not in ("login",)]
        for path in sample:
            self.assertNotEqual(self.client.get(path, HTTP_HOST=ADMIN).status_code, 200, f"anonymous {path}")
        self.client.force_login(self.ordinary)
        for path in sample:
            self.assertNotEqual(self.client.get(path, HTTP_HOST=ADMIN).status_code, 200, f"non-staff {path}")

    def test_login_page_is_the_only_shell_less_page_and_has_no_sidebar(self):
        html = self.client.get("/login/", HTTP_HOST=ADMIN).content.decode()
        self.assertNotIn("data-pa-sidebar", html)
        self.assertIn("pa-login", html)

    def test_numeric_inputs_keep_native_semantics_on_pricing_forms(self):
        self.client.force_login(self.owner)
        html = self.client.get(f"/plans/{self.plan.pk}/edit/", HTTP_HOST=ADMIN).content.decode()
        numeric = re.findall(r'<input[^>]*type="number"[^>]*>', html)
        self.assertGreater(len(numeric), 8)
        for tag in numeric:
            self.assertIn("min=", tag)          # min/step semantics preserved (spinner hiding is CSS-only)
        self.assertNotIn("type=\"text\" name=\"price_", html)

    def test_destructive_actions_ask_for_confirmation(self):
        self.client.force_login(self.owner)
        html = self.client.get("/plans/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn("data-confirm=", html)
        for path in (f"/plans/{self.plan.pk}/migrate/", "/sms/packages/", "/domains/"):
            self.assertEqual(self.client.get(path, HTTP_HOST=ADMIN).status_code, 200)
        self.assertIn("data-confirm=", self.client.get("/sms/packages/", HTTP_HOST=ADMIN).content.decode())
        self.assertIn("data-confirm=", self.client.get("/domains/", HTTP_HOST=ADMIN).content.decode())

    # ---------------------------------------------------------------- changed workflows still work end-to-end
    def test_plan_form_edits_the_draft_in_place_and_keeps_everything_published_intact(self):
        self.client.force_login(self.owner)
        payload = {"name": "UX plan", "code": "uxplan", "billing_interval": "monthly", "display_price": "100000", "price_monthly": "100000",
                   "trial_days": "3", "marketing_submitted": "1", "promo_label": "پیشنهادِ UX"}
        for _ in range(2):
            self.assertEqual(self.client.post(f"/plans/{self.plan.pk}/edit/", payload, HTTP_HOST=ADMIN).status_code, 302)
        self.assertEqual(self.plan.versions.filter(status="draft").count(), 1)
        self.assertEqual(PlanVersion.objects.get(pk=self.version.pk).trial_days, 0)         # published version untouched
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.promo_label, "پیشنهادِ UX")

    def test_change_plan_uses_a_select_of_published_versions_and_applies_the_change(self):
        _p2, v2 = make_plan("uxplan2", base=200000)
        self.client.force_login(self.owner)
        html = self.client.get(f"/stores/{self.store.public_id}/?tab=subscription", HTTP_HOST=ADMIN).content.decode()
        self.assertIn('<select name="plan_version_id"', html)
        self.assertNotIn('type="number" name="plan_version_id"', html)
        self.assertIn(f'value="{v2.pk}"', html)
        response = self.client.post(f"/stores/{self.store.public_id}/change-plan/", {"plan_version_id": v2.pk, "reason": "ux"}, HTTP_HOST=ADMIN)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StoreSubscription.objects.get(pk=self.sub.pk).plan_version_id, v2.pk)

    def test_pricing_content_is_tabbed_and_saves_return_to_the_same_tab(self):
        self.client.force_login(self.owner)
        for tab in ("rows", "faq", "services", "gap"):
            html = self.client.get(f"/plans/content/?tab={tab}", HTTP_HOST=ADMIN).content.decode()
            self.assertIn(f'href="?tab={tab}"', html)
        response = self.client.post("/plans/content/", {"action": "faq_save", "question": "پرسشِ UX؟", "answer": "پاسخ", "is_published": "on"}, HTTP_HOST=ADMIN)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("?tab=faq"))

    def test_flash_messages_are_rendered_once_by_the_shell(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/plans/{self.plan.pk}/archive/", {}, HTTP_HOST=ADMIN, follow=True)
        html = response.content.decode()
        self.assertEqual(html.count("بایگانی شد"), 1)

    def test_notification_template_page_loads_htmx_for_its_preview_button(self):
        from apps.notifications import events as notif_events

        self.client.force_login(self.owner)
        key = next(iter(notif_events.EVENTS))
        html = self.client.get(f"/notifications/{key}/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn("htmx.min.js", html)
        self.assertIn("hx-post=", html)

    # ---------------------------------------------------------------- PR #40 finance pages (same shell, same components)
    def test_finance_pages_render_inside_the_shared_shell_with_finance_nav_active(self):
        self.client.force_login(self.owner)
        p = self.params()
        for name in FINANCE_PAGES:
            route = next(str(x.pattern) for x in admin_urls.urlpatterns if x.name == name)
            path = "/" + re.sub(r"<(\w+):(\w+)>", lambda m: str(p[m.group(2)]), route)
            html = self.client.get(path, HTTP_HOST=ADMIN).content.decode()
            self.assertEqual(html.count("data-pa-sidebar"), 1, name)
            self.assertIn('aria-current="page"', html, name)
            self.assertIn("مالی و پرداخت", html, name)
            self.assertNotIn(' style="', html, name)

    def test_gateway_credentials_stay_masked_and_never_leak_into_the_page(self):
        self.client.force_login(self.owner)
        html = self.client.get("/payments/gateways/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn('id="default-gateway"', html)
        for m in re.finditer(r'<input[^>]*type="password"[^>]*>', html):
            self.assertNotRegex(m.group(0), r'value="[^"]+"', "secret inputs must never carry a value")
            self.assertIn('autocomplete="new-password"', m.group(0))
        self.assertIn("pa-fieldset", html)

    def test_claim_review_page_keeps_the_conflict_of_interest_and_permission_guards(self):
        self.client.force_login(self.owner)
        html = self.client.get(f"/payments/card-claims/{self.claim.pk}/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn("جزئیاتِ ادعا", html)
        self.assertIn("pa-dl", html)
        self.assertIn('name="bank_reference"', html)           # approve form present for a different reviewer
        self.assertIn("data-confirm=", html)

    def test_finance_filters_use_the_shared_filter_bar(self):
        self.client.force_login(self.owner)
        for path in ("/payments/transactions/", "/payments/card-claims/", "/payments/sms-purchases/"):
            html = self.client.get(path, HTTP_HOST=ADMIN).content.decode()
            self.assertIn("pa-filters", html, path)
            self.assertIn("<label", html, path)
