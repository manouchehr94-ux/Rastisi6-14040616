"""Import the demo stores from a validated bundle (idempotent).

    python manage.py import_demo_bundle /srv/rastisi/bundle            # both stores
    python manage.py import_demo_bundle /srv/rastisi/bundle --only demo_v5 --dry-run

Creates the Store + verified primary StoreDomain from
``rebuild/manifests/demo_stores.json`` when absent, upserts every bundled row by
primary key, copies and verifies media, and guarantees exactly one ShopSettings
and one FooterSettings per store. Creates NO users and sets NO passwords.
"""

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.stores.services.demo_bundle.importer import ImportAborted, import_store
from apps.stores.services.demo_bundle.targets import load_targets


class Command(BaseCommand):
    help = "Import the two demo stores from a store bundle."

    def add_arguments(self, parser):
        parser.add_argument("bundle")
        parser.add_argument("--only", action="append", help="import only this target key")
        parser.add_argument("--targets", default=None)
        parser.add_argument("--media-root", default=None)
        parser.add_argument("--dry-run", action="store_true", help="validate and run in a rolled-back transaction")
        parser.add_argument(
            "--allow-blocked", action="append", default=[], metavar="CODE",
            help="proceed despite a BLOCKED finding with this code (e.g. studio.layout_missing, singleton.missing); "
                 "the finding stays in the report and the exit code stays 2",
        )
        parser.add_argument("--prune", action="store_true", help="delete store rows that are not in the bundle")

    def handle(self, *args, **opts):
        targets = load_targets(opts["targets"])
        keys = opts["only"] or list(targets)
        unknown = [k for k in keys if k not in targets]
        if unknown:
            raise CommandError(f"unknown target key(s): {', '.join(unknown)}")
        worst = 0
        for key in keys:
            try:
                result = import_store(
                    opts["bundle"], key, targets[key], media_root=opts["media_root"],
                    dry_run=opts["dry_run"], prune=opts["prune"],
                    allow_blocked=tuple(opts["allow_blocked"]),
                )
            except ImportAborted as exc:
                self.stderr.write(exc.report.to_text(show_pass=False))
                worst = max(worst, 2 if exc.report.blocked_any and not exc.report.failed else 1)
                continue
            self.stdout.write(result.report.to_text(show_pass=False))
            self.stdout.write(
                f"{key}: store={result.store.slug} created={result.created_store} rows={sum(result.rows.values())} "
                f"media_copied={result.media_copied} media_identical={result.media_identical}"
                + (" [DRY RUN - rolled back]" if opts["dry_run"] else "")
            )
            if result.report.blocked_any:
                worst = max(worst, 2)
        sys.exit(worst)
