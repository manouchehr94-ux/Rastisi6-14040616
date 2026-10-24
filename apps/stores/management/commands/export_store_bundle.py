"""Export stores into a portable bundle (run where the ORIGINAL data lives).

    python manage.py export_store_bundle --store demo-v5=demo_v5 --store demo-arch02=demo_arch02 --out /tmp/bundle

``--store SLUG=KEY`` maps a source Store slug to the bundle key used by
``rebuild/manifests/demo_stores.json``. Read-only: nothing in the database or
MEDIA_ROOT is modified.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.stores.models import Store
from apps.stores.services.demo_bundle import exporter


class Command(BaseCommand):
    help = "Export one or more stores (catalogue, media, Studio design) into a bundle directory."

    def add_arguments(self, parser):
        parser.add_argument("--store", action="append", required=True, metavar="SLUG=KEY")
        parser.add_argument("--out", required=True)
        parser.add_argument("--media-root", default=None)
        parser.add_argument("--note", default="")

    def handle(self, *args, **opts):
        out = Path(opts["out"])
        if out.exists() and any(out.iterdir()):
            raise CommandError(f"{out} exists and is not empty; refusing to mix bundles")
        media_root = Path(opts["media_root"] or settings.MEDIA_ROOT)
        entries = []
        for spec in opts["store"]:
            slug, _, key = spec.partition("=")
            key = key or slug.replace("-", "_")
            store = Store.objects.filter(slug=slug).first()
            if store is None:
                raise CommandError(f"store {slug!r} not found")
            entry = exporter.export_store(store, out, key=key, media_root=media_root)
            entries.append(entry)
            self.stdout.write(
                f"{slug} -> {key}: "
                f"{sum(entry['counts'].values())} rows, {len(entry['media'])} media files, "
                f"{len(entry['missing_media'])} missing on source"
            )
        exporter.write_manifest(out, entries, note=opts["note"])
        self.stdout.write(self.style.SUCCESS(f"bundle written to {out}"))
