"""Selected Ready Template → delivered storefront fidelity (onboarding end to end).

Findings these tests pin (see the investigation report):

* the Draft/Published provenance and composition ARE exactly the selected Ready Template;
* a brand-new Store is empty, so the data-driven sections (hero slides, category rail, product rows) have
  nothing to show — the delivered storefront used to be only the template's shell;
* the first-run structural placeholders keep the selected composition visible WITHOUT creating any merchant
  commerce record, only for modern-portal Stores with no listable product;
* the Template step makes preview vs select vs apply unmistakable (server stays the authority).
"""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import HeroSlide
from apps.portal.services import provisioning_service
from apps.storefront_builder import appearance_registry, layout_preset_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion
from apps.storefront_builder.services import store_template_service
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
_HOST = "rastisi.localhost"
_PASS = "a-very-strong-pass-1"

# Three visually contrasting canonical Ready Templates (dark neon / terracotta boutique / marketplace spectrum).
TEMPLATES = ("dark_digital", "warm_boutique", "dense_marketplace")


def _public_get(store, path="/"):
    domain = store.domains.filter(is_primary=True).first().hostname
    with override_settings(ALLOWED_HOSTS=[domain, _HOST, "testserver"]):
        return Client().get(path, HTTP_HOST=domain)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class FidelityBase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="fid-owner@example.com", email="fid-owner@example.com", password=_PASS)
        self.store = provisioning_service.provision_trial_store(owner=self.owner, name="فروشگاه وفاداری")
        self.client.force_login(self.owner)

    def url(self, stage, store=None):
        return f"/app/stores/{(store or self.store).public_id}/onboarding/{stage}/"

    def select(self, key):
        return self.client.post(self.url("template"), {"template_key": key}, HTTP_HOST=_HOST)

    def publish(self):
        return self.client.post(self.url("review"), {}, HTTP_HOST=_HOST)

    def commerce_counts(self, store=None):
        store = store or self.store
        return (
            Product.objects.filter(store=store).count(), Category.objects.filter(store=store).count(),
            HeroSlide.objects.filter(store=store).count(),
        )


class DraftAndPublishedStructureMatchTheCatalogTests(FidelityBase):
    def structure(self, version):
        home = version.get_page("home")
        return {
            "sections": [s.section_key for s in home.sections.order_by("order", "id")],
            "provenance": version.template_provenance["template"],
            "palette": version.appearance_config.get("palette_slug"),
            "header_variant": (version.header_config or {}).get("header_variant"),
            "footer_variant": (version.footer_config or {}).get("footer_variant"),
        }

    def canonical(self, key):
        preset = layout_preset_registry.get_layout_preset(key)
        return {
            "sections": [e.section_key for e in preset.pages["home"]],
            "provenance": {"key": key, "version": preset.version},
            "palette": preset.default_palette_slug,
            "header_variant": (preset.header or {}).get("header_variant"),
            "footer_variant": (preset.footer or {}).get("footer_variant"),
        }

    def test_selected_template_survives_draft_to_publish_exactly_for_three_templates(self):
        for key in TEMPLATES:
            with self.subTest(template=key):
                cache.clear()
                owner = User.objects.create_user(username=f"fid-{key}@example.com", email=f"fid-{key}@example.com", password=_PASS)
                store = provisioning_service.provision_trial_store(owner=owner, name=f"فروشگاه {key}")
                client = Client()
                client.force_login(owner)
                client.post(self.url("template", store), {"template_key": key}, HTTP_HOST=_HOST)

                applied = store_template_service.get_applied_template(store)
                self.assertEqual((applied.key, applied.location), (key, "draft"))
                draft = StorefrontLayout.objects.get(store=store).draft_version
                self.assertEqual(self.structure(draft), self.canonical(key))

                client.post(self.url("review", store), {}, HTTP_HOST=_HOST)
                layout = StorefrontLayout.objects.get(store=store)
                self.assertIsNone(layout.draft_version_id)
                self.assertEqual(layout.published_version_id, draft.pk)  # the SAME Draft was published
                self.assertEqual(self.structure(layout.published_version), self.canonical(key))
                applied = store_template_service.get_applied_template(store)
                self.assertEqual((applied.key, applied.location), (key, "published"))


class FirstRunPlaceholderTests(FidelityBase):
    def published_public_html(self, key):
        self.select(key)
        self.publish()
        self.store.refresh_from_db()
        response = _public_get(self.store)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_an_empty_store_keeps_the_selected_composition_visible_for_three_templates(self):
        htmls = {}
        for key in TEMPLATES:
            with self.subTest(template=key):
                cache.clear()
                owner = User.objects.create_user(username=f"fp-{key}@example.com", email=f"fp-{key}@example.com", password=_PASS)
                store = provisioning_service.provision_trial_store(owner=owner, name=f"فروشگاه {key}")
                client = Client()
                client.force_login(owner)
                client.post(self.url("template", store), {"template_key": key}, HTTP_HOST=_HOST)
                client.post(self.url("review", store), {}, HTTP_HOST=_HOST)
                html = _public_get(store).content.decode()
                htmls[key] = html
                # The template's composition is recognisable: hero + product rows are present as placeholders…
                self.assertIn('data-first-run-placeholder="hero"', html)
                self.assertIn('data-first-run-placeholder="products"', html)
                # …and the selected template's OWN palette is what styles the page.
                preset = layout_preset_registry.get_layout_preset(key)
                primary = appearance_registry.get_palette(preset.default_palette_slug).colors["primary"]
                self.assertIn(f"--brand-primary:{primary}", html)
                # No fake commerce is created or claimed.
                self.assertEqual(self.commerce_counts(store), (0, 0, 0))
        # The three deliveries are visibly different from one another (palette differs).
        palettes = {re.search(r"--brand-primary:(#[0-9A-Fa-f]{6})", h).group(1).upper() for h in htmls.values()}
        self.assertEqual(len(palettes), 3)

    def test_category_rail_placeholder_appears_for_templates_that_compose_one(self):
        key = next(
            p.key for p in layout_preset_registry.list_ready_templates()
            if "category_grid" in [e.section_key for e in p.pages["home"]]
        )
        html = self.published_public_html(key)
        self.assertIn('data-first-run-placeholder="categories"', html)

    def test_placeholders_are_never_persisted_and_create_no_merchant_records(self):
        before = self.commerce_counts()
        versions = StorefrontLayoutVersion.objects.count()
        self.published_public_html("dark_digital")
        _public_get(self.store)  # rendering the public page a second time creates nothing either
        self.assertEqual(self.commerce_counts(), before)
        self.assertEqual(self.commerce_counts(), (0, 0, 0))
        published = StorefrontLayoutVersion.objects.get(layout__store=self.store, status="published")
        self.assertNotIn("first_run", str(published.template_provenance))
        self.assertEqual(StorefrontLayoutVersion.objects.count(), versions + 1)  # only the selected template's own Draft→Published

    def test_the_first_product_replaces_the_product_rows_but_the_empty_hero_stays_until_slides_exist(self):
        html = self.published_public_html("dark_digital")
        self.assertIn('data-first-run-placeholder="products"', html)
        vendor = Vendor.objects.create(store=self.store, name="v", slug="v-fr")
        category = Category.objects.create(store=self.store, name="c", slug="c-fr")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای واقعی", slug="p-fr",
            sku="SKU-FR-1", price=Decimal("1000"), status=Product.Status.ACTIVE,
        )
        html = _public_get(self.store).content.decode()
        self.assertNotIn('data-first-run-placeholder="products"', html)  # real data replaces the product placeholder
        self.assertNotIn('data-first-run-placeholder="categories"', html)  # a real category now exists
        self.assertIn("کالای واقعی", html)
        # The template's Hero is still recognisable: it has no real slides yet, and the merchant has not
        # published any later layout — adding a first product must not collapse it.
        self.assertIn('data-first-run-placeholder="hero"', html)

    def test_a_legacy_store_without_the_signal_is_unchanged(self):
        legacy = Store.objects.create(
            name="قدیمی", slug="legacy-fid", status=Store.Status.ACTIVE, platform_code=generate_unique_platform_code(),
            onboarding_completed_at=timezone.now(),
        )
        owner = User.objects.create_user(username="fid-legacy@example.com", email="fid-legacy@example.com", password=_PASS)
        StoreMembership.objects.create(
            store=legacy, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        from apps.storefront_builder.services import first_run_placeholder_service as svc

        self.assertIsNone(legacy.onboarding_required_at)
        self.assertFalse(svc.is_first_run_store(legacy))

    def test_another_stores_products_never_count_for_this_store(self):
        other_owner = User.objects.create_user(username="fid-other@example.com", email="fid-other@example.com", password=_PASS)
        other = provisioning_service.provision_trial_store(owner=other_owner, name="دیگری")
        vendor = Vendor.objects.create(store=other, name="v", slug="v-o")
        Product.objects.create(
            store=other, vendor=vendor, name="کالای دیگری", slug="p-o", sku="SKU-O", price=Decimal("1"),
            status=Product.Status.ACTIVE,
        )
        html = self.published_public_html("dark_digital")
        self.assertIn('data-first-run-placeholder="products"', html)  # this Store is still empty
        self.assertNotIn("کالای دیگری", html)

    def test_only_the_home_page_gets_placeholders(self):
        from apps.storefront_builder.services import first_run_placeholder_service as svc

        self.select("dark_digital")
        self.publish()
        items = [{"section": type("S", (), {"section_key": "product_section"})(), "context": {"products": []}}]
        self.assertEqual(svc.apply_first_run_placeholders(items, self.store, page_type="product_list"), items)


class TemplateStepInteractionTests(FidelityBase):
    def html(self):
        response = self.client.get(self.url("template"), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_every_card_has_an_explicit_choose_affordance_and_a_sample_content_label(self):
        html = self.html()
        self.assertEqual(html.count('class="ob-tpl-choose"'), 50)
        self.assertEqual(html.count('class="ob-tpl-sample"'), 50)
        self.assertIn("data-ob-sample-note", html)
        self.assertIn("پیش‌نمایش‌ها با محتوای نمونه ساخته شده‌اند", html)

    def test_nothing_is_selected_or_applicable_before_an_explicit_choice(self):
        html = self.html()
        self.assertNotRegex(html, r'name="template_key" value="[^"]+" checked')
        self.assertNotIn("ob-tpl-card is-selected", html)
        self.assertIn("هنوز قالبی انتخاب نشده است", html)

    def test_the_large_preview_is_a_plain_link_and_a_dialog_that_states_it_does_not_select(self):
        html = self.html()
        # the zoom control is an <a href> outside any form field: it cannot submit a template_key
        self.assertRegex(html, r'<a class="ob-tpl-zoom" href="[^"]+\.webp"')
        self.assertIn("این فقط یک پیش‌نمایش است و قالبی را انتخاب یا اعمال نمی‌کند", html)
        self.assertIn("data-ob-lightbox-choose", html)  # the ONLY way to select from the preview is an explicit button

    def test_the_cta_names_what_will_be_applied_and_the_stylesheet_keeps_it_visible(self):
        from pathlib import Path

        import apps.portal as portal_app_module

        html = self.html()
        self.assertIn("اعمالِ قالبِ انتخاب‌شده و ادامه", html)  # no-JS fallback label
        base = Path(portal_app_module.__file__).resolve().parent / "static/portal"
        js = (base / "js/onboarding.js").read_text(encoding="utf-8")
        css = (base / "css/onboarding.css").read_text(encoding="utf-8")
        self.assertIn("اعمالِ «' + name + '» و ادامه", js)
        self.assertIn("data-ob-lightbox-choose", html)
        self.assertRegex(css, r"\.ob-page--gallery \.ob-actions\{position:sticky;bottom:0")

    def test_preview_alone_never_applies_anything(self):
        """A GET (opening a page/preview) and a POST without an explicit template_key mutate nothing."""
        counts = (StorefrontLayout.objects.count(), StorefrontLayoutVersion.objects.count())
        self.client.get(self.url("template") + "?template_key=dark_digital", HTTP_HOST=_HOST)
        self.client.post(self.url("template"), {}, HTTP_HOST=_HOST)
        self.client.post(self.url("template"), {"preview": "dark_digital", "zoom": "dark_digital"}, HTTP_HOST=_HOST)
        self.assertEqual((StorefrontLayout.objects.count(), StorefrontLayoutVersion.objects.count()), counts)
        self.assertIsNone(store_template_service.get_applied_template(self.store))

    def test_applying_requires_the_explicit_selection_post_and_applies_exactly_that_key(self):
        self.select("warm_boutique")
        applied = store_template_service.get_applied_template(self.store)
        self.assertEqual(applied.key, "warm_boutique")

    def test_the_selected_card_is_visibly_selected_after_apply(self):
        self.select("dark_digital")
        html = self.html()
        self.assertEqual(html.count("ob-tpl-card is-selected"), 1)
        self.assertRegex(html, r'value="dark_digital" checked')


class ReviewShowsTheAppliedTemplateTests(FidelityBase):
    def test_review_displays_name_version_screenshot_and_the_sample_content_explanation(self):
        self.select("dark_digital")
        applied = store_template_service.get_applied_template(self.store)
        response = self.client.get(self.url("review"), HTTP_HOST=_HOST)
        html = response.content.decode()
        self.assertContains(response, "قالبِ انتخاب‌شده شما")
        self.assertContains(response, applied.preset.label_fa)
        self.assertContains(response, f"نسخه‌ی {applied.version}")
        self.assertIn('data-ob-review-template="dark_digital"', html)
        self.assertRegex(html, r'class="ob-review-tpl-shot" src="[^"]*dark_digital/v3\.webp"')
        self.assertIn("با محتوای نمونه ساخته شده است", html)
        self.assertIn("بدونِ محصول منتشر می‌شود", html)

    def test_review_reflects_a_later_change_of_template(self):
        self.select("dark_digital")
        self.select("warm_boutique")
        html = self.client.get(self.url("review"), HTTP_HOST=_HOST).content.decode()
        self.assertIn('data-ob-review-template="warm_boutique"', html)
        self.assertNotIn('data-ob-review-template="dark_digital"', html)


class PermissionsAndTenancyStayIntactTests(FidelityBase):
    def test_a_member_without_settings_manage_cannot_apply(self):
        analyst = User.objects.create_user(username="fid-an@example.com", email="fid-an@example.com", password=_PASS)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(analyst)
        self.assertEqual(self.select("dark_digital").status_code, 403)
        self.assertIsNone(store_template_service.get_applied_template(self.store))

    def test_another_owner_cannot_apply_to_this_store(self):
        intruder = User.objects.create_user(username="fid-int@example.com", email="fid-int@example.com", password=_PASS)
        provisioning_service.provision_trial_store(owner=intruder, name="مهاجم")
        self.client.force_login(intruder)
        self.assertEqual(self.select("dark_digital").status_code, 404)
        self.assertIsNone(store_template_service.get_applied_template(self.store))
