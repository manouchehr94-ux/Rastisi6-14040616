"""چکپوینتِ نسخه‌بندیِ ظاهر — تنها الزامِ غیرقابلِ‌مذاکره: تغییراتِ ظاهر
باید دقیقاً همان چرخه‌ی Draft/Preview/Publish سکشن‌ها/هدر/فوتر را طی
کنند، نه یک مسیرِ زنده‌ی جدا."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.storefront_builder import appearance_registry
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ValidateAppearanceConfigTests(TestCase):
    def test_non_dict_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config("not a dict")

    def test_defaults_when_empty(self):
        cleaned = svc.validate_appearance_config({})
        self.assertEqual(cleaned["template_slug"], "modern")
        self.assertIsNone(cleaned["palette_slug"])
        self.assertEqual(cleaned["color_overrides"], {})
        self.assertEqual(cleaned["type_scale"], "normal")

    def test_unknown_template_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"template_slug": "not-a-real-template"})

    def test_unknown_palette_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"palette_slug": "not-a-real-palette"})

    def test_invalid_hex_color_override_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"color_overrides": {"primary": "not-a-color"}})

    def test_valid_color_override_accepted(self):
        cleaned = svc.validate_appearance_config({"color_overrides": {"text": "#111111"}})
        self.assertEqual(cleaned["color_overrides"], {"text": "#111111"})

    def test_unknown_color_key_silently_dropped(self):
        cleaned = svc.validate_appearance_config({"color_overrides": {"not_a_real_token": "#111111"}})
        self.assertEqual(cleaned["color_overrides"], {})

    def test_unknown_font_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"font": "ComicSans"})

    def test_radius_clamped(self):
        cleaned = svc.validate_appearance_config({"radius": 999})
        self.assertEqual(cleaned["radius"], 32)
        cleaned = svc.validate_appearance_config({"radius": -5})
        self.assertEqual(cleaned["radius"], 0)

    def test_invalid_density_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"density": "super-compact"})

    def test_invalid_motion_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"motion": "extreme"})

    def test_invalid_type_scale_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"type_scale": "huge"})

    def test_valid_type_scale_accepted(self):
        cleaned = svc.validate_appearance_config({"type_scale": "large"})
        self.assertEqual(cleaned["type_scale"], "large")

    def test_invalid_button_style_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"button_style": "glowing"})

    def test_valid_button_style_accepted(self):
        cleaned = svc.validate_appearance_config({"button_style": "outline"})
        self.assertEqual(cleaned["button_style"], "outline")

    def test_invalid_image_fit_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"image_fit": "stretch"})

    def test_valid_image_fit_accepted(self):
        cleaned = svc.validate_appearance_config({"image_fit": "contain"})
        self.assertEqual(cleaned["image_fit"], "contain")

    def test_invalid_image_hover_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"image_hover": "spin"})

    def test_valid_image_hover_accepted(self):
        cleaned = svc.validate_appearance_config({"image_hover": "none"})
        self.assertEqual(cleaned["image_hover"], "none")

    def test_image_and_button_defaults_preserve_pre_existing_behavior(self):
        """رگرسیون: پیش‌فرض‌ها باید دقیقاً همان رفتارِ سخت‌کدشده‌یِ قبل
        از این چکپوینت باشند (object-fit:cover، زوم روی هاور، دکمه‌ی پر‌رنگ)
        — یعنی هیچ فروشگاهی که هرگز این فیلدها را لمس نکرده تغییری نبیند."""
        cleaned = svc.validate_appearance_config({})
        self.assertEqual(cleaned["image_fit"], "cover")
        self.assertEqual(cleaned["image_hover"], "zoom")
        self.assertEqual(cleaned["button_style"], "filled")

    def test_card_image_crossfade_and_zoom_are_actually_persisted(self):
        """Phase 8 P0-7 — رگرسیونِ یک باگِ واقعی: قبل از این فیکس، این دو
        کلید هیچ‌وقت از ``config`` ورودی خوانده نمی‌شدند — خروجی همیشه
        فقط پیش‌فرضِ ثابت (False/True) بود، حتی اگر مرچنت صریحاً چک‌باکسِ
        مربوطه را در فرم عوض می‌کرد."""
        cleaned = svc.validate_appearance_config({"card_image_crossfade": True, "card_image_zoom": False})
        self.assertTrue(cleaned["card_image_crossfade"])
        self.assertFalse(cleaned["card_image_zoom"])

    def test_card_image_crossfade_and_zoom_default_unchanged(self):
        cleaned = svc.validate_appearance_config({})
        self.assertFalse(cleaned["card_image_crossfade"])
        self.assertTrue(cleaned["card_image_zoom"])


class SiteStructuralFieldsTests(TestCase):
    """Phase 8 P0-7 — ۵ فیلدِ ساختاریِ سراسری که قبلاً فقط از طریقِ
    انتخابِ یک Templateِ کامل قابلِ‌تغییر بودند، اکنون مستقیماً در
    ``appearance_config`` قابلِ‌override‌اند."""

    def test_absent_by_default(self):
        """این ۵ کلید عمداً در APPEARANCE_CONFIG_DEFAULTS نیستند —
        غیابشان یعنی «فروشگاه هنوز این پنل را لمس نکرده»، تا
        ``context_processors`` بتواند به‌درستی به Templateِ ذخیره‌شده
        بازگردد (نگاه کنید به تست‌هایِ context_processors)."""
        cleaned = svc.validate_appearance_config({})
        for key in ("content_width", "grid_density", "card_shadow", "card_hover", "hero_style"):
            self.assertNotIn(key, cleaned, key)

    def test_valid_content_widths_accepted(self):
        for width in appearance_registry.SITE_CONTENT_WIDTH_CHOICES:
            cleaned = svc.validate_appearance_config({"content_width": width})
            self.assertEqual(cleaned["content_width"], width)

    def test_invalid_content_width_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"content_width": 9999})

    def test_valid_grid_densities_accepted(self):
        for n in appearance_registry.SITE_GRID_DENSITY_CHOICES:
            cleaned = svc.validate_appearance_config({"grid_density": n})
            self.assertEqual(cleaned["grid_density"], n)

    def test_invalid_grid_density_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"grid_density": 99})

    def test_valid_card_shadow_accepted(self):
        cleaned = svc.validate_appearance_config({"card_shadow": "strong"})
        self.assertEqual(cleaned["card_shadow"], "strong")

    def test_invalid_card_shadow_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"card_shadow": "glowing"})

    def test_valid_card_hover_accepted(self):
        cleaned = svc.validate_appearance_config({"card_hover": "zoom"})
        self.assertEqual(cleaned["card_hover"], "zoom")

    def test_invalid_card_hover_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"card_hover": "spin"})

    def test_valid_hero_style_accepted(self):
        cleaned = svc.validate_appearance_config({"hero_style": "split"})
        self.assertEqual(cleaned["hero_style"], "split")

    def test_invalid_hero_style_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_appearance_config({"hero_style": "not-a-style"})


class TypographyScaleTests(TestCase):
    """چکپوینتِ ۸: مقیاسِ تایپوگرافی — پنج نقشِ معنادار (نه اندازه‌یِ
    دلخواه در هر جای CSS)."""

    def test_normal_scale_matches_pre_existing_hardcoded_sizes(self):
        """رگرسیون: مقیاسِ پیش‌فرض نباید هیچ فروشگاهی را تغییر دهد —
        دقیقاً همان مقادیرِ سخت‌کدشده‌یِ قبل از این چکپوینت."""
        sizes = appearance_registry.resolve_typography("normal")
        self.assertEqual(sizes, {"heading": 19, "body": 14, "product_name": 13, "price": 15, "muted": 11})

    def test_all_scale_choices_define_all_five_roles(self):
        for scale in appearance_registry.TYPE_SCALE_CHOICES:
            sizes = appearance_registry.resolve_typography(scale)
            self.assertEqual(set(sizes), {"heading", "body", "product_name", "price", "muted"})

    def test_unknown_scale_falls_back_to_normal(self):
        self.assertEqual(
            appearance_registry.resolve_typography("not-a-real-scale"),
            appearance_registry.resolve_typography("normal"),
        )

    def test_scales_are_genuinely_ordered(self):
        compact = appearance_registry.resolve_typography("compact")
        normal = appearance_registry.resolve_typography("normal")
        large = appearance_registry.resolve_typography("large")
        for role in ("heading", "body", "product_name", "price", "muted"):
            self.assertLess(compact[role], normal[role])
            self.assertLess(normal[role], large[role])


class ResolveColorsTests(TestCase):
    def test_no_palette_uses_default_colors(self):
        colors = appearance_registry.resolve_colors({"palette_slug": None, "color_overrides": {}})
        self.assertEqual(colors, appearance_registry.DEFAULT_COLORS)

    def test_overrides_apply_on_top_of_default(self):
        colors = appearance_registry.resolve_colors({"palette_slug": None, "color_overrides": {"text": "#000000"}})
        self.assertEqual(colors["text"], "#000000")
        self.assertEqual(colors["primary"], appearance_registry.DEFAULT_COLORS["primary"])


class EffectiveAppearanceConfigTests(TestCase):
    def test_fresh_version_has_full_defaults(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.appearance_config = {}
        config = draft.effective_appearance_config()
        self.assertEqual(config["template_slug"], "modern")
        self.assertEqual(config["font"], "Vazirmatn")

    def test_clone_carries_appearance_forward(self):
        """پابلیش → یک Draft جدید (کلون از published) باید همان
        appearance_config را داشته باشد، نه پیش‌فرضِ خالی."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"text": "#123456"}})
        draft.save(update_fields=["appearance_config"])
        svc.publish(store)

        new_draft = svc.get_or_create_draft(store)
        self.assertEqual(new_draft.appearance_config.get("color_overrides", {}).get("text"), "#123456")


HOST = "sfb-appearance-test.rastisi.localhost"


class AppearanceEditorViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="appearance_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="appearance_owner", password="pass12345")

    def test_get_renders_hub(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ظاهر سایت")

    def test_post_saves_color_override_to_draft_not_live_shopsettings(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        shop_before = ShopSettings.load(store=self.store)
        original_primary = shop_before.primary_color

        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "modern", "font": "Vazirmatn", "radius": "18", "button_radius": "12",
            "density": "normal", "motion": "subtle", "color_text": "#0A0A0A",
        })
        self.assertEqual(resp.status_code, 302)

        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"]["text"], "#0A0A0A")

        # ShopSettings زنده دست‌نخورده مانده — این تغییر فقط در Draft است
        shop_after = ShopSettings.load(store=self.store)
        self.assertEqual(shop_after.primary_color, original_primary)

    def test_hub_no_longer_has_standalone_template_card(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """Phase 8 P0-7 — کارتِ مستقلِ «قالب فروشگاه» و گالریِ آن از هابِ
        ظاهر حذف شده‌اند؛ پیش‌تنظیم/پالت/تنظیماتِ بیشتر جایگزینش شده‌اند."""
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        body = resp.content.decode()
        self.assertNotIn("قالب فروشگاه", body)
        self.assertNotIn("اعمال قالب", body)
        self.assertIn("پیش‌تنظیمِ صفحه‌آرایی", body)

    def test_advanced_panel_has_new_structural_controls(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.get(reverse("dashboard:storefront-builder-appearance"))
        body = resp.content.decode()
        self.assertIn("عرض محتوای سایت", body)
        self.assertIn("تعداد ستون گرید محصول", body)
        self.assertIn("سایه‌ی کارت محصول", body)
        self.assertIn("هاور کارت محصول", body)
        self.assertIn("سبک هیرو", body)

    def test_post_saves_type_scale_to_draft(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "modern", "font": "Vazirmatn", "radius": "18", "button_radius": "12",
            "density": "normal", "motion": "subtle", "type_scale": "large",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["type_scale"], "large")

    def test_invalid_color_shows_error_without_saving(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft_before = svc.get_or_create_draft(self.store)
        original = dict(draft_before.appearance_config or {})
        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "not-a-real-template",
        })
        self.assertEqual(resp.status_code, 302)
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.appearance_config, original)


@override_settings(ALLOWED_HOSTS=["sfb-appearance-public.example.com", "testserver", HOST])
class AppearanceDraftPublishIsolationTests(TestCase):
    """قلبِ چکپوینت: تغییرِ رنگ در Draft نباید تا Publish روی فروشگاهِ
    عمومی دیده شود — دقیقاً همان الزامِ غیرقابلِ‌مذاکره‌یِ بخشِ ۱۵ کار."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-appearance-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="isolation_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=HOST)
        self.admin_client.login(username="isolation_owner", password="pass12345")

    def test_draft_color_change_invisible_on_public_page_until_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])

        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertNotContains(public_resp, "#00FF00")

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(preview_resp, "#00FF00")

    def test_published_appearance_reaches_public_page(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(public_resp, "#00FF00")

    def test_draft_type_scale_change_invisible_on_public_page_until_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"type_scale": "large"})
        draft.save(update_fields=["appearance_config"])

        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertNotContains(public_resp, "--sfb-heading-size:22px")

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(preview_resp, "--sfb-heading-size:22px")

        svc.publish(self.store)
        public_resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(public_resp, "--sfb-heading-size:22px")

    def test_other_pages_use_live_shopsettings_when_nothing_published_yet(self):
        """صفحاتِ غیرِ Builder-aware (مثلاً product-list) قبل از اولین
        انتشار دقیقاً مثلِ قبل رفتار می‌کنند — رنگِ زنده‌یِ ShopSettings،
        نه Draft (که هرگز نباید بیرون از Preview دیده شود). بعد از
        publish شدن، این صفحات هویتِ *سراسری* را از همان نسخه‌ی منتشرشده
        می‌خوانند — نگاه کنید به
        ``test_published_global_identity_reaches_non_builder_aware_pages``
        برایِ آن سناریو."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#00FF00"}})
        draft.save(update_fields=["appearance_config"])

        shop = ShopSettings.load(store=self.store)
        live_primary = shop.primary_color
        self.assertNotEqual(live_primary, "#00FF00")

        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(resp, live_primary.upper())
        self.assertNotContains(resp, "#00FF00")

    def test_published_global_identity_reaches_non_builder_aware_pages(self):
        """بخشِ ۲۲ بازبینیِ نهایی: هویتِ *سراسری* (رنگ، فونت، گردی، سبکِ
        دکمه، حرکت، اندازه‌متن، رفتارِ تصویر) بعد از publish باید در
        صفحاتِ غیرِ Builder-aware هم دیده شود — نه فقط صفحه‌ی اصلی —
        وگرنه مشتری در جزئیاتِ کالا برندِ متفاوتی با صفحه‌ی اصلی می‌بیند."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "color_overrides": {"primary": "#00FF00"}, "font": "Georgia", "button_style": "outline",
        })
        draft.save(update_fields=["appearance_config"])

        # قبل از publish — هنوز رنگِ زنده (این Draft هرگز نباید بیرون درز کند)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertNotContains(resp, "#00FF00")

        svc.publish(self.store)

        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(resp, "#00FF00")
        self.assertContains(resp, "data-sfb-button-style=\"outline\"")
        self.assertContains(resp, "--sfb-font:'Georgia'")

    def test_unpublished_store_never_leaks_draft_to_other_pages_even_with_history(self):
        """اگر Draftِ فعلی تغییر کند اما دوباره publish نشود، صفحاتِ
        غیرِ Builder-aware باید همچنان همان نسخه‌ی *قبلاً منتشرشده* را
        ببینند — نه Draftِ جدیدِ ذخیره‌نشده."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)  # published v1، رنگِ پیش‌فرض

        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#123456"}})
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)  # published v2 — #123456

        # یک Draftِ *جدیدِ* دیگر (منتشرنشده) با رنگِ متفاوت
        draft2 = svc.get_or_create_draft(self.store)
        draft2.appearance_config = svc.validate_appearance_config({"color_overrides": {"primary": "#ABCDEF"}})
        draft2.save(update_fields=["appearance_config"])

        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST="sfb-appearance-public.example.com")
        self.assertContains(resp, "#123456")
        self.assertNotContains(resp, "#ABCDEF")


class PaletteRegistryTests(TestCase):
    def test_at_least_twenty_palettes_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_palettes()), 20)

    def test_every_palette_has_all_eight_color_keys(self):
        from apps.storefront_builder.models import APPEARANCE_COLOR_KEYS

        for palette in appearance_registry.list_palettes():
            self.assertEqual(set(palette.colors.keys()), set(APPEARANCE_COLOR_KEYS), palette.slug)

    def test_palette_slugs_are_unique(self):
        slugs = [p.slug for p in appearance_registry.list_palettes()]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_at_least_one_template_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_templates()), 1)
        self.assertIsNotNone(appearance_registry.get_template("modern"))


class PaletteOverrideWorkflowTests(TestCase):
    """سناریوی دقیقاً همان مثالِ کارِ کاربر: انتخابِ پالت → override فقط
    یک رنگ → بازگردانیِ همان یک رنگ → بازگردانیِ کلِ پالت."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="palette_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="palette_owner", password="pass12345")

    def _base_fields(self, draft):
        config = draft.effective_appearance_config()
        return {
            "template_slug": config["template_slug"], "font": config["font"],
            "radius": config["radius"], "button_radius": config["button_radius"],
            "density": config["density"], "motion": config["motion"],
        }

    def test_selecting_palette_sets_all_coordinated_colors(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["palette_slug"], "ocean")
        colors = appearance_registry.resolve_colors(draft.appearance_config)
        self.assertEqual(colors, appearance_registry.get_palette("ocean").colors)

    def test_overriding_only_text_preserves_rest_of_palette(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000",
        })
        draft = svc.get_or_create_draft(self.store)
        colors = appearance_registry.resolve_colors(draft.appearance_config)
        base = appearance_registry.get_palette("ocean").colors
        self.assertEqual(colors["text"], "#000000")
        for key in ("primary", "secondary", "accent", "background", "surface", "muted", "border"):
            self.assertEqual(colors[key], base[key], key)

    def test_reset_one_color_restores_only_that_key(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000", "color_primary": "#00FF00",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
            "color_text": "#000000", "color_primary": "#00FF00", "reset_color": "text",
        })
        draft = svc.get_or_create_draft(self.store)
        overrides = draft.appearance_config["color_overrides"]
        self.assertNotIn("text", overrides)
        self.assertEqual(overrides["primary"], "#00FF00")

    def test_reset_all_overrides_clears_everything_but_keeps_palette(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000", "color_primary": "#00FF00",
        })
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean",
            "color_text": "#000000", "color_primary": "#00FF00", "reset_all_overrides": "1",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"], {})
        self.assertEqual(draft.appearance_config["palette_slug"], "ocean")

    def test_switching_palette_clears_previous_overrides(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "ocean", "color_text": "#000000",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["color_overrides"], {"text": "#000000"})

        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            **self._base_fields(draft), "palette_slug": "forest",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["palette_slug"], "forest")
        self.assertEqual(draft.appearance_config["color_overrides"], {})


class TemplateRegistryTests(TestCase):
    def test_at_least_ten_templates_registered(self):
        self.assertGreaterEqual(len(appearance_registry.list_templates()), 10)

    def test_templates_are_structurally_distinct_not_just_color(self):
        """الزامِ صریحِ کار: «Template صرفاً رنگ نیست» — این تست تأیید
        می‌کند حداقل چند فیلدِ ساختاریِ واقعی (نه رنگ) بینِ قالب‌ها واقعاً
        فرق دارد، نه این‌که همه یک مقدارِ یکسان را کپی کرده باشند."""
        templates = appearance_registry.list_templates()
        content_widths = {t.content_width for t in templates}
        grid_densities = {t.grid_density for t in templates}
        radii = {t.radius for t in templates}
        hero_styles = {t.hero_style for t in templates}
        card_shadows = {t.card_shadow for t in templates}
        self.assertGreater(len(content_widths), 1)
        self.assertGreater(len(grid_densities), 1)
        self.assertGreater(len(radii), 1)
        self.assertGreater(len(hero_styles), 1)
        self.assertGreater(len(card_shadows), 1)

    def test_modern_template_matches_pre_template_system_defaults(self):
        """قالبِ پیش‌فرض نباید هیچ فروشگاهی را که هنوز به این سیستم دست
        نزده تغییر دهد."""
        modern = appearance_registry.get_template("modern")
        self.assertEqual(modern.radius, 18)
        self.assertEqual(modern.button_radius, 12)
        self.assertEqual(modern.content_width, 1200)


class TemplateSwitchViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="template_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="template_owner", password="pass12345")

    def test_switching_template_with_no_palette_selected_does_not_crash(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """رگرسیونِ باگِ واقعی: حلقه‌ی فرمِ گالریِ قالب یک‌بار مقدارِ
        Noneِ پایتون را به‌صورتِ رشته‌ی literal «None» در فیلدِ مخفیِ
        palette_slug رندر می‌کرد — این تست دقیقاً همان سناریو (فروشگاهی
        که هنوز هیچ Paletteی انتخاب نکرده) را شبیه‌سازی می‌کند."""
        draft = svc.get_or_create_draft(self.store)
        self.assertIsNone(draft.effective_appearance_config()["palette_slug"])

        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "boutique", "font": "Tahoma", "radius": "24",
            "button_radius": "22", "density": "relaxed", "motion": "subtle",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["template_slug"], "boutique")
        self.assertIsNone(draft.appearance_config.get("palette_slug"))

    def test_switching_template_applies_its_own_presentation_defaults(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """رگرسیون: کلیک روی کارتِ یک Templateِ دیگر در گالری باید
        پیش‌فرض‌هایِ *همان* Template (فونت/گردی/تراکم/حرکت/مقیاسِ متن)
        را اعمال کند — حتی اگر مقادیرِ فرم (مثلاً فیلدهایِ مخفیِ گالری)
        هنوز مقدارِ Templateِ *قبلی* را حمل کنند؛ در غیرِ این صورت تعویضِ
        Template هیچ حسِ محسوسی در این فیلدها نداشت."""
        boutique = appearance_registry.get_template("boutique")
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.effective_appearance_config()["template_slug"], "modern")

        resp = self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            # عمداً مقادیرِ Templateِ *قبلی* (modern) فرستاده می‌شود —
            # دقیقاً شبیه‌سازیِ فیلدِ مخفیِ گالری که هنوز عوض نشده.
            "template_slug": "boutique", "font": "Vazirmatn", "radius": "18",
            "button_radius": "12", "density": "normal", "motion": "subtle", "type_scale": "normal",
        })
        self.assertEqual(resp.status_code, 302)

        config = svc.get_or_create_draft(self.store).appearance_config
        self.assertEqual(config["template_slug"], "boutique")
        self.assertEqual(config["font"], boutique.font)
        self.assertEqual(config["radius"], boutique.radius)
        self.assertEqual(config["button_radius"], boutique.button_radius)
        self.assertEqual(config["density"], boutique.density)
        self.assertEqual(config["motion"], boutique.motion)
        self.assertEqual(config["type_scale"], boutique.type_scale)

    def test_resubmitting_same_template_does_not_override_manual_customization(self):
        """اگر مرچنت بعد از انتخابِ Template دستی radius را عوض کرده،
        submitِ دوباره‌یِ همان فرم (بدونِ تغییرِ template_slug) نباید آن
        شخصی‌سازی را با پیش‌فرضِ Template بازنویسی کند."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"template_slug": "modern", "radius": 5})
        draft.save(update_fields=["appearance_config"])

        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "modern", "font": "Vazirmatn", "radius": "5",
            "button_radius": "12", "density": "normal", "motion": "subtle", "type_scale": "normal",
        })
        config = svc.get_or_create_draft(self.store).appearance_config
        self.assertEqual(config["radius"], 5)

    def test_switching_template_preserves_color_overrides(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"color_overrides": {"text": "#123123"}})
        draft.save(update_fields=["appearance_config"])

        self.client.post(reverse("dashboard:storefront-builder-appearance"), {
            "template_slug": "tech", "font": "Tahoma", "radius": "14",
            "button_radius": "10", "density": "normal", "motion": "dynamic",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config["template_slug"], "tech")
        self.assertEqual(draft.appearance_config["color_overrides"], {"text": "#123123"})


class NonDestructiveTemplatePreviewTests(TestCase):
    """چکپوینتِ «پیش‌نمایشِ غیرمخربِ قالب» (بخشِ ۱۰ بازبینیِ نهایی):
    ``?preview_template=<slug>`` باید ظاهرِ Templateِ کاندید را در
    iframeِ پیش‌نمایش نشان دهد بدونِ این‌که چیزی روی Draft ذخیره شود."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="preview_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="preview_owner", password="pass12345")

    def test_preview_template_param_shows_candidate_without_saving(self):
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.effective_appearance_config()["template_slug"], "modern")

        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"preview_template": "boutique"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-sfb-template=\"boutique\"")

        # Draft در دیتابیس دست‌نخورده مانده
        draft_after = svc.get_or_create_draft(self.store)
        self.assertEqual(draft_after.effective_appearance_config()["template_slug"], "modern")

    def test_preview_without_param_shows_real_draft(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"template_slug": "tech"})
        draft.save(update_fields=["appearance_config"])

        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-sfb-template=\"tech\"")

    def test_unknown_preview_template_slug_falls_back_to_real_draft(self):
        """اسلاگِ نامعتبر/جعلی هرگز نباید خطا بدهد یا صفحه را بشکند —
        فقط بی‌صدا نادیده گرفته می‌شود (پیش‌نمایشِ Draftِ واقعی)."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"preview_template": "not-a-real-template"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-sfb-template=\"modern\"")

    def test_preview_candidate_resets_structural_fields_to_candidate_template_defaults(self):
        """پیش‌نمایش باید دقیقاً همان چیزی را نشان دهد که Applyِ واقعی
        تولید می‌کند — یعنی فیلدهایِ ساختاری (اینجا: گردی) به پیش‌فرضِ
        Templateِ کاندید بازنشانی شوند، نه این‌که مقدارِ Draftِ فعلی را
        نگه دارند."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({"template_slug": "modern", "radius": 18})
        draft.save(update_fields=["appearance_config"])

        boutique = appearance_registry.get_template("boutique")
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"preview_template": "boutique"})
        self.assertContains(resp, f"--sfb-radius:{boutique.radius}px")


@override_settings(ALLOWED_HOSTS=["sfb-template-public.example.com", "testserver", HOST])
class TemplateStructuralChangeReachesPublicPageTests(TestCase):
    """قدمِ Q/R/S/T واکینگِ کاربر: انتخابِ Marketplace → Publish → تغییرِ
    ساختاریِ محسوس؛ سپس تغییر به Boutique بدونِ تغییرِ محصولات/کالکشن‌ها."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname="sfb-template-public.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def _publish_with_template(self, template_slug):
        """شبیه‌سازیِ همان چیزی که ``storefront_appearance_editor`` واقعاً
        هنگامِ کلیکِ مرچنت روی کارتِ Template انجام می‌دهد: پیش‌فرض‌هایِ
        *همانِ* Template اعمال می‌شوند (نگاه کنید به ``views.py``)."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        template = appearance_registry.get_template(template_slug)
        draft.appearance_config = svc.validate_appearance_config({
            "template_slug": template_slug,
            "font": template.font, "radius": template.radius, "button_radius": template.button_radius,
            "density": template.density, "motion": template.motion, "type_scale": template.type_scale,
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

    def test_marketplace_template_changes_content_width_on_public_page(self):
        self._publish_with_template("marketplace")
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "data-sfb-template=\"marketplace\"")
        self.assertContains(resp, "--sfb-content-width:1320px")

    def test_editorial_template_increases_heading_size_on_public_page(self):
        """قالبِ ``editorial`` مقیاسِ تایپوگرافیِ پیش‌فرضِ ``large`` دارد —
        این آزمون تأیید می‌کند این پیش‌فرض واقعاً تا CSS custom property
        رویِ صفحه‌ی عمومی می‌رسد، نه فقط در appearance_registry."""
        self._publish_with_template("editorial")
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "--sfb-heading-size:22px")

    def test_switching_to_boutique_does_not_touch_products(self):
        from apps.catalog.models import Product

        product_count_before = Product.objects.filter(store=self.store).count()
        self._publish_with_template("marketplace")
        self._publish_with_template("boutique")
        product_count_after = Product.objects.filter(store=self.store).count()
        self.assertEqual(product_count_before, product_count_after)

        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "data-sfb-template=\"boutique\"")
        self.assertContains(resp, "data-sfb-hero-style=\"tall\"")

    def test_explicit_structural_override_wins_over_stored_template_default(self):
        """Phase 8 P0-7 — یک فروشگاهِ روی Templateِ ``modern`` (که
        content_width پیش‌فرضش ۱۲۰۰ است) با override صریح ۱۱۰۰ باید
        همان ۱۱۰۰ را روی صفحه‌ی عمومی نشان دهد — نه پیش‌فرضِ Template."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = svc.validate_appearance_config({
            "template_slug": "modern", "content_width": 1100,
        })
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, "--sfb-content-width:1100px")

    def test_store_never_touching_structural_advanced_panel_keeps_stored_template_defaults(self):
        """رگرسیون: فروشگاهی که هرگز پنلِ جدید را لمس نکرده (فقط
        template_slug ذخیره دارد) باید دقیقاً همان مقادیرِ Templateِ
        خودش را ببیند — بدونِ نیاز به Migration."""
        self._publish_with_template("editorial")
        editorial = appearance_registry.get_template("editorial")
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST="sfb-template-public.example.com")
        self.assertContains(resp, f"--sfb-content-width:{editorial.content_width}px")
        self.assertContains(resp, f"data-sfb-hero-style=\"{editorial.hero_style}\"")
