"""Post-import integrity verification of a live store (database + media + HTTP).

``verify_store`` is read-only. It never repairs anything: a finding is a
statement of fact about the current database, so an operator can trust it.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db.models import Q

from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

from . import contract
from .exporter import _store_q, rows_for
from .files import file_fields, model_for
from .report import Report


def verify_store(store: Store, *, hostname: str | None = None, media_root: Path | None = None,
                 decode_images: bool = True, http: bool = False) -> Report:
    media_root = Path(media_root or settings.MEDIA_ROOT)
    report = Report(f"integrity {store.slug}")
    s = store.slug

    _check_identity(store, hostname, report)
    _check_singletons(store, report)
    _check_files(store, media_root, decode_images, report)
    _check_cross_store(store, report)
    _check_studio(store, report)
    _check_products(store, report)
    if http:
        _check_http(store, hostname, report)
    return report


def _check_identity(store, hostname, report):
    s = store.slug
    if store.status != Store.Status.ACTIVE:
        report.fail("store.status", f"status is {store.status}", s)
    else:
        report.ok("store.status", "active", s)
    if store.onboarding_completed_at is None and store.onboarding_required_at is not None:
        report.fail("store.private", "store is still private (onboarding not completed)", s)
    domains = StoreDomain.objects.filter(store=store)
    if hostname:
        d = domains.filter(hostname=hostname).first()
        if d is None:
            report.fail("domain.missing", f"no StoreDomain {hostname}", s)
        elif d.verification_status != StoreDomain.VerificationStatus.VERIFIED or d.retired_at:
            report.fail("domain.state", f"{hostname} is not verified/active", s)
        else:
            report.ok("domain", f"{hostname} verified", s)


def _check_singletons(store, report):
    s = store.slug
    for model in (ShopSettings, FooterSettings):
        n = model.objects.filter(store=store).count()
        if n == 1:
            report.ok("singleton", f"exactly one {model.__name__}", s)
        else:
            report.fail("singleton", f"{n} {model.__name__} rows (expected exactly 1)", s)


def _check_files(store, media_root, decode_images, report):
    s = store.slug
    total = bad = 0
    for spec in contract.MODEL_SPECS:
        model = model_for(spec.label)
        fields = file_fields(model)
        if not fields:
            continue
        for obj in rows_for(spec, store):
            for field in fields:
                name = getattr(obj, field.name).name if getattr(obj, field.name) else ""
                if not name:
                    continue
                total += 1
                path = media_root / name
                if not path.is_file():
                    bad += 1
                    if bad <= 25:
                        report.fail("file.missing", f"{spec.label} pk={obj.pk}.{field.name} -> {name} not on disk", s)
                elif path.stat().st_size == 0:
                    bad += 1
                    report.fail("file.empty", f"{name} is empty", s)
                elif decode_images and name.lower().rsplit(".", 1)[-1] in {"jpg", "jpeg", "png", "webp", "gif"}:
                    try:
                        from PIL import Image

                        with Image.open(path) as img:
                            img.verify()
                    except Exception as exc:  # noqa: BLE001
                        bad += 1
                        report.fail("file.undecodable", f"{name}: {exc}", s)
    if bad:
        report.fail("files.total", f"{bad} of {total} file reference(s) are broken", s)
    else:
        report.ok("files", f"{total} file reference(s) exist and decode", s)


def _check_cross_store(store, report):
    """No foreign key of this store's rows may point at a row of another store."""
    s = store.slug
    broken = 0
    for spec in contract.MODEL_SPECS:
        model = model_for(spec.label)
        mine = rows_for(spec, store)
        for field in model._meta.concrete_fields:
            if not field.is_relation:
                continue
            target = field.related_model._meta.label
            if target not in contract.SPEC_BY_LABEL:
                continue
            tspec = contract.SPEC_BY_LABEL[target]
            allowed = rows_for(tspec, store).values("pk")
            bad = mine.filter(**{f"{field.name}__isnull": False}).exclude(**{f"{field.name}__in": allowed})
            n = bad.count()
            if n:
                broken += n
                report.fail("tenant.cross_reference", f"{spec.label}.{field.name}: {n} row(s) point outside this store", s)
    if not broken:
        report.ok("tenant.isolation", "no cross-store references", s)


def _check_studio(store, report):
    from apps.storefront_builder.models import StorefrontLayout, StorefrontPage

    s = store.slug
    layout = StorefrontLayout.objects.filter(store=store).select_related("published_version", "draft_version").first()
    if layout is None:
        report.blocked("studio.layout", "no StorefrontLayout (original Studio design absent)", s)
        return
    pv = layout.published_version
    if pv is None:
        report.fail("studio.published", "no published layout version", s)
        return
    if pv.status != "published":
        report.fail("studio.published_status", f"published_version status is {pv.status}", s)
    types = set(StorefrontPage.objects.filter(version=pv).values_list("page_type", flat=True))
    missing = [t for t in contract.REQUIRED_PAGE_TYPES if t not in types]
    if missing:
        report.fail("studio.pages", f"published version lacks pages: {', '.join(missing)}", s)
    else:
        report.ok("studio.pages", f"published v{pv.version_number} has all six page types", s)
    empty = [
        p.page_type for p in StorefrontPage.objects.filter(version=pv)
        if not p.sections.exists()
    ]
    if empty:
        report.warn("studio.empty_pages", f"published pages with no sections: {', '.join(empty)}", s)
    if layout.draft_version_id:
        report.ok("studio.draft", f"draft v{layout.draft_version.version_number} present", s)


def _check_products(store, report):
    from apps.catalog.models import Product, ProductImage

    s = store.slug
    n = Product.objects.filter(store=store).count()
    no_img = Product.objects.filter(store=store).exclude(
        pk__in=ProductImage.objects.filter(product__store=store).values("product_id")
    ).count()
    report.ok("products", f"{n} product(s)", s)
    if no_img:
        report.warn("products.no_image", f"{no_img} product(s) have no image", s)


def _check_http(store, hostname, report):
    """Render the main storefront URLs through the full middleware stack."""
    from django.test import Client

    from apps.catalog.models import Product

    s = store.slug
    if not hostname:
        report.blocked("http.host", "no hostname given; HTTP checks skipped", s)
        return
    client = Client(HTTP_HOST=hostname)
    urls = ["/", "/products/", "/products/?q=a", "/collections/", "/cart/"]
    urls += [f"/products/{slug}/" for slug in Product.objects.filter(store=store).values_list("slug", flat=True)]
    bad = 0
    for url in urls:
        try:
            response = client.get(url, secure=True)
        except Exception as exc:  # noqa: BLE001 - a raised exception is a 500
            bad += 1
            report.fail("http.exception", f"GET {url}: {type(exc).__name__}: {exc}", s)
            continue
        if response.status_code != 200:
            bad += 1
            where = f" -> {response['Location']}" if response.has_header("Location") else ""
            report.fail("http.status", f"GET {url} -> {response.status_code}{where}", s)
    if bad:
        report.fail("http.total", f"{bad} of {len(urls)} URL(s) failed", s)
    else:
        report.ok("http", f"{len(urls)} URL(s) answered 200", s)
