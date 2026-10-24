"""Provision the missing per-store singleton settings rows.

Fixes the root cause of ``ShopSettingsNotProvisionedError`` (HTTP 500 on product
pages): a Store that was imported/created without a ``ShopSettings`` row.

Uses the platform's own ``provision_for`` (get_or_create) so existing rows are
never modified, and never copies another store's settings. A freshly provisioned
row only holds neutral defaults (name = store name); real branding must come from
the original source (see ``import_demo_bundle``).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store


class Command(BaseCommand):
    help = "Create the missing ShopSettings / FooterSettings row of stores (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--store", action="append", help="store slug (repeatable)")
        parser.add_argument("--all", action="store_true", help="every store in the database")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if not opts["store"] and not opts["all"]:
            raise CommandError("pass --store SLUG (repeatable) or --all")
        stores = Store.objects.all() if opts["all"] else Store.objects.filter(slug__in=opts["store"])
        if not opts["all"]:
            missing = set(opts["store"]) - set(stores.values_list("slug", flat=True))
            if missing:
                raise CommandError(f"store(s) not found: {', '.join(sorted(missing))}")
        created = 0
        with transaction.atomic():
            for store in stores:
                for model in (ShopSettings, FooterSettings):
                    if not model.objects.filter(store=store).exists():
                        created += 1
                        self.stdout.write(f"{store.slug}: provisioning {model.__name__}")
                        if not opts["dry_run"]:
                            model.provision_for(store)
        self.stdout.write(self.style.SUCCESS(f"{created} row(s) {'would be ' if opts['dry_run'] else ''}created"))
