"""Render a store's storefront through the real middleware stack and write one
signature per URL to a JSON file (see ``demo_bundle.signature``).

Used by ``build_demo_bundle`` to compare a SOURCE database with the freshly
imported result. With ``--scratch-copy-confirmed`` it first makes the store
renderable in THIS database (active, onboarding completed, a verified domain for
``--host``); that flag exists only because the converter calls it on a throw-away
snapshot - never use it on a database you care about.
"""

import json
from pathlib import Path
from urllib.parse import quote

from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.demo_bundle.signature import page_signature


class Command(BaseCommand):
    help = "Write per-URL rendering signatures of one store to a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True)
        parser.add_argument("--host", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--offset", type=int, default=0, help="id offset to shift back in attribute/URL contexts")
        parser.add_argument("--stride", type=int, default=1)
        parser.add_argument("--rename-map", default="", help="JSON file {new_media_path: original_media_path}")
        parser.add_argument("--max-products", type=int, default=500)
        parser.add_argument("--scratch-copy-confirmed", action="store_true")

    def handle(self, *args, **opts):
        from apps.catalog.models import Product
        from apps.content.models import ContentPage
        from apps.catalog.models import MerchantCollection

        store = Store.objects.filter(slug=opts["store"]).first()
        if store is None:
            raise CommandError(f"store {opts['store']!r} not found")
        host = opts["host"]
        if opts["scratch_copy_confirmed"]:
            Store.objects.filter(pk=store.pk).update(
                status=Store.Status.ACTIVE, onboarding_completed_at=timezone.now(), onboarding_required_at=None,
            )
            StoreDomain.objects.filter(hostname=host).exclude(store=store).delete()
            domain, _ = StoreDomain.objects.get_or_create(
                store=store, hostname=host,
                defaults={"is_primary": False, "domain_type": StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                          "verification_status": StoreDomain.VerificationStatus.VERIFIED, "verified_at": timezone.now()},
            )
            StoreDomain.objects.filter(pk=domain.pk).update(
                verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(), retired_at=None,
            )
            store.refresh_from_db()

        urls = ["/", "/products/", "/products/?q=a", "/collections/", "/cart/"]
        urls += [f"/products/{quote(slug)}/" for slug in
                 Product.objects.filter(store=store).order_by("pk").values_list("slug", flat=True)[: opts["max_products"]]]
        urls += [f"/collections/{quote(slug)}/" for slug in
                 MerchantCollection.objects.filter(store=store).order_by("pk").values_list("slug", flat=True)]
        urls += [f"/pages/{quote(slug)}/" for slug in
                 ContentPage.objects.filter(store=store).order_by("pk").values_list("slug", flat=True)]
        rename = {}
        if opts["rename_map"]:
            rename = {new: old for old, new in json.loads(Path(opts["rename_map"]).read_text(encoding="utf-8")).items()}

        client = Client(HTTP_HOST=host, raise_request_exception=True)
        result = {}
        for url in urls:
            try:
                response = client.get(url, secure=True)
            except Exception as exc:  # noqa: BLE001 - an exception is a 500
                result[url] = {"status": f"EXC:{type(exc).__name__}"}
                continue
            entry = {"status": response.status_code}
            if response.status_code == 200 and "text/html" in response.get("Content-Type", ""):
                entry["signature"] = page_signature(
                    response.content.decode("utf-8", "replace"), host=host,
                    offset=opts["offset"], stride=opts["stride"], rename=rename,
                )
            result[url] = entry
        Path(opts["out"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        ok = sum(1 for v in result.values() if v["status"] == 200)
        self.stdout.write(f"{len(result)} URL(s) rendered, {ok} answered 200")
