"""Media recovery: files a source ZIP lacks are rebuilt from the repo / application code
with recorded provenance - or stay missing (and BLOCK the build).

Fixture data is generated; the only real inputs are the repository's own curated assets.
"""

import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.utils.text import slugify
from PIL import Image

from apps.catalog.models import Brand, Category, Product, ProductImage, Vendor
from apps.catalog.services import product_image_service as svc
from apps.content.models import DestinationType, HeroSlide, StoryRailItem
from apps.core.models import ShopSettings
from apps.stores.services.demo_bundle import integrity, media_recovery as mr
from apps.stores.services.demo_bundle.converter import ConvertOptions, SourceSpec, convert
from apps.stores.services.demo_bundle.importer import import_store
from apps.stores.services.demo_bundle.report import BLOCKED, PASS
from apps.stores.tests import bundle_fixtures as fx
from apps.stores.tests.test_demo_bundle_converter import HOSTS, TARGET_ARCH, TARGET_V5, TARGETS

CURATED = mr.default_curated_dir()
RUNNING = "کتانی رانینگ"
CASUAL = "کتانی کژوال"


def curated_bytes(rel):
    return (CURATED / rel).read_bytes()


def photo_webp(size=(1200, 1600), seed=1):
    """A deterministic non-trivial picture (gradient + stripes) as WebP."""
    image = Image.new("RGB", size)
    px = image.load()
    for x in range(0, size[0], 7):
        for y in range(0, size[1], 7):
            px[x, y] = ((x * seed) % 255, (y * 3) % 255, ((x + y) * 5) % 255)
    buf = io.BytesIO()
    image.save(buf, format="WEBP", quality=80)
    return buf.getvalue()


def add_real_image(product, *, size=(1200, 1600), seed=1, ext="webp"):
    data = photo_webp(size, seed)
    return svc.add_product_image(product, SimpleUploadedFile(f"src-{seed}.{ext}", data, content_type=f"image/{ext}"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed_module():
    import importlib

    return importlib.import_module("apps.stores.management.commands.seed_ready_template_fashion_demo")


def build_v5_like(slug, count=4, extra_images=0):
    """seed-style store: composite category covers (``category-<slug>.jpg``) + real product images."""
    seed = seed_module()
    store = fx.build_rich_store(slug, color="#aa0000", product_count=count)
    vendor, brand = Vendor.objects.get(store=store), Brand.objects.get(store=store)
    for sku, name in (("FSH-001", RUNNING), ("FSH-006", CASUAL)):
        cat = Category.objects.create(store=store, name=name, slug=slugify(name, allow_unicode=True))
        product = Product.objects.create(store=store, vendor=vendor, category=cat, brand=brand, name=f"{name} {sku}",
                                         slug=f"{sku.lower()}-{slug}", sku=sku, price=1000, stock=5)
        row = next(r for r in seed.PRODUCT_MATRIX if r[0] == sku)
        colors = row[6] if isinstance(row[6], tuple) else (row[6],)
        data = seed._composite_visual_bytes(
            width=800, height=600, product_paths=[seed.PRODUCT_MEDIA_DIR / sku / "01.webp"],
            bg_hex=seed.COLOR_HEX.get(colors[0], seed._FALLBACK_COLOR_HEX))
        cat.image.save(f"category-{cat.slug}.jpg", ContentFile(data), save=False)
        cat.save()
        add_real_image(product, seed=3)
    for index, product in enumerate(Product.objects.filter(store=store).order_by("pk")[:extra_images or 0]):
        add_real_image(product, size=(90, 120), seed=index + 5)
    return store


def build_arch_like(slug, count=5, extra_images=0):
    """refresh_rasti_mode_demo_visuals-style store (curated assets under their upload names) + a hand-made category."""
    store = fx.build_rich_store(slug, color="#0000bb", product_count=count)
    vendor = Vendor.objects.get(store=store)
    brand_names = json.loads((CURATED / "manifest.json").read_text(encoding="utf-8"))
    manifest = brand_names
    shop = ShopSettings.objects.get(store=store)
    shop.logo.save("rasti-mode-demo-logo.png", ContentFile(curated_bytes(manifest["branding"]["logo"])), save=False)
    shop.favicon.save("rasti-mode-demo-favicon.png", ContentFile(curated_bytes(manifest["branding"]["favicon"])), save=False)
    shop.save()
    cats = {}
    for name, rel in manifest["categories"].items():
        cat = Category.objects.create(store=store, name=name, slug=slugify(name, allow_unicode=True))
        cat.image.save(f"rasti-{cat.slug}.webp", ContentFile(curated_bytes(rel)), save=False)
        cat.save()
        cats[name] = cat
    for name, rel in manifest["brands"].items():
        brand = Brand.objects.create(store=store, name=name, slug=slugify(name))
        brand.logo.save(f"rasti-{brand.slug}.webp", ContentFile(curated_bytes(rel)), save=False)
        brand.save()
    for hero in manifest["heroes"]:
        order = hero["order"]
        slide = HeroSlide(store=store, title=hero["title"], display_order=order, is_active=True,
                          destination_type=DestinationType.SEARCH)
        slide.desktop_image.save(f"rasti-curated-hero-{order + 1}.webp", ContentFile(curated_bytes(hero["desktop"])), save=False)
        slide.mobile_image.save(f"rasti-curated-hero-{order + 1}-mobile.webp", ContentFile(curated_bytes(hero["mobile"])), save=False)
        slide.save()
    for order, (name, rel) in enumerate(manifest["categories"].items()):
        item = StoryRailItem(store=store, title=name[:60], display_order=order, is_active=True,
                             destination_type=DestinationType.CATEGORY, destination_category=cats[name])
        item.image.save(f"rasti-curated-story-{order + 1}.webp", ContentFile(curated_bytes(rel)), save=False)
        item.save()
    kafsh = Category.objects.create(store=store, name="کفش", slug="kafsh")
    kafsh.image.save("kafsh.jpg", ContentFile(photo_webp((300, 300), 9)), save=False)  # hand-uploaded: not in Git
    kafsh.save()
    product = Product.objects.filter(store=store).order_by("pk").first()
    add_real_image(product, seed=7)
    for index, other in enumerate(Product.objects.filter(store=store).order_by("pk")[:extra_images]):
        add_real_image(other, size=(90, 120), seed=index + 11)
    return store


def strip_derived(media_root, lost):
    """Remove from the MEDIA_ROOT everything a real export would have lacked; ``lost[rel] = bytes``."""
    for path in sorted(Path(media_root).rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(media_root).as_posix()
        if rel.startswith("products/thumbnails/") or rel.startswith("categories/images/") \
                or rel.startswith(("brands/logos/", "homepage/hero/", "storyrail/")) \
                or rel.startswith("shop/branding/rasti-mode-demo-"):
            lost[rel] = path.read_bytes()
            path.unlink()


@unittest.skipUnless(connection.vendor == "sqlite", "source databases are built by dumping the SQLite test database")
@override_settings(ALLOWED_HOSTS=HOSTS, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir")
class RecoveryBase(TestCase):
    scale = False

    @classmethod
    def setUpTestData(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="recov-tests-"))
        cls.media_a, cls.media_b = cls.root / "media_a", cls.root / "media_b"
        cls.media_a.mkdir()
        cls.media_b.mkdir()
        cls.sqlite_a, cls.sqlite_b = cls.root / "demo_v5.sqlite3", cls.root / "demo_arch02.sqlite3"
        cls.lost_a, cls.lost_b = {}, {}
        n = 50 if cls.scale else 4
        with override_settings(MEDIA_ROOT=str(cls.media_a)):
            fx.build_source_sqlite(cls.sqlite_a, cls.media_a, lambda: build_v5_like("alpha", n, extra_images=n - 2 if cls.scale else 0))
        with override_settings(MEDIA_ROOT=str(cls.media_b)):
            fx.build_source_sqlite(cls.sqlite_b, cls.media_b, lambda: build_arch_like("beta", n if cls.scale else 5, extra_images=n if cls.scale else 0))
        strip_derived(cls.media_a, cls.lost_a)
        strip_derived(cls.media_b, cls.lost_b)
        cls.zip_a, cls.zip_b = cls.root / "demo_v5_media.zip", cls.root / "demo_arch02_media.zip"
        fx.zip_media(cls.media_a, cls.zip_a, wrapper="media")
        fx.zip_media(cls.media_b, cls.zip_b, wrapper="demo_arch02_media/media", backslashes=True)
        cls.hashes_before = {p.name: sha(p) for p in (cls.sqlite_a, cls.sqlite_b, cls.zip_a, cls.zip_b)}
        cls.kafsh = "categories/images/kafsh.jpg"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.work = Path(tempfile.mkdtemp(prefix="recov-work-"))
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.out = self.work / "bundle"
        self.extra = self.work / "extra"
        (self.extra / "categories" / "images").mkdir(parents=True)
        (self.extra / self.kafsh).write_bytes(self.lost_b[self.kafsh])  # the operator's own file

    def run_convert(self, *, with_extra=True, **opts):
        specs = [SourceSpec("demo_v5", self.sqlite_a, self.zip_a), SourceSpec("demo_arch02", self.sqlite_b, self.zip_b)]
        if with_extra:
            opts.setdefault("extra_media_dir", self.extra)
        return convert(specs, self.out, targets=TARGETS, options=ConvertOptions(**opts), work_dir=self.work / "w")

    def prov(self, result, key):
        return {item["path"]: item for item in result.provenance[key]}


class ThumbnailRecoveryTests(RecoveryBase):
    def test_thumbnails_are_regenerated_with_the_application_logic_and_exact_db_paths(self):
        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        for key, lost in (("demo_v5", self.lost_a), ("demo_arch02", self.lost_b)):
            prov = self.prov(result, key)
            thumbs = [p for p in lost if p.startswith("products/thumbnails/")]
            self.assertTrue(thumbs)
            for rel in thumbs:
                self.assertEqual(prov[rel]["classification"], mr.REGENERATED_DERIVATIVE, rel)
                self.assertTrue((self.out / "media" / rel).is_file(), f"{rel} must be at the exact path the database stores")

    def test_a_real_upload_gives_a_byte_identical_thumbnail(self):
        """Input = the uploaded original kept by product_image_service -> the very same bytes come out."""
        result = self.run_convert()
        prov = self.prov(result, "demo_v5")
        exact = [p for p in prov.values() if p["classification"] == mr.REGENERATED_DERIVATIVE
                 and p["method"] == "product_image_service.thumbnail" and p["sources"]
                 and p["sources"][0]["path"].startswith("products/originals/")]
        self.assertTrue(exact, "the seed-like images keep their uploaded originals")
        for item in exact:
            self.assertEqual((self.out / "media" / item["path"]).read_bytes(), self.lost_a[item["path"]], item["path"])
            with Image.open(self.out / "media" / item["path"]) as img:
                self.assertEqual(img.size, (300, 400))  # 1200x1600 shrunk to THUMBNAIL_DIMENSION=400
                self.assertEqual(img.format, "WEBP")

    def test_thumbnail_extension_is_kept_even_if_the_source_format_differs(self):
        env = mr.RecoveryEnv(
            read_zip=lambda rel: photo_webp((500, 500), 2) if rel == "products/gallery/p.webp" else None,
            find_in_zip_elsewhere=lambda rel: [], records=[
                {"model": "catalog.productimage", "pk": 1, "fields": {"image": "products/gallery/p.webp"}}],
            curated_dir=CURATED)
        got = mr.recover_one(env, "products/thumbnails/p-thumb.jpg", "catalog.ProductImage", 1, "thumbnail")
        self.assertEqual(got.classification, mr.REGENERATED_DERIVATIVE)
        with Image.open(io.BytesIO(got.data)) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(max(img.size), svc.THUMBNAIL_DIMENSION)
        self.assertIn("encoded as JPEG", got.note)

    def test_thumbnail_without_any_source_image_is_unrecoverable(self):
        env = mr.RecoveryEnv(read_zip=lambda rel: None, find_in_zip_elsewhere=lambda rel: [], records=[
            {"model": "catalog.productimage", "pk": 1, "fields": {"image": "products/gallery/p.webp"}}], curated_dir=CURATED)
        got = mr.recover_one(env, "products/thumbnails/p-thumb.webp", "catalog.ProductImage", 1, "thumbnail")
        self.assertIsInstance(got, str)
        self.assertIn("neither", got)

    def test_undecodable_source_is_unrecoverable_not_a_placeholder(self):
        env = mr.RecoveryEnv(read_zip=lambda rel: b"not an image", find_in_zip_elsewhere=lambda rel: [], records=[
            {"model": "catalog.productimage", "pk": 1, "fields": {"image": "products/gallery/p.webp"}}], curated_dir=CURATED)
        self.assertIsInstance(mr.recover_one(env, "products/thumbnails/p-thumb.webp", "catalog.ProductImage", 1, "thumbnail"), str)


class CuratedRecoveryTests(RecoveryBase):
    def test_every_curated_kind_is_recovered_byte_identically_with_its_repo_source(self):
        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        prov = self.prov(result, "demo_arch02")
        manifest = json.loads((CURATED / "manifest.json").read_text(encoding="utf-8"))
        sums = mr.RecoveryEnv(None, None, [], CURATED).curated_sums()
        from_repo = [p for p in prov.values() if p["classification"] == mr.RECOVERED_FROM_REPO]
        # 10 categories + 6 brands + 8 hero images + 10 story items + logo + favicon
        self.assertEqual(len(from_repo), 10 + 6 + 8 + 10 + 2, sorted(p["path"] for p in from_repo))
        for item in from_repo:
            source = item["sources"][0]
            self.assertEqual(source["kind"], "repo")
            rel = source["path"].split("curated/", 1)[1]
            self.assertEqual(source["sha256"], sums[rel], "recorded source must be the checksum-verified repo asset")
            self.assertEqual(item["sha256"], source["sha256"])
            self.assertEqual((self.out / "media" / item["path"]).read_bytes(), self.lost_b[item["path"]], item["path"])
            self.assertTrue(item["evidence"])
        kinds = {p["models"][0]["model"].lower() for p in from_repo}
        self.assertEqual(kinds, {"catalog.category", "catalog.brand", "content.heroslide", "content.storyrailitem", "core.shopsettings"})
        self.assertEqual(len(manifest["brands"]), 6)

    def test_checksum_mismatch_in_the_repo_asset_refuses_recovery(self):
        altered = self.work / "curated"
        shutil.copytree(CURATED, altered)
        (altered / "branding" / "favicon.png").write_bytes(b"tampered")
        result = self.run_convert(curated_dir=altered)
        self.assertEqual(result.report.status, BLOCKED)
        lost = [p for p in result.provenance["demo_arch02"] if p["classification"] == mr.UNRECOVERABLE]
        self.assertEqual([p["path"] for p in lost], ["shop/branding/rasti-mode-demo-favicon.png"])
        self.assertIn("SHA256SUMS", lost[0]["note"])

    def test_a_name_the_refresh_command_would_not_have_produced_is_not_recovered(self):
        env = mr.RecoveryEnv(read_zip=lambda r: None, find_in_zip_elsewhere=lambda r: [], curated_dir=CURATED, records=[
            {"model": "catalog.category", "pk": 1, "fields": {"name": RUNNING, "slug": slugify(RUNNING, allow_unicode=True)}},
            {"model": "core.shopsettings", "pk": 1, "fields": {}}])
        # right category, wrong file name -> could be anything the owner uploaded
        got = mr.recover_one(env, "categories/images/my-own-photo.webp", "catalog.Category", 1, "image")
        self.assertIsInstance(got, str)
        self.assertIsInstance(mr.recover_one(env, "shop/branding/other-logo.png", "core.ShopSettings", 1, "logo"), str)
        # django's collision suffix is tolerated
        ok = mr.recover_one(env, "shop/branding/rasti-mode-demo-logo_AbC1234.png", "core.ShopSettings", 1, "logo")
        self.assertEqual(ok.classification, mr.RECOVERED_FROM_REPO)

    def test_format_mismatch_is_transcoded_kept_at_the_db_path_and_not_called_a_repo_copy(self):
        env = mr.RecoveryEnv(read_zip=lambda r: None, find_in_zip_elsewhere=lambda r: [], curated_dir=CURATED, records=[
            {"model": "catalog.category", "pk": 1, "fields": {"name": RUNNING, "slug": "x"}}])
        got = mr.recover_one(env, "categories/images/rasti-x.jpg", "catalog.Category", 1, "image")
        self.assertEqual((got.classification, got.method), (mr.REGENERATED_DERIVATIVE, "transcode_repo_asset"))
        with Image.open(io.BytesIO(got.data)) as img:
            self.assertEqual(img.format, "JPEG")


class SeedCompositeTests(RecoveryBase):
    def test_v5_category_covers_are_rebuilt_from_the_committed_product_photos(self):
        result = self.run_convert()
        prov = self.prov(result, "demo_v5")
        covers = [p for p in prov.values() if p["models"][0]["model"].lower() == "catalog.category"
                  and p["classification"] != mr.ORIGINAL]
        self.assertEqual(len(covers), 2)
        for item in covers:
            self.assertEqual(item["classification"], mr.REGENERATED_DERIVATIVE)
            self.assertEqual(item["method"], "seed_composite")
            self.assertTrue(item["sources"][0]["path"].endswith("/01.webp"))
            self.assertEqual((self.out / "media" / item["path"]).read_bytes(), self.lost_a[item["path"]])
            with Image.open(self.out / "media" / item["path"]) as img:
                self.assertEqual((img.format, img.size), ("JPEG", (800, 600)))

    def test_cover_needs_the_seed_product_in_that_category(self):
        seed = seed_module()
        recs = [{"model": "catalog.category", "pk": 1, "fields": {"name": RUNNING, "slug": "s"}}]
        env = mr.RecoveryEnv(read_zip=lambda r: None, find_in_zip_elsewhere=lambda r: [], curated_dir=CURATED, records=recs)
        got = mr.recover_one(env, "categories/images/category-s.jpg", "catalog.Category", 1, "image")
        self.assertIsInstance(got, str)
        self.assertIn("FSH-001", got)
        recs.append({"model": "catalog.product", "pk": 5, "fields": {"sku": "FSH-001", "category": 1}})
        env = mr.RecoveryEnv(read_zip=lambda r: None, find_in_zip_elsewhere=lambda r: [], curated_dir=CURATED, records=recs)
        self.assertEqual(mr.recover_one(env, "categories/images/category-s.jpg", "catalog.Category", 1, "image").method, "seed_composite")
        self.assertTrue(seed.PRODUCT_MATRIX)


class UnrecoverableTests(RecoveryBase):
    def test_kafsh_is_unrecoverable_and_no_stand_in_is_used(self):
        result = self.run_convert(with_extra=False)
        self.assertEqual(result.report.status, BLOCKED, result.report.to_text())
        self.assertFalse(self.out.exists(), "an UNRECOVERABLE file must stop the build")
        lost = [p for p in result.provenance["demo_arch02"] if p["classification"] == mr.UNRECOVERABLE]
        self.assertEqual([p["path"] for p in lost], [self.kafsh])
        self.assertIn("not in Git", lost[0]["note"])
        codes = [f.code for f in result.report.findings]
        self.assertIn("media.unrecoverable", codes)
        self.assertIn("media.missing_at_export", codes, "the validator must stay enabled")
        self.assertEqual([p for p in result.provenance["demo_v5"] if p["classification"] == mr.UNRECOVERABLE], [])

    def test_extra_media_dir_supplies_the_original_and_is_recorded_as_such(self):
        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        item = self.prov(result, "demo_arch02")[self.kafsh]
        self.assertEqual((item["classification"], item["method"]), (mr.ORIGINAL, "operator_supplied"))
        self.assertEqual((self.out / "media" / self.kafsh).read_bytes(), self.lost_b[self.kafsh])

    def test_same_name_file_under_another_folder_of_the_zip_is_an_original(self):
        import zipfile

        moved = self.work / "b_moved.zip"
        with zipfile.ZipFile(self.zip_b) as src, zipfile.ZipFile(moved, "w") as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info))
            dst.writestr("demo_arch02_media/media/old-uploads/kafsh.jpg", self.lost_b[self.kafsh])
        specs = [SourceSpec("demo_v5", self.sqlite_a, self.zip_a), SourceSpec("demo_arch02", self.sqlite_b, moved)]
        result = convert(specs, self.out, targets=TARGETS, options=ConvertOptions(), work_dir=self.work / "w")
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        item = self.prov(result, "demo_arch02")[self.kafsh]
        self.assertEqual((item["classification"], item["method"]), (mr.ORIGINAL, "zip_other_path"))

    def test_recovery_can_be_switched_off_and_everything_stays_blocked(self):
        result = self.run_convert(recover_media=False)
        self.assertEqual(result.report.status, BLOCKED)
        self.assertEqual(
            len([p for p in result.provenance["demo_arch02"] if p["classification"] == mr.UNRECOVERABLE]),
            len(self.lost_b))
        self.assertFalse(self.out.exists())

    def test_provenance_report_is_written_even_when_the_build_is_refused(self):
        from django.core.management import call_command

        provenance = self.work / "prov.json"
        with self.assertRaises(SystemExit) as ctx:
            call_command("build_demo_bundle", "--v5-sqlite", str(self.sqlite_a), "--v5-media-zip", str(self.zip_a),
                         "--arch02-sqlite", str(self.sqlite_b), "--arch02-media-zip", str(self.zip_b),
                         "--out", str(self.out), "--work-dir", str(self.work / "cmd"), "--no-full-check",
                         "--provenance-report", str(provenance), stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 2)
        self.assertFalse(self.out.exists())
        doc = json.loads(provenance.read_text(encoding="utf-8"))
        self.assertEqual(doc["sources"]["demo_arch02"]["counts"][mr.UNRECOVERABLE], 1)


class ProvenanceAndInputsTests(RecoveryBase):
    def test_every_referenced_file_is_classified_and_counts_add_up(self):
        result = self.run_convert()
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        document = json.loads((self.out / "MEDIA_PROVENANCE.json").read_text(encoding="utf-8"))
        for key, entry in manifest["stores"].items():
            counts = entry["conversion"]["media"]["provenance_counts"]
            files = document["sources"][key]["files"]
            self.assertEqual(sum(counts.values()), len(files))
            self.assertEqual({f["classification"] for f in files} - set(mr.CLASSES), set())
            self.assertEqual(entry["missing_media"], [])
            for f in files:
                self.assertTrue(f["models"], f["path"])
                if f["classification"] != mr.UNRECOVERABLE:
                    self.assertTrue(f["sha256"])
        self.assertGreater(counts[mr.ORIGINAL], 0)
        text = result.report.to_text(show_pass=True)
        self.assertIn("media.regenerated_derivative", text)
        self.assertIn("media.recovered_from_repo", text)

    def test_inputs_are_never_modified(self):
        self.run_convert()
        self.assertEqual({p.name: sha(p) for p in (self.sqlite_a, self.sqlite_b, self.zip_a, self.zip_b)}, self.hashes_before)
        self.assertEqual(sha(self.extra / self.kafsh), hashlib.sha256(self.lost_b[self.kafsh]).hexdigest())

    def test_recovered_media_exist_only_in_the_temp_staging_until_the_build_passes(self):
        result = self.run_convert(with_extra=False)
        self.assertEqual(result.report.status, BLOCKED)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.out / "media").exists())
        self.assertFalse(list(self.zip_a.parent.glob("**/*.partial")))

    def test_inspect_only_reports_what_is_recoverable_and_writes_nothing(self):
        result = self.run_convert(inspect_only=True, with_extra=False)
        text = result.report.to_text(show_pass=True)
        self.assertIn("recoverable", text)
        self.assertIn("REGENERATED_DERIVATIVE=", text)
        self.assertIn("RECOVERED_FROM_REPO=", text)
        self.assertFalse(self.out.exists())

    def test_bundle_is_deterministic(self):
        first = self.run_convert()
        digest = {p.relative_to(self.out).as_posix(): sha(p) for p in sorted(self.out.rglob("*")) if p.is_file()
                  and not p.name.startswith("manifest")}
        shutil.rmtree(self.out)
        again = self.run_convert()
        self.assertEqual(first.report.status, again.report.status)
        self.assertEqual(digest, {p.relative_to(self.out).as_posix(): sha(p) for p in sorted(self.out.rglob("*")) if p.is_file()
                                  and not p.name.startswith("manifest")})


class ImportAndRenderTests(RecoveryBase):
    def setUp(self):
        super().setUp()
        self.dst_media = self.work / "dst_media"
        self.dst_media.mkdir()
        self.result = self.run_convert()
        self.assertEqual(self.result.report.status, PASS, self.result.report.to_text())
        override = override_settings(MEDIA_ROOT=str(self.dst_media))
        override.enable()
        self.addCleanup(override.disable)
        self.v5 = import_store(self.out, "demo_v5", TARGET_V5, media_root=self.dst_media).store
        self.arch = import_store(self.out, "demo_arch02", TARGET_ARCH, media_root=self.dst_media).store

    def test_integrity_with_http_passes_for_both_stores_after_recovery(self):
        for store, target in ((self.v5, TARGET_V5), (self.arch, TARGET_ARCH)):
            report = integrity.verify_store(store, hostname=target.hostname, media_root=self.dst_media, http=True)
            self.assertEqual(report.status, PASS, report.to_text())

    def test_every_thumbnail_and_curated_file_is_on_disk_and_decodes(self):
        names = [i.thumbnail.name for i in ProductImage.objects.filter(product__store__in=[self.v5, self.arch]) if i.thumbnail]
        self.assertGreaterEqual(len(names), 20)
        for name in names:
            with Image.open(self.dst_media / name) as img:
                img.verify()
        for model, field in ((Category, "image"), (Brand, "logo"), (HeroSlide, "desktop_image"), (HeroSlide, "mobile_image"),
                             (StoryRailItem, "image")):
            for obj in model.objects.filter(store=self.arch):
                value = getattr(obj, field)
                if value:
                    with Image.open(self.dst_media / value.name) as img:
                        img.verify()

    def test_product_page_and_storefront_serve_the_recovered_images(self):
        client = Client()
        product = Product.objects.filter(store=self.v5, images__isnull=False).order_by("pk").first()
        thumb_url = product.images.first().thumbnail.url
        page = client.get(f"/products/{product.slug}/", HTTP_HOST="demo-v5.rastisi.ir", secure=True)
        self.assertEqual(page.status_code, 200)
        home = client.get("/", HTTP_HOST="demo-v5.rastisi.ir", secure=True).content.decode()
        self.assertIn("from collection", home)  # Studio published page still renders
        self.assertTrue(thumb_url.startswith("/media/products/thumbnails/"))
        self.assertTrue((self.dst_media / thumb_url.removeprefix("/media/")).is_file())
        arch_home = client.get("/", HTTP_HOST="demo-arch02.rastisi.ir", secure=True)
        self.assertEqual(arch_home.status_code, 200)

    def test_studio_pages_of_both_stores_render_with_recovered_media(self):
        client = Client()
        for host in ("demo-v5.rastisi.ir", "demo-arch02.rastisi.ir"):
            for path in ("/", "/products/"):
                response = client.get(path, HTTP_HOST=host, secure=True)
                self.assertLess(response.status_code, 400, f"{host}{path}")

    def test_import_is_idempotent_with_recovered_media(self):
        before = sorted(str(p.relative_to(self.dst_media)) for p in self.dst_media.rglob("*") if p.is_file())
        import_store(self.out, "demo_v5", TARGET_V5, media_root=self.dst_media)
        import_store(self.out, "demo_arch02", TARGET_ARCH, media_root=self.dst_media)
        self.assertEqual(before, sorted(str(p.relative_to(self.dst_media)) for p in self.dst_media.rglob("*") if p.is_file()))


class ScaleTests(RecoveryBase):
    scale = True

    def test_301_missing_thumbnails_are_all_regenerated(self):
        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        counts = {}
        for key in ("demo_v5", "demo_arch02"):
            counts[key] = sum(1 for p in result.provenance[key]
                              if p["classification"] == mr.REGENERATED_DERIVATIVE and p["method"] == "product_image_service.thumbnail")
        self.assertEqual(counts, {"demo_v5": 150, "demo_arch02": 151})
        self.assertEqual(sum(counts.values()), 301)
        for key in counts:
            self.assertEqual(result.provenance[key] and [p for p in result.provenance[key]
                                                         if p["classification"] == mr.UNRECOVERABLE], [])


class WindowsCompatibilityTests(RecoveryBase):
    def test_recovery_runs_with_the_windows_path_and_encoding_rules(self):
        """Windows opens files through ``long_path`` (``\\\\?\\``) and CP1252/CP437 consoles must not crash the report."""
        from apps.stores.services.demo_bundle import converter, files

        seen = []
        real = files.long_path

        def fake_nt(path):
            seen.append(str(path))
            return real(path)

        with mock.patch.object(converter, "long_path", side_effect=fake_nt):
            result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        self.assertTrue(seen, "recovered files must be written through long_path (the Windows MAX_PATH guard)")
        text = result.report.to_text(show_pass=True)
        text.encode("cp1252", errors="replace")  # the report must be printable on a legacy console
        doc = (self.out / "MEDIA_PROVENANCE.json").read_text(encoding="utf-8")
        self.assertIn(mr.RECOVERED_FROM_REPO, doc)
        for item in json.loads(doc)["sources"]["demo_arch02"]["files"]:
            self.assertNotIn("\\", item["path"], "database paths are always POSIX, also on Windows")
            for source in item["sources"]:
                self.assertNotIn("\\", source["path"])

    def test_persian_names_and_backslash_zip_members_are_recovered(self):
        # the arch fixture ZIP was written with ``\\`` separators and a Persian category name in its database
        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        names = [p["models"][0] for p in result.provenance["demo_arch02"] if p["classification"] == mr.RECOVERED_FROM_REPO]
        self.assertTrue(any(m["model"].lower() == "catalog.category" for m in names))

    def test_windows_build_command_forwards_the_new_switches(self):
        script = Path(__file__).resolve().parents[3] / "rebuild" / "windows" / "build_demo_bundle.ps1"
        self.assertTrue(script.is_file())
        self.assertIn("ExtraMediaDir", script.read_text(encoding="utf-8"))
        bat = (script.with_suffix(".bat")).read_text(encoding="utf-8", errors="replace")
        self.assertIn("build_demo_bundle", bat.replace("_", "_"))
        self.assertTrue(os.path.isdir(CURATED))


class EndToEndTests(RecoveryBase):
    def test_full_scratch_check_passes_on_a_bundle_made_of_recovered_media(self):
        """Fresh scratch DB, import x2, HTTP, and source-vs-import page equivalence - with recovery in the bundle."""
        from apps.stores.services.demo_bundle.fullcheck import run_full_check

        result = self.run_convert()
        self.assertEqual(result.report.status, PASS, result.report.to_text())
        report = run_full_check(self.out, TARGETS, result.sources, result.stride, result.offsets, self.work)
        self.assertEqual(report.status, PASS, report.to_text())

    def test_command_builds_the_bundle_and_writes_provenance_beside_it(self):
        from django.core.management import call_command

        out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("build_demo_bundle", "--v5-sqlite", str(self.sqlite_a), "--v5-media-zip", str(self.zip_a),
                         "--arch02-sqlite", str(self.sqlite_b), "--arch02-media-zip", str(self.zip_b),
                         "--out", str(self.out), "--work-dir", str(self.work / "cmd"), "--no-full-check",
                         "--extra-media-dir", str(self.extra), stdout=out, stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 0, out.getvalue())
        self.assertIn("BUNDLE READY", out.getvalue())
        beside = self.out.with_name(self.out.name + ".media_provenance.json")
        self.assertTrue(beside.is_file())
        self.assertEqual(json.loads(beside.read_text(encoding="utf-8")), json.loads((self.out / "MEDIA_PROVENANCE.json").read_text(encoding="utf-8")))
