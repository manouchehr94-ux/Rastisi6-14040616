"""Phase 6 — Preset System: اعتبارسنجیِ خودِ ``layout_preset_registry.py``
(بخشِ section/page، مستقل از هر Draftِ واقعی).

پوششِ الزاماتِ ۱، ۲، ۳ از فهرستِ تست‌هایِ Phase 6:
۱) تعاریفِ Preset درون‌ساخت باید اعتبارسنجی شوند؛
۲) کلیدِ section ناشناخته رد شود؛
۳) ترکیبِ نامعتبرِ page/section رد شود."""

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry


class BuiltInPresetsValidateTests(SimpleTestCase):
    """۱ — هر چهار Preset درون‌ساخت باید در زمانِ import (بدونِ نیاز به
    دیتابیس) بدونِ خطا معتبر باشند — دقیقاً همان الگویِ
    ``test_preset_registry_import.py`` برایِ رجیستریِ قدیمی."""

    def test_five_internal_plus_fifty_latest_ready_templates_are_registered(self):
        # Phase 3 (Universal Storefront — V5 Golden Homepage) added a
        # fifth built-in preset ("v5_golden_homepage"). U10 added the 8
        # required Ready Template recipe keys on top of that (5 + 8 = 13).
        self.assertEqual(len(lpr.LAYOUT_PRESET_REGISTRY), 58)

    def test_all_built_in_presets_have_unique_keys(self):
        keys = [p.key for p in lpr.list_layout_presets()]
        self.assertEqual(len(keys), len(set(keys)))

    #: Phase 3 (Universal Storefront — V5 Golden Homepage) — این Preset
    #: عمداً فقط صفحه‌ی اصلی را پوشش می‌دهد (دامنه‌ی صریحِ این فاز:
    #: Homepage only)؛ دقیقاً همان استثنایی که خودِ docstring پایین
    #: از قبل مجاز می‌داند («a preset may omit a page deliberately»).
    _HOME_ONLY_PRESET_KEYS = {"v5_golden_homepage"}

    def test_every_built_in_preset_covers_all_six_pages(self):
        """۱۱ — معماری باید از هر ۶ نوع صفحه پشتیبانی کند؛ هرکدام از
        Presetهای درون‌ساختِ چندصفحه‌ای واقعاً هر ۶ صفحه را پوشش می‌دهند
        (طبقِ طراحیِ این فاز، نه یک الزامِ اجباریِ معماری — یک Preset
        مجاز است صفحه‌ای را عمداً جا بیندازد، مثلِ ``v5_golden_homepage``
        بالا)."""
        for preset in lpr.list_layout_presets():
            if preset.key in self._HOME_ONLY_PRESET_KEYS:
                self.assertEqual(set(preset.pages.keys()), {"home"}, preset.key)
                continue
            self.assertEqual(set(preset.pages.keys()), section_registry.ALL_PAGE_TYPES, preset.key)

    def test_no_built_in_preset_embeds_a_tenant_specific_id(self):
        """۱۶ — هیچ Presetِ سراسری نباید یک شناسه‌ی خاصِ یک فروشگاه
        (محصول/دسته/کالکشن/برند) را در تنظیماتِ خودش داشته باشد."""
        suspicious_keys = {"product_id", "category_id", "collection_id", "brand_id", "source_id", "product_ids", "manual_product_ids"}
        for preset in lpr.list_layout_presets():
            for page_type, entries in preset.pages.items():
                for entry in entries:
                    if entry.settings is None:
                        continue
                    self.assertFalse(
                        suspicious_keys & set(entry.settings.keys()),
                        f"{preset.key}/{page_type}/{entry.section_key} settings={entry.settings}",
                    )

    def test_compatible_families_defaults_to_universal(self):
        """۲۷ — برخلافِ ``preset_registry.PresetDefinition`` منجمد (که
        ``family_slug`` الزامی دارد)، هیچ Presetِ V2ای نباید ذاتاً به یک
        Family خاص قفل شود."""
        for preset in lpr.list_layout_presets():
            self.assertIsNone(preset.compatible_families, preset.key)


class RejectsInvalidPresetShapeTests(SimpleTestCase):
    """۲، ۳ — ثبتِ یک Presetِ بدشکل باید بدونِ آلوده‌کردنِ رجیستریِ سراسری رد شود."""

    def test_unknown_section_key_rejected(self):
        bad = lpr.LayoutPresetDefinition(
            key="__test_bad_section_key__", label_fa="x", description_fa="x",
            pages={"home": (lpr.PresetSectionEntry("this_section_does_not_exist"),)},
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(bad)
        self.assertNotIn("__test_bad_section_key__", lpr.LAYOUT_PRESET_REGISTRY)

    def test_section_not_allowed_on_page_rejected(self):
        """``product_main`` فقط رویِ ``product_detail`` مجاز است — قرار
        دادنش رویِ ``home`` باید رد شود."""
        bad = lpr.LayoutPresetDefinition(
            key="__test_bad_page_combo__", label_fa="x", description_fa="x",
            pages={"home": (lpr.PresetSectionEntry("product_main"),)},
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(bad)
        self.assertNotIn("__test_bad_page_combo__", lpr.LAYOUT_PRESET_REGISTRY)

    def test_unknown_page_type_rejected(self):
        bad = lpr.LayoutPresetDefinition(
            key="__test_bad_page_type__", label_fa="x", description_fa="x",
            pages={"not_a_real_page_type": (lpr.PresetSectionEntry("rich_text"),)},
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(bad)
        self.assertNotIn("__test_bad_page_type__", lpr.LAYOUT_PRESET_REGISTRY)

    def test_invalid_section_settings_rejected(self):
        """``product_section`` یک ``data_source`` معتبر لازم دارد — مقدارِ
        نامعتبر باید رد شود، نه بی‌صدا نادیده گرفته شود."""
        bad = lpr.LayoutPresetDefinition(
            key="__test_bad_settings__", label_fa="x", description_fa="x",
            pages={"home": (lpr.PresetSectionEntry("product_section", settings={"data_source": "not_a_real_source"}),)},
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(bad)
        self.assertNotIn("__test_bad_settings__", lpr.LAYOUT_PRESET_REGISTRY)

    def test_valid_partial_settings_accepted(self):
        """مقابلِ تستِ بالا — یک Presetِ معتبر با تنظیماتِ *جزئی* (فقط
        ``data_source``ی خنثی، بدونِ ID فروشگاه‌محور) باید ثبت شود."""
        ok = lpr.LayoutPresetDefinition(
            key="__test_ok_settings__", label_fa="x", description_fa="x",
            pages={"home": (lpr.PresetSectionEntry("product_section", settings={"data_source": "newest"}),)},
        )
        try:
            lpr.register_layout_preset(ok)
            self.assertIn("__test_ok_settings__", lpr.LAYOUT_PRESET_REGISTRY)
        finally:
            lpr.LAYOUT_PRESET_REGISTRY.pop("__test_ok_settings__", None)
