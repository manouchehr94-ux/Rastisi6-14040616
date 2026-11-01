"""Automatic IndexNow pass for every active store (cron-friendly). Dry-run by default; ``--send`` sends only if ``RASTISI_INDEXNOW_ENABLED`` is on.

A store that is not public, has no verified domain, or has nothing new is skipped quietly. Nothing is sent to anyone otherwise."""

from django.core.management.base import BaseCommand

from apps.core import indexnow_sync
from apps.stores.models import Store


class Command(BaseCommand):
    help = "Send changed / retired public URLs of every eligible store to IndexNow (dry-run unless --send)."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Actually send (needs the platform switch RASTISI_INDEXNOW_ENABLED)")
        parser.add_argument("--store", help="Only this store slug")

    def handle(self, *args, **opts):
        stores = Store.objects.filter(status=Store.Status.ACTIVE)
        if opts["store"]:
            stores = stores.filter(slug=opts["store"])
        for store in stores.order_by("pk"):
            result = indexnow_sync.sync(store, dry_run=not opts["send"])
            self.stdout.write(f"{store.slug}: {result.status} {result.reason} urls={result.metrics.get('urls', 0)}")
