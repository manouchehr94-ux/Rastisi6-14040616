"""Re-check pending / unready custom domains of every active store (cron-friendly). Dry run unless ``--run``; ``--run`` also needs the platform switch RASTISI_DOMAIN_AUTOCHECK_ENABLED.
Reads DNS / HTTPS like the seller's own «check» button; never activates a domain and never changes DNS or certificates."""

from django.core.management.base import BaseCommand

from apps.stores.models import Store
from apps.stores.services import domain_autocheck_service


class Command(BaseCommand):
    help = "Periodic read-only domain checks (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--run", action="store_true", help="Actually perform the checks (needs RASTISI_DOMAIN_AUTOCHECK_ENABLED)")
        parser.add_argument("--store", help="Only this store slug")

    def handle(self, *args, **opts):
        stores = Store.objects.filter(status=Store.Status.ACTIVE)
        if opts["store"]:
            stores = stores.filter(slug=opts["store"])
        for store in stores.order_by("pk"):
            result = domain_autocheck_service.recheck_store(store, dry_run=not opts["run"])
            if result.metrics.get("due") or result.status not in ("dry_run", "done"):
                self.stdout.write(f"{store.slug}: {result.status} due={result.metrics.get('due', 0)} {result.reason}")
