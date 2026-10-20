"""New public design ("Sardar"): renders every public page, is fully editable from
Platform Admin and can be rolled back to the previous design instantly."""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.portal.models import PlatformAuditLogEntry, PublicSiteSetting
from apps.portal.public_site import registry, services
from apps.subscriptions.models import Plan, PlanVersion

PUBLIC_HOST = "rastisi.localhost"
ADMIN_HOST = "platformadmins.rastisi.localhost"
HOSTS = [PUBLIC_HOST, ADMIN_HOST, "testserver"]
PAGES = [
    "/", "/features/", "/design/", "/plans/", "/about/", "/contact/", "/help/",
    "/supported-industries/", "/terms/", "/privacy/", "/register/", "/login/",
    "/reset-password/", "/does-not-exist/",
]
V2_DIR = Path("apps/portal/templates/portal/public_v2")


@override_settings(ALLOWED_HOSTS=HOSTS)
class DesignSwitchTests(TestCase):
    def _get(self, path="/"):
        return self.client.get(path, HTTP_HOST=PUBLIC_HOST)

    def test_every_public_page_renders_in_the_new_design_by_default(self):
        for path in PAGES:
            with self.subTest(path=path):
                response = self._get(path)
                self.assertIn(response.status_code, (200, 404))
                self.assertContains(response, "public-v2.css", status_code=response.status_code)
                self.assertNotContains(response, "public-site-v2.css", status_code=response.status_code)

    def test_every_public_page_still_renders_in_the_previous_design(self):
        with override_settings(PUBLIC_SITE_FORCE_DESIGN="legacy"):
            for path in PAGES:
                with self.subTest(path=path):
                    response = self._get(path)
                    self.assertIn(response.status_code, (200, 404))
                    self.assertContains(response, "public-site-v2.css", status_code=response.status_code)
                    self.assertNotContains(response, "public-v2.css", status_code=response.status_code)

    def test_database_switch_selects_the_design_and_keeps_edits(self):
        PublicSiteSetting.objects.create(key="home.hero.title", value="تیتر سفارشی من")
        PublicSiteSetting.objects.create(key=registry.SWITCH_KEY, value="legacy")
        self.assertContains(self._get(), "public-site-v2.css")
        PublicSiteSetting.objects.filter(key=registry.SWITCH_KEY).update(value="v2")
        response = self._get()
        self.assertContains(response, "public-v2.css")
        self.assertContains(response, "تیتر سفارشی من")

    def test_environment_force_beats_the_panel_switch(self):
        PublicSiteSetting.objects.create(key=registry.SWITCH_KEY, value="v2")
        with override_settings(PUBLIC_SITE_FORCE_DESIGN="legacy"):
            self.assertContains(self._get(), "public-site-v2.css")
        PublicSiteSetting.objects.filter(key=registry.SWITCH_KEY).update(value="legacy")
        with override_settings(PUBLIC_SITE_FORCE_DESIGN="v2"):
            self.assertContains(self._get(), "public-v2.css")


@override_settings(ALLOWED_HOSTS=HOSTS)
class EditableContentTests(TestCase):
    def _home(self):
        return self.client.get("/", HTTP_HOST=PUBLIC_HOST)

    def test_defaults_come_from_the_registry_and_use_the_real_trial_length(self):
        html = self._home().content.decode()
        self.assertIn("فروشگاه خودتان را بسازید", html)
        self.assertIn("روز رایگان فروشگاه بسازید", html)
        self.assertNotIn("{trial}", html)

    def test_text_override_is_shown_and_html_is_escaped(self):
        PublicSiteSetting.objects.create(key="home.hero.title", value="<script>alert(1)</script> تیتر")
        html = self._home().content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; تیتر", html)

    def test_dash_hides_a_text_and_hide_switch_hides_a_list_item(self):
        PublicSiteSetting.objects.create(key="home.hero.fact3", value="-")
        PublicSiteSetting.objects.create(key="faq.1.hide", value="1")
        html = self._home().content.decode()
        self.assertNotIn("پشتیبانی تلفنی", html)
        self.assertNotIn("راستی‌سی دقیقاً چه کاری انجام می‌دهد؟", html)

    def test_colour_and_font_overrides_become_theme_css(self):
        PublicSiteSetting.objects.create(key="color.light.sign", value="#7a1f3d")
        PublicSiteSetting.objects.create(key="color.dark.paper", value="#101010")
        PublicSiteSetting.objects.create(key="font.display", value="tahoma")
        html = self._home().content.decode()
        self.assertIn('<style id="ps-theme">', html)
        self.assertIn("--sign:#7a1f3d", html)
        self.assertIn("--paper:#101010", html)
        self.assertIn("--display:Tahoma", html)

    def test_untrusted_values_never_reach_the_stylesheet(self):
        PublicSiteSetting.objects.create(key="color.light.sign", value="red;}</style><script>x()</script>")
        PublicSiteSetting.objects.create(key="font.custom_text", value="a';}</style><script>")
        PublicSiteSetting.objects.create(key="font.stylesheet", value="http://insecure.example/x.css")
        html = self._home().content.decode()
        self.assertNotIn("<script>x()", html)
        self.assertNotIn("</style><script>", html)
        self.assertNotIn("insecure.example", html)
        self.assertNotIn("ps-theme", html)

    def test_a_hand_edited_javascript_link_is_never_rendered(self):
        PublicSiteSetting.objects.create(key="footer.instagram", value="javascript:alert(1)")
        PublicSiteSetting.objects.create(key="footer.telegram", value="https://t.me/rastisi")
        html = self._home().content.decode()
        self.assertNotIn("javascript:alert", html)
        self.assertIn('href="https://t.me/rastisi"', html)

    def test_https_font_stylesheet_is_linked(self):
        PublicSiteSetting.objects.create(key="font.stylesheet", value="https://fonts.example/css?family=Estedad")
        PublicSiteSetting.objects.create(key="font.custom_text", value="Estedad")
        html = self._home().content.decode()
        self.assertIn('href="https://fonts.example/css?family=Estedad"', html)
        self.assertIn("--text:'Estedad',", html)

    def test_contact_details_come_from_platform_configuration_and_nothing_is_invented(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        cache.clear()
        response = self.client.get("/contact/", HTTP_HOST=PUBLIC_HOST)
        self.assertNotContains(response, "021 0000 0000")
        self.assertContains(response, "برای تماس با ما از فرم کنار صفحه پیام بفرستید.")
        config = get_platform_configuration()
        config.support_contact_phone = "02112345678"
        config.support_contact_email = "help@example.com"
        config.save()
        cache.clear()
        response = self.client.get("/contact/", HTTP_HOST=PUBLIC_HOST)
        self.assertContains(response, "02112345678")
        self.assertContains(response, "help@example.com")

    def test_plan_cards_are_built_from_real_published_plans(self):
        plan = Plan.objects.create(
            code="gold", name="gold", public_title="طلایی",
            description="برای فروشگاه‌های پرفروش", is_recommended=True,
        )
        PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=490000, billing_interval=PlanVersion.BillingInterval.MONTHLY, trial_days=14,
        )
        for path in ("/plans/", "/"):
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST=PUBLIC_HOST)
                self.assertContains(response, "طلایی")
                self.assertContains(response, "۴۹۰٬۰۰۰")
                self.assertContains(response, "۱۴ روز دوره آزمایشی")
                self.assertContains(response, "پیشنهاد ما")

    def test_faq_page_groups_rows_and_exposes_faq_jsonld(self):
        response = self.client.get("/help/", HTTP_HOST=PUBLIC_HOST)
        self.assertContains(response, 'id="faqQ"')
        self.assertContains(response, "شروع کار")
        self.assertContains(response, '"@type": "FAQPage"')

    def test_register_prefills_the_phone_from_the_closing_form(self):
        response = self.client.get("/register/?phone=09121234567", HTTP_HOST=PUBLIC_HOST)
        self.assertContains(response, 'value="09121234567"')


class RegistryContractTests(SimpleTestCase):
    def _templates(self):
        return {p.name: p.read_text(encoding="utf-8") for p in V2_DIR.glob("*.html")}

    def test_every_key_used_in_the_new_templates_exists_in_the_registry(self):
        used, lists = set(), set()
        for text in self._templates().values():
            used.update(re.findall(r"\{%\s*ps(?:_on)?\s+'([^']+)'", text))
            lists.update(re.findall(r"\{%\s*ps_items\s+'([^']+)'", text))
        self.assertTrue(used)
        self.assertEqual(sorted(k for k in used if k not in registry.FIELDS), [])
        self.assertEqual(sorted(k for k in lists if k not in registry.LISTS), [])

    def test_new_templates_define_no_local_styles_or_colours(self):
        offenders = [
            name for name, content in self._templates().items()
            if re.search(r"<style\b", content, re.I) or re.search(r"\sstyle\s*=", content, re.I)
            or re.search(r"#[0-9a-fA-F]{3,8}\b", content)
        ]
        self.assertEqual(offenders, [])

    def test_colour_defaults_are_valid_hex(self):
        for name, _label, light, dark in registry.COLOR_TOKENS:
            self.assertTrue(services.is_valid_color(light), name)
            self.assertTrue(services.is_valid_color(dark), name)

    def test_colour_defaults_match_the_stylesheet(self):
        css = Path("apps/portal/static/portal/css/public-v2.css").read_text(encoding="utf-8")
        light_block = re.search(r":root\{(.*?)\}", css, re.S).group(1)
        dark_block = re.search(r'\[data-theme="dark"\]\{(.*?)\}', css, re.S).group(1)
        for name, _label, light, dark in registry.COLOR_TOKENS:
            self.assertIn(f"--{name}:{light}", light_block, name)
            if dark != light:
                self.assertIn(f"--{name}:{dark}", dark_block, name)

    def test_validate_rules(self):
        field = registry.FIELDS["color.light.sign"]
        self.assertEqual(services.validate(field, "#ABCDEF"), ("#abcdef", None))
        self.assertIsNone(services.validate(field, "#0c4a3c")[0])          # equals default -> no override
        self.assertIsNotNone(services.validate(field, "blue")[1])
        text = registry.FIELDS["home.hero.title"]
        self.assertIsNone(services.validate(text, "  ")[0])                  # empty -> default
        self.assertEqual(services.validate(text, "-")[0], "-")
        size = registry.FIELDS["font.base_size"]
        self.assertIsNotNone(services.validate(size, "40")[1])
        self.assertEqual(services.validate(size, "18")[0], "18")
        sheet = registry.FIELDS["font.stylesheet"]
        self.assertIsNotNone(services.validate(sheet, "http://x.example/a.css")[1])
        self.assertIsNone(services.validate(sheet, "https://x.example/a.css")[1])
        flag = registry.FIELDS["faq.1.hide"]
        self.assertEqual(services.validate(flag, "1")[0], "1")
        self.assertIsNone(services.validate(flag, "")[0])                   # unchecked == default


@override_settings(ALLOWED_HOSTS=HOSTS)
class PlatformAdminEditorTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            "site-owner", password="secure-pass-2026", is_staff=True, is_superuser=True,
        )
        self.staff = user_model.objects.create_user("site-staff", password="secure-pass-2026", is_staff=True)
        self.client.force_login(self.owner)

    def _post(self, path, data):
        return self.client.post(path, data, HTTP_HOST=ADMIN_HOST)

    def _form_for(self, slug):
        """Posted data equal to the page's current values (what an untouched browser form submits)."""
        response = self.client.get(f"/public-site/{slug}/", HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 200)
        group = next(g for g in registry.GROUPS if g.slug == slug)
        data = {}
        for section in group.sections:
            for f in section.fields:
                if f.kind == registry.KIND_BOOL:
                    if f.default == "1":
                        data[f.key] = "1"
                else:
                    data[f.key] = f.default
        return data

    def test_only_superusers_can_use_the_editor(self):
        self.client.logout()
        self.client.force_login(self.staff)
        for method, path in (
            ("get", "/public-site/"), ("get", "/public-site/home/"), ("post", "/public-site/home/"),
            ("post", "/public-site/switch/"), ("post", "/public-site/home/reset/"),
        ):
            with self.subTest(path=path, method=method):
                response = getattr(self.client, method)(path, HTTP_HOST=ADMIN_HOST)
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"])
        self.assertFalse(PublicSiteSetting.objects.exists())

    def test_public_host_does_not_expose_the_editor(self):
        self.assertEqual(self.client.get("/public-site/", HTTP_HOST=PUBLIC_HOST).status_code, 404)

    def test_index_and_every_group_page_render(self):
        self.assertEqual(self.client.get("/public-site/", HTTP_HOST=ADMIN_HOST).status_code, 200)
        for group in registry.GROUPS:
            with self.subTest(group=group.slug):
                response = self.client.get(f"/public-site/{group.slug}/", HTTP_HOST=ADMIN_HOST)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, group.title)
        self.assertEqual(self.client.get("/public-site/nope/", HTTP_HOST=ADMIN_HOST).status_code, 404)

    def test_saving_unchanged_forms_stores_nothing(self):
        for slug in ("home", "design", "faq", "layout", "features", "templates"):
            with self.subTest(group=slug):
                response = self._post(f"/public-site/{slug}/", self._form_for(slug))
                self.assertEqual(response.status_code, 302)
        self.assertFalse(PublicSiteSetting.objects.exists())

    def test_saving_a_change_stores_only_the_difference_and_is_audited(self):
        data = self._form_for("home")
        data["home.hero.title"] = "تیتر تازه"
        response = self._post("/public-site/home/", data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            dict(PublicSiteSetting.objects.values_list("key", "value")), {"home.hero.title": "تیتر تازه"},
        )
        self.assertEqual(PublicSiteSetting.objects.get(key="home.hero.title").updated_by, self.owner)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_admin.public_site_saved").exists())
        self.assertContains(self.client.get("/", HTTP_HOST=PUBLIC_HOST), "تیتر تازه")

    def test_clearing_a_field_or_ticking_reset_goes_back_to_default(self):
        PublicSiteSetting.objects.create(key="home.hero.title", value="x")
        PublicSiteSetting.objects.create(key="home.hero.lead", value="y")
        data = self._form_for("home")
        data["home.hero.title"] = ""
        data["__reset__home.hero.lead"] = "1"
        self._post("/public-site/home/", data)
        self.assertFalse(PublicSiteSetting.objects.exists())

    def test_an_invalid_value_saves_nothing(self):
        data = self._form_for("design")
        data["color.light.sign"] = "javascript:alert(1)"
        data["font.display"] = "tahoma"
        response = self._post("/public-site/design/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کد رنگ باید")
        self.assertFalse(PublicSiteSetting.objects.exists())

    def test_a_colour_and_font_edit_reaches_the_public_site(self):
        data = self._form_for("design")
        data["color.light.leaf"] = "#aa3311"
        data["font.text"] = "tahoma"
        self.assertEqual(self._post("/public-site/design/", data).status_code, 302)
        html = self.client.get("/", HTTP_HOST=PUBLIC_HOST).content.decode()
        self.assertIn("--leaf:#aa3311", html)
        self.assertIn("--text:Tahoma", html)

    def test_group_reset_removes_only_that_groups_overrides(self):
        PublicSiteSetting.objects.create(key="home.hero.title", value="x")
        PublicSiteSetting.objects.create(key="about.title", value="y")
        self._post("/public-site/home/reset/", {})
        self.assertEqual(list(PublicSiteSetting.objects.values_list("key", flat=True)), ["about.title"])

    def test_switch_back_to_the_previous_design_and_forward_again(self):
        self.assertContains(self.client.get("/", HTTP_HOST=PUBLIC_HOST), "public-v2.css")
        self.assertEqual(self._post("/public-site/switch/", {"design": "legacy"}).status_code, 302)
        self.assertContains(self.client.get("/", HTTP_HOST=PUBLIC_HOST), "public-site-v2.css")
        self._post("/public-site/switch/", {"design": "v2"})
        self.assertContains(self.client.get("/", HTTP_HOST=PUBLIC_HOST), "public-v2.css")
        self.assertEqual(
            PlatformAuditLogEntry.objects.filter(action_code="platform_admin.public_site_design_switched").count(), 2,
        )
        self.assertEqual(self._post("/public-site/switch/", {"design": "evil"}).status_code, 404)
