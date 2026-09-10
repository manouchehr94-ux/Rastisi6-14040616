"""Phase 6 — Preset System: ``services/preset_service.py`` (اعمالِ Preset
روی Draft) و ویوی ``storefront_apply_layout_preset``.

پوششِ الزاماتِ ۴-۲۸ از فهرستِ تست‌هایِ Phase 6 (۱-۳ در
``test_layout_preset_registry.py``)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-p6-preset.rastisi.localhost"
PUBLIC_HOST = "sfb-p6-preset.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="sfb-p6-store-b", defaults=dict(name="فروشگاه دوم فاز ۶", status=Store.Status.ACTIVE),
    )
    return store


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class PresetServiceTestCase(TestCase):
    def setUp(self):
        # Phase 1 correction: ``get_or_create_draft`` نرخِ خودش را بر رویِ
        # ``cache`` (نه دیتابیس/تراکنش) می‌شمارد — بدونِ پاک‌سازیِ آن بینِ
        # تست‌ها، فراخوان‌هایِ تجمعیِ کلاس‌هایِ *بعدیِ* همین فایل (که همگی
        # همین Store ثابتِ «akhlaghi» را به اشتراک می‌گذارند) می‌توانند سقفِ
        # ``_NEW_DRAFT_RATE_LIMIT`` را رد کنند — دقیقاً همان الگویی که
        # ``test_render_service.py::BuildRenderItemsTests`` از قبل رعایت می‌کند.
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="p6_preset_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="p6_preset_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)
        self.preset = lpr.get_layout_preset("dense_catalog")


class HiddenFromLibrarySectionsNeverBuiltByPresetTests(PresetServiceTestCase):
    """Task 9 — ``_build_sections_for_page`` must honor the same
    ``hidden_from_library`` gate ``section_structure_service.add_section``/
    ``duplicate_section`` already enforce. Four real A8 recipes
    (``premium_leather``, ``street_drop``, ``racer_tech``,
    ``anniversary_mosaic``) still carry a ``ticker`` component token that maps
    to ``announcement_bar`` (hidden from the library, superseded by the
    header's own notification bar) — applying any of them must not create an
    ``announcement_bar`` section, since one would double-render the strip the
    header already shows."""

    def test_ticker_bearing_a8_recipes_never_create_announcement_bar_section(self):
        for key in ("premium_leather", "street_drop", "racer_tech", "anniversary_mosaic"):
            preset = lpr.get_layout_preset(key)
            draft = svc.get_or_create_draft(self.store)
            preset_service.apply_preset(draft, preset)
            self.assertFalse(
                StorefrontSection.objects.filter(
                    page__version=draft, section_key="announcement_bar",
                ).exists(),
                f"preset {key!r} must not build a hidden_from_library announcement_bar section",
            )


class ValidationRejectionTests(PresetServiceTestCase):
    """۴، ۵، ۶ — appearance/header/footerِ نامعتبر باید رد شوند، نه بی‌صدا اصلاح."""

    def test_invalid_header_override_rejected(self):
        bad = lpr.LayoutPresetDefinition(
            key="__bad_header__", label_fa="x", description_fa="x",
            header={"show_cart": False},
        )
        with self.assertRaises(preset_service.InvalidPresetError):
            preset_service.validate_layout_preset(bad)

    def test_invalid_footer_override_rejected(self):
        bad = lpr.LayoutPresetDefinition(
            key="__bad_footer__", label_fa="x", description_fa="x",
            footer={f: False for f in [
                "show_about", "show_contact", "show_quick_links", "show_categories",
                "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright",
            ]},
        )
        with self.assertRaises(preset_service.InvalidPresetError):
            preset_service.validate_layout_preset(bad)

    def test_invalid_appearance_override_rejected(self):
        bad = lpr.LayoutPresetDefinition(
            key="__bad_appearance__", label_fa="x", description_fa="x",
            appearance={"density": "not_a_real_density"},
        )
        with self.assertRaises(preset_service.InvalidPresetError):
            preset_service.validate_layout_preset(bad)

    def test_all_built_in_presets_pass_validate_layout_preset(self):
        for preset in lpr.list_layout_presets():
            preset_service.validate_layout_preset(preset)  # نباید هیچ خطایی پرتاب شود


class DraftOnlyAndPublishLifecycleTests(PresetServiceTestCase):
    """۷، ۸، ۹، ۱۰، ۲۲ — Draft-only، Published دست‌نخورده تا publish،
    Preview بازتاب‌دهنده، Publish فعال‌کننده، Header/Footer سراسری می‌مانند."""

    def setUp(self):
        super().setUp()
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)  # یک Publishedِ اولیه، قبل از اعمالِ Preset

    def test_apply_targets_draft_only_published_unchanged(self):
        published_before = svc.get_or_create_layout(self.store).published_version
        published_home_before = list(published_before.home_page().sections.order_by("order").values_list("section_key", flat=True))

        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)

        published_before.refresh_from_db()
        published_home_after = list(published_before.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(published_home_before, published_home_after)

        public_resp = self.public_client.get(reverse("catalog:home"))
        self.assertEqual(public_resp.status_code, 200)
        self.assertNotEqual(public_resp.content.decode().count('class="rsec"'), len(self.preset.pages["home"]))

    def test_preview_reflects_applied_preset_before_publish(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(preview_resp, 'data-section-key="category_grid"')

    def test_publish_activates_preset_publicly(self):
        """``data-section-key`` فقط در Preview درج می‌شود (نگاه کنید به
        ``responsive_section_wrapper.html``)، پس در صفحه‌ی عمومی به‌جایِ آن
        از تعدادِ بلوک‌هایِ رندرشده (``rsec``) استفاده می‌کنیم.

        ``dense_catalog`` هفت section روی صفحه‌ی اصلی دارد، اما Acceptance
        Batch 1 (post-U11) چهارتایِ آن‌ها (``newest_products``/
        ``best_sellers``/``discounted_products``/``amazing_offers`` — همگی
        section‌هایِ داده‌محورِ اختیاری) را، وقتی داده‌شان واقعاً خالی است
        (این Store تازه هیچ کالایی ندارد)، از صفحه‌ی عمومی/زنده حذف
        می‌کند — نه Builder/editor. پس فقط سه‌تای باقی‌مانده
        (``category_grid``/``brand_carousel``/``trust_features``) واقعاً
        رندر می‌شوند؛ نگاه کنید به
        ``render_service.hide_empty_public_sections`` و
        ``test_acceptance_batch1.EmptyDataDrivenSectionsHiddenOnPublicTests``
        برایِ پوششِ کاملِ این قرارداد."""
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        svc.publish(self.store)

        public_resp = self.public_client.get(reverse("catalog:home"))
        self.assertEqual(public_resp.status_code, 200)
        self.assertEqual(public_resp.content.decode().count('class="rsec"'), 3)

    def test_header_footer_config_land_on_version_not_sections(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()

        self.assertFalse(draft.header_config.get("announcement_enabled"))  # dense_catalog اعلان را خاموش می‌کند
        section_keys = set(StorefrontSection.objects.filter(page__version=draft).values_list("section_key", flat=True))
        header_like = {k for k in section_keys if "header" in k or "footer" in k}
        # فقط collection_header مجاز است («header» در نامش هست اما یک section واقعی صفحه‌ی کالکشن است، نه هدرِ سراسری)
        self.assertEqual(header_like, {"collection_header"} if "collection_header" in section_keys else set())


class AllSixPagesOrderingAndSettingsTests(PresetServiceTestCase):
    """۱۱، ۱۲، ۱۳، ۱۴ — هر ۶ صفحه، ترتیب، responsive، تنظیماتِ section حفظ می‌شوند."""

    def test_all_six_pages_populated(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        for page_type in StorefrontPage.PageType.values:
            page = draft.get_page(page_type)
            self.assertTrue(page.sections.exists(), page_type)

    def test_page_ordering_matches_preset_definition_order(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        home = draft.home_page()
        actual = list(home.sections.order_by("order").values_list("section_key", flat=True))
        expected = [e.section_key for e in self.preset.pages["home"]]
        self.assertEqual(actual, expected)

    def test_responsive_defaults_present_on_every_created_section(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        for section in StorefrontSection.objects.filter(page__version=draft):
            self.assertIn("responsive", section.settings, section.section_key)

    def test_explicit_partial_section_settings_are_preserved(self):
        custom = lpr.LayoutPresetDefinition(
            key="__settings_preserved__", label_fa="x", description_fa="x",
            pages={"home": (lpr.PresetSectionEntry("product_section", settings={"data_source": "best_sellers", "item_limit": 6}),)},
        )
        lpr.register_layout_preset(custom)  # apply_preset ذخیره‌ی layout_preset_key را در برابرِ رجیستری چک می‌کند
        try:
            draft = svc.get_or_create_draft(self.store)
            preset_service.apply_preset(draft, custom)
            section = draft.home_page().sections.get(section_key="product_section")
            self.assertEqual(section.settings["data_source"], "best_sellers")
            self.assertEqual(section.settings["item_limit"], 6)
        finally:
            lpr.LAYOUT_PRESET_REGISTRY.pop("__settings_preserved__", None)


class MerchantContentPreservationTests(PresetServiceTestCase):
    """۱۵ — محتوایِ کسب‌وکاریِ مرچنت (رسانه، متنِ نوارِ اعلان) هرگز توسطِ
    اعمالِ Preset پاک/بازنویسی نمی‌شود."""

    def test_custom_announcement_text_survives_preset_apply(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**draft.effective_header_config(), "announcement_text": "MERCHANT-MARKER"}
        draft.save(update_fields=["header_config"])

        preset_service.apply_preset(draft, self.preset)  # dense_catalog هرگز announcement_text را ست نمی‌کند
        draft.refresh_from_db()
        self.assertEqual(draft.header_config.get("announcement_text"), "MERCHANT-MARKER")

    def test_catalog_product_count_unaffected_by_preset_apply(self):
        from apps.catalog.models import Product

        before = Product.objects.filter(store=self.store).count()
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        after = Product.objects.filter(store=self.store).count()
        self.assertEqual(before, after)


class LockedSectionsBlockPresetApplyTests(PresetServiceTestCase):
    """Phase 1 correction (spec §37 — Lock): اعمالِ Preset یعنی حذفِ کاملِ
    sectionهایِ هر صفحه‌ای که پوشش می‌دهد — این «مسیرِ جایگزین» هم باید
    دقیقاً همان محافظتی را رعایت کند که ``storefront_section_remove``
    برایِ حذفِ تک‌section دارد."""

    def test_locked_section_on_covered_page_blocks_apply(self):
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        locked = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0, is_locked=True,
        )
        with self.assertRaises(preset_service.LockedSectionsPresentError):
            preset_service.apply_preset(draft, self.preset)
        # هیچ نوشتنی نباید اتفاق افتاده باشد — نه section، نه appearance/header/footer
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())
        draft.refresh_from_db()
        self.assertNotEqual(draft.appearance_config.get("layout_preset_key"), self.preset.key)

    def test_unlocked_draft_still_applies_normally(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)  # نباید خطا بدهد
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("layout_preset_key"), self.preset.key)

    def test_locked_section_error_subclasses_invalid_preset_error(self):
        """کدِ ویویِ موجود فقط ``InvalidPresetError`` را می‌گیرد — این خطایِ
        جدید باید بدونِ تغییرِ آن کد هم درست نمایش داده شود."""
        self.assertTrue(issubclass(preset_service.LockedSectionsPresentError, preset_service.InvalidPresetError))

    def test_apply_view_shows_lock_message_and_leaves_section_intact(self):
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        locked = StorefrontSection.objects.create(
            page=home, section_key="rich_text", order=0, is_locked=True,
        )
        resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": self.preset.key, "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())


class TenantIsolationTests(PresetServiceTestCase):
    """۱۷ — اعمالِ Preset روی فروشگاهِ A هرگز فروشگاهِ B را لمس نمی‌کند."""

    def test_applying_to_store_a_never_touches_store_b(self):
        store_b = _second_store()
        draft_b = svc.get_or_create_draft(store_b)
        home_b_before = list(draft_b.home_page().sections.order_by("order").values_list("section_key", flat=True))

        draft_a = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft_a, self.preset)

        draft_b.refresh_from_db()
        home_b_after = list(draft_b.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(home_b_before, home_b_after)


class TransactionalAndIdempotencyTests(PresetServiceTestCase):
    """۱۸، ۱۹ — اتمیک بودن و idempotent بودنِ اعمال."""

    def test_invalid_preset_leaves_draft_completely_unchanged(self):
        draft = svc.get_or_create_draft(self.store)
        appearance_before = dict(draft.appearance_config)
        home_before = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))

        bad = lpr.LayoutPresetDefinition(
            key="__will_fail__", label_fa="x", description_fa="x",
            header={"show_cart": False},
            pages={"home": (lpr.PresetSectionEntry("hero_banner"),)},
        )
        with self.assertRaises(preset_service.InvalidPresetError):
            preset_service.apply_preset(draft, bad)

        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config, appearance_before)
        self.assertEqual(
            list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True)),
            home_before,
        )

    def test_db_failure_mid_apply_rolls_back_everything(self):
        """شبیه‌سازیِ خطایِ سطحِ دیتابیس هنگامِ نوشتنِ صفحه‌ی دوم — چون
        کلِ ``apply_preset`` در یک تراکنش پیچیده شده، حتی نوشتنِ
        appearance_config (که زودتر انجام شده) هم باید rollback شود."""
        draft = svc.get_or_create_draft(self.store)
        appearance_before = dict(draft.appearance_config)

        with mock.patch.object(
            StorefrontSection.objects, "bulk_create", side_effect=RuntimeError("simulated failure"),
        ):
            with self.assertRaises(RuntimeError):
                preset_service.apply_preset(draft, self.preset)

        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config, appearance_before)

    def test_reapplying_same_preset_is_idempotent(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        first = list(draft.home_page().sections.order_by("order").values_list("section_key", "settings"))

        preset_service.apply_preset(draft, self.preset)
        second = list(draft.home_page().sections.order_by("order").values_list("section_key", "settings"))

        self.assertEqual(first, second)
        self.assertEqual(draft.home_page().sections.count(), len(self.preset.pages["home"]))


class EditingAfterApplyAndNextDraftTests(PresetServiceTestCase):
    """۲۰، ۲۱ — پس از اعمال، ویرایشِ دستی عادی کار می‌کند؛ Draftِ بعدی
    (پس از publish) نتیجه‌ی اعمال‌شده را حفظ می‌کند."""

    def test_manual_edit_after_apply_works_normally(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        home = draft.home_page()
        StorefrontSection.objects.create(page=home, section_key="rich_text", order=99, settings={"body_html": "manual add"})
        self.assertTrue(home.sections.filter(section_key="rich_text").exists())

    def test_next_draft_after_publish_preserves_preset_result(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        svc.publish(self.store)

        next_draft = svc.get_or_create_draft(self.store)
        self.assertEqual(next_draft.appearance_config.get("layout_preset_key"), "dense_catalog")
        self.assertEqual(
            list(next_draft.home_page().sections.order_by("order").values_list("section_key", flat=True)),
            [e.section_key for e in self.preset.pages["home"]],
        )


class PaletteSeparationTests(PresetServiceTestCase):
    """۲۳ — Palette همیشه مستقل/آزاد می‌ماند."""

    def test_preset_sets_default_palette_when_merchant_has_none(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = {**draft.effective_appearance_config(), "palette_slug": None}
        draft.save(update_fields=["appearance_config"])

        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("palette_slug"), self.preset.default_palette_slug)

    def test_applying_a_template_replaces_the_previous_palette_baseline(self):
        """Acceptance Batch 1 (post-U11) — corrects the original assumption
        this test enforced (a Preset's palette was a one-time suggestion
        that never overrode an existing choice). Real QA found this made
        an explicit Ready Template switch (dense_marketplace/dark_digital)
        silently keep whatever palette the store had before, which
        contradicts the Template baseline including its default palette.
        Explicitly applying a Ready Template is a deliberate action that
        replaces the whole previous baseline — exactly like it already
        replaces section composition — not merely a passive suggestion."""
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = {
            **draft.effective_appearance_config(), "palette_slug": "rose",
            "color_overrides": {"primary": "#123456"}, "color_overrides_customized": True,
        }
        draft.save(update_fields=["appearance_config"])

        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("palette_slug"), self.preset.default_palette_slug)
        # color_overrides is a separate, always-free customization layer on
        # top of whichever palette is active — untouched by a Template
        # apply when it is a genuine, flagged merchant customization
        # (Part 2B: distinguished from a bootstrap-mirrored carryover,
        # see ``StaleColorOverridesClearedOnApplyTests`` below).
        self.assertEqual(draft.appearance_config.get("color_overrides"), {"primary": "#123456"})

    def test_merchant_can_still_freely_change_palette_after_applying_template(self):
        """The Template's default palette is only the *baseline* set at
        apply time — a merchant remains completely free to change it
        afterward, exactly as before this fix; nothing about applying a
        Template locks the palette control."""
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("palette_slug"), self.preset.default_palette_slug)

        draft.appearance_config = {**draft.effective_appearance_config(), "palette_slug": "rose"}
        draft.save(update_fields=["appearance_config"])
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("palette_slug"), "rose")


class StaleColorOverridesClearedOnApplyTests(PresetServiceTestCase):
    """Part 2B (ibolak Home rebuild) — merchant-reported regression: a
    Store's ``color_overrides`` mirrored once by
    ``bootstrap_service.bootstrap_appearance_config`` (migration-safety
    carryover of the live ``ShopSettings`` colors, never a deliberate
    in-editor choice) survived an explicit Ready Template apply and
    silently defeated that Template's ``default_palette_slug`` forever —
    every Ready Template rendered with the Store's old purple identity
    regardless of its own registered palette. ``color_overrides_customized``
    (set only by the dashboard's own color-editing view) is the fix:
    apply_preset now clears a *stale* (unflagged) override the same way it
    already replaces ``palette_slug``, while a genuinely flagged merchant
    customization (see ``PaletteSeparationTests`` above) is still
    preserved exactly as before."""

    def test_stale_bootstrap_mirrored_override_is_cleared_on_apply(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = {
            **draft.effective_appearance_config(),
            "palette_slug": None,
            "color_overrides": {"primary": "#6D28D9", "accent": "#FF4D77"},
            "color_overrides_customized": False,
        }
        draft.save(update_fields=["appearance_config"])

        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("palette_slug"), self.preset.default_palette_slug)
        self.assertEqual(draft.appearance_config.get("color_overrides"), {})

    def test_genuinely_customized_override_survives_apply(self):
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = {
            **draft.effective_appearance_config(),
            "palette_slug": None,
            "color_overrides": {"primary": "#123456"},
            "color_overrides_customized": True,
        }
        draft.save(update_fields=["appearance_config"])

        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("color_overrides"), {"primary": "#123456"})

    def test_preset_without_a_default_palette_never_touches_overrides_either_way(self):
        """A legacy Preset with ``default_palette_slug=None`` never claims
        to replace the palette baseline at all — so it must not clear
        color_overrides either, flagged or not (the whole clearing branch
        is nested under the same ``if preset.default_palette_slug is not
        None`` condition as the pre-existing palette_slug replacement)."""
        preset_without_palette = lpr.LayoutPresetDefinition(
            key="__no_default_palette__", label_fa="x", description_fa="x",
        )
        self.assertIsNone(preset_without_palette.default_palette_slug)
        # apply_preset resolves ``layout_preset_key`` against the registry
        # (see ``validate_appearance_config``) — register this ad-hoc test
        # preset so that lookup succeeds, exactly like every real preset.
        lpr.LAYOUT_PRESET_REGISTRY[preset_without_palette.key] = preset_without_palette
        self.addCleanup(lpr.LAYOUT_PRESET_REGISTRY.pop, preset_without_palette.key, None)
        draft = svc.get_or_create_draft(self.store)
        draft.appearance_config = {
            **draft.effective_appearance_config(),
            "color_overrides": {"primary": "#6D28D9"},
            "color_overrides_customized": False,
        }
        draft.save(update_fields=["appearance_config"])

        preset_service.apply_preset(draft, preset_without_palette)
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("color_overrides"), {"primary": "#6D28D9"})

    def test_bootstrap_appearance_config_never_marks_overrides_as_customized(self):
        from apps.storefront_builder.services import bootstrap_service

        config = bootstrap_service.bootstrap_appearance_config(self.store)
        self.assertFalse(config.get("color_overrides_customized", False))

    def test_dashboard_color_save_view_flags_a_genuine_override_as_customized(self):
        svc.get_or_create_draft(self.store, user=self.staff)
        response = self.admin_client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {"color_primary": "#112233"},
        )
        self.assertIn(response.status_code, (302, 200))
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.appearance_config.get("color_overrides_customized"))
        self.assertEqual(draft.appearance_config.get("color_overrides", {}).get("primary"), "#112233")

    def test_dashboard_reset_all_overrides_clears_the_customized_flag(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        draft.appearance_config = {
            **draft.effective_appearance_config(),
            "color_overrides": {"primary": "#112233"},
            "color_overrides_customized": True,
        }
        draft.save(update_fields=["appearance_config"])

        response = self.admin_client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {"reset_all_overrides": "1"},
        )
        self.assertIn(response.status_code, (302, 200))
        draft.refresh_from_db()
        self.assertFalse(draft.appearance_config.get("color_overrides_customized"))
        self.assertEqual(draft.appearance_config.get("color_overrides"), {})


class ViewLevelTests(PresetServiceTestCase):
    """۲۴، ۲۵، ۲۶ — احراز هویت، CSRF، کلیدِ نامعتبر."""

    def test_anonymous_denied(self):
        client = Client(HTTP_HOST=ADMIN_HOST)
        resp = client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "dense_catalog", "confirm_preset_apply": "1"})
        self.assertEqual(resp.status_code, 302)

    def test_role_without_permission_denied(self):
        analyst = User.objects.create_user(username="p6_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=ADMIN_HOST)
        client.login(username="p6_analyst", password="pass12345")
        resp = client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "dense_catalog", "confirm_preset_apply": "1"})
        self.assertEqual(resp.status_code, 403)

    def test_csrf_required(self):
        csrf_client = Client(HTTP_HOST=ADMIN_HOST, enforce_csrf_checks=True)
        csrf_client.login(username="p6_preset_owner", password="pass12345")
        draft = svc.get_or_create_draft(self.store)
        home_before = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))

        resp = csrf_client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "dense_catalog", "confirm_preset_apply": "1"})
        self.assertEqual(resp.status_code, 403)
        draft.refresh_from_db()
        self.assertEqual(
            list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True)),
            home_before,
        )

    def test_unknown_preset_key_fails_safely(self):
        draft = svc.get_or_create_draft(self.store)
        home_before = list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True))

        resp = self.admin_client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "does_not_exist"})
        self.assertEqual(resp.status_code, 302)  # بدونِ crash، فقط redirect با پیامِ خطا

        draft.refresh_from_db()
        self.assertEqual(
            list(draft.home_page().sections.order_by("order").values_list("section_key", flat=True)),
            home_before,
        )

    def test_confirmation_required_when_pages_already_have_sections(self):
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.home_page().sections.exists())  # بوت‌استرپِ اولیه از قبل چیزی دارد

        resp = self.admin_client.post(reverse("dashboard:storefront-builder-apply-preset"), {"preset_key": "dense_catalog"})
        self.assertEqual(resp.status_code, 302)
        draft.refresh_from_db()
        self.assertNotEqual(draft.appearance_config.get("layout_preset_key"), "dense_catalog")

    def test_apply_via_view_succeeds_with_confirmation(self):
        resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            {"preset_key": "dense_catalog", "confirm_preset_apply": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.appearance_config.get("layout_preset_key"), "dense_catalog")
