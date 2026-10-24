"""Verify the live demo stores: identity, ShopSettings, files, tenant isolation,
Studio pages and (with --http) real rendering through the middleware stack.

Exit code: 0 = PASS, 1 = FAIL, 2 = BLOCKED.
"""

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.stores.models import Store
from apps.stores.services.demo_bundle.integrity import verify_store
from apps.stores.services.demo_bundle.report import Report
from apps.stores.services.demo_bundle.targets import load_targets


class Command(BaseCommand):
    help = "Read-only integrity verification of the demo stores."

    def add_arguments(self, parser):
        parser.add_argument("--only", action="append")
        parser.add_argument("--targets", default=None)
        parser.add_argument("--media-root", default=None)
        parser.add_argument("--http", action="store_true", help="also render storefront URLs with the Django test client")
        parser.add_argument("--no-decode", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        targets = load_targets(opts["targets"])
        keys = opts["only"] or list(targets)
        total = Report("demo store integrity")
        for key in keys:
            if key not in targets:
                raise CommandError(f"unknown target key {key!r}")
            t = targets[key]
            store = Store.objects.filter(slug=t.slug).first()
            if store is None:
                total.blocked("store.absent", f"store {t.slug} is not in the database (import not run)", t.slug)
                continue
            total.extend(verify_store(
                store, hostname=t.hostname, media_root=opts["media_root"],
                decode_images=not opts["no_decode"], http=opts["http"],
            ))
        self.stdout.write(total.to_json() if opts["json"] else total.to_text())
        sys.exit({"PASS": 0, "FAIL": 1, "BLOCKED": 2}[total.status])
