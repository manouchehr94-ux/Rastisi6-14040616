"""Regression tests for the store-bundle tooling (export / validate / import /
verify), the ShopSettings provisioning fix and the two install-time accounts.

Every store here is built from scratch with the ORM and tiny generated PNGs -
these tests prove the TOOLING is correct. They are NOT evidence that the real
``demo_v5`` / ``demo_arch02`` data exists (see docs/rebuild/MISSING_INPUTS.md).
"""

import json
import os
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.catalog.models import Brand, Category, Product, ProductImage, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.storefront_builder.models import StorefrontLayout, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.demo_bundle import accounts, contract, exporter, integrity
from apps.stores.services.demo_bundle.importer import ImportAborted, import_store
from apps.stores.services.demo_bundle.report import BLOCKED, FAIL, PASS
from apps.stores.services.demo_bundle.targets import TargetStore, load_targets
from apps.stores.services.demo_bundle.validator import validate_bundle

User = get_user_model()

HOSTS = [
    "rastisi.ir", "platformadmins.rastisi.ir", "demo-v5.rastisi.ir", "demo-arch02.rastisi.ir",
    "src-one.rastisi.ir", "src-two.rastisi.ir", "testserver",
]
STRONG = "Zx9-correct-horse-battery-staple"


def png_bytes(color):
    buf = BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, "PNG")
    return buf.getvalue()


TARGET_V5 = TargetStore("demo_v5", "demo-v5", "Demo V5", "demo-v5", "demo-v5.rastisi.ir")
TARGET_ARCH = TargetStore("demo_arch02", "demo-arch02", "Demo Arch02", "demo-arch02", "demo-arch02.rastisi.ir")


def build_store(slug, *, color="#112233", product_count=2):
    """A complete little store: settings, catalogue with image files, Studio layout."""
    store = Store.objects.create(
        name=slug, slug=slug, admin_subdomain=slug, status=Store.Status.ACTIVE,
        onboarding_completed_at=timezone.now(),
    )
    StoreDomain.objects.create(
        store=store, hostname=f"{slug}.rastisi.ir", is_primary=True,
        domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )
    shop = ShopSettings.provision_for(store)
    shop.primary_color = color
    shop.logo.save(f"{slug}-logo.png", ContentFile(png_bytes((10, 20, 30))), save=False)
    shop.save()
    FooterSettings.provision_for(store)
    vendor = Vendor.objects.create(store=store, name="V", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name="C", slug=f"c-{slug}")
    brand = Brand.objects.create(store=store, name="B", slug=f"b-{slug}")
    products = []
    for i in range(product_count):
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, brand=brand, name=f"P{i}",
            slug=f"p{i}-{slug}", sku=f"SKU-{slug}-{i}", price=Decimal("1000"),
        )
        image = ProductImage(product=product, order=0, is_cover=True, alt="a")
        image.image.save(f"{slug}-{i}.png", ContentFile(png_bytes((200, i * 40, 50))), save=False)
        image.thumbnail.save(f"{slug}-{i}-t.png", ContentFile(png_bytes((i, i, i))), save=False)
        image.save()
        products.append(product)
    draft = layout_service.get_or_create_draft(store)
    home = StorefrontPage.objects.get(version=draft, page_type="home")
    StorefrontSection.objects.create(
        page=home, section_key="product_section", order=1,
        settings={"data_source": "manual", "product_ids": [p.pk for p in products], "item_limit": 8},
    )
    layout_service.publish(store)
    return store


def wipe_store(store):
    from apps.catalog.models import ProductVariant
    from apps.content.models import MenuItem

    ProductVariant.objects.filter(product__store=store).delete()
    MenuItem.objects.filter(menu__store=store).delete()
    Product.objects.filter(store=store).delete()
    store.delete()


@override_settings(ALLOWED_HOSTS=HOSTS, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class BundleTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src_media = self.tmp / "src_media"
        self.dst_media = self.tmp / "dst_media"
        self.bundle = self.tmp / "bundle"
        self.src_media.mkdir()
        self.dst_media.mkdir()
        self._override = None
        self.use_media(self.src_media)
        self.addCleanup(lambda: self._override and self._override.disable())

    def use_media(self, path):
        if self._override is not None:
            self._override.disable()
        self._override = override_settings(MEDIA_ROOT=str(path))
        self._override.enable()

    def export(self, store, key="demo_v5"):
        entry = exporter.export_store(store, self.bundle, key=key, media_root=self.src_media)
        exporter.write_manifest(self.bundle, [entry])
        return entry

    def data(self, key="demo_v5"):
        return json.loads((self.bundle / "stores" / key / "data.json").read_text(encoding="utf-8"))

    def write_data(self, records, key="demo_v5"):
        (self.bundle / "stores" / key / "data.json").write_text(json.dumps(records), encoding="utf-8")


class ExportValidateTests(BundleTestBase):
    def setUp(self):
        super().setUp()
        self.store = build_store("src-one")
        self.entry = self.export(self.store)

    def test_export_has_no_users_or_secrets(self):
        labels = {r["model"] for r in self.data()}
        self.assertFalse({l for l in labels if l.startswith(("auth.", "orders.order", "customers.", "sms.", "billing."))})
        text = (self.bundle / "stores" / "demo_v5" / "data.json").read_text(encoding="utf-8").lower()
        for needle in ("password", "api_key", "device_token", "melipayamak", "kavenegar"):
            self.assertNotIn(needle, text)

    def test_credentials_on_shopsettings_are_dropped_at_export(self):
        ShopSettings.objects.filter(store=self.store).update(
            melipayamak_password="s3cret-sms-pass", kavenegar_api_key="K-12345", smsrasti_device_token="tok",
        )
        shutil.rmtree(self.bundle)
        self.export(self.store)
        text = (self.bundle / "stores" / "demo_v5" / "data.json").read_text(encoding="utf-8")
        for leaked in ("s3cret-sms-pass", "K-12345", '"tok"'):
            self.assertNotIn(leaked, text)

    def test_validator_rejects_a_bundle_that_carries_credentials(self):
        records = self.data()
        for r in records:
            if r["model"] == "core.shopsettings":
                r["fields"]["kavenegar_api_key"] = "LEAKED"
        self.write_data(records)
        self.assertIn("secret.in_bundle", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_valid_bundle_passes(self):
        report = validate_bundle(self.bundle, targets={"demo_v5": TARGET_V5})
        self.assertEqual(report.status, PASS, report.to_text())

    def test_missing_bundle_is_blocked_not_pass(self):
        report = validate_bundle(self.tmp / "nope")
        self.assertEqual(report.status, BLOCKED)

    def test_missing_target_store_is_blocked(self):
        report = validate_bundle(self.bundle, targets={"demo_v5": TARGET_V5, "demo_arch02": TARGET_ARCH})
        self.assertEqual(report.status, BLOCKED)
        self.assertIn("store.missing", [f.code for f in report.of(BLOCKED)])

    def test_missing_media_file_fails(self):
        next((self.bundle / "media").rglob("*.png")).unlink()
        self.assertIn("media.missing", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_tampered_media_fails_hash(self):
        path = next((self.bundle / "media").rglob("*.png"))
        path.write_bytes(png_bytes((1, 2, 3)))
        self.assertIn("media.hash", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_non_image_content_fails_decode(self):
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        path = next((self.bundle / "media").rglob("*.png"))
        path.write_bytes(b"not an image at all")
        import hashlib

        for m in manifest["stores"]["demo_v5"]["media"]:
            if m["path"] == path.relative_to(self.bundle / "media").as_posix():
                m["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.assertIn("media.undecodable", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_path_traversal_in_media_is_rejected(self):
        records = self.data()
        for r in records:
            if r["model"] == "core.shopsettings":
                r["fields"]["logo"] = "../../etc/passwd"
        self.write_data(records)
        self.assertIn("media.unsafe_path", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_broken_foreign_key_fails(self):
        records = self.data()
        for r in records:
            if r["model"] == "catalog.product":
                r["fields"]["category"] = 999999
                break
        self.write_data(records)
        self.assertIn("fk.broken", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_count_mismatch_fails(self):
        self.write_data([r for r in self.data() if r["model"] != "catalog.productimage"])
        self.assertIn("count.mismatch", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_missing_shopsettings_in_bundle_is_blocked(self):
        records = [r for r in self.data() if r["model"] != "core.shopsettings"]
        self.write_data(records)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["stores"]["demo_v5"]["counts"]["core.ShopSettings"] = 0
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.assertIn("singleton.missing", [f.code for f in validate_bundle(self.bundle).of(BLOCKED)])

    def test_studio_without_published_version_fails(self):
        records = self.data()
        for r in records:
            if r["model"] == "storefront_builder.storefrontlayout":
                r["fields"]["published_version"] = None
        self.write_data(records)
        self.assertIn("studio.no_published", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_published_version_missing_a_page_type_fails(self):
        records = [r for r in self.data() if not (
            r["model"] == "storefront_builder.storefrontpage" and r["fields"]["page_type"] == "cart"
            and r["fields"]["version"] == next(
                x for x in self.data() if x["model"] == "storefront_builder.storefrontlayout")["fields"]["published_version"]
        )]
        self.write_data(records)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["stores"]["demo_v5"]["counts"]["storefront_builder.StorefrontPage"] -= 1
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.assertIn("studio.pages", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_dangling_studio_json_reference_is_reported(self):
        records = self.data()
        for r in records:
            if r["model"] == "storefront_builder.storefrontsection":
                r["fields"]["settings"]["product_ids"] = [987654]
        self.write_data(records)
        self.assertIn("json.ref_missing", [f.code for f in validate_bundle(self.bundle).findings if f.level == "WARN"])

    def test_primary_key_collision_between_stores_fails(self):
        shutil.copytree(self.bundle / "stores" / "demo_v5", self.bundle / "stores" / "demo_arch02")
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["stores"]["demo_arch02"] = {**manifest["stores"]["demo_v5"], "key": "demo_arch02"}
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.assertIn("pk.collision.total", [f.code for f in validate_bundle(self.bundle).of(FAIL)])

    def test_strict_expected_counts_block(self):
        target = TargetStore("demo_v5", "demo-v5", "x", "demo-v5", "demo-v5.rastisi.ir", {"catalog.Product": 50})
        self.assertEqual(validate_bundle(self.bundle, targets={"demo_v5": target}).status, PASS)  # advisory by default
        strict = validate_bundle(self.bundle, targets={"demo_v5": target}, strict_expected=True)
        self.assertEqual(strict.status, FAIL)

    def test_real_targets_manifest_describes_exactly_two_stores(self):
        targets = load_targets()
        self.assertEqual(set(targets), {"demo_v5", "demo_arch02"})
        self.assertEqual(targets["demo_v5"].hostname, "demo-v5.rastisi.ir")
        self.assertEqual(targets["demo_arch02"].hostname, "demo-arch02.rastisi.ir")


class ImportRoundTripTests(BundleTestBase):
    def setUp(self):
        super().setUp()
        self.store = build_store("src-one", color="#abcdef")
        self.src_counts = {
            "products": Product.objects.filter(store=self.store).count(),
            "images": ProductImage.objects.filter(product__store=self.store).count(),
            "pages": StorefrontPage.objects.filter(version__layout__store=self.store).count(),
        }
        self.published_id = StorefrontLayout.objects.get(store=self.store).published_version_id
        self.product_ids = sorted(Product.objects.filter(store=self.store).values_list("pk", flat=True))
        self.export(self.store)
        wipe_store(self.store)  # the "fresh server": source rows gone, new MEDIA_ROOT
        self.use_media(self.dst_media)

    def do_import(self, **kw):
        return import_store(self.bundle, "demo_v5", TARGET_V5, media_root=self.dst_media, **kw)

    def test_roundtrip_restores_everything_for_the_target_store(self):
        result = self.do_import()
        store = result.store
        self.assertEqual((store.slug, store.status), ("demo-v5", Store.Status.ACTIVE))
        self.assertEqual(Product.objects.filter(store=store).count(), self.src_counts["products"])
        self.assertEqual(ProductImage.objects.filter(product__store=store).count(), self.src_counts["images"])
        self.assertEqual(StorefrontPage.objects.filter(version__layout__store=store).count(), self.src_counts["pages"])
        # primary keys preserved so Studio JSON ids stay valid
        self.assertEqual(sorted(Product.objects.filter(store=store).values_list("pk", flat=True)), self.product_ids)
        section = StorefrontSection.objects.get(page__version__layout__store=store, section_key="product_section")
        self.assertEqual(section.settings["product_ids"], self.product_ids)
        self.assertEqual(StorefrontLayout.objects.get(store=store).published_version_id, self.published_id)
        # branding came from the source, not from defaults
        shop = ShopSettings.objects.get(store=store)
        self.assertEqual(shop.primary_color, "#abcdef")
        self.assertTrue((self.dst_media / shop.logo.name).is_file())
        domain = StoreDomain.objects.get(store=store)
        self.assertEqual((domain.hostname, domain.is_primary), ("demo-v5.rastisi.ir", True))

    def test_exactly_one_shopsettings_and_footer_per_store(self):
        store = self.do_import().store
        self.assertEqual(ShopSettings.objects.filter(store=store).count(), 1)
        self.assertEqual(FooterSettings.objects.filter(store=store).count(), 1)

    def test_import_is_idempotent(self):
        self.do_import()

        def snapshot():
            return {
                "stores": Store.objects.count(), "domains": StoreDomain.objects.count(),
                "products": Product.objects.count(), "images": ProductImage.objects.count(),
                "shop": ShopSettings.objects.count(), "footer": FooterSettings.objects.count(),
                "layouts": StorefrontLayout.objects.count(), "pages": StorefrontPage.objects.count(),
                "sections": StorefrontSection.objects.count(),
                "files": sorted(p.name for p in self.dst_media.rglob("*") if p.is_file()),
            }

        first = snapshot()
        second_result = self.do_import()
        self.assertEqual(snapshot(), first)
        self.assertFalse(second_result.created_store)
        self.assertEqual(second_result.media_copied, 0)

    def test_integrity_passes_after_import_including_http(self):
        self.do_import()
        report = integrity.verify_store(
            Store.objects.get(slug="demo-v5"), hostname="demo-v5.rastisi.ir", media_root=self.dst_media, http=True,
        )
        self.assertEqual(report.status, PASS, report.to_text())

    def test_dry_run_changes_nothing(self):
        self.do_import(dry_run=True)
        self.assertFalse(Store.objects.filter(slug="demo-v5").exists())
        self.assertEqual(Product.objects.count(), 0)

    def test_prune_removes_rows_not_in_bundle_only_for_that_store(self):
        store = self.do_import().store
        extra = Product.objects.create(
            store=store, vendor=Vendor.objects.get(store=store), name="extra", slug="extra-x", sku="X1", price=1,
        )
        other = build_store("src-two")
        self.do_import(prune=True)
        self.assertFalse(Product.objects.filter(pk=extra.pk).exists())
        self.assertEqual(Product.objects.filter(store=other).count(), 2)

    def test_missing_shopsettings_in_bundle_is_provisioned_empty_and_reported(self):
        records = [r for r in self.data() if r["model"] != "core.shopsettings"]
        self.write_data(records)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["stores"]["demo_v5"]["counts"]["core.ShopSettings"] = 0
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ImportAborted):  # BLOCKED by default - never silently defaulted
            self.do_import()
        result = self.do_import(allow_blocked=("singleton.missing",))
        self.assertEqual(ShopSettings.objects.filter(store=result.store).count(), 1)
        self.assertEqual(result.provisioned_empty, ["core.ShopSettings"])
        self.assertIn("settings.missing_source", [f.code for f in result.report.of(BLOCKED)])

    def test_media_conflict_is_never_overwritten(self):
        entry = json.loads((self.bundle / "manifest.json").read_text())["stores"]["demo_v5"]
        victim = self.dst_media / entry["media"][0]["path"]
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_bytes(b"someone else's file")
        with self.assertRaises(ImportAborted):
            self.do_import()
        self.assertEqual(victim.read_bytes(), b"someone else's file")
        self.assertFalse(Store.objects.filter(slug="demo-v5").exists())

    def test_two_demo_stores_stay_isolated(self):
        # second store with disjoint keys, exported into the same bundle
        self.use_media(self.src_media)
        arch_src = build_store("src-two", color="#fedcba", product_count=3)
        arch_entry = exporter.export_store(arch_src, self.bundle, key="demo_arch02", media_root=self.src_media)
        self.use_media(self.dst_media)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["stores"]["demo_arch02"] = arch_entry
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        wipe_store(arch_src)
        v5 = self.do_import().store
        arch = import_store(self.bundle, "demo_arch02", TARGET_ARCH, media_root=self.dst_media).store
        self.assertEqual(Product.objects.filter(store=v5).count(), 2)
        self.assertEqual(Product.objects.filter(store=arch).count(), 3)
        self.assertEqual(ShopSettings.objects.get(store=v5).primary_color, "#abcdef")
        self.assertEqual(ShopSettings.objects.get(store=arch).primary_color, "#fedcba")
        for store, host, other_host in ((v5, "demo-v5.rastisi.ir", "demo-arch02.rastisi.ir"),
                                         (arch, "demo-arch02.rastisi.ir", "demo-v5.rastisi.ir")):
            report = integrity.verify_store(store, hostname=host, media_root=self.dst_media, http=True)
            self.assertEqual(report.status, PASS, report.to_text())
        # a product slug of one store is a 404 on the other store's host
        arch_slug = Product.objects.filter(store=arch).first().slug
        self.assertEqual(Client().get(f"/products/{arch_slug}/", HTTP_HOST="demo-v5.rastisi.ir", secure=True).status_code, 404)

    def test_pk_owned_by_another_store_aborts_and_rolls_back(self):
        # Re-create the original rows for a DIFFERENT store at the same pks.
        other = Store.objects.create(name="o", slug="o", admin_subdomain="o", status=Store.Status.ACTIVE)
        vendor_pk = next(r["pk"] for r in self.data() if r["model"] == "catalog.vendor")
        Vendor.objects.create(pk=vendor_pk, store=other, name="mine", slug="mine")
        with self.assertRaises(ImportAborted) as ctx:
            self.do_import()
        self.assertIn("tenant.pk_conflict", [f.code for f in ctx.exception.report.of(FAIL)])
        self.assertFalse(Store.objects.filter(slug="demo-v5").exists())
        self.assertEqual(Vendor.objects.get(pk=vendor_pk).store_id, other.pk)

    def test_outside_references_are_nulled(self):
        records = self.data()
        user = User.objects.create_user("someone", password=STRONG)
        for r in records:
            if r["model"] == "catalog.vendor":
                r["fields"]["owner"] = user.pk
        self.write_data(records)
        store = self.do_import().store
        self.assertIsNone(Vendor.objects.get(store=store).owner)


class IntegrityDetectionTests(BundleTestBase):
    """The verifier must FAIL on the defects seen in the previous deployment."""

    def setUp(self):
        super().setUp()
        self.store = build_store("src-one")

    def run_verify(self, **kw):
        return integrity.verify_store(self.store, hostname="src-one.rastisi.ir", media_root=self.src_media, **kw)

    def test_clean_store_passes(self):
        self.assertEqual(self.run_verify(http=True).status, PASS)

    def test_missing_shopsettings_fails_http_and_singleton(self):
        ShopSettings.objects.filter(store=self.store).delete()
        report = self.run_verify(http=True)
        self.assertEqual(report.status, FAIL)
        codes = [f.code for f in report.of(FAIL)]
        self.assertIn("singleton", codes)
        self.assertIn("http.exception", codes)

    def test_missing_image_file_fails(self):
        image = ProductImage.objects.filter(product__store=self.store).first()
        (self.src_media / image.image.name).unlink()
        self.assertIn("file.missing", [f.code for f in self.run_verify().of(FAIL)])

    def test_empty_image_file_fails(self):
        image = ProductImage.objects.filter(product__store=self.store).first()
        (self.src_media / image.image.name).write_bytes(b"")
        self.assertIn("file.empty", [f.code for f in self.run_verify().of(FAIL)])

    def test_cross_store_reference_fails(self):
        other = build_store("src-two")
        product = Product.objects.filter(store=self.store).first()
        product.category = Category.objects.get(store=other)
        product.save(update_fields=["category"])
        self.assertIn("tenant.cross_reference", [f.code for f in self.run_verify().of(FAIL)])

    def test_missing_published_layout_is_reported(self):
        layout = StorefrontLayout.objects.get(store=self.store)
        layout.published_version = None
        layout.save()
        self.assertIn("studio.published", [f.code for f in self.run_verify().of(FAIL)])

    def test_unverified_domain_fails(self):
        StoreDomain.objects.filter(store=self.store).update(verification_status="unverified", verified_at=None)
        self.assertIn("domain.state", [f.code for f in self.run_verify().of(FAIL)])


@override_settings(ALLOWED_HOSTS=HOSTS, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class ShopSettingsProvisioningRegressionTests(TestCase):
    """Root cause of the old HTTP 500: a Store with no core_shopsettings row."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(
            name="NoSettings", slug="no-settings", admin_subdomain="no-settings", status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store, hostname="src-one.rastisi.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        FooterSettings.provision_for(self.store)
        vendor = Vendor.objects.create(store=self.store, name="V", slug="v-ns")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, name="P", slug="p-ns", sku="NS1", price=Decimal("1000"),
        )
        layout_service.get_or_create_draft(self.store)
        layout_service.publish(self.store)

    def get_detail(self):
        return Client().get(f"/products/{self.product.slug}/", HTTP_HOST="src-one.rastisi.ir", secure=True)

    def test_without_settings_the_page_fails_closed(self):
        with self.assertRaises(ShopSettingsNotProvisionedError):
            self.get_detail()

    def test_never_falls_back_to_another_stores_settings(self):
        other = Store.objects.create(name="Other", slug="other-ns", admin_subdomain="other-ns", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other)
        with self.assertRaises(ShopSettingsNotProvisionedError):
            self.get_detail()

    def test_provision_command_fixes_the_page_and_is_idempotent(self):
        out = StringIO()
        call_command("provision_shop_settings", "--store", "no-settings", stdout=out)
        self.assertEqual(ShopSettings.objects.filter(store=self.store).count(), 1)
        self.assertEqual(self.get_detail().status_code, 200)
        settings_row = ShopSettings.objects.get(store=self.store)
        settings_row.primary_color = "#010203"
        settings_row.save()
        out = StringIO()
        call_command("provision_shop_settings", "--store", "no-settings", stdout=out)
        self.assertIn("0 row(s)", out.getvalue())
        self.assertEqual(ShopSettings.objects.get(store=self.store).primary_color, "#010203")

    def test_provision_dry_run_writes_nothing(self):
        call_command("provision_shop_settings", "--all", "--dry-run", stdout=StringIO())
        self.assertFalse(ShopSettings.objects.filter(store=self.store).exists())

    def test_provision_requires_a_scope(self):
        with self.assertRaises(CommandError):
            call_command("provision_shop_settings", stdout=StringIO())

    def test_unknown_store_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command("provision_shop_settings", "--store", "nope", stdout=StringIO())


class RetireSeedStoreTests(TestCase):
    def test_empty_seed_store_is_deleted_only_with_confirm(self):
        # migration stores.0002 creates 'akhlaghi' in every fresh database
        self.assertTrue(Store.objects.filter(slug="akhlaghi").exists())
        call_command("retire_seed_store", stdout=StringIO())
        self.assertTrue(Store.objects.filter(slug="akhlaghi").exists())
        call_command("retire_seed_store", "--confirm", stdout=StringIO())
        self.assertFalse(Store.objects.filter(slug="akhlaghi").exists())

    def test_refuses_store_with_real_data(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="V", slug="v-ak")
        Product.objects.create(store=store, vendor=vendor, name="P", slug="p-ak", sku="AK1", price=1)
        with self.assertRaises(CommandError):
            call_command("retire_seed_store", "--confirm", stdout=StringIO())
        self.assertTrue(Store.objects.filter(slug="akhlaghi").exists())

    def test_never_touches_other_stores(self):
        other = Store.objects.create(name="Keep", slug="keep", admin_subdomain="keep", status=Store.Status.ACTIVE)
        call_command("retire_seed_store", "--confirm", stdout=StringIO())
        self.assertTrue(Store.objects.filter(pk=other.pk).exists())


@override_settings(ALLOWED_HOSTS=HOSTS, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class InstallAccountsTests(TestCase):
    def setUp(self):
        cache.clear()
        for t in (TARGET_V5, TARGET_ARCH):
            Store.objects.create(name=t.name, slug=t.slug, admin_subdomain=t.admin_subdomain, status=Store.Status.ACTIVE)
        self.before = User.objects.count()

    def ensure(self, **kw):
        args = dict(platform_owner_password=STRONG, shops_admin_password=STRONG + "x",
                    store_slugs=["demo-v5", "demo-arch02"])
        args.update(kw)
        return accounts.ensure_accounts(**args)

    def test_creates_exactly_two_accounts_with_correct_roles(self):
        self.ensure()
        self.assertEqual(User.objects.count(), self.before + 2)
        owner = User.objects.get(username="platform_owner")
        admin = User.objects.get(username="shops_admin")
        self.assertTrue(owner.is_superuser and owner.is_staff and owner.is_active)
        self.assertFalse(admin.is_superuser or admin.is_staff)
        self.assertEqual(StoreMembership.objects.filter(user=owner).count(), 0)
        for slug in ("demo-v5", "demo-arch02"):
            m = StoreMembership.objects.get(user=admin, store__slug=slug)
            self.assertEqual((m.role, m.status), (StoreMembership.Role.OWNER, StoreMembership.MembershipStatus.ACTIVE))

    def test_passwords_are_hashed_and_not_stored_in_plaintext(self):
        self.ensure()
        owner = User.objects.get(username="platform_owner")
        self.assertTrue(owner.check_password(STRONG))
        self.assertNotIn(STRONG, owner.password)
        self.assertTrue(owner.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))

    def test_is_idempotent_and_keeps_existing_passwords(self):
        self.ensure()
        self.ensure(platform_owner_password=None, shops_admin_password=None)
        self.assertEqual(User.objects.count(), self.before + 2)
        self.assertEqual(StoreMembership.objects.filter(user__username="shops_admin").count(), 2)
        self.assertTrue(User.objects.get(username="platform_owner").check_password(STRONG))

    def test_existing_password_changes_only_on_explicit_reset(self):
        self.ensure()
        self.ensure(platform_owner_password="Another-Strong-Pass-77", shops_admin_password=None)
        self.assertTrue(User.objects.get(username="platform_owner").check_password(STRONG))
        self.ensure(platform_owner_password="Another-Strong-Pass-77", shops_admin_password=None, reset_password=True)
        self.assertTrue(User.objects.get(username="platform_owner").check_password("Another-Strong-Pass-77"))

    def test_weak_password_is_rejected_and_nothing_is_created(self):
        with self.assertRaises(accounts.AccountError):
            self.ensure(platform_owner_password="12345678")
        self.assertEqual(User.objects.count(), self.before)

    def test_password_is_required_for_a_new_account(self):
        with self.assertRaises(accounts.AccountError):
            self.ensure(shops_admin_password=None)
        self.assertEqual(User.objects.count(), self.before)

    def test_unknown_store_aborts_before_creating_anything(self):
        with self.assertRaises(accounts.AccountError):
            self.ensure(store_slugs=["demo-v5", "ghost"])
        self.assertEqual(User.objects.count(), self.before)

    def test_does_not_displace_a_different_active_owner(self):
        rival = User.objects.create_user("rival", password=STRONG)
        StoreMembership.objects.create(
            store=Store.objects.get(slug="demo-v5"), user=rival, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        with self.assertRaises(accounts.AccountError):
            self.ensure()
        self.assertEqual(StoreMembership.objects.get(user=rival).status, StoreMembership.MembershipStatus.ACTIVE)

    def test_command_reads_passwords_from_named_env_vars_and_never_prints_them(self):
        out = StringIO()
        env = {"T_OWNER_PW": STRONG, "T_ADMIN_PW": STRONG + "y"}
        with mock.patch.dict(os.environ, env):
            call_command(
                "create_install_accounts", "--platform-owner-password-env", "T_OWNER_PW",
                "--shops-admin-password-env", "T_ADMIN_PW", stdout=out,
            )
        self.assertNotIn(STRONG, out.getvalue())
        self.assertTrue(User.objects.get(username="shops_admin").check_password(STRONG + "y"))

    def test_command_without_tty_or_env_fails_instead_of_inventing_a_password(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(CommandError):
                call_command("create_install_accounts", stdout=StringIO())
        self.assertEqual(User.objects.count(), self.before)

    def test_command_has_no_password_cli_argument(self):
        with self.assertRaises(CommandError):
            call_command("create_install_accounts", "--password", "x", stdout=StringIO())

    def test_no_hardcoded_credentials_in_tooling_sources(self):
        root = Path(__file__).resolve().parents[3]
        needles = ("password=\"", "password = \"")
        for path in list((root / "apps/stores/services/demo_bundle").glob("*.py")) + [
            root / "apps/stores/management/commands/create_install_accounts.py"
        ]:
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                self.assertNotIn(needle, text, f"{path.name} contains a literal password assignment")


@override_settings(ALLOWED_HOSTS=HOSTS, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class HostAndRoleTests(TestCase):
    """Platform admin host, central login host and per-store admin hosts."""

    def setUp(self):
        cache.clear()
        self.v5 = self._store(TARGET_V5)
        self.arch = self._store(TARGET_ARCH)
        accounts.ensure_accounts(
            platform_owner_password=STRONG, shops_admin_password=STRONG + "x",
            store_slugs=["demo-v5", "demo-arch02"],
        )

    def _store(self, target):
        store = Store.objects.create(
            name=target.name, slug=target.slug, admin_subdomain=target.admin_subdomain,
            status=Store.Status.ACTIVE, onboarding_completed_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=store, hostname=target.hostname, is_primary=True,
            domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)
        return store

    def test_platform_admin_login_page_is_on_its_own_host(self):
        r = Client().get("/login/", HTTP_HOST="platformadmins.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "portal/platform_admin/login.html")

    def test_platform_owner_can_log_in_to_platform_admin(self):
        c = Client()
        r = c.post("/login/", {"identifier": "platform_owner", "password": STRONG},
                   HTTP_HOST="platformadmins.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/", HTTP_HOST="platformadmins.rastisi.ir", secure=True).status_code, 200)

    def test_shops_admin_cannot_log_in_to_platform_admin(self):
        c = Client()
        r = c.post("/login/", {"identifier": "shops_admin", "password": STRONG + "x"},
                   HTTP_HOST="platformadmins.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", c.session)
        self.assertEqual(c.get("/", HTTP_HOST="platformadmins.rastisi.ir", secure=True).status_code, 302)

    def test_wrong_password_is_rejected_on_platform_admin(self):
        r = Client().post("/login/", {"identifier": "platform_owner", "password": "wrong"},
                          HTTP_HOST="platformadmins.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 200)

    def test_platform_admin_login_is_not_served_by_store_hosts(self):
        # /login/ is the platform-admin form only on platformadmins.rastisi.ir
        r = Client().get("/login/", HTTP_HOST="demo-v5.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 404)

    def test_django_admin_is_not_served_on_the_platform_admin_host(self):
        r = Client().get("/admin/", HTTP_HOST="platformadmins.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 404)

    def test_central_login_page_renders_on_rastisi_ir(self):
        r = Client().get("/login/", HTTP_HOST="rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 200)

    def test_shops_admin_authenticates_through_central_identity(self):
        from django.test import RequestFactory

        from apps.portal.services import owner_auth_service

        user = owner_auth_service.authenticate_owner_by_identifier(
            RequestFactory().post("/login/password/"), identifier="shops_admin", password=STRONG + "x",
        )
        self.assertIsNotNone(user)

    def test_shops_admin_reaches_both_store_admin_panels(self):
        admin = User.objects.get(username="shops_admin")
        for host in ("demo-v5.rastisi.ir", "demo-arch02.rastisi.ir"):
            c = Client()
            c.force_login(admin)
            r = c.get("/admin-portal/", HTTP_HOST=host, secure=True)
            self.assertEqual(r.status_code, 200, host)

    def test_platform_owner_without_membership_gets_no_store_panel(self):
        c = Client()
        c.force_login(User.objects.get(username="platform_owner"))
        r = c.get("/admin-portal/", HTTP_HOST="demo-v5.rastisi.ir", secure=True)
        self.assertNotEqual(r.status_code, 200)

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def test_anonymous_admin_portal_redirects_to_central_login(self):
        r = Client().get("/admin-portal/", HTTP_HOST="demo-v5.rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])
        self.assertTrue(r["Location"].startswith("https://rastisi.ir/login/"), r["Location"])

    def test_enter_admin_hands_off_to_the_stores_own_host(self):
        admin = User.objects.get(username="shops_admin")
        c = Client()
        c.force_login(admin)
        r = c.post(f"/app/stores/{self.v5.public_id}/enter-admin/", HTTP_HOST="rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 302, getattr(r, "content", b"")[:200])
        self.assertTrue(r["Location"].startswith("https://demo-v5.rastisi.ir/admin-portal/handoff/"), r["Location"])

    def test_enter_admin_for_unowned_store_is_404(self):
        outsider = User.objects.create_user("outsider", password=STRONG)
        c = Client()
        c.force_login(outsider)
        r = c.post(f"/app/stores/{self.v5.public_id}/enter-admin/", HTTP_HOST="rastisi.ir", secure=True)
        self.assertEqual(r.status_code, 404)
